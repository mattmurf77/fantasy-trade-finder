# Monetization Brainstorm → Top-5 Plans (with growth loops)

Owner: pm-monetization (with mkt-* and pm-* persona brainstorms). Date: 2026-07-17.

## Question & context

What are FTF's monetization options, which five are best, and — after researching the
tactics behind each — how do they rank by **conversion impact**, **total monetization
value**, and **industry fit**? Per operator request, growth-loop mechanics (referral
incentives, free-premium rewards for user joins) are folded into each plan.

Stage: pre-revenue, pre-public-launch, TestFlight v1.7.3, no client analytics, no
payment/ad SDKs. Solo operator. Peak season (Jul–Aug draft ramp) is starting **now**.
Guardrail honored throughout: the core loop (rank → see trades) is never gated.

Method: two independent persona brainstorms (marketing composite, PM composite) → 30
ideas → evaluation → top 5 → six web-research briefs (subscription, season pass,
lifetime, affiliate, ads, referral loops; all claims cited in the research appendix
summaries below) → plans → final scored prioritization.

## Idea pool (30 ideas, both personas)

**PM pool:** Pro portfolio tier · Trade Engine+ knobs · Season Pass · Founder Lifetime ·
League Pass (commissioner buys) · Alert Pack · Deep-dive credits (AI trade reports) ·
Trial/intro-offer mechanics · Chalkline cosmetics · Values API (B2B) · Tip jar · Rookie
Draft War Room · Cross-platform bundle · Extension Pro · Trade Concierge (Elite AI tier).

**Marketing pool:** Native ad units · Rewarded ads · Sportsbook/DFS affiliate ·
Direct-sold sponsorships · Creator rev-share codes · Trade-deadline sponsored event ·
Contrarian Report newsletter · Divergence-data licensing · White-label calculator
widget · Promoted content slots · Card-collectibles affiliate · Commissioner merch
affiliate · Ad-free founding pass · Best-ball tie-in campaigns · Extension sponsor line.

### Evaluation

Scored on stage-fit, revenue potential, effort, guardrail compliance, differentiation,
risk. Full scoring table lives in the session working notes; outcomes:

- **Merged into top 5:** engine knobs, alerts, trial mechanics, Extension Pro → Pro
  pillars; rookie War Room → Season Pass; ad-free founding pass + Founder Lifetime →
  one Founder offer (both personas converged on this independently — the strongest
  signal in the exercise); best-ball campaigns + cards + commissioner merch → affiliate
  layer; native + rewarded → hybrid ads.
- **Backlog (good, not now):** League Pass (design league-scoped entitlements early,
  ship post-launch), Trade Concierge Elite (price-ladder tier v2), Values API + data
  licensing (needs ranking-population scale), white-label widget, newsletter
  (retention tool first), creator codes (needs attribution), deadline event (year 2),
  direct-sold sponsorships (solo-op sales time), deep-dive credits, tip jar
  (superseded by Founder offer).
- **Killed:** cosmetics (ceiling too small for solo-op focus), promoted content slots
  (sponsored analysis inside a "YOUR values" product is an existential trust conflict).

## The growth-loop spine (applies across all five plans)

FTF's referral unit is the **league**: every user sits in a 10–14 person Sleeper league,
and the mutual-interest trade signal *provably improves* as leaguemates join and rank.
Sleeper itself grew >90% virally on exactly this channel (a16z memo). This is "pull"
virality — the invite is a favor, not an ad. Mechanics used by the plans below:

1. **Signal-quality framing first, reward second.** Surface "3 of 12 leaguemates
   ranked — trade confidence LOW" in Matches/Trades screens; the invite CTA rides the
   product truth, the give-get is the kicker.
2. **Give-get in product currency:** 1 free Pro month per **activated** leaguemate
   (joined your league in FTF + completed ≥25 ranking matchups), both sides rewarded,
   capped at 4–6 months/season (Duolingo/Dropbox pattern; worst-case cost ≈ one season
   pass).
3. **Milestone unlock:** 8+ of your league activated → free Season Pass for you.
4. **Group-unlock experiment (white space — no published case study exists):** when
   8/12 leaguemates have ranked, the *whole league* gets Pro trade suggestions free for
   2 weeks. A/B against per-referrer rewards.
5. **Apple-proofing:** every reward triggers on in-app *actions*, never install/signup
   (guideline 3.2.2(x) allows incentivized in-app actions; invitee-install rewards get
   rejected). Never gate already-paid features behind invites (3.1.2(a)).
6. **Granting:** server-side entitlement grants on `acct_` (or RevenueCat promotional
   entitlements) — time-boxed, never auto-converts to a charge. Apple offer codes
   reserved for win-back blasts.
