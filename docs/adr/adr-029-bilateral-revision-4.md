# ADR-029 — Revision 4 reorders through support scores; Calibration adds it as an additive arm

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
6. **Fourth rule, partner activity (WS7, 2026-11-10), behind flag `trade.partner_activity`.**
   The worker passes `partner_activity` (each league manager's completed public trades this
   league year, from `manager_profiles`) only when the flag is on and revision 4 is selected;
   the generator stays a leaf. The threshold is the league's own: flagged at or below a third
   of the league median, only when the median is at least 2 and at least half the managers
   have a profile; no profile is never flagged, and a league where everyone trades flags
   nobody. A flagged manager's offers drop `.05` on both support scores (half the best-asset
   demotion, past the comparable set), so, like decision 2, order changes and inventory does
   not. With the input, proofs gain `revision_4.partner_activity` and rules version
   `offer-learnings-1+partner-activity-1`; without it, revision 4's bytes are unchanged.

## Consequences

- Revision 1-3 bytes are unchanged with the selector at any value other than 1 (goldens from
  `origin/main`). `test_deck_pipeline_digest` changes and needs one coordinated bump.
- Calibration's paired v2/v3 comparison keeps its exact selection; revision 4 is read as an
  extra arm in the admin report, not as part of the two-arm comparison.
- Pairs whose deck is already exposed get no revision-4 cards in this round; extending them
  needs an operator decision (scope §6).
- Starting values (20/10/0 premium, .10 demotion) are effects to grade, not fitted parameters.
- Partner activity (decision 6): Calibration captures are built with the revision-4 selector
  at 0, so the Calibration revision-4 arm carries no `partner_activity` and grades WS1's
  three rules only, until the operator decides otherwise. A profile rebuild marks no stored
  first page stale; a page can carry the previous count's order until its next invalidation.
