# Arm-B engine audit — adjudicating external review claims 5 and 6

> **Purpose:** verify, on `origin/main` at `16d277f`, two claims from an external review of the
> arm-B (live) trade engine. This is a **verification memo**. No engine behaviour, flag or knob was
> changed by the work it records — in particular `pick_year_decay_r1` was not touched.

**Date:** 2026-08-19
**Base:** `origin/main` @ `16d277f5c12a8d1c36b36534b74ac1cabe0df0a3`
**Arm under review:** `bakeoff_runner.ARM_CURRENT` = `"current"` = arm **B** = the live v2/v3 engine
(`backend/bakeoff_runner.py:111-126`). Arm A is the pinned `MODEL_A_PROFILE` baseline; arm C is
`gen_v2`.
**Prod evidence:** read-only, `SET TRANSACTION READ ONLY`, `SELECT` only. 8,617 `deck_impressions`
rows spanning 2026-07-27 → 2026-08-19 18:15 UTC; 2,881 of them carry a populated `assets_json`
(the column post-dates the older rows), which is the denominator for every asset-level number below.

## Contents

- [Verdict summary](#verdict-summary)
- [Live knob and flag state](#live-knob-and-flag-state)
- [Claim 5 — picks are one number on all three boards](#claim-5--picks-are-one-number-on-all-three-boards)
- [Adjudicating the D-079 collision](#adjudicating-the-d-079-collision)
- [Claim 6 — "fairness" is consensus, not min(user, partner)](#claim-6--fairness-is-consensus-not-minuser-partner)
- [Prod measurements](#prod-measurements)
- [What strengthens and what weakens the reviewer](#what-strengthens-and-what-weakens-the-reviewer)

## Verdict summary

| # | Sub-claim | Verdict |
|---|---|---|
| 5a | Owned picks injected with one bridged Elo onto seed, user and opponent maps | **CONFIRMED** |
| 5b | `board_divergence` on a pick is 0 by construction | **CONFIRMED** (and robust to every live flag) |
| 5c | `pick_year_decay_r1` is 1.00 live | **CONFIRMED** |
| 5d | Player Elo and pick Elo come from different maps | **CONFIRMED**, but the inference drawn from it is wrong |
| 5e | `market_slots` reprices both sides from the requestor's mode | **CONFIRMED** |
| 5 (thesis) | "The engine cannot represent *I discount future firsts, you don't*" | **CONFIRMED** |
| 5 (corollary) | "If both boards agree on the player, there is no trade" | **PARTIALLY CONFIRMED** — true for divergence cards; 74.6 % of served cards are consensus-basis, where the corollary is vacuous |
| 6a | Divergence fairness floor is 0.55, computed on seed/consensus values | **CONFIRMED** |
| 6b | Ranking blend is 0.70 × capped HM + 0.30 × consensus ratio | **PARTIALLY CONFIRMED** — two multiplicative terms are omitted |
| 6c | C1 drops picks from the ranking term because pick divergence is 0 | **PARTIALLY CONFIRMED** — a documented fallback keeps picks in on 30.4 % of divergence cards |
| 6d | Range overlap uses the user's counts; uncertainty is directionally asymmetric | **PARTIALLY CONFIRMED** — the counts half is right, the *directional* half is wrong at the gate |
| 6 (thesis) | "The 70/30 blend is not `min(user, partner)`" | **PARTIALLY CONFIRMED** — true of the *ranking* term, but a hard `min(user, partner)` admission gate already exists and the reviewer does not mention it |
| 6 (example) | "A deal both personal boards like but consensus hates (ratio 0.54) is killed" | **REFUTED** — 6 of 123 divergence cards with a recorded threshold were served *below* it, one at 0.488 against a floor of 0.50 |

## Live knob and flag state

Read from prod `model_config` (read-only) and `config/features.json` on `16d277f`.

| Knob | Live value | Source |
|---|---|---|
| `pick_year_decay_r1` | **1.00** | `model_config` row; code default `backend/pick_values.py:161-166`, `backend/trade_service.py:759` |
| `pick_year_decay_r2/r3/r4` | 0.85 / 0.85 / 0.85 | `model_config` rows |
| `fairness_floor_divergence` | **0.55** | `model_config` row; `backend/database.py:2300`, `backend/trade_service.py:154` |
| `relaxed_fairness_threshold` | 0.55 | `model_config` row |
| `mismatch_weight` | **0.70** | `model_config` row; `backend/trade_service.py:107` |
| `fairness_weight` | **0.30** | `model_config` row; `backend/trade_service.py:108` |
| `mutual_gain_cap` | 1500.0 | `model_config` row; `backend/trade_service.py:147` |
| `range_base` | 0.35 | `model_config` row; `backend/trade_service.py:187` |
| `shrink_pseudocount` | 4.0 | `model_config` row; `backend/trade_service.py:186` |
| `rank_div_min_frac` | **0.02** (no DB row — code default governs) | `backend/trade_service.py:677` |
| `mismatch_confidence_damp` | 1.0 (no DB row) | `backend/trade_service.py:723` |
| `min_side_surplus` / `_marginal` | 150.0 / **60.0** (no DB rows) | `backend/trade_service.py:146`, `:210` |
| `user_gain_epsilon` | 0.0 (no DB row) | `backend/trade_service.py:220` |
| `placement_tier_clamp` | 1.0 (no DB row, D-085 default) | — |

Flags (`config/features.json`): `trade_engine.v2` ON, `trade_engine.v3` ON, `trade.picks_in_pool` ON,
`trade.marginal_value` **ON** (so `MIN_SIDE` = 60.0), `trade.slot_pricing` **ON**,
`trade.presentment_rules` ON, `trade.fit_premium` ON, `trade.outlook_blend` **OFF**,
`picks.league_horizon` ON, `picks.slot_labels` ON, `trade_gen.v2` OFF.

## Claim 5 — picks are one number on all three boards

### 5a — one bridged Elo onto seed, user and opponent — CONFIRMED

`backend/server.py:10403-10410` is the whole mechanism, and it is one dict written three times:

```python
pick_elos = _pick_asset_elos(pick_assets)
if pick_elos:
    seed_map = dict(seed_map)          # never mutate service._seed
    seed_map.update(pick_elos)
    user_elo.update(pick_elos)         # user board: consensus for picks
    for _m in league.members:
        if _m.elo_ratings:
            _m.elo_ratings.update(pick_elos)
```

The function's own docstring says it in the same words the reviewer used
(`backend/server.py:10360-10362`): *"The user board gets the same consensus Elo as the seed (picks
aren't matchup-rankable, so user/consensus divergence on a pick is zero by construction)."* The
bridged value is `1200.0 + 6.0 * pick_value` (`backend/server.py:10332-10344`), the exact inverse of
the `pick_value` the pseudo-asset was built with in `_owned_pick_assets`
(`backend/server.py:10315-10317`), so a pick's engine Elo round-trips to its `pool_value`.

### 5b — `board_divergence` on a pick is 0 by construction — CONFIRMED, and robust

`backend/trade_service.py:1319-1330` defines divergence as `|u − o| / max(|u|,|o|)` over the two raw
board accessors, and its docstring already states the pick case. Pinned by
`backend/tests/test_engine_quality.py:105-115` (`board_divergence("PK", …) == 0.0`, "no rounding
slack").

I tried to break it and could not, on four routes:

1. **Shrinkage.** `user_value` is built from `_shrink_user_elo(user_elo, seed_elo, …)`
   (`backend/trade_service.py:4021-4023`), which blends personal Elo *toward the seed*. For a pick
   the two inputs are already identical, so every weight `w` returns the same number. The D-085
   placement clamp cannot move it either: picks are never in `RankingService.placement_bands()`.
2. **Opponent-side outlook blend.** `_vo` (`backend/trade_service.py:4499-4515`) may multiply by
   `outlook_blend_mult`. `trade.outlook_blend` is OFF live, but even ON it is inert here:
   `outlook_blend_mult` at `backend/trade_service.py:2187-2191` documents *"Players with no age data
   get exactly 1.0 from both curves"*, and an injected pick carries `age = 0`
   (`backend/server.py:10322`). Zero divergence survives every flag combination.
3. **An opponent with no primed board.** `_m.elo_ratings.update(...)` is guarded by
   `if _m.elo_ratings`, so a member with an empty map is skipped — which would leave `_vo` falling
   back to `elo_to_value(1500.0)` and manufacture *fake* pick divergence. That hole is closed
   upstream: `_known_user` / `_known_opp` at `backend/trade_service.py:4755-4763` both require
   `p in opp_elo`, so an unprimed pick is dropped from the pools instead of mispriced.
4. **The v3 optimizer.** Same accessors, same `rank_fairness` call
   (`backend/trade_optimizer.py:482-495`).

**A consequence the reviewer did not draw, and it is the sharpest one in this claim.** The v2
candidate prefilter at `backend/trade_service.py:4765-4766` keeps a give candidate when
`_vo(p) >= user_value[p] * 0.97` and a receive candidate when `user_value[p] >= _vo(p) * 0.97`. A
pick satisfies `_vo(p) == user_value[p]` exactly, so **every owned pick passes both direction filters,
always**. Zero divergence does not merely fail to *earn* a pick a place in a package — it makes a
pick permanently eligible on *both* sides of every enumeration. That is the mechanism behind the
picks-as-universal-filler shape the operator has reported repeatedly, and it is upstream of C1, C3
and #227, all of which are downstream filters on a pool picks can never be excluded from.

### 5c — `pick_year_decay_r1` is 1.00 live — CONFIRMED

Code default `backend/pick_values.py:161-166`; mirrored in `trade_service._DEFAULT_CFG`
(`:759-762`) and `_MODEL_CONFIG_DEFAULTS` (`backend/database.py:2367-2370`). Prod `model_config`
carries an explicit row at **1.0**. `pick_pool_value` applies it as
`base_val * (year_decay(round_) ** years_out)` (`backend/pick_values.py:284-289`), so a 2029 1st and
a 2026 1st are the same number to the byte.

### 5d — different maps — CONFIRMED as fact, wrong as an inference

Factually right. A player's consensus seed Elo comes from `data_loader.seed_elo_for_value`
(`backend/data_loader.py:103-115`), an affine map of DynastyProcess's 0–10000 scale into the engine's
value space, then inverted through the exponential Elo↔value curve. A pick's engine Elo comes from
`GENERIC_PICK_SEEDS` (`backend/pick_values.py:24-49`) through `elo_to_value` → `value_to_elo`. The
two are not the same function and agree at exactly one point, Elo 1548.0 — that is precisely
**D-088**'s finding.

But the inference the reviewer is reaching for — that pick and player numbers are therefore
incommensurable in the engine — does not follow, and D-088 is the reason it does not. D-088 was a
**display-path** defect: `server._pick_tier` inverted a stored `pool_value` (already in
`elo_to_value` units) with `seed_elo_for_value` (which inverts DP units). It moved **600 of 1,104
live pick rows' badges (54.3 %)** and **nothing about pricing** —
`docs/reviews/2026-08-19-pick-badge-scale.md`. On the pricing path the correct inverse was already
in use (`backend/server.py:10290`, `_owned_pick_assets` uses `_trade_service_mod.value_to_elo`), and
the ladder's landing point on the player board has been measured directly: `Mid 1st` = the **65th**
best asset against a market median of **66.5** (`docs/reviews/2026-08-19-ktc-pick-value-comparison.md`
line 149). Two different calibration routes into one shared Elo space is not the same as two
incompatible scales.

**Verdict: CONFIRMED as stated, but it is not evidence of a defect on the path the review is about.**

### 5e — `market_slots` reprices both sides from the requestor's mode — CONFIRMED

`_inject_owned_picks` resolves the mode **once**, from the deck owner
(`backend/server.py:10379-10382`: `pinned_pick_pricing_mode() or pick_pricing_mode_for_user(user_id)`),
and calls `_owned_pick_assets(league_id, …)` inside that override. `_owned_pick_assets` prices
**every owner's** picks (`backend/server.py:10298-10302`) through `priced_pool_value`
(`backend/pick_values.py:460-482`). So one user's setting reprices the picks on both sides of every
card in that job. `trade.slot_pricing` is ON live, so the path is reachable; the per-user default is
`tier_ladder` (`backend/pick_values.py:335`), under which `priced_pool_value` returns the stored
value and no DP read is attempted, i.e. today this is a no-op for any user who has not opted in.

### 5 thesis — representability — CONFIRMED

Given 5a and 5b, the conclusion is forced: there is no field, map or code path by which a user can
say "I value a 2029 first less than you do". A pick's number is a league-wide constant written
identically to `seed_map`, `user_elo` and every member's `elo_ratings`. No amount of ranking,
tiering, swiping or placing can move it, because picks are not matchup-rankable and never enter
`_elo_overrides`. **This is a real architectural limitation and it is independent of what the decay
rate is set to.** Setting `pick_year_decay_r1` to 0.85, 0.80 or 1.00 changes the number; it changes
it on all three boards at once.

### 5 corollary — "a pick-for-player 1-for-1 can only show surplus from the player" — PARTIALLY CONFIRMED

Mechanically true on a **divergence** card, for the reason given. But the corollary is doing much
less work than the reviewer implies, because pick-for-player 1-for-1s are almost never divergence
cards. Prod, over the 2,881 asset-bearing impressions: **866 pick-for-player 1-for-1s (30.1 %), of
which exactly 8 are divergence-basis.** The other 858 are `basis = "consensus"`, where the
counterparty has not ranked at all, both boards *are* the seed, and "if both boards agree there is
no trade" is vacuous rather than damning. The claim is right about the mechanism and wrong about
where the volume is.

## Adjudicating the D-079 collision

The two questions have to be separated because the answers point in opposite directions.

### (i) Is flat year-decay wrong as PRICING? — the reviewer is right on the market fact, and wrong on the remedy

The KTC memo does **not** rebut the reviewer, and it is important not to let it appear to. Its
rank-65 finding is measured on the `GENERIC_PICK_SEEDS[(1,"Mid")]` rung, i.e. a **current-year**
pick at `years_out = 0` (`docs/reviews/2026-08-19-ktc-pick-value-comparison.md` line 60 pins it at
value 2117.0 = `elo_to_value(1650)`). That memo measures the **round** axis and explicitly says
round 1 is untouched. D-079 moved the **year** axis. They measure different things, and the KTC memo
is silent on the one the reviewer is challenging.

On the year axis every source we hold runs against us, and the repo already says so in three places:
`docs/reviews/2026-08-19-pick-year-valuation.md` line 209 (*"Do firsts hold value YoY? **No.** Every
source discounts them: DP 0.80, FantasyCalc 0.80, KTC 0.83, DynastyCalc 0.93"*), the code comment at
`backend/pick_values.py:138-148`, and D-079's own Consequences paragraph (*"We are now deliberately
pricing firsts above the outside market"*). This is logged as **Q-018**.

So the reviewer's *observation* is correct and already conceded. Their *remedy* —
`pick_year_decay_r1 → 0.85` — is not new information, it is the exact constant D-079 removed after a
measurement and an explicit operator direction. Reverting it re-opens two things D-079 closed and
measured: the Adams-for-a-2029-1st shape (`overpay_ok` gap 978.2 → 161.3, back under its 500 floor),
and the year arbitrage, which was **99 of 2,048 served cards** moving a 1st one way and a
different-year 1st the other. D-079's rejected-alternatives note is directly on point: *"Flat is the
**only** rate that makes first-for-first year swaps structurally impossible rather than filtered."*

**A partial correction against D-079, from prod.** "Structurally impossible" overstates what
shipped. Post-deploy (served after 2026-08-19 05:00 UTC), **14 cards still put a 1st on both sides**
— 4.3 % of pick-bearing cards, down from 9.5 % pre-deploy but not zero — and several are
cross-year: impression `503ddb44` gives a 2027 1st for a 2029 1st, `a89b0be7` a 2027 for a 2028,
`a868457d` a 2027 for a 2026. What D-079 killed is the *economic* arbitrage (the two picks now price
identically, so the swap earns nothing). What it did not kill is the *shape*, because C3's
`strip_matched_pick_pairs` is evaluation-only by design — D-074 says so explicitly (*"C3's strip is
evaluation-only: a matched pick pair inside a package with real content on both sides still rides on
the emitted card"*), and `pick_swap_ok` (`backend/trade_service.py:1597-1638`) only kills the card
when stripping empties a side. So the operator can still be shown a card that swaps firsts across
years. That is a live gap worth naming; it is **not** an argument for restoring the decay, which
would make those same 14 cards score as profitable again.

**Verdict on (i): the reviewer is factually right that flat r1 diverges from every market source,
and adds nothing the repo had not already logged as Q-018. Their proposed revert is refused on the
evidence D-079 recorded. This is an operator call, already made, one config write from reversal.**

### (ii) Is per-board pick divergence unrepresentable? — CONFIRMED, and this is the real finding

Yes, and it is orthogonal to the rate — see 5b above. This half of claim 5 survives every
countervailing document the task named, because none of them addresses it: the KTC memo is about
where the ladder sits against the market, D-079 is about the year gradient, D-084 is about round 2,
D-088 is about a badge, D-090 is about a label, D-091 is about which years exist. All six move *the*
number. None of them creates a *second* number.

The product consequence is stated fairly by the reviewer. Picks are in **54.4 %** of served cards
and **85.5 %** of divergence cards, and firsts are **78.9 %** of all pick mentions — so the single
largest asset class in the deck contributes exactly zero to the mutual-gain signal the whole product
is built on. D-090's Q-023 already brushes the same wall from another side (a 1.01 vs a 1.12 is one
number today too), and D-074 named the same fact in 2026-08-18 as "picks are free fairness".

I make no recommendation here — that is a product decision — but the honest framing for the operator
is: this is not a bug in a knob, it is an absent axis, and the four decisions shipped today all move
the axis that exists.

## Claim 6 — "fairness" is consensus, not min(user, partner)

### 6a — floor is 0.55, computed on seed values — CONFIRMED

`backend/trade_service.py:4491-4496`:

```python
fairness_threshold = min(fairness_threshold,
                         _c("fairness_floor_divergence"))
```

with the preceding comment recording the 2026-07-17 interview rationale (*"the consensus fairness
check is only an extreme-case veto"*). `_fairness` (`backend/trade_service.py:4580-4610`) prices both
sides with `seed_value(p)`, which is `_vs` (`backend/trade_service.py:4042-4048`):
`elo_to_value(seed_elo.get(pid, 1500.0))` — the consensus seed, not either manager's board. v3 mirrors
it exactly (`backend/trade_optimizer.py:111-142`). Live value 0.55, confirmed in prod `model_config`
**and** in the served data: the 123 divergence impressions carrying a recorded
`fairness_threshold` show **0.55 (105 rows)** or **0.50 (18 rows — the client toggle at 0.50, since
`min(0.50, 0.55) = 0.50`)**, while consensus impressions show 0.75 (568) or 0.50 (186). That is
`min(requested, fairness_floor_divergence)` visible in the data.

### 6b — the 0.70/0.30 blend — PARTIALLY CONFIRMED

The two weights and the cap are right (`backend/trade_service.py:107-108`, `:147`; both carry
matching prod `model_config` rows). The formula the reviewer wrote omits two multiplicative terms
that are in the shipped line (`backend/trade_service.py:4731-4738`):

```python
composite = (W_MIS * min(hm, GAIN_CAP) / GAIN_CAP
             * mismatch_damp(give_ids + recv_ids, seed_value, confidence)
             + W_FAIR * rank_fairness(fairness, give_ids, recv_ids,
                                      seed_value, _uv, _vo))
composite *= self._tier_mult_v2(shrunk_user_elo, give_ids + recv_ids)
```

— C5's `mismatch_damp` (live at `mismatch_confidence_damp = 1.0`, so it is *not* inert) scales the HM
term down by the package's mean per-asset uncertainty, and a positional tier multiplier scales the
whole thing. A target bonus follows. The reviewer's second sentence is also imprecise: the fairness
term is **not** the consensus ratio, it is `rank_fairness` — the C1 signal-core ratio — which the
reviewer then correctly describes in their next sentence. Right numbers, incomplete formula.

### 6c — C1 drops picks from the ranking term — PARTIALLY CONFIRMED

`signal_core` (`backend/trade_service.py:1333-1337`) keeps only ids clearing
`rank_div_min_frac = 0.02`; a pick scores 0.0, so it is dropped. Correct, and the stated reason is
correct.

The reviewer omits the **degenerate-core fallback**, and it is not a footnote.
`rank_fairness` (`backend/trade_service.py:1362-1367`) returns the **full-package** fairness whenever
either core comes back empty — which is exactly the "buy a player with a pick" shape, and the
docstring says why (*"Scoring it 0 would systematically demote every pick-for-player trade, which is
a new defect, not the one being fixed"*). Measured in prod: **222 of 731 divergence cards (30.4 %)
have one side composed entirely of picks**, so on nearly a third of divergence cards C1 does *not*
drop the picks — it hands back the full-package ratio and the picks are fully priced into the
ranking term. The claim is true on the other ~70 %.

### 6d — range overlap and asymmetric uncertainty — PARTIALLY CONFIRMED

**Right:** the uncertainty map is the requesting user's and only the user's.
`server.py:5276` passes `confidence_counts = service.comparison_counts()` — the deck owner's ranking
service — into the engine, and `_value_uncertainty`
(`backend/trade_service.py:1281-1303`) reads it for *every* asset on *both* sides:
`unc = range_base / sqrt(1 + n)`, `range_base = 0.35`. Since the receive side is the opponent's
roster, its players are systematically less compared by this user, so `r_unc` really does run larger
than `g_unc` in practice. F1 (`pin_exclude_comparisons = 1.0` live) narrows `n` further.

**Wrong:** the gate is *not* directionally asymmetric. `backend/trade_service.py:4605-4606`:

```python
overlap = (gv * (1 + g_unc) >= rv * (1 - r_unc)
           and rv * (1 + r_unc) >= gv * (1 - g_unc))
```

Widening either interval loosens **both** inequalities. A large `r_unc` makes the gate more
permissive to user-steals *and* to user-overpays by the same amount; there is no term that
distinguishes the direction. The reviewer's directional framing is inaccurate **at the gate**.

**But the composed claim survives.** #108 (`user_gain_ok_1for1` → `fit_premium_1for1`,
`backend/trade_service.py:2422-2454`, called at `:4655-4659`) is a strictly one-directional filter
that only blocks the user-losing side, and only on 1-for-1s. So a symmetric gate followed by an
asymmetric one yields a net asymmetry in the direction the reviewer names — for 1-for-1 shapes.
Multi-asset packages get no #108 protection at all. **Verdict: right conclusion, wrong mechanism;
the asymmetry is #108's, not the overlap term's.**

### 6 thesis — "the 70/30 blend is not `min(user, partner)`" — PARTIALLY CONFIRMED

True of the **ranking** term, and the code says so deliberately — the gate-vs-ranking separation is
documented at `backend/trade_service.py:1305-1315`:

> *A GATE judges the real package: a pick genuinely transfers value and can genuinely make an unfair
> trade fair, so every gate keeps pricing the whole thing on real consensus values. A RANKING term
> may judge only the divergence-bearing content, because the composite is supposed to score MUTUAL
> GAIN.*

**The reviewer talks past this design rationale on one half and lands a hit on the other.**

Where they talk past it: the review presents 70/30 as if it were the *admission* rule. It is not.
Admission runs `if user_surplus < MIN_SIDE or opp_surplus < MIN_SIDE: return`
(`backend/trade_service.py:4720-4721`; v3 at `backend/trade_optimizer.py:559-561`) — which *is*
`min(user_surplus, opp_surplus) >= 60.0`, evaluated on each side's own board, before fairness is
consulted at all. And `_harmonic_mean` returns 0 whenever either surplus is ≤ 0
(`backend/trade_service.py:1224-1228`), so the HM term is structurally a min-like statistic.
Prod confirms the gate bites: **all 1,335 divergence impressions carry `surplus_margin` > 0
(min 75.7, median 1,667.2)** — `surplus_margin` is the stamped `mismatch_score`, i.e. the HM
(`backend/server.py:3860`, `backend/trade_service.py:4858`). Not one served divergence card lacked
two-sided gain. A `min(user, partner)` rule already exists; it is spelled as a surplus floor rather
than as a fairness ratio.

Where they land a hit: the *ordering* among admitted cards genuinely does spend 30 % of its budget on
a consensus statistic that neither manager holds, and 70 % on a harmonic mean of two personal
surpluses. A card whose two boards both love it can be out-ranked by one they both merely tolerate
but consensus adores. That is real, and it is the deliberate design.

### 6 example — "a deal at ratio 0.54 is killed" — REFUTED

This one is simply wrong, and the line is `backend/trade_service.py:4607-4608`:

```python
if not overlap and fairness < fairness_threshold:
    return None
```

The kill requires **both** conditions. A 0.54 card whose value intervals overlap is served. In prod,
of the 123 divergence impressions with a recorded effective threshold, **6 (4.9 %) were served with
a `fairness_score` strictly below their own threshold** — including 0.495 and 0.503 against a 0.55
floor and **0.488 against a 0.50 floor**. None was flagged `relaxed`, so these are range-overlap
passes, not the #189 relaxed band. Across all 8,617 rows, 71 divergence cards (min 0.483) and 164
consensus cards (min 0.501) sit below 0.55. The reviewer's own mechanism section describes the
overlap gate two sentences later and then writes an example that ignores it.

## Prod measurements

Denominator 2,881 impressions with `assets_json` populated, unless noted.

| Measure | All | Divergence (731) | Consensus (2,150) |
|---|---|---|---|
| Share of served cards | — | 25.4 % | 74.6 % |
| Pick-bearing | 1,566 (54.4 %) | 625 (**85.5 %**) | 941 (43.8 %) |
| One side entirely picks (C1 fallback fires) | 1,087 (37.7 %) | 222 (**30.4 %**) | 865 (40.2 %) |
| Both sides entirely picks | **0** | 0 | 0 |
| Pick-for-player 1-for-1 | 866 (30.1 %) | **8** (1.1 %) | 858 (39.9 %) |

Pick mentions by round: 1st **1,776 (78.9 %)**, 2nd 435, 3rd 36, 4th 5 — consistent with D-088's
independent 80.9 % and its finding that 4ths reach essentially no decks.
Pick mentions by season: 2026 610 · 2027 654 · 2028 536 · 2029 452.

Fairness, over all 8,617 rows: divergence median 0.811, min 0.483, 71 below 0.55; consensus median
0.859, min 0.501, 164 below 0.55.
`surplus_margin` (= HM): divergence 1,335/1,335 > 0; consensus 7,282/7,282 exactly 0 (the
`mismatch_score = 0.0` constructor at `backend/trade_service.py:5035`, *"no divergence signal by
construction"*).

First-for-first shape, cohorted at the D-079 deploy boundary (main commit `8b7689a`,
2026-08-19 00:39 EDT ≈ 04:39 UTC):

| Cohort | n | pick-bearing | 1st on both sides | as % of pick-bearing |
|---|---|---|---|---|
| Pre-deploy | 2,122 | 1,237 (58.3 %) | 118 | 9.5 % |
| Post-deploy | 759 | 329 (43.3 %) | 14 | 4.3 % |

### Confound: D-091 phantom picks

**Every pick-related number above is polluted, and by more than the headline figure.** D-091 (merged
today at `eafd3f8`) found that pre-draft leagues carried a phantom 2029 draft class. Measured here:
**431 of 2,881 asset-bearing impressions (15.0 %) carry a 2029 pick — 27.5 % of all pick-bearing
cards.** In the post-D-079 cohort it is still 9.9 %. D-091's own read put it at 12.8 % of served
cards on a different (larger, differently-windowed) denominator; the two are consistent given the
different bases.

Consequences for this memo, stated rather than buried:

- The pick-bearing shares (54.4 % overall, 85.5 % of divergence) are **inflated** — a quarter of
  pick-bearing cards owe their pick to a class that does not exist. Treat 54.4 % as an upper bound.
- The 14 surviving post-D-079 first-for-first cards include ones naming a 2029 pick
  (`503ddb44`, `355df89e`), so that count is also an upper bound.
- The like/pass propensity data over 2026-08-16 → 08-19 is contaminated in a *directional* way per
  D-091 (phantom cards drew 6.7 % of likes but 15.8 % of passes), so I deliberately made **no
  acceptance-rate claim** anywhere in this memo. Every number above is a count of what was *served*,
  which the phantom inflates but does not bias in a direction I cannot state.
- Nothing about claims 5a–5e or 6a–6d depends on the phantom: those are code facts and threshold
  facts, and the phantom changes only the volume the facts apply to.

## What strengthens and what weakens the reviewer

**Strengthens claim 5:**

- The both-directions prefilter pass at `backend/trade_service.py:4765-4766` — zero divergence makes
  every pick permanently eligible on both sides of every enumeration. The reviewer did not find this
  and it is the strongest version of their argument.
- 14 post-D-079 cards still swap firsts across years, so "structurally impossible" in D-079's
  Alternatives paragraph is an overstatement of what shipped.
- Firsts are 78.9 % of pick mentions and picks are in 85.5 % of divergence cards: the missing axis
  covers the majority of the divergence deck by asset count.

**Weakens claim 5:**

- The corollary lands almost nowhere in practice: only 8 of 866 pick-for-player 1-for-1s are
  divergence-basis. 74.6 % of served cards are consensus-basis, where "both boards agree" is a
  tautology, not a defect.
- 5d's map observation is true but is not evidence about the pricing path; D-088 fixed the one place
  the wrong map was actually used, display-side, today.
- The proposed remedy (`pick_year_decay_r1 → 0.85`) is a revert of a measured, operator-directed
  decision, and it does nothing at all for the representability half — which is the half of the claim
  that is actually novel.

**Strengthens claim 6:**

- 6a, and the weights, are exactly right and confirmed twice over (code + prod `model_config` + the
  per-card `fairness_threshold` column).
- The 30 % consensus term in the ordering is a genuine, deliberate departure from a purely personal
  criterion, and the reviewer describes its effect accurately.
- 6d's counts observation is right and its net conclusion is right, even though its mechanism is not.

**Weakens claim 6:**

- The headline is answered by the design it does not engage with: a hard `min(user_surplus,
  opp_surplus) >= 60.0` admission gate runs before fairness is consulted
  (`backend/trade_service.py:4720-4721`), and prod shows it never let a one-sided card through
  (1,335/1,335 with HM > 0). The reviewer treats a *ranking* weight as if it were the *admission*
  rule; `backend/trade_service.py:1305-1315` exists precisely to keep those separate, and the
  criticism talks past it.
- The 0.54 example is **factually wrong** — `backend/trade_service.py:4607` kills only when the
  ranges *also* fail to overlap, and 6 divergence cards were served below their own floor, one at
  0.488 against 0.50.
- 6b's formula omits `mismatch_damp` (live, not inert) and the tier multiplier.
- 6c ignores the degenerate-core fallback, which applies on 30.4 % of divergence cards.
- 6d's directional asymmetry is not in the overlap term, which is symmetric by inspection; it comes
  from #108, and #108 covers only 1-for-1 shapes.

## Cross-check against the last 24 hours

Read before judging: D-079 → D-091 in `living-memory/DECISIONS.md`, and
`docs/reviews/2026-08-19-pick-year-valuation.md`, `-ktc-pick-value-comparison.md`,
`-pick-badge-scale.md`.

| Recent decision | Bearing on these claims |
|---|---|
| **D-079** | Head-on collision with the reviewer's remedy. Adjudicated above: reviewer right on the market fact (already Q-018), remedy refused, representability untouched by either position. |
| **D-084** | Repriced round 2 only; explicitly leaves round 1 alone. Does not bear on the year axis. |
| **D-088** | Establishes precisely which map is used where. Confirms 5d's fact, removes 5d's sting: the wrong inverse was on the badge path and is fixed. |
| **D-090** | Slot labels, display-only, `test_no_price_moves_with_or_without_an_order`. Its Q-023 (should a 1.01 outprice a 1.12?) is a *sibling* of claim 5's missing axis — same class, different dimension. |
| **D-091** | The measurement confound; quantified above. Does not touch either claim's logic. |
| **D-074** | Pre-dates the review and already names claim 5's premise ("picks are free fairness") and builds C1 on it. Claim 6c is a partial re-description of D-074's own decision. |
| **D-085** | Confirms the gate-vs-ranking separation is load-bearing and deliberate: `_value_uncertainty` was left placement-blind *because* it feeds a gate (`backend/trade_service.py:1286-1292`). Directly relevant to 6d. |

## Scope

Read-only on engine code. This memo is the only file added. No `backend/*.py`, no flag, no
`model_config` row, and specifically not `pick_year_decay_r1`, was modified. No D-/G-/M-/Q- id was
allocated; existing ids are referenced only. Probe scripts stayed in the session scratchpad.
