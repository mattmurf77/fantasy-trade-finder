# Code walk — Landing platform options (D-056 evidence)

Line numbers as of the shipping commit on branch
`claude/app-entry-platform-options-3e16ac`.

## 1. The chip row renders, correctly gated

- `mobile/src/screens/SignInScreen.tsx:115` — `platformPickerShown = landingOn
  && platformOptionsFlag && platformChips.length >= 2`. `landingOn` is
  `useOnboardingFeature('onboarding.landing')` (master AND flag, line 87);
  `platformOptionsFlag` is `useFlag('landing.platform_options')`. The chip
  list (lines 106–110) includes `'espn'` only under `espn.link` and `'mfl'`
  only under `mfl.link`; with fewer than 2 chips the row hides (a one-chip
  "choice" is noise).
- `SignInScreen.tsx:527` — the row renders only inside
  `{platformPickerShown ? … : null}`, above the form. With the flag off, or
  `onboarding.landing` off, nothing in the render tree changes: every new
  element is behind `platformPickerShown` / `nonSleeperEntry`, and
  `nonSleeperEntry` (line 117) is false whenever `platformPickerShown` is.

## 2. Sleeper default is byte-identical behavior

- `entryPlatform` initializes `'sleeper'` (line 104). `nonSleeperEntry`
  (line 117) is therefore false at mount, and every fork below renders its
  existing branch: hint row (`!nonSleeperEntry && hint`, line ~614), username
  field wrapper (line ~660), field hint, continue button, and the
  "Already have an account?" Apple link (`… && !nonSleeperEntry`). The
  username submit path (`handleSubmit`) is untouched — it never carries an
  intent, so RootNav's `platformIntentParams(undefined)` returns `undefined`
  and `navigation.replace('LeaguePicker')` is called with no params, exactly
  the pre-change call.

## 3. ESPN/MFL selection swaps the form for the Apple panel

- `SignInScreen.tsx:130-141` — `selectEntryPlatform` sets the chip, clears
  the error state, and for non-Sleeper chips dismisses the keyboard and
  `advanceGuideIfActive('s0.2')` (line 139): the Analyst's s0.2 spotlight
  targets the username field this selection hides, so it is advanced before
  the target unmounts.
- `SignInScreen.tsx:581` — the panel (`signin.platform-panel`): platform
  explainer + the official `AppleAuthenticationButton`
  (`signin.platform-apple-btn`, line 590) wired to the same
  `handleAppleSignIn` as the P2.6 primary portal. `appleShown === false`
  renders the honest `signin.platform-unavailable` line instead of a dead
  end. The error line stays outside the fork, so Apple failures surface
  under the panel.
- Flag revalidation withdrawing the selected platform resets to Sleeper
  (effect at lines 121–128), so the user is never stranded on a chip that no
  longer renders.

## 4. The choice rides Apple sign-in as an intent

- `SignInScreen.tsx:235-236` — `platformIntent = nonSleeperEntry ?
  entryPlatform : undefined`, computed at press time inside
  `handleAppleSignIn`.
- `SignInScreen.tsx:284` — linked-account branch: `onSignedIn(platformIntent)`.
- `SignInScreen.tsx:302` — account-only branch:
  `(onAccountSignedIn ?? onSignedIn)(platformIntent)`.
  Both Apple outcomes land on LeaguePicker (RootNav routes them there), so
  both carry the intent; the Sleeper flows pass nothing.

## 5. RootNav maps intent → LeaguePicker params

- `mobile/src/navigation/RootNav.tsx:176-184` — `platformIntentParams`:
  `'espn' → {espnLink: true}` (the existing #130 param), `'mfl' →
  {mflLink: true}` (its new twin, typed at line 78), `undefined → undefined`.
- `RootNav.tsx:526` / `:536` — both `onSignedIn` and `onAccountSignedIn`
  `replace('LeaguePicker', platformIntentParams(platformIntent))`.
- `RootNav.tsx:552` — `autoOpenMflLink={route.params?.mflLink === true}`.

## 6. LeaguePicker opens the right sheet, safely

- `mobile/src/screens/LeaguePickerScreen.tsx:168-187` — the MFL auto-open
  effect is a line-for-line mirror of the #130 ESPN one directly above it:
  gated on `autoOpenMflLink && mflEnabled`, deferred to the navigation
  `transitionEnd` (with the 800 ms fallback) per #266 — `PlatformLinkSheet`
  is a sibling RN `<Modal>` and wedges identically if presented
  mid-transition — then `setPlatformOpen('mfl')` (line 173), the same call
  the footer "Link an MFL league" button makes (line 652).
- `LeaguePickerScreen.tsx:203` — the single-league auto-skip
  (`onboarding.league_autoskip`) now also blocks on `autoOpenMflLink`: a
  user who chose MFL at entry and happens to have one Sleeper league gets
  the MFL sheet, not an auto-skip into that league.
- Arrival states both work: an account-only Apple sign-in lands on the P0-5
  companion state (account_only + empty list) with the sheet opening over
  it; a linked returning user lands on their league list the same way the
  Settings `espnLink` CTA (#130) already does.

## 7. Stale "coming soon" copy corrected

- `SignInScreen.tsx` smart-start branch (dark — `landing.smart_start_cta`
  false): the unsupported-URL error no longer claims ESPN/MFL "sync is
  coming soon" (both are live). It now points at the entry chips when they
  render, else at the Settings link path.

## Session requirement (why Apple is the door)

`POST /api/espn/link` and `POST /api/mfl/link` both `_require_session`
(`backend/server.py:23359` ff. / `:25955` ff.), so a platform link cannot
start sign-in by itself. Apple sign-in (`auth.accounts`, live) is the one
session mint that needs no Sleeper username — which is why the ESPN/MFL
panels lead with it rather than a platform-native credential flow at entry
(see the DECISIONS entry for this feature).
