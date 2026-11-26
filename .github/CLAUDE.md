# .github/ — Notes for Claude

Two workflows and one CI helper script (`scripts/backend-area.sh`). Nothing else lives here — no issue templates, no CODEOWNERS, no Dependabot.

## `workflows/ci.yml` — the only merge gate that runs automatically

Triggers on every `pull_request` and every push to `main`. Ubuntu jobs:

| Job | Command |
|---|---|
| `changes` | Decides whether the backend suite must run (see "Skip by area" below). Always `true` on a push to `main`. |
| `backend-suite` | `python -m pytest backend/tests -q` (Python 3.12, `requirements.txt` + `requirements-dev.txt`). Runs only when `changes` says so. |
| `backend-tests` | The gate that reports the required `backend-tests` check. Passes when the suite passed, or when it was correctly skipped. |
| `mobile-typecheck` | `npx tsc --noEmit` in `mobile/` (Node 20, `npm ci`), then every `mobile/tests/check-*.js` structural suite |
| `web-structure` | `qa/web/check_web_structure.py`, `qa/web/check_trade_search.cjs`, and `scripts/qa/test_instant_trade_report.py` |
| `maestro-testid-lint` | `bash mobile/scripts/testid-lint.sh` |

Notes for anyone adding a job:

- **There is no iOS-simulator job and there will not be one** — no free macOS runner, and operator decision **D-056** (2026-08-15) retired Maestro/simulator work entirely. `maestro-testid-lint` is a static lint of `testID` references and was explicitly kept.
- `mobile-typecheck` globs `mobile/tests/check-*.js`, so a new structural suite runs in CI as soon as the file exists. No npm script or workflow edit is needed.
- Making these required checks on `main` is a repo-settings branch ruleset — an operator action, not something a workflow file can do.

### Skip by area (which jobs run for which change)

Every push to `main` runs the full backend suite, whatever changed. Skipping applies to pull requests only, and only to the backend suite. The three cheap jobs always run: each takes under two minutes, and path-filtering them is not clearly safe (`mobile/tests/check-*.js` read `backend/`, `config/`, `docs/` and `web/`; `qa/web/check_web_structure.py` reads `backend/server.py`).

On a PR the backend suite is skipped only when every changed path is in a skipped area below. Evidence verified by grep on 2026-11-25.

| Changed area | Backend suite on a PR | Why |
|---|---|---|
| `backend/` | runs | The code under test. |
| `config/` | runs | `backend/feature_flags.py` and about 40 tests read `config/features.json`; other config JSON is read by `experiments.py`, `negmem.py` and `league_projections/`. |
| `scripts/` | runs | `test_receipts_append_only.py` and `test_error_log_templates.py` scan every `.py`/`.sql` under `scripts/`; about 20 scripts are imported by tests. |
| `web/` | runs | Flask serves `web/` as its static folder; `test_cut_web_pages.py`, `test_prod_blocked_static.py`, `test_share_link_previews.py`, `test_value_bar_scale.py` and others read or serve named files. |
| Root build and dependency files: `requirements*.txt`, `pyproject.toml`, `render.yaml`, `build.sh`, `run.py`, `.gitignore`, `.python-version` | runs | `test_win_now_api.py` runs `build.sh`; `test_packed_evidence.py` imports `run.py` and reads `render.yaml`; `test_fork_safe_db_and_threads.py` reads `requirements.txt`; several tests run `git check-ignore`. |
| `.github/workflows/ci.yml`, `.github/scripts/` | runs | They decide how the suite runs, so a change to them must exercise it. |
| `mobile/src/`, `mobile/App.tsx`, `mobile/app.json`, `mobile/ios/` | runs | `test_rookie_ranks_editable.py` and `test_analytics_taxonomy_fa_move_server.py` scan all of `mobile/src/**/*.ts*`; `test_app_version_consistency.py` reads `mobile/app.json` and `mobile/ios/DTFDynastyTradeFinder/Info.plist`; `backend/app_version_policy.py` reads `mobile/app.json`. |
| Rest of `mobile/` | skipped | No backend test reads it. |
| `docs/config-reference.md`, `docs/cross-client-invariants.md`, `docs/plans/` | runs | Tests read these two docs, and contracts plus Python backtest modules under `docs/plans/`. |
| Rest of `docs/` | skipped | No backend test reads it. |
| `.claude/skills/feedback/scripts/` | runs | `test_fetch_feedback_table.py` executes `.claude/skills/feedback/scripts/fetch_feedback.py`. |
| Rest of `.claude/` and `.github/` | skipped | No backend test reads it. |
| `living-memory/`, `qa/`, `extension/`, `githooks/`, `mockups/`, `reference/`, `screens/`, `archive/`, root `*.md`, `LICENSE`, `.easignore` | skipped | No backend test reads them. |
| Anything not listed | runs | Unknown means run. |

How it works: the `changes` job diffs the PR merge commit against its first parent (the base tip) with `git diff --name-only --no-renames`, so a rename lists both paths, and pipes the list to `.github/scripts/backend-area.sh`, which prints `true` or `false`. `backend-suite` runs only on `true`. `backend-tests` always runs and is the job behind the required check, so the check name is unchanged and the ruleset needs no edit. It fails if detection fails, if the suite was needed and did not pass, or if the suite ran when it should have been skipped.

Maintenance rule: a new backend test that reads a path in a skipped area must add that path to the "run" list in `.github/scripts/backend-area.sh` and to this table in the same PR.

## `workflows/keep-warm.yml` — production, not CI

Cron ping against the Render free-tier service so the next real request doesn't pay a
30–60s cold start (which would blow the onboarding time-to-first-trade-card budget).

**This workflow is the keep-warm switch.** Turn it off by disabling the workflow in the
GitHub Actions UI. The `onboarding.keep_warm` flag in `config/features.json` does **not**
gate it — that flag is reserved for future server-side warm affordances. Best-effort only:
Actions cron drifts, and scheduled workflows auto-disable after 60 days of repo inactivity.
Background: [`docs/runbook.md`](../docs/runbook.md) → "Render cold starts — keep-warm cron".

## Related, elsewhere

- Local pre-push enforcement: [`githooks/pre-push`](../githooks/) — install once per clone with `git config core.hooksPath githooks`.
- Current QA regime and what replaced the simulator lane: [`qa/README.md`](../qa/README.md).
