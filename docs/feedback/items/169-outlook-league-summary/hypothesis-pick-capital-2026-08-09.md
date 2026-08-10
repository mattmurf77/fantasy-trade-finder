# #169 Outlook Odds — Pick-Capital Hypothesis Test (1a vs 1b)

**Date:** 2026-08-09 · **Author:** research/validation agent · **Branch:** `outlook-calibration` (worktree continuation of the calibration report)
**Subject:** whether a roster's draft-pick capital at the start of a season predicts what happens to that roster **during** the season — and if so, in which direction.
**Purpose:** empirical validation only. No product code changed; the operator rules on whether/how this ever enters `backend/outlook/`.

> **Verdict in one line:** **1a ("more picks → gets stronger") is not supported anywhere in this sample. 1b ("more picks → signals a rebuild that sheds players") has weak-to-moderate, mostly consistent support** — teams that start a season holding more future pick capital tend to under-perform their already-observed early-season form, make the playoffs less often, and are more likely to trade players away for picks (not picks for players) as the season goes on. Effect sizes are small and the sample (72 team-seasons, 6 independent league-clusters) is underpowered for a confident causal claim; the strongest single piece of evidence is the **behavioral** one (what teams actually traded), not the outcome correlations. **No implementation is recommended at this sample size** — see §7.

> **CORRECTION AND RE-VERDICT — 2026-08-09.** This report states that "there
> is no historical, dated dynasty-value board" and substitutes points-per-game
> for sub-test (i) on that basis. **The premise was wrong** — DynastyProcess
> keeps the full git history of `values-players.csv`. Sub-test (i) has since
> been re-run with period-correct boards, and **the result changes**:
> Pearson r moves from **−0.113 / −0.108 (CI excluding 0)** to
> **+0.076 / +0.074 with a CI spanning zero** — a clean null whose point
> estimate is mildly the *wrong* sign for 1b. The confound (capital vs week-1
> lineup strength) gets *stronger*: −0.349 → **−0.415**. Everything that never
> depended on a value board — (ii), (iii), and §6.2's buy:sell gradient — is
> **bit-identical**.
>
> **Net: 1b is WEAKENED, not overturned.** "Real signal on 3 of 4 sub-tests"
> should read "**2 of 4 outcome sub-tests plus the behavioural mechanism; no
> signal on roster composition**". The §7 recommendation (do not spec a term)
> is unchanged and better supported. The §7 prerequisite — "revisit if/when a
> historical, dated dynasty-value board exists" — is **met and answered**, and
> the answer is that Δ dynasty value is a structurally poor instrument for 1b:
> a competent rebuild trades present output for future value, so it moves this
> metric the *opposite* way from 1b's framing. Full re-test:
> [`dated-values-revalidation-2026-08-09.md`](dated-values-revalidation-2026-08-09.md) §6.
> Original text below left intact.

---

## Table of contents

