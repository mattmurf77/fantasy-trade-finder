# Max PF moves: leave-one-out accuracy backtest

Date: 2026-11-12. Research only: no product code or configuration changed; the flag
`league.max_pf_moves` stays off. This answers operator decision 11 (exploration §14): "run the
leave-one-out backtest, then decide whether risk 2 needs a caveat line or a tier 3 fix".

Data: the cached Sleeper responses behind [`../../calibration-check/`](../../calibration-check/README.md):
9 leagues, 110 teams, weeks 1–9 of 2026, 990 team-weeks, 28,682 player-weeks. Every number
below is reproduced by one command (bottom of this page) and stored in
[`result.json`](result.json) (aggregates only: no league, team, manager or player).

## The answer

**Show it, with one caveat line, and keep the threshold at 5.**

1. **The list is right; the size is too small.** The players the feature would list really do
   lower max PF: over windows of five weeks or more, 99.4% of them had a real drop, 98% a real
   drop of 5 points or more, and none had a drop of the wrong sign. The order is good: four of
   the top five agree on average and the predicted #1 is in the real top three 85% of the time.
   But the real drop is bigger than the one shown: for listed players, 50 points against 37
   predicted, about a third more. The shortfall is in one direction every week, every position
   and every league.
2. **Risk 2 is real, and bigger than "small".** It is not about bench depth; it is about
   hindsight. A projected bench player shows 0, but in 28% of weeks he would have been in the
   best lineup in hindsight (average 5.7 points when he was). Starters' real drops are 1.4 times
   the predicted ones. How many players a team has at the position does not predict the gap.
