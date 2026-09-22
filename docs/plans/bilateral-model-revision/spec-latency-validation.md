# Supplemental independent full-worker latency check

Agent A: after completing implementation and cross-review, perform a read-only
performance validation; do not edit constructor, policy, server, grader or config
sources while paired evaluation is running. Use existing
`scripts/research_trade_pipeline.py` and prior isolated full-worker methodology.
Inspect all harness assumptions and label reconstructed/unknown provider, pick,
history and projection context. Use the same frozen original request and current
captured config on incumbent revision0 and candidate revision1 in separate fresh
processes, scratch SQLite, blocked sockets, no credentials or production access.

Compare actual worker start→first durable actionable batch and worker completion,
full served/impression counts, exact eligibility/order/proof identity invariants,
and execution errors. First30 is a delivery prefix, never a smaller search.
At least one paired smoke is required; if feasible run three alternating pairs
after coordinating CPU windows with Agent C. Do not claim product p95, Render or
phone three-second performance from localPython3.14/SQLite. Keep private rosters
and captured request outside Git. Aggregate evidence may be written only to
`docs/plans/bilateral-model-revision/latency-evidence.md`; new temporary harness
adaptations must use apply_patch and remain private. Report inability to reuse a
faithful harness rather than inventing a production-speed claim.

If a significant slowdown or correctness issue is found, report the measured
boundary and code cause to parent; do not silently optimize against the frozen
evaluation source set. Parent decides a follow-up coding round or release block.
