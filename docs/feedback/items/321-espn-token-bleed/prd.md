# PRD — #321 ESPN token bleed (G5, 2026-08-16 wave)

> Mini-PRD (fast-track bug path) for feedback #321. Companion to
> [`plan.md`](plan.md) (dual-agent plan, complete), [`scope.md`](scope.md),
> [`review-round-1.md`](review-round-1.md), and
> [`reconciliation-log.md`](reconciliation-log.md) (round-1 dispositions).
> Revised 2026-08-16 after review round 1 (B1–B3 incorporated; N1–N5
> incorporated).
> Batch context:
> [`../304-positional-need-filter/batch-plan.md`](../304-positional-need-filter/batch-plan.md).
>
> **Base:** all file:line cites verified against `origin/main` @ `d3fe3ac`
> (v1.13.4), the batch baseline. Every plan citation was re-checked against
> that sha by this author; all verified (see §8).
>
> **Line-drift note for builders:** `origin/main` has since advanced to
> `0b2dcee` (guide-v2 + fit-congruence, unrelated to ESPN). The only hunks
> touching our files sit at `backend/server.py` ~10311 (+15 lines) and
> `backend/database.py` ~2016 (+3 lines) — so on current main, `server.py`
> cites above 10311 shift **+15** and `database.py` cites above 2016 shift
> **+3**. All ESPN code is otherwise byte-identical between the two shas.
>
> This is an API-contract-touching change (additive `reason` field + a new
> 403 path + a data migration). No lld-delta is owed on the fast-track path,
> so **§5 of this PRD is the full contract of record** for the changed
> responses. The batch selection placed G5 on full gates with operator
> awareness of the bright line.

## 1. The report, and what actually happened

**Report (#321, mattmurf77, v1.13.0, TradeCalculator):** "I tested using
another user's account the other day and I think it's treating those tokens
as mine, but that user is not in the espn league I'm in, so it's silently
failing."

**Repro narrative (same physical device — operator-confirmed):**

1. The other person signs in to ESPN inside FTF's ESPN Connect WebView (or
   simply had a live ESPN/Disney web session on the device). Their
   `espn_s2` + `SWID` — and their Disney OneID SSO session — land in the
   **app-wide native cookie store** (WKHTTPCookieStore, shared across every
   FTF account on the phone; `mobile/src/utils/espnCookies.ts:1-30`).
2. The operator, signed in to FTF as themselves, opens ESPN Connect. On
   v1.13.0 the screen did not clear the jar first, so the poll harvested the
   stale pair ~1s after mount — before any login was even visible — and a
   surviving Disney session would silently re-authenticate the previous
   human with no password prompt (`espnCookies.ts:60-73`;
   `EspnConnectScreen.tsx:28-37` header comment records exactly this).
3. The v1.13.0 store path stamped `verified_at` off an unbound fan-leagues
   call that never raises (the pre-fix bug is memorialised in the comment at
   `backend/server.py:20130-20141`) — so the *other human's* credential was
   persisted as verified under the **operator's** `user_id`.
4. From then on everything trusted the stamp: Settings showed "connected",
   my-leagues listed the other person's leagues, and features quietly
   degraded (§3) — "treating those tokens as mine … silently failing."

**Already fixed before this item (v1.13.2, 2026-08-12):** clear-on-mount
(fresh login every capture), verify-before-store with a real oracle
(`_espn_verify_credential`, `server.py:19915-20018`), and
`DELETE /api/espn/link` (user-facing disconnect). What remains — and what
this PRD covers — is the **identity-binding hole** (Defect A), the **silent
failure** (Defect B), and **eviction of already-polluted rows** (the
migration).

## 2. Defect A — verification proves session validity, not identity

At `d3fe3ac`, `_espn_verify_credential` proves only "this pair is a valid
ESPN session for *some* account" (all verified):

- **Strong oracle** (`league_read`, `server.py:19956-19999`): runs only when
  a linked league has `espn_auth == 'cookie'`. Any league *member's* pair
  passes; with only PUBLIC (or no) linked leagues it never runs.
