# Founder Lifetime — PRD

Owner: pm-monetization. Date: 2026-07-17. Status: DRAFT (pending operator green-light).
Builds on [../00-platform-foundation.md](../00-platform-foundation.md) (entitlements,
webhooks, paywall config, manual grants — referenced throughout, never re-specified).
Source plan: [Plan C](../../../business/product/2026-07-17-monetization-brainstorm-and-plans.md)
· research: [founder-lifetime brief](../../../business/product/2026-07-17-monetization-research-appendix.md).

## 1. Opportunity

One-time **$99–119 "Founder" lifetime** offer (band; point price = operator decision
D8 — repriced from $79, teardown 2026-07, see pricing rationale), capped at **100**,
TestFlight-exclusive window before public launch, then closed forever. Three jobs, in
order of value:

1. **Willingness-to-pay probe.** The TestFlight list is the owned warm channel the
   research playbook prescribes (warm-list launches convert ~10x cold; founders
   routinely sell ~50 LTDs to a ~1k list). An optional $119-vs-$99 A/B is the cheapest
   price-elasticity test FTF can run before the public paywall exists.
2. **Cash now.** 50–100 × $99–119 ≈ **$5–12k one-time**, ~85% net under the Small
   Business Program. Peak season (Jul–Aug) is the demand window.
3. **Permanent paywall anchor.** On the eventual 3-option paywall (monthly decoy →
   annual hero → lifetime ceiling), a visible lifetime ceiling pushes annual selection
   to 69–74%. After the window closes, the sold-out Founder slot keeps anchoring.

**Pricing rationale (appendix; repriced 2026-07-19, teardown S9 PRD-03):** folk-wisdom
2–3x annual is the LOW end; RevenueCat observes 2x–12x and recommends pricing above
expected LTV; Airbridge norm **3–5x**; comps: Calm 5x, Flighty ~5x, Jumpspeak 3.6x.
The original **$79 ≈ 3.5–4x claim was computed against an intended $20–25 annual that
Plan A superseded** — against the shipped $34.99 hero SKU, $79 is only ≈2.3x, below the
3–5x floor, and the anchor teaches that "forever" costs two seasons. Repriced band:
**$99 ≈ 2.8x · $109 ≈ 3.1x · $119 ≈ 3.4x** of the $34.99 annual. Recommend **$119**
(inside the 3–5x band); $99 is the floor of the band, defensible only if warm-list
price sensitivity demands it (still above folk-wisdom 2–3x, but under the 3x
institutional floor). Cap-100 and the honest closed-forever window are unchanged —
they, plus the multiple, are what keep lifetime an offer, not the business model.

**Cannibalization is priced in, not wished away:** ~15–20% of lifetime buyers are
warm leads who would have converted to annual within 60 days (pull-forward), and
lifetime-dominant apps monetize roughly half as well as yearly-dominant ($0.19 vs
$0.36 rev/install at D14). The ≈3–3.4x multiple + hard cap of 100 + closed-forever
window is what keeps lifetime an *offer*, never the business model.

**Scarcity is honest:** real caps carry an 8–32% conversion lift; fake timers burn
trust. Average LTD does ~100 sales — "first 100 Founders" is honest *and* hittable.
The remaining count shown to users is the real server-side count, always.

## 2. Goals / non-goals

**Goals**
- G1: Ship a purchasable `ftf_founder` non-consumable behind `monetize.founder`,
  granting the same perpetual "pro" entitlement the foundation defines
  (`expires_at NULL`, `source='founder_iap'`).
- G2: Honest cap of 100 enforced server-side via paywall config; SKU hides everywhere
  at cap; operator flag flip closes the window regardless of count.
- G3: Permanent Founder badge (account-keyed, survives Sleeper re-links) on profile,
  trade cards, and a founders wall (web + in-app).
- G4: Sub-overlap detection: active sub + founder purchase → prompt user to cancel
  the sub (StoreKit will not auto-cancel).
- G5: Operator can comp founder status (`manual_grant`, perpetual + badge) for e.g.
  most-active beta testers.
- G6: Measure everything: offer views, purchases, cap-remaining snapshots, A/B arm.

**Non-goals**
- No trial (non-consumables can't have one), no Family Sharing (one-way toggle;
  Flighty withdrew family lifetime — leave OFF).
- No post-window "reprice to 5x+" lifetime SKU — the window closes forever; a future
  non-founder lifetime is a separate decision (backlog).
- No refunds UI, no gifting, no league-scoped founder bundles.
- Not the referral program itself (pm-growth owns it) — this PRD only reserves
  founders' first-access hook into it.
- No client analytics SDK — `record_event`/`user_events` per foundation §6.

## 3. User stories

- **TestFlight tester (window open):** I open FTF during the founder window and see
  the Founder offer — value-first headline, real remaining count ("31 of 100 left"),
  the window price ($99–119 band, D8), what I get forever. I buy in two taps, see
  "You're Founder #17", and my badge is live on my profile immediately.
