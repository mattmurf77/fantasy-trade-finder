# Appendix to Round-3 Topic 02 — ABM validation & calibration (late-arriving research thread)

> Full report of the ABM validation/calibration research thread that had not yet returned when the
> main memo (02-acceptance-modeling-simulation-experimentation.md) was compiled. Companion to
> appendix 02a (simulation testbeds). Recorded 2026-08-16.
>
> **Framing the literature converges on:** for a simulator used as a *policy testbed*, the target is
> not point prediction of individual trades. It is (a) **rank-preservation** — does the sim order
> policies the same way reality does — and (b) **non-exploitability** — can a policy win in-sim by
> exploiting an artifact. Almost every source below maps onto one of those two.

---

## 1. Canonical ABM validation methodology

### 1.1 Sargent — Verification & Validation of Simulation Models (WSC 1981–2017; *Journal of Simulation* 7:12–24, 2013)
The field's standard V&V taxonomy: **conceptual model validity**, **computerized model verification**, **operational validity**, **data validity**; three approaches to who decides validity; the "problem entity → conceptual model → computerized model" paradigm with validation arcs on each edge.
- URLs: https://doi.org/10.1057/jos.2012.20 · https://dl.acm.org/doi/10.1145/318371.318379 · open WSC PDFs https://www.informs-sim.org/wsc11papers/016.pdf · https://www.informs-sim.org/wsc10papers/016.pdf
- **Transferable practice:** Split the validation ledger into four buckets and never conflate them. *Data validity* = are the Sleeper/consensus-derived values and roster snapshots correct. *Conceptual validity* = is "GM accepts if perceived surplus > threshold, subject to roster need and window" a defensible theory. *Verification* = does the code implement it. *Operational validity* = does output match observed league behavior. Use the cheap techniques first — they work at N=12 where statistics don't: **face validity** (blind-mix 20 sim-generated trades with 20 real trades, ask 3–5 experienced dynasty players to label which are real — a Turing test); **extreme-condition tests** (a rebuilding agent offered a 34-year-old WR must reject ~always); **degenerate tests** (all-identical agents ⇒ trade volume collapses toward zero, since mutual gain requires heterogeneous valuations); **traces** (single-agent step-through logs); **internal validity** (variance across seeds — if seed variance swamps policy effect, the testbed can't rank policies).
- **Confidence: high** on framework. **FLAG:** body not extractable in the research environment; technique list reconstructed from well-known content + the secondary index at https://faculty.sites.iastate.edu/tesfatsi/archive/tesfatsi/EmpValid.htm — verify against the PDF before formal citation.

### 1.2 Axtell, Axelrod, Epstein & Cohen — "Aligning Simulation Models" (*Comput. Math. Organ. Theory* 1:123–141, 1996) — DOCKING
Origin of **docking/alignment**: run two independently-built models against each other. Three equivalence levels: **numerical identity**, **distributional equivalence**, **relational alignment** (same qualitative input→output relationships).
- URLs: https://doi.org/10.1007/BF01299065 · https://hdl.handle.net/2027.42/44707
- **Transferable practice:** With ~dozens of real trades you cannot achieve numerical or distributional equivalence against reality. **Target relational alignment explicitly and say so in the docs.** Assert directional claims ("raising a GM's risk aversion lowers accept rate", "widening the two boards' want/accept gap lowers acceptance monotonically") and require the sim to reproduce the *sign and ordering* of each. Second use: dock the trade-acceptance engine against a deliberately simpler independent reimplementation (pure surplus-threshold, no roster fit) — divergences localize bugs and reveal which mechanism does the work.
- **Confidence: high** (taxonomy corroborated by Wilensky & Rand). **FLAG:** full text 403'd; metadata + secondary corroboration.

