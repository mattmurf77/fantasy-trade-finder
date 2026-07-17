# Season Pass — PRD

Owner: pm-monetization. Date: 2026-07-17. Status: DRAFT (pending operator decisions §8).
Plan B of the [top-5 monetization plans](../../../business/product/2026-07-17-monetization-brainstorm-and-plans.md);
builds on the [platform foundation](../00-platform-foundation.md) (entitlements, IAP,
flags, manual grants, growth loops — referenced throughout, never re-specified).
Research: [season-pass brief](../../../business/product/2026-07-17-monetization-research-appendix.md).

## 1. Problem / opportunity

- **Subscription fatigue is a real segment:** 41% of consumers report subscription
  fatigue; average household subs fell 4.1 → 2.8 YoY. Median annual auto-renewal is
  only 23–40% in this category anyway — auto-renew retention is weaker than it looks,
  so a voluntary re-buy with a strong August trigger competes with it.
- **The one-time draft-kit purchase is *the* most proven paid mechanic in fantasy
  football:** Fantasy Footballers UDK $34.99 / UDK+ $59.99 as year-labeled one-time
  IAPs, new SKU each season; ETR Draft Kit Pro $49.99 → $54.99 YoY with $45.99
  early-bird; Dynasty Nerds Rookie Guide $19.99 standalone spring product. 35% of
  apps blend subscriptions + one-time purchases.
- **Demand is deadline-driven:** search and purchase intent peak in August; the
  spring rookie-draft window (Apr–May) is a second, smaller spike that FTF's existing
  rookie surfaces (Pick Anchor wizard, Quick-set tier ladder / draft board) already
  serve.
- Opportunity: capture the fatigued segment that will never start a subscription, at
  ~$17 net per pass (Small Business Program), with a natural repurchase moment every
  season. Assumed math: 500 passes ≈ $8.5k/season net at moderate scale; launch-year
  realistic 50–150 passes ≈ $850–2,500. (All figures assumed/benchmarked, not
  measured.)

## 2. Goals

1. Ship a **year-labeled non-consumable IAP** granting the same "pro" entitlement as
   the Pro subscription, scoped to one league year, dark behind `monetize.season_pass`.
2. Sit on the **same 3-option paywall** as Pro (monthly decoy / annual-or-pass hero /
   founder anchor) — no second paywall surface.
3. Ship the **spring Rookie Pass** SKU + upgrade path for the Apr–May 2027 window.
4. Wire the **milestone growth loop**: 8+ activated leaguemates → free Season Pass.
5. Establish the **annual SKU-rollover routine** (mint, ratchet, retire) so year 2 is
   a checklist, not a project.

## Non-goals

- No changes to what "pro" unlocks — the gate list is Plan A's (Pro) and is consumed
  by reference (§4.2).
- No non-renewing subscriptions (rejected in research: expiry + cross-device delivery
  become our problem; non-consumable + server-side season expiry is the chosen shape).
- No league-scoped or gift purchasing (League Pass is backlog).
- No Android/Google Play.
- No auto-conversion of a pass into a subscription — ever.

## 3. User stories

- **Fatigued non-subscriber:** "I will not add another subscription. Let me pay once
  for this season and be done." → Sees the pass as the hero option in Jul–Sep, buys
  once, everything Pro unlocks until Jul 31, no renewal anxiety.
- **Rookie-draft user (Apr–May):** "I only care about my rookie draft." → Buys the
  ~$9.99 Rookie Pass, gets pro access through the draft window; if hooked, upgrades
  to the full pass for a discounted step-up instead of paying full freight twice.
- **Returning year-2 buyer:** "I bought last year — why is there no loyalty?" → The
  paywall recognizes prior-season pass ownership server-side and shows a
  returning-buyer discounted SKU (iOS) / Stripe coupon (web) as the year-2 retention
  substitute for auto-renew.
- **Milestone earner:** "I got my whole league on FTF." → 8+ activated leaguemates
  (foundation §5 activation gate) auto-grants a free Season Pass; share cards they
  send carry seasonal urgency ("Deadline SZN").
- **Operator:** "Comp a pass for this podcaster / beta tester." → Existing manual-grant
  route with a season-end expiry and a note; no store involvement.

## 4. Functional requirements

### 4.1 SKU calendar

