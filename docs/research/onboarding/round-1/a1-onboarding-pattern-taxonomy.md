# A1 — Taxonomy of Onboarding Patterns

**Date:** 2026-08-15
**Lens:** Pattern taxonomy only. What each onboarding pattern *is*, when it works, when it fails, what the published evidence actually shows, and the known anti-patterns. Competitive teardowns, FTF-specific flows, and metrics design are other lenses.

---

## TL;DR

- **The strongest experimental evidence is anti-tutorial for simple products and pro-tutorial for complex ones.** NN/g's 70-user, 4-app quantitative test found deck-of-cards tutorials produced *no* significant gain in task success (91% with vs 94% without, p=0.443) and made tasks feel **harder** (SEQ 4.92 vs 5.49, p=0.047). But a 45,000-player, 3-game, 8-design multivariate study found tutorials raised play time by **up to 29% in the most complex game** while doing nothing measurable in the two simpler ones. Complexity is the moderator, not "tutorials good/bad."
- **Context beats sequence.** The same 45k-player study found *context-sensitivity* (teaching a thing next to the thing) improved engagement, while *freedom* (skippability) had no measurable effect on behavior. Two lab studies of in-context guidance show large effects: Stencils-based tutorials → **26% faster** completion with fewer errors; ToolClips (contextual video in tooltips) → users completed **7× as many unfamiliar tasks** as with a commercial help system.
- **"Learn by doing" isn't automatically better — it trades helpfulness for engagement.** A 47-participant game study found implicit (embedded) tutorials were rated 0.6 points *less boring* but 0.69 points *less helpful* than explicit ones, and the benefit concentrated in **experienced** users. Novices got the least from implicitness.
- **Checklists are the best-evidenced motivational device and the worst-performing in the field.** The endowed-progress effect is a real randomized field experiment (n=300; 34% vs 19% completion). But the largest available field benchmark — 188 SaaS companies — puts mean checklist completion at **19.2%** and *median at 10.1%*. Abandonment is the norm, not the exception.
- **Gate placement is often a bigger lever than any teaching pattern.** Duolingo's delayed sign-up test moved DAUs ~20%; a single soft-wall button copy change contributed 8.2%. The `$300M button` post-mortem: replacing "Register" with "Continue" lifted sales 45%. Removing a *requirement* consistently outperforms explaining one.
- **Empty states and templates are onboarding disguised as product.** NN/g's three empty-state guidelines (communicate status, provide learning cues, provide direct pathways) put the teaching where the user already is — no dismissal cost, no memory tax, no tour to blind out.
- **Platform guidance (Apple HIG) is unambiguous and rarely followed:** avoid splash/instruction screens, make tutorials skippable and never re-show them, "education isn't a substitute for great app design," teach "gradually and in context."
- **Most quantified onboarding "benchmarks" circulating in 2026 are vendor-authored and often circular** (one vendor blog citing another vendor blog). Treat the ~19% checklist median, the "3-step tours complete at 72% / 7-step at 16%" claim, and "personalized onboarding lifts retention 40%" as directional-at-best. Flagged individually below.

---

## 1. Front-loaded intro carousels ("deck-of-cards" tutorials, value-prop swipes)

