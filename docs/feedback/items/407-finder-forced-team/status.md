# FB-407
- **Status:** built 2026-08-30 — awaiting orchestrator review + merge; TestFlight checklist pending
- **Group:** G-407 (fast-track bug). Batch plan: [406-target-any-leaguemate/plan.md](../406-target-any-leaguemate/plan.md)
- **Reported:** `mattmurf77`, screen `TradesHome`, v1.16.11, filed 2026-08-30T02:51Z
- **Report:** "The find a trade feature is incorrectly forcing a team from the calculator screen below it"
- **Context:** filed hours after v1.16.11 shipped (PR #237, "found ideas browse in the calculator; Trades is the front door") — suspected regression in the merged calc/finder surface ([384-calc-finder-merge](../384-calc-finder-merge/status.md) lineage).
- 2026-08-30: Phase 1 (planner) — root cause pinned, REPRODUCES on origin/main tip e89eebb0: the calculator auto-defaults its partner to the first leaguemate (`InLeagueCalculator.tsx:538-541`), Find a Trade passes that partner unconditionally (`:1214-1217`), `handleInlineFindATrade` adopts it as the finder scope (`TradesScreen.tsx:3055`) and the dispatch sends `opponent_user_id` (`:1850`/`:3353`) — a single-team sweep the user never asked for, pinned back into the dropdown by the canvas remount (`TradeBuildCanvas.tsx:152/168/172`); exposed (not introduced) by PR #237's merged-view trim + Trades landing. Fix planned (1 production file: gate the payload's `opponent` on chosen-or-receive-side); see [mini-prd.md](mini-prd.md) + [scope.md](scope.md).
- 2026-08-30: Phase 2 (mobile build agent) — **built and statically verified**, exactly the
  mini-PRD's "Fix approach"; working tree left uncommitted for orchestrator review.
  - **Production change** (`mobile/src/components/InLeagueCalculator.tsx`, +16/-1):
    `opponentChosenRef = useRef(!!initialOpponentId)` at `:351`; the two user-tap
    `setOpponentId` sites mark it chosen (`:1074` chip row, `:1485` team-picker sheet);
    the Find a Trade payload gates the partner on
    `opponentChosenRef.current || receiveIds.length > 0` (`:1229-1231`). The
    default-opponent effect (`:545-548`) is untouched and never sets the ref.
  - **Regression guard** (`mobile/tests/check-calc-merged-behavior.js`, +44): FB-407
    section, assertions 20a (ref exists, initialOpponentId counts as chosen), 20b/20b-bis
    (default effect exists and never marks chosen), 20c/20c-bis (exactly two user-tap
    sites, both paired with the ref write), 20d (payload gate anchored end-to-end incl.
    `: null,`).
  - **Verification (D-056 static):** `npx tsc --noEmit` clean (exit 0); full
    `npm run test:calc-merged-behavior` green ("all assertions passed"). Five sabotage
    cycles, each red→restore→green: (1) revert gate to unconditional pass-through → 20d ✗;
    (2) remove chip-row ref-set → 20c-bis ✗; (3) remove team-sheet ref-set → 20c-bis ✗;
    (4) add ref write inside the default effect → 20b-bis ✗; (5) break the ref initializer
    to `useRef(false)` → 20a ✗. Each run ended "check-calc-merged-behavior: 1 FAILED";
    final restored run fully green.
  - **Code-walk proof:** [code-walk.md](code-walk.md) — the mini-PRD's 7-step trace
    executed at the post-fix state (default never chosen → payload null → fork
    `has_partner:false` → `setSheetOpponent(null)` → `opponent_user_id` omitted →
    server all-teams path `server.py:6090-6096`/`:6258-6261`; explicit-pick and
    built-trade counter-cases; no dropdown pin-back via `TradeBuildCanvas.tsx:152/172`).
  - **Zero diff confirmed** in `TradesScreen.tsx`, `TradeBuildCanvas.tsx`,
    `canvasSearch.ts`, and everything else — `git status` shows only the two owned files
    modified plus this folder's docs.
  - **Left for ship phase:** operator's 5-step TestFlight checklist (mini-prd.md);
    TEST_LEDGER + CHANGELOG entries; the scope.md DECISIONS.md row ("a partner counts as
    the search scope only when chosen — the auto-default never scopes").