- **Weak oracle** (`fan_profile`, `server.py:20003-20018`): passes any valid
  ESPN account whatsoever. No membership check of any kind.
- **League-link import path** (`server.py:20256-20272`): pasted/captured
  cookies are stamped `verified_at` whenever the league fetch succeeded —
  but a PUBLIC league fetch succeeds with *any* cookies, so a wrong pair is
  still stamped verified today. (This residual is already confessed in
  `docs/api-reference.md` line 550, "Known residual (2026-08-12)".)
- **Nothing anywhere compares the stored SWID to the user's league
  membership.** The membership snapshot replaces the linking user's own row
  with their FTF `user_id` (`server.py:20278`, `20470`), so the user's own
  owner-SWID is not stored — an identity check must read it live
  (`parse_league` teams carry `owner_swid`,
  `backend/espn_service.py:442, 477-504`).

## 3. Defect B — the wrong identity fails silently

Once a wrong-human pair carries a `verified_at` stamp (all verified):

- `GET /api/espn/link` reports `{connected: true}` from the stamp alone — no
  live call, by design (`server.py:20097-20117`).
- `GET /api/espn/my-leagues` keys the fan profile on the stored SWID and
  lists the *other person's* leagues (`server.py:20354-20413`).
- Suggested draft order fails soft — `(None, None)` + info log
  (`server.py:11071-11110`); the feature is just absent.
- The YR-8 sweep's `espn_reconnect` inbox nudge says "sign-in stopped
  working" (`server.py:16743-16771`) — wrong diagnosis for a wrong account.
- The send pre-flight fails loudly but late and mislabeled: 409
  `espn_auth_expired` + credential delete (`server.py:23504-23517`).
- Mobile: `EspnConnectScreen` renders a *fixed* 'rejected' string and
  discards the server's message (`EspnConnectScreen.tsx:398-419`,
  `storePair` at 217-230) — so even the existing wrong-account copy minted
  at `server.py:20155-20161` never reaches the user.

## 4. Requirements

### Defect A — identity binding (server)

- **R1 — Membership assertion on every verify, across ALL bound leagues.**
  Extend `_espn_verify_credential` (`server.py:19915`) with a membership
  check that runs regardless of oracle strength. **Set semantics, no
  ordering:** evaluate **every** linked ESPN league row of the caller that
  has a team binding (`espn_my_team_id` not NULL) — deliberately not
  "newest" or "first": `load_espn_leagues_for_user`
  (`backend/database.py:10606`) pins no order, and one ESPN human owns one
  SWID, so a conclusive mismatch against *any* bound league indicates the
  wrong account. Per league:
  - League already fetched as the strong oracle: its parsed teams are in
    hand — assert `canonical_swid(captured_swid)` equals the bound team's
    `owner_swid` (canonicalised compare per the existing pattern at
    `server.py:23367-23370`; `canonical_swid` at `espn_service.py:124`).
  - Otherwise (PUBLIC league, or additional cookie leagues beyond the
    oracle): `fetch_league` it — at most **one live read per league**, store
    time only — and run the same assertion. A public read needs no auth but
    returns `owner_swid`s; this read is the *membership* oracle only, the
    fan probe remains the auth proof.
  - **Verdict precedence:** any conclusive mismatch → `wrong_account`
    (even if another league matched or a read failed) → all conclusive
    matches / inconclusives → accept → otherwise any membership-read
    transport failure → `unavailable` (R6). A mismatch on one league while
    another matches means the *binding* is wrong (mis-picked team at
    import) — surfacing that as `wrong_account` with re-link recovery is
    intended, not a false reject.
- **R2 — New verdict, additive wire field.** Mismatch → verdict
  `wrong_account` → HTTP 403 with wire code **unchanged**
  (`espn_bad_credentials`, so `espnCredentialsRejected` at
  `mobile/src/api/espn.ts:112-119` keeps working on old and new builds) plus
  a new additive `reason: "wrong_account"` field and recovery copy naming
  the real fix ("Sign in with the ESPN account that owns your team" — the
  copy already minted at `server.py:20155-20161`). Nothing is stored.
