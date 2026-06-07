# 04 — React Native Rendering & List Performance

## TL;DR

- **FlashList v2 over FlatList** for any list of 20+ items: recycling + synchronous new-arch layout measurements eliminate blank cells and sustain 60 FPS on low-end Android at near-zero API-surface cost.
- **Memoize list rows unconditionally** (`React.memo` + `useCallback` for `renderItem`): a single parent re-render propagates to every mounted row if rows are not memoized, which is the most common source of list jank in data-heavy RN apps.
- **Reanimated 4 animations already run on the UI thread**; the risk is accidental JS thread reads of shared values and un-memoized gesture objects in list rows — both easy to grep for.
- **Hermes bytecode** cuts cold TTI by 25–50 % at zero ongoing maintenance cost; gains are only visible in release builds — never profile in dev mode.
- **InteractionManager / requestIdleCallback** defers heavy work (roster processing, trade scoring) past the first paint, keeping the first frame fast even when data arrives immediately.
- **expo-image with `memory-disk` cache policy + `recyclingKey`** is the correct choice for avatar-heavy ranked lists; it uses SDWebImage/Glide and avoids re-decoding on list-cell recycling.
- **Zustand `useShallow` selectors** prevent whole-screen re-renders when only a subset of store state changes — critical for screens that subscribe to the full player cache.

---

## Why it matters for FTF

FTF's known pain is that "data-heavy screens feel slow to become interactive." The four most affected surfaces are:

| Surface | Rendering challenge |
|---|---|
| Trade card deck (swipeable) | Each card is a complex component with animated Reanimated gestures; gesture objects recreated on each render cause dropped frames |
| Tiers board (draggable) | Potentially 100+ player chips in simultaneous animated drag states; UI-thread budget exhausted quickly |
| Ranked player lists | Long lists with avatar images, tier badges, and Elo deltas; blank cells and re-render cascades from un-memoized rows |
| Match lists | Per-item "awaiting them" state requires fine-grained Zustand subscriptions; coarse subscriptions trigger full list re-renders |

The backend Render free-tier adds a cold-start latency window (≥10 s) where the JS bundle is already parsed and the UI is interactive — but nothing to show. That makes **TTI optimisation** (fast first paint + deferred heavy work) unusually high-value here compared to a typical app.

---

## Tactics

### 1. React.memo for list row components

