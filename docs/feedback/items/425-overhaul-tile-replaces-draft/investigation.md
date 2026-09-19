# G-425 (#425 + #426) — investigation: what the operator sees, and what "the draft button" is

**Date:** 2026-09-08 · **Reporter:** mattmurf77, app 1.17.2 build 154, screen TradesHome · **Path:** polish (mobile) · **Planner:** G-425 planner (read-only on code; branch `claude/feedback-422-428`)

Reports, verbatim: #425 "The overhaul tile should replace the draft button. Too much content on one page." · #426 "The overhaul button should be a big red button."

## 1. The reporter's cohort decides which "draft button" exists

The Acquire landing renders one of two top rows, chosen by `showInlineHome` (`TradesScreen.tsx:960` = `finderMode === 'guided' && homeInlineVariant !== 'control'`):

| Cohort | Who | Top row | Draft control |
|---|---|---|---|
| `trades_home_inline` **strip** (or canvas) | tester-allowlisted accounts — the operator's account `313560442465169408` is in `config/tester_allowlist.json` (`docs/feedback/items/270-inline-trades-home/status.md:381-382`); the experiment has run at **100% strip since 2026-08-09** and was kept by operator choice (`living-memory/CHANGELOG.md:1201-1203`) | `TradeHomeUtilityRow` (`TradesScreen.tsx:6795-6821`) | the **leading 64pt icon button "Draft"**, testID `trades.home-utility.draft`, flag glyph (`TradeHomeUtilityRow.tsx:74-88`, `minHeight: 64` at `:150`); it exists only because TradesScreen passes `onDraft` at `:6797-6801`, gated on `draft.room` (`config/features.json:213`, **true**) |
| control (every non-allowlisted user) | production users | `TradeFinderModeBar` (`TradesScreen.tsx:6823-6851`) | the leading **"Draft" chip** (`TradeFinderModeBar.tsx:49-60`, `:130`), 36pt pill, created by the `onDraft` pass at `TradesScreen.tsx:6834-6838` |

`finderMode` is `'guided'` for everyone because `trades.finder_hub` is true (`config/features.json:14`) and `TradesHome` mounts with `initialParams {mode:'guided'}` (`TabNav.tsx:456-460`; `TradesScreen.tsx:931-933`).

**Verdict:** the reporter is in the strip cohort, so "the draft button" is the **utility-row Draft cell** (`trades.home-utility.draft`). It is not the mode-bar chip (the reporter never sees the mode bar), not the seasonal bottom-tab **Draft** (`draft.tab`, `config/features.json:228` true; `TabNav.tsx:716-718`, operator decision quoted at `:596-604`), and not the League tab's "Rookie draft" tile (`LeagueScreen.tsx:697-704`). The Draft Room stays reachable through those three plus the `app/league/draft-room` deep link after the cell is removed.

## 2. The landing, top to bottom, as the reporter sees it today

Inside the main `ScrollView` (`styles.scroll` = padding lg, gap lg, `TradesScreen.tsx:9870`), with production flags (`trades.finder_hub`, `calc.inline_home`, `trades.edit_full_sheet`, `trades.sheet_targeting`, `draft.room`, `overhaul.enabled`, `trades.team_review` all true; `trades.presentation_v2`, `receipts.screen` false):

| # | Element | Source | Renders for the reporter? |
|---|---|---|---|
| 1 | `trades.win-now` text link | `:6754-6758` (`trades.win_now` + `outlook.season_projections`, both true) | yes, 44pt |
| 2 | `modeBarWrap` → `TradeHomeUtilityRow` **[Draft \| Free agents \| Manual calc]** | `:6783-6821`; wrapper measured into `modeBarBottom` (`:638`) for the Toast offset (`:6638`) | yes, 64pt row |
| 3 | `OutlookBiasReceipt` / `trades.outlook-fallback` | `:6866-6952`; fallback suppressed by T-1 `canvasHost !== 'flag'` (`:6908`); receipt hidden while `trade.outlook_direction` is false (423 investigation) | no |
| 4 | prefs-changed strip | `:6961` | transient only |
| 5 | `TradingWithStrip` (League / Trading with pills) | `:6991-6998` | yes |
| 6 | IdentityConfirmStrip · NewPartnersBanner · InviteLeaguematesBanner | `:7003-7045` | first-run / conditional |
| 7 | `TeamReviewEntryCard` | `:7047-7056` | yes — collapsed "Team review · done" row after completion (`TeamReviewEntryCard.tsx:98-113`) |
| 8 | **`OverhaulEntryCard`** full card: kicker + 2-line body + ice CTA (≈120pt) | `:7058-7075`; gate `(overhaulOn \|\| !!activeOverhaul) && leagueId` (`:7060`) | yes |
| 9 | page title + sub-route pills | `:7081-7126` | no (`!finderMode` only) |
| 10 | merged trade builder `TradeBuildCanvas` → `InLeagueCalculator` | `canvasHost === 'flag'` (`:6083-6098`) → mount `:7910`, `:8006-8020` | yes |

