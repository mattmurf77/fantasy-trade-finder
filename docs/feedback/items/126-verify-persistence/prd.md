# #126 — PRD: durable verification without weakening the gate

*Author agent (Phase 1, G2 fast-track-bug), 2026-07-12. Input: [plan.md](plan.md). Branch `trade-engine-v2`. This PRD is the build contract — no code ships with this doc.*

*Round 3: Planner round-2 review incorporated ([reconciliation-log.md §"Author round 3"](reconciliation-log.md)) — blockers B-1 (closed outcome rule, R-2.4) and B-2 (revocation pre-check, R-2.2) resolved; non-blocking N-1/N-2/N-3/N-5/N-6/N-7 incorporated, N-4 rejected with reasons in the log.*

> **Operator directive:** fix the persistence, don't weaken the gate.

---

## 0. Blocking finding — why this PRD deviates from plan §2a

Every code citation in the plan checked out (see [reconciliation-log.md](reconciliation-log.md) appendix) **except the one that carries the security argument**. Plan §2b claims:

> "A genuine squatter has no stored credential under the victim's user_id (storing one requires the claim-match + oracle at link time), so auto-verify gives them nothing."

This is false. `_maybe_autoverify(sess)` as specced does `get_sleeper_credential(sess["user_id"])` — and that lookup is keyed **by user_id alone** ([database.py:5776](../../../../backend/database.py)). A squatter's session *shares the victim's user_id* (that is what squatting is), so step 2 of the plan's proof chain retrieves the **victim's own live token**, step 4's claim re-check trivially passes (it is the victim's token matching the victim's user_id), and step 5's oracle passes (the token is genuinely live). Nothing in the chain proves anything about **who holds the session** — session mint requires only a public username (`POST /api/extension/auth`, [server.py:8892-8899](../../../../backend/server.py); `POST /api/session/init` likewise carries no proof).

Consequences of shipping the plan as written, for every user with a stored credential (≈ every verified Sleeper-keyed user, since `/api/sleeper/link` stores on success, [server.py:5063-5072](../../../../backend/server.py)):

1. **Write gate** ([server.py:1274-1278](../../../../backend/server.py)) — reopened to any username-knower. This is exactly the #102 hole P1 closed.
2. **Read gate** ([server.py:1345-1349](../../../../backend/server.py)) — P2.5 privacy reopened.
3. **`POST /api/trades/propose`** ([server.py:5134-5137](../../../../backend/server.py)) — a username-only attacker gets a verified session **and** the route pulls the same stored credential ([server.py:5149-5153](../../../../backend/server.py)) → real trade proposals sent from the victim's Sleeper account. **Strictly worse than pre-P1**, where propose required an in-session capture the attacker couldn't perform.

The root error: a **server-stored** credential proves that *someone once* controlled the account — it can never prove the *current session holder* does. Any design where the server self-serves verification from its own credential store converts that store into an ambient grant.

