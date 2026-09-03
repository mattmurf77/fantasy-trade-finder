# FB-413 — Send in Sleeper fails on trades with draft picks

**Status:** in_progress · Phase 3 complete 2026-09-02 — dual-QA PASS, awaiting the operator ship go (branch `feat/fb413-sleeper-send-draft-picks` @ `d49611be`, local, unpushed) — ready for build
- **Reporter:** mattmurf77, 2026-08-30T15:38Z, app v1.16.12 (build 140), screen `TradesHome`
- **Report:** *"Send in sleeper isn't correctly identifying draft picks and causing trades with draft picks to fail"*
- **Group:** G-413 (canonical) — batch plan [plan.md](plan.md); trace [investigation.md](investigation.md)
- **Phase 1 docs:** [plan-g413.md](plan-g413.md) · [hld-delta.md](hld-delta.md) · [lld-delta.md](lld-delta.md) · [prd.md](prd.md) · [scope.md](scope.md) · critique [review-round-1.md](review-round-1.md) · [reconciliation-log.md](reconciliation-log.md)

## Phase log

- 2026-09-02: Phase 0 complete — trace captured, planner launched.
- 2026-09-02: Phase 1 round 1 — plan, four Author docs, Planner critique (14 objections, 5 rulings; verdict "ready for build after fixes").
- 2026-09-02: **Phase 1 round 2 complete — 14 incorporated, 0 rebutted, 0 for arbitration.** Expected test delta +20 (4483 → 4503). Blocking items closed: `detail` on both 422s (+ the 400), one build-honesty statement in PRD §1/§10 + scope §5, TF-3 conditional / TF-5–6 opportunistic, count-aware mobile copy with curly quotes on the server string, positive spine assertion T-3b, ruling-1 paragraph in PRD §4 + LLD §4.2.

## Phase log
- 2026-09-02 Phase 1: planner + author, 1 critique round (14/14 incorporated), no arbitration.
- 2026-09-02 Phase 2: backend `b4aabcc3`→`b938642b` (+ orchestrator `51794a35` ADR-010 guard sanction), mobile `8e4e1648`. 25 + 6 builder sabotage cycles.
- 2026-09-02 Phase 3: QA-A and QA-B both PASS at `8e4e1648` (reports in this folder). Post-QA copy-only fix `d49611be` (validate advisory grammar/apostrophe); full suite 4503/1 re-run green. Evidence: TEST_LEDGER 2026-09-02.
- Owed: operator go → push + PR + merge (Render deploy fixes fielded builds), EAS build for the mobile copy, 7-step TestFlight checklist (PRD §10), TF-3 closes Q-037.
