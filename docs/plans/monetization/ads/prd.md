# Hybrid Ads (Free Tier) — PRD

Owner: pm-monetization → eng-mobile / eng-web / eng-integrations / eng-backend.
Date: 2026-07-17. Status: DRAFT (Plan E of the
[top-5 monetization plans](../../../business/product/2026-07-17-monetization-brainstorm-and-plans.md)).
Builds on the [monetization platform foundation](../00-platform-foundation.md) —
entitlements, flags, referral infra, and instrumentation are specified there, not here.
Design: [hld.md](hld.md) · [lld.md](lld.md).

## 1. Opportunity — and honest expectations

Ads are the single most proven model in dynasty tools (KTC and FantasyCalc run
Raptive; Dynasty Daddy runs Freestar + a $6/mo ad-free club — the exact hybrid we
copy). No dynasty comp is mobile-app-first, so mobile ad real estate is uncontested.

**Revenue is a coffee budget and the PRD says so up front:** ~$150–700/mo at 1,000
DAU (ARPDAU $0.005–0.02); tens of $/mo at hundreds of DAU
([research appendix, ads brief](../../../business/product/2026-07-17-monetization-research-appendix.md)).
We ship this for the **hybrid pattern** — ads exist partly to sell their own removal
(layering ads onto an IAP model lifted IAP revenue ~30% in documented cases) — and
for the stack learning, not the money.

## 2. Goals / non-goals

**Goals**
1. Establish the hybrid pattern: ads on free tier, ad-free as a Pro perk, rewarded
   watchers logged as warm premium leads.
2. Measurable Pro upsell lift from the "remove ads" perk and rewarded-preview funnel.
3. Web ad stack live at launch (AdSense → network ladder); mobile stack built dark
   and gated on DAU/retention thresholds.
4. Zero damage to the core loop: rank → see trades is never interrupted by an ad.

**Non-goals**
- Meaningful ad revenue in year 1 (see §1).
- Interstitials, native ads, app-open ads, mediation — all skipped at this scale.
- Rewarded ads gating any *existing* free functionality (hard guardrail; rewarded
  unlocks only new EXTRA capacity — see §4.3).

## 3. User stories

1. **Free user, browsing:** while scrolling Trends or the Tiers board I see one
   Chalkline-framed adaptive banner at the bottom of the screen. It never appears
   while I'm ranking, building a trade, or in the calculator. If no ad fills, the
   slot collapses (mobile) or shows an FTF house card (web).
2. **Rewarded watcher:** on the Trades screen I see "Watch a short ad → unlock
   today's extra deep scan." I watch, the deep scan runs, and I can do this up to
   3 times a day. Nothing I could already do for free is behind this.
3. **Pro user:** I see no ads, no ad slots, no ATT prompt, no rewarded CTA (deep
   scans are included in Pro). No ad request is even made from my device.
4. **Invited-leaguemate reward:** I invite a leaguemate; when they verify into my
   league and complete ≥25 matchups, I get **30 ad-free days** (a lightweight
   `ad_free` entitlement — not full Pro; see HLD §4).

## 4. Functional requirements

