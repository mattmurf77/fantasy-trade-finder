# FB-417 — the pushed deck's second search replaces the anchored one

**Status:** in_progress — **QA A + QA B both PASS; QA round-1 resolution applied** ·
2026-09-03 · `feat/fb417-pushed-deck-research`, resolution on
`claude/new-user-feedback-06dabd`

- **Path:** fast-track bug (single-surface defect, proven from the prod event stream).
- **Covers feedback IDs:** 417 — filed by the operator on 2026-09-02 against v1.16.14,
  screen `TradeDeck`. No satellites; this folder is canonical.
- **Docs:** [investigation.md](investigation.md) (event timeline + mechanism) ·
  [prd.md](prd.md) (R-1…R-5, code-walk, TestFlight checklist) ·
  [scope.md](scope.md) (feature-gate block) · [build-notes.md](build-notes.md)
  (post-change lines, sabotage tables, command results; §5 is the QA round-1 resolution) ·
  [qa-A.md](qa-A.md) (mechanical re-proof — PASS) · [qa-B.md](qa-B.md) (product/behavior
  walk — PASS).
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

## QA round 1 — both agents PASS, non-blocking findings resolved (2026-09-03)

Neither agent found a blocking defect. The six non-blocking findings that touched behavior or
honesty were resolved in the session tree (details: [build-notes.md](build-notes.md) §5,
[prd.md](prd.md) R-1/R-3/R-6):

- **B-5 + B-1 — the page no longer invites a tap it cannot honor.** The CTA is hidden for the
  *whole* anchored lifecycle (`fairDeck || fairSweepPending`), the sweep's second is narrated by
  the existing "Looking for trades…" card instead of the never-searched card, and the deck-done
  copy names the control that actually renders (the receipt's Clear, or this card's own
  "Search all trades" when there is no receipt).
- **B-2 — no stranded disabled button.** The QuickSet-regen focus effect's inline epoch bump now
  disarms `fairSweepPending` too; the invariant is "every epoch bump disarms", and both sites do.
- **B-3 (new R-6) — a failed anchored search retries the *anchored* search** on the pushed page,
  not the unanchored model job.
- **qa-A F-1 / F-2 — guard gaps closed.** Both of qa-A's own "plausible wrong implementation"
  sabotages (an extra unconditional reset; arming the sweep above the `leagueId` early return)
  now go red.
- **qa-A F-3 — stale census comments corrected** (`dispatchGenerate` census table, the `deckMode`
  emitter comment, and `check-offer-prefill-330.js`'s "8-site census" prose).

`check-results-push.js` § 8 is now 23 assertions / 28 printed lines; the five new and two changed
ones were each proven red by a named sabotage (S18–S24) and restored. Gates re-run green:
`tsc --noEmit`, `npm run test:results-push` (75 ✓), all 32 `TradesScreen` suites, `testid-lint`.

Still open and disclosed, not fixed: **B-4** (discoverability of "search everything" dropped from
a full-width primary to the receipt's text link — deliberate, watch `deck_search_all_tapped`),
**B-6** (landing double-tap under the push posture still pushes two decks — PRD §5, not #417),
**qa-A F-4/F-5** (two weak-but-honest pins), **qa-A F-6** (a null-`anchorLabel` push has no
mid-deck search control — now named in R-1's table).

## Where it stands

Built, typechecked and guarded on `feat/fb417-pushed-deck-research`; QA'd twice (both PASS) and
the round-1 findings resolved in the session tree `claude/new-user-feedback-06dabd`.
**Not committed, not pushed, not merged.** Remaining: commit + merge to `main` per the normal
gate, the operator's TestFlight checklist ([prd.md](prd.md) §7.3, now the 15-step qa-B list),
and a `living-memory/TEST_LEDGER.md` + `CHANGELOG.md` entry on ship.
