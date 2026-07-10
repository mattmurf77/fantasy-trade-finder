# Test Case Template

Copy this block per test case (or per tightly-related group). Keep every section —
write "n/a" rather than deleting, so reports stay scannable.

---

## TC-<AREA>-<NNN> — <short title>

| Field | Value |
|---|---|
| **Status** | Draft / Ready / PASS / FAIL / BLOCKED |
| **Date executed** | YYYY-MM-DD |
| **Layer** | engine / ranking / api / db / integration / config / security / perf / full-stack |
| **Component(s)** | e.g. `trade_service.py::_generate_for_pair_v2` fairness gate |
| **Requirement / doc ref** | e.g. docs/config-reference.md §fairness, HLD §trade-engine, FB-47 |
| **Engine path & flags** | e.g. `trade_engine.v2=true, v3=false, trade.marginal_value=on`; relevant `model_config` overrides |

### Objective
One or two sentences: what question does this test answer, and why it matters.

### Scope
- **In scope:** exactly what is exercised.
- **Out of scope:** adjacent behavior deliberately not covered (and where it IS covered, if known).

### Preconditions / Setup
- DB state or fixture (in-memory schema, seeded rows, copied DB snapshot — never the live DB for writes).
- Server state (local Flask? which port? warm or cold cache?).
- Config/flag pins beyond defaults.

### Inputs / Steps
1. Numbered, reproducible steps — exact payloads, function args, or curl commands.
2. ...

### Expected Result
Verifiable criteria — exact values, ranges, invariants, response shapes, status codes,
timing budgets. "Looks right" is not a criterion.

### Actual Result
What happened, with evidence (response bodies, query output, timings, log excerpts).
On FAIL: smallest reproduction + suspected cause with `file:line` if identified.

### Outcome
**PASS / FAIL / BLOCKED** — one line of justification.

### Findings requiring attention
| ID | Severity | Finding | Evidence (file:line / payload) | Suggested action |
|---|---|---|---|---|
| F-1 | P0/P1/P2/P3 | ... | ... | ... |

*(Severity: P0 prod-breaking/security/data-corruption · P1 wrong results or contract violation ·
P2 inconsistency/doc-drift/perf smell · P3 minor)*

### Observations & feedback (no change required)
Non-blocking thoughts worth sharing: design observations, future-proofing notes,
things that are fine today but won't scale, nice patterns worth replicating.

---
