# Code-walk proof — Receipts

**Date:** 2026-08-21 · **Branch:** `feat/receipts` · **Evidence class:** D-056 written code-walk
(the simulator and Maestro are retired; this plus the structural check
`mobile/tests/check-receipts.js`, the 54-test pytest suite, and the operator's manual
TestFlight pass in [testflight-checklist.md](testflight-checklist.md) are the whole
evidence set).

Every line below is a real `file:line` on this branch at the commit that added it. Where a
claim is also test-enforced, the test is named — a code-walk that cannot be re-checked is a
story.

---

## 1. Serve → impression → snapshot → grade → payload → screen

| # | Step | Where |
|---|---|---|
| 1 | A deck job serves cards and stamps the impression rows. `user_id` is the ACCOUNT id (`g_user_id = sess["user_id"]`, `backend/server.py:5441`), which is what the read route later scopes on | `backend/server.py:6101` (`_log_deck_signal_impressions(...)`) |
| 2 | The row carries the PREDICTION: `assets_json` (asset ids + direction), `served_at`, `trade_hash`, and the frozen slice keys | `backend/database.py:500-607` (`deck_impressions_table`) |
| 3 | A separate daily job writes the yardstick — consensus value per player per format per UTC day, denormalized at snapshot time so an engine repricing cannot rewrite history | `backend/server.py:19531` (`_write_daily_value_snapshots`), table at `backend/database.py:1298` |
| 4 | Grade time: the queue is every telemetry-era, non-ghost impression whose window has elapsed and has **no grade row** at the current version | `backend/database.py:13212` (`_receipts_candidate_where`), consumed at `:13267` (`load_receipts_queue`) |
| 5 | One snapshot prefetch per format per batch, then a pure per-impression grade | `backend/receipts_service.py:803` (`_grade_batch`) → `:559` (`grade_one`) |
| 6 | Terminal rows are appended, insert-or-ignore on `uq_receipts_grade` | `backend/database.py:13312` (`insert_receipts_grades`) |
| 7 | Read time (user): viewer-scoped, ghost-filtered, deduped, min-n gated, all three windows in one payload | `backend/receipts_service.py:927` (`league_receipts`) via `backend/server.py:16127` (`league_receipts_route`) |
| 8 | Read time (operator): per-cell win share with Wilson intervals | `backend/receipts_service.py:1127` (`admin_metrics`) via `backend/server.py:8293` |
| 9 | Screen renders one payload; the window chips select fields of it and never refetch | `mobile/src/screens/ReceiptsScreen.tsx` (`WindowChips` → `onWindow`, no `getLeagueReceipts` call inside) |

**Enforced by:** `test_receipts_grading.py::test_t9_payload_carries_all_three_windows_always`,
`::test_t9_viewer_scoping_hides_other_users_rows`, and structural check 4 (one `useQuery`,
one `getLeagueReceipts`).

---

## 2. The cron 202 path — grading never runs inline

`POST /api/cron/receipts-grade` (`backend/server.py:19810`):

1. `_require_cron_auth()` — `X-Cron-Secret`, fails **closed** in prod (`server.py:19038`).
2. `grading_enabled()` (`receipts_service.py:167`) checks the env kill switch **before** the
   flag, and returns `200 {"ok": true, "skipped": "flag"}` with **no writes** when either
   says no.
3. `remaining_resolvable()` is computed on the request thread *before* the daemon starts, so
   the number in the 202 describes the backlog the caller is about to work on rather than a
   race.
4. `_kickoff_receipts_grading` (`server.py:19789`) checks `is_running()`
   (`receipts_service.py:178`) so `started` is answered honestly, then starts a **daemon
   thread** and returns.
5. The route returns **202** immediately. It never returns grading output.

This is the `cron_players_refresh` shape, and the reason is the same: Render "cron" is an
HTTP POST into a **single-worker** gunicorn service (`render.yaml:16`), so an inline
grading loop would block every request in the app for its duration.

