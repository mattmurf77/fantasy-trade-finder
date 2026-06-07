# 01 — Mobile Data-Fetching & Loading-UX Best Practices

> Research doc — follows the framework in `00-research-methodology.md`.
> Stack: RN 0.81 / Expo SDK 54, New Architecture + Hermes, Reanimated 4,
> TanStack Query v5, Zustand, Flask/Render free tier, SQLite dev / Postgres prod.

---

## TL;DR

- **Eliminate request waterfalls first** — replacing sequential `await` chains with `useQueries` / `Promise.all` is the single highest-leverage change; each saved round-trip on a cold Render dyno costs 200–600 ms.
- **Prefetch on the critical path** — warm the player-list cache on app boot and before navigation so the first real render hits the cache, not the network.
- **Set `staleTime` to something sane** — the default `0` forces a refetch every mount; player metadata changes at most once per week; `staleTime: 5 * 60_000` alone eliminates most redundant fetches.
- **Replace FlatList with FlashList** for player/trade lists — cell recycling benchmarks 5–10× faster on the UI thread; eliminates the "blank tile" jank on fast scrolls.
- **Use `placeholderData` + skeleton screens** instead of blank spinners — perceived load drops significantly even when actual network time is unchanged.
- **Implement dynamic-interval polling** for background job status rather than fixed `refetchInterval` — stop polling when done, add full-jitter backoff to avoid server stampede on reconnect.
- **Wire `focusManager` + `onlineManager`** to React Native's `AppState` and `NetInfo` — without this, TanStack Query's built-in SWR triggers (`refetchOnWindowFocus`, `refetchOnReconnect`) are dead on mobile.
- **Debounce user-triggered search fetches** by debouncing the query key value, not the fetch call itself — avoids violating TanStack Query's rules of hooks.

---

## Why it matters for FTF

| Known pain point | Relevant tactic(s) |
|---|---|
| 4.8 MB player payload fetched on every league-switch | staleTime tuning, pagination/windowed fetch, prefetch on boot |
| Render free-tier cold starts (15–30 s spin-up) | keep-warm ping, prefetch to hide latency, optimistic UI |
| Trade deck and tier screen feel slow on first open | parallel queries, prefetch before nav, skeleton/placeholderData |
| Player search fires on every keystroke | debounce query key |
| Elo matchup job polling blocks progress indicator | dynamic refetchInterval with jitter |
| Players list jank on scroll | FlashList + useInfiniteQuery + windowed fetch |
| Refetches on every screen re-focus (no focusManager wired) | focusManager + AppState setup, staleTime |

---

## Tactics

### 1. Request parallelization vs waterfalls

