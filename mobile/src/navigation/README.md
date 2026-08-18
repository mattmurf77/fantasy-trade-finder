# mobile/src/navigation/

React Navigation config. Behavior, gates, and sharp edges are in [CLAUDE.md](CLAUDE.md) — read that before adding or moving a route.

| File | Role |
|---|---|
| `RootNav.tsx` | Root native-stack. Auth routing (SignIn → LeaguePicker → Main), all root-level pushed surfaces, and the app-wide mounts that sit above the tabs |
| `TabNav.tsx` | Bottom tabs and each tab's own stack |
| `rankChooserModel.ts` | Shared content model for the rank-method chooser, consumed by both `RankHomeScreen` and TabNav's `RankMenu` sheet so they cannot diverge |
| `scrollToTop.ts` | Re-tap-to-top registry (flag `ux.retap_active_tab`) — a tab's root screen registers its scroll handler via `registerScrollToTop` |

The deep-link route table is **not** in this folder — it lives in [`../utils/deepLinks.ts`](../utils/deepLinks.ts) and is the single source for URLs, push taps, and notification-bell rows.

## Route map

```
RootNav (Stack)
├─ SignIn
├─ LeaguePicker
├─ LeagueJoin
├─ Main ──► <TabNav /> + <VerifyAccountBanner /> + <PushPrimingModal /> + <FeedbackFAB />
├─ Settings          ├─ Profile        ├─ FeedbackInbox
├─ LeagueSummary     ├─ FreeAgents     ├─ DraftRoom
├─ MockDraft         ├─ PickAssignment ├─ RecordPicks
├─ TestStages        ├─ SleeperConnect └─ EspnConnect
```

```
TabNav (Bottom tabs — Rank · Acquire · Draft · Matches · League)
├─ Rank    (Stack)  RankHome · Trios · Anchors · Tiers · QuickSetTiers ·
│                   QuickRank · ManualRanks · RookieRanks · Trends
├─ Trades  (Stack)  TradesHome · TradeDeck · Portfolio · TradeCalculator
│          ↳ tab label is "Acquire"; the route name stays `Trades`
├─ Draft   (Stack)  DraftRoom              — renders only under flag `draft.tab`
├─ Matches (screen)
└─ League  (Stack)  LeagueRankings (root, = LeagueSummaryScreen) · LeagueHome (= LeagueScreen)
```

`DraftRoom` is registered in **both** navigators. The tab copy receives `initialParams {inTabs:true}` (suppresses its local `FeedbackFAB`, since RootNav's global mount already covers tab screens); `deepLinks.ts` points the canonical path at the root-stack copy.

## Adding a screen

Three things, together:

1. Create the file in [`../screens/`](../screens/CLAUDE.md).
2. Register it here — `TabNav.tsx` for a tab-stack screen, `RootNav.tsx` for a pushed surface.
3. Add its route to [`../utils/deepLinks.ts`](../utils/deepLinks.ts).

Then check [CLAUDE.md](CLAUDE.md) § Sharp edges — flag-gated routes register unconditionally, and root-stack pushes over the `headerShown:false` Main tabs need the explicit `HeaderBack` control.
