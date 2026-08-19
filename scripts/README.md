# scripts/

Backend-side utility scripts: local seeding, one-off fixture captures, and offline
research backtests. **Not application code** — nothing here is imported by `backend/`.

Run from the repo root with the backend's Python environment active:
`python scripts/<name>.py`. Scratch output goes to gitignored `scripts/scratch/`.

Deeper per-script notes (arguments, verdict documents, the "must pass `seed_type`"
trap) live in [`CLAUDE.md`](CLAUDE.md).

## Seeding & demo — writes the local DB

| Script | Purpose |
|---|---|
| `create_test_league.py` | Fabricate a league for local testing |
| `seed_test_user.py` / `seed_test_user_2.py` | Insert test users with rosters + rankings |
| `publish_test_rankings.py` | Publish canned ranking snapshots |
| `demo_matchup.py` | Run the Claude-powered smart matchup picker end-to-end |

**Never point these at production.**

## Offline research — no network, no DB

Backtests and hypothesis tests behind the #169 outlook / league-summary work.
Each writes a verdict doc under `docs/feedback/items/169-outlook-league-summary/`;
fixtures live in `backend/tests/fixtures/`.

| Script | Purpose |
|---|---|
| `outlook_calibration_backtest.py` | As-of backtest of the outlook odds engine against 6 captured Sleeper league-seasons |
| `outlook_preseason_backtest.py` | Backtest of the preseason `roster_value` strength source (rewinds standings, rosters, and values) |
| `outlook_pick_capital_hypothesis.py` | Tests the draft-pick-capital hypotheses (1a upgrade-signal vs 1b rebuild-signal) |
| `outlook_pick_capital_dated_values.py` | Re-tests 1b's Δ-roster-value sub-test with period-correct value boards |
| `outlook_hypothesis_bench_depth.py` | Tests the bench-depth / injury-fragility hypothesis (1c) |
| `outlook_idp_pricing_backtest.py` | Five-variant backtest of BUG-5 (IDP slots priced at 0.0), split by league |
| `outlook_strength_source_compare.py` | Diagnostic: roster-value prior vs Sleeper projections as strength source. Needs `--players-cache`; **the projections source is never shipped** |
| `deck_eval.py` | Offline deck-quality + latency eval — the onboarding-conversion ship gate. Reads the public Sleeper API (read-only); report in `docs/plans/onboarding-conversion/deck-eval-report.md` |

## Fixture capture — network, run once

| Script | Purpose |
|---|---|
| `outlook_pick_capital_capture.py` | Captures `traded_picks` + trade transactions from Sleeper's public API into `backend/tests/fixtures/outlook-hypotheses/` |
| `dp_values_history_capture.py` | Captures **dated** DynastyProcess value boards into `backend/tests/fixtures/dp-values-history/`. Module: `backend/dp_values_history.py` |

Both read public endpoints and write only fixtures. Re-run only to refresh/extend fixtures.
