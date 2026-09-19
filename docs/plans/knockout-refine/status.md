# Status — knockout-refine

```project-status
{
  "status": "active",
  "updated": "2026-08-23",
  "summary": "knockout refine",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: **active** · 2026-08-23 **active** · 2026-08-23 — Loosen four trade-engine knockouts that the [2026-08-22 rules judgement](../../reviews/2026/2026-08-22-knockout-rules-judged.html) found were killing trades for the wrong reason, each behind its own `model_config` knob: R5's need gate gains an any-asset read plus a dual-need rescue (`need_gate_dual_rescue`), R1 measures overpay in `package_value_v2` — the currency the card actually shows — instead of raw sums (`overpay_adjusted`), R2 gains starter-depth relief so shedding RB4+RB5 passes while stripping RB1+RB2 still dies (`pos_net_starter_relief`), and the v3 package-shape literal becomes `v3_shape_max_delta`, unlocking the 3-for-1 / 1-for-3 subsets the enumeration already builds. Operator-aligned on items 1–4 (2026-08-23), including the clarification that positional protection is **R2's** job, not the shape rule's. [plan](plan.md) · [scope](scope.md). C1/C2/C3 ship **LIT**; C4 ships at its byte-identical default `1`. The prod move is a separate, deploy-free **consolidation bundle** applied after merge — `filler_min_frac` 0.15 (450 floor held) + `trade_elo_gap_max` 0 + `v3_shape_max_delta` 2, flipped together because the knockouts nest ([G-058](../../../living-memory/GOTCHAS.md)), each still independently revertible. Measured by `scripts/knockout_knob_sweep.py`, a read-only three-variant replay. Built on `claude/knockout-refine-0823`.. Prior row preserved at ../../reviews/2026/2026-09-06-project-status-migration/plans-index.md."
}
```
