# Monetization Platform Foundation — shared HLD/LLD

Owner: pm-monetization → eng-backend / eng-mobile / eng-integrations.
Date: 2026-07-17. Status: DRAFT (pending operator green-light on
[the top-5 plan doc](../../business/product/2026-07-17-monetization-brainstorm-and-plans.md)).

Every monetization plan (Pro, Season Pass, Founder, Affiliate, Ads) and both
growth-loop programs build on the primitives in this doc. Plan docs reference this
file instead of re-specifying schemas. Nothing here ships user-visible on its own;
everything is dark behind flags.

## 1. Feature flags

All new flags follow the existing pattern: registered in `FLAG_KEYS` in
[backend/feature_flags.py](../../../backend/feature_flags.py) (defaults False), flipped
in `config/features.json` or `FTF_FLAGS` env, served to clients via
`GET /api/feature-flags`. Mobile/web read `window.FTF_FLAGS` / the flags hook as today.

| Flag | Gates |
|---|---|
| `monetize.entitlements` | Master switch: entitlement *checks* become enforcing. OFF = every feature behaves exactly as today (all users implicitly "pro"); billing/webhook routes stay mounted but grants have no user-visible effect. This is the global kill switch. |
| `monetize.paywall` | Paywall surfaces (mobile + web). OFF = no purchase UI anywhere, even if entitlements enforce. |
| `monetize.pro` | Pro subscription SKUs purchasable + Pro gate list active |
| `monetize.season_pass` | Season Pass SKUs purchasable (year-labeled non-consumables) |
| `monetize.founder` | Founder Lifetime SKU visible/purchasable (also auto-hides at cap) |
| `monetize.affiliate` | Affiliate placements (web/extension/app per plan doc) |
| `monetize.ads_web` | Web display ads |
| `monetize.ads_mobile` | Mobile AdMob (banner + rewarded) + ATT prompt |
| `growth.referral` | Give-get referral program (invite CTAs, reward granting) |
| `growth.group_unlock` | League group-unlock experiment |

Admin/manual-grant routes are **not** flag-gated — they follow the `X-Cron-Secret`
operator pattern and are safe to keep always mounted (fail closed in prod without
`CRON_SECRET`, same as `/api/feedback/admin`). Grants written while
`monetize.entitlements` is OFF simply sit dormant until the flag flips — this is the
intended rollout order (grant testers first, flip enforcement later).

Rollout order: `monetize.entitlements` ON in *observe* mode first (see §2.4),
then `monetize.founder` + `monetize.paywall` (TestFlight window), then
`monetize.pro`/`monetize.season_pass` at launch, `growth.referral` after, ads last.

## 2. Entitlement service (backend)

### 2.1 Tables (add to `backend/database.py`; update docs/data-dictionary.md)

```
entitlements
  id              INTEGER PK
  user_id         TEXT NOT NULL, indexed      -- working key (sleeper id or acct_*), same
                                              -- opaque-key convention as every other table
  account_id      TEXT NULL, indexed          -- accounts.id when known; lets grants survive
                                              -- Sleeper re-links (resolution checks both)
  entitlement     TEXT NOT NULL               -- "pro" | "ad_free" (ad_free is the
                                              -- lightweight ads-only value specced in
                                              -- the ads plan HLD §4; enum in glossary)
  source          TEXT NOT NULL               -- apple_iap | stripe | founder_iap |
                                              -- season_pass_iap | promo_referral |
                                              -- promo_group_unlock | manual_grant | trial
  product_id      TEXT NULL                   -- store SKU, e.g. ftf_pro_annual (subs
                                              -- are not year-labeled), ftf_season_pass_2026
                                              -- (season SKUs are), ftf_founder
  status          TEXT NOT NULL DEFAULT 'active'   -- active | expired | revoked | refunded
  starts_at       TEXT NOT NULL (UTC ISO)
  expires_at      TEXT NULL                   -- NULL = perpetual (founder, manual perpetual)
  granted_by      TEXT NULL                   -- "operator" for manual grants; webhook id else
  note            TEXT NULL                   -- operator note on manual grants
  metadata        TEXT NULL (JSON)            -- store payloads: original_transaction_id,
                                              -- stripe subscription id, referral id, etc.
  created_at / updated_at
```