7. **Built-in fraud control:** rewards only for verified co-members of the referrer's
   real Sleeper league, one reward per unique Sleeper user ever — kills the 5–15%
   self-referral fraud vector for free.
8. **Share card before referral program:** Chalkline-styled trade-proposal/board card
   with deep link, surfaced at value peaks (trade found, ranking finished) — contextual
   deep links convert 2–6x bare links (Branch). The league group chat already contains
   all 11 targets.
9. **Expectations:** instrument for K ≈ 0.2–0.5; track invites/activated user,
   invite→activation, and referred-user retention (Wharton: referred customers show
   +16–25% CLV, −18% churn — net of reward cost).

## The five plans

### Plan A — FTF Pro (freemium subscription) — the anchor

**Packaging.** Free: 1 synced league, full core loop, raw values/tiers. Pro: unlimited
leagues + Portfolio, trade-engine power knobs (aggression, lanes, fuzzy tolerance,
crown-asset override, future three-team), alerts (post-launch pillar), Extension Pro
overlays, ad-free. Never gate rank→trades in the synced free league.

**Pricing (benchmarked).** $4.99/mo (trial-less decoy) · **$34.99–39.99/yr hero SKU
with 14–30-day trial** (long trials convert 42–46% vs 25% for short). Undercuts Dynasty
Nerds ($6.99/$69.99), sits in the empty $30–50/yr band between free tools (KTC,
FantasyCalc, Dynasty Daddy) and $70–120/yr content bundles.

**Paywall.** Soft, multi-page (+37% vs single-page, Superwall 40M-open study), placed
at end of onboarding *after* the aha: Sleeper login → league sync → show 2–3 real
mutual-gain trades → paywall for the full list. ~90% of trial starts happen Day 0.

**Entitlements.** Payment-agnostic from day one: one entitlement service on `acct_`
fed by StoreKit (RevenueCat SDK) *and* Stripe webhooks. US apps may currently link to
web checkout with zero Apple fee (May 2025 guideline change) but SCOTUS review lands
~mid-2027 — don't hard-depend on it. Enroll in Small Business Program (15%).

