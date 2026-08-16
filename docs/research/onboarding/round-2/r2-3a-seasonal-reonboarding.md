# R2-3A — Seasonal Engagement and Returning-User Re-Onboarding

**Round 2 research brief — lens 3A**
**Date:** 2026-08-15
**Scope:** obtainable fantasy/sports seasonality data; what sports apps do at season start; "what changed since you left" surfaces; returning-player systems in games; seasonal businesses outside sports; win-back economics; pre-season ramp sequencing.
**Builds on:** [round-1/b3-discovery-loops-lifecycle.md](../round-1/b3-discovery-loops-lifecycle.md) — specifically its logged gap #3 ("no public fantasy-sports seasonality curves"), which this brief closes with measured data.

---

## TL;DR

- **The seasonality gap is now closed with real numbers.** Wikipedia pageview data for the "Fantasy football (gridiron)" article gives a clean four-year curve: the **July→August step is 3.4–3.5x, replicating within ±0.1 across 2023, 2024 and 2025**, and the September peak runs **6.3–7.3x the annual trough** ([Wikimedia Pageviews API](https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Fantasy_football_(gridiron)/monthly/2022010100/2026070100)). This is a public, reproducible, free seasonality curve — no Sensor Tower licence required.
- **The single most consequential finding: the dynasty calendar is not the redraft calendar, and they are close to anti-phased in the offseason.** Generic fantasy-football attention bottoms out in **April–June**. The NFL Draft — dynasty's rookie-draft trigger — peaks in **April at ~113,000–115,000 views, roughly 15x its own June baseline** ([Wikimedia, NFL draft](https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/NFL_draft/monthly/2024010100/2026060100)). In April 2026 the NFL-draft article drew 113,028 views while the fantasy-football article drew 2,649 — its annual minimum. **FTF has two peaks, not one**, and the second sits inside what a redraft-shaped product would treat as dead time.
- **More than half the September peak evaporates within one month.** September→October decline was **−52% (2024), −52% (2025), −44% (2023)**. Interest concentrates on *getting set up*, not on playing the season. For FTF this argues the draft-season window is narrower than it feels.
- **ESPN's answer to seasonal re-entry is to delete the re-entry decision.** Its 2025 app shipped **Auto-Reactivate — automatic league reactivation at season end** ([ESPN Press Room](http://espnpressroom.com/press-release/espn-fantasy-football-30th-anniversary-new-design-new-features-all-new-fantasy-app-for-2025/)). The strongest sports-app seasonal pattern found is not a better welcome-back screen; it is removing the need for one.
- **Duolingo's returning-user flow is documented but its results are not.** The public record describes a **full-screen modal asking whether the learner still remembers what they learned**, functioning as re-segmentation rather than greeting ([UserGuiding](https://userguiding.com/blog/duolingo-onboarding-ux)), plus explainer video after the redesign. **No published lift figures exist** — round-1's assumption that Duolingo's returning flow has published results does not hold.
- **Games have the most mature returning-player systems, and the transferable pattern is suppression, not celebration.** WoW's Catch Up Experience **temporarily hides the returning player's old quests** so they can relearn their character, grants level-appropriate gear, and offers an accelerated story recap — and it is **opt-in, presented as a choice against "pick up where you left off"** ([Wowhead](https://www.wowhead.com/guide/returning-players-catch-up-experience-guide); [Blizzard](https://news.blizzard.com/en-us/article/24263354/welcome-home-a-returning-player-s-guide)).
- **Win-back economics are strongly favourable but the numbers are vendor-sourced and wildly inconsistent** — ranging from "5–7x cheaper than acquisition" to "80–300x cheaper" across sources with no shared methodology. The one credible structural claim, from Mixpanel via a secondary source, is that **recently-dormant users resurrect at 3–5x the rate of users dormant 6+ months** — which for a seasonal product is the finding that actually matters.
- **Pre-season ramp guidance converges on 6–8 weeks before the peak** for reactivation campaigns and **2–3 months** for store/creative preparation, with The Athletic's 12-day pre-kickoff countdown as the best-documented editorial mechanic ([Roastbrief](https://roastbrief.us/how-the-athletic-is-turning-pre-season-anticipation-into-a-content-led-engagement-platform/)).

---

## 1. Fantasy seasonality, measured

Round 1 logged "no public fantasy-sports seasonality curves" as an open gap after Sensor Tower's fantasy cuts proved unretrievable. That gap is closable from a different direction. The **Wikimedia Pageviews API** is public, free, unauthenticated, returns monthly series back to 2015, and filters automated traffic (the `user` agent segment). It is a proxy for *public attention to a topic*, not for app usage — but for establishing the **shape and amplitude** of the season it is sufficient, and it replicates across years, which is the property that matters.

### 1.1 The redraft curve

English Wikipedia, article `Fantasy_football_(gridiron)`, monthly user pageviews:

| Month | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| Jan | 6,614 | 6,832 | 4,994 | 7,555 | 5,169 |
| Feb | 4,050 | 3,625 | 4,117 | 4,279 | 4,124 |
| Mar | 3,269 | 3,672 | 3,523 | 3,996 | 2,922 |
| Apr | 2,781 | 3,039 | 3,701 | 3,252 | **2,649** |
| May | 3,366 | 2,944 | 3,382 | 3,557 | 2,911 |
| Jun | 3,627 | 2,849 | 3,827 | 2,845 | 2,953 |
| Jul | 5,119 | 4,372 | 4,871 | 4,953 | — |
| Aug | 23,018 | 15,270 | 16,857 | 16,866 | — |
| **Sep** | **30,332** | **19,105** | **21,468** | **20,791** | — |
| Oct | 11,033 | 10,718 | 10,356 | 10,009 | — |
| Nov | 9,811 | 7,372 | 7,340 | 7,357 | — |
| Dec | 8,209 | 7,290 | 8,425 | 7,145 | — |

Three derived facts, each replicating across years:

1. **The July→August step is 3.4–3.5x** (2023: 3.49x; 2024: 3.46x; 2025: 3.41x; 2022 was 4.50x). This is the tightest number in the dataset. Draft season does not ramp gradually — it steps.
2. **Peak-to-trough amplitude is 6.3–7.3x** (2023: 6.7x; 2024: 6.3x; 2025: 7.3x).
3. **September→October falls 44–52%.** The peak is about *acquiring and configuring a team*, not about playing the season out. By November, attention is at roughly one-third of peak and it keeps sliding.

There is no January bump. The playoff/championship period does not restore attention; it decays through it.

### 1.2 The dynasty curve is different — and this is the finding

Dynasty's defining annual event is the rookie draft, which follows the NFL Draft in late April. Using `NFL_draft` as the proxy:

| Month | 2024 | 2025 | 2026 |
|---|---|---|---|
| Jan | 3,135 | 27,955 | 28,442 |
| Feb | 3,787 | 30,477 | 15,754 |
| Mar | 2,621 | 25,747 | 17,542 |
| **Apr** | **75,907** | **115,159** | **113,028** |
| May | 14,333 | 16,167 | 15,342 |
| Jun | 8,395 | 7,681 | — |
| Jul | 8,025 | 7,878 | — |
| Aug | 7,265 | 9,219 | — |
| Sep | 10,200 | 11,921 | — |
| Dec | 15,084 | 13,427 | — |

April runs **~15x its own June baseline** (2025: 115,159 vs 7,681) and **6.4x the immediately preceding March** in 2026. The relative spike is *larger* than fantasy football's September peak, and it lands in the month that redraft fantasy treats as its annual dead zone.

This is corroborated qualitatively by dynasty-native sources. The Fantasy Footballers' trade-window piece puts rookie-pick value at its annual maximum in April around the NFL Draft, with veterans correspondingly undervalued, and marks **May–July as the low-engagement stretch** ([The Fantasy Footballers](https://www.thefantasyfootballers.com/dynasty/dynasty-trade-windows-timing-the-market-fantasy-football/)). Dynasty Nerds describes early May as when dynasty leagues come back to life and calls the first week of May the best week on the dynasty calendar; July brings startup-draft activity ([Dynasty Nerds, via search result](https://www.dynastynerds.com/dynasty/may-dynasty-fantasy-football-calendar/) — the page returned 403 on direct fetch, so this is search-snippet sourced).

**Composite dynasty calendar (synthesised, medium confidence):**

| Window | State | Driver |
|---|---|---|
| Late Apr – early May | **Peak #1** | NFL Draft → rookie pick values reprice violently |
| May – Jun | High, decaying | Rookie drafts execute; roster fine-tuning |
| Jul | Rising | Startup drafts, ADP forms |
| Aug – Sep | **Peak #2** | Draft season; 3.4x step from July |
| Oct – Nov | Decaying, trade-deadline blip | In-season trading |
| Dec – Mar | **Trough** | Season over; only NFL-calendar news |

The trough is **December through March**, not "the offseason" broadly — and it is interrupted by the combine/free-agency period (the elevated Jan–Mar NFL-draft figures in 2025–26 relative to 2024 suggest the pre-draft cycle now starts in January).

### 1.3 App-side corroboration

ESPN publishes Comscore-measured figures. The ESPN Fantasy App recorded **10.8 million unique users in September 2024**, No. 1 among fantasy apps ([ESPN Press Room](http://espnpressroom.com/press-release/espn-digital-2024-no-1-in-september/)), against **9.3 million unique visitors in pre-season August** ([ESPN Press Room, 2025 launch](http://espnpressroom.com/press-release/espn-fantasy-football-30th-anniversary-new-design-new-features-all-new-fantasy-app-for-2025/)). That is only a **~16% August→September step** — far flatter than the 3.4x Wikipedia step.

The divergence is informative rather than contradictory. Wikipedia measures *newcomers and the curious* (a 3.4x step); ESPN measures *installed-base activation* (a 16% step) — its August audience is already largely mobilised because drafts happen in August. **Attention arrives in August; usage was already there.** For FTF this suggests the acquisition curve and the reactivation curve peak at different moments, and should not be run off the same trigger.

---

## 2. What sports apps do at season start

### 2.1 ESPN 2025: the strongest single pattern is Auto-Reactivate

ESPN's 2025 app rebuild, launched ahead of its 11 August Fantasy Football Marathon and before the 7 September Week 1, shipped: a personalized home screen with analyst rankings for the user's own lineup; a **Dynamic Roster Dashboard** that surfaces waiver activity, trade offers and other action items as a to-do list; live in-game projections; enriched player cards; and — most relevant here — **Auto-Reactivate, which automatically reactivates leagues at season end** ([ESPN Press Room](http://espnpressroom.com/press-release/espn-fantasy-football-30th-anniversary-new-design-new-features-all-new-fantasy-app-for-2025/)).

Two design lessons:

- **The best seasonal re-entry design is often the removal of a re-entry decision.** ESPN did not build a better welcome-back screen; it made the returning state the default state. The returning user's league simply exists again.
- **The Dynamic Roster Dashboard is a "what needs your attention" surface, not a "what's new in the app" surface.** It re-onboards by pointing at the user's own stale state rather than at the product's changelog.

Notably, the press release says nothing about league history, season recaps, or returning-manager greetings beyond Auto-Reactivate. If ESPN — the largest player in the category, 13M+ players in 2024 — is not building a "welcome back, here's your last season" artifact, that is either a gap in the market or evidence it doesn't matter. Round 1's Wrapped/Year-in-Sport evidence argues the former; this is a genuine open question.

### 2.2 The Athletic: converting the pre-kickoff dead zone into a daily habit

The Athletic launched an **Advantage Calendar** on 13 August 2026: a hyper-limited physical 12-day countdown to the first NFL Sunday, each box holding a QR code unlocking exclusive insider content, mixed with game-day items and novelty ([Roastbrief](https://roastbrief.us/how-the-athletic-is-turning-pre-season-anticipation-into-a-content-led-engagement-platform/)). The stated intent is to turn the two-week pre-kickoff window into a daily reason to open the app. No results are published.

The mechanic worth abstracting is **a fixed-length, dated countdown with a daily unlock**, which manufactures a cadence during a period when the sport itself provides no events. That is exactly the structural problem a dynasty app faces in late July and early August.

### 2.3 Sleeper

No public teardown of Sleeper's season-start or returning-manager experience was found. Its own materials emphasise a short onboarding flow designed to make league-mates switch platforms, and draft-season features (castable draft board, commissioner controls) ([Sleeper](https://sleeper.com/fantasy-football)). **Logged as a gap** — Sleeper's returning-user handling would have to be observed directly in the app rather than researched.

---

## 3. Returning-user re-onboarding: the documented flows

### 3.1 The three-level framework

The clearest published framework tiers re-onboarding by implementation cost ([retention.blog](https://www.retention.blog/p/win-back-more-users-with-re-onboarding)): **Level 1** is an in-app welcome message triggered on app-open after **20–30+ days** of absence, with reinstalls counting as returns; **Level 2** is persistent feature-highlight messaging with tooltips, which also signals the product is still being developed; **Level 2.5** adds an explainer video covering what changed (the author cites Duolingo doing exactly this after its redesign, to prevent confusion); **Level 3** is a **full returning-user flow mirroring onboarding** — goal questions, experience questions, then recommendations for features correlated with retention.

The best-cited concrete example is **Fabulous**, which greets returning users with a personal framing, **asks why they left**, asks goal questions, and recommends features from the answers. The animating principle is that a returning user has already given a strong positive signal. The author publishes **no metrics**: this is a design framework, not evidence.

### 3.2 Duolingo — documented, unmeasured

Round 1 assumed Duolingo's returning-user flow had published results. It does not, as far as the public record goes. What is documented:

- A **full-screen modal on return asking whether the user still remembers what they learned**, which serves re-segmentation (placement testing) as much as greeting ([UserGuiding](https://userguiding.com/blog/duolingo-onboarding-ux)).
- After the app redesign, feature-explainer video for returning users ([retention.blog](https://www.retention.blog/p/win-back-more-users-with-re-onboarding)).
- Limited-time badges used as a return trigger ([Yodel Mobile](https://yodelmobile.com/seasonal-retention-engagement/)).

The re-segmentation framing is the transferable idea: the returning user's *state* is stale, not just their memory. Duolingo doesn't ask "want a tour?" — it asks a question whose answer changes where the product puts them.

### 3.3 TurboTax — the annual re-onboarding masterclass

TurboTax is the closest structural analogue to a fantasy app: a mandatory annual cycle with an 11-month gap, where both the user's context and the product's have changed. Its documented mechanics ([Appcues teardown](https://www.appcues.com/blog/how-turbotax-makes-a-dreadful-user-experience-a-delightful-one); [Intuit support](https://ttlc.intuit.com/turbotax-support/en-us/help-article/import-export-data-files/transfer-last-year-return-2021-turbotax-windows/L0JcyjyrG_US_en_US)):

1. **Prior-year transfer as the default first action.** It auto-detects last year's file and carries personal details, income, deductions and carryovers forward. The returning user starts from their own history, not from zero.
2. **Diffing last year against this year to generate proactive value.** If the address changed, it raises the moving-expense deduction unprompted. This has the most direct FTF analogue: *the diff between then and now is itself the feature*.
3. **Milestone checkpoints whose "what's coming up" sections differ between new and returning users** — explicit branching of one flow by user state.
4. **Continuous progress signalling** — a running refund estimate updating at every step.

The key structural insight: TurboTax never has to *ask* the returning user to come back — the deadline does that (a pull, exactly like a fantasy draft). Its entire re-onboarding budget therefore goes into **reducing re-entry cost**, not into persuasion. For a product whose users return on a calendar pull, that is the correct allocation.

### 3.4 The primacy-effect warning for experiments

If FTF A/B tests a returning-user flow, note the **primacy effect**: returning users trained on the old experience temporarily underperform under a new one because they must relearn it, depressing measured lift early and recovering later ([Statsig](https://www.statsig.com/perspectives/calculating-lift-ab-tests-impact); [MetricGate](https://metricgate.com/blogs/ab-test-novelty-effect-detection/)). A short test on a seasonal returning cohort is at high risk of reading a relearning cost as a design failure.

---

## 4. Games' returning-player systems

Games have run this problem for two decades and their solutions are the most mature.

### 4.1 World of Warcraft — Catch Up Experience

Blizzard's system for returners ([Wowhead](https://www.wowhead.com/guide/returning-players-catch-up-experience-guide); [Warcraft Wiki](https://warcraft.wiki.gg/wiki/Catch_Up_Experience); [Blizzard](https://news.blizzard.com/en-us/article/24263354/welcome-home-a-returning-player-s-guide)):

- **Suppression first.** Old quests are **temporarily hidden** so the player can relearn their class without the accumulated backlog shouting at them. This is the single most transferable mechanic in this brief: a returning user's stale state is *noise*, and the first act of re-onboarding is to mute it.
- **Restore competitive parity.** Level-appropriate gear and bag space granted outright (e.g. ilvl 460 at level 70, ilvl 551 at level 80 in patch 11.2.7) — so the returner isn't punished for having been away.
- **Story recap as an accelerated playthrough**, not a wall of text.
- **Explicitly opt-in.** Blizzard's guide presents it as a choice between picking up where you left off and starting the Catch Up Experience. Agency is preserved.
- **Sequencing in the official guide:** story context → catch-up system → what mechanically changed → new features framed as opportunities. Note that "what changed" comes *third*, after the player is oriented and comfortable.

### 4.2 Destiny 2 — and the failure mode

Bungie's overhaul made new-player onboarding **skippable** in Into the Light, letting players jump past the tutorial ([GameSpot](https://www.gamespot.com/articles/destiny-2-into-the-light-to-add-raid-boss-rush-mode-skippable-new-player-onboarding/1100-6522337/); [Destructoid](https://www.destructoid.com/destiny-2-into-the-light-introduces-onboarding-skip-for-new-players-heres-how-it-works/)). Commentary in the ecosystem is blunt that Destiny's **onboarding for lapsed players is worse than for new players**, and that even a few months away leaves a player overwhelmed by changes. Destiny is the cautionary case: a product with a fast-moving change surface and no returner-specific path accumulates re-entry debt.

### 4.3 The mobile-game pattern set

Four recurring mechanics across mobile games ([GameRefinery](https://www.gamerefinery.com/four-ways-how-mobile-games-re-engage-lapsed-players/)): **welcome-back gifts** (Lords Mobile, Homescapes; login calendars near-universal in Japan); **monetising the return** via returner-only offers and comeback gacha with a guaranteed high-rarity first pull (FFBE War of the Visions, State of Survival); **returning-player missions**, a short task ladder with escalating rewards over ~5 days (Call of Duty: Mobile, Mobile Legends); and **friend-system reactivation**, rewarding *active* players for bringing dormant friends back (PUBG Mobile Recall; Fortnite's Reboot Rally and Refer a Friend, where an eligible friend has played **under 2 hours in the last 30 days** — [Fortnite](https://www.fortnite.com/news/fortnite-refer-a-friend-3-0-play-together-and-earn-rewards)).

The fourth transfers cleanly to a league-based product: **your active users are inside a social graph containing your dormant ones**. That is a fantasy app's structural advantage — the league is the recall mechanism, and it costs no push budget.

The article publishes no lapse thresholds, prevalence data, or measured results — pattern catalogue only. The canonical GDC talk (Phil Mansell, Jagex, 2015, *Returners and Retention*) is **paywalled**; only the abstract was retrievable ([GDC Vault](https://gdcvault.com/play/1022237/Returners-and-Retention-How-to)).

---

## 5. "What changed since you left" surfaces

The changelog-for-humans literature is practitioner-only and thin, but consistent on structure ([Frill](https://frill.co/blog/changelog-examples); [Worknotes](https://www.worknotes.ai/blog/best-changelog-page-designs)): a **vertical timeline** with clear date markers; **new features first, then fixes**; **screenshots or short animations per entry** (text-only changelogs are not read); an **in-product drawer rather than a link out**, browsable without leaving the app and badged; and **help-article links** on significant entries to reduce support load.

Combined with WoW's sequencing (orient → catch up → what changed → new opportunities) and Duolingo's post-redesign explainer video, the cross-domain convergence is: **"what changed" is a second-position surface, not a landing screen.** Nobody's evidence supports opening a returning user's session with a changelog. It is something they should be able to *pull* once they are re-oriented — consistent with round 1's finding that Drift's "Now In Drift" pull-based panel is the lowest-risk discovery mechanism.

---

## 6. Win-back economics

The numbers here are the weakest in this brief and must be handled carefully.

**Cost-ratio claims are all vendor/agency-sourced with no shared methodology, and they do not agree.** Reactivation is variously "5–7x cheaper" than acquisition ([DigitalApplied](https://www.digitalapplied.com/blog/customer-win-back-campaigns-2026-retention-playbook)), "5–10x" ([FlareLane](https://flarelane.com/en/blog/win-back-inactive-customers/)), "$6.80 vs $32" ≈4.7x ([Eightx](https://eightx.co/blog/average-win-back-reactivation-rate-benchmarks)), "3–10x" ([social.plus](https://www.social.plus/blog/4-proven-ways-to-re-engage-inactive-users-to-fuel-app-growth)), and "80–300x" ([US Tech Automations](https://ustechautomations.com/resources/blog/ecommerce-customer-win-back-campaigns-roi-analysis-2026)). The 4.7x-to-300x spread is itself the finding: **nobody is measuring this comparably.** The defensible statement is directional only — reactivation is cheaper, magnitude unknown.

**Rate benchmarks:** win-back email flows are reported to convert **2–5% of lapsed recipients, top quartile 5–10%**, alongside circulating "reactivate 15–30%" headlines that are not reconcilable with the flow-level numbers ([Eightx](https://eightx.co/blog/average-win-back-reactivation-rate-benchmarks); [DigitalApplied](https://www.digitalapplied.com/blog/customer-win-back-campaigns-2026-retention-playbook)). The 2–5% figure is consistent with round 1's DellaVigna & Linos calibration; the 15–30% claims are not.

**The one structurally useful finding:** recently-dormant users resurrect at **3–5x the rate of users dormant 6+ months**, and successful resurrections show 60%+ 30-day retention ([Monetizely, citing Mixpanel/Amplitude](https://www.getmonetizely.com/articles/how-to-calculate-resurrection-rate-for-dormant-users-a-critical-saas-metric); [Amplitude](https://amplitude.com/explore/analytics/resurrected-user)). This is the finding that bears directly on FTF: **a nine-month seasonal gap puts every user in the low-yield bucket by the time the pull arrives.** The economic implication is not "message harder in month eight" — it is that the *decay is the enemy*, and cheap in-season and shoulder-season touches that keep the gap short are worth more than an expensive August win-back blast to a fully-decayed base.

**Against that:** round 1's Wohllebe finding (non-personalized push frequency monotonically raises uninstalls, ~17,500 users) means the offseason — highest temptation to send, lowest relevance available — is exactly where frequency does the most damage. The two findings together define the constraint: **shorten the gap with relevance, not with volume.**

---

## 7. Pre-season ramp sequencing

Convergent practitioner guidance on timing: **2–3 months before** the peak for store listing, creative and metadata preparation, with starting too late named as the most common seasonal-marketing mistake ([Adapty](https://adapty.io/blog/app-seasonality/)); **6–8 weeks before** for campaign mapping and **6 weeks before** for season-start reactivation with escalating urgency ([AppFillip](https://appfillip.com/sports-app-marketing/)); **12 days before kickoff** for a daily-unlock anticipation mechanic (The Athletic).

**Content pivot during the trough.** The clearest offseason guidance is to change *what the product talks about* rather than how often: from match-day results to transfer news, historical stats, pre-season coverage and community content, with push shifting from match-triggered to editorial ([AppFillip](https://appfillip.com/sports-app-marketing/)). The ski-resort framing is the same idea: publish through summer to help people plan winter, including a countdown to opening weekend ([Yodel Mobile](https://yodelmobile.com/seasonal-retention-engagement/)).

---

## Evidence quality notes

**Tier A — measured, reproducible, public:**
- **Wikimedia Pageviews API** (both series). Free, unauthenticated, filters automated traffic, reproducible by anyone. Caveats: (i) it measures *public attention to a topic*, not app usage — the ESPN comparison in §1.3 shows the two curves have different amplitudes; (ii) `NFL_draft` is a proxy for dynasty rookie-draft interest, not a measurement of it; (iii) **a data artifact I verified and resolved** — the final bucket in each series (2026-07 = 97; 2026-06 = 393) is a *truncated partial-month bucket* produced by the API's end-timestamp, not a collapse in traffic. I confirmed this by pulling daily data for 20 Jun – 15 Jul 2026, which ran a steady 65–171 views/day with no discontinuity.
- **ESPN Press Room figures** (10.8M September uniques; 9.3M pre-season August uniques; 13M+ players). Comscore-measured and attributed, but self-published by an interested party and selectively released.

**Tier B — credible first-party product documentation, no results published:** ESPN's 2025 feature list including Auto-Reactivate; Blizzard's returning-player guide; Wowhead's Catch Up Experience guide; Fortnite's Refer a Friend eligibility definition. These verifiably describe what shipped; none publish outcomes. GameRefinery's four-pattern catalogue comes from a market observer with real data access but carries no thresholds, prevalence figures, or results. The Fantasy Footballers / Dynasty Nerds calendar is domain-expert opinion — internally consistent with the Wikipedia curves, but practitioner judgement about a market, not measurement of it.

**Tier C — practitioner frameworks and vendor marketing:** the retention.blog three-level framework, the Appcues TurboTax teardown, the UserGuiding Duolingo teardown, all changelog-design guidance, all win-back cost ratios and rate benchmarks, all seasonal-ASO uplift figures. Hypothesis-generating only. The win-back cost ratios in particular should never be quoted as a planning number.

**Gaps I could not close:**
1. **Airship's Sports & Recreation vertical benchmarks remain unretrieved.** I obtained the 2025 PDF but its text layer uses subset fonts with a shifted encoding, and the vertical labels sit in an unextractable font; page rendering was unavailable locally (no poppler). The blog summary confirms methodology — Jan–Dec 2024, thousands of apps, billions of users, 10th/50th/90th percentiles across 13 verticals including Sports & Recreation — but publishes no numbers. **Recommendation: install `poppler` (`brew install poppler`) and re-read the saved PDF, or request the report directly.** This is now a two-round-old open item.
2. **No published results for any returning-user flow, anywhere.** Duolingo, Fabulous, TurboTax, WoW, ESPN — every documented flow in this brief is described without measured outcomes. This is a real and somewhat surprising hole in the public record.
3. **Sleeper's returning-manager experience** — no teardown exists; would require direct observation.
4. **KeepTradeCut traffic seasonality** — nothing public. No third-party traffic estimates for dynasty tool sites were retrievable.
5. **GDC Vault's canonical lapsed-player talk** is paywalled; abstract only.
6. **App-store rank histories for fantasy apps** are behind Sensor Tower/Appfigures paywalls; the Wikipedia proxy was used instead.

---

## Implications for FTF — hypotheses only

Stated as hypotheses with the evidence they lean on and the reason each might not transfer.

1. **Plan for two peaks, and treat the April–May peak as the underserved one.** The measured curves show dynasty's rookie-draft window (April, ~15x baseline) sits inside redraft fantasy's annual trough. Competitors built for redraft will be quiet then. *Risk:* the NFL-draft proxy measures general football interest, not dynasty-manager behaviour; FTF's own analytics should be checked against this shape before it drives a roadmap.
2. **The real trough is December–March, not "the offseason."** Sequencing FTF's re-engagement work off a "long summer lapse" model would be mistimed. If the pre-draft NFL cycle now starts in January (as the elevated Jan–Mar figures suggest), there is a shoulder season available that most fantasy products ignore.
3. **Build the FTF equivalent of Auto-Reactivate before building a welcome-back screen.** ESPN's answer to seasonal re-entry is to remove the decision. FTF's analogue: on return, the roster is already re-synced from Sleeper, the board is already refreshed against current values, and nothing asks the user to reconnect anything. *This is the highest-confidence hypothesis in the brief* because it is the only pattern where the market leader in the exact category has committed. *Risk:* silent auto-refresh could destroy user-curated board state — needs a non-destructive merge, not a wipe.
4. **Suppress stale state before showing anything new.** WoW hides old quests so returners can relearn. FTF's analogue: on a 90+ day return, collapse or archive stale trade suggestions, expired offers and dead notifications *before* rendering the home screen, rather than presenting a returning manager with a backlog of nine-month-old recommendations. Cheap, and the most directly transferable mechanic found.
5. **The diff is the feature.** TurboTax's strongest move is comparing this year's inputs to last year's and generating proactive value from the delta. FTF holds an unusually rich diff: roster changes since last visit, Elo movement of held players, rookie picks that became players, values that inverted. *Hypothesis:* a "what changed on your roster" surface outperforms both a changelog and a generic welcome-back. It also does not depend on FTF having shipped anything new.
6. **"What changed in the app" belongs in second position, pulled not pushed.** Every cross-domain source that sequences re-entry puts orientation first and product changes later (WoW explicitly; Duolingo's video is post-redesign remediation). Combined with round 1's Drift finding, this argues for a pull-based "new in FTF" panel reachable from the returning-user surface — not a takeover.
7. **Ask a re-segmentation question, not a greeting question.** Duolingo's returning modal asks whether the learner still remembers — an answer that changes where the product puts them. FTF's analogue: "are you still in the same leagues / still rebuilding or contending?" — a question whose answer re-tunes trade generation. Greeting costs a screen and returns nothing; re-segmentation costs the same screen and returns state.
8. **Use the league as the recall channel before using push.** Mobile games' friend-reactivation pattern (PUBG Recall, Fortnite Reboot Rally) exploits exactly the structure FTF has: active users share leagues with dormant ones. This spends social capital instead of notification budget — relevant given round 1's finding that non-personalized push frequency monotonically raises uninstalls. *Risk:* games pay for this with hard currency; FTF has no equivalent reward, and a nag-your-league-mate mechanic can read as spam.
9. **Shorten the gap rather than winning back from the bottom of it.** The 3–5x resurrection differential between recently-dormant and 6+ month dormant users means every cheap touch that keeps a user from fully decaying is worth more than an expensive August blast. *Hypothesis:* a low-frequency, high-relevance shoulder-season artifact (post-NFL-draft rookie repricing; a January "your dynasty year" recap per round 1) beats an August win-back campaign on cost per reactivated user.
10. **Set the ramp on the measured step, not on intuition.** The July→August step is 3.4–3.5x and replicates. Working backwards from a known step with 2–3 months of store/creative lead time and a 6-week reactivation ramp puts preparation in **late May/June** — which is also the trough, i.e. the cheapest time to build. And the ~52% September→October decay says the draft-season window closes faster than it opens: the value of a returning user acquired in October is materially lower.
11. **Measure it yourself, and don't read a short test at face value.** No published results exist for any returning-user flow in any product surveyed, so FTF's own holdout is the only available evidence source — ship the returning-user surface *with* a holdout rather than instrumenting later. And expect the primacy effect to depress early lift while returning cohorts relearn the interface; a seasonal returning cohort is the highest-risk population for that artifact.

---

## Sources

**Measured data**
- Wikimedia Pageviews API — `Fantasy_football_(gridiron)`, monthly, 2022-01 to 2026-07. https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Fantasy_football_(gridiron)/monthly/2022010100/2026070100
- Wikimedia Pageviews API — `Fantasy_football_(gridiron)`, daily, 2026-06-20 to 2026-07-15 (truncation-artifact verification). https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Fantasy_football_(gridiron)/daily/2026062000/2026071500
- Wikimedia Pageviews API — `NFL_draft`, monthly, 2024-01 to 2026-06. https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/NFL_draft/monthly/2024010100/2026060100
- ESPN Press Room. *ESPN Digital 2024: No. 1 in September* (Comscore). http://espnpressroom.com/press-release/espn-digital-2024-no-1-in-september/

**First-party product documentation**
- ESPN Press Room. *ESPN Fantasy Football 30th Anniversary: New Design, New Features, All-New Fantasy App for 2025.* http://espnpressroom.com/press-release/espn-fantasy-football-30th-anniversary-new-design-new-features-all-new-fantasy-app-for-2025/
- Blizzard. *Welcome Home: A Returning Player's Guide.* https://news.blizzard.com/en-us/article/24263354/welcome-home-a-returning-player-s-guide
- Wowhead. *The Catch Up Experience Guide.* https://www.wowhead.com/guide/returning-players-catch-up-experience-guide
- Warcraft Wiki. *Catch Up Experience.* https://warcraft.wiki.gg/wiki/Catch_Up_Experience
- Epic Games. *Fortnite Refer a Friend 3.0.* https://www.fortnite.com/news/fortnite-refer-a-friend-3-0-play-together-and-earn-rewards · *Reboot Rally.* https://www.fortnite.com/reboot-rally
- Sleeper. *Fantasy Football on Sleeper.* https://sleeper.com/fantasy-football
- Intuit TurboTax Support. *Transfer last year's return.* https://ttlc.intuit.com/turbotax-support/en-us/help-article/import-export-data-files/transfer-last-year-return-2021-turbotax-windows/L0JcyjyrG_US_en_US

**Industry analysis / teardowns**
- GameRefinery. *Four Ways How Mobile Games Re-Engage Lapsed Players.* https://www.gamerefinery.com/four-ways-how-mobile-games-re-engage-lapsed-players/
- GDC Vault. Mansell, P. (Jagex, 2015). *Returners and Retention — How to Win Back Lapsed Players.* https://gdcvault.com/play/1022237/Returners-and-Retention-How-to (abstract only; paywalled)
- GameSpot. *Destiny 2 Into The Light … Skippable New-Player Onboarding.* https://www.gamespot.com/articles/destiny-2-into-the-light-to-add-raid-boss-rush-mode-skippable-new-player-onboarding/1100-6522337/
- Destructoid. *Destiny 2: Into the Light introduces onboarding skip.* https://www.destructoid.com/destiny-2-into-the-light-introduces-onboarding-skip-for-new-players-heres-how-it-works/
- Roastbrief US. *How The Athletic Is Turning Pre-Season Anticipation Into a Content-Led Engagement Platform.* https://roastbrief.us/how-the-athletic-is-turning-pre-season-anticipation-into-a-content-led-engagement-platform/
- Airship. *A Marketer's Guide to Push Notification Benchmarks.* https://www.airship.com/blog/a-marketers-guide-to-push-notification-benchmarks/ · 2025 PDF (unextractable): https://growth.airship.com/rs/313-QPJ-195/images/Airship-2025-Push-Notification-Benchmarks-EN.pdf

**Domain (dynasty) sources**
- The Fantasy Footballers. *Dynasty Trade Windows: Timing the Market.* https://www.thefantasyfootballers.com/dynasty/dynasty-trade-windows-timing-the-market-fantasy-football/
- Dynasty Nerds. *May Post-Draft Dynasty To-Do's — Fantasy Football Calendar.* https://www.dynastynerds.com/dynasty/may-dynasty-fantasy-football-calendar/ (403 on fetch; search-snippet sourced)

**Practitioner frameworks (Tier C)**
- retention.blog. *Win back more users with re-onboarding.* https://www.retention.blog/p/win-back-more-users-with-re-onboarding
- UserGuiding. *Duolingo — an in-depth UX and user onboarding breakdown.* https://userguiding.com/blog/duolingo-onboarding-ux
- Appcues. *How TurboTax turns a dreadful user experience into a delightful one.* https://www.appcues.com/blog/how-turbotax-makes-a-dreadful-user-experience-a-delightful-one
- Adapty. *App Seasonality: How to Prepare Your App for Peak Seasonality.* https://adapty.io/blog/app-seasonality/
- Yodel Mobile. *Seasonal retention and engagement strategies.* https://yodelmobile.com/seasonal-retention-engagement/
- AppFillip. *Sports app marketing strategies.* https://appfillip.com/sports-app-marketing/
- Frill. *15 Best Changelog Examples.* https://frill.co/blog/changelog-examples
- Worknotes. *Best Changelog Page Designs.* https://www.worknotes.ai/blog/best-changelog-page-designs
- Amplitude. *What Is a Resurrected User.* https://amplitude.com/explore/analytics/resurrected-user
- Monetizely. *How to Calculate Resurrection Rate for Dormant Users.* https://www.getmonetizely.com/articles/how-to-calculate-resurrection-rate-for-dormant-users-a-critical-saas-metric
- Eightx. *Win-back and reactivation rate benchmarks for DTC.* https://eightx.co/blog/average-win-back-reactivation-rate-benchmarks
- DigitalApplied. *Customer Win-Back Campaigns: 2026 Retention Playbook.* https://www.digitalapplied.com/blog/customer-win-back-campaigns-2026-retention-playbook
- FlareLane. *Win-Back Campaigns for Inactive Customers.* https://flarelane.com/en/blog/win-back-inactive-customers/
- US Tech Automations. *Ecommerce customer win-back campaigns ROI analysis 2026.* https://ustechautomations.com/resources/blog/ecommerce-customer-win-back-campaigns-roi-analysis-2026
- social.plus. *4 Proven ways to re-engage inactive users.* https://www.social.plus/blog/4-proven-ways-to-re-engage-inactive-users-to-fuel-app-growth
- Statsig. *Calculating lift in A/B tests.* https://www.statsig.com/perspectives/calculating-lift-ab-tests-impact
- MetricGate. *A/B Test Novelty Effects: Detection.* https://metricgate.com/blogs/ab-test-novelty-effect-detection/
