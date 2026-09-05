# Scope — scoring and trade execution context

**Date:** 2026-09-04
**Entry point:** direct ask; first local milestone under a hard $200/month operating budget
**Builder:** Astra implementation agent
**Operator sign-off on waivers:** not needed; backend-only applicability reasons below

## 1. Analytics scope

Existing events cover it: `trades_generated`, trade impressions and deck signal impressions continue at their existing emitters with captured user/league identity. No new collection or events.

## 2. Schema & flag scope

No tables, columns, flags, environment variables, model settings, infrastructure, paid resources or deployment changes. No quotas, cooldowns, pregen removal, search cuts or job timing changes.

## 3. Test scope

Backend pytest concurrency/regression coverage: request format isolation and write-through behavior; delayed job start after session reinit/format switch; explicit kickoff format for pregen/replenishment; job-owned league mutations; existing card publication and suppression; existing trade pipeline regression suites. Tests use scratch SQLite and network-blocked imports, Python 3.12.

Mobile structural/type checks and manual TestFlight: n/a, no mobile code or contract/visual change. No testID/capture delta. Maestro and simulator are retired by current root CLAUDE.md (D-056); stale template simulator requirements do not apply.

## 4. Docs scope

| Doc | Action / reason |
|---|---|
| docs/api-reference.md | Clarify unchanged per-call scoring override contract |
| living-memory/LLD.md | Record request-view and kickoff capture convention |
| docs/architecture.md | Document local execution seam and remaining shared state |
| living-memory/HLD.md | n/a: no new module/service, durable worker or deployment topology |
| docs/cross-client-invariants.md | n/a: no client constants or enums changed |
| docs/glossary.md | n/a: no new product/domain term |
| ADR / DECISIONS.md | Choice and limits recorded in scoped implementation record; no deployment architecture decision |

## 5. Ship gate

Local implementation and review only; no push, merge or deployment authorized. Run relevant backend checks and log exact evidence in TEST_LEDGER plus scoped implementation record. Full pre-ship CI remains required before any later shipment.

## 6. Acceptance and boundaries

Overlapping requests and accepted jobs retain their intended user, league and scoring-format service. Ordinary session mutations persist; generated cards remain available to existing pending/swipe flows. Pregen, replenishment, generation options, API shape and algorithms remain intact. This is a local execution-context prerequisite: durable snapshots/jobs, cross-process correctness, general ranking-write atomicity and production scalability are deferred.