- **What it is** — A request waterfall occurs when fetch B cannot start until fetch A resolves. Parallelization fires multiple independent requests concurrently, collapsing total wall time to `max(t_A, t_B)` rather than `t_A + t_B`.
- **When to use it** — Whenever two or more queries have no data dependency between them (e.g., "fetch player metadata" and "fetch trade scores" are independent). Do NOT parallelize genuinely dependent queries (e.g., you need a `leagueId` from query A to build query B's URL).
- **Expected impact** — **Massive (3)**: On a 250 ms-latency connection a three-deep waterfall wastes ~750 ms vs ~250 ms for parallel execution. On a cold Render dyno where each request can cost 1–3 s, the savings are proportionally larger. The TanStack Query docs note that with 250 ms latency a triple waterfall costs 1 000 ms vs ~500 ms for flat parallel.
- **RN/Flask applicability** — Use `useQueries([...])` for a static or dynamic list of independent queries in one component. Use `useSuspenseQueries([...])` when Suspense boundaries are in play — standard parallel `useSuspenseQuery` calls do NOT parallelize; each suspends the component before the next starts. No backend changes required.
- **Cost / risk** — Low; `useQueries` is a drop-in. Risk: if a dependent query is accidentally made parallel, it will attempt to fetch with an `undefined` parameter — guard with `enabled: !!param`.
- **Source(s)** — [TanStack Query: Performance & Request Waterfalls](https://tanstack.com/query/v5/docs/framework/react/guides/request-waterfalls), [TanStack Query: Parallel Queries](https://tanstack.com/query/v5/docs/framework/react/guides/parallel-queries)

**Impact ladder: Massive**

---

### 2. Prefetching / warm-up

- **What it is** — Seeding the TanStack Query cache before the component that needs the data mounts, so the first render reads from cache rather than waiting for a network round-trip.
- **When to use it** — (a) App boot: prefetch the most-accessed data (player roster, league config) during the auth/splash phase. (b) Before navigation: call `queryClient.prefetchQuery` in the `onPress` handler of a tab or card before the screen mounts. (c) Render cold-start keep-warm: a lightweight `/ping` request on app foreground forces the Render dyno to spin up before the user taps a real feature. Do NOT prefetch every possible query; prioritize the critical path only.
- **Expected impact** — **Massive (3)** for cold-Render scenario (removes a 15–30 s stall from the user-visible critical path); **High (2)** for pre-nav prefetch on a warm server (saves one ~300–800 ms round-trip per screen transition).
- **RN/Flask applicability** — `queryClient.prefetchQuery({ queryKey, queryFn })` in a `useEffect` on the root navigator or in `AppState` "active" handler. Expo Router v5 introduced `router.prefetch()` for route-level data prefetching. The backend needs a `/ping` or `/health` endpoint (trivial Flask `@app.route`). `prefetchQuery` always returns `Promise<void>` and never throws — safe to fire-and-forget.
- **Cost / risk** — Low–Medium. Risk: stale prefetched data served if `staleTime` is set too high. Over-prefetching wastes bandwidth on metered connections. Mitigate by respecting a `reducedData` / network-type check.
- **Source(s)** — [TanStack Query: Prefetching & Router Integration](https://tanstack.com/query/latest/docs/framework/react/guides/prefetching), [Expo SDK 54 Changelog](https://expo.dev/changelog/sdk-54), [Render cold-start strategy guide](https://blog.samkiel.dev/your-render-free-tier-is-not-broken-its-just-cold)

**Impact ladder: Massive**

---

### 3. Optimistic UI + mutation patterns

- **What it is** — Updating the local UI immediately on user action, before the server confirms, so the interaction feels instant. Two patterns exist: (a) *via `variables`* — display `mutation.variables` with reduced opacity while `isPending`; (b) *via `onMutate` cache write* — call `queryClient.setQueryData` optimistically, snapshot previous data, rollback via `onError`.
- **When to use it** — Tier saves, trade "like" / "pass" swipes, player re-ranking — any mutation where the server outcome is highly predictable. Avoid for high-uncertainty ops (e.g., validation-heavy trade submissions where the server may reject).
- **Expected impact** — **High (2)**: eliminates the entire perceived wait for common swipe/save interactions (typically 300–800 ms round-trip on Render). The user sees the result before the server responds.
- **RN/Flask applicability** — Fully supported by TanStack Query v5 `useMutation`. Use pattern (a) — via `variables` — for single-location displays (simpler, less code). Use pattern (b) — via `onMutate` — when the same data appears in multiple components (e.g., a trade card and a summary bar). Always call `queryClient.invalidateQueries` in `onSettled` (not `onSuccess`) to ensure a server reconciliation even after rollback.
- **Cost / risk** — Medium. Risk: visible rollback flicker if the server rejects. Rollback UX (toast + fade) must be designed. Race conditions if multiple mutations target the same query key — cancel in-flight queries with `queryClient.cancelQueries` inside `onMutate`.
- **Source(s)** — [TanStack Query: Optimistic Updates](https://tanstack.com/query/v5/docs/framework/react/guides/optimistic-updates), [How to Implement Optimistic Updates in React with React Query](https://oneuptime.com/blog/post/2026-01-15-react-optimistic-updates-react-query/view)

**Impact ladder: High**

---

### 4. Skeletons / `placeholderData` / progressive paint vs spinners

- **What it is** — Showing a layout-matching placeholder (skeleton shimmer) or stale/synthetic data (`placeholderData`) during fetch, rather than a full-screen spinner or blank state. `placeholderData` in TanStack Query serves cached data from a similar key while a fresh fetch runs in the background.
- **When to use it** — Any screen that has a known layout before data arrives: player cards, trade rows, tier columns. Prefer `placeholderData: keepPreviousData` for paginated lists so the user sees the previous page while the next loads. Use synthetic skeleton data for first-ever renders. Full spinners are acceptable only for auth gates and destructive operations with no recoverable prior state.
- **Expected impact** — **High (2)**: perceived load time drops substantially even when actual network time is unchanged. Research on SWR patterns confirms "faster feedback reduces the necessity to show spinners and results in better-perceived user experience." The `isPlaceholderData` flag lets you show a subtle loading indicator alongside real-looking content.
- **RN/Flask applicability** — `react-native-skeleton-placeholder` (npm) provides shimmer effects compatible with RN New Architecture. `placeholderData: (previousData) => previousData` is a built-in TanStack Query v5 option — no extra library needed. For trade/player lists, pair with `keepPreviousData` pattern during paginated refetch.
- **Cost / risk** — Low. Risk: skeleton layout must match real content layout — mismatches look jarring. Shimmer animations via `Animated` or Reanimated 4 add minor CPU cost; use `useNativeDriver: true` or Reanimated's worklet-based approach.
- **Source(s)** — [TanStack Query: Initial Query Data / placeholderData](https://tanstack.com/query/v4/docs/framework/react/guides/initial-query-data), [react-native-skeleton-placeholder (npm)](https://www.npmjs.com/package/react-native-skeleton-placeholder), [UX Patterns: Stale-While-Revalidate — InfoQ](https://www.infoq.com/news/2020/11/ux-stale-while-revalidate/), [Using React Query's placeholderData for Skeleton Loading](https://darius-marlowe.medium.com/using-react-querys-placeholderdata-for-skeleton-loading-with-typescript-discriminated-unions-10c60e4695c5)

**Impact ladder: High**

---

### 5. Suspense + streaming render in RN

- **What it is** — React 18 Suspense lets a component "suspend" by throwing a Promise; the nearest `<Suspense fallback>` renders the fallback until the Promise resolves. With concurrent rendering (enabled by New Architecture), React can continue rendering other parts of the tree while one subtree is suspended, and can deprioritize suspended updates when urgent interactions arrive.
- **When to use it** — Use `useSuspenseQuery` (single) or `useSuspenseQueries` (multiple, truly parallel) for queries that are required for a screen to be useful. Do NOT use `useSuspenseQuery` alone when you have multiple independent queries in the same component — each will cause a sequential suspend/resume waterfall. Use `useSuspenseQueries` or separate Suspense-wrapped sibling components instead.
- **Expected impact** — **Medium (1)**: removes "loading skeleton flicker" caused by rapid `isPending → data` transitions; enables `startTransition` to keep the current screen interactive while the next one loads. Not a raw latency fix, but measurably improves perceived smoothness.
- **RN/Flask applicability** — Fully supported since RN 0.76 (New Architecture stable). Expo SDK 54 ships with New Architecture on by default. Hermes V1 (RN 0.82) benchmarks show 2.5–9% TTI improvements with concurrent features. Pair with `<Suspense fallback={<PlayerSkeleton />}>` wrapping screens. Note: `useSuspenseQueries` internally uses `Promise.all`, so true parallelism is guaranteed.
- **Cost / risk** — Medium. Requires component tree restructuring to place `<Suspense>` boundaries correctly. Error boundaries must be added alongside each Suspense boundary. Streaming (server-driven chunk delivery) is a web/React Server Components concept and does not apply to RN's client-side fetch model — the term "streaming render" here means concurrent rendering of suspended subtrees, not HTTP streaming.
- **Source(s)** — [React Native: New Architecture is here (RN Blog, Oct 2024)](https://reactnative.dev/blog/2024/10/23/the-new-architecture-is-here), [TanStack Query: Parallel Queries — useSuspenseQueries](https://tanstack.com/query/v5/docs/framework/react/guides/parallel-queries), [TanStack Query Discussion: Suspense + parallel fetching #5946](https://github.com/TanStack/query/discussions/5946)

**Impact ladder: Medium**

---

### 6. Request deduplication + in-flight coalescing

- **What it is** — TanStack Query automatically deduplicates concurrent requests for the same `queryKey`: if component A and component B both mount simultaneously and both call `useQuery({ queryKey: ['players'] })`, only one network request is made. Both components share the single in-flight promise.
- **When to use it** — This is on by default; no API call needed. The tactic is to *preserve* deduplication by using stable, serializable query keys. Unstable keys (object literals created inline, functions as keys) break deduplication and cause duplicate requests. This is as much a "don't break it" pattern as an "add it" pattern.
- **Expected impact** — **Medium (1)** when broken (avoids duplicate 4.8 MB player fetches); **Minimal (0.25)** when working correctly (it's already free).
- **RN/Flask applicability** — Works natively in TanStack Query v5. Key rule: query keys must be JSON-serializable. TanStack Query uses its `hashKey` function (deterministic JSON serialization) to compare keys. Unstable references — e.g., `queryKey: [{ filter: filterObj }]` where `filterObj` is re-created on every render — will fail to deduplicate and trigger the "duplicate queryKey" console warning.
- **Cost / risk** — Minimal if keys are kept stable. Risk: `queryKey` arrays that include non-serializable values (class instances, functions, `undefined` mid-array) silently prevent deduplication without obvious errors.
- **Source(s)** — [TanStack Query Discussion: Request deduplication #553](https://github.com/TanStack/query/discussions/553), [React Data Fetching Best Practices — rtcamp](https://rtcamp.com/handbook/react-best-practices/data-loading/), [Deduplicating Parallel Queries in TanStack Query](https://matthuggins.com/blog/posts/deduplicating-parallel-queries-in-tanstack-query-react-query)

**Impact ladder: Medium** (to fix deduplication breakage); **Minimal** (ongoing maintenance)

---

### 7. Poll backoff + jitter for job-status polling

- **What it is** — For long-running backend jobs (e.g., Elo recalculation, trade-score batch), client polling checks status repeatedly. Fixed-interval polling wastes requests when the job is still running and hammers a recovering server when many clients reconnect simultaneously. Exponential backoff + full jitter spaces requests out: `sleep = random(0, min(cap, base * 2^attempt))`. Jitter prevents the "thundering herd" where all clients retry at the same moment after a server restart.
- **When to use it** — Any async job whose completion time is unpredictable. Do NOT poll with a fixed interval shorter than your server's response time — this can queue up requests faster than the server can drain them.
- **Expected impact** — **Medium (1)**: reduces unnecessary server load by 60–80% vs fixed polling; eliminates Render dyno CPU spikes on reconnect. Direct latency to the user is unchanged, but retry storms during Render restarts become non-events.
- **RN/Flask applicability** — TanStack Query's `refetchInterval` accepts a function: `(query) => query.state.data?.status === 'complete' ? false : computeBackoffInterval(query.state.dataUpdateCount)`. Implement `computeBackoffInterval` as `Math.random() * Math.min(30_000, 1_000 * 2 ** attempt)` (full-jitter formula). Set `refetchIntervalInBackground: false` (default) so polling pauses when the app is backgrounded — the job can continue server-side; the client re-checks on foreground. Flask backend needs no changes.
- **Cost / risk** — Low. The function form of `refetchInterval` is a single file change. Risk: under-tuned base/cap values can still over-poll; cap at 30 s for user-visible job feedback.
- **Source(s)** — [TanStack Query: Polling](https://tanstack.com/query/latest/docs/framework/react/guides/polling), [Exponential Backoff and Jitter — AWS Architecture Blog](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/), [Requests at Scale — Exponential Backoff with Jitter](https://medium.com/@titoadeoye/requests-at-scale-exponential-backoff-with-jitter-with-examples-4d0521891923)

**Impact ladder: Medium**

---

### 8. Pagination / infinite scroll / windowed fetch for large lists

- **What it is** — Instead of fetching all records in one request (the current 4.8 MB player payload), paginate the API and fetch additional pages on demand. `useInfiniteQuery` manages the page cursor and accumulated pages. FlashList (Shopify) replaces FlatList's virtualization model with cell recycling, eliminating mount/unmount overhead for off-screen rows.
- **When to use it** — Any list with > ~50 rows where the full dataset doesn't need to be in memory simultaneously. Prefer cursor-based pagination over offset pagination for consistency under concurrent writes.
- **Expected impact** — **Massive (3)**: initial payload reduction from 4.8 MB to one page (~50–100 rows, est. 50–100 KB) saves 4–10 s on the first load on a slow connection. FlashList benchmarks show 10× faster JS thread execution and 5× faster UI thread vs FlatList for complex cells; a real-world 600-item list case study showed 54% FPS improvement and 82% CPU reduction.
- **RN/Flask applicability** — Backend: add `?page=N&per_page=50` query params to `/players` and `/trades` endpoints (Flask `request.args`). Frontend: replace `useQuery` with `useInfiniteQuery({ getNextPageParam: (lastPage) => lastPage.nextCursor })`. FlatList `data` prop receives `data.pages.flatMap(p => p.items)`. Replace `<FlatList>` with `<FlashList estimatedItemSize={72}>` (Shopify FlashList, `@shopify/flash-list`). Set `onEndReachedThreshold={0.3}` — triggers `fetchNextPage` when 30% of the remaining list is visible.
  - FlatList tuning (if staying with FlatList): `windowSize={5}`, `maxToRenderPerBatch={10}`, `initialNumToRender={15}`, `removeClippedSubviews={true}`.
- **Cost / risk** — High effort (3) for full pagination (backend + frontend schema change, infinite scroll UX, edge cases on list reconciliation). FlashList swap alone is Low (1) — near drop-in replacement. Risk: cursor pagination requires stable sort order on the backend; offset pagination suffers from duplicates/gaps under concurrent writes.
- **Source(s)** — [TanStack Query: Infinite Queries](https://tanstack.com/query/v4/docs/react/guides/infinite-queries), [Pagination in React Native: useQuery vs useInfiniteQuery](https://gabrielvrl.medium.com/pagination-in-react-native-usequery-vs-useinfinitequery-7db763b6adb7), [FlashList vs FlatList — Whitespectre](https://www.whitespectre.com/ideas/better-lists-with-react-native-flashlist/), [React Native FlatList with useInfiniteQuery (TanStack discussion #1218)](https://github.com/TanStack/query/discussions/1218)

**Impact ladder: Massive** (pagination of player payload) / **High** (FlashList swap)

---

### 9. Client-side stale-while-revalidate (`staleTime` / `gcTime` tuning)

- **What it is** — `staleTime` is the window during which cached data is considered fresh and no background refetch is triggered on mount or focus. `gcTime` (formerly `cacheTime`) controls how long unused cache entries stay in memory after their last observer unmounts. The default `staleTime: 0` means every component mount triggers a background refetch — on a busy screen this can fire 5–10 redundant requests per navigation.
- **When to use it** — Set `staleTime` aggressively for data that doesn't change frequently. Set `gcTime > staleTime` so that when stale data IS refetched, the old data is still in memory to serve as `placeholderData`.
- **Expected impact** — **High (2)**: eliminates the majority of redundant background fetches on navigation. For FTF's player metadata (changes once/week at most), `staleTime: 5 * 60_000` removes essentially all repeat fetches within a session. The 4.8 MB player payload fetched on every league-switch becomes a one-time cost.
- **RN/Flask applicability** — Set globally in `QueryClient` constructor; override per-query as needed. No backend changes required. Wire `focusManager` and `onlineManager` to RN's `AppState` and `NetInfo` (see Tactic 10 below) — without this, `refetchOnWindowFocus` and `refetchOnReconnect` are effectively always false on RN, which means `staleTime` alone controls revalidation timing.
  - Recommended starting values (see "Recommended defaults" section below).
- **Cost / risk** — Minimal (0.5 effort: one config change). Risk: over-large `staleTime` serves stale data after a backend update. Mitigate with targeted `queryClient.invalidateQueries` after mutations that change shared state.
- **Source(s)** — [TanStack Query: Important Defaults](https://tanstack.com/query/v4/docs/framework/react/guides/important-defaults), [Understanding staleTime vs gcTime in TanStack Query](https://medium.com/@bloodturtle/understanding-staletime-vs-gctime-in-tanstack-query-e9928d3e41d4), [Caching with TanStack Query — Telerik](https://www.telerik.com/blogs/caching-tanstack-query)

**Impact ladder: High**

---

### 10. Debounce / throttle of user-triggered fetches

- **What it is** — Delaying the start of a fetch until user input has settled (debounce) or rate-limiting how often a fetch can fire (throttle). TanStack Query does not debounce queries internally by design (would add ~1.1 KB and violates the principle of separation of concerns). The recommended pattern is to debounce the *query key value* — the query only fires when the debounced state changes.
- **When to use it** — Search inputs, filter controls, any text field that drives a query. Do NOT debounce navigational fetches (user pressed a button — fire immediately).
- **Expected impact** — **Medium (1)**: on a 300 ms debounce of a search field, keystrokes at 5 WPM (~1 key/200 ms) fire ~1 request every 500 ms instead of 5 requests per second. Reduces backend load and prevents in-flight races that cause out-of-order result display.
- **RN/Flask applicability** — Implement a `useDebounce(value, 300)` hook; pass the debounced value into the `queryKey`. TanStack Pacer (`@tanstack/pacer`) is the emerging first-party solution, providing `useDebouncedCallback` and `useThrottledCallback` designed to integrate cleanly with TanStack Query. Also consider React 18's `useDeferredValue` for search — defers the query key update to a low-priority render, keeping the input responsive without a manual timer.
- **Cost / risk** — Low (1 day: add a hook, thread the debounced value). Risk: too long a debounce (>500 ms) makes search feel unresponsive. Start at 300 ms; allow per-query tuning.
- **Source(s)** — [TanStack Query Discussion: Proposal — Add Debouncing to useQuery #8423](https://github.com/TanStack/query/discussions/8423), [TanStack Pacer: Solving Debounce, Throttle, and Batching](https://shaxadd.medium.com/tanstack-pacer-solving-debounce-throttle-and-batching-the-right-way-94d699befc8a), [Debouncing while using React Query](https://lkioi.hashnode.dev/debouncing-while-using-react-query), [TanStack Pacer: react-query-debounced-prefetch example](https://tanstack.com/pacer/latest/docs/framework/react/examples/react-query-debounced-prefetch)

**Impact ladder: Medium**

---

## Anti-patterns to flag in the audit

The following code smells should be grepped for during the codebase audit phase. Each maps directly to a tactic above.

1. **Sequential awaits in the same scope with no data dependency** — `const a = await queryA(); const b = await queryB(a_not_used);` — classic waterfall. Should be `Promise.all` or `useQueries`. Grep: `await fetch` or `useQuery` + `useQuery` in sequence in the same component without `enabled` dependency.

2. **`useQuery` without `staleTime` at call site and no global default set** — every mount triggers a background refetch. Grep: `useQuery({` with no `staleTime` in the options object AND no `defaultOptions` in QueryClient constructor.

3. **Fixed `refetchInterval` on a job-status query** — `refetchInterval: 2000` never stops. Grep: `refetchInterval:` with a numeric literal (not a function).

4. **Inline object literal as `queryKey`** — `queryKey: [{ filter: { leagueId } }]` where the object is created on every render. Breaks deduplication. Grep: `queryKey: [\{` without wrapping in `useMemo`.

5. **`onSuccess` used for cache invalidation instead of `onSettled`** — `onSuccess: () => queryClient.invalidateQueries(...)`. After a rollback `onSuccess` does not fire; `onSettled` always does. Grep: `onSuccess:` inside `useMutation` options.

6. **FlatList with no `windowSize`, `maxToRenderPerBatch`, or `initialNumToRender` on lists > 50 items** — default FlatList settings render too many items. Grep: `<FlatList` without those props near `data={players}` or similar large arrays.

7. **`data.map(...)` to flatten `useInfiniteQuery` pages outside a `useMemo`** — `data.pages.flatMap(p => p.items)` on every render. Grep: `.pages.flatMap` or `.pages.map` inside a render function body without memo.

8. **No `focusManager` / `onlineManager` RN wiring** — without this, `refetchOnWindowFocus` and `refetchOnReconnect` are inert on mobile. Grep: absence of `focusManager.setEventListener` or `AppState.addEventListener` in the app bootstrap.

9. **Unguarded `enabled` on dependent queries** — `enabled: someValue` where `someValue` could be `0` or `""` (falsy but defined). Should be `enabled: !!someValue`. Grep: `enabled: [^!]` in `useQuery` options.

10. **Search input `onChangeText` directly setting a query key state** — fires a fetch on every keystroke. Grep: `onChangeText` with `setQuery` or `setSearch` that is directly in a `queryKey` array without a debounce step.

---

## Recommended defaults for FTF

These are opinionated starting values; measure and tune per screen after instrumenting with Flipper / Reactotron / React DevTools profiler.

```ts
// QueryClient global defaults
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Player metadata changes at most once/week; 5 min prevents re-fetching
      // on every navigation within a session.
      staleTime: 5 * 60 * 1_000,          // 5 minutes

      // Keep unused cache entries for 10 min to support
      // back-navigation without refetch; gcTime > staleTime is required.
      gcTime: 10 * 60 * 1_000,            // 10 minutes

      // Wire to AppState (see focusManager setup below).
      refetchOnWindowFocus: true,          // effective only after focusManager is wired

      // Wire to NetInfo (see onlineManager setup below).
      refetchOnReconnect: true,            // effective only after onlineManager is wired

      // 3 retries with built-in exponential backoff is the default;
      // keep it. Override per-query for job-status polls.
      retry: 3,
    },
    mutations: {
      // Re-throw by default so callers can handle errors explicitly.
      throwOnError: false,
    },
  },
})
```

```ts
// focusManager — wire to AppState in app bootstrap (e.g. App.tsx)
import { focusManager } from '@tanstack/react-query'
import { AppState, Platform } from 'react-native'

if (Platform.OS !== 'web') {
  focusManager.setEventListener((handleFocus) => {
    const subscription = AppState.addEventListener('change', (state) => {
      handleFocus(state === 'active')
    })
    return () => subscription.remove()
  })
}
```

```ts
// onlineManager — wire to NetInfo in app bootstrap
import { onlineManager } from '@tanstack/react-query'
import NetInfo from '@react-native-community/netinfo'

onlineManager.setEventListener((setOnline) => {
  return NetInfo.addEventListener((state) => {
    setOnline(!!state.isConnected)
  })
})
```

```ts
// Per-query overrides — data that changes frequently or rarely
const PLAYER_METADATA_QUERY = {
  staleTime: 5 * 60_000,    // 5 min: players don't change mid-session
  gcTime:   10 * 60_000,    // 10 min
}

const TRADE_SCORES_QUERY = {
  staleTime: 60_000,        // 1 min: trade values shift after ranking changes
  gcTime:    5 * 60_000,
}

const LEAGUE_CONFIG_QUERY = {
  staleTime: 30 * 60_000,   // 30 min: league settings rarely change mid-session
  gcTime:    60 * 60_000,
}
```

```ts
// Dynamic polling for async job status (e.g., Elo recalculation)
const BASE_MS = 1_000
const CAP_MS  = 30_000

useQuery({
  queryKey: ['job', jobId],
  queryFn: fetchJobStatus,
  refetchInterval: (query) => {
    if (query.state.data?.status === 'complete') return false
    const attempt = query.state.dataUpdateCount
    // Full-jitter formula (AWS recommendation)
    return Math.random() * Math.min(CAP_MS, BASE_MS * 2 ** attempt)
  },
  refetchIntervalInBackground: false,  // pause when app is backgrounded
})
```

```ts
// Debounced search — debounce the key value, not the fetch
function usePlayerSearch(rawQuery: string) {
  const debouncedQuery = useDebounce(rawQuery, 300)
  return useQuery({
    queryKey: ['players', 'search', debouncedQuery],
    queryFn: () => searchPlayers(debouncedQuery),
    enabled: debouncedQuery.length >= 2,
    staleTime: 60_000,
  })
}
```

```ts
// FlashList + useInfiniteQuery for large player/trade lists
// prerequisite: @shopify/flash-list installed
<FlashList
  data={data?.pages.flatMap(p => p.items) ?? []}
  estimatedItemSize={72}           // measure actual row height once
  renderItem={renderPlayerCard}
  keyExtractor={(item) => item.id}
  onEndReached={() => { if (hasNextPage) fetchNextPage() }}
  onEndReachedThreshold={0.3}
  ListFooterComponent={isFetchingNextPage ? <RowSkeleton /> : null}
/>
```

```ts
// Parallel queries — replace waterfall useQuery calls
const [playersQuery, scoresQuery, leagueQuery] = useQueries({
  queries: [
    { queryKey: ['players'], queryFn: fetchPlayers, staleTime: PLAYER_METADATA_QUERY.staleTime },
    { queryKey: ['trade-scores', leagueId], queryFn: () => fetchTradeScores(leagueId), enabled: !!leagueId },
    { queryKey: ['league', leagueId], queryFn: () => fetchLeague(leagueId), enabled: !!leagueId },
  ],
})
```

---

## Open questions / needs measurement

1. **Actual 4.8 MB breakdown** — is the player payload compressible with gzip/Brotli on the Flask side? What is the decompressed vs wire size? Needs a timed `curl -v --compressed` against the Render endpoint. If Render's Nginx proxy already applies gzip at the edge, the effective size may already be much lower.

2. **Render cold-start real p99** — the 15–30 s range quoted in the brief is anecdotal. A 30-day p50/p99 from Render's metrics panel (or an external ping log) would sharpen the ROI case for the keep-warm ping strategy.

3. **staleTime impact in practice** — with `staleTime: 0` (current default), how many redundant requests does a typical session generate? Needs Flipper network inspector or a custom `queryClient.getQueryCache().subscribe` counter for one user session.

4. **FlashList compatibility with Reanimated 4** — Shopify FlashList uses its own layout engine; verify no conflicts with Reanimated 4's `useAnimatedStyle` usage in tier and trade card components before committing to the swap.

5. **Render paid tier breakeven** — at what request rate does upgrading to a Render paid instance (always-on) cost less in user-abandonment loss than the free-tier cold-start keep-warm workaround? A simple conversion-rate × ARPU estimate would make this decision clear.

6. **Backend pagination readiness** — does the `/players` Flask route support cursor or offset pagination today? If not, the effort estimate for tactic 8 is understated by the backend work required.

---

*Primary sources consulted during research:*
- [TanStack Query: Request Waterfalls](https://tanstack.com/query/v5/docs/framework/react/guides/request-waterfalls)
- [TanStack Query: Parallel Queries](https://tanstack.com/query/v5/docs/framework/react/guides/parallel-queries)
- [TanStack Query: Prefetching & Router Integration](https://tanstack.com/query/latest/docs/framework/react/guides/prefetching)
- [TanStack Query: Optimistic Updates](https://tanstack.com/query/v5/docs/framework/react/guides/optimistic-updates)
- [TanStack Query: Polling](https://tanstack.com/query/latest/docs/framework/react/guides/polling)
- [TanStack Query: Infinite Queries](https://tanstack.com/query/v4/docs/react/guides/infinite-queries)
- [TanStack Query: Important Defaults](https://tanstack.com/query/v4/docs/framework/react/guides/important-defaults)
- [TanStack Query: React Native Guide](https://tanstack.com/query/v5/docs/framework/react/react-native)
- [AWS Architecture Blog: Exponential Backoff and Jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)
- [React Native: New Architecture is here (Oct 2024)](https://reactnative.dev/blog/2024/10/23/the-new-architecture-is-here)
- [Expo SDK 54 Changelog](https://expo.dev/changelog/sdk-54)
- [FlashList vs FlatList — Whitespectre](https://www.whitespectre.com/ideas/better-lists-with-react-native-flashlist/)
- [Render free-tier cold-start guide](https://blog.samkiel.dev/your-render-free-tier-is-not-broken-its-just-cold)
- [UX Patterns: Stale-While-Revalidate — InfoQ](https://www.infoq.com/news/2020/11/ux-stale-while-revalidate/)
- [TanStack Pacer — debounce/throttle integration](https://tanstack.com/pacer/latest/docs/framework/react/examples/react-query-debounced-prefetch)
