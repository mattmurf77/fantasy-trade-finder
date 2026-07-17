# #132 — Tiers "All players" view + cross-position trios (and the #62 verdict)

**Covered feedback IDs:** #132 (feature), #62 (deferred swipe-gesture verdict — recorded here per the batch grouping).
**Branch:** `trade-engine-v2` (TIERS VIEW group of the 2026-07-17 batch).
**State:** built + verified (backend suite green, tsc clean, sim run below).

## What shipped

### (a) Tiers "All" board — mobile

`TiersScreen` position switcher gains an **All** tab (`tiers.pos-tab.all`;
PositionTabs spec's Overall-tab treatment — ice underline, not a position hex)
rendering the merged cross-position board: every player from the unfiltered
`/api/rankings` payload, bucketed into the same 8-tier pick-value ladder by
**each player's own position's** thresholds (`autoBucketMixed` in
`mobile/src/utils/tierBands.ts` — bands are position-uniform today, so this
matches a single-position walk, and stays honest if bands ever diverge),
value-sorted within tier. Drag, multi-select, tier-target chips, bulk
rank/tier moves, sticky banner and expand all operate on the merged board
unchanged. Positional rank badges (QB4, WR12, …) are derived client-side on
the All board (the unfiltered payload's `rank` is overall), mirroring
ManualRanksScreen's `posRanks` map.

**Cross-position save design (the load-bearing decision).**
`POST /api/tiers/save` is per-position by contract (rejects anything but
QB/RB/WR/TE, and `apply_tiers` silently drops pids outside that position's
pool) — posting a merged board to one position would silently corrupt it.
Saves therefore stay per-position and the All view **routes every mutation
to the owning position's pathway, client-side**:

- **Save** splits the board by `player.position` into four per-position
  `{tiers, cleared_pids}` payloads and issues one `saveTiers(pos, …)` per
  position (positions with nothing assigned/cleared are skipped —
  empty+empty is a 400 by contract). `cleared_pids` are routed by owning
  position via a pid→position lookup from the loaded payload + pool.
- **Reset to suggested** likewise fans out as per-position clear-only saves
  (Alert copy says ALL positions).
- **Round-trip semantics:** tier *membership* and *within-position order
  inside a tier* round-trip exactly (each position's list is submitted in
  user order and spread across the band). The **cross-position interleave
  within a tier is not literally persisted** — each position's list spreads
  independently across the same uniform band, so after save+reload the
  intra-tier interleave is re-derived from the band Elos. Documented
  limitation, not data loss; tier assignment (the thing the ladder means)
  is exact.
- Quick set is hidden on the All tab (it's a per-position walk). The
  copy-from-format button is position-independent and untouched (owned by
  the #124/#139 agent this batch).
- Query key for the All read is `['rankings', fmt, 'all']` — deliberately
  shared with ManualRanksScreen's overall board. All-view saves/resets
  invalidate the whole `['rankings', fmt]` prefix (they touch every
  position).
- Known edge: an All-view save is up to four requests via `Promise.all`; a
  partial failure surfaces the error toast while some positions may have
  committed. Re-tapping Save is idempotent (full board re-post), so the
  recovery is the button the user is already looking at.

### (b) Cross-position trio variety — backend

`ranking_service` gains a fourth trio lane, **cross_pos**
(`_cross_position_trio`, reasoning `"Cross-position tier check: <tier>"`):
3 **same-tier** players from **≥2 different positions**, full-pool reach,
own rotating tier cursor (random start, FB #97 pattern), freshest-member
picks within each position, standard anti-repeat with the FB #97
partial-relaxation (which additionally never collapses the position spread
below 2). Falls back to tightest when no tier holds 3+ members across 2+
positions.

- **Gate:** served only when `_trade_unlocked()` — all four positional
  interaction thresholds met (the trio-method trade-finder unlock). The
  gate lives in the service (it only sees interaction counts), so users who
  unlocked via the tiers/manual methods stay gated until their swipe counts
  catch up — a deliberate conservative under-serve, never a pre-unlock
  leak. Pre-unlock the lane is off regardless of config.
- **Knob:** `trio_cross_pos_rate` (default **0.15**, model_config-tunable,
  documented in docs/config-reference.md). Its share comes out of the
  tightest remainder — boundary (0.4) and within-tier (0.35) keep their
  tuned calibration rates.
- **Trio pins:** all existing pins in `test_trio_variety.py` /
  `test_trio_boundary.py` pass **unmodified** (their fixtures are
  pre-unlock and/or single-position, so the gate stays closed — verified).
  New pins: `backend/tests/test_trio_cross_position.py` (8 tests — gate
  closed pre-unlock; same-tier ≥2-positions post-unlock; small-default +
  remainder-preserving weight; mix includes cross_pos only post-unlock;
  anti-repeat; tier-cursor rotation; single-position fallback).

## #62 verdict — swipe-left-reveals-tier-cards: **decline (do not build)**

The requested gesture is a horizontal pan on a Tiers row that reveals
tier-target cards. Every Tiers row lives inside `react-native-draggable-flatlist`
with the PlayerCard wrapped in `pointerEvents="none"` — the exact
configuration where adding any gesture recognizer that captures list touches
crashed TestFlight builds #11/#12 (lessons.md; treated as absolute). A
horizontal pan recognizer would have to mount inside the list's touch tree
and negotiate with both the long-press drag activation (220 ms +
`activationDistance: 18`) and vertical scroll, which is precisely that
hazard class; and the previously-suggested conflict-free host — a
non-draggable chevron gutter — was removed in 1.5.4 #98, so no touch real
estate exists on a row that the drag/scroll system doesn't already claim.
The need is already covered without new gesture surface: multi-select
tier-target chips (FB4-62) send any selection straight to a tier, Tier
up/down bulk moves (FB-73) step them, and Quick set (#104) covers the
guided path. Recommendation: close #62 as superseded by those affordances;
revisit only if the drag library is ever replaced.

## Files

- `backend/ranking_service.py` — trio-selector region: `trio_cross_pos_rate`
  default, `_cross_pos_cursor`, `_trade_unlocked`, `_pick_trio_variety`
  weights, `cross_pos` dispatch in `get_next_trio`, `_cross_position_trio`.
- `backend/tests/test_trio_cross_position.py` — new (8 pins).
- `mobile/src/utils/tierBands.ts` — additive `autoBucketMixed`.
- `mobile/src/screens/TiersScreen.tsx` — All tab + routing (list/view
  regions only; copy-from-format region untouched).
- `mobile/.maestro/flows/tiers-all-board.yaml` — new feature flow.
- Docs: `docs/config-reference.md` (knob), `docs/glossary.md`
  (cross-position trio / All board), `mobile/src/components/CLAUDE.md`
  (testID registry: `tiers.pos-tab.all`).

## Verification

Static verification complete; **simulator verification is deferred to the
batch's dedicated dual-agent QA round** (orchestrator directive 2026-07-17:
five agents were contending for the shared sim/harness, and the combined
build gets a full QA pass anyway).

Done this session:

- `python3 -m pytest backend/tests/ -q` — **618 passed, 0 failed** (full
  suite incl. parallel agents' in-flight work). Trio pins itemized: all 15
  pre-existing pins in `test_trio_variety.py` + `test_trio_boundary.py`
  pass **unmodified** (their fixtures are pre-unlock and/or
  single-position, so the new lane's gate stays closed); **8 new pins**
  added in `test_trio_cross_position.py`.
- `cd mobile && npx tsc --noEmit` — clean.
- Grep-level routing sanity: exactly four `saveTiers(` call sites in
  `TiersScreen.tsx` — L279 (single-position save, guarded `!isAllView`),
  L320 (All-view save fan-out: `POSITIONS.filter(...).map(pos =>
  saveTiers(pos, perPos[pos], clearedByPos[pos]))`, `perPos` keyed by
  `p.position`), L876 (single-position reset), L883 (All-view reset
  fan-out). A literal `'ALL'` can never reach the endpoint (which 400s on
  anything outside QB/RB/WR/TE).

### Manual checks for the batch QA round (must-run)

A ready-made flow exists: `mobile/.maestro/flows/tiers-all-board.yaml`
(standard profile; drag via the 06-flow slow-swipe technique).

1. **All view render** — Tiers → tap `tiers.pos-tab.all`: merged board
   renders all four positions grouped under the 8 tier headers, save bar
   reads "Save all tiers", positional badges read per-position (QB4,
   WR12 — not overall rank), Quick set button hidden, sticky banner +
   expand still work.
2. **Cross-position drag targets the right position save** — on the All
   board, drag (or multi-select + tier chips) a QB and a WR into new
   tiers → Save → "Tiers saved" toast → flip to the QB tab and the WR tab:
   each player sits in the tier assigned on the All board (proves the
   per-position routing); return to All: memberships identical
   (intra-tier cross-position interleave may re-derive — documented
   limitation, not a failure). Also verify a drag-release does NOT crash
   (lessons.md #11/#12 hazard class; no new gesture recognizers were
   added, so this is regression assurance only).
3. **Cleared-pid routing** — drag a pool (Unassigned) player into a tier,
   save, drag it back out, save again, reload: the player must not snap
   back into the tier (cleared pid reached ITS position's save).
4. **Trio variety appearance** — with a user past all four thresholds
   (standard profile post-unlock), request trios: within ~10 serves at
   default rates a mixed-position, same-tier trio should appear
   (reasoning "Cross-position tier check: <tier>"); a pre-unlock user
   must never see one.
5. **Reset on All** — "Reset to suggested" on the All tab clears manual
   placements for every position (Alert copy says ALL) and the board
   rebuilds to suggested tiers.
