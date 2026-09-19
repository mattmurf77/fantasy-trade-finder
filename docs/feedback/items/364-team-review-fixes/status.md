# Status — Team Review defect batch (#364 / #367 / #368)

**Status:** `shipped-pending-verification` — PR #152 merged `bc43b6f`, Render live, EAS build 124 submitted to TestFlight. **The 13-step checklist is still UNRUN.**
**Date:** 2026-08-20
**Covered feedback IDs:** #364, #367, #368 built · #365, #366, #369, #370, #371 **planned only** (canonical folder = lowest built id, 364)
**Flags:** none added. Lands inside the already-lit `trades.team_review`; `outlook.odds` gates the #364 surface.

---

## What shipped

| # | Report | Fix |
|---|---|---|
| **#364** | Playoff disclaimer should name IDP | Caption names the cause and lists the unpriced slots, reading `priced_slot_coverage.unpriced_slots` — on the wire since 2026-08-10, never read by any client |
| **#367** | Sells/buys backwards | Selection corrected **upstream** in `compute_consensus_gap` (repairs Trends too), and the crossed field mapping un-crossed on both source ladders. [D-100](../../../../living-memory/DECISIONS.md) |
| **#368** | Partners beat nonsense, firsts blank | Route now passes the `pick_share` / `first_rounds` it already computed. One root cause, both symptoms |
| *operator* | Show every outlook input | `window.model` ships all seven knobs; beat renders the full arithmetic. Caught a hardcoded "age 23" against `youth_age` 26. [D-101](../../../../living-memory/DECISIONS.md) |
| *operator* | Minimize after completion | `ftf_team_review_completed`, kept separate from "Not now"; row reads "Team review · done" |

## Evidence

pytest **3606 passed, 1 skipped** · tsc clean · 64 `check-*.js` suites, 0 failed · testid-lint OK.
6 new backend tests, **5 sabotage-proven red** ([code-walk.md](code-walk.md) §5).
Two pre-existing tests repaired: one **asserted the defect**, one had gone **vacuous** under the fix
while still passing green.

**TestFlight checklist ([13 steps](testflight-checklist.md)) is UNRUN** — the only runtime evidence
available under D-056, and the corrected divergence beat has never been seen on a device.

## Not built — by operator selection

#365, #366, #369, #371, #370 and #367's consensus-vs-league toggle are specced in
[plan-remaining.md](plan-remaining.md), each with the decision it needs. See [scope.md](scope.md) §6
for why each was held back.

## The one thing to carry forward

**No feature flag reverts #367.** `compute_consensus_gap` is ungated and shared by mobile Trends,
web Trends and Team Review — rollback is a code revert, not a `features.json` flip.
