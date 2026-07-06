# PRD FB4-62 — Simpler tier moves in multi-select

**Feedback #62 (Tiers, polish):** "Need a simpler way to move players between tiers for multiselect,
likely just the tier cards from the [position] ranked section. For drag and drop, swiping left on
the card displays tier cards."

## Problem
Today, multi-select only moves the selected block ONE RANK per ↑/↓ tap. Crossing several tiers means
many taps. The user wants a **direct "send these to tier X"** action.

## Requirement (primary — implement this)
In multi-select mode, when ≥1 chip is selected, show a row of **tier-target chips** (Elite / Starter /
Solid / Depth / Bench, using `tierBands` labels + accent colors). Tapping a tier chip moves ALL
selected players directly into that tier (appended to the END of that tier, preserving their relative
order), then keeps them selected so the user can fine-tune with ↑/↓. This replaces the multi-tap grind.

## Secondary (only if cleanly doable — else defer & note)
"Swipe-left on a card reveals tier cards" for single-player quick reassign. ⚠️ The list uses
`react-native-draggable-flatlist` (pan-based drag) — a swipe gesture on the row risks the exact
gesture-capture conflict that broke builds #11/#12. **Do NOT introduce a swipe gesture that competes
with the drag.** If a conflict-free reveal isn't trivial, SKIP it and leave a `// FB4-62 deferred:`
note; the tier-target chips above already satisfy "a simpler way to move players between tiers."

## User story
I tap Select, tap three elite players, then tap the "Depth" chip — all three drop into Depth at once,
no repeated arrow taps.

## Acceptance criteria
- [ ] In multi-select with ≥1 selected, a tier-target chip row is visible (the 5 real tiers; not "unassigned").
- [ ] Tapping a tier chip moves every selected player into that tier (appended, original relative order
      preserved), removing them from their previous tiers; non-selected players are untouched.
- [ ] Selection persists after the move (chips stay selected); the existing ↑/↓/Done bar still works.
- [ ] Tier chips use `tierBands` label + accent (no hardcoded colors).
- [ ] No new gesture competes with the drag list (verify the drag still works after this change).
- [ ] tsc clean.

## Implementation notes
- File: `mobile/src/screens/TiersScreen.tsx`. The action bar already renders when
  `multiSelect && selectedIds.size > 0`. Add the tier-target chip row there.
- Reuse `TIERS`, `TIER_LABEL`, `accentFor`. The move = a `setBuckets` that, for each tier, filters out
  selected ids, then appends the selected players (in their current flattened order) to the target tier.
  Mirror the structure of the existing `bulkMove`. Keep `unassigned` untouched.
