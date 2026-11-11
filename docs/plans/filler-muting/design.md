# Filler muting: throw-ins count for less, and never make a trade fair

**Date:** 2026-11-11 · **Status:** design, not built · **Baseline:** `origin/main` @ `8b5f076a`
· **Entry point:** operator direction, 2026-11-11 (below) · **Replaces:** the `filler` rule of
D-207 (`backend/deck_quality.py`, flag `deck.quality_filters`)

Everything here was measured offline on this laptop. The inputs were the recorded production owner
requests in the main checkout's git-ignored `data/prod-requests/` (aggregates only; no names, ids
or rosters leave that folder) and synthetic leagues. The method follows the fast-deck v2 replay
(its appendix). The scratch scripts are outside the repository. Nothing touched production. Player
and pick names in the examples are public NFL labels; values are consensus market values.

- [1. Summary](#1-summary)
- [2. Diagnosis: why padded trades passed in October](#2-diagnosis-why-padded-trades-passed-in-october)
- [3. The operator's direction and how it is read](#3-the-operators-direction-and-how-it-is-read)
- [4. Candidates](#4-candidates)
- [5. Measurements](#5-measurements)
- [6. Recommended design](#6-recommended-design)
- [7. Guardrails and interactions with the other rules](#7-guardrails-and-interactions-with-the-other-rules)
- [8. Tests that prove October's cards stay out](#8-tests-that-prove-octobers-cards-stay-out)
- [9. Parameters, tuning, validation, rollout and kill switch](#9-parameters-tuning-validation-rollout-and-kill-switch)
- [10. Open decisions](#10-open-decisions)
- [Appendix: method](#appendix-method)

## 1. Summary

**What went wrong in October.** The live engine (owner-bilateral, revision 2) never had a junk
gate. The older engines' #141 `filler_ok` was not carried over. Its market pricing counts a
small piece at roughly 55–80% of face value. Its companion search adds whichever extra piece
closes the value gap. Its fairness floor is wide (a 0.65 ratio). So the cheapest way to make a
lopsided 1-for-1 "fair" was to add a bench body or a second-round pick, and the ranker rewarded
that because the weaker side's support rises when the gap closes. In replay, **22% of everything
the engine generates is padded this way**: a small companion its side needs to reach the floor.
The 2026-10-14 rule fixed this by deleting every card with any piece below max(450, ¼ of the best
piece). Because second-round picks are worth 300–600 and the median rostered asset is about 390,
that rule rejects 55% of all generated cards. It also bans every 2nd, 3rd and 4th, and every bench
player, from ever appearing.

**Recommendation, in one sentence a manager would use:** *a throw-in can sweeten a fair trade, but
it can never be what makes the trade fair, and it only counts for a sliver of its value.* Concretely:

1. **Pricing (one function, every surface).** On a side with two or more pieces, a *throw-in* is
   a piece worth less than the **line** = max(450, ¼ × the best piece in the whole trade), except
   a first-round pick. The rest of the side (its *core*) is priced exactly as today. Each throw-in
   adds `v × (v / line)²`. A throw-in at half the line counts a quarter of its value, and one at a
   tenth of the line counts 1%. Adding a throw-in can never lower a side. That fixes a quirk of
   today's depth curve, where adding a 2nd makes an offer worth *less*.
2. **Fairness on the cores.** A card is eligible only if it clears its fairness floor **with every
   throw-in removed**, as well as with them in. A pile of small pieces therefore counts as its
   single best piece when fairness is judged, so it can never equal a better asset.
3. **Throw-ins come from the short side.** A throw-in may only sit on the side whose core is worth
   less. It sweetens a deal and never pads an overpay.
4. **The hard rule shrinks to roster filler.** The `filler` predicate becomes: drop a card if any
   **non-pick player** is worth less than 450. Picks never trip it. A real player between 450 and
   the line (for example, a 900-value WR behind a 7,000 star) is allowed and treated as a throw-in.
5. **One version per trade at the top of the deck.** Within the first 30 cards, a trade and its
   "+ a 2nd" variant do not both appear; the later one is deferred, like the repeat cap.

**Measured effect** (64 recorded requests, 13 leagues; synthetic 12/14-team leagues agree in
direction). Items 1, 2, 4 and 5 were replayed end to end; item 3's effect was measured separately
on 13 requests and is applied in the last column.

| | Today | Recommended (1, 2, 4, 5) | + short-side rule (3) |
|---|---|---|---|
| Survival (served ÷ generated) | 7.6% | 13.1% | ≈ 10.6% |
| Served deck, median (p10–p90) | 173 (108–299) | 358 (190–565) | ≈ 290 |
| Cards carrying a pick sweetener | 0% | 23.1% | — |
| Cards carrying any piece below the line | 0% | 48.1% | ≈ 36% |
| "Pile for one" (one piece for ≥ 2 pieces each below its line) | 0 | 0.1% | — |
| Cards whose core fails the floor (padding) | 0 | **0** | 0 |
| First 30: same as today's first 30 (median) | 30 | 20 | — |
| First 30: mean weaker-side support | 0.495 | 0.503 | — |
| First 30: near-duplicate pairs ("X" and "X + a 2nd") | 0 | 2 in 64 decks | — |

None of today's served cards is priced out. Fifteen of 12,354 (0.1%) fail the core test, because
the deck filter and the generator use slightly different pick values (§6.6).

## 2. Diagnosis: why padded trades passed in October

### 2.1 Which valuation the served engine uses

Production serves `owner_v2_bilateral` revision 2 (`trade_gen_bilateral_candidate.py`, selected
by `owner_bilateral_revision_enabled = 1` in production's `model_config` capture). A card's
eligibility and rank come from:

- **Price:** `trade_gen_owner._Search._package` (`trade_gen_owner.py:366-367`) →
  `trade_service.price_consensus_package` (`trade_service.py:2277-2307`) →
  `package_value_v2` (`:1690`) under `stud_tax_override("market")`, which every bilateral
  generator pins (`trade_gen_bilateral.py:471`). In market mode that is `_package_value_market`
  (`trade_service.py:1799-1880`).
- **Fairness:** `ratio = min(gv, rv) / max(gv, rv)` must reach `floor = max(fairness_threshold,
  market_floor_absolute = 0.65)` (`trade_gen_owner.py:215`, `:514-525`). Requests carry 0.5 or
  0.75, so the floor is 0.65 or 0.75. Then comes `overpay_ok` (`:526`;
  production's `overpay_adjusted = 0`, so it compares raw sums).
- **Shape:** organic cards are 1x1, 1x2 or 2x1 only (`trade_gen_owner.py:501-502`). The engine
  never builds a "four 3rds for a 1st" card unless the user pins those assets.
- **Support and rank:** each side's support is 0.45 × preference + 0.35 × market acceptability + 0.20 ×
  team plan (`trade_gen_bilateral.py:22-24`), where market acceptability =
  `clip(.5 + .5 × market_gain / (1 − floor))` (`:204-206`). The deck is ranked by the weaker
  side's support (`:422-455`), then revision 2's same-family precedence
  (`trade_gen_bilateral_candidate.py:306-376`).
- **The card's "Dynasty value swing"** is not the generator's number. The app calls
  `/api/trade/evaluate`, which prices through `trade_optimizer._consensus_packages`
  (`trade_optimizer.py:111-122`). That makes the same `package_value_v2` call with the same
  trade-wide benchmark and #427 mask, under the user's stud-tax mode (default `market`). So one
  function, `_package_value_market`, already decides both the engine's fairness and the bar most
  users see.

### 2.2 Are small pieces already discounted?

Partly, and not enough.

- **`package_weight_1..5`** (1.00 / 0.75 / 0.55 / 0.40 / 0.28, `trade_service.py:1630-1649`,
  seeded at `database.py:3575-3579`) feed only the legacy `package_value`. The bilateral engines
  never call it. They are irrelevant here.
- **The market depth curve** (`_package_value_market`): on a multi-piece side each piece counts
  `v × (floor + (1 − floor)(v / bench)^0.5)`. On the side holding the trade's best piece,
  floor = 0.70 and bench = that side's best. On the other side, floor = `package_floor_cross`
  0.40 and bench = the trade's best piece. The whole side's discount is capped at 35%
  (`package_discount_cap`). So a 300-value bench RB behind a 3,400 headliner still counts ~58% of
  face, and a 2nd ~55–65%. The curve never goes below its floor, so junk is never muted toward
  zero. With a floor of 0.05 or less the curve would also hit near-star pieces, so no setting of
  today's knobs can mute junk without repricing real two-for-ones (§4, candidate b).
- **The crown premium** adds value to elite pieces (≥ 6,000). It makes stars dearer; it does not
  make filler cheaper.
- **A quirk that matters for sweeteners:** adding *any* second piece to a side that does not hold
  the trade's best piece re-benchmarks the side's existing piece at the 0.40 cross floor. In
  replay, "Rome Odunze (3,669) + a 2027 2nd for Christian McCaffrey" priced the giving side at
  3,646, *below* Odunze alone. Under today's rule such a card is never shown. Once 2nds may
  appear, the value bar would tell a user their sweetener made the offer worse.

### 2.3 Why padding passed

1. **No filler gate in this engine.** #141's `filler_ok` (`trade_service.py:2241-2274`, knobs
   `filler_min_frac` / `asset_floor_abs`) runs in `trade_gen_v2`, `trade_optimizer` and
   `trade_gen_fit` only (`git grep filler_ok`). The owner-bilateral modules never call it.
2. **The companion search pads by construction.** Expansions add one companion to a focal pair,
   ordered by joint interest minus `cost = |gap| / gross` (`trade_gen_bilateral.py:382-403`).
   The best-ranked companion is the one that closes the market gap.
3. **Small pieces still count 55–80%,** and the floor is a 0.65 ratio. A 1-for-1 at 0.60 becomes
   "fair" with a 300-value body attached.
4. **The ranker rewards closing the gap.** Market acceptability rises with the weaker side's
   market gain, so the padded version outranks the honest one.
5. **Revision 2 keeps padded alternatives.** Revision 1 deleted a card whose companion was
   unnecessary (`trade_gen_bilateral.py:308-338`). Revision 2 instead records "avoidable
   companions" and only orders the cheaper card first
   (`trade_gen_bilateral_candidate.py:142-200`, policy `rank_efficient_first_preserve_valid_inventory`).
   A companion that improves balance by ≥ 0.025 counts as useful. Junk at 55% of face usually does.
6. **The value scale is steep.** In a typical recorded league the median rostered asset is
   worth ~390. A 2027 2nd is ~395, a 3rd ~255 and a 4th ~230, and a 1st is ~2,070. Most of every
   roster sits below 450, so there is always junk available to pad with.

Measured on the replay (64 requests, 162,959 generated cards): **22.3% of generated cards are
padded**, meaning a companion below the line without which its own side falls below the card's floor
(3.3% are padded with a pick). Calibration's "junk filler is the reason on 59% of this engine's
low cards" (D-207) is the visible face of that.

### 2.4 What today's rule actually does: three jobs in one line

`deck_quality._filler` (`deck_quality.py:57-63`) drops a card if *any* piece on *either* side is
below `max(FILLER_FLOOR 450, FILLER_FRAC 0.25 × the trade's best piece)`. It rejects 55% of
generated cards (first failing rule), and three different things trip it:

| Job | What it catches | Should it stay? |
|---|---|---|
| Padding | a small companion that makes a side "enough" (October) | Yes, and the core test (§6.2) does it exactly |
| Junk bodies | a bench player under 450 thrown in | Yes, as a hard rule (§6.4); graders call these junk |
| Small trades | a 1-for-1 or whole trade among sub-450 pieces (19% of generated cards have a best piece under 450) | Yes for players (the 450 floor); picks are covered by significance |

and, as collateral, every 2nd/3rd/4th-round pick and every player between 450 and the line
(10.5% of offending pieces in the fast-deck replay).

## 3. The operator's direction and how it is read

> "Yes, but we need to ensure we don't recreate October's issue. I think primarily this gets
> solved by having fillers' value in a trade suggestion get muted/ downgraded by more valuable
> pieces. So rather than killing the trades, ensuring 3-4 low value picks don't end up being
> graded equal to a 4th." (operator, 2026-11-11, asked whether picks may be sweeteners)

**Interpretation (ours, stated as such).** Small pieces should count for less when they sit next
to much more valuable pieces. Their value in the trade's evaluation is discounted, so that:

- (i) a pile of low-value pieces can never add up to equal one substantially more valuable asset;
- (ii) a sweetener can be present without being what makes the trade fair.

"A 4th" most likely stands for a much more valuable single piece (e.g. a 1st). **The literal
reading is covered too.** Under the core test a pile counts as its single best piece when
fairness is judged. So four 4ths (232 each) never equal one 2nd (395): the core ratio is 0.59,
below every floor. Three or four of the lowest picks therefore never grade equal to anything
better than the best of them. A trade made *only* of non-first picks never reaches the deck
anyway: significance requires a player in tier "second" or better, or a first-round pick
(`trade_significance.py:91-136`).

Both readings ask for the same property, sub-additive value for small pieces relative to the
headliner, and the design satisfies it by construction, not by tuning.

## 4. Candidates

Notation: `H` is the best single piece in the whole trade, `v` a piece's market value, and the
**line** `L = max(450, 0.25 × H)` (today's filler bar, deliberately reused). Today's market
pricing is unchanged for every piece not named.

| | Formula | Parameters | What a manager would say it means |
|---|---|---|---|
| **(a) Ratio muting** (Hill curve) | each piece on a multi-piece side × `w(r) = (1+k²) r² / (r² + k²)`, `r = v/H` | k = 0.12 or 0.20 | "The further a piece is below the star of the deal, the less it counts — even good players." |
| **(a′) Knee muting** | pieces below `L` × `(v/L)^p`, on top of today's depth factor | p = 1 or 2 | "Pieces under a quarter of the best player count for a fraction; everything else as today." |
| **(b) Reshape the depth curve** (knobs only) | today's formula with `package_floor_market` 0.35, `package_floor_cross` 0.15, `package_discount_cap` 0.65 | 3 existing knobs | "Every second piece counts for less." |
| **(c) Sweetener cap** | pieces below `L` together contribute at most 10% of the side's other value | X = 0.10 | "Small stuff can add at most a tenth." |
| **(d) Hard rule for bench players, picks muted** | (a′) + drop any non-pick player below `L` (D1), below `L` and bench (D2), or below 450 (D3) | as stated | "No junk bodies; picks can ride along at a discount." |
| **Recommended** (core + throw-ins) | core priced as today; each throw-in adds `v(v/L)²`; floor must hold on cores; D3 floor; short side only | p = 2, 450, 0.25 | "A throw-in can sweeten a fair trade but never make it fair, and counts for a sliver." |

**Worked examples** (consensus values; floor 0.65; "today" = today's pricing, then today's rule):

| Trade | Today | Recommended |
|---|---|---|
| Star 8,000 for near-star 6,400 + a 3rd (255) | 8,381 v 6,429 = 0.77, **dropped** (3rd < 2,000) | 8,381 v 6,660 = 0.79; core 0.80 → **admitted**: the 3rd adds 31, not 255 |
| Star 8,000 for four 2,000-value players | 8,640 v 5,600 = 0.648 → fails the floor | unchanged (pieces at the line are core): 0.648 → fails. The depth curve already prices four quarters at 65¢ |
| A 1st (2,070) for four 3rds | 663 → 0.32, dropped | 441 → 0.21; core 0.12 → not fair at any floor |
| A 1st for three 2nds (395) | 785 → 0.38, dropped | 855 → 0.41; core 0.19 → not fair (and needs ≥ 6 2nds before even the priced ratio passes; the core never does) |
| 4,000 + 1,500 + a 2nd for 4,200 + 1,500 (poorer side sweetens) | 0.96, **dropped** | 5,136 v 5,519 = 0.93; core 0.92 → admitted; the 2nd adds 56 |
| WR 3,000 + bench RB 300 for WR 3,400 (October's shape) | 0.90, dropped | core 0.88 is fair, but the 300 RB is a non-pick player < 450 → **dropped** by the roster floor |
| 1,000 + a 2nd for 1,800 (pick padding) | 0.62, dropped | priced 0.72, but core 1,000/1,800 = 0.56 → **not fair**: the 2nd cannot make it fair |
| 1,800 + a 600 bench player for 3,000 (player padding) | 0.65, dropped | priced 0.73, core 0.60 → **not fair** |
| 3,000 + a 2nd + a 3rd for 3,400 (two throw-ins) | 0.96, dropped | 3,108 v 3,400 = 0.91; core 0.88 → admitted |

Candidates (a)–(d) on the same examples: (a) Hill k=0.2 prices "star for four 2,000s" at 0.41
(it mutes real players too). (b) and (c) leave "a 1st for six 2nds" fair (0.76). (a′) p=2
multiplies through today's re-benchmark and so prices the 2nd-sweetened Odunze offer below
Odunze alone.

## 5. Measurements

### 5.1 Candidate comparison (63 requests, 13 leagues)

Post-hoc (PH) = today's generated inventory, re-judged. Regenerated (RG) = the generator re-run with
the pricing change inside it. Survival = served ÷ generated. "Padding" = a sub-line companion
without which its side falls below the floor (October's pattern, judged on today's pricing).

| Scenario | Served | Survival | Pick sweetener | Bench < line | Padding | Pile for one | Top-30 same as today | Top-30 weaker support |
|---|---|---|---|---|---|---|---|---|
| Today | 12,174 | 7.6% | 0% | 0% | 0% | 0% | 30 | 0.495 |
| No filler rule at all | 47,738 | 29.7% | 13.8% | 56.0% | 7.8% | 6.7% | 11 | 0.505 |
| (b) depth knobs | 46,802 | 29.1% | 13.6% | 55.8% | 7.0% | 6.3% | 11 | 0.505 |
| (c) cap 10% | 47,093 | 29.3% | 13.7% | 55.7% | 6.7% | 6.7% | 11 | 0.504 |
| (a) Hill k=0.20, PH / RG | 46,011 / 44,844 | 28.6 / 29.9% | 13.5% | 55.7% | 6.5 / 6.0% | 6.2% | 11 / 10 | 0.505 / 0.500 |
| (a′) knee p=1, PH / RG | 45,698 / 47,413 | 28.4 / 26.1% | 13.1% | 54.3% | 4.3 / 4.1% | 3.6 / 6.9% | 11 / 12 | 0.503 / 0.501 |
| (a′) knee p=2, PH / RG | 44,401 / 46,632 | 27.6 / 28.0% | 12.5% | 53.3% | 2.5 / 2.7% | 1.6 / 5.5% | 11 / 12 | 0.501 / 0.503 |
| (d) D1: knee + kill players < line | 17,475 | 10.9% | 30.3% | 0% | 0.9% | 0.3% | 24 | 0.499 |
| (d) D2: … bench players < line | 20,864 | 13.0% | 25.6% | 0% | 1.6% | 0.4% | 20 | 0.500 |
| (d) D3: knee p=2 + kill players < 450, RG | 23,030 | 13.8% | 22.8% | 15.4% | 0.8% | 0.2% | 19 | 0.501 |
| D3 + kill padding (PH) | 23,056 | 14.3% | 22.3% | 15.9% | **0%** | 0% | 19 | 0.503 |

Read-outs:

- **Muting alone (a, a′, b, c) does not stop junk.** Without a hard floor, 53–56% of served cards
  carry a sub-line bench player, and most of them are junk-for-junk small trades among sub-450
  players that today's absolute 450 floor removes. Muting addresses padding (job 1), not junk
  bodies or small trades (jobs 2–3).
- **No smooth muting reaches zero padding.** A continuous curve leaves pieces just under the line
  near full value, so they can still tip a trade sitting a few points under the floor. Only a
  discrete test, judging fairness without the throw-ins, gets padding to 0; it costs ~1.5% of the
  deck.
- **Post-hoc tracks regeneration closely** (D3: 23,383 PH vs 23,209 RG with knee p=1), so the
  pricing change matters little for *which* cards survive and mostly for how they are priced and
  ranked.

### 5.2 The recommended design end to end (64 requests, 13 leagues)

Regenerated with the recommended pricing and core test inside the generator; roster floor (D3)
as the predicate; the rest of today's downstream (significance, presentment, breakup, redundant,
repeat cap at 3 of 30) unchanged.

| | Today | Recommended |
|---|---|---|
| Generated inventory | 162,959 | 180,860 (+11%) |
| First failing rule, share of generated: significance / breakup / filler / redundant / pass | 19.8 / 9.7 / 55.3 / 7.5 / 7.6% | 28.9 / 4.9 / 40.2 / 12.9 / 13.1% |
| Served, total (median per request; p10–p90; min–max) | 12,354 (173; 108–299; 77–501) | 23,762 (358; 190–565; 83–784) |
| Served ÷ today's served, per request | 1 | median 1.84 (p10 1.44, p90 2.50) |
| Decks under 30 cards | 0 | 0 |
| Served cards with: a pick below the line / a bench player 450–line / a starter below the line | 0 / 0 / 0 | 23.1% / 16.0% / 9.0% |
| Pieces below the line, by kind (served) | none | 4,204 2nds, 793 3rds, 423 4ths, 90 1sts behind a much bigger star; 3,802 bench and 2,135 starter players |
| Two or more pieces below the line on one side | 0 | 0.1% |
| "Pile for one" (one piece for ≥ 2 pieces each below its line) | 0 | 0.1% |
| A card whose best piece is under 450 | 0 | 0 |
| Cards whose cores fail the floor (padding) | — | **0** (guard re-check: 0 drops) |
| Shapes 1x1 / 1x2 / 2x1 | 28 / 26 / 45% | 15 / 39 / 46% |
| First 30, with variant cap: pick sweetener / any piece below the line | 0 / 0 | 11.8% / 27.3% |
| First 30: overlap with today's first 30 (median, p10–p90) | 30 | 20 (13–23) |
| First 30: cards that were somewhere in today's deck | 100% | 73% |
| First 30: mean weaker support / partners / distinct assets per deck | 0.495 / 9.7 / 33.5 | 0.503 / 9.9 / 36.8 |
| First 30: "X" and "X + a throw-in" both present (pairs, 64 decks) | 0 | 230 without the variant cap, **2 with it** |
| Today's served cards that the new pricing prices out | — | 0 |
| Today's served cards that fail the core test | — | 15 of 12,354 (0.1%; two-market mismatch, §6.6) |

Synthetic leagues (12-team seeds 7 and 11, 14-team seed 7; no production data): served 1.40×
today (median 521 → 831), 24.4% of served cards carry a pick sweetener, padding 0 by the core
test, and the first 30 share 18 of 30 with today's.

**Short-side rule (13 requests, the latest per league).** Of 4,314 served cards, 2,098 carry a
throw-in, and **813 of those (39%) carry it on the side whose core is already worth more**
("Kyren Williams + a 2028 2nd for Quinshon Judkins", where the giver already overpays). In
the first 30 (variant cap on), that is 9 of 390 cards. The rule removes ~19% of the deck and
almost nothing at the top.

### 5.3 Examples of newly admitted cards (first 30, recommended)

- Harold Fannin (TE, 2,232) for a 2027 1st + a 2028 2nd: 2,456 v 2,502, 0.98.
- Bucky Irving (RB, 1,698) + a 2027 2nd for Harold Fannin (TE, 1,827): 1,997 v 2,009, 0.99.
- A 2027 1st for Tucker Kraft (TE, 2,096) + a 2029 2nd: 2,308 v 2,231, 0.97.
- Chris Olave (WR, 4,334) for Breece Hall (RB, 3,802) + Jaylen Warren (bench RB, 869): 0.99.
- Jaxon Smith-Njigba (7,866) for Jahmyr Gibbs (6,736) + Travis Etienne (bench RB, 1,647): 0.98.
- Jalen Hurts + a 2029 2nd for Caleb Williams (superflex): 0.97.

And October's pattern, now not fair (core below the floor), from the same replay:
"MarShawn Lloyd (568) for Tyrone Tracy (293) + Ray Davis (261)" (today's pricing 0.80), "a
bench WR (226) + a 2028 4th for Eli Raridon (414)" (0.83), and "Zach Charbonnet for two bench
QBs" (0.81). Each is a small piece making a side "enough".

### 5.4 What cannot be measured offline

- **Whether managers like sweetened cards.** No graded or decided history exists for a card with a
  2nd attached, because none has ever been served since 2026-10-14. Calibration is the instrument (§9).
- **Decline-window suppression, dispositions, likes-you injection** (DB-backed; not replayed),
  as in the fast-deck replay. Suppression may already treat "X + a 2nd" as a near-duplicate of a
  declined "X". If so, production thins the variants further.
- **Production timing.** The generated inventory grows 11%, and the admitted inventory roughly
  doubles. Under rules-first construction that inventory is built completely (median ~196 cards
  today), so construction cost grows. It has to be measured with the served-deck replay tool.
- **The calculator and card rendering** of a new adjustment row (§6.5).
- **16–32 team leagues** (no recorded requests; synthetic only to 14).

## 6. Recommended design

### 6.1 Pricing: core + throw-ins (`trade_service._package_value_market`)

For a side with two or more pieces, in market stud-tax mode, with the knob `throwin_mute_power`
> 0 and the flag on:

```
H      = max(v_max, max(values))          # v_max is already the trade-wide best piece
line   = max(throwin_line_floor, throwin_line_frac * H)          # 450, 0.25
throw  = [v for v, exempt in side if v < line and not exempt]    # exempt = #427 first-round mask
core   = the other pieces; if none, the side's single best piece
value  = today's _package_value_market(core, other_values, v_max, core_exempt)
         + sum(v * (v / line) ** throwin_mute_power for v in throw)
```

- A side with no throw-ins is priced **exactly as today**. That covers every card served today:
  measured 0 of 12,354 change eligibility on price.
- Single-piece sides are never throw-ins, which matches today's "a single-asset side is never
  depth-discounted".
- First-round picks stay at face (#427) and are never throw-ins.
- The crown credit is computed on the core, as today.
- **Monotone:** adding a throw-in adds `v(v/line)² ≥ 0` and leaves the core untouched, so an
  offer never gets worse by adding a sweetener. That retires the re-benchmark quirk (§2.2) for
  throw-ins.
- `heavy` and `off` modes are untouched (both are per-user calculator settings; engines always
  pin `market`).

Because this lives in the one function both the engine and `/api/trade/evaluate` call, the card's
"Dynasty value swing", the calculator, the generator's fairness and support, revision 2's
term-efficiency audit, `overpay_ok` (when `overpay_adjusted` ≥ 1), the likes-you injector and the
legacy consensus surfaces all move together. Nothing can show "You win by +N" on one scale while
the engine judged it on another. The legacy engines keep their own `filler_ok` (#141) and are not
otherwise affected.

### 6.2 Fairness on the cores (`trade_gen_owner._Search.evaluate`)

Right after the market floor (`trade_gen_owner.py:514-525`), when the flag is on and either side
holds a throw-in:

- price the two cores alone with the same `_package`;
- **reject `market_floor_core`** if `core_ratio < floor`;
- **reject `throw_in_on_long_side`** if a side holding a throw-in has the larger core value.

This is an eligibility change inside the generator. All bilateral revisions inherit it (1, 2 and
dark 4; owner-v1 too, unserved). It is not a deck predicate, because it needs the request's
fairness floor and the generator's own market. Page-first search bounds never predict
eligibility (`trade_first_page.py` module docstring), so they need no change for this part.

### 6.3 Which valuation applies where

| Where | Today | Recommended |
|---|---|---|
| Engine eligibility (floor) | priced ratio | priced ratio **and** core ratio (+ short side) |
| Engine support / rank | priced (throw-ins at 55–80%) | priced (throw-ins at `(v/line)²`) |
| Card value swing, calculator | priced via `/api/trade/evaluate` | same function, so the same numbers |
| Calculator "fair" verdict (`_fairness_v3`) | priced ratio | priced ratio (decision 4: also show "fair only with throw-ins") |
| Deck predicate (`filler`) | any piece < line | any non-pick **player** < 450 |
| Deck order | repeat cap | repeat cap + variant cap |

### 6.4 The predicate: `filler` becomes roster filler (`deck_quality.py`)

```
def _roster_filler(give, receive, market, is_pick):
    return any(market(a) is not None and market(a) < FILLER_FLOOR and not is_pick(a)
               for a in (*give, *receive))
```

`filter_deck` (and `card_rule` in the rules-first build) calls `_roster_filler` instead of
`_filler` when the flag is on. It gains an `is_pick` callable, which the worker builds from
`trade_service.is_pick_asset(players_dict.get(pid))`. Positions alone are not enough, because
generic picks carry a fake position. `_filler` stays for flag-off byte identity and for
`eval/bdk_audit.py`.

**How this fits the rules-first build** (`feat/deck-rules-first`, `deck_rules.DeckRules` →
`deck_quality.card_rule`): exactly **one predicate is replaced** (`_filler` → `_roster_filler`;
still a pure function of terms + request inputs, so it can be decided before pricing and inside
the page search's screen) **plus one pricing change** (§6.1) and **one generator eligibility
change** (§6.2), both upstream of the rules. `DeckRules.VERSION` and `DECK_PIPELINE_VERSION` bump.
The downstream guard copy of the predicate must still remove zero cards. The variant cap (§7.2)
is order-dependent, so it lives downstream next to the repeat cap, as rules-first requires.

### 6.5 Calculator itemisation (`server._evaluate_adjustments`, `server.py:1040-1083`)

Add a row `{"key": "throw_ins", "label": "Throw-ins", "amount": <priced − priced with
throwin_mute_power 0>, "why": "Small pieces next to a much bigger one count for only part of
their value."}` so a user sees why a 2nd adds ~60, not 395. `mobile/src/api/calc.ts:100` types
`key` as a string, and labels come from the server. Rendering it needs a TestFlight check, not an
app change. `docs/api-reference.md` gains the key.

### 6.6 One market for the line

The deck filter prices with `elo_to_value(seed)`; the generator with
`make_consensus_value_fn` (owned picks priced by market slot). They disagree on some picks. That
mismatch is the source of the 15 served cards (0.1%) that would newly fail, and of the 0.1%
residual "padding" in the deck-market metric. The line in §6.1–6.2 uses the generator's
market (the pricing function's own values). The predicate uses the deck market only for the
absolute 450 player floor, where the two markets agree, because they differ only on picks.

### 6.7 Page-first bounds (`trade_first_page._Bounds`, `:238-306`)

Muting only lowers a side's price, so upper bounds stay admissible. Lower bounds must drop:

- `side_price(values, other_max)` knows the side's values and the other side's best piece, so
  it can compute `H`, the line and the core/throw-in split exactly: `low = today's low(core) +
  Σ v(v/line)²`.
- `price_range(naive, count)` (used by `window_terms`) does not know the values. For
  `count > 1` its low becomes `naive × keep / count` when muting is on. The core contains the
  side's best piece (≥ naive / count) and is priced ≥ keep × itself. This widens the companion
  window's upper edge (roughly ×2 for 2-piece sides). The cost must be re-measured with
  `first_page_bench`; companions that large are rare.
- `_Bounds.envelope` gains the knob's validity condition (`0 ≤ throwin_mute_power`,
  `0 ≤ throwin_line_frac ≤ 1`).

`test_bounds_are_admissible_over_the_exhaustive_universe` and
`test_market_price_envelope_contains_every_package_price` must run with the flag on (§8).

## 7. Guardrails and interactions with the other rules

### 7.1 Hard rules that remain

| Rule | Why it stays hard |
|---|---|
| **Roster floor:** no non-pick player under 450 | Junk bodies cost a roster spot. They were 80% of today's offending pieces and the bulk of graders' "junk filler". Without it 56% of served cards carry one (§5.1). |
| **Core fairness** | The only measured way to make padding exactly zero (§5.1). |
| **Short side** | 39% of throw-ins otherwise pad an overpay (§5.2). |
| **Organic shape ≤ 2x1** (existing) | Bounds piles to one throw-in per side organically. Pinned searches can be larger; the core test covers them. |
| **Significance** (existing) | A trade made only of throw-ins and non-first picks never reaches the deck. |

There is no separate "maximum throw-ins per side": the core test makes every additional throw-in
worthless for fairness, and organic shapes allow one.

### 7.2 Interactions

- **Breakup** (best piece received < 70% of the best given): unchanged. Throw-ins never change
  either side's best piece.
- **Redundant QB/TE:** unchanged. It already drops most bench-QB throw-ins (a team rarely lacks a
  QB worth 70% of a 600 QB), which is why "redundant" rises as a first-failing rule (7.5% →
  12.9% of generated).
- **Repeat cap** (no asset in > 3 of the first 30; the rules-first branch moves it to 5): a team's
  2nd can appear in many cards, and the cap spreads them. Add the **variant cap** beside it:
  within the first 30, at most one card per *core trade* (same partner and cores). Later variants
  are deferred to just after the window in their order. Protected cards hold their positions.
  Measured: near-duplicate pairs in the first 30 drop from 230 to 2 across 64 decks. It also raises
  distinct assets (35.3 → 36.8 per deck) and partners (9.5 → 9.9).
- **Revision 2's precedence:** unchanged. With muted throw-ins a sweetener rarely improves balance
  by 0.025, so it is "avoidable" unless the recipient benefits (known target, declared target, or
  a rebuilder's future portfolio at ≥ 5% of the focal value,
  `trade_gen_bilateral_candidate.py:22, :127-140`). So the plain card precedes its sweetened
  sibling. That is the intended meaning of an honest sweetener: it goes to a team that wants it.
- **Revision 4** (dark; owned-pick premium by outlook, pay-picks tie-breaker) will now see
  throw-in picks. It must be re-measured with this on before it is enabled.
- **Value core** (`backend/value_core/`, dark): keeps its own hard filler rule. D-207's "every
  engine shares one definition of a bad card" stops holding while the value core is off. Port it
  if the value core is revived.

## 8. Tests that prove October's cards stay out

Each test names the sabotage it must fail under (revert the line, watch it go red, restore).

| Test (file) | Asserts | Sabotage that must fail it |
|---|---|---|
| `test_throw_in_pricing.py::test_no_throw_in_prices_byte_identical` | flag on vs off, every package with no piece below the line (randomised over the recorded-value scale + the arm-A fixture packages) prices identically | mute every piece on multi-piece sides (not just those below the line) |
| `::test_adding_a_throw_in_never_lowers_a_side` | price(side + t) ≥ price(side) for t < line, both stud sides | price the whole side through today's depth curve (re-benchmark returns) |
| `::test_pile_never_equals_a_better_piece` | 1st vs N 2nds / N 3rds / N 4ths for N = 2…10, and 2nd vs N 4ths: core test rejects at floors 0.65 and 0.75 | drop the core test (N = 6 2nds passes on price) |
| `::test_operator_examples` | the nine §4 examples, exact values and verdicts | `throwin_mute_power` read as 1 |
| `test_trade_gen_bilateral_throw_ins.py::test_octobers_padded_card_is_not_generated` | a fixture league where a 1-for-1 at 0.60 can be padded by a 300 bench RB or a 2nd: flag on, no generated card has core ratio < floor; flag off, the padded card is generated (proves the fixture bites) | remove `market_floor_core` |
| `::test_throw_in_only_from_the_short_side` | a sweetener on the richer core side is rejected `throw_in_on_long_side` | flip the comparison |
| `::test_honest_sweetener_is_generated` | a fair 1x1 for a rebuilding partner with a 2nd available: the "+ 2nd" card is generated and ranks after the plain card | kill all throw-ins (today's rule) |
| `test_deck_quality.py::test_roster_filler_drops_only_sub_450_players` | 300 RB dropped; 2nd / 3rd / 4th / generic picks kept; 900 WR behind 7,000 star kept | revert to `max(450, 0.25 H)` (the 900 WR fails) or drop the 450 floor (the 300 RB passes) |
| `test_deck_quality.py::test_variant_cap_defers_the_second_version` | "X" and "X + 2nd" never both in the first 30; deferred order kept; protected cards hold position | key the cap on full terms |
| `test_trade_first_page.py` (existing two envelope/admissibility tests, parametrised flag on) | bounds admissible with muting | leave `side_price` low unmuted |
| `test_throw_in_pricing.py::test_card_swing_equals_engine_price` | `/api/trade/evaluate` give/receive equal the proof's `market.give/receive` for a sweetened card | mute only inside the generator |
| `test_deck_pipeline_digest.py`, `test_bakeoff_arm_a_golden.py` | flag off: deck digest and arm-A golden byte-identical | read the knob with the flag off |

Plus the replay as an operator check (rules-first's planned `backend/eval/served_deck_replay.py`):
flag on vs off over the recorded requests, reporting the §5.2 table. Pass criteria: padding = 0,
pile-for-one ≤ 0.2%, no card with best piece < 450, and decks no thinner than today.

## 9. Parameters, tuning, validation, rollout and kill switch

| Key | Kind | Value | Evidence / meaning |
|---|---|---|---|
| `deck.throw_in_muting` | flag (`config/features.json`, code default false) | off → on after §9 validation | gates §6.1–6.4 and the variant cap together; off is byte-identical |
| `throwin_mute_power` | `model_config` float | **2.0** | p = 2 halves the padding p = 1 leaves (2.5% vs 4.3%, §5.1). Under the core test p only sets how much a sweetener moves value and rank. 0 = no muting (throw-ins at face, core test still on) |
| `throwin_line_frac` | `model_config` float | **0.25** | today's `FILLER_FRAC`; graders accepted it in October |
| `throwin_line_floor` | `model_config` float | **450** | today's `FILLER_FLOOR`; the roster floor reuses `FILLER_FLOOR` itself |

Seed all three in `database._MODEL_CONFIG_DEFAULTS` and `trade_service._DEFAULT_CFG`. Pin them in
`bakeoff_profiles.MODEL_A_PROFILE` (power 0), and pin the flag off in the bake-off harness, as
`deck.quality_filters` is. Rows in `docs/config-reference.md`; "throw-in" and "core" in
`docs/glossary.md`. Tuning: `PUT /api/admin/config/<key>` re-runs `reload_config()`. A higher
power mutes harder; a higher fraction treats more pieces as throw-ins.

**Validation before serving.** Run a blind Calibration round with two arms: *current* (today's
filler rule) and *throw-ins* (this design), each over the same leagues, Yes/No grading (D-208).

- Success: the throw-ins arm's would-send rate is no lower than current's.
- Its `junk_filler` tag rate is no higher.
- `too_small` does not rise.
- Report the would-send rate on cards with a pick sweetener separately.

The offline acceptance eval cannot judge this: no logged outcome exists for a sweetened card.

**Rollout.**

1. Build dark (flag off) and get CI green. Run the replay (§8) at flag on.
2. Calibration round.
3. On for everyone. Watch the job log's `quality_filters` counts: `filler` falls from ~55% to
   ~40% of generated, and `deferred` rises with the variant cap. Watch the served-deck size
   (about 1.5–1.8× today) and construction time.

**Kill switch.** Set `deck.throw_in_muting` false and `POST /api/feature-flags/reload`. That
restores today's pricing, eligibility, filler rule and deck order byte for byte. To mute harder
without turning it off, raise `throwin_mute_power`.

**Build size.** About 250–350 lines of production code: `_package_value_market` split ~40;
generator core / short-side checks ~30; `deck_quality` predicate, `is_pick` plumbing and the
variant cap ~60; page-first bounds ~40; calculator row ~15; knobs, flag and fixtures ~30. About
400 lines of tests. Docs: config-reference, glossary, api-reference, architecture, ADR-028
addendum, D-entry. Roughly two builder-days, most of it the bound proofs and parity runs. It is
best done on top of the rules-first branch, which owns `card_rule`.

## 10. Open decisions

1. **Adopt the rule as stated** ("a throw-in can sweeten a fair trade, never make it fair; it
   counts `(v/line)²`")? *Recommended: yes.* It is the only option measured to get padding to 0
   while letting picks back in.
2. **Keep the hard floor for players under 450?** *Recommended: yes.* Picks are freed; real
   players between 450 and the line are allowed as throw-ins. Freeing bench players too (no
   floor) brings back 56% junk-carrying decks.
3. **Throw-ins only from the short side?** *Recommended: yes.* It cuts ~19% of the deck (39% of
   throw-in cards pad an overpay) and changes 9 of 390 first-30 cards.
4. **Calculator "fair" verdict:** also apply the core test, showing "fair only with throw-ins"? *Recommended: yes*, so the calculator never
   calls fair a trade the engine would not suggest. The values themselves already agree by
   construction.

Also for the operator's awareness, not a decision here: the repeat cap's 3→5 change on the
rules-first branch was not modelled. Replay used 3.

## Appendix: method

- **Inputs:** the recorded owner requests in the main checkout's git-ignored
  `data/prod-requests/`. The candidate comparison (§5.1) used 63 of them: up to 5 per league,
  spread over time, 13 leagues. The end-to-end run (§5.2) used the same 64-request subset with the
  last request included. The short-side measure used the 13 latest requests, one per league.
  Production's `model_config` capture and this branch's `config/features.json` were used. Each
  request was rebuilt as the fast-deck replay rebuilds it: a fresh interpreter,
  `PYTHONHASHSEED=0`, network blocked, a private scratch SQLite database.
- **Generator:** `trade_gen_bilateral_candidate.generate_bilateral_trades` (revision 2), the full
  solve. Candidates were applied by patching `trade_service._package_value_market` (pricing) and
  `trade_gen_owner._Search.evaluate` (core test) in the scratch process only. A sanity check
  re-priced 400 cards per request with the patch inert: 0 mismatches against the proofs.
- **Downstream:** significance (discovery, tier "second", first-round picks allowed),
  `trade_bilateral_presentment.present`, `deck_quality.filter_deck` with the filler predicate
  swapped per scenario, market = `elo_to_value(seed)`, lineup slots as in the fast-deck replay,
  repeat cap 3/30. Not replayed: decline-window suppression, dispositions, likes-you /
  revised-offer injection.
- **Classification:** "below the line" = market < max(450, 0.25 × the card's best piece) on the
  deck market. Pick vs player by `is_pick_asset`. Starter vs bench by a greedy best-value lineup
  of the owner's roster in the league's slots.
- **Padding:** a below-the-line piece on a side with ≥ 2 pieces, without which (today's pricing)
  that side is worth less than floor × the other side.
- **Synthetic:** `backend/eval/synthetic_league.build` 12 teams (seeds 7, 11) and 14 teams (seed
  7), 1QB PPR, default slots.
