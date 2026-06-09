# Trade Engine — Tier 2: Model Upgrades

*Companion to [`docs/reviews/trade-engine-deep-dive.md`](../reviews/trade-engine-deep-dive.md). Tier 1 → [`trade-engine-tier1-fixes.md`](trade-engine-tier1-fixes.md). Tier 3 → [`trade-engine-tier3-rebuild.md`](trade-engine-tier3-rebuild.md).*

**Theme:** make the *valuation* roster-aware and the *ranking* acceptance-aware, replacing hand-tuned multiplier stacks with principled mechanisms and a learned model. **Depends on Tier 1** (single value space, true mutual gain). Estimated effort: 2–4 weeks, sequenced so each piece ships independently.

**Scope:** `backend/trade_service.py`, `backend/server.py` (match flow + feature wiring), `backend/database.py` (new tables for training data + want-lists), a new `backend/acceptance_model.py`, and small mobile/web surface for want-lists. Multiple feature flags.

---

## Goals

1. **Roster-aware valuation:** a player is worth what he adds over the roster's own replacement at his position — automatically devaluing clogger packages and surfacing need-fillers. *(replaces positional-preference filter, roster-clogger tax, most needs logic)*
2. **Outlook as valuation, not post-hoc multiplier:** blend now-value/future-value per the user's contender↔rebuilder stance. *(replaces the inert `team_outlook_multiplier`)*
3. **"Likes-you" match acceleration:** surface cards the counterparty already liked; relax exact-mirror matching to fuzzy similarity. *(biggest match-rate lever, mostly plumbing)*
4. **Learned acceptance model:** rank cards by `P(user likes) × P(opp accepts) × joint_gain`, trained on accumulated swipe/disposition data. The model *learns* the QB/star/clogger corrections instead of hard-coding them.

## Non-goals

- ILP/knapsack generator, 3-team cycles, sweeteners — Tier 3.
- Replacing consensus seed values with FantasyCalc-fit values — Tier 3 (needs volume).
- Any change to the core Elo trio-ranking math.

---

## Work item 2.1 — Marginal (over-replacement) valuation

**Problem it solves:** raw value ignores roster context. A 3rd starting-caliber QB in a 1-QB league is near-worthless to that roster but scores like an asset today. The clogger tax, positional-preference filter, and `match_context` needs/surplus are all partial, bolt-on attempts at this.

### Mechanism

For a roster `R` and player `p` at position `pos`:
```
replacement(R, pos) = value of R's best player at pos NOT in the starting lineup
                      (i.e. the player who would start if p left, or the
                       waiver baseline if pos is already thin)
marginal(p, R)      = max(0, value(p) - replacement(R, pos)) + bench_credit(p)
```
- `bench_credit` is a small fraction of raw value (config `bench_credit_rate ≈ 0.15`) so depth still has *some* worth (bye weeks, injuries) but far less than starters.
- Starter slots per position come from league settings (`scoring_format`, superflex, TEP) — the same data `analyze_roster_strengths` and `_STARTER_NEED`/`_SURPLUS_AT` already encode.

### Where it plugs in

In `_generate_for_pair`, surplus is computed on **marginal** values from each roster's perspective:
```
user_surplus = marginal_pkg(recv, user_roster_after) - marginal_pkg(give, user_roster_before)
opp_surplus  = marginal_pkg(give, opp_roster_after)  - marginal_pkg(recv, opp_roster_before)
```
Computing post-trade marginals exactly requires re-deriving the lineup after the swap; a cheaper, good-enough approximation for Tier 2: compute replacement levels from the *pre-trade* roster (acquiring side gains `value(p) − pre_replacement`, shedding side recovers a roster spot worth `bench_credit`). Exact post-trade re-optimization is a Tier 3 ILP feature.

### Consolidation

Once marginal valuation is live and validated:
- **Remove** the positional-preference *hard filter* (keep acquire/trade-away as an optional UI filter, not scoring).
- **Retire** `roster_clogger_adjustment` (subsumed: a clogger package has low marginal value on the receiving roster).
- Keep `match_context` for narrative but drive the rationale from marginal deltas ("adds a starter at your thinnest position").

