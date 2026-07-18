# HLD — FTF Analytics & Experimentation Platform

**Date:** 2026-07-17 · **Status:** **Final — dual-agent validated** (3 rounds, both lenses signed off; see [hld-reconciliation.md](hld-reconciliation.md))
**Satisfies:** [prd.md](prd.md) (Final, dual-agent validated). All FR/NFR/SM/OQ references are to that document. Component boundaries are **modules inside the existing Flask monolith** — zero new deployables (G6/NFR-6).
**Method:** every component states its failure mode → degradation → blast-radius bound. A design that can't state all three isn't done.

---

## 1. Context & Goals

### 1.1 Requirements & stance

This design must satisfy PRD G1–G6, FR-1..48, NFR-1..10; §2.2 maps every FR to exactly one owning module. The platform is a parasite on a resource-constrained host: one Flask process on Render, one SQLite file shared with product traffic, an in-process session dict wiped every deploy, boolean flags reloaded only by manual cron-gated POST, and a mobile client that takes days to update. The design goal is not "analytics works" — it is **analytics failing, misbehaving, or being attacked cannot take the host down, corrupt its data, lie to the operator, or leak tester behavior**:

- **G-A (bounded harm):** every new code path has a stated worst case and a bound. No unbounded queues, retries, or hot-path table scans.
- **G-B (correct under partial failure):** deploys mid-flush, crashes mid-batch, dead tokens, clock skew, replayed queues converge to correct-or-visibly-degraded data, never silently wrong data.
- **G-C (fail-open product, fail-closed data):** evaluator/SDK errors serve defaults (FR-40/NFR-3); the admin surface serves nothing without the secret (FR-24/NFR-5).
- **G-D (one person can run it):** zero new deployables, zero background workers in MVP; degradations self-describe on the Health tab instead of paging anyone.

### 1.2 Constraints & assumptions (from the real codebase)

- `backend/server.py` is a ~9k-line route monolith; `backend/database.py` owns schema + idempotent `_migrate_db()` ALTERs. Repo shape: **new files for new domains; `server.py` gains only thin route shims** (flat modules, not a package — matches `ranking_service.py`/`trade_service.py` convention).
- WAL is genuinely **off** today (`database.py:43`'s comment is wrong — `{"check_same_thread": False}` doesn't touch journaling).
- `GET /api/feature-flags` (server.py:9184) is identity-less; FR-35 extends it additively rather than replacing it. Mobile merges `LAUNCHED_FLAG_DEFAULTS` over cached fetch — FR-19's keep-out rule is enforceable at that exact file.
- `record_event()` dual-writes `users` hot columns; dead-token is the routine post-deploy state (FR-6/E-15).
- Simplest design that satisfies the PRD: **five new backend modules, three thin client SDK files, one static dashboard page, three new tables + six new columns.** Anything adding a process, broker, framework, or second datastore is rejected in §4.

## 2. Architecture Overview

### 2.1 Component map

```
clients                         backend (Flask monolith)                storage (SQLite WAL → Postgres)
───────                         ────────────────────────                ───────
mobile/src/api/events.ts ──┐
web/js/events.js      (P4) ┼─► POST /api/events ─► analytics_ingest.py ─► user_events (+6 cols)
extension bg          (P4) ┘        (server.py shim)    │ analytics_taxonomy.py (allowlist)
  in-mem queue → persistent                             │
  queue (500, funnel_critical   GET /api/feature-flags ─► feature_flags.py
  drop-last), device_id/seq        (extended, FR-35)    + experiments.py (evaluator) ─► experiments,
                                                             │                          experiment_assignments
server call sites (trade_service, server.py) ────────────────┘ (same evaluator, 60s cache)
                                                        analytics_stats.py ─► experiment_metric_snapshots
web/admin/analytics.html ─► GET /api/admin/analytics/* ─► analytics_queries.py (read-only engine)
  (X-Cron-Secret header,                                     └─ reads user_events, identity_links, …
   sessionStorage)              sign-in path ─► identity_links (append-only)
```

### 2.2 Modules: responsibility, FR ownership, failure envelope

