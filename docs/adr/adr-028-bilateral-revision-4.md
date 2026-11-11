# ADR-028 — Revision 4 reorders through support scores; Calibration adds it as an additive arm

**Date:** 2026-11-10
**Status:** accepted for default-dark implementation; activation and grading are operator steps

## Context

612 real Sleeper offers (offer-learnings evidence) show managers hold their picks, resist
giving up their best asset for pieces, and prefer small offers. The operator asked for these
as ranking changes driven by the other team's outlook, shipped dark and graded first, with
new Calibration trades "additive to current calibration decks". Production serves revision 2;
revision 3 exists dark. The Calibration round in production is a frozen, equal-quota v2/v3
pair under one round id.

## Decision

1. `owner-v2-bilateral-4` subclasses revision 2, never revision 3, behind its own selector,
   which wins over the v3 selector when both are exactly 1.
2. Every rule acts on the two managers' support scores (the inputs of the ranker and of
   bilateral presentment), never on `utility`, market gain, package price, floor or overpay.
   So the eligible inventory is revision 2's and only order changes; presentment cannot
   undo a demotion because it reads the same scores.
3. The premium uses the outlook the engine already resolves for that team (declared,
   caller-inferred or roster-inferred), recorded with its source. Unknown values get none.
4. The tie-breaker is one extra key inside bilateral-1's existing comparable set, after
   diversity usage, so it can only choose among offers the ranker already treats as equal.
5. Calibration folds revision 4 into each *new* round build after the paired v2/v3 order is
   fixed: same capture and gates, shared cards credited, new cards inserted without
   reordering the pair, failure isolated. Exposed and completed decks are never changed.

## Consequences

- Revision 1-3 bytes are unchanged with the selector at any value other than 1 (goldens from
  `origin/main`). `test_deck_pipeline_digest` changes and needs one coordinated bump.
- Calibration's paired v2/v3 comparison keeps its exact selection; revision 4 is read as an
  extra arm in the admin report, not as part of the two-arm comparison.
- Pairs whose deck is already exposed get no revision-4 cards in this round; extending them
  needs an operator decision (scope §6).
- Starting values (20/10/0 premium, .10 demotion) are effects to grade, not fitted parameters.
