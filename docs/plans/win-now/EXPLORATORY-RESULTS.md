# Exploratory historical evaluation — 2026-09-04

Ran the operator-approved diagnostic using later-revised Sleeper projections and historical league outcomes. **One league-season (Lakeview 2024), 12 teams, four forecast origins, 10,000 season simulations per origin.** This produces 48 team/origin rows, but only one independent championship outcome.

## Results

Lower error is better. Final-win error is mean absolute error in regular-season wins, including the league’s additional median-match wins (28 possible wins over 14 weeks). Brier score measures probability error; equal-odds baselines are 0.2500 for playoffs and 0.0764 for the championship.

| Completed weeks | Final-win error | Playoff Brier | Championship Brier | Actual champion’s projected chance |
|---:|---:|---:|---:|---:|
| 3 | 2.60 | 0.0678 | 0.0535 | 28.1% |
| 6 | 1.81 | 0.0252 | 0.0428 | 35.1% |
| 9 | 1.21 | 0.0217 | 0.0327 | 44.0% |
| 12 | 0.76 | 0.0000 | 0.0288 | 46.9% |

The model beat equal odds at each scored origin and final-win error decreased as more actual games were known. The equal-odds control does not incorporate current standings, so this comparison does not isolate the forecasts’ value beyond standings. Perfect playoff classification after week 12 is one sample result, not a general accuracy claim. No uncertainty interval is estimated from a single league lineage.

## Inclusion and exclusions

Lakeview 2024 supplied all four scored origins: after weeks 3, 6, 9 and 12. Lakeview 2025 was attempted at all four origins but excluded because roster 12 could not fill a source-covered legal lineup in projected week 13 (`incomplete_lineup_coverage:12:13`). Its rostered quarterbacks lacked usable Week 13 stat forecasts. Four FFv3 seasons were excluded for active kicker/IDP slots. No missing player projections were fabricated to admit those seasons.

For both offensive-only seasons, the diagnostic removed unsupported scoring coefficients from a local input copy and recorded the exact omitted keys. Production scoring is unchanged. “Model-supported” counts in this diagnostic report refer to those adjusted inputs, not the production compatibility of the original league configurations.

## Assumptions attached to this run

- Historical projection URLs were fetched now; the full remaining-season horizon combines later weekly revisions.
- Standings use completed games only, including custom zero overrides and median matches. Rosters come from the last completed week and remain fixed thereafter; historical reserve/taxi eligibility is unavailable.
- Current injury and current-team metadata are ignored. Usable stat rows are treated as available; past starter requirements were relaxed only where missing future starter forecasts blocked replay. All listed roster IDs and full legal-lineup coverage checks were retained; missing player IDs and original starters are recorded in replay details.
- The independent player/week residual model and legal projected lineup selection are unchanged. Actual future lineup decisions, roster moves and correlated injuries are not modeled.
- These are exploratory measurements with potentially optimistic later information. They do not establish historical calibration, causal trade uplift, or a release threshold. No flags or production settings changed.

## Artifacts and reproducibility

[Machine-readable results](exploratory-results-2026-09-04.json) include reliability bins, per-origin metrics, exclusions, assumptions and the 28-response source manifest. Full local inputs and replay details are in `/private/tmp/ftf-win-now-diagnostic-final-20260904`; the slim source cache is `/private/tmp/ftf-revised-weekly-cache`. Cache envelopes preserve actual source capture timestamps and response hashes.

```sh
python3 scripts/run_season_historical_diagnostic.py \
  --outcomes /private/tmp/ftf-win-now-history-20260904.json \
  --cache /private/tmp/ftf-revised-weekly-cache \
  --output-dir /private/tmp/ftf-win-now-diagnostic-new --sims 10000

python3 scripts/evaluate_season_calibration.py \
  --outcomes /private/tmp/ftf-win-now-diagnostic-final-20260904/adjusted-outcomes.json \
  --predictions /private/tmp/ftf-win-now-diagnostic-final-20260904/predictions.json \
  --checkpoints /private/tmp/ftf-win-now-diagnostic-final-20260904/checkpoints.json \
  --exploratory-revised-inputs --output /private/tmp/exploratory-evaluator.json
```

Parent verification: **144 affected tests passed in 0.62s**. The independent evaluator CLI reproduces the runner’s four metric groups exactly; cached rerun metrics match the first run exactly. The strict CLI control rejects all four revised-input cohorts. Parent reviewed the Astra evaluator changes and the replay adapter, including prefix-only standings, median win units, source provenance, assumptions and exclusions. The native/web product is unchanged.
