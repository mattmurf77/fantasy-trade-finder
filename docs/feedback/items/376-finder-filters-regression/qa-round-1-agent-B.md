# QA round 1 — agent B — 2026-08-24

## Summary: PASS (1 finding)

Group A — #376/#379/#394 minimized "Outlook & filters" row. All PRD test-plan
rows reproduced from scratch: 12/12 sabotages RED with the named assertion,
all reverts green, code-walk cites verified line-by-line against the merged
tree. One minor checklist-feasibility finding; no code, guard, or contract
defect found.

## Environment

- Commit: `c8b0e224` ("merge Group F mobile…"), worktree originally cut at
  `cce3895f` and checked out to `c8b0e224` per the brief. Tree clean after QA
  (all sabotages reverted via `git checkout`).
- node v24.14.1 · Python 3.14.4 · fresh `npm ci` (no symlinked node_modules)
- Guard: `node tests/check-finder-conditions-reachable.js` (6 assertions)

## Results

| Test | Result |
|---|---|
| Batch: `npm ci` | PASS (clean) |
| Batch: `npx tsc --noEmit` | PASS |
| Batch: `bash scripts/testid-lint.sh` | PASS |
| Batch: full guard sweep (78 × `tests/check-*.js`) | PASS 78/78 |
| Batch: full `pytest backend/tests` (fresh data dir) | PASS — 4238 passed, 1 skipped, 5m39s |
| Batch: `git diff ff153a0..c8b0e224 --stat -- web/ extension/` | EMPTY — no web/extension changes, as claimed |
| Guard baseline 6/6 | PASS |
| S1a delete whole row → red | PASS — RED, assertions 1 (+2,3 collateral) |
| S1b delete container id, keep `.change` → red | PASS — RED, assertion 1 (boundary anchor works; 2,3 collateral) |
| S2a prepend `homeInlineVariant !== 'control' &&` → red | PASS — RED, assertion 2 only |
| S2b append `&& showInlineHome` → red | PASS — RED, assertion 2 |
| S2c append `&& presentationV2On` → red | PASS — RED, assertion 2 |
| S2d drop `!firstRun` → red | PASS — RED, assertion 2 |
| S2e gate via intermediate variable → red | PASS — RED, assertion 2 |
| S3 row wrapped in `{!consolidateOn ? (` branch → red | PASS — RED, assertion 3 only (anchor+balanced-paren located) |
| S4 swap `setDnaSheetOpen(true)` → `setOutlookOpen(true)` in the row span → red | PASS — RED, assertion 4 only (span-scoped; 5 other `setDnaSheetOpen` sites did not self-satisfy) |
| S5a re-add `onConditions` prop pass → red | PASS — RED, assertion 5 |
| S5b re-add `trades.home-utility.conditions` → red | PASS — RED, assertion 5 |
| S6 drop `hideTeamAndPlayer={sheetTargetingOn && consolidateOn}` → red | PASS — RED, assertion 6 |
| Missing-source-file harness case | PASS — exit 2, "missing source file" message |
| R-1 code-walk: gate `consolidateOn && !outlookReceiptShown && !firstRun` at `TradesScreen.tsx:5155`; row inside `outlookReceiptWrapRef` wrapper (`:5130`), sibling below `<OutlookBiasReceipt/>` | VERIFIED |
| R-1 value map: `OUTLOOK_FALLBACK_LABEL` (`:7446-7452`) = LEAN names verbatim (All-in/Contending/Rebuilding/Tanking, `OutlookBiasReceipt.tsx:34-39`) + `not_sure`→"Not sure"; "Not set" at call site (`:5159-5163`); `TradeDnaSheet.tsx:496` persists `outlook: draftOutlook ?? 'not_sure'` as cited | VERIFIED |
| R-2 removal proof: `git grep "onConditions\|home-utility.conditions" mobile/src/` | VERIFIED — zero hits |
| R-3 no-double-render: `outlookReceiptShown` (`:1047-1053`) is the receipt's own `outlookReceiptCovers` predicate; row gate is its exact complement under `consolidateOn && !firstRun` | VERIFIED |
| R-4/R-5: gate reads no variant/flag; `firstRun` latch at `:433-440` | VERIFIED |
| R-6: `check-trades-banner-region.js`, `check-calc-merged-behavior.js`, `check-guide-spotlight-tracking.js` green untouched; guide registration `trades.outlook-receipt.change`→`outlookReceiptWrapRef` (`:3229/:3246`) intact | VERIFIED (in the 78-guard sweep) |
| R-7: no `useInterruptSlot` in the row's span (`:5155-5200`) | VERIFIED |
| File ownership: commit `f449b1ad` touches only TradesScreen.tsx, TradeHomeUtilityRow.tsx, the guard, two CLAUDE.md rows + status doc | VERIFIED |

