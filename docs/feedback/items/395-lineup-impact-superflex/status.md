# FB-395 + FB-396 — starting-lineup impact: superflex + flex labels (Group C canonical)
- **Status:** planned 2026-08-24 — PRD ready
- **Covered:** #395 (SF slot attribution), #396 (flex slot labeled "WR3")
- **Path:** fast-track bug, full gates
- Docs: [plan.md](plan.md) · [prd.md](prd.md) · [scope.md](scope.md)
- Batch plan: [346-quickset-tier-drop/plan.md](../346-quickset-tier-drop/plan.md)

#395: trading away Jayden Daniels in a superflex league, the lineup-change
readout claims Maye was the QB starter and Fannin the SF starter, rather than
Daniels occupying SF. Verdict: math right, presentation wrong — the two
canonical greedy fills are diffed row-by-row with no churn minimization. Fix A:
pure `align_starter_slots` display alignment inside `_starter_impact` only.

#396: change readout says "WR3" in a league with 2 WR slots + flex. Verdict:
ESPN/MFL/Fleaflicker leagues substitute the 3-WR `_MOCK_DEFAULT_LINEUP` for the
real template (`server.py:24171-24175`). Fix B: honest
`_PLATFORM_DEFAULT_LINEUP` (QB/2RB/2WR/TE/2FLEX, +SF for sf_tep), unconditional.
Plus a one-line rank-chip disambiguation (`WR3 → WR12` becomes `WR #3 → WR #12`,
`CardImpactBlock.tsx:155`) — the chip is the only source that can read "WR3" in
a Sleeper 2-WR league. TestFlight checklist covers both league types so the
operator's pass settles which one the report came from.
