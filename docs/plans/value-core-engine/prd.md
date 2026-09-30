# PRD — Value-core trade engine

**Date:** 2026-09-30 · **Status:** spec, not built · **Owner:** operator
**Decision being implemented:** the operator's 2026-09-30 call to rebuild from scratch instead of patching.

## 1. The decision in one paragraph

We are replacing how the app builds its trade deck.

The new engine does two separate jobs:
1. It finds every trade that is **fair on consensus market value** between you and each leaguemate. It uses 1–3 pieces per side and follows a handful of hard rules.
2. It **ranks** those fair trades with three plain scores: how much value you get back, how well the trade fits both teams' windows, and how much your own rankings like it. Then it spreads the deck out so no player hogs it.

The old engines stay in the code, one switch away, until the new one beats them on a fixed test bench and on the operator's blind grades.

## 2. Problem

- **Repetition.** One player fills 27 of the top 30 cards in two of the operator's leagues. The prod findings of 2026-09-29 are in the unmerged `docs/plans/trade-suggestion-quality/prod-findings-2026-09-29.md`.
- **Returns too small.** "I'm giving up too much" is 51% of tagged pass reasons. When a card returns 5%+ extra market value, the like rate jumps from about 50% to 73%. The engine does build hundreds of 1st-round-plus returns, but ranks them below the top 30.
- **Not mutual across windows.** "Wrong for my team's direction" is the second pass reason, at 20%.
- **The current engine cannot be tuned out of this.**
  - It has about 315 config keys and about 15 stacked gates.
  - Its composite score had roughly zero correlation with likes (D-180, `living-memory/DECISIONS.md:1828`).
  - Every recent evaluation round ended "evidence-limited". The 6-dimension × 2-manager × 3-assessment scorecard in `docs/plans/model-evaluation-framework/` could not produce a verdict.

## 3. Goals

1. **G1 — Fair by construction.** Every served card sits inside a consensus-value fairness band, adjusted for consolidating a stud. The band is competitor-sized. #214 found our current consolidation math +35 to +68 points heavier than KTC, FantasyCalc and Dynasty Dealer (`docs/feedback/items/214-stud-tax/results.md:257-259`).
2. **G2 — Few, legible hard rules.**
   - Rosters stay legal.
   - Untouchables move only for an above-market return.
   - No junk filler, using the operator's two floors: a rosterable absolute floor and a percentage of the headliner.
3. **G3 — Ranking that is three numbers.** The priority of a card is w_value·value + w_outlook·outlook + w_rank·rankings. The weights start equal. The whole ranking layer is 5 settings.
4. **G4 — A varied deck.** One card per trade idea: versions of a trade with the same partner and the same headliners, where only minor pieces or pick years differ, collapse to the best one. Every acquisition is shown once before any is shown twice. In the first 30 cards no partner takes more than its share and no player appears more than 3 times. Nothing else is filtered at the ranking layer: weak trades sink, they don't vanish.
5. **G5 — Every card says why.** The card reasons come from the three scores, e.g. "Fair on value · Fits their rebuild · You rank Chase 12 spots above market".
6. **G6 — A measuring stick before any rollout.**
   - A frozen bench of the operator's connected leagues.
   - Five automatic guardrails.
   - A real-trade recall check.
   - A blind-grade export and import.
7. **G7 — Reversible.** A default-off flag, tester-only first, no client release, no schema change.

## 4. Non-goals (v1)

- **No machine learning, no learned acceptance model.** The three weights are set by hand and tuned on the bench.
- **No change to mobile or web code.**
- **Trade-intent decks stay on the legacy engine.** This covers Consolidate, Tier up and Tier down (`trades.intent_modes`).
- **Other surfaces stay on the legacy engine:**
  - `/api/trades/asset-ideas` and `/api/trades/fair-packages`;
  - the manual calculator;
  - prepared inventories. `trade.prepared_inventory` adoption is disabled while the flag is on.
