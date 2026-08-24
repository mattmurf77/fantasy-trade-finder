# Plan — #376/#379/#394: outlook & finder filters back inside the Find-a-Trade page

**Date:** 2026-08-24 · **Group A planner output (fast-track bug path)**
**Covers:** #394 (canonical for this fix), #379 (ruling: filters in-page, minimized default), #376 (history; its reachability half already shipped in `bda0d51`). **Verified rider:** #333. **Reported-on riders:** #360/#361 (report only, no commitment).
**Base:** `origin/main` @ `ff153a0`, branch `claude/new-user-feedback-55320e`. All file:line cites are against this tree.

---

## 1 · Does the defect reproduce on current main, for the operator's exact assignment?

**Yes — as a placement/visibility defect, not a reachability one.** The operator's assignment: every gate flag true (`trades.finder_hub`, `trades.edit_full_sheet`, `trades.sheet_targeting` — `config/features.json`), experiment `trades_home_inline` = variant **strip** (tester allowlist, 100% strip since 2026-08-09), `trade.outlook_direction` **false**, `calc.merged_layout` true, an outlook already declared. On that assignment, TradesHome renders **no in-page outlook or preferences surface at all**; the single entry to the filters is a 28pt icon button labeled "Filters" in the top utility row — the exact placement #379 ruled "doesn't make sense".

