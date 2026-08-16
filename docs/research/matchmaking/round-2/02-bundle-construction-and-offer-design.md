# Round 2 — Topic 02: Constructing the Package — Bundle Generation & Offer Design

> Research memo, 2026-08-15. Round-2 follow-up to the round-1 matchmaking research, covering the gap flagged there: once two managers are identified as compatible trade partners, how do you build the actual multi-asset offer? Draws on bundle-recommendation literature, combinatorial exchange theory, automated negotiation (ANAC), negotiation science (MESO, anchoring, log-rolling), and sports trade-machine precedents.

Confidence flags used throughout: **[HIGH]** = multiple converging sources, **[MED]** = one solid source or converging-but-thin, **[LOW]** = plausible inference / speculative transfer.

---

## 0. TL;DR

Package construction is a solved-enough problem if you decompose it the way every successful system does: **(1) pick the partner, (2) pick a centerpiece, (3) search a constrained package space for balance, (4) validate against a fairness band and both parties' own valuations, (5) present 2–3 differently-shaped equivalent offers with a two-sided explanation.** The single most transferable finding: **mutual gain comes from valuation divergence, not from "fair value"** — a trade both sides should accept exists precisely where the two managers' boards disagree, and FTF's per-user Elo boards mean it can compute this *directly* instead of inferring it, which almost no published system can. The second most important finding: **acceptance is a psychology problem, not just a math problem** — fixed-pie bias makes recipients distrust offers that are objectively good for them, and the countermeasures (MESO choice sets, two-sided explanations, neutral-mediator framing) are well documented and cheap to build.

---

## 1. Research threads and findings

### 1.1 Bundle recommendation: generation vs. ranking **[HIGH]**

The bundle-recsys field splits cleanly into two tasks, and the split matters because almost all commercial fantasy tools sit on the wrong side of it for FTF's purpose:

- **Bundle ranking (discriminative):** rank/match *pre-existing* bundles to users. The bulk of the literature (user–item + bundle–item affiliation graphs, BPR-style ranking losses).
- **Bundle generation (generative):** *construct new* bundles for a user. Methods include policy-based RL that builds bundles sequentially with a reward balancing user preference against item compatibility (BYOB), graph-generation approaches that learn item–item structure (BGGN), non-autoregressive one-shot generation (BundleNAT), and LLM/instruction-driven generation (BRIDGE, Text2Bundle). A 2024 survey (arXiv 2411.00341) formalizes the discriminative/generative taxonomy.

Key recurring insight: the core difficulty of generation is producing a set that satisfies **two objectives at once — user preference and internal coherence of the bundle** (item compatibility). In FTF terms: a package must be wanted by the receiver *and* make sense together (not three backup RBs when the receiver needs one starter).

The complementarity/substitutability literature (McAuley et al.'s substitute/complement networks; Amazon Science's finding that co-purchase ≠ complementarity — co-purchase-only pairs rated ~30% more complementary than pairs also co-viewed) says relationships between items are **asymmetric and typed**, and modeling them beats treating items independently. For trades the analogue: two players in a package can be substitutes (two startable TEs — value sub-additive for the receiver) or complements (a QB stack, or a starter + his handcuff — value super-additive). **Package value is not the sum of item values, and the direction of the deviation depends on the receiving roster.**

**Generation-vs-ranking verdict for FTF [MED]:** the neural generation machinery exists because e-commerce has millions of items and no enumerable package space. FTF's space (two ~25-asset rosters, packages capped at 3+picks per side) is small enough that *constrained enumeration + scoring* does what deep generators do, with full explainability. Take the *task decomposition* from this literature, not the models.

### 1.2 Combinatorial exchange & package bidding **[HIGH]**

Combinatorial auctions exist because bidders' package valuations are **non-additive**: complements (package worth more than the sum) and substitutes (worth less). Two transferable results:

