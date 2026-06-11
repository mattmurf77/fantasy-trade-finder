# Trade Engine Deep Dive & Improvement Proposal

*Date: 2026-06-09 · Scope: `backend/trade_service.py`, `backend/ranking_service.py`, trade wiring in `backend/server.py` + `backend/database.py` · Goal: surface "better" trades — more cards liked by the user AND accepted by the counterparty.*

> ~~Research caveat: web access was down…~~ **Resolved 2026-06-10:** §3 has been verified online with sources. Two corrections vs. the original training-knowledge draft: (1) the eBay QJE 2020 paper documents bargaining *behavior* (immediate vs. delayed agreement, reciprocal concessions), it is not itself an ML acceptance model — the P(accept) modeling recommendation stands on its own; (2) DynastyProcess's published decay (k=0.0235) is ~2× steeper than FTF's `ktc_k=0.0126`, a new calibration finding. §2b adds second-pass code findings verified directly in the repo.
>
> **Update (2026-06-09, third pass):** §3 has now been verified and superseded by [`trade-engine-external-research.md`](trade-engine-external-research.md), which carries live sources and a list of amendments (A1–A10) to the tier plans — including a data-volume reality check that defers the Tier 2 learned acceptance model.

**Implementation plans** (derived from §4 below):
- Tier 1 — Fix the current engine: [`docs/plans/trade-engine-tier1-fixes.md`](../plans/trade-engine-tier1-fixes.md)
- Tier 2 — Model upgrades: [`docs/plans/trade-engine-tier2-models.md`](../plans/trade-engine-tier2-models.md)
- Tier 3 — Rebuild the generator: [`docs/plans/trade-engine-tier3-rebuild.md`](../plans/trade-engine-tier3-rebuild.md)

---

## 1. How the engine works today

1. **Personal values:** each user ranks players via 3-player trios → pairwise Elo updates (K=32), seeded from consensus values. Manual tier/reorder saves pin Elo overrides.
2. **Candidate enumeration:** per opponent with rankings, nested loops over 1-for-1, 2-for-1, 1-for-2, 3-for-2 packages, pre-pruned to players where the *other* party values the asset ≥ 0.97× the owner's value. 1s/opponent deadline, 200k iteration cap, 30-candidate cap.
3. **Gates:** KTC-style package-value ratio ≥ fairness_threshold (exponential value curve on Sleeper `search_rank`, diminishing package weights 1.0/0.75/0.55/…); best-player user-Elo gap ≤ 250; "mutual gain" checks in raw Elo space.
4. **Score:** `composite = 0.70·min(mismatch, cap)/cap + 0.30·fairness(seed-Elo-sum ratio)`, × max-tier multiplier (1.60 elite … 0.35 bench), × flag-gated QB/star/clogger taxes.
5. **Loop:** Tinder-style like/pass → exact-mirror like detection (90-day window) → mutual match → accept/decline disposition; decisions feed back into Elo at K=8/4/20.

The core product insight — exploiting *divergent personal valuations* between two real league-mates so **both** sides perceive a win — is sound and is the moat vs. one-sided calculators (KTC etc.). The problems are in the math that implements it.

---

## 2. Issues found (ranked by impact)

### P0-1 · Multi-player trades are mathematically unreachable
`trade_service.py:1141` (2-for-1), `:1197` (1-for-2), `:1260-1263` (3-for-2).

The mutual-gain gates **sum raw Elo ratings** as if they were values:

```python
combined_give_user = user_elo[g1] + user_elo[g2]   # ~2400–3600
if recv_user <= combined_give_user * 0.95:          # recv_user ≤ ~1900 always
    continue
```

Elo lives on an interval scale centered at 1500 (practical range ~1200–1850). Two players always sum to ≥ ~2400; no single player approaches 0.95× that. **Every 2-for-1, 1-for-2, and 3-for-2 candidate is filtered out, in all realistic data.** The engine has only ever been able to surface 1-for-1 trades; the package-weight config, star tax, and roster-clogger tax mostly act on code paths that never produce cards. (Runtime repro pending — Bash sandbox was down during this review — but the bound is arithmetic, not empirical.)

