# Feature Scope — Home tiles' "‹ Home" control and the navigation continuity fixes

**Date:** 2026-11-17
**Entry point:** direct ask (operator, through the main session): "wiring Home's tiles to the Home control, plus the smaller navigation fixes from the audit". The audit is the 2026-11-12 navigation map (`docs/reviews/2026-11-12-navigation-map/README.md` on branch `docs/navigation-map`) and its fix list. Decision Q1 taken as option (a), following D-269. Q5 not taken (rank pages keep their one exit). Out of scope: R6, R7, R10, R11, R12 and decisions Q2–Q7.
**Builder:** builder subagent on `feat/nav-continuity` (D-275)
**Amended 2026-11-19 (D-276, [home-return-unify](../home-return-unify/scope.md)):** with flag `nav.home_return_unified` on (shipped on), the position tile body arms this "‹ Home" bar too and League rankings drops D-269's header control; the rows and step below that say otherwise describe that flag OFF.
**Operator sign-off on waivers:** GIVEN 2026-11-17 — the operator answered "Yes, sign off" to the main session's question on the analytics waiver (§1). The sign-off covers that waiver only; the deliberate omission (§What is not built) is restated to the operator in the release message for build 197.

---

## What the user sees

### Flag `nav.home_return` (R5, decision Q1 (a))

When a Home tile moves the user to another tab, a **"‹ Home"** control appears at the top of the destination, directly under the top bar, for that visit only. One tap returns to the Home tab as the user left it. Leaving that tab any other way (tab bar, a link) ends the visit, and coming back to the tab later never shows a stray control.

| Home tile | Destination | "‹ Home"? |
|---|---|---|
| Team outlook (View / Set) | Acquire, Trade DNA sheet | yes |
| Playoff card's Review outlook | Acquire, Trade DNA sheet | yes |
| Overall rank | League rankings | yes |
| Buy, Sell, See P ranking (position tile) | League rankings | yes |
| Find a trade | Acquire (whatever page is open there) | yes |
| View matches | Matches | yes |
| Position tile body (D-269) | League rankings, own team | `nav.home_return_unified` on (D-276): **yes**, and the bar's tap also closes the arrival's drill-in (`home_back`). Off: its own D-269 header "Home" control, unchanged (no second control) |
| Rank players | Rank tab (a rank page) | **no**: rank pages keep exactly one exit (operator ruling 2026-08-16, `check-rank-nav-exit.js`; Q5 not taken) |
| Check trends | Trends (a rank page) | **no**: same ruling |
| Standings, playoff card's View and its sheet rows, Usage Rates, Search free agents, Link a league | pages opened over the tabs | already have a Back that returns to Home |

The control is drawn once, by `TabNav`, between the top bar and the tabs (`components/HomeReturnBar.tsx`), so it lands on whichever Acquire page is open without each page drawing its own. Same chevron-and-word treatment as the app's "‹ Back"; label "Home"; VoiceOver "Back to Home"; testID `home-return.back`.

