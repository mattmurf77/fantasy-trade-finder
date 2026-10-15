# DB storage budget — requirements

> **Status: REQUIREMENTS, not design.** Drafted 2026-10-15 by `analytics-lead`. States what any storage
> design must satisfy and how it is checked; it does not pick an architecture, migration, vendor or cost.
> Every size is the last measured baseline (2026-09-15, cited) or **pending the W3 inventory read** (§3.4).
> No production read was made for this doc; local SQLite counts are test noise and are not cited.

## 1. Purpose and owners

Operator, 2026-10-15, verbatim: *"Database storage: We need to find a way to limit database usage
(DB is close to full storage and we don't have the budget to increase). I don't want to compromise
the robustness of the user events tracking or the trade history. So either find a better, cheaper
approach or something else."*

| Concern | Owner |
|---|---|
| Requirements (this doc), the inventory read, metric/readout parity checks | `analytics-lead` |
| Architecture, migration plan, maintenance procedure | `head-eng` |
| Cost model; clearance of any paid component | `head-bizops` (`fin-pnl`) |
| Prepared-inventory product need (Find a Trade latency) | `head-product` (`trades-pm`) |

Stale-claim note: the `an-data-architect` charter and `analytics_queries.py:21-27` still call client events dark.
`analytics.client_events`, `analytics.ingest`, `experiments.engine` (`config/features.json:121-123`) and
`obs.api_events` (`:250`) are all `true`, so client-event volume is real and unmeasured.

## 2. Constraints

| ID | Constraint | Source |
|---|---|---|
| C-1 | Disk is the Render 5 GB volume (5,246,714,000 B reported 2026-09-15). The operator rules out an increase. Increases are permanent; storage cannot be reduced again | `db-storage-reduction/release.md:3,50`; `runbook.md:1243-1245` |
| C-2 | Postgres compute is Basic 256 MB. A ~28 MB single `INSERT` OOM-killed it on 2026-09-07. Every write, rewrite, copy or archive step must be bounded (the shipped precedent is 100-row, ~2 MB statements) | `render.yaml:6`; `runbook.md:594` |
| C-3 | One gunicorn worker with a 120 s timeout. The cleanup loop and prepared-inventory ticks share that process. Maintenance must not starve product requests | `render.yaml:16`; `server.py:2732-2812` |
| C-4 | SQLite locally and in CI, Postgres in prod. The report layer is dual-dialect, with text ISO timestamps and no SQL JSON functions. Any new reader (archive or rollup) must run on both, or CI cannot gate it | `analytics_queries.py:8-12`; `analytics-platform/hld.md:111` |
| C-5 | No paid infrastructure unless `fin-pnl` clears it. Extra disk costs $0.30/GB-month, but the operator has ruled it out | `db-storage-reduction/release.md:3` |
| C-6 | Autoscaling stays off. There is no compute change | `db-storage-reduction/status.md:5-6` |
| C-7 | Public privacy commitments: rankings, rating history and daily consensus values are "retained indefinitely". A successful deletion removes activity and usage events. Changing either needs an operator decision and a policy edit | `web/privacy.html:214-238` |
| C-8 | Incident rules stay in force: take a backup and recovery point first, use bounded transactions, never do a bulk table delete, and never run an unreviewed `VACUUM FULL`, which needs an exclusive lock plus temporary disk | `db-storage-reduction/scope.md:18`; `runbook.md:1255-1284` |

## 3. Baseline and what is unknown

### 3.1 Last measured baseline — 2026-09-15 16:55 UTC (after compaction and `VACUUM FULL`)

| Measure | Bytes | Source |
|---|---:|---|
| Whole Postgres database (before compaction: 895,088,319) | 539,281,087 | `db-storage-reduction/release.md:41` |
| `deck_impressions` + `deck_diagnostic_snapshots`, incl. indexes/TOAST | 431,964,160 | `release.md:42` |
| … `deck_impressions` alone | 244,547,584 | `release.md:44` |
| … `deck_diagnostic_snapshots` alone | 187,416,576 | `release.md:45` |
| Render volume used / size (20.03%) | 1,051,078,660 / 5,246,714,000 | `release.md:50-51` |
| Planning runway, 20% reserve, ~9 KB/record | ~350,000 records ≈ 380 runs at ~910 cards/job | `release.md:17-19,58-62` |

### 3.2 Inferences from that baseline (arithmetic on cited numbers, not measurements)

- **All 92 other tables, plus catalog, totalled at most 107,316,927 B** (539,281,087 − 431,964,160).
  On 2026-09-15 this covered `user_events`, `deck_candidate_sets`, `trade_impressions` and everything else.
- **Non-relation disk use was 511,797,573 B**, about 49% of the volume used (1,051,078,660 − 539,281,087).
  That is WAL and platform overhead. Projections must use Render's volume bytes, as `release.md:55-58` did, not `pg_database_size`.
- **At least 97.4% of stored recommendation rows were unlabelled.** Compaction checked 67,159 impression rows
  against 1,715 outcome rows (`db-storage-reduction/status.md:12-14`).
- **Hypothesis — verify:** "close to full" 30 days after the 380-run runway was set fits about 12–13 generation runs per day.
  If so, `deck_impressions` core rows are the dominant growth. `release.md:19` predicted this: "Core recommendation rows still grow indefinitely."

### 3.3 Unknown — current sizes are NOT measured in this doc

Today's bytes per table, weekly growth, WAL or replication-slot retention, dead tuples and index bloat are
all unmeasured. Unmeasured since 2026-09-15: (a) tables added later (`usage_*`, `grading_*`); (b) value-core
and Calibration rows; (c) client events; (d) whether prepared-inventory rollout is on (last recorded off,
`prepared-trade-inventory/status.md:7`, 2026-09-23); (e) post-cleanup diagnostic steady state.

### 3.4 Inventory read (W3) — exact read-only SQL, to be run by `analytics-lead` once the prod-read grant is in force

Posture of `backend/tools/prod_analytics.py:57-62` (`default_transaction_read_only=on`, `statement_timeout`).
Run Q0–Q6 on day 0 and Q7 on day 7.

```sql
-- Q0  session posture (no writes are possible)
SET default_transaction_read_only = on;  SET statement_timeout = '60s';
-- Q1  database size
SELECT now() AS measured_at, pg_database_size(current_database()) AS db_bytes;
-- Q2  per-table size, tuples, vacuum state (every table, largest first)
SELECT c.relname AS table_name,
       pg_total_relation_size(c.oid) AS total_bytes, pg_relation_size(c.oid) AS heap_bytes,
       pg_indexes_size(c.oid) AS index_bytes,
       COALESCE(pg_total_relation_size(NULLIF(c.reltoastrelid, 0)), 0) AS toast_bytes,
       s.n_live_tup, s.n_dead_tup, s.n_tup_ins, s.n_tup_upd, s.n_tup_del,
       s.last_vacuum, s.last_autovacuum, s.last_analyze, s.last_autoanalyze
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
WHERE n.nspname = 'public' AND c.relkind IN ('r','p')
ORDER BY total_bytes DESC;
-- Q3  per-index size and use (index-bloat / unused-index evidence)
SELECT t.relname AS table_name, i.relname AS index_name,
       pg_relation_size(i.oid) AS index_bytes, si.idx_scan
FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid
JOIN pg_class t ON t.oid = x.indrelid JOIN pg_namespace n ON n.oid = t.relnamespace
LEFT JOIN pg_stat_user_indexes si ON si.indexrelid = x.indexrelid
WHERE n.nspname = 'public' ORDER BY index_bytes DESC;
-- Q4  non-relation disk: replication slots, WAL settings (pg_ls_waldir needs pg_monitor; skip if denied)
SELECT slot_name, active, pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) AS retained_wal_bytes
FROM pg_replication_slots;
SELECT name, setting, unit FROM pg_settings WHERE name IN ('max_wal_size','min_wal_size',
  'wal_keep_size','autovacuum','autovacuum_vacuum_scale_factor','autovacuum_vacuum_threshold');
SELECT sum(size) AS wal_dir_bytes FROM pg_ls_waldir();
-- Q5  rows + approx stored (compressed) row bytes per ISO week, last 12 weeks; excludes page/index
--     overhead. ISO-text timestamps make the date-prefix compare exact. Run per (table, ts column):
--     user_events.occurred_at, deck_impressions.served_at, deck_candidate_sets/deck_diagnostic_snapshots/
--     trade_policy_shadow/bakeoff_runs/trade_decisions/swipe_decisions/prepared_trade_manifests_v2.created_at,
--     deck_outcomes.acted_at, trade_impressions.shown_at, elo_history.snapshot_at,
--     player_value_history.snapshot_date, sleeper_trades.synced_at, experiment_assignments.assigned_at.
SELECT to_char(substr(served_at,1,10)::date, 'IYYY-"W"IW') AS iso_week,
       count(*) AS rows, sum(pg_column_size(t.*)) AS row_bytes
FROM deck_impressions t
WHERE served_at >= to_char(current_date - 84, 'YYYY-MM-DD')
GROUP BY 1 ORDER BY 1;
--     On timeout: exact count(*), bytes from TABLESAMPLE SYSTEM (10) x 10. JSON-heavy tables: also sum
--     pg_column_size() of features_json, valuation_json, assets_json, candidates_json, payload_json, props.
-- Q6  user_events by class (the DEC-1 evidence), last 12 weeks
SELECT to_char(substr(occurred_at,1,10)::date, 'IYYY-"W"IW') AS iso_week,
       CASE WHEN event_type IN ('api_call','api_request') THEN 'obs'
            WHEN user_id LIKE 'device:%' THEN 'pre_auth_client'
            WHEN event_id IS NULL THEN 'server_fired' ELSE 'client' END AS class,
       count(*) AS rows, sum(pg_column_size(t.*)) AS row_bytes
FROM user_events t WHERE occurred_at >= to_char(current_date - 84, 'YYYY-MM-DD')
GROUP BY 1, 2 ORDER BY 1, 2;
SELECT event_type, count(*) AS rows, sum(pg_column_size(t.*)) AS row_bytes FROM user_events t
WHERE occurred_at >= to_char(current_date - 28, 'YYYY-MM-DD') GROUP BY 1 ORDER BY 3 DESC LIMIT 40;
-- Q7  day 7: rerun Q1-Q3. Report weekly growth = (day7 - day0) per table, with Render's
--     reported volume bytes on both days.
```

Deliverable of W3: fill the Size column of §4 and confirm or reject every "hypothesis" label in §4 and §6.

## 4. Table inventory — 94 tables (`Table("` in `backend/database.py`, counted 2026-10-15)

Classes: **NN** = non-negotiable (the reason follows the slash); **DR** = derived/regenerable;
**OP** = operational; **DBG** = debug; **CFG** = config/reference.
The `#` column is the definition line in `backend/database.py`.
Every user-keyed table is in the export/deletion matrix: `accounts.py:593-628` (matrix comment), `:652-661`, `:944-993`.
Size = pending W3 unless a 2026-09-15 number exists.

| Table (#) | Holds | Writer | Readers | Growth driver | Retention in code | Size |
|---|---|---|---|---|---|---|
| **NN / user events** | | | | | | |
| `user_events` (2141) | Append-only event log: server-fired, client (via ingest) and obs `api_call`/`api_request` rows. 1 PK + 5 indexes (`:2143,2160-2169`) | `record_event` (`database.py:4389`); `analytics_ingest.py:292`; `api_observability.py:190` | 15 reports (`analytics_queries.py:435`); `experiments.readout` (`experiments.py:654`); `load_league_activity` (`database.py:8854`); export and deletion | Per user action; per client event; obs per sampled API call (all errors + 1 in 10 successes, `api_observability.py:39-46`) | Obs rows only: 30 d, one unbounded `DELETE` every 6 h (`api_observability.py:396-433`). Product rows: none | pending (≤107 MB with all non-deck tables, 2026-09-15) |
| `identity_links` (2176) | device → user stitching | `link_identity` (`database.py:4556`) | `attribution_join` (`analytics_queries.py:464`), funnel stage 0–2 | Per sign-in with a device id | none | pending |
| `experiment_assignments` (2260) | Assignment audit: the readout denominator | `experiments._persist_assignment` (`:274`) | `experiments.readout` (`:663`); deletion (`accounts.py:763`) | Per unit × experiment version | none | pending |
| `wrapped_events` (2106) | Pre-cutover activity history, frozen (zero writers) | none | `load_league_activity` | none | none | pending |
| **NN / trade history** | | | | | | |
| `deck_impressions` (928) | Every card of the final served deck (~910 per job) with core cols, `features_json`, `assets_json`, `valuation_json` | `save_deck_impressions` (`database.py:6783`) | Receipts; executed-trade matcher (`database.py:7372`); fatigue (`trade_service.py:410`); Calibration (`database.py:15307`); `bakeoff_readout.sql`; disposition review 2026-08-29; `eval/scorecard_evidence.py` | Per generation run × cards | none for core rows | **244,547,584 B (2026-09-15)** |
| `deck_outcomes` (1228) | Append-only labels: viewed/like/pass/propose/undo | `save_deck_outcome` (`:6965`) | Same as above; `user_taste` | Per user card action | none | pending (1,715 rows 2026-09-15) |
| `trade_impressions` (889) | Legacy per-card served log (training negatives) | `log_trade_impressions` (`:6634`, called `server.py:7572,8963`) | Training joins; export | Per run × cards served | none | pending |
| `trade_decisions` (596) | Like/pass audit, with `impression_id` | `save_trade_decision` (`:6089`) | Match logic, `analytics_queries`, eval | Per like/pass | none (retract is a column) | pending |
| `trade_matches` (728) | Mutual matches with both impression ids | `create_trade_match` (`:9648`) | Matches UI, eval, disposition review | Per mutual like | none (anonymized on delete) | pending |
| `trade_proposals` (809) | Confirmed provider sends, frozen `valuation_json` | `save_trade_proposal` (`:6900`) | Eval, prepared runtime | Per confirmed send | none | pending |
| `sleeper_trades` (663) | Executed league trades, full `raw` payload | `record_sleeper_trades` (`:8469`) | Matcher, organic-corpus report 2026-08-16, eval | Per sync × new trades | none | pending |
| `suggestion_trade_links` (1131) | Executed trade → suggestion link | `save_suggestion_trade_links` (`:7422`) | Ratio reads; disposition and corpus reports | Per captured trade | none | pending |
| `trade_pass_reasons` (1404), `bad_trade_flags` (1739) | Decline reasons; "bad trade" flags | `upsert_trade_pass_reason` (`:7087`); `save_bad_trade_flag` (`:14530`) | `bakeoff_readout.sql`; disposition review | Per decline / flag | none | pending |
| `receipts_grades` (2772) | Append-only 14/28/56-day grades per impression | `insert_receipts_grades` (`:15055`) | Receipts read surfaces | Per graded impression × 3 windows | none | pending |
| `grading_sessions` (2856), `grading_cards` (2870) | Calibration grades (Gate 2 evidence) | `insert_grading_session` (`:15370`); `answer_grading_card` (`:15544`) | `GET /api/admin/grading/report` (`blind_grading.py`) | ≤40 cards per session | none | pending |
| `standing_offers` (1529), `shared_packages` (2525) | Offer intents with lifecycle; shared trade packages | Route writers | Generation guards; share landing | Per user action | `expires_at`/`revoked_at` columns, no purge | pending |
| `overhauls` (242), `overhaul_offers` (263), `overhaul_roadmaps` (284), `overhaul_attempts` (298) | Team-overhaul runs, offers, roadmaps, send attempts | `overhaul_store.py` | Overhaul UI and resume | Per overhaul run | none | pending |
| `win_now_decisions` (228), `win_now_scenarios` (217) | Win Now trade evidence | `win_now_store.py` | Win Now | Per evaluation | **180 d** (`win_now_store.py:90-101`) | pending |
| **NN? / pending DEC-3** | | | | | | |
| `deck_candidate_sets` (1104) | One `candidates_json` per job: served, ghost and trimmed pool | `save_deck_candidate_set` (`:7340`) | OPE; `eval/scorecard_evidence.py` | 1 row/job; bytes scale with candidates | none | pending (**suspected large**) |
| `trade_policy_shadow` (845) | Candidates rejected by the treatment policy | `save_trade_policy_shadow` (`:6880`) | Policy evaluation | ≤ `policy_shadow_log_cap` rows/job when on | none | pending |
| `bakeoff_runs` (1184) | Per-job arm and config ledger (`config_json` stored whole) | `save_bakeoff_run` (`:7347`) | `bakeoff_readout.sql`; disposition review | 1 row/job | none | pending |
| **NN / history promised indefinitely (C-7)** | | | | | | |
| `elo_history` (1793), `swipe_decisions` (584), `league_board_history` (2019) | Personal Elo snapshots, pairwise votes, board snapshots | `record_elo_snapshot` (`:12657`); `save_ranking_swipes` (`:5921`); `upsert_board_snapshots` (`:12859`) | Trends, Elo rebuild, recap | Per ranking save, changed players only | none (code comment at `:1786-1790` defers compaction) | pending |
| `player_value_history` (1817), `league_roster_history` (1924) | Daily consensus values; weekly roster snapshots with `roster_hash` (`roster_history.py:67`) | `record_value_snapshots` (`:12965`); `upsert_roster_snapshots` (`:12729`) | **Receipts valuation source**; recap; rank quality | Players × 2 formats per day; ~240 rows/league-season (`data-dictionary.md:1353`) | none (ADR-011) | pending |
| **NN / user and account state** (small; one row per entity) | | | | | | |
| `users` (448), `accounts` (2465), `linked_identities` (2478), `member_rankings` (683), `league_preferences` (1467), `asset_preferences` (1496), `user_player_skips` (1775), `recorded_picks` (1616), `notifications` (1657), `app_feedback` (1687), `entitlements` (2547), `subscription_events` (2578), `referrals` (2598), `affiliate_clicks` (2623), `rank_sets` (2648), `rank_set_entries` (2670), `rank_set_adoptions` (2687), `accuracy_scores` (2704), `mock_drafts` (2735), `sleeper_credentials` (2374), `espn_credentials` (2413), `mfl_credentials` (2439), `device_tokens` (2297), `notification_prefs` (2324), `deck_suppressions` (1255), `deck_fatigue_resets` (1279) | Live product, account and billing state | `database.py` / `accounts.py` helpers | Product surfaces; export and deletion | Per user or entity; replace-in-place for `member_rankings` (`:5720,9255,9266`) | Replace or delete on update; billing is append-only | pending (hypothesis: small) |
| **DR / derived-regenerable** | | | | | | |
| `prepared_trade_inventories` (70), `prepared_trade_manifests_v2` (132), `prepared_trade_pages_v2` (161), `prepared_trade_nodes_v2` (177), `prepared_trade_participants` (117) | Silent prepared inventories (v1 envelope; v2 pages and nodes) | `prepared_trade_store*.py` | Find a Trade adoption | Linked teams × inventory bytes (dense synthetic: 15,083,835 B compressed per 12-team inventory, `chunked-storage-plan.md:7`) | **24 h** eligibility; prune (`prepared_trade_store.py:1047`, `prepared_trade_store_v2.py:887`) | pending (rollout last recorded off) |
| `players` (1433), `leagues` (521), `league_members` (625), `trade_block` (644), `draft_picks` (1562) | Provider-synced reference and roster state | Sync paths | Everything | Per league or player | Replace on sync (`:10773,13734,8446,11527`) | pending |
| `usage_week_loads` (1841), `usage_team_weeks` (1853), `usage_player_weeks` (1862) | Usage Trends weekly store | `replace_usage_week` (`:15620`) | Usage Trends | Per NFL week | Week replaced whole | pending |
| `season_forecast_snapshots` (190), `season_projection_snapshots` (197) | Win Now forecast and projection evidence | `win_now_store.py` | Win Now | Per forecast or league | **400 d** (`win_now_store.py:90-101`) | pending |
| `experiment_metric_snapshots` (2274), `archetype_auditions` (1343), `user_taste` (1319) | Rollup; audition state; decayed taste weights | Experiments; `server._audition_statuses`; outcome writes | Experiments; exploration; ranking | Small | GC on read for `user_taste` (`:8013,8032`) | pending |
| **DBG** | | | | | | |
| `deck_diagnostic_snapshots` (1085) | Content-addressed debug JSON per user/job | `save_deck_impressions` path | `load_deck_diagnostics` (owner-scoped) | Per run (local evidence: 7,013,287 B unique per 2,354 rows, `compute-storage-summary.json`, 2026-09-21) | **14 d**, 500 rows per 5-min tick (`database.py:6864`; `server.py:2773`) | **187,416,576 B (2026-09-15, pre-expiry)** |
| **OP** | | | | | | |
| `sessions` (2502) | Durable verified sessions | Auth | Session restore | Per verified device | **90 d idle** (`database.py:14741`; `server.py:2337`) | pending |
| `notification_queue` (2345), `notification_events_log` (2334) | Push queue; push dedup log | Notification system | Push scheduler | Per push | Queue deleted on drain (`:14160`); log: none | pending |
| `deck_replenish_log` (1292), `receipts_grade_runs` (2827) | Weekly replenish marker; grading run ledger (2 rows per run) | Cron | Ops | Per league-week; per run | none | pending |
| `prepared_trade_sweeps` (89), `prepared_trade_targets` (100), `prepared_trade_worker` (123) | Preparation sweep, target and lease state | Prepared store | Prepared runtime | Per sweep × teams | Not pruned by `prune()` (hypothesis — verify) | pending |
| `win_now_jobs` (205), `overhaul_reservations` (322) | Job queue; asset reservations | Win Now; overhaul | Same | Per job | **7 d** for jobs (`win_now_store.py:90-101`) | pending |
| **CFG** | | | | | | |
| `model_config` (2054), `model_config_changes` (2080), `experiments` (2218), `experiment_layers` (2210), `experiment_transitions` (2246), `analytics_segments` (2198) | Knobs and audit; experiment definitions; segments | Admin routes | Everything; readouts; `bakeoff_readout.sql` | Per change | none | pending (hypothesis: small) |

## 5. Non-negotiables, as testable requirements

### 5.1 User events tracking (`user_events` product rows, `identity_links`, `experiment_assignments`, `wrapped_events`)

- **R-E1 Lossless capture.** No sampling, no new drop path and no truncation of any product event.
  Rows may be dropped only by the drop rules that exist today: allowlist misses, the rate limit,
  props-size and PII scrubs, bad envelopes (`analytics_ingest.py:9-17,142-152`) and the
  `user_id='system:api'` obs rows (subject to DEC-1).
- **R-E2 Ingest contract unchanged.** `accepted + deduped + len(rejected) == len(events)` for every
  committed batch (`analytics_ingest.py:13-15`). Response shape, idempotency on `event_id`
  (`database.py:2165`) and the short ingest lock budget (`analytics-platform/hld.md`, KD-12) also stay unchanged.
- **R-E3 Every canon metric is recomputable for any past period** from retained data, with
  identical results. The canon is:
  - funnel v2 stages 0–8 (`analytics_queries.py:406-416`; `context.md:61-71`);
  - DAU/WAU/MAU, activation, TTFV, the retention triangle, churn, the trade-quality funnel and WAT
    (`2026-07-17-analytics-program-plan.md:28-37`; `analytics_queries.py:53-57,402`);
  - the five PFO guardrails (`2026-07-17-pfo-measurement-spec.md:27-33`);
  - all 15 report builders (`analytics_queries.py:435-438`).

  The canon needs row-level props and timestamps (R2 `client_ts`/`dwell_ms`; R3/R4 last screen and errors;
  PFO parses `trades_generated.props.count`, `analytics_queries.py:966-970`), so **a rollup may be added for
  speed but never replaces raw rows** unless the operator decides otherwise per metric.
- **R-E4 Experiment readouts reproduce.** `experiments.readout` scans `user_events` from
  `assigned_at` with no upper bound (`experiments.py:654-657`). Assignments and the events after them
  must stay reachable for every non-draft experiment version.
- **R-E5 Attribution survives.** `identity_links` is retained for as long as any `device:%` event is,
  so pre-auth stitching (`analytics_queries.py:14-18`) gives the same resolved user ids.

### 5.2 Trade history (the NN / trade history group of §4; scope of `deck_impressions` per DEC-2)

- **R-T1 Complete.** Every trade and lifecycle row is retained: served card, outcome, decision,
  pass reason or flag, match, confirmed send, executed trade, link and grade. Deletion and
  anonymization happen only through the account matrix (`accounts.py:593-628`).
- **R-T2 Auditable chain.** Every link resolves: suggestion (`deck_impressions`) → outcomes →
  `trade_decisions.impression_id` → `trade_matches.user_{a,b}_impression_id` → `trade_proposals.impression_id`
  → `sleeper_trades` ⇐ `suggestion_trade_links.{matched,ghost}_impression_id`, plus
  `receipts_grades.impression_id` and `grading_cards.arms_json.current.impression_id`.
- **R-T3 Byte-exact where hashes depend on it.** This covers:
  - frozen JSON (`features_json` core, `valuation_json`, `assets_json`, `trade_proposals.valuation_json`, `sleeper_trades.raw`);
  - identifiers derived by hashing (`trade_hash`, `trade_concept_id` at `trade_policy.py:1036`, `set_hash`, `roster_hash` at `roster_history.py:67`);
  - prepared `payload_sha256`. Re-serialization, key reordering or float reformatting is a failure.
- **R-T4 Product paths unaffected.** Generation, fatigue (30 d, `trade_service.py:410,413`), executed-trade
  matching (14 d lookback, `trade_service.py:693`), receipts grading (14/28/56 d ±3 d,
  `receipts_service.py:95,664`) and Calibration give identical outputs whatever tier a row is in.
  Capture can lag by an unbounded time, so the matcher must find impressions served up to 14 d
  before `traded_at` whenever capture runs.

### 5.3 What "retained" may mean

A row counts as retained in any of three forms:

1. **Hot raw.** In the primary Postgres tables for N days after its timestamp, as the code reads it today.
2. **Lossless cold archive.** Row-for-row, byte-exact copies with a per-row checksum and a manifest per
   ISO week, restorable or queryable on demand. Maximum time-to-query: **≤ 15 min** for one ISO week of one
   table; **≤ 4 h** for full history since 2026-07-18; no operator step beyond starting it (`head-eng` to confirm).
3. **Rollups.** Optional, additive only, for metrics that need hot speed. They are never the source of truth (R-E3).

N ranges (requirement ranges, not choices; DEC-4):

| Data | N range | Reasoning |
|---|---|---|
| `user_events` product rows | **104–180 d** | The longest report window is 90 d (`analytics_queries.py:439`). The churn horizon is 14 d (`:1029`) and the retention triangle 8 weeks (`:1304`). The upper end covers half a season of WoW review without archive reads. Overriding rule: rows any running experiment needs stay hot. |
| `deck_impressions` core and its trade-history children | **70–120 d** | The receipts 56 d window plus ±3 d tolerance plus grading backlog is the floor. Fatigue and suppression need 30 d, matching 14 d. Bake-off readouts since 2026-08-19 (`bakeoff_readout.sql:22-23`) may read the archive within the time-to-query bounds. |

### 5.4 Account export and deletion reach every tier (non-negotiable)

- **R-L1 Export.** `GET /api/account/export` (`server.py:27945`, flag on at `config/features.json:191`)
  returns archived rows exactly as if they were hot, with the same column omissions (`accounts.py:940-993`).
  The route is synchronous under a 120 s timeout (`render.yaml:16`). If archive retrieval cannot fit,
  making it asynchronous is an API-contract change and needs DEC-6.
- **R-L2 Deletion.** `DELETE /api/account` reports success only after the hot, archive and rollup
  tiers are all deleted or anonymized per the matrix (`accounts.py:593-628,696`). This matches
  "A successful deletion removes … activity and usage events" (`web/privacy.html:224-238`). A rollup
  must not let a deleted user's rows be re-identified.
- **R-L3 Obs rows.** `api_request` rows carry the requesting user in `props.user`
  (`api_observability.py:33-36,372-374`) under `user_id='system:api'`. The deletion predicate
  (`accounts.py:754-757`) does not reach them; today only the 30 d purge bounds them. If any design
  keeps obs rows longer than 30 d, deletion must also remove or scrub `props.user`.

## 6. Per large table: retention and fidelity per consumer

All size claims are **hypotheses — verify with the inventory read** unless they cite 2026-09-15.

| Table / slice | Consumers | Raw (hot) | Rollup | Cold archive | Notes |
|---|---|---|---|---|---|
| `user_events` product | Reports, experiments, export/deletion | N_events (104–180 d) | Optional daily per metric | Lossless, indefinite | Six indexes. `ix_user_events_user_id` (`:2143`) is a prefix of `ix_user_events_user_occurred` (`:2160`): redundant-index hypothesis, check Q3 `idx_scan` |
| `user_events` obs (`api_call`/`api_request`) | `report_apihealth` (`:1690`), incident diagnosis | 30 d today | Daily error and volume counts would be new | **DEC-1** | Sampled already (not lossless). The unbounded 6-hourly `DELETE` leaves dead tuples and WAL bursts (`api_observability.py:424-430`). Suspected top-3 by rows |
| `deck_impressions` core cols + `assets_json` | Receipts, matcher, fatigue, Calibration, bake-off, OPE, export | N_deck (70–120 d) | Arm/lane/week counts for readouts | Lossless, indefinite, byte-exact (R-T3) | **244.5 MB on 2026-09-15**, ~9 KB/record, ~910 rows/job, ≥97.4% unlabelled: **DEC-2** |
| `deck_impressions.valuation_json` / `features_json` | Bake-off fit slices (`features_json->'fit'`), audit replay | Same as row | none | Same as row | Not debug: it is a frozen record (`database.py:1038-1083`). Byte-exact |
| `deck_candidate_sets` | OPE, eval | N_deck | Size/hash only | Lossless if DEC-3 = trade history; else per DEC-3 | 1 row/job carrying the full action set: suspected large and unmeasured |
| `deck_diagnostic_snapshots` | Owner-scoped debug | 14 d (code) | none | none (DBG) | Already bounded. Verify steady state against the 187.4 MB pre-expiry figure (2026-09-15) and churn bloat (500 deletes per tick) |
| `deck_outcomes` | All label consumers, `user_taste` | ≥ N_deck | none | Lossless | Small per row. Must stay joinable to archived impressions |
| `trade_impressions` | Training negatives, export | N_deck | none | Lossless unless DEC-10 proves it derivable | Near-duplicate of the `deck_impressions` core; suspected top-5 |
| Prepared tables (5 data + 3 state) | Find a Trade adoption | 24 h eligibility | none | **none** (DR) | Dense synthetic case: 15.1 MB compressed per inventory (`chunked-storage-plan.md:7`, 2026-09-22). Staging and sealed copies coexist during a swap. **Contention:** `trades-pm` task 1 (Find a Trade ≤ 250 ms, up-to-date offers) implies inventories for every linked team. Requirements: an explicit byte budget enforced before write; shed first under disk pressure; the budget is agreed via `head-product`. Sweep and target state retention to be stated |
| `experiment_assignments` | Readout denominator | While the experiment is running + N_events | none | Lossless | Small (hypothesis) |
| `receipts_grades`, `receipts_grade_runs` | Receipts surfaces | Indefinite (append-only design) | none | Lossless | Small (hypothesis). Run ledger is OP |
| `trade_policy_shadow`, `bakeoff_runs` | Policy and bake-off readouts | N_deck | none | Per DEC-3 | `config_json` is stored whole per job (hypothesis: material) |
| `sleeper_trades.raw` | Matcher, organic corpus | Indefinite | none | Lossless, byte-exact | Grows with linked leagues |
| Log/cache tables (`notification_events_log`, `deck_replenish_log`, `sessions`, `notification_queue`, `model_config_changes`, `win_now_jobs`) | Ops | Existing code retention | none | none | Logs without retention need a stated bound. `notification_events_log` dedup needs ≥30 d (`data-dictionary.md:1620`) |
| Index and table bloat (all) | — | — | — | — | Only `deck_impressions` was rewritten (2026-09-15). Steady churn from three sources: the obs purge, diagnostic expiry, and the 24 h prepared turnover. W3 must report `n_dead_tup` and index bytes; the design must state a steady-state bloat allowance |

## 7. Acceptance tests a design must pass

Run on a full restore in a disposable Postgres and again in prod after cutover. "Before" and "after"
are computed on the same data snapshot with no deletion in between. A deletion changes both sides equally.

| ID | Check | Pass |
|---|---|---|
| AT-1 | DAU, WAU, MAU and WAT for every ISO week from 2026-W29 (the week of 2026-07-18) to the last complete week, with demo users included and excluded | 0 difference (lossless) |
| AT-2 | Every funnel-v2 stage count (`report_waterfall`) per weekly cohort; activation, TTFV p50, empty-deck and insult rate; retention triangle; churn list | 0 difference |
| AT-3 | All 15 `VALID_REPORTS` over 3 windows (last 28 d, a 90 d window ending 60 d ago, the oldest 90 d) | Byte-identical JSON, after removing `generated_at` |
| AT-4 | `experiments.readout` for every non-draft experiment version (if more than 20: all decided ones plus a random 20) | Identical arms, n, success, z, p, SRM and verdict |
| AT-5 | Lifecycle chains (R-T2) over all rows | Orphan count per link type after ≤ before. No new orphan |
| AT-6 | Per-row SHA-256 of canonical text over the core columns of `deck_impressions` and the full rows of `deck_outcomes`, `trade_proposals`, `sleeper_trades`, `receipts_grades` (same method as `status.md:13-14`, 2026-09-15). Also recompute `trade_concept_id`, `set_hash` and `roster_hash` | 100% match |
| AT-7 | `scripts/bakeoff_readout.sql` (with the same `:window_start`) and the 2026-08-29 disposition-review and 2026-08-16 corpus queries | Identical result sets |
| AT-8 | Export a synthetic account that has archived rows in every user-keyed table | Archived rows present. Omitted columns stay omitted. Completes within 120 s or DEC-6 |
| AT-9 | Delete that account | 0 rows in any tier, including obs `props.user` if R-L3 applies. Counterparty anonymization unchanged |
| AT-10 | Ingest load at 10× current peak, run while archival or maintenance runs (the KD-12 SM-3 shape) | Invariant holds for 100% of committed batches. Product p95 within noise of baseline |
| AT-11 | Receipts grading, executed-trade matching (capture lag > N_deck), fatigue and Calibration on fixture decks that straddle the hot/archive boundary | Outputs identical to all-hot |
| AT-12 | CI: `pytest backend/tests` (SQLite), `tsc --noEmit`, testid-lint, plus any new archive or rollup readers tested on both dialects | Green |
| AT-13 | Every maintenance, archival or migration statement is bounded (C-2); no exclusive lock exceeds the 120 s statement limit precedent (`release.md:45-47`) | Logged per batch |
| AT-14 | **Headroom** (to be confirmed by `head-eng`, see below) | Holds at cutover and in the weekly projection |

**Headroom target (AT-14), derived from the 2026-09-15 runway logic** (`release.md:55-62`). Projections use Render volume bytes, including the ~0.51 GB non-relation overhead (§3.2).

- **H1 Reserve.** Free space never falls below 20% of the volume (≥ 1,049,342,800 B).
- **H2 Maintenance room.** Above that reserve there is room for the largest relation's total size, so a rewrite or copy can run (C-8).
- **H3 Horizon.** H1 and H2 hold for ≥ 52 weeks at W3-measured weekly growth × 2 (user growth) without operator
  action; a design needing recurring operator action must state the cadence, and more often than monthly fails.
- **H4 Alerting.** A disk-usage signal fires at 70% of the volume. The 2026-09-15 incident reached 98.3% unannounced (`runbook.md:1243`).

## 8. Out of scope

Architecture and storage technology; migration and cutover plan; cost model; Render-managed backups/PITR;
changes to ranking, generation, card counts or analytics semantics. Cutting served cards or sampling events
is already excluded by `db-storage-reduction/scope.md:15` and by R-E1/R-T1 here.

## 9. Decisions needed and handoffs

| ID | Decision | Owner | Evidence / default if undecided |
|---|---|---|---|
| DEC-1 | Do obs `api_call`/`api_request` rows count as "user events tracking"? | Operator | They are written under `user_id='system:api'`, already sampled, purged at 30 d and NON_INTENT (`analytics_queries.py:58-71`). Default: operational (current behavior) |
| DEC-2 | Is every served `deck_impressions` card "trade history", or only cards that reach an outcome, link, match, proposal, grade or Calibration reference? | Operator | ≥97.4% were unlabelled on 2026-09-15. Unlabelled rows still feed receipts, matcher denominators, OPE and bake-off denominators. Dropping them cannot be undone; keeping them can be revisited. Default: all served cards are trade history |
| DEC-3 | Are `deck_candidate_sets`, `trade_policy_shadow` and `bakeoff_runs` trade history or evaluation evidence (which may have a shorter lossless horizon)? | Operator + `analytics-lead` | Default: trade history |
| DEC-4 | N within the §5.3 ranges | Operator, on `head-eng` + `fin-pnl` input | Default: upper bound |
| DEC-5 | Any change to user-visible retention wording (`privacy.html` §5–6) | Operator | Default: none needed if lossless |
| DEC-6 | Export may become asynchronous if archive retrieval exceeds 120 s | Operator (API contract: express bright line) | Default: synchronous |
| DEC-7 | Confirm H1–H4 numbers and the 52-week horizon | `head-eng` | Default: as stated |
| DEC-8 | Clear or refuse any paid component (object storage, etc.); confirm "no disk increase" is absolute | `fin-pnl` via `head-bizops` | Default: no paid component |
| DEC-9 | Prepared-inventory byte budget and shed order versus the ≤ 250 ms Find a Trade goal; does rollout wait for this design? | `trades-pm` via `head-product`, with `head-eng` | Default: prepared data sheds first; no rollout without a budget |
| DEC-10 | Is `trade_impressions` provably derivable, row for row, from `deck_impressions`? | `analytics-lead` + `head-eng` | Default: no, so retain losslessly |
| DEC-11 | May a decided experiment's readout be frozen, or must it always recompute from raw? | Operator | Default: recompute from raw (R-E4) |

**Handoffs.**

- `analytics-lead`: run W3 (§3.4) once the operator's prod-read grant is in force; fill §4; confirm or reject every hypothesis.
- `head-eng`: design and migration against §2 and §5–7; answer DEC-7; route a privacy review of any archive tier.
- `head-bizops` / `fin-pnl`: cost the options; answer DEC-8.
- `head-product` → `trades-pm`: answer DEC-9.
- Operator: answer DEC-1, 2, 3, 4, 5, 6 and 11.
