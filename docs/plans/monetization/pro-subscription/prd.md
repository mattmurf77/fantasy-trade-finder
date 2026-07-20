# FTF Pro — freemium subscription — PRD

Owner: pm-monetization. Date: 2026-07-17. Status: DRAFT (pending operator decisions §10).
Builds on: [../00-platform-foundation.md](../00-platform-foundation.md) (entitlements, IAP,
flags, manual grants, growth-loop infra — referenced throughout, never re-specified).
Source plan: [Plan A](../../../business/product/2026-07-17-monetization-brainstorm-and-plans.md);
benchmarks: [research appendix](../../../business/product/2026-07-17-monetization-research-appendix.md).

## 1. Problem / opportunity

FTF is pre-revenue at TestFlight v1.7.3 with peak season (Jul–Aug draft ramp) starting now.
The dynasty tools market is a barbell — free crowdsourced tools (KTC, FantasyCalc, Dynasty
Daddy) vs $70–120/yr content bundles (Dynasty Nerds $6.99/mo–$69.99/yr is the closest comp)
— leaving the **$30–50/yr band empty**. Benchmarks that shape this plan (appendix,
subscription brief):

- Freemium download→paid is ~2.1% at D35 (vs 10.7% hard paywall) — but hard paywalls are
  incompatible with FTF's league-network growth loop, so freemium + strong trial mechanics
  is the play.
- 17–32-day trials convert 42.5–45.7% vs 25.5% for <4-day; trial→paid global median 25.6%.
- Day 0 = ~90% of trial starts and 44.5% of purchases → the paywall must sit in onboarding.
- Multi-page onboarding paywalls convert +37% vs single-page (12.41% vs 9.07%, Superwall
  40M-open study).
- Annual first renewal is only 35–37% (M&E/Utilities); 72% of annual subs cancel auto-renew
  in year 1 → cancel-flow win-back (offer within 10–15 min of cancel intent) is in scope v1.
- Apple Small Business Program nets 85%; US external-checkout link currently 0% Apple fee
  (SCOTUS ruling ~mid-2027 — don't hard-depend; entitlements are payment-agnostic per
  foundation §2).

Assumed revenue math (not measured): 1,000 launch-season actives × 2–3% paid ≈ 20–30 subs,
~80% annual → ≈ $700–1,000/yr net year 1, compounding with scale.

## 2. Goals / non-goals

**Goals**

1. Ship a purchasable Pro subscription (mobile IAP + web Stripe) on the foundation
   entitlement service, dark-launched and flag-flippable.
2. Convert at the moment of maximum demonstrated value: soft multi-page paywall at end of
   onboarding, after showing 2–3 real mutual-gain trades.
3. Preserve the hard guardrail: **the core loop (rank → see trades in one synced league) is
   never gated** — free users get the full product truth in their league.
4. Launch the give-get referral program (foundation §5) as Pro's acquisition engine.
5. Instrument every funnel step via `record_event` so conversion stops being assumed.

**Non-goals**

- Season Pass / Founder SKUs (separate plans; they share this paywall surface later).
- Alerts pillar build (Pro pillar, post-launch — reserved in the gate list, not built here).
- Ads / ad-free enforcement (Plan E; "ad-free" is a listed Pro perk that activates when ads
  ship).
- Elite/Concierge tier, League Pass, price experiments (backlog).
- Client-side analytics SDK selection (an-data-architect owns; this PRD names the events).

## 3. Users / stories

| Actor | Story |
|---|---|
| Free user | I sync my one league, rank my players, and see mutual-gain trades — complete and un-nagged except a dismissible paywall at onboarding end and at Pro-feature touchpoints. |
| Trialer | I start a 14-day trial on the annual SKU at Day 0, keep full Pro during it, get a clear expiry date, and am never silently converted from a promo grant. |
| Paying user | I subscribe once (Apple or Stripe) and Pro works on iOS, web, and the extension; restore purchases works; canceling shows me a save offer, then works without dark patterns. |
| Referred leaguemate | I tap a share-card link from a leaguemate, land in FTF with my league pre-linked context, and when I've joined the league in FTF and completed ≥25 matchups, both of us get a free Pro month. |
| Operator | I can comp Pro to any tester via the foundation manual-grant routes, watch observe-mode logs before enforcement, and kill any surface with one flag. |

