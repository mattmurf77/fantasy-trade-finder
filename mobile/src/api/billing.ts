// billing.ts — the monetization read endpoints.
//
//   GET /api/me/entitlements    — resolved entitlement state (foundation §2.3,
//                                 live in backend/server.py today)
//   GET /api/paywall/config     — what the paywall renders (pro-subscription
//                                 LLD §3)
//
// Both are session-authed and both stay mounted regardless of flags: clients
// bootstrap entitlement state BEFORE `monetize.entitlements` flips, and the
// paywall config answers `{enabled:false}` while `monetize.paywall` is off.
//
// The server is the ONLY authority on `pro` (backend/entitlements.check_pro).
// Nothing this module returns is derived from a device receipt.

import { api } from './client';

/** GET /api/me/entitlements. `enforcing` is the server's enforce predicate
 *  (the same one the 402 gate uses), so a client can tell "you are not Pro"
 *  from "gating is not on yet". For an UNVERIFIED session the server blanks
 *  every subscription field (`pro`/`founder` false, `sources` [], R28.9) but
 *  keeps `enforcing`: a blank reads as not entitled, never as not enforcing. */
export interface EntitlementsResponse {
  pro: boolean;
  ad_free: boolean;
  /** Grant provenance, e.g. ['apple_iap'] / ['manual_grant']. */
  sources: string[];
  /** Furthest expiry among active pro rows; null when one is perpetual. */
  expires_at: string | null;
  enforcing?: boolean;
  /** Founding GMs member (S1, #465). Absent on an older server ⇒ false. */
  founder?: boolean;
}

/** One purchasable plan as the SERVER describes it. `display_price` is the
 *  fallback the paywall renders when StoreKit offerings are unavailable —
 *  a localized `priceString` from RevenueCat always wins when present. */
export interface PaywallProduct {
  product_id: string;
  period: string;              // 'monthly' | 'annual' | 'lifetime' | 'season'
  display_price: string;
  per_month_equiv?: string;
  /** "1 month" (S1). Display context only: the free-month copy keys off
   *  StoreKit intro eligibility (purchases.checkIntroEligibility), never this
   *  and never a day count. (`trial_days` is gone, #393 D14.) */
  trial_period?: string;
  hero: boolean;
  badge?: string;              // 'best_value' — enum in cross-client-invariants
}

/** The Founding GMs window (S1, #465). Absent on an older server ⇒ closed. */
export interface PaywallClub {
  name: string;
  closes_at: string;
  open: boolean;
}

/** One rendered block of the paywall. `kind` is an OPEN set on purpose: an
 *  older binary must skip a page type it does not know rather than break. */
export interface PaywallPage {
  id: string;
  kind: string;                // 'trades_found' | 'features' | 'purchase'
  title?: string;
  body_ref?: string;
  features?: string[];
}

/** GET /api/paywall/config?platform=ios — pro-subscription LLD §3. */
export interface PaywallConfig {
  enabled: boolean;
  /** Echo of the resolved `platform` (the server falls back to 'ios' on an
   *  unknown value rather than 400ing a stale client). */
  platform?: string;
  pages?: PaywallPage[];
  products?: PaywallProduct[];
  club?: PaywallClub;
  /** Per-SKU claim only. Never read for copy (#393 D6). */
  trial_eligible?: boolean;
  dismissible?: boolean;
  /** Tip-jar consumables (support-the-platform; no entitlement). */
  tips?: PaywallTip[];
}

export function getEntitlements(): Promise<EntitlementsResponse> {
  return api.get<EntitlementsResponse>('/api/me/entitlements');
}

/** `platform` filters DISPLAY only (which SKUs a store can actually sell).
 *  iOS is the shipping client; the param is explicit so the web and extension
 *  paywalls can reuse the same route without the server guessing. */
export function getPaywallConfig(
  platform: 'ios' | 'web' | 'extension' = 'ios',
): Promise<PaywallConfig> {
  return api.get<PaywallConfig>(`/api/paywall/config?platform=${platform}`);
}

/** One tip-jar consumable. Display metadata ONLY — a tip grants nothing
 *  (the backend projector stores the event and deliberately never writes an
 *  entitlement row; entitlements.is_tip_product). */
export interface PaywallTip {
  product_id: string;          // ftf_tip_* — enum in cross-client-invariants
  display_price: string;       // fallback when StoreKit products are unavailable
}
