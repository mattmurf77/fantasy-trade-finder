# Tooling command index

Run commands from the repository root with the backend Python environment unless
stated otherwise. These are operator, fixture, and research tools. Some research
modules are imported by `backend/tests/`; retain their import paths when reorganizing.
Temporary output belongs in gitignored `scripts/scratch/` or the command's explicit
output directory. Per-script implementation traps live in [CLAUDE.md](CLAUDE.md).

## Project maintenance

| Command | Purpose | Writes / external access |
|---|---|---|
| `python3 scripts/session_context.py --check` | Validate the bounded session-memory and hook output contract | Read-only local files |
| `python3 scripts/codecity/generate.py` | Regenerate the local Code City repository visualization | Generated local visualization assets; [instructions](codecity/README.md) |
| `python3 -m unittest discover -s tests/project_hygiene` | Project organization and session-context regression checks | Temporary test files only |
| `bash mobile/scripts/testid-lint.sh` | Validate current testIDs against archived historical flow specifications | Read-only local files; runs in CI |

Current mobile verification commands live in [mobile/package.json](../mobile/package.json).
Retired simulator commands are preserved in
[archive/retired-tooling/mobile/](../archive/retired-tooling/mobile/README.md) and refuse execution.

## Local seeding and demonstration

Never configure these commands against production.

| Command | Purpose | Writes / external access |
|---|---|---|
| `python3 scripts/seed_test_user.py [--dry-run] [--clear]` | Seed the preserved April 2025 FantasyPros profile | Local DB unless `--dry-run`; `--clear` replaces only this profile's swipes |
| `python3 scripts/seed_test_user_2.py [--dry-run] [--clear]` | Seed the preserved April 2026 FantasyPros profile | Same behavior, separate test-user identity |
| `python3 scripts/create_test_league.py [--dry-run] [--clear]` | Fabricate a test league from local league data | Local DB |
| `python3 scripts/publish_test_rankings.py` | Publish canned ranking snapshots | Local DB |
| `python3 scripts/demo_matchup.py` | Exercise the smart matchup picker | Backend/model access; see script configuration |

The two ranking entry points share [one implementation and named profile data](fixtures/README.md).

## Operational commands

Read each script's usage and the linked runbook before selecting its database or
service. These tools remain at their established paths; they are not cleanup scratch.

| Script / invocation | Purpose | Writes / external access |
|---|---|---|
| `python3 scripts/set_knob.py KEY VALUE` | Logged model-config change through the admin endpoint; `--local` selects the local DB path | Service/DB write; [runbook](../docs/runbook.md) |
| `python3 scripts/backfill_sleeper_trades.py --dry-run` | Count/fetch the organic executed-trade corpus and historical league chain | Public Sleeper reads; omit `--dry-run` to append to the selected DB |
| `python3 scripts/backfill_suggestion_links.py --dry-run` | Reconstruct historical exact suggestion links | Selected DB; omit `--dry-run` to write links |
| `python3 scripts/receipts_backfill.py --dry-run` | Inspect or drain the Receipts grading backlog | Selected DB; omit `--dry-run` to grade/write |
| `python3 scripts/remediate_analytics_tokens.py --database /absolute/offline.db` | Explicit offline analytics remediation | Dry-run by default; `--apply` writes, requires stopped app workers; see script prerequisites |
| `backend/scripts/` | Established calibration, replay, pick-value and historical feedback backfill commands | Mixed effects; [backend tooling map](../backend/CLAUDE.md) |
| `backend/tools/prod_analytics.py` | Read-only production analytics reports | Selected production DB, read-only transaction posture |
| `qa/` operator scripts | Explicit live verification and test-data support | Mixed effects; [QA instructions](../qa/README.md) |

## Research and measurement

| Script / input | Purpose | Writes / external access |
|---|---|---|
| `evaluate_season_calibration.py` | Score archived Win Now predictions; revised-input analysis requires an explicit exploratory option | Offline output; [protocol](../docs/plans/win-now/HISTORICAL-VALIDATION.md) |
| `outlook_calibration_backtest.py` | As-of outlook-odds calibration against captured league seasons | Offline, fixture reads |
| `outlook_preseason_backtest.py` | Preseason strength backtest with rewound rosters, standings and values | Offline, fixture reads |
| `outlook_pick_capital_hypothesis.py`, `outlook_pick_capital_dated_values.py` | Draft-pick-capital hypotheses and period-correct value remeasurement | Offline, fixture reads |
| `outlook_hypothesis_bench_depth.py` | Bench-depth / injury-fragility hypothesis | Offline, fixture reads |
| `outlook_idp_pricing_backtest.py` | IDP pricing variants; also a test oracle | Offline, fixture reads |
| `outlook_strength_source_compare.py` | Roster-value / projection diagnostic; projection source is not shipped | Offline, explicit `--players-cache` input |
| `deck_eval.py` | Deck-quality and latency measurement | Public Sleeper reads; report/output |
| `knockout_knob_sweep.py` | Compare generation under model-config variants | DB reads guarded against writes; public player/value fetches; optional JSON output |
| `bakeoff_readout.sql`, `negmem-gr4-joint.sql`, `negmem-stamp-rate.sql` | Measurement readout and tripwire query packs | Execute only through a read-only DB session with statement timeout |
| `python3 -m backend.eval.replay` | Importable offline deck-evaluation package | Explicit datasets; [backend map](../backend/CLAUDE.md) |

## Capture and historical diagnostics

These read public endpoints and write explicit local captures. Run to extend or
refresh datasets, not as routine product checks.

| Script | Purpose |
|---|---|
| `capture_season_history.py` | Bounded league-history, weekly-matchup and bracket capture |
| `probe_season_forecasts.py` | Weekly stat-forecast horizon probe and optional prospective snapshot |
| `run_season_historical_diagnostic.py` | Opt-in revised-input player simulator diagnostic; [results](../docs/plans/win-now/EXPLORATORY-RESULTS.md) |
| `outlook_pick_capital_capture.py` | Traded picks and trade transactions into outlook fixtures |
| `dp_values_history_capture.py` | Dated DynastyProcess value boards into history fixtures |
