---
round: 02
direction: primary->subagent
thread: perf-optimization
date: 2026-06-07
author: primary
status: answered
surface: cross-client
references:
  - round-01-findings.md
  - ../../code-audit/perf-optimization/plan/optimization-plan.md
---

## Context
Audit + plan accepted. Implement Wave 1 (8 lowest-risk, highest-leverage
initiatives) via 6 parallel subagents on **disjoint file sets** (no two agents
share a file) on integration branch `feat/wave1-perf`. Primary owns all git +
verification + merge.

## Decisions on Prior Findings (locked architecture/infra calls)
- [accept] INIT-01/02/03/04/05/06/12a/14a for Wave 1.
- [defer] INIT-12b GET retry → Wave 2 (timeout + warm-dedup only in 12a).
- [decide] INIT-02 bake: `build.sh` fetches the cache at build time via the
  runtime path, **best-effort/non-fatal**; **no committed binary**; parallelize
  the dual-format CSV; reuse the players read. **Do NOT change `--workers`**
  (free-tier OOM risk).
- [decide] INIT-05: wire `focusManager` only; **skip `onlineManager`** (no
  NetInfo dep in Wave 1).
- [decide] INIT-12a timeout: 15 s GET / 30 s slow POST; warmed-once-per-launch.
- [decide] INIT-03: memoize + **golden ELO parity test** (pytest, `backend/tests/`).

## New Tasks (one per agent, disjoint files)
1. **M1** INIT-01+05 — `App.tsx`, `useFeatureFlags.ts`, `RootNav.tsx`, `queryClient.ts`.
2. **M2** INIT-04 — `TabNav.tsx`.
3. **M3** INIT-12a — `api/client.ts`, `api/sleeper.ts`, `api/auth.ts`.
4. **B1** INIT-02+06 — `server.py`, `data_loader.py`, `build.sh`.
5. **B2** INIT-03 — `ranking_service.py`, `tests/test_elo_memoization.py`.
6. **B3** INIT-14a — `database.py`.
**AC (all):** matches the relevant `design/requirements/init-0X-*.md`; no git;
edits only the assigned files; reports tsc/pytest status + invariant concerns.

## Out of Scope
- Wave 2/3 initiatives. Key-scoping (INIT-07) — flat keys stay for now.

## Touches
- The 11 files above + the new test file.
