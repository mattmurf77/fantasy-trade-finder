# FB-417 — the pushed deck's second search replaces the anchored one

**Status:** in_progress · 2026-09-03 · `feat/fb417-pushed-deck-research`

- **Path:** fast-track bug (single-surface defect, proven from the prod event stream).
- **Covers feedback IDs:** 417 — filed by the operator on 2026-09-02 against v1.16.14,
  screen `TradeDeck`. No satellites; this folder is canonical.
- **Docs:** [investigation.md](investigation.md) (event timeline + mechanism) ·
  [prd.md](prd.md) (R-1…R-5, code-walk, TestFlight checklist) ·
  [scope.md](scope.md) (feature-gate block) · [build-notes.md](build-notes.md)
  (post-change lines, sabotage table, command results).
- **Surface:** mobile only — `mobile/src/screens/TradesScreen.tsx`. No backend, no schema,
  no API, **no new flag** (`calc.results_push` remains the kill switch).

## The report

> *"Starting a trade offer with a player selected worked for the first offer and didn't
> include him for subsequent offers."*

Clarified 2026-09-03: a decision was made on the first card; the second card presented did
not include the selected player.

## What was wrong (one line)

On the pushed anchored deck the page still rendered the unanchored "Find a Trade" primary; a
tap ~1 s after the push dispatched the model job, whose cards appended to the fair deck and —
fairness off — sorted above it, so the top card stopped being about the anchored player while
the "Built around <name>" receipt still said it was.

## What changed

- The primary `trades.find-btn` does not render while `isResultsPushed && fairDeck` (both arms,
  one shared derivation). The receipt's Change/Clear and the end-of-deck exits are that page's
  search controls.
- `handleFindTrades` resets the deck when the current deck is a fair deck, before dispatching —
  so anchored and model cards can never share a deck, and the receipt cannot outlive it. The
  legacy CTA arm now routes through it, so the two arms cannot drift.
- The jobless fair sweep tracks `fairSweepPending` and both CTA arms plus the landing canvas
  cell read it, closing the double-tap window the sweep left open.

## Where it stands

Built, typechecked, and guarded on `feat/fb417-pushed-deck-research` in a scratch worktree.
**Not pushed, not merged** — the building session was scoped to the branch. Remaining:
merge to `main` per the normal gate, the operator's TestFlight checklist ([prd.md](prd.md) §7.3),
and a `living-memory/TEST_LEDGER.md` + `CHANGELOG.md` entry on ship.
