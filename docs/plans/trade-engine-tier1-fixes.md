# Trade Engine — Tier 1: Fix the Current Engine

*Companion to [`docs/reviews/trade-engine-deep-dive.md`](../reviews/trade-engine-deep-dive.md). Tier 2 → [`trade-engine-tier2-models.md`](trade-engine-tier2-models.md). Tier 3 → [`trade-engine-tier3-rebuild.md`](trade-engine-tier3-rebuild.md).*

**Theme:** correct the math without changing the product surface. These are surgical, individually testable, and should be done regardless of whether we later rebuild the generator. Estimated effort: 2–4 focused days.

**Scope:** `backend/trade_service.py` only (plus tests + one doc fix). No API shape changes, no DB migrations, no client changes. Everything behind a single feature flag so we can A/B vs. the legacy scorer.

---

## Goals

1. Multi-player trades (2-for-1, 1-for-2, 3-for-2) can actually surface. *(fixes P0-1)*
2. Every surfaced trade is genuinely mutually beneficial — both sides perceive a gain. *(fixes P0-2)*
3. All scoring happens in one consistent value space. *(fixes P1-3)*
4. Noisy (under-sampled) personal ratings don't masquerade as real valuation disagreement. *(fixes P1-5)*
5. The top-N cards returned are the actual best N, not the first N enumerated. *(fixes P2-6)*
6. Mechanical correctness: the `fairness_score` field bug, dead-code multipliers, stale docs. *(fixes P3-8)*

## Non-goals (deferred to Tier 2/3)

- Marginal/over-replacement valuation, outlook-as-blend, acceptance model — Tier 2.
- ILP/knapsack package construction, 3-team cycles, sweeteners — Tier 3.
- "Likes-you" deck boosting and fuzzy mirror matching — Tier 2 (touches match flow, not the scorer).
- Any change to the Elo ranking engine itself (`ranking_service.py`).

---

## Feature flag

Add `trade_engine_v2` to `config/features.json` and the `FLAGS` object in `backend/feature_flags.py`. When **off**, `generate_trades` runs the exact legacy path (current behavior, byte-for-byte). When **on**, the Tier 1 scorer runs. This lets us:
- Ship dark, validate via offline replay (see Testing).
- A/B per league later by reading the flag per-request.

All new config constants below go in `_DEFAULT_CFG` in `trade_service.py` (and the `model_config` DB seed) so they're tunable without a deploy, consistent with the existing pattern.

---

## Change 1 — Single value space *(P1-3, foundational; do first)*

Everything else depends on this. Today three scales coexist: raw Elo diffs (mutual gain), summed-seed-Elo ratios (fairness), and `search_rank`→exponential (KTC gate). Collapse to one transform applied to **every** Elo before any comparison.

### New function

```python
def elo_to_value(elo: float) -> float:
    """Map a personal/seed Elo rating onto the dynasty-value scale used for
    ALL trade math. Monotone increasing. Calibrated so the transform of a
    typical elite Elo (~1790) ≈ the KTC value of a top-5 player, and a
    replacement-level Elo (~1300) ≈ a low-end bench value.

        value = ktc_max * exp(elo_value_k * (elo - elo_value_ref))

    elo_value_k and elo_value_ref are config-tunable. With ref=1500 and
    k≈0.0050, elo 1790 → ~4250, elo 1500 → 1000-ish baseline, elo 1300 → ~370.
    """
```

Config additions (`_DEFAULT_CFG`):
```python
"elo_value_k":   0.0050,   # steepness of Elo→value curve
"elo_value_ref": 1500.0,   # Elo that maps to the curve's reference value
"elo_value_base": 1000.0,  # value at the reference Elo
```
(Final constants set during calibration — see "Calibration" below. The curve must be roughly consistent with the existing `dynasty_value(search_rank)` curve so the KTC fairness gate and the new value space agree.)

### Where it's used
- **User value** of a player: `vu(pid) = elo_to_value(user_elo[pid])`
- **Opponent value:** `vo(pid) = elo_to_value(opp_elo[pid])`
- **Consensus/seed value:** `vs(pid) = elo_to_value(seed_elo[pid])`

