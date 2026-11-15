# Improve pages: evidence (step 1)

> D-056: no Maestro, no simulator, no `screens/` capture. This file holds what was run for step 1
> of the [spec](spec.md) §10.3 build order (the two pages and the Standings link rows, app only),
> the sabotages, the code walk, and the manual TestFlight checklist. Decision **D-265**. Every
> `file:line` was read on `feat/direction-pages` (origin/main plus `feat/playoff-targets` and
> `docs/playoff-pages-spec`). Counts are also in `living-memory/TEST_LEDGER.md` (2026-11-15).

- [0. Scope and judgement calls](#0-scope-and-judgement-calls)
- [1. What was run](#1-what-was-run)
- [2. Sabotages](#2-sabotages)
- [3. Code walk](#3-code-walk)
- [4. Manual TestFlight checklist](#4-manual-testflight-checklist)

## 0. Scope and judgement calls

The approved spec is the scope block for this feature: it answers analytics (§9), flags (§8),
evidence (§10.1) and docs (§10.2). Step 1 builds P-1 to P-14 and the `league.direction_pages`
flag. Not built here, by the build order: the `team_direction` block, the Home card
(`HomePlayoffBanner` is untouched), the button logic, the half sheet, the experiment, the other
three flags, and every §9 event (step 3 owns "the events", including `direction_page_opened`).

Where the spec left room, these readings were taken:

| # | Point | Reading taken |
|---|---|---|
| J1 | P-5 "one new prop that skips the collapsed step" | Only `MaxPfMovesBody` has a collapsed step of its own ("Show moves"), so only it gains the prop, `openOnArrival` (default false). `PlayoffTargetsBody`'s only collapsed step is the Standings `Disclosure` around it; the page renders it directly, so it needs no prop and is unchanged |
| J2 | P-6 projected pick "from the same block as the list" | `playoff_targets` has no pick label. The D-257 label is served only as `max_pf_moves.baseline.label` (spec §2), so both pages read it there, from the same forecast read. It is hidden when that block is absent, and when the stored draft order is `reverse_standings` or `lottery_or_other` (the H-5 / §7.2 rule for the same figure) |
| J3 | P-10 "has something to offer" | The §5.3 rule from the blocks the read already carries: the other feature's flag on, its block `state` `ready`, and for the draft pick `pick_owner.owns_own_pick === true`. The server's state decides; the app classifies no probability. While `league.direction_pages` is off (a deep link) the cross-link is hidden, because the flag gates every entry point (§8) |
| J4 | P-12 "the existing unavailable card" | No existing card fits a page (Standings' says "standings coming"). The page uses Standings' card construction with its own two lines (`utils/directionPagesCopy.ts`). A forecast read that fails shows Standings' "Couldn't load" pattern with Try again |
| J5 | Events on the pages | The bodies' existing events (`maxpf_moves_viewed`, `playoff_targets_viewed`, the expand and pin events) fire on the pages unchanged, with `screen` still `Standings`. §9 says the page's route name; that is left to step 3, which owns the events. Nothing is added to the taxonomy |
| J6 | Link navigation | Both links use `popTo`: back to Standings or the other page when it is below in the stack, otherwise the current page is replaced, so moving between the two pages never piles them up (React Navigation 7.5 `StackRouter` POP_TO) |
| J7 | Rosters query | The pages also read `['league-rosters', leagueId]`, the session-seeded query Standings uses, for the bodies' roster checks and the playoff page's trade partner. It is not a new request |

## 1. What was run

All on a laptop, no network, Python 3.12 venv, Node with `mobile/node_modules` from `npm ci`.

| Command | Result |
|---|---|
| `pytest backend/tests/test_direction_pages_flag.py` | **4 passed** |
| `pytest` on the new file, `test_playoff_targets_read.py`, `test_maxpf_moves_read.py` and the 44 test files that read `config/features.json`, the flag fixtures or `FLAG_KEYS` (incl. `test_seed_ui_test_db.py::test_release_flags_mirror_features_json`) | **1659 passed** in 108 s |
| `pytest backend/tests` (full suite) | **15,740 passed, 43 skipped, 0 failed** in 30m58s |
| `node tests/check-direction-pages.js` (new; `npm run test:direction-pages`) | **112 of 112** |
| every `mobile/tests/check-*.js` plus `scripts/check-contrast.js` | **189 of 189 scripts pass** (incl. `check-max-pf-moves` 153, `check-playoff-targets` 84, `check-standings-table` 107, `check-league-header-pages`, `check-home-destinations`) |
| `npx tsc --noEmit` in `mobile/` | clean, no output |
| `bash mobile/scripts/testid-lint.sh` | `testid-lint OK` |

Two existing checks had one regex each widened for the new props: `check-max-pf-moves.js` D4 (the
`gated` line now has `&& !openOnArrival` inside the collapsed term) and
`check-standings-table.js` B4g (the detail now takes `pageLinks={pageLinks}`). Both still pin
the rest of the line exactly.

`check-direction-pages.js` groups: A copy (the spec's strings), B which branch a page shows
(every input, every server state of both features), C the summary, D the §5.3 rule and the links,
E routes / header / FeedbackFAB, F one forecast read, G the existing body and the open-on-arrival
prop (the gate expression executed on real models), H page testIDs and layout order, I league
switch, J deep links, K Standings with the flag on and off, L the flag and nothing from steps 2
and 3, M Chalkline.

## 2. Sabotages

Each was applied to the working tree, the named check run, then the file restored. The tree
fingerprint (`git diff` plus untracked files, SHA-1) was `d862444c502f` before and after all
eleven.

| # | Sabotage | What went red |
|---|---|---|
| S1 | The draft-pick page drops `openOnArrival` | G5 |
| S2 | The page renders its own rows (`view.block.rows.map(...)`) | G3 (the P-5 guard) |
| S3 | Standings passes `pageLinks` with the flag off | K1 |
| S4 | Deep link `app/league/improve-pick` removed | J1 |
| S5 | `FeedbackFAB` removed from the playoff page | E5 |
| S6 | The own-pick condition dropped from §5.3 | D4, D8 |
| S7 | `openOnArrival` also skips the "Show anyway" owner gate | G6 |
| S8 | `league.direction_pages` dropped from `FLAG_KEYS` | `test_flag_is_registered_and_ships_off`, `test_flag_reaches_the_app`, `test_no_backend_code_reads_the_flag` |
| S9 | `config/features.json` sets it true | `test_flag_is_registered_and_ships_off`, `test_release_flags_mirror_features_json` |
| S10 | Key removed from `profiles-on.json` | `test_flag_is_registered_and_ships_off` |
| S11 | A backend module (`league_projections/api.py`) names the flag | `test_no_backend_code_reads_the_flag` |

## 3. Code walk

### 3.1 Routes, header, feedback button (P-1, P-2, P-3, P-11)

| Step | Where |
|---|---|
| Both screens imported and in the root param list, no params | `mobile/src/navigation/RootNav.tsx:41-42`, `:168-169` |
| Registered unconditionally, after Standings, with `LeagueTopBarHeader`, the title, the #151 JS back (`canGoBack ? goBack : navigate('Main')`) | `RootNav.tsx:986-1006`, `:1009-1029` |
| Each screen pads the bottom only and mounts one `FeedbackFAB` with its route name | `mobile/src/screens/ImprovePlayoffChancesScreen.tsx:17-21`, `ImproveDraftPickScreen.tsx:17-21` |
| Deep links at the root of the v2 table, like Standings | `mobile/src/utils/deepLinks.ts:131-132` |

### 3.2 The page (P-4 to P-10, P-12, P-14)

| Step | Where |
|---|---|
| Content keyed by user and league: a switch remounts it, dropping open rows, Show all and the impression ref | `mobile/src/components/DirectionPage.tsx:42` |
| Rosters: Standings' key, fetcher and staleTime | `DirectionPage.tsx:57-62` |
| Forecast: Standings' key `['league-projection-batch', userId, leagueId]`, fetcher and staleTime; no other request | `DirectionPage.tsx:63-69` |
| Which branch: no league, unavailable (not Sleeper, a flag off, no user, no block, unknown version or state), loading, error, the body | `mobile/src/utils/directionPages.ts:59-72`; rendered `DirectionPage.tsx:82-103` |
| Summary: playoff chance from the block's `baseline` through `playoffOddsText` (D-262), projected pick the D-257 label | `directionPages.ts:85-101`; `DirectionPage.tsx:107-116` |
| The body, rendered directly (no Disclosure); the draft-pick page passes `openOnArrival` | `DirectionPage.tsx:117-121` |
| `openOnArrival` skips only the collapsed step; the owner gate keeps "Show anyway" | `mobile/src/components/MaxPfMovesSection.tsx:44`, `:47`, `:77` |
| Find trades is the bodies' own hand-off (`popTo('Main', …)`), unchanged | `MaxPfMovesSection.tsx` `onFindTrades`; `PlayoffTargetsSection.tsx` `onFindTrades` |
| Links: "View projected standings" always, the other page when §5.3 offers it and the flag is on; both `popTo` | `directionPages.ts:111-139`; `DirectionPage.tsx:122-133` |

### 3.3 Standings (P-13)

| Step | Where |
|---|---|
| The flag is read; `pageLinks` is set only while it is on, `undefined` otherwise | `mobile/src/screens/StandingsScreen.tsx:86-92` |
| Passed to the open team's detail | `StandingsScreen.tsx:287` |
| The mount rule is computed exactly as before (`targetsMounted`, `movesMounted`); the inline sections are those values when `pageLinks` is unset | `mobile/src/components/LeagueProjectionDetail.tsx:63-75` |
| With `pageLinks`, each mounted section is one row in the Disclosure shape with a › chevron, opening its page | `LeagueProjectionDetail.tsx:104-107`, `:112-121` |

Flag off, line by line: `pageLinks` is `undefined` (`StandingsScreen.tsx:88`), so
`playoffTargets === targetsMounted` and `moves === movesMounted` (`:68`, `:75`), the two
Disclosures render as before, and both `PageLink` lines are `null` (`:104-107`). The detail
still reads no flag, query or navigation (check K7). The added `useNavigation()` call in
Standings does not change rendering.

### 3.4 The backend

`league.direction_pages` is in `FLAG_KEYS` (`backend/feature_flags.py`), false in
`config/features.json` and the three fixtures. No other backend module names it
(`test_no_backend_code_reads_the_flag`), and the forecast read is byte-identical in either state
(`test_forecast_read_is_byte_identical_in_either_state`).

## 4. Manual TestFlight checklist

For the operator, on a TestFlight build containing this branch. Turn on `league.direction_pages`
for the test account (and `league.playoff_targets`, which needs D-264 merged, for the playoff
page). Use a Sleeper league in season, before its trade deadline, with a weekly forecast saved
after `league.playoff_targets` was turned on.

| # | Do | Expect |
|---|---|---|
| 1 | With `league.direction_pages` **off**, open Standings and tap your own team | "Max PF moves" and "Playoff targets" are the expandable sections they were; one starts open by the 45% rule. Nothing else changed |
| 2 | Turn the flag on, reload, open your own team | Both rows read "Max PF moves" and "Playoff targets" with a › chevron; they do not expand. Another team's card has neither |
| 3 | Tap "Max PF moves" | "Improve Draft Pick" opens with the league selector header and a back arrow. Under the header: "Playoff chance N%" (matches the Playoffs column for your team) and "Projected pick 1.0X" |
| 4 | Read the list on that page with a playoff chance above 45% and no Rebuilding / Tanking outlook | The moves are listed at once: no "Show moves" button |
| 5 | In a league where another team owns your first | "Show anyway" still shows before the list; tap it to see the moves |
| 6 | Open a row and tap "Find trades for [player]" | Trades opens with the player on your give side |
| 7 | Back on the page, read under the list | "View projected standings"; and "Improve Playoff Chances instead" only if the playoff list is ready |
| 8 | Tap "Improve Playoff Chances instead", then the back arrow | The playoff page replaces the draft-pick page; back returns to Standings, not to the draft-pick page |
| 9 | On the playoff page | The summary's playoff chance matches "Your playoff chance today" in the list; the list is open; "Find trades" pins the player on the receive side with his team as partner |
| 10 | Tap "View projected standings" | Returns to Standings (no second Standings on the stack: one back press reaches Home) |
| 11 | Switch league in the header while a page is open | The page reloads for the new league; no number from the previous league stays on screen |
| 12 | Switch to an ESPN or MFL league on a page | "Not available for this league" card |
| 13 | Open `dtf://app/league/improve-pick` and `dtf://app/league/improve-playoffs` from Notes or Safari | Each page opens over the tabs; back returns to the app |
| 14 | Tap the feedback button on each page | The feedback sheet opens, tagged with the page's route name |
| 15 | Largest text size on each page | The two figures wrap onto two lines; nothing is cut off; links stay tappable |
| 16 | VoiceOver on Standings' "Max PF moves" row | Read as a button with the hint "Opens Improve Draft Pick" |

Regressions this is built to catch: the Standings card changing with the flag off (1), the list
staying collapsed on arrival (4), the owner gate lost (5), and pages piling up on the stack (8, 10).
