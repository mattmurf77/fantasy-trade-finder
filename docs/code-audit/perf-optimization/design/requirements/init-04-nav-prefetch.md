# REQ — INIT-04: Extend navigation prefetch beyond Trios

- **Initiative / Wave / Scope:** INIT-04 · Wave 1 · [M]
- **Source observations:** OBS-CACHE-05 (RICE-P 6.4)
- **Peak RICE-P:** 6.4

## Problem statement

The only navigation-time prefetch in the app is for the Trios destination: `RankMenu.go()` warms `['trio','QB']` during the action-sheet close animation so `RankScreen` adopts an in-flight request on mount. All other destinations — Tiers, Overall Ranks, Manual Ranks, Matches, and Trades — start their data fetch only after the navigation transition completes, causing a visible spinner on every first in-session visit even on a warm dyno.

## User stories

- As a dynasty manager navigating to the Tiers or Overall Ranks screen, I want the ranking data to already be loading or loaded when the screen appears, so that I do not see a blank spinner after every tab or menu tap.
- As a dynasty manager tapping the Matches or Trades tab, I want the tab's data to be in-flight before the transition animation ends, so that the screen paints content as soon as it is visible.
- As a developer, I want the prefetch extension to reuse the proven adoption pattern already in place for Trios, so that the change is minimal and the risk is low.

## Functional requirements

- FR-1: `RankMenu.go(route)` in `TabNav.tsx` must call `queryClient.prefetchQuery` for the destination's primary query key before (or immediately as) the navigation action fires, for each of the following routes:
  - Tiers: prefetch `['rankings', 'QB']` (or the active position) and `['tiers-status']`
  - OverallRanks: prefetch `['rankings', 'all']`
  - ManualRanks: prefetch `['rankings', 'all']`
- FR-2: A `tabPress` listener must be added in `TabNav.tsx` for the **Trades** tab that prefetches `['liked-trades', leagueId]` on tab press, fire-and-forget.
- FR-3: A `tabPress` listener must be added in `TabNav.tsx` for the **Matches** tab that prefetches `['matches', 'all']` on tab press, fire-and-forget.
- FR-4: All prefetch calls must be fire-and-forget (no `await`); errors must surface only on the destination screen's `useQuery`, not in the prefetch call site.
- FR-5: Each prefetch must use the **exact same query key shape** as the `useQuery` call in the destination screen — if INIT-07 (key scoping) lands first or concurrently, the prefetch keys must be updated to match the scoped shape `['rankings', format, position]` etc. Key-shape mismatches must be caught by a test or a shared key-factory utility.
- FR-6: The existing Trios prefetch at `TabNav.tsx:169–177` must not be modified beyond what is needed to refactor the call into the shared pattern (no behavioral change for Trios).

## Acceptance criteria

- [ ] AC-1 — Given the user opens the RankMenu action sheet and taps the Tiers row, when the navigation transition begins, then a `prefetchQuery` for `['rankings', 'QB']` and `['tiers-status']` is dispatched before or at the moment of navigation, and `TiersScreen` adopts the in-flight or completed query on mount without issuing a duplicate fetch.
- [ ] AC-2 — Given the user opens the RankMenu action sheet and taps Overall Ranks or Manual Ranks, when the navigation transition begins, then a `prefetchQuery` for `['rankings', 'all']` is dispatched, and the destination screen adopts it on mount.
- [ ] AC-3 — Given the user taps the Trades tab, then a `prefetchQuery` for `['liked-trades', leagueId]` is dispatched; `TradesScreen` adopts the in-flight query on mount.
- [ ] AC-4 — Given the user taps the Matches tab, then a `prefetchQuery` for `['matches', 'all']` is dispatched; `MatchesScreen` adopts the in-flight query on mount.
- [ ] AC-5 — Given a prefetch call throws a network error, then the error is swallowed at the prefetch call site and the destination screen's `useQuery` surfaces the error through its own error state, with no unhandled promise rejection.
- [ ] AC-6 — Given a warm dyno and the network round-trip is ≥ 200 ms (normal warm-dyno latency), when the user navigates to any prefetched destination, then no full spinner is shown on that first in-session visit (the screen either shows prefetched data or shows `placeholderData` from the in-flight prefetch).
- [ ] AC-7 — The Trios prefetch behavior is unchanged: `RankMenu.go()` still prefetches `['trio', 'QB']` and `RankScreen` adopts it, as verified by the existing behavior before this change.
- [ ] AC-8 — If INIT-07 key scoping has already landed, then the prefetch keys in FR-1 through FR-3 use the scoped forms (e.g. `['rankings', format, 'QB']`), and a test confirms the prefetch key matches the destination's `useQuery` key exactly.

