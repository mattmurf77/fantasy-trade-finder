# #243 — TradeValueBar density (V1) — build notes

**Date:** 2026-08-03
**Design source:** `mockups/polish-lab-2026-08/tradevaluebar-density.html`, frame **B1** (operator-approved V1)
**Audit source:** `docs/feedback/items/243-scroll-audit/trades-surfaces.md` (top-10 items #4 and #6 + the winner-line step and padding trim)
**Files changed:** `mobile/src/components/TradeValueBar.tsx` (component), `mobile/src/components/CLAUDE.md` (row + testID registry), this doc.

## What changed

All four V1 items, in `TradeValueBar.tsx` only — no mounting file touched, so the change applies at every mount by design (deck TradeCards, FeaturedTradeWindow, ConsensusVerdictCard + In-league calculator verdicts, League "Works right now" example card):

1. **Winner line stepped `type.heading` → `type.title`** (22/26 display → 16/22 UI semi). It's a mid-card element, not a page title; the step also drops the heading variant's VoiceOver header trait, which was wrong for a card interior.
2. **Verdict paragraph collapsed by default** behind a one-line **"Why?"** disclosure. Per-instance `useState(false)` — collapsed on mount, chevron-down → chevron-up when open, full paragraph (both the even and the win/counteroffer variants) rendered exactly as before when expanded. Pattern matches `AdjustmentsDisclosure.tsx`: full-width space-between Pressable row, `type.label` dim text + 14px chevron `Icon`, `minHeight: 32` + `hitSlop: 6` (≥32pt target), `accessibilityRole="button"` with a state-describing label.
3. **Verdict-box padding** `padding: space.md` → `paddingVertical: space.sm` + `paddingHorizontal: space.md` (vertical 12→8pt per side; horizontal kept at md).
4. **Chalkline floor fix:** `scaleEnd` / `scaleTickLbl` `fontSize: 9` → `11` (type.label metrics; the only literal floor violation the audit found on the trades surfaces). Mono family/line-height unchanged; fixed `width: 30` / `44` label boxes still fit `−1st` / `−2nd` at 11px.

**New testID:** `valuebar.why` (the disclosure toggle). All existing testIDs preserved (the component itself had none; mount-side IDs untouched).

## Pt saved (per the mockup's pt math, 393pt width, verdict wrapping to 2 lines)

| State | Height | vs current (248pt) |
|---|---|---|
| Collapsed (default) | 192pt | **−56pt (−23%)** |
| Expanded ("Why?" tapped) | 236pt | −12pt (−5%) |

Single-pin mode mounts the bar twice, so the default-state saving there is ≈112pt.

## Cross-client note

No `docs/cross-client-invariants.md` change: the invariant governs the server payload shape (`favors`, `give_value`/`receive_value`, `gap`) — untouched. The verdict copy and the collapse are mobile presentation only; web renders its own fairness meter.

## Verification

- `cd mobile && npx tsc --noEmit` — passes clean (run in the worktree against the repo's node_modules).
- Behavior is state-local and presentational: no props/API changes, so every existing mount compiles and renders unchanged apart from the four visual deltas above.
- Not verified on-device in this pass (worktree build); the disclosure logic mirrors the shipped `AdjustmentsDisclosure` toggle line-for-line.
