// purchases.ts — the ONE module in this app that touches react-native-purchases.
//
// Everything else (PaywallScreen, state/useEntitlements, useSession's identity
// bridge) talks to the wrappers below, so the SDK has exactly one seam. That
// is what makes the two hard rules cheap to keep:
//
//   1. FAIL-SAFE. Without `EXPO_PUBLIC_REVENUECAT_IOS_KEY` — and in Expo Go,
//      where the native module is absent and the SDK falls back to its Preview
//      API Mode — every export here no-ops (void / null / a no-op unsubscribe).
//      The app must behave EXACTLY as it does today: no crash, no thrown
//      promise a caller forgot to catch, no half-configured SDK. The paywall
//      is dark behind `monetize.paywall` anyway; this guarantees the module is
//      inert even if someone flips it before the key exists.
//   2. NEVER AUTHORITATIVE. Nothing here decides whether a user is Pro. The
//      server does, via `backend/entitlements.check_pro()` reading rows the
//      RevenueCat webhook wrote. CustomerInfo from this module is a UI cache
//      only (see state/useEntitlements.ts).
//
// The SDK is loaded with a lazy `require` rather than a top-level import, the
// same pattern client.ts uses for events.ts: with no key configured the module
// is never even evaluated, so the fail-safe path costs nothing at boot.
//
// Native code ⇒ the first build carrying this must be a full EAS build, not an
// OTA update (living-memory/DEPENDENCIES.md 2026-08-28). No Expo config plugin
// is required — the native module lands via prebuild/autolinking.

import type {
  CustomerInfo,
  MakePurchaseResult,
  PurchasesOfferings,
  PurchasesPackage,
  PurchasesStoreProduct,
} from 'react-native-purchases';

export type { CustomerInfo, PurchasesOfferings, PurchasesPackage, PurchasesStoreProduct };

/** Static side of the SDK's default export, as a type only — `import type`
 *  is erased at compile time, so this costs no runtime require. */
type PurchasesSdk = typeof import('react-native-purchases').default;

/** RevenueCat entitlement identifier. Must equal the backend's entitlement
 *  string (`backend/entitlements.ENTITLEMENTS`) and the RevenueCat dashboard's
 *  entitlement id, or the optimistic UI cache and the server disagree.
 *  Cross-client value — see docs/cross-client-invariants.md. */
export const PRO_ENTITLEMENT_ID = 'pro';

/** Publishable Apple SDK key, injected at BUILD time by EAS.
 *  `process.env.EXPO_PUBLIC_*` is inlined by babel-preset-expo, so it must be
 *  written as a full static member expression (same contract sentry.ts relies
 *  on for EXPO_PUBLIC_SENTRY_DSN). Absent ⇒ this whole module is inert. */
const API_KEY = process.env.EXPO_PUBLIC_REVENUECAT_IOS_KEY || '';

let _sdk: PurchasesSdk | null = null;
let _sdkLoadFailed = false;
let _configured = false;
let _configuredUserId: string | null = null;

// ── Identity-ready gate (#393 M1, D12) ──────────────────────────────────────
// The RevenueCat webhook grants `pro` to RevenueCat's appUserID, and the
// server checks the SESSION's user_id. A purchase made while RevenueCat
// still holds the previous identity (a `logIn` in flight after an account
// switch) would grant the wrong user, and a reviewer who bought would stay
// gated: a rejection. So purchase and restore wait until RevenueCat's
// identity is confirmed to be the caller's current session user_id, and the
// paywall shows a pending CTA meanwhile. `_identityUserId` is set only once
// `configure` or `logIn` for that id has completed; `_identitySeq` makes a
// slow, superseded `logIn` unable to claim readiness for the wrong user.
let _identityUserId: string | null = null;
let _identitySeq = 0;
const _identityListeners = new Set<() => void>();

function _setIdentity(userId: string | null): void {
  _identityUserId = userId;
  for (const fn of _identityListeners) {
    try {
      fn();
    } catch {
      /* a listener never breaks the identity bridge */
    }
  }
}

/** True once RevenueCat's identity is confirmed to be `userId`. */
export function isIdentityReady(userId: string | null | undefined): boolean {
  return _configured && !!userId && _identityUserId === userId;
}

/** Re-render hook for the pending CTA. Returns an unsubscribe. */
export function onIdentityChange(cb: () => void): () => void {
  _identityListeners.add(cb);
  return () => {
    _identityListeners.delete(cb);
  };
}

/** Resolves once RevenueCat's identity is `userId`; rejects after `timeoutMs`
 *  (the session changed under the caller, or a `logIn` never completed). */
