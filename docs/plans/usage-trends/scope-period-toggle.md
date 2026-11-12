# Feature Scope — Usage Trends: Last week | Last 3 weeks

**Date:** 2026-11-12
**Entry point:** direct ask. Operator feedback on a TestFlight screenshot of Usage Trends (Simple, Snaps, Free agents, Biggest jumps): "Should let users toggle between last week and last three for usage rates".
**Builder:** builder session on `feat/usage-trends-period-toggle` (cut from `origin/main` at `12ac0f1d`)
**Operator sign-off on waivers:** not needed (no waivers)

Parent scopes: [scope.md](scope.md) and [scope-order-toggle.md](scope-order-toggle.md). This change adds a period to the Simple view's two orders. Nothing about **Last week** changes.

---

## 0. What changes, and the decisions it rests on

**Reading of the ask.** A period control in the Simple view, **Last week | Last 3 weeks**. It applies to whichever order is selected (Biggest jumps or Weekly share). Last week is the default and is today's screen, byte for byte: same request, same cache key, same list, same copy. A narrower reading (the period only on Weekly share) was considered; the operator's sentence names "usage rates", and both orders read usage, so the period applies to both. If only Weekly share should get it, hiding the pill under Biggest jumps is a one-line change at `UsageTrendsScreen.tsx:625`.

