# Matchmaking research corpus

> How dating/matchmaking companies (Tinder, Hinge, Bumble, OkCupid, eharmony, CMB) and adjacent
> two-sided matchers build their models — researched 2026-08-15/16 to transfer into FTF's trade
> generation. Operating premise: FTF is matchmaking for trade partners — present a trade both
> managers will like. Two rounds: round 1 = broad sweep (3 agents), round 2 = follow-up gaps
> flagged by round 1 (5 agents). Every memo carries per-claim confidence flags, best practices,
> antipatterns, ranked what-matters-most, counterintuitive what-doesn't-matter, follow-up gaps,
> and full source URLs.

## Round 1 — the broad sweep

| Memo | Covers |
|---|---|
| [round-1/01-matching-models-and-algorithms.md](round-1/01-matching-models-and-algorithms.md) | Elo→TinVec history, Hinge Gale-Shapley, reciprocal recommendation (RECON, LFRR), fusion functions, retrieval→ranking→re-ranking pipeline, cold start |
| [round-1/02-signals-features-feedback-loops.md](round-1/02-signals-features-feedback-loops.md) | Stated vs revealed preferences, signal taxonomy and cost-to-fake grading, outcome-label ladders (Hinge "We Met"), degenerate feedback loops, desirability scoring |
| [round-1/03-marketplace-dynamics-and-presentation.md](round-1/03-marketplace-dynamics-and-presentation.md) | Congestion/popularity bias, exposure fairness = throughput, choice overload, double opt-in, post-match funnel, pool hygiene, Roth market-design framing |

## Round 2 — follow-up deep dives

| Memo | Covers |
|---|---|
| [round-2/01-thin-markets-and-multiparty-matching.md](round-2/01-thin-markets-and-multiparty-matching.md) | Kidney exchange (cycle caps, failure-aware matching, match-run cadence), barter markets, stable-roommates non-existence at n=12, batch-vs-greedy, league simulation |
| [round-2/02-bundle-construction-and-offer-design.md](round-2/02-bundle-construction-and-offer-design.md) | Package generation pipelines (IBM/ESPN precedent), Myerson–Satterthwaite and why per-user boards are the moat, log-rolling, MESO offers, non-additive package math, fairness bands |
| [round-2/03-sparse-data-learning-and-evaluation.md](round-2/03-sparse-data-learning-and-evaluation.md) | Funnel-label cascades (ESMM, Best-of-Both α-blend), OPE for matching markets, ghost-suggestion holdouts, Thompson sampling, graded negatives, EB shrinkage, season-phase regimes; N=tiny vs needs-scale table |
| [round-2/04-closed-communities-and-fantasy-analogs.md](round-2/04-closed-communities-and-fantasy-analogs.md) | Repeated-game/acquaintance dynamics (friends negotiate worse, indirect speech, third-party judgment), babysitting-co-op/LETS liquidity lessons, KeepTradeCut loop, competitor trade-finder landscape, trade etiquette norms |
| [round-2/05-presentation-and-conversion-engineering.md](round-2/05-presentation-and-conversion-engineering.md) | Reciprocal explanations (+17pp acceptance), endorsement tiers, notification pacing benchmarks, expiry grammar, turn-state machines, patent verification sweep, small-N testing designs |

## Round 3 — gaps flagged by round 2

| Memo | Covers |
|---|---|
| [round-3/01-counteroffer-and-negotiation-loop.md](round-3/01-counteroffer-and-negotiation-loop.md) | eBay Best Offer bargaining corpus (impasse-despite-surplus rates), concession pacing, decline taxonomies, marketplace counter-offer mechanics, decline→revise→re-offer state machine for FTF |
| [round-3/02-acceptance-modeling-simulation-experimentation.md](round-3/02-acceptance-modeling-simulation-experimentation.md) | Acceptance-probability modeling (Airbnb host-accept template; the field's blind spot), league-simulator design, experimentation under interference (cluster/switchback/interleaving at tens of leagues) |
| [round-3/02a-appendix-simulation-testbeds.md](round-3/02a-appendix-simulation-testbeds.md) | Simulator deep dive: RecSim/RecSim NG calibration, Virtual-Taobao anti-overfitting, ELAS liver-allocation simulator (the template), LLM-user-simulator failure modes |
| [round-3/02b-appendix-abm-validation-calibration.md](round-3/02b-appendix-abm-validation-calibration.md) | ABM validation/calibration canon: POM pattern filters, ODD protocol, ergodicity tests, parameter-recovery experiments, MCR, reward-hacking defenses |
| [round-3/03-valuation-integrity-and-governance.md](round-3/03-valuation-integrity-and-governance.md) | Pick valuation under uncertainty (owner-conditioned pick pricing; variance-floored fairness bands), board-gaming threat model, crowdsource manipulation resistance, veto/governance calibration |

The cross-memo synthesis delivered to the operator (2026-08-16) distills these into design
principles for the trade engine; the memos are the citable source of record. Rounds were
executed 2026-08-15 (1–2) and 2026-08-16 (3).
