# Code walk — Landing platform options (D-056 evidence)

Line numbers as of the shipping commit on branch
`claude/app-entry-platform-options-3e16ac`.

> **V2 note (same day):** sections 3, 4 and "Session requirement" below
> describe the v1 Apple-panel design, superseded hours later by the
> sessionless entry in §V2 at the bottom (D-164). Sections 1, 2, 5, 6, 7
> still describe shipped behavior.

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

---

# V2 — Sessionless platform entry (D-164): the Apple decoupling

Line numbers as of the shipping commit on `claude/platform-entry-decouple-apple`.

## 1. The sessionless route

- `backend/server.py:21544` — `POST /api/entry/platform` (`entry_platform`).
  Gated on `landing.platform_options` + the platform's `espn.link`/`mfl.link`;
  **no `_require_session` anywhere in the body** (pinned by the structural
  guard). Preview branches return the byte-shape of the link routes'
  `choose_team` payloads; ESPN cookies come from the body only.
- Deterministic ids: `server.py:21656-21658` (`entry:espn:<canonical SWID>`,
  else `entry:espn:<league>.t<team>`) and `:21696`
  (`entry:mfl:<league>.f<franchise>` via `_mfl_member_id`). The `entry:`
  namespace never collides with the `espn:`/`mfl:` member placeholders
  (documented never-routable at `database.py` `replace_espn_league_members`).
- Mint: `server.py:21700` — the same `_extension_build_session` behind
  `/api/extension/auth` (creates the users row, registers the token);
  `_link_device_identity` for analytics stitching; `extension/auth`-shaped
  response. #321 wrong-account parity: the cookie-pair SWID must own the
  claimed team (403 `espn_bad_credentials` + `wrong_account`).
- Proven by `backend/tests/test_entry_platform_route.py` (13 tests), incl.
  the end-to-end handoff: the minted token drives the real `/api/mfl/link`
  import and the claimed franchise binds to the entry user in
  `league_members`.

## 2. The sheets in entry mode

- `EspnLinkSheet.tsx:280` — preview through `entryEspnPreview` (same wire
  shape, same 403 `espn_auth_required` self-serve, WebView capture path
  untouched — `EspnConnectScreen`'s default path makes zero authenticated
  calls and runs signed-out). `:162` — the my-leagues fetch (a
  stored-credential read) is skipped in entry mode. `:332` — `pickTeam`
  mints first (`entryPlatformMint` stores the token —
  `api/platformEntry.ts`), delivers the user via `onEntrySession`, then runs
  the **canonical** `linkEspnLeague` import under the fresh token.
- `PlatformLinkSheet.tsx:202/:238` — the MFL twins; `:89` — the
  `mfl.auth_link` username/password path (session-required routes) is
  suppressed in entry mode.
- Entry props default off → both sheets' linked flows are byte-identical.

## 3. The host

- `SignInScreen.tsx:617-624` — the ESPN/MFL panel's primary button opens the
  entry sheet (`signin.platform-link-btn`); Apple is gone from the panel.
  The quiet "Already have an account? Sign in with Apple" link is restored
  under every chip and still carries the v1 `platformIntent`.
- `:140` — `handleEntrySession` pins `{user_id, display_name,
  account_only: true}`; `account_only` is load-bearing: LeaguePicker's
  refresh skips the Sleeper league fetch for it and merges the platform
  leagues instead.
- `:153` — `handleEntryLinked` closes the sheet and routes through
  `(onAccountSignedIn ?? onSignedIn)()` → `LeaguePicker` (no params) → the
  shipped platform-league merge finds exactly one league →
  `onboarding.league_autoskip` picks it → session-init → Main. No new
  activation code.
- `:811-826` — sheet mounts mirror LeaguePicker's pattern (ESPN
  unconditional, PlatformLinkSheet conditional; one visible at a time).

## 4. Analytics

`api/platformEntry.ts` — the mint fires `signin_attempted` /
`signin_succeeded` / `signin_failed` with `method: 'espn' | 'mfl'` (the claim
IS the sign-in attempt). Value-only addition on the registered `method` prop;
tracking-plan addendum noted in
`docs/business/analytics/2026-07-17-tracking-plan-v2.md`.

---

# V2.1 — Login as a first-class entry option (same day)

Built by an Opus subagent; reviewed line-by-line by the lead session. Line
numbers as of the shipping commit on `claude/entry-platform-login-option`.

- `backend/server.py` — the action block sits at the top of `entry_platform`
  (~L22303–22368), BEFORE the untouched preview/mint branches: ESPN
  `my_leagues` calls `espn_service.fetch_fan_leagues(espn_s2, swid)` with the
  supplied pair and returns `jsonify({"leagues": …})` — verified byte-identical
  to `GET /api/espn/my-leagues`'s serialization; MFL `auth_leagues` calls the
  exact `_mfl.login(...)` / `fetch_my_leagues(auth["cookie"], year)` pair the
  auth-link route uses (verified against its lines), `del password` after the
  one use, `MflAuthError` → 403 `mfl_bad_credentials`. No `upsert_*`, no
  `_extension_build_session`, no session anywhere in the block — pinned by the
  guard and by `_assert_stored_nothing` in the tests.
- `mobile/src/components/EspnLinkSheet.tsx` — `fetchEntryMyLeagues` (~L181)
  soft-fails into the manual field; the capture callback's entry branch
  (~L234) feeds it the fresh pair; the first-class `espn-link.entry-signin`
  button (~L457) reuses `launchWebViewCapture` and hides once the picker has
  rows. The picker itself (`showingPicker`) was already keyed on data alone.
- `mobile/src/components/PlatformLinkSheet.tsx` — `mflAuthEnabled` drops
  `!entry` (~L98); the sign-in JSX became one `mflAuthBlock` rendered at its
  ORIGINAL position when `!entry` (linked render output unchanged) and above
  the league-id field in entry mode; `mflSignIn`'s entry branch (~L313) goes
  through the sessionless action and into the new single-select `entry-pick`
  step (~L731); `mflEntryPickLeague` (~L362) = mint → `onEntrySession` →
  canonical import → best-effort `mflAuthLink` re-store with the password held
  in `entryMflPassRef` (a ref, never state/`dirty`/logs; dropped before the
  call, cleared on reset/failure/empty-list). The session-scoped bulk
  `mflAuthImport` path is never used in entry mode.
- `mobile/src/api/platformEntry.ts` — `entryEspnMyLeagues` /
  `entryMflAuthLeagues` (~L76/L99), both `skipAuth`, no analytics: the signin
  funnel still fires exactly once, at the mint.
- Lead-session addition: SignInScreen panel explainers updated to name the
  sign-in option first ("Sign in to ESPN and we'll find your leagues, or
  enter a league ID").
