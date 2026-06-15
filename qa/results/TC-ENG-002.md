# TC-ENG-002 — Fairness-gate golden fixtures (1-for-1 gate + package-discount watch item)

| Field | Value |
|---|---|
| **Status** | PASS (8/8 tests, stable ×3; full suite 178 passed) |
| **Date executed** | 2026-06-11 |
| **Layer** | engine |
| **Component(s)** | `trade_service.py::package_value_v2`, `_generate_for_pair_v2._fairness`, `_value_uncertainty`; `trade_optimizer.py::_fairness_v3`; surplus + ELO-gap + lineup-feasibility gates |
| **Requirement / doc ref** | "1-for-1 fairness-gate watch item" (memory: project_ftf_trade_engine_v2); package-discount / "Crown Asset" problem; FR8 fairness market-neutrality (docs/plans/competitor-top20/01) |
| **Engine path & flags** | v2 (`trade_engine.v2`) and v3 (`+trade_engine.v3`); `trade.outlook_blend` for FR8 case; `model_config` defaults, `package_adj_gamma` swept |

### Objective
Pin the fairness gate's documented-but-untested behaviors: the package-discount
math that prevents "quantity beats quality," the 1-for-1 gate's config-driven
threshold, fairness market-neutrality vs outlook, and v2↔v3 floor parity.

### Scope
- **In scope:** `package_value_v2` discount (exact + monotone in gamma);
  1-for-1 gate knife-edge (present at threshold F−ε, vetoed at F+ε);
  discount propagation to a card's `fairness_score`; outlook-independence of
  fairness (FR8); v2↔v3 reject-unfair + fair-score parity; threshold monotonicity.
- **Out of scope:** range-overlap rescue with confidence (covered by
  `test_trade_engine_v2.py::test_range_overlap_fairness`); composite ranking;
  three-team cycles.

### Inputs / Steps
Automated pytest: [backend/tests/test_fairness_gate_golden.py](../../backend/tests/test_fairness_gate_golden.py).
Eight tests, tiny deterministic fixtures, flags/cfg snapshot-restored per test.
Knife-edge and discount tests are self-calibrating (read the card's own
`fairness_score` as the oracle) to avoid brittle hand-predicted thresholds.

### Expected Result
Best asset contributes 100% of value regardless of gamma; lesser assets
discounted and strictly decreasing in gamma; a 1-for-1 with reported fairness F
surfaces below F and is vetoed above F; raising gamma lowers a multi-give
package's fairness; outlook never changes `fairness_score`; both engines reject
a clearly-unfair 1-for-1 and report identical fairness for a fair one;
card count is monotone non-increasing in threshold.

### Actual Result
**8/8 PASS**, stable across 3 runs; full backend suite 178 passed with the new
file added (no cross-test pollution). Evidence: test output + fixtures in the
file above.

### Outcome
**PASS** — the fairness gate behaves to spec: the package discount is real and
gamma-tunable, the 1-for-1 gate is correctly config-driven, fairness is
market-neutral, and the v2/v3 floors agree.

### Findings requiring attention
| ID | Severity | Finding | Evidence | Suggested action |
|---|---|---|---|---|
| F-1 | **P3 (latent / maintainability)** | `_fairness_v3` (trade_optimizer.py:99) is a hand-copied mirror of v2's `_fairness` with a standing `TODO refactor`. This test now guards score parity, but the duplication remains a drift risk for any future fairness change (two sites to edit). | trade_optimizer.py:103 comment; new parity test | Extract a shared `score_trade`/`_consensus_fairness` helper (already planned in docs/plans/competitor-top20/03 §"Extract score_trade") so v2 and v3 cannot diverge. |

### Observations & feedback (no change required)
- **v3 lineup feasibility is all-or-nothing per roster (sharp edge):** a roster
  that cannot field a full lineup (`_STARTER_NEED` = QB1/RB2/WR2/TE1) gets
  **zero** v3 cards — every trade is infeasible. This is correct, but means a
  thin/lopsided roster silently yields an empty v3 deck (v2 would still serve
  cards). Real Sleeper rosters always carry all positions, so it's unlikely in
  prod; worth a one-line note in the runbook for diagnosing "no trades" reports.
  (This shaped the test fixture — the gate must be exercised with a legal lineup
  or it masks the fairness behavior under test.)
- **The package discount is aggressive at default gamma=1.5:** even a 40-Elo
  consensus gap on a 1-for-1 drops fairness to ~0.33, because the lesser asset
  is discounted hardest. This is by design (anti-quantity), but it's why most
  surfaced 1-for-1s are near-equal-value — relevant context for the planned
  `fairness_threshold` tuning (memory watch item #4).
- **FR8 holds cleanly:** outlook blends user value (surpluses/composite) but the
  gate reads consensus seed only, so fairness is genuinely market-neutral.
- One transient `AttributeError` on `FLAGS.trade_outlook_infer` appeared during
  an interrupted mid-edit run but was not reproducible across 4 subsequent clean
  runs; the flag is validly defined in `FLAG_KEYS`. Noted, not filed.
