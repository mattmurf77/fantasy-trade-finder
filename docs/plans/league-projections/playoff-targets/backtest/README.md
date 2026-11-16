# Playoff targets: backtest of the shown gains against completed seasons

Date: 2026-11-15. Research only: no product code, configuration or flag changed (the feature is
live, D-271). This answers the scope's waiver W3 ("no backtest of the number against real
seasons"), which the operator has now asked for.

Data: 13 completed league-seasons (2022 to 2025) of 4 of the operator's league lineages, all
12-team, 14 regular-season weeks; forecasts rebuilt for the Tuesday before weeks 4, 6, 8 and 10
(52 forecasts, 624 team-forecasts). Every number below is reproduced by one command (bottom of
this page) and stored in [`result.json`](result.json) (aggregates only: no league, team, manager
or player).

## The answer

**Keep the calculation as it is. No caveat line is needed for accuracy (the footer already says a
real trade costs something). One small settings change is worth making: raise `min_playoff_gain`
from 0.01 to 0.02.**

1. **The shown chance gain is right on average.** Over 4,336 listed rows the feature promised
   +8.6 percentage points on average; replaying the rest of each season with actual points, the
   move put the viewer into the playoffs (net of moves that knocked him out) in 9.1% of rows. Bias
   −0.5 points (95% interval −2.9 to +1.8). Leaving out any one of the four lineages moves the
   bias between −1.8 and +0.5 points. If a row says +8, about 8% of such rows come true.
2. **Calibration holds where it matters.** Rows promising 2 to 5 points came true 6.7% of the time
   (2.6% to 11.3%), 5 to 10 points 9.7% (5.6% to 13.4%), 10 points or more 15.5% (10.5% to 21.2%,
   against 16.9 promised). The one miss is at the bottom: rows promising 1 to 2 points (350 rows)
   came true once (0.3%, interval 0 to 0.9%, against 1.5% promised). They come almost entirely from
   viewers already near 0% or near 100%, and they are inside the simulation noise of the paired
   5,000-run re-run (about ±0.5 points). Raising the threshold to 2 points removes 9% of passing
   rows; the rest stay calibrated (bias −0.8 points).
3. **The order is useful.** The #1 row came true 17.7% of the time (12.5% to 22.7%), rows 2 and 3
   9.3%, rows 4 to 8 7.2%. A random player from the same selling teams with a positive projected
   gain came true 3.3% of the time, and any random player on those teams 1.9%. Paired inside the
   same forecast, the #1 row beats a random candidate by 14.3 points (9.8 to 18.9).
4. **The forecast it rests on is well calibrated.** The baseline playoff chance scores a Brier of
   0.111 against the replayed season (0.105 against the real one); always saying 50% would score
   0.250. Teams given 95% or more all made it (111 of 111); teams given under 5% made it 1.5% of
   the time.
5. **The lineup gain (points) is slightly too small.** Listed rows show 45.3 points over the rest
   of the season; the same weeks with actual points and lineups set by projection give 49.7 (bias
   −4.4, −6.6 to −2.2): about a tenth more than shown. Against the hindsight-best lineup it is 38%
   more. No caveat line: the figure only orders the rows, and the error is small next to its own
   spread (MAE 23 points).

**How rare flips are, and what n means.** A row "comes true" only if the viewer's playoff place
actually changes. Of 549 viewer-forecasts with rows, 134 had at least one row that flipped the
viewer in and 23 one that flipped him out; the 441 flips in come from those 134 forecasts (about
3.3 rows each), because the rows of one forecast share the same season. The intervals resample
whole league-seasons, which accounts for this, but they rest on 13 league-seasons in 4 lineages:
good enough to rule out a large bias (more than about 3 points either way), not to tune the
number finely.

**What this does not test:** the trade itself. The backtest makes the same assumption as the
feature (P4: the viewer gives up nothing, the other team gets nothing back), so it shows the
forecast does what it says, not that a real trade would gain this much. It also uses each week's
final projection rather than one made weeks ahead (see "What it does not capture").

