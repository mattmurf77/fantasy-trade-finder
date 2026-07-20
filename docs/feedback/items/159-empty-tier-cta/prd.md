# FB-159 — Quick Set empty-tier CTA

- **Screen:** QuickSetTiers (guided tier walk) · also QuickRank if it shares the CTA
- **Type:** polish · **Reporter:** jonbonjourvi (filed v1.7.1)
- **Status:** requirement written 2026-07-18 (operator-dictated)

## Problem
During the Quick Set guided walk, when the user has selected **no** players for
the current tier, the primary CTA still shows its normal save-and-continue label,
giving no signal that proceeding leaves this tier empty. The save behavior itself
is already correct — an empty save composes as a skip (`QuickSetTiersScreen.onSave`,
the "nothing picked and nothing to un-pick" branch). This is a label/affordance
clarity fix only.

## Requirements
- **R-1 — empty-state label.** When the current tier's selection is empty (zero
  player chips selected), the primary CTA label changes to **"No players for this
  tier"**, shortened as needed to fit the button at the current type size without
  wrapping or mid-word truncation (e.g. "No players here" if the full string
  overflows — final short form at implementer discretion). Tapping it performs the
  **same** action as today's Save (commit the tier as empty and advance to the next
  tier). No behavior change — label only.
- **R-2 — revert on selection.** The moment one or more players are selected, the
  CTA reverts to its current content (label **and** behavior) exactly as today.
- **R-3 — immediate, state-driven.** The label swaps immediately on
  select/deselect (no reload), driven by the existing selection state
  (`selectedIds`). If Quick Rank shares this CTA/empty-tier pattern, apply the same
  rule there; implementer confirms.

## Out of scope
Skip button, Back button, and the `/api/tiers/save` contract — all unchanged. No
new tier semantics; unpicked-player demotion is a separate item (FB-161).

## Test plan
- Enter a tier, select nothing → CTA reads the empty-state label; tap → walk
  advances and the tier is saved empty.
- Select a player → CTA reverts to the normal label; deselect all → returns to the
  empty-state label.
- Maestro: extend the Quick Set flow to assert the CTA label text in both states
  (testID on the primary CTA if not already present).