| SKU | Type | Price | On-sale window | Access ends |
|---|---|---|---|---|
| `ftf_season_pass_2026` | non-consumable | $19.99 (early-bird $14.99 — see note) | launch (Aug 2026) → ~Mar 2027 | 2027-07-31 |
| `ftf_rookie_pass_2027` | non-consumable | ~$9.99 | Apr–May 2027 | 2027-07-31 |
| `ftf_season_pass_2027_upgrade` | non-consumable | $7.99 (op. decision, $5–10 band) | shown only to `ftf_rookie_pass_2027` holders | 2028-07-31 |
| `ftf_season_pass_2027` | non-consumable | $19.99 full / $14.99 early-bird (Jun 2027) | Jun 2027 → ~Mar 2028 | 2028-07-31 |
| `ftf_season_pass_2027_returning` | non-consumable | ~$14.99 | shown only to prior-year pass buyers | 2028-07-31 |

- **Assumption:** league year = Aug 1 → Jul 31; SKU year N covers through Jul 31 of
  N+1. (Rookie Pass 2027 covers the *2027 rookie class* draft season, Apr–Jul 2027 —
  its access also ends… see HLD §4 for the resolved rule; the table above reflects
  the resolution: rookie pass access runs to the *following* Jul 31 so an upgrade
  makes sense. Operator confirms in §8.)
- **Note on early-bird:** the launch-year 2026 pass ships in Aug 2026 and therefore
  misses its own June early-bird window; the first real early-bird is Jun 2027 on the
  2027 SKU. Price ratchet = inverse discounting: discount *early* (June), full price
  Jul → Labor Day at urgency peak. Feb–Mar trough: flash-sale hook on the upcoming
  Rookie Pass (DLF pattern).
- Family Sharing OFF on every SKU (consistent with Founder; one-way toggle).
- Next season = new SKU = the repurchase moment. Old SKUs are removed from sale at
  rollover but restores remain honored (and season-scoped — HLD §3).

### 4.2 What the pass unlocks

Exactly the **Pro gate list, by reference** — the set of routes wrapped in
`@require_pro` per the Pro plan LLD ([../pro-subscription/lld.md](../pro-subscription/lld.md)). The pass grants the same
single `entitlement = "pro"` (foundation §2.1); no pass-only features, no Pro-only
features withheld from the pass. The core loop (rank → trades in one synced league)
is never gated (foundation §2.2 guardrail).

### 4.3 Purchase & entitlement behavior

- Purchase (RevenueCat, App Store) → webhook → `subscription_events` → projector
  writes `entitlements` row: `source='season_pass_iap'`, `product_id=<sku>`,
  `expires_at = season_end(sku)`. **Deliberate mismatch:** the store never expires a
  non-consumable; the server expiry enforces season scope. Restore after Jul 31 must
  NOT re-grant active access (projector rule, HLD §3) — the year label in the SKU is
  what makes this safe and legible to users and App Review.
- Web: Stripe one-time payment for the same logical SKU → same projector (foundation §4).
- Manual comp: foundation §3 grant route with `expires_at = season_end`,
  `source='manual_grant'`.
- Milestone grant: `source='promo_referral'`, `expires_at = season_end`,
  `metadata.program='milestone_season_pass'`; caps per foundation §5 plus one
  milestone pass per user per season. **Delta from foundation §5:** promo rows there
  default to +30d; the milestone pass explicitly uses season-end expiry (this doc is
  the spec for that).

### 4.4 Paywall

One 3-option paywall (Plan C anchoring): monthly decoy / **hero = annual OR season
pass** / founder anchor. `GET /api/paywall/config` (foundation §2.3) chooses which
SKUs display, driven by `monetize.season_pass` + the season calendar + the caller's
entitlement history (early-bird pricing display, rookie window, upgrade SKU for
rookie holders, returning-buyer SKU for prior-year buyers). Spec in HLD §2.
Seasonal urgency (countdown to price step-up / season start) renders in Chalkline
terms — flare informational accents, no fake timers: every deadline shown is a real
calendar date.

## 5. Success metrics + events

All via existing `record_event` / `user_events` (client-side event spec from
an-data-architect is the blocking prerequisite, foundation §6). Events:

| Event | When |
|---|---|
| `paywall_viewed` (prop `variant`) | foundation event; `variant` carries which hero showed (annual vs pass) |
| `season_pass_purchased` | projector, on grant (props: sku, price_tier: early_bird/full/returning/upgrade) |
| `rookie_pass_purchased` | projector |
| `pass_upgrade_purchased` | projector |
| `pass_milestone_earned` | milestone grant insert |
| `pass_expired_seen` | client, first post-expiry launch that hits a gate (win-back trigger) |
| `pass_rebuy` | projector, when buyer of year-N SKU purchases year-N+1 SKU |

Targets (assumed, to be replaced by measured baselines):

