# Plan — #321 ESPN token bleed (G5, 2026-08-16 wave)

> Security-scoped bug investigation + fix plan. Item #321 (bug, TradeCalculator,
> reported on v1.13.0, mattmurf77): "I tested using another user's account the
> other day and I think it's treating those tokens as mine, but that user is
> not in the espn league I'm in, so it's silently failing."
>
> Base: `origin/main` @ `d3fe3ac` (v1.13.4). All file:line references are
> against that sha. Batch context:
> [`../304-positional-need-filter/batch-plan.md`](../304-positional-need-filter/batch-plan.md).
> Operator fact (binding, chat 2026-08-16): both accounts were used on the
> **same physical device**.

## 1. Blast-radius verdict (up front)

**Bounded — device-scoped, not a server-side cross-user bug.** Server storage
and every read of it are keyed by the FTF account:

- `espn_credentials` table: `user_id` is the **primary key** —
  `backend/database.py:1523-1530`.
- `user_id` at request time comes from the session resolved off the
  `X-Session-Token` header (`_require_session`, `backend/server.py:2271-2296`;
  `sess.get("user_id")` at `backend/server.py:20084-20087`), never from a
  device id or request body. `X-Device-Id` exists but feeds only
  `identity_links` analytics (`mobile/src/api/auth.ts:44-46`).
- All credential reads/deletes are scoped to that session user
  (`get_espn_credential(user_id)` / `delete_espn_credential(user_id)`,
  e.g. `backend/server.py:20090`, `20095`, `20387`, `23454`).

No path lets FTF user B read user A's stored credential. The bleed happened
**on the device**: the ESPN Connect WebView captures `espn_s2`/`SWID` from the
**app-wide native cookie store** (WKHTTPCookieStore,
`mobile/src/utils/espnCookies.ts:1-30`), which is shared across every FTF
account and every ESPN login performed on that phone.

**Honest nuance:** although the storage keying is sound, the consequence of
the bleed is real — the *other human's* ESPN session credential ended up in
the operator's `espn_credentials` row, where FTF will exercise it (league
reads, and trade proposals via `espn.send` would be authored *as that
person*). Severity is bounded by "requires sharing a physical device and
signing into ESPN in the app," but the fix must both stop the capture leak
(already shipped, §3) and evict/prevent wrong-identity rows (this plan).

## 2. Verified storage/keying model

| Layer | Where | Keying |
|---|---|---|
| Capture | `EspnConnectScreen` WebView → native cookie store poll (`mobile/src/utils/espnCookies.ts` `pickEspnCookies`; D-021) | **Device-scoped** — WKHTTPCookieStore is app-wide; ESPN/Disney SSO cookies belong to whoever last signed in on the device |
| In-flight (mobile) | `espnConnectBus` (module memory) + `pairRef` in the screen; link flow hands the pair to `POST /api/espn/link` | Never persisted device-side — no AsyncStorage/SecureStore ESPN entries exist (verified by grep) |
| At rest (server) | `espn_credentials` (`backend/database.py:1523-1530`): `user_id` PK, `swid` plaintext, `espn_s2_encrypted` Fernet, `verified_at` honesty stamp | **Account-scoped** (FTF `user_id` from the session token) |
| Consumption | link/import (`server.py:20020+`, `20415+`), my-leagues picker (`20355+`), propose-espn pre-flight (`23420+`), suggested draft order (`11071-11110`), YR-8 roster sweep (`16755-16830`) | All resolve the credential via the row's / session's `user_id` |

Key structural fact for the fix: the membership snapshot stores every
*other* manager as `espn:{SWID}` (`_espn_member_id`,
`backend/server.py:19858-19862`), but the linking user's own row is replaced
by their FTF `user_id` (`server.py:20278`, `20470`) — so **the user's own
team's owner-SWID is not stored anywhere**, and an identity check must get it
from a live `fetch_league`/fan-profile read at verify time (both already
return it: `parse_league` teams carry `owner_swid`,
`backend/espn_service.py:442,477-504`).

## 3. Timeline — what v1.13.0 had vs. what already shipped

