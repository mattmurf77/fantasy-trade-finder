# REQ — INIT-07: Persisted Query Cache + Key Scoping

- **Initiative / Wave / Scope:** INIT-07 · Wave 2 · [M]
- **Source observations:** OBS-CACHE-01, OBS-CACHE-04
- **Peak RICE-P:** 4.3 (OBS-CACHE-01); OBS-CACHE-04 (1.6) is a hard prerequisite

## Problem statement

Every cold launch starts with an empty in-memory query cache, forcing the user to wait on fresh network round-trips (or a Render dyno wake) before any player, rankings, or trade data appears. Separately, player-data query keys omit `format` and `leagueId`, so switching leagues or scoring formats can serve the wrong league's or format's data until the stale-time window expires — a correctness bug that would be made significantly worse if stale data were persisted to disk under the wrong key.

## User stories

- As a dynasty manager, I want my rankings, progress, and matches to appear instantly on cold launch, so that I am not staring at a spinner while the app warms up.
- As a dynasty manager, I want switching leagues or scoring formats to immediately show the correct data for the new context, so that I never act on another league's rankings.
- As a developer, I want the cache persistence layer to only store keys that are correctly scoped by format and league, so that cache entries from one user context never bleed into another.

## Functional requirements

### Part A — Key scoping (CACHE-04, prerequisite, must land with or before Part B)

- **FR-1** The `['rankings', position]` query key used in `TiersScreen.tsx:103` must be replaced with `['rankings', format, position]` where `format` is the active scoring format.
- **FR-2** The `['rankings', 'all']` query key used in `OverallRanksScreen.tsx:30` and `ManualRanksScreen.tsx:60` must be replaced with `['rankings', format, 'all']`.
- **FR-3** The `['progress']` query key used in `RootNav.tsx:76` and `RankScreen.tsx:83` must be replaced with `['progress', leagueId, format]`.
- **FR-4** The `['streak']` key (`RankScreen.tsx:90`), `['tiers-status']` key (`TiersScreen.tsx:110`), and `['trio', position]` key (`RankScreen.tsx:76`, `TabNav.tsx:173`) must be reviewed and scoped to `format` (and `leagueId` where the backend returns league-relative data).
- **FR-5** All existing `invalidateQueries` partial-key calls (`RankScreen.tsx:145`, `TiersScreen.tsx:145,173`, `ManualRanksScreen.tsx:105`) must continue to match the new prefixed key shape — the broad `['rankings']` partial-key invalidation naturally extends to `['rankings', format, position]` prefixes; verify this holds after the change.
- **FR-6** `useSession.switchLeague` (`useSession.ts:182–184`) must invalidate the full `['rankings']`, `['progress']`, `['streak']`, and `['tiers-status']` families on league swap, in addition to the three keys it already invalidates.
- **FR-7** `setActiveScoringFormat` (`rankings.ts:35`) must trigger invalidation of the format-scoped player-data family when called.

### Part B — AsyncStorage persister (CACHE-01, after or with Part A)

- **FR-8** Add `@tanstack/query-async-storage-persister` as a dependency in `mobile/package.json`.
- **FR-9** Wrap `<QueryClientProvider>` in `App.tsx:96–105` with `<PersistQueryClientProvider>` backed by the existing `@react-native-async-storage/async-storage` dependency.
- **FR-10** Set the persister `maxAge` to match `gcTime` (currently 30 min, `queryClient.ts:20`) so persisted entries expire at the same horizon as in-memory entries.
- **FR-11** Apply a `dehydrateOptions.shouldDehydrateQuery` allowlist that includes: `['rankings', ...]`, `['progress', ...]`, `['matches', 'all']`, `['tiers-status', ...]`, `['liked-trades', ...]`. Exclude `['trio', ...]` (must stay fresh) and any live trade-generation job snapshot keys.
- **FR-12** On cold launch, persisted data for an allowlisted key must render immediately (stale-while-revalidate), followed by a background network refetch, before any spinner is shown.
- **FR-13** Persisting must not occur under under-scoped keys. FR-1 through FR-7 (key scoping) must be complete before or in the same release as FR-8 through FR-12.

## Acceptance criteria

