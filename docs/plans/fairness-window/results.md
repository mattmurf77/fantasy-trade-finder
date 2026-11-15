# Fairness window — replay result (2026-11-14)

Aggregates only: no league, roster, transaction or owner ids. The rule, the sample and the measures were fixed in [spec.md](spec.md) § Technical design before any result was seen.

**Verdict: no candidate passed. The configured value stays 0.75, and `trade.fairness_window_v2` ships off with no behaviour change available.** The best candidate (0.65) gained +0.5 points on the primary measure, with an interval that includes zero, and it built decks 21% slower (the limit is 10%).

## Sample

- Research dataset `analysis.sqlite`, split `train`, folds 0–2, in-season, unflagged, M2 population rule. 14,947 eligible trades.
- 600 drawn (seed 20261114). All 600 replayed, none skipped. 458 league lineages.
- Each trade's deck was built at all five thresholds in the same process, with `trade_gen_bilateral_r4.generate_bilateral_trades` run offline through `backend/eval/fairness_window_replay.py` (sockets blocked, scratch database, shipped model_config defaults).

## Table

Intervals are 95% percentile bootstraps over whole lineages (2,000 draws). "Gain" is paired per trade against 0.75.

| Threshold | Close match in first 30 (primary) | Gain vs 0.75 | Close match anywhere | Exact match in first 30 | First-30 cards under 0.75 | Median build s | Median time ratio vs 0.75 | Median deck size |
|---|---|---|---|---|---|---|---|---|
| 0.75 | 7.3% [5.1, 9.6] | — | 42.0% [38.1, 46.2] | 0.5% [0.0, 1.1] | 0.0% | 3.94 | 1.00 | 2,466 |
| 0.70 | 7.2% [5.0, 9.4] | −0.2 pts [−0.7, +0.3] | 43.8% [39.9, 48.2] | 0.7% [0.2, 1.3] | 0.0% | 4.40 | 1.12 | 2,864 |
| 0.65 | 7.8% [5.6, 10.2] | +0.5 pts [−0.5, +1.5] | 44.8% [40.9, 49.1] | 0.8% [0.2, 1.6] | 0.0% | 4.78 | 1.21 | 3,161 |
| 0.60 | 7.8% [5.6, 10.2] | +0.5 pts [−0.5, +1.5] | 44.8% [40.9, 49.1] | 0.8% [0.2, 1.6] | 0.0% | 4.75 | 1.21 | 3,161 |
| 0.55 | 7.8% [5.6, 10.2] | +0.5 pts [−0.5, +1.5] | 44.8% [40.9, 49.1] | 0.8% [0.2, 1.6] | 0.0% | 4.74 | 1.20 | 3,161 |

## The rule applied

- To pass, a candidate needs a gain interval above zero **and** a median time ratio of at most 1.10.
- No candidate's gain interval excludes zero. 0.65, 0.60 and 0.55 also fail the time check (1.20–1.21), and 0.70 fails it too (1.12).
- So 0.75 is kept.

## What to read into it

- **0.60 and 0.55 are the 0.65 deck.** For all 600 trades they gave identical first-30 cards and identical deck sizes. The engine clamps every request to `market_floor_absolute` (0.65, "the one non-negotiable floor"). Opening the window below 0.65 would mean changing that policy floor, which this change does not do.
- **A wider window adds cards at the back, not the front.** The deck grows by about 28% at 0.65, and a close match *anywhere* in the deck rises by 2.8 points. That is exploratory: it was not the pre-registered measure, and its interval was not computed as a paired gain. None of the first 30 cards was under 0.75 at any threshold, because the generator's own order puts the most even offers first.
- So widening, by itself, does not put the trades managers actually make in front of them. Reordering is out of scope here.

## Limits carried over from the research prototype

- Approximate pick inventories (generic picks from counts, at most 6 per team).
- Only organic 1-for-1, 1-for-2 and 2-for-1 cards.
- The deck is the r4 generator's emitted order, not the production-served deck: no ranker, presentment, deck-quality filters or first-page store.
- Consensus boards only: no personal boards. Dated DynastyProcess values, not the app's live blend.
- Build times were measured on a shared machine, four processes at once. The ratio is paired per trade in the same process, which removes most of that noise.
