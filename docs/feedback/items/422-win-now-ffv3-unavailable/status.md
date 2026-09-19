# Status — 422-win-now-ffv3-unavailable

```project-status
{
  "status": "shipped",
  "updated": "2026-09-08",
  "summary": "FB-422 — Win Now explains unsupported FFV3 roster slots",
  "evidence": "The latest phase-log entry explicitly records shipment, superseding the earlier planned header. PR #292 / 1371d2e5 merged; ../../../recovery/2026-09-08-feedback-batch-422-428.md verifies Render LIVE at September 9 00:03:58 UTC (September 8 local), production smoke and preserved release tree. iOS 1.17.3 (155) uploaded through submission 2742bdd6; feedback DB set fixed. The physical-device checklist remains unrun; uploaded is not a claim of tester installation. G-422; plan.md, reconciliation-log.md and build-report.md retain the chosen refusal behavior, not a claim that kicker/IDP projections are now supported."
}
```

## Historical phase and release notes

The current disposition is the status record above. Earlier planned/build wording below is retained as dated history.

# FB-422 — Win Now unavailable on FFV3

- **Status:** planned 2026-09-08 (operator selection; fast-track bug path)
- **Group:** G-422 — batch plan [422-win-now-ffv3-unavailable/plan.md](../422-win-now-ffv3-unavailable/plan.md)
- **Reporter:** mattmurf77, app v1.17.x, iOS 27.0

## Phase log
- 2026-09-08: Phase 0 — selected; folder created; investigation planner launched.
- 2026-09-08: Phase 1 complete — reason `unsupported_roster_slots` reproduced locally against live FFV3 data (98-byte body identical to prod); fix (b) adopted (reconciliation-log.md). Build launched.
- 2026-09-08: Phase 2 build `e280ca73` + docs; Phase 3 round 1 QA-A PASS, QA-B PASS (full suite 5872/1); no Phase 4. Ready for ship.
- 2026-09-08: Phase 5 — merged into `feat/feedback-2026-09-08` (mobile 1.17.3); awaiting operator go.
- 2026-09-08: **Shipped** — PR #292 → `1371d2e5`; Render live; iOS **1.17.3 (155)** uploaded (submission `2742bdd6`); item set `fixed`. Device checklist unrun.