## Terms

- **Row**: one player the feature lists for one viewer in one forecast (`compute`'s output: the
  top 8 by projected lineup gain, re-simulated, kept when the chance rises).
- **Predicted gain**: the row's `playoff_probability.after − now`, as the app shows it.
- **Realised gain**: replay the rest of the regular season with actual points twice, without and
  with the move; made the playoffs with the move minus without it: +1, 0 or −1. The mean over
  rows is directly comparable to the mean predicted gain.
- **Comes true / flip in**: realised gain +1. **Flip out**: −1 (the player costs the viewer his
  place: he scores less than projected in the weeks he is started, or his old team now beats
  someone the viewer needed it to lose to, or the reverse).
- **Lineup gain**: the row's `lineup_gain_exact`: projected points added to the viewer's lineup over
  the remaining weeks. **Realised lineup gain**: the same weeks, actual points, lineup chosen by
  projection.
- **Bias**: predicted minus realised (negative = the shown number is too small).
- **95% interval**: re-drawing the 13 league-seasons with replacement 1,000 times.
- **Brier score**: mean squared gap between a chance and the 0/1 outcome (lower is better).

## 1. How it was run, and what was checked

**Product code the backtest runs, unmodified:**

| Step | Product code |
|---|---|
| The Tuesday snapshot before week w | `provider.capture` (with its own record, points-for and points-against reconciliation, free-agent pool, IDP replacement means and side channel) |
| Each future week's projection rows | `provider.SleeperExperimentalFeed.weeks`, called once per week, on the cached Sleeper projections |
| The forecast | `simulation.simulate` at the configured 250,000 runs, then `clinch.attach` (as `service._run`) |
| The rows | `playoff_targets.compute` with `config/league_projections.json`'s `playoff_targets` settings, for every team as the viewer |
| Step one again, for the candidate pool and the nulls | `playoff_targets.lineup_gains` and `_base` |
| Who makes the playoffs in a replayed season | `simulation.simulate` with every week entered as an observed score: the product's records, median game, points-for and points-against tiebreak and lottery |
| Projected points in the replay | `season_points._entry_points` on the feed's rows (the same scoring the snapshot uses) |
| The lineup a manager starting by projection sets | `core.optimize` then `core.free_agent_fill` |

**What it replaces (every deviation from the product):**

- `provider.capture` reads league, rosters, matchups, users, picks and the player file through a
  stand-in fetch built from the cache: the league's own settings; **rosters as at the end of week
  w−1** (Sleeper's matchup `players` list; taxi and reserve status in past weeks is unknown, so
  every rostered player counts as active); records and points rebuilt from the recorded matchups
  (capture's own reconciliation then checks them); official max PF to date from the hindsight best
  lineups (it does not enter the playoff chance); **no users** (no names read) and **no traded
  picks** (pick ownership does not enter the playoff chance); future weeks' matchups reduced to
  what Sleeper shows before kickoff (pairings and current rosters, no scores).
- The feed is called one week at a time with each player's NFL team **that week** (from that
  week's projection or stats row, else the nearest week's), because today's player file has
  today's teams. The weekly score rows are rewritten to their pre-kickoff state so the product's
  timing contract reads the games as not yet played. Injury labels are left empty.
- **No saved outlooks** exist for past seasons, so a team is selling only when its chance is below
  50% (`seller_outlooks={}`).
- The read (`compose`) is not run: it re-applies the seller rule with live outlooks, which do not
  exist here. The time budget is not applied (`compute` was never cancelled).
- The realised replay is the backtest's own code (lineups by projection, scored with actual
  points; see section 3), with the product's standings code deciding places.

**Checks:**