| Module | Responsibility (owns FRs) | Failure mode → degradation → blast-radius bound |
|---|---|---|
| **`analytics_ingest.py`** (new) | `/api/events` body: envelope validation, per-envelope partial-failure semantics, intra-batch de-dupe + pre-insert `SELECT event_id IN (…)` accounting, single-txn dialect-branched conflict-ignore insert, rate limit (600/hr/device accept-and-drop), `client_ts` clamp, PII re-validation, dead-token → device fallback, health counters. **Never calls `record_event()`** — client rows bypass the `users` dual-write (FR-3). (FR-6..13, FR-47; SM-2/4) | Lock contention / malformed floods / retry storms → per-envelope accept/dedupe/reject; over-limit 200+drop+counter; **txn failure → 200 with `accepted:0`** (client requeues; `event_id` idempotency makes replay safe — see KD-2 and its response-accounting invariant). Bound: one ≤50-row txn **with a deliberately short ingest-only lock-wait budget** (KD-12); `analytics.ingest` flag amputates the endpoint; product routes never call this module. |
| **`analytics_taxonomy.py`** (new) | Machine-loadable allowlist of client event types/props generated from tracking plan v2; `funnel_critical` tag list; **import-time namespace assertion** against server-authoritative names (`_EVENT_TO_USER_COL`, `_RANK_STREAK_EVENTS`, server taxonomy) — CI-promotable (OQ-5). (FR-9, FR-48) | A drifted client → dropped+counted rows (SM-5), never insertion; a colliding name → import-time failure at deploy, not silent corruption. |
| **`experiments.py`** (new) | Evaluator: FR-33b targeting → `sha256(layer_salt:key:unit) % 10000` → variant; persist-on-first-eval (conflict-ignore PK); status machine + transition log; launch validation (layer overlap, metric keys, unit-attribute compatibility, weights); per-variant `model_config` overlays; 60 s in-process config cache (the FR-38 TTL); fail-open wrapper. Server-only — clients never hash. (FR-30..34, FR-36, FR-38..41) | Evaluator bug / bad config row → exception caught at the two seams (config fetch, server call sites) → default experience + counter. Worst case: every user in control; product identical to pre-platform. Concurrent first evaluations race benignly (same deterministic variant; conflict-ignore). A deploy wiping the cache *shortens* kill latency (DB is truth). |
| **`analytics_stats.py`** (new) | Pure functions, no Flask/DB imports: power/duration calculator, z/Welch/χ²/SRM, Bonferroni, guardrail thresholds, verdict suppression. *(Amended per LLD §4.5/§8.1c: the snapshot-builder entry point lives in `analytics_queries.py` as that module's single sanctioned primary-engine writer — keeping this module truly import-free.)* (FR-42..46) | Numeric wrongness is quieter than crashing → golden-value tests are a launch gate (OQ-10) **plus a one-time manual re-derivation of Experiment #1's readout in scipy before engine verdicts are trusted**. Read-time only; never live scans on page-load. |
| **`analytics_queries.py`** (new) | Every report (R1–R8, R10) as parameterized dual-dialect SQL → JSON/CSV; **the single home of the `device:` exclusion filter and the FR-21 attribution rule** (shared query fragments — named bug class, one implementation); insufficiency states, demo/allowlist exclusion, segmentation; **FR-37 readout-side exposure dedupe** (crash double-fire re-dedupe lives here as a shared fragment, same one-implementation discipline as FR-21). (FR-3, FR-21 query side, FR-23, FR-26..29, FR-37 readout side) | A pathological report degrades the dashboard, never the app: **all admin reads run on a separate read-only engine** (SQLite `mode=ro` URI) with per-query LIMIT/window bounds — a scan cannot hold the write lock or mutate anything. Secret-gated, so testers can't trigger scans. |
| **`feature_flags.py`** (extended) + config shim | FR-35 contract: read `X-Device-Id` + optional token, resolve unit per session class, return `{flags, experiments, configs}` additively on the existing endpoint; kill-switch flags. Boolean flag semantics unchanged (manual reload; KD-8). (FR-19, FR-35) | Resolution failure → flags-only response (old contract) + counter; clients keep last snapshot. |
| **`database.py`** (extended) | Additive migration: 6 nullable `user_events` cols + partial unique index; `identity_links`; 3 experiment tables; **WAL on-connect listener + boot-time `journal_mode=='wal'` assertion surfaced on the Health tab** (log + red, not refuse-to-serve — refusing would create a deploy-blocking failure mode for an analytics feature, violating G-C; **both dialect-gated to sqlite** — on Postgres the Health tab shows "n/a (postgres)" green, per §3.4); `wrapped_events` cutover + Wrapped-narrative repoint. (FR-1, FR-2 DDL, FR-4/5, FR-30 DDL; NFR-2) | Migration is additive/idempotent; cutover rollback = rehearsed revert deploy (the one non-flag rollback). |
| **Server call sites** (`server.py`, `wrapped_collector.py`) | FR-20 server-fired events via `record_event()` (these legitimately keep the dual-write — authenticated, server-authoritative); **FR-2 write side** (append `identity_links` row on every successful sign-in); FR-22 tombstone transaction; **FR-24 server half** (the `_require_cron_auth` gate + new rate limiting on `/api/admin/analytics/*` — note: the existing helper has constant-time compare and fail-closed but **no rate limiting today; that is new code**). | Same swallow-errors contract as today. |
| **Client SDKs** (`mobile/src/api/events.ts`, `web/js/events.js`, extension bg P4) | One contract, three ports: `track()` → in-mem queue → flush (10 s / 20 events / background, **serialized: one outstanding request per client**) → persistent queue → drop-oldest-except-`funnel_critical` at 500; `device_id`/`session_id`/`seq` stamping; fully fire-and-forget. Mobile adds `useVariant()` snapshot hook + ≥30-min foreground config refetch. (FR-14..18, client halves of FR-35/37) | Any SDK error swallowed + local counter; **corrupted persisted queue → discard + counter, never crash-loop**; storage-full → best-effort. An SDK bug can lose telemetry (visible via `seq` gaps) but cannot white-screen, block UI, or drain battery beyond the flush cadence. |
| **`web/admin/analytics.html`** + `web/js/admin-analytics.js` | Thin renderer: tabs, gated JSON fetch, Chalkline-token charts; secret once → `sessionStorage` → `X-Cron-Secret` header. Computes nothing. (FR-24 client half, FR-25) | Misconfigured gate → server fails closed (403), page shows error, not data. Report JSON rendered via `textContent`/attribute-safe writes only — no `innerHTML` of event-derived strings, so a hostile `screen` or scrubbed-but-weird error message can't XSS the one browser holding the secret. Static page itself contains zero data. |

**Deliberately absent machinery:** no Redis/queue/worker (bounded client queues + idempotent replay *are* the durability layer), no snapshot cron in MVP (on-request, OQ-7), no auto-rollback (N9), no sequential stats (N6). Each absence is a failure mode chosen over a maintenance mode.

### 2.3 Interactions — sync vs async

Everything server-side is synchronous within a request; the platform's only asynchrony is client-side (queue/flush timers). No threads, workers, or brokers.

- **Client → ingestion:** interaction paths only append to an in-memory array; a timer/background hook flushes. HTTP never awaited on an interaction path (FR-15). Server processes one bounded batch per request.
- **Client → config:** cold start, sign-in, and the ≥30-min foreground refetch hit the extended flag endpoint; everything between reads the snapshot pinned per client `session_id` (FR-35, N10).
- **Server call sites → evaluator:** in-process call, exactly like `is_enabled()` today; the 60 s cache makes pause/stop FR-38-compliant with no push channel.
- **Operator → dashboard:** pull-only; readouts from snapshots built on request (FR-46). No polling, websockets, or cron in MVP; the P4 snapshot cron reuses the same schema.

## 3. Data Model & Flow

### 3.1 Entities

**Extended:** `user_events` + nullable `event_id` (**full unique index, NULLS DISTINCT on both dialects** *(amended per LLD §3.1/§8.1d — the partial-index requirement rested on a wrong premise and the shipped v0 baseline already carries the full index)* — the idempotency keystone: crash-after-insert-before-ack, deploy-mid-flush, and offline replay all collapse to `deduped`, counted, invisible in reports), `device_id` (indexed), `platform`, `screen`, `client_ts`, `experiments` (JSON). v1 rows/call sites untouched. `wrapped_events` frozen read-only at cutover.

**New:**
- `identity_links(device_id, sleeper_user_id, account_id, linked_at)` — append-only, duplicates allowed (shared devices are 1:N by design). **No update job exists to half-complete:** events immutable, links immutable, the join rule pure and re-runnable.
- `experiments(key, version, layer, status, hypothesis, unit_type, targeting_json, variants_json, primary_metric, guardrails_json, mde, alpha, power, timestamps, decision, notes)` — append-only except `status`; edits mint a new version (FR-39).
- `experiment_assignments(unit_id, experiment_key, version, variant, assigned_at, context_json)` — PK `(unit_id, key, version)`, conflict-ignore. **A lost assignment row is re-derivable** (deterministic hash): the persisted row is an audit record, not a correctness dependency — this kills the insert-vs-assignment partial-failure class.
- `experiment_metric_snapshots(experiment_key, version, variant, metric_key, window, values…)` — the only table readouts scan.

**Identity namespace:** `sleeper_user_id` / `acct_…` / `device:<device_id>` / tombstone hash — one string space across all tables.

### 3.2 Primary flow — client event end-to-end (with the NFL-Sunday walkthrough)

1. `track('screen_viewed', {…})` → envelope `{event_id, event_type, client_ts, screen, props, session_id, seq}` appended in memory.
2. Flush POSTs ≤50 envelopes with token + `X-Device-Id` + device headers; failure → persistent queue, bounded backoff, serialized flushes.
3. `analytics_ingest.py`: identity resolve (dead token → silent `device:` fallback, never 4xx); rate-limit (over → 200+drop+counter); allowlist → PII denylist → `client_ts` clamp per envelope; intra-batch de-dupe; one transaction: pre-insert `SELECT` for `deduped`, then conflict-ignore executemany; FR-32 experiment stamping (see §3.3).
4. Response `{accepted, deduped, rejected}`; client applies the KD-2 purge rule (`rejected` purged always; sum == N → purge batch; sum < N → requeue non-rejected).
5. Read side: `analytics_queries.py` applies attribution (nearest link at-or-before, else first-after) + `device:` exclusion — post-deploy dead-token rows still land in signed-in DAU/funnel stages 2+.

**Burst behavior (N clients foregrounding Sunday 1 pm ET while product writes):** one txn ≈ one product write; WAL lets report reads proceed and serializes writers with bounded wait instead of `SQLITE_BUSY`. If the writer backs up, ingestion txns fail → 200 `accepted:0` → **load sheds onto bounded client queues, never onto product-route latency.** SM-3's 10× headroom test verifies the bound; past that, Postgres is the valve and this schema ports unmodified.

### 3.3 Critical edge paths

- **Pre-auth → sign-in stitch:** pre-auth rows persist as `device:` forever; sign-in appends a link row; stitching is purely query-time.
- **Evaluation:** config fetch → FR-33b targeting (header attrs + allowlist for device units; full registry for account units) → non-match = default, excluded from analysis → hash → persist assignment → return snapshot; client pins per `session_id`; `experiment_exposed` at first render, deduped per unit×exp×client-session, re-deduped at readout vs crash double-fires.
- **FR-32 stamping (ingest→engine coupling, fail-open):** `analytics_ingest.py` reads `experiments.py`'s read-only cache to know which surfaces/funnel events get stamped; **a missing stamp is never an error — analysis falls back to joining `experiment_assignments`.** The stamp is an optimization, structurally. Phase-order note: ingest ships in P1, the evaluator in P3 — P1 lands a guarded import/stub so the fail-open path is real code, not an ImportError at first deploy. The cache shape must carry both surface scope (*whether* to stamp) and per-unit variant resolution (*what* to stamp). No circular-import risk: nothing in the evaluator needs ingest.
- **Kill hierarchy, fastest first:** pause one experiment (≤60 s, DB-truth) → stage kill-flags via manual reload (≤minutes) → revert deploy (P0 cutover only, rehearsed). Client bounds: one backgrounding cycle on P1+ binaries, next cold start on older ones.
- **Deletion:** one transaction tombstones identity across `user_events`, `identity_links`, `experiment_assignments`; unit stops matching targeting next session.
- **Deploy-mid-everything:** sessions dict wiped → dead-token fallback keeps attribution correct (E-15); experiment cache wiped → reloads from DB (kill latency shortens, never lengthens); client persistent queues survive; `event_id` dedupe absorbs replays.
- **Time:** `occurred_at` is the only ordering authority; `client_ts` advisory for intra-session deltas, `ts_suspect` beyond 48 h; `seq` gaps make real loss measurable per session.

### 3.4 Storage choices and why

Everything in the existing SQLite file via SQLAlchemy Core — the PRD's constraints (zero deployables, portability, solo operator) rule out anything else. `user_events` extended, not forked: one events table keeps every report a single-table scan + one small join; additive columns are free NULLs for v1 rows. Write-path risk answered by WAL (finally actually on, boot-asserted), single-transaction batches, and SM-3 as a hard gate. Dialect discipline: exactly **three sanctioned dialect-aware spots**, each gated on `engine.dialect.name`: (1) ingestion's conflict-ignore insert helper (FR-5); (2) the SQLite PRAGMA listener + boot assertion — **applies only when dialect == 'sqlite'; on Postgres the Health tab reports "journal: n/a (postgres)" green**, never a false red and never a boot error (`PRAGMA journal_mode` is SQLite-only); (3) read-only engine construction (SQLite `mode=ro` file-URI vs a Postgres read-only role / `default_transaction_read_only`). Nothing else knows the dialect — those three plus `DATABASE_URL` are the whole Postgres seam.

## 4. Key Design Decisions (mini-ADRs)

**KD-1 — New domain = new module; `server.py` gains only ~5-line shims.** *Rejected:* inlining (9k-line file, NFR-6 wants documented boundaries); a `backend/analytics/` package (repo convention is flat modules; a package is a refactor no FR needs).

**KD-2 — Idempotency is the transaction protocol; load sheds outward, never inward.** Every cross-boundary partial failure is resolved by one side being immutable/append-only and the other derivable or replayable-with-dedupe. Overflow lives in bounded client queues and *dropped, counted* telemetry — never server memory, server retries, or product latency. Hence 200-on-overlimit, **200-with-`accepted:0` on txn failure** (a 5xx/Retry-After would revive the synchronized-retry-storm class FR-11 exists to kill; clients can't distinguish "try later" from "try forever" — bounded backoff + idempotent replay gives the same eventual outcome without the storm).
**Response-accounting invariant (the rule that makes this buildable):** every server-side drop — rate-limit (FR-11), allowlist/PII (FR-9) — counts as `accepted` ("accepted-and-dropped"), so on any successful transaction `accepted + deduped + |rejected| == N`. A whole-txn failure is the **only** case where the sum falls short. Client purge rule: `rejected` entries → purge always (client can't fix them); sum == N → purge the whole batch; sum < N → requeue everything not in `rejected`. Without this invariant, a builder's natural reading either silently loses batches (200 = purge all) or requeues dropped events forever. *Rejected:* ack ledgers, client txn logs, server-side buffering, background writer thread (in-process queues are lossy on deploy; clients' persistent queues are the durable buffer), Redis/broker (new deployable).

**KD-3 — Client rows bypass `record_event()` entirely.** The `users` dual-write is server-authoritative product state; client batches touching it would mint `users` rows for `device:` pseudo-identities and corrupt hot-column reads. *Rejected:* `record_event(dual_write=False)` flag — two call-site conventions in one function is how the named bug class re-enters.

**KD-4 — Reads and writes physically segregated at the connection level.** Admin/report queries run on a second **read-only engine** over the same WAL file: a table-scanning report can't hold the write lock, and buggy report SQL can't mutate. Snapshot posture: on-request now; precomputation scheduled by evidence (dashboard latency), not anxiety. *Rejected:* live page-load scans (FR-46 forbids); MVP snapshot cron (a scheduled job to babysit before any latency exists).

**KD-5 — Query-time identity stitching; never rewrite history.** Append-only links + one attribution rule in one module. *Rejected:* sign-in backfill/rewrite of `device:` rows (write-amplifying job that races ingestion, breaks append-only auditability, and hard-codes 1:1 device↔account, which shared devices violate).

**KD-6 — Extend `GET /api/feature-flags` additively; evaluator server-only; experiments get a TTL, boolean flags keep manual reload.** One config fetch path, one cache, one kill path per client; snapshot pinning gives N10. Adding a TTL to boolean flags is a behavior change to every existing consumer no FR requires (surgical-changes principle). *Rejected:* separate `/api/experiments/resolve` (second fetch/cache/kill path for zero gain); client-side hashing (leaks salts/targeting, breaks audit, FR-31 forbids).

**KD-7 — The evaluator is on the config-fetch path, not the request path.** Product routes read the 60 s cache; cost per config fetch is K hashes + one conflict-ignore insert, K = running experiments (single digits at beta). Fail-open try/except at exactly two seams. *Rejected:* per-request evaluation (hot-path tax, wider failure surface).

**KD-8 — Stats as a pure-function module.** No Flask/DB imports → golden-value tests against known vectors; scipy-vs-hand-rolled deferred to LLD (OQ-10) plus the one-time scipy re-derivation of Experiment #1. *Rejected:* stats inline with query code (untestable), notebook-only stats (not self-service).

**KD-9 — Dashboard is a static page + gated JSON; no framework.** Matches the vanilla-JS `web/` stack; makes "dashboard computes nothing" structurally true; JSON/CSV parity for role skills falls out free. *Rejected:* React admin app (new toolchain for one operator), server-rendered templates (couples SQL to presentation), BI tooling (N1).

**KD-10 — `aggression_ab` migrates by re-bucket, not continuity.** New sha256 bucketing, new version; v0 MD5-era props analyzable as an archived readout, never blended. *Rejected:* MD5-continuity shims (unverifiable membership equivalence, zero payoff).

**KD-11 — Operator fat-fingers are a first-class input.** Launch is guilty-until-validated (FR-33/33b); running experiments reject in-place mutation (FR-39); underpowered launches need a logged override (FR-42). The one fast lever is pause → default, which is always safe because default = the product as it exists. There is deliberately no fast lever that changes behavior in any other direction.

**KD-12 — Sunday-vs-SQLite is bounded, not solved, and the casualty ordering is *enforced*, not hoped for.** At some N, one writer is one writer. The design guarantees the *ordering of casualties* — analytics rows drop (counted) long before product p95 moves — via an explicit mechanism: **ingest-path transactions get a deliberately short lock-wait budget (~100–250 ms `busy_timeout` or immediate-busy → `accepted:0`), distinct from product writes' timeout.** Without this asymmetry, contended ingest txns would *wait* on a shared engine-wide timeout, occupying Flask worker threads, and the first 10× cliff would be WSGI worker exhaustion hitting product p95 directly — the exact inversion this KD forbids. Worker-thread occupancy is therefore the named contention surface, and SM-3's 10× headroom test measures **concurrent** ingest + product p95, not sequential runs. Postgres exit stays clean. *Rejected:* real queue/worker (a second deployable trades visible bounded loss for invisible unbounded ops surface).

## 5. Cross-Cutting Concerns

**Scalability & performance.** Client: append-only interaction cost, lazy queue init (<50 ms cold-start gate). Server: one bounded txn per batch; WAL removes reader-blocks-writer; 10× headroom test gates P1. Reads: index set finalized in LLD (`device_id`, existing `(event_type, occurred_at)`/`(user_id, occurred_at)`, plus assignment/snapshot indexes) targeting 3 s p95 @ 1M rows; rollup+prune plan written-not-built, 1M-row trigger. Postgres seam: `DATABASE_URL` + the three sanctioned dialect spots (§3.4).

**Reliability.** Fail-open uniform: SDK errors swallowed; ingestion never 4xxes for content; evaluator errors → default + counter; dashboard renders "—". Loss measured via `seq` gaps; duplication bounded by end-to-end `event_id` idempotency. The dead-token fallback and replay-dedupe paths get explicit tests — **they are routine paths, not edge cases.**

**Security & trust boundaries.** Three zones: (1) untrusted clients — may only append heavily-validated events and fetch resolved config values (salts, targeting rules, bucket math never leave the server); (2) operator — all admin/experiment-mutation routes behind `X-Cron-Secret` header (never query param), constant-time compare, rate-limited, fail-closed when unset, reusing `_require_cron_auth`; the static page holds zero data; `textContent`-only rendering blocks stored-XSS via event strings; (3) internal — evaluator/queries trust the DB. PII: server-side denylist at the boundary + client scrub for error messages; monthly regex sweep. Rotation procedure in runbook. One-secret blast radius accepted per N11; trigger for real auth = first non-Matt admin.

**Observability & operability.** Rule: **a degradation that doesn't produce a counter is a spec bug.** FR-13 counters, `seq`-gap sampling, 24 h volume, WAL boot assertion, evaluator fallback counters — all on the Health tab. Experiment health (SRM banners, guardrail alerts, dilution) on monitor cards. Deploys: P0/P2/P3 ordinary Render pushes; P1 rides EAS→TestFlight behind `analytics.client_events` (operator devices 48 h → all testers). Rollback: flag-off-without-deploy everywhere except the rehearsed P0 cutover. Docs land per phase (NFR-9); ADR at P0 so the decision trail predates dependent code.

**Testability.** Determinism (same unit ⇒ same variant), cross-layer independence χ², kill drill (SM-8), cutover double-count checks, golden-value stats tests + Experiment #1 scipy re-derivation, Maestro event assertions, dead-token/replay path tests (NFR-10).

## 6. Risks & Open Questions

**Residual risks:**

1. **WAL assumption self-verification (RB-1).** Everything in §3.2 presumes WAL; today it's off and the code comment lies. Boot-time assertion (`journal_mode=='wal'`) logged + Health-tab red makes the assumption self-verifying; enable in P0 *before* ingestion traffic exists and watch product p95 for a week.
2. **Read-only engine is protection, not isolation (RB-2).** A 3 s scan still competes for page cache/CPU. If SM-3 shows report-triggered jitter → snapshot cron (OQ-7) is the pre-planned upgrade; Postgres terminal.
3. **`funnel_critical` mis-tagging (RB-3).** A forgotten tag on a new critical event silently eats the rows the funnel needs under backlog. Tag list lives in `analytics_taxonomy.py` (shared, OQ-5 strengthens to CI); SM-2 gap analysis cut by event class.
4. **One secret, total blast radius (RB-4).** CRON_SECRET now gates cron + feedback admin + all behavioral data. Accepted at one operator; rotation runbook interim; real auth at first non-Matt admin.
5. **Stats wrongness is quieter than crashes (RB-5).** Golden-value tests necessary but not sufficient → one-time scipy re-derivation of Experiment #1 before verdicts are trusted.
6. **Attribution-rule drift (RB-6).** FR-21 is subtle enough to re-implement wrongly if any query bypasses `analytics_queries.py`. The rule + `device:` filter exist exactly once as shared fragments; NFR-10 pins E-15 behavior.
7. **Config-fetch contract skew (RB-7).** FR-38's client bound holds only for P1+ binaries; pre-P1 bounds at next cold start. Runbook states it; FR-34's version-predicate warning keeps client-UI experiments off old binaries.

**Deferred to the LLD:**
- Exact DDL: column types, full index set for 3 s @ 1M, migration shim text (partial unique index under `_migrate_db()`), WAL listener pragmas (`journal_mode`, `synchronous`, `busy_timeout` — **split budgets: short ingest-path, normal product-path**, per KD-12 — implemented via per-connection PRAGMA on checkout or a dedicated ingest engine, and `busy_timeout` is SQLite-only: the Postgres analogue is `SET LOCAL lock_timeout` or nothing (MVCC dissolves the class), so the split budget lands inside sanctioned dialect spots 1/2, not as an unsanctioned fourth — plus `wal_autocheckpoint`; note long read snapshots stall checkpointing and grow the WAL during report scans) + connect-event wiring, read-only engine setup (exact SQLAlchemy URI `sqlite:///file:…?mode=ro&uri=true` so read-only is engaged, not assumed) and pool sizing (benchmark on the actual Render instance class, not a laptop — HQ-3).
- OQ-10: scipy vs hand-rolled special functions (golden-value tests either way).
- Rate-limiter accounting (in-process vs table — stated property: the in-process option resets on every deploy, i.e. deploy = free rate-limit window; acceptable at these stakes but it must be a documented property, not a discovery) and health-counter persistence: counters feeding SM-2/SM-4 *verdicts* must be DB-derivable (`seq` gaps, dedupe rows); process-local counters are labeled "since last deploy" on the Health tab.
- FR-32 stamping mechanics (surface-scope registry shape in `experiments.py`'s cache).
- Snapshot window/rollup grain (cron-compatible for P4).
- Client queue file formats, flush backoff curve, `funnel_critical` tag propagation to three SDK ports.
- Dashboard secret-entry/rotation UX; Chalkline chart spec addendum (D-4).
