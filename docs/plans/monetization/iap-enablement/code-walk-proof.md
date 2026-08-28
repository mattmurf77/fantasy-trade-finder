# Code-walk proof — IAP enablement (mobile)

**Date:** 2026-08-28
**Scope block:** [scope.md](scope.md) §3 "Evidence scope"
**Why this document exists:** [D-056](../../../../living-memory/DECISIONS.md) (2026-08-15) retired
Maestro and the simulator entirely. Where a sim capture used to go, the evidence is now a written,
file:line-cited trace through the shipped code. This is that trace for the purchase path. The
automated half is [`mobile/tests/check-paywall.js`](../../../../mobile/tests/check-paywall.js)
(11 assertions, all passing); the runtime half is
[sandbox-test-checklist.md](sandbox-test-checklist.md), which the operator runs once the Paid Apps
agreement is active.

**Line numbers are as of this commit.** They are citations, not contracts — re-derive them with
`git grep -n` if the files have moved since.

**Everything below is DARK.** `monetize.paywall` and `monetize.entitlements` are both `false` in
`config/features.json`, neither is in the mobile flag store's `LAUNCHED_FLAG_DEFAULTS`
(`mobile/src/state/useFeatureFlags.ts:45–89`), so every gate in this trace resolves closed today.
The trace describes what happens **after** the operator flips them per runbook B9.

---

## 0. The claim this document proves

> A device receipt can make the UI *look* unlocked for a few seconds. It can never make the user
> Pro. `backend/entitlements.check_pro()` is the only thing that decides, it reads rows the
> RevenueCat webhook wrote, and every client value is overwritten by the next
> `GET /api/me/entitlements`.

Each step below names the line that keeps that true.

---

## 1. Boot / sign-in → `Purchases.configure` with the working key

The RevenueCat app-user-id **must** be the session working key — the same string
`backend/entitlements.resolve_user()` resolves (`backend/entitlements.py:62`). If it were anything
else, a webhook would arrive naming an app-user-id no row in `entitlements` is keyed on, and a real
purchase would never become a real entitlement.

There are exactly two moments that key becomes known, and both call `initPurchases`:

| Moment | Site |
|---|---|
| Restored session (cold launch with a persisted user) | `mobile/src/state/useSession.ts:332` — end of `bootstrap()` (`:266`), right after `set({user, …})` |
| Fresh sign-in / account switch | `mobile/src/state/useSession.ts:408` — inside `setUser()` (`:389`), beside the existing `sentrySetUser` call |

`initPurchases` (`mobile/src/api/purchases.ts:124`):

- `sdk()` (`:59`) returns `null` immediately when `API_KEY` is falsy (`:60`), and `API_KEY` is
  `process.env.EXPO_PUBLIC_REVENUECAT_IOS_KEY || ''` (`:50`). **No key ⇒ the SDK module is never
  even `require`d**, so a build without the key cannot execute a line of RevenueCat code.
- First call configures once: `P.configure({ apiKey: API_KEY, appUserID: userId })` (`:129`).
- A later call with a *different* key aliases instead: `await P.logIn(userId)` (`:138`).
- The whole body is inside a `try` whose `catch` leaves `_configured` false — the Expo Go path,
  where the native module is absent and the SDK drops into Preview API Mode. Every other export
  then no-ops.
- **There is no `logOut` call anywhere in the file** — pinned by `check-paywall.js` §7b
  (`noLogOut`). `useSession.setUser(null)` on sign-out deliberately does nothing here
  (`useSession.ts:398–408` — the comment block above the `if (u?.user_id)` guard): logging out would re-anonymize the RevenueCat identity, and
  leaving FTF is not leaving the Apple ID that owns the subscription.

`P.configure` is synchronous and sits before the first `await`, so `_configured` flips during the
call — which is what lets step 2's listener bind on the same tick.

## 2. Boot → entitlements hydrate, fetch, and listener

