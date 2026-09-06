# Project documentation

Start with [the product overview](product/overview.md) for current scope, [the root README](../README.md) to run the project, and [the shared agent contract](../AGENTS.md) for working rules. Read only the topic needed for the task.

## Current reference — one owner per topic

| Topic | Authoritative document |
|---|---|
| Product purpose and capabilities | [Product overview](product/overview.md) |
| Architecture and data flow | [Architecture](architecture.md) |
| Route contracts | [API reference](api-reference.md) |
| Tables and data lifecycle | [Data dictionary](data-dictionary.md) |
| Flags, environment and tuning | [Configuration reference](config-reference.md) |
| Shared client constants | [Cross-client invariants](cross-client-invariants.md) |
| Domain language | [Glossary](glossary.md) |
| Operations and incident recovery | [Runbook](runbook.md) |
| UI and writing conventions | [Design system](design/design-system.md), [components](design/components.md) |
| External APIs | [Integrations](integrations/README.md) |
| Engineering workflow | [Agent workflow](agent-workflow.md), [coding guidelines](coding-guidelines.md) |
| Architectural rationale | [Decision records](adr/) |

## Work and evidence

- [Initiatives](plans/README.md): generated from each initiative's status source. Proposed work and shipped behavior are distinct.
- [Feedback](feedback/items/INDEX.md): stable item IDs, status and links; generated from item records.
- [Trade-engine owner decisions](plans/trade-engine-balance/README.md): answers, open questions and superseded proposals in one place.
- [Research](research/README.md): outside evidence and competitor observations; these do not override accepted product decisions.
- [Dated reviews](reviews/README.md): point-in-time findings; never assume an old finding still applies.
- [Recovery](recovery/): append-only records, including [the organization migration](recovery/2026-09-06-project-organization.md).
- [Business](business/README.md): business assumptions and deliverables, with product facts linked to the overview.
- [Session memory](../living-memory/README.md): short handoff and priorities; detailed history is retrieved on demand.

`../_local/` holds private recovery archives, captured research and scratch. It is ignored by Git and excluded from app builds. It is not a source of current product behavior. Historical source mirrors have been archived with integrity manifests; do not copy them over working code.
