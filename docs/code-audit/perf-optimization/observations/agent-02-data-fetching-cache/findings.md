# Agent-02 — Client Data-Fetching & Caching Layer (TanStack Query + Zustand)

## Scope & method

Observation-only audit of the FTF mobile client's data-fetching and caching
layer: the single `QueryClient` config (`mobile/src/state/queryClient.ts`),
every `useQuery` / `useMutation` / `prefetchQuery` / `invalidateQueries`
call across `mobile/src/screens/*` and `mobile/src/components/*`, the
navigation-time prefetch in `mobile/src/navigation/TabNav.tsx`, the root
gating query in `mobile/src/navigation/RootNav.tsx`, the AsyncStorage
hydration sequencing in `mobile/App.tsx`, and the Zustand stores in
`mobile/src/state/*` (`useSession`, `useFeatureFlags`, `useNotifications`,
`useFeedback`, `useTradeQueue`, `usePushPriming`). Focus per the brief is the
**player + trade data caches** (`['trio', …]`, `['rankings', …]`,
`['progress']`, `['tiers-status']`, `['liked-trades', …]`, `['matches','all']`,
`['awaiting-trades']`, `['league-prefs', …]`, trade-generation job state).

Method: static analysis of the full call graph (every `queryKey:` and
`invalidateQueries` occurrence was enumerated with grep and read in context),
cross-referenced against the server-side scoping model in
`mobile/src/api/client.ts` (session token + `X-Scoring-Format` header) and
`mobile/src/api/rankings.ts`. Latency anchors come from timed read-only GETs
against the live Render backend (`https://fantasy-trade-finder.onrender.com`):
warm `/api/feature-flags` measured **0.21–0.54 s** (711 B), `/api/trio` route
**0.23 s** (401 unauth, but exercises routing). The code itself documents the
cold-Render-dyno window as **30–60 s** (`App.tsx:43–46`,
`TradesScreen.tsx:108–109`). No data was mutated; all POST paths were read,
not executed.

Headline structural facts that drive several findings below:
- **No query-cache persistence layer exists.** `package.json` pulls only
  `@tanstack/react-query` and `@react-native-async-storage/async-storage`;
  there is no `@tanstack/query-async-storage-persister` /
  `persistQueryClient` / MMKV, and `grep` for `persistQueryClient` across
  `mobile/src` returns nothing. Every cold launch starts with an empty cache.
- **Server scopes data by session token AND active scoring format**
  (`client.ts:144–146`, `rankings.ts:48–51`), but the player-data query keys
  (`['rankings', position]`, `['progress']`, `['streak']`, `['tiers-status']`)
  encode **neither** league nor format.
- The single `QueryClient` sets `gcTime: 30min`, `staleTime: 30s`,
  `refetchOnWindowFocus: false` globally (`queryClient.ts:17–30`).

---

## OBS-CACHE-01 — No persisted query cache: every cold launch re-fetches all slow player/trade data from scratch

- **Area:** data-fetching / caching
- **Severity:** P1
- **Status:** observed
- **Evidence type:** static-analysis (latency anchored by measured warm GET + in-code cold-dyno window)

### What happens today
The `QueryClient` (`mobile/src/state/queryClient.ts:17–30`) is constructed with
in-memory cache only. There is no `persistQueryClient` /
`PersistQueryClientProvider` wrapper in `App.tsx:96–105`, and no persister
package in `mobile/package.json` (only `@tanstack/react-query` at line 17 and
`@react-native-async-storage/async-storage` at line 12). A `grep` for
`persistQueryClient|createAsyncStoragePersister|createSyncStoragePersister`
across `mobile/src` returns zero hits. The only things hydrated from disk on
boot are the *Zustand* slices (session user/league/leagues in
`useSession.bootstrap` `useSession.ts:96–113`, and the feature-flag map in
`useFeatureFlags.load` `useFeatureFlags.ts:27–37`) — none of the TanStack
query data.

