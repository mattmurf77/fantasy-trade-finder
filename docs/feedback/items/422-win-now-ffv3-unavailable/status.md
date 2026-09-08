# FB-422 — Win Now unavailable on FFV3

- **Status:** planned 2026-09-08 (operator selection; fast-track bug path)
- **Group:** G-422 — batch plan [422-win-now-ffv3-unavailable/plan.md](../422-win-now-ffv3-unavailable/plan.md)
- **Reporter:** mattmurf77, app v1.17.x, iOS 27.0

## Phase log
- 2026-09-08: Phase 0 — selected; folder created; investigation planner launched.
- 2026-09-08: Phase 1 complete — reason `unsupported_roster_slots` reproduced locally against live FFV3 data (98-byte body identical to prod); fix (b) adopted (reconciliation-log.md). Build launched.
- 2026-09-08: Phase 2 build `e280ca73` + docs; Phase 3 round 1 QA-A PASS, QA-B PASS (full suite 5872/1); no Phase 4. Ready for ship.
