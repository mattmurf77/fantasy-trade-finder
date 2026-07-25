# #181 — League rankings becomes the League tab's primary page — status

**Status: built** · 2026-07-25 · branch `teardown-remediation` worktree

Operator: the league rankings view should be the primary page when clicking the League tab, with the current default league page reachable from it.

## Approach: League tab becomes a small stack (mirrors the Trades-tab pattern)

`TabNav.tsx` gains a `LeagueStack` (same construction as `TradesStack`):

- **`LeagueRankings`** (stack root) — `LeagueSummaryScreen`, the view the tab now lands on (stacked bar chart + basis toggle + position filter + drill-in + the dark odds section). Gets a Chalkline stack header titled "League rankings"; being the stack root it has no headerLeft, so there is **no back button to nowhere**.
- **`LeagueHome`** (pushed) — `LeagueScreen`, the classic league page (hero/switcher, Matches tiles, Explore rows, activity, contrarian, coverage, leaderboards). Uses the shared always-on `HeaderBack` (#51/#52 pattern) with fallback `LeagueRankings`, covering the cold-start deep-link case.

Chosen over swapping the tab's component alone because the classic page needs to stay one tap away with sane back behavior, and the app already has two tab stacks establishing exactly this pattern — least new machinery, no RootNav changes needed.

### Entry points between the two views

- `LeagueSummaryScreen` (tab-root variant only) renders a **"League home"** row at the top (LeagueRow construction, testID **`league-summary.league-home`**) → pushes `LeagueHome`.
- `LeagueScreen`'s existing "League rankings" Explore row (testID `league.rankings-row`, unchanged) now navigates to `LeagueRankings` (returns to the stack root) instead of pushing the root-stack `LeagueSummary` on top.

### Legacy route kept functional

The ROOT-stack `LeagueSummary` route (RootNav) is untouched and still serves old entry points: deep link `app/league/summary`, stored whats-new routes, any `navigate('LeagueSummary')`. `LeagueSummaryScreen` detects its variant via `useRoute().name === 'LeagueRankings'`; the root-stack variant renders no home row and registers no re-tap handler (its RootNav `HeaderBack`, testID `league-summary.back-btn`, is unchanged).

### Deep links (v2 table, `utils/deepLinks.ts`)

`League` tab is now nested: `app/league` → `LeagueRankings` (tab root), `app/league/home` → `LeagueHome`. `app/league/summary` still resolves to the root-stack screen. Notification taps to the League tab (`league_member_joined` etc.) land on the rankings root.

### Re-tap / scroll-to-top (flag `ux.retap_active_tab`)

League tab listener now uses the Trades pattern: focused re-tap pops `LeagueHome` → `LeagueRankings`; at root it requests scroll-to-top. The `registerScrollToTop('League', …)` registration **moved from `LeagueScreen` to `LeagueSummaryScreen`'s tab-root variant** (the old registration would have clobbered the root's handler while both were mounted).

## testIDs

- All existing testIDs preserved (`league.*`, `league-summary.*`, `tab.league`).
- New: `league-summary.league-home`.
- None renamed; note the *route names* around them changed (`League` tab root screen is now `LeagueRankings`; classic page is `LeagueHome`) — Maestro flows that asserted on screen names, and analytics `screen_viewed` values, see `LeagueRankings`/`LeagueHome` instead of `League`.

## Known follow-ups (not in scope — other agents own the files)

- `RankScreen.tsx:361` streak chip navigates to the League tab expecting the leaderboards (which live on `LeagueScreen`); it now lands on the rankings root, one tap short. Fix is a one-liner: `navigate('League', { screen: 'LeagueHome' })`.
- League-kind notification taps (member joined/unlocked) also now land on rankings rather than the members surface; acceptable per "rankings is primary", revisit if testers object.

## Verification

- `cd mobile && npx tsc --noEmit` — clean (exit 0).
- Backend untouched by this item; suite green via #183's run (1047 passed, 1 skipped).
- Docs updated: `docs/design/components.md` (League rankings spec: tab root + League home row), `mobile/src/navigation/CLAUDE.md`, `mobile/src/screens/CLAUDE.md`.
