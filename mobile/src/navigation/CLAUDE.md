# mobile/src/navigation/

React Navigation config.

- `RootNav.tsx` — root stack: Sign in → main app
- `TabNav.tsx` — bottom tabs (Rank, Trades, Matches, League). The Rank tab is a stack (RankHome chooser / Trios / Anchors / Tiers / QuickSetTiers / ManualRanks / Trends) whose initial route follows `useSession.rankingMethodPref` (null → RankHome chooser); tapping the tab opens the rank-mode action sheet. QuickSetTiers is in that sheet as "Quick set" (recommended, #119) and is also entered from the Tiers header or launch routing (`rankingMethodPref: 'quickset'`)

Add a new screen: register here and create the screen file in `../screens/`.
