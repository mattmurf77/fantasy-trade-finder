# Trade model activation and whole-team benefit

Date: 2026-09-04. Branch: `claude/fleeced-trade-engine-balance-c0c75d`.
User request: complete activation validation; implement original items 2 (outlook-specific whole-team benefit) and 3 (rank by the smaller manager benefit). The HTML mockup is excluded from product rollout.

## Decision

Keep market fairness and post-trade roster coverage as hard constraints. Measure utility over each complete team using explicit outlook before inferred outlook. Distinguish current production from dynasty value and expose uncertainty instead of inventing point projections. Rank eligible trades by the weaker manager benefit before aggregate benefit, preserving the market policy's Core/Conviction presentation quotas.

## Analytics scope

Existing deck impressions and policy rejection ledger capture final-package evaluation. Additive frozen utility diagnostics live within the existing roster evaluation JSON; no client event or taxonomy additions. Served and viewed remain distinct. No acceptance uplift is claimed from synthetic tests or unexposed offers.

## Schema and flag scope

Reuse additive migrations and the four trade flags already on this branch. Rollout configuration must remain separately reversible. Added `trade.mutual_benefit_v1`, false in the registry defaults, config and all three flag fixtures. It implies final market and roster enforcement and remains dark. No new model_config key or env name: thresholds are explicit pure-function inputs with documented defaults; collection uses the existing FTF_FLAGS operator override. Validate migrations on PostgreSQL; do not copy production identities into committed fixtures.

## Evidence scope

Subagents own focused pure-function tests for outlook utility and mutual benefit. Main validates integration, confidence provenance, unchanged flag-off behavior, malformed/unknown inputs, final-package gating, availability and coverage, telemetry completeness, exact-SHA CI and full backend suite with sources frozen. Run mobile static gates because they are repository merge requirements. Native UI has no changes; no simulator is used and no TestFlight proof is claimed. A live provider send is not part of automated validation because it would message another manager.

## Documentation scope

Update API contract, architecture, HLD/LLD, config reference, data dictionary and rollout evidence where behavior or stored diagnostics change. Record residual data limitations and the exact enabled cohort/flags. Existing mockup remains a standalone review artifact.

## Ship gate

The user authorizes execution and activation. Complete all locally executable and remote read-only validation, then deploy only a configuration supported by the evidence. Record pushed-SHA CI and deployed revision. Existing telemetry quality and latency gates still apply to broad enforcement. If live observations or a native controlled-send check cannot be completed here, state them precisely; do not call them passed or silently enable broad enforcement. Rollback flags and operational steps must be concrete and verified before rollout.

## Documentation and native evidence decision

No mobile structural guard or new testID is needed because no client code changes. The existing 90 structural suites, TypeScript and testID lint still run as merge gates. The prior controlled-send TestFlight checklist stays pending for enforcement/proposal-funnel graduation; collection-only rollout uses server-side recording/ownership tests and production readback, and claims no native runtime proof.

| Doc | Scope |
|---|---|
| docs/api-reference.md | Additive evaluation JSON and frozen diagnostics; no route added. |
| docs/architecture.md; living-memory/HLD.md; living-memory/LLD.md | New leaf modules and final-package ordering. |
| docs/data-dictionary.md | Existing features_json nested utility and readiness fields. |
| docs/config-reference.md | Dark mutual-benefit flag, implied gates and rollback. |
| docs/cross-client-invariants.md | No new client UI or public enum consumed; existing roster_evaluation remains additive. |
| docs/glossary.md | Normalized whole-team benefit and weaker-manager ranking. |
| living-memory/DECISIONS.md | Existing D-180/D-181 preserved; readiness decision recorded in this scope. |
| living-memory/TEST_LEDGER.md; HANDOFF.md | Executed checks and precise activation state. |

Express lane: no. All repository CI jobs remain required. No crossover allocation is changed during collection; generator arm and legacy serving policy attribution remain separate. No production acceptance claim or mockup rollout.
