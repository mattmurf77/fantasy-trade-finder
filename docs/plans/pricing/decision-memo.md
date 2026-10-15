# Pricing decision memo: Fleeced Pro, Founder, Season Pass, tips, referral v2

> **Owner:** `monetization-pm` (drafting worker, wave 2 task 4) · **Reviewer:** `head-product` · **Decider:** operator
> **Date:** 2026-10-15 · **Status:** DRAFT, awaiting operator decisions · **Base:** `origin/main` `678834ab`
> **What this is:** a decision memo, not a build. It flips no flag and touches neither App Store Connect nor StoreKit.
> The build is a later scope block (`docs/templates/feature-scope.md`) under the full four feature gates.
> **Number labels:** **[M]** measured (source cited), **[B]** benchmarked (URL and date), **[A]** assumed, **[P]** pending an owner.
> **Evidence copies:** [research/platform-and-benchmarks.md](research/platform-and-benchmarks.md) (Apple, RevenueCat, Stripe;
> accessed 2026-10-15) and [research/repo-facts.md](research/repo-facts.md) (repo state at `678834ab`, file:line cites).

## TL;DR

- **Pro launches with the App Store build and sells only what exists:** unlimited synced leagues (free = 1 per season,
  swap with a confirm) and cross-league Portfolio. The core loop and every depth tool already free stay free.
- **Prices: $6.99/mo (14-day trial) and $34.99/yr ("1 month" trial, "save 58%").** Set them now, while there are no
  subscribers: later, a raise notifies every subscriber and a cut passes through to all of them.
- **Founder: $119**, non-consumable, cap 100 on the server, App Store build only, Family Sharing off; expect single digits.
- **Season Pass: defer to 2027** as a non-renewing subscription: $24.99 ($22.99 in July), access to 2028-02-15. A $19.99
  June–July early-bird would beat annual per covered month. Rookie Pass deferred. **Tips ship as built;** no ads or affiliate.
- **Referral v2:** one Pro month per activated leaguemate, both sides, cap 2 per season, no milestone, grants by state.
- **No paid launch before** Sleeper commercial coverage, Apple and RevenueCat setup, seven eng fixes, and ≥2 weeks of
  observe mode. Two fixes stop free Pro: sandbox webhooks grant in prod; a Season Pass purchase projects as perpetual.
- **Riskiest assumption: enough users sync 2+ leagues.** It's unmeasured, and one read-only query tests it. Under 20%,
  Pro still ships (single-league users lose nothing), but the one-shot Founder window waits for a new pillar.

## Decision table

| # | Decision | Recommendation | Main alternative | Cost of being wrong |
|---|---|---|---|---|
| 1 | Packaging | **A:** Pro = unlimited leagues + Portfolio | B: no Pro until a new pillar; Founder + tips | If multi-league is rare, A sells almost nothing (single-league users untouched); branch in §10 |
| 2 | League cap | 1 distinct synced league per season, swap with confirm | No cap (Pro = Portfolio only) | Second-league leaguemates never reached through that user; one flag reverts it |
| 3 | Pro price | **$6.99 / $34.99** | $4.99/$34.99 · $6.99/$39.99 | Too low: any raise notifies every subscriber. Too high: trial→paid falls. Cuts are never grandfathered |
| 4 | Feature grid | Drop `engine_knobs`, `extension_overlays`, `ad_free`; fix the Portfolio line | Keep them and build first | App Review 2.3 / 3.1.2(c); 5.6 "charge for features … not delivered"; trust |
| 5 | Season Pass | Defer to 2027; non-renewing; $24.99 ($22.99 July); ends 2028-02-15 | Ship a 2026 pass now | A new product type and rework mid-season, for a pass covering ~4 months |
| 6 | Founder | **$119**, cap 100, App Store launch, Family Sharing off | $149 (4.3× annual) | At worst 100 × ~$56 under a 5-year subscriber (~$5.6k gross); if higher, fewer sales from a tiny list |
| 7 | Tester comp | 90-day Pro comp before enforcement, plus the Founder offer | Perpetual comp | A perpetual comp takes the warmest users out of the paying pool forever |
| 8 | Referral v2 | 1 month per activated leaguemate, both sides, cap 2/season, no milestone | July: cap 4–6 + milestone | Too generous: rewards plus trial cover the whole season, leaving no paid moment |
| 9 | Ads / affiliate | Not now; reopen on the §4.5 trigger | Web ads or affiliate at launch | Trust and Sleeper-terms exposure, for $150–700/mo even at 1,000 DAU [B, July appendix] |
| 10 | Sleeper coverage | **Gate 0:** no paid launch until the operator confirms commercial coverage | Launch, ask later | Losing platform access ends the product, not just the revenue |
| 11 | Kill criteria | WAT and W1-retention thresholds (§8.2) | None | Damage from gating goes unseen at n ≈ 16 |

## 1. Question & context

**Question.** What does FTF charge for, at what prices, and in what order? The answer has to be final enough for the
operator to approve and for `head-eng` to scope; it feeds ASC setup, `GET /api/paywall/config`, the gate list and launch.

