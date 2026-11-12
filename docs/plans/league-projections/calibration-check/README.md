# Are the playoff odds overconfident? (calibration check, model v5/v6)

Date: 2026-11-12. Research only: no production code or configuration changed.
Data: the cached Sleeper responses behind [`../universal-sd/`](../universal-sd/README.md),
9 leagues, 110 teams, weeks 1–9 of 2026, 990 team-weeks, 495 head-to-head games.
Five of the nine leagues also play the weekly median game. Every number below is reproduced
by one command (bottom of this page) and stored in [`result.json`](result.json) (aggregates only).

## Verdict

**No evidence that the odds are overconfident because weeks are treated as independent.**
The suspected mechanism (a team that misses its projection this week tends to miss it the
same way next week) is not in this data. If anything the errors lean slightly the other
way: a team that beats its projection one week tends to give some of it back later. Adding the
kind of persistent team draw v4 had (SD 5) moves published odds by 0.3 points on average and
1.7 points at most.

**The extreme odds come from real gaps between teams.** Inside a league, teams' projected
weekly totals differ by about 21 points (one standard deviation), almost as much as the
week-to-week noise (25). With five weeks left, that alone puts about a third of teams at
95% or better and another third at 5% or worse. Those gaps are not exaggerated: a team
projected 10 points above its league scores about 10 to 11 points above it.

**The operator's example is plausible.** Among teams that were 5–4 after week 9 in these
leagues, the model's odds ranged from about 18% to 97%, and one was above 95%, with or
without a persistent draw.

**What this data cannot rule out.** (1) Error that grows with how far ahead the forecast is
made: the cache only has each week's *final* projection, while the live model projects up to
five weeks ahead. A rough proxy (below) suggests this costs the near-certain teams 1 to 5
points, not 10. (2) Sleeper's stored projections may contain information from after the
games. That would make errors look smaller and less persistent than live errors, so it biases
this check **toward** "not overconfident". Confidence: moderate. One season, nine leagues; the
intervals are wide, but they exclude anything large.

