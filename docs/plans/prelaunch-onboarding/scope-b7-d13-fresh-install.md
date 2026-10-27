# Feature Scope — B7: no D-13 policy notice right after agreeing

**Date:** 2026-10-27
**Entry point:** direct ask (head-eng → onboarding-eng 2026-10-27, from Product's pre-launch review B7; onboarding-pm §3, "a gap in my D-13 spec"). It amends #380 (D-13; spec `plans/launch-support-policy/scope-d13-policy-notice.md` on the launch-support-policy plan branch). Due in release-lead's queue by 11-03.
**Builder:** onboarding-eng
**Operator sign-off on waivers:** none needed beyond §1 (c).

**The gap.** #380 keys the policy notice to the release version, 1.22.0. `useWhatsNew` had no first-install check, so a brand-new install agreed to the policies on the sign-in screen ("By signing in you agree to the…") and was then told "We've updated our Privacy Policy and Terms of Use…".

**The fix.** `useSession.bootstrap` calls `markSeenAtSignedOutBoot()` when it restores **no signed-in user**. That covers a fresh install, a reinstall (AsyncStorage is wiped; the Keychain session token survives, so the token is deliberately NOT the signal) and a signed-out user. Each goes through the sign-in screen and agrees to the current policies.
- The call marks this release's entry seen in memory at once, and in storage.
- A signed-in user upgrading restores a user, so they still see the notice once, as D-13 requires.
- **Behaviour note for legal and release-lead:** a signed-out existing user also skips the notice, and gets the sign-in screen's "you agree" line with its links instead.

## 1. Analytics scope
- [x] **(c) WAIVED:** no new events. The tip's existing `tapAction('whats_new')` is unchanged. The change only stops the tip showing to people who just agreed.

## 2. Schema & flag scope
- Tables/columns: none. Flags: none (`ux.whats_new` still gates the tip; its value isn't changed here). Env / `model_config`: none.
- **Rollback:** revert the commit. The notice then shows on fresh installs again.

## 3. Evidence scope
- [x] **Structural guard:** `mobile/tests/check-whats-new.js` pin 8. It checks that:
  - `markSeenAtSignedOutBoot` writes the app version to the seen key and sets an in-memory mark, which the entry also checks;
  - its only caller is `useSession.bootstrap`, once, under `if (!user)`, after `user = JSON.parse(userRaw)`.

  Pins 1–7 are unchanged and pass. **Sabotage 7/7 red,** restored byte-identical:
  - the entry ignores the mark;
  - nothing is written to storage;
  - there's no in-memory mark;
  - it's marked on every boot;
  - it's keyed on the Keychain token;
  - it's called before the user is restored;
  - there's a second caller.
- [x] **Code-walk:**
  - `bootstrap` reads `SU_KEY` (`sleeper_user`) from AsyncStorage. Every signed-in state, including account-only, has a user there, and RootNav routes to sign-in without one.
  - The tip renders only on League (`LeagueScreen`), which needs a signed-in user. So on a signed-out boot the in-memory mark is set before the tip can mount.
- [x] **Manual TestFlight checklist (operator, 11-06 build, with `ux.whats_new` on):**
  1. Delete the app, reinstall, sign in and open League: no "We've updated…" tip.
  2. On a device signed in on the previous build, install the 11-06 build over it and open League: the tip shows once; tapping it opens Help & about.
  3. Sign out, quit, relaunch and sign in again: no tip.
- `testID`s: none.

## 4. Docs scope
| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route change |
| `living-memory/LLD.md` | n/a | no convention shift |
| `docs/architecture.md` / `living-memory/HLD.md` | n/a | no wiring change |
| `docs/cross-client-invariants.md` | n/a | mobile only |
| `docs/glossary.md` | n/a | no new term |
| ADR / `DECISIONS.md` | n/a | it implements Product's stated fix; the behaviour note is above |

## 5. Ship gate declaration
- **CI:** `mobile-typecheck` (with the `check-*.js` loop), testid-lint and `backend-tests` green on the pushed sha.
- **Evidence:** a `living-memory/TEST_LEDGER.md` entry. **TestFlight:** §3's checklist, run by the operator.
- Express lane declared by the operator? No.
