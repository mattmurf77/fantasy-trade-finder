# Release log — Fleeced

Release authorization and verified delivery are recorded separately. Engineering evidence remains in the linked feature records; no release is marked live from intent alone.

| Date | Release | Status | Record |
|---|---|---|---|
| 2026-09-05 | Season projections + Win Now + championship experimental beta; mobile 1.17.0 planned | Explicitly authorized; final CI, Render/effective flags and EAS/TestFlight delivery verification pending. Calibration and physical QA unperformed. | [Release scope, evidence, checklist and rollback](2026-09-05-win-now.md) |

## Decisions needed

None for the already authorized release. Authorization accepts exploratory, uncalibrated evidence; it does not certify deployment or predictive accuracy.

## Handoffs

The parent release executor updates the dated record and this row with observed CI/deploy/build/processing outcomes. The operator completes the linked physical TestFlight checklist. Rollback is all three Win Now flags false; prior Render commit `0a8093fe` is recorded in the dated release document.
