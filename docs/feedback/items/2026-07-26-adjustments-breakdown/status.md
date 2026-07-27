# Itemized value adjustments on the calculator verdict — status

**Source:** DynastyDealer teardown 2026-07-26 (polish candidate #1 —
"Trade Adjustments Breakdown": collapsible panel itemizing each value
adjustment per team with plain-language rationale, e.g. "Stud Bonus +668").
**Operator:** "Visible trade adjustments let's do assuming it's simple."
**Status:** DONE (backend + mobile), 2026-07-26.

## What shipped

- `POST /api/trade/evaluate` additionally returns, when at least one
  adjustment moved a side's value:
  - `adjustments: {give: [{key, label, amount, why}], receive: [...]}`
  - `naive_totals: {give, receive}` (the "sum of parts" per side)

  Invariant: `naive_totals[side] + Σ amounts == give_value/receive_value`
  (0.1 rounding). Amounts are **derived** — `_evaluate_adjustments`
  (backend/server.py) re-calls `package_value_v2` with and without `n_other`
  to attribute the depth discount and the crown premium separately. No
  valuation math was changed or duplicated; **displayed totals are
  byte-identical to before** (pinned by
  `test_adjustments_do_not_change_displayed_totals`).
- Mobile: `AdjustmentsDisclosure` — a collapsed-by-default "Value
  adjustments" row (chevron toggle) rendering per-side labeled rows with
  signed green/red amounts and a dim why sentence, plus a
  "Sum of parts N → M" line. Mounted under the verdict in
  `ConsensusVerdictCard` (open calculator) and in the In-league verdict card
  (`InLeagueCalculator`), below the Consensus row and clear of `EvenerRows`.
  Renders nothing when the server sent no adjustments. testIDs:
  `calc.adjustments.toggle`, `calc.adjustments.row.<side>-<key>`
  (side-qualified — the same key can appear on both sides).
- No feature flag: additive response field + a disclosure that renders only
  with data; no existing displayed number changes.

## Audit — what the evaluate path ACTUALLY applies

The only value math in `/api/trade/evaluate` is
`trade_optimizer._consensus_packages` → `trade_service.package_value_v2`
(and `_fairness_v3`, which re-runs the same package math for the gate).
Mode B repeats `_consensus_packages` per owner board — same function, so
the same two adjustments apply to board-priced totals.

| Candidate adjustment | Applied in evaluate? | Itemized? | Notes |
|---|---|---|---|
| Package depth weighting (`package_adj_gamma`, 0.15 contribution floor) | YES — every `package_value_v2` call; any asset below the trade-wide `v_max` contributes below face value (bites even 1-for-1 on the weaker side) | YES — `package_depth` (negative) | Mode A and Mode B (consensus itemization; board totals share the math, not itemized — see below) |
| Crown/consolidation premium (flag `trade.crown_asset` — ON; `crown_rate`/`crown_share_floor`/`crown_elite_value`) | YES — inside `package_value_v2` when the side has FEWER assets than the other and top-asset share > floor | YES — `consolidation` (positive) | Exactly 0 on equal-count trades (cross-side count guard) |
| TEP TE uplift (`tep_te_uplift`) | NO — baked into the `sf_tep` universal-pool seed values at pool build time (`data_loader`, #148) | SKIPPED | Already inside the per-player values (and `naive_totals`); not an evaluate-time adjustment, so itemizing it would require refactoring the seed pipeline for attribution |
| Waiver-slot cost (`waiver_slot_cost`) | NO — generation only (`_generate_for_pair_v2`, optimizer §3) | n/a | Evaluate never applies it, even on unequal-count trades |
| Marginal (over-replacement) valuation (flag `trade.marginal_value`) | NO — generation only | n/a | Evaluate prices raw consensus/board values |
| QB tax / star tax / roster-spot / clogger (`trade_math.*` flags) | NO — composite-score multipliers in generation scoring | n/a | Their `human_explanations` copy voice was reused for the `why` sentences |
| Fit premium 1-for-1, tier multipliers, outlook blend | NO — generation only | n/a | |
| Value uncertainty (`range_base`) | Affects the fairness GATE only, never a displayed value | n/a | Not a value adjustment |

**Mode A vs Mode B:** the itemization decomposes the CONSENSUS totals
(`give_value`/`receive_value`) — the numbers both verdict cards display
(Mode B shows them as its "Consensus" row). Mode B's board-priced totals
(`your_*`/`their_*`) go through the same two adjustments but are not
itemized (would double the payload for numbers shown only as deltas);
`test_adjustments_mode_b_match_consensus_itemization` pins that Mode B
carries the same consensus itemization as Mode A.

## Tests

`backend/tests/test_trade_evaluate.py` (new section):

- `test_adjustments_1for1_depth_on_weaker_side_only`
- `test_adjustments_2for1_depth_and_consolidation`
- `test_adjustments_equal_counts_never_show_consolidation`
- `test_adjustments_absent_when_none_apply`
- `test_adjustments_do_not_change_displayed_totals`
- `test_adjustments_mode_b_match_consensus_itemization`

(No TEP fixture test — TEP is not an evaluate-path adjustment; see audit.)
