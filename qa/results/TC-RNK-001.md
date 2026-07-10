# TC-RNK-001 — Elo math golden fixtures (trade-engine input quality)

| Field | Value |
|---|---|
| **Status** | PASS (6/6 tests, in CI) |
| **Date executed** | 2026-06-11 |
| **Layer** | ranking |
| **Component(s)** | `ranking_service.py::_compute_elo`, `record_ranking`, `record_trade_signal`, override anchoring |
| **Requirement / doc ref** | cross-client-invariants.md K-factors (rank 32 / like 8 / pass 4 / accept-decline 20); docs/architecture.md 3-player decomposition |
| **Engine path & flags** | n/a (pure Elo math) |

### Objective
Pin the Elo update — the engine's primary input — to its documented spec with
hand-computed values, so any drift in the K-factors or expected-score formula is
caught before it silently corrupts trade valuations.

### Scope
- **In scope:** single pairwise update exactness; K-factor by decision type and
  its linearity; zero-sum conservation; 3-player decomposition + order
  preservation; override pinning; replay determinism.
- **Out of scope:** memoization/cross-client parity (test_elo_memoization.py);
  tier-band bucketing; seed derivation from DynastyProcess.

### Actual Result
**6/6 PASS** ([backend/tests/test_rnk_elo_golden.py](../../backend/tests/test_rnk_elo_golden.py)).
Single pairwise at 1500/1500 → 1516/1484 (K=32, exact). rank:like:pass gains =
16:4:2 (linear in K 32:8:4). Total Elo conserved across a 3-player ranking.
Decomposition produces exactly {(a,b),(a,c),(b,c)} with order preserved.
Overridden player pinned; partner still moves. Replay deterministic.

### Outcome
**PASS** — Elo arithmetic matches spec exactly; graduated into the pytest suite.

### Findings requiring attention
| ID | Severity | Finding | Evidence | Suggested action |
|---|---|---|---|---|
| — | — | No defects. | | |

### Observations & feedback (no change required)
- **Displayed Elo is rounded to 1 decimal** in `get_rankings`, and *that rounded
  value* is what gets published to `member_rankings` and fed into `elo_to_value`
  for trade math. So the whole valuation pipeline operates at 0.1-Elo precision
  (≈0.5 value units near the reference) — more than fine, but worth knowing when
  reconciling a displayed Elo against an internal computation.
- **Zero-sum conservation only holds without overrides** — once a player is
  tier-pinned, their swipe partner's gain/loss is no longer mirrored (the anchor
  absorbs nothing). Correct by design, but it means total Elo drifts as users
  pin tiers; not a conserved quantity in production.
- K-factor linearity makes the relative signal strengths legible: a "like" is
  exactly a quarter of a ranking swipe, a "pass" an eighth — matches the
  documented intent.