## 4. Functional requirements

### 4.1 Packaging + gate list (exact)

Free tier — everything shipped today EXCEPT the Pro column. Never gated, ever (guardrail):
ranking flows (all five), tiers/values (raw), trades + matches + calculator, league summary,
free agents, trends, feedback — all within the user's **1 synced league**.

| # | Capability | Free | Pro |
|---|---|---|---|
| G1 | Synced leagues | 1 (see §4.2) | Unlimited |
| G2 | Cross-league Portfolio (`/api/portfolio`, PortfolioScreen) | — | ✓ |
| G3 | Engine power knobs: opening-offer aggression, lane filter (window/value moves), fuzzy-match tolerance, crown-asset premium override | Engine defaults (current behavior) | User-tunable |
| G4 | Three-team trades (`trade.three_team`, future client surface) | — | ✓ (reserved; gate registered now) |
| G5 | Alerts pillar (post-launch) | — | ✓ (reserved) |
| G6 | Extension Pro overlays (values/tiers overlay beyond basic rankings) | Basic overlay | Full overlays |
| G7 | Ads (when Plan E ships) | Ads | Ad-free |

R1. Gates are enforced server-side via the foundation `require_pro` decorator / 402
`pro_required` (foundation §2.2); clients render upsell states from
`GET /api/me/entitlements`, never decide entitlement locally.
R2. The gate list is final only after observe-mode data (§8 step 3) — G3 knob demand is the
riskiest assumption (un-instrumented today).

### 4.2 League cap (G1)

R3. Free = 1 distinct synced league per season (Sleeper mints new league_ids each season;
counting lifetime would strand returning users). Syncing a 2nd distinct current-season
league without Pro → 402 `league_limit` + paywall entry point. Switching *which* league is
the synced one is allowed with a confirm ("replaces your synced league") — free users are
never locked out of their data, but flip-flopping is deliberately manual. [ASSUMPTION —
operator decision Q1.]

### 4.3 Pricing + SKUs

R4. `ftf_pro_monthly` $4.99/mo, **no trial** (decoy anchor). `ftf_pro_annual` $34.99/yr,
**14-day free trial** (hero, pre-selected). One subscription group (foundation §4). Web:
Stripe equivalents keyed to account email. Prices live in `GET /api/paywall/config`, not in
clients.

### 4.4 Paywall

R5. Soft, multi-page, server-driven (`GET /api/paywall/config`), placed at end of
onboarding **after** the aha: Sleeper login → league sync → show 2–3 real mutual-gain
trades → paywall for the rest of Pro. Dismissible on every page; dismissal lands in the
normal free app.
R6. Additional entry points ("touchpoints"): 402 responses (league cap, Portfolio, knobs),
Settings "FTF Pro" row. Same PaywallScreen, `source` prop recorded.
R7. Chalkline: ink surfaces, ice CTAs only, no gradients/emoji-icons; hero SKU pre-selected
with an ice tick; flare only for informational highlights (e.g. "most popular" tag is a
flare-bordered chip, never the buy button).
R8. Restore purchases affordance on the paywall (guideline 3.1.1).
R18. **Trial-timeline visualization** (teardown 2026-07, S9 PRD-03): the paywall page for
the annual/hero SKU renders a three-step timeline — **"Today — full access → Day 12 — we
remind you → Day 14 — you're charged"** — with the real charge date computed client-side.
This is the single most-proven honest-conversion pattern (Blinkist: +23% trial starts,
−55% billing complaints) and matches the brand's honesty posture exactly. Chalkline: ice
step markers, no gradients; the timeline is informational, never the buy button.

### 4.5 Trial + cancel flow