- **R3 — Team-binding assertion, regardless of cookie provenance.** The
  membership assertion runs at the league-link **team-binding step**
  (`POST /api/espn/link` with `espn_league_id` + `team_id`,
  `server.py:20256-20290`) whenever a cookie pair accompanies the import —
  **pasted, captured, or the stored-credential fallback**
  (`server.py:20206-20216`, `pasted_cookie=False`). The team list with
  `owner_swid`s is already in hand from the import fetch, so this is
  comparison-only — no extra ESPN read. Compare the pair's SWID (pasted or
  stored) to the chosen team's `owner_swid`; on conclusive mismatch → the
  403 of R2, nothing imported — **and, when the mismatching SWID is the
  STORED credential's SWID** (stored-fallback case, or a pasted pair equal
  to the stored one), **null the stored row's `verified_at` stamp** so
  `GET` status stops lying (row kept, consistent with R10's no-delete
  forensics posture; a mismatching pasted pair that differs from the stored
  one says nothing about the stored row and leaves it untouched). This closes the store-then-link hole: a
  pair stored under R5's vacuous accept (no league yet) is re-checked the
  moment a league gets a team binding.
  - **R3b — Re-sync assertion.** Same comparison-only assertion in
    `espn_import` re-sync (`server.py:20415+`): the stored SWID, the row's
    `espn_my_team_id`, and the fetched teams are all in hand
    (`server.py:20462-20470`). Conclusive mismatch → 403 `wrong_account` +
    null the stamp. Cheap, and it catches wrong-identity rows bound before
    this fix that the migration alone cannot identify.
- **R4 — Close the public-league stamp gap, without punishing the import.**
  On the import path, a PUBLIC-league fetch proves nothing about the pair,
  so it no longer stamps `verified_at` by itself (removes the "Known
  residual" confessed in `docs/api-reference.md`). Semantics (revised per
  review N2 — the credential is *optional* to a public import):
  - Membership mismatch vs the chosen team (R3) → 403, import blocked —
    identity failures always block.
  - No mismatch: the **import succeeds regardless of credential health.**
    `_espn_verify_credential` then decides the pair's fate: `ok` → stored +
    stamped; `bad` or `unavailable` → the pair is **not stored** (an
    unproven pair must not reach the DB — existing principle), the import
    still returns 200, and the response says so via the additive
    `credential_stored` field (§5). A fan-probe hiccup never fails a
    working public-league import.
  - Cookie-league imports are unchanged: the import fetch itself is a
    genuine authenticated proof, and R3's comparison guards identity.
- **R5 — Zero false rejects.** Bound team ownerless / co-owned /
  `owner_swid` missing or shape-drifted → **inconclusive-accept**, never a
  reject and never a crash (mirrors the weak oracle's zero-false-reject
  posture, `server.py:19945-19951`). No linked league at all → membership
  check is vacuous; weak-oracle verdict stands. **Deliberate drop from plan
  §F1** (review N4): the plan's ownerless fallback ("is any team's owner")
  is intentionally NOT implemented — unconditional inconclusive-accept is
  simpler and strictly zero-false-reject. Builders must not restore the
  fallback from the plan.
- **R6 — Fail-open on outage.** Membership-read transport failure / 5xx /
  unparseable → `unavailable` → 502 `espn_unavailable`, nothing stored —
  identical to the existing oracle's posture, and subordinate to R1's
  precedence (a conclusive mismatch elsewhere still rejects). A user with a
  good sign-in is never told it's bad because ESPN was down.

### Defect B — surface the mismatch (mobile + inbox)

