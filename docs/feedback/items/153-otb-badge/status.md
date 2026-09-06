# Status — 153-otb-badge

```project-status
{
  "status": "in-progress",
  "updated": "2026-07-25",
  "summary": "Status — #153 \"On the Block\" badge overlaps position tags → \"OTB\"",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: in-progress 2026-07-25 — worktree-agent-ae33eec5a00d24264. Prior row preserved at ../../../reviews/2026/2026-09-06-project-status-migration/feedback-index.md."
}
```

## Historical notes

The material below is retained evidence. Its former status wording does not override the record above.

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
