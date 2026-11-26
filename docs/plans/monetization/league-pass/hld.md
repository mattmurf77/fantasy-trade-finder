# League pass — HLD

Owner: eng-architect review pending. Date: 2026-11-22. Status: DRAFT.
Builds on [../00-platform-foundation.md](../00-platform-foundation.md): the
`entitlements` and `subscription_events` tables, the RevenueCat webhook and projector,
and the admin grant routes are specified there. It also builds on the global paywall
gate (`backend/paywall_gate.py`). This doc covers how the league pass composes them.
Requirements are traced to [prd.md](prd.md) R-numbers. Detail is in [lld.md](lld.md).

- [1. Component architecture](#1-component-architecture)
- [2. Core model](#2-core-model)
- [3. Data flows](#3-data-flows)
- [4. Flags and surfaces](#4-flags-and-surfaces)
- [5. Integration points](#5-integration-points)
- [6. Sequencing and dependencies](#6-sequencing-and-dependencies)
- [7. Alternatives considered](#7-alternatives-considered)

## 1. Component architecture

```
 App Store ──▶ RevenueCat ──webhook──▶ ┌──────────────────────────────────────────────┐
                                       │ backend (Flask, backend/server.py)           │
                                       │                                              │
                                       │  billing webhook ─▶ subscription_events      │
                                       │        └─▶ projector ─▶ entitlements         │
                                       │              (buyer: pro, league_pass_iap)   │
                                       │        └─▶ league_pass.on_billing_event      │
                                       │              └─▶ league_passes (bind)        │
                                       │                                              │
  operator (curl) ────────────────────▶│  admin comp / list / end ─▶ league_passes    │
                                       │                                              │
  league sync (Sleeper/ESPN/MFL) ─────▶│  league_members, platform_league_bindings,   │
                                       │  leagues.previous_league_id                  │
                                       │                                              │
                                       │  NEW backend/league_pass.py                  │
                                       │    quote · intent · bind · repoint · covers  │
                                       │                                              │
                                       │  paywall gate hook                           │
                                       │    resolve league ─▶ verdict(…, league_id)   │
                                       │         pro? ─▶ covers? ─▶ preview ─▶ 402    │
                                       │                                              │
                                       │  GET /api/me/entitlements (+ league_passes)  │
                                       │  GET /api/paywall/config  (+ league_pass)    │
                                       │  /api/league-pass/*                          │
                                       └───────────────────┬──────────────────────────┘
                                                           │
                                              ┌────────────▼─────────────┐
                                              │ mobile (Expo)            │
                                              │  useEntitlements         │
                                              │    pro + leaguePasses    │
                                              │    proForLeague(id)      │
                                              │  LeaguePassScreen        │
                                              │  PaywallScreen entry     │
                                              │  SubscriptionSection     │
                                              │  api/purchases (offers)  │
                                              └──────────────────────────┘
```

One new backend module, `backend/league_pass.py`, owns everything stateful, in the same
way `entitlements.py` and `paywall_gate.py` do. Routes in `server.py` stay thin wrappers.

## 2. Core model

Three facts decide coverage, and each has one owner.

| Fact | Owner | Written by |
|---|---|---|
| The buyer's subscription is active | `entitlements` (a `pro` row, source `league_pass_iap`) | The billing projector only |
| The pass is bound to a league | `league_passes` | `league_pass.py` only |
| The member is in the league | `league_members`, `platform_league_bindings` | League sync only |

**Coverage is derived, never stored.** `league_pass.covers(user_id, league_id)` joins the
three facts at read time. No row is written per member. This follows the existing rule
that `expires_at` is read-time truth (`entitlements._active_rows`).

The consequences:

- Lapse, refund and grace need no fan-out: the buyer's row changes and coverage follows
  (R33, R34).
- A leaguemate who joins later is covered at once (R5). A member who leaves stops being
  covered at the next sync (R6).
- A covered member holds no entitlement row. So `_held_pro` still reads them as never
  entitled, and they keep the deck preview and the individual free month (R35).

**Account-level `pro` keeps its meaning.** Only the buyer has it. A covered member's
`pro` stays false, and coverage is a separate, league-keyed answer on both the server
and the client.

## 3. Data flows

### 3.1 Quote → purchase → bind

```
client                         server                              RevenueCat / Apple
  │ POST /api/league-pass/intent {league_id}
  │ ─────────────────────────▶ member? league uncovered? buyer free?
  │                            INSERT league_pass_intents
  │ ◀───────────────────────── {intent_id, product_id, teams}
  │
  │ purchase(ftf_league_annual)  (free month if intro-eligible) ▶ sheet
  │                                                          ◀────────── webhook
  │                            projector: buyer row (pro, league_pass_iap),
  │                              trial or paid alike
  │                            league_pass.on_billing_event:
  │                              open intent? still valid? member? uncovered?
  │                              INSERT league_passes (active)
  │ GET /api/me/entitlements
  │ ─────────────────────────▶ pro: true, league_passes: [{role: buyer, …}]
```

The league never travels through the store or RevenueCat. The intent is the only source
of the binding, and the server re-checks it when the webhook arrives (R17, R18, R20).

If no usable intent exists, the buyer keeps Pro and the pass stays unbound. The client
then calls `POST /api/league-pass/bind` (R19).

### 3.2 Gate evaluation (request path)

```
before_request hook
  rule gated and server enforcing?            no → through
  session user?                               no → through (route's own 401)
  demo session on a deck rule?                yes → through
  web request with the web knob off?          yes → through
  verified?                                   no → route's 403, or 402 verify_required
  account-level pro?                          yes → through
  flag monetize.league_pass on?               no → skip the next line
  league = resolve(rule, request, session)
  league and covers(user, league)?            yes → through; g.paywall_pass_league = league
  never held pro and a deck rule?             preview
  else                                        402 pro_required
```

Two properties matter:

- The unverified answer is settled before coverage is read, so it cannot reveal whether
  a pass exists (R8).
- Coverage is checked before the preview, so a covered request never spends it (R9).

**The league-match rule.** The gate resolves a league before the handler runs, and the
handler then decides which league it acts on. If the two could differ, a covered member
could name league A to the gate and act on league B. So a request let through by a pass
carries `g.paywall_pass_league`, and every gated handler confirms the league it acts on
equals it, or answers 402 (LLD §4.3).

### 3.3 Renewal, cancellation, expiry, refund

| Event | Buyer's row | Coverage | Other effect |
|---|---|---|---|
| Renewal | Expiry moves out | Continues | None |
| Auto-renew off | Unchanged | Continues to expiry | None. No ending notice is sent (R32) |
| Auto-renew back on | Unchanged | Continues | None |
| Billing issue | Expiry extended to the grace date | Continues | None |
| Expiry | `expired` | Ends at once | A hygiene job marks the pass `ended` (reporting only) |
| Refund | `refunded` | Ends at once | The buyer is blocked from buying again (R36) |
| Transfer to another account | Re-keyed | Follows the new owner if they are a member, else released | — |
| Upgrade from an individual plan (prd R42) | A league row; the individual row on the same chain `expired` | Starts at the bind | Binds from the intent on the first league event (LLD §5.1) |
| Downgrade to an individual plan | At the renewal into the individual plan, `expired` | Ends then | The pass is ended |

A buyer whose Pro also comes from a grant (lifetime, comp, promo, Founder) keeps the
grant through all of the above: coverage reads only the `league_pass_iap` row.

### 3.4 Re-point

The buyer calls `POST /api/league-pass/repoint`. The server checks membership of the new
league, that it has no pass, and the 30-day cooldown. It releases the current row and
inserts a new one in one transaction (R21). Coverage is derived, so it moves at once.

### 3.5 Sleeper season rollover

Sleeper gives a league a new id each season and names the old one in
`previous_league_id`. League sync starts storing that field. When it imports a league
whose previous league has an active pass, and the buyer is a member of the new one, it
moves the pass. This does not use the buyer's re-point (R22). ESPN keeps its league id
across seasons; MFL is treated like ESPN until shown otherwise.

### 3.6 Comp pass (operator)

A comp pass is a `league_passes` row with `origin='comp'` and its own expiry. It has no
buyer row behind it. Coverage reads the comp expiry in place of the buyer's subscription.
Phase 1 uses this to test coverage with real users before any purchase UI exists (R39).

## 4. Flags and surfaces

| Surface | `monetize.league_pass` off | On |
|---|---|---|
| Gate | Byte-identical to today; coverage is never read | Coverage checked after account-level Pro |
| `/api/me/entitlements` | No `league_passes` field | `league_passes` list |
| `/api/paywall/config` | No `league_pass` block | Block served only when the client asks with `caps=league_pass` |
| `/api/league-pass/*` | 404 | Live |
| Admin comp routes | Live (operator surface, like the grant routes) | Live |
| Webhook | League products still project the buyer's Pro; no bind | Bind runs |
| Client | No entry, no covered state | Entry on the paywall, covered state, Settings block |

Release to a subset uses a `model_config` allow-list of league ids (R41). Enforcement
itself stays on the existing rule: `monetize.entitlements` ∧ `monetize.paywall` ∧
`paywall_enforce_enabled == 1`.

## 5. Integration points

- **`entitlements.py`.** One new billing source and one product-prefix mapping. The
  projector, the sandbox lane, alias reconciliation and the perpetual-grant guard apply
  unchanged. A sandbox purchase covers the reviewer's league for at most 24 hours.
- **`paywall_gate.py`.** `verdict` gains a `league_id` argument and one coverage check.
  A new `LEAGUE_RESOLVERS` table sits beside `ROUTES`. The 402 body and its `gate` enum
  do not change.
- **`server.py`.** The hook resolves the league. New thin routes. Every new rule gets a
  row in `ROUTES`, or `test_paywall_gate_allowlist.py` fails.
- **League sync.** Stores `previous_league_id`; calls the rollover follow.
- **RevenueCat.** One product, `ftf_league_annual`, attached to the `pro` entitlement,
  in a separate offering named `league`. No in-app purchase key is needed: there are no
  promotional offers to sign.
- **Account deletion.** Releases the buyer's pass and scrubs the two new tables.
- **Analytics.** New events go through the taxonomy review, which is a bright-line
  surface.

## 6. Sequencing and dependencies

Operator, 2026-11-25: the pass is ON at the initial public launch, so the phase 0
experiment no longer comes first (plan D5 superseded).

```
paid launch live ──▶ phase 0 comp experiment (existing bulk-grant route)
                         │ lift?
                         ▼
      ┌── server: tables, covers(), resolvers, hook, tests ──▶ admin comp passes
      │
      ├── legal: ruling on the covered-state disclosure ──▶ copy
      │
      ├── App Store Connect: 1 product, a 1-month free-trial intro offer
      │        └─▶ RevenueCat: offering `league`
      │
      └── client: state, screen, pre-checks, Settings ──▶ store build ──▶ App Review
                                                                │
                                             flag on: allow-list ──▶ everyone
```

Blocking order:

1. The legal ruling comes before any copy, and copy comes before the client can finish.
2. The server lands before the client, because the client is tested against comp passes.
3. The unverified RevenueCat items (plan §15) are settled in sandbox before the webhook
   bind is written.

## 7. Alternatives considered

| Alternative | Why not |
|---|---|
| **Account-wide coverage** (every member gets full Pro everywhere) | A free throwaway Sleeper league turns one pass into twelve full Pro accounts at $8.33 each. It also removes the upsell in members' other leagues. |
| **League-scoped for everyone, including the buyer** | The buyer pays the most and would get less than an individual subscriber. |
| **One stored grant per member** (`promo_group_unlock` rows) | Needs fan-out on purchase, renewal, refund and every roster change, and a hook for late joiners. Derived coverage has none of that. |
| **Reusing `growth.group_unlock`** | That flag names a different idea: a free 14-day unlock when eight members activate. Overloading it would confuse both. |
| **Non-renewing season pass** | Allows several leagues per buyer, but has no renewal revenue and no upgrade path from the individual plan. The projector also refuses a grant with no expiry. |
| **Permanent price tiers** | The lower price would renew for ever, after the leaguemates who earned it may have cancelled. |
| **Year-one discount tiers** ($84.99 / $69.99 in year one when 1–2 / 3+ leaguemates held a paid annual plan; intro plus promotional offers) | Built, then dropped by the operator on 2026-11-24 for a one-month free trial on a single product. The tiers needed three products, four offers, an IAP key and leaguemate counting, and the discounted price revealed that leaguemates subscribe. |
| **Offer codes** | The purchase leaves the app's flow, codes are transferable, and a code inventory has to be kept. Dropped by the operator. |
| **Cash rebates** | Paying people outside the App Store brings payment, tax and fraud handling, and risks reading as getting around in-app purchase. |
| **Binding through RevenueCat subscriber attributes** | They are set by the client, so the league would be client-asserted. |
| **Apple multiseat or Family Sharing** | Seats go to Apple accounts and know nothing about leagues. Both are off on purpose. |
| **Commissioner-only purchase** | No commissioner data is stored, and it differs across the three platforms. |
