# Merged-view trim — operator ruling 2026-08-28 (evening, post-light)

> Operator, looking at the LIVE merged page (calc.inline_home lit): *"Remove
> the duplicate outlook bar and the fully horizontal find a trade bar. Also
> remove the 1QBPPR and SF TEP filters."* Ships with the v1.16.10 train.
> All three were predicted by the 2026-08-27 parity audit §7 (items 1 and 3).

## T-1 — one outlook bar

Under `calc.inline_home`, BOTH the guided page's minimized "Outlook & filters"
row and the calculator's own outlook row render. `TradesScreen`'s CLAUDE.md
already marks its copy **mortal** under this flag — honor it: suppress the
TradesScreen row when `inlineHomeOn`; the calculator's row (inside the hosted
`InLeagueCalculator`) is the survivor. Flag-off rendering unchanged.

## T-2 — the page-level Find a Trade bar dies on the merged view

The full-width horizontal `trades.find-btn` bar does not render when
`inlineHomeOn` — the canvas's own action row (Find a Trade 50 / Clear 30 /
✓ 20) is the ONLY primary (audit §7 item 3; ice-rationing rule). Verify the
"Find more trades" relabel path and the empty-canvas model-deck path still
have an entry — the canvas Find a Trade covers both (empty canvas ⇒ model
deck per D-153); if any end-of-deck exit referenced the page bar, re-point it
at the canvas row. Flag-off rendering unchanged.

## T-3 — the scoring-format chips leave the merged header

The 1QB PPR / SF TEP format chips (+ the #191 conversion note they drive) do
not render when the calculator is hosted inline (host prop from
`TradeBuildCanvas`, not a flag read inside `InLeagueCalculator` — the pushed
Real-values page keeps its chips). **History, on the record:** #384 W1
dropped these once and W5 restored them after review §11 called the absence
a regression; the operator has now seen the live merged page and ruled the
other way. The scoring-format override's remaining homes: the pushed Real
values page and league settings. Docs touched: the `calc.merged_layout` /
`calc.inline_home` flag comments' chip claims, `components/CLAUDE.md`'s
InLeagueCalculator row, and `check-calc-merged-layout.js` if it pins the
chips in the merged header (re-key to host-aware).

## Evidence

Suite assertions for each (TradesScreen row suppressed under the flag; page
bar absent under the flag; chips host-gated with the pushed page still
pinned); TestFlight checklist gains a merged-view step: one outlook bar, one
Find a Trade, no format chips, chips still present on Real values.