**Fix:** convert Elo → value through a monotone curve *before* any package math, e.g. reuse the existing exponential: `v(p) = ktc_max · exp(−k · rank_in_user_elo_order(p))`, or calibrate `v = exp(elo/τ)`. Then compare `package_value()` (with the diminishing weights) on both sides in both users' value spaces.

### P0-2 · "Mutual gain" doesn't actually require mutual gain
`_mismatch_score` returns `opp_surplus + user_surplus` and callers check the **sum** > 0. A trade with user_surplus = −50, opp_surplus = +200 passes. Combined with the 0.97 pre-prune fallback (full roster when <5 candidates), one-sided cards can surface.

**Fix:** require `min(user_surplus, opp_surplus) > 0` and *rank* by `min(·,·)` (or a concave combination). The min-objective is also what behavioral research says maximizes acceptance: both sides face an endowment effect (WTA ≈ 2×WTP, Kahneman/Knetsch/Thaler 1990; loss-aversion λ≈2.25, Tversky & Kahneman 1992), so the binding constraint is the *less-happy* side, not the total.

### P1-3 · Three inconsistent value spaces
- Mutual gain: raw Elo differences (user-specific, interval scale)
- Fairness: ratio of **summed seed Elos** — the 1500 baseline dominates, compressing all ratios toward 1 (elite 1790 vs bench 1250 → fairness 0.70, barely below the default 0.75 gate). The score adds almost no discrimination; the KTC gate does the real work.
- KTC gate: `search_rank` → exponential value (a *third* scale, global not user-specific)

**Fix:** one canonical value transform applied to (a) user Elo, (b) opponent Elo, (c) consensus/seed Elo. Surplus, fairness, and gates all computed in that single value space.

### P1-4 · Dead code: outlook and positional-preference multipliers never run
`team_outlook_multiplier` and `positional_preference_multiplier` are defined but **never called** anywhere in the live tree (verified by repo-wide grep; only an abandoned worktree wired them up). Team outlook currently affects *only* job-cache freshness and a card label. `docs/architecture.md` line 71 incorrectly documents them as active. Positional preferences act only as the hard filter inside `_generate_for_pair`.

**Fix:** rather than resurrecting the multipliers, fold outlook into valuation (see §4.3) — the DynastyProcess pattern: per-player `now_value` / `future_value` columns blended by outlook α. Update the architecture doc either way.

### P1-5 · No uncertainty modeling → the depth-trade bias the tier multipliers patch over
The config comment admits it: *"mismatch math favors players with high valuation variance (and depth tiers have more variance)"*. A player seen in 2 trios has noisy Elo; the engine reads noise as genuine valuation disagreement and builds trades on it. The tier multipliers (×1.60 elite … ×0.35 bench) are a symptom patch.

**Fix:** track per-player rating uncertainty (comparison count is already in `_compute_stats`). Either shrink personal Elo toward seed by `n/(n+n₀)` before computing surplus, or require divergence > z·σ to count. Glicko-2/TrueSkill would formalize this, but count-based shrinkage gets 90% of the benefit in 20 lines.

### P2-6 · `max_candidates=30` is an enumeration cutoff, not a top-K
Loops break after the *first* 30 candidates in roster order — not the best 30. Card quality silently depends on Sleeper roster ordering.

**Fix:** heap-based top-K, or pre-sort candidate players by |value divergence| so the loops visit high-promise pairs first (anchor-first search). Either preserves the time budget while making truncation principled.

### P2-7 · Match flow leaves acceptance on the table
- Mirror detection (`check_for_match`) requires **exact set equality** of both packages. Two cards that differ by a bench throw-in never match.
- The opponent's deck is generated independently — cards the counterparty *already liked* are not boosted to the top of the user's deck (the Tinder "likes you" queue is missing). This is the cheapest large win for match rate.
- A "like" nudges Elo (K=8) toward the received players, which mildly self-reinforces similar future cards.

### P3-8 · Smaller items
- `TradeCard.fairness_score` is assigned the composite, not the fairness value (`trade_service.py:1353`).
- Composite normalization caps (300/400/500) are arbitrary and saturate, flattening rank order among strong cards.
- QB tax penalizes *both* directions symmetrically, including the direction it claims to help; star tax + package weights double-penalize the same phenomenon.
- `match_context` (needs/surplus) is computed per pair but only feeds narrative text, never scoring.

