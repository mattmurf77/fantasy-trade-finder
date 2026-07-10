# TC-ENG-004 — 3-team cycle clearing (find_three_team_cycles)

| Field | Value |
|---|---|
| **Status** | PASS (4/4 tests, in CI) |
| **Date executed** | 2026-06-11 |
| **Layer** | engine |
| **Component(s)** | `trade_optimizer.py::find_three_team_cycles` (work item 3.3) |
| **Requirement / doc ref** | architecture.md Tier 3 3-team cycles; `trade.three_team` flag |
| **Engine path & flags** | direct unit (marginal off → raw member values) |

### Objective
Cover genuinely-untested code: the kidney-exchange-style 3-team cycle clearer,
so it's known-good for when it gets wired into generation.

### Scope
- **In scope:** Pareto-improving A→B→C→A cycle detection (transfers, nets,
  min_net ≥ floor); no-benefit → empty; <3 ranked members → empty; lineup
  feasibility blocks a roster-breaking handoff.
- **Out of scope:** end-to-end generation (3-team is not wired — see F-1);
  marginal-value path of the cycle scorer.

### Actual Result
**4/4 PASS** ([backend/tests/test_three_team_cycles.py](../../backend/tests/test_three_team_cycles.py)).
The clearer finds the Pareto cycle with correct transfers (each cyclic asset
moves to the coveting team) and all-positive nets; returns empty when no mutual
benefit or fewer than 3 ranked members; and refuses a cycle whose handoff would
leave a team unable to field its lineup.

### Outcome
**PASS** — the 3-team cycle algorithm is correct and now has regression coverage.

### Findings requiring attention
| ID | Severity | Finding | Evidence | Suggested action |
|---|---|---|---|---|
| F-1 | **P3 (dead code)** | **`find_three_team_cycles` is implemented + exported but never called** — no reference in server.py or trade_service.py; the `trade.three_team` flag appears only in a comment. It is fully dark code (no client UI per recon). | grep: 0 callers | Either wire it behind `trade.three_team` in the generation path (it's correct and tested now) or mark it explicitly experimental/parked so it isn't mistaken for a live feature. |

### Observations & feedback (no change required)
- **The implementation is solid** — the kidney-exchange framing (directed
  beneficial-handoff edges, clear short cycles, feasibility-gated) is correct and
  cleanly factored; wiring it on is low-risk now that it has tests.
- Cap at 3-cycles + the `cycle_min_net`/`cycle_edge_min_gain` floors mean it
  won't spam marginal multi-team deals — sensible defaults for a feature that
  "essentially never executes" beyond 3 teams in real leagues.
- Worth a product decision: a tested, correct 3-team clearer is sitting unused.
  This QA pass de-risks turning it on.