| Check | Result |
|---|---|
| Actual points from Sleeper's weekly stats under each league's scoring equal the recorded `players_points` | 63,672 of 63,672 player-weeks |
| Replaying the **recorded** scores through the product's standings code reproduces the real playoff field (Sleeper's winners bracket) | 156 of 156 teams |
| The product's own parity check (`maxpf_moves.parity`): every team-week of every rebuilt snapshot re-solves to the stored projected scores | 4,992 team-weeks, 0 mismatches |
| The replay's projected points equal the snapshot's (`season_points.player_points`) | 145,267 player-weeks, 0 mismatches |
| An independent exact check (a dynamic programme over open slots, no assignment algorithm) agrees with `playoff_targets.lineup_gains` | 1,714 player-weeks, 0 mismatches (321 weeks with a free-agent or IDP fill skipped: the programme does not model them) |
| Step one's gain equals the row's `lineup_gain_exact` | all 4,336 rows, to the cent |
| The same forecasts re-run with another simulation seed (Monte Carlo noise of the shown "after") | 1,032 rows: mean absolute difference 0.4 points, SD 0.55; 18 rows change pass/fail |
| The baseline replay (every lineup by projection) against the real playoff field | 92% of team-forecasts agree (89% to 95%): real managers did not always start by projection and rosters changed; reported, not forced |
| Unit tests on a synthetic league with known answers | `backend/tests/test_playoff_targets_backtest.py`, 21 tests |

**Sample.**

| | Count |
|---|---:|
| League-seasons | 13 (4 lineages): 2022 ×2, 2023 ×3, 2024 ×4, 2025 ×4; 2 play the weekly median, 4 have IDP and kicker slots |
| Excluded by the product | 5 league-seasons of a fifth lineage: its lineup has a team-defense slot, which `provider.capture` refuses (`unsupported_lineup`) |
| Forecasts | 52 (weeks 4, 6, 8, 10 in every league-season; none at or after a trade deadline) |
| Team-forecasts | 624: 549 with rows, 12 computed with no row, 61 skipped near certain (99%+), 2 proven eliminated |
| Re-simulated candidates | 4,488, of which 4,336 listed (chance rose) and 3,720 passing the 1-point threshold |
| Null draws | 1,122 random players with a positive projected gain, 1,122 random players from the selling teams |

## 2. The playoff-chance gain (the headline)

**All listed rows, and by the threshold.**

| Rows | n | Mean predicted | Mean realised (95% interval) | Bias | Flips in | Flips out |
|---|---:|---:|---|---|---:|---:|
| All listed | 4,336 | 8.6% | 9.1% (6.7% to 11.5%) | −0.5 (−2.9 to +1.8) | 441 | 48 |
| Passing (≥ 1 point) | 3,720 | 9.9% | 10.6% (8.0% to 13.5%) | −0.7 (−3.9 to +2.0) | 440 | 46 |
| Not passing | 616 | 0.4% | −0.2% (−1.0% to +0.5%) | +0.6 | 1 | 2 |

**Calibration by predicted gain** (the question that matters: if rows say +8, do 8% flip?).

| Predicted gain | n | Mean predicted | Mean realised (95% interval) | Flips in / out |
|---|---:|---:|---|---|
| under 1 point | 617 | 0.4% | −0.2% (−1.0% to +0.4%) | 1 / 2 |
| 1 to 2 | 350 | 1.5% | 0.3% (0.0% to 0.9%) | 1 / 0 |
| 2 to 5 | 733 | 3.5% | 6.7% (2.6% to 11.3%) | 55 / 6 |
| 5 to 10 | 1,107 | 7.4% | 9.7% (5.6% to 13.4%) | 124 / 17 |
| 10 or more | 1,529 | 16.9% | 15.5% (10.5% to 21.2%) | 260 / 23 |

Rows under 2 points promised 7.6 flips in all; there were 2 in and 2 out. Rows of 2 points or more
are calibrated within their intervals (the 2-to-5 bin lands high, the top bin slightly low).