**What it is.** A 2–5 screen swipeable sequence shown before first use, mixing feature promotion, brand narrative, and instructions. NN/g classifies mobile onboarding content into three components: *feature promotion*, *customization*, and *instructions* — carousels usually blend all three ([NN/g, Mobile-App Onboarding](https://www.nngroup.com/articles/mobile-app-onboarding/)).

**Evidence.** This is the one pattern with a clean, published, controlled test against a no-onboarding baseline. NN/g ran a between-subjects remote unmoderated quantitative study: **70 participants, 35 per group, 4 iPhone apps**, tasks chosen to be exactly what the tutorials taught ([NN/g, Mobile Tutorials](https://www.nngroup.com/articles/mobile-tutorials/)):

| Measure | Saw tutorial | Skipped tutorial | Significance |
|---|---|---|---|
| Task success | 91% | 94% | p = 0.443 (n.s.) |
| Perceived difficulty (SEQ, 1–7) | 4.92 | 5.49 | **p = 0.047** |
| Completion time | 93.49 s | 85.17 s | p > 0.1 (n.s.) |

The direction on perceived difficulty is the notable result: seeing the tutorial made the app feel *harder*. NN/g's conclusion: tutorials "don't make users faster or more successful… on the contrary, they make them perceive the tasks as more difficult."

**When it works.** Rarely for teaching. Defensible when (a) the app's value proposition is genuinely non-obvious pre-signup and the carousel is doing *marketing*, not instruction; (b) legal/permission context must be set; (c) the app diverges hard from platform conventions. NN/g's own escape hatches: onboarding is justified when information is *needed* to start, when functionality requires high personalization, or when features are genuinely novel.

**When it fails / anti-patterns.**
- **Instruction without application.** Content is presented out of context; users must memorize and later recall. Working memory "fades in about 20 seconds" ([NN/g, Instructional Overlays](https://www.nngroup.com/articles/mobile-instructional-overlay/)).
- **Dismissal tax.** Every screen is friction between the user and the thing they opened the app to do — the *paradox of the active user* (Carroll & Rosson, 1987): users "never read manuals but start using the software immediately," and are motivated by the immediate task, not system mastery ([NN/g summary](https://www.nngroup.com/articles/paradox-of-the-active-user/); [Carroll & Rosson PDF](https://research.cs.vt.edu/ns/cs5724papers/4.mental.mental.carroll.paradox.pdf)).
- **Apple HIG explicitly discourages it:** "Avoid showing a splash screen, menus, and instructions that make it take longer to reach content," and if tutorials exist, make them skippable and don't show them to returning users ([Apple HIG, First Launch / Onboarding](https://developer.apple.com/design/human-interface-guidelines/onboarding)).

---

## 2. Product tours (auto-launched sequential tooltips/modals inside the UI)

**What it is.** A chained sequence of in-app callouts fired on first entry to a screen, with next/back/skip. NN/g's framing: this is a **push revelation** — surfaced "without any specific indication that the user would benefit from the information *at that moment*" ([NN/g, Onboarding Tutorials vs. Contextual Help](https://www.nngroup.com/articles/onboarding-tutorials/)).

**Evidence.** No high-quality independent controlled study of tours-vs-no-tour exists that I could find; the tour evidence base is dominated by tool vendors with an obvious incentive. The most useful *directional* vendor data (flagged: Chameleon sells tour software) claims the **top 1% of tours reach 61% completion**, that completion "nosedives after five steps," that **self-triggered tours see 2–3× the engagement of forced ones**, and that progress indicators add ~12% completion ([Chameleon](https://www.chameleon.io/blog/product-tours-still-work)). A widely-repeated stat that 3-step tours complete at 72% and 7-step at 16% appears in secondary write-ups with **no traceable primary source** — do not treat it as data.

The nearest thing to a controlled result is the game study's finding that *tutorial freedom* (whether players could skip) "did not affect player behavior" — i.e., making a tour skippable neither rescued nor harmed it ([Andersen et al., CHI 2012](https://grail.cs.washington.edu/projects/game-abtesting/chi2012/chi2012.pdf)).

**When it works.** Short (≤3–5 steps), user-*triggered* rather than auto-fired, scoped to one screen or one job, and re-findable later. NN/g: make help easy to dismiss **and to recall**.

**When it fails / anti-patterns.**
- **Tour blindness.** Users learn the shape of the overlay and reflexively dismiss it; NN/g observes users "dismiss hints more quickly" when bombarded with chains.
- **Chains of tips make the app look harder** — "multiple tips can make apps appear overly complicated and daunting."
- **Overlay/UI confusion.** In an NN/g tablet study of the Wimbledon app, users tried to *interact with* polished-looking tutorial overlays, mistaking annotation for interface.
- **Tour as documentation dumping ground** — the "20-step modal marathon," where every team that ships a feature appends a step (vendor-acknowledged failure mode, Chameleon; also the core critique in Intercom's own Product Tours retrospective, [Intercom](https://www.intercom.com/blog/podcasts/behind-the-scenes-product-tours/)).
- **The tour as a substitute for IA work.** NN/g's blunt guidance: "Avoid creating app onboarding whenever possible and instead spend your resources making the UI more usable" — and *test the app without onboarding first* to find where users actually stumble.

---

## 3. Coach marks / instructional overlays (single-shot)

**What it is.** A dimmed scrim with arrows/labels pointing at controls, usually one-shot on first view.

**Evidence.** Thin and inconclusive. A published study ("Effectiveness of Coach Marks or Instructional Overlay in Smartphone Apps Interfaces," HCII 2019) used a between-subjects design measuring completion time on a prototype flow and found a *tendency* toward faster completion with overlays, but the sample was too small to reach significance — the authors call for a larger study ([Springer](https://link.springer.com/chapter/10.1007/978-3-030-20227-9_7)). That is the honest state of the art: a non-significant trend.

**When it works.** For a *single* genuinely non-obvious gesture or affordance ("swipe left to compare"), delivered once, visually distinct from the UI (NN/g suggests hand-drawn styling so users don't mistake it for chrome), visual rather than textual.

**When it fails.** The structural flaw NN/g names: "users cannot read the hint overlay and use the app at the same time," so overlays convert doing into memorizing. Chained coach marks inherit every tour failure mode plus a full-screen block.

---

## 4. Interactive walkthroughs / guided tasks (learn by doing)

**What it is.** The user performs the real task on real (or realistic) data while the system constrains, prompts, and confirms. Distinguished from a tour by *the user acting*, not reading.

**Evidence — this is where the large effects are.**
- **Stencils-based tutorials** (Kelleher & Pausch, CHI 2005): translucent stencils with holes that expose only the correct control, with sticky-note instructions in situ. Versus a paper tutorial for the same task in Alice: **26% faster completion, fewer errors, less reliance on human help** ([ACM](https://dl.acm.org/doi/abs/10.1145/1054972.1055047)).
- **ToolClips** (Grossman & Fitzmaurice, CHI 2010): tooltips augmented with short contextual video/text. Users "successfully completed 7 times as many unfamiliar tasks" compared with a commercial, professionally-developed online help system ([ACM PDF](https://dl.acm.org/doi/pdf/10.1145/1753326.1753552); [Autodesk Research](https://www.research.autodesk.com/publications/toolclips-an-investigation-of-contextual-video-assistance-for-functionality-understanding/)).
- **Context-sensitivity** was the dimension that mattered in the 45,000-player game study — "grouping tutorials with what they teach enhances tutorials' efficiency."

**The important caveat against naive "learn by doing."** A pilot study (n=47; 26 implicit / 21 explicit) on a runner game found implicit, embedded-in-play tutorials were rated **0.6 points less boring but 0.69 points less helpful** than explicit ones, with the effect largest for medium-experience players and smallest for inexperienced ones ([Heliyon 2022](https://pmc.ncbi.nlm.nih.gov/articles/PMC9676530/)). So: doing beats reading for *engagement and speed*, but pure implicitness can under-teach precisely the novices who need teaching. The practical read is *guided doing* — action plus a minimal explicit cue — not action alone.

**When it fails.**
- **Fake sandboxes.** Walkthroughs on dummy data that the user then has to redo for real double the work.
- **Rails that don't survive divergence.** If the user taps anything unplanned and the walkthrough breaks or nags, it becomes a tour with extra steps.
- **Over-guidance.** Krystal Higgins' "optimal onboarding zone" names the left-hand failure: onboarding so hand-holding that users become passive observers — her example is a game where "instructional overlays popped up every few seconds," preventing engagement ([kryshiggins.com](https://www.kryshiggins.com/optimal-onboarding-zone/)).

---

## 5. Contextual / on-demand help ("pull revelations")

**What it is.** Help that appears because the user asked, or because a real behavioral signal says they're stuck: hover tooltips, "?" affordances, inline definitions, first-use-of-*this*-feature hints.

**Evidence.** NN/g's push/pull distinction is the cleanest available framework: pull revelations avoid interruption, avoid memorization, and are "more memorable" because "in-context help can often be applied right away." The ToolClips 7× result is a pull-help result. One caution from the game study: **on-demand help both "harmed and helped player retention"** depending on the game — availability is not free; an always-visible help affordance can itself signal complexity.

**Guidelines with the most support.** Easy to dismiss *and* easy to recall; progressive disclosure inside the help itself; never require memorization (show help beside each step); skip explaining platform conventions.

---

## 6. Setup checklists

**What it is.** A persistent list of 3–7 activation tasks, usually with a progress bar, often with one item pre-completed.

**Evidence for the mechanism (strong, primary, but from a different domain).** The **endowed progress effect** — Nunes & Drèze (2006, *Journal of Consumer Research*): 300 car-wash customers randomized to an 8-stamp card or a 10-stamp card with 2 stamps pre-given (both requiring 8 more washes). Redemption: **34% vs 19%**, and the endowed group returned faster. This is a genuine randomized field experiment and is the strongest thing behind "pre-check step one." The Zeigarnik effect (tension from unfinished tasks) is cited constantly in this context but almost never with a product-specific test attached — treat it as plausible mechanism, not evidence.

**Evidence for the outcome (field, vendor-sourced, sobering).** Userpilot's benchmark across **188 SaaS companies** (published 2024, from their own platform's telemetry): **mean checklist completion 19.2%, median 10.1%**; by industry, FinTech/Insurance highest at 24.5% and MarTech lowest at 12.5%; sales-led 22.1% vs product-led 19% ([Userpilot benchmark](https://userpilot.medium.com/customer-onboarding-checklist-completion-rate-2024-benchmark-report-8ebabebefb1f)). Vendor first-party data with obvious selection bias (only Userpilot customers, only companies that built a checklist), but it's the largest N available and it points one way: **most checklists are abandoned.**

**When it works.** Short (3–5 items), each item a real value-producing action rather than a configuration chore, ordered so item 1 is already done, dismissible-but-recoverable, and — per Higgins' evaluation method — judged on downstream retention rather than on its own completion rate ([kryshiggins.com](https://www.kryshiggins.com/evaluating-your-new-user-experience/)).

**Anti-patterns.**
- **Checklist as chore list.** Items like "complete your profile" or "invite a teammate" serve the company, not the user; they train dismissal.
- **The dense checklist on an unfamiliar page.** Higgins names Notion's "Getting Started" page as the right-hand failure of the optimal zone: a long checklist on a structure the newcomer doesn't yet understand.
- **Optimizing completion rate as the goal.** A checklist can be completed by users who then churn; the metric to chase is the correlation between *step-level* progress and retention, not completion.

---

## 7. Wizards / multi-step setup

**What it is.** A linear, chunked flow for one complex task (account setup, league import, preference capture), with a progress indicator and one decision per screen. A specialized application of **progressive disclosure** (Nielsen, 1995): show a few important options first, defer the rest ([NN/g](https://www.nngroup.com/articles/progressive-disclosure/)).

**Evidence.** Honest assessment: **weaker than its reputation.** Nielsen's progressive-disclosure article argues learnability/efficiency/error benefits but cites *no controlled data*. The much-quoted "multi-step forms convert 86%/59%/300% better" figures trace to marketing-tool vendors (HubSpot, Venture Harbour, Instapage, Conversion Fanatics) and are reported without sample sizes or methodology; even a form-analytics vendor summarizing them concedes "the exact quantum of performance improvement varies" and that single-page forms are better below ~5 fields ([Zuko](https://www.zuko.io/blog/single-page-or-multi-step-form)). Publication bias here is extreme — nobody blogs the multi-step test that lost.

**When it works.** Genuinely complex, one-time, mandatory setup where the alternative is a wall of fields; where each step's answer *changes* subsequent steps; where progress is visible and back-navigation is cheap.

**When it fails.** Nielsen's named failure conditions: more than two levels of disclosure; interdependent steps requiring back-and-forth; illogical grouping. Product-side: wizards that gather preferences the product then ignores (a specific critique in the Blinkist teardown — asking preference questions and then not using them, [Growth.Design](https://growth.design/case-studies/blinkist-user-onboarding)), and wizards placed *before* any value is delivered.

---

## 8. Empty states as onboarding

**What it is.** The zero-data screen does the teaching: it explains the container, shows what will live there, and offers the action that fills it.

**Evidence/guidance.** NN/g's three guidelines ([Designing Empty States](https://www.nngroup.com/articles/empty-state-interface-design/)):
1. **Communicate system status** — "Totally empty states cause confusion about how and whether the system is working." Users otherwise re-run queries and refresh.
2. **Provide learning cues** — e.g. "Star your favorites to list them here"; "in-context help can often be applied right away and is thus more memorable."
3. **Provide direct pathways to key tasks** — their Loggly example offers both "add a log source" and "explore demo data" as clickable options.

This is guideline-grade evidence (expert review + illustrative usability observations), not experimental — but it is structurally the cheapest pattern to get right: no interruption, no dismissal, no memory tax, and it can't be blinded out because it *is* the screen.

**When it fails.** Decorative illustration with no next action; an empty state that explains the feature but not why this user should care; empty states that never expire (still showing beginner copy to a power user whose data is legitimately empty).

---

## 9. Template / sample-data starts

**What it is.** Instead of a blank canvas, the user lands in a pre-populated artifact — a template, a demo dataset, or a personalized starting configuration derived from a single intent question.

**Evidence.** Mostly **received wisdom plus convergent practice**, not published experiments. Notion, Airtable, and Figma all route new users via a "what do you want to make?" question into a pre-filled workspace; the widely-repeated claim is that templates are the highest-leverage investment where the empty state is the main drop-off. I could not find a primary A/B write-up for this; the sources are practitioner/vendor round-ups. The nearest formal support is NN/g's empty-state guideline #3 (offering demo data as a first-class path) and the general context-sensitivity result from the game study.

**When it works.** When the blank state is genuinely paralysing; when a template shows the *shape* of a good outcome; when sample data is clearly labelled and one tap from being replaced by real data.

**When it fails.** Sample data indistinguishable from real data (users act on fake numbers — a serious risk in any product where numbers imply decisions); templates that must be laboriously un-done; intent questions whose answers don't visibly change anything (the Blinkist critique above).

---

## 10. Video and animated intros

**What it is.** A short video or looping animation explaining the product or a feature.

**Evidence.** The only strong result is for **short, contextual, in-place video**: ToolClips' 7× improvement came from ~10–25 second clips reachable from the tooltip of the control in question. Intercom added video to Product Tours late and found it "compelling for engagement" (practitioner claim, no numbers). Full-screen intro videos at first launch inherit every carousel problem plus a longer dismissal cost, and fall directly under Apple's "avoid… instructions that make it take longer to reach content."

**Read:** video's evidence supports *micro*, *pull*, *contextual* — not *intro reel*.

---

## 11. Personalization / intent surveys as onboarding

**What it is.** 1–3 questions at start ("what are you here to do?") that route the user into a tailored first-run path.

**Evidence.** Weak and heavily vendor-contaminated. Claims like "personalized onboarding increases retention by 40%" appear across vendor blogs with no traceable study. NN/g's position is narrower and more defensible: customization is one of the three legitimate reasons to have onboarding at all, and "prioritize content customization over visual design customization." The credible mechanism is *routing* (fewer irrelevant steps downstream), not personalization-as-delight.

**Anti-pattern.** Asking, then not using. Also: demographic questions (which serve the company) dressed as intent questions (which serve the user).

---

## 12. Gate placement: deferred sign-up / value-before-account

Not usually catalogued as an "onboarding pattern," but on the published evidence it is the **highest-leverage one**, because it removes a step rather than explaining it.

- **Duolingo** (via First Round Review's interview with their growth lead): letting users complete lessons before prompting sign-up produced roughly a **20% increase in DAUs**; a follow-on soft-wall change (relabelling "Discard my progress" to "Later") contributed **8.2%**. For calibration on their testing discipline: their ship threshold is a **1%** metric improvement, they cap experiments at **three arms**, and they treat ~100k DAU as the floor for meaningful A/B testing ([First Round Review](https://review.firstround.com/the-tenets-of-a-b-testing-from-duolingos-master-growth-hacker/)).
- **The `$300M button`** (Jared Spool / UIE): on a major e-commerce checkout, replacing "Register" with "Continue" plus a note that registration was optional lifted sales **45%**, ~$15M in month one, ~$300M in year one. Notably, the usability study also found 45% of users had multiple registrations — the gate was failing returning users too ([UIE archive](https://archive.uie.com/brainsparks/2015/10/21/uie-article-the-300-million-button/)).

Higgins' Spotify example runs the same direction: free exploration with gradual coaching toward sign-up, rather than a wall.

---

## Cross-cutting anti-patterns

| Anti-pattern | Why it happens | Evidence/authority |
|---|---|---|
| **Tour/tooltip blindness** | Repeated push revelations train reflexive dismissal | NN/g: users "dismiss hints more quickly" when bombarded |
| **Checklist abandonment** | Items serve the company; too many; shown before context exists | 19.2% mean / 10.1% median across 188 companies (Userpilot) |
| **Memorize-then-apply** | Instruction separated from the moment of use | NN/g overlays: STM "fades in about 20 seconds" |
| **Onboarding as IA patch** | Cheaper to explain a confusing screen than fix it | NN/g: "Avoid creating app onboarding whenever possible"; test without onboarding first |
| **Front-loading everything** | Every team wants their feature in the first-run flow | Andersen et al.: context-sensitivity is what pays, not coverage |
| **Perceived-difficulty backfire** | Explaining a thing signals the thing is hard | NN/g: tutorial group rated tasks significantly harder (p=0.047) |
| **Skippability as absolution** | "It's fine, they can skip it" | Andersen et al.: tutorial *freedom* had no measurable behavioural effect |
| **Optimizing the onboarding metric** | Completion rate is easy to move and easy to fake | Higgins: teams "measure onboarding myopically, like a feature in isolation" |
| **Correlation-as-activation** | "Users who did X retain, so make everyone do X" | The Facebook "7 friends in 10 days" critique — a memorable average, not a validated causal threshold ([Mode](https://mode.com/blog/facebook-aha-moment-simpler-than-you-think/)) |

---

## Evidence quality notes

**Tier 1 — controlled experiments with published methods and N.**
NN/g mobile tutorials (n=70, between-subjects, 4 apps, p-values reported). Andersen et al. CHI 2012 (~45,000 players, 3 games, 8 tutorial designs, multivariate). Kelleher & Pausch CHI 2005 (Stencils, 26%). Grossman & Fitzmaurice CHI 2010 (ToolClips, 7×). Nunes & Drèze 2006 (endowed progress, n=300 field randomization). Heliyon 2022 implicit tutorials (n=47 — small, but pre-registered design and reported effect sizes).
*Caveats:* the game studies generalize to "complex, unconventional, voluntary-use software," which is arguably the right reference class for a dynasty trade tool, but they are games. NN/g's n=70 is adequately powered only for large effects — its **null** results are weaker than its significant one.

**Tier 2 — expert-review guidance from a credible independent lab.** NN/g's empty-state, instructional-overlay, onboarding-tutorials, mobile-app-onboarding and progressive-disclosure articles; Apple HIG. These are heuristic, illustrated with usability observations, not experiments. Nielsen's progressive-disclosure piece in particular cites **no data at all** — its authority is reputational.

**Tier 3 — practitioner accounts with real numbers but unpublished methods.** Duolingo via First Round; Spool's $300M button (usability study behind it never published in full); Intercom's Product Tours retrospective. Directionally valuable, unreplicable, survivorship-biased (nobody writes up the redesign that lost).

**Tier 4 — vendor first-party telemetry.** Userpilot's 188-company checklist benchmark (best-in-class of this tier: N and method stated, selection bias obvious). Chameleon's tour completion figures (no N, no method, sells tours). Appcues' pattern taxonomy (useful vocabulary; its own quantitative claims mostly lack source attribution — the article's only sourced number is a Clutch survey of 501 mobile users).

**Tier 5 — do not cite as evidence.** The "3-step tours complete at 72%, 7-step at 16%" pair, "personalized onboarding increases retention 40%," "good onboarding increases retention 82%," "gamified onboarding lifts activation 30–50%." Tracing these leads to vendor blogs citing vendor blogs — one aggregation I checked attributed the gamification figure to a marketing site via a second marketing site, with no study underneath.

**Known gaps in this round.** I could not find: (a) any independent RCT of product tours vs no tours in a real SaaS/consumer app; (b) primary A/B evidence for template/sample-data starts; (c) published onboarding experiments from sports/fantasy apps specifically; (d) a peer-reviewed replication of the coach-marks study (the existing one is explicitly underpowered). Session web-search budget was exhausted before I could chase GDC tutorial post-mortems and Baymard's registration research; those are the two highest-value follow-ups.

---

## Implications for FTF (hypotheses only)

These are hypotheses generated by the evidence, not recommendations. Each is stated so it could be falsified.

1. **FTF is in the complexity band where teaching pays.** Elo-from-matchup-votes, tier ladders, want/accept boards, and mutual-gain discovery are unconventional mechanics — closer to the CHI 2012 "most complex game" (+29% play time from tutorials) than to the four simple iPhone apps where NN/g found tutorials useless. *Hypothesis: instructional support will show measurable effect in FTF where it would not in a simpler app — but only if it is context-sensitive, not front-loaded.*
2. **Context-sensitivity is likely the dominant design variable, and skippability is likely irrelevant.** *Hypothesis: moving the same explanatory content from a first-run sequence to the moment-of-first-use of each feature changes activation; adding or removing a "Skip" affordance does not.*
3. **The three-player matchup vote is a natural "guided doing" surface.** It is a real task, self-explaining through action, and it produces the data the rest of the product needs. *Hypothesis: a first session structured as "do a few matchups, then see your board" outperforms any explanation of what Elo is.* Counter-hypothesis from the Heliyon result: pure implicitness may under-teach *why* the votes matter, so a minimal explicit cue may be needed alongside the doing.
4. **Every screen with a zero state is an untapped onboarding surface.** Empty want/accept boards, an empty notification inbox, an empty trade-finder result set, and a not-yet-linked second platform each qualify. *Hypothesis: empty-state teaching (status + cue + direct action) will outperform an equivalent amount of tour content, and cannot be blinded out.*
5. **Sample/demo data carries unusual risk here.** In a product whose output is a *valuation judgement*, fake players or fake trade values could be acted on. *Hypothesis: template starts help in FTF only if the "sample" is the user's own real Sleeper roster — i.e. the import *is* the template.*
6. **Gate placement may dominate teaching entirely.** Sleeper sign-in is currently the first wall. The Duolingo and $300M-button results both say value-before-account beats explaining-the-account. *Hypothesis: allowing meaningful use (a manual calculator run, a handful of matchup votes) before requiring Sleeper linkage moves activation more than any tour, tutorial, or checklist variant.*
7. **If a checklist ships, expect ~10–20% completion and design for the abandoners.** *Hypothesis: the value of an FTF checklist lies in step-1-and-2 completion correlating with week-2 retention, not in full completion; and pre-completing item one (the Sleeper link, already done at signup) should lift subsequent steps per the endowed-progress result.*
8. **Feature density argues for progressive *reveal*, not progressive *explanation*.** *Hypothesis: gating advanced surfaces (send-in-platform, MFL/ESPN linkage, want/accept boards) behind demonstrated use of the core loop reduces first-session overwhelm more than any amount of in-place guidance on a fully-exposed UI.*
9. **Measurement framing matters more than pattern choice.** Higgins' longitudinal frame (d1–7, 7–14, 14–30, 30–90 retention curves; compare successful vs churned cohorts) plus the Facebook correlation/causation caution suggest FTF should validate any "aha" candidate (first trade sent? Nth matchup vote?) by *pushing* users toward it and checking whether retention follows.

---

## Sources

**Peer-reviewed / academic**
- Andersen, O'Rourke, Liu, et al. — *The Impact of Tutorials on Games of Varying Complexity*, CHI 2012 — https://grail.cs.washington.edu/projects/game-abtesting/chi2012/chi2012.pdf · https://dl.acm.org/doi/abs/10.1145/2207676.2207687
- Kelleher & Pausch — *Stencils-based tutorials: design and evaluation*, CHI 2005 — https://dl.acm.org/doi/abs/10.1145/1054972.1055047
- Grossman & Fitzmaurice — *ToolClips: An investigation of contextual video assistance for functionality understanding*, CHI 2010 — https://dl.acm.org/doi/pdf/10.1145/1753326.1753552 · https://www.research.autodesk.com/publications/toolclips-an-investigation-of-contextual-video-assistance-for-functionality-understanding/
- Carroll & Rosson — *Paradox of the Active User* (1987) — https://research.cs.vt.edu/ns/cs5724papers/4.mental.mental.carroll.paradox.pdf
- Nunes & Drèze — *The Endowed Progress Effect* (JCR, 2006), summarized with method and results — https://www.coglode.com/nuggets/endowed-progress-effect
- *Learning to play: understanding in-game tutorials with a pilot study on implicit tutorials*, Heliyon 2022 — https://pmc.ncbi.nlm.nih.gov/articles/PMC9676530/
- *Effectiveness of Coach Marks or Instructional Overlay in Smartphone Apps Interfaces*, HCII 2019 — https://link.springer.com/chapter/10.1007/978-3-030-20227-9_7

**Independent research labs / platform authorities**
- NN/g — *Mobile Tutorials: Wasted Effort or Efficiency Boost?* — https://www.nngroup.com/articles/mobile-tutorials/
- NN/g — *Onboarding Tutorials vs. Contextual Help* — https://www.nngroup.com/articles/onboarding-tutorials/
- NN/g — *Mobile-App Onboarding: An Analysis of Components and Techniques* — https://www.nngroup.com/articles/mobile-app-onboarding/
- NN/g — *Instructional Overlays and Coach Marks for Mobile Apps* — https://www.nngroup.com/articles/mobile-instructional-overlay/
- NN/g — *Designing Empty States in Complex Applications: 3 Guidelines* — https://www.nngroup.com/articles/empty-state-interface-design/
- NN/g — *Progressive Disclosure* — https://www.nngroup.com/articles/progressive-disclosure/
- NN/g — *Paradox of the Active User* — https://www.nngroup.com/articles/paradox-of-the-active-user/
- NN/g — *Onboarding: Skip it When Possible* (video) — https://www.nngroup.com/videos/onboarding-skip-it-when-possible/
- Apple — *Human Interface Guidelines: Onboarding* — https://developer.apple.com/design/human-interface-guidelines/onboarding · *Launching* — https://developer.apple.com/design/human-interface-guidelines/launching · archived iOS HIG *First Launch Experience* — https://codershigh.github.io/guidelines/ios/human-interface-guidelines/interaction/first-launch-experience/index.html

**Practitioner (numbers real, methods unpublished)**
- First Round Review — *The Tenets of A/B Testing from Duolingo's Master Growth Hacker* — https://review.firstround.com/the-tenets-of-a-b-testing-from-duolingos-master-growth-hacker/
- Jared Spool / UIE — *The $300 Million Button* — https://archive.uie.com/brainsparks/2015/10/21/uie-article-the-300-million-button/ · https://articles.centercentre.com/three_hund_million_button/
- Krystal Higgins — *The optimal user onboarding zone* — https://www.kryshiggins.com/optimal-onboarding-zone/ · *Evaluating your new user experience* — https://www.kryshiggins.com/evaluating-your-new-user-experience/ · *Better Onboarding* (A Book Apart, 2021) — https://abookapart.com/blogs/press/new-better-onboarding-by-krystal-higgins.html
- Intercom — *A behind-the-scenes look at building Product Tours* — https://www.intercom.com/blog/podcasts/behind-the-scenes-product-tours/
- Mode — *Facebook's "Aha" Moment Was Simpler Than You Think* — https://mode.com/blog/facebook-aha-moment-simpler-than-you-think/
- Geckoboard — *How Facebook's "7 friends in 10 days" got everyone confused about correlation and causation* — https://medium.com/geckoboard-under-the-hood/how-facebooks-7-friends-in-10-days-got-everyone-confused-about-correlation-and-causation-25da4bb8220e
- Growth.Design — *Blinkist user onboarding* teardown (opinionated; "Psych" framework is proprietary, not academic) — https://growth.design/case-studies/blinkist-user-onboarding

**Vendor sources — bias flagged**
- Userpilot (onboarding-tooling vendor; first-party telemetry, N and method stated) — *Customer Onboarding Checklist Completion Rate: 2024 Benchmark Report*, 188 SaaS companies — https://userpilot.medium.com/customer-onboarding-checklist-completion-rate-2024-benchmark-report-8ebabebefb1f · 2025 update — https://userpilot.com/blog/onboarding-checklist-completion-rate-benchmarks/
- Chameleon (sells product tours; no N or method given) — *Yes, product tours still work* — https://www.chameleon.io/blog/product-tours-still-work
- Appcues (sells onboarding tooling; useful taxonomy, weak sourcing) — *The essential guide to mobile user onboarding* — https://www.appcues.com/blog/essential-guide-mobile-user-onboarding-ui-ux
- Zuko (form analytics; summarizes third-party multi-step form claims and concedes their variability) — https://www.zuko.io/blog/single-page-or-multi-step-form
- Venture Harbour (form-builder vendor; multi-step conversion claims) — https://ventureharbour.com/form-ab-test-ideas-backed-by-ux-research/
