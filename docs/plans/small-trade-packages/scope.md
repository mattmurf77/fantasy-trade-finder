# Feature Scope — bounded small-player-package presentation

**Date:** 2026-09-06

**Entry point:** owner-requested package-shape research and separately reviewed presentation change; [planner](plan.md), [PRD](prd.md).

**Builder:** parent-assigned backend owner after original-planner critique and root gate. Author writes only this scope, PRD and reconciliation.

**Operator sign-off on waivers:** not needed; none requested. No express lane.

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [x] **(b) Existing events cover it:** `trades_generated`, `deck_card_viewed`, and existing deck outcomes connect generated inventory, observed exposure and subsequent action. They do not turn served cards into viewed cards or establish causal acceptance improvement. Existing `deck_impressions.features_json` gains the frozen `presentation` object defined in PRD §4; existing `policy_version` gains the captured presentation suffix while arm attribution and valuation `policy_variant` remain distinct. No new event/property in the client taxonomy.
- [ ] **(c) WAIVED:** not applicable. Existing-column metadata is an explicit data-collection change, not a waiver.

Record original/final indices and player counts, never private board values or new identifiers. Retain pre-presentation original indices through #419's final pre-impression removal; remap surviving occurrence records and assign final indices from actual writer enumeration, equal to F1 `card_index`. Distinct duplicate-shaped objects and repeated same-object occurrences retain metadata without an impression-ID redesign. Later post-freeze filtering cannot rewrite recorded indices. Preserve actual draw propensity, original arm/group ranks and every-row batch semantics. Parent updates data-dictionary and serving-policy documentation before activation. No production evidence or event write occurs in this author pass.

## 2. Schema & flag scope

- Tables/columns/migrations: **none**. Additive nested JSON semantics in the existing `features_json` and a serving-version string suffix only.
- Feature flags/env vars: **none**. Existing live market/mutual policy, ghost, bakeoff and logging gates remain unchanged.
- One Float-valued `model_config` key: **`simple_player_presentment`**, default **0.0** in both `trade_service._DEFAULT_CFG` and database defaults. Exactly `1.0` enables v1; `0.0`, missing, invalid or unsupported values mean off. Six-position windows are versioned code, not another knob.
- Rollback: set this existing-admin-config key to 0; fresh generation must reject incompatible running/completed/pregen/replenishment cache entries. Old job IDs and already rendered decks retain captured order, subject to existing safety/disposition filtering. No remote re-sort or policy disablement.
- Activation is an explicit parent-owned release action after review/QA; default-off seeding must never overwrite a saved value. No fourth arm, quota, score or eligibility threshold.

## 3. Evidence scope

- **Structural guard:** no new mobile suite required because no mobile code, control or sorting changes. Backend AST/wiring guards supplement the executable worker tests; existing mobile structural suites still run at integration.
- **Unit tests, required/not run:** `backend/tests/test_small_trade_presentment.py`; narrow worker/cache/impression assertions in existing bakeoff/policy harnesses. T1–T8 in the PRD cover meaningful three-arm movement, no-op controls, all invariants, first publication, captured settings, every cache probe and frozen telemetry. T4/T6 hold the worker after presentation/publication, introduce a pass, then verify the final #419 cut and surviving occurrence/index alignment, including duplicate-shaped distinct objects and repeated same-object records. Generator goldens are not rewritten to bless the new serving order.
- **Code-walk, required after build:** exact final SHA/file:line trace from request/pregen/replenishment capture through reuse checks, kickoff, final policy survivors, one reorder, first evaluated publication, final `_project_trade_dispositions` removal, occurrence remapping, serialization and both impression writers. Include mid-job knob change, logging disabled and post-freeze poll filtering. The ≤5 movement and class-vector checks apply before authoritative removal/compaction; no stale parallel zip, second sort or later index rewrite.
- **Manual TestFlight, required/not run:** PRD §6 names organic generation, larger-package reachability, picks, explicit selections, Find More/pass suppression, Back and retained-deck order. No simulator, Maestro, mockups or captures under D-056.
- **Waivers:** none. No new mobile structural suite/testID is applicable, not a waived backend behavior test.
- **testIDs:** none added/renamed; parent still runs existing testID lint and TypeScript checks.

Every new behavioral test needs a preserved RED against the original missing behavior or a named meaningful sabotage, then GREEN. Tests use synthetic fixtures/isolated databases and no live user generation or provider writes.

## 4. Docs scope

Shared follow-through below is **required at integration, not completed by this author**; parent owns assignments and final status.

| Doc | Disposition | Scope |
|---|---|---|
| `docs/api-reference.md` | Required | Generated-deck ordering and mode-compatible cache semantics; no endpoint or JSON wire shape change. |
| `docs/config-reference.md` | Required | The single default-off knob, exact values, capture timing and rollback limits. |
| `docs/data-dictionary.md` | Required | Frozen nested presentation fields and serving-version suffix; distinguish served position from original arm/group rank. |
| `living-memory/LLD.md` | Required | Six absolute slots, class locks, publication ordering, captured-mode reuse checks and frozen provenance. |
| `docs/architecture.md` | Required | One post-policy/pre-publication helper and writer/cache flow. |
| `living-memory/HLD.md` | n/a | No new service/client/subsystem or major flow; targeted module wiring is covered by architecture/LLD. |
| `docs/cross-client-invariants.md` | n/a | No shared client enum/color/constant; clients do not gain a re-sort. Existing wire/identity invariants preserved. |
| `docs/glossary.md` | n/a | No new user-facing domain term. |
| ADR or `DECISIONS.md` | Required | Explicit narrow exception to fixed within-arm serving order; not permission to change generator goldens, group drafting or arm allocation. |
| Plan index, ledger, release note | Required, parent-owned | Review outcome, RED/GREEN evidence, deployment/activation/device facts and exposure-analysis limitations. |

## 5. Ship gates

Original planner approved author `07d98473` without baseline blockers. Root and planner accepted the narrowly documented #419 `cf8cc2cc` pre-freeze disposition/occurrence-alignment condition; root approved the complete revised `5171f13a` specification on 2026-09-06. Fresh-main verification at 15:09 UTC remains `4026ebc8`. `server.py` changes are sequenced after final #419 backend review/integration by the parent. Full backend CI, all mobile guards/typecheck and testID lint must pass on the reviewed release SHA. Parent records precise RED/GREEN/code-walk evidence and the manual checklist's actual outcome. Existing batch release authorization is conditional on review/QA; this build gate does not activate the knob or perform a release. No express waiver.
