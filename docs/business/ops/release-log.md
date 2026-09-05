# Release log — Fleeced

Release authorization and verified delivery are recorded separately. Engineering evidence remains in the linked feature records; no release is marked live from intent alone.

| Date | Release | Status | Record |
|---|---|---|---|
| 2026-09-05 | Season projections + Win Now + championship experimental beta; mobile 1.17.0 planned | Authorized; security main `a927e3a7` integration and fresh CI/Render/EAS verification pending. CI `ee4f37a8` and build 146 superseded; cancellation confirmed, replacement build pending. Calibration/physical QA unperformed. | [Release scope, evidence, checklist and rollback](2026-09-05-win-now.md) |

## Decisions needed

None for the already authorized release. Authorization accepts exploratory, uncalibrated evidence; it does not certify deployment or predictive accuracy.

## Handoffs

The parent release executor updates the dated record and this row with observed CI/deploy/build/processing outcomes. The operator completes the linked physical TestFlight checklist. Rollback is all three Win Now flags false; prior main commit `a927e3a7` is recorded in the dated release document.