### Why it's slow / costly
The in-memory cache is destroyed when the OS evicts the JS context (app fully
backgrounded for a while, or killed). On the next cold launch, the first visit
to each tab issues a fresh network request with **no cached bytes to paint
first**: Trios (`['trio', position]`, `RankScreen.tsx:75–80`), the ranking
board (`['rankings', …]`, `OverallRanksScreen.tsx:29–33`,
`ManualRanksScreen.tsx:59–63`, `TiersScreen.tsx:102–107`), progress
(`['progress']`, `RootNav.tsx:75–81` — this one is on the **critical auth
path**, blocking the push-priming gate), matches (`['matches','all']`,
`MatchesScreen.tsx:53–58`), liked trades, league summary, etc. `placeholderData:
(prev) => prev` (used widely) only helps *within* a live session — on cold
start `prev` is `undefined`, so every screen blanks to a spinner. The
`gcTime: 30min` tuning (`queryClient.ts:20`) is explicitly there to survive
tab-switches and AppState suspensions, but it cannot survive a JS-context
teardown because the cache lives in memory only.

### Evidence
- `queryClient.ts:17–30` — no `persister`, in-memory `QueryClient`.
- `App.tsx:96–105` — plain `<QueryClientProvider>`, not the persist variant.
- `mobile/package.json:12,17` — no persister dependency.
- Warm per-call latency measured at **0.21–0.54 s** each; a cold launch that
  re-paints Trios + progress + rankings + matches is several serialized/
  parallel round-trips. On a cold Render dyno the first of these eats the
  **30–60 s** wake documented in `App.tsx:43–46` with nothing on screen.
- Zustand already proves the pattern works: `useFeatureFlags.ts:27–47`
  hydrates flags from AsyncStorage *then* revalidates — exactly the
  stale-while-revalidate behavior the query cache lacks.

### Recommendation(s)
- **Option A (preferred):** Add `@tanstack/query-async-storage-persister` +
  `persistQueryClient` (or the `PersistQueryClientProvider`) in `App.tsx`,
  backed by AsyncStorage (already a dependency), with a `maxAge` aligned to
  `gcTime` and a `dehydrateOptions` allowlist so only durable player/trade
  data is persisted (exclude in-flight trade-generation job snapshots and the
  `['trio', …]` deck, which must stay fresh). Gives instant
  stale-while-revalidate paint on cold launch for rankings/progress/matches.
  Client-only; moderate effort because each persisted key needs a
  freshness review.
- **Option B:** Swap the AsyncStorage persister for an MMKV-backed synchronous
  persister (react-native-mmkv). Faster hydrate (synchronous, no bridge
  round-trip) and avoids the async sequencing concern in OBS-CACHE-02, but
  adds a native dependency and an Expo prebuild/config-plugin step — larger
  effort, defer unless AsyncStorage hydrate latency proves material.
- **Option C (narrow):** Persist only the two highest-value, slowest keys
  (`['rankings','all']` and `['progress']`) via manual
  `setQueryData`-on-boot from AsyncStorage, mirroring the flag-hydrate
  pattern. Cheapest, but reinvents a subset of the persister and doesn't
  scale to the other tabs.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 8 | 2 | 80% | 3 | **4.3** |

- **Estimated latency delta:** Cold launch (warm dyno): each first-visited
  tab paints cached content in ~0 ms instead of waiting on a 0.2–0.5 s
  round-trip (−0.2–0.5 s per tab, ×4–5 tabs over the session). Cold launch
  (cold dyno): the 30–60 s wake is removed from the *paint* critical path —
  user sees last-known rankings/progress/matches immediately while the
  refetch happens behind the scenes. No change to first-ever-launch.
- **Confidence note:** 80% — absence of persistence is unambiguous in
  code/deps; the win is well-documented TanStack behavior. Held below 100%
  because the realized delta depends on how recently the user last launched
  (very old caches still show stale data + refetch) and on per-key freshness
  tuning.

### Related components
`mobile/src/state/queryClient.ts`, `mobile/App.tsx`, `mobile/package.json`,
all player/trade `useQuery` call sites; `useFeatureFlags.ts` (reference
pattern). Interacts with OBS-CACHE-02 (hydration sequencing) and OBS-CACHE-04
(format/league key scoping — persisted stale data under-scoped by format would
be *worse*, so 04 should land with or before this).

### Prerequisites / dependencies
Add the persister dependency. Should land alongside OBS-CACHE-04 so persisted
caches aren't served cross-format/cross-league.

