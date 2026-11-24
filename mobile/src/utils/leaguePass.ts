// League pass — the client's pure decisions (flag `monetize.league_pass`,
// dark; docs/plans/monetization/league-pass/lld.md §8, D-281).
//
// ZERO RUNTIME IMPORTS, on purpose: tests/check-league-pass.js transpiles and
// executes this module under plain node. Everything here is a function of its
// arguments; no flag, store, clock or SDK is read. Callers pass the flag and
// `Date.now()`.
//
// What lives here:
//   - coverage: `livePassFor`, `proForLeague`, `coveredElsewhere`;
//   - the purchase path for a quoted tier (`purchasePathFor`, `purchasePlan`,
//     `purchaseCallFor`), which is what keeps the price on screen equal to
//     the price charged;
//   - the 409 refusal reason → copy key table (`refusalCopyKey`);
//   - the one-time "your league is now covered" notice (R29): its storage key
//     and when it is due;
//   - the paywall config path (`paywallConfigPath`): `caps=league_pass` rides
//     only while the flag is on, so a flag-off request is byte-identical.

/** One entry of `GET /api/me/entitlements` `league_passes` (lld §6.1). */
export interface LeaguePassEntryLike {
  league_id: string;
  role: string;                 // 'buyer' | 'member'
  covered_until: string | null; // ISO UTC
  buyer_display?: string | null;
}

/** Parse an ISO instant; NaN for anything unreadable. */
function ms(iso: string | null | undefined): number {
  if (!iso) return NaN;
  const t = Date.parse(iso);
  return Number.isFinite(t) ? t : NaN;
}

/** The pass covering `leagueId` whose `covered_until` is still in the future,
 *  else null. An unreadable or past date is not coverage. */
export function livePassFor<T extends LeaguePassEntryLike>(
  passes: readonly T[] | null | undefined,
  leagueId: string | null | undefined,
  nowMs: number,
): T | null {
  if (!leagueId || !passes) return null;
  for (const p of passes) {
    if (p && p.league_id === leagueId && ms(p.covered_until) > nowMs) return p;
  }
  return null;
}

/** `pro` OR a live pass for that league. With the flag off this is exactly
 *  `pro`, whatever the passes say. Client-side UI only: the server's gate
 *  decides (backend/paywall_gate, LEAGUE_RESOLVERS). */
export function proForLeague(
  pro: boolean,
  passes: readonly LeaguePassEntryLike[] | null | undefined,
  leagueId: string | null | undefined,
  flagOn: boolean,
  nowMs: number,
): boolean {
  if (pro) return true;
  if (!flagOn) return false;
  return livePassFor(passes, leagueId, nowMs) !== null;
}

/** R26: a live pass that covers this user in ANOTHER league while nothing
 *  covers them in `leagueId`. Null when they are covered here, or nowhere. */
export function coveredElsewhere<T extends LeaguePassEntryLike>(
  passes: readonly T[] | null | undefined,
  leagueId: string | null | undefined,
  nowMs: number,
): T | null {
  if (!passes || livePassFor(passes, leagueId, nowMs)) return null;
  for (const p of passes) {
    if (p && p.league_id !== leagueId && ms(p.covered_until) > nowMs) return p;
  }
  return null;
}

/** The caller's own live pass as its buyer (role 'buyer'), else null. */
export function buyerPass<T extends LeaguePassEntryLike>(
  passes: readonly T[] | null | undefined,
  nowMs: number,
): T | null {
  for (const p of passes ?? []) {
    if (p && p.role === 'buyer' && ms(p.covered_until) > nowMs) return p;
  }
  return null;
}

/** Live passes in which the caller is a covered member (not the buyer). */
export function memberPasses<T extends LeaguePassEntryLike>(
  passes: readonly T[] | null | undefined,
  nowMs: number,
): T[] {
  return (passes ?? []).filter((p) => p && p.role === 'member' && ms(p.covered_until) > nowMs);
}

