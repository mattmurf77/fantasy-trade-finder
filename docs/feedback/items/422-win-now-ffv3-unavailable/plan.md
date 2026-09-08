# Feedback batch 2026-09-08 — plan (#422, #423, #424, #428)

Operator selection 2026-09-08: "spin up subagents to handle all of the bugs." Session branch `claude/feedback-422-428` from `origin/main` `2863362e`. All four take the **fast-track bug** path (no schema/API/flag change expected); every group fills a scope block. Older open items (42) were triaged 2026-09-06 and are not in this batch; #425–#427 (layout/valuation) were not selected.

| Group | Items | Canonical folder | Platforms | Path | Root-cause evidence at triage |
|---|---|---|---|---|---|
| G-428 | 428 | `428-sleeper-pick-send-refused/` | backend (+ mobile copy) | fast-track bug | Render 2026-09-08 17:03:52Z, FFV3 `1312140920132497408`: Sleeper GraphQL `"These draft picks cannot be traded."` → 502 `sleeper_write_failed`. Encoding reached Sleeper; Sleeper refused the picks. |
| G-422 | 422 | `422-win-now-ffv3-unavailable/` | backend | fast-track bug | 2026-09-06 17:50:19Z `GET /api/league/season-projections?league_id=1312140920132497408` → 200, 98-byte body (structured `unavailable`). Reason unknown at triage. |
| G-423 | 423, 424 | `423-team-review-not-registering/` | mobile | fast-track bug | Lakeview `1312076055586050048` review 17:56–17:58Z; every `POST /api/league/preferences` 200, final `outlook=rebuilder`; TradesHome still shows "Not set" and the review card never showed done. Client read/marker issue. |

File ownership is disjoint: G-428 owns `backend/server.py` pick paths + `backend/sleeper_write.py` + the relevant mobile copy in `SendInSleeperButton.tsx`; G-422 owns `backend/win_now_*.py` and `backend/outlook/`; G-423 owns `mobile/src/screens/TradesScreen.tsx`, `TeamReviewScreen.tsx`, `TeamReviewEntryCard.tsx` and related state. Backend groups finish before any mobile group touches shared files (none expected).

Phases: 1 mini-PRD + scope per group (one investigating planner each) → 2 one build agent per group in the session worktree on a group branch → 3 two QA agents per group (guards, pytest/tsc, code-walk proof of the repro path) → 4 resolution loop → 5 operator go/no-go, merge, Render, EAS.
