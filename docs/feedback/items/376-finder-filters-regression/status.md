# FB-376 + FB-379 + FB-394 — finder filters / outlook & prefs regression (Group A canonical)
- **Status:** built 2026-08-24 — on `feat/fb376-outlook-filters-row-mobile`, all static gates green (see Build report below); awaiting review/merge + operator TestFlight checklist (prd.md §6d)
- **Covered:** #376, #379, #394 (+#333 verified delivered on the merged calculator, `InLeagueCalculator.tsx:784-824` — no work; see prd.md §5)
- **Path:** fast-track bug (mobile-only); stayed fast-track — plan found no layout work
- Docs: [plan.md](plan.md) → [prd.md](prd.md) + [scope.md](scope.md) (analytics: existing `outlook_saved` covers it; no schema/API/flag changes)
- Batch plan: [346-quickset-tier-drop/plan.md](../346-quickset-tier-drop/plan.md)

History that matters: #376's first diagnosis (2026-08-20, in
[374-partners-copy-and-finder-conditions](../374-partners-copy-and-finder-conditions/status.md))
found the filters hidden by the `trades_home_inline` experiment's
`TradeHomeUtilityRow` swap; that fix merged. The #384 merged-calculator
rebuild (1.16.0→1.16.2) reshaped TradesHome again, and #394 (2026-08-24,
1.16.2) reports outlook & preferences still/again completely missing —
operator calls it the most critical bug. #379 rules the top-tab placement
out: filters belong inside the Find-a-Trade page, minimized by default.
Check #360/#361 ("positions I'm NOT looking for") as a candidate rider on
this surface — flagged in the batch plan, not committed.

---

## Build report — 2026-08-24, branch `feat/fb376-outlook-filters-row-mobile`