3. **Recommendation: a caveat line now, no correction factor yet.** Suggested wording: "The
   real max PF loss is usually larger, roughly a third more, because in hindsight your bench
   would have started some weeks." A correction factor does work on this data (tested on each
   league with the factor fitted on the other eight), but it was fitted on projections that
   probably contain post-game information, and the pick-odds simulation compares every team on
   projected max PF, so correcting only the number shown would make the row disagree with the
   pick change beside it. Leave it until the frozen pregame snapshots can test it (see "Still
   unproven").
4. **The 5-point threshold is sensible.** It lists almost nothing that turns out to be zero
   (0.6% over five weeks or more). It hides real drops instead: two thirds of players predicted
   between 0 and 5 really dropped 5 or more. Raising it would hide more; lowering it would list
   players whose shown figure is mostly noise. The pick-movement conditions, which this data
   cannot test, decide most rows anyway.
5. **The operator's simple rule is not a better calculation.** It never shows less than the exact
   re-solve, and differs from it by more than 2 points for half of starters over five weeks or
   more. It lands slightly closer to the real drop over long windows only because it overstates
   in the same direction as the hindsight shortfall: right for the wrong reason. Week by week the
   exact re-solve is closer.

**Still unproven:** accuracy of the rest-of-season figure as the product computes it (projections
made weeks ahead, roster fixed); whether a listed move changes the draft pick at all (needs the
season to finish); behaviour on live, pregame projections.

## Terms

- **Max PF** (maximum points for): the points a team would have scored with its best possible
  lineup. Many dynasty leagues order the rookie draft for non-playoff teams by it.
- **Predicted drop**: for one player and one week, the best-lineup total from *projected* points
  with him minus without him. This is what the feature shows, summed over the remaining weeks.
- **Realised drop**: the same difference from *actual* points: the best lineup in hindsight with
  him minus without him. This is what really happens to max PF if he is gone.
- **Bias**: average of predicted minus realised. Negative means the feature shows too small a drop.
- **MAE** (mean absolute error): the typical size of the miss, either direction.
- **Rank correlation** (Spearman): 1 = the predicted order matches the real order exactly, 0 = no
  relation.
- **Window**: a start week *w* and every later week to week 9, with each week's own roster.
- **Listed**: a player the feature would show: among the eight largest predicted drops on his
  team, with a predicted drop of at least 5 (the shipped `min_drop_points`). The pick-movement
  conditions are not applied (they cannot be tested here).
- **95% interval**: the range the value very probably lies in, from re-drawing the 9 leagues with
  replacement 1,000 times. Splits that live in one league (kickers, defensive players) have no
  meaningful interval.

## 1. How it was run, and what was checked

**Product code the backtest runs.** For every league-week the script rebuilds a one-week
forecast snapshot from the cached feed and calls, unmodified:

| Step | Product code |
|---|---|
| Score each player's projection under the league's own scoring | `scoring.best_available` with `provider.LINEAR_PROJECTED_EVENTS` and `season_forecasts.normalize_scoring_for_slots` (the provider's best-available branch), then `season_points.player_points` |
| The predicted drop, player by player | `maxpf_moves.resolve` and its `_Context.lineups` (the max PF lane), `core.optimize` |
| The realised drop | `core.optimize(..., hindsight=True)` on actual points |

**What it replaces.** `provider.capture` and the provider's weekly feed (schedule, game timing,
injury and availability rules) need live endpoints; the script builds the same input rows from
the cached projection rows instead (`projected_input` in `backtest.py`). A player's bye is
inferred from his NFL team having no projected player that week (the cache has no schedule). The
provider's "team changed" rule is not applied (the player map in the cache is from November).
The free-agent pool is empty, so a removal that leaves a slot no one on the roster can fill
counts the slot as 0. `maxpf_moves.compute`, the simulation, pick odds and the pick-movement part
of the threshold are not run.

**Checks on the lineup solver** (Sleeper's matchups do not give a weekly max PF, so it cannot be
compared directly):

| Check | Result |
|---|---|
| Sleeper's starters add up to its recorded score | 990 of 990 team-weeks |
| Hindsight best lineup is never below the recorded score | 990 of 990 (equal in 11; on average 24.9 points above) |
| An independent exact check (a dynamic programme over open slots, no assignment algorithm) agrees with `core.optimize` on the full roster | 478 team-weeks, both projected and actual: 0 mismatches |
| The same, for every one-player removal, actual points | 150 random team-weeks, 4,383 removals: 0 mismatches |
| The same, for the predicted drops coming out of `maxpf_moves.resolve` | 12 random league-weeks, 2,852 drops: 0 mismatches (scratch script, not committed) |

Seven team-weeks had an empty starting slot in Sleeper; the hindsight best still fills it if the
roster can.

**Sample.**

| | Count |
|---|---:|
| Player-weeks | 28,682 |
| Priced (a usable projection) | 20,140: 10,201 projected starters, 9,939 projected bench |
| Bye (left out of the weekly figures, 0 on both sides) | 1,574 |
| No usable projection ("unknown"; the product leaves these players out) | 6,968 |
| By position, priced | WR 7,786 · RB 5,448 · TE 3,310 · QB 2,381 · defensive players 1,065 (one league) · K 150 (one league) |

The unknown player-weeks are almost all players who did not play: 96% scored 0, and only 0.6%
had a realised drop above 0.

## 2. One week at a time

| | n | Predicted (mean) | Realised (mean) | Bias | MAE | Rank correlation | Realised ÷ predicted |
|---|---:|---:|---:|---|---|---|---|
| All priced players | 20,140 | 2.45 | 4.20 | −1.75 (−1.90 to −1.61) | 3.38 (3.07 to 3.63) | 0.53 (0.51 to 0.55) | 1.72 (1.66 to 1.79) |
| Projected starters | 10,201 | 4.83 | 6.75 | −1.91 (−2.10 to −1.71) | 5.13 (4.63 to 5.47) | 0.41 (0.39 to 0.43) | 1.40 (1.36 to 1.43) |
| Projected bench | 9,939 | 0 | 1.58 | −1.58 (−1.72 to −1.48) | 1.58 | n/a | n/a |
| QB | 2,381 | 4.16 | 6.79 | −2.63 (−2.88 to −2.33) | 4.98 | 0.49 | 1.63 |
| RB | 5,448 | 2.95 | 4.25 | −1.30 (−1.45 to −1.15) | 3.24 | 0.60 | 1.44 |
| WR | 7,786 | 2.05 | 3.74 | −1.69 (−1.86 to −1.51) | 3.19 | 0.51 | 1.83 |
| TE | 3,310 | 1.67 | 3.67 | −2.00 (−2.13 to −1.82) | 3.23 | 0.43 | 2.19 |
| K (one league) | 150 | 3.89 | 5.60 | −1.71 | 3.43 | 0.58 | 1.44 |
| Defensive players (one league) | 1,065 | 1.21 | 2.97 | −1.76 | 2.39 | 0.38 | 2.46 |

By week, the bias runs between −1.3 and −2.3 in every week from 1 to 9, with no trend (all nine
in `result.json`).

**Calibration by predicted drop** (all priced player-weeks):

| Predicted drop | n | Mean predicted | Mean realised (95% interval) | Realised 0 | Realised below 0 |
|---|---:|---:|---|---:|---:|
| 0 | 9,940 | 0 | 1.58 (1.48 to 1.71) | 72% | 0% |
| 0 to 2 | 3,011 | 0.94 | 3.57 (3.22 to 3.97) | 43% | 0% |
| 2 to 5 | 3,161 | 3.42 | 5.45 (5.08 to 5.76) | 33% | 0% |
| 5 to 10 | 2,902 | 7.11 | 8.91 (8.63 to 9.21) | 18% | 0% |
| 10 to 20 | 1,087 | 13.03 | 12.96 (12.58 to 13.38) | 7% | 0% |
| above 20 | 39 | 22.38 | 22.71 (19.05 to 25.57) | 0% | 0% |

Large weekly drops are right on average. Small ones are too small, because a player who is
nearly interchangeable with his backup in projection is often clearly better or clearly worse in
hindsight, and the hindsight best lineup always takes the better one.

## 3. Risk 2

| | Value (95% interval) |
|---|---|
| Players predicted 0 who had a real drop that week | 28.0% (27.2% to 28.8%) |
| Their average real drop, all of them | 1.58 (1.48 to 1.71) points |
| Their average real drop, when above 0 | 5.65 (5.34 to 5.99); median 4.2, 90th percentile 12.9 |
| Projected starters: realised ÷ predicted, summed | 1.40 (1.36 to 1.43) |
| Projected starters: average real minus predicted | +1.91 (1.72 to 2.10) points a week |

**Bench depth does not explain it.** Rank correlation between the number of rostered players at
the player's position and the gap (realised minus predicted) is −0.02 (−0.03 to −0.00); for
players predicted 0 it is −0.07. By depth:

| Players at his position | Player-weeks | Predicted 0 but real drop | Starters: realised ÷ predicted | Average gap |
|---|---:|---:|---:|---:|
| 1 | 140 | 14% | 1.09 | +0.95 |
| 2 | 292 | 45% | 1.34 | +2.46 |
| 3 | 1,015 | 36% | 1.46 | +2.57 |
| 4 | 1,601 | 33% | 1.45 | +2.10 |
| 5 | 1,550 | 34% | 1.48 | +2.28 |
| 6 or more | 15,542 | 27% | 1.38 | +1.60 |

Apart from the rare only-player-at-his-position case, the gap is flat. What drives it is that
the best lineup in hindsight is chosen after the scores are known. At team level, the hindsight
best lineup averages 152.4 points a week against 132.6 projected (+19.8, 17.8 to 22.7), and every
team's max PF in the forecast is subject to the same shortfall.

## 4. Over several weeks (what the feature shows)

For each team and start week *w*, each player on the roster at *w*: predicted and realised drops
summed over weeks *w* to 9, using each week's own roster (0 in weeks after he left). A week with
no usable projection counts as predicted 0.

| Window length | Player-windows | Predicted | Realised | Bias | MAE | Rank correlation | Realised ÷ predicted |
|---|---:|---:|---:|---|---|---|---|
| All | 28,682 | 8.70 | 14.15 | −5.45 (−5.88 to −5.08) | 7.22 | 0.79 (0.78 to 0.81) | 1.63 (1.57 to 1.69) |
| 1–2 weeks | 6,423 | 2.72 | 4.21 | −1.49 | 2.96 | 0.67 | 1.55 |
| 3–4 weeks | 6,434 | 6.39 | 9.87 | −3.48 | 5.53 | 0.77 | 1.54 |
| 5–6 weeks | 6,393 | 9.83 | 15.74 | −5.92 (−6.41 to −5.51) | 7.91 | 0.81 | 1.60 |
| 7–9 weeks | 9,432 | 13.58 | 22.74 | −9.17 (−9.94 to −8.48) | 10.82 | 0.85 | 1.68 |

The shortfall adds up week by week (about 1 point per rostered player per week), and the rank
correlation improves with length because weekly luck averages out. Leaving out every window with
an unknown week, as the product would, gives the same picture (5+ weeks: bias −11.7, realised ÷
predicted 1.65, rank correlation 0.85).

**Calibration, windows of five weeks or more:**

| Predicted drop | n | Mean predicted | Mean realised (95% interval) | Realised 0 |
|---|---:|---:|---|---:|
| 0 | 6,603 | 0 | 2.99 (2.72 to 3.37) | 64% |
| 0 to 5 | 2,544 | 2.16 | 11.38 (10.89 to 11.97) | 15% |
| 5 to 10 | 1,624 | 7.27 | 18.17 (16.72 to 19.49) | 5% |
| 10 to 20 | 1,719 | 14.68 | 25.93 (24.73 to 27.08) | 2% |
| 20 to 40 | 1,758 | 28.73 | 41.88 (40.43 to 43.40) | 0.2% |
| 40 to 80 | 1,314 | 54.89 | 67.83 (65.83 to 69.94) | 0% |
| above 80 | 263 | 97.84 | 112.64 (106.75 to 116.70) | 0% |

For anyone predicted above 0 the gap is roughly constant in points (9 to 15 over these windows),
so it is proportionally largest for small figures.

**What this does and does not capture.** It measures the lineup arithmetic over real rosters and
real outcomes. It does not reproduce the product's rest-of-season figure, which fixes the roster
at week *w* and uses projections made at week *w* for weeks up to five or more ahead. The cache
only has each week's final projection. Projections made weeks ahead are worse, so the product's
figure will miss by more than shown here, and a fixed roster ignores later trades, pickups and
injuries.

**Would a correction help?** Fitted on eight leagues and scored on the ninth, nine times, windows
of five weeks or more:

| | MAE | Bias | Listed players: MAE | Listed players: bias |
|---|---:|---:|---:|---:|
| As shown today | 9.64 | −7.85 | 16.12 | −12.14 |
| × 1.28 (fitted 1.27 to 1.29) | 8.82 | −4.45 | 14.30 | −4.30 |
| 1.13 × predicted + 0.97 per week on the roster | 9.27 | +0.12 | 13.34 | −1.79 |

The second form removes the bias, but it adds about a point a week to every player, including
those predicted 0, and its rank correlation drops (0.80 against 0.83). Both are fitted on final
projections. See the recommendation above.

## 5. List quality

Per team and start week, the predicted top five by drop against the realised top five (ties by
player id). As a reference, the same scores for a list that simply ranks players by projected
points.

| | Lists | Top-5 overlap (of 5) | Rank correlation | Predicted #1 in real top 3 |
|---|---:|---|---|---|
| All windows | 990 | 3.41 (3.31 to 3.50) | 0.77 (0.75 to 0.79) | 77% (73% to 81%) |
| Windows of 5+ weeks | 550 | 3.68 (3.57 to 3.79) | 0.82 (0.80 to 0.84) | 85% (80% to 89%) |
| Single week (week 9) | 110 | 2.65 | 0.61 | 55% |
| Reference, by projected points, 5+ weeks | 550 | 3.50 | 0.84 | 78% |

The exact re-solve beats ranking by projected points on the top of the list (paired: +0.18 of
overlap, 0.04 to 0.36; +7 points for the #1, 3 to 12) and ties it on the full-roster correlation.

## 6. The simple rule against the exact re-solve

The rule: a projected starter's projected points minus the best projected bench player who
could replace him; 0 for a bench player. Two readings, as in exploration §10: "same position"
and "slot-eligible" (any bench player who can fill the starter's slot).

| | Same position | Slot-eligible |
|---|---|---|
| Weekly, projected starters: differs from exact by more than 2 | 22% (18% to 26%) | 12% (10% to 14%) |
| Weekly: by more than 5 | 11% | 6% |
| 5+ week windows: by more than 2 | 50% (41% to 58%) | 32% (27% to 38%) |
| 5+ week windows: by more than 5 | 34% | 20% |
| Largest difference, 5+ weeks | 95 points | 84 points |
| Direction | never below exact | never below exact |

Closeness to the realised drop (projected starters; paired difference of MAE, exact minus rule,
negative = exact closer):

| | Exact MAE | Same-position MAE | Slot-eligible MAE | Exact − same position | Exact − slot-eligible |
|---|---:|---:|---:|---|---|
| Weekly | 5.13 | 5.44 | 5.25 | −0.31 (−0.39 to −0.21) | −0.12 (−0.16 to −0.08) |
| 5+ week windows | 14.40 | 13.30 | 13.60 | +1.10 (0.71 to 1.45) | +0.80 (0.46 to 1.09) |

Biases over 5+ weeks: exact −11.3, same position −5.5, slot-eligible −8.1. The rule's longer-window
advantage comes entirely from overstating, which happens to offset the hindsight shortfall; it is
not tracking the lineup better. Keep the exact re-solve, and the rule as the sentence the user reads.

## 7. The threshold

Windows of five weeks or more (the product's normal horizon is five or more weeks):

| Predicted drop at least | Player-windows | Realised 0 | Realised below 0 | Realised below the threshold | Realised below half the prediction |
|---|---:|---:|---:|---:|---:|
| 1 | 8,478 | 3.9% | 0% | 4.8% | 8.9% |
| **5 (shipped)** | 6,678 | **1.6%** | 0% | 5.2% | 6.9% |
| 10 | 5,054 | 0.6% | 0% | 5.7% | 5.4% |
| 20 | 3,336 | 0.1% | 0% | 7.3% | 3.4% |
| Listed (top 8 and at least 5) | 4,397 | **0.6%** (0.4% to 1.0%) | 0% | 2.1% | |

All windows together: listed 7,300, realised 0 for 2.1%, below 5 for 7.8%, never below 0.

The miss grows with the window: the standard deviation of realised minus predicted (players
predicted above 0) is 6 points for one week, 14 for five, 17 for nine. So a "−5" row is the right
direction but its size is uncertain by more than its own value. On the other side, of players
predicted between 0 and 5 over five weeks or more, 66% really dropped 5 or more, and of those
predicted 0, 20% did. The threshold costs missed real drops, not false ones.

## 8. Limitations

- **9 leagues, one season, weeks 1–9.** Mostly superflex, full-PPR leagues; kickers and defensive
  players come from one league each. Intervals resample leagues, so they cover league-to-league
  differences within this set, not other formats.
- **Final-week projections.** The cache holds each week's last projection, which may include
  post-game information (the calibration check found their update stamps after the games). That
  makes predictions look *better* than live ones. Players the final projection dropped (out,
  inactive) are "unknown" here; a live projection made days or weeks earlier would usually have
  priced them.
- **No horizon effect.** The product projects five or more weeks ahead from a fixed roster; this
  backtest uses each week's own projection and roster. It cannot measure how much worse the
  far-ahead figure is.
- **Taxi and reserve status in past weeks are unknown.** Sleeper's matchup `players` list
  includes taxi and injured-reserve players (up to 32 per roster here). All were treated as
  eligible for max PF on both sides. The product excludes reserve players from max PF. Effect:
  reserve players almost never have a usable projection and almost never score (of the 6,968
  unknown player-weeks, 96% scored 0 and 0.6% had a realised drop), so they barely move either
  side; they are left out of the weekly figures with the other unknowns.
- **No free-agent fills.** 529 predicted removals (2.6% of priced player-weeks) left a slot no one
  on the roster could fill; the product would fill it with a free agent, showing a smaller drop.
  Sleeper's real max PF does not use free agents either, so the realised side is right.
- **Byes inferred, not read** from a schedule (a team with no projected player that week). The
  provider's "team changed" rule is not applied.
- **Sleeper's own weekly max PF is not in the cache**, so the hindsight solver is checked by an
  independent exact method and against recorded scores, not against Sleeper's figure.
- **No pick-odds validation at all.** Whether a listed move changes the draft pick, and by how
  much, needs the final 2026 draft order. The paired re-simulation is not run here.

## 9. Still to validate

1. Re-run this on the frozen pregame snapshots the weekly forecast now saves (90-day retention,
   D-240): this measures the horizon effect and removes the post-game-information doubt. If the
   bias still holds there, reconsider the correction factor (or the tier 3 hindsight model).
2. After the 2026 draft order is set: score the saved pick odds and listed moves against it.
3. Real trades: for trades the app captured, the selling team's max PF afterwards against the
   predicted drop (exploration §11).

## Reproduce

```
python3.12 docs/plans/league-projections/max-pf-trade-away/backtest/backtest.py /path/to/cache
```

The cache is the calibration check's (raw Sleeper responses, kept outside the repo). The script
disables network sockets before reading anything, finds the league ids from the cached matchup
files, and writes `result.json` next to itself. About a minute of solving with 4 workers and a few
minutes of bootstrap (1,000 draws). `--rows PATH` writes a per-row dump with ids for checking; it
refuses a path inside the repo. Unit tests: `backend/tests/test_maxpf_backtest.py`.
