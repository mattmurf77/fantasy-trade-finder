# Feature Scope — daily-tick fix (S3): stop the 120 s kill

**Date:** 2026-10-22
**Entry point:** direct ask. The operator approved the build in head-eng's session (2026-10-20, verbatim: "Yes, also
build the S3 daily-tick fix."). Brief: `docs/plans/org-bringup/briefs/build-s3-daily-tick-league-eng.md` (records
worktree), with head-eng's rulings appended.
**Builder:** `league-eng` (design, acceptance) → one `eng-backend` worker. Branch `fix/daily-tick-s3`, base
`origin/main` @ `712dcbed`.
**Operator sign-off on waivers:** the waivers in §1 and §3 (no analytics; no TestFlight) are surfaced to head-eng
in this scope block. The API change in §2 was approved by head-eng on 2026-10-20 under full gates.

---

## 0. Problem and design

**Failure** (`docs/runbook.md` § Known outage).
- `POST /api/cron/daily-tick` (`backend/server.py:24678`) runs every step inline on the one sync gunicorn worker
  (`--workers 1 --timeout 120`, `render.yaml:16`).
- Since at least 2026-10-01 the worker has been killed about 150 s into every run.
- **Wed–Sun:** the killer is the inline weekly replenishment, about 17.4 s per pre-built deck (`db-capacity.md`
  M16).
- **Mon–Tue:** most likely the inline re-engagement scan or the inline eval nightly. The eval loads 30 days of
  `trade_impressions` with every column (`backend/eval/data.py:108`) and runs 1,000 bootstrap resamples per scorer.
- **What never runs:** the steps after the kill. Four of them were already daemon kickoffs costing about 0 s inline
  (roster snapshots, Usage Trends, receipts grading, players-cache refresh); they never start because they come
  after the slow steps.
- **No other trigger:** players-refresh and receipts-grade have no scheduler of their own (no Render cron), so they
  have not run since then either.

**Design (B), approved by head-eng 2026-10-20.** The handler authenticates, starts one **single-flight runner
thread** and returns **202** at once. The runner runs the steps **serially**. Each step is wrapped so that a raise
or a slow step never skips the rest, and each step logs one timing line. Order (permanent-loss writers first):

| # | Step key | What runs (helper today) | Gate (read at run time) |
|---|---|---|---|
| 1 | `roster_snapshot` | ADR-011 Writer B sweep, `_run_roster_snapshot_sweep` (today behind `_kickoff_roster_snapshot_sweep`) | `market.roster_history`; `FTF_ROSTER_SNAPSHOT_WEEKDAY` `>=` gate |
| 2 | `usage_trends` | `usage_trends_refresh.refresh_usage_weeks` (today behind `_start_usage_refresh`) | `usage_trends.enabled`; `_usage_refresh_lock` single-flight |
| 3 | `receipts_grade` | `receipts_service.run_grading(trigger="daily_tick")` (today behind `_kickoff_receipts_grading`) | `receipts.grading`; `is_running()` single-flight |
| 4 | `rookie_monitor` | `_check_rookie_class_load(_CURRENT_SEASON + 1)` | none |
| 5 | `players_guard` | `_players_refresh_worker` (today behind `_refresh_players_cache_async`) | `_IS_PROD_ENV` and cache past TTL; `_players_refresh_lock` / `_players_refresh_active` |
| 6 | `reengagement` | the user loop now inline in `cron_daily_tick` (`server.py:24699-24776`), moved verbatim into a function | per-kind caps inside `_send_typed_push` |
| 7 | `replenishment` | `_run_weekly_replenishment(now)` | `deck.replenishment` via `_deck_replenishment_enabled()`, **at run time**; the `replenish_weekday` gate |
| 8 | `eval_nightly` | `eval.nightly.run_all(window_days=30)` | none (idempotent per UTC day) |
| 9 | `value_model_refit` | `_value_model.nightly_refit(now=now)` | `deck.value_model` |

- **Where things live.** The runner goes in a new `backend/daily_tick.py`, which does not import `server.py` and is
  testable on its own. `server.py` keeps the helpers and registers the step table. Steps resolve server helpers at
  call time, so existing `patch.object(server, …)` tests still bite.
- **No step changes behavior.** Steps 1, 2, 3 and 5 get a synchronous entry beside their existing async wrapper:
  same body, same lock or single-flight. Their own routes (`/api/cron/roster-snapshot`, `/receipts-grade`,
  `/players-refresh`) stay byte-identical.
