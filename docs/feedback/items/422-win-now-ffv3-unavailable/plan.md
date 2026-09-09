# Feedback batch 2026-09-08 — plan (#422, #423, #424, #428)

Operator selection 2026-09-08: "spin up subagents to handle all of the bugs." Session branch `claude/feedback-422-428` from `origin/main` `2863362e`. All four take the **fast-track bug** path (no schema/API/flag change expected); every group fills a scope block. Older open items (42) were triaged 2026-09-06 and are not in this batch; #425–#427 (layout/valuation) were not selected.

| Group | Items | Canonical folder | Platforms | Path | Root-cause evidence at triage |
|---|---|---|---|---|---|
| G-428 | 428 | `428-sleeper-pick-send-refused/` | backend (+ mobile copy) | fast-track bug | Render 2026-09-08 17:03:52Z, FFV3 `1312140920132497408`: Sleeper GraphQL `"These draft picks cannot be traded."` → 502 `sleeper_write_failed`. Encoding reached Sleeper; Sleeper refused the picks. |
| G-422 | 422 | `422-win-now-ffv3-unavailable/` | backend | fast-track bug | 2026-09-06 17:50:19Z `GET /api/league/season-projections?league_id=1312140920132497408` → 200, 98-byte body (structured `unavailable`). Reason unknown at triage. |
| G-423 | 423, 424 | `423-team-review-not-registering/` | mobile | fast-track bug | Lakeview `1312076055586050048` review 17:56–17:58Z; every `POST /api/league/preferences` 200, final `outlook=rebuilder`; TradesHome still shows "Not set" and the review card never showed done. Client read/marker issue. |

File ownership is disjoint: G-428 owns `backend/server.py` pick paths + `backend/sleeper_write.py` + the relevant mobile copy in `SendInSleeperButton.tsx`; G-422 owns `backend/win_now_*.py` and `backend/outlook/`; G-423 owns `mobile/src/screens/TradesScreen.tsx`, `TeamReviewScreen.tsx`, `TeamReviewEntryCard.tsx` and related state. Backend groups finish before any mobile group touches shared files (none expected).

Phases: 1 mini-PRD + scope per group (one investigating planner each) → 2 one build agent per group in the session worktree on a group branch → 3 two QA agents per group (guards, pytest/tsc, code-walk proof of the repro path) → 4 resolution loop → 5 operator go/no-go, merge, Render, EAS.

## Added 2026-09-08 (operator: "spin up another subagent to start working on the polish items")

| Group | Items | Canonical folder | Platforms | Path | Notes |
|---|---|---|---|---|---|
| G-425 | 425, 426 | `425-overhaul-tile-replaces-draft/` | mobile | polish | Overhaul entry replaces the Draft entry on the Acquire landing; make it prominent. Design-system tension: no red action accent exists (ice = actions, flare = highlights); build the hero tile in the sanctioned palette with the color as one token, and surface the "true red" question to the operator. Owns `TradesScreen.tsx` entry region, `OverhaulEntryCard.tsx`, `TradeFinderModeBar.tsx` (Draft chip) — disjoint from G-423 (which owns only the TradesScreen label alias at ~L9843 and the calculator/review files). |
| G-427 | 427 | `427-first-round-picks-stud-tax-exempt/` | backend (affects deck, calculator, web via the shared evaluator) | polish (valuation) | First-round picks are not devalued by the stud adjustment; two firsts straight up for a player in the "2 firsts" ladder tier evaluates even; other rounds still taxed. Owns the stud-tax code in `backend/trade_service.py` (and `pick_values.py` if the rule lives there) + its tests; no schema/API/flag change. |

## Final status 2026-09-08 (SHIPPED)

| Item | Group | Status | Evidence |
|---|---|---|---|
| 422 | G-422 | QA-green, shipped | [prd](prd.md) · [qa A](qa-round-1-agent-A.md) · [qa B](qa-round-1-agent-B.md) |
| 423 | G-423 | QA-green (2 rounds), shipped | [prd](../423-team-review-not-registering/prd.md) · [qa r2 A](../423-team-review-not-registering/qa-round-2-agent-A.md) · [qa r2 B](../423-team-review-not-registering/qa-round-2-agent-B.md) |
| 424 | G-423 | satellite of 423 | — |
| 425 | G-425 | QA-green, shipped | [prd](../425-overhaul-tile-replaces-draft/prd.md) · [qa A](../425-overhaul-tile-replaces-draft/qa-round-1-agent-A.md) · [qa B](../425-overhaul-tile-replaces-draft/qa-round-1-agent-B.md) |
| 426 | G-425 | satellite of 425 (red pending token decision) | — |
| 427 | G-427 | QA-green, shipped | [prd](../427-first-round-picks-stud-tax-exempt/prd.md) · [qa A](../427-first-round-picks-stud-tax-exempt/qa-round-1-agent-A.md) · [qa B](../427-first-round-picks-stud-tax-exempt/qa-round-1-agent-B.md) |
| 428 | G-428 | QA-green (2 rounds), shipped | [prd](../428-sleeper-pick-send-refused/prd.md) · [qa r2 A](../428-sleeper-pick-send-refused/qa-round-2-agent-A.md) · [qa r2 B](../428-sleeper-pick-send-refused/qa-round-2-agent-B.md) |

Shipped on operator go 2026-09-08: PR #292 squash-merged as `1371d2e5`, Render live 00:03:58Z, iOS 1.17.3 (EAS `c0fe6e0d`) auto-submitted, all seven items `fixed`. Decisions D-189–D-192; [recovery capture](../../recovery/2026-09-08-feedback-batch-422-428.md); consolidated operator checklist [testflight-checklist.md](testflight-checklist.md) **unrun**.
