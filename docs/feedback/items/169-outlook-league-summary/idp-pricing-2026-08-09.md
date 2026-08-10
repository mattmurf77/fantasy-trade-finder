# #169 Outlook Odds — BUG-5: IDP and kicker starting slots are unpriced

**Date:** 2026-08-09 · **Author:** worktree fix agent (BUG-5) · **Branch:** `worktree-agent-ad46ed229323d0421`
**Subject:** `RosterValueStrength` prices a team's starting lineup with a board that contains no defensive player and no kicker. In the operator's FFv3 league — **4 of the 6 backtested league-seasons** — that is **8 of 15 starting slots**.
**Scope guard:** `outlook.odds` stays dark. No feature flag touched, `config/features.json` untouched, no mobile change, no `model_config` key added. The only behaviour change is a *provably prediction-neutral* selection fix; everything else here is measurement.

> **Three lines:**
> 1. The defect is real and larger than it looks: **53.3 % of FFv3's starting slots price at exactly 0.0**, covering **~33 % of the points those teams actually scored**. Lakeview is unaffected (0 %).
> 2. **It is a missing signal, not a bias.** The unpriced slots contribute 0.0 to *every* team, so they cancel in `RosterValueStrength`'s cross-team z-score. The published preseason numbers (Brier 0.1959, +21.6 %) are arithmetically correct — they just describe a model that ranks IDP teams on their **offensive core alone**, which is not what the report said it was measuring.
> 3. **No available fix beats the status quo.** No license-clean dynasty IDP value board exists (verified, not assumed). Both candidate workarounds were backtested: a league-mean fallback is **worse** (Δ Brier +0.0005) and coverage attenuation is **inside the noise** (−0.0019, CI [−0.0167, +0.0070]). Shipped: the slot-eligibility correctness fix (0/72 predictions moved) and a `lineup_pricing()` instrument so the surface can say so honestly.

---

## Table of contents