---

## 2b. Additional findings (second pass — verified in code)

### P0-3 · Opponent valuations are *fabricated* for league-mates who never ranked
`server.py:236-243` (`_biased_elo_random`), wired at `server.py:4640`, `:4666`, `:4685`.

Every opponent is initialized with `elo_ratings = seed + random.uniform(-120, 120)` per player. `_run_trade_job` (`server.py:1155-1172`) then overwrites with real `member_rankings` **only for members who have them** (`load_member_rankings` requires just one saved ranking row — no confidence threshold, `database.py:2599-2660`). Everyone else keeps the RNG ratings.

Consequences:
- The eligibility filter in `generate_trades` (`if m.elo_ratings`) is **illusory** — always truthy, so "opponents with established rankings" includes everyone.
- For non-ranked opponents, the engine's core signal — *valuation disagreement* — is literally random noise (±120 Elo dwarfs `min_mismatch_score = 40`). Cards vs. those opponents are RNG-driven and reshuffle on every session re-init.
- These cards can essentially **never produce a mutual match** (the counterparty would have to rank, at which point real values replace the noise that motivated the card), so they silently dilute the deck and erode trust in "they undervalue X" claims.

**Fix options:** (a) exclude non-ranked opponents from disagreement-based generation; serve only consensus/need-based cards against them, labeled as such; (b) at minimum make the noise deterministic per (user, league) so cards stop reshuffling; (c) turn cold-start into a growth loop — "3 league-mates haven't ranked yet; invite them to unlock real trade matches."

### P1-9 · `fairness_score` never reaches clients — mobile has a dormant fairness meter waiting for it
`trade_card_to_dict` (`server.py:2752-2785`) serializes `mismatch_score` and `composite_score` but **not** `fairness_score`. Mobile (`mobile/src/api/trades.ts:54-59`, `mobile/src/components/TradeCard.tsx:100-107`) already normalizes and renders a fairness meter when the field is present — it is permanently hidden today. Fixing the P3-8 field bug *and* serializing the field lights up existing UI for free. (Web shows raw `mismatch_score` as "Match score" — a unitless number that means nothing to users.)

### P1-10 · Draft picks cannot appear in any trade
Generic pick pseudo-players (`server.py:703-749`) exist in the *rankable* pool with ids like `generic_pick_1_early`, but rosters passed to `generate_trades` are Sleeper player ids — picks are never on a roster, so no generated trade can include one. Side bugs: picks are created with `position` = RB/WR/TE/QB (for UI tab mixing), so `dynasty_value`'s `position == "PICK"` branch is dead code for them; their value flows from hard-coded `search_rank` (10/50/100/200). Any sweetener/pick-trade feature (§4.12) first requires mapping Sleeper's per-roster traded draft capital onto rosters.

### P2-11 · Engine test coverage is a single file
Only `backend/tests/test_trade_gen_prune.py` exercises `_generate_for_pair` (prune-equivalence only). Nothing tests `generate_trades`, the multi-player paths (consistent with P0-1 — they produce nothing to test), the gates, or scoring. The Tier-1 plan's test list is the right starting set.

### Confirmed mechanics (context for the fixes)
- Mirror matching is strict set-equality on both sides, 90-day like window (`database.py:2714-2760`); match → notifications both ways → accept/decline disposition at K=20 (`server.py:3374-3539`).
- Deck: 5 cards/opponent, global target ~30, 30-min job cache keyed (user, league, format), invalidated on ranking swipes and preference changes.
- Like/pass feeds personal Elo at K=8/4 (`server.py:2916-2972`) — a mild self-reinforcement loop on the very signal the generator reads.

---

## 3. What comparable systems do (external research)

*Verified online 2026-06-10 (second-pass session). Sources at the end of this section.*