**Growth loop.** Give-get months (#2), group-unlock trial (#4), signal-quality CTA
(#1). Rewarded months extend paid subs (auto-extension is the canonical pattern).

**Riskiest assumption:** multi-league prevalence and knob usage among real users —
un-instrumented today. **Cheapest test:** an-user-data query on league counts per
account + `user_events` knob usage before finalizing the gate list.

**Assumed revenue math** (all assumed, not measured): 1,000 launch-season actives ×
2–3% freemium paid conversion ≈ 20–30 subs, ~80% annual → ≈ $700–1,000/yr net year 1,
compounding with scale and the ladder (Elite tier later). Annual first-renewal
benchmark is only 25–37% — plan year-2 economics around win-backs (cancel-flow
discount offer within 10–15 min of cancel intent).

### Plan B — Season Pass (calendar-aligned one-time SKU)

**Shape.** Copy Fantasy Footballers' UDK, not MLS: **year-labeled non-consumable IAP
("2026 Season Pass", $19.99)** granting Pro-equivalent entitlements for the labeled
season; next season = new SKU = natural repurchase moment. Apple handles restore; no
expiry cron (non-renewing subs would make expiry + cross-device delivery your
problem). Nets ~$17 under SBP.

**Second SKU:** spring **Rookie Pass** (~$9.99, Apr–May window; pick ladder, tiers
draft board, pick-vs-player suggestions — absorbs the War Room idea), with a $5–10
upgrade path to the full pass (UDK→UDK+ pattern).

**Price ratchet (inverse discounting — demand is deadline-driven):** early-bird
$14.99 in June, full $19.99–24.99 late-July→Labor Day. Returning-buyer discount in
year 2 substitutes for auto-renew retention. Feb–Mar trough: DLF-style flash sale on
the upcoming Rookie Pass.

**Why alongside Plan A:** captures the 41%-subscription-fatigued segment; median
annual auto-renewal is only 23–40% anyway, so a strong August re-buy trigger competes.
Both SKUs sit on one 3-option paywall (see Plan C anchoring).

**Growth loop.** Milestone unlock (#3: 8 activated leaguemates → free pass) makes the
pass itself the referral prize; share cards carry the seasonal urgency ("Deadline
SZN").

**Riskiest assumption:** year-over-year re-buy rate (no vendor publishes theirs;
revealed preference only). **Cheapest test:** ship it and measure season 2.

**Assumed math:** 500 passes ≈ $8.5k/season net at moderate scale; launch year
realistic 50–150 passes ≈ $850–2,500.

### Plan C — Founder Lifetime (launch-window offer)

**Offer.** **$79 non-consumable "Founder" SKU** (~3.5–4x intended annual — the
researched band; folk-wisdom 2–3x is too low), capped honestly at **first 100
founders**, TestFlight-exclusive window before public launch, then closed forever.
Permanent Founder badge on profile/trade cards (Discord Early Supporter pattern) +
founders wall. Family Sharing OFF. Same "pro" entitlement as subs; build the
"active sub + lifetime → prompt cancel" detection day one.

**Messaging:** value-first ("everything FTF ever ships, one price, locked forever +
Founder badge"), solo-dev support as the second sentence — Overcast's 1.9% patronage
rate proves donation framing doesn't convert.

**Role in the system:** cash now, willingness-to-pay probe (A/B $79 vs $59 on the
TestFlight list calibrates the public paywall), and the permanent **anchor** on the
3-option paywall (monthly decoy → annual pre-selected → lifetime ceiling pushes
annual selection to ~70%). Lifetime must never become the dominant model (lifetime-
dominant apps monetize ~half as well; expect 15–20% pull-forward cannibalization —
priced in at 4x).

**Growth loop.** Founders are the evangelist seed: badge + share card + first access
to the give-get program; a "founders recruit their league" push is the program's
warm-start.

**Riskiest assumption:** TestFlight cohort size/warmth supports meaningful volume.
**Cheapest test:** the offer itself — it *is* the cheapest willingness-to-pay test
available.

**Assumed math:** 50–100 × $79 ≈ **$4–8k one-time**, ~85% net.

### Plan D — Endemic affiliate layer (best-ball first)

**Partner #1: Underdog** (direct application, negotiated CPA $25–150/first-time
depositor, no state licensing needed for DFS — unlike sportsbooks, which need NJ/PA/CO
licenses and are **skipped** despite $100–300 CPAs). Partner #2 later: PrizePicks
(higher Sleeper-channel-conflict optics). Sleeper API has no ToS restricting this;
residual risk noted.

**Placement (FantasyPros pattern — keep iOS clean):** affiliate lives on **web +
Chrome extension** first; in-app at most an outbound Safari-link "Best Ball" info
card. DFS links likely mean a "Contests" declaration; avoid anything triggering the
18+ gambling rating. FTC disclosure adjacent to every placement ("FTF earns a
commission if you sign up").

**The killer feature-placement:** "convert your dynasty board into an Underdog draft
strategy" — FTF uniquely knows where the user diverges from ADP, which *is* best-ball
edge. **Timing: Best Ball Mania entries close before Week 1 — the window is now
(Jul–Aug).** Cards affiliate (eBay EPN 1–4%) = distant experiment.

**Growth loop.** The "my board vs. ADP" shareable graphic is simultaneously the
affiliate placement and an acquisition artifact (deep link back to FTF).

**Riskiest assumption:** depositor conversion of engaged niche users (benchmark
15–25% click→reg, 2–5% click→depositor). **Cheapest test:** one web placement +
UTM/subid tracking during the BBM window.

**Assumed math:** 1,000 actives seeing contextual placement ≈ 20–50 FTDs ≈
**$500–5,000/season**.

### Plan E — Hybrid ads on the free tier

**Stack.** AdMob only (no mediation until ~100k DAU) via `react-native-google-mobile-
ads` Expo config plugin (EAS dev build; pin past the SDK-54 plugin bug, GitHub #820).
One adaptive banner on high-dwell browse surfaces (trends/tiers browsing — never
mid-calculator) + **one rewarded placement as the flagship** ("watch → unlock today's
extra deep scan"; rewarded $15–40 eCPM vs banner $0.45–1.50; cap ~3/day). ATT prompt
with pre-prompt explainer — sports is the #1 opt-in vertical (~50%). Web: AdSense day
one → Mediavine Journey at 10k sessions/mo → Raptive at 25k pageviews (the network
KTC and FantasyCalc actually run; thresholds dropped Oct 2025). Skip interstitials.

**Pattern: Dynasty Daddy's hybrid, not KTC's pure-ads** — ads exist partly to sell
their own removal (ad-free is a Pro perk; layering ads onto an IAP model lifted IAP
revenue ~30% in documented cases). Rewarded watchers are the warmest premium leads —
log them via `user_events`.

**Growth loop.** Alternate currency: **invite an activated leaguemate → 30 ad-free
days** — monetization-neutral for never-payers, feeds the same loop. If D7 retention
dips post-ads, cut banners before rewarded.

**Riskiest assumption:** ads don't dent retention/word-of-mouth pre-PMF. **Cheapest
test:** web AdSense first (no app build risk), watch retention delta.

**Assumed math:** $150–700/mo at 1,000 DAU; tens of $/mo at hundreds. A coffee budget
year 1 — shipped for the hybrid pattern and the stack learning, not the money.

## Final prioritization (the ask: conversion impact · total monetization value · industry fit)

Scores 1–5, equal weights. Conversion impact = how much the method itself drives
free→paid (or revenue-event) conversion; total value = realistic cumulative revenue
over ~24 months at plausible scale; industry fit = how proven the mechanic is in
fantasy/dynasty specifically.

| # | Plan | Conversion impact | Total value | Industry fit | Σ | Rationale |
|---|------|:--:|:--:|:--:|:--:|---|
| **1** | **A · FTF Pro subscription** | 5 | 5 | 4 | **14** | Owns the paywall/trial machinery (Day-0 trials, multi-page +37%, cancel-flow saves); only recurring compounding line; Dynasty Nerds proves the model, though free comps cap the ceiling |
| **2** | **B · Season Pass** | 4 | 4 | 5 | **13** | Lower purchase friction + deadline urgency; re-buys each season at ~$17 net; the draft-kit/one-time shape is *the* most proven paid mechanic in fantasy football |
| **3** | **D · Affiliate layer** | 3 | 3 | 4 | **10** | No user payment barrier at all (conversion happens on the partner's dime); $500–5k/season now, scales with users; endemic norm across fantasy media |
| **4** | **C · Founder Lifetime** | 4 | 2 | 3 | **9** | Warm-list scarcity converts hard but once; hard revenue ceiling (~$8k) + pull-forward; indie-app norm more than a fantasy norm. Wins the tiebreak vs. ads on stage-fit: it ships first and seeds the whole paywall |
| **5** | **E · Hybrid ads** | 2 | 2 | 5 | **9** | Indirect conversion only (ad-free upsell lift); coffee-budget revenue until thousands of DAU; but the single most proven model in dynasty tools (KTC, FantasyCalc, Dynasty Daddy all run it) |

**Sequencing is not the same as ranking:**

1. **Now (Jul):** Founder offer to the TestFlight list (needs ASC IAP + first paywall)
   + Underdog partner application + one web affiliate placement (BBM window closes at
   Week 1). Share-card artifact ships first (it serves every plan).
2. **Launch (Aug–Sep):** 3-option paywall (Pro monthly decoy / annual-or-Season-Pass
   hero / lifetime anchor until cap hits) + give-get referral v1.
3. **Post-launch:** alerts pillar, group-unlock A/B, web AdSense; mobile ads and
   Mediavine once DAU/session thresholds arrive.
4. **Prerequisite under everything:** client-side funnel instrumentation — every
   conversion number above is assumed or benchmarked, none measured.

## Decisions needed (operator calls, each with a recommendation)

1. **Green-light the Founder offer and its price?** Recommend: yes, $79, cap 100,
   TestFlight-exclusive window in August ($59 A/B arm optional).
2. **Pro pricing:** recommend $4.99/mo + $34.99/yr hero with 14-day trial.
3. **Season Pass alongside annual, or annual only at launch?** Recommend: both on one
   paywall (fatigue segment is real; UDK precedent strong); collapse later if data
   says they cannibalize.
4. **Affiliate green light + partner:** recommend Underdog, web/extension-only, now.
5. **Ads timing:** recommend web AdSense at launch, mobile ads deferred until ≥500 DAU
   and D7 stability.
6. **Referral reward sizing:** recommend 1 month/activated leaguemate, cap 4, plus
   the group-unlock A/B.

## Handoffs

- **an-data-architect:** client-side event spec for funnel + paywall + referral
  attribution + ARPDAU/retention delta (blocking prerequisite for every plan).
- **eng-backend:** entitlement service on `acct_` (StoreKit + Stripe + promotional
  grants + league-scoped future-proofing), referral qualification logic (league
  co-membership + activation gating).
- **eng-mobile:** RevenueCat integration, 3-option paywall (Chalkline), Founder SKU +
  badge, share-card renderer, later ATT + AdMob.
- **eng-web / eng-integrations:** Stripe checkout, Underdog partner application +
  placement, app-ads.txt, AdSense.
- **pm-growth:** owns give-get/group-unlock experiment design (this doc is its spec
  seed). **fin-forecast:** revenue model from the assumed-math sections.
- **mkt-lifecycle:** Founder-window and early-bird/win-back campaign copy calendar.
- **legal-privacy:** FTC disclosure copy; ATT/privacy-label review when ads ship.

---

*Research appendix summaries (six briefs with full citations) were produced in-session;
key figures are inlined above. All revenue figures are assumed or benchmarked (sources
inline) — nothing is measured until instrumentation ships.*
