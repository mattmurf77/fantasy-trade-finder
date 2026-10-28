# Feature Scope — account-only sessions get `verification`

**Date:** 2026-10-28
**Entry point:** direct ask (head-eng → onboarding-eng 2026-10-28: "pull your verification root-cause fix forward to before 11-06"), from the #495 review. For the 11-06 binary.
**Builder:** onboarding-eng
**Operator sign-off on waivers:** none needed beyond §1 (c).

**The gap.** `useSession.verification` is written only from `/api/session/init`'s response (and from the read-gate 403 mirror). An account-only session (Apple-first, no league) pins the `NO_LEAGUE_ID` sentinel:
- `revalidateSession` returns early for it (`useSession.ts`);
- `initLeagueSession` throws for it (`auth.ts`).

So its `verification` stayed null for good. #495's Restore row couldn't be strict ("render nothing while unknown", head-eng's rule that Pro counts only on a verified session; legal R28.9) without hiding Restore from exactly the accounts App Review creates.

**The fix:**
- **Server:** `GET /api/session/ping` returns the same additive `verification` object session/init returns, built by `_session_verification(sess)` from the same sources: this session's own `verified` stamp and the user_id's stored verified_via.
  - An account-only session is minted verified (`_provider_auth_response` sets `payload["verified"] = True`), so it reads `session_verified: true`, `user_verified: true`, `verified_via: 'apple'|'google'`.
- **Client:** `api/auth.ts` `refreshVerification()` pings, and records the answer only when it's for the user it asked for and that user is still signed in. It runs:
  - from `revalidateSession`'s sentinel branch (every launch and foreground for an account-only session);
  - right after the account-only Apple sign-in pins the sentinel.

## 1. Analytics scope
- [x] **(c) WAIVED:** no events. This only fills a state field other sessions already get.

## 2. Schema & flag scope
- Tables, flags, env: none.
- **API:** `GET /api/session/ping` gains an additive response field (`docs/api-reference.md`). No existing caller in mobile or web used ping before this, so nothing changes for them.
- **Rollback:** revert the PR. #495's session-field fallback (`user.account_only` + `user.verified_via`) still keeps Restore for Apple-first users.

## 3. Evidence scope
- [x] **Backend:** `backend/tests/test_session_ping_verification.py`, 6 tests:
  - an account-only Apple session reads verified;
  - an unverified session reads unverified;
  - the squatter case (an unverified session for a verified user_id);
  - a session restored after a restart reads verified;
  - a `verified_via` lookup failure never fails the ping;
  - no session is still a 401 without the field.
  - With `test_persistent_sessions.py`: 21 passed. **Sabotage 4/4 red:** the field dropped; the session stamp ignored; `user_verified` taken from the session instead of the user row; a lookup failure failing the ping.
- [x] **Mobile guard:** `mobile/tests/check-account-only-verification.js` (`npm run test:account-only-verification`), 4 AST pins:
  1. `refreshVerification`: pings, records only for the same, still-signed-in user, and swallows a failure;
  2. `sessionPing`'s result type carries `verification`;
  3. the sentinel branch awaits it, then returns, before any `initializeLeagueSession`;
  4. the account-only sign-in calls it after pinning the sentinel.
  - **Sabotage 7/7 red,** restored byte-identical. `check-win-now-recovery.js` still passes (useSession's `../api/auth` import was already allowed).
- [x] **Code-walk:**
  - every non-sentinel session still gets `verification` from session init, unchanged;
  - the read-gate 403 mirror is unchanged;
  - a ping failure (offline) leaves the state as it was, as `revalidateSession`'s own catch does.
- [x] **Manual TestFlight checklist** (operator, 11-06 build, with #495 in):
  1. Sign in with Apple as a new account with no league, and open Settings: the Subscription section shows (See plans + Restore), not the Verify row.
  2. Force-quit and reopen offline: the section may be empty until you're back online. Online, it shows again.
  3. Sign in with a Sleeper username without verifying: the Subscription section shows only the Verify row.
- `testID`s: none.

## 4. Docs scope
| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | `GET /api/session/ping` row |
| `living-memory/LLD.md` | n/a | no convention shift; the field exists and gets one more source |
| `docs/architecture.md` / `living-memory/HLD.md` | n/a | no wiring change |
| `docs/cross-client-invariants.md` | n/a | the field's shape is session/init's, unchanged |
| `docs/glossary.md`, ADR | n/a | no new term or decision |

## 5. Ship gate declaration
- **CI:** `backend-tests`, `mobile-typecheck` (with the `check-*.js` loop), testid-lint and `web-structure` green.
- **Evidence:** a `living-memory/TEST_LEDGER.md` entry. **TestFlight:** §3's checklist.
- Express lane declared by the operator? No.
