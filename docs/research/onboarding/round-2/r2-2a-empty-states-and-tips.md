# R2-2A — Empty States, Tips, and the Trigger/Retirement Rules That Govern Them

**Round 2, Lens 2A — research brief**
**Date:** 2026-08-15
**Lens:** The concrete design of a contextual teaching layer — empty-state pattern library (including "no results"), trigger taxonomy as actually implemented, retirement/frequency governance, tip copy patterns, cross-feature bridging prompts, and games' just-in-time hint systems as a transferable model.
**Builds on:** round-1 `b1-progressive-disclosure-theory.md` and `b2-contextual-inapp-patterns.md`. Findings already established there (interruption budget, modal 4-second rule, pull-beats-push, expertise reversal) are assumed, not re-derived.

---

## TL;DR

- **The best experiment here is from games, not SaaS.** Andersen et al. (CHI 2012, **45,000+ players**) found tutorials paid off only in the most complex of three games: in Foldit, context-sensitive tutorials produced **+75% levels and +29% play time** vs none, and **+40% levels / +16% time** vs identical content delivered out of context. In the two simpler games tutorials did nothing — and on-demand help *actively hurt* one ([PDF](https://grail.cs.washington.edu/projects/game-abtesting/chi2012/chi2012.pdf)). **Complexity is the gate; context-sensitivity is the multiplier.**
- **Help-on-demand can be net negative.** In Refraction, players given a help button completed a median **14 levels vs 16** and played **900s vs 1050s** vs players given nothing (p=0.013 / p=0.031); in Hello Worlds it dropped return rate to **18.44% from 21.60%** (p=0.003). A teaching affordance is not free even when the user must opt in.
- **Placement beats volume, with a hard number.** Maniktala et al. compared unsolicited hints rendered *inside the workspace in the user's own visual format* against text hints fired after **1 minute of idle**: attention rate **0.93 vs 0.63** (F(1,100)=191.10, p<0.001), and the *number* of hints given correlated with no learning outcome while attention to them did ([arXiv 2009.13371](https://arxiv.org/abs/2009.13371)). Idle-timeout is the weakest trigger measured anywhere here.
- **A relevance-only trigger over-fires catastrophically.** Aleven et al.'s help-seeking model — 57 production rules over ~47,500 real actions — flagged **72% of all actions** as teachable moments; the authors' verdict is that intervening on 3 of 4 actions "is likely to be quite annoying and distracting" ([ITS 2004](https://www.cs.cmu.edu/~bmclaren/pubs/AlevenEtAl-HelpSeeking-ITS2004.pdf)). **Trigger predicate and delivery budget are two systems; both are required.**
- **Copy length has a measured ceiling:** ~25s base + **4.4s per additional 100 words** (~18 words read per extra 100 written), and half the information read only at **≤111 words** ([NN/G](https://www.nngroup.com/articles/how-little-do-users-read/)). With round 1's 4-second modal dismissal: ~16 words of usable budget.
- **Four design systems independently converged on one empty-state contract:** name the state → explain the next step → **exactly one primary action** → never a dead end. Carbon adds **starter content** as a distinct tier for when a sentence cannot convey what belongs in the space.
- **Governance in practice = three layered caps (session → format → campaign lifetime) plus one semantic rule,** whose strongest first-party statement is Intercom's (2016): *"When you dismiss a snippet, we'll never show it to you again. On any platform."*
- **The two weakest evidence areas are the two written about most confidently.** "Did you know" framing and cross-feature bridging prompts have essentially **zero** published controlled measurement — everything available is vendor case-study copy with no control group.

---

## 1. Empty-state pattern library

### 1.1 The contract, as four independent design systems state it

Round 1 established NN/G's three functions — communicate system status, provide a learning cue, provide a direct pathway ([NN/G](https://www.nngroup.com/articles/empty-state-interface-design/)). Four production design systems, written by different companies for different audiences, independently specify the same contract plus operational detail:

| System | Scenario taxonomy | CTA rule | Copy rule |
|---|---|---|---|
| **[PatternFly](https://www.patternfly.org/components/empty-state/design-guidelines/)** | 7: getting started, no results, required configuration, no access, back-end failure, success, creation | **One primary CTA**; secondary below; standalone secondary when the only action is "adjust filters" | "State what isn't there, and then give the user a next step." Sentence case; no blame; no "please" |
| **[Carbon](https://carbondesignsystem.com/patterns/empty-states-pattern/)** | 3 basic (no data / user action / error) + 3 in-depth alternatives (in-line docs, onboarding, **starter content**) | Single most-important action; **"never lead users into dead ends"**; tertiary buttons when several empty states co-occur | "Keep words to a minimum"; write positively ("Start by adding data assets", not "You don't have any"); no jargon |
| **[Atlassian](https://atlassian.design/components/empty-state)** | Not enumerated | Primary button for the best next step; **tertiary** when multiple empty states could render at once | If no results: "suggest adjusting the search or filters" |
| **[Material](https://m1.material.io/patterns/empty-states.html)** | first-time use, user-cleared, errors, **no results** | Basic tier deliberately has **no** CTA — the tagline "conveys the purpose of the app without coming across as a call to action" | Heading states no results found; body explains how to continue searching |

Two operational rules are non-obvious. **The multi-empty-state collision rule:** Carbon and Atlassian both specify demoting the CTA to tertiary when several empty states can render on one screen — four competing primary buttons teach nothing, which is round-1's badge-blindness failure mode in button form. **Carbon's "starter content" tier:** pre-populating the space with sample data is a *distinct pattern*, prescribed when a sentence cannot convey what belongs there.

### 1.2 Concrete product examples

From UserOnboard's collection, the mechanistically distinct ones ([UserOnboard](https://www.useronboard.com/onboarding-ux-patterns/empty-states/)): **Trello** preloads a real, working board showing members, cards and activity — the empty state *is* a functioning instance of the product. **Dropbox** preloads a PDF that exists across devices, demonstrating the core value proposition (sync) *and* serving as the getting-started guide. **Evernote's** first note explains how notes work — the teaching artifact is indistinguishable in form from user content (§2.3's Assertions result in consumer form). **Duolingo** withholds the dashboard until a lesson is complete so the user never meets a blank one — avoidance rather than design, and a legitimate option. **InVision / Whimsical** use starter templates showing "what the space looks like to experienced users." **IFTTT** is deliberately minimal: "a helpful line or two" plus a next step.

Pencil & Paper adds an axis the design systems miss ([Pencil & Paper](https://www.pencilandpaper.io/articles/empty-states)): **information-focused** (reassure nothing is broken), **action-focused** (urge the user to fill it), **celebration-focused** (inbox-zero, where the right response is acknowledgement, not a CTA). Consequence: an empty *inbox* and an empty *board* are opposite states and should not share a component.

### 1.3 "No results" — the state most analogous to an empty trade-finder

This is the best-measured empty state, because e-commerce has money riding on it.

**Baymard Institute** — 25 rounds of "think-aloud" usability testing across 4,400+ participant/site sessions — reports roughly **50% of sites fail to provide effective recovery** from a zero-result search, the common failure being a dead end offering "no more than a generic set of search tips" ([Baymard](https://baymard.com/blog/no-results-page)). Two transferable findings: users hitting an unhelpful no-results page either reformulate or **abandon** (often to an external search engine — in a mobile app, abandonment just means session end); and **search tips are "rarely read" and can themselves be the reason to leave** — the sharpest available warning against the reflexive fix of adding a help paragraph.

Baymard's five prescribed strategies: related categories, alternative searches with previews, personalized recommendations, support contact, and popular/bestselling items with social proof. What they share — **every one replaces the empty result with content the user can act on**; none explains the search syntax.

Named instances circulating in trade press (Tier 4, no methodology): eBay offering "save this search + alert me" on zero results, Nike showing a curated popular-products grid rather than random inventory, Google's "Did you mean…" ([Prefixbox](https://www.prefixbox.com/blog/no-results-page-examples/)); Slack's no-results screen suggests the "next best thing."

**The teaching move specific to no-results:** eBay's save-search-and-alert is the only one that converts a zero-result into *feature adoption* rather than recovered browsing. That is the shape to steal — a failed query is the moment a persistent-interest feature (want board, saved search, alert) is maximally legible.

---

## 2. Trigger taxonomy as actually implemented

### 2.1 The four families

Real trigger logic decomposes into four families. Only two have good evidence.

| Family | Predicate | Evidence status |
|---|---|---|
| **Post-success boundary** | Declared completion event (submit, send, save, vote) | Strong — round-1 breakpoint literature; §6 |
| **Failure / error** | N consecutive failed attempts, or an error state | Strong in ITS/games; §2.2, §6.2 |
| **Behavioral count** | Nth use of X, or Nth screen visit without acting | Weak — widely asserted, measured nowhere I could find |
| **Idle-on-screen** | N seconds of inactivity | **Measured, and it loses** — §2.3 |

### 2.2 The one published, fully-specified trigger rule set: Aleven et al.'s help-seeking model

The most valuable find here: a complete, publishable *rule set* with named thresholds, validated against real logs, and honest about its own failure. Aleven, McLaren, Roll & Koedinger built a 57-production-rule model of ideal help-seeking for the Geometry Cognitive Tutor ([ITS 2004](https://www.cs.cmu.edu/~bmclaren/pubs/AlevenEtAl-HelpSeeking-ITS2004.pdf)):

> Spend time thinking → **Familiar at all?** No → ask for hint. Yes → **Sense of what to do?** No → consult the glossary. Yes → try the step. If wrong → **Clear how to fix?** No → ask for a hint.

The predicates are made concrete against a per-skill mastery estimate from Bayesian knowledge tracing: **`min-familiarity-level` = 0.3** (below this, show a hint rather than let them try); **"sense of what to do" = 0.6** (between 0.3 and 0.6 the right affordance is *reference material*, not a step-by-step hint); **`min-thinking-time`**, a dwell threshold below which an action is undeliberate; and hint *depth* scaled to mastery (high-skill 1/3 of available hint levels, mid 2/3, low all). The authors call these "intuitively plausible but need to be validated empirically."

**The result that matters most is the failure.** Replayed over ~47,500 actions from 49 students, **72% of all actions violated the model** — Help Abuse 37% (of which "clicking through hints" alone was 33%), Try-Step Abuse 18%, Help Avoidance 11%. Bug frequency correlated with learning gain at **r = −0.61, p < .0001**, so the model measures something real. But:

> "The current rate of 72% implies that the Help-Seeking Tutor Agent would intervene […] in 3 out of every 4 actions taken by a student. In practical use, this is likely to be quite annoying and distracting."

A well-motivated, individually-correct relevance predicate fires far too often to ship as-is. **The trigger answers "would this help?"; a separate governance layer must answer "is this the one we spend the budget on?"** Round 1's relevance-beats-recency finding is necessary but not sufficient.

Secondary finding worth carrying: help *abuse* correlated with worse learning (r = −0.46) while help *avoidance* did not (r = −0.10, n.s.). Making help too cheap to click has a measured downside; making it slightly effortful may not.

### 2.3 Idle-timeout is the weakest trigger measured

Maniktala, Cody, Barnes & Chi ran the cleanest available head-to-head on hint *delivery form* ([arXiv 2009.13371](https://arxiv.org/abs/2009.13371)). N=122 assigned (73/49), 100 analysed. **Control ("Messages"):** text hints in a message box fired **after one minute of inactivity** — the classic idle trigger, classic overlay-ish delivery. **Treatment ("Assertions"):** partially-worked example steps rendered **inside the user's own workspace, in the same visual format as their own steps**, fired after ~40% of steps.

| Metric | Assertions | Messages |
|---|---|---|
| Hints given during training | 48.82 | 32.74 |
| **Hint Justification Rate (attention)** | **0.93** (SD 0.07) | **0.63** (SD 0.18) |
| Hint Needed Rate (influence) | 0.82 | 0.62 |

HJR F(1,100)=191.10, p<0.001; HNR F(1,100)=62.30, p<0.001. No interaction with prior proficiency — the effect held for novices and experts alike.

The correlational follow-up has the teeth: **the number of hints given correlated with no posttest outcome** (solution length r=−0.13, p=0.18; time r=−0.02, p=0.88), while *attention to* hints did (HJR → solution length r=−0.25, p=0.01; low-prior-knowledge users r=−0.37, p<0.001). Volume bought nothing; form bought everything. This is direct experimental corroboration of round 1's "embedded cards beat pop-ups" vendor claim, with a cleaner mechanism: a teaching artifact that *looks like the user's own content, sitting where the user is already looking*.

### 2.4 Industrial trigger architecture: LinkedIn's Air Traffic Controller

The most detailed first-party description of a production decision layer ([LinkedIn Engineering](https://www.linkedin.com/blog/engineering/messaging-notifications/air-traffic-controller-member-first-notifications-at-linkedin)). ATC handles over a billion requests/day and, per candidate message, can **score** it to predict the likelihood of acting *or of disabling the channel* (the disable term prices the long-term cost of the interruption, not just the click); **drop** it or downgrade the channel; **delay and aggregate** it into one ranked batch; **filter** duplicates, expired content, and interactions completed elsewhere; **rate-limit** upstream applications; and **time-shift** to a locale-appropriate window. LinkedIn reports it "cut member complaints in half" with "double digit increases in member engagement site-wide."

Note: **no per-user frequency cap is disclosed** — this is a scoring-and-dropping architecture, not a quota. The transferable claim: **the drop decision and the message-authoring decision live in different systems.** Any team authors candidates; one arbiter decides what ships.

### 2.5 Vendor trigger taxonomies (Tier 3–4)

Vendor documentation converges on a plausible, unmeasured taxonomy ([Chameleon](https://www.chameleon.io/blog/contextual-in-app-guidance-vs-product-tours-guide), [Digia](https://www.digia.tech/post/in-app-nudges-mobile-growth-guide/), [GuideNow](https://vividminds.ai/products/guidenow/blog/in-app-guidance-software-triggers)): in-app events (tap, screen view, completed or **abandoned** action), user attributes, behavioural combinations, time conditions, screen/session conditions. *Abandoned action* is the only vendor trigger mapping onto the failure family — the family with real evidence.

---

## 3. Retirement and frequency governance

### 3.1 The layered-cap architecture

The clearest published cap structure is Plotline's three-layer model — **vendor content; the numbers are recommendations, not findings** ([Plotline](https://www.plotline.so/blog/frequency-capping-in-app-messaging)):

- **Layer 1 — global session cap:** 2–4 impressions/session across all campaigns and all internal teams.
- **Layer 2 — per-format cap:** full-screen modals **1/session max**; bottom sheets 1–2; tooltips/spotlights 2–3 within a guided flow; embedded widgets and floating buttons **uncapped** — they are pull surfaces and spend no budget.
- **Layer 3 — per-campaign lifetime cap:** onboarding flows 2–3 total; promotional offers once daily / 3–5 total; **feature announcements once, with "don't show again"**; NPS once per quarter; transactional uncapped.
- **Priority arbitration:** transactional > promotional > onboarding > re-engagement, with a 2–3s delay for lower-priority messages so two never render at once.

The structural insight survives even if the numbers don't: **format determines cap, and pull surfaces are exempt** — the conclusion round 1 reached independently from Chameleon's launcher data. Plotline also cites alarming statistics (71% uninstall due to annoying notifications; 46% opt out after 2–5 messages/week; 3.4× uninstall at 6+/week; 440% retention lift). **None carry a source, sample, or method. Do not plan against any of them.** Braze's parallel >2-push/week claim is likewise uncited (round 1 §11).

### 3.2 "Never show twice" — the semantic rule

The strongest first-party statement of dismissal semantics is Intercom's, 27 July 2016 ([Intercom](https://www.intercom.com/blog/behind-messenger-right-kind-disruption/)): *"When you dismiss a snippet, we'll never show it to you again. On any platform."* Support is qualitative ("hours of watching user tests" showing users close pop-ups without reading) and the conclusion unnumbered. Treat the claim as opinion; treat the **rule** as a defensible default — it is cheap, verifiable, and the failure mode of getting it wrong is precisely what trains dismissal reflexes.

Intercom's docs add two details: outbound messages support show-once-then-never keyed on interaction, and banners in a Series display once regardless of a dismiss control ([Intercom Help](https://www.intercom.com/help/en/articles/6475948-automatically-show-tooltips-to-the-right-customers)). Tooltips, by contrast, are *persistent by design*, gated by audience targeting rather than frequency — round 1's push/pull split in implementation: pushed things get budgets, pulled things get targeting.

### 3.3 Behavioral retirement — theoretical case, made urgent by one experiment

Round 1 established expertise reversal as the theoretical argument for retiring scaffolds. Two results here make it operational. **CHI 2012's help-on-demand result** (§6.1): a persistent help affordance measurably *reduced* engagement in a simple game — 14 vs 16 median levels and 900s vs 1050s in Refraction, a 3.2-point return-rate drop in Hello Worlds. The scaffold did not merely become useless; it became a cost, even though users had to opt in. **Aleven's help-abuse correlation** (§2.2): the behaviour correlating most negatively with learning was *over-use* of help (r=−0.46), not avoidance.

**Neither is answered by a dismiss button**, because both are damage done by users who *do* engage. The retirement condition must be behavioural and system-driven: N successful unaided uses retires the tip whether or not it was ever dismissed. I found **no published product-team documentation of such a rule** — no vendor supports "retire after N successful uses" as a first-class concept; the available primitives are impression counts, dismissals, and audience segments.

---

## 4. Tip content patterns

### 4.1 The reading budget gives a hard word cap

Nielsen's analysis of Weinreich's dataset — 59,573 page views from 25 users, 45,237 after cleaning — yields ~**25s base plus 4.4s per additional 100 words** ([NN/G](https://www.nngroup.com/articles/how-little-do-users-read/)). At 250 wpm, 4.4s accommodates ~18 words, hence: **"when you add verbiage to a page, you can assume that customers will read 18% of it,"** and *"users read half the information only on those pages with 111 words or less."* Composed with round 1's modal finding (38% of dismissals under 4 seconds): **4 seconds buys roughly 16 words.** A tip whose value proposition does not survive compression to one line has no delivery vehicle that will carry it.

This is desktop web, 2005–2008 — an order-of-magnitude anchor, not a constant. But every design system lands in the same place: Carbon's "keep words to a minimum so they are fast to read and act upon," PatternFly's "state what isn't there, and then give the user a next step," Chameleon's ≤26-word embeddable optimum (round 1 §4).

### 4.2 One line + one action

The convergent structure across every source: **one sentence naming the state or opportunity, plus exactly one action control.** PatternFly and Carbon explicitly forbid multiple primary CTAs; Baymard's finding that users rarely read search tips is the empirical case against the explanatory paragraph; Material's basic tier prescribes *no* CTA when the state is purely informational. Two named anti-patterns: **blame framing** (Carbon: "Start by adding data assets," not "You don't have any data assets") and **cross-reference framing** (Carbon: "be contextual; avoid referencing other app areas" — "go to Settings → Boards → Configure" is worse than a button).

### 4.3 "Did you know" framing — an evidence hole

I located **no controlled test of "did you know" framing** for in-product tips. What exists is the **curiosity-gap** rationale — copywriting practice with no product-context measurement ([AB Tasty](https://www.abtasty.com/blog/framing-effect-ux-testing/)) — and **Duolingo's Expurrimenter** copy-testing infrastructure (14 Jan 2022), the closest thing to first-party evidence that framing moves numbers. Its reported wins are reframings, not feature announcements: German notification copy recast as "proven to foster learning success" rather than "Duolingo needs to send you notifications" produced an **8% increase in opt-in**; a Spanish session-quit prompt recast to "Don't give up! Do you really want to end this session?" reduced abandonment ([Duolingo](https://blog.duolingo.com/copy-testing-experiments/)). Both replaced a *system-centred* frame with a *user-benefit* frame — a more useful generalisation than "use did-you-know." Duolingo's own caveat: copy effects do not transfer across locales; they almost certainly do not transfer across products either.

---

## 5. Cross-feature bridging prompts

The thinnest evidence area in the brief, and worth being blunt about: **I found no named, dated, controlled example of "feature A completes → suggest feature B" with a measured result.**

What exists is (a) **design-pattern assertions** — the circulating named example is Slack surfacing Workflow Builder when a user manually performs a repeatable action ([Userpilot](https://userpilot.com/blog/product-adoption-strategy/), Tier 4, no first-party confirmation, no numbers), with stated triggers of repetitive manual task / third visit without acting / milestone unlocking a capability; (b) **vendor case studies with numbers and no controls** — Ghost's progress bar ("1,000% more likely to convert" is an association presented as an effect), Trainual "+100% activation, +80% conversion," Cleeng recovering a 92% usage drop with contextual tooltips ([Userpilot](https://userpilot.com/blog/interactive-walkthroughs-improve-onboarding/)) — all testimonials produced by the vendor whose product is the treatment; and (c) **the e-commerce analogue with real research behind it** (§1.3), eBay converting a zero-result search into a saved search + alert. Only (c) is a genuine bridge sitting inside a tested framework: a failure in feature A becomes the enrolment moment for feature B.

**The defensible version of the bridging claim comes from the boundary literature, not from bridging case studies.** Iqbal & Bailey (round 1) established that task boundaries are cheap interruption points and that relevance beats timing policy; a completion event is a boundary *and* the moment adjacent-feature relevance peaks. That is a strong prior, not evidence that bridging prompts work, and it should ship labelled as a hypothesis.

---

## 6. Games' just-in-time hint systems

### 6.1 Andersen et al., CHI 2012 — the reference experiment

Eight tutorial designs across three games of varying complexity (Refraction — puzzle; Hello Worlds — platformer; Foldit — protein folding, unconventional and complex), **45,318 players**, multivariate, analysed with Wilcoxon/Kruskal-Wallis and Pearson χ² ([PDF](https://grail.cs.washington.edu/projects/game-abtesting/chi2012/chi2012.pdf)). Four variables: **presence**, **context-sensitivity**, **freedom** (blocking vs non-blocking), **help availability**.

| Comparison | Foldit (complex) | Refraction (simple) | Hello Worlds (simple) |
|---|---|---|---|
| Context-sensitive tutorial vs none | **+75% levels, +29% time** (p<0.001) | n.s. | n.s. on engagement; **return rate 17.96% vs 21.60%** (p<0.001) |
| Context-sensitive vs context-insensitive | **+40% levels, +16% time** (p<0.001 / p=0.014) | n.s. | return rate −2pts (p=0.013) |
| Blocking vs non-blocking (freedom) | n.s. on median | n.s. | n.s. |
| Help-only vs no tutorials | +time (p=0.036), +levels (p=0.001) | **14 vs 16 levels (p=0.013); 900s vs 1050s (p=0.031)** | return rate **18.44% vs 21.60%** (p=0.003) |

Four conclusions in the authors' terms: **"Tutorials were only justified in the most complex game"** — not for mechanics "that can be discovered through experimentation." **Context-sensitivity is a multiplier on a positive, not a rescue for a negative.** **Restricting freedom bought nothing anywhere**, consistent with Carroll's training wheels being *blocking-with-explanation* rather than forced-sequence (round 1 §4.1). **On-demand help is not free.**

The complexity gate is the crux for a feature-dense app: the teaching layer should be **allocated by feature, not by user**. Self-evident mechanics get nothing; mechanics not discoverable by poking get the full contextual treatment. Corroborating (weaker): Cao & Liu's review + pilot found just-in-time tutorial access positively affected gameplay learning, that tutorials matter more for complex games, and that **implicit** guidance improved enjoyment especially for experienced players ([Heliyon 2022](https://pmc.ncbi.nlm.nih.gov/articles/PMC9676530/)).

### 6.2 Struggle detection: what the trigger predicates actually are

- **ITS-derived** (§2.2–2.3): failure count, skill-mastery threshold, dwell-below-minimum, idle timeout. Idle timeout has the worst measured attention rate (0.63); mastery-thresholding has the best-specified rule set but a 72% over-fire rate.
- **Patented consumer-games logic:** Sony's "Assignment of contextual game play assistance to player reaction" ([US 10,610,783](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10610783); [US 11,229,844](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11229844)) assigns hints/advice/walkthrough content against **thresholds of inferred frustration** derived from repeated failure on a specific obstacle, explicitly aiming to intervene *before* the player quits. A patent is design intent, not evidence — but it shows what a shipped struggle-detector's inputs look like.
- **Practitioner heuristics (Tier 4, unsourced):** gentle nudge after 20–30s of inactivity or a first failed attempt; strategic guidance at 2 consecutive failures; direct help at 3+.

The escalation ladder — nudge → strategic → direct — mirrors Aleven's mastery-scaled hint depth (1/3, 2/3, all levels) arrived at from the opposite direction.

---

## Evidence quality notes

**Tier 1 — controlled experiments, published methods.** Andersen et al., CHI 2012 (45,318 players, multivariate, effect sizes and p-values) — strongest evidence here; *caveat:* Flash-era browser games plus a scientific puzzle game, "levels completed" is not "feature adopted," and none of these users had a task they needed done. Maniktala et al. (N=122 assigned / 100 analysed, stratified randomisation, ART-ANOVA) — clean, but undergraduates, one logic tutor, and the conditions differ in *both* form and trigger, so the two are partly confounded. Aleven et al., ITS 2004 (49 students, ~47,500 actions) — the model was never run live, so the 72% figure is a property of an unvalidated model, as the authors say: a warning, not a measurement of user behaviour. Nielsen/Weinreich reading data (45,237 page views) — real logs, but 25 users, desktop, 2005.

**Tier 2 — structured qualitative research at scale.** Baymard's no-results findings (25 rounds, 4,400+ think-aloud sessions). Observation, not experiment; e-commerce-specific; "~50% of sites fail" benchmarks *sites*, not user outcomes.

**Tier 3 — first-party accounts.** LinkedIn ATC (architecture credible; "complaints cut in half" has no method or counterfactual). Duolingo Expurrimenter (real A/B infrastructure; the 8% opt-in lift is one result with no CI or sample). Intercom's dismissal policy (a stated rule, qualitative support only). Design-system documentation — Carbon, PatternFly, Atlassian, Material — is **normative, not evidential**: the independent convergence is meaningful, but none of it is a study.

**Tier 4 — vendor recommendations and unsourced statistics.** Plotline's cap numbers are recommendations presented as best practice, and its statistics (71%, 46%, 3.4×, 440%) carry no source and should be ignored. Userpilot/Appcues customer case studies (Ghost, Trainual, Cleeng) are vendor-produced, uncontrolled, selection-biased. The 20–30s / 2-failure / 3-failure hint ladder is folklore. "Did you know" framing claims have no measurement at all.

**Gaps I could not close.** (1) No controlled measurement of **cross-feature bridging prompts** anywhere. (2) No published **behavioral-retirement rule** from any product team or vendor. (3) No measurement of **"did you know" framing**. (4) **No empty-state experiment** — every empty-state source here is normative or anecdotal; the closest evidence is Baymard's no-results work and the games literature by analogy. (5) **Mobbin returned 403** and could not be mined for dated mobile examples. (6) Nothing here is measured on short-session consumer mobile with a seasonal usage curve.

---

## Implications for FTF *(hypotheses only — none validated against FTF users)*

1. **Allocate the teaching layer per feature by discoverability, not per user by tenure.** CHI 2012's complexity gate says teaching pays only where the mechanic can't be found by poking. *Hypothesis:* the send-trade flow and the trade-finder list are self-evident and should get **nothing**; want/accept boards and the Elo matchup's relationship to displayed values clear the bar. Testable by comparing first-use latency against a per-feature discoverability rating.

2. **Build the empty state as one component with a scenario enum, not per-screen bespoke copy.** PatternFly's seven scenarios map onto FTF almost exactly: getting-started (empty board), no-results (trade finder returns nothing), creation (no leagues linked), success (inbox zero), no-access (unlinked platform), back-end failure (Sleeper down). *Hypothesis:* a single `EmptyState` primitive with a hard one-primary-CTA constraint prevents the multi-empty-state collision Carbon and Atlassian warn about, and is cheaper than four bespoke screens.

3. **The empty trade-finder result is FTF's eBay moment — the highest-value empty state in the app.** *Hypothesis:* "no mutual-gain trades found → save these players to your want board and we'll tell you when a match appears" beats both a bare empty state and a filter-relaxation tip, because a failed query is the exact moment a persistent-interest feature is legible.

4. **Never ship a "search tips" paragraph.** Baymard observed users rarely read them and that they can *be* the reason to leave. *Hypothesis:* the failing FTF empty state explains how the filters work; the winning one replaces the void with actionable content (near-miss trades, a board CTA, most-traded players at your thin position).

5. **Trigger predicate and delivery budget must be separate systems, and the budget must exist before the first trigger ships.** Aleven's 72% is the cautionary number. *Hypothesis:* FTF needs (a) a candidate-generation layer any feature can write to, and (b) one arbiter picking at most one candidate per session, scoring predicted-act minus predicted-annoy — LinkedIn ATC's shape minus the ML. Without (b), relevance-gating produces more noise than recency-gating did.

6. **If a tip must be pushed, render it as content, not chrome — and never on an idle timer.** HJR 0.93 vs 0.63 is the strongest number available on delivery form. *Hypothesis:* a tip rendered as a card *in the trade-suggestion list*, styled like a suggestion card, beats any anchored tooltip or toast; and FTF's declared boundaries (trade sent, vote submitted, board saved, results rendered, zero-result returned) outperform any dwell-time heuristic while requiring no modelling.

7. **Hard-cap tip copy at ~16–20 words and one action.** *Hypothesis:* any tip that can't compress to one line + one button belongs in the notification inbox — a pull surface with no reading budget — rather than shortened badly.

8. **Ship the retirement rule with the tip, and make it behavioral.** CHI 2012's help-on-demand harm and Aleven's help-abuse correlation are both damage from users who *engage*, so a dismiss button doesn't cover it. *Hypothesis:* `retire_after: N successful unaided uses` as a required field on every tip definition — with dismissal as a separate permanent cross-device override per Intercom's rule — prevents the expertise-reversal tax.

9. **The cross-feature bridge is the highest-upside, lowest-evidence idea here — ship it as an experiment.** "Trade sent → save your remaining targets to your want board" sits at a declared boundary with maximal adjacent relevance, the strongest available prior, but no controlled result for this pattern exists publicly. *Requirement:* flag + holdout — if FTF measures it, FTF will hold data that does not exist in public.

10. **Govern frequency by surface class, not by message.** *Hypothesis:* FTF can treat empty states, inbox entries, and inline cards as **budget-free**, spending the entire per-session budget on at most one pushed item — which, given 3-minute sessions, is likely one item per *several* sessions.

---

## Sources

**Peer-reviewed / controlled**
- Andersen, O'Rourke, Liu, Snider, Lowdermilk, Truong, Cooper & Popović, "The Impact of Tutorials on Games of Varying Complexity," CHI 2012 — https://grail.cs.washington.edu/projects/game-abtesting/chi2012/chi2012.pdf
- Aleven, McLaren, Roll & Koedinger, "Toward Tutoring Help Seeking: Applying Cognitive Modeling to Meta-cognitive Skills," ITS 2004 — https://www.cs.cmu.edu/~bmclaren/pubs/AlevenEtAl-HelpSeeking-ITS2004.pdf | https://link.springer.com/chapter/10.1007/978-3-540-30139-4_22
- Maniktala, Cody, Barnes & Chi, "Avoiding Help Avoidance: Using Interface Design Changes to Promote Unsolicited Hint Usage in an Intelligent Tutor," arXiv 2009.13371 — https://arxiv.org/abs/2009.13371
- Aleven, Roll, McLaren & Koedinger, "Help Helps, But Only So Much: Research on Help Seeking with Intelligent Tutoring Systems," IJAIED — https://link.springer.com/article/10.1007/s40593-015-0089-1
- Cao & Liu, "Learning to play: understanding in-game tutorials with a pilot study on implicit tutorials," Heliyon 2022 — https://pmc.ncbi.nlm.nih.gov/articles/PMC9676530/
- Baker, Corbett & Koedinger, "Detecting Student Misuse of Intelligent Tutoring Systems," ITS 2004 — http://pact.cs.cmu.edu/pubs/Baker,%20Corbett,%20Koedinger%20ITS04.pdf

**Behavioural research / usability benchmarks**
- Nielsen, "How Little Do Users Read?" (NN/G, 2008; Weinreich dataset) — https://www.nngroup.com/articles/how-little-do-users-read/
- NN/G, "Designing Empty States in Complex Applications: 3 Guidelines" — https://www.nngroup.com/articles/empty-state-interface-design/
- Baymard Institute, "5 Proven UX Strategies for 'No Results' Pages" — https://baymard.com/blog/no-results-page
- Baymard Institute, E-Commerce Search UX research studies — https://baymard.com/research/ecommerce-search
- Baymard Institute, research methodology — https://baymard.com/research/methodology

**Design-system documentation (normative)**
- Carbon Design System, Empty states pattern — https://carbondesignsystem.com/patterns/empty-states-pattern/
- PatternFly, Empty state design guidelines — https://www.patternfly.org/components/empty-state/design-guidelines/
- Atlassian Design System, Empty state — https://atlassian.design/components/empty-state
- Material Design 1, Empty states — https://m1.material.io/patterns/empty-states.html

**First-party engineering / product accounts**
- LinkedIn Engineering, "Air Traffic Controller: Member-First Notifications at LinkedIn" — https://www.linkedin.com/blog/engineering/messaging-notifications/air-traffic-controller-member-first-notifications-at-linkedin
- Duolingo, "Duolingo's Copy Testing Tool Perfects In-App Messaging" (14 Jan 2022) — https://blog.duolingo.com/copy-testing-experiments/
- Intercom, "Behind the messenger: the right kind of disruption" (27 Jul 2016) — https://www.intercom.com/blog/behind-messenger-right-kind-disruption/
- Intercom Help, "Automatically show Tooltips to the right customers" — https://www.intercom.com/help/en/articles/6475948-automatically-show-tooltips-to-the-right-customers
- Intercom Help, "Tooltips explained" — https://www.intercom.com/help/en/articles/6475940-tooltips-explained

**Patents (design intent, not evidence)**
- Sony Interactive Entertainment, "Assignment of contextual game play assistance to player reaction," US 10,610,783 — https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10610783
- Sony Interactive Entertainment, US 11,229,844 (continuation) — https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11229844

**Pattern collections and practitioner guidance (Tier 3–4)**
- UserOnboard, Onboarding UX Patterns — Empty States — https://www.useronboard.com/onboarding-ux-patterns/empty-states/
- Pencil & Paper, "Empty State UX Examples & Best Practices" — https://www.pencilandpaper.io/articles/empty-states
- Prefixbox, "No Results Page Examples" — https://www.prefixbox.com/blog/no-results-page-examples/
- UXmatters, "Starting from Zero: Winning Strategies for No Search Results Pages" — https://www.uxmatters.com/mt/archives/2009/02/starting-from-zero-winning-strategies-for-no-search-results-pages.php

**Vendor guidance and benchmarks (flagged — Tier 4 statistics)**
- Plotline, "Frequency Capping: What It Is, Why It Matters, and How to Get It Right for In-App Messaging" — https://www.plotline.so/blog/frequency-capping-in-app-messaging
- Chameleon, "Contextual In-App Guidance vs Product Tours" — https://www.chameleon.io/blog/contextual-in-app-guidance-vs-product-tours-guide
- Digia, "In-App Nudges: The Complete Guide for Mobile Growth Teams" — https://www.digia.tech/post/in-app-nudges-mobile-growth-guide/
- GuideNow / VividMinds, "How Does Contextual In-App Guidance Software Decide What to Show You?" — https://vividminds.ai/products/guidenow/blog/in-app-guidance-software-triggers
- Userpilot, "6 Interactive Walkthrough Examples From Successful Userpilot Customers" — https://userpilot.com/blog/interactive-walkthroughs-improve-onboarding/
- Userpilot, "Product Adoption Strategy in 2026" — https://userpilot.com/blog/product-adoption-strategy/
- Appcues, "26 Best User Onboarding Examples by Tactic" — https://www.appcues.com/blog/best-user-onboarding-examples
- AB Tasty, "Framing Effect: How It Affects UX Testing & Design Choices" — https://www.abtasty.com/blog/framing-effect-ux-testing/