### Regression risk
Medium. Persisting under-scoped keys (see OBS-CACHE-04) could show another
league's/format's data on cold launch. Must exclude live job snapshots and the
trio deck from dehydration, and verify `staleTime`/`maxAge` so the refetch
still fires. No ELO-math / tier-color / enum invariants touched (cache
transport only).

---

## OBS-CACHE-02 — Boot fans out 4 async tasks in parallel but query hydration isn't sequenced before first paint

- **Area:** data-fetching / app boot
- **Severity:** P2
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
`App.tsx:47–54` fires `Promise.all([bootstrap(), loadFlags(),
fetchTierConfig(), warmPlayerCache()])` and flips `booted=true` in
`.finally()`. `bootstrap()` (`useSession.ts:96–113`) does four AsyncStorage
reads, and `loadFlags()` (`useFeatureFlags.ts:22–56`) does an AsyncStorage read
*then* a network fetch. The boot gate therefore waits on the **slowest of all
four**, including the network flag fetch and the `warmPlayerCache()` ping,
before `RootNav` renders anything past the splash (`RootNav.tsx:96–102`).

### Why it's slow / costly
Two coupled issues:
1. **The splash is gated on a network call.** `loadFlags()` awaits
   `loadFeatureFlags({ throwOnError: true })` (`useFeatureFlags.ts:44`) before
   resolving. Although it hydrates cached flags from AsyncStorage first
   (lines 27–37), the *promise the boot gate awaits* doesn't resolve until the
   network attempt finishes (or fails). Measured warm flag fetch is
   0.21–0.54 s; on a cold dyno this is the 30–60 s wake — the splash can hang
   far longer than the cheap local hydration would require. (`warmPlayerCache`
   is correctly `.catch()`-isolated at line 51, but `loadFlags` is not
   similarly time-boxed.)
2. **No query prewarm during the splash.** The boot already knows the user is
   returning (session token + league present, `useSession.ts:97–112`), yet
   nothing seeds `['progress']` or `['rankings','all']` during the dead splash
   time. `RootNav`'s `['progress']` query (`RootNav.tsx:75–81`) only starts
   *after* `booted` flips and the tree mounts, adding a serial round-trip
   after the splash instead of overlapping with it.

### Evidence
- `App.tsx:47–54` — `Promise.all(...).finally(() => setBooted(true))`; the
  gate waits on the network `loadFlags`.
- `useFeatureFlags.ts:43–55` — local hydrate (sync-ish) and network fetch are
  in the *same* awaited promise; the local hydrate can't release the gate
  early.
- `RootNav.tsx:75–81` — `['progress']` query is mount-triggered, not
  prewarmed; it's on the auth/push-gate path.
- Measured warm flag GET 0.21–0.54 s; cold-dyno window 30–60 s
  (`App.tsx:43–46`).

### Recommendation(s)
- **Option A (preferred):** Decouple the splash gate from the *network* half
  of `loadFlags`. Release `booted` as soon as the AsyncStorage hydrations
  (session + cached flags) complete; let the flag network fetch and
  `warmPlayerCache` continue in the background (they already tolerate
  failure). Client-only, low risk — turns a network-bound splash into a
  disk-bound one.
- **Option B:** During the splash, `queryClient.prefetchQuery(['progress'])`
  and `prefetchQuery(['rankings','all'])` when a session token + league are
  present, so `RootNav`/Tiers/Overall adopt the in-flight request on mount
  (same adoption trick already used for Trios in `TabNav.tsx:172–176`).
  Overlaps the first data round-trip with splash time. Slightly more code;
  pairs naturally with OBS-CACHE-01's persister.
- **Option C:** Time-box `loadFlags`' network half with a short race
  (e.g. resolve the boot gate after N ms regardless), keeping the cached
  flags. Simplest, but a fixed timeout is a blunt instrument vs. Option A.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 10 | 1 | 50% | 1 | **5.0** |

- **Estimated latency delta:** −0.2–0.5 s to first interactive frame on a
  warm dyno (splash no longer waits on the flag network call); on a cold dyno
  the splash stops blocking on the 30–60 s wake entirely (Option A). Option B
  saves an additional ~0.2–0.5 s on the first `['progress']`/rankings paint by
  overlapping it with splash.
