# Is the forecast's score spread too small? (score-spread study)

Date: 2026-11-13. Research only: no product code or configuration changed.
Operator's question: "projections are still too over confident" — measure how much players and
starting lineups vary around their projections, and what that means for the confidence of the
playoff odds in the operator's three leagues. Every number below is reproduced by one command
(bottom of this page) and stored in [`result.json`](result.json) (aggregates only).

## Answer

**For a single week, the spread is right. 25 is what the data supports.** Across 24,002
head-to-head games in 331 league-seasons (2024, 2025 and 2026 weeks 1–9), the single-game spread
that best explains who actually won is **24.8 points (95% interval 24.0–25.5)**. When the model
says a favourite wins 90–100% of the time it wins 94.3% (model average 95.0%); every other band is
within a point. A new flat value would be 25 again.

**The spread does depend on lineup size and position mix, but fixing that barely moves the odds.**
Leagues with 8–9 starters fit about 22, 10 starters 24.6, 11–12 starters 28, 13+ about 30. A
per-team spread built from each lineup's positions fits measurably better than one flat number
(cross-validated, interval excludes zero), but the gain is tiny, and it moves the operator's
three leagues by at most 1.8 points.

**Where the forecast is overconfident is over the five weeks ahead, not in a single week.** The
model treats a team's remaining weeks as independent. When the projection is made weeks before the
games (as the live forecast's is), a team's misses repeat: a team the projections overrate this
week tends to stay overrated (an injury, a role change, a lost job). Measured with a stand-in for
forward projections, that persistent part is worth about **10 points per week per team (9.6–10.4)**,
and it makes a team's five-week point total about **58% more variable** than the model assumes
(variance ratio 1.58, interval 1.54–1.62).

**What that does to the operator's leagues: up to 4 points, and nobody's "certain" teams fall.**
Adding the persistent part (keeping one week at 25) lowers the top teams by up to 3.6 points and
raises the long shots by similar amounts. The number of teams at 95% or more drops by
one in League B and League C; League C's one team at 99.9% or more drops to 99.8%. **The two 8–1
teams in League B stay at 100.0% under every assumption the data supports**, and at 99.9% or more
even under deliberately extreme stress tests (weekly spread 35, or twice the measured persistence).
Their odds come from their records with five weeks left, not from the spread.

**Recommendation:** keep `score_sd` at 25; do not move to a per-league or per-team spread now. The
change the data supports is restoring a **persistent team draw of about 10 points** for the
remaining weeks, with the weekly draw lowered to about 23 so one week still totals 25. That is a
**code change**, not configuration (details at the end). Confirm the size with the saved Tuesday
snapshots before shipping it (see "What this still cannot see").

## Terms

- **Residual** = actual points − projected points. Negative = scored less than projected.
- **Bias** = the average residual. **SD** = the standard deviation of the residual about that
  average (how far a typical week lands from the projection, once the average miss is removed).
- **Projected best lineup** = the product's forecast mean: provider weekly projections scored with
  the league's own scoring, best legal lineup from the roster (`core.optimize`).
- **Fitted game SD** = the single per-team spread that makes the model's pregame win chances
  (`Φ(gap / (SD·√2))`) best match who actually won (maximum likelihood).
- **95% interval** = re-drawing whole league-seasons at random 200 times and re-computing.
- **Persistent part** = the share of a team's error that repeats across its remaining weeks.

## Data

| | |
|---|---|
| League-seasons | 356 with at least one scored week (2024: 117, 2025: 118, 2026: 121): the research store's 352 dynasty league-seasons plus the earlier study's cached leagues not in it |
| Lineup level | 331 league-seasons whose lineups the product supports (25 with team-defense slots are player-level only, because the product does not support a DEF slot) |
| Weeks | 2024 and 2025: each league's regular season (weeks 1–14 by default). 2026: **weeks 1–9 only** — week 10 is in progress today, so "the first 11 weeks" cannot be measured yet |
| Player-weeks started | 521,584 (14,286 had no usable projection and are left out of player tables) |
| Team-weeks | 48,012; head-to-head games 24,002 |
| Projections | Sleeper's stored weekly projections for every week, scored through the product's own path (`scoring.best_available` via the universal-SD backtest's `projected_points`) |
| Operator's leagues | In the sample for 2025 and 2026 (414 games). League A has 9 starters, League B 15 (with defensive players), League C 10 (with the weekly median game) |

## 1. Players

**Spread by position, started players** (bias / SD, points per week):

| Position | 2025 (n) | 2025 bias / SD | 2026 wk 1–9 (n) | 2026 bias / SD | Bias share of the miss | Persistent per-player share |
|---|---:|---|---:|---|---:|---:|
| QB | 30,993 | −0.8 / 9.2 | 21,309 | 0.0 / 9.2 | 0.0% | 0.4% |
| RB | 52,730 | −0.7 / 7.7 | 34,634 | −0.8 / 7.8 | 0.0% | 0% |
| WR | 70,044 | −0.9 / 7.6 | 45,649 | −0.4 / 8.0 | 0.3% | 0% |
| TE | 28,340 | −0.2 / 7.2 | 20,246 | −0.5 / 7.7 | 0.0% | 0% |
| K | 1,662 | −0.4 / 4.7 | 1,028 | +0.9 / 4.9 | 0.3% | 4% |
| DEF (team defense) | 1,143 | +2.1 / 7.2 | 726 | +1.2 / 6.6 | 8.2% | 16% |
| DL | 997 | +0.8 / 6.2 | 329 | +0.5 / 4.3 | 0.5% | 4% |
| LB | 2,927 | +0.3 / 5.8 | 960 | +1.8 / 5.0 | 1.0% | 11% |
| DB | 2,862 | −0.3 / 5.1 | 679 | +0.5 / 4.7 | 0.0% | 3% |

"Bias share" = bias² ÷ mean squared miss, all seasons pooled. "Persistent per-player share" = how
much of the spread is a player being consistently over- or under-projected all season (a
random-effects split of each player's weeks within a league-season); the rest is week-to-week noise.

**So: a player's miss is almost all noise around the projection, not the projection being wrong on
average.** For QB, RB, WR and TE the average miss is under 1 point a week and contributes under 1%
of the miss; no measurable part is a player-specific bias that lasts the season. Team defenses
are the exception (projected about 2 points low, partly because the product's linear scoring path
cannot price the points-allowed bands), and linebackers have some persistent player bias (11%).
Players projected to start (the product's lineup) look the same: QB 9.1, RB 7.7, WR 7.9, TE 7.6.

**Spread by projected points, started players, all seasons** (bias / SD (n)):

| Position | <5 | 5–10 | 10–15 | 15–20 | 20–25 | 25+ |
|---|---|---|---|---|---|---|
| QB | +0.8 / 5.9 (49) | – | +0.4 / 7.4 (6,308) | +0.2 / 8.5 (35,714) | −0.4 / 9.4 (30,839) | −1.0 / 10.8 (9,933) |
| RB | +0.5 / 4.5 (6,419) | +0.1 / 6.1 (21,161) | +0.4 / 7.4 (52,417) | −0.5 / 7.9 (43,149) | −0.9 / 10.0 (12,240) | −3.8 / 11.3 (3,020) |
| WR | +0.5 / 4.8 (5,756) | +0.1 / 6.4 (38,058) | −0.4 / 7.6 (94,192) | −0.7 / 9.2 (41,339) | −2.2 / 10.2 (7,364) | −4.3 / 10.5 (660) |
| TE | +0.4 / 4.2 (3,118) | +0.7 / 6.7 (21,108) | −0.2 / 7.7 (37,469) | −0.7 / 8.9 (10,201) | −1.1 / 8.1 (1,879) | −2.0 / 6.2 (185) |
| K | – | +0.3 / 4.8 (4,444) | +0.7 / 5.6 (153) | – | – | – |
| DL | +0.5 / 3.9 (783) | +0.3 / 5.3 (1,593) | +0.7 / 10.4 (233) | – | – | – |
| LB | +1.2 / 3.7 (849) | +0.6 / 4.8 (3,228) | +0.7 / 6.3 (2,965) | −0.8 / 7.8 (693) | – | – |
| DB | +0.4 / 2.8 (1,300) | +0.6 / 5.1 (2,609) | −0.5 / 5.9 (2,023) | – | – | – |

The spread grows with the projection (a 25-point running back varies about 11, a 5-point one about
4), and the highest projections run a few points high. Defensive players vary less than offensive
ones, which is why a 15-slot league with six defensive starters is not much wider than a 9-slot one.

## 2. Lineups

| Lineup | Team-weeks | Avg projected | Actual − projected best lineup | Actual − starters as set | Independent players would give | Observed (player bias removed) | Implied teammate correlation |
|---|---:|---:|---|---|---:|---:|---:|
| All | 48,012 | 143 | −6.6 / 27.5 | −1.9 / 26.4 | 25.0 | 26.4 | +0.02 |
| 2024 | 17,358 | 138 | −0.4 / 27.5 | +4.2 / 26.1 | 24.6 | 26.2 | +0.03 |
| 2025 | 18,396 | 146 | −11.2 / 26.9 | −6.4 / 25.8 | 25.3 | 25.7 | +0.01 |
| 2026 wk 1–9 | 12,258 | 145 | −8.2 / 26.7 | −3.7 / 26.0 | 25.3 | 26.1 | +0.02 |
| 8–9 starters | 15,724 | 123 | −6.7 / 25.7 | −1.1 / 24.1 | 23.3 | 24.3 | +0.02 |
| 10 starters | 19,176 | 142 | −6.1 / 27.1 | −2.2 / 26.3 | 25.0 | 26.3 | +0.02 |
| 11–12 starters | 9,992 | 163 | −8.6 / 29.5 | −4.7 / 28.7 | 26.8 | 28.5 | +0.02 |
| 13+ starters | 3,120 | 184 | −2.4 / 30.6 | +5.3 / 28.5 | 27.6 | 28.9 | +0.01 |
| Leagues with defensive players | 2,732 | 180 | −3.0 / 29.1 | +4.8 / 26.9 | 26.9 | 27.1 | +0.01 |

Cells are bias / SD. "Projected best lineup" is what the model uses; "starters as set" scores the
lineup the manager actually started (an unpriced starter counts 0; 17% of team-weeks had one).
"Independent players" = √(sum of each lineup player's variance from the position × projection
table above).

- **The flat 25 is about right for the typical league, too small for big lineups and a little
  large for small ones.** Lineup spread rises from about 24 (8–9 starters) to 29–31 (13+). Per
  league-season the SD of the model's residual ranges from 23.0 (10th percentile) to 29.5 (90th),
  median 26.2.
- **Teammates' errors barely move together** (average correlation +0.02): a lineup's spread is
  almost exactly what independent players would give.
- **The average miss is negative** (−6.6): the best projected lineup is picked *because* its
  players have the highest projections, so it is the set most likely to be over-projected, and
  managers' real lineups score 3.8 less than that lineup's players did. A bias shared by every team
  in a league does not change who wins; it does lower simulated points-for.
- **Opponents.** Inside a league-week the two teams in a game are slightly negatively related
  (correlation −0.10, the model assumes 0), plausibly because real NFL production is split across
  rosters (one team's quarterback against another's defense, two backs from one backfield). Raw,
  before removing the league-week average, they are +0.10 (a weekly shock shared by everyone). The
  SD of the difference between the two teams' misses is 36.7, i.e. 26.0 per team.

## 3. Is 25 right, and should it be one number?

**Fitted single-game spread** (the spread that best explains realised head-to-head results):

| Games from | Games | League-seasons | Fitted SD (95% interval) | Log loss at 25 | at fitted | Margin ÷ projected gap |
|---|---:|---:|---|---:|---:|---:|
| All | 24,002 | 331 | **24.8 (24.0–25.5)** | 0.5414 | 0.5414 | 1.02 |
| 2024 | 8,677 | 105 | 24.1 (22.4–25.6) | 0.5639 | 0.5637 | 1.10 |
| 2025 | 9,198 | 111 | 25.1 (23.9–26.3) | 0.5404 | 0.5404 | 0.99 |
| 2026 wk 1–9 | 6,127 | 115 | 25.3 (23.9–26.4) | 0.5111 | 0.5111 | 1.01 |
| 8–9 starters | 7,858 | 107 | 21.9 (20.7–23.0) | 0.5441 | 0.5424 | 1.09 |
| 10 starters | 9,588 | 135 | 24.6 (23.5–25.5) | 0.5324 | 0.5324 | 1.02 |
| 11–12 starters | 4,996 | 69 | 27.9 (26.1–29.6) | 0.5492 | 0.5478 | 0.96 |
| 13+ starters | 1,560 | 20 | 29.8 (26.9–33.1) | 0.5583 | 0.5546 | 1.02 |
| The operator's 6 league-seasons | 414 | 6 | 23.1 (19.0–27.5) | 0.5451 | 0.5444 | 1.07 |

"Margin ÷ projected gap" is the slope of the real winning margin on the projected gap: 1 means the
projections' gaps between teams are the right size (not exaggerated). The fitted spread (24.8)
sits a little below the raw per-team spread (26.0) because leagues differ: pooled together, the
narrow small-lineup leagues and the wide big-lineup ones fit a single game best slightly below their
average spread.

**Reliability at SD 25** (when the model said the favourite would win with this chance, how often
it did; best flat value rounds to 25, so the table at the fitted value is identical):

| Model says | Games (all) | Model average | Favourite won (95% interval) | 2026 games | 2026 favourite won |
|---|---:|---:|---|---:|---|
| 50–60% | 6,298 | 54.9% | 55.2% (54.0–56.5) | 1,305 | 54.1% (51.4–56.8) |
| 60–70% | 5,812 | 64.9% | 65.2% (64.0–66.4) | 1,327 | 65.8% (63.2–68.3) |
| 70–80% | 4,826 | 74.9% | 75.1% (73.8–76.3) | 1,183 | 74.9% (72.3–77.3) |
| 80–90% | 3,903 | 84.8% | 85.9% (84.7–86.9) | 1,179 | 85.4% (83.3–87.3) |
| 90–100% | 3,163 | 95.0% | 94.3% (93.5–95.1) | 1,133 | 94.2% (92.7–95.4) |

The top band is 0.7 points short, at the edge of its interval; everything else matches. (The
earlier check's soft spot, 87% in that band from 61 games, does not survive a sample 50 times
larger.)

**Flat versus a spread that varies** (cross-validated: fitted on nine-tenths of the leagues,
scored on the rest; lower log loss is better):

| Spread model | Fitted | Log loss | vs flat (95% interval) |
|---|---|---:|---|
| Flat (product today) | 24.8 | 0.54144 | |
| Scales with √(starting slots) | 24.6 at 10 slots | 0.54045 | −0.0010 (−0.0015 to −0.0005) |
| Scales with √(projected total) | 22.9 at 120 points | 0.53978 | −0.0017 (−0.0023 to −0.0010) |
| **Per team, from lineup positions** (multiplier on the independent-player spread) | 0.99 | **0.53973** | **−0.0017 (−0.0023 to −0.0011)** |
| Per league, from its typical lineup | 0.98 | 0.53996 | −0.0015 (−0.0021 to −0.0009) |

Every varying model beats flat with an interval clear of zero, and the per-team one fits best
(multiplier 0.99: the lineup's own independent-player spread, unchanged). But the gain is about
0.3% of log loss, and its reliability table is no better calibrated than flat 25's (90–100% band:
94.8% vs 95.1% predicted). It is a real but small refinement. As a check on the per-league version
for the operator's own leagues, its predicted spread against each league's realised lineup spread:
League A 23.2 predicted vs 23.9 (2025) and 24.6 (2026) realised; League B 23.0 / 22.5 vs 20.8 / 21.4;
League C 24.5 / 24.4 vs 26.1 / 26.2.

## 4. The operator's three leagues

Today's captures (week 10 in progress, weeks 10–14 left, 6 playoff spots of 12), 250,000 simulated
seasons per run. Teams are ordered by their odds today; records are wins-losses (League C counts the
median game too). Columns:

- **25**: the shipped model (`simulation.simulate`, unchanged). The best flat value from the data
  rounds to 25.0, so it is the same run.
- **Per league**: the product with one `score_sd` per league from its lineups' positions
  (League A 23.0, B 22.5, C 24.5).
- **Per team**: each team-week's own spread from its projected lineup (League A 16.8–27.3, median
  23.3; B 19.3–25.4; C 19.5–27.2), only the not-yet-played starters counting in week 10. The product
  takes one spread per run, so this uses the study's own simulator.
- **+ persistent**: weekly spread 22.9 rising to 25.6 by week 14, plus one persistent draw per team
  of 10.1 (point estimate) shared by all its remaining weeks, so a single week still totals 25. The
  "upper" column uses the top of the interval (10.5). Study simulator.
- **Stress** (not supported by the data, shown to bound the answer): weekly spread 35; or a
  persistent draw of 20, twice the measured value. Study simulator.

The study simulator reproduces the product at 25: largest difference 0.34 points over all 36 teams,
largest |z| 2.84 across 36 comparisons (what Monte Carlo noise alone produces).

**League A (9 starters)** — playoff odds, %

| Team | Record | 25 | Per league | Per team | + persistent | + persistent (upper) | Stress SD 35 | Stress persistent 20 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Team 1 | 7-2 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| Team 2 | 9-0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| Team 3 | 8-1 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 99.9 |
| Team 4 | 5-4 | 87.4 | 87.8 | 87.3 | 84.1 | 83.8 | 85.5 | 78.5 |
| Team 5 | 5-4 | 75.8 | 76.5 | 77.3 | 72.9 | 72.7 | 73.8 | 67.8 |
| Team 6 | 4-5 | 43.8 | 42.8 | 42.0 | 44.7 | 44.8 | 46.3 | 46.4 |
| Team 7 | 3-6 | 41.8 | 42.1 | 41.9 | 42.7 | 42.7 | 39.3 | 42.1 |
| Team 8 | 4-5 | 36.9 | 37.5 | 38.3 | 37.9 | 37.9 | 35.9 | 39.3 |
| Team 9 | 4-5 | 14.1 | 13.2 | 13.0 | 17.0 | 17.3 | 18.5 | 23.3 |
| Team 10 | 2-7 | 0.2 | 0.2 | 0.2 | 0.7 | 0.7 | 0.6 | 2.4 |
| Team 11 | 2-7 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.1 | 0.3 |
| Team 12 | 1-8 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

**League B (15 starters, with defensive players)** — playoff odds, %

| Team | Record | 25 | Per league | Per team | + persistent | + persistent (upper) | Stress SD 35 | Stress persistent 20 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Team 1 | 8-1 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| Team 2 | 8-1 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 99.9 |
| Team 3 | 6-3 | 99.8 | 99.9 | 99.8 | 99.4 | 99.4 | 99.3 | 97.6 |
| Team 4 | 5-4 | 96.2 | 96.9 | 96.6 | 93.9 | 93.7 | 93.0 | 88.1 |
| Team 5 | 5-4 | 66.1 | 66.3 | 66.1 | 64.0 | 63.8 | 65.5 | 60.8 |
| Team 6 | 4-5 | 64.5 | 65.9 | 66.0 | 62.7 | 62.6 | 58.9 | 57.8 |
| Team 7 | 4-5 | 53.1 | 54.1 | 54.3 | 52.0 | 52.1 | 49.6 | 50.4 |
| Team 8 | 4-5 | 13.3 | 11.8 | 11.9 | 16.9 | 17.2 | 17.7 | 23.2 |
| Team 9 | 5-4 | 6.1 | 4.3 | 4.5 | 8.9 | 9.0 | 14.1 | 16.4 |
| Team 10 | 2-7 | 0.7 | 0.6 | 0.6 | 1.5 | 1.6 | 1.2 | 3.5 |
| Team 11 | 2-7 | 0.3 | 0.2 | 0.2 | 0.7 | 0.7 | 0.6 | 2.3 |
| Team 12 | 1-8 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.2 |

**League C (10 starters, weekly median game)** — playoff odds, %

| Team | Record | 25 | Per league | Per team | + persistent | + persistent (upper) | Stress SD 35 | Stress persistent 20 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Team 1 | 15-3 | 100.0 | 100.0 | 100.0 | 99.8 | 99.8 | 99.9 | 99.1 |
| Team 2 | 13-5 | 99.9 | 99.9 | 99.8 | 99.5 | 99.5 | 99.5 | 97.4 |
| Team 3 | 14-4 | 99.6 | 99.6 | 99.6 | 98.9 | 98.8 | 99.2 | 96.5 |
| Team 4 | 12-6 | 96.4 | 96.5 | 96.2 | 93.5 | 93.3 | 93.6 | 87.7 |
| Team 5 | 12-6 | 94.0 | 94.2 | 94.3 | 91.1 | 90.9 | 91.4 | 85.3 |
| Team 6 | 12-6 | 60.3 | 60.1 | 60.1 | 59.8 | 59.7 | 63.7 | 60.1 |
| Team 7 | 10-8 | 45.3 | 45.3 | 45.5 | 48.2 | 48.4 | 45.6 | 51.6 |
| Team 8 | 8-10 | 3.5 | 3.4 | 3.5 | 6.7 | 7.0 | 5.3 | 14.5 |
| Team 9 | 7-11 | 0.9 | 0.9 | 0.9 | 2.5 | 2.7 | 1.8 | 7.8 |
| Team 10 | 2-16 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Team 11 | 1-17 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Team 12 | 2-16 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

**Counts** (teams at ≥95% / ≥99.9%, largest change from the shipped run in points):

| Scenario | League A | League B | League C |
|---|---|---|---|
| Shipped 25 (= best flat) | 3 / 3 | 4 / 2 | 4 / 1 |
| Per league | 3 / 3, 1.0 | 4 / 2, 1.8 | 4 / 1, 0.2 |
| Per team | 3 / 3, 1.8 | 4 / 2, 1.6 | 4 / 1, 0.3 |
| + persistent (point) | 3 / 3, 3.3 | **3** / 2, 3.6 | **3 / 0**, 3.2 |
| + persistent (upper) | 3 / 3, 3.5 | 3 / 2, 3.9 | 3 / 0, 3.4 |
| Stress SD 35 (unsupported) | 3 / 3, 4.4 | 3 / 2, 8.0 | 3 / 1, 3.4 |
| Stress persistent 20 (unsupported) | 3 / 2, 9.1 | 3 / 2, 10.3 | 3 / 0, 11.0 |

**What changes in practice.** A per-league or per-team spread changes nothing a user would notice
(under 2 points, same counts). The persistent draw is the only supported change that moves
anything: one team per league drops below 95% in B and C (96.2 → 93.9, 96.4 → 93.5), League C's
leader drops from 99.97% to 99.8%, and long shots gain 1 to 4 points. The teams at 100% in Leagues A
and B are 7–2 to 9–0 with five weeks left; they stay at 100.0% (rounded) under every supported
assumption and at 99.9% or more even under both stress tests.

## 5. What this still cannot see

1. **The live forecast's own projections.** The cache holds each week's *final* stored projection
   (stamped after the games; it may include late information). The model's score SD is calibrated
   against those, so a Tuesday projection for the same week is probably a little less accurate: the
   one-week-old stand-in below puts this at 25 → 26–27 for the current week. Direction: the true
   spread is larger than measured, by up to about 2 points.
2. **Forward projections.** The product projects up to five weeks ahead. The cache has no projection
   made weeks in advance, so this study uses a **stand-in**: the projection a player had h weeks
   before the game (rosters as they actually were in the game week, byes known). Two versions bracket
   how a player who was out at the time is treated (kept out, or counted at his last healthy
   projection); they agree. On the same 28,432 team-weeks (weeks 6 and later):

   | Weeks ahead | 0 | 1 | 2 | 3 | 4 | 5 |
   |---|---:|---:|---:|---:|---:|---:|
   | SD of the miss, relative to the league-week | 25.0 | 26.0 | 26.6 | 26.8 | 27.1 | 27.4 |
   | Fitted game SD (kept-out version) | 24.9 | 27.2 | 28.5 | 28.9 | 29.2 | 30.3 |
   | Fitted game SD (last-healthy version) | 24.9 | 25.7 | 26.6 | 27.1 | 27.2 | 28.2 |

   And from one forecast point, a team's misses over the next five weeks (32,348 windows):

   | | Average covariance between two of the five weeks (points²) | Persistent SD | Five-week total variance ÷ independent | By season (cov / ratio) |
   |---|---:|---:|---:|---|
   | Projections made at the forecast point | **99 (92–107)** | **9.9 (9.6–10.4)** | **1.58 (1.54–1.62)** | 2024 105 / 1.62, 2025 97 / 1.56, 2026 92 / 1.52 |
   | Control: each week's own final projection | 28 (21–35) | 5.3 (4.6–5.9) | 1.18 (1.14–1.23) | 2024 44 / 1.29, 2025 25 / 1.16, 2026 3 / 1.02 |

   The control reproduces the earlier calibration check for 2026 (no persistence with each week's
   own projection); the persistence appears when the projection is made ahead of time, every season.
   **Limits of the stand-in.** It ignores matchups (makes each future week noisier than a real
   forward projection, which inflates the per-week SDs but not the persistence) and it knows the
   game-week roster (the live forecast uses today's roster, so pickups and trades add error it does
   not see). The persistent SD is therefore an estimate of the right size, not a measurement.
3. **How to measure it properly.** The weekly batch saves each Tuesday's forecast (`snapshot_json`,
   kept 7 days, baseline runs 90): export them weekly, then for each saved week N score every team's
   projected weeks N+1..N+5 against the recorded scores. That gives the per-week spread and the
   persistent part directly, from the product's own forward projections. The three captures used
   here are kept in the scratch folder for the same purpose: after week 14, score them against what
   happened and check how often teams given 90–95% and 95%+ made the playoffs.
4. **Other limits.** Player positions come from today's player map (a few players changed
   position). Team defenses cannot be fully priced by the product's linear scoring path. 17% of
   team-weeks started at least one player with no usable projection (scored 0 projected). Unusual
   scoring rules (21 of 352 store leagues) are scored by the same path, which leaves out bonus
   rules it cannot price. The variance table used for the per-team spread was fitted on the same
   data it is used on (hundreds of thousands of player-weeks; negligible leakage). The operator's
   leagues are in the sample (6 of 331 league-seasons).

## Recommendation

**Keep 25.** It is the value the outcomes support (24.8, 24.0–25.5), it is calibrated in every
probability band, and a new flat value would round to the same number.

**Do not switch to a per-league or per-team spread now.** It is statistically better (lineups really
do range from about 22 to 30), but it changes the operator's odds by under 2 points. If it is wanted
later (for unusually small or large lineups), the per-team version needs code: a position ×
projected-points variance table, a per-team-week SD in `simulation.simulate` (today one
`score_sd` is applied to every team), and the same table at capture time.

**The change the data supports is a persistent team draw for the weeks ahead**, about 10 points,
with the weekly draw lowered to about 23 (√(23² + 10²) ≈ 25, so a single week is unchanged). Effect
on the operator's leagues: top teams down by up to 3.6 points, one fewer team at ≥95% in two of
the three leagues; the 8–1 teams unchanged. This is **code**, not configuration: model v4's
`persistent_sd` (one draw per team per simulated season, added to every future week) was removed by
D-229 and `simulation.config` now rejects the key. Adopting it means restoring that draw (a
random-walk version that grows with weeks ahead would match the stand-in slightly better), bumping
`core.VERSION`, setting `score_sd` 23 and `persistent_sd` 10 in `config/league_projections.json`,
updating the `sd_status` / warning text, and re-checking the published spread against results.
Before that, confirm the persistent SD from the saved Tuesday snapshots (section 5, item 3); this
study's 10 comes from a stand-in for forward projections.

**On the operator's example:** two 8–1 teams at 100% with five weeks left is not a symptom of too
small a spread. It holds under every spread the data supports and under deliberately extreme ones.

## Reproduce

```sh
python3.12 docs/plans/league-projections/score-spread-study/study.py \
    /path/outside/repo/scratch /path/to/data/sleeper-universe/crawl-pilot/universe.sqlite --workers 10
```

About 3 minutes on 10 cores after the first extraction (about 1 minute). Standard library and the
repo's own modules only. The scratch folder holds `cache/` (raw Sleeper responses),
`league_ids.txt`, `operator_leagues.txt` and `snapshots/league1..3.json`; intermediate files with ids
go to `<scratch>/study/`. The store is opened read-only; sockets cannot connect. Seeds are fixed.
Pure pieces: [`spread_stats.py`](spread_stats.py), tested by
`backend/tests/test_score_spread_stats.py`.
