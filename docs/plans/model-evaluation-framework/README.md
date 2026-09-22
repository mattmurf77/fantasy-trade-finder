# Trade model evaluation framework

Reviewed planning package, September 21, 2026 (America/New_York), followed by an offline implementation and initial comparison September 22. No production model, data, configuration or deployment changed.

**Objective:** grade whether the engine finds personally desirable, realistically acceptable trades for **both** managers—not whether it reproduces its own scores or a competitor's calculator.

Read in this order:

1. [Build plan](plan.md): architecture boundaries, live baseline, data design, experiments, work packages and acceptance criteria.
2. [Scorecard contract](scorecard-spec.md): the six requested dimensions, independent outgoing/incoming grades for each manager, denominators and reporting rules.
3. [Development and evaluation playbook](ways-of-working.md): required documents, development/release/production operating procedures, best practices and antipatterns.
4. [Scope](scope.md) and [status](status.md).
5. [Adversarial review](adversarial-review.md): Astra Ultra findings, author responses, revisions and acceptance fixtures; both reviewers aligned after three rounds, with exact document hashes recorded.
6. [Implementation](implementation.md) and [validation](validation.md): offline foundation, tests, cross-review and remaining work.
7. [Three-model comparison](comparison-2026-09-22.md): measured strengths/gaps, including evidence-limited grades.
8. [Model-revision plan](model-revision-plan.md): conditional model selection, six-dimensional changes, ablations and graduation gates.

All metric definitions and proposed operating defaults must be versioned before teams use them for release decisions. The offline core is implemented; representative calibration, ratified thresholds, complete serving-path replay and production instrumentation remain unfinished. This is not evidence that any model has met its quality targets.

Key additions beyond the requested six dimensions: an independent evaluator separate from the live presentation gate; exposure- and time-aware outcome attribution; model-versus-filter blame isolation; leakage-resistant benchmarks; uncertainty/coverage reporting; repetition and latency guardrails; evaluator testing; and explicit ownership, graduation and rollback rules.

Adversarial revisions add fixed-cohort primary yield, immutable valid mutual-interest milestones, post-milestone reversal/confirmation promotion guardrails, unique cross-arm outcome attribution, honest probability target definitions, missing-data/user-authority rules, dimension-specific worked examples, and a baseline-first threshold-ratification sequence. Review alignment concerns the plan, not a completed evaluator or a model's release readiness.
