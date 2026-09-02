# FB-413 — Send in Sleeper fails on trades with draft picks

**Status:** planned 2026-09-02 · Phase 1 (planning) — ready for build
- **Reporter:** mattmurf77, 2026-08-30T15:38Z, app v1.16.12 (build 140), screen `TradesHome`
- **Report:** *"Send in sleeper isn't correctly identifying draft picks and causing trades with draft picks to fail"*
- **Group:** G-413 (canonical) — batch plan [plan.md](plan.md); trace [investigation.md](investigation.md)
- **Phase 1 docs:** [plan-g413.md](plan-g413.md) · [hld-delta.md](hld-delta.md) · [lld-delta.md](lld-delta.md) · [prd.md](prd.md) · [scope.md](scope.md) · critique [review-round-1.md](review-round-1.md) · [reconciliation-log.md](reconciliation-log.md)

## Phase log

- 2026-09-02: Phase 0 complete — trace captured, planner launched.
- 2026-09-02: Phase 1 round 1 — plan, four Author docs, Planner critique (14 objections, 5 rulings; verdict "ready for build after fixes").
- 2026-09-02: **Phase 1 round 2 complete — 14 incorporated, 0 rebutted, 0 for arbitration.** Expected test delta +20 (4483 → 4503). Blocking items closed: `detail` on both 422s (+ the 400), one build-honesty statement in PRD §1/§10 + scope §5, TF-3 conditional / TF-5–6 opportunistic, count-aware mobile copy with curly quotes on the server string, positive spine assertion T-3b, ruling-1 paragraph in PRD §4 + LLD §4.2.
