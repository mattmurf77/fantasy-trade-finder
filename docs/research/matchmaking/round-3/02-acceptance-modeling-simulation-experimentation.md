# Round 3 — Predicting Acceptance, Simulating the League, and Experimenting in Interfering Markets

> Research memo, 2026-08-16. Closes the three interlocking gaps round-2/03 §7 flagged: (1) acceptance
> probability as a supervised learning problem, (2) agent-based league simulation as a policy
> pre-screen, (3) experimentation when every suggestion changes every other pair's feasible set.
> Round 1 established the matching architecture; round 2 established reciprocal scoring, funnel-label
> training, and ghost holdouts. This memo is about *learning whether they work*.
>
> **Confidence tags:** `[verified]` primary source read in full this session · `[verified-2°]` read via
> a secondary page or search summary this session · `[known-unverified]` canonical work cited from
> established knowledge, URL/identifier **not** re-fetched this session — check the identifier before
> citing externally · `[inference]` my synthesis, not any source's claim.
>
> **⚠️ Coverage caveat, stated up front.** This memo was researched by three parallel sweeps. The
> Part-1 (acceptance) and Part-3 (experimentation) sweeps completed. **The Part-2 (simulation) deep
> sweep did not return.** Part 2 below is built from what I verified directly (Thumbtack's production
> simulator, the transplant-allocation literature, the automated-negotiation literature) plus canonical
> simulator work cited from knowledge and tagged `[known-unverified]`. Section 6 lists exactly what
> is still owed. Do not treat Part 2's citation set as being at the same verification standard as
> Parts 1 and 3.

## Contents