The report is against **v1.13.0** (shipped 2026-08-11, `3af201a`). The
2026-08-12 incident (same operator, same shape — recorded in the
`DELETE /api/espn/link` docstring at `server.py:20027-20031` and in
`espnCookies.ts:66-73`) drove three fixes that shipped in **v1.13.2**
(`3293f4a`, `2fa1ff2`, `7dfcd16`, all 2026-08-12):

1. **Clear-on-mount**: `EspnConnectScreen` clears the espn.com + Disney-SSO
   cookie jars before the WebView mounts (gated on `storeCleared`), so every
   capture is a fresh login — a surviving Disney session can no longer
   silently re-authenticate the previous human.
2. **Verify-before-store** with a real oracle (`_espn_verify_credential`,
   `server.py:19915-20018`): a pair is stored (and `verified_at` stamped)
   only after an asserted authenticated read.
3. **DELETE /api/espn/link** — user-facing disconnect (Settings row), the
   removal path the incident lacked.

So on v1.13.4 the *capture-time* leak is closed. What #321 still needs is
below.

## 4. Root cause of the bleed (v1.13.0 code)

Three stacked causes, on one device:

1. **Shared device cookie jar + Disney SSO silent re-auth** — after the other
   person's ESPN login, their `espn_s2`/`SWID` (and Disney OneID session)
   persisted in the app-wide native store; the next capture harvested them
   ~1s after mount, before any login was visible
   (`EspnConnectScreen.tsx` header comment; `espnCookies.ts:66-73`).
   *Fixed 2026-08-12 (clear-on-mount).*
2. **No verification before store** (v1.13.0): the pre-fix store path stamped
   `verified_at` off an unbound fan-leagues call that never raises
   (`server.py:20134-20142` comment records exactly this), so the wrong
   pair was persisted as verified under the operator's `user_id`.
   *Partially fixed 2026-08-12 (oracle).*
3. **No identity binding — still open at `d3fe3ac`.** Even the current oracle
   proves only "this pair is a valid ESPN session for *some* account":
   - The **strong oracle** (league read, `server.py:19957-20001`) runs only
     when a linked league has `espn_auth == 'cookie'`. It proves the pair can
     read the league — any *member's* pair passes, and for the wrong-human
     case it correctly 403s. But with only PUBLIC (or no) linked leagues it
     never runs.
   - The **weak oracle** (fan profile, `server.py:20003-20018`) passes any
     valid ESPN account whatsoever — it never checks that the account is in
     the caller's league, let alone owns the bound team.
   - The **league-link path** stamps `verified_at` for pasted/captured
     cookies whenever the league fetch succeeded (`server.py:20262-20272`)
     — for a PUBLIC league that fetch succeeds with *any* cookies, so a
     wrong pair is still stamped verified today.

## 5. Root cause of the silent failure

The wrong pair, once stored with `verified_at`, is trusted everywhere and its
downstream failures are individually rationalized:

- `GET /api/espn/link` reports `{connected: true}` from the stamp alone — no
  live call, by design (`server.py:20094-20117`). Settings and
  `SendInEspnButton` therefore show "connected". **Nothing anywhere compares
  the stored SWID to the user's league membership.**
- `GET /api/espn/my-leagues` keys the fan profile on the stored SWID
  (`server.py:20355-20413`) — it happily lists the *other person's* leagues.
  Wrong identity, zero mismatch signal.
- Suggested draft order fails soft — `_espn_standings_read` returns
  `(None, None)` on any failure with an info log (`server.py:11071-11110`);
  the feature is just absent.
- YR-8 roster sweep nudges on `EspnAuthError` via an `espn_reconnect` inbox
  row (`server.py:16743-16771`) — visible, but the copy says "sign-in stopped
  working", which is the wrong diagnosis for a wrong-account pair.
- The send pre-flight does fail loudly (409 `espn_auth_expired` + credential
  delete, `server.py:23504-23517`) — but only if/when the user tries a send,
  and again with "expired" copy for a wrong-account condition.
