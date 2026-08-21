# LLD — Receipts

**Date:** 2026-08-21 · **Parent:** [HLD.md](HLD.md) · Planning only — nothing here is built.

---

## Table of Contents
- [1. Scope & reference](#1-scope--reference)
- [2. Interfaces / API](#2-interfaces--api)
- [3. Data structures & schema](#3-data-structures--schema)
- [4. Core logic — the grader](#4-core-logic--the-grader)
- [5. Concurrency, error handling & edge cases](#5-concurrency-error-handling--edge-cases)
- [6. Backward compatibility & migration](#6-backward-compatibility--migration)
- [7. Testing](#7-testing)
- [8. Pre-build prod queries (P0)](#8-pre-build-prod-queries-p0)

---

## 1. Scope & reference

Implements HLD components: `backend/receipts_service.py`, three `server.py` routes, the
daily-tick guard, schema, mobile screen contract, knobs. Assumes the HLD's decisions D-1…D-11.
Module import contract: `receipts_service` imports `database`, `feature_flags`, stdlib —
**nothing from `trade_service` / `trade_optimizer` / `trade_gen_*` / `bakeoff_*` / `server`**
(leaf pattern per `suggestion_telemetry.py`'s docstring; test-pinned §7 T-1).

Constants in `receipts_service.py`:

```python
GRADER_VERSION   = "receipts-1"   # bump on any grading-semantics change (D-3)
TAXONOMY_VERSION = "1.0.0"        # mirrors docs/plans/shared/trade-shape-taxonomy.md (D-10)
WINDOWS_DAYS     = (14, 28, 56)   # fixed; additive changes only (PLAN §3.3)
```

`model_config` knobs (seeded via `_MODEL_CONFIG_DEFAULTS`, flipped via `scripts/set_knob.py`):

| Key | Default | Meaning |
|---|---|---|
| `receipts_grade_batch` | 500 | impressions per run (fan-out cap) |
| `receipts_min_n` | 10 | user-facing headline gate |
| `receipts_coverage_min` | 0.5 | value-weighted gradeable share below which a graded row is excluded from user headline aggregates |
| `receipts_pick_share_max` | 0.5 | pick share of a side's serve value above which the row is `ungradeable/pick_majority` |
| `receipts_snap_tolerance_days` | 3 | ± days for snapshot-date matching |

## 2. Interfaces / API

### 2.1 `POST /api/cron/receipts-grade`
Auth `X-Cron-Secret` (`_require_cron_auth()`, `backend/server.py:19038`-area). Behavior:
flag `receipts.grading` off → `200 {"ok": true, "skipped": "flag"}` (no writes).
On → **202 immediately**, `{"ok": true, "started": bool}` (`started=false` when a run is
already in flight); grading proceeds in a daemon thread (precedent `cron_players_refresh`,
`backend/server.py:19512-19531`). Query `?batch=N` overrides the knob for one run
(bounded 1..5000). Env kill switch `FTF_RECEIPTS_GRADE=0` → always `skipped`.
Also invoked (same function, fire-and-forget) from the **daily-tick guard** and from
`scripts/receipts_backfill.py` (loops until `remaining == 0`).

### 2.2 `GET /api/league/<league_id>/receipts`
Session auth (viewer = session user); flag `receipts.screen` off → `404 {"error":
"feature_disabled"}`. Viewer-scoped: rows where `user_id = viewer`, `is_ghost` falsy,
league matches; deduped by `(league_id, trade_hash)` keeping earliest serve; grader_version
pinned to max present. Response (one payload, all windows — anti-cherry-pick by construction):

```json
{
  "league_id": "…", "scoring_format": "1qb_ppr",
  "maturity": {"tracked_n": 23, "first_tracked_at": "2026-08-16",
               "graded_n": {"14": 12, "28": 9, "56": 0},
               "min_n": 10, "mature": {"14": true, "28": false, "56": false}},
  "windows": [
    {"window_days": 14, "n": 12, "win_share": 0.58, "median_edge_pct": 0.031,
     "status": "ready"},
    {"window_days": 28, "n": 9,  "status": "insufficient"},
    {"window_days": 56, "n": 0,  "status": "pending"}
  ],
  "headline_window_days": 28,
  "rows": [
    {"served_at": "…", "shape_bucket": "2x1",
     "give":   {"assets": [{"id": "…", "name": "…", "is_pick": false}], "serve_value": 2140.0},
     "receive": {"assets": [...], "serve_value": 2210.0},
     "windows": {"14": {"give_delta": -60.0, "receive_delta": 190.0,
                        "edge": 250.0, "edge_pct": 0.115, "imputed": false},
                 "28": null, "56": null},
     "has_picks": true, "coverage": {"give": 1.0, "receive": 0.62}}
  ],
  "disclosure": {"gradeable_share": 0.74,
                 "excluded": {"pick_majority": 4, "missing_snapshot": 1, "no_serve_snapshot": 1},
                 "methodology": "Graded against market consensus at serve time; picks held constant; predictions locked when shown."}
}
```

Names resolved server-side from the players cache at read time (display-only; never used in
math). Win/median stats computed over rows passing the coverage filter
(`receipts_coverage_min`) — excluded counts appear in `disclosure`.

### 2.3 `GET /api/admin/receipts/metrics`
Auth `X-Cron-Secret` (operator-dashboard pattern, `backend/server.py:8140`). Query params:
`window`, `shape_bucket`, `basis`, `model_arm`, `ghost` (0/1), `league_id` — all optional
filters. Returns per-cell rows: `{cell keys, n, win_share, wilson_low, wilson_high,
median_edge_pct, gradeable_share, flag_low_share}` plus a `served_vs_ghost` block (same
stats split by `is_ghost`, ghost date range labeled). Available regardless of
`receipts.screen`; requires `receipts.grading` on (404 `feature_disabled` while fully dark).

Route additions land in `docs/api-reference.md` in the same PR (mandatory docs gate).

## 3. Data structures & schema

Additive tables in `backend/database.py` (house style: soft references, no FKs — cf.
`deck_outcomes`, `backend/database.py:741-747`); `_migrate_db` entries; documented in
`docs/data-dictionary.md`.

```python
# receipts_grades — APPEND-ONLY. One row per (impression, window, grader_version)
# reaching a terminal status. Never UPDATEd/DELETEd; corrections = new grader_version
# (D-3). The impression row is the preregistered prediction; this table records only
# how consensus moved afterward.
receipts_grades_table = Table("receipts_grades", metadata,
    Column("id",              Integer, primary_key=True, autoincrement=True),
    Column("impression_id",   String,  nullable=False),   # deck_impressions soft ref
    Column("window_days",     Integer, nullable=False),   # 14 | 28 | 56
    Column("grader_version",  String,  nullable=False),   # 'receipts-1'
    Column("taxonomy_version",String),                    # '1.0.0' (doc mirror, D-10)
    Column("status",          String,  nullable=False),   # 'graded' | 'ungradeable'
    Column("reason",          String),                    # NULL when graded; enum §5.3
    # snapshot dates ACTUALLY used (±tolerance matching recorded)
    Column("serve_snap_date", String),
    Column("window_snap_date",String),
    # players-only consensus sums, value units (D-1/D-2)
    Column("give_serve_value",   Float), Column("receive_serve_value", Float),
    Column("give_delta",         Float), Column("receive_delta",       Float),
    Column("edge",               Float), Column("edge_pct",            Float),
    Column("baseline_edge",      Float),  # RESERVED NULL in v1 (shuffle baseline follow-on)
    # coverage + pick accounting (D-7)
    Column("coverage_give",   Float), Column("coverage_receive", Float),
    Column("has_picks",       Integer),
    Column("imputed_count",   Integer),                   # floor-imputed assets (D-8)
    # per-asset audit trail: [{id, side, is_pick, cv0, cv1, imputed_floor: bool}]
    Column("assets_detail_json", Text),
    # denormalized slice keys, copied FROM the impression at grade time
    Column("league_id",       String, nullable=False),
    Column("user_id",         String, nullable=False),
    Column("scoring_format",  String),
    Column("served_at",       String, nullable=False),
    Column("trade_hash",      String),                    # read-time dedup key
    Column("is_ghost",        Integer),
    Column("shape_bucket",    String), Column("archetype", String),
    Column("basis",           String), Column("model_arm", String),
    Column("policy_version",  String),
    Column("graded_at",       String, nullable=False),    # ISO UTC
    UniqueConstraint("impression_id", "window_days", "grader_version",
                     name="uq_receipts_grade"),
)
Index("ix_receipts_grades_league", c.league_id, c.window_days)
Index("ix_receipts_grades_user",   c.user_id,   c.league_id)
Index("ix_receipts_grades_shape",  c.shape_bucket, c.window_days)

# receipts_grade_runs — run ledger, one row per grading invocation (bakeoff_runs style)
receipts_grade_runs_table = Table("receipts_grade_runs", metadata,
    Column("id",             Integer, primary_key=True, autoincrement=True),
    Column("run_at",         String,  nullable=False),
    Column("trigger",        String),                     # 'cron' | 'daily_tick' | 'backfill'
    Column("duration_ms",    Integer),
    Column("graded",         Integer), Column("ungradeable", Integer),
    Column("reason_counts_json", Text),
    Column("batch_cap",      Integer), Column("cap_hit", Integer),
    Column("remaining",      Integer),                    # backlog estimate at run end
    Column("grader_version", String),
)
```

Invariants: no UPDATE path exists in the module for either table (the database.py helpers
expose insert + select only); `deferred` work is **not persisted** — an impression×window
whose window snapshot isn't yet available simply stays in the queue (terminal rows only).

## 4. Core logic — the grader

### 4.1 Work queue (idempotent by construction)

```
todo = SELECT i.* FROM deck_impressions i
       WHERE i.assets_json IS NOT NULL                   -- telemetry era only (NG-7)
         AND date(i.served_at) + :w <= utc_today()       -- per window w ∈ (14,28,56)
         AND NOT EXISTS (SELECT 1 FROM receipts_grades g
                          WHERE g.impression_id = i.impression_id
                            AND g.window_days = :w
                            AND g.grader_version = :GRADER_VERSION)
       ORDER BY i.served_at LIMIT :batch
```

### 4.2 Snapshot prefetch
One query per run: all `player_value_history` rows for the distinct
`(player_id, scoring_format)` set across `[serve_date − tol, serve_date + tol]` ∪
`[window_date − tol, window_date + tol]`, memoized `{(pid, fmt, date): value}` — lookups
against `uq_value_snapshot` (`backend/database.py:1310`); the nearest-date resolution
reuses the `latest_value_snapshot_date` nearest-≤ idiom (`backend/database.py:10883`)
generalized to ± tolerance. Fan-out bound: 500 × 3 windows × ≤6 assets × 2 endpoints ≤
18k dict lookups per run.

### 4.3 `grade_one(imp, window_days)` — pure function

```
assets = json.loads(imp.assets_json)          # {"give": [...], "receive": [...]}
fmt    = league scoring format (set_league_scoring store, database.py:6897;
         detection precedent _detect_scoring_format_from_meta, server.py:725)
serve_date  = utc_date(imp.served_at)
window_date = serve_date + window_days

def side(ids):
    players = [a for a in ids if not is_pick(a)]     # picks: generic_pick_* ids via
    picks   = [a for a in ids if is_pick(a)]         # parse_generic_pick_id + owned-pick
                                                     # pseudo-id pattern (suggestion_
                                                     # telemetry.suggestion_asset_token
                                                     # regex, :196) — same classifier
    cv0 = {p: snap(p, fmt, serve_date  ± tol) for p in players}
    cv1 = {p: snap(p, fmt, window_date ± tol) for p in players}
    # D-8 anti-survivorship: present at serve, absent at window → impute pool floor
    for p where cv0[p] and not cv1[p]:
        cv1[p] = floor_value(fmt, window_snap_date); flag imputed_floor
    graded = [p for p in players if cv0[p] and cv1[p]]
    excluded_at_serve = players − graded              # direction-neutral exclusion
    pick_w  = Σ GENERIC_PICK_SEEDS-derived serve weights of picks   # weighting ONLY
    coverage = Σcv0[graded] / (Σcv0[graded] + Σcv0[excluded_at_serve] + pick_w)
    return Σcv0[graded], Σcv1[graded], coverage, picks, detail

give  = side(assets.give); recv = side(assets.receive)
if pick_share(either side) > receipts_pick_share_max:  → ungradeable/pick_majority
if no graded players on either side:                   → ungradeable/no_serve_snapshot
if a window endpoint unresolvable within ±tol:
    if utc_today() < window_date + 14: leave unqueued (retry later, no row)
    else:                                              → ungradeable/missing_snapshot
give_delta = give.Σcv1 − give.Σcv0 ; recv_delta = recv.Σcv1 − recv.Σcv0
edge     = recv_delta − give_delta
edge_pct = edge / ((give.Σcv0 + recv.Σcv0) / 2)        # serve-time package midpoint
status   = 'graded'  (coverage recorded; read-time filter applies receipts_coverage_min)
```

**Forbidden operations (preregistration, D-2 / PRD §5.3):** reading
`features_json.give_value/receive_value` for any arithmetic; calling `elo_to_value` or any
live seed/pool value; reconstructing assets from `trade_hash`; touching engine modules.

### 4.4 Read-side statistics
Win share = share of graded rows with `edge > 0` (explicit 50% null model in copy). Median
`edge_pct` (median, not mean — heavy tails). Wilson 95% interval on win share for admin
cells: `p̂ ± z√(p̂(1−p̂)/n + z²/4n²) / (1 + z²/n)`, z = 1.96.

## 5. Concurrency, error handling & edge cases

### 5.1 Concurrency
Module-level `threading.Lock` single-flight (`started=false` when held); daemon thread;
batch cap bounds each run. Crash mid-batch: completed inserts stand (unique-keyed), the
rest re-queue next run. Double-fire (cron + daily-tick same day): second call no-ops on
the lock or finds an empty queue.

### 5.2 Error handling
Per-impression try/except: one malformed row (bad `assets_json` JSON → `ungradeable/
malformed_assets`) logs + continues; unexpected exception skips the row (stays queued) and
increments an error counter in the run ledger. Route errors follow house JSON error shapes.
Flag-off and kill-switch paths write nothing.

### 5.3 Status/reason enum (terminal rows only)
`graded` · `ungradeable/` + `pick_majority` | `no_serve_snapshot` | `missing_snapshot` |
`malformed_assets` | `format_missing` (league scoring unresolvable). Not persisted:
retry-pending (queue-implicit), pre-telemetry rows (excluded by queue predicate; disclosed
at read time via a COUNT over `assets_json IS NULL`).

### 5.4 Edge cases enumerated
Empty give or receive side (1x0 shouldn't exist; if seen → `malformed_assets`) · both-side
pick-only packages (`pick_majority`) · player traded IRL / team change (irrelevant — id
stable) · league deleted/renamed (grades keep `league_id`; route 404s naturally) · viewer
left league (route scopes by membership check, existing pattern) · duplicate serve of the
same trade (read-time dedup by earliest) · `served_at` in the future / malformed (skip +
counter) · window lands beyond newest snapshot (retry window §4.3) · format flips
mid-history (grades pin `scoring_format` at grade time; aggregates group by it) · DST/local
time (all UTC, D-11/HLD §5).

## 6. Backward compatibility & migration

Purely additive: two new tables (`_migrate_db` idempotent CREATE), two flags (default
false), five `model_config` seeds, three routes (404/flag-gated), one screen (unregistered
entry point while dark). No existing row, route, or client contract changes. Rollback =
flags off; tables inert. Mobile ships in the normal EAS cadence; server can deploy first
(screen dark until both halves exist).

## 7. Testing (each test names what it proves)

- **T-1 module isolation:** importing `receipts_service` pulls no engine module
  (assert on `sys.modules`); grep-level pin that `server.py`'s engine paths don't import
  receipts. Proves PLAN §7.3.
- **T-2 honesty theorem:** synthetic snapshots with uniform additive drift → `edge ≈ 0`
  for every package shape. Proves D-1's cancellation claim mechanically.
- **T-3 anchor independence:** perturb `features_json` values → byte-identical grades.
  Proves D-2.
- **T-4 pick rules:** Δ=0, weighting-only seeds, `pick_majority` threshold. Proves D-7.
- **T-5 anti-survivorship:** player present at serve, absent at window → floor-imputed
  loss retained, flagged. Proves D-8.
- **T-6 snapshot matching:** ±tol selection, retry window, `missing_snapshot` terminal.
- **T-7 idempotency:** second run inserts zero; crash-sim (partial insert) re-run
  completes without duplicates. Proves §5.1.
- **T-8 regrade:** bump `GRADER_VERSION` → new rows appear, old retained, reads pin max.
  Proves D-3.
- **T-9 route contracts:** viewer scoping, ghost exclusion, dedup-by-earliest, min-n
  gating, all-windows payload, flag-off 404s, admin Wilson numbers.
- **T-10 append-only:** module exposes no UPDATE/DELETE for `receipts_` tables.
- **Structural (`mobile/tests/check-receipts.js` + npm script):** ReceiptsScreen
  registered as root-stack push; `FeedbackFAB activeScreen="Receipts"` exactly once; all
  three window chips bound to one payload; no bare `Receipt` component name (collision
  guard vs `OutlookBiasReceipt.tsx`); testIDs present (testid-lint).
- **Code-walk proof (build-time doc):** cron 202 path; flag-off no-op; daily-tick guard;
  the four forbidden operations with their enforcing tests.
- **Manual TestFlight checklist (PRD §8.3).**

## 8. Pre-build prod queries (P0)

Read-only, `prod_analytics` posture (`default_transaction_read_only=on`):

1. `SELECT COUNT(*), COUNT(assets_json), MIN(served_at) FILTER (WHERE assets_json IS NOT NULL) FROM deck_impressions;` + per-league histogram → A-1 gate.
2. Ghost share + `MAX(served_at) WHERE is_ghost=1` → confirm cohort end (PLAN Q-5) against `model_config_changes`.
3. Pick-involvement share via `features_json->>'involves_pick'`.
4. `SELECT COUNT(DISTINCT snapshot_date) FROM player_value_history WHERE snapshot_date >= '2026-07-26'` vs calendar days → gap rate (A-5 tolerance check).
5. Per-user × league gradeable counts → screen maturity forecast (Q-1).
