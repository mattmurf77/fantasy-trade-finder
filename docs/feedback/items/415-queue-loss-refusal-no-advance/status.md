# FB-415 — "this trade would be a loss for Bcork", then no advance

**Status:** fixed (verify on v1.16.14) · 2026-09-02 triage · closed by work shipped outside this pipeline

- **Reporter:** mattmurf77, 2026-08-31T20:26Z, app v1.16.13 (EAS build 142), screen `TradesHome`
- **Report:** accepting (✓) a suggested trade shows *"this trade would be a loss for Bcork"* and the deck does not advance to the next suggestion.
- **Batch:** 2026-09-02 weekly run — plan in [413-sleeper-send-draft-picks/plan.md](../413-sleeper-send-draft-picks/plan.md).

## Verdict — already shipped, by the operator's own rulings the same day

Two ships between the report and this triage cover both halves:

| Half of the report | Cause | Fix | Live since |
|---|---|---|---|
| The refusal toast | `POST /api/trades/queue` returned `fails_fairness_floor`, rendered by `mobile/src/utils/queueCalcTrade.ts:47` (`…'s board reads this as a loss for them, so it won't surface.`) | [D-170](../../../../living-memory/DECISIONS.md) — `_calc_queue_mirror_reason` deleted; every well-formed ✓ records (PR #256, `1531a91d`) | Render, 2026-08-31T21:29Z — **63 min after the report**, server-only, every fielded build |
| No advance after ✓ | v1.16.13 rendered results inside the canvas (`calc.canvas_results` browse); the ✓ there queues a hand-built package and has no deck to advance | [D-171](../../../../living-memory/DECISIONS.md) — Find a Trade pushes the classic `TradeDeck`; ✓ is the classic like + advance (PR #259, `046fa378`) | v1.16.14, EAS build 143 (finished 2026-08-31 20:29 local), flags `calc.results_push: true` / `calc.canvas_results: false` |

Three agreeing signals per the 2026-08-27 triage lesson: CHANGELOG 2026-08-31 + 2026-08-31b entries, the flag values in `config/features.json`, and the code on `origin/main` @ `ce3f443c`.

## Code-walk (current `origin/main`)

- `mobile/src/screens/TradesScreen.tsx:5794` `resultsPushLive = resultsPushOn && canvasHost === 'flag'`; `:5800` `landingDeckRetired` — the landing no longer hosts a deck.
- `:2968-2985` Find a Trade pushes `resultsPush` payload; `:837-846` the pushed instance reads it (`isResultsPushed`).
- `:8248-8260` the pushed instance renders `SwipableTopCard` with `onLike={() => advance('like')}` — the classic like path, which advances `deckIdx` (`advance` at `:5300`).
- Server: `backend/server.py` queue route no longer emits `fails_fairness_floor` (D-170; `CALC_QUEUE_REASONS` keeps the enum value, vestigial). Tests: `backend/tests/test_calc_trade_queue.py` (38 tests, incl. "the old `fails_fairness_floor` package queues AND surfaces").

## Operator verification (runtime, D-056)

Run [docs/plans/finder-results-push/scope.md §7](../../../plans/finder-results-push/scope.md) on v1.16.14 — **step 5** (✓ like → success toast, deck advances) is this item's proof. Any recurrence of the "loss for" toast on ≥ v1.16.14 is a new report.
