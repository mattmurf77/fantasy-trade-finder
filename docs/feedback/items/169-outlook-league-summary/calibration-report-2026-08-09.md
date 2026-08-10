# #169 Outlook Odds — Calibration Report

**Date:** 2026-08-09 · **Author:** calibration/validation agent · **Branch:** `outlook-calibration`
**Subject:** the dark playoff/championship-odds engine in `backend/outlook/` (flag `outlook.odds`, default false)
**Purpose:** decide whether the engine is accurate enough to ever light up. The operator rules on the verdict; this document is written so they can.

> **Verdict in one line:** the **playoff-odds** number has real, statistically
> demonstrated skill and is ready to ship once **BUG-1 is fixed**; the
> **title-odds** number has **no demonstrated skill** at this sample and must
> not ship as a headline figure. Overall: **MARGINAL PASS, conditional.**

---

## Table of contents

- [1. What was validated, and what was not](#1-what-was-validated-and-what-was-not)
- [2. Method](#2-method)
- [3. Tier 1 — backtest against reality](#3-tier-1--backtest-against-reality)
- [4. Sample size and what it does not support](#4-sample-size-and-what-it-does-not-support)
- [5. Tier 2 — cross-source agreement](#5-tier-2--cross-source-agreement)
- [6. Tier 3 — internal invariants](#6-tier-3--internal-invariants)
- [7. Bugs found](#7-bugs-found)
- [8. Calibration evidence for the flagged knobs](#8-calibration-evidence-for-the-flagged-knobs)
- [9. Proposed pass bar and verdict](#9-proposed-pass-bar-and-verdict)
- [10. Reproducing this report](#10-reproducing-this-report)

---

## 1. What was validated, and what was not

| Pipeline phase | Validated? | How |
|---|---|---|
| Phase 1 `LeagueStateProvider` | **Partially — and it has a severe bug** | Replayed against 6 real captured seasons; reproduces Sleeper's own final W/L exactly *only once you account for median-match scoring*, which the shipped code does not. See [BUG-1](#7-bugs-found). |
| Phase 2 `TrailingScoresStrength` | **Yes** | This is what `auto` resolves to at every as-of week tested (3/6/9/12). |
| Phase 2 `RosterValueStrength` | **NO — not backtestable** | It needs a *historical* dynasty value board. Sleeper exposes no historical rosters and FTF has no dated value snapshots, so there is no honest way to score the preseason default. This is the single biggest gap in this report. |
| Phase 3 `simulate()` | **Yes** | Backtest + 22 permanent invariant tests. |
| Phase 4 `StandardFormat` | **Indirectly** | Ground truth is taken from Sleeper's own bracket, so seeding errors surface as prediction error. One unmodelled setting found (`playoff_seed_type`, [BUG-3](#7-bugs-found)). |
| Phase 5 `serialize` | **Yes** | Existing tests + payload used throughout the backtest. |

**The most important caveat in this document:** the headline Brier numbers score
**Phases 2–5 fed with clean, correctly-rewound standings**. They do *not* score
the shipped Phase-1 ingestion path, because the as-of rewind the backtest needs
also happens to bypass BUG-1. The shipped path's separate measurement is in
[§7](#7-bugs-found).

---

## 2. Method

### Data

Six completed seasons of the operator's two real Sleeper dynasty leagues, found
by following `previous_league_id` back from the league ids in
`data/trade_finder.db` (`leagues`, platform `sleeper`):

| Fixture | League | Season | Sleeper league id | Teams | Reg. weeks | Slots | Median match |
|---|---|---|---|---|---|---|---|
| `lakeview-2025` | Lakeview League | 2025 | `1180999595377590272` | 12 | 14 | 6 | **yes** |
| `lakeview-2024` | Lakeview League | 2024 | `1101407304802574336` | 12 | 14 | 6 | **yes** |
| `ffv3-2025` | Fantasy Football V3 | 2025 | `1181674778942836736` | 12 | 14 | 6 | no |
| `ffv3-2024` | Fantasy Football V3 | 2024 | `1048263304533188608` | 12 | 14 | 6 | no |
| `ffv3-2023` | Fantasy Football V3 | 2023 | `916436765509046272` | 12 | 14 | 6 | no |
| `ffv3-2022` | Fantasy Football V3 | 2022 | `867593839303598080` | 12 | 14 | 6 | no |

Plus the two **current 2026** leagues for Tier 2 (`1312076055586050048` Lakeview,
`1312140920132497408` FFv3) and a 14-week 2026 Sleeper projections capture.

Every response is committed under `backend/tests/fixtures/outlook-calibration/`
(public read-only API, captured 2026-08-09), so the backtest is repeatable
offline and never re-fetches. The projections fixture is slimmed (documented
in its `_note`); everything else is raw.

### As-of semantics (no look-ahead)

The shipped `SleeperLeagueState.load()` reads standings off `/rosters`, which
for a completed season are **final** — running it unmodified on a past season
leaks the answer and leaves nothing to simulate. So the harness loads the real
full-season state **through the shipped provider**, then rewinds it to week W:

- wins / losses / ties / points_for **recomputed from weeks 1..W only**;
- `weekly_scores` truncated to weeks 1..W;
- `completed_weeks = W`.

Everything else the simulator reads is genuinely known before kickoff. The one
arguable item — the remaining-week pairing schedule — was **validated
empirically**, not assumed (see [BUG-2](#7-bugs-found)), and a
no-future-schedule variant is reported to bound its value.

The rewind is itself tested: replaying all 14 weeks reproduces Sleeper's own
reported final W/L **exactly for all 72 team-seasons**
(`test_as_of_rewind_reproduces_sleepers_own_final_standings`).

### Ground truth

From Sleeper's `/winners_bracket` — the union of concrete `t1`/`t2` entries is
the real playoff field (asserted to equal `playoff_teams`), and the winner of
the match with `p == 1` is the champion. Using the bracket rather than
re-deriving standings means FTF's own seeding logic is *being scored*, not
assumed correct.

### Baselines

| id | Definition |
|---|---|
| **B1 climatology** | `playoff_slots / team_count` = 0.500 playoff for everyone; `1/12` = 0.0833 title for everyone. |
| **B2 standings-hard** | Rank by as-of (win_credit, points_for). Top 6 → playoff 1.0, rest 0.0; rank 1 → title 1.0. |
| **B3 standings-shrunk** | `0.5 × B2 + 0.5 × B1` — a deliberately *stronger* baseline so B2 is not a strawman. |

Scored with Brier (primary), log-loss (secondary), a 10-bucket calibration
table, and a **cluster bootstrap over the 6 league-seasons** for confidence
limits. Monte-Carlo N = 10,000 (the shipped default).

---

## 3. Tier 1 — backtest against reality

### Headline (all four as-of weeks pooled, n = 288 team-week predictions)

| Predictor | Playoff Brier | Skill vs B1 | Title Brier | Skill vs B1 |
|---|---|---|---|---|
| **Outlook engine** | **0.1113** | **+55.5 %** | **0.0725** | **+5.1 %** |
| B1 climatology | 0.2500 | — | 0.0764 | — |
| B2 standings-hard | 0.1806 | +38.3 % | 0.1319 | +45.0 % |
| B3 standings-shrunk | 0.1528 | +27.1 % | 0.0851 | +14.8 % |

Log-loss: playoff 0.4131, title 0.2578.

**The engine beats all three baselines on playoff odds.** On title odds it
beats the two standings extrapolations comfortably but is barely distinguishable
from climatology.

### Confidence — cluster bootstrap over 6 league-seasons, 90 % interval

| Quantity | Point estimate | 90 % CI | Reading |
|---|---|---|---|
| Playoff skill vs climatology | **+55.5 %** | **[+44.5 %, +65.9 %]** | **excludes 0 — real skill** |
| Title skill vs climatology | **+5.1 %** | **[−13.2 %, +22.3 %]** | **includes 0 — no demonstrated skill** |

The league-season is the only defensible resampling unit: the 12 team-seasons
inside a league are mechanically dependent (exactly 6 make the playoffs,
exactly 1 wins). Six clusters is a very small bootstrap and the interval should
be read as *wide*, not *precise*.

### Per as-of week (n = 72 each)

| as-of week | Model playoff | B1 | B2 | B3 | Model title | B1 | B2 | B3 |
|---|---|---|---|---|---|---|---|---|
| 3 | 0.1972 | 0.2500 | 0.2778 | 0.2014 | **0.0953** | **0.0764** | 0.1667 | 0.1024 |
| 6 | 0.1204 | 0.2500 | 0.1944 | 0.1597 | 0.0694 | 0.0764 | 0.1389 | 0.0885 |
| 9 | 0.0729 | 0.2500 | 0.1389 | 0.1319 | 0.0628 | 0.0764 | 0.0833 | 0.0608 |
| 12 | 0.0548 | 0.2500 | 0.1111 | 0.1181 | 0.0626 | 0.0764 | 0.1389 | 0.0885 |

Two things to notice:

1. **Playoff odds improve monotonically** with information (0.197 → 0.055) and
   beat every baseline at every week. That is exactly the shape a working
   simulator should have.
2. **At week 3 the title number is WORSE than climatology** (0.0953 vs 0.0764)
   and barely better than it at weeks 6 and 9 — at week 9 B3 actually wins
   (0.0608 vs 0.0628). Early-season title odds are, on this evidence, actively
   misleading.

### Calibration — playoff odds (pooled)

| bucket | n | mean predicted | realized | gap |
|---|---|---|---|---|
| 0.0–0.1 | 90 | 0.012 | 0.044 | +0.032 |
| 0.1–0.2 | 20 | 0.164 | 0.350 | +0.186 |
| 0.2–0.3 | 18 | 0.254 | 0.333 | +0.080 |
| 0.3–0.4 | 9 | 0.354 | 0.444 | +0.091 |
| 0.4–0.5 | 10 | 0.465 | 0.100 | −0.365 |
| 0.5–0.6 | 8 | 0.554 | 0.625 | +0.071 |
| 0.6–0.7 | 12 | 0.659 | 0.667 | +0.007 |
| 0.7–0.8 | 10 | 0.752 | 0.700 | −0.052 |
| 0.8–0.9 | 17 | 0.864 | 0.765 | −0.099 |
| 0.9–1.0 | 94 | 0.986 | 0.947 | −0.039 |

The two large buckets (n = 90 at the bottom, n = 94 at the top) are well
calibrated — a 1 % prediction realizes 4 %, a 99 % prediction realizes 95 %,
both slightly *under*-confident, which is the safe direction. The middle
buckets each hold 8–20 observations, where a single flipped season moves the
realized frequency by 0.05–0.12; the −0.365 gap in the 0.4–0.5 bucket is
**1 playoff berth out of 10 observations** and is not evidence of a defect.

### Calibration — title odds (pooled)

| bucket | n | mean predicted | realized | gap |
|---|---|---|---|---|
| 0.0–0.1 | 205 | 0.016 | 0.039 | +0.023 |
| 0.1–0.2 | 33 | 0.143 | 0.121 | −0.022 |
| 0.2–0.3 | 25 | 0.236 | 0.160 | −0.076 |
| 0.3–0.4 | 16 | 0.350 | 0.375 | +0.025 |
| 0.4–0.5 | 6 | 0.416 | 0.333 | −0.083 |
| 0.5–0.6 | 2 | 0.568 | 0.000 | −0.568 |
| 0.6–0.7 | 0 | — | — | — |
| 0.7–0.8 | 0 | — | — | — |
| 0.8–0.9 | 1 | 0.800 | 0.000 | −0.800 |
| 0.9–1.0 | 0 | — | — | — |

Above 0.5 there are **three observations in total**. The −0.568 and −0.800 gaps
are one team each and support **no inference whatsoever**. Reported only so the
table is not silently truncated.

### Per-league / per-week playoff Brier

| league-season | wk 3 | wk 6 | wk 9 | wk 12 |
|---|---|---|---|---|
| lakeview-2025 | 0.0948 | 0.0555 | 0.0492 | 0.0920 |
| lakeview-2024 | 0.3030 | 0.1230 | 0.0816 | 0.0142 |
| ffv3-2025 | 0.3088 | 0.2109 | 0.1026 | 0.0628 |
| ffv3-2024 | 0.2860 | 0.1693 | 0.0888 | 0.0290 |
| ffv3-2023 | 0.0889 | 0.1165 | 0.0349 | 0.1308 |
| ffv3-2022 | 0.1016 | 0.0474 | 0.0804 | 0.0001 |

Every league-season beats climatology (0.2500) at weeks 6, 9 and 12. Three of
six are worse than climatology at week 3.

### Does the future schedule matter?

Running the same backtest with future pairings **removed** (forcing the
simulator's random re-pairing fallback):

| | Playoff Brier | Title Brier |
|---|---|---|
| With true remaining schedule | 0.1113 | 0.0725 |
| Random re-pairing fallback | 0.1168 | 0.0727 |

**The fallback costs ~5 % of playoff Brier and nothing measurable on title.**
Strength-of-schedule is a second-order effect in a 12-team league. This is good
news: a platform that does not publish future pairings still gets usable odds.

---

## 4. Sample size and what it does not support

| Unit | Count |
|---|---|
| League-seasons | **6** |
| Independent team-seasons | **72** |
| Playoff berths (positive events) | **36** |
| **Champion events (positive events for title odds)** | **6** |
| Team-week predictions scored | 288 |
| Distinct leagues | **2** |
| Distinct league formats | **2** (SF/TEP median-match; 1QB IDP) |

**What this sample supports:**
- A confident statement that playoff odds beat climatology (bootstrap CI
  excludes zero by a wide margin, and the effect is present in all 6 seasons).
- A confident statement that playoff-odds accuracy improves with more weeks
  played.
- Detection of *mechanical* defects (BUG-1 through BUG-3) — real data found
  three that unit tests did not.

**What this sample does NOT support:**
- **Any claim about title-odds accuracy.** Six champion events. The bootstrap
  CI spans −13 % to +22 %. A model that emitted 1/12 for everyone would be
  statistically indistinguishable from the engine.
- Any per-bucket calibration claim above a predicted probability of ~0.4 for
  title odds (n ≤ 6 per bucket).
- **Any claim about the preseason `roster_value` source at all** — it was not
  scored (see §1).
- Generalization beyond 12-team, 6-slot dynasty leagues. Both leagues have the
  identical shape; 4-, 8- and 10-team formats and divisional leagues are
  entirely untested against reality.
- Anything about the **playoff bracket** model beyond what the 6 title outcomes
  say, which is nothing.

The 288 team-week figure is **not** 288 independent observations. Weeks 3/6/9/12
of one season are heavily autocorrelated; treat the effective sample as 72
team-seasons in 6 clusters.

---

## 5. Tier 2 — cross-source agreement

**Diagnostic only. Nothing here is shipped.** The alternate source is
implemented in `scripts/outlook_strength_source_compare.py`, deliberately
*outside* `backend/outlook/` — `SleeperProjectionsStrength` remains a registered
stub.

### 5a. Sleeper projections endpoint — verified shape

The research doc records the endpoint as
`GET api.sleeper.app/projections/nfl/<season>/<week>`. **Empirically that exact
URL returns HTTP 400.** The working form requires query parameters:

```
GET https://api.sleeper.app/projections/nfl/2026/1
      ?season_type=regular
      &position[]=QB&position[]=RB&position[]=WR&position[]=TE
      &order_by=pts_ppr
```

Response: a **JSON array** (~3,100 rows for the 4 skill positions), each row
`{player_id, week, season, season_type, team, opponent, game_id, category:"proj",
 status, date, last_modified, updated_at, player:{...}, stats:{...}}`, with
`stats.pts_ppr` / `pts_half_ppr` / `pts_std` carrying the projected points.
Two other live variants were confirmed: `v1/projections/nfl/regular/<season>/<week>`
returns a `{player_id: stats}` **object**, and
`projections/nfl/player/<id>?season_type=regular&season=<y>&grouping=week`
returns a per-week object for one player.

Caveats worth recording: the endpoint is undocumented and unversioned; the 2025
rows carry `last_modified` timestamps from *October 2025*, i.e. what is served
for a past week is the **latest revision**, not a point-in-time projection — so
this endpoint cannot be used to backtest projections honestly without a
contemporaneous capture.

Fixture: `sleeper-projections-2026.json` (14 weeks, 527 rostered player ids,
93–95 % coverage of the two leagues' rosters).

### 5b. Roster-value prior vs projections — 2026 leagues

Both sources run through the same simulator (N = 10,000, identical seed);
only Phase 2 differs.

**Lakeview 2026** (SF/TEP, schedule published, `completed_weeks = 0`):

| roster | team | mu (value) | mu (proj) | playoff (value) | playoff (proj) | delta |
|---|---|---|---|---|---|---|
| 9 | The Nixers | 140.2 | 170.0 | 0.999 | 0.983 | −0.016 |
| 4 | Pewter Gym | 128.7 | 165.8 | 0.975 | 0.964 | −0.012 |
| 7 | Swaggy J's Pond | 116.1 | 157.6 | 0.819 | 0.906 | +0.087 |
| 3 | Brock Tua | 110.2 | 146.7 | 0.618 | 0.563 | −0.054 |
| 8 | Slim Pickens | 105.1 | 121.4 | 0.429 | 0.011 | **−0.419** |
| 1 | Boutte & the Breeches | 104.8 | 139.0 | 0.383 | 0.246 | −0.137 |
| 2 | The Dart Knight Rises | 103.7 | 128.1 | 0.378 | 0.045 | **−0.333** |
| 6 | gildalbora | 105.7 | 150.6 | 0.350 | 0.618 | +0.268 |
| 10 | Critical Chase Theory | 102.9 | 155.7 | 0.346 | 0.885 | **+0.539** |
| 5 | Hurts Donut | 101.8 | 149.6 | 0.305 | 0.705 | **+0.400** |
| 12 | The Replacements | 103.1 | 121.2 | 0.298 | 0.010 | −0.288 |
| 11 | DrByron34 | 97.5 | 133.6 | 0.100 | 0.064 | −0.036 |

- mean |Δ playoff| **0.216**, max **0.539**
- Spearman(mu) **+0.587**, Spearman(playoff odds) **+0.573**
- projected playoff-field overlap **3 / 6**

**FFv3 2026** (1QB + IDP, **pre-draft — no schedule published**, random
re-pairing fallback active):

- mean |Δ playoff| **0.102**, max **0.363**
- Spearman(mu) **+0.874**, Spearman(playoff odds) **+0.937**
- projected playoff-field overlap **5 / 6**

**Reading (flag for investigation, not automatic failure).** The two sources
agree well on the 1QB league and **disagree badly on the superflex/TEP league**
— they pick a different half of the playoff field. The mechanism is visible in
the mu columns: the roster-value source produces a spread of ~11.7 points
(1 SD, by construction = `outlook_points_per_value_sd`), the projections source
~15.9. A dynasty value board also prices *future* seasons, so a young roster is
valued highly while its 2026 projected points are not — exactly the disagreement
you would expect, and a genuine argument that **a dynasty value board is the
wrong prior for a current-season odds question.** Roster 10 ("Critical Chase
The...") is the clearest case: mid-pack by dynasty value, third-best by 2026
projected points.

This is a strong argument for prioritising the `sleeper_projections` strength
source before the preseason odds surface ever lights up — and it is *not*
evidence about which source is more accurate, because neither was backtestable
preseason.

### 5c. DynastyDaddy cross-check — for the operator to complete

DynastyDaddy simulates Sleeper leagues directly and is the closest public
comparable. Everything below is filled in except their numbers.

**Steps**
1. Go to <https://dynasty-daddy.com/> → **League Analyzer** (or "Power Rankings"
   → "Playoff Calculator", depending on their current nav).
2. Connect **Sleeper**, enter username `mattmurf77`, pick season **2026**.
3. Select the league **Lakeview League 🏈** (`1312076055586050048`).
4. Open the **season simulator / playoff odds** view. Note their sim count
   (they document 10,000) and whether it is set to use *starting-lineup value*
   or *projections*.
5. Record their playoff % and championship % per team below.
6. Repeat for **Fantasy Football Version 3** (`1312140920132497408`) if it has
   completed its draft — while it is `pre_draft` neither tool has a schedule.

**Table to fill — Lakeview 2026**

| roster | team | FTF playoff % (roster-value) | FTF playoff % (projections) | DynastyDaddy playoff % | FTF title % (roster-value) | DynastyDaddy title % |
|---|---|---|---|---|---|---|
| 9 | The Nixers | 99.9 | 98.3 |  | 56.2 |  |
| 4 | Pewter Gym | 97.5 | 96.4 |  | 27.4 |  |
| 7 | Swaggy J's Pond | 81.9 | 90.6 |  | 7.1 |  |
| 3 | Brock Tua | 61.8 | 56.3 |  | 2.9 |  |
| 8 | Slim Pickens | 42.9 | 1.1 |  | 1.1 |  |
| 1 | Boutte & the Breeches | 38.3 | 24.6 |  | 0.9 |  |
| 2 | The Dart Knight Rises | 37.8 | 4.5 |  | 1.1 |  |
| 6 | gildalbora | 35.0 | 61.8 |  | 1.0 |  |
| 10 | Critical Chase Theory | 34.6 | 88.5 |  | 0.9 |  |
| 5 | Hurts Donut | 30.5 | 70.5 |  | 0.5 |  |
| 12 | The Replacements | 29.8 | 1.0 |  | 0.8 |  |
| 11 | DrByron34 | 10.0 | 6.4 |  | 0.1 |  |

**What to conclude from it**
- If DynastyDaddy tracks the **projections** column, that corroborates §5b's
  suspicion that the dynasty-value prior is the wrong basis for current-season odds.
- If it tracks the **roster-value** column, the two independent implementations
  agree and the disagreement in §5b is about the *source*, not the *simulator*.
- If it tracks **neither**, look first at whether their sim includes the median
  match (Lakeview has it on — see BUG-1) and at their playoff seeding rule.

---

## 6. Tier 3 — internal invariants

New permanent file: `backend/tests/test_outlook_calibration.py` —
**22 passed, 1 xfailed**, runs in ~3.6 s.

| # | Invariant | Test | Result |
|---|---|---|---|
| 1 | Σ playoff odds == playoff slot count | `test_playoff_odds_sum_to_slot_count` (4 league shapes) | **pass** (exact, ±1e-9) |
| 1b | Σ bye odds == bye count | same | **pass** |
| 2 | Σ title odds == 1 | `test_title_odds_sum_to_one` (4 shapes) | **pass** (exact) |
| 2b | title % ≤ playoff % for every team | `test_only_playoff_teams_can_win_the_title` | **pass** |
| 3 | odds monotone in team strength | `test_odds_are_monotone_in_team_strength` | **pass** (10-team ordered league; playoff, title, projected wins all non-decreasing; seed improves) |
| 4 | symmetric league → uniform odds | `test_symmetric_league_is_uniform_within_mc_tolerance` | **pass** (12 identical teams, N=8000, within ~6 SE) |
| 5 | estimates converge as N grows | `test_estimates_converge_as_n_grows` | **pass** (spread across 8 seeds shrinks >40 % from N=250 to N=4000) |
| 6 | deterministic under a fixed seed | `test_run_outlook_is_deterministic_under_a_fixed_seed` | **pass** end-to-end through `run_outlook`; a different `outlook_seed` moves the numbers |
| 6b | seed is process-stable | `test_seed_is_process_stable_across_interpreters` | **pass** (invariant under `PYTHONHASHSEED`) |
| — | as-of rewind reproduces Sleeper's own final standings | `test_as_of_rewind_reproduces_sleepers_own_final_standings` (6 seasons) | **pass** |
| — | as-of state carries no future information | `test_as_of_state_carries_no_future_information` | **pass** |
| — | engine beats climatology on captured seasons | `test_engine_beats_climatology_on_captured_seasons` | **pass** (regression guard, week 9, Brier < 0.75 × climatology) |
| — | median-match leagues ingested on the simulated win scale | `test_median_match_leagues_are_ingested_on_the_simulated_win_scale` | **xfail (strict)** — tracks BUG-1; delete the marker when fixed |

**The simulator was already seedable** (`simulate(config_seed=)`, plumbed
through `run_outlook` via `model_config["outlook_seed"]`) and already uses a
SHA-256 stable hash rather than the salted builtin. No fix was needed there.

---

## 7. Bugs found

Per the validation-first brief: documented with severity; nothing structural was
rewritten.

### BUG-1 — `league_average_match` (median scoring) is ignored — **SEVERE, affects the operator's own live league**

**What.** `SleeperLeagueState.load()` copies `wins`/`losses`/`ties` straight off
`/rosters` and never reads `settings.league_average_match`. When that setting is
on, Sleeper books **two decisions per week** (head-to-head *and* versus the
league median), so a 14-week season records 28 W/L. `simulate()` adds exactly
**one** win per remaining week. Base standings and simulated increments are on
different scales.

**Proof.** Recomputing standings *with* the median game reproduces Sleeper's
reported record for **all 24 median-league rosters exactly** (and the H2H-only
recomputation reproduces all 36 non-median rosters exactly). E.g. lakeview-2025
roster 1: Sleeper 13-15, H2H-only replay 9-5, median-inclusive replay 13-15.

**Blast radius.** `settings.league_average_match == 1` on **Lakeview 2024, 2025
and the live 2026 league** — i.e. one of the operator's two leagues, right now.

**User-visible effect.** Lakeview 2026 at as-of week 12, shipped ingestion:

| roster | record shown | `projected_wins` | in a season of |
|---|---|---|---|
| 9 | 21-3 | **22.29** | 14 weeks |
| 10 | 18-6 | **19.07** | 14 weeks |

`projected_wins` mixes a 24-decision base with 2 simulated H2H games — it is
neither the 14-game scale nor the 28-decision scale, and it is what the mobile
odds row renders.

**Effect on accuracy (measured).** Scoring the shipped ingestion path against
the clean rewind:

| | Playoff Brier | Title Brier |
|---|---|---|
| All 6 leagues, clean rewind | 0.1113 | 0.0725 |
| All 6 leagues, shipped ingestion | 0.0982 (−11.8 %) | 0.0733 (+1.1 %) |
| **Median leagues only, clean** | 0.1017 | 0.0541 |
| **Median leagues only, shipped** | **0.0621 (−38.9 %)** | 0.0564 (+4.4 %) |

Counter-intuitively the bug *improves* playoff Brier on these 24 team-seasons.
That is not a defence of it. Doubling the banked-win count halves the leverage
of the remaining games, which collapses the engine toward "current standings are
destiny" — an over-confident predictor that happened to be right in a small
sample, while title Brier got slightly worse. The probabilities are not honestly
derived, and `projected_wins`/`projected_seed` are on a nonsense scale. **This is
a ship blocker regardless of the Brier direction.**

**Fix sketch (for a fix agent, not done here).** Phase 1: read
`settings.league_average_match` into `LeagueState`. Phase 3: when set, score the
median game each simulated week (compute the week's median across the 12 drawn
scores, award a second win/loss per team). Phase 4/5: `projected_wins` then
lands on the same scale as the displayed record. Delete the `xfail` on
`test_median_match_leagues_are_ingested_on_the_simulated_win_scale`.

### BUG-2 — the "future pairings unknown" risk is real but narrower than flagged — **INFORMATIONAL, resolves an open item**

`league_state.py` flags as unvalidated whether Sleeper exposes `matchup_id` for
future weeks. Measured:

| League | Status | Weeks returned | Weeks with pairings | Weeks with points |
|---|---|---|---|---|
| Lakeview 2026 | `in_season` | 18 | **18** | 0 |
| FFv3 2026 | `pre_draft` | **0** | 0 | 0 |

**A scheduled league publishes the full-season pairing graph before a single
game is played** — so the flagged assumption holds once the schedule exists.
A **pre-draft** league returns no matchups at all, and the random re-pairing
fallback fires. Cost of the fallback, measured on 6 real seasons: **~5 % of
playoff Brier, nothing on title**. Recommend replacing the "not validated" note
in `league_state.py` with this result, and gating the odds surface on
`league.status != "pre_draft"` rather than on schedule presence.

### BUG-3 — `playoff_seed_type` is not modelled — **MODERATE, unquantified**

Both Lakeview seasons carry `settings.playoff_seed_type: 1` (FFv3 has `0`).
`StandardFormat` ignores it entirely and always seeds by record then
points-for. Sleeper uses this setting to vary re-seeding behaviour between
playoff rounds. The backtest cannot isolate its cost (6 title events), but any
league where it is non-zero has its bracket simulated under the wrong rule.
Recommend reading it into `LeagueState` and either modelling it or refusing to
emit `title_pct` when it is unsupported.

### BUG-4 — `points_for` is not exactly reconstructible from weekly scores — **LOW, external**

lakeview-2024 roster 10: Sleeper's roster `fpts` is 1981.22 but the sum of its
own weekly matchup `points` is 1959.02 (+22.20, ~1.1 %). All matchup groups are
well-formed, so this is a Sleeper-side stat correction applied to the roster
total and not backfilled into the weekly record. Consequence for FTF: the
`points_for` seeding tiebreak can disagree with the scoring history by ~1 %.
Not actionable, but it is why the rewind test checks PF within 2 % rather than
exactly.

### Non-bug confirmations

- The simulator **is** seedable, deterministic, and process-stable. No fix needed.
- The `auto` source resolver picks `trailing_scores` at every as-of week ≥ 3,
  as designed.
- Conservation laws (Σ playoff = slots, Σ title = 1) hold **exactly**, not
  approximately — they are structural, not statistical.

---

## 8. Calibration evidence for the flagged knobs

The status doc flags `outlook_mean_points` / `outlook_points_per_value_sd` /
`outlook_sigma_default` as "plausible but unvalidated". Measured across the 6
captured seasons:

| league-season | league mean pts | within-team σ | between-team SD (raw) | between-team SD (noise-corrected) |
|---|---|---|---|---|
| lakeview-2025 | 132.3 | 24.7 | 18.1 | 16.8 |
| lakeview-2024 | 136.3 | 24.9 | 19.1 | 17.9 |
| ffv3-2025 | 128.5 | 20.5 | 12.8 | 11.5 |
| ffv3-2024 | 128.1 | 21.0 | 12.1 | 10.7 |
| ffv3-2023 | 129.2 | 20.9 | 15.3 | 14.2 |
| ffv3-2022 | 129.3 | 20.8 | 14.6 | 13.5 |
| **pooled** | **130.6** | **22.1** | — | **14.1** |

(The raw between-team SD of season means is inflated by sampling noise;
corrected via `var(true) = var(observed) − σ²/weeks`.)

| Knob | Shipped default | Empirical | Assessment |
|---|---|---|---|
| `outlook_sigma_default` | 25 | **22.1** | Close, ~13 % conservative. Harmless — errs toward *less* confident odds. Fine as-is; 22 would be better. |
| `outlook_mean_points` | 110 | **130.6** | ~19 % low, but **it cancels**: only mu *differences* affect a head-to-head, so a uniform shift changes nothing. Cosmetic only — worth fixing so the number isn't misread as meaningful. |
| `outlook_points_per_value_sd` | 12 | true talent SD **14.1** | This knob should equal `corr(roster value, weekly points) × 14.1`, not 14.1 itself. 12 implies an assumed correlation of ~0.85, which is **optimistic** for a dynasty board predicting current-season points (see §5b). Without a historical value board the correlation cannot be measured — so 12 is unfalsifiable, not validated. |

**Format-dependence is the bigger finding:** the superflex/TEP league's talent
spread (16.8–17.9) is ~35 % wider than the 1QB league's (10.7–14.2). A single
global constant is wrong for both. Recommend making
`outlook_points_per_value_sd` scale with league type, or deriving it per-league
from observed scoring once ≥ 3 weeks exist (which `trailing_scores` already
does implicitly — another argument for shortening the roster-value window).

---

## 9. Proposed pass bar and verdict

The bar below is proposed by this agent; the operator rules.

| # | Criterion | Bar | Measured | Result |
|---|---|---|---|---|
| P1 | Playoff odds beat climatology | Brier skill > +20 %, bootstrap CI excludes 0 | **+55.5 %, CI [+44.5, +65.9]** | **PASS** |
| P2 | Playoff odds beat standings-extrapolation | beat both B2 and B3 | +38.3 % / +27.1 % | **PASS** |
| P3 | Playoff calibration sane in populated buckets | \|gap\| < 0.10 in every bucket with n ≥ 50 | 0.032 and −0.039 (n = 90, 94) | **PASS** |
| P4 | Accuracy improves with information | monotone across weeks 3→12 | 0.197 → 0.120 → 0.073 → 0.055 | **PASS** |
| P5 | Title odds beat climatology | skill > 0 with CI excluding 0 | +5.1 %, **CI [−13.2, +22.3]** | **FAIL** |
| P6 | Title odds not worse than climatology at any shipped week | — | **week 3 is worse** (0.0953 vs 0.0764) | **FAIL** |
| P7 | Internal invariants hold | all pass | 22 pass, 1 xfail (tracks BUG-1) | **PASS** |
| P8 | No severe unfixed correctness bug on a real operator league | zero | **BUG-1** (Lakeview, live) | **FAIL** |
| P9 | Preseason default source validated | backtested | **not backtestable** (no historical value board) | **FAIL — untestable** |
| P10 | Cross-source agreement | Spearman > 0.8 or explained | 0.57 (SF/TEP) / 0.93 (1QB) — explained in §5b | **MARGINAL** |

### Verdict: MARGINAL PASS, conditional

**The Monte-Carlo engine works.** Phases 2–5 are correct, deterministic,
invariant-respecting, and on real data they produce playoff odds with large,
statistically significant skill over both dumb baselines, improving as the
season progresses. That is a genuine result on 72 team-seasons across 6
seasons and 2 league formats — not a "it compiles" result.

**But three things block the flag as it stands:**

1. **BUG-1 must be fixed first.** One of the operator's two leagues is a
   median-match league and would render `projected_wins = 22.29` in a 14-week
   season today. Non-negotiable.
2. **Title / championship odds have not been shown to work.** Six champion
   events is not a validation; the confidence interval spans zero, and at week 3
   the number is worse than a constant 1/12. Recommend one of: hide `title_pct`
   entirely at v1; or show it only from week 6 with explicit "low confidence"
   labelling; or show a seed distribution instead, which the sim already computes
   and which does not require a rare-event claim.
3. **The preseason default (`roster_value`) is entirely unvalidated**, and Tier 2
   gives positive reason to doubt it: on the superflex league the dynasty-value
   prior and a 2026 projection feed disagree on half the playoff field. Since
   the flag would be flipped *in the preseason*, this is the source users would
   see first. Recommend gating the surface to `completed_weeks >= 3` (where
   `trailing_scores` — the source that was actually validated — takes over), or
   implementing `sleeper_projections` before preseason odds go live.

**Recommended operator decision:** approve a follow-up build that (a) fixes
BUG-1, (b) gates the odds surface to `completed_weeks >= 3` and
`status != "pre_draft"`, and (c) ships **playoff odds only**, with title odds
either withheld or demoted. Re-run this backtest after (a) — the regression
guard is already in the test suite. Do **not** flip `outlook.odds` on before
BUG-1 lands.

**What would raise confidence most, cheaply:** more leagues. The engine is
public-API-driven, so any set of completed Sleeper dynasty leagues can be added
to the fixture set with the same capture script. Twenty league-seasons would put
the title-odds question within reach; six cannot.

---

## 10. Reproducing this report

```bash
# Tier 1 — as-of backtest, invariant checks, calibration evidence (offline)
python3 scripts/outlook_calibration_backtest.py --sims 10000

# Tier 2 — roster-value vs Sleeper projections on the 2026 leagues (offline)
python3 scripts/outlook_strength_source_compare.py --sims 10000 \
    --players-cache data/.sleeper_players_cache.json

# Tier 3 — permanent invariants
python3 -m pytest backend/tests/test_outlook_calibration.py -q
```

| Artefact | Path |
|---|---|
| Captured Sleeper fixtures (8 league-seasons + projections) | `backend/tests/fixtures/outlook-calibration/` |
| As-of backtest harness | `scripts/outlook_calibration_backtest.py` |
| Tier-2 script-only projections source | `scripts/outlook_strength_source_compare.py` |
| Permanent invariant tests | `backend/tests/test_outlook_calibration.py` |
| Design under test | `docs/feedback/items/169-outlook-league-summary/odds-pipeline-lld.md` |

Test posture: backend suite **2136 passed / 1 skipped** before this work,
**2158 passed / 1 skipped / 1 xfailed** after. No mobile changes. The
`outlook.odds` flag is untouched and remains dark.