```
subscription_events            -- append-only billing ledger ("tracking subscriptions")
  id              INTEGER PK
  source          TEXT NOT NULL               -- revenuecat | stripe | app_store_notification
  event_type      TEXT NOT NULL               -- INITIAL_PURCHASE, RENEWAL, CANCELLATION,
                                              -- BILLING_ISSUE, EXPIRATION, REFUND,
                                              -- PRODUCT_CHANGE, UNCANCELLATION …
  user_id         TEXT NULL, indexed
  account_id      TEXT NULL
  product_id      TEXT NULL
  event_id        TEXT UNIQUE                 -- provider event id → idempotency
  payload         TEXT NOT NULL (JSON, raw)
  occurred_at     TEXT NOT NULL
  processed_at    TEXT NULL                   -- NULL until the projector has applied it
  process_error   TEXT NULL
```

```
referrals
  id                 INTEGER PK
  referrer_user_id   TEXT NOT NULL, indexed
  referred_user_id   TEXT NULL, indexed       -- filled when the invitee is identified
  league_id          TEXT NOT NULL            -- the shared Sleeper league (fraud control:
                                              -- reward only verified co-members)
  invite_token       TEXT UNIQUE NOT NULL     -- carried by the share-card deep link
  status             TEXT NOT NULL DEFAULT 'pending'
                                              -- pending → joined → activated → rewarded
                                              -- | rejected (fraud/cap) | expired
  qualifying_event   TEXT NULL                -- e.g. "matchups_completed>=25"
  reward_entitlement_id  INTEGER NULL FK → entitlements.id
  created_at / joined_at / activated_at / rewarded_at
  UNIQUE(referrer_user_id, referred_user_id)  -- one reward per unique referred user ever
```

```
affiliate_clicks               -- outbound click ledger for CPA attribution (subid)
  id          INTEGER PK
  user_id     TEXT NULL, indexed
  partner     TEXT NOT NULL                   -- underdog | draftkings | fanduel | …
  placement   TEXT NOT NULL                   -- e.g. web_bestball_card, ext_trade_overlay
  subid       TEXT UNIQUE NOT NULL            -- passed to the partner link; joins payouts
                                              -- back to placement/user cohort (no PII)
  clicked_at  TEXT NOT NULL
  -- reconciliation write-back columns (nullable; populated by the monthly
  -- partner-report import script — see affiliate LLD): converted_at,
  -- payout_cents, reconciled_at
```

### 2.2 Resolution

`get_entitlements(user_id) -> {"pro": bool, "sources": [...], "expires_at": ...}`:
active = any row for `user_id` **or** the account behind it (join via
`linked_identities`/`accounts` when `user_id` is `acct_*` or has an account) with
`status='active'` and (`expires_at` IS NULL or > now). Expiry is evaluated at read
time; a daily cron marks stale rows `expired` for reporting hygiene (no correctness
dependency on the cron). Per-request memoization; no cross-request cache at SQLite
scale.

`require_pro` route decorator: when `monetize.entitlements` is OFF → always allow.
When ON → 402 `{"error": "pro_required"}` for gated routes. The **core loop
(rank → see trades in one synced league) is never wrapped** — the gate list lives in
each plan's LLD, and the decorator is applied per-route so the guardrail is auditable
by grepping `@require_pro`. Not every gate is decorator-shaped: the free-tier
1-league cap is enforced at league-sync time inside `POST /api/session/init`
(sessions are one-league-at-a-time already), and non-route gates document their
check site in the owning plan's LLD.