`package_value()` stays as-is (diminishing weights 1.0/0.75/0.55…) but is now fed `elo_to_value` outputs, not raw Elo and not `dynasty_value(search_rank)`. The existing `dynasty_value()`/`search_rank` curve is retained **only** as the seed source and as a fallback when a player has no Elo; it no longer participates in the per-trade gates directly (those move to the seed-Elo→value space).

### Calibration
Pick `elo_value_k`, `elo_value_ref`, `elo_value_base` so that, across the live player pool, `elo_to_value(seed_elo[p])` correlates ≥ 0.98 (Spearman) with the current `dynasty_value(p)`. Write a one-off script in `backend/scripts/` that loads the universal pool, computes both, and reports correlation + a few anchor points (elite/starter/bench). This guarantees the fairness gate behaves the same on 1-for-1s (no silent regression) while extending cleanly to multi-player packages.

---

## Change 2 — Un-break multi-player trades *(P0-1)*

In `_generate_for_pair`, the 2-for-1 / 1-for-2 / 3-for-2 sections currently sum **raw Elo** and compare against a single raw Elo (`recv_user <= combined_give_user * 0.95`). Two players sum to ≥ ~2400; no single player reaches 0.95× that → every candidate is filtered. Replace raw-Elo sums with **package values** in the new value space.

### Pattern (shown for 2-for-1; mirror for 1-for-2 and 3-for-2)

```python
# OLD (broken):
combined_give_user = user_elo[g1] + user_elo[g2]
combined_give_opp  = opp_elo[g1]  + opp_elo[g2]
recv_user = user_elo[recv]; recv_opp = opp_elo[recv]
if recv_user <= combined_give_user * 0.95: continue
if combined_give_opp <= recv_opp * 0.95:   continue
mismatch = (recv_user - combined_give_user) + (combined_give_opp - recv_opp)

# NEW:
give_val_user = package_value([vu(g1), vu(g2)])   # user's value of what they give
give_val_opp  = package_value([vo(g1), vo(g2)])   # opp's value of the same package
recv_val_user = package_value([vu(recv)])
recv_val_opp  = package_value([vo(recv)])

user_surplus = recv_val_user - give_val_user      # user gains in user's eyes
opp_surplus  = give_val_opp  - recv_val_opp       # opp gains in opp's eyes
# (gate handled by Change 3)
```

The diminishing-returns weighting now correctly makes a 2-pack worth *less* than the raw sum, so a single elite can clear a two-player package. This is what makes 2-for-1s reachable.

`package_value` is computed in the per-opponent value space; memoize `vu/vo` per pid with the existing `_dv_cache` pattern (rename to `_vu_cache`/`_vo_cache` or generalize). Keep the deadline + iteration budget guards unchanged.

---

## Change 3 — True mutual gain *(P0-2)*

The current `_mismatch_score` returns `opp_surplus + user_surplus` and callers gate on the **sum** > 0, which admits one-sided trades (user −50, opp +200 passes). For both 1-for-1 and multi-player paths:

### New gate + score

```python
MIN_SIDE = _c("min_side_surplus")   # both sides must clear this (value units)

if user_surplus < MIN_SIDE or opp_surplus < MIN_SIDE:
    continue   # not genuinely mutual — skip

mutual_gain = min(user_surplus, opp_surplus)        # the binding side
balance     = mutual_gain / max(user_surplus, opp_surplus, 1)  # 0..1, 1=symmetric
```

### New composite

```python
composite = (
    _c("mismatch_weight") * _normalize(mutual_gain)   # was min(mismatch,cap)/cap on the SUM
    + _c("fairness_weight") * fairness                # consensus balance (Change 4)
) * _tier_mult_for_pids(all_pids)
```

`_normalize` replaces the arbitrary 300/400/500 caps with one scale (e.g. logistic or `min(x, V_CAP)/V_CAP` with a single `mutual_gain_cap` config). Ranking by `min(·,·)` is also the acceptance-optimal objective: both managers face an endowment effect, so the less-happy side is what kills the deal.

