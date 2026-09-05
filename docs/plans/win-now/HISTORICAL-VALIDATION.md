# Historical Sleeper validation

Date: 2026-09-04 (America/New_York; capture timestamps use UTC).

## What the data can establish

Sleeper's historical weekly matchups and winners bracket supply observed team scores, weekly roster lists, playoff qualification, and the champion. This is the outcome half of a calibration dataset. The offline capture and evaluation tools keep it separate from forecast inputs and do not change product flags or model parameters.

The [official matchup documentation](https://docs.sleeper.com/#getting-matchups-in-a-league) describes weekly `players`, ordered `starters`, scores, and commissioner score overrides. These are useful historical roster lists; they are not timestamped pregame roster eligibility or injury snapshots. The [bracket documentation](https://docs.sleeper.com/#getting-the-playoff-bracket) identifies bracket participants and winners. A championship label comes from the first-place match, not the last array row. Median matches affect regular-season records only; exact-median scores tie. See [Sleeper's median rules](https://support.sleeper.com/en/articles/3971690-extra-game-each-week-against-league-median).

## Projection source audit

The live [audit artifact](historical-source-probe-2026-09-04.json) records six public projection endpoint responses, their SHA-256 hashes, retrieval timestamps, counts, and limited player/date examples. Every returned stat row with a game date and revision timestamp had a revision timestamp later than its game date:

| Season / week | Stat rows | Revision date after game date |
|---|---:|---:|
| 2022 / 1 | 387 | 387 |
| 2024 / 1 | 351 | 351 |
| 2025 / 1 | 356 | 356 |
| 2025 / 6 | 321 | 321 |
| 2025 / 12 | 324 | 324 |
| 2025 / 17 | 363 | 363 |

For example, the 2025 Week 1 Lamar Jackson row has a September 7 game date and an October 6 source update. The nested player information also contains current metadata. The timestamps do not tell us exactly which numeric fields changed, but they cannot establish that the returned complete payload existed before the games. We do not backdate a retrieval to `updated_at`, treat today's historical URL as an immutable archive, or infer pregame availability from today's injury status.

There is a second timing constraint for season odds: at a Week 4 forecast origin, we need the forecasts for **all remaining weeks as they existed at Week 4**. Combining each later week's final projection leaks later injury, role, and depth-chart information even if each projection preceded its own game.

## Cohort and model coverage

The initial cohort follows the two league histories already used in the repository's research: Lakeview 2024–2025 and FFv3 2022–2025. Six league-seasons mean six championship events from only two recurring league groups; team rows and repeated forecast weeks do not create independent champions. This is a convenience sample, not representative evidence for all Sleeper leagues.

Outcome coverage and current Win Now model coverage are distinct. FFv3 starts kickers and IDP players, which the current player model does not support. Lakeview's active slots are offensive, but its saved scoring configuration also contains nonzero kicker/defense coefficients; the current production scorer rejects unsupported coefficients even for inactive position types. The capture reports those constraints explicitly. The historical evaluator must not silently remove scoring rules to make a league appear compatible. Supporting these configurations is a separate model change requiring tests and re-evaluation.

## Evaluation protocol

Use fixed forecast origins, reconstruct standings solely from completed weeks, and retain the exact scoring rules, future schedule, eligible rosters, player forecasts, source snapshots, and model version. Authentic historical inputs may be replayed today; the date we run the new code need not precede the games. The input snapshots still must precede the independently evidenced forecast cutoff.

Freeze fitting decisions on earlier data and reserve later seasons or independent league groups for evaluation. Keep prospective archived predictions separate from retrospective replays, and split reports by model and forecast origin. Report playoff/championship Brier score, log loss, reliability bins, skill versus an equal-team baseline, and expected-win error where present. Resample entire league lineages for uncertainty; two lineages are inadequate for a strong population-level conclusion. Local JSON timestamps and hashes alone do not authenticate an archive, so any supplied-archive results remain conditional on provenance review.

Historical championship results do not identify the causal benefit of a hypothetical trade that never happened. Calibration of baseline season odds is necessary evidence for Win Now, but does not by itself validate every displayed trade uplift or partner acceptance estimate.

## Current conclusion

The historical outcome collection and evaluator provide the validation workflow. The new player-based championship model has **not** been calibrated by this collection: we have no authenticated pregame input archive for these past seasons, and the initial cohort falls outside its current strict rule coverage. The older `backend/outlook/` backtest assesses a different strength model and does not validate `backend/season_simulator.py`.

The next usable evidence is either a historical provider archive containing the full remaining-season forecast at each origin, or snapshots actually captured before future games. Pair those with supported league-state snapshots, then evaluate against the outcome collector without changing the model on the held-out sample. No automatic flag graduation or recurring capture is configured by this work.

## Capture and report results

The live read-only collection completed at `2026-09-05T03:21:06.357299Z` (September 4 locally). It recovered all six completed seasons: 72 team-season records, 1,008 regular-season team scores (504 head-to-head games), 36 playoff participants, and six champions. The two explicit missing-season exclusions are Lakeview 2022 and 2023, absent from its predecessor chain. The collector retrieved weeks 1–18; standings use only weeks 1–14.

- [Outcome summary and raw-capture hash](historical-outcomes-2026-09-04.json) preserves anonymous roster-number labels and observed standings.
- [Readiness report](historical-readiness-2026-09-04.json): six valid outcome seasons, two league lineages, zero current-model-compatible seasons, zero archived prediction records, and no calibration metrics claimed.
- Full 1.74 MB capture: `/private/tmp/ftf-win-now-history-20260904.json`. This is local research input, not committed application data. The smaller outcome summary is a review artifact, not a replacement input for the evaluator.

## Reproduce and extend

Run from the repository root. The capture creates its output exclusively; choose a new path for another capture. It performs public GETs with a 20-second timeout and at most five requests per second, bounded to eight predecessor steps per seed and sixteen captured seasons by default.

```sh
python3 scripts/capture_season_history.py \
  --league-id 1312076055586050048 --league-id 1312140920132497408 \
  --seasons 2022 2023 2024 2025 \
  --output /private/tmp/ftf-win-now-history-new.json

python3 scripts/evaluate_season_calibration.py \
  --outcomes /private/tmp/ftf-win-now-history-new.json \
  --output /private/tmp/ftf-win-now-readiness.json
```

For real archived inputs, add `--predictions archived-predictions.json --checkpoints reviewed-checkpoints.json`. The versioned field contract is documented in `backend/season_calibration.py`. Each prediction cohort contains every league team, one model version and forecast origin, probabilities, optional whole-cohort expected wins, the complete remaining-week horizon, source capture timestamps, archive evidence references/hashes, and either an archived-prediction or retrospective-replay declaration. Retrospective replays also declare the frozen fitting/holdout protocol. The evaluator validates those assertions for consistency; it does not download or independently authenticate the referenced archives or run the player simulator itself.

The source-probe artifact contains the exact six URLs and retrieval details. Re-requesting one can inspect today's payload, but cannot reproduce the archived response bytes or establish an earlier capture date.

## Verification and code walk

Three Astra subagents implemented collection, evaluation, and an independent method audit. Parent reviewed all code and tests, ran the real source/capture probes and the offline report, and corrected integration/documentation details. Final affected test command:

```sh
python3 -m pytest backend/tests/test_season_history.py \
  backend/tests/test_season_calibration.py backend/tests/test_season_forecasts.py \
  backend/tests/test_season_simulator.py -q
```

Result: **119 passed in 0.95s**, local Python 3.14. Both CLI help/run paths were exercised. No production DB, model weights, flags, or UI changed, so mobile runtime testing is not applicable to this addition. Hosted Python 3.12 CI remains a pre-merge requirement for the full feature.

Code walk: `scripts/capture_season_history.py:20` bounds and paces public GETs, writes a new capture exclusively, and stamps completion; `backend/season_history.py:155` follows predecessor chains without profiles/final rosters and deduplicates related sampling lineages; `:70` derives regular-season labels from weekly scores plus the authoritative placement bracket; `:31` reports rule coverage separately. `backend/season_calibration.py:78` rejects inconsistent origins, post-cutoff snapshots, incomplete horizons and team cohorts; `:162` computes errors/reliability and resamples whole league lineages; `:215` preserves exclusions and empty-evidence reports. `scripts/evaluate_season_calibration.py:16` writes the offline report with no serving imports or feature activation.

Named subagent sabotage checks: treating custom zero scores as false, allowing post-cutoff snapshots, and inverting playoff truth each made their guard tests fail; each change was restored before the final parent run.
