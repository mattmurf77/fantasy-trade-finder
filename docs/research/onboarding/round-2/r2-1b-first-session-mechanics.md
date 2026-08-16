# R2-1B — First-Session Mechanics for a Complex App Built on Imported Data

> **Date:** 2026-08-15
> **Round:** 2 (builds on `round-1/a2-time-to-value-activation.md` and `round-1/a4-personalized-segmented-onboarding.md`)
> **Lens:** The mechanics of a high-converting complex-app first session when the app can read the user's real data. Six drill-downs: (1) "magic first screen" precedents, (2) the confirmation-tap hypothesis, (3) loading as theater / the labor illusion, (4) defaulted-unskippable setup steps, (5) synthetic sandbox vs. real-data first actions, (6) the first-recommendation quality bar.
> **Scope:** Research only. Every substantive claim carries a URL. Evidence is tiered at the end. Nothing here is a build recommendation.

---

## TL;DR

- **The "magic first screen" is a well-attested design belief with almost no published funnel data behind it.** What *is* published sits one step earlier, at the connection: Plaid reports "roughly 1 in 3 US consumers with a financial account" have connected via Link, plus customer lifts of **+21% account connections / +19% subsequent funding** (Stash) and **~11%** relative conversion from a mobile OAuth pop-up ([Plaid](https://plaid.com/blog/more-conversion-with-plaid-link/)). No fintech or wearable I could find publishes what the post-link screen did to retention. Unfalsified, not evidenced.
- **The hard time budget comes from Netflix:** a member "either finds something of interest [within the first 60 or 90 seconds] or the risk of the user abandoning our service increases substantially" ([Gomez-Uribe & Hunt, ACM TMIS 2016](https://dl.acm.org/doi/10.1145/2843948)).
- **The labor illusion is real and peer-reviewed, but its parameters are not what the internet says.** Buell & Norton, five experiments: people can prefer sites with **longer waits** to instant identical results, mediated by perceived effort and reciprocity ([record](https://ideas.repec.org/a/inm/ormnsc/v57y2011i9p1564-1579.html)). I could **not** verify durations or reversal points — an automated PDF extraction produced clean-looking numbers I am explicitly not citing. The usable ceiling is Nielsen's **10-second** attention limit ([NN/g](https://www.nngroup.com/articles/response-times-3-important-limits/)), and progress-display *shape* measurably changes perceived duration ([Harrison et al., UIST 2007](https://chrisharrison.net/projects/progressbars/ProgBarHarrison.pdf)).
- **Unskippable works when the step does work *for* the user; it backfires when the step asks something *of* the user.** Superhuman's full-screen, defaulted, unskippable setup went **30% → 98%+ completion** and **45% → ~80% feature opt-in** ([First Round](https://review.firstround.com/superhuman-onboarding-playbook/)). Vevo went the other way: adding a skip to its tutorial raised logins **~10%** and signups **~6%** ([secondary](https://messagegears.com/resources/blog/mobile-app-onboarding-creating-engaged-users-from-the-start/)). One rule fits both.
- **The confirmation tap has a strong legibility rationale and a strong agency counter-argument.** Pinterest's in-flow, reason-framed signal question added a step and still lifted flow completion **+11%** — including **~8%** on Facebook signups where the answer was already known ([Pinterest](https://medium.com/pinterest-engineering/exploring-effective-user-signals-585507d8e926)). Against it: with **fully pre-populated** suggestions, 18 expert clinicians "exhibit less agency: accepting improper mentions, and taking less initiative" ([Levy et al. 2021](https://arxiv.org/abs/2103.04725)). A pre-filled confirm manufactures assent as easily as it collects a correction.
- **Sandbox teaching has a 40-year-old academic anchor, not just Superhuman's +17%.** Carroll & Carrithers' training-wheels interface blocked error states; learners were faster and more successful, and the control group spent close to a quarter of its time recovering from errors the training interface had blocked ([ACM](https://dl.acm.org/doi/10.1145/358198.358218)).
- **A bad *first* recommendation is materially worse than a bad later one, and worst of all for domain experts.** Across three domains, naive first-interaction recommendations had a measured negative long-run impact — "bandit performance is directly related to the choices made in the first trials" ([Silva et al., ACM TORS 2022](https://dl.acm.org/doi/10.1145/3554819)). With accuracy held *constant*, early errors "cause negative first impressions for domain experts, negatively impacting their trust over the course of interactions," while novices instead over-rely ([Nourani et al., HCOMP 2020](https://arxiv.org/abs/2008.09100)). And people abandon algorithms faster than humans after identical errors ([Dietvorst et al. 2015](https://marketing.wharton.upenn.edu/wp-content/uploads/2016/10/Dietvorst-Simmons-Massey-2014.pdf)).

---

## 1. "Magic first screen": what the published record actually supports

The canonical story — link an account, watch a personalized dashboard assemble itself, be hooked — is repeated everywhere and measured almost nowhere. I went looking for funnel results for Mint, Credit Karma, Copilot Money, Rocket Money/TrueBill, Strava, Whoop and Oura. **None has published post-connection activation or retention data.** What exists is product journalism, teardowns without instrumentation, and help-centre pages.

What *is* published sits one step upstream, at the connection itself. **Plaid Link** reports "roughly 1 in 3 US consumers with a financial account connecting to apps using Plaid Link"; a customer (Stash) saw **+21% external account connections and +19% subsequent account funding** after switching providers; a mobile-web OAuth pop-up produced a **~11% relative conversion lift**; app2app SDK auth got **10–15% more users to connect**; and — notably — *personalizing the institution list* delivered only **~1% relative lift** ([Plaid](https://plaid.com/blog/more-conversion-with-plaid-link/)). Conversion there is defined as HANDOFF ÷ unique link sessions ([docs](https://plaid.com/docs/link/measuring-conversion/)); no sample sizes or windows are disclosed.

Two readings follow. First, in the one domain where import-led onboarding is instrumented in public, **the measured wins are in removing friction from the import, not in dressing up what happens after it** — and the one personalization lift reported is ~1%, an order of magnitude below the plumbing wins. Second, this is publication bias in a specific shape: an infrastructure vendor publishes the metric it owns.

The strongest *indirect* support for the magic-screen thesis is adjacent work logged in round 1: Pinterest's country-specific new-user topic pickers, built from an inferred attribute (locale) with zero user input, made signups **5–10% more likely to return** ([Pinterest](https://medium.com/pinterest-engineering/personalizing-pinterests-new-user-experience-abroad-60f8f55177ac)); Spotify's onboarding-signal ablation cost **-13.8% nDCG@50** on onboarding-aligned clusters ([Spotify Research](https://research.atspotify.com/2025/9/generalized-user-representations-for-large-scale-recommendations)).

**The time budget.** Netflix's published account of its recommender is the most usable constraint in print: a typical member browses 10–20 titles and "either finds something of interest [within the first 60 or 90 seconds] or the risk of the user abandoning our service increases substantially" ([Gomez-Uribe & Hunt, ACM TMIS 6(4)](https://dl.acm.org/doi/10.1145/2843948)). That is a *browsing* budget for a returning member, so transferring it to a first run is a hypothesis — but it is the only hard number of its kind.

**The counter-precedent nobody cites.** Whoop and Oura are import-data products that deliberately *refuse* to show personalized value early. Whoop runs a stated 4-day calibration and ~1 week to a personal baseline; commentary is blunt that early scores are "measuring you against a rough population average, or worse, guessing" ([freeCodeCamp](https://www.freecodecamp.org/news/why-your-wearable-needs-weeks-of-data-before-it-becomes-useful)). That is a shipped alternative strategy: **when the first computation is genuinely low-confidence, name the calibration period rather than fake the payoff.** No retention data either way — but a large product doing the opposite of "magic in seconds" is evidence the thesis is contingent, not universal.

---

## 2. The confirmation tap: infer, then ask the user to confirm or correct

The hypothesis is that a product should compute a segment from imported data, show it, and ask for one tap — beating both a survey (extraction, no visible return) and a silent inference (invisible, unverifiable).

**The case for it rests on legibility, and the best evidence is Pinterest's.** Placed inside the onboarding flow with a stated reason ("helps us show you more relevant content"), a gender question **added a step and still lifted flow completion +11%**, with ~8% gains on Facebook signups *where gender was already known*. The same question placed immediately after Google auth produced +7% activation but a **-30% collapse in Google signups** ([Pinterest Engineering](https://medium.com/pinterest-engineering/exploring-effective-user-signals-585507d8e926)). Pinterest's own conclusion was that signal collection is "an opportunity to educate users about personalization benefits." The redundant-question gain is the load-bearing detail: **the ask did psychological work independent of its informational value** — which is exactly the mechanism a confirmation tap would exploit.

Two supporting strands, both indirect. **Ownership through minimal labor:** the IKEA effect — a single act of assembly raising valuation of the result — is established across four studies on boxes, origami and Lego, *but* with a boundary condition the authors stress: **labor leads to love only when labor results in successful completion**; when participants failed to complete or destroyed their creation, the effect dissipated ([Norton, Mochon & Ariely 2012](https://www.hbs.edu/ris/Publication%20Files/11-091.pdf)). A confirmation tap that surfaces an obviously *wrong* inference is a failed completion, not a cheap ownership win. **Perception beats accuracy:** Knijnenburg et al. find "perceptions of recommendation quality and/or variety are important mediators" between system properties and experience — accuracy "only partially constitutes the user experience" ([UMUAI 2012](https://pure.tue.nl/ws/files/3484177/724656348730405.pdf)). A confirm step is a perception intervention as much as a data one. Harper et al. make the adjacent case that lightweight user control can be bolted onto any recommender by re-ranking ([RecSys 2015](https://files.grouplens.org/papers/harper-recsys2015.pdf)).

**The case against it is sharper than I expected.** Levy et al. ran a lab study with **18 clinicians** annotating clinical text. Experts generally built calibrated intuition about when to rely on automation — *but* "when presented with fully pre-populated suggestions, these expert users exhibit less agency: accepting improper mentions, and taking less initiative in creating additional annotations" ([arXiv 2103.04725](https://arxiv.org/abs/2103.04725)). Translated: **a pre-filled answer with a confirm button does not reliably harvest a correction; it manufactures assent.** Defaulting the answer converts a question into a default (§4), with all the power and all the epistemic emptiness that implies.

**Accuracy legibility is the hinge, and it is segment-dependent.** Nourani et al. held accuracy *constant* and varied only error timing: domain experts formed durable negative first impressions from early errors, knowledgeable users who saw correct outputs first went on to "dynamically adjust their trust based on their observations," and **novices "suffer from over-reliance due to their lack of proper knowledge to detect errors"** ([HCOMP 2020](https://arxiv.org/abs/2008.09100)). The confirmation tap's *value* (a real correction signal) and its *risk* (a wrong inference read as authoritative) land on opposite segments.

**Correction rates: a genuine gap.** No published benchmark exists for what fraction of users correct a system-inferred attribute at onboarding. The nearest datum is lab-scale and domain-specific: in an annotation-suggestion study, users accepted suggestions "over 99% of the time" when correct, but when the label was wrong the median user accepted unmodified only **17%** of the time — i.e. when error is *visible*, users do reject. Search-summary only; do not plan on the number.

---

## 3. Loading and processing as theater

**The primary result.** Buell & Norton, "The Labor Illusion: How Operational Transparency Increases Perceived Value," *Management Science* 57(9), 1564–1579, 2011. Five experiments simulating online travel and online dating: when a site signals it is exerting effort, "people can actually prefer websites with longer waits to those that return instantaneous results — even when those results are identical," with perceived provider effort inducing reciprocity, and the two together mediating the transparency→valuation link ([citation record](https://ideas.repec.org/a/inm/ormnsc/v57y2011i9p1564-1579.html); [HBS PDF](https://www.hbs.edu/ris/Publication%20Files/Norton_Michael_The%20labor%20illusion%20How%20operational_f4269b70-3732-4fc4-8113-72d0c47533e0.pdf); [Semantic Scholar record](https://www.semanticscholar.org/paper/The-Labor-Illusion:-How-Operational-Transparency-Buell-Norton/46cb7b946bec87d30c27d2ca1b6c457db59de11d)).

**A methodological warning.** An automated extraction of the HBS PDF returned tidy study parameters — specific Ns, a 0/15/30/60-second condition grid, and a claim that the effect "reverses beyond 90 seconds." I could not corroborate any of it (INFORMS 403; local PDF text extraction unavailable), and the shape of those numbers is exactly what a summarizing model invents when pressed for specifics. **Do not cite a reversal threshold from this paper.** The defensible claim is directional.

**Where the ceiling actually comes from.** Not from Buell & Norton but from the response-time literature: 0.1s for direct manipulation, 1s for uninterrupted flow of thought, and **10s as "about the limit for keeping the user's attention focused on the dialogue"** — beyond which users task-switch and need an expected-completion signal ([NN/g](https://www.nngroup.com/articles/response-times-3-important-limits/)). Independently, the wait's *design* moves perceived duration: Harrison et al. evaluated nine progress-bar behaviours and found variants that "appear faster when in fact they are not… yielding statistically significantly shorter perceived durations," with users most tolerant of slow behaviour at the *beginning* and slow-to-fast pacing best overall ([UIST 2007](https://chrisharrison.net/projects/progressbars/ProgBarHarrison.pdf)).

**The field anecdote that generalises best.** Steven Hoober built a mobile-phone plan advisor whose instant results nobody trusted: "we found that no one trusted the information. We eventually discovered that users assumed that a fast response meant a lie — a canned response pushing what the company wanted to sell." The fix was "a delay indicator — with a bit of randomness for the time so it didn't seem fake," after which users leaned into the screen ([4ourth Mobile](https://www.4ourthmobile.com/publications/the-labor-illusion-and-ethically-deceptive-design)). Qualitative and self-reported, but it is the closest published case to *a recommendation engine whose speed read as a sales pitch* — the exact failure a trade engine could inherit. Kayak's itemised "searching Delta… comparing 200 airlines…" stream is the commercial instantiation ([digitalwellbeing.org](https://digitalwellbeing.org/the-kayak-effect-why-making-customers-wait-drives-satisfaction/)).

**The honest/dishonest line.** Buell's later framing is *operational transparency* — showing work that is actually happening ([HBR 2019](https://hbr.org/2019/03/operational-transparency)). Itemising real computation is disclosure; padding an instant result is deception. A product that genuinely computes something has the cheap version available and does not need the expensive one.

---

## 4. Defaulted, unskippable setup steps — and when removing skip backfires

**The Superhuman case, with its full number set** ([First Round](https://review.firstround.com/superhuman-onboarding-playbook/); [Gaurav Vohra](https://substack.gauravvohra.com/p/obsessing-over-onboarding-for-10)):

| Change | Result |
|---|---|
| Tucked-away checklist → full-screen, unskippable panels with smart defaults | completion **30% → over 98%** |
| Same change, feature opt-in | **45% → nearly 80%** |
| Opinionated focus on two shortcuts ("e" done, "h" reminder) | shortcut usage **+50%** |
| Prioritising Inbox Zero controls | self-serve activation **40% → 50%** |
| "Get Me To Zero" interruptive prompt | **57%** opt-in; ~1B emails archived |
| Human-led (concierge) onboarding | **>65%** of new customers fully transitioned email; ~2x self-serve |

Their three stated principles are the transferable part: **opinionated** (the single path to setup→aha→habit), **interruptive** ("if an experience is tucked away, it will be ignored — and if it is ignored, it may as well not exist"), and **interactive** ("do > show > tell").

**The general power of defaults is among the best-evidenced findings in behavioural science**, and is worth separating from "unskippable." Madrian & Shea showed 401(k) participation is "significantly higher under automatic enrollment," with the company-chosen default rate and fund allocation exerting a strong pull on subsequent behaviour ([QJE 116(4)](https://academic.oup.com/qje/article-abstract/116/4/1149/1903159); [NBER](https://www.nber.org/papers/w7682)). Johnson & Goldstein found opt-out countries clustering near-universal consent against roughly 10–28% under opt-in ([*Science* 302(5649)](https://www.science.org/doi/10.1126/science.1091721)). Neither removed the user's ability to skip; both moved what happens if the user does nothing.

**The backfire case.** Vevo A/B-tested its informational onboarding screens (reported as 15% of new users per arm). Adding a skip raised logins by **nearly 10%** and successful signups by **almost 6%**, with no reported engagement cost ([secondary](https://messagegears.com/resources/blog/mobile-app-onboarding-creating-engaged-users-from-the-start/); the primary Apptimize post now 301s to airship.com). This sits alongside round 1's NN/g controlled result (n=70) that tutorial-viewers succeeded no more often and rated tasks *harder* ([NN/g](https://www.nngroup.com/articles/mobile-tutorials/)). The named mechanism is psychological reactance: a mandatory flow removes perceived freedom, and users optimise for escape rather than comprehension.

**The reconciliation.** Superhuman and Vevo look contradictory and are not. Superhuman made unskippable a set of steps that were **pre-decided on the user's behalf** — smart defaults, nothing to author, work being done *for* them. Vevo made unskippable a set of screens that **asked for attention and gave nothing back**. The rule that fits both:

> Unskippable is safe when the step *does work for the user* and is defaulted so there is nothing to decide. Unskippable is dangerous when the step *asks something of the user* — attention, data, or a decision.

That rule is my synthesis, not a published finding, and it is testable: it predicts that making a defaulted, do-it-for-you step unskippable raises completion with no retention cost, while making an explanatory or interrogative step unskippable raises completion and lowers downstream engagement.

---

## 5. Synthetic/sandbox first actions vs. real-data first actions

**Superhuman's is the headline case and it runs against intuition.** They moved onboarding *out* of the user's real inbox into a full-screen **synthetic inbox** — "fully interactive and entirely safe" — because real inboxes were inconsistent (an empty one teaches nothing) and users hesitated to take irreversible actions on real mail. Reported: shortcut usage **+20%**, reminder adoption **+67%**, week-1 activation **+17%** ([Growthmates](https://www.growthmates.news/p/onboarding-lab-how-superhuman-and); corroborated in [First Round](https://review.firstround.com/superhuman-onboarding-playbook/)).

**The academic root is 40 years old and stronger than the product anecdote.** Carroll & Carrithers' *training wheels* interface disabled features novices don't need but which "can be springboards for errors and confusions." Learners on the reduced interface were faster and more successful, with better comprehension post-test scores, and the control group "spent almost a quarter of their time recovering from the error states that the training interface blocked off" ([CACM](https://dl.acm.org/doi/10.1145/358198.358218); [CHI/GI 1987](https://dl.acm.org/doi/10.1145/29933.275625); [SAGE 1984](https://journals.sagepub.com/doi/10.1177/001872088402600402)). The mechanism — *error states are the tax on learning in a dense product* — transfers cleanly.

**The synthesis** (round 1's H6, now with an anchor): **imported real data is superior for personalising what you show; a controlled synthetic surface is superior for teaching a mechanic safely.** Different moments, separable within one first session.

**Gap:** no published A/B of sandbox-vs-real-data teaching for a *recommendation* product, where the sandbox has an extra job — protecting the algorithm's reputation from an unrepresentative first case. The commercial "interactive demo" literature offers vendor case studies with no disclosed methodology and should not be used as evidence.

---

## 6. The trust problem: what a bad first recommendation costs

This is the best-evidenced section in the document, and the news is bad for anything that leads with an algorithmic suggestion.

**First recommendations have measurable long-run consequences.** Silva et al. observe that contextual-bandit recommenders "are limited to naive non-personalised approaches in the first interactions of a new user, offering random or most popular items," and: "Through experiments in three domains, we identify a negative impact of these first choices. Our study indicates that the bandit performance is directly related to the choices made in the first trials" ([ACM TORS 2022](https://dl.acm.org/doi/10.1145/3554819)). This is a *system*-level result — first interactions shape everything the model learns afterwards — which compounds with the psychological results below rather than duplicating them.

**People punish algorithms harder than humans for identical errors.** Dietvorst, Simmons & Massey, five studies: "people more quickly lose confidence in algorithmic than human forecasters after seeing them make the same mistake," even having watched the algorithm outperform the human ([*JEP: General* 144(1)](https://marketing.wharton.upenn.edu/wp-content/uploads/2016/10/Dietvorst-Simmons-Massey-2014.pdf)). The trade engine is held to a standard no human trade partner is held to.

**Error *order* matters even at constant accuracy, and expertise inverts the failure mode.** Nourani, King & Ragan fixed an explainable classifier's accuracy and varied only error timing: "encountering errors early-on can cause negative first impressions for domain experts, negatively impacting their trust over the course of interactions. However, encountering correct outputs early helps more knowledgable users to dynamically adjust their trust… In contrast, novice users suffer from over-reliance due to their lack of proper knowledge to detect errors" ([HCOMP 2020](https://arxiv.org/abs/2008.09100)). **For an expert audience the first few outputs are not a sample — they are a verdict.**

**Two softer strands.** Trust-dynamics modelling finds "the user attitude (controlled by a single parameter balancing the gain/loss of trust after a good/bad recommendation) has a great impact in the trust dynamics" — the per-user loss-to-gain asymmetry dominates the long-run equilibrium ([Pelta et al. 2020](https://arxiv.org/abs/2002.04302)); this is a simulation. And the recommender-UX literature reports a self-serving attribution pattern — users credit themselves for good recommendations and blame the system for bad ones — which if true means good first recs buy less credit than bad ones cost (folklore-grade; no primary verified).

**Mitigations the same literature points at.** Explanations are the oldest lever: Herlocker, Konstan & Riedl established the explanation-interface agenda for collaborative filtering and reported experimental results on which components are most compelling ([CSCW 2000](https://dl.acm.org/doi/10.1145/358916.358995)). Knijnenburg's mediation framework implies the target is *perceived* quality, of which accuracy is only a component. And Netflix's history cautions against over-collecting explicit taste data: "knowing my age and gender doesn't help predict my movie tastes. Knowing just a few movies or TV shows I like is much more helpful," and a simpler thumbs interface "collected twice as many ratings" as five stars ([Gibson Biddle](https://gibsonbiddle.medium.com/a-brief-history-of-netflix-personalization-1f2debf010a1)) — practitioner memoir, not a published experiment.

---

## Evidence quality notes

**Tier 1 — peer-reviewed and controlled**

- Nourani, King & Ragan (HCOMP 2020) — accuracy held constant, error ordering manipulated, expertise as moderator. Sample size not stated in the abstract; image-classification domain, so transfer is an assumption.
- Dietvorst, Simmons & Massey (2015) — five studies, incentivised choice, *JEP: General*.
- Silva et al. (ACM TORS 2022) — three domains, but **offline simulation of bandit trajectories, not a live user experiment**.
- Levy et al. (2021) — n=18 clinicians, lab study. Very small, single domain, high internal validity.
- Buell & Norton (*Management Science* 2011) — five experiments; **direction verified, parameters not.**
- Carroll & Carrithers (1984/1987) — small-n by modern standards; 1980s word processor.
- Madrian & Shea (2001), Johnson & Goldstein (2003) — canonical default-effect evidence, but neither is about removing a skip button.
- Harrison et al. (UIST 2007) — nine progress-bar variants, significant perceived-duration differences.

**Tier 2 — company blogs / first-person practitioner accounts, methodology undisclosed**

- Superhuman's full number set. Two independent write-ups agree, one by the person who ran the work — but self-reported, no test design or significance, published as a success narrative.
- Pinterest gender-signal result (+11% / -30%) — unusually credible because it publishes the negative arm.
- Plaid conversion figures — real analytics, no samples or windows, published by the vendor whose metric it is.
- Netflix 60–90 seconds and $1B/year — peer-reviewed venue, but company narrative rather than reported experiment.
- Gibson Biddle's Netflix personalization history — practitioner memoir.

**Tier 3 — secondary or unverifiable**

- **Vevo's ~10% logins / ~6% signups.** Primary Apptimize post is gone (301 → airship.com); every surviving version is secondary. Direction agrees with NN/g's controlled result; the numbers are not solid.
- Hoober's phone-plan advisor — qualitative, single case, no numbers.
- "99% accept when correct / 17% accept unmodified when wrong" — search-summary only, primary not read.
- Self-serving attribution in recommender trust; Kayak "slowed down and bookings went up" — folklore-grade, no primary located.

**Tier 4 — do not use**

- Any duration threshold for the labor illusion ("reverses past 90 seconds", "optimal 30–60s") — automated PDF summarisation, uncorroborated.
- Interactive-demo vendor case studies; "progress indicators improve completion by ~12%" — no disclosed methodology.

**Gaps I could not close**

1. **No published post-connection funnel data for any consumer fintech or wearable** (Mint, Credit Karma, Copilot, Rocket Money, Strava, Whoop, Oura all searched). If the magic-first-screen thesis has ever been A/B tested, the result is not public.
2. No benchmark for confirm/correct rates on system-inferred attributes at onboarding.
3. No A/B of sandbox-vs-real-data teaching for a recommendation product.
4. No study of first-recommendation confidence gates measured against retention.
5. The Buell & Norton study parameters — needs a library copy.

---

## Implications for FTF

*Hypotheses only. Nothing below is a recommendation to build, and several of them conflict with each other on purpose.*

**H1 — The magic first screen is a design bet, not an evidenced pattern.** The published record supports "reduce friction on the import" (Plaid's measured wins) far better than "make the post-import screen spectacular" (nobody's measured win). If FTF invests here it should instrument the post-import screen itself, because the industry hasn't.

**H2 — FTF's first-recommendation risk is the highest-severity finding here, and its audience makes it worse.** Nourani et al. say early errors durably damage trust *specifically for domain experts who can detect them*. Dynasty players are exactly that, with strong priors about player values; a first trade suggestion that reads as absurd is not a sample, it is a verdict — and Dietvorst says they will punish the algorithm harder than a human trade partner making the same mistake. Corollary: **the first suggestion should be optimised for defensibility, not for cleverness or maximum computed gain.**

**H3 — A first-recommendation confidence gate may be worth more than a better model.** Silva et al. show first choices shape the whole trajectory. A gate that suppresses or reframes low-confidence first suggestions ("here's the clearest one; there are 14 more once we know your board") trades coverage for credibility. Testable against a no-gate arm on D7 return, though FTF is almost certainly under-powered for it (round 1, H7).

**H4 — If the confirmation tap is meant to collect a correction, it must not pre-select.** Levy et al. is the direct warning: fully pre-populated suggestions get accepted, wrong ones included. For a *correction signal* (labelled training data for a roster-archetype classifier), disagreement must be as cheap as agreement. If the goal is only *legibility* (Pinterest's mechanism), a pre-filled confirm is fine — but then it is not a data-quality check and shouldn't be treated as one.

**H5 — Split the confirmation tap by segment, because the risk inverts.** For an expert, a wrong inferred archetype shown confidently is an early error — the thing Nourani says costs durable trust. For a novice, the same screen risks over-reliance on a label they can't evaluate. Round 1's H4 already noted that league count, format and trade history separate these segments at import with no questions asked.

**H6 — The Elo matchup vote and the board mechanic are the sandbox candidates; the trade suggestions are the personalized ones.** Superhuman and Carroll & Carrithers point the same way: teach the *mechanic* on controlled data where no error state exists and nothing is risky; personalize the *content*. FTF has an unusual advantage — a synthetic matchup is not obviously fake to a dynasty player, since comparing three real NFL players is legitimate regardless of whose roster they're on.

**H7 — Loading theater is cheap and defensible for FTF specifically, because the labor is real.** FTF genuinely computes Elo, roster holes and a mutual-gain search. Itemising that ("reading 12 rosters… scoring 4,300 candidate trades… filtering for mutual gain") is operational transparency, not a fake spinner, and Hoober's case is the closest published analogue to instant results reading as a sales pitch. Bound it by Nielsen's 10s limit, front-load the slow portion (Harrison), and never pad past the real computation.

**H8 — Unskippable is available to FTF only for defaulted, do-it-for-you steps.** By the §4 rule, a full-screen unskippable step is safe if it *configures* something on the user's behalf (league defaulted to their only dynasty league; scoring format read from Sleeper; board pre-seeded) and dangerous if it *explains* or *interrogates*.

**H9 — Consider the Whoop counter-strategy as an explicit alternative arm.** If first-session suggestions are genuinely low-confidence before any want/accept input, the honest move may be to *name the calibration* ("your suggestions sharpen after you rate three matchups") rather than lead with the weakest output the engine will ever produce. This contradicts H1, which is why it belongs in the same list.

**H10 — Redundant asks are not automatically waste.** Pinterest's ~8% gain on Facebook signups, where the answer was already known, is the most surprising number in this lens: asking for information you already have can still pay, because the ask communicates that personalization is happening. That reframes "we already read your roster, so don't ask" as testable rather than obvious.

---

## Sources

**Peer-reviewed**

- Buell, R. W. & Norton, M. I. — *The Labor Illusion: How Operational Transparency Increases Perceived Value*, Management Science 57(9):1564–1579 (2011): https://ideas.repec.org/a/inm/ormnsc/v57y2011i9p1564-1579.html · PDF: https://www.hbs.edu/ris/Publication%20Files/Norton_Michael_The%20labor%20illusion%20How%20operational_f4269b70-3732-4fc4-8113-72d0c47533e0.pdf
- Dietvorst, B., Simmons, J. & Massey, C. — *Algorithm Aversion: People Erroneously Avoid Algorithms After Seeing Them Err*, JEP: General 144(1) (2015): https://marketing.wharton.upenn.edu/wp-content/uploads/2016/10/Dietvorst-Simmons-Massey-2014.pdf
- Nourani, M., King, J. & Ragan, E. — *The Role of Domain Expertise in User Trust and the Impact of First Impressions with Intelligent Systems*, HCOMP 2020: https://arxiv.org/abs/2008.09100
- Silva, N. et al. — *User Cold-start Problem in Multi-armed Bandits: When the First Recommendations Guide the User's Experience*, ACM TORS (2022): https://dl.acm.org/doi/10.1145/3554819
- Levy, A., Agrawal, M., Satyanarayan, A. & Sontag, D. — *Assessing the Impact of Automated Suggestions on Decision Making: Domain Experts Mediate Model Errors but Take Less Initiative* (2021): https://arxiv.org/abs/2103.04725
- Gomez-Uribe, C. & Hunt, N. — *The Netflix Recommender System: Algorithms, Business Value, and Innovation*, ACM TMIS 6(4) (2016): https://dl.acm.org/doi/10.1145/2843948
- Carroll, J. M. & Carrithers, C. — *Training Wheels in a User Interface*, CACM (1984): https://dl.acm.org/doi/10.1145/358198.358218 · *Blocking Learner Error States in a Training-Wheels System*: https://journals.sagepub.com/doi/10.1177/001872088402600402 · *Learning a word processing system with training wheels and guided exploration*: https://dl.acm.org/doi/10.1145/29933.275625
- Harrison, C., Amento, B., Kuznetsov, S. & Bell, R. — *Rethinking the Progress Bar*, UIST 2007: https://chrisharrison.net/projects/progressbars/ProgBarHarrison.pdf
- Herlocker, J., Konstan, J. & Riedl, J. — *Explaining Collaborative Filtering Recommendations*, CSCW 2000: https://dl.acm.org/doi/10.1145/358916.358995
- Knijnenburg, B. et al. — *Explaining the User Experience of Recommender Systems*, UMUAI (2012): https://pure.tue.nl/ws/files/3484177/724656348730405.pdf
- Harper, F. M. et al. — *Putting Users in Control of their Recommendations*, RecSys 2015: https://files.grouplens.org/papers/harper-recsys2015.pdf
- Norton, M., Mochon, D. & Ariely, D. — *The IKEA Effect: When Labor Leads to Love*, J. Consumer Psychology (2012): https://www.hbs.edu/ris/Publication%20Files/11-091.pdf
- Madrian, B. & Shea, D. — *The Power of Suggestion: Inertia in 401(k) Participation and Savings Behavior*, QJE 116(4) (2001): https://academic.oup.com/qje/article-abstract/116/4/1149/1903159 · NBER: https://www.nber.org/papers/w7682
- Johnson, E. & Goldstein, D. — *Do Defaults Save Lives?*, Science 302(5649) (2003): https://www.science.org/doi/10.1126/science.1091721
- Pelta, D. et al. — *Trust dynamics and user attitudes on recommendation errors: preliminary results* (2020): https://arxiv.org/abs/2002.04302

**Company engineering / research blogs**

- Plaid — *Activate more users with a faster and easier Link experience*: https://plaid.com/blog/more-conversion-with-plaid-link/ · *Measuring conversion*: https://plaid.com/docs/link/measuring-conversion/
- Pinterest Engineering — *Exploring effective user signals*: https://medium.com/pinterest-engineering/exploring-effective-user-signals-585507d8e926 · *Personalizing Pinterest's new user experience abroad*: https://medium.com/pinterest-engineering/personalizing-pinterests-new-user-experience-abroad-60f8f55177ac
- Spotify Research — *Generalized user representations for large-scale recommendations*: https://research.atspotify.com/2025/9/generalized-user-representations-for-large-scale-recommendations
- Harvard Business Review — Buell, *Operational Transparency* (2019): https://hbr.org/2019/03/operational-transparency

**Practitioner accounts**

- First Round Review — *How to Build and Scale Onboarding* (Superhuman playbook): https://review.firstround.com/superhuman-onboarding-playbook/
- Gaurav Vohra — *Obsessing Over Onboarding for 10+ Years*: https://substack.gauravvohra.com/p/obsessing-over-onboarding-for-10
- Growthmates — *Onboarding Lab: How Superhuman and Reforge craft the first experience*: https://www.growthmates.news/p/onboarding-lab-how-superhuman-and
- Gibson Biddle — *A Brief History of Netflix Personalization*: https://gibsonbiddle.medium.com/a-brief-history-of-netflix-personalization-1f2debf010a1
- Steven Hoober / 4ourth Mobile — *The Labor Illusion and Ethically Deceptive Design*: https://www.4ourthmobile.com/publications/the-labor-illusion-and-ethically-deceptive-design
- NN/g — *Response Time Limits*: https://www.nngroup.com/articles/response-times-3-important-limits/ · *Mobile tutorials: wasted effort or efficiency boost?*: https://www.nngroup.com/articles/mobile-tutorials/

**Secondary / tier-3 (cited with caveats)**

- Vevo onboarding-tutorial A/B (primary Apptimize post dead; secondary): https://messagegears.com/resources/blog/mobile-app-onboarding-creating-engaged-users-from-the-start/
- digitalwellbeing.org — *The Kayak Effect*: https://digitalwellbeing.org/the-kayak-effect-why-making-customers-wait-drives-satisfaction/
- freeCodeCamp — *Why Your Wearable Needs Weeks of Data Before It Becomes Useful* (Whoop/Oura calibration): https://www.freecodecamp.org/news/why-your-wearable-needs-weeks-of-data-before-it-becomes-useful
