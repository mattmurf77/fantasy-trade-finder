# FB-226 — OTB tag overlaps the position tag on the user's own (give) side

- **Type:** bug · **Status:** fixed 2026-08-01 (branch
  `teardown-remediation` worktree)
- **Surface:** trade cards (`TradeCard` → compact `PlayerCard` rows) —
  worst on the give ("YOU SEND") column, reproducible on receive too.

## Root cause (reproduced by layout math)

The compact `PlayerCard`'s `rightSlot` was **absolutely positioned** at
the card's top-right, floating OVER the header badge row instead of
reserving space. A trade card's split column is ~140pt (screen ≈390pt −
paddings − divider), leaving ~126pt of row content. The give side stuffed
the slot with a horizontal row of the OTB badge (+ optionally UNTOUCHABLE)
PLUS up to three 28pt icon buttons (lock/swap/remove) — ~130pt of overlay
that reached across the whole column and landed on the position tag. #153
had only shortened the label ("ON THE BLOCK" → "OTB"), which fixed the
lighter receive side but not the button-heavy give side; text scaling
(a11y) widened the badges and re-broke it sooner.

## Fix — reflow instead of overlay (both columns, same treatment)

1. **`PlayerCard`** (classic/compact branch): `rightSlot` now participates
   in layout — content column (`flex:1, minWidth:0`) beside the slot —
   instead of `position:absolute`. Nothing can be covered; the name
   ellipsizes honestly. New optional `badgeSlot` prop renders extra
   informational badges INSIDE the header badge row, which has `flexWrap`
   — badges wrap to a second line at large text sizes rather than
   colliding. (Only `TradeCard` uses the classic branch's `rightSlot` —
   Tiers/FreeAgents rows are `dense`, which was already in-flow —
   so no other surface changes.)
2. **`TradeCard`** (give AND receive columns, identical treatment):
   - OTB + UNTOUCHABLE badges moved out of the overlay into
     `badgeSlot` → they sit next to the position tag and wrap with it.
   - The interactive controls (lock/swap/remove) stay in `rightSlot` but
     now stack **vertically** (`rightSlotStack`), so the slot is one
     button (28pt) wide and the column keeps ~90pt for name/badges even
     with all three controls present.

## What changed visually

- Give side: OTB (and UNTOUCHABLE) render in the top badge row right
  after the position tag; the swap/lock/✕ buttons form a single vertical
  stack on the row's right edge. No overlap at any text size — badges
  wrap the header row taller instead.
- Receive side: same — OTB in the badge row, swap/✕ stacked at right.
- Rows with several controls get slightly taller (stack height) instead
  of wider-than-the-column; rows without controls are visually unchanged
  apart from OTB's new in-row position.
- A11y: `rowA11y` labels ("on the block", "untouchable") are unchanged;
  at accessibility text sizes the wrapping header row grows the card
  vertically — nothing truncates or collides.

## Files

- `mobile/src/components/PlayerCard.tsx`
- `mobile/src/components/TradeCard.tsx`
- `mobile/src/components/CLAUDE.md` (component notes)

## Verification

`cd mobile && npx tsc --noEmit` clean. Layout reasoning above (392pt and
narrower + a11y scaling); no new testIDs (no new interactive elements).
