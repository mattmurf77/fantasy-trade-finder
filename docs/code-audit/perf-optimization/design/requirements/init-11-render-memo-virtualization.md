# REQ — INIT-11: Render Memoization + Tiers Virtualization

- **Initiative / Wave / Scope:** INIT-11 · Wave 2 (cheap memo wins) + Wave 3 (Tiers virtualization) · [M]
- **Source observations:** OBS-RENDER-01, OBS-RENDER-02, OBS-RENDER-03, OBS-RENDER-05, OBS-RENDER-06, OBS-CACHE-06
- **Peak RICE-P:** 3.2 (OBS-RENDER-01, OBS-RENDER-02)

## Problem statement

The mobile app's data-heavy screens contain a cluster of render anti-patterns —
non-memoized list-row components, a `renderItem` that re-creates on every
keystroke, an over-broad cache invalidation that forces full-list re-renders on
high-frequency mutations, no-change poll ticks that re-render the Trades screen,
and (the largest structural issue) the Tiers screen mounting the full ranked pool
as expensive Reanimated + gesture nodes in a non-virtualized `ScrollView`. Each
issue is individually modest but together they produce measurable jank, battery
drain, and dropped frames on the core ranking and trading surfaces.

## User stories

- As a **dynasty manager** editing my tiers, I want position switches and
  bucket reassignments to feel instant, so that I can reorganize my board without
  dropped frames or input lag.
- As a **dynasty manager** watching a trade job generate, I want the screen to
  stay smooth rather than re-rendering on every poll tick when nothing has changed.
- As a **dynasty manager** browsing my overall ranks, I want background refetches
  (triggered by trio submits) to be invisible — the list should not visibly
  re-render when my rankings haven't changed.
- As a **dynasty manager** editing a rank number manually, I want the input to be
  responsive with no keystroke lag while the surrounding list stays still.

---

## Wave 2 — Cheap memo wins

### Functional requirements

- **FR-W2-1 (React.memo on PlayerCard and TradeCard):** Wrap `PlayerCard`
  (`PlayerCard.tsx:27`) and `TradeCard` (`TradeCard.tsx:23`) in `React.memo`.
  For memo to bite on `PlayerCard` used in `TiersScreen`, hoist the inline arrow
  closures in `renderPlayerCard` (`TiersScreen.tsx:537–560`) to stable callbacks
  (`useCallback` or module-level) so the function-prop identity is stable across
  renders.

- **FR-W2-2 (OverallRanks memo + getItemLayout):** Wrap the `Row` component
  (`OverallRanksScreen.tsx:103`) in `React.memo`. Add `getItemLayout` to the
  `FlatList` (`OverallRanksScreen.tsx:85–93`) using the known fixed row-height
  (verify against `row`/`sep` style values at `:150–156`).

- **FR-W2-3 (ManualRanks edit-row extraction):** Lift the inline `TextInput` and
  its `editValue` state out of the main `renderItem` callback
  (`ManualRanksScreen.tsx:231–290`) into a self-contained `RankEditRow` child
  component that owns its own draft string. The `renderItem` `useCallback`
  dependency array must no longer include `editValue` — only `editingPid` and
  `commitRankEdit`. Preserve existing edit semantics: `selectTextOnFocus`,
  `onBlur`/`onSubmitEditing` → `commitRankEdit`, and the filter-switch dismissal
  (`:319–326`).

- **FR-W2-4 (Scoped rankings invalidation):** Change the `invalidateQueries`
  calls at `RankScreen.tsx:145`, `TiersScreen.tsx:145`, `TiersScreen.tsx:173`,
  and `ManualRanksScreen.tsx:105` from the broad `['rankings']` partial key to
  the narrower `['rankings', position]` + `['rankings', 'all']`, so a trio
  submit for QB does not mark WR/RB/TE Tiers caches stale. If INIT-07/OBS-CACHE-04
  key scoping (`['rankings', format, position]`) has landed, the invalidation
  prefix must match the new shape.

- **FR-W2-5 (setJob shallow-equal guard):** In `TradesScreen.tsx:243`, before
  calling `setJob(next)`, check whether the incoming snapshot is shallow-equal
  to the current `job` on the fields the UI reads (`status`, `opponents_done`,
  `opponents_total`, `cards.length`). If all are equal, skip the `setState` and
  retain the previous object reference so React skips the re-render. The guard
  must still pass through any increase in `cards.length` (streaming cards) and
  the `running → complete` status flip.

### Wave 2 acceptance criteria

- [ ] **AC-W2-1 — PlayerCard/TradeCard memo:** On `MatchesScreen`, a background
  refetch that does not change match data produces zero re-renders of visible
  `TradeCard` / `PlayerCard` instances (verify with React DevTools profiler or a
  render-count ref in development).

