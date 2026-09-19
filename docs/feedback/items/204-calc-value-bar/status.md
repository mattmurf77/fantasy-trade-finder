# #204 — Value bar missing from the In-league trade calculator (BUG)

**Operator:** "The value bar is missing from the trade calculator. This should
be presented on every page that involves trade offers."
**Status:** BUILT 2026-07-27 (branch `teardown-remediation`, isolated
worktree). Client-only — no backend change, no flag (the bar renders from
fields Mode B already returns; old servers unaffected).

## What shipped

- `mobile/src/components/InLeagueCalculator.tsx` (`LeagueVerdict`): the shared
  `TradeValueBar` (diverging pick-denominated bar) is now the In-league
  verdict's HEADLINE visual, exactly as in live mode's `ConsensusVerdictCard`,
  fed from the same Mode B `/api/trade/evaluate` response's consensus fields
  (`give_value` / `receive_value` / `favors` / `gap`). Renders whenever both
  sides carry valued assets (`gap` is non-null exactly then).

## Consolidated, not stacked (feedback #205 pressure)

- REMOVED: the consensus-basis headline sentence ("Consensus read — @X hasn't
  ranked, so this is market value only.") — the bar now IS the consensus
  verdict; provenance survives as a one-line dim note ("Market values only —
  @X hasn't ranked.").
- KEPT (distinct information, not duplication): the two-board divergence block
  (headline sentence + Your board / @X's board delta rows) — that's each
  owner's personal-board read, which the consensus bar cannot express; the
  single "Consensus X vs Y" totals row stays as the only place package totals
  appear (TradeSide lists per-asset values, never sums — mirrors live mode's
  secondary totals under the bar); starter-impact line + adjustments
  disclosure unchanged.
- One-sided trades keep the old "Add a player to each side for a verdict."
  line (the bar needs a two-sided gap).
- Demo mode untouched (`VerdictPanel`).

## Verification

- `cd mobile && npx tsc --noEmit` → clean.
- Backend suite untouched-green: `python3 -m pytest backend/tests -q` →
  1346 passed, 1 skipped (identical to branch baseline).
