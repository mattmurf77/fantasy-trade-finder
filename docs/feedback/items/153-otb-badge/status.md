# Status — #153 "On the Block" badge overlaps position tags → "OTB"

**2026-07-25 — fixed on worktree branch `worktree-agent-ae33eec5a00d24264` (worktree agent).**

Verbatim: "On the block rage is overlapping with positional tags. Change
'On the Block' to 'OTB'" (TradesHome, v1.9.1).

## Fix

- `mobile/src/components/TradeCard.tsx`: FB-147 block badge label
  `ON THE BLOCK` → `OTB` (Chalkline Badge, flare, construction unchanged).
  The shorter label no longer crowds the position tags in the player row —
  no layout rework needed.
- Accessibility text deliberately UNCHANGED: the row's grouped a11y label
  still appends the full phrase "on the block" for screen readers.

## Scope check

Grepped `on_block` / "on the block" across `mobile/`, `web/`, `extension/`:
the visual badge renders only in `TradeCard.tsx` (mobile).
`mobile/src/shared/types.ts` just types the `on_block` field; web and the
extension never render the badge, so they are untouched.

## Verification

- `mobile: npx tsc --noEmit` — clean.