- **Confidence note:** 50% — the sequencing is clear in code, but the
  realized first-paint delta depends on RN/Expo splash teardown timing and
  device disk speed, which aren't measured here. A startup trace would raise
  this.

### Related components
`mobile/App.tsx`, `mobile/src/state/useFeatureFlags.ts`,
`mobile/src/state/useSession.ts`, `mobile/src/navigation/RootNav.tsx`
(`['progress']`), `mobile/src/api/flags.ts`. Synergistic with OBS-CACHE-01
(persisted cache makes the prewarm instant) and OBS-CACHE-05 (prefetch).

### Prerequisites / dependencies
None for Option A. Option B benefits from OBS-CACHE-01 landing first.

### Regression risk
Low–medium. Must ensure flag-gated UI still settles correctly when the gate
releases before the network flags arrive (components already handle
`loaded=false` → cached flags, see `useFeatureFlags.ts:29–37`). Confirm the
push-priming gate (`RootNav.tsx:82–94`) still fires once `['progress']`
resolves whether prewarmed or mount-triggered.

---

## OBS-CACHE-03 — No `focusManager` bridge: returning from background can show stale data and the `refetchOnWindowFocus` intent is dead

- **Area:** data-fetching / cache freshness
- **Severity:** P2
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
The global config sets `refetchOnWindowFocus: false` and `staleTime: 30_000`
(`queryClient.ts:21,24`). React Native has no DOM "window focus," but
TanStack's RN integration maps app foreground → focus when a `focusManager`
is wired; it is **not** wired here (no `focusManager.setEventListener` /
AppState bridge anywhere in `mobile/src`). So returning to the foreground does
**not** revalidate any query except via `refetchOnReconnect` (network change)
or a screen remount. Meanwhile `['trio', position]` overrides with
`staleTime: 0` + `refetchOnMount: 'always'` (`RankScreen.tsx:78–80`), and
`RootNav`'s `['progress']` sets `refetchOnWindowFocus: true` (`RootNav.tsx:80`)
— which is a **no-op** without the `focusManager` bridge.

### Why it's slow / costly
Two opposite failure modes coexist:
1. **Staleness on resume:** A user who backgrounds the app mid-session and
   returns after >30 s sees screens that are `stale` but won't refetch until
   they navigate away and back (remount) or the network blips. The
   `['progress']` author *intended* focus-refetch (`RootNav.tsx:80`) but it
   silently does nothing — the push-unlock gate can lag.
2. **Inconsistent freshness:** because `placeholderData: (prev) => prev` is
   everywhere, a tab revisit shows old data instantly and then *may or may
   not* refetch depending on `staleTime`. The behavior differs across screens
   (15 s, 30 s, 60 s, 5 min), so "is this fresh on resume?" has no single
   answer.

### Evidence
- `queryClient.ts:21,24` — `refetchOnWindowFocus: false`, `staleTime: 30s`.
- No `focusManager`/`onlineManager` AppState bridge anywhere under
  `mobile/src` (grep: no `focusManager` hits).
- `RootNav.tsx:80` — `refetchOnWindowFocus: true` set on `['progress']` but
  unreachable without the bridge → dead config, misleading intent.
- `App.tsx:84–94` already has an AppState `'active'` listener (used only for
  feedback `retrySync`) — the hook point exists but isn't connected to the
  query layer.

### Recommendation(s)
- **Option A (preferred):** Wire TanStack's `focusManager` to RN AppState in
  `App.tsx` (reuse the existing AppState listener at lines 84–94) and
  `onlineManager` to NetInfo. Then `refetchOnWindowFocus` (including the
  already-intended `['progress']` one) works as written, giving consistent
  revalidate-on-resume. Low effort, mostly enabling intent already in code.
- **Option B:** Leave focus off, but make resume-freshness explicit by
  invalidating the small set of resume-sensitive keys (`['progress']`,
  `['matches','all']`, `['liked-trades', …]`) from the existing AppState
  `'active'` handler. More targeted (avoids refetch storms across all tabs)
  but hand-maintained.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 6 | 0.5 | 80% | 0.5 | **6.0** |

