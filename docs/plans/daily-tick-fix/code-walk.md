# Code-walk proof: daily-tick fix (S3)

> File:line-cited trace for scope §3 "Code-walk proof". Line numbers are from branch `fix/daily-tick-s3`
> at the commit that adds this file (base `origin/main` @ `712dcbed`). `server.py` = `backend/server.py`,
> `daily_tick.py` = `backend/daily_tick.py`. Tests named here are in `backend/tests/`.

## Contents

- [(a) Auth, then thread start, then 202](#a-auth-then-thread-start-then-202)
- [(b) Each step's gate and lock, preserved](#b-each-steps-gate-and-lock-preserved)
- [(c) Steps 1, 2, 3 and 5 call the same body as their async wrappers](#c-steps-1-2-3-and-5-call-the-same-body-as-their-async-wrappers)
- [(d) Replenishment is unreachable while the flag is off](#d-replenishment-is-unreachable-while-the-flag-is-off)
- [(e) A raise in step k does not prevent step k+1](#e-a-raise-in-step-k-does-not-prevent-step-k1)
- [(f) No step needs a request or app context](#f-no-step-needs-a-request-or-app-context)

## (a) Auth, then thread start, then 202

1. `server.py:24743`: `cron_daily_tick` calls `_require_cron_auth()` first, synchronously. That function
   (`server.py:24431-24450`) `abort(503)`s in prod with no secret and `abort(401)`s on a wrong or missing
   `X-Cron-Secret` (`:24449-24450`). An abort raises out of the handler, so lines `:24744-24746` never run and
   no thread starts.
2. `server.py:24744`: `now = datetime.now(timezone.utc)` uses server.py's own `datetime` name, on the request
   thread, so a test's `patch.object(server, "datetime", …)` pins it.
3. `server.py:24745`: `_daily_tick.start(_daily_tick_steps(), now, log=log)`. The table is built per call
   (`:24749-24765`), so each entry is the module's current function.
4. `daily_tick.py:71-75`: `_lock.acquire(blocking=False)`. If a run already holds it, a warning naming the run's
   age is logged and `False` is returned. Nothing is started.
5. `daily_tick.py:76-93`: otherwise it records the start time and starts ONE `daily-tick-runner` daemon thread,
   then returns `True` without waiting for it.
6. `server.py:24746`: `return jsonify({"ok": True, "started": started}), 202`.

Tests:
- `test_daily_tick_route.py::test_post_returns_202_at_once_then_runs_all_nine_steps_in_order`. Every step blocks
  until the test opens a gate after the response is in hand; the 202 arrives in under 1 s with no step finished.
- `::test_missing_or_wrong_secret_is_rejected_and_starts_no_thread`: 401 twice, `start` never called, no
  `daily-tick-runner` thread alive.
- `::test_second_post_while_a_run_is_in_flight_answers_started_false`.

## (b) Each step's gate and lock, preserved

Every gate below is evaluated inside the step function, which runs on the runner thread, so it is read at run
time. None is read at import or when the table is built.

| # | Step (`server.py`) | Gate / lock in the new step | Same gate in the old code / async wrapper |
|---|---|---|---|
| 1 | `_daily_tick_roster_snapshot` `:24388` | flag `market.roster_history` `:24393`; `>=` weekday gate `:24395-24397` | `_kickoff_roster_snapshot_sweep` `:24378`, `:24381-24383` |
| 2 | `_daily_tick_usage_trends` `:30787` | flag `usage_trends.enabled` `:30792`; `_usage_refresh_lock.acquire(blocking=False)` `:30794` (busy ⇒ `skipped`), released in `finally` `:30798-30799` | `_kickoff_usage_refresh` `:30807`; `_start_usage_refresh` `:30772`, `:30780-30781` |
| 3 | `_daily_tick_receipts_grade` `:24957` | `grading_enabled()` (flag + `FTF_RECEIPTS_GRADE`) `:24965`; `is_running()` `:24967` | old tick guard `grading_enabled()`, then `_kickoff_receipts_grading` `:24948`; `run_grading`'s own `_RUN_LOCK` still backs both |
| 4 | `_daily_tick_rookie_monitor` `:24768` | none (the once-per-process `_class_load_seen` set lives in `_check_rookie_class_load`) | old tick: unguarded call |
| 5 | `_daily_tick_players_guard` `:2143` | tick gate `_IS_PROD_ENV` and cache past TTL `:2157-2159`; `FTF_PLAYERS_REFRESH` `:2160-2162`; TTL re-check `:2163-2165`; in-flight flag claimed under `_players_refresh_lock` `:2166-2170` | old tick gate (same expression); `_refresh_players_cache_async` `:2120-2131` (`force=False`) |
| 6 | `_daily_tick_reengagement` `:24778` | lifecycle snapshot at step start `:24787`; per-kind caps inside `_send_typed_push` (unchanged); `notif.honest_winbacks` inside the loop (moved verbatim) | old handler loop, moved unchanged |
| 7 | `_daily_tick_replenishment` `:24879` | `_deck_replenishment_enabled()` `:24884`; `replenish_weekday` `>=` gate inside `_run_weekly_replenishment` `:23930-23931` | old tick `if _deck_replenishment_enabled():` around the same call |
| 8 | `_daily_tick_eval_nightly` `:24890` | none (idempotent per UTC day inside `run_all`) | old tick: same call, same two log lines |
| 9 | `_daily_tick_value_model_refit` `:24904` | `_deck_value_model_enabled()` `:24910` | old tick `if _deck_value_model_enabled():` around the same call |

- **Players in-flight protocol:** `_players_refresh_worker` clears `_players_refresh_active` in its `finally`
  (`server.py:2106-2109`). The flag is therefore released on every path, exactly as when the daemon ran the
  worker.
- **Tests (each gate driven through every branch):** `test_daily_tick_route.py::test_roster_step_keeps_the_flag_and_weekday_gates_then_sweeps_inline`,
  `::test_usage_step_keeps_the_flag_gate_and_single_flight_lock` (also asserts the lock is held during the
  body and released after), `::test_receipts_step_keeps_both_guards_then_grades_inline`, and
  `::test_players_step_keeps_every_guard_then_runs_the_worker_inline` (also asserts the flag is held while the
  worker runs and cleared after).

## (c) Steps 1, 2, 3 and 5 call the same body as their async wrappers

| Step | Inline (runner thread) | Async wrapper (dedicated route) | Shared body |
|---|---|---|---|
| 1 | `server.py:24398`: `_run_roster_snapshot_sweep(now, _ROSTER_SNAPSHOT_SWEEP_BUDGET, ACTIVE_LEAGUE_WINDOW_DAYS)` | `_start_roster_snapshot_daemon` `:24366`, used by `cron_roster_snapshot` `:24501` (with `active_within_days=None`) | `_run_roster_snapshot_sweep` `:24307` (unchanged) |
| 2 | `server.py:30797`: `_run_usage_refresh("daily_tick", now=now)` | `_start_usage_refresh` `:30777`, used by `cron_usage_trends_refresh` `:24525` | `_run_usage_refresh` `:30754-30765` |
| 3 | `server.py:24969`: `run_grading(trigger="daily_tick")` | `_kickoff_receipts_grading` `:24951`, used by `cron_receipts_grade` | `receipts_service.run_grading` (unchanged) |
| 5 | `server.py:2171`: `_players_refresh_worker()` | `_refresh_players_cache_async` `:2133`, used by `cron_players_refresh` `:25036` | `_players_refresh_worker` `:2082` (unchanged) |

- **The only body that moved is usage's.** The closure that used to live inside `_start_usage_refresh` is now
  `_run_usage_refresh` (`:30754-30765`), statement for statement: fetch, cache drop when anything was stored,
  log line. `_start_usage_refresh` keeps its lock, its `try/except/finally` and its thread
  (`:30772-30784`).
- **The four dedicated routes' handlers are unchanged,** as are `_refresh_players_cache_async`,
  `_kickoff_receipts_grading` and `_start_roster_snapshot_daemon`.
- **Test:** `test_daily_tick_route.py::test_usage_async_wrapper_still_runs_the_same_body`. The existing
  `test_usage_trends_refresh.py`, `test_players_refresh.py`, `test_roster_history.py` and
  `test_receipts_grading.py` route tests all stay green.

## (d) Replenishment is unreachable while the flag is off

1. The only call site of `_run_weekly_replenishment` is `server.py:24886`
   (`git grep -n "_run_weekly_replenishment(" backend/server.py`).
2. That line follows `if not _deck_replenishment_enabled(): return "skipped", "flag off"` (`:24884-24885`).
3. `_deck_replenishment_enabled` (`server.py:4432`) reads `FLAGS.deck_replenishment` each time it is called, here
   on the runner thread at run time. A flag flip plus `POST /api/feature-flags/reload` therefore takes effect on
   the next run.
4. With the flag off there are no deck builds, no `_send_typed_push("deck_replenished")` and no
   `log_deck_replenish` marker row. All three live only inside `_run_weekly_replenishment`.

Tests:
- `test_daily_tick_route.py::test_replenishment_flag_off_never_calls_the_pass_and_logs_skipped` (spy never called;
  exactly one `daily-tick step=replenishment ms=<n> outcome=skipped detail=flag off` line).
- `::test_replenishment_flag_on_past_the_weekday_calls_the_pass_once` (flag on, Thursday ≥ Wednesday: called once,
  with the handler's clock).
- `test_deck_replenishment.py::test_flag_off_no_replenish_work_no_push_no_payload_change` (no generation, no push,
  no marker row, step `skipped`).

Mutation check: deleting `:24884-24885` turns both flag-off tests red.

## (e) A raise in step k does not prevent step k+1

1. `daily_tick.py:47-59`: one loop iteration per step. The step call (`:50`) sits inside `try`, and
   `except Exception` (`:52-54`) logs the traceback (`log.exception`, a separate `daily-tick: step <key> raised`
   line) and sets `outcome="error"`, `detail="<Class>: <message>"`.
2. The iteration then logs the single step line (`:55-58`) and appends the result (`:59`), and the `for` moves on
   to step k+1.
3. Only a `BaseException` (not `Exception`) can leave the loop. Even then, `_body`'s `finally`
   (`daily_tick.py:83-84`) releases the single-flight lock, so the next day's tick can still start.

Tests:
- `test_daily_tick_runner.py::test_raising_step_is_an_error_and_every_later_step_still_runs`;
- `::test_exactly_one_line_per_step_in_the_exact_format`;
- `::test_lock_is_released_after_a_raising_step`;
- `::test_lock_is_released_even_when_a_run_escapes_step_isolation`;
- `test_daily_tick_route.py::test_a_raising_step_never_stops_the_steps_after_it` (step 3 raises; steps 4–9 run).

Mutation check: removing the `try/except` turns four of these tests red. Removing the `finally` release turns
the lock tests red.

## (f) No step needs a request or app context

None of the nine step functions references `request`, `g`, `jsonify` or `current_app`:
`git grep -n "request\.\|\bg\.\|jsonify" backend/server.py` finds no hits inside `:2143-2173`, `:24388-24399`,
`:24768-24915`, `:24957-24970` or `:30787-30800`.

What each step reaches:
- **Steps 1, 2, 3 and 5:** their bodies already ran on daemon threads, outside any request: `roster-snapshot-sweep`,
  `usage-trends-refresh`, `receipts-grade-*` and `players-refresh`.
- **Step 4:** one DB `COUNT` (`count_rookie_class_rows`).
- **Step 6:**
  - `_user_data_lifecycle.snapshot()` / `.capture()` (`backend/user_data_lifecycle.py`) use only a lock, per-user
    condition variables and a `ContextVar`, none of them Flask.
  - The step takes its snapshot at step start (`server.py:24787`), not from `g`.
  - `_send_typed_push` (`server.py:23489`) reads `g` only behind `has_request_context()` (`:23509`), so off-request
    it captures with `started=None` and inherits the step's snapshot through the `ContextVar` set by the loop's
    `.active()`.
- **Step 7:**
  - `_replenish_deck_for` → `_kickoff_trade_job(..., synchronous=True)` reads `g` only behind
    `has_request_context()` (`server.py:9384`).
  - The rest is DB and in-process session/job state (`_sessions`, `_trade_jobs`, both lock-guarded).
- **Steps 8 and 9:** `backend/eval/nightly.py` and `backend/value_model.py` import nothing from Flask
  (`git grep -n "flask" backend/eval/nightly.py backend/value_model.py` returns no hits).

The handler takes `now` on the request (`server.py:24744`) and hands it in, so no step reads the clock through
the request either.

Tests: every route test above runs the steps on the `daily-tick-runner` thread with no request context. The first
test asserts the thread name, and `test_notif_teardown.py`'s winback / Aug-25 tests drive the real step 6 there
with the pinned clock.
