# Feature Scope — Full-roster trade evaluation

**Date:** 2026-09-04
**Entry point:** direct user request following competitor research; review and revise the balance agent on `claude/fleeced-trade-engine-balance-c0c75d`.
**Builder:** Codex
**Operator sign-off on waivers:** not needed; no waivers.

## 1. Analytics scope

Existing deck impressions/outcomes and policy shadow records cover this work. Store a frozen `roster_evaluation` inside the existing impression `features_json`, including both teams, settings provenance, blockers, replacements, depth and outlook utility. Keep rejected-candidate counts/reasons in job diagnostics. No new client events. Unknown data is not a successful safety check. No acceptance probability is claimed.

## 2. Schema and flag scope

No new schema, environment variables or model_config keys. Add `trade.roster_evaluation` (shadow evidence) and `trade.roster_protection` (enforce the supported checks and rank within policy lanes); both default false. Existing market-policy switches remain false. Rollback: disable protection independently of shadow. Graduate only after offline replay, shadow coverage and outcome review; do not enable production in this task.

## 3. Evidence scope

Backend unit and worker integration tests cover exact slot assignment, both teams, FLEX/Superflex, unusable bodies, existing deficits, depth, unbalanced packages/cuts, uncertain inputs, outlook, streaming bypass, policy exceptions and deck quotas. The backend tests also provide structural guards for the final publication seam. Mobile code and testIDs do not change; browser HTML is a review artifact. Code-walk and TestFlight checklist accompany the implementation; no simulator or Maestro usage (D-056).

## 4. Docs scope

Update API reference (optional card/job evidence), architecture and HLD (leaf evaluator and final gate), LLD (coverage semantics), config reference (switches), data dictionary (frozen feature evidence), glossary (usable depth), cross-client invariants (unknown is not safe), decisions (estimated settings never enforce), and test ledger. Add the HTML mockup alongside its dated design reference; it elaborates existing rationale/lineup impact rather than duplicating it.

## 5. Ship gate declaration

Run focused tests, backend regression suite, mobile typecheck/structural checks and testID lint where available. Record exact outcomes; pushed-SHA CI and operator TestFlight verification remain release gates, not claims from local execution. No deployment or production migration in this task.

## Implementation boundary

Use consensus dynasty values and the existing starter-quality predicate as value proxies, never projected fantasy points. Exact assignment optimizes occupied slots then value. Protect each constrained position group and preserve up to one usable backup at dedicated positions. Existing weaknesses may improve without unrelated weaknesses vetoing the trade, but no group may worsen. Apply the same structural protection to rebuilders. Outlook changes soft utility only. Capacity overflow requires explicit cuts and re-evaluation; never assume a waiver replacement. Current server integration observes Sleeper slots/reserve/taxi; non-Sleeper templates and absent/freshness-limited data remain uncertain and cannot pass enforcement. Bye-week scenarios are supported by the leaf evaluator but remain unknown without a schedule feed. Multi-team trade evaluation is deferred and must not be labelled checked.