Config:
```python
"bench_credit_rate": 0.15,
"waiver_baseline_value": 250.0,   # replacement floor when a position is empty
```

Flag: `trade_marginal_value`. Tests: a 3rd-QB-in-1QB trade scores near zero; a need-filling trade outscores an equal-raw-value depth swap.

---

## Work item 2.2 — Outlook as now/future valuation blend

**Problem it solves:** team outlook currently does nothing to scoring (`team_outlook_multiplier` is dead code). Age-threshold multipliers were a blunt instrument.

### Mechanism (DynastyProcess pattern)

Maintain two value columns per player:
- `now_value` — redraft/win-now weighted (peak-age and proven production favored)
- `future_value` — age- and pick-weighted (youth and draft capital favored)

Derive both from the existing seed/Elo value plus a per-position **age curve**:
```
now_value(p)    = base_value(p) * age_now_curve(pos, age)
future_value(p) = base_value(p) * age_future_curve(pos, age)
```
Age curves (config-driven, position-specific): RB cliff ~26, WR plateau into ~29, QB ~flat into 30s, TE late peak. Picks: high future_value, low now_value.

Blend per user outlook:
```
α = {championship:1.0, contender:0.75, not_sure:0.5, rebuilder:0.25, jets:0.1}[outlook]
v_user(p) = α * now_value(p) + (1-α) * future_value(p)
```

This `v_user` feeds the value space from Tier 1 (`elo_to_value` output × the now/future blend, or blend applied to base then transformed). Because it's an **input** to surplus/fairness, it composes correctly with the fairness gate — unlike a post-hoc multiplier, which fought the gate.

### Consolidation
Delete `team_outlook_multiplier` (truly dead now). Outlook reads from `load_league_preference` exactly as today; only its *effect* moves from "unused multiplier" to "valuation blend weight."

Config: age-curve tables per position; `outlook_alpha` map. Flag: `trade_outlook_blend`. Tests: same trade ranks higher for a rebuilder when receiving youth/picks vs. a championship roster.

---

## Work item 2.3 — "Likes-you" boosting + fuzzy mirror matching

**Problem it solves:** the counterparty's prior likes are invisible to the user's deck, and mirror detection requires exact set equality so near-identical trades never match. This is the cheapest large match-rate win.

### 2.3a — Likes-you queue
When generating the user's deck, query `trade_decisions` for **likes by league-mates whose mirror the user could accept** (opponent liked giving X for Y; X is on opponent's roster, Y on the user's). Inject these as high-priority cards (boost composite, or a dedicated "they're interested" rail). Reuses `check_for_match`'s mirror logic, run proactively at generation time instead of only at swipe time.

### 2.3b — Fuzzy mirror matching
Relax `check_for_match` (`database.py`) from exact set equality to **package similarity**:
```
match if  jaccard(their_give, my_receive) ≥ τ
      and jaccard(their_receive, my_give) ≥ τ
      and the symmetric value gap is within a band
```
with `τ ≈ 0.8` (config). Two cards differing by one low-value bench piece or a swappable pick then still match. Guard against false matches with a value-gap ceiling so a similar-but-lopsided pair doesn't auto-match.

Flags: `trade_likes_you`, `trade_fuzzy_match`. Tests: a card differing from a league-mate's like by one bench player triggers a match under fuzzy, not under exact; likes-you cards appear at deck top.

> Note: 2.3 touches the **match flow**, not the scorer — it can ship before or in parallel with 2.1/2.2.

---

## Work item 2.4 — Learned acceptance model

**Problem it solves:** the composite is a hand-tuned weighted sum with ad-hoc taxes. The app already generates labeled impressions on every swipe; learn the ranking instead.

