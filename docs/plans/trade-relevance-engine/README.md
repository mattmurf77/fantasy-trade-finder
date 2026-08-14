# Trade Relevance Engine — X-algorithm audit & enhancement plan

> **Purpose:** planning home for the 2026-08-14 initiative to make FTF's trade
> suggestions interaction-driven the way X's For You feed is — use everything we know
> about a user (their interactions, their league's real market, their pre-platform
> history, what they value in players) to produce and present the most relevant and
> enticing trade offers.

## Contents

| Doc | What |
|---|---|
| [ftf-current-state.md](ftf-current-state.md) | File:line map of FTF's trade generation, ranking, and interaction-signal systems at HEAD 2026-08-14. Supersedes `docs/plans/tiktok-discovery/current-state.md`. |
| [audit-x-vs-ftf.md](audit-x-vs-ftf.md) | Stage-by-stage audit of X's FYP pipeline vs FTF's, with per-stage verdicts and a scorecard. |
| [enhancement-plan.md](enhancement-plan.md) | The buildable roadmap: P0 close existing loops → P1 promote/widen the learned ranker → P2 source neglected data (market, FA, pre-join history) → P3 archetypes + user value decomposition → P4 presentation. |
| [hld.md](hld.md) | **SIGNED OFF** high-level design (dual-agent, 4 rounds): pass ledger, serving contract, data model, D1–D12 decisions, privacy posture, non-goals, risk register + operator questions. |
| [lld.md](lld.md) | **SIGNED OFF** low-level design (dual-agent, 4 rounds): DDL, interfaces, build order B1–B15, core logic, error matrix E1–E27, migration/rollout, sabotage tests T-1–T-35. |
| [prds/](prds/) | Five phase PRDs (dual-agent drafted, cross-reviewed): [P0](prds/prd-p0-close-the-loops.md) · [P1](prds/prd-p1-learned-ranker.md) · [P2](prds/prd-p2-market-and-history.md) · [P3](prds/prd-p3-archetypes-value-decomposition.md) · [P4](prds/prd-p4-presentation.md). |
| [reconciliation-log.md](reconciliation-log.md) | The dual-agent authoring record for all seven artifacts: every blocking objection, fix, and parent amendment, plus the consolidated operator decision queue. |

## Companion reference

How X's algorithm actually works — four subsystem deep-dives with code citations,
produced from the 2026-08-13 open-source release: [`reference/x-algorithm/`](../../../reference/x-algorithm/).

## Relationship to prior work

Builds directly on `docs/plans/tiktok-discovery/` (2026-07-26), whose F1–F10 features
are the substrate this plan extends — 9 of 10 are live; F6 (learned value model) is
built and dark. That folder's five guardrails remain standing and are restated in the
enhancement plan.

## Status

- 2026-08-14: research, audit, and plan complete.
- 2026-08-14 (later): HLD and LLD **signed off** (dual-agent, 4 rounds each);
  five phase PRDs drafted dual-agent and cross-reviewed (8 blockers found and
  fixed; parent docs amended in the same change — see the reconciliation
  log). Nothing built. Build entry point: PRD P0's B1 (pass ledger), after
  the operator clears the decision queue consolidated at the end of the
  reconciliation log.
- 2026-08-14 (ship time): cross-session supersession — **P0-1 (register
  dropped client events) shipped independently** via the G-031 session
  (PR #116); the P0 PRD's R4 carries the note (remaining work =
  verification only). The impression-ownership validation (P0 R6) has a
  standalone fix session in flight; if it lands first, B5 inherits it.
