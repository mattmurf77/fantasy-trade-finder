# PRD FB-02 — Tiers interaction overhaul: drag engine + multi-select

**Feedback:** #27, #29, #32 (←#14, #15, #16, #22) · **Surface:** mobile · **Priority:** P0

Two coupled interactions on the Tiers screen are reworked together because they
share the same gesture/selection model.

---

## Part A — Drag "make room" (adopt the ManualRanks engine)

### Requirement
Replace the Tiers screen's custom Reanimated drag with the **same drag engine
ManualRanks uses** (`react-native-draggable-flatlist`) so that, while dragging a
player, the other tiles visibly shift in real time to open the destination slot
(Apple home-screen reorder feel) — within a tier. Cross-tier moves (dragging a
player from one tier to another, and to/from the unassigned pool) must still
work, and the PR #60 screen-Y drop-coordinate correctness must be preserved.

### User story
As a manager arranging my tiers, when I drag a player up or down, the surrounding
players slide out of the way to show exactly where the player will land — exactly
like the Manual Ranks screen — and I can still drag a player into a different
tier.

### Acceptance criteria
- [ ] Within a tier, dragging a chip animates the other chips making room
      (matches the ManualRanks feel; #30 is the reference). No more subtle ±10px
      gap (#27).
- [ ] The dragged chip's neighbors fully shift to the target slot (#29).
- [ ] Cross-tier drag still works: a player can be dragged from one tier into
      another and to/from the unassigned pool; the drop lands in the tier/slot
      shown during the drag (no "drops outside the field / much lower than
      intended" regression — #23 must stay fixed).
- [ ] Drop resolution remains in screen-Y coordinates (PR #60 invariant) — drops
      land where the finger is.
- [ ] Tier save still persists order correctly (`saveTiers` payload reflects the
      new within-tier order); auto-bucket / tier bands unchanged.

---

## Part B — Multi-select redesign (Select-button only, grouped move)

### Requirement
Remove the long-press multi-select trigger entirely. Multi-select is entered
ONLY via the existing **"Select"** button. In select mode, tapping a tile toggles
its selection with a clear **lighter-blue full-tile fill**. Up/down arrows move
the selected players as a **collapsed contiguous block** by one rank per tap.

### User story
As a manager, I tap **Select**, tap the players I want to move (each turns light
blue), then use up/down arrows to move them together through the rankings as a
group — without any long-press, and without the tiles being hard to tell apart.

### Acceptance criteria
- [ ] **Long-press no longer triggers multi-select** anywhere on Tiers
      (remove the two-stage long-press from PR #58).
- [ ] Tapping "Select" enters multi-select mode; tapping it again (or Cancel)
      exits and clears the selection.
- [ ] In select mode, tapping a tile toggles selection; a selected tile shows a
      **lighter-blue fill across the whole tile** (clear, not a subtle border).
- [ ] Up/down arrows appear when ≥1 tile is selected and move the selection.
- [ ] **Collapse-into-a-block semantics:** non-adjacent selected players gather
      into a contiguous group and move together toward the destination one rank
      per tap. (Locked decision — NOT shift-each-independently.) The block stays
      together across tiers as it moves.
- [ ] Selecting/deselecting causes no layout jump; drag is suppressed in select
      mode.
- [ ] Order persists via `saveTiers` after a grouped move.

## Implementation notes
- This rewrites the interaction core of `mobile/src/screens/TiersScreen.tsx`.
  Study `mobile/src/screens/ManualRanksScreen.tsx` for the
  `react-native-draggable-flatlist` setup (it's the gold standard per #30) and
  reuse that engine per-tier. Tiers is multi-bin (5 tiers + unassigned), so each
  tier is a draggable list; cross-tier moves need handling on drop (the existing
  `dropTargetAt` / screen-Y logic from PR #60 is the reference to preserve).
- **Owns only `TiersScreen.tsx`** (+ may add a small shared component under
  `mobile/src/components/`). Do NOT edit `ManualRanksScreen.tsx` or
  `PlayerCard.tsx` (other features own those). READ them freely.
- Preserve: tier colors/bands (`utils/tierBands`), the `cleared_pids` save logic,
  copy-from-format, the position switcher.
- Verify `cd mobile && npx tsc --noEmit` clean; manually reason through the
  worklet/JS boundary if any Reanimated remains (no JS calls from worklets w/o
  runOnJS — the PR #44/#60 invariant).