**Context.** FTF is pre-revenue, TestFlight-only, run by one operator, with 3–16 measured users (§2). The purchase stack
is built but dark (RevenueCat client, webhook ledger and projector, PaywallScreen, tip jar, manual-grant routes), and
**nothing is gated:** `_require_pro` (`backend/server.py:30965-30977`) wraps zero routes (`iap-enablement/scope.md:39-41`).
Public launch is likely mid-season [A, lead's steer].

**Rulings treated as fixed.** *Operator:* 14-day monthly and 30-day annual trials (`CHANGELOG.md:519-521`), the annual
set up as "1 month"; the tip jar (`ftf_tip_199/499/999`, grants nothing); the `ftf_*` SKU ids (Q-034); the never-gated list
("the deck, Find-a-Trade, matches, the calculator, sends, every tab", `2026-08-14-open-access-onboarding.md:285`); and
**never tolled**: no data-generating action is ever gated. **Its source, "timing doc §7/§11", is on no ref**; the best
paraphrases are `origin/claude/new-user-feedback-06dabd:living-memory/HANDOFF.md:195` and `iap-enablement/scope.md:39-41`.
*P20 (head-product, 2026-10-15):* referral v1 has no rewards; this memo designs v2, and `growth-pm` defines "activated".
*E2 (head-product):* Sleeper's 2026-10-06 Terms (§11.1, §11.3) bar commercial use and automated access without written
consent, superseding the July "no ToS restricting commercial use" (`…-research-appendix.md:57`); hence Gate 0.

## 2. Evidence: facts vs assumptions

| Claim | Label | Source |
|---|---|---|
| No route is gated; `check_pro` is called only by the unused decorator | M | `server.py:30965-30977`; `entitlements.py:251-265` |
| **The grid sells three features that don't exist** (no engine-knob UI; no extension `pro` field despite the server comment; no ad code) **and mislabels Portfolio** as "your roster value over time" when it is cross-league player exposure | M | Grid `server.py:31003-31005`; copy `PaywallScreen.tsx:82-87`; `PortfolioScreen.tsx:24-27`; `iap-enablement/scope.md:35-36`; handler `server.py:25792+` vs `:30984-30986`; `features.json:147-148` |
| Every `monetize.*` flag is false; `monetize.pro`, `season_pass` and `founder` are never read | M | `features.json:141-148`; `feature_flags.py:260-290` |
| Entitlements + paywall flags both on = **enforcing**; `/api/me/entitlements` reports `enforcing` from one flag | M | `entitlements.py:257-265`; `server.py:30989` |
| The RevenueCat webhook has no sandbox/production check | M | `server.py:31149-31179` |
| `NON_RENEWING_PURCHASE` is an activating event; expiry is read only from `expiration_at_ms`, so if it's absent the grant is perpetual | M | `entitlements.py:342-343, 535, 556-557` |
| `entitlement_granted` is fired but not registered in the taxonomy | M | `entitlements.py:302`; repo-facts §6 |
| Users: 16 (08-05/08-09); 3–5 (08-12 to 08-14); ~10 testers (~08-20); 6 users sent 92 proposals (08-21 to 08-29) | M | repo-facts §8 table |
| **Leagues per account** | P analytics-lead | "16 users, 7 leagues" (`2026-08-09-mobile-ux-audit/05-appendix.md:47`) says nothing per account |
| DB: 1,051,078,660 B of 5,246,714,000 B used (20.03%) on 2026-09-15, after compaction; "close to full" on 2026-10-15; operator rules out more disk. Storage per user, infra cost and cost per user are **[P]** | M | `db-storage-reduction/release.md:50-51`; draft PR #337 `requirements.md` §1, C-1; pending analytics-lead (W3), head-bizops |
| Apple: SBP 15%; Season Pass must be non-renewing; no TestFlight sale; no "30-day" trial | B | Apple pages in the platform research, accessed 2026-10-15 |
| Monthly median $8 (North America $9.99); annual median $34.80 (NA $39.99) | B | RevenueCat SOSA 2026, https://www.revenuecat.com/state-of-subscription-apps (blog 2026-03-19, updated 2026-09-11) |
| Trial→paid: monthly 10–16 days 46.6%; annual 17–32 days 44.6% | B | https://www.revenuecat.com/blog/growth/free-trial-length (2026-09-28) |
| Lifetime "often priced at 5–12x the annual"; lifetime-dominant apps have the lowest revenue per install | B | https://www.revenuecat.com/blog/growth/lifetime-subscriptions (2025-11-12); SOSA 2026 |
| Multi-league share, gate-hit demand, willingness to pay, paywall conversion | A | Nothing is measured; every conversion figure below is benchmarked or assumed |

### 2.1 Competitor price map (interim: July/September sources, refresh pending)

**Interim:** the `pm-competitor` refresh (`competitor-pricing.md`) didn't exist when this was written. Re-verify every row
before ASC prices are set.

| Product | Price | Model | Source (date) |
|---|---|---|---|
| Dynasty Nerds Premium | $6.99/mo · $69.99/yr. Free tier: preview ranks, **1 league sync**, 3 trades/day. Claims 11,000+ premium members | Freemium sub | `connected-rankings/research/2026-08-15-dynasty-nerds.md:71-73` (2026-08-15); July appendix :29 |
| FantasyPros PRO → HOF | $5.99/mo · $47.88/yr → $107.88/yr | Tiered sub | July appendix :29 (2026-07-17) |
| PFF+ · RotoWire · Footballguys Elite | $24.99/mo or $119.99/yr · $17.99/mo · $89.99/yr | Content bundles | July appendix :29 |
| Dynasty Daddy | Free, plus Patreon $6/mo (ad-free, league-infused values) | Hybrid | July appendix :29, :44 |
| KeepTradeCut · FantasyCalc | Free; Raptive ads, a donation link | Ads | July appendix :29, :44 |
| Dynasty Trade Lab | Credits: 10 for $4.99 · 40 for $17.99 · 75 for $29.99; 5 free | Credits | `origin/docs/dtl-teardown:…/competitor-matrix.md` (2026-10-09, draft PR #316) |
| Season-style products | UDK $34.99 / UDK+ $59.99 · ETR Draft Kit $49.99→$54.99 · DN Rookie Guide $19.99 · PlayerProfiler $45/season/module | One-time per season | July appendix :36, :100 |

**What it supports:** a barbell of free tools and $70–120/yr bundles, with $30–50/yr still empty. A 1-league free tier
has a direct precedent (Dynasty Nerds), and $6.99/mo matches the closest league-sync competitor.

## 3. Free vs paid

### 3.1 Options considered

**A. Pro sells what exists (recommended):** unlimited synced leagues plus Portfolio, everything else free. It's the only
option where the paywall is true on day one. It never touches a single-league user's loop, has a direct precedent in
Dynasty Nerds' free tier, and gives Founder something real to grant. Weakness: both features need 2+ leagues (§10).

**B. No Pro until a new pillar; launch Founder + tips. Killed as default.** With nothing gated, Founder sells a badge
plus a promise. Selling future pillars invites 5.6 ("charge for features … not delivered") and 3.1.2(c) trouble, and
patronage converts poorly (Overcast 1.9% [B, July appendix :10]). Its pillar-first instinct survives in the §10 branch.

**C. Gate depth tools. Killed.** Never tolled forbids most of it: Win Now evaluations persist, overhaul **sends**
trades, Team Review writes the `league_preferences` that reshape the deck, shop-a-player feeds trade ideas. Overhaul and
shop-a-player also sit next to the core loop (PFO), removing shipped free features breaks 3.1.2(a)'s spirit ("should
not take away the primary functionality…"), and no gate-hit or retention data justifies it. Revisit only read-only tools.

### 3.2 Recommended packaging

| Tier | What | Notes |
|---|---|---|
| **Free forever** | Sign-in; syncing **one league per season** on any platform, swappable with a confirm; every ranking flow (trios, tiers / Quick Set, grading); values and tiers; the deck and Find-a-Trade; matches; calculator; sends (Sleeper / ESPN / MFL); Calibration; every tab | The never-gated list plus the data-generating rule. Calibration open to all since 2026-10-05 (`CalibrationScreen.tsx:27-28`) |
| **Pro at launch** | Unlimited synced leagues (PRD R3, `pro-subscription/prd.md:91-96`); cross-league Portfolio | Portfolio is read-only aggregation; its pill appears only with 2+ leagues (`TradesScreen.tsx:457`) |
| **Free at launch, revisit with data** | Win Now, team overhaul, shop-a-player, Usage Trends, Trends, mock draft and draft room, Team Review, league summary and rankings, free agents | Revisit only with gate-hit and retention data, and only the read-only surfaces |
| **Joins Pro only once built** | Alerts pillar (G5); three-team trades (G4, `trade.three_team` off); extension Pro overlays (G6); engine-knob UI (G3) | The lane and fairness fine-tuning in TradeDnaSheet (`TradeDnaSheet.tsx:63-74`) **stays free**; ad-free only if ads ever ship |

**Launch grid:** `unlimited_leagues` and `portfolio` only. Rewrite the Portfolio line to match the screen, e.g. "See your
exposure to every player across all your leagues" (`marketing-lead` owns the words). Add each pillar as it ships.

### 3.3 The PFO case

The first league is untouched: sign-in, sync, rank and the first suggestion work exactly as today. The cap fires only on
a second distinct league in a season, after the first is in use, and league selection stays the existing picker. That
adds no step before the first suggestion, where `pm-pfo`'s default answer is no (`pm-pfo/SKILL.md:93-95`). There's no
onboarding-end paywall at launch (PRD R5 waits for retention data), and the 90-day comp protects current testers.

### 3.4 Two tensions the operator must see

1. **The cap vs never tolled.** I read the cap as honoring the rule: it limits *which* league a free user syncs, not any
   action, and the swap keeps every league reachable. A stricter reading ("syncing generates data") would forbid it and
   leave Pro as Portfolio alone. The source can't be quoted, so this is Decision 2.
2. **The cap vs the network effect.** Per-league density is the moat (`2026-08-09-mobile-ux-audit/00-master-report.md:51`),
   and unsynced leagues are leagues FTF never reaches through that user. Mitigations: referral months unlock extra
   leagues (§6.2), observe mode measures exposure first, and K3 (§8.2) reverts the cap if gate-hitters go dark.

## 4. Tiers & prices

### 4.1 Pro: final prices

| Option | Monthly | Annual | Annual saving vs 12× monthly | Annual per month | Against benchmarks [B, SOSA 2026] | Verdict |
|---|---|---|---|---|---|---|
| Keep | $4.99 | $34.99 | 42% | $2.92 | Monthly at the bottom of category medians ($4.99–9.99); typical annual discount ~64% | Weak annual pitch |
| **Recommended** | **$6.99** | **$34.99** | **58%** | **$2.92** | Monthly = Dynasty Nerds; annual = all-app median ($34.80), in the empty $30–50 band | **Adopt** |
| Higher annual | $6.99 | $39.99 | 52% | $3.33 | Annual = NA median; Founder drops to 2.98× | Later, when a pillar ships |

**Why $6.99 monthly:** monthly is the decoy, annual the pre-selected hero. Four in-season months cost $27.96 (vs $19.96
at $4.99), nudging seasonal buyers to the $34.99 annual; it also matches Dynasty Nerds.

**Why not $39.99 yet:** launch Pro is two multi-league features; the NA median risks trial→paid. $34.99→$39.99 later is
+14% (notice only), and Apple's "keep current price" option lets early subscribers keep theirs.

**Pushback on the lead's rationale:** Apple's consent threshold isn't why to set prices now. A later $4.99→$6.99 raise is
+40%, under the ">50% **and** >~$5" line, so notice only (platform research §6). The real reasons: no notice cost today;
every later raise emails every subscriber and starts a 12-month clock before a second needs consent; cuts always pass
through; and 5.6 bars raising prices "in a tricky manner".

**Server change:** `_PAYWALL_PRODUCTS` (`server.py:31009-31015`) gets `$6.99` as monthly fallback copy; StoreKit-localized
prices stay authoritative on iOS (`server.py:31044-31048`).

### 4.2 Net per SKU

SBP is 15% from the first sale once enrolled. RevenueCat is $0 below $2,500 monthly tracked revenue (MTR), then 1% of
gross [B, https://www.revenuecat.com/pricing/, 2026-10-15].

| SKU | Store type | Price | Net at 15% | Net at 30% (if SBP missed) | RevenueCat 1% (past $2.5k MTR) |
|---|---|---|---|---|---|
| `ftf_pro_monthly` | Auto-renewable | $6.99 | $5.94 | $4.89 | $0.07 |
| `ftf_pro_annual` | Auto-renewable | $34.99 | $29.74 | $24.49 | $0.35 |
| `ftf_founder` | Non-consumable | $119 | $101.15 | $83.30 | $1.19 |
| `ftf_season_pass_2027` (2027) | Non-renewing subscription | $24.99 / $22.99 | $21.24 / $19.54 | $17.49 / $16.09 | $0.25 / $0.23 |
| `ftf_tip_199/499/999` | Consumable | $1.99 / $4.99 / $9.99 | $1.69 / $4.24 / $8.49 | $1.39 / $3.49 / $6.99 | — |

Apple remits US sales tax on IAP, so net is 85% of list. Reaching $2.5k MTR takes ~71 annual sales in one month (computed).

### 4.3 Season Pass: defer to the 2027 season

**Why defer:** a 2026 pass bought at a mid-season launch covers ~4 months. It needs a new product type, the rework
below, and a new app version (Apple's rule for the first non-renewing IAP). Annual, with its 1-month trial, covers launch.

**Shape:** `ftf_season_pass_2027`, a **non-renewing subscription** with a new id; never a non-consumable season SKU, as
product type can't change later. On sale 2027-07-01 to 2027-11-30 ($22.99 through Jul 31, $24.99 after); access from
purchase to **2028-02-15**, after the fantasy playoffs, with that date on the purchase sheet (5.6).

**The rule: the pass never beats annual per covered month ($34.99 / 12 = $2.92).**

| Bought | Price | Months to 2028-02-15 | $ per covered month | Pass vs annual |
|---|---|---|---|---|
| Jun 1 (the lead's early-bird) | $19.99 | 8.5 | $2.35 | **Beats annual: fails** |
| Jul 1 | $19.99 | 7.5 | $2.67 | **Fails** |
| Jul 1 | **$22.99** | 7.5 | $3.07 | Holds |
| Aug 1 | **$24.99** | 6.5 | $3.84 | Holds |
| Nov 30 (last sale day) | $24.99 | 2.5 | $10.00 | Holds; stop selling here |

An annual raise before June 2027 raises the floor, so recompute then. The pass is for people who refuse auto-renewal,
but an annual buyer can turn auto-renew off on day one and keep 12 months for $34.99, so the pass must win on price.
Revisit with 2026–27 cancel timing (month 1 holds 23–50% of annual cancels [B, SOSA 2026]). **Rookie Pass:** defer; the
draft room and mock draft are free, so revisit after the Apr–May 2027 rookie window with gate-hit data.

**Eng rework (`head-eng`, before any pass exists in ASC).** **(a)** Stop the perpetual grant: `ftf_season_pass*` maps
to `season_pass_iap` (`entitlements.py:378-380`) and expiry comes only from `expiration_at_ms` (`:535`), so a
`NON_RENEWING_PURCHASE` lands perpetual (`:556-557`); compute expiry from the SKU. **(b)** Keep the pass off RevenueCat's
`pro` entitlement, which would unlock "forever" [B]. **(c)** Restore and cross-device delivery via the `acct_` account,
which FTF owns for non-renewing products. **(d)** An overlap prompt over an active auto-renewal (StoreKit won't block it).

### 4.4 Founder

**The offer:** `ftf_founder`, a **$119** non-consumable. The window opens with the **App Store build**; it is never sold
or linked from TestFlight (DPLA §7.4), and closes at the cap or the operator's date.

**Mechanics.** A **cap of 100 on the server** counts **production** `founder_iap` rows only, hides the SKU at the cap,
accepts a small boundary oversell (`founder-lifetime/prd.md:106-107`), and reopens a slot on refund while the window is
open. **Family Sharing off** (irreversible; one unit could entitle 6 Apple IDs). An **overlap prompt** over an active
auto-renewal explains first, then links to Manage Subscriptions and the refund path.

**Price evidence:** $119 is 3.40× annual and 17× monthly. RevenueCat's "often 5–12x" means $175–420 [B], but it also
advises pricing "just above expected LTV" (July appendix :10). From SOSA 2026's renewal ranges (23–40%, 44–64%, 56–70%,
with the third rate held steady after), an annual subscriber pays for **1.5–2.3 years**, an expected LTV of $51–79 gross.
**$119 is 1.5–2.3× that.** A 5-year loyalist pays $175, so $119 is ~$56 short, a worst case of ~$5.6k gross under the cap.

**Recommend $119 over $149 (4.3×):** with a tiny list and a one-shot window, a visible sell-out beats the margin. Lead
with value, define "lifetime" in the Terms of Use as the product's lifetime, never sell an unbuilt pillar (5.6).

**Storage liability:** founders never churn on price and keep generating decks, ≈ 8.2 MB per generation run (~9 KB × ~910
rows, computed from draft PR #337 §3.1), on a disk the operator won't grow. The cap bounds it; the cost is pending (§7).

**Testers:** a 90-day Pro comp bulk-granted **before** enforcement (`00-platform-foundation.md:173`; Pro PRD Q4), plus the
Founder offer; comps don't use cap slots (Founder PRD D4).

**Sell-through, honestly:** ~10–16 testers [M] at the warm-list norm of ~5% (≈50 lifetime deals per ~1,000-person list
[B, July appendix :15]) is roughly **one sale**. Launch traffic is unknown [A]. Plan for single digits in month one; the
PRD's "viable" 25 (`founder-lifetime/prd.md:177`) is a stretch.

### 4.5 Tips, ads, affiliate

**Tips:** keep as built: `ftf_tip_199/499/999` consumables that grant nothing (`entitlements.py:363-371`), riding
`monetize.paywall` and shipping with it. Keep them on IAP: Stripe's 30¢ is 18% of $1.99 [B, platform research §7].

**Ads and affiliate: not now.** There's no DAU to sell (3–16 users [M]). They're the plainest "commercial use" of
Sleeper-derived surfaces (Gate 0). They'd undercut "your board, not a consensus" (`open-access-onboarding.md:196-205`).
And the July math is small: $150–700/mo at 1,000 DAU [B].

**Reopen trigger, all of:** Sleeper coverage confirmed in writing; **≥500 DAU sustained for 4 weeks** (July's mobile-ads
gate); WAT and W1 retention stable for 8 weeks post-paywall. Affiliate also needs a signed DFS partner and FTC copy, web first.

## 5. App Store / StoreKit implications & fees (hard constraints)

| Constraint | What FTF does | Source [B unless noted] |
|---|---|---|
| **SBP: 15% from the first billing cycle** for developers under $1M; you have to enroll | Operator enrolls **before the first sale** | developer.apple.com/app-store/small-business-program/ |
| **Product types:** subscriptions auto-renewable in one group; Founder non-consumable; Season Pass **non-renewing**; tips consumable | Pass: no trial or intro offer; FTF owns expiry, restore and cross-device delivery | DPLA Att. 2 §2.3; guideline 3.2.1(iii) |
| **One intro offer per person per subscription group;** same-level monthly↔annual switches take effect at next renewal | A monthly triallist can't trial annual later, so the paywall pre-selects annual (RevenueCat's data favours it). Same level: it's the same service | Apple intro-offer help; subscriptions page |
| **Trial durations:** "2 weeks" exists; **"30 days" doesn't** | Configure annual as **"1 month"**; copy says "1 month free", never "30 days". `trial_days: 30` (`server.py:31014`) must render that way | Same page |
| **Multiseat (Group Purchases) on by default** for subscriptions since 2026-09-16; **Family Sharing** can't be turned off once on | Multiseat **off** for `ftf_pro_*` until seats are designed; Family Sharing **off** on every SKU | developer.apple.com/news/?id=likeohx4; Apple Family Sharing help |
| **Disclosure and accuracy:** 3.1.2(c) plus Schedule 2 §3.8(b); 2.3 / 5.6 | Billed amount most prominent; trial length and post-trial price; Restore; Terms + Privacy links; grid lists delivered features only (§3.2). `web/privacy.html` still says "no in-app purchases"; fix in the same release (Pro PRD §6 step 6) | Guidelines, updated 2026-06-08 |
| **TestFlight:** purchases "must be for no charge … beta testing purposes only", including immediate link-outs | No Founder sale or link from TestFlight. Rewrite Founder PRD FR3's Stripe rail (`founder-lifetime/prd.md:116-120`) | DPLA §7.4 |
| **Price changes:** consent needed if >50% **and** >~$5 (non-annual) or >$50 (annual), or if raised in the past 12 months; otherwise notice. Decreases always pass through | "Keep current price" when a pillar justifies a raise | Apple pricing help |
| **Review Notes:** describe new features specifically | Explain the league cap and referral rewards plainly | Guideline 2.3.1(a) |
| **US web checkout:** link-out from the App Store build is legal at 0% Apple fee today; fees on remand, SCOTUS ~mid-2027 | **IAP-only at launch** (Pro PRD Q6). Stripe later, kill-switched, never priced as if 0% lasts | Platform research §2 |
| **Double pay:** Apple won't cancel a subscription when a lifetime is bought | Check `CustomerInfo`, explain, link to `showManageSubscriptions`, then `beginRefundRequest` | RevenueCat lifetime guide, 2025-11-12 |

## 6. Trials, intro offers & referral rewards

### 6.1 Trials (ruled; implications only)

Monthly is "2 weeks" and annual "1 month". Benchmarks back both: 10–16-day monthly trials convert at 46.6%, 17–32-day
annual at 44.6% with a 47.5% first renewal [B, 2026-09-28]. Two gaps: PRD R18's timeline says "Day 14 — you're charged"
and R19's `trial_ending` push is unbuilt (repo-facts §1); both need the real "1 month" charge date, and a trial without
the promised push blocks launch (`pro-subscription/prd.md:134-141`). The sandbox checklist still says annual is "14 days
free" (`sandbox-test-checklist.md:100`).

### 6.2 Referral v2 reward economics (v1 has no rewards, per P20)

**Reward: one free Pro month per activated leaguemate, both sides.** `growth-pm` defines "activated" (July: verified
co-member plus ≥25 ranking matchups). Open access counts grading as ranking, so pin it to an existing event such as
`ranking_complete_first_time` ("board usable"). An invitee is rewarded once, ever.

**Cap: 2 rewarded months per referrer per season** (July 4–6; foundation ≤4). In-season engagement runs ~5.5 months,
Sept to Feb 15 [A]; keeping rewards plus the 1-month trial at or under half of that allows ~1.75 months, so **2**. A cap
of 4 plus the trial is 5 free months, the whole season with no paid decision, given to the likeliest payers. Past the
cap, activations earn recognition on the signal-quality invite CTA (Pro PRD R13): free, and true to the product.

**Milestone (8+ activated → free Season Pass): drop it from v2.** There's no pass until 2027, eight activated members in
one league has never been seen (16 users across 7 leagues [M]), and it breaks the cap by design. Revisit it, and the
group unlock, when any league reaches 5 activated members [A].

**Grant mechanism by user state:**

| User state | Mechanism | Why |
|---|---|---|
| Free or never paid; lapsed | Server `promo_referral` row, 30 days (`entitlements.grant`; valid source `entitlements.py:49-51`) | Never converts to a charge; no StoreKit, so **Apple intro eligibility is untouched** |
| In an Apple intro trial | **Bank** the reward. Converted → promotional offer; cancelled → server grant from trial expiry | A grant during the trial overlaps it and doesn't stop the charge |
| Active Apple subscriber | **Apple promotional offer**, 1 free month: a server signature per redemption, ≤10 active offers per subscription, Apple's sheet. **Sandbox-test whether it starts now or at renewal.** Fallback: non-time reward | A server grant gives a payer nothing, since billing continues. Offer codes are once per customer; renewal extensions are 2 a year and framed for outages |
| Founder | Non-time reward | Already lifetime |
| Season Pass holder (2027) | Extend the FTF-computed expiry by 30 days | FTF owns the pass's expiry |
| Comped tester | Server grant, stacked after the comp expires | Foundation §5: extend from the furthest `expires_at` |

**Stacking:** a promo month then a trial is fine, since the promo leaves intro eligibility alone. While a promo row is
active, suppress contextual paywall prompts (keep the Settings row), with one in-app note, not a push, 3 days before expiry.

**Compliance:** reward in-app actions, never installs, sign-ups, ratings or reviews (3.2.2(x)); rewards are additive,
never needed to get what was paid for (3.1.2(a)); no referral manipulation (5.6.3), bulk contact select (5.1.2(v)) or
typed unlock code (3.1.1); describe it in Review Notes (2.3.1(a)). **Fraud:** only verified co-members of a league the
referrer synced count, one reward per Sleeper user ever. `referrals` has `UNIQUE(referrer, referred)` (`database.py:2598-2618`)
but no writer; v2 adds per-referred-user uniqueness.

**Reward cost = forgone revenue + infra per user-month.** Forgone revenue is ≈0 for a free user (unless they'd have paid
that month) and at most one month's net for a payer ($5.94 monthly, $2.48 annual-equivalent): **worst case $11.88 per
referrer per season.** Infra is **pending fin-pnl / head-bizops**; the storage share is pending analytics-lead.

## 7. Unit economics

| Cost line | Status | Monthly |
|---|---|---|
| Apple Developer Program | $99/yr [M, `docs/business/context.md:81`] | $8.25 |
| Render web service | `render.yaml:14` says `plan: free`; the dashboard is **unverified**. Starter ~$7/mo is assumed (`2026-07-17-render-paid-tier-memo.md:15`) | $0, or ~$7 [A] |
| Render Postgres `basic-256mb` | `render.yaml:6`; price not recorded in the repo | **[P head-bizops]** |
| Postgres disk, 5 GB | $0.30/GB-month (`db-storage-reduction/status.md:5-6`) | $1.50 (computed) |
| Three Render crons | Billable (`GOTCHAS.md` G-018); plan unrecorded | **[P]** |
| EAS builds | Plan unrecorded | **[P]** |
| Anthropic API (matchup selection; `claude-sonnet-4-6` when the key is set) | No spend recorded (`smart_matchup_generator.py:23, 59`) | **[P]** |
| Domain(s) | Unrecorded | **[P]** |
| RevenueCat | $0 under $2.5k MTR | $0 |
| **Ceiling** | Hard $200/month operating budget (`budget-scalability/scope.md:4`, 2026-09-04) | — |

**Break-even** (computed, at $2.48 net per annual user-month and $5.94 monthly): **every $10/month of cost needs 4.0
annual or 1.7 monthly subscribers.** The known $9.75 floor (Apple plus disk) breaks even at **4 annual**, the $200 ceiling
at **81 annual or 34 monthly**. The real number waits on head-bizops' monthly total.

**Storage is a capacity limit, not a dollar cost.** The operator ruled out more disk (C-1), so a user's real cost is a
share of a fixed 5 GB. Measured: 539 MB of database on 1.05 GB of volume after compaction (2026-09-15), "close to full"
by 2026-10-15; `deck_impressions` ≈ 8.2 MB per run (computed, draft PR #337 §3.1). League history alone reaches ~470 MB
at 1,000 leagues (`adr-011-…:114-115`). Storage per active user waits on analytics-lead's W3 inventory (§3.4 there).

**Lifetime liability = founders × (storage and $ per user-month) × active months;** the cap bounds the first term. Over 5
years a founder stays net-positive while all-in cost is under $101.15 ÷ 60 = $1.69/month [computed; cost pending].

## 8. Activation sequence

### 8.1 Ordered gates (every flag stays false until its step)

| # | Gate | Owner | Flag / state | Exit criterion |
|---|---|---|---|---|
| 0 | **Sleeper commercial coverage:** written consent for commercial use and automated access under Terms §11.1/§11.3 (2026-10-06) | Operator (`platforms-pm` drafts the ask; also checks ESPN/MFL terms) | None; blocks gates 6–10 | Operator confirms coverage in writing |
| 1 | **Apple setup:** Paid Apps agreement; **SBP enrollment before the first sale**; ASC products `ftf_pro_monthly` $6.99 ("2 weeks"), `ftf_pro_annual` $34.99 ("1 month"), one group, same level; tips; `ftf_founder` | Operator (`release-lead` keeps the checklist) | ASC only | Products "Ready to Submit" |
| 2 | **Multiseat off** on both subscriptions; **Family Sharing off** on every SKU | Operator | ASC only | Verified in ASC |
| 3 | **RevenueCat:** project, `pro` entitlement, Offering marked Current. Key names only: `EXPO_PUBLIC_REVENUECAT_IOS_KEY` (EAS env, baked in at build time); `REVENUECAT_WEBHOOK_SECRET` (Render env **and** `secrets.local.env`) | Operator | Webhook 503s until the secret is set (`server.py:31162-31163`) | Wrong bearer → 401, right → 200 |
| 4 | **Design review of placement:** Settings row; 402 touchpoints on second-league sync and Portfolio; **no** paywall before the first suggestion; the onboarding-end soft paywall waits for retention data | `ux-lead` and `design-lead`, before step 5's build | None | Signed-off spec |
| 5 | **Eng fixes** (below) | `head-eng` | Dark | CI green; TEST_LEDGER evidence |
| 6 | **Analytics:** register `entitlement_granted`; add `paywall_dismissed`, `trial_started`, `pro_gate_hit`, `subscription_cancelled`, `referral_*`, each registered in `analytics_taxonomy.py` and classified in `NON_INTENT_EVENTS` **in the same commit as its emitter**; confirm funnel coverage | `analytics-lead` | `analytics.*` already on | Events visible in reports |
| 7 | **Observe mode:** `monetize.entitlements` on **alone**, after fix 5a | Operator flips; `analytics-lead` reads | `monetize.entitlements` | ≥2 weeks of `would_block` counts per gate (§9) |
| 8 | **Operator sandbox checklist** in TestFlight, updated for $6.99, Founder, the cap, and sandbox events not granting in prod | Operator (`release-lead` updates it) | Sandbox | Every row passes; logged in TEST_LEDGER |
| 9 | **Public launch:** tester comps bulk-granted **first**, then paywall + Pro + Founder window + tips. Onboarding-end soft paywall only after 8 weeks of retention data | Operator, `release-lead` | `monetize.paywall`, `monetize.pro`, `monetize.founder` | §8.2 watch starts |
| 10 | **Season Pass 2027:** mint the non-renewing SKU with the May/June 2027 app version; on sale Jul 1 | `head-eng`, operator | `monetize.season_pass` | Sold Jul 1 to Nov 30 |

The placement review (step 4) moves ahead of the build: the lead's list had it seventh, but the 402 touchpoints ship with the cap.

**Step 5 eng fixes (`head-eng`):**
- **(a) Decouple enforcement.** `monetize.pro` is never read, so turning on `monetize.paywall` with entitlements on
  enforces every gate (`entitlements.py:257-265`). Enforce only with `monetize.entitlements` **and** `monetize.pro`;
  `monetize.paywall` gates purchase UI only.
- **(b)** `enforcing` on `/api/me/entitlements` uses one flag (`server.py:30989`), misreporting observe mode; use (a)'s
  predicate. **(c)** Truthful grid: `_PAYWALL_PAGES` = `unlimited_leagues` + `portfolio`, new Portfolio copy. **(d)** The
  Season Pass rework (§4.3 a–d). **(e)** Server Founder cap: read `monetize.founder`, count production rows only.
- **(f) Stop sandbox events granting in prod.** The webhook ignores RevenueCat's environment (`server.py:31149-31179`), so
  once `ftf_founder` is in ASC any TestFlight user can "buy" it free and get a perpetual grant, a badge and a cap slot.
  Ledger sandbox events but project them only for `FTF_TESTER_ALLOWLIST` (`render.yaml:33-34`), time-boxed, excluded
  from the cap and revenue. **Land before the Founder SKU is created.**
- **(g)** League-cap gate in observe mode: a second distinct current-season league at session init logs `would_block`,
  then returns 402 `league_limit` (PRD R3) once (a) enforces.

### 8.2 Guardrail kill criteria

Thresholds are **[A]** until `analytics-lead` replaces them with observe-mode baselines. Window: the 4 weeks before vs
the 4 weeks after `monetize.pro` enforcement.

| Criterion | Trigger | Action |
|---|---|---|
| **K1, WAT** | 4-week mean WAT (`analytics_queries.py:49-56`) after enforcement falls below **85%** of the mean before it, for **2 consecutive weeks** | `monetize.pro` off: gates stop; purchases and grants keep working |
| **K2, W1 retention** | Week-1 retention of the 4 signup cohorts after enforcement (`report_retention`, `:1307`) averages **≥10 points** below the 4 cohorts before | Same as K1 |
| **K3, gate churn (small n)** | Of users who hit `pro_gate_hit{league_limit}` and were WAT-active in the prior 14 days, **2 of the first 5, or ≥30% once there are 10+**, go WAT-dark for the 14 days after | Revert the cap only |

At n ≈ 16 these are directional, not significant: power needed ~174 per arm (`2026-08-09-mobile-ux-audit/06-resolutions.md:22`).
WAT also moves with the NFL calendar; compare against the comped tester cohort, which sees no gates for 90 days.

## 9. What would change the price

| Evidence | Threshold → direction (every threshold **[A]**; read only past its minimum sample) |
|---|---|
| Leagues per account (analytics-lead) | ≥40% of active accounts with 2+ current-season leagues → hold, then take annual to $39.99 for new subscribers when a pillar ships. Under 20% → no raise; Founder deferral branch (§10) |
| Gate hits in observe mode | `would_block` users ≥20% of WAU → strong Pro value; hold. Under 5% → the cap barely binds; no raise; build a pillar |
| Paywall view → trial (≥100 views) | Under 4% (M&E download-to-trial median 4.0%, SOSA) → value or price mismatch; test $29.99 annual. Over 12% → headroom for $39.99 |
| Trial → paid (≥20 trials) | Under 25% → lower price or fix the value page. Over 50% (benchmark 44.6–46.6%) → room to raise |
| Founder sell-through | 100 sold within 14 days → underpriced; any future lifetime at ≥5× annual. Fewer than 10 in 60 days → expected at this scale; **don't cut** (it burns $119 buyers); close on the date |
| Refunds and churn | Refunds over 6.8% (2× the NA median of 3.4%) → mis-set expectations; fix copy before price. Monthly first renewal under 40% (benchmark 53–61%) → price–value gap; consider $5.99 |
| Competitor moves (refresh §2.1) | KTC or FantasyCalc adds a paid tier under $30/yr, or Dynasty Nerds cuts monthly to ≤$4.99 → revisit monthly. Nerds rising → headroom |
| Cost per user rising (head-bizops) | All-in cost per active user-month over 20% of net ARPPU → raise annual for new subscribers, and push head-eng on storage. **Never gate the core loop** |
| Van Westendorp survey of testers (operator sends; outbound) | Median "too expensive" under $34.99 → consider $29.99. Median "expensive but OK" over $49.99 → $39.99 is safe. n ≈ 10–16: directional only |

## 10. Riskiest assumption & cheapest test

**Riskiest assumption: a meaningful share of active users sync 2+ leagues in a season.** Both launch features depend on
it, and it's unmeasured ("16 users / 7 leagues" says nothing per account). **Cheapest test:** one read-only production
query by `analytics-lead` (once the prod-read grant is in force, per draft PR #337 §3.4): distinct current-season
leagues per active account, and the share of WAT users with 2+. No build; observe-mode `would_block` counts confirm it.
**Second-riskiest:** Sleeper coverage (Gate 0), tested by the operator's written ask.

| Multi-league share of active accounts | What launches |
|---|---|
| ≥40% | As recommended: Pro + Founder window + tips |
| 20–40% | As recommended; the alerts pillar becomes the next monetization build |
| **Under 20%** | **Pro + tips only.** Pro still ships (single-league users lose nothing; the minority can pay). **The Founder window waits for the first new pillar** (recommend alerts): it opens once, and opening it on a near-empty Pro wastes it on patronage |

## 11. Decisions needed

1. **Packaging:** Option A, Pro = unlimited synced leagues + Portfolio, everything else free (§3.2). *Recommend yes.*
2. **Never-tolled ruling:** the league cap limits scope, not a data-generating action (§3.4). *Recommend confirming.*
3. **Pro prices:** $6.99/mo (14 days), $34.99/yr ("1 month"). *Recommend yes; $39.99 once a pillar ships, keeping current prices.*
4. **Feature grid:** drop `engine_knobs`, `extension_overlays`, `ad_free`; rewrite the Portfolio line. *Recommend yes.*
5. **Season Pass:** defer to 2027, non-renewing, $24.99 ($22.99 July), ends 2028-02-15; defer the Rookie Pass. *Recommend yes.*
6. **Founder:** $119, cap 100 on the server, App Store launch only, Family Sharing off, comps outside the cap. *Recommend $119 (alt. $149).*
7. **Testers:** 90-day manual Pro comp before enforcement, plus the Founder offer. *Recommend yes.*
8. **Referral v2:** 1 month per activated leaguemate, both sides, cap 2/season, no milestone or group unlock, grants by state (§6.2). *Recommend yes.*
9. **Ads and affiliate:** no, until the §4.5 trigger. *Recommend yes.*
10. **Gate 0:** no paid launch until you confirm Sleeper commercial coverage in writing. *Recommend yes.*
11. **Kill criteria K1–K3** by default, replaced by measured baselines (§8.2). *Recommend yes.*
12. **Van Westendorp:** send the 4-question tester survey before step 9 (outbound, so you send it). *Recommend yes.*
13. **Founder branch:** pre-approve deferring the Founder window if multi-league is under 20% (§10). *Recommend yes.*

## 12. Handoffs

| Owner box | Deliverable |
|---|---|
| Operator | Decisions 1–13. Gate 0 (Sleeper). Gates 1–3: ASC, SBP, multiseat and Family Sharing off, RevenueCat keys by key name in `secrets.local.env` and Render. Flag flips at 7 and 9. Send the Van Westendorp survey |
| `head-eng` | The scope block (full feature gates) for eng fixes 5a–5g and the Season Pass rework (§4.3 a–d). The sandbox fix (5f) lands before the Founder SKU exists |
| `analytics-lead` | The multi-league query (§10); W3 storage per active user; event registrations (step 6); funnel-coverage confirmation; observe-mode `would_block` readout; baselines that replace K1–K3 |
| `growth-pm` | Define "activated"; the referral v2 build spec from §6.2 (reward writer, state branching, cap of 2, fraud rules); the promotional-offer sandbox test plan |
| `head-bizops` (fin-pnl) | Monthly infra total by line (the §7 pending rows; verify the Render web and DB plans in the dashboard); cost per active user-month; break-even and Founder-liability numbers |
| `ux-lead` + `design-lead` | Step 4 placement review: Settings row, 402 touchpoints, cap-swap confirm copy, Founder overlap prompt, the trial timeline for "1 month". Chalkline-compliant |
| `platforms-pm` | Draft the Sleeper written-consent ask (Terms §11.1/§11.3); check ESPN and MFL terms for the same exposure |
| `marketing-lead` | Grid and price copy ("save 58%", the Portfolio line); Founder launch-window copy with no future-pillar claims; the Van Westendorp survey text; the §2.1 competitor refresh, with `pm-competitor` |
| `release-lead` | ASC configuration checklist; Review Notes (cap, referral); sandbox checklist update (fix `:100`; add Founder, the cap, sandbox-not-granting); `web/privacy.html` IAP language in the same release as the paywall |
| `monetization-pm` (this box), after decisions | Stale-doc sweep: **`docs/plans/README.md` `monetization/` row** (:85 on `678834ab`; it says "No `monetize.*` flag exists … nothing was implemented", which is false); `monetization/README.md:6, 16, 35`; Pro PRD R4 (`:100-101`) and R18 "Day 14" (`:117-119`); Season Pass PRD non-consumable shape (`:32-33, 45-46, 75-79`); `season-pass/lld.md:103` ($79 Founder); Founder PRD FR3 TestFlight Stripe rail (`:116-120`); foundation doc `:23, :38-40`; `docs/business/context.md:20-27, 34` |
