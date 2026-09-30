# ADR-024: Value-core trade engine — a value-only fair pool, ranked by three scores

Date: 2026-09-30
Status: Accepted. Built dark behind `trade.value_core` (default off); serving beyond testers is an operator decision.

## Context

The legacy trade deck comes out of a stacked engine: v2/v3 generation, bake-off
arms, the owner and bilateral constructors, the personal-market policy, roster
gates, and a presentation stack (Thompson ordering, diversity, fatigue, taste,
value model, exploration, first-session shaping). It carries about 315 config
keys and about 15 stacked gates. The 2026-09-04 prod read behind
[D-180](../../living-memory/DECISIONS.md#d-180--consensus-value-is-a-non-bypassable-market-guardrail-personal-rankings-are-the-ordering-signal)
found that its composite score had roughly zero correlation with likes. Later
evaluation rounds, including the model-evaluation scorecard, ended
evidence-limited.

The 2026-09-29 prod read of the operator's leagues named three failures:

- **Repetition.** One player filled 27 of the top 30 cards in two leagues.
- **Returns too small.** "I'm giving up too much" was 51% of tagged pass
  reasons. Cards returning 5% or more extra market value were liked about 73%
  of the time, against about 50% otherwise. The engine built hundreds of
  real-return trades but ranked them below the top 30.
- **Not mutual across windows.** "Wrong for my team's direction" was the second
  pass reason, at 20%.

Feedback #214 also found the legacy consolidation math 35–68 points heavier than
KTC, FantasyCalc and Dynasty Dealer. On 2026-09-30 the operator decided to
rebuild the suggestion engine rather than keep tuning the stack.

## Decision

1. **A value-only core.** For the viewer against each partner, enumerate every
   1–3 × 1–3 package and keep those inside one fairness band on consensus market
   value (`vc_band`, ±10%). When one side gets the trade's single best asset with
   fewer pieces, credit it one competitor-sized stud premium,
   `vc_stud_premium × (headliner/elite)²` (up to 15%). A few legible hard rules
   replace the gate stack: asset floor, junk filler relative to the trade's
   headliner, untouchables only for an above-market return, irreducibility,
   roster size, lineup legality. The core never sees a personal board or a
   window.
2. **A separate three-weight ranking.** Every fair trade gets a value, an outlook
   and a rank score in [0, 1]. Priority is their weighted mean, equal weights by
   default: five ranking knobs in all. A greedy assembly with a repeat penalty
   keeps any asset to 3 of the first 30 cards. The ranking orders and never
   drops a trade. Card reasons come from the three scores.
3. **One branch point that bypasses the legacy stack.** `_run_trade_job` keeps
   its prelude, then hands eligible jobs to the value core and returns. For
   those jobs no legacy gate, arm or ordering layer runs, so no deck mixes the
   two engines. The package is a leaf that never imports `server`, and the
   server imports it lazily, so with the flag off it is never loaded.
4. **No silent fallback.** A value-core exception fails the job visibly. The job
   is not quietly re-served by the legacy engine, so every measurement stays
   single-source.
5. **A flag plus a tester lever.** `trade.value_core` defaults off. While it is
   on, `vc_testers_only` (default 1) limits serving to the tester allowlist. The
   engine earns wider serving on a fixed bench — four guardrails, real-trade
   recall and the operator's blind grade — before `vc_testers_only` goes to 0.

Each served card's evidence (scores, weights, windows, market, per-asset values)
goes into the existing `deck_impressions.valuation_json`, with `model_arm` and
`policy_variant` both `value_core`. No schema change and no client change.

## Alternatives considered

- **Patch v2/v3/bilateral in place.** This was the 2026-09-29 repair plan: a
  scoreboard, then repetition, value-ranking and standings-based outlook fixes.
  Rejected because each fix adds a layer to a stack whose interactions already
  hide the signal, and ~315 knobs make any single change hard to attribute.
- **A hybrid**, such as legacy generation feeding the new ranking (plan step 5).
  Rejected for v1: a fair pool can only be trusted when the rules that shaped it
  are known, and mixing engines inside one deck breaks per-card attribution.
- **A learned acceptance model.** Rejected for v1: too few paired outcomes to fit
  one, the same constraint recorded in
  [ADR-022](adr-022-preference-led-bilateral.md). Three hand-set weights tuned on
  the bench are legible and change without a deploy.
- **Automatic fallback to the legacy engine on error.** Rejected: it would mix the
  engines in the measurements exactly when the new one misbehaves.

## Consequences

- **Easier:** the ranking layer is five settings; every card explains itself from
  three numbers; the bench gives a pass/fail verdict before any rollout; rollback
  is a flag flip or one knob.
- **Legacy surfaces stay legacy:** intent-mode decks, asset ideas, fair packages,
  the manual calculator and prepared inventories keep the old engines, and
  prepared-inventory adoption is off while the flag is on. Nothing old is
  deleted.
- **Layers value-core decks drop by design:** likes-you injection, standing-offer
  stamps, breaker narration, lanes, fatigue, taste, exploration wildcards,
  first-session shaping and ghost holdout.
- **The partner is judged on consensus value and their window,** not on their
  personal board.
- **Precedence:** while the flag is on, value-core decks supersede the
  [ADR-022](adr-022-preference-led-bilateral.md) bilateral ordering for the jobs
  they serve.
- **Risks:** the default band and premium are uncalibrated until the recall run;
  recall evidence is thin (77 reconstructable trades, no ages, only traded
  picks); trade swipes still move the user's board through the existing
  `trade_k_like` / `trade_k_pass` path.

Plans: [scope](../plans/value-core-engine/scope.md) ·
[PRD](../plans/value-core-engine/prd.md) ·
[HLD](../plans/value-core-engine/hld.md) ·
[LLD](../plans/value-core-engine/lld.md) ·
[architecture](../architecture.md#value-core-trade-engine) ·
[configuration](../config-reference.md#flags--value-core-trade-engine-2026-09-30-ships-off)