Not extended to non-Home origins (League rankings' Offer / Target, Matches' Open in calculator, Usage Trends' Trade) or to the Trios streak chip: the chip is on Trios (a rank page), not on Home, so its arrival has no Home to return to and would need a label other than "Home" (see §What is not built).

### Flag `nav.continuity` (R1–R4, R8, R9, R13)

- **R1** — the league picker opened from inside the app (league switcher's Add a league, Home's Link a league, Free agents, Usage Trends, Settings' link rows, a failed ESPN/MFL send, League home's Sign in to ESPN) shows **Close** next to Sign out; Close returns to the page it was opened from. A one-league user is no longer bounced straight back out. At sign-in the picker is unchanged (no Close, auto-forward as before).
- **R2** — picking a league in that in-app picker, Usage Trends' Trade and Re-rank, and the pushed Draft Room's "Rank the rookies" return to the tabs already underneath instead of stacking a second copy of the app. Rookie Ranks' "‹ Back to the draft room" returns to the Draft tab when it came from there.
- **R3** — Team review's Find my trades, League home's Find a trade and Rankings, Matches' Find a trade and Open in calculator, League rankings' Offer / Target hand-off, the rank chooser's method cards and "More ways to rank" return to the page already underneath (React Navigation `navigate(…, { pop: true })`, G-056) instead of opening a new copy on top. A page that is not underneath opens exactly as before.
- **R4** — the "go back, or if there is nothing to go back to, go to X" controls test the page's own stack: Quick Set Tiers' Not now lands on Tiers, Quick Rank's finish lands on Tiers, Roster setup's exit lands on the Acquire landing, and every tab-stack "‹ Back" on the first page of its tab goes to that tab's named fallback, not to Home.
- **R8** — sign-out (Settings › Account, the flat Settings list, the league picker), account deletion and session expiry leave the sign-in page alone on the stack, as the test-profile swap does. A reset removes every page, so the two leave prompts this touches let it through: Tiers' new prompt never fires for a reset, and Roster setup's existing tier prompt and skip bookkeeping step aside for a reset (flag-gated). The founder notes page's prompt (`RuleWaterfallReview`) is unchanged and can still ask during a sign-out with unsaved founder notes.
- **R9** — Portfolio gets the app's own "‹ Back" (it was the one Acquire sub-page on the dead system arrow). "See liked" on a finished deck opens Matches › Awaiting (the liked trades) for the active league instead of Portfolio. Label unchanged.
- **R13** — three "go to X" sentences become links, words unchanged: Roster setup's "Trade DNA › Your roster" (opens the Trade DNA sheet on the Acquire landing), the rank chooser's "Settings" (the Ranking settings page, or the flat Settings list with the hub off), and the standing-offer toast's "Matches → Standing offers" (the toast gains a "Standing offers" action and is held 5 s). Tiers asks "Discard your tier changes?" (Keep editing / Discard, Roster setup's wording) before a page removal would drop unsaved moves.

With either flag off, its behaviour is exactly today's: every changed call site keeps the old call in its flag-off branch (pinned by `check-nav-continuity.js` part B).

## What is not built, and why

| Item | Why |
|---|---|
| "‹ Home" on Rank players / Check trends | Rank pages: 2026-08-16 ruling stands, Q5 not taken |
| The Trios streak chip | The brief placed it on Home; in code it is on Trios (`RankScreen.tsx` streak chip → League home). Not a Home origin, so "‹ Home" would be wrong, and "‹ Trios" is new wording the brief does not allow. Left as is |
| The flag-off Home (four text rows, `HomeScreen` with `nav.home_hub` off) | Not the tiles the audit counts; `nav.home_hub` ships on |
| League rankings playoff tile's Review outlook (`LeagueSummaryScreen` `onTileReviewOutlook`) | Not in the audit's R3 list (it was a pending branch when the map was written); executed by `check-league-rankings-playoff-tile.js`; left as is |
| The picker's token-missing reroutes (`LeaguePickerScreen` replace('SignIn') ×3) | Not in R8's list (sign-out, deletion, expiry); left as is |
| Android hardware back for "‹ Home" | iOS-only release; the tab switch has no stack entry to pop (same as D-269) |

## 1. Analytics scope

- [ ] (a) New events specced — none.
- [x] **(b) Existing events cover most of it:** `home_tile_tapped` (which tile was tapped), `tab_selected` (a tap on the Home tab), `screen_viewed` (every page change, with `prev_screen`). A tap on "‹ Home" shows up as `screen_viewed` Home with the destination as `prev_screen`, without a `tab_selected` row.
- [x] **(c) WAIVED — operator sign-off 2026-11-17 ("Yes, sign off"):** no dedicated event for the "‹ Home" tap, the picker's Close, or the Tiers prompt's choice. Rationale: navigation chrome; the brief limited the build to the controls. If the operator wants a direct count, the follow-up is one client event (`home_return_tapped {tab}`) registered in `analytics_taxonomy.py` and `NON_INTENT_EVENTS` in the same commit.

## 2. Schema & flag scope

