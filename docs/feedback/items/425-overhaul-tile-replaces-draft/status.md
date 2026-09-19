# Status — 425-overhaul-tile-replaces-draft

```project-status
{
  "status": "shipped",
  "updated": "2026-09-08",
  "summary": "FB-425 — Team overhaul hero replaces Draft entry; canonical for #425/#426",
  "evidence": "The latest phase-log entry explicitly records shipment, superseding the earlier planned header. PR #292 / 1371d2e5 merged; ../../../recovery/2026-09-08-feedback-batch-422-428.md verifies Render LIVE at September 9 00:03:58 UTC (September 8 local), production smoke and preserved release tree. iOS 1.17.3 (155) uploaded through submission 2742bdd6; feedback DB set fixed. The physical-device checklist remains unrun; uploaded is not a claim of tester installation. G-425 canonical for #426. The hero remains ice; a red design-system token is a separate unresolved decision. See prd.md, reconciliation-log.md and build-report.md."
}
```

## Historical phase and release notes

The current disposition is the status record above. Earlier planned/build wording below is retained as dated history.

# FB- —

- **Status:** planned 2026-09-08 (operator selection; polish path)
- **Group:**  — batch plan [422-win-now-ffv3-unavailable/plan.md](../422-win-now-ffv3-unavailable/plan.md)
- **Reporter:** mattmurf77, app v1.17.2, iOS 27.0

## Phase log
- 2026-09-08: Phase 0 — selected; folder created; planner launched.
- 2026-09-08: Phase 1 complete — PRD, scope, investigation; rulings in reconciliation-log.md. Build launched.
- 2026-09-08: Phase 1 — planned: [prd.md](prd.md), [scope.md](scope.md), [investigation.md](investigation.md). Draft cell removed from `TradeHomeUtilityRow`; overhaul hero mounts above the utility row; `check-team-overhaul.js` §3 rewritten; 4 operator questions (red / control-cohort chip / pushed page / flag-off Draft).
- 2026-09-08: Phase 2 build `9610e5ec`/`d80e9ee9`; Phase 3 QA-A PASS, QA-B PASS (0 findings); ship-ready (branch feat/fb425-overhaul-hero-replaces-draft).
- 2026-09-08: Phase 5 — merged into `feat/feedback-2026-09-08` (mobile 1.17.3); awaiting operator go.
- 2026-09-08: **Shipped** — PR #292 → `1371d2e5`; Render live; iOS **1.17.3 (155)** uploaded (submission `2742bdd6`); item set `fixed`. Device checklist unrun.
