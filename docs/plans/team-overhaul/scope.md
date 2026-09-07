# Feature Scope — Team overhaul (v1 build)

**Date:** 2026-09-07 (supersedes the 2026-09-06 documentation-only scope)
**Entry point:** direct owner request — "Team overhaul is ready for engineering scoping … spin up subagents to build it"; NEXT item "Build Team overhaul"
**Builder:** Claude scoping session + three parallel build agents (backend, mobile A, mobile B) on `claude/team-overhaul-scoping-ea1c72`
**Operator sign-off on waivers:** not needed (no waivers)

Binding design: [BUILD-CONTRACT.md](BUILD-CONTRACT.md). Product rules: [PRODUCT-SPEC.md](PRODUCT-SPEC.md). Decision record: [D-188](../../../living-memory/DECISIONS.md).

---

## 1. Analytics scope

- [x] **(a) New events specced** (registered in `backend/analytics_taxonomy.py` in the same change as the emitters; properties are ids, counts and enums only):

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `overhaul_started` | league_id, outlook?, entry | User taps Start overhaul on the Acquire card | mobile |
  | `overhaul_roadmap_selected` | overhaul_id, roadmap_id, package_count | User picks a roadmap to set priorities | mobile |
  | `overhaul_batch_requested` | overhaul_id, batch_id?, package_count, offer_count, tied_package_count | User confirms Send all offers | mobile |
  | `overhaul_fallback_requested` | overhaul_id, package_id, tier, offer_count | User explicitly sends a package's next tier | mobile |
  | `overhaul_generation_completed` | overhaul_id, candidate_count, compatible_roadmap_count, shortfall_reason | `POST /api/overhauls/{id}/generate` finishes | backend (server-fired) |
  | `overhaul_batch_reconciled` | overhaul_id, batch_id, sent_count, failed_count, unknown_count | `POST /api/overhauls/{id}/send` finishes dispatch | backend (server-fired) |

  → follow-through: the two server events are classified in `analytics_queries.NON_INTENT_EVENTS`; storage is the existing `events` path (no new table).

## 2. Schema & flag scope

- New tables: `overhauls`, `overhaul_offers`, `overhaul_roadmaps`, `overhaul_attempts`, `overhaul_reservations` → `docs/data-dictionary.md` (one section each). Created by `metadata.create_all`; no ALTER migration rows needed.
- New feature flag: `overhaul.enabled` → `config/features.json` (**false**), `backend/feature_flags.py` `FLAG_KEYS` + mirror fixtures, `docs/config-reference.md`. Gates the entry card and the create/generate/assemble/send routes only; reads, decisions, priorities, prepare-send, refresh and status assertions stay reachable so live sends are never stranded by a rollback. **Graduation criterion:** the operator runs the [QA.md](QA.md) physical-device checklist on a TestFlight build and confirms D1 (Sleeper-only sends) and D9 (Acquire placement).
- New env vars / `model_config` keys: **none**. Search bounds are module constants in `backend/overhaul_service.py`. Deploy-free rollback lever: flip `overhaul.enabled` false and `POST /api/feature-flags/reload`.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-team-overhaul.js` (`npm run test:team-overhaul`) — pins: all eight overhaul screens registered once, in the Trades stack, none in RootNav; no `FeedbackFAB` import in any overhaul screen; entry card rendered in `TradesScreen` after `TeamReviewEntryCard` gated on `useFlag('overhaul.enabled')`; no overhaul file references league-preference, tiers-save or swipe-learning helpers; priorities screen uses `react-native-draggable-flatlist` with `accessibilityActions`; summary renders races keyed by `package_id`; every `AttemptState` has a label used by the plan screen; every testID family present.
- [x] **Unit tests:** `backend/tests/test_overhaul_service.py` (pool/E01–E15 fixtures, D4), `test_overhaul_store.py` (reservations, CAS), `test_overhaul_api.py` (flag gating, ownership scoping, idempotency, prepare/send/refresh/status with fake generator and fake Sleeper propose), plus the existing `/api/trades/propose` tests proving the extraction is behavior-preserving.
- [x] **Code-walk proof:** [BUILD-CONTRACT §6–§7](BUILD-CONTRACT.md) name the seams; the build report in [status.md](status.md) cites the final file:line trace for pool enforcement, reservation claim and attempt state transitions.
- [x] **Manual TestFlight checklist:** [QA.md](QA.md) "Manual physical-device checklist" (10 items) — **unrun** until a build exists; the only runtime evidence mobile gets.
- `testID`s added: families `overhaul.entry-card`, `overhaul.entry-start`, `overhaul.entry-resume`, `overhaul.outlook.<key>`, `overhaul.asset.<id>`, `overhaul.continue`, `overhaul.review.like|pass|build`, `overhaul.roadmap.<id>`, `overhaul.priority.list`, `overhaul.priority.move.<id>`, `overhaul.summary.send-all|copy`, `overhaul.plan.refresh|send-next` (static prefixes; passes `mobile/scripts/testid-lint.sh`).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | new section "Team overhaul (flag `overhaul.enabled`)" — 13 routes, error codes, idempotency, prepare-token lifetime |
| `living-memory/LLD.md` | n/a | no schema/route *convention* shifted; the feature follows the `win_now_api.install` route-module convention and existing JSON-as-Text tables |
| `docs/architecture.md` | updated | "Team overhaul" wiring: service / store / api modules, generation reuse of the owner constructor, extraction of `_sleeper_propose_core` |
| `living-memory/HLD.md` | n/a | compatibility pointer per docs/agent-workflow; architecture.md carries the change |
| `docs/cross-client-invariants.md` | updated | outlook enum, attempt-state enum, shortfall enum, validation codes |
| `docs/glossary.md` | updated | overhaul, package, tier, roadmap, attempt |
| ADR or `DECISIONS.md` entry | updated | D-188 (nine defaults, v1 execution posture) + ADR-020 (plan-level roster policy) |
| `docs/data-dictionary.md` | updated | five tables |
| `docs/config-reference.md` | updated | `overhaul.enabled` row |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (incl. `check-*.js`) + `web-structure` + `maestro-testid-lint` on the pushed sha — recorded in [status.md](status.md) and TEST_LEDGER before merge.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming the backend suite result, the guard run, typecheck, and the unrun device checklist.
- **TestFlight verification:** [QA.md](QA.md) checklist to be run by the operator on the next build that includes this branch; outcome logged in TEST_LEDGER. Flag stays **false** until then.
- Express lane declared by the operator? **no** — full gates.
