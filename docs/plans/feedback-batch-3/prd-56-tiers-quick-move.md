# PRD — #56 Tier-list quick-move (select players → tap a tier)

**Severity:** idea (filed as bug) · **Screen:** Tiers · **Effort:** medium

## Problem / request
User: "It's difficult to follow where players are getting moved to when using multiselect… One idea: a quick-move within multiselect — select the players, then hit the tier to move the group there. Would require hidden tier buttons that only appear when using multiselect."

Two parts: (a) the current multiselect (tap chips → ↑/↓ arrows nudge them) is hard to follow because the screen doesn't keep the moving players in view; (b) the requested fix is a **tap-a-target-tier** bulk move.

## Why (research)
- **Validated pattern.** External best practice for moving MANY items between buckets on touch is **multi-select + "move to tier"**, not drag (drag is for single moves, fragile on touch — TierCraft does exactly multi-select→move-to-tier). [research-synthesis.md #56]
- The "select N → tap one action" grammar is already used by competitors (DynastyGM bulk-delete, DynastyDealer Mass-Send "apply to all"), so it's category-familiar.
- **No competitor has a user-editable tier board** to copy pixel-for-pixel — so this is product-led, build the user's exact ask.

## Goal
In multiselect mode, let the user select any set of chips and **tap a destination tier to move them all there at once**, with clear feedback on where they landed. Keep the existing ↑/↓ nudge as a secondary fine-adjust.

## Decisions
1. **Hidden tier-target bar, shown only in select mode** (as the user described): when ≥1 chip is selected, surface a row of tier buttons (Elite / Starter / Solid / Depth / Bench, using the existing `TIERS`/`TIER_LABEL` + tier colors). Tapping one moves all selected chips into that tier (appended in their current relative order) and clears or keeps the selection (decision: keep selection so multiple moves are easy; provide "Done").
2. **Follow-the-move feedback** (addresses part (a)): on a quick-move, briefly highlight/flash the destination tier and/or scroll it into view, plus the existing Toast ("Moved 3 to Starter"). This fixes the "can't tell where they went" complaint independent of the new buttons.
3. Reuse the existing buckets state + save path (`clearedPids`/saveMutation) — a quick-move is just a bucket reassignment, persisted on Save like any other.
4. Keep tap-to-select threshold logic intact; don't regress the drag (separate gesture; #57 just tuned it).

## Acceptance criteria
- In select mode with chips selected, a tier-target bar appears; tapping a tier moves all selected chips there.
- The destination is made visible (scroll-into-view and/or flash) and a Toast confirms the count + tier.
- Moves persist after Save + reload.
- Single-drag and ↑/↓ nudge still work; non-select mode is unchanged (no tier bar).
- `tsc --noEmit` clean; on-device verification of the full select → tap-tier → save loop.

## Files (anticipated)
- `mobile/src/screens/TiersScreen.tsx` (select-mode action bar → add tier-target buttons + move handler + visibility feedback)
- possibly `mobile/src/components/TierBin.tsx` if the flash/scroll-into-view lives there
- theme tokens only.

## Risk
Touches the multiselect + buckets logic adjacent to the drag gesture the operator just confirmed. Keep the new path additive (new buttons + handler); don't refactor existing select/drag code.
