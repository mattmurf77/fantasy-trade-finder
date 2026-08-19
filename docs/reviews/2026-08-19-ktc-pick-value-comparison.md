# How our 1st-vs-2nd gap compares to KeepTradeCut — measurement, not a change

**Date:** 2026-08-19
**Trigger:** operator, verbatim — *"It seems that the gap between a 1st and a second is not severe enough. Compare our valuation of 1sts vs. 2nds to KTC."*
**Companion:** [2026-08-19-pick-year-valuation.md](2026-08-19-pick-year-valuation.md) (D-079, the *year* axis of pick pricing, shipped earlier tonight)
**Status:** research memo. **No pricing was changed.** `GENERIC_PICK_SEEDS` and `tier_config.json` are byte-identical to `origin/main` @ `8b7689a`.

---

## Table of contents

- [The short version](#the-short-version)
- [What FTF prices today](#what-ftf-prices-today)
- [What KTC prices today](#what-ktc-prices-today)
- [The scale trap — why you cannot transplant KTC's ratio](#the-scale-trap--why-you-cannot-transplant-ktcs-ratio)
- [The scale-free comparison: what player is a pick worth?](#the-scale-free-comparison-what-player-is-a-pick-worth)
- [Cross-checks: DynastyProcess and FantasyCalc](#cross-checks-dynastyprocess-and-fantasycalc)
- [The within-round spread](#the-within-round-spread)
- [Direct answer to the operator's question](#direct-answer-to-the-operators-question)
- [Recalibration proposal — and why it is also a tier change](#recalibration-proposal--and-why-it-is-also-a-tier-change)
- [Sources](#sources)
- [What I could not determine](#what-i-could-not-determine)

---

## The short version

**The operator is right, but for the opposite reason to the one KTC's published numbers appear to give.**

Read KTC's raw values and it looks like we are *already* too harsh: KTC prices a mid-2nd at **0.70** of a mid-1st, against our **0.387**. Taken at face value that says our gap is nearly twice too severe.

That reading is wrong, and it is wrong for a measurable reason: KTC's value scale is heavily compressed at the bottom, so every ratio taken on it is pulled toward 1. The comparison that survives a change of scale is **"which player is this pick worth?"** — the rank of the pick inside the same board of players. On that measure:

| | our board says a… | market median says a… |
|---|---|---|
| **Mid 1st** | ≈ the **65th** best asset | ≈ the **66th** — dead on |
| **Mid 2nd** | ≈ the **119th** | ≈ the **141st** — **we are 22 ranks too generous** |
| Mid 3rd | ≈ the 165th | ≈ the 232nd |
| Mid 4th | ≈ the 228th | ≈ the 296th |

Our first-round pricing is essentially perfect. Everything below it is too expensive, and the error grows with the round. **The 1st-vs-2nd gap is too small, exactly as the operator suspected** — and KTC, DynastyProcess and FantasyCalc all agree once they are read on a common scale.

Two things make this more than a numbers exercise:

1. **The repo already measured this and pinned it as a test.** `backend/tests/test_pick_pricing_m6b.py::test_the_measured_reshaping_direction_is_deflation_not_inflation` asserts that switching owned-pick pricing to DynastyProcess's real market slot prices makes our 2nds **collapse by more than 40 %**. That assertion has been green in CI for two weeks. It is a standing, checked-in statement that our ladder overprices 2nds.
2. **Repricing picks *is* repricing tiers.** `tier_config.json`'s own `_calibration` note states that `second`'s floor **is** the Late-2nd seed (1400), `third`'s floor is the Late-3rd seed (1280), `fourth`'s is the Late-4th (1220). You cannot move a pick seed without moving the tier band that sits on it. Any change here changes what every user sees on their board.

A conservative proposal is in [the last section](#recalibration-proposal--and-why-it-is-also-a-tier-change), with its measured tier-occupancy and test consequences. **It is a proposal; nothing was applied.**

---

## What FTF prices today

Verified against `origin/main` @ `8b7689a`, not re-derived. `GENERIC_PICK_SEEDS` (`backend/pick_values.py:24`) seeds Elo; `trade_service.elo_to_value` (`backend/trade_service.py:1020`) converts with the live prod `model_config` `1000 / 0.0050 / 1500`.

| Round | Elo seed | Value | Ratio to same-rung 1st |
|---|---|---|---|
| 1st Early | 1720 | 3004.2 | 1.000 |
| 1st Mid | 1650 | 2117.0 | 1.000 |
| 1st Late | 1580 | 1491.8 | 1.000 |
| 2nd Early | 1520 | 1105.2 | **0.368** |
| 2nd Mid | 1460 | 818.7 | **0.387** |
| 2nd Late | 1400 | 606.5 | **0.407** |
| 3rd Mid | 1320 | 406.6 | 0.192 |
| 4th Mid | 1240 | 272.5 | 0.129 |

All the operator's numbers reproduce exactly.

**One wrinkle D-079 introduced tonight that changes what "0.387" means.** Round 1 no longer decays with year; rounds 2–4 still lose 15 %/yr. So the 2nd-to-1st ratio is now a function of *which year's 2nd*:

| Pick year | 1st | 2nd | ratio |
|---|---|---|---|
| 2026 | 2117.0 | 818.7 | **0.387** |
| 2027 | 2117.0 | 695.9 | 0.329 |
| 2028 | 2117.0 | 591.5 | 0.279 |
| 2029 | 2117.0 | 502.8 | 0.238 |

0.387 is the *widest* case — the current-year 2nd. Every future 2nd is already cheaper against a 1st than the number the operator quoted. That does not change the conclusion below (the current-year rung is still too generous), but it means the deck's far-out cards are already closer to market than the near-year ones.

---

## What KTC prices today

Pulled **2026-08-19 05:01 UTC** from `https://keeptradecut.com/dynasty-rankings`, parsing the server-rendered `playersArray` — the same extraction `backend/data_loader.parse_ktc_players` already performs in prod. Independently confirmed in a browser at `?format=1` (Superflex toggle Off; the page's own settings line reads `.5 PPR • 12 Tm. • No TEP`): the rendered rows for 2027 Early 1st / 2026 Early 1st / 2027 Mid 1st showed 7266 / 6155 / 6153, matching the parse to the unit.

`parse_ktc_players` filters KTC's picks out (`position == "RDP"`) because the pool seeds its own picks — so **these 36 rows are data the app fetches every day and then discards.** That is the reason nobody had noticed the divergence.

### 1QB values, all 36 rungs

| Year | Rung | 1st | 2nd | 3rd | 4th | 2nd:1st |
|---|---|---|---|---|---|---|
| 2026 | Early | 6155 | 4073 | 2861 | 2033 | **0.662** |
| 2026 | Mid | 5336 | 3718 | 2592 | 1887 | **0.697** |
| 2026 | Late | 4685 | 3546 | 2528 | 1737 | **0.757** |
| 2027 | Early | 7266 | 4560 | 3137 | 2175 | 0.628 |
| 2027 | Mid | 6153 | 4188 | 2889 | 2086 | 0.681 |
| 2027 | Late | 5483 | 3832 | 2735 | 1873 | 0.699 |
| 2028 | Early | 5714 | 3876 | 2674 | 1933 | 0.678 |
| 2028 | Mid | 5195 | 3610 | 2508 | 1822 | 0.695 |
| 2028 | Late | 4704 | 3328 | 2352 | 1505 | 0.707 |

Superflex 2nd:1st runs slightly steeper — 2026 Early/Mid/Late = 0.598 / 0.657 / 0.723 — but the shape is the same. **FTF's pick values are format-agnostic by design** (`docs/cross-client-invariants.md` → Pick anchor keys), so 1QB is the comparable, and Superflex would not change any conclusion.

### So, at face value

**KTC's mid-2nd is 0.70 of its mid-1st. Ours is 0.387.** Read this way, our gap is not too small — it is **1.8× too large**, and the operator's intuition is backwards.

That reading does not survive the next section.

---

## The scale trap — why you cannot transplant KTC's ratio

Ratios are only comparable across two valuation scales if both are anchored at the same zero. These are not.

The tell is what a *worthless* asset costs. On KTC's 1QB board the 464 real players run from 9999 down to 172, and the cheapest pick on the entire board — a 2028 Late 4th — is **1505**, nearly nine times the value of the worst rostered player. KTC's numbers behave like "a large constant plus something", which drags every ratio toward 1. The companion memo found the same thing on the year axis: an offset fit collapsed KTC's apparent round-dependence in year decay at `c ≈ 555`, i.e. most of KTC's round gradient there was scale artifact, not opinion.

The decisive check is direct. **If we adopted KTC's 0.70 ratio literally**, our mid-2nd would be worth `0.70 × 2117.0 = 1482` in engine space. On our own board that is the **86th** most valuable asset in dynasty football. No source anywhere in this memo puts a mid-2nd higher than **103rd** (and that is KTC's own hyped 2027 class); the sober estimates are 134–169. Transplanting KTC's ratio would make our 2nds *wildly* overpriced, not correctly priced.

So the raw-ratio comparison is not usable. What is usable is a measure invariant to any monotone rescaling.

---

## The scale-free comparison: what player is a pick worth?

**The measure.** For each source, take its own player list, sort by its own values, and ask what rank the pick's value slots into. That question — *"a mid-2nd is worth roughly the Nth-best dynasty asset"* — is exactly what a user is being told when a trade card puts a 2nd against a player, and it is unchanged by any rescaling of either board.

**This comparison is only fair if the boards rank *players* the same way.** They do, and I measured it rather than assuming it. Matching FTF's blended board against KTC's 1QB list by name, over FTF's top 220:

| FTF rank band | n matched | median (KTC rank − FTF rank) |
|---|---|---|
| 50–80 | 30 | −2.5 |
| 100–140 | 39 | 0.0 |
| 140–180 | 39 | 0.0 |
| 180–220 | 39 | −1.0 |

216 of FTF's top 220 appear on KTC's top-500. **The two boards agree on players to within a rank or two.** Whatever they disagree about, it is the picks.

FTF's board here is the real thing: `data_loader.load_consensus_maps("1qb_ppr")` run against live DynastyProcess (`values-players.csv`, `scrape_date` 2026-08-14) blended with the live KTC pull at the prod default `ktc_blend_weight = 0.5` — 643 players, 439 KTC-matched. Pick rungs are compared in Elo space, where the seeds already live.

### The table that answers the question

Market median excludes KTC's 2027 column: the 2027 rookie class is hyped, which inflates every 2027 rung and is a class-quality effect, not a round effect. The 2026 and 2028 KTC columns, FantasyCalc's 2027 Early/Mid/Late rungs and DynastyProcess's 2027 rungs make up the median.

| Rung | **FTF** | KTC '26 | KTC '27 | KTC '28 | FC '27 | DP '27 | **market median** | FTF error |
|---|---|---|---|---|---|---|---|---|
| 1st Early | **48** | 34 | 18 | 49 | 29 | 43 | **38.5** | 10 too cheap |
| **1st Mid** | **65** | 64 | 35 | 66 | 67 | 77 | **66.5** | **−1.5 — exact** |
| 1st Late | **85** | 79 | 57 | 78 | 85 | 112 | **82.0** | 3 too cheap |
| 2nd Early | **101** | 109 | 86 | 124 | 116 | 139 | **120.0** | **19 too dear** |
| **2nd Mid** | **119** | 134 | 103 | 137 | 144 | 169 | **140.5** | **22 too dear** |
| 2nd Late | **136** | 144 | 125 | 158 | 176 | 193 | **167.0** | **31 too dear** |
| 3rd Early | **146** | 197 | 178 | 217 | 195 | 221 | **207.0** | 61 too dear |
| 3rd Mid | **165** | 227 | 196 | 236 | 200 | 242 | **231.5** | 67 too dear |
| 3rd Late | **193** | 235 | 212 | 250 | 206 | 259 | **242.5** | 50 too dear |
| 4th Early | **205** | 277 | 266 | 292 | 212 | 276 | **276.5** | 72 too dear |
| 4th Mid | **228** | 300 | 273 | 300 | 221 | 292 | **296.0** | 68 too dear |
| 4th Late | **257** | 307 | 300 | 339 | 231 | 302 | **304.5** | 48 too dear |

Three things fall straight out of it:

1. **The first round is right.** Our Mid 1st lands within 1.5 ranks of the market median, and the Early/Late rungs are within 10. Nothing about round 1 needs touching. If anything the Early 1st is slightly *cheap* — market says ≈ 38th, we say 48th.
2. **Every rung below round 1 is too expensive**, and the error is monotone in round: ~22 ranks at the 2nd, ~67 at the 3rd, ~68 at the 4th.
3. **Even KTC — read scale-free — says we overprice the 2nd.** KTC's own 2026 and 2028 mid-2nds sit at ranks 134 and 137. We put ours at 119. The source the operator named agrees with him once you stop comparing incommensurable ratios.

---

## Cross-checks: DynastyProcess and FantasyCalc

Neither source was used to *set* anything; both exist to stop one site's quirk from driving a repricing.

**DynastyProcess** — `files/values.csv`, `scrape_date` 2026-08-14, pulled 2026-08-19 05:02 UTC. The same file `data_loader.PICK_VALUES_URL` already fetches for its `pos == "PICK"` rows.

| 2027 rung | 1st | 2nd | 2nd:1st | 3rd:1st | 4th:1st |
|---|---|---|---|---|---|
| Early | 4240 | 401 | **0.095** | 0.014 | 0.003 |
| Mid | 1853 | 203 | **0.110** | 0.019 | 0.005 |
| Late | 837 | 108 | **0.129** | 0.026 | 0.008 |

**FantasyCalc** — `api.fantasycalc.com/values/current?isDynasty=true&numQbs=1&numTeams=12&ppr=1`, pulled 2026-08-19 05:02 UTC.

| 2027 rung | 1st | 2nd | 2nd:1st | 3rd:1st | 4th:1st |
|---|---|---|---|---|---|
| Early | 4325 | 1771 | **0.409** | 0.259 | 0.195 |
| Mid | 2848 | 1474 | **0.518** | 0.351 | 0.275 |
| Late | 2200 | 1273 | **0.579** | 0.415 | 0.330 |

### The raw ratios are useless; the ranks agree

Side by side, the mid-rung 2nd:1st ratio across the four boards is **0.110 (DP) · 0.387 (FTF) · 0.518 (FC) · 0.697 (KTC)** — a 6× spread that tells you nothing except that the four scales have different curvature. The *same four boards*, asked what player a mid-2nd is worth, answer **169 · 119 · 144 · 134** — a tight cluster with FTF as the clear outlier on the generous side.

That is the whole methodological argument of this memo in one line: **the ratios disagree by 6×, the ranks agree within ±25, and FTF is outside the cluster in the direction the operator guessed.**

DP is the extreme on both readings (steepest ratio, cheapest rank). Its pick curve is famously convex and near-zero-anchored — a 2027 Late 4th is 7 against an Early 1st of 4240 — so I weight it as one vote, not as a target.

---

## The within-round spread

FTF's Early → Late 1st runs 3004.2 → 1491.8, a **2.01:1** range; in rank terms, the 48th asset down to the 85th (a 37-rank span).

| Source | Early:Late 1st (value) | Early rank → Late rank | span |
|---|---|---|---|
| **FTF** | **2.014** | 48 → 85 | **37** |
| KTC 1QB 2026 | 1.314 | 34 → 79 | 45 |
| KTC 1QB 2027 | 1.325 | 18 → 57 | 39 |
| KTC 1QB 2028 | 1.215 | 49 → 78 | 29 |
| FantasyCalc 2027 | 1.966 | 29 → 85 | 56 |
| DynastyProcess 2027 | 5.066 | 43 → 112 | 69 |

On raw values KTC's first round looks dramatically flatter than ours (1.2–1.3 vs our 2.0) — the same compression artifact. **On ranks, FTF's 37-rank span sits inside KTC's own 29–45 range**, below FantasyCalc's 56 and well below DynastyProcess's 69. Our within-round spread is at the flat end of the market but is not an outlier, and no source supports steepening it.

**KTC does not publish twelve slots.** Its board carries exactly 36 pick rows — 3 years × 4 rounds × 3 tiers (Early/Mid/Late) — so the question "does KTC's spread across the twelve 1st-round slots look like ours" cannot be answered from KTC directly. The only source publishing all twelve is DynastyProcess, for the current year:

| Slot | value | rank | ratio to 1.01 |
|---|---|---|---|
| 2026 Pick 1.01 | 6818 | 17 | 1.000 |
| 1.02 | 6072 | 23 | 0.891 |
| 1.03 | 4866 | 34 | 0.714 |
| 1.04 | 3915 | 47 | 0.574 |
| 1.06 | 2563 | 64 | 0.376 |
| 1.08 | 1704 | 81 | 0.250 |
| 1.10 | 1150 | 94 | 0.169 |
| 1.12 | 787 | 112 | 0.115 |

DP's twelve slots span rank 17 → 112 (95 ranks) against our three-rung 48 → 85. That is a real gap, but it is comparing a twelve-slot ladder against a three-tier one and is the subject of the already-flagged M6b `market_slots` work, not of this memo. **No change to the within-round spread is proposed.**

---

## Direct answer to the operator's question

> *"It seems that the gap between a 1st and a second is not severe enough."*

**Correct.** 0.387 is **too high** — a 2nd should be worth relatively less against a 1st than we currently say.

The evidence, ordered by how much weight I put on it:

1. **The rank-equivalence table.** Our mid-2nd sits at the 119th asset; KTC says 134–137, FantasyCalc 144, DynastyProcess 169. We are the most generous board of the four, by 15–50 ranks, and our first round is simultaneously priced correctly — so the error is specifically the 1st-to-2nd step, not a global scale offset.
2. **A checked-in test already says so.** `test_pick_pricing_m6b.py::test_the_measured_reshaping_direction_is_deflation_not_inflation` asserts `delta(2026, 2) < -0.40` — that a 2026 2nd priced from DynastyProcess's real slot values is **more than 40 % cheaper** than our ladder's price for it, and that 2nds "collapse hardest" of any round. That is our own regression suite pinning the overprice as a known fact.
3. **KTC agrees once its scale is neutralised.** This matters because KTC is the source the operator named, and its published ratio (0.70) points the other way.

The one caveat worth stating plainly: **anyone quoting KTC's raw numbers will conclude the opposite.** If this comes up again, the counter is the 86th-best-asset check in [the scale trap](#the-scale-trap--why-you-cannot-transplant-ktcs-ratio) — adopting KTC's 0.70 would price a mid-2nd above Xavier Worthy and George Kittle, which no one in the market believes.

---

## Recalibration proposal — and why it is also a tier change

**Nothing here was applied.** `git diff origin/main -- backend/` in the branch that carries this memo is empty.

### Why this cannot be a quiet pricing tweak

`backend/tier_config.json`'s `_calibration` field, verbatim: *"first_1 floor = Late 1st seed 1580 (worth a 1st-round pick); second floor = Late 2nd 1400; third floor = Late 3rd 1280; fourth floor = Late 4th 1220."*

The Late rung of each round **is** that round's tier floor. Lowering the 2nd-round seeds necessarily lowers the `second` band's floor, which moves players up from `third` into `second` — coherently, since a cheaper 2nd means more players clear the "worth a 2nd" bar, but visibly, on every user's board, in every client that caches `GET /api/tier-config`. This is a **schema-and-invariants-class change under the bright line in CLAUDE.md**, not a quick fix.

### Option A — conservative, round 2 only (recommended if anything moves)

Touches the minimum number of moving parts, and closes most of the measured gap where the board still has resolution.

| Rung | Elo now | Elo proposed | value now | value proposed | rank now | **rank after** | market median | gap closed |
|---|---|---|---|---|---|---|---|---|
| 2nd Early | 1520 | **1470** | 1105.2 | 860.7 | 101 | **117** | 120 | 84 % |
| 2nd Mid | 1460 | **1400** | 818.7 | **606.5** | 119 | **136** | 140.5 | 79 % |
| 2nd Late | 1400 | **1370** | 606.5 | 522.0 | 136 | **141** | 167 | 16 % |

New mid 2nd:1st ratio: **0.287** (from 0.387). Rounds 1, 3 and 4 unchanged.

The Late rung barely moves because it is already sliding into the compressed part of the board described under Option B — 30 Elo points buy only 5 ranks there. That is a reason to stop at Option A, not a reason to push the Late seed harder.

Required companion edit, in the same commit: `tier_config.json` `second.min` 1400 → **1370** and `third.max` 1395 → **1365**, for all 8 (format, position) pairs. The ladder stays strictly ordered — the new Late 2nd (1370) still sits above the Early 3rd seed (1360), though the margin narrows from 40 Elo to 10.

**Measured tier-occupancy consequence** (against the same checked-in `dp_values_snapshot_2026-07-10.json` that `test_tier_occupancy.py` uses):

| format/pos | second now → after | third now → after | fourth | waivers | 1st-or-better |
|---|---|---|---|---|---|
| 1qb_ppr/QB | 10 → **12** | 7 → **5** | 10 | 54 | 13 |
| 1qb_ppr/RB | 11 → **13** | 16 → **14** | 18 | 113 | 23 |
| 1qb_ppr/WR | 24 → **27** | 17 → **14** | 27 | 133 | 36 |
| 1qb_ppr/TE | 8 → **10** | 12 → **10** | 10 | 90 | 9 |
| sf_tep/QB | 8 → **9** | 9 → **8** | 6 | 48 | 23 |
| sf_tep/RB | 8 → **13** | 18 → **13** | 26 | 109 | 20 |
| sf_tep/WR | 27 → **32** | 19 → **14** | 30 | 132 | 29 |
| sf_tep/TE | 8 → **10** | 10 → **8** | 16 | 87 | 8 |

Two to five players per position/format move from `third` up into `second`. Nothing else shifts: `fourth`, `waivers` and the four firsts tiers are untouched.

**Would it break `test_tier_occupancy.py`? No — verified, not modelled.** I applied Option A to a throwaway copy of the worktree under my scratchpad (never to the repo) and ran the file: **47 passed**. Every bound holds — `second` peaks at 32 against a ceiling of 35, `third` bottoms at 5 against a floor of 3.

**What it does break — the full suite on the same throwaway copy: 11 failed, 3405 passed, 1 skipped.** All eleven are value pins keyed to the old seeds, not logic failures, and each would need a deliberate retarget:

| File | What it pins |
|---|---|
| `test_pick_anchor.py` (2) | `_anchor_target_elo("1_second") == 1460`, and its position-uniformity twin |
| `test_pin_tier_bounded.py` (4) | the `second` band floor as a literal 1400 |
| `test_pick_pricing_m6b.py` (3) | the ladder being byte-unchanged in both pricing modes; **and `delta(2026, 2) < -0.40`, which stops holding at −0.284** |
| `test_league_picks_tier.py` (1) | the literal tier rung a pick row carries |
| `test_power_rankings.py` (1) | a "≈1 firsts" aggregate label that flips to "≈0.5 firsts" |

That `-0.40 → -0.284` movement is the honest scorecard for Option A: it is the distance the ladder travelled toward DynastyProcess's real market slot prices. Under Option A the two are 28 % apart instead of 40 %.

Also worth flagging: `test_tier_occupancy.py::test_anchor_rungs_land_in_matching_tiers` hard-codes `1460.0 → "second"`. It happens to still pass under Option A (1460 clears the new 1370 floor), but it is asserting the *Mid 2nd seed* and should be retargeted to 1400 so it keeps meaning what it says.

### Option B — full market alignment (measured, and not recommended)

Moving every rung to its market-median rank requires 2nd = 1456/1379/1314, 3rd ≈ 1300/1275/1255, 4th ≈ 1245/1235/1225 — mid ratios 0.258 / 0.153 / 0.126. **It fails `test_tier_occupancy.py` in three places:** `1qb_ppr/WR second = 36` and `sf_tep/WR second = 38` (ceiling 35), and `sf_tep/QB fourth = 2` (floor 5). It also breaks `test_anchor_rungs_land_in_matching_tiers` outright, because the Mid 3rd seed 1320 would bucket as `second`.

The deeper reason it does not work is structural, not a bounds problem. `seed_elo_for_value` maps DP value 0 → Elo 1200, so **our board has almost no resolution below rank ~200**: rank 230 sits at Elo 1238.8 and rank 300 at 1206.6 — 70 ranks inside 32 Elo points. The market-implied Elo for a Mid 4th is 1207, which is *inside the current `waivers` band*. The 3rd/4th divergence in the big table is therefore only partly a pricing error; a large part of it is the seed map's floor compression, and it cannot be fixed by moving seeds. **If the operator wants the 3rd and 4th repriced too, the seed map — not the pick ladder — is the thing to open.**

### Recommendation

Round 2 only (Option A), as one commit that moves the three seeds and the two band edges together, with the eleven pinned tests retargeted deliberately and a decision recorded. Round 1 stays exactly where it is — it is the one part of the ladder the market fully endorses. Round 3/4 gets logged as an open question against the seed map rather than patched here.

---

## Sources

Every number in this memo traces to one of these five pulls. Nothing is quoted from memory.

| Source | Exact endpoint | As-of | Pulled (UTC) |
|---|---|---|---|
| KeepTradeCut | `https://keeptradecut.com/dynasty-rankings` — embedded `playersArray`, `oneQBValues.value` / `superflexValues.value`, `position == "RDP"`; browser-confirmed at `?format=1` (`.5 PPR • 12 Tm. • No TEP`) | live | **2026-08-19 05:01** |
| DynastyProcess (picks) | `https://raw.githubusercontent.com/dynastyprocess/data/master/files/values.csv`, `pos == "PICK"`, `value_1qb` | `scrape_date` 2026-08-14 | **2026-08-19 05:02** |
| DynastyProcess (players) | `.../files/values-players.csv`, `value_1qb` | `scrape_date` 2026-08-14 | **2026-08-19 05:03** |
| FantasyCalc | `https://api.fantasycalc.com/values/current?isDynasty=true&numQbs=1&numTeams=12&ppr=1` | live | **2026-08-19 05:02** |
| FTF board | `data_loader.load_consensus_maps("1qb_ppr")` on the two DP files + the KTC pull, `ktc_blend_weight = 0.5` (prod default) — 643 players, 439 KTC-matched | — | **2026-08-19 05:03** |

No page or API response contained text addressed to an agent, and nothing in them was treated as an instruction.

---

## What I could not determine

- **Whether KTC's crowd is pricing an *average* 2nd or an *anonymous* 2nd.** KTC's Early/Mid/Late tiers are crowd-voted composites with no published definition of which slots they span. If "Mid 2nd" means picks 2.05–2.08 to voters but our Mid 2nd rung means "an unknown 2nd", the two are not quite the same asset. This is the single largest unquantified error term in the rank table.
- **KTC publishes no per-slot pick values**, so question 3's twelve-slot comparison could only be answered from DynastyProcess. Whether KTC's crowd would spread twelve slots as widely as DP does is unknown.
- **KTC's 1QB board is 0.5 PPR, not full PPR** (the page's own settings line). FTF's `1qb_ppr` is full PPR. Pick values are position-uniform in both systems so the effect should be nil, but it was not measured.
- **Whether the overpriced 2nd is actually costing us accepted trades.** I did not query `deck_impressions` or `swipe_decisions` for cards where a 2nd was the swing asset. The companion memo established that picks appear in 58.5 % of served cards but that 2nds are only 279 of 1763 pick mentions — so the blast radius of a 2nd-round repricing is real but an order of magnitude smaller than the first-round change that shipped tonight. **This is the number I would want before touching pricing**, and it is a read-only prod query away.
- **What Option A does to served deck composition.** Occupancy I measured; deck output I did not — that needs the bake-off harness, and it would confound with D-079, which shipped hours ago and whose own deck effect is not yet observed in prod.
- **Whether the seed map's floor compression is a defect or a deliberate choice.** Everything below roughly rank 200 collapses into 40 Elo points, which is what makes the 3rd/4th rungs unfixable via seeds. `seed_elo_for_value`'s docstring explains the *top* of the affine map (DP 10000 → the 4-firsts rung) but says nothing about whether the bottom's compression was intended.
- **Paywalled sources** — Footballguys Trade Value Chart Plus, DynastyLeagueFootball, Dynasty Nerds — were not consulted, same as in the companion memo.
