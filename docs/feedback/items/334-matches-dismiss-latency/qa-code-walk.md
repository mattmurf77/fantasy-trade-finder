# CW-1 — code-walk proof: #334 dismiss resurrect-race (G9 build, 2026-08-16)

> Build deliverable required by `prd.md` § Test plan (D-056 replaces the
> retired simulator evidence for race-shaped behavior). All file:line cites
> are against branch `feat/fb334-matches` @ the G9 build commit
> (`mobile/src/screens/MatchesScreen.tsx` post-fix). Verified during build:
> the five pre-fix files (`MatchesScreen.tsx`, `TradesScreen.tsx`,
> `TabNav.tsx`, `useSession.ts`, `queryClient.ts`) were **byte-identical**
> between the PRD's base `0b2dcee` and this branch's base (specs commit
> `56856f7` on `origin/main 96f6945`) — every PRD cite re-verified, and the
> repopulation-path hunt was re-run at this base: **no seventh path** (grep
> over `mobile/src` for every `['matches','all']` / `['awaiting-trades']`
> reference, every `invalidateQueries`/`prefetchQuery`/`fetchQuery`/
> `setQueryData`/`refetchInterval`/`refetchOnWindowFocus` site).

## The mechanism being proven

A dismissed tile is hidden by **component state**, not by cache contents:

- `hiddenKeys` set — `MatchesScreen.tsx:109` (state), `:110`/`:118`
  (`hideKey`/`unhideKey`).
- Hide at tap time, both `ux.swipe_undo` branches — `:462` (mutual),
  `:510` (awaiting), before the flag branch in each handler.
- The rendered lists derive through the shared pure predicate
  `filterVisible(rows, leagueFilter, hiddenKeys, keyFn)`
  (`mobile/src/utils/matchesDerive.ts:38-48`) — `visibleMatches` `:673`,
  `visibleAwaiting` `:678`.

Therefore: **whatever any path writes into the TanStack cache, a row whose
key is in `hiddenKeys` cannot render.** That is the load-bearing claim; the
per-path walk below shows each path only ever writes the cache.

## Per-path walk (P1–P6)

| Path | (a) Where it writes the cache | (b) Why the written row cannot render | (c) Tap-time cancel |
|---|---|---|---|
| P1 mount/enabled refetch while stale | `matchesQuery` `MatchesScreen.tsx:257`, `awaitingQuery` `:272` (staleTime 15s; default `refetchOnMount`) write their query data | Render reads `visibleMatches`/`visibleAwaiting` (`:673`/`:678`), both filtered by `hiddenKeys` — cache write re-renders with the row still excluded | `:472`/`:517` (handlers) + `:309`/`:359` (`onMutate`) cancel any in-flight read at both dismiss moments |
| P2 pull-to-refresh | `onRefresh` → `refetch()` (`:781-784`); RefreshControls on both FlatLists | Same render guard — a refresh completing during the undo window or POST round-trip repopulates the cache but not the list | Same four `cancelQueries` sites kill a refresh **already in flight** at tap; a refresh started *after* the tap lands against the guard |
| P3 reconnect refetch | `refetchOnReconnect: true` app default (`mobile/src/state/queryClient.ts:27`; NetInfo-wired onlineManager) | Same render guard; note post-R-7 the awaiting query is always enabled, so reconnect now refetches it even off-segment — still guarded | Same; reconnect refetches begun before the tap are cancelled, later ones are guarded |
| P4 league switch (reachable mid-window via #319 open-in-calc) | `useSession.switchLeague` invalidates both keys (`mobile/src/state/useSession.ts:455-456`) → active queries refetch | Same render guard — the invalidation-triggered refetch writes the cache only | Tap-time cancel precedes it chronologically (switch happens after the dismiss tap); the refetch it triggers is a *new* read, handled by the guard |
| P5 Matches tab-press prefetch | `TabNav.tsx:746-750` `prefetchQuery(['matches','all'])` on every Matches tab press | Same render guard — prefetch writes the cache during the tab transition; the remount reads through `hiddenKeys`, which survives the tab switch (see (e)) | A prefetch in flight at tap time is cancelled by `:309`/`:472`; a later tab-press prefetch is guarded |
| P6 guide-v2 N6.1 gate check | `TradesScreen.tsx:3323` `fetchQuery({queryKey:['awaiting-trades']})` on the first-like beat — writes the awaiting cache **from another tab** | Same render guard — this is exactly why R-1 (render layer), not cancellation alone, is load-bearing: P6 can start *after* every tap-time cancel has already run, while the user sits on the Trades tab | Not applicable by design — see (e). Accepted side effect of R-3 (NB-1, verified `TradesScreen.tsx:3252-3268`): if a dismiss's cancel kills an in-flight P6 `fetchQuery`, it rejects into its own `.catch` → `decide(false)` → `v2ShowN61(false)` — the N6.1 beat shows **immediately with its router-less copy variant**; nothing defers. Benign, vanishingly rare |

## (d) The B-1 unhide ordering

The residual race after R-1+R-3 is a **GET racing the POST's commit**: a
list read that starts *after* `onMutate`'s `cancelQueries` (P2/P3/P6 during
the POST round-trip) can read the row **pre-commit server-side** and write a
resurrected list into the cache. The backend `retracted_at` filter
(`backend/database.py:4648/6798/7090/7247` — untouched) only governs reads
that hit the DB *after* the commit; it cannot close this window.

