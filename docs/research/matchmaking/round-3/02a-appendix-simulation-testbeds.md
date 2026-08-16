# Appendix to Round-3 Topic 02 — Simulation testbeds (late-arriving research thread)

> This is the full report of the simulation-testbeds research thread that had not yet returned
> when the main memo (02-acceptance-modeling-simulation-experimentation.md) was compiled; the
> main memo's §Part 2 gaps are covered here. Same confidence-flag discipline as the main memo.
> Recorded 2026-08-16.

**Framing for the dynasty-league use case.** The literature converges on one uncomfortable point: a simulator is a *hypothesis generator and a falsifier*, not a measurement device. The single most quotable finding for this project is Krauth et al.'s asymmetry — good simulator performance is not evidence a policy works, but bad simulator performance *is* strong evidence it fails. Design the 12-team league sim as a **falsification harness**, not a scoreboard.

---

## A. Recommender-system simulators

### A1. The Google lineage — RecSim / RecSim NG

**RecSim** (Ie, Hsu, Mladenov, Jain, Narvekar, Wang, Wu, Boutilier; arXiv:1909.04847) — https://arxiv.org/abs/1909.04847 · full text https://ar5iv.labs.arxiv.org/html/1909.04847

The architecture is the cleanest transferable template. Four separable pieces:
- **Document/item model** — items sampled from a prior over latent (quality) + observable (topic, length, popularity) features.
- **User model** — users sampled from a prior over latent (satisfaction, interests), observable (demographics), and budget features (session length, time budget).
- **User choice model** — maps *(full user state incl. latent, slate)* → stochastic response. Named instantiations: **multinomial logit** and **exponentiated cascade**.
- **Transition model** — updates latent user state after consumption (interest drift, budget decay, satisfaction).

The simulator loop deliberately splits what the *agent* sees (observable state only) from what the *choice model* sees (observable + latent). **Transfer:** for the league sim, a manager's "latent state" is roster need / contention window / risk appetite; the trade-recommender must only see what the app can actually observe.

On fidelity the authors are explicit: *"Our goal is not to create a 'perfect' simulator; we do not expect policies learned in simulation to be deployed in live systems."* They advocate **"stylized user models"** that reflect specific aspects of behavior, and say RecSim environments *"will not reflect the full extent of user behavior in most practical recommender settings,"* explicitly disclaiming benchmark status. Confidence: **high** (verified against full text).

**RecSim NG** (Mladenov et al.; arXiv:2103.08057) — https://arxiv.org/abs/2103.08057 · full text https://ar5iv.labs.arxiv.org/html/2103.08057 · Google blog https://research.google/blog/flexible-scalable-differentiable-simulation-of-recommender-systems-with-recsim-ng/

The one that actually tells you **how to calibrate a simulator** — the most directly reusable methodology in thread A:
- Design pattern is **Variables / Entities / Stories** over a Dynamic Bayesian Network — entities batch a whole *population* of agents (12 managers), variables carry initial distribution + transition kernel, stories wire them together.
- A `log_probability` API scores real logged trajectories under the simulator's own generative model. Combined with autodiff, this gives **maximum-likelihood fitting of simulator parameters to logged data** — you can literally fit accept/reject parameters by gradient descent on observed trade history.
- For latent state you can't observe (manager's true contention intent): **Hamiltonian Monte Carlo inside a Monte-Carlo EM loop**, maximizing an ELBO. This is the answer to "how do I fit agent thresholds when I only see accept/reject, not the reasoning."

Caveat, verbatim: *"While the so-called 'sim2real' perspective is valuable, we focus on simulations that reflect particular phenomena of interest… to allow the controlled evaluation of recommender methods at suitable levels of abstraction."* No validation methodology against production logs is provided — sim-to-real transfer is named as future work only. Confidence: **high**.

### A2. Data-grounded simulators (the ones that actually fit real data)