Every path to the outlook/preferences editor (`TradeDnaSheet`, the full #257 sheet) from TradesHome, with its conditionals:

| # | Path | Conditionals | Operator sees it? |
|---|---|---|---|
| A | **Utility row "Filters" button** → `setDnaSheetOpen(true)` | `finderMode` truthy (`trades.finder_hub` on + `TradesHome` `initialParams {mode:'guided'}`) → `TradesScreen.tsx:700-702`; `showInlineHome` (`:707`, guided + variant ≠ control); handler gated `consolidateOn` (`:5075-5077`); control renders `TradeHomeUtilityRow.tsx:72-86` | **Yes** — the only visible entry. This is #379's "Filters in the top tab" |
| B | **`OutlookBiasReceipt` "Change"** (`TradesScreen.tsx:5132-5146`) | `OutlookBiasReceipt.tsx:81` reads `trade.outlook_direction`; `:96` `hidden = !outlookReceiptCovers(directionOn, …)`; `:101-103` returns null when hidden | **Never.** The flag shipped `false` in `4f3b1fe` (2026-07-25) and has never flipped (`git log -S`, one hit). The receipt has never rendered on anyone's TradesHome |
| C | **Legacy in-page Controls Card** — outlook "Not set / Edit" row (`:5407-5424`), fairness slider (`:5433-5483`), lane pills (`:5497+`) | Entire card gated **`!consolidateOn`** (`:5330`); `consolidateOn = fullSheetOn && !!finderMode` (`:731`) is **true** for every finder-mode user since `trades.edit_full_sheet` lit | **Never** (for anyone in finder mode — i.e. everyone on the guided landing) |
| D | **Outlook interrupt banner** (`:6058-6101`, Confirm/Change → sheet) | `outlookBannerWants = !!inferredOutlook \|\| (outlookInlineOn && prefs && !team_outlook)` (`:3038-3040`) — only while no outlook is declared | **No** — operator declared an outlook long ago |
| E | Legacy `editDna:true` route param (`:786-791`) | stale deep links only | No |

**Verdicts per report:** #376's literal complaint ("filters removed") no longer reproduces — path A restored reachability and is on main since `bda0d51` (in the 1.16.x builds). #379 reproduces exactly: the filters live **only** in the top utility row. #394 reproduces exactly: with paths B–D all dead, there is **no in-page "outlook & preferences" surface** on TradesHome — a user who doesn't decode the settings-glyph icon as "outlook & preferences" correctly reports it completely missing. Note the **control cohort is worse off still**: `TradeFinderModeBar` carries no conditions entry (its Team/Player chips are hidden by `hideTeamAndPlayer={sheetTargetingOn && consolidateOn}`, `:5117`), so a control-variant user with a declared outlook has *no* sheet entry at all.

## 2 · Root cause

Three decisions stacked into a hole; no single commit "removed" anything:

1. **#257** consolidated the in-page Controls Card into the full `TradeDnaSheet`, making `OutlookBiasReceipt`'s "Change" the designed sole in-page entry (`TradesScreen.tsx:5324-5329` comment states this).
2. **The receipt's render is coupled to `trade.outlook_direction`** (`OutlookBiasReceipt.tsx:81,96`) — an *engine weighting* flag (#175) that has been false since birth. So the designed entry never existed. The screen's own fallback outlook row (`:5407`) that acknowledges this exact case ("`trade.outlook_direction` off") was left **inside the `!consolidateOn` branch** — dead code for the consolidated world.
3. **#384 fixed this same coupling on the calculator only**: `InLeagueCalculator.tsx:713-744` renders a `calc.outlook-fallback` row ("Outlook · Not set · Change") whenever the receipt reports hidden. TradesHome never got the twin. The #376 fix (`bda0d51`) then restored *reachability* into the utility row — the placement #379 ruled against three days later.

Nothing left for the build agent to root-cause; the remaining unknowns are cosmetic (exact copy, `firstRun` gating — see §3).

## 3 · Fix approach

**TradesHome gets the calculator's proven pattern: an always-rendered, minimized outlook-and-filters row that opens the full sheet; the utility row's Filters button goes away.** Mobile-only; **no backend, no schema, no analytics events, no flag changes**; no new flag (this restores ruled behavior under existing gates — the render condition is the same predicate family the receipt already uses).

1. **Add the minimized in-page row** inside the existing receipt wrapper (`TradesScreen.tsx:5132-5146`, `outlookReceiptWrapRef`), rendered when `consolidateOn && !outlookReceiptShown` (`outlookReceiptShown` is the receipt's own predicate, `:1047-1053`, so the two can never double-render — same rule as #254). One line, receipt-styled: label **"Outlook & filters"**, value = `team_outlook` (from the screen's existing `prefsQuery`) or **"Not set"**, plus the #315-style details summary the screen already composes where available, plus a **Change** pressable → `setDnaSheetOpen(true)` (the full sheet: outlook chips, Chasing/Shopping, fairness, lanes, League/Trading-with targeting, untouchables, intent — `:4929-4976`). testIDs `trades.outlook-fallback` / `trades.outlook-fallback.change`, mirroring `calc.outlook-fallback`. **Not** gated on `showInlineHome` — it renders for strip, canvas, *and* control (fixes the control cohort's total stranding, §1). **Not** an interrupt slot — the banner (path D) vanished because it was one; this row is persistent chrome, deliberately. Recommend keeping the legacy `!firstRun` gating (first-run chrome is deliberately minimal, `:5315-5318`); build agent may confirm with orchestrator.
2. **Remove the Filters entry from `TradeHomeUtilityRow`** — drop the `onConditions` pass (`TradesScreen.tsx:5070-5077`) and the prop + control (`TradeHomeUtilityRow.tsx:35-49, 72-86`), per #379's ruling. The sheet stays reachable via the new row (a strict improvement: labeled, in-page, shows current state).
3. **"Minimized default" reading:** the row *is* the minimized state; the full sheet is the expanded state. This matches #257's operator-decided architecture (sheet as the single expanded surface) — we restore the missing minimized half rather than re-inventing an inline accordion.

**Alternatives rejected:**
- *Flip `trade.outlook_direction` true* — lights the #175 directional deck-weighting engine change to fix a UI gap; also insufficient (the receipt still hides on a non-directional outlook, `outlookReceiptCovers`).
- *Stop/reweight the `trades_home_inline` experiment* — prod DB write, restores a mode bar that also has no filters entry post-#269, and answers neither #379 nor #394.
- *Inline-expand the full controls in the page* (true accordion) — requires extracting `TradeDnaSheet`'s Modal body into a shared component; contradicts #257; and Wave B0 (D-158) will re-lay this whole region shortly.
- *Build Wave B0 now* — the real long-term answer (the guided tab becomes the merged In-league page, which carries `InLeagueCalculator`'s own receipt+fallback at `:713-744` and #333's dropdowns), but it is an M-sized layout merge owned by `docs/plans/onboarding-tour-merge/plan.md` §3b, not a fast-track bug fix.

**Coherence with standing decisions:** contradicts nothing in D-151/D-152/D-153/D-157/D-158/D-159. When Wave B0 lands, this row dies naturally with the region it sits in, replaced by the identical pattern inside `InLeagueCalculator` — the interim fix and the target state agree.

## 4 · #333 verification — League/Team side-by-side drop-downs under the fold

**Delivered on the merged calculator page** (`calc.merged_layout` lit): `InLeagueCalculator.tsx:784-818` — `calc.league-dropdown` + `calc.team-dropdown` in a side-by-side `dropdownRow`, placed *beneath* the outlook section per the comment at `:784-785` ("beneath the collapsible outlook section rather than above it"). On TradesHome, the analogous League / "Trading with" pills exist for the experiment cohort (`TradingWithStrip`, `TradesScreen.tsx:5182-5189`, below the receipt slot per #314). **Recommend EXCLUDE — no work in this fix.** Full TradesHome parity (real dropdowns, not pills) arrives with Wave B0, which mounts `InLeagueCalculator` inline.

## 5 · File ownership (build agent)

| File | Change |
|---|---|
| `mobile/src/screens/TradesScreen.tsx` | New fallback row in the receipt wrapper (`~:5132-5146`); remove `onConditions` pass (`~:5070-5077`); styles |
| `mobile/src/components/TradeHomeUtilityRow.tsx` | Remove `onConditions` prop + Filters control |
| `mobile/tests/check-finder-conditions-reachable.js` | Rewrite (see §6) |
| `mobile/tests/check-trades-banner-region.js` | Extend if it pins the receipt/strip region order (verify before editing) |
| `mobile/src/components/CLAUDE.md`, `mobile/src/screens/CLAUDE.md` | Row descriptions for `TradeHomeUtilityRow` / `TradesScreen` |
| `docs/feedback/items/376-finder-filters-regression/` | status.md, testflight-checklist.md |
| `living-memory/` | CHANGELOG, TEST_LEDGER, NEXT (#394/#379/#376 rows) |

**Group B overlap — must be serialized on `TradesScreen.tsx`.** Group B (tour step placement, AnalystGuide) also edits `TradesScreen.tsx` (e.g. n22 retarget near `:5433`, guide targets/scroller). Ownership split: Group A owns the receipt-wrapper block + utility-row wiring; Group B owns guide/beat code — but the *file* is shared, so the orchestrator should run them serially or rebase one on the other. Side effect worth telling Group B: N2 form A spotlights `outlookReceiptWrapRef` (`:5135`), which today measures an empty wrapper; once the fallback row renders inside it, N2's ring gains a real frame — an improvement, but Group B should know the frame changes. `TradeHomeUtilityRow.tsx` and the two guards are Group A–exclusive.

## 6 · Evidence plan (D-056 — no Maestro, no simulator)

**Structural guard — rewrite `mobile/tests/check-finder-conditions-reachable.js`** (keep the filename; its invariant broadens from "reachable" to "reachable *in the ruled place*"). Assertions, each provably red under a named sabotage:

1. `trades.outlook-fallback` exists in `TradesScreen.tsx` with a `trades.outlook-fallback.change` control. *Sabotage: delete the row.*
2. Its render condition references `consolidateOn` and `outlookReceiptShown`, and the row is **not** inside the `!consolidateOn` legacy branch (positional check between the `:5330` branch markers). *Sabotage: move it into the legacy Controls Card.*
3. Its condition does **not** read `outlookDirectionOn` / `useFlag('trade.outlook_direction')` — flag-independence is the whole fix. *Sabotage: add the flag to the gate.*
4. Its condition does **not** reference `showInlineHome` (all three variants get it). *Sabotage: add `showInlineHome &&`.*
5. The change control is wired to `setDnaSheetOpen(true)`, not `setOutlookOpen`. *Sabotage: swap the setter.*
6. `TradeHomeUtilityRow.tsx` no longer contains `trades.home-utility.conditions` (#379 — absence is now the invariant). *Sabotage: re-add the button.*
7. Keep the existing #269 assertion: `hideTeamAndPlayer={sheetTargetingOn && consolidateOn}` intact. *Sabotage: drop the guard.*

**Code-walk proof:** a flag×variant truth table (strip / canvas / control × outlook declared / not) tracing the render tree to show exactly one outlook surface renders in every cell — receipt, fallback row, or banner — and the sheet is reachable from each.

**Operator TestFlight checklist:**
1. Acquire tab (TradesHome): below the icon utility row, an **"Outlook & filters"** line shows your current outlook (e.g. "Contender") — not blank, not "Not set" if you've set one.
2. Tap **Change** → the full sheet opens: outlook chips, Shopping/Chasing positions, trade-idea lane, fairness toggle, League + Trading-with, untouchables, intent chips.
3. The icon row no longer shows a "Filters" button; Draft / Free agents / Manual calc still navigate.
4. Change any preference, close the sheet → "Preferences changed — tap to refresh" strip appears; tap it → deck regenerates.
5. (Second account / fresh outlook) With no outlook set, the line reads "Not set" and Change opens the same sheet.

**Gates before merge:** `pytest backend/tests` (unchanged — no backend), `npx tsc --noEmit`, `bash mobile/scripts/testid-lint.sh` (two new testIDs follow the existing `trades.*` grammar), all `mobile/tests/check-*.js`, ledger entry in `TEST_LEDGER.md`.

## 7 · Risks & invariants

- **Why the existing guard stayed green:** `check-finder-conditions-reachable.js` pins #376's *literal* complaint — a conditions entry exists on the stand-in row and opens the full sheet (assertions 1–4) — and that is still true. It never encoded #379's later ruling (in-page, minimized) or #394's real ask (a *labeled outlook* surface). Lesson for the rewrite: pin the ruling, not the report's wording. The new assertion 6 inverts the old assertions 1–3, so the rewrite must land in the same commit as the code change or CI goes red.
- **`docs/cross-client-invariants.md`:** nothing touched. Outlook mode enums ("Team outlook modes") are read, not extended; no tier/position hexes; no new cross-client enum. The row uses ink/chalk tokens only, ≥13pt bodySm (Chalkline 11pt floor), radius ≤8, no new accents.
- **Double-surface risk if `trade.outlook_direction` ever flips true:** prevented by construction — the row's gate is the receipt's own `outlookReceiptShown` complement (#254's rule: "the two can never both appear and can never both vanish").
- **Interrupt arbiter:** the row deliberately does *not* claim a `useInterruptSlot` — path D died precisely because it was slot-claimed and condition-gated. Persistent chrome is the point.
- **#380 rider** (partner tap minimizes section) is folded into #384/Wave B0 — out of scope here; nothing in this fix blocks it.
- **#360/#361 (report only):** "positions we're NOT looking for" — the natural home **is** the surface this fix makes discoverable: `TradeDnaSheet`'s Chasing/Shopping block (`dna.chase.*`/`dna.shop.*`, `TradeDnaSheet.tsx:~636`). Building it needs a third chip group + a new `league_preferences` field + a generate-side filter — a backend/API change, bright-line per the feature gates, so it must be its own item; do not fold into this fast-track fix.
- **Rollout:** no flag, ships with the next client build. Revert = revert the commit (self-contained, two source files + guards).
