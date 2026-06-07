# Agent 05 — React Native Rendering & Screen Perf

## Scope & method

**Scope.** RN rendering and screen-level performance on the data-heavy player +
trade surfaces, per brief: `TradesScreen.tsx`, `MatchesScreen.tsx`,
`OverallRanksScreen.tsx`, `RankScreen.tsx`, `TiersScreen.tsx`,
`PortfolioScreen.tsx`, `ManualRanksScreen.tsx`, and their row/card components
(`PlayerCard`, `TradeCard`, `TierBin`, `StrengthBar`, `PositionChip`,
`TierBadge`, `LeaderboardsSection`). Stack: RN 0.81 (new arch), Hermes,
Reanimated 4, `react-native-gesture-handler` 2.28, `react-native-draggable-flatlist`
4.0, Zustand 5, TanStack Query 5.

**Method.** Static analysis only — no code edits, no builds, no `npm`/`tsc`.
Read every target file end-to-end. Cross-referenced the `mobile/` git log to
avoid double-reporting already-shipped fixes (notably #56 progressive paint,
#60 Tiers coord-space, #62 Trios skeleton/prefetch, #65 cache invalidation).
Confirmed list sizing against the backend: `GET /api/rankings`
(`backend/server.py:1637-1655`) returns the user's **entire** ranked pool with
no `LIMIT` — for a dynasty board with `position=null` that is commonly
200-450+ players. That number drives the impact sizing for every
`.map()`-in-`ScrollView` finding below.

**Two whole anti-pattern categories came back empty and are NOT reported:**
- **`expo-image` / RN `<Image>` in lists / unbounded avatar lists** — there are
  *zero* `<Image>` usages anywhere in the player/trade surfaces. The only
  `<Image>` in the entire mobile app is a single profile avatar
  (`ProfileScreen.tsx:141`), not a list. No avatars are rendered in any deck,
  card, row, or leaderboard. `expo-image` is not a dependency and does not need
  to be (`mobile/package.json` has no image lib). Nothing to do here.
- **Missing `keyExtractor` on `FlatList`** — every `FlatList` in scope supplies
  a stable `keyExtractor` (`MatchesScreen.tsx:299,347`,
  `OverallRanksScreen.tsx:87`, `PortfolioScreen.tsx:118`,
  `ManualRanksScreen.tsx:363`). No finding.

**Severity vs RICE-P.** Several findings are real but low-severity because the
lists, while *unbounded in principle*, are gated behind unlock thresholds or
multi-league requirements that cap realistic sizes. Where that caps impact, the
Confidence note says so.

---

## OBS-RENDER-01 — TiersScreen renders the entire ranked pool as `.map()` inside a ScrollView (no virtualization)

- **Area:** RN rendering
- **Severity:** P1
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
`TiersScreen` lays out six `TierBin`s (unassigned + 5 tiers) inside a plain
`ScrollView` (`TiersScreen.tsx:722-756`). Each bin renders its players via
`buckets[t].map((p, i) => renderPlayerCard(p, t, i))` (`:736`, `:752`).
`renderPlayerCard` mounts a `DraggableRow` (`:521-563`) — and `DraggableRow` is
*heavy*: it allocates four `useSharedValue`s, a `useDerivedValue` gap-shift
worklet, three `useMemo`'d gestures (`LongPress`, `Pan`, `Race`), a
`useAnimatedStyle`, an `onLayout` that calls `measureInWindow`, and a
`PlayerCard` (which itself renders a `Pressable` + `PositionChip` +
conditionally `TierBadge`) (`TiersScreen.tsx:868-1045`). For a `position=null`-
equivalent board this is the full per-position pool; for a single position it's
commonly 40-120 chips — **all mounted at once**, none windowed.

### Why it's slow / costly
Anti-pattern: large list rendered eagerly via `.map()` in a `ScrollView`
instead of a virtualized list. The cost is multiplied here because every row is
a Reanimated + gesture node, not a static view. On position switch or on the
post-fetch `setBuckets` (`:219-241`), React mounts/commits *every* `DraggableRow`
in one synchronous pass — each registering a gesture handler and scheduling a
`measureInWindow`. That is the classic first-paint stall + GC pressure for the
screen, and it grows linearly with pool size. A `ScrollView` also keeps all
off-screen rows resident, so memory scales with the whole board rather than the
viewport.

### Evidence
- `TiersScreen.tsx:722` — `<ScrollView>` wrapper, not `FlatList`/`FlashList`.
- `TiersScreen.tsx:736,752` — `.map()` over every bucket with no windowing.
- `TiersScreen.tsx:888-1005` — per-row Reanimated allocations (4 shared values,
  derived worklet, 3 gestures, animated style) — confirms each row is expensive.
- `TiersScreen.tsx:898-904` — each row schedules `measureInWindow` on layout.
- Backend: `server.py:1637-1655` — `/api/rankings` returns the full pool, no cap.

### Recommendation(s)
- **Option A (preferred):** keep the `ScrollView` but make it explicit that this
  is a *drag canvas* and cap the working set. The drag-drop model in this screen
  depends on every chip being measured up-front (`chipLayouts` /
  `dropTargetAt` walk in `:319-356`), so naive `FlatList` virtualization would
  break drop-target resolution for off-screen chips. The surgical win is to
  **collapse non-active tiers by default** (render only counts + a "show N"
  expander) so only the position's actively-edited tier mounts its
  `DraggableRow`s. Mounts drop from "whole board" to "one tier". Medium effort,
  no change to the gesture math for the expanded tier.
- **Option B:** memoize `DraggableRow` with `React.memo` and a custom comparator
  (see OBS-RENDER-05) so that re-renders after a `setBuckets` don't re-run all
  rows — does *not* fix first-mount cost but caps re-render storms. Cheaper,
  partial.
- **Option C (largest):** migrate to a windowed drag library
  (`FlashList` + a measured drag overlay, or a Reanimated-native sortable that
  virtualizes). Big rewrite of the bespoke drag engine; defer unless A/B prove
  insufficient on large boards.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 8 | 1 | 80% | 2 | **3.2** |

- **Estimated latency delta:** Option A — first-paint / position-switch commit
  on a ~100-chip position drops from mounting ~100 Reanimated+gesture nodes to
  ~10-25 (active tier only); estimate −150-400 ms on the switch transition on a
  mid-tier device, plus a jank-burst removed. Scales worse (better savings) the
  larger the board.
- **Confidence note:** 80% — the eager-mount pattern and per-row cost are
  unambiguous in code. Exact ms needs a device profile (set to 50% if you want a
  measured number before committing Option C). Reach 8 because Tiers is a core
  tab opened every session once unlocked; Impact 1 (jank/dropped-frame burst,
  not a multi-second block).

### Related components
`TiersScreen.tsx`, `components/TierBin.tsx`, `components/PlayerCard.tsx`,
`utils/tierBands.ts` (`autoBucket`), `api/rankings.ts` (`getRankings`).

### Prerequisites / dependencies
None for A/B. Option C depends on a drag library that virtualizes while keeping
screen-Y measurement (the #60 fix invariant — drops must resolve in screen-Y).

### Regression risk
Medium for Option A: collapsing tiers must not break the drop-target walk
(`dropTargetAt` reads `chipLayouts` for chips in the target zone — a collapsed
zone has no measured chips, so dropping *into* a collapsed tier must auto-expand
or fall back to append-at-end). Must re-verify the screen-Y drop coordinate fix
from PR #60 still holds. Tier colors / `TIER_LABEL` / band thresholds are a
cross-client invariant — do not touch `autoBucket` or `tierBands`.

---

## OBS-RENDER-02 — OverallRanksScreen FlatList rows are non-memoized and re-render the whole list on refetch

- **Area:** RN rendering
- **Severity:** P2
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
`OverallRanksScreen` correctly uses a `FlatList` over the full ranked pool
(`OverallRanksScreen.tsx:85-93`), but `renderItem` is an inline arrow that
constructs `<Row player={item} overallRank={index + 1} />` (`:89`), and `Row`
(`:103-122`) is a plain function component — **not** wrapped in `React.memo`.
There is also no `getItemLayout`. The rows are fixed-height
(`row` + `sep` styles, `:150-156`), so `getItemLayout` is computable.

### Why it's slow / costly
Two anti-patterns: (1) non-memoized list-row component → on any parent
re-render that produces a new `data` array (the `useMemo` at `:35-41` recomputes
a fresh sorted array whenever `ranksQuery.data` changes, e.g. a background
refetch every 30 s staleTime, or the `['rankings']` family invalidation fired by
RankScreen/Tiers/Manual on every submit/save — `RankScreen.tsx:145`,
`TiersScreen.tsx:145`, `ManualRanksScreen.tsx:105`), `FlatList` re-renders all
*resident* `Row`s because nothing tells React they're unchanged. (2) Missing
`getItemLayout` forces RN to measure each row during scroll/scroll-to, costing
extra layout passes on a long board.

### Evidence
- `OverallRanksScreen.tsx:103` — `function Row(...)`, no `React.memo`.
- `OverallRanksScreen.tsx:89` — inline `renderItem` arrow (new identity each
  render; harmless alone but combines with the non-memo row).
- `OverallRanksScreen.tsx:35-41` — `rows` is a fresh array on every
  `ranksQuery.data` change; the `['rankings']` family is invalidated app-wide on
  every trio submit / tier save / manual reorder.
- No `getItemLayout` prop on the `FlatList` (`:85-93`); rows are fixed-height.

### Recommendation(s)
- **Option A (preferred):** wrap `Row` in `React.memo` (props are `player`
  object + `overallRank` number — stable across refetches when content is
  unchanged) and add `getItemLayout` using the known row+separator height.
  Cheap, removes the per-refetch re-render of resident rows and the per-scroll
  measure. Pure client change, no behavior change.
- **Option B:** also hoist `renderItem` to a `useCallback`. Minor; only matters
  once `Row` is memoized.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 4 | 0.5 | 80% | 0.5 | **3.2** |

- **Estimated latency delta:** removes a full-list re-render (resident rows
  only, ~10-20 on screen) on each `['rankings']` invalidation — a few dropped
  frames avoided per submit/save while this screen is mounted; smoother scroll
  via `getItemLayout`. No first-paint change. ~−50-150 ms jank on the refetch.
- **Confidence note:** 80% — pattern is clear. Reach 4 (Overall is a secondary
  read-only view, not a core daily tab); Impact 0.5 (smoothness, not a block).

### Related components
`OverallRanksScreen.tsx`, `components/PositionChip.tsx` (rendered per row).

### Prerequisites / dependencies
None.

### Regression risk
Low. `React.memo` on a pure presentational row is safe; `getItemLayout` must use
the *actual* fixed height including the 1px separator or scroll position math
drifts — verify against the `row`/`sep` paddings.

---

## OBS-RENDER-03 — ManualRanksScreen `renderItem` depends on `editValue`, re-creating the row callback on every keystroke during a rank edit

- **Area:** RN rendering
- **Severity:** P2
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
`ManualRanksScreen` uses `DraggableFlatList`. Its `renderItem` is a
`useCallback` whose dependency array is `[commitRankEdit, editValue, editingPid]`
(`ManualRanksScreen.tsx:231-290`). `editValue` is the live text of the inline
rank-number `TextInput` (`:194`, bound at `:252-254`). Every keystroke in that
input calls `setEditValue`, which changes `editValue`, which **re-creates the
`renderItem` callback identity**, which makes `DraggableFlatList` re-render its
rows.

### Why it's slow / costly
Anti-pattern: hot-path state (per-keystroke input value) leaked into a list
`renderItem` dependency. The `editValue` is only needed by the *one* row being
edited, but threading it through `renderItem` re-renders the *whole visible list*
on each character. On a long board (`getRankings(null)` returns the full pool,
`api/rankings.ts:96-99`) the visible window of draggable rows re-renders on every
digit typed. `DraggableFlatList` rows are gesture-wrapped, so this is more
expensive than a plain row.

### Evidence
- `ManualRanksScreen.tsx:289` — `useCallback(..., [commitRankEdit, editValue, editingPid])`.
- `ManualRanksScreen.tsx:254` — `onChangeText={setEditValue}` on the per-row input.
- `ManualRanksScreen.tsx:249-260` — only the editing row consumes `editValue`;
  all other rows ignore it but still re-render.

### Recommendation(s)
- **Option A (preferred):** lift the inline `TextInput` and its `editValue`
  state into a small self-contained `RankEditRow` child that owns its own draft
  string, and have `renderItem` depend only on `editingPid` (which row is in edit
  mode) — not the keystroke value. The list stops re-rendering on every digit.
  Medium-small effort, isolates the input.
- **Option B:** keep `editValue` in a `useRef` + a single-row force-update, and
  drop it from the `renderItem` deps. Smaller diff but more bespoke.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 4 | 0.5 | 80% | 1 | **1.6** |

- **Estimated latency delta:** eliminates a full-visible-list re-render per
  keystroke during jump-to-rank edits — a typed 3-digit rank goes from ~3
  list-wide re-renders to ~3 single-row updates; removes input lag/jank while
  typing. Only hits during the rank-edit interaction, hence Reach 4.
- **Confidence note:** 80% — dependency leak is explicit. Impact 0.5 because it
  only bites during the edit gesture, but it's a felt input-latency issue when it
  does (typing into a list that re-renders itself).

### Related components
`ManualRanksScreen.tsx`, `react-native-draggable-flatlist`.

### Prerequisites / dependencies
None.

### Regression risk
Low-medium. Must preserve the existing edit semantics: `selectTextOnFocus`,
`onBlur`/`onSubmitEditing` → `commitRankEdit`, and the filter-switch dismissal
(`:319-326`). Extracting the row must keep `commitRankEdit` reading the latest
draft.

---

## OBS-RENDER-04 — Find-a-Trade poll re-creates a fresh `deck` array reference per tick; deck render is non-virtualized but bounded

- **Area:** RN rendering
- **Severity:** P3
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
The Trades deck itself is *not* a list-perf problem — only `topCard` + a peek of
`nextCard` are rendered (`TradesScreen.tsx:601-614`), so deck size doesn't drive
render cost. The render concern is the 1.5 s status poll: each tick calls
`setJob(next)` with a brand-new snapshot object (`:243`), and the deck-append
effect runs on `[job?.cards.length, job?.status]` (`:274-282`). The
`sortedDeck` `useMemo` re-runs only when `deck`/`fairnessOn` change
(`:355-358`) — correctly memoized. The `SwipableTopCard` gesture is keyed by
`topCard.trade_id` (`:610`) and its `pan` gesture is `useMemo`'d
(`:800-824`) — also correct.

The residual cost: `setJob` fires every 1.5 s even when `cards.length` and
`status` are unchanged, causing a `TradesScreen` re-render each tick (the screen
reads `job?.status`, `job.opponents_done`, `job.cards.length` directly in JSX at
`:551,570-576`). The deck-append effect is guarded against the no-op via its
length/status deps (good), but the *screen* still re-renders on every poll while
a job runs.

### Why it's slow / costly
Minor anti-pattern: a 1.5 s `setState` cadence that re-renders the whole screen
subtree even on unchanged-progress ticks. Most ticks during a multi-opponent job
*do* change `opponents_done`, so the re-render is mostly legitimate (the progress
strip must update). The waste is the tail end where `opponents_done` has plateaued
but `status` is still `running`. This is a smoothness/battery nit, not a stall —
and the network-cadence half of it is already covered by the worked example
OBS-NET-07 (poll backoff), so this observation is scoped to the *render* side
only.

### Evidence
- `TradesScreen.tsx:243` — `setJob(next)` every tick; new object identity always.
- `TradesScreen.tsx:551,570-576` — screen JSX reads `job.*` directly, so each
  `setJob` re-renders the screen.
- `TradesScreen.tsx:274-282` — deck-append effect *is* correctly gated on
  `cards.length`/`status` (no spurious deck rebuild) — noted so synthesis
  doesn't double-flag it.

### Recommendation(s)
- **Option A (preferred):** bail out of `setJob` when the incoming snapshot is
  shallow-equal on the fields the UI reads (`status`, `opponents_done`,
  `opponents_total`, `cards.length`) — keep the previous object reference so
  React skips the re-render. Tiny, client-only, complements (does not replace)
  the OBS-NET-07 backoff.
- **Option B:** move the progress strip into a child component subscribed to a
  narrower slice so an unchanged tick can't re-render the deck region. More code
  for marginal gain given the deck region is already cheap (1-2 cards).

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 6 | 0.25 | 80% | 0.5 | **3.0** |

- **Estimated latency delta:** removes screen re-renders on no-change poll ticks
  (roughly the tail of each job); sub-perceptual per tick (<16 ms), value is
  battery/CPU during the wait, not user-visible latency. Reach 6 (every
  Find-a-Trade run), Impact 0.25 (below perception threshold per tick).
- **Confidence note:** 80% on the mechanism; Impact deliberately minimal. This is
  a polish item — most ticks legitimately change progress, so the real-world
  saved renders are a minority of ticks.

### Related components
`TradesScreen.tsx` (poll effect + progress strip), `api/trades.ts`
(`getTradeStatus`). Overlaps the *network* cadence finding OBS-NET-07 (agent-06)
— cross-ref, don't merge.

### Prerequisites / dependencies
None. Pairs naturally with OBS-NET-07 poll backoff.

### Regression risk
Low. The shallow-equal guard must still let `cards.length` growth through (so
streaming cards land) and must let the `running → complete` flip through (so the
deck-append effect's same-length-different-content case still fires — see the
existing comment at `:266-273`).

---

## OBS-RENDER-05 — PlayerCard / TradeCard / DraggableRow are not memoized; shared list cards re-render with their parents

- **Area:** RN rendering
- **Severity:** P2
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
The shared card primitives are plain (non-memoized) components:
- `PlayerCard` is a `forwardRef` function with no `React.memo`
  (`PlayerCard.tsx:27-119`). It's the hot leaf rendered by *every* tier chip
  (`TiersScreen`), every Trios card (`RankScreen`), and inside every `TradeCard`
  side (`TradeCard.tsx:84-86,93-95`).
- `TradeCard` (`TradeCard.tsx:23-151`) is not memoized and `.map()`s
  `receivePlayers`/`givePlayers` into `PlayerCard`s, and calls `useFlag(...)`
  (`:44`) so it subscribes to the Zustand flag store.
- `DraggableRow` (`TiersScreen.tsx:868`) is not memoized (compounds OBS-RENDER-01).

In `TradeCard`, the player arrays are re-derived each render via
`Array.isArray(...) ? data.x : []` (`:38-39`) — a fresh `[]` on the fallback
path, but the normal path passes the same array reference through.

### Why it's slow / costly
Anti-pattern: non-memoized leaf components on hot paths. When a parent
re-renders (e.g. `MatchesScreen` `FlatList` re-render per OBS-RENDER-02-style
invalidation, or `TiersScreen` `setBuckets`), each `TradeCard`/`PlayerCard`
re-renders even when its `data`/`player` prop is referentially unchanged.
`PlayerCard` does non-trivial work per render (rank-style branching `:51-58`,
several conditional `Text` subtrees, a `Pressable` with a function-style prop
`:67-74`). Multiplied across a deck peek + match list + tier board, the wasted
reconciliation adds up. `TradeCard`'s `useFlag` subscription also means a flag
store change re-renders every mounted `TradeCard`.

### Evidence
- `PlayerCard.tsx:27` — `forwardRef(function PlayerCard...)`, no `memo`.
- `TradeCard.tsx:23` — `export default function TradeCardComp(...)`, no `memo`.
- `TradeCard.tsx:84-86,93-95` — `.map()` into `PlayerCard` per side.
- `TradeCard.tsx:44` — `useFlag('trade_math.human_explanations')` subscription.
- `TiersScreen.tsx:868` — `function DraggableRow(...)`, no `memo`.

### Recommendation(s)
- **Option A (preferred):** wrap `PlayerCard` and `TradeCard` in `React.memo`.
  Props are mostly primitives + a stable `player`/`data` object and `compact`
  bool; the function props (`onPress`, `onLongPress`) are the only churn risk —
  ensure call sites pass `useCallback`-stable handlers (RankScreen's
  `SwipePlayerCard` already memoizes via `useMemo` gestures; Tiers passes inline
  arrows in `renderPlayerCard` `:537-560` that would need hoisting for memo to
  bite). Start with `TradeCard` (cleanest — Matches/Trades pass stable `data`).
- **Option B:** memoize `DraggableRow` with a custom comparator that ignores
  unchanged `player`/`binIndex`/`binZone` and the shared-value props (which are
  stable refs). Biggest single win for the Tiers re-render storm, pairs with
  OBS-RENDER-01 Option B.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 6 | 0.5 | 80% | 1 | **3.0** |

- **Estimated latency delta:** cuts wasted re-renders of resident cards on
  parent updates — on the Matches list and the Tiers board, a refetch/invalidation
  re-renders only changed cards instead of all visible ones; ~−50-150 ms jank on
  those updates, scaling with visible card count. No first-paint change.
- **Confidence note:** 80% on the pattern. The caveat (memo only bites if call
  sites pass stable function props) is why Effort is 1 not 0.5 — Tiers'
  `renderPlayerCard` inline closures must be hoisted/stabilized to realize the
  full gain. Impact 0.5 (smoothness).

### Related components
`components/PlayerCard.tsx`, `components/TradeCard.tsx`, `TiersScreen.tsx`
(`DraggableRow`, `renderPlayerCard`), `MatchesScreen.tsx`, `RankScreen.tsx`,
`state/useFeatureFlags.ts`.

### Prerequisites / dependencies
For the Tiers half: hoist the inline arrows in `renderPlayerCard`
(`TiersScreen.tsx:537-560`) to stable callbacks first, or memo won't help there.

### Regression risk
Low-medium. `React.memo` on these presentational components is safe; the risk is
a *missed* re-render if a mutated-in-place prop ever stops triggering an update —
`buckets` are cloned on every mutation (`cloneBuckets`, `TiersScreen.tsx:1062`),
so arrays get new identities, which is memo-friendly. Verify the drop-preview
gap-shift (driven by shared values, not props) still animates — it reads
`useDerivedValue`, which is independent of `React.memo`.

---

## OBS-RENDER-06 — StrengthBar mounts ~24 sub-views per trade card via two `Array.from` maps

- **Area:** RN rendering
- **Severity:** P3
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
`StrengthBar` fakes a gradient by rendering `segments` (default **24**)
individual `<View>` slivers via `Array.from({length: segments}, ...)`
(`StrengthBar.tsx:64-80`). It's rendered once per `TradeCard`
(`TradeCard.tsx:78`). The color array is `useMemo`'d (`:40-44`) — good — but the
24 `<View>`s themselves are re-created each render and always mounted. There's
also a second `Array.from` for the colors inside the memo. So every trade card =
24 extra leaf views just for the bar.

### Why it's slow / costly
Minor anti-pattern: a decorative element implemented as N native views instead of
one. On the swipe deck only ~1-2 cards exist so it's negligible there. On the
Matches list, every mutual/awaiting card carries a `StrengthBar`
(`TradeCard.tsx:78`, rendered for both `variant="match"` and the awaiting reuse),
so a screen of 10 matches mounts ~240 sliver views on top of the card content —
extra shadow-tree nodes, layout work, and memory for a purely cosmetic ramp.

### Evidence
- `StrengthBar.tsx:64-80` — `Array.from({length: 24}, ...)` → 24 `<View>`s.
- `StrengthBar.tsx:36-44` — segments default 24; colors memoized but views not.
- `TradeCard.tsx:78` — `<StrengthBar value={matchPct} ... />` once per card.
- `MatchesScreen.tsx:322-328,371-374` — a `TradeCard` (with bar) per list row.

### Recommendation(s)
- **Option A (preferred):** render the bar as a single filled `<View>` over a
  track with a horizontal gradient — but since the app deliberately avoids
  `expo-linear-gradient` (`StrengthBar.tsx:22-23` comment), the zero-dep version
  is: one filled `<View>` whose `width: ${pct}%` and a single interpolated solid
  `backgroundColor` (the color at the value's position). Drops 24 views → 2 and
  keeps the red→green semantic via `interpolateRYG(pct/100)`. Loses the
  multi-stop ramp *within* the filled portion (cosmetic only).
- **Option B:** lower `segments` (e.g. 8-10) on the list/`compact` variant to cut
  the per-card view count while keeping the stepped look. Smaller change, keeps
  the gradient feel; pass a smaller `segments` from the Matches call path.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 6 | 0.25 | 80% | 0.5 | **3.0** |

- **Estimated latency delta:** Matches list with 10 cards drops from ~240 sliver
  views to ~20 (Option A) — fewer layout/commit nodes and lower memory on that
  list; small first-paint and scroll-smoothness gain (~−30-100 ms on a long
  matches list). Negligible on the 1-card swipe deck.
- **Confidence note:** 80%; Impact 0.25 because the view count is real but each
  sliver is trivial and the lists are short in practice (matches are gated on
  mutual likes, rarely dozens). Pure polish.

### Related components
`components/StrengthBar.tsx`, `components/TradeCard.tsx`, `MatchesScreen.tsx`,
`TradesScreen.tsx`. Tier colors are a cross-client invariant but the RYG match
ramp is **not** a tier color — safe to restyle.

### Prerequisites / dependencies
None.

### Regression risk
Low. Option A changes the bar's visual texture (solid fill vs slivered ramp) —
purely cosmetic; confirm the `valueTone` numeric callout and `accessibilityValue`
(`StrengthBar.tsx:60-62`) are preserved.

---

## OBS-RENDER-07 — MatchesScreen rebuilds three derived arrays + filter chips on every render; chips are `.map()` in a ScrollView

- **Area:** RN rendering
- **Severity:** P3
- **Status:** observed
- **Evidence type:** static-analysis

### What happens today
`MatchesScreen` derives `visibleMatches`, `visibleAwaiting`, and `filterChips`
via `useMemo` (`MatchesScreen.tsx:144-176`) — correctly memoized on their inputs.
The `filterChips` memo does a `Set` build + two `.filter().map()` passes + a dedup
(`:159-176`); it recomputes whenever `leagues`, `allMatches`, or `allAwaiting`
change (e.g. each cross-league refetch at 15 s staleTime). The chips then render
via `filterChips.map(...)` inside a horizontal `ScrollView` (`:234-259`) with
inline `Pressable` style arrows. The match/awaiting lists themselves correctly
use `FlatList` with `keyExtractor` (`:296-332`, `:344-379`) and inline
`renderItem` (acceptable for `FlatList`).

### Why it's slow / costly
This is largely *already correct* — flagging it so synthesis sees it was checked,
and to note the two residual nits: (1) the `filterChips` derivation is O(matches +
awaiting) work rerun on every cross-league refetch; for a power user with many
cross-league matches this is a non-trivial reduce/dedup each 15 s tick while the
screen is focused. (2) The horizontal chip `ScrollView` `.map()`s all leagues —
bounded by the user's league count (small), so virtualization is unnecessary, but
the per-chip inline style arrow (`:247-251`) defeats any future chip memoization.

### Evidence
- `MatchesScreen.tsx:159-176` — `filterChips` reduce/filter/dedup memo.
- `MatchesScreen.tsx:241-258` — `filterChips.map()` in a horizontal `ScrollView`
  with inline `Pressable` style arrows.
- `MatchesScreen.tsx:296-332,344-379` — main lists are proper `FlatList`s
  (no finding on those).

### Recommendation(s)
- **Option A (preferred):** leave as-is — the lists are virtualized and the chip
  count is bounded by league count. If a power-user profile shows the
  `filterChips` reduce as hot, extract the chip into a memoized `FilterChip` and
  hoist its `onPress`. Document as "verified acceptable" rather than fix.
- **Option B:** if pursued, memoize the `Set`-based seen-id lookup across renders
  with a ref keyed on `leagues` identity. Marginal.

### RICE-P
| Reach | Impact | Confidence | Effort | **Score** |
|------:|-------:|-----------:|-------:|----------:|
| 4 | 0.25 | 50% | 0.5 | **2.0** |

- **Estimated latency delta:** negligible for typical league counts (<10);
  unmeasurable first-paint impact. Listed for completeness / to prevent
  re-investigation.
- **Confidence note:** 50% — this is a "checked and mostly fine" entry; the only
  real-world cost (the 15 s `filterChips` recompute) is tiny unless a user has
  many cross-league matches. Lowest-priority in this file.

### Related components
`MatchesScreen.tsx`.

### Prerequisites / dependencies
None.

### Regression risk
Low. The chip dedup logic (same-named cross-league disambiguation) is load-bearing
for correctness — don't simplify it away.

---

## Top 3 by RICE-P

1. **OBS-RENDER-01 — TiersScreen non-virtualized drag canvas (RICE-P 3.2, P1).**
   Highest-severity render issue: the whole ranked pool mounts as
   Reanimated+gesture rows in a `ScrollView`. Collapse non-active tiers
   (Option A) to cut mounts from "whole board" to "one tier."
2. **OBS-RENDER-02 — OverallRanks non-memoized rows + missing `getItemLayout`
   (RICE-P 3.2, P2).** Cheapest high-value fix (0.5 day): `React.memo(Row)` +
   `getItemLayout` stops a full-list re-render on every app-wide `['rankings']`
   invalidation.
3. **OBS-RENDER-04 — Trades poll re-renders the screen on no-change ticks
   (RICE-P 3.0, P3)** — tied on score with OBS-RENDER-05 and OBS-RENDER-06
   (both 3.0). Listed here as the cross-cutting one; **OBS-RENDER-05**
   (memoize `PlayerCard`/`TradeCard`/`DraggableRow`) is the better *durable*
   investment if only one of the three is taken, since it compounds with
   OBS-RENDER-01.

---

## CROSS-REF (outside this lane — route to the right agent)

- **Network/poll cadence:** the 1.5 s Find-a-Trade poll's *network* cost (vs its
  render cost in OBS-RENDER-04) is the worked-example OBS-NET-07 territory —
  agent-06 (network/cold-start). `TradesScreen.tsx:233-261`.
- **Unbounded `/api/rankings` payload:** `server.py:1637-1655` returns the full
  ranked pool with no `LIMIT`/pagination — drives the client list sizes in
  OBS-RENDER-01/02/03. Belongs to agent-03 (backend routes) / agent-04 (data/DB)
  as a payload-size + pagination question.