1. [Best practices](#1-best-practices)
2. [Antipatterns](#2-antipatterns)
3. [What matters most (ranked)](#3-what-matters-most-ranked)
4. [What doesn't matter (even though it seems like it should)](#4-what-doesnt-matter-even-though-it-seems-like-it-should)
5. [Transfer notes for FTF](#5-transfer-notes-for-ftf)
6. [Not researched / follow-up topics](#6-not-researched--follow-up-topics)
7. [Sources](#7-sources)

---

## 1. Best practices

### Part A — Acceptance-probability modeling

#### 1.1 Make acceptance a supervised target in its own right; nobody in fantasy has

The clearest finding in Part 1 is a negative one, and it is FTF's opening. **Both published
fantasy-trade systems optimize trade *quality* and neither models acceptance.** `[verified]`

- **IBM/ESPN (arXiv 2111.02859)** — abstract read in full. Pipeline: an ensemble player valuation
  (QSVC-PI, QSVC-ALE, VQC-PI, HQNN-PI, XGB, SME rules), personalized by league rules and roster →
  teams paired by **cosine dissimilarity** → **0-1 knapsack** picks the outgoing side → postprocessors
  score six objective measures. Validation is **24 IBM/ESPN experts across 10 "Football Error Analysis
  Tool" sessions**, moving 76.9% → 97.3% "high-quality trades." There is **no acceptance label, no
  acceptance model, and no deployed acceptance rate anywhere in the paper.** Expert-judged quality is
  the entire evaluation.
- **Parshall, Ali & Zimmerman (arXiv 2511.17535, Nov 2025)** — genetic algorithm whose cost function is
  playoff-weighted user gain + opponent gain − fairness penalty, explicitly to preserve *"apparent
  fairness for negotiation."* Also no acceptance model. Evaluated on **one** 12-team ESPN league at
  Week 8, 2025 (both sides gained ~3 projected points/week).
- **Dynasty Dealmaker** ships a **"Trade Acceptance Probability: High"** badge and a **"98% Fair"**
  number with **zero disclosed methodology** — no data sources, no model, no evidence of historical
  acceptance data. `[verified]` An ordinal label rendered as a probability is a UI affordance, not a
  model. Treat the competitor claim as unbacked until shown otherwise.

Meanwhile every mature two-sided marketplace that faced this problem **did** build the supervised
model, and it paid:

| Domain | Target | Model | Result |
|---|---|---|---|
| **Airbnb** | P(host accepts this guest request) | L2-regularized logistic regression | **+3.75% booking conversion**, ~+1% more later `[verified]` |
| **Upwork** | P(freelancer accepts an invite), used as an *availability* proxy | not disclosed | used in two-sided matching `[verified-2°]` |
| **Transplant allocation** | P(center accepts this organ offer) | XGBoost > LR | AP 0.0645 → 0.0940 `[verified]` |
| **Freight** | P(carrier accepts this tender) | vendor GBMs | industry-standard practice `[verified-2°]` |
| **Recruiting** | P(candidate accepts this offer) | ensemble ML | Greenhouse "Offer forecast" `[verified]` |

**Practice:** acceptance is a *different function* from fairness. Model it separately, then combine.
The fairness gate answers "should this trade exist?"; the acceptance model answers "will this manager
say yes?" FTF's existing `user_gain_epsilon` machinery is the former and cannot substitute for the latter.

#### 1.2 The feature families that actually carry signal — in the order the literature ranks them

Across five independent domains the same four families recur, and the ordering is remarkably stable.

**(a) Counterparty history — the strongest and most reusable family.** `[verified]`
Airbnb's model is *entirely* built from this: for each trip characteristic (check-in/check-out gap,
advance notice, party size, weekend vs. weekday, geography), compute **that host's historical mean
acceptance rate for that characteristic** and feed each as an independent feature. The kidney work's
single largest feature-engineering win, likewise, was **historical OPO–transplant-hospital *pair*
acceptance patterns** — not donor or candidate biology, but *who has said yes to whom before*.
Freight vendors' first-listed feature is "carrier + service level plus tender acceptance history on
that lane."

**(b) Operational / logistical features that seem irrelevant.** `[verified]` The kidney paper's
headline surprise: adding **transportation features (proximity to commercial airports)** raised the
best model's average precision by **~45.7% over baseline** (0.0645 → 0.0940), a bigger lift than
switching from logistic regression to XGBoost bought on its own. In freight, C.H. Robinson found
**distance and volatility were *not* strong determinants** of rejection, while **lead time was** —
short lead times drive rejections because carriers pre-book. The lesson generalizes: the friction
of *acting* on the offer often predicts better than the merits of the offer.

**(c) Counterparty state and outside options.** `[verified-2°]` Freight's canonical framing: a carrier
rejects for one of two reasons — no capacity, or **a better alternative in the spot market**. Rejected
loads move at **+14.8%** on spot; long-run rejection rates swing from **6.69% (May 2025) to ~25%
(early 2021)** purely on market conditions, with the same loads and the same carriers. The recruiting
literature says the same thing in different words: *"offer acceptance is decided in the interview, not
at offer"* — by the time terms are on the table the counterparty's disposition is largely set, and the
predictive signals are decision-timeline cues and competing offers `[verified]`.

**(d) Offer terms — real, but weaker than intuition suggests, and non-linear in form.** `[verified-2°]`
eBay's Best Offer corpus (88–98M listings, >25M with buyer offers) shows the terms matter mostly
through *relational* framing, not absolute generosity: **~1/3 of bargaining threads end in immediate
agreement**; the rest end in disagreement or delayed agreement; and the most robust regularity that
standard theory cannot explain is a **strong preference for offers that split the difference between
the two most recent offers**, alongside reciprocal and gradual concession. The companion cheap-talk
paper is sharper still: items listed at **multiples of $100 sell for 5–8% less but receive offers
6–11 days sooner and are 3–5% more likely to sell** `[verified]`. **The *form* of the number is itself
a signal of flexibility.** Offer design is partly a communication problem, not only a value problem.

#### 1.3 At FTF's sample size, use a penalized linear model — the evidence against fancy ones is strong

- **Christodoulou et al. (2019), 71 studies, 282 comparisons** `[verified]`: for the **145 comparisons
  at low risk of bias, the difference in logit(AUC) between logistic regression and ML was 0.00
  (95% CI −0.18 to 0.18)**. ML looked better *only* in the 137 high-risk-of-bias comparisons (+0.34).
  Median study: 1,250 participants, **median 8 events per predictor**. Their conclusion: "no evidence
  of superior performance of ML over LR."
- **Riley's sample-size framework** `[verified-2°]` replaces EPV≥10 with three criteria — shrinkage
  factor ≥0.9, small optimism in apparent R², precise estimate of overall risk. Worked example in the
  cited primer: **15 candidate predictors at 3% prevalence requires 5,795 observations (174 events)**.
  Explicit guidance: *"Rules-of-thumb for sample size calculations should be avoided."*
- **van der Ploeg et al., "Modern modelling techniques are data hungry"** `[known-unverified]`: random
  forests, SVMs and neural nets need far more events per variable than logistic regression to reach
  stable performance.
- **Firth penalized logistic regression** `[verified-2°]` is the right small-N/separation-safe default —
  **but** it "biases predicted probabilities toward 1/2, and the stronger the outcome imbalance the more
  severe the bias." If you use Firth for *prediction* rather than effect estimation, apply the FLIC
  (post-hoc intercept correction) or FLAC (iterative data-augmentation) variants that restore calibration.

**Practice:** Airbnb — a company with vastly more data than FTF will ever have per league — shipped
**L2-regularized logistic regression** and explicitly *rejected* collaborative filtering because "no two
trips are ever identical" and hosts give **conflicting votes for identical characteristics at different
times**. That is precisely FTF's situation with managers and trades. Start there.

#### 1.4 Calibration: parametric only, and re-fit it as a first-class artifact

`[verified]` scikit-learn's own guidance is explicit: **isotonic "will perform as well as or better
than sigmoid when there is enough data (greater than ~1000 samples) to avoid overfitting"** and is
"more prone to overfitting, especially on small datasets." Below that, use Platt (sigmoid) or beta
calibration — few parameters, sample-efficient, and (sigmoid being strictly monotonic) ranking metrics
are preserved. FTF will be under 1,000 labeled trade decisions for a long time; **isotonic is off the
table**, and this is a decision, not a default.

#### 1.5 Borrow strength across managers — hand-rolled empirical Bayes is enough

`[verified]` Airbnb's sparsity fix is worth copying verbatim: **~26% of hosts had no data for a given
characteristic**, so they blended the host's own rate with the **regional median preference** using a
weight that **decays monotonically as the host's own observations accumulate**. That is empirical-Bayes
shrinkage implemented in a few lines, and it solves cold-start and noise in one move. The hierarchical /
partial-pooling literature is the formal version: group-level parameters drawn from a population
distribution, with shrinkage strength set by how much data each group has `[verified-2°]`.

For FTF, the natural hierarchy is **league → manager → (manager × trade-archetype)**.

#### 1.6 Treat "acceptance strategy" as a modeled component, not an emergent one

`[verified]` The automated-negotiation field (Baarslag et al.'s survey of opponent modeling) decomposes
every negotiating agent into three parts: **bidding strategy | opponent model | acceptance strategy** —
acceptance is a first-class module. Their opponent models learn four distinct things: the counterparty's
**preference profile, acceptance strategy, bidding strategy, and deadline/reservation value.** Canonical
acceptance rules include **AC_next** (accept if the offer on the table beats what you were about to
propose next) and combined variants, plus optimal-stopping formulations.

Two things transfer. First, the four-way decomposition is a good schema for FTF's counterparty model.
Second — and this is the field's most useful warning — **a more accurate opponent model does not
reliably produce better negotiation outcomes.** Accuracy and performance come apart, because of
computational overhead and exploitation risk. Optimize acceptance *decisions*, not acceptance *AUC*.

#### 1.7 Choose the target label deliberately; the obvious one may be unlearnable

`[verified]` The kidney authors' most useful recommendation is a reframing. Per-candidate acceptance is
brutally imbalanced (**~105:1**), and despite **AUROC 0.833** their models "never eclipsed a 10% average
precision" — at 10% recall, 21% precision. Their proposal: **stop predicting "will *this* recipient
accept" and predict instead "will this organ be accepted by sequence number N — early or late in the
match run."** Same data, a far more learnable target, and it still supports the operational decision.

They also flag: **non-stationarity** (their training window straddled a policy change and COVID),
**equity failures** (worst performance for Black candidates; **zero correctly predicted accepts for
pediatric candidates** — so use separate models for low-volume subgroups), and **label ambiguity**
(the "decision" is made by a team of coordinators, specialists and surgeons, none of it in the data).
Their verdict on their own work: *"we do not believe this meets a threshold for clinical application."*

---

### Part B — Agent-based league simulation as a policy testbed

> ⚠️ **Verification standard is lower in this section** — see the coverage caveat at the top. Claims
> tagged `[known-unverified]` are canonical and I state them with confidence, but their identifiers
> were not re-fetched this session.

#### 1.8 The production reality check: the "simulator" a real marketplace shipped is a replay harness

`[verified]` Thumbtack — a two-sided marketplace with a mature ML ranking stack — publishes a system
they call **the Simulator**. It is *not* an agent-based behavioral model. It records production HTTP
requests/responses to BigQuery, then **replays historical customer search requests** against a
candidate build and diffs the output through three comparators (**Response** = full body, **List** =
ranking order, **Set** = which pros are returned, order-ignored). Its documented catch was a
floating-point/map-iteration-order bug that swapped adjacent professionals.

Two lessons, both important. **(a)** Trace-driven replay is cheap, trustworthy, and catches a real class
of bug that no behavioral simulator catches. Build it first. **(b)** The post **never discusses
validating simulator conclusions against A/B results** — because it does not claim to predict behavior.
The industry's shipped simulators are mostly regression harnesses; behavioral simulators are a research
artifact. Calibrate expectations accordingly.

#### 1.9 Trace-driven replay beats synthetic generation — and the market-design field already settled this

Round-2/01 established the kidney-exchange practice in depth and it stands: **trace-driven replay of
real historical arrivals under counterfactual policies** is where credibility comes from, with
generator-based synthesis (Saidman-style draws from blood-type and sensitization distributions) as the
benchmark supplement. Registry simulators additionally model **per-center acceptance heterogeneity
("center selectivity")** — the direct analogue of per-manager accept thresholds. See
[round-2/01 §Simulating small matching markets](../round-2/01-thin-markets-and-multiparty-matching.md).
`[established in round 2]`

What round 3 adds: the kidney *offer-acceptance* paper gives you the **empirical basis for calibrating
those thresholds** — historical OPO–TXH pair acceptance patterns are the highest-value behavioral
feature, and they are exactly the kind of thing a simulator's agents should be parameterized on
rather than guessed at `[verified]`.

#### 1.10 The recommender-simulator canon: useful patterns, well-known limits

`[known-unverified]` The reusable design pattern is consistent across **RecSim** (arXiv 1909.04847),
**RecSim NG** (arXiv 2103.08057), **RecoGym** (arXiv 1808.00720) and **Virtual-Taobao** (arXiv 1805.10000):
separate the simulator into **(i) a user/agent state**, **(ii) a choice model** mapping presented slate ×
state → response, and **(iii) a transition model** updating state after the response. Keep those three
swappable; the whole value of the architecture is that you can vary one and hold the others fixed.

The critique literature is the part to internalize, not the tooling. **Krauth et al., "Do Offline Metrics
Predict Online Performance in Recommender Systems?"** (arXiv 2011.07931) is the canonical result that
offline/simulated metrics and online outcomes decouple `[known-unverified]`. The general form of the
problem: **a simulator rewards what you coded into it.** If you hard-code "managers accept when
perceived gain ≥ ε," then any policy that maximizes perceived gain will look brilliant in simulation,
and you have learned nothing except that your optimizer works.

LLM-agent user simulators (e.g. **Agent4Rec**, arXiv 2310.10108) are the 2024–26 fashion
`[known-unverified]`; the Part-3 sweep surfaced the marketplace-flavored descendants — **SimGym**
(arXiv 2605.19219) reports **77% directional alignment** with observed add-to-cart shifts, and
**Agent A/B** (arXiv 2504.09723) `[verified-2°, flagged]`. Note that "directional alignment" against a
50% chance baseline is a weak bar, and LLM agents are known to be agreeable in ways real users are not.

#### 1.11 What makes a simulator trustworthy: validation is the deliverable, not the simulator

`[known-unverified]` for the ABM-methodology canon (Windrum/Fagiolo/Moneta's JASSS treatment of
empirical validation; Grimm et al.'s pattern-oriented modelling; simulated-method-of-moments and ABC
approaches to calibration), `[inference]` for the FTF-specific instantiation. The validation ladder:

1. **Face validity** — a domain expert (the operator) watches simulated seasons and says "yes, that's
   what a dynasty league looks like."
2. **Stylized-fact / pattern matching** — the sim must reproduce aggregate regularities it was *not*
   fit to: the distribution of trades per league-season, the share of leagues with zero trades, the
   heavy-tailed concentration of trades among a few active managers, the seasonal shape (deadline spike).
3. **Held-out backtest** — fit agent parameters on leagues 1..k, replay leagues k+1..n's *real* history
   under the sim's behavior model, and check calibration of predicted vs. actual accepts.
4. **Sensitivity analysis** — sweep each parameter and report which conclusions survive. Conclusions
   that flip under a ±20% threshold perturbation are simulator artifacts, not findings.
5. **Docking** — implement the same policy comparison two ways and check they agree.

**Rule:** a simulator's output is only admissible for decisions on the dimensions where step 3 passed.

#### 1.12 Calibrate accept thresholds from behavior, don't assert them

`[verified]` The two mechanisms that actually give you calibrated agents:
- **Per-agent historical acceptance rates with shrinkage to a population prior** (the Airbnb pattern,
  §1.5) — each simulated manager's threshold is drawn from a posterior fit to that manager's real
  accept/reject history where it exists, and from the league/global prior where it doesn't.
- **Outside-option modeling** (the freight pattern, §1.2c) — an agent should reject a *good* offer when
  a better one is visible. Any simulator that models acceptance as a function of the offer alone will
  systematically overstate accept rates, because it has removed the main reason real counterparties
  say no.

---

### Part C — Experimentation under interference

This section is drawn from the completed Part-3 sweep. Confidence tags follow that sweep's ledger.

#### 1.13 FTF gets the hard part free — and that changes which literature applies

`[inference, well-grounded]` The graph-cluster-randomization literature exists to solve a problem FTF
does not have: how to cut a connected social graph into low-leakage clusters. **A league *is* a cluster
with zero edge leakage.** Ugander et al.'s clustering machinery is therefore inapplicable; what transfers
is the **estimand framing** — target the **total average treatment effect** (what happens if the feature
ships to everyone) rather than an individual-level ATE `[verified by sweep]`.

More consequentially: **partial interference — spillover only within cluster — is literally true for
FTF, not an approximation.** That makes the entire **Hudgens & Halloran (JASA 2008)** apparatus *valid*
rather than merely convenient, including two-stage randomized-saturation designs and their clean
decomposition into direct, indirect, total and overall effects `[verified by sweep]`.

The one leakage channel worth checking: **managers who play in multiple FTF leagues.** That is the only
plausible cross-cluster edge, and it is empirically checkable today.

#### 1.14 Expect naive A/B to overstate the effect — by a lot

Two anchors, both empirical rather than simulated:
- **Airbnb pricing meta-experiment** (Holtz et al., *Management Science* 2025): **at least 19.76%** of
  the TATE estimate from individual randomization is interference bias, eliminated by cluster
  randomization `[verified by sweep, "at least" is the authors' own qualifier]`.
- **Lyft** (Chamandy): a two-passenger/one-driver worked example where user-level randomization
  produced a **200% estimated effect against a 33% true effect — a ~6× overestimate** `[verified by sweep]`.

FTF's substitutability is *far* higher than Airbnb's (12 managers competing for one asset vs. a city of
listings), so read **~20% as a floor and 6× as the ceiling** `[inference]`. The mechanism is identical:
a treated manager who executes a suggested trade **consumes the asset**, degrading the control manager's
counterfactual and inflating the measured treatment benefit.

#### 1.15 Two-sided design theory says randomize on the *asset* side, not the manager side

`[verified by sweep]` **Johari, Li, Liskovich & Weintraub (arXiv 2002.05670, Mgmt Sci 2022)**: the
bias-optimal randomization side is determined by **market balance**. In demand-constrained markets,
customer randomization is unbiased and listing randomization is biased; in supply-constrained markets,
the reverse. **Li et al. (arXiv 2104.12222, WWW '22)** adds the practitioner's corollary: choosing the
bias-optimal side **costs almost nothing in variance** (sometimes it is also variance-optimal) — so take
it — but the **treatment proportion is a genuine bias–variance tradeoff, and the bias-minimizing
proportion is generally not 50/50.**

**A dynasty league is asset-constrained, not manager-constrained** — there is one Ja'Marr Chase and
twelve people who want him `[inference]`. By this theory, **randomizing on the asset/listing side is
the less-biased choice and randomizing on managers is the more-biased one** — a direct inversion of the
default instinct.

#### 1.16 Manufacture units; you do not have enough leagues

`[verified by sweep]` Standard cluster-RCT arithmetic (MDE ≈ (z₁₋α/₂+z₁₋β)·σ_cluster·√(2/k)) gives:

| Leagues | k/arm | MDE (cluster-level σ) | with small-df t-crit |
|---|---|---|---|
| 20 | 10 | 1.25σ | ~1.4σ |
| 40 | 20 | 0.89σ | ~0.93σ |
| 50 | 25 | 0.79σ | ~0.83σ |

**At 40 leagues you can only detect effects near one full cluster-level standard deviation** — a change
you would see without an experiment. League-level cluster randomization at FTF's N is not an
underpowered experiment; for realistic effect sizes it is *not an experiment*. The CRT sample-size
literature is consistent that **cluster *count* dominates cluster *size***: 40→80 leagues roughly halves
MDE; 10→12 managers per league does almost nothing.

The unit-multiplication ladder, in payoff order:
1. **Budget-split design** (Liu, Mao & Kang, arXiv 2012.08724) — splits the *budget*, not the buyers,
   and claims to be more powerful than all other unbiased designs. **A dynasty roster *is* a budget: a
   fixed, finite asset pool.** Partitioning each manager's tradeable pool (or the engine's candidate
   inventory) into treatment and control halves converts between-manager interference into
   within-manager, and keeps all 12 managers in every league contributing to both arms.
   `[verified paper; the roster analogy is my inference and is untested — flagged]`
2. **Dyad-level randomization** (Bajari et al., Multiple Randomization Designs, arXiv 2112.13495) —
   assigns interventions and measures outcomes at the **pair** level, separately identifying main,
   direct and spillover effects under a local-interference assumption. A 12-team league has **66 ordered
   dyads**; 40 leagues gives **2,640 dyad-units** vs. 40 league-units. ⚠️ Local interference may be
   violated for FTF, since assets are consumed league-wide rather than dyad-wide — check before relying on it.
3. **League × time switchbacks** — but **simulate the power first.** Pankratev (arXiv 2606.03012) shows
   switchback power hinges on outcome **autocorrelation**, and under strong positive within-period
   autocorrelation the advantage evaporates. Dynasty trade activity is heavily autocorrelated (waiver
   cycles, byes, deadline). Statsig's worked example — a 2-week experiment with 1-hour windows and 5
   clusters yields only **1,680 units, potentially underpowered** — is the right sanity arithmetic.
   Burn-in/burn-out at window boundaries matters acutely here: a trade suggested at 11:58pm is acted on
   the next morning.

#### 1.17 Design and inference that actually work at N=40

`[verified by sweep]`
- **Matched-pair cluster assignment + CUPED is the design I'd run.** Pair leagues on pre-period trade
  volume, roster activity and manager count; randomize within pair; analyze with a **within-pair
  permutation test** (finite-sample valid for the sharp null). This directly addresses MacKinnon &
  Webb's warning that randomization inference degrades when treated clusters are *atypical* — with 20
  of 40 leagues treated, two unusually active leagues can drive everything. CUPED then strips variance
  using pre-period outcomes; league trade volume is highly autocorrelated season-to-season, so if
  ρ≈0.8, residual σ falls by √(1−0.64)=0.6, taking the 40-league MDE from ~0.93σ to **~0.56σ**.
  ⚠️ Compute ρ on FTF's own data — the widely-circulated "CUPED cuts sample size 30–40%" figure could
  not be traced to a primary source.
- **Randomization inference, always.** **Athey, Eckles & Imbens (JASA 2018)** give **exact p-values for
  non-sharp nulls about spillovers in a single connected network** — finite-sample valid at any N. FTF
  controls the assignment mechanism, so the randomization distribution can be enumerated or simulated
  directly. **Never report plain cluster-robust t-statistics at N=40**; CRVE t-tests severely over-reject
  with few treated clusters.
- **If you must run a regression, use wild cluster bootstrap-t** (Cameron/Gelbach/Miller;
  MacKinnon & Webb). Its key precondition — **cluster sizes similar regardless of treatment** — FTF
  satisfies by construction (10–12 managers everywhere). `fwildclusterboot` (R) / Stata `wildbootstrap`.
- **Exposure mappings, then Hájek not Horvitz–Thompson.** Aronow & Samii's framework wants an explicit
  exposure mapping — for FTF plausibly `(own treatment, # treated managers in my league, whether the
  manager holding my target asset is treated)`. HT weighting is design-unbiased but notoriously
  high-variance; use the self-normalized Hájek form at N=40. And read Sävje/Aronow/Hudgens on
  **misspecified exposure mappings** first, because FTF will certainly misspecify.
- **Pick one question per experiment.** Baird, Bohren, McIntosh & Özler (*REStat* 2018) prove the
  tradeoff formally: **power to detect the ATE declines exactly as you gain the ability to identify
  spillovers.** At 40 clusters FTF can buy one, not both. Their randomized-saturation power software
  (World Bank) is directly usable.
- **Reframe most questions as non-inferiority.** Georgiev's small-sample guidance: a 20% non-inferiority
  margin needs **12,000–35,000 users at 90% power** versus hundreds of thousands for superiority; and at
  small N, raising α (his worked example moves to **α=0.15**) is the honest lever. Most FTF roadmap
  questions are "does this not hurt trade volume?", which is answerable; "does this help by X%" mostly isn't.

#### 1.18 Measure your own interference bias once, then stop guessing

`[verified by sweep]` The **meta-experiment** design (Saveski et al. KDD 2017; the mechanism Holtz et al.
used at Airbnb) is FTF's highest-value single experiment: run a **Bernoulli-randomized arm and a
league-randomized arm concurrently** and difference the TATE estimates. A significant difference is
direct evidence of network effects; **no difference licenses years of cheap user-level tests.** It is
the rare experiment whose result is a standing policy rather than a feature decision. Run it once.

---

## 2. Antipatterns

**Acceptance modeling**

1. **Shipping an "acceptance probability" that is a fairness score with a new label.** This is the
   observable state of the fantasy market (Dynasty Dealmaker's "Trade Acceptance Probability: High"
   next to "98% Fair", with no methodology). If the number moves only when fairness moves, it is
   fairness. `[verified]`
2. **Validating with expert panels instead of outcomes.** IBM/ESPN's 97.3% is 24 experts' opinion of
   trade quality. It is a real signal about *quality* and zero signal about *acceptance*. `[verified]`
3. **Reading AUROC and declaring victory.** The kidney models hit **AUROC 0.833 with average precision
   under 0.10** at ~105:1 imbalance. Under imbalance, ROC is nearly uninformative; **report
   precision-recall and calibration**, and state the operating point (theirs: 21% precision at 10% recall).
   `[verified]`
4. **Reaching for gradient boosting at small N.** No benefit over logistic regression in 145 low-bias
   comparisons; ML is more data-hungry, not less. `[verified]`
5. **Isotonic calibration below ~1,000 samples.** Explicitly warned against; it overfits.  `[verified]`
6. **Using raw Firth predictions for probabilities.** Firth stabilizes coefficients but **biases
   predicted probabilities toward 1/2 under imbalance** — use FLIC/FLAC. `[verified-2°]`
7. **Modeling acceptance as a function of the offer alone.** Ignoring outside options is the single
   biggest structural error; freight rejection swings 6.69%→25% on market conditions with the same
   offers. `[verified-2°]`
8. **One global model across heterogeneous subgroups.** The kidney model produced **zero correctly
   predicted accepts for pediatric candidates** and performed worst for Black candidates. Low-volume
   segments need their own model or an explicit abstention. `[verified]`
9. **Optimizing opponent-model accuracy as the objective.** The negotiation survey's finding is that
   accuracy and negotiation performance come apart. `[verified]`

**Simulation**

10. **Coding the accept rule you intend to optimize against.** If agents accept when perceived gain ≥ ε
    and the policy maximizes perceived gain, the simulation is a tautology. `[inference, grounded in the
    offline/online decoupling literature]`
11. **Trusting a simulator on dimensions it was never validated on.** Validation is per-dimension; a sim
    that reproduces trade *counts* says nothing about trade *composition*. `[inference]`
12. **Treating LLM agents as calibrated stand-ins for managers.** Directional alignment near chance-plus
    is not calibration, and LLM agents are systematically agreeable. `[verified-2°, flagged]`
13. **Reporting a single simulator configuration.** Without a sensitivity sweep you cannot distinguish a
    finding from a parameter artifact. `[known-unverified methodology canon]`
14. **Skipping the boring replay harness.** Thumbtack's shipped simulator is trace replay and it caught a
    real float/map-ordering ranking bug. Behavioral simulation is the expensive second step. `[verified]`

**Experimentation**

15. **Naive user-level A/B on a trade-suggestion feature.** Expect overstatement between ~20% and ~6×.
    `[verified by sweep]`
16. **League-level cluster randomization as the default "rigorous" answer.** Unbiased and useless is
    still useless at MDE ≈ 0.9σ. `[verified by sweep]`
17. **Cluster-robust t-statistics at 40 clusters.** Severe over-rejection with few treated clusters; use
    randomization inference or wild cluster bootstrap-t. `[verified by sweep]`
18. **Defaulting to a 50/50 split.** The bias-minimizing treatment proportion for a cannibalization-prone
    feature is generally not balanced. `[verified by sweep]`
19. **Assuming switchbacks rescue power.** They don't automatically; under strong autocorrelation the
    advantage evaporates, and practitioners routinely use far fewer periods than needed. `[verified-2°]`
20. **Trying to measure the main effect and the spillover in one experiment.** Formally impossible to
    optimize both at a fixed cluster count. `[verified by sweep]`
21. **Growing leagues instead of league count.** Power scales with cluster count, not cluster size.
    `[verified by sweep]`
22. **Building an OPE pipeline that needs hyperparameter tuning.** Voloshin et al.: *"hyperparameter
    tuning is not practical for OPE due to a lack of validation signal."* `[verified by sweep]`

---

## 3. What matters most (ranked)

1. **Logging the acceptance label, with propensities and exposure, starting now.** Every technique in
   this memo — supervised acceptance, simulator calibration, OPE, randomization inference — consumes
   the same instrumentation, and none of it can be reconstructed retroactively. This is round-2/03's
   conclusion and round 3 only sharpens it.
2. **Counterparty acceptance history as the feature backbone.** The strongest family in Airbnb, the
   transplant registry, and freight alike. Per-manager × per-archetype accept rates, shrunk to a
   league/global prior.
3. **Modeling the counterparty's outside option.** The most under-appreciated structural feature and the
   one that separates an acceptance model from a fairness score. In a 12-team league, the alternative
   trades available to the counterparty are fully enumerable — FTF can compute this exactly, which
   almost no other domain can.
4. **Choosing a learnable target.** Per-suggestion acceptance may be too sparse; the kidney reframe
   ("accepted by sequence N", or FTF's "any trade executed with this partner within 14 days") converts
   an unlearnable label into a learnable one.
5. **Penalized logistic regression + Platt/beta calibration + hierarchical shrinkage.** The whole model
   stack, and the evidence says nothing fancier will beat it at FTF's N.
6. **Measuring FTF's own interference bias once, via a meta-experiment.** Converts an open methodological
   question into a standing policy.
7. **Matched-pair league assignment + CUPED + randomization inference.** The only design/inference
   combination that is both valid and non-trivially powered at 20–50 leagues.
8. **A trace-driven replay harness before any behavioral simulator.** Cheap, catches real bugs, and is
   the substrate the behavioral simulator later plugs into.
9. **A validated league simulator with held-out backtesting.** High ceiling — FTF's domain is far more
   simulatable than e-commerce UI because valuations, rosters and rules are explicit — but only credible
   after step 8 and the §1.11 validation ladder.
10. **Non-inferiority framing for most roadmap decisions.** Changes what is answerable at current scale.
11. **Growing league count as a measurement investment.** 40→80 halves MDE; it is the only lever that
    moves the power floor.
12. **Formal OPE (FQE/DR/OBP).** Real, but latest-payoff; and Voloshin's finding that **policy divergence
    degrades OPE ~100× versus ~10× for horizon** means the actionable step today is simply *keep the
    logging policy stochastic and close to the evaluation policy.*

---

## 4. What doesn't matter (even though it seems like it should)

1. **Model sophistication.** Zero difference between ML and logistic regression across 145 low-bias
   comparisons. Airbnb shipped L2 logistic regression and got +3.75% conversion. `[verified]`
2. **Opponent-model accuracy as an end.** More accurate opponent models do not reliably negotiate
   better. `[verified]`
3. **AUROC.** Near-useless under the imbalance acceptance modeling actually has. `[verified]`
4. **Sheer offer generosity, relative to framing.** eBay's corpus says the *relational* structure of the
   offer (split-the-difference, reciprocal concession) and even the **roundness of the number** carry
   signal that raw generosity does not — round-numbered listings sell **3–5% more often** while
   realizing **5–8% less**. `[verified]`
5. **Distance/volatility-type "obvious" difficulty features.** C.H. Robinson found neither predicted
   tender rejection; **lead time** did. The analogue: roster-need mismatch may matter less than *when*
   and *how easily* a manager can act. `[verified]`
6. **Cluster size / managers per league.** Power scales with cluster count. Adding managers is nearly
   worthless for measurement. `[verified by sweep]`
7. **Graph-clustering algorithms.** The largest body of interference literature, and FTF needs none of it
   — leagues are already perfect clusters. `[inference]`
8. **Statistical significance at α=0.05.** At 40 clusters, insisting on 0.05 mostly guarantees learning
   nothing; α is a dial, not a law. `[verified-2°]`
9. **Isotonic regression, quantile calibration, and most calibration machinery.** Below ~1,000 samples
   the sophisticated options are strictly worse. `[verified]`
10. **Whether the simulator's agents are LLMs.** The validation ladder decides trustworthiness, not the
    agent implementation. A calibrated logistic accept rule with shrinkage beats an uncalibrated LLM
    persona. `[inference]`

---

## 5. Transfer notes for FTF

### (a) Candidate feature list for the acceptance model, ranked by expected signal

Target: `P(counterparty accepts | suggestion rendered and sent)`. Model: L2-penalized logistic
regression (or Firth+FLAC if separation appears), Platt-calibrated, with league/manager hierarchical
shrinkage. Tier 1 alone is a shippable v1.

**Tier 1 — build first (highest expected signal, computable today)**

| # | Feature | Rationale / precedent |
|---|---|---|
| 1 | Counterparty's historical accept rate, shrunk to league then global prior | Airbnb's core construction; Airbnb blended with regional median for the ~26% of hosts with no data |
| 2 | Counterparty's accept rate **for this trade archetype** (2-for-1 consolidation, pick-for-player, WR-for-RB, buy-low-on-injury) | Airbnb's per-characteristic decomposition — independent signals, not a joint model |
| 3 | **Pair** history: prior trades and prior offers between these two managers, and their outcomes | The kidney model's biggest behavioral feature was the **OPO–hospital pair** acceptance pattern |
| 4 | **Counterparty's outside option**: rank of this offer among all feasible trades available to them in-league, and the gap to their best alternative | Freight's spot-market mechanism; FTF can compute this *exactly*, which is a genuine moat |
| 5 | Counterparty's perceived gain on *their own* board (not consensus values) | Round-2's per-user boards; this is the reciprocal-scoring output |
| 6 | Counterparty responsiveness/latency: median time-to-respond, days since last app open, trades initiated this season | Freight's carrier-availability features; Upwork models acceptance explicitly as an *availability* proxy |
| 7 | Season phase + days to trade deadline; bye/injury week | Freight lead-time and seasonality; round-2's season-phase regimes |
| 8 | Counterparty's competitive posture (contender vs. rebuilder) × direction of the offer (win-now vs. youth) | The core dynasty archetype split; IBM/ESPN's cosine-dissimilarity pairing is a crude proxy for it |

**Tier 2 — add once Tier 1 is calibrated**

| # | Feature | Rationale |
|---|---|---|
| 9 | **Offer "roundness"/legibility**: whole-number pick counts, clean 2-for-1 shapes, no odd filler | eBay round-number signaling: **3–5% more likely to sell** |
| 10 | Split-the-difference distance: how close the package sits to the midpoint of the two boards | The most robust eBay regularity that theory can't explain |
| 11 | Number of assets moving each way (complexity/friction of acting) | The kidney "operational features beat clinical ones" result; complexity is friction |
| 12 | Roster-slot friction: does accepting force the counterparty to cut someone? | Direct analogue of transport/logistics friction |
| 13 | Whether FTF suggested it vs. manager-composed; whether a reciprocal explanation was shown | Round-2/05's +17pp reciprocal-explanation finding — must be a feature, or it confounds everything |
| 14 | Counterparty's recent rejection streak (fatigue/annoyance) | Round-2/04's repeated-game dynamics; also the notification-fatigue literature |
| 15 | League-level norms: league's historical trade volume and acceptance base rate | Hierarchical level-2 covariate; also the CUPED covariate |

**Tier 3 — speculative, worth logging but not modeling yet**

16. Social relationship (real-life friends vs. strangers) — round-2/04 says friends negotiate *worse*.
17. Manager's stated preferences from onboarding (elicited want/accept lists).
18. Time-of-day / day-of-week of send.
19. Message text sentiment, if free-text is ever attached.

**Explicitly do not include:** consensus trade-value fairness as the dominant term. It belongs in the
gate, not the acceptance model — otherwise FTF ships Dynasty Dealmaker's antipattern with better prose.

**Label design.** Start with the *sparse-but-clean* label `accepted within 7 days`. If positives are too
few for stable fitting (§1.3's arithmetic implies you want ≥ ~10–15 events per predictor even under
Riley's more permissive framing, i.e. **~100+ accepts for an 8-feature Tier-1 model**), fall back to the
kidney reframe: **`any trade executed between these two managers within 14 days of the suggestion`** —
looser, denser, and still decision-relevant.

### (b) League-simulator design sketch

**Build order matters more than the design.** Phase 0 is not optional.

**Phase 0 — trace replay harness (weeks, not months).** Copy Thumbtack: record every rendered suggestion
request/response, replay historical requests against a candidate engine build, diff with three
comparators — full response, ranked list order, and candidate set ignoring order. This catches ranking
regressions and costs nothing in modeling assumptions. It is also the substrate Phase 1 plugs into.

**Phase 1 — the 12-agent behavioral simulator.**

*State (per agent):* roster; private valuation vector over assets; positional needs; contender/rebuilder
posture with a transition rule; responsiveness parameter; accept threshold; fatigue counter.

*Heterogeneous valuations:* draw each manager's private value for asset *j* as consensus value × a
manager-specific multiplicative noise term, with the noise's **dispersion itself a per-manager
parameter** fit from their observed ranking-matchup behavior. Archetype (contender/rebuilder) shifts the
age/win-now weighting rather than being a separate valuation model.

*Choice model (the part that must not be hand-waved):*
```
P(accept) = σ( β0_m + β1·(perceived_gain_m) + β2·(gap_to_best_alternative_m)
               + β3·(friction_m) + β4·(responsiveness_m) + β5·(fatigue_m) )
```
where `β0_m` is a **per-manager random intercept shrunk to a league prior** (§1.5), and
`gap_to_best_alternative_m` is computed by enumerating the counterparty's feasible in-league trades.
**Fit these coefficients on real accept/reject logs — do not assert them.** The moment you hard-code
"accept if gain ≥ ε" you have built the tautology in antipattern 10.

*Transition model:* executed trades mutate both rosters and therefore every other agent's feasible set —
this is the whole point, and it is what makes the simulator worth building rather than a spreadsheet.

*Arrival/initiation process:* calibrate suggestion cadence, manager-initiated offers, and seasonal
intensity from real league traces (trace-driven), with a generator for synthetic leagues as a stress test.

**Policies to replay:** suggestion cadence; 2-way vs. 3-way mix; how many suggestions surfaced at once;
cooldowns after rejection; fairness-gate ε; reciprocal-explanation on/off; ranking by P(accept) vs. by
mutual gain.

**Scoring:** completed trades per league-season; time-to-first-trade; rejection rate (burnout proxy);
**Gini of trade participation** (does the policy always feed the same two active managers?); asset
churn; and — critically — **the counterfactual cannibalization measure**: trades that would have
happened absent the suggestion.

**Validation gate before any simulator output informs a decision** (§1.11): reproduce the trades-per-
league-season distribution, the zero-trade-league share, the deadline spike, and the heavy tail of
manager participation **without having been fit to them**; then hold out leagues *k+1..n* and check
calibration of predicted vs. actual accepts; then sweep every parameter ±20% and report which
conclusions survive. **State explicitly which dimensions passed** — the simulator is admissible only
on those.

### (c) Experimentation decision tree for FTF's current scale (~tens of leagues)

```
START: what kind of question is it?

├─ Q1. Is it a pure ranking/ordering comparison?
│      (engine A's suggestion list vs. engine B's, same UI, same everything else)
│   └─ YES → INTERLEAVING. Verified at Thumbtack: ~400 samples to 90% agreement vs.
│            ~40,000 for the equivalent A/B — a ~100× sensitivity gain. Works at FTF's
│            scale TODAY. Limits: preference signal only, no marketplace-level or KPI
│            effects, cannot see cannibalization. Use it to pick a ranker, never to
│            size a business impact.
│
├─ Q2. Is it a bug/regression question — "did this change break ordering"?
│   └─ YES → TRACE REPLAY (Phase 0 simulator). No statistics required.
│
├─ Q3. Is it "does this hurt?" rather than "how much does this help?"
│   └─ YES → NON-INFERIORITY TEST at the league level, with a pre-declared margin,
│            α relaxed (0.10–0.15), matched-pair assignment + CUPED, analyzed by
│            within-pair permutation. This is answerable at 20–50 leagues. Most
│            roadmap questions belong here and are misfiled as superiority tests.
│
├─ Q4. Is it "does the suggestion feature create incremental trades at all?"
│      (the one big, first-order question)
│   └─ YES → RUN THE META-EXPERIMENT ONCE. Concurrent Bernoulli-randomized and
│            league-randomized arms; difference the TATE estimates.
│            ├─ Estimates agree → interference is not binding; you are licensed to
│            │  run cheap user-level tests for the foreseeable future. Record as a
│            │  decision (D-###), not a result.
│            └─ Estimates differ → league-level (or budget-split) assignment is
│               mandatory for any trade-volume metric from here on.
│            Alongside it, keep the round-2 GHOST-SUGGESTION HOLDOUT running
│            permanently — it answers incrementality by accumulation rather than power.
│
├─ Q5. Is the expected effect ≥ ~0.5σ of the league-level metric?
│   ├─ YES → CLUSTER-RANDOMIZE at the league level, but only with the full stack:
│   │        matched-pair assignment on pre-period trade volume → CUPED on pre-period
│   │        outcomes → within-pair permutation test (or wild cluster bootstrap-t;
│   │        FTF's equal cluster sizes satisfy MacKinnon–Webb's precondition).
│   │        Never plain cluster-robust t-stats. Pick EITHER the main effect OR the
│   │        spillover — Baird et al. prove you cannot power both.
│   │        Consider randomizing on the ASSET side rather than the manager side
│   │        (Johari et al.: an asset-constrained market makes listing-side
│   │        randomization the less-biased choice), and do not default to 50/50.
│   │
│   └─ NO (the common case) → DO NOT RUN AN A/B TEST. Escalate offline:
│            ├─ Need more units first? → BUDGET-SPLIT on the roster asset pool
│            │  (highest-payoff untested idea; keeps all 12 managers in both arms)
│            │  or DYAD-level randomization (66 dyads/league → 2,640 units at 40
│            │  leagues) — after checking whether local interference survives.
│            ├─ Switchback? → only after simulating power on historical logs.
│            │  Autocorrelation in weekly fantasy cycles may erase the benefit.
│            ├─ Rolling out to a handful of leagues? → SYNTHETIC CONTROL with
│            │  placebo-in-space/time inference. 20–50 leagues is an unusually good
│            │  donor pool by SCM standards.
│            └─ Otherwise → SIMULATOR + OPE. Keep the logging policy stochastic and
│               CLOSE to the evaluation policy (divergence degrades OPE ~100× vs.
│               ~10× for horizon). Prefer direct methods (FQE) over IPS/DR hybrids
│               in the low-data regime. Use OPE to REJECT bad policies, not to crown
│               close winners. Validate OPE retrospectively on a past policy change
│               before trusting it prospectively (the Open Bandit Pipeline protocol).
│
└─ ALWAYS, regardless of branch:
   • Randomization inference for p-values; asymptotics are not valid at N=40.
   • Check the one leakage channel: managers who belong to multiple FTF leagues.
   • Report the estimand you actually targeted (TATE, not individual ATE).
   • Log propensities, exposure, candidate set and policy version on every render.
   • Treat league COUNT as the measurement growth metric: 40→80 halves your MDE.
```

---

## 6. Not researched / follow-up topics

**Owed from the Part-2 sweep that did not return** (highest priority):
- Primary-source verification of the recommender-simulator canon cited here from knowledge: RecSim
  (arXiv 1909.04847), RecSim NG (2103.08057), RecoGym (1808.00720), Virtual-Taobao (1805.10000),
  Krauth et al. (2011.07931), Agent4Rec (2310.10108). **Identifiers should be checked before external citation.**
- The ABM validation-methodology canon: Windrum/Fagiolo/Moneta on empirical validation of ABMs,
  Grimm et al. on pattern-oriented modelling, and ABC / simulated-method-of-moments calibration for
  agent-based models — cited structurally in §1.11 but not sourced this session.
- SRTR's Kidney-Pancreas Simulated Allocation Model (KPSAM) and the UNOS simulation practice: how
  regulators actually parameterize center-level acceptance behavior. Round-2/01 covered the matching
  side; the *acceptance-behavior calibration* side is still open.
- The sim-to-real gap literature specifically (how the field handles "simulators reward what you coded
  into them") beyond the single canonical citation.

**Genuinely unresolved elsewhere:**
- **eBay Best Offer exact statistics.** Every PDF route (NBER, Berkeley, eScholarship, SSRN) returned
  binary/403. The "~1/3 immediate agreement" figure is corroborated across several independent
  secondary summaries but was **not read in the primary text**; the offer-ratio → acceptance-probability
  mapping was not obtained at all. Worth one manual read — it is the closest thing to a base-rate
  reference for bilateral offer acceptance.
- **Bojinov et al.'s closed-form optimal switchback block length under carryover order *m*** — could not
  be extracted; do not cite a specific interval rule from that paper.
- **Holtz et al.'s cluster counts and the variance cost of cluster randomization** at Airbnb — the
  19.76% figure is solid, the surrounding design detail is not extracted.
- **Upwork's acceptance model details** — the engineering blog 403s; only search-snippet level.
- **Whether the budget-split → roster-asset-pool analogy actually holds.** This memo's most promising
  design idea is my inference, not any author's claim. It needs a formal check that splitting a roster's
  tradeable pool preserves the unbiasedness argument, and a simulator run before it touches production.
- **Whether dyad-level "local interference" survives FTF's closed market.** Assets are consumed
  league-wide, not dyad-wide, which may violate the MRD assumption outright.
- **Cross-league contamination** from managers in multiple FTF leagues — empirically checkable from the
  current database; not checked here.
- **Base rate for fantasy trade-offer acceptance.** No published figure found anywhere. FTF's own logs
  will be the first credible number; Dynasty Daddy's ">1M trades from 200k leagues" corpus is the only
  visible dataset at scale.
- **Multi-objective calibration** (execute-probability × roster-improvement × fairness gate) — carried
  over unresolved from round-2/03 §7.
- **DoorDash's switchback posts** — all four URLs 403'd; directionally reported, numbers unverified.

---

## 7. Sources

### Part 1 — Acceptance-probability modeling

Fantasy-domain precedent:
1. Trenkwalder-Baumgartner et al. / IBM — *Large Scale Diverse Combinatorial Optimization: ESPN Fantasy Football Player Trades* — https://arxiv.org/abs/2111.02859
2. Parshall, Ali & Zimmerman — *A Genetic Algorithm for Optimizing Fantasy Football Trades with Playoff Biasing* — https://arxiv.org/abs/2511.17535
3. IBM — *IBM Brings watsonx to ESPN Fantasy Football with New Waiver Grades and Trade Grades* — https://newsroom.ibm.com/2023-09-13-IBM-Brings-watsonx-to-ESPN-Fantasy-Football-with-New-Waiver-Grades-and-Trade-Grades
4. Dynasty Dealmaker — https://www.dynastydealmaker.com/
5. Dynasty Daddy — https://dynasty-daddy.com/trade-calculator

Marketplace acceptance models:
6. Airbnb Engineering — *How Airbnb Uses Machine Learning to Detect Host Preferences* — https://medium.com/airbnb-engineering/how-airbnb-uses-machine-learning-to-detect-host-preferences-18ce07150fa3
7. Upwork Engineering — *Data, Machine Learning, and Marketplace Optimization at Upwork (Part 1)* — https://www.upwork.com/careers/engineering-blog/data-machine-learning-and-marketplace-optimization-at-upwork-part-1-user-level-growth
8. Thumbtack Engineering — *Our Transition to Machine Learning in Search Ranking* — https://medium.com/thumbtack-engineering/our-transition-to-machine-learning-in-search-ranking-to-match-customers-and-professionals-68fb29e39899
9. Thumbtack Engineering — *Evolution of Search Ranking at Thumbtack* — https://medium.com/thumbtack-engineering/evolution-of-search-ranking-at-thumbtack-f7a69fd0da13

Organ-offer acceptance (the closest published acceptance-prediction literature):
10. *Predictive Models for Kidney Offer Acceptance: Challenges and Strategies* — https://pmc.ncbi.nlm.nih.gov/articles/PMC12784377/
11. *Enhancing Expedited Kidney Allocation Through Machine Learning* — https://www.amjtransplant.org/article/S1600-6135(25)03249-6/fulltext
12. *Comparative Evaluation of Machine Learning Models for Predicting Donor Kidney Discard* — https://arxiv.org/html/2602.21876

Bargaining / offer design:
13. Backus, Blake, Larsen & Tadelis — *Sequential Bargaining in the Field: Evidence from Millions of Online Bargaining Interactions*, QJE 135(3):1319 — https://www.nber.org/papers/w24306 · https://academic.oup.com/qje/article-abstract/135/3/1319/5721265 · data: https://www.nber.org/research/data/best-offer-sequential-bargaining
14. Backus, Blake & Tadelis — *On the Empirical Content of Cheap-Talk Signaling: An Application to Bargaining*, JPE 127(4) — https://www.journals.uchicago.edu/doi/abs/10.1086/701699 · WP: https://www.nber.org/system/files/working_papers/w21285/w21285.pdf · digest: https://www.nber.org/digest/sep15/cheap-talk-round-numbers-and-signaling-behavior
15. *Buyer behavior under the Best Offer mechanism* (eBay Motors) — https://www.sciencedirect.com/science/article/abs/pii/S0167268113001698

Automated negotiation / opponent modeling:
16. Baarslag, Hendrikx, Hindriks & Jonker — *Learning about the opponent in automated bilateral negotiation: a comprehensive survey of opponent modeling techniques*, AAMAS 30(5) — https://dl.acm.org/doi/10.1007/s10458-015-9309-1 · PDF: https://homepages.cwi.nl/~baarslag/pub/A_survey_of_opponent_modeling_techniques_in_automated_negotiation.pdf
17. Baarslag — *What to Bid and When to Stop* (thesis) — https://homepages.cwi.nl/~baarslag/pub/What_to_Bid_and_When_to_Stop.pdf

Freight tender acceptance:
18. C.H. Robinson — *Distance, Volatility, and Rejection Rates* — https://www.chrobinson.com/en-us/resources/blog/distance-volatility-and-rejection-rates/
19. SONAR — *How To Interpret Tender Rejection Rates* — https://gosonar.com/freight-market-blog/how-to-interpret-tender-rejection-rates
20. FreightWaves — *Why tracking tender rejections is important* — https://www.freightwaves.com/news/why-tracking-tender-rejections-is-important
21. Fleetworks — *Tender Response Automation in Freight* — https://www.fleetworks.ai/resources/tender-response-automation
22. *Latency-Aware Bid Acceptance under Operational Feasibility* (FreightBidBench) — https://arxiv.org/abs/2607.07343
23. *Reinforcement Learning for Dynamic Bidding in Truckload Markets* — https://arxiv.org/pdf/1802.08976

Job-offer acceptance / B2B quote win:
24. Greenhouse — *Offer forecast overview* — https://support.greenhouse.io/hc/en-us/articles/115005312666-Offer-forecast-overview
25. Metaview — *Offer acceptance is decided in the interview, not at offer* — https://www.metaview.ai/resources/blog/offer-acceptance-rate
26. Oracle — *Deal Win Probability Using Machine Learning* — https://docs.oracle.com/en/industries/financial-services/revenue-management-billing/81000/ormb-online-help/Topics/C1_Deal_Win_Probability_Using_Machine_Learning_ML.html
27. Wapice — *How does AI help CPQ systems learn from won and lost deals?* — https://wapice.com/insights/how-does-ai-help-cpq-systems-learn-from-won-and-lost-deals/

Small-N modeling and calibration:
28. Christodoulou et al. — *A systematic review shows no performance benefit of machine learning over logistic regression for clinical prediction models*, J Clin Epi 110:12–22 — https://pubmed.ncbi.nlm.nih.gov/30763612/ · https://research.birmingham.ac.uk/en/publications/a-systematic-review-shows-no-performance-benefit-of-machine-learn/
29. Riley et al. — *Minimum sample size for developing a multivariable prediction model: Part II* , Stat Med — https://onlinelibrary.wiley.com/doi/full/10.1002/sim.7992
30. *Statistical primer: sample size considerations for developing and validating clinical prediction models*, EJCTS — https://academic.oup.com/ejcts/article/67/5/ezaf142/8120086
31. van Smeden et al. — *Sample size for binary logistic prediction models: Beyond events per variable criteria* — https://journals.sagepub.com/doi/10.1177/0962280218784726
32. van der Ploeg et al. — *Modern modelling techniques are data hungry* — https://bmcmedresmethodol.biomedcentral.com/articles/10.1186/1471-2288-14-137
33. Puhr et al. — *Firth's logistic regression with rare events: accurate effect estimates AND predictions?* — https://arxiv.org/abs/2101.07620 · https://onlinelibrary.wiley.com/doi/10.1002/sim.7273
34. scikit-learn — *Probability calibration* — https://scikit-learn.org/stable/modules/calibration.html
35. Niculescu-Mizil & Caruana — *Predicting Good Probabilities With Supervised Learning*, ICML 2005 — https://www.cs.cornell.edu/~alexn/papers/calibration.icml05.crc.rev3.pdf
36. *Calibration Meets Reality: Making Machine Learning Predictions Trustworthy* — https://arxiv.org/pdf/2509.23665

Reciprocal recommendation (acceptance on both sides):
37. Pizzato et al. — *RECON: A Reciprocal Recommender for Online Dating* — https://www.researchgate.net/publication/221140972_RECON_A_reciprocal_recommender_for_online_dating
38. *Reciprocal Recommendation System for Online Dating* — https://arxiv.org/pdf/1501.06247

### Part 2 — Simulation

39. Thumbtack Engineering — *Validating Search Ranking with the Simulator* — https://medium.com/thumbtack-engineering/validating-search-ranking-with-the-simulator-fba377dd27c4  `[verified]`
40. Ie et al. — *RecSim: A Configurable Simulation Platform for Recommender Systems* — https://arxiv.org/abs/1909.04847  `[known-unverified]`
41. Mladenov et al. — *RecSim NG: Toward Principled Uncertainty Modeling for Recommender Ecosystems* — https://arxiv.org/abs/2103.08057  `[known-unverified]`
42. Rohde et al. — *RecoGym: A Reinforcement Learning Environment for the problem of Product Recommendation in Online Advertising* — https://arxiv.org/abs/1808.00720  `[known-unverified]`
43. Shi et al. — *Virtual-Taobao: Virtualizing Real-world Online Retail Environment for Reinforcement Learning* — https://arxiv.org/abs/1805.10000  `[known-unverified]`
44. Krauth et al. — *Do Offline Metrics Predict Online Performance in Recommender Systems?* — https://arxiv.org/abs/2011.07931  `[known-unverified]`
45. Zhang et al. — *On Generative Agents in Recommendation (Agent4Rec)* — https://arxiv.org/abs/2310.10108  `[known-unverified]`
46. *SimGym* — https://arxiv.org/html/2605.19219  `[verified-2°, flagged]`
47. *Agent A/B* — https://arxiv.org/html/2504.09723  `[verified-2°, flagged]`
48. FTF round-2 memo — kidney-exchange simulation practice, trace-driven replay vs. Saidman generator, center selectivity — [round-2/01 §Simulating small matching markets](../round-2/01-thin-markets-and-multiparty-matching.md)

### Part 3 — Experimentation under interference

Designs:
49. Ugander, Karrer, Backstrom & Kleinberg — *Graph Cluster Randomization: Network Exposure to Multiple Universes*, KDD 2013 — https://arxiv.org/abs/1305.6979
50. Eckles, Karrer & Ugander — *Design and Analysis of Experiments in Networks: Reducing Bias from Interference* — https://arxiv.org/abs/1404.7530
51. Karrer et al. (Meta) — *Network Experimentation at Scale*, KDD 2021 — https://arxiv.org/abs/2012.08591
52. Saveski et al. — *Detecting Network Effects: Randomizing Over Randomized Experiments*, KDD 2017 — https://dl.acm.org/doi/10.1145/3097983.3098192 · Biometrika follow-up: https://faculty.washington.edu/msaveski/assets/publications/2019_biometrika/paper.pdf
53. Holtz, Lobel, Lobel, Liskovich & Aral — *Reducing Interference Bias in Online Marketplace Experiments Using Cluster Randomization: Evidence from a Pricing Meta-Experiment on Airbnb*, Mgmt Sci 2025 — https://pubsonline.informs.org/doi/10.1287/mnsc.2020.01157 · https://ide.mit.edu/wp-content/uploads/2020/05/SSRN-id3583836.pdf
54. Bojinov, Simchi-Levi & Zhao — *Design and Analysis of Switchback Experiments* — https://arxiv.org/abs/2009.00148
55. Pankratev — *Powerful Switchback Experiments — Or Not?* — https://arxiv.org/pdf/2606.03012
56. Chamandy (Lyft) — *Experimentation in a Ridesharing Marketplace* — https://eng.lyft.com/experimentation-in-a-ridesharing-marketplace-b39db027a66e · https://eng.lyft.com/experimentation-in-a-ridesharing-marketplace-36007a8a31f2 · https://eng.lyft.com/using-marketplace-marginal-values-to-address-interference-bias-a11aff6e670f
57. DoorDash — *Switchback Tests and Randomized Experimentation Under Network Effects* — https://careersatdoordash.com/blog/switchback-tests-and-randomized-experimentation-under-network-effects-at-doordash/ · *Cluster Robust Standard Error in Switchback Experiments* — https://careersatdoordash.com/blog/cluster-robust-standard-error-in-switchback-experiments/ · *Balancing Network Effects, Learning Effects, and Power* — https://careersatdoordash.com/blog/balancing-network-effects-learning-effects-and-power-in-experiments/  `[403 — search-derived]`
58. Uber — *Under the Hood of Uber's Experimentation Platform* — https://www.uber.com/us/en/blog/xp/
59. Statsig — *Switchback experiments: overview and considerations* — https://www.statsig.com/blog/switchback-experiments
60. Saint-Jacques, Varshney, Simpson & Xu — *Using Ego-Clusters to Measure Network Effects at LinkedIn* — https://arxiv.org/abs/1903.08755
61. Su & Duan — *Improving Ego-Cluster for Network Effect Measurement*, KDD '24 — https://dl.acm.org/doi/10.1145/3637528.3671557 · https://arxiv.org/html/2308.05945v3
62. Liu, Hu & Zhang — *Estimating Treatment and Spillover Effects with the Ego-Cluster Experimental Design* — https://arxiv.org/html/2605.00534
63. Johari, Li, Liskovich & Weintraub — *Experimental Design in Two-Sided Platforms: An Analysis of Bias*, Mgmt Sci 68(10) — https://arxiv.org/abs/2002.05670
64. Li, Zhao, Johari & Weintraub — *Interference, Bias, and Variance in Two-Sided Marketplace Experimentation*, WWW '22 — https://arxiv.org/abs/2104.12222
65. Liu, Mao & Kang — *Trustworthy Online Marketplace Experimentation with Budget-Split Design* — https://arxiv.org/abs/2012.08724
66. Bajari et al. — *Multiple Randomization Designs: Estimation and Inference with Interference* — https://arxiv.org/abs/2112.13495
67. Shekhar & Howard — *Choosing Online Experiment Designs under Interference* — https://arxiv.org/html/2605.25290v1

Estimation and inference:
68. Hudgens & Halloran — *Toward Causal Inference with Interference*, JASA 103(482) — https://ideas.repec.org/a/bes/jnlasa/v103y2008mjunep832-842.html
69. Aronow & Samii — *Estimating Average Causal Effects Under General Interference*, AOAS 11(4) — https://arxiv.org/pdf/1305.6156
70. Sävje, Aronow & Hudgens — *Causal Inference with Misspecified Exposure Mappings* — https://arxiv.org/pdf/2103.06471
71. Leung — *Causal Inference Under Approximate Neighborhood Interference*, Econometrica 90(1) — https://onlinelibrary.wiley.com/doi/abs/10.3982/ECTA17841 · *Treatment and Spillover Effects Under Network Interference*, REStat 102(2) — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2757313
72. Athey, Eckles & Imbens — *Exact p-Values for Network Interference*, JASA 113(521) — https://arxiv.org/abs/1506.02084
73. MacKinnon & Webb — *The Wild Bootstrap for Few (Treated) Clusters*, Econometrics J. 21(2) — https://onlinelibrary.wiley.com/doi/abs/10.1111/ectj.12107 · WP: http://qed.econ.queensu.ca/pub/faculty/mackinnon/working-papers/qed_wp_1364.pdf
74. MacKinnon & Webb — *Randomization Inference for Difference-in-Differences with Few Treated Clusters*, J. Econometrics 218(2) — https://www.sciencedirect.com/science/article/abs/pii/S0304407620301445
75. Baird, Bohren, McIntosh & Özler — *Optimal Design of Experiments in the Presence of Interference*, REStat 100(5) — https://direct.mit.edu/rest/article/100/5/844/58481/Optimal-Design-of-Experiments-in-the-Presence-of · power software: https://blogs.worldbank.org/en/impactevaluations/power-calculation-software-randomized-saturation-experiments
76. Firpo & Possebom — *Synthetic Control Method: Inference, Sensitivity Analysis and Confidence Sets* — https://economics.yale.edu/sites/default/files/firpo_possebom_2017_synthetic-control-method-inference-sensitivity-analysis-and-confidence-sets.pdf · *Inference for Synthetic Controls via Refined Placebo Tests* — https://arxiv.org/abs/2401.07152

Power, variance reduction, and small-N practice:
77. Deng, Xu, Kohavi & Walker — *Improving the Sensitivity of Online Controlled Experiments by Utilizing Pre-Experiment Data* (CUPED), WSDM 2013 — https://dl.acm.org/doi/10.1145/2433396.2433413 · Netflix: https://kdd.org/kdd2016/papers/files/adp0945-xieA.pdf
78. *Inference in cluster randomized trials with matched pairs*, J. Econometrics 2024 — https://www.sciencedirect.com/science/article/abs/pii/S0304407624002185 · *A General Framework for Design-Based Treatment Effect Estimation in Paired Cluster-Randomized Experiments* — https://arxiv.org/pdf/2407.01765
79. *Sample size calculations for cluster randomised trials with a fixed number of clusters*, BMC Med Res Methodol 11:102 — https://bmcmedresmethodol.biomedcentral.com/articles/10.1186/1471-2288-11-102
80. Rutterford, Copas & Eldridge — *Methods for sample size determination in cluster randomized trials*, IJE — https://pmc.ncbi.nlm.nih.gov/articles/PMC4521133/
81. Hedberg — *How Many Cases per Cluster?*, Am. J. Evaluation 2023 — https://journals.sagepub.com/doi/10.1177/10982140221134618
82. Georgiev — *A/B Testing with a Small Sample Size* — https://blog.analytics-toolkit.com/2019/a-b-testing-with-a-small-sample-size/
83. Thumbtack Engineering — *Accelerating Ranking Experimentation at Thumbtack with Interleaving* — https://medium.com/thumbtack-engineering/accelerating-ranking-experimentation-at-thumbtack-with-interleaving-20cbe7837edf

Off-policy evaluation:
84. Voloshin, Le, Jiang & Yue — *Empirical Study of Off-Policy Policy Evaluation for Reinforcement Learning* — https://arxiv.org/abs/1911.06854
85. Saito, Aihara, Matsutani & Narita — *Open Bandit Dataset and Pipeline* — https://arxiv.org/abs/2008.07146 · https://github.com/st-tech/zr-obp
86. Saito et al. — *Evaluating the Robustness of Off-Policy Evaluation*, RecSys 2021 — https://dl.acm.org/doi/10.1145/3460231.3474245
87. *Off-Policy Evaluation of Ranking Policies under Diverse User Behavior* — https://arxiv.org/pdf/2306.15098

### Internal cross-references

- [round-2/01 — Thin markets and multiparty matching](../round-2/01-thin-markets-and-multiparty-matching.md) (§Simulating small matching markets is this memo's Part-2 starting point)
- [round-2/03 — Sparse-data learning and evaluation](../round-2/03-sparse-data-learning-and-evaluation.md) (§7 flagged the three gaps this memo closes; its logging contract is the prerequisite for everything here)
- [round-2/04 — Closed communities and fantasy analogs](../round-2/04-closed-communities-and-fantasy-analogs.md) (repeated-game dynamics behind features 14 and 16)
- [round-2/05 — Presentation and conversion engineering](../round-2/05-presentation-and-conversion-engineering.md) (reciprocal explanations; must be a feature in the acceptance model, not a confound)
- [round-3/01 — Counteroffer and negotiation loop](01-counteroffer-and-negotiation-loop.md)
