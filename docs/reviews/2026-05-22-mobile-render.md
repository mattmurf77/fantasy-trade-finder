# Mobile first-render perf review — 2026-05-22

Scope: cold-start render of every authed tab, with the Trios screen as the
user's primary pain point. Builds on `docs/feedback/perf-audit-2026-05-21.md`
(warm endpoint + progressive paint on LeagueScreen/MatchesScreen — already
shipped). Read-only audit; no code changed.

Real-world latencies measured against the prod Render free-tier dyno
while warm:

| Endpoint | Warm latency |
|---|---|
| `GET /api/sleeper/players/warm` | ~0.93 s |
| `GET /api/tier-config` | ~0.20 s |
| `GET /api/feature-flags` | ~0.34 s |
| `GET /api/trio?position=QB` (401, no session) | ~0.30–0.50 s |
| `GET /api/rankings/progress` (401) | ~0.17 s |
| `GET /api/me/streak` (401) | ~0.20 s |

Authenticated `/api/trio` is meaningfully heavier server-side (skip lookup
+ QC/community signal hooks + tier-info bundling, see
`backend/server.py:1271-1400`) — anecdotally 0.4–1.5 s warm. On a cold dyno
add 30–60 s.

---

## Trios cold-start trace (user's primary complaint)

Cold start scenario: user opens the app, splash shows, lands on Main tabs
(Trades is the active tab by default since LeagueScreen isn't the first
tab in `TabNav.tsx:108-138` — actually the first registered tab is `Rank`
but it's tap-intercepted; the user lands on whichever tab the tab-nav
picks, which in v7 is the first non-`tabBarButton: null` screen → still
Rank, but the listener at `TabNav.tsx:117-121` calls
`e.preventDefault()` so the RankStack never actually mounts on initial
focus). User then taps the Rank tab to open the action sheet, picks
Trios, and waits.

**Step-by-step latency budget (warm dyno; cold dyno adds 30–60 s in one
of the first network steps):**