**Enforced by:** `::test_t9_cron_route_is_a_202_and_no_ops_while_dark` (which stubs
`run_grading` deliberately — letting a real daemon outlive the in-memory-engine patch would
write to the dev DB, which the suite never touches).

---

## 3. Flag-off is a genuine no-op

| Surface | Flag off behaviour | Line |
|---|---|---|
| Cron endpoint | `200 {"ok":true,"skipped":"flag"}`; **no grade rows and no ledger rows** | `server.py:19810` → `receipts_service.py:691` (`run_grading` returns before acquiring the lock or writing the start row) |
| Daily-tick guard | No thread, and **`receipts_grade_started` is not serialized at all** — the tick payload stays byte-identical | `server.py:19745-19750`, response at `:19762` |
| Admin route | `404 {"error":"feature_disabled"}` | `server.py:8293` |
| User route | `404 {"error":"feature_disabled"}` — the client hides the entry point on this response rather than showing an error | `server.py:16127` |
| Mobile entry | `receiptsOn` is false ⇒ `onTrackRecord` is omitted ⇒ the control does not exist. The ROUTE stays registered so a flag revalidation cannot unmount an in-flight push | `mobile/src/screens/TradesScreen.tsx` (`useFlag('receipts.screen')`), `mobile/src/navigation/RootNav.tsx` |

The stronger claim — that flag-off is byte-identical **serving** — is structural rather than
tested-by-enumeration: no engine module imports `receipts_service`, and nothing reads a
`receipts_*` table. Both directions are guarded (§5).

**Enforced by:** `::test_t7_flag_off_writes_absolutely_nothing`,
`::test_t7_env_kill_switch_stops_the_grader_without_a_flag_write`,
`::test_t9_daily_tick_payload_is_byte_identical_while_grading_is_dark`,
`::test_t9_user_route_404s_while_the_screen_flag_is_dark`,
`::test_t9_admin_route_404s_while_grading_is_dark`.

---

## 4. The daily-tick guard — why grading fires at all

`POST /api/cron/receipts-grade` is the primary trigger, but **no Render cron service is
provisioned for it** (operator ruling Q-4), and the one "provisioned cron" this repo
believed in for value snapshots turned out to be fictional (reverted, commit `1e50d3e`). So
grading rides the `roster_history` three-trigger pattern: the dedicated endpoint
(`server.py:19810`), this guard (`server.py:19745`), and `scripts/receipts_backfill.py` all
call **one** idempotent writer, `receipts_service.run_grading` (`:691`).

The guard is fire-and-forget on a daemon thread inside its own `try/except`, so a grading
failure can neither lengthen the tick nor touch the push work above it — and single-flight
inside the service means an overlap with the dedicated endpoint no-ops rather than
duplicating.

---

## 5. The four forbidden operations (PRD DR-4), and what stops each

