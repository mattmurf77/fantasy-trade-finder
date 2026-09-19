# PRD — FTF Self-Training Loops (Plan 1: 1A–1E)

> **Purpose:** build-ready functional + technical specification for the five FTF self-training loops. Companion to [`loop-hld.md`](loop-hld.md) (architecture/why) and [`loop-lld.md`](loop-lld.md) (schemas/signatures — normative for all interfaces; this doc references rather than restates them). Covers every requirement, test, and work unit needed for the build to be complete.
>
> **This package is design only.** No code changes accompany it. Build commences on approval via the work breakdown in §8.

---

## Table of Contents
- [1. Scope](#1-scope)
- [2. System architecture](#2-system-architecture)
- [3. Data requirements](#3-data-requirements)
- [4. Schema definitions](#4-schema-definitions)
- [5. Public API](#5-public-api)
- [6. Functional requirements (R1–R20)](#6-functional-requirements-r1r20)
- [7. Testing requirements (T1–T14)](#7-testing-requirements-t1t14)
- [8. Work breakdown for subagent dispatch (WP1–WP9)](#8-work-breakdown-for-subagent-dispatch-wp1wp9)
- [9. Sequencing and dependencies](#9-sequencing-and-dependencies)
- [10. Risk register](#10-risk-register)

---

## 1. Scope

### In scope
- **1A:** weighted action-score metric (pre-registered weights in `model_config`), telemetry rollup job + per-engine-version report, league-state + proposal logging for offline replay (schema now, replay later), feature-flag A/B harness on `config/features.json` (one live variant at a time), automated fairness audit (value-delta distribution bounds; 1-for-1 gate as seed check), quarterly human reward-hacking review checklist.
- **1B:** invite-funnel event schema (nudge shown → invite sent → accepted → activated), weekly viral-coefficient report, nudge-fatigue guardrail (frequency cap + dismiss-rate kill metric).
- **1C:** onboarding step funnel (Sleeper login → league import → first matchup session → first trade suggestion seen), cohort activation reporting, matchups-before-abandon vs matchups-before-value instrumentation.
- **1D:** D7/D30 cohort job, notification A/B slots keyed to league events (riding the shared harness), opt-out guardrail, season-window comparability rule.
- **1E:** cross-client invariant CI checks generated from `docs/cross-client-invariants.md`, per-page TTFA budgets in a checked-in file + deploy-time synthetic check, Render cold-start tracking, per-release persona-walkthrough checklists.
- Client event emission (web/mobile/extension) for the events the server can't observe.
- All docs-sync updates mandated by the root `CLAUDE.md` table (each WP lists its owned docs).

### Out of scope (filed as follow-ups)
- F1: The replay runner over `engine_proposal_log` (schema lands now; runner is a separate plan).
- F2: Auto-actuating guardrails (v1 flags; humans disable flags/nudges/experiments).
- F3: Multi-variant or concurrent experiments (one live variant at a time is a design rule).
- F4: Client-side RUM for TTFA (v1: API synthetic checks + stopwatch in persona walkthroughs).
- F5: Any trade-engine math change (the loop produces those hypotheses; it doesn't ship them).
- F6: Perf gate as deploy blocker (v1 advisory; `--strict` exists for later).

### Constraints (normative)
- **SQLite now / Postgres-swappable:** portable column types, ISO-string timestamps, JSON as TEXT, no dialect-specific SQL; aggregation in Python (existing `load_engine_telemetry` pattern).
- **Three clients:** every client-emitted event is client-tagged via the existing `device_type`/`source` envelope; impressions gain a `client` column.
- **Privacy:** event `props`, snapshots, and deck logs carry Sleeper user IDs + player IDs only — no usernames, display names, tokens, or free text. Ingestion strips undeclared prop keys.
- **Docs sync:** schema → `data-dictionary.md`; routes → `api-reference.md`; flags/keys/config files → `config-reference.md`; cross-client values/enums → `cross-client-invariants.md`; module wiring → `architecture.md` (per root `CLAUDE.md`).

---

## 2. System architecture

```
┌─ Clients ────────────────────────────┐      ┌─ Backend (Flask) ───────────────────────────┐
│ web/js/app.js                        │      │ server.py                                    │
│ mobile/src/api/events.ts (NEW)       │──────►  POST /api/events ──► record_event()        │
│ extension/content.js                 │ batch│        │ (whitelist + prop filter)           │
│  emit: view_detail, shared,          │      │        ▼                                     │
│  nudge shown/dismissed, invite_sent  │      │   user_events (existing, +6 event types)     │
└──────────────────────────────────────┘      │                                              │
                                              │ _run_trade_job ──► log_trade_impressions     │
        config/experiment.json ───────────────►  (+trade_id, job_id, engine_version,         │
        config/features.json    feature_flags │   variant, client)                           │
              │                 + experiments │        └─► loop_logging:                     │
              ▼                               │             snapshot_league_state ─► league_ │
        experiments.variant_for(user) ────────►             state_snapshots (hash-dedup)     │
              │                               │             log_proposal_deck ─► engine_     │
              ▼                               │             proposal_log                     │
        experiment_assignments                │                                              │
                                              │ /api/cron/daily-tick ─► loop_metrics.        │
                                              │   rollup_daily() ─► loop_rollups             │
                                              │   guardrails.check_guardrails()              │
                                              │                                              │
                                              │ GET /api/admin/loop/engine-report            │
                                              │ GET /api/admin/loop/growth-report            │
                                              │ GET /api/admin/loop/activation-report        │
                                              │ GET /api/admin/loop/retention-report         │
                                              │ GET /api/admin/loop/guardrails               │
                                              │ GET /api/admin/loop/experiment               │
                                              └──────────────────────────────────────────────┘
┌─ CI / deploy / human cadence ────────────────────────────────────────────────────────────┐
│ .github/workflows/loop-checks.yml ─► backend/scripts/check_invariants.py + pytest        │
│ post-deploy ─► backend/scripts/synthetic_check.py  vs config/perf-budgets.json           │
│ per release ─► backend/scripts/fairness_audit.py --strict ; persona-walkthroughs.md      │
│ quarterly  ─► docs/loop-reviews/quarterly-reward-hacking.md                              │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Data requirements

### 3.1 Existing data (consumed, unchanged)
| Source | Used by | Notes |
|---|---|---|
| `user_events` + `record_event()` | all loops | gains new event types; envelope unchanged |
| `trade_decisions`, `trade_matches` | 1A | like/pass + match conversion |
| `users.signup_at`, `users.invited_by`, `users.last_active_at` | 1B, 1C, 1D | cohorting + invite attribution |
| `swipe_decisions` | 1C | matchup counts (`decision_type='rank'`) |
| `notification_prefs`, `notification_events_log` | 1D | opt-out + per-kind delivery |
| `member_rankings`, `league_members`, `league_preferences`, `draft_picks`, `model_config`, flags | 1A snapshots | assembled from data `_run_trade_job` already loads |
| `backend/profile_session_init.py` measurements | 1E | seeds `session_init_*` budgets |

### 3.2 NEW data to be created
| Artifact | Kind | Created by |
|---|---|---|
| `league_state_snapshots`, `engine_proposal_log`, `experiment_assignments`, `loop_rollups` tables | DB | WP1 |
| `trade_impressions` columns: `trade_id`, `job_id`, `engine_version`, `variant`, `client` | DB ALTER | WP1 |
| 6 new `user_events` types (see LLD taxonomy) | events | WP6 (server), WP7 (clients) |
| New `model_config` keys (`action_w_*`, `fairness_audit_*`, `nudge_*`, `retention_optout_kill_delta`, `loop_min_n`) | config | WP1 (seed) |
| `config/experiment.json`, `config/invariants.json`, `config/perf-budgets.json` | config files | WP3 / WP8 / WP8 |
| `docs/loop-reviews/quarterly-reward-hacking.md`, `docs/release-checklists/persona-walkthroughs.md` | docs | WP5 / WP9 |

### 3.3 Volume expectations
Current traffic is cold-start thin. All reports must carry `n` and a `thin` flag (`loop_min_n`); guardrails stay silent below it. Nothing in this design assumes volume before the Aug–Dec season.

---

## 4. Schema definitions

**Normative source: [`loop-lld.md`](loop-lld.md)** — § New tables (column-level definitions of `league_state_snapshots`, `engine_proposal_log`, `experiment_assignments`, `loop_rollups`, including `payload_json` and `deck_json` contracts), § Altered tables (`trade_impressions`), § Event taxonomy additions, § Config files (`experiment.json`, `invariants.json`, `perf-budgets.json` shapes). Build agents implement those verbatim; deviations require updating the LLD in the same commit.

Key uniqueness/idempotency contracts (restated because they're load-bearing):
- `league_state_snapshots.snapshot_hash` UNIQUE → snapshot writes are INSERT-OR-IGNORE.
- `engine_proposal_log.job_id` UNIQUE → one row per generation job.
- `experiment_assignments` UNIQUE`(experiment_key, unit_type, unit_id)` → sticky assignment.
- `loop_rollups` UNIQUE`(loop, metric, period, period_start, dims_json)` with canonical (sorted-keys) `dims_json` → re-running a rollup replaces, never duplicates.

---

## 5. Public API

**Normative source: [`loop-lld.md`](loop-lld.md)** § Function signatures and § API routes. Summary of the surface:

- **Python:** `loop_logging.{current_engine_version, current_config_hash, snapshot_league_state, log_proposal_deck}`; `experiments.{live_experiment, variant_for, record_exposure, flag_with_experiment}`; `loop_metrics.{rollup_daily, action_score, season_window, engine_report, growth_report, activation_report, retention_report}`; `guardrails.check_guardrails`.
- **HTTP:** `POST /api/events`; `GET /api/admin/loop/{engine-report, growth-report, activation-report, retention-report, guardrails, experiment}`; extended `POST /api/cron/daily-tick`.
- **CLI:** `fairness_audit.py --days N [--strict]`; `check_invariants.py`; `synthetic_check.py --host H [--strict]`.

---

## 6. Functional requirements (R1–R20)

### 1A — trade-engine quality
- **R1. Pre-registered action score.** Weights `action_w_dismiss/view/save/share` are seeded into `model_config` (defaults 0/1/3/8) and read at rollup time. The quarterly-review governance rule is documented in the reward-hacking checklist and config-reference.
- **R2. Attributable impressions.** Every impression row written after the migration carries non-null `trade_id`, `job_id`, `engine_version`, `client` (and `variant` when an experiment is live). `engine_version` is a pure function of active flags; `config_hash` changes whenever effective `model_config`/flags change.
- **R3. State snapshots.** Each generation job writes (or dedup-reuses) a `league_state_snapshots` row conforming to the payload contract, containing zero usernames/display names, assembled without additional DB reads beyond what `_run_trade_job` already loads.
- **R4. Proposal log.** Each job writes exactly one `engine_proposal_log` row linking snapshot → ordered deck (deck_json contract), sufficient for a future replay runner to re-generate decks from frozen state with no other inputs. Demo league excluded.
- **R5. Per-engine-version report.** `GET /api/admin/loop/engine-report?days=N` returns, per `(engine_version, variant)`: decks, impressions, like/view/share/pass counts, `action_score_per_deck`, fairness summary (p10, share below floor), match conversion, and `thin` flags.
- **R6. Fairness audit.** `fairness_audit.py` computes the value-delta (fairness-score) distribution over the window's decks and asserts the four bounds from the LLD (`min_p10`, `floor` + `max_below_floor_pct`, `1for1_floor` seed check). `--strict` exits 1 on breach (release gate); the same checks run daily via `check_guardrails`.
- **R7. Reward-hacking review.** `docs/loop-reviews/quarterly-reward-hacking.md` exists with the 5-step checklist and a dated sign-off table; `action_w_*` changes require a checklist entry.

### Experiment harness (1A/1B/1D shared)
- **R8. One live variant.** `config/experiment.json` holds exactly one experiment object; loader raises on malformed config or `status` other than `off`/`live`. With `status: "off"`, all behavior is identical to today.
- **R9. Deterministic, sticky assignment.** `variant_for(unit_id)` is a pure hash of `(salt, unit_id)` — same answer in every process and across restarts; first behavioral exposure records into `experiment_assignments`. `flag_with_experiment` overlays only the targeted flag; all other flags resolve unchanged.

### Rollups (shared)
- **R10. Idempotent daily rollup.** `rollup_daily()` runs inside `/api/cron/daily-tick`; running it twice for the same day yields identical `loop_rollups` contents. Every metric in the LLD's pre-registered metric table is produced with its declared dims; all rows carry `n`.

### 1B — growth
- **R11. Invite funnel + viral coefficient.** Funnel events (`invite_nudge_shown/dismissed`, `invite_sent`; accepted via `users.invited_by`; activated via `ranking_complete_first_time` ≤14d post-signup) roll up weekly; `growth_report` returns per-week stage counts, conversions, and `k = invites_per_weekly_active × accept_rate × activation_rate`.
- **R12. Nudge-fatigue guardrail.** The server suppresses invite-nudge surfacing beyond `nudge_max_per_user_per_week` (counted from `invite_nudge_shown` events); `check_guardrails` flags trailing-14d dismiss rate > `nudge_dismiss_kill_rate`.

### 1C — activation
- **R13. Cohort funnel report.** `activation_report` returns, per signup-week cohort: stage-reached counts for the 4 stages (signup → `league_synced` → first `trio_swipe` → first `trade_impressions` row), activation rate (stage 4 within 14 days), built entirely from existing server-side data (no new client emission).
- **R14. Matchups-before-X.** The report includes p25/p50/p75 of rank-decision counts at first impression (`matchups_before_value`) and at abandonment (`matchups_before_abandon`: users with no impression and ≥14d inactivity), per cohort.

### 1D — retention
- **R15. D7/D30 cohorts + season windows.** `retention_report` computes D7/D30 per signup-week cohort once horizons close, tags every row with `season_window`, and never aggregates or compares across windows (rows grouped by window; no cross-window deltas in the payload).
- **R16. Notification A/B + opt-out guardrail.** Push dispatch consults `variant_for` when a live experiment targets notifications; `variant` rides `push_sent` props. Per-variant open and opt-out rates are reported; `check_guardrails` flags treatment opt-out exceeding control by > `retention_optout_kill_delta`.

### 1E — UX / perf / consistency
- **R17. Invariant CI.** `config/invariants.json` covers every machine-checkable row of `docs/cross-client-invariants.md` (tier colors, position colors, gating thresholds, K-factor defaults, scoring-format strings, fairness `×100` rendering, shared copy strings); `check_invariants.py` passes on the current repo and fails (exit 1, naming the invariant id + file) when any listed location drifts; `.github/workflows/loop-checks.yml` runs it plus pytest on push/PR. Non-regexable rows appear as visible SKIPPED entries, not silent omissions.
- **R18. Perf budgets + synthetic check + cold start.** `config/perf-budgets.json` is checked in with API, client-TTFA, and cold-start budgets; `synthetic_check.py --host` probes the API budgets post-deploy and prints a budget table (advisory by default, `--strict` gates); the server records one `server_cold_start` event (boot_ms, commit) on first request after boot, rolled up as p50/p95.

### Cross-cutting
- **R19. Client ingestion with PII defense.** `POST /api/events` accepts batches ≤50, rejects non-whitelisted event types, strips prop keys not declared for the type, stamps client tags from existing headers, and returns `{accepted, rejected}`. All three clients emit their LLD-assigned events through it, fire-and-forget (event failures never break UX).
- **R20. Portability + regression.** All new schema/queries run unmodified on SQLite and Postgres (portable types, Python aggregation); the existing pytest suite continues to pass; with `experiment.json` off and before any client release, all existing behavior is byte-for-byte unchanged except the additive logging.

---

## 7. Testing requirements (T1–T14)

New tests live in `backend/tests/` (pytest, in-memory/temp SQLite; mirrors existing suite style).

| Test | Description |
|---|---|
| T1 | `action_score`: hand-built counts × default weights → expected value; weight change in `model_config` reflected without restart |
| T2 | Impression enrichment: run a synthetic generation job → impressions carry `trade_id`/`job_id`/`engine_version`/`client`; `engine_version` flips correctly when flags flip (`legacy`/`v2`/`v3+three_team`) |
| T3 | Snapshot dedup + privacy: same state twice → one row; payload contains no `username`/`display_name` keys anywhere (recursive assert); changed ranking → new hash |
| T4 | Proposal log: one row per job (UNIQUE job_id), deck_json round-trips to the served deck order |
| T5 | Experiments: `variant_for` deterministic across instances; split within ±3pp over 10k synthetic units; assignment sticky (INSERT OR IGNORE); malformed config raises; `status: off` → `flag_with_experiment` ≡ `flag_enabled` for all keys |
| T6 | Rollup idempotency: seed fixtures → `rollup_daily(d)` twice → identical `loop_rollups`; dims_json canonical ordering |
| T7 | Growth math: synthetic funnel fixture → stage counts and `k` match hand-computed values; dismiss-rate guardrail breaches at the threshold and respects `loop_min_n` |
| T8 | Activation funnel: fixture users at each stage → correct stage-reached counts, 14-day activation window honored, matchups-before-value/abandon percentiles correct |
| T9 | Retention: fixture cohorts → D7/D30 correct; rows tagged with `season_window`; report contains no cross-window comparison; unclosed horizons excluded |
| T10 | Guardrails: fairness fixture violating each of the four bounds (incl. a 1-for-1 card below `1for1_floor`) → corresponding breach dicts; opt-out delta breach per variant |
| T11 | Invariants checker: passes against the real repo; a temp-dir fixture with one mutated tier color → exit 1 naming the invariant; zero-match pattern → failure (anti-rot) |
| T12 | `/api/events`: batch accepted with client tags; unknown event_type rejected; undeclared prop keys stripped; >50 batch rejected; unauthenticated → 401 |
| T13 | Fairness audit CLI: synthetic proposal-log fixture → report numbers match hand calc; `--strict` exit codes correct on clean vs breached data |
| T14 | Regression: full existing pytest suite passes; with experiment off, `GET /api/trades` card payloads are unchanged vs pre-build snapshot |

---

## 8. Work breakdown for subagent dispatch (WP1–WP9)

Owned files are **strictly disjoint** across WPs — a file appears in exactly one WP. Directories may be shared; files may not. Each WP lists its docs-sync obligations per the root `CLAUDE.md` table.

### WP1 — Schema + config-key foundations
- **Objective:** all new tables, `trade_impressions` ALTERs, new `_MODEL_CONFIG_DEFAULTS` keys, and DB helper functions (`insert_*`/`load_*` for the four new tables; enrich `log_trade_impressions` signature with the new columns).
- **Owned files:** `backend/database.py`, `docs/data-dictionary.md`.
- **Dependencies:** none.
- **Steps:** define 4 tables per LLD → add idempotent `_migrate_db()` ALTERs → seed new `model_config` keys → extend `log_trade_impressions(user_id, league_id, cards, *, trade_meta)` to write the new columns (callers updated in WP6) → write loop read/write helpers (Python-side aggregation only) → update data-dictionary (4 new tables, impressions columns, user_events taxonomy rows).
- **Acceptance:** fresh DB creates all tables; existing DB migrates idempotently (run twice); helpers round-trip on SQLite; no dialect-specific SQL (grep for `json_` / `ON CONFLICT`); data-dictionary updated.
- **Effort:** M (~half day).

### WP2 — Proposal/state logging + engine versioning (1A)
- **Objective:** `backend/loop_logging.py` per LLD signatures; engine identity derivation.
- **Owned files:** `backend/loop_logging.py` (NEW), `backend/trade_service.py` (expose effective-config accessor `effective_engine_identity()` returning the flag/config inputs `loop_logging` hashes).
- **Dependencies:** WP1.
- **Steps:** implement `current_engine_version` (fixed modifier-flag order documented in module docstring) → `current_config_hash` → `snapshot_league_state` (canonical JSON, sha256, insert-or-ignore) → `log_proposal_deck` → privacy assertion helper (`_assert_no_pii(payload)`) used by both writers.
- **Acceptance:** R2 (version derivation), R3, R4 satisfiable in isolation with a fake DB session; T3/T4 fixtures pass; demo-league exclusion honored.
- **Effort:** M.

### WP3 — Experiment harness (shared)
- **Objective:** `backend/experiments.py` + `config/experiment.json` + experiment-aware flag resolution.
- **Owned files:** `backend/experiments.py` (NEW), `config/experiment.json` (NEW), `backend/feature_flags.py`, `docs/config-reference.md`.
- **Dependencies:** WP1 (assignments table).
- **Steps:** config loader + validation per LLD → deterministic bucketing → `record_exposure` → `flag_with_experiment` in `feature_flags.py` (delegating to `experiments`; plain `flag_enabled` untouched) → document the file, keys, and one-live-variant rule in config-reference (plus the WP1 `model_config` keys and WP8 config files — this WP owns the whole config-reference update; coordinate content from those WPs' specs in the LLD).
- **Acceptance:** R8, R9; T5 passes; with `status: "off"` a full-suite run is behaviorally identical to pre-WP3.
- **Effort:** M.

### WP4 — Rollups, reports, guardrails (1A–1D compute)
- **Objective:** `backend/loop_metrics.py` and `backend/guardrails.py` per LLD: `rollup_daily`, the five report builders, season windows, all metric definitions, all guardrail checks.
- **Owned files:** `backend/loop_metrics.py` (NEW), `backend/guardrails.py` (NEW).
- **Dependencies:** WP1 (tables), WP3 (variant dims), WP2 (engine_version values; can develop against fixtures in parallel once WP1 lands).
- **Steps:** season-window table + helper → per-loop metric builders (joins per LLD metric table, incl. trade_id join with legacy set-equality fallback) → idempotent upsert (delete+insert on unique key) → report builders reading `loop_rollups` (not raw tables, except current-window guardrails) → `check_guardrails` with `loop_min_n` silence rule.
- **Acceptance:** R5, R10, R11 (report math), R13–R16 (compute side); T1, T6–T10 pass.
- **Effort:** L (~1 day). The largest WP — split internally by loop if dispatched to two agents (metrics file vs guardrails file).

### WP5 — Fairness audit + reward-hacking review (1A checker side)
- **Objective:** release-gate fairness audit CLI and the quarterly human checklist.
- **Owned files:** `backend/scripts/fairness_audit.py` (NEW), `docs/loop-reviews/quarterly-reward-hacking.md` (NEW), `docs/adr/` new ADR ("behavioral reward + pre-registered weights + one-live-experiment").
- **Dependencies:** WP1, WP2 (reads proposal log).
- **Steps:** `run_audit` per LLD (reads `fairness_audit_*` from `model_config`) → CLI with `--days/--strict` → checklist doc with sign-off table → ADR recording the three non-obvious decisions and their alternatives.
- **Acceptance:** R6, R7; T13 passes; `--strict` is documented in the release checklist (WP9 references it).
- **Effort:** S–M.

### WP6 — Server wiring + loop API routes
- **Objective:** every `backend/server.py` change: `POST /api/events` (whitelist + prop filter per LLD), six `/api/admin/loop/*` routes, daily-tick extension, `_run_trade_job` call-sites for `loop_logging` + enriched `log_trade_impressions` (job_id mint, client tag from session headers, `record_exposure` at deck serve), invite-nudge frequency cap, `server_cold_start` event, push-dispatch variant threading.
- **Owned files:** `backend/server.py`, `docs/api-reference.md`, `docs/architecture.md`.
- **Dependencies:** WP1–WP4.
- **Steps:** ingestion route → admin routes (thin: jsonify the WP4 builders, existing admin error-handling style) → daily-tick hook → trade-job call-sites → nudge cap check (count `invite_nudge_shown` for user, trailing 7d) → cold-start event (module-level boot timestamp; first-request flag) → api-reference (all new routes + `/api/events` body schema) → architecture.md (new modules in the table + data-flow diagram additions).
- **Acceptance:** R12 (cap half), R18 (cold-start half), R19; T2, T12 pass; `GET /api/admin/engine-metrics` unchanged (T14 regression).
- **Effort:** L.

### WP7 — Client event emission (web / mobile / extension)
- **Objective:** clients emit `trade_card_view_detail`, `trade_card_shared`, `invite_nudge_shown/dismissed`, `invite_sent` through `POST /api/events`, batched and fire-and-forget.
- **Owned files:** `web/js/app.js`, `mobile/src/api/events.ts` (NEW), `mobile/src/components/TradeCard.tsx`, `mobile/src/screens/LeagueScreen.tsx`, `extension/content.js`.
- **Dependencies:** WP6 (route live).
- **Steps:** shared mobile helper (`events.ts`: queue, flush on batch-of-10/foreground, silent failure) → web inline equivalent in `app.js` → hook card-detail expand + share actions in both → nudge surfaces (cold-start nudge component, league tab) → extension: `invite_sent`/share only if surfaces exist, else no-op with comment.
- **Acceptance:** events arrive with correct `device_type`/`source` per client; UX unaffected when the endpoint is down (airplane-mode manual check on mobile); event types/props match the LLD taxonomy exactly.
- **Effort:** M.

### WP8 — 1E invariants CI + perf budgets (build FIRST — no dependencies, cheapest win)
- **Objective:** machine-readable invariants manifest + checker + CI workflow; perf-budget file + synthetic check.
- **Owned files:** `config/invariants.json` (NEW), `config/perf-budgets.json` (NEW), `backend/scripts/check_invariants.py` (NEW), `backend/scripts/synthetic_check.py` (NEW), `.github/workflows/loop-checks.yml` (NEW), `docs/cross-client-invariants.md`.
- **Dependencies:** none (this is why it goes first).
- **Steps:** walk every section of `cross-client-invariants.md`, pin each value's location with a real regex against current source (manual-check entries for unpinnable rows) → checker per LLD (zero-match = fail) → run against repo until green → workflow (checker + pytest) → budgets file seeded from `profile_session_init.py` measurements → synthetic probe script → update `cross-client-invariants.md` header: manifest is the machine source; doc remains the human index; new event types + variant enums appended (content supplied by WP1/WP3 specs).
- **Acceptance:** R17, R18 (budget half); T11 passes; CI green on current main; intentionally mutating one client color in a branch turns CI red.
- **Effort:** M.

### WP9 — Tests, persona checklists, docs closeout
- **Objective:** the T1–T14 suite, persona walkthrough checklist, glossary/runbook sync.
- **Owned files:** `backend/tests/test_loop_metrics.py`, `backend/tests/test_loop_logging.py`, `backend/tests/test_experiments.py`, `backend/tests/test_loop_api.py`, `backend/tests/test_invariants_checker.py` (all NEW), `docs/release-checklists/persona-walkthroughs.md` (NEW), `docs/glossary.md`, `docs/runbook.md`.
- **Dependencies:** all prior WPs.
- **Steps:** implement T1–T14 → persona checklist per LLD (3 personas × 3 clients, TTFA stopwatch column referencing perf budgets; includes "run `fairness_audit.py --strict`" as a release step) → glossary (action score, viral coefficient, season window, engine version, snapshot hash, thin flag) → runbook (what to do on each guardrail breach; how to start/stop an experiment; how to legitimately change an invariant).
- **Acceptance:** full pytest green; every R has at least one covering T or an explicit manual-check note in the persona checklist.
- **Effort:** M–L.

---

## 9. Sequencing and dependencies

```
Group 0 (now, parallel):   WP8 (1E CI + budgets)        ← no deps, cheapest win
                           WP1 (schema foundations)

Group 1 (after WP1):       WP2 (logging)   WP3 (experiments)     [parallel]

Group 2 (after WP1–3):     WP4 (rollups/reports/guardrails)
                           WP5 (fairness audit)  [parallel with WP4 once WP2 lands]

Group 3 (after WP2–4):     WP6 (server wiring + routes)

Group 4 (after WP6):       WP7 (client emission)

Group 5 (last):            WP9 (tests + checklists + docs closeout)
```

**Critical path:** WP1 → WP2/WP3 → WP4 → WP6 → WP7 → WP9. WP8 and WP5 hang off the side. Estimated wall time with parallel subagents: ~3 working days; serial: ~6–7.

**Calendar alignment (from the spec):** WP8 + the WP1 weight pre-registration are this-month (June) work; everything through WP7 should land before August so the loops read real traffic during the Aug–Dec season. Loop state (HANDOFF/NEXT/CHANGELOG) lives in `living-memory/` per the PGA discipline.

---

## 10. Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| Telemetry too thin to read for months (cold start) | High (certain) | `n` + `thin` flags everywhere; guardrails silent below `loop_min_n`; escalation rule: thin data → no ship. The loops' job pre-season is to *accumulate*, not conclude |
| Action-score reward hacking (flashy-lopsided proposals win) | High | Fairness audit bounds (R6) + quarterly human review (R7) are first-class deliverables, not afterthoughts; weights pre-registered before any optimization |
| `dims_json` uniqueness breaks if key ordering varies | Medium | Canonical sorted-keys serialization enforced in one helper; T6 asserts it |
| Snapshot payloads bloat the DB on busy leagues | Medium | Hash dedup (states change slowly between jobs); `schema_version` allows a slimmer v2; monitor table size in runbook |
| Invariant regexes rot as client code refactors | Medium | Zero-match = CI failure (anti-rot rule, T11); manual-check entries visible as SKIPPED |
| `server.py` (~6.4k lines) merge conflicts | Medium | All `server.py` edits owned by exactly one WP (WP6); other WPs expose functions for it to call |
| Experiment salt reuse correlates assignments across experiments | Low | Loader requires a fresh salt per experiment_key; runbook documents it |
| Render cold starts pollute synthetic perf numbers | Medium | Cold-start budgeted separately; synthetic check medians over 3 probes; advisory in v1 (F6) |
| Postgres swap breaks delete+insert upsert atomicity | Low | Wrap upsert in a transaction (SQLAlchemy `begin()`); no dialect-specific conflict clauses anywhere |
| Client event spam / abuse of `/api/events` | Low | Session auth, 50/batch cap, whitelist + prop stripping; events are operator-owned product data, no third parties |
| Notification A/B raises opt-outs before guardrail reads | Medium | `min_runtime_days` + opt-out delta guardrail checked daily, not at experiment end; humans can kill anytime |

---

## Sign-off

Approval of this PRD (implicit by dispatching WP8 + WP1) starts the build. Every WP must leave the repo green (pytest + invariants checker once WP8 lands) and its owned docs updated in the same change.
