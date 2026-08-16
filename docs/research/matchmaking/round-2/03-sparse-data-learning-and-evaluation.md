# Round 2 — Topic 03: The Learning/Evaluation Loop Under Data Sparsity

> How to train, evaluate, and safely iterate a reciprocal trade-suggestion model when the deep
> outcome (executed trades) is rare, the pool is tiny (10–12 managers per league, tens of leagues),
> and the act of recommending changes the outcome. Research memo for the FTF matchmaking study,
> round 2. Written 2026-08-15.

**Confidence key:** 🟢 high (multiple independent sources / peer-reviewed + replicated in industry),
🟡 medium (solid single source or consistent secondary reporting), 🔴 low (extrapolation to FTF's
regime; the literature was built at larger N).

**FTF signal inventory referenced throughout:** per suggestion — `rendered → viewed → expanded →
dismissed | saved | sent-to-partner`; ground truth — trade executed on Sleeper (auto-observable).

---

## 0. TL;DR

The literature's single most transferable message: **never train or evaluate directly on the rare
deep label alone.** Every serious system facing funnel sparsity — Alibaba's ESMM for conversions,
Wantedly's Best-of-Both for reciprocal job matches, the RecSys'25 DiPS/DPR estimators for matching-market
OPE, Chapelle's delayed-feedback models for ads — solves sparsity the same structural way: **exploit
the funnel.** Train on the dense mid-funnel signals over the entire exposure space, then use the sparse
deep label to *calibrate*, *blend*, or *anchor* — never as the sole target. Off-policy evaluation at
FTF's N is mostly a variance graveyard; the estimators that survive small N are exactly the ones that
substitute dense intermediate rewards for sparse final rewards (DiPS/DPR) or shrink toward a model
(DR/SNIPS with ESS diagnostics). Causal credit ("did our suggestion *cause* the trade?") is answerable
even at tiny N with a permanent suggestion-level randomized holdout — the fantasy-football analog of
ghost ads, and it costs almost nothing to log the counterfactual because FTF can observe executed
trades on Sleeper *whether or not it suggested them*. That last property is rare and valuable: FTF sees
the organic baseline for free.

---

## 1. Deep dives by topic

### 1.1 Label cascade engineering — training on the funnel, calibrating on the deep label

