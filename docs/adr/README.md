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

_(none yet — add entries here as ADRs land: `- [ADR-0001 Title](0001-title.md)`)_
