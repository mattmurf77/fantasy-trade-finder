# REQ — INIT-05: Wire focusManager + onlineManager

- **Initiative / Wave / Scope:** INIT-05 · Wave 1 · [M]
- **Source observations:** OBS-CACHE-03
- **Peak RICE-P:** 6.0

## Problem statement

TanStack Query's `refetchOnWindowFocus` is dead configuration in the mobile app
because the `focusManager` is never bridged to React Native's AppState; as a
result, resume-sensitive queries such as `['progress']` and `['matches','all']`
stay stale after backgrounding, and the `refetchOnWindowFocus: true` intent
written on `RootNav.tsx:80` is silently unreachable. Similarly, no
`onlineManager` bridge means `refetchOnReconnect` cannot fire on a genuine
network-reconnection event.

## User stories

- As a **dynasty manager**, I want the app to silently revalidate my progress
  and matches data when I return from the background, so that the board reflects
  any changes made by opponents while I was away.
- As a **dynasty manager**, I want the app to recover and refresh its data
  automatically when I regain connectivity, so that I do not have to manually
  navigate away and back to clear a stale screen.
- As a **developer**, I want `refetchOnWindowFocus` and `refetchOnReconnect` to
  behave as the TanStack documentation specifies, so that per-query focus/network
  config is not silently ignored.

## Functional requirements

- **FR-1** — Wire `focusManager.setEventListener` to React Native's `AppState`
  inside `mobile/App.tsx`, using (or reusing) the existing `'change'` listener
  at `App.tsx:84–94`, so that `handleFocus(true)` is called when AppState
  transitions to `'active'` and `handleFocus(false)` on any other state.
- **FR-2** — Wire `onlineManager.setEventListener` to `@react-native-community/
  netinfo`'s `addEventListener`, calling `setOnline(!!s.isConnected)` on each
  `NetInfo.NetInfoState` change, so that `refetchOnReconnect` fires on network
  recovery.
- **FR-3** — The `focusManager` bridge must be set up once at app startup, before
  the `QueryClientProvider` tree mounts, and the listener must be cleaned up
  (unsubscribed) when the component unmounts.
- **FR-4** — After the bridges are wired, the `refetchOnWindowFocus: true` on
  `RootNav.tsx:80` (`['progress']` query) must revalidate on resume when the
  query is stale (i.e., its `staleTime` has elapsed while backgrounded).
- **FR-5** — Queries whose per-query `staleTime` has **not** elapsed since their
  last successful fetch must **not** refetch on resume, preserving the existing
  per-screen tuning.
- **FR-6** — The trio deck (`['trio', position]` with `staleTime: 0` and
  `refetchOnMount: 'always'` at `RankScreen.tsx:78–80`) must **not** reshuffle
  mid-swipe on a resume event; the refetch must only fire if the screen remounts
  or an explicit invalidation is issued, not on focus alone.

## Acceptance criteria

- [ ] **AC-1** — Given the app is backgrounded for longer than 30 s (the global
  `staleTime`), when the user brings the app to the foreground, then the
  `['progress']` query issues a new network request within 2 s of the
  `AppState → 'active'` event.
- [ ] **AC-2** — Given a `['matches','all']` query whose `staleTime` has elapsed
  while backgrounded, when the user resumes, then `MatchesScreen` transitions
  from stale data to fresh data without a manual navigate-away-and-back.
- [ ] **AC-3** — Given the user is on `RankScreen` mid-swipe (trio deck active),
  when the app is briefly backgrounded and resumed within `staleTime`, then no
  new `/api/trio` request is issued and the current deck is not reset.
- [ ] **AC-4** — Given the device loses network and then regains it, when
  `NetInfo.isConnected` returns `true`, then at least one stale query with
  `refetchOnReconnect: true` (or the default) fires a refetch without a screen
  remount.
- [ ] **AC-5** — Given the `focusManager` bridge is registered, when
  `queryClient.ts` global `refetchOnWindowFocus: false` is the default, then a
  query with no per-query override does **not** refetch on resume (bridge does not
  override the global default).
- [ ] **AC-6** — NetInfo is confirmed present (transitively or explicitly) in
  `mobile/package.json` before the `onlineManager` bridge is shipped; if absent,
  it is added as a dependency.

## Related components

- `mobile/App.tsx:84–94` — existing AppState `'active'` listener (hook point)
- `mobile/src/state/queryClient.ts:21,24` — global `refetchOnWindowFocus: false`,
  `staleTime: 30_000`
- `mobile/src/navigation/RootNav.tsx:80` — dead `refetchOnWindowFocus: true` on
  `['progress']`
- `mobile/src/screens/RankScreen.tsx:78–80` — `staleTime: 0`,
  `refetchOnMount: 'always'` on trio deck

## Prerequisite components / dependencies

- None for the `focusManager` (AppState) half — the hook point already exists at
  `App.tsx:84–94`.
- The `onlineManager` half requires `@react-native-community/netinfo`; verify it
  is transitively present in `mobile/package.json` before wiring. If not, add
  it.
- No other INIT must land first.

## Non-functional requirements & invariants

- **Perf target:** no observable increase in total network requests per warm
  in-session navigation; focus-refetch budget is bounded by per-screen
  `staleTime` values.
- **No refetch storm:** with the bridge active, a resume event must not trigger a
  simultaneous refetch of every mounted query. This is guaranteed by the existing
  `staleTime` tuning (30 s global, 15 s progress, 60 s tiers-status), but must
  be verified across the full tab set.
- **Trio deck invariant:** the trio deck (`staleTime: 0`) is exempt from
  focus-triggered refetch mid-swipe. A reshuffle would discard user context.
  Confirm `refetchOnWindowFocus` for the trio query remains `false` (or
  effectively overridden) at `RankScreen.tsx:78`.
- **No ELO / tier-band invariant:** this change is purely reactive infrastructure
  (when to re-fetch, not what to compute). ELO math, K-factors, and tier bands
  are untouched.
- **Rollback:** removing the two `setEventListener` calls fully restores prior
  behavior; no persistent state is modified.

## Out of scope

- Changing any per-screen `staleTime` value as part of this initiative.
- Implementing `refetchOnWindowFocus` globally (the global default stays
  `false`; only queries with explicit `refetchOnWindowFocus: true` benefit).
- Optimistic pre-warming of queries during the splash (INIT-01) or on
  navigation (INIT-04).
- The `onlineManager` half if NetInfo adds unacceptable dependency weight — it
  may be deferred independently without blocking the `focusManager` half.