R9. Trial only on annual, Apple/Stripe-managed (no server-minted trials; foundation
`source='trial'` rows come from webhook events only). Trial state shown in Settings with
expiry date.
R10. Cancel flow (in-app "Manage subscription" → before deep-linking to store management):
one-screen exit survey + **one** win-back offer (annual discount or pause-equivalent promo
grant) shown within the same session as cancel intent. No confirm-shaming; the store link
is always visible. [Offer mechanics via store promotional offer — assumption: RevenueCat
promotional offer support; fallback = skip offer v1.]
R19. **Committed day-12 pre-charge push** (the reminder R18's timeline promises): a new
typed push kind **`trial_ending`** through the existing dispatcher (`server.py` push
stack), fired by the daily cron from webhook-projected trial state on trial day 12.
Dedup-capped once per trial (`_NOTIF_DEDUP_CAPS`, dedup_key = the trial's original
transaction/entitlement id); body states the charge date and billed amount; tap
deep-links to the in-app subscription management surface. Transactional bucket — not
gated on the `reengagement` pref, but respects quiet hours. Shipping the trial without
this push is a launch blocker: the timeline page (R18) commits to it in user-facing copy.
R20. **Billing grace period + soft failure state** (involuntary churn is ~14% of App
Store cancels): enable App Store Billing Grace Period in ASC and Stripe smart retries;
the webhook projector treats grace/retry states as **still entitled** (entitlement row
stays active through the grace window). In-app, a soft dismissible banner — "We couldn't
renew your subscription — you keep access while we retry. Update payment?" — links to
Manage Subscriptions / the Stripe portal. Never a hard mid-retry lockout, never a modal.

### 4.6 Growth-loop program rules (Pro give-get)

Infrastructure per foundation §5; the **program rules** for Pro:

R11. Reward: 1 free Pro month per **activated** leaguemate — referred user is a verified
co-member of the referrer's Sleeper league AND has completed ≥25 ranking matchups. Both
sides rewarded. Never on install/signup (Apple 3.2.2(x)).
R12. Caps: ≤4 rewarded referrals per referrer per season; one reward per unique referred
user ever (schema-enforced, foundation).
R13. Invite framing is signal-quality first: "3 of 12 leaguemates ranked — trade confidence
LOW" on Trades/Matches surfaces; the give-get is the kicker line. Behind `growth.referral`.
R14. Share card: Chalkline-styled trade/board card embedding the invite deep link, surfaced
at value peaks (trade found, ranking finished). Ships before/with the referral program.
R15. Group unlock behind `growth.group_unlock`: ≥8 league members activated → 14-day
`promo_group_unlock` Pro for the whole league, once per league per season; A/B vs
per-referrer rewards.
R16. Grants are server-side promo entitlements (30-day rows) for free users; paid subs get
RevenueCat promotional-entitlement extension (foundation §5). Promo never converts to a
charge.

### 4.7 Operator

R17. Foundation §3 manual grants usable to comp Pro (single + bulk) before any flag flips;
grants sit dormant until `monetize.entitlements` enforces.

## 5. Success metrics + instrumentation

All via `record_event` (existing `user_events`; client-event transport is the
an-data-architect spec — blocking prerequisite for the client-side rows). Exact
`event_type` strings:

| Event | Props | Fired by |
|---|---|---|
| `paywall_viewed` | `{source, page}` | client |
| `paywall_advanced` | `{page}` | client |
| `paywall_dismissed` | `{page, source}` | client |
| `paywall_purchase_tapped` | `{product_id}` | client |
| `trial_started` | `{product_id, source}` | server (webhook projector) |
| `purchase_completed` | `{product_id, source}` | server (webhook projector) |
| `subscription_cancelled` | `{product_id, reason?}` | server (webhook projector) |
| `cancel_intent` | `{product_id}` | client (cancel flow opened) |
| `cancel_offer_shown` / `cancel_offer_accepted` | `{offer}` | client |
| `pro_gate_hit` | `{gate: "portfolio"\|"league_limit"\|"knobs"\|"extension"\|"three_team", route}` | client + `ENTITLE-OBSERVE` server log |
| `knob_changed` | `{knob, value}` | client (Pro) |
| `entitlement_granted` | `{source, entitlement}` | server (foundation §3/§5) |
| `invite_created` / `invite_clicked` / `referral_joined` / `referral_activated` / `referral_rewarded` | per foundation §5 | mixed |
| `share_card_rendered` / `share_card_shared` | `{surface, kind}` | client |

Targets (benchmarked, not promises): paywall view→trial ≥8% · trial→paid ≥25% ·
free→paid ≥2% by D35 · referral K 0.2–0.5 · invite→activation and referred-user D30
retention tracked from day one · cancel-offer acceptance ≥10%.

## 6. Rollout plan

Flag sequence (all default False in `FLAG_KEYS`; foundation §1 order):

1. Merge everything dark. Foundation tables + routes live; zero user-visible change.
2. `monetize.entitlements` ON in **observe mode** (foundation §2.4): `ENTITLE-OBSERVE`
   logs measure would-block counts per gate on real TestFlight traffic. Minimum 1–2 weeks.
3. Operator bulk-grants Pro to current TestFlight testers (foundation §3) — grandfathering
   + goodwill.
4. Review observe data → finalize gate list (drop any gate that would block a top-decile
   retention behavior).
5. **Pricing research (pre-paywall, teardown 2026-07):** Van Westendorp price-sensitivity
   survey on the TestFlight cohort (4 questions, in-app or lifecycle email) before the
   public paywall flips — validates the $34.99/$4.99 points and the Founder band against
   measured WTP instead of comp inference. Readout is an operator input to Q2, not a gate.
6. `monetize.paywall` ON (TestFlight window; shares the surface with the Founder offer per
   Plan C sequencing). **Same-release checklist item:** update `web/privacy.html` (§ "No
   email addresses, phone numbers, or payment information — … no billing, and no in-app
   purchases") and any matching terms language in the SAME release that ships purchase UI
   — the legal docs must never lag the paywall (teardown S9 PRD-01/03). Verify 3.1.2
   plumbing at review time: billed amount most legible on the paywall, Restore present,
   terms + privacy linked.
7. `monetize.pro` ON at public launch (Aug–Sep) → enforcement + purchasable SKUs. **At
   launch:** PPP (purchasing-power-parity) price localization via App Store per-storefront
   pricing + Stripe adaptive pricing — the highest-win-rate paywall lever (~62% of
   localization experiments win).
8. `growth.referral` ON post-launch once share-card + attribution verified;
   `growth.group_unlock` A/B after that.

Kill switches: `monetize.entitlements` OFF reverts the entire product to today's behavior;
`monetize.paywall` OFF removes purchase UI independently.

## 7. Risks

| Risk | Mitigation |
|---|---|
| **Gating too close to the core loop** — league cap + knob gates could nudge the rank→trades loop and dent retention pre-PMF (retention is the whole moat vs free comps) | Observe mode before enforcement (§6.2); guardrail is structural (`require_pro` never wraps core-loop routes — auditable by grep); D7/D30 watched post-enforcement with rollback = one flag |
| Multi-league/knob demand is assumed, not measured | an-user-data query on league counts per account + observe logs before finalizing gates (Plan A's stated riskiest assumption) |
| Annual first-renewal only 35–37% | Cancel-flow win-back v1 (R10); year-2 economics planned around win-backs, not renewals |
| Free comps (KTC etc.) cap willingness to pay | Price in the empty $30–50 band; Pro sells *your league's* trade intelligence, not values data |
| Apple rejection of referral mechanics | Action-gated rewards only (R11); plain description in Notes for Review (appendix, referral brief) |
| External-checkout rule reversal (~mid-2027) | Payment-agnostic entitlements (foundation §2); Stripe is additive, not load-bearing |
| Trial abuse / promo stacking | Store-managed trial eligibility; promo caps + co-membership fraud control (R12); see LLD edge cases |

## 8. Open questions (operator decisions)

| # | Question | Recommendation |
|---|---|---|
| Q1 | League cap semantics: per-season distinct leagues (R3) vs concurrent-league swap-anytime | Per-season distinct, swap allowed with confirm |
| Q2 | Annual price $34.99 vs $39.99; trial 14 vs 30 days | $34.99 / 14-day; revisit after Founder-window price signal |
| Q3 | Do Trends / League Summary / Free Agents stay free forever, or become Pro later? | Free at launch (they feed the loop); revisit with observe data — changing later is a paywall-config flip, not an app release |
| Q4 | Grandfather TestFlight testers 90 days or perpetual? | 90-day bulk grant (foundation §3 bulk-grant), Founder offer is their perpetual path |
| Q5 | Cancel-flow win-back offer mechanics (store promotional offer vs promo-entitlement month) | Promo-entitlement month v1 (no store config dependency) |
| Q6 | iOS deep-link to web Stripe checkout at launch, or IAP-only until SCOTUS clarity? | IAP-only v1 on iOS; Stripe for web users (lower risk, same entitlements) |