**RecoGym** (Rohde, Bonner, Dunlop, Vasile, Karatzoglou; arXiv:1808.00720; REVEAL @ RecSys'18) — https://arxiv.org/abs/1808.00720 · https://ar5iv.labs.arxiv.org/html/1808.00720
Markov chain alternating **organic** (browsing, reveals preferences) / **bandit** (recommendation shown, click or not) / **stop** states. Latent utility Λ_{u,p,t} drives organic views via Bernoulli(σ(Λ)); CTR is a noisy function of the same Λ, with σ_Φ tuning the **correlation between what a user browses and what they'll accept** — a knob with a direct analogue in the league sim (correlation between a manager's stated wants and their actual accepts). Ad-fatigue (repeat exposure decay) is a configurable effect — directly analogous to spamming a manager with trade offers. Confidence: **medium-high**.

**Virtual-Taobao** (Shi, Yu, Da, Chen, Zeng; AAAI 2019; arXiv:1805.10000) — https://arxiv.org/abs/1805.10000 · https://ar5iv.labs.arxiv.org/html/1805.10000
The best worked example of *learning a simulator from logs and then not letting the policy cheat it*:
- **GAN-SD** generates customers — plain GAN *"tend[s] to generate the most frequent occurring customers"*, so they add entropy-maximization and KL-divergence distribution constraints to preserve tail diversity. **Directly relevant:** a naive generative model of "typical dynasty manager" will collapse onto the median manager and erase the rebuilders and the hoarders, who are exactly the interesting cases.
- **MAIL** (multi-agent GAIL) learns customer *and* platform policy jointly, because behavior cloning breaks under covariate shift once the recommender policy changes.
- **Action Norm Constraint** penalizes actions far from historical norms: `r'(s,a) = r(s,a) / (1 + ρ·max{||a|| − μ, 0})`. Rationale, verbatim: *"A powerful RL algorithm… can easily train an agent to over-fit Virtual Taobao which means it can perform well in the virtual environment but poorly in the real."* The canonical statement of **simulator-policy co-adaptation**, and the cheapest known defense: constrain the policy to stay near the support of real data.
- Validation: compared simulated vs real distributions (customer proportions by query category / purchase power, Rate-of-Purchase-Page by feature, R2P across 12 daily time periods), then an **online A/B test** (R2P 0.101 for RL+VTaobao vs 0.096/0.098 supervised; >2% revenue). Confidence: **medium-high** (numbers via summarizer, not eyeballed).

**SOFA — "Keeping Dataset Biases out of the Simulation"** (Huang, Oosterhuis, de Rijke, van Hoof; RecSys 2020) — https://harrieo.github.io/publication/2020-recsys · https://irlab.science.uva.nl/wp-content/papercite-data/pdf/huang-2020-keeping.pdf · code https://github.com/BetsyHJ/SOFA
Logged data is MNAR (you only see interactions the old policy produced), so a simulator naively fit to logs **inherits the logging policy's bias and passes it into every policy you then train**. SOFA inserts an explicit debiasing step *before* simulator fitting, and proposes judging a simulator by *the performance of policies optimized inside it* rather than by its own predictive accuracy. **Directly relevant:** observed trade history only contains trades someone chose to *propose*; fitting accept-probability to that log without correction systematically overstates acceptance. ⚠️ Confidence: **medium** — mechanism description is abstract-level (PDF fetch unreliable).

**MARS-Gym** (Santana et al.; arXiv:2010.07035) — https://arxiv.org/abs/2010.07035 — marketplace RL rec framework; ingests interaction logs, trains with counterfactual losses, exposes a Gym env; evaluated on the Trivago dataset. Confidence: **medium** (abstract-level).

**RL4RS** (Wang et al.; SIGIR 2023; arXiv:2110.11073) — https://arxiv.org/abs/2110.11073 · https://ar5iv.labs.arxiv.org/html/2110.11073
The most useful *evaluation protocol* in the thread. Three parts: (1) evaluate the environment simulator itself, (2) counterfactual/off-policy evaluation (IS, SWIS, DR, sequential DR), (3) build a **second environment from a held-out test set** and evaluate there — explicitly *"prevents overfitting because the estimated reward of the test set will be affected by the train set through the shared environmental model."* Sharpest finding: standard classification metrics on the user model are **not** sufficient — *"prediction of user behavior seems to be accurate enough"* yet *"the estimated reward error is still not low."* **Transfer:** AUC on the accept-model is not evidence the sim gives correct policy rankings; measure **reward error**, not just classification error. Confidence: **high**.

