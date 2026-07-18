# HLD Reconciliation Log — Analytics & Experimentation Platform

**Document type:** HLD · **Rounds run:** 3 · **Converged:** yes (both lenses signed off, round 3)
**Lenses:** Agent A = Architecture-Coherence · Agent B = Failure-Modes/Scale (adversarial). Round 1 = two independent drafts; candidate synthesized; rounds 2–3 = cross-review. (Two transient API failures during the loop — one draft, one review — were resumed/relaunched without content loss.)

## Round 1 → synthesis

Drafts were highly convergent (same module decomposition, same storage posture, both derived from the validated PRD). Synthesis took A's structure (module/FR traceability table, KD set, repo-convention grounding) and folded in B's failure-envelope discipline (failure mode → degradation → blast-radius per component) plus B-only hardening: **read-only second engine** for all report queries; **WAL boot assertion** (log + Health-tab red, not refuse-to-serve); **txn-failure → 200 `accepted:0`** semantics (B's HQ-1, resolved per B's own position); **FR-32 stamping as fail-open coupling** with assignment-join fallback (HQ-4); serialized client flushes; corrupted-queue discard rule; one-time scipy re-derivation of Experiment #1; "a degradation that doesn't produce a counter is a spec bug."

## Round 2

**A: sign-off yes** (no blocking). Non-blocking ownership-table gaps adopted: FR-24 server half + FR-2 write side added to the server-call-sites row; FR-37 readout-side dedupe assigned to `analytics_queries.py`; rate-limiter deploy-reset stated as a property; FR-9 split notation.

**B: 3 blocking (code-verified) → resolved:**
1. **Response-accounting invariant unstated** — counts can't tell a client what to purge; accept-and-drop classes would break the sum and cause either silent batch loss or infinite requeue → KD-2 now states: drops count as `accepted`; `accepted+deduped+|rejected| == N` on any successful txn; whole-txn failure is the only short-sum case; explicit purge rule.
2. **Casualty-ordering guarantee had no enforcing mechanism** — a shared engine-wide `busy_timeout` would make contended ingest txns *wait*, exhausting WSGI workers and hitting product p95 first (the exact inversion the design forbids) → KD-12 now mandates a short ingest-only lock-wait budget (~100–250 ms) distinct from product writes, names worker-thread occupancy as the contention surface, and pins SM-3 to concurrent measurement.
3. **Dialect claim contradicted the design; WAL assertion broke Postgres portability** (PRAGMA is SQLite-only → boot error or permanent false-red Health tab after migration) → §3.4 now enumerates three sanctioned dialect-gated spots (insert helper; sqlite-gated PRAGMA listener + assertion with "n/a (postgres)" green; read-only engine construction).

**B non-blocking adopted:** `wal_autocheckpoint` + checkpoint-stall note + exact `mode=ro&uri=true` URI in the LLD deferrals; DB-derivable SM-2/SM-4 counters with "since last deploy" labeling; FR-32 P1 guarded stub + cache-carries-scope-and-variant; "rate limiting is new code" honesty on the admin gate.

## Round 3

**B: sign-off yes** — verified all three fixes and their cross-references compose consistently. **A: sign-off yes** — full FR-1..48 re-sweep: every FR has exactly one labeled owner (or labeled half), no orphans, no new contradictions. Final polish applied from round-3 non-blocking notes: §3.2 step-4 purge-rule reference, split-budget-inside-spot-2 note for the LLD, §5 "one dialect helper" → "three sanctioned dialect spots".

## Unresolved disagreements

None — both lenses signed off. (All four of B's round-1 HQ questions were resolved inside the loop: HQ-1 → KD-2; HQ-2 → log+red assertion; HQ-3 → LLD benchmark on the real Render instance; HQ-4 → fail-open stamping fallback.)