### Data pipeline
- **Impressions table** (new, `database.py`): every card *shown* (from `_make_progress_cb` / `/api/trades`) logged with its features + an `impression_id`. Today only decisions are stored; we need shown-but-not-acted (implicit negatives) too. Add lightweight logging in the trade snapshot path.
- **Labels:** join impressions to `trade_decisions` (like=positive, pass=negative) and `trade_matches` (matched/accepted = strong positive). Real Sleeper trade outcomes via the API are the ultimate label when available.

### Features (per card, both perspectives)
user_surplus, opp_surplus, min/ratio of the two, consensus value delta, best-player tier gap, package sizes & asymmetry, positional-need fit (marginal-value deltas from 2.1), outlook alignment (2.2), counterparty recent activity, records/standings, whether it's a likes-you card.

### Model
Start **pointwise logistic regression** in pure Python (keep the stack light — no new heavy deps; `numpy` is enough, or a tiny hand-rolled SGD) predicting `P(positive)`. Graduate to gradient-boosted trees (LightGBM/XGBoost) only if logistic underperforms and the dependency is acceptable. New module `backend/acceptance_model.py`:
```python
def predict_accept(features: dict) -> float        # P(opp accepts | shown)
def predict_like(features: dict) -> float          # P(user likes | shown)
def score_card(card, ctx) -> float                 # P(like)*P(accept)*joint_gain
```
Model artifact (coefficients) stored in `model_config` or a small file; retrained offline by a script in `backend/scripts/`, never in the request path.

### Ranking
Final deck order = `score_card`. The hand-tuned taxes (QB/star/clogger) and tier multipliers become **fallback** when the model is unconfident (cold-start: few labels for this user/league) — blend `λ·model + (1−λ)·heuristic`, λ rising with label volume. This is the data flywheel: more swipes → better ranking → more matches → more swipes.

Flag: `trade_acceptance_model`. Tests: model improves precision@5 over the Tier 1 heuristic on a held-out split; cold-start falls back gracefully to the heuristic.

---

## Sequencing & dependencies

```
Tier 1 (value space, mutual gain) ──┬─► 2.1 marginal valuation ──┐
                                    ├─► 2.2 outlook blend  ───────┼─► 2.4 acceptance model
                                    └─► 2.3 likes-you / fuzzy ─────┘   (uses 2.1/2.2 features)
2.3 can ship independently (match flow, not scorer).
2.4 should ship last (needs 2.1/2.2 features + accumulated labels).
```

## File-by-file (high level)

| File | Change |
|---|---|
| `backend/trade_service.py` | marginal valuation; outlook blend feeding value space; delete dead multipliers; heuristic↔model blend hook |
| `backend/acceptance_model.py` (new) | feature extraction, train/predict, artifact load |
| `backend/server.py` | impression logging; likes-you query at generation; model wiring; want-list endpoints (optional, feeds 2.4 features) |
| `backend/database.py` | `trade_impressions` table; fuzzy `check_for_match`; (optional) `player_wants` table |
| `backend/scripts/train_acceptance_model.py` (new) | offline training + eval |
| `mobile/` + `web/` | (2.3) "they're interested" rail; (optional) per-player want toggles |
| `docs/` | data-dictionary (new tables), api-reference (new endpoints), architecture, glossary (now/future value, marginal value) |

## Testing & rollout

- Each work item behind its own flag; unit tests per item (above).
- **Offline replay** harness from Tier 1 extended with the new features; gate each item on precision@5 / matched-trade recall ≥ previous state.
- **Shadow mode** for 2.4: log model scores beside served heuristic order; compare before serving.
- A/B per league; **primary metric: mutual-match rate per active user**, then accept-rate-per-match, then like-rate-per-card.
- Guardrail: model never serves below the heuristic floor during cold-start (λ blend).

## Success criteria

- ✅ Clogger/positional/outlook multipliers retired; one valuation mechanism does their job better (measured: need-filling trades rank above equal-value depth swaps).
- ✅ Match rate up vs. Tier 1, driven measurably by likes-you + fuzzy matching.
- ✅ Acceptance model beats the heuristic on held-out precision@5 and lifts live match rate in A/B.
- ✅ No cold-start regression (λ-blend fallback verified).