**The canonical pattern: ESMM (Alibaba, SIGIR 2018).** 🟢
The post-click conversion problem is structurally identical to FTF's: conversions (executed trades)
are rare; clicks (views/expands) are abundant; and a model trained only on clicked impressions
(suggestions users engaged with) is both starved for data and biased, because it's trained on a
selected subspace but must score the entire exposure space (sample selection bias). ESMM's fix
([arXiv 1804.07931](https://arxiv.org/abs/1804.07931)):

- Model the chain `pCTCVR = pCTR × pCVR` over the **entire impression space**, with two towers
  sharing an embedding layer. The sparse task (CVR) never gets its own selected-sample loss; it is
  learned implicitly as the ratio of two entire-space quantities.
- The dense task's gradients train the shared representation (feature-representation transfer),
  so the sparse task inherits statistical strength from the dense one.

For FTF this maps to: `P(executed) = P(viewed|rendered) × P(expanded|viewed) × P(saved-or-sent|expanded)
× P(executed|sent)`. Each conditional is far denser than the end-to-end label, and every stage is
trained on its full parent population — no stage is trained only on "suggestions that got far."
ESCM² ([ResearchGate](https://www.researchgate.net/publication/359890563_ESCM2_Entire_Space_Counterfactual_Multi-Task_Model_for_Post-Click_Conversion_Rate_Estimation))
extends this with counterfactual (IPS/DR) regularizers because ESMM's implicit CVR is itself
slightly biased — worth knowing about, overkill at FTF's N. 🟡

**Best-of-Both (BoB), arXiv 2409.10992 — read in depth.** 🟢 (method), 🟡 (transfer to N=tiny)
Goda, Hayashi & Saito, "A Best-of-Both Approach to Improve Match Predictions and Reciprocal
Recommendations for Job Search" — Wantedly production data. This is the closest published analog to
FTF's exact problem: a **reciprocal** market where the true label ("match" = both sides act) is far
sparser than either side's one-directional action. Extracted method:

1. Train two **directional preference models** on the dense one-directional signals:
   `p̂^(c→j)` (company→seeker, trained on scout sends) and `p̂^(j→c)` (seeker→company, trained on
   replies). Both are much denser than mutual matches.
2. Construct a **pseudo-match score** per pair, blending the sparse true label with the dense
   prediction product:
   `s_pseudo(c,j; α) = α·m(c,j) + (1−α)·p̂^(c→j)·p̂^(j→c)`
   where `m ∈ {0,1}` is the true match label and `α ∈ [0,1]` trades label accuracy against density.
3. Train a **meta-model** (they used GBDT, cross-entropy loss) to regress pair features onto
   `s_pseudo`. The meta-model, not a hand-picked aggregation function (product, harmonic mean),
   produces the final match score — this is what mitigates the error propagation of multiplying two
   noisy directional predictions.
4. **Personalize α by segment**: they split companies into High/Middle/Low activity and tuned α per
   segment on validation. Sparse-history segments got low α (lean on predictions); rich-history
   segments tolerate higher α. α = 1.0 (pure true labels) consistently *degraded* — pure sparse
   labels are unusable even at Wantedly's scale.
5. Results: NDCG@10 +4.3% relative for the best global α (0.25), +7.2% for personalized α, versus
   the best classical aggregation (harmonic mean). Baselines compared: scout-only, reply-only,
   multiplication, harmonic mean.

Key transferable insights: (a) the *best global α was 0.25* — even with a production job platform's
data volume, the optimal blend is dominated by the dense pseudo-signal, not the true label; (b) the
harmonic mean / product of directional scores is the baseline to beat, and it's decent — FTF can ship
`p̂(A accepts)·p̂(B accepts)` long before it has data for a meta-model; (c) α is a *dial that should
follow per-segment data volume* — exactly the partial-pooling instinct from §1.6.

**Delayed feedback is part of the same cascade.** 🟡 Executed trades arrive days after the
suggestion (negotiation, league veto windows). The ads literature (Chapelle's DFM with exponential
delay; FNW/DEFER importance-weighted label correction; multi-task delay-bin models — see
[Entire Space Cascade Delayed Feedback Modeling](https://arxiv.org/pdf/2308.04768) and the
[delayed-feedback benchmark](https://arxiv.org/html/2601.19965v2)) says: a not-yet-executed trade is
not a negative, it's a censored observation. At FTF's volume, the full survival-model machinery is
unnecessary; the N=tiny version is a fixed **maturation window** (e.g., a suggestion's execute label
is undefined until 14 days post-send, then frozen) so training data never contains fake negatives.

**Knowledge distillation framing.** 🟡 The distillation variants (UKD for CVR debiasing; teacher
trained on dense labels producing soft targets for a student calibrated on sparse ones) are the deep-
learning dress on the same body: dense-signal model as teacher, sparse-label data as the calibration
set. BoB's pseudo-label blend *is* self-distillation with a truth-mixing knob. At FTF's N, prefer the
BoB/GBDT form over neural multi-task: fewer parameters, works at hundreds of rows.

### 1.2 Off-policy evaluation — judging a new suggestion policy from logged data

**The standard toolkit and its small-N failure modes.** 🟢
- **Direct Method (DM):** fit a reward model, score the new policy's choices. Low variance, bias
  bounded only by model quality — and at small N the model is bad in exactly the regions the new
  policy explores.
- **IPS:** reweight logged rewards by `π_new(a|x)/π_logged(a|x)`. Unbiased *if propensities are
  logged and support overlaps*, but variance explodes when the new policy likes actions the old
  policy rarely took — which is the whole point of trying a new policy. At FTF's N, a handful of
  large weights will dominate the estimate.
- **SNIPS:** divide by the sum of weights — a multiplicative control variate. Trades a small bias
  for a large variance cut; consistently tighter in recommender evaluations
  ([SNIPS overview](https://www.emergentmind.com/topics/self-normalized-inverse-propensity-scoring-snips)).
  Recent work shows an optimal *additive* baseline (β\*-IPS) dominates SNIPS asymptotically
  ([arXiv 2602.14914](https://arxiv.org/html/2602.14914v3)) — a refinement, not a game-changer at tiny N.
- **Doubly Robust:** DM baseline + IPS on the residual. Unbiased if *either* the model or the
  propensities are right; lower variance than IPS. The default recommendation in the OPE tutorials
  ([Towards Data Science tutorial](https://towardsdatascience.com/a-complete-tutorial-on-off-policy-evaluation-for-recommender-systems-e92085018afe/),
  [Saito's counterfactual-ML tutorials](https://counterfactual-ml.github.io/kdd2022-tutorial/)).
- **The diagnostic that matters at small N: Effective Sample Size.** `ESS = (Σw)²/Σw²`. If ESS is
  20 when you logged 2,000 suggestions, your OPE estimate is worth 20 observations and should be
  treated (and confidence-intervaled) accordingly. Compute it every time; refuse to read point
  estimates without it. 🟢

**OPE for matching markets specifically — DiPS and DPR, arXiv 2507.13608 (RecSys'25), read in depth.** 🟢
Hayashi, Goda & Saito (same Wantedly group). Matching markets break vanilla OPE twice: action spaces
are large (many candidates per user) and the final reward (mutual match) is brutally sparse, so IPS
variance is catastrophic. Their move is the same funnel exploitation as §1.1, now inside the estimator:

- **DiPS**: importance-weight the *dense first-stage reward* `s` (e.g., scout sent / FTF: user
  saved-or-sent), and multiply by a *regression estimate* `q̂_r(c,j)` of the second-stage conversion
  (reply | scout / FTF: partner accepts & executes | sent):
  `V̂_DiPS = (1/|C|) Σ_c [π(j_c|c)/π₀(j_c|c)] · s_c · q̂_r(c, j_c)`
  Variance replaces the (huge) match-label noise term `E[w²σ²_m]` with the much smaller
  `E[w²σ²_s·q̂_r²]`. Bias depends only on the *second-stage* regression error — and the second stage
  (accept|sent) is a much easier, better-conditioned prediction than the end-to-end match.
- **DPR**: doubly-robust variant adding a match-probability model `q̂_m` as a control variate:
  `V̂_DPR = (1/|C|) Σ_c { w·(s_c·q̂_r − q̂_m) + E_π[q̂_m] }`. Same bias as DiPS, lower variance when
  `q̂_m` is decent.
- Empirics: lowest MSE among six estimators on synthetic + real Wantedly logs, *gains largest at
  1–2% match rates and large action spaces*; validated against real A/B ground truth. Their
  practitioner guidance: DiPS when the match model is hard to train (FTF today), DPR once `q̂_m`
  is trustworthy; both need **logged propensities** from the serving policy.
- They also derive policy-*learning* gradients (DiPS-PG/DPR-PG) for training a policy offline —
  relevant later, not now.

**What OPE requires FTF to do *today* regardless of scale** 🟢: log, for every rendered suggestion,
(a) the propensity / score / rank under the serving policy, (b) the candidate set it was chosen
from, (c) the policy version ID. OPE is impossible retroactively; the logging is the investment.
[Open Bandit Pipeline](https://github.com/st-tech/zr-obp) implements DM/IPS/SNIPS/DR (+ estimator-
selection tooling) off exactly this log schema and is the right scaffold when FTF gets there.

**Honest small-N verdict** 🔴: with tens of leagues, OPE will *rank* two policies ("is B obviously
worse than A?") long before it *measures* lift. Use it as a guardrail (reject clearly-bad policies
offline) rather than a scalpel (pick between close policies) until ESS on the deep signal clears a
few hundred. On mid-funnel rewards (save/send rates) that threshold arrives 20–50× sooner — another
reason the funnel labels carry the program.

### 1.3 Uplift and incrementality — did the suggestion *cause* the trade?

**The problem.** A recommender that suggests trades likely to happen anyway scores beautifully on
correlational labels while adding zero value; worse, an *endorsement effect* (the app blessing a
trade makes managers accept it) means the recommendation partially manufactures its own label —
the self-fulfilling recommendation. The ads industry's answer is randomized withholding. 🟢

- **User/opportunity-level holdouts** are the purest RCT: randomly withhold treatment from a slice
  and compare ([Remerge's incrementality taxonomy](https://www.remerge.io/blog-post/incrementality-tests-101-intent-to-treat-psa-ghost-ads-and-ghost-bids),
  [SegmentStream guide](https://segmentstream.com/blog/articles/incrementality-measurement-guide)).
- **Ghost ads** (Johnson, Lewis & Nubbemeyer, JMR 2017 — [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2620078))
  refine this: in the control group, *record the exact impression that would have been served* but
  don't serve it. You compare exposed-treated to would-have-been-exposed-control, which slashes
  dilution and cost versus intent-to-treat; Google's implementation cut experimentation costs by an
  order of magnitude. 🟢
- **Uplift modeling** then targets treatment where the *causal delta* is largest, not where the
  outcome probability is highest ([INCRMNTAL on uplift](https://www.incrmntal.com/resources/how-to-use-uplift-modeling)) —
  the four-quadrant framing: persuadables / sure things / lost causes / do-not-disturbs. FTF's
  "sure things" are trades the two managers were going to do anyway; FTF only earns its keep on
  persuadables. 🟢 concept, 🔴 any model-based uplift estimation at FTF's N (uplift models need the
  *most* data of anything in this memo — you're estimating a difference of two rare rates).

**The FTF-shaped gift: the organic baseline is free.** Because Sleeper exposes all executed trades,
FTF observes the outcome for suggestions it *never rendered* — a natural "ghost suggestion" design:
generate the top-K suggestions per user as usual, randomly withhold suggestion #k for a small slice
(log it as a ghost), and watch Sleeper to see whether the withheld trade (or a close variant —
define a similarity match rule up front) executes anyway. This gives a true incrementality read with
zero user-visible cost and works at small N because it accumulates across every league-week. Also
track the coarse global ratio `executed trades that were previously suggested / all executed trades`
per league as a cheap, always-on endorsement-effect dashboard. 🟡 (design is my synthesis; every
component — ghost recording, holdout comparison, ITT dilution logic — is standard in the cited work)

**Feedback-loop hygiene.** Degenerate feedback loops / algorithmic confounding
([Chaney et al.](https://www.researchgate.net/publication/320754991_How_Algorithmic_Confounding_in_Recommendation_Systems_Increases_Homogeneity_and_Decreases_Utility),
[Feedback Loop and Bias Amplification](https://ar5iv.labs.arxiv.org/html/2007.13019),
[Bias & Debias survey](https://arxiv.org/pdf/2010.03240)): once you retrain on data your own
recommendations produced, mild biases compound each cycle — the model narrows toward what it already
shows. Mitigations that work at any N: keep the permanent exploration slice (§1.4), tag every training
row with `was_recommended` and the policy version so exposure is a *feature/correction*, not an
invisible confounder, and never delete the holdout. 🟢

### 1.4 Exploration in tiny action spaces

**Thompson sampling vs UCB at very small N.** 🟢 The empirical comparisons
([ITM comparative study](https://www.itm-conferences.org/articles/itmconf/pdf/2025/11/itmconf_acaai2025_02004.pdf),
[Agrawal & Goyal's optimality analyses](http://proceedings.mlr.press/v23/agrawal12/agrawal12.pdf),
[Kaufmann on Bayesian index policies](https://arxiv.org/pdf/1601.01190)) converge on: TS usually edges
out UCB on cumulative regret, is markedly better *early* (small t — FTF's permanent condition), is
trivial to implement with Beta posteriors on binary rewards, and — decisive for FTF — **absorbs
priors and batched/delayed rewards gracefully**, whereas UCB's exploration bonus needs hand-tuning
(the `c` coefficient) and misbehaves under delayed feedback. Practical verdict: Beta-Bernoulli
Thompson sampling over discrete choices (which counterparty to feature, which package archetype to
lead with), with priors seeded from the global model — an 11-arm problem needs a spreadsheet, not a
library.

**Exploration budgets.** 🟡 Production systems run small fixed exploration slices: the classic
95/5 epsilon-greedy framing ([Milvus overview](https://milvus.io/ai-quick-reference/how-do-you-balance-exploration-and-exploitation-in-recommendations)),
1–2% in a large-scale bandit serving system ([Online Matching, arXiv 2307.15893](https://arxiv.org/pdf/2307.15893)),
Spotify's epsilon-greedy in production ([Explore, Exploit, Explain](https://dl.acm.org/doi/10.1145/3240323.3240354)),
and Netflix-affiliated work on *scheduling* the rate over time
([Optimization of Epsilon-Greedy Exploration](https://arxiv.org/html/2506.03324)). Two adjustments
for FTF's regime: (a) small platforms should run *hotter* than 1–5% — those numbers are for systems
already drowning in data; early FTF learns almost nothing new from suggestion #1's clone. Something
like 1 slot in each user's daily list (~10–20% of impressions) being off-model-but-sensible is closer
to right 🔴 (my extrapolation; no source studies exploration rates at tens-of-leagues scale). (b) In
a list UI, exploration is free-ish real estate: randomize *within* the plausible set (swap positions
4–10), never the top slot — position-swap exploration also produces exactly the interventional data
that position-bias correction (§1.5) needs.
**Structured sharing beats per-arm learning:** with ~11 counterparties, don't learn 11 independent
arms per user — model arms via shared features (position needs, tier gap, manager activity) so every
observation updates every arm. At FTF's N, a contextual model with TS on its posterior beats any
context-free bandit. 🟢 (standard contextual-bandit doctrine)

**Cold-start preference elicitation.** 🟢 Pairwise comparisons beat absolute ratings (humans are
better at relative judgments), and active selection makes them sample-efficient: decision-tree and
Fisher-information-driven elicitation get usable preference signal in a handful of queries
([Pairwise & Attribute-Aware Decision Tree elicitation, arXiv 2510.27342](https://arxiv.org/abs/2510.27342),
[Explainable Active Learning for Preference Elicitation](https://arxiv.org/pdf/2309.00356),
[Cold-Start Active Preference Learning](https://arxiv.org/pdf/2508.05090) — the last reporting F1 ≈ 0.65
after just 2 well-chosen queries). FTF already has the perfect instrument: the Elo 3-player matchup
flow *is* active pairwise elicitation. The research supports pointing it at trade-preference
dimensions during onboarding ("would you rather get: proven RB2 vs. two future 2nds?") — 3–5 forced
choices along the axes Matt's trade-philosophy interview surfaced (consolidation appetite, age
tolerance, pick fetish) initializes a per-user preference vector before any behavioral data exists.

### 1.5 Negative-signal weighting in practice

**The foundational rule: absence of action ≠ dislike.** 🟢 Hu, Koren & Volinsky
([Collaborative Filtering for Implicit Feedback, ICDM'08](https://dl.acm.org/doi/10.1109/ICDM.2008.22))
formalized implicit feedback as (preference, confidence) pairs: unobserved = weak negative at low
confidence; observed = positive with confidence growing in engagement intensity. Everything since is
elaboration.

**Graded negatives for FTF's funnel.** The literature supports a confidence ladder, not binary labels.
Synthesis of Hu-Koren-Volinsky confidence weighting, WBPR's popularity-weighted negatives
(unclicked-but-surely-seen items are more trustworthy negatives), and exposure-aware sampling
([Reinforced Negative Sampling with Exposure Data](https://www.ijcai.org/proceedings/2019/0309.pdf),
[Correct and Weight](https://arxiv.org/html/2601.04291)) 🟢, mapped to FTF's signals 🟡 (mapping is
mine; the ordering principle is sourced):

| Signal | Label | Suggested confidence weight |
|---|---|---|
| Executed on Sleeper | strong positive | 25–50 (rare; carries calibration) |
| Sent-to-partner | positive | 8–10 |
| Saved | positive | 4–6 |
| Expanded, no action | weak positive | 1–2 |
| Viewed (impression confirmed) & scrolled past | weak negative | 0.5–1 |
| **Explicitly dismissed after viewing** | **strong negative** | **3–5 (the only trustworthy negative)** |
| Rendered but never viewed | ~no signal | ≈0 (exclude or ε) |

The single most-repeated warning: **never treat never-viewed as negative** — that's exposure bias
laundered into labels, and at FTF's volume a few hundred poisoned negatives will dominate training.
An explicit dismissal is *gold* precisely because it's exposure-controlled: the user demonstrably saw
it and said no. Pairwise losses (BPR — sample negatives from *viewed-and-dismissed* before falling
back to unviewed; [WARP](https://building-babylon.net/2016/03/18/warp-loss-for-implicit-feedback-recommendation/) —
rank-weighted updates) exploit this ladder naturally; IPS-weighted BPR
([arXiv 2509.00333](https://arxiv.org/pdf/2509.00333)) adds exposure correction inside the loss. 🟢

**Position-bias correction.** 🟢 In any ranked list, lower positions get examined less, so their
non-engagement means less (examination hypothesis). Standard fixes: estimate position propensities
`θ_k` (P(examined | rank k)) and inverse-weight clicks — with the caveat that plain IPS corrects
clicks-as-relevant but not nonclicks-as-irrelevant; affine corrections and the position-bias DR
estimator fix both and cut variance enormously ([affine corrections, arXiv 2008.10242](https://arxiv.org/pdf/2008.10242),
[DR for position bias, TOIS](https://dl.acm.org/doi/10.1145/3569453)). Estimation at small N: full
EM-style propensity estimation needs volume, but FTF has two shortcuts — (a) the exploration slice's
position swaps are randomized interventions, the gold standard for estimating `θ_k`
([eCommerce position-bias estimation, arXiv 1812.09338](https://arxiv.org/pdf/1812.09338)); (b) the
mobile client can log *actual viewport visibility* (rendered vs. viewed is already in the schema!),
which replaces inferred examination with measured examination — most of the position-bias literature
exists because platforms *can't* observe examination; FTF can. Log scroll-depth/visibility per card
and position bias mostly reduces to a measured exposure filter. 🟡

### 1.6 Per-user normalization — selectivity and partial pooling

**The problem:** a save from a manager who saves everything is weak evidence; a save from a picky
manager is strong. Raw per-user rates at 10–30 observations are noise. The canonical fix is
**empirical Bayes shrinkage / partial pooling** 🟢: fit a Beta(α₀, β₀) prior across all users by
moment-matching or MLE on the population of per-user rates, then estimate each user's rate as the
posterior mean `(α₀ + successes) / (α₀ + β₀ + trials)`. Low-volume users sit near the population
mean; evidence moves them out gradually
([kiwidamien on shrinkage + EB](https://kiwidamien.github.io/shrinkage-and-empirical-bayes-to-improve-inference.html),
[Andrew Wheeler on sorting rates with EB](https://andrewpwheeler.com/2018/07/23/sorting-rates-using-empirical-bayes/),
[EB for discrete exponential families](https://arxiv.org/pdf/1910.08997)). This is ~15 lines of code
and is *the* technique in this memo most obviously built for N=tiny — it exists precisely to make
small per-unit samples usable.

Concrete FTF uses 🟡: (a) shrunken per-user save-rate and dismiss-rate → a **selectivity score**;
weight each user's positives by ~`1/save_rate_shrunk` (a save from a 5%-saver ≫ a save from a
60%-saver) — this is the per-user analog of tf-idf, and the same idea BoB reached via per-segment α;
(b) shrunken per-user accept-given-sent rates feed the reciprocal model's "partner will accept" term;
(c) the hierarchy can go deeper — league-level priors under a global prior (some leagues are trade-happy)
— but two levels (global → user) is enough until there are ≥50 leagues; (d) same machinery applies to
Thompson-sampling priors: the Beta posterior per arm *is* the shrunken estimate. One caution from the
EB literature: shrinkage biases *extreme true* users toward the mean — a genuinely trade-crazy manager
looks average for their first ~20 events. Acceptable cost; note it.

### 1.7 Recency and decay in a hard-seasonal domain

**The headline finding is a negative one.** 🟢 Koren's landmark temporal-dynamics work
([Collaborative Filtering with Temporal Dynamics, CACM/KDD](https://dl.acm.org/doi/pdf/10.1145/1721654.1721677))
explicitly found that **naive time-decay and sliding windows *underperform*** — "classical
time-window or instance decay approaches … lose too many signals when discarding data instances."
The winning approach models time explicitly (time-varying bias terms, transient vs. long-term
components) so old data still informs stable preferences while dated *states* fade. The temporal-RS
survey literature ([MDPI systematic review](https://www.mdpi.com/2076-3417/10/7/2204),
[ACM TORS on concept drift in streams](https://dl.acm.org/doi/10.1145/3707693)) adds the distinction
FTF needs: **preference drift** (smooth — handled by per-user decay rates) vs. **temporal context /
regime** (cyclic or discrete — handled by treating time as a *feature*, e.g., summer vs. winter
recommendations differ).

Fantasy football is dominated by the second kind: offseason / draft season / in-season / trade-deadline
/ playoffs are **regimes, not drift**. A smooth half-life cannot express "contender-mode preferences
snap back every August." The sourced-principles synthesis for FTF 🟡:

1. **Season phase as a first-class context feature** on every training row and every inference call —
   never only as a decay knob. What a user saved at the deadline is evidence about *deadline behavior*,
   fully reusable next deadline (annual periodicity ≈ Koren's cyclic day-of-week effects, scaled up).
2. **Split the state, decay it differently.** Roster/contention state: no decay — *replace* (it's
   observable from Sleeper, current truth beats history). Taste parameters (consolidation appetite,
   pick-vs-player lean, age tolerance): slow decay, half-life of ~a season; these are what Matt's
   interview suggests are stable traits. Within-phase tactical signals (who they're targeting now):
   fast decay, half-life 2–4 weeks, hard reset at phase boundaries.
3. **Phase-boundary resets, not amnesia:** at a regime change, widen posteriors / re-inflate
   exploration (the bandit's cue to re-explore) rather than discarding rows — discarding data at
   N=tiny is self-harm, which is Koren's point at any N.

---

## 2. Best practices

1. **Train on the funnel over the entire exposure space; calibrate on the deep label** (ESMM
   entire-space decomposition; BoB pseudo-label blend with α ≈ 0.25 dominated by dense signal). 🟢
2. **Ship the directional-product baseline first** — `P(A engages) × P(B accepts)` from dense
   one-directional signals is the proven pre-meta-model baseline in reciprocal matching. 🟢
3. **Log for counterfactuals from day one**: propensity/score/rank of every rendered suggestion,
   the candidate set, policy version, `was_recommended` on every executed Sleeper trade. OPE and
   incrementality are logging problems before they are math problems. 🟢
4. **Report ESS with every offline estimate**; use SNIPS/DR (later DiPS/DPR) rather than raw IPS;
   use OPE to reject bad policies, not to crown close winners, until ESS clears a few hundred. 🟢
5. **Run a permanent randomized ghost-suggestion holdout** and watch Sleeper for organic execution —
   FTF's free organic baseline makes true incrementality measurable even at tiny N. 🟡
6. **Beta-Bernoulli Thompson sampling with feature-shared arms** for the explore/exploit layer; seed
   priors from the global model; batch-update on FTF's natural cadence. 🟢
7. **Grade negatives by exposure**: dismissed-after-viewed is the only strong negative;
   never-viewed is near-zero signal; log viewport visibility so examination is measured, not modeled. 🟢
8. **Shrink every per-user rate with empirical Bayes** before using it anywhere (selectivity
   weighting, accept-rate features, bandit priors). Two-level pooling (global→user) until ≥50 leagues. 🟢
9. **Season phase is a feature, not a decay constant**; decay taste slowly, replace state instantly,
   reset tactics at phase boundaries; widen posteriors at regime changes instead of deleting data. 🟡
10. **Onboard with 3–5 active pairwise trade-philosophy questions** riding the existing Elo matchup
    UI — elicitation research shows a handful of well-chosen pairwise queries carries real signal. 🟢

## 3. Antipatterns

1. **Training a model directly and only on executed trades.** At tens of leagues this is dozens of
   positives — guaranteed overfit, and sample-selection-biased besides (the ESMM problem). Even
   Wantedly found pure true labels (α = 1.0) degraded performance *at production scale*. 🟢
2. **Treating unviewed suggestions as negatives.** Exposure bias as label poison; the most warned-
   against error in the implicit-feedback literature. 🟢
3. **Vanilla IPS on the executed-trade reward.** Variance is maximal exactly where reward is sparse
   and policies differ; a couple of lucky logged executions will swing the estimate arbitrarily. 🟢
4. **Retraining on your own recommendations' outcomes without exposure tagging or a holdout** —
   algorithmic confounding compounds per cycle and, in FTF's case, quietly replaces "trades both
   sides want" with "trades the app already likes to show." 🟢
5. **Optimizing correlational execute-probability** — rewards "sure things" the managers would have
   traded anyway and pushes toward obvious, low-value suggestions (the uplift quadrant error). 🟢
6. **Sliding windows / aggressive global decay** — at N=tiny, discarding data is the one unaffordable
   luxury, and Koren showed it's a bad idea even at Netflix scale. 🟢
7. **Per-arm, per-user context-free bandits** — 11 counterparties × dozens of package archetypes ×
   12 users/league never converges; arms must share strength through features. 🟢
8. **Uplift *modeling* (per-pair heterogeneous treatment effects) now** — estimating a difference of
   two rare rates needs orders of magnitude more data than FTF has; measure *average* incrementality
   instead (the holdout), model heterogeneity later. 🟡
9. **A/B testing as the primary iteration loop** at 10–12 users per league / tens of leagues —
   league-level interference (one trade changes every roster) plus tiny N means most A/B reads will
   be noise; this is precisely why the matching-market OPE literature exists. 🟡

## 4. What matters most (ranked)

1. **The logging schema** (propensities, candidate sets, visibility, policy versions, exposure tags,
   ghost slots). Every technique in this memo consumes it; none can be applied retroactively. Cost:
   days. Unlocks: everything.
2. **Funnel-structured training** (entire-space cascade + BoB-style blending). The difference between
   "model learns from ~50 executions" and "model learns from ~50,000 funnel events."
3. **Exposure-graded negative weighting.** Dismissals are FTF's richest abundant signal; mishandling
   negatives poisons more rows than any other single error at small N.
4. **Empirical Bayes shrinkage on all per-user rates.** Cheapest technique here, purpose-built for
   small samples, feeds features, selectivity weights, and bandit priors simultaneously.
5. **A permanent randomized holdout + Sleeper organic baseline.** The only credible answer to "does
   FTF cause trades?" — and the moat metric for the business, not just the model.
6. **A modest, permanent, structured exploration slice** (TS within the plausible set, position swaps).
   Prevents feedback-loop lock-in and generates the interventional data items 3 and 5 rely on.
7. **Regime-aware time handling.** Matters more in fantasy than in any domain the literature studies,
   but it's a feature-engineering decision, not an infrastructure one — hence ranked below the loop
   mechanics.
8. **Formal OPE (DiPS/DPR, OBP).** Highest ceiling, latest payoff — becomes decisive at hundreds of
   leagues; until then it's a guardrail.

## 5. What doesn't matter (even though it seems like it should)

- **Estimator sophistication beyond SNIPS/DR at current N.** The DiPS/DPR machinery is the right
  destination, but below a few hundred effective samples every estimator returns wide intervals;
  the binding constraint is logged data, not math. Adopt the *logging* now, the estimators later. 🟢
- **Neural multi-task architectures (ESMM-style towers, distillation students).** The *pattern*
  transfers; the parameter counts don't. GBDT/logistic + the BoB blend does the same job at
  hundreds-of-rows scale. 🟢
- **TS vs UCB agonizing.** The measured differences are small and setup-dependent; delayed-feedback
  tolerance and prior-seeding convenience decide it for TS, and either would work. Pick TS, move on. 🟢
- **Optimal exploration-rate scheduling** (Netflix's regret-minimizing MPC schedules). At FTF's
  volume the difference between 10% and 15% exploration is undetectable; any fixed sensible rate
  beats none, and none of the scheduling machinery pays off below massive N. 🟡
- **Model-based position-bias correction (EM propensity estimation, DR-for-rank).** FTF's client can
  *measure* card visibility — measured exposure makes most of that literature unnecessary. Log
  visibility; skip the propensity models. 🟡
- **Per-pair uplift models.** Seems like the principled end-state ("suggest where we change minds")
  — but the sample-size requirements are the worst in this memo, and average incrementality from the
  holdout answers the business question for years first. 🟢
- **Fine-grained decay-constant tuning.** Once season phase is a feature and state is replaced rather
  than decayed, the residual sensitivity to taste-signal half-lives is small; don't burn experiment
  budget on it. 🔴 (inference from the regime structure, not directly studied)

## 6. Transfer notes for FTF

**The one-paragraph program.** Instrument first (propensities, visibility, exposure tags, ghost
slots). Train a two-directional engagement model on funnel labels over the entire rendered space,
score pairs with the product rule, and blend toward executed-trade truth with a small α as executions
accumulate — per-segment α via empirical-Bayes-shrunk user activity, exactly BoB's recipe. Serve
through a Thompson-sampling layer with one exploratory slot per list. Keep a permanent ghost-suggestion
holdout scored against Sleeper's organic trade feed as the incrementality dashboard. Evaluate policy
candidates offline with SNIPS/DR + ESS as a reject-bad-ideas filter; graduate to DiPS/DPR when scale
arrives. Season phase is a feature everywhere; roster state is replaced, taste decays slowly, tactics
reset at phase boundaries.

**Works at N=tiny vs needs scale:**

| Technique | N=tiny (tens of leagues, now) | Needs scale | Notes |
|---|---|---|---|
| Counterfactual logging schema | ✅ build now | — | Prerequisite for everything; retroactively impossible |
| Directional-product reciprocal score (`p̂_A·p̂_B`) | ✅ | — | BoB's own baseline; dense labels only |
| Entire-space funnel cascade (ESMM *pattern*, GBDT/LR) | ✅ | — | The pattern, not the neural towers |
| BoB pseudo-label blend (global α) | ✅ once ~50–100 executions exist | — | Start α≈0.1–0.25; α=0 until then |
| BoB personalized/segment α | ⚠️ segment-level only | user-level α | Use 2–3 activity segments via EB shrinkage |
| Empirical Bayes shrinkage (rates, selectivity) | ✅ ideal at this N | — | Built for small samples; ~15 LOC |
| Graded negatives + dismissal weighting | ✅ | — | Needs visibility logging, not volume |
| Measured viewport visibility (vs. position-propensity models) | ✅ | — | Replaces most position-bias machinery |
| Thompson sampling, feature-shared arms | ✅ | — | Beta-Bernoulli; batch updates fine |
| Fixed exploration slice (~1 slot/list) | ✅ | — | Run hotter than big-platform 1–5% |
| Pairwise onboarding elicitation (3–5 questions) | ✅ | — | Rides existing Elo matchup UI |
| Ghost-suggestion holdout + Sleeper organic baseline | ✅ | — | Average incrementality only; accumulate across league-weeks |
| Season-phase-as-feature, split decay | ✅ | — | Design decision, not data-hungry |
| Maturation window for execute labels | ✅ | — | Poor man's delayed-feedback model |
| SNIPS/DR OPE as guardrail | ⚠️ reject-only, with ESS | precise policy ranking | Wide CIs; mid-funnel rewards usable much sooner |
| DiPS/DPR matching-market OPE | ❌ adopt logging contract now | ✅ ~100s of leagues | Purpose-built for this domain at scale |
| Off-policy *learning* (DiPS-PG/DPR-PG) | ❌ | ✅ | After OPE itself is trustworthy |
| Delayed-feedback survival models (DFM/DEFER) | ❌ window suffices | ✅ | Revisit if maturation window bites |
| Per-pair uplift / heterogeneous treatment effects | ❌ | ✅✅ (most data-hungry) | Holdout answers the question meanwhile |
| Neural multi-task / distillation (ESCM², UKD) | ❌ | ✅ | Pattern already captured by BoB+GBDT |
| League-level A/B testing | ❌ interference + tiny N | ✅ many leagues | OPE + holdout instead |

**FTF-specific asymmetries worth exploiting (not in the literature):** (1) Sleeper gives the organic
outcome feed for *non-suggested* trades — dating apps and job boards never see matches that happen
off-platform; FTF's incrementality measurement is structurally easier than the platforms this
literature was built on. (2) The candidate space is enumerable (11 counterparties × finite sensible
packages), so "propensity of the logged action" is genuinely computable, not approximated — the
biggest practical obstacle to OPE elsewhere. (3) Roster state is fully observable and objective,
so the model only has to learn *taste*, not *situation* — a large effective-dimensionality reduction
that partially offsets tiny N. 🔴 (my analysis)

## 7. Not researched / follow-up topics

- **Interference-aware experimentation in closed markets:** a trade changes both rosters and shifts
  every other manager's opportunity set — cluster-randomized designs (league-level assignment) and
  interference-robust estimators were not covered; relevant once FTF has enough leagues to randomize
  across them.
- **DiPS/DPR variance behavior below ~1k logged decisions:** the paper's synthetic sweeps go small
  but not FTF-small; worth an empirical replication with OBP on simulated FTF logs before trusting it.
- **Preference-elicitation question *design* for trades:** which 3–5 pairwise questions maximize
  information about accept behavior (vs. generic attribute elicitation) — needs FTF's own pilot data;
  literature covers algorithms, not this domain's question content.
- **Simulation-based policy pre-screening:** agent-based league simulators as a zeroth evaluation
  gate before OPE (analog of RecSim/RL simulators). Deliberately out of scope; promising for FTF
  since roster state and values are fully specifiable.
- **Multi-objective calibration** (execute-probability vs. roster-improvement vs. fairness-gate
  interactions) — how the learning loop coexists with FTF's existing `user_gain_epsilon` fairness
  machinery.
- **The 2×2 reciprocal cold-start** (new user × new league mid-season) and cross-league transfer of
  user preference vectors for managers in multiple leagues.
- **Best-of-Both follow-ups:** whether the Wantedly group has published α-selection theory (their
  segment tuning was grid search); watch this Goda/Hayashi/Saito cluster — three of the most
  FTF-relevant papers in this memo share authors.

## 8. Sources

Anchor papers (read in depth):
1. Goda, Hayashi & Saito — *A Best-of-Both Approach to Improve Match Predictions and Reciprocal Recommendations for Job Search* — https://arxiv.org/abs/2409.10992 (full text: https://arxiv.org/html/2409.10992v1)
2. Hayashi, Goda & Saito — *Off-Policy Evaluation and Learning for Matching Markets* (RecSys'25, DiPS/DPR) — https://arxiv.org/abs/2507.13608 (full text: https://arxiv.org/html/2507.13608)

Label cascades / funnel / delayed feedback:
3. Ma et al. — *Entire Space Multi-Task Model (ESMM)* — https://arxiv.org/abs/1804.07931
4. Wang et al. — *ESCM²: Entire Space Counterfactual Multi-Task Model* — https://www.researchgate.net/publication/359890563_ESCM2_Entire_Space_Counterfactual_Multi-Task_Model_for_Post-Click_Conversion_Rate_Estimation
5. *Entire Space Cascade Delayed Feedback Modeling* — https://arxiv.org/pdf/2308.04768
6. *Modeling Cascaded Delay Feedback for Online Net Conversion Rate Prediction* (delayed-feedback benchmark incl. Chapelle DFM, FNW/DEFER taxonomy) — https://arxiv.org/html/2601.19965v2
7. *A Multi-Task Learning Approach for Delayed Feedback Modeling* — https://dx.doi.org/10.1145/3487553.3524217

Off-policy evaluation:
8. *A Complete Tutorial on Off-Policy Evaluation for Recommender Systems* — https://towardsdatascience.com/a-complete-tutorial-on-off-policy-evaluation-for-recommender-systems-e92085018afe/
9. SNIPS overview (ESS diagnostic, variance behavior) — https://www.emergentmind.com/topics/self-normalized-inverse-propensity-scoring-snips
10. *Additive Control Variates Dominate Self-Normalisation in OPE* (β*-IPS) — https://arxiv.org/html/2602.14914v3
11. *Doubly Robust OPE for Ranking Policies under the Cascade Behavior Model* — https://arxiv.org/pdf/2202.01562
12. Saito et al. — *Open Bandit Dataset and Pipeline* — https://arxiv.org/pdf/2008.07146 ; library: https://github.com/st-tech/zr-obp
13. Saito & Joachims — KDD'22 tutorial, *Counterfactual Evaluation and Learning for Interactive Systems* — https://counterfactual-ml.github.io/kdd2022-tutorial/

Uplift / incrementality / feedback loops:
14. Johnson, Lewis & Nubbemeyer — *Ghost Ads: Improving the Economics of Measuring Online Ad Effectiveness* (JMR 2017) — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2620078 ; NBER draft: https://conference.nber.org/confer/2016/EoDs16/Johnson_Lewis_Nubbemeyer.pdf
15. Remerge — *Incrementality Tests 101: ITT, PSA, Ghost Ads, Ghost Bids* — https://www.remerge.io/blog-post/incrementality-tests-101-intent-to-treat-psa-ghost-ads-and-ghost-bids
16. SegmentStream — *Incrementality Measurement Guide (2026)* — https://segmentstream.com/blog/articles/incrementality-measurement-guide
17. INCRMNTAL — *Proving Marketing Incrementality with Uplift Modeling* — https://www.incrmntal.com/resources/how-to-use-uplift-modeling
18. Chaney, Stewart & Engelhardt — *How Algorithmic Confounding in Recommendation Systems Increases Homogeneity and Decreases Utility* — https://www.researchgate.net/publication/320754991
19. Mansoury et al. — *Feedback Loop and Bias Amplification in Recommender Systems* — https://ar5iv.labs.arxiv.org/html/2007.13019
20. Chen et al. — *Bias and Debias in Recommender System: A Survey* — https://arxiv.org/pdf/2010.03240

Bandits / exploration / elicitation:
21. *A Comparative Study of UCB and Thompson Sampling* — https://www.itm-conferences.org/articles/itmconf/pdf/2025/11/itmconf_acaai2025_02004.pdf
22. Agrawal & Goyal — *Analysis of Thompson Sampling for the Multi-armed Bandit Problem* — http://proceedings.mlr.press/v23/agrawal12/agrawal12.pdf
23. Kaufmann — *On Bayesian Index Policies for Sequential Resource Allocation* — https://arxiv.org/pdf/1601.01190
24. *Optimization of Epsilon-Greedy Exploration* (Netflix-affiliated exploration scheduling) — https://arxiv.org/html/2506.03324
25. *Online Matching: A Real-time Bandit System for Large-scale Recommendations* (1–2% exploration traffic) — https://arxiv.org/pdf/2307.15893
26. McInerney et al. (Spotify) — *Explore, Exploit, and Explain* — https://dl.acm.org/doi/10.1145/3240323.3240354
27. *Pairwise and Attribute-Aware Decision Tree-Based Preference Elicitation for Cold-Start Recommendation* — https://arxiv.org/abs/2510.27342
28. *Cold-Start Active Preference Learning in Socio-Economic Domains* — https://arxiv.org/pdf/2508.05090
29. *Explainable Active Learning for Preference Elicitation* — https://arxiv.org/pdf/2309.00356

Negative signals / position bias:
30. Hu, Koren & Volinsky — *Collaborative Filtering for Implicit Feedback Datasets* (ICDM'08) — https://dl.acm.org/doi/10.1109/ICDM.2008.22
31. Kula — *WARP Loss for Implicit-Feedback Recommendation* — https://building-babylon.net/2016/03/18/warp-loss-for-implicit-feedback-recommendation/
32. *Counterfactual Risk Minimization with IPS-Weighted BPR* — https://arxiv.org/pdf/2509.00333
33. Ding et al. — *Reinforced Negative Sampling for Recommendation with Exposure Data* (IJCAI'19) — https://www.ijcai.org/proceedings/2019/0309.pdf
34. *Correct and Weight: A Simple Yet Effective Loss for Implicit Feedback Recommendation* — https://arxiv.org/html/2601.04291
35. *When Inverse Propensity Scoring Does Not Work: Affine Corrections for Unbiased Learning to Rank* — https://arxiv.org/pdf/2008.10242
36. *Doubly Robust Estimation for Correcting Position Bias in Click Feedback* (TOIS) — https://dl.acm.org/doi/10.1145/3569453
37. *Position Bias Estimation for Unbiased Learning-to-Rank in eCommerce Search* — https://arxiv.org/pdf/1812.09338

Per-user normalization:
38. kiwidamien — *Shrinkage and Empirical Bayes to Improve Inference* — https://kiwidamien.github.io/shrinkage-and-empirical-bayes-to-improve-inference.html
39. Wheeler — *Sorting Rates Using Empirical Bayes* — https://andrewpwheeler.com/2018/07/23/sorting-rates-using-empirical-bayes/
40. *A General Framework for Empirical Bayes Estimation in Discrete Linear Exponential Family* — https://arxiv.org/pdf/1910.08997

Temporal / seasonal:
41. Koren — *Collaborative Filtering with Temporal Dynamics* — https://dl.acm.org/doi/pdf/10.1145/1721654.1721677
42. *Recommender System Based on Temporal Models: A Systematic Review* — https://www.mdpi.com/2076-3417/10/7/2204
43. *Modelling Concept Drift in Dynamic Data Streams for Recommender Systems* (ACM TORS) — https://dl.acm.org/doi/10.1145/3707693
