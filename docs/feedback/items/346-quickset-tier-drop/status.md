# FB-346 + FB-381 — QuickSet tier drop (Group F canonical)
- **Status:** planned 2026-08-24 — PRD ready
- **Covered:** #346 (jonbonjourvi, 1.13.4), #381 (mattmurf77, 1.15.0 — detailed repro)
- **Path:** fast-track bug, full gates
- Batch plan: [plan.md](plan.md) (this folder is also the batch home — lowest selected id)
- Group F plan: [plan-group-f.md](plan-group-f.md) · PRD: [prd.md](prd.md) · Scope: [scope.md](scope.md)
- Verdict: the #161 demote rule (commit `a8898a7`, v1.10.0) is the cause; the
  operator's #381 ruling supersedes it → contract is **HOLD** (saves touch
  only selected players). Fix is backend + mobile; decision records as D-160.

Repro (#381): player set tier "4+ 1sts"; operator saves that tier having
selected 3 other WRs; on moving to the "3+ 1sts" screen the unselected player
has been silently reset to FA instead of staying at 4+ (preferred) or stepping
to 3+. #346 is the same defect class reported earlier: preselected values drop
to zero rather than the next tier. "This is new behavior that is broken."
