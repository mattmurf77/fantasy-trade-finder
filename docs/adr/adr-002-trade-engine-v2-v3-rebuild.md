# ADR-002 — Trade Engine v2/v3 Rebuild

**Status:** Accepted  
**Date:** 2026-06-09  
**Initiative:** Trade engine Tiers 1–3 (docs/plans/trade-engine-tier1-fixes.md, -tier2-models.md, -tier3-rebuild.md; research in docs/reviews/trade-engine-external-research.md)

---

## Context

The legacy trade engine scored candidates across three incommensurable scales (user Elo gaps, consensus `search_rank`-decay values, fixed package weights), checked "mutual gain" in raw Elo space, fabricated Elo ratings for opponents who had never ranked players, and patched symptoms with stacked post-hoc multipliers and taxes (outlook multiplier, positional preference multiplier, QB/star/clogger taxes). A deep-dive review (docs/reviews/trade-engine-deep-dive.md) plus verified external research (docs/reviews/trade-engine-external-research.md — KTC, FantasyCalc, reciprocal recommenders, kidney exchange) motivated a ground-up rebuild.

Data reality at decision time (research doc §6): 3 users (1 real), **20 trade decisions**, 4 matches. Anything "learned" had no training data.

## Decision

Rebuild in flag-gated tiers, all sharing one design:

1. **Single value space.** All v2 math runs in dynasty-value units via `elo_to_value(elo) = base·exp(k·(elo−ref))`; personal Elos are confidence-shrunk toward consensus first. Packages valued KTC-style per side (`package_value_v2`, single-term simplification of KTC's raw adjustment), with a `waiver_slot_cost` on the side receiving more players.
2. **Two-sided surplus gate + harmonic ranking.** A trade surfaces only when BOTH sides' surpluses (in their own valuations) clear `min_side_surplus`; candidates rank by the harmonic mean of the two surpluses (research amendment A1), blended with range-overlap consensus fairness (A4). Opponents without real rankings get labeled consensus-basis cards instead of fabricated-Elo divergence math.
3. **Roster- and stance-aware valuation as inputs, not multipliers** (Tier 2): marginal over-replacement value, and outlook as a now/future age-curve blend — the deleted `team_outlook_multiplier` / `positional_preference_multiplier` are replaced by an input-side blend and a hard positional filter.
4. **Thompson sampling instead of a learned acceptance model.** With ~20 labels, a trained ranker is unjustifiable; per-shape Beta(1+likes, 2+passes) deck ordering (A5) works at n≈0, bounds quality inversion to a (0.5, 1.5) multiplier, and *generates* the exploration data a future model needs. Impressions are logged (`trade_impressions`) as the implicit-negative training stream.
5. **Tier 3: pure-Python exact optimizer (`backend/trade_optimizer.py`), not OR-Tools.** The plan's preferred Approach A was an OR-Tools ILP, but at this scale (~12-asset candidate pools per side, `v3_pool_size`) exhaustive/DP search in pure Python is milliseconds-fast and avoids a native dependency on the Render deploy. Includes a sweetener pass for near-miss-fair trades and 3-team cycle clearing (kidney-exchange style, length ≤ 3) behind `trade.three_team`.
6. **Calibration to the legacy `dynasty_value(search_rank)` curve deliberately abandoned.** The Tier 1 plan required Spearman ≥ 0.98 between `elo_to_value(seed_elo)` and `dynasty_value(player)` (`backend/scripts/calibrate_elo_value.py`). Sleeper's `search_rank` is a **search-relevance proxy** — popularity ordering for an autocomplete box, not a market value — while seed Elo derives from DynastyProcess consensus values (see docs/reviews/trade-engine-external-research.md §1 on DynastyProcess/FantasyCalc as value sources, and the deep-dive's identification of the `search_rank` decay curve as a third, global scale). Where the two disagree, the consensus-value-derived seed is the one to trust, so the v2 value space anchors to seed Elo and the legacy curve is retained only for the flag-off path.

## Alternatives considered

- **Keep patching the legacy scorer** (more taxes/multipliers): rejected — each patch fought the incommensurable-scales root cause; multipliers don't compose with a fairness gate.
- **Bare `min(surplus_a, surplus_b)` ranking:** kept as the *gate* but ranked by harmonic mean — smoother, citable (RECON reciprocal recommender evidence), preserves binding-side logic.
- **Learned acceptance model now (plan item 2.4):** deferred for Thompson sampling — ~20 labels is two orders of magnitude short.
- **OR-Tools CBC ILP for Tier 3:** rejected for a pure-Python exact search — equal results at league scale, no native dependency.
- **FantasyCalc public API as the consensus scale:** deferred (terms unverified, adds a runtime dependency); accepted-trade-fit values (plan 3.5) remain the long-term goal once trade volume exists.

## Consequences

- "Mutual gain" is now real: both sides must profit *in their own valuations*, in one unit system. Clogger trades die at the valuation level (marginal value + waiver-slot cost), not via taxes — the v2 path drops the QB/star/clogger taxes entirely.
- Unranked opponents produce honest, labeled consensus cards (`basis: "consensus"`) instead of noise; clients carry matching copy (see cross-client-invariants.md).
- New permanent data exhaust: `trade_impressions` (every served card with deck position) enables a future acceptance model and powers deck diversification.
- More config surface: ~20 new `model_config` keys (config-reference.md). Note: they currently exist only as code defaults in `trade_service._DEFAULT_CFG` — not yet seeded into the `model_config` table, so the admin API can't tune them yet.
- Deck order is no longer purely deterministic by score (Thompson sampling) — deterministic per job via a seeded RNG, but cross-job comparisons must account for exploration.
- Dual/triple engine paths must be kept green until legacy is retired.

## Rollback

Pure flag flips, no data migration: `trade_engine.v3` off → v2; `trade_engine.v2` off → legacy scorer (kept byte-for-byte unchanged). Tier 2 features (`trade.marginal_value`, `trade.outlook_blend`, `trade.likes_you`, `trade.fuzzy_match`, `trade.thompson_deck`, `trade.deck_diversity`) toggle independently within v2. See runbook.md for the kill-switch order.
