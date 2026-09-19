# Status — 426-overhaul-button-prominent

```project-status
{
  "status": "shipped",
  "updated": "2026-09-08",
  "summary": "FB-426 — Prominent Team overhaul entry; canonical implementation is #425",
  "evidence": "The latest phase-log entry explicitly records shipment, superseding the earlier planned header. PR #292 / 1371d2e5 merged; ../../../recovery/2026-09-08-feedback-batch-422-428.md verifies Render LIVE at September 9 00:03:58 UTC (September 8 local), production smoke and preserved release tree. iOS 1.17.3 (155) uploaded through submission 2742bdd6; feedback DB set fixed. The physical-device checklist remains unrun; uploaded is not a claim of tester installation. G-425 satellite; canonical ../425-overhaul-tile-replaces-draft/status.md. Hero remains ice pending a red-token decision."
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
- 2026-09-08: Phase 1 — planned (G-425, with #425): the utility-row Draft cell is the reported button; a full-width ice hero (`HERO_TONE`, one constant) takes its slot above the utility row; red needs a design-system addition → operator Q1 in [425 prd.md](../425-overhaul-tile-replaces-draft/prd.md).
- 2026-09-08: Phase 2 build `9610e5ec`/`d80e9ee9`; Phase 3 QA-A PASS, QA-B PASS (0 findings); ship-ready (branch feat/fb425-overhaul-hero-replaces-draft).
- 2026-09-08: Phase 5 — merged into `feat/feedback-2026-09-08` (mobile 1.17.3); awaiting operator go.
- 2026-09-08: **Shipped** — PR #292 → `1371d2e5`; Render live; iOS **1.17.3 (155)** uploaded (submission `2742bdd6`); item set `fixed`. Device checklist unrun.
