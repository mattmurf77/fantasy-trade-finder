# HLD — Receipts

**Date:** 2026-08-21 · **Parent:** [PLAN.md](PLAN.md) · **Child:** [LLD.md](LLD.md) · [PRD.md](PRD.md)

---

## Table of Contents
- [1. Context & goals](#1-context--goals)
- [2. Architecture overview](#2-architecture-overview)
- [3. Data model & flow](#3-data-model--flow)
- [4. Key design decisions](#4-key-design-decisions)
- [5. Cross-cutting concerns](#5-cross-cutting-concerns)
- [6. Risks & open questions](#6-risks--open-questions)

---

## 1. Context & goals

Grade past trade suggestions against subsequent consensus value movement, with the
serve-time record as the immutable prediction. Requirements it must satisfy:

- **Honesty:** market drift must not read as engine skill; selection effects disclosed;
  grades immutable (PLAN §3).
- **Isolation:** zero engine footprint (PLAN §7.3); grading failure can never touch
  serving, snapshots, or notifications.
- **Operability:** runs on the free-plan single-worker Render web service
  (`--workers 1`, `render.yaml:16`); deploy-free kill switches; idempotent under
  crashes and double-fires.
- **Scale envelope:** thousands of impressions, not millions — the binding constraints
  are statistical (n per cell) and data-coverage, not throughput.

**The question boundary:** `suggestion_trade_links` + `suggestion_telemetry.py` answer
*"did a suggested trade EXECUTE?"* (asset-set matching against captured Sleeper trades).
Receipts answers *"did the VALUE move as the suggestion implied?"*. Different question,
different table family; Receipts never writes telemetry tables.

## 2. Architecture overview

```
serve time (exists today)              grade time (new)                    read time (new)
─────────────────────────              ────────────────                    ───────────────
_run_trade_job                         POST /api/cron/receipts-grade       ReceiptsScreen (mobile)
 └ _log_deck_signal_impressions          (X-Cron-Secret · 202 + daemon       └ GET /api/league/<id>/receipts
   (server.py:~4130-4230)                 thread · single-flight)               (session auth · flag receipts.screen
 └ deck_impressions row                + daily-tick internal guard              · viewer-scoped · ghosts excluded
   = FROZEN prediction                   (same function, roster_history        · min-n gate · all 3 windows)
                                          three-trigger pattern)            operator
daily consensus snapshots (exists)     + scripts/receipts_backfill.py        └ GET /api/admin/receipts/metrics
 /api/cron/value-snapshot (:19493)        (operator loop until drained)         (X-Cron-Secret · per-cell n +
 + hourly-tick fallback (:19166)          │                                      Wilson intervals · served-vs-ghost)
 └ player_value_history rows              ▼
                                       backend/receipts_service.py (new)
                                        reads:  deck_impressions, player_value_history
                                        writes: receipts_grades (append-only),
                                                receipts_grade_runs (run ledger)
```

Components:
- **`backend/receipts_service.py` (new, leaf):** grader + read queries. Imports
  `database` + `feature_flags` + `pick_values.parse_generic_pick_id` (import-safe by
  design) only — no engine modules (mirrors the `suggestion_telemetry.py` leaf pattern,
  its module docstring; exact contract in LLD §1).
- **`server.py`:** three thin routes + the daily-tick guard call.
- **`mobile/src/screens/ReceiptsScreen.tsx`:** root-stack push (FeedbackFAB rule #188);
  renders one payload containing all windows.

## 3. Data model & flow

Entities (full DDL in LLD §3):

- **`deck_impressions` (read-only)** — the prediction. Grader inputs: `impression_id`,
  `served_at`, `assets_json`, `league_id`, `user_id`, `is_ghost` + taxonomy slice keys
  (`shape_bucket`, `archetype`, `basis`, `model_arm`, `policy_version`).
  `features_json` is used for **slicing only, never valuation** (D-2).
- **`player_value_history` (read-only)** — the yardstick. Daily
  `(player_id, scoring_format, snapshot_date) → consensus_value`, denormalized at
  snapshot time so engine config changes cannot rewrite history
  (`backend/database.py:1294-1296`).
- **`receipts_grades` (new, append-only)** — one row per
  `(impression_id, window_days, grader_version)` reaching a terminal status
  (`graded` | `ungradeable/<reason>`). Carries both sides' serve/window sums, `edge`,
  `edge_pct`, per-asset detail, coverage, and denormalized slice keys.
- **`receipts_grade_runs` (new)** — run ledger (counts, duration, cap-hit), the
  observability surface for a job with no UI.

**Primary flow:** daily trigger → work queue = telemetry-era impressions with an elapsed
window and no grade row at the current grader version → batched snapshot prefetch → pure
per-impression grading → insert-or-ignore. **Read flows:** user route filters
`user_id = viewer AND is_ghost falsy`, dedupes re-serves by `(league_id, trade_hash)`
keeping the earliest, gates the headline at min-n; admin route aggregates per taxonomy
cell with intervals.

## 4. Key design decisions (mini-ADRs)

| # | Decision | Rationale | Rejected alternative |
|---|---|---|---|
| D-1 | **Metric = swap edge** (receive-delta − give-delta, consensus units; `edge_pct` vs serve-time package midpoint; win share vs an explicit 50% null) | The give side is the market control. Precisely: uniform **multiplicative** drift `m` yields `edge = m · (serve-time imbalance)` — ≈0 for fairness-gated, near-balanced packages; uniform **additive** drift `d` yields `edge = d · (n_receive − n_give)` — exactly 0 for equal-cardinality shapes. Residual shape effects (asymmetric cardinality, side-size beta) are disclosed per shape cell, not hidden. A standalone acquire-side % measures the market, not the engine | Acquire-side %: banned as standalone (PRD §4.4). Value space is exponential in Elo (`elo_to_value`, `backend/trade_service.py:1267`), so per-asset percentages don't compose |
| D-2 | **Serve anchor = `player_value_history` at serve date — never `features_json` values** | Frozen `give_value`/`receive_value` may be personal-basis (`user_value_basis`, `backend/server.py:4159`) and are engine units; comparing them to later consensus manufactures fake movement | Grading from frozen card values: fails whenever `user_value_basis='personal'` |
| D-3 | **Append-only + `grader_version` (string, `'receipts-1'`)** — unique `(impression, window, version)`, reads pin max version, superseded rows retained, regrades footnoted on-screen | Corrections without goalpost-moving; precedent `SCORER_VERSION = "fit-1"` (`backend/trade_gen_fit.py:43`) | UPDATE-in-place (destroys the audit trail); never-fix (wrong screen forever) |
| D-4 | **202 + daemon thread + single-flight + batch cap** for the cron endpoint | Single gunicorn worker (`render.yaml:16`); precedent `cron_players_refresh` (`backend/server.py:19512-19531`) | Inline grading (blocks all traffic); Celery/queue infra (over-scaled) |
| D-5 | **Ghosts graded identically, internal-only; never in user payloads** | Free served-vs-ghost control read; but surfacing withheld suggestions leaks the holdout and invites "why didn't you show me?". Bounded cohort (PLAN §3.5) | Skipping ghosts (loses the only selection-effect control); showing them (trust harm) |
| D-6 | **User surface is viewer-scoped** (own impressions only), league-wide aggregate deferred | Other managers' decks are private; a league aggregate at n≈5 is reverse-engineerable. PLAN Q-2 for later | League-wide track record v1 |
| D-7 | **Picks contribute Δ=0; pick-majority sides ungradeable; per-asset flags + coverage disclosure.** Pick weights for coverage/pick-share come from a value-unit table **frozen inside the grader** (versioned under `grader_version`) — never read live from `GENERIC_PICK_SEEDS` | Pick prices are static code seeds repriced by commits (D-084) — grading them, or even weighting by them live, grades deploys: a seed repricing would flip the same impression between graded and pick_majority under one grader version | Grading picks from seeds (phantom moves on deploy days); excluding pick trades entirely (kills too much cohort) |
| D-8 | **Pool-floor imputation for players absent at window date** (present at serve), flagged `imputed_floor` | A cratered player falls out of the snapshot pool; marking him ungradeable deletes our worst outcomes — survivorship bias that flatters the engine | Ungradeable-on-missing (silently biased); carrying last-known value (understates busts) |
| D-9 | **Trigger = dedicated cron endpoint + daily-tick internal guard**, render.yaml cron optional | `roster_history` three-trigger precedent (`backend/database.py:1320-1336`); value-snapshot's "provisioned cron" turned out to be fictional (commit `1e50d3e`) — the guard is what actually fires | Blueprint-only cron (launch coupled to render.yaml sync risk) |
| D-10 | **Taxonomy artifact of record = `docs/plans/shared/trade-shape-taxonomy.md`**; receipts-local `TAXONOMY_VERSION` constant stamped per row; Python mirror module proposed as 1.2.0 direction, not v1 | Three-way co-ownership already anchored on the doc; a code module is a governance change needing sibling sign-off (PLAN §7.1) | New `backend/trade_shape_taxonomy.py` now (draft A's proposal — carried as recommendation) |
| D-11 | **No composite `shape_key` string** — store the individual taxonomy columns | Cells compose at read time from denormalized columns; a composite key freezes one cell definition and bloats cardinality | Draft A's `"2x1\|consolidate\|pick:0\|…"` key |

## 5. Cross-cutting concerns

- **Failure isolation:** dedicated endpoint (value-snapshot isolation rationale,
  `backend/server.py:19497-19502`); grader exceptions bounded per-impression (one bad row
  logs + continues); snapshot gaps degrade to `ungradeable/missing_snapshot`, never block
  the run; screen degrades to its empty state on API failure.
- **Idempotency/concurrency:** structural — work queue is defined by the absence of a grade
  row at the current version; unique constraint + insert-or-ignore; single-flight lock; a
  crash loses at most one batch's progress. Render free-instance spin-down mid-run is the
  same case: completed inserts stand, the run's start ledger row stays unmatched (the kill
  marker), the next trigger resumes. Same pattern family as `uq_value_snapshot`.
- **Observability:** `receipts_grade_runs` ledger — a start row at run begin and a
  completion row at run end, both append-only, so a killed run is visible as an unmatched
  start; `receipts_grade_run` server analytics event; `remaining_resolvable`
  (eligible-and-resolvable-now, excluding retry-pending) precomputed into every cron 202
  response.
- **Security/trust boundaries:** cron + admin routes behind `X-Cron-Secret`
  (`_require_cron_auth`, fails closed); user route behind session auth, viewer-scoped;
  no board content in any payload (consensus-derived numbers only).
- **Deploy/rollback:** flags `receipts.grading` / `receipts.screen` default false; tables
  additive via `_migrate_db`; all knobs `model_config` via `scripts/set_knob.py` (logged in
  `model_config_changes`, `backend/database.py:1515`).
- **Timezones:** all date math on UTC dates; `served_at` is ISO UTC
  (`backend/database.py:513`), `snapshot_date` is a UTC `YYYY-MM-DD`.

## 6. Risks & open questions

Top architectural risks: snapshot-supply gaps (PLAN A-5), cohort too small at launch
(PLAN A-1), grader-bug regrade churn (PLAN A-4). Deferred to LLD: exact route payloads,
status/reason enums, snapshot tolerance mechanics, test matrix. Deferred to operator:
PLAN §8 register.