| # | Step | File:line | Cost |
|---|---|---|---|
| 1 | User taps Rank tab → `tabPress` preventDefault, opens `RankMenu` Modal | `TabNav.tsx:113-122,140-144` | ~0 ms (Modal slide animation ~250 ms) |
| 2 | User taps "Trios" row → `setRankMenuOpen(false)` + `navContext.dispatch(navigate('Rank', { screen: 'Trios' }))` | `TabNav.tsx:159-167` | ~0 ms JS; Modal-close + tab-transition animation ~250 ms; then RankStack mounts for the first time |
| 3 | RankStack mounts → `RankScreen` function body runs. Synchronous work: three `useState`, `useEffect` for AsyncStorage read of `ftf.trios.speedMode`, three `useQuery` registrations, callback memos | `RankScreen.tsx:45-92` | <5 ms JS; **shell does NOT paint here — the body's "Cards" branch at line 368 short-circuits to `<ActivityIndicator>` because `trioQuery.isLoading || !trio`** |
| 4 | First render commits → spinner visible. The position switcher / progress bar / I-AM-SPEED tile / Skip button DO paint immediately (they depend on local state, not `trio`). But the section that matters (the three cards) is a spinner. | `RankScreen.tsx:368-371` | ~16–32 ms (one or two frames) |
| 5 | Three parallel `useQuery` fires:<br/>• `['trio', position]` → `GET /api/trio?position=QB` with `staleTime: 0, refetchOnMount: 'always'`<br/>• `['progress']` → `GET /api/rankings/progress` (`staleTime: 15s` — likely cached if RootNav's progressQuery already ran) <br/>• `['streak']` → `GET /api/me/streak` (`staleTime: 60s`) | `RankScreen.tsx:75-92` | All three sent concurrently. **Latency dominated by the slowest, which is always `/api/trio`** |
| 6 | `/api/trio` response arrives (warm: 0.4–1.5 s; cold: +30–60 s) | server `backend/server.py:1271-1400` | This is the entire perceived wait |
| 7 | `trioQuery.data` flips → second render. `SwipePlayerCard` x3 mount inside `<View style={styles.cards}>`. Each one constructs a Reanimated Pan gesture + animated style — non-trivial but <5 ms total. | `RankScreen.tsx:384-402, 509-581` | ~10–20 ms |
| 8 | First *interactive* trio paints. | | |

**Total cold-start wall time, warm dyno:** ~600–1800 ms from tab tap
to interactive (dominated by step 6: `/api/trio`).
**Total cold-start wall time, cold dyno:** 30–60 s, all in step 6.

### Why this feels slow even when it's not catastrophic

1. **The spinner is unconditional.** Step 4 paints a centered
   `ActivityIndicator` (`RankScreen.tsx:369`) with no skeleton, no
   shadow card, no "What's coming next" copy. Even when `/api/trio`
   resolves in 700 ms, the user sees ~700 ms of nothing-card. Compare
   to MatchesScreen's three skeleton tiles (`MatchesScreen.tsx:253-264`)
   which give the user a "page shape" — Trios doesn't have this.

2. **`staleTime: 0, refetchOnMount: 'always'`** on the trio query
   (`RankScreen.tsx:78-79`) is intentional (a trio should never be
   reused once shown) but it means **a tab switch away and back
   triggers a fresh `/api/trio` round-trip every time** — no cached
   trio is ever surfaced for the "instant first paint" moment.

3. **No prefetch.** `RankMenu`'s "Trios" row knows the user is about
   to open the Trios screen 250 ms before RankScreen mounts (the Modal
   close animation duration). Nothing fires `queryClient.prefetchQuery
   (['trio', 'QB'], …)` during that animation. Result: the network
   round-trip starts ~250–400 ms *after* the user taps, instead of
   *during* the menu→screen transition.

4. **No "user has at least seen a player card before" optimism.**
   On every cold start of the screen, we paint the spinner. If the
   user already ranked a trio yesterday, we could persist the last
   trio's player-shape into AsyncStorage and render a ghosted version
   (or even just three skeleton cards with the right dimensions) as
   instant feedback. We do neither.

**Single biggest win for the user:** add a trio skeleton + prefetch on
RankMenu tap. That collapses the perceived wait from "wait for network"
to "wait for animation" on the warm path, and on the cold path at least
gives the user something to look at while the dyno wakes.

---

## Top 5 findings (ROI ordered)

### #M1 — Trios shows a bare `<ActivityIndicator>` instead of a skeleton
- **Symptom:** Tap Rank → Trios. Position switcher and progress bar
  paint; then a centered spinner replaces the card area for the entire
  `/api/trio` round-trip (0.5–1.5 s warm, 30–60 s cold). No page shape,
  no "loading next trio" copy.
- **Root cause:** `mobile/src/screens/RankScreen.tsx:368-371` — the
  cards branch short-circuits to `<View style={styles.centered}>
  <ActivityIndicator /></View>` when `trioQuery.isLoading || !trio`.
- **Proposed fix:** Render three skeleton `PlayerCard`-shaped
  placeholders (same outer height/radius/padding as
  `PlayerCard`) — exactly mirroring the pattern already shipped in
  `MatchesScreen.tsx:253-264`. Static fills, no shimmer needed. Also
  swap the spinner-only branch for a `"Pulling your next trio…"` line
  on cold-dyno waits (~4 s timeout pattern from
  `TradesScreen.tsx:109-116`).
- **Effort:** small (one screen, no new components if MatchesScreen's
  pattern is reused). **Impact:** large — directly addresses the
  user's complaint. **Risk:** very low (purely additive UI).

### #M2 — No prefetch on RankMenu → Trios; the network round-trip waits for screen mount
- **Symptom:** The 250–400 ms `RankMenu` Modal-close animation is
  wasted dead time. `/api/trio` only fires after `RankScreen` mounts
  and its first `useQuery` registers, ~one frame after the modal
  finishes.
- **Root cause:** `mobile/src/navigation/TabNav.tsx:159-167` —
  `go('Trios')` only dispatches navigation; nothing warms the query
  cache. `RankScreen.tsx:75-80` then registers `useQuery(['trio', 'QB'])`
  with `refetchOnMount: 'always'` and that's when fetch actually starts.
- **Proposed fix:** In `RankMenu.go`, when `screen === 'Trios'`, call
  `queryClient.prefetchQuery({ queryKey: ['trio', 'QB'], queryFn: ()
  => getNextTrio('QB'), staleTime: 0 })` *before* `navContext.dispatch`.
  React Query will dedup so the screen's `useQuery` adopts the
  in-flight request. The user effectively gets a free 250–400 ms head
  start. Same trick is worth applying to Tiers (`['rankings', 'QB']`)
  and Trades (`['league-prefs', leagueId]`) for parity.
- **Effort:** small. **Impact:** medium-large — closes the entire
  Modal-close animation window. **Risk:** very low.

### #M3 — `useTradeQueue.hydrate` on TradesScreen blocks the queue UI's first paint and re-fires on every userId change
- **Symptom:** Open Trades for the first time after a fresh boot.
  The queue footer (which gates on `queuedTrades.length > 0`) flashes
  empty for a render or two while the AsyncStorage read finishes,
  even though there are queued trades on disk. Subtle but real on
  slow devices.
- **Root cause:** `mobile/src/screens/TradesScreen.tsx:135-138` —
  `useEffect(() => { if (!queueEnabled) return; void hydrateQueue();
  }, [userId, queueEnabled, hydrateQueue])`. The dep array includes
  `userId` (correct for sign-out/sign-in) but also `hydrateQueue` (a
  zustand selector returning a function reference — stable per store,
  so this is fine) and triggers AFTER first paint. Hydration of the
  store could be moved to `App.tsx`'s boot `Promise.all` so the
  queue is warm by the time TradesScreen ever renders.
- **Proposed fix:** Move `useTradeQueue.getState().hydrate()` into
  the `App.tsx:63-68` `Promise.all` (with userId guard handled inside
  the store). Remove the screen-local `useEffect`. Saves one
  AsyncStorage round-trip on the first Trades tab visit per session.
- **Effort:** small. **Impact:** small-medium (only matters on
  cold-start of Trades, but matters every cold start). **Risk:** low
  (store hydration is idempotent per its `hydrated` flag).

### #M4 — `RankScreen` AsyncStorage read for `speedMode` runs *every* mount and is uncached
- **Symptom:** Every time the user enters Trios, the speed-mode tile
  briefly renders in the OFF state before flipping to ON (if ON was
  persisted). One-frame flicker on hot devices, multi-frame on
  cold-start.
- **Root cause:** `mobile/src/screens/RankScreen.tsx:57-61` — the
  `useEffect` reads `AsyncStorage.getItem(SPEED_MODE_KEY)` on every
  mount with no module-level cache. The same was noted in the prior
  audit (`docs/feedback/perf-audit-2026-05-21.md:39`) but is also
  the canonical example for a broader pattern: AsyncStorage reads
  inside screen `useEffect`s should be hoisted into a module-level
  warm cache (the way `mobile/src/api/rankings.ts:18-19,21-33`
  already does for `_activeFormatCache`).
- **Proposed fix:** Module-level `let _speedModeCache: boolean | null
  = null;` Initialize lazily inside the effect, write through on
  toggle. Or simpler: persist via a tiny zustand slice and hydrate
  in App.tsx boot.
- **Effort:** trivial. **Impact:** small. **Risk:** none.

### #M5 — TanStack `gcTime` defaults to 5 minutes; tab-switch round trips re-fetch unnecessarily
- **Symptom:** User opens Trios, swipes a few trios, switches to
  Trades, makes a trade, comes back to Trios 6 minutes later — the
  Trios screen's React Query cache for `['progress']` and `['streak']`
  has been garbage-collected, so it refetches both even though
  `staleTime` is 15 s / 60 s. The cache-hit path that would have
  delivered instant zero-flash progress chips is gone.
- **Root cause:** `mobile/App.tsx:25-37` — `QueryClient` is
  constructed with `defaultOptions.queries.{staleTime: 30_000, retry:
  1, refetchOnReconnect: true, refetchOnWindowFocus: false}` but no
  `gcTime`. TanStack v5 default `gcTime` is 5 min. Mobile sessions
  involve tab switches and AppState suspensions where 5 min lapses
  routinely. Prior audit flagged this
  (`docs/feedback/perf-audit-2026-05-21.md:40`) — still unset.
- **Proposed fix:** Add `gcTime: 30 * 60_000` (or 60 min) to the
  default options. Combined with `placeholderData: (prev) => prev`
  on screen-level queries (already done on League/Matches/Trades
  prefs etc.), this gives "instant content, refetch silently in
  background" behavior across tab switches.
- **Effort:** one line. **Impact:** medium (compounding — every
  query in the app benefits). **Risk:** very low (RAM bump is
  negligible vs. perf gain).

---

## Per-screen first-paint audit

| Screen | Shell paints first? | Skeleton? | Issues |
|---|---|---|---|
| **Trios** (`RankScreen.tsx`) | Partial — position switcher + progress + speed tile + Skip paint; **card area is bare spinner** | No | #M1, #M2, #M4. The page shape collapses around the spinner because nothing reserves the card-stack height. |
| **Trades** (`TradesScreen.tsx`) | Yes — league pill, outlook card, fairness toggle, Find-a-Trade button all paint immediately from local state / cached `league-prefs` | The deck has a friendly empty-state copy (`emptyCard` at 624-631) for pre-tap. Post-tap, while job is running, there's `ActivityIndicator + "Looking for trades…" + body copy` at 603-615 — counts as a skeleton, good. | The `switching` overlay at 411-420 fully blocks the page during league swaps; could downgrade to "controls disabled" + inline spinner. Polling at 1.5 s with no backoff (prior audit). |
| **Tiers** (`TiersScreen.tsx`) | Yes — title, multi-select toggle, position switcher, copy-from-format button, hint line all paint immediately | No — `rankingsQuery.isLoading` short-circuits the body to a centered `<ActivityIndicator />` at lines 684-687. | Same anti-pattern as Trios. Tier bins should paint empty with their labels so the user sees "Elite / Starter / Solid / Depth / Bench" before chips populate. `staleTime: 30_000` on `['rankings', position]` (line 105) is short; consider 60 s and `placeholderData: (prev) => prev`. |
| **League** (`LeagueScreen.tsx`) | Yes — hero card paints `league?.league_name` from session, then sections paint with `'—'` placeholders | Partial — uses `'—'` text placeholders inside stat cards. Better than a single spinner. | Shipped per prior audit. Still missing `placeholderData` on one query? — confirmed all six queries DO use `placeholderData: (prev) => prev` (lines 49, 57, 68, 81, 89, 97). Clean. |
| **Matches** (`MatchesScreen.tsx`) | Yes — header, segment, chip row, then 3 skeleton match cards | Yes — three skeleton cards at 253-264 | Shipped per prior audit. Could be reused on Trios/Tiers verbatim. |

---

## TanStack Query config issues

Catalogue of `useQuery` calls and the option they're missing (file:line).
"OK" = best-practice options present.

| Query | File:line | `staleTime` | `placeholderData` | `gcTime` | `enabled` gate | Notes |
|---|---|---|---|---|---|---|
| `['trio', position]` | `RankScreen.tsx:75-80` | `0` (intentional) | — | default 5m | — | Intentional 0 stale; consider keeping a tombstone shape (last player IDs) for skeleton rendering. |
| `['progress']` | `RankScreen.tsx:82-86` | 15 s | — | default | — | Add `placeholderData: (prev) => prev` so progress bar doesn't blank during refetch. |
| `['streak']` | `RankScreen.tsx:88-92` | 60 s | — | default | — | Same — add `placeholderData`. |
| `['progress']` | `RootNav.tsx:75-81` | 15 s | — | default | `enabled: !!user && hasToken && !everUnlockedRef.current` (good) | Two queries on `['progress']` (here and RankScreen) — TanStack dedups, harmless but worth noting. |
| `['new-partners', leagueId, userId]` | `TradesScreen.tsx:86-91` | 60 s | — | default | `!!leagueId && !!userId && flag` (good) | Missing `placeholderData`. |
| `['league-prefs', leagueId]` | `TradesScreen.tsx:176-181` | 5 min | — | default | `!!leagueId` (good) | Missing `placeholderData`. The `useEffect` at 183-187 fires `setOutlookOpen(true)` based on `prefsQuery.data` — auto-opens the outlook sheet on first land, which is a UX delay on cold start (Outlook query returns "no outlook set" → sheet pops up over the deck). Consider gating on `prefsQuery.isSuccess` to avoid a flash-of-no-outlook → modal pop. |
| `['liked-trades', leagueId]` | `TradesScreen.tsx:303-308` | 30 s | — | default | `!!leagueId` | Missing `placeholderData`. |
| `['rookies']` | `RookieDraftBoardSheet.tsx:35-40` | 5 min | — | default | `enabled: visible` (good — lazy) | OK. |
| `['rankings', position]` | `TiersScreen.tsx:102-106` | 30 s | — | default | — | Missing `placeholderData`. Consider 60 s stale. |
| `['tiers-status']` | `TiersScreen.tsx:108-112` | 60 s | — | default | — | Missing `placeholderData`. |
| `['league-summary', …]` | `LeagueScreen.tsx:44-50` | 60 s | OK | default | OK | OK. |
| `['league-coverage', …]` | `LeagueScreen.tsx:52-58` | 60 s | OK | default | OK | OK. |
| `['league-members', …]` | `LeagueScreen.tsx:63-69` | 60 s | OK | default | OK | OK. |
| `['league-activity', …]` | `LeagueScreen.tsx:76-82` | 60 s | OK | default | OK + flag | OK. |
| `['league-contrarian', …]` | `LeagueScreen.tsx:84-90` | 5 min | OK | default | OK | OK. |
| `['league-member-unlocks', …]` | `LeagueScreen.tsx:92-98` | 60 s | OK | default | OK + flag | OK. |
| `['matches', 'all']` | `MatchesScreen.tsx:53-58` | 15 s | OK | default | — | OK. Optimistic-update path verified clean (lines 73-95). |
| `['awaiting-trades']` | `MatchesScreen.tsx:63-68` | 15 s | — | default | `segment === 'awaiting'` (good — lazy) | Missing `placeholderData` — toggle back from Mutual blanks for a frame. |

**Pattern summary:** League and Matches have been "fixed" (prior audit
work landed). Trios, Tiers, and Trades still missing `placeholderData`
across the board, which is the cheapest cross-screen win after the
global `gcTime` bump in #M5.

---

## Lower-priority findings

- **#L1** `RankScreen.tsx:248-267` — streak chip's `streakQuery.data?.current
  > 0` check renders nothing for streakless users but the layout
  reserves no fixed height; once the streak query resolves and the
  chip pops in, every section below shifts down by ~36 px. Reserve a
  fixed-height container or render a placeholder pill.

- **#L2** `RankScreen.tsx:130-131` — `skipTrio` calls
  `queryClient.invalidateQueries({ queryKey: ['trio', position] })`.
  Because the trio query has `staleTime: 0, refetchOnMount: 'always'`,
  this is correct, but the `setSelectionOrder([])` happens BEFORE the
  invalidate so the cards rerender empty for ~one frame before the
  spinner takes over. Swap the order or wrap both in a single
  `unstable_batchedUpdates` call to avoid the double-render.

- **#L3** `TradesScreen.tsx:147-160` — `useEffect` reads
  `AsyncStorage.getItem(FAIRNESS_PREF_KEY)` on mount, identical
  AsyncStorage-on-mount anti-pattern as #M4. Move to a module-level
  cache or zustand slice.

- **#L4** `TradesScreen.tsx:183-187` — auto-opening the OutlookSheet on
  `prefsQuery.data && !prefsQuery.data.team_outlook` fires on every
  render where the data resolves negative. If the user dismisses the
  sheet, the data stays `team_outlook: null` and the next refetch
  triggers a re-pop. Track a `outlookPrompted` ref or gate on
  `prefsQuery.isLoading === false && prefsQuery.isPlaceholderData ===
  false` once.

- **#L5** `TiersScreen.tsx:193-215` — re-auto-bucket effect runs
  whenever `rankingsQuery.data` or `tiersStatusQuery.data?.scoring_format`
  changes. With `staleTime: 30_000` and TanStack's background
  refetch, this means every 30 s of tab focus the buckets are
  rebuilt from scratch, blowing away any in-progress user drag state.
  In practice this is masked by the focus-lifecycle but worth adding
  a "skip if user has actively dragged since last bucket" guard.

- **#L6** `MatchesScreen.tsx:148-165` — `filterChips` `useMemo`
  recomputes on every `allMatches`/`allAwaiting` reference change,
  even when contents are equal (TanStack returns fresh array
  references on refetch). Cheap, but the prior comment about polling
  at TradesScreen.tsx:280 ("don't depend on the array reference")
  applies here too if this list ever gets long.

- **#L7** `App.tsx:25-37` — `QueryClient.defaults.queries.staleTime`
  is 30 s; many screen queries override to 15 s or 60 s. Worth
  re-considering whether 30 s is the right global floor (it forces
  every screen's "default" query to refetch within half a minute of
  any interaction).

- **#L8** `RankScreen.tsx:288` — `<Text style={styles.modeHint}>Trios
  · tap 🏈 Rank below for more modes ›</Text>` — emoji in JS text
  string. Hermes handles it fine but adds non-trivial first-render
  shape measurement. Negligible but mentioned for completeness.

- **#L9** `App.tsx:81-94` — deep-link listener registers `Linking
  .addEventListener` inside a `useEffect` with `[]` deps. Fine, but
  `Linking.getInitialURL()` resolves asynchronously and has no
  cancellation on the await — if the user signs out before it
  resolves, `handleDeepLink` still runs. Probably benign; flag for
  the silent-bugs reviewer.

---

## What I checked and found clean

- **App.tsx boot flow** (`App.tsx:44-71`) — `Promise.all` parallelizes
  `bootstrap`, `loadFlags`, `fetchTierConfig`, `warmPlayerCache`. No
  hidden serialization, no synchronous work blocking splash dismissal.
- **`useSession.bootstrap`** (`useSession.ts:95-112`) — four
  AsyncStorage reads parallelized via `Promise.all`. Clean.
- **`useFeedback.hydrate`** (`useFeedback.ts:101-126`) — guarded by
  `hydrated` flag, single AsyncStorage read, idempotent. The
  AppState 'active' listener at `App.tsx:100-110` fires `retrySync`,
  which is gated on unsynced items (`useFeedback.ts:164-167`). No
  double-fire risk.
- **`switchLeague`** atomicity (`useSession.ts:146-178`) — uses
  zustand's `set` callback for atomic check-and-acquire. Correctly
  prevents two concurrent switches.
- **Bottom-tab `lazy`** — React Navigation v7 defaults
  `bottom-tabs.lazy = true`, so RankStack / TradesStack / Matches /
  League screens only mount on first focus. Confirmed no `lazy:
  false` override in `TabNav.tsx`. Tab cold-start cost is bounded to
  the tab the user touches.
- **`PlayerCard` / `TradeCard`** — no `<Image>` usage, text-only.
  No avatar fetches on the hot paths.
- **Sentry init** (`sentry.ts:27-58`) — gated on DSN. Without a DSN
  (current default) it's truly a no-op. With a DSN, `traces
  SampleRate: 0.2` in prod is reasonable.
- **`useQuery` retry config** — global `retry: 1` plus per-query
  defaults are sensible; no infinite-retry storms.
- **Reanimated worklets** in `TiersScreen` and `RankScreen` — every
  JS-side function called from a worklet goes through `runOnJS`.
  Same audit hygiene as PR #44. No release-build crash risk.

---

## Open questions for the user

1. **Is the user's "loads too slowly" complaint primarily about cold
   dyno (30–60 s) or warm-but-feels-slow (0.5–1.5 s with bare
   spinner)?** The fixes for each are different. #M1 (skeleton)
   addresses both perceptions; #M2 (prefetch) only meaningfully helps
   warm. If it's mostly cold-dyno, the $7/mo Render starter dyno
   (no sleep) remains the only complete fix and is worth re-raising.

2. **Should Trios prefetch on `RankMenu` mount (i.e. on tab tap)
   rather than on row selection?** Aggressive: warms `/api/trio?
   position=QB` the instant the user taps Rank, before they've
   decided which sub-mode to enter. Pays the network cost on every
   Rank-tab tap including ones that end up in Tiers/Manual/Overall/
   Trends. Probably worth it (one wasted request per misroute vs.
   instant Trios for the 60 %+ who pick Trios).

3. **Tiers: should the tier bins paint with their TIER labels before
   `rankings` resolves?** I think yes — the user sees "Elite /
   Starter / Solid / Depth / Bench" headers immediately and chips
   stream in. But it changes the page from "loading state → loaded
   state" to "skeleton → populated", which is a bigger visual change
   than #M1 on Trios. Worth a quick design call.

4. **Is the `useFeedback` AppState `retrySync` worth keeping inline
   in `App.tsx` (line 100-110)?** It blocks no UI but does kick a
   sequential POST loop on every foreground. On a tester device with
   30 unsynced notes that's 30 sequential requests. Currently fine
   in practice; flag if this user count grows.

5. **Should `QueryClient`'s `defaultOptions.queries.staleTime` move
   from 30 s to 60 s?** Most per-screen queries override it anyway.
   60 s would make the global floor match the median, and any screen
   that really needs 30 s can declare it.
