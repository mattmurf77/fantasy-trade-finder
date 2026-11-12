# Usage Trends — code-walk proof

**Date:** 2026-10-10 · branch `feat/usage-trends` · evidence for [scope.md](scope.md) §3 (D-056: a file:line trace stands in for a simulator capture). Line numbers are as of the commit that adds this file.

## 1. A row's first action follows the player's status in the focused league

1. **Server.** `_usage_league_rosters` (`backend/server.py:30601`) maps every rostered player to an owner key.
   - An ownerless Sleeper roster becomes `roster:<id>` (`:30632`), so its players are never free agents.
   - `me` comes from `sleeper_roster.owns_roster` on the live read, so a co-owner counts (`:30635`).
   - A league the caller has no team in returns `None` (`:30637`, `:30654`). The route sends it as `ok:false` with empty rosters, so other leagues' rosters are never served.
2. **Client.** `statusIn` (`mobile/src/utils/usageTrends.ts:20`) reads that map:
   - absent → `free_agent` (`:23`);
   - equal to `me` → `mine`;
   - anything else → `rostered`;
   - an unreadable league → `unknown`.
3. **Screen.** `UsageTrendsScreen.tsx:299` computes `focusStatus`. Both views branch on it:
   - Version A, `UsageTrendCard`: Add, Trade, a "Yours" label, or nothing.
   - Version B, `UsageStatsTable.tsx:126`/`:137`: a `+` icon, the stacked `trade` icon, a check, or nothing.

## 2. Trade lands in Find a Trade with the player pinned and his manager chosen

1. `onTrade={() => focusId && doTrade(p, focusId)}` (`UsageTrendsScreen.tsx:311` A, `:336` B).
2. In `doTrade` (`:218`), the league is switched first if needed (`switchTo`, `:194`). The pins are written only after that resolves (`:223`), because `useFinderTargets` clears pins on any league switch. The guard pins this order.
3. Then the screen writes the receive-side pin and `setHandoff({opponent, autoRun:true})` (`:227`). The opponent is the owner key, with `null` for an orphaned roster.
4. Finally it navigates `Main → Trades → TradesHome` (`:234`). That is the same handoff contract `LeagueSummaryScreen` uses, consumed by `TradesScreen`'s #330 choke point.

## 3. Add opens the same claim sheet as Free Agents, or an honest refusal

1. In `doAdd` (`:237`), `resolveAddPlatform(lgId, isDemo)` (`:239`) runs first.
2. Non-Sleeper leagues get `explainNoAdd(platform)` (`:242`) with no league switch.
3. Sleeper leagues switch if needed (`:245`), then `setClaim(...)` (`:246`), which mounts the shared `<ClaimSheet>` (`:522`).
4. That sheet is the component `FreeAgentsScreen` now imports (`components/ClaimSheet.tsx`, moved unchanged). Its FAAB and drop context comes from the same `['free-agents', leagueId, 'ALL']` query the Free Agents screen uses.

## 4. Re-rank opens Quick Set on the player's position, even if it is already open

1. In `doRerank` (`:249`), the screen navigates `Main → Rank → QuickSetTiers {position, positionSeq: Date.now()}` (`:253`).
2. On a fresh mount, `QuickSetTiersScreen`'s `useState` initializer reads `position`.
3. On an already-mounted walk, the new effect (`QuickSetTiersScreen.tsx:512-516`) fires on the changed `positionSeq` and calls the existing `onPosition`. A repeat of the same position still lands, because the seq changes.

## 5. The list is the server's order; Version B can re-sort by column

