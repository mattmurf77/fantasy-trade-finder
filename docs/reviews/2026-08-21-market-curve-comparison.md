# Is our player curve flatter than the market's? — measurement, not a change

**Date:** 2026-08-21
**Trigger:** operator, paraphrased — *"all the player valuations feel slightly off, and served trades show large packages of mid-tier players 'fairly' buying studs."* Hypothesis put for test: **FTF's player value curve is flatter across ranks than the market's**, i.e. our mid-tier players are systematically rich against our elite players.
**Method:** the scale-free rank-equivalence approach from [D-084](../../living-memory/DECISIONS.md) / [2026-08-19-ktc-pick-value-comparison.md](2026-08-19-ktc-pick-value-comparison.md), extended from picks to players. Raw values are never compared across sources.
**Commissioned by:** the 2026-08-21 tier-anchor diagnostic (`living-memory/CHANGELOG.md`, 2026-08-21 entry), which found within-band spread HEALTHY and named this comparison as the follow-up.
**Status:** research memo. **No engine code, knob, flag or config was changed.** `git diff origin/main -- backend/ config/` on this branch is empty. The only file written is this one.

---

## Table of contents

- [The short version](#the-short-version)
- [What prod actually serves](#what-prod-actually-serves)
- [The three curves](#the-three-curves)
- [Test 1 — overall curve shape](#test-1--overall-curve-shape)
- [Test 2 — rank equivalence](#test-2--rank-equivalence)
- [Test 3 — the consolidation implication](#test-3--the-consolidation-implication)
- [Test 4 — per-position cuts, and the QB compression](#test-4--per-position-cuts-and-the-qb-compression)
- [Where the symptom actually comes from](#where-the-symptom-actually-comes-from)
- [Remedy options](#remedy-options)
- [Sources](#sources)
- [What this does NOT show](#what-this-does-not-show)

---

## The short version

**The hypothesis as stated is refuted. Two other things are wrong, and one of them is large.**

The deciding number is **`value(rank 36) / value(rank 3)`** — the cleanest single expression of "how much cheaper is a mid-tier starter than an elite asset":

| board | value(#36) / value(#3) |
|---|---|
| KeepTradeCut 1QB | **0.607** ← flattest |
| DynastyProcess raw | 0.479 |
| **FTF, as served** | **0.466** |
| FantasyCalc 1QB | **0.422** ← steepest |

FTF sits **inside** the market band, at its steep end — 22 % of the way up from FantasyCalc toward KTC. Every other anchoring I tried says the same thing (normalise to #1, normalise to the rank-24 mid anchor, and a two-anchor affine normalisation at ranks 3/200 that is immune to both a scale factor *and* an additive pedestal). Our mids are not rich against our elites. If anything they are slightly cheap.

What *is* wrong:

1. **Quarterbacks are deflated by a factor of 4.4, and it happened five hours before this memo.** The `qb_1qb_cap_elo` 1785→1644 / knee 1580→1200 flip at 04:46Z today puts **Josh Allen at the 71st asset on our board**. KTC 1QB says 12th, FantasyCalc 18th, DynastyProcess 16th. We serve **zero QBs in the top 50**; all three market boards serve five or six. Lamar Jackson badges `second`. This alone is enough to make "all the valuations feel slightly off" true for any roster with a starting QB on it. It is a deliberate operator ruling, not a bug — but no market source supports it.
2. **The mid-package-buys-stud symptom is real and reproducible — and it is not the curve.** It is the package aggregation math. A concrete served example below has FTF calling **Rashee Rice + Travis Etienne + D'Andre Swift + Blake Corum for Puka Nacua** a fair trade (ratio 0.939, inside the ±15 % band). The same four players against the same target price at 1.362 on FantasyCalc and 2.260 on KTC — both say the package massively overpays, i.e. both would refuse to build it. The gap is `_package_value_market` (`backend/trade_service.py:1378`): it benchmarks each piece against **the package's own best asset**, at floor 0.70 and γ 0.5, with the whole discount capped at 35 %. A package of four similar mids therefore gets a ~5 % haircut. The pre-#214 `heavy` shape prices the same package at 0.692 — blocked.

A third, smaller finding: **raising `ktc_blend_weight` cannot change the curve's shape at all**, by construction. Measured across `w = 0 … 1`, `value(#36)/value(#3)` moves 0.474 → 0.466 → 0.474. Remedy (b) from the brief is structurally inert on this question.

---

## What prod actually serves

**Our curve is a blend, but the blend is ordering-only.** `_apply_consensus_blend` (`backend/data_loader.py:399`) rank-normalises KTC onto DP's *own* value curve before averaging: the KTC-rank-*i* matched player is assigned `curve[i]`, the *i*-th largest DP value. So KTC imports an **opinion about who is better**, never an opinion about **how much better**. At `w = 1.0` the blended value multiset is DP's multiset re-permuted (max |Δ| over 643 sorted ranks = 256, entirely the top-anchor rescale and the 203 unmatched players). The value distribution is DynastyProcess's, always. This is stated in the module comment at `data_loader.py:161-172` and in `docs/glossary.md` § Blended consensus; I re-measured it rather than trusting it.

So **"FTF's curve" = DynastyProcess's curve**, with three FTF-specific transforms on top:

| transform | where | effect on the curve |
|---|---|---|
| KTC blend, `ktc_blend_weight = 0.5` | `data_loader.py:399` | reorders players; **shape unchanged** |
| 1QB QB compression, `qb_1qb_cap_elo` / `_knee_elo` | `data_loader.py:267` | a **scalar** on every QB (see below) |
| affine seed map, `SEED_VALUE_FLOOR/CEIL` | `data_loader.py:97-100`, `:103` | adds a **+223.13 pedestal** to every asset and caps the top at 8468 |

The affine map is worth stating explicitly because it is the thing most likely to be mistaken for flatness. `elo_to_value(seed_elo_for_value(dp))` collapses to

```
engine_value = 223.13 + (dp / 10000) × 8244.87
```

— a straight line. `223.13` is `SEED_VALUE_FLOOR`, the engine value of Elo 1200 (`ELO_MIN`, `data_loader.py:84`); `8468.0` is `SEED_VALUE_CEIL`, four mid-1sts. Every rostered body in the pool, down to the 643rd, is worth 223 engine points, and the engine sums those.

**Knob provenance.** The 1QB QB knobs are the operator's `set_knob.py` flip of **2026-08-21 04:46Z** — `qb_1qb_cap_elo` 1785 → **1644**, `qb_1qb_cap_knee_elo` 1580 → **1200** (`living-memory/CHANGELOG.md`, 2026-08-21). I used those, not the code defaults. `ktc_blend_weight` I could not verify against prod — the read-only prod DB pull was blocked in this session — so I used **0.5**, the code default (`data_loader.py:215`), the seed default (`database.py:2205`) and the value in the local dev DB. Since the w-sweep shows the curve shape is insensitive to it, a wrong guess here changes nothing in this memo.

Other live settings that matter to §[Where the symptom actually comes from](#where-the-symptom-actually-comes-from): `stud_tax_mode` default **`market`** (`trade_service.py:1068`), `trade.crown_asset` **ON**, `trade_engine.v2`/`v3` ON, `trade_gen.v2` OFF (`config/features.json`).

---

## The three curves

All boards are 1QB, pulled 2026-08-21. Rank agreement is checked first, because a rank-vs-rank comparison is only fair if the boards order players the same way:

| FTF rank band | n matched (KTC) | median (KTC − FTF) | n matched (FC) | median (FC − FTF) |
|---|---|---|---|---|
| 1–50 | 49 | +2.0 | 49 | +2.0 |
| 50–100 | 50 | +10.0 | 50 | +11.0 |
| 100–150 | 48 | +7.0 | 50 | +6.0 |
| 150–220 | 69 | +3.0 | 69 | 0.0 |
| 220–300 | 78 | −4.5 | 79 | +15.0 |

217/220 of FTF's top 220 appear on KTC, 219/220 on FantasyCalc. The boards agree on **who** to within a handful of ranks — exactly as the D-084 memo found two days ago. Whatever they disagree about, it is not the ordering. (The +10/+11 bulge at ranks 50–100 is the QB deflation showing up as a rank shift; see §[Test 4](#test-4--per-position-cuts-and-the-qb-compression).)

---

## Test 1 — overall curve shape

### Normalised to the #1 asset

| rank | **FTF served** | DP raw | KTC 1QB | FantasyCalc |
|---:|---:|---:|---:|---:|
| 1 | 1.000 | 1.000 | 1.000 | 1.000 |
| 3 | 0.979 | 0.932 | 0.999 | 0.853 |
| 5 | 0.922 | 0.891 | 0.877 | 0.760 |
| 8 | **0.875** | 0.883 | **0.780** | **0.659** |
| 12 | 0.763 | 0.711 | 0.756 | 0.605 |
| 18 | 0.652 | 0.624 | 0.692 | 0.505 |
| 24 | 0.573 | 0.574 | 0.648 | 0.430 |
| 36 | **0.457** | 0.447 | **0.606** | **0.360** |
| 48 | 0.341 | 0.367 | 0.573 | 0.316 |
| 64 | 0.199 | 0.254 | 0.530 | 0.271 |
| 100 | 0.107 | 0.097 | 0.423 | 0.177 |
| 150 | 0.052 | 0.031 | 0.345 | 0.131 |
| 200 | 0.035 | 0.009 | 0.282 | 0.098 |

### Normalised to the rank-24 mid anchor

| rank | **FTF served** | DP raw | KTC 1QB | FantasyCalc |
|---:|---:|---:|---:|---:|
| 1 | 1.744 | 1.741 | 1.543 | 2.325 |
| 3 | 1.707 | 1.623 | 1.541 | 1.982 |
| 8 | 1.526 | 1.537 | 1.204 | 1.533 |
| 12 | 1.330 | 1.239 | 1.167 | 1.406 |
| 36 | 0.796 | 0.778 | 0.935 | 0.837 |
| 48 | 0.594 | 0.640 | 0.883 | 0.735 |
| 64 | 0.348 | 0.442 | 0.817 | 0.630 |
| 100 | 0.186 | 0.169 | 0.653 | 0.412 |

Against the mid anchor, an elite asset is worth **1.71 mid-tier players** on our board, **1.54** on KTC's and **1.98** on FantasyCalc's. We are between them, closer to KTC. A flat-curve defect would put us *below* both.

### Two-anchor affine normalisation

Because a source's zero point is an editorial choice — and the D-084 memo's central methodological warning is exactly that KTC's is not ours — here is the same shape with **both** an unknown scale and an unknown additive pedestal divided out: `φ(r) = (v_r − v_200) / (v_3 − v_200)`.

| rank | **FTF served** | DP raw | KTC 1QB | FantasyCalc |
|---:|---:|---:|---:|---:|
| 5 | 0.939 | 0.956 | 0.831 | 0.877 |
| 8 | **0.890** | 0.947 | 0.695 | 0.744 |
| 12 | 0.771 | 0.761 | 0.662 | 0.672 |
| 18 | 0.653 | 0.666 | 0.572 | 0.539 |
| 24 | 0.570 | 0.612 | 0.511 | 0.440 |
| 36 | 0.446 | 0.474 | 0.452 | 0.348 |
| 48 | 0.323 | 0.388 | 0.405 | 0.289 |
| 64 | 0.174 | 0.265 | 0.346 | 0.229 |
| 100 | 0.076 | 0.095 | 0.197 | 0.105 |

This is the only cut where FTF looks flat, and it is flat in **one specific place: the top 8**. `φ(8) = 0.890` against KTC's 0.695 and FantasyCalc's 0.744 — our #8 asset is nearly as valuable as our #3. From rank 48 down we are the **steepest** board of the four.

**Flatness verdict.** Our elite tier is internally compressed (ranks 3–12 are hard to tell apart), and our tail is steeper than either market source. Neither of those is "mids are rich against elites". The mid-vs-elite ratio, however anchored, lands at or below FantasyCalc's:

| metric | FTF | DP | KTC | FC | FTF inside market band? |
|---|---:|---:|---:|---:|---|
| v(36)/v(3) | 0.466 | 0.479 | 0.607 | 0.422 | yes, steep end |
| v(48)/v(3) | 0.348 | 0.394 | 0.573 | 0.371 | **below both** |
| v(36)/v(8) | 0.522 | 0.506 | 0.777 | 0.546 | **below both** |
| v(24)/v(1) | 0.573 | 0.574 | 0.648 | 0.430 | yes, middle |

---

## Test 2 — rank equivalence

For our rank-*N* player, take its value relative to our #1, and ask what rank on the market board carries the same relative value (linear interpolation between ranks).

| our rank | player | rel. to our #1 | KTC-equivalent rank | Δ | FC-equivalent rank | Δ |
|---:|---|---:|---:|---:|---:|---:|
| 3 | Bijan Robinson | 0.979 | 3.2 | +0.2 | 1.9 | −1.1 |
| 8 | Justin Jefferson | 0.875 | 5.1 | −2.9 | 2.8 | −5.2 |
| 12 | Brock Bowers | 0.763 | 10.5 | −1.5 | 4.9 | −7.1 |
| 18 | Jonathan Taylor | 0.652 | 23.7 | +5.7 | 8.3 | −9.7 |
| 24 | George Pickens | 0.573 | 47.6 | +23.6 | 14.3 | −9.7 |
| 36 | Chase Brown | 0.457 | 85.3 | +49.3 | 19.9 | −16.1 |
| 48 | Tucker Kraft | 0.341 | 154.1 | +106.1 | 41.1 | −6.9 |
| 64 | Josh Jacobs | 0.199 | 280.0 | +216.0 | 84.6 | +20.6 |
| 100 | Jayden Higgins | 0.107 | 402.1 | +302.1 | 192.4 | +92.4 |
| 150 | AJ Barner | 0.052 | 451.2 | +301.2 | 246.8 | +96.8 |

**The two market sources point in opposite directions, and the disagreement between them dwarfs our deviation from either.** Relative to KTC we are far too *cheap* in the mid band (our #24 prices like KTC's #48). Relative to FantasyCalc we are too *rich* through ranks 8–36 (our #36 prices like FC's #20). There is no median to hide behind with n = 2 — this is the honest reason the hypothesis cannot be confirmed rather than a claim that it is precisely wrong.

**Where divergence concentrates**, taking the two sources together:

- **Ranks 1–12 (elite):** we agree with KTC almost exactly and are much flatter than FantasyCalc. Both market boards spread their top 8 more than we do.
- **Ranks 18–48 (the mid band the operator named):** we are bracketed. Nobody's outlier.
- **Ranks 64+ (the tail):** we are steeper than both, then the pedestal reverses it below ~rank 250. At rank 200, 74.5 % of a player's served engine value is the flat 223.13 floor; at rank 300 it is 97.3 %. That is a genuine artifact — but it makes our deep filler *cheaper* than either market source in relative terms (0.035 of the #1 asset vs KTC's 0.282 and FC's 0.098), so it does not support the hypothesis either.

---

## Test 3 — the consolidation implication

Two different questions live here and they have different answers. The first is scale-free-ish and comes out clean; the second is where the operator's complaint actually lives.

### 3a. Naive package sums on each board's own scale

How many engine/market points does a package of mid-tier players carry, as a fraction of the **#3 asset** on the same board?

| package (by rank) | **FTF served** | DP raw | KTC 1QB | FantasyCalc |
|---|---:|---:|---:|---:|
| 25 + 35 + 45 | 1.436 | 1.485 | **1.841** | 1.299 |
| 20 + 30 + 40 | 1.599 | 1.659 | 1.887 | 1.395 |
| 30 + 40 + 50 | 1.271 | 1.390 | 1.787 | 1.235 |
| 25 + 40 | 0.993 | 1.051 | 1.237 | 0.892 |
| 36 + 48 + 64 | 1.018 | 1.146 | 1.710 | 1.111 |

Named, on real players, with the target held constant (Bijan Robinson) and the package pinned to the *same three humans* on every board:

| board | target | package (its own ranks) | package sum ÷ target |
|---|---|---|---|
| **FTF served** | Bijan #3 (8291) | K. Walker III #25, McCaffrey #35, T. Henderson #45 → 11 902 | **1.436** |
| KTC 1QB | Bijan #2 (9996) | #27, #41, #45 → 18 068 | 1.808 |
| FantasyCalc | Bijan #1 (11 067) | #20, #22, #43 → 13 570 | 1.226 |
| DP raw | Bijan #3 (9558) | #27, #39, #55 → 13 156 | 1.376 |

Again bracketed, again closer to the steep end. On the pure curve, **it does not take fewer mids to buy a stud on our board than on the market's.**

### 3b. What the engine actually serves — and this is the complaint

The engine does not add naively. `package_value_v2` → `_package_value_market` (`trade_service.py:1298`, `:1378`) applies a depth discount and a crown credit before the fairness ratio is taken. Run at the live knobs (`package_floor_market` 0.70, `package_adj_gamma_market` 0.5, `package_discount_cap` 0.35, `crown_rate_market` 0.08, `skew_phaseout` 0.5, `trade.crown_asset` ON):

| card | naive | **served ratio** | verdict at ±15 % | pre-#214 `heavy` ratio |
|---|---:|---:|---|---:|
| Rice + Etienne + Swift + Corum → **Puka Nacua** | 1.057 | **0.939** | **FAIR — serves** | 0.692 (blocked) |
| K. Walker + McCaffrey + T. Henderson → **Bijan** | 1.436 | 1.386 | blocked | 0.641 |
| Pickens + Flowers → **Justin Jefferson** | 1.195 | 1.125 | **FAIR — serves** | 0.657 |
| McConkey + Coleman + Mason → **Brock Bowers** | 0.873 | 0.793 | blocked | 0.462 |

The 4-for-1 is the operator's card. FantasyCalc prices that same package at **1.362** of Nacua and KTC at **2.260** — on both market boards it is a wild overpay that no counterparty would take. FTF calls it even.

The mechanism is visible in one line of `_package_value_market`:

```python
contrib = sum(v * (floor + (1.0 - floor) * (v / own_max) ** gamma) for v in values)
```

`own_max` is **this side's** best asset, not the trade's. Four mids of similar value each sit near `own_max`, so each contributes ≈ 100 % of its value; the total discount then bottoms out at `package_discount_cap` anyway. Meanwhile the single-asset stud side is never depth-discounted *and* collects the +8 % crown credit, because a 5.7 % naive skew is well inside `skew_phaseout`. Net: the package loses 5 %, the stud gains 7 %, and a 4-for-1 lands inside the fairness band.

The module's own docstring (`trade_service.py:1318-1322`) quotes KTC's published shape — `p·[0.29(p/v)^8 + …]`, an eighth power against the *trade's* best asset — and describes `heavy` as its "single-term simplification". The `market` mode that actually serves is a further, much weaker retune. **This, not the curve, is what lets a pile of mids buy a stud.** It is the same defect the 2026-08-21 CHANGELOG entry already names from the other end: *"15 % of cards carry gap > a late 1st, all from arms D/C at fairness .73–.83 on big packages — the ratio-gate scale-blindness, live."*

---

## Test 4 — per-position cuts, and the QB compression

### Positional curves, value(pos-rank) ÷ value(pos-rank 1)

| pos-rank | QB: FTF / DP / KTC / FC | RB: FTF / DP / KTC / FC | WR: FTF / DP / KTC / FC | TE: FTF / DP / KTC / FC |
|---:|---|---|---|---|
| 3 | 0.758 / 0.713 / 0.824 / 0.715 | 0.903 / 0.879 / 0.780 / 0.688 | 0.922 / 0.895 / 0.878 / 0.891 | 0.724 / 0.746 / 0.803 / 0.693 |
| 8 | 0.525 / 0.459 / 0.709 / 0.549 | 0.560 / 0.638 / 0.616 / 0.441 | 0.724 / 0.711 / 0.732 / 0.583 | 0.210 / 0.284 / 0.501 / 0.299 |
| 12 | 0.378 / 0.282 / 0.618 / 0.397 | 0.406 / 0.331 / 0.591 / 0.360 | 0.588 / 0.615 / 0.630 / 0.470 | 0.122 / 0.143 / 0.456 / 0.238 |
| 24 | 0.191 / 0.054 / 0.467 / 0.256 | 0.135 / 0.104 / 0.435 / 0.193 | 0.395 / 0.368 / 0.565 / 0.343 | 0.046 / 0.020 / 0.327 / 0.158 |

Within every position we track FantasyCalc closely and sit far below KTC. Nothing here is an outlier. **The positional *shapes* are fine.**

### The QB level is not fine

The compression is applied last, in value space (`data_loader.py:267`). With the prod knobs the knee lands at **DP value 0.00** — `seed_value_for_elo(1200)` is exactly the bottom of the affine map — so the "identity below the knee" region described in the function's own docstring **does not exist**. The transform degenerates into a single scalar: **every QB's value × 0.2221**.

Where that puts the position:

| config | QB1 (Josh Allen) served value | Allen's **overall** rank | QBs in the top 50 |
|---|---:|---:|---:|
| **prod, 1644 / 1200** (live since 04:46Z today) | 1 536 | **#71** | **0** |
| code defaults, 1785 / 1580 | 3 266 | #45 | 2 |
| 1785 / 1200 | 3 044 | #47 | 1 |
| 1750 / 1500 | 2 712 | #50 | 1 |
| compression OFF | 6 134 | **#14** | 6 |
| — KTC 1QB | — | **#12** | 6 |
| — FantasyCalc 1QB | — | **#18** | 6 |
| — DynastyProcess raw | — | **#16** | 5 |

Both market 1QB boards — and our own upstream source — put the best quarterback in dynasty football inside the top 20 assets. **We put him 71st.** The compression-off column lands within two ranks of all three; the live setting is 53–59 ranks below them.

Six named players, as served today:

| player | FTF rank | served value | seed Elo | tier badge | KTC | FC | DP |
|---|---:|---:|---:|---|---:|---:|---:|
| Ja'Marr Chase | 1 | 8 468 | 1927.3 | `firsts_4plus` | 3 | 3 | 1 |
| Bijan Robinson | 3 | 8 291 | 1923.0 | (1 pt above `firsts_3.max`) | 2 | 1 | 3 |
| Brock Bowers | 12 | 6 460 | 1873.1 | `firsts_3` | 6 | 9 | 24 |
| Ladd McConkey | 30 | 4 403 | 1796.5 | `firsts_2` | 30 | 39 | 33 |
| Christian McCaffrey | 35 | 3 912 | 1772.8 | `first_1` | 41 | 22 | 39 |
| **Josh Allen** | **71** | **1 536** | 1585.9 | `first_1` | **12** | **18** | **16** |
| **Lamar Jackson** | **80** | **1 164** | 1530.3 | **`second`** | **29** | **35** | **32** |

The 04:46Z ruling's stated two-anchor solve — *"Allen = exactly a late 1st (1539), sub-first QBs = mid-2nds"* — reproduces exactly (I compute 1 536 against the Late-1st seed's 1 491.8). The solve is internally consistent; it is the anchor itself that no market source shares. D-084 measured a Late 1st at the **82nd** asset on the market median (our own board: 85th). Pricing Allen there is a deliberate statement that a 1QB league's best quarterback is worth the 71st-best asset, against a market that says 12th–18th.

One further consequence worth naming: `first_1` now spans Allen (1 536) and McCaffrey (3 912), a **2.5× value range inside one badge**. That is not new — the band is 205 Elo wide and `docs/plans/trios-tier-calibration-plan-2026-07-08.md` already flagged bands as ~50 % value-wide — but the QB flip widened the *occupied* part of it considerably, and it is a plausible second contributor to "the valuations feel off": two assets with the same badge trading at 2.5× each other.

---

## Where the symptom actually comes from

Ranked by how much of the operator's report each explains:

1. **The QB scalar (0.2221×).** Explains "all valuations feel slightly off" better than anything else in this memo. Every roster has QBs; every deck prices them at 22 % of what our own upstream source says. Live for five hours; no user-visible evidence has been gathered yet.
2. **`_package_value_market`'s own-max benchmark + 35 % discount cap + crown credit.** Explains "large packages of mid-tier players fairly buying studs" exactly, with a reproducible served example. Live since #214.
3. **The elite band's internal flatness (φ(8) = 0.890).** A secondary amplifier: when #3 and #8 are 4 % apart, a package sized to beat #8 also beats #3.
4. **The +223.13 pedestal.** Real, measurable, and pointed the *wrong way* for this complaint — it makes deep filler expensive in absolute engine points (six players at ranks 150–155 = 30 % of the #3 asset, 54 % of which is pedestal) but still leaves our tail cheaper than both market boards in relative terms. It matters for junk-stuffing, which is why `#141` exists; it does not matter for mid-tier consolidation.
5. **The value curve's mid-vs-elite steepness.** **Not a contributor.** Inside the market band, at its steep end.

---

## Remedy options

**Nothing below was applied.** Each is priced against the served numbers for the six named players and against the 4-for-1 card.

### (a) A global steepness exponent, post-blend — *not recommended*

Shape: `v' = 10000 · (v / 10000)^p`, slotted in `_apply_consensus_blend` (`data_loader.py:399`) after the QB compression and before the `seed_elo_for_value` map, as a `model_config` knob defaulting to `1.0` (identity, byte-for-byte).

| p | #1 | #3 | #12 | #24 | #36 | #48 | #64 | #100 | v36/v3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **1.0 (today)** | 8 468 | 8 291 | 6 460 | 4 856 | 3 867 | 2 885 | 1 688 | 904 | **0.466** |
| 1.15 | 8 468 | 8 265 | 6 204 | 4 472 | 3 447 | 2 469 | 1 354 | 692 | 0.417 |
| 1.30 | 8 468 | 8 239 | 5 959 | 4 120 | 3 075 | 2 119 | 1 096 | 546 | 0.373 |
| 1.50 | 8 468 | 8 204 | 5 647 | 3 696 | 2 646 | 1 735 | 841 | 419 | 0.322 |

Even `p = 1.15` pushes us **outside** the market band on the steep side (FantasyCalc's floor is 0.422). Since Test 1 says we are already at the steep end, this remedy makes the measured position worse, not better. **What it breaks, if anyone tries it anyway:**

- **Players move against picks.** `GENERIC_PICK_SEEDS` (`backend/pick_values.py:24`) seeds Elo *directly* and never passes through this transform. Steepening players alone silently reprices every pick-for-player card and undoes the D-084 rank-equivalence calibration that was landed two days ago (Mid 1st = the 65th asset). Any exponent change is a pick recalibration whether or not anyone intends it.
- **Tier occupancy moves for every user.** `tier_config.json`'s bands are fixed in Elo; a value transform slides everyone through them. `backend/tests/test_tier_occupancy.py`'s ceilings and floors would need re-measuring, exactly as D-084's Option B failed them in three places.
- **The affine map's own anchors stop meaning what they say.** `SEED_VALUE_CEIL = 4 × value(Mid 1st)` (`data_loader.py:99`) is documented as "the top asset is worth ≈ 4 firsts". Under `p > 1` the ceiling still holds for #1 but every rank below it loses first-equivalence, so the `docs/config-reference.md` and `data_loader.py:20-40` docstring claims go stale in the same commit.
- **arm-A golden: safe.** Verified, not assumed. `test_bakeoff_arm_a_golden.py` supplies `seed_elo` as a **literal** table (`_USER_ASSETS`, line 58 → `seed_elo=seed`, line 196) and never touches `data_loader`; the file's own header says the fixture pins its own board "immune to board-computation drift by construction". Any seed-curve change leaves it green.

### (b) Raise `ktc_blend_weight` — *structurally inert, measured*

| `ktc_blend_weight` | v36/v3 | v24/v1 | v100/v1 | v200/v1 | Allen's rank |
|---:|---:|---:|---:|---:|---:|
| 0.00 | 0.474 | 0.577 | 0.107 | 0.034 | 72 |
| 0.25 | 0.463 | 0.582 | 0.105 | 0.035 | 73 |
| **0.50 (live)** | **0.466** | **0.573** | **0.107** | **0.035** | **71** |
| 0.75 | 0.468 | 0.567 | 0.106 | 0.035 | 70 |
| 1.00 | 0.474 | 0.575 | 0.102 | 0.035 | 69 |

The curve does not move, because the blend rank-normalises KTC onto DP's own curve before averaging (`data_loader.py:161-172`). Turning this knob to 1.0 buys **KTC's ordering and none of KTC's flatness** — the shape stays DP's. If someone genuinely wanted KTC's flatter curve, the change would be to stop rank-normalising, which the module comment explicitly rejects as the "FB-69 tier-inflation failure mode". Cost of that: it re-scales every tier band's occupancy and re-opens the whole #145 design. **Do not reach for this knob to fix curve shape.**

### (c) Per-tier re-anchoring — *heavier, and the diagnostic already narrowed it*

Reconciling with the 2026-08-21 tier-anchor diagnostic: it found **within-band spread HEALTHY** (p10/p50/p90 ≈ .07/.5/.9 in every band) and rung occupancy lumpy. This memo finds **between-rank steepness is also fine** vs market. The two together say the ladder is not the problem in either axis, and per-tier re-anchoring has no measured defect left to fix. The one band-shaped observation that survives is the `first_1` span — Allen at 1 536 and McCaffrey at 3 912 under one badge — and that is downstream of the QB scalar, not of the band edges. **Fix the input, not the band.**

### (d) What I would actually do — the package aggregation, then the QB anchor

Neither is a curve change, and both target something measured rather than hypothesised.

**(d1) Re-tune `_package_value_market`.** The specific defect is `own_max`. Benchmarking against the *trade's* best asset (what `heavy` does at `trade_service.py:1354`) is what makes four quarters stop being a dollar. Sensitivity on the operator's 4-for-1:

| knobs | give | get | ratio | serves? |
|---|---:|---:|---:|---|
| **live: floor 0.70, γ 0.5, cap 0.35** | 7 842 | 8 356 | **0.939** | **yes** |
| floor 0.55 | 7 638 | 8 356 | 0.914 | yes |
| γ 1.0 | 7 568 | 8 356 | 0.906 | yes |
| floor 0.55 + γ 1.0 | 7 226 | 8 356 | 0.865 | yes (barely) |
| `heavy`-like: floor 0.15, γ 1.5, cap 0.85, own_max → trade max | 5 779 | 8 356 | 0.692 | **no** |

Knob-only tuning of `package_floor_market` / `package_adj_gamma_market` **cannot** block this card — the `package_discount_cap = 0.35` floor and the own-max benchmark between them keep the ratio inside the band. Getting there needs the benchmark change, which is code, plus a decision about the crown credit (the stud collecting +8 % while the package pays 5 % is half the gap). The CHANGELOG's already-commissioned **auto-sweetener pass** and an **absolute-gap gate alongside the ratio gate** are the two adjacent moves; a ratio band is scale-blind by construction and a 4-piece package is exactly where that bites.

**Two biggest costs.** First, **the arm-A golden breaks — verified, not assumed.** The package-math knobs are **not** in `MODEL_A_PROFILE` (`backend/bakeoff_profiles.py`), so arm A reads them live. I ran the golden with `package_floor_market=0.55, package_adj_gamma_market=1.0` patched in: **3 failed, 7 passed** (`test_arm_a_reproduces_the_pre_wave_deck`, `test_arm_a_is_flag_independent`, `test_r4_bypass_restores_a_card_the_flag_would_exclude`). Baseline is 10/10 green. So the operator's assumption that the golden is untouched holds for a *seed-curve* change and **fails for a package-math change** — a package retune either pins the old shape into `MODEL_A_PROFILE` (with a written arm-A decision, per the knob-inventory test at `test_bakeoff_arm_a_golden.py:545`) or re-captures the golden at a new reference, and the bake-off's only fixed point moves. Second, **it shrinks the deck, hard, in the middle of a live interleaved bake-off.** The `heavy`-like column blocks three of the four cards in Test 3b; the 2026-08-21 entry already records FFV3 pool exhaustion producing repeat decks. Cutting supply while supply is the live complaint needs a measured deck-volume estimate first (`scripts/deck_eval.py` on real leagues), not a knob flip.

**(d2) Revisit the QB anchor.** The market comparison is unanimous and large: three independent 1QB boards put QB1 at #12–#18; we serve #71. Compression **off** lands at #14. If the product rule "no QB may badge two firsts in 1QB" is what matters — which is what #313 was actually about ([scope](../feedback/items/313-1qb-qb-cap/scope.md)) — then `qb_1qb_cap_elo = 1785` with the knee back at 1580 achieves the badge outcome (top of `first_1`, `firsts_2` starts at 1788) at #45, roughly halfway to market, rather than #71. **Costs:** it reverses an operator ruling made hours ago on an explicit two-anchor solve, and QB pricing feeds `position_needs`/`position_surplus`, so it changes every deck for every user — the same blast radius flagged for `trade.position_tiers`. It is deploy-free either way (`set_knob.py`, logged in `model_config_changes`), which is the one thing in this memo that is cheap to try and cheap to undo.

---

## Sources

Every number traces to one of these. Nothing is quoted from memory.

| Source | Exact endpoint | As-of | Pulled (UTC) |
|---|---|---|---|
| DynastyProcess (players) | `https://raw.githubusercontent.com/dynastyprocess/data/master/files/values-players.csv`, `value_1qb` | `scrape_date` **2026-08-21** | **2026-08-21 05:52** (byte-identical re-fetch of the 05:3x copy) |
| KeepTradeCut 1QB | `https://keeptradecut.com/dynasty-rankings` — embedded `playersArray`, `oneQBValues.value`, `position == "RDP"` excluded (36 rows), parsed by the same regex `data_loader.parse_ktc_players` uses | live | **2026-08-21 05:43** |
| KeepTradeCut cross-check | same page at `?format=1` | live | **2026-08-21 05:43** |
| FantasyCalc 1QB | `https://api.fantasycalc.com/values/current?isDynasty=true&numQbs=1&numTeams=12&ppr=1` | live | **2026-08-21 05:43** |
| FTF served board | `data_loader` pipeline reimplemented locally in the session scratchpad: DP `value_1qb` → `_apply_consensus_blend` at `w = 0.5` → `_compress_qb_1qb_values` at **1644 / 1200** → `seed_elo_for_value` → `elo_to_value`. 643 players, 440 KTC-matched | — | **2026-08-21 05:5x** |

**On KTC's 1QB field.** KTC's default page is Superflex-first in its *rendering*, but the embedded `playersArray` carries both blocks on every row, and `oneQBValues.value` is unambiguous — Josh Allen reads `oneQB 7562 / superflex 9995` on the same row. The `?format=1` variant returned 500 rows with **identical `oneQBValues.value` on all 500**, so the toggle is presentational and the field choice is safe. This is the same field `_KTC_FORMAT_PATH` maps to `1qb_ppr` in prod (`data_loader.py:204`).

No page or API response contained text addressed to an agent, and nothing in any of them was treated as an instruction.

---

## What this does NOT show

- **Two market sources is not a market.** With KTC and FantasyCalc pointing in opposite directions and disagreeing with each other far more than either disagrees with us, "the market median" does not exist here the way it did in D-084 (which had five pulls and a pick ladder to anchor on). The correct reading of Test 2 is *"we are inside the disagreement"*, not *"we are right"*. A third and fourth independent 1QB board would materially change how much weight this memo can carry.
- **Curve-shape comparison is not scale-free, and cannot be made so.** D-084's method worked because a *pick* is a single asset locatable on both boards by rank. Two player curves have no such shared object. I used three different normalisations, including an affine-invariant one, and they agree — but a reader who believes KTC's zero is the true zero and ours is not will read Test 1 differently, and nothing in this memo can settle that.
- **The package sums in Test 3a are the most scale-dependent numbers here.** Adding values across ranks assumes each board is a true ratio scale. KTC's is not quite (its worst rostered player is 179 of 9 999); ours is not (223.13 of 8 468). The 3b served-math comparison is on firmer ground because it prices the *same humans* on each board, but even there the ratio-of-sums inherits both pedestals.
- **Our QB rows are not comparable to DP's raw rows at all.** The 0.2221 scalar is applied to every QB before Elo seeding, so any FTF-vs-DP QB comparison in this memo is measuring our own knob, not a disagreement about quarterbacks. The DP column in Test 4 is DP *raw*, deliberately.
- **KTC's 1QB board is 0.5 PPR** (the page's own settings line, as noted in the D-084 memo); our `1qb_ppr` is full PPR. That should matter most at RB/TE and least at WR. Not measured.
- **The pick ladder was not re-checked.** D-084 recalibrated round 2 two days ago; this memo compares players only. If the player curve is ever transformed, the pick rank-equivalence table in that memo becomes stale on the same commit, and nothing here tells you by how much.
- **No prod verification of `ktc_blend_weight`.** The read-only prod DB pull was blocked in this session, so 0.5 is inferred from three consistent non-prod sources. The w-sweep shows it does not matter for the curve; it *would* matter for any claim about which players sit at which rank.
- **No user-facing evidence.** I did not query `deck_impressions`, `swipe_decisions` or `served_arm` to measure how many live cards are the 4-for-1 shape, nor how many carry a QB. The 2026-08-21 CHANGELOG's "15 % of cards carry gap > a late 1st" is the closest existing number and it was measured for a different question. **That query is the thing I would want before anyone touches the package math**, and it is read-only.
- **No deck-volume estimate for remedy (d1).** I measured which individual cards a retune blocks, not what it does to deck size on real leagues. `scripts/deck_eval.py` exists for exactly that and was not run.
