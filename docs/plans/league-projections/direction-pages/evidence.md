# Improve pages: evidence (step 1, and the half sheet build)

> D-056: no Maestro, no simulator, no `screens/` capture. This file holds what was run for step 1
> of the [spec](spec.md) §10.3 build order (the two pages and the Standings link rows, app only),
> the sabotages, the code walk, and the manual TestFlight checklist. Decision **D-265**. Every
> `file:line` was read on `feat/direction-pages` (origin/main plus `feat/playoff-targets` and
> `docs/playoff-pages-spec`). Counts are also in `living-memory/TEST_LEDGER.md` (2026-11-15).
> Sections 5-9 are the next build, the half sheet version of the Home card (**D-270**), read on
> `feat/direction-sheet`.

- [0. Scope and judgement calls](#0-scope-and-judgement-calls)
- [1. What was run](#1-what-was-run)
- [2. Sabotages](#2-sabotages)
- [3. Code walk](#3-code-walk)
- [4. Manual TestFlight checklist](#4-manual-testflight-checklist)
- [5. The half sheet build (D-270): scope and judgement calls](#5-the-half-sheet-build-d-270-scope-and-judgement-calls)
- [6. The half sheet build: what was run](#6-the-half-sheet-build-what-was-run)
- [7. The half sheet build: sabotages](#7-the-half-sheet-build-sabotages)
- [8. The half sheet build: code walk](#8-the-half-sheet-build-code-walk)
- [9. The half sheet build: manual TestFlight checklist](#9-the-half-sheet-build-manual-testflight-checklist)

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

## 5. The half sheet build (D-270): scope and judgement calls

The operator, 2026-11-15: "get an agent building the half sheet version of the home page as the
initial experience update". **D-270** records the change of order (spec §10.3 note). Branch
`feat/direction-sheet` (step 1 plus this build). Built: the whole `team_direction` block (§7) behind
`league.direction_card`, the settings `team_direction.middle_min` / `middle_max`; the card's two
figures (§4) on Home and League Rankings; the half sheet (§5.6, S-1 to S-10) behind
`league.direction_view_sheet`; the §9 events for what exists; both flags (off) everywhere §8 lists.
**Not built (deferred by D-270):** the button row on the card (cells A and B),
`league.direction_both_middle`, the experiment definition. No change to Max PF moves, Playoff targets
or the pages beyond the analytics item.

| # | Point | Reading taken |
|---|---|---|
| J8 | H-8 with no button row in this build | The card never draws a button. With the card on and the sheet off it shows the two figures and "View" opens Standings. `direction_card_shown.shown` is always `none` |
| J9 | §7.3 lists reasons, not their order | Draft pick: `feature_off`, `unavailable`, `season_over`, `after_trade_deadline`, `draft_order_not_maxpf`, then `pick_owned_elsewhere`, then `no_miss`, `none_found` (`no_moves`). This follows the `max_pf_moves` block's own state order; a league that does not draft by max PF, or a finished season, is the more basic reason than who owns the pick. Playoffs: the `playoff_targets` state order, `no_targets` → `none_found` |
| J10 | A feature state this server does not know | Passed through as the option's reason (§7.2 calls the set open); the sheet's line for it is "Not available right now." |
| J11 | `reason` when the team is not in the run, or the read fails | `team_not_found` (spec §5.4 "the team cannot be matched"; the outlook block's word) and `read_failed`. Both are outside `unusable_reason`'s own words; the field is an open set |
| J12 | Figures for a forecast that is not current | `captured_at`, `playoff_probability`, the D-262 proof and `projected_pick` are served from any saved run that holds the team (the card marks them "last saved", H-6). `band` and `primary` are null unless `ready`. A non-Sleeper league (`unsupported_policy`) gets no figures |
| J13 | `options` while `state` is `unavailable` | Still computed from the two served blocks (which carry the same unusable reason, so neither is offered), so the sheet can say why (S-10). A feature flag off still reads `feature_off` |
| J14 | H-6 "with no saved forecast, the cell is hidden" | The card shows the pick only beside a playoff-chance figure: no estimate on the card (no run, bad probability) → no pick, even if one were sent |
| J15 | H-7's sentence | Added to the explanation only when the pick is shown |
| J16 | §8 "Needs" | The app opens the sheet only with `league.direction_card`, `league.direction_view_sheet` **and** `league.direction_pages` on: the sheet's rows are entry points to the pages, which that flag gates. The card's figures need only `league.direction_card`. No backend code reads the sheet or pages flag |
| J17 | Copy the spec does not give | "View" while it opens the sheet is a button with the spoken label "Playoff options"; the sheet has no visible title. The scrim's spoken label is "Close" (AnchorSheet's) |
| J18 | §9 calls `home_tile_tapped` "Intent" | It has been in `NON_INTENT_EVENTS` since 2026-10-10 (Home is the launch tab); moving it would change DAU for every Home tap. Left as is. `direction_card_shown` is NON_INTENT; `direction_page_opened` is intent |
| J19 | Which taps carry `via` | Only the card's direction taps: `playoff_options` (card), and the sheet's three rows (sheet), of which "View projected standings" is `standings` + `via: sheet`. The percentage tap keeps `{tile: 'standings'}` with no `via` |
| J20 | `direction_page_opened` "a page gains focus" | Once per focus, after the branch is known (never while loading), `state` = the block's state on a list, else `unavailable` / `error` / `no_league`. A blur re-arms it. A league switch on an open page remounts the content and logs again |
| J21 | P-1 "no params" vs §9's `source` | One optional route param, `{ source }`, set by each entry point (`standings`, `sheet`, `other_page`); a deep link has none and logs `deep_link`. `card` is reserved for cells A/B |
| J22 | "the page's route name as the screen" | Each body takes an optional `screen` (default `Standings`), used by every event it emits (`*_viewed`, `*_expanded`, `draft_order_rule_answered`) and by `finder_target_pinned` through `handOffToFinder`'s new `deps.screen` |
| J23 | Two "offered" rules | `utils/directionPages.offered` reads `team_direction.options` when a version-1 block is on the read; otherwise the step-1 rule over the two blocks |
| J24 | Sheet testIDs | Static literals (testid-lint and check-home-hub 11b): `home.playoff.sheet`, `.scrim`, `.standings`, `.improve-playoffs`, `.improve-pick`, and `.note` on each |
| J25 | S-7 "a downward drag" | `PanResponder` on the panel: a mostly downward move is the sheet's; release at 48pt or more closes it. No finger-follow animation (none in AnchorSheet either) |
| J26 | An owner with no name | Server: `Team N` (the `max_pf_moves` fallback). App: "owned by another team" / "Another team owns your first-round pick." |
| J27 | Settings read | `team_direction.settings()` per read while the flag is on; an invalid file makes the block `read_failed` and the rest of the read is served |
| J28 | `docs/business/analytics` addendum | Not written: §10.2 does not list one; the events are specified in spec §9 and the taxonomy comments |

## 6. The half sheet build: what was run

All on a laptop, no network, Python 3.12 venv, Node with `mobile/node_modules` from `npm ci`.

| Command | Result |
|---|---|
| `pytest backend/tests/test_team_direction.py` (new) | **11 passed** |
| `pytest backend/tests/test_team_direction_read.py` (new) | **6 passed** |
| `pytest backend/tests/test_direction_card_analytics.py` (new) | **4 passed** |
| `pytest` on the three new files, the touched `test_analytics_taxonomy_home_hub.py`, the forecast-read, flag, analytics and events files, and every test file that reads `config/features.json`, the flag fixtures or `FLAG_KEYS` (55 files) | **1716 passed** in 118 s |
| `pytest backend/tests` (full suite) | FULL_SUITE_RESULT |
| `npx tsc --noEmit` in `mobile/` | clean, no output |
| `bash mobile/scripts/testid-lint.sh` | `testid-lint OK` |
| `node tests/check-direction-card.js` (new; `npm run test:direction-card`) | **73 of 73** |
| `node tests/check-direction-sheet.js` (new; `npm run test:direction-sheet`) | **64 of 64** |
| `node tests/check-direction-pages.js` (updated) | **125 of 125** (was 112) |
| every `mobile/tests/check-*.js` (192) plus `scripts/check-contrast.js` | **193 of 193 scripts pass** |

Existing checks updated for the new shape (each still pins the rest exactly): `check-home-playoff-banner.js`
(the harness now reads the three new flags, all **off**, so every existing assertion is the H-12
proof; hooks by call order; no impression or direction tap with the flags off),
`check-home-hub.js` 6a/6e/6g (one direction call site with `tile: tap.tile, via: tap.via`; the card's
one impression), `check-league-rankings-playoff-tile.js` T2d/T4c/T4d/T5d and new T3e (the half-sheet
handler executed on both routes), `check-max-pf-moves.js` K7 and `check-playoff-targets.js` H6 (the
bodies' `screen` prop), `check-position-tile-tap.js` 8d (`via` on the prop row),
`check-direction-pages.js` E4/G5/G6/G10/H3/K1/L3/L4 plus new D12-D15 and N1-N8.
`backend/tests/test_analytics_taxonomy_home_hub.py` gained `via` on its exact prop row.

## 7. The half sheet build: sabotages

Each was applied to the working tree, the named test run, then the file restored with
`git checkout`. The tree fingerprint (`git diff` plus untracked files, SHA-1) was `da39a3ee5e6b`
(clean) before and after all twenty.

| # | Sabotage | What went red |
|---|---|---|
| S1 | Band: `<=` for the `middle_max` cut (0.65 reads middle) | `test_band_cuts_exactly` |
| S2 | Lean: `<` for `REBUILDING_MAX` (0.45 leans to the playoffs) | `test_lean_at_045_and_for_each_saved_outlook` |
| S3 | `primary` = the lean whether offered or not | `test_primary_falls_back_to_the_offered_direction` |
| S4 | The pick-ownership check dropped | `test_every_reason_in_7_3` |
| S5 | The non-max-PF draft-order check dropped from the projected pick | `test_projected_pick_hidden_for_a_non_max_pf_draft_order`, `test_options_follow_the_served_blocks_and_flags` |
| S6 | Band and primary computed for an unusable forecast that has figures | `test_every_unusable_forecast_state` |
| S7 | Block composed with `league.direction_card` off | `test_flag_off_read_is_byte_identical` |
| S8 | `direction_card_shown` left out of `NON_INTENT_EVENTS` | `test_only_the_impression_is_non_intent`; check-direction-card J7 |
| S9 | The "owned by" line dropped | check-direction-card D1, D2, D4 |
| S10 | The sheet opens without `league.direction_pages` | check-direction-sheet S-2f |
| S11 | `feature_off` rows listed in the sheet | check-direction-sheet S-6e |
| S12 | The scrim no longer closes the sheet | check-direction-sheet S-7d |
| S13 | `direction_card_shown` on every render | check-direction-card J1 |
| S14 | The pages ignore the server's `options` | check-direction-pages D12, D13, D15 |
| S15 | The playoff page logs its body under Standings | check-direction-pages G10 |
| S16 | The card hides the pick above 99% (classifies on the device) | check-direction-card I1, I5. **First run: passed** (the I1 regex looked only for `playoff_probability` comparisons); I1 was widened to any probability comparison and I5 added (render the pick at eight chances), commit `496409f4`, then red |
| S17 | A sheet row taps without closing the sheet | check-direction-sheet S-7b |
| S18 | `league.direction_card` dropped from `FLAG_KEYS` | `test_flags_ship_off_and_reach_the_app` |
| S19 | `config/features.json` sets `league.direction_view_sheet` true | `test_flags_ship_off_and_reach_the_app`, `test_release_flags_mirror_features_json` |
| S20 | A backend module names `"league.direction_view_sheet"` | `test_no_backend_code_reads_the_sheet_flag` (first written as a bare substring test, it also caught the taxonomy's comment; narrowed to quoted literals, commit `fb05bb9c`, then re-sabotaged red) |

## 8. The half sheet build: code walk

### 8.1 The server block (§7)

| Step | Where |
|---|---|
| Composed after `max_pf_moves` and `playoff_targets`, only while `league.direction_card` is on | `backend/league_projections/api.py:235-236` |
| Never raises; reads the saved outlook, the stored draft order and the settings; passes the two served blocks and their flags | `api.py:142-158` (`direction_block`) |
| Settings: both keys, 0 < min < max < 1, booleans refused | `backend/league_projections/team_direction.py:35-51` |
| Band, lean | `team_direction.py:54-71` |
| Options and their reason order | `team_direction.py:74-120` |
| Projected pick: `compact` → `slot_ranks` → `slot_suffix`; null for `reverse_standings` / `lottery_or_other` | `team_direction.py:123-138` |
| Figures from any saved run holding the team; `unusable_reason`, then `team_not_found`; band and primary only when ready | `team_direction.py:141-184` |
| Nothing saved: the stored `result_json` is unchanged after a read | `backend/tests/test_team_direction_read.py::test_ready_block_on_the_read` |

### 8.2 The card (§4)

| Step | Where |
|---|---|
| Flags read; the sheet also needs the pages flag | `mobile/src/components/home/HomePlayoffBanner.tsx:54-66` |
| The block honoured only at version 1 with the flag on (H-12) | `mobile/src/utils/directionCard.ts:28-33` |
| Pick figure: the server's label, "owned by", hidden without a percentage | `directionCard.ts:45-52`; `HomePlayoffBanner.tsx:69` |
| `direction_card_shown` once per mount, host screen | `HomePlayoffBanner.tsx:71-76` |
| Two figures, info beside the percentage, "View" last; today's row JSX untouched in the other branch | `HomePlayoffBanner.tsx:98-133`; today's row `:135-156` |
| Projected-pick sentence in the explanation | `HomePlayoffBanner.tsx:161` |
| Hosts: Home `screen="Home"`, League Rankings `screen={route.name}`; both track `home_tile_tapped {tile, via}` then navigate | `mobile/src/components/home/HomeHub.tsx:178-182`, `:391`; `mobile/src/screens/LeagueSummaryScreen.tsx:621-625`, `:1884` |

### 8.3 The sheet (§5.6)

| Requirement | Where |
|---|---|
| S-2, S-10: "View" opens it whenever the card holds a block and the sheet is on | `directionCard.ts:56-58`; `HomePlayoffBanner.tsx:90-96` |
| S-3 to S-6: rows from the block's options only | `directionCard.ts:80-110` |
| S-7: row (`onChoose` closes first), scrim, drag, Android back, VoiceOver escape | `HomePlayoffBanner.tsx:92-95`; `mobile/src/components/home/DirectionSheet.tsx:47`, `:65-70`, `:82-86` |
| S-8: Modal, fade under Reduce Motion, safe area, modal region, focus to the first row, 44pt rows | `DirectionSheet.tsx:72-79`, `:82-104`, `:121` |
| S-9: reads nothing (props only) | `DirectionSheet.tsx` (no query, session, flag or navigation import) |

### 8.4 Pages and events (§9)

| Step | Where |
|---|---|
| `offered` reads `team_direction.options` when the block is present | `mobile/src/utils/directionPages.ts:108-119` |
| `source` param on both routes; entry points set it | `mobile/src/navigation/RootNav.tsx:171-172`; `mobile/src/screens/StandingsScreen.tsx:89-90`; `DirectionPage.tsx:149`; `directionCard.ts:117-125` |
| `direction_page_opened` once per focus | `mobile/src/components/DirectionPage.tsx:88-98`; `directionPages.ts:155-169` |
| Bodies log under the page's route name | `DirectionPage.tsx:137`, `:139`; `MaxPfMovesSection.tsx` / `PlayoffTargetsSection.tsx` `screen = SCREEN`; `utils/maxPfMoves.ts` / `utils/playoffTargets.ts` `deps.screen ?? SCREEN` |
| Registration | `backend/analytics_taxonomy.py` (`ALLOWED_CLIENT_EVENTS`, `CLIENT_EVENT_PROPS`), `backend/analytics_queries.py` (`NON_INTENT_EVENTS`: `direction_card_shown`) |

## 9. The half sheet build: manual TestFlight checklist

For the operator, on a TestFlight build containing this branch, with a backend deployed from it. Turn
on, for the test account: `league.direction_pages`, `league.direction_card`, and (from step 6)
`league.direction_view_sheet`; `league.max_pf_moves` is already on; `league.playoff_targets` for the
playoff row. Use a Sleeper league in season, before its trade deadline, with a weekly forecast saved
after `league.playoff_targets` was turned on.

| # | Do | Expect |
|---|---|---|
| 1 | All three new flags **off**: open Home | The playoff row is exactly as before: "Playoff chance", the percentage, ⓘ, "View ›"; "View" opens Standings |
| 2 | Turn on `league.direction_card` only (sheet off); reload Home | Two figures: "Playoff chance 62.4%" with ⓘ, and "Projected pick 1.0X". No buttons. "View ›" and the percentage both open Standings |
| 3 | Open Standings, your own team, Max PF moves / Improve Draft Pick | The page's "Projected pick" equals the card's figure |
| 4 | Tap ⓘ on the card | The explanation ends with "Projected pick is where your own first-round pick lands if the season follows the forecast." |
| 5 | A league where another team owns your first | The pick still shows, with "owned by [team]" under it |
| 6 | A league whose draft order you answered "reverse standings" or "lottery" (Max PF moves' question) | No projected pick; the playoff chance alone |
| 7 | Turn on `league.direction_view_sheet`; tap the percentage | Standings opens directly |
| 8 | Tap "View ›" | A half sheet slides up: "View projected standings", "Improve Playoff Chances", "Improve Draft Pick", in that order |
| 9 | Close it four ways: tap above it, drag it down, (Android) back, and VoiceOver's two-finger scrub | It closes each time; nothing else happens |
| 10 | Tap "Improve Draft Pick" (a team at or under 45%, own pick) | The sheet closes and Improve Draft Pick opens; back returns to Home |
| 11 | A team that has clinched, or with `league.playoff_targets` off | Clinched: "Improve Playoff Chances" greyed with "You have clinched a playoff spot."; flag off: that row is absent |
| 12 | A low team (under 35%), a middle team (35-65%) and a high team (65% and up) | The sheet has the same three rows in the same order for all three; only the disabled lines differ |
| 13 | A stale forecast (after the weekly update is due) | The card shows both figures with "last saved"; the sheet opens with the two Improve rows disabled ("Not available until the next forecast.") |
| 14 | League Rankings (League tab) | The same card and the same sheet |
| 15 | Switch league in the header on Home | The card reloads for the new league; no figure from the previous league stays |
| 16 | Largest text size | The two figures stack; "View ›" stays on the right; every sheet row is still tappable |
| 17 | VoiceOver on the card and the sheet | "View" reads "Playoff options, button"; on open, focus lands on "View projected standings"; a disabled row reads its line and "dimmed" |
| 18 | Turn `league.direction_card` off again | Back to item 1's row, with the sheet flag still on |

Regressions this is built to catch: the row changing with the flags off (1, 18), a pick that does not
match the page (3), the percentage no longer opening Standings (7), a sheet that will not close (9),
rows in a different order for some teams (12), and the card or sheet missing on League Rankings (14).
Not checked here and worth a look on the device: whether the 48pt drag threshold feels right.

