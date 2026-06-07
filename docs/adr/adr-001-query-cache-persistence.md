# ADR-001 — Query Cache Persistence Storage: AsyncStorage vs MMKV

**Status:** Accepted  
**Date:** 2026-06-07  
**Initiative:** INIT-07 (Persisted Query Cache + Key Scoping)

---

## Context

Every cold launch starts with an empty TanStack Query in-memory cache, forcing the user to wait on fresh network round-trips before any player, rankings, or trade data appears. Adding a query persister (via `@tanstack/react-query-persist-client`) would let allowlisted queries paint immediately from disk while revalidating in the background.

Two storage options were evaluated:

### Option A — `@react-native-async-storage/async-storage` (AsyncStorage)

- Already a direct dependency in `mobile/package.json`
- Pure JS / no native module compilation required
- Asynchronous read: hydration happens in a `useEffect`-like hook, so the first paint still shows a loading state for a brief moment (~50–200 ms) before persisted data arrives
- No Expo prebuild or config-plugin step needed
- `@tanstack/query-async-storage-persister` adapter is the upstream-blessed approach for Expo

### Option B — MMKV (`react-native-mmkv`)

- Synchronous reads: persisted data available before first render, enabling true instant paint
- Requires a native module — adds an Expo config-plugin, forces an `npx expo prebuild`, and creates a managed-workflow compatibility concern
- Meaningfully faster cache reads (< 1 ms vs ~5–50 ms for AsyncStorage on typical payloads)
- Switching to MMKV later is a contained 1-day change once the persister abstraction is in place

---

## Decision

**Use AsyncStorage (Option A)** for Wave 2.

### Rationale

1. **Zero native dependency risk.** AsyncStorage is already installed and requires no config changes. Adding a native module introduces prebuild complexity and potential managed-workflow breaks that are out of scope for a perf wave.

2. **Sufficient latency.** The goal is "cached data paints before the spinner shows on cold launch." AsyncStorage's ~50–200 ms hydration latency clears that bar for the allowlisted screens (rankings, progress, matches). The improvement from MMKV's sub-millisecond reads is real but not user-perceivable at this screen density.

3. **Reversible choice.** The persister abstraction (`PersistQueryClientProvider` + `createAsyncStoragePersister`) decouples storage from the cache logic. Swapping to an MMKV-backed persister later is a single-file change in `App.tsx` once `react-native-mmkv` is added as a dependency. No query-key or screen-level code changes needed.

4. **Upstream recommendation.** The TanStack Query docs explicitly list AsyncStorage as the primary persister example for React Native / Expo Managed Workflow.

---

## Consequences

- Cold launches show persisted rankings/progress/matches data within ~200 ms instead of waiting for a network round-trip.
- The `['trio', ...]` deck and live trade-generation job snapshots are explicitly excluded from the dehydration allowlist — they must stay fresh.
- If a future measurement shows AsyncStorage hydration latency is user-perceivable (e.g., a spinner flash before cached data appears on older devices), upgrading to MMKV is the documented next step. No architectural rework needed.
- **Open question (Q6 in questions-for-user.md):** User has not yet confirmed AsyncStorage is acceptable long-term. This ADR documents the default; the MMKV upgrade path is ready.

---

## Dehydration allowlist

Keys persisted to AsyncStorage (Wave 2 implementation):
- `['rankings', ...]` — positional ELO boards
- `['progress', ...]` — ranking progress bar + unlock state
- `['matches', ...]` — trade match inbox
- `['tiers-status', ...]` — tier unlock state
- `['liked-trades', ...]` — liked trade cards

Keys **excluded** (must not persist):
- `['trio', ...]` — must always be fresh (staleTime: 0)
- Live trade-generation job snapshots
