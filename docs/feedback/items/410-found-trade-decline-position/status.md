# FB-410 — decline position on found trades

**Status:** planned · 2026-08-30 · `claude/fb-410-412-trade-card-polish`

- **Group:** G-410 — merged-canvas trade-card polish. **This folder is the group
  canonical** (lowest id); it holds the full doc set.
- **Covers feedback IDs:** #410, #411, #412 — all filed by mattmurf77 on
  2026-08-30 against v1.16.12 (EAS build 140), screen `TradesHome`.
  Satellites: [`411-player-name-truncation/`](../411-player-name-truncation/status.md),
  [`412-more-offers-placement/`](../412-more-offers-placement/status.md).
- **Plan:** [plan.md](plan.md). Scope block and PRD authored separately.

## The report

> *"X button should replace the 'clear' button next to check box when a found
> trade is suggested."*

## Current behavior (one line)

While a `calc.canvas_results` browse session is live, the decline ✕ sits in the
pager row above the canvas (`mobile/src/screens/TradesScreen.tsx:7390`) while the
action row's middle cell still shows **Clear**
(`mobile/src/components/InLeagueCalculator.tsx:1302-1319`) — which empties the
canvas without ending the session and snapshots the emptied sides into the
browsed idea's edit map, so paging back restores the wiped idea rather than the
engine's original.

## Log

- **2026-08-30 — specced; operator confirmation obtained; ready to build.** The
  block below is **cleared**: the operator was shown both prior rulings and ruled
  *"It does mean pass / Keep the x button."* for #410, and **tag move + shrink the
  name** (no wrapping) for #411. [prd.md](prd.md) is written to those rulings —
  **17 requirements**, incl. R-6 for the browse-session data-loss defect and R-17
  for the #409 refusal copy — with [scope.md](scope.md) (no waivers) and
  [reconciliation-log.md](reconciliation-log.md) (rulings verbatim, the Planner's
  four open questions resolved, 13 deviations, 7 plan claims corrected).
  **D-169** amending D-157 + `canvas-results-spec.md` §4 is drafted verbatim in
  prd.md §13. Name size measured, not estimated: **13pt**, taking the top-100
  dynasty assets from 1/100 to 83/100 on one line — but **3 of the operator's 5
  pressure-test names still ellipsize** (prd.md §6.1). Owed next: `code-walk.md`,
  `testflight-checklist.md`, and the build.

## Blocking: operator confirmation required before build — CLEARED 2026-08-30

**Resolved.** Both rulings below were surfaced to the operator, who overturned the
placement clause knowingly. Kept here as the record of what was overturned.

The fix contradicts two prior rulings — see [plan.md §5](plan.md#5-prior-ruling-conflicts-the-operator-must-see):

1. `docs/feedback/items/402-more-offers-shop/canvas-results-spec.md` §4 (operator
   session, 2026-08-28) places the ✕ *"with the pager, never inside the action
   row's 50/30/20 cells"*.
2. [D-157](../../../../living-memory/DECISIONS.md) (2026-08-23) replaced a bare ✕
   in that exact cell with the labeled **Clear** after a tester misread it and
   wiped his canvas.

Neither is a hard blocker on the operator's own authority — but both must be
surfaced and confirmed rather than silently reversed. A new `D-###` amending both
is owed if the change ships.
