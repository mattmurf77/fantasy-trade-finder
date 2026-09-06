# Fleeced product overview

Fleeced is a dynasty fantasy football trade discovery product. Managers express their own player valuations through ranking interactions, then explore trades informed by those preferences, market value, and roster context. The goal is useful trades; more time spent swiping is not itself success.

The user-facing name is **Fleeced: Dynasty Trade Finder** (D-057). The mascot is the ram, also named Fleeced; “The Analyst” names its guide role (D-155). Internal repository, service, and native target names retain earlier names where changing them would disrupt integrations.

## Product surfaces

| Surface | Purpose and implementation |
|---|---|
| iOS app | Ranking, trade discovery/calculator, league and draft tools, account/settings flows in `mobile/` |
| Web companion | Browser entry, ranking and trade surfaces in `web/`; scope decision D-173 |
| Browser extension | Manifest V3 companion in `extension/`; distribution is a separate decision |
| Backend | Flask APIs, persistence, ranking/trade generation, platform adapters, analytics and background jobs in `backend/` |

Sleeper, ESPN, and MyFantasyLeague integrations support league workflows. Available reads/writes differ by platform and feature flag; consult [integrations](../integrations/README.md), [API reference](../api-reference.md), and [configuration](../../config/features.json) for exact capabilities. Account/identity and multiuser data exist; old “Sleeper-only, personal-use-only, no accounts” snapshots are historical.

## Sources of truth

- **Implementation:** code/configuration, [architecture](../architecture.md), [schema](../data-dictionary.md), [API](../api-reference.md), and [shared invariants](../cross-client-invariants.md). Python/Flask with SQLAlchemy Core; SQLite locally and Postgres in production. Dependency manifests define installed versions.
- **Release state:** [handoff](../../living-memory/HANDOFF.md) links the specific release record. Do not copy version numbers, test counts, flag states, or release claims into introductions.
- **Intent/acceptance:** initiative plan/status, [feedback records](../feedback/items/INDEX.md), and [ADRs](../adr/README.md). A plan or flag default does not prove a deployed release.
- **Business strategy:** [business context](../business/context.md) and adopted measurement definitions. Both server and client analytics implementations exist; actual coverage requires observed data.
- **Voice/design:** [voice](voice.md), [brand](../design/brand.md), [tokens](../design/design-system.md), and [components](../design/components.md).

## Boundaries and success

Dynasty football is the established domain. Rankings, trade discovery, manual calculation, league analysis, draft support, and season-oriented analysis coexist; old assertions that draft/calculator tools are out of scope no longer describe the product. New sports, distribution channels, monetization, and rollouts require explicit product scope.

Success evidence connects expressed preferences to useful proposals and completed trades. Preserve uncertainty and exposure context when interpreting likes, passes, or model comparisons. Market consensus, personal valuation, and forecasts answer different questions; labels and explanations keep them distinct.