- **R7 — Wrong-account state on `EspnConnectScreen`.** On a 403 with
  `reason === 'wrong_account'`, render the wrong-account recovery copy
  (server's message or a dedicated variant) instead of the generic
  'rejected' string (`EspnConnectScreen.tsx:398-419`); the retry control
  resets to a genuinely fresh sign-in (existing `retryStore` 'rejected'
  branch behavior, `EspnConnectScreen.tsx:236-252`). Distinct element or
  string reachable by a structural check. **Link-path surface (review N1,
  verified):** the R3/R3b 403s reach the user through `EspnLinkSheet`'s
  existing generic catch — `ApiError` carries the server's `message`
  (`mobile/src/api/client.ts:552-553`) and the sheet renders it under
  testID `espn-link.error` (`EspnLinkSheet.tsx:287, 324, 528, 549`); the
  `isEspnAuthRequired` branch (`:277, :314`) matches only
  `espn_auth_required`, so a 403 `espn_bad_credentials` falls through to
  the message render. This is the intended surface — no sheet change
  required, but §7.2 pins it structurally so a later refactor can't
  swallow it.
- **R8 — Typed reason on the client.** `mobile/src/api/espn.ts` gains a
  narrowing helper (or extension of `espnCredentialsRejected`) exposing the
  optional `reason` field. Absent field → exactly today's behavior.
- **R9 — Honest nudge copy (nice-to-have; droppable if it bloats the
  diff).** `_espn_reconnect_nudge` (`server.py:16743`) already takes a
  `reason` kwarg — add `wrong_account` copy when the sweep's auth failure
  follows an identity-mismatch deletion, so the inbox row states the true
  diagnosis instead of "sign-in stopped working". **Constraint (review N3,
  verified): reuse the existing `espn_reconnect` notification type — same
  type, new copy/`meta.reason` only.** The web client allowlists inbox row
  types (`web/js/app.js:4895`) and maps `espn_reconnect` (`:4716`); a new
  type string would be silently dropped on web.

### Residue eviction — migration

- **R10 — One-time idempotent migration** in `_migrate_db()`
  (`backend/database.py:2046` @ d3fe3ac; ~2049 on current main). **Respec'd
  after review B1** — the original cutoff (`2026-08-12T20:00:00+00:00`,
  claimed to be `7dfcd16`'s deploy time) was factually wrong in the unsafe
  direction. Timestamps verified this round from git:
  - `2fa1ff2` (introduces `espn_credentials.verified_at` and the broken
    unbound-fan-leagues verify; the earlier `verified_at` in the repo,
    `920a638` 2026-07-11, is `users.verified_at` — different table) —
    committed **2026-08-12T04:25:58Z**. Rows stored before it have no stamp
    at all (born-NULL) and already read `connected: false`.
  - `7dfcd16` (real-oracle fix) — committed **2026-08-13T02:27:03Z**, ~6.5h
    *after* the old cutoff: the dishonest-stamp window
    `04:26Z → 02:27Z(+deploy lag)` was partly left trusted.

  **Respec — evict every pre-release stamp, not just the dishonest-verify
  window:**

  ```sql
  UPDATE espn_credentials SET verified_at = NULL
  WHERE verified_at < '<RELEASE_CUTOFF>'   -- finalized at ship, see below
  ```

  - **Why full eviction:** even post-`7dfcd16` stamps prove session
    validity, never identity — the weak oracle vacuously accepts any
    account (R5's no-league case), the public-league import gap (R4)
    stamped with no verify at all, and the strong oracle passes any league
    *member's* pair. Identity binding does not exist until this release, so
    **no existing stamp is identity-trustworthy**. Under-eviction re-opens
    #321; over-eviction costs one harmless re-sign-in (zero benefit of the
    doubt to the unsafe direction).
  - **Cutoff mechanics:** `_migrate_db` runs on every boot, so the UPDATE
    must stay date-bounded — an unbounded "null all stamps" would sign
    users out on every deploy. `<RELEASE_CUTOFF>` is a literal finalized at
    ship: the observed deploy-completion time of THIS release (Render
    dashboard), else push-to-main time **plus a generous margin (+1h)** —
    erring later is safe (a stamp minted by the new identity-bound code
    inside the margin is re-nulled once at next boot; that user re-signs-in
    one extra time, nothing worse). The chosen literal and both commit
    timestamps above go in the ship-time DECISIONS entry.
  - **Idempotent:** after the first run every matched row is NULL, and
    `NULL < '<cutoff>'` is NULL in SQLite/Postgres three-valued logic — not
    matched — so re-runs are structural no-ops, not accidents of data.
    Named explicitly because the `_migrate_db` try/except wrapper would
    otherwise swallow a permanently-failing UPDATE. Comparison is
    lexicographic over ISO UTC strings — valid because `verified_at` is
    always written via `datetime.now(timezone.utc).isoformat()` (uniform
    `+00:00` offset); T9's fixtures prove the boundary in the same format.
  - **No row deletion:** the encrypted pair stays (forensics + idempotence),
    exactly how born-NULL legacy rows already behave. The GET honesty gate
    (`server.py:20097-20101`, verified) already treats
    `verified_at IS NULL` as **not connected**, so affected users are simply
    routed through the now clearing + verifying + identity-bound sign-in.
  - **Blast radius (corrected):** the **entire ESPN-connected cohort**
    (small — operator + friends) gets exactly one re-sign-in ask, including
    users who signed in correctly after 08-12. Pre-`2fa1ff2` rows are
    untouched (already NULL). The operator's own polluted row is evicted.
    Wrong-identity rows the migration can't see coming (stored post-release
    under a vacuous accept, then bound) are caught by R3/R3b instead.
  - Support note goes in `docs/runbook.md` (drafted in plan §10; see
    scope.md docs table).

### Analytics

- **R11 — Instrument the rejection.** New client event
  `espn_connect_store_rejected` (spec in `scope.md` §1) fired when
  `storePair` fails, with `reason` distinguishing `wrong_account` /
  `bad_credentials` / `unavailable`. Today no failure event exists at all
  (verified: `EspnConnectScreen` tracks only opened / captured / abandoned /
  otp_step).

## 5. API contract (contract of record — no lld-delta on this path)

### `POST /api/espn/link` — changed error surface

Route: `server.py:20020` (`espn_link`), both the credential-only store path
and the league-link import path. **Request shapes are unchanged:**

```jsonc
// credential-only store (send-auth lazy flow)
{ "espn_s2": "<string>", "swid": "<string>" }

// league import (after preview)
{ "espn_league_id": "<digits>", "season": 2026, "team_id": 3,
  "espn_s2": "<string, optional>", "swid": "<string, optional>" }
```

**403 rejection — extended (additive only):**

```jsonc
{
  "error":   "espn_bad_credentials",   // string, UNCHANGED — client compat
  "reason":  "wrong_account",          // string, OPTIONAL, NEW — present
                                       //   only for identity mismatch
  "message": "That ESPN account can't open your linked league, so nothing was saved. Sign in with the ESPN account that owns your team."
}
```

- `error` (string, required): wire code stays `espn_bad_credentials` for
  every credential rejection. Old builds keep matching on it
  (`espnCredentialsRejected`) and show today's generic rejected copy — no
  breakage.
- `reason` (string, optional, additive): only defined value in this change
  is `"wrong_account"`. Absent on plain bad-credential rejections. Clients
  must tolerate absence and unknown future values.
- `message` (string, required): human recovery copy; wrong-account variant
  already exists at `server.py:20155-20161`.

**New conditions that now produce this 403** (previously stored + stamped,
or stamped via the public-league gap):

1. Credential-only store where the pair authenticates but its SWID
   conclusively mismatches the bound team's `owner_swid` of **any** of the
   caller's linked leagues with a team binding — cookie or public leagues
   alike (R1; precedence: mismatch > accept > unavailable).
2. League import with `team_id` where the pair's SWID — **pasted, captured,
   or the stored-credential fallback** — does not own the chosen team (R3).
   When the mismatching SWID is the stored credential's, the stored row's
   `verified_at` is also nulled.
3. `POST /api/espn/import` (re-sync) where the stored SWID no longer owns
   the row's bound team (R3b); the stamp is nulled.

**New additive success field — import path only (R4):** when a cookie pair
accompanied a league import (any provenance), the 200 import response gains:

```jsonc
{
  // ...existing import success fields unchanged...
  "credential_stored": true,          // boolean, OPTIONAL, NEW — present
                                      //   only when a pair accompanied the
                                      //   import
  "credential_reason": "unverified"   // string, OPTIONAL — present only
                                      //   when credential_stored is false:
                                      //   "unverified" (verify said bad)
                                      //   | "unavailable" (couldn't judge)
}
```

Clients must tolerate absence (old servers) and ignore unknown values. No
mobile UI consumes it in this change — it exists so the contract states the
pair's fate instead of implying it.

**Behavioral contract change on the import path (R4, revised per review
N2):** a PUBLIC-league fetch no longer stamps `verified_at` by itself.
Identity mismatch (R3) blocks the import with the 403; otherwise the
**import always succeeds independent of credential health** — the pair is
stored + stamped only if `_espn_verify_credential` passes, else it is not
stored at all and the response says so via `credential_stored: false`. A
fan-probe outage never fails a public-league import (it lands in
`credential_reason: "unavailable"`, not a 502). Cookie-league imports keep
their existing stamp semantics (the import fetch is a genuine auth proof).

**Unchanged:** 502 `espn_unavailable` shape and semantics — on the
credential-only store path, membership-read outages land here per R6,
nothing stored; 200 success shapes for store / preview (import gains only
the additive fields above); `GET /api/espn/link` response shape
(`{connected, expires_at, expired, verified_at}`) — though post-migration,
every pre-release row reports `connected: false` until re-verified;
`DELETE` unchanged.

### Schema

**None.** No new tables, columns, routes, or flags. R10 is a data migration
over existing columns only.

## 6. What is NOT changing (and why)

- **Server-side keying is already account-scoped — this was never a
  cross-user server bug.** `espn_credentials.user_id` is the **primary
  key** (`backend/database.py:1523-1530`, verified: one row per FTF user);
  `user_id` at request time comes only from the session resolved off
  `X-Session-Token` (`_require_session`, `server.py:2271-2296`; then
  `sess.get("user_id")` at `server.py:20084-20087`), never from a device id
  or request body (`X-Device-Id` feeds only `identity_links` analytics,
  `mobile/src/api/auth.ts:44-46`). All credential reads/deletes are scoped
  to that session user (`server.py:20093`, `20100`, `20389`, `23454-23459`).
  No path lets FTF user B read user A's stored credential.
- **No device-side credential storage to re-key** — nothing
  credential-shaped is persisted on the device (verified: zero
  AsyncStorage/SecureStore ESPN entries; the pair lives only in module
  memory via `espnConnectBus` in flight).
- **No cookie-clear on FTF sign-out** — redundant; `EspnConnectScreen`
  clears on every mount and nothing else reads the jar (plan §F4).
- **No new column for the user's own SWID** — the live read at verify time
  suffices; revisit when the auth epic's `linked_sources` lands (plan §F4;
  the "do not widen" guard comment above the table agrees,
  `database.py:1500-1519`).
