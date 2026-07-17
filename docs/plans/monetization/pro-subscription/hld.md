# FTF Pro — HLD

Owner: eng-architect review pending. Date: 2026-07-17. Status: DRAFT.
Builds on [../00-platform-foundation.md](../00-platform-foundation.md) — all schemas
(`entitlements`, `subscription_events`, `referrals`), billing webhooks, `require_pro`,
manual grants, and growth-loop primitives are specified there. This doc covers how the
**Pro plan** composes them across the four clients. Requirements traced to
[prd.md](prd.md) R-numbers.

## 1. Component architecture

```
                        ┌─────────────────────────────────────────────┐
                        │ backend (Flask, backend/server.py)          │
  RevenueCat webhook ──▶│  billing webhooks ─▶ subscription_events    │
  Stripe webhook ──────▶│       └─▶ projector ─▶ entitlements         │
  operator (curl) ─────▶│  admin grant routes ─▶ entitlements         │
  referral qualifier ──▶│  promo grants ─▶ entitlements               │
                        │  get_entitlements() / @require_pro          │
                        │  GET /api/me/entitlements                   │
                        │  GET /api/paywall/config                    │
                        └──────┬───────────┬───────────┬──────────────┘
                               │           │           │
                    ┌──────────▼───┐ ┌─────▼─────┐ ┌───▼────────────┐
                    │ mobile (Expo)│ │ web       │ │ extension (MV3)│
                    │ RevenueCat RN│ │ Stripe    │ │ pro flag in    │
                    │ SDK (buy UX) │ │ Checkout  │ │ /api/extension │
                    │ PaywallScreen│ │ pro.html  │ │ /auth payload  │
                    │ useEntitle-  │ │ paywall   │ │ overlay gating │
                    │ ments hook   │ │ page      │ │                │
                    └──────────────┘ └───────────┘ └────────────────┘
```

Single source of truth: the server `entitlements` table (foundation §2.3 projector rule).
RevenueCat SDK state and Stripe session state are purchase UX only; every client renders
gates from `GET /api/me/entitlements`.

New components this plan adds (everything else is foundation):

| Component | Where | Purpose |
|---|---|---|
| `backend/entitlements.py` | backend | Foundation §2 service implementation home: `get_entitlements`, `require_pro`, projector, observe logging. (Foundation defines behavior; this plan builds it — first consumer.) |
| Pro gate applications | `backend/server.py` | `@require_pro` on the G2/G3/G6 routes + league-cap check in session/league sync (LLD §2) |
| Paywall config route | `backend/server.py` | `GET /api/paywall/config` (foundation §2.3 names it; Pro defines the payload — LLD §3) |
| Engine knob prefs | backend + mobile | New per-user knob storage + `GET/POST /api/trade/knobs`; trade engine reads them when caller is Pro (G3) |
| PaywallScreen + purchase flow | `mobile/src/` | Multi-page soft paywall, RevenueCat purchase, restore |
| `useEntitlements` | `mobile/src/state/` | Entitlements context beside the existing flags/session contexts |
| Web paywall + checkout | `web/` | `pro.html` + Stripe Checkout redirect + success/cancel pages |
| Extension gating | `extension/` | `pro` bool in `/api/extension/auth` response → overlay tiering |
| Share card + invite CTA | mobile first | Foundation §5 growth loop, Pro program rules (R11–R16) |

## 2. Data flows

### 2.1 Purchase → entitlement → client gate

```
iOS:  PaywallScreen ─▶ RevenueCat SDK purchase (StoreKit under the hood)
        ─▶ RevenueCat webhook ─▶ POST /api/billing/revenuecat/webhook
        ─▶ subscription_events (idempotent on event_id)
        ─▶ projector upserts entitlements row (source=apple_iap, product_id, expires_at)
        ─▶ record_event purchase_completed / trial_started
      client: SDK resolves ─▶ refetch GET /api/me/entitlements ─▶ pro:true ─▶ gates open
Web:  pro.html ─▶ Stripe Checkout (account email) ─▶ POST /api/billing/stripe/webhook
        ─▶ same ledger ─▶ same projector ─▶ same entitlements row (source=stripe)
      cross-platform: iOS app reads the same /api/me/entitlements → web purchase unlocks iOS
        (Apple 3.1.3(b) multiplatform services, foundation §2.3)
```

Failure containment: webhook down ⇒ ledger row missing ⇒ client shows purchased-but-locked;
mobile mitigates by also honoring the RevenueCat SDK "pro" customer-info as a **temporary
optimistic unlock** (≤24 h, client-side only) while polling the server. Server remains
truth; optimistic state never writes anywhere.

### 2.2 Renewal / cancel / refund

RevenueCat `RENEWAL` extends `expires_at`; `CANCELLATION` records intent (entitlement stays
active until period end); `EXPIRATION` → projector sets `status='expired'`; `REFUND` →
`status='refunded'` within one webhook cycle (foundation §6 security requirement). Client
cancel flow (R10) fires `cancel_intent` → shows win-back → deep-links to store management;
no server write on intent.

### 2.3 Referral → activation → promo grant

```
Pro/free user taps invite CTA (signal-quality framing, R13)
  ─▶ POST invite creation ─▶ referrals row (pending) + invite_token
  ─▶ share card w/ https://ftf.app/join/<token> (foundation §5) ─▶ league group chat
invitee: link ─▶ web landing ─▶ store/app ─▶ token attached at session init ─▶ status=joined
activation check (on rank-event thresholds + hourly cron):
  co-member of referrer's league? AND matchups_completed ≥ 25?
  ─▶ status=activated ─▶ reward both sides IF referrer under 4/season cap:
       free side: entitlements row source=promo_referral, expires now+30d
       paid side: RevenueCat promotional entitlement extension (store UI coherent)
  ─▶ status=rewarded, record_event referral_rewarded
group unlock (growth.group_unlock): league activated-count ≥8 ─▶ promo_group_unlock rows
  for all members, 14d, once per league per season (foundation §5)
```