1. `visiblePlayers(data.players, focus, metric, ownership, positionFilter)` (`UsageTrendsScreen.tsx:119`) filters, then sorts by the server's per-metric `rank` (`usageTrends.ts:50`).
2. The screen contains no other `.sort(`, and the guard pins that.
3. Version A splits the list at `newsCount`: the newest-week jumps come first, under "Biggest jumps last week".
4. **Version B only.** The `items` memo's stats branch is `sortStatsRows(list, metric, unit, statsSort)`. With `statsSort` null it returns `list` untouched.
   - Header taps go through `nextSort`: first → reversed → null.
   - Nulls (out/bye) sort last both ways, and ties keep the server order. Both are executed by `check-usage-trends.js` §1v–1ab.
   - §2e2 pins that this is the only `sortStatsRows` call, so Version A cannot be re-sorted.

## 6. One pill flips the two views

1. `setView(v)` and `lastView = v` (`:426-427`) swap the `renderItem` branch: `UsageTrendCard` vs `UsageStatsRow`.
2. The swap also changes the fixed header (`UsageStatsHeader` appears only under `stats`) and the per-view unit: A defaults to % of team, B to counts.
3. Version B's chevron (`UsageStatsTable.tsx:162`) and its row body both call `onToggle` (`UsageTrendsScreen.tsx:331`), which expands `UsageLeagueList` inline and reports `usage_trends_availability_opened`.

## 7. The user's week selection reaches every number

1. Filters → Weeks keeps a draft (`toggleWeek`, `presetWeeks`). On close it commits `setSelectedWeeks(nextWeeks)`. A pick equal to the last four is normalized back to `null`, the default.
2. The query key includes `weeksParam(selectedWeeks)`, and `getUsageTrends(..., selectedWeeks)` sends `&weeks=2,6`. `keepPreviousData` holds the old list on screen while it loads.
3. Server side, `parse_weeks_param` validates against `completed_weeks` (400 `invalid_weeks` otherwise; the client resets to the default on that error).
4. Each week resolves through `_usage_week` (store, else a live fetch of that week). `compute_normalized` runs over exactly those weeks, so averages, totals, signals and `rank` cover the pick only.
5. The response echoes `weeks` and `available_weeks`. The sub-header renders `weeksLabel(weeks)`, Version A sizes its bars with `barGeometry(n)`, and Version B widens the table with `statsTableWidth` inside a horizontal `ScrollView`.


## 8. The order toggle, and why each order now reads as sorted (2026-10-10, [scope](scope-order-toggle.md))

1. `order` starts from the module-level `lastOrder` (`UsageTrendsScreen.tsx:83`, `:99`), which defaults to `'jumps'`. The pill is the Simple list's `ListHeaderComponent` (`:445`), so Raw stats never shows it. A tap sets `order` and `lastOrder` and reports `usage_trends_view_changed{order}` (`:453-460`). Every report carries the current order (`:186`), and so does every action event (`:220`).
2. **Biggest jumps** (`:318`): `newsSplit` (`utils/usageTrends.ts:182`) splits the server's order without re-sorting it. The first run of newest-week jumps comes first (`isJump`, `:173`: a spike, or a return carrying `delta_share`). The next run is newest-week returns and new roles that aren't jumps. The server's `_rank` puts tier 0 (newest spikes) before tier 1 (return/new), so each group is contiguous.
3. A jump card's sentence names both ends: `headline` → "Jumped from ${jumpFrom} to ${amount}" (`utils/usageTrends.ts:145`). `jumpFrom` (`:115`) is `share − delta_share`, the earlier-weeks mean the server's `d_share` was measured against (`usage_trends.py` `_metric`), so the gap shown is the tier-0 sort key.
4. **Weekly share** (`UsageTrendsScreen.tsx:307`): one section, `sortByLatestWeek(list, metric, unit, weeks.length)` (`utils/usageTrends.ts:197`). That is `sortStatsRows` with the last week descending, the same tested sort Raw stats uses, so a missed game or bye sorts last and ties keep the server order. The card gets `order` (`UsageTrendCard.tsx:109`) and renders `weekHeadline` (`:136` → `utils/usageTrends.ts:205`): that week's share or count, or "Didn't play" / "Bye". It's the number the list is sorted by.
5. The server's return floor: `elif missed_before_latest and counts[last] >= floor` (`usage_trends.py:251`), the same floor `new` uses (`:247`). Below it the player falls through to an earlier spike, rising/falling, or no signal. With no signal, `_relevant` drops him unless his average snap share is ≥10%.


