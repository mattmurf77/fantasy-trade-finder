# Architecture Decision Records

Short, dated docs capturing **why** a non-obvious choice was made. One file per decision.

## Template

```
# ADR-NNNN: <Decision title>

Date: YYYY-MM-DD
Status: Proposed | Accepted | Superseded by ADR-MMMM

## Context
What problem are we solving? What constraints?

## Decision
What did we choose?

## Alternatives considered
What else did we look at? Why not?

## Consequences
What does this make easier? Harder? What new risks?
```

## When to write one

- Choosing between two real alternatives (Postgres vs. Mongo, Context vs. Redux).
- Doing something that looks weird without context.
- Reversing a previous decision.

Don't bother for routine code changes, bug fixes, or anything self-evident from the code.

## Index

- [ADR-001 Query Cache Persistence Storage: AsyncStorage vs MMKV](adr-001-query-cache-persistence.md)
- [ADR-002 Trade Engine v2/v3 Rebuild](adr-002-trade-engine-v2-v3-rebuild.md)
- [ADR-003 Crown-Asset Package Premium](adr-003-crown-asset-package-premium.md)
- [ADR-004 Chalkline Design Language](adr-004-chalkline-design-language.md)
- [ADR-005 Chalkline Palette v2: ice/flare](adr-005-palette-v2-ice-flare.md)
- [ADR-006 Account-Later Onboarding](adr-006-account-later-onboarding.md)
- [ADR-007 First-Party Analytics Platform + Layered Experimentation](adr-007-first-party-analytics-experimentation.md)
- [ADR-008 Teardown Remediation Wave (2026-07)](adr-008-teardown-remediation-wave.md)
- [ADR-009 Rookie Scope as a Post-Elo View Filter (and the Merged-Band Save)](adr-009-rookie-scope-view-filter.md)
- [ADR-010 User-Asserted Pick Ownership is League-Scoped Truth in `draft_picks`](adr-010-user-asserted-pick-ownership.md)
- [ADR-011 League State Gets an Append-Only History](adr-011-league-state-history-is-append-only.md)
- [ADR-012 A Co-Owned Sleeper Roster Has One League Identity: its Primary `owner_id`](adr-012-co-owned-roster-identity.md)
- [ADR-013 The Fit Challenger is a Generator, Not a Config Profile of the Live Engine](adr-013-fit-challenger-is-a-generator.md)
- [ADR-014 Bake-Off Serving Rounds](adr-014-bakeoff-serving-rounds.md)
- [ADR-015 Negative-Results Memory is a Clamped Soft Prior, Not a Fourth Filter](adr-015-negmem-soft-prior-not-fourth-filter.md)
- [ADR-016 RevenueCat is the Purchase Layer; the Entitlements Ledger is the Truth](adr-016-revenuecat-with-server-truth-entitlements.md)
- [ADR-017 Drain Account Work Before Deleting Its Data](adr-017-account-deletion-work-leases.md)
- [ADR-018 External Weekly Forecasts and an Independent Win Now Season Model](adr-018-win-now-external-forecasts.md)
