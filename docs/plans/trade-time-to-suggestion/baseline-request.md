# Baseline request: time to trade suggestion (for analytics-lead, W3)

**Requested by:** trades-pm, 2026-10-15 · **For:** [prd.md](prd.md) §6, which is marked
"PENDING analytics-lead read (W3)" until this read returns.
**Ask:** run the read-only queries below against production and return the output tables in the
shapes given. Nothing here writes, flips or generates anything.

## Ground rules

- **Read-only.** Use `SET default_transaction_read_only = on`, confirm it is on, and use a 15 s
  statement timeout. No `EXPLAIN ANALYZE` on large tables.
  - No generation requests, no admin POSTs, no knob changes.
  - Q0 uses authenticated admin **GETs** only, and only if your W3 grant covers them. Otherwise mark
    Q0 "not run".
- **Window:** the 14 days ending at the read: `occurred_at >= <run_date − 14 d>`. Report the exact
  UTC bounds you used.
  - `user_events.occurred_at`, `client_ts`, `deck_impressions.served_at` and
    `bakeoff_runs.created_at` are **VARCHAR ISO strings**. Compare them as text. `extract()` fails
    on them (`.claude/skills/feedback/lessons.md:389`).
- **Split at the filter ship.** Report server timings (Q2–Q4) separately before and after
  **2026-10-15 01:18 UTC**, when `deck.quality_filters` went live
  (`living-memory/CHANGELOG.md:14-18`).
- **Population:**
  - iOS client rows only (`user_events.platform = 'ios'`) for client queries.
  - Apply the standard exclusion `analytics_queries.device_exclusion(include_demo=False)`
    (`backend/analytics_queries.py:473-500`): no `device:%`, `demo_%`, `test_user_fp_%` or `qa_%`
    ids, and no demo sessions.
- **Privacy:** aggregates only. No user, league, trade or player ids in the returned tables (the
  `docs/business/analytics/2026-07-17-tracking-plan-v2.md:183` posture).
- **Small n:** about 8 users and 16 user-league pairs had a qualifying deck in 14 days
  (`living-memory/TEST_LEDGER.md:200-201`).
  - Report n on every row.
  - Report p95/p99 only when n ≥ 40 (p99 only at n ≥ 100). Otherwise show "—", plus max and the
    share ≤ 250 ms.

### Schema used (from `backend/database.py`)

| Table | Columns relied on | Defined at |
|---|---|---|
| `user_events` | `user_id`, `event_type`, `occurred_at` (server receive, ISO), `client_ts` (client wall clock, ISO with ms; `mobile/src/api/events.ts:202`), `session_id`, `league_id`, `platform`, `device_type`, `os_version`, `app_version`, `screen`, `props` (JSON text) | `:2141-2175` |
| `deck_impressions` | `impression_id`, `user_id`, `league_id`, `deck_job_id`, `card_index`, `served_at` (ISO; one value per job), `is_ghost`, `model_arm`, `features_json` | `:928-1071` |
| `bakeoff_runs` | `deck_job_id`, `user_id`, `league_id`, `deck_size`, `total_ms`, `served_arm`, `created_at` | `:1184-1201` |
| `league_members` | `league_id`, `user_id`, `roster_data`, `updated_at` | `:625-633` |
| `member_rankings` | `user_id`, `league_id`, `updated_at`, `scoring_format` | `:683-690` |
| `player_value_history` | `scoring_format`, `snapshot_date` | `:1817-1827` |
| `prepared_trade_*` (v1 and v2) | sizes only | `:70-190` |

### Event facts the queries depend on

- **`calc_find_a_trade_tapped`** {`path`, `give_count`, `receive_count`, `has_partner`} fires **at
  the tap** of the canvas Find a Trade (`mobile/src/utils/canvasSearch.ts:52-61`).
  - `give_count > 0` means the fairness sweep.
  - An empty canvas, or `give_count = 0`, means the model deck.
- **`find_trades_tapped`** {`source`, `mode`} fires from in-deck controls
  (`mobile/src/screens/TradesScreen.tsx:1221`). For handoffs it fires **at dispatch inside the
  pushed deck** (`:3329-3336`, `source` ∈ calculator / league_offer), and for the fair sweep at
  `:3799`.
  - One canvas tap can therefore produce `calc_find_a_trade_tapped` and then
    `find_trades_tapped{source:'calculator'}`.
- **`trade_card_viewed`** {`trade_id`, `card_index`, `ms_since_open`, `cold_start`, `mode`, …} fires
  once per fronted card (`TradesScreen.tsx:4255-4282`).
  - It is the best existing end proxy. It marks fronting, not "controls enabled".
- **`trades_generated`** (server) props: {`count`, `gen_ms`, `engine_version`, `lanes`,
  `deck_source`?} (`backend/server.py:7614-7617`, `:9226-9238`).
  - `gen_ms` is job start → successful finish (`server.py:3060-3077`). Failed and superseded jobs
    emit nothing.
  - `deck_source` is present only for non-pull jobs (e.g. replenishment). Its absence mixes
    interactive searches with session-init warm-ups
    (`trade-search-latency/execution-20260921/infrastructure-and-precompute.md:42`).
  - Props carry **no job id**.
