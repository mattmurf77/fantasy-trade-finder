# Research notes — decision engines in lending, matching and low-latency serving

Gathered 2026-11-10 by three research agents for [recommendation.md](recommendation.md).
This supplements, and does not repeat, the three-round corpus in
[docs/research/matchmaking/](../../research/matchmaking/README.md). **Research, not decisions.**

Confidence marks: **[V]** read in the primary source or its abstract; **[S]** secondary
source only; **[U]** not verified. Claims without a mark are the agents' own reasoning.

## A. Lending and risk decision engines

None of Upstart, Affirm, Klarna, Capital One or Zest publish decision-engine internals; what
exists is filings, trade press and secondary write-ups.

**Offline vs online**
- Batch features into a key-value store; stream only fast-moving ones (Uber Michelangelo:
  batch → Cassandra, Kafka → Flink aggregates to online store and Hive). [S]
  <https://www.uber.com/en-VN/blog/palette-meta-store-journey>
- Define a feature once for training and serving and check they match: Airbnb Chronon logs
  each live fetch and replays it through the backfill. [V]
  <https://medium.com/airbnb-engineering/chronon-a-declarative-feature-engineering-framework-b7b8ce796e04>
- Pre-approval pools: the lender fixes criteria in advance, the bureau builds the list, and
  criteria may not change when the consumer responds. [V]
  <https://www.experian.com/blogs/ask-experian/what-is-a-firm-offer-of-credit/>

**Engine structure**
- Rules wrap the model: Stripe Radar blocks by default and lets merchants add allow/block
  rules around the score. [V] <https://docs.stripe.com/radar/risk-evaluation>
- Expected value = take-up probability × value: loan pricing fits logistic price-response
  curves and picks the rate maximising expected profit. [V]
  <https://orion.journals.ac.za/pub/article/download/160/435>
- Monotonic and interaction constraints on credit GBMs so reason codes stay coherent. [V]
  <https://arxiv.org/pdf/2204.12365>
- Calibration (Platt/isotonic on held-out data): general practice; **no lending primary
  source found**. It matters when two probabilities are multiplied.

**Evaluation**
- Champion/challenger on a small slice, one change at a time (FICO). [V]
  <https://www.fico.com/blogs/adaptive-control-champion-challenger>
- Shadow models log scores without deciding; promotion requires meeting the latency SLA
  (PayPal [S, post returned 403], Nubank [V]).
  <https://building.nubank.com/practices-to-scale-machine-learning-operations/>
- Counterfactual evaluation: weight by the probability a decision was shown/overridden and
  inject some randomness in production (Stripe). [V]
  <https://de.slideshare.net/MichaelManapat/counterfactual-evaluation-of-machine-learning-models>

**Latency**
- One model call under ~100 ms over precomputed network-wide features (Stripe Radar). [V]
  <https://stripe.dev/blog/how-we-built-it-stripe-radar>
- Cascades with early exit: cheap stages settle most traffic. [S]

**Cold start**
- Empirical-Bayes shrinkage toward a segment prior, weighted by evidence. [S]
- Track the share of decisions served by the fast path (Upstart reports 91% of loans fully
  automated in 2025). [V]
  <https://www.sec.gov/Archives/edgar/data/1647639/000164763926000027/upst-20251231.htm>

## B. Two-sided matching, reciprocal recommendation and bargaining

**Scoring mutual acceptance**
- Harmonic mean is the reciprocal-recommender default; arithmetic and geometric means did
  worse; the cross-ratio uninorm matched or slightly beat it (Palomares, Pizzato et al.,
  *Information Fusion* 2021). [V] <https://arxiv.org/abs/2007.16120>
- The aggregator is a parameter to tune against accept data (Neve & Palomares, RecSys 2019).
  [S] <https://dblp.org/rec/conf/recsys/NeveP19.html>
- Model a match as P(A acts) × P(B replies); ranking by one side's relevance crowds everyone
  onto the same counterparties. Welfare-optimal ranking: 1,199 expected matches vs 957
  (reciprocal) and 844 (naive) on dating data (Su, Bayoumi & Joachims). [V]
  <https://arxiv.org/abs/2106.01941>
- The one fantasy-trade paper with a two-sided objective (Parshall et al. 2025) has no
  acceptance model. [V] <https://arxiv.org/html/2511.17535v1>
- ESPN/IBM trade assistant: pair teams by roster-strength dissimilarity, knapsack the
  players, post-process for parity; expert-rated quality 76.9% → 97.3% over 239M proposals;
  no acceptance labels reported. [V] <https://arxiv.org/abs/2111.02859>

**Inferring the passive side**
- Airbnb host acceptance: learn each host from accept/decline history, borrow strength from
  the region when sparse, demote low-acceptance results (+~3.75% booking conversion). [S —
  patent and secondary write-ups; the engineering post returned 403]
  <https://patents.google.com/patent/US10354206>