- **Estimated latency delta:** No raw-latency change; correctness/freshness
  win. Eliminates the "stale board after returning from background" class and
  makes the `['progress']` push-gate fire on resume as intended. Slight extra
  network on each resume (bounded by `staleTime`).
- **Confidence note:** 80% — the missing `focusManager` bridge is verifiable
  (the `RootNav` `refetchOnWindowFocus:true` is provably dead). Impact kept at
  0.5 because it's smoothness/correctness, not a spinner removal.

### Related components
`mobile/App.tsx` (AppState listener), `mobile/src/state/queryClient.ts`,
`mobile/src/navigation/RootNav.tsx` (`['progress']`), all `placeholderData`
screens. `@react-native-community/netinfo` would be needed for `onlineManager`.

### Prerequisites / dependencies
`onlineManager` half needs NetInfo (check if already transitively present).
`focusManager` half needs nothing new.

### Regression risk
Low–medium. Enabling focus-refetch app-wide could add a refetch burst every
resume; mitigate by keeping per-screen `staleTime` honest. Confirm the trio
deck (`staleTime:0`) doesn't refetch-and-reshuffle mid-swipe on a resume.

---

## OBS-CACHE-04 — Player-data query keys omit league and scoring-format → cache bleed and missed invalidation on switch

- **Area:** data-fetching / query-key design
- **Severity:** P1
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
The backend scopes ranking/trio/tier/progress data by **session token AND the
`X-Scoring-Format` header** (`client.ts:144–146`; header injected via
`formatHeader()` / `setActiveScoringFormat` in `rankings.ts:35–51`). But the
query keys for that data encode neither dimension:
- `['rankings', position]` (`TiersScreen.tsx:103`), `['rankings','all']`
  (`OverallRanksScreen.tsx:30`, `ManualRanksScreen.tsx:60`)
- `['progress']` (`RootNav.tsx:76`, `RankScreen.tsx:83`)
- `['streak']` (`RankScreen.tsx:90`), `['tiers-status']` (`TiersScreen.tsx:110`)
- `['trio', position]` (`RankScreen.tsx:76`, `TabNav.tsx:173`)

`useSession.switchLeague` (`useSession.ts:182–184`) invalidates only
`['portfolio']`, `['matches','all']`, `['awaiting-trades']` on a league swap —
it does **not** invalidate `['rankings', …]`, `['progress']`, `['streak']`, or
`['tiers-status']`. And nothing invalidates anything on a **scoring-format**
change (`grep` for format-triggered invalidation returns nothing;
`setActiveScoringFormat` `rankings.ts:35` has no cache hook).

### Why it's slow / costly
Two cache-correctness anti-patterns:
1. **League-switch staleness:** rankings/progress/tiers are league-relative on
   the backend. After `switchLeague`, these stably-keyed caches keep the
   **old league's data** until their `staleTime` elapses (30 s rankings, 15 s
   progress, 60 s tiers-status) and a remount/refetch happens. The author
   *recognized* this for the three keys they did invalidate
   (`useSession.ts:178–184` comment), but the rankings/progress/tiers family
   was missed.
2. **Format-switch bleed (latent):** `setActiveScoringFormat` is defined for
   web parity but not yet wired to a UI control in this scope. If/when it is,
   flipping format changes the `X-Scoring-Format` header but reuses the same
   `['rankings', position]` key — serving 1QB-PPR data under an SF-TEP view
   until staleTime expires. A wrong-data bug, not just a latency one.

This *interacts dangerously with OBS-CACHE-01*: persisting under-scoped keys
would carry the bleed across launches.

### Evidence
- `client.ts:144–146` + `rankings.ts:48–51` — data is token+format scoped
  server-side.
- Query keys listed above — no league, no format component.
- `useSession.ts:182–184` — league-switch invalidation omits the rankings/
  progress/streak/tiers family.
- No format-triggered invalidation anywhere (grep result empty);
  `setActiveScoringFormat` has no UI caller in this scope today.

### Recommendation(s)
- **Option A (preferred):** Add `format` (and, for league-relative data,
  `leagueId`) to the query keys of the player-data family —
  `['rankings', format, position]`, `['progress', leagueId, format]`, etc. —
  so a format/league change *automatically* switches cache slots (no manual
  invalidation, no bleed, instant when revisiting a prior format/league). The
  idiomatic TanStack fix. Effort is in touching ~6 call sites + their
  invalidation partial-keys consistently.