- **`deck_impressions.served_at` is one timestamp per job**, taken when the impression logger starts
  and shared by every row (`backend/server.py:5197`). It is not a per-batch commit time.
- **`api_request`** rows (`user_events`, `user_id='system:api'`, props {`ms`, `route`, `status`})
  give per-request handler time. Successes are sampled 1-in-10 (`obs_success_sample_n`,
  `backend/database.py:3073`; written at `backend/api_observability.py:360-380`).
- **No analytics row carries a job or request id**, so client taps cannot be joined to server jobs
  exactly (`mobile/src/api/client.ts:54-61`). The joins below use stated heuristics; label them as
  such.

## Q0. Live configuration readback (optional, GET-only)

Return the current values and readback time for:
- `model_config`:
  - `prepared_trade_inventory_enabled`;
  - the owner-serving keys `bakeoff_include_owner`, `bakeoff_serve_owner`, `bakeoff_owner_only`,
    `owner_bilateral_enabled`, `owner_bilateral_revision_enabled`, `significance_mode` and
    `simple_player_presentment`;
  - `bakeoff_deck_limit`, `bakeoff_serve_interleaved`, `owner_pool_size`, `owner_pair_budget`,
    `owner_total_budget`, `full_sweep_budget_s` and `obs_success_sample_n`.

  The checked-in seeds (`backend/database.py:3158-3182,3248,3278`) leave #303's owner batching and
  prepared adoption inactive. Production has differed from them before, so which path is live
  depends on these values.
- `/api/feature-flags`: `trade.prepared_inventory`, `deck.quality_filters`, `trade.value_core`,
  `deck.replenishment`, `calc.inline_home`, `calc.results_push`, `obs.api_events`.

**Why:** the last prepared-inventory readback was 0, on 2026-09-23
(`prepared-trade-inventory/release.md:154`). Nothing since confirms it.

| key | value | read_at_utc |
|---|---|---|

## Q1. Tap → first card, client proxy (the headline baseline)

**Taps:**
- `T` = `user_events` rows where `event_type IN ('calc_find_a_trade_tapped','find_trades_tapped')`,
  `platform='ios'`, in the window, with exclusions applied.
- **De-duplicate:** a `find_trades_tapped` whose `props.source IN ('calculator','league_offer')`
  that comes ≤ 5 s after a `calc_find_a_trade_tapped` in the same `session_id` is the same search.
  Anchor on the earlier row, and also report the gap between them (tap → dispatch, which includes
  the `TradeDeck` push).

**First card:**
- `V` = the first `trade_card_viewed` with `props.card_index = 0` in the same `user_id` and
  `session_id`, with `client_ts` after the tap's `client_ts`, before the next tap in that session,
  and ≤ 120 s after the tap.
- `delta_ms = client_ts(V) − client_ts(T)`, using client clock on both sides.
- A tap with no `V` inside 120 s is **no-card**. Separately count no-card taps with an
  `api_request_failed` in the same session within 120 s as **errored**.

**Cohorts:**
- `search_type`:
  - `fair_sweep` if `give_count > 0`;
  - `pinned_or_partner` if `receive_count > 0` or `has_partner`;
  - `organic` if the canvas is empty;
  - `in_deck` for `find_trades_tapped` without a preceding canvas tap, split by `props.source`.
- `launch_state`:
  - `cold_launch` if an `app_opened` exists in the same `session_id` ≤ 60 s before the tap;
  - `first_tap` for the first tap in the session otherwise;
  - `repeat_tap` for the rest.
- `app_version`, `device_type`.

**Output:**

| search_type | launch_state | n_taps | n_card | n_no_card | n_errored | p50_ms | p90_ms | p95_ms | p99_ms | max_ms | share_le_250ms | share_le_1s | share_le_3s | share_le_10s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

Second output, the de-duplication gap: `n`, p50, p95 and max of tap → dispatch.

## Q2. Server worker time

`trades_generated` rows in the window (server rows, `source='api'`), with user exclusions.

| deck_source (absent = pull) | engine_version | period (pre/post 2026-10-15 01:18) | n | p50_gen_ms | p90 | p95 | p99 | max | share_count_0 | p50_count | p95_count |
|---|---|---|---|---|---|---|---|---|---|---|---|

## Q3. Engine time

`bakeoff_runs` in the window.

| served_arm (NULL = interleaved) | period | n | p50_total_ms | p90 | p95 | max | p50_deck_size | p95_deck_size |
|---|---|---|---|---|---|---|---|---|

## Q4. Server stage split per job

