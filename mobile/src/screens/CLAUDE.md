# mobile/src/screens/

One file per top-level route.

| Screen | Purpose |
|---|---|
| `SignInScreen` | Sign in with Apple is the primary portal behind `auth.accounts` (P2.6 account-first: a new Apple identity lands in an account-only session, no league needed); Sleeper username demoted to "Continue with Sleeper" below it (flow unchanged) |
| `LeaguePickerScreen` | Pick which league to use |
| `LeagueScreen` | League home / settings |
| `RankHomeScreen` | Build-your-board chooser — Rank tab's first-run screen; describes the five ranking flows by process (guided → manual) with Quick set leading as the lowest-effort "recommended" card (#119), saves `rankingMethodPref` so later launches route straight to the chosen flow |
| `RankScreen` | 3-player swipe matchup loop |
| `TiersScreen` | Tiered roster view |
| `QuickSetTiersScreen` | Guided tier quick-set (1.5.4 #104; Rank-stack route `QuickSetTiers`; since #119 a first-class method — entered from the Tiers header, the rank-home chooser, the Rank menu, or launch routing via `rankingMethodPref: 'quickset'`) — per position, walk the ladder top→Waivers (8 steps since #117) tapping player chips into each tier; one `/api/tiers/save` per tier |
| `PickAnchorScreen` | Pick Anchor wizard (Rank-stack route `Anchors`; reached from the rank home chooser or the Rank menu — the Tiers-header link was removed in 1.5.4 #99) — value one player at a time in draft-pick terms via `/api/anchor/save` |
| `ManualRanksScreen` | Editable drag/tap rank board — labeled "Overall Ranks" in the UI |
| `TradesScreen` | Trade card browser |
| `TradeCalculatorScreen` | Manual trade builder — "Calculator" pill in Trades. Live mode: real consensus values via /api/trade/*; Demo mode: mock dual-board league |
| `MatchesScreen` | Mutual trade matches inbox |
| `SleeperConnectScreen` | WebView login to Sleeper → captures the JWT for "Send in Sleeper" (flagged beta). Doubles as account **verification** (account-auth P1): the backend proves the captured token live + claim-matched, marks the session verified, and the screen surfaces "Account verified" on success |
| `SettingsScreen` | Settings modal (gear icon): leagues, ranking pref, notifications, and the **Account** section — renders meaningful state for every session type (P2.7): linked identities, an Apple-link button for any session without an Apple identity (binds via `POST /api/auth/apple` on the live session and flips `useSession.verification`), Sleeper source row, link-Sleeper card for account-only users (P2.6 merge flow), verification status, Verify account (Sleeper sessions), Delete account |
| `PlaceholderScreen` | Stub for unfinished routes |
