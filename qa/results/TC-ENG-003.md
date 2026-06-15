# TC-ENG-003 — Engine gate config-responsiveness (admin tuning surface)

| Field | Value |
|---|---|
| **Status** | PASS (4/4 tests, in CI) |
| **Date executed** | 2026-06-11 |
| **Layer** | engine |
| **Component(s)** | v2 `_consider` gates: `min_side_surplus`, `trade_elo_gap_max`, `waiver_slot_cost`, `tier_mult_*` |
| **Requirement / doc ref** | config-reference.md model_config; PUT /api/admin/config tuning surface |
| **Engine path & flags** | `trade_engine.v2`; `model_config` swept |

### Objective
Prove the operator's live-tuning knobs move the gates **predictably and
monotonically** — so tuning via `/api/admin/config` is deterministic, not a
guess. Complements test_trade_engine_v2 (gates exist) by testing they *respond*.

### Scope
- **In scope:** `min_side_surplus` monotonicity (↑ → fewer cards);
  `trade_elo_gap_max` knife-edge (gap-200 trade passes under cap 250, fails
  under 150); `waiver_slot_cost` erodes the extra-player side (2-for-1 dies as
  cost ↑); `tier_mult_elite` scales an elite trade's composite.
- **Out of scope:** marginal_value valuation (test_trade_tier2.py); outlook blend
  (TC-ENG-002 FR8); fairness (TC-ENG-002).

### Actual Result
**4/4 PASS** ([backend/tests/test_engine_gates_config.py](../../backend/tests/test_engine_gates_config.py)).
Surplus floor monotone (cards strictly drop as floor rises across 50→900).
Elo-gap cap is a clean knife-edge. Waiver cost kills the uneven 2-for-1 at high
cost while the math stays valid. Raising `tier_mult_elite` 1.0→2.0 raises the
elite trade's composite.

### Outcome
**PASS** — every tested knob is monotone and predictable; the admin tuning
surface is safe to operate.

### Findings requiring attention
| ID | Severity | Finding | Evidence | Suggested action |
|---|---|---|---|---|
| — | — | No defects. | | |

### Observations & feedback (no change required)
- **The legacy parity fixture is legacy-only**: the broad-divergence 7v7 from
  test_trade_engine_v2 yields 4 cards under the legacy path but **0 under v2** —
  v2 correctly rejects those one-sided-from-the-user trades that legacy's
  mismatch scoring surfaced. A concrete reminder that legacy and v2 are different
  products (reinforces TC-ENG-001's "kill-switch is a real downgrade" note); v2
  needs genuine two-sided mutual gain.
- **Building v2 fixtures requires both-sides divergence + equal seeds + an
  Elo-gap within 250** — the gates are interlocked, so a fixture targeting one
  gate must satisfy the others. Documented in the test for future authors.
- Tuning levers compose cleanly: surplus floors gate *which* trades survive,
  tier multipliers reorder *survivors* — operators can think about them
  independently.