- **What it is** — Wraps a component so it only re-renders when its own props change (shallow equality by default). A custom comparator can be passed as the second argument for deep equality on specific fields.
- **When to use it** — On every component passed to `renderItem` / `FlashList`'s `renderItem`. Also on card components in a swipeable deck that share a common parent. Do **not** apply to components that are genuinely stateful from context or that always receive new prop references — the memo comparison overhead then costs more than it saves.
- **Expected impact** — **High (I=2)**. A single `setData()` call on the parent would otherwise re-render every mounted row; with memo each row re-renders only when its own item changes. On a 50-item list this eliminates ~49 wasted renders per data refresh.
- **RN/Flask applicability** — Pure React; no library needed. TanStack Query's `select` option already returns stable references when data hasn't changed (structural sharing), but row-level memo is still required because the parent component re-renders on query state transitions (loading → success).
- **Cost / risk** — Low. Custom comparators can silently skip needed updates if written incorrectly. Prefer the default shallow comparator and ensure prop objects are stable (see tactics 2 & 3).
- **Sources** — [React docs: memo](https://react.dev/reference/react/memo), [RN FlatList optimization guide](https://reactnative.dev/docs/optimizing-flatlist-configuration)

---

### 2. useCallback / useMemo for stable prop references

- **What it is** — `useCallback` memoizes a function reference; `useMemo` memoizes a value. Both break only when listed dependencies change, preventing unnecessary `React.memo` invalidations caused by new object/function references on each parent render.
- **When to use it** — `useCallback` on every `renderItem`, `onPress`, and `keyExtractor` passed to a list. `useMemo` on derived data (filtered/sorted player arrays, computed trade objects). **When NOT to**: on cheap computations that run faster than the memo bookkeeping (~<0.1 ms); on callbacks whose deps change every render anyway (the memoisation never hits).
- **Expected impact** — **Medium–High (I=1–2)** combined with `React.memo`. Without stable `renderItem`, every parent re-render invalidates memo on every row. With both: render cost becomes proportional to changed items only.
- **RN/Flask applicability** — Pure React. Note: if Expo SDK 54 ships the **React 19 Compiler** stable (it was experimental in SDK 53, standard in SDK 54 per Sentry's 2025 guide), the compiler auto-memoizes pure functions and may make manual `useCallback`/`useMemo` redundant — verify whether the compiler is enabled in this project before auditing for missing memos.
- **Cost / risk** — Low. Stale-closure bugs are the main failure mode when dependency arrays are incomplete (ESLint `exhaustive-deps` rule catches these).
- **Sources** — [React docs: useMemo](https://react.dev/reference/react/useMemo), [RN perf guide: useCallback with FlatList](https://reactnative.dev/docs/optimizing-flatlist-configuration), [Sentry RN perf strategies](https://blog.sentry.io/react-native-performance-strategies-tools/)

---

### 3. Zustand useShallow selectors

- **What it is** — `useShallow` from `zustand/react/shallow` wraps a selector so the component only re-renders when the **values** returned by the selector change (shallow equality), not when the selector produces a new object/array reference on every store update.
- **When to use it** — Any component that selects multiple fields: `const { trades, isLoading } = useStore(useShallow(s => ({ trades: s.trades, isLoading: s.isLoading })))`. Essential for list screens that subscribe to the player cache: without it, any background cache update triggers a full list re-render.
- **Expected impact** — **High (I=2)** for list screens. Coarse subscriptions to large Zustand slices (e.g., the full player map) cause full-screen re-renders on every cache update. `useShallow` with a narrow selector reduces this to zero re-renders unless the selected fields change.
- **RN/Flask applicability** — Zustand is already in the FTF stack. Requires importing `useShallow` from `zustand/react/shallow` (available in Zustand v4+).
- **Cost / risk** — Minimal. One-line change per subscription. Risk: selectors that return derived arrays still produce new references on every call even with `useShallow` — use `useMemo` inside the component for those.
- **Sources** — [Zustand: prevent re-renders with useShallow](https://zustand.docs.pmnd.rs/learn/guides/prevent-rerenders-with-use-shallow), [Zustand GitHub](https://github.com/pmndrs/zustand)

---

### 4. FlashList v2 (preferred) vs FlatList tuning

#### FlashList v2 — preferred path

- **What it is** — Shopify's complete rewrite of FlatList. Recycles existing native views (instead of unmounting/remounting), uses synchronous New Architecture layout measurements via `useLayoutEffect`, and requires no `estimatedItemSize` in v2 (progressive measurement).
- **When to use it** — Any list of 20+ homogeneous or type-grouped items: ranked player lists, match lists, trade history. **When NOT to**: very short lists (< 10 items), lists whose items have complex interactive states that don't survive recycling (custom `recyclingKey` solves most cases).
- **Expected impact** — **Massive (I=3)** for long ranked lists. FlashList v2 delivers up to 50 % reduced blank area vs v1 on the new architecture and sustains 60 FPS on low-end Android where FlatList drops to ~40 FPS. 2 million monthly downloads; powers Shopify's production mobile app.
- **RN/Flask applicability** — Expo SDK 46+; direct FlatList API replacement. Key props: `renderItem`, `data`, `getItemType` (for heterogeneous items), `keyExtractor`, `drawDistance`. No `estimatedItemSize` required in v2.
- **Cost / risk** — Medium (E=1–2). The key anti-pattern in FlashList is using the `key` prop inside item components or nested children — this degrades recycling performance. Items with complex animations (Reanimated) need `recyclingKey` reset to blank the view on reuse. `maintainVisibleContentPosition` is enabled by default in v2.
- **Sources** — [FlashList v2 engineering blog](https://shopify.engineering/flashlist-v2), [FlashList performant components (v1 guide, principles still apply)](https://shopify.github.io/flash-list/docs/1.x/fundamentals/performant-components/)

#### FlatList tuning — when FlashList is not yet adopted

| Prop | Default | FTF recommended | Rationale |
|---|---|---|---|
| `windowSize` | 21 | **5–9** | Ranked lists are long; 21 viewports wastes memory. 5 = 2 above + 2 below + current. |
| `maxToRenderPerBatch` | 10 | **5–8** | Reduces JS-thread blocking per scroll event; accept slightly more blank area. |
| `initialNumToRender` | 10 | **8–12** | Match visible items on first paint; avoid over-rendering off-screen. |
| `updateCellsBatchingPeriod` | 50 ms | **50–80 ms** | Default is fine; increase to 80 if JS thread is already loaded. |
| `getItemLayout` | — | **Provide if fixed height** | Eliminates async layout measurement pass; significant on 50+ item lists. |
| `keyExtractor` | — | **Always provide** | Use stable player/trade IDs, never array index for reorderable lists. |
| `removeClippedSubviews` | true (Android) | **Leave default** | True on Android is fine; do not force true on iOS (causes content gaps). |

- **Sources** — [RN FlatList optimization](https://reactnative.dev/docs/optimizing-flatlist-configuration), [RN performance overview](https://reactnative.dev/docs/performance)

---

### 5. Image loading: expo-image over RN Image

- **What it is** — `expo-image` wraps SDWebImage (iOS) and Glide (Android) — battle-tested native image caching libraries — with a React Native API that adds CSS-like layout props, blurhash placeholders, priority queuing, and a `recyclingKey` prop for FlashList recycling.
- **When to use it** — All image rendering in FTF. The built-in RN `Image` uses basic platform defaults with no disk cache management or priority control.
- **Expected impact** — **High (I=2)** for avatar-dense ranked lists. Native caching eliminates repeat network decoding; `recyclingKey` prevents showing the previous player's avatar during FlashList cell recycling. BlurHash placeholders eliminate layout shifts on first load.
- **RN/Flask applicability** — Already in Expo SDK 54. No additional install needed. Backend should serve player avatar URLs as stable (same URL = same image), which enables disk cache hits across sessions.
- **Cost / risk** — Low. `recyclingKey` must be set to the player/item ID when used in FlashList; omitting it causes stale avatar flicker. `configureCache()` on iOS allows capping disk cache size (recommend 100–150 MB for player avatars).
- **Recommended config for FTF avatar lists**:
  ```js
  <Image
    source={{ uri: player.avatarUrl }}
    cachePolicy="memory-disk"
    priority="normal"     // bump to "high" for above-fold items
    placeholder={{ blurhash: player.avatarBlurhash }}
    transition={150}
    recyclingKey={player.id}   // required in FlashList
    contentFit="cover"
  />
  ```
- **Sources** — [expo-image docs](https://docs.expo.dev/versions/latest/sdk/image/)

---

### 6. Reanimated 4 + New Architecture: keeping work on the UI thread

- **What it is** — Reanimated 4 runs all animations (CSS-based and worklet-based) on the UI thread via JSI, decoupled from the JS thread. `useSharedValue`, `useAnimatedStyle`, `useDerivedValue`, and `useAnimatedGestureHandler` execute inside a worklet runtime on the UI thread.
- **When to use it** — All gesture-driven animations (swipeable trade cards, draggable tier chips): use `useSharedValue` + `useAnimatedStyle` and keep all transform logic in worklets. Use `runOnJS` **only** for side effects that must update React state (e.g., committing a swipe decision).
- **Expected impact** — **Massive (I=3)** for the swipeable card deck and tiers drag. Animations run at 60–120 FPS even when the JS thread is blocked processing Elo ranking data. JS-thread animation (Animated API with no `useNativeDriver`) drops frames during data-heavy operations.
- **RN/Flask applicability** — Reanimated 4 + gesture-handler already in the FTF stack. **Required new-arch feature flags** (add to `react-native.config.js` or the feature flags API):
  - `DISABLE_COMMIT_PAUSING_MECHANISM` (RN 0.81+): eliminates animated-component scroll flickering
  - `USE_COMMIT_HOOK_ONLY_FOR_REACT_COMMITS` (RN 0.80+, Reanimated 4.2.0+): restores FPS when many animated components are scrolling simultaneously
  - `IOS_SYNCHRONOUSLY_UPDATE_UI_PROPS` / `ANDROID_SYNCHRONOUSLY_UPDATE_UI_PROPS`: fast-path for non-layout style updates
- **Cost / risk** — Medium (E=2 to enable flags + audit). Main failure modes: (a) reading `sharedValue.value` on the JS thread (blocks until UI-thread sync — repeat reads in a hot render path add up); (b) per-frame `runOnJS` calls (each call crosses the thread boundary and serializes); (c) gesture objects (`Gesture.Pan()`) created inline in `renderItem` without `useMemo` — recreated on every parent re-render, breaking gesture handler registration.
- **Component animation limits** — Low-end Android: max ~100 simultaneously animated components. iOS: ~500. Tiers board with 100+ chips is at the Android limit; use `react-native-skia` for the drag shadow/overlay rather than individual animated chip components if needed.
- **Sources** — [Reanimated performance guide](https://docs.swmansion.com/react-native-reanimated/docs/guides/performance/), [Reanimated 4 blog post](https://blog.swmansion.com/reanimated-4-is-new-but-also-very-familiar-b926dd59aa40), [New arch perf regression flags](https://docs.swmansion.com/react-native-reanimated/docs/guides/performance/)

---

### 7. Hermes: bytecode compilation and TTI

- **What it is** — Hermes is the default JS engine for React Native. At release build time, Metro compiles JS to Hermes bytecode (`.hbc`), which the device executes without parsing — the costliest startup step for traditional JS engines.
- **When to use it** — Already enabled by default in RN 0.76+ / Expo SDK 54. No configuration needed. **Verify**: `global.HermesInternal !== undefined` at runtime. Benefits only materialise in **release builds** — development builds skip bytecode compilation.
- **Expected impact** — **Massive (I=3)** for cold start. Benchmarks: ~55 % faster app startup (4.5 s → 2.0 s in one study), 26 % lower memory usage, 7–25 % TTI improvement across multiple Meta/community benchmarks. Impact is larger on Android (historically slower JS parsing) but significant on iOS too.
- **RN/Flask applicability** — No changes needed. Confirm in `app.json`/`app.config.js` that `jsEngine: "hermes"` is set (Expo SDK 54 default). For Hermes V1 (RN 0.82+): additional startup improvements expected; FTF is on RN 0.81 so standard Hermes is active.
- **Cost / risk** — Zero ongoing cost. Only risk: non-standard bundle loading paths (dynamic require, custom metro transforms) may load JS without the `.hbc` optimisation — verify with profiling.
- **Sources** — [RN Hermes docs](https://reactnative.dev/docs/hermes), [FB engineering: Hermes announcement](https://engineering.fb.com/2019/07/12/android/hermes/), [Toward Hermes being default](https://reactnative.dev/blog/2021/10/26/toward-hermes-being-the-default), [Hermes V1 in RN 0.82](https://medium.com/react-native-journal/hermes-v1-in-react-native-0-82-unlocking-faster-startup-times-bfd0cf1b107c)

---

### 8. JS thread vs UI thread; InteractionManager / requestIdleCallback

- **What it is** — React Native has two primary threads relevant to rendering: the **JS thread** (React reconciliation, business logic, TanStack Query callbacks, event handlers) and the **UI/main thread** (native view updates, Reanimated worklets, ScrollView, native stack navigation). A 16 ms frame budget applies to both. JS thread overrun causes touch unresponsiveness and animation jank; UI thread overrun drops frames.
- **InteractionManager.runAfterInteractions** defers a callback until all active touches and animations complete. **`requestIdleCallback`** (the current recommended API; `InteractionManager` is deprecated) fires when the JS thread is idle between frames.
- **When to use it** — Defer: initial trade scoring computation, Elo delta calculations for all players, sorting the full ranked list, TanStack Query `select` transforms on 4.8 MB player payloads. Keep on the critical path: only what's needed to paint the first visible items.
- **Expected impact** — **High (I=2)** for the "slow to become interactive" problem. Moving 200 ms of player-list processing off the mount path directly reduces TTI by that amount. Visible as the difference between a blank screen with a spinner versus a usable list that loads more data in the background.
- **RN/Flask applicability** — Pure RN API. For heavy synchronous transforms on the player payload (filtering, sorting 4.8 MB), consider TanStack Query's `select` option (runs on the query thread, off the render path) combined with `useMemo` with a stable selector.
- **Cost / risk** — Low–Medium (E=1). Deferred work that mutates visible state can cause a brief layout jump if not handled carefully (show skeleton → deferred render → reveal). `requestIdleCallback` has a 50 ms default timeout.
- **Sources** — [RN InteractionManager](https://reactnative.dev/docs/interactionmanager) (notes deprecation in favour of `requestIdleCallback`), [RN performance overview](https://reactnative.dev/docs/performance)

---

### 9. Bundle / TTI: lazy screen loading

- **What it is** — React.lazy + Suspense (or Expo Router's async routes) defer loading a screen's JS bundle until the user navigates to it, reducing the initial bundle evaluated at boot.
- **When to use it** — Heavy secondary screens (Tiers board, Trade detail) that are not the landing screen. The trade card deck and ranked list (core screens) should stay in the main bundle. **When NOT to**: async routes in Expo Router do not yet support native production builds (as of mid-2025) — web-only or development-only. For production native, use `React.lazy` + Suspense per-screen inside the navigation stack.
- **Expected impact** — **Medium (I=1)** for TTI. Removing a 200–400 KB heavy screen module from the boot bundle reduces parse time. Expo Atlas can quantify module size per route before/after.
- **RN/Flask applicability** — Expo Router is already in use. For native: standard React.lazy in the navigation config. For web build: enable async routes in `app.json` (`"experiments": { "asyncRoutes": true }`). Use Expo Atlas (`EXPO_ATLAS=1 npx expo export`) to identify the heaviest modules.
- **Cost / risk** — Medium (E=2). Requires Suspense boundaries with loading fallbacks. Async routes (web) require additional testing.
- **Sources** — [Expo Router async routes](https://expo.dev/changelog/2024-01-23-router-3), [Callstack: code splitting in RN](https://www.callstack.com/blog/code-splitting-in-react-native-applications), [Sentry: RN performance tactics](https://blog.sentry.io/react-native-performance-strategies-tools/)

---

### 10. Measuring: RN DevTools, Perf Monitor, Sentry performance spans

#### React Native DevTools (React Profiler)

- Open via `j` in Metro / Expo Dev Client → "Open React DevTools"
- **React Profiler panel**: records a flame graph of component render timing and commit durations. Enable "Highlight updates when components render" to see live re-render overlays.
- **Performance panel**: unified timeline showing JS execution, React tracks, network events, and custom User Timings.
- Primary tool for identifying unnecessary re-renders and slow commit paths.
- **Source**: [RN DevTools docs](https://reactnative.dev/docs/react-native-devtools)

#### Perf Monitor (in-app)

- Shake device / Expo Dev Menu → "Show Perf Monitor"
- Shows live JS FPS and UI FPS. JS FPS drop = JS thread overload; UI FPS drop = native/Reanimated issue.
- Always test in **release mode** (`expo run:ios --configuration Release`); dev builds disable compiler optimisations and show 2–5x worse numbers.

#### Sentry Performance Spans

- `@sentry/react-native` with `Sentry.reactNavigationIntegration({ enableTimeToInitialDisplay: true })` automatically captures TTID (first frame) and TTFD (full display) per screen.
- Use `<Sentry.TimeToFullDisplay record={dataLoaded} />` for screens that fetch before rendering (trade deck, ranked list).
- Custom spans with `Sentry.startSpan({ name: 'process-player-roster' })` let you see how long heavy transforms take in production.
- **Source**: [Sentry time-to-display docs](https://docs.sentry.io/platforms/react-native/tracing/instrumentation/time-to-display/), [Sentry RN performance](https://blog.sentry.io/react-native-performance-strategies-tools/)

---

## Anti-patterns to flag in the audit

These are concrete code smells to grep for. Each maps to a tactic above.

**Re-renders**
- Inline arrow functions in `renderItem`: `renderItem={({ item }) => <Row item={item} />}` — creates a new function on every parent render, invalidating `React.memo` on every row.
- Object/array literals as props to list items: `<Row style={{ flex: 1 }} />` or `<Row ids={[player.id]} />` — new reference every render.
- Zustand subscriptions without `useShallow` that select multiple fields: `const { a, b } = useStore(s => ({ a: s.a, b: s.b }))` — returns new object every call.
- Missing `React.memo` on `renderItem` component.
- Context consumers inside list items (e.g., `useContext(PlayerContext)` in a row) — any context update re-renders every visible row.

**List configuration**
- Missing `keyExtractor` on FlatList / FlashList (uses index as default for FlatList; causes incorrect diff on reorder).
- `key` prop used inside FlashList item or its nested components — degrades recycling.
- Default `windowSize={21}` on long ranked lists without tuning.
- Missing `getItemLayout` on FlatList with fixed-height rows.
- `getItemType` absent on FlashList with heterogeneous item types (player chip vs header vs separator).

**Reanimated / gestures**
- `Gesture.Pan()` or similar gesture objects created inline in `renderItem` without `useMemo` — recreated on every render, re-registers gesture handler.
- `runOnJS` called per-animation-frame (inside `useAnimatedReaction` or `useFrameCallback` with no throttle) — saturates the JS thread at 60 calls/sec.
- Reading `sharedValue.value` on the JS thread inside a hot render path (e.g., `const pos = dragX.value` in a render function) — blocks JS thread waiting for UI-thread sync.
- Animating `top`/`left`/`width`/`height` properties instead of `transform: [{ translateX }]` — triggers layout recalculation each frame.
- Missing Reanimated new-arch feature flags (`DISABLE_COMMIT_PAUSING_MECHANISM`, `USE_COMMIT_HOOK_ONLY_FOR_REACT_COMMITS`) causing scroll-with-animation FPS regression.

**Images**
- Using RN `Image` component instead of `expo-image` in lists.
- Missing `recyclingKey` on `expo-image` inside FlashList — shows previous item's avatar during cell reuse.
- No `cachePolicy` set (defaults to `disk` only, missing memory cache layer for in-session avatar re-use).
- Large unresized avatar URLs (backend serving full-resolution images where 64×64 px suffices).

**Boot / TTI**
- Heavy synchronous work at module evaluation time (top-level `require()` of large JSON, synchronous SQLite reads, complex factory calls outside components).
- No `requestIdleCallback` / `InteractionManager` deferral for non-critical post-mount work (Elo delta recalculation, sorting the full 4.8 MB player list).
- `console.log` statements left in production bundle (creates a JS thread bottleneck on every logged statement).
- Profiling in development mode and treating those numbers as production baseline.

---

## Recommended defaults for FTF

### FlatList (when FlashList not yet adopted)

```js
<FlatList
  windowSize={7}                   // 3 viewports above + 3 below + current
  maxToRenderPerBatch={6}          // smaller batches = more responsive scroll
  initialNumToRender={10}          // match ~1 screen of items
  updateCellsBatchingPeriod={60}   // slightly relaxed; reduce blank area vs responsiveness
  getItemLayout={fixedHeightGetItemLayout}  // provide whenever row height is fixed
  keyExtractor={(item) => item.id} // always use stable domain ID
  removeClippedSubviews={undefined} // let platform default apply (true on Android)
  renderItem={memoizedRenderItem}  // wrap in useCallback; item component wrapped in memo()
/>
```

### FlashList v2 (preferred)

```js
<FlashList
  data={items}
  renderItem={memoizedRenderItem}
  keyExtractor={(item) => item.id}
  getItemType={(item) => item.type}  // if list has headers, players, separators
  drawDistance={400}                 // tune to device scroll velocity
  estimatedItemSize={72}             // v2: optional hint but still helps initial layout
/>
```

### expo-image policy

- `cachePolicy="memory-disk"` everywhere (memory layer for in-session reuse, disk for cross-session).
- `priority="high"` for the first 3 visible items in a list; `"normal"` for the rest.
- Always provide `recyclingKey={item.id}` inside FlashList.
- Use `blurhash` placeholder from the player data API response (add to backend player schema if not present).
- Cache size cap on iOS: `Image.configureCache({ maxDiskSize: 150 * 1024 * 1024 })` at app boot.

### Reanimated / gesture defaults

- All shared values read inside `useAnimatedStyle`, `useDerivedValue`, or `useAnimatedReaction` only — never in render scope.
- Gesture objects (`Gesture.Pan()`, etc.) wrapped in `useMemo` whenever inside a list item or frequently re-rendered parent.
- Enable all three new-arch performance flags before any animation profiling.
- Animate only `transform` and `opacity`; never `top`/`left`/`width`/`height` for performance-critical motion.

### Sentry instrumentation

- Enable `enableTimeToInitialDisplay: true` in `reactNavigationIntegration`.
- Add `<Sentry.TimeToFullDisplay record={!!data} />` to TradesDeckScreen, RankedListScreen, TiersScreen.
- Add custom span around the TanStack Query `select` transform for the player payload to baseline how long it takes in production.

---

## Open questions / needs measurement

1. **Does the React 19 Compiler ship enabled in Expo SDK 54 by default?** If yes, manual `useCallback`/`useMemo` on list items may already be handled; the audit should check `babel.config.js` for `react-compiler` before flagging every missing memo.
2. **How many items are visible on the ranked list and tiers board in a typical FTF session?** The windowSize and maxToRenderPerBatch recommendations above assume 30–80 items; profiling may shift these.
3. **What is current TTID for the TradesDeckScreen on a cold Render dyno boot?** Sentry TTID instrumentation must be added before this can be baselined. Suspected: 3–8 s cold, <1 s warm.
4. **Are Reanimated new-arch feature flags already set?** If not, scroll-with-animation FPS numbers in profiling will be artificially low — flags must be enabled before treating animation perf numbers as representative.
5. **What is the average rendered row height for the ranked player list?** Needed to set `getItemLayout` / `estimatedItemSize` accurately. Needs measurement with a layout inspector or `onLayout` logging.
6. **How large is the FlashList recycle pool on the tiers board?** If chip components hold animation state via shared values, recycling without proper `recyclingKey` resets will cause visual glitches.

---

*Sources consulted:*

- [React Native: Optimizing FlatList configuration](https://reactnative.dev/docs/optimizing-flatlist-configuration)
- [React Native: Performance overview](https://reactnative.dev/docs/performance)
- [React Native: InteractionManager](https://reactnative.dev/docs/interactionmanager)
- [React Native: Hermes](https://reactnative.dev/docs/hermes)
- [React Native: New Architecture landing page](https://reactnative.dev/docs/the-new-architecture/landing-page)
- [React Native DevTools](https://reactnative.dev/docs/react-native-devtools)
- [Shopify FlashList v2 engineering blog](https://shopify.engineering/flashlist-v2)
- [Shopify: Instant Performance Upgrade FlatList → FlashList](https://shopify.engineering/instant-performance-upgrade-flatlist-flashlist)
- [FlashList: Performant components guide (v1)](https://shopify.github.io/flash-list/docs/1.x/fundamentals/performant-components/)
- [Reanimated: Performance guide](https://docs.swmansion.com/react-native-reanimated/docs/guides/performance/)
- [Reanimated 4 blog post](https://blog.swmansion.com/reanimated-4-is-new-but-also-very-familiar-b926dd59aa40)
- [expo-image docs](https://docs.expo.dev/versions/latest/sdk/image/)
- [Zustand: Prevent re-renders with useShallow](https://zustand.docs.pmnd.rs/learn/guides/prevent-rerenders-with-use-shallow)
- [Sentry: React Native performance strategies & tools](https://blog.sentry.io/react-native-performance-strategies-tools/)
- [Sentry: Time to Display instrumentation](https://docs.sentry.io/platforms/react-native/tracing/instrumentation/time-to-display/)
- [React docs: memo](https://react.dev/reference/react/memo)
- [React docs: useMemo](https://react.dev/reference/react/useMemo)
- [Facebook Engineering: Hermes announcement](https://engineering.fb.com/2019/07/12/android/hermes/)
- [Toward Hermes being the Default (RN blog)](https://reactnative.dev/blog/2021/10/26/toward-hermes-being-the-default)
- [Callstack: Code splitting in React Native](https://www.callstack.com/blog/code-splitting-in-react-native-applications)
- [Expo Router v3 changelog: async routes](https://expo.dev/changelog/2024-01-23-router-3)
