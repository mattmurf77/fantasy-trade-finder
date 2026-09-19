# Trade Engine — Tier 3: Rebuild the Generator

*Companion to [`docs/reviews/trade-engine-deep-dive.md`](../reviews/trade-engine-deep-dive.md). Tier 1 → [`trade-engine-tier1-fixes.md`](trade-engine-tier1-fixes.md). Tier 2 → [`trade-engine-tier2-models.md`](trade-engine-tier2-models.md).*

**Theme:** replace blind nested-loop enumeration with exact optimization, and unlock trade structures no consumer tool offers (3-team cycles, sweeteners). **Depends on Tiers 1 & 2** (single value space, marginal valuation, acceptance model as the objective). This is the "new engine" the user explicitly wants to **A/B-test before shipping live**. Estimated effort: 3–6 weeks.

**Scope:** a new generator module running alongside the existing one, selectable per league via flag; new optimization dependency (OR-Tools); DB read of full-league rosters/picks for cycles. The legacy + Tier 1/2 scorer remains the fallback and the A/B control.

---

## Goals

1. **Exact package construction** — guarantee the best feasible give/receive package per opponent is found, instead of truncating an arbitrary enumeration under a time budget. *(fixes the "best 2-for-1 may never be visited" problem)*
2. **Roster-feasibility as a hard constraint** — post-trade lineups must be legal for *both* teams (true post-trade marginal valuation, not the Tier 2 approximation).
3. **3-team cycle trades** — Pareto-improving multi-way swaps via kidney-exchange-style clearing.
4. **Sweeteners** — auto-suggest picks/FAAB to close near-miss trades.
5. **Accepted-trade-fit consensus values** — replace static seed values with values regressed from real accepted trades, once data volume allows.

## Non-goals

- Discarding Tiers 1/2 — this *consumes* their value space, marginal valuation, and acceptance model. Tier 3 changes *how candidates are constructed and selected*, not what "good" means.
- GA/metaheuristics — dominated by exact ILP/DP at league scale (documented rationale, not pursued).

---

## Work item 3.1 — Per-pair exact package construction

**Approach A — Integer Program (preferred).** For each (user, opponent) pair, binary vars `x_i` (user gives asset i ∈ user roster), `y_j` (user receives asset j ∈ opp roster):

```
maximize   z                                    # the binding-side surplus (min of the two)
subject to z ≤ user_surplus(x, y)               # marginal value, both from Tier 2
           z ≤ opp_surplus(x, y)
           user_surplus ≥ θ,  opp_surplus ≥ θ   # genuine mutual gain (Tier 1 gate)
           fairness_lo ≤ Σ vs·y / Σ vs·x ≤ fairness_hi   # consensus balance band
           Σx ≤ 3,  Σy ≤ 3,  |Σx − Σy| ≤ 1      # package size limits
           post-trade lineup feasibility (both rosters)  # linear count constraints
           [optional] x_pinned = 1              # "I want to trade away player P"
```

- `min`-objective linearized with the single auxiliary `z` (standard).
- Marginal value (Tier 2) makes the objective roster-aware; with exact post-trade lineup constraints we get true post-trade marginals, upgrading the Tier 2 approximation.
- ~60 binary vars per pair → **milliseconds** with OR-Tools CBC. All ~11 opponents solve exactly well inside the current 1s/opponent budget.
- To return *multiple* cards per opponent (the deck wants ~5), solve iteratively with **no-good cuts** (forbid the previous solution, re-solve) or enumerate the top-K via solution-pool — both cheap at this size.

