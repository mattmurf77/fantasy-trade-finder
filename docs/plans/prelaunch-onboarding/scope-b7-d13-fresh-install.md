# Feature Scope — B7: no D-13 policy notice right after agreeing

> **SUPERSEDED 2026-10-29 by legal R28.22 P2-2 (MUST, 11-06), with Product's agreement (head-eng's routing).** Both policy pages promise to announce material changes in the app, so a sign-in can't count as seeing the notice. B7 is **removed**. The section below replaces it; everything after it is B7's history.

## P2-2 (replaces B7)

**The rule** (legal's minimum; head-eng and head-product):
- don't mark the notice seen at the sign-in screen;
- show the approved D-13 tip after sign-in, as for any signed-in user. "Sign-in" means any session start, the username Continue included;
- mark it seen only after the tip has actually shown;
- no new copy, and the pinned sign-in line with both links stays.

**The change:**
- `useWhatsNew` drops B7's boot-fact read, its seen-write effect, and the `!agreedThisLaunch` term in the entry's condition. `useSession` drops `bootSignedIn` and is back to the branch base.
- The only seen-mark left is `dismiss`, the tip's own tap on League home. It persists `SEEN_KEY` and marks the version seen in memory, and it can only run after the tip has rendered. Nothing changes copy.
- Pin 9 (the sign-in line, unconditional, both links) is kept as is.

**Evidence:**
- [x] **Structural guard** `check-whats-new.js` pin 8, rewritten. It checks that:
  - `SEEN_KEY` is written exactly once, inside `dismiss`, and no other `src/` file holds the key;
  - `setSeenVersion(APP_VERSION)` is called only in `dismiss`;
  - the hook reads no session state (no `useSession`), and `bootSignedIn` is gone from `src/`;
  - the entry's condition is exactly `enabled && APP_VERSION != null && seenVersion !== undefined && seenVersion !== APP_VERSION`.

  Pins 1–7 and 9 are unchanged and pass. **Sabotage 7/7 red,** restored byte-identical: B7's boot write back; an in-memory mark at mount; the entry gated on sign-in state (`useSession` back); an extra term in the entry's condition; `dismiss` storing nothing; `bootSignedIn` back in `useSession`; another file holding the seen key. A comment-only control stays green.
- [x] **Code-walk:**
  - The tip renders only on League (`LeagueScreen.tsx`), which needs a signed-in user. Every path into Main (the username Continue, the hint row, Apple, an ESPN/MFL entry, a restored session) is a session start, and afterwards League shows the tip while `ux.whats_new` is on and the version is unseen.
  - Seen is stored only by the tap. A user who never taps sees it on each visit to League (no silent expiry, pin 6), which is D-13's existing contract.
- [x] **Manual TestFlight checklist (operator, 11-06 build, `ux.whats_new` on).** The tip lives on **League home**: open the League tab (which opens on the rankings), then League home (`LeagueScreen` is the LeagueHome sub-route, `TabNav.tsx:586-597`).
  1. Delete the app, reinstall, sign in with a Sleeper username (the username Continue), then open the League tab, then League home: the "We've updated our Privacy Policy and Terms of Use…" tip shows.
  2. Tap it: Help & about opens. Go back to League home: the tip is gone. Quit, relaunch, open the League tab, then League home: still gone.
  3. Reinstall again and sign in with Apple, then open the League tab, then League home: the tip shows again (the seen-mark is per device, and it was wiped with the app). Use the solid white "Continue with Apple" button if #507 ships in the 11-06 build; otherwise use the "Already have an account? Sign in with Apple" link.
  4. On a device that was signed in on a build before 1.22.0 and **has never run a 1.22.0 build**, install the 11-06 build over it, then open the League tab, then League home: the tip shows once, and tapping it opens Help & about.
  5. Sign out on a device that has tapped the tip, sign in again, then open the League tab, then League home: no tip (already seen for 1.22.0 on this device).
  6. On the sign-in screen, "By signing in you agree to the Terms & Privacy Policy" shows, and both links open.

**Next (P2-3, before the first 1.22.x patch, separate PR):** key the notice to a "last material change" version, not the app version. It's served by the server and stored per account (Product), with the 1.22.0 device ack carried up. The first patch must not ship the app-version key.
- **From release-lead's delta QA (GO-with-notes @ `d318d180`), for P2-3:**
  - 1.22.0's device key doesn't record who tapped, so the device ack must NOT be credited to whoever is signed in at the patch's first launch.
  - Harden pin 8 against indirect writes: walk `App.tsx` too (outside the `src/` walk), count every AsyncStorage call that takes `SEEN_KEY` (including `multiSet`, an alias, a key built from pieces, and `setSeenVersion(v ?? APP_VERSION)`), and pin LeagueScreen's `{whatsNew ? (` gate.

---

## B7 (history, superseded)

**Date:** 2026-10-27
**Entry point:** direct ask (head-eng → onboarding-eng 2026-10-27, from Product's pre-launch review B7; onboarding-pm §3, "a gap in my D-13 spec"). It amends #380 (D-13; spec `plans/launch-support-policy/scope-d13-policy-notice.md` on the launch-support-policy plan branch). Due in release-lead's queue by 11-03.
**Builder:** onboarding-eng
**Operator sign-off on waivers:** none needed beyond §1 (c).

**The gap.** #380 keys the policy notice to the release version, 1.22.0. `useWhatsNew` had no first-install check, so a brand-new install agreed to the policies on the sign-in screen ("By signing in you agree to the…") and was then told "We've updated our Privacy Policy and Terms of Use…".

**The fix.** `useSession.bootstrap` records the boot fact `bootSignedIn: !!user`: did this launch restore a signed-in user? That covers a fresh install, a reinstall (AsyncStorage is wiped; the Keychain session token survives, so the token is deliberately NOT the signal) and a signed-out user. Each goes through the sign-in screen and agrees to the current policies. `useWhatsNew` reads `bootSignedIn === false`, hides the entry, and stores it as seen. useSession gains no import, so its harnesses (e.g. `check-win-now-recovery.js`) are untouched; a first cut that imported the hook into useSession broke that harness's import allowlist.
- A signed-in user upgrading restores a user, so they still see the notice once, as D-13 requires.
- **Behaviour note for legal and release-lead:** a signed-out existing user also skips the notice, and gets the sign-in screen's "you agree" line with its links instead.

## 1. Analytics scope
- [x] **(c) WAIVED:** no new events. The tip's existing `tapAction('whats_new')` is unchanged. The change only stops the tip showing to people who just agreed.

## 2. Schema & flag scope
- Tables/columns: none. Flags: none (`ux.whats_new` still gates the tip; its value isn't changed here). Env / `model_config`: none.
- **Rollback:** revert the commit. The notice then shows on fresh installs again.

## 3. Evidence scope
- [x] **Structural guard:** `mobile/tests/check-whats-new.js` pin 8. It checks that:
  - `bootSignedIn` is assigned exactly twice in useSession: the initial `null`, and `!!user` in `bootstrap` after the user is restored; sign-out doesn't reset it, and no other file sets it;
  - `useWhatsNew` reads `bootSignedIn === false`, the entry requires `!agreedThisLaunch`, and `SEEN_KEY` is written only by dismiss and by the B7 effect, whose first statement is `if (!enabled || !agreedThisLaunch || !APP_VERSION) return;`.

  Pins 1–7 are unchanged and pass. **Sabotage 8/8 red,** restored byte-identical:
  - the entry ignores the boot fact;
  - it's stored seen on every launch;
  - an unknown boot counts as agreed;
  - it's never stored seen;
  - it's keyed on the Keychain token;
  - it's always signed out;
  - sign-out resets the boot fact;
  - another file sets it.
- [x] **Code-walk:**
  - `bootstrap` reads `SU_KEY` (`sleeper_user`) from AsyncStorage. Every signed-in state, including account-only, has a user there, and RootNav routes to sign-in without one.
  - The tip renders only on League (`LeagueScreen`), which needs a signed-in user. So `bootSignedIn` is already set when the hook mounts, and a late storage read can't show the entry, because the entry also requires `!agreedThisLaunch`.
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