- **Option B (cheaper, less safe):** Keep flat keys but extend `switchLeague`
  (`useSession.ts:182–184`) to also invalidate `['rankings']`, `['progress']`,
  `['streak']`, `['tiers-status']`, and add a format-change invalidation hook
  in `setActiveScoringFormat`. Smaller diff, but forces a full refetch on
  every switch (loses the "instant when revisiting" benefit) and remains
  error-prone (every new call site must remember to invalidate).

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 4 | 1 | 80% | 2 | **1.6** |

- **Estimated latency delta:** League switch: Option A makes revisiting a
  previously-loaded league's board/progress instant (cache hit, −0.2–0.5 s
  per affected query) instead of a stale-then-refetch; Option B forces the
  refetch (+round-trip) but fixes correctness. Format switch: removes a
  wrong-data window (correctness, not latency). Reach 4 because league switch
  is occasional and format-switch UI isn't wired yet.
- **Confidence note:** 80% — server scoping and key shapes are both verifiable
  in code. The format half is latent (no UI caller today), so its *current*
  user impact is lower, reflected in Reach.

### Related components
`mobile/src/state/useSession.ts` (`switchLeague`), `RankScreen.tsx`,
`TiersScreen.tsx`, `OverallRanksScreen.tsx`, `ManualRanksScreen.tsx`,
`RootNav.tsx`, `TabNav.tsx`, `mobile/src/api/rankings.ts`
(`setActiveScoringFormat`, `formatHeader`). **Hard dependency for
OBS-CACHE-01** (don't persist under-scoped keys).

### Prerequisites / dependencies
Should land before or with OBS-CACHE-01.

### Regression risk
Medium. Changing query keys changes every matching `invalidateQueries` partial
key — the broad `invalidateQueries({ queryKey: ['rankings'] })` calls
(`RankScreen.tsx:145`, `TiersScreen.tsx:145,173`, `ManualRanksScreen.tsx:105`)
still match a `['rankings', format, position]` prefix, so they keep working,
but verify screen-by-screen. No ELO-math/tier-color/enum invariant changes —
only cache identity.

---

## OBS-CACHE-05 — Prefetch warms only the Trios deck; Trades/Tiers/Overall/Matches navigate cold

- **Area:** data-fetching / prefetch
- **Severity:** P2
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
The only navigation-time prefetch in the app is for Trios: `RankMenu.go()`
prefetches `['trio','QB']` during the action-sheet close animation
(`TabNav.tsx:169–177`), so `RankScreen`'s `useQuery(['trio','QB'])` adopts the
in-flight request. No equivalent warm-up exists for any other destination:
- Tapping the **Tiers** row navigates and only *then* fires
  `['rankings', position]` + `['tiers-status']` (`TiersScreen.tsx:102–114`).
- **Overall/Manual Ranks** fire `['rankings','all']` on mount
  (`OverallRanksScreen.tsx:29`, `ManualRanksScreen.tsx:59`).
- The **Trades** tab and **Matches** tab have no prefetch; `['matches','all']`
  (`MatchesScreen.tsx:53`) and `['liked-trades', leagueId]`
  (`TradesScreen.tsx:341`) start cold on tab focus.

The `RankMenu` action sheet (`TabNav.tsx:188–194`) lists Tiers / ManualRanks /
OverallRanks / Trends as siblings to Trios — the exact same ~250–400 ms
animation window the author already exploits for Trios is left unused for the
other four destinations.

### Why it's slow / costly
The user has already expressed navigation intent (tapped the row / opened the
sheet); the transition animation is dead time that could overlap the data
round-trip. Because the destination screens only have `placeholderData:
(prev) => prev`, the **first** visit in a session (no `prev`) shows a spinner
for a full round-trip (measured 0.2–0.5 s warm; the 30–60 s cold-dyno wake
when the dyno is asleep). Prefetching on the row-press, as already done for
Trios, would hide most of that behind the transition.

### Evidence
- `TabNav.tsx:169–177` — Trios-only `prefetchQuery`; comment at 162–168
  explicitly notes "Only fires for the Trios destination."
- `TiersScreen.tsx:102–114`, `OverallRanksScreen.tsx:29`,
  `ManualRanksScreen.tsx:59`, `MatchesScreen.tsx:53`,
  `TradesScreen.tsx:341` — all mount-triggered, no prefetch.
- Warm round-trip 0.2–0.5 s measured; cold-dyno 30–60 s (`App.tsx:43–46`).

### Recommendation(s)
- **Option A (preferred):** Extend the existing `RankMenu.go()` prefetch
  (`TabNav.tsx:169–177`) to warm the destination's key per route: Tiers →
  `['rankings','QB']` + `['tiers-status']`; OverallRanks/ManualRanks →
  `['rankings','all']`. Reuses the proven adoption pattern; tiny, localized.
  Trends has its own shapes — include if cheap.
- **Option B:** Add a tab-`listeners` `tabPress` prefetch for the **Trades**
  and **Matches** tabs in `TabNav.tsx` (warm `['matches','all']` /
  `['liked-trades', leagueId]`) so the two most-used post-unlock tabs warm on
  tap. Slightly more surface than A but covers the highest-traffic flows.
- **Option C:** Pair with OBS-CACHE-01's persister so warm-from-disk replaces
  most prefetch needs on cold launch (prefetch then only matters for the
  *first* in-session visit). Complementary, not exclusive.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 8 | 1 | 80% | 1 | **6.4** |

- **Estimated latency delta:** −0.2–0.5 s perceived load on the first
  in-session visit to Tiers / Overall / Manual / Matches / Trades (warm dyno),
  by overlapping the round-trip with the ~250–400 ms transition; larger
  perceived win on a cold dyno where the round-trip is much longer.
- **Confidence note:** 80% — the pattern is already proven for Trios in this
  exact file; extending it is low-risk and the round-trip cost is measured.
  Below 100% only because the transition window must be ≥ the round-trip to
  fully hide it (true warm, not always true cold).

### Related components
`mobile/src/navigation/TabNav.tsx` (`RankMenu.go`, tab listeners),
`TiersScreen.tsx`, `OverallRanksScreen.tsx`, `ManualRanksScreen.tsx`,
`MatchesScreen.tsx`, `TradesScreen.tsx`, `mobile/src/api/rankings.ts`,
`mobile/src/api/trades.ts`.

### Prerequisites / dependencies
None. Composes with OBS-CACHE-01 and OBS-CACHE-04 (prefetch the correctly
scoped key).

### Regression risk
Low. Prefetch is fire-and-forget (errors surface on the real `useQuery`). Must
prefetch the **same** key shape the destination uses (watch OBS-CACHE-04's
key changes) or the warm-up misses.

---

## OBS-CACHE-06 — Over-broad `['rankings']` invalidation triggers refetches across multiple screens per ranking/tier mutation

- **Area:** data-fetching / invalidation
- **Severity:** P3
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
Several mutations invalidate the entire `['rankings']` family on success:
- `RankScreen` trio submit → `invalidateQueries(['rankings'])`
  (`RankScreen.tsx:145`)
- `TiersScreen` save → `['rankings']` (`TiersScreen.tsx:145`); copy →
  `['rankings']` (`TiersScreen.tsx:173`)
- `ManualRanksScreen` reorder → `['rankings']` (`ManualRanksScreen.tsx:105`)

A partial key `['rankings']` matches **every** sub-key: `['rankings','all']`
(Overall + Manual), `['rankings','QB'|'RB'|'WR'|'TE']` (Tiers per-position).
So a single trio submit marks all of them stale; any of those screens that are
mounted (or become active) refetch a full board.

### Why it's slow / costly
On the active screen the refetch is intended (the board did change). But the
blast radius is wider than necessary: every trio submit (`RankScreen.tsx:145`)
invalidates the whole family on a **high-frequency** action — the comment at
lines 140–144 correctly flags that downstream screens read `['rankings', …]`,
but a position-scoped invalidation (`['rankings', position]` +
`['rankings','all']`) would suffice; invalidating *other* positions' Tiers
caches is wasted work, forcing a redundant full-board refetch on the next
visit even where `gcTime` would have served warm. The accompanying
`['progress']` and `['tiers-status']` invalidations are correctly scoped; only
the `['rankings']` breadth is loose.

### Evidence
- `RankScreen.tsx:145`, `TiersScreen.tsx:145,173`, `ManualRanksScreen.tsx:105`
  — bare `['rankings']` partial-key invalidations.
- Key shapes proving the breadth: `['rankings','all']`
  (`OverallRanksScreen.tsx:30`, `ManualRanksScreen.tsx:60`),
  `['rankings', position]` (`TiersScreen.tsx:103`).
- Trio submit is the app's highest-frequency mutation
  (`RankScreen.tsx:96–160`).

### Recommendation(s)
- **Option A (preferred):** Scope the trio-submit invalidation to the touched
  data: `['rankings', position]` (the submitted position) + `['rankings',
  'all']` (the flat board), instead of the whole `['rankings']` family. Leaves
  the other three positions' Tiers caches warm. Tiny, localized.
- **Option B:** Leave breadth as-is and rely on `gcTime`/`staleTime` to absorb
  it (status quo). Zero effort; accepts the redundant next-visit refetches.
  Acceptable given low absolute cost — this is a polish item.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 6 | 0.25 | 80% | 0.5 | **3.0** |

- **Estimated latency delta:** No first-paint change. Saves a redundant
  full-board refetch (~0.2–0.5 s warm) on the *next* visit to Overall/Manual/
  other-position Tiers after a trio submit, where `gcTime` would otherwise
  have served warm. Mostly background/battery + backend-load savings on a
  high-frequency action.
- **Confidence note:** 80% — the partial-key match semantics are
  deterministic. Impact is minimal (0.25) because mounted-screen refetches are
  legitimate and unmounted ones are cheap; efficiency polish, not a
  user-visible stall.

### Related components
`RankScreen.tsx`, `TiersScreen.tsx`, `ManualRanksScreen.tsx`,
`OverallRanksScreen.tsx`. Watch interaction with OBS-CACHE-04 key changes
(invalidation prefixes must still match).

### Prerequisites / dependencies
None. If OBS-CACHE-04 lands, re-verify the prefix still matches the new
`['rankings', format, position]` shape.

### Regression risk
Low. The risk is *under*-invalidating (a screen showing stale ELOs). Test:
submit a trio, then open Overall Ranks and Tiers for the submitted position and
confirm both reflect the new ELO; confirm other-position Tiers are
intentionally left warm. ELO values are server-authoritative — no math
invariant touched.

---

## Top 3 by RICE-P

| Rank | OBS | Title | RICE-P | Severity |
|-----:|-----|-------|-------:|----------|
| 1 | OBS-CACHE-05 | Prefetch only warms Trios; Trades/Tiers/Overall/Matches navigate cold | **6.4** | P2 |
| 2 | OBS-CACHE-03 | No `focusManager` bridge → stale-on-resume + dead `refetchOnWindowFocus` intent | **6.0** | P2 |
| 3 | OBS-CACHE-02 | Splash gate waits on the flag network call; no query prewarm during splash | **5.0** | P2 |

> Note on prioritization: **OBS-CACHE-01** (no persisted cache, score 4.3,
> **P1**) and **OBS-CACHE-04** (key under-scoping, score 1.6, **P1**) carry
> higher *severity* than the top-3 RICE-P items — they're larger-effort
> structural fixes whose scores are dampened by Effort, not by impact. They
> should be sequenced together (persist + correct-scoping) as the strategic
> work, with the top-3 quick wins shipped first.

## CROSS-REF

- **Backend / cold-start (out of lane):** Several findings are dominated by
  the documented 30–60 s Render free-tier cold-dyno wake (`App.tsx:43–46`,
  `TradesScreen.tsx:108–109`). The client-side caching/prefetch fixes only
  *hide* this; eliminating the cold start (paid dyno / keep-warm cadence) is a
  backend/infra item that would raise the realized impact of
  OBS-CACHE-01/02/05.
- **Network (out of lane):** the 1500 ms fixed trade-status poll
  (`TradesScreen.tsx:233–261`) is a network/data-fetching cadence concern
  (matches the template's worked example OBS-NET-07) — flagging for the
  network audit rather than duplicating here.