| Domain | Mechanism (verified) | Takeaway for FTF |
|---|---|---|
| **KeepTradeCut** | Users rank **3 players Keep/Trade/Cut** → "adapted ELO algorithm" consolidates ~25.8M submissions into live values; standardized 12-team 0.5 PPR, separate 1QB/SF databases; attention-check "test KTCs" filter low-quality votes | FTF's trio-ranking mechanic is independently validated as the industry standard input — KTC built a business on exactly this interaction. Consider attention-check trios for data quality |
| **KTC Trade Calculator "Value Adjustment"** | Extra value is required from the side giving up **more players**; sized by the value gap, how much of a "stud" the top asset is, and the count of lesser pieces; reverse-engineered from "the player needed to even the trade" | Confirms package math must penalize quantity (diminishing returns) and scale the penalty with star quality — FTF's `package_value` weights are the right shape; the star tax double-counts it |
| **FantasyCalc** | Values fit by an optimization over **2.64M real league trades** (Σ side A ≈ Σ side B), refreshed multiple times daily; free public API (same one powering the site); per-league-setting customization | Gold standard for acceptance-calibrated values. FTF logs the equivalent training data (likes/dispositions). API is a drop-in upgrade over `search_rank` decay for the consensus scale |
| **DynastyProcess** | Published formula: `value = 10500 · e^(−0.0235 · FantasyPros_dynasty_ECR)`; coefficient explicitly tunable ("−0.0220 values depth more, −0.0250 values studs more"); open data on GitHub | Same curve family as FTF's `dynasty_value` — **but FTF's k=0.0126 is half as steep**, valuing depth ~3× richer at rank 100 than the industry reference. This flat curve is a plausible root cause of the depth-trade bias the tier multipliers patch. Recalibrate k during the value-space unification |
| **Reciprocal recommender systems (RECON, Pizzato et al., RecSys 2010; Palomares et al. 2020 survey)** | Two-sided matching (dating/jobs): compute each side's preference for the other, combine with the **harmonic mean** — deliberately biased toward the smaller value so asymmetric-interest pairs rank low. Mutual-match rate beats one-sided ranking | Direct academic blueprint for FTF's core ranking objective: score cards by harmonic mean (or min) of both sides' predicted satisfaction, not the sum. Identical conclusion to the endowment-effect argument, from an independent field |
| **VBD/VORP (Footballguys)** | Value = points over positional replacement | Value players against the *user's own roster replacement* — kills roster-clogger trades and surfaces need-filling ones without bolt-on multipliers |
| **Kidney exchange (Abraham/Blum/Sandholm, EC 2007)** | Barter clearing = max-weight vertex-disjoint cycles with a fixed max cycle length; NP-hard; solved at national scale by branch-and-price ILP; deployed for the Alliance for Paired Donation | Blueprint for 3-team trades. A 12-team league is microscopic vs. nationwide kidney pools — exact solves in milliseconds. No consumer fantasy tool offers this |
| **Top Trading Cycles (Shapley–Scarf 1974)** | Point at most-preferred good; execute cycles → Pareto-efficient core | The cycle-frame for multi-way Pareto improvements |
| **eBay Best Offer (Backus/Blake/Larsen/Tadelis, QJE 135(3) 2020)** | 25M+ bargaining sequences: ⅓ end in immediate agreement; the rest show reciprocal, gradual concession behavior and delayed (dis)agreement | Negotiations converge when openings are close and concessions feel reciprocal → surface trades *near* consensus-fair with visible give-and-take framing; expect counters, so fuzzy mirror matching (P2-7) matters more than exact mirrors |
| **Endowment effect (Kahneman/Knetsch/Thaler, JPE 1990 — verified: median WTA $5.25 vs WTP $2.25–2.75, ~2:1, trades collapse; Tversky/Kahneman 1992 — verified: λ = 2.25)** | Owners demand ~2× what buyers pay; losses weighted 2.25× gains | "Fair" trades get rejected; only perceived-surplus-on-both-sides trades clear. Maximize the *min* perceived surplus |
| **Consumer trade finders (FantasyPros My Playbook Trade Finder, FantasySP "Fair Trade Rating", Fantasy Nerds Trade Finder)** | All suggest "mutually beneficial" trades from **one consensus value scale + roster needs**; FantasySP explicitly optimizes "trades that will be accepted" via fairness assessment — but none ingest the counterparty's *personal* valuations, and none have a mutual opt-in (match) loop | FTF's two-sided personal-valuation + mutual-match design is genuinely differentiated. The competition's lever is need-fit on consensus values — which is exactly what FTF should fall back to for non-ranked opponents (P0-3) |
| **Deckbox (MTG), backpack.tf (TF2)** | Explicit have/want lists; matcher ranks counterparties by intersection | Per-player "I want him" toggles on league-mates' rosters → direct matcher edges, no inference needed |
| **Swap markets (PaperBackSwap)** | Points as numeraire to escape double-coincidence | Picks/FAAB are fantasy's currency — auto-suggest sweeteners to close near-miss trades |