| # | Forbidden | Mechanism | Test |
|---|---|---|---|
| 1 | Import or replay engine code | `receipts_service.py` imports `database`, `feature_flags`, `pick_values.parse_generic_pick_id` and stdlib — nothing else (`:60-74`). The owned-pick regex is **copied locally** (`:214`) rather than importing `suggestion_telemetry`, a sibling leaf | `::test_t1_importing_receipts_service_pulls_no_engine_module` (child interpreter — asserting on `sys.modules` in-process would prove nothing, since the suite imports the engine for its own reasons) and `::test_t1_no_engine_module_imports_receipts` (the direction NG-1 actually protects) |
| 2 | Read any live value for valuation or edge arithmetic | Both endpoints come from `player_value_history` (`ctx.value_at`, `receipts_service.py:441`). `features_json` is parsed for the `basis` SLICE KEY only (`:430-447`), never for `give_value`/`receive_value`. Pick weights are frozen literals (`:131`), populated once at build time from `elo_to_value(GENERIC_PICK_SEEDS[(r,"Mid")])` and hard-coded — the sole exemption, used for coverage/pick-share and never for edge | `::test_t3_perturbing_features_json_values_changes_no_grade`, `::test_t4_repricing_generic_pick_seeds_changes_no_grade`, `::test_t4_pick_weights_survive_the_seed_table_disappearing` |
| 3 | Reconstruct assets from `trade_hash` | The hash is a dedup key and a denormalized column, nothing more. Pre-telemetry rows (`assets_json IS NULL`) are excluded by the queue predicate (`database.py:13241`) and disclosed at read time instead | `::test_t1_assets_are_never_reconstructed_from_trade_hash` (behavioural — a pre-telemetry row with a valid hash must never be graded, asserted alongside a gradeable neighbour so the run does real work), `::test_t1_the_grader_reads_trade_hash_only_as_a_dedup_key` (static) |
| 4 | UPDATE or DELETE a grade | No such path exists. `database.py` exposes `insert_receipts_grades` / `insert_receipts_grade_run` / the `load_*` selects and nothing else | `::test_t10_no_update_or_delete_path_exists_for_receipts_tables` (greps both modules), `::test_t10_regrading_never_mutates_an_existing_row` (behavioural) |

---

## 6. Why the numbers are honest — the four load-bearing choices

- **Swap edge, not acquire-side %** (`grade_one`, `receipts_service.py:643-651`). The give
  side is the market control. The sign convention is pinned in BOTH directions
  (`::test_t2_additive_drift_residual_on_a_2x1_is_negative_d`,
  `::test_t2_a_directional_win_is_positive`) because a 2x1's disclosed residual is `−d`, not
  `+d`, and this is the matrix's only sign-sensitive test — a flipped sign would have shipped
  every win rendered as a loss.
- **Anti-survivorship** (`_resolve_window`, `:531`). A player present at serve and gone at
  the window date is imputed to the consensus pool floor and RETAINED, flagged and counted.
  Dropping him would delete our worst outcomes — bias that flatters the engine exactly where
  it was most wrong (`::test_t5_a_player_who_leaves_the_pool_is_floor_imputed_not_dropped`).
- **Serve anchor is nearest-≤, never nearest** (`_serve_anchor_dates`, `:311`). A post-serve
  snapshot is look-ahead bias however near it is
  (`::test_t6_serve_anchor_never_uses_a_post_serve_snapshot`).
- **n means the rows the stats were computed over** — post-dedup, post-coverage
  (`league_receipts`, `:1000-1035`). An `n` describing a different set than the number beside
  it is the quiet way a trust feature starts lying
  (`::test_t9_n_equals_the_rows_the_stats_were_computed_over`).

---

## 7. Idempotency and crash behaviour

The work queue is defined by the **absence** of a grade row at
`(impression_id, window_days, grader_version)` (`database.py:13232-13245`). Nothing tracks
progress, so nothing can lose track of it:

- Second run over the same work: zero terminal rows (`::test_t7_a_second_run_inserts_nothing`).
- Crash mid-batch (and Render free-instance spin-down mid-run is the same case): completed
  inserts stand under the unique constraint, the rest re-queue, and the run's unmatched
  `kind='start'` ledger row is the kill marker
  (`::test_t7_a_partial_insert_crash_resumes_without_duplicates`,
  `::test_t7_the_run_ledger_records_a_start_end_pair`).
- Retry-pending impressions are **never persisted** — a row whose window snapshot has not
  arrived simply stays out of the table until it resolves or its 14-day deadline passes
  (`::test_t6_retry_pending_writes_no_row_then_goes_terminal`).
- A retry-pending row cannot starve a run: resolvability is folded into the queue predicate,
  and the cross-format case is skipped in-loop without consuming the batch cap
  (`::test_t6_retry_pending_rows_do_not_starve_the_batch_cap`).