**Corrected principle (R-0, the load-bearing invariant):** verification is granted only when the **client presents** the Sleeper credential in the request, exactly as `/api/sleeper/link` already requires. The persistence fix therefore moves to the client: persist the captured JWT in the device Keychain and **silently replay the existing verification route** on fresh sessions. Same proof predicate, byte-identical server behavior, zero new backend attack surface — and the friction (`#126`'s literal complaint) disappears because the friction was never the proof, it was the WebView capture.

This also resolves the plan's own risk #4 ("widens *when* verification is granted, not *what* grants it") in the only honest way: the plan's design **did** widen what grants it.

---

## 1. Requirements

### R-0 — Server verification invariant (unchanged, now codified)

A server session gains `sess["verified"]` only via a request that carries proof inline: the Sleeper-JWT capture route (`POST /api/sleeper/link`: claim-match [server.py:5040-5043] + live oracle [server.py:5051-5061] → stamp [server.py:5074-5077]) or provider identity-token auth (`/api/auth/apple|google`, [server.py:9643-9651]). The server MUST NOT grant verification from `sleeper_credentials` (or any server-held secret) absent that client-presented proof. **No backend app-code change is required or permitted by this PRD** (backend/tests only; §4).

### R-1 — Persist the captured Sleeper JWT client-side (mobile)

- **Where:** `mobile/src/screens/SleeperConnectScreen.tsx` `onMessage` success path (the `linkSleeperToken(payload.token)` call at line 68 resolving with HTTP 200).
- **What:** store `{ user_id, token }` in **expo-secure-store** (already a dependency; the session token lives there today, [client.ts:72-87](../../../../mobile/src/api/client.ts)) under a new key (suggested `SECURE_SLEEPER_JWT_KEY = 'sleeper.link.jwt'`), where `user_id` is the signed-in FTF user. Store on any 200 (a 200 implies the claim matched the session user — mismatches 403 before storing server-side); `res.verified` may still be false (inconclusive oracle) and the token remains worth keeping for later replay.
- **Storage helpers** live in `mobile/src/api/sendInSleeper.ts` (it already owns the link API surface): `persistSleeperToken(userId, token)`, `getPersistedSleeperToken(): Promise<{user_id, token} | null>`, `clearPersistedSleeperToken()`.
- **Never** AsyncStorage, never logged, never sent anywhere except `POST /api/sleeper/link` to our own backend (which it already traverses today at capture time). Keychain survives app updates and (on iOS, in practice) reinstalls — covering both the #126 report ("download a new app version") and the fresh-install case.

### R-2 — Silent replay at session establishment (the corrected "helper contract")

New client helper `maybeReplaySleeperVerification(userId: string): Promise<'verified' | 'rejected' | 'inconclusive' | 'none'>` in `mobile/src/api/sendInSleeper.ts`:

1. **Bail fast (no I/O beyond Keychain read):** stored record absent, or `stored.user_id !== userId` → `'none'`. (Optionally decode `exp` locally: past-expiry is the same condition as R-2.4's 400 `token_expired` row, determined without the network — same `'rejected'` + delete. Not a fifth delete path. The server enforces regardless via `is_expired`.)
2. **Revocation pre-check (round-3 B-2; orchestrator arbitration: pre-check over recorded-limitation):** `getSleeperLinkStatus()` — the existing `GET /api/sleeper/link` ([sendInSleeper.ts:35-37]; session-scoped, not read-gated, cheap DB read):
   - `connected: false` → **skip the replay AND delete the Keychain copy**; return `'rejected'`. Rationale: `POST /api/sleeper/link` stores the credential before stamping verification ([server.py:5063-5072]) — replay and re-link are inseparable — so without this check, Disconnect on device A (server credential deleted) would be silently resurrected by device B's next background replay, re-arming `/api/trades/propose` against the user's explicit revocation. Revocation stickiness is non-negotiable. This never blocks the #126 fix: the server credential survives client reinstalls by construction, so a user who did *not* disconnect always pre-checks `connected: true`.
   - `connected: true` → proceed to step 3. (An `expired: true` flag describes the *server's* copy and does not short-circuit — the local token may differ; step 4's closed rule handles every replay outcome.)
   - **Any pre-check failure** — 404 `feature_disabled`, 401, network/timeout, anything else → skip the replay, **retain** the copy, return `'inconclusive'`. Never POST the token without a confirmed live server-side link.
3. **Replay the proof:** `linkSleeperToken(stored.token)` — the existing hard-verified route. The oracle bound is the server's 15 s HTTP timeout ([sleeper_write.py:40](../../../../backend/sleeper_write.py), applied at [sleeper_write.py:300]); the client call is additionally bounded by `client.ts`'s 15 s default request deadline (`DEFAULT_TIMEOUT_MS`; `/api/sleeper/link` is not in `SLOW_POST_PATHS`). No new timeout plumbing (the plan's optional `_post_graphql` timeout param is dropped along with the server helper).
4. **Outcomes — CLOSED RULE (round-3 B-1).** The Keychain copy is deleted on **exactly four** conditions and no others. Every outcome not in the delete set — *named below or not, known today or introduced later* — retains the copy and returns `'inconclusive'`:

   | Outcome | Return | Keychain copy |
   |---|---|---|
   | Pre-check `connected: false` (step 2) | `'rejected'` | **delete** |
   | 400 `token_expired` | `'rejected'` | **delete** |
   | 403 `token_rejected` | `'rejected'` | **delete** |
   | 403 `token_user_mismatch` | `'rejected'` | **delete** |
   | 200 `verified: true` | `'verified'` | retain |
   | 200 `verified: false` (oracle inconclusive server-side) | `'inconclusive'` | retain |
   | 404 `feature_disabled` (whole route is flag-gated, [server.py:5016-5017]) | `'inconclusive'` | retain |
   | 401 (session missing/evicted mid-flight; `client.ts:318-323` clears the *session* token on it — never the JWT copy) | `'inconclusive'` | retain |
   | 503 `sleeper_unconfigured`, 500 `store_failed`, any other 4xx/5xx | `'inconclusive'` | retain |
   | Network failure / timeout / unparseable response | `'inconclusive'` | retain |

   Implementation shape: match the three definitive error codes (plus the pre-check branch) **explicitly**; the `default`/catch-all branch MUST be retain-and-`'inconclusive'`. Deleting from a catch-all branch is a build error. The delete set is definitive because the server refuses rejected tokens before storing ([server.py:5033-5034, 5055-5058]) and a rejected 365-day token cannot heal; everything else is transport/config/flag noise where deletion would destroy the only proof copy over a transient condition. (There is no mobile unit-test harness — this table is the contract.)
5. **Single-flight:** a module-level in-flight promise; concurrent callers await (or race against — see call sites) the same replay. A `'rejected'` outcome is terminal (the delete is the memo). `'inconclusive'` retries naturally on the next session establishment (no timer needed — establishment events are rare).
6. Failures are silent (no toast, no thrown error to the caller's happy path). One `console`/Sentry-breadcrumb-safe log line **without the token**.

**Call sites — one awaited choke point plus one warm-up trigger:**

- **Primary (awaited): `sessionInit()`** in `mobile/src/api/auth.ts` (~line 199-220), after `setSessionToken(res.token)` and **before** mirroring `res.verification` into `useSession`:
  - If `res.verification && !res.verification.session_verified`, race the (single-flight) replay against a **4 s cap** (round-3 N-1): `Promise.race([maybeReplaySleeperVerification(body.user_id), sleep(4000)])`.
    - `'verified'` within the cap → mirror `{ session_verified: true, user_verified: true, verified_via: 'sleeper', enforced: res.verification.enforced }` (round-3 N-3 — the same shape as SleeperConnectScreen's own success mirror, [SleeperConnectScreen.tsx:76-81]; covers the linked-while-oracle-inconclusive user whose persisted marker was absent at init). The live server session was stamped by the replay; no re-init needed.
    - Cap elapsed, or any other outcome → mirror the server's values unchanged (banner shows when applicable — now truthfully, see R-6). The in-flight replay keeps running; on a late `'verified'` it **late-applies** the same mirror, guarded: only if the store's `verification` still shows `session_verified: false` for the same signed-in user (never clobber a newer state).
  - This hook covers **every** establishment path, because they all funnel through `sessionInit()`: SignIn → LeaguePicker (`initLeagueSession`), app-relaunch restore (`useSession.revalidateSession`, [useSession.ts:229]), in-app league switch (`switchLeague`), and ESPN-league init (`buildEspnSessionInitBody` path). `acct_*` sessions are verified at mint (server-side) so the `session_verified === false` guard skips them; demo and `test_user_fp_*` users never captured a token → `'none'`.
  - **Ordering guarantee (no banner flash):** `setVerification` is called exactly once per init (plus at most one guarded late-apply), *after* the race resolves. Latency cost: one pre-check + one oracle RTT (~200-500 ms each typical) appended to an already 5-10 s cold `session_init`, with added wait hard-capped at 4 s — and only paid by users holding a stored token with an unverified session.
- **Warm-up (fire-and-forget, round-3 N-2):** immediately after `signIn()`'s `setSessionToken` ([auth.ts:26-35]), call `maybeReplaySleeperVerification(res.user_id)` **without awaiting**. Safe: the session already exists (extension/auth just minted it), and verified state survives the same-user re-init that `sessionInit` performs later ([server.py:7279-7285]). Effect: the replay usually completes during league pick, shrinking the INIT-08 window (user can reach Main before background `sessionInit` finishes) where gated reads would 403, and the primary call site's race then resolves instantly off the single-flight promise. No query invalidation on `'verified'` is required (rejected — see reconciliation log, Author round 3).

### R-3 — `session_init` `verification` response field: UNCHANGED

Response shape and semantics stay exactly as shipped ([server.py:7578-7583]): `session_verified` reports the server session's state at init time; same-user carryover and re-point clearing ([server.py:7277-7291]) untouched. The client patches its *mirror* to `session_verified: true` only after a successful replay has actually stamped the live session (R-2). Prefer-none achieved: **no response-shape changes anywhere in this PRD.**

### R-4 — Dead-credential hygiene (resolves plan Q1, recast)

The plan's Q1 asked whether the *server* should delete `sleeper_credentials` on oracle-reject inside the (now dropped) server helper. Recast client-side with the same answer — **delete on definitive rejection**:

- Client deletes its Keychain copy **only** per R-2.4's closed rule: the three definitive rejection codes (`token_expired` / `token_rejected` / `token_user_mismatch`) plus the R-2.2 pre-check's `connected: false`. Justification mirrors the plan's: `SleeperAuthError` is raised server-side only on Sleeper's explicit 401/403 ([sleeper_write.py:307-308]) or an auth-worded GraphQL error ([sleeper_write.py:319-325]), verified 2026-07-08 to fire before query execution; a rejected 365-day token cannot heal. Matches propose's expired-token deletion semantics ([server.py:5156-5158]) and the `SleeperAuthError` docstring ("Caller should drop the stored token", [sleeper_write.py:80-82]).
- Client retains the copy on every other outcome (inconclusive ≠ dead) — retry works on the next establishment.
- Server-side `sleeper_credentials` handling is **unchanged** (propose already deletes expired creds; further server hygiene is out of scope).

### R-5 — Disconnect clears the local copy

Wherever `unlinkSleeper()` ([sendInSleeper.ts:45-47]) is invoked (Settings account section), also call `clearPersistedSleeperToken()`. Cross-device: other devices' copies are neutralized by the R-2.2 pre-check (their next replay sees `connected: false`, self-deletes, and never re-stores) — disconnect stays sticky everywhere.

The stored copy is otherwise retained across sign-out (it is the device owner's own credential, keyed to `user_id`, and replay only fires on a matching sign-in). **Shared-device note (round-3 N-5, deliberate):** retaining across sign-out means anyone who signs in as that username *on that physical device* gets auto-verified. That is the same trust boundary as the original capture — device possession — not a widening of it; recorded here so it is a decision, not an accident.

### R-6 — Banner copy fix (`VerifyAccountBanner.tsx:44-45`)

Post-fix, the `user_verified && !session_verified` banner appears only when replay **couldn't** succeed: no stored token on this device (never captured here / cleared), or the token is dead/expired, or Sleeper was unreachable. Replace:

> ~~"This account was verified on another device. Reconnect Sleeper here to keep editing your ranks."~~

with:

> **"We couldn't confirm your Sleeper login on this device. Reconnect to keep editing your ranks."**

Accurate in all three residual cases, drops the factually-wrong "another device" claim (#126's report), Chalkline voice (plain, dry, no exclamation, no emoji). The unverified-no-controller line (`VerifyAccountBanner.tsx:46`) and all display gating logic (lines 34-42) are unchanged.

### R-7 — ESPN sheet error mapping (`EspnLinkSheet.tsx`)

Both catch blocks currently print `e?.message`, which for the write gate's 403 is the raw code `verification_required` ([client.ts:325] falls back to `body.error`; the backend sends no `message` on this error). In `fetchPreview` (lines 95-99) **and** `pickTeam` (lines 118-122), branch first:

```ts
if (e instanceof ApiError && e.isVerificationRequired) {
  setError('Verify your account to link a league.');
}
```

(`ApiError.isVerificationRequired` exists, [client.ts:128-135]; copy pattern matches `utils/verification.ts`'s `VERIFY_READS_COPY`.) The central `_onVerificationRequired` listener still fires and raises the banner — unchanged.

### R-8 — Explicitly UNCHANGED

- Gate decision matrices, grace-flag semantics (`auth.enforce_verified_writes`), first-verified-controller-wins for genuinely unverified squatters, the read gate's no-grace rule — all byte-identical.
- Hard-verified routes (`/api/sleeper/link`, `/api/trades/propose`, `/api/account/reset-rankings`).
- `verify_token_live` and `_post_graphql` (no timeout param — dropped with the server helper).
- `sleeper_credentials` server-side lifecycle; `accounts.mark_user_verified` (see reconciliation Q4).
- The SleeperConnect WebView capture — still the path for first-ever verification, new-device-without-Keychain, and dead-token recovery. The replay is a *repeat* of its output, not a new proof class.
- `session_init` / `sleeper/link` response shapes.

**Recorded coupling (round-3 B-1, pre-existing but now load-bearing):** the entire `/api/sleeper/link` route — GET pre-check and POST replay alike — 404s while `trade.send_in_sleeper` is off ([server.py:5016-5017]), so verification *durability* inherits that flag. This was already true of first capture; the replay extends it to re-verification. If the kill switch is ever flipped, replays go `'inconclusive'` (copies retained, R-2.4), banners reappear, and manual capture 404s too — flag owners should know verification recovery rides this flag.

### R-9 — Non-goals (corrections to plan §3 "for free" claims)

- **Web + extension P2.5 known limitation is NOT closed** — those clients have no capture flow and hence no credential to replay. The plan's claim that server-side auto-verify would fix them "for free" fell with the server helper. Web verification remains the top P3 item.
- Server-side session persistence (P3), Android uninstall persistence (Keystore is wiped on uninstall; updates are fine), retrying replay from the 403-listener mid-session (V1 replays at establishment only; the banner's Verify button is the in-session recovery).
- **Migration note:** existing users' tokens were never persisted client-side, so each verified user re-captures **once** after this ships (the operator will see the banner one final time), then never again.

---

## 2. Files touched (all mobile + backend tests + docs; single owner: #126 Author)

| File | Change |
|---|---|
| `mobile/src/api/sendInSleeper.ts` | Keychain persist/get/clear helpers + `maybeReplaySleeperVerification` (single-flight, revocation pre-check, closed outcome rule) |
| `mobile/src/api/auth.ts` | `sessionInit()` 4s-capped replay race before verification mirror + fire-and-forget warm-up after `signIn()` |
| `mobile/src/screens/SleeperConnectScreen.tsx` | persist token on 200 in `onMessage` |
| `mobile/src/components/VerifyAccountBanner.tsx` | copy only (R-6) |
| `mobile/src/components/EspnLinkSheet.tsx` | error mapping in two catches (R-7) |
| Settings disconnect call site of `unlinkSleeper()` | `clearPersistedSleeperToken()` (R-5) |
| `backend/tests/test_verified_sessions.py` | sequence regression pins (§4) — **no backend app code** |
| Docs: `docs/plans/account-auth-plan-2026-07-11.md` status appendix; `mobile/src/components/CLAUDE.md` registry (banner copy note); `docs/runbook.md` only if an operational note is warranted | XS |
| Privacy (round-3 N-6, no gate): flag device-side storage of the Sleeper credential to whoever owns the privacy disclosure docs — the server-side storage disclosure likely already covers it | — |

## 3. Success criteria & guardrails

**Success criteria**

1. Operator scenario: verified controller + token in Keychain + fresh session → `POST /api/espn/link` succeeds with zero manual steps; no banner shown.
2. Every backend gate/verification test passes **unmodified** (zero backend behavioral change).
3. Squatter regression: a session minted with only the victim's username — no Keychain credential — still 403s all gated reads and writes and cannot propose. (The corrected design makes this structural: the server never self-serves proof.)
4. **Revocation stickiness:** after Disconnect on any device, no other device's background replay re-stores the credential or re-arms propose (R-2.2 pre-check); the only path back is a deliberate SleeperConnect capture.
5. Banner, when shown, is truthful (R-6); ESPN sheet never surfaces a raw error code for the gate 403 (R-7).

**Guardrails**

- Never verify on claim-match alone — the live oracle stays mandatory (unchanged server predicate).
- **The server never grants verification from server-stored credentials** (R-0) — the review gate for any future iteration of this feature.
- **Replay only against a confirmed live link** (R-2.2): `connected: true` on the pre-check is a precondition for POSTing the token; the Keychain copy is deleted only per R-2.4's closed rule, never from a catch-all branch.
- Oracle bound: 15 s server HTTP timeout + 15 s client request deadline; replay is fire-once-per-establishment, single-flight, non-fatal on any failure; added sign-in wait capped at 4 s (late-apply covers the tail).
- `session_init` server latency budget: **unchanged** (no server work added). Client sign-in adds ~2 short RTTs (pre-check + oracle, ~200-500 ms each typical) only for token-holders with unverified sessions.
- The JWT never touches AsyncStorage, logs, Sentry, or any endpoint other than our `/api/sleeper/link`.
- SecureStore value stays tiny (one JSON object, well under the ~2 KB iOS advisory).

## 4. Test plan

**pytest — `backend/tests/test_verified_sessions.py`** (existing fixtures/oracle stubs reused; these pin the *sequence* the client will drive — the server code is unchanged):

1. **Operator repro end-to-end:** user with `users.verified_via='sleeper'` + fresh injected session → `POST /api/sleeper/link` with a valid claim-matched token (oracle stubbed OK) → 200 `verified: true`; then a representative gated write (`POST /api/ranking-method`) → 200, a P2.5-gated read → 200, and `POST /api/espn/link` (flag on, `_espn.fetch_league` mocked) → 200 preview, never `verification_required`.
2. **session_init reports verified after replay:** same setup, then `POST /api/session/init` (init_client fixture) → `verification.session_verified: true`.
3. **Dead token:** replay with oracle → `SleeperAuthError` → 403 `token_rejected`, session stays unverified, nothing stored, gated write still 403 (gate not weakened), `verification` reports `user_verified: true / session_verified: false` (the banner state).
4. **Transport failure:** replay with oracle → `SleeperWriteError(kind='network')` → 200 `connected: true, verified: false`; gated write 403 (controller exists); a second replay with the oracle healthy → verified (client-side retention is what enables this; server credential intact throughout).
5. **Squatter (no credential to present):** unverified session for a verified user_id issuing gated reads + writes → 403 both (pins existing behavior against this change; complements `test_first_verified_wins_across_live_sessions`).
6. **Expired token (round-3 N-7, pins B-1's `token_expired` delete trigger):** replay with a past-`exp` token → 400 `token_expired`, session stays unverified, nothing stored server-side (client contract: Keychain copy deleted per R-2.4).
7. **Revocation stickiness (round-3 B-2):** link + verify, then `DELETE /api/sleeper/link` → 200; `GET /api/sleeper/link` → `connected: false` (client contract: pre-check sees this, skips the replay, deletes the local copy — the server pin is the `connected: false` read the pre-check depends on).
8. Existing suites (`test_verified_sessions.py`, `test_verified_reads.py`, `test_sleeper_write_route.py`) pass without edits.

**Maestro / client-visible:** the observable win is the **absence** of the banner (and of ESPN-link 403s) on a fresh session when a valid token sits in Keychain. Simulator limits make this effectively untestable in CI: the capture needs a real Sleeper login (credentials can't be automated), and Keychain persistence across reinstall isn't exercisable in a Maestro flow. Coverage therefore = backend tests above + a **manual operator checkpoint**:

1. Install the build containing this fix; sign in; run SleeperConnect once (final manual capture — R-9 migration note).
2. Wait >4 h (session eviction) or redeploy the backend; relaunch the app and sign in / let revalidate run.
3. Confirm: no verify banner, Settings shows the account linked/verified, ESPN league link completes, Send-in-Sleeper does not degrade to the deep-link fallback.
4. Negative check: on a second device that never captured, confirm the banner still appears with the new copy (R-6) and ESPN link shows the new human copy (R-7).

A copy-only assertion (banner text, `main.verify-banner` testID already registered) can ride an existing smoke flow if one reaches the banner state; do not build a dedicated flow for it.