export function whenIdentityReady(userId: string, timeoutMs = 15_000): Promise<void> {
  if (isIdentityReady(userId)) return Promise.resolve();
  return new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => {
      unsub();
      reject(new PurchaseIdentityError());
    }, timeoutMs);
    const unsub = onIdentityChange(() => {
      if (!isIdentityReady(userId)) return;
      clearTimeout(timer);
      unsub();
      resolve();
    });
  });
}

/** Thrown by purchase / restore when RevenueCat's identity isn't (or can't be
 *  confirmed to be) the current session user. Nothing reached Apple's sheet. */
export class PurchaseIdentityError extends Error {
  constructor() {
    super('purchase_identity_not_ready');
    this.name = 'PurchaseIdentityError';
  }
}

async function _assertIdentity(P: PurchasesSdk, sessionUserId: string): Promise<void> {
  if (!sessionUserId) throw new PurchaseIdentityError();
  await whenIdentityReady(sessionUserId);
  // Belt and braces: ask the SDK itself, right before Apple's sheet.
  let current: string | null = null;
  try {
    current = await P.getAppUserID();
  } catch {
    current = null;
  }
  if (current !== sessionUserId) throw new PurchaseIdentityError();
}

/** Lazy SDK handle. Returns null when there is no key, or when requiring the
 *  package throws (a bare/Expo Go runtime without the native module). */
function sdk(): PurchasesSdk | null {
  if (!API_KEY || _sdkLoadFailed) return null;
  if (_sdk) return _sdk;
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const mod = require('react-native-purchases') as { default: PurchasesSdk };
    _sdk = mod.default;
    return _sdk;
  } catch {
    _sdkLoadFailed = true;
    return null;
  }
}

/** True when a key exists AND `configure` has succeeded. The paywall uses this
 *  to decide whether to offer store-priced plans or fall back to the server's
 *  `display_price` strings — never to decide entitlement. */
export function purchasesReady(): boolean {
  return _configured;
}

// ── "purchases became usable" listener ──────────────────────────────────────
// `configure` happens whenever the session's working key first exists, which
// may be at boot (restored session) or minutes later (fresh sign-in). The
// entitlements store needs to attach its CustomerInfo listener at THAT moment,
// whichever it is — attaching earlier is a silent no-op (see
// onCustomerInfoChange below). Registered as a callback rather than an import
// so this module keeps its no-state-dependencies posture, exactly like
// client.ts's setOnVerificationRequired / setOnSessionExpired.
let _onReady: (() => void) | null = null;
export function setOnPurchasesReady(fn: (() => void) | null): void {
  _onReady = fn;
  // Late registration must not miss an already-configured SDK.
  if (_configured && fn) {
    try {
      fn();
    } catch {
      /* listener errors are never the SDK's problem */
    }
  }
}

function _notifyReady(): void {
  if (!_onReady) return;
  try {
    _onReady();
  } catch {
    /* same */
  }
}

/** Configure once, then bridge identity on every later sign-in.
 *
 *  `userId` is the session WORKING KEY (`useSession.SavedUser.user_id` — the
 *  Sleeper user id, or the synthetic `acct_<account_id>` for account-only
 *  users). It is the same key `backend/entitlements` resolves against, which
 *  is what lets a RevenueCat webhook land on the right rows.
 *
 *  Deliberately no `Purchases.logOut()` anywhere in this module, including on
 *  sign-out: RevenueCat's guidance is that logOut mints a fresh anonymous
 *  app-user-id whose purchases then need aliasing back, and this app's next
 *  sign-in always calls logIn with a real working key anyway. Signing out of
 *  FTF is not signing out of the App Store account that owns the subscription.
 *
 *  Never throws — a purchases failure must not be able to break sign-in. */
export async function initPurchases(userId: string): Promise<void> {
  const P = sdk();
  if (!P || !userId) return;
  const seq = ++_identitySeq;
  try {
    if (!_configured) {
      P.configure({ apiKey: API_KEY, appUserID: userId });
      _configured = true;
      _configuredUserId = userId;
      _setIdentity(userId);
      _notifyReady();
      return;
    }
    // Already configured this launch — a different working key means the user
    // switched accounts, so alias the RevenueCat identity across.
    if (_configuredUserId !== userId) {
      // Not ready for anyone until this logIn lands: purchase/restore wait.
      _setIdentity(null);
      await P.logIn(userId);
      _configuredUserId = userId;
      if (seq === _identitySeq) _setIdentity(userId);
    } else if (seq === _identitySeq && _identityUserId !== userId) {
      _setIdentity(userId);
    }
  } catch {
    // Expo Go / Preview API Mode / a malformed key. Leave `_configured` false
    // so every other export stays a no-op and the app behaves as it does today.
  }
}

