# Engineering contract map

This page routes contracts formerly mixed into `living-memory/HLD.md` and `LLD.md`. It is a navigation aid, not another architecture/schema snapshot. Update the authoritative reference or initiative below when a contract changes.

## Current reference owners

| Concern | Reference |
|---|---|
| Module wiring, request/background lifecycles | [Architecture](architecture.md) |
| Tables, lifecycle, migrations | [Data dictionary](data-dictionary.md), `backend/database.py` |
| Routes, request/response and error contracts | [API reference](api-reference.md), `backend/server.py` |
| Flags and runtime tunables | [Config reference](config-reference.md), source configuration |
| Cross-client vocabulary, values and display invariants | [Shared invariants](cross-client-invariants.md) |
| Integration credentials, transport, error/redaction contracts | [Integrations](integrations/README.md) |
| Coding, collaboration, release practices | [Agent workflow](agent-workflow.md), [coding guidelines](coding-guidelines.md) |

The current implementation uses SQLAlchemy Core, local SQLite at `data/trade_finder.db`, production Postgres, a pytest suite, and mobile/web automated checks. Old claims of singular `user`/`player` tables, two active SQLite locations, undeployed Postgres, or no pytest are retired. Use actual table definitions and CI rather than historic inventories.

## Contract-specific evidence

These records preserve detailed implementation reasoning and unresolved limits. Read their status and verify the relevant source before acting; a historical design does not grant rollout permission.

| Contract | Owner/evidence |
|---|---|
| Policy evaluation, generator arms, proposal/match attribution, two-user exposure | [Personal-market policy](plans/personal-market-policy/status.md), [two-user funnel](plans/personal-market-policy/two-user-funnel.md), [owner-contract review](plans/owner-contracts/review.md) |
| Owner-driven construction and exclusive serving; captured inputs, attribution and bounded search | [Architecture](architecture.md#owner-driven-construction-challenger), [ADR-019](adr/adr-019-owner-construction-before-market-terms.md), [owner-only scope](plans/owner-only-uncapped/scope.md), [dated paging/release evidence](recovery/2026-09-08-owner-only-impression-paging.md) |
| Team overhaul eligible pools, compatible packages, reservations, manual fallback and platform capabilities | [Build contract](plans/team-overhaul/BUILD-CONTRACT.md), [later owner decisions](plans/team-overhaul/owner-decisions.md), [API](api-reference.md), [release record](recovery/2026-09-07-team-overhaul-release.md), [entry revision](feedback/items/425-overhaul-tile-replaces-draft/prd.md) |
| Shared significance filtering, trusted exceptions, cache safety and calibration | [Architecture](architecture.md#shared-recommendation-significance), [scope](plans/trade-significance/scope.md), [validation and release gates](plans/trade-significance/validation.md) |
| Bounded diagnostic storage, owner-scoped reconstruction and debug-only expiry | [ADR-021](adr/adr-021-bounded-deck-diagnostics.md), [data lifecycle](data-dictionary.md#deck-diagnostic-storage-2026-09-15), [storage recovery/recheck](plans/db-storage-reduction/release.md) |
| Final-roster evaluation and forecast/provenance enforcement | [Roster evaluation](plans/post-trade-roster-evaluation/validation.md), [model activation](plans/trade-model-activation/validation.md) |
| Request-scoped scoring and captured job ownership | [Budget scalability implementation](plans/budget-scalability/implementation.md) |
| Account deletion, queued writes and worker fencing | [ADR-017](adr/adr-017-account-deletion-work-leases.md), [security release](plans/archive/2026/security-data-hardening/deployment.md) |
| Season snapshots, observed data versus forecast claims, request isolation | [Win Now build](plans/win-now/BUILD.md), [evidence](plans/win-now/EVIDENCE.md) |
| Offline grade isolation and append-only measurement | [Receipts](plans/receipts/README.md) |
| Provider identity and provider-driven presentation | [Connected rankings](plans/connected-rankings/status.md), [shared invariants](cross-client-invariants.md) |
| Exact interest/pass disposition and immutable reason episodes | [API reference](api-reference.md), [episode repair](feedback/items/419-rejected-interest-resurfacing/backend-code-walk.md#qa-a-episode-repair--final-path-atop-e02d074e), [data dictionary](data-dictionary.md) |
| Win Now request generations, shared session recovery and status errors | [Mobile state ownership](../mobile/src/state/README.md), [recovery evidence](feedback/items/420-win-now-loading/code-walk.md) |
| Bounded preference for smaller eligible player packages | [Small-package contract](plans/small-trade-packages/prd.md), [architecture](architecture.md) |
| Settings route/query ownership | [Settings IA](plans/settings-ia-hub/plan.md) |
| Synthesized cards, generation/presentment gates, bake-off attribution, pricing waterfalls, board assertions, mock-draft ownership and picker contracts | [Shared invariants](cross-client-invariants.md), applicable [feedback item](feedback/items/INDEX.md), and preserved LLD sections below |

Construction, policy evaluation, significance filtering and diagnostics have different owners. Owner-only serving selects which generated arm executes; significance does not select arms or change rankings, and a default-off setting is not proof of a deployed mode. Diagnostic expiry removes debug detail, not core recommendations, frozen valuations or outcomes.

For Team overhaul, use the build contract together with later owner decisions and platform API contracts. The original discovery mocks and initial Sleeper-only design predate the all-platform send revision and replacement entry tile. Likewise, an initial owner-only release plan predates its activation and paging incident. Read dates and follow the later evidence; neither an old plan nor a checked-in flag proves current production state.

## Preserved observations and decisions

The full [HLD snapshot](../living-memory/archive/static-2026-09-06/HLD.md) and [LLD snapshot](../living-memory/archive/static-2026-09-06/LLD.md) retain all prior details and headings. Recent LLD sections include D-085/090/091/096 (placement, derived state, synthesized cards), D-142/144/146/147/148 (objections, receipts, pricing, module bindings and value seams), D-154/160 (full-sweep budgets and retired save keys), and D-176 (mixed pick arrays and platform writes). These are searchable historical records, not a second current specification. Existing [decisions](../living-memory/DECISIONS.md) and canonical reference sections retain their IDs.

Reusable conventions from the old mixed log remain useful when supported by the relevant implementation: shared presentational variants use opt-in props; first-writer-wins updates are conditional and atomic; one form owns its destructive confirmation; derived display coordinates follow their source ordering; inbox rows have their own idempotency rather than borrowing push gates. Before changing one, inspect its source-specific decision/evidence and update the corresponding canonical contract.

No unresolved item was closed by this consolidation. Preserve an observation with its original date and evidence until it is verified, superseded, or explicitly declined; do not promote a stale assertion merely because it survived in a memory file.
