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
  - **An unverified or demo session** (the ones session/init refuses, 403) gets the constant `{session_verified: false, user_verified: false, verified_via: null, enforced}`, before any lookup (release-lead #524 QA P1). Otherwise ping would tell anyone who can name a user_id whether that account exists and which provider proved it (legal R28.9 row 4 / R28.14).
- **Client:** `api/auth.ts` `refreshVerification()` pings, and records the answer only when it's for the user it asked for and that user is still signed in. It runs:
  - from `revalidateSession`'s sentinel branch (every launch and foreground for an account-only session), not awaited, since callers chain foreground work on `revalidateSession` (QA P3-2);
  - right after the account-only Apple sign-in pins the sentinel.
- **Client, also from QA:** `setUser` resets `verification` to null whenever the user_id changes, so after an expiry and another user's sign-in the previous user's answer never carries over. This predates the change.

## 1. Analytics scope
- [x] **(c) WAIVED:** no events. This only fills a state field other sessions already get.

## 2. Schema & flag scope
- Tables, flags, env: none.
- **API:** `GET /api/session/ping` gains an additive response field (`docs/api-reference.md`). No existing caller in mobile or web used ping before this, so nothing changes for them.
- **Rollback:** revert the PR. #495's session-field fallback (`user.account_only` + `user.verified_via`) still keeps Restore for Apple-first users.

## 3. Evidence scope
- [x] **Backend:** `backend/tests/test_session_ping_verification.py`, 24 tests:
  - an account-only Apple session reads verified;
  - an unverified session reads unverified;
  - the squatter case (an unverified session for a verified user_id) reads the constant, with no lookup;
  - a demo session reads the constant even if stamped verified;
  - a verified session reads the user row's provider, not its own stamp;
  - a session restored after a restart reads verified;
  - a `verified_via` lookup failure never fails the ping;
  - no session is still a 401 without the field;
  - the exact top-level and `verification` key sets for 7 session types (account-only Apple, verified league, unverified Sleeper, squatter, ESPN/MFL entry claim, extension, demo);
  - 0 SQL for an anonymous or unknown-token ping and for unverified, squatter, entry and demo pings, plus a positive control showing the counter sees a verified ping's lookup;
  - a foreign `user_id` query param or `X-User-Id` header is ignored, for a verified and an unverified session.
  - **Sabotage 11/11 red,** restored byte-identical:
    - round 1, re-run: the field dropped; the session stamp ignored; `user_verified` taken from the session instead of the user row; a lookup failure failing the ping;
    - after QA: the P1 fix reverted; demo sessions looked up; an extra top-level key; an extra key in the unverified answer; the query `user_id` answered; `X-User-Id` looked up; the 401 path probing the users table.
- [x] **Mobile guard:** `mobile/tests/check-account-only-verification.js` (`npm run test:account-only-verification`), 5 AST pins:
  1. `refreshVerification`: pings, records only for the same, still-signed-in user, and swallows a failure;
  2. `sessionPing`'s result type carries `verification`;
  3. the sentinel branch fires it without awaiting, then returns, before any `initializeLeagueSession`;
  4. the account-only sign-in calls it after pinning the sentinel;
  5. `setUser` resets `verification` to null when the user_id changes, in the same `set()` that stores the user, and leaves it alone for the same user.
  - **Sabotage:** 7/7 red in round 1, then 5/5 after QA, restored byte-identical. The 5: awaited again; no reset; the same-user branch wiping it too; a reset only when a previous user existed (misses the expiry case); the reset split into a second `set()`.
  - `check-win-now-recovery.js` still passes (useSession's `../api/auth` import was already allowed).
- [x] **Code-walk:**
  - every non-sentinel session still gets `verification` from session init, unchanged;
  - the read-gate 403 mirror is unchanged;
  - a ping failure (offline) leaves the state as it was, as `revalidateSession`'s own catch does;
  - the `setUser` reset can't wipe a fresh answer: every `verification` writer runs after `setUser` for its user. These are session init, `refreshVerification`, the Apple link in Settings, Account identity and the save-moment sheet, SleeperConnect, LeaguePicker's 403 mirror, and the read-gate mirror;
  - the link-Sleeper re-key (acct_ → Sleeper id) reads null until the league pick's session init answers. That's "render nothing while unknown", the strict rule.
- [x] **Manual TestFlight checklist** (operator, 11-06 build, with #495 in):
  1. Sign in with Apple as a new account with no league, and open Settings: the Subscription section shows (See plans + Restore), not the Verify row.
  2. Force-quit and reopen offline: the section still shows See plans + Restore, from #495's account-only fallback (`user.account_only` + `user.verified_via`) while the ping can't answer. Back online, it stays the same.
  3. Sign in with a Sleeper username without verifying: the Subscription section shows only the Verify row.
  4. As the account from step 1, link Sleeper in Settings and pick a league. Back in Settings, the Subscription section shows (See plans + Restore). This checks that the reset on the acct_ → Sleeper re-key fills back in.
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