- Mobile: when a store *is* rejected, `EspnConnectScreen` renders its own
  fixed 'rejected' copy and discards the server's message
  (`EspnConnectScreen.tsx:398-419`) — so even the existing wrong-account
  message minted at `server.py:20158-20164` ("that ESPN account can't open
  your linked league") never reaches the user.

Net: valid-but-wrong-human tokens produce "connected" status plus a scatter
of quietly-degraded features — precisely "treating those tokens as mine …
silently failing."

## 6. Fix approach

### F1 — Identity binding at verify time (server; the core fix)

Extend `_espn_verify_credential` (`server.py:19915`) with a **membership
check** that runs on every verification, independent of oracle strength:

- Load the caller's linked ESPN leagues (already done for the strong oracle).
  For the newest league row with a team binding (`espn_my_team_id`):
  - If the strong oracle's `fetch_league` ran, its parsed teams already carry
    `owner_swid` — assert `canonical_swid(captured_swid)` equals the bound
    team's `owner_swid` (fall back to "is any team's owner" if the bound
    team is ownerless; comparison pattern exists at `server.py:23369`).
  - If the league is PUBLIC (strong oracle skipped), still `fetch_league` it
    — a public read needs no auth but *does* return `owner_swid`s — and run
    the same assertion. (This read is the membership oracle, not an auth
    oracle; the fan probe remains the auth proof.)
  - No linked league at all → membership check is vacuous; weak oracle
    verdict stands (nothing to mismatch against yet).
