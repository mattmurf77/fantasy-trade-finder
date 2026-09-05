# Release log — Fleeced

Release authorization and verified delivery are recorded separately. Engineering evidence remains in the linked feature records; no release is marked live from intent alone.

| Date | Release | Status | Record |
|---|---|---|---|
| 2026-09-05 | Season projections + Win Now + championship experimental beta; iOS 1.17.0 (147) | Backend/web LIVE `c28ec6d8`; all three flags true; final CI green. iOS built/uploaded, Apple processing; tester availability and physical QA unverified. Calibration unproven. | [Release evidence and rollback](2026-09-05-win-now.md) |

## Decisions needed

None for the already authorized release. Authorization accepts exploratory, uncalibrated evidence; it does not certify deployment or predictive accuracy.

## Handoffs

Confirm Apple processing/tester availability and complete the linked physical TestFlight checklist. Rollback remains all three flags false; prior main `a927e3a7` is the code rollback target.
