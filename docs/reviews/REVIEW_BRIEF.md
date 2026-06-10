# Deep code review — 2026-05-22

User-initiated. Specific user concern: **"the app just loads too slowly
when rendering an experience for the first time (the trios prompt,
etc)."** Plus a broader ask for inefficient code + silent bugs across
the product.

## Review tracks (one report per file)

Four subagents producing reports in this dir:

| File | Scope |
|---|---|
| `2026-05-22-backend.md` | Hot-path backend perf + silent bugs (`backend/server.py`, `backend/{database,trade_service,ranking_service,trends_service}.py`). N+1, missing indexes, blocking calls, silent except blocks. |
| `2026-05-22-mobile-render.md` | Mobile first-render perf with Trios as primary case study. Cold-start path for Trios / Trades / Tiers / League. Skeleton coverage, sequential fetches, blocking UI. |
| `2026-05-22-silent-bugs.md` | Cross-cutting silent-bug sweep: `try/except` that hides real failures, race conditions, state inconsistencies, untested error paths. |
| `2026-05-22-api-layer.md` | API + query layer review. Web `app.js` + mobile `src/api/` + TanStack Query configs. Cache invalidation, duplicate fetches, polling cadences, type drift between client / server. |

Each report follows the same template:
1. Top 5 findings ranked by ROI (symptom / cause / fix / effort / impact / risk)
2. Lower-priority findings (1-line each)
3. What was checked and found clean
4. Open questions for the user

After all four land, synthesis + prioritized action list goes in
`2026-05-22-SUMMARY.md`.

## Why now

Recent context:
- 12 PRs merged today addressing user feedback (#48–60).
- Multiple bugs traced to silent failures (e.g. PR #58 worktree contamination, #55 unbounded queries, #51 dropped `g_league` precondition, #60 coord-space mismatch).
- User reports slow Trios load on cold start — Render free-tier dyno wake is part of it but probably not all.
- Earlier perf audit (`docs/feedback/perf-audit-2026-05-21.md`) covered top-level cold-start wins (warm endpoint, progressive paint) but didn't dig into per-screen first-render or backend hot paths.

## Out of scope

- Code style nits (we have CLAUDE.md for those)
- Architectural rewrites
- Anything that would need its own design doc
