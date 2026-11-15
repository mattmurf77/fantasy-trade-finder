# Fairness formula — replay result (2026-11-15)

Aggregates only: no league, roster, transaction or owner ids; every cell rests on at least 20 trades and 10 lineages. The arms, the measures and the rule were fixed in [spec.md](spec.md) § Technical design (commit 4510528d) before any real-data run.

**Verdict: no arm passed. The knobs stay at today's math, and `trade.fairness_formula_v2` ships off with no behaviour change available.** No arm moved the primary measure up: the best change was arm C at exactly +0.0 points (it built the same first 30 cards as today for every trade). Arm B was significantly worse (−1.4 points).

## Sample

- Research dataset `analysis.sqlite`, split `train`, folds 0–2, in-season, unflagged, M2 population rule. 14,947 eligible trades.
- 1,200 drawn (seed 20261115). All 1,200 replayed, none skipped. 729 league lineages. 954 trades move at least one pick (626 lineages); 246 do not (218 lineages).
- Each trade's deck was built under all five arms in the same process with `trade_gen_bilateral_r4.generate_bilateral_trades` through `backend/eval/fairness_formula_replay.py` (sockets blocked, scratch database, shipped model_config defaults), at a requested threshold of 0.75.
- Matches are scored on the case's own values for every arm (the fairness-window scale), so no arm can win by changing how matches are counted.

## Table

Intervals are 95% percentile bootstraps over whole lineages (2,000 draws, seed 20261115). "Gain" is paired per trade against T, in percentage points.

| Arm | Close match in first 30 (primary) | Gain vs T | Close match anywhere | Exact match in first 30 | First-30 cards under 0.75 on today's math | Median deck size | Median build s | Median time ratio vs T | First 30 identical to T |
|---|---|---|---|---|---|---|---|---|---|
| T (today) | 5.3% [4.1, 6.6] | — | 41.8% [39.1, 44.6] | 0.8% [0.3, 1.3] | 0.0% | 2,436 | 3.18 | 1.00 | 1,200 of 1,200 |
| A Σv^0.7, 0.75 | 5.0% [3.8, 6.3] | −0.3 [−1.2, +0.5] | 38.8% [36.1, 41.5] | 0.9% [0.4, 1.5] | 0.0% | 1,846 | 2.90 | 0.91 | 30 |
| B Σv^0.7, 0.8176 | 3.9% [2.8, 5.1] | −1.4 [−2.6, −0.3] | 32.5% [29.9, 35.1] | 0.9% [0.4, 1.5] | 0.0% | 1,203 | 2.25 | 0.71 | 8 |
| C Σv, 0.75 | 5.3% [4.1, 6.6] | +0.0 [+0.0, +0.0] | 42.5% [39.7, 45.2] | 0.8% [0.3, 1.3] | 0.0% | 2,343 | 3.28 | 1.03 | 1,200 |
| D Σraw^0.7, 0.75 | 5.1% [3.9, 6.4] | −0.2 [−1.1, +0.7] | 35.0% [32.4, 37.6] | 0.8% [0.3, 1.3] | 0.0% | 1,905 | 2.97 | 0.94 | 54 |

Primary measure split by whether the real trade moves a pick:

| Arm | Pick trades (954): close in first 30 | Gain vs T | No-pick trades (246): close in first 30 | Gain vs T |
|---|---|---|---|---|
| T | 6.0% [4.5, 7.5] | — | 2.9% [0.8, 5.0] | — |
| A | 5.8% [4.2, 7.3] | −0.2 [−1.2, +0.8] | 2.0% [0.4, 3.9] | −0.8 [−2.1, +0.0] |
| B | 4.6% [3.2, 6.0] | −1.4 [−2.7, +0.0] | 1.2% [0.0, 2.8] | −1.6 [−3.6, +0.4] |
| C | 6.0% [4.5, 7.5] | +0.0 [+0.0, +0.0] | 2.9% [0.8, 5.0] | +0.0 [+0.0, +0.0] |
| D | 5.6% [4.1, 6.9] | −0.4 [−1.5, +0.7] | 3.2% [1.2, 5.6] | +0.4 [−0.8, +2.0] |

## The rule applied

- To pass, an arm needs (1) a gain interval above zero, (2) a median time ratio of at most 1.10, and (3) a pick-trade gain whose interval is not entirely below zero.
- No arm meets (1). A, C and D have intervals around zero; B's interval is entirely below zero. All arms pass (2) (A, B and D build faster because their decks are smaller). B's pick-trade interval touches zero, so (3) alone would not have excluded it.
- So no arm is recorded as the configured formula. The knobs stay at their defaults (today's math).

## What to read into it (exploratory, not pre-registered)

- **The first page does not move because the order does not use the ratio.** The r4 generator orders admitted cards by both managers' support scores, and those read today's package values (out of scope here). Changing the admission formula mostly changes which cards sit at the back of the deck: C (no package discount) built the identical first 30 cards for all 1,200 trades, and no arm put a single first-30 card under 0.75 on today's math.
- **The compressed formulas shrink the deck.** Σv^0.7 makes a lopsided pair look closer, but in this generator it removes more cards than it adds (deck size −24% for A, −51% for B) and lowers "close match anywhere" (41.8% → 38.8% for A, 32.5% for B, 35.0% for D). So the research gain in telling real trades from made-up ones does not carry into a better deck through the admission gate alone.
- **Pick trades did not suffer** under A, C or D (intervals around zero); B lost them along with everything else.
- T's primary measure here (5.3%) is lower than the fairness-window replay's 0.75 row (7.3%) on a different draw of the same population (600 trades, seed 20261114); both intervals overlap.

## Limits

Carried over from the fairness-window replay: approximate pick inventories (generic picks from counts, at most 6 per team); only organic 1-for-1, 1-for-2 and 2-for-1 cards; the r4 generator's emitted order, not the production-served deck (no ranker, presentment, deck-quality filters or first-page store); consensus boards only; dated DynastyProcess values, not the app's live KeepTradeCut blend (so "v" here is DynastyProcess-only, age preference included; no TE-premium league). Build times were measured with two processes on a shared machine; the ratio is paired per trade in the same process.

## Confirmation command (held-back trades; the main session runs it once)

Not run by the builder, and not needed while no arm passes. If a later change makes an arm pass, the main session runs, from the project root:

```sh
PY=<venv python> sh data/sleeper-universe/analysis/fairness-formula/confirm.sh <path-to-db> <out-dir>
```

It extracts every in-season unflagged trade in that file under the same population rule (1,200 drawn, seed 20261115; `extract_cases.py <db> <out> --confirm`), replays all five arms in two processes, and writes `<out-dir>/table.json` with the same table and the rule's selection. The scripts are local research code under `data/sleeper-universe/analysis/fairness-formula/` (git-ignored); the replay itself is the committed `backend/eval/fairness_formula_replay.py`.
