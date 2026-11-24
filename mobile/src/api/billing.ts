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
import { useFeatureFlags } from '../state/useFeatureFlags';
import { paywallConfigPath } from '../utils/leaguePass';

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
  /** League pass (lld §6.1): every live pass covering the caller. Present
   *  ONLY while `monetize.league_pass` is on server-side; `[]` for an
   *  unverified session. `pro` keeps its meaning: a covered member's `pro`
   *  stays false. */
  league_passes?: LeaguePassEntry[];
}

/** One live pass covering the caller (`GET /api/me/entitlements`). */
export interface LeaguePassEntry {
  league_id: string;
  platform: string;
  role: 'buyer' | 'member';
  /** ISO UTC; coverage runs to here. */
  covered_until: string;
  /** The buyer's display name only when they opted in (R28), else null. */
  buyer_display: string | null;
}

/** One purchasable plan as the SERVER describes it. `display_price` is the
 *  fallback the paywall renders when StoreKit offerings are unavailable —
 *  a localized `priceString` from RevenueCat always wins when present. */
export interface PaywallProduct {
  product_id: string;
  period: string;              // 'monthly' | 'annual' | 'lifetime' | 'season'
  display_price: string;
  scheduled_us_price?: string; // US new-subscriber price when the Founder window closes
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
  /** League pass (lld §6.2): served only while `monetize.league_pass` is on
   *  AND the request carried `caps=league_pass`. Display FALLBACK copy, like
   *  `products`: StoreKit's localized prices win. */
  league_pass?: LeaguePassConfig;
}

/** The `league_pass` block of the paywall config. */
export interface LeaguePassConfig {
  /** The RevenueCat offering holding the one product ('league'). */
  offering: string;
  /** The yearly price, fallback copy ("$99.99"). */
  renews_at_price: string;
  products: LeaguePassProduct[];
}

/** The one league product. Its one-month free trial is the App Store
 *  introductory offer, read from StoreKit, never from this config. */
export interface LeaguePassProduct {
  product_id: string;          // ftf_league_annual — cross-client-invariants
  display_price: string;       // the yearly price, fallback copy
}

export function getEntitlements(): Promise<EntitlementsResponse> {
  return api.get<EntitlementsResponse>('/api/me/entitlements');
}

/** `platform` filters DISPLAY only (which SKUs a store can actually sell).
 *  iOS is the shipping client; the param is explicit so the web and extension
 *  paywalls can reuse the same route without the server guessing.
 *  `caps=league_pass` is added ONLY while the client's `monetize.league_pass`
 *  is on (utils/leaguePass.paywallConfigPath), so a flag-off request is
 *  byte-identical to the launch binary's. */
export function getPaywallConfig(
  platform: 'ios' | 'web' | 'extension' = 'ios',
): Promise<PaywallConfig> {
  const leaguePassOn = useFeatureFlags.getState().flags['monetize.league_pass'] === true;
  return api.get<PaywallConfig>(paywallConfigPath(platform, leaguePassOn));
}

// ── League pass (lld §6; flag `monetize.league_pass`, dark) ─────────────────
// Every route 404s with the flag off, needs a verified session, and answers
// a refusal as 409 `{error: reason, ...detail}` (utils/leaguePass.refusalReason
// reads it). 409 is an expected answer, so it stays out of api_request_failed.

const LP_QUIET = { quietStatuses: [409] as const };

/** `POST /api/league-pass/intent`: the league chosen before the purchase
 *  sheet, and its quote. */
export interface LeaguePassIntent {
  intent_id: number;
  /** Always `ftf_league_annual`. */
  product_id: string;
  teams: number | null;
}

/** `GET /api/league-pass`: the caller's own pass, as its buyer. */
export interface LeaguePassView {
  pass: {
    league_id: string;
    platform: string;
    covered_until: string;
    will_renew: boolean;
    covered_count: number;
    /** Null when a move is allowed now. */
    can_repoint_at: string | null;
    show_buyer: boolean;
  } | null;
  /** Holds a live league product but no live pass: choose a league (R19). */
  unbound: boolean;
}

export function createLeaguePassIntent(leagueId: string): Promise<LeaguePassIntent> {
  return api.post<LeaguePassIntent>('/api/league-pass/intent', { league_id: leagueId }, LP_QUIET);
}

export function getLeaguePass(): Promise<LeaguePassView> {
  return api.get<LeaguePassView>('/api/league-pass');
}

export function bindLeaguePass(leagueId: string): Promise<LeaguePassView> {
  return api.post<LeaguePassView>('/api/league-pass/bind', { league_id: leagueId }, LP_QUIET);
}

export function repointLeaguePass(leagueId: string): Promise<LeaguePassView> {
  return api.post<LeaguePassView>('/api/league-pass/repoint', { league_id: leagueId }, LP_QUIET);
}

export function setLeaguePassShowBuyer(show: boolean): Promise<LeaguePassView> {
  return api.put<LeaguePassView>('/api/league-pass/settings', { show_buyer: show }, LP_QUIET);
}

/** One tip-jar consumable. Display metadata ONLY — a tip grants nothing
 *  (the backend projector stores the event and deliberately never writes an
 *  entitlement row; entitlements.is_tip_product). */
export interface PaywallTip {
  product_id: string;          // ftf_tip_* — enum in cross-client-invariants
  display_price: string;       // fallback when StoreKit products are unavailable
}
