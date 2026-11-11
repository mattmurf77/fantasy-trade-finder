# ADR-030: Rules-first deck construction (fast deck v2)

Date: 2026-11-11
Status: Accepted. Ships **on** at merge (flag `deck.rules_first`, code default off). Supersedes
the serving half of [ADR-028](adr-028-page-first-trade-search.md) (its 150-card fast deck and
the flags `trade.fast_deck` / `trade.fast_deck_shadow`, now read nowhere). ADR-028's page-first
search itself stands and is what this decision runs.

Design and measurements: `docs/plans/realtime-trade-engine/fast-deck-v2-design.md` (§3.4, §5–§7).

## Context

The deck's per-card rules (discovery significance; `deck_quality`'s breakup, filler and
redundant QB/TE) ran after generation and rejected 93–97% of what the bilateral generator
emitted. ADR-028's fast deck served the generator's first 150 cards; after the rules, 2 were
left in production on 2026-11-11 and the flag went off (D-232). Its parity tests compared
generator output, never the served deck.

The rules read only a package's terms and inputs the worker already holds, so they can decide
eligibility before pricing and ranking.

## Decision

1. **The per-card rules decide which owner-bilateral cards exist, before ranking.** One
   predicate, `backend/deck_rules.py` (`DeckRules`), built once per job by
   `server._rules_first_deck_rules` from exactly the downstream gates' inputs. It calls the
   downstream definitions themselves (`deck_quality.card_rule`, which `filter_deck` also calls,
   and `server._evaluate_trade_significance`), so the two cannot drift. The rules depend on
   the request only, never on who liked what (decision 3).
2. **The whole admitted inventory is built**, by the page-first search with the predicate as
   its admission hook (`PageSearch(admit=…)`), taken to exhaustion. If the page cannot prove the
   inventory within `MAX_VERIFICATIONS` (12,000) or does not support the request, the **gated
   full solve** builds it (the generator's search with failing expansions skipped and failing
   survivors dropped before its own ranker). Any other failure serves today's full solve. No
   deck-size cap anywhere.
3. **Order-dependent stages stay downstream, unchanged:** likes-you and revised-offer
   injection, decline-window suppression (with its floor and retest), owner revalidation,
   dispositions, the bilateral presentment, the repeat cap, evidence and publication. The
   downstream copies of the per-card rules stay as guards; on a rules-first deck they must
   remove nothing, and the worker logs `rules-first guard` if they do.
   **Liked trades are an overlay evaluated after generation, never an input to it**
   (operator, 2026-11-11), so the generated inventory, stored pages, prepared inventories and
   the safety signature stay cacheable and a new like never needs a rebuild. The likes-you
   step is today's (selection, D-096 gates, flag, boost to the top, cap, exposure), with one
   addition on rules-first jobs: a liked mirror or standing offer that has no matching
   generated card is proven by the job's owner evaluator (`_bakeoff.owner_evaluator`, the one
   owner revalidation runs, with the job's owner context and without the deck rules, which
   likes-you cards are protected from today). Eligible: the injected card carries the proof,
   the generator's market terms, fit context, request evidence and `mismatch_score` 300, and is
   revalidated downstream like any engine card. Not eligible, or any error: today's consensus
   card, unchanged, counted in the `liked cards proven / consensus / errors` log line. At most
   the likes-you cap (3) of evaluations per job, about 9–14 ms each on 12–16-team synthetic
   leagues. Flag off the step is exactly today's (no on-demand proof), which keeps the kill
   switch byte-identical.
4. **Scope:** organic owner-only decks of bilateral revisions 1 and 2 (the generators with
   page-search parity suites), interactive and background jobs alike, when at least one
   per-card rule is live. Pinned, opponent-scoped and intent requests (no served-deck parity
   suite or recorded request covers them; the 247 recorded requests have neither), revision 3
   and 4 (an expected info-level log line), legacy engines, the value core, and
   owner-generator calls outside `_run_trade_job` keep today's path.
5. **One capture per job:** the rules read `deck.quality_filters` once; the downstream quality
   filter of a rules-first job follows that capture, so a reload mid-job neither drops admitted
   cards nor serves cards the job never filtered.
6. **Kill switch:** `deck.rules_first` off restores today's pipeline (full solve, then the
   filters). The job's safety signature carries `rules_first` while it is on, so cached jobs
   and stored first pages built under one setting never serve under the other.