**What a higher threshold would keep** (rows with predicted gain at least the threshold):

| `min_playoff_gain` | Rows | Mean predicted | Mean realised | Bias |
|---|---:|---:|---:|---|
| 0.01 (shipped) | 3,720 | 9.9% | 10.6% | −0.7 |
| **0.02** | 3,369 | 10.8% | 11.7% | −0.8 |
| 0.03 | 3,132 | 11.5% | 12.3% | −0.9 |
| 0.05 | 2,639 | 12.9% | 13.0% | −0.2 |
| 0.10 | 1,531 | 16.8% | 15.6% | +1.2 |

**By forecast week** (later forecasts have fewer weeks left, so smaller gains):

| Forecast before week | Rows | Mean predicted | Mean realised (95% interval) | Bias |
|---|---:|---:|---|---|
| 4 | 1,208 | 10.7% | 9.4% (6.6% to 12.8%) | +1.3 (−1.5 to +4.0) |
| 6 | 1,134 | 9.9% | 11.4% (8.8% to 14.3%) | −1.5 (−4.9 to +1.5) |
| 8 | 1,053 | 7.8% | 8.4% (5.8% to 11.5%) | −0.6 (−3.9 to +2.2) |
| 10 | 941 | 5.2% | 6.7% (4.3% to 9.6%) | −1.5 (−3.8 to +0.5) |

**By the viewer's baseline chance:**

| Chance now | Rows | Mean predicted | Mean realised (95% interval) |
|---|---:|---:|---|
| under 10% | 1,088 | 3.6% | 3.3% (0.4% to 6.6%) |
| 10% to 30% | 688 | 14.0% | 10.5% (5.2% to 16.9%) |
| 30% to 50% | 512 | 16.1% | 18.8% (11.5% to 26.5%) |
| 50% to 70% | 568 | 13.6% | 14.1% (8.0% to 20.9%) |
| 70% to 90% | 720 | 8.0% | 10.7% (5.1% to 16.4%) |
| 90% or more | 760 | 2.6% | 4.2% (0.0% to 9.0%) |

**Leave one lineage out:** bias −0.0, −0.6, +0.5 and −1.8 points; mean realised 8.5% to 9.7%.

**A diagnostic, not a test:** split by the baseline replay's own outcome, rows of viewers who
made it can only flip out (2,008 rows, −2.4%) and rows of viewers who missed can only flip in
(2,328 rows, +18.9%). The forecast cannot know which side a viewer will land on; averaged over
both it is right.

**The sellers pay.** In 446 rows the player's old team's own result changed: 416 times it lost a
playoff place it had in the baseline replay (it had been under 50%, not out), 30 times it gained
one (the order of other teams changed).

## 3. The ranking

| Rows | n | Mean realised gain (95% interval) | Flipped in | Flipped out | Mean predicted |
|---|---:|---|---:|---:|---:|
| Listed #1 | 549 | 17.7% (12.5% to 22.7%) | 17.9% | 0.2% | 13.3% |
| Listed #2–3 | 1,093 | 9.3% (6.0% to 12.8%) | 10.6% | 1.3% | 10.3% |
| Listed #4–8 | 2,694 | 7.2% (5.2% to 9.3%) | 8.4% | 1.2% | 7.0% |
| Re-simulated, not listed (chance did not rise) | 152 | 0.0% | 0% | 0% | |
| Null: random seller player with a positive projected gain | 1,122 | 3.3% (1.8% to 5.0%) | 4.4% | 1.1% | |
| Null: random player on the selling teams | 1,122 | 1.9% (1.0% to 2.8%) | 2.9% | 1.0% | |

Paired inside the same viewer-forecast: #1 minus a random candidate, +14.3 points (9.8 to 18.9),
1,098 pairs. Rank correlation of predicted and realised gain within listed rows: 0.20 (0.13 to
0.26); low because the realised outcome is 0 for most rows, but positive throughout.