- **Clear-on-mount, verify-before-store, and DELETE disconnect** — already
  shipped in v1.13.2; untouched.

## 7. Test plan (per D-056 — no Maestro, no simulator)

### 7.1 Backend pytest (mocked ESPN transport) — each with a named sabotage

Every test lands with a **named sabotage**: a one-line deliberate mutation,
applied and reverted during development, that must flip the test red —
proving the test is non-vacuous. The sabotage name goes in the test's
docstring.

| # | Test | Asserts | Named sabotage (must fail the test) |
|---|---|---|---|
| T1 | `test_verify_wrong_swid_cookie_league` | Valid pair, SWID ≠ bound team's `owner_swid`, cookie league → 403, `error: espn_bad_credentials`, `reason: wrong_account`, DB row absent/unstamped | `SAB-skip-membership`: comment out the R1 assertion on the strong-oracle path |
| T2 | `test_verify_wrong_swid_public_league` | Same but only a PUBLIC linked league — membership read runs anyway → 403 `wrong_account` (the §2 gap case) | `SAB-public-skip`: gate the membership read on `espn_auth == 'cookie'` |
| T2b | `test_verify_two_league_mixed_verdict` | Two bound leagues, pair matches league 1's bound team but conclusively mismatches league 2's → 403 `wrong_account` (R1 precedence: any mismatch rejects) | `SAB-first-league-wins`: return accept after the first league's verdict |
| T3 | `test_verify_correct_swid_each_oracle` | Matching SWID via strong oracle and via weak+membership → stored, `verified_at` stamped, 200 | `SAB-invert-compare`: invert the SWID equality |
| T4 | `test_verify_ownerless_team_inconclusive` | Bound team has no/empty `owner_swid` → accept (R5), stored | `SAB-reject-ownerless`: treat missing `owner_swid` as mismatch |
| T5 | `test_verify_no_linked_league_unchanged` | No league rows → weak-oracle verdict stands, no membership fetch attempted | `SAB-force-fetch`: unconditionally require a league read |
| T6 | `test_verify_membership_read_outage` | Membership `fetch_league` raises transport error → 502 `espn_unavailable`, nothing stored (R6) | `SAB-outage-as-bad`: map the exception to verdict `bad` |
| T7 | `test_link_public_league_no_stamp` | Import path, pasted cookies + PUBLIC league, no mismatch, verify says `bad` → **import succeeds 200**, pair NOT stored, `credential_stored: false` + `credential_reason: "unverified"` in the response; verify `unavailable` → same with `"unavailable"` (R4 revised) | `SAB-always-stamp`: restore the unconditional stamp |
| T8 | `test_link_chosen_team_swid_mismatch` | Import with `team_id` whose `owner_swid` ≠ pasted SWID → 403 `wrong_account`, nothing persisted (R3) | `SAB-skip-link-check`: bypass the link-path assertion |
| T8b | `test_link_stored_cookie_fallback_mismatch` | Wrong pair stored earlier under a vacuous accept (no league); user then links a PUBLIC league picking a team via the stored-cookie fallback (`pasted_cookie=False`) → 403 `wrong_account`, nothing imported, **stored row's `verified_at` nulled** (B3's store-then-link hole) | `SAB-pasted-only`: gate the R3 assertion on `pasted_cookie` |
| T8c | `test_import_resync_swid_mismatch` | `espn_import` re-sync where stored SWID ≠ bound team's `owner_swid` → 403 `wrong_account`, stamp nulled (R3b) | `SAB-skip-resync-check`: bypass the re-sync assertion |
| T9 | `test_migration_nulls_prerelease` | All stamps `< RELEASE_CUTOFF` → NULL regardless of vintage (fixtures: pre-`2fa1ff2`-style born-NULL row untouched, dishonest-window stamp nulled, post-`7dfcd16` stamp still `< cutoff` nulled); post-cutoff stamp untouched; boundary fixture at the exact cutoff string; re-run is a no-op (NULL fails `<`); `GET` reports `connected: false` for nulled rows (R10) | `SAB-invert-cutoff`: flip `<` to `>=` |
| T10 | `test_403_shape_additive` | Wrong-account 403 body carries `error` + `message` + `reason`; plain rejection carries no `reason` (R2) | `SAB-rename-code`: change `error` to `espn_wrong_account` |

