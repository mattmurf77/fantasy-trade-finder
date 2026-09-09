
## Orchestrator rulings 2026-09-08 (Phase 1 exit)

- Fix (b) adopted: honest, specific, early refusal; reason string unchanged; no client change. Copy as drafted in prd.md. Analytics waiver accepted (a refusal already reaches the client as `baseline.message`; no new event).
- Lakeview `unknown_starter_availability` refusal and the post-2026-09-09 `live_week_unsupported` window are surfaced to the operator in the ship summary as a separate candidate item, not built here.
- Note: investigation.md was swept into `a8658cec` by the orchestrator; harmless.

## Phase 3 round 1 — 2026-09-08

QA-A PASS (3 minor), QA-B PASS (2 observations). No confirmed defect; no Phase 4. Rulings: F-1/O-2 DEF-slot wording is inside the signed-off copy — noted for a later copy pass; F-2 doc-prose counts (13 idp / 8 kicker) corrected in the PRD by this commit; A F-3 full-suite flake (`test_rookie_scope` 401 under load) — that file re-run green here and QA-B's full run on the same commit was 5872 passed / 1 skipped. O-1 search-job path stores only the reason (pre-existing, unreachable for FFV3) — candidate follow-up.