The #1 row comes true more often than its own figure says (17.7% against 13.3%), and the lower
rows about as often as theirs. The ordering by chance gain adds real information over the
projected-points order the feature uses to pick its 8 (a random positive-gain candidate is far
below every listed rank).

## 4. The baseline chance

| | n | Brier | Always say the base rate |
|---|---:|---:|---:|
| All team-forecasts, against the replayed season | 624 | 0.111 (0.088 to 0.137) | 0.250 |
| All team-forecasts, against the real season | 624 | 0.105 (0.078 to 0.130) | 0.250 |
| Viewers with rows, against the replay | 549 | 0.126 (0.101 to 0.152) | 0.248 |
| Viewers with rows, against the real season | 549 | 0.117 (0.090 to 0.140) | 0.248 |

Reliability, all team-forecasts against the replay:

| Chance now | n | Mean chance | Made it (95% interval) |
|---|---:|---:|---|
| under 5% | 134 | 1.0% | 1.5% (0% to 4.0%) |
| 5% to 20% | 73 | 12.5% | 15.1% (6.8% to 24.3%) |
| 20% to 40% | 69 | 30.4% | 24.6% (14.7% to 37.3%) |
| 40% to 60% | 59 | 50.2% | 52.5% (37.3% to 68.1%) |
| 60% to 80% | 93 | 70.6% | 73.1% (63.3% to 82.1%) |
| 80% to 95% | 85 | 89.0% | 84.7% (75.5% to 93.7%) |
| 95% or more | 111 | 98.7% | 100% (100% to 100%) |

No sign of overconfidence at the extremes on these seasons (if anything the top band is
slightly cautious), consistent with the 2026 calibration check.

## 5. The lineup gain (points)

Predicted: the row's `lineup_gain_exact` (projected re-solve, roster fixed at the forecast,
summed over the remaining weeks). Realised, three ways, same weeks:

| Realised as | n | Predicted | Realised | Bias (95% interval) | MAE | Rank correlation | Realised ÷ predicted |
|---|---:|---:|---:|---|---:|---:|---:|
| **Each week's real roster, lineup by projection, actual points** | 4,336 | 45.3 | 49.7 | −4.4 (−6.6 to −2.2) | 23.1 | 0.64 | 1.10 |
| Roster fixed at the forecast (as predicted), lineup by projection | 4,336 | 45.3 | 51.1 | −5.9 (−8.0 to −3.6) | 22.0 | 0.67 | 1.13 |
| Each week's real roster, hindsight-best lineup | 4,336 | 45.3 | 62.6 | −17.4 (−20.1 to −14.8) | 22.4 | 0.72 | 1.38 |
| Null: random player on the selling teams (real roster, by projection) | 1,122 | 12.5 | 13.4 | −0.8 (−2.0 to +0.3) | 11.0 | 0.60 | 1.07 |

Points-for counts the lineup the manager starts, so the first line is the right comparison. The
realised gain is about a tenth above the shown one; the shortfall is largest for the biggest
figures (the feature picks the highest projected gains, and here those players beat their projection).

**By predicted lineup gain** (listed rows):

| Predicted | n | Mean predicted | Mean realised | Bias | Realised 0 or less |
|---|---:|---:|---:|---|---:|
| 5 to 10 | 29 | 8.0 | 7.0 | +1.0 | 38% |
| 10 to 20 | 452 | 16.1 | 15.2 | +0.9 (−1.0 to +3.1) | 25% |
| 20 to 40 | 1,634 | 30.3 | 32.6 | −2.3 (−5.0 to +0.4) | 11% |
| 40 or more | 2,221 | 62.7 | 69.8 | −7.1 (−10.5 to −4.1) | 2% |

**By position** (listed rows): RB 1,794 rows, bias −5.2; WR 1,342, −7.4; QB 569, −4.3; TE 349,
−0.3; defensive players 281 (one lineage), +6.7 to +15.9 by position (IDP projections overstate);
one kicker.

