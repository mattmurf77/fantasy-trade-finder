# Status — 428-sleeper-pick-send-refused

```project-status
{
  "status": "shipped",
  "updated": "2026-09-08",
  "summary": "FB-428 — Sleeper refuses spent/out-of-window pick classes before provider sends",
  "evidence": "The latest phase-log entry explicitly records shipment, superseding the earlier planned header. PR #292 / 1371d2e5 merged; ../../../recovery/2026-09-08-feedback-batch-422-428.md verifies Render LIVE at September 9 00:03:58 UTC (September 8 local), production smoke and preserved release tree. iOS 1.17.3 (155) uploaded through submission 2742bdd6; feedback DB set fixed. The physical-device checklist remains unrun; uploaded is not a claim of tester installation. G-428; D-189 and round-2 reviews preserve shape-blind completed-draft exclusion and bounded tradability validation. This follows the distinct PR #270 encoding fix in #413; no startup-league live capture is claimed."
}
```

## Historical phase and release notes

The current disposition is the status record above. Earlier planned/build wording below is retained as dated history.

# FB-428 — Sleeper refuses draft-pick sends

- **Status:** planned 2026-09-08 (operator selection; fast-track bug path)
- **Group:** G-428 — batch plan [422-win-now-ffv3-unavailable/plan.md](../422-win-now-ffv3-unavailable/plan.md)
- **Reporter:** mattmurf77, app v1.17.x, iOS 27.0

## Phase log
- 2026-09-08: Phase 0 — selected; folder created; investigation planner launched.
- 2026-09-08: Phase 1 complete — spent current-season pick mechanism strongly indicated from public Sleeper data; new 422 approved (reconciliation-log.md). Build launched.
- 2026-09-08: Phase 2 build `26ab3147`; Phase 3 round 1 QA-A FAIL (adjudicated: startup-draft exclusion), QA-B PASS; Phase 4 resolution launched.
- 2026-09-08: Phase 4 — round-1 rulings applied (shape-blind exclusion, guard check 9 on the Alert argument, dead `season_window: null` / `?–?` branches removed, D-189 text amended); targeted suites green, guard RED→GREEN proven; full suite + QA round 2 pending.
- 2026-09-08: Phase 3 round 2 — QA-A PASS, QA-B PASS; ship-ready (branch feat/fb428-sleeper-pick-tradability).
- 2026-09-08: Phase 5 — merged into `feat/feedback-2026-09-08` (mobile 1.17.3); awaiting operator go.
- 2026-09-08: **Shipped** — PR #292 → `1371d2e5`; Render live; iOS **1.17.3 (155)** uploaded (submission `2742bdd6`); item set `fixed`. Device checklist unrun.
