# mobile/src/screens/

One file per top-level route.

| Screen | Purpose |
|---|---|
| `SignInScreen` | Sleeper username login |
| `LeaguePickerScreen` | Pick which league to use |
| `LeagueScreen` | League home / settings |
| `RankHomeScreen` | Build-your-board chooser — Rank tab's first-run screen; describes the four ranking flows by process (guided → manual), saves `rankingMethodPref` so later launches route straight to the chosen flow |
| `RankScreen` | 3-player swipe matchup loop |
| `TiersScreen` | Tiered roster view |
| `PickAnchorScreen` | Pick Anchor wizard (Rank-stack route `Anchors`; reached from the rank home chooser, the Rank menu, or Tiers) — value one player at a time in draft-pick terms via `/api/anchor/save` |
| `ManualRanksScreen` | Editable drag/tap rank board — labeled "Overall Ranks" in the UI |
| `TradesScreen` | Trade card browser |
| `TradeCalculatorScreen` | Manual trade builder — "Calculator" pill in Trades. Live mode: real consensus values via /api/trade/*; Demo mode: mock dual-board league |
| `MatchesScreen` | Mutual trade matches inbox |
| `SleeperConnectScreen` | WebView login to Sleeper → captures the JWT for "Send in Sleeper" (flagged beta) |
| `PlaceholderScreen` | Stub for unfinished routes |