- **Founder, post-purchase:** My profile and my trade cards carry the Founder badge
  permanently. I appear on the founders wall as #17. When I re-link a different
  Sleeper account, the badge follows my account. I get first access to the give-get
  referral program when it ships, and a "Founder #17" share card for my league chat.
- **Sub-holder buying lifetime:** I already have an active Pro sub (post-launch case)
  and buy Founder anyway. The app immediately tells me my subscription is now
  redundant and deep-links me to Manage Subscriptions to cancel — FTF never silently
  double-charges me.
- **Operator comping a tester:** I run one `curl` against the foundation's grant
  route with `perpetual: true` + founder marker and a note ("top-10 beta tester");
  the tester gets the perpetual entitlement, the badge, and a founders-wall spot,
  without touching the store or the cap.

## 4. Functional requirements

### FR1 — Offer window lifecycle
`monetize.founder` (already in the foundation flag table) **is** the window: OFF =
pre-window/closed, ON = open. States and transitions in HLD §1. Cap-hit auto-hides
the SKU while the flag is still ON; flag OFF closes regardless of count. Closed +
`monetize.paywall` ON = anchor-mode (sold-out Founder row on the 3-option paywall).

### FR2 — Cap
- Cap value lives in server config (default **100**, operator decision D2).
- `GET /api/paywall/config` (foundation §2.3) returns the founder block with a live
  `remaining` computed from `entitlements` rows — displayed honestly in every client.
- `remaining == 0` → founder block returns `state: "cap_hit"`, no purchasable SKU.
- Purchase races at the boundary are resolved by **accepting small oversell**
  (LLD §7.1) — a completed Apple purchase is never rejected server-side.
- Manual comps do **not** consume cap slots (recommendation; operator decision D4).

### FR3 — Purchase + entitlement
- `ftf_founder` non-consumable, Family Sharing OFF, no trial. RevenueCat webhook →
  foundation projector → `entitlements` row (`pro`, `source='founder_iap'`,
  `expires_at NULL`, `product_id='ftf_founder'`, founder number in metadata).
- Restore purchases must re-grant forever, including after the window closes
  (guideline 3.1.1 — the SKU is hidden from offers, never removed from ASC).
- **TestFlight rail caveat:** TestFlight IAPs run in the App Store sandbox — they do
  not charge real money. The pre-launch window therefore transacts via **Stripe web
  checkout** (foundation §4 web rail; account-keyed, unlocks iOS), surfaced from the
  in-app offer as an outbound link; the `ftf_founder` IAP rail activates at public
  launch for any remaining window/anchor time. See HLD §4 and risk R5.

### FR4 — Badge surfaces
- **Truth:** badge = presence of an active founder entitlement row (purchase or
  manual comp) resolved per foundation §2.2 — account-keyed, survives Sleeper
  re-links. No separate badge table.
- **Surfaces:** mobile ProfileScreen (public profile), mobile TradeCard (counterparty
  chip on match cards), web `profile.html`, founders wall. Chalkline: **flare accent**
  — the badge is an informational highlight, never an action, which is exactly
  flare's charter (`docs/design/design-system.md` §Flare).
- Badge and wall placement persist after the window closes (permanent recognition).

### FR5 — Founders wall
- Public wall: web page + in-app entry, listing founders in number order.
- Listing is **opt-in at purchase** (privacy default; operator decision D5). Opted-out
  founders show as "Founder #N" with no name.
- Deleted accounts drop off the wall (accounts.py delete matrix; LLD §7.3).

### FR6 — Price A/B (optional, operator decision D1)
- $119 control vs $99 arm (both inside the repriced band — never test below $99) via
  RevenueCat offerings/experiments (two SKUs, one entitlement; HLD §5). Web rail
  mirrors the split by tokenized checkout link.
- Both arms receive identical perpetual entitlement + badge. Cap counts both arms.
- If declined, ship the single D8 point price (recommend $119).

### FR7 — Sub-overlap prompt
Projector flags `active sub + founder` overlap (foundation projector extension);
`GET /api/me/entitlements` surfaces it; clients render a persistent-until-dismissed
prompt deep-linking to Manage Subscriptions (Apple) or the Stripe portal.

### FR8 — Manual grants
Foundation grant route (§3) extended with a founder marker: perpetual `manual_grant`
row + badge + wall spot. Revocation (`DELETE`) removes badge and wall spot.

### FR9 — Growth-loop hooks (reserved surface, not the program)
- Founder share card ("Founder #17", Chalkline) via the foundation share-card
  renderer (§5) — ships with the offer if the renderer exists, else fast-follow.
- `growth.referral` program checks `is_founder` for first-access cohort.
- Founders wall doubles as social proof on the public site.

## 5. Success metrics + events