- **No likes-you injection, standing-offer stamps, breaker narration, lanes, fatigue or taste multipliers, exploration wildcards, first-session shaping or ghost-holdout withholding on value-core decks.** These layers belong to the legacy stack. Open question Q2 asks which, if any, come back.
- **No counterparty personal boards in scoring.** The rank score uses only the viewer's board. The partner side is judged on consensus value and the partner's window, the evidence we actually have for most teams.
- **No new standings providers.** ESPN, MFL and Fleaflicker standings stay "not implemented" (`backend/outlook/league_state.py:295-315`), so those leagues get windows from roster age and picks only.
- **No deletion of old engines, flags or knobs.**

## 5. User-visible behavior (flag on, user in the tester allowlist)

- **The deck opens with cards from many different partners and players.** No trade idea repeats with only minor pieces or pick years swapped, and no acquisition is shown twice until every other one has been shown once. In the first 30, no single player appears more than 3 times and no partner takes more than its share (4 of 30 in a 12-team league). A repeated partner is pushed down too, at half the player rate.
- **Every card is fair on consensus value.** The adjusted ratio sits within ±10% by default. When one side gets the single best asset with fewer pieces, the other side must add a premium. That premium is up to 15% for an elite asset and near zero for mid-tier ones, which matches the operator's "tier-1 commands a huge premium, mid-tier barely any" (`docs/plans/trade-logic-interview-2026-07-17.md`).
- **Cards that bring back a real piece rise.** A real piece is a player who would start in your lineup, or a 1st-round-value asset. Bench swaps sink.
- **Cards that fit both teams' windows rise.**
  - A contender is rewarded for improving its starting lineup.
  - A rebuilder is rewarded for gaining youth and picks.
  - Windows come from roster age and picks (the existing `infer_team_outlook`), plus points-for standings.
  - Standings get a small weight early in the season: 0 in the preseason, about 0.11 at week 3, full weight from week 8. This follows the operator's 2026-09-29 decision.
  - A window you declared yourself always wins.
- **Cards where you rate incoming players above market, or outgoing players below market, rise.** Your board is shrunk toward consensus by how many matchups you've done on each player (w = n/(n+4)).
- **The card shows the value bar** (give vs get totals) and **1–3 reason lines**. It shows no lane chips, narrative paragraph or breaker line.
- **Unchanged:**
  - "What can I get for X", "I want Y" and the specific-team deck all work. Pins and the partner are hard constraints.
  - Untouchables are only offered when you get at least 8% above market back.
  - "Not interested" players never come back to you.
  - A trade you already passed does not return. This uses the existing exact-disposition check.
  - The fairness slider can only tighten the band. At 0.95 it narrows the band to ±5%. It can never loosen it.

## 6. Success metrics

**Bench guardrails.** These are automatic. They are computed on the first 30 cards of every bench team's deck, for every seat in every bench league.

| Guardrail | Definition | Target |
|---|---|---|
| Insult rate | share of cards where the other side loses more than 20% of raw market value: (get − give)/get > 0.20 | **< 3%** |
| Real-piece-back share | share of cards whose best incoming asset starts in the viewer's post-trade lineup or is worth ≥ the first_1 tier floor (Late 1st, about 1,492 value) | **≥ 70%** |
| Median value given | median of (get − give)/give | **≥ −10%** |
| Max acquired appearances | most cards any one acquired (received) asset appears in | **≤ 3** on every seat |
| Near-duplicates | cards that repeat an earlier card's trade idea (same partner and headliners; minor pieces or pick years differ) | **0** on every seat |

The bench also reports, without gating on them, repeat acquisitions (the same headliner, or a pick, from the same partner), the most cards from one partner, and the most cards any asset appears in on either side.

**Blind grade.**
- The operator grades 40 shuffled cards per engine variant, with the source hidden: "would I send this?" on a 1–5 scale, with optional reason tags.
- Target: **mean ≥ 4.0**, clearly above the incumbent's served cards. The prod baseline is about 2.5 (the operator's "5 of 10").

