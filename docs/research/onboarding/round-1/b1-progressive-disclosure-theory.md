# Progressive Disclosure Theory and the Research Behind It

**Round 1, Lens B1 — research brief**
**Date:** 2026-08-15
**Scope:** Progressive disclosure theory, cognitive load theory as applied to UI, feature-discoverability research, layered/leveled UI design, training-wheels interfaces, and Hick's law / choice-overload evidence. Deliberately excludes onboarding-flow benchmarking, competitor teardowns, and activation-metric strategy (other lenses).

---

## TL;DR

- **Progressive disclosure is a two-level idea, and the evidence for going past two levels is thin.** NN/G's own guidance is that designs with three or more disclosure levels "typically suffer usability problems" and should be re-chunked instead ([NN/G](https://www.nngroup.com/articles/progressive-disclosure/)). The practitioner rule of thumb — ~80% of tasks complete at Level 1, ~20% need one drawer opened — is Nielsen's heuristic, not a measured constant ([UX Tigers](https://www.uxtigers.com/post/progressive-disclosure)).
- **Progressive ≠ staged disclosure, and confusing them is the most common design error.** Progressive is *hierarchical and optional* (most users never open the advanced layer); staged is *linear and mandatory* (wizards — users must pass through). Staged disclosure breaks badly when steps are interdependent and users need to alternate between them ([NN/G](https://www.nngroup.com/articles/progressive-disclosure/)).
- **The strongest empirical result in this literature is 42 years old and still holds: training wheels.** Carroll & Carrithers (1984) blocked advanced/error-producing functions in a commercial word processor; novices learned faster, produced better work, scored better on a comprehension post-test, and made *fewer errors even in the unblocked areas*. The control group spent roughly a quarter of its time recovering from error states the training-wheels version simply blocked ([ACM CACM](https://dl.acm.org/doi/10.1145/358198.358218); [Sage](https://journals.sagepub.com/doi/10.1177/001872088402600402)).
- **Users will not read your explanation — this is a documented behavior pattern, not a failure of your copy.** The "paradox of the active user" (Carroll & Rosson, IBM, early 1980s) shows *production bias* (doing beats learning-about-doing) and *assimilation bias* (new systems get interpreted through old mental models). Design for the irrational-but-real user ([NN/G](https://www.nngroup.com/articles/paradox-of-the-active-user/)).
- **Users satisfice: they keep a known-inefficient path forever rather than pay a small one-time learning cost.** The keyboard-shortcut literature is the cleanest demonstration — shortcuts are roughly twice as fast, yet even experienced users largely stay on toolbars and menus; adoption tracks *social exposure* more than efficiency ([Radboud repository](https://repository.ubn.ru.nl/bitstream/handle/2066/116659/1/116659.pdf); [ResearchGate](https://www.researchgate.net/publication/252646472_Keyboard_Shortcut_Usage_The_Roles_of_Social_Factors_and_Computer_Experience)).
- **Adaptive (system-driven) interfaces lose; adaptable (user-driven) interfaces win on preference, static wins on speed.** Findlater & McGrenere's CHI 2004 comparison (N=27) found static menus fastest, adaptive slowest, and adaptable *most preferred* despite not being fastest — a durable, heavily cited verdict against auto-reorganizing UI ([ACM](https://dl.acm.org/doi/10.1145/985692.985704)).
- **Hick's law and choice overload are both weaker than their popular framing.** Hick's law does not apply to scanning an unordered list — that is linear visual search ([Wikipedia, Hick's law](https://en.wikipedia.org/wiki/Hick%27s_law)). Choice overload's meta-analytic mean effect is ≈ 0 ([Scheibehenne et al. 2010](https://www.researchgate.net/publication/255702128_Choice_Overload_Is_There_Anything_to_It)), reappearing only under specific moderators ([Chernev et al. 2015](https://chernev.com/wp-content/uploads/2017/02/ChoiceOverload_JCP_2015.pdf)) — moderators that a dynasty trade app plausibly satisfies.
- **What helps a novice can actively hurt an expert — the expertise reversal effect.** Guidance/scaffolding that reduces extraneous load for beginners becomes redundant processing for knowledgeable users and degrades their performance ([Springer, Instructional Science](https://link.springer.com/article/10.1007/s11251-009-9102-0)). This is the theoretical case for *retiring* onboarding scaffolds, not just deferring features.

---

## 1. What progressive disclosure actually is (and what it is not)

### 1.1 Definition and structure

Progressive disclosure is a strategy in which the interface "initially shows users only a few of the most important options" and offers "a larger set of specialized options upon request" in a secondary display ([NN/G](https://www.nngroup.com/articles/progressive-disclosure/)). The canonical example is a print dialog: copies and page range up front, scaling and duplex behind "Advanced."

NN/G frames the payoff explicitly against three of the five usability components: **learnability, efficiency, and error reduction**. Notably, NN/G asserts the opposite of the common objection — rather than hidden features producing an impoverished mental model, "people understand a system better when you help them prioritize features" ([NN/G](https://www.nngroup.com/articles/progressive-disclosure/)).

Two design preconditions are stated as required, not optional:

1. **Correct split.** Designers must correctly separate frequently-needed from rarely-used features, informed by task analysis *and* usage statistics — with the caveat that raw page/feature hit counts can reflect accidental navigation rather than genuine need, so observational testing is needed to validate the split.
2. **Legible progression mechanics.** The control that opens the second level must have strong information scent — the label must set accurate expectations about what is behind it.

### 1.2 The two-level ceiling

NN/G explicitly cautions that although progressive disclosure generalizes to multiple levels in theory, designs exceeding two levels "typically suffer usability problems"; if complexity seems to demand three or more, the recommended response is to simplify or re-chunk the feature set using card sorting and user testing ([NN/G](https://www.nngroup.com/articles/progressive-disclosure/)).

Nielsen's 2026 restatement sharpens this into a rule: stop at two levels, because "each additional level multiplies clicks and halves discoverability," with a target split of roughly 80% of tasks completable at Level 1 ([UX Tigers](https://www.uxtigers.com/post/progressive-disclosure)). Treat the 80/20 figure as a design heuristic — no underlying dataset is cited for it.

### 1.3 Progressive vs. staged vs. responsive enabling

| Variant | Secondary content | Must users reach it? | Navigation | Failure mode |
|---|---|---|---|---|
| **Progressive** | Advanced/rare features | Usually not | Hierarchical, returnable | Advanced layer becomes undiscoverable |
| **Staged** | Sequential steps of one task | Yes — task stalls otherwise | Linear | Breaks when steps are interdependent |
| **Responsive enabling** | Contextually irrelevant controls | n/a — shown but disabled | In place | Users can't tell *why* something is disabled |

Sources: [NN/G](https://www.nngroup.com/articles/progressive-disclosure/); [IxDF](https://ixdf.org/literature/topics/progressive-disclosure).

The distinction matters operationally. Wizards (staged) are the right tool when a task decomposes into steps with **little interaction between them**; they are the wrong tool when users must alternate between steps to make a decision — the classic case being comparison shopping, where users need several parameters on screen simultaneously. NN/G's cited case study — a test of 46 web applications including a hotel reservation flow — found a single-screen design excelled at exploratory comparison but failed by demanding payment details prematurely, concluding a **two-screen compromise would beat both extremes** ([NN/G](https://www.nngroup.com/articles/progressive-disclosure/)).

### 1.4 Attribution and history — genuinely contested

Attribution is muddier than most secondary sources admit. Wikipedia traces the seminal idea to **Kristina Hooper Woolsey (1985)**, an Apple Human Interface Group founding member, arguing that design must consider how one "selectively informs a user about a particular system, providing well-chosen bits and pieces" ([Wikipedia](https://en.wikipedia.org/wiki/Progressive_disclosure)) — that article is a stub and cites no Carroll or Nielsen origin. Secondary sources variously credit **Carroll & Rosson (early 1980s, IBM)** for the research program and **Nielsen (1995)** for naming the pattern; I found no primary document establishing either as the coinage. IxDF's topic page gives **no attribution at all** ([IxDF](https://ixdf.org/literature/topics/progressive-disclosure)).

**Verdict:** treat "who invented progressive disclosure" as unresolved. The *evidence* behind it (training wheels, cognitive load, minimalist instruction) is well-sourced; the origin story is folklore-grade.

---

## 2. Cognitive load theory applied to UI

### 2.1 The three loads

Cognitive load theory (Sweller, 1980s; refined with Paas and van Merriënboer) distinguishes three additive components:

- **Intrinsic load** — inherent complexity of the material, driven by *element interactivity*: how many elements must be held in working memory simultaneously because they can only be understood in relation to each other. Intrinsic load is relative to the learner's prior knowledge.
- **Extraneous load** — load imposed by presentation and design rather than the material itself. This is the portion design can remove.
- **Germane load** — effort actually devoted to building and automating schemas in long-term memory.

([Sweller/CLT overview, U. Kentucky](https://www.uky.edu/~gmswan3/544/Cognitive_Load_&_ID.pdf); [ScienceDirect, CLT and individual differences](https://www.sciencedirect.com/science/article/pii/S1041608024000165))

The design implication is precise and often mis-stated: progressive disclosure does **not** reduce intrinsic load — the domain is as complex as it is. It reduces *extraneous* load by not requiring the user to hold irrelevant options in working memory while doing something else.

### 2.2 Worked examples and the expertise reversal effect

The worked-example effect — showing a fully solved instance rather than asking a novice to problem-solve — is one of CLT's best-replicated findings for low-knowledge learners. The critical corollary for a feature-dense app is the **expertise reversal effect**: instructional support that reduces extraneous load for novices becomes *redundant* for knowledgeable users, imposing its own processing cost and degrading performance. Kalyuga's work showed the superiority of worked examples over problem-solving practice **disappearing** as trainees gained experience; the effect has been replicated across a wide range of materials, usually as a partial rather than full reversal ([Springer, Instructional Science special issue](https://link.springer.com/article/10.1007/s11251-009-9102-0); [Wikipedia](https://en.wikipedia.org/wiki/Expertise_reversal_effect)).

**This is the strongest theoretical argument in this brief for *time-limited* scaffolding.** A tooltip, coach mark, worked example, or simplified default that is correct in session 1 is a tax in session 20. Progressive disclosure that only ever adds and never retires its own training apparatus is half-implemented.

### 2.3 Measurement caveat

Cognitive-load measurement is contested. A 2024 critical analysis notes substantial disagreement about whether subjective rating scales, dual-task performance, and physiological measures converge on the same construct ([arXiv 2402.11820](https://arxiv.org/pdf/2402.11820)). Be skeptical of any product claim that a redesign "reduced cognitive load by X%" — in most product settings the measured quantity is a NASA-TLX-style self-report, which is a perception, not a load measurement.

Relatedly, Miller's "magical number seven" is routinely misapplied in UI to cap menu lengths at 7±2. Miller's finding concerned recall of unrelated items held in memory, not visual selection from a persistently displayed list. I could not retrieve NN/G's dedicated article on this (404), so treat it as a well-known caveat rather than a citation-backed claim here.

---

## 3. How users actually find features

### 3.1 The paradox of the active user

Carroll & Rosson's studies at the IBM User Interface Institute in the early 1980s produced the field's most durable behavioral finding: **users never read manuals; they start using the software immediately**, motivated by the immediate task, unwilling to spend time up front getting established ([NN/G](https://www.nngroup.com/articles/paradox-of-the-active-user/); [Carroll & Rosson PDF, Virginia Tech](https://research.cs.vt.edu/ns/cs5724papers/4.mental.mental.carroll.paradox.pdf)).

Two mechanisms:

- **Production bias** — the psychological reward from completing a task exceeds the reward from acquiring capability. Completing a task inefficiently is immediately gratifying; learning offers only abstract future benefit.
- **Assimilation bias** — users interpret a new system through prior knowledge, which produces confident, wrong mental models when the new system differs from the old one.

NN/G's framing is that this is a paradox only from a rational-actor standpoint: users *would* save time by investing up front, but they don't, and "we must design for the way users actually behave."

### 3.2 Satisficing: the known-inefficient path is sticky

The keyboard-shortcut literature is the cleanest natural experiment. Shortcuts typically take about half the time of menu or toolbar selection, and yet most users — including experienced ones — persist with the slower method. The explanation the literature converges on is **satisficing** (Simon): people accomplish tasks at a sufficient level rather than an optimal one, and once a working path is found, the search stops ([Radboud repository PDF](https://repository.ubn.ru.nl/bitstream/handle/2066/116659/1/116659.pdf)).

Crucially, what *does* predict shortcut adoption is not efficiency but **social and experiential factors**: working alongside other shortcut users, and hours of computer use per week ([ResearchGate, keyboard shortcut usage and social factors](https://www.researchgate.net/publication/252646472_Keyboard_Shortcut_Usage_The_Roles_of_Social_Factors_and_Computer_Experience)). Interface guidelines that assume users will graduate to accelerators on their own are contradicted by this evidence — NN/G states plainly that when left alone, "users do not transition to true expert usage" ([NN/G, complex application design](https://www.nngroup.com/articles/complex-application-design/)).

### 3.3 Social learning is a primary discovery channel

Twidale's "over-the-shoulder learning" (CSCW, 2005) documents informal, spontaneous help-giving between colleagues as a dominant mode of learning application features — brief, embedded in the real work context, and effective precisely because it is triggered by an actual blocked task rather than scheduled as training ([Springer CSCW](https://link.springer.com/content/pdf/10.1007/s10606-005-9007-7.pdf); [Illinois Experts](https://experts.illinois.edu/en/publications/over-the-shoulder-learning-supporting-brief-informal-learning/)).

Recent work qualifies this. A CSCW 2025 interview study (N=31 professional spreadsheet users) found expertise *fails* to spread for social reasons: experts' strategies are too personalized to generalize, timing of unsolicited advice is socially fraught, users hold self-doubt about their own competence, and the domain is culturally undervalued. The authors attribute much of this to "feature-rich software designed primarily with initial learnability in mind" — i.e., optimizing for first-session simplicity can starve the long-term learning path ([arXiv 2506.09216](https://arxiv.org/abs/2506.09216)).

A companion survey (N=100 admin/finance professionals) found **self-efficacy** and expected reputational gain predict willingness to share knowledge, while documentation effort suppresses it — and identified a "self-efficacy paradox": users report high confidence for their own job-specific tasks but low general confidence in the tool ([arXiv 2408.08068](https://arxiv.org/abs/2408.08068)). Self-efficacy is therefore a *designable* variable, and social proof is the lever.

### 3.4 Machine-assisted discovery

Three HCI systems represent the main research answers to "how do we surface features users don't know to look for": **CommunityCommands** (UIST 2009, [DOI](https://dl.acm.org/doi/10.1145/1622176.1622214)) applies collaborative filtering to command logs — an Amazon-style recommender for functionality rather than products; **ToolClips** (CHI 2010, [DOI](https://dl.acm.org/doi/10.1145/1753326.1753552)) attaches short contextual videos to tools, targeting *functionality understanding* rather than location; **Ambient Help** (CHI 2011, [DOI](https://dl.acm.org/doi/10.1145/1978942.1979349)) surfaces potentially relevant help in the periphery without an explicit request.

I could not retrieve abstracts or effect sizes for these behind ACM's paywall — cite them as *design precedents with peer-reviewed evaluations*, not as quantified evidence.

### 3.5 The Office / Ribbon case: the best-documented industrial instance

Microsoft's Office 2007 Ribbon redesign is the most-cited industrial example of feature-discoverability failure at scale. From Jensen Harris's UX Week 2008 talk, as recorded in contemporaneous notes:

- Word toolbars grew from **2 (Word 1.0, 1989) → 31 (Word 2003)**; menu items from **~50 → ~300**.
- Telemetry scale: **~150 million command-button clicks tracked per month in Word**, over **3 billion anonymous data sessions**, **~6,000 individual data points**.
- The core problem statement: "They added new features, but hardly anyone found them," with menus and toolbars originally "designed for less full-featured programs" and stretched past their limits.

([UX Week 2008 notes](https://www.jurecuhalev.com/blog/jensen-harris-the-story-of-the-ribbon-office-2007-uxweek08-notes/); Harris's own retrospective at [jensenharris.com](https://jensenharris.com/home/ribbon) confirms the design goals but contains no statistics.)

**The famous claim needs a warning label.** The widely repeated finding that "most requested Office features already existed in the product" (often paired with "90% of users use less than 10% of features") appears in search summaries and countless blog posts, but I could not locate a primary Microsoft document or paper stating it with a methodology. Harris's own writing does not contain it. **Use it as an illustrative anecdote, never as a statistic.**

---

## 4. Layered and leveled UI design

### 4.1 Training wheels (Carroll, IBM)

Carroll & Carrithers (1984) built a "Training Wheels Displaywriter" — a commercial word processor in which advanced and error-prone functions were *blocked*, producing a feedback message without changing system state, rather than removed or hidden. Results across the training-wheels studies:

- Beginners learned the basic letter-typing task **faster**.
- They **scored better on a comprehension post-test** afterward.
- They produced **better work**.
- They spent less time on errors **including errors the design did not block** — a *generalized* facilitation of learning, not merely avoidance of the blocked paths.
- The control group spent **roughly a quarter of its time** recovering from error states the training version blocked.

([ACM CACM, "Training wheels in a user interface"](https://dl.acm.org/doi/10.1145/358198.358218); [Sage, "Blocking Learner Error States in a Training-Wheels System"](https://journals.sagepub.com/doi/10.1177/001872088402600402); [SIGCHI/GI, "Learning a word processing system with training wheels and guided exploration"](https://dl.acm.org/doi/10.1145/29933.275625))

Two design details are frequently lost in the retelling and matter a great deal:

1. **The advanced functions were still visible and reachable — they were blocked, with an explanatory message.** This is not the same as hiding them. It preserves the user's mental model of the system's full extent while preventing the error.
2. **The benefit was learning-generalization, not just error avoidance.** Reduced error recovery freed attention for schema-building, which is exactly the CLT prediction (extraneous load down, germane load up).

Nielsen's recent restatement summarizes training wheels as "reduced errors by roughly 25%" ([UX Tigers](https://www.uxtigers.com/post/progressive-disclosure)); the underlying figure is the ~quarter-of-time-in-error-recovery result, so treat the 25% as a paraphrase rather than a reported effect size.

### 4.2 Multi-layer interfaces (Shneiderman)

Shneiderman's "Promoting Universal Usability with Multi-Layer Interface Design" (ACM CUU 2003) proposes that first-time and novice users begin at **layer 1** with a deliberately limited feature set and either stay there or move up when they have a need and the time to learn. He illustrates with a word processor designed in **8 layers** and an interactive map in **3 layers** ([ACM](https://dl.acm.org/doi/abs/10.1145/957205.957206); [Semantic Scholar](https://www.semanticscholar.org/paper/3d6e713d5cf65e66657b5af8a509a3df2f72cde3)).

Note the tension with NN/G's two-level ceiling: Shneiderman's layers are *interface versions* a user opts into and inhabits over time, whereas NN/G's levels are *nested screens* traversed inside a single task. Both can hold. The evidence base is weaker than for training wheels — the CUU paper presents arguments plus example systems, not a controlled experiment. (I could not extract the paper's text; the [UMD-hosted PDF](https://www.cs.umd.edu/users/ben/ACM-CUU2003.pdf) did not convert.)

### 4.3 Adaptive vs. adaptable — the research verdict

This is the clearest "don't do the clever thing" finding in the brief.

**Findlater & McGrenere, CHI 2004, "A comparison of static, adaptive, and adaptable menus"** (N=27, UBC; 332 citations as of retrieval):

- **Static** split menu — four most frequently selected items pinned at top. *Fastest.*
- **Adaptive** split menu — two most frequent + two most recent promoted automatically. *Slowest* (though by a small margin).
- **Adaptable** split menu — user moves items to the top/bottom sections themselves. *Middle on speed, most preferred.*

Users preferred the adaptable menu to both the static and adaptive versions, despite it not being the fastest ([ACM](https://dl.acm.org/doi/10.1145/985692.985704); citation metadata via [Semantic Scholar](https://api.semanticscholar.org/graph/v1/paper/DOI:10.1145/985692.985704)).

The broader literature adds a caveat: because adaptive-menu results depend heavily on the specific adaptation algorithm, prediction accuracy, and task distribution, "no overall conclusion valid for all adaptive menus can be inferred" ([Springer, Usability of Adaptable and Adaptive Menus](https://link.springer.com/chapter/10.1007/978-3-540-73287-7_49)). A 2025 study revisiting adaptive UIs on performance and preferences continues the line ([ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0164121225002675) — abstract not retrievable, paywalled).

**Practical reading:** system-driven rearrangement costs users their spatial memory and gives back less than it takes; user-driven customization buys satisfaction and perceived control at little performance cost. Predictability beats optimality.

### 4.4 Modern scaffolding evidence

**ScaffoldUI** (Liu & Sra, 2025) is the most recent controlled work directly on progressive feature disclosure in genuinely complex professional software. The method presents only task-relevant tools, **progressively discloses tool complexity**, and organizes tools by domain concept rather than by implementation grouping. Implemented in Blender and evaluated with **N=32 beginners and N=8 experts**, it "significantly reduced perceived task load caused by interface complexity," supported task performance through structured guidance, and improved learning by connecting concepts to tools within the taskflow context ([arXiv 2505.12101](https://arxiv.org/abs/2505.12101)).

The organizing-by-domain-concept element is worth flagging separately: it suggests the win comes not only from *fewer* controls but from controls grouped by the user's conceptual model of the task.

---

## 5. Hick's law and choice overload — what the evidence supports

### 5.1 Hick's law is narrower than its popular use

Hick's law (T = b · log₂(n+1)) was derived from experiments with **10 lamps arranged in a circle**, each paired with a Morse key, with a pre-punched tape triggering a random lamp every 5 seconds — i.e., a pre-learned stimulus-response mapping with equiprobable alternatives ([Wikipedia](https://en.wikipedia.org/wiki/Hick%27s_law)).

The key limitation for UI: **finding a named command in a randomly ordered list requires scanning each item — linear time — so Hick's law does not apply.** It applies only when the set is ordered such that the user can use a subdividing strategy (e.g., alphabetical), which yields logarithmic time. Other documented exceptions: verbal responses to highly familiar stimuli show little relationship between RT and set size, and saccade responses can show *decreasing* time with more elements — the opposite of the prediction.

Landauer & Nachbar (CHI 1985) is the usual reference for applying Hick's and Fitts's laws jointly to menu breadth-vs-depth, and their result is the origin of the "broad, shallow menus beat deep, narrow ones" guidance.

**Reading:** "reduce the number of options because Hick's law" is not supported as stated. "Group and order options so users can subdivide the search space" is.

### 5.2 Choice overload: mostly a moderator story

- **Iyengar & Lepper (2000), the jam study:** the 24-jam display attracted more foot traffic (60% vs 40%) but ~3% purchase conversion vs ~30% for the 6-jam display — roughly a 10× conversion difference ([summary](https://atticusli.com/replication-crisis/choice-overload-jam-study/)).
- **Scheibehenne, Greifeneder & Todd (2010) meta-analysis:** ~50 studies, ~5,000 participants; **mean effect of assortment size ≈ d = 0**, with high heterogeneity and evidence of publication bias. Their own replication of the jam paradigm found no significant choice-overload effect ([ResearchGate](https://www.researchgate.net/publication/255702128_Choice_Overload_Is_There_Anything_to_It)).
- **Chernev, Böckenholt & Goodman (2015) meta-analysis:** reframes the question from *whether* to *when*, identifying four moderators — **choice-set complexity, decision-task difficulty, preference uncertainty, and decision goal** (effort-minimization/regret-avoidance). With all four high, reported effects reach roughly **d ≈ 0.5–0.6**; with moderators absent, the effect vanishes or reverses ([Chernev PDF](https://chernev.com/wp-content/uploads/2017/02/ChoiceOverload_JCP_2015.pdf); [summary](https://atticusli.com/replication-crisis/choice-overload-jam-study/)).
- **Dean, Ravindran & Stoye (2022, rev. 2026):** argue existing tests are underpowered and, with better-specified random-utility tests, find "strong evidence of choice overload that would likely be missed using current approaches" ([arXiv 2212.03931](https://arxiv.org/abs/2212.03931)).

**Reading:** don't cite "the jam study" as settled. Do note that the Chernev moderator profile — many multi-attribute options that are hard to compare, an evaluative task, and users uncertain of their own preferences — describes a dynasty trade list rather precisely.

---

## 6. Onboarding-specific evidence (bounded to the disclosure question)

NN/G's analysis of mobile onboarding decomposes it into **feature promotion, customization, and instructions**, and reaches an unusually blunt conclusion: **skip onboarding whenever possible**, because it adds interaction cost and memory strain with uncertain performance benefit; invest instead in making the UI itself more usable. Onboarding is justified mainly when the app requires account setup, is meaningfully personalized, or introduces genuinely unfamiliar interactions. NN/G specifically reports research in which tutorials did not improve task performance ([NN/G, mobile-app onboarding](https://www.nngroup.com/articles/mobile-app-onboarding/)).

On overlays and coach marks specifically, NN/G's observed failure modes are ([NN/G](https://www.nngroup.com/articles/mobile-instructional-overlay/)):

- **Rapid dismissal** without reading, worse on mobile where attention is fragmented.
- **Confusion with real UI** — in a Wimbledon app study, users tried to interact with tutorial annotations.
- **Memory decay** — sequential instructions exceed short-term memory, which "fades in about 20 seconds."
- **Chains of tips** make the app appear "overly complicated and daunting" and accelerate dismissal.

Overlays succeed when they target **a single unfamiliar interaction**, appear **one at a time at the moment of relevance**, pair a visual with ultra-short text, and are visually distinct from the real UI.

For complex applications specifically, NN/G recommends **in-context learning cues** over tutorials, tooltips that suggest faster methods as users hover, and learn-by-doing supported by making experimentation safe — "without that experimentation resulting in loss of work or irreparable damages" ([NN/G](https://www.nngroup.com/articles/complex-application-design/)). That last clause is the modern restatement of training wheels: make errors cheap rather than making features scarce.

Krystal Higgins adds a measurement critique worth carrying into any FTF experiment design: teams measure onboarding "myopically, like a feature in isolation," using slideshow clickthrough and wizard completion time, which say nothing about comprehension or subsequent feature use. She argues for longitudinal windows (Day 0, 1–7, 7–14, 14–30, 30–90) and includes **new-feature adoption latency** — how soon after a feature ships an existing user starts using it — as a first-class metric ([kryshiggins.com](https://www.kryshiggins.com/evaluating-your-new-user-experience/)).

---

## Evidence quality notes

**Strong (peer-reviewed, replicated, or large-scale):**
- Training wheels (Carroll & Carrithers 1984 and follow-ups) — controlled studies, converging results across multiple papers, still cited 40+ years on. Caveat: 1980s command-line-era word processing; external validity to touch apps is an inference, not a finding.
- Expertise reversal effect — replicated across many materials and domains; the most transferable CLT result for this problem.
- Findlater & McGrenere 2004 — a single N=27 lab study, but heavily replicated in spirit and 332 citations; the static-vs-adaptive-vs-adaptable ordering is one of the field's more stable results.
- Paradox of the active user — behavioral pattern observed across many studies since the 1980s; qualitative rather than effect-size evidence.
- Choice-overload meta-analyses — two large, methodologically serious meta-analyses that *disagree in framing* but are reconcilable via moderators.

**Moderate:**
- ScaffoldUI (2025) — recent, well-designed, but N=32 beginners / N=8 experts in one application (Blender), no replication.
- Satisficing/keyboard-shortcut literature — consistent across studies but largely correlational and survey-based on adoption predictors.
- Shneiderman multi-layer (2003) — a well-argued position paper with worked examples, not an experiment.
- Twidale over-the-shoulder learning — qualitative/observational; workplace context may not transfer to a consumer sports app used solo.

**Weak / opinion / needs a warning label:**
- **NN/G articles generally.** Authoritative practitioner guidance grounded in the firm's own usability testing, but the specific studies, sample sizes, and statistics are usually not published. Treat as expert opinion informed by data, not as citable evidence.
- **The 80/20 progressive-disclosure split and the "two levels max" rule.** Heuristics from Nielsen; no dataset offered.
- **"Most requested Office features already existed" / "90% of users use 10% of features."** Widely repeated, primary source not found. The verifiable Office material is the telemetry-scale and toolbar-growth data from Harris's talk.
- **Progressive disclosure's attribution/origin story.** Sources conflict (Woolsey 1985 vs. Carroll & Rosson early 1980s vs. Nielsen 1995).
- **Any "reduced cognitive load by X%" product claim.** Load measurement methodology is itself contested ([arXiv 2402.11820](https://arxiv.org/pdf/2402.11820)).

**Retrieval limitations for this brief:** ACM DL, ScienceDirect, Springer, Sage, and ResearchGate PDFs returned 403 or paywall redirects; several PDFs did not convert to text. Where that happened I cite metadata (title/authors/year/DOI) plus a secondary description and say so. The session's web-search budget was exhausted mid-research, so later gaps were filled by direct URL fetches rather than fresh searches — the "80/20 origin" and "Office feature-request" claims are the two I would most want another pass on.

---

## Implications for FTF — hypotheses only

These are hypotheses generated from the literature above. None are validated against FTF data, and each should be treated as a testable proposition, not a recommendation.

1. **The two-level ceiling probably indicts any FTF surface that requires three taps of "advanced."** *Hypothesis:* if any of the trade finder's filters, the want/accept board configuration, or the manual calculator's settings sit at disclosure depth ≥3, those features have measurably lower discovery rates than depth-1/2 features. Testable directly against existing analytics without shipping anything.

2. **Elo matchup voting is FTF's natural training-wheels layer.** *Hypothesis:* a 3-player vote is a low-element-interactivity task (one comparison, three items, no wrong answer, no destructive outcome) — exactly the "safe experimentation" NN/G prescribes for complex apps. Routing first-session users to voting before the trade finder should improve tier/value comprehension in session 2+ and lower abandon rates in the finder. The competing hypothesis — that voting delays time-to-value and hurts D1 — is not resolved by the literature; it is an A/B question.

3. **Send-trade is a staged-disclosure task; the trade finder is a progressive-disclosure surface — mixing the models will hurt.** *Hypothesis:* send-trade decomposes into weakly interdependent steps (pick trade → pick platform → confirm) and suits a wizard; trade *exploration* requires simultaneous comparison and degrades if wizardized, matching NN/G's hotel-reservation finding that premature commitment steps break exploratory comparison.

4. **Chernev's four moderators describe a dynasty trade list almost exactly, so choice overload is likelier here than the meta-analytic mean suggests.** *Hypothesis:* suggestions are multi-attribute and hard to compare, require active evaluation, and are consumed by users uncertain of their own roster direction. Predicted effect: capping the initially rendered suggestion set and expanding on request beats rendering the full list — with a *larger* effect for new users and a *smaller* one for users who have declared a contend/rebuild stance, since declaring one reduces preference uncertainty.

5. **Adaptive personalization of FTF navigation would likely lose; adaptable would likely win on satisfaction.** *Hypothesis:* auto-reordering tabs or algorithmically reshuffling the home screen costs spatial memory and slows users (Findlater & McGrenere), while user-controlled pinning/reordering is preferred at little speed cost. Corollary: express personalization as *defaults the user can change*, not silent rearrangement.

6. **Any first-session scaffolding should ship with an explicit retirement condition.** *Hypothesis:* per the expertise reversal effect, coach marks and explanatory subtitles that persist past competence measurably slow returning users. Test tying scaffold removal to a behavioral signal (N successful uses) rather than a session counter or a dismiss button.

7. **The notification inbox is FTF's best post-session-1 disclosure channel, and it should fire on task state, not schedule.** *Hypothesis:* introductions delivered at the moment of relevance (surface want/accept boards after a user rejects three suggestions in a row) beat a scheduled drip or feature tour — matching NN/G's "timely, one-at-a-time, single unfamiliar interaction" criterion and Twidale's blocked-task trigger.

8. **A solo consumer app has no over-the-shoulder colleague, so FTF must synthesize the social channel.** *Hypothesis:* since feature adoption tracks social exposure more than efficiency, social-proof framing ("league-mates who rebuild use the want board") beats capability-descriptive copy ("the want board lets you specify targets"). This also targets the self-efficacy variable from the end-user-programming work.

9. **The in-app feedback loop is a discoverability instrument, not just a bug channel.** *Hypothesis:* a nontrivial fraction of feature requests will describe capabilities that already ship. Tagging incoming feedback "exists / partially exists / new" yields a cheap per-feature measure of the discoverability gap, regardless of which onboarding design wins. (The underlying Office statistic is unverified folklore — this is a hypothesis, not an expectation.)

10. **Measure adoption latency, not tutorial completion.** *Hypothesis:* completion-based onboarding metrics cannot distinguish a good disclosure design from a bad one. The discriminating metrics are per-feature first-use latency by cohort, D7/D30 breadth-of-feature-use, and the share of users who ever reach each feature — over 30–90 days, not one session.

---

## Sources

**Progressive disclosure — core**
- NN/G, "Progressive Disclosure" — https://www.nngroup.com/articles/progressive-disclosure/
- NN/G video, "Progressive Disclosure" (Budiu, 2022) — https://www.nngroup.com/videos/progressive-disclosure/
- Jakob Nielsen, "Progressive Disclosure: From Training Wheels to Week-Long AI Agents" (UX Tigers) — https://www.uxtigers.com/post/progressive-disclosure
- IxDF, "Progressive Disclosure" topic — https://ixdf.org/literature/topics/progressive-disclosure
- Wikipedia, "Progressive disclosure" — https://en.wikipedia.org/wiki/Progressive_disclosure

**Training wheels / minimalist instruction**
- Carroll & Carrithers, "Training wheels in a user interface," CACM 1984 — https://dl.acm.org/doi/10.1145/358198.358218
- Carroll & Carrithers, "Blocking Learner Error States in a Training-Wheels System," Human Factors 1984 — https://journals.sagepub.com/doi/10.1177/001872088402600402
- Carroll & Mack et al., "Learning a word processing system with training wheels and guided exploration," CHI/GI 1987 — https://dl.acm.org/doi/10.1145/29933.275625
- IxDF glossary, "Training Wheels Interface" — https://ixdf.org/literature/book/the-glossary-of-human-computer-interaction/training-wheels-interface

**Paradox of the active user / satisficing**
- Carroll & Rosson, "Paradox of the Active User" (PDF) — https://research.cs.vt.edu/ns/cs5724papers/4.mental.mental.carroll.paradox.pdf
- NN/G, "The Paradox of the Active User" — https://www.nngroup.com/articles/paradox-of-the-active-user/
- "Satisficing and the Use of Keyboard Shortcuts: Being Good Enough Is Enough?" — https://repository.ubn.ru.nl/bitstream/handle/2066/116659/1/116659.pdf
- "Keyboard Shortcut Usage: The Roles of Social Factors and Computer Experience" — https://www.researchgate.net/publication/252646472_Keyboard_Shortcut_Usage_The_Roles_of_Social_Factors_and_Computer_Experience

**Cognitive load theory**
- Sweller, "Cognitive Load Theory and Instructional Design" (PDF, U. Kentucky) — https://www.uky.edu/~gmswan3/544/Cognitive_Load_&_ID.pdf
- "Cognitive load theory and individual differences," ScienceDirect — https://www.sciencedirect.com/science/article/pii/S1041608024000165
- "A critical analysis of cognitive load measurement methods," arXiv 2402.11820 — https://arxiv.org/pdf/2402.11820
- Kalyuga et al., expertise reversal special issue, *Instructional Science* — https://link.springer.com/article/10.1007/s11251-009-9102-0
- Wikipedia, "Expertise reversal effect" — https://en.wikipedia.org/wiki/Expertise_reversal_effect

**Layered / adaptive interfaces**
- Findlater & McGrenere, "A comparison of static, adaptive, and adaptable menus," CHI 2004 — https://dl.acm.org/doi/10.1145/985692.985704
- Findlater, MSc thesis, "Comparing Static, Adaptable, and Adaptive Menus" (UBC) — https://www.cs.ubc.ca/labs/imager/th/2004/Findlater2004/Findlater2004.pdf
- "Usability of Adaptable and Adaptive Menus," Springer — https://link.springer.com/chapter/10.1007/978-3-540-73287-7_49
- "User experience with adaptive user interfaces: Comparing performance and preferences" (2025), ScienceDirect — https://www.sciencedirect.com/science/article/pii/S0164121225002675
- Shneiderman, "Promoting Universal Usability with Multi-Layer Interface Design," ACM CUU 2003 — https://dl.acm.org/doi/abs/10.1145/957205.957206 (PDF: https://www.cs.umd.edu/users/ben/ACM-CUU2003.pdf)
- Liu & Sra, "Designing Scaffolded Interfaces for Enhanced Learning and Performance in Professional Software," arXiv 2505.12101 — https://arxiv.org/abs/2505.12101

**Feature discoverability**
- Twidale, "Over the Shoulder Learning: Supporting Brief Informal Learning," CSCW 2005 — https://link.springer.com/content/pdf/10.1007/s10606-005-9007-7.pdf
- Xia, Sarkar, Brumby & Cox, "'How do you even know that stuff?': Barriers to expertise sharing among spreadsheet users," CSCW 2025, arXiv 2506.09216 — https://arxiv.org/abs/2506.09216
- Xia et al., "The Paradox of Spreadsheet Self-Efficacy," arXiv 2408.08068 — https://arxiv.org/abs/2408.08068
- Matejka, Li, Grossman & Fitzmaurice, "CommunityCommands," UIST 2009 — https://dl.acm.org/doi/10.1145/1622176.1622214
- Grossman & Fitzmaurice, "ToolClips," CHI 2010 — https://dl.acm.org/doi/10.1145/1753326.1753552
- Matejka et al., "Ambient Help," CHI 2011 — https://dl.acm.org/doi/10.1145/1978942.1979349
- Grossman, Fitzmaurice & Attar, "A survey of software learnability," CHI 2009 — https://dl.acm.org/doi/10.1145/1518701.1518803
- Jensen Harris, "The Story of the Ribbon" (UX Week 2008 notes) — https://www.jurecuhalev.com/blog/jensen-harris-the-story-of-the-ribbon-office-2007-uxweek08-notes/
- Jensen Harris, "Designing the Ribbon" — https://jensenharris.com/home/ribbon

**Hick's law / choice overload**
- Wikipedia, "Hick's law" — https://en.wikipedia.org/wiki/Hick%27s_law
- NN/G video, "Hick's Law: Designing Long Menu Lists" — https://www.nngroup.com/videos/hicks-law-long-menus/
- Scheibehenne, Greifeneder & Todd, "Choice Overload: Is There Anything to It?" (2010) — https://www.researchgate.net/publication/255702128_Choice_Overload_Is_There_Anything_to_It
- Chernev, Böckenholt & Goodman, "Choice overload: A conceptual review and meta-analysis," JCP 2015 — https://chernev.com/wp-content/uploads/2017/02/ChoiceOverload_JCP_2015.pdf
- Dean, Ravindran & Stoye, "A Better Test of Choice Overload," arXiv 2212.03931 — https://arxiv.org/abs/2212.03931
- Atticus Li, "The Jam Study and Choice Overload" (evidence trail summary) — https://atticusli.com/replication-crisis/choice-overload-jam-study/

**Onboarding practice**
- NN/G, "Mobile-App Onboarding: An Analysis of Components and Techniques" — https://www.nngroup.com/articles/mobile-app-onboarding/
- NN/G, "Instructional Overlays and Coach Marks for Mobile Apps" — https://www.nngroup.com/articles/mobile-instructional-overlay/
- NN/G, "Complex Application Design" — https://www.nngroup.com/articles/complex-application-design/
- Krystal Higgins, "Evaluating onboarding experiences" — https://www.kryshiggins.com/evaluating-your-new-user-experience/
