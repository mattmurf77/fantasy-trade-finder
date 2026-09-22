# Development and post-release operating workflow

The full [reviewed playbook](../plans/model-evaluation-framework/ways-of-working.md) governs. This is the operator entry point, not a weaker alternative approval process.

## Bootstrap and pre-release

1. Product/evaluation owners agree the charter and invariant tests. Data owner audits real evidence; immutable source manifests and exclusions are mandatory.
2. Run the incumbent-only offline baseline and blinded four-side annotation calibration. Expose Unknown instead of waiting for a perfect dashboard.
3. Product plus independent evaluation/analytics sign rubric anchors, noninferiority margins, critical segments, coverage, outcome horizons, attrition limits and power assumptions. No challenger tuning/locked-test access before this freeze.
4. Modeling writes a development brief and model card; logs all variants and ablations. Separate constructor, reference-price and presentation changes. Preserve a locked time/league/concept-separated holdout.
5. Independent reviewer runs paired frozen-input comparison, negative controls and release checks. Explicitly classify failed, insufficient evidence, qualified for limited experiment, or qualified for promotion. The current CLI never issues the latter automatically.
6. Only with release authorization and repository CI may operators shadow/canary/roll out. Record exact versions and read back actual state. An offline comparison is not permission to flip an arm.

## Post-release

Daily: source freshness, observation coverage, illegal assets, empty/errors, first-action latency and attribution integrity. Weekly: mature fixed-cohort outcomes and six-dimension distributions, both-manager slices, policy losses, repeats and follow-up attrition. Monthly: failure taxonomy, independent examples, source/rubric drift, new holdout and model-card update. These are operating responsibilities; no schedule or automation was created by this build.

No pooling of old/new configuration under one arm label. No view inferred from generation, refusal inferred from silence, or completion inferred from a send. Late counterpart action belongs to the original terms and cohort. Missing data cannot improve a denominator. Stop expansion for untrustworthy telemetry/assignment; contain confirmed integrity/privacy failures. Any promotion requires adequate predeclared evidence, not a single high proxy score.

## Roles

Product owns intent and trade-offs; modeling owns candidate design; data owns snapshots/joins/privacy; evaluation owns independent grades/holdouts; backend/mobile own instrumentation/reliability; release owner owns exact artifact and rollback. A model author cannot be its sole evaluator and release approver. Name people in the ratification record before operating this as a production promotion gate.

## Antipatterns

Avoid tuning to the final test, hiding failed experiments, replacing private preferences with consensus, rewarding a like by raising its purchase price, adding filler to game fit, blocking almost all candidates to inflate precision, assuming independent counterpart decisions, and changing model plus policy without isolating their effects. Negative experiments and honest Unknown cells are useful results.
