# A2 — Time-to-Value & Activation Science

> **Date:** 2026-08-15
> **Lens:** How teams empirically identify an activation event / "aha moment", how activation metrics are designed and validated, what the evidence says about minimizing steps to first value, deferred signup, and the tradeoff between front-loading personalization data and front-loading value.
> **Scope:** Research only. Hypotheses at the end, no implementation prescriptions.

---

## TL;DR

- **The famous "magic numbers" are stories, not science.** Facebook's "7 friends in 10 days" and Slack's "2,000 messages" were never presented by their authors as statistically derived thresholds; both Mixpanel and Mode argue publicly that these are round numbers picked from the middle of a range, valuable for team alignment rather than precision ([Mixpanel](https://mixpanel.com/blog/magic-numbers-are-an-illusion/), [Mode](https://mode.com/blog/facebook-aha-moment-simpler-than-you-think/)). Slack's own founder describes 2,000 as a judgement call: "we decided that any team that has exchanged 2,000 messages… has tried Slack" ([GrowthHackers case study](https://growthhackers.com/growth-studies/slack/)).
- **The standard method for finding an aha moment is correlational, and correlation is the wrong tool.** Every credible practitioner source — Lenny Rachitsky, Reforge, GoPractice, Kissmetrics — describes the same three-step recipe (candidate milestones → correlation/regression against retention → *experiment to prove causality*), and every one of them flags that most teams stop after step two ([Lenny](https://www.lennysnewsletter.com/p/how-to-determine-your-activation)).
- **The most common activation-metric design error is a milestone that is "necessary but not sufficient"** — something a user must do, but which doesn't itself deliver value (e.g. "connected an account"). If a user could complete it and immediately churn, it's the wrong milestone ([Lenny](https://www.lennysnewsletter.com/p/what-is-a-good-activation-rate)).
- **Deferred signup has the single strongest published evidence in this area.** Duolingo's VP of Growth reports that moving the signup screen back a few steps produced a **~20% DAU increase**, and that a soft-wall-then-hard-wall sequence added **8.2% DAU** — with neither wall type performing as well in isolation ([First Round Review](https://review.firstround.com/the-tenets-of-a-b-testing-from-duolingos-master-growth-hacker/)).
- **Forced account creation is measurably expensive in the one domain with rigorous survey data:** Baymard finds **24% of US shoppers abandoned a cart in the last quarter *solely* because of forced account creation** (n=4,384, 2022) ([Baymard](https://baymard.com/blog/make-guest-checkout-prominent)).
- **Instructional onboarding does not help task performance.** NN/g's quantitative test (70 users, 4 iOS apps) found tutorial-viewers succeeded at 91% vs 94% for skippers (n.s., p=0.443) and rated the tasks *harder* (4.92 vs 5.49 on SEQ, p=0.047) ([NN/g](https://www.nngroup.com/articles/mobile-tutorials/)).
- **"Every extra step costs X%" is received wisdom, not evidence.** The widely circulated per-step onboarding drop-off benchmarks trace back to vendor blogs with no disclosed sample, dates, or methodology — I verified this directly on the source page ([UXCam](https://uxcam.com/blog/drop-off-rates/)).
- **There is a real counter-case: some of the highest-converting consumer funnels are 90–113 screens long.** Noom's web-to-app onboarding runs to ~113 screens / 10–15 minutes and is credited by teardowns with building commitment before the paywall ([RevenueCat](https://www.revenuecat.com/blog/growth/web-to-app-onboarding-funnel), [retention.blog](https://www.retention.blog/p/the-longest-onboarding-ever)). Crucially, that evidence is about *monetization of paid traffic*, not about retention of organic users — a distinction the popular write-ups collapse.

---

## 1. Definitional layer: activation ≠ onboarding ≠ time-to-value

The dominant vocabulary comes from Reforge (Brian Balfour / Casey Winters), which decomposes activation into three sequential moments:

- **Setup moment** — the user has supplied the information and completed the actions that give them a *high probability* of experiencing the value prop. It is a precondition, not value itself ([Reforge](https://www.reforge.com/guides/define-your-setup-moment)).
- **Aha moment** — the user first *experiences* the core value.
- **Habit moment** — the user establishes a recurring behaviour around that value.

GoPractice frames activation more broadly still: "the entire journey — from the first time someone hears about your product… to the moment they experience its value" ([GoPractice](https://gopractice.io/product/designing-activation-in-reverse/)). That framing matters because it puts store listing, first-run, and empty states inside the same funnel rather than treating "onboarding" as a screen sequence.

**Time-to-value (TTV)** is the elapsed-time version of the same idea, and the literature separates *time to first value* (any payoff, however small) from *time to value* (the full outcome the user came for). The recommended aggregation is the **median, not the mean**, since a long tail of stalled users distorts the average ([Valuecase](https://www.valuecase.com/articles/what-is-time-to-value)). One vendor benchmark (Userpilot, n=547 SaaS companies) puts median TTV at roughly 1 day 12 hours — a number worth treating as directional only, given the self-selected sample.

Two framing consequences follow:

1. **Setup work is not value.** A metric anchored on setup ("linked a league", "completed profile") measures your funnel, not the user's payoff.
2. **The clock starts before install.** If store screenshots or a web landing page already delivered the "this is for me" moment, the in-app first run has a lower burden.

---

## 2. How teams identify the activation event empirically

### 2.1 The standard recipe

Across Lenny's Newsletter, Reforge, Kissmetrics, Mercury's growth blog, and June's activation playbook, the recipe is remarkably uniform:

1. **Enumerate candidate milestones** from product-usage data and qualitative work (JTBD interviews, session review). Kissmetrics is explicit that "the activation event is not something you define based on intuition… it is something you discover by analyzing the behavioral patterns" ([Kissmetrics](https://www.kissmetrics.io/blog/activation-rate-optimization)).
2. **Split retained vs churned cohorts** and compare first-session / first-week behaviour, typically via correlation or regression against a retention outcome at D7/D30 ([Lenny](https://www.lennysnewsletter.com/p/how-to-determine-your-activation), [Mercury](https://mercury.com/blog/identifying-product-aha-moment)).
3. **Experiment to establish causality** — build a variant that drives more users to the candidate behaviour and check whether retention actually moves. Lenny's formulation: "a good activation metric is causal for your retention, not just correlative."

Reforge adds a metric-architecture layer: retention is the *output*; activation is an *input* metric, and inputs should be "leading indicators that cause, or are at least highly correlated with" the north star ([Reforge](https://www.reforge.com/blog/north-star-metrics)).

Two secondary criteria appear repeatedly and are worth naming, because they are what make a candidate *usable* rather than merely predictive:

- **Reachability.** An event only 5% of users ever hit is not an activation target regardless of predictive power; it must be within reach of the majority of new users, ideally in the first session.
- **Discrimination.** The gap between retained and churned users must be large. The sharpest statement of this comes from a UXCam critique: "if 60% of your retained users completed onboarding step X, that sounds meaningful. But if 55% of your churned users also completed step X, the signal is noise" ([UXCam](https://uxcam.com/blog/why-most-teams-have-the-wrong-aha-moment/)).

### 2.2 Why the standard recipe is fragile

The correlational step is subject to at least five well-documented failure modes:

- **Survivorship / selection bias.** Analysing only retained users to find shared behaviours systematically ignores churned users who did the same thing ([UXCam](https://uxcam.com/blog/why-most-teams-have-the-wrong-aha-moment/)).
- **Reverse causality.** Engaged users add friends *because* they are engaged. The behaviour is a symptom of motivation, not a cause of retention. This is the core critique of every "N actions in M days" metric.
- **Threshold arbitrariness.** Andrew Chen's observation, relayed by Mixpanel, is that Facebook's number "could have realistically been 10 friends in 12 days or 5 friends in 1 day" — the threshold is chosen for memorability from a smooth curve, not identified as a discontinuity ([Mixpanel](https://mixpanel.com/blog/magic-numbers-are-an-illusion/)).
- **Cohort contamination.** Baselines built on early adopters, or pooled across acquisition channels, produce unrepresentative conclusions. Clean cohorts controlled for channel and time period are the stated fix.
- **Goodhart's law.** Once the activation number becomes a target it stops being a measure. GrowthBook frames this as specification gaming: teams optimise the gap between the metric and the mission ([GrowthBook](https://blog.growthbook.io/goodharts-law-and-the-dangers-of-metric-selection-with-a-b-testing/)). Reforge's countermeasure is a metric *tree* plus explicit quality guardrails, so that gaming a leaf shows up as damage elsewhere.

The most useful reframing I found is Mixpanel's: magic numbers are **a useful illusion** — a narrative device that focuses a team, whose value lies in alignment rather than in the specific integer. Mixpanel's alternative is multi-factor, feature-specific milestones (citing VSCO's tiered goals: 8 photo edits, 10 publishes, 16 collections) rather than one universal number.

### 2.3 What a causal test actually requires

The methodological constraints are stricter than most teams' experiment practice:

- **Long horizons.** Activation windows span 14+ days, so tests need 4–8 weeks minimum, and must track downstream retention rather than activation rate alone ([Kissmetrics](https://www.kissmetrics.io/blog/activation-rate-optimization)).
- **Power.** Duolingo's growth lead states that a mature product needs **~100,000 DAU** for significance on 1%-scale effects, and that early-stage apps should be aiming at **20–30% improvements**, not 1–2% ones ([First Round](https://review.firstround.com/the-tenets-of-a-b-testing-from-duolingos-master-growth-hacker/)). This is the single most transferable constraint for a small app: at low traffic, only structural changes are detectable.
- **Design restraint.** Same source: "stick to no more than three arms per experiment: a control and two test conditions."
- **Novelty and primacy effects.** Short-window onboarding tests are especially prone to these; the experimentation literature treats long-term effect estimation as a distinct problem ([arXiv: Novelty and Primacy](https://arxiv.org/pdf/2102.12893)).
- **Observational fallbacks are second-best.** Where randomisation isn't possible, propensity-score methods are the standard tool for opt-in / self-selected behaviours, precisely because "the naïve opt-in comparison is usually the wrong number" ([freeCodeCamp](https://www.freecodecamp.org/news/product-experimentation-with-propensity-scores-causal-inference-for-llm-based-features-in-python)). This is directly relevant to any activation event a user chooses to perform.

### 2.4 The canonical examples, and what they actually rest on

| Product | Stated activation event | What the evidence actually is |
|---|---|---|
| Facebook | 7 friends in 10 days | Retrospective cohort comparison described anecdotally by Chamath Palihapitiya in a talk; no published methodology. Publicly critiqued as an approximation ([Mixpanel](https://mixpanel.com/blog/magic-numbers-are-an-illusion/), [Mode](https://mode.com/blog/facebook-aha-moment-simpler-than-you-think/)) |
| Slack | 2,000 team messages | Founder judgement on top of observed patterns: "based on experience of which companies stuck with us and which didn't, we decided…" ([GrowthHackers](https://growthhackers.com/growth-studies/slack/)) |
| Grubhub | 55+ restaurant results on first search | Conversion-vs-supply curve in Boston; conversion roughly doubled past ~55 results. An S-curve inflection, which is a stronger empirical claim than a round-number threshold ([First Round podcast](https://review.firstround.com/podcast/building-winning-marketplaces-casey-winters/)) |
| Twitter / Dropbox | 30 follows / file on any device | Widely repeated, no primary methodology located ([Kissmetrics](https://www.kissmetrics.io/blog/activation-rate-optimization)) |
| VSCO | Tiered, feature-specific milestones | Cited by Mixpanel as the multi-factor alternative to a single magic number |

The Grubhub case is the most methodologically interesting: it identifies a **genuine inflection in a supply curve**, which is a different animal from picking a round number off a monotonic retention curve. Where a real threshold exists in the data, the magic-number framing is defensible; where the curve is smooth, it is a communication device.

---

## 3. Activation metric design and published benchmarks

**Lenny Rachitsky's activation-rate survey** (500+ responses, self-reported, eight product categories) is the largest public benchmark of its kind ([Lenny](https://www.lennysnewsletter.com/p/what-is-a-good-activation-rate)):

- Overall: **average 34%, median 25%**
- SaaS-only: **average 36%, median 30%**
- Rules of thumb: 60th percentile = good, 80th = great
- B2C freemium/subscription sits highest (low-friction milestones); DTC subscription lowest (transaction-based milestones)
- **Only 6% of respondents used a time-bound definition** — i.e. most "activation rates" have no denominator window, which makes cross-company comparison close to meaningless
- The variance is "mostly due to the milestone definition", and initial metrics are "hypothesis-driven" and "only correlative"

**Amplitude's Product Benchmark Report** is the largest behavioural dataset in play — 2,600+ companies, 10,600+ products, 17 industries ([Amplitude](https://amplitude.com/benchmarks/activation)). Its headline activation findings:

- **The "7% rule":** getting 7% of an original cohort to return on day 7 puts a product in the **top 25%** for activation ([Amplitude](https://amplitude.com/blog/7-percent-retention-rule))
- **69% of products strong at day-7 activation were also strong at three-month retention** — the strongest cross-temporal correlation in the dataset
- Enterprise: 90th percentile achieves 12.4% D7 retention vs 2.1% at the median (~6x spread)
- The sobering companion statistic: even at top-quartile performance, **93% of users do not return on day 7**

**Retention-curve context** (Quettra via Andrew Chen, 125M+ Android devices, Jan–May 2015, apps with 10k+ installs) ([andrewchen.com](https://andrewchen.com/new-data-shows-why-losing-80-of-your-mobile-users-is-normal-and-that-the-best-apps-do-much-better/)):

| | Average app | Top-10 apps |
|---|---|---|
| D1 | 29.17% | 74.67% |
| D3 | 23.42% | 71.51% |
| D7 | 17.28% | 67.39% |
| D30 | 9.55% | 59.80% |
| D90 | 3.97% | 50.87% |

The interpretive claim — "users decide which apps they want to stop using within the first 3–7 days" — is the empirical basis for the whole activation discipline. Note the important nuance in the same post: top apps' *slope* from D1→D30 is similar; they win on the **intercept**, i.e. the first session, not on later-stage retention mechanics.

---

## 4. Minimising steps to first value: what the evidence supports

### 4.1 Deferred signup / gradual engagement — the strongest evidence

The **Duolingo** results are the best-attributed numbers in this entire research area, because they come from the practitioner who ran them (Gina Gotthilf, VP Growth) in a first-person account ([First Round Review](https://review.firstround.com/the-tenets-of-a-b-testing-from-duolingos-master-growth-hacker/)):

- Moving the signup screen back a few steps, so users complete a lesson first: **~20% DAU increase**
- Optimised soft-wall → hard-wall sequence (including changing the dismiss button from "Discard my progress" to "Later"): **+8.2% DAU**
- Critically: **neither wall type performed as well in isolation** — soft walls prime users for the hard wall

That last point is the non-obvious finding. The lesson is not "remove the wall"; it is that a *dismissible* ask, placed after value, raises the conversion of the later mandatory ask. The mechanism is presumably investment/consistency rather than friction reduction alone.

For calibration, other Duolingo lifts from the same source: red notification dot +6% DAU, notification copy +5% DAU, badges +2.4% DAU (with +116% friends added), growth-mindset coach copy +7.2% D14 retention. The signup-placement change is by far the largest — structural placement beat every copy/mechanic tweak.

The pattern generalises as **gradual engagement**: let users do the core thing before asking who they are. Appcues catalogues the pattern across Duolingo, GOAT, Zocdoc, Tablet Hotel, TED, and Acorns, and is honest about the cost: fewer total registrations and less early contact data for feedback ([Appcues](https://www.appcues.com/blog/gradual-engagement-mobile-app-first-screen)). No A/B data of its own is presented.

### 4.2 Forced account creation — good survey evidence, one domain

Baymard's checkout research is the most methodologically transparent evidence for signup friction anywhere in this corpus: **24% of US internet shoppers abandoned one or more carts in the past quarter *solely* due to forced account creation** (n=4,384 US adults, 2022) ([Baymard](https://baymard.com/blog/make-guest-checkout-prominent)). Their qualitative testing adds that *offering* guest checkout isn't enough — 47% of sites that offer it fail to make it the most prominent option, and users abandon believing account creation is mandatory.

Caveat: this is e-commerce checkout, where the user has zero ongoing relationship incentive. Transfer to a habitual, identity-bound app is a hypothesis, not a finding.

### 4.3 Instructional onboarding — evidence says it doesn't work as taught

NN/g ran a controlled quantitative usability test: 70 iOS users, 35 per group, 4 apps with deck-of-cards tutorials, tasks that the tutorials explicitly taught ([NN/g](https://www.nngroup.com/articles/mobile-tutorials/)):

- Task success: **91% (tutorial) vs 94% (skipped)** — not significant, p=0.443
- Perceived ease (SEQ 1–7): **4.92 (tutorial) vs 5.49 (skipped)** — significant, p=0.047, i.e. *tutorials made tasks feel harder*
- Completion time: 93.5s vs 85.2s — not significant

NN/g's own limitation is stated: 4 iOS apps, generalisability uncertain. But the direction is consistent and the recommendation is blunt — spend the effort on making the UI usable rather than on explaining it. Their companion analysis of onboarding components reaches the same conclusion ([NN/g](https://www.nngroup.com/articles/mobile-app-onboarding/)).

The contrary academic evidence is narrow and comes from games: a controlled study (32 participants, 16 per group, custom game) found *progressive and adaptive* tutorials produced higher initial learning and higher memory retention than minimal assistance. Note the distinction — that study tested **contextual, adaptive** instruction, not upfront card decks, which is exactly the boundary NN/g draws.

### 4.4 The "each step costs X%" claim — weak evidence

This is the area where received wisdom is thickest. I traced the per-step onboarding drop-off benchmarks that circulate widely (e.g. "38% drop from stage 1 to 2", "a progress bar cut it to 24.1%") back to their apparent source page and found **no methodology, no sample size, no dates, and no named study**; the page's actual published figure is a range ("20–35% per screen") with attribution only to a mixed list of unrelated datasets ([UXCam](https://uxcam.com/blog/drop-off-rates/)). Treat all per-step onboarding benchmarks as folklore.

What *is* reasonably sourced:

- **Web-to-app funnels lose the majority of traffic at the first screen.** FunnelFox's State of Web2App report puts entry-point drop-off at ~52%, with ~13% of users reaching the paywall and ~3% of sessions purchasing ([FunnelFox](https://blog.funnelfox.com/onboarding-funnel-optimization/)). Sample size and period are not disclosed.
- **Form length reduces completion, in forms specifically.** Typeform reports ~47% average completion for one-question-per-screen forms vs a cited industry average of 21.5%, and that forms beyond six questions fall below 50% completion ([Typeform](https://help.typeform.com/hc/en-us/articles/360029615911-What-s-the-average-completion-rate-of-a-typeform)). This is vendor data on a self-selected corpus, and confounds format with the kind of company that chooses Typeform.
- **The Amplitude corollary:** over 98% of new users churn within two weeks when they never hit a value milestone. Reported from the 2,600-company dataset; note this is definitionally close to circular (users who never got value churn) but establishes the base rate.

---

## 5. The counter-case: front-loading setup can *increase* conversion

The "minimise steps" orthodoxy is contradicted by some of the highest-revenue consumer funnels operating today.

**Noom's web-to-app onboarding runs to ~113 screens over 10–15 minutes** before pricing ([RevenueCat teardown](https://www.revenuecat.com/blog/growth/web-to-app-onboarding-funnel)); an independent teardown counts 96+ screens against ~$750M–$1B annual revenue ([retention.blog](https://www.retention.blog/p/the-longest-onboarding-ever)). Cal AI is reported to have *added* questions that had no functional impact and seen conversion improve.

The teardowns converge on a mechanism, and it is worth stating precisely because it is *not* "length is good":

1. **Payoff precedes the data gate.** Noom shows the personalised projection graph and behavioural profile *before* asking for email; the email gate sits after the first visible payoff.
2. **Each answer visibly changes the output.** Projected dates move forward as answers deepen — the questions are legible as *work being done for the user*.
3. **The quiz teaches the method** (green/yellow/red foods, calorie density), pre-answering objections that would otherwise surface at the paywall.
4. **Sensitive questions are contextualised before being asked**, and vulnerable moments are followed immediately by reassurance.
5. **Commitment accumulates.** By the pricing screen the user has invested 10+ minutes; the cited supporting datum is that 55% of trial cancellations happen on day 0, which the design is built to pre-empt.

The academic anchor for (2) and (5) is the **endowed progress effect** (Nunes & Drèze, *Journal of Consumer Research*, 2006): a loyalty card requiring 10 stamps but pre-stamped with 2 produced substantially higher completion than an 8-stamp card starting at zero, despite identical remaining effort. I located this only via secondary UX sources and did not verify the primary paper's figures ([UX Collective](https://uxdesign.cc/endowed-progress-effect-give-your-users-a-head-start-97d52d8b0396)).

**Three reasons to hold this counter-case loosely:**

- **No controlled comparison exists in public.** Every long-funnel write-up cites revenue, not a randomised test against a short funnel. Noom's revenue is evidence that a long funnel *can* work at scale, not that it beat the alternative.
- **The optimised outcome is different.** These funnels optimise **paid-traffic monetisation** — the goal is to convert a cold, ad-acquired visitor to a subscription in one session. That is not the same objective as activating an organic user into a durable habit, and the reported metric (purchase) is not retention.
- **Selection.** Users who complete a 113-screen quiz are, by construction, high-intent. The funnel is partly a qualification filter, and its conversion rate among finishers cannot be read as an effect of length.

**The reconciliation hypothesis** that best fits both bodies of evidence: users tolerate steps in proportion to the *visible return* on each step, not in proportion to their count. Duolingo's removed steps were pure extraction (identity before value). Noom's added steps are visible production (each answer redraws the plan). What predicts drop-off is plausibly the ratio of steps-that-serve-the-user to steps-that-serve-the-company — not step count. This is a hypothesis; I found no study that tests it directly.

---

## 6. The personalisation-data vs speed-to-value tradeoff

Recommender systems have a genuine cold-start problem, and preference pickers (Netflix genres, Spotify artists) are the standard mitigation. The consensus practitioner position — which I found stated repeatedly but never with experimental backing — is that preference questions are tolerated **only when the payoff is visible and immediate**, i.e. when answering visibly changes what appears on screen within the same session.

Two design consequences appear across sources, both unvalidated:

- **Progressive profiling** over upfront profiling: collect the minimum needed for the first payoff, defer the rest to moments where each field unlocks something.
- **Real data beats sample data for attachment.** Kissmetrics argues users who activate on their *own* data form a stronger product connection than those using demo data — while the empty-state literature argues the opposite (preload sample data so the first screen isn't blank). These are in direct tension and neither is experimentally supported in the sources I found. The vendor claim that improved empty states lift first-action rates "often in the range of 15–30%" ([SaaS empty-state guidance](https://pixxen.com/blog/saas-empty-state-design/)) has no disclosed basis and should be discarded as evidence.

---

## Evidence quality notes

**Tier 1 — controlled, disclosed method, primary source**

- NN/g mobile tutorials study: n=70, 4 apps, two-group design, p-values reported, limitations stated. The only true controlled experiment in the corpus with full disclosure.
- Baymard forced-account-creation survey: n=4,384, dated 2022, single-cause attribution, paired with qualitative testing.
- Quettra/Andrew Chen retention curves: 125M+ devices, stated period (Jan–May 2015), stated inclusion criteria. **Now 11 years old** — mobile install and retention dynamics have shifted materially since.
- Game tutorial thesis: n=32, controlled, but tiny and on a custom game.

**Tier 2 — first-person practitioner reports of real experiments, method not disclosed**

- Duolingo's +20% DAU / +8.2% DAU results. Reported by the growth lead who ran them, with plausible mechanism and internally consistent surrounding numbers. No test design, duration, or significance detail published. This is the strongest evidence for deferred signup and it is still a self-report from an interested party.
- Grubhub's 55-restaurant inflection.
- Amplitude's 2,600-company benchmarks: enormous dataset, real behavioural data, but published as marketing with methodology summarised rather than specified. **The public activation benchmark page rendered a 0% placeholder when fetched** — the interactive numbers are not reliably retrievable, which is itself a caution about citing them.

**Tier 3 — survey / self-report**

- Lenny's activation-rate benchmarks (500+ self-reported responses). Useful for order of magnitude; the author's own caveat that variance is driven mostly by inconsistent milestone definitions, plus the finding that only 6% used time-bounded definitions, means these numbers cannot support cross-company comparison.
- Typeform and Userpilot vendor benchmarks: self-selected corpora, format confounded with company type.

**Tier 4 — received wisdom presented as data (do not rely on)**

- Per-step onboarding drop-off benchmarks (the "38% first-step" and "progress bar cut it to 24.1%" figures). I could not find the claimed study on the cited page; the page's own numbers differ and carry no methodology.
- "Good onboarding lifts retention by up to 50%", "empty-state improvements lift first-action 15–30%", most SaaS activation-rate bands (20–40% typical / 60%+ excellent).
- The Facebook and Slack magic numbers as *methodological* precedents. They are real historical artefacts of real teams, but neither was derived by a published method, and both are explicitly characterised by analytics vendors as approximations.

**Gaps I could not close** (session web-search budget exhausted after 20 queries; several sources returned 403 or were paywalled):

- Reforge's primary activation curriculum pages (403).
- Any published, randomised test of onboarding *length* holding content constant.
- Any peer-reviewed field experiment on registration-wall placement in a consumer app.
- Primary verification of the Nunes & Drèze figures.
- A/B evidence on whether upfront personalisation questions improve retention (as opposed to purchase conversion).

---

## Implications for FTF

Hypotheses only — each would need its own validation.

1. **FTF's likely activation event is a *judgement*, not a connection.** The Reforge setup/aha split suggests "connected a Sleeper league" is a setup moment: necessary, not sufficient, and exactly the "necessary but not sufficient" failure Lenny flags. Candidate aha events look more like *the first time a user sees a trade proposal involving their own players that they find plausible* — value received, not access granted. Worth testing whether league-connection alone discriminates between retained and churned users at all, or whether nearly everyone who churns also connected.

2. **The 3-player matchup vote is an unusual asset: it may be an aha *generator* rather than a setup cost.** It requires no league, produces immediate output (a ranking that moves), and is legible as "work being done for the user" — the Noom property. Hypothesis: matchup voting could serve as pre-account first value, with signup deferred behind it, which is structurally the Duolingo pattern. The counter-hypothesis is that voting is *contribution*, not consumption, and users may not read it as value received.

3. **The manual trade calculator is FTF's plausible "single-player mode."** It delivers value with zero league connection and zero social dependency. If the activation event can be reached without Sleeper auth, the entire signup-placement question opens up. Hypothesis: the calculator is the shortest path to first value in the product, and the automated trade finder — which requires connection *and* league context — is the deeper second act.

4. **Duolingo's soft-wall-then-hard-wall finding argues against a binary choice.** The transferable result is not "defer signup" but "a dismissible ask placed after value raises conversion of the later mandatory ask." Hypothesis: a dismissible Sleeper-connect prompt after first value, followed by a hard gate at a feature that genuinely requires it (send-trade-in-platform, notifications), outperforms either a front gate or a pure defer.

5. **FTF is almost certainly under-powered for the experiments this literature assumes.** Duolingo's 100k-DAU threshold for 1% effects implies FTF should only attempt **structural** onboarding changes with expected effects in the 20–30% range, and should not run copy-level onboarding tests expecting readable results. Corollary: qualitative session review and the existing in-app feedback loop are likely higher-information per unit effort than A/B testing at current scale.

6. **The activation window may be seasonal in a way the general literature doesn't model.** Dynasty fantasy has a hard annual rhythm (offseason trading, rookie drafts, in-season). A time-bound activation definition ("X within N days") — which only 6% of Lenny's respondents even use — may need a season-relative denominator rather than a signup-relative one. This is a genuinely FTF-specific design question with no external precedent found.

7. **Feature density argues for multi-factor milestones over one magic number.** Mixpanel's VSCO example (per-feature tiered goals) fits a product with nine notification types, boards, tiers, rankings, and two trade surfaces better than a single integer would. Hypothesis: FTF needs an activation *set* — one milestone per core surface — with a single headline number reserved for team communication rather than analysis.

8. **Guard against the metric becoming the product.** If "leagues connected" or "votes cast" becomes the target, Goodhart predicts the onboarding will optimise toward extraction. A metric tree with a quality guardrail (e.g. did the user return and act) is the documented countermeasure.

---

## Sources

**Activation metric design and aha-moment identification**
- Lenny Rachitsky — How to determine your activation metric: https://www.lennysnewsletter.com/p/how-to-determine-your-activation
- Lenny Rachitsky — What is a good activation rate (500+ response survey): https://www.lennysnewsletter.com/p/what-is-a-good-activation-rate
- Reforge — How to choose & measure North Star metrics: https://www.reforge.com/blog/north-star-metrics
- Reforge — Define your setup moment: https://www.reforge.com/guides/define-your-setup-moment
- GoPractice — Designing activation in reverse: https://gopractice.io/product/designing-activation-in-reverse/
- GoPractice — Conditions necessary for the aha moment: https://gopractice.io/product/conditions-necessary-for-the-aha-moment/
- June — Activation playbook: https://www.june.so/blog/activation-playbook
- Kissmetrics — Activation rate optimization: https://www.kissmetrics.io/blog/activation-rate-optimization
- Mercury — Identifying your product's aha moment: https://mercury.com/blog/identifying-product-aha-moment

**Critiques of magic numbers**
- Mixpanel — Magic numbers are an illusion: https://mixpanel.com/blog/magic-numbers-are-an-illusion/
- Mode — Facebook's aha moment was simpler than you think: https://mode.com/blog/facebook-aha-moment-simpler-than-you-think/
- UXCam — Why most teams have the wrong aha moment: https://uxcam.com/blog/why-most-teams-have-the-wrong-aha-moment/
- GrowthBook — Goodhart's law and the dangers of metric selection with A/B testing: https://blog.growthbook.io/goodharts-law-and-the-dangers-of-metric-selection-with-a-b-testing/
- Ravi Mehta — Your product team doesn't need a North Star Metric: https://blog.ravi-mehta.com/p/your-product-team-doesnt-need-a-north
- The Growth Mind — The ultimate story of growth hacking (Facebook origin): https://thegrowthmind.substack.com/p/story-of-growth-hacking-part-1
- GrowthHackers — Slack growth study (2,000 messages origin): https://growthhackers.com/growth-studies/slack/

**Benchmarks and retention data**
- Amplitude — Activation benchmarks: https://amplitude.com/benchmarks/activation
- Amplitude — The 7% retention rule: https://amplitude.com/blog/7-percent-retention-rule
- Amplitude — Product Benchmark Report (PDF): https://info.amplitude.com/rs/138-CDN-550/images/the-product-benchmark-report.pdf
- Andrew Chen — New data shows losing 80% of mobile users is normal (Quettra): https://andrewchen.com/new-data-shows-why-losing-80-of-your-mobile-users-is-normal-and-that-the-best-apps-do-much-better/
- UXCam — Drop-off rate: formula, benchmarks (methodology critique): https://uxcam.com/blog/drop-off-rates/
- FunnelFox — Onboarding funnel optimization for web-to-app: https://blog.funnelfox.com/onboarding-funnel-optimization/
- Valuecase — Time to value: definition, formula, benchmarks: https://www.valuecase.com/articles/what-is-time-to-value

**Experiments and step-minimisation**
- First Round Review — The tenets of A/B testing from Duolingo's master growth hacker: https://review.firstround.com/the-tenets-of-a-b-testing-from-duolingos-master-growth-hacker/
- How They Grow — How Duolingo grows: https://www.howtheygrow.co/p/how-duolingo-grows
- Appcues — Gradual engagement: why your mobile app's first screen should not be a signup: https://www.appcues.com/blog/gradual-engagement-mobile-app-first-screen
- Baymard Institute — Make guest checkout prominent: https://baymard.com/blog/make-guest-checkout-prominent
- NN/g — Mobile tutorials: wasted effort or efficiency boost? https://www.nngroup.com/articles/mobile-tutorials/
- NN/g — Mobile-app onboarding: an analysis of components and techniques: https://www.nngroup.com/articles/mobile-app-onboarding/
- Typeform — What's the average completion rate of a typeform? https://help.typeform.com/hc/en-us/articles/360029615911-What-s-the-average-completion-rate-of-a-typeform
- First Round Review — Building winning marketplaces, Casey Winters (Grubhub 55 restaurants): https://review.firstround.com/podcast/building-winning-marketplaces-casey-winters/

**Long-funnel counter-case and psychology**
- RevenueCat — Inside Noom's web-to-app onboarding funnel: https://www.revenuecat.com/blog/growth/web-to-app-onboarding-funnel
- retention.blog — The longest onboarding ever: https://www.retention.blog/p/the-longest-onboarding-ever
- UX Collective — Endowed progress effect (Nunes & Drèze 2006, secondary): https://uxdesign.cc/endowed-progress-effect-give-your-users-a-head-start-97d52d8b0396

**Experiment methodology**
- Kohavi & Deng — Trustworthy online controlled experiments: five puzzling outcomes explained: https://www.semanticscholar.org/paper/Trustworthy-online-controlled-experiments:-five-Kohavi-Deng/5d3abf5eb6df602e0d5779bad62fa5b3dcd40854
- arXiv — Novelty and primacy: a long-term estimator for online experiments: https://arxiv.org/pdf/2102.12893
- freeCodeCamp — Product experimentation with propensity scores: https://www.freecodecamp.org/news/product-experimentation-with-propensity-scores-causal-inference-for-llm-based-features-in-python
- DiVA — When and how to use tutorials in video games: a quantitative experiment: https://www.diva-portal.org/smash/get/diva2:1650050/FULLTEXT01.pdf
