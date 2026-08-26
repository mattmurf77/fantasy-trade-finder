# Status — #374 partners copy + #376 finder conditions

**Status:** `built` — on `fix/finder-conditions-and-partners-copy`, awaiting merge + a client release.
**Date:** 2026-08-20 · **Covered:** #374, #376

---

## #376 — the filters were not removed by an update

**The report's premise is wrong, and that matters for the fix.** Verified:

- Between build **123** (`a76498e`, what the operator used this morning) and build **124** (`bc43b6f`, "the latest update"), **only four files changed** — `teamReview.ts`, `TeamReviewEntryCard.tsx`, `TeamReviewScreen.tsx`, `TrendsScreen.tsx`. Neither `TradesScreen.tsx` nor `TradeFinderModeBar.tsx` was touched.
- Prod feature flags were diffed against `config/features.json` on `main`: **zero drift across all 178 flags.**

**The actual cause is an experiment.** `trades_home_inline` (prod `experiments` table) is `status=running`, `unit_type=account`, targeting `{"is_tester_allowlist": true}`, with variant weights **control 0 bp / strip 10000 bp / canvas 0 bp**, started **2026-08-09**. The operator is on the allowlist, so he is 100% assigned `strip`.

`TradesScreen.tsx:4732` — when `showInlineHome` is true, `TradeHomeUtilityRow` **replaces** `TradeFinderModeBar`. That row shipped with Draft / Free agents / Manual calc / Today and **no conditions entry**, so for the enrolled cohort the finder's filters survived only behind `OutlookBiasReceipt`'s "Change" link (`TradesScreen.tsx:4802`) — present, but nowhere a user looks for a filter. Compounded by `#269`, which had already moved Team/Player targeting off the mode bar into that same sheet.

**The component's own source had already stated the rule it broke.** The `onTodaysTrade` prop comment says: *"This row REPLACES TradeFinderModeBar for users in the `trades_home_inline` experiment, so the entry point has to exist here too — otherwise those users could never reach the surface under test."* That reasoning was applied to Today's Trade and not to the filters.

### Fix

`onConditions?: () => void` on `TradeHomeUtilityRow`, rendering a **Filters** button (`settings` glyph) that **leads the row** — burying it would repeat the discoverability failure that produced the report. `TradesScreen` wires it to `setDnaSheetOpen(true)`, gated on `consolidateOn` for the same reason `hideTeamAndPlayer` is: that flag is what makes the *full* sheet (fairness, lanes, targeting) exist, so passing the handler without it would open a DNA-only sheet and quietly not be "the filters".

New guard `mobile/tests/check-finder-conditions-reachable.js` — 5 assertions, **7 sabotages each proven red on its named assertion**. It pins the invariant the prose had stated and nobody had encoded: *an experiment that swaps one component for another must not silently drop an affordance the first one carried.*

### Still the operator's call

The fix restores the entry point but **does not end the experiment**. `trades_home_inline` is at 100% `strip` with `control` at 0 bp, so nobody is getting the mode bar. Stopping it (or reweighting to control) is a **prod DB write** and was not done unilaterally. That is the one-step revert if the mode bar is wanted back as-is.

## #374 — "Still unclear what 'pointed the other way' means"

Fair: the beat used the phrase three times and never defined it, requiring the user to hold their own window in their head and infer the complement.

Now stated in the user's own terms, read from `data.window.declared ?? data.window.inferred`: a contender sees *"Rebuilding teams — they want picks, you want players"*; a rebuilder sees the mirror; an undecided user gets the neutral form. A fine-print line names the mechanism (each side gives up what it values less) and says what tapping does.

Copy only — no payload, flag, or logic change.

## Gates

`pytest` **3723 passed, 1 skipped** · `tsc --noEmit` clean · **67** `check-*.js` suites, 0 failed · testid-lint OK.

**TestFlight checklist is UNRUN** — both changes are client-side and need a build.
