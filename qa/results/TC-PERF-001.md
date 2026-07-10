# TC-PERF-001 — Performance: cold-start, warm latency, concurrent load, budgets

| Field | Value |
|---|---|
| **Status** | PASS (9/9 checks) |
| **Date executed** | 2026-06-11 |
| **Layer** | perf |
| **Component(s)** | server boot + player sync, `session_init` ranking-service build, `/api/trades/generate` async job, per-opponent enumeration budget |
| **Requirement / doc ref** | qa/README.md §6 budgets |
| **Engine path & flags** | default flags; SQLite scratch (local) |

### Objective
Measure the backend against the charter budgets and confirm graceful behavior
under concurrent load.

### Scope
- **In scope:** cold boot, cold/warm session_init, warm GET p50/p95, generate
  end-to-end, per-opponent enumeration bound, 8-way concurrent init+generate,
  error-free-under-load.
- **Out of scope:** Postgres-backed latency (SQLite local only — prod numbers
  will differ), real Sleeper-fetch cold path in session_init (synthetic league),
  sustained soak/memory-growth.

### Actual Result (measured, local)
| Metric | Measured | Budget |
|---|---|---|
| Cold boot (incl. 2,684-player sync) | **1.0 s** | < 90 s |
| Cold session_init | **338 ms** | < 30 s |
| Warm session_init | **241 ms** | < 5 s |
| Warm GET p50 / p95 / max | **20 / 58 / 60 ms** | p95 < 500 ms |
| Trade generate (31 cards) | **1.28 s** | < 30 s |
| Cached re-generate | **~0 ms** | — |
| 8 concurrent init+generate | **0.2 s wall, all complete, 0 errors** | < 30 s |

All 9/9 PASS. Evidence: `qa/perf/scratch/TC-PERF-001-run.json`.

### Outcome
**PASS** — comfortably within every budget at this data scale; no errors,
deadlocks, or pathological tails under concurrency.

### Findings requiring attention
| ID | Severity | Finding | Evidence | Suggested action |
|---|---|---|---|---|
| — | — | No defects at tested scale. | | |

### Observations & feedback (no change required)
- **Honest scope caveat on the concurrency test:** the 8 workers all use the
  same fixture user, so they share the module-level trade-job cache (keyed on
  user+league+format) — the 0.2 s wall reflects cache-hit sharing, not 8
  independent generations. What it *does* prove: the session store + job cache
  are thread-safe under contention with zero errors/tracebacks. A true
  throughput test needs N distinct users (blocked by fixture-data breadth) and
  is the right follow-up before a real launch.
- **The real prod perf risks are not exercised here** and remain the recon
  items: (1) cold Sleeper fetch inside `session_init` on Render (synthetic
  leagues skip it / 404 fast), and (2) v3 exact enumeration without a time
  budget on a *large* roster league. This test confirms the v2 path's per-opponent
  budget holds; a v3-on large-league perf case belongs in a later cycle.
- **SQLite default pool** showed no contention at 8 concurrent; the recon
  pool-saturation concern is real only at higher concurrency on Postgres — worth
  a Render-side load test before scale, not reproducible locally.
