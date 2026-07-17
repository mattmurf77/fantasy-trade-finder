# mobile/src/navigation/

React Navigation config.

- `RootNav.tsx` — root stack: Sign in → main app. Also hosts the pushed league-wide surfaces `LeagueSummary` (League rankings, #142/#144) and `FreeAgents` (FA finder, #143) — entered from the League tab's Explore rows; being root-stack routes, `navigation.navigate` from any tab screen bubbles up to them
- `TabNav.tsx` — bottom tabs (Rank, Trades, Matches, League). The Rank tab is a stack (RankHome chooser / Trios / Anchors / Tiers / QuickSetTiers / QuickRank / ManualRanks / Trends) whose initial route follows `useSession.rankingMethodPref` (null → RankHome chooser); tapping the tab opens the rank-mode action sheet. QuickSetTiers is in that sheet as "Quick set" (recommended, #119) and is also entered from the Tiers header or launch routing (`rankingMethodPref: 'quickset'`). QuickRank (#136) sits in the sheet as "Quick rank" and is offered when the Quick set walk finishes; it is deliberately not a launch-routable pref

Add a new screen: register here and create the screen file in `../screens/`.