T10's sabotage doubles as the compatibility proof: `espnCredentialsRejected`
semantics survive only because the wire code is untouched.

### 7.2 Structural checks (`check-*.js` / grep-provable)

- `EspnConnectScreen` renders a distinct wrong-account string when
  `reason === 'wrong_account'` (R7) — assert the string/testID exists and is
  reachable from the `storeFail` branch — and the R8 typed-`reason` helper
  in `mobile/src/api/espn.ts` exists and narrows the optional field
  (review N5).
- `EspnLinkSheet`'s link-path rejection surface holds (review N1): the 403
  `espn_bad_credentials` response is NOT routed into the
  `isEspnAuthRequired` branch and the server `message` reaches the
  `espn-link.error` element — assert branch order / condition strings.
- No new device-side persistence of `espn_s2`/`SWID` introduced (grep:
  AsyncStorage/SecureStore in `mobile/src` × espn — must stay empty).
- `espn_connect_store_rejected` is emitted from the `storePair` failure path
  with a `reason` property (R11).
- `testid-lint` stays green (CI).

### 7.3 Operator TestFlight checklist (runtime proof — two-account switch, one physical device)

1. **Post-deploy first launch (before anything else):** if ESPN showed
   *connected* before the update (any vintage — the migration evicts every
   pre-release stamp), confirm first launch now shows *not connected*. That
   is the residue eviction (R10) working. If you were already disconnected
   pre-update, this step is vacuous — note it and move on.