## The definition change (operator-approved 2026-11-11)

Ranking now runs over admitted cards only. Today a rejected card still consumed the ranker's
diversity window and revision 2's same-family precedence before it was thrown away. Measured on
the 247 recorded production requests: the **served set is identical on 247 of 247**; the first
card is the same on 167 (68%); the first 30 share a median of 25 cards (p10 20). No fast path
can reproduce the old order cheaply: under it the first 30 depend on about 70% of the
generator's inventory. That replay
covers the stages that run offline (significance, presentment, quality filters, repeat cap),
not suppression, dispositions or injections. The served set against today's pipeline is the
same for organic owner decks on those requests and on the synthetic leagues, EXCEPT:

- (a) leagues large enough for the incumbent's stream budgets to bind (16+ teams in the
  tests): a **superset**, the evaluator-eligible cards the budgeted solve never reached;
- (b) users at the decline-suppression floor (`_DECK_MIN_CARDS`, 5): the floor now counts
  admitted cards, so a heavy-decline user with a small admitted inventory can get up to 5
  recently declined near-duplicates restored where today the deck was thinner;
- (c) the fatigue-retest grant can go to a different card (below);
- (d) the order changes for everyone (accepted above).

Liked trades are not an exception to the served set: a liked package the generator built is
flagged in place as today; one it did not build (because it fails a rule, or for any other
reason) is now a full engine card when the owner evaluator finds it eligible, where today it
was either the generated card (rule-failing packages the full solve built) or a bare consensus
card (packages it did not build). The first is the same package, now at the top of an
owner-serving deck with the injected cards rather than at its interleaved position (an order
change); the second is the improvement. An ineligible like is today's consensus card.

## Why no shadow week

The operator chose to ship on at merge. The evidence that carries the weight instead: the
served-set and order comparison above, page = gated full solve on every recorded request (and
on synthetic leagues in CI), the downstream guards removing nothing, and the deploy-free kill
switch. `backend/eval/served_deck_replay.py` re-runs the comparison on demand.

## Consequences

- Construction is about the cost of the page search over the admitted inventory (median about
  0.3 s of laptop CPU against 3–4 s for the full solve), and the deck is complete, so the
  publication contract (one evidence seal per job, the published prefix is the head of the
  finished deck) is unchanged.
- Large leagues (16+ teams), where the incumbent's stream budgets bind: the page covers the
  whole un-budgeted admitted universe, so it can serve cards the budgeted full solve never
  reached. A gated fallback there is budgeted; the worker's log line says when that happens.
- A card the rules reject is never generated, so it can no longer be marked later as
  protected and survive the filters through that protection. For likes-you matches and
  standing offers this is closed after generation by the on-demand proof (decision 3).
  **Known difference (reviewer finding B): the fatigue retest.** The one retest grant goes to
  the first matching card in deck order and is consumed in the database, so it is not
  knowable before generation and is not reproduced: under rules-first a grant that today would
  have rescued a rule-failing card goes to the next matching admitted card (or to none). The
  exploration wildcard (also protected) is drawn after generation, but F7 exploration does not
  run on owner-serving decks, so it does not arise. Protected cards themselves are never
  gated.
- The suppression floor (`_DECK_MIN_CARDS`, 5) now measures admitted cards, so for a user with
  heavy decline history it can restore a few suppressed cards where today the filters would
  have left a thinner deck.
- The repeat cap of the deck quality filters moved from 3 to 5 of the first 30 (operator, same
  day), on every path through them. The value core keeps its own per-asset cap
  (`vc_player_cap`, 3): the per-card rules (breakup, filler, redundant) are still the value
  core's, the repeat cap no longer is.
- "Match strength" (`mismatch_score / 300 × 100` in the app) is the card's position from the
  bottom of what the generator emitted, so it reads 100 for nearly every card a thousands-card
  full solve serves and would decay down a few-hundred-card admitted inventory (0% past card
  300; a recorded request admitted 466). Operator decision: the rollout must not visibly move
  it, so every rules-first card carries the constant `trade_fast_deck.MATCH_SCALE` (300, reads
  100). The bar carries no information either way, and whether to replace it is a separate
  decision. `composite_score` (the ordering key) is unchanged. **Training caveat:** the
  impression feature `surplus_margin` is `mismatch_score`, so it is constant on rules-first
  rows and carries no information for value-model training on them.
