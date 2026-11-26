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
//   - the quote (`purchasePlan`): the price on screen and whether the free
//     month may be promised (only when StoreKit confirmed it);
//   - the 409 refusal reason → copy key table (`refusalCopyKey`);
//   - the one-time "your league is now covered" notice (R29): its storage key
//     and when it is due;
//   - existing Pro users buying (`proBuyEntry`, `currentProOnBuy`): the
//     Settings entry, and whether the purchase replaces their subscription;
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

// ── The quote (lld §8; operator 2026-11-24, "Free month replaces discount") ──
//
// ONE product, `ftf_league_annual`, bought as a plain package purchase. Its
// App Store introductory offer is a one-month free trial, which Apple applies
// by itself to an eligible buyer. Eligibility is per subscription group, so
// someone who already took the individual plan's free month is not eligible.
// The screen promises the free month ONLY when StoreKit confirmed it for this
// Apple ID (api/purchases.checkIntroEligibility, the individual paywall's own
// rule: ELIGIBLE and an intro of exactly one free month). Unknown, loading,
// an error or no StoreKit all read as no free month: the paid copy.

export interface PurchasePlanInput {
  /** StoreKit's localized list price (what is charged / renews), when a
   *  package for the product loaded. */
  storePrice: string | null;
  /** StoreKit confirmed this Apple ID's one free month for the product. */
  freeMonthConfirmed: boolean;
  /** The server config's display price (`league_pass.products[].display_price`,
   *  else `renews_at_price`). Display only, when StoreKit has no package. */
  configPrice: string | null;
}

export interface PurchasePlan {
  /** The yearly price shown (and charged, or charged after the free month). */
  price: string | null;
  /** Show the free month: StoreKit confirmed it AND a purchase can run. */
  freeMonth: boolean;
  /** True when a purchase can run at all (a StoreKit package exists). */
  canBuy: boolean;
}

/** The ONE place the screen's price and free-month state come from. Without
 *  StoreKit nothing can be bought, the server's display string stands in, and
 *  no free month is promised. */
export function purchasePlan(i: PurchasePlanInput): PurchasePlan {
  if (!i.storePrice) return { price: i.configPrice, freeMonth: false, canBuy: false };
  return { price: i.storePrice, freeMonth: i.freeMonthConfirmed === true, canBuy: true };
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

// ── Existing Pro users buying a pass (operator 2026-11-25) ──────────────────
//
// "Existing pro users need the option to purchase a league pass." The
// paywall's entry is never seen by a Pro user, so Settings › Subscription
// offers it. Two kinds of Pro user can buy:
//   - an App Store individual subscriber (`apple_iap`, monthly or annual, in
//     the free month or paying): the pass is in the SAME subscription group,
//     ranked above the individual plans, so buying it is an Apple upgrade
//     that REPLACES the individual subscription (Apple prorates);
//   - Pro with no App Store subscription (a lifetime grant to existing users
//     at launch, a comp or promo grant, Founder lifetime, a web plan):
//     nothing is replaced, and that Pro stays when the pass ends.

/** The App Store individual subscription source (the one group the league
 *  pass shares). Not Stripe: a web plan is not in the App Store group. */
export const APP_STORE_INDIVIDUAL_SOURCE = 'apple_iap';

/** The Settings buy entry for a Pro user: Pro, and not already a pass buyer
 *  (no league product held, bound or unbound, and no live buyer entry).
 *  Shown whether or not a leaguemate's pass covers them as a member: they
 *  may buy for another league (the server refuses a league that already has
 *  a pass, `already_covered`). */
export function proBuyEntry(
  pro: boolean,
  sources: readonly string[] | null | undefined,
  passes: readonly LeaguePassEntryLike[] | null | undefined,
  nowMs: number,
): boolean {
  return pro && !(sources ?? []).includes('league_pass_iap') && !buyerPass(passes, nowMs);
}

/** What buying the pass does to the caller's current Pro, said before Buy:
 *  'replaces' an App Store individual subscription; 'keeps' Pro from
 *  anything else; 'none' when the caller is not Pro. */
export function currentProOnBuy(
  pro: boolean,
  sources: readonly string[] | null | undefined,
): 'replaces' | 'keeps' | 'none' {
  if (!pro) return 'none';
  return (sources ?? []).includes(APP_STORE_INDIVIDUAL_SOURCE) ? 'replaces' : 'keeps';
}

// ── The paywall config request ──────────────────────────────────────────────

/** `GET /api/paywall/config`'s path. `caps=league_pass` rides ONLY with the
 *  flag on, so with it off the request is exactly today's. */
export function paywallConfigPath(platform: string, leaguePassOn: boolean): string {
  const base = `/api/paywall/config?platform=${platform}`;
  return leaguePassOn ? `${base}&caps=league_pass` : base;
}
