# Season Pass — HLD

Owner: pm-monetization → eng-backend / eng-mobile / eng-integrations.
Date: 2026-07-17. Status: DRAFT. Companion to [prd.md](prd.md); builds on the
[platform foundation](../00-platform-foundation.md) — every primitive (tables,
webhook pipeline, paywall config route, manual grants, growth caps) is the
foundation's; this doc specifies only the season-pass deltas.

## 1. Purchase flow through the foundation platform

```
App Store purchase (non-consumable, RevenueCat SDK)
      │  NON_RENEWING_PURCHASE webhook            Stripe Checkout (one-time)
      ▼                                                 │ checkout.session.completed
POST /api/billing/revenuecat/webhook            POST /api/billing/stripe/webhook
      └──────────────► subscription_events ◄────────────┘
                              │  projector (idempotent on event_id)
                              ▼
                    entitlements row:
                      entitlement = "pro"
                      source     = "season_pass_iap"
                      product_id = "ftf_season_pass_2026"
                      expires_at = season_end(product_id)   ← server-side, NOT store-side
                              │
                              ▼
                GET /api/me/entitlements  →  clients gate on {pro: true, expires_at}
```

Nothing new architecturally: same webhook → ledger → projector → resolution path as
Pro subscriptions (foundation §2). The **only** season-pass-specific logic is:

1. A static `SEASON_SKUS` map (SKU → season metadata) consulted by the projector and
   the paywall config route.
2. The **season-scoping projector rule** (§3) — the deliberate store/server expiry
   mismatch.
3. Seasonal display logic in `GET /api/paywall/config` (§2).

The store treats the SKU as owned forever (restore always succeeds Apple-side);
the server enforces the season. The year label in the SKU/product name is what makes
this honest: the user bought "2026 Season Pass", not "Season Pass".

## 2. Paywall-config seasonal logic

`GET /api/paywall/config` (foundation §2.3) stays the single server-driven paywall
source. Season-pass additions to its response assembly, evaluated in order:

1. **Flags:** `monetize.paywall` off → no config. `monetize.season_pass` off → pass
   SKUs simply absent; the 3-option paywall degrades to Pro-only (monthly / annual /
   founder). Foundation master-switch semantics unchanged.