### 2.3 API

| Route | Purpose |
|---|---|
| `GET /api/me/entitlements` | Client bootstrap: `{pro, ad_free, sources, expires_at, flags_snapshot}` — mobile/web read this directly. Session-authed (same verified-session layer as accounts). **Exception:** the Chrome extension authenticates via username-only `POST /api/extension/auth`, so its `pro` bool rides in that auth payload instead (see pro-subscription LLD; spoof risk is read-only and flagged for eng-security review). |
| `POST /api/billing/revenuecat/webhook` | RevenueCat events → `subscription_events` → projector updates `entitlements`. Auth: `Authorization: Bearer <REVENUECAT_WEBHOOK_SECRET>` (secrets.local.env / Render env). Idempotent on `event_id`. |
| `POST /api/billing/stripe/webhook` | Same, Stripe signature verification (`STRIPE_WEBHOOK_SECRET`). |
| `GET /api/paywall/config` | Server-driven paywall: SKUs, prices (display), which options show (founder cap remaining, trial eligibility), so packaging changes don't need app releases. Flag-aware. |

Projector rule: `entitlements` rows are **only** written by (a) the webhook
projector, (b) referral/group-unlock reward granting, (c) manual-grant admin routes.
Client receipts are never trusted directly; the mobile app's RevenueCat SDK state is
a UX hint, the server row is the truth (cross-platform: web Stripe purchase unlocks
iOS and vice versa — Apple guideline 3.1.3(b) multiplatform services).

### 2.4 Observe mode (pre-enforcement safety)

`monetize.entitlements` flips ON before any paywall exists. In this state every
`require_pro` check logs `ENTITLE-OBSERVE user=<id> route=<r> would_block=<bool>`
(same pattern as AUTH-GRACE) without blocking. This produces the measured "how many
actives would hit each gate" numbers that finalize the gate list — mirroring the
auth.enforce_verified_writes grace rollout that already worked.

## 3. Manual grants (operator requirement)

Mechanism to manually grant access/memberships to specific users. `X-Cron-Secret`
auth (identical to `/api/feedback/admin`; open in local dev without the secret, 503
fail-closed in prod without it).

| Route | Behavior |
|---|---|
| `POST /api/admin/entitlements/grant` | Body: `{user: <sleeper_user_id \| sleeper_username \| acct_id \| account_email>, entitlement: "pro", duration_days: N \| expires_at: ISO \| perpetual: true, note: "beta thanks"}`. Resolves `user` against users/accounts (username → id via existing lookup), inserts `source='manual_grant', granted_by='operator'`, returns the row. Emits `user_events` type `entitlement_granted`. |
| `DELETE /api/admin/entitlements/<id>` | Sets `status='revoked'` (audit-preserving; never hard-deletes). |
| `GET /api/admin/entitlements?user=…` | List a user's rows (all statuses) for support. |
| `POST /api/admin/entitlements/bulk-grant` | `{users: [...], …}` — e.g. grant all current TestFlight testers 90 days in one call. |

Operator UX: callable via `curl` with `CRON_SECRET` from `secrets.local.env`; a
one-page admin HTML surface can come later — the endpoints are the mechanism.

## 4. IAP enablement + subscription tracking (mobile/web)

**Store setup (one-time, eng-mobile + operator):** paid-apps agreement in App Store
Connect · enroll Small Business Program (15%) · create SKUs (`ftf_pro_monthly`,
`ftf_pro_annual` auto-renewables in one subscription group; `ftf_founder`,
`ftf_season_pass_2026` non-consumables) · restore-purchases button (guideline 3.1.1).

**Client:** RevenueCat `react-native-purchases` (Expo config plugin, EAS build — same
integration mode as existing native modules). RevenueCat chosen over raw StoreKit 2:
solo-operator webhook simplicity, RN support, **promotional entitlements API** (used
by the referral loop; §5), price experiments later. Offerings mirror
`/api/paywall/config`; the app renders paywalls from server config, purchases through
RevenueCat, then trusts `GET /api/me/entitlements` for gating.