- **Rejected: (A), the cron service running the steps in its own process.**
  - Steps 5, 7 and 9 are tied to web-process state: the on-disk cache plus `_pool_generation`; `_sessions` plus
    `_trade_jobs`; and the served `models.jsonl`.
  - Importing `server.py` runs `init_db()` (`:464`) and starts `_cleanup_loop` (`:2817`) and the Win Now worker
    (`:33474`).
  - (A) is a post-launch follow-up (head-eng ruling 4), after the helpers are extracted out of `server.py`.

**The replenishment trap** (brief § "The trap"). If the tick survives, a live `deck.replenishment` would pre-build
and write full evidence weekly, and it renews itself (`db-capacity.md` latent issue 1). Rules:
- the runner reads the flag at run time;
- a test pins that replenishment cannot run while the flag is off;
- **no merge while `deck.replenishment` is ON** (the operator chose to pause it; the flip belongs to release-lead's
  session).

## 1. Analytics scope

- [x] **(c) WAIVED, no analytics needed because:**
  - the change is operator infrastructure with no user-visible surface;
  - observability is one server log line per step plus the runbook's existing DB liveness queries;
  - no event is added, removed or renamed, and nothing touches `analytics_taxonomy.py`.

## 2. Schema & flag scope

- **New/changed tables or columns:** none.
- **New/changed feature flags:** none. The flags read are unchanged (`market.roster_history`, `usage_trends.enabled`,
  `receipts.grading`, `deck.replenishment`, `deck.value_model`, `notif.honest_winbacks`); all are read at run time.
- **New env vars / `model_config` keys:** none. `FTF_ROSTER_SNAPSHOT_WEEKDAY`, `FTF_RECEIPTS_GRADE`,
  `FTF_PLAYERS_REFRESH` and `replenish_weekday` keep their meaning.
- **Rollback lever:** revert the commit (Render redeploys the last good sha). Each step keeps its own flag or env
  kill switch.
- **API contract change (approved by head-eng 2026-10-20):** `POST /api/cron/daily-tick` moves from `200 {ok,
  …counters, [replenish], [roster_snapshot], [players_refresh_started], [receipts_grade_started], [usage_refresh]}`
  to **`202 {"ok": true, "started": <bool>}`**. `started: false` means a run is already in flight. The counters
  move to the per-step log line.
  - Callers: only Render's `notif-daily-tick` cron (`curl -fsS`, which accepts any 2xx). No client calls it.
  - Auth is unchanged (`_require_cron_auth()`, synchronous, before the thread starts).
  - `render.yaml` needs **no** change.

## 3. Evidence scope

- [ ] **Structural guard:** n/a (backend only; no mobile file touched).
- [ ] **Unit tests:**
  - **New `backend/tests/test_daily_tick_runner.py`** (does not import `server`):
    - steps run in table order;
    - a raising step is logged `outcome=error` and every later step still runs;
    - each step logs exactly one line `daily-tick step=<key> ms=<int> outcome=<ok|skipped|error>`;
    - single-flight: a second `start()` while a run is in flight returns `False` and starts nothing;
    - the lock is released after a raising run.
  - **New route tests** (in `test_daily_tick_runner.py` or a sibling file that imports `server`):
    - with every step stubbed to sleep about 2 s, `POST /api/cron/daily-tick` returns 202 `{ok: true, started:
      true}` in well under 1 s, and all 9 steps then run in order;
    - without `X-Cron-Secret`, it is still rejected before any thread starts;
    - **replenishment guard:** with `deck.replenishment` off, `_run_weekly_replenishment` is never called (spy) and
      its step logs `outcome=skipped`; with it on and past `replenish_weekday`, it is called once.
  - **Updated:**
    - `test_deck_replenishment.py`: `_tick` and the flag-off "byte-identical payload" test move to the 202 contract,
      and the flag-off assertions become "no replenish work, no push, no marker row" plus the payload equal to
      `{ok, started}`;
    - `test_notif_teardown.py`: the winback and Aug-25 tests run the re-engagement step, with the pinned clock still
      applying;
    - `test_receipts_grading.py::test_t9_daily_tick_payload_is_byte_identical_while_grading_is_dark`: becomes
      "grading not started while dark";
    - every other existing test stays green: `test_cron_sweep_scope`, `test_roster_history`, the usage-trends tests
      and `test_players_refresh*`.
- [ ] **Code-walk proof:** `docs/plans/daily-tick-fix/code-walk.md`, a file:line trace of the following:
  - auth, then thread start, then 202;
  - each step's gate and lock, preserved from the old code;
  - steps 1, 2, 3 and 5 calling the same body their async wrapper calls;
  - replenishment unreachable while the flag is off;
  - a raise in step k not reaching step k+1's call site;
  - no step needing a Flask request or app context (`_send_typed_push` guards `g` with `has_request_context()`; the
    `_user_data_lifecycle` snapshot is taken at step start).