- Launch year: 50–150 passes sold; pass share of paywall conversions ≥ 25% in Jul–Sep.
- Paywall→purchase conversion on pass-hero variant ≥ annual-hero variant during
  Jul–Sep (else collapse to annual-only — operator decision 3 in the brainstorm doc).
- Year 2: re-buy rate measured via `pass_rebuy` (no industry benchmark exists —
  revealed preference only); returning-buyer SKU uptake among lapsed year-1 buyers.
- Rookie Pass: attach rate in Apr–May; upgrade rate rookie→full ≥ 20% (assumed).

## 6. Rollout

| When | What |
|---|---|
| Aug 2026 | Foundation live (flags, entitlements observe mode, RevenueCat, paywall). `ftf_season_pass_2026` minted in ASC + RevenueCat + Stripe. `monetize.season_pass` ON at public launch with `monetize.pro` (foundation §1 rollout order). Full price $19.99. |
| Sep 2026 | "Deadline SZN" urgency window (real deadline: trade-deadline/season ramp copy). Milestone growth loop live once `growth.referral` flips (after launch, foundation order). |
| Feb–Mar 2027 | Flash-sale hooks: teaser pricing for the upcoming Rookie Pass; 2026 pass removed from paywall display (still restorable). |
| Apr 2027 | `ftf_rookie_pass_2027` on sale (Apr–May window) + upgrade SKU minted. 2026 pass removed from sale in ASC. |
| Jun 2027 | `ftf_season_pass_2027` early-bird $14.99 + returning-buyer SKU. Year-rollover checklist (HLD §4) executed — first full turn of the annual crank. |

Kill switch at every stage: `monetize.season_pass` OFF hides all pass SKUs from
paywall config; already-granted rows keep working (entitlement checks don't consult
the flag — foundation §1 master-switch semantics).

## 7. Risks

- **Year-over-year re-buy rate is unknown** — no vendor publishes theirs. Mitigation:
  it's the cheapest possible test (ship, measure season 2 via `pass_rebuy`);
  returning-buyer discount exists specifically to prop this number.
- **SKU-per-year App Review friction:** every new season's SKUs need review. The
  year-labeled pattern is well-precedented (UDK does exactly this), but reviews can
  stall in August when it hurts most. Mitigation: mint year-N+1 SKUs with a routine
  app update in May/June (checklist, HLD §4), months before the sales window.
- **Cannibalization of annual Pro:** the pass may pull buyers who'd have taken the
  $34.99 annual. Mitigation: measured via `paywall_viewed` variant props; operator
  decision 3 (brainstorm doc) pre-authorizes collapsing to annual-only if data says so.
- **Offer-code gap on iOS (spec correction):** Apple offer codes apply to
  auto-renewable subscriptions only — they cannot discount a non-consumable. The
  returning-buyer discount on iOS is therefore a **display-gated discounted SKU**,
  not an offer code; Stripe coupons cover web. (Labeled here because the plan-doc
  shorthand "offer codes" is wrong for this SKU type.)
- **Server-expiry mismatch confusion:** a user seeing "purchased" in App Store
  history after Jul 31 may expect access. Mitigation: year label in the product name,
  expiry date shown at purchase time and in Settings, win-back surface at expiry.

## 8. Operator decisions

1. **Rookie Pass access end** — recommend: runs to the *following* Jul 31 (i.e.
   `ftf_rookie_pass_2027` ends 2028-07-31 alongside the 2027 season pass), making the
   upgrade a true step-up within one season. Alternative (cheaper to reason about,
   worse UX): hard stop at Jul 31 2027.
2. **Upgrade price** — recommend $7.99 flat (rookie + upgrade = $17.98, between
   early-bird and full). Band per research: $5–10.
3. **Returning-buyer discount depth** — recommend $14.99 (matches early-bird; simple
   story: "loyal buyers always get the early-bird price").
4. **Milestone pass for someone who already bought** — recommend: insert the promo
   row anyway (harmless overlap, `pass_milestone_earned` still fires) and surface a
   recognition badge; do NOT build credit/refund machinery. Alternative: convert to a
   year-N+1 returning-buyer grant.
5. **Hero A/B** — run annual-vs-pass hero rotation Jul–Sep 2026, or fixed pass-hero
   during draft ramp? Recommend fixed pass-hero Jul–Sep, annual-hero otherwise;
   A/B once event volume supports it.
6. **2026 launch price** — $19.99 vs $24.99 late-window ratchet. Recommend $19.99
   flat for year 1 (no early-bird existed, so no ratchet story to tell).
