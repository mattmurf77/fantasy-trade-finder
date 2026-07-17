# FTF Pro — LLD

Owner: eng-backend / eng-mobile / eng-web / eng-integrations. Date: 2026-07-17. Status: DRAFT.
Builds on [../00-platform-foundation.md](../00-platform-foundation.md) (schemas §2.1, webhook
routes §2.3, admin grants §3, growth infra §5 — implemented once, consumed here).
Requirements: [prd.md](prd.md) R1–R17; architecture: [hld.md](hld.md).

## 1. Flag registrations — `backend/feature_flags.py`

Append to `FLAG_KEYS` (defaults False via `DEFAULT_FLAGS`; dotted-key convention):

```python
    # Monetization platform (docs/plans/monetization/00-platform-foundation.md §1)
    "monetize.entitlements",  # MASTER: require_pro checks enforce (observe mode first,
                              # foundation §2.4). OFF = today's behavior, global kill switch.
    "monetize.paywall",       # paywall surfaces (mobile PaywallScreen, web/pro.html,
                              # extension upsell row). OFF = no purchase UI anywhere.
    "monetize.pro",           # Pro SKUs purchasable + Pro gate list active
                              # (docs/plans/monetization/pro-subscription/)
    # Growth loops (foundation §5; program rules in pro-subscription/prd.md §4.6)
    "growth.referral",        # give-get invite CTAs, share card, reward granting
    "growth.group_unlock",    # league group-unlock A/B experiment
```

No other flag-plumbing changes — `GET /api/feature-flags`, `window.FTF_FLAGS`, and the
mobile `useFeatureFlags` hook pick these up automatically.

## 2. Backend changes

### 2.1 New module `backend/entitlements.py` (foundation §2 implementation)