| Decision | Ruling | Why |
|---|---|---|
| **What "Last 3 weeks" covers** | The **newest three selected weeks** (default window Weeks 6–9 → Weeks 7–9). "Last week" already means the newest *selected* week, so the period follows the same rule. With fewer than three weeks selected (Filters → Weeks → Last 2), the pill is hidden and the list is the one-week reading. | One rule for both periods; a custom week pick still reads honestly because every card and section line names the weeks. |
| **Three-week average** | Played weeks only (the feature's rule): byes and missed games leave the divisor. Count = mean per played game; % of team = total ÷ team total over those games (the existing `avg_share` rule). | Same definitions as the rest of the screen. |
| **Baseline for the three-week jump** | The player's average over **up to three completed weeks right before the period** (Weeks 4–6 for a Weeks 7–9 period), played weeks only. The server reads those weeks even when they are outside the selection (store first, live fetch otherwise, the same path as any week). They are not added to `weeks`, so the card's bars and Raw stats are unchanged. | A one-week baseline (the default window's single earlier week) is too noisy to call a three-week trend. Three before three compares like with like. Early in the season fewer exist (Weeks 2–4 have only Week 1); the section line names whatever weeks were used. |
| **Jump rule** | `avg_share − base_avg_share ≥` the spike margin (15 / 10 / 8 points for snaps / carries / targets), with **at least 2 games** in the period, an **average at or above the weekly volume floor** (20 snaps / 6 carries / 4 targets a game) and **at least 1 baseline game**. Ranked biggest jump first. | The same margins and floors that keep small samples out of the one-week jumps, applied per game. |
| **Fewer than two of the three weeks** | A player with one game in the period is never a jump or back-or-new, and in **both** orders he ranks after everyone with two or more games (no games: last). His card says so: "97% of Jets plays in 1 game, Weeks 7–9". A player with two games is ranked normally and his card says "in 2 games, Weeks 7–9". | One big game would otherwise top a three-week list, which is exactly the one-week noise the operator wants to look past. |
| **"Back or new" under three weeks** | Kept as a section, redefined: **no game in the baseline weeks, then a real role in the period** (2+ games, volume floor). Card: "Averaged 47% of Jets plays over Weeks 7–9, no games in Weeks 4–6". A return from a *short* absence is not its own section any more: his baseline is his pre-injury games, so he is a jump or not on the merits. | "Returned in Week 9" is a one-week event. Over three weeks the useful question is "who had no role before and has one now", and the card states the facts (no games before) instead of guessing injury vs. rookie. |
| **No earlier weeks** (the period starts at the season's first completed week) | No jumps and no back-or-new: one section "All players", sub-line "No earlier weeks to compare with yet. By share of team plays in Weeks 1–3." | Nothing honest to compare against. |
| **Weekly share, Last 3 weeks** | Ordered by the server's `rank_share` (% of team) or `rank_count` (Filters → Count), highest average first, fewer than two games last. Card: "Averaged 47% of Jets plays over Weeks 7–9" / "Averaged 40 snaps a game over Weeks 7–9". | The card states the number the list is ordered by, as Weekly share already does. |
| **Who computes and ranks** | The server (`backend/usage_trends.py` `_period_metric`, `_rank_period`) behind `?period=3`. The client orders by the server's rank and splits runs; it compares no average, share or jump (pinned by checks 1ai and 2e10). Without the parameter the response is byte-identical to before (pinned by hash). | The feature's rule. Builds already in testers' hands send no `period` and get today's bytes. |
| **Raw stats** | **No period control.** Its table already shows every week side by side, and its Tot/Avg column covers the selection; a period there would just hide columns the user can already read. Same reasoning as the order pill. | |
| **Where the control sits** | In the Simple list's header, **in the same row as the order pill, wrapping**: `orderRow` became `flexDirection: row, flexWrap: wrap, gap: space.sm`. On a 375-point phone the two pills don't fit side by side (about 220 + 190 points against 343), so **Last week \| Last 3 weeks** sits on its own line directly under **Biggest jumps \| Weekly share**; on a wider screen they share a line. Same pill construction (`viewPill` / `viewSeg`, `radii.pill`, ice border on the selected segment). | The fixed header (league line, view pill, metric tabs, ownership + Filters) gains nothing; the new pill scrolls away with the list like the order pill. No new colour, no icon, no radius outside the specced pill. |
| **Loading** | Choosing Last 3 weeks sends `period=3` under its own cache key; while that answer loads the screen shows the spinner instead of the one-week list under three-week titles. A server without the reading (a settled answer with no `period`) falls back to the one-week list. Switching back to Last week is instant (its key is cached). | |
| **Players listed** | Unchanged: `_relevant` still decides on the selection. A player with a three-week jump has, by the floors, at least 20 snaps a game (or 6 carries / 4 targets), which keeps his average snap share well over 10% in practice. Recorded here as the one theoretical gap. | Keeps the period response's player set identical to Last week's, so Raw stats never differs. |
| **Feature flag** | **None new.** The control rides `usage_trends.enabled`. The server reading is additive and inert without the parameter; rollback is a client revert, or a one-line server revert that makes `period=3` a 400 (the client then shows the error with Try again; Last week is unaffected). | |

## 1. Analytics scope

- [x] **(b) Existing events cover it** — no new event name.
  - `usage_trends_view_changed` gains **`period`** ∈ `week | three_weeks`. It fires when the period pill changes and is carried on every other view change.
  - `usage_trends_action` gains **`period`**, so an Add / Trade / Re-rank is attributed to the period the user was reading.
  - Classes unchanged (view_changed NON_INTENT, action INTENT). Registered in `backend/analytics_taxonomy.py` `CLIENT_EVENT_PROPS` in the same commit as the emitter. Tracking-plan addendum: [2026-11-12-usage-trends-period.md](../../business/analytics/2026-11-12-usage-trends-period.md).
  - Question: does anyone read the longer reading, and does it produce Adds / Trades?

## 2. Schema & flag scope

- New/changed tables or columns: **none**. The baseline weeks come from the existing weekly store.
- New/changed feature flags: **none** (rides `usage_trends.enabled`, see §0).
- New env vars / `model_config` keys: **none**. Constants `PERIOD_WEEKS = 3`, `MIN_PERIOD_GAMES = 2` in `backend/usage_trends.py`.
- **API contract:** `GET /api/usage-trends` gains optional `period=3` (400 `invalid_period` for any other value). With it, top-level `period {weeks, base_weeks}` and a `period` block on every metric. Without it, unchanged. `docs/api-reference.md` updated.

## 3. Evidence scope

- [x] **Unit tests** — `backend/tests/test_usage_trends.py` (+11 tests, 46 in the file):
  `test_period_param_and_weeks`, `test_three_week_average_leaves_out_byes_and_missed_games`, `test_three_week_jump_is_measured_against_the_three_weeks_before` (baseline outside the selection, one missed baseline game, biggest jump first, and the one-week block untouched), `test_three_week_jump_needs_two_games_and_the_volume_floor`, `test_fewer_than_two_games_rank_after_everyone_who_played_two`, `test_no_earlier_weeks_means_no_jumps_and_no_new`, `test_back_or_new_over_three_weeks`, `test_without_a_period_the_output_is_byte_identical_to_before` (sha256 of the real Weeks 1–4 and 2–4 output, captured from the code before this change), `test_real_2026_three_week_reading` (Darius Cooper 14.5% → 48.7% over Weeks 2–4, rank 1; Sterling Shepard back-or-new), `test_route_without_period_is_byte_identical_to_before` (sha256 of three raw route responses captured before this change), `test_route_period_adds_the_reading_and_reads_the_baseline_weeks`, `test_route_rejects_a_bad_period`.
- [x] **Structural guard** — `mobile/tests/check-usage-trends.js`: 1ag–1am executed against the pure module (server-rank order per order and unit, sections, no client arithmetic, copy with both ends and the weeks, the 1- and 2-game copy, back-or-new and no-earlier-weeks copy, bar flare), 1p's jargon scan now covers `periodHeadline`, 2e7 (pill: Simple only, three or more weeks, Last week default, remembered, reported, handed to the card), 2e8 (both events carry `period`), 2e9 (only Last 3 weeks sends `period=3`), 2e10 (the three-week list goes through the server's ranks only), 2e11 (section titles and sub-lines), 2e12 (card sentence and bar flare); 2p2 updated for the new query key and argument.
- [x] **Sabotage**: 13 backend and 16 mobile sabotages, each red then green with the file checksum unchanged (table in the build report and TEST_LEDGER).
- [x] **Code-walk proof:** [code-walk.md](code-walk.md) §9.
- [x] **Manual TestFlight checklist** (the build after this merge):
  1. Usage Trends → Simple. Under **Biggest jumps \| Weekly share** there is a second pill, **Last week \| Last 3 weeks**, with Last week selected. The list is exactly what it was before this build (titles "Biggest jumps last week" / "Back or new last week", cards "Jumped from X% to Y%").
  2. Tap **Last 3 weeks** (Biggest jumps). A brief spinner, then "BIGGEST JUMPS OVER THE LAST 3 WEEKS" with the sub-line "Share of team plays in Weeks 7–9 against Weeks 4–6, biggest jump first." Cards read "Up from X% to Y% of <team> plays over Weeks 7–9" and the gap (Y − X) shrinks down the list. Bars flare Weeks 7–9 on those cards only.
  3. If present, "BACK OR NEW OVER THE LAST 3 WEEKS": cards read "Averaged N% … over Weeks 7–9, no games in Weeks 4–6". Then "EVERYONE ELSE", cards "Averaged N% …"; anyone reading "in 1 game" is at the bottom.
  4. Pick a player you know missed one of the last three games: his card says "in 2 games, Weeks 7–9".
  5. Tap **Weekly share** (still Last 3 weeks). One section "WEEKS 7–9 AVERAGE SHARE OF TEAM PLAYS"; each card "Averaged N% of <team> plays over Weeks 7–9", numbers falling top to bottom, "in 1 game" players last.
  6. Filters → **Count**. Pill reads "Weekly count"; the section reads "Weeks 7–9 average snaps a game"; cards "Averaged N snaps a game …", ordered by that number. Switch to Targets: the order follows targets. In Biggest jumps a jump reads "Up from 3 to 8 targets a game over Weeks 7–9".
  7. Tap **Last week**: the one-week list is back instantly. Back out and reopen the screen: the period you left is still selected. Restart the app: it opens on Last week.
  8. Filters → Weeks → **Last 2**: the period pill disappears and the list is the one-week reading. Back to Last 4: the pill returns.
  9. **Raw stats**: no period pill, table unchanged in either period.
- `testID`s added: `usage-trends.period.week`, `usage-trends.period.three_weeks` (template literal; `testid-lint.sh` green, no flow references them).

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | `GET /api/usage-trends`: `period` param, `period` response blocks, `invalid_period`, the client order note |
| `living-memory/LLD.md` | n/a here | the brief reserves `living-memory/` for the lead session; suggested entry: "Usage Trends Last 3 weeks: server-ranked (`rank_jump`/`rank_share`/`rank_count`); the client sorts by those ranks only" |
| `docs/architecture.md` | n/a | no module wiring change; one route reads extra weeks through the existing `_usage_week` |
| `living-memory/HLD.md` | n/a | no architectural shift |
| `docs/cross-client-invariants.md` | n/a | mobile is the only client of `/api/usage-trends`; no constant is shared with web or the extension |
| `docs/glossary.md` | updated | "Last week / Last 3 weeks" period entry |
| ADR or `DECISIONS.md` entry | n/a here | `living-memory/` is the lead's; the decisions are in §0 for the lead to record |
| `docs/plans/README.md` | updated | usage-trends row |
| `docs/business/analytics/2026-11-12-usage-trends-period.md` | added | `period` prop |
| `mobile/src/screens/CLAUDE.md`, `mobile/src/components/CLAUDE.md` | updated | screen and card rows |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (with the `check-*.js` suites) + `maestro-testid-lint` on the pushed sha.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry (lead session).
- **TestFlight verification:** the 9 steps in §3.
- Express lane declared by the operator? **No**, so full gates apply.