### 2.4 Gate evaluation (request path)

`@require_pro` route → `monetize.entitlements` OFF ⇒ pass-through (today's behavior).
ON + observe window ⇒ log `ENTITLE-OBSERVE`, pass. ON enforcing ⇒
`get_entitlements(user_id)` (checks user_id + linked account per foundation §2.2) ⇒ 402
`{"error":"pro_required","gate":...}` when not pro. League cap (G1) is not a decorator —
it's a branch in league-sync/session-init that counts distinct current-season synced
leagues (LLD §2.2).

## 3. Flags × surfaces

| Flag | Backend | Mobile | Web | Extension |
|---|---|---|---|---|
| `monetize.entitlements` | `require_pro` + league cap enforce (observe first, §2.4 foundation) | gates render locked states (via `/api/me/entitlements` `flags_snapshot`) | same | overlay tiering active |
| `monetize.paywall` | `/api/paywall/config` returns `enabled:false` when OFF | PaywallScreen reachable; onboarding hook active | `pro.html` live, nav links shown | popup upsell row |
| `monetize.pro` | Pro SKUs listed in paywall config | purchase buttons render | Stripe checkout enabled | — |
| `growth.referral` | invite/referral routes + reward granting | invite CTAs + share card | join landing page | — |
| `growth.group_unlock` | group-unlock qualifier + grants | league-progress meter variant (A/B) | — | — |

All five already enumerated in foundation §1; this plan registers them in `FLAG_KEYS`
(LLD §6). Clients read flags exactly as today (`GET /api/feature-flags`, `window.FTF_FLAGS`,
flags context) plus the `flags_snapshot` in `/api/me/entitlements` to avoid a second
round-trip on boot.

## 4. Integration points with the foundation platform

| Foundation section | This plan consumes it as |
|---|---|
| §1 flags | Registers `monetize.entitlements/paywall/pro`, `growth.referral/group_unlock` |
| §2.1 tables | No new tables except `trade_knobs` prefs (LLD §2.3 — plan-specific, so specced here not there) |
| §2.2 resolution + `require_pro` | Applied to the PRD §4.1 gate list; observe mode = rollout step 2 |
| §2.3 API | `/api/me/entitlements` is the client bootstrap; Pro defines `/api/paywall/config` payload |
| §3 manual grants | Operator comps + tester grandfathering (R17, rollout step 3) |
| §4 IAP | SKUs `ftf_pro_monthly` / `ftf_pro_annual` in one group; RevenueCat RN SDK; Stripe web |
| §5 growth loop | Invite links, activation gate, granting, caps — Pro supplies program rules R11–R16 |
| §6 cross-cutting | `record_event` names (PRD §5), docs checklist (LLD §9), eng-security review |

## 5. Sequencing / dependencies

```
[A] foundation backend (tables + entitlements.py + webhooks + admin grants + observe mode)
      └─ blocks everything below
[B] store setup (ASC agreement, SBP, SKUs) ── operator + eng-mobile, parallel with [A]
[C] gate applications + league cap + knob prefs backend        ← needs [A]
[D] GET /api/paywall/config                                    ← needs [A]
[E] mobile: RevenueCat init + useEntitlements + locked states  ← needs [A][B]
[F] mobile: PaywallScreen + onboarding placement               ← needs [D][E]
[G] web: pro.html + Stripe checkout                            ← needs [A][D]
[H] extension: pro tiering                                     ← needs [C]
[I] share card + invite CTA (ships first among growth pieces)  ← needs nothing above (deep
     link works pre-monetization; serves every plan)
[J] referral qualifier + rewards                               ← needs [A][I]
[K] group-unlock A/B                                           ← needs [J]
[L] cancel-flow win-back                                       ← needs [E]; can trail launch
      by one release but must exist before first renewals (~30 days post-launch)
Observe-mode window sits between [C] landing and monetize.pro enforcement.
an-data-architect client-event transport blocks the *client-side* PRD §5 events only —
server-side events flow through existing record_event immediately.
```

## 6. Alternatives considered

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| IAP layer | **RevenueCat RN SDK** | Raw StoreKit 2 + App Store Server Notifications | Solo operator: RevenueCat gives signed webhooks with a stable event vocabulary (one projector for Apple+Stripe-shaped events), RN/Expo config-plugin support, receipt validation, **promotional entitlements API which the referral loop needs** (foundation §4), and price experiments later. Raw StoreKit 2 means JWS verification, notification v2 parsing, and hand-rolled promo grants for paid subs — weeks of solo work for zero product difference. Cost (1% of tracked revenue over $2.5k/mo) is immaterial at FTF scale. Exit path preserved: server entitlements are payment-agnostic, so swapping the purchase layer later never touches gates. |
| Web billing | Stripe Checkout (hosted) | Stripe Elements custom UI | Hosted page = no PCI surface, prebuilt SCA; brand polish irrelevant at this scale. |
| Gate placement | Server 402 + client locked states | Client-only gating | Client gating is trivially bypassed (extension/web) and drifts per client; server decorator is auditable by grep (guardrail). |
| League cap point | League-sync/session-init count | Gating league *reads* | Never lock users away from already-synced data; cap at acquisition point only. |
| Trial | Store-managed (annual SKU) | Server-minted trial entitlements | Store handles eligibility/abuse per Apple ID; server trials would double the abuse surface (LLD edge cases). |
