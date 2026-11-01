# Tip jar at launch

> **Status:** active, 2026-10-31. **Owner:** `monetization-pm` (under `head-product`).
> **Operator ask** (2026-11-01, verbatim, relayed by head-product): "have the right Pm and eng
> create the solution for a tip jar and give me instructions on how to set it up".
> This overturns, for tips only, #393 decision 6 "tips stay dark". The lifetime plan and the
> Season Pass stay out. Read at `origin/main` `245f5e60`. Evidence rules: D-056.
> Scope block: [scope.md](scope.md).

## TL;DR

- **The product:** three consumable in-app purchases, using the ids that are already in the code: `ftf_tip_199` $1.99, `ftf_tip_499` $4.99, `ftf_tip_999` $9.99. iOS only.
- **The entry point:** one row, Settings › Subscription › **Support Fleeced**. It opens the existing `TipJarScreen` modal. No tip prompt appears anywhere else.
- **A tip buys nothing.** Guideline 3.1.1 allows tipping the developer through in-app purchase. The server already stores tips and grants nothing (`entitlements.is_tip_product`).
- **Mostly config:**
  - Server: serve the existing `_PAYWALL_TIPS` list behind a new `model_config` knob, `paywall_tips_enabled` (default 0). That knob is also the kill switch, with no deploy needed.
  - Client: two small items for the 11-06 binary. The Settings row must work for a user who has never opened the paywall (§3 C1), and the copy (§2).
- **The operator:**
  - by **11-05**: create the three tips in App Store Connect and add them to RevenueCat;
  - **11-07**: upload review screenshots from the gated build;
  - **11-10**: attach the tips to the version.
  - Apple reviews an app's **first consumable only with a new app version**. If the tips miss 11-10, they wait for the next version.
- **Risk:** three more in-app purchases on the first review. If Apple objects only to the tips, remove them from the submission, resubmit, and keep the knob at 0. **Tips never hold the 11-18 launch.**

## 1. The product

### The three tips

| Product id | Price (US) | Reference name (internal, ≤64) | Display name (≤30) | Description (≤45) |
|---|---|---|---|---|
| `ftf_tip_199` | $1.99 | `Tip 1.99` | **Small Tip** (default; marketing may replace) | **A one-time tip. It unlocks nothing.** (35) |
| `ftf_tip_499` | $4.99 | `Tip 4.99` | **Medium Tip** | same |
| `ftf_tip_999` | $9.99 | `Tip 9.99` | **Large Tip** | same |

- **Why these ids and prices:**
  - They already appear in `server.py` `_PAYWALL_TIPS` (`:36879-36883`), `test_paywall_config.py:219-222`, `cross-client-invariants.md` and the sandbox checklist (step 10b). Changing them costs code and tests for no gain.
  - After the Small Business Program's 15%, $1.99 nets about $1.69.
  - A later price change happens in App Store Connect alone. The server's price strings are only fallback copy, because StoreKit's localized price wins (`TipJarScreen.tsx:97-99`).
- **Apple's limits** (App Store Connect help, read 2026-10-31):
  - a product id can't be edited after saving, and can't be reused, even after the product is deleted;
  - the display name is 2–30 characters;
  - the description is at most 45 characters;
  - the review notes are at most 4,000 characters.

### Where it shows