### 1.3 Wilensky & Rand — "Making Models Match" (*JASSS* 10(4):2, 2007)
Full primary account of replicating Axelrod's ethnocentrism model, documenting exactly what breaks.
- URL: https://www.jasss.org/10/4/2.html
- **Transferable practice (most immediately actionable in section 1):** their failure modes are exactly FTF's. (i) **Agent activation order** — materially different outcomes purely from event reordering. Whether GM #1 always proposes first, or proposal order is shuffled each week, will change outcomes; make ordering explicit, documented, *randomized-per-tick*, and test both. (ii) **Unshuffled agent lists** create systematic bias — shuffle team iteration order every tick. (iii) **Ambiguity in the written spec** broke their replication. Author-side checklist: state event order, state random-vs-sequential activation, publish pseudocode, publish sensitivity analyses.
- **Confidence: high** (primary HTML).

### 1.4 Grimm et al. — Pattern-Oriented Modelling (*Science* 310:987–991, 2005)
POM: use **multiple observed patterns at different levels of organization simultaneously as filters** to reject model structures and parameterizations. Several individually weak patterns jointly form a strong filter — the standard answer to "complex model, thin data."
- URLs: https://doi.org/10.1126/science.1116681 · https://pubmed.ncbi.nlm.nih.gov/16284171/ · practitioner follow-up: Gallagher et al., *Biological Reviews* 96(5), 2021, https://doi.org/10.1111/brv.12729
- **Transferable practice — the primary strategy given tiny data.** Do not calibrate to one number (trade count). Assemble 5–8 **weak but cheap** patterns from Sleeper league history and require the sim to hit all simultaneously:
  - trades per league-season (distribution across leagues, not one league);
  - trade *size* distribution (1-for-1 vs 2-for-1 vs 3+-for-3+);
  - fraction picks-only / players-only / mixed;
  - seasonal timing profile (preseason spike, deadline spike, post-deadline collapse);
  - concentration — Gini of trades-per-manager;
  - directional asymmetry: contenders acquire vets, rebuilders acquire picks/youth;
  - accept rate conditional on offer surplus (if offers are logged, not just completions);
  - dyad repetition — same pair trading repeatedly more than chance.
  Any parameter set that fails any filter is rejected. This is the documented cure for equifinality.
- **Confidence: high** on method; **FLAG:** *Science* text inaccessible — content from corroborated derived sources, chiefly the ODD-2020 paper which formalizes POM into the protocol.

### 1.5 Grimm et al. — ODD Protocol, second update (*JASSS* 23(2):7, 2020)
Seven elements: **Purpose *and patterns*** / Entities, state variables, scales / Process overview & scheduling / Design concepts / Initialization / Input data / Submodels. The 2020 update folds POM into element 1: state up front the **criteria by which you'll judge the model realistic enough for its purpose**. Points to **TRACE** for validation documentation.
- URLs: https://www.jasss.org/23/2/7.html · https://doi.org/10.18564/jasss.4259 · open copy https://bio.uib.no/te/papers/Grimm_2020_The_ODD_protocol_for_describing_agent-based.pdf
- **Transferable practice:** Write the ODD before the simulator, "Purpose and patterns" first — it commits acceptance criteria before there's temptation to move them. Element 3 (scheduling) pins the weekly tick order; element 4 (design concepts) declares the GM agents' *adaptation, objectives, prediction, sensing, interaction, stochasticity, observation* — "objectives" is where the accept/reject utility gets stated in the open rather than buried in code. Slots naturally into FTF's feature-scope-block habit.
- **Confidence: high** (primary HTML).

