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

/** GET /api/me/entitlements. `enforcing` echoes `monetize.entitlements`, so a
 *  client can tell "you are not Pro" from "gating is not on yet". */
export interface EntitlementsResponse {
  pro: boolean;
  ad_free: boolean;
  /** Grant provenance, e.g. ['apple_iap'] / ['manual_grant']. */
  sources: string[];
  /** Furthest expiry among active pro rows; null when one is perpetual. */
  expires_at: string | null;
  enforcing?: boolean;
}

/** One purchasable plan as the SERVER describes it. `display_price` is the
 *  fallback the paywall renders when StoreKit offerings are unavailable —
 *  a localized `priceString` from RevenueCat always wins when present. */
export interface PaywallProduct {
  product_id: string;
  period: string;              // 'monthly' | 'annual' | 'lifetime' | 'season'
  display_price: string;
  per_month_equiv?: string;
  trial_days: number;
  hero: boolean;
  badge?: string;              // 'best_value' — enum in cross-client-invariants
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
