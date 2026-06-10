# Status: feedback-batch-2

## OUTCOME (2026-06-08) — all 7 features merged to main

| Feature | ids | PR | State |
|---------|-----|----|-------|
| FB-01 Matches disposition + logging | #35/#36 | #77 | ✅ merged |
| FB-02 Tiers drag engine + multi-select | #27/#29/#32 | #78 | ✅ merged |
| FB-03 Ranks consolidation + nav | #40/#28 | #79 | ✅ merged |
| FB-04 Trends rank deltas | #31 | #80 | ✅ merged |
| FB-05 Trades ✓/✗ buttons | #34 | #81 | ✅ merged |
| FB-06 League team count | #41 | #82 | ✅ merged |
| FB-07 Trios cleanup | #26/#33 | #83 | ✅ merged |

Integrated regression on main: **backend pytest 55 passed**, **mobile tsc clean**.
Phase: **done** (code). Remaining: EAS build #11 to get the mobile features onto
TestFlight (user decides cadence). FB-02 needs a device smoke test (drag/cross-tier/
grouped move). FB-01 ships with logging so any residual Matches accept failure
surfaces the real cause.

Follow-ups flagged (not blocking): FB-01 cross-league/cross-format `save_trade_swipes`
key; RookieDraftBoardSheet component now unused (left in place).

---

- **Phase:** done — all 7 merged
- **Current round:** 01 (open)
- **Last update:** 2026-06-08 by primary
- **Next action:** 6 subagents (FB-01..FB-06) implementing in worktree isolation;
  primary doing FB-07 directly; then review → PR-per-feature → merge → regression.
- **Blockers:** none
- **Surfaces touched:** mobile, backend
- **Linked ADRs:** none
- **HLD/LLD:** no system-level change; screen registry `mobile/src/screens/CLAUDE.md`
  updated by FB-03 (remove OverallRanks, rename ManualRanks→"Overall Ranks").

## Resume in a fresh chat
1. CLAUDE.md + docs/coding-guidelines.md
2. this status.md → conversation.md → plan.md
3. prd/*.md (the 7 feature specs)
4. Feedback source: `GET /api/feedback/admin` (backend app_feedback table)

## Features → agents
| Feature | ids | Agent | State |
|---------|-----|-------|-------|
| FB-01 Matches disposition + logging | #35/#36 | A | ⬜ |
| FB-02 Tiers drag engine + multi-select | #27/#29/#32 | B | ⬜ |
| FB-03 Ranks consolidation + nav | #40/#28 | C | ⬜ |
| FB-04 Trends rank deltas | #31 | D | ⬜ |
| FB-05 Trades ✓/✗ buttons | #34 | E | ⬜ |
| FB-06 League team count | #41 | F | ⬜ |
| FB-07 Trios cleanup (rookies link + injury tags) | #26/#33 | primary | ⬜ |

## Locked decisions (2026-06-08)
- FB-02 multi-select: collapse-into-block move; Select-button only (no long-press);
  lighter-blue full-tile fill.
- FB-02 drag: adopt ManualRanks engine; preserve PR #60 coord fix + cross-tier moves.
- FB-03: remove OverallRanks; rename ManualRanks → "Overall Ranks".
- FB-01: investigate + add structured logging; harden cross-league path.

## Accepted / merged
- _none yet_
