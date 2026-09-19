---
round: 01
direction: primary->subagent
thread: perf-optimization
date: 2026-06-07
author: primary
status: answered
surface: cross-client
references:
  - plan.md
---

## Context
User reported the mobile app is slow to fetch players & trade info. Kicked off a
full research → audit → synthesis → design pipeline before writing any code, so
optimization effort is grounded in measured findings, not guesses.

## New Tasks
1. **Research** — 5 parallel agents produce external best-practice deep-dives
   (mobile data-fetching, backend API perf, caching, RN rendering, network/
   cold-start) into `docs/code-audit/perf-optimization/research/`.
   **AC:** 5 docs following `research/00-research-methodology.md`.
2. **Audit** — 6 parallel agents audit the codebase (API client, data-fetch/
   cache, backend routes, backend data/DB, RN rendering, network/cold-start),
   observation-only, writing RICE-P-scored findings to `observations/agent-0X-*/`.
   **AC:** 6 observation sets, every finding cites `file:line` + RICE-P + latency
   delta. Use the templates in `templates/` (scoring-criteria, observation-template,
   recommendation-example).
3. **Synthesize** — consolidate findings into a prioritized plan
   (`plan/optimization-plan.md` + `plan/priority-matrix.md`), merging overlapping
   observations into initiatives with incorporate/alternative/defer/reject calls.
4. **Design** — `design/hld.md`, `design/lld.md`, and one feature-requirement
   file per initiative (`design/requirements/init-0X-*.md`) with user stories,
   ACs, related + prerequisite components, invariants.

## Out of Scope
- Any application code changes (audit is observation-only).

## Touches
- `docs/code-audit/perf-optimization/**` (new tree) only.