**Accordion** (McInerney, Elahi, Basilico, Raimond, Jebara; RecSys '21; DOI 10.1145/3460231.3474259) — https://dl.acm.org/doi/10.1145/3460231.3474259 · code https://github.com/jamesmcinerney/accordion
A **trainable Poisson-process simulator** from Netflix modeling *visit* patterns over time — recommendation quality changes *engagement frequency*, not just per-offer acceptance, the piece the others miss that matters most for dynasty. ⚠️ Internals unverified (paywalled). Confidence: **low-medium on internals, high on existence/metadata**.

**Survey:** Stavinova et al., *Synthetic Data-Based Simulators for Recommender Systems: A Survey* (2022), arXiv:2206.11338 — https://arxiv.org/abs/2206.11338. Abstract-level only. Confidence: **low-medium**.

### A3. The critique literature — "simulators reward what you coded into them"

**Krauth, Dean, Zhao, Guo, Curmei, Recht, Jordan, *Do Offline Metrics Predict Online Performance in Recommender Systems?*** (arXiv:2011.07931) — https://arxiv.org/abs/2011.07931 · https://ar5iv.labs.arxiv.org/html/2011.07931 · RecLab framework
**The keystone source.** 11 recommenders × 6 simulated environments. Findings:
- Offline metrics (nDCG, RMSE) *are* correlated with online performance, **but "improvements in offline metrics lead to diminishing returns in online performance"** — past ~0.92 nDCG, further gains buy almost nothing.
- **The offline ranking of algorithms changes with the size of the initial dataset.** In low-data regimes rankings reversed outright.
- Feedback loops dominate: in topics-*dynamic*, TopPop improves markedly over time; in topics-*static* it performs on par with Random. Same algorithm, opposite verdict, purely from whether user preferences respond.
- The governance quote: *"A recommender system or metric performing well in simulation should not be interpreted as a carte blanche to claim such a system/metric would perform well in real-world settings"* — but poor simulation performance is *"strong negative evidence that such a system would fail."*
Confidence: **high**.

**Deffayet, Thonet, Renders, de Rijke, *Offline Evaluation for Reinforcement Learning-based Recommendation*** — SIGIR Forum 56(2), 2022 — https://dl.acm.org/doi/10.1145/3582900.3582905 · https://arxiv.org/abs/2301.00993 · https://ar5iv.labs.arxiv.org/html/2301.00993
Three shortcomings of next-item-prediction evaluation: **myopic**; **suboptimal target** (rewards imitating the logging policy); **risky deployment** (can't detect the optimizer's curse). On simulation: benefits are *"observ[ing] how recommenders react under a chosen set of assumptions on user behavior"* and access to *"otherwise unobservable metrics"*; the risk is *"their ecological validity may clearly be limited"* — so *"benchmark… against a wide range of simulated configurations."* Confidence: **high** (via ar5iv).

> ⚠️ **Integrity flag (carried from the research thread).** A first PDF fetch of this paper returned a fabricated "quote" that was actually the search phrasing echoed back. It was caught and re-verified via ar5iv; the quotes above are the real ones. Treat any single-source PDF-derived quote in this space with suspicion.

**Aouali et al., *Offline Evaluation of Reward-Optimizing Recommender Systems: The Case of Simulation*** (arXiv:2209.08642) — https://arxiv.org/abs/2209.08642. The *pro-simulation* counterweight: proxy offline metrics correlate poorly with online, counterfactual methods rest on unrealistic assumptions, therefore *"simulation-based comparisons provide ways forward beyond offline metrics."* Confidence: **medium** (abstract-level).

**Chaney, Stewart, Engelhardt** (RecSys 2018; arXiv:1710.11214) — https://arxiv.org/abs/1710.11214. A simulator is worth building *specifically* to expose feedback-loop pathologies: training on data from users already exposed to recommendations *"homogenizes user behavior without increasing utility."* **Transfer:** the league sim's highest-value output may be "does this policy collapse the league into everyone trading the same six players." Confidence: **medium**.

**Said, Pera, Ekstrand, *We're Still Doing It (All) Wrong*** (RecSys 2025 BEYOND; arXiv:2509.09414) — https://arxiv.org/html/2509.09414v1. Field-level critique; notably does **not** treat simulation as the fix — calls for targeted data collection and user studies. Confidence: **medium-high**.

**SimuRec workshop** (RecSys '21, DOI 10.1145/3460231.3470938) — https://dl.acm.org/doi/10.1145/3460231.3470938 — convened because *there are no clear best practices* for recsys simulation.

### A4. LLM agents as user simulators (2023–2026) — and why not to trust them on accept/reject

**Agent4Rec** (Zhang et al.; SIGIR 2024; arXiv:2310.10108) — https://arxiv.org/abs/2310.10108 · code https://github.com/LehengTHU/Agent4Rec. 1,000 LLM agents with profile/memory/action modules; reproduces filter-bubble effects; authors report *"both the alignment and deviation between agents and user-personalized preferences."* Confidence: **medium**.

**★ *Simulated Customers Never Walk Away*** (arXiv:2606.20708) — https://arxiv.org/abs/2606.20708
**The single most on-point paper for a trade accept/reject simulator.** Benchmarked against 2,790 production conversations with real purchase verification. Names the **"disengagement deficit"**: simulators halved expressed resistance among eventual non-buyers (25.1% → 13.5%) and nearly doubled deliberation (21.9% → 40.1%), d=0.38, p<0.001, replicated on a second model. *"Real non-buyers say 'not now' and stop; simulated non-buyers ask about price."* **Transfer:** an LLM-agent league-mate will negotiate politely and eventually accept. Real dynasty managers ghost you. Confidence: **medium-high** (abstract-level numbers).

**★ *Mind the Sim2Real Gap in User Simulation for Agentic Tasks*** (Zhou et al.; arXiv:2603.11245) — https://arxiv.org/html/2603.11245v1
Behavioral gap + evaluative gap taxonomy; **User-Sim Index** (USI). Best LLM simulator scores USI 76.0 vs human baseline 92.9; simulators create an **"easy mode"** — 77.8% agent success vs 63.6% with humans; **70.6% of reward=0 interactions were judged successful by humans**. Confidence: **high** (full HTML).

**★ *Lost in Simulation*** (Seshadri et al.; arXiv:2601.17087) — https://arxiv.org/html/2601.17087
Human study across demographics: swapping the *user* LLM alone moved agent success ~9pp; ECE 15.1 even for the best-matched group; simulated users asked questions 18.8% of turns vs 9.8% for humans. Recommendation: report robustness across **multiple** user-simulator models, validate against human data. Confidence: **high**.

***The Illusion of Intervention*** (Lin et al.; arXiv:2605.20767) — https://arxiv.org/abs/2605.20767. LLM-simulated experiments are observational studies: interventions silently shift latent user attributes ("user drift"), confounding arms. Remedies: **negative-control outcomes**, persona specification with targeted confounders. Confidence: **medium**.

Supporting: **RecUserSim** (arXiv:2507.22897) — persona sampling from dictionaries under priors, validated against 100 real conversations. **LLM-Powered User Simulator** (arXiv:2412.16984) — grounds LLM output in an explicit logical model + statistical ensemble. **LLM Social Simulations Are a Promising Research Method** (arXiv:2504.02234) — restrict to *"pilot and exploratory studies."* Confidence: **medium** each.

---

## B. Market-design / matching simulation practice

### ★ The best available template: the ELAS liver-allocation simulator

**de Ferrante et al., *A discrete event simulator for policy evaluation in liver allocation in Eurotransplant*** (arXiv:2410.10840) — https://arxiv.org/abs/2410.10840 · full text https://arxiv.org/html/2410.10840v2

**If you copy one design from this appendix, copy this one.** A matching simulator whose entire purpose is evaluating allocation *policies*, and whose central stochastic component is an **offer acceptance model** — structurally identical to FTF's problem.

- **Arrivals: trace-driven replay, with synthetic as an option.** For validation they replayed *all* real donors from 2016–2019. **Transfer:** replay the real league's actual roster states and real waiver/draft events; only synthesize what you must.
- **Offer acceptance: two-stage nested logistic regression with mixed effects.** Stage 1: center-level logistic model predicts from donor characteristics alone whether the center is willing to accept. Stage 2: given willingness, a patient-level logistic model predicts acceptance from patient × donor characteristics. Odds ratios estimated with *"mixed effect models with random effects for donor heterogeneity…, patient heterogeneity, and center heterogeneity."* **Transfer — the exact shape FTF's accept model should take:** stage 1 = "does this manager engage with a trade of this shape at all" (offer-level features); stage 2 = "given engagement, does this package clear their bar" (package × roster features). **Random effects are how you get heterogeneous agents with limited data** — per-manager random intercepts partially pooled toward the league mean, not 12 independently-fit models.
- **Validation: 200 replications; "well-calibrated" = real statistic falls inside the simulated 95% interquantile range.** Reported honestly, including misses: total transplants 6,415 [6,398–6,432] vs actual 6,418 ✓; waitlist deaths ✓; **active waitlist size +4.5% ✗**; per-country and per-severity-stratum misses broken out. **Transfer:** publish a calibration table with per-stratum misses — trade volume, accept rate, trades-per-manager, position mix — and state where the sim is untrustworthy.
- **Stated limitations, verbatim:** *"we do not model potential behavioral adaptations by transplantation centers or changes in clinical outcomes that might arise in response to a policy shift."* — the honest name for simulator-policy co-adaptation risk in a deployed matching market.

Confidence: **high** (full text verified).

### Dynamic matching theory — what the sim should be testing

**Akbarpour, Li, Oveis Gharan** (arXiv:1402.3643) — https://arxiv.org/abs/1402.3643. Headline: *"waiting to thicken the market can be substantially more important than increasing the speed"* of matching **when departure information is available**; simple local algorithms are near-optimal; knowing *when agents will depart* helps far more than knowing more about the network. (Note: the round-2 thin-markets memo reads this same literature as favoring greedy *absent* departure information — the deciding variable is whether departure/urgency signals are observable. For FTF, deadlines and activity decay ARE observable, which is the interesting case.) Confidence: **high** (abstract).

**Ashlagi, Jaillet, Manshadi, *Kidney Exchange in Dynamic Sparse Heterogenous Pools*** (arXiv:1301.3509) — https://arxiv.org/abs/1301.3509. In small, sparse, heterogeneous pools (FTF's regime), 2-way cycles require very long waiting to beat greedy matching, while **3-way cycles get most of the gain at much shorter waits**. **Transfer:** direct argument for eventually simulating 3-team trades — in sparse pools that's where the surplus is. Confidence: **high** (abstract).

Further kidney-exchange simulators (abstract-level, **medium**): Biró et al. (arXiv:1904.07448); Carvalho et al. (arXiv:2309.13421, full-scale simulation of the Canadian KPD program); Verma & Rangaraj (arXiv:2012.06647, arXiv:2010.05105); Dai & He (arXiv:2302.09757).

### Ride-hailing / two-sided matching simulators (listing-level, medium)

Namdarpour & Chow (arXiv:2510.25796, validated on NYC taxi data); Zhang & Varma (arXiv:2411.19471); Bao et al., *Timing the Match* (arXiv:2503.13200); Lyu et al., *ProfiLLM* (arXiv:2606.18803), deployed on DiDi's production dispatcher with a 14-day online A/B (+0.47% GMV) — the industry pattern is **sim-for-development, A/B-for-truth**.

**School choice:** Sage & Flache (arXiv:2006.13531) — calibrates heterogeneous preferences via random-utility discrete choice. Confidence: **low-medium**.

> ⚠️ **Verification gap.** SRTR Simulated Allocation Model documentation (KPSAM/LSAM/TSAM) could **not** be retrieved (site 404s; PubMed cookie wall; Science/ACM 403). **Nothing about SRTR SAM, the Wey/Salkowski/Snyder offer-acceptance literature, or Ashlagi–Roth multi-hospital free-riding simulations is verified here — treat as unresearched, not absent.** ELAS is a close functional substitute and is fully verified.

---

## C. Practical guidance for a small-scale heterogeneous-agent league simulator

(§C1 validation methodology and §C2 calibration are covered in far greater depth by the companion appendix 02b — the dedicated ABM validation/calibration thread. Kept here: the failure-mode list, which the two threads converged on independently.)

### Failure modes, named

1. **Simulator-policy co-adaptation / overfitting the sim.** Virtual-Taobao's Action Norm Constraint is the cheap mitigation; RL4RS's held-out second environment is the cleaner structural fix.
2. **Over-optimistic accept rates.** The disengagement deficit (arXiv:2606.20708) and the "easy mode" inflation (arXiv:2603.11245). Any LLM-driven manager agent has acceptance biased high; calibrate against real accept/reject logs.
3. **MNAR/selection bias in the training log.** SOFA: you only observe offers someone chose to make; naive fitting inherits the proposer's policy.
4. **Metric–reward mismatch.** RL4RS: good AUC on the accept model can coexist with large reward error, which is what actually drives policy ranking.
5. **Degenerate equilibria / feedback collapse.** Chaney et al.: homogenization without utility gain.
6. **Equifinality / under-determination.** Many parameterizations fit the same moments; the deliverable is robust *policy orderings across the plausible set*, not parameter estimates.
7. **The simulated experiment isn't an experiment.** arXiv:2605.20767 — latent drift under intervention; use negative-control outcomes.
8. **Ranking instability with data volume.** Krauth et al. — offline rankings flipped with the amount of initial data.

---

## Closest domain-adjacent primary source — and the gap it leaves

**Parshall, Ali & Zimmerman, *A Genetic Algorithm for Optimizing Fantasy Football Trades with Playoff Biasing*** (arXiv:2511.17535) — https://arxiv.org/abs/2511.17535
Evaluated on a 12-team ESPN league; improves projected points ~3/week for both sides. But it **does not model the partner's accept/reject decision at all** — mutual projected gain is *assumed* to imply acceptance. A broader sweep surfaced nothing else in-domain. **That is the gap: the published state of the art in this exact domain optimizes trades against an assumed-acceptant counterparty. A calibrated accept/reject agent model is genuinely novel here, and the ELAS two-stage mixed-effects logistic is the ready-made blueprint.** Confidence: **medium** (abstract-level).

---

## Synthesis: a concrete recipe for the FTF league simulator

1. **Write the ODD first** (see appendix 02b §1.5) — "purpose **and patterns**" names up front which real-league patterns the sim must reproduce; that list *is* the validation spec.
2. **Trace-driven replay over synthetic generation** (ELAS). Replay real rosters and events; synthesize only the accept/reject decision.
3. **Two-stage accept model, mixed effects** (ELAS): stage 1 engagement, stage 2 acceptance, per-manager random intercepts partially pooled.
4. **Debias the training log before fitting** (SOFA). You only see proposed trades.
5. **Fit by likelihood, not by hand** (RecSim NG): score real trade trajectories under the generative model; MC-EM/HMC for latent manager state.
6. **Validate ELAS-style**: N replications, per-stratum interquantile-range calibration table, publish the misses.
7. **Hold out a season and a separate held-out-derived environment** (RL4RS); check **reward error**, not just accept-model AUC.
8. **Constrain the policy to the data support** (Virtual-Taobao ANC) so it can't farm simulator artifacts.
9. **Extended OFAT first, then global SA** (02b §2.10).
10. **Report policy *orderings* robust across the plausible parameter set**, never a point estimate of "+X% trade acceptance."
11. **Governance rule (Krauth et al.):** a policy winning in the sim earns a real test, never a ship decision; a policy losing in the sim is killed. Simulation is a *filter*, not a *verdict*.
12. **If LLM manager agents are used at all**: run ≥2 different simulator models and report the spread; measure USI-style calibration against real accept/reject; assume acceptance is biased high.
