# mobile/src/navigation/

React Navigation config.

- `RootNav.tsx` — root stack: Sign in → main app. Also hosts the pushed league-wide surfaces `LeagueSummary` (League rankings, #142/#144) and `FreeAgents` (FA finder, #143) — entered from the League tab's Explore rows; being root-stack routes, `navigation.navigate` from any tab screen bubbles up to them
- `TabNav.tsx` — bottom tabs (Rank, Trades, Matches, League). The Rank tab is a stack (RankHome chooser / Trios / Anchors / Tiers / QuickSetTiers / QuickRank / ManualRanks / Trends) whose initial route follows `useSession.rankingMethodPref` (null → QuickSetTiers, the default method since #122, with an always-on "More ways to rank" header link to the demoted RankHome chooser — formerly gated behind `onboarding.rank_routing`, item 9's Q1 ruling; a stored pref always wins); tapping the tab opens the rank-mode action sheet. QuickSetTiers is in that sheet as "Quick set" (recommended, #119) and is also entered from the Tiers header or launch routing (`rankingMethodPref: 'quickset'`). QuickRank (#136) sits in the sheet as "Quick rank" and is offered when the Quick set walk finishes; it is deliberately not a launch-routable pref

- `scrollToTop.ts` — re-tap-to-top registry (teardown PRD 01-05, flag `ux.retap_active_tab`): TabNav fires `requestScrollToTop(tab)` on a focused re-tap at stack root; each tab's root screen registers its list-scroll handler via `registerScrollToTop`

Teardown flags in this dir (all default off; flag-off = pre-teardown behavior):
- `ux.rank_tab_destination` — Rank tab navigates (PREF_ROUTE surface) instead of the menu intercept; chevron dropped from the tab icon; every rank surface gets a "More ways to rank" header control opening the RankMenu sheet; focused re-tap pops the Rank stack. Unflagged fix riding along: RankHome now has the shared sub-screen header (was headerless with only edge-swipe exit).
- `ux.retap_active_tab` — focused re-tap on Trades pops its stack (else scroll-to-top request); Matches/League get scroll-to-top requests.
- `ux.deeplink_router_v2` — RootNav's `linking` swaps to the full nested route table in `../utils/deepLinks.ts` (single source for URLs, push taps, bell rows). **URL-addressability is definition-of-done for new screens**: when you add a screen here, add its path to that table.

Add a new screen: register here, create the screen file in `../screens/`, and add its route to the v2 table in `../utils/deepLinks.ts`.