`get_entitlements(user_id)`, `require_pro` decorator (observe-mode `ENTITLE-OBSERVE`
logging), webhook projector, referral qualifier + reward granting, manual-grant helpers.
Tables added to `backend/database.py` exactly per foundation §2.1 (`entitlements`,
`subscription_events`, `referrals`; `affiliate_clicks` is Plan D's — skip). SQLAlchemy Core
only (Postgres path).

Decorator stacks UNDER `@app.route` and AFTER the existing session/verification gates
(same convention as `_gate_unverified_read/_write`, see server.py ~1314).

### 2.2 `backend/server.py` — gate applications

| Route | Change | Gate |
|---|---|---|
| `GET /api/portfolio` (~5886) | add `@require_pro(gate="portfolio")` | G2 |
| `POST /api/session/init` (~7002), league-sync branch | not a decorator: when the requested `league_id` is not already synced for this user AND count of distinct current-season synced leagues ≥ 1 AND not pro → 402 `{"error":"pro_required","gate":"league_limit","synced_league": {id,name}}`. Swap flow: client passes `replace_league_id` → old league's synced status released (data retained), new league syncs. Free swap allowed (PRD R3). | G1 |
| `GET/POST /api/trade/knobs` (new, §2.3) | `POST` gets `@require_pro(gate="knobs")`; `GET` open (returns defaults + `pro_locked:true` for free) | G3 |
| `POST /api/trades/generate` (~4423) | read caller's knob prefs via `get_engine_knobs(user_id, league_id)`; free users always get engine defaults (no 402 — core loop untouched) | G3 |
| `GET /api/extension/rankings` (~9010) | when enforcing and caller not pro: strip Pro-overlay fields (`tier_bands`, per-player values beyond rank order) and set `"pro": false` | G6 |
| `POST /api/extension/auth` (~8931) | add `"pro": <bool>` + `"flags"` to response payload | G6 |
| `GET /api/paywall/config` (new) | see §3 | R5 |
| `POST /api/invites` / `POST /api/invites/claim` (new) | create `referrals` row + token; claim binds token at session init (foundation §5 link format `https://ftf.app/join/<token>`); behind `growth.referral` | R11–R14 |
| activation qualifier | hook in the rank-event path (where `record_event` fires rank-class events) + `POST /api/cron/hourly-tick` (~8151): check joined referrals for co-membership + ≥25 matchups → grant per foundation §5 | R11, R15 |

**Never wrapped** (guardrail, auditable by grepping `@require_pro`): `/api/rank3`,
`/api/trio*`, `/api/tiers/*`, `/api/anchor/*`, `/api/rankings/*`, `/api/trades`,
`/api/trades/generate|swipe|matches*`, `/api/trade/values|evaluate`, `/api/league/*`,
`/api/trends/*`, `/api/players*`.

### 2.3 Engine knob prefs (new table, plan-specific)

```
engine_knob_prefs                 -- add to backend/database.py + docs/data-dictionary.md
  user_id    TEXT NOT NULL        -- working-key convention
  league_id  TEXT NOT NULL
  knobs      TEXT NOT NULL (JSON) -- {"aggression":"light|fair|generous",
                                  --  "lanes":"all|window_move|value_move",
                                  --  "fuzzy_tolerance":0.0-0.15,
                                  --  "crown_asset_premium":"default|off|high"}
  updated_at TEXT
  UNIQUE(user_id, league_id)
```

`trade_service.py` / `trade_optimizer.py`: accept an optional `knobs` dict where the
corresponding flag-gated behaviors (`trade.aggression_ab`, `trade.lanes`,
`trade.fuzzy_match`, `trade.crown_asset`) currently read model_config/flag defaults;
knob value overrides the default **only when supplied** (Pro callers). NOTE: today these
are backend A/B or global behaviors with **no per-user UI** — the knob UIs are new build,
not a re-gating of existing controls (labeled assumption in PRD R2). Three-team (G4):
register the gate string now; no client surface yet (`trade.three_team` has no UI).

### 2.4 Account-deletion interplay — `backend/accounts.py`

Extend `delete_user_data()` (delete matrix, accounts.py ~537):

- `entitlements`: set `status='revoked'`, `note='account_deleted'` for the user's rows
  (both `user_id` and resolved `account_id` matches). Never hard-delete (audit +
  refund-dispute trail, mirrors admin revoke semantics foundation §3).
- `subscription_events`: retain rows (financial records) but re-key `user_id` to
  `DELETED_USER_PLACEHOLDER` (existing tombstone convention, accounts.py ~55–58).
- `referrals`: rows where the deleted user is referrer → status `expired`; where referred →
  re-key to placeholder (counterparty's rewarded grant is NOT clawed back).
- Deletion confirmation copy (SettingsScreen + web): "Deleting your FTF account does not
  cancel your App Store/Stripe subscription — cancel in Settings ▸ Subscriptions / the
  Stripe portal." (Apple keeps billing regardless of our rows.)
- Update the matrix comment block + `docs/data-dictionary.md`.

## 3. `GET /api/paywall/config` — contract

Query: `?platform=ios|web|extension` (display filtering only). Session-authed (same layer
as `/api/me/entitlements`). Flag-aware: `monetize.paywall` OFF → `{"enabled": false}`.

```json
{
  "enabled": true,
  "pages": [
    {"id": "value_recap",  "kind": "trades_found",
     "title": "Your league has trades waiting",
     "body_ref": "matches_preview"},
    {"id": "feature_grid", "kind": "features",
     "features": ["unlimited_leagues", "portfolio", "engine_knobs",
                  "extension_overlays", "ad_free"]},
    {"id": "plans",        "kind": "purchase"}
  ],
  "products": [
    {"product_id": "ftf_pro_monthly", "period": "monthly",
     "display_price": "$4.99", "trial_days": 0, "hero": false},
    {"product_id": "ftf_pro_annual",  "period": "annual",
     "display_price": "$34.99", "per_month_equiv": "$2.92",
     "trial_days": 14, "hero": true, "badge": "best_value"}
  ],
  "trial_eligible": true,
  "dismissible": true
}
```

Client renders pages in order; `products` mirrors RevenueCat offerings (iOS) / Stripe
prices (web) — IDs must match, checked in tests. Enum strings (`kind`, `badge`, feature
keys) go in `docs/cross-client-invariants.md`. `body_ref: matches_preview` = client
substitutes 2–3 real matches from its already-fetched `/api/trades/matches` (R5 aha
placement) — the config route never recomputes trades.

**402 shape** (foundation §2.2, extended with `gate`):
`{"error": "pro_required", "gate": "portfolio"}` — clients map `gate` → paywall `source`.

**`GET /api/me/entitlements`** (foundation §2.3) example for client work:
`{"pro": true, "sources": ["apple_iap"], "expires_at": "2027-07-17T00:00:00Z",
"trial": false, "flags_snapshot": {"monetize.paywall": true, ...}}`

## 4. Mobile changes (`mobile/src/`)

| File | Change |
|---|---|
| `App.tsx` | RevenueCat init: `Purchases.configure({apiKey})` after session context mounts; identify with working key (`Purchases.logIn(userId)`); Expo config plugin `react-native-purchases` in `app.json` (EAS build required — same mode as existing native modules) |
| `state/useEntitlements.ts` (new) | context + hook beside `useFeatureFlags`/`useSession`: fetches `/api/me/entitlements` on session init + on app foreground + after purchase; exposes `{pro, trial, expiresAt, refresh}`; AsyncStorage cache with 72 h offline grace (§7); optimistic ≤24 h unlock from RevenueCat customer-info while server catches up (HLD §2.1) |
| `api/billing.ts` (new) | `getPaywallConfig()`, `getEntitlements()`, invite endpoints |
| `screens/PaywallScreen.tsx` (new) | multi-page pager from `/api/paywall/config`; page 1 injects 2–3 real matches; purchase via RevenueCat offerings; restore button; close affordance always visible (soft). Chalkline: ink-1 cards, ice CTA fill, ice tick on hero SKU, flare-bordered `best_value` chip (informational), Barlow Condensed headers — no gradients, no emoji icons, radius ≤8px |
| `navigation/RootNav.tsx` | register root-stack modal route `Paywall` (params: `{source}`); onboarding flow (post league-sync, after MatchesScreen first render with ≥2 matches) pushes it once when `monetize.paywall` |
| `screens/PortfolioScreen.tsx` | when enforcing + not pro: locked state (ice "Unlock with Pro" CTA → `Paywall {source:'portfolio'}`); fires `pro_gate_hit` |
| `screens/LeaguePickerScreen.tsx` | on 402 `league_limit`: sheet explaining 1-league free cap with two actions — "Replace synced league" (confirm, passes `replace_league_id`) and "Go Pro" (ice CTA → Paywall). Fires `pro_gate_hit {gate:'league_limit'}` |
| `screens/TradesScreen.tsx` | "Engine" knob sheet (new `components/EngineKnobsSheet.tsx`): aggression / lanes / fuzzy / crown-asset controls per §2.3 JSON; free users see controls disabled with lock affordance → Paywall. Also the signal-quality invite banner ("N of M leaguemates ranked" via `/api/league/coverage`) behind `growth.referral` |
| `screens/MatchesScreen.tsx` | same invite banner; share-card CTA at value peaks (match found) |
| `components/ShareCard.tsx` (new) | Chalkline trade/board card render (react-native-view-shot) + share sheet; embeds `https://ftf.app/join/<token>`; fires `share_card_rendered/shared` |
| `screens/SettingsScreen.tsx` | "FTF Pro" section: status (Free / Trial ends X / Pro via Apple/Stripe/Promo), Manage subscription (cancel flow → `cancel_intent`, exit survey, one win-back offer, then `Linking.openURL` store management), Restore purchases; referral progress row ("2 of 4 free months earned") behind `growth.referral` |
| `state/useSession.ts` | attach `invite_token` (from deep link) to session init payload; deep-link handling for `ftf.app/join/*` |

## 5. Web + extension changes

| File | Change |
|---|---|
| `web/pro.html` (new) | paywall page mirroring `/api/paywall/config` (Chalkline tokens from `web/css/styles.css`); Stripe Checkout redirect (`POST /api/billing/stripe/checkout-session` — new thin route creating a Checkout Session keyed to account email, foundation §4); success/cancel query-param states on same page |
| `web/index.html` | nav "Pro" link when `window.FTF_FLAGS["monetize.paywall"]` |
| `web/js/*` | entitlements bootstrap (`/api/me/entitlements`) + locked states on any web Pro surface (portfolio-equivalent pages if/when present) |
| `web/` join landing (new `web/join.html`) | `/join/<token>` landing: league context + store badge/app link; behind `growth.referral` |
| `extension/popup.js` / `popup.html` | show Pro status from `/api/extension/auth` `pro` field; upsell row linking to `web/pro.html` when `monetize.paywall` |
| `extension/content.js` | overlay tiering: basic rank overlay always; Pro overlay fields only when payload contains them (server-stripped per §2.2 — no client secret-keeping) |

Note: extension auth is username-only (no proof), so a spoofed username could *read*
another user's Pro overlay state. Read-only, low value, accepted risk — flag for
eng-security pre-launch review (foundation §6).

## 6. Edge cases

| Case | Handling |
|---|---|
| Trial abuse (delete/re-create account, multiple Sleeper users) | Trials are store-managed per Apple ID / Stripe customer (HLD §6) — server never mints trials. RevenueCat `trial_eligible` reflected in paywall config. Promo abuse capped by foundation §5 fraud controls (co-membership + one-reward-per-referred-user + 4/season). |
| Re-link Sleeper / working-key change | `entitlements.account_id` survives re-links; resolution checks both keys (foundation §2.1/§2.2). Test: grant on `acct_*`, re-link Sleeper, `pro` still true. RevenueCat `logIn` with new working key → aliases merge on RC side. |
| Account deletion | §2.4 matrix. Counterparty referral grants persist; store billing continues until user cancels (explicit copy). |
| Offline grace | Mobile honors cached `/api/me/entitlements` for 72 h past last successful fetch; after that, gates lock (free behavior) rather than fail open indefinitely. Core loop unaffected either way. |
| Refund | Webhook `REFUND` → `status='refunded'` within one cycle → next client fetch locks gates. No claw-back of referral rewards already granted to the *other* side. |
| Double subscription (Apple + Stripe both active) | `get_entitlements` returns both sources; Settings surfaces "You're subscribed twice" with links to both cancel paths (appendix: sub+lifetime detection pattern generalized). |
| Webhook outage / ordering | Idempotent on `event_id`; `processed_at`/`process_error` allow replay (foundation §2.1). Client optimistic unlock (≤24 h) bridges the gap. |
| Grace-period billing issues | RevenueCat `BILLING_ISSUE` → keep `active` until `EXPIRATION` event (matches store grace period); no immediate lockout. |
| Observe mode noise | `ENTITLE-OBSERVE` lines are log-only, rate volume ≈ gated-route traffic — acceptable; same precedent as AUTH-GRACE. |
| Free user's stored knob prefs after downgrade | Rows retained, ignored by engine (defaults used); restored on re-subscribe. |

## 7. Test plan

**pytest** (`backend/tests/`, existing conventions — `test_support.py` fixtures, flag
fixtures like `fixtures/flags/release.json`):

| File | Cases |
|---|---|
| `test_entitlements.py` | resolution (user_id row, account_id row, both, expired, revoked, refunded); expiry-at-read; promo stacking extends furthest `expires_at` |
| `test_require_pro_gates.py` | flag OFF → all pass (today's behavior); observe → logs + passes; enforcing → 402 with `gate`; **grep-audit test: assert no `@require_pro` on the never-gated route list §2.2** |
| `test_league_cap.py` | free 1st league OK; 2nd distinct → 402 `league_limit`; swap with `replace_league_id` OK; pro unlimited; same-league re-init OK |
| `test_engine_knobs.py` | GET defaults for free (`pro_locked:true`); POST 402 free / 200 pro; generate() honors pro knobs, ignores rows for free callers; invalid knob values 400 |
| `test_paywall_config.py` | flag matrix (`monetize.paywall`×`monetize.pro`); product/SKU ids match cross-client-invariants; trial eligibility passthrough |
| `test_billing_webhooks.py` | RC + Stripe: signature/secret auth, idempotency on `event_id`, INITIAL_PURCHASE→active, CANCELLATION keeps active til period end, EXPIRATION→expired, REFUND→refunded, projector `process_error` on malformed payload |
| `test_referral_rewards.py` | full state machine pending→joined→activated→rewarded; both sides granted; 4/season cap; unique-referred-user constraint; non-co-member rejected; <25 matchups not activated; group unlock at 8, once per league per season |
| `test_admin_grants_pro.py` | grant by username/acct/email; bulk grant; revoke; dormant while entitlements OFF |
| `test_account_delete_entitlements.py` | §2.4 matrix: revoked rows, ledger tombstone, referral re-key, counterparty grant intact |

**Maestro** (`mobile/.maestro/`, `NN-slug.yaml` convention, demo-CTA bootstrap per README —
new flows need the monetize flags ON in the test flag set):

- `07-paywall-renders.yaml` — onboarding reaches paywall after matches; pages swipe;
  dismiss lands in free app (soft-gate regression).
- `08-free-gates-render.yaml` — Portfolio locked state + league-cap sheet render, "Go Pro"
  opens Paywall, core loop (Rank → Trades) still fully reachable.
- `09-pro-unlocked.yaml` — with a manual-grant pro test user: Portfolio opens, knob sheet
  enabled, Settings shows Pro status.
- `10-invite-share-card.yaml` — invite banner renders, share card composes (no crash).

Purchase itself is tested manually in TestFlight sandbox (StoreKit sandbox not
Maestro-drivable reliably) — checklist in the release runbook.

## 8. Docs-to-update checklist (root CLAUDE.md table)

- `docs/data-dictionary.md` — foundation tables + `engine_knob_prefs` + deletion-matrix notes
- `docs/api-reference.md` — `/api/me/entitlements`, billing webhooks, `/api/paywall/config`,
  `/api/trade/knobs`, `/api/invites*`, admin grant routes, 402 shape, extension payload change
- `docs/config-reference.md` — 5 new flags; secrets `REVENUECAT_WEBHOOK_SECRET`,
  `REVENUECAT_PUBLIC_SDK_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` (secrets.local.env
  + Render env)
- `docs/cross-client-invariants.md` — entitlement enum (`pro`), SKU ids, paywall config enums
  (`kind`, `badge`, feature keys), 402 `gate` strings, knob enums
- `docs/glossary.md` — entitlement, observe mode, promo grant, referral activation, give-get,
  group unlock, league cap
- `docs/architecture.md` — entitlements module + billing data flow
- `docs/adr/` — ADR: RevenueCat + server-truth entitlements (foundation §6; write it when the
  first code lands)
- `docs/runbook.md` — webhook replay procedure, observe-mode log grep, manual-grant curl
  recipes
- `mobile/src/screens/CLAUDE.md` — PaywallScreen row; `mobile/.maestro/README.md` — new flows