- [ ] **Operator checklist** (replaces TestFlight; this is backend-only runtime proof, run by the operator because
  prod reads are theirs). On the first full UTC day after deploy, and again after the first Wednesday:
  1. Render logs for `srv-d7g37ftckfvc73a32gvg`, 13:30–14:30 UTC:
     - `POST /api/cron/daily-tick` returns **202** and there is **no** `WORKER TIMEOUT`;
     - nine `daily-tick step=` lines appear in order 1→9, then `daily-tick done`;
     - note every `ms=` value (this is S3's measurement goal).
  2. Roster history (from Tuesday on, the weekday gate): `SELECT source, count(*), max(snapshot_at) FROM
     league_roster_history GROUP BY 1` shows `weekly` rows with a `snapshot_at` in this ISO week (runbook §
     roster-snapshot monitoring).
  3. Usage Trends (from the first tick after Sleeper rolls `week`): `SELECT season, week, team_count, fetched_at FROM
     usage_week_loads ORDER BY season, week` shows the just-finished week with 26–32 teams and today's
     `fetched_at`, not a hand load.
  4. Value snapshots (hourly-tick guard, not a daily-tick step, but confirms the worker is no longer restarted
     daily): `player_value_history` has rows for today's UTC date.
  5. If `receipts.grading` is on: a `receipts-grade` run logged with `trigger=daily_tick`.
  6. Wednesday, **with `deck.replenishment` OFF:** the `replenishment` step logs `outcome=skipped` and no
     `deck_replenish_log` row is written.
- [x] **WAIVED: TestFlight checklist,** because this is backend-only with no app surface. The operator checklist
  above is the runtime evidence.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | `POST /api/cron/daily-tick` row (`:897` on base): the 202 `{ok, started}` contract, the step order, per-step gates, and counters moving to the log. The receipts-grade (`:901`) and players-refresh (`:902`) rows: the "adds `…` to its response" sentences are rewritten to "runs as daily-tick step N". |
| `living-memory/LLD.md` | **handed to release-lead's scribe at merge** | Cron convention: a long cron is 202 plus a daemon, and the daily tick is one serial single-flight runner. living-memory is the scribe's |
| `docs/architecture.md` | **updated** | Cron/background-work wiring: the new `backend/daily_tick.py` runner and its step table, and why it runs in-process (option A deferred) |
| `living-memory/HLD.md` | n/a because | no new client, service or major flow. The runner is in-process and the cron service is unchanged |
| `docs/cross-client-invariants.md` | n/a because | no shared constant, enum or color |
| `docs/glossary.md` | n/a because | no new domain term ("daily tick" exists) |
| `docs/runbook.md` | **updated** | Replace § "Known outage" with the fix, the per-step log format, and the liveness checks from §3. State that players-refresh and receipts-grade have no scheduler of their own and run as tick steps 5 and 3. Update § Usage Trends "has never completed" once proven (scribe, post-deploy). |
| ADR or `DECISIONS.md` entry | **handed to the scribe at merge** | One D- entry: "(B) in-process runner, not (A) cron process", with the three reasons in §0 |

## 5. Ship gate declaration

- **CI green:** `backend-tests`, `mobile-typecheck` (unchanged, but must stay green), `web-structure` and
  `maestro-testid-lint`, all passing on the pushed sha.
- **Evidence recorded:** the `living-memory/TEST_LEDGER.md` entry (scribe) names the pytest files and counts, the
  code-walk path, and the operator checklist outcome.
- **Merge blockers:**
  - `deck.replenishment` must be **OFF** in `config/features.json` on `origin/main` (or overridden off in prod, as
    release-lead confirms);
  - the operator's push word in league-eng's session;
  - the operator's merge go in release-lead's session;
  - release-lead's independent QA pass.
- **Watch after deploy:** the first 13:30 UTC run (operator checklist step 1). Eval nightly runs last and still loads
  30 days of full evidence; if the first run OOMs the worker at step 8, steps 1–7 have already landed. models-eng is
  asked, through head-eng, to slim it down.
- Express lane declared by the operator? **No.** Full gates.

## Known limits (accepted)

- **A hung step blocks the steps after it,** and single-flight then blocks the next day's run. Every network call in
  the steps already carries a timeout (`_sleeper_get(url, 20)`, Expo, the platform clients). A second tick while a
  run is in flight logs a warning with that run's age, so it is visible. Restarting the worker clears it.
- **A worker restart mid-run** (deploy at 13:30, OOM) loses the rest of that run. Each step is idempotent and the
  weekday gates are `>=`, so the next day retries. The permanent-loss writers go first.
- **CPU:** the run shares the free instance's CPU with the 200 ms tap path for its duration. Steps 1–6 are mostly
  I/O, and the CPU-heavy steps (7 if lit, 8) run last.