- [ ] **AC-W2-2 — TiersScreen memo with stable callbacks:** After hoisting
  `renderPlayerCard` closures, a `setBuckets` call that does not change a chip's
  `player`/`binIndex`/`binZone` does not re-render that chip's `PlayerCard`. The
  drop-preview gap-shift animation (driven by Reanimated shared values) still
  animates correctly — it is independent of `React.memo`.

- [ ] **AC-W2-3 — OverallRanks no re-render on unchanged refetch:** After a trio
  submit (which invalidates `['rankings', position]` + `['rankings', 'all']`), the
  `OverallRanksScreen` `FlatList` re-renders only rows whose rank changed; rows
  with identical data are skipped. `getItemLayout` is present and uses the correct
  row+separator height — verify scroll position is stable after a fast-scroll.

- [ ] **AC-W2-4 — ManualRanks no keystroke jank:** Typing a 3-digit rank number
  into a `RankEditRow` input does not trigger a visible re-render of the
  surrounding list; only the editing row updates per keystroke. The edit commits
  correctly on blur/submit; filter-switch while editing dismisses the input.

- [ ] **AC-W2-5 — Scoped invalidation:** After a QB trio submit, only
  `['rankings', 'QB']` (or `['rankings', format, 'QB']` if INIT-07 is live) and
  `['rankings', 'all']` are marked stale. `['rankings', 'WR']`, `['rankings',
  'RB']`, and `['rankings', 'TE']` retain their prior cache state (not stale,
  not refetched).

- [ ] **AC-W2-6 — setJob shallow-equal:** During a running trade job where
  `opponents_done` has plateaued but `status` is still `running`, no new
  `TradesScreen` re-render occurs on no-change poll ticks. The screen re-renders
  correctly when `opponents_done` increments or `status` flips to `complete`.

---

## Wave 3 — Tiers virtualization (structural)

### Functional requirements

- **FR-W3-1 (Collapse non-active tiers):** In `TiersScreen` (`TiersScreen.tsx:722–756`),
  render only the currently-edited tier's `DraggableRow` instances; all other
  tiers are collapsed to a count badge + expand affordance. A collapsed tier must
  mount zero `DraggableRow` nodes. Only the expanded tier participates in the
  `chipLayouts` / `dropTargetAt` walk (`TiersScreen.tsx:319–356`).

- **FR-W3-2 (Drop into collapsed tier):** Dragging a chip over a collapsed tier
  must auto-expand that tier (or fall back to append-at-end) before the drop
  resolves. The `chipLayouts` for the newly expanded tier must be measured before
  `dropTargetAt` is called with the drop coordinate.

- **FR-W3-3 (Screen-Y invariant preserved):** The PR #60 screen-Y drop-coordinate
  model must be preserved end-to-end. All chip Y-coordinates stored in
  `chipLayouts` are screen-Y values (from `measureInWindow`), not bin-relative
  values. No change to the coordinate space or the `dropTargetAt` logic is
  permitted as part of this wave.

- **FR-W3-4 (Tier-band invariant preserved):** `autoBucket` (`utils/tierBands.ts`)
  and `TIER_LABEL` / tier-color constants must not be modified as part of the
  collapse/expand UI change. These are cross-client invariants per
  `docs/cross-client-invariants.md`.

### Wave 3 acceptance criteria

- [ ] **AC-W3-1 — Mounted node count:** On a position with 100 players across 6
  tiers, with one tier expanded, the number of mounted `DraggableRow` instances
  equals the expanded tier's player count (not 100). Confirm via React DevTools
  component tree count or a `console.count` guard in development.

- [ ] **AC-W3-2 — Position switch commit time:** Switching from QB to RB on a
  board with ~100 players per position completes the React commit phase in
  < 100 ms (measured via the React DevTools profiler, or via an RN
  `InteractionManager.runAfterInteractions` timing in development). This is a
  reduction from the full ~100-node Reanimated mount.

- [ ] **AC-W3-3 — Drop into expanded tier:** Dragging a chip to any location
  within an expanded tier drops it at the correct row (same result as the pre-
  collapse behavior on a fully-expanded board). Screen-Y coordinate semantics
  are unchanged.

- [ ] **AC-W3-4 — Drop into collapsed tier:** Dragging a chip over a collapsed
  tier auto-expands it (or appends to the end); the chip lands in a valid slot
  and is not lost.

- [ ] **AC-W3-5 — Tier band values unchanged:** After the W3 change, the
  `autoBucket` output for a given set of ELO scores is byte-for-byte identical
  to the pre-change output. Tier colors (`TIER_LABEL`) map to the same values.
  Confirm with a snapshot test or a golden fixture.

- [ ] **AC-W3-6 — No regression on PR #60 invariant:** Execute the manual test
  sequence from PR #60 (drag a chip across a tier boundary; verify the drop
  lands in the visually correct bin). The screen-Y coordinate model must not
  have regressed.

