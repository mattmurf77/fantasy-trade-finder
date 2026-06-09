# Trade Engine — External Research (verified, with sources)

*Date: 2026-06-09 · Companion to [`trade-engine-deep-dive.md`](trade-engine-deep-dive.md), whose §3 was written while web access was down. This doc replaces that section with verified findings and records the resulting amendments to the Tier 1–3 plans in [`docs/plans/`](../plans/).*

---

## 1. Fantasy trade calculators

### KeepTradeCut — crowdsourced Elo + a hidden package-adjustment formula
- Value generation is the same mechanism FTF uses: 3-player "Keep/Trade/Cut" forced rankings → pairwise comparisons → an "adapted Elo algorithm" over ~25M+ data points, projected onto an exponential value spectrum (top player pinned at 9999). They run **planted "test" matchups with one obvious answer** to filter low-quality voters. ([FAQ](https://keeptradecut.com/frequently-asked-questions))
- **Package adjustment (reverse-engineered):** each player in a trade gets a *raw adjustment* `p × [0.29·(p/v)^8 + 0.28·(p/t)^1.3 + 0.07·(p/(v+2000))^1.28]` where `p` = player value, `t` = best value in this trade, `v` = best value overall (≈9999). Raw adjustment ranges 10%–42.4% of player value; **a trade is "fair" when the sums of raw adjustments are equal**, not when raw values are. A 5000-value player carries only ~26% of the raw adjustment of a 9999 player → packages of mids are heavily discounted ("four quarters ≠ a dollar"). ([Javelin Fantasy Football deep-dive](https://www.javelinfantasyfootball.com/2022/09/30/how-the-ktc-adjustment/))

### FantasyCalc — values fit from ~1M real trades
- Each real multi-player trade is treated as a value constraint; a player's value sits in the middle of his implied trade values, with recency weighting, outlier (lopsided-trade) removal, and per-format regressions (SF/TEP/PPR/team count). Updated multiple times daily. ([FAQ](https://fantasycalc.com/frequently-asked-questions))
- **Roster-slot effect:** the side receiving more players is assumed to drop a waiver-level player (~rank-300, value ≈ 425), with the cost growing per extra player. The consolidation premium is otherwise already priced in by training on real trades.

### DynastyProcess — open-source curve + tunable depth
- Values = market/expert rank through an exponential decay with a **user-tunable "depth" slider** (steepness of starter→bench falloff). Rookie picks: blend of two GAM models, default 80/20; **future-year picks at 80%** of current-year. ([repo](https://github.com/dynastyprocess/apps-calculator), [pick values](https://dynastyprocess.com/blog/2019-02-14-2019pickvalues/))

### Dynasty Nerds DynastyGM, Sleeper, market practice
- DynastyGM is the closest commercial trade finder: league sync → power rankings + positional strength per team → "ideal trade partners" → proposed deals with **suggested pieces to bridge value gaps**. ([landing](https://www.dynastynerds.com/dynasty-gm-landing/))
- Sleeper has no native analyzer — just a Trade Block + "trade interest" hearts (a lightweight two-sided signal). ([Sleeper](https://support.sleeper.com/en/articles/4238825-welcome-to-a-new-trading-experience))
- Market rule of thumb: the side getting the best single player pays a **+10–30% premium**; consolidation buyers target ≈ −15% on package value. ([UTH Dynasty](https://uthdynasty.com/dynasty-trade-calculator/))

## 2. Reciprocal recommenders (both sides must say yes)

- **RECON** (dating): combine the two directional preference scores with the **harmonic mean** — (0.1, 0.9) → ≈0.18, vs arithmetic 0.5 — punishing asymmetry. Two-sided matching improved successful-match rates by **up to ~45%**. ([arXiv 1501.06247](https://arxiv.org/abs/1501.06247))
- **OkCupid** uses the geometric mean of the two directional scores. ([AMS blog](https://blogs.ams.org/mathgradblog/2016/06/08/okcupid-math-online-dating/))
- **Hinge "Most Compatible"**: modified **Gale–Shapley** over learned like/pass models, refreshed daily; those picks convert **8×** better. ([Cornell Networks](https://blogs.cornell.edu/info2040/2021/09/30/hinge-and-its-implementation-of-the-gale-shapley-algorithm/))
- **Su, Bayoumi & Joachims (WWW '22):** ranking purely by local reciprocal relevance is **suboptimal under limited capacity** — jointly optimize the market's rankings for expected total matches; don't show the same popular item to everyone. ([arXiv 2106.01941](https://arxiv.org/abs/2106.01941))
- **Airbnb**: ranks partly by a learned **host-acceptance-probability** model; host rejections are negative training samples. The canonical production "rank by P(both sides say yes)". ([KDD '18](https://dl.acm.org/doi/10.1145/3219819.3219885))

## 3. Matching markets / kidney exchange

- **Abraham, Blum & Sandholm (EC '07):** barter clearing = max-weight cycle cover, **cycle length ≤ 3**, ILP/branch-and-price at national scale. At 12-team league scale, brute force suffices. ([ACM](https://dl.acm.org/doi/10.1145/1250910.1250954))
- **Top Trading Cycles (Shapley–Scarf 1974):** point at most-preferred good, execute cycles → unique core allocation, strategy-proof. The "no better deal exists for this player elsewhere in the league" framing is also persuasive UI copy. ([overview](https://en.wikipedia.org/wiki/Top_trading_cycle))

## 4. Sports trade machines

- **ESPN NBA Trade Machine:** binary validity gating (CBA salary-matching rules) with the **failure reason and what would fix it** — not value scoring. ([Trade Machine](https://www.espn.com/nba/trademachine))
- **BaseballTradeValues:** surplus value with published **low/median/high ranges per player**; the simulator accepts a trade when the sides' **ranges overlap** — fairness as a *band*, not a point. ([valuation notes](https://www.baseballtradevalues.com/articles/notes-on-our-valuations))

## 5. Acceptance modeling in swipe interfaces

- **Tinder** retired pure Elo for a contextual swipe-right-probability model incorporating mutual-interest rates. ([explainer](https://www.swipestats.io/blog/tinder-algorithm))
- **Thompson sampling / contextual bandits** are the standard tool for small candidate pools and cold-start — Beta posteriors over acceptance probability, sample to order the deck. ([arXiv 1405.7544](https://arxiv.org/pdf/1405.7544))
- Curiosities: GA-based fantasy trade optimizer with playoff biasing ([arXiv 2511.17535](https://arxiv.org/pdf/2511.17535)); granted patent on a fantasy trade evaluator ([US 8,340,794](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/8340794)).

---

## 6. Amendments to the Tier 1–3 plans

Data reality check (live DB, 2026-06-09): **3 users (1 real), 20 trade decisions (12 like / 8 pass), 4 matches (1 accepted), 2,441 member_rankings rows (1,149 from the one real user).** Anything labeled "learned" has no training data yet.

| # | Amendment | Affects |
|---|---|---|
| A1 | **Rank by harmonic mean of the two sides' surpluses** (RECON evidence) instead of bare `min(·,·)`; keep the `min ≥ θ` gate. Harmonic mean preserves the "binding side" logic with a citable, smoother objective. | Tier 1 Change 3 |
| A2 | **Calibrate `package_value` against KTC's raw-adjustment formula** (or adopt it outright in value space): per-asset weight `(p/v_max)^k`-style rather than fixed 1.0/0.75/0.55 positional weights. Validates and sharpens the diminishing-returns mechanism. | Tier 1 Change 2 |
| A3 | **Add a waiver/roster-slot cost** to the side receiving more players (FantasyCalc: ≈ value-425 per extra slot). Replaces most of the clogger tax with one principled term, available in Tier 1 (doesn't need marginal valuation). | Tier 1 / Tier 2 2.1 |
| A4 | **Fairness as range overlap, not a point band** (BaseballTradeValues): derive per-player value ranges from comparison count + vote disagreement (the same data Tier 1's shrinkage uses); accept when ranges overlap. High-uncertainty players (rookies) pass more easily — they're also the most-traded assets in real dynasty leagues. | Tier 1 Change 4 |
| A5 | **Defer the learned acceptance model (2.4)** until label volume exists (hundreds of decisions, not 20). In its place, ship **Thompson sampling** over Beta posteriors of like-rate per card-feature bucket — works at n≈0, prevents the deck from showing the same 3 trades forever, and *generates* the exploration data 2.4 needs. | Tier 2 2.4 |
| A6 | **Deck diversification across the league** (Joachims): when generating all members' decks, cap how many decks feature the same target player — saturating everyone's queue with one stud mathematically limits total possible matches. | Tier 2 (new) |
| A7 | **Vote quality control** (KTC): occasionally insert a trio with one objectively right answer; downweight rankings from users who fail. Protects the core signal as user count grows. | Ranking flow (new, small) |
| A8 | **"Bridge the gap" UX for near-miss trades** (Trade Machine + DynastyGM): when a candidate fails the fairness gate, surface the failure reason and the sweetener that fixes it. Confirms Tier 3 3.4 and argues for pulling a simple version earlier. | Tier 3 3.4 |
| A9 | **Likes-you mirror boosting confirmed as the biggest match lever** (Hinge 8×, Sleeper trade interest). Raises Tier 2 2.3's priority to first-in-line. | Tier 2 2.3 |
| A10 | **Future pick valuation:** when picks become tradeable (deep-dive P1-10), value future-year picks at ~80% of current-year (DynastyProcess). | Tier 3 |