**Sources:** [KTC FAQ](https://keeptradecut.com/frequently-asked-questions) · [KTC rankings](https://keeptradecut.com/dynasty-rankings) · [KTC trade calculator](https://keeptradecut.com/trade-calculator) · [FantasyCalc](https://fantasycalc.com/) · [FantasyCalc API walkthrough](https://www.fantasydatapros.com/fantasyfootball/blog/fantasycalc/1) · [DynastyProcess values](https://dynastyprocess.com/values/) · [DynastyProcess GitHub](https://github.com/dynastyprocess/data) · [RECON (ResearchGate)](https://www.researchgate.net/publication/221140972_RECON_A_reciprocal_recommender_for_online_dating) · [RECON model overview](https://bi4allconsulting.com/en/knowledgecenter/reciprocal-recommendation-systems-overview-of-the-recon-model/) · [Palomares et al. survey (arXiv 2007.16120)](https://arxiv.org/pdf/2007.16120) · [SIGIR 2020 reciprocal matching](https://dl.acm.org/doi/10.1145/3397271.3401420) · [Abraham/Blum/Sandholm EC'07 (CMU PDF)](https://www.cs.cmu.edu/~sandholm/kidneyExchange.EC07.withGrantInfo.pdf) · [ACM DOI](https://dl.acm.org/doi/10.1145/1250910.1250954) · [Backus et al. QJE 2020](https://academic.oup.com/qje/article-abstract/135/3/1319/5721265) · [NBER w24306](https://www.nber.org/papers/w24306) · [Endowment effect (Wikipedia)](https://en.wikipedia.org/wiki/Endowment_effect) · [KKT 1990 (Semantic Scholar)](https://www.semanticscholar.org/paper/350fda1ed1f795a3957d23bd6d7a69c7d833ec04) · [Prospect theory λ=2.25](https://en.wikipedia.org/wiki/Prospect_theory) · [FantasyPros Trade Finder](https://www.fantasypros.com/nfl/myplaybook/trade-finder.php) · [FantasyPros dynasty tools roundup](https://www.fantasypros.com/2026/05/best-dynasty-fantasy-football-trade-tools/) · [FantasySP Trade Analyzer](https://www.fantasysp.com/nfl_trade_analyzer/) · [Fantasy Nerds Trade Finder](https://www.fantasynerds.com/nfl/trade-finder)

---

## 4. Recommendations

### Tier 1 — Fix the current engine (days; do these regardless)
0. **Stop fabricating opponent values (P0-3).** Partition opponents: *ranked* (real `member_rankings`) get disagreement-based generation; *non-ranked* get consensus/need-based cards only (seed-Elo both sides + roster-fit), labeled as such — or are excluded, with an "invite to rank" nudge in their slot. Remove `_biased_elo_random` from the trade path entirely. This is as foundational as the value-space fix: every metric in §5 is polluted while a random share of cards is RNG-driven.
1. **Single value space.** One transform `v = V(elo)` (reuse the exponential curve) applied to user/opponent/seed Elo. All surplus, fairness, and package math in value units. This *automatically un-breaks multi-player trades* (P0-1) and makes the fairness score meaningful (P1-3).
2. **True mutual gain.** Gate and rank on `min(user_surplus, opp_surplus)` in value units (P0-2).
3. **Confidence shrinkage.** Shrink personal values toward seed by comparison count before surplus math (P1-5). Then retune (likely shrink) the tier multipliers, which were compensating.
4. **Top-K selection** instead of first-30 enumeration; pre-sort by divergence (P2-6).
5. **Mechanical fixes:** `fairness_score` field bug; remove or wire the dead multipliers; update `docs/architecture.md`.

### Tier 2 — Model upgrades (weeks)
6. **Lineup-delta (marginal) valuation.** Value each asset as its contribution over the roster's replacement at that position, for *both* rosters: `marginal(p, roster) = max(0, v(p) − v(next-best at pos))` (+ small bench/depth term). One principled mechanism replaces the positional-preference filter, roster-clogger tax, and most of the needs logic — and `analyze_roster_strengths` already computes the inputs.
7. **Outlook as valuation blend.** `v_user = α·now_value + (1−α)·future_value` with α from outlook (championship→1.0 … jets→~0.2); age curves per position (RB cliff ~26, WR ~29, QB flat) instead of a single average-age threshold.
8. **"Likes you" boosting + fuzzy matching.** Inject cards the counterparty already liked at the top of the user's deck; relax mirror detection to package-similarity (e.g. Jaccard ≥ 0.8 on each side, or same core players ± one asset below a value floor). Likely the single biggest match-rate lever, and it's pure plumbing.
9. **Acceptance model.** Train logistic regression (later GBM) on accumulated like/pass + accept/decline data: features = both sides' surpluses, consensus delta, best-player tier gap, package sizes, positional-need fit, outlook alignment. Rank by `P(user likes) × P(opp accepts) × joint gain`. This *learns* the QB/star/clogger taxes instead of hard-coding them. FTF's data flywheel (every swipe is a label) is the long-term moat.

### Tier 3 — Rebuild the generator (the "new engine" to A/B)
10. **Optimization-based package construction.** Per opponent pair, replace nested loops with either:
    - **Knapsack-DP:** enumerate covetable receive-packages (1–2 opponent players ranked by user surplus), then DP the give side to hit the consensus-value band while minimizing the user's marginal-value loss; or
    - **Small ILP** (OR-Tools CBC): binary give/receive vars, maximize min-surplus, subject to fairness band, package-size limits, and post-trade lineup feasibility for both rosters. ~60 vars → milliseconds; all 11 opponents solved exactly inside the current 1s budget.
11. **3-team cycles.** Kidney-exchange clearing: nodes = (team, asset), edges where the receiver's value exceeds the giver's by δ; max-weight disjoint cycles of length ≤ 3 via ILP. No consumer tool offers this.
12. **Sweeteners.** For trades landing just below the fairness gate (0.60–0.75), search picks/FAAB to close the gap and present "add a 2027 3rd to make it work."
13. **Accepted-trade value fitting** (FantasyCalc method) over FTF's own accept/decline corpus once volume allows; until then, consider FantasyCalc's API as the consensus scale.

### Presentation (cheap, research-backed)
- Narratives should lead with the *receiver's* gain in the receiver's own terms (integrative framing), not a value ledger.
- Optionally tilt displayed consensus fairness slightly toward the opponent (their side shows a small visible surplus) — the spread idea from market makers; counteracts the endowment effect.
- **Serialize `fairness_score`** (post-fix) in `trade_card_to_dict` — mobile's fairness meter is already built and waiting (P1-9). Replace web's raw "Match score N" with the same normalized meter; unitless Elo sums mean nothing to users.

---

## 5. Test-before-ship plan

1. **Offline replay (first, free):** rerun historical sessions through the new scorer; measure AUC / precision@5 against recorded likes, and what fraction of historically *matched* trades the new engine would have ranked top-5. The swipe log (`trade_decisions`) is already the labeled dataset.
2. **Shadow mode:** generate cards from both engines per job; serve old, log new side-by-side with rank deltas. Zero user risk.
3. **A/B by league:** flag-gate the new engine per league (infrastructure exists: `config/features.json` + `model_config`). Primary metrics, in order: **mutual-match rate per active user**, accept rate per match, like rate per card shown, multi-player-card share, time-to-first-match.
4. **Guardrails:** card generation p95 latency ≤ current; no league with 0 cards that previously had >0.