## Findings

**F-1 · minor · Group A TestFlight checklist steps 6–7 omit the
`testing.stage_users` feasibility branch.**
- Repro: prd.md §6d step 6 says "a fresh stage account (TestStagesScreen)";
  step 7 says "fresh stage user". The Test-stages row is gated on
  `testing.stage_users` (`mobile/src/screens/settings/sections/TestingSection.tsx:46`),
  which is `false` in `config/features.json:181` and only delivered per-device
  via the experiment overlay.
- Expected (PRD-ref): an executable checklist step. Actual: on a device
  without the overlay flag the Test-stages row is absent and steps 6–7 stall
  with no instruction. Group B's checklist (397 prd.md §6c step 1) documents
  the exact fix — flip `testing.stage_users` → `true` + `POST
  /api/feature-flags/reload` for the QA window, flip back after — Group A's
  should carry the same one-line branch (the step 6 fallback account
  "jonbonjourvi" partially mitigates for step 6, but step 7's first-run
  requires a fresh/stage user).
- Evidence: features.json:181; TestingSection.tsx:46; 397-swipe-tour-placement/prd.md §6c step 1.

Observation (not a finding): S1b turns assertions 2 and 3 red alongside the
named assertion 1 (renaming the container also breaks the gate locator).
Collateral reds beyond the named case; the named case still fires.

## TestFlight checklist (operator-run)

Verified executable as written except the step-6/7 caveat above. Refined wording:

1. **Strip variant (your device), outlook declared:** Acquire tab — below the
   icon utility row, an "Outlook & filters" line shows your current outlook
   (e.g. "Contending"), not blank, not "Not set".
2. The icon row **no longer shows a Filters button**; Today's trade / Draft /
   Free agents / Manual calc / Track record (those present) still navigate.
   (Verified: `TradeHomeUtilityRow.tsx` carries exactly these five testIDs and
   no `conditions` control.)
3. Tap **Change** → the full sheet opens: outlook chips, Shopping/Chasing,
   trade-idea lane, fairness, League + Trading-with, untouchables, intent.
4. Change any preference, close the sheet → "Preferences changed — tap to
   refresh" appears; tap → deck regenerates; the row reflects the new
   outlook/summary.
5. **Undeclared state** (fresh account that has never declared an outlook —
   there is no clear-outlook affordance): the line reads "Not set"; Change
   opens the same sheet; the "Set your team's outlook" banner may also appear.
   Bonus: save Chasing/Shopping positions *without* picking an outlook → the
   line reads **"Not sure"** (never "Not_sure", never "Not set").
6. **Control variant** — a fresh stage account (TestStagesScreen) is off the
   tester allowlist → no `trades_home_inline` variant → control. **Expected:
   the chip mode bar renders instead of the icon utility row — correct for
   this cohort, not a bug.** Confirm the same "Outlook & filters" line renders
   below the mode bar and Change opens the full sheet. *Caveat (F-1): if
   Settings → Testing shows no Test-stages row, flip `testing.stage_users` →
   true + `POST /api/feature-flags/reload` for the QA window (flip back
   after), or use a non-allowlisted tester account (e.g. jonbonjourvi).*
7. **First-run** (fresh stage user; same F-1 caveat): the minimized row is
   absent; the outlook banner is the entry (it may be deferred behind
   quickset/coach-mark/apple prompts); after the first swipe + remount the
   row appears. A *declared*-outlook first-run user has no in-page edit until
   the next mount — that is the accepted A1 residual, not a failure.
