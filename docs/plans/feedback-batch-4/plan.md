# Feedback Batch 4 — "today's polish" (2026-06-19)

**Source:** in-app feedback #59, #61, #62, #63 (all `status=new`, `sev=polish`, v1.2.0).
**Out of scope:** #60 (Tiers default-bucketing bug) — explicitly deferred by operator.

## Base line
- Branch base: **`origin/trade-engine-v2`** (`a39e1e1`, v1.2.0 = the live TestFlight tester line).
- Confirmed this base already contains the draggable-flatlist Tiers rewrite (#84) + the
  multi-select `blockTier` fix (#85), so these features sit on the current Tiers code.
- Operator's uncommitted WIP in the root worktree is backend/docs/web only — **no mobile-screen
  files** — so these features are file-disjoint from it.

## Features
| ID | Screen | One-liner | Owner agent | PRD |
|----|--------|-----------|-------------|-----|
| FB4-63 | Tiers | Sticky floating tier header that updates while scrolling | Agent T | [prd-63](prd/prd-63-sticky-tier-header.md) |
| FB4-62 | Tiers | Direct tier-move buttons in multi-select (simpler than ↑/↓ one-rank) | Agent T | [prd-62](prd/prd-62-quick-tier-move.md) |
| FB4-61 | Tiers | Stats on tiles (consensus rank + 30d trend) + consensus/user toggle | Agent T | [prd-61](prd/prd-61-tile-stats.md) |
| FB4-59 | TradesHome | Error when only one scoring format is set, with copy options | Agent X | [prd-59](prd/prd-59-format-gate-error.md) |

## Agent ownership (disjoint files — no overlap)
- **Agent T (Tiers):** owns `mobile/src/screens/TiersScreen.tsx` + any new
  `mobile/src/components/Tier*.tsx`. Does FB4-61, 62, 63 together (same file → one agent).
  Worktree: `.claude/worktrees/fb4-tiers` (branch `feat/fb4-tiers-polish`).
- **Agent X (TradesHome):** owns the trades-home/format-gate path only.
  Worktree: `.claude/worktrees/fb4-trades` (branch `feat/fb4-trades-gate`).

## Pipeline
1. Agents implement in their worktrees; each runs `cd mobile && npx tsc --noEmit` clean.
2. Primary reviews both diffs; revises anything off.
3. Merge both feature branches → `feat/feedback-batch-4-polish`; regression (tsc + backend pytest).
4. PR `feat/feedback-batch-4-polish` → `trade-engine-v2`; merge.
5. EAS build from a clean `trade-engine-v2` checkout → TestFlight (operator's uncommitted WIP
   is NOT included — flagged to operator).

## Guardrails
- Simplicity first; surgical; mirror existing screen patterns (per `docs/coding-guidelines.md`).
- Tier colors/labels come from `mobile/src/utils/tierBands.ts` (cross-client invariant) — do not hardcode.
- Do NOT re-introduce gesture conflicts: the Tiers drag is `react-native-draggable-flatlist`
  with `PlayerCard` wrapped in `<View pointerEvents="none">`. Any new gesture must not capture
  touches from the list (that's what broke builds #11/#12).