### 1.6 Windrum, Fagiolo & Moneta — "Empirical Validation of Agent-Based Models" (*JASSS* 10(2):8, 2007)
The taxonomy paper: **indirect calibration** / **Werker–Brenner** (empirical ranges → Bayesian pruning → "methodological abduction") / **history-friendly** modelling. Problem list includes over-parameterization, **under-determination/identification**, stylized-fact ambiguity, counterfactual validity under non-ergodicity, **time-scale ambiguity**.
- URLs: https://www.jasss.org/10/2/8.html · PDF https://www.jasss.org/10/2/8/8.pdf
- **Transferable practice:** Use **indirect calibration** as the named methodology — designed for exactly this situation (rich micro theory, thin macro data). (1) Fix agent decision rules from evidence you *can* get cheaply — structured interviews of dynasty managers (the operator's own documented trade philosophy counts as micro evidence under Werker–Brenner's expert-testimony step); (2) hard-bound each parameter from that evidence; (3) Monte-Carlo *within* the bounds; (4) keep the surviving region, not a point estimate. Also: **fix the time-scale explicitly** — one tick = one NFL week is a modeling decision with consequences; time-scale ambiguity is a recurring silent error.
- **Confidence: high** (primary HTML).

### 1.7 Fagiolo, Guerini, Lamperti, Moneta & Roventini — "Validation of Agent-Based Models in Economics and Finance" (LEM WP 2017/23; Springer 2019)
Three dimensions: **(i) comparison between artificial and real-world data; (ii) calibration and estimation; (iii) parameter-space exploration.** Emphasis on **stationarity and ergodicity**.
- URLs: https://ideas.repec.org/p/ssa/lemwps/2017-23.html · https://www.econstor.eu/bitstream/10419/174573/1/2017-23.pdf
- **Transferable practice:** Treat these as three separate work items, not one blob called "validation."
- **Confidence: high on the framing** (verbatim from abstract). **FLAG:** a full-text fetch produced a framing contradicting the authors' own abstract — believed to be a fetch-tool confabulation and discarded; read the PDF before citing internals.

### 1.8 Troost et al. — "How to keep it adequate: A protocol for ensuring validity in agent-based simulation" (*Env. Modelling & Software* 159:105559, 2023)
A **twelve-step protocol** running validity through the entire modeling process. Defines validation as "systematically substantiating the premises on which conclusions from simulation analysis for a particular modelling context are built" — validity is relative to the question asked.
- URLs: https://doi.org/10.1016/j.envsoft.2022.105559 · https://www.econstor.eu/bitstream/10419/266186/1/Troost_2023_validity_agent_based_simulation.pdf
- **Transferable practice:** Adopt the premise framing literally. The simulator's conclusion is "policy A beats policy B on mutual-gain trade yield." Enumerate the premises (GM utility form, acceptance noise, offer-arrival rate, value source, roster-need model); attach to each a line of evidence or an explicit "unsubstantiated, treated as uncertainty." That enumeration *is* the validation document and defines the uncertainty sweep.
- **Confidence: medium-high.** **FLAG:** the twelve individual steps not extracted; get from the PDF before building a checklist.

---

## 2. Calibration with limited data

### 2.1 Grazzini & Richiardi — "Estimation of ergodic agent-based models by simulated minimum distance" (*JEDC* 51:148–165, 2015)
Reference treatment of **SMD/SMM** for ABMs; consistency requires **ergodicity**.
- URLs: https://doi.org/10.1016/j.jedc.2014.10.006 · WP https://www.nuffield.ox.ac.uk/media/1690/abmestimation-ergodicv18.pdf
- **Transferable practice:** Implementable in an afternoon: pick moment vector **m** (the POM patterns), compute **m_real** from Sleeper history, minimize ‖m_sim(θ) − m_real‖_W with m_sim averaged over many seeds. The conditional in the title is the warning: **establish ergodicity first** or the estimator has no consistency guarantee. If the league is in a transient (expansion year, rookie-class shock), estimating on long-run moments is wrong.
- **Confidence: high** on citation/headline. **FLAG:** specific ergodicity tests not extractable.