Ordering that closes it (`MatchesScreen.tsx`):

1. `onSuccess` fires — the POST has committed server-side.
2. `await queryClient.invalidateQueries(...)` (`:346` mutual, `:383`
   awaiting) — marks the key stale and **waits for the reconcile refetch to
   resolve**. Any resurrected pre-commit payload in the cache is overwritten
   by a post-commit list before the next step. The promise settles even if
   the refetch fails (TanStack contract), so no tile is hidden forever.
3. Only then `unhideKey(...)` (`:347`/`:384`) — the unhide lands against a
   post-commit cache and can never expose a resurrected row.

`onError` (`:323`/`:371`) unhides **immediately, first statement** — the
snapshot restore + undo-flag refetch that follow honestly return the row,
and it must render at once (R-5: never invisibly archived, never invisibly
hidden). Mutations are `retry: 0` (`queryClient.ts:30-33`), so exactly one
of `onError`/`onSuccess` runs per dismiss. Pinned by S-10c
(`mobile/tests/check-awaiting-dismiss.js` #27/#28) with the named sabotage
"unhide before await" — RED run recorded in `qa-notes.md`.

## (e) P6's off-screen timing — why the render guard suffices

P6 starts on a **Trades-tab** like, potentially seconds after the user
dismissed a row on Matches and switched tabs — after every tap-time
`cancelQueries` has run. The defense is solely R-1, and it holds because
`hiddenKeys` is **component state that survives tab switches**: React
Navigation bottom-tab screens stay mounted on blur by default, and this
tree sets no override — verified at build: `git grep` over `mobile/src` for
`unmountOnBlur` / `freezeOnBlur` / `detachInactiveScreens` finds **zero**
occurrences. The blurred MatchesScreen keeps its state; when the user
returns, `visibleAwaiting` re-derives against the P6-written cache with the
key still hidden. S-10e additionally pins the analysis premise that no
focus-refetch path exists (`refetchOnWindowFocus: false` app-wide, no
per-query override on this screen) even though the focusManager is
AppState-bridged (`mobile/App.tsx`).

## (f) The unmounted-tab dual (NB-4)

The proof must not rest on today's navigation config alone. If MatchesScreen
ever *were* unmounted (a future `unmountOnBlur`, a nav restructure):

- The unmount cleanup **flushes the pending dismiss first**
  (`MatchesScreen.tsx:443-448` → `flushPendingDismiss` `:412`), so the POST
  fires before the component state dies.
- The lost `hiddenKeys` state is then harmless: the flush's
  `mutate` → `onMutate` re-cancels in-flight reads and re-filters the row
  out of the cache (`:309-318`/`:359-368`), and the fresh mount starts with
  an empty `hiddenKeys` against a cache that either already excludes the row
  or reconciles to exclude it on the `onSuccess` invalidate.
- Worst case on a slow POST: the row could flash on the freshly mounted
  screen until `onMutate` runs (microtasks later) — a strictly smaller
  exposure than the pre-fix 5–8s resurrect, and only under a navigation
  config that does not exist today.

## Verification summary

- `npx tsc --noEmit` — clean.
- `mobile/tests/check-awaiting-dismiss.js` — 30/30 (existing 1–21
  byte-unmodified; new S-10a–e #22–30).
- `mobile/tests/check-matches-counts.js` — 21/21 (U-1…U-5 executed against
  the real transpiled `matchesDerive.ts` + S-11a–f).
- All 38 `mobile/tests/check-*.js` suites green; `testid-lint.sh` OK.
- Sabotage RED runs (proven-to-fail): see `qa-notes.md`.
