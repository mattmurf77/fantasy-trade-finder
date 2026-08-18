# mobile/src/screens/

32 screen components, one per route. What each screen *does* — and its sharp edges — is in [CLAUDE.md](CLAUDE.md). This file maps route names to files, because the two rarely match.

## Route → file

| Registered in | Route name | File |
|---|---|---|
| RootNav | `SignIn` | `SignInScreen.tsx` |
| RootNav | `LeaguePicker` | `LeaguePickerScreen.tsx` |
| RootNav | `LeagueJoin` | `LeagueJoinScreen.tsx` |
| RootNav | `Settings` | `SettingsScreen.tsx` |
| RootNav | `Profile` | `ProfileScreen.tsx` |
| RootNav | `FeedbackInbox` | `FeedbackInboxScreen.tsx` |
| RootNav | `LeagueSummary` | `LeagueSummaryScreen.tsx` (legacy push; primary registration is the League tab root) |
| RootNav | `FreeAgents` | `FreeAgentsScreen.tsx` |
| RootNav + Draft tab | `DraftRoom` | `DraftRoomScreen.tsx` |
| RootNav | `MockDraft` | `MockDraftScreen.tsx` |
| RootNav | `PickAssignment` | `PickAssignmentScreen.tsx` |
| RootNav | `RecordPicks` | `RecordPicksScreen.tsx` |
| RootNav | `TestStages` | `TestStagesScreen.tsx` |
| RootNav | `SleeperConnect` | `SleeperConnectScreen.tsx` |
| RootNav | `EspnConnect` | `EspnConnectScreen.tsx` |
| RootNav | `PremiumRankingsBrowser` | `PremiumRankingsBrowserScreen.tsx` |
| Rank tab | `RankHome` | `RankHomeScreen.tsx` |
| Rank tab | `Trios` | `RankScreen.tsx` |
| Rank tab | `Anchors` | `PickAnchorScreen.tsx` |
| Rank tab | `Tiers` | `TiersScreen.tsx` |
| Rank tab | `QuickSetTiers` | `QuickSetTiersScreen.tsx` |
| Rank tab | `QuickRank` | `QuickRankScreen.tsx` |
| Rank tab | `ManualRanks` | `ManualRanksScreen.tsx` (labeled "Overall Ranks" in the UI) |
| Rank tab | `RookieRanks` | `RookieRanksScreen.tsx` |
| Rank tab | `Trends` | `TrendsScreen.tsx` |
| Acquire tab | `TradesHome`, `TradeDeck` | `TradesScreen.tsx` (both routes) |
| Acquire tab | `Portfolio` | `PortfolioScreen.tsx` |
| Acquire tab | `TradeCalculator` | `TradeCalculatorScreen.tsx` |
| Matches tab | `Matches` | `MatchesScreen.tsx` |
| League tab | `LeagueRankings` (root) | `LeagueSummaryScreen.tsx` |
| League tab | `LeagueHome` | `LeagueScreen.tsx` |
| — | *(no route)* | `PlaceholderScreen.tsx` — stub for unfinished routes |
| — | **unrouted** | `TradeFinderHubScreen.tsx` — kept in the tree, no navigator registers it |

## Conventions

- **`<Name>Screen.tsx`**, PascalCase, default export. The route name is whatever `navigation/` registers — do not assume they match.
- Screens own their data: `useQuery` against [`../api/`](../api/CLAUDE.md) lives here, not in a component.
- Screens compose from [`../components/`](../components/CLAUDE.md) and read tokens from [`../theme/`](../theme/CLAUDE.md). No inline hexes or px.
- **Root-stack pushes mount their own `<FeedbackFAB activeScreen="<RouteName>" aboveTabBar={false} />`.** Tab-stack screens do not — RootNav's global mount covers them, and a second one is the #196/#197 bug. Screens with a pinned bottom bar call `setPinnedBottomBarHeight` instead.
- **Root-stack pushes over the `headerShown:false` Main tabs need the explicit `HeaderBack` control** — native back is dead on iOS 26 (RNS#3294).
- Every interactive element gets a `testID` from the grammar in [docs/plans/mobile-testing/lld.md](../../../docs/plans/mobile-testing/lld.md) Appendix A; `bash ../../scripts/testid-lint.sh` enforces it in CI (this survived the Maestro retirement).

## Adding a screen

1. `MyThingScreen.tsx` here.
2. Register it in [`../navigation/`](../navigation/CLAUDE.md) — unconditionally, even if flag-gated.
3. Add its route to [`../utils/deepLinks.ts`](../utils/deepLinks.ts).
4. Mount `FeedbackFAB` if it is a root-stack push.
5. Add a row to [CLAUDE.md](CLAUDE.md).
6. Evidence per D-056 (2026-08-15): a `../../tests/check-*.js` guard for anything structural, a file:line code-walk for behavior, and a TestFlight checklist item for the operator. **No Maestro flow, no simulator capture** — `../../.maestro/` is retained history, not a workflow.
