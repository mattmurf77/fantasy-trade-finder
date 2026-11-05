# Feature Scope — bounded roster assignment reuse

**Date:** 2026-11-05
**Entry point:** authorized investigation of the signed-in Find a Trade timeout.
**Builder:** launch privacy/backend subagent.
**Operator sign-off on waivers:** not needed; backend-only computation, no client surface change.

## 1. Analytics scope

Existing `find_trades_tapped`, `trade_first_card_failed`, `trades_generated`,
`api_request` and generation/publication logs cover the incident. No new data
collection. Live diagnostics returned only aggregate counts/timings and numeric
configuration; no identities, trade contents or raw logs were saved.

## 2. Schema & flag scope

No schema, flag, environment, model-config, provider or client contract changes.
No live knob change or deployment. The generator, offer limits, policy gates,
publication boundaries and order remain unchanged. Rollback is a code revert.

## 3. Evidence scope

The 04:17:04 UTC verified tap failed after 10,007 ms. Its generation produced
92 served cards in 64,812 ms; the owner arm generated 2,785 candidates in
29,662 ms. The first durable 30-card batch appeared at 64,567 ms. Generate
HTTP took 353 ms, sampled status reads 13–98 ms. A later page serve took
203.8 ms. This proves a long background/publication wait; it does not recover
the historical page-miss reason after that unique row was replaced. No
engine/config/experiment block was logged in the incident's five-minute window.

Production roster shadow evaluation was on; protection/mutual enforcement was
off. Prepared inventory had no ready inventory for the selected account and its
numeric enable knob was zero. Enabling preparation is not part of this fix.

A synthetic whole-worker profile with 432 offers and 12 slots reproduced
8,768 exact lineup solves, including repeated before-rosters across structural
and outlook checks. The bounded `Context` LRU shares only identical slot lists
and complete immutable `Asset` tuples. Values, multi-position eligibility,
startability and availability all participate. Recurring baselines remain hot;
at most 128 assignment entries are retained. Returned lists are independent.
There is no global or cross-context private cache.

Unprofiled whole-worker runs, same synthetic inputs/configuration, no concurrent
local suite: baseline 4.334 / 4.989 / 5.117 s; memo 2.659 / 2.977 / 3.097 s.
Medians: 4.989 → 2.977 s. Solver calls: 8,768 → 2,727. All six runs have
identical full roster-result JSON hashes and identical ordered offer-term
hashes. Retained state: 128 entries / 1,536 asset references / approximately
81,048 bytes of memo containers (not a total process-memory measurement).
Local wall times vary; no production latency target or 200 ms claim follows.

Unit regressions cover cached/uncached exact structural/outlook equivalence,
fresh/stale/missing point inputs, availability, scenarios/cuts, slot/value/flag
changes, returned-list isolation, no cross-context reuse, bounded eviction and
real-card solver reuse. Removing values from memo identity fails the changed-
value regression; source was restored. Existing roster/owner route and durable
publication suites remain the integrated gate. No mobile structural guard,
testID, capture or TestFlight checklist is needed for this pure backend change.

## 4. Docs scope

| Reference | Result |
|---|---|
| `docs/api-reference.md` | N/A: no route or wire-contract change. |
| `living-memory/LLD.md` | Context-local exact-input/bounded memo convention updated. |
| `docs/architecture.md` | Full-roster evaluation wiring updated. |
| `living-memory/HLD.md` | N/A: no new module, client, or major flow. |
| Data dictionary/config/cross-client invariants/glossary | N/A: no stored field, control, shared constant or term. |
| ADR/decisions | N/A: computational memo preserves the existing policy. |
| `living-memory/TEST_LEDGER.md` | Targeted tests, negative control and benchmark recorded. |

## 5. Ship gate declaration

Parent owns integration, independent review, exact-head GitHub CI and any
deployment. No express-lane waiver. This change reduces repeated post-generation
work; the incident's 29.7-second owner-generation phase and cold first-tap
readiness remain separate constraints.
