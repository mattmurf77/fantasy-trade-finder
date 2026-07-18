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