Config additions:
```python
"min_side_surplus":  150.0,   # min per-side value gain to surface a trade (tune)
"mutual_gain_cap":  1500.0,   # normalization ceiling for mutual_gain
```

`_mismatch_score` is refactored to return `(user_surplus, opp_surplus)` (or kept as a thin wrapper returning the min). Keep `mismatch_score` on `TradeCard` populated with `mutual_gain` for display continuity.

---

## Change 4 — Confidence shrinkage *(P1-5)*

Under-sampled players have noisy Elo; the engine reads noise as disagreement. Shrink each user's personal value toward the consensus seed by how many times the player has been compared.

### Mechanism

`RankingService._compute_stats` already tracks `compared` (set of opponents faced) per player. Expose a per-player comparison count to the trade layer. In `generate_trades`, the caller (server) already has the `RankingService`; pass a `confidence: dict[str, int]` (pid → comparison count) alongside `user_elo`.

Shrink **before** `elo_to_value`:

```python
n0 = _c("shrink_pseudocount")          # e.g. 4
def shrunk_user_elo(pid):
    n = confidence.get(pid, 0)
    w = n / (n + n0)                    # 0 when unseen, →1 as well-sampled
    return w * user_elo[pid] + (1 - w) * seed_elo.get(pid, 1500.0)
```

So a player the user never ranked sits at consensus (no fake divergence); a heavily-ranked player keeps their full personal value. This directly attacks the depth-trade bias the tier multipliers were patched in to fight — **after this lands, re-tune (likely shrink) the tier multipliers** (`tier_mult_*`) and confirm the deck no longer over-indexes on depth without them carrying all the weight.

Config:
```python
"shrink_pseudocount": 4.0,
```

If threading `confidence` through is too invasive for Tier 1, an acceptable interim: shrink toward seed by a flat factor when `user_elo[pid] == seed_elo[pid]` (unranked proxy). But the comparison-count version is strongly preferred and is a small server wiring change (`_run_trade_job` and the `/generate` handler already hold `service`).

---

## Change 5 — Top-K, not first-K *(P2-6)*

`max_candidates=30` currently breaks the loops after the first 30 candidates *in roster order*. Replace the "append then break at 30" with a bounded **min-heap of size K** keyed on `composite`, so we keep the best K seen regardless of visit order; and pre-sort candidate players by value-divergence so high-promise pairs are visited first (anchor-first), preserving the time budget.

```python
import heapq
heap = []   # (composite, tiebreak, give_ids, recv_ids)
def _offer(composite, give_ids, recv_ids):
    if len(heap) < K:
        heapq.heappush(heap, (composite, _tb(), give_ids, recv_ids))
    elif composite > heap[0][0]:
        heapq.heapreplace(heap, (composite, _tb(), give_ids, recv_ids))
```

