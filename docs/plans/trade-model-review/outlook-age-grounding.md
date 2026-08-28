# Outlook × age × pick-flow — grounding memo for the plan

> **Purpose:** measured + code-verified inputs for the "mix outlook into the engines / add age
> bias" plan (operator direction, 2026-08-27, responding to the review's H1/H3/H7 findings).
> Data: the 2026-08-27 prod mirror ([data-readout-2026-08-27.md](data-readout-2026-08-27.md)
> §Provenance). This memo states facts; the plan argues design.

## Contents

- [What the operator asked for](#what-the-operator-asked-for)
- [Finding 1 — consensus already encodes age, strongly](#finding-1--consensus-already-encodes-age-strongly)
- [Finding 2 — user boards lean slightly AGAINST consensus's age curve](#finding-2--user-boards-lean-slightly-against-consensuss-age-curve)
- [Finding 3 — pick flow is currently anti-intent by outlook](#finding-3--pick-flow-is-currently-anti-intent-by-outlook)
- [Finding 4 — outlook coverage is thin on declarations](#finding-4--outlook-coverage-is-thin-on-declarations)
- [Finding 5 — reordering alone never fixed pick flow: the inversion predates the 08-20 flip](#finding-5--reordering-alone-never-fixed-pick-flow-the-inversion-predates-the-08-20-flip)
- [Finding 6 — the 08-20 flip-off experiment's metric, read out at last](#finding-6--the-08-20-flip-off-experiments-metric-read-out-at-last)
- [The two behavioral facts to reconcile](#the-two-behavioral-facts-to-reconcile)
- [Dark machinery inventory](#dark-machinery-inventory)

## What the operator asked for

Verbatim (2026-08-27): *"H1 speaks to mixing in the outlook into the engines. And ensuring that
users get more picks offered and give up picks less if they are rebuilding or tanking. Let's plan
out adding age bias (although there should be some implicitly added by the consensus values so
that may be what speaks to what you're seeing on consensus vs. divergence)."*

Two asks: (1) outlook-conditioned pick FLOW — rebuilders/tankers should be offered picks and asked
to give them up less; (2) an age bias plan, with the stated suspicion that consensus already
carries age. Both suspicions are measured below and both are confirmed.

## Finding 1 — consensus already encodes age, strongly

**measured** (latest 1qb snapshot 2026-08-28, top-48 per position by value, median consensus value
per age band within position):

| Pos | u23 | 23–26 | 27–29 | 30+ |
|---|---|---|---|---|
| QB | 226 (n=3) | 302 | 348 | 289 |
| RB | 2,595 | 2,310 | **755** | 2,804 (n=2 — CMC-type outliers) |
| WR | 3,034 | 3,531 | 3,730 | **1,302** (n=2) |
| TE | 905 | 510 | 280 | 332 |

The RB cliff at 27 and the WR cliff at 30 are already in the prices the engine uses. QBs age
gracefully in consensus too. **Any additional flat app-side age curve would double-count this.**
(The operator's parenthetical is confirmed.)

## Finding 2 — user boards lean slightly AGAINST consensus's age curve

**measured.** For every (user, league, format) board with ≥50 co-ranked players: z-score personal
Elo and consensus Elo over the co-ranked set, position-controlled, mean Δz per age band
(+ = user rates the band ABOVE consensus):

| Band | n | mean Δz |
|---|---|---|
| u23 | 968 | **−0.080** |
| 23–26 | 5,487 | −0.001 |
| 27–29 | 2,475 | +0.018 |
| 30+ | 1,736 | +0.023 |

Direction is consistent across 7 of 8 boards (u23 negative on 7; 30+ positive on 6). Users are
*less* rookie-feverish than consensus and marginally kinder to vets — i.e. the market's youth
premium already overshoots these users' stated values. **An app-side global vet discount would
fight both consensus and the users' own boards.** This is also a live partial explanation for H7
(consensus-basis cards outperforming divergence): personal boards deviate from consensus most on
young players, in the *negative* direction — so divergence cards sourced from those deviations
skew toward exactly the give-youth/get-vet arbitrage users then decline on the swipe surface.

## Finding 3 — pick flow is currently anti-intent by outlook

**measured** (served non-ghost deck cards with assets, viewer's *declared* outlook):

| Viewer outlook | n served | viewer GIVES pick | viewer RECEIVES pick |
|---|---|---|---|
| championship | 5,447 | 15.5% | 19.1% |
| contender | 4,260 | 36.3% | 20.2% |
| **rebuilder** | 531 | **43.9%** | **11.1%** |

The one declared rebuilder is asked to GIVE picks on 44% of cards and offered picks on 11% — the
exact opposite of the operator's intent. (Mechanism hypothesis for the plan: rebuilders hold more
pick inventory, so a delta-maximizing search finds their picks as give-currency; flat far-first
pricing [D-079/D-161] makes those picks the cheapest fair-looking filler.)

Like-rates agree with the intent (small n, direction only):

| Cut | Like-rate |
|---|---|
| contender × receives pick | 34/74 = 46% |
| contender × gives pick | 20/108 = 19% |
| championship × no pick | 53/107 = 50% |
| championship × receives pick | **3/35 = 9%** |
| championship × gives pick | 1/10 = 10% |

Championship viewers don't want picks in either direction; contenders accept receiving them and
hate giving them. Rebuilder decided-n is too small to read — but the served-mix inversion alone is
the defect.

## Finding 4 — outlook coverage is thin on declarations

**measured:** 13 `league_preferences` rows: 4 championship, 7 contender, 1 not_sure, **1
rebuilder**. Any outlook-conditioned behavior reaching most decks must ride *inferred* outlook
(`trade.outlook_infer`, live) with declared outlook as the override — and the plan must handle
`not_sure`/unresolved without weirdness.

## Finding 5 — reordering alone never fixed pick flow: the inversion predates the 08-20 flip

**measured.** `trade.outlook_direction` (#175) — the only outlook→pick-flow scorer in the codebase
— was LIVE from the deck spine's start (2026-07-27) until 2026-08-20. Served pick-direction mix by
declared outlook, split at the flip:

| Viewer outlook | dir ON (<08-20) | dir OFF (≥08-20) |
|---|---|---|
| rebuilder | n=138: gives 47.1% / receives **6.5%** | n=393: gives 42.7% / receives 12.7% |
| contender | n=1,616: gives 26.3% / receives 31.9% | n=2,644: gives 42.4% / receives 13.0% |
| championship | n=901: gives 16.5% / receives 25.0% | n=4,546: gives 15.3% / receives 17.9% |

The rebuilder inversion (asked to GIVE picks ~4–7× more than receive) existed **in both regimes** —
a composite reorder multiplier cannot overcome the generation-level inventory effect (rebuilders
hold picks, so the delta-maximizing search finds their picks as give-currency, and flat far-first
pricing makes them the cheapest fair-looking filler). The contender mix was healthier under dir ON,
but the 08-24 knob bundle and interleave confound that comparison. **Design consequence: the
operator's pick-flow intent needs generation-level treatment (pool construction / sweetener
direction / deck quota), not only a reranker.**

## Finding 6 — the 08-20 flip-off experiment's metric, read out at last

**measured.** The 2026-08-20 flip-off was recorded as "experiment #1 — watch `fit_outlook`
pass-reason share" (CHANGELOG), and that share was never read out until now. `fit_outlook` share of
all layer-2 pass reasons: **dir ON (pre-08-20): 57/177 = 32.2%** · **dir OFF (post-08-20): 25/166 =
15.1%**. Time-confounded (QB recompression 08-21, D-159 bundle + interleave 08-21/24, taste-vector
learning, cohort drift) — but at face value the metric moved *against* the flag: window-mismatch
passes did not rise when direction turned off; they halved. Re-lighting #175 as-shipped cannot cite
its own experiment as support. Any re-light should be graded offline first (it is a pure reranker —
exactly what the F8 replay harness in `backend/eval/` evaluates) and/or redesigned per Finding 5.

## The two behavioral facts to reconcile

The plan has to hold these together:

1. **On boards** (Finding 2): users rate young players *below* consensus.
2. **On swipes** (readout H3): users *like receiving* u23 (47.8%) and hate receiving 30+ (15.0%),
   monotone, and like shipping vets.

These are not contradictory — one is a pricing opinion, the other is an acquisition appetite
(younger = longer runway, resale liquidity, the same reason they hoard far firsts at 9.3%
give-like). The design implication: the appetite belongs in **presentment/exposure and
window-conditioning** (what to offer whom), not in a global **price** edit (which the boards say
would be wrong). The dark `outlook_blend` is precisely a window-conditional value tilt; the taste
layer already learns per-user age appetite. What has no owner today is pick-flow direction.

## Dark machinery inventory

Code-verified inventory with exact curves/knobs: appended by the code-map pass — see
[outlook-age-code-map.md](outlook-age-code-map.md). Summary from
[current-state.md](current-state.md): `trade.outlook_blend` (age×window value multiplier, both
sides, dark), `trade.outlook_direction` (#175 rebuilder age-gap rule + deck weighting, dark),
`trade.outlook_net_firsts` (dark), `trade.outlook_composite` (dark), `trade.outlook_infer` (LIVE),
`trade.lanes` (LIVE, labels), R5's outlook read (LIVE), gen_v2 `youth_heavy` tag (dark).
