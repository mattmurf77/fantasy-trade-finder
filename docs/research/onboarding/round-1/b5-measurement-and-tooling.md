# B5 — Measuring Feature Adoption, and the Tooling Landscape

**Date:** 2026-08-15
**Lens:** How complex apps *measure* whether progressive feature reveal works, and what tooling exists to build/buy discovery surfaces.
**Scope note:** This document deliberately stays out of the "what onboarding pattern to use" and "competitor teardown" lenses. It covers metrics, instrumentation, experiment design, and the build-vs-buy landscape.

---

## TL;DR

- **Adoption is not one number.** The usable frame is four metrics: *breadth* (share of eligible users who ever used it), *depth* (how much of the capability they use), *frequency* (sessions/uses per period), and *time-to-adopt* (exposure → first meaningful use). The denominator must be *eligible* users, not all actives, or every number is artificially deflated.
- **Portfolio view beats per-feature view.** Intercom's feature audit plots adoption (x) against frequency (y) and asks one of four questions per feature — kill, raise adoption, raise frequency, or deliberately improve. Pendo's study of 615 subscriptions found **80% of features are rarely or never used** and **12% of features drive 80% of daily usage**. For a feature-dense app like FTF, that is the central prior.
- **Feature retention ≠ user retention.** A feature can be adopted broadly and still not create return behavior. Amplitude's own guidance ends on the honest caveat: cohorting feature-users vs non-users gives correlation, *"you don't have causation yet"* — power users adopt features because they're power users.
- **The single highest-leverage instrumentation change for discovery features is exposure logging.** Analysing on *assignment* instead of *exposure* dilutes effects: Spotify's worked example shows a true +2 effect diluted to +0.2 when only 10% of assigned users actually encounter the change. Trigger analysis recovers it — at the cost that the estimate now applies only to triggered users.
- **Onboarding/discovery experiments are structurally the hardest kind.** New-user-only eligibility caps the sample, activation metrics are noisy and seasonal, and novelty effects distort week one. Group-sequential designs beat always-valid inference on power (~90% vs ~72–74% at a 0.2 SD effect in Spotify's simulations), but naive peeking pushes false-positive rate from 5% to ~10% after two looks and up toward 30% with daily peeking.
- **React Native support in the discovery-tooling market is genuinely uneven — and vendor marketing overstates it.** Verified: Appcues and Pendo both ship maintained RN SDKs (`@appcues/react-native` 5.0.6, 2026-06-17; `rn-pendo-sdk` 3.13.3, 2026-07-09). Chameleon's own help centre says it *"does not support native mobile apps"* — while a Chameleon marketing blog implies React Native support. Trust docs over blogs.
- **Pricing is the real gate for a small team.** Pendo is free to 500 MAU then quote-only (third-party estimates $7k–$142k/yr — treat as soft). Appcues publishes tiers but not prices; third-party estimates put entry around $249/mo. Chameleon publishes: $279/mo startup (2,000 MTUs), $750/mo Pro (5,000 MTUs) — and is web-only anyway.
- **The credible "build" path for a small RN team isn't building a tour engine — it's using the analytics/flag platform you already have.** PostHog (1M events + 1M flag requests free/mo) and Statsig (2M events free) both cover flags + experiments + surveys with maintained RN SDKs. Popular OSS RN tour libraries (`rn-tourguide`, `react-native-copilot`) have had **no release since 2024**.

---

## 1. What "feature adoption" actually means

The most common measurement failure is a definitional one. Contentsquare's framework is explicit that the adoption rate formula is `(users who completed the adoption event ÷ eligible users) × 100`, and that using the whole active base rather than the *eligible* base artificially deflates the number ([Contentsquare](https://contentsquare.com/blog/app-feature-adoption/)). For an app where a feature only exists for users who have linked a league, or only for dynasty formats, the eligible-user denominator is materially smaller than MAU.

The same source draws a second distinction that matters more than it sounds: **usage vs adoption**. Usage is a surface interaction (a tap, a screen view). Adoption is completing the workflow that delivers the intended value. It recommends modelling a four-stage funnel — *exposed → activated → used → used again* — so you can localise the drop-off. "Exposed" as an explicit, instrumented stage is the piece almost everyone skips, and it's the same piece that experimentation literature says is load-bearing (see §4).

## 2. The four-metric frame

Across sources the same decomposition recurs, with slightly different labels:

| Metric | Question it answers | Typical definition |
|---|---|---|
| **Breadth** | How widely is it used? | % of *eligible* users who used it ≥1 time |
| **Depth** | How much of the capability is used? | Advanced actions, feature-surface coverage, casual vs power split |
| **Frequency** | How often? | Uses/sessions per user per week |
| **Time-to-adopt** | How fast does value land? | Elapsed time from first exposure to first meaningful use |

Sources: [Contentsquare](https://contentsquare.com/blog/app-feature-adoption/), [Appcues](https://www.appcues.com/blog/success-with-product-adoption-metrics), [Userpilot](https://userpilot.com/blog/feature-adoption-metrics/).

Contentsquare frames time-to-adopt as a *leading* indicator — it degrades before adoption rate does, because friction shows up as delay before it shows up as abandonment. That makes it the most useful early-warning metric for a discovery-surface change: if a coach mark works, time-to-adopt should compress before breadth moves.

Amplitude's seven-step feature-measurement sequence adds the analytical ordering: basic usage → property segmentation → pre-feature event flow (what leads users into it) → behavioural cohort → retention comparison → conversion funnel → engagement/stickiness ([Amplitude](https://medium.com/@amplitudeHQ/7-steps-to-measuring-the-success-of-a-feature-21045ea640fb)). Step 3 — *what did users do immediately before first use* — is the one that speaks directly to discovery: it tells you which surface is actually feeding the feature, rather than which surface you *intended* to feed it.

## 3. Portfolio views: the feature audit and the 80% prior

**Intercom's feature audit** ([Intercom](https://www.intercom.com/blog/before-you-plan-your-product-roadmap/)) plots each feature with adoption (number of users) on the x-axis and frequency of use on the y-axis. The top-right region — "the star" — is what people actually use your product for. For any feature outside it there are exactly four moves: kill it, increase adoption, increase frequency, or deliberately improve it for the users it has. The framework's real value is forcing a *single* declared intent per feature before you touch it, so the result is measurable rather than "valueless pixel pushing."

The article's warning is directly relevant to a feature-dense dynasty app: you end up with "an excellent product for one precise workflow" plus a fringe of unused surface area, which leaves you exposed to a competitor who does only the core workflow.

**The base rate.** Pendo analysed 615 subscriptions with >1 year of tenure, over a three-month window, across banking/finance, HR tech, education, logistics, healthcare and e-commerce, and reported that **80% of features in the average software product are rarely or never used**, with **12% of features generating 80% of daily usage volume** ([Pendo feature adoption report](https://www.pendo.io/resources/the-2019-feature-adoption-report/)). Caveat: this is vendor-produced research on a self-selected customer base (companies that bought a feature-analytics product), and the headline "$29.5bn wasted" extrapolation leans on a Gartner revenue forecast and an average of 54 public software companies' R&D lines. The *direction* is well-corroborated by every practitioner framework; the precise 80/12 split should be treated as illustrative.

**Benchmarks are weak evidence.** A widely-circulated 2026 benchmark post gives "24.5% average core feature adoption (median 16.5%), top quartile >45%", "60% of users adopt within 24 hours", "40% of MAUs use 3+ features regularly" — but cites no methodology and references a "Product Metrics Benchmark Report 2024" without a link ([Artisan Strategies](https://www.artisangrowthstrategies.com/blog/feature-adoption-metrics-top-benchmarks-2025)). The likely upstream source is Userpilot's benchmark report (547 SaaS companies), which reports **activation 34.6% PLG / 41.6% SLG**, **time-to-value ~1 day 12 hours**, **1-month retention 48.4% PLG**, and **onboarding checklist completion averaging 19.2%** ([Userpilot](https://userpilot.com/blog/product-metrics-benchmark-report/)). That report gives **no mobile-vs-web split**, and it is drawn from a B2B SaaS customer base — so none of it transfers cleanly to a consumer fantasy-sports app. Use these as sanity bands, never as targets.

## 4. Feature retention, user retention, and the power user curve

Retention and stickiness are different measurements and can move independently. Amplitude defines retention as N-day return behaviour and stickiness as the share of users active *n* days out of a period, and warns that optimising one without the other is a real failure mode: you can pull people back into the app without giving them a reason to engage, and they churn anyway ([Amplitude](https://amplitude.com/blog/drive-engagement-and-stickiness)). Amplitude's stickiness chart is explicitly recommended for the per-feature question — comparing power users against regular users to find what the engaged cohort does differently ([Amplitude docs](https://amplitude.com/docs/analytics/charts/stickiness/stickiness-identify-features)).

Amplitude also notes that retention differs between users who touched a feature *once* and users who touched it a 3rd, 4th, or 5th time — which is the empirical basis for "habit formation" thresholds, and for defining an adoption event as *n*-th use rather than first use.

**The power user curve (L28/L30)** is the most useful single chart for a product whose value is uneven across users. It is a histogram of users by number of active days in a 28/30-day window, popularised by Andrew Chen from the Facebook growth team's L30 ([a16z](https://a16z.com/the-power-user-curve-the-best-way-to-understand-your-most-engaged-users/), [andrewchen.com](https://andrewchen.com/power-user-curve/)). Key points from the source:

- A right-leaning "smile" indicates a hardcore daily core; Chen's illustrative claim is Facebook would show 60%+ of MAUs returning daily.
- A left-leaning curve is *not necessarily* a failure — LinkedIn and Wealthfront are cited as products that work fine with infrequent engagement, provided monetisation doesn't assume daily use.
- The action can be customised: app opens, or a value action (posts, transactions). Chen explicitly recommends **analysing by feature and by segment**, and tracking cohorts over time to see whether the mass shifts rightward.
- L7 is the right window for productivity/B2B tools that follow a workweek rhythm.

For a fantasy app the seasonal analogue is obvious: an L28 built on "app open" during the NFL season will look nothing like the same curve in June, and comparisons must be cohort- and calendar-aligned.

**Counter-evidence worth holding:** Reforge's "power user trap" argues that optimising around the most engaged segment can misdirect a roadmap, because power users' needs diverge from the median user's and their behaviour is the *result* of engagement rather than the cause. (Page returned 403 to automated fetch; cited from the search result title/summary only — treat as a pointer, not as verified content.)

## 5. Instrumentation for discovery features: exposure, triggering, dilution

This is the section that most directly answers "how do we tell a tooltip *caused* adoption rather than correlated with it."

**Log exposure, not assignment.** An exposure event marks when a unit was actually in a position to be affected. Microsoft's experimentation guidance treats exposure/trigger logging as a hard requirement, not a nice-to-have, because it both simplifies analysis and increases statistical power by separating units that could have been affected from those that provably couldn't ([Microsoft Research, Patterns of Trustworthy Experimentation](https://www.microsoft.com/en-us/research/group/experimentation-platform-exp/articles/patterns-of-trustworthy-experimentation-post-experiment-stage/)).

**Trigger analysis has two flavours** ([Spotify Confidence](https://confidence.spotify.com/blog/trigger-analysis)):
- *User-level inclusion* — filter to users who ever hit the changed surface; include all their measurements.
- *Event-level inclusion* — include only measurements taken while the user was in the changed experience; the natural fit for recommender-style counterfactual logging.

The worked example is the clearest statement of why this matters: if only 10% of assigned users actually experience the change, a real treatment effect of 2 units gets diluted to 0.2 across the assigned population. Filtering to the triggered 10% recovers the true 2-unit effect.

**Three traps, all of which apply to tooltips and coach marks:**

1. **The estimate changes meaning.** Spotify is blunt: "An estimated effect of 10% on trigger-exposed users doesn't translate to a 10% increase in the entire population." You need the dilution step to get back to a launch decision. Kohavi/Deng's group note that practitioners routinely apply approximate or outright wrong dilution formulas, especially for ratio metrics, and propose combining triggered analysis and dilution into one estimator for better accuracy and power ([ExP Platform](https://exp-platform.com/dilution/)).
2. **Treatment can change who triggers.** If the treatment makes the surface slower, or the tooltip blocks the element that would otherwise fire the trigger, the triggered populations diverge between arms — producing sample ratio mismatch and invalidating the comparison (Spotify, above). A tooltip that suppresses the very interaction it's meant to encourage is exactly this failure.
3. **Trigger conditions need ~100% recall.** Microsoft's post-experiment checklist requires that the trigger captures users who *were or would have been* affected, and that the *triggered-complement* analysis looks like an A/A test. If the untriggered remainder shows a treatment effect, your trigger definition is wrong.

**Place the exposure event as late as possible in code** — at the moment the surface actually renders, not at flag evaluation — so exposure rows are only generated for units that genuinely could see it (per the trigger/dilution guidance above).

**Post-experiment hygiene** from Microsoft: run SRM checks (including at individual metric level for rate metrics, using "the metric with the most fine-grained denominator where the denominator has no stat-sig movement"), watch for telemetry-breaking changes where the treatment alters logging itself, reproduce surprising results (Twyman's Law), and archive hypotheses for meta-analysis.

**Holdouts as the causal backstop.** For discovery systems that will be permanently on, a long-running holdout — a randomly assigned slice that never receives the tours/announcements — measures cumulative incremental lift that individual short tests can't ([Amplitude on incrementality](https://amplitude.com/explore/experiment/incrementality-testing), [Measured](https://www.measured.com/faq/holdout-test/)). Note that most of the accessible writing on holdouts is marketing-measurement content; the technique transfers, but the sources are not product-experimentation sources.

## 6. Experiment design for onboarding and discovery changes

**Why these tests are slow and noisy.**
- The eligible population is usually *new users only*, which for a small app is a fraction of MAU per week.
- Activation metrics are binary and low-base-rate, and noisier metrics require more sample for the same power ([Convert](https://www.convert.com/blog/a-b-testing/statistical-power/), [Atticus Li](https://atticusli.com/blog/posts/statistical-power-why-most-ab-tests-underpowered/)).
- Seasonality and external events swamp small effects — one source's example is an onboarding wizard whose completion moves from 40% to 80–90% during a conference week.
- The most common cause of underpowered tests is simply never doing the power calculation: teams pick "two weeks" or "one sprint" and hope.

**The winner's curse makes underpowered tests worse than useless.** In a small sample, the only way a real-but-small effect crosses significance is if noise pushes the measured effect well above its true value — so *reaching* significance in an underpowered test guarantees the estimate is inflated ([Atticus Li](https://atticusli.com/blog/posts/statistical-power-why-most-ab-tests-underpowered/)). The practical advice is to run fewer, adequately powered tests rather than many weak ones.

**Sequential testing — real, but not free.** Always-valid inference (mSPRT and successors) lets you monitor continuously without inflating type-I error; mSPRT is used/extended by Optimizely, Uber, Netflix and Amplitude, Eppo uses a GAVI generalisation, Statsig a corrected-alpha approach ([Johari et al., arXiv](https://arxiv.org/pdf/1512.04922), [Analytics-Toolkit](https://blog.analytics-toolkit.com/2022/comparison-of-the-statistical-power-of-sequential-tests/)). Spotify's simulation study gives the tradeoff numbers ([Spotify Engineering](https://engineering.atspotify.com/2023/03/choosing-sequential-testing-framework-comparisons-and-discussions)):

- Group sequential tests (GST) dominate on power when you can estimate max sample size in advance: **~90% power vs ~72–74% for always-valid methods at a 0.2 SD effect**.
- GAVI loses ~15% power vs its optimal configuration and ~30% vs a correctly-specified GST when the sample size is badly (50×) underestimated.
- Naive peeking without any correction takes the false-positive rate to **10% after two looks** at a nominal 5%; daily peeking over a month is commonly quoted at **up to ~30%** ([Donnu](https://donnuab.com/blog/en/sequential-testing-explained/)).

Read together: for a small-traffic product, a fixed-horizon or group-sequential design with a pre-registered stopping rule is the higher-power choice; always-valid inference is what you adopt if you cannot resist looking, and you pay ~15–20% power for the privilege.

**Proxy metrics.** Because the outcome you care about (season-long retention, trades actually executed) is far downstream, onboarding tests almost always run on proxies — activation, time-to-adopt, checklist completion. Two disciplines apply: declare the proxy *and* the guardrails before launch, and periodically validate that the proxy still predicts the downstream metric (the "closing the loop"/meta-analysis pattern in the Microsoft guidance). Contentsquare's time-to-adopt-as-leading-indicator argument is the practical version of this.

**Novelty/primacy.** Discovery surfaces are the archetypal novelty-effect case: a new tooltip gets attention because it's new. The standard mitigation is cohort-based analysis (new users only, so nobody has a "before"), and checking whether the effect persists in later weekly cohorts rather than decaying.

## 7. The tooling landscape — what's real, verified where possible

### 7.1 React Native support (the thing vendors overstate)

| Vendor | Native mobile / RN? | Evidence |
|---|---|---|
| **Appcues** | Yes. iOS, Android, RN, Flutter, Ionic. RN ≥0.73, Expo SDK ≥50; New Architecture (Fabric/TurboModules) from module 4.4.0. Modals, anchored + floating tooltips, embeds (embeds not on Ionic). iOS 13+ to render. | [Appcues docs](https://docs.appcues.com/mobile-installation-overview/installing-the-mobile-sdk), [GitHub](https://github.com/appcues/appcues-react-native-module), [Expo module](https://github.com/appcues/appcues-expo-module) |
| **Pendo** | Yes, with a caveat: RN 0.66–0.84 codeless with react-navigation 5+; **tooltips are not available for RN apps using custom routers**, and custom-navigation apps must hand-instrument `PendoSDK.track()` for pages, features and guide triggers. | [Pendo help — RN with custom navigation](https://support.pendo.io/hc/en-us/articles/360038590491-React-Native-with-custom-navigation), [pendo-mobile-sdk](https://github.com/pendo-io/pendo-mobile-sdk) |
| **Chameleon** | **No.** Help centre: *"Chameleon does not support native mobile apps but fully supports mobile web applications."* SPAs fully supported. | [Chameleon help](https://help.chameleon.io/en/articles/1204271-will-chameleon-work-with-my-product) |
| **Userflow** | Unverified — pricing and docs pages returned 403 to automated fetch. Positioned as a web/SPA tool in every third-party comparison seen; treat native RN support as *not established*. | — |
| **Intercom** | In-app messages/banners/tooltips are included on all plans; mobile SDK coverage not stated on the pricing page. | [Intercom pricing](https://www.intercom.com/pricing) |

**Vendor-bias flag, concrete instance:** a Chameleon *marketing blog* was surfaced claiming Chameleon "allows support for React Native, Cordova, Xamarin, Flutter, etc." while Chameleon's *own help centre* says it does not support native mobile apps. The reconciliation is that Capacitor/Cordova-wrapped web apps work; a true RN app does not. This is the general pattern — marketing pages list frameworks, docs list constraints. **Verify every mobile claim against the docs/SDK repo, not the comparison page.**

**Maintenance signal (verified directly from the npm registry, 2026-08-15):**

| Package | Latest | Published | Weekly downloads |
|---|---|---|---|
| `@appcues/react-native` | 5.0.6 | 2026-06-17 | ~12.9k |
| `rn-pendo-sdk` | 3.13.3 | 2026-07-09 | ~46.8k |
| `posthog-react-native` | — | — | ~982k |
| `@amplitude/analytics-react-native` | — | — | ~178k |
| `rn-tourguide` (OSS tour) | 3.3.2 | **2024-10-30** | ~10.0k |
| `react-native-copilot` (OSS tour) | 3.3.3 | **2024-12-17** | ~15.6k |

The commercial mobile SDKs are actively maintained. The two best-known open-source RN walkthrough libraries have shipped **nothing in ~20 months** — adopting either is effectively adopting an unmaintained dependency.

### 7.2 Pricing relevant to a small team

- **Pendo** — free forever to **500 MAU**, including product analytics, in-app guides, Pendo-branded roadmaps/NPS, unlimited web and mobile app keys; past 500 MAU you cannot create new guides/surveys/segments without upgrading. Paid Base/Core/Ultimate are **quote-only, no published prices** ([Pendo pricing](https://www.pendo.io/pricing/)). Third-party estimates range $7k–$142k/yr with a mid-market average near $47k ([Usercall](https://www.usercall.co/post/pendo-pricing), [Supered](https://www.supered.io/blog/pendo-pricing/)) — these are resellers/competitors aggregating anecdotes; treat as order-of-magnitude only.
- **Appcues** — publishes tiers (Start ≤3,000 MAU / 10 published experiences; Grow from 3,000 MAU / 25; Enterprise / 100) but **not prices**; a "Spark program" exists for teams under 25 people. Billing counts *every* identified user in a rolling 30 days as an MAU "regardless of whether they see an experience or not" ([Appcues pricing](https://www.appcues.com/pricing), [Appcues docs](https://docs.appcues.com/mobile-installation-overview/installing-the-mobile-sdk)). Third-party estimates put Essentials ≈$249/mo at 2,500 MAU and Growth ≈$879/mo ([Apty](https://apty.ai/blog/appcues-pricing/), [Userpilot](https://userpilot.com/blog/appcues-pricing-explained/) — both competitor-adjacent).
- **Chameleon** — publishes prices: Startup from **$279/mo for 2,000 MTUs** (10 live experiences), Pro from **$750/mo for 5,000 MTUs**, Growth from **$1,250/mo** annually ([Chameleon pricing](https://www.chameleon.io/pricing)). Web-only, so not applicable to an RN app.
- **Intercom** — $29/$85/$132 per seat/month; in-app chats, banners and tooltips included on all plans; Proactive Support Plus add-on $99/mo ([Intercom pricing](https://www.intercom.com/pricing)).

The billing model matters as much as the sticker: MAU-metered pricing on a *consumer* app with a large free base scales badly, because you pay for every identified user whether or not they ever see a guide.

### 7.3 The "already have it" alternative

For a team with an existing events pipeline and flag system, the realistic build path is not writing a tour engine — it's driving simple, hand-built UI affordances from the flag/experiment infrastructure already in place, and measuring them in the analytics store already in place.

- **PostHog** — free monthly: 1M events, 1M feature-flag requests, 1,500 survey responses; experiments billed with flags; then $0.00005/event, $0.0001/flag request ([PostHog pricing](https://posthog.com/pricing)). RN SDK supports autocapture, flags, experiments, surveys, session replay, error tracking and push, and works in Expo without extra native deps ([PostHog RN docs](https://posthog.com/docs/libraries/react-native)).
- **Statsig** — free Developer tier: 2M events/mo, unlimited flag/config checks, 50k session replays; Pro $150/mo with 5M events then $0.05/1k ([Statsig pricing](https://www.statsig.com/pricing)).

Both give sequential/always-valid or corrected-alpha analysis out of the box, which is exactly the machinery §6 says you need and which no in-app-guidance vendor provides at the same rigour.

### 7.4 When teams build in-house

The honest case *against* building the guidance layer comes from a vendor's own engineering blog, which is useful precisely because it undercuts their marketing simplicity: Appcues describes maintaining separate native modules per framework (RN native module, Flutter plugin, Ionic plugin, Xamarin bindings), and notes that "each new release of the native toolkits likely necessitates a new update of these wrapper libraries," with Android dependency chains propagating into required SDK versions ([Appcues engineering](https://engineering.appcues.com/blog/building-cross-platform-mobile-frameworks-at-appcues)). Element targeting and rendering over native views are the hard parts.

Synthesising that against the rest: teams tend to build in-house when (a) they only need a handful of *specific* affordances rather than a general no-code editor, (b) they already own flags + events, so the marginal build is the UI component and a couple of event names, (c) design-system fidelity matters and vendor-rendered overlays would look foreign, (d) MAU-metered pricing is punitive for a consumer free tier, or (e) they refuse to ship a third-party SDK that can render arbitrary remote content into the app. They tend to buy when non-engineers must author and target content weekly without a release, which is the genuine and non-trivial value a DAP provides.

---

## Evidence quality notes

- **Search budget was capped mid-task.** The session's WebSearch allowance (200 calls, shared across concurrent agents) was exhausted after ~10 searches here. I compensated with ~28 direct WebFetch calls against canonical vendor docs, engineering blogs, and primary papers, plus direct npm-registry queries. Net effect: fewer discovery paths, but a higher proportion of primary sources than a search-heavy pass would have produced.
- **Strong evidence (primary, methodologically explicit):** Spotify's sequential-testing simulation study and trigger-analysis explainer; Microsoft Research's trustworthy-experimentation patterns; Johari et al. on always-valid inference; Kohavi/Deng on dilution; vendor *documentation* on SDK support; npm registry version/download data (verified directly, not scraped from a blog).
- **Medium evidence (credible but self-interested or unaudited):** Pendo's 80%/12% feature-adoption study — real methodology (615 subscriptions, 3 months) on a self-selected customer base, published to sell feature analytics. Amplitude's stickiness and feature-measurement guidance — sound, but it exists to demonstrate Amplitude charts. Andrew Chen's power-user-curve numbers are illustrative ("Facebook would have…"), not measured disclosures.
- **Weak evidence (treat as opinion):** all third-party pricing estimates for Pendo and Appcues — the highest-ranking sources are competitors (Userpilot, Apty) or procurement/aggregator sites with unverifiable data. Feature-adoption "benchmarks" with no methodology (Artisan Strategies). Userpilot's 547-company benchmark report has a stated sample but is drawn from its own B2B SaaS customers and gives no mobile split.
- **Unverified:** Userflow's mobile/native support and current pricing (403 on both pages). Reforge's "power user trap" argument (403; cited from search summary only).
- **Documented vendor-marketing contradiction:** Chameleon's marketing blog implies React Native support; Chameleon's help centre states it does not support native mobile apps. Resolved in favour of the docs.
- **Transfer risk:** almost the entire adoption-benchmark and DAP literature is B2B SaaS. FTF is a consumer, seasonal, free-tier app. Absolute benchmark numbers should not be imported; the *frameworks* (breadth/depth/frequency/time-to-adopt, feature audit, exposure logging) transfer cleanly.

---

## Implications for FTF — hypotheses only, not recommendations

These are framed as testable hypotheses. None has been validated against FTF data.

1. **The exposure gap is the single highest-value fix.** `backend/experiments.py` currently annotates every readout with `"assignment used as exposure proxy (experiment_exposed dark until the client SDK ships) — dilution not yet separable"`, while `experiment_exposed` is already registered in `analytics_taxonomy.py` with an `{experiment, variant, unit, …}` property set. *Hypothesis:* for onboarding/discovery experiments — where a large share of assigned units never reach the changed surface — assignment-based readouts are diluted enough to hide real effects, and lighting up client-side `experiment_exposed` (fired at render, not at flag evaluation) would recover most of the lost sensitivity. Spotify's 10%-trigger example implies a 10× attenuation in the worst case.
2. **FTF may already have the discovery instrumentation it needs, unanalysed.** The taxonomy already carries `coach_mark_shown` / `coach_mark_dismissed`, the full `guide_step_shown` / `guide_step_advanced` / `guide_step_skipped` / `guide_tour_dismissed` / `guide_tour_completed` set, `quickset_prompt_*`, `apple_prompt_*`, and first-session deck activation events. *Hypothesis:* a shown→advanced→completed→downstream-adoption funnel per coach mark, cut by cohort, would identify which discovery surfaces are inert without needing any new instrumentation — an observational first pass that costs nothing and scopes the experiment backlog.
3. **A feature audit on the existing `config/features.json` surface would likely reproduce the 80/12 shape.** The flag file lists 60+ user-visible capabilities. *Hypothesis:* plotting each against adoption (unique eligible users) × frequency, per Intercom, would place the large majority far from the star, and would surface a specific list of "kill / raise adoption / raise frequency / improve" decisions rather than an undifferentiated "improve discovery" goal.
4. **Time-to-adopt is probably the right primary metric for discovery experiments, not adoption rate.** *Hypothesis:* because it is a leading indicator and a continuous (rather than binary) measure, per-feature time-from-first-eligible-session-to-first-use will move detectably on a sample size where a binary adoption rate would not — improving power on a population that is structurally small.
5. **Season-aligned cohorting is likely mandatory.** *Hypothesis:* any L28/power-user-curve or retention comparison spanning the NFL calendar boundary will be dominated by seasonality rather than by the change under test, so onboarding readouts should compare same-week cohorts across arms and never period-over-period.
6. **The existing experiments engine may already exceed what a DAP would provide statistically — but be under-powered by design.** `experiments.py` has layered assignment, an SRM check, an underpowered gate with `override_underpowered`, and a design calculator taking `mde`/`alpha`/`power`. *Hypothesis:* the binding constraint on FTF onboarding experiments is weekly new-user volume, not tooling; and given Spotify's power comparison, a pre-registered fixed-horizon or group-sequential design will beat adopting always-valid inference by roughly 15–20% power at this sample size.
7. **Buying a DAP looks poorly matched to FTF's shape.** *Hypothesis:* MAU-metered pricing against a consumer free base, Chameleon's lack of native support, Pendo's tooltip restriction under custom RN navigation, and the fact that FTF already owns flags + events + experiment assignment mean the marginal value of a vendor is narrow — essentially "let a non-engineer author and target content without a release." If nobody needs that weekly, the vendor spend buys little.
8. **If FTF does build tour UI, it should not adopt an OSS RN tour library.** `rn-tourguide` and `react-native-copilot` have had no release since late 2024. *Hypothesis:* a small purpose-built overlay component against the Chalkline design system is lower total risk than a stale dependency, and keeps the discovery surface visually native to the app.
9. **A permanent discovery holdout may be worth its cost.** *Hypothesis:* a small always-off slice (never receives coach marks/tours/announcements) would, over a season, measure the cumulative incremental value of the whole discovery layer — a number no individual short test can produce, and the only defence against a stack of individually-neutral surfaces that collectively add clutter.

---

## Sources

**Metrics and frameworks**
- Intercom — Before you plan your product roadmap (feature audit chart): https://www.intercom.com/blog/before-you-plan-your-product-roadmap/
- Pendo — Feature adoption report (80% rarely/never used; 615 subscriptions): https://www.pendo.io/resources/the-2019-feature-adoption-report/
- Contentsquare — How to measure feature adoption (formulas, breadth/depth/time-to-adopt): https://contentsquare.com/blog/app-feature-adoption/
- Appcues — Product adoption metrics: https://www.appcues.com/blog/success-with-product-adoption-metrics
- Userpilot — Feature adoption metrics: https://userpilot.com/blog/feature-adoption-metrics/
- Userpilot — Product metrics benchmark report (547 SaaS companies): https://userpilot.com/blog/product-metrics-benchmark-report/
- Artisan Strategies — Feature adoption benchmarks (no methodology cited): https://www.artisangrowthstrategies.com/blog/feature-adoption-metrics-top-benchmarks-2025

**Retention, stickiness, power users**
- Amplitude — 7 steps to measuring the success of a feature: https://medium.com/@amplitudeHQ/7-steps-to-measuring-the-success-of-a-feature-21045ea640fb
- Amplitude docs — Stickiness: identify the features that drive users back: https://amplitude.com/docs/analytics/charts/stickiness/stickiness-identify-features
- Amplitude — Drive engagement and stickiness: https://amplitude.com/blog/drive-engagement-and-stickiness
- Andrew Chen — The power user curve: https://andrewchen.com/power-user-curve/
- a16z — The power user curve: https://a16z.com/the-power-user-curve-the-best-way-to-understand-your-most-engaged-users/
- Reforge — The power user trap (403 on fetch; pointer only): https://www.reforge.com/blog/the-power-user-trap

**Instrumentation, exposure, experiment design**
- Spotify Confidence — Reduce dilution and improve sensitivity with trigger analysis: https://confidence.spotify.com/blog/trigger-analysis
- ExP Platform (Kohavi/Deng) — Dilution: https://exp-platform.com/dilution/
- Microsoft Research — Patterns of trustworthy experimentation: post-experiment stage: https://www.microsoft.com/en-us/research/group/experimentation-platform-exp/articles/patterns-of-trustworthy-experimentation-post-experiment-stage/
- Spotify Engineering — Choosing a sequential testing framework: https://engineering.atspotify.com/2023/03/choosing-sequential-testing-framework-comparisons-and-discussions
- Johari, Pekelis, Walsh — Always valid inference: continuous monitoring of A/B tests: https://arxiv.org/pdf/1512.04922
- Analytics-Toolkit — Comparison of the statistical power of sequential tests: https://blog.analytics-toolkit.com/2022/comparison-of-the-statistical-power-of-sequential-tests/
- Donnu — Sequential testing and always-valid inference explained: https://donnuab.com/blog/en/sequential-testing-explained/
- Convert — Statistical power in A/B testing: https://www.convert.com/blog/a-b-testing/statistical-power/
- Atticus Li — Underpowered A/B tests: the silent killer: https://atticusli.com/blog/posts/underpowered-ab-tests-silent-killer-experimentation/
- Atticus Li — What is statistical power and why most A/B tests don't have enough: https://atticusli.com/blog/posts/statistical-power-why-most-ab-tests-underpowered/
- Amplitude — Incrementality testing: https://amplitude.com/explore/experiment/incrementality-testing
- Measured — What is a holdout test: https://www.measured.com/faq/holdout-test/

**Tooling: capability, mobile support, pricing**
- Appcues docs — Installing the mobile SDK: https://docs.appcues.com/mobile-installation-overview/installing-the-mobile-sdk
- Appcues — React Native module (GitHub): https://github.com/appcues/appcues-react-native-module
- Appcues — Expo module (GitHub): https://github.com/appcues/appcues-expo-module
- Appcues Engineering — Inside our cross-platform mobile SDKs: https://engineering.appcues.com/blog/building-cross-platform-mobile-frameworks-at-appcues
- Appcues pricing: https://www.appcues.com/pricing
- Apty — Appcues pricing (competitor-adjacent estimate): https://apty.ai/blog/appcues-pricing/
- Userpilot — Appcues pricing explained (competitor): https://userpilot.com/blog/appcues-pricing-explained/
- Pendo pricing: https://www.pendo.io/pricing/
- Pendo help — React Native with custom navigation (tooltip limitation): https://support.pendo.io/hc/en-us/articles/360038590491-React-Native-with-custom-navigation
- Pendo mobile SDK (GitHub): https://github.com/pendo-io/pendo-mobile-sdk
- Usercall — Pendo pricing breakdown (third-party estimate): https://www.usercall.co/post/pendo-pricing
- Supered — Pendo pricing by MAU (third-party estimate): https://www.supered.io/blog/pendo-pricing/
- Chameleon help — Will Chameleon work with my product (no native mobile): https://help.chameleon.io/en/articles/1204271-will-chameleon-work-with-my-product
- Chameleon pricing: https://www.chameleon.io/pricing
- Chameleon blog — product tour software (marketing content; contradicts help centre on mobile): https://www.chameleon.io/blog/product-tour-software
- Intercom pricing: https://www.intercom.com/pricing
- PostHog pricing: https://posthog.com/pricing
- PostHog — React Native SDK docs: https://posthog.com/docs/libraries/react-native
- Statsig pricing: https://www.statsig.com/pricing
- rn-tourguide (GitHub): https://github.com/xcarpentier/rn-tourguide
- npm registry API (versions and download counts verified directly, 2026-08-15): https://registry.npmjs.org/ and https://api.npmjs.org/downloads/point/last-week/

**FTF internal files consulted (read-only, for the implications section)**
- `backend/experiments.py` — layered assignment, SRM check, underpowered gate, design calculator, `exposure_note`
- `backend/analytics_taxonomy.py` — `ALLOWED_CLIENT_EVENTS`, `experiment_exposed`, coach-mark and guided-tour event names
- `config/features.json` — flag surface used for the feature-audit hypothesis