- **One row:** Settings › Subscription › **Support Fleeced**, previewed "Tip jar". It's in both the hub (`SettingsHubScreen.tsx:319-327`) and the legacy screen (`SettingsScreen.tsx:1074-1080`).
- **When the row shows:** only while `monetize.paywall` is on **and** the server offers tips (#526).
- **Who sees it:** free and Pro users alike. **Unverified sessions don't see it.** It follows the rest of the Subscription section, which at launch shows such sessions only "Verify this session first" (T13, Product P53–P55). See §3 C3.
- **Nowhere else:**
  - no prompt after a trade, a sync or a milestone;
  - no link from the paywall;
  - no push;
  - not on the web or the extension, which have no in-app purchase (T19: no purchase UI on the web).
- A tip is something a user goes looking for. Nagging for one would undercut both the subscription and design tenet Q33.

### The screen (exists; `TipJarScreen.tsx`)

- **Layout:**
  - the header "Support Fleeced";
  - a one-paragraph lede that already says "A tip unlocks nothing";
  - one card per tip, showing StoreKit's localized price;
  - a close control.
- **No Restore button and no renewal disclosure.** Consumables can't be restored and carry no subscription terms (`:32-34`).
- **The thank-you state** (`:167-178`): a check mark, "Thank you.", one body line and **Done**. The app **doesn't refresh entitlements** after a tip (`:130-131`). Repeat tips are allowed.
- **The other states:**
  - cancel on Apple's sheet: silent;
  - a failed purchase: "That didn't go through. You haven't been charged.";
  - a product that didn't load: an inline error;
  - no tips offered: "Tips aren't available right now."
  - The copy for these goes to marketing in §2.

### App Review rules

- **3.1.1:** "Apps may use in-app purchase currencies to enable customers to 'tip' the developer or digital content providers in the app." The tips are therefore in-app purchases, type **Consumable**.
- **Never imply a benefit.**
  - No "unlock", "get", "perks", "supporter" badge, "priority" or "early access".
  - The screen, Apple's sheet (display name and description) and the review notes all say a tip unlocks nothing.
  - The server enforces the same rule: `is_tip_product` → store the event, grant nothing (`entitlements.py:363-371, :523`; tests at `test_entitlements.py:594-627`, refund included).
- **Never "donate", "donation", "charity" or "fundraiser".** 3.2.2(iv) bars apps that aren't approved nonprofits from collecting funds for charities. A tip to the developer is allowed, but donation wording invites the wrong reading.
- **2.5.19 (no dormant features):** at knob 0 the row is hidden and the route stays registered, the same posture #526 shipped for the 11-06 binary.
- **Review notes, one per tip:**

  > Optional tip to support the developer. Consumable. It unlocks no content, features or
  > benefits, and the app grants nothing on purchase. To find it: sign in first (Sign in with
  > Apple works), then Settings › Subscription › Support Fleeced. Demo mode shows no purchase flow.

  The sign-in line matches the purchases note in `docs/business/ops/2026-11-18-launch.md`. Demo mode gets no
  RevenueCat at all, and #576 serves it no tips.

## 2. Copy (marketing) and legal checks: routed through head-product

**Marketing:** final strings by **11-03**, so they make the 11-06 binary. The App Store Connect strings are needed by **11-05**.

| # | Where | Today | Ask |
|---|---|---|---|
| 1 | Settings row (hub + legacy) | title "Support Fleeced", preview "Tip jar" | Keep or replace |
| 2 | TipJar header | "Support Fleeced" | Keep or replace |
| 3 | Lede (`TipJarScreen.tsx:182-184`) | "Fleeced is built by one person. If it's earned a spot in your league routine, a tip helps keep it going. A tip unlocks nothing — it's just a thank-you." | Keep the "unlocks nothing" meaning. **The operator should confirm "built by one person"** |
| 4 | Thank-you (`:171-175`) | "Thank you." / "Tips keep Fleeced independent — every one goes straight into building the tool." | "Every one goes straight into" is a factual claim: Apple keeps 15% and taxes apply. Soften it (legal checks) |
| 5 | Product didn't load (`:117`, `:125`) | "Tips aren't available on this build yet. Thanks for the thought!" | "On this build yet" reads as a beta in production. Needs a production line |
| 6 | Failure (`:137`) / none offered (`:195`) | "That didn't go through. You haven't been charged." / "Tips aren't available right now." | Keep or replace |
| 7 | App Store Connect display names ×3 (≤30) and the description (≤45, one shared or one per tip) | defaults in §1 | Final strings; no benefit or donation words |
| 8 | Accessibility label (`:204`) | "Tip $1.99" | Keep or replace |

**Legal:**

- **Terms** (#373 @ `41aef26c`) have no tip clause. legal-lead decides whether they need one. A suggested clause: tips are optional one-time payments through Apple, buy no features, content or benefits, and are refunded only through Apple.
- **Privacy** (#373): check that "Subscriptions and purchases" (`privacy.html:153`) and the RevenueCat line (`:226`) cover tips. The wording starts "If you subscribe".
- Check the claims in rows 3–4 above.

## 3. Eng (head-eng → engagement-eng)

**Server (no binary):**

- **S1:** `GET /api/paywall/config` returns `tips: _PAYWALL_TIPS` when `model_config` `paywall_tips_enabled` = 1 **and** the platform is `ios`. Otherwise it returns `[]`.
  - The default is 0. Use the same read pattern as `paywall_enforce_enabled` (#394).
  - Update `test_paywall_config.py:209` (it pins `[]`) and the comment at `server.py:36873-36878` and `:36926-36930`.
  - Update `docs/api-reference.md` (`/api/paywall/config`) and `docs/config-reference.md` (the new key).
  - It can deploy at any time with the knob at 0.
- **No entitlement change.** `is_tip_product` already covers storage, no grant, and refunds.

**Client (must make the 11-06 binary):**

- **C1: the Settings row must show for a user who has never opened the paywall.** Today it wouldn't:
  - `useTipsOffered` (`useTipsOffered.ts:18-25`) subscribes to `['paywall-config','ios']` with `enabled: false`, so it never fetches;
  - the only fetchers are `PaywallScreen.tsx:198` and `TipJarScreen.tsx:67`;
  - the key isn't persisted (`App.tsx:69` `PERSIST_KEYS`), and `gcTime` is 30 min (`queryClient.ts:26`);
  - so with tips served, the row would appear only within 30 minutes of opening the paywall, and App Review might never see it.
  - **The ask:** keep that query warm from an always-mounted place while `monetize.paywall` is on (for example, a `useQuery` with `enabled: paywallOn` under `Main`). That keeps the Settings hub's zero-network rule intact (`SettingsHubScreen.tsx:100-101`). Eng chooses the place.
  - `check-tipjar.js` §8c pins `enabled: false` and needs to pin the new shape.
- **C2:** the copy from §2.
- **C3:** the tip row hides on unverified sessions along with the rest of the Subscription section (T13). On main the section has no verify condition (`SettingsHubScreen.tsx:302-328`).
  - **#495 (Paywall M3) carries it:** the verified-only Settings tip row, plus TipJar's `customerInfoApplies` purchase guard.
  - **Builds:** S1 is #576. It also serves no tips to unverified or demo sessions, as defence in depth. C1 is #575, which also clears the cached config whenever a session stops being verified.
  - **Merge order:** #569 (this plan) merges first or alongside #576, which links to it.
- **No change to the purchase path.** `getTipProducts` → `P.getProducts(ids, NON_SUBSCRIPTION)` and `purchaseTip` → `purchaseStoreProduct` (`purchases.ts`) work with real products by id, with **no offering needed**. That matches RevenueCat's guidance for consumables: an entitlement is optional, and fetching products directly is supported.

**Analytics (analytics-lead; server-side reads, no binary):**

- **TipJar reuses the paywall events:**
  - `paywall_viewed {source: 'tip_jar'}` (`TipJarScreen.tsx:107`);
  - `paywall_purchase_initiated / _completed / _failed {product_id: 'ftf_tip_*', source}` (`:115-135`). Here `source` is the route param `settings`, **not** `tip_jar`.
- **The rule:** every paywall-conversion read (K0–K3) excludes views with `source = 'tip_jar'` and purchases whose `product_id` starts `ftf_tip_`. Recommendation: no new events.
- **fin-pnl:** tips arrive as `NON_RENEWING_PURCHASE` rows in the ledger. Report tip revenue apart from subscription revenue.

## 4. Operator setup (for app-manager's `leads/app-manager-monetization-setup.md`)

Written for the setup doc's format (📱 phone / 💻 computer, `[verify on screen]` where Apple's or RevenueCat's docs don't confirm the wording).

- **Keys:** this needs no new secret. The only new key is `paywall_tips_enabled`, a `model_config` setting that release-lead sets. `EXPO_PUBLIC_REVENUECAT_IOS_KEY` (step 6k) already covers tips.
- **Replaces step 4c** ("Don't add them to any submission").

### Tip jar (💻, about 20 min, by 11-05; needs 1a, the Paid Apps agreement)

| # | Do | Set to | ✅ / ❌ |
|---|---|---|---|
| TJ1 | App Store Connect → **Apps** → Fleeced → **Monetization** → **In-App Purchases** → **+** | Type **Consumable**. Reference Name **`Tip 1.99`**. Product ID **`ftf_tip_199`**, exactly: **it can't be changed or reused later** → **Create** | |
| TJ2 | On it: **Price Schedule** → add a price **[verify on screen]** | United States **$1.99**; let Apple fill the other countries | |
| TJ3 | **Availability** | The same countries as the app | |
| TJ4 | **App Store Localization** → English (U.S.) | Display Name and Description from marketing (defaults: **Small Tip** / **A one-time tip. It unlocks nothing.**) | |
| TJ5 | **Review Information** → Review Notes | Paste the review note in plan §1 ("Optional tip to support the developer…"). The screenshot comes in TJ10 | |
| TJ6 | **Tax category** **[verify on screen]** | Leave Apple's default | |
| TJ7 | Repeat TJ1–TJ6 | **`Tip 4.99`** / **`ftf_tip_499`** / **$4.99** / **Medium Tip**, then **`Tip 9.99`** / **`ftf_tip_999`** / **$9.99** / **Large Tip** | |
| TJ8 | RevenueCat → **Products** | Add, or import, `ftf_tip_199`, `ftf_tip_499` and `ftf_tip_999`. **Don't attach them to the `pro` entitlement (6e) and don't put them in the offering (6f).** The app fetches tips by id, and a tip attached to `pro` would grant Pro | |
| TJ9 | `release-lead`'s session. **Only when both are true:** (1) eng says S1 (#576) is deployed; (2) **#495's tip guard** (the verified-only tip row, plus TipJar's purchase guard) is merged **and in the build under test or review**. Without #495, demo and unverified sessions would see a purchase flow, against the App Review note | Say: `The three tip products exist. Set paywall_tips_enabled to 1.` release-lead checks (2) before setting it | |
| TJ10 | 📱 **11-07**, on the gated TestFlight build | Settings › Subscription › **Support Fleeced** → screenshot the tip jar → upload it as **each** tip's Review Screenshot. Each tip shows **Ready to Submit** **[verify on screen]** | |
| TJ11 | **11-10**, with step 5 | On each tip: **Add for Review** → iOS → the **11-10 version**. Step 5b's list becomes: the version, the group, `ftf_pro_monthly`, `ftf_pro_annual`, `ftf_tip_199`, `ftf_tip_499`, `ftf_tip_999` | |

**If a tip isn't Ready to Submit by 11-10:**
1. Leave all three out of the submission.
2. Tell head-product.
3. release-lead sets `paywall_tips_enabled` back to 0, which hides the row.

Apple takes an app's first consumable only with a new app version, so tips then wait for the next one.

**If App Review objects only to the tips:** remove them from the submission, resubmit, and set the knob to 0. The subscriptions and the launch go ahead.

**What the knob does and doesn't do:**
- **At 1, it's live whenever the paywall is.** Once `monetize.paywall` is on, tips are served at once. So set the knob only under TJ9's two conditions.
- **At 0, it hides the row on the next config read.** It doesn't close a TipJar screen that's already open.
- **The hard stop** is taking the three products off sale in App Store Connect (each tip's **Availability** → remove from sale **[verify on screen]**). Use it only if a tip must stop selling immediately, because putting them back needs Apple again.

### Checks (add to step 8, 11-07 to 11-09, on the gated build, after TJ9)

| # | Device | Account | Do | You should see | ✅ / ❌ |
|---|---|---|---|---|---|
| **T21** | 📱 | A verified account, freshly launched, **paywall not opened** | Settings › Subscription | **Support Fleeced** is there. It opens three prices from StoreKit | |
| **T22** | 📱 | A **gated** account | Tap **$1.99** → Apple's sandbox sheet → buy | The thank-you screen. Settings › Subscription is **unchanged**, and Find a trade still opens the paywall: **a tip unlocks nothing** | |
| **T23** | 📱 | Same | Tap a tip, then **Cancel** on Apple's sheet | Back on the jar, with no error | |
| **T24** | 📱 + `release-lead` | Same | Say `Set paywall_tips_enabled to 0.` → relaunch → Settings. Then `Set it back to 1.` → relaunch | At **0**: no tip row. At **1**: the row is back | |
| **T25** | 📱 | Same | Read the jar and Apple's purchase sheet | No "unlock", "get", "perk", "donate" or "donation"; the sheet's name matches TJ4 | |
| **T26** | 📱 | An **unverified** session (T13's), then **demo mode** | Settings | **No** tip row in either, same as T13 | |

## 5. Timeline

| By | What | Who |
|---|---|---|
| 11-03 | Copy (§2) final; legal's terms and privacy call | marketing-lead, legal-lead (via head-product) |
| 11-04 | S1 merged; C1 + C2 PRs green | engagement-eng (via head-eng); release-lead merges |
| 11-05 | TJ1–TJ8 | operator |
| 11-06 | Release binary built with C1 + C2 | distribution-lead |
| 11-07 | TJ9 (knob 1), TJ10 (screenshots), T21–T26 | operator, release-lead |
| 11-10 | TJ11 with the submission | operator |

## 6. Risks

- **First-review surface.** Three more in-app purchases. Mitigated by the remove-and-resubmit path and the knob, so tips can't hold the launch.
- **#495's tip guard misses the binary.** Then TJ9's condition (2) fails: keep the knob at 0, and don't submit tips at 11-10.
- **C1 misses the 11-06 binary.** Then the row appears only after opening the paywall, so a reviewer may not find the tips. **In that case don't submit tips at 11-10.** Keep the knob at 0 and ship them with the next version.
- **Paywall metrics polluted by tips** if analytics-lead's read filters aren't in place by the first K read.
- **Copy claims** ("built by one person", "every one goes straight into…"): legal checks them before 11-03.

## Sources

- **Code**, `origin/main` `245f5e60`:
  - `mobile/src/screens/TipJarScreen.tsx`, `mobile/src/state/useTipsOffered.ts`, `mobile/src/api/purchases.ts` (getTipProducts, purchaseTip);
  - `mobile/src/screens/settings/SettingsHubScreen.tsx:96-110, :286-328`, `mobile/App.tsx:69`, `mobile/src/state/queryClient.ts:26`;
  - `backend/server.py:36873-36931`, `backend/entitlements.py:363-371, :523`;
  - `backend/tests/test_paywall_config.py:209-222`, `backend/tests/test_entitlements.py:594-627`;
  - `mobile/tests/check-tipjar.js` §8c, `backend/analytics_taxonomy.py:715-716, :1785-1787`.
- **Apple, read 2026-10-31:**
  - [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/) 3.1.1 (tipping), 3.2.2(iv) (charitable fundraising);
  - [In-App Purchase information](https://developer.apple.com/help/app-store-connect/reference/in-app-purchases-and-subscriptions/in-app-purchase-information) (field limits, product id rules);
  - [Create consumable or non-consumable In-App Purchases](https://developer.apple.com/help/app-store-connect/manage-in-app-purchases/create-consumable-or-non-consumable-in-app-purchases);
  - [Submit an In-App Purchase](https://developer.apple.com/help/app-store-connect/manage-submissions-to-app-review/submit-an-in-app-purchase) (the first consumable rides a new app version).
- **RevenueCat:**
  - [Non-subscriptions](https://www.revenuecat.com/docs/platform-resources/non-subscriptions.md) (consumables need no entitlement and are tracked for revenue);
  - [community: fetch products without offerings](https://community.revenuecat.com/sdks-51/fetch-products-without-offerings-2119).
- **Terms and privacy:** #373 @ `41aef26c`.
