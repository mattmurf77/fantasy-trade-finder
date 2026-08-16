# R2-3B — Recap Artifacts, Digests, and Inbox Content Strategy as Feature-Discovery Mechanisms

**Round-2 research brief — lens 3B · Date: 2026-08-15**
**Scope:** anatomy of Wrapped-class annual recaps; smaller-cadence recaps; share-card virality and fantasy share culture; notification-inbox content strategy; digest engineering; iOS provisional push in practice.
**Relationship to round 1:** drills into the recap/digest/inbox sections of [`round-1/b3-discovery-loops-lifecycle.md`](../round-1/b3-discovery-loops-lifecycle.md), and targets the open questions in [`2026-08-13-dynasty-year-in-review-plan.md`](../../../business/product/2026-08-13-dynasty-year-in-review-plan.md) — stat selection, share mechanics, tone, and the P3/P4 build.

---

## TL;DR

- **The recap funnel is now measurable.** Wrapped 2025 reached **200M engaged users in 24 hours** (vs. 62 hours in 2024, +19% YoY) and **~500M shares in the first 24 hours (+41% YoY)**, finishing at **300M+ users and 630M shares** — roughly **2.1 shares per engaged user** ([MBW](https://www.musicbusinessworldwide.com/spotify-wrapped-campaign-hit-200m-engaged-users-in-24-hours-a-19-yoy-increase/), [Music Week](https://www.musicweek.com/digital/read/spotify-wrapped-2025-was-biggest-ever-with-200-million-engaged-users/093178)). Spotify defines "engaged user" as *viewed at least one story*, and counts screenshots as shares — both worth copying as metric definitions.
- **The best published finding on stat selection comes from Duolingo, not Spotify.** Their XP-percentile stat lifted share rates — but **learners in the top 10% of XP earners produced more than half of all shares**. The fix was *archetypes* ("learner style personalities") everyone qualifies for, which "significantly boosted share rates" ([Duolingo](https://blog.duolingo.com/year-in-review-behind-the-scenes)). Rank stats are vanity goods that concentrate sharing in the top decile; identity labels distribute it.
- **Wrapped 2024 is the negative case.** Spotify cut top genres and top albums for AI-generated commentary; execs conceded it was the biggest-reach Wrapped ever *and* drew "more negative feedback than they've seen before" ([Music Ally](https://musically.com/2025/05/30/spotify-execs-talk-superfans-ai-and-wrapped-2024-backlash/)). Recap value lives in specific verifiable facts; generated narration is not a substitute for them.
- **In-app inboxes have real read-rate data — it just isn't recent.** Airship's 2016 study (83 apps, **1.15B message-center messages**) found iOS 90th-percentile read rates of **44%**, median **8x** push direct-taps, read rates **more than doubling** when a card is paired with a push, **+23%** with a home-screen badge, and — most importantly — **25% read rates among push-opted-*out* users** ([Airship](https://www.airship.com/newsroom/new-urban-airship-study-finds-in-app-message-centers-generate-eight-times-m/)). Observational and a decade old, but large-N with a stated methodology.
- **The only inbox figure with a control group is Braze/Equinox: +21% engagement over control.** The rest of the Content Cards corpus is self-selected — Wondery's engagers listened to **64% more episodes/week**; MARVEL SNAP's cards were the **first interaction point for 96% of users** and drove **86% of traffic** to a campaign page ([Braze](https://www.braze.com/customers/wondery-case-study), [Braze](https://www.braze.com/customers/second-dinner-case-study)).
- **Send-time optimisation has one credible causal estimate and it is small.** A microrandomized trial (N=1,255, 89 days) found a tailored push made users **3.9% more likely** to engage within 24h (RR 1.039, CI 1.01–1.08), rising to **8.7% on weekends** and **11.8% at 12:30pm weekends**, with no significant decay ([PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC6293241/)). Vendor STO claims ("15% in every channel") are an order of magnitude larger and uncontrolled.
- **Digest fatigue has a published threshold:** ~**0.58% unsubscribe at >5 emails/week vs. 0.07% at 1–2/week** (Salesforce, ~19B sends, reported second-hand), with 20–30% of unsubscribes citing volume ([clean.email](https://clean.email/blog/insights/email-subscription-fatigue-statistics)). A weekly digest sits inside the safe band; the risk is cumulative volume across channels.
- **Provisional push is genuinely unmeasured, and the one practitioner sweep found it neutral** — same opt-in rate as the APNs prompt, no D1/D3/D7 retention difference, no increase in upgrades to prominent alerts ([Phiture](https://phiture.com/blog/provisional-push-what-is-it-and-how-will-it-impact-your-addressable-audience/)); Braze's guide publishes no numbers at all. Treat it as free optionality, not a lever with known upside.
- **Fantasy-football recaps are already a saturated category, and every entrant names the league group chat as the channel.** RecapMyLeague, ffrec.app, fantasywrapped.xyz and an open-source Sleeper app (~30k users) all ship story-style slides "for your league group chat" — all Sleeper-only, all commodity results data.

---

## 1. The anatomy of a Wrapped-class recap

### 1.1 The measured funnel

Spotify is the only recap that publishes a funnel, and it publishes it in a usable shape:

| Metric | Wrapped 2024 | Wrapped 2025 | Δ |
|---|---|---|---|
| Time to 200M engaged users | ~62 hours | ~24 hours | −38 hours |
| Engaged users, first 24h | — | 200M | +19% YoY |
| Shares, first 24h | — | ~500M | +41% YoY |
| Campaign-total users | — | 300M+ | — |
| Campaign-total social shares | — | 630M | — |

Sources: [MBW](https://www.musicbusinessworldwide.com/spotify-wrapped-campaign-hit-200m-engaged-users-in-24-hours-a-19-yoy-increase/), [Mi3](https://www.mi-3.com.au/07-12-2025/spotify-wrapped-2025-reaches-record-200-million-engaged-users-24-hours), [Music Week](https://www.musicweek.com/digital/read/spotify-wrapped-2025-was-biggest-ever-with-200-million-engaged-users/093178), [TechCrunch](https://techcrunch.com/2025/12/04/spotify-says-wrapped-2025-is-its-biggest-yet-with-200m-users-in-its-first-day).

Two definitional details matter more than the magnitudes. **"Engaged user" = viewed at least one story**, so the headline is *reach*, not completion — no public source discloses story-completion rate for any recap product. And **"shares" bundles native shares, screenshots and downloads**, which is the honest way to count: for a card artifact the screenshot *is* the share.

Derived (derivation, not measurement): **630M / 300M ≈ 2.1 shares per engaged user.** Round 1 asked for shares-per-user data; this is the best public estimate available, and it implies the recap is not one card but a set from which people pick about two.

Attribution caution: Spotify's record 751M MAU in Q4 2025 ([Hypebeast](https://hypebeast.com/2026/2/spotify-wrapped-drives-record-751-million-monthly-users)) is widely credited to Wrapped but is correlational. Round 1's Sensor Tower finding (+13–14% DAU day-over-day while Wrapped ad spend fell ~60%) remains the stronger causal argument.

### 1.2 Story-format mechanics

The structural pattern is consistent across every published analysis: **progressive disclosure, one fact per card, sequential reveal, tap-to-advance** — the Instagram/Snapchat stories grammar. Wrapped 2025 organised cards into "scenes" (commute, late-night, focus) rather than a linear chronology ([UX Playbook](https://uxplaybook.org/articles/spotify-wrapped-ux-design-lessons)). The recurring framing rule is emotional re-encoding of a raw number — *"you spent 788 hours finding yourself"* rather than *"47,283 minutes."*

The best engineering account is Monzo's ([Monzo blog](https://monzo.com/blog/building-year-in-monzo-as-told-by-engineering)):

- **Precompute everything.** A Kafka pipeline enriched raw data (merchant logos, friend names, share-image URLs) into AWS Keyspaces; "the only things done at API read time are Authorisation, and re-shaping the data." A recap is a spike-load product — on-demand computation is the wrong shape.
- **Backend-driven story templates with hard constraints** (line lengths, image sizes, optional fields) so creative could add stories **without a client release**.
- **Share images as HTML/CSS → PNG via headless Chrome**, 5M+ of them — also the source of their worst incident: Chrome tabs accumulated faster than they closed, cascading OOM kills; scaling ~120 → 600 instances got the pipeline to ~5 hours. They name it as a dev-speed/ops-complexity trade.
- **Preload all assets behind a loading screen**, ≥3 retries each, API calls batched ~5 per request. Mid-story spinners kill completion.
- **Accessibility in scope**: experience-level screen-reader narration, a reduced-motion variant unified with it, responsive font scaling.

### 1.3 Stat selection — the one published experiment

Duolingo's Year in Review is the only recap with a public account of *what they learned about which stats to show* ([Duolingo](https://blog.duolingo.com/year-in-review-behind-the-scenes)). The arc: **2019** email-only activity counters (active days, time, words, lessons) → **2020** moved in-app → **2021** added an XP percentile comparison to the share card, which raised share rates but produced a pathological distribution — **the top 10% of XP earners produced more than half of all shares** → **the fix was archetypes, not more stats**: "learner style personalities" mapped to app habits, a qualitative label everyone qualifies for, which "significantly boosted share rates" → **2022** sharing itself was rewarded in-product with a themed Leaderboard badge reflecting the learner style.

This is the empirically-grounded answer to the "self-expression vs. vanity" question. **Rank-based stats are vanity goods — they concentrate sharing in the top decile. Archetype/label stats are self-expression goods — they distribute sharing**, because a label is a claim about identity rather than superiority. The academic literature agrees from the other direction: sharing a taste artifact is read as an identity claim and "invites normative judgment" ([UNC thesis](https://cdr.lib.unc.edu/concern/honors_theses/6h4413727)); Wrapped "configures a space where consumption data is transformed into a resource for identity construction" ([ICS](https://www.tandfonline.com/doi/full/10.1080/1369118X.2026.2647352)); users report "performative listening" and "Wrapped anxiety" — modifying behaviour because the recap is coming ([New Media & Society](https://journals.sagepub.com/doi/10.1177/14614448251391301)).

**Design principle:** give every user a label they can own; reserve rank-comparisons for the cards where being in the top decile is the point.

### 1.4 The negative case: Wrapped 2024

Wrapped 2024 dropped **top genres and top albums** — the most concrete, verifiable, argued-about stats — and led with AI-generated genre labels and an AI podcast. Users called the labels nonsensical ("Pink Pilates Princess" became a meme) and the commentary generic ([Forbes](https://www.forbes.com/sites/danidiplacido/2024/12/05/spotify-wrapped-2024-backlash-controversy-and-memes/), [Today](https://www.today.com/popculture/music/spotify-wrapped-2024-controversy-rcna183189)); execs later acknowledged the biggest-reach-worst-feedback outcome ([Music Ally](https://musically.com/2025/05/30/spotify-execs-talk-superfans-ai-and-wrapped-2024-backlash/)). 2025 restored accurate genre/artist classification and added *specific* new facts (Listening Age, Clubs, podcast/audiobook stats) — and set records.

**Transferable rule:** a recap's currency is *facts the user recognises as true about themselves*. Generated narration on thin facts reads as filler; on dense verified facts it reads as insight. Directly relevant to the FTF plan's tier proportions — Tier 1 stats are the verifiable-facts category and should not be diluted.

### 1.5 The rest of the field

- **Strava Year in Sport** is deliberately **mobile-app-only**, which forces an app open ([Strava](https://support.strava.com/en-us/articles/15401959-your-year-in-sport)). Strava also publishes a *separate* editorial trend report from aggregate data (180M+ users, 185 countries, 30k survey respondents) that earns press independently of the personal artifact ([Strava press](https://press.strava.com/articles/strava-releases-12th-annual-year-in-sport-trend-report-2025)). Two artifacts, one dataset.
- **GitHub Unwrapped** (Remotion) renders the recap as a **personalised video** rather than cards ([githubunwrapped.com](https://githubunwrapped.com/)) — the format is not load-bearing, but video is a heavier build for the same identity payload.
- **Reddit Recap** publishes no artifact-level engagement data; circulating numbers are platform DAU/WAU, which do not isolate Recap.
- **Fantasy-football recaps already exist as a category**, all Sleeper-only and results-based: RecapMyLeague (AI 400–600-word narrative + nine player superlatives, free, "for your league group chat"), ffrec.app ("Instagram Story-style slides", auto-refreshing the Monday after championship week), fantasywrapped.xyz, and an open-source Sleeper analytics app claiming ~30k users. **This is exactly the commodity tier the FTF plan identified as low-value — and it is saturated.** The differentiator is unchanged: value history and personal-Elo stats nobody else holds.

---

## 2. Smaller-cadence recaps

Weekly and monthly recaps differ structurally from annual ones in three ways, and the differences are consistent across the products that ship both:

| | Annual recap | Weekly/monthly recap |
|---|---|---|
| Primary job | Identity artifact → share | Feedback loop → return |
| Format | Story deck, animated, one-shot | Fixed slot, scannable, repeated |
| Comparison frame | Self vs. population percentile | Self vs. *last week* |
| Distribution | Social/group chat | Private, in-app or email |
| Failure mode | Embarrassing thin users | Fatigue and habituation |

**Strava** runs the full ladder: a Monday **weekly summary** (total stats, longest effort highlighted, a shareable recap card), a **Monthly Recap / Month in Sport** that was *moved out of email into an in-app animated review*, and the annual Year in Sport ([Monthly Recap](https://support.strava.com/hc/en-us/articles/360057807412-Monthly-Recap), [Month in Sport](https://support.strava.com/en-us/articles/15401741-month-in-sport), [BikeRadar](https://www.bikeradar.com/news/strava-monthly-activity-stats-animation)). The email→in-app migration trades reach for session credit — the same trade as making Year in Sport app-only.

**Whoop's Weekly Performance Assessment** is the closest analogue to Grammarly's weekly digest and adds two mechanics Grammarly lacks ([Whoop](https://support.whoop.com/hc/en-us/articles/360019454194-What-is-the-Weekly-Performance-Assessment-WPA-), [The Locker](https://www.whoop.com/thelocker/new-weekly-performance-assessment/)): a **fixed Monday slot** for every member; a **global community comparison** delivered privately rather than as a share card; and — the important one — an **unlock threshold**: the WPA is gated until the member logs 14 recovery scores, then arrives the following Monday. **That is the published solution to the thin-data problem** — rather than sending a bad first digest, the product withholds it until it can be good.

Neither Whoop nor Strava publishes lift for any of these, so the honest claim is: **the weekly → monthly → annual ladder is the convergent pattern among data-rich consumer products, and the unlock threshold is the one published mechanic for protecting new users from a thin recap.**

**Airship's Starbucks example is the inbox version:** "Pick of the Week," a fixed offer delivered to the message center every Tuesday, cited as the way to make message-center visits *habitual* through anticipation ([Airship](https://support.airship.eu/hc/en-us/articles/5578647880091-Advanced-Topic-Message-Center)). The predictable slot is the mechanism; the content is almost incidental.

---

## 3. Share-card virality mechanics

**What the peer-reviewed literature supports.** Berger & Milkman (JMR 2012): content evoking **high-arousal** emotion — awe, anger, anxiety — is more viral; **low-arousal** emotion (sadness) suppresses sharing; positive beats negative overall; effects hold controlling for surprise, interest, utility and prominence ([JMR](https://journals.sagepub.com/doi/10.1509/jmr.10.0353), [PDF](http://jonahberger.com/wp-content/uploads/2013/02/ViralityB.pdf)). Applied to recaps: **a card producing awe ("I did *that* much?") or indignation ("this trade aged *how*?") out-shares a card producing mild regret.** Sadness-shaped cards — "the one that got away" — are the least shareable framing available, independently supporting the FTF plan's decision to keep that stat self-only.

**Optimal distinctiveness** (Brewer) recurs across the Wrapped analyses: people want to *belong* and to *stand out* at once, and a card saying "you're in a recognisable group, and unusual within it" satisfies both. Established theory; its application to share cards is analysis, not measurement. **Craft rules, unanimous across teardowns but unmeasured:** fixed 9:16 ratio; typography and contrast chosen assuming a screenshot rather than a share-sheet call; one stat per card; a share affordance on *every* card, not only the last.

**Fantasy-specific share culture.** Every incumbent names the league group chat — RecapMyLeague invites users to post to "your league group chat or on social media"; ffrec.app ships story-style slides for league circulation. Sleeper itself is chat-first ([Sleeper](https://sleeper.com/fantasy-football)) and GroupMe markets a fantasy vertical around draft results, standings and trade-offer screenshots ([GroupMe](https://groupme.com/fantasyfootball)). **The share target is a private 10–12 person chat, not a public feed** — the audience already knows the context, so comparative stats land harder than absolute ones, and the card must be legible pasted in with no caption. I found **no published quantitative data** on shares-per-user, share→install conversion, or group-chat referral rates for any fantasy recap product.

---

## 4. Notification-inbox content strategy

Round 1's conclusion — no *controlled* evidence on inboxes as discovery surfaces — stands. But there is more observational evidence than round 1 surfaced, and it has methodology.

**Airship's message-center study** (Nov 13 2015 – Jan 13 2016; **83 apps, 1,149,156,265 messages**; read rate = users who read ÷ users who received) ([newsroom](https://www.airship.com/newsroom/new-urban-airship-study-finds-in-app-message-centers-generate-eight-times-m/), [blog](https://www.airship.com/blog/surprise-and-delight-your-customers-with-an-offers-inbox-for-the-holidays/)):

| Finding | Value |
|---|---|
| iOS 90th-percentile read rate | 44% (retail high-performers 49%) |
| iOS median read rate vs. push direct-taps | **8x** |
| Read rate when card is paired with a push | **more than doubles** |
| Read rate with a home-screen badge | **+23%** |
| iOS opted-in vs. opted-out users | 52% vs. **25%** |
| Android median read rate | 6% (≈ parity with push direct taps) |

The **25% read rate among push-opted-out users** is the most strategically important number: the inbox reaches people push cannot, at a quarter of them per message. That is the quantitative case for an inbox as a discovery surface, and round 1 did not have it.

**Braze Content Cards** supplies the modern layer, with the usual controls problem: **Wondery** — highest-converting CRM channel to Wondery+ (**+6% conversion** vs. other channels), engagers listened to **64% more unique episodes/week** (self-selected), and **total CTR 152% above unique CTR**, i.e. users returned to the same card repeatedly — the persistence property push lacks ([Braze](https://www.braze.com/customers/wondery-case-study)). **Second Dinner / MARVEL SNAP** — **96%** of users reported cards as their first interaction point with a new campaign, driving **86%** of traffic to its voting page ([Braze](https://www.braze.com/customers/second-dinner-case-study)). **Equinox** — **+21% over a control group**, the only control-group figure in the corpus ([Braze](https://www.braze.com/customers/equinox-case-study)).

**Conventions worth adopting** ([Braze docs](https://www.braze.com/docs/user_guide/message_building_by_channel/content_cards/), [Airship](https://support.airship.eu/hc/en-us/articles/5578648209947-Best-practices-for-Message-Center-message-removal), [Courier](https://www.courier.com/guides/how-to-build-a-notification-center/chapter-3-best-practices-for-notification-centers)):

- **Match format to urgency:** inbox = non-urgent, status, reference-worthy; toast = ephemeral confirmations; badge = glanceable count; push = critical or re-engagement, sparingly.
- **Bundle on repetition, not volume.** "10 new comments on Q4 Roadmap" beats ten rows — "the information value is identical and the interruption cost is a tenth." Courier calls bundling the highest-impact change to a noisy feed, and a *content* decision rather than a UI one.
- **Scan target ≈ 2 seconds**; front-load who/what/why; concrete titles over generic.
- **Expiry is mandatory for time-sensitive content.** Airship expires items after one year by default with per-message overrides and auto-deletes anything with an offer deadline; Courier auto-archives *read* items after 30–90 days.
- **One quiet unread signal**, strict title/body/timestamp hierarchy, "mark all read," per-type preferences.

---

## 5. Digest engineering

**Send-time optimisation.** The only causal estimate I found is the JOOL microrandomized trial: **N=1,255, 89 days**, tailored push → **3.9%** relative increase in 24h engagement (RR 1.039, CI 1.01–1.08); **weekends 8.7% vs. weekdays 2.5%**; peak **11.8% at 12:30pm on weekends** (weekday peak also at lunch, 7.4%); no significant attenuation over the study ([PMC6293241](https://pmc.ncbi.nlm.nih.gov/articles/PMC6293241/)). Two implications: the effect is real but single-digit — consistent with round 1's DellaVigna & Linos calibration — and **the day-type × time-of-day interaction is larger than the main effect**, which is the cheap version of STO. Vendor claims run an order of magnitude higher (Braze: Intelligent Timing "lifted conversions by at least 15% in every messaging channel"; foodora +9% email CTR, −26% unsubscribes, +6% push opens) with no published control design ([Braze](https://www.braze.com/resources/articles/intelligent-delivery-find-every-customers-optimal-moment)).

**Digest fatigue.** The best-cited threshold analysis (Salesforce Marketing Cloud, ~19B sends, reported second-hand) puts unsubscribes at **0.58% for >5 emails/week vs. 0.07% at 1–2/week**, names volume as the top unsubscribe driver in 20–30% of cases, and notes fatigue takes **3–4 weeks** to surface in unsubscribe data ([clean.email](https://clean.email/blog/insights/email-subscription-fatigue-statistics)). Operationally useful: **offering a digest as an explicit lower-frequency option reduces unsubscribes** versus a binary on/off. A weekly digest is well inside the safe band alone; the risk is cumulative volume across channels.

**The dynamic-recommendation slot.** Round 1 flagged Grammarly's structure — fixed Monday slot, collision-protected, prioritised above promotional email, with **one dynamically-inserted "logical next step"**. Round 2 found the same shape recurring (LinkedIn's behavioural digests, Whoop's "actionable feedback," Strava's highlighted longest effort) but **no published lift figure for the slot itself anywhere** — convergent practice, not measurement. Whoop adds the one mechanic worth stealing outright: **gate the digest behind a data threshold** so the first one is never thin.

---

## 6. Provisional push in practice

Apple introduced provisional authorization in iOS 12 (WWDC18 session 710) on an explicit rationale: users cannot make an informed choice about notifications until they have seen what an app sends ([Apple](https://developer.apple.com/videos/play/wwdc2018/710/)). Mechanically: no permission prompt, quiet delivery only (Notification Center, no sound, no lock-screen banner), and an inline **Keep / Turn Off** control on the notification itself, with some implementations exposing the fuller "Keep — Prominent / Quiet" branch ([Use Your Loaf](https://useyourloaf.com/blog/provisional-authorization-of-user-notificatons/), [iOS Brain](https://iosbrain.com/blog/2018/07/05/new-in-ios-12-implementing-provisional-authorization-for-quiet-notifications-in-swift/)).

**The evidence base is close to empty, and what exists is null.** Phiture's practitioner sweep — the only multi-company account I found — reports the **same opt-in rate** as the standard APNs prompt, **no difference in D1/D3/D7 retention**, and **no increase** in upgrades to prominent alerts; their recommendation is a phased rollout on a small share of new users ([Phiture](https://phiture.com/blog/provisional-push-what-is-it-and-how-will-it-impact-your-addressable-audience/)). Braze's marketer guide publishes **no numbers at all** ([Braze](https://www.braze.com/resources/articles/mastering-provisional-push)) and notes that over half of retailers reported no change in notification engagement since provisional auth shipped. Baseline iOS opt-in is variously reported at 40–56% ([Batch](https://help.batch.com/en/articles/4195576-how-to-improve-the-push-opt-in-rate), [OneSignal](https://onesignal.com/blog/how-to-create-more-compelling-opt-in-messages-for-ios-push/)).

**Honest reading:** provisional push has no demonstrated upside. Its value is *optionality* — it converts a zero-reach population (never prompted, or declined) into a quietly-reachable one at no permission cost, and Airship's **25% read rate among opted-out users** suggests the persistent-surface half is where value would show up. The asymmetry to respect: the first provisional notification carries a **Turn Off** button, so a weak first send permanently forecloses the channel.

---

## Evidence quality notes

**Tier A — peer-reviewed / controlled / large-N:**
- **JOOL microrandomized trial** (PMC6293241) — genuine within-person randomisation of push timing, N=1,255 over 89 days, CIs reported. The only causal timing estimate here. Workplace-wellness domain; transfer is an assumption.
- **Berger & Milkman (2012), JMR** — large observational dataset with controls plus supporting lab experiments. Well-replicated; about news articles, not recap cards.
- **Wrapped academic corpus** (New Media & Society 2025; ICS 2026; Journal of Gender Studies 2024; UNC thesis) — qualitative, small samples, no effect sizes. Strong on *mechanism* (identity performance, normative judgment, "Wrapped anxiety"), useless for magnitude. Mostly paywalled; I read abstracts and search summaries, not full texts (Sage and T&F fetches returned 403).

**Tier B — first-party accounts of real systems, no controls:**
- **Duolingo Year-in-Review behind-the-scenes** — the top-decile-produces-half-the-shares finding is the most valuable datapoint in this brief, but it is an internal observation with no published methodology. Credible mainly because it explains a design change they then made.
- **Spotify Wrapped 2025 numbers** — first-party via trade press, with a stated "engaged user" definition. Reach and shares are countable; persistence and downstream behaviour are not disclosed.
- **Monzo engineering blog** — detailed and includes their own failures. No engagement data.
- **Airship 2016 message-center study** — 83 apps, 1.15B messages, stated read-rate definition, but **a decade old**, and the notification landscape has changed (iOS summaries, Focus modes). Treat the *relative* findings (badge +23%, push-pairing doubling, opted-out 25%) as more durable than the absolute rates.

**Tier C — vendor case studies and marketing:** every Braze Content Cards figure except Equinox's +21% is uncontrolled and self-selected ("engagers listened to 64% more episodes" is a textbook selection effect; the 96%/86% MARVEL SNAP figures are attribution, not experiment). Braze Intelligent Timing's "≥15% in every channel" has no methodology. The Salesforce 19B-send analysis is second-hand via an aggregator — the direction is not in doubt, but the 0.58%/0.07% figures should be verified before use as targets. All share-card craft rules are convergent practitioner opinion.

**Gaps I could not close:**
1. **No completion-rate data for any recap product** — reach and shares are published; "how many finished the deck" is not.
2. **No shares-per-user or share→install conversion for any fantasy-sports recap.**
3. **Still no controlled experiment on an inbox as a feature-discovery surface** (round-1 gap 1 stands; Airship measures read rates, not discovery).
4. **No published lift for the dynamic-recommendation slot** in any weekly digest (round-1 gap 4 stands).
5. **No developer post-mortems of provisional push with instrumented Keep/Turn-Off rates** — the Phiture sweep is the ceiling of what exists.
6. Airship's gated 2025/2026 Sports & Recreation benchmarks remain unretrieved.

---

## Implications for FTF — hypotheses only

1. **Ship archetypes, not just percentiles.** Duolingo's finding maps directly onto the plan's stated risk that "recaps reward users with lots of history." *Hypothesis:* a dynasty **manager archetype** derived from data FTF already logs (trade frequency, board divergence, age-curve direction, contention window) out-shares every rank-based card and is the only card a light user posts. *Risk:* an archetype computed from three weeks of data is a lie — gate it.
2. **Adopt Whoop's unlock threshold as the answer to the thin-user problem.** The plan treats this as a segmentation/suppression question; Whoop's published solution is better — define a data minimum (n matchups ranked, n weeks of roster history) and **withhold the recap until it is met**. Withholding is a feature, and it converts the thin-user risk into an activation prompt.
3. **Instrument shares the way Spotify does — count screenshots.** Define "engaged user = viewed ≥1 story"; count native shares, downloads *and* screenshots. Group-chat distribution makes the screenshot the dominant mode, so instrumenting only the share sheet undercounts by an unknown factor. Register these alongside the already-reserved `wrapped_viewed`. And design for a 10–12 person private chat, not a public feed: comparative and league-relative cards should out-perform absolute ones — exactly the surface YR-3 unblocked.
4. **Precompute, template server-side, batch the share images.** Monzo's architecture applies directly and their OOM incident is the failure to avoid. Generate images in a scheduled batch before launch day; use backend-driven story templates with hard field constraints so December copy changes don't need a client release (an EAS cycle in launch week is a real risk).
5. **Do not lead with generated narration.** Wrapped 2024 is the cautionary case, and the competitor set has already gone all-in on AI narrative over commodity results data. FTF's Tier 1 stats *are* the verifiable facts; LLM copy frames them, never replaces a stat that got cut.
6. **Avoid sadness-shaped share cards.** "The one that got away" is the archetypal low-arousal-negative card. The plan already rules it self-only on tone grounds; the virality evidence supports that independently, and implies any *shareable* regret stat must be reframed as indignation ("this trade aged 2,400 points"), not loss.
7. **The inbox's biggest measurable value may be reaching push-opted-out users.** Airship's 25% opted-out read rate is the strongest quantitative argument for the inbox FTF just shipped. *Hypothesis:* segment inbox read-rate reporting by push-opt-in status from day one — if the opted-out segment reads meaningfully, the inbox is genuinely additive and warrants discovery content.
8. **Pair every push with a card, and badge the inbox.** Read rates more than double when paired with a push, +23% with a badge. Round 1 recommended pairing on design grounds; this is the number behind it, and badging is cheap and independently measurable.
9. **Use the Starbucks fixed-slot mechanic for the weekly digest.** Predictable weekly content in a persistent surface is the published mechanism for habitual inbox visits; combine with Grammarly's structure (fixed day, collision-protected, one dynamic next-step). *Test:* does a "you haven't tried X" payload in a fixed weekly card raise 7-day first-use of the named feature?
10. **Take the cheap version of send-time optimisation.** The MRT's day-type × time-of-day interaction (weekend 8.7% vs. weekday 2.5%; lunchtime peaks) is bigger than the main effect and needs no ML. The fantasy analogue is Tuesday-post-waivers / Sunday-morning / Sunday-night — a fixed-arm test, feasible where a per-user bandit is not.
11. **Run provisional push as a phased experiment with a pre-registered null.** The honest prior is no effect on opt-in or retention; the reason to do it is reach into the never-prompted population, and the reason to be careful is that a weak first send carries a **Turn Off** button. Small % of new installs; the first send must be a genuinely useful personal event (a match, a value swing on a rostered player), never marketing.
12. **Consider Strava's two-artifact structure.** Once roster and value history exist, an aggregate **dynasty trend report** (league-wide value movement, most-traded assets, market-vs-consensus divergence) is nearly free, is press/creator-facing in a way the personal recap is not, and can fire in the Feb–March trough the plan wants to bridge.

---

## Sources

**Peer-reviewed / academic**
- Klasnja, P. et al. *To Prompt or Not to Prompt? A Microrandomized Trial of Time-Varying Push Notifications to Increase Proximal Engagement With a Mobile Health App.* JMIR mHealth uHealth. https://pmc.ncbi.nlm.nih.gov/articles/PMC6293241/
- Berger, J. & Milkman, K. L. (2012). *What Makes Online Content Viral?* Journal of Marketing Research 49(2), 192–205. https://journals.sagepub.com/doi/10.1509/jmr.10.0353 · PDF: http://jonahberger.com/wp-content/uploads/2013/02/ViralityB.pdf
- Annabell, T. & Vindum Rasmussen, N. (2025). *An algorithmic event: The celebration and critique of Spotify Wrapped.* New Media & Society. https://journals.sagepub.com/doi/10.1177/14614448251391301
- *Wrap your head around it: algorithmic self-making and performances of taste on Spotify Wrapped.* Information, Communication & Society (2026). https://www.tandfonline.com/doi/full/10.1080/1369118X.2026.2647352
- *Spotify (Un)wrapped: how ordinary users critically reflect on Spotify's datafication of the self.* Journal of Gender Studies (2024). https://www.tandfonline.com/doi/full/10.1080/09589236.2024.2433674
- *Facing the Music: Spotify Wrapped as a Determinant for Personal Identity Performance.* UNC honors thesis. https://cdr.lib.unc.edu/concern/honors_theses/6h4413727

**First-party product / engineering accounts**
- Duolingo. *Year in Review: behind the scenes.* https://blog.duolingo.com/year-in-review-behind-the-scenes
- Monzo. *How we built Year in Monzo: as told by the engineering team.* https://monzo.com/blog/building-year-in-monzo-as-told-by-engineering
- Apple. *What's New in User Notifications* — WWDC 2018 session 710. https://developer.apple.com/videos/play/wwdc2018/710/
- Strava Support. *Your Year in Sport.* https://support.strava.com/en-us/articles/15401959-your-year-in-sport · *Monthly Recap.* https://support.strava.com/hc/en-us/articles/360057807412-Monthly-Recap · *Month in Sport.* https://support.strava.com/en-us/articles/15401741-month-in-sport
- Strava Press. *12th Annual Year in Sport Trend Report.* https://press.strava.com/articles/strava-releases-12th-annual-year-in-sport-trend-report-2025
- Whoop Support. *What is the Weekly Performance Assessment (WPA)?* https://support.whoop.com/hc/en-us/articles/360019454194-What-is-the-Weekly-Performance-Assessment-WPA- · *Monthly Performance Assessment.* https://www.whoop.com/us/en/thelocker/monthly-performance-assessment/
- Remotion. *GitHub Unwrapped.* https://githubunwrapped.com/ · https://github.com/remotion-dev/github-unwrapped

**Industry data / trade press**
- Music Business Worldwide. *Spotify Wrapped campaign hit 200M engaged users in 24 hours — a 19% YoY increase.* https://www.musicbusinessworldwide.com/spotify-wrapped-campaign-hit-200m-engaged-users-in-24-hours-a-19-yoy-increase/
- Music Week. *Spotify Wrapped 2025 was biggest ever with 200 million engaged users.* https://www.musicweek.com/digital/read/spotify-wrapped-2025-was-biggest-ever-with-200-million-engaged-users/093178
- Mi3. *Spotify Wrapped 2025 reaches a record 200 million engaged users in 24 hours.* https://www.mi-3.com.au/07-12-2025/spotify-wrapped-2025-reaches-record-200-million-engaged-users-24-hours
- TechCrunch. *Spotify says Wrapped 2025 is its biggest yet.* https://techcrunch.com/2025/12/04/spotify-says-wrapped-2025-is-its-biggest-yet-with-200m-users-in-its-first-day
- Music Ally. *Spotify execs talk superfans, AI and Wrapped 2024 backlash.* https://musically.com/2025/05/30/spotify-execs-talk-superfans-ai-and-wrapped-2024-backlash/
- Forbes. *The Backlash Against 'Spotify Wrapped 2024,' Explained.* https://www.forbes.com/sites/danidiplacido/2024/12/05/spotify-wrapped-2024-backlash-controversy-and-memes/
- Today. *Spotify Wrapped 2024 Controversy.* https://www.today.com/popculture/music/spotify-wrapped-2024-controversy-rcna183189
- Hypebeast. *Spotify Wrapped Drives Record 751 Million Monthly Users in Q4 2025.* https://hypebeast.com/2026/2/spotify-wrapped-drives-record-751-million-monthly-users
- BikeRadar. *Strava adds monthly activity stats animation.* https://www.bikeradar.com/news/strava-monthly-activity-stats-animation

**Vendor documentation, studies and case studies (Tier B/C)**
- Airship. *New Urban Airship Study Finds In-App Message Centers Generate Eight Times More Direct Response Than Push Notifications.* https://www.airship.com/newsroom/new-urban-airship-study-finds-in-app-message-centers-generate-eight-times-m/
- Airship. *Why Add an In-App Message Center to Your Retail App? Read Rate Benchmarks.* https://www.airship.com/blog/surprise-and-delight-your-customers-with-an-offers-inbox-for-the-holidays/
- Airship Support. *Advanced Topic: Message Center.* https://support.airship.eu/hc/en-us/articles/5578647880091-Advanced-Topic-Message-Center · *Best practices for Message Center message removal.* https://support.airship.eu/hc/en-us/articles/5578648209947-Best-practices-for-Message-Center-message-removal
- Braze. *Content Cards documentation.* https://www.braze.com/docs/user_guide/message_building_by_channel/content_cards/
- Braze. *Wondery case study.* https://www.braze.com/customers/wondery-case-study · *Second Dinner case study.* https://www.braze.com/customers/second-dinner-case-study · *Equinox case study.* https://www.braze.com/customers/equinox-case-study
- Braze. *Improve Your Push Notification Strategy with Provisional Push.* https://www.braze.com/resources/articles/mastering-provisional-push
- Braze. *Intelligent Timing: Find Every Customer's Optimal Moment.* https://www.braze.com/resources/articles/intelligent-delivery-find-every-customers-optimal-moment
- Courier. *Best Practices for Notification Centers.* https://www.courier.com/guides/how-to-build-a-notification-center/chapter-3-best-practices-for-notification-centers · *In-app notification center design.* https://www.courier.com/blog/in-app-notification-center-design
- Phiture. *Provisional Push: What is it and how will it impact your addressable audience?* https://phiture.com/blog/provisional-push-what-is-it-and-how-will-it-impact-your-addressable-audience/
- Batch. *How to improve the push opt-in rate?* https://help.batch.com/en/articles/4195576-how-to-improve-the-push-opt-in-rate
- OneSignal. *Increase Your iOS Push Notification Opt-in Rates.* https://onesignal.com/blog/how-to-create-more-compelling-opt-in-messages-for-ios-push/
- clean.email. *Email Subscription Fatigue Statistics.* https://clean.email/blog/insights/email-subscription-fatigue-statistics

**Developer references**
- Use Your Loaf. *Provisional Authorization of User Notifications.* https://useyourloaf.com/blog/provisional-authorization-of-user-notificatons/
- iOS Brain. *Implementing Provisional Authorization for Quiet Notifications in Swift 4.2.* https://iosbrain.com/blog/2018/07/05/new-in-ios-12-implementing-provisional-authorization-for-quiet-notifications-in-swift/

**Competitive / category references**
- RecapMyLeague. https://www.recapmyleague.com/
- Fantasy Wrapped (ffrec.app). https://www.ffrec.app/
- Fantasy Wrapped 2025. https://fantasywrapped.xyz/
- kt474. *fantasy-football-wrapped* (open-source Sleeper analytics). https://github.com/kt474/fantasy-football-wrapped
- Sleeper. *Fantasy Football.* https://sleeper.com/fantasy-football
- GroupMe. *Fantasy Sports Group Chats.* https://groupme.com/fantasyfootball

**Design analysis (opinion tier)**
- UX Playbook. *What UX Designers Can Learn From Spotify Wrapped 2025.* https://uxplaybook.org/articles/spotify-wrapped-ux-design-lessons
- The Conversation. *Spotify Wrapped is about more than what songs you listen to.* https://theconversation.com/spotify-wrapped-is-about-more-than-what-songs-you-listen-to-its-about-what-makes-you-you-245019
