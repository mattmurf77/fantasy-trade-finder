# LLD — FTF Analytics & Experimentation Platform

**Date:** 2026-07-17 · **Status:** **Final — dual-agent validated** (4 rounds at the protocol cap; both lenses' final objections were the same one-line queue-key literal, applied verbatim; see [lld-reconciliation.md](lld-reconciliation.md))
**Parents (normative):** [prd.md](prd.md) · [hld.md](hld.md) — both Final. This LLD resolves every HLD §6 "Deferred to the LLD" item and decides PRD OQ-10. All FR/NFR/SM/KD/RB/E references resolve to the parents.
**Stance:** every interface states exact types, nullability, and error returns; every race is named with its resolution; every invariant names the test that proves it.

---

## 1. Scope & Reference

**Covers:** P0–P3 implementation — DDL + migration text, `POST /api/events`, extended `GET /api/feature-flags`, admin analytics/experiment routes, the five backend modules (`analytics_ingest.py`, `analytics_taxonomy.py`, `experiments.py`, `analytics_stats.py`, `analytics_queries.py`), engine/PRAGMA wiring in `database.py`, the mobile SDK (`mobile/src/api/events.ts`, `mobile/src/state/useExperiments.ts`), dashboard secret handling. **Excludes:** web/extension SDK ports (P4 — they implement §2.5's contract verbatim), `/an-experiment` skill (N12), Sentry arming (OQ-1), R3/R4/R6 full query text (P4, same query-module pattern).

**Grounding anchors (symbols, not line numbers — lines rot):** `database.py` `_connect_args` — WAL off, the adjacent comment is wrong (NFR-2); `_migrate_db()` per-statement-transaction idempotent ALTER pattern (Postgres aborts a txn on any error → one-ALTER-per-txn is load-bearing); `user_events_table`, all timestamps ISO-UTC TEXT; `record_event()` dual-writes `users` — ingestion must never call it; `server.py` `_sessions` in-process dict + lock; `_require_cron_auth()` (constant-time, prod fail-closed, **no rate limit today**); flags endpoint returns `{"flags": {...}}`; `useFeatureFlags.ts` `LAUNCHED_FLAG_DEFAULTS`; `client.ts` header stamping + a GET-retry machinery the SDK deliberately does **not** reuse; `requirements.txt` has no scipy/numpy.

**§1.1 Shipped v0 baseline (this LLD reconciles, it does not greenfield).** A parallel work stream has already landed a tracking-plan-v2 §S1/S2 implementation in the working tree, *predating* the PRD/HLD refinements: `POST /api/events` (`ingest_client_events_route`, server.py) with the **old contract** — 404 on flag-off, 400 on missing device_id / oversized batch, **429 on rate limit**, `{accepted, dropped}` response, no dedupe accounting; `insert_client_events()` (database.py) doing per-row inserts; the six envelope columns + a **full** unique index `ix_user_events_event_id` (Table def + migration DDL); `identity_links_table` + `link_identity()`/`_link_device_identity()` already declared and wired into sign-in; the client-event allowlist inline in server.py (`ALLOWED_CLIENT_EVENTS`, which also carries onboarding-conversion events from `docs/plans/onboarding-conversion/plan.md` — those are taxonomy-legal and must survive the move); and a v0 `mobile/src/api/events.ts` (15 s timeout, no `seq`, no `FUNNEL_CRITICAL` retention, purge-on-4xx incl. flag-off-404). **Build rule: every §2–§6 spec below is a rewrite-in-place of these artifacts, never a duplicate** — extend `identity_links_table`'s declaration rather than re-declare (a second `Table()` with the same name raises at import), move/alias `ALLOWED_CLIENT_EVENTS` into `analytics_taxonomy.py`, rewrite the route body to §2.1, replace `insert_client_events()` with the §4.1 single-transaction pipeline. Old-binary tolerances the server must carry through the transition: v0 SDKs purge on **2xx and 4xx** but retry 5xx/network (`sendBatch` returns `'retry'`), never parse the response body (status-only), and send `device_id` in the body — keep the body-then-header fallback (cross-referenced from §2.1's identity paragraph). Because v0 never parses the body, the `dropped` field in §2.1's response is **observability, not compat** — it protects no shipped parser. Accepted transition losses, documented not hidden: v0 binaries lose queued events on flag-off (they purge on 404 today), cannot benefit from sum-short requeue semantics, and their persisted queue key is reused by P1 (`ftf.events.queue.v1` — the new SDK keeps the **same key**; its unknown-shape → discard path handles the v0 plain-array blob, so no orphaned backlog lingers).

**Conventions:** timestamps ISO-8601 UTC TEXT via `database._now()`; JSON stored as `Text`, parsed in Python only — **no json1/JSONB in any query** (dual-dialect). New flag keys appended to `FLAG_KEYS`: `analytics.ingest`, `experiments.engine`, `analytics.dashboard` (`analytics.client_events` already exists).

## 2. Interfaces / API

### 2.1 `POST /api/events` (shim in `server.py` → `analytics_ingest.ingest_request()`)

Gate: `is_enabled("analytics.ingest")`; off → `200 {"accepted":0,"deduped":0,"rejected":[],"disposition":"disabled"}` (client requeues; queue cap bounds it; on re-enable, preserved backlog flows in). Identity resolution in the shim (it owns `_sessions`): token match under one lock acquisition → session identity; dead/absent token → `device:` + `X-Device-Id` (FR-6/E-15); missing `X-Device-Id` *and* no live token → all-`rejected(no_identity)` (the one unattributable case; client purges).

Request headers: `X-Device-Id` (string ≤64; required for pre-auth), `X-Session-Token` (optional), existing `X-Device`/`X-OS-Version`/`X-App-Version`/`X-User-TZ`.

```json
{ "events": [ {
  "event_id":  "string, required, 8–64, ^[A-Za-z0-9_-]+$ (uuid4 expected)",
  "event_type":"string, required, 1–64",
  "client_ts": "string|null, ISO-8601",
  "screen":    "string|null, ≤64",
  "props":     "object|null, ≤4096 B serialized, depth ≤3, ≤40 keys",
  "session_id":"string, required, 8–64",
  "seq":       "integer, required, 1 ≤ seq ≤ 1_000_000"
} ] }
```

Response — always `200` for content (FR-9/11/KD-2); `500` only on unhandled bug (client treats as network failure → requeue):

```json
{ "accepted": 7, "deduped": 2,
  "rejected": [{"index": 3, "reason": "bad_envelope"}],
  "dropped": 1,
  "disposition": "ok" | "disabled" | "batch_rejected:too_many" | "batch_rejected:too_large" }
```

**Accounting invariant (KD-2, normative):** on any committed transaction `accepted + deduped + len(rejected) == len(events)`. Server-side drops (rate-limit, unknown-type/prop, PII-scrub, oversized `props`) count as **`accepted`** ("accepted-and-dropped") + their health counter. Whole-txn failure is the only sum-short case: `{"accepted":0,"deduped":0,"rejected":[]}`, still 200. `rejected` reasons (closed enum): `bad_envelope | bad_event_id | bad_seq | no_identity`. Client purge rule: `rejected` → purge always; sum == N → purge batch; sum < N → requeue non-rejected; **`batch_rejected:*` dispositions override the sum-short rule → purge whole batch** (§4.6); `disabled` → retain (§4.6). Empty `events:[]` → legal no-op (sum 0==0). The `dropped` field is **observability only** (= accepted-and-dropped count, present on every response incl. `disabled`/`batch_rejected:*` where it is 0 — v0 binaries never parse the body, §1.1); it plays no part in the sum invariant or purge rule. Identity: header `X-Device-Id` preferred; the v0 body `device_id` fallback is kept per §1.1.

**Size caps (checked before body parse where possible):** `len(events) > 50` → `disposition:"batch_rejected:too_many"` (purge); `Content-Length > 131072` (128 KiB) → `"batch_rejected:too_large"` checked pre-read (purge — requeueing a forever-unparseable batch is the bug). Do **not** set Flask `MAX_CONTENT_LENGTH` (app-global; would break feedback screenshots). Per-envelope `props` > 4096 B → accepted-and-dropped + counter (client truncates at 2048 B, so this counter ≈ 0 or there's a client bug — that margin is the point).

### 2.2 `GET /api/feature-flags` (extended; FR-35/KD-6)

New optional header `X-Device-Id`. Response strictly additive to `{"flags": {...}}`:

```json
{ "flags": {"espn.link": true},
  "experiments": {"trade.aggression": "generous"},
  "configs":     {"trade.aggression": {"opening_offer_bias": 0.12}} }
```

- Shape per PRD FR-35: `experiments` maps key → variant name (string). `configs[key]` = resolved variant's `client_config` (may be `{}`). No version on the wire: **experiment versions never overlap in time for a key**, so server-side analysis scopes exposures by `[started_at, ended_at)` — clients stay version-ignorant.
- No `X-Device-Id` and no live token → `experiments:{}, configs:{}` (always objects, never absent). Old binaries unaffected (§6.3).
- Unit resolution: live session → `account_id` if present else `sleeper_user_id`; else `device_id`.
- Evaluator exception or `experiments.engine` off → flags-only + `experiments_resolve_errors` counter (FR-40).

### 2.3 Admin surface

All routes: `_require_cron_auth()` first line (secret via `X-Cron-Secret` header only; secret-in-query-param → 401, tested); then `_rate_limit_admin()` — **new** fixed-window 60 req/min keyed by client addr honoring `X-Forwarded-For` leftmost (weak behind a proxy; acceptable at one operator; documented) → `429 {"error":"rate_limited"}`.

| Route | Method | Success | Errors (`{"error": code, "detail": str}`) |
|---|---|---|---|
| `/api/admin/analytics/<report>` (`report ∈ waterfall,time,bottlenecks,churn,releases,adoption,engagement,pfo` — **`health` is NOT in this enum**; params `start,end` ISO date (default trailing 28 d), `format=json\|csv`, `include_demo=0\|1` (default 0), `segment=platform\|signin_method\|ranking_method\|league_count\|experiment:<key>`) | GET | 200 `{"report","window","generated_at","caveats":[…],"rows":[…]}`; insufficiency = `null` cells + `"n_too_small"` caveats — data, never an error | 400 `unknown_report`/`bad_param`; 200 `{"error":"query_timeout"}` cell on statement-guard abort |
| `/api/admin/analytics/health` (dedicated static route — the Health tab calls this; keeping `health` out of the `<report>` enum avoids two responses claiming one URL, where Werkzeug would silently dead-letter the enum entry) | GET | 200 counters, each labeled `"since":"deploy"\|"all-time"`, plus `{wal, event_id_index_present, wal_file_bytes}` | — |
| `/api/admin/experiments` | GET / POST (create draft) | 200 list (newest first) / 201 `{key, version}` | 400 (all errors at once, actionable strings): `layer_unknown, layer_overlap, bucket_range_invalid, weights_not_10000, metric_unknown, attr_unknown, attr_unit_incompatible, unit_type_invalid, targeting_too_deep, targeting_too_large, no_exposure_surface`; 409 `key_version_exists` |
| `/api/admin/experiments/<key>/transition` | POST `{to, actor, reason, override_underpowered?, override_rationale?}` | 200 status row (+ `experiment_transitions` insert) | **409** `illegal_transition` (conflict-class, matching `key_version_exists`/`immutable_running`); 400 `underpowered_needs_override`; 404 |
| `/api/admin/experiments/<key>` | DELETE | 204 — **drafts only** (the §4.3 hard-delete) | 409 `immutable_running` for any non-draft; 404 |
| `/api/admin/experiments/<key>/decide` | POST `{decision: ship\|revert\|iterate, rationale}` | 200; requires `status='stopped'`; permanent (FR-41) | 400 `not_stopped`; 404 |
| `/api/admin/experiments/<key>/revise` | POST new spec | 201 `(key, version+1)` draft | running versions immutable: any mutating PUT/PATCH on non-draft → 409 `immutable_running` (FR-39) |
| `/api/admin/experiments/<key>/readout` | GET | 200 per-metric `{variant_stats, lift_abs, lift_rel, ci95, p, verdict, srm:{chi2,p,red}, guardrails:[…], dilution}`; `verdict:null` + `honesty_banner` below min-n/horizon; SRM red → `verdict:null, srm_alert:true` | 400 `not_started`; 404 |
| `/api/admin/experiments/preview` (design-time calculator, FR-42) | POST spec subset | 200 `{n_per_arm, eligible_per_week, predicted_weeks, mde_at:{"2w","4w","8w"}, underpowered, banner}` | 400 `metric_unknown` |

### 2.4 Client SDK public surface

```ts
// mobile/src/api/events.ts — no React imports; every export swallows all errors
export function track(eventType: string, props?: Record<string, unknown>,
                      opts?: { screen?: string }): void;   // sync: one array push + Date.now(); never awaits
export async function flush(): Promise<void>;              // exported for AppState hook; serialized (§4.6)
export async function getDeviceId(): Promise<string>;      // 'dev_'+uuid4, SecureStore 'ftf.deviceId', minted once
export function currentSessionId(): string;                // rotation per §4.6
export function noteExposure(expKey: string): void;        // experiment_exposed once per exp×session

// mobile/src/state/useExperiments.ts — Zustand, mirrors useFeatureFlags idiom
export function useVariant(expKey: string): string | null;              // null = default/unassigned
export function useExperimentConfig(expKey: string): Record<string, unknown> | null;
```

`track()` is dark unless the **fetched** flag map has `analytics.client_events === true` (missing/`undefined` = off; the key is banned from `LAUNCHED_FLAG_DEFAULTS` — comment on the literal + test T-28). Client-side props truncation at 2048 B (drop + local counter); `client_error.message` scrubbed (regexes: emails, bearer/JWT shapes, 16-digit runs) + truncated to 200 chars **before** enqueue; server re-validates (FR-47).

## 3. Data Structures & Schema

### 3.1 `user_events` additive columns

Appended to `_migrate_db()`'s column list (existing pattern) **and** to `user_events_table` `Column(...)` defs (dual declaration so fresh DBs via `create_all()` match):

| Column | Type | Null | Notes |
|---|---|---|---|
| `event_id` | VARCHAR(64) | YES | NULL for all v1 + all server-fired rows, forever |
| `device_id` | VARCHAR(64) | YES | indexed |
| `platform` | VARCHAR(16) | YES | `ios\|web\|extension` |
| `screen` | VARCHAR(64) | YES | |
| `client_ts` | VARCHAR(32) | YES | advisory only (FR-12) |
| `experiments` | TEXT | YES | JSON `{key: variant}`, stamped rows only (FR-32) |

**Unique index — the idempotency keystone (reconciled with the shipped baseline):** the tree already creates a **full** unique index `ix_user_events_event_id` (Table def + migration DDL). **Keep it** — both SQLite and Postgres default to NULLS DISTINCT, so unlimited v1/server NULL rows coexist legally on both dialects; the earlier draft's claim that a full index "fails at the Postgres port" was wrong. The one consequence lives in §4.1's helper: `on_conflict_do_nothing(index_elements=["event_id"])` **without** `index_where` (a partial predicate would fail to match the full index on Postgres — "no unique constraint matching"). Add the missing composite read index:

```sql
CREATE INDEX IF NOT EXISTS ix_user_events_device_occurred
  ON user_events (device_id, occurred_at);
```

(The shipped single-column `ix_user_events_device_id` may be dropped in the same migration or left as a redundant subset — dropping is preferred; both statements idempotent.) v1 NULL rows never collide by NULLS-DISTINCT semantics — invariant I-1, test T-1.

### 3.2 New tables (SQLAlchemy Core; `metadata.create_all()` picks them up)

```python
# identity_links ALREADY EXISTS (shipped baseline, §1.1) — extend in place, never re-declare
# (a second Table("identity_links") raises at import). Delta vs shipped declaration:
#   NEW ix_identity_links_device_linked ("device_id", "linked_at")  [attribution scans —
#     NEW NAME, not a redefinition of ix_identity_links_device: CREATE INDEX IF NOT EXISTS
#     silently no-ops on the existing single-column name and the composite would never
#     materialize in prod; the old single-column index may then be dropped]
#   NEW ix_identity_links_user ("sleeper_user_id",)
# code-enforced CHECK: at least one of sleeper_user_id/account_id non-null (T-4);
# link_identity()/_link_device_identity() already wired into sign-in — verify-only.

experiment_layers_table = Table("experiment_layers", metadata,
    Column("layer", String(32), primary_key=True),   # onboarding|ranking|trades_ui|engine|growth
    Column("salt",  String(64), nullable=False),     # secrets.token_hex(16), minted by P3 seed, IMMUTABLE
    Column("created_at", String(32), nullable=False))

experiments_table = Table("experiments", metadata,
    Column("key", String(64), primary_key=True),
    Column("version", Integer, primary_key=True),
    Column("layer", String(32), nullable=False),
    Column("status", String(16), nullable=False),    # draft|running|paused|stopped|decided
    Column("unit_type", String(16), nullable=False), # account|device
    Column("hypothesis", Text, nullable=False),
    Column("bucket_start", Integer, nullable=False), # in-layer claim [start, end), 0..10000
    Column("bucket_end",   Integer, nullable=False),
    Column("targeting_json", Text, nullable=False),  # ≤8192 B, depth ≤4, ≤32 predicates (create-time caps)
    Column("variants_json", Text, nullable=False),   # [{name, weight_bp, model_config_overlay?, client_config?}] — Σweight_bp == 10000
    Column("primary_metric", String(64), nullable=False),
    Column("guardrails_json", Text, nullable=False), # auto-seeded five PFO guardrails + bands
    Column("exposure_surface", String(64), nullable=False),
    Column("scope_json", Text),                      # FR-32: {"event_types":[…],"screens":[…]}
    Column("mde", Float), Column("alpha", Float, nullable=False), Column("power", Float, nullable=False),
    Column("override_underpowered", Integer),        # 0|1
    Column("created_at", String(32), nullable=False), Column("started_at", String(32)),
    Column("ended_at", String(32)),
    Column("decision", String(16)), Column("decision_rationale", Text), Column("decided_at", String(32)))

experiment_transitions_table = Table("experiment_transitions", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("experiment_key", String(64), nullable=False), Column("version", Integer, nullable=False),
    Column("from_status", String(16)), Column("to_status", String(16), nullable=False),
    Column("actor", String(64)), Column("reason", Text), Column("at", String(32), nullable=False))
# separate append-only table (not a transitions_json blob): no row-growth cap needed, queryable audit

experiment_assignments_table = Table("experiment_assignments", metadata,
    Column("unit_id", String(64), primary_key=True),
    Column("experiment_key", String(64), primary_key=True),
    Column("version", Integer, primary_key=True),
    Column("variant", String(32), nullable=False),
    Column("assigned_at", String(32), nullable=False),
    Column("context_json", Text),                    # attrs at assignment; first-writer-wins audit, not truth
    Index("ix_assignments_key_ver", "experiment_key", "version"))

experiment_metric_snapshots_table = Table("experiment_metric_snapshots", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("experiment_key", String(64), nullable=False), Column("version", Integer, nullable=False),
    Column("variant", String(32), nullable=False), Column("metric_key", String(64), nullable=False),
    Column("window_start", String(32), nullable=False), Column("window_end", String(32), nullable=False),
    Column("n", Integer, nullable=False),            # exposed units in window
    Column("numerator", Float), Column("denominator", Float),   # proportion metrics
    Column("mean", Float), Column("m2", Float),                 # continuous: winsorized mean + Σ(x−x̄)² (Welford; merged via parallel-variance)
    Column("computed_at", String(32), nullable=False),
    Index("ix_snapshots_key_ver_metric", "experiment_key", "version", "metric_key", "window_end"))
```

Snapshot grain: one row per (key, version, variant, metric, **UTC calendar day**) — cron-compatible for P4; the on-request builder fills missing days then reads all (OQ-7 stays open at zero cost).

**`layer_salt` rules (implementers forget this):** stored in DB, not env — env rotates with deploy-config changes and would silently reshuffle every bucket in the layer (re-randomizing all running experiments with no record). Minted once by the P3 seed migration, never returned by any API, never sent to clients. **Rotation is forbidden while any experiment in the layer is not `decided`**; a forced rotation (salt leak) = stop all layer experiments → new salt row → new assignment universe. There is no rotate-in-place.

### 3.3 Engines & PRAGMAs (sanctioned dialect spots 2 and 3)

```python
# Spot 2 — product engine (existing), database.py ~line 48
if engine.dialect.name == "sqlite":
    @sa_event.listens_for(engine, "connect")
    def _sqlite_on_connect(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")         # persistent; set per-connect (cheap)
        cur.execute("PRAGMA synchronous=NORMAL")       # WAL-safe durability point
        cur.execute("PRAGMA busy_timeout=5000")        # product-path budget (today's pysqlite default, now explicit)
        cur.execute("PRAGMA wal_autocheckpoint=1000")  # ~4 MB; Health surfaces wal_file_bytes
        cur.close()

# Spot 2 continued — dedicated INGEST engine (KD-12 short budget; no PRAGMA-restore-on-pooled-conn risk)
if engine.dialect.name == "sqlite":
    ingest_engine = create_engine(DATABASE_URL, future=True,
        connect_args={"check_same_thread": False, "timeout": 0.15})
    @sa_event.listens_for(ingest_engine, "connect")
    def _sqlite_on_connect_ingest(dbapi_conn, _rec):        # SEPARATE listener — do NOT attach
        dbapi_conn.isolation_level = None                    # canonical pysqlite recipe: disable the
        cur = dbapi_conn.cursor()                            # driver's implicit BEGIN so our explicit
        cur.execute("PRAGMA journal_mode=WAL")               # BEGIN IMMEDIATE below is the only txn
        cur.execute("PRAGMA synchronous=NORMAL")             # start (driver autocommit checks have
        cur.execute("PRAGMA busy_timeout=150")               # churned across Python versions).
        cur.close()                                          # Do NOT attach _sqlite_on_connect: its
                                                             # busy_timeout=5000 PRAGMA runs post-
                                                             # connect and would WIN over 150 (T-23b)
    # RC-8 (SQLITE_BUSY_SNAPSHOT): the §4.1 SELECT-then-INSERT txn must take the write
    # lock UP FRONT — a deferred txn's read snapshot fails its lock upgrade IMMEDIATELY
    # (busy handler not invoked) whenever any product write committed in between, so under
    # the very Sunday burst this design centers on, ingest would shed near-always. Fix:
    @sa_event.listens_for(ingest_engine, "begin")
    def _ingest_begin_immediate(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE")              # write lock first, then SELECT+insert
else:
    ingest_engine = engine   # Postgres: same engine; ingest txns issue SET LOCAL lock_timeout='150ms'
                             # (self-reverting; MVCC has no snapshot-upgrade class — RC-8 is sqlite-only)

# Spot 3 — read-only report engine
if engine.dialect.name == "sqlite":
    ro_engine = create_engine(f"sqlite:///file:{_DB_PATH}?mode=ro&uri=true", future=True,
        connect_args={"check_same_thread": False, "uri": True}, pool_size=2, max_overflow=1)
    # per-connection: dbapi_conn.set_progress_handler(abort_after_~5s_vm_ops, N)  — SQLite has no statement
    # timeout; the progress-handler watchdog is the honest substitute
else:
    ro_engine = create_engine(DATABASE_URL, future=True, pool_size=2, max_overflow=1,
        connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=5s"})
```

Boot check after `_migrate_db()`: `analytics_boot_status()` → `{wal: True|False|None, event_id_index_present: bool}` (`None` = "n/a (postgres)", rendered green; `False` = Health red; **never refuse to serve** — HLD G-C). Engine discipline in `analytics_queries.py`: report-query functions use only `ro_engine`; `build_snapshots()` is the module's single sanctioned primary-engine writer (§4.5 [AMEND]); import-graph test T-2b asserts exactly that split.

### 3.4 In-process structures

- **Rate limiter** (`analytics_ingest.py`): `dict[device_id → (hour_bucket, count)]` under a lock; limit from `model_config` key `analytics_events_per_hr` (seeded 600). **Bounded at 10 000 entries** — `device_id` is attacker-controlled; on cap, evict stale-bucket entries then oldest (unbounded dict = memory DoS). Documented property: resets on deploy (deploy = free window; accepted).
- **Experiment config cache** (`experiments.py`): `{loaded_at, experiments, layers, stamp_scope}` TTL 60 s, lock + double-check rebuild, **stale copy served during rebuild** (never block); deploy wipe → reload (kill latency only shortens).
- **Mobile queues:** in-mem `Envelope[]`; AsyncStorage **`ftf.events.queue.v1`** (the shipped v0 key, reused per §1.1 — the v0 plain-array blob hits the unknown-shape discard path once, no orphaned backlog) = `{"v":1,"events":[…]}`; unknown `v`/parse failure → discard file + counter, never crash-loop; cap 500 with `FUNNEL_CRITICAL` drop-last (`{'app_opened_first','signin_attempted','signin_succeeded','experiment_exposed'}` — source of truth `analytics_taxonomy.py`, hand-mirrored into SDK ports, copy-checked by an eng-qa script until OQ-5 promotes it to generated JSON).

### 3.5 Invariants

- **I-1:** client rows have `event_id NOT NULL ∧ device_id NOT NULL`; server rows have `event_id IS NULL`. No third state. v1 NULLs never collide under the full unique index (NULLS-DISTINCT on both dialects).
- **I-2:** ingestion never touches `users`/`record_event()`/streaks — import-graph asserted (T-2).
- **I-3:** `accepted + deduped + len(rejected) == N` on every committed path (T-3).
- **I-4:** assignment rows are audit, not truth — variant always re-derivable from the hash; the `_flushing` gate is bandwidth optimization, the full unique `event_id` index is correctness.
- **I-5:** `user_id` string space = `sleeper_user_id | acct_… | device:<id> | tomb_<hex16>`; `device:%` excluded from user-scoped metrics **only** via `analytics_queries.device_exclusion()`; stitching **only** via `analytics_queries.attribution_join()` (FR-21).
- **I-6:** `experiments` rows immutable while running except `status`; edits mint `version+1`.

## 4. Core Logic

### 4.1 Ingest pipeline (exact order)

1 flag gate → `disabled` · 2 `Content-Length` cap (pre-read) · 3 parse; `len>50` → `too_many` · 4 identity resolve (shim; one `_sessions_lock` acquisition, copy out) · 5 per-envelope structural validation → `rejected(bad_*)` · 6 rate limit — **whole-batch granularity**: the counter increments by the batch's valid-envelope count and, when the hour cap is busted, the *entire batch's* remaining envelopes are accepted-and-dropped + counter (matches the shipped `_events_rate_exceeded` semantics; per-envelope partial admission is not worth the bookkeeping — T-3's "rate-limited" fixture is a whole batch over the cap) · 7 taxonomy allowlist + namespace check → accepted-and-dropped + counter; unknown props stripped + counted · 8 PII denylist scan (`props` + `client_error` re-scrub) · 9 `client_ts` clamp (|Δ|>48 h → `props.ts_suspect=true`) · 10 **intra-batch dedupe** on `event_id` (first wins; repeats → `deduped` — without this, step 11's SELECT misses same-batch repeats and they'd double-count as accepted) · 11 one transaction on **`ingest_engine`**: `SELECT event_id FROM user_events WHERE event_id IN :batch` → pre-existing = `deduped`; conflict-ignore executemany of the rest, server-stamped (`user_id`, `occurred_at=_now()`, `source`, headers, FR-32 stamp via guarded import — `try: from backend import experiments; except Exception: stamp=None`; P1 ships before P3, so the guard runs in production) · 12 commit; `OperationalError` → rollback, sum-short response, `txn_failed` counter — **the handler wraps the context-manager *entry* too**: with `BEGIN IMMEDIATE` in the begin event (§3.3/RC-8), the 150 ms lock failure raises at `ingest_engine.begin()` entry, not at execute/commit · 13 respond.

```python
def _insert_events_ignore(conn, rows):        # sanctioned dialect spot 1 (FR-5)
    # NO index_where: the shipped index is a FULL unique index (§3.1) — a partial
    # predicate here fails to match it on Postgres ("no unique constraint matching").
    ins = sqlite_insert if engine.dialect.name == "sqlite" else pg_insert
    stmt = ins(user_events_table).on_conflict_do_nothing(index_elements=["event_id"])
    conn.execute(stmt, rows)
# Replaces the shipped per-row insert_client_events() (§1.1) — one txn per batch, not per row.
```

`seq` stored in `props["seq"]` (no new column; gap sampling is sampled, not scanned — revisit only if SM-2 queries hurt).

### 4.2 Hashing & bucketing (exact; **[AMEND — PRD FR-31 / framework §D2]**)

The parents print one formula, `sha256(layer_salt:experiment_key:unit_id)`. A single experiment-keyed hash **cannot deliver in-layer mutual exclusivity**: each experiment would place the same unit at a different bucket, so two experiments with disjoint ranges would still both capture the unit. Two stages are required — flagged as an [AMEND] flowing up on approval:

```python
h = lambda s: int.from_bytes(hashlib.sha256(s.encode()).digest()[:8], "big") % 10000
layer_bucket   = h(f"{layer_salt}:{unit_id}")                      # experiment-INDEPENDENT: places the unit once per layer
in_range       = exp.bucket_start <= layer_bucket < exp.bucket_end # [lo, hi) half-open — see below
variant_bucket = h(f"{layer_salt}:{exp.key}:{exp.version}:{unit_id}")  # version in the preimage (same [AMEND]):
variant        = cumulative_lookup(exp.variants, variant_bucket)   #   without it, a v2 revision re-assigns the SAME
```                                                                #   units to correlated arms — carryover bias after
                                                                   #   a harmful v1. weight_bp ranges over [0,10000).

Ranges are **half-open** `[lo, hi)`, `0 ≤ lo < hi ≤ 10000`. The off-by-one this kills: inclusive `[0,5000]`+`[5000,10000]` double-claims bucket 5000 — 0.01 % contamination, invisible until an SRM check fires months later. Launch validation rejects `hi > 10000`, `lo ≥ hi`, pairwise in-layer overlap across all non-decided versions (interval sweep), and `Σ weight_bp ≠ 10000`. Variant weights and layer claims are separate concerns on purpose: `bucket_start/end` = how much layer traffic the experiment owns; `weight_bp` = how that traffic splits.

### 4.3 Evaluation (`experiments.evaluate_all(unit_id, unit_type, attrs)`, config-fetch path only)

Per running experiment: unit-type match (**`unit_type='account'` is satisfied by both `acct_…` ids and bare `sleeper_user_id`s** — the binary type distinguishes person-units from device-units, not id formats; when an `identity_links` row maps a sleeper id to an `acct_`, the evaluator resolves through to the `acct_` id so a Sleeper-only user who later creates an account keeps their bucket — the remaining unlinked-then-linked swap window is documented in the data dictionary as accepted imprecision) → targeting predicate (attributes validated against the FR-33b registry at **create** time; at eval, a missing attr value → predicate false, unit excluded, no row) → layer bucket check → variant hash → `INSERT OR IGNORE` assignment `(unit_id, key, version, variant, now, json(attrs))` → include in response. Predicate ops: `eq`, `in`, `gte` (semver-aware for `app_version_gte`). Concurrent first evaluations (RC-1) race benignly: determinism ⇒ identical variant; PK conflict-ignore; `context_json` first-writer-wins. Entire evaluator + both call seams (config fetch §2.2, server call sites §6.5) wrapped fail-open (FR-40). Paused experiments load into cache but resolve to no assignment ⇒ default within ≤60 s (FR-38).

**Status machine legal edges (closed set — anything else → 409 `illegal_transition`):** `draft→running` (launch) · `running→paused` · `paused→running` (resume) · `running→stopped` · `paused→stopped` · `stopped→decided`. `decided` is terminal; `draft` may also be deleted (hard-delete allowed only for drafts).

**Admin create/revise body (operator-supplied vs server-stamped):** operator sends `{key, layer, unit_type, hypothesis, bucket_start, bucket_end, targeting, variants:[{name, weight_bp, model_config_overlay?, client_config?}], primary_metric, secondary_metrics?, exposure_surface, scope?, mde, alpha?, power?}`. Server stamps: `version` (1 or prior+1), `status='draft'`, `guardrails_json` (auto-seeded five PFO guardrails + bands, FR-45 — never operator-supplied), `created_at`, salts nothing (layer salt pre-exists).

### 4.4 Time: the definition of "week"

**Cohort week = ISO week, Monday 00:00 UTC, keyed by the Monday's date.** All cohort bucketing uses `occurred_at` — never `client_ts`, never `X-User-TZ` (the streak system's local-day frame deliberately does **not** apply here; two frames, both correct for their purpose, documented in the data dictionary). Implementation: SQL groups at day grain via `substr(occurred_at,1,10)` (portable TEXT op, both dialects); Python folds days→weeks with `date.isocalendar()` in one helper `week_key(day)` in `analytics_queries.py`. No SQL date functions (SQLite `%V` needs ≥3.46; `date_trunc` is Postgres-only).

### 4.5 Stats (`analytics_stats.py`) — **OQ-10 decided: hand-rolled special functions; scipy stays out of requirements.txt**

Needed: Φ (stdlib `math.erf` — free), Φ⁻¹ (Acklam rational approx + one Newton polish, |ε|<1.15e-9), Student-t CDF via regularized incomplete beta `betainc` (Lentz continued fraction, `lgamma` prefactor, symmetry switch at x > (a+1)/(a+b+2), 200-iter cap, 1e-12 tol), χ² survival via regularized incomplete gamma (series for x < s+1, continued fraction otherwise — **same 200-iter cap / 1e-12 tol**). ~150 lines total. Rationale: (a) N6's anti-hand-rolling principle targets *statistical design* wrongness (mSPRT) that no unit test catches; special functions are the opposite — pure `float→float` with independently generated truth tables, testable to 1e-9; (b) scipy+numpy costs seconds of cold start and ~150 MB RSS on Render's 512 MB instance for four functions; (c) RB-5's one-time scipy re-derivation of Experiment #1 audits the exact paths that matter. **Mitigation contract:** `backend/tests/fixtures/stats_golden.json` — ≥200 vectors per function generated offline by a committed scipy script (scipy never in requirements), asserted `abs err < 1e-9`, plus end-to-end known-answer z/Welch/SRM cases. Public surface is scipy-shaped (`norm_cdf, norm_ppf, t_cdf, chi2_sf`) so swapping implementations later is a one-file change.

```
two_prop_z: p̂ pooled for z; unpooled SE for the CI on (p1−p2)
welch: t = (m1−m2)/√(s1²/n1+s2²/n2); df = Welch–Satterthwaite (un-rounded); p = betainc(df/2, ½, df/(df+t²))
srm: χ² = Σ(obs−exp)²/exp over arms vs bucket-width expectation; red at p < .001
power_n_per_arm(p̄, mde, α=.05, β=.20) = 2·(z_{1−α/2}+z_{1−β})²·p̄(1−p̄)/mde²
predicted_weeks = n_per_arm·arms / eligible_per_week   (trailing-28-d units matching targeting ∧ exposure surface)
bonferroni: α / max(arms−1, primary-eligible metric count)
winsorize: p99 pooled across arms per analysis window (pooled avoids arm-dependent truncation bias — Q3 to pm-pfo)
```

Snapshot builder lives in `analytics_queries.py` (keeps `analytics_stats.py` pure — no Flask/DB imports there, per HLD KD-8) **[AMEND — HLD §2.2, which placed the builder entry point in the stats module]**: per missing UTC day × variant × metric → one aggregate over exposed units → insert row via the **primary** engine. This scopes the module's engine rule precisely: **report-query functions use only `ro_engine`; `build_snapshots()` is the single sanctioned primary-engine writer in the module** — T-2b's grep/import assertion is written against that scoped rule, not a blanket "only ro_engine" (the blanket version and this builder cannot both exist). Readout folds day rows (Σ for proportions; Chan et al. parallel-variance merge for continuous), then applies verdict/suppression rules.

### 4.6 Client queue/flush state machine (`events.ts`)

```
track(): flag gate → envelope {event_id: uuid4, client_ts: ISO now, seq: nextSeq(), session_id, screen}
         → queue.push → maybe start 10 s timer. Entire body try/catch-swallow.
session: uuid4 at cold start; rotated when now − lastActivityAt > 30 min (checked in track());
         seq resets to 1 on rotation — gap analysis partitions by (device_id, session_id);
         gap-free ⇔ min(seq)==1 ∧ max(seq)==count(distinct seq)  (a restart is never a gap — T-14)
flush triggers: 10 s timer | len ≥ 20 | AppState→background.  Single _flushing gate; re-entry sets
         _pendingFlush and returns — at most one outstanding request; on completion, purge rule §2.1,
         then re-run if pending. Even a defeated gate converges via server dedupe (I-4).
HTTP:    own AbortController, 10 s timeout; deliberately does NOT reuse client.ts retry machinery —
         event_id idempotency is the retry story.
failure: persist survivors to AsyncStorage; backoff 30 s → 2 min → 10 min cap, ±20 % jitter;
         reset on success or foreground. batch_rejected:* dispositions → purge + counter.
disabled: disposition "disabled" is NOT success — retain queue, jump directly to the 10 min
         max backoff, never reset it, and STOP timer-driven flushes entirely while the fetched
         `analytics.client_events` is false (a killed client must not flush 128 KiB every 10 s
         for weeks — G-A/US-8). Emission and flushing resume on the next fetch that flips the
         flag true; preserved backlog then flows in. (v0 binaries purge on the old 404 —
         accepted transition loss, §1.1.)
cap:     500, FUNNEL_CRITICAL drop-last (§3.4).
uuid:    event_id/session_id via expo-crypto randomUUID (crypto.getRandomValues) — the shipped
         v0 Math.random fallback is not collision-safe for an idempotency key; P1 removes it.
```

**§4.6b Foreground config refetch (the mechanism FR-19/FR-38's client bounds ride on — ships in P1):** the AppState listener already in `App.tsx` (which today calls `retrySync()` + `revalidateSession()`) additionally calls `revalidateFlags()` on active-transition when `now − lastConfigFetchAt ≥ 30 min` (timestamp persisted in the flags store, not module state, so cold starts count correctly). The fetch carries `X-Device-Id` + token per §2.2; on success it updates the flags store **and** the `useExperiments` snapshot — but the experiment snapshot swap is deferred until the next client-session rotation if a session is active (N10 no-mid-session-flips), except transitions *toward default* (pause/stop), which apply immediately (the kill switch is the sanctioned exception).

### 4.7 Report queries

All in `analytics_queries.py` on `ro_engine`; every query takes explicit window params (≤90 d) and carries `LIMIT` (5 000 rows JSON / 50 000 CSV). Shared fragments, each implemented once (RB-6): `device_exclusion()`; `attribution_join()` — FR-21 nearest `identity_links.linked_at ≤ occurred_at`, else earliest after, correlated subquery on `ix_identity_links_device_linked` (§3.2's composite — exactly the `(device_id, linked_at)` shape this scan wants); `exposure_dedupe()` — `GROUP BY unit, experiment, session_id` with `MIN(occurred_at)`; `week_key()`. Demo sessions (`demo_entered` in-session) + allowlist device_ids excluded by default, `include_demo=1` re-includes (E-11/E-12 of PRD §5.3).

## 5. Error Handling & Edge Cases

### 5.1 Named races

| # | Race | Resolution |
|---|---|---|
| RC-1 | Concurrent first evaluation (two devices, same account) | Deterministic hash ⇒ same variant; PK conflict-ignore; context first-writer-wins (T-9) |
| RC-2 | Double flush (timer + background overlap) | `_flushing` gate; defeated gate → server dedupe, sum still == N (T-10) |
| RC-3 | Crash-mid-flush replay (acked but ack lost) | Queue persisted pre-flush, purged only on qualifying response; replay → all `deduped` (T-11) |
| RC-4 | Deploy-mid-batch (server dies commit↔response) | Client sees network error → requeue → RC-3; next flush's dead token → FR-6 fallback + FR-21 at-or-before attribution (T-12) |
| RC-5 | Tombstone vs concurrent ingest from the deleted device | Writers serialize. Ingest-first → tombstone UPDATE rewrites (scans `user_id` **and** `device_id` via `ix_user_events_device_occurred`). Tombstone-first → new rows land under raw `device:` id with no surviving link row ⇒ can never attribute to the deleted account; hashed old ids share no join key with raw new ids ⇒ no re-identification; `event_id` survives tombstoning ⇒ replayed pre-deletion batches dedupe instead of resurrecting (T-13). **Closing the leak the PRD's three-table list missed [AMEND — PRD FR-22]:** the tombstone transaction ALSO rewrites `wrapped_events.user_id` — the frozen table retains raw ids for pre-cutover history, and the §6.4 union reader still *renders* that legacy span, so without this a deleted user's pre-cutover actions stay attributed forever; T-13 additionally asserts the narrative reader returns no raw-id rows for a tombstoned account. The deletion response also instructs the SDK to purge its local queues (`{"purge_analytics_queue": true}`) so pre-deletion unsent events don't flush post-deletion under the persisting Keychain `device_id` and re-attribute via a later re-signup link |
| RC-6 | Config-cache rebuild vs pause | 60 s TTL is the stated bound; stale-copy-during-rebuild never blocks; drill SM-8 measures |
| RC-7 | Rate-limiter check-then-increment across workers | Lock around read-modify-write; limiter is advisory (accept-and-drop) so any bug over-accepts, never rejects |

### 5.2 Timeout budgets (everything that waits)

| Path | Budget | On expiry |
|---|---|---|
| Ingest txn lock wait | 150 ms (`ingest_engine` connect arg / `SET LOCAL lock_timeout`) | rollback → `accepted:0` → client queue (KD-12) |
| Product writes | 5 s explicit (formerly implicit pysqlite default) | existing behavior |
| Report statement | ~5 s progress-handler abort / `statement_timeout` | `query_timeout` cell, dashboard renders error card |
| SDK flush HTTP | 10 s AbortController | requeue + backoff |
| Config fetch | client.ts 15 s (unchanged) | keep last snapshot |
| Evaluator per fetch | no I/O beyond one conflict-ignore insert; K = running experiments (single digits) | fail-open `experiments:{}` |

### 5.3 Unbounded-resource guards

Batch 50 / 128 KiB pre-parse · `props` 4096 B server, 2048 B client · `targeting_json` 8192 B, depth ≤4, ≤32 predicates · client queue 500 (critical drop-last) · rate-limiter dict 10 000 entries · CSV export 50 000 rows · JSON report 5 000 rows · health counters plain ints (no per-device server maps beyond the bounded limiter) · transitions in a separate append-only table (no blob growth).

### 5.4 PRD edge-case map (E-1..E-15)

E-1 offline → §4.6 persist/flush; E-2 5xx → backoff/requeue/cap; E-3 duplicates → §4.1 steps 10–11; E-4 stitch/shared device → `attribution_join()` + R1 trace raw+attributed; E-5 multi-device → account-unit hash consistency; E-6 mid-session stop → snapshot pinned, readout filters `occurred_at > ended_at`, late `experiment_exposed` lands and is window-excluded, never rejected; E-7 version skew → allowlist tolerate+count, launch warning sans `app_version_gte`; E-8 SRM → `srm.red` ⇒ banner + verdict null; E-9 tiny cohorts → `n_too_small` caveats, counts kept; E-10 skew → clamp step 9; E-11 demo/operator → default-excluded; E-12 deletion → RC-5 + tombstone matches no targeting attr next session; E-13 crash double-fire → client Set best-effort + authoritative `exposure_dedupe()`; E-14 reinstall → Keychain semantics documented, web caveat badge; E-15 dead token → step 4 fallback + T-21. Duplicate `event_id` with *different* payload (client bug) → first-write-wins, counted `deduped`, divergence undetectable by design (documented). `seq` > 1 000 000 → `rejected(bad_seq)`.

## 6. Backward Compatibility & Migration

### 6.1 Migration mechanics (P0, extends `_migrate_db()`)

(1) additive ALTERs via the existing one-ALTER-per-txn list (Postgres txn-abort semantics make that pattern load-bearing — keep it); (2) the two indexes via `CREATE … IF NOT EXISTS` wrapped try/except (plain, not CONCURRENTLY — beta table size makes the lock window trivial; Postgres-at-scale revisit noted); (3) new tables via `metadata.create_all()`; (4) P3 seed: layer rows with fresh salts, `INSERT OR IGNORE`. Idempotent end-to-end: T-15 runs `_migrate_db()` twice and diffs schema.

### 6.2 v1 rows and server call sites

`record_event()` call sites keep writing `event_id=NULL` forever — correct, not debt: server-fired events are never retried-with-replay, so they need no idempotency key. Reports treat `event_id IS NULL` as "server-fired", never as an error class. All report predicates NULL-tolerant on the six new columns.

### 6.3 Old binaries — three concrete hazards

(1) Pre-P1 binaries hit the extended flag endpoint without `X-Device-Id` → `experiments:{}`, `flags` unchanged; mobile `flags.ts` reads `res?.flags || {}` (tolerant — verified; T-27 pins it), web reads `.flags` into `window.FTF_FLAGS` (tolerant), extension re-verified at P4 (OQ-6 closed per-client, not assumed). (2) Stale taxonomy from old binaries for months → allowlist tolerate+count, never 4xx. (3) Kill-switch masking → `analytics.client_events` absent from `LAUNCHED_FLAG_DEFAULTS` and from the first-boot cache ⇒ default-dark until first successful fetch; T-28.

### 6.4 `wrapped_events` cutover (P0, FR-4)

Single deploy: the five writers flip to `user_events` (`tier_save` routes through `record_event()` and joins `_RANK_STREAK_EVENTS` — the comment beside `_RANK_STREAK_EVENTS` says exactly this migration unlocks it; `league_sync` renames to the live server name `league_synced`). Narrative builder (`database.py`, Wrapped narrative section) repoints with the union predicate on **each table's own timestamp column**: legacy `wrapped_events.created_at < cutover_ts` ∪ `user_events.occurred_at ≥ cutover_ts` (`wrapped_events` has **`created_at`, not `occurred_at`** — the column-name mismatch is exactly the kind of thing that breaks the one non-flag-rollback migration). Field mapping stated per event type: legacy rows parse `payload_json`; new rows parse `props` (same inner keys per the wrapped_collector call sites) with `league_id` read from the first-class column instead of the payload. The boundary constant lives in `model_config` (`analytics.wrapped_cutover_at`) so T-16 asserts `count(legacy<t) + count(new≥t) == count(total)` with zero overlap. `NARRATIVE_TYPES` gains the writer-less `trade_accepted`/`trade_declined` from the live `user_events` variants. Rollback = the rehearsed revert deploy (P0 PR checklist item).

### 6.4b FR-20 server-fired events — call-site spec (P0 scope; the PRD's P0 exit criterion depends on these)

Already landed by the parallel v0 stream (**verify-only**, per current tree): `anchor_answered`, `feedback_submitted`, `tier_save`, `ranking_reorder`, `ranking_method_changed`, `league_synced`. **Still zero call sites (build these):**

| Event | Owning route/function (server.py) | props |
|---|---|---|
| `quickset_completed` | QuickSet tier-save route (the `via:'quickset'` branch of the tiers save path) | `position`, `players_placed`, `duration_ms` (client-passed), `skipped` |
| `quickrank_completed` | Quick Rank save route | `position`, `players_ranked`, `duration_ms`, `skipped` |
| `trades_generated` | Find-a-Trade generation route (post-engine, pre-response) | `count`, `gen_ms`, `engine_version`, `lanes` |
| `calc_trade_evaluated` | Calculator evaluate route (server-truth mode) | `verdict`, `asset_count`, `mode` — **load-bearing for the WAT north star (PRD FR-20)** |

Each is one `record_event()` call following the existing call-site idiom (splat `g.device_info`, swallow errors); event names join the server-fired taxonomy in `analytics_taxonomy.py` and `docs/data-dictionary.md`.

### 6.5 `aggression_ab` migration (P3) — and the second evaluation seam it requires

Delete the MD5 branch in `trade_service.aggression_variant()`; insert `experiments` row (`key='trade.aggression'`, `version=1`, `layer='engine'`, `unit_type='account'`, variants carrying `model_config_overlay` deltas). **`experiments.variant_overlay(unit_id)` is the HLD's second fail-open seam, fully defined:** it runs the *complete* §4.3 evaluation (targeting → layer bucket → variant hash → conflict-ignore persist → overlay merge over `get_config()`), sourcing attrs from the `users` row — **header-derived attrs are unavailable at this seam**, so launch validation warns when an engine-layer experiment targets header attributes. This matters because server call sites fire for users who never fetch config with identity (all web users until P4, all pre-P1 binaries); if the seam were assignment-lookup-only, those users would be default-with-no-assignment while still hitting the exposure surface, poisoning Experiment #1's dilution/SRM. Same 60 s cache, same fail-open wrapper (returns `{}` overlay → pure `get_config()` behavior). v0 `props.aggression_variant` rows → one archived readout doc; never joined with v1 (KD-10). The `trade.aggression_ab` flag retires from `FLAG_KEYS` after Experiment #1 decides.

### 6.6 Dashboard secret UX

Prompt once per tab; `sessionStorage` (cleared on tab close — `localStorage` would persist the master admin secret indefinitely); any 401 clears + re-prompts (handles rotation mid-session); the page never echoes the secret into DOM/URL/history. Rotation = Render env update + redeploy (secret read from env at boot); procedure in runbook.

## 7. Testing

| Test | Proves |
|---|---|
| T-1 | Full unique index, NULLS-DISTINCT: 2×NULL + 2×same-`event_id` → 3 rows, on both dialects (I-1) |
| T-2/T-2b | Ingest import graph excludes `record_event`/`touch_user_activity`; `analytics_queries` report functions touch only `ro_engine` while `build_snapshots()` alone uses the primary engine (I-2, RB-6, §4.5 scoped rule) |
| T-3 | Accounting invariant across a batch mixing all six dispositions (valid, dup-in-batch, dup-in-db, unknown-type, rate-limited, malformed) (I-3) |
| T-4 | `identity_links` code-CHECK: both ids null → rejected |
| T-8/T-8b | Bucket goldens incl. 0/4999/5000/9999 edges; inclusive-range config `[0,5000]+[5000,10000]` rejected (§4.2) |
| T-9/T-9b | Assignment determinism across processes (10 k units); cross-layer independence χ² p > .01; **in-layer exclusivity: every unit hits ≤1 experiment per layer** (the two-stage-hash property) |
| T-10..12 | RC-2/3/4 replay convergence: kill at each seam, resend, assert rowcount + `deduped` |
| T-13 | RC-5 both interleavings: tombstone join returns ∅; replay doesn't resurrect |
| T-14 | Seq: two sessions 1..n gap-free; dropped seq 3 flagged; rotation ≠ gap |
| T-15 | `_migrate_db()` twice = identical schema |
| T-16 | Cutover count-consistency across `analytics.wrapped_cutover_at`, zero overlap (FR-4) |
| T-17/T-18 | Stats goldens (≥200 vectors/function, 1e-9) + end-to-end z/Welch/SRM known answers; one-time scipy re-derivation of Exp #1 (manual gate, RB-5) |
| T-19 | Exposure dedupe: synthetic crash double-fires → readout n unchanged (FR-37) |
| T-20 | Pause drill: evaluator flips ≤60 s (FR-38/SM-8) |
| T-21 | Dead-token post-deploy rows attribute to signed-in user in stage-2+ queries (E-15/FR-21) |
| T-22/T-23 | WAL boot assertion (sqlite true, postgres n/a-green); concurrent 10× ingest + product writes: ingest sheds (`accepted:0`) while product p95 holds (KD-12/SM-3 harness, on the Render instance class) |
| T-23b | `PRAGMA busy_timeout` returns **150** on an `ingest_engine` connection and **5000** on a product-engine connection (the listener-precedence trap §3.3) |
| T-24 | Admin auth matrix: 401 wrong secret, 401 secret-in-query-param, 503 unset-in-prod, 429 over rate |
| T-25 | Week bucketing: events straddling Sunday 23:59/Monday 00:00 UTC split cohorts; `X-User-TZ` irrelevant (§4.4) |
| T-26 (Jest) | Corrupt persisted queue discarded without crash; 600-event overflow retains `FUNNEL_CRITICAL` |
| T-27 (Jest) | `flags.ts` parses extended response; old-shape fixture also parses |
| T-28 (Jest+grep) | `analytics.client_events` absent from `LAUNCHED_FLAG_DEFAULTS`; SDK treats `undefined` as off |
| Maestro (eng-qa) | Sign-in flow → expected `user_events` rows via gated JSON; airplane-mode → relaunch → flush → gap-free `seq`, `deduped=0`; kill drill end-to-end |
| Perf gates | SM-3 concurrent harness above; cold-start delta <50 ms on test device (NFR-1) |

## 8. Open Questions

1. **[AMEND]s flowing up (Q1):** (a) two-stage hash **with version in the variant preimage** (§4.2) — PRD FR-31 and framework §D2 print the single, version-less formula; in-layer exclusivity is otherwise unimplementable and revisions otherwise carry over correlated arms. (b) **PRD FR-22**: tombstone transaction extends to `wrapped_events.user_id` (§5.1 RC-5) — the PRD's three-table list left a rendered leak. (c) **HLD §2.2**: snapshot-builder entry point lives in `analytics_queries.py` (scoped engine rule), not `analytics_stats.py` (§4.5). (d) **PRD FR-1 / HLD §3.1**: the shipped **full** unique `event_id` index is kept (NULLS-DISTINCT is legal on both dialects) — the parents' "partial unique index `WHERE event_id IS NOT NULL`" DDL is superseded (§3.1); their "review trap" rationale was wrong.
2. **Resolved here — OQ-10:** hand-rolled special functions + committed scipy-generated goldens (§4.5); public surface scipy-shaped for cheap later swap.
3. **Resolved here:** "week" = ISO Monday-start UTC on `occurred_at` (§4.4) — one-line confirmation lands in the data dictionary + program plan (the Monday ritual reads these cohorts).
4. **Q3 (pm-pfo):** winsorization pooled-across-arms at p99 (avoids arm-dependent truncation bias) — confirm.
5. **Q4 (legal-privacy, joins OQ-3):** tombstone = `tomb_` + hex16 of a **random-per-deletion value discarded after use** (truly one-way; a pure hash of the id risks re-identification).
6. **OQ-5 (P2 exit):** taxonomy constants hand-mirrored into SDK ports + eng-qa copy-check now; promote to generated shared JSON + CI if SM-5 shows drift.
7. **HQ-3 (P2 gate):** index sufficiency for 3 s @ 1M measured on the Render instance class (T-23 harness), not asserted.
8. **New, small:** Render SQLite build tolerance of `mode=ro` URI connections alongside WAL writers under load — believed yes (WAL's purpose); verified by the T-23 harness before P2; Postgres read-role is the pre-planned fallback.
