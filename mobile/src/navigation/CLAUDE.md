# mobile/src/navigation/

React Navigation config. MAP, not a changelog — present behavior only, no dated amendments. History: `git log -- <this file>` and `living-memory/CHANGELOG.md`.

- `RootNav.tsx` — root stack: Sign in → main app. Also hosts root-level pushed surfaces `LeagueSummary` (legacy deep-link entry; primary registration is the League tab's stack root), `FreeAgents`, `DraftRoom`, `MockDraft`, `PickAssignment`, `EspnConnect`. Flag-gated screens (`DraftRoom`, `MockDraft`, `PickAssignment`) register UNCONDITIONALLY — the flag gates the entry point, not the route.
- `TabNav.tsx` — bottom tabs **Rank · Acquire · Draft · Matches · League** (Draft renders only with flag `draft.tab`; the Acquire tab's route name stays `Trades`).
  - **Rank** stack (RankHome / Trios / Anchors / Tiers / QuickSetTiers / QuickRank / ManualRanks / Trends / RookieRanks); launch route follows `useSession.rankingMethodPref`, or for no-pref users the next unset QuickSetTiers position, or Trios once all four are complete. Every surface falls back to `RankHome` on back.
  - **Acquire** (route `Trades`) — stack root `TradesHome` renders `TradesScreen` with `initialParams {mode:'guided'}` when flag `trades.finder_hub` is on (the guided deck is the landing), else the classic standalone home. `TradeDeck` stays registered for the `app/trades/finder` deep link.
  - **League** stack — root `LeagueRankings` = `LeagueSummaryScreen`, with the classic `LeagueScreen` pushed as `LeagueHome`. Focused re-tap pops to the root (flag `ux.retap_active_tab`).
  - **Draft** (flag `draft.tab`, hand-flipped seasonal switch, never computed) registers one screen, `DraftRoomScreen` with `initialParams {inTabs:true}` — no per-league chooser. The flag is read once at first mount, so a mid-session flip takes effect next launch. `DraftRoom` is dual-registered (root + this tab), but `deepLinks.ts` points its one canonical path at the root-stack copy.
- `rankChooserModel.ts` — the rank-method chooser's shared content model, consumed by both `RankHomeScreen` and TabNav's `RankMenu` sheet so they can't diverge.
- `scrollToTop.ts` — re-tap-to-top registry (flag `ux.retap_active_tab`): each tab's root screen registers its scroll handler via `registerScrollToTop`.
- `deepLinks.ts` — nested route table for `linking` (flag `ux.deeplink_router_v2`) — single source for URLs, push taps, and bell rows.

## Sharp edges

- Flag-gated screens (`DraftRoom`, `MockDraft`, `PickAssignment`) must stay registered unconditionally — gating the route breaks an in-flight push on flag revalidation.
- `RankHomeScreen.choose` must use `navigation.navigate`, not `replace`, so back/edge-swipe returns to the chooser — regressing this recreates a "stuck in a ranking loop" trap.
- Adding a screen means three things together: register it here, create the file in `../screens/`, add its route to `deepLinks.ts`.
