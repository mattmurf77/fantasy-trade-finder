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

## 5. The list is the server's order, in both views

1. `visiblePlayers(data.players, focus, metric, ownership, positionFilter)` (`UsageTrendsScreen.tsx:119`) filters, then sorts by the server's per-metric `rank` (`usageTrends.ts:50`).
2. The screen contains no other `.sort(`, and the guard pins that.
3. Version A splits the list at `newsCount`: the newest-week jumps come first, under "Biggest jumps last week".

## 6. One pill flips the two views

1. `setView(v)` and `lastView = v` (`:426-427`) swap the `renderItem` branch: `UsageTrendCard` vs `UsageStatsRow`.
2. The swap also changes the fixed header (`UsageStatsHeader` appears only under `stats`) and the per-view unit: A defaults to % of team, B to counts.
3. Version B's chevron (`UsageStatsTable.tsx:162`) and its row body both call `onToggle` (`UsageTrendsScreen.tsx:331`), which expands `UsageLeagueList` inline and reports `usage_trends_availability_opened`.
