# FB-407
- **Status:** planned 2026-08-30
- **Group:** G-407 (fast-track bug). Batch plan: [406-target-any-leaguemate/plan.md](../406-target-any-leaguemate/plan.md)
- **Reported:** `mattmurf77`, screen `TradesHome`, v1.16.11, filed 2026-08-30T02:51Z
- **Report:** "The find a trade feature is incorrectly forcing a team from the calculator screen below it"
- **Context:** filed hours after v1.16.11 shipped (PR #237, "found ideas browse in the calculator; Trades is the front door") — suspected regression in the merged calc/finder surface ([384-calc-finder-merge](../384-calc-finder-merge/status.md) lineage).
- 2026-08-30: Phase 1 (planner) — root cause pinned, REPRODUCES on origin/main tip e89eebb0: the calculator auto-defaults its partner to the first leaguemate (`InLeagueCalculator.tsx:538-541`), Find a Trade passes that partner unconditionally (`:1214-1217`), `handleInlineFindATrade` adopts it as the finder scope (`TradesScreen.tsx:3055`) and the dispatch sends `opponent_user_id` (`:1850`/`:3353`) — a single-team sweep the user never asked for, pinned back into the dropdown by the canvas remount (`TradeBuildCanvas.tsx:152/168/172`); exposed (not introduced) by PR #237's merged-view trim + Trades landing. Fix planned (1 production file: gate the payload's `opponent` on chosen-or-receive-side); see [mini-prd.md](mini-prd.md) + [scope.md](scope.md).
