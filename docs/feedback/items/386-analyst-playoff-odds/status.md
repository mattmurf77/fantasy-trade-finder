# FB-386 + FB-391 — analyst pop-up / playoff odds broken (Group D canonical)
- **Status:** planned 2026-08-24 — PRD ready
- **Covered:** #386 (bug), #391 (context: analyst box positions correctly when playoff projection is minimized)
- **Path:** fast-track bug, full gates
- Batch plan: [346-quickset-tier-drop/plan.md](../346-quickset-tier-drop/plan.md)
- Plan (root cause + fix choice): [plan.md](plan.md)
- PRD (fix contract R-1…R-6 + D-056 test plan): [prd.md](prd.md)
- Scope block: [scope.md](scope.md)

On LeagueRankings (1.16.2) the analyst pop-up renders broken when the playoff
odds section is expanded; correct when minimized (#391). Note `outlook.odds`
was lit 2026-08-19 (D-094) — this surface is young.
