# LLD Reconciliation Log — Analytics & Experimentation Platform

**Document type:** LLD · **Rounds run:** 4 (protocol cap) · **Converged:** yes — both lenses' final objections were one identical one-line literal, applied verbatim; no unresolved disagreements.
**Lenses:** Agent A = Implementer ("can I code from this?") · Agent B = Reviewer (adversarial; "what breaks in review or production?").

## Round 1 → synthesis

Independent drafts converged on structure; synthesis took A's DDL/pipeline/stats detail and B's adversarial specifics (named races RC-1..7, timeout budget table, resource caps, ISO-Monday-UTC week definition, layer-salt-in-DB immutability rules, sessionStorage secret UX, cutover boundary constant in `model_config`). Load-bearing disagreement resolved in A's favor: **the parents' single assignment hash cannot deliver in-layer mutual exclusivity** — a two-stage hash (experiment-independent layer bucket + experiment-keyed variant bucket) is required → [AMEND] up to PRD FR-31/framework §D2. Both drafts independently decided OQ-10 the same way: no scipy; stdlib `math.erf` + hand-rolled `betainc`/`gammainc` with committed scipy-generated golden fixtures.

## Round 2 — the big one

**A: 1 blocking** — snapshot-builder home contradicted the module's own only-`ro_engine` invariant and HLD §2.2's ownership → resolved with a scoped engine rule (`build_snapshots()` = the module's single sanctioned primary-engine writer) + [AMEND — HLD §2.2].

**B: 10 blocking, all code-verified — headlined by the discovery that the LLD was written as greenfield while the working tree already contained a v0 implementation** (built by a parallel work stream directly from tracking plan v2, predating the PRD/HLD refinements): the shipped `/api/events` route (404-on-flag-off / 400s / **429**, `{accepted, dropped}`), per-row `insert_client_events()`, `identity_links` already declared, a **full** unique `event_id` index, the allowlist inline in `server.py`, and a v0 `events.ts`. Resolutions:
1. New **§1.1 shipped-baseline reconciliation**: rewrite-in-place rule (never duplicate tables/routes), old-binary tolerances, accepted transition losses.
2. **Full unique index kept** (NULLS DISTINCT is legal on both dialects — the draft's "review trap" rationale was factually wrong); conflict helper loses `index_where`.
3. Separate `_sqlite_on_connect_ingest` listener — attaching the shared listener would let its `busy_timeout=5000` PRAGMA silently destroy the 150 ms ingest budget (T-23b).
4. **RC-8**: `BEGIN IMMEDIATE` for ingest txns — a deferred txn's SELECT-then-INSERT fails its lock upgrade instantly (`SQLITE_BUSY_SNAPSHOT`, busy handler not invoked) under exactly the Sunday burst the design centers on.
5. `disposition:"disabled"` semantics bounded: retain queue, jump to max backoff, stop timers while the flag is off.
6. Cutover reader fixed to `wrapped_events.created_at` (the column that exists) + `payload_json`→`props` mapping.
7. `variant_overlay()` defined as the full second evaluation seam (server call sites serve users who never fetch config — web until P4, pre-P1 binaries — otherwise Experiment #1's dilution/SRM is poisoned).
8. §6.4b FR-20 call-site table (`quickset_completed`, `quickrank_completed`, `trades_generated`, **`calc_trade_evaluated`** — zero call sites in tree; six others verified already landed by the v0 stream).
9. `health` removed from the report enum (two responses claimed one URL; Werkzeug would dead-letter the enum entry).
10. **RC-5 leak closed**: tombstone extends to `wrapped_events.user_id` → [AMEND — PRD FR-22]; deletion response instructs SDK queue purge.

**Non-blocking adopted:** version in the variant-hash preimage (carryover-bias fix, folded into the FR-31 [AMEND]); sleeper→acct unit resolution through `identity_links`; expo-crypto UUIDs (v0's `Math.random` fallback unsafe for an idempotency key); whole-batch rate-limit granularity; §4.6b foreground-refetch spec; status-machine edge list; admin body schema; gamma iteration caps; symbol-based grounding anchors.

## Round 3

**A: 2 blocking** (leftover-phrasing sweeps) — partial-index residue in I-1/I-4/T-1 + the full-index deviation missing from the [AMEND] list → fixed, [AMEND] (d) added; `illegal_transition` 400-vs-409 contradiction → unified to 409, DELETE-drafts route added. Non-blocking: `dropped` added to the §2.1 schema, purge-rule cross-references, T-23b row.

**B: 1 blocking** — the same partial-index residue (concurrent review of the same candidate; fix already applied). B also **empirically tested the BEGIN IMMEDIATE recipe on SQLAlchemy 2.0.49** (works as written). Non-blocking adopted: §1.1 v0 factual corrections (purge 2xx/4xx, retry 5xx, body never parsed — `dropped` reframed observability-only), AsyncStorage key reuse (`ftf.events.queue.v1`), `isolation_level = None` in the ingest listener + OperationalError wraps `begin()` entry, `ix_identity_links_device_linked` new-name (IF-NOT-EXISTS no-op trap).

## Round 4 (cap)

Both lenses confirmed every delta; both raised the **same single new blocker** — the §1.1 key-reuse fix hadn't been propagated to §3.4's queue-key literal (`ftf.events_queue_v1` vs shipped `ftf.events.queue.v1`) → fixed verbatim as both prescribed, plus the stale `ix_identity_links_device` reference in §4.7 and "full" in I-4. Cap reached with the prescribed one-liners applied and nothing else open — recorded as converged.

## Unresolved disagreements

None.

## Amendments — disposition

**Applied to parents (intra-doc-set corrections, annotated in place):** PRD FR-1 + HLD §3.1 (full unique index); PRD FR-22 (wrapped_events tombstone + SDK purge); PRD FR-31 (two-stage hash + version in preimage); HLD §2.2 (snapshot-builder home).
**Pending operator approval (strategy-layer docs, per Decisions Needed):** experimentation-framework §D2 (two-stage hash formula + device-unit attribute limits), §D4 (envelope stamping scope), §D5 Decision 2 (mSPRT → v2); tracking-plan §S2 (`seq` envelope field).

## Process note

The v0 implementation discovered in round 2 was produced by a **parallel work stream in the same working tree** during this design effort — the LLD now treats it as the §1.1 baseline and every spec as a rewrite-in-place. Builders should re-diff §1.1 against the tree at P0/P1 kickoff in case that stream has moved further.