**Recommendation:** do not restore a persistent team draw on this evidence. Keep SD 25.
Re-test with the frozen pregame snapshots the weekly batch now saves (see "What to validate
next"), which measures the one thing this cache cannot.

## How to read the numbers

- **Error** = what a team scored minus its projected best lineup that week. Negative = scored less.
- **Relative error** = a team's error minus the average error of its league that week. If
  every team in a league misses by 10 together, nobody's standing changes, so only relative
  error matters for playoff odds.
- **95% interval** = the range the true value very probably lies in, given how few teams we
  have. It comes from re-drawing whole teams at random (inside each league) 1,000 times and
  recomputing.

## Step 1. The table reproduces the earlier backtest exactly

| | Team-weeks | Mean error | RMSE (typical miss) |
|---|---:|---:|---:|
| Weeks 1–6 | 660 | −3.05 | 24.54 |
| Weeks 7–9 | 330 | −9.11 | 25.97 |
| All | 990 | −5.07 | 25.02 |

Same method (`../universal-sd/backtest.py`'s own `league_rows`, read from the cache with the
network disabled), same numbers to the last digit.

## Step 2. Is a team's weekly error independent of its other weeks?

**Persistent team effect.** If some teams were systematically over- or under-projected, part
of the error would be a fixed amount per team (its SD is called *tau*). Splitting the error
variance three ways:

| Part | What it is | Estimate |
|---|---|---|
| Persistent team effect | the same miss every week for a team | **none** (variance −15 points², i.e. below zero; 95% interval −27 to −0.4) |
| League-week shock | the whole league misses together that week | about 0 inside a league (league-resampled interval −6 to +7 points²) |
| Week-to-week noise | everything else | 608 points² (SD 24.7) |

A below-zero team variance means teams' 9-week average errors are *more alike* than pure
chance would make them. The share of relative error that is persistent is −2.6%
(interval −5.0% to −0.1%). As a check, scrambling which team got which error inside each
league-week (which destroys any team effect) gives shares between −3.2% and +3.3% in 95% of
200 scrambles; the real data sit at the low edge (p = 0.05 one-sided).

**tau.** Point estimate **0**, with an interval of 0 to 0 (the variance is negative across the
interval). That interval is narrower than the data justify, so a second test: plant a team
effect of a known size into scrambled data and ask how often it looks as low as the real data.
At tau = 3, 1% of planted copies do; at tau = 5 (v4's value), none of 200. **A persistent team
SD of 3 points or more is inconsistent with this data.**

**Week-to-week correlation of a team's relative error:** next week +0.06 (−0.02 to +0.13);
two weeks later −0.04 (−0.12 to +0.04); three weeks later −0.08 (−0.16 to 0.00). Small, and
not the steady positive pattern a persistent effect would give.

**League-week shock, separately.** Across all leagues there is a common drift: the average
error by week runs −0.9, −8.0, +0.3, −0.4, +1.0, −10.2, −2.9, −6.9, −17.6 (week 9 interval
−21 to −13), about −1.3 points per week (interval −2.0 to −0.6). Its SD beyond chance is about
5.7 points. It is shared by every team in every league, so it does not move standings, and
the head-to-head and median games cancel it. Inside a league, errors of different teams in the
same week are slightly *negatively* related (−0.04; opponents −0.13), plausibly because NFL
production is partly zero-sum across fantasy rosters (two backs on one NFL team, a defense
against an offense). That is why the league-week component nets to about zero.

**Mean drift.** The −3 early / −9 late split in the earlier backtest is this common drift, not
a change in spread: the SD about the mean is 24.4 in both halves.

## Step 3. The direct test of independence at season scale

**Points.** Add up a team's relative errors over a window of weeks. If weeks were independent,
the spread of that sum would be √(weeks) × the weekly spread. Ratio of observed to expected
variance (1 = independent, above 1 = the model is too sure):

| Window | Observed SD of the sum | Independence says | Variance ratio | 95% interval |
|---:|---:|---:|---:|---|
| 3 weeks | 40.9 | 40.4 | 1.02 | 0.91 – 1.12 |
| 5 weeks | 49.2 | 52.2 | 0.89 | 0.76 – 1.01 |
| 7 weeks | 54.3 | 61.7 | 0.77 | 0.62 – 0.92 |
| 9 weeks | 62.4 | 70.0 | 0.79 | 0.60 – 1.00 |

Season-long totals are *less* uncertain than independence implies, not more.

**Wins.** For every head-to-head game, the model's pregame chance from the two projections and
SD 25. Per team over a window: actual wins minus the sum of those chances. Independence
predicts how big that gap should be; the ratio is observed over predicted (above 1 = more
surprise than the model allows):

| Window | Ratio (SD 25) | 95% interval | Scrambled-data range |
|---:|---:|---|---|
| 3 weeks | 1.07 | 0.95 – 1.19 | |
| 5 weeks | 1.13 | 0.93 – 1.34 | 0.87 – 1.23 |
| 7 weeks | 1.13 | 0.87 – 1.41 | |
| 9 weeks | 1.16 | 0.89 – 1.44 | 0.73 – 1.27 |

Slightly above 1, inside what chance gives (p = 0.16 at 5 weeks, 0.13 at 9). Wins carry the
opponent's luck as well as the team's, so they are a noisier test than points; points say no.

**Single games (reliability).** All 9 weeks, 495 games:

| Model says favourite wins | Games | Model average | Favourite actually won | 95% interval |
|---|---:|---:|---:|---|
| 50–60% | 116 | 55% | 50% | 41–59% |
| 60–70% | 127 | 65% | 63% | 54–71% |
| 70–80% | 112 | 75% | 83% | 75–89% |
| 80–90% | 79 | 85% | 86% | 77–92% |
| 90–100% | 61 | 95% | 87% | 76–93% |
| **All** | 495 | **71.8%** | **71.1%** | 67–75% |

Overall the model's game odds are right. The single-game SD that fits the outcomes best is 26
(21.5 to 31). The top bin is the one soft spot: games the model calls 90%+ were won 87% of the
time, and the interval stops just short of 95%. It is one bin of five and 61 games, so treat it
as a hint to re-check with pregame data, not a finding.

**Projected gaps between teams are not overstated.** Regressing actual (relative) scores on
projected (relative) scores gives a slope of 1.03 (0.97 to 1.10) per week and 1.12 (1.05 to
1.19) over nine weeks. A slope below 1 would have meant the projections exaggerate how far
apart teams are, which would make odds too extreme; they do not.

**Placebo.** Two scrambles, 200 times each:
- *Across teams within a league-week* (breaks any team link, keeps the weekly shocks): team
  share averages 0.0%, the 9-week points ratio 1.00, the 9-week wins ratio 1.00. The measures
  behave as they should when there is nothing to find.
- *A team's weeks in random order* (the shuffle the brief named): team share stays at −2.6% and
  the 9-week ratio at 0.79. This is expected, not a failure. Reordering a team's weeks keeps
  its total, so it cannot remove a team effect; it only tests ordering (lags 1 and 2 go to
  about −0.02). The across-team scramble is the right placebo for the team effect.

## Step 4. How much would playoff odds move?

**Missing data, so this is an illustration.** The remaining schedule (weeks 10–14) and the
future-week projections are not cached, and the schedule cannot be derived from weeks 1–9
without guessing: the 12-team leagues have played 9 of 11 opponents and still owe 2 new games
and 3 repeats in an unknown order. So each league is simulated with its real records, points
for and against after week 9, playoff spots and median game, but with:
- a team's future weekly mean = its average projected best lineup over weeks 7–9;
- a **random pairing each remaining week of each simulated season**, not the real schedule.

These are therefore not the leagues' published odds. The comparison between assumptions is
still meaningful because both runs share the same states, schedules and random draws. The
engine matches the production simulator (`simulation.simulate`) on a fixed schedule: largest
difference 0.9 points, within Monte Carlo error (|z| under 2), for one median and one
head-to-head league. 40,000 seasons per league per scenario; repeating (a) with another seed
moves odds 0.08 points on average and 0.5 at most (the noise floor).

| Scenario | Persistent SD | Weekly SD | Teams ≥95% | Teams ≤5% | Mean change | Largest change | Teams at 85–99% under (a), average |
|---|---:|---:|---:|---:|---:|---:|---:|
| (a) live model | 0 | 25 | 37 | 36 | | | 93.1% |
| (b) tau from data, and its interval ends | 0 | 25 | 37 | 36 | 0 | 0 | 93.1% |
| (b) tau = 3, the largest the data allow | 3 | 24.8 | 37 | 36 | 0.1 pt | 0.7 pt | 92.8% |
| (b) v4's persistent SD 5 | 5 | 24.5 | 37 | 35 | 0.3 pt | 1.7 pt | 92.3% |
| (b) hypothetical 10 (not supported) | 10 | 22.9 | 35 | 33 | 1.3 pt | 5.8 pt | 90.3% |
| (d) horizon drift 3.8/wk (2.8–4.5) | 0 | 25 + drift | 36 | 35 | 0.5 pt | 2.4 pt | 92.1% |
| (d) horizon drift, bye-free weeks 6.6/wk | 0 | 25 + drift | 36 | 33 | 1.3 pt | 6.1 pt | 90.4% |

Of 110 teams, 17 sit between 85% and 99% under (a). They fall 0.1 to 0.6 points with tau = 3,
0.2 to 1.7 with tau = 5, 0.6 to 2.0 with the drift estimate, and 1.6 to 5.0 with the larger
early-season drift. Low-odds teams rise by similar amounts.

**Horizon-growing uncertainty (d).** Measured indirectly, so treat it as a proxy. How far a
team's projected total (relative to its league) moves between week w and week w+h grows with
h: half the mean squared change is 58 at one week apart and 90 at five. The growth is about 15
points² per week, i.e. a random-walk drift of **3.8 points per week** (interval 2.8 to 4.5).
Byes make weeks 5–9 noisy; in the bye-free weeks 1–4 the growth is faster, **6.6 per week**
(33 → 61 → 76). In (d) each team's future mean wanders by that drift, step by step, on top of
the weekly SD 25. This is the closest the cache gets to "a projection made five weeks ahead is
less certain"; it misses errors in the forecast itself that never show up as a change in the
weekly projection. It is the only effect found that pushes odds toward 50%, and it is small.

## Step 5. Is "a 5–4 team at 95.8%" plausible?

| Teams one game over .500 after week 9 | Teams | (a) range (median) | ≥95% under (a) | (b) tau = 3 | (d) drift 3.8 |
|---|---:|---|---:|---|---|
| Head-to-head leagues, 5–4 | 9 | 18% – 97% (58%) | 1 | 18% – 97% | 19% – 97% |
| Median leagues, 10–8 (closest equivalent) | 3 | 15% – 96% (42%) | 1 | 16% – 96% | 18% – 95% |

Yes. A 5–4 team with a much stronger projected lineup than the teams around it reaches the
mid-90s under every assumption tested here. A whole league with four teams at 95% or more is
also ordinary here: 37 of 110 teams are at 95% or better under (a).

## Step 6. Verdict detail and caveats

- **Overconfident? Not from persistence.** Best estimate: weekly independence costs nothing,
  and anything up to a 3-point persistent SD (the most the data allow) moves odds by under one
  point. The largest plausible effect found (horizon drift at the bye-free rate) is about 1
  point on average and 5 to 6 points at most, on teams that are near-certain or near-hopeless.
- **How sure.** One season, weeks 1–9, 9 leagues, 110 teams. Enough to exclude a persistent
  effect of v4's size (SD 5) and anything larger; not enough to pin down effects of 1 to 2 points.
- **Post-game information.** Sleeper's stored rows for past weeks are stamped the Tuesday after
  the games. If they were revised with what happened (an injury known only after kickoff, a role
  change), errors look smaller and less persistent than live errors. Both bias this check toward
  "independent, not overconfident". The mild mean reversion found here may itself be a symptom:
  projections that chase recent results would overshoot after a big week. Size of the bias:
  unknown from this cache.
- **Future means.** The live model uses provider projections for each future week from the
  current roster. Their error at five weeks ahead is not measured here except by the drift proxy.

**Recommendation.** No change to the model on this evidence: keep independent weekly draws at
SD 25 and do not restore v4's persistent draw (it would make the published odds slightly less
extreme without data behind it). If a later check finds horizon error, the mechanism to reuse is
v4's: one draw per team per simulated season (`strength = rng.gauss(0, persistent_sd)` added to
every future week's score; config key `persistent_sd`, removed by D-229). A random-walk version
that grows with weeks ahead would fit horizon error better. Either change needs, before it ships:
an estimate from frozen pregame projections (below), a sensitivity run on saved league states with
the real schedule, `core.VERSION` bumped with `model.score_sd`, and the published spread checked
against realized results.

## What to validate next

1. **Frozen pregame projections (the app's own).** The weekly batch saves real Tuesday snapshots
   (`snapshot_json`). For each saved week-N run, compare the projection it made for weeks N+1 to
   N+5 with the recorded scores. That measures error by weeks ahead directly, and its persistence,
   without the post-game question. Retention is 7 days (baseline runs 90): pull them weekly.
2. **The exact version of step 4.** Fetch the URLs below into the cache and re-run the same command;
   the script switches to the real schedule automatically.

## Larger validation (a few thousand past league-seasons, no projections)

Data: weekly scores, schedules and final playoff results; no pregame projections.

- **Stand-in for the projection:** each team's average score to date, shrunk toward the league
  average (more shrinkage early in the season; a fixed amount fitted once on held-out seasons).
  Points scored to date is what the projection is trying to predict, and it is available in
  every past season. It is a weaker forecast than a lineup projection, so its errors are larger;
  the test is about the *structure* of the errors, not their size.
- **Persistence:** repeat steps 2 and 3 on the errors of the stand-in (score minus stand-in made
  before that week): team share, lag correlations, the points ratio and the wins ratio by window.
  Thousands of seasons narrow the intervals here by roughly 20 times.
- **The test that matters:** at week N (6, 8, 10), simulate each past season to its end with the
  stand-in means, SD fitted to the stand-in's own weekly error, and (a) independent weeks, (b)
  a persistent draw at several SDs, (c) a random-walk drift. Score each against the real outcome:
  for teams given 90–95%, 95–99% and 99%+, how often did they make the playoffs? Report Brier
  score and log loss by week N and the reliability curve with intervals. The model is
  overconfident if teams at 95%+ make it clearly less than 95% of the time.
- **Bridge to the live model:** fit the same measurements on this season's frozen pregame
  projections and check that the stand-in's error *structure* (team share, drift per week) is
  similar. If it is, the historical reliability curve transfers; if not, use it only as a bound.

## Missing data for an exact run (50 URLs)

- `https://api.sleeper.app/v1/league/{league_id}/matchups/{week}` for weeks 10–14, for each of the
  9 supported leagues (45 URLs; the remaining schedule).
- `https://api.sleeper.app/projections/nfl/2026/{week}?season_type=regular` for weeks 10–14
  (5 URLs; future-week projections; optional, the script uses the weeks 7–9 average).

The full list with league ids is written outside the repo by `--missing-out` (never committed).

## Corrections to the earlier backtest

- "Favourites also won more often than a pregame forecast usually manages" is not supported over
  all 9 weeks: favourites won 71.1% against the model's own 71.8%. The remark rested on one 35-game
  bin of weeks 7–9. Calibration at SD 25 is partly built in (the SD was fit to these errors), so
  this is not evidence against post-game leakage either.
- Its −3 / −9 mean-error split is a common weekly drift shared by every team in every league (about
  −1.3 points per week), which does not move standings. The README already notes it is not corrected;
  that is right.
- Nothing else found wrong. Its headline numbers reproduce exactly.

## Reproduce

```sh
python docs/plans/league-projections/calibration-check/calibration_check.py \
    --cache /path/outside/repo/cache --leagues /path/outside/repo/league_ids.txt \
    --out docs/plans/league-projections/calibration-check/result.json \
    [--missing-out /path/outside/repo/missing_urls.txt]
```

About 30 seconds. Needs numpy (not a repo dependency; the statistics module itself is standard
library). The script refuses the network: a cache miss raises. Seeds are fixed, so the output is
identical run to run. Pure pieces: `calibration_stats.py`, tested by
`backend/tests/test_projection_calibration_stats.py`.
