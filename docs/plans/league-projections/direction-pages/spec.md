# Improve pages, the Home playoff card and its call to action: specification

**Date:** 2026-11-14 · **Entry point:** direct operator ask · **Status:** approved by the
operator 2026-11-14 (D-265) with one change: the half sheet replaces the card's buttons.
Nothing here is built. Written against `origin/main` `f0ab507b` and the unmerged
branch `feat/playoff-targets` (D-264).

The operator asked for three things:

1. A dedicated page for each version of the feature.
2. The projected playoff odds placement on Home shows playoff odds and projected pick.
3. Logic that picks a button, "Improve Playoff Chances" or "Improve Draft Pick", linking to
   the two pages. Test a version that shows both buttons to teams in the middle, and a
   variation where "View" opens a half sheet with three options.

Eight choices in this spec were the operator's. All eight are answered in
[§11](#11-operator-decisions): seven as recommended and one changed (#5). The requirements
below are written to those answers.

- [1. Terms](#1-terms)
- [2. What exists today](#2-what-exists-today)
- [3. Part 1: the two pages](#3-part-1-the-two-pages)
- [4. Part 2: the Home playoff card](#4-part-2-the-home-playoff-card)
- [5. Part 3: the call to action](#5-part-3-the-call-to-action)
- [6. The test](#6-the-test)
- [7. Wire contract: `team_direction`](#7-wire-contract-team_direction)
- [8. Flags and settings](#8-flags-and-settings)
- [9. Analytics](#9-analytics)
- [10. Evidence, docs and build order](#10-evidence-docs-and-build-order)
- [11. Operator decisions](#11-operator-decisions)
- [12. Out of scope](#12-out-of-scope)

## 1. Terms

| Term | Meaning |
|---|---|
| Draft-pick feature | Max PF moves (D-258 to D-263, flag `league.max_pf_moves`, on). Players on your roster whose trade lowers your max PF the most, with your pick before and after |
| Playoff feature | Playoff targets (D-264, flag `league.playoff_targets`, built on `feat/playoff-targets`, not merged, off). Players on selling teams whose acquisition raises your playoff chance the most |
| Playoff page | The new dedicated page for the playoff feature, titled "Improve Playoff Chances" |
| Draft-pick page | The new dedicated page for the draft-pick feature, titled "Improve Draft Pick" |
| The card | The playoff row on Home (`HomePlayoffBanner`). League Rankings mounts the same component |
| Projected pick | The D-257 label for your own next-year 1st, for example "1.04": your team's rank from 1 to N when the forecast orders every team by expected draft slot |
| Middle | A playoff chance of at least 35% and under 65% ([§5.2](#52-the-band)) |

## 2. What exists today

| Piece | Where | Behaviour |
|---|---|---|
| Home playoff row | `mobile/src/components/home/HomePlayoffBanner.tsx`, mounted at `HomeHub.tsx:364` and `LeagueSummaryScreen.tsx:1764` | One 40pt row: "Playoff chance", the percentage, an info toggle, "View ›". The percentage and "View" both open Standings. A second row, "Consider [outlook] · Review outlook", shows when the server's suggestion differs from the saved outlook. No projected pick and no trade action |
| Row logic | `mobile/src/utils/homePlayoffBanner.ts` | Reads the saved forecast only. Never classifies a probability on the device |
| Draft-pick feature | `MaxPfMovesBody` in `mobile/src/components/MaxPfMovesSection.tsx:42`, mounted by `LeagueProjectionDetail.tsx` | A section inside your own open team card on Standings. Starts open when your playoff chance is 45% or lower, or your saved outlook is Rebuilding or Tanking |
| Playoff feature | `PlayoffTargetsBody` in `PlayoffTargetsSection.tsx:35` (branch `feat/playoff-targets`) | A fifth section on the same card. Starts open in exactly the opposite case |
| Forecast read | `GET /api/leagues/<league_id>/projection-runs/latest` | Carries `max_pf_moves`, and `playoff_targets` once D-264 merges, as top-level blocks with a server-decided `state` |
| Projected pick label | `pick_projection.slot_ranks` (`backend/pick_projection.py:247`), served today only as `max_pf_moves.baseline.label` | Not on the forecast read outside the draft-pick block |
| Standings route | `RootNav.tsx:949`, deep link `app/league/standings` (`deepLinks.ts:127`) | A root-stack push with its own feedback button |
| Experiments | `backend/experiments.py`, flag `experiments.engine` (on) | A running experiment delivers per-user flag values, which the app merges over the global flags (`mobile/src/api/flags.ts:72-94`) |

Both features sit three taps deep today: Home, Standings, your own team, the section. Nothing
on Home leads to either.

## 3. Part 1: the two pages

### 3.1 Requirements

| Id | Requirement |
|---|---|
| P-1 | Two new root-stack routes: `ImprovePlayoffChances` and `ImproveDraftPick`. Registered unconditionally, as Standings is. The flags gate the entry points, not the routes |
| P-2 | Each page uses the Standings header pattern: league selector header, title, back control. Titles: "Improve Playoff Chances" and "Improve Draft Pick" |
| P-3 | Each page mounts its own feedback button, as every root-stack push must (root `CLAUDE.md`, #188) |
| P-4 | Each page reads the saved forecast on the query key Standings and Home already use, `['league-projection-batch', userId, leagueId]`. No new request. Opening a page never starts a forecast |
| P-5 | The page body is the existing component: `MaxPfMovesBody` on the draft-pick page, `PlayoffTargetsBody` on the playoff page. Its only change is one new prop that skips the collapsed step (P-7). The page adds no list, number or copy of its own for the rows. A guard test fails if a page renders rows any other way |
| P-6 | Above the list, a two-figure summary: playoff chance and projected pick, read from the same block as the list (`baseline`), printed by the existing formatters (`utils/playoffOdds`, the D-257 label) |
| P-7 | The list is open on arrival. The Standings default-open rule and the "Show moves" step do not apply: the user chose to come here. The "Show anyway" step for a pick owned by another team stays on the draft-pick page, because the advice would help that team |
| P-8 | Every server state renders its existing one-line message. No state leaves a blank page |
| P-9 | "Find trades for [player]" works as it does today: the draft-pick page pins the player on the give side, the playoff page on the receive side. The `finder_target_pinned` sources stay `maxpf_moves` and `playoff_targets` |
| P-10 | Under the list, two links: "View projected standings" (opens Standings) and a link to the other page ("Improve Draft Pick instead" or "Improve Playoff Chances instead"). The link to the other page shows only when that page has something to offer ([§5.3](#53-when-a-direction-is-offered)) |
| P-11 | Deep links: `app/league/improve-playoffs` and `app/league/improve-pick` |
| P-12 | With no league, a non-Sleeper league, or the feature's flag off, the page shows the existing "unavailable" card. It can be reached then only by a deep link |
| P-13 | On Standings, with `league.direction_pages` on, each of the two sections on your own team card becomes a single row that opens its page: "Max PF moves ›" and "Playoff targets ›". With the flag off, Standings is unchanged |
| P-14 | Switching league while a page is open reloads it for the new league, with no number from the previous league left on screen |

### 3.2 What the pages do not change

No server change, no schema change and no change to either feature's numbers, states or
copy. Installed builds without the pages keep the sections on Standings.

## 4. Part 2: the Home playoff card

### 4.1 Layout

```
┌───────────────────────────────────────────────┐
│ Playoff chance      Projected pick     View › │
│ 62.4%  ⓘ            1.08                      │
│ ┌───────────────────────────┐                 │
│ │  Improve Playoff Chances  │                 │
│ └───────────────────────────┘                 │
├───────────────────────────────────────────────┤
│ Consider All-in                Review outlook │
└───────────────────────────────────────────────┘
```

### 4.2 Requirements

| Id | Requirement |
|---|---|
| H-1 | The card shows two figures side by side: "Playoff chance" and "Projected pick" |
| H-2 | Playoff chance is unchanged: same source, same formatter, same "last saved" note, same status text when there is no estimate |
| H-3 | Projected pick is the D-257 label for your own next-year 1st from your saved forecast, the number the draft-pick page shows as "today". The server sends it; the app never computes it |
| H-4 | When another team owns that pick, the figure still shows and a second line reads "owned by [team]" |
| H-5 | When the league's stored draft-order answer is reverse standings or lottery, the projected pick is hidden. The forecast orders picks by max PF, so the figure would be wrong for that league |
| H-6 | When the forecast is not current, the projected pick keeps its last saved value under the same "last saved" note as the percentage. With no saved forecast, the cell is hidden |
| H-7 | "View ›", the info toggle and its explanation stay. The explanation gains one sentence: "Projected pick is where your own first-round pick lands if the season follows the forecast." |
| H-8 | The button row sits under the figures and shows zero, one or two buttons ([§5](#5-part-3-the-call-to-action)). With none, the row is not rendered and the card is two lines shorter. In the half-sheet version there is never a button row ([§5.6](#56-the-half-sheet)) |
| H-9 | The "Consider [outlook] · Review outlook" row is unchanged and stays last |
| H-10 | At large text sizes the two figures stack, and two buttons stack. Every control keeps a 44pt target |
| H-11 | League Rankings shows the same card, because it mounts the same component. Events carry the host screen |
| H-12 | With `league.direction_card` off, or on a server that does not send the block, the card is today's row, unchanged |

## 5. Part 3: the call to action

### 5.1 Principle

The server decides, and the app shows what it is given. This is the rule for every forecast
surface: the device never classifies a probability. The decision is composed when the forecast
is read, from figures the saved run already holds. The weekly job does no extra work.

### 5.2 The band

On the unrounded playoff chance *p*:

| Band | Rule |
|---|---|
| `low` | *p* < 0.35 |
| `middle` | 0.35 ≤ *p* < 0.65 |
| `high` | *p* ≥ 0.65 |

These are the cuts the first Home playoff banner used on 2026-11-07 to choose between
buying, selling and both. They are settings, not code ([§8](#8-flags-and-settings)).

### 5.3 When a direction is offered

A direction is offered only when its page has at least one move worth showing:

| Direction | Offered when |
|---|---|
| Draft pick | `league.max_pf_moves` is on, the block's `state` is `ready`, and you own your own pick |
| Playoffs | `league.playoff_targets` is on, and the block's `state` is `ready` |

`ready` means at least one row clears that feature's own threshold. So neither button shows
after the trade deadline or when the season is over. The draft-pick button never shows for a
team that almost never misses the playoffs, or in a league that does not draft by max PF. The
playoff button never shows for a team that has clinched, is eliminated, is at 99% or more, or
has no selling teams to buy from.

### 5.4 Which direction leads

```
lean = draft pick   if p ≤ 0.45, or the saved outlook is Rebuilding or Tanking
       playoffs     otherwise
```

This is the rule that already decides which of the two Standings sections starts open, so the
button and the page it leads to never disagree. Then:

```
primary = lean, if it is offered
          the other direction, if that one is offered
          none
```

When the forecast is not usable (not current, incomplete, from an older model, failed, or the
team cannot be matched), there is no primary and no button. The figures still show as "last
saved".

### 5.5 What the card shows

| Version | Team | Buttons |
|---|---|---|
| Single (base) | Any | The primary direction only |
| Both for the middle | Band is `middle` and both directions are offered | Both, primary first |
| Both for the middle | Any other | The primary direction only |
| Half sheet | Any | None. The choices are in the sheet ([§5.6](#56-the-half-sheet)) |

Labels: "Improve Playoff Chances" and "Improve Draft Pick". Each opens its page.

Worked examples, with both directions offered unless the row says otherwise:

| Team | Single | Both for the middle |
|---|---|---|
| 20% chance | Improve Draft Pick | Improve Draft Pick |
| 50% chance, no saved outlook | Improve Playoff Chances | Improve Playoff Chances, Improve Draft Pick |
| 50% chance, saved outlook Rebuilding | Improve Draft Pick | Improve Draft Pick, Improve Playoff Chances |
| 40% chance, no saved outlook | Improve Draft Pick | Improve Draft Pick, Improve Playoff Chances |
| 80% chance | Improve Playoff Chances | Improve Playoff Chances |
| 50% chance, pick owned by another team | Improve Playoff Chances | Improve Playoff Chances |

### 5.6 The half sheet

A third version, which replaces the buttons (operator, 2026-11-14). The card shows the two
figures and "View ›" and nothing else; the choices live in the sheet.

| Id | Requirement |
|---|---|
| S-1 | With the sheet on, the card has no button row, for any team in any band. `league.direction_both_middle` has no effect |
| S-2 | "View ›" opens a half sheet instead of going to Standings. Tapping the percentage still opens Standings directly |
| S-3 | The sheet lists three rows in this order: "View projected standings", "Improve Playoff Chances", "Improve Draft Pick". The order is the same for every team |
| S-4 | "View projected standings" is always enabled and opens Standings |
| S-5 | A direction that is offered ([§5.3](#53-when-a-direction-is-offered)) is enabled and opens its page |
| S-6 | A direction that is not offered is shown disabled with one line saying why, from the server's reason ([§7.3](#73-reasons)). A direction whose feature flag is off is not listed |
| S-7 | The sheet closes on a row tap, a tap outside it, a downward drag, or the system back gesture. Closing without choosing changes nothing |
| S-8 | The sheet follows the existing sheet pattern (`AnchorSheet`): a modal over a scrim, safe-area padding, reduced-motion respected, focus moved into the sheet for VoiceOver, each row a 44pt target |
| S-9 | The sheet reads no data of its own. It renders the block the card already holds |
| S-10 | "View ›" opens the sheet whenever the card has a `team_direction` block, including when neither direction is offered. The sheet then holds "View projected standings" and the disabled rows |

## 6. The test

### 6.1 Cells

Three cells:

| Cell | Buttons on the card | "View ›" |
|---|---|---|
| A (base) | One: the primary direction | Opens Standings |
| B | Both for the middle, otherwise one | Opens Standings |
| C | None | Opens the half sheet |

A and B differ only for teams in the middle with both directions offered; outside the middle
the two are the same screen. C differs from both for every team.

### 6.2 What is measured

| Measure | Definition |
|---|---|
| Primary | Share of users shown the card in a week who tap "Find trades for [player]" on either page in that week (`finder_target_pinned`, source `maxpf_moves` or `playoff_targets`) |
| Secondary | Button tap rate (A, B) and sheet row tap rate (C); page opens per user; for the middle band, which direction is chosen; trades generated |
| Guard | Standings opens per user (the sheet adds a tap before Standings), plus the five standing guardrails every experiment carries |

### 6.3 How it runs

Each switch is a flag. Before there are enough users, the operator turns each cell on for
their own account and judges it by use. Once there are, the same two flags are delivered by
one experiment through the existing engine: account as the unit, three variants, each variant
carrying the two flag values. The app records the exposure itself the first time it reads a
delivered flag.

Two facts limit the test and are stated here so they are not found later:

- **Users.** The runbook's last count (2026-10-05) is under ten users, all on TestFlight.
  Only Sleeper leagues with a current forecast see the card, and only teams in the middle
  see a difference between A and B. No split of that population can show a real difference.
  Until launch brings users, the test is the operator's own judgement of three screens.
- **The metric.** The engine's metric list (`backend/experiments.py:65`) has no
  click-through measure. Reading this test from the engine needs one added. Without it, the
  result is read from the events in [§9](#9-analytics) by query. The engine's design
  calculator (`experiments.py:731`) gives the users needed once a base rate exists.

## 7. Wire contract: `team_direction`

### 7.1 Where it travels

A new top-level key on `GET /api/leagues/<league_id>/projection-runs/latest`, present only
while `league.direction_card` is on. Composed on read. Nothing is saved, no route is added,
and with the flag off the response is byte-identical to today's.

### 7.2 Shape

| Field | Type | Null? | Meaning |
|---|---|---|---|
| `version` | `1` | no | An app that does not know the version shows today's row |
| `state` | `'ready' \| 'unavailable'` | no | `ready`: the forecast is current, complete and from the current model, by the one existing definition (`recommendation.unusable_reason`) |
| `reason` | `string` | yes | Only with `unavailable`. The existing vocabulary of `unusable_reason`. An open set |
| `captured_at` | ISO-8601 string | yes | The forecast's capture time. Null with no saved run |
| `playoff_probability` | `number` | yes | Your team's playoff chance, 0 to 1, unrounded. Null when your team is not in a saved run |
| `playoff_clinched`, `playoff_eliminated` | `boolean` | no | The D-262 proof. False when not proven |
| `projected_pick` | `ProjectedPick` | yes | Null with no saved run, when your team is not in it, or when the stored draft-order answer is `reverse_standings` or `lottery_or_other`. Served for a run that is not current, so the card can show it as "last saved" |
| `band` | `'low' \| 'middle' \| 'high'` | yes | [§5.2](#52-the-band). Null unless `state` is `ready` |
| `primary` | `'playoffs' \| 'draft_pick'` | yes | [§5.4](#54-which-direction-leads). Null when neither direction is offered or `state` is `unavailable` |
| `options` | `{playoffs: Option, draft_pick: Option}` | no | Whether each direction is offered, and why not |

`ProjectedPick`: `{label: string, slot: number, owns_own_pick: boolean, owner_name: string}`.
`label` and `slot` come from `pick_projection.slot_ranks` over this run, the computation
behind `max_pf_moves.baseline.label`. A guard test pins the two to the same value.

`Option`: `{offered: boolean, reason: string | null}`. `reason` is null when `offered` is true.

### 7.3 Reasons

| `reason` | Direction | Disabled-row line in the sheet |
|---|---|---|
| `feature_off` | either | (row not listed) |
| `unavailable` | either | "Not available until the next forecast." |
| `season_over` | either | "The regular season is over." |
| `after_trade_deadline` | either | "The trade deadline has passed." |
| `none_found` | either | "No single move changes this right now." |
| `pick_owned_elsewhere` | draft pick | "[Team] owns your first-round pick." |
| `no_miss` | draft pick | "Your team almost never misses the playoffs." |
| `draft_order_not_maxpf` | draft pick | "Your league does not draft by max PF." |
| `clinched` | playoffs | "You have clinched a playoff spot." |
| `eliminated` | playoffs | "You are eliminated from the playoffs." |
| `near_certain` | playoffs | "Your playoff chance is already 99% or higher." |
| `no_sellers` | playoffs | "No team in your league is selling right now." |

An unknown reason uses "Not available right now."

## 8. Flags and settings

| Flag | Default | Gates | Needs |
|---|---|---|---|
| `league.direction_pages` | false | The Standings link rows and every entry point to the two pages | `league.projections` |
| `league.direction_card` | false | The `team_direction` block, the projected pick on the card, and the button | `league.direction_pages` |
| `league.direction_both_middle` | false | Cell B: both buttons for the middle. Ignored while the sheet flag is on | `league.direction_card` |
| `league.direction_view_sheet` | false | Cell C: the half sheet on "View", and no buttons on the card | `league.direction_card` |

Each is registered in `backend/feature_flags.py`, `config/features.json` with a comment line,
`docs/config-reference.md`, and the three mirrored flag fixtures.

Settings, in `config/league_projections.json` under a new `team_direction` key:
`middle_min` 0.35 and `middle_max` 0.65, validated as 0 < min < max < 1. The 45% cut is the
existing fixed `REBUILDING_MAX` and is not a new setting.

Turning off: each flag is a switch with no stored state behind it. Off returns the surface to
what it was. An experiment is stopped with one call.

The playoff button cannot show until D-264 is merged and `league.playoff_targets` is on.
Until then the card can ship with the draft-pick direction alone, and cell B has nothing
to show.

## 9. Analytics

No player id or name in any property. All emitted by the app; each new name and property is
registered in `backend/analytics_taxonomy.py`, and impressions are added to
`analytics_queries.NON_INTENT_EVENTS`, in the same commit as the emitter.

| Event | Fires when | Properties | Class |
|---|---|---|---|
| `direction_card_shown` (new) | The card renders with a `team_direction` block, once per mount | `band` → `low` \| `middle` \| `high` \| `none`; `primary` → `playoffs` \| `draft_pick` \| `none`; `shown` → `playoffs` \| `draft_pick` \| `both` \| `none` (the buttons on the card; always `none` in cell C); `sheet` → boolean; `pick_shown` → boolean | Impression |
| `home_tile_tapped` (existing) | A button on the card or a row in the sheet is tapped | `tile` gains `improve_playoffs`, `improve_pick`, `playoff_options` (the tap that opens the sheet); new property `via` → `card` \| `sheet`. `standings` keeps its meaning | Intent |
| `direction_page_opened` (new) | A page gains focus | `page` → `playoffs` \| `draft_pick`; `source` → `card` \| `sheet` \| `standings` \| `other_page` \| `deep_link`; `state` → the feature block's server `state` | Intent |
| `maxpf_moves_viewed`, `playoff_targets_viewed`, `maxpf_move_expanded`, `playoff_target_expanded`, `finder_target_pinned` (existing) | As today, with the page's route name as the screen | Unchanged | Unchanged |
| `experiment_exposed` (existing) | The app first reads a flag an experiment delivered | Unchanged | Unchanged |

A sheet closed without a choice is the count of `playoff_options` taps minus the sheet
choices that follow; it needs no event of its own.

## 10. Evidence, docs and build order

### 10.1 Evidence

| Kind | What it proves |
|---|---|
| Backend tests | The band at 0.35 and 0.65 exactly; the lean at 0.45 exactly and for each saved outlook; the fallback when the lean is not offered; every reason in §7.3; every unusable forecast state; the projected pick equals `max_pf_moves.baseline.label`; the pick is null for a non-max-PF draft order; flag off is byte-identical. Each rule has a named change that makes its test fail |
| `mobile/tests/check-direction-card.js` | The card shows what the block says and decides nothing itself; zero, one and two buttons; the stacked layout; today's row when the flag is off or the block is absent; both hosts |
| `mobile/tests/check-direction-pages.js` | Both routes registered; each page mounts the existing body component and no second list; the feedback button; deep links; league switch |
| `mobile/tests/check-direction-sheet.js` | No button row while the sheet is on; row order; enabled, disabled and unlisted rows; every way of closing; the percentage still opens Standings |
| Code walk | File and line for each requirement that a test cannot pin |
| TestFlight checklist | The three cells on a device, with large text and VoiceOver; a low, a middle and a high team; a pick owned by another team; a league switch. The only runtime evidence (D-056: no simulator) |

### 10.2 Docs

| Doc | Change |
|---|---|
| `docs/api-reference.md` | The `team_direction` block |
| `docs/config-reference.md` | Four flags, two settings |
| `docs/architecture.md` | Two screens; the card's new block |
| `docs/glossary.md` | "Projected pick", "middle" |
| `docs/cross-client-invariants.md` | The band cuts, as server-owned |
| `mobile/src/screens/CLAUDE.md`, `components/CLAUDE.md` | The two screens, the card, the sheet |
| `living-memory/DECISIONS.md` | One entry once §11 is answered |
| `docs/data-dictionary.md`, `living-memory/HLD.md`, `LLD.md` | No change: nothing is stored and no convention moves |

### 10.3 Build order

| Step | Contains | Depends on |
|---|---|---|
| 1 | The two pages and the Standings link rows (app only) | D-264 merged for the playoff page; the draft-pick page can go first |
| 2 | The `team_direction` block, the projected pick on the card, the single button | Step 1 |
| 3 | Cell B, the half sheet (cell C), the events, the experiment definition | Step 2 |

Each step is its own pull request, ships with its flag off, and needs an app build.

## 11. Operator decisions

Answered by the operator on 2026-11-14 (D-265): "I agree with all recs but one. The sheet
removes the buttons."

| # | Question | Decision | Why |
|---|---|---|---|
| 1 | What is "the middle"? | 35% up to 65% | The cuts the first Home banner used. Centred on your 50% line for a selling team |
| 2 | In the single version, which button does a middle team get? | The rule in §5.4: draft pick at 45% or lower, or with a saved outlook of Rebuilding or Tanking; otherwise playoffs | It is the rule that already opens one Standings section and closes the other. The alternative is your 50% line, which would disagree with the page for teams between 45% and 50% |
| 3 | Does a saved outlook of Contender or All-in override a low playoff chance? | No | Matches the existing rule. The "Consider [outlook]" row already tells that user their outlook and their odds disagree |
| 4 | Show a button when the page has no move that clears its threshold? | No | A button that says "Improve" should lead to something that does |
| 5 | In the sheet variation, do the card's buttons stay? | **No. The sheet replaces the buttons** (the operator's change; the recommendation was to keep them) | The test is then three cells, not four: with no buttons on the card, single and both are the same screen |
| 6 | Do the Standings sections become links to the pages, or stay in full? | Links | One home for each list. Two full copies doubles what can drift and splits the view counts |
| 7 | Does League Rankings get the new card too? | Yes | It mounts the same component. Keeping it on the old row means a second component |
| 8 | Button labels | "Improve Playoff Chances" and "Improve Draft Pick" | Your message had "Improve Draft pick" and "improve Draft pick"; one capitalisation is needed |

## 12. Out of scope

- Any change to how either feature computes or words its rows.
- A projected pick for a league that does not draft by max PF.
- The web client. The web forecast page (`web/js/league-projections.js`) shows the outlook
  suggestion but neither feature, and it has no Home card.
- Changing the saved outlook from the card. "Review outlook" keeps that job.
- Push notifications or other prompts toward either page.
