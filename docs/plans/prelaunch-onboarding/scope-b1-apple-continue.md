# Feature Scope — B1: Sign in with Apple parity on the landing

**Date:** 2026-10-27
**Entry point:** direct ask (head-eng → onboarding-eng 2026-10-27, from Product's pre-launch review B1, score 12; onboarding-pm Top 1). Due in release-lead's queue by 11-03, for the 11-06 binary.
- **Stacked on #443** (`feat/espn-signin-flag-client`, the same `SignInScreen.tsx`).
  - If #443 merges first, a merge of main leaves only B1's diff.
  - If #443 isn't merged by ~11-02, B1 merges together with it (head-eng).
- **ADR-006 decision 1 is amended in this PR** with ux-lead's text (head-product's ruling, 2026-10-28; ux-lead and design-lead agree).

**Builder:** onboarding-eng
**Operator sign-off on waivers:** none needed beyond §1 (c).

**Why.** At launch, ESPN and MFL sign-in create accounts. That makes them third-party login services under App Store guideline 4.8, which asks for Sign in with Apple as an equivalent option. Apple's sign-in guidelines also ask for Apple's own button, at least as prominent as the other options. With `onboarding.landing` on (the launched layout, now baked into first paint by B2), Apple appeared only as the text link "Already have an account? Sign in with Apple". The risk is a rejection at the 11-10 submission.