All via existing `record_event` → `user_events` (foundation §6). Names are
cross-client invariants once shipped.

| Event | When | Properties |
|---|---|---|
| `founder_offer_viewed` | Offer surface rendered | `price_arm`, `remaining` |
| `founder_purchased` | Projector applies purchase | `price_arm`, `rail` (iap/stripe), `founder_number` |
| `founder_cap_remaining` | Daily cron snapshot + on each purchase | `remaining` |
| `founder_sub_overlap_prompted` / `_dismissed` | Overlap prompt shown / dismissed | — |
| `founder_wall_viewed` | Wall opened (in-app) | — |
| `founder_share_card_created` | Share card generated | `founder_number` |
| `entitlement_granted` | Manual comp (foundation event) | existing |

**Targets (assumptions, not measured — no baseline exists):**
- Primary: ≥50 founders by window close (research: ~50 LTDs per ~1k warm list; our
  list is smaller — treat 50 as stretch, 25 as viable).
- Offer-view → purchase ≥5% on the TestFlight cohort (warm ~10x cold assumption).
- A/B readout: net revenue per exposed user by arm (not conversion alone).
- Guardrail: post-launch annual-plan selection ≥60% on the 3-option paywall (anchor
  is working); founder share of total paid users trending *down* after launch
  (lifetime never dominant).

## 6. Rollout timeline

Depends on: foundation entitlements + webhook projector + paywall-config route +
manual grants; ASC paid-apps agreement + SBP enrollment; Stripe checkout (web rail).

| Phase | When (assumed) | What |
|---|---|---|
| 0. Dark build | late Jul | All code behind `monetize.founder` OFF; SKUs created in ASC; pytest green; manual comps granted to top testers (dormant until entitlements flip) |
| 1. Window open | early Aug | Flip `monetize.founder` (+ `monetize.paywall`) for the TestFlight cohort; Stripe rail live; mkt-lifecycle sends the window announcement; A/B arms live if D1=yes |
| 2. Window close | cap hit or operator date (D3; default: public-launch day) | Cap-hit auto-hide or flag flip; "founders closed" announcement; wall stays up |
| 3. Anchor mode | public launch (Aug–Sep) | 3-option paywall ships (Plan A); Founder row renders sold-out as ceiling anchor; badge/wall permanent |

## 7. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Pull-forward cannibalization** — best 15–20% of would-be annual subs buy once | Priced at ≈3–3.4x the shipped annual (2026-07 reprice); hard cap 100; window closes forever; track founder share of paid |
| R2 | **Mispricing permanence** — lifetime holders never see price increases; every future feature ships to them free | Cap bounds total exposure to ≤100 users; "everything FTF ever ships" is the explicit promise — don't ship a carve-out later (trust) |
| R3 | **App Review of a capped SKU** — server-hidden SKU + external purchase link scrutiny | Hiding via server paywall config is standard; SKU stays restorable (3.1.1); US external-link entitlement rules currently allow the Stripe link but SCOTUS risk ~mid-2027 — don't hard-depend, IAP rail is primary at launch |
| R4 | **Warm list too small/cold** (riskiest assumption in Plan C) | The offer *is* the cheapest WTP test (plus the Van Westendorp pass in the Pro rollout, step 5); 25 sales still = ~$2.5–3k + calibration data; cap unmet ≠ failure, close honestly |
| R5 | **TestFlight sandbox** — pre-launch IAP can't take real money | Stripe web rail during the window (FR3); if operator rejects link-out, shift window to launch day with TestFlight-list early access instead (D3) |
| R6 | **A/B fairness blowback** — $119 buyer learns leaguemate paid $99 | Short A/B window, or decline D1; never A/B after public visibility grows |
| R7 | **Refund gaming at cap** (buy→refund→slot churn) | Refund reopens the slot naturally (honest count); volume too small to game profitably; operator can close window anytime |

## 8. Operator decisions

| # | Decision | Recommendation |
|---|---|---|
| D1 | Run the $119/$99 A/B? | Yes if TestFlight list ≥200; else ship the D8 point price flat |
| D2 | Cap size | 100 ("first 100 Founders") |
| D3 | Window dates | Open early Aug; close at public launch or cap, whichever first |
| D4 | Do manual comps consume cap slots? | No — comps are additive recognition, purchases fill the 100 |
| D5 | Wall listing opt-in vs opt-out | Opt-in at purchase (privacy-safe default) |
| D6 | Anchor-mode display after close | Show sold-out Founder row on the paywall ("100/100 — closed") for anchoring + social proof |
| D7 | Refund policy at cap | Refund reopens the slot while window open; moot after close |
| D8 | Point price within the $99–119 band (2026-07 teardown reprice) | $119 (≈3.4x annual — inside the 3–5x researched band); take $99 only on strong warm-list price-sensitivity signal (Van Westendorp readout, Pro rollout step 5) |
