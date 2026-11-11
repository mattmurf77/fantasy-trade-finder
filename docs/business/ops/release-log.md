# Release log — Fleeced

Release authorization and verified delivery are recorded separately. Engineering evidence remains in the linked feature records; no release is marked live from intent alone.

| Date | Release | Status | Record |
|---|---|---|---|
| 2026-11-11 | Projection model v5 and outlook suggestion; iOS 1.22.0 (185) | Backend/web LIVE `253136ac` (#647), CI green on the merged head, `league.projection_outlook` on. iOS built/uploaded; Apple processing and tester availability unverified. Same day: #648 (a player's NFL team change stopped every forecast), #649 (fast deck off again, D-232; held-rank wording; Home link), #650 (operator re-run option); main `74cbbce8`. All six supported forecasts completed on v5 at 19:34, four of them incomplete. Nothing verified on a device; the score SD is provisional. | [2026-11-11-projection-model-v5.md](2026-11-11-projection-model-v5.md) |
| 2026-11-10 | Offer learnings and fast deck; iOS 1.22.0 (184) | Backend/web LIVE `13865d73` with seven flags on (#641 dark, then #643); CI green on both heads. Approved Terms and Privacy wording published. iOS built/uploaded, Apple processing; tester availability unverified. Revision 4 Calibration round: 11 decks ready, 5 provider failures. Nothing verified on a device; fast deck turned on without a shadow day. | [Release evidence and rollback](2026-11-10-offer-learnings.md) |
| 2026-09-16 | Web landing page | Initial release LIVE `3789bb36`; all four CI jobs green; public assets verified. Narrow embedded-browser scroll correction in follow-up validation. | [Release evidence and rollback](2026-09-16-landing-page.md) |
| 2026-09-05 | Season projections + Win Now + championship experimental beta; iOS 1.17.0 (147) | Backend/web LIVE `c28ec6d8`; all three flags true; final CI green. iOS built/uploaded, Apple processing; tester availability and physical QA unverified. Calibration unproven. | [Release evidence and rollback](2026-09-05-win-now.md) |

## Decisions needed

None for the already authorized release. Authorization accepts exploratory, uncalibrated evidence; it does not certify deployment or predictive accuracy.

## Handoffs

Confirm Apple processing/tester availability and complete the linked physical TestFlight checklist. Rollback remains all three flags false; prior main `a927e3a7` is the code rollback target.
