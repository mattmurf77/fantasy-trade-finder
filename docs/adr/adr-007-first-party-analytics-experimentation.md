# ADR-007 — First-Party Analytics Platform + Layered Experimentation

**Status:** Accepted (P0 shipped; P1–P3 phased per the LLD)
**Date:** 2026-07-17
**Initiative:** Analytics & Experimentation Platform (docs/plans/analytics-platform/{prd,hld,lld}.md — all dual-agent validated). Builds on the tracking-plan-v2 §S1/S2 baseline already in the tree.

---

## Context

The product needs funnel/retention/experiment measurement across mobile, web, and extension. Server-fired `user_events` already exist (one append-only lineage with denormalized `users.last_*_at` pointers), a v0 `POST /api/events` client-ingest route shipped from tracking plan v2, and a parallel `wrapped_events` table collected a second, narrower event stream for the Wrapped recap. Third-party options (Amplitude/Mixpanel/PostHog/Statsig) were evaluated in the PRD.

## Decision

1. **Build, don't buy.** First-party analytics on the existing Flask + SQLAlchemy Core + SQLite(→Postgres) stack. Rationale: full-fidelity raw events in our own DB (joinable to leagues/trades/rankings), no per-MTU pricing cliff, no PII export surface for legal review, and the experimentation layer needs server-side config the SaaS free tiers don't give us. Cost accepted: we own correctness (mitigated by the LLD's named invariants + test map).
2. **One lineage: extend `user_events`.** Client events land in the same table as server-fired events via six nullable envelope columns (`event_id, device_id, platform, screen, client_ts, experiments`) — not a second events table. Server rows keep `event_id = NULL` forever; client rows always carry `event_id` + `device_id` (invariant I-1). Pre-auth rows use `user_id='device:<id>'`, stitched by `identity_links`.
3. **Full unique index on `event_id`** (`ix_user_events_event_id`) — not the partial `WHERE event_id IS NOT NULL` index earlier drafts specified. Both SQLite and Postgres default to NULLS-DISTINCT, so unlimited NULL (server) rows coexist legally on both dialects; the partial-index "Postgres port trap" rationale was wrong. Consequence: conflict-ignore inserts must target the index **without** `index_where` (a partial predicate fails to match a full index on Postgres). This is the idempotency keystone for client retries.
4. **Two-stage hash for experiment bucketing** (amendment to PRD FR-31's single formula): `layer_bucket = h(layer_salt:unit_id)` places a unit once per layer (in-layer mutual exclusivity — impossible with an experiment-keyed single hash), then `variant_bucket = h(layer_salt:key:version:unit_id)` splits arms, with `version` in the preimage so revisions don't re-assign the same units to correlated arms. Ranges half-open `[lo, hi)`; layer salts are DB rows, minted once, never rotated in place.
5. **`wrapped_events` frozen at a cutover instant** (`analytics.wrapped_cutover_at` in `model_config`, epoch seconds): all five wrapped writers now go through `record_event()` into `user_events` (`league_sync`→`league_synced`; `tier_save` joins `_RANK_STREAK_EVENTS`), and the Wrapped/activity narrative reads the union split on each table's own timestamp column. Zero writes to `wrapped_events` after the cutover deploy.
6. **Engine split on one DB (SQLite):** WAL + `synchronous=NORMAL` on the product engine; a dedicated `ingest_engine` with a 150 ms lock budget + `BEGIN IMMEDIATE` so Sunday ingest bursts shed instead of stalling product writes; a read-only `ro_engine` for report queries. Event taxonomy is centralized in `backend/analytics_taxonomy.py` with an import-time client/server namespace-disjointness assertion.

## Consequences

- **Positive:** every metric joins directly to product tables; experiments ride the existing flags endpoint; kill switches are flags; the whole platform deploys with the app (no vendor SDK in clients).
- **Negative / accepted:** we own stats correctness (hand-rolled special functions with committed scipy-generated golden vectors, LLD §4.5), in-process counters/limiters reset on deploy, and SQLite write-lock discipline is ours to enforce (T-22/T-23 harnesses).
- Rollback story: analytics ingest and experiments are flag-gated; the only non-flag rollback is the wrapped cutover, which is a rehearsed revert deploy (runbook).
