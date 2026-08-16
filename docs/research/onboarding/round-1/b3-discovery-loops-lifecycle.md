# B3 — Feature-Discovery Loops Beyond the Immediate UI

**Round 1 research brief — lens B3**
**Date:** 2026-08-15
**Scope:** behavior-triggered nudges and lifecycle messaging; notification inboxes and activity feeds as discovery surfaces; gamification of *feature adoption* (not just usage); habit-formation frameworks and their empirical standing; weekly digests and year-in-review recaps; seasonality and returning-user re-onboarding.
**Out of scope (other lenses):** in-session progressive disclosure, IA/navigation, empty states, tooltips-in-the-moment, pricing/paywall sequencing.

---

## TL;DR

- **Behavior-triggered messaging beats scheduled blasts, but the honest effect size is much smaller than vendor marketing implies.** The best-controlled body of evidence on nudge-type interventions (126 RCTs, 23M people, two large nudge units) found an average effect of **1.4 percentage points / +8% over control**, versus **8.7pp / +33%** in published academic papers — a gap fully explained by publication bias ([DellaVigna & Linos, *Econometrica* 2022](https://onlinelibrary.wiley.com/doi/abs/10.3982/ECTA18709)). Treat any "74% lift" vendor claim as an upper bound from a self-selected case.
- **The one deeply-documented production system for notification-driven return is Duolingo's contextual bandit.** It was trained on ~200M practice reminders over 34 days, optimizes a single downstream behavior (lesson completed after receipt), compares notifications only within matched eligibility cohorts, and applies a forgetting-curve spacing rule to prevent habituation to any one message ([Duolingo blog](https://blog.duolingo.com/hi-its-duo-the-ai-behind-the-meme/)). Duolingo's own growth write-ups call notifications "a nearly infinite source of gains" but publish **no** per-experiment lift numbers — the credible claim is *many small compounding wins*, not one big one.
- **Notification frequency is the dose-limiting toxicity.** A field study of ~17,500 app users found uninstall probability rises monotonically with push frequency, and direct-open rate falls, with the damage concentrated in *non-personalized* sends ([Wohllebe et al., 2021](https://www.researchgate.net/publication/351932011_Mobile_apps_in_retail_Effect_of_push_notification_frequency_on_app_user_behavior)).
- **Notification inboxes/activity feeds as discovery surfaces are widely practiced but thinly evidenced.** The design distinction is real and useful (feeds = persistent, browsable, discovery-oriented; alerts = transient, action-oriented; [GetStream](https://getstream.io/blog/activity-feeds-app-notifications/)), but the headline stats circulating ("40% retention boost, 35% engagement increase") are unsourced vendor copy ([social.plus](https://www.social.plus/blog/top-7-companies-driving-app-growth-with-activity-feeds-with-examples)). **I found no controlled study isolating an inbox's effect on feature discovery.**
- **Gamification of feature adoption is the weakest link in the chain.** The strongest meta-analysis is on *learning* outcomes and finds small-to-moderate effects (cognitive g=0.49, motivational g=0.36, behavioral g=0.25), with the **behavioral** effect the least stable under methodological rigor ([Sailer & Homner 2020](https://eric.ed.gov/?id=EJ1245270)). Badge research on Stack Overflow shows badges **steer** effort toward badge-qualifying actions without clearly increasing total contribution ([Anderson et al., WWW 2013](https://www.cs.cornell.edu/home/kleinber/www13-badges.pdf)) — which is arguably *exactly* what you want for feature discovery, and arguably a warning about gaming.
- **Habit-formation frameworks are design heuristics, not validated theory.** The Fogg Behavior Model has ~2,000+ citations but **no published RCTs testing its core predictions** ([scoping review, 2025](https://pubmed.ncbi.nlm.nih.gov/41088011/)); the Hooked model's variable-reward step is contested on basic behavioral-science grounds ([Behavioral Scientist](https://www.thebehavioralscientist.com/articles/hooked-how-to-build-habit-forming-products-is-wrong)). The best-evidenced habit finding is descriptive: median 66 days to automaticity, range 18–254 ([Lally et al. 2010](https://onlinelibrary.wiley.com/doi/abs/10.1002/ejsp.674)).
- **Annual recaps are the most reliably-measured depth-discovery mechanism available.** Spotify Wrapped produced **~+14% DAU day-over-day in 2022 and ~+13% in 2023** while Wrapped ad spend fell 60% YoY — i.e. the *product* mechanic, not the marketing, carries it ([Sensor Tower](https://sensortower.com/blog/spotify-wrapped-is-on-a-roll)).
- **Returning users are a distinct population and must not be re-onboarded as new users.** Google Play's lifecycle framing (7-day lapsed / 14-day lapsed / 28-day churned; "increase in time between core actions" as the leading indicator) plus "welcome back / pick up where you left off / what's new" re-entry is the standard playbook ([Google Play](https://medium.com/googleplaydev/the-user-journey-disengagement-and-reactivation-6e34fe04694a)).

---

## 1. Behavior-triggered nudges and lifecycle messaging

### 1.1 Calibrating what a "lift" is worth

Every lifecycle-marketing vendor publishes a big number. The most important corrective in this entire brief is DellaVigna & Linos (2022), who assembled all 126 RCTs run by two of the largest US nudge units — 23 million individuals — and compared them to nudge trials published in academic journals. Academic-journal nudges averaged an **8.7 percentage-point** take-up effect (+33.4% over control). The same class of intervention run at scale by practitioners averaged **1.4 percentage points** (+8.0%). Publication bias plus low statistical power accounted for the full difference. Notably, *practitioners* forecast the small effects accurately; academics overestimated ([NBER working paper](https://www.nber.org/system/files/working_papers/w27594/w27594.pdf)).

The transferable rule: **a well-targeted behavioral message moves a target behavior by single-digit percent, not by multiples.** Design the measurement so single-digit effects are detectable, and expect the value to come from many small compounding wins rather than one hero campaign. This is exactly the shape Duolingo describes.

### 1.2 The bandit-over-blast pattern (Duolingo — the deepest published case)

Duolingo's public engineering description is the most concrete production system on record ([blog.duolingo.com](https://blog.duolingo.com/hi-its-duo-the-ai-behind-the-meme/)):

- It is a **bandit algorithm**: repeatedly choose among a fixed set of notification copy options; learn which ones drive the downstream outcome.
- The training set was **~200 million practice reminders collected over 34 days**; the live system processes tens of millions of records per week.
- It optimizes for **one downstream behavior** — did the learner complete a lesson after receiving this? — not opens or clicks.
- **Fair-comparison cohorts:** notifications are only compared among learners with equivalent eligibility (same language, streak state, day of week). This is the methodological detail most teams skip and it is what makes the scores meaningful.
- **Anti-habituation:** the system applies the same forgetting-curve spacing used for vocabulary review to avoid over-exposing any single message.
- **Personalization findings are segment-specific and non-obvious:** "Time for [language]" performs very well for Chinese learners and poorly for English learners. Novel notifications outperform worn-in ones.
- Reported result is qualitative: within weeks, "more learners were completing lessons more frequently," reaching tens of thousands of returning learners.

Duolingo's growth write-ups reinforce the *pattern* rather than any single number. Jorge Mazal's account reports DAU up **4.5x over four years**, CURR (current-user retention) up **21%** — over a 40% reduction in daily churn — and the share of DAU with a 7+ day streak nearly **tripling to more than half of DAU**; notifications contributed "dozens of small- and medium-size wins" with no individual figures published ([Lenny's Newsletter](https://www.lennysnewsletter.com/p/how-duolingo-reignited-user-growth)). A companion piece quantifies the compounding logic: a 1% retention improvement on a 100k-DAU base compounds materially within weeks, and roughly **50% of Duolingo experiments succeed** ([Lenny's Newsletter](https://www.lennysnewsletter.com/p/the-secret-to-duolingos-growth)).

### 1.3 Frequency and personalization: the harm side

The clearest causal-ish evidence on harm comes from a retail-app field study of ~**17,500 users**: as *non-personalized* push frequency rises, uninstall probability rises and direct-open rate falls ([Wohllebe et al., 2021](https://www.researchgate.net/publication/351932011_Mobile_apps_in_retail_Effect_of_push_notification_frequency_on_app_user_behavior)). The authors' operational recommendation is a per-message relevance test: every standardized send should be checked for whether it adds user value.

Vendor benchmark literature reports behavior/event-triggered pushes clearing **3–4% CTR** versus **<2%** for broadcast, and Airship's benchmark series segments opt-in, direct-open, and monthly-sends-per-user by category (Sports & Recreation is a reported vertical) at the 10th/50th/90th percentiles ([Airship 2026 benchmarks](https://www.airship.com/resources/mobile-app-push-notification-benchmarks-2026/); [Business of Apps](https://www.businessofapps.com/marketplace/push-notifications/research/push-notifications-statistics/)). I could not extract the underlying numbers — both are gated PDFs — so the category medians should be pulled directly before being used as targets.

### 1.4 Channel choice for *feature* discovery specifically

Push is the wrong instrument for teaching depth; it is a return trigger. The depth teaching happens in-session. Practitioner sources claim in-app messages are "8x more effective at engaging users than push" ([Appcues](https://www.appcues.com/blog/improve-feature-adoption-in-app-messaging)) — an unsourced figure, but the directional argument is sound and mechanically obvious: an in-app message reaches a user who is already in context and already has the feature one tap away.

The soberest number in the feature-adoption literature comes from Pendo's aggregate product data: **~6.4% of features drive 80% of click volume**, i.e. roughly 94% of shipped features get near-zero engagement; top-quartile products reach 15.6% adoption, ~2.5x the average; media products are lowest at 4.9% ([Pendo](https://www.pendo.io/pendo-blog/feature-adoption-benchmarking/)). For a feature-dense app, this is the baseline condition to design against — not an anomaly.

---

## 2. Notification inboxes and activity feeds as discovery surfaces

The useful design distinction ([GetStream](https://getstream.io/blog/activity-feeds-app-notifications/)):

| | Activity feed / inbox | Transient in-app notification |
|---|---|---|
| Lifespan | Persistent, revisitable | Ephemeral |
| Intent | Discovery, ambient awareness | Immediate action |
| Content | Progress logs, community/network activity, milestones | Time-sensitive alerts |
| Discovery role | Passive browsing surface — users encounter things they didn't know to look for | Interrupt |

Documented design patterns that make a feed function as *discovery* rather than noise: algorithmic/personalized ranking; social signals (Duolingo surfaces friends' streak milestones); **contextual linking — every notification links to its related feed item**, so the alert is a doorway into a fuller context rather than a dead end; and segmentation triggers that surface different card types by user attributes.

Confluence's activity-feed case study frames the goal well — turning the product "from a black box into a town square," with feeds surfacing content that was relevant but that users didn't know existed ([Andrew Nelson](https://andrewnelson.design/project/activity-feed)). Knock's B2B write-up makes the parallel argument that an in-product feed reduces reliance on email and keeps discovery inside the app ([Knock](https://knock.app/blog/the-benefits-of-adding-an-activity-feed-to-your-product)).

**Evidence caveat, stated plainly:** the widely-recirculated "activity feeds boost retention 40%, engagement 35%, growth 30%, revenue 2.8x" figure appears in vendor copy with **no source or methodology** ([social.plus](https://www.social.plus/blog/top-7-companies-driving-app-growth-with-activity-feeds-with-examples)). Company examples cited (Strava 100M+ users, Venmo 60M, Tripadvisor 150M monthly mobile uniques, Vivino 26M) demonstrate that successful apps have feeds; they do not isolate the feed's contribution. I found **no controlled experiment** measuring a notification inbox's effect on feature discovery. This is a genuine gap in the public literature and a reason to treat FTF's own inbox as an experiment platform rather than a settled pattern.

A related pattern worth noting: **changelog-as-surface** — Drift's "Now In Drift" sidebar lists newly shipped features as an always-available, user-pulled discovery panel ([Userpilot](https://userpilot.com/blog/improve-feature-discovery-product-adoption/)). This is the lowest-risk form of inbox-based discovery because it is pull, not push.

---

## 3. Gamification applied to feature adoption

### 3.1 The meta-analytic base is about learning, and it is modest

Sailer & Homner's meta-analysis (Educational Psychology Review, 2020) — the most cited rigorous synthesis — found significant but **small** effects of gamification: cognitive *g* = 0.49 (k=19, N=1,686), motivational *g* = 0.36 (k=16, N=2,246), behavioral *g* = 0.25 (k=9, N=951). Critically: **the cognitive effect held up in a subsplit of high-methodological-rigor studies; the motivational and behavioral effects were less stable** ([ERIC record](https://eric.ed.gov/?id=EJ1245270)). Behavioral change is precisely the outcome feature-adoption gamification needs, and it is the weakest and least stable of the three. Reported moderator analysis suggests reward-and-status mechanics alone underperform designs that add challenge, meaningful goals, and narrative.

Two independent transfer problems apply to FTF:

1. **Domain transfer.** These are classroom/learning-task studies. Duolingo's own experience shows domain-mismatched mechanics fail: a Gardenscapes-style "moves counter" was tested and came back "**completely neutral. No change to our retention. No increase in DAU**," because strategic move-budgeting has no meaning in language learning ([Lenny's Newsletter](https://www.lennysnewsletter.com/p/how-duolingo-reignited-user-growth)). Their Uber-style referral program lifted new users by only **3%**. Mechanics must map to something the user already cares about.
2. **Target transfer.** Gamifying *frequency of use* (streaks, leagues) is not the same problem as gamifying *breadth of feature use*. Almost all published gamification success is on frequency/volume. Breadth is closer to a checklist/completion problem.

### 3.2 Badges: steering effort, not creating it

Anderson, Huttenlocher, Kleinberg & Leskovec analyzed several million Stack Overflow users and modeled the deviation in action distributions around badge thresholds ([WWW 2013 PDF](https://www.cs.cornell.edu/home/kleinber/www13-badges.pdf)). The finding, and its caveat, are both important:

- Users measurably increase badge-qualifying activity as they approach a threshold ("steering").
- But the effect appears to **redirect existing effort toward recognized activities rather than generate net new contribution**, and effort can be pulled away from other valuable-but-unbadged actions.

For feature *discovery*, steering is arguably the desired outcome — you explicitly want to redirect a user's existing session time toward a feature they've never opened. The warning is that badges do not manufacture engagement out of nothing, and they can starve whatever isn't badged. Follow-up work argues badge response is heterogeneous across user types ([Yanovsky et al., JASIST 2021 — "One Size Does Not Fit All"](https://asistdl.onlinelibrary.wiley.com/doi/10.1002/asi.24409); I was unable to parse the full text, so treat this as a pointer rather than a cited finding).

### 3.3 Streaks outside learning: real, and not free

Streaks are the single most-credited Duolingo mechanic — PMs there call them "the product's most important lever in driving DAUs," with ~9M users holding year-plus streaks, and the loss-aversion effect strengthening as the streak lengthens ([Deconstructor of Fun](https://www.deconstructoroffun.com/blog/2025/4/14/duolingo-how-the-15b-app-uses-gaming-principles-to-supercharge-dau-growth)). Leaderboards, on the fourth iteration, produced **D1 +1%, D7 +2%, D14 +3% retention and +17% time spent learning**, with highly-engaged learners tripling.

The counterweight is the Snapchat-streak literature, which studies the same mechanic in a non-learning social app: streaks are associated with obligation, anxiety, late-night use, and distress on loss, and correlate with problematic smartphone use and FOMO among early adolescents ([Zsila et al. / ScienceDirect](https://www.sciencedirect.com/science/article/pii/S2772503023000476); [ResearchGate record](https://www.researchgate.net/publication/372726551_Snapchat_Streaks_-_how_are_these_forms_of_gamified_interactions_associated_with_smartphone_dependency_and_fear_of_missing_out_among_early_adolescents)). A streak works by making absence costly. If the underlying activity is not something the user independently wants to do daily, the mechanic manufactures guilt rather than value.

### 3.4 Where gamification has been retired

The negative cases are instructive because they are rarely written up as experiments:

- **Google News** removed its reading badges.
- **Fitbit/Google Health** removed badges entirely in a mandatory update rolled out 19–26 May 2026, deleting historical badges and ceasing new badge generation, along with sleep animals and social features ([Gadgets & Wearables](https://gadgetsandwearables.com/2026/05/08/google-health-app/); [TechRadar](https://www.techradar.com/health-fitness/why-does-technology-just-keep-getting-less-fun-fitbit-users-are-mad-about-losing-key-features-as-a-result-of-the-huge-google-health-changes-but-i-want-to-hear-what-you-think)). Note the user reaction: the removal was widely experienced as making the product "less fun," which is itself evidence the mechanic had real attachment value.
- **Foursquare** stripped its gamification in a redesign.
- Gartner's oft-cited prediction that **80% of gamified applications would fail to meet their objectives**, attributed to fixation on points and badges over meaningful motivation, dates to 2012 and is a forecast, not a measurement ([TechCrunch report](https://techcrunch.com/?p=706231)).

**Assessment:** gamification of *feature discovery* outside learning apps has no strong published evidence base. The defensible position is that completion-style mechanics (checklists, "you've used 4 of 9 tools") are lower-risk and better-matched to breadth goals than status/competition mechanics, and that streaks should be attached only to a behavior the user would want to repeat anyway.

---

## 4. Habit-formation frameworks: what they're actually worth

- **Fogg Behavior Model (B = MAP).** Widely used as a design vocabulary. But the original is a **conference paper, not peer-reviewed journal work**; a 2025 scoping review of its use in behavior-change interventions found that despite 2,000+ citations, **most citing papers apply it as a design framework rather than test its predictions, and there are no published RCTs testing its core predictions** ([PubMed](https://pubmed.ncbi.nlm.nih.gov/41088011/); [Behavioral Scientist explainer](https://www.thebehavioralscientist.com/articles/fogg-behavior-model)). Its components (motivation, friction, cueing) rest on established science; the *model as stated* does not.
- **Hooked (Eyal).** The sharpest published critique argues two of the four steps are wrong as sequenced: (a) **variable rewards** are contraindicated for *establishing* a new behavior — continuous reinforcement establishes, variable schedules maintain, so a product teaching a new behavior should be reliably rewarding first; (b) **investment** is not a discrete post-reward phase — in practice most successful products collect investment during onboarding and continuously, not as a trailing step. The alternative offered is unglamorous: be Effective, Easy, Enjoyable, Exciting; habits form when a product reliably solves a recurring problem ([Behavioral Scientist](https://www.thebehavioralscientist.com/articles/hooked-how-to-build-habit-forming-products-is-wrong)).
- **Lally et al. (2010)** remains the best-evidenced empirical habit finding: 96 participants, daily self-report over 84 days, **median 66 days to 95% of asymptotic automaticity, range 18–254 days**, and missing a single occasion did not materially damage formation ([Wiley](https://onlinelibrary.wiley.com/doi/abs/10.1002/ejsp.674)). Two implications: habit timelines are long and highly variable, and a **single missed day should not be punished** — which is the empirical case for streak freezes.

**Net:** use these frameworks to generate hypotheses and to structure vocabulary. Do not use them as evidence that a design will work.

---

## 5. Weekly digests and year-in-review as depth-discovery

**Annual recap (strongest evidence).** Spotify Wrapped's measured product effect, per third-party app-intelligence data: downloads spiked **~+90% day-over-day in 2022** and **~+60% in 2023**; DAU rose **+14%** and **+13%** day-over-day respectively. Meanwhile Wrapped's share of Spotify ad spend fell from **12% of overall spend in 4Q22 to 5% in 4Q23** — a ~60% cut with essentially unchanged DAU effect ([Sensor Tower](https://sensortower.com/blog/spotify-wrapped-is-on-a-roll)). That decoupling is the single most useful fact here: the recap's pull is intrinsic to the artifact, not bought. Spotify separately reported 225M+ MAUs engaging with Wrapped content in Q4 2023, up 40%+ YoY (as reported in secondary coverage). Strava runs the same annual play with "Year in Sport," deliberately built as a **mobile-app-only, in-app experience** — you cannot see it on the web, which forces the app open ([Strava support](https://support.strava.com/en-us/articles/15401959-your-year-in-sport); [Strava press](https://press.strava.com/articles/strava-releases-12th-annual-year-in-sport-trend-report-2025)).

**Weekly digest.** Grammarly's Weekly Progress Report is the canonical example: sent every Monday to every user, deliberately scheduled to avoid overlap with other campaigns, and prioritized *above* promotional email in the send hierarchy. It reports activity, mastery, and vocabulary, benchmarks the user against other users, and — the discovery-relevant part — **dynamically inserts content to provide a logical next step** based on what the user did ([Vero teardown](https://www.getvero.com/resources/grammarly/); [Grammarly support](https://support.grammarly.com/hc/en-us/articles/115000090892-Common-questions-about-weekly-Grammarly-Insights-reports)). Grammarly treats it as a *product feature* rather than a marketing campaign. **No public lift numbers exist** for it; claims that recap emails outperform promotional emails on open rate are asserted, not measured ([Failory](https://newsletter.failory.com/p/surprising-effectiveness-recap-emails)).

The mechanism worth stealing is structural rather than statistical: a periodic recap is the one message a user opens *voluntarily and about themselves*, which makes it the cheapest place to attach a "here's the thing you haven't tried" recommendation without it reading as promotion.

---

## 6. Seasonality and re-onboarding returning users

**Seasonality is a recognized ASO/lifecycle discipline.** Sports apps are explicitly named as event-driven seasonal categories, with fantasy-league apps spiking around major competitions; the standard guidance is to plan seasonal campaigns **2–3 months in advance**, refresh metadata/creative to seasonal intent, and avoid leaving stale seasonal content up in the trough ([AppTweak](https://www.apptweak.com/en/aso-blog/app-store-seasonality)). I was unable to obtain fantasy-football-specific download/usage seasonality data (Sensor Tower's fantasy-sports cuts were not publicly retrievable within this session) — flagged as an open gap.

**Lifecycle segmentation for lapse.** Google Play's framework is the most concrete public one ([Google Play Apps & Games](https://medium.com/googleplaydev/the-user-journey-disengagement-and-reactivation-6e34fe04694a)):

- **7-day lapsed** = no session in 7–13 days; **14-day lapsed** = 14–20; **churned** = 28+ days.
- Illustrative magnitude (dating category): 42% of users lapsed 7–13 days in a month, 26% lapsed 14–20, 12% lapsed 21–27. Lapse is the normal state, not the exception.
- **Leading indicator:** "increase in time between core actions" predicts involuntary lapse *before* it happens — an in-product signal, available without any messaging.
- **Voluntary vs involuntary lapse** are different problems: intent-driven absence (season ended) vs forgetting. Only the second is a messaging problem.
- Recovery cost rises with time away; recently-lapsed users are cheaper to reactivate than long-churned ones.

**Re-entry design.** The consistent cross-source recommendation is that returning users get a distinct entry experience, not the new-user flow: a one-screen progress recap, "welcome back" acknowledgment, "pick up where you left off" when state is retained, **"what's new since you were gone"** pointers, a returning-user banner surfacing **a single** high-value action, and an opt-in re-onboarding for users gone 30+ days ([Helpshift](https://www.helpshift.com/blog/re-engagement-campaigns-for-mobile-games/); [Google Play](https://medium.com/googleplaydev/the-user-journey-disengagement-and-reactivation-6e34fe04694a)). Helpshift states the rule bluntly: "Returning players are not new players, and treating them like new players is one of the fastest ways to lose them."

**Reactivation case data (vendor-reported, uncontrolled):** AvaTrade reported +12% conversion to real-account registration from re-engagement messaging; Beach Bum Games reported 3x DAU/MAU/subscribers and 3x push CTR from personalized re-engagement with custom notification sounds ([Pushwoosh](https://www.pushwoosh.com/blog/re-engage-mobile-app-users/)). These are self-selected success stories with no control group; use them as existence proofs, not as forecasts.

---

## Evidence quality notes

**Tier A — peer-reviewed, controlled, or large-N:**
- DellaVigna & Linos (2022), *Econometrica* — 126 RCTs, 23M subjects, includes publication-bias analysis. The best calibration source in this brief.
- Sailer & Homner (2020), *Educational Psychology Review* — meta-analysis with rigor-subsplit sensitivity analysis. Note the small k values (9–19 studies per outcome).
- Anderson et al. (2013), WWW — millions of users, threshold-based identification. Observational with a model, not an RCT.
- Lally et al. (2010) — small (N=96), self-report, but the field's reference point; correctly interpreted as descriptive.
- Wohllebe et al. (2021) — ~17,500 users, real app, but a single retail app; the original PDF returned 403 and the specific figures here come from secondary summaries and should be verified against the paper before being used in a decision.

**Tier B — credible first-party practitioner accounts, no controls published:**
- Duolingo's own engineering blog and the Mazal/Lenny's write-ups. These describe real systems and real experiments and openly report failures (moves counter: neutral; referral: +3%), which raises their credibility. But almost all wins are reported without magnitudes.
- Sensor Tower's Wrapped analysis — third-party panel-estimated data; directionally strong, methodology proprietary, and day-over-day comparisons don't tell us persistence.
- Google Play's lifecycle framework — platform-authored, widely adopted, but the quantitative example is a single category illustration.

**Tier C — vendor marketing; treat as hypothesis-generating only:**
- "In-app messages are 8x more effective than push" (Appcues), "activity feeds boost retention 40%" (social.plus), "74% engagement lift from AI-personalized push" (Braze, via aggregator), "6% of users abandon an app after one push per week / up to 40%" (aggregator). None carry methodology. The Amra & Elma and sci-tech-today statistics pages in particular are content-farm aggregations and were not relied on for any claim above.
- Pendo's 6.4% figure sits between B and C: it's from a real aggregate dataset the vendor owns, but is self-published without methodology detail.

**Known gaps I could not close in this session:**
1. No controlled evidence anywhere for **notification inboxes as feature-discovery surfaces** specifically.
2. Airship's category benchmarks (Sports & Recreation opt-in / direct-open / sends-per-user) are behind gated PDFs — retrieve before setting targets.
3. No public fantasy-sports-specific seasonality curves (draft-season peak magnitude, offseason trough depth, trade-deadline spike).
4. No published lift figures for any weekly-digest product (Grammarly included).
5. WebSearch quota was exhausted mid-brief; several intended queries (Braze Content Cards inbox performance, Apple activity-rings adherence research, dynasty-specific traffic seasonality, win-back benchmarks) were not run.

---

## Implications for FTF — hypotheses only

These are hypotheses to test, not recommendations to ship. Each is stated with the evidence it leans on and the reason it might not transfer.

1. **Optimize the notification inbox on a downstream behavior, not on opens.** Duolingo's bandit scores notifications by *lesson completed after receipt*. FTF's analogue is "trade viewed/sent/board edited after receipt," not tap-through. *Risk:* FTF's send volume is orders of magnitude smaller than 200M/34 days; a full bandit is almost certainly over-engineered at current scale, and matched-cohort comparison may be impossible with small N. A ranked-rules system with holdouts is the scale-appropriate version.
2. **Every push should have a matching inbox card, and every card should deep-link to its context.** Contextual linking is the one feed-design pattern with consistent cross-source support, and it converts a transient interrupt into a persistent, re-findable discovery surface. Cheap given the inbox already shipped.
3. **Treat the inbox as a changelog/"what's new" surface, not only an events surface.** Pull-based feature announcement (Drift's "Now In Drift") is the lowest-risk discovery mechanism available and does not consume notification budget. *Test:* does a "new in FTF" card type increase first-use of the named feature within 7 days?
4. **The single highest-leverage seasonal artifact is probably a "Your Dynasty Year in Review."** Wrapped's DAU effect held while its ad spend was cut 60%, and Strava deliberately makes theirs app-only. Fantasy football has an unusually well-defined annual boundary (post-Super Bowl / pre-draft), and FTF holds data no competitor holds: matchup votes cast, Elo movement of the user's roster, trades explored vs sent, board churn. *Hypothesis:* a recap is the best-tolerated vehicle for feature discovery because the user opens it voluntarily and it's about them — attach one "you never tried X" module to it. *Risk:* recaps reward users with lots of history; new/light users get an embarrassing artifact. Segment or suppress.
5. **A weekly in-season digest ("your week in dynasty") is the seasonal-cadence version of the same bet.** Grammarly's structural choices are the ones to copy: fixed day, protected from campaign collision, prioritized above promotional sends, and **dynamically inserting a logical next step**. That next-step slot is the feature-discovery payload. *Risk:* in a weekly-decision sport the digest competes with the user's league app; it must say something the league app cannot.
6. **Seasonal re-onboarding deserves its own flow, distinct from onboarding.** Fantasy is the archetypal seasonal app: a large share of users will be 28+ day churned every offseason, and lapse will be overwhelmingly *voluntary* (season ended), which is a re-entry-design problem more than a messaging problem. *Hypothesis:* a returning-user entry state — roster diff since last visit, one high-value action, "what's new since you were gone" — outperforms both the new-user flow and the default home screen. Plan the pre-draft campaign 2–3 months ahead per seasonal-ASO practice.
7. **Use "time between core actions" as the in-product lapse predictor** rather than waiting for a 7/14/28-day silence. It is available today from existing analytics and needs no messaging infrastructure to be useful — it can drive an *in-app* nudge while the user is still present, which avoids spending push budget.
8. **If gamifying, gamify breadth as completion, not as status.** The evidence for behavioral gamification effects is the weakest tier of the meta-analysis and least stable under rigor; badges provably *steer* effort toward badged actions but don't clearly create net new effort. A "features explored" checklist maps directly onto the breadth goal; leagues/leaderboards map onto frequency and import social pressure FTF may not want. *Corollary:* if a streak is ever introduced, attach it to a behavior a dynasty manager would repeat anyway (weekly roster check) and implement a streak-freeze — Lally's finding that one missed occasion doesn't damage habit formation is the empirical justification.
9. **Set effect-size expectations before running anything.** Calibrate on DellaVigna & Linos: a good lifecycle intervention is worth low single-digit percent on the target behavior. Power the experiments accordingly, or accept that most results will be uninterpretable and the program will be run on anecdote.
10. **Cap frequency and enforce a relevance test per send.** The one reasonably-controlled harm finding is that non-personalized push frequency raises uninstalls and lowers open rates. For a seasonal app, the offseason is exactly when frequency temptation is highest and relevance is lowest.

---

## Sources

**Peer-reviewed / academic**
- DellaVigna, S. & Linos, E. (2022). *RCTs to Scale: Comprehensive Evidence from Two Nudge Units.* Econometrica. https://onlinelibrary.wiley.com/doi/abs/10.3982/ECTA18709 · NBER WP: https://www.nber.org/system/files/working_papers/w27594/w27594.pdf
- Sailer, M. & Homner, L. (2020). *The Gamification of Learning: A Meta-Analysis.* Educational Psychology Review 32, 77–112. https://eric.ed.gov/?id=EJ1245270
- Anderson, A., Huttenlocher, D., Kleinberg, J. & Leskovec, J. (2013). *Steering User Behavior with Badges.* WWW '13. https://www.cs.cornell.edu/home/kleinber/www13-badges.pdf
- Yanovsky, S. et al. (2021). *One Size Does Not Fit All: A Study of Badge Behavior in Stack Overflow.* JASIST. https://asistdl.onlinelibrary.wiley.com/doi/10.1002/asi.24409
- Lally, P. et al. (2010). *How are habits formed: Modelling habit formation in the real world.* European Journal of Social Psychology. https://onlinelibrary.wiley.com/doi/abs/10.1002/ejsp.674
- Scoping review of the Fogg Behavior Model in behavior-change interventions (2025). https://pubmed.ncbi.nlm.nih.gov/41088011/
- Wohllebe, A. et al. (2021). *Mobile apps in retail: Effect of push notification frequency on app user behavior.* https://www.researchgate.net/publication/351932011_Mobile_apps_in_retail_Effect_of_push_notification_frequency_on_app_user_behavior
- *Snapchat streaks — gamified interactions, problematic smartphone use and FOMO among early adolescents.* ScienceDirect. https://www.sciencedirect.com/science/article/pii/S2772503023000476 · https://www.researchgate.net/publication/372726551_Snapchat_Streaks_-_how_are_these_forms_of_gamified_interactions_associated_with_smartphone_dependency_and_fear_of_missing_out_among_early_adolescents

**First-party practitioner accounts**
- Duolingo. *Hi, it's Duo — the AI behind the meme.* https://blog.duolingo.com/hi-its-duo-the-ai-behind-the-meme/
- Mazal, J. *How Duolingo reignited user growth.* Lenny's Newsletter. https://www.lennysnewsletter.com/p/how-duolingo-reignited-user-growth
- *The secret to Duolingo's exponential growth.* Lenny's Newsletter. https://www.lennysnewsletter.com/p/the-secret-to-duolingos-growth
- Google Play Apps & Games. *The user journey: disengagement and reactivation.* https://medium.com/googleplaydev/the-user-journey-disengagement-and-reactivation-6e34fe04694a
- Strava. *Your Year in Sport* (support). https://support.strava.com/en-us/articles/15401959-your-year-in-sport · Press release. https://press.strava.com/articles/strava-releases-12th-annual-year-in-sport-trend-report-2025
- Grammarly Support. *Common questions about weekly Grammarly Insights reports.* https://support.grammarly.com/hc/en-us/articles/115000090892-Common-questions-about-weekly-Grammarly-Insights-reports

**Third-party analysis / industry data**
- Sensor Tower. *Spotify Wrapped is on a Roll.* https://sensortower.com/blog/spotify-wrapped-is-on-a-roll
- Deconstructor of Fun. *Duolingo: How the $15B App uses Gaming Principles to Supercharge DAU Growth.* https://www.deconstructoroffun.com/blog/2025/4/14/duolingo-how-the-15b-app-uses-gaming-principles-to-supercharge-dau-growth
- Airship. *Mobile App Push Notification Benchmarks 2026.* https://www.airship.com/resources/mobile-app-push-notification-benchmarks-2026/ · 2025 report PDF: https://growth.airship.com/rs/313-QPJ-195/images/Airship-2025-Push-Notification-Benchmarks-EN.pdf
- Business of Apps. *Push Notifications Statistics (2026).* https://www.businessofapps.com/marketplace/push-notifications/research/push-notifications-statistics/
- Pendo. *Why feature adoption may be your biggest weakness—or strength.* https://www.pendo.io/pendo-blog/feature-adoption-benchmarking/
- AppTweak. *App store seasonality.* https://www.apptweak.com/en/aso-blog/app-store-seasonality
- Vero. *How Grammarly Built an Email Product Users Love.* https://www.getvero.com/resources/grammarly/
- Gadgets & Wearables. *Google Health app drops badges, sleep animals and social features.* https://gadgetsandwearables.com/2026/05/08/google-health-app/
- TechRadar. *Fitbit badges and sleep animals removed in Google Health migration.* https://www.techradar.com/health-fitness/why-does-technology-just-keep-getting-less-fun-fitbit-users-are-mad-about-losing-key-features-as-a-result-of-the-huge-google-health-changes-but-i-want-to-hear-what-you-think
- TechCrunch. *Badges Beware: 80% Of Gamification Apps Will End Up Being Losers, Says Gartner.* https://techcrunch.com/?p=706231

**Opinion / critique**
- The Behavioral Scientist. *Hooked: How to Build Habit Forming Products Is Wrong.* https://www.thebehavioralscientist.com/articles/hooked-how-to-build-habit-forming-products-is-wrong
- The Behavioral Scientist. *The Fogg Behavior Model: B = MAP.* https://www.thebehavioralscientist.com/articles/fogg-behavior-model
- Amplitude. *The Hook Model.* https://amplitude.com/blog/the-hook-model

**Vendor / practitioner guides (Tier C — assertions, not measurements)**
- GetStream. *Activity Feeds vs In-App Notifications.* https://getstream.io/blog/activity-feeds-app-notifications/
- Knock. *The benefits of adding an activity feed to your B2B product.* https://knock.app/blog/the-benefits-of-adding-an-activity-feed-to-your-product
- social.plus. *Top 7 companies driving app growth with activity feeds.* https://www.social.plus/blog/top-7-companies-driving-app-growth-with-activity-feeds-with-examples
- Andrew Nelson. *Activity Feed — UX Case Study (Confluence).* https://andrewnelson.design/project/activity-feed
- Appcues. *How to drive feature adoption with in-app messaging.* https://www.appcues.com/blog/improve-feature-adoption-in-app-messaging
- Userpilot. *How to Use Feature Discovery to Improve Product Adoption.* https://userpilot.com/blog/improve-feature-discovery-product-adoption/
- Helpshift. *Re-Engagement Campaigns For Mobile Games: 2026 Playbook.* https://www.helpshift.com/blog/re-engagement-campaigns-for-mobile-games/
- Pushwoosh. *How to re-engage inactive users.* https://www.pushwoosh.com/blog/re-engage-mobile-app-users/
- Customer.io. *Push notification metrics.* https://customer.io/learn/mobile-marketing/push-notification-metrics
- Braze. *Essential mobile app metrics and engagement KPIs.* https://www.braze.com/resources/articles/essential-mobile-app-metrics-formulas
- Failory. *The Surprising Effectiveness of Recap Emails.* https://newsletter.failory.com/p/surprising-effectiveness-recap-emails