- New verdict `"wrong_account"` → HTTP 403, wire code stays
  `espn_bad_credentials` (client compatibility; `espnCredentialsRejected`
  keeps working) with a new additive `reason: "wrong_account"` field and the
  existing recovery copy ("Sign in with the ESPN account that owns your
  team").
- Same assertion added to the **league-link POST** path: when cookies are
  pasted/captured with an `espn_league_id` + chosen `team_id`, compare the
  captured SWID to the chosen team's `owner_swid` from the fetch already in
  hand (`server.py:20262-20272`) — refuse the stamp on mismatch. Also stop
  stamping `verified_at` for a PUBLIC-league fetch unless
  `_espn_verify_credential` separately passes (closes the §4.3 public-league
  stamp gap).

Skipped-on-purpose: ESPN leagues can have co-owned/ownerless teams, so the
mismatch check must treat "bound team has no `owner_swid`" as *inconclusive*
(accept), never as a reject — zero-false-reject posture mirrors the existing
weak-oracle rule (`server.py:19948-19954`).

### F2 — Evict already-polluted rows (migration/cleanup)

Rows stamped before the 2026-08-12 oracle fix may be wrong-human pairs (the
operator's almost certainly is). One-time data migration in `_migrate_db()`
(`backend/database.py:2046`, idempotent per existing pattern):

```
UPDATE espn_credentials SET verified_at = NULL
WHERE verified_at < '2026-08-12T20:00:00+00:00'   -- deploy time of 7dfcd16
```

The GET honesty gate (`server.py:20098-20101`) already treats
`verified_at IS NULL` as **not connected**, so affected users just re-run the
(now clearing + verifying + identity-bound) sign-in. No row deletion — the
encrypted pair stays for forensics/idempotence, exactly like legacy
pre-verification rows already behave. Blast radius of the migration: every
pre-08-12 ESPN-connected user gets one re-sign-in ask; the ESPN cohort is
small (operator + friends) and the alternative — leaving possibly-wrong
identities trusted — is worse.

### F3 — Surface the mismatch state (mobile, small)

- `EspnConnectScreen`: on a 403 with `reason === 'wrong_account'`, render the
  server's message (or a dedicated variant) instead of the generic 'rejected'
  copy — the recovery ("use the ESPN account that owns your team") is
  materially different from "sign in again"
  (`EspnConnectScreen.tsx:398-419`, `mobile/src/api/espn.ts:112-119`).
- `_espn_reconnect_nudge` (`server.py:16746`): accept a `reason` already —
  add `wrong_account` copy when the sweep's auth failure follows an
  identity-mismatch deletion, so the inbox row states the true diagnosis.
  (Nice-to-have; drop if it bloats the change.)

### F4 — Considered and rejected

- **Clearing ESPN cookies on FTF sign-out** — redundant: `EspnConnectScreen`
  clears on every mount, and nothing else reads the jar. No change.
- **Re-keying device storage by account** — nothing credential-shaped is
  persisted device-side (§2); there is nothing to re-key.
- **Storing the user's own SWID in a new column** to enable offline checks —
  schema change for marginal benefit; the live read at verify time suffices.
  Revisit if/when the auth epic's `linked_sources` lands.

**Server-side change needed? Yes** (F1 + F2). No schema change; one additive
response field; no new route; no flag surface touched. Under the batch's
bright-line rule this stays within "bug fix with an additive error field" —
flagging to the orchestrator regardless since it grazes an API contract:
`docs/api-reference.md` must gain the `reason` field + migration note.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Membership check adds a live ESPN read on public-league verifies | Only at store time (rare); reuse the fetch already made in the link path; fail-open (`unavailable` → 502, nothing stored) exactly like the existing oracle |
| False rejects on co-owned/ownerless teams | Inconclusive-accepts rule (F1); unit-test the ownerless fixture |
| Migration logs out legitimate pre-08-12 pairs | Deliberate; small cohort; re-sign-in is the safe path and the copy explains it |
| ESPN payload shape drift breaks the `owner_swid` comparison | Comparison uses `parse_league`'s existing parsed shape + `canonical_swid` (`espn_service.py:124`); missing field → inconclusive, never a crash |
| Client on an old build sees the new 403 | Wire code unchanged (`espn_bad_credentials`) → old builds show today's generic rejected copy, no breakage |

## 8. File ownership (build phase)

| File | Change |
|---|---|
| `backend/server.py` | F1: membership check in `_espn_verify_credential` + link-path SWID assertion + public-league stamp fix; F3 nudge copy |
| `backend/database.py` | F2 migration in `_migrate_db()` |
| `mobile/src/screens/EspnConnectScreen.tsx` | F3 wrong-account copy |
| `mobile/src/api/espn.ts` | Narrowing helper reads optional `reason` |
| `docs/api-reference.md` | `espn_bad_credentials.reason` field; migration note |
| `docs/data-dictionary.md` | `verified_at` semantics addendum (invalidation event) |
| `tests/` (backend) + `mobile/tests/` | See §9 |

No overlap with G1–G4/G6/G9 files per the batch plan.

## 9. Test plan (per D-056 — Maestro retired)

**Backend unit tests** (pytest, mocked ESPN transport):
1. Verify: wrong SWID vs bound team's `owner_swid`, cookie league → 403
   `reason: wrong_account`, nothing stored.
2. Verify: wrong SWID, PUBLIC linked league → membership read runs → 403
   wrong_account (the gap case).
3. Verify: correct SWID, each oracle → stored + stamped.
4. Verify: bound team ownerless / `owner_swid` missing → inconclusive-accept.
5. Verify: no linked league → weak oracle verdict stands (unchanged).
6. Link path: pasted cookies + PUBLIC league → no `verified_at` stamp without
   a passing verify; chosen-team SWID mismatch → refused.
7. Migration: pre-cutoff stamp → NULL; post-cutoff untouched; idempotent
   re-run; GET reports `connected: false` for the nulled row.

**Structural checks** (`check-*.js` / grep-provable):
- `EspnConnectScreen` renders a distinct wrong-account string when
  `reason === 'wrong_account'`.
- No new device-side persistence of `espn_s2`/`SWID` introduced.

**Operator TestFlight checklist** (runtime proof — the two-account switch
sequence, on one physical device):
1. Settings → Disconnect ESPN (clears any residue) → status shows *not
   connected*.
2. Sign in to ESPN in-app as **Account A (yours, in league)** → connected;
   my-leagues picker lists *your* leagues; send pre-flight passes.
3. Disconnect. Sign in as **Account B (the other person, not in your
   league)** → expect the **wrong-account rejection with the new copy**;
   status remains *not connected*; nothing stored (re-open Settings to
   confirm).
4. Without disconnecting anything, open ESPN Connect again → confirm the
   login page is genuinely signed out (clear-on-mount) — no silent
   re-authentication as Account B.
5. Re-sign-in as Account A → connected again; propose a test trade to prove
   end-to-end.
6. Post-deploy (before any of the above): confirm the migration signed you
   out of ESPN (status *not connected* on first launch) — that is the
   residue eviction working.

## 10. Living-memory / docs write-backs (ship time)

- `living-memory/CHANGELOG.md` entry; `TEST_LEDGER.md` run record.
- `GOTCHAS.md` candidate: "a verified_at stamp proves session validity, not
  identity — membership binding is a separate assertion."
- `docs/runbook.md`: note the one-time re-sign-in support question the
  migration will generate.
