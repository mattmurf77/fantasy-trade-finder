# #214 Stud-Tax Tuning Proposal (NOT applied — operator decision)

**Verdict being addressed** (results.md, confirmed): FTF's consolidation adjustments are heavier than the market consensus on 6/6 matrix trades, by +34.8pp to +68.4pp against a +10pp bar. Direction is 100% one-sided; this is a magnitude problem, not a sign problem — T2 proved the market itself applies a real stud premium (−20% to −32% skew), so the tax should be *reduced and reshaped*, not removed.

## Three mechanical changes (from results.md root causes)

### 1. Phase the crown premium out as the naive gap widens (KTC's shape)
Today `crown_rate=0.12` applies at full strength regardless of how lopsided the trade already is naively — on T3 (already +66% package-favoring naive) we still add the full 12% to the stud. KTC visibly phases its adjustment to zero as the raw gap grows.
**Change:** scale the crown bonus by `max(0, 1 − |naive_skew| / skew_phaseout)` with `skew_phaseout ≈ 0.5` (new `model_config` key). Full premium on near-even trades, zero once the trade is already half-again lopsided.

### 2. Elite credit for both sides (DynastyDealer's shape)
Today the crown bonus only triggers on the outnumbered side (`package_value_v2`: `len(values) < n_other`), so Gibbs+Achane earn nothing for both being individually elite while Bijan collects +12%. DynastyDealer awards an independent per-side stud bonus per qualifying elite piece.
**Change:** award the crown scaling per elite asset (value ≥ `crown_elite_value`) on either side, independent of piece count; keep the *rate* per piece lower (see 4) so two elites ≠ 2× a single crown.

### 3. Depth discount measured against the package's own best asset
Today `package_adj_gamma`'s discount benchmarks each package piece against the whole trade's best asset, producing −56% to −62% effective discounts on T2 vs DynastyDealer's observed −22% to −38% ceiling.
**Change:** benchmark within the package (its own best asset), and cap the total package discount at `package_discount_cap ≈ 0.35` (new key).

## 4. Constant re-tune (after the shape fixes)
With the shapes fixed, re-fit `crown_rate` (start ~0.08/elite piece) and gamma so the matrix replay lands within **±15pp of the competitor median on ≥4/6 trades** — the acceptance gate. Constants live in `model_config` per docs/config-reference.md conventions; no hardcoding.

## Validation gate (before any ship)
1. Replay T1–T6 (both formats) via the feedback-workspace/214/run_matrix.py harness; acceptance as above, with T1 specifically required to move to "package favored" in SF (market: +56.6%).
2. Full backend test suite green; engine tests that pin current adjustment values updated deliberately, not loosened.
3. Deck sanity replay: generate decks for the operator's league before/after and diff — the change must not flood decks with stud-for-package offers (the fairness gates still bind).

## Ship vehicle
Options, not mutually exclusive:
- **Constants-only retune behind a `model_config` version** — invisible, reversible, no flag.
- **#215's requested toggle** ("stud tax: market / conservative") — ship the retuned curve as "market" and today's as "conservative"; DynastyProcess's user-tunable slider is prior art. This turns a modeling risk into a user preference and closes #215 in the same change.

Recommendation: do both — retune as the default, expose the old behavior via the #215 toggle for a season as the escape hatch.