### 2.2 Grazzini, Richiardi & Tsionas — "Bayesian Estimation of Agent-Based Models" (*JEDC* 2017)
Likelihood-free Bayesian estimation: KDE-approximated likelihood on simulated output + MCMC; compared against **ABC** across tolerance levels. Requires ergodicity/stationarity + burn-in.
- URL: https://www.nuffield.ox.ac.uk/economics/papers/2015/AB-v26.pdf
- **Transferable practice:** With ~dozens of real trades, a point estimate is a fiction. Go Bayesian; report a **posterior over GM-behavior parameters**; propagate into every policy comparison — "policy A beats B in 87% of posterior draws," not "A beats B." ABC is the pragmatic entry point. Informative priors from domain knowledge are exactly what §2.6 shows you need.
- **Confidence: medium-high.** **FLAG:** summarizing fetch, not direct read; confirm the published version's details.

### 2.3 Platt — "A Comparison of Economic Agent-Based Model Calibration Methods" (arXiv:1902.05938; *JEDC* 2020)
Head-to-head on models with known ground truth: **Bayesian estimation consistently outperforms frequentist objective-function approaches.**
- URLs: https://arxiv.org/abs/1902.05938
- **Transferable practice:** (1) Default to Bayesian/ABC over moment-distance minimization. (2) **Run a perfect-model / parameter-recovery experiment on your own simulator before trusting it**: pick known GM parameters θ*, generate a synthetic league season exactly the size of the real data, try to recover θ*. If θ* isn't recoverable from synthetic data of realistic size, it certainly isn't from real data — the single highest-value test on this list.
- **Confidence: high** (arXiv primary).

### 2.4 Lamperti, Roventini & Sani — "Agent-Based Model Calibration using Machine Learning Surrogates" (arXiv:1703.10639; *JEDC* 90:366–389, 2018)
ML surrogate over the parameter→output map + adaptive sampling; framed as a **filter** over parameter space.
- URLs: https://arxiv.org/abs/1703.10639
- **Transferable practice:** Probably unnecessary at FTF scale — a 12-agent season is cheap to simulate; brute-force Monte Carlo may beat surrogate overhead. The portable idea is **surrogate-as-filter**: train a classifier on (θ → satisfies all POM patterns?) to map the *feasible region*, more informative than a best-fit point.
- **Confidence: high** on abstract/venue.

### 2.5 ten Broeke, van Voorn, Ligtenberg & Molenaar — "The Use of Surrogate Models to Analyse Agent-Based Models" (*JASSS* 24(2):3, 2021)
SVM/SVR surrogates on replicated Latin-hypercube designs (1000 points) with adaptive resampling; acceptance thresholds F1 ≥ 0.9 / CoP ≥ 0.9; five-fold CV + independent test set. Uses: **behavioral-regime classification**, sensitivity indices, tipping-point location. Caution: surrogates cannot represent stochastic variability.
- URLs: https://www.jasss.org/24/2/3.html · https://doi.org/10.18564/jasss.4530
- **Transferable practice:** The **regime-classification** use is the one to take: classify parameter space into *no-trade-market* / *healthy market* / *degenerate churn*; verify default parameters sit well inside "healthy," not on a boundary. A policy comparison run near a regime boundary measures the boundary, not the policy.
- **Confidence: high** (primary HTML).

### 2.6 Srikrishnan & Keller — "Small increases in agent-based model complexity can result in large increases in required calibration data" (arXiv:1811.08524)
Perfect-model experiment: limited datasets **may not constrain a model with just four parameters**; spatially-aggregated data can be **insufficient to identify model structure** (with vs without agent interactions); many ABMs "require informative prior distributions to be descriptive," justified by "independent lines of evidence."
- URLs: https://arxiv.org/abs/1811.08524
- **Transferable practice — the most sobering result for this project:** (i) **cap free parameters at ~3–5** per agent archetype; (ii) prefer a **small number of discrete GM archetypes** (contender / rebuilder / win-now-overpayer / hoarder) with shared parameters — 12 independently-parameterized agents is unidentifiable from a season of trades; (iii) league-level trade counts will not reveal whether interaction structure matters — that needs offer-level or dyad-level data; (iv) budget real effort for priors — a survey of 20–30 dynasty managers on accept thresholds is a cheaper path to validity than any estimator.
- **Confidence: high** (arXiv primary).

