# PRD — #376/#379/#394: minimized "Outlook & filters" row on TradesHome

**Date:** 2026-08-24 · **Path:** fast-track bug (mobile-only) · **Group A author output**
**Covers:** #394 (canonical defect), #379 (placement ruling), #376 (history — reachability half shipped in `bda0d51`). **Verified rider:** #333 (no work — see §6). **Base:** `origin/main` @ `ff153a0`. Every file:line cite below re-verified against this tree.
**Plan:** [plan.md](plan.md) · **Scope block:** [scope.md](scope.md)

---

## 1. Repro + root cause (re-verified)

**Repro (operator's exact assignment):** `trades.finder_hub` / `trades.edit_full_sheet` / `trades.sheet_targeting` all true, `trade.outlook_direction` **false**, `calc.merged_layout` true (`config/features.json:11,60,84,213,217`), experiment `trades_home_inline` = **strip**, outlook already declared. TradesHome renders **no in-page outlook/preferences surface**; the only sheet entry is the 28pt settings-glyph "Filters" button in the top utility row — the placement #379 ruled against, and the invisibility #394 reports as "outlook & preferences completely missing."

**Root cause chain** (all cites verified):

1. #257 consolidated the in-page Controls Card into `TradeDnaSheet` behind `consolidateOn = fullSheetOn && !!finderMode` (`TradesScreen.tsx:731`), making `OutlookBiasReceipt`'s "Change" the designed sole in-page entry (comment at `:5324-5329`).
2. The receipt renders null unless `trade.outlook_direction` is on (`OutlookBiasReceipt.tsx:81,96,101-103` via `outlookReceiptCovers` `:46-54`) — an engine-weighting flag (#175) that has been false since it shipped. The designed entry never rendered for anyone. The screen's own fallback outlook row (`TradesScreen.tsx:5407-5424`) sits inside the `!consolidateOn` legacy branch (`:5330`) — dead for every finder-mode user.
3. #384 fixed this exact coupling on the calculator only: `InLeagueCalculator.tsx:713-744` renders `calc.outlook-fallback` whenever the receipt reports hidden. TradesHome never got the twin. The #376 fix (`bda0d51`) then restored reachability via the utility row (`TradesScreen.tsx:5075-5077`, `TradeHomeUtilityRow.tsx:72-86`) — the placement #379 subsequently ruled out.

**Worse for control-variant users:** the mode bar's Team/Player chips are hidden (`hideTeamAndPlayer={sheetTargetingOn && consolidateOn}`, `:5117`), the utility row doesn't render for them (`showInlineHome`, `:707`), so a control-variant user with a declared outlook has **no sheet entry at all**.

## 2. Orchestrator arbitrations (provisional — open to critique)

- **A1:** the new row keeps the Planner-recommended `!firstRun` gate. First-run chrome stays minimal (F11, comment `:5315-5318`). Coverage is exactly this: an **undeclared-outlook** first-run user gets the interrupt banner (`outlookBannerWants`, `:3038-3040`; `ux.outlook_inline_default` true, `features.json:151`) *when the interrupt slot frees* — it is arbitered below the quickset / coach-mark / apple prompts (`:3006-3045`), so it may be deferred, not instant. A **declared-outlook** first-run user (rare — declaration usually postdates the first swipe) has **no in-page edit until the next mount**. That is the accepted residual, stated plainly; it is *not* banner-covered (`inferredOutlook` is null once declared, `:1032-1035`, so `outlookBannerWants` is false).
- **A2:** the top utility-row Filters button is **removed outright in the same change** (per #379's explicit operator ruling) — no both-entries transition period.

Author's position: both stand. **A2's complete safety argument:** the row's gate is pinned as the exact whitelist `consolidateOn && !outlookReceiptShown && !firstRun` (guard assertion 2 — any added conjunct, aliased or not, turns it red), so every green build renders the row unless one of exactly three predicates is false, and each false-branch has a verified covering surface:
- ¬`consolidateOn` → the legacy Controls Card returns with its own outlook row + OutlookSheet entry (`:5330` branch, row at `:5407-5424`);
- `outlookReceiptShown` → the receipt itself renders with its Change control into the same sheet (`OutlookBiasReceipt.tsx:96,101-126`);
- `firstRun` → a one-mount latch (`:433-440`): undeclared cell covered by the interrupt banner (above), declared cell is the logged A1 residual, cleared on next mount.

No variant predicate can re-strand the control cohort past the whitelist, and assertion 5 pins the Filters button's absence — do not ship assertion 5 without assertion 2.

## 3. Requirements

**R-1 — Always-available minimized row.** TradesHome renders a minimized "Outlook & filters" row (only its **Change** control is pressable — tap-surface call in §4) inside the existing receipt wrapper (`View ref={outlookReceiptWrapRef}`, `TradesScreen.tsx:5132-5146`), as a sibling directly below `<OutlookBiasReceipt …/>` — the same composition the calculator uses (`InLeagueCalculator.tsx:713-744`). **Exact gating expression — this precise conjunction, nothing added, nothing dropped:**

```
consolidateOn && !outlookReceiptShown && !firstRun
```

(`outlookReceiptShown` is the screen's existing predicate at `:1047-1053`; `firstRun` at `:433-440`; A1 above.) Content: label **"Outlook & filters"**; **value mapping, exactly:** the four directional `team_outlook` values render the receipt's `LEAN` display names — `championship`→"All-in", `contender`→"Contending", `rebuilder`→"Rebuilding", `jets`→"Tanking" (`OutlookBiasReceipt.tsx:34-39`, so the row and receipt share one vocabulary); the persisted `not_sure` renders **"Not sure"** (it *is* declared — the sheet itself writes it when positions are saved without an outlook pick, `TradeDnaSheet.tsx:494-496` — never "Not_sure" via `cap()` and never "Not set"); and **"Not set"** renders only when `team_outlook` is null/absent. Declared values only — an inference is not "set"; the interrupt banner owns confirming inferences. When the screen's existing `receiptDetails` memo (`:1100-1115`) is non-empty, a second dim line renders it (same ≤2-row budget as the receipt's #315 contract). **Change** → `setDnaSheetOpen(true)`, opening the full `TradeDnaSheet` (`:4929-4976`: outlook chips, Chasing/Shopping, fairness, lanes, League/Trading-with targeting, untouchables, intent).

**R-2 — Utility-row Filters entry removed (A2).** Drop the `onConditions` pass (`TradesScreen.tsx:5070-5077`) and the prop + control in `TradeHomeUtilityRow.tsx` (prop doc `:35-49`, control `:72-86`), plus the orphaned prop destructure. No other button in that row changes.

**R-3 — No-double-render invariant.** The row's gate is the exact complement of the receipt's own render predicate inside the shared wrapper (#254 rule, `OutlookBiasReceipt.tsx:44-54` + `TradesScreen.tsx:1040-1053`): under `consolidateOn && !firstRun`, exactly one of {receipt, new row} renders; they can never both appear and never both vanish. If `trade.outlook_direction` ever flips true with a directional outlook, the receipt takes over and the row yields — by construction, not by a second flag read.

**R-4 — Control-variant users get a working entry.** The row's gate must NOT reference `showInlineHome` (`:707`). The receipt wrapper is gated `finderMode ?` (`:5132`) and `consolidateOn` ⊆ `finderMode` (`:731`), so a control-variant guided user renders: `TradeFinderModeBar` (chips hidden per `:5117`) → **the new "Outlook & filters" row** → deck. That row is their sole sheet entry — previously they had none (§1).

**R-5 — Flag/variant independence.** The row's condition reads neither `useFlag('trade.outlook_direction')` / `outlookDirectionOn` (`:625`) nor any experiment variant. Behavior:
- flag **false** (today): receipt always hidden → row renders for all outlook states (declared shows the value; undeclared shows "Not set" and coexists with the interrupt banner, which is transient slot-arbitered chrome, not this row's concern);
- flag **true**: directional outlook → receipt renders, row doesn't; non-directional/no outlook → row renders. All × {strip, canvas, control}.

**R-6 — #384/W6 contract non-regressions.** Untouched surfaces: the calculator's own receipt+fallback (`InLeagueCalculator.tsx:713-744`); the ✓ queue cell and `POST /api/trades/queue` (W6-A, D-152); the canvas fair-package fork and `FinderHandoff`/`fairAnchor` (W6-B, D-153); the Find-a-Trade 70/15/15 action row (D-151/D-153); `TradingWithStrip` mount order (#314, `:5182-5189`); the prefs-changed strip (`:5153-5169`); the interrupt banner (`:6058-6101`). The guide target id `trades.outlook-receipt.change` → `outlookReceiptWrapRef` registration (`:3229,:3246`) is untouched.

**R-7 — Not an interrupt slot.** The row claims no `useInterruptSlot` — it is persistent chrome. Path D died precisely because it was slot-claimed and condition-gated.

## 4. Copy / design (Chalkline — ADR-004/005)

Row spec mirrors the calculator's `calc.outlook-fallback` (`InLeagueCalculator.tsx:722-742`, styles `:1708-1721`), which is itself the receipt's quiet bar minus the lean claim:

- Container: `ink.ink2` background, 1px `ink.line` border, `radii.sm` (≤8px), `minHeight: 44` (touch floor), `paddingHorizontal: 10`, `marginBottom: space.md` (the receipt's own `:153` — the wrapper adds no layout, so the row carries its own bottom margin exactly as the receipt does).
- Row 1: `type.bodySm` (13pt ≥ the 11pt floor) `chalk.dim` text — **"Outlook & filters · Contending"** / **"Outlook & filters · Not set"** — plus an ice `Change` pressable (`ice.base`, `fonts.uiSemi`, `hitSlop 8`, pressed → `ice.press` or 0.6 opacity per the calculator).
- Row 2 (only when `receiptDetails` non-empty): one dim ellipsized `bodySm` line, e.g. "Chasing WR, Picks · 2 off the table" — same content contract as `trades.outlook-receipt.details` (#315: never team scope or specific players). Row 2 is not interactive.
- **Tap surface (pinned): Change-only pressable.** The row body is not tappable; only the `Change` control opens the sheet — matching the shipped `calc.outlook-fallback` (`InLeagueCalculator.tsx:726-741`) and the receipt itself (`OutlookBiasReceipt.tsx:114-126`), so all three sibling surfaces carry one interaction contract and the calculator's styles reuse verbatim. A whole-row tap is arguably better UX but is a new contract for this pattern — deferred to Wave B0's re-layout as a candidate, not shipped here.
- No new colors, no icons-as-emoji, no gradients; ice is used for the one action only. Accessibility: `accessibilityRole="button"`, label "Change outlook and trade filters".
- **testIDs:** `trades.outlook-fallback`, `trades.outlook-fallback.change`, `trades.outlook-fallback.details` — mirrors the `calc.outlook-fallback` grammar; literal strings, pass `mobile/scripts/testid-lint.sh` without allowlist entries.

## 5. Out of scope

- **#360/#361** "positions we're NOT looking for" — needs a new `league_preferences` field + generate-side filter: schema/API bright line, own item. This fix only makes their natural home (the DNA sheet's Chasing/Shopping block) discoverable.
- **Wave B0 / D-158** layout merge (`docs/plans/onboarding-tour-merge/plan.md` §3b) — **the row is deliberately mortal.** B0 mounts `InLeagueCalculator` inline, which carries its own outlook surface (`calc.outlook-row` + fallback, `InLeagueCalculator.tsx:713-744`); B0's builder must delete `trades.outlook-fallback` and retire/rewrite guard assertions 1–4 in the same change, or TradesHome shows two outlook surfaces. This mortality note goes in the planned DECISIONS.md entry and as a pointer in the B0 plan.
- **Flipping `trade.outlook_direction`** — lights the #175 engine weighting; also insufficient (receipt still hides on non-directional outlooks).
- **`trades_home_inline` experiment changes** — no assignment, weighting, or stop.
- **#333** — verified delivered on the merged calculator: `calc.league-dropdown` + `calc.team-dropdown` side-by-side beneath the outlook section, `InLeagueCalculator.tsx:784-824` (`calc.merged_layout` true). No TradesHome work; full parity arrives with Wave B0.

## 6. D-056 evidence plan

### (a) Rewrite `mobile/tests/check-finder-conditions-reachable.js` (owned by this group alone)

Filename and `npm run test:finder-conditions` (`mobile/package.json:36`) kept; invariant broadens from "reachable" to "reachable in the ruled place." **Assertions 1, 2 and 5 replace or invert old assertions 1–4, and CI runs every `check-*.js` (`.github/workflows/ci.yml:47`), so the rewrite must land in the same commit as the code change or CI goes red both ways.** Each assertion, its sabotage (must turn it red), and the self-satisfaction check (builder applies each sabotage to a scratch copy, runs the guard, observes red, reverts — logged in TEST_LEDGER as "sabotage matrix run"):

| # | Assertion | Named sabotage → red |
|---|---|---|
| 1 | `TradesScreen.tsx` contains the exact boundary-anchored ids `testID="trades.outlook-fallback"` and `testID="trades.outlook-fallback.change"` (closing-quote-exact per id — `trades.outlook-fallback` is a prefix of its children, so an unanchored match would pass with the container deleted; the #384 `/isDemo/` lesson) | Delete the row (or delete just the container, keeping `.change`) |
| 2 | **Whitelist, not blacklist:** the row's render condition **equals** `consolidateOn && !outlookReceiptShown && !firstRun` — whitespace/paren-tolerant, but no extra conjuncts and none missing. Subsumes the old flag/variant blacklists and closes their aliasing dodge: `showInlineHome`, `homeInlineVariant !== 'control'`, `homeInlineStripOn`, `outlookDirectionOn`, or any derived boolean added as a conjunct all turn it red without being named | **Proving sabotage:** prepend `homeInlineVariant !== 'control' && ` (the alias that beats a blacklist) → red. Also red: `&& showInlineHome`, `&& presentationV2On`, or dropping `!firstRun` |
| 3 | The row's element sits **outside** the `!consolidateOn` legacy branch — the branch located by its anchor expression `{!consolidateOn ? (` (and matching close), **never by line number** (this very diff shifts `:5330` by deleting lines above it) | Move it into the legacy Controls Card |
| 4 | **Within the row's extracted JSX span** (not file-global — `setDnaSheetOpen(true)` appears at `:787,:813,:852,:3348,:5142` and would self-satisfy), the change control calls `setDnaSheetOpen(true)` and not `setOutlookOpen` | Swap the setter |
| 5 | `TradeHomeUtilityRow.tsx` contains no `trades.home-utility.conditions` and `TradesScreen.tsx` passes no `onConditions` (#379 — absence is now the invariant) | Re-add the button or the prop pass |
| 6 | `hideTeamAndPlayer={sheetTargetingOn && consolidateOn}` intact (carried #269 guard, old assertion 5) | Drop the guard |

Self-satisfaction guard: the suite must also fail loudly (exit 2 style) if either source file goes missing, and assertion matching runs against the stripped (comment-free) source as the current guard does (`:33`), so a commented-out row can't satisfy them. Assertion 2's whitelist is what makes A2 mechanically safe (§2): a green guard means the row renders unless one of exactly three predicates is false, and each false-branch has a cited covering surface.

### (b) `check-trades-banner-region.js` — verified, **no edit**

Its assertions survive the change untouched: 1a counts exactly one `OutlookBiasReceipt` (we add a sibling row, not a second receipt); 1c/1d pin `TradingWithStrip` outside `modeBarWrap` and after the receipt (the new row sits inside the wrapper, before the strip); 2/3/4 don't touch this region. Run it in the gate to confirm.

### (c) Code-walk proof (outline — builder fills file:line for the final diff)

A truth table: {strip, canvas, control} × {`trade.outlook_direction` false, true} × {outlook declared, undeclared, non-directional} → trace `finderMode` (`:700-702`) → wrapper (`:5132`) → receipt predicate (`OutlookBiasReceipt.tsx:96`) vs. row gate → prove **exactly one persistent outlook surface renders in every non-first-run cell** and `TradeDnaSheet` is reachable from it; plus the two first-run cells shown honestly: undeclared = interrupt banner *when the slot frees* (arbitered below quickset/coach-mark/apple, `:3006-3045`); declared = **accepted gap** (A1 residual — not banner-covered, `inferredOutlook` null once declared per `:1032-1035`), cleared on next mount. Ends with the removal proof: `git grep onConditions mobile/src` returns nothing.

### (d) Operator TestFlight checklist

1. **Strip variant (your device), outlook declared:** Acquire tab — below the icon utility row, an "Outlook & filters" line shows your current outlook (e.g. "Contending"), not blank, not "Not set".
2. The icon row **no longer shows a Filters button**; Draft / Free agents / Manual calc (and Today/Track record if present) still navigate.
3. Tap **Change** → the full sheet opens: outlook chips, Shopping/Chasing, trade-idea lane, fairness, League + Trading-with, untouchables, intent.
4. Change any preference, close the sheet → "Preferences changed — tap to refresh" appears; tap → deck regenerates; the row reflects the new outlook/summary.
5. **Undeclared state** (second account that has never declared an outlook — there is no clear-outlook affordance, so a fresh account is the only path): the line reads "Not set"; Change opens the same sheet; the "Set your team's outlook" banner may also appear — both work. Bonus check on the same account: save Chasing/Shopping positions *without* picking an outlook → the line now reads **"Not sure"** (the sheet persists `not_sure`), not "Not_sure" and not "Not set".
6. **Control variant** — mechanism: a fresh stage account (TestStagesScreen) is off the tester allowlist, and the `trades_home_inline` experiment targets the allowlist only, so no variant is assigned → control. **Expected: the chip mode bar renders instead of the icon utility row — that is correct for this cohort, not a bug.** Confirm the same "Outlook & filters" line renders below the mode bar and Change opens the full sheet. Fallback if a stage account is ever allowlisted: use a non-allowlisted tester account (e.g. jonbonjourvi). **Feasibility note (QA round 1):** TestStagesScreen is reachable only when `testing.stage_users` is delivered to the device (false in `features.json:181`, per-device via experiment overlay) — if the row is absent, flip the flag + `POST /api/feature-flags/reload` for the QA window and flip back, same procedure as Group B's checklist step 1.
7. **First-run** (fresh stage user): the minimized row is absent; the outlook banner is the entry; after the first swipe + remount the row appears.

### Requirement → criterion map

| R | Mechanical criterion |
|---|---|
| R-1 | guard 1, 2, 4; checklist 1, 3, 4 |
| R-2 | guard 5; checklist 2 |
| R-3 | guard 2 (whitelist names `outlookReceiptShown`); code-walk table |
| R-4 | guard 2 (whitelist admits no variant conjunct, aliased or not); checklist 6 |
| R-5 | guard 2 (whitelist admits no flag conjunct); code-walk table; checklist 5 |
| R-6 | `check-calc-merged-behavior.js` + `check-trades-banner-region.js` + `check-guide-spotlight-tracking.js` all green, untouched |
| R-7 | code-walk (no `useInterruptSlot` call in the row's diff); guard 3's positional check keeps it out of banner slots |

**Gate before merge:** `pytest backend/tests` (unchanged), `npx tsc --noEmit`, `bash mobile/scripts/testid-lint.sh`, full `mobile/tests/check-*.js` loop, sabotage matrix logged, TEST_LEDGER entry. `FTF_SKIP_SIM_GATE=1` standing posture (D-056).

## 7. Coordination

- **This group OWNS `mobile/src/screens/TradesScreen.tsx` and `mobile/src/components/TradeHomeUtilityRow.tsx`** for this wave. Group B reads TradesScreen only — serialize or rebase if Group B must touch it.
- **Note to Group B:** N2 form A's spotlight target `outlookReceiptWrapRef` (`TradesScreen.tsx:3229`, registered as `trades.outlook-receipt.change` at `:3246`) today measures an empty wrapper (the receipt renders null). Once the fallback row renders inside it, the spotlight gains a **real frame** — an improvement, but plan tour-frame assertions against the new geometry.
- `check-finder-conditions-reachable.js` is owned here alone.
- `mobile/src/components/CLAUDE.md` (TradeHomeUtilityRow row) and `mobile/src/screens/CLAUDE.md` (TradesScreen row) need their one-line descriptions updated with the diff.

## 8. Reconciliation (summary — full round history in [reconciliation-log.md](reconciliation-log.md))

| Date | Point | Resolution |
|---|---|---|
| 2026-08-24 | Orchestrator A1: keep `!firstRun` | **Provisional, accepted.** Coverage stated precisely in §2: undeclared first-run → interrupt banner when the slot frees; declared first-run → accepted residual (no in-page edit until next mount), *not* banner-covered. |
| 2026-08-24 | Orchestrator A2: remove utility-row Filters outright, no transition | **Provisional, accepted with the safety argument completed (§2).** The exact-whitelist gate (guard assertion 2) plus per-predicate covering surfaces make A2 mechanically safe; do not ship assertion 5 without assertion 2. |
| 2026-08-24 | Planner cite drift | Only one found: #333 dropdown block is `InLeagueCalculator.tsx:784-824` (plan said 784-818). All other cites verified exact. |
| 2026-08-24 | Round 3 (critique incorporated) | B-1 whitelist gate assertion + completed A2 argument; B-2 `not_sure` → "Not sure" + LEAN labels; N-1…N-6 all applied — see reconciliation-log.md Round 3. |
