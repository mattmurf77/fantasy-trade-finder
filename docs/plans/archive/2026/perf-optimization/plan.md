# Plan: Mobile Player & Trade Fetch Performance

**Thread slug:** `perf-optimization`
**Started:** 2026-06-07
**Trigger:** User report — "the mobile app takes too long to fetch players & trade information."

## Goal

Make the FTF mobile app's player + trade data fetch/load feel fast, via a
research → audit → plan → design → phased-implementation pipeline. Ship the
optimizations in low-risk waves, verifying each.

## The headline reframing (most important context)

The audit proved the obvious suspect — the **4.84 MB player payload** — is
**not** on the mobile critical path. Mobile fetches a 25-byte
`/api/sleeper/players/warm` ping (not the full body), and RN auto-negotiates
gzip; Cloudflare already compresses at the edge. The full payload is a **web**
concern. The real mobile latency is:

1. **Boot sequencing** — splash gated on a network warm-ping the first screen
   doesn't need (top finding, RICE-P 16.0).
2. **Cold-start cache population** — cold dyno re-fetches ~5 MB from upstream
   Sleeper on the critical path.
3. **Redundant backend recompute** — ELO recomputed 3–4× per rank request;
   `session_init` rebuilds both formats synchronously.
4. **Client cache gaps** — prefetch only Trios; no persisted cache; dead
   `refetchOnWindowFocus`.

Underneath all of it: the **Render free-tier cold start** (30–60 s wake,
`--workers 1`) — the irreducible floor no client trick fully removes.

## Deliverables (all produced)

The full audit + design lives in **`docs/code-audit/perf-optimization/`**
(on branch `audit/perf-optimization`, NOT yet merged to main):
- `research/` — 5 external best-practice deep-dives
- `observations/` — 6 codebase audits, **38 RICE-P-scored findings**
- `plan/optimization-plan.md` + `plan/priority-matrix.md` — **16 consolidated
  initiatives**, 3 waves, with incorporate/alternative/defer/reject decisions
- `design/hld.md`, `design/lld.md`, `design/requirements/init-01..16-*.md` —
  feature-by-feature requirements (user stories, ACs, prerequisites, invariants)

## Waves

- **Wave 1 (SHIPPED to main, PR #66):** INIT-01 splash decouple, INIT-02
  cold-cache bake+parallelize, INIT-03 ELO memo, INIT-04 nav prefetch, INIT-05
  focusManager, INIT-06 touch throttle, INIT-12a timeout+warm-dedup, INIT-14a
  position index.
- **Wave 2 (NEXT, mostly autonomous):** INIT-07 persisted cache + key scoping,
  INIT-08 optimistic session_init shell, INIT-09 trade-gen prune, INIT-10 web
  payload [W], INIT-11a render memo wins, INIT-12b GET retry, INIT-13 poll
  backoff, INIT-14b DB hygiene.
- **Wave 3 (larger/lower-priority):** INIT-11b Tiers virtualization, INIT-08
  Option B snapshot replay, INIT-15 docs, INIT-16 league double-fetch,
  StrengthBar slivers.

## Standing rules

- Implementation must be surgical (`docs/coding-guidelines.md`).
- Anything touching ELO math / K-factors / tier bands / per-format
  independence ships behind a **byte-for-byte golden test** (cross-client
  invariant, `docs/cross-client-invariants.md`).
- Subagents work on **disjoint file sets** (no two agents share a file) so
  parallel runs don't collide; the primary owns all git + verification + merge.

## Linked
- Audit tree: `docs/code-audit/perf-optimization/` (branch `audit/perf-optimization`)
- Wave-1 merge: PR #66 → `main` commit `464a7a2`