2. Settings → Disconnect ESPN (clears any residue) → status shows *not
   connected*.
3. Sign in to ESPN in-app as **Account A (yours, in the league)** →
   connected; my-leagues picker lists *your* leagues; send pre-flight
   passes.
4. Disconnect. Sign in as **Account B (the other person, not in your
   league)** → expect the **wrong-account rejection with the new copy**
   ("…the ESPN account that owns your team"); status remains *not
   connected*; re-open Settings to confirm nothing was stored.
5. **Passive-harvest repro (the original #321 shape — review N5):** after
   step 4's B sign-in, back out of ESPN Connect **without** disconnecting
   anything, kill and relaunch the app, open ESPN Connect again → the login
   page must be genuinely signed out and **nothing auto-captured** in the
   first seconds (no store attempt, no rejection banner from a phantom
   capture) — the stale-jar harvest must be impossible, not just survivable.
6. Re-sign-in as Account A → connected again; propose a test trade to prove
   end-to-end.
7. **Account-keying spot check (blast-radius verdict, runtime proof):** sign
   in to a **second FTF account** on the same device → its ESPN status must
   be independent (*not connected*), untouched by Account A's link.

## 8. Citation verification record

Every file:line claim in `plan.md` was independently re-read at `d3fe3ac`
by this author. **All verified**; none failed. Ranges accurate to ±3 lines
in four places (noted inline above where it matters): the wrong-account
message body sits at `server.py:20155-20161` (plan said 20158-20164),
`_espn_reconnect_nudge` is defined at 16743 (plan's §F3 said 16746), the
league-link stamp block spans 20256-20272 (plan said 20262-20272), and the
weak-oracle zero-false-reject prose sits at 19945-19951 (plan said
19948-19954). No substantive discrepancies. The public-league stamp gap the
plan asserts is independently confirmed by the existing "Known residual
(2026-08-12)" admission in `docs/api-reference.md` (line 550 @ d3fe3ac).

**Round-1 correction (B1):** the original PRD carried the plan's cutoff
`2026-08-12T20:00:00+00:00` as "deploy time of `7dfcd16`" **without
verifying it** — the one claim in v1 taken on faith, and it was wrong in
the unsafe direction. Verified this round from git: `2fa1ff2` (introduces
`espn_credentials.verified_at`; the earlier `920a638` hit is
`users.verified_at`) committed 2026-08-12T04:25:58Z; `7dfcd16` committed
2026-08-13T02:27:03Z. R10 is respec'd accordingly.

**Round-1 additions, all verified at `d3fe3ac`:** stored-cookie fallback
sets `pasted_cookie=False` (`server.py:20206-20216`); `espn_import` re-sync
has teams + `espn_my_team_id` in hand (`server.py:20462-20470`); ESPN write
authored via `member_swid` context (`server.py:23545` region); `ApiError`
carries the server `message` (`mobile/src/api/client.ts:552-553`);
`EspnLinkSheet` renders it under `espn-link.error` after the
`isEspnAuthRequired` branch (`EspnLinkSheet.tsx:277, 287, 314, 324, 528,
549`); web inbox type allowlist and icon map (`web/js/app.js:4895`,
`4716`); `load_espn_leagues_for_user` pins no ordering
(`backend/database.py:10606`).

## 9. Security framing

Defensive analysis of FTF's own auth handling only. No exploit tooling; the
TestFlight checklist uses two consenting accounts the operator already
controls, on the operator's own device.
