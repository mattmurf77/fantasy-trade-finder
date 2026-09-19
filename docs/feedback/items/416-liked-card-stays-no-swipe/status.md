# FB-416 — liked card doesn't disappear; swipe is gone

**Status:** fixed (verify on v1.16.14) · 2026-09-02 triage · closed by work shipped outside this pipeline

- **Reporter:** mattmurf77, 2026-08-31T22:22Z, app v1.16.13 (EAS build 142), screen `TradesHome`
- **Report:** *"The validation errors don't fire anymore but the card doesn't disappear when liked. Also the swipe functionality has been lost."*
- **Batch:** 2026-09-02 weekly run — plan in [413-sleeper-send-draft-picks/plan.md](../413-sleeper-send-draft-picks/plan.md).

## Verdict — already shipped by D-171 (v1.16.14)

The report was filed **53 minutes after D-170 went live** (2026-08-31T21:29Z) — "the validation errors don't fire anymore" is the operator observing that ship land on a fielded build. What remained is the v1.16.13 in-canvas results surface itself (`calc.canvas_results`): its ✓ queues the fronted idea but the idea stays on the canvas (no deck to advance), and the canvas pager has no swipe gesture at all. Both are exactly what [D-171](../../../../living-memory/DECISIONS.md) replaced two hours later: Find a Trade now pushes the classic `TradeDeck` page, where a like advances the deck and swipe is the `SwipableTopCard` gesture.

| Signal | Value |
|---|---|
| CHANGELOG | 2026-08-31b — D-171, v1.16.14 |
| Flags (`config/features.json`) | `calc.results_push: true`, `calc.canvas_results: false` |
| Code on `origin/main` @ `ce3f443c` | `mobile/src/screens/TradesScreen.tsx:5794-5800` (landing deck retired under push), `:8248-8260` (pushed deck renders `SwipableTopCard`, `onLike={() => advance('like')}`) |
| Build | EAS build **143** / v1.16.14, finished 2026-08-31 20:29 local, commit `070f1ce1` |

Sibling report: [#415](../415-queue-loss-refusal-no-advance/status.md) (the same surface, filed before D-170 landed).

## Operator verification (runtime, D-056)

[docs/plans/finder-results-push/scope.md §7](../../../plans/finder-results-push/scope.md) on v1.16.14 — **step 1** (classic swipe cards appear on the pushed page) and **step 5** (✓ advances) are this item's proof; step 6 covers ✕. Not fixed for anyone still on v1.16.13 — this half needs the build, unlike #415's server half.