/** Store offerings, or null when purchases are unavailable / the fetch fails.
 *  Null is a normal answer — the paywall renders server `display_price`
 *  strings in that case rather than showing nothing. */
export async function getOfferings(): Promise<PurchasesOfferings | null> {
  const P = sdk();
  if (!P || !_configured) return null;
  try {
    return await P.getOfferings();
  } catch {
    return null;
  }
}

/** Run a purchase.
 *
 *  Returns null when purchases are unavailable (no key / Expo Go) — the caller
 *  shows the "not available" state. A real StoreKit failure THROWS, because
 *  the caller must distinguish a user cancel (silent) from an error (visible);
 *  narrow it with `isUserCancelled` rather than reading the error shape.
 *
 *  `sessionUserId` is the CURRENT session's user_id. The call waits until
 *  RevenueCat's identity is that user (D12) and throws `PurchaseIdentityError`
 *  if it can't be confirmed: Apple's sheet never opens for the wrong user. */
export async function purchasePackage(
  pkg: PurchasesPackage,
  sessionUserId: string,
): Promise<MakePurchaseResult | null> {
  const P = sdk();
  if (!P || !_configured) return null;
  await _assertIdentity(P, sessionUserId);
  return P.purchasePackage(pkg);
}

/** Restore Purchases (App Store guideline 3.1.1 — required on any screen that
 *  sells a subscription). Null when purchases are unavailable or the restore
 *  itself failed; an empty-but-successful restore returns a CustomerInfo with
 *  no active entitlements, which is a different (and honest) answer. Waits on
 *  the same identity gate as `purchasePackage` (a restore aliases the Apple
 *  ID's purchases onto RevenueCat's current identity). */
export async function restorePurchases(sessionUserId: string): Promise<CustomerInfo | null> {
  const P = sdk();
  if (!P || !_configured) return null;
  await _assertIdentity(P, sessionUserId);
  try {
    return await P.restorePurchases();
  } catch {
    return null;
  }
}

/** Subscribe to CustomerInfo pushes (purchases, renewals, expirations the SDK
 *  learns about). Returns an unsubscribe function — a no-op one when purchases
 *  are unavailable, so callers never branch. */
export function onCustomerInfoChange(
  cb: (info: CustomerInfo) => void,
): () => void {
  const P = sdk();
  if (!P || !_configured) return () => {};
  try {
    P.addCustomerInfoUpdateListener(cb);
    return () => {
      try {
        P.removeCustomerInfoUpdateListener(cb);
      } catch {
        /* teardown must never throw */
      }
    };
  } catch {
    return () => {};
  }
}

/** Does this CustomerInfo carry an ACTIVE `pro` entitlement?
 *  UI cache only — the server's `/api/me/entitlements` is the truth. */
export function hasProEntitlement(info: CustomerInfo | null | undefined): boolean {
  if (!info) return false;
  try {
    return !!info.entitlements.active[PRO_ENTITLEMENT_ID];
  } catch {
    return false;
  }
}

/** The active `pro` entitlement's product and JOIN date (its first
 *  purchase, a trial start included). DISPLAY ONLY (#393 M3: the welcome's
 *  date, Settings › Subscription's plan line): never a gate input. Null
 *  without an active `pro`. Deliberately reads no expiry, renewal or trial
 *  field: nothing in the app shows a trial state or a countdown (D10). */
export function activeProFrom(
  info: CustomerInfo | null | undefined,
): { productId: string; since: string | null } | null {
  try {
    const ent = info?.entitlements.active[PRO_ENTITLEMENT_ID];
    if (!ent?.productIdentifier) return null;
    return { productId: ent.productIdentifier, since: ent.originalPurchaseDate || null };
  } catch {
    return null;
  }
}

/** Settings › Subscription's member line (#393 M3), DISPLAY ONLY: the active
 *  `pro` product, its join date, and StoreKit's period ("P1Y" / "P1M") and
 *  localized price for that product. Null when purchases are unavailable,
 *  when RevenueCat's identity isn't confirmed as `sessionUserId` (a
 *  CustomerInfo for the previous user must never describe this one), or on
 *  any SDK error. Never throws. */
export async function getActivePro(sessionUserId: string): Promise<{
  productId: string;
  since: string | null;
  period: string | null;
  priceString: string | null;
} | null> {
  const P = sdk();
  if (!P || !_configured || !isIdentityReady(sessionUserId)) return null;
  try {
    const ent = activeProFrom(await P.getCustomerInfo());
    if (!ent) return null;
    let product: PurchasesStoreProduct | null = null;
    try {
      product = (await P.getProducts([ent.productId]))?.[0] ?? null;
    } catch {
      product = null;
    }
    return { ...ent, period: product?.subscriptionPeriod ?? null, priceString: product?.priceString ?? null };
  } catch {
    return null;
  }
}