- **Winner determination is NP-hard** in general combinatorial exchanges; real systems cope with constrained bundle languages, small cardinality limits, and heuristics — exactly the "cap package size at 3-for-3" instinct, given theoretical backing.
- **Myerson–Satterthwaite (1983):** with two parties holding *private* valuations, no mechanism is simultaneously efficient, truthful, voluntary, and budget-balanced — private value information inherently blocks some mutually beneficial trades. Recent work shows second-best mechanisms recover ≥ 1/2 of first-best gains (arXiv 2606.03849). **Why this matters for FTF [HIGH]:** M–S is the formal statement of why leaguemates fail to make trades that would benefit both — each side shades their stated values. FTF *sidesteps the impossibility entirely* because both managers have already revealed their true-ish valuations to the app via matchup votes. The app is a trusted third party holding both boards — it can find the efficient trades the parties' own bargaining would strangle. This is the strongest theoretical justification for the product's core loop, and worth stating in marketing language someday: "the trades your league can't find on its own."

### 1.3 Automated negotiation & offer construction **[HIGH]**

The ANAC (Automated Negotiating Agents Competition, 2010–present) literature is the richest source on *how agents actually generate multi-issue offers*:

- Standard architecture is **BOA: Bidding strategy, Opponent model, Acceptance condition** — three separable modules. Bid generation typically: pick a target utility for yourself (time-/concession-driven), then among all packages at that utility level, **choose the one the opponent model says the opponent likes most**. That inner step is exactly log-rolling, automated.
- Top agents explicitly aim bids at the **estimated Pareto frontier**, using multi-objective optimization (e.g., SPEA2 over own-utility × estimated-opponent-utility) — Pareto-efficient bid generation measurably increases both individual and social welfare (arXiv 2009.08302 beat ANAC'19 winners this way).
- Negotiation-support-system (NSS) research adds the **neutral-mediator framing**: a "single negotiating text" the mediator iteratively improves for both parties, and "improving directions" methods that walk a tentative agreement toward Pareto optimality. An NSS proposes allocations satisfying individual rationality, equity, and Pareto efficiency. A 2026 paper (Conditional Graph Diffusion, arXiv 2606.02209) frames offer generation with three normative targets worth stealing as metric names: **individual rationality rate** (both sides prefer offer to no deal — they hit 0.997), **security gap** (distance from exploitation), and **symmetry gap** (equity of the surplus split).

**Transfer [HIGH]:** FTF is structurally an NSS/mediator, not a negotiating agent — it holds *both* utility functions, so it doesn't need opponent modeling, concession curves, or acceptance-condition games. It should jump straight to the mediator's job: generate offers on/near the joint Pareto frontier and split the surplus roughly evenly.

### 1.4 MESO, anchoring, log-rolling, fixed-pie **[HIGH]**

- **MESO (Multiple Equivalent Simultaneous Offers):** present 2–3 offers of equal value *to the presenter*, differently shaped. Documented effects (Ames & Mason 2015, OBHDP; Medvec & Galinsky practitioner work; PON/Harvard summaries): offers **more likely to be accepted**, recipients **more satisfied**, presenters achieve **better outcomes without relational damage**, MESOs **anchor more strongly** (recipients adjust less), are perceived as **more sincere/flexible**, and — crucially for FTF — **the recipient's choice among variants reveals their preferences**. Standard guidance: don't exceed ~3 offers.
- **First-offer anchoring:** first offers correlate ~0.497 with final outcomes (Orr & Guthrie meta-analysis); a 2025 meta-analysis (Petrowsky et al., OBHDP) confirms a general first-mover advantage. Precise numbers anchor harder than round ones (Mason et al. 2013), though extreme precision can signal inflexibility in take-it-or-leave-it contexts.
- **Log-rolling** — conceding on issues you value less in exchange for issues you value more — is *the* mechanism of integrative bargaining, and it is mathematically identical to FTF's board-divergence trade construction. Key experimental caveat (Moran & Ritov 2002, J. Behavioral Decision Making): **recipients do not recognize log-rolling offers as more attractive than distributive ones** — the fixed-pie assumption survives contact with a genuinely integrative offer — *but* log-rolling first offers still anchored within-issue and produced higher profits for the initiator *and higher joint profit*. Translation: a mathematically win-win package will NOT sell itself; the fixed-pie reflex ("if they offered it, it must be bad for me") must be actively designed against.
- **Fixed-pie bias** is reduced by information exchange about priorities, perspective-taking, and value-focused framing — in-app, that means the explanation layer ("here's why this helps THEM" shown to each side) is doing debiasing work, not decoration.

### 1.5 Sports trade machines & fantasy calculators **[HIGH]**

What existing tools actually do:

| Tool | Generates or validates? | Mechanism |
|---|---|---|
| ESPN NBA Trade Machine | Validates only | CBA salary-matching rules: over-cap teams may take back ≤125% + $100K of outgoing salary (dollar-for-dollar above second apron). Instant legal/illegal verdict + reason. |
| Fanspo | Validates + social | Same CBA validation, plus cap analytics, an "Explain Yourself" rationale field, and community voting on proposed trades. |
| KeepTradeCut calculator | Validates | Crowdsourced values (26.5M+ 3-way "keep/trade/cut" votes — structurally similar to FTF's 3-player matchups). Applies a **non-linear "raw adjustment"** that discounts multi-player sides (a 5000-value player carries only ~26% of the adjustment weight of a 9999 player), implementing "four quarters ≠ a dollar" / roster-clogger logic. Known exploit: junk players still add positive value, so fair-looking trades can be manufactured by stuffing. |
| FantasyCalc | Validates | Values regressed from millions of *real completed trades* — market-revealed values rather than opinion votes. |
| DLF Trade Finder | Precedent search | Searches thousands of real MFL league trades for comps involving a player — "what does the market actually pay" evidence, filterable by league settings. |
| Dynasty Dealmaker | **Generates** | Closest live competitor to FTF's ambition: syncs Sleeper, scans all rosters, classifies contender/rebuilder, constructs packages, attaches an **acceptance-probability rating** and a two-sided narrative ("helps Team A's need for youth and Team B's title push"). Freemium token pricing. |
| IBM/ESPN trade system (arXiv 2111.02859) | **Generates, at scale** | Production pipeline: (1) pair teams by **cosine dissimilarity** of strengths/weaknesses; (2) **0-1 knapsack** selects each team's outgoing players; (3) ensemble of 6 valuation models + SME rules scores packages; (4) post-processors score 6 objective measures per trade; fairness is **roster-contextual** (positional depth, slot counts). Enforced 100% trade uniqueness for diversity. Expert-judged high-quality rate went 76.9% → 97.3% across seasons via error-analysis loops. |
| GA trade optimizer (arXiv 2511.17535) | **Generates** | Genetic algorithm seeded with 1-for-1s, five mutation operators (add/remove/swap/combine/new), fitness = playoff-weighted user gain + opponent gain − fairness penalty, team-specific elitism for diversity. Produced trades adding ~3 proj. pts/week to *both* sides. Note its stated objective includes user gain "while maintaining apparent fairness" — it's a user-agent, not a neutral mediator. |

**The pattern [HIGH]:** validation tools use a *hard constraint band* (salary match, value tolerance) as the fairness gate; the two real generators both use a **staged pipeline** (partner pairing → outgoing-asset selection → package scoring) rather than searching the raw combinatorial space, and both treat **diversity of suggestions** as a first-class requirement.

### 1.6 Asymmetric valuation & gains from trade **[HIGH]**

Dynasty strategy content is unanimous on the economics: contenders value proven current production, rebuilders value youth and picks — the same asset carries different value on different timelines, and "people become so focused on chasing tomorrow that they discount proven production today; that's where value is created." This is comparative advantage applied to rosters. Formally, with per-user value functions `v_A`, `v_B`:

```
joint_gain(P_out, P_in) = [v_A(P_in) − v_A(P_out)] + [v_B(P_out) − v_B(P_in)]
```

Both bracketed terms can be simultaneously positive **iff the boards disagree** about the assets exchanged. So the generator's search should be *divergence-driven*: A should send assets where `v_B − v_A` is most positive, and receive assets where `v_A − v_B` is most positive. Maximum-joint-gain trades live where board divergence is largest; the fairness question is then how the surplus is *split*, which is a separate knob from whether the trade is worth doing.

---

## 2. Best practices

1. **Stage the pipeline; never search raw package space.** Partner selection → centerpiece selection → return-package search → fairness/rationality validation → presentation. Both production generators (IBM/ESPN, Dynasty Dealmaker) and the ANAC BOA architecture converge on decomposition. **[HIGH]**
2. **Enforce dual-board individual rationality as a hard gate.** Every suggested package must clear `v_A(in) − v_A(out) ≥ ε_A` AND `v_B(out) − v_B(in) ≥ ε_B` — each side gains *on their own board*. This is the ANAC "individual rationality" criterion, the NSS mediator's first test, and log-rolling formalized. FTF's existing `user_gain_epsilon` gate (#108) is this — extend it to both sides of every generated package. **[HIGH]**
3. **Maximize joint gain, then split it near-evenly.** Rank candidate packages by total surplus (sum of both sides' own-board gains), and among near-ties prefer the most symmetric split. Track the CGD paper's three metrics: individual-rationality rate, security gap, symmetry gap. Lopsided splits are what get trades vetoed and apps called biased. **[HIGH]**
4. **Value packages non-additively, in roster context.** Two adjustments, both precedented: (a) a KTC-style **consolidation discount** — the multi-asset side is worth less than its sum, scaled non-linearly by value concentration; (b) **marginal-lineup value** — an asset's worth to a receiver is its effect on *that roster* (positional depth, starter slots, bye/timeline fit), per IBM/ESPN's depth- and slot-aware trade cost. **[HIGH]**
5. **Use a fairness band as a constraint, not an objective.** Salary matching (125% + $100K) is the template: a package must fall within ±X% of consensus/league-market value of what it returns, with X possibly widening for smaller packages. The band is a *defensibility* check (would the league veto? does it look absurd?) layered on top of dual-board gain, which is the *acceptance* check. **[HIGH]**
6. **Present 2–3 MESO variants, equivalent on the recipient's board, differently shaped.** E.g., for the same centerpiece: a youth-heavy return, a pick-heavy return, a depth/consolidation return. Documented effects: higher acceptance, higher satisfaction, stronger anchoring, perceived sincerity — and the variant the manager picks (or counters from) is free preference elicitation to feed back into their board. Cap at 3. **[HIGH]**
7. **Explain the trade in both directions, to both parties.** Fixed-pie bias means recipients distrust even objectively good offers; Moran & Ritov showed integrative offers aren't recognized as such. Dynasty Dealmaker's two-sided narrative and Fanspo's "Explain Yourself" are the market versions. Show each manager (a) their own gain in their own board's terms, and (b) *why the other side plausibly says yes* (timeline/positional story). The second half is the debiasing payload — it preempts "this must be a trap." **[HIGH]**
8. **Frame the app as neutral mediator, not as the user's shark.** The NSS "single negotiating text" posture — "here's a draft both of you can improve" — measurably supports agreement, and it protects the two-sided marketplace (every manager is the counterparty in someone else's suggestion). The suggested package is also the first offer and will anchor (~0.5 correlation with final outcome), so anchor at the *joint-gain* point, not at either side's max extraction. **[HIGH]**
9. **Enforce diversity across the suggestion list.** IBM/ESPN enforced 100% trade uniqueness; the GA used team-specific elitism. Don't show five perturbations of the same deal; vary centerpiece, partner, and package shape across the list. **[MED]**
10. **Close the loop on outcomes.** IBM/ESPN's 76.9% → 97.3% quality jump came from structured error analysis on expert-judged trades. Instrument accept/decline/counter/veto per suggestion and per MESO variant, and mine declines for which term of the model (value, fit, framing) failed. **[MED]**

---

## 3. Antipatterns

1. **Additive package valuation.** Summing item values makes "four quarters for a dollar" trades look fair and invites junk-stuffing — KTC's documented exploit is that even worthless players contribute positive adjustment, so any trade can be dressed up as fair. Non-linear consolidation adjustment plus a per-package asset cap is the fix. **[HIGH]**
2. **One-sided optimization with cosmetic fairness.** The GA paper's objective — maximize user gain "while maintaining apparent fairness" — is fine for a user-agent tool, but poison for a neutral platform: the counterparty is also your user, and repeated slanted suggestions burn trust in both directions. **[HIGH]** (as an antipattern *for a mediator app specifically*)
3. **Evaluating instead of generating.** Nearly the whole commercial field (KTC, DTC, FantasyCalc, ESPN TM, Fanspo) only validates user-built packages. The generation side is where FTF differentiates; don't let the product collapse back into another calculator. **[HIGH]**
4. **Single take-it-or-leave-it offers.** Forgoes every documented MESO benefit and reads as an ultimatum; also wastes the preference-elicitation channel. **[HIGH]**
5. **Treating consensus value as the acceptance criterion.** A trade that's "fair on KTC" but negative on the recipient's own board will be declined; one that's "unfair on KTC" but positive on both boards may still be vetoed by the league. You need both tests, in the right roles: own-board gain decides *acceptance*, consensus band decides *defensibility*. Conflating them kills exactly the divergence-driven trades that carry the joint gain. **[HIGH]**
6. **Ignoring roster feasibility.** Packages that leave a side with zero startable QBs, exceed roster/taxi limits, or trade away a starter for three bench-cloggers fail the "internal coherence" half of bundle generation. Feasibility screens come before value math. **[MED]**
7. **"You win this trade by X" framing.** Any UI that scores the trade as won/lost on a single axis re-installs the fixed pie: the other manager sees the same screen and concludes they lost. Frame gains per-side, in each side's own terms. **[MED]**
8. **Unbounded package search.** C(25,3)² is ~5.3M combos per ordered pair before picks; across a 12-team league that's billions. Centerpiece anchoring + caps + pruning by board divergence keeps it trivial; brute force does not scale and, per combinatorial-auction theory, never will. **[HIGH]**
9. **MESO variants equivalent on the wrong board.** Classic MESO is equivalent *to the offerer*; a mediator app should make variants equivalent *to the recipient* (so the choice is genuinely indifferent in value and purely reveals shape preference) — offering three deals where one is clearly better on the recipient's board just collapses the choice and teaches nothing. **[LOW — my synthesis; not directly studied]**

---

## 4. What matters most (ranked)

1. **Dual-board individual rationality (log-rolling on per-user values).** The one non-negotiable. It is simultaneously the acceptance predictor, the theory-backed source of joint gain, and FTF's structural moat (M–S impossibility doesn't bind a third party holding both boards). **[HIGH]**
2. **Roster-context marginal valuation + non-additive package math.** Without fit/scarcity/consolidation adjustments, board math suggests trades that are numerically positive and practically absurd. This is where most calculator complaints concentrate (roster cloggers). **[HIGH]**
3. **Offer framing and two-sided explanation.** The literature's sharpest warning: mathematically integrative offers are *not perceived* as such. Acceptance rate — the metric FTF actually lives on — moves with framing, choice, and explanation as much as with value. **[HIGH]**
4. **MESO presentation (2–3 shaped variants).** Cheap to build once generation exists; documented lift in acceptance and satisfaction; doubles as an elicitation channel that makes the boards better. **[HIGH]**
5. **Fairness band + junk-stuffing defenses.** Protects league-level legitimacy (vetoes, "this app is rigged" chatter) even when both parties would accept. **[MED]**
6. **Suggestion diversity + feedback loop.** What separates the one production-grade system on record (IBM/ESPN) from demos: uniqueness constraints and season-over-season error analysis. **[MED]**
7. **Search architecture (staged, centerpiece-anchored).** Matters for latency and coverage, but at FTF's scale many architectures work; it's an enabler, not a differentiator. **[MED]**

---

## 5. What doesn't matter (even though it seems like it should)

- **Exact Pareto-optimality and optimal surplus splits.** ANAC agents win with *estimated* frontiers; NSS methods walk toward the frontier stepwise; behaviorally, recipients can't tell Pareto-optimal from near-optimal — they respond to own-gain, framing, and choice. Near-frontier with a roughly even split is enough. **[HIGH]**
- **Mechanism-design incentive compatibility.** Truthful-elicitation machinery (VCG, etc.) solves a problem FTF doesn't have: boards come from matchup votes made for self-interested ranking accuracy, not from strategic trade declarations. (Watch for board-gaming if managers learn votes move trade suggestions — see §6.) **[MED]**
- **Deep-learning bundle generation.** BYOB/BGGN/BundleNAT exist for million-item catalogs with no enumerable space. FTF's constrained space makes enumeration + scoring strictly better (faster, explainable, debuggable). Borrow the taxonomy and the preference-vs-coherence framing, skip the models. **[HIGH]**
- **Global market-value precision.** Chasing KTC-grade consensus accuracy feels central but isn't: consensus values only gate the *defensibility band*, and a ±10–15% band tolerates a lot of noise. The per-user boards are where precision pays. **[MED]**
- **Anchoring micro-tactics (precise numbers, extreme-first-offer games).** These effects are real in adversarial human-vs-human bargaining, but a neutral app suggesting trades isn't making an adversarial first offer; over-anchored (extreme) suggestions would just burn trust. The transferable part of anchoring research is only: *your suggestion sets the reference point, so set it at the joint-gain package*. **[MED]**
- **Bigger packages to "find more value."** Package size beyond ~3 per side adds combinatorial cost, triggers consolidation discounts, raises fixed-pie suspicion ("too clever"), and in the KTC data invites junk-stuffing. Every practical system caps small. The 1-for-1 to 3-for-3 + picks scope is already right. **[MED]**

---

## 6. Transfer notes for FTF

**Proposed generation pipeline (maps directly onto existing FTF assets):**

1. **Partner + centerpiece selection** (round-1 territory): from A's *want board* and B's roster, pick centerpiece X where divergence `v_A(X) − v_B(X)` is large and positive, and B's timeline/depth makes X expendable (IBM's cosine-dissimilarity pairing = complementary strengths/weaknesses).
2. **Divergence-driven return search:** candidate return assets from A's roster ranked by `v_B(y) − v_A(y)` (things B likes more than A does — A's *accept board* is the pre-filter). Build returns of 1–3 assets + picks around that ranking. Centerpiece anchoring collapses the search to ~C(25,3) ≈ 2,300 returns per centerpiece — trivial in Python/SQLite.
3. **Hard gates, in order:** roster feasibility (both sides) → dual-board ε-gain (both sides, own boards, with consolidation discount applied to the multi-asset side and a roster-fit adjustment on marginal values) → consensus fairness band (±X% on league/global values; widen ε or X only by explicit config).
4. **Rank survivors by joint gain; tiebreak by symmetry of the split.** Log per-suggestion: joint gain, split ratio, IR margins — these are the health metrics (CGD's IR-rate / security-gap / symmetry-gap, renamed).
5. **MESO layer:** for the top deal, emit up to 3 return-package variants within ±small% on the *recipient's* board but different in shape (youth / picks / consolidation). Record which variant is accepted, countered, or declined.
6. **Explanation layer:** two renderings per trade — "your side" (own-board gain, roster fit) and "why they say yes" (their timeline, their positional need) — never a single won/lost score. This is Chalkline-friendly: two columns, per-side gain chips, no winner banner.
7. **Feedback loop:** accepted/declined/countered + MESO choice → adjust want/accept boards and the fit-model weights; run periodic error analysis on declines (IBM's FEAT-session pattern, lightweight).

**FTF-specific advantages to exploit [HIGH]:** (a) per-user boards from matchup votes are the exact private-valuation data M–S says bargainers hide — no published fantasy tool has both sides' honest boards; (b) KTC's vote mechanism (3-way keep/trade/cut) is structurally FTF's 3-player matchup, validating the elicitation approach at 26M+ votes of scale; (c) want/accept boards give the generator its pre-filters for free.

**FTF-specific risks [MED/LOW]:** cold-start boards (few votes → noisy `v_u`; fall back to consensus values blended with vote count as confidence weight); board-gaming once users learn votes drive suggestions (monitor vote patterns of heavy traders); two-sided trust (if manager B never opened the app, "B should accept this" is model fiction — label suggestions involving low-data managers accordingly).

---

## 7. Not researched / follow-up topics

- **Acceptance-probability modeling** as its own supervised problem (Dynasty Dealmaker ships one; no methodology published). What features predict human trade acceptance in fantasy specifically? Needs FTF's own accept/decline telemetry to build.
- **Multi-party (3+ team) trades** — kidney-exchange cycle/chain machinery (integer programming over bounded cycles) is the obvious template and was only skimmed here; out of scope for 2-party v1 but the graph formulation would slot in.
- **Counter-offer dynamics:** what to do after a decline — ANAC concession strategies were reviewed for generation, not for the re-offer loop; negotiation-dance literature on concession reciprocity untouched.
- **Timing/liquidity effects:** when to surface a suggestion (post-injury, post-breakout, near deadline) — round-1 marketplace-dynamics territory, not re-examined for offers specifically.
- **Draft-pick valuation curves under uncertainty** (pick value distributions vs. point estimates) — treated picks as ordinary assets here.
- **Veto/league-governance modeling:** how leagues actually veto and whether a fairness band calibrated to veto behavior beats a value-based band.
- **Empirical MESO sizing for low-stakes digital offers** — all MESO studies are human business negotiations; the 2–3 offer guidance is assumed transferable but unverified in-app. A/B test single vs. MESO presentation post-launch.
- **The full text of the bundle survey (2411.00341) constraint-handling sections** — abstract-level access only; if package-composition constraints get gnarly, read in full.

---

## 8. Sources

**Bundle recommendation & complementarity**
1. Sun et al., *A Survey on Bundle Recommendation: Methods, Applications, and Challenges* — https://arxiv.org/pdf/2411.00341
2. *Revisiting Bundle Recommendation for Intent-aware Product Bundling*, ACM TORS — https://dl.acm.org/doi/10.1145/3652865
3. *Text2Bundle: Towards Personalized Query-based Bundle Generation* — https://arxiv.org/pdf/2310.18004
4. *BRIDGE: Bundle Recommendation via Instruction-Driven Generation* — https://arxiv.org/pdf/2412.18092
5. *Non-autoregressive personalized bundle generation* (BundleNAT), Inf. Processing & Mgmt — https://www.sciencedirect.com/science/article/abs/pii/S0306457324001730
6. *Accurate bundle matching and generation via multitask learning* — https://pmc.ncbi.nlm.nih.gov/articles/PMC10019671/
7. Zhao & McAuley, *Improving recommendation accuracy using networks of substitutable and complementary products* — https://www.semanticscholar.org/paper/1f10615ca9072d6fa27ce606b7a5185e9194c25a
8. Amazon Science, *Improving complementary-product recommendations* — https://www.amazon.science/blog/improving-complementary-product-recommendations
9. *Complementary Recommendation in E-commerce: Definition, Approaches, and Future Directions* — https://arxiv.org/pdf/2403.16135

**Combinatorial exchange & bilateral trade theory**
10. Leyton-Brown, UBC lecture notes, *Combinatorial Auctions & Bidding Languages* — https://www.cs.ubc.ca/~kevinlb/teaching/cs532l%20-%202007-8/lectures/lect21.pdf
11. Brown CSCI 1951k lecture, *Combinatorial Auctions / spectrum* — https://cs.brown.edu/courses/cs1951k/lectures/2020/spectrum_auctions.pdf
12. Myerson & Satterthwaite via Saylor econ text — https://saylordotorg.github.io/text_introduction-to-economic-analysis/s19-02-myerson-satterthwaite-theorem.html
13. *Second-Best Bilateral Trade is 1/2 Efficient* — https://arxiv.org/abs/2606.03849
14. Peck (OSU) lecture notes on Myerson–Satterthwaite 1983 — https://www.asc.ohio-state.edu/peck.33/gametheory/gameL11.pdf

**Automated negotiation & negotiation support**
15. ANAC official site — https://anac.cs.brown.edu/
16. EmergentMind topic survey, *Automated Negotiating Agents Competition* — https://www.emergentmind.com/topics/automated-negotiating-agents-competition-anac
17. Bagga et al., *Learnable Strategies for Bilateral Agent Negotiation over Multiple Issues* — https://arxiv.org/abs/2009.08302
18. *Conditional Graph Diffusion for Negotiation Support* — https://arxiv.org/pdf/2606.02209
19. Ehtamo et al., *Identifying Pareto-optimal settlements for two-party resource allocation negotiations*, EJOR — https://www.sciencedirect.com/science/article/abs/pii/0377221795000887
20. *Interactive Multiple-Criteria Methods for Reaching Pareto Optimal Agreements in Negotiations* — https://www.researchgate.net/publication/226606545

**Negotiation science: MESO, anchoring, log-rolling**
21. Ames & Mason, *MESOs reduce the negotiator dilemma*, OBHDP — https://www.sciencedirect.com/science/article/pii/S074959781630557X
22. Wikipedia, *Multiple Equivalent Simultaneous Offers* — https://en.wikipedia.org/wiki/Multiple_Equivalent_Simultaneous_Offers
23. PON Harvard, *The Negotiator's Dilemma: How MESOs Help You Create and Claim Value* — https://www.pon.harvard.edu/daily/negotiation-skills-daily/managing-the-negotiators-dilemma-nb/
24. *Negotiating for More: The Multiple Equivalent Simultaneous Offer*, JACR — https://pubmed.ncbi.nlm.nih.gov/24042029/
25. Petrowsky et al., *The power and peril of first offers: conceptual, meta-analytic, and experimental synthesis*, OBHDP 2025 — https://www.sciencedirect.com/science/article/pii/S0749597825000603
26. *Toward a Process Model of First Offers and Anchoring in Negotiations*, NCMR — https://ncmr.lps.library.cmu.edu/article/574/galley/480/download/
27. PON Harvard, *For Effective Price Anchoring, Strive for Precision* — https://www.pon.harvard.edu/daily/dealmaking-daily/negotiation-research-can-use-effective-first-offer-strive-precision-nb
28. Moran & Ritov, *Initial perceptions in negotiations: evaluation and response to 'logrolling' offers*, J. Behavioral Decision Making — https://onlinelibrary.wiley.com/doi/abs/10.1002/bdm.405
29. De Dreu et al., *Unfixing the fixed pie: motivated information-processing approach to integrative negotiation* — https://www.academia.edu/61530879/

**Sports trade machines & fantasy tools**
30. Fanspo NBA Trade Machine & Cap Manager — https://fanspo.com/nba/trade-machine
31. Hoops Rumors, *Traded Player Exception glossary* (salary-matching rules) — https://www.hoopsrumors.com/2023/01/hoops-rumors-glossary-traded-player-exception-4.html
32. KeepTradeCut FAQ (crowdsourced methodology) — https://keeptradecut.com/frequently-asked-questions
33. Javelin Fantasy, *How the KTC Adjustment Works (in Detail)* — https://www.javelinfantasyfootball.com/2022/09/30/how-the-ktc-adjustment/
34. FantasyCalc trade database / methodology — https://www.fantasycalc.com/database
35. DLF Trade Finder — https://dynastyleaguefootball.com/dynasty-fantasy-football-trade-finder/
36. Dynasty Dealmaker — https://www.dynastydealmaker.com/
37. Baughman et al. (IBM/ESPN), *Large Scale Diverse Combinatorial Optimization: ESPN Fantasy Football Player Trades* — https://arxiv.org/pdf/2111.02859
38. *A Genetic Algorithm for Optimizing Fantasy Football Trades with Playoff Biasing* — https://arxiv.org/abs/2511.17535

**Asymmetric valuation / dynasty strategy**
39. DLF, *Dynasty Rebuilding Strategy: Trading, Part Two* — https://dynastyleaguefootball.com/2026/08/10/dynasty-rebuilding-strategy-trading-part-two/
40. Fantasy Football Foundry, *Dynasty Strategy — Trading as a Contender* — https://fantasyfootballfoundry.com/articles/dynasty-strategy-trading-as-a-contender