// ── The purchase path (lld §8 "Purchase path in LeaguePassScreen") ──────────
//
//   tier 0                         → 'standard'  (purchasePackage, list price)
//   tier 1/2, intro-eligible       → 'intro'     (purchasePackage; Apple applies
//                                                  the introductory price)
//   tier 1/2, not eligible, a
//     signed promotional offer     → 'promo'     (purchaseDiscountedPackage)
//   tier 1/2, neither              → 'full_price' (purchasePackage at the FULL
//                                                  price, only after the user
//                                                  chose it on a screen that
//                                                  says so)

export type LeaguePurchasePath = 'standard' | 'intro' | 'promo' | 'full_price';

export function purchasePathFor(tier: number, introEligible: boolean, promoAvailable: boolean): LeaguePurchasePath {
  if (!(tier > 0)) return 'standard';
  if (introEligible) return 'intro';
  if (promoAvailable) return 'promo';
  return 'full_price';
}

/** Which SDK call a path makes. Only 'promo' uses the signed offer. */
export function purchaseCallFor(path: LeaguePurchasePath): 'package' | 'discounted' {
  return path === 'promo' ? 'discounted' : 'package';
}

export interface PurchasePlanInput {
  tier: number;
  /** A StoreKit package exists for the quoted product. */
  storeAvailable: boolean;
  introEligible: boolean;
  /** StoreKit's localized list price (what renews), when known. */
  standardPrice: string | null;
  /** StoreKit's localized introductory price, when the product has one. */
  introPrice: string | null;
  /** The signed promotional offer's localized price, when one was obtained. */
  promoPrice: string | null;
  /** Server config fallbacks (`league_pass.products[].display_price` for the
   *  tier and `league_pass.renews_at_price`). Display only. */
  configYearOne: string | null;
  configRenewal: string | null;
}

export interface PurchasePlan {
  path: LeaguePurchasePath;
  /** What the first year costs on THIS path. */
  yearOne: string | null;
  /** What it renews at. */
  renewal: string | null;
  /** True when a purchase can run at all (a StoreKit package exists). */
  canBuy: boolean;
  /** The discount could not be obtained: the screen must say the price is the
   *  full price and let the user continue or cancel. */
  fullPriceNotice: boolean;
}

/** The ONE place the screen's prices come from. The year-one price shown is
 *  the price of the path that will run: the intro price only on 'intro', the
 *  promotional price only on 'promo', and the full price on 'standard' and
 *  'full_price'. A discount price is never shown for a path that charges the
 *  full price. Without StoreKit nothing can be bought, and the server's
 *  display strings stand in (they are the same prices, unlocalized). */
export function purchasePlan(i: PurchasePlanInput): PurchasePlan {
  if (!i.storeAvailable || !i.standardPrice) {
    return {
      path: purchasePathFor(i.tier, false, false),
      yearOne: i.configYearOne,
      renewal: i.configRenewal,
      canBuy: false,
      fullPriceNotice: false,
    };
  }
  const path = purchasePathFor(i.tier, i.introEligible && !!i.introPrice, !!i.promoPrice);
  const yearOne = path === 'intro' ? i.introPrice : path === 'promo' ? i.promoPrice : i.standardPrice;
  return {
    path,
    yearOne,
    renewal: i.standardPrice,
    canBuy: true,
    fullPriceNotice: path === 'full_price',
  };
}

// ── Refusals (lld §3.3/§3.4; api-reference § League pass: 409 {error}) ──────

/** Every 409 reason the `/api/league-pass/*` routes send, mapped to its own
 *  `mon.lp.*` copy key. An unknown reason gets the generic line. */
export const REFUSAL_COPY_KEY = {
  not_member: 'mon.lp.refused.not_member',
  league_not_allowed: 'mon.lp.refused.league_not_allowed',
  already_covered: 'mon.lp.refused.already_covered',
  already_buyer: 'mon.lp.refused.already_buyer',
  refund_blocked: 'mon.lp.refused.refund_blocked',
  tier_mismatch: 'mon.lp.refused.tier_mismatch',
  no_purchase: 'mon.lp.refused.no_purchase',
  no_pass: 'mon.lp.refused.no_pass',
  cooldown: 'mon.lp.refused.cooldown',
} as const;

export type RefusalReason = keyof typeof REFUSAL_COPY_KEY;
export type RefusalCopyKey = (typeof REFUSAL_COPY_KEY)[RefusalReason] | 'mon.lp.refused.generic';