- [1. The defect](#1-the-defect)
- [2. Quantifying the damage](#2-quantifying-the-damage)
- [3. Why it does not distort the preseason numbers](#3-why-it-does-not-distort-the-preseason-numbers)
- [4. The pricing decision — options, and what was verified](#4-the-pricing-decision--options-and-what-was-verified)
- [5. Validation — before/after, split by league](#5-validation--beforeafter-split-by-league)
- [6. What shipped](#6-what-shipped)
- [7. What this does not support](#7-what-this-does-not-support)
- [8. Reproducing](#8-reproducing)

---

## 1. The defect

`backend/outlook/strength.py::RosterValueStrength` estimates a team's weekly
scoring mean from the dynasty value of its greedily-selected starting lineup.
The value map it is handed comes from the DynastyProcess board, and that board
is offence-only:

```
values-players.csv  (live, 2026-08-09)  676 rows
  WR 251 · RB 196 · TE 133 · QB 96 · zero IDP · zero K
values.csv          (combined)          761 rows = the same 676 + 85 PICK rows
```

There is no `values-idp.csv` in the repository (`files/` listing checked in
full, §4). The operator's leagues:

| League | Starting slots |
|---|---|
| Lakeview | `QB,RB,RB,WR,WR,WR,TE,FLEX,FLEX,SUPER_FLEX` |
| **FFv3** | `QB,RB,RB,WR,WR,TE,FLEX,`**`K,DL,DL,LB,LB,DB,DB,IDP_FLEX`** |

Every bolded slot prices at exactly 0.0.

**A second, compounding defect in the same function.** `select_starting_lineup`
matched a slot name against the player's `position` string. That is correct for
QB/RB/WR/TE/K, where slot name and position coincide — but Sleeper names a
*defensive* slot after the fantasy position **group** (`DL`, `LB`, `DB`) while a
player's `position` is his NFL position (`DE`, `DT`, `NT`, `OLB`, `CB`, `SS`,
`FS`). So a `DL` slot only ever accepted a player literally labelled "DL", and
`IDP_FLEX` — which matches no position at all — accepted nobody. Across the four
FFv3 league-seasons (12 teams × 15 slots = 180 slot-instances each), **25–33
slots were left completely empty**, on top of the 63–71 filled with a 0-priced
player. Exactly 84 — the 7 offensive slots × 12 teams — carried a price.

---

## 2. Quantifying the damage

### 2.1 Starting-slot share, at the period-correct kickoff board

| league-season | starting slots | priceable | unpriceable | **unpriced slot share** | unpriceable slots |
|---|---|---|---|---|---|
| lakeview-2025 | 10 | 10 | 0 | **0.0 %** | — |
| lakeview-2024 | 10 | 10 | 0 | **0.0 %** | — |
| ffv3-2025 | 15 | 7 | 8 | **53.3 %** | K, DL, DL, LB, LB, DB, DB, IDP_FLEX |
| ffv3-2024 | 15 | 7 | 8 | **53.3 %** | K, DL, DL, LB, LB, DB, DB, IDP_FLEX |
| ffv3-2023 | 15 | 7 | 8 | **53.3 %** | K, DL, DL, LB, LB, DB, DB, IDP_FLEX |
| ffv3-2022 | 15 | 7 | 8 | **53.3 %** | K, DL, DL, LB, LB, DB, DB, IDP_FLEX |

Slot *value* share is the degenerate version of the same table: **100 % of the
value `starting_lineup_value()` returns for an FFv3 team comes from 7 of its 15
slots**, because the other 8 contribute 0.0 by construction.

### 2.2 The number that actually matters — realised scoring

Slot count over-states the blindness (an IDP slot scores less than a WR slot).
The honest denominator is what those slots really produced, taken from Sleeper's
own `starters_points`, weeks 1–14:

| league-season | total pts | priceable slots | unpriced slots | **unpriced points share** |
|---|---|---|---|---|
| lakeview-2025 | 22,231 | 22,231 | 0 | **0.0 %** |
| lakeview-2024 | 22,891 | 22,891 | 0 | **0.0 %** |
| ffv3-2025 | 21,590 | 14,375 | 7,215 | **33.4 %** |
| ffv3-2024 | 21,514 | 14,363 | 7,150 | **33.2 %** |
| ffv3-2023 | 21,698 | 14,253 | 7,445 | **34.3 %** |
| ffv3-2022 | 21,725 | 14,553 | 7,172 | **33.0 %** |

**A third of every FFv3 team's scoring is invisible to the preseason model.**

### 2.3 …but the invisible third barely separates teams

Between-team spread of season points, by slot class:

| league-season | sd(priceable pts) | sd(unpriced pts) | sd(total) | ρ(unpriced pts, wins) |
|---|---|---|---|---|
| ffv3-2025 | 182 | 62 | 179 | +0.149 |
| ffv3-2024 | 160 | 59 | 169 | +0.309 |
| ffv3-2023 | 211 | 65 | 214 | +0.000 |
| ffv3-2022 | 182 | 58 | 205 | +0.347 |

The unpriced third of the scoring carries roughly **one third of the offence's
between-team spread** — about 10 % of total between-team variance. That is not
nothing, but it bounds how much a perfect IDP board could ever have bought here,
and it is the reason §5's fixes measure flat.

Corroborating: Spearman(season points, wins) is +0.657 for the offensive core
alone vs +0.830 for the full lineup in `ffv3-2024`, but the two are within noise
of each other in the other three seasons (+0.853/+0.867, +0.819/+0.769,
+0.835/+0.860).

---

## 3. Why it does not distort the preseason numbers

`RosterValueStrength` maps lineup value to a scoring mean through a **cross-team
z-score**:

```
mu_i = MEAN_POINTS + POINTS_PER_VALUE_SD * (v_i - mean(v)) / sd(v)
```

Every team in a league has the *same* slot shape, so the unpriced slots
contribute exactly 0.0 to every `v_i`. A constant additive term cancels in both
the numerator and the standard deviation. **The unpriced slots are therefore a
missing signal, not a systematic bias**: no team is advantaged or penalised
relative to another by the gap.

Three consequences, all load-bearing:

1. **The published preseason figures are arithmetically correct.** Playoff Brier
   0.1959, +21.6 %, and the six per-league-season values in
   [`dated-values-revalidation-2026-08-09.md`](dated-values-revalidation-2026-08-09.md) §3
   were reproduced here bit-for-bit as the V0 baseline. They do not need re-measuring.
2. **They do need re-describing.** For 4 of the 6 league-seasons, "preseason
   strength from starting-lineup value" means *from the offensive core only*.
   The revalidation report's "starting-slot coverage **100.0 %**" row (§2.3) is
   a **QB/RB/WR/TE-only** coverage figure — it silently excluded the eight slots
   that had no chance of being covered. That row is the single most misleading
   line in the prior analysis and is corrected inline there.
3. **"Normalise by the priceable share" is a mathematical no-op.** Dividing
   every `v_i` by the same constant leaves `z` unchanged. It is a labelling
   change, which is why this pass ships the label (`lineup_pricing()`) and not
   a renormalisation.

---

## 4. The pricing decision — options, and what was verified

### 4.1 A free IDP value source — **does not exist**

Every claim below was checked live on 2026-08-09, not inferred.

| Source | Checked | Result |
|---|---|---|
| **DynastyProcess `values-players.csv` / `values.csv`** | full `files/` listing via the GitHub contents API + both CSVs parsed | **QB/RB/WR/TE + PICK only.** No `values-idp.csv`, no IDP rows, no K rows. The `archives/` folder holds `database.csv`, `debunking-trading-up.csv`, `RAS/`, `fantasypros/`, `workbooks/` — no values file. |
| **nflverse / `nflreadpy`** | already a documented dependency; `projection-source-research.md` | Publishes **historical stats, rosters, schedules** and no dynasty values of any kind. Its `load_ff_rankings()` is a **relay of DynastyProcess's FantasyPros scrape**, not an independent source. License is the cleanest available (CC-BY 4.0 data / MIT package) but there is nothing here to read. |
| **DynastyProcess `db_fpecr_latest.csv`** | fetched, parsed | Does contain IDP — a `dynasty-idp` page with **exactly 100 players** (50 LB / 30 DL / 20 DB), plus redraft IDP pages. Three problems, any one disqualifying: (a) it is a **FantasyPros scrape**, and FantasyPros is the ToS landmine `projection-source-research.md` §"landmines" already ruled out for production — relaying it through a third party does not launder it; (b) it is an **ECR rank**, not a value, so putting it on the board's 0–10000 scale requires an invented rank→value curve — that *is* fabricating IDP values, with extra steps; (c) 100 ranked players does not even cover a 12-team league's 84 IDP starters plus benches. |
| **FantasyCalc** | live API call, dynasty values | **475 rows: WR/RB/QB/TE + PICK. Zero IDP.** (ToS also still unverified per the research doc.) |
| **KeepTradeCut** | existing FTF blend | Offence-only, and an unsanctioned HTML scrape FTF already treats as fail-soft-only. |
| **Sleeper `search_rank`** | considered | Sleeper's bulk player dump does rank IDP players, on the API FTF already uses. Rejected: it is a redraft-popularity ordinal, not a dynasty value; mapping it onto the DP scale is again an invented curve; and the bulk dump is **current-state only**, so any model built on it is *unbacktestable* — it could never clear the bar the rest of #169 was held to. |

**Verdict: there is no license-clean, dated, dynasty-scaled IDP value board.**
Nothing was added to `docs/integrations/`, because no source was added.

### 4.2 A position-agnostic fallback — **rejected on measurement and on principle**

*"Price unpriced starters at the league-wide mean so a filled IDP slot
contributes something."* Implemented as **V2** and backtested.

It fails on principle before it fails on measurement. Because the mean is the
same for every team, the only cross-team variation it can introduce is **how
many unpriceable slots each team happens to fill** — which, given the board
prices none of them, is an artefact of roster composition and NFL position
labels, not of team quality. It manufactures differentiation out of a data
artefact. Measured, it is also mildly **worse** (§5).

### 4.3 Scoping to priceable slots — **shipped as a label, not as arithmetic**

Renormalising by the priced share cannot move a prediction (§3). What it *can*
do is stop the surface claiming a whole-lineup estimate it does not have. That
is `lineup_pricing()`: it returns the total slot count, the priceable count and
the exact unpriceable slot names for a league, computed from the board's own
position universe rather than a hard-coded position list — so a future board
that does price defenders needs no change here.

The stronger version — **attenuating the z-score by the priced share**, so an
IDP league's odds are correspondingly less confident — is the one option with a
real statistical motivation, and it was backtested in two forms (**V3 linear**
and **V3 sqrt**). §2.3 predicts it should barely matter, and §5 confirms it.

### 4.4 The eligibility fix — **shipped, and provably prediction-neutral**

Independent of pricing, `select_starting_lineup()` was returning a *wrong
lineup* for IDP leagues: empty defensive slots and an `IDP_FLEX` that matched
nothing. That is a correctness bug in a function whose contract is "which
players are starting", and it already has a consumer that reads the selection
rather than the sum (`bye_multiplier.py`). It is fixed here with an explicit
slot → eligible-positions map.

The fix **cannot** change any prediction while the board prices no defender —
every newly-selectable player is worth 0.0 — and that is asserted rather than
assumed, both by a per-team test against the verbatim pre-fix algorithm and by
the backtest (**0 of 72 predictions moved**).

### 4.5 What was deliberately not done

- **No invented IDP values.** No rank→value curve, no positional heuristic, no
  synthetic board.
- **No `model_config` knob** for an attenuation the evidence does not support.
  Adding a dark, unvalidated tuning surface is how the roster-value knobs got
  flagged "unvalidated" in the first place.
- **No gate on IDP leagues.** The measured skill in the IDP league (Brier
  0.1789) is *better* than in the fully-priced one (0.2298), so "gate IDP
  leagues out of odds entirely" is not supported by this data. What is
  supported is labelling.
- **`FB` was not added to `RB` eligibility.** It is a real (tiny) eligibility
  gap of the same family, but it touches offensive selection in *both* leagues
  and is out of BUG-5's scope. Logged here so it is not lost.

---

## 5. Validation — before/after, split by league

Same rewound as-of-week-0 state, same real week-1 rosters, same period-correct
kickoff board, same seed, **10,000 sims**, scored against the same reality.
Five pricings of the identical state:

| variant | what it does |
|---|---|
| **V0** | status quo — the shipped provider with the verbatim pre-BUG-5 selection |
| **V1** | eligibility fix only (shipped) |
| **V2** | V1 + every unpriceable *filled* slot priced at the league's mean priced-slot value |
| **V3 sqrt / linear** | V1 + z scaled by √coverage / coverage |

**V0 reproduces the published baseline exactly** — playoff Brier 0.1959, title
0.0740, +21.6 % skill, and all six per-league-season values match
[`dated-values-revalidation-2026-08-09.md`](dated-values-revalidation-2026-08-09.md)
§3.5 and §5 to four decimals. The harness is measuring the same thing the parent
report measured.

### 5.1 The IDP league — FFv3, 4 seasons, n = 48

| variant | playoff Brier | skill vs clim | title Brier | Δ playoff vs V0 | 90 % CI | reading |
|---|---|---|---|---|---|---|
| **V0 status quo** | **0.1789** | +28.4 % | 0.0673 | — | — | baseline |
| **V1 eligibility fix** | **0.1789** | +28.4 % | 0.0673 | **+0.0000** | [+0.0000, +0.0000] | **identical, as designed** |
| V2 league-mean fallback | 0.1794 | +28.2 % | 0.0709 | +0.0005 | [−0.0056, +0.0061] | indistinguishable (nominally worse) |
| V3 attenuation (sqrt) | 0.1770 | +29.2 % | 0.0670 | −0.0019 | [−0.0167, +0.0070] | indistinguishable |
| V3 attenuation (linear) | 0.1831 | +26.7 % | 0.0676 | +0.0042 | [−0.0242, +0.0205] | indistinguishable (nominally worse) |

### 5.2 The non-IDP league — Lakeview, 2 seasons, n = 24

| variant | playoff Brier | Δ playoff vs V0 | reading |
|---|---|---|---|
| V0 status quo | 0.2298 | — | baseline |
| V1 / V2 / V3 sqrt / V3 linear | **0.2298** | **+0.0000** | **bit-identical under every variant** |

This is the requirement the brief set, and it holds **by construction, not by
luck**: Lakeview's coverage is 1.0, so no unpriced-slot policy can reach it. It
is pinned by a test.

### 5.3 Pooled, and per league-season

| variant | playoff Brier (n = 72) | skill vs clim | title Brier |
|---|---|---|---|
| V0 status quo | 0.1959 | +21.6 % | 0.0740 |
| V1 eligibility fix | 0.1959 | +21.6 % | 0.0740 |
| V2 league-mean fallback | 0.1962 | +21.5 % | 0.0764 |
| V3 attenuation (sqrt) | 0.1946 | +22.2 % | 0.0738 |
| V3 attenuation (linear) | 0.1987 | +20.5 % | 0.0742 |

| league-season | V0 | V1 | V2 | V3 sqrt | V3 linear | climatology |
|---|---|---|---|---|---|---|
| lakeview-2025 | 0.1806 | 0.1806 | 0.1806 | 0.1806 | 0.1806 | 0.2500 |
| lakeview-2024 | 0.2789 | 0.2789 | 0.2789 | 0.2789 | 0.2789 | 0.2500 |
| ffv3-2025 | 0.1528 | 0.1528 | 0.1615 | 0.1567 | 0.1689 | 0.2500 |
| ffv3-2024 | 0.2812 | 0.2812 | 0.2718 | **0.2557** | **0.2409** | 0.2500 |
| ffv3-2023 | 0.1372 | 0.1372 | 0.1416 | 0.1468 | 0.1612 | 0.2500 |
| ffv3-2022 | 0.1446 | 0.1446 | 0.1427 | 0.1489 | 0.1616 | 0.2500 |

The per-season table is the whole story of the attenuation variants: they help
in exactly the one season where the preseason board carried no information
(`ffv3-2024`, ordering correlation +0.022) and hurt in the three where it did.
That is what shrinkage toward the mean always does, it is the same effect the
parent report already reported as an in-sample λ sweep (§3.5 there), and it is
not evidence about IDP.

### 5.4 Verdict

**The defect is real. No available fix beats the status quo.**

- The **eligibility fix ships** — it is a correctness fix with a measured
  0-of-72 prediction delta.
- The **league-mean fallback is rejected** — nominally worse, and its only
  source of differentiation is a data artefact.
- The **attenuation is not shipped** — its point estimate is a 1 % Brier
  improvement whose CI is an order of magnitude wider, it is driven by one
  season, and §2.3 gives an independent reason to expect it to be small.
- **The preseason verdict from
  [`dated-values-revalidation-2026-08-09.md`](dated-values-revalidation-2026-08-09.md)
  §4 is unchanged**: playoff odds conditional-go (banded, not a precise
  percentage, BUG-1 fixed first); title odds no-ship. What changes is the
  *description*: in an IDP league that number is an offensive-core estimate and
  must be labelled as one.

---

## 6. What shipped

| Change | File | Effect on predictions |
|---|---|---|
| Slot → eligible-positions map incl. IDP groups (`eligible_positions()`), used by `select_starting_lineup()` | `backend/outlook/strength.py` | **None** (0/72), asserted |
| `lineup_pricing()` / `LineupPricing` — measures the priced share of a league's starting lineup | `backend/outlook/strength.py` | None — pure measurement |
| BUG-5 recorded in the module docstring next to the existing calibration warning | `backend/outlook/strength.py` | None |
| 30 tests: board-premise pin, coverage detection on all 6 real league-seasons, eligibility behaviour, the neutrality invariant vs the verbatim pre-fix algorithm, offence-only bit-identity, records-based verdict guards | `backend/tests/test_outlook_idp_pricing.py` | — |
| The five-variant backtest | `scripts/outlook_idp_pricing_backtest.py` + `backend/tests/fixtures/outlook-hypotheses/idp-pricing-backtest-records.json` | — |

### Follow-up, explicitly not done here

**`lineup_pricing()` is not wired into the payload.** The `meta` block is built
in `backend/outlook/serialize.py`, which a parallel agent owns this session. The
wiring is one line — `meta["priced_slot_coverage"]` (or the fuller
`{total_slots, priceable_slots, unpriceable_slots}`) — and it is what lets the
UI say *"based on your offensive starters — this league's IDP and K slots aren't
priced"* instead of showing an unqualified number. **This should land before
`outlook.odds` lights for any IDP league.**

---

## 7. What this does not support

- **Two leagues, one IDP format.** Every IDP measurement here is FFv3 —
  4 league-seasons, 4 bootstrap clusters, one slot shape. Nothing here
  generalises to IDP-heavy formats (6+ defensive starters), tackle-heavy
  scoring, or DEF/ST leagues.
- **Nothing is said about K leagues separately.** The kicker slot is folded into
  the same 8 and never isolated.
- **§2.2/§2.3 are retrospective.** They measure what IDP slots *did* score, not
  what a value board could have *predicted*. They bound the opportunity; they do
  not measure a fix.
- **The V3 attenuation was not tuned, and must not be.** Both forms are a-priori
  functions of coverage. Reading §5.3 and picking the best cell would be
  in-sample fitting on 4 clusters — the same trap the parent report flagged for λ.
- **The confound between the two leagues is total.** FFv3 is the IDP league *and*
  the H2H-only, 1QB league; Lakeview is the fully-priced *and* median-match,
  superflex/TEP league. Cross-league comparisons here are descriptive only.
- **BUG-1's simulation half is inside every FFv3-vs-Lakeview comparison**, exactly
  as in the parent report.
- **In production the gap is wider than the fixtures show.** `data_loader.VALID_POSITIONS`
  is `{QB, RB, WR, TE}`, so the live universal pool contains no IDP player at
  all — the route's `player_pos` resolves them to `"?"`, not to `DE`/`CB`. The
  eligibility fix is therefore inert on the live path until a position map that
  covers defenders reaches `/api/league/outlook`; `lineup_pricing()` reports the
  slots as unpriceable either way, which is the number that matters.

---

## 8. Reproducing

```bash
# five-variant preseason backtest (offline, ~20 min at 10k sims)
python3 scripts/outlook_idp_pricing_backtest.py --sims 10000

# permanent tests
python3 -m pytest backend/tests/test_outlook_idp_pricing.py -q
```

| Artefact | Path |
|---|---|
| Fix + instrument | `backend/outlook/strength.py` |
| Backtest | `scripts/outlook_idp_pricing_backtest.py` |
| Per-team records (5 variants × 72 team-seasons) | `backend/tests/fixtures/outlook-hypotheses/idp-pricing-backtest-records.json` |
| Tests | `backend/tests/test_outlook_idp_pricing.py` |
| Reused unmodified | `scripts/outlook_calibration_backtest.py`, `scripts/outlook_preseason_backtest.py`, `backend/dp_values_history.py`, the dated boards in `backend/tests/fixtures/dp-values-history/` |
| Parent reports | [`dated-values-revalidation-2026-08-09.md`](dated-values-revalidation-2026-08-09.md), [`calibration-report-2026-08-09.md`](calibration-report-2026-08-09.md), [`projection-source-research.md`](projection-source-research.md) |

Test posture: backend suite **2217 passed / 1 skipped / 1 xfailed** before this
work (fresh `origin/main` at `359a0ff`) → **2247 passed / 1 skipped / 1 xfailed**
after, exit 0.
