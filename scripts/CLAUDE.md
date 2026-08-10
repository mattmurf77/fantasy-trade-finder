# scripts/ — Notes for Claude

One-off utility / seeding scripts. Run from the repo root with the same Python env as the backend.

- `create_test_league.py` — fabricate a league for local testing
- `seed_test_user.py`, `seed_test_user_2.py` — seed users with rosters + rankings
- `publish_test_rankings.py` — push canned rankings into the DB
- `demo_matchup.py` — exercise the smart matchup generator end-to-end
- `outlook_calibration_backtest.py` — offline as-of backtest of the #169 outlook odds engine against captured past Sleeper seasons (fixtures in `backend/tests/fixtures/outlook-calibration/`). No network, no DB. Verdict: `docs/feedback/items/169-outlook-league-summary/calibration-report-2026-08-09.md`
- `outlook_strength_source_compare.py` — diagnostic only: roster-value prior vs Sleeper projections as the outlook strength source. The projections source lives here on purpose and is **never shipped**; needs `--players-cache` in a worktree.
- `outlook_hypothesis_bench_depth.py` — offline test of operator hypothesis 1c (bench depth / injury fragility) against the same 6 captured Sleeper league-seasons as the calibration backtest, plus a DP value-board snapshot and a slim Sleeper players cache in `backend/tests/fixtures/outlook-hypotheses/`. No network, no DB writes. Verdict: `docs/feedback/items/169-outlook-league-summary/hypothesis-bench-depth-2026-08-09.md`

The first three `outlook_*` scripts are read-only and safe anywhere. The rest touch the local DB — don't run those against production.
- `outlook_pick_capital_capture.py` — one-time network capture (public Sleeper REST v1) of `traded_picks` + trade-only `transactions/{week}` for the 6 outlook-calibration league-seasons, into `backend/tests/fixtures/outlook-hypotheses/`. Run once; re-run only to refresh the fixtures.
- `outlook_pick_capital_hypothesis.py` — offline test of the #169 operator's draft-pick-capital hypotheses (1a "more picks → in-season upgrades" vs 1b "more picks → rebuild signal, sheds players") against the same 6 seasons. No network, no DB. Verdict: `docs/feedback/items/169-outlook-league-summary/hypothesis-pick-capital-2026-08-09.md`

The `outlook_calibration_backtest.py`, `outlook_pick_capital_hypothesis.py`, and `outlook_strength_source_compare.py` (once `--players-cache` is supplied) scripts are read-only and safe anywhere. The rest touch the local DB or the network — don't run those against production; `outlook_pick_capital_capture.py` only ever reads Sleeper's public API, never writes anywhere.
