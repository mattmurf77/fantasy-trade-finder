# Scope — model evaluation framework

**Date:** 2026-09-22. **Entry:** owner approved implementation, comparison of the three newest constructors, then an evidence-grounded revision plan. **Waivers:** none. This supersedes the planning-only scope; reviewed plan/spec/playbook remain unchanged.

## Analytics

Consume existing `deck_impressions`, `deck_outcomes`, `trade_pass_reasons`, `trade_matches`, `trade_proposals`, `bakeoff_runs` and frozen diagnostics offline. No emitters, production writes or synthetic production events. Distinguish reviewed synthetic fixtures, frozen research requests and real events. Generated offers are not views; sends are not completions; absent expiry, counterparty boards, projections and experiment cohorts remain unknown. Audit available fields and missingness before comparison. New runtime instrumentation remains a later reviewed taxonomy/schema change.

## Schema, flags and configuration

No DB migrations, routes, flags or live model settings. Add versioned offline JSON contracts, read-only snapshot adapters, pure evaluators and local reports. No evaluator import into the app runtime. New output directories are local/private; never commit raw snapshots or ranks. Operator tooling rollback is not invoking it. No arm is re-enabled; no paid infrastructure or dependency service.

## Evidence

Add focused unit tests for dimensions, outcomes, evidence, runner/replay; verify mirror invariance, missingness, chronology/denominator attacks, deterministic hashes and read-only safety. Independently review agent code and negative controls; run backend regression and record interpreter/hosted-CI limitations. Replay retained owner-v2-bilateral, owner-v1 and fit on frozen common contexts with explicit policy stages, source/config dates and native search limits. Actual acceptance and independently annotated quality remain Unknown when unsupported. No UI/TestFlight/device-latency changes or claims; no simulator/Maestro work. No promotion pass from unratified thresholds.

## Canonical documentation

Create canonical `docs/model-evaluation/` contracts, metrics, registry, workflows and templates. Update architecture/runbook for the independent operator-only pipeline and safe invocation. Existing API/schema/config/cross-client contracts remain unchanged; source audit cites them. No new runtime architecture/service warrants an ADR; reviewed separation remains the decision. Update initiative status and TEST_LEDGER with exact checks/results. HLD/LLD compatibility stubs are not targets.

## Ship gate

Build/evaluate locally, then write the revision plan. No production model/presentation changes, merge/push/deployment or TestFlight release under this request. Future release requires exact-head CI, independent validation and applicable authorization. Preserve unrelated canonical edits; implementation is in an isolated fresh-main worktree.
