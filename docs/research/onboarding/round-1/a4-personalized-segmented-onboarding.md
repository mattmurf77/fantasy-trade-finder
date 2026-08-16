# A4 — Personalized & Segmented Onboarding

> **Date:** 2026-08-15
> **Lens:** Intent surveys, persona branches, adaptive/behavioral onboarding, personalizing from imported data, power-vs-casual segmentation at entry, and how teams actually experiment on onboarding.
> **Scope:** Research only. Findings are evidence-cited where possible; opinion and uncited practitioner claims are labelled as such.

---

## TL;DR

- **The "does an intent survey hurt or help?" question is badly posed.** The published evidence says *placement and perceived payoff* dominate, not question count. Pinterest added an *extra* onboarding step and saw **+11% onboarding-flow completion**; the same question placed out of context after Google auth caused a **-30% collapse in Google signups** ([Pinterest Engineering](https://medium.com/pinterest-engineering/exploring-effective-user-signals-585507d8e926)).
- **Long intent surveys are defensible only when the answers visibly change the product.** Reforge cut onboarding from 12 steps to 2 (role + discovery source) and paired it with a personalized homepage: **+20% first-week active users, +25% CSAT** ([Growthmates](https://www.growthmates.news/p/onboarding-lab-how-superhuman-and)). Airtable's segmented, wizard-based onboarding produced **+20% activation** ([Lenny's Newsletter](https://www.lennysnewsletter.com/p/mastering-onboarding-lauryn-isford)).
- **Two different mechanisms get conflated.** An intent question can be a *routing signal* (data used to branch the product) or a *commitment device* (sunk-cost investment before a paywall, e.g. Noom's 100+ screen quiz). These have different evidence bases and different failure modes; the commitment mechanism does not require the data ever to be used.
- **Stated intent is a weak, decaying signal.** Spotify encodes onboarding-declared artists/genres/language as cold-start features, then *deliberately shifts to behavioural signals as they accumulate*; ablating onboarding signals costs **-13.8% nDCG@50** on onboarding-aligned clusters, but the model gains **+5% accuracy within 4 hours** of real listening ([Spotify Research](https://research.atspotify.com/2025/9/generalized-user-representations-for-large-scale-recommendations)). The right model is: stated intent is a *prior*, overwritten by behaviour fast.
- **Imported account data is a strictly better personalization source than a survey where it exists** — it is revealed, not stated, and it costs the user zero taps. Deezer's production cold-start system assigns new users to behaviour-derived clusters at registration rather than asking them ([arXiv 2106.03819](https://arxiv.org/abs/2106.03819)); Pinterest's current work derives per-user interest clusters with lifecycle metadata from engagement rather than declared interests ([Pinterest Engineering](https://medium.com/pinterest-engineering/pinner-progression-better-use-case-representation-driving-weekly-active-user-growth-at-pinterest-bd2131ab238a)).
- **Onboarding A/B tests are structurally the hardest tests to run.** New users have no pre-experiment history, so CUPED — the standard variance-reduction tool — is essentially inapplicable ([Statsig docs](https://docs.statsig.com/experiments/statistical-methods/methodologies/cuped), [Amplitude](https://amplitude.com/blog/amplitude-experiment-cuped)). Effects are small (Duolingo's mature-product launch bar is ~1%, needing ~100k DAU for significance), the outcome metric is delayed, and early converters distort early readings — Airbnb showed a test hitting p<0.05 with a 4% effect at day 7 that converged to *neutral* ([Airbnb Tech Blog](https://medium.com/airbnb-engineering/experiments-at-airbnb-e2db3abf39e7)).
- **The mitigations are known and mostly unavailable to small apps.** Learned proxy metrics (up to **78%** standalone power gain, or equal power at **12%** of the sample size — [arXiv 2402.03915](https://arxiv.org/abs/2402.03915)), surrogate indices, sequential testing, and long-term holdouts (Facebook 1–5% per half-year; LinkedIn 2%) all assume scale. Below that scale the honest options are qualitative research, directional instrumentation, and shipping on judgement.
- **Personalization must be *legible* to work.** Pinterest's own conclusion from the gender-signal experiment was that signal collection is "an opportunity to educate users about personalization benefits" — the completion gain came from telling users *why* ("helps us show you more relevant content"), not from asking more efficiently.

---

## 1. Intent surveys: what the evidence actually shows

### 1.1 Adding a step can *increase* completion

The single most useful published result in this lens is Pinterest's growth-activation work on user signals. The team wanted gender as a personalization signal and tested where to collect it.

- Placed immediately **after Google authentication** — out of the user's expected flow — it produced **+7% new-user activation but a 30% decrease in Google signups**. Net-negative.
- Placed **inside the onboarding flow** alongside topic selection and framed with a reason ("helps us show you more relevant content"), it produced **+11% onboarding-flow completion *despite adding an extra step***, with similar ~8% gains on Facebook signups where gender was already known.

Source: [Exploring effective user signals — Pinterest Engineering](https://medium.com/pinterest-engineering/exploring-effective-user-signals-585507d8e926).

Two things follow. First, "fewer questions = higher completion" is not a law; it is an artefact of badly-framed questions. Second, the +11% on Facebook signups (where gender was *already known* and therefore the answer was redundant) suggests part of the gain came from the **framing and the perceived personalization promise**, not from the data itself. That is a strong hint that intent questions do psychological work independent of their informational value.

### 1.2 But long, unused surveys are a real tax

The counterexample is Reforge's own onboarding. They ran a 12-step flow collecting detailed user data, and — critically — **weren't fully using the data to personalize**. Users, especially lower-motivation ones arriving via team subscriptions, dropped out. Reducing to **2 questions (role, and how they heard about it)** paired with a personalized homepage and customized checklists produced **+20% first-week active users and +25% CSAT** ([Growthmates onboarding lab](https://www.growthmates.news/p/onboarding-lab-how-superhuman-and)).

The lesson is not "2 is the magic number." It is that **the cost of a question is paid immediately and the benefit is only realised if the answer visibly changes something.** An unused profiling question is pure friction.

Airtable's overhaul, described by then-Head of Growth Lauryn Isford, took a similar shape — a guided onboarding wizard segmented by *learning style*, with week-four multi-user collaboration as the operationalized activation metric — and delivered **+20% activation rate** ([Lenny's Newsletter](https://www.lennysnewsletter.com/p/mastering-onboarding-lauryn-isford)).

### 1.3 The other mechanism: intent surveys as commitment devices

A large class of consumer subscription apps runs *very long* onboarding quizzes — Noom's pre-paywall flow reportedly runs to 100+ screens and 10–15 minutes — explicitly to manufacture investment before the paywall ([RevenueCat teardown](https://www.revenuecat.com/blog/growth/web-to-app-onboarding-funnel), [Web2App World](https://web2appworld.com/breakdowns/noom/)). The stated mechanism is sunk cost: each answered question raises the cost of walking away, and the personalization framing ("we're building your plan") converts effort into perceived bespokeness.

This is a **different mechanism from routing** and it is important not to import its conclusions into a routing context:

- It optimizes **paywall conversion**, not activation or long-term retention.
- It works because the *ritual* of answering is the product of the flow; the data need not be used.
- The evidence for it is overwhelmingly practitioner teardowns and funnel breakdowns, not controlled experiments. Treat as opinion-with-strong-priors.

Duolingo sits between the two: intent ("why are you learning?") plus a placement test plus goal-setting, with the paywall deferred until after a first lesson. Duolingo's MAU→paid rate rose from roughly 4% to >9% between 2020 and 2025, but attributing that to onboarding structure specifically is not supported by anything published — that is a correlation asserted in secondary teardowns.

### 1.4 The uncited-number problem

A large share of the "personalized onboarding lifts X%" numbers circulating are **unsourced**. I checked one representative example directly: a widely-syndicated claim that "personalization based on user role or signup intent lifts 7-day retention by 35%," alongside "every additional question reduces completion by 10–15%" and "segment into 3–5 onboarding paths." Fetching the source confirmed **no citation is given for any of the three numbers** ([DesignRevision](https://designrevision.com/blog/saas-onboarding-best-practices)). Similar: "personalized onboarding increases conversions by up to 200% in specific experiments" appears in mobile-onboarding roundups with no primary attribution ([Setgreet](https://www.setgreet.com/blog/what-the-numbers-actually-say-about-mobile-app-onboarding-(and-what-to-track))).

These should not be used as planning inputs. The defensible numbers in this document are the ones traceable to a company engineering blog, a named growth lead, or a peer-reviewed paper.

---

## 2. Stated intent vs. observed behaviour

### 2.1 The stated/revealed gap is real and well-documented

The stated-vs-revealed preference gap is a standard economics/HCI finding: what people say they want systematically diverges from what they choose. A recent study of young adults' news curation found participants report valuing diverse, balanced coverage while their actual consumption diverges substantially, with recommender feedback loops widening the gap ([arXiv 2604.11517](https://arxiv.org/pdf/2604.11517)). Practitioner framing of the same point notes that recommender systems that relied on explicit stated ratings have largely been deprecated in favour of behavioural signals because stated data predicts behaviour worse ([Hyntelo](https://blog.hyntelo.com/stated-vs-revealed-preference-understanding-your-customers-needs)).

Applied to onboarding: a user's answer to "what brings you here?" is a *self-image statement* as much as a plan. It is useful, but it should not outrank observed behaviour once behaviour exists.

### 2.2 The production pattern: intent as a decaying prior

Spotify's generalized user representation system is the clearest published articulation of how to handle this. Onboarding-declared artists, genres and languages are encoded through the *same* embedding pipeline as established users' behaviour, combined with demographic features, to enable personalization from day one. Then, "as behavioral data accumulates, the system gradually shifts from onboarding-based features to behavior-driven signals." Reported results: **+5% accuracy** on predicting future streaming within **4 hours** of joining; removing onboarding signals costs **-13.8% nDCG@50** on onboarding-aligned clusters ([Spotify Research](https://research.atspotify.com/2025/9/generalized-user-representations-for-large-scale-recommendations)).

Read that carefully: the onboarding signal is worth a real, measurable amount — *and* four hours of actual behaviour already meaningfully improves on it. That is the correct mental model for the half-life of stated intent.

Deezer's production cold-start system goes further and skips the asking: it clusters warm users from heterogeneous sources and assigns new users to a cluster at registration, delivering "semi-personalized" recommendations as a middle ground between generic and fully personalized ([arXiv 2106.03819](https://arxiv.org/abs/2106.03819), KDD 2021).

### 2.3 Behaviour-derived segmentation is where the frontier is

Pinterest's current work ("Pinner Progression") builds **User Interest Clusters** from a user's own engaged content rather than a global taxonomy or declared interests, and attaches **lifecycle metadata** to each cluster — recency and frequency signals marking an interest as nascent, mature, or declining. Ranking weights become state-dependent: nascent interests get curiosity-weighted signals, mature ones get commitment-weighted ones. The stated reframing is from optimizing engagement to optimizing **retention** ([Pinterest Engineering](https://medium.com/pinterest-engineering/pinner-progression-better-use-case-representation-driving-weekly-active-user-growth-at-pinterest-bd2131ab238a)). Note that Part 1 of that series does **not** publish the WAU numbers, so treat the framework as credible and the impact as unquantified.

---

## 3. Personalizing from imported data

Where a product can *read* something about the user at signup, it dominates asking.

- **Pinterest, localized new-user experience:** rather than a global topic picker, Pinterest built country-specific pickers from the most common board topics and top search queries per country, ranked candidate boards by engagement, relevance, recency and *language-match*, and had in-country teams vet the result. Outcome: new-user activation increased and signups were **5–10% more likely to return** ([Pinterest Engineering](https://medium.com/pinterest-engineering/personalizing-pinterests-new-user-experience-abroad-60f8f55177ac)). This is personalization from an inferred attribute (locale) requiring zero user input.
- **Spotify:** demographics + onboarding selections, both fed through the same encoder (above).
- **Whatnot:** collects gender and preferences early, then segments users into livestream options before dropping them into the product, rather than showing an undifferentiated feed ([Aakash Gupta, The Ultimate Guide to Onboarding](https://www.news.aakashg.com/p/the-ultimate-guide-to-onboarding)). Notably Aakash's framing is that **"sometimes longer can be better"** — speed-to-value is not universally the right objective; emerging-category products may need the profiling step to make the product legible at all.

**Important counterexample — real data is not always the best teaching substrate.** Superhuman moved *away* from onboarding inside the user's real inbox to a **full-screen synthetic inbox**, because real inboxes were inconsistent (empty ones taught nothing) and users hesitated to take risky actions on real mail. Results: **keyboard-shortcut usage +20%, reminder adoption +67%, week-1 activation +17%** ([Growthmates](https://www.growthmates.news/p/onboarding-lab-how-superhuman-and)).

The reconciliation: **imported data is superior for *personalizing what you show*; synthetic/controlled data is superior for *teaching a mechanic safely*.** Products that need to do both may need to separate the two moments.

---

## 4. Segmenting power users from casual users at entry

Published material here is thinner, and mostly indirect.

- **Superhuman's tenure-based UI:** compose and search icons were temporarily enlarged and labelled for new users, then labels were removed after **7 days** to restore the minimalist design for experienced users. Result: **+16% compose-button clicks, +20% emails created** ([Growthmates](https://www.growthmates.news/p/onboarding-lab-how-superhuman-and)). This is segmentation on *tenure* rather than declared expertise, and it is time-boxed and self-expiring — an unusually clean pattern.
- **Pinterest's lifecycle metadata** (nascent/mature/declining per interest cluster) is the same idea applied per-interest rather than per-user.
- **Activation benchmarks vary enormously by category**, which matters for choosing a segment-level target. From a survey of 500+ products: overall **average 34%, median 25%** activation; SaaS average 36%/median 30%; B2C free/ads products are among the lowest at roughly **25–35% for a "good" rate**; marketplaces lowest of all (~15–25%) since activation equals a first purchase. Only ~6% of respondents used a time-bound activation definition (median window 10 days) ([Lenny's Newsletter](https://www.lennysnewsletter.com/p/what-is-a-good-activation-rate)). The stated bar for a valid activation metric: activated users should retain **2x+** better than non-activated, and the metric must be actionable.
- **Aggregate results hide segment effects.** Airbnb's search-redesign experiment read neutral overall; broken down, the design was fine everywhere except Internet Explorer, where it was broken. After the fix the redesign showed **>2%** improvement ([Airbnb Tech Blog](https://medium.com/airbnb-engineering/experiments-at-airbnb-e2db3abf39e7)). Any onboarding test that reads flat should be cut by entry segment before being written off.

---

## 5. How teams experiment on onboarding — and why it's so hard

### 5.1 The structural problems

**No pre-experiment data.** CUPED, the standard variance-reduction technique, works by regressing out a pre-experiment covariate. New users have none. Statsig's own docs route new-user experiments away from CUPED to CURE, which uses assignment properties as covariates instead ([Statsig docs](https://docs.statsig.com/experiments/statistical-methods/methodologies/cuped)); Amplitude states it more bluntly — CUPED "will not be an effective variance reduction technique if you are only targeting new users in your test" ([Amplitude](https://amplitude.com/blog/amplitude-experiment-cuped)). This is the single most underappreciated reason onboarding tests need more traffic than other tests.

**The outcome metric is delayed and insensitive.** North-star retention metrics are, in the words of the accelerated-A/B-testing literature, "delayed and insensitive," producing long durations and frequent false negatives ([arXiv 2402.03915](https://arxiv.org/abs/2402.03915)). Netflix frames the same problem: many tests "do not provide enough signal to measure a change in long-term retention" ([Netflix TechBlog](https://netflixtechblog.com/improve-your-next-experiment-by-learning-better-proxy-metrics-from-past-experiments-64c786c2a3ac)).

**Early readings are systematically misleading.** Airbnb's price-filter test hit p<0.05 at day 7 with a 4% effect and converged to neutral; they note "this pattern of hitting 'significance' early and then converging back to a neutral result is actually quite common," driven by early converters having outsized influence at the start ([Airbnb Tech Blog](https://medium.com/airbnb-engineering/experiments-at-airbnb-e2db3abf39e7)). Peeking without correction is disastrous: in one demonstration, **>57% of A/A tests** falsely declared a winner or loser at least once when peeked at ([Johari et al., Peeking at A/B Tests](http://library.usc.edu.ph/ACM/KKD%202017/pdfs/p1517.pdf)).

**Real effects are small.** Duolingo's growth lead put the practical bar at roughly **~100,000 DAU** for significance, a **1%** improvement threshold for launching on a mature product, and 20–30% expected effects only for early-stage products, decaying over time (20% → 15% → 10%) ([First Round Review](https://review.firstround.com/the-tenets-of-a-b-testing-from-duolingos-master-growth-hacker/)).

### 5.2 What teams do about it

**Compound small wins rather than hunt for big ones.** Duolingo's published onboarding-adjacent results are individually modest and cumulatively large: delayed sign-up **+20% DAU**; a later "soft wall" refinement (a "Later" button replacing "Discard Progress") **+8.2% DAU**; growth-mindset in-app coach messaging **+7.2% D14**; personalized notification copy **+5% DAU**; an app-icon notification dot **+6% DAU** for six lines of code, plus **+1.6%** from a v2 ([First Round Review](https://review.firstround.com/the-tenets-of-a-b-testing-from-duolingos-master-growth-hacker/)). Their design discipline: max three conditions per test (one control, two variants), and a continuously re-ranked backlog scored by users affected ÷ engineering hours.

**Learn better proxy metrics.** Netflix's approach estimates the *structural* relationship between treatment effects on proxies and on the north star across a corpus of past experiments, using Total Covariance / JIVE / LIML estimators to strip out measurement-error bias — because naive user-level correlations and naive regressions on past experiment results are both biased ([Netflix TechBlog](https://netflixtechblog.com/improve-your-next-experiment-by-learning-better-proxy-metrics-from-past-experiments-64c786c2a3ac)). Independently, learning metrics by minimizing p-values over a log of 153 past A/B pairs across two social platforms yielded **up to 78%** standalone power increase, **up to 210%** combined with the north star, and equal power at **12%** of the north-star sample size ([arXiv 2402.03915](https://arxiv.org/abs/2402.03915)). The surrogate-index literature (Athey, Chetty, Imbens, Kang) is the formal underpinning ([NBER w26463](https://www.nber.org/system/files/working_papers/w26463.pdf)).

**Use sequential testing instead of peeking.** Always-valid inference (mSPRT-based) permits unlimited monitoring at the cost of some power at any fixed sample size ([Johari et al., *Always Valid Inference*](https://arxiv.org/pdf/1512.04922); [Optimizely](https://support.optimizely.com/hc/en-us/articles/39714777161229-Statistical-analysis-methods-overview); [Statsig](https://www.statsig.com/blog/sequential-testing-on-statsig)).

**Run tests concurrently, and use cheap variance tricks.** Interaction effects between overlapping tests are described as "super rare," so concurrency is nearly free; winsorization of heavy tails and stratified sampling help; CUPED/CURE delivers up to ~40% variance reduction where applicable ([Statsig](https://www.statsig.com/blog/speeding-up-a-b-tests-with-discipline)).

**Use long-term holdouts to measure the cumulative effect of many small onboarding wins.** Individual +1–2% results do not sum. Facebook product teams create **1–5%** holdouts at the start of each half and measure aggregate shipped impact against them; LinkedIn ran a **2%** member holdout across an entire 2021 member-value initiative ([Statsig](https://www.statsig.com/blog/getting-in-on-holdouts)). Practical guidance: measure over the final 1–4 weeks rather than the whole window; don't run 1% holdouts unless you're at Facebook scale; compare confidence intervals, not point estimates; and treat **~80% alignment** between holdout results and summed individual impacts as a healthy program, ~20% as a signal your testing methodology needs review ([Eppo](https://www.geteppo.com/blog/holdouts-measuring-experiment-impact-accurately)).

**Institutionalize idea generation.** Pinterest's Experiment Idea Review — a recurring meeting with a standard idea doc (problem, current UX screenshots, design, hypothesis with expected metric movement, opportunity size, estimated impact, investment, precedent, priority), 5 minutes present + 5 minutes discuss — reportedly resulted in **50–100% of experiments being ideated by non-lead team members**, while scaling the growth team past 100 people ([Pinterest Engineering](https://medium.com/pinterest-engineering/how-pinterest-supercharged-its-growth-team-with-experiment-idea-review-fd6571a02fb8)).

### 5.3 The small-app reality

Every mitigation above except sequential testing and qualitative research assumes traffic. A product without ~100k DAU cannot detect a 1–2% onboarding effect in any reasonable time, and cannot borrow strength from a corpus of past experiments it doesn't have. The honest posture for a small app is:

- pick an activation proxy that fires **within the first session** and has been validated as retention-predictive (Lenny's bar: activated cohort retains 2x+ better);
- accept that most onboarding decisions will be made on **qualitative evidence and judgement**, with instrumentation used to catch catastrophes rather than to certify wins;
- reserve the experimentation budget for changes with **plausibly double-digit** effects (structural flow changes), not copy tweaks;
- consider a **long-run holdout** as the eventual arbiter of whether a year of onboarding work did anything.

---

## 6. Anti-patterns and thin ice

- **Collecting profile data you don't use.** The clearest negative case in the literature (Reforge's 12-step flow). Cost is certain, benefit is zero.
- **Asking out of context.** Pinterest's -30% Google signup result. A question inserted at a moment where the user has a different expectation is far more expensive than the same question inside a flow they've accepted.
- **Assuming a survey answer beats a behavioural signal.** It does not, once behaviour exists (Spotify's 4-hour crossover).
- **Reading onboarding tests early.** Airbnb's 4%-then-neutral result, and the 57% A/A false-positive figure.
- **Importing subscription-quiz conclusions into an activation context.** Sunk-cost quiz funnels optimize paywall conversion, and the evidence is teardown-grade.
- **Trusting the circulating "35% retention lift from personalization" class of numbers.** Verified uncited.

---

## Evidence quality notes

| Claim class | Quality | Notes |
|---|---|---|
| Pinterest gender-signal experiment (+11% completion; -30% Google signups) | **High** | Company engineering blog, specific numbers, both positive and negative results reported |
| Pinterest localization (+5–10% return rate) | **Medium-high** | Company blog; activation "increased" is unquantified; 2016 vintage, five languages only |
| Spotify onboarding-signal ablation (-13.8% nDCG@50; +5% @4h) | **High** | Spotify Research publication with ablation study |
| Deezer semi-personalized cold start | **High** | KDD 2021 peer-reviewed; I could only read the abstract (PDF was not text-extractable), so cluster-assignment mechanics are unverified here |
| Duolingo experiment numbers (delayed signup +20% DAU, etc.) | **Medium-high** | First Round Review interview with the responsible growth lead; self-reported, no methodology published |
| Airtable +20% activation | **Medium** | Podcast interview with the Head of Growth; no methodology, no confidence intervals |
| Reforge 12→2 steps (+20% W1 actives, +25% CSAT) | **Medium** | Secondary write-up of a Reforge case study; the primary Reforge artifact returned HTTP 403 and could not be verified directly |
| Superhuman numbers (+17% W1 activation, +67% reminders, +16%/+20% compose) | **Medium** | Same secondary source; self-reported |
| Whatnot persona onboarding | **Low-medium** | Described qualitatively; the $2B GMV figure is company scale, not an onboarding result |
| Airbnb peeking/segment examples | **High** | Company engineering blog with a worked example |
| CUPED inapplicability to new-user tests | **High** | Vendor documentation from two independent vendors, consistent |
| Proxy/surrogate metric power gains (78% / 210% / 12%) | **High** | Peer-reviewed, 153 experiment pairs, two platforms |
| Netflix proxy-metric estimators | **High** for method, **N/A** for results | The blog post explicitly publishes no quantitative results |
| "14-day surrogate 95% consistent with 63-day outcomes, 79% precision" | **Low — unverified** | Surfaced in a search snippet attributed to a Netflix surrogate-index evaluation; I could not verify it against the primary paper. Do not cite without checking [arXiv 2311.11922](https://arxiv.org/pdf/2311.11922) |
| Holdout sizes (FB 1–5%, LinkedIn 2%), 80% alignment heuristic | **Medium-high** | Vendor blogs reporting on named companies; the 80% heuristic is vendor opinion |
| "Personalization lifts 7-day retention 35%", "10–15% completion drop per question", "up to 200% conversion" | **Very low — verified uncited** | Fetched the sources; no citations exist for any of them |
| Noom/quiz sunk-cost mechanics | **Low (opinion)** | Funnel teardowns; internally consistent and widely repeated, but no controlled evidence |

**General caution:** almost every positive number in this space is self-reported by the company that shipped the change, published because it worked. Publication bias here is severe. There is essentially no published literature on onboarding personalization that *failed*, other than the two cases companies disclosed as part of a success narrative (Pinterest's Google-auth placement, Reforge's 12-step flow).

---

## Implications for FTF

*Hypotheses only. Nothing below is a recommendation to build.*

**FTF's structural advantage: it reads the user's actual league rosters at sign-in.** This is the revealed-preference data that Spotify has to wait four hours for and Deezer has to approximate with clusters. A dynasty roster is an unusually rich behavioural artefact: it encodes team age curve, positional depth and holes, draft-pick capital, win-now vs. rebuild posture, league size and scoring format, and the user's own historical trade behaviour. Almost every segmentation question an intent survey would ask is *already answered* by the import.

- **H1 — Roster-derived segmentation should beat an intent survey on activation.** If a contender/rebuilder classification can be computed from roster age + record + pick capital, the survey question "are you contending or rebuilding?" is redundant informational overhead. Testable by comparing the roster-derived label to a stated label on the same users.
- **H2 — A single intent question may still pay for itself, for three non-informational reasons.** (a) It is a *legibility* device: Pinterest's +11% came from telling users why. Showing the user "we read your roster — you look like a rebuilder, is that right?" converts an invisible import into a visible act of personalization. (b) It resolves the genuinely ambiguous middle of the roster distribution. (c) It generates labelled training data for the roster classifier. Note that (a) is a *confirmation*, not a survey — one tap, pre-filled from data.
- **H3 — Stated intent should be modelled as a decaying prior.** Spotify's 4-hour crossover suggests FTF's own behavioural signals (which trade suggestions the user opens, which players they add to want/accept boards, which matchup votes they cast) should override a signup-time declaration quickly. A stale "rebuilding" label from August driving November's suggestions is a foreseeable failure mode.
- **H4 — Power-vs-casual segmentation is available at import with no questions asked.** League count, number of dynasty vs. redraft leagues, roster completeness, whether the user has made trades recently, and superflex/TE-premium format all separate the deep-dynasty user from the casual one at time zero. Superhuman's self-expiring tenure-based UI (labels for 7 days, then gone) is a cleaner model for FTF's feature depth than a permanent "advanced mode" toggle.
- **H5 — The first session should be a *personalized artefact*, not a tour.** The evidence pattern across Pinterest, Spotify, Reforge and Airtable is that personalization pays when it produces a visibly customised surface (localized topic picker, personalized homepage, segmented feed). FTF's analogue is a first screen that already contains *this user's* roster holes and *this user's* two or three highest-mutual-gain trades — the empty state that isn't empty.
- **H6 — Where imported data teaches badly, use a synthetic surface.** Superhuman's counterexample matters. Teaching the *3-player Elo matchup vote* or the *want/accept board mechanic* on the user's real roster may be worse than teaching it on a controlled example, because a user with an unusual roster gets an unrepresentative first lesson. Personalize the *content* surfaces; consider controlled examples for the *mechanic* lessons.
- **H7 — FTF almost certainly cannot A/B test onboarding to significance, and planning should say so out loud.** With no pre-experiment covariates (CUPED unavailable), a delayed outcome metric, and a user base orders of magnitude below Duolingo's ~100k-DAU bar, FTF cannot detect the 1–5% effects that constitute normal onboarding wins. Plausible posture: (a) define one in-first-session activation proxy and validate the 2x-retention-lift property against existing data before trusting it; (b) reserve experiments for structural changes with double-digit expected effects; (c) use sequential/always-valid monitoring so early looks aren't fatal; (d) consider a long-run holdout only once the shipping cadence justifies it.
- **H8 — Segment every onboarding read before concluding "flat."** Airbnb's IE case generalizes: a change that reads neutral overall may be strongly positive for Sleeper users with 3+ dynasty leagues and negative for single-league casuals. FTF's entry segments (platform, league count, format, roster archetype) should be pre-registered as breakdown dimensions.

**Open questions this lens could not answer.** No published fantasy-sports-specific onboarding experiments were located (the web-search budget for this session was exhausted before that query ran). Whether the dynasty audience's high domain expertise changes the friction calculus — expert users may *tolerate* and even expect a configuration step that would kill a mass-consumer flow — is unresolved and worth a targeted round-2 look.

---

## Sources

**Company engineering / research blogs**
- Pinterest Engineering — *Exploring effective user signals*: https://medium.com/pinterest-engineering/exploring-effective-user-signals-585507d8e926
- Pinterest Engineering — *Personalizing Pinterest's new user experience abroad*: https://medium.com/pinterest-engineering/personalizing-pinterests-new-user-experience-abroad-60f8f55177ac
- Pinterest Engineering — *Pinner Progression: Better use-case representation*: https://medium.com/pinterest-engineering/pinner-progression-better-use-case-representation-driving-weekly-active-user-growth-at-pinterest-bd2131ab238a
- Pinterest Engineering — *How Pinterest supercharged its growth team with Experiment Idea Review*: https://medium.com/pinterest-engineering/how-pinterest-supercharged-its-growth-team-with-experiment-idea-review-fd6571a02fb8
- Spotify Research — *Generalized user representations for large-scale recommendations*: https://research.atspotify.com/2025/9/generalized-user-representations-for-large-scale-recommendations
- Airbnb Tech Blog — *Experiments at Airbnb*: https://medium.com/airbnb-engineering/experiments-at-airbnb-e2db3abf39e7
- Netflix TechBlog — *Improve your next experiment by learning better proxy metrics from past experiments*: https://netflixtechblog.com/improve-your-next-experiment-by-learning-better-proxy-metrics-from-past-experiments-64c786c2a3ac

**Practitioner primary interviews / newsletters**
- First Round Review — *The tenets of A/B testing from Duolingo's master growth hacker*: https://review.firstround.com/the-tenets-of-a-b-testing-from-duolingos-master-growth-hacker/
- Lenny's Newsletter — *Mastering onboarding | Lauryn Isford (Head of Growth at Airtable)*: https://www.lennysnewsletter.com/p/mastering-onboarding-lauryn-isford
- Lenny's Newsletter — *What is a good activation rate?*: https://www.lennysnewsletter.com/p/what-is-a-good-activation-rate
- Aakash Gupta — *The Ultimate Guide to Onboarding*: https://www.news.aakashg.com/p/the-ultimate-guide-to-onboarding
- Growthmates — *Onboarding Lab: How Superhuman and Reforge craft the first experience*: https://www.growthmates.news/p/onboarding-lab-how-superhuman-and
- Reforge artifact — *Onboarding experiment result for personalization at Airtable* (returned HTTP 403; unverified): https://www.reforge.com/artifacts/onboarding-experiment-result-personalization-airtable

**Academic / methodological**
- Fadelli et al. — *A semi-personalized system for user cold start recommendation on music streaming apps* (KDD 2021): https://arxiv.org/abs/2106.03819
- *Learning metrics that maximise power for accelerated A/B-tests*: https://arxiv.org/abs/2402.03915
- Johari, Pekelis, Walsh — *Always valid inference: continuous monitoring of A/B tests*: https://arxiv.org/pdf/1512.04922
- Johari et al. — *Peeking at A/B tests: why it matters and what to do about it* (KDD 2017): http://library.usc.edu.ph/ACM/KKD%202017/pdfs/p1517.pdf
- Athey, Chetty, Imbens, Kang — *The surrogate index: combining short-term proxies to estimate long-term treatment effects* (NBER w26463): https://www.nber.org/system/files/working_papers/w26463.pdf
- *Evaluating the surrogate index as a decision-making tool* (unverified, flagged above): https://arxiv.org/pdf/2311.11922
- *Understanding the gap between stated and revealed preferences in news curation*: https://arxiv.org/pdf/2604.11517

**Experimentation tooling documentation**
- Statsig — *CUPED* (new-user experiment limitation): https://docs.statsig.com/experiments/statistical-methods/methodologies/cuped
- Statsig — *Don't be a holdout holdout*: https://www.statsig.com/blog/getting-in-on-holdouts
- Statsig — *Speeding up A/B tests with discipline*: https://www.statsig.com/blog/speeding-up-a-b-tests-with-discipline
- Statsig — *Sequential testing on Statsig*: https://www.statsig.com/blog/sequential-testing-on-statsig
- Amplitude — *Announcing CUPED availability in Experiment*: https://amplitude.com/blog/amplitude-experiment-cuped
- Eppo — *Holdouts: measuring experiment impact accurately*: https://www.geteppo.com/blog/holdouts-measuring-experiment-impact-accurately
- Optimizely — *Statistical analysis methods overview*: https://support.optimizely.com/hc/en-us/articles/39714777161229-Statistical-analysis-methods-overview

**Lower-quality / uncited (cited here only as examples of unsupported claims)**
- DesignRevision — *SaaS onboarding flow best practices*: https://designrevision.com/blog/saas-onboarding-best-practices
- Setgreet — *What the numbers actually say about mobile app onboarding*: https://www.setgreet.com/blog/what-the-numbers-actually-say-about-mobile-app-onboarding-(and-what-to-track)
- RevenueCat — *Inside Noom's web-to-app onboarding funnel*: https://www.revenuecat.com/blog/growth/web-to-app-onboarding-funnel
- Web2App World — *Noom funnel breakdown*: https://web2appworld.com/breakdowns/noom/
- Hyntelo — *Stated vs revealed preferences*: https://blog.hyntelo.com/stated-vs-revealed-preference-understanding-your-customers-needs