**Web:** Stripe Checkout (subscriptions + one-time SKUs) keyed to the account email;
webhook → same projector. US iOS may deep-link to web checkout under the current
anti-steering rules (plan docs carry the SCOTUS-risk caveat).

**Subscription tracking:** `subscription_events` is the ledger; a nightly cron rolls
up MRR / active subs / trial counts / churn events into `user_events`-style metrics
rows surfaced by an-user-data queries. RevenueCat dashboard is the convenience view;
the ledger is the audit source.

## 5. Growth-loop infrastructure

Shared by Pro/Season Pass/Founder plans (program rules live in those PRDs):

- **Invite links:** `https://ftf.app/join/<invite_token>` → web landing → store/app
  deep link; token binds referrer + league. Share cards (Chalkline-styled trade/board
  images) embed the link. `record_event` types: `invite_created`, `invite_clicked`,
  `referral_joined`, `referral_activated`, `referral_rewarded`.
- **Activation gate (Apple-safe):** rewards trigger only on in-app *actions* —
  referred user is a verified co-member of the referrer's Sleeper league **and**
  completed ≥25 ranking matchups. Never on install/signup (3.2.2(x) history).
- **Granting:** referral rewards insert `entitlements` rows
  (`source='promo_referral'`) server-side — no store involvement, never converts to
  a charge. The reward writer is **parameterized** on (entitlement, duration):
  default = `pro` for 30 days; the ads plan's ad-free reward uses
  (`ad_free`, 30d) — see ads PRD decision D4 for when each applies; the season-pass
  milestone grants (`pro`, season-end expiry). Stacking: extends the furthest
  `expires_at` among promo rows of the same entitlement; paid subs are extended via
  RevenueCat promotional entitlement instead so the store UI stays coherent.
- **Caps:** ≤4 rewarded referrals per referrer per season; one reward per unique
  referred user ever (schema-enforced); league co-membership check is the fraud
  control.
- **Group unlock (`growth.group_unlock`):** when ≥8 members of a league have
  activated, insert 14-day `promo_group_unlock` rows for every member. One unlock per
  league per season. A/B against per-referrer rewards per the plan doc.

## 6. Cross-cutting

- **Instrumentation:** every purchase/paywall/referral surface fires `record_event`
  (existing `user_events`); the an-data-architect client-event spec is a blocking
  prerequisite for funnel numbers and is referenced by every PRD.
- **Docs to update when building:** data-dictionary (new tables), api-reference
  (new routes), config-reference (new flags + secrets: `REVENUECAT_WEBHOOK_SECRET`,
  `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `ADMOB_APP_ID`, partner affiliate
  IDs), cross-client-invariants (entitlement names, SKU ids, paywall enum strings),
  glossary (entitlement, founder, season pass, referral activation), ADR for the
  RevenueCat + server-truth decision.
- **Security (eng-security review before launch):** webhook signature verification,
  admin surface stays CRON_SECRET-guarded, no receipts/PII in logs, refunds
  propagate to `status='refunded'` within one webhook cycle.
- **Postgres path:** all new tables are SQLAlchemy Core like existing ones; no
  SQLite-specific SQL.
- **Source enum is extensible:** a purchase can arrive on either rail (e.g. a
  founder purchase via Stripe during the TestFlight window — see founder HLD), so
  role predicates like "is founder" key on `product_id`/`metadata`, never on
  `source` alone.
- **Account deletion:** the `backend/accounts.py` delete matrix predates these
  tables. The foundation build adds them to it: revoke `entitlements` rows,
  tombstone `subscription_events` via the existing `DELETED_USER_PLACEHOLDER`
  convention, keep counterparty referral grants intact, and warn in deletion copy
  that store billing must be cancelled with Apple/Stripe separately.
