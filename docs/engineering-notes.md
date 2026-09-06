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
| Final-roster evaluation and forecast/provenance enforcement | [Roster evaluation](plans/post-trade-roster-evaluation/validation.md), [model activation](plans/trade-model-activation/validation.md) |
| Request-scoped scoring and captured job ownership | [Budget scalability implementation](plans/budget-scalability/implementation.md) |
| Account deletion, queued writes and worker fencing | [ADR-017](adr/adr-017-account-deletion-work-leases.md), [security release](plans/archive/2026/security-data-hardening/deployment.md) |
| Season snapshots, observed data versus forecast claims, request isolation | [Win Now build](plans/win-now/BUILD.md), [evidence](plans/win-now/EVIDENCE.md) |
| Offline grade isolation and append-only measurement | [Receipts](plans/receipts/README.md) |
| Provider identity and provider-driven presentation | [Connected rankings](plans/connected-rankings/status.md), [shared invariants](cross-client-invariants.md) |
| Settings route/query ownership | [Settings IA](plans/settings-ia-hub/plan.md) |
| Synthesized cards, generation/presentment gates, bake-off attribution, pricing waterfalls, board assertions, mock-draft ownership and picker contracts | [Shared invariants](cross-client-invariants.md), applicable [feedback item](feedback/items/INDEX.md), and preserved LLD sections below |

## Preserved observations and decisions

The full [HLD snapshot](../living-memory/archive/static-2026-09-06/HLD.md) and [LLD snapshot](../living-memory/archive/static-2026-09-06/LLD.md) retain all prior details and headings. Recent LLD sections include D-085/090/091/096 (placement, derived state, synthesized cards), D-142/144/146/147/148 (objections, receipts, pricing, module bindings and value seams), D-154/160 (full-sweep budgets and retired save keys), and D-176 (mixed pick arrays and platform writes). These are searchable historical records, not a second current specification. Existing [decisions](../living-memory/DECISIONS.md) and canonical reference sections retain their IDs.

Reusable conventions from the old mixed log remain useful when supported by the relevant implementation: shared presentational variants use opt-in props; first-writer-wins updates are conditional and atomic; one form owns its destructive confirmation; derived display coordinates follow their source ordering; inbox rows have their own idempotency rather than borrowing push gates. Before changing one, inspect its source-specific decision/evidence and update the corresponding canonical contract.

No unresolved item was closed by this consolidation. Preserve an observation with its original date and evidence until it is verified, superseded, or explicitly declined; do not promote a stale assertion merely because it survived in a memory file.