### 2.7 Franke & Westerhoff — "Structural stochastic volatility in asset pricing dynamics" (*JEDC* 36(8):1193–1211, 2012)
MSM estimation with bootstrap weighting; introduces the **Moment Coverage Ratio (MCR)** — fraction of Monte Carlo runs in which *all* simulated moments land inside their empirical confidence intervals; runs a **model contest** across specifications.
- URLs: https://doi.org/10.1016/j.jedc.2012.04.006 · https://www.econstor.eu/bitstream/10419/45552/1/658137409.pdf
- **Transferable practice:** **MCR is the right headline validation number and is trivial to compute.** Bootstrap CIs for each POM pattern from real Sleeper data; run 1000 sim seasons; report the % in which *every* pattern falls inside its interval. Joint, all-or-nothing — much harder to game than averaging per-moment errors; degrades honestly with small samples. Second: run a **model contest** — naive baseline (random acceptance at fitted rate), pure value-surplus model, full roster-fit + window model. If the naive one isn't clearly worse on MCR, the mechanisms aren't earning their keep.
- **Confidence: high** on MCR and its role. **FLAG:** moment-list specifics unverified.

### 2.8 Gilli & Winker — "A global optimization heuristic for estimating agent based models" (*CSDA* 42(3):299–312, 2003)
ABM objective surfaces are **rugged and non-convex**; local optimizers fail.
- URLs: https://doi.org/10.1016/S0167-9473(02)00214-1
- **Transferable practice:** Don't point-optimize GM parameters with a local method — global heuristic (threshold accepting, differential evolution, CMA-ES) or skip optimization for ABC/posterior sampling. **Plot the objective surface** in 2-D slices — a flat valley is a direct visual of unidentifiability.
- **Confidence: medium** (secondary sources).

### 2.9 Dyer, Cannon, Farmer & Schmon — black-box Bayesian inference & GNN calibration (arXiv:2202.00625; arXiv:2206.07570); Wang et al., SBI guide (arXiv:2409.19675)
Neural posterior/density-ratio estimation for ABMs; GNN calibration directly to *agent-level microdata*. But the SBI guide finds classical statistical SBI **more accurate than neural** when the simulation budget suffices.
- **Transferable practice:** A league *is* a temporal graph (12 nodes, trade edges over weeks) — calibrating on graph structure uses far more information than a trade count. Practically: **start with classical ABC/SMM** — at 12 agents the simulation budget is large relative to model size, exactly the regime where classical methods win.
- **Confidence: high** on abstracts; **medium** on the guide's finding.

### 2.10 ten Broeke, van Voorn & Ligtenberg — "Which Sensitivity Analysis Method Should I Use for My Agent-Based Model?" (*JASSS* 19(1):5, 2016)
OFAT vs regression vs **Sobol'**: OFAT reveals nonlinearities/tipping points cheaply (1,650 vs 17,000 runs) but misses interactions; regression fails on skewed output; **Sobol' is unreliable when output distributions are non-normal** and obscures mechanism. 11 of 15 parameters had tipping points. Recommendation: extended OFAT first.
- URLs: https://www.jasss.org/19/1/5.html
- **Transferable practice:** Trade-count output will be skewed and zero-inflated — precisely where Sobol' misleads. **Extended OFAT first**, plotting the whole output distribution at each parameter value, hunting the tipping point where the trade market dies or explodes. Note the tension with Saltelli et al., "Why so many published sensitivity analyses are false" (arXiv:1711.11359; *EMS* 114:29–39, 2019) which condemns OFAT-only. Resolution: OFAT to *understand*, a global method to *claim robustness*.
- **Confidence: high** (primary HTML); **medium-high** for Saltelli.

---

## 3. Stylized facts, failure modes, and the co-adaptation problem