**Approach B — Knapsack/Subset-sum DP (fallback / no-dependency path).** Fix the receive-package (enumerate the opponent's 1–2 player combos the user most covets, ranked by user surplus), then DP the give side: discretize consensus value to ~50-pt buckets, fill a `(roster_size × value_buckets)` table, find the give-package landing in the fairness band that minimizes the user's marginal-value loss. Table is tiny (~30×200). Exact for the fixed-receive subproblem; loop over the top receive-packages. Use this if we want to avoid the OR-Tools dependency.

Decision: ship **A** behind the flag; keep **B** documented as the dependency-free alternative. Both share the Tier 2 marginal-value and fairness functions, so the objective is identical — only the search differs.

Flag: `trade_engine_v3`. New module `backend/trade_optimizer.py`. The acceptance model from Tier 2 re-ranks the ILP's feasible top-K (ILP finds *fair + mutually-beneficial*; the model orders by *likely to be accepted*).

---

## Work item 3.2 — Roster-feasibility constraints

Encode each league's lineup requirements (starters per position, FLEX, superflex, TEP, bench size) as linear constraints in 3.1. Inputs already exist: `scoring_format`, `_STARTER_NEED`/`_SURPLUS_AT`, league settings from Sleeper sync. A trade is infeasible if either team can't field a legal lineup afterward (e.g. trades away their only TE in a TE-required league). This is what makes the marginal valuation *exact* rather than approximate, and it kills nonsensical cards at the constraint level instead of post-hoc penalties.

---

## Work item 3.3 — 3-team cycle trades (kidney-exchange clearing)

**The genuine differentiator** — no consumer dynasty tool offers automated 3-team trades, and Sleeper/MFL support executing them.

### Mechanism (Abraham/Blum/Sandholm EC'07 clearing, scaled down)
1. Build a directed graph over the whole league. Node = a candidate single-asset transfer "atom": team A could give player p. Edge `A→B` (with player p, q) when B values p more than A does by margin δ>0 **and** A would accept q-class compensation — i.e. there's a beneficial directed handoff.
2. Find **max-weight vertex-disjoint cycles of length 2–3** where every participating team's *net* surplus (received marginal value − given marginal value, in its own valuation) ≥ θ. Cycle weight = sum (or min) of per-team net surpluses.
3. Solve as a small ILP: one binary var per feasible cycle, constraint that each team appears in ≤1 selected cycle, maximize total weight. League scale (12 teams) makes this trivial (sub-second).
4. Cap cycle length at 3 (mirrors the practical reality that >3-team fantasy trades essentially never execute, and matches kidney-exchange's simultaneity constraint).

### Product surface
3-team cards are a distinct card type ("3-team deal: you send X to B, get Y from C"). Matching/acceptance is harder (all three must agree) — gate these to high-confidence, high-surplus cycles only, and require all three to opt in. Present rarely and only when clearly better than any available 2-team deal for the user.

Flag: `trade_three_team`. New logic in `trade_optimizer.py`. Reads full-league rosters (already available in `League.members`) and per-member rankings (`load_member_rankings`).

---

## Work item 3.4 — Sweeteners

For trades that land *just below* the fairness band (e.g. consensus ratio 0.60–0.75 — currently discarded), search the under-paying side's assets for a **pick or FAAB** add that brings the ratio into band while keeping both surpluses positive. Picks/FAAB are fantasy's numeraire — the escape from double-coincidence-of-wants. Implementation: after the ILP returns the best in-band trade, also run a "near-miss + sweetener" pass that adds one pick/FAAB var to close the gap. Present as "add a 2027 3rd to make it work." Flag: `trade_sweeteners`. Requires pick/FAAB assets in the value space (picks already exist as pseudo-players with `pick_value`; FAAB needs a value mapping).

---

## Work item 3.5 — Accepted-trade-fit consensus values (FantasyCalc method)

**Once trade volume allows.** Replace static `search_rank`-decay seed values with values **regressed from real accepted trades**:
- Collect accepted trades (FTF's own `trade_matches` with `status='accepted'`, plus real Sleeper league trades via the API).
- Treat each as `Σ value(side A) ≈ Σ value(side B)`; solve the over-determined system (recency-weighted least squares) for per-asset values, per format (superflex/TEP/league size).
- These become the **consensus/seed value scale** for the fairness gate; per-user Elo still drives the *mismatch/perception-gap* term. By construction, "fair" now means "resembles trades people actually accept."

Interim: use FantasyCalc's public API as the consensus scale (verify terms) before we have the volume to fit our own. New module `backend/value_fitting.py` + offline script. Flag: `trade_fitted_values`.

---

## Architecture: dual engine, selectable

```
/api/trades/generate
   └─ engine = flag(league) ?  trade_optimizer (v3)   # ILP/DP + cycles + sweeteners
                            :  trade_service  (v1/v2)   # legacy + Tier1/2 fallback / control
   both feed the SAME value space (Tier 1), marginal valuation (Tier 2),
   and acceptance-model re-ranking (Tier 2).
```

The optimizer produces feasible mutually-beneficial candidates; the Tier 2 acceptance model orders them; the same `TradeCard` shape ships to clients (3-team cards carry an extra field). Legacy path stays as the A/B control and kill-switch.

## File-by-file (high level)

| File | Change |
|---|---|
| `backend/trade_optimizer.py` (new) | ILP package construction (3.1), feasibility constraints (3.2), 3-team cycle clearing (3.3), sweetener pass (3.4) |
| `backend/value_fitting.py` (new) | accepted-trade regression (3.5) |
| `backend/server.py` | engine selection by flag; 3-team card shape; full-league roster/pick loading for cycles |
| `backend/trade_service.py` | expose shared value/marginal/fairness functions for the optimizer to reuse |
| `requirements` | `ortools` (Approach A); none if Approach B chosen |
| `docs/` | ADR for the engine rebuild; architecture; data-dictionary; api-reference (3-team card shape) |

## Testing & rollout — the explicit "test before live" gate the user asked for

1. **Correctness unit tests:** ILP returns the known-optimal package on hand-built fixtures (cross-check against brute force on small rosters); feasibility constraints reject illegal-lineup trades; 3-team cycle solver finds the optimal disjoint cycle set on a constructed graph.
2. **Equivalence/parity:** on 1-for-1-only fixtures, v3 and v2 should agree on the top card (the optimizer shouldn't *lose* good 1-for-1s).
3. **Offline replay (primary pre-ship validation):** regenerate historical decks with v1, v2, v3; measure precision@5, matched-trade top-5 recall, and **counterfactual match rate** (how many historically-matched trades each engine surfaces). v3 must beat v2.
4. **Shadow mode:** run v3 alongside the served engine for N weeks; log card sets + scores; no user exposure. Inspect 3-team cards manually for sanity before ever showing them.
5. **Staged A/B by league** (`config/features.json` + `model_config` per-league flags): start with a handful of opt-in/test leagues. **Primary metric: mutual-match rate per active user**; secondary: accept-rate-per-match, like-rate-per-card, 3-team-card engagement, latency p95.
6. **Guardrails:** v3 latency p95 ≤ budget; never 0 cards where v2 had > 0; 3-team cards suppressed unless they clear a high surplus bar; kill switch = flip flag to v2.
7. **Promote** to default only after A/B shows a statistically meaningful match-rate lift with no acceptance-quality regression.

## Success criteria

- ✅ Optimizer provably returns the best feasible package per pair (vs. brute-force on small cases); no good trade missed due to enumeration truncation.
- ✅ Illegal-lineup trades never surface (constraint-level, not penalty).
- ✅ 3-team cycles surface real, sane, high-surplus deals — a feature no competitor has.
- ✅ Offline replay + A/B: v3 lifts mutual-match rate over v2 with no accept-quality drop.
- ✅ Fitted consensus values (when volume allows) make "fair" mean "actually accepted."
- ✅ Full kill-switch back to v2/v1 at any time via flag.
