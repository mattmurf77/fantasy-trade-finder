# #126 — Build status: durable verification without weakening the gate

*Build agent (G2 fast-track, mobile + backend tests), 2026-07-12. Spec: [prd.md](prd.md) (round-3 converged) + [reconciliation-log.md](reconciliation-log.md). Branch `trade-engine-v2`, uncommitted.*

## Summary

Mobile-only fix, **zero backend app-code changes** (R-0 honored). The captured Sleeper JWT is persisted to the device Keychain at capture time and silently replayed through the existing hard-verified `POST /api/sleeper/link` at every session establishment, behind the R-2.2 revocation pre-check and the R-2.4 closed outcome rule. Banner and ESPN-sheet copy corrected. Two pytest sequence pins added.

## Requirement → code map

| PRD req | Where | What |
|---|---|---|
| R-0 (server invariant) | — | No backend app code touched (`git diff` on `backend/server.py` etc. contains only other agents' pre-existing work; this build's backend diff is tests-only) |
| R-1 persist at capture | `mobile/src/screens/SleeperConnectScreen.tsx` (`onMessage` success path) | `persistSleeperToken(uid, payload.token)` on any 200, non-blocking; comment records the keep-even-if-unverified rationale |
| R-1 storage helpers | `mobile/src/api/sendInSleeper.ts` | `SECURE_SLEEPER_JWT_KEY = 'sleeper.link.jwt'`, single `{user_id, token}` slot via expo-secure-store; `persistSleeperToken` / `getPersistedSleeperToken` / `clearPersistedSleeperToken`. Never AsyncStorage; token never logged (log lines carry outcome only) |
| R-2 replay helper | `mobile/src/api/sendInSleeper.ts` `maybeReplaySleeperVerification()` | Bail-fast (absent / user mismatch → `'none'`; optional local `exp` decode omitted — PRD marks it optional, server enforces via `is_expired`); R-2.2 pre-check `getSleeperLinkStatus()` (`connected:false` → delete + `'rejected'`; any pre-check failure → retain + `'inconclusive'`); replay via `linkSleeperToken(stored.token)`; single-flight module-level in-flight promise keyed to user_id, cleared on settle |
| R-2.4 closed rule | same fn | Delete on **exactly four** conditions: pre-check `connected:false`, 400 `token_expired`, 403 `token_rejected`, 403 `token_user_mismatch` — matched explicitly. Catch-all (404/401/503/500/other/transport/unparseable) retains + `'inconclusive'`. Grep-proof below |
| R-2 primary call site (N-1) | `mobile/src/api/auth.ts` `sessionInit()` | Trigger: `res.verification && !verification.session_verified`. `Promise.race([replay, 4s cap])`; `'verified'` → full N-3 mirror shape (`session_verified: true, user_verified: true, verified_via: 'sleeper', enforced` from init response); timeout → mirror server values + guarded late-apply (only if store still shows `session_verified: false` **and** `state.user.user_id === body.user_id`); `setVerification` called exactly once per init after the race (+ at most one late-apply) — no banner flash. Covers all establishment paths (LeaguePicker, revalidateSession, switchLeague, ESPN init) since they all funnel through `sessionInit()` |
| R-2 warm-up (N-2) | `mobile/src/api/auth.ts` `signIn()` | Fire-and-forget `maybeReplaySleeperVerification(res.user_id)` immediately after `setSessionToken`; no query invalidation (rejected per log) |
| R-4 dead-credential hygiene | closed rule above | Delete only on the three definitive codes + pre-check; retain everything else |
| R-5 disconnect clears local copy | `mobile/src/api/sendInSleeper.ts` `unlinkSleeper()` | `clearPersistedSleeperToken()` after the DELETE succeeds. Note: `unlinkSleeper()` currently has **no call site** in `mobile/src` (grep-verified) — putting the clear inside the API fn guarantees R-5 for any future Settings call site without touching forbidden `SettingsScreen`. Copy retained across sign-out (N-5 decision recorded in PRD; `useSession.signOut` untouched) |
| R-6 banner copy | `mobile/src/components/VerifyAccountBanner.tsx` | `user_verified` branch → "We couldn't confirm your Sleeper login on this device. Reconnect to keep editing your ranks." Title, no-controller line, and all display gating unchanged |
| R-7 ESPN sheet mapping | `mobile/src/components/EspnLinkSheet.tsx` | Both catches (`fetchPreview` + `pickTeam`) branch first on `e instanceof ApiError && e.isVerificationRequired` → "Verify your account to link a league."; central listener untouched |
| §4 pytest pins 6+7 | `backend/tests/test_verified_sessions.py` | `test_link_expired_token_denied_before_oracle` (400 `token_expired`, oracle not called, unverified, nothing stored) + `test_link_delete_then_get_reports_disconnected` (link+verify → DELETE 200 → GET `connected:false` — the exact server read R-2.2 depends on). Pins 1–5 map onto pre-existing tests (dead-token, inconclusive-oracle, carryover, squatter/first-verified-wins, gate matrix) — left unmodified per §4.8 |

## Verification evidence

- **`cd mobile && npx tsc --noEmit`** — clean (no output).
- **`python3 -m pytest backend/tests/ -q`** — **558 passed** in 6.7 s (556 before this change; +2 = the new pins). Existing verified-sessions/reads/write-route suites pass unmodified.
- **Closed-rule grep-proof** — `grep -rn "clearPersistedSleeperToken()" mobile/src` (excluding the definition) yields exactly **3** call sites:
  1. `sendInSleeper.ts:52` — inside `unlinkSleeper()` (R-5 deliberate disconnect; not a replay outcome).
  2. `sendInSleeper.ts:151` — pre-check `connected: false` (R-2.4 condition 1).
  3. `sendInSleeper.ts:182` — inside the explicit three-code match `(400 token_expired) || (403 token_rejected || token_user_mismatch)` (R-2.4 conditions 2–4).
  The replay's catch-all branch returns `'inconclusive'` with **no** delete; the outer safety `.catch` in `maybeReplaySleeperVerification` likewise maps to `'inconclusive'` only.
- **Forbidden-path check** — `git diff` for this build touches only: `sendInSleeper.ts`, `auth.ts`, `SleeperConnectScreen.tsx`, `VerifyAccountBanner.tsx`, `EspnLinkSheet.tsx`, `test_verified_sessions.py`, this file. No backend app code, no `mobile/ios/**`, no SettingsScreen/SignInScreen, no `useSession.ts` change needed (mirror shape already existed).
- **Maestro** — none built, per the PRD (§4: manual operator checkpoint is the client-visible coverage; no new testIDs introduced).

## Manual operator checkpoint (from PRD §4 — still owed post-ship)

1. Install this build; sign in; run SleeperConnect once (final manual capture — migration note R-9).
2. After session eviction (>4 h) or a backend redeploy, relaunch: expect **no banner**, ESPN link works, Send-in-Sleeper doesn't degrade.
3. Negative: a second device that never captured still shows the banner with the new copy.

## Deviations

None from the PRD's normative requirements. Two implementation notes:

- R-2.1's *optional* local `exp` decode was omitted (PRD: "Optionally…"; simplicity-first — the server's `is_expired` 400 maps to the same delete+`'rejected'` row, costing one round-trip only in the already-rare expired case).
- R-5's "wherever `unlinkSleeper()` is invoked" resolved to the API function itself because no call site exists yet (see map above).

Out-of-scope rows from the PRD files table left to the orchestrator (not in this agent's owned paths): `docs/plans/account-auth-plan-2026-07-11.md` status appendix; privacy-disclosure flag (N-6, no gate); no runbook note warranted.