### 3.1 Barde — "Direct comparison of agent-based models of herding in financial markets" (*JEDC* 73:329–353, 2016)
Information-theoretic model comparison of three ABMs across 24 real series **plus ARCH processes as a benchmark**. Killer finding: the best ABM *"is generally not distinguishable from an ARCH-type process."*
- URLs: https://doi.org/10.1016/j.jedc.2016.10.005
- **Transferable practice:** **Always include a stupid benchmark in the contest.** For FTF: every GM accepts any offer with fixed probability p, tuned to match total trade volume. If the heterogeneous-GM simulator can't beat that on the joint pattern set, the agent mechanisms are decorative — and **any policy ranking it produces is a ranking against noise**. A cheap, decisive gate to run before trusting any policy comparison.
- **Confidence: high**.

### 3.2 Lamperti — GSL-div (*J. Econ. Interaction & Coordination* 13(1):143–171, 2018)
Information-theoretic distance between observed and simulated **dynamics** (pattern distributions, not summary statistics); no likelihood, **no stationarity requirement**. Independently documents equifinality: *"many different combinations of traders' behavioural rules are compatible with the same observed dynamics"* — though successful fits all shared a strong trend-following component.
- URLs: https://doi.org/10.1007/s11403-017-0206-3
- **Transferable practice:** (1) For *timing* of trade activity across a season (non-stationary by construction), a pattern-distribution distance beats moment-matching. (2) Equifinality is the expected outcome; report **what is invariant across all good fits** ("every configuration matching the data requires roster-need weighting > X") — the invariant is the real finding, the point estimate is not.
- **Confidence: high** on method/finding; math internals not extracted.

### 3.3 Platt & Gebbie — "The Problem of Calibrating an Agent-Based Model of High-Frequency Trading" (arXiv:1606.01495)
Models can reproduce known stylized facts while being badly calibrated and poorly identified — *"inadequacies of a stylized fact-centric approach to model validation."*
- **Transferable practice:** **Matching POM patterns is necessary, not sufficient.** Split patterns into **construction patterns** (used to build/calibrate) and **held-out validation patterns** (checked only at the end). A pattern you engineered the model to produce is not evidence.
- **Confidence: high** (arXiv primary).

### 3.4 Grazzini — "Analysis of the Emergent Properties: Stationarity and Ergodicity" (*JASSS* 15(2):7, 2012)
Cheap **Wald–Wolfowitz runs tests**: within-run (stationarity — window moments scatter randomly around the global moment) and across-run (ergodicity — subsample moment distribution vs across-seed distribution). Non-ergodic systems cannot have structural parameters reliably estimated from observed data.
- URLs: https://www.jasss.org/15/2/7.html
- **Transferable practice:** **Run this before any calibration — an hour of work that determines the whole methodology.** A dynasty league is a strong candidate for **non-ergodicity** (early trades change rosters change needs change trades — path dependence is the point of the domain). If non-ergodic: (a) SMD/SMM consistency doesn't apply; (b) report distributions over many seeds, never one long run; (c) initial conditions (starting rosters) are *parameters*, sampled or held fixed deliberately. The practical rule for a policy testbed: **compare policies on paired seeds and identical initial rosters; report the paired difference distribution.**
- **Confidence: high** (primary HTML).

### 3.5 Oreskes, Shrader-Frechette & Belitz — "Verification, Validation, and Confirmation of Numerical Models in the Earth Sciences" (*Science* 263:641–646, 1994)
The canonical "validation is impossible" essay: agreement between model and data is the fallacy of **affirming the consequent**; all you accumulate are **confirming instances**. Models are **heuristics**, not truth machines.
- URLs: https://doi.org/10.1126/science.263.5147.641
- **Transferable practice:** Set expectations in writing: the simulator will never be "validated." Claimable: "confirmed against N independent patterns, K held out; falsified in regime R; policy ranking stable across the calibrated posterior." Make the success criterion **falsification-shaped** (specify in advance what sim behavior would make you discard the testbed). A simulator-preferred policy earns a shortlist, never a launch.
- **Confidence: medium-high on the argument.** **FLAG — strongest flag on this list:** neither full text nor abstract was reachable in the research session; the summary is from background knowledge. **Verify before quoting.**