## Related components

- `mobile/src/navigation/TabNav.tsx:169–177` — existing Trios `prefetchQuery` (reference pattern; must not be changed functionally)
- `mobile/src/navigation/TabNav.tsx:162–168` — comment noting Trios-only prefetch scope (to be updated)
- `mobile/src/navigation/TabNav.tsx:188–194` — `RankMenu` action sheet listing Tiers / ManualRanks / OverallRanks / Trends as siblings to Trios (the tap targets for FR-1)
- `mobile/src/screens/TiersScreen.tsx:102–114` — `useQuery(['rankings', position])` + `useQuery(['tiers-status'])` (destination key shapes for Tiers prefetch)
- `mobile/src/screens/OverallRanksScreen.tsx:29` — `useQuery(['rankings', 'all'])` (destination key shape)
- `mobile/src/screens/ManualRanksScreen.tsx:59` — `useQuery(['rankings', 'all'])` (destination key shape)
- `mobile/src/screens/MatchesScreen.tsx:53` — `useQuery(['matches', 'all'])` (destination key shape)
- `mobile/src/screens/TradesScreen.tsx:341` — `useQuery(['liked-trades', leagueId])` (destination key shape; `leagueId` must be available at the prefetch call site)
- `mobile/src/api/rankings.ts` — query functions for rankings/tiers-status
- `mobile/src/api/trades.ts` — query function for liked-trades

## Prerequisite components / dependencies

None for the core prefetch extension. However:
- **Interaction with INIT-07 (key scoping):** if INIT-07 lands before or concurrently with this initiative, the prefetch keys must match the scoped key shape (`['rankings', format, position]`, etc.). The two initiatives must coordinate on key shapes. If INIT-07 is not yet landed, the current flat keys are correct; the change must be revisited when INIT-07 ships.
- **`leagueId` availability:** the Trades tab prefetch (FR-2) requires `leagueId` at the `TabNav` level. Confirm that `leagueId` is accessible from the tab navigator's context (e.g. via `useSession`) before implementing.

## Non-functional requirements & invariants

- **Key-shape correctness invariant:** a prefetch that uses a different key than the destination's `useQuery` is a silent no-op — the warm misses and the screen fetches cold regardless. Every prefetch key must exactly match the destination's `useQuery` key at the time of ship. This is the primary risk of this initiative and must be verified by a test or a shared key-factory (see FR-5).
- **Fire-and-forget only:** prefetch calls must never be awaited. An awaited prefetch would block the navigation action and could introduce new latency.
- **No ELO / tier-band / cross-client invariants touched:** this initiative is client-side cache warming only. No ranking math, no backend, no data mutations.
- **Performance target:** on a warm dyno (round-trip 0.2–0.5 s), the first in-session visit to each prefetched destination must show content without a full spinner, by overlapping the data round-trip with the ~250–400 ms navigation transition.
- **Rollback:** removing the `prefetchQuery` calls restores cold-fetch behavior on navigation. No DB migration, no backend change.

## Out of scope

- INIT-07 (persisted query cache + key scoping) — complementary but separate; on cold launch the persisted cache provides last-known data; prefetch handles the first in-session visit.
- Prefetching during the splash screen (OBS-CACHE-02 Option B) — covered by INIT-01 scope if desired; not this initiative.
- The Trends screen prefetch — mentioned in the LLD as "include if cheap"; deferred unless the Trends query key is confirmed and the incremental effort is trivial.
- INIT-05 (`focusManager` / `onlineManager`) — separate initiative; resume-freshness is a different problem from navigation prefetch.
- Any backend changes.
- The web client or browser extension.
