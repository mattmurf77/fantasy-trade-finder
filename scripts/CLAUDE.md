# scripts/ — Notes for Claude

One-off utility / seeding / research scripts. Run from the repo root with the same Python
env as the backend. Index + safety grouping: [`README.md`](README.md). This file carries the
per-script traps.

**Safety, in one line:** the four seeding/demo scripts (`create_test_league.py`,
`seed_test_user*.py`, `publish_test_rankings.py`, `demo_matchup.py`) write the local DB —
never point them at production. Every `outlook_*` analysis script and `deck_eval.py` are
read-only and safe anywhere; the two `*_capture.py` scripts hit the network (public
Sleeper / GitHub endpoints only) and write fixtures.

## Seeding / demo

- `create_test_league.py` — fabricate a league for local testing
- `seed_test_user.py`, `seed_test_user_2.py` — seed users with rosters + rankings
- `publish_test_rankings.py` — push canned rankings into the DB
- `demo_matchup.py` — exercise the smart matchup generator end-to-end
- `deck_eval.py` — offline deck-quality + timing eval, the onboarding-conversion GATE (build item 2 of `docs/plans/onboarding-conversion/plan.md`). Fetches rosters/users from the public Sleeper API read-only, then simulates each team's brand-new-user first session. Report: `docs/plans/onboarding-conversion/deck-eval-report.md`

## Outlook research (#169)

- `outlook_calibration_backtest.py` — offline as-of backtest of the #169 outlook odds engine against captured past Sleeper seasons (fixtures in `backend/tests/fixtures/outlook-calibration/`). No network, no DB. Verdict: `docs/feedback/items/169-outlook-league-summary/calibration-report-2026-08-09.md`; combined post-fix re-measurement: `calibration-combined-2026-08-10.md`. **Every bracket it builds must be passed the league's `playoff_seed_type` via `seed_type(fx)`** — omitting it scores the four FFv3 seasons (all `playoff_seed_type: 0`, a FIXED bracket) under the reseeding rule they don't use. Pinned by `test_backtest_scripts_pass_seed_type_into_every_bracket_they_build`.
- `outlook_strength_source_compare.py` — diagnostic only: roster-value prior vs Sleeper projections as the outlook strength source. The projections source lives here on purpose and is **never shipped**; needs `--players-cache` in a worktree.
- `outlook_hypothesis_bench_depth.py` — offline test of operator hypothesis 1c (bench depth / injury fragility) against the same 6 captured Sleeper league-seasons as the calibration backtest, plus a DP value-board snapshot and a slim Sleeper players cache in `backend/tests/fixtures/outlook-hypotheses/`. No network, no DB writes. Verdict: `docs/feedback/items/169-outlook-league-summary/hypothesis-bench-depth-2026-08-09.md`

- `outlook_pick_capital_capture.py` — one-time network capture (public Sleeper REST v1) of `traded_picks` + trade-only `transactions/{week}` for the 6 outlook-calibration league-seasons, into `backend/tests/fixtures/outlook-hypotheses/`. Run once; re-run only to refresh the fixtures.
- `outlook_pick_capital_hypothesis.py` — offline test of the #169 operator's draft-pick-capital hypotheses (1a "more picks → in-season upgrades" vs 1b "more picks → rebuild signal, sheds players") against the same 6 seasons. No network, no DB. Verdict: `docs/feedback/items/169-outlook-league-summary/hypothesis-pick-capital-2026-08-09.md`

- `dp_values_history_capture.py` — one-time NETWORK capture of **dated** DynastyProcess value boards (`values-players.csv` at a historical commit) into `backend/tests/fixtures/dp-values-history/`. Run once; re-run only to add seasons/weeks. Reads two public GitHub endpoints, writes only fixtures. Module: `backend/dp_values_history.py`.
- `outlook_preseason_backtest.py` — offline backtest of the **preseason `roster_value`** strength source: rewinds standings AND rosters (real week-1 rosters from `/matchups/1`) AND values (kickoff-day dated board), then scores as-of week 0 against reality. Verdict: `docs/feedback/items/169-outlook-league-summary/dated-values-revalidation-2026-08-09.md`. No network, no DB.
- `outlook_pick_capital_dated_values.py` — offline re-test of hypothesis 1b's Δ-roster-value sub-test with period-correct boards (three pricings: published PPG control, contemporaneous, kickoff-board-both-ends). Same report.
- `outlook_idp_pricing_backtest.py` — offline five-variant backtest of **BUG-5** (the value board prices QB/RB/WR/TE only, so 8 of FFv3's 15 starting slots price at 0.0): status quo vs the IDP slot-eligibility fix vs a league-mean fallback vs two coverage attenuations, scored **split by league** so the IDP and non-IDP leagues are separable. Also carries `legacy_select()`, the verbatim pre-BUG-5 selection, used as the oracle by `backend/tests/test_outlook_idp_pricing.py`. Verdict: `docs/feedback/items/169-outlook-league-summary/idp-pricing-2026-08-09.md`. No network, no DB.