- [ ] AC-1 — Given a user who has previously loaded the app, when the JS context is fully terminated and the app is cold-launched, then rankings/progress/matches paint from the persisted cache within 200 ms before the network refetch completes.
- [ ] AC-2 — Given a persisted cache entry for scoring format A, when the user switches to format B, then the format-B screens show format-B data (or a loading state), never format-A data.
- [ ] AC-3 — Given the user switches leagues, when `switchLeague` fires, then `['rankings', ...]`, `['progress', ...]`, `['streak']`, and `['tiers-status']` are all invalidated (verified by observing a network refetch on next screen visit).
- [ ] AC-4 — Given a Trios swipe is submitted, when `invalidateQueries` fires, then only the submitted position's Tiers cache and `['rankings', format, 'all']` are stale; other positions' Tiers caches remain warm (verifiable via React Query devtools / cache inspection).
- [ ] AC-5 — Given a persisted cache from a prior launch, the `['trio', ...]` keys are absent from AsyncStorage (never persisted), verified by inspecting the persisted store contents.
- [ ] AC-6 — Given an allowlisted key is in the persisted cache, a format switch must not render that key's data under a different format's view — confirmed by loading format A, killing the app, switching to format B on relaunch, and observing either a loading state or format-B data.
- [ ] AC-7 — No ELO values, tier band colors, or KTC math are touched by this change; the data served is unchanged, only the caching transport is modified.

## Related components

- `mobile/src/state/queryClient.ts:17–30` — in-memory-only QueryClient, no persister (OBS-CACHE-01)
- `mobile/App.tsx:96–105` — plain `<QueryClientProvider>`, not the persist variant (OBS-CACHE-01)
- `mobile/package.json:12,17` — missing persister dependency (OBS-CACHE-01)
- `mobile/src/screens/TiersScreen.tsx:103` — under-scoped `['rankings', position]` (OBS-CACHE-04)
- `mobile/src/screens/OverallRanksScreen.tsx:30` — under-scoped `['rankings', 'all']` (OBS-CACHE-04)
- `mobile/src/screens/ManualRanksScreen.tsx:60` — under-scoped `['rankings', 'all']` (OBS-CACHE-04)
- `mobile/src/navigation/RootNav.tsx:76` — under-scoped `['progress']` (OBS-CACHE-04)
- `mobile/src/screens/RankScreen.tsx:83,90` — under-scoped `['progress']`, `['streak']` (OBS-CACHE-04)
- `mobile/src/state/useSession.ts:182–184` — incomplete league-switch invalidation (OBS-CACHE-04)
- `mobile/src/api/rankings.ts:35` — `setActiveScoringFormat` has no cache-invalidation hook (OBS-CACHE-04)
- `mobile/src/navigation/TabNav.tsx:173` — `['trio', position]` key must be excluded from persistence (OBS-CACHE-04)

## Prerequisite components / dependencies

- **CACHE-04 key scoping (FR-1 through FR-7) must land in the same release as or before CACHE-01 persistence (FR-8 through FR-13).** Persisting under-scoped keys is a correctness regression worse than the current state — cross-league/cross-format data would survive across app kills. This is the single most important sequencing constraint for this initiative.
- The `@react-native-async-storage/async-storage` dependency is already present; only the persister adapter needs to be added.
- INIT-04 (navigation prefetch): if prefetch keys are updated for CACHE-04 scoping, they must use the same new key shape so prefetch adoption works.

## Non-functional requirements & invariants

- **Correctness invariant:** the persisted cache is a transport layer only. No ELO math, K-factors, tier band colors, or per-format independence (`docs/cross-client-invariants.md`) are touched. The same server-computed values are shown, just served from disk on cold launch before the network refetch.
- **Per-format independence (cross-client invariant):** 1QB-PPR and SF-TEP are independent rank sets on the backend. After key scoping, a cache entry for one format must never be served to a view rendering the other format. Verify with a multi-format switch smoke test.
- **Freshness:** persisted entries must still trigger a background revalidation. The `staleTime` (currently 30 s for most keys) must remain the freshness gate; the persister only provides the "instant paint while stale" behavior.
- **Exclusion of live state:** trade-generation job snapshots and the `['trio', ...]` deck must be excluded from dehydration. Trio deck staleness is user-visible (wrong opponent matchup); job snapshots are ephemeral by design.
- **AsyncStorage hydration latency:** if AsyncStorage hydration proves materially slow on device (measurable startup trace), consider the MMKV-backed synchronous persister (Option B in OBS-CACHE-01) as a future upgrade. This is out of scope for Wave 2.
- **Rollback:** reverting the persister wrapper returns the app to today's in-memory behavior with no data loss. Reverting key scoping alone would require a cache-version bump or a full invalidation on app startup to avoid serving old under-scoped entries from disk.

## Out of scope

- MMKV-backed synchronous persister (Option B / OBS-CACHE-01) — deferred pending evidence that AsyncStorage hydration latency is material.
- Manual `setQueryData`-on-boot pattern for individual keys (Option C / OBS-CACHE-01) — superseded by the full persister.
- Persisting web-client query state — web client uses a different data-fetching stack.
- Any change to ELO computation, K-factors, or tier band thresholds.
- `['trio', ...]` deck persistence — explicitly excluded; must stay fresh.
