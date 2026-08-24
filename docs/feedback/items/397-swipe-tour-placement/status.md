# FB-397 + FB-398 — swipe tour step placement (Group B canonical)
- **Status:** planned 2026-08-24 — PRD ready
- **Covered:** #397 (superseded), #398 (operative: top of screen, above the trade chip section)
- **Path:** fast-track bug, full gates
- **Docs:** [plan.md](plan.md) (planner investigation) · [prd.md](prd.md) (mini-PRD + D-056 test plan) · [scope.md](scope.md) (feature-scope gates)
- Batch plan: [346-quickset-tier-drop/plan.md](../346-quickset-tier-drop/plan.md)

The Fleeced swipe right/left onboarding step (beat s2.2) band-flips mid-screen /
bottom-band; #397 asked for bottom, #398 corrects to top of screen above the
trade chips. Filed on 1.16.3 build 129 — the current tour shipped via #384 W5–W8.

Fix (PRD): opt-in per-step pin — `GuideStep.band?: 'top'` + solver 5th param
`pin?: 'top'` returning `{from:'top', offset: insets.top + BAND_EDGE}`; s2_2
declares it; 4-arg solver path byte-identical. New guard cases **11n–11q**
(plan's proposed 11i/11j IDs were already taken by the invariant sweep).

Coordination: `TradesScreen.tsx` READ-ONLY (Group A owns it);
`check-guide-spotlight-tracking.js` also extended by Group D — serialize merges,
Group D must not claim case IDs 11n–11q.