## 9. Last week | Last 3 weeks (2026-11-12, [scope](scope-period-toggle.md))

Line numbers are as of the commit that adds this section.

1. **The pill.** `period` starts from the module-level `lastPeriod` (`UsageTrendsScreen.tsx:101`, `:118`), default `'week'`. It renders in the Simple list's `ListHeaderComponent`, in the same wrapping row as the order pill (`:625`), only while `periodShown` (`:207`: `view === 'simple' && weeks.length >= 3`). A tap sets `period` and `lastPeriod` and reports `usage_trends_view_changed{period}` (`:638`); every view report carries it (`:253`), and so does every action (`usage_trends_action`, `:277`).
2. **Last week is today's request.** `periodParam` is `3` only under Last 3 weeks (`:170`); the query key gains `'period3'` only then (`:173`), and `getUsageTrends` appends `&period=3` only then (`api/usageTrends.ts:123`). Under Last week the request, cache key and every branch below are the ones that existed before.
3. **Server.** The route parses `period` (`server.py:43204`, 400 `invalid_period`), computes `period_weeks(weeks, available)` (`usage_trends.py:136`: newest three selected weeks; up to three completed weeks before them), echoes it as `payload.period` (`server.py:43217`), and computes under a separate cache key with the baseline weeks read through the same `_usage_week` (`server.py:43218`, `:43223`). Without the parameter, `period` is `None`, the key and the `compute_normalized` call are the old ones, and the response bytes are pinned equal to the pre-change capture (`test_route_without_period_is_byte_identical_to_before`).
4. **The numbers.** In `compute_normalized`, after `_relevant` (so the player set never changes), each player's played period weeks (`usage_trends.py:369`) and played baseline weeks (`:376`) feed `_period_metric` (`:379` → `:391`): played-week averages, `kind` jump/new with the two-game minimum, per-game volume floor and spike margin (`:418`-`:422`). `_rank_period` (`:387` → `:429`) writes `rank_jump`, `rank_share`, `rank_count`, with fewer than two games last (`:441`).
5. **The client only orders by those ranks.** `periodMeta` (`UsageTrendsScreen.tsx:208`) is the response's `period` under Last 3 weeks. The items memo hands off to `periodItems` before any one-week branch (`:451`). `periodItems` (`:981`) calls `periodOrder` (`:985` → `utils/usageTrends.ts:228`, which sorts by `rank_jump`, or `rank_share` / `rank_count` for the unit showing, and nothing else) and `periodSplit` (`:1000` → `utils/usageTrends.ts:240`, the leading `jump` run, then the `new` run). The section lines name the weeks (`Weeks 7–9 against Weeks 4–6`).
6. **The card says the number the list is ordered by.** `period={periodMeta}` (`UsageTrendsScreen.tsx:510`) makes `UsageTrendCard` read `periodHeadline` (`UsageTrendCard.tsx:147` → `utils/usageTrends.ts:262`): "Up from 12% to 47% of Jets plays over Weeks 7–9" for a jump (both ends are the server's `base_avg_share` and `avg_share`, so the gap is the `rank_jump` key), "Averaged …" otherwise, "in 2 games" / "in 1 game" when he missed period weeks. The bars flare the period weeks of a jump or back-or-new card (`UsageTrendCard.tsx:158`).
7. **Loading and fallback.** While the period answer is placeholder data from the one-week key, `periodPending` (`UsageTrendsScreen.tsx:210`) shows the spinner (`:587`) rather than the one-week list under three-week titles. A settled answer without `period` (an older server) leaves `periodMeta` null and the one-week list renders.
