# PRD — #58 Tier tiles are too big (density)

**Severity:** polish · **Screen:** Tiers (and the shared player row) · **Effort:** small–medium · **BLOCKED on operator screenshots**

## Problem
User: "Our tiles are too big. Prompt me and I will share screenshots from another app example for ranking and it feels better from a size perspective."

## Why (research)
- Competitors run **dense one-line rows**, not large tiles: DynastyGM `headshot · name · team chip · age(1dp) · value · pos-rank · R-tag` on a single line; DynastyDealer adds a thin trend-colored edge bar; both use **collapsible position groups** to keep the default view dense. [research-synthesis.md #58]
- External: **44pt minimum touch target** (Apple HIG) — rows must stay tappable, so "smaller" has a floor; ≥8px separation; **rows beat cards** for scannable ranking lists (NN/g); most-important attribute **top-left**; ~3–4 fields per row.
- No competitor publishes an exact row height — sizing is judgment, which is why the operator's reference screenshots matter.

## Goal
Shrink the tier chips/rows toward a compact, scannable one-line row that fits more players per screen, without dropping below the 44pt tap target and without losing the info the row needs (esp. the new positional rank from #53).

## Blocking input
**Get the operator's reference-app screenshots first.** They will pin: target row height, which fields to keep, and whether to adopt collapsible position groups. Do not finalize sizing without them — the user explicitly offered them and "feels better" is a visual target, not a spec.

## Decisions (provisional, pending screenshots)
1. Reduce chip vertical padding / font to a compact row while keeping the touchable area ≥44pt (touch target ≥ visual size via hitSlop if needed).
2. Per-row fields (align with #53/#54): position-color chip · name · **positional rank (prominent)** · value (0–10k, secondary) · optional small trend/age cue. Cap at ~3–4 visible fields.
3. Consider a thin tier/position color edge-bar instead of a large filled tile (DynastyDealer pattern).
4. Consider **collapsible position groups** so the board stays dense by default (DynastyGM/#14 accordion pattern) — but confirm against the screenshots; may be out of scope for a pure sizing pass.
5. Keep tier colors consistent across web/mobile/extension (cross-client-invariant).

## Acceptance criteria
- Tier rows are visibly more compact; more players visible per screen than v1.2.0.
- Touch targets remain ≥44pt; drag + tap-select still work (don't regress #57/#56).
- Matches the density the operator's reference screenshots indicate.
- `tsc --noEmit` clean; on-device comparison before/after.

## Files (anticipated)
- `mobile/src/components/TierBin.tsx`, `mobile/src/components/PlayerCard.tsx`, `mobile/src/screens/TiersScreen.tsx`
- theme tokens; `docs/cross-client-invariants.md` if tier sizing becomes shared.

## Status
**Blocked** — awaiting operator screenshots. Sequence after #53/#54 (the row's value/rank content) so density is tuned against the final row contents, not the current ones.