/** True when a rejected purchase was the user backing out of the StoreKit
 *  sheet. RevenueCat sets `userCancelled` on the rejection; a cancel is not an
 *  error and must never surface an error message. */
export function isUserCancelled(err: unknown): boolean {
  return !!(err && typeof err === 'object' && (err as { userCancelled?: boolean }).userCancelled);
}

/** True when StoreKit deferred the purchase (Ask to Buy / SCA): not a failure,
 *  and nothing was charged yet. RevenueCat's PAYMENT_PENDING_ERROR, code "20". */
export function isPaymentPending(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false;
  const e = err as { code?: unknown; readableErrorCode?: unknown; userInfo?: { readableErrorCode?: unknown } };
  return String(e.code) === '20'
    || e.readableErrorCode === 'PAYMENT_PENDING_ERROR'
    || e.userInfo?.readableErrorCode === 'PAYMENT_PENDING_ERROR';
}

// ── Intro (free-month) eligibility (#393 M1, D6; legal R28.8 #1) ────────────
// "Free" copy appears ONLY when StoreKit confirms, for this Apple ID, that the
// product's introductory offer is ours: one free month. Unknown, loading, an
// SDK error, no SDK, or an intro offer that isn't exactly one free month all
// read as NOT eligible, so the screen shows the paid disclosure and no "free"
// anywhere. The server's `trial_eligible` is a per-SKU claim, never read here.

/** RevenueCat's `INTRO_ELIGIBILITY_STATUS_ELIGIBLE` (UNKNOWN 0, INELIGIBLE 1,
 *  ELIGIBLE 2, NO_INTRO_OFFER_EXISTS 3). A literal so this stays pure. */
export const INTRO_ELIGIBLE_STATUS = 2;

/** Pure: StoreKit confirms a free month for this product. */
export function isConfirmedFreeMonth(
  status: unknown,
  intro: { price?: number; period?: string; periodUnit?: string; periodNumberOfUnits?: number } | null | undefined,
): boolean {
  if (status !== INTRO_ELIGIBLE_STATUS || !intro) return false;
  if (intro.price !== 0) return false;
  return intro.period === 'P1M' || (intro.periodUnit === 'MONTH' && intro.periodNumberOfUnits === 1);
}

/** product id → confirmed free month. A product absent from the map, or an
 *  empty map, means NOT eligible. Never throws. */
export async function checkIntroEligibility(
  products: PurchasesStoreProduct[],
): Promise<Record<string, boolean>> {
  const out: Record<string, boolean> = {};
  const P = sdk();
  if (!P || !_configured || products.length === 0) return out;
  try {
    const res = await P.checkTrialOrIntroductoryPriceEligibility(products.map((p) => p.identifier));
    for (const p of products) {
      out[p.identifier] = isConfirmedFreeMonth(res?.[p.identifier]?.status, p.introPrice);
    }
  } catch {
    // Unknown is not eligible.
  }
  return out;
}

// ── Tip jar (consumables) ───────────────────────────────────────────────────
// Tips are NOT packages in an offering — they are plain consumable products
// fetched by id (the ids come from /api/paywall/config `tips`). They buy
// nothing: backend/entitlements.is_tip_product() short-circuits the webhook
// projector, so a tip can never grant `pro`, and no CustomerInfo/entitlement
// handling belongs anywhere near this path.

/** Fetch the tip consumables by product id. Empty array when purchases are
 *  unavailable or the store lookup fails — the tip jar renders server
 *  `display_price` strings display-only in that case. */
export async function getTipProducts(
  productIds: string[],
): Promise<PurchasesStoreProduct[]> {
  const P = sdk();
  if (!P || !_configured || productIds.length === 0) return [];
  try {
    return await P.getProducts(productIds, P.PRODUCT_CATEGORY?.NON_SUBSCRIPTION);
  } catch {
    return [];
  }
}

/** Purchase one tip. Same contract as purchasePackage: null when purchases
 *  are unavailable; a StoreKit rejection THROWS so the caller can separate a
 *  user cancel (silent) from a failure (visible) via isUserCancelled. */
export async function purchaseTip(
  product: PurchasesStoreProduct,
): Promise<MakePurchaseResult | null> {
  const P = sdk();
  if (!P || !_configured) return null;
  return P.purchaseStoreProduct(product);
}