### 4.1 Mobile (behind `monetize.ads_mobile`, dark by default)
- **Stack:** AdMob only, via `react-native-google-mobile-ads` official Expo config
  plugin. Requires an EAS dev build (not Expo Go); pin the plugin version past the
  Expo SDK-54 plugin bug (GitHub issue #820). No mediation until ~100k DAU.
- **Banner:** exactly ONE anchored adaptive banner, only on high-dwell browse
  surfaces: `TrendsScreen` and `TiersScreen` (browse mode). NEVER on
  TradeCalculatorScreen, RankScreen, or any core rank flow (QuickSet/QuickRank/
  PickAnchor/ManualRanks). Ad-load failure → collapse silently (height 0).
- **Rewarded:** exactly ONE placement — "watch → unlock today's extra deep scan"
  (see §4.3), capped **3/day per user, server-tracked** (survives reinstall and
  cross-device). Rewarded eCPM $15–40 vs banner $0.45–1.50 — this is the flagship.
- **ATT:** pre-prompt explainer sheet (Chalkline) → system ATT prompt. Sports is
  the #1 opt-in vertical (~50%). Prompt only shown to users who will actually see
  ads (never Pro/ad-free). AdMob serves non-personalized without consent, so a
  denial still monetizes at reduced eCPM.
- **Consent:** Google UMP consent flow for GDPR-adjacent users, sequenced before
  ATT (HLD §5). `app-ads.txt` published at the web domain root.

### 4.2 Web (behind `monetize.ads_web`)
- **Ladder:** AdSense day one → apply to Mediavine Journey at 10k sessions/mo →
  Raptive at 25k pageviews/mo (the network KTC and FantasyCalc run; thresholds
  dropped Oct 2025).
- **Slots:** one styled slot per candidate page — `positional-tiers.html`,
  `player.html`, `ranking-method.html`, `faq.html` (browse/content surfaces; never
  the `index.html` app core loop, never privacy/terms). Slots live inside
  Chalkline-token containers (ink surfaces, hairline border, "SPONSOR" TickLabel);
  the creative itself is third-party, the frame is ours.
- **House-ad fallback:** unfilled/blocked slots render a config-driven FTF house
  card (newsletter / extension / Pro) — never an empty hole.

### 4.3 Rewarded capacity guardrail
"Deep scan" is a **new** capability introduced with this plan (assumption: exact
scan semantics owned by the trade-engine owner; placeholder = an on-demand,
deeper-than-default trade-finder pass, LLD §3). Free tier behavior today is
unchanged and stays unchanged; rewarded only mints EXTRA deep scans. Pro includes
deep scans without ads. Nothing that is free today ever moves behind a rewarded ad.

### 4.4 Hybrid / entitlement behavior
- Ad-free is a Pro perk: an active `pro` OR `ad_free` entitlement suppresses all
  ads — client hides the UI **and** makes no ad request (HLD §3).
- Rewarded watchers are warm premium leads: every completion logged via
  `record_event` for lifecycle targeting.
- Growth loop: activated-leaguemate referral can pay **30 ad-free days**
  (`entitlements` row, `entitlement='ad_free'`, `source='promo_referral'`,
  `expires_at=+30d`) as an alternate reward currency (HLD §4; operator decision D4).

## 5. Success metrics + instrumentation

Event names (via existing `record_event` / `user_events`; client-side event spec
from an-data-architect is a blocking prerequisite per foundation §6):

| Event | Props | Fired |
|---|---|---|
| `ad_impression` | `{surface, format: banner\|rewarded\|house, filled, platform}` | every slot render outcome |
| `rewarded_completed` | `{surface, remaining_today}` | server-side, on claim |
| `att_response` | `{status: authorized\|denied\|restricted}` | after system prompt |
| `arpdau` rollup | `{revenue_est, dau, arpdau}` | nightly cron (foundation §4 pattern) |

Targets (assumed, not measured — instrument first):
- ATT opt-in ≥40% (vertical benchmark ~50%).
- Rewarded completion ≥90% of starts; ≥5% of free DAU complete ≥1 rewarded/day.
- Ad-free perk cited in Pro paywall taps (upsell lift measurable once paywall
  events exist).

**Retention-delta guard (the metric that can kill the feature):** D7 retention of
the first post-ads cohort vs the trailing 4-week pre-ads baseline. If D7 dips
beyond noise, **cut banners before rewarded** (banners are the low-value, high-
annoyance half). This guard is a launch requirement, not a nice-to-have.

## 6. Rollout gates

1. `monetize.ads_web` ON at public launch (web first — no app-build risk; cheapest
   test of the retention question).
2. `monetize.ads_mobile` stays OFF until **≥500 DAU AND D7 retention stable for 4
   consecutive weeks** (operator judgment on "stable"). Then: TestFlight cohort →
   watch guard metric 2 weeks → production flip.
3. Both flags are independent kill switches; Pro/ad-free entitlement overrides
   both. Foundation rollout order (§1) already places ads last.
4. Network ladder upgrades (Mediavine/Raptive) gate on their published traffic
   minimums, not on flags.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Ads dent retention/word-of-mouth pre-PMF (top risk) | Web-first rollout; mobile DAU gate; retention-delta guard + banner-first kill rule; one banner max; no interstitials |
| App Review friction (ATT, rewarded mechanics) | Pre-prompt explainer follows ATT HIG; rewarded gates only new capacity; describe plainly in Notes for Review |
| eCPM reality: revenue rounds to zero at our scale | Framed as pattern-building (§1); no revenue-dependent commitments; AdSense (not premium networks) until thresholds |
| SDK-54 Expo plugin bug (#820) breaks builds | Pin fixed plugin version; ads code no-ops without the native module (LLD §7) |
| Cap abuse (rewarded farming) | Server-side 3/day cap; SSV upgrade path noted (LLD §4); stakes are one deep scan — low |
| Chalkline violation by third-party creative | We control the frame, not the creative; slots isolated in specced containers; house ads fully Chalkline |

## 8. Operator decisions

| # | Decision | Recommendation |
|---|---|---|
| D1 | Green-light web AdSense at launch? | Yes (matches plan-doc decision #5) |
| D2 | Mobile DAU gate number | 500 DAU + 4-week D7 stability |
| D3 | Deep-scan definition + free baseline | Delegate to trade-engine owner; placeholder in LLD §3; must be NEW capacity |
| D4 | Referral reward currency: when does `ad_free` 30d apply vs the Pro-month reward (foundation §5)? | Pro month remains the primary give-get; `ad_free` 30d pays activations **beyond the 4/season Pro-month cap** (and is the A/B alternate arm for never-payers). pm-growth owns the experiment split |
| D5 | AdMob account + `ADMOB_APP_ID` provisioning | Operator creates account; IDs into `secrets.local.env` / Render env per secrets convention |
