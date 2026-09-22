# Feature Scope — persistent prepared trade inventory

**Date:** 2026-09-22. **Entry:** owner request to plan, build, deploy and prepare every existing user's linked teams. **Builder:** parent plus three Astra Ultra lanes. **Waivers:** none; non-applicable items explained below. [Plan](plan.md).

## 1. Analytics scope

Existing actual-view/disposition events retain their definitions. Preparation status has a dedicated operational ledger, not synthetic user activity. New operational telemetry must be explicitly specified/classified before emitting; no new client events in this scope. Preparation must not emit shown/viewed/like/proposal events, write last-active/login, or trigger notifications. Adoption records exact durable evidence before actionable publication. Document all new persisted operational fields in the data dictionary.

## 2. Schema and controls

Add versioned prepared-inventory and resumable sweep/target state using SQLAlchemy Core; necessary binding/preference persistence must be exact-scope and additive. Safe JSON codec only. Include participant-aware deletion. Register a default-dark rollout control with audited activation/rollback; preserve unrelated flags/knobs. No new paid infrastructure/env credentials or offer caps.

## 3. Evidence

Backend unit/integration tests for storage, membership, freshness, lease/restart/retry, capture/adoption durability, no activity/notifications, exact card metadata/order/count, source failures and interactive priority. Negative-control tests named in validation receipt. Full backend and all current hosted CI jobs required. Code-walk citations cover scheduler/process-local boundaries. Manual TestFlight checklist: open each supported linked league after prepared inventory, tap Find, verify actionable first tile and further cards; change rank/outlook/roster/fairness, verify stale results withheld; restart server, verify valid reuse; confirm no unsolicited inbox messages. Device timing remains unverified until performed. No mobile changes/testIDs/structural guard authored unless scope actually requires them; current mobile/web CI still runs. No simulator/Maestro.

## 4. Documentation

| Reference | Required update |
|---|---|
| API reference | Authenticated silent sweep/start/status and adoption compatibility |
| Data dictionary | Inventory, leases, scope/bindings, deletion, operational counters |
| Architecture | Capture→prepare→validate→durable publication flow |
| Config reference | Rollout and workload/retention controls, safe defaults |
| Runbook | Dry run, canary, full sweep, coverage, rollback and failures |
| Engineering conventions | No convention replacement; SQLAlchemy Core and additive migrations retained |
| Cross-client invariants | Existing payload/identity invariants unchanged; document if an additive field becomes necessary |
| Glossary | Define prepared inventory distinctly from shown offer |
| Architectural decision | SQL-backed safe JSON preparation/no fake exposure decision retained in plan; add ADR if implementation changes global architecture |

## 5. Ship gate

No express lane. All exact-head hosted CI jobs green before merge/push-main. Parent reviews all agent work and canary evidence. Ledger distinguishes executed, failed, unrun and manual checks. User has explicitly authorized deployment and initial preparation, not messages to users, paid resources or model changes. No TestFlight release expected for backend-compatible work.