---

## Related components

- `mobile/src/components/PlayerCard.tsx:27` — non-memoized `forwardRef` (OBS-RENDER-05)
- `mobile/src/components/TradeCard.tsx:23` — non-memoized (OBS-RENDER-05)
- `mobile/src/screens/TiersScreen.tsx:537–560` — inline `renderPlayerCard` closures (OBS-RENDER-05)
- `mobile/src/screens/TiersScreen.tsx:722–756` — `ScrollView` + `.map()` (OBS-RENDER-01)
- `mobile/src/screens/TiersScreen.tsx:868–1045` — `DraggableRow` with Reanimated allocs (OBS-RENDER-01)
- `mobile/src/screens/TiersScreen.tsx:319–356` — `chipLayouts` / `dropTargetAt` (screen-Y walk)
- `mobile/src/screens/OverallRanksScreen.tsx:103` — non-memoized `Row` (OBS-RENDER-02)
- `mobile/src/screens/OverallRanksScreen.tsx:85–93` — `FlatList` without `getItemLayout` (OBS-RENDER-02)
- `mobile/src/screens/ManualRanksScreen.tsx:231–290` — `renderItem` `useCallback` with `editValue` dep (OBS-RENDER-03)
- `mobile/src/screens/TradesScreen.tsx:243` — `setJob(next)` every tick (OBS-RENDER-04)
- `mobile/src/screens/RankScreen.tsx:145` — broad `['rankings']` invalidation (OBS-CACHE-06)
- `mobile/src/screens/TiersScreen.tsx:145,173` — broad `['rankings']` invalidation (OBS-CACHE-06)
- `mobile/src/screens/ManualRanksScreen.tsx:105` — broad `['rankings']` invalidation (OBS-CACHE-06)
- `mobile/utils/tierBands.ts` — `autoBucket`, tier-color constants (W3 invariant)

## Prerequisite components / dependencies

**Wave 2:**
- **FR-W2-1 (hoist closures) must land before memo bites on TiersScreen.** If
  `renderPlayerCard` still passes inline arrow props, `React.memo` on `PlayerCard`
  will have no effect in the Tiers context.
- INIT-07/OBS-CACHE-04 key scoping: if FR-W2-4 (scoped invalidation) lands after
  INIT-07, the invalidation prefix must be re-verified to match the new
  `['rankings', format, position]` shape. Land them together or sequence
  scoped-invalidation after key-scoping.

**Wave 3:**
- Wave 2 (FR-W2-1) must land first: stabilizing `renderPlayerCard` callbacks is a
  prerequisite for the collapse/expand plumbing.
- A golden snapshot test for `autoBucket` output and tier-color constants must
  exist before W3 ships (confirms the FR-W3-4 / AC-W3-5 invariant).
- The PR #60 manual regression test must be run and pass before merging W3.

## Non-functional requirements & invariants

- **ELO math invariant:** No ELO computation, K-factor, or tier-band threshold
  (`docs/cross-client-invariants.md`) is modified by any wave of this initiative.
  Rankings data is fetched from the server unchanged; only client-side render
  optimization is applied.
- **Screen-Y drop coordinate invariant (W3):** The PR #60 fix established that
  chip Y-coordinates in `chipLayouts` must be in screen space (from
  `measureInWindow`), not bin-relative space. W3 must not regress this. A
  collapsed tier has no measured chips; dropping into a collapsed tier must
  expand it and re-measure before resolving the drop.
- **Tier-band cross-client invariant (W3):** `autoBucket`, `TIER_LABEL`, tier
  colors, and band thresholds are shared with the web client and must not change.
  The collapse/expand UI is a display optimization only — it does not alter which
  tier a player belongs to.
- **`cloneBuckets` memo safety:** `buckets` are cloned on every mutation
  (`TiersScreen.tsx:1062`) so array identities change on update. `React.memo`
  comparators for `DraggableRow` must treat the new array identity as a real
  change but may compare `player.id`, `binIndex`, and `binZone` props shallowly
  to avoid spurious re-renders when only other buckets changed.
- **Reanimated shared values:** drop-preview gap-shift is driven by
  `useDerivedValue` worklets reading shared values, not React props. `React.memo`
  on `DraggableRow` does not affect worklet execution — the animation will
  continue to run independently of memoization.

## Out of scope

- Migrating `TiersScreen` to `FlatList` / `FlashList` with a windowed drag
  library (OBS-RENDER-01 Option C — deferred unless W3 proves insufficient).
- `StrengthBar` sliver reduction (OBS-RENDER-06 — deferred to Wave 3 polish,
  separate from this initiative).
- `MatchesScreen` filter chip extraction (OBS-RENDER-07 — verified acceptable,
  no action).
- Any backend route or data-layer change.
- Any web-client change.
