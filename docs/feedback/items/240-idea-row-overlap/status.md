# #240 — More-trades idea rows blocking player names

**Status: fixed (worktree branch `teardown-remediation`, pending merge) — 2026-08-02**

Operator (build 68, bug): "The more trades section is blocking player names -
making the cards useless."

## Root cause

In `AssetIdeasPanel`'s `IdeaRow` the give↔receive name line shared its row
with a fixed-width right rail (signed diff chip + IN WINDOW tag / chevron).
Only the name column could shrink, so the rail starved it: on the featured
row a multi-asset idea ("Jaylen Wright + 2026 1st") showed ~9 characters per
side at default text size, and at larger Dynamic Type sizes (raw RN `Text`,
no scale caps) the rail widened until `rowMain` collapsed below the width of
the row's fixed elements (position dots + swap glyph + gaps), which then
overflowed underneath the diff chip — literal overlap. Verified with a Yoga
(RN's layout engine) simulation of the exact style tree.

## Fix

- Row restructure: the name line now owns (nearly) the full row width — only
  the 14pt chevron remains beside it. The diff chip and the IN WINDOW tag
  moved to the meta line (counterparty flexes + ellipsizes, chip/tag
  right-aligned). Names render fully or truncate with ellipsis; nothing can
  overlap.
- Text scaling: the panel's `Text`s now use the chalkline primitive
  (`a11y.text_scaling` caps — names/meta at the ×2.0 body tier, diff chip /
  IN WINDOW / group labels at the ×1.35 dense tier), so large OS text sizes
  stay inside the row.
- Re-verified with the same Yoga simulation: short names full, long
  multi-asset sides ~16–19 chars at 1×, no overflow at ×2.0 body scale on
  326pt or 288pt content widths.

## Files

- `mobile/src/components/AssetIdeasPanel.tsx` — only file changed

testIDs unchanged (`featured-trade.idea.<key>`, `trades.asset-ideas`).

## Verification

- `cd mobile && npx tsc --noEmit` — clean
- Yoga layout simulation (scratchpad) — before/after, cases: short names,
  multi-asset both sides, featured row, ×2.0 Dynamic Type, 320pt device