Pre-sort: `give_candidates.sort(key=lambda pid: opp_value - user_value, reverse=True)` (players the opponent over-values relative to the user — i.e. the user's best sell-high assets) and symmetrically for `recv_candidates`. Keep the deadline and `_iter_budget`; they now bound work *after* the most promising pairs are already visited, so early termination loses little.

Bump the effective ceiling so K covers `max_per_opponent` with headroom (K ≈ 4× `max_cards`).

---

## Change 6 — Mechanical fixes *(P3-8)*

1. **`fairness_score` field bug** (`trade_service.py:1353`): currently assigned `composite`. Assign the actual `fairness` value; keep `composite_score` separate. Audit clients (`trade_card_to_dict`, mobile/web) for any code that read `fairness_score` expecting the composite — fix or leave a compatibility alias if needed.
2. **Dead multipliers:** `team_outlook_multiplier` and `positional_preference_multiplier` are never called. For Tier 1, **leave them defined but unused** (Tier 2 replaces them with valuation-level mechanisms) and add a module docstring note `# NOT WIRED — see Tier 2 plan`. Do **not** silently wire them now.
3. **Docs:** fix `docs/architecture.md` line ~71, which claims outlook/positional multipliers are active. Note they're inert pending Tier 2. Update the trade-card request-lifecycle section if value-space wording changed.
4. **Tax overlap (light touch):** leave QB/star/clogger taxes flag-gated and off by default under v2 (the clogger phenomenon is partly absorbed by package_value diminishing returns now). Full reconciliation is Tier 2. Document the overlap in the plan, don't re-tune yet.

---

## File-by-file change list

| File | Change |
|---|---|
| `backend/trade_service.py` | `elo_to_value`; rewrite multi-player gates to use `package_value`; refactor `_mismatch_score`→surplus pair; min-surplus gate + new composite; confidence shrinkage hook; heap-based top-K; fix `fairness_score` field; flag branch for legacy vs v2 |
| `backend/feature_flags.py` + `config/features.json` | add `trade_engine_v2` flag |
| `backend/server.py` | thread `confidence` (comparison counts) into `generate_trades` from the `RankingService`; pass through in `_run_trade_job` |
| `backend/scripts/calibrate_elo_value.py` (new) | one-off correlation check for `elo_to_value` constants |
| `backend/tests/test_trade_engine_v2.py` (new) | see Testing |
| `docs/architecture.md` | correct the inert-multiplier claim; value-space wording |
| `docs/config-reference.md` | document new `model_config` keys |

---

## Testing

**Unit (`test_trade_engine_v2.py`):**
1. **Multi-player reachability** — the engineered scenario from the deep dive: user covets one elite, opponent covets the user's two mid WRs. Assert at least one 2-for-1 card is produced (the legacy engine produces zero). This is the regression test for P0-1.
2. **No one-sided trades** — construct a trade with user_surplus < 0; assert it is never surfaced. (P0-2)
3. **Value-space monotonicity** — `elo_to_value` strictly increasing; package_value of [a,b] < a+b for a,b>0. 
4. **Calibration guard** — Spearman(`elo_to_value(seed)`, `dynasty_value`) ≥ 0.98 on the live pool (in the calibration script, asserted).
5. **Shrinkage** — an unranked player (0 comparisons) contributes ~seed value; a heavily-ranked one contributes ~personal. (P1-5)
6. **Top-K** — feed > K candidates in deliberately bad order; assert the returned set equals the true top-K by composite. (P2-6)
7. **Flag parity** — with `trade_engine_v2` OFF, output is identical to current `main` on a fixed fixture (snapshot test) — proves the legacy path is untouched.

**Offline replay (the real validation, before any A/B):**
- Script in `backend/scripts/replay_trade_decisions.py`: load historical `trade_decisions` (likes/passes) and `trade_matches`. For each historical session state, regenerate cards with v1 and v2; measure:
  - **precision@5 / recall** against recorded *likes*
  - fraction of historically *matched* trades that each engine ranks in the user's top-5
  - multi-player card share (expect 0% → non-trivial under v2)
- Ship v2 only if precision@5 is ≥ v1 and matched-trade top-5 recall improves.

**Guardrails:** card-gen p95 latency ≤ current (the heap + pre-sort should be neutral-to-faster since pruning improves); no league that had > 0 cards drops to 0.

---

## Rollout

1. Land behind `trade_engine_v2 = false`. Unit + parity tests green.
2. Run offline replay; review metrics.
3. Enable in shadow mode (generate both, serve v1, log v2 deltas) — see Tier 2/3 plans for the shared shadow harness, or a minimal version here.
4. Flip the flag on for a small set of test leagues; watch mutual-match rate.
5. Promote to default; keep the flag for one release as a kill switch.

## Success criteria

- ✅ Multi-player trades appear in real decks (was structurally impossible).
- ✅ Zero one-sided trades in generated output (verified by gate + test).
- ✅ Offline replay: precision@5 ≥ legacy, matched-trade top-5 recall ↑.
- ✅ Latency p95 ≤ legacy; no league regresses to 0 cards.
- ✅ `docs/` no longer misdescribes the engine.
