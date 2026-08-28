# Sandbox / TestFlight checklist — IAP enablement

**Date:** 2026-08-28 · **Runs:** operator, on a real device, once the **Paid Apps agreement is
active** · **Log the outcome in** `living-memory/TEST_LEDGER.md`

**Why this is the only runtime evidence.** [D-056](../../../../living-memory/DECISIONS.md) retired
Maestro and the simulator, and StoreKit purchases were never simulator-testable anyway. The
automated evidence is `mobile/tests/check-paywall.js` (11 assertions) plus
`backend/tests/test_paywall_config.py` / `test_entitlements.py`; the written evidence is
[code-walk-proof.md](code-walk-proof.md). **Everything below is what neither of those can see**:
that StoreKit actually presents a sheet, that RevenueCat actually delivers a webhook, and that a
row actually lands in `entitlements`.

Work top to bottom. **Stop at the first failure** — every later step depends on the earlier ones,
and a "pass" recorded downstream of a broken webhook is worse than no record.

Where this disagrees with `docs/plans/monetization/iap-enablement-runbook-2026-08-27.md` (authored
on the `app-launch-scorecard` worktree; not present in this tree at the time of writing), **the
runbook wins** — flag order especially.

---

## Part 0 — Prerequisites (none of this is code; all of it is operator lane)

| # | Item | Where | Done when |
|---|---|---|---|
| P1 | **Paid Apps agreement active** | App Store Connect → Business | Status reads Active. Nothing below works before this — sandbox purchases fail with an opaque StoreKit error. |
| P2 | **ASC subscription SKUs created** and in a subscription group | ASC → Subscriptions | `ftf_pro_monthly` ($4.99/mo, **3-day free trial** introductory offer — operator ruling 2026-08-28) and `ftf_pro_annual` ($34.99/yr, **14-day free trial** introductory offer) exist and are "Ready to Submit". Reminder: Apple grants **one intro-offer redemption per subscription group per person**, so a sandbox account that redeems one trial will not see the other — and the same is true for real users. **The ids must match `backend/server.py` `_PAYWALL_PRODUCTS` exactly** — if ASC was configured with the runbook's `pro_monthly_499` / `pro_annual_3499` names instead, see the SKU-naming conflict in [scope.md](scope.md) and reconcile BEFORE testing, not after. |
| P3 | **RevenueCat project + app** created, App Store shared secret uploaded | app.revenuecat.com | The two products are imported and attached to an **entitlement whose identifier is exactly `pro`** (`mobile/src/api/purchases.ts` `PRO_ENTITLEMENT_ID`, and `backend/entitlements.ENTITLEMENTS`), inside an **Offering marked Current** with an `annual` and a `monthly` package. Offerings not marked Current will not reach the app. |
| P4 | **`EXPO_PUBLIC_REVENUECAT_IOS_KEY`** = the RevenueCat **Apple public/SDK key** (starts `appl_`), set as an EAS environment variable for the `production` profile | EAS project env | **Build-time inlining** — this is baked into the JS bundle by babel-preset-expo. Setting it later, or changing it, requires a **new EAS build**. It cannot be fixed by a flag flip or an OTA update. Never the RevenueCat *secret* key. |
| P5 | **`REVENUECAT_WEBHOOK_SECRET`** set in **Render** env AND in the local `secrets.local.env` | Render dashboard (NOT `render.yaml` — [G-018](../../../../living-memory/GOTCHAS.md): blueprint `envVars` never reach a dashboard-created service) | `POST /api/billing/revenuecat/webhook` returns 401 for a wrong bearer and 200 for the right one. With the secret unset in prod the route **503s by design** (`backend/server.py`, `billing_revenuecat_webhook`). |
| P6 | **RevenueCat webhook configured** | RevenueCat → Integrations → Webhooks | URL `https://<render-host>/api/billing/revenuecat/webhook`, Authorization header `Bearer <REVENUECAT_WEBHOOK_SECRET>`. |
| P7 | **Sandbox Apple ID** created and signed in on the test device | ASC → Users and Access → Sandbox; device Settings → App Store → Sandbox Account | Use a sandbox account with **no prior purchase of these SKUs**, or step 7's trial will be ineligible and step 5's copy will not show the trial line. |
| P8 | **A build containing this work** on TestFlight | `eas build --profile production --platform ios` then `eas submit` | Required regardless of flags: `react-native-purchases` is native code, so an OTA update cannot deliver it (`living-memory/DEPENDENCIES.md` 2026-08-28). |

### Flag order (runbook B9)

All `monetize.*` flags are `false` in `config/features.json` today. Flip in `config/features.json`,
push (Render auto-deploys), or hot-reload without a deploy:

```bash
curl -X POST https://<render-host>/api/feature-flags/reload \
  -H "X-Cron-Secret: $CRON_SECRET"
```

| Step | Flag | Effect | When |
|---|---|---|---|
| F1 | `monetize.paywall` → `true` | The Settings row appears and `GET /api/paywall/config` starts answering `enabled:true`. **Gating is still off** (`check_pro` returns `True` whenever `monetize.entitlements` is false), so nothing in the app locks. This is the flag this checklist runs under. | Before step 2 |
| F2 | `monetize.entitlements` → `true` | Observe mode *only while `monetize.paywall` is false*; with the paywall flag already on, this pair is **enforcing** (`backend/entitlements.check_pro`). This build wraps **zero** routes in `@_require_pro`, so nothing changes yet either way — but do not flip it during this checklist. | A later build |
| — | `monetize.pro` | **Read by no code today** — registered in `backend/feature_flags.py` only. Flipping it does nothing. | — |

**After any flag flip, force-quit and relaunch the app.** The mobile flag map is cached in
AsyncStorage and revalidated on cold start; a warm foreground only refetches on a 30-minute
throttle (`mobile/src/state/useFeatureFlags.ts`).

**Rollback lever:** set every `monetize.*` flag back to `false` and reload. That is today's
behavior exactly, with no deploy and no build.

---

## Part 1 — The checks

Record `PASS` / `FAIL` + a note per row.

### 1. The no-key / Expo Go safety net (do this FIRST, before any key exists)

**Why first:** this is the one check that proves the feature cannot hurt anyone who never sees it,
and it is only possible in a build without the key.

1. Launch the current TestFlight build (or `npx expo start` → Expo Go) with
   `EXPO_PUBLIC_REVENUECAT_IOS_KEY` **unset** and all flags off.
2. Sign in, browse Rank → Trades → Matches → League, open Settings.

**Expect:** no crash, no new error, no console RevenueCat noise beyond Expo Go's own
"Using RevenueCat in Browser Mode" line, and **no "Fleeced Pro" row in Settings**. The app must be
indistinguishable from v1.16.8.

### 2. The paywall is reachable, and only from Settings

1. Flip **F1** (`monetize.paywall`). Force-quit, relaunch.
2. Open Settings.

**Expect:** a **Subscription** section with a **Fleeced Pro** row showing `Free` (or, briefly,
no status line at all before the entitlements fetch lands — that is correct, not a bug: the row
refuses to guess). Tap it.

**Expect:** the paywall opens as a **modal** (slides up from the bottom, not a push), with a ✕ in
its top-right.

**Also confirm the negative:** nothing else in the app navigates here. Rank, Trades, Matches,
League, Portfolio, and the Draft surfaces must show no upsell and no lock. Gate-driven entry points
are a later build.

### 3. Guideline 3.1.2 — everything visible before purchase

On the paywall, **without scrolling past the CTA**, confirm each of these is on screen:

- [ ] Plan name for each plan (e.g. "Fleeced Pro — Annual", or the App Store's own localized title)
- [ ] Price **and** period — e.g. `$34.99/year`, `$4.99/month`
- [ ] Trial terms on the annual plan — `14 days free, then $34.99/year`
- [ ] `Auto-renews until cancelled. Cancel anytime in Settings ▸ Subscriptions.`
- [ ] A **Restore Purchases** control
- [ ] **Privacy Policy** and **Terms of Use**, both tappable
- [ ] A visible dismiss control (✕)

Tap **Privacy Policy** and **Terms of Use**.
**Expect:** each opens the browser at `https://<render-host>/privacy` and `/terms` — real pages,
not 404s. (This is the single most common 3.1.2 rejection cause; a 404 here fails the review.)

Then tap ✕. **Expect:** back to Settings, nothing changed, no error.

### 4. Prices come from the App Store, not from our server

Re-open the paywall on the device with the key present and P3 complete.

**Expect:** the prices shown are the **StoreKit-localized** strings (change the device's App Store
region if you want to prove it — the currency should follow the storefront). If the prices are the
US-English `$4.99` / `$34.99` literals in a non-US storefront, the offering did not load: check
that the RevenueCat Offering is marked **Current** and that the product ids match P2 exactly.

### 5. Sandbox purchase of the annual plan with trial

1. Select the annual plan (it should already be selected — it is the `hero` SKU).
2. Tap the CTA. It should read **Start free trial**.

**Expect:** the StoreKit sheet appears, marked **[Environment: Sandbox]**, stating the free-trial
terms. Confirm the purchase with the sandbox Apple ID.

**Expect after confirmation:** the modal dismisses on its own, and Settings' Fleeced Pro row now
reads **Pro**.

### 6. RevenueCat saw it

RevenueCat dashboard → **Customer History**, search the app user id (your session working key — the
Sleeper user id, or `acct_<…>` for an account-only session).

**Expect:** a customer whose **app user id equals that working key** (not a bare
`$RCAnonymousID:…`), an `INITIAL_PURCHASE` event, and the `pro` entitlement showing **active**
with a trial period.

> If the id is anonymous, the identity bridge did not run — the app configured RevenueCat before a
> working key existed. Note the exact sign-in path you used; that is a real bug, not a config issue.

### 7. Render got the webhook, and it landed in the ledger and the entitlement table

RevenueCat → Integrations → Webhooks → delivery log.

**Expect:** a `200` for the `INITIAL_PURCHASE` event. A `401` means P5/P6 disagree on the secret; a
`503` means `REVENUECAT_WEBHOOK_SECRET` is unset on Render.

Then confirm the row actually exists (substitute your own values; `CRON_SECRET` is in the
gitignored `secrets.local.env` at the repo root — never paste it into chat or a doc):

```bash
curl -s "https://<render-host>/api/admin/entitlements?user=<sleeper_username_or_id_or_acct_id>" \
  -H "X-Cron-Secret: $CRON_SECRET" | python3 -m json.tool
```

**Expect:** `entitlements` contains a row with `entitlement: "pro"`, `status: "active"`,
`source: "apple_iap"`, the `product_id` you bought, and an `expires_at` about 14 days out (the
trial).

### 8. The app reads the SERVER, not the receipt

```bash
# From the device's own session — easiest via the app; this curl is for a
# session token you already hold.
curl -s "https://<render-host>/api/me/entitlements" \
  -H "X-Session-Token: <token>" | python3 -m json.tool
```

**Expect:** `{"pro": true, "ad_free": true, "sources": ["apple_iap"], "expires_at": "…",
"enforcing": false}` — `enforcing:false` is correct while `monetize.entitlements` is off.

**Then the real test:** background the app for a moment and re-open it. The Settings row must still
read **Pro** — that value now came from the server on foreground refresh, not from the device
receipt.

### 9. Restore Purchases on a clean install

1. Delete the app. Reinstall from TestFlight. Sign in with the **same** FTF account and the **same**
   sandbox Apple ID.
2. Before opening Settings, note that the app has no local cache.
3. Settings → Fleeced Pro → **Restore Purchases**.

**Expect:** the modal dismisses (or the row flips to **Pro**), with no error. A `paywall_restore`
event with `restored: true` is emitted.

**Then the harder half:** repeat with a sandbox Apple ID that has bought **nothing**.
**Expect:** the honest message "No subscription found on this Apple ID." — and **not** an error
dialog, and **not** a silent no-op.

### 10. Cancel is silent

Open the paywall, tap the CTA, and dismiss the StoreKit sheet with **Cancel**.

**Expect:** no error message of any kind, no toast, the paywall stays open, and the plan stays
selected. (A `paywall_purchase_failed {user_cancelled: true}` event is emitted, but the user sees
nothing — a cancel is a decision, not a failure.)

### 11. The dark state really is dark

Set `monetize.paywall` back to `false`, reload flags, force-quit, relaunch.

**Expect:** the Fleeced Pro row is gone from Settings; nothing anywhere offers a purchase; the app
is v1.16.8's behavior. The **entitlement row is still in the database** and
`GET /api/me/entitlements` still reports `pro: true` — that is correct. Flags gate the surface, not
the grant, and a paying user's grant must survive a kill switch.

---

## Analytics spot-check (optional, same session)

With `analytics.client_events` on, the run above should have produced, in order:
`paywall_viewed {source:'settings', platform:'ios'}` → `paywall_purchase_initiated {product_id,
source}` → `paywall_purchase_completed {product_id, source}` → (step 9) `paywall_restore
{restored}` → (step 10) `paywall_purchase_failed {product_id, user_cancelled:true}`.

Server-side conversion truth is separate and does **not** depend on these: `entitlement_granted` is
fired by `backend/entitlements.grant()` when the webhook lands.

---

## Known gaps this checklist deliberately does not cover

- **Gate behavior.** This build wraps zero routes in `@_require_pro`, so there is nothing to lock
  and nothing to test. The Pro gates (portfolio, engine knobs, league cap) are a later build with
  their own checklist.
- **Web / Stripe.** `web/pro.html` and the Stripe checkout route are out of scope
  ([scope.md](scope.md)).
- **Renewal, refund, TRANSFER, BILLING_ISSUE.** These are webhook projector paths covered by
  `backend/tests/test_entitlements.py`. Sandbox renewals run on an accelerated clock and are worth
  a separate soak, not a step in this list.
- **`react-native-purchases-ui`.** Not installed and not planned — the paywall is a hand-built
  Chalkline screen.
