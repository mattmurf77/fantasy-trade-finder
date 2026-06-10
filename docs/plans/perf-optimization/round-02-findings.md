---
round: 02
direction: subagent->primary
thread: perf-optimization
date: 2026-06-07
author: 6 impl agents
status: answered
surface: cross-client
references:
  - round-02-task.md
---

## Summary
- All 8 Wave-1 initiatives implemented by 6 agents on disjoint files; reviewed,
  regression-tested, merged to `main` (**PR #66, commit `464a7a2`**).
- Verification: mobile `tsc` clean · backend `pytest` **28 passed** (19 prior +
  9 new ELO golden tests) · `py_compile` OK.
- **B2 caught + fixed a spec bug:** keying the ELO memo on `_version` alone
  would be wrong (the methods are pool-dependent); corrected to
  `(_version, pool-fingerprint)` with a dedicated collision test.

## Findings (per agent)
### M1 — INIT-01 splash decouple + INIT-05 focusManager
Boot gate now awaits only `bootstrap()` + `loadCachedFlags()`; tier-config,
flag-revalidate, warm-ping detached. `useFeatureFlags.load` split into
`loadCachedFlags()` + `revalidateFlags()`. `focusManager`→AppState wired;
`onlineManager` TODO'd. Verified trio deck inherits global
`refetchOnWindowFocus:false` → no mid-swipe reshuffle on resume.

### M2 — INIT-04 nav prefetch
Extended Trios prefetch to Tiers/Overall/Manual (RankMenu) + Trades/Matches
(tab-press). Keys/queryFns verified per destination. Trends skipped (runtime-arg
keys). Flat keys kept (scoping = Wave 2).

### M3 — INIT-12a timeout + warm dedup
`client.ts`: hand-composed AbortController + caller signal (avoids
`AbortSignal.any/.timeout` for Hermes); 15 s/30 s; timeout-vs-cancel via
`ApiError.isTimeout`. `sleeper.ts`: `warmedThisLaunch` flag + `resetWarmedFlag()`.
`auth.ts`: `session_init` "not cached" recovery resets flag + re-warms + retries
once.

### B1 — INIT-02 cold-cache + INIT-06 touch throttle
`build.sh` bakes the cache via the runtime path (non-fatal). `_ensure_universal_pools`
parallelizes the dual-format DP CSV (ThreadPoolExecutor, graceful per-format
failure); players read once across both builds. `touch_user_activity` throttled
to ≤1 write/min/user (`TOUCH_THROTTLE_S=60`), first-request still touches,
session-expiry unaffected.

### B2 — INIT-03 ELO memo + golden tests
Memoize `_compute_elo`/`_compute_stats` keyed by `(_version, pool-fingerprint)`.
Audited all 6 `_version` bump sites; flagged (without changing) that
`replay_from_db` *sets* version (safe — only called on fresh instances).
9 new golden tests assert byte-for-byte ELO parity + version invalidation +
single-compute-per-request.

### B3 — INIT-14a index
`ix_players_position` appended to `_hot_path_indexes` (idempotent, dialect-safe).

## Proposed Changes (all shipped in PR #66)
- `[MOBILE]` `App.tsx`, `useFeatureFlags.ts`, `TabNav.tsx`, `api/{client,sleeper,auth}.ts`
- `[BACKEND]` `server.py`, `ranking_service.py`, `database.py`, `data_loader.py`, `build.sh`, `tests/test_elo_memoization.py`

## Answers to Questions
n/a

## Open Questions (carried to round 03 / questions-for-user)
1. Build-time bake imports full server (init_db + daemon + a reference-data DB
   write at build) — harmless/non-fatal but a fetch-only script is a possible
   refinement. (Primary's call; not a user input.)
2. Infra cold-start mitigation — user decision (questions-for-user #1).

## Evidence
- PR #66 → `main` `464a7a2`.
- `artifacts/wave-status-matrix.md` — per-initiative state.
- Primary's review verified: `concurrent.futures` import present (server.py:18),
  `last_active`/session-expiry interaction safe, timeout signal composition correct.
