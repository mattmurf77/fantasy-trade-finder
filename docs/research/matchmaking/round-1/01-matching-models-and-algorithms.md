# Matching Models and Algorithms in Dating/Matchmaking Services

> Research memo — Round 1, Topic 01. How dating apps (and adjacent two-sided matchers) build their core recommendation/ranking/matching algorithms. Companion memos cover signals/features and marketplace dynamics; this one stays on the algorithms themselves.
>
> **Date:** 2026-08-15
> **Confidence legend used throughout:** `[official]` = company statement, engineering blog, or peer-reviewed paper by the company; `[academic]` = peer-reviewed literature, usually on real dating-site data; `[reported]` = credible journalism quoting the company; `[reverse-engineered]` = third-party inference, SEO blogs, teardown speculation — treat as directional only.

---

## Table of contents

1. [Executive summary](#executive-summary)
2. [System-by-system: what each service actually runs](#system-by-system)
3. [The reciprocal recommendation problem, formally](#the-reciprocal-recommendation-problem-formally)
4. [Algorithm families](#algorithm-families)
5. [Pipeline architecture: retrieval → ranking → re-ranking](#pipeline-architecture)
6. [Cold start at the algorithm level](#cold-start-at-the-algorithm-level)
7. [Best practices](#best-practices)
8. [Antipatterns](#antipatterns)
9. [What matters most](#what-matters-most)
10. [What doesn't matter (even though it seems like it should)](#what-doesnt-matter)
11. [Transfer notes for a two-sided trade matcher](#transfer-notes)
12. [Not researched / follow-up topics](#not-researched--follow-up-topics)
13. [Sources](#sources)

---

## Executive summary

Three findings dominate everything below:

1. **Every serious matchmaker converged on modeling BOTH directions of preference and fusing them.** RECON (2010) proved recommending for reciprocity beats recommending for one-sided taste; Hinge's Most Compatible (Gale-Shapley over learned mutual preferences) produced an 8x lift in real-date conversion over its ordinary feed; OkCupid's match percentage is literally a geometric mean of two directional satisfaction scores. The single highest-leverage design decision is *how* you fuse P(A→B) and P(B→A) — and the literature's consensus fusion is the **harmonic mean**, precisely because it punishes asymmetry (one thrilled party + one lukewarm party ≈ no match).

2. **Naive score-product reciprocity has a documented failure mode: congestion/popularity bias.** If you rank every user's feed by P(A likes B)×P(B likes A), the globally desirable candidates appear at the top of *everyone's* list, they get flooded, and total system-wide matches fall well below optimum. The 2023-era fix is to treat recommendation as a **market-wide allocation problem** (transferable-utility matching, optimal-transport-flavored methods) that maximizes *total* matches rather than each user's local best.

3. **Elo-style scalar desirability scores are an abandoned technology.** Tinder built its empire on Elo, then publicly killed it in 2019 ("Elo is old news… an outdated measure") in favor of a dynamic engagement-driven system seeded by TinVec-style swipe embeddings. The lesson isn't that global quality scores are useless — it's that a *single scalar* collapses taste into popularity, and pairwise/embedding models strictly dominate it.

---

## System-by-system

### Tinder: Elo → TinVec embeddings → "dynamic" engagement system

**The Elo era (2012–2019)** `[official, retrospective]`. Tinder's original ranking assigned each user a hidden desirability score using the Elo rating system from chess. Every swipe was treated as a game: if a high-scoring user swiped right on you, your score rose more than if a low-scoring user did — i.e., the standard Elo update `R' = R + K(S − E)` where the "expected outcome" E depends on the score gap between swiper and swipee. Users were then preferentially shown candidates in their own score band (assortative matching by desirability). This was confirmed by Tinder itself when it retired the system, and by years of credible reporting beforehand (Fast Company's 2016 interview coined the internal framing "desirability score"). Key properties worth noting:

- It is a **collaborative signal compressed to one dimension** — who likes you, weighted by how liked *they* are.
- It made the feed cheap to build (band matching = a range query, no per-pair scoring).
- It was widely gamed once understood (right-swipe rationing, reset accounts), which Tinder cited when killing it. ([Tinder pressroom, 2019](https://www.tinderpressroom.com/powering-tinder-r-the-method-behind-our-matching); [Engadget](https://www.engadget.com/2019-03-18-tinder-dumps-desirability-scores.html); [Global Dating Insights](https://www.globaldatinginsights.com/featured/tinder-changes-algorithms-and-removes-elo-scores/))

**TinVec (2017)** `[official — MLconf talk by Tinder Chief Scientist Steve Liu]`. Tinder's first published embedding system. Word2Vec's skip-gram idea transplanted to swipes: users a given swiper right-swipes in a session play the role of "words in the same sentence/context," so *co-liked users end up near each other in the embedding space*. Swipees become dense vectors that implicitly encode attributes nobody typed in (interests, environment, education, career), and recommendation becomes nearest-neighbor retrieval around the vectors a user has recently liked. This is collaborative filtering — no profile content needed — learned purely from the swipe graph. ([MLconf session](https://mlconf.com/sessions/personalized-user-recommendations-at-tinder-the-t/); [Liu's slides](https://www.slideshare.net/SessionsEvents/dr-steve-liu-chief-scientist-tinder-at-mlconf-sf-2017); [open-source reimplementation](https://github.com/CharlesGaydon/Dater-to-Vec))

**The current "dynamic system" (2019–)** `[official but vague]`. Tinder's 2019 statement: the system "continuously factors in how members are engaging" through Likes/Nopes and profile content; ranking updates propagate "within 24 hours or so" of your profile being Liked/Noped; the **most heavily weighted factor is recency/activity** — "we prioritize potential matches who are active, and active at the same time"; it uses "anonymized cues from photos"; it explicitly does *not* use race, religion, income, or social status. Read together with the TinVec talk, the consensus interpretation `[reverse-engineered]` is: embedding-based candidate retrieval + an engagement-probability ranker + heavy activity/recency re-ranking. ([Tinder pressroom](https://www.tinderpressroom.com/powering-tinder-r-the-method-behind-our-matching); [SwipeStats teardown](https://www.swipestats.io/blog/tinder-algorithm), low confidence)

### Hinge: "Most Compatible" via Gale-Shapley stable matching

`[official + reported]` Launched July 2018. Mechanics, per Hinge and TechCrunch:

1. Hinge learns **directional preference models** from each user's like/pass/comment activity (implicit feedback — no questionnaire ranking).
2. Nightly, it runs a variant of the **Gale-Shapley deferred-acceptance algorithm** (Nobel-recognized 1962 stable-marriage solution) over users' predicted preference orderings to compute a *stable assignment* — a pairing where no two people would both rather be with each other than with their assigned match.
3. Each user gets ONE "Most Compatible" pick per day, and — crucially — **the pairing is symmetric**: CEO Justin McLeod: "the person that you're seeing is also seeing you, and this is the best pairing that we think that we can find."
4. For non-binary/non-heterosexual pools where the two-sided marriage formulation doesn't apply, Hinge uses the **stable roommates** variant (one common pool, no side division).

Reported result: users were **8x more likely to exchange numbers / go on dates** from Most Compatible than from ordinary feed recommendations. ([TechCrunch](https://techcrunch.com/2018/07/11/hinge-employs-new-algorithm-to-find-your-most-compatible-match-for-you/); [9to5Mac](https://9to5mac.com/2018/07/12/ai-dating-app-hinge/); [Scientific American on deferred acceptance in apps](https://www.scientificamerican.com/article/the-stable-marriage-problem-solution-underpins-dating-apps-and-school/))

Two caveats the coverage tends to skip `[academic critique]`: Gale-Shapley assumes complete, static preference orderings over the whole pool, which no app has — Hinge necessarily runs it over *predicted* preferences on a candidate subset, so "stability" is stability with respect to a model, not reality. And GS stability is proposer-optimal: the side that "proposes" gets its best stable outcome, the other side its worst — an asymmetry any implementer must consciously handle. ([arXiv matching-theory survey for dating](https://arxiv.org/pdf/2208.11384))

### OkCupid: explicit questionnaire math (fully public)

`[official — OkCupid published the math; best remaining writeups are third-party]` The only major service with a fully documented formula. Per-pair match percentage:

1. Each answered question carries the user's answer, the answers they'd **accept from a partner**, and an **importance weight**: Irrelevant = 0, A little important = 1, Somewhat important = 10, Very important = 50, **Mandatory = 250**.
2. For the set S of commonly answered questions, compute each direction's satisfaction:
   `sat(A←B) = (importance points A assigned to questions where B's answer is acceptable to A) / (total importance points A assigned over S)` — and symmetrically `sat(B←A)`.
3. **Match % = geometric mean of the two directional satisfactions**, i.e. `match(A,B) = sqrt(sat(A←B) × sat(B←A))` over n common questions (n-th root of the product in the general formulation). Example from OkCupid's own explainer: `sqrt(0.91 × 0.98) ≈ 94%`.
4. Subtract a **"reasonable margin of error"** based on n — with only a handful of common questions, the displayed match is capped low (2 common questions ⇒ ~50% cap). This deliberately shows "the lowest match percentage possible," pushing users to answer more questions to raise confidence.

The geometric mean is the load-bearing choice: it makes mutuality mandatory. Two people at 50%/50% score 50; a 0%/100% pair scores 0. ([AMS math grad blog](https://blogs.ams.org/mathgradblog/2016/06/08/okcupid-math-online-dating/); [HackerEarth writeup](https://www.hackerearth.com/practice/notes/okcupids-matching-algorithm-1/))

Known critique `[credible independent analysis]`: mandatory questions **inflate** scores because passing a dealbreaker check adds 250 points to both numerator and denominator — "someone doesn't become a great potential match simply because they're not a bigot." Proposed fix: dealbreakers should be **filters (negative-only)**, not positive score contributors. ([isomorphismes](https://isomorphismes.wordpress.com/2011/11/22/okcupid-whats-wrong-match-algorithm/); see also [JSTOR Daily](https://daily.jstor.org/dont-fall-in-love-okcupid/) on the weak evidence that the match % predicts real-world outcomes at all)

### eharmony: questionnaire benchmark models + ~20 ML "affinity" models

`[reported — CIO interview with eharmony engineering]` Two layers: (1) the classic **compatibility layer** — a 100+-item questionnaire scored against benchmarks derived from studying thousands of successful married couples (dimension-wise similarity models on traits like intellectual curiosity, ambition, kindness); (2) a **behavioral ML layer** added later — roughly 20 "Affinity" models learning from on-site behavior (who you click, who you message, what your self-description says) to personalize beyond the questionnaire. Infrastructure note: a daily Hadoop batch scores ~1B candidate pairs down to a handful of delivered matches per user per day, and ML even decides *how many* matches to send and *when*. This is the canonical "content/psychometric prior + behavioral posterior" hybrid. ([CIO](https://www.cio.com/article/206096/click-me-maybe-inside-eharmony-s-matchmaking-machine.html); [datingnews summary](https://www.datingnews.com/apps-and-sites/facts-about-eharmonys-algorithm/))

### Coffee Meets Bagel: item-based collaborative filtering on latent features

`[official — AWS engineering blog co-authored with CMB engineers]` CMB computes **latent features for all active users via batch matrix-factorization-style jobs**, then serves recommendations with item-based collaborative filtering over those latent vectors (Redis-backed). Their stated rationale is a finding worth quoting for any matcher: human-selected observable features (age, height, religion…) "are not the most powerful indicators for predicting high-quality matches" — the **learned latent features extracted from past match data are far more predictive**. ([AWS blog](https://aws.amazon.com/blogs/database/powering-recommendation-models-using-amazon-elasticache-for-redis-at-coffee-meets-bagel/))

### Bumble: undisclosed; behavior-shaped ranking

`[reverse-engineered — treat as low confidence]` Bumble denies using an Elo score and has published almost nothing. Teardowns consistently infer: profile-completeness gating, activity-weighted visibility, swipe-selectivity signals (indiscriminate right-swiping is penalized; a moderate right-swipe rate is treated as genuine intent), and CV/NLP profile-quality scoring. Useful mainly as evidence that *every* major app runs a visibility-ranking layer even when it denies "scores." ([DEV community teardown](https://dev.to/karim__sk/decoding-bumbles-algorithm-a-developers-guide-to-building-smart-matchmaking-systems-3ejh); [Photofeeler on algorithm myths](https://blog.photofeeler.com/dating-app-algorithms/))

### Adjacent two-sided matchers

- **LinkedIn Recruiter** `[official/academic]` — the clearest industrial statement of reciprocal objective outside dating: talent-search ranking is trained on **inMail-accept** events (recruiter reached out AND candidate accepted) — i.e., the label itself is mutual, not one-sided. Deep + representation-learning rankers replaced linear models; LinkedIn markets the outcome directly ("Recommended Matches candidates are up to 35% more likely to accept your InMail"). ([arXiv: Towards Deep and Representation Learning for Talent Search at LinkedIn](https://arxiv.org/pdf/1809.06473); [LinkedIn help](https://www.linkedin.com/help/recruiter/answer/a413241))
- **Job platforms** `[academic]` — the 2024 "Best-of-Both" paper (job-search data) is the best treatment of *when to fuse two directional models vs. train one direct match model*; details in §4. ([arXiv 2409.10992](https://arxiv.org/pdf/2409.10992))
- **Uber (Eats)** `[official]` — canonical two-tower reference implementation: query tower (user+context) and item tower trained so dot product predicts engagement; item embeddings precomputed offline into an ANN index; in-batch negatives with logQ correction (recall@500 89%→93%); one global model replaced thousands of per-city models. Not reciprocal — but the retrieval architecture is what dating apps use for candidate generation. ([Uber blog](https://www.uber.com/us/en/blog/innovative-recommendation-applications-using-two-tower-embeddings/))

---

## The reciprocal recommendation problem, formally

**One-sided recommendation** optimizes `P(user engages with item)`. Items have no veto.

**Reciprocal recommendation** (Pizzato et al.'s framing, now standard `[academic]`): both parties are simultaneously subject and object. A recommendation of y to x only succeeds if x acts AND y reciprocates. So the system must estimate two directional preferences and produce one bilateral score:

```
p(x→y) = P(x likes/contacts y)        (direction 1)
p(y→x) = P(y likes/responds to x)     (direction 2)
p(x↔y) = φ( p(x→y), p(y→x) )          (fusion / aggregation)
```

**Fusion functions φ actually used in the literature** ([RRS survey, arXiv 2007.16120](https://arxiv.org/pdf/2007.16120); [Springer: nature of reciprocal recommenders](https://link.springer.com/article/10.1007/s11257-012-9125-0)):

| φ | Formula | Behavior |
|---|---|---|
| Product | `p₁·p₂` | The literal `P(A likes B)×P(B likes A)`; assumes independence; drives popularity concentration (see Antipatterns) |
| Arithmetic mean | `(p₁+p₂)/2` | Too forgiving — one high side can carry a zero side |
| Geometric mean | `√(p₁·p₂)` | OkCupid's choice; zero if either side is zero |
| **Harmonic mean** | `2/(1/p₁ + 1/p₂)` | **The field's default.** Skews hard toward the *minimum* input — encodes "both must want it." RECON's choice and the most-replicated winner |
| Weighted mean, learned weights | `w·p₁+(1−w)·p₂`, w optimized | Kleinerman et al. 2018 — see below |

Key mathematical/practical differences from one-sided recommendation `[academic]`:

1. **The min matters more than the mean.** Success ≈ min(p₁,p₂) in practice, which is why harmonic mean (closest mean to the min) empirically wins over arithmetic ([survey](https://arxiv.org/pdf/2007.16120)).
2. **The two objectives partially conflict.** Kleinerman et al. (RecSys 2018) showed "very often the receiver is likely to contact users who are not likely to respond positively, and vice versa" — and that the optimal weighting between 'receiver will act' and 'candidate will reciprocate' is **not 50/50 and differs by user**; they learn per-context weights and validated on a live dating site ([ACM](https://dl.acm.org/doi/abs/10.1145/3240323.3240349)).
3. **Users are perishable, limited-capacity items.** A popular user recommended to everyone congests; an item recommended to everyone just sells more. This breaks the independence assumption in `p₁·p₂` at the system level ([TU-matching paper](https://arxiv.org/pdf/2306.09060)).
4. **Error compounds across two models.** The 2024 Best-of-Both paper identifies "biased error propagation between the two models" when directional predictors are trained independently then multiplied; direct match-label prediction avoids that but starves on label sparsity (matches are rare events). Their fix: train directional models, use them to generate dense **pseudo-match scores**, blend with sparse true match labels, train a meta-model on the blend ([arXiv 2409.10992](https://arxiv.org/html/2409.10992v2)).
5. **Asymmetric awareness is real.** On a large Chinese dating site (reciprocal CF study), men systematically overweighted their own preferences and underweighted their attractiveness to the other side; women weighted both. A good φ (or learned weights) absorbs this asymmetry; a naive product does not ([arXiv 1501.06247](https://arxiv.org/abs/1501.06247)).

---

## Algorithm families

### 1. Content-based reciprocal: RECON (the founding system, 2010)

`[academic — deployed on a major Australian dating site]` For each user x, build a preference model over discrete attribute values (age buckets, education, etc.) from x's *sent-contact history* (implicit feedback: whom did x contact, and what were their attributes). Compatibility of x with y = how well y's attributes satisfy x's learned preference distribution, and vice versa; the two directional supports are fused with the **harmonic mean**. Result: adding reciprocity roughly **doubled success rate at top-10** vs. the same recommender without the reciprocal term, and improved most for users the one-sided system served worst. ([ACM RecSys 2010](https://dl.acm.org/doi/10.1145/1864708.1864747); [Springer follow-up study](https://link.springer.com/article/10.1007/s11257-012-9125-0))

### 2. Reciprocal collaborative filtering (memory-based)

`[academic — Baihe (major Chinese dating site) data]` Xia et al.: define **interest similarity** (two users are similar if they message the same people) and **attractiveness similarity** (similar if the same people message them). Predict p(x→y) from neighbors, fuse bidirectionally. CF variants **substantially beat content-based** methods on precision/recall — profile text/attributes are weak compared to behavior. ([arXiv 1501.06247](https://arxiv.org/pdf/1501.06247); [WWW'14 companion study](https://dl.acm.org/doi/10.1145/2567948.2579240))

### 3. Latent-factor / matrix-factorization reciprocal: LFRR

`[academic — validated on Pairs (millions of users, Japan)]` Neve & Palomares (RecSys 2019): factorize **two preference matrices** (side1→side2 likes, side2→side1 likes) with SGD; `p(x→y) = u_x · v_y` from the first model, `p(y→x)` from the second; fuse (harmonic mean again performing best among tested operators). Scales where memory-based CF dies, and is essentially the minimum viable "modern" reciprocal recommender. ([ACM](https://dl.acm.org/doi/10.1145/3298689.3347026); [Semantic Scholar](https://www.semanticscholar.org/paper/805379f796810d2b2575f0d320aee383afd85f6f))

### 4. Embedding / deep approaches

- **TinVec** (above): skip-gram over swipe co-occurrence → user vectors → ANN retrieval `[official]`.
- **Two-tower models**: the industry-standard architecture for the retrieval stage — user tower and candidate tower co-trained so `dot(u_x, v_y) ≈ P(engagement)`; candidate embeddings precomputed into an ANN index. In a reciprocal setting you either (a) run two two-tower models (one per direction) and fuse, or (b) train on mutual-event labels directly (LinkedIn's inMail-accept approach). ([Uber](https://www.uber.com/us/en/blog/innovative-recommendation-applications-using-two-tower-embeddings/); [Snap](https://eng.snap.com/embedding-based-retrieval); [Shaped.ai deep dive](https://www.shaped.ai/blog/the-two-tower-model-for-recommendation-systems-a-deep-dive))
- **Image-based reciprocal (ImRec / "Photos Are All You Need")** `[academic]`: siamese/RNN networks on photo history alone predict bidirectional preference at F1 ≈ 0.87 on a large real dating dataset, beating both content-based and CF baselines — evidence that rich learned representations of "what each side responds to" can carry the whole reciprocal task ([arXiv 2108.11714](https://arxiv.org/pdf/2108.11714); [OpenReview ImRec](https://openreview.net/pdf?id=GOsmeVvSTGC)).
- **RRCN** `[academic]`: reinforced random convolutional network selecting "key attributes" for reciprocal dating recommendation — representative of the deep-attribute-interaction branch ([arXiv 2011.12586](https://arxiv.org/pdf/2011.12586)).

### 5. Matching-theory / allocation approaches (the current frontier)

`[academic — includes industry authors from Japanese dating platforms]` Instead of scoring pairs independently, solve for the **assignment** that maximizes expected total matches under capacity constraints:

- **Gale-Shapley / stable matching** (Hinge, production): guarantees no blocking pairs w.r.t. predicted preferences; naturally one-recommendation-per-user-per-round; but needs predicted full orderings and inherits proposer-side optimality ([SciAm](https://www.scientificamerican.com/article/the-stable-marriage-problem-solution-underpins-dating-apps-and-school/); [arXiv 2208.11384 — matching-theory RS in online dating](https://arxiv.org/pdf/2208.11384)).
- **Transferable-utility (TU) matching for ranked feeds** — Tomita et al., RecSys 2023: formulates feed construction as a market equilibrium so exposure of popular users is *priced*; their examination-agnostic algorithm beats or ties score-fusion baselines on **total system matches** and scales to datasets where prior market-based methods failed; evaluated on a real Japanese dating platform ([arXiv 2306.09060](https://arxiv.org/abs/2306.09060); [ACM](https://dl.acm.org/doi/10.1145/3604915.3608774)).
- **Online/bandit variants**: sequential reciprocal recommendation with theoretical guarantees ([arXiv 1806.01182](https://arxiv.org/pdf/1806.01182)); contextual bandits with argumentation-based explanations for RRS ([Springer](https://link.springer.com/article/10.1007/s11280-023-01173-z)); off-policy evaluation for matching markets ([arXiv 2507.13608](https://arxiv.org/pdf/2507.13608)); counterfactual RRS ([arXiv 2508.01867](https://arxiv.org/html/2508.01867)).

---

## Pipeline architecture

Every at-scale matcher follows the same three-stage funnel `[official/industry-standard]` ([Google ML rec-systems course](https://developers.google.com/machine-learning/recommendation/dnn/re-ranking); [Aman.ai re-ranking notes](https://aman.ai/recsys/re-ranking/); [Superlinked overview](https://superlinked.com/glossary/introduction-to-recommendation-systems)):

1. **Candidate generation (retrieval)** — cheap, recall-oriented: cut the full pool to hundreds/thousands via hard filters (distance, age prefs, dealbreakers) + ANN search over embeddings (two-tower / TinVec-style). eharmony's version: Hadoop batch over ~1B pairs/day.
2. **Ranking (scoring)** — expensive, precision-oriented: a learned model scores each retrieved candidate with full pairwise features. In dating this is where the *reciprocal* score lives: two directional predictors + fusion, or a direct mutual-event model (LinkedIn's inMail-accept). Learning-to-rank formulations (pairwise/listwise) apply here exactly as in search ([LinkedIn talent search paper](https://arxiv.org/pdf/1809.06473)).
3. **Re-ranking (policy layer)** — business rules and system health: activity/recency boosts (Tinder's dominant factor), exposure caps on popular profiles (congestion control), diversity injection, freshness for new users, one-per-day constructs (Hinge's Most Compatible, CMB's daily bagels).

The stage split matters because **reciprocity is cheap to respect at ranking time but expensive at retrieval time** — most systems retrieve one-sidedly (who would *you* like) and apply the mutual model only to the shortlist; the matching-theory work (§4.5) is precisely about pushing reciprocity/congestion awareness up into the allocation itself.

---

## Cold start at the algorithm level

`[academic + official practice]`

- **Content prior → behavioral posterior.** Every hybrid system (eharmony, RECON-style) starts new users on declared attributes/questionnaires and hands over to behavioral models as swipes accumulate. RECON's preference model needs only a handful of sent contacts to become useful.
- **Community/cluster assignment.** For reciprocal cold start specifically: assign the new user to a behavioral community (via profile similarity to existing members), then recommend people *who historically replied to that community* — directly optimizing the reciprocal direction you have zero data for ([Springer: community-based reciprocal cold start](https://link.springer.com/chapter/10.1007/978-3-319-78196-9_10)).
- **Bandit exploration.** Contextual bandits / UCB variants intentionally spend early impressions to localize the new user in preference space ([arXiv 1405.7544](https://arxiv.org/pdf/1405.7544); [Hellinger-UCB, arXiv 2404.10207](https://arxiv.org/pdf/2404.10207)).
- **New-user boost** `[reported/reverse-engineered]`: Tinder-family apps give fresh profiles a temporary visibility boost — both a growth tactic and a data-acquisition strategy (rapid preference localization).
- **Honest uncertainty.** OkCupid's margin-of-error cap (display the *lower confidence bound* of the match score until enough common questions exist) is cold-start handling on the *pair* level — a directly reusable pattern.

---

## Best practices

1. **Model both directions, fuse with a min-skewed operator.** RECON's harmonic-mean fusion roughly doubled top-10 success versus one-sided ranking on a live dating site ([RECON](https://dl.acm.org/doi/10.1145/1864708.1864747)); the RRS survey confirms harmonic mean as the most-replicated best default because it "provide[s] aggregated results closer to the minimum of its inputs" ([survey](https://arxiv.org/pdf/2007.16120)). OkCupid independently converged on the geometric mean for the same reason ([AMS](https://blogs.ams.org/mathgradblog/2016/06/08/okcupid-math-online-dating/)).
2. **When you have real mutual-outcome labels, train on them.** LinkedIn trains talent-search ranking on inMail *accepts* (mutual event), not sends ([arXiv 1809.06473](https://arxiv.org/pdf/1809.06473)). Best-of-Both shows the strongest results come from blending direct match-label prediction with directional-model pseudo-labels ([arXiv 2409.10992](https://arxiv.org/pdf/2409.10992)).
3. **Learn behavioral/latent representations instead of hand-picked attributes.** CMB states outright that observable features underperform latent features mined from past match data ([AWS/CMB](https://aws.amazon.com/blogs/database/powering-recommendation-models-using-amazon-elasticache-for-redis-at-coffee-meets-bagel/)); TinVec encodes taste no form field captures ([MLconf](https://mlconf.com/sessions/personalized-user-recommendations-at-tinder-the-t/)); photos-only deep models beat attribute systems ([arXiv 2108.11714](https://arxiv.org/pdf/2108.11714)).
4. **Use the three-stage funnel with reciprocity applied at ranking, allocation applied at re-ranking.** Retrieval one-sided and cheap (ANN over embeddings — Uber-style two-tower serving: offline item embeddings + online query embedding, [Uber](https://www.uber.com/us/en/blog/innovative-recommendation-applications-using-two-tower-embeddings/)), mutual scoring on the shortlist, congestion/diversity control last ([Google](https://developers.google.com/machine-learning/recommendation/dnn/re-ranking)).
5. **Present the top mutual pick as a scarce, symmetric event.** Hinge's Most Compatible: one stable-matched pairing per day, shown to *both* parties simultaneously — 8x conversion lift. The scarcity and the symmetry are part of the algorithm's effectiveness, not just UX garnish ([TechCrunch](https://techcrunch.com/2018/07/11/hinge-employs-new-algorithm-to-find-your-most-compatible-match-for-you/)).
6. **Treat dealbreakers as filters, not score components.** The documented OkCupid flaw: mandatory-question points inflate match scores for merely-acceptable candidates. Hard constraints belong in retrieval-stage filtering; scores should differentiate among the survivors ([isomorphismes](https://isomorphismes.wordpress.com/2011/11/22/okcupid-whats-wrong-match-algorithm/)).
7. **Weight the two directions asymmetrically, and learn the weights.** Kleinerman et al.: likelihood-to-act and likelihood-to-reciprocate genuinely conflict; a learned weighted fusion beat fixed 50/50 on a live dating site ([ACM RecSys 2018](https://dl.acm.org/doi/abs/10.1145/3240323.3240349)). The Baihe study's gender asymmetry (one side ignores its own attractiveness to the other) is the behavioral reason why ([arXiv 1501.06247](https://arxiv.org/abs/1501.06247)).
8. **Weight activity/recency heavily.** Tinder says the strongest factor is being "active, and active at the same time" — a match suggestion to a dormant counterparty is a wasted recommendation and a bad user experience ([Tinder pressroom](https://www.tinderpressroom.com/powering-tinder-r-the-method-behind-our-matching)).
9. **Display calibrated uncertainty on pair scores.** OkCupid's lower-bound display (margin of error shrinking with common questions) both protects trust and creates an incentive loop for more preference data ([AMS](https://blogs.ams.org/mathgradblog/2016/06/08/okcupid-math-online-dating/)).
10. **Explain reciprocal recommendations two-sidedly.** RecSys 2018 work on reciprocal explanations found explanations must cover *why you'd like them AND why they'd like you*; one-sided explanations underperform in reciprocal domains ([ACM](https://dl.acm.org/doi/10.1145/3240323.3240362)).

## Antipatterns

1. **Scalar global desirability scores (Elo).** Collapses multidimensional taste into popularity; produces assortative "leagues"; is gameable; and was publicly abandoned by its most famous user — "Elo is old news… an outdated measure" ([Tinder](https://www.tinderpressroom.com/powering-tinder-r-the-method-behind-our-matching); [Engadget](https://www.engadget.com/2019-03-18-tinder-dumps-desirability-scores.html)). Note the subtlety: Elo-like *popularity* information still exists implicitly inside any behavioral model; the antipattern is making it the ranking key.
2. **Naive `P(A→B)×P(B→A)` ranked greedily per user.** Three documented failure modes: (a) **congestion/popularity concentration** — globally attractive users top everyone's list, get flooded, response rates crater, and total matches fall short of what market-aware allocation achieves ([arXiv 2306.09060](https://arxiv.org/abs/2306.09060)); (b) **independence violation** — P(B reciprocates) is not independent of how many other recommendations B just received; (c) **compounded model error** — two independently trained directional models propagate bias into the product ([arXiv 2409.10992](https://arxiv.org/html/2409.10992v2)).
3. **Arithmetic-mean fusion.** Lets one enthusiastic side carry a near-zero other side into the feed — exactly the outcome reciprocal systems exist to prevent; consistently loses to harmonic mean in the literature ([survey](https://arxiv.org/pdf/2007.16120)).
4. **Scoring dealbreakers positively** (OkCupid's mandatory-question inflation — §2, [isomorphismes](https://isomorphismes.wordpress.com/2011/11/22/okcupid-whats-wrong-match-algorithm/)).
5. **Trusting questionnaire similarity as an outcome predictor.** Psychology research reviewed by JSTOR Daily/HDSR finds stated-preference similarity scores are weak predictors of real-world relationship success; behavioral data repeatedly dominates stated data ([JSTOR Daily](https://daily.jstor.org/dont-fall-in-love-okcupid/); [HDSR overview](https://hdsr.mitpress.mit.edu/pub/i4eb4e8b)).
6. **Applying textbook Gale-Shapley uncritically.** It assumes complete static rankings, balanced sides, and ignores that model-predicted "stability" ≠ satisfaction; proposer-optimality silently favors one side. Hinge's adaptations (predicted preferences, stable-roommates variant for non-binary pools, one match/day cadence) are the necessary engineering around those gaps ([arXiv 2208.11384](https://arxiv.org/pdf/2208.11384); [TechCrunch](https://techcrunch.com/2018/07/11/hinge-employs-new-algorithm-to-find-your-most-compatible-match-for-you/)).
7. **Evaluating on one-sided proxy metrics.** Optimizing likes-sent (or clicks) instead of *mutual* events inflates apparent performance while degrading match totals; the matching-market OPE literature exists because standard offline evaluation misranks reciprocal policies ([arXiv 2507.13608](https://arxiv.org/pdf/2507.13608)).
8. **Ignoring capacity.** Recommending a person (unlike an item) consumes their finite attention; systems that don't cap exposure of high-demand profiles burn out exactly the inventory everyone wants ([arXiv 2306.09060](https://arxiv.org/abs/2306.09060)).

## What matters most

Ranked by leverage, with rationale:

1. **The fusion function and its weights** — cheapest change, largest measured effect. Reciprocity-aware scoring ~doubled RECON's success rate; harmonic vs. arithmetic mean is a one-line change with material outcome differences; learned asymmetric weights beat fixed ones ([RECON](https://dl.acm.org/doi/10.1145/1864708.1864747); [Kleinerman](https://dl.acm.org/doi/abs/10.1145/3240323.3240349)).
2. **What event you train on** — mutual-outcome labels (match/accept/reply) over one-sided proxies. This is the difference between LinkedIn's inMail-accept ranker and a naive CTR model; Best-of-Both's pseudo-label blend is the state of the art when mutual labels are sparse ([arXiv 1809.06473](https://arxiv.org/pdf/1809.06473); [arXiv 2409.10992](https://arxiv.org/pdf/2409.10992)).
3. **Behavioral/latent representations over declared attributes** — every measured comparison (Baihe CF vs. content, CMB latent vs. observable, photos-only vs. attributes) lands the same way ([arXiv 1501.06247](https://arxiv.org/abs/1501.06247); [CMB](https://aws.amazon.com/blogs/database/powering-recommendation-models-using-amazon-elasticache-for-redis-at-coffee-meets-bagel/); [arXiv 2108.11714](https://arxiv.org/pdf/2108.11714)).
4. **System-level allocation (congestion control)** — once per-pair scoring is decent, the next gains come from optimizing *total* matches: exposure caps, market/TU-matching, or stable matching. This is what separates a scorer from a matchmaker ([arXiv 2306.09060](https://arxiv.org/abs/2306.09060); Hinge's 8x).
5. **Activity/recency gating** — a correct match with an absent counterparty is a failed match; the biggest player says it's their heaviest factor ([Tinder](https://www.tinderpressroom.com/powering-tinder-r-the-method-behind-our-matching)).
6. **Cold-start ramp design** — reciprocal systems starve twice (no data on either direction); community-assignment + content prior + explicit uncertainty display is the proven combination ([Springer cold-start](https://link.springer.com/chapter/10.1007/978-3-319-78196-9_10); OkCupid margin of error).
7. **Presentation of the match (scarcity + symmetry)** — Hinge's evidence suggests *how* the algorithmic pick is delivered (one per day, both sides see it) multiplies measured algorithm value ([TechCrunch](https://techcrunch.com/2018/07/11/hinge-employs-new-algorithm-to-find-your-most-compatible-match-for-you/)).

## What doesn't matter (even though it seems like it should)

1. **Elaborate psychometric questionnaires.** The intuitive core of "matchmaking science" — and the least supported empirically. Similarity on stated traits barely predicts relationship outcomes; eharmony itself layered ~20 behavioral models on top of its questionnaire, and behavioral CF beats content methods in every head-to-head on real dating data ([JSTOR Daily](https://daily.jstor.org/dont-fall-in-love-okcupid/); [HDSR](https://hdsr.mitpress.mit.edu/pub/i4eb4e8b); [CIO/eharmony](https://www.cio.com/article/206096/click-me-maybe-inside-eharmony-s-matchmaking-machine.html); [arXiv 1501.06247](https://arxiv.org/abs/1501.06247)).
2. **Hand-engineered attribute features.** CMB's engineering team says directly that the observable features humans assume matter are not the strong predictors — latent features mined from match history are ([AWS/CMB](https://aws.amazon.com/blogs/database/powering-recommendation-models-using-amazon-elasticache-for-redis-at-coffee-meets-bagel/)). Corroborated by photos-only models beating full-attribute systems ([arXiv 2108.11714](https://arxiv.org/pdf/2108.11714)).
3. **Point-estimate precision of the pair score.** OkCupid deliberately shows a *lower bound*, not its best estimate, and it made the product stickier, not weaker. Users (and downstream ranking) need ordering and confidence, not third-decimal accuracy ([AMS](https://blogs.ams.org/mathgradblog/2016/06/08/okcupid-math-online-dating/)).
4. **Theoretical stability guarantees per se.** Gale-Shapley's mathematical guarantee ("no blocking pairs") is defined over predicted preferences that are themselves noisy; the observed 8x lift plausibly owes as much to mutual-preference modeling + scarce symmetric presentation as to stability itself. "A stable match might pair you with someone who thinks you're amazing while you think they're just fine" ([SciAm](https://www.scientificamerican.com/article/the-stable-marriage-problem-solution-underpins-dating-apps-and-school/); [arXiv 2208.11384](https://arxiv.org/pdf/2208.11384)). Confidence: moderate — no published ablation separates these effects.
5. **Model family sophistication at the margin.** Matrix factorization (LFRR) on millions of users with a good fusion operator remains competitive; the RecSys 2023 market-based system beat baselines by fixing *allocation*, not by a deeper network ([ACM LFRR](https://dl.acm.org/doi/10.1145/3298689.3347026); [arXiv 2306.09060](https://arxiv.org/abs/2306.09060)). Fusion choice and label choice dominate architecture choice until you're very large.

<a name="transfer-notes"></a>
## Transfer notes for a two-sided trade matcher

Direct mappings from the above to a dynasty-trade-finding context (kept brief; product design is out of scope here):

- A trade proposal is a **reciprocal recommendation**: `p(x↔trade↔y) = φ(P(x accepts), P(y accepts))`. Use harmonic-mean-style fusion (or learned asymmetric weights) so one-sided lopsided "wins" never surface — this is exactly the min-skew property RECON validated.
- The **congestion result transfers cleanly**: the most tradeable assets/managers will dominate every user's suggestions under a greedy product ranking; a league is a *closed market*, making TU-matching/stable-assignment framing (suggest a league-wide consistent set of trades, cap how often one manager is targeted) unusually applicable — a league is small enough to run exact assignment where dating apps must approximate.
- **Mutual-outcome labels** = accepted/countered/declined proposals. Even sparse, they should anchor the model (Best-of-Both pseudo-label pattern: dense heuristic fairness scores blended with sparse real accept/decline labels).
- **OkCupid's machinery is the best template for the explicit-preference layer**: importance-weighted preference questions per manager (positional needs, win-now vs. rebuild), dealbreakers as filters not points, geometric/harmonic-mean pair score, and a displayed confidence bound that rises as the app learns a manager's boards.
- **Hinge's presentation lesson**: one high-conviction, symmetric "Most Compatible trade of the day" shown to both managers is plausibly worth more than a long ranked list — scarcity plus the knowledge that the other side sees the same suggestion.
- **Activity gating**: never surface a trade whose counterparty hasn't opened the app recently; Tinder ranks this factor first for good reason.

## Not researched / follow-up topics

- **Marketplace dynamics, liquidity, and exposure fairness policy** — deliberately left to the sibling memo; the TU-matching thread here ([arXiv 2306.09060](https://arxiv.org/abs/2306.09060)) is the algorithmic bridge into it and deserves a joint read.
- **Feature/signal engineering details** (what inputs feed these models: photo scoring, text NLP, session behavior) — sibling memo's territory; the CF-beats-content findings here constrain which signals are worth the effort.
- **Match Group / Bumble patent corpus** — patents like "private stable matchings via re-encryption mix networks" (US 9218623, 9672564) and Bumble's recommendation patents (US 11151208, 11443256) surfaced in search but were not read in depth; patents often reveal production mechanics official blogs omit.
- **Off-policy evaluation and A/B methodology for reciprocal systems** ([arXiv 2507.13608](https://arxiv.org/pdf/2507.13608), [arXiv 2508.01867](https://arxiv.org/html/2508.01867)) — how to evaluate a matcher offline without deploying it; directly relevant before shipping model changes to a live league.
- **Bandit/online-learning formulations of reciprocal matching** ([arXiv 1806.01182](https://arxiv.org/pdf/1806.01182)) — regret-bounded exploration of the pair space; relevant for small pools (a 12-team league is tiny, exploration is cheap).
- **Group/package recommendation** — a multi-asset trade is closer to bundle recommendation than single-item pairing; the combinatorial layer (which asset bundles to propose, not just which counterparty) has its own literature (bundle recsys, combinatorial auctions) that this memo did not touch.
- **Gale-Shapley variants in depth** (incomplete lists, ties, many-to-many, school-choice mechanisms like deferred acceptance with quotas) — the many-to-many variant maps to "each manager can be in several concurrent trade conversations."
- **Tinder's post-2019 stack specifics** (rumored deep-learning ranker, "Smart Photos" bandit) — only low-confidence teardown material found; a pass through Tinder engineering-blog archives and conference talks (e.g., Tinder at QCon/MLconf after 2017) could firm this up.
- **eharmony's published research** (they have KDD/RecSys-adjacent papers and patents, e.g. US 11409807 "single-click matchmaking") — found but not read; likely the deepest public record of two-sided compatibility modeling at scale.
- **Academic economics of dating markets** (Hitsch/Hortaçsu/Ariely mate-preference estimation) — quantifies revealed preferences and market sorting; useful for priors but sits between this memo and the marketplace one.

## Sources

Official / company engineering:
- https://www.tinderpressroom.com/powering-tinder-r-the-method-behind-our-matching — Tinder, "Powering Tinder: The Method Behind Our Matching" (2019)
- https://www.help.tinder.com/hc/en-us/articles/7606685697037-Powering-Tinder-The-Method-Behind-Our-Matching — Tinder help-center version (fetch-blocked; content mirrored in pressroom post)
- https://mlconf.com/sessions/personalized-user-recommendations-at-tinder-the-t/ — MLconf SF 2017, Steve Liu, TinVec session
- https://www.slideshare.net/SessionsEvents/dr-steve-liu-chief-scientist-tinder-at-mlconf-sf-2017 — TinVec slides
- https://aws.amazon.com/blogs/database/powering-recommendation-models-using-amazon-elasticache-for-redis-at-coffee-meets-bagel/ — Coffee Meets Bagel recommendation infrastructure
- https://www.uber.com/us/en/blog/innovative-recommendation-applications-using-two-tower-embeddings/ — Uber two-tower embeddings
- https://eng.snap.com/embedding-based-retrieval — Snap two-tower retrieval
- https://www.linkedin.com/help/recruiter/answer/a413241 — LinkedIn Recommended Matches
- https://business.linkedin.com/talent-solutions/recruiter — LinkedIn Recruiter (InMail-accept claims)

Journalism / reported:
- https://techcrunch.com/2018/07/11/hinge-employs-new-algorithm-to-find-your-most-compatible-match-for-you/ — TechCrunch on Hinge Most Compatible + Gale-Shapley
- https://9to5mac.com/2018/07/12/ai-dating-app-hinge/ — 9to5Mac, same launch
- https://www.engadget.com/2019-03-18-tinder-dumps-desirability-scores.html — Engadget on Elo retirement
- https://www.globaldatinginsights.com/featured/tinder-changes-algorithms-and-removes-elo-scores/ — Global Dating Insights on Elo removal
- https://www.cio.com/article/206096/click-me-maybe-inside-eharmony-s-matchmaking-machine.html — CIO, inside eharmony's matchmaking machine
- https://www.datingnews.com/apps-and-sites/facts-about-eharmonys-algorithm/ — eharmony algorithm facts
- https://www.scientificamerican.com/article/the-stable-marriage-problem-solution-underpins-dating-apps-and-school/ — Scientific American on deferred acceptance

Academic:
- https://dl.acm.org/doi/10.1145/1864708.1864747 — Pizzato et al., "RECON: a reciprocal recommender for online dating" (RecSys 2010)
- https://link.springer.com/article/10.1007/s11257-012-9125-0 — Pizzato et al., "Recommending people to people" (UMUAI 2013)
- https://arxiv.org/pdf/2007.16120 — Palomares et al., RRS survey (state of art, challenges)
- https://arxiv.org/abs/1501.06247 — Xia et al., reciprocal CF on Baihe data
- https://dl.acm.org/doi/10.1145/2567948.2579240 — Xia et al., "Online dating recommendations" (WWW 2014)
- https://dl.acm.org/doi/10.1145/3298689.3347026 — Neve & Palomares, LFRR (RecSys 2019)
- https://dl.acm.org/doi/abs/10.1145/3240323.3240349 — Kleinerman et al., "Optimally balancing receiver and recommended users' importance" (RecSys 2018)
- https://dl.acm.org/doi/10.1145/3240323.3240362 — Kleinerman et al., reciprocal explanations (RecSys 2018)
- https://arxiv.org/abs/2306.09060 — Tomita et al., "Fast and Examination-agnostic Reciprocal Recommendation in Matching Markets" (RecSys 2023; TU matching)
- https://arxiv.org/pdf/2208.11384 — "Matching Theory-based Recommender Systems in Online Dating" (survey)
- https://arxiv.org/pdf/2409.10992 — "A Best-of-Both Approach to Improve Match Predictions and Reciprocal Recommendations for Job Search"
- https://arxiv.org/pdf/2108.11714 — "Photos Are All You Need for Reciprocal Recommendation in Online Dating"
- https://openreview.net/pdf?id=GOsmeVvSTGC — ImRec: reciprocal preferences from images (siamese networks)
- https://arxiv.org/pdf/2011.12586 — RRCN: reinforced random convolutional network for reciprocal dating recommendation
- https://arxiv.org/pdf/1806.01182 — Online reciprocal recommendation with theoretical guarantees
- https://arxiv.org/pdf/1809.06473 — LinkedIn, deep & representation learning for talent search
- https://arxiv.org/pdf/2507.13608 — Off-policy evaluation and learning for matching markets
- https://arxiv.org/html/2508.01867 — Counterfactual reciprocal recommender systems
- https://link.springer.com/chapter/10.1007/978-3-319-78196-9_10 — Community-based reciprocal cold start (dating)
- https://arxiv.org/pdf/1405.7544 — Contextual bandits for cold start
- https://arxiv.org/pdf/2404.10207 — Hellinger-UCB bandit for cold start
- https://link.springer.com/article/10.1007/s11280-023-01173-z — Contextual bandits + argumentation explanations for RRS
- https://hdsr.mitpress.mit.edu/pub/i4eb4e8b — Harvard Data Science Review, "Finding Love on a First Data: Matching Algorithms in Online Dating"

OkCupid math + critique:
- https://blogs.ams.org/mathgradblog/2016/06/08/okcupid-math-online-dating/ — AMS blog, OkCupid match math (importance weights, geometric mean, margin of error)
- https://www.hackerearth.com/practice/notes/okcupids-matching-algorithm-1/ — HackerEarth writeup of the same math
- https://isomorphismes.wordpress.com/2011/11/22/okcupid-whats-wrong-match-algorithm/ — mandatory-question inflation critique
- https://daily.jstor.org/dont-fall-in-love-okcupid/ — JSTOR Daily on predictive validity

Industry-standard pipeline references:
- https://developers.google.com/machine-learning/recommendation/dnn/re-ranking — Google ML course, re-ranking stage
- https://aman.ai/recsys/re-ranking/ — Aman.ai recsys re-ranking notes
- https://superlinked.com/glossary/introduction-to-recommendation-systems — pipeline overview
- https://www.shaped.ai/blog/the-two-tower-model-for-recommendation-systems-a-deep-dive — two-tower deep dive
- https://medium.com/glassdoor-engineering/improving-embedding-based-candidate-generation-for-recommender-systems-with-a-two-tower-model-c222123beb7f — Glassdoor two-tower candidate generation

Teardowns (low confidence, used sparingly):
- https://www.swipestats.io/blog/tinder-algorithm — Tinder algorithm teardown
- https://dev.to/karim__sk/decoding-bumbles-algorithm-a-developers-guide-to-building-smart-matchmaking-systems-3ejh — Bumble teardown
- https://blog.photofeeler.com/dating-app-algorithms/ — dating-algorithm myths
- https://github.com/CharlesGaydon/Dater-to-Vec — TinVec-inspired open-source reimplementation

Patents (surfaced, not read in depth):
- https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9218623 — private stable matchings
- https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11409807 — eharmony single-click matchmaking
- https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11151208 — Bumble: recommending users via shared digital experiences