Two entry surfaces (7, 8) plus a utility row sit between the top of the page and the builder. The card the operator wants moved is #8; the slot he wants it in is the first cell of #2.

The same tree renders on the pushed "Trade ideas" results page (`TradeDeck` pushed with `mode: 'guided'` + `resultsPush`, `:3212-3214`; `TabNav.tsx:470-478`): neither the utility row nor the card reads `isResultsPushed` (`:955`), so both appear there today too.

## 3. What pins the current placement

- `mobile/tests/check-team-overhaul.js` §3a (`:113-126`) asserts `<OverhaulEntryCard` comes **after** `<TeamReviewEntryCard` with no other component between; §3b (`:127-139`) asserts the mount's gate names the flag and the active-overhaul probe; §8 (`:194-208`) requires `overhaul.entry-card` / `overhaul.entry-start` / `overhaul.entry-resume` to appear literally. §3a must be rewritten; §3b and §8 stay as they are.
- `docs/plans/team-overhaul/BUILD-CONTRACT.md` §9 entry row ("Acquire landing card below `TeamReviewEntryCard`") and its guard paragraph; `docs/plans/team-overhaul/mockups/entry-mock-evidence.md:7` (the approved *proposal*: "immediately after the existing Team review entry and before the merged trade builder"). #425 is the operator revising that placement after seeing build 154.
- No test pins `trades.home-utility.draft` or the `onDraft` pass (`git grep` over `mobile/tests`: zero hits).
- Guards that touch the neighbourhood and must stay green: `check-presentation-v2.js` (Today handler at both host sites — the utility row keeps `onTodaysTrade`), `check-receipts.js` §12 (track-record control on the utility row — kept), `check-finder-conditions-reachable.js` §5/§6 (no `onConditions`; the mode bar's `hideTeamAndPlayer` guard — untouched), `check-trades-banner-region.js` §1 (`TradingWithStrip` outside `modeBarWrap` and after `OutlookBiasReceipt` — untouched), `check-team-review.js` §3 (entry is not a mode chip) and §11 (`setHandoff(null)` present), `check-inline-home.js`, `check-calc-merged-layout.js` (calculator files only).

## 4. Colour: why "red" has nowhere to come from

- `design-system.md:20` rule 6: ice is the primary accent; flare "appears ONLY on informational highlights, never on actions". `:66`: "Flare never appears on a button or actionable control's primary affordance." Mirrored in `mobile/src/theme/chalkline.ts:50-56`.
- `design-system.md:73`: `--neg #EF4444` = "Pass/decline, errors, destructive"; `components.md:25` gives the Pass button that vocabulary. A red full-width tile at the top of Acquire would read as an error or a destructive action.
- `design-system.md:23` rule 9: "No new hues."
- `chalkline.ts:45`: ice is rationed to ≤3 per screen. After the change the landing carries at most three ice fills: the hero, the Team review CTA (only while the review is un-completed and un-collapsed), and the builder's Find a Trade cell.

So the only sanctioned bold *action* fill is ice. A true red action tile is a design-system addition (a new accent token + ADR-005 amendment), which is the operator's call, not the builder's — see PRD open question Q1.

## 5. Concurrency and the FAB rule

- G-423 owns `TradesScreen.tsx` only at the `OUTLOOK_FALLBACK_LABEL` alias (`:9837-9849`) plus `TeamReviewEntryCard.tsx`, `InLeagueCalculator.tsx`, `OutlookBiasReceipt.tsx`, `TeamReviewScreen.tsx`. G-425's TradesScreen hunks are `:6783-6821` and `:7058-7075` — more than 2,700 lines away; G-425 does not touch any G-423 file.
- TradesHome is a tab-stack screen (`TabNav.tsx:456-460`), covered by the single global `FeedbackFAB` mount (`RootNav.tsx:624`). No local FAB; the hero is top-anchored so it never sits under the bottom-right FAB and needs no `setPinnedBottomBarHeight`.
- Analytics: `overhaul_started` is registered with props `league_id`, `outlook`, `entry` (`backend/analytics_taxonomy.py:1407`) and fires from the host with `entry: 'trades_home_card'` (`TradesScreen.tsx:7066`). The hero is still the trades-home entry; the value is kept so the funnel does not split across builds.