2. **Already entitled:** caller has active `pro` (any source) → config returns
   `entitled: true` + manage-state; no purchase options. (This resolves "Pro holder
   buys pass" at the display layer — §5.)
3. **Season calendar** (small static table shipped with the backend, one row per
   league year: `season_end`, `early_bird_start/end`, `rookie_window_start/end`,
   `display_end`): selects which pass SKU (if any) occupies a paywall slot —
   fall/winter → current season pass; Apr–May → rookie pass; after `display_end` →
   none until the next SKU's window opens.
4. **Caller history:** prior-season `season_pass_iap` row → substitute the
   returning-buyer SKU; active rookie-pass row → add the upgrade SKU.
5. **Hero selection:** config's hero slot carries either annual Pro or the season
   pass per the calendar + operator setting (PRD §8.5); the client renders whatever
   the config says — packaging changes never need an app release (foundation design
   goal).

Prices in the config are display strings; the store is authoritative at purchase
time (StoreKit localizes). Early-bird is an ASC scheduled price change + matching
config display window, not a coupon.

## 3. Season-scoped entitlement projection (the core rule)

Projector case for `product_id ∈ SEASON_SKUS`, on any grant-shaped event
(INITIAL/NON_RENEWING_PURCHASE, restore-derived events, TRANSFER):

- `expires_at = SEASON_SKUS[product_id].season_end` — **always** the SKU's fixed
  season end, never `purchase_date + duration`. Purchase on Jul 30 gets 1 day
  (mitigated by pulling the SKU from sale months earlier — §4); restore mid-season
  on a new device gets exactly the remainder; restore after season end computes an
  `expires_at` in the past → row written (audit) with `status='expired'`, **no
  active access re-granted**. Idempotency on `event_id` plus upsert-by
  `(user/account, product_id)` keeps repeated restores from stacking rows.
- REFUND/CANCELLATION → `status='refunded'` on the matching row (foundation §6
  security requirement: propagates within one webhook cycle).
- The row is otherwise a normal foundation entitlement: resolution, account
  survival across Sleeper re-links, daily expiry-hygiene cron (which now actually
  has season rows to mark `expired` — read-time evaluation remains the correctness
  truth, unchanged).

Growth-loop and comp grants reuse the same expiry: milestone pass rows
(`source='promo_referral'`, `metadata.program='milestone_season_pass'`) and operator
comps (`source='manual_grant'`) set `expires_at = season_end` — season scope is a
property of the *grant*, not of the store product.

## 4. Year-rollover architecture

Rollover is an annual operational routine, not code. Code changes per year: one
`SEASON_SKUS` entry + one season-calendar row (a small PR, no schema/logic edits).

**New-SKU minting checklist (run May–June for season N+1):**

1. ASC: create non-consumables `ftf_season_pass_20NN` (+ `_returning`, and in spring
   `ftf_rookie_pass_20NN` + `_upgrade`), Family Sharing OFF, submit with a routine
   app update (avoids August review-queue risk — PRD §7).
2. RevenueCat: add products to offerings; map to the `pro` entitlement.
3. Stripe: create one-time Prices; wire coupon for returning buyers (web path).
4. Backend PR: `SEASON_SKUS` entry + season-calendar row; schedule early-bird price
   change in ASC (manual price edit — offer codes don't apply to non-consumables).
5. Docs: cross-client-invariants (SKU ids), config-reference if any new env.
6. At window close (~Mar): remove year-N SKU from sale in ASC; paywall calendar
   `display_end` already hid it. Restores keep working (Apple requirement) and stay
   season-scoped by §3.

**Grandfathering:** none, by design — year-N buyers get no year-N+1 access; the
re-buy *is* the retention model. What they do get: the returning-buyer SKU/coupon
(the auto-renew substitute) and their purchase history intact. Milestone-earned and
comped passes expire identically; no promo row ever spans seasons.

## 5. Interaction with Pro subscriptions (precedence rules)

Entitlement resolution is already an OR over active rows (foundation §2.2), so
nothing can "conflict" server-side; the rules below govern *display* and *messaging*:

| Case | Rule |
|---|---|
| Active Pro sub (or Founder) views paywall | `entitled: true` → no pass SKUs shown. The store can't stop a determined double-purchase (e.g. web Stripe); if it happens, rows coexist harmlessly, no automated refund — operator handles on request via ASC/Stripe. No "active sub + pass" cancel-prompt needed (unlike Founder, the pass expires on its own). |
| Pass holder mid-season | Paywall hidden (entitled). No trial CTA, no annual upsell mid-season — they already paid for the year; upselling now reads as double-charging. |
| Pass holder at/after season end | The prime conversion moment: win-back surface offers year-N+1 pass (returning price) *and* annual-with-trial side by side. Apple-side intro-offer/trial eligibility is unaffected by non-consumable ownership, so a lapsed pass holder can start the annual trial normally. |
| Pass holder earns give-get Pro months (foundation §5) | Promo months are redundant while the pass is active; foundation stacking rule (extend furthest promo `expires_at`) applies only among promo rows — a promo month landing mid-season extends nothing past `season_end` unless granted within 30d of it. Accepted quirk; not worth machinery. |
| Rookie-pass holder | Sees upgrade SKU only (no full-pass SKU — prevents accidental double-pay); upgrade purchase writes a second row with the full pass's `expires_at`. |
| Milestone earner who already bought | PRD §8.4 (operator decision; default = insert anyway + recognition). |

## 6. Web (Stripe) path

Foundation §4 already specs Stripe Checkout for one-time SKUs keyed to account
email. Season-pass specifics: one Stripe Price per season SKU; returning-buyer
discount = Stripe coupon/promo code gated by the same server-side history check that
gates the iOS returning SKU; webhook → same projector case (§3) with the logical
`product_id`. Cross-platform truth per foundation: a web-bought pass unlocks iOS via
`GET /api/me/entitlements` (guideline 3.1.3(b) multiplatform services); US
anti-steering link-out caveat (SCOTUS ~2027) carried from the plan doc.

## 7. Flag gating

- `monetize.season_pass` — this plan's flag, registered in `FLAG_KEYS`, default
  False (dark). Gates: pass SKUs in paywall config, upgrade/returning display logic,
  seasonal urgency UI. Does **not** gate: projector handling of season SKUs (a
  purchase that somehow lands while dark must still be recorded and granted — money
  was taken), entitlement checks (foundation: checks consult `monetize.entitlements`
  only), manual grants (never flag-gated, foundation §1).
- Master flags apply above it: `monetize.entitlements` (enforcement),
  `monetize.paywall` (any purchase UI). Milestone loop additionally requires
  `growth.referral`.
- Rollout order per foundation §1: pass flag flips with `monetize.pro` at public
  launch.

## 8. Open items feeding the LLD

- Exact `SEASON_SKUS` shape + season-calendar constants → LLD §2.
- Paywall-config response schema deltas + examples → LLD §5.
- Countdown/urgency component spec (Chalkline: flare informational accent, real
  dates only) → LLD §4.
- Test matrix incl. Jul-30 purchase, post-season restore, refund, upgrade → LLD §7.