export function refusalCopyKey(reason: string | null | undefined): RefusalCopyKey {
  return reason && Object.prototype.hasOwnProperty.call(REFUSAL_COPY_KEY, reason)
    ? REFUSAL_COPY_KEY[reason as RefusalReason]
    : 'mon.lp.refused.generic';
}

/** The refusal reason from a rejected league-pass call: a 409 whose body is
 *  `{error: reason, ...}`. Null for anything else (network, 5xx, 404). */
export function refusalReason(err: unknown): string | null {
  if (!err || typeof err !== 'object') return null;
  const e = err as { status?: unknown; body?: unknown };
  if (e.status !== 409 || !e.body || typeof e.body !== 'object') return null;
  const reason = (e.body as { error?: unknown }).error;
  return typeof reason === 'string' && reason ? reason : null;
}

// ── Dates ───────────────────────────────────────────────────────────────────

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

/** "January 15, 2028" (the copy's own date style, as `clubSince`); null for
 *  a missing or unreadable date, so a line is left out, never guessed. */
export function passDate(iso: string | null | undefined): string | null {
  const t = ms(iso);
  if (!Number.isFinite(t)) return null;
  const d = new Date(t);
  return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

/** Fill `{name}` slots; a missing value leaves the template unchanged so a
 *  caller can see it, but callers only fill what they hold. */
export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (m, k: string) =>
    Object.prototype.hasOwnProperty.call(values, k) ? String(values[k]) : m);
}

/** A league's display name from the session's league list, else null. */
export function leagueNameFor(
  leagues: readonly { league_id: string; name?: string | null }[] | null | undefined,
  leagueId: string | null | undefined,
): string | null {
  if (!leagueId) return null;
  const hit = (leagues ?? []).find((l) => l.league_id === leagueId);
  const name = (hit?.name ?? '').trim();
  return name || null;
}

// ── R29: the one-time "your league is now covered" notice ───────────────────

/** Billing sources that make someone an existing INDIVIDUAL subscriber
 *  (backend entitlements `_BILLING_SOURCES` minus `league_pass_iap`). */
export const INDIVIDUAL_SOURCES: readonly string[] = [
  'apple_iap', 'stripe', 'founder_iap', 'season_pass_iap', 'trial',
];

/** Per user AND league, so a second covered league tells them again, and the
 *  key carries the user id (accountReset keeps such keys, D-280). */
export function coveredNoticeKey(userId: string, leagueId: string): string {
  return `ftf_lp_covered_notice_${userId}_${leagueId}`;
}

/** Due when the caller pays for an individual plan AND a live pass bought by
 *  someone else covers them in this league. */
export function coveredNoticeDue(
  pro: boolean,
  sources: readonly string[] | null | undefined,
  passes: readonly LeaguePassEntryLike[] | null | undefined,
  leagueId: string | null | undefined,
  flagOn: boolean,
  nowMs: number,
): boolean {
  if (!flagOn || !pro || !leagueId) return false;
  if (!(sources ?? []).some((s) => INDIVIDUAL_SOURCES.includes(s))) return false;
  const entry = livePassFor(passes, leagueId, nowMs);
  return !!entry && entry.role === 'member';
}

/** Holds a league product but no live pass as its buyer: the pass is unbound
 *  (R19) as far as the entitlements tell. `GET /api/league-pass` confirms. */
export function looksUnbound(
  pro: boolean,
  sources: readonly string[] | null | undefined,
  passes: readonly LeaguePassEntryLike[] | null | undefined,
  nowMs: number,
): boolean {
  return pro && (sources ?? []).includes('league_pass_iap') && !buyerPass(passes, nowMs);
}

// ── The paywall config request ──────────────────────────────────────────────

/** `GET /api/paywall/config`'s path. `caps=league_pass` rides ONLY with the
 *  flag on, so with it off the request is exactly today's. */
export function paywallConfigPath(platform: string, leaguePassOn: boolean): string {
  const base = `/api/paywall/config?platform=${platform}`;
  return leaguePassOn ? `${base}&caps=league_pass` : base;
}