`mobile/App.tsx:135` calls `initEntitlements()` from the boot `.finally`, **detached**: nothing on
the first paint reads `pro`, so it must not join the splash gate (`mobile/CLAUDE.md` § "App.tsx boot
contract"). `bootstrap()` (`App.tsx:95`) has already resolved by then, so a restored session's
working key has reached `configure`.

`initEntitlements` (`mobile/src/state/useEntitlements.ts:139`) does three things:

1. `loadCached()` (`:77`) — AsyncStorage hydrate under the **72 h offline grace** (`GRACE_MS`,
   `:40`; evaluated at `:83`). Past the window the cached grant is discarded and the UI reads free.
   Deliberately not "keep the last value": an indefinitely-honored cache is a free subscription for
   anyone who stays offline.
2. `refresh()` (`:100`) — the server read. Returns early without a session token (`:103`), then
   `await getEntitlements()` (`:105`) → `GET /api/me/entitlements`
   (`mobile/src/api/billing.ts`, route at `backend/server.py:26654`).
3. `setOnPurchasesReady(...)` (`:152`) — binds the CustomerInfo listener at the moment `configure`
   succeeds. It goes through the callback seam (`purchases.ts:89`, fired at `:132`) rather than
   running inline because `configure` may happen at boot *or* minutes later at sign-in, and
   `onCustomerInfoChange` returns a silent no-op unsubscribe when the SDK is not configured
   (`purchases.ts:191–194`). Binding early would bind nothing.

Foreground resume re-reads the server: `mobile/App.tsx:220`,
`void useEntitlements.getState().refresh()` inside the existing AppState `active` branch. This is
what makes the server authoritative in practice and not only in principle — a purchase, lapse,
renewal or refund that happened while the app was backgrounded is reflected on the next resume.

## 3. Entry point → the paywall modal

One entry exists in this build. `monetize.paywall` gates the **row**, never the route:

- Hub (live surface; `account.settings_hub` is `true` in `config/features.json`):
  `mobile/src/screens/settings/SettingsHubScreen.tsx:95` reads the flag, `:290` gates the block,
  `:296` is `testID="settings-pro-row"`, and the row navigates
  `('Paywall', { source: 'settings' })`. Status preview is `loaded ? (pro ? 'Pro' : 'Free') : null`
  — the hub's never-guess rule (its header §6): before any source has answered we print nothing,
  because "Free" would be wrong for every subscriber who opened Settings quickly.
- Flat list (the `account.settings_hub`-off twin): `mobile/src/screens/SettingsScreen.tsx:111`
  (flag), `:1060` (`proSection`), `:1066` (same testID). Carried on both because exactly one of the
  two ever mounts, and a row on only one makes the paywall unreachable in the other flag state.

The route itself: `mobile/src/navigation/RootNav.tsx:175` (`Paywall: { source: string }`) and
`:709` (`<Stack.Screen name="Paywall" … presentation: 'modal', headerShown: false />`), registered
**unconditionally** like every other flag-gated route — gating the registration would unmount an
in-flight push the moment `revalidateFlags` lands. `headerShown:false` because the screen draws its
own header with the explicit ✕ that `docs/design/components.md` § "Sheets, modals, menus" requires
of a modal presentation.

## 4. Paywall mount → two independent guards, then two reads

`mobile/src/screens/PaywallScreen.tsx`:

- **Guard A (client flag):** `:111` `useFlag('monetize.paywall')`; the effect at `:127–129` pops
  immediately when it is false, and `:262` `if (!paywallOn) return null` renders nothing. Hooks all
  run before that return, so the early exit is rules-of-hooks-safe.
- **Guard B (server flag):** `:155` — `config.enabled === false` also dismisses. That is exactly
  what `GET /api/paywall/config` answers while `monetize.paywall` is off
  (`backend/server.py:26713–26714`). **The server's answer outranks this device's flag map**, so a
  stale or experiment-overlaid client cannot sell a product the server says is not for sale.
- `configQuery` (`:131`) → `getPaywallConfig('ios')` → `backend/server.py:26694`. Contract matches
  the shipped route field-for-field: `enabled` / `platform` / `pages` / `products` /
  `trial_eligible` / `dismissible`, products keyed `product_id, period, display_price,
  per_month_equiv, trial_days, hero, badge` (`backend/server.py:26682–26688`).
- `offeringsQuery` (`:141`) → `getOfferings()` (`purchases.ts:150`), which **resolves `null`**
  rather than throwing when purchases are unavailable (`:152`, `:156`). A missing SDK therefore
  degrades the screen to server prices instead of an error state.
- `paywall_viewed {source, platform:'ios'}` fires at `:192`, gated on the flag.

## 5. Render → what a reviewer sees before they can pay

`plans` (`:161`) joins the two reads: for each server product it finds the StoreKit package whose
`product.identifier` matches `product_id`, then prefers the localized StoreKit strings and falls
back to the server's:

- title — `planTitle()`, `pkg.product.title` else the period name;
- price+period — `priceLine()`, `pkg.product.priceString` else `display_price`, plus the period
  suffix (`/year`, `/month`);
- trial — `` `${trial_days} days free, then ${price}` ``, only when `trial_eligible !== false`.

Guideline 3.1.2 elements, all on this one screen, all **outside** the loading branch so a failed
fetch cannot strip them:

| Requirement | Line |
|---|---|
| Plan name | `:344` (plan card title) |
| Price + period | `:355` |
| Trial terms | `:361` |
| Auto-renew + how to cancel | `AUTO_RENEW_COPY` at `:58`, rendered at `:378`, above the CTA |
| Restore Purchases | `:391` (`testID="paywall-restore"`) |
| Privacy Policy | `:400`, opens `/privacy` (`:403`) |
| Terms of Use | `:414`, opens `/terms` (`:417`) |
| Dismiss affordance | `:276` (`testID="paywall-close"`), rendered when `dismissible` |

Legal links use `getBaseUrl()` (`openLegal`, `:255`): the backend origin serves the web app at `/`
(`mobile/src/api/client.ts` `getBaseUrl` comment), so there is no second origin constant to drift
when the deploy target moves.

**Chalkline:** ink-1 plan cards with a `--line` hairline and `radii.md`; selection is a border
change to ice, never a lift or shadow; the CTA is the screen's single ice fill; the "Best value"
chip is a flare **border** because it is informational, never an action (ADR-005); headers are
Barlow Condensed via `ChalkText variant="heading"/"display"`. No emoji, no gradient, no blur, no
radius above 8.

**#188:** this is a modal, so it deliberately mounts no `FeedbackFAB` — asserted as an absence by
`check-paywall.js` §6.

## 6. Purchase → optimistic cache → server refresh

`onPurchase` (`:197`):

1. `paywall_purchase_initiated {product_id, source}`.
2. No StoreKit package behind the row (offerings never loaded) ⇒ an honest "not available" message
   and a `paywall_purchase_failed {user_cancelled:false}`; nothing pretends to charge.
3. `await purchasePackage(selected.pkg)` (`:212`) → `purchases.ts:166`. This wrapper returns `null`
   only when purchases are unavailable; a real StoreKit failure **throws**, which is what lets the
   caller separate the two.
4. On success: `paywall_purchase_completed` (`:218`), then
   `noteCustomerInfo(hasProEntitlement(result.customerInfo))` (`:221`) — **the optimistic step** —
   then `await refreshEntitlements()` (`:222`) and dismiss.
5. On rejection: `isUserCancelled(err)` (`:225`, defined `purchases.ts:224`). A cancel is a
   decision, not a failure: it fires `paywall_purchase_failed {user_cancelled:true}` and shows **no
   error**. A genuine failure gets the inline Chalkline error box.

**Why the optimistic step is safe.** `noteCustomerInfo` (`useEntitlements.ts:124`) is
raising-only — `if (proActive && !get().pro)` — and its body contains **no `setItem`**. So:

- a device receipt can never *revoke* (an SDK cache miss must not look like a refund — only
  `refresh()` can lower `pro`);
- a device receipt can never *persist* (a client-derived `true` must not survive a relaunch and
  then impersonate a server answer inside the 72 h grace window);
- `refresh()` (`:100`) sets `optimistic: false` alongside the server's value, in both directions.

`check-paywall.js` §10 pins all three properties by parsing the `noteCustomerInfo` body.

## 7. Server-authoritative gating — where the decision actually lives

The purchase reaches the server through RevenueCat's webhook, not through the client:
`backend/server.py:26807` (`/api/billing/revenuecat/webhook`) → the projector in
`backend/entitlements.py` (`_product_mapping` at `:363`) → rows in `entitlements`.

The decision itself:

- `backend/entitlements.py:251` — `check_pro(user_id, route, logger)`.
- `:257` — `if not is_enabled("monetize.entitlements"): return True` — flag off is **today's
  behavior**, the deploy-free kill switch.
- `:259` — `has_pro = get_entitlements(user_id)["pro"]`, read from the rows.
- `:260–264` — with `monetize.paywall` still off, observe mode: log `ENTITLE-OBSERVE` and return
  `True`.
- `:265` — enforcing: return the resolution result.
- `get_entitlements` (`:226`) filters on read-time expiry (`_active_rows`, ending `:224`), so an
  elapsed `expires_at` locks without waiting for the hygiene cron.

`GET /api/me/entitlements` (`backend/server.py:26654`) serves exactly that resolution plus
`enforcing`. **The client never computes `pro`; it renders what this returns.** The gate decorator
`_require_pro` (`:26638`) calls `check_pro` directly — nothing on the device is consulted, so a
tampered client learns nothing and gets nothing.

## 8. Restore

`onRestore` (`:236`): `await restorePurchases()` (`:241`, wrapper at `purchases.ts:178`) →
`hasProEntitlement(info)` → `paywall_restore {restored}` (`:243`) → optimistic raise when true →
`await refreshEntitlements()` (`:247`) **unconditionally**. The unconditional refresh matters: a
restore that finds nothing on *this* Apple ID can still be a user whose grant lives on their account
row (a manual grant, or a purchase made under a different working key that the webhook's alias
reconciliation already merged). Only after the server has been asked does the screen say "No
subscription found on this Apple ID."

## 9. The no-key / Expo Go path, end to end

With `EXPO_PUBLIC_REVENUECAT_IOS_KEY` unset — which is **every build until the operator adds it to
EAS env**:

| Call | Result |
|---|---|
| `initPurchases` (`:124`) | `sdk()` returns null at `:60`; returns immediately. Nothing configured, nothing required. |
| `setOnPurchasesReady` (`:89`) | Stored; never fired, because `_notifyReady` only runs after a successful `configure`. |
| `onCustomerInfoChange` (`:191`) | Returns a no-op unsubscribe. |
| `getOfferings` (`:150`) | `null` ⇒ the paywall renders server `display_price` strings. |
| `purchasePackage` (`:166`) | `null` ⇒ the honest "not available on this build yet" message. |
| `restorePurchases` (`:178`) | `null` ⇒ `restored:false`. |
| `useEntitlements` | Unaffected — it reads the server, which knows nothing about the SDK. |

So the app behaves exactly as it does today, with the additional fact that `monetize.paywall` is
false, so none of it is reachable at all.

---

## What this proof does NOT cover (honest label, G-035)

This is a proof of **wiring and shape**, not of runtime behavior. It cannot show that StoreKit
presents the sheet, that RevenueCat delivers the webhook, that Render returns 200, or that the
entitlement row lands. Those are exactly the items in
[sandbox-test-checklist.md](sandbox-test-checklist.md), and they cannot be exercised at all until
the Paid Apps agreement is active.