Base: `a4c25816` (Group A Phase-1 specs signed off; sits on `ff153a0` = the PRD's cited base).
The build worktree's original HEAD (`cce3895f`, a recovery-ledger doc commit) was NOT in this
branch's ancestry — deliberately branched from the spec commit instead; no code differs between
the two besides that doc.

### Diff summary

| File | Change |
|---|---|
| `mobile/src/screens/TradesScreen.tsx` | **R-1:** minimized "Outlook & filters" row (`trades.outlook-fallback` :5156, `.change` :5166, `.details` :5192) inside the `outlookReceiptWrapRef` wrapper (:5130), sibling directly below `<OutlookBiasReceipt/>`, gated exactly `consolidateOn && !outlookReceiptShown && !firstRun` (:5155). Change → `setDnaSheetOpen(true)` (:5172). Value map `OUTLOOK_FALLBACK_LABEL` (:7446): LEAN names for the four directional outlooks, `not_sure`→"Not sure", null→"Not set" at the call site. Styles :7765+ mirror `calc.outlook-fallback` (`InLeagueCalculator.tsx:1708-1721`) + the receipt's `marginBottom: space.md`. **R-2:** `onConditions` pass removed (was :5075-5077). |
| `mobile/src/components/TradeHomeUtilityRow.tsx` | **R-2:** `onConditions` prop, doc comment, destructure, and the Filters `Pressable` (`trades.home-utility.conditions`) removed; `onTrackRecord` doc's dangling reference fixed. No other button changed. |
| `mobile/tests/check-finder-conditions-reachable.js` | Full rewrite per prd.md §6a — 6 assertions, same commit as the code (old assertions 1–4 inverted). |
| `mobile/src/screens/CLAUDE.md`, `mobile/src/components/CLAUDE.md` | One-line map rows updated (PRD §7). |

### Gate results (D-056, static only)

- `npm ci` (no symlinked node_modules) → clean
- `npx tsc --noEmit` → clean
- `node tests/check-finder-conditions-reachable.js` → **6/6 green**
- Full structural loop: **all 77 `mobile/tests/check-*.js` green**, including untouched
  `check-trades-banner-region.js` (10/10 — 1a one receipt, 1c/1d strip placement),
  `check-calc-merged-behavior.js`, `check-guide-spotlight-tracking.js`
- `bash scripts/testid-lint.sh` → OK

### Sabotage matrix (every case: applied → RED with the named assertion → reverted → green)

| Case | Sabotage | Result |
|---|---|---|
| S1a | delete the row entirely | RED — assertion 1 (also 2, 3) |
| S1b | delete just the container id, keep `.change` (boundary-anchor test) | RED — assertion 1 |
| S2a | prepend `homeInlineVariant !== 'control' && ` (the whitelist-beating alias) | RED — assertion 2 |
| S2b | append `&& showInlineHome` | RED — assertion 2 |
| S2c | append `&& presentationV2On` | RED — assertion 2 |
| S2d | drop `!firstRun` | RED — assertion 2 |
| S2e | gate via an intermediate variable (indirection dodge) | RED — assertion 2 |
| S3 | move the row into the `{!consolidateOn ? (` legacy branch (anchor+balanced-paren located, not line numbers) | RED — assertion 3 |
| S4 | swap `setDnaSheetOpen(true)` → `setOutlookOpen(true)` inside the row's span | RED — assertion 4 |
| S5a | re-add the `onConditions` prop pass in TradesScreen | RED — assertion 5 |
| S5b | re-add the `trades.home-utility.conditions` testID | RED — assertion 5 |
| S6 | drop `hideTeamAndPlayer={sheetTargetingOn && consolidateOn}` | RED — assertion 6 |

Final restored run: 6/6 green. Missing-source-file case exits 2 (harness failure, not "0 failed").

### Code-walk proof (file:line vs this diff)

**Render chain.** `finderMode` (`TradesScreen.tsx:700-702`) gates the receipt wrapper
(`:5127-5130`, `View ref={outlookReceiptWrapRef}`). Inside it: `<OutlookBiasReceipt
details={receiptDetails} …/>` (`:5131-5139`) then the new row (`:5155-5201`) gated
`consolidateOn && !outlookReceiptShown && !firstRun` (`:5155`). `consolidateOn = fullSheetOn &&
!!finderMode` (`:731`) ⊆ `finderMode`, so the row can only render where the wrapper exists.
`outlookReceiptShown = !!finderMode && outlookReceiptCovers(outlookDirectionOn, declared,
inferred)` (`:1047-1053`) is the receipt's own predicate (`OutlookBiasReceipt.tsx:46-54,96`):
under `consolidateOn && !firstRun`, row renders ⟺ receipt hidden — **exactly one of
{receipt, row} in every such cell (R-3)**, by shared predicate, not a second flag read.

**Truth table** — {strip, canvas, control} × {`trade.outlook_direction` false, true} ×
{declared directional, `not_sure`, undeclared}, all with `consolidateOn` true, not first-run:

| flag | outlook | `outlookReceiptShown` | Renders | Sheet entry |
|---|---|---|---|---|
| false (today) | any | false (`covers` returns false at `OutlookBiasReceipt.tsx:51`) | row — "All-in/Contending/Rebuilding/Tanking" / "Not sure" / "Not set" | row Change → `setDnaSheetOpen(true)` (`:5172`) |
| true | directional (declared or inferred) | true (`LEAN[resolved]` exists) | receipt | receipt Change (`:5137`) |
| true | `not_sure` / none resolved | false (`LEAN` has no `not_sure` key) | row | row Change |

The variant axis is degenerate **by construction**: the gate reads no variant and no flag
(guard assertion 2 whitelist), and the wrapper's own gate (`:5127`) reads only `finderMode`.
Control variant (**R-4**): `showInlineHome` false (`:707`) → `TradeFinderModeBar` renders
(`:5088-5118`, chips hidden per `hideTeamAndPlayer` `:5112`) → wrapper + row still render below
it — the control cohort's sole sheet entry, where before this diff it had none.
**R-5** holds the same way: no `outlookDirectionOn` (`:625`) read anywhere in `:5155-5201`.

**First-run cells (honest, per A1):** `firstRun` latches per mount (`:433-440`). Undeclared →
interrupt banner (`outlookBannerWants` `:3038-3040`) *when the slot frees* (arbitered below
quickset/coach-mark/apple, `:3006-3045`). Declared → **accepted residual**: `inferredOutlook`
is null once declared (`:1032-1035`) so the banner does not cover it; no in-page edit until the
next mount.

**R-7:** the row's diff span (`:5140-5201`) contains no `useInterruptSlot` — persistent chrome.

**Value mapping (R-1/B-2):** `OUTLOOK_FALLBACK_LABEL` (`:7446-7452`) carries the receipt's
LEAN names verbatim (`OutlookBiasReceipt.tsx:34-39`) plus `not_sure`→"Not sure"; null/absent →
"Not set" at the call site (`:5159-5163`). `cap()` is never applied to `team_outlook` in the
row. Details line (`:5190-5198`) reuses the screen's existing `receiptDetails` memo
(`:1100-1115`) — same #315 content contract as `trades.outlook-receipt.details`.

**Removal proof (R-2):** `git grep -n "onConditions\|home-utility.conditions" mobile/src/`
returns nothing.

**R-6 untouched surfaces:** the diff touches no line of `InLeagueCalculator.tsx`,
no queue/canvas/action-row code (D-151/D-152/D-153); `TradingWithStrip` still mounts after the
wrapper (`:5238`, banner-region guard 1d green); prefs-changed strip intact; guide target
registration `trades.outlook-receipt.change` → `outlookReceiptWrapRef` untouched (the row
renders *inside* that wrapper, giving the N2-A spotlight a real frame — flagged to Group B in
prd.md §7).

**Chalkline:** ink2 bg, 1px `ink.line`, `radii.sm` (≤8px), `minHeight 44`, 13pt `bodySm`, ice
on the single action only, no icons/emoji/gradients; pressed = 0.6 opacity per the calculator.

### Deviations from the PRD

None in contract terms. Two notes: (1) the LEAN display names are duplicated into
`OUTLOOK_FALLBACK_LABEL` rather than imported — `OutlookBiasReceipt.tsx` keeps `LEAN` private
and that file is outside this group's owned list; the duplication is commented against #253
canonical order. (2) TEST_LEDGER.md and DECISIONS.md (the B0 mortality note) are outside this
group's owned file list — the sabotage-matrix evidence lives here for the wave orchestrator to
ledger at ship time.
