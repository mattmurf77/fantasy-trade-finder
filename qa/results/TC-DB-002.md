# TC-DB-002 — DB concurrency, write integrity, recency bounds

| Field | Value |
|---|---|
| **Status** | PASS (5/5 checks) |
| **Date executed** | 2026-06-11 |
| **Layer** | db |
| **Component(s)** | `upsert_member_rankings` (delete+insert replace), `save_trade_decision`, `save_ranking_swipes`, `check_for_match` (90-day window); SQLite WAL |
| **Requirement / doc ref** | data-dictionary.md atomic-replace invariants; check_for_match recency |
| **Engine path & flags** | n/a; SQLite scratch |

### Objective
Verify write paths stay correct under thread concurrency (no corruption, no lost
writes, no lock errors) and that the match-recency window is enforced.

### Scope
- **In scope:** concurrent member_rankings replace (atomicity), concurrent
  distinct trade decisions (no loss), concurrent ranking swipes (WAL under
  contention), 90-day match recency bound.
- **Out of scope:** Postgres pool saturation (recon item — needs a real
  multi-process load test); append-only pruning policy.

### Actual Result
**5/5 PASS.** 8 concurrent upserts of a 20-row snapshot → exactly 20 rows (atomic
replace, no accumulation), 0 errors. 16 concurrent distinct decisions → all 16
persisted. 8 concurrent rankings → 24 swipe rows, **no "database is locked"** (WAL
holds). Fresh mirror like matches; a >90-day-old like is correctly excluded.
Evidence: `qa/db/scratch/TC-DB-002-run.json`.

### Outcome
**PASS** — write integrity holds under concurrency at thread scale; the recency
bound works.

### Findings requiring attention
| ID | Severity | Finding | Evidence | Suggested action |
|---|---|---|---|---|
| — | — | No defects at thread-concurrency scale. | | |

### Observations & feedback (no change required)
- **Atomic-replace is genuinely atomic under contention** — 8 threads racing to
  delete+insert the same snapshot landed exactly one snapshot's worth of rows,
  not a mix or a doubling. The per-call `engine.begin()` transaction boundary is
  doing its job.
- **SQLite WAL handles thread-level write contention cleanly** at this scale
  (`check_same_thread=False` + WAL). The recon pool-saturation concern is a
  *Postgres multi-process* question (Render with gunicorn workers), not
  reproducible with threads on SQLite — still the right follow-up before scale,
  but the local layer is sound.
- The 90-day `check_for_match` window means a stale like silently stops being
  matchable — good for relevance, but worth knowing it's a *silent* expiry (a
  user who liked a trade 3 months ago won't match even if the counterparty likes
  the mirror today).