- [1. Scope and how this relates to the calibration report](#1-scope-and-how-this-relates-to-the-calibration-report)
- [2. Method](#2-method)
- [3. Data coverage](#3-data-coverage)
- [4. Results — hypothesis (i): capital vs in-season roster-strength change](#4-results--hypothesis-i-capital-vs-in-season-roster-strength-change)
- [5. Results — hypothesis (ii) and (iii): capital vs win outperformance and playoff berth](#5-results--hypothesis-ii-and-iii-capital-vs-win-outperformance-and-playoff-berth)
- [6. Moderator analysis and the mechanism check](#6-moderator-analysis-and-the-mechanism-check)
- [7. Verdict per hypothesis, and the spec-or-reject recommendation](#7-verdict-per-hypothesis-and-the-spec-or-reject-recommendation)
- [8. Honesty notes / what this sample does not support](#8-honesty-notes--what-this-sample-does-not-support)
- [9. Reproducing this report](#9-reproducing-this-report)

---

## 1. Scope and how this relates to the calibration report

The [2026-08-09 calibration report](calibration-report-2026-08-09.md) validated the
Monte-Carlo outlook engine's **playoff-odds** number (real skill, +55.5% Brier
skill vs climatology) and found the **preseason default strength source**
(`RosterValueStrength`, a dynasty-value-based prior) "not backtestable — Sleeper
exposes no historical rosters and FTF has no dated value snapshots." This
report tests a narrower, adjacent question the operator raised independently:
**should a team's future draft-pick capital itself be an input to preseason
strength** — a bonus (1a) or a penalty (1b)? The same 6 real backtested
Sleeper dynasty league-seasons are reused so the two reports are directly
comparable, and the same historical-value-board gap shows up again here (see
§2's "why points, not dynasty value").

This is validation, not a build: **no file under `backend/outlook/` and no
feature flag changed.** The new artifacts are two scripts under `scripts/`
and new fixtures under `backend/tests/fixtures/outlook-hypotheses/`.

---

## 2. Method

### 2.1 Pick capital at season start

Sleeper exposes pick ownership two ways: `/league/{id}/traded_picks` (current
snapshot, no history) and `/league/{id}/transactions/{week}` (timestamped,
`type=="trade"` rows carry a `draft_picks` array of
`{season, round, roster_id (original owner), owner_id (new owner),
previous_owner_id}`). The brief's method spine pointed at `traded_picks`;
this report uses **transaction replay** instead, for a concrete, checkable
reason:

**Empirically verified Sleeper quirk** — `/transactions/1` returns every
completed trade from league creation/rollover through the end of week 1, not
just week 1's own week. A spot check on `ffv3-2024`'s week-1 bucket found
trades timestamped back to **2024-03-09**, five months before kickoff.
Week-2-onward buckets are genuine single-week windows (verified: week 2 had 0
trades, week 3's trades were dated after week-1 games completed). So:

- **Season-start pick capital** = replay only the **week-1 bucket** of trade
  transactions onto a pristine grid where every roster owns one pick per
  round (1-4) for each of the three following draft classes
  (`season+1..season+3` — dynasty rookie drafts for all 6 league-seasons here
  ran May-August, i.e. **before** kickoff, confirmed via `/drafts`, so
  `season` itself is already-drafted players by week 1 and correctly excluded
  from "future capital").
- **In-season change** = continue replaying week 2 through
  `regular_season_weeks` (14 for all 6 fixtures) chronologically by
  `status_updated`.
- Priced two ways per roster: **raw count** of owned picks, and
  **value-weighted** via the SHIPPED `backend.pick_values.pick_pool_value(round,
  years_out)` ladder — imported, not reimplemented, per the brief.
  `pick_pool_value`'s `scoring_format` parameter is a documented no-op today
  ("pick value is format-agnostic in v1"), so format was not modeled.

**Validation.** Replaying every captured trade (weeks 1-18) and comparing
against Sleeper's own *current* `traded_picks` snapshot for the same
league_id: of 181 pick-ownership facts both sources have an opinion on, **181
agree (100%)** and the replay never asserts an ownership Sleeper doesn't also
show. Sleeper's list additionally carries 52 keys the replay has no evidence
for — all attributable to trades made *after* week 18 closes but before the
next season's league object is created (a real coverage gap in an 18-week
sweep, not a logic error; it lands entirely outside the two windows this
report actually measures, so it does not contaminate either the season-start
or in-season numbers). See the full per-league breakdown in the script
output.

### 2.2 In-season roster-strength change — points, not dynasty value

`backend.outlook.strength.starting_lineup_value(player_ids, player_value,
player_pos, roster_slots)` is the shipped optimal-lineup pricer (greedy fill
by value) and is imported and called unmodified. The brief asked for it fed a
dynasty-value board; **this report feeds it each player's own-season
points-per-game instead**, for the same reason the calibration report
declined to backtest `RosterValueStrength` at all: ~~**there is no historical,
dated dynasty-value board.**~~ **[CORRECTED 2026-08-09 — there is one: the
DynastyProcess repo keeps the git history of `values-players.csv`. Sub-test (i)
was re-run with period-correct boards and its result flips sign and loses
significance; see
[`dated-values-revalidation-2026-08-09.md`](dated-values-revalidation-2026-08-09.md)
§6. Original reasoning follows.]** Pricing a 2022 roster with today's live values
would score a since-broken-out rookie as valuable in 2022 because of what he
did in 2024-25 — exactly the dressed-up-with-hindsight result this report's
honesty section forbids. Feeding the same function each player's actual
in-season scoring output instead is contemporaneous (no hindsight), still
literally `starting_lineup_value()`, and more directly on-topic: the
hypotheses are about whether a roster got **objectively better or worse at
scoring points**, not whether its trade value moved.

Per league-season, every player's PPG is computed once from `players_points`
across all 14 regular-season weeks (mean over weeks they were rostered by
anyone, including 0.0 for a rostered-but-inactive/bye week — a limitation
noted in §8, applied identically to both snapshots so it cannot structurally
favor 1a or 1b). That single fixed price list is then applied to the
`week 1` roster and the `week 14` roster (each team's actual, full,
Sleeper-reported roster for that week — not a transaction replay; Sleeper's
`/matchups/{week}` rows already carry the full roster, including bench, for
that exact week, which is a **more direct** source than reconstructing it
from adds/drops and was preferred for that reason). Player positions came
from Sleeper's bulk `/players/nfl` dump, filtered to the 1,078 player ids
that actually appear across the 6 seasons (all 1,078 matched; 0 missing).

**Δ starting-lineup value** = `sl_value(week 14 roster) − sl_value(week 1
roster)`, on a fixed points-per-week scale. This isolates *which players are
rostered* — the roster-construction question 1a/1b is actually about — from
week-to-week performance swings of players who never left.

### 2.3 Outperformance vs early-season form

The brief asked for "actual wins vs preseason-value-implied expected wins" —
again blocked by the missing historical value board (the calibration report's
own finding: `RosterValueStrength` "NOT backtestable"). Substituted with
**actual regular-season wins minus week-3 `TrailingScoresStrength`-implied
`projected_wins`**, both computed via the exact same shipped
`run_outlook()` the calibration report scored (never reimplemented), and both
on the **H2H-only win scale** (`as_of()`'s clean rewind) — deliberately
**side-stepping BUG-1** (the median-match double-counting bug the calibration
report found live in Lakeview's shipped ingestion), since `as_of()`'s
recompute is on the clean 14-game scale the simulator itself uses. Week 3 is
the earliest as-of week `trailing_scores` resolves (`outlook_trailing_min_weeks
= 3`) and was already shown, in the calibration report, to have real skill at
that point (Brier 0.197 vs 0.250 climatology). This is arguably a *stronger*
substitution than the literal ask: it uses the already-validated source, not
the never-validated one, and it nets out three weeks of observed team quality
by construction, so hypothesis (ii) is not just "capital vs raw wins" but
"capital vs wins **beyond** what early-season form already predicted."

### 2.4 Trade-mechanism tag

Each in-season trade transaction's own `adds`/`drops` (player_id → roster_id)
and `draft_picks` (`previous_owner_id`→`owner_id`) fields are enough to
classify, per roster per trade: net gave picks + received players →
**"bought"** (1a-flavored); net gave players + received picks →
**"sold"** (1b-flavored); anything else → mixed/other. This is the one piece
of evidence in this report that requires no outcome modeling at all — it is
a direct read of what each team actually traded.

### 2.5 Playoff berth ground truth

Reused unmodified from `outlook_calibration_backtest.truth()` — the winners
bracket's `t1`/`t2` field, asserted to equal `playoff_slots`.

---

## 3. Data coverage

Same 6 league-seasons as the calibration report (2 leagues × 3-4 seasons
each, 12 teams, 14-week regular season, all Sleeper dynasty):
`lakeview-2025`, `lakeview-2024`, `ffv3-2025`, `ffv3-2024`, `ffv3-2023`,
`ffv3-2022`.

| Unit | Count |
|---|---|
| League-seasons | **6** |
| Team-seasons (independent-ish, see §8) | **72** |
| Distinct leagues | **2** |
| Preseason (week-1-bucket) trades replayed | 34 + 35 + 12 + 21 + 21 + 11 = **134** |
| In-season (week 2-14) trades replayed | 9 + 17 + 16 + 10 + 21 + 7 = **80** |
| Pick-ownership facts validated against Sleeper's own list | 181/181 agree where both track (100%); 52 outside an 18-week sweep's coverage (§2.1) |

New fixtures, captured 2026-08-09, public read-only Sleeper endpoints, all
committed so this is repeatable offline:

| Artefact | Path |
|---|---|
| Per-league `traded_picks` + filtered `transactions_trades` (wk 1-18) | `backend/tests/fixtures/outlook-hypotheses/<league>.json` |
| Player id → position, filtered to the 1,078 ids seen | `backend/tests/fixtures/outlook-hypotheses/player-positions.json` |
| Capture script (network, run once) | `scripts/outlook_pick_capital_capture.py` |
| Analysis script (offline, this report's numbers) | `scripts/outlook_pick_capital_hypothesis.py` |

**All 6 league-seasons are usable** for every metric in this report — unlike
the calibration report's Tier-2 diagnostic (which needed live 2026 data),
everything here runs on the already-completed, already-committed seasons.
There is **no** season this report had to drop for missing transaction
history; Sleeper's public API served weeks 1-18 for the oldest season
(2022) exactly as readily as the newest.

---

## 4. Results — hypothesis (i): capital vs in-season roster-strength change

**1a predicts positive** (more capital → roster gets stronger during the
season). **1b predicts negative** (more capital → roster gets weaker).

| Capital measure | Pearson r | Spearman ρ | 90% CI (cluster bootstrap, 6 leagues) | Reading |
|---|---|---|---|---|
| Raw pick count | −0.113 | +0.012 | [−0.240, −0.001] | technically excludes 0, but grazes it |
| Value-weighted | −0.108 | −0.004 | [−0.237, −0.036] | excludes 0, weak |

**Confound check** (not one of the four required tests, but necessary
context): season-start capital is **already** negatively correlated with
week-1 roster strength itself (r = −0.278 raw / −0.349 value-weighted, 90% CI
excludes 0 both ways). Teams that enter a season holding more future picks
already have weaker week-1 rosters — consistent with the obvious
self-selection story (you accumulate picks by trading away good players in a
*prior* off-season, which is exactly what a rebuild looks like) — before a
single game of the season being measured is even played.

**Tercile means (value-weighted capital)** — not monotonic:

| Tercile | n | mean capital | mean Δ starting-lineup PPG | mean win residual | playoff rate |
|---|---|---|---|---|---|
| Low (bottom third) | 24 | 5,697.5 | **+3.83** | +0.89 | 62% |
| Mid | 24 | 7,771.1 | −1.23 | −0.13 | 46% |
| High (top third) | 24 | **10,244.3** | +2.85 | **−0.76** | **42%** |

The Δ-starting-lineup-value column is **not monotonic** across terciles (the
high tercile actually has a *positive* mean, driven partly by one large
outlier — `ffv3-2025` roster 5 shed six star-level starters, including
Prescott/Gibbs/Adams/Henry/Mayfield/McBride, for role players and rookies,
a genuine, spot-checked, textbook rebuild move, and dragged the low/mid means
around by itself). The linear correlation is small and its CI grazes zero.
**This particular sub-test (i) is the weakest result in this report** — read
it as noisy, not as evidence either way.

---

## 5. Results — hypothesis (ii) and (iii): capital vs win outperformance and playoff berth

### (ii) Actual wins minus week-3-implied wins

| Capital measure | Pearson r | Spearman ρ | 90% CI (cluster bootstrap) | Reading |
|---|---|---|---|---|
| Raw pick count | −0.254 | −0.172 | [−0.403, −0.139] | **excludes 0, moderate** |
| Value-weighted | −0.197 | −0.159 | [−0.394, −0.024] | excludes 0, weak-moderate |

Teams that start a season with more future pick capital tend to win **fewer**
games than their own week-3 form already implied — i.e. they under-perform
relative to a baseline that has already seen three weeks of their actual
play, not just a flat league-average expectation. This is the cleanest
outcome-side evidence in the report, in the **1b** direction (negative)
and **not** the 1a direction (which predicts positive).

### (iii) Playoff berth

| Capital measure | Pearson r | Spearman ρ | mean(made playoffs) | mean(missed) |
|---|---|---|---|---|
| Raw pick count | −0.210 | −0.182 | 11.5 picks | 12.5 picks |
| Value-weighted | −0.251 | −0.171 | 7,265 | 8,543 |

Same direction, similar magnitude, consistent with (ii): teams that miss the
playoffs held, on average, ~18% more value-weighted pick capital at season
start than teams that made it. No bootstrap CI is reported for a
binary-outcome correlation at n=72 with only ~36 positive events per class —
report the point estimate and group means only; do not over-read a
correlation coefficient against a 0/1 outcome at this sample size (see §8).

---

## 6. Moderator analysis and the mechanism check

### 6.1 Contender vs non-contender at week 7

Split each league's 12 teams into top/bottom half by week-7 win-credit
(record), then re-run the two correlations within each half:

| Group | n | capital vs Δ starting-lineup r | capital vs win-residual r |
|---|---|---|---|
| Contenders (top half @ wk 7) | 36 | **+0.079** | **−0.284** |
| Non-contenders (bottom half @ wk 7) | 36 | −0.120 | −0.080 |

This is the one place 1a gets a (very weak) positive signal: among teams
that were *already* playing well at week 7, capital correlates near-zero
with roster-strength change. But even among contenders, capital correlates
**more negatively** with win outperformance than the pooled sample does — a
pick-rich "contender" still tends to underperform its own week-3 form more
than a pick-poor one does. Non-contenders show the opposite pattern from
what 1b's simplest reading would predict (their Δ-roster-strength correlation
is the more negative one, −0.120, but their win-residual correlation is
close to flat, −0.080) — the moderator split does **not** cleanly separate
1a and 1b into "happens among contenders" vs "happens among rebuilders" the
way the operator's framing anticipated. Read this as: the underlying effect
is present but diffuse across the contender/non-contender split, not
concentrated in one half.

### 6.2 Trade-mechanism tag — the strongest single result in this report

For every in-season trade, tag each involved roster as a net **buyer**
(gave picks, got players — 1a-flavored) or net **seller** (gave players, got
picks — 1b-flavored), then bucket rosters into terciles by season-start
value-weighted capital:

| Capital tercile | n | bought (picks→players) | sold (players→picks) | buy:sell ratio |
|---|---|---|---|---|
| Low | 24 | 12 | 5 | **2.4 : 1** |
| Mid | 24 | 8 | 11 | 0.7 : 1 |
| High | 24 | 7 | 11 | **0.6 : 1** |

This is monotonic and requires no outcome modeling, no win-projection
machinery, and no roster-value pricing at all — it is a direct read of what
teams actually did in-season. **Teams that started the season with the least
future pick capital were net buyers of players (spending down whatever
capital they had); teams that started with the most were net sellers of
players (continuing to accumulate more).** That is exactly 1b's mechanism
("lots of picks signals a rebuilding team that will actively shed productive
players"), and the mirror image of 1a's ("in-season moves to get
stronger" — which would predict the *high*-capital tercile buying more, not
less). Counts are small (5-12 per cell) and this is descriptive, not a
formal test — but the direction is consistent across all three terciles, not
just the two extremes.

---

## 7. Verdict per hypothesis, and the spec-or-reject recommendation

| Hypothesis | Predicts | Result | Verdict |
|---|---|---|---|
| **1a** — picks enable in-season upgrades | positive Δ-roster-strength, positive win outperformance, high-capital teams buy | Every correlation is flat-to-negative; buy:sell ratio falls as capital rises (opposite of predicted) | **NOT SUPPORTED** |
| **1b** — picks signal a rebuild that sheds players | negative Δ-roster-strength, negative win outperformance, high-capital teams sell | Δ-roster-strength: weak/noisy, CI grazes 0. Win outperformance: moderate, CI excludes 0. Playoff berth: consistent negative. Trade mechanism: clean, monotonic, in the predicted direction. | **WEAKLY-TO-MODERATELY SUPPORTED** — real signal on 3 of 4 sub-tests, weakest on the roster-value delta specifically |

**Net effect:** the tension the operator asked to resolve does not go both
ways in this sample — there is no sub-test where 1a's predicted sign shows
up with anything resembling the strength 1b's signs show. If anything has to
be dressed down here, it's how confidently to state 1b, not whether to give
1a equal billing.

### Is this real, or is it just "pick capital proxies for team quality"?

Partially the latter, and the report says so plainly: teams with more
season-start capital already have weaker week-1 rosters (§4's confound
check). Some of the win-outperformance and playoff-berth effect is very
plausibly just "the same underlying weak roster keeps being weak," not a
behavioral in-season selling story on its own. What survives that objection
is **§6.2** — the buy/sell mechanism tag doesn't measure roster quality at
all, it measures a **behavioral choice** (what a manager traded for what),
and it still shows the predicted 1b-direction gradient. That is the one
result in this report that is not fully explained away by "pick capital just
means the team was already bad."

### Recommendation: do not spec an adjustment term yet

**Reject, for now** — not because the signal is absent, but because it is
too weak and the sample too small to trust a coefficient. If this were to
enter the strength model despite that, the natural home would be a small
downward adjustment to preseason μ for high-pick-capital rosters (only
`RosterValueStrength`, which is itself unvalidated per the calibration
report — a double unvalidated-on-unvalidated stack the operator should
weigh) — proportional to value-weighted capital, calibrated against the
tercile means in §4 (~1-2 points of season-average optimal-lineup PPG per
capital-SD, an effect roughly the same order of magnitude as
`outlook_sigma_default`'s own uncertainty band, i.e. small enough to be
within noise for a single team but potentially visible in the pooled Brier
the way BUG-1 was). Expected calibration impact if implemented anyway: at
best a marginal Brier improvement on playoff odds for the small subset of
extreme-capital rosters, easily offset by the risk of writing a wrong-signed
or overfit term into a preseason source that, per the calibration report, is
**already unbacktestable and not scheduled to ship** ("gating the surface to
`completed_weeks >= 3`... where `trailing_scores` — the source that was
actually validated — takes over" is the calibration report's own standing
recommendation). Spending calibration effort on an adjustment to a source
the operator may not even ship is premature. ~~**Revisit if/when a historical,
dated dynasty-value board exists** (the same prerequisite the calibration
report flagged) — at that point hypothesis (i) could be retested properly
(dynasty value, not points-per-game) and with more league-seasons, both of
which would meaningfully raise confidence one way or the other.~~

**[CLOSED 2026-08-09.** The prerequisite was met the same day (DynastyProcess
git history) and hypothesis (i) was retested properly, in dynasty value, with
period-correct boards. Result: r = **+0.076 / +0.074**, 90 % CI spanning zero
— a null with the point estimate mildly the *wrong* sign for 1b, replacing
the −0.113 / −0.108 reported in §4. Do **not** re-run this sub-test on more
league-seasons: §6 of
[`dated-values-revalidation-2026-08-09.md`](dated-values-revalidation-2026-08-09.md)
shows Δ dynasty value is a structurally poor instrument for 1b, because a
competent rebuild trades present output for future value and therefore moves
the metric the opposite way from 1b's framing. The recommendation above — do
not spec an adjustment term — stands, and is better supported than when it
was written.**]**

---

## 8. Honesty notes / what this sample does not support

- **72 team-seasons in 6 clusters is a small sample**, and the same
  non-independence the calibration report flagged applies here: 12
  team-seasons inside one league-season are mechanically linked (exactly 6
  make the playoffs; wins and losses within a league sum to a fixed total).
  Every CI in this report is a cluster bootstrap over the 6 league-seasons,
  not a naive n=72 calculation, for that reason — and even so, 6 clusters is
  very few; read every CI as wide, not precise.
- **No claim of causation.** Pick capital is not randomly assigned; the
  confound check in §4 shows it already correlates with weaker starting
  rosters, so some or all of the outcome correlations could be pure team-
  quality persistence rather than any in-season *behavior* triggered by
  holding picks. Section 6.2's trade-mechanism result is the one piece of
  evidence least vulnerable to this objection.
- **Hypothesis (i) specifically is underpowered to distinguish signal from
  noise** — its CI grazes zero, tercile means are non-monotonic, and one
  outlier roster-teardown visibly moves the low/mid tercile means. Do not
  read "Δ starting-lineup value" as a settled negative result; read it as
  "not distinguishable from zero at this n."
- **Playoff berth (iii) has no reported confidence interval** — a
  correlation against a binary outcome with ~36 positive events per class at
  n=72 does not support a trustworthy bootstrap CI the way the continuous
  outcomes in (i)/(ii) do; only the point estimate and group means are
  reported, deliberately, rather than dressing up a shaky CI.
- **Two real, disclosed methodological deviations from a literal reading of
  the brief** (both explained in §2, both driven by the same missing-
  historical-value-board gap the calibration report already found): Δ
  starting-lineup value is priced in season points-per-game, not dynasty
  value; win outperformance is measured against week-3 trailing-scores
  `projected_wins`, not a preseason-value-implied number. Both are argued to
  be *stronger* substitutions than the literal ask (no hindsight
  contamination; built on the already-validated `trailing_scores` source),
  but they are not what was literally specified, and a reader who wants the
  literal dynasty-value version should treat this report as blocked on the
  same historical-value-board gap, not as having quietly answered it.
- **Points-per-game pricing counts a rostered-but-inactive/bye week as 0.0**
  (§2.2) — a known, symmetric limitation that dilutes PPG for long-bench
  players uniformly across both snapshots and both hypotheses; it does not
  structurally favor 1a or 1b, but it does mean "Δ starting-lineup value" is
  not a precise points-per-game forecast, just a consistent relative
  yardstick.
- **Generalization is limited to 12-team, 6-slot, 4-round-rookie-draft
  dynasty leagues**, the same 2 real leagues (2 formats: SF/TEP median-match,
  1QB IDP) as the calibration report. Nothing here says anything about other
  league shapes.
- **`pick_pool_value`'s `scoring_format` argument is a documented no-op** in
  the shipped ladder today, so value-weighted capital does not distinguish
  SF/TEP from 1QB pick pricing — inherited from the app's own pricing code,
  not a limitation introduced by this analysis.

---

## 9. Reproducing this report

```bash
# One-time network capture (already run; fixtures are committed)
python3 scripts/outlook_pick_capital_capture.py

# Offline analysis — every number in this report
python3 scripts/outlook_pick_capital_hypothesis.py
```

| Artefact | Path |
|---|---|
| New fixtures (traded_picks, filtered trade transactions, player positions) | `backend/tests/fixtures/outlook-hypotheses/` |
| Capture script | `scripts/outlook_pick_capital_capture.py` |
| Analysis script | `scripts/outlook_pick_capital_hypothesis.py` |
| Reused, unmodified | `scripts/outlook_calibration_backtest.py` (fixture loader, `as_of()`, `truth()`), `backend/outlook/strength.py` (`starting_lineup_value`), `backend/outlook/pipeline.py` (`run_outlook`), `backend/pick_values.py` (`pick_pool_value`) |
| Calibration report this builds on | `docs/feedback/items/169-outlook-league-summary/calibration-report-2026-08-09.md` |

Test posture: backend suite **2173 passed / 1 skipped / 1 xfailed** before
this work (baseline re-confirmed on a fresh `origin/main` reset,
2026-08-09). No file under `backend/` was modified; only new scripts and
fixtures were added, so the suite is unaffected. No feature flag touched.