- New/changed tables or columns: none.
- New feature flags (both CLIENT-ONLY, no route reads them): `nav.home_return`, `nav.continuity`. Code default False (`backend/feature_flags.py` `FLAG_KEYS`), shipped **true** in `config/features.json` (operator asked for the behaviour), mirrored true in `release`, `onboarding-v2`, `profiles-on` fixtures, compiled default true in `mobile/src/state/useFeatureFlags.ts` (same value as config, so the first paint agrees with the fetched map). Not in `FTF_FLAGS`. Documented in `docs/config-reference.md`. Graduation: remove the flag-off branches after one TestFlight cycle with the checklist below passed.
- Rollback lever (deploy-free, no new build): set either key false + `POST /api/feature-flags/reload`. Most call sites read the flag live; `nav.home_return` disarms at the next revalidate.
- New env vars / `model_config` keys: none.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-nav-continuity.js` (`npm run test:nav-continuity`), 108 assertions. Part A EXECUTES the decisions: `navigation/navContinuity.ts` (which tap arms which tab, own-stack Back, picker in-app detection, the pick's exit, the auto-forward rule, navigate options, the sign-in reset, the Tiers prompt rule) and the real zustand store `state/homeReturn.ts` driven through tap → land → leave sequences. Part B pins every call site to those helpers with the flag-off branch intact. Part C pins the flags.
- [x] Existing checks updated where they pinned an exact line this work changed (intent unchanged): `check-home-hub.js` 12c, `check-home-playoff-banner.js` F (the arm line between track and navigate), `check-team-review.js` 20b, `check-league-candidates-300.js`, `check-offer-prefill-330.js` S-1 (accept the `pop` form / the new dep), `check-usage-trade-handoff.js` (env gains `continuityOn: false` and `popTo`). `check-rank-nav-exit.js` unchanged and green.
- [x] **Unit tests:** `backend/tests/test_nav_continuity_flags.py` (registration, False code default, true in config + three fixtures, comment present, not env-forced, client default matches).
- [x] **Code-walk proof:** below.
- [x] **Manual TestFlight checklist:** below.
- `testID`s added: `home-return.back`, `leagues.close`, `roster-setup.done.dna-link`, `rank-home.settings-link` (all static; `testid-lint` OK).

### Code-walk proof (router: `@react-navigation/routers` 7.5.3, read in `node_modules`)

1. **Stacking (G-056).** `StackRouter` `NAVIGATE` reuses a route only when it is current, when `payload.pop` is set, or with a `getId` (`StackRouter.tsx:372-390`); with `pop` it keeps the routes up to the match and drops the rest (`:410-428`); with no match it pushes as before (`:441-451`). Nested `{ screen, pop: true }` params are forwarded as `navigate({ name, params, pop })` (`core/useNavigationBuilder.tsx:698-705`). `POP_TO` finds the existing route below and drops everything above (`StackRouter.tsx:575-662`).
2. **R5.** `HomeHub.tsx:168-487` arms (flag-gated `armReturn`) after `track` and before `navigate`. `TabNav.tsx:850` mounts `HomeReturnBar` once; `TabNav.tsx:857` reports every tab focus to `state/homeReturn.ts`, whose `noteTabFocus` keeps the arm only for its own tab (`navContinuity.homeReturnOnTabFocus`). `HomeReturnBar.tsx` renders null unless `homeReturnVisible` and navigates `Main › Home`.
3. **R1/R2 picker.** `RootNav.tsx:661` `inApp` = flag ∧ `Main` below the picker in the root stack (at sign-in the picker REPLACES SignIn, so it is index 0). `:667-668` pick → `popTo('Main')` in-app, else `replace('Main')`. `:679` Close → `goBack()`. `LeaguePickerScreen.tsx:247` returns before the auto-forward; `:534-541` draws Close. On the `popTo` path the pick first calls `useSession.refreshAfterLeagueChange()` (the same trade-input note and cache invalidations as the in-place `switchLeague`), because the tabs are not remounted.
4. **R4.** `canGoBack()` asks parents (`core/useNavigationHelpers.tsx:78-90`) and the tabs' default `backBehavior: 'firstRoute'` can always go back to Home (`TabRouter.tsx`), so the old fallbacks were unreachable. `backOrFallback` tests `navigation.getState().index` of the page's own stack: `TabNav.tsx:134`, `QuickSetTiersScreen.tsx:412`, `QuickRankScreen.tsx:181`, `RosterSetupScreen.tsx:555`.
5. **R8.** `navigation.reset({ index: 0, routes: [{ name: 'SignIn' }] })` from a root-stack page resets the root stack: `SettingsAccountScreen.tsx:57`, `SettingsScreen.tsx:110`, `RootNav.tsx:673`; expiry `useSession.ts:1005` (`navigationRef.reset`), the pattern of `testProfile.ts` `restartNavigation`.
6. **R13 Tiers.** `TiersScreen.tsx:465` `beforeRemove` fires on any removal of the page (pop, popTo, popToTop from a Rank re-tap), including removal by a parent's reset (child listeners are consulted first: `core/useOnPreventRemove.tsx:52-53`), and not on a tab switch; it prevents, asks, and on Discard re-dispatches `e.data.action`. `tiersLeavePrompts` returns false for `RESET`, so R8's sign-out reset is never held; `RosterSetupScreen.tsx` `implicitExitRef` does the same for its own prompt.

### Manual TestFlight checklist (operator)

Setup: a TestFlight build with this branch, a Sleeper account with ONE league (for 3) and one with two or more leagues. "Flag off" = set the key false in `config/features.json` on the server + `POST /api/feature-flags/reload`, then pull to refresh or relaunch.

**`nav.home_return`**

1. Home → tap **Team outlook**. Expect: Acquire opens with the Trade DNA sheet; close the sheet; a "‹ Home" bar is under the top bar. Tap it. Expect: Home, as you left it. *Flag off:* no bar; only the Home tab gets you back.
2. Home → playoff card → **Review outlook**. Same as 1.
3. Home → **Overall rank**. Expect: League rankings with "‹ Home" above its header. Tap a team, then "‹ Home". Expect: Home. *Flag off:* no bar.
4. Home → a position tile's **Buy**, then **Sell**, then **See P ranking**. Expect: "‹ Home" each time; it returns Home. *Flag off:* no bar.
5. Home → **Find a trade**. Expect: Acquire (whatever page was open) with "‹ Home". *Flag off:* no bar.
6. Home → **View matches**. Expect: Matches with "‹ Home". *Flag off:* no bar.
7. After 3: instead of "‹ Home", tap the **Matches** tab, then the **League** tab. Expect: no "‹ Home" on League any more (the visit ended).
8. Home → **Rank players** and → **Check trends**. Expect: NO "‹ Home" (rank pages keep "More ways to rank" as their one exit) in both flag states.
9. Home → a position tile's **body** (D-269). Expect (with `nav.home_return_unified` OFF): League rankings with your team open and the header "Home" on the right, and NO "‹ Home" bar (only one Home control). With it on (the shipped value since D-276), see `docs/plans/home-return-unify/scope.md` checklist instead.

**`nav.continuity`**

10. (two-league account) Top bar league name → **Add a league**. Expect: Choose a League with **Close** next to Sign out. Tap Close. Expect: back where you were. *Flag off:* no Close.
11. (one-league account) Same as 10. Expect: the picker stays open (it used to bounce straight back). *Flag off:* it bounces back.
12. From the picker in 10, pick a league. Expect: the tabs, on the page you came from; a left-edge swipe at the root of a tab does NOT slide the app away to reveal another copy. *Flag off:* fresh tabs (every tab reset).
13. Sign out, sign in: the picker at sign-in has NO Close and a one-league account still forwards automatically (both flag states).
14. Home → Usage Rates → a player → **Trade**. Expect: Acquire with the search; no second copy of the app underneath (left-edge swipe at Acquire's first page does nothing). Repeat with **Re-rank** (lands on Quick Set). *Flag off:* the old stacking.
15. Draft Room opened from League home → **Rank the rookies** → Rookie Ranks → "‹ Back to the draft room". Expect: a Draft Room; Back from it returns to the tabs, not to a second Draft Room. With the Draft TAB: Draft tab → Rank the rookies → "‹ Back to the draft room" returns to the Draft tab.
16. Acquire → Team review → go through to **Find my trades**. Expect: the Acquire landing you started from (Back/swipe does not return into the review). *Flag off:* a second landing over the review.
17. League → League home → **Rankings**. Expect: back on League rankings with no Back control (the tab's own page), not a second copy with a system arrow. Then League home → **Find a trade** while an Acquire sub-page (e.g. Portfolio) is open: lands on the landing, Portfolio gone.
18. Matches → an empty state's **Find a trade**, and a match's **Open in calculator**, while Acquire has a sub-page open. Expect: the landing (with the trade loaded for Open in calculator), no second landing.
19. Rank: on Tiers → **More ways to rank** → pick **Tiers board**. Expect: the same Tiers page you left (unsaved moves still there), not a blank copy. From the chooser pick a different method, then More ways again: the chooser you came from, not a new one.
20. Tiers: drag a player (do not save) → **More ways to rank**. Expect: "Discard your tier changes?" — Keep editing stays; Discard leaves. Re-tapping the Rank tab with unsaved moves asks the same. Switching to another tab does NOT ask. *Flag off:* no prompt.
21. Fresh launch with no saved rank method (Quick Set is the Rank tab's first page): finish a position → "Tiers set" → **Not now**. Expect: Tiers. *Flag off:* Home.
22. Deep link `app/league/home` cold: League home's "‹ Back". Expect: League rankings. *Flag off:* Home.
23. Settings › Account › **Sign out**. Expect: sign-in page; a left-edge swipe does nothing (nothing underneath). Sign in again: one set of tabs. Same with **Delete account** on a throwaway test account. Also: drag a Tiers player without saving, switch to Home, open Settings and sign out — no "Discard" prompt, straight to sign-in. *Flag off:* the old pages stay underneath.
24. Let a session expire (or revoke it server-side): the app shows sign-in with nothing underneath.
25. Acquire → Portfolio. Expect: "‹ Back" (chevron and word) top left. *Flag off:* the system arrow.
26. Finish a deck → **See liked**. Expect: Matches › Awaiting for this league. *Flag off:* Portfolio.
27. Roster setup → done step → tap **Trade DNA › Your roster**. Expect: the Acquire landing with the Trade DNA sheet open. *Flag off:* plain text.
28. Rank chooser → tap **Settings** in "Change your pick in Settings." Expect: the Ranking settings page (flat Settings with the hub off); Back returns to the chooser.
29. Post a standing offer. Expect: the toast has a **Standing offers** button for 5 s; it opens Matches on Standing offers. *Flag off:* the toast without the button.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added or changed |
| `living-memory/LLD.md` | n/a | no schema/route/invariant convention shifted; the navigation conventions live in `mobile/src/navigation/CLAUDE.md` (updated) |
| `docs/architecture.md` | n/a | no backend module wiring or data flow changed |
| `living-memory/HLD.md` | n/a | no new module, client or major flow |
| `docs/cross-client-invariants.md` | n/a | mobile-only navigation; no shared constants |
| `docs/glossary.md` | n/a | no new domain term ("‹ Home" is a control, named in the navigation map) |
| `DECISIONS.md` | updated | D-275 |
| `docs/config-reference.md` | updated | the two flag rows |
| `mobile/src/navigation/CLAUDE.md`, `mobile/src/components/CLAUDE.md`, `mobile/src/state/CLAUDE.md`, `mobile/tests/README.md` | updated | present behaviour of the changed navigation |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` + `maestro-testid-lint` on the pushed sha (main session pushes).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-11-17 entry.
- **TestFlight verification:** the checklist above, by the operator; outcome to TEST_LEDGER.
- Express lane declared by the operator? No (full gates).