### 3.6 Krauth et al. — "Do Offline Metrics Predict Online Performance in Recommender Systems?" (arXiv:2011.07931)
(Also covered in appendix 02a §A3.) The transfer that changes the design: **never report a policy ranking from a single simulator configuration.** Sweep the axes that mattered (history volume, exploration setting, warm-up weeks); report only rankings **stable across the sweep**. Build 3–5 league archetypes (active traders, dormant league, mixed), not one environment.
- **Confidence: high**.

### 3.7 Hsu et al. — "Minimizing Live Experiments in Recommender Systems: User Simulation to Evaluate Preference Elicitation Policies" (arXiv:2409.17436; KDD 2024)
The industry existence proof: YouTube Music new-user onboarding. Counterfactually-robust behavior models trained on logged production data; the simulator **reliably predicted live-deployment performance on key metrics**.
- URLs: https://arxiv.org/abs/2409.17436 · https://doi.org/10.1145/3626772.3661358
- **Transferable practice:** The copyable validation protocol: **run a small number of real experiments, check whether the simulator predicted their outcomes** — ideally arm *ordering*, minimum the sign. Even 3–4 real experiments give a meaningful rank-correlation check. Their "counterfactually robust" emphasis: real trade data is logged under the current recommender, so an agent model naively fit to it undervalues policies proposing off-distribution trades. Mitigations: hold out trades that occurred outside the app, keep exploration/randomization in live suggestions, check sensitivity to the offer-generation distribution.
- **Confidence: high**.

### 3.8 Laidlaw, Singhal & Dragan — "Correlated Proxies: A New Definition and Improved Mitigation for Reward Hacking" (arXiv:2403.03185; ICLR 2025 Spotlight)
Reward hacking occurs when **the correlation between proxy and true reward, over states visited by a reference policy, breaks down under optimization**. Regularizing toward a reference policy prevents it; proposes χ² divergence between **occupancy measures**.
- URLs: https://arxiv.org/abs/2403.03185
- **Transferable practice — the precise formal statement of simulator-policy co-adaptation risk.** The sim's accept model is a proxy calibrated on the distribution of trades that actually occur; a policy optimized hard against it drifts off-distribution, exactly where the proxy was never established. Defenses: (1) **occupancy-distance monitoring** — measure divergence (KL/χ² over trade-type/size/position-mix histograms) between a candidate policy's induced trade distribution and the calibration distribution; discard or discount drifting policies regardless of in-sim score; (2) **regularize toward the incumbent** — in-sim gain minus divergence penalty. Concrete domain exploit this catches: "propose enormous 5-for-5 junk-filler packages because the surplus threshold is additive."
- **Confidence: high**.

### 3.9 Stavinova et al. survey (arXiv:2206.11338) + Aouali et al. (arXiv:2209.08642)
The survey's simulator-quality section is the domain-specific complement to Sargent; Aouali et al. supply the written-down argument for *why* simulation is the right tool for a reward-optimizing (two-sided acceptance) matcher.
- **Confidence: medium-high** (abstracts).

---

## 4. Synthesized protocol for the FTF league simulator

Ordered by value-per-hour, tuned to 12 agents and thin data:

1. **Write the ODD "Purpose and patterns" section first** (§1.5) — commit acceptance criteria before code. Pin tick semantics and agent activation order explicitly (§1.3).
2. **Assemble 6–8 POM patterns** from Sleeper history across *many* leagues; split into construction vs **held-out validation** patterns (§1.4, §3.3).
3. **Run the ergodicity/stationarity runs-tests** (§3.4). Result determines long-runs vs seed-ensembles and whether SMD consistency applies at all.
4. **Perfect-model parameter-recovery experiment** at real data volume (§2.3, §2.6). Cut parameters/archetypes until θ* is recoverable. Expect to land at 3–5 free parameters and 3–4 GM archetypes.
5. **Calibrate with ABC/Bayesian, informative priors, keep the posterior** (§2.2, §2.6). Manager interviews/surveys are legitimate evidence and what makes this identifiable.
6. **Report MCR** as the headline validation number (§2.7), computed on **held-out** patterns.
7. **Model contest against a trivial baseline** (§3.1). Gate: no policy conclusions until the full model beats fixed-probability acceptance.
8. **Extended OFAT sweeps → regime map** (§2.10, §2.5). Confirm defaults sit interior to a healthy-market regime.
9. **Only now compare policies** — paired seeds, identical initial rosters, ranking reported across the posterior *and* across warm-up/history/league-archetype sweeps; report only rank-stable conclusions (§3.6).
10. **Guard against co-adaptation**: occupancy-distance monitoring; penalize drifting policies (§3.8). Watch for junk-filler stuffing and threshold-edge exploits.
11. **Confirm against reality**: a few real experiments; check the sim predicted their *ordering* (§3.7). Simulator output shortlists; it does not ship (§3.5).

---

## 5. Confidence & access flags

| Source | Access achieved | Confidence |
|---|---|---|
| Windrum, Fagiolo & Moneta 2007 (JASSS) | Full HTML | High |
| Grimm et al. 2020 ODD (JASSS) | Full HTML | High |
| Wilensky & Rand 2007 (JASSS) | Full HTML | High |
| Grazzini 2012 ergodicity (JASSS) | Full HTML | High |
| ten Broeke et al. 2016 SA (JASSS) | Full HTML | High |
| ten Broeke et al. 2021 surrogates (JASSS) | Full HTML | High |
| Platt 2019 / Platt & Gebbie 2016 / Srikrishnan & Keller 2018 / Laidlaw 2024 / Krauth 2020 / Hsu 2024 (arXiv) | Abstract | High |
| Lamperti, Roventini & Sani 2017 | Abstract | High (learner type unconfirmed) |
| Dyer et al. 2022 ×2 | Abstract / listing | High / medium |
| Barde 2016 (JEDC) | Full abstract via metadata | High |
| Fagiolo et al. 2017/2019 | Abstract only — full-text fetch contradicted the abstract; discarded | Medium |
| Grazzini & Richiardi 2015 | Abstract + DOI; body not extractable | Medium-high |
| Grazzini, Richiardi & Tsionas | WP PDF via summarizing fetch | Medium |
| Franke & Westerhoff 2011/2012 | Record abstract; moment details unverified | Medium-high |
| Troost et al. 2023 | Abstract + DOI; 12 steps not extracted | Medium-high |
| Sargent | Abstract via metadata; technique list reconstructed | Medium-high |
| Axtell et al. 1996 | Metadata only (403); corroborated via Wilensky & Rand | Medium-high |
| Grimm et al. 2005 POM (Science) | Abstract publisher-elided; derived sources | Medium |
| Gilli & Winker 2003 | Secondary only | Medium |
| Lamperti GSL-div | Record abstract; internals not extracted | Medium-high |
| Saltelli et al. 2017/2019 | arXiv preprint verified; EMS DOI unverified | Medium-high |
| **Oreskes et al. 1994 (Science)** | **Neither full text nor abstract reachable — background knowledge only** | Medium — **verify before quoting** |
| Marks 2007 | Secondary only | Low — completeness only |

Environment notes for follow-up: the research session's WebSearch budget was exhausted mid-task (later sourcing via the arXiv API and Semantic Scholar graph API); and **no PDF text extraction was available on the machine** (`pdftotext`/`mutool`/`qpdf` absent) — several key PDFs downloaded but couldn't be read. Installing poppler (`brew install poppler`) would let a follow-up session close most medium-confidence flags.
