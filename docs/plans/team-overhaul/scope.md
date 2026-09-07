# Feature Scope — team overhaul roadmap

**Date:** 2026-09-06  
**Entry point:** direct owner request; approved core mockups and requested engineering handoff  
**Builder:** Codex planning task; implementation owners to be assigned  
**Operator sign-off on waivers:** not needed; this change adds documentation/prototypes, with no runtime gates waived for future implementation.

## 1. Analytics scope

**(a) New events specced as proposals, not registered/emitted.** Engineering must reconcile names and privacy/intent classification against the existing taxonomy before adding emitters. Include only opaque plan/league context IDs, counts, enums and outcome codes; omit credentials, audio and freeform notes.

| Proposed event | Properties | Trigger | Emitter |
|---|---|---|---|
| `overhaul_started` | entry, outlook (when known) | User starts a new draft | Client, once per explicit action |
| `overhaul_generation_completed` | candidate_count, compatible_roadmap_count, shortfall_reason | Generation completes | Backend, once per generation |
| `overhaul_roadmap_selected` | roadmap_id, package_count | User selects a roadmap | Client |
| `overhaul_batch_requested` | batch_id, package_count, offer_count, tied_package_count | User confirms the previewed batch | Client or server, one canonical emitter |
| `overhaul_batch_reconciled` | batch_id, sent_count, failed_count, unknown_count | Submission outcomes reconcile | Backend/integration owner |
| `overhaul_fallback_requested` | package_id, priority, offer_count | User explicitly sends the next tier | Client or server, one canonical emitter |

Do not count submission as acceptance or generation as intent. Register final names in `backend/analytics_taxonomy.py`, classify non-intent events in `analytics_queries.NON_INTENT_EVENTS`, and document storage when implemented.

## 2. Schema & flag scope

- This handoff changes no live tables, routes, flags, credentials, environment or model configuration.
- Proposed persistence: draft/settings, eligible assets, generations/likes, immutable roadmap versions and packages, ordered alternatives, send batches/attempts and provider status history. See [engineering spec](ENGINEERING-SPEC.md); final tables/migrations must be reviewed and added to the data dictionary during build.
- Proposed shared release gate: entry/generation disabled until validated; choose/register its exact name in `config/features.json`, backend flag registry and config reference during implementation. Preserve resume/status access for live sent work when creation is disabled.
- No new environment variables or model knobs are specified. Reuse existing authenticated integration/configuration boundaries.

## 3. Evidence scope

- Structural guards planned for final entry/root-stack routing (Acquire placement is proposed), one-package priority flow, test IDs and isolation from regular finder settings.
- Backend tests planned for selected-pool enforcement, pick identity, compatible-set construction, version changes, reservations, idempotent attempts and partial outcomes.
- Code-walk proof: inspected reuse surfaces and baseline qualifications in [engineering spec](ENGINEERING-SPEC.md).
- Manual physical-device/TestFlight checklist: [QA.md](QA.md), unrun until a real build exists. Prototype screenshots do not satisfy it.
- Proposed test-ID families: `overhaul-entry`, `overhaul-resume`, `overhaul-outlook-*`, `overhaul-asset-*`, `overhaul-continue`, `overhaul-priority-*`, `overhaul-send-all`, `overhaul-send-next`. Final dynamic naming must follow the repository linter.
- No backend test run is required for this documentation-only handoff; future implementation gates are not waived.

## 4. Docs scope

| Canonical reference | This handoff | Required during implementation |
|---|---|---|
| API reference | n/a: proposed contracts only | Final routes, errors and idempotency behavior |
| Data dictionary | n/a: no schema changes | Tables, lifecycle, analytics storage |
| Architecture / engineering notes | n/a: no module wiring changes | Generation, persistence and integration ownership |
| Cross-client invariants | n/a: proposed vocabulary local to initiative | Final enums, identifiers and state contracts |
| Glossary | n/a: new feature unbuilt | Roadmap vs package vs offer tier |
| ADR / decisions | Owner decisions preserved in initiative product spec | Durable non-obvious implementation choices |
| Product/design/components | n/a: prototype and planned behavior only | Shipped entry/flow, approved new components and copy |
| Config / integrations | n/a: no runtime config/provider changes | Launch gate, supported capabilities and verified call shapes |

## 5. Ship gate declaration

No release is requested or claimed. Implementation must pass the current CI jobs, appropriate behavioral tests and the physical-device checklist, then record evidence in the initiative and TEST_LEDGER. Follow repository merge/deploy/TestFlight gates and preserve platform-specific limitations. No express lane was requested.