**What changes** (`mobile/src/screens/SignInScreen.tsx`, the landing layout only):
- The text link is replaced by Apple's own `AppleAuthenticationButton`: type CONTINUE, style WHITE (Apple's style for dark backgrounds, a solid white button; release-lead #507 QA P2-b), testID `signin.apple-continue-btn`.
- It's full width, 44pt tall like the landing's other sign-in buttons (`styles.button`; P2-a; the 36pt chips were too short for the HIG minimum).
- **It sits below the username field and its Continue, and below the ESPN/MFL panel** (head-product's ruling 2026-10-28). Above the field, on first paint it was the only enabled full-width button (Continue is disabled at 45% until the field has text), which reversed ADR-006 decision 1.
- **An "or" divider** comes between Continue and Apple: `styles.orDivider` (body-sm, centered), now chalk-dim, with `space.md` above and below (design-lead). The flags-off layout's "or continue with Sleeper" uses the same style, so it turns chalk-dim too: chalk-faint is for placeholders and disabled text only. The words are marketing's; design-lead says "or" alone is fine.
- **The landing body is a `ScrollView`** (`contentContainerStyle` `styles.body`: flexGrow 1, centered; `keyboardShouldPersistTaps="handled"`; it bounces only when it overflows). The returning-user, session-expired and error states run past an SE's height (design-lead's estimate), and Apple at the bottom is the first thing clipped. "handled" means that with the keyboard up, the first tap on Continue, Apple, a chip or the hint row acts instead of only closing the keyboard (ux-lead). The username field and the platform link are guide targets, so the ScrollView announces movement to the spotlight (`notifyGuideTargetsMoved` on scroll, layout and content-size changes; `check-guide-spotlight-tracking` rules 9 and 10).
- The legal line goes from chalk-faint to chalk-dim (design-lead's optional fix; same reason).
- While an Apple sign-in is in flight, the username Continue does nothing (`handleSubmit` returns on `busy || appleBusy`; QA P3).
- The username field and its Continue button above it stay the primary door.
- The same `handleAppleSignIn`, so an ESPN/MFL chip selection still rides the Apple flow (`platformIntent`), and the busy guard is unchanged.
- The flags-off layout's own SIGN_IN / WHITE button is untouched.

## 1. Analytics scope
- [x] **(c) WAIVED:** the existing `signin_attempted {method:'apple'}` fires from the same handler. No new events.

## 2. Schema & flag scope
- Tables, flags, env: none. The button shows under the existing `landingOn && appleShown` (Apple availability on device). **Rollback:** revert the PR (the text link returns).

## 3. Evidence scope
- [x] **Structural guard:** `mobile/tests/check-signin-apple-parity.js` (`npm run test:signin-apple-parity`), via the AST:
  1. exactly one landing Apple button, CONTINUE / WHITE, onPress `handleAppleSignIn`, and every condition above it (not just the nearest) is exactly `landingOn && appleShown`;
  2. below the username field, its Continue and the ESPN/MFL panel, and above "Just looking?". Its block is the very next one after the Continue block, and inside it only the "or" divider (`[styles.orDivider, styles.landingOrDivider]`, text "or") comes before the button, with only the busy spinner after;
  3. its height equals `styles.button.height` (at least 44), and its style carries only alignSelf / height / marginBottom (no margin, position or transform push);
  4. the old text and testID are gone: no element's rendered text says "Already have an account" (JSX text and string children, joined), and no `signin.apple-link` (comment-stripped);
  5. the flags-off SIGN_IN / WHITE button stays, and there are exactly 2 Apple buttons in the screen;
  6. `handleAppleSignIn` returns while busy, and `handleSubmit` returns while an Apple sign-in is in flight;
  7. nothing else can hide it: `appleShown` is exactly `appleAvailable || TEST_APPLE_SUB !== null`, and the availability effect's early return is exactly `!accountsEnabled || Platform.OS !== 'ios'`;
  8. the body scrolls: exactly one `ScrollView`, the KeyboardAvoidingView's only child, holding the whole form; `contentContainerStyle` `styles.body` with flexGrow 1, justifyContent center and no `flex`; `keyboardShouldPersistTaps` "handled"; `onScroll` is `notifyGuideTargetsMoved`, with a throttle;
  9. the "or" and the legal line are chalk-dim, and `landingOrDivider` carries only `marginTop: space.md`.

  **Sabotage 35/35 red,** restored byte-identical.

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

  Round 3, after head-product's ruling (16), each red on the pin it targets:
  - pin 2 (6): Apple back under the chips; Apple after "Just looking?"; an element between Continue and Apple; the divider removed; the divider after the button; the divider's copy changed;
  - pin 8 (7): the ScrollView back to a View; taps "never"; the taps prop dropped; the body `flex: 1`; the body not centered; no guide notifier on scroll; the form outside the ScrollView;
  - pin 9 (3): the divider chalk-faint; a margin push on the landing divider; the legal line chalk-faint.
  - Cross-check: with the scroll notifier removed, `check-guide-spotlight-tracking` also goes red (9b).

  A comment-only edit, which isn't a real mutation, correctly stays green (rounds 1 and 3).
- [x] **Code-walk:** with `onboarding.landing` and `landing.platform_options` on, the form renders:
  1. the reauth / invited notes;
  2. the chip row (`styles.platformRow`);
  3. the ESPN/MFL panel, or the hint row, the username field, its hint and error lines, and its Continue button;
  4. **"or", then the Apple CONTINUE button**;
  5. "Just looking?";
  6. the legal line.

  All of it sits inside the ScrollView, which centers it when it fits. A tap with the keyboard up reaches its target, because the ScrollView passes taps to children that handle them ("handled"), and every one of those targets is a `Pressable` or Apple's native button.
- [x] **Manual TestFlight checklist (operator, 11-06 build, iPhone signed in to an Apple ID):**
  1. Fresh install: below "See trades for your team →" is a small "or", then a solid white "Continue with Apple" button, the same height. The username field and "See trades" sit above it, under the Sleeper · ESPN · MFL chips.
  2. Tap it: Apple's sheet appears, and sign-in completes.
  3. Select the ESPN chip, then tap Continue with Apple: after sign-in, the ESPN link sheet opens.
  4. With VoiceOver on, it reads "Continue with Apple, button".
  5. The text "Already have an account? Sign in with Apple" appears nowhere.
  6. Tap Continue with Apple, then (while Apple's sheet is up or the sign-in is finishing) tap the username Continue: nothing happens, and only the Apple sign-in completes.
  7. On the smallest supported iPhone (SE 3rd gen, or 13 mini), keyboard closed:
     - fresh install: everything from the headline to the legal line shows on one screen, including the whole Apple button, and nothing needs scrolling;
     - returning user (the "Continue as @x" row) and session expired (the reauth note): the Apple button is fully visible or reachable by scrolling, and nothing is cut off.
  8. Select ESPN: the order is the chip, then the ESPN explainer and "Link your ESPN league →", then "or", then Continue with Apple.
  9. With VoiceOver on, swipe through the landing: the chips, the username field, "See trades for your team", "or", then "Continue with Apple, button".
  10. Type a username and, with the keyboard still up, tap "See trades for your team →" once: it submits on that tap. Repeat with Continue with Apple: Apple's sheet opens on the first tap.
- `testID`s: `signin.apple-continue-btn` added; `signin.apple-link` removed (only `SignInScreen.tsx` referenced it).

## 3b. App Review notes (the four sign-in doors)
- **The submission text is release-lead's, and it's legal's.** R28.16 row 7's paragraph (in `leads/legal-lead.md`) already names all four doors: "Sign in with Apple, a Sleeper username, or an ESPN or MyFantasyLeague (MFL) login". It ends "Sign in with Apple is offered on the same screen."
- B1 is what makes that last sentence visibly true: Apple's own button is now on the same screen as the ESPN/MFL chips, below the sign-in form.
- It still needs ESPN and MFL demo logins, or legal's fallback sentence. That's release-lead's call; the use conditions are in `docs/business/ops/2026-11-18-launch.md`.
- No new App Store text is drafted here. Anything added goes through legal.

## 4. Docs scope
| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route change |
| `living-memory/LLD.md`, `docs/architecture.md`, `living-memory/HLD.md` | n/a | no convention, wiring or architecture change |
| `docs/cross-client-invariants.md` | n/a | mobile only (the web has no Apple sign-in) |
| `docs/glossary.md` | n/a | no new term |
| `docs/adr/adr-006-account-later-onboarding.md` | **updated** | decision 1's amendment (ux-lead's text, verbatim), and the status line |
| `docs/design/components.md` | n/a here | design-lead adds the Apple-button row once #507 lands (their review) |

## 5. Ship gate declaration
- **CI:** `mobile-typecheck` (with the `check-*.js` loop), testid-lint, `backend-tests` and `web-structure` green.
- **Evidence:** a `living-memory/TEST_LEDGER.md` entry. **TestFlight:** §3's checklist.
- Express lane declared by the operator? No.
