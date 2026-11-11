# Universal weekly score SD (model `projected-lineup-universal-sd-v5`)

Date: 2026-11-11. This is the record the model version points at.

| Item | Value |
|---|---|
| Selected value | **25.0** |
| Units | Fantasy points per team per week, in each league's own scoring |
| Distribution | Normal, centred on the team's projected best-lineup total |
| Scope | Every team, every unplayed week; independent by team and week. Completed weeks carry no noise |
| Also used for | The latent Max PF draw (same value; the realized Max PF spread differs because Max PF is floored at the score) |
| Where it lives | `config/league_projections.json` → `model.score_sd`. No code default; a scenario request may not change it |
| Status | **Provisional. Not calibrated.** |

## How it was chosen

`backtest.py` (this folder) compared the projected best lineup of each week's roster with the
score the team recorded, for weeks 1–9 of 2026 across 9 Sleeper leagues with supported lineups
(990 team-weeks; 6 other known leagues were another season or an unsupported lineup). Errors were
pooled across teams and leagues. Output: `backtest-result.json` (aggregates only).

- Selection weeks 1–6 (660 team-weeks): root-mean-square error about the projection **24.5**;
  mean error −3.0 (teams score slightly under their projected best lineup).
- Holdout weeks 7–9 (330 team-weeks, not used for selection): RMSE 26.0, mean error −9.1.
- Nearby values on the holdout:

| SD | 50% interval covers | 80% covers | 90% covers | Head-to-head log loss |
|---:|---:|---:|---:|---:|
| 20 | 42% | 69% | 79% | 0.4968 |
| 22.5 | 47% | 76% | 84% | 0.4942 |
| 24.5 | 52% | 78% | 87% | 0.4947 |
| **25** | 52% | 79% | 88% | 0.4951 |
| 27.5 | 55% | 82% | 92% | 0.4981 |
| 30 | 58% | 85% | 94% | 0.5023 |

The selection rule gives 24.5. On the later weeks 25 covers the 80% and 90% intervals slightly
better at the same log loss, so 25.0 is configured. By lineup size the pooled error is 23.4
(9 starters, 216 team-weeks), 26.0 (10 starters, 666) and 21.4 (15 starters with IDP, 108):
one value is a compromise across formats, as the spec requires.

## Why it is not called calibrated

1. **The projection rows are not proven pregame snapshots.** Sleeper serves stored rows for past
   weeks, and their last-update stamps fall on the Tuesday after the games. Favourites also won
   more often than a pregame forecast usually manages. The rows may carry late or post-game
   information, which would make this error too small.
2. **Horizon.** The backtest measures the final projection for a week. The weekly batch projects
   up to five weeks ahead from one Tuesday snapshot, where error is larger.
3. **True pregame evidence is tiny.** The only frozen snapshots are the app's own saved runs:
   36 team-weeks (week 9, 3 leagues, saved the Saturday before), RMSE 20.9, with a Thursday
   player already final in 30 of them.
4. **Three lineup formats**, one season, nine weeks.

## Sensitivity (`sensitivity-result.json`)

The three leagues with saved snapshots, re-run under v5 at 40,000 seasons each:

| Comparison | Mean change in playoff chance | Largest change | Teams (of 36) changing outlook band |
|---|---:|---:|---:|
| SD 20 vs 25 | 1.0 pt | 4.1 pts | 2 |
| SD 30 vs 25 | 0.9 pt | 4.1 pts | 1 |
| SD 20 vs 30 | 1.9 pts | 7.4 pts | 3 |
| Saved v4 result vs v5 at 25 | 1.7 pts | 11.1 pts | 2 |

Playoff chances after week 9 are not sensitive to the SD inside 20–30.

## To calibrate properly

The weekly batch now freezes real pregame projections every Tuesday (`snapshot_json`). Compare
each saved week-N projection with the recorded week-N score once retention allows (runs are kept
7 days; the last success per league is kept longer), by weeks-ahead, and re-run this selection on
those pairs. Change `model.score_sd` and bump `core.VERSION` together.