Per `deck_job_id` in the window (served rows: `is_ghost` NULL or 0):
- `logger_start = served_at`, which is the same on every row of the job;
- `rows = count(*)`;
- join `bakeoff_runs` on `deck_job_id` for `total_ms` (arm fan-out), `deck_size` and `created_at`.

`created_at` is written after the impressions (`backend/server.py:9171-9186`). Confirm it is the
insert time before relying on it.

Report distributions of:
- `rows` per job;
- `bakeoff_runs.created_at − logger_start`, approximately the evidence-write span;
- `total_ms`.

If `trades_generated` can be matched to the job (same `user_id` and `league_id`, `occurred_at` the
first row ≥ `bakeoff_runs.created_at` within 10 s; label it a heuristic), also report
`gen_ms − total_ms − (created_at − logger_start)`. That is the unattributed time: input capture,
post-layers, filters and revalidation.

This query is server-clock only. It is not tap-relative.

| period | n_jobs | p50_rows | p95_rows | p50_total_ms | p95_total_ms | p50_evidence_span_s | p95_evidence_span_s | n_matched_gen | p50_unattributed_s | p95_unattributed_s |
|---|---|---|---|---|---|---|---|---|---|---|

**Optional, if you have Render log access:** the distribution of `elapsed_ms` from
`trade-job … first durable owner batch: cards=… elapsed_ms=…` (`backend/server.py:9033-9038`; it
appears only on the owner-serve path), shaped like Q2.

## Q5. Tap → server job (heuristic join, to locate where the time goes)

For each Q1 tap with `search_type='organic'`, find the first `deck_impressions` job for the same
`user_id` and `league_id` whose `logger_start` (`served_at`) is ≥ the tap's `occurred_at`, within
120 s. Both are
server clock, but `occurred_at` is the event batch's receive time, so it lags the tap.

Then report:
- `logger_start − occurred_at(T)`;
- the share of taps whose job's `logger_start` is **before** the tap's `occurred_at`. This is the
  cache or joined-warm-up proxy: the job existed before the tap arrived.

| launch_state | n_matched | n_unmatched | share_job_preexisting | p50_s | p95_s |
|---|---|---|---|---|---|

## Q6. Input staleness at tap (freshness baseline for prd §5.1)

For each Q1 organic tap, using **current** rows. These tables hold latest values, not history, so
restrict to taps in the last 72 h and say so:

- **roster_age:** tap `occurred_at` − `league_members.updated_at` for the tapping user's row in that
  league, and the **max** across that league's members (the partner side);
- **ranking_age:** tap − `max(member_rankings.updated_at)` for (user, league, scoring_format);
- **value_age_days:** tap date − `max(player_value_history.snapshot_date)` for the league's format.

Also, for every league with a tap in the window, the share of `league_members` rows with `updated_at`
older than 7 days. This is the G-075 exposure (`living-memory/GOTCHAS.md:98-102`).

| input | n | p50 | p90 | p95 | max | share_over_5min | share_over_24h |
|---|---|---|---|---|---|---|---|

## Q7. Volume (does the sample floor look reachable?)

| entry (event + source/path) | taps_per_day_p50 | taps_14d | distinct_users | distinct_user_leagues |
|---|---|---|---|---|

## Q8. Storage footprint (for prd §10.4, AC-11 and the parallel DB-storage task)

Use read-only catalog functions only: `pg_total_relation_size` and `pg_relation_size`.

- Table sizes (total, heap and indexes/TOAST), row counts, and growth over the window (rows/day)
  for `deck_impressions`, `deck_diagnostic_snapshots`, `deck_candidate_sets`, `user_events`, and
  every `prepared_trade_*` table.
- Database total size, and the disk used/free figure from the Render dashboard if your grant
  covers it.
- On a sample of ≤ 1,000 recent `deck_impressions` rows: `avg(pg_column_size(features_json))` and
  `avg(pg_column_size(t.*))`.

| table | rows | rows_per_day_14d | total_bytes | heap_bytes | index_toast_bytes | avg_row_bytes (sampled) |
|---|---|---|---|---|---|---|

## Q9. Route handler time (`api_request` sampling)

`user_events` rows with `event_type='api_request'`, for `props.route` in `/api/trades/generate`,
`/api/trades/status`, `/api/trades/fair-packages`, `/api/trades/asset-ideas` and
`/api/session/init`. Split by `props.status` class (2xx / 4xx / 5xx). Note that 2xx rows are sampled
1-in-10, so counts are ×10 estimates and percentiles are sample percentiles.

| route | status_class | n_rows | est_requests | p50_ms | p90_ms | p95_ms | p99_ms | max_ms |
|---|---|---|---|---|---|---|---|---|

**Why:** under 250 ms, even one `/status` poll or one `/generate` round trip has to fit the server
slice of the budget (prd §10.2). This is the only existing server-side per-request timing.

## What comes back to trades-pm

The tables above (Q0–Q9), the exact window bounds, and any query you could not run, with the reason.
trades-pm then replaces `prd.md` §6's provisional table with these results and keeps the prior
numbers as history.
