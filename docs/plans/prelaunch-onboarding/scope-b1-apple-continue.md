# Feature Scope — B1: Sign in with Apple parity on the landing

**Date:** 2026-10-27
**Entry point:** direct ask (head-eng → onboarding-eng 2026-10-27, from Product's pre-launch review B1, score 12; onboarding-pm Top 1). Due in release-lead's queue by 11-03, for the 11-06 binary.
- **Stacked on #443** (`feat/espn-signin-flag-client`, the same `SignInScreen.tsx`).
  - If #443 merges first, a merge of main leaves only B1's diff.
  - If #443 isn't merged by ~11-02, B1 merges together with it (head-eng).
- **ux-lead amends ADR-006** (head-product is routing that).

**Builder:** onboarding-eng
**Operator sign-off on waivers:** none needed beyond §1 (c).

**Why.** At launch, ESPN and MFL sign-in create accounts. That makes them third-party login services under App Store guideline 4.8, which asks for Sign in with Apple as an equivalent option. Apple's sign-in guidelines also ask for Apple's own button, at least as prominent as the other options. With `onboarding.landing` on (the launched layout, now baked into first paint by B2), Apple appeared only as the text link "Already have an account? Sign in with Apple". The risk is a rejection at the 11-10 submission.

**What changes** (`mobile/src/screens/SignInScreen.tsx`, the landing layout only):
- The text link is replaced by Apple's own `AppleAuthenticationButton`: type CONTINUE, style WHITE (Apple's style for dark backgrounds, a solid white button; release-lead #507 QA P2-b), testID `signin.apple-continue-btn`.
- It's full width, 44pt tall like the landing's other sign-in buttons (`styles.button`; P2-a; the 36pt chips were too short for the HIG minimum), directly under the chip row.
- While an Apple sign-in is in flight, the username Continue does nothing (`handleSubmit` returns on `busy || appleBusy`; QA P3).
- The username field and its Continue button below stay the primary door.
- The same `handleAppleSignIn`, so an ESPN/MFL chip selection still rides the Apple flow (`platformIntent`), and the busy guard is unchanged.
- The flags-off layout's own SIGN_IN / WHITE button is untouched.

## 1. Analytics scope
- [x] **(c) WAIVED:** the existing `signin_attempted {method:'apple'}` fires from the same handler. No new events.

## 2. Schema & flag scope
- Tables, flags, env: none. The button shows under the existing `landingOn && appleShown` (Apple availability on device). **Rollback:** revert the PR (the text link returns).

## 3. Evidence scope
- [x] **Structural guard:** `mobile/tests/check-signin-apple-parity.js` (`npm run test:signin-apple-parity`), via the AST:
  1. exactly one landing Apple button, CONTINUE / WHITE, onPress `handleAppleSignIn`, and every condition above it (not just the nearest) is exactly `landingOn && appleShown`;
  2. right under the chip row with nothing in between, and above the username field;
  3. its height equals `styles.button.height` (at least 44), and its style carries only alignSelf / height / marginBottom (no margin, position or transform push);
  4. the old text and testID are gone: no element's rendered text says "Already have an account" (JSX text and string children, joined), and no `signin.apple-link` (comment-stripped);
  5. the flags-off SIGN_IN / WHITE button stays, and there are exactly 2 Apple buttons in the screen;
  6. `handleAppleSignIn` returns while busy, and `handleSubmit` returns while an Apple sign-in is in flight;
  7. nothing else can hide it: `appleShown` is exactly `appleAvailable || TEST_APPLE_SUB !== null`, and the availability effect's early return is exactly `!accountsEnabled || Platform.OS !== 'ios'`.

  **Sabotage 19/19 red,** restored byte-identical.

  Round 1 (10):
  - SIGN_IN type;
  - solid white (since reversed: WHITE is now the pinned style);
  - a no-op press;
  - an element in between;
  - 30pt;
  - the text link back;
  - the flags-off button turned CONTINUE;
  - the busy guard dropped;
  - shown in both layouts;
  - moved below the username field.

  Round 2, after release-lead's #507 QA (9): QA's six escapes, plus the reversions:
  - an outer flag wrapper around the button;
  - `appleShown` and-ed with a flag;
  - a flag in the availability effect's early return;
  - the text link restored with its copy split across JSX children;
  - shrunk below the other buttons;
  - back to the chips' 36;
  - a `marginTop` push;
  - WHITE_OUTLINE back;
  - `handleSubmit` ignoring an Apple sign-in in flight.

  A comment-only rename, which isn't a real mutation, correctly stays green.
- [x] **Code-walk:** with `onboarding.landing` and `landing.platform_options` on, the form renders:
  1. the reauth / invited notes;
  2. the chip row (`styles.platformRow`);
  3. **the Apple CONTINUE button**;
  4. the ESPN/MFL panel or the username field, with its Continue button;
  5. "Just looking?";
  6. the legal line.
- [x] **Manual TestFlight checklist (operator, 11-06 build, iPhone signed in to an Apple ID):**
  1. Fresh install: under the Sleeper · ESPN · MFL chips is a solid white "Continue with Apple" button, the same height as the username Continue button below it, then the username field.
  2. Tap it: Apple's sheet appears, and sign-in completes.
  3. Select the ESPN chip, then tap Continue with Apple: after sign-in, the ESPN link sheet opens.
  4. With VoiceOver on, it reads "Continue with Apple, button".
  5. The text "Already have an account? Sign in with Apple" appears nowhere.
  6. Tap Continue with Apple, then (while Apple's sheet is up or the sign-in is finishing) tap the username Continue: nothing happens, and only the Apple sign-in completes.
- `testID`s: `signin.apple-continue-btn` added; `signin.apple-link` removed (only `SignInScreen.tsx` referenced it).

## 3b. App Review notes (the four sign-in doors)
- **The submission text is release-lead's, and it's legal's.** R28.16 row 7's paragraph (in `leads/legal-lead.md`) already names all four doors: "Sign in with Apple, a Sleeper username, or an ESPN or MyFantasyLeague (MFL) login". It ends "Sign in with Apple is offered on the same screen."
- B1 is what makes that last sentence visibly true: the Apple button now sits beside the ESPN/MFL chips.
- It still needs ESPN and MFL demo logins, or legal's fallback sentence. That's release-lead's call; the use conditions are in `docs/business/ops/2026-11-18-launch.md`.
- No new App Store text is drafted here. Anything added goes through legal.

## 4. Docs scope
| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route change |
| `living-memory/LLD.md`, `docs/architecture.md`, `living-memory/HLD.md` | n/a | no convention, wiring or architecture change |
| `docs/cross-client-invariants.md` | n/a | mobile only (the web has no Apple sign-in) |
| `docs/glossary.md` | n/a | no new term |
| ADR-006 | **ux-lead amends** (head-product routing) | the landing's Apple entry is now Apple's own button, not a text link |
| `docs/design/components.md` | n/a until ux-lead's ADR amendment | it follows ADR-006 |

## 5. Ship gate declaration
- **CI:** `mobile-typecheck` (with the `check-*.js` loop), testid-lint, `backend-tests` and `web-structure` green.
- **Evidence:** a `living-memory/TEST_LEDGER.md` entry. **TestFlight:** §3's checklist.
- Express lane declared by the operator? No.