**By weeks remaining:** 11 weeks −4.5, 9 weeks −5.0, 7 weeks −3.6, 5 weeks −4.5: flat, so the
shortfall is not growing with the horizon on these final-week projections.

## 6. What it does not capture

- **The trade.** Same assumption as the feature (P4): the viewer gives up nothing, the other team
  gets no starter back. The footer already says the true gain of a real trade is usually smaller.
- **Final-week projections.** The snapshot uses each future week's last Sleeper projection, not one
  made weeks ahead (the 2025 rows checked are stamped after the week's last game, as the 2026
  calibration check found for 2026). The live forecast projects up to eleven weeks ahead from Tuesday's numbers, which are
  less accurate, so the live chance gains will be noisier than this. The live baseline chance may
  be less sharp than the Brier 0.11 here.
- **Rosters.** The counterfactual moves the player at the forecast and then uses each later week's
  real rosters plus or minus him: if he would have been traded or dropped later, he is still moved
  to the viewer and removed from whoever held him that week (88% of his remaining weeks were with
  the seller; he was on some roster in 99.9%). The viewer's own later moves are real. Nobody
  reacts to the trade (no counter-moves, no changed waiver claims).
- **Lineups by projection.** Every team in the replay starts its best projected lineup. Real
  managers did not (the baseline replay matches the real playoff field for 92% of teams).
- **Taxi and reserve.** Past status is unknown: every rostered player counts as active, in the
  snapshot and in the replay (players on reserve rarely have a projection, so rarely start).
- **Free agents.** Open slots in the replay take the best projected free agent that week, scored
  with his actual points, as the product fills the projection. Each team draws from the same pool
  independently (two teams may "use" the same free agent). IDP bye fills with a replacement mean
  (a projection device) are not used in the replay: such a slot scores 0.
- **Outlooks.** No saved Rebuilding/Tanking outlooks exist for past seasons, so sellers are teams
  under 50% only. Teams above 50% with such an outlook would add rows not tested here.
- **The sample.** 13 league-seasons in 4 lineages of the operator's own leagues, all 12-team,
  6-team playoffs, mostly superflex or IDP. Formats the product refuses (team defense, divisions)
  are out. Rows from one forecast and forecasts from one season are correlated; the intervals
  resample whole league-seasons, which covers that within this set but not other formats.

## 7. Still to validate

1. Re-run on the frozen pregame snapshots the weekly job saves (90-day retention): measures the
   horizon effect and removes the post-game-information doubt, for both the chance gain and the
   baseline chance.
2. After the 2026 regular season ends: score the rows actually shown this season, with real
   saved outlooks.
3. Real trades: for trades the app captured, the receiving team's chance change against what
   the row promised (with what it gave up).

## Reproduce

```
python3.12 docs/plans/league-projections/playoff-targets/backtest/fetch_cache.py /path/to/cache ROOT_IDS...
python3.12 docs/plans/league-projections/playoff-targets/backtest/backtest.py /path/to/cache
```

The first command (network, GET only) fills the cache from the 2026 root leagues of the operator's
five lineages (the ids are in `docs/business/analytics/2026-08-16-organic-trade-corpus.md`); it
never fetches users. The cache used here is at `~/Documents/Claude/Projects/ftf-research-cache/sleeper`
(outside the repo, 527 files). The second command disables network sockets before reading anything,
finds the league-seasons from the cached matchups, excludes formats `provider.capture` refuses, and
writes `result.json` next to itself: about 20 minutes on 11 workers (`--workers`), then a few
minutes of bootstrap (`--reps`, default 1,000). Seeds are fixed. `--rows PATH` writes a per-row dump
with ids for checking; it refuses a path inside the repo. Needs the repo's Python requirements.
Unit tests: `backend/tests/test_playoff_targets_backtest.py`.