- Host rejections as explicit negatives in listing embeddings (Grbovic & Cheng, KDD 2018). [S]
- Revealed preference beats stated: two-sided matching from messaging behaviour raised
  first-contact replies by up to 45% (Tu, Ribeiro et al., WWW 2014). [V]
  <https://arxiv.org/abs/1401.8042>
- **Not found:** a published reciprocal system using Thompson sampling on the passive side.

**Funnel**
- LinkedIn Recruiter optimises a two-sided target (InMail accept), not recruiter clicks. [V]
  <https://arxiv.org/abs/1809.06473>
- Airbnb diversity re-ranking: independent per-item scores are wrong because similar items
  compete (Haldar et al., CIKM 2023). [V] <https://arxiv.org/abs/2210.07774>
- Batch rather than greedy matching (Uber). [V on the claim; numbers unverified]

**Thin barter markets**
- Optimise expected completed swaps, not planned ones; failure-aware matching roughly doubles
  expected transplants and long cycles fail as a whole (Dickerson, Procaccia & Sandholm,
  *Management Science* 2019). [V] <https://par.nsf.gov//servlets/purl/10120603>

**Bargaining**
- First offers anchor; extreme openers reduce settlement (Galinsky & Mussweiler, JPSP 2001).
  No quantified optimal point inside the zone of agreement was found. [V]
- Automated negotiation agents target the Nash product of gains. [V]
  <https://arxiv.org/abs/2512.06595>
- Endowment effect is strong in inexperienced traders and nearly absent in dealers (List,
  QJE 2003, sports-card show). [V]
  <https://econpapers.repec.org/RePEc:oup:qjecon:v:118:y:2003:i:1:p:41-71>
- **Not found:** fantasy-specific endowment evidence, or any peer-reviewed model predicting
  fantasy trade acceptance.

**Feedback**
- Feed position into the model in training and drop it out 15% of the time to separate
  position bias from relevance (Airbnb, KDD 2020). [V] <https://arxiv.org/abs/2002.05515>

## C. Low-latency serving and combinatorial search

**Cascades**
- Instagram Explore: retrieval → light two-tower ranker → heavy model on ~100 → rule-based
  rerank; item side precomputed daily, user side online. No latency numbers given. [V]
  <https://engineering.fb.com/2023/08/09/ml-applications/scaling-instagram-explore-recommendations-system/>
- Airbnb embedding retrieval chose a filter-friendly IVF index over HNSW because hard filters
  hurt graph-index latency. [S] <https://airbnb.tech/ai-ml/embedding-based-retrieval-for-airbnb-search/>
- Pinterest: one shared lightweight scorer across all candidate generators. [S]
- Etsy: real-time feature fetch is p99 40–50 ms, so features stay out of the hot path. [V]
  <https://arxiv.org/html/2306.04833v2>
- X/Twitter and DoorDash stage budgets: **not verified; do not cite.**

**Anytime results**
- Anytime algorithms trade deliberation time for quality; contract vs interruptible
  (Zilberstein, AI Magazine 1996). [V] <https://doi.org/10.1609/aimag.v17i3.1232>
- Tiered indexes answer most queries from a small top tier (Risvik et al., 2003). [V]
- Hedged requests ("The Tail at Scale"): barely applicable on one instance; the usable idea
  is serving a stale prepared answer when the live search misses its deadline. [U on numbers]

**Caching**
- Incremental view maintenance updates results from diffs; freshness is change-to-queryable
  time (Materialize). [V] <https://materialize.com/blog/freshness/>
- Component caches (independent sides cached separately, joined online) beat whole-result
  caches when any of many inputs can change.

**Combinatorial search**
- Meet-in-the-middle on sorted package sums (Horowitz & Sahni, JACM 1974). [V]
- Kidney-exchange clearing by column generation scales far better than constraint
  generation (Abraham, Blum & Sandholm, EC 2007). Relevant only beyond pairwise swaps. [V]
  <https://ttic.edu/blum/Papers/ec150abraham.pdf>
- Additive bounds for branch-and-bound are admissible only if every non-additive term is
  bounded separately. (Agent's derivation; this is the property the page-first bound has to
  prove and the test suite audits exhaustively.)

**Python serving**
- Load once and share: `gc.freeze()` before fork keeps copy-on-write pages shared
  (Instagram). [V]
  <https://instagram-engineering.com/copy-on-write-friendly-python-garbage-collection-ad6ed5233ddf>
- Swap immutable snapshots by rebinding a reference; never mutate in place.
- Flask streaming via `stream_with_context`; whether Render's proxy buffers server-sent
  events is **not verified**.

**Parity**
- Approximate proposer, exact re-rank of the candidates (Faiss `IndexRefineFlat`). [V]
  <https://github.com/facebookresearch/faiss/wiki/Faiss-indexes>
- Reuse the same code in the fast and exact paths and measure skew (Google Rules of ML #29,
  #32, #37). [V] <https://developers.google.com/machine-learning/guides/rules-of-ml>
