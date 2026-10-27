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
- The text link is replaced by Apple's own `AppleAuthenticationButton`: type CONTINUE, style WHITE_OUTLINE on the dark landing, testID `signin.apple-continue-btn`.
- It's full width, at the platform chips' height (36), directly under the chip row.
- The username field and its Continue button below stay the primary door.
- The same `handleAppleSignIn`, so an ESPN/MFL chip selection still rides the Apple flow (`platformIntent`), and the busy guard is unchanged.
- The flags-off layout's own SIGN_IN / WHITE button is untouched.

## 1. Analytics scope
- [x] **(c) WAIVED:** the existing `signin_attempted {method:'apple'}` fires from the same handler. No new events.

## 2. Schema & flag scope
- Tables, flags, env: none. The button shows under the existing `landingOn && appleShown` (Apple availability on device). **Rollback:** revert the PR (the text link returns).

## 3. Evidence scope
- [x] **Structural guard:** `mobile/tests/check-signin-apple-parity.js` (`npm run test:signin-apple-parity`), via the AST:
  1. exactly one landing Apple button, CONTINUE / WHITE_OUTLINE, onPress `handleAppleSignIn`;
  2. right under the chip row with nothing in between, and above the username field;
  3. its height equals the chips' `minHeight`;
  4. the old text and testID are gone (comment-stripped);
  5. the flags-off SIGN_IN / WHITE button stays, and there are exactly 2 Apple buttons in the screen;
  6. `handleAppleSignIn` returns while busy.

  **Sabotage 10/10 red,** restored byte-identical:
  - SIGN_IN type;
  - solid white;
  - a no-op press;
  - an element in between;
  - 30pt;
  - the text link back;
  - the flags-off button turned CONTINUE;
  - the busy guard dropped;
  - shown in both layouts;
  - moved below the username field;

  A comment-only rename, which isn't a real mutation, correctly stays green.
- [x] **Code-walk:** with `onboarding.landing` and `landing.platform_options` on, the form renders:
  1. the reauth / invited notes;
  2. the chip row (`styles.platformRow`);
  3. **the Apple CONTINUE button**;
  4. the ESPN/MFL panel or the username field, with its Continue button;
  5. "Just looking?";
  6. the legal line.
- [x] **Manual TestFlight checklist (operator, 11-06 build, iPhone signed in to an Apple ID):**
  1. Fresh install: under the Sleeper · ESPN · MFL chips is a white-outlined "Continue with Apple" button, the same height as the chips, then the username field.
  2. Tap it: Apple's sheet appears, and sign-in completes.
  3. Select the ESPN chip, then tap Continue with Apple: after sign-in, the ESPN link sheet opens.
  4. With VoiceOver on, it reads "Continue with Apple, button".
  5. The text "Already have an account? Sign in with Apple" appears nowhere.
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