**Real-trade recall.** The target is to report a baseline, not to pass a gate.
- Take the 77 in-season, two-team trades reconstructable from committed fixtures: FFV3 2022–2025 and Lakeview 2024–2025.
- For each, give the engine the two rosters from the week before and measure top-10 recall (exact or close trade).
- Also report the share of real trades inside the fairness band, and the band that would cover 80% of them. That is the calibration input for `vc_band`.

**Latency.** Value-core generation (core, ranking and deck) for a 14-team league must be **p95 < 8 s** on Render, well inside the current interactive 18–75 s (`docs/plans/trade-search-latency/README.md:13`). The core has an 8 s time budget and deterministic work caps ([lld.md §4.6](lld.md#46-complexity-caps-and-pruning)).

**After graduation.** Track like rate, the "giving up too much" pass share (target < 25%), sends and accepted proposals, joined through `deck_impressions.valuation_json`.

## 7. Rollout and kill switch

1. **Build dark.** Flag false. The full suite and flag-off byte-identity pass ([specs.md §6](specs.md#6-integration-checklist-lead)).
2. **Bench.**
   - The operator freezes the bench leagues with `value_core_bench freeze`, reading prod read-only.
   - Run the guardrails and recall.
   - Tune the knobs until the guardrails pass.
   - Export the blind grade: value-core variants alongside the incumbent's served cards.
3. **Tester-only live.** Flag true, `vc_testers_only = 1`. The operator runs the TestFlight checklist in [scope.md §3](scope.md#3-evidence-scope).
4. **Graduate.** Set `vc_testers_only = 0` once the graduation criterion in scope §2 is met. That is an operator decision.
5. **Kill.**
   - `trade.value_core` → false, then `POST /api/feature-flags/reload`. The next generate runs the legacy engine, because the safety signature and request signature change.
   - Or `vc_testers_only` → 1 to fall back to testers only.
   - There is no silent automatic fallback. A value-core failure fails that job visibly and logs it, so the two engines never mix in one deck or in the measurements.

## 8. Open questions (lead to take to the operator before build)

- **Q1 — Failure behavior.** v1 fails the job if the value core throws: the client shows the existing error state and a retry regenerates. Should it instead fall back to the legacy engine for that job, logged and marked in `trades_generated`? The spec says no, to keep measurement clean.
- **Q2 — Likes-you and standing offers.** These cards come from other managers' likes. Should they be merged into value-core decks, pinned on top as the legacy deck does? v1 leaves them out. That lowers match surfacing but keeps the deck single-source.
- **Q3 — Starter-strength in the window.** Should the window use the #372 starter-value index? It needs `trade.outlook_composite` on, or a direct call to `starter_value_signal`. v1 uses age, picks and points-for only, as the operator named.
- **Q4 — Blind-grade graders.** The 2026-09-30 note in the superseded plan says 1–2 testers will blind-grade alongside the operator. The export supports several sheets, one per grader. Who are they?
- **Q5 — Trade intent.** Should value-core v1 also serve intent-mode decks by mapping Consolidate, Tier up and Tier down to shape constraints? v1 hands them to the legacy engine.
- **Q6 — Bush League** has never been served a card. The freeze reads DB state directly, so it does not depend on served decks. But if the league has no `league_members` rows it cannot be benched. That needs checking at freeze time.

## 9. Risks

- **The default band and premium are guesses** until the recall calibration runs. The guardrails are the tripwire. The knobs are deploy-free.
- **Recall evidence is thin.** It covers 77 reconstructable trades from the two franchises with committed weekly rosters. Other picks held at trade time and player ages are absent from the fixtures ([lld.md §8.3](lld.md#83-real-trade-recall-backendevalvalue_core_recallpy)).
- **Swipes still train the board.** Trade swipes still move the user's Elo through the existing `trade_k_like`/`trade_k_pass` path, as they do for legacy cards. The bake-off zeroes these knobs. The value core does not.
- **A parallel scoreboard exists.** An uncommitted `backend/eval/deck_scoreboard.py` in the `trade-quality-scoreboard` worktree measures *served* decks with overlapping numbers. The two should share definitions: the lead decides whether it lands, and whether the bench adopts its thresholds.
