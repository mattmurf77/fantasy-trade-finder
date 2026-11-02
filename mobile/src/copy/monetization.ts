// The monetization copy (#393 M1, D8): every `mon.*` string the paywall and
// the VerifySheet render, plus the few pure helpers that assemble them.
//
// SOURCE: docs/plans/org-bringup/leads/marketing-lead-copy.md §9.1–9.5 and
// §9.11, legal-approved (R28.8, R28.9, R28.10, R28.12, R28.15). The strings
// are VERBATIM; change one only from that file. `{Club name}` is "Founding
// GMs" (operator, 2026-10-25).
//
// ONE RUNTIME IMPORT, on purpose: the support address (utils/supportContact,
// a constant-only module; check-feedback-public pin 3 keeps it the only
// literal in mobile/src). tests/check-paywall-gate.js transpiles and executes
// this module under plain node, stubbing that import with the real module, to
// pin legal R28.8:
//   #1 unknown eligibility → the paid copy, no "free" anywhere;
//   #2 the per-month figure and the savings % come from live StoreKit
//      prices: per-month rounds UP to the cent, savings rounds DOWN; no SAVE
//      badge; "/year" stays the largest price text (the screen's job);
//   #3 the CTA is "Start 1-month trial" ("Start my free month" waits for
//      legal's ruling on the anchored layout to land in the copy file);
//   #4 `mon.club.kept_home` is not in this build;
//   #6 the plan titles match App Store Connect exactly;
//   #7 nothing implies board-based PRICING (C9: boards drive selection).
// No countdown, days-left, trial-end date or "ends soon" line exists here
// (the operator's 2026-10-24 ruling, D10).

import { SUPPORT_EMAIL } from '../utils/supportContact';

export const CLUB_NAME = 'Founding GMs';

export const MON = {
  // §9.1 the offer
  'mon.offer.headline': "There's a full deck behind this page.",
  'mon.offer.body.eligible':
    'Start the month and the deck keeps building. Not now, and you still finish this page.',
  'mon.offer.body.paid':
    'Subscribe and the deck keeps building. Not now, and you still finish this page.',
  'mon.offer.cta': 'Start 1-month trial',
  'mon.offer.cta_paid': 'Subscribe',
  'mon.offer.not_now': 'Not now',
  'mon.offer.close_a11y': 'Close',
  // §9.2 the free page's end card (M2): the eyebrow above `mon.lock.find`
  'mon.preview.page_end': "That's the first page.",
  // §9.3 the lock lines (headlines when a locked action opens the paywall)
  'mon.lock.find': 'Finding trades needs a subscription.',
  'mon.lock.send': 'Sending trades needs a subscription.',
  'mon.lock.free':
    'No subscription needed for ranking, Calibration, tiers, trends, rosters or the Draft Room.',
  // §9.4 the paywall
  'mon.pay.headline': 'Find trades. Send them to your league.',
  'mon.pay.value': 'A subscription covers finding and sending trades.',
  'mon.pay.b1': 'A trade deck that weighs your board and theirs',
  'mon.pay.b2': 'Matches when a leaguemate likes the same trade',
  'mon.pay.b3': 'Proposals sent to Sleeper, ESPN or MFL',
  'mon.pay.b4': 'Shop a player and Win Now trade targets',
  'mon.pay.restore': 'Restore purchases',
  // §9.4 (row §2): the end card's button (M2) and Settings' non-member row
  'mon.pay.see_plans': 'See plans',
  'mon.pay.terms': 'Terms of Use',
  'mon.pay.privacy': 'Privacy Policy',
  'mon.pay.error':
    "The App Store didn't finish the purchase. Check your connection and try again.",
  'mon.pay.error.retry': 'Try again',
  'mon.pay.pending': 'Waiting for approval. Access starts when it comes through.',
  'mon.pay.restore_ok': 'Welcome back. Your subscription is restored.',
  'mon.pay.restore_none':
    `No subscription found for this Apple ID. Questions: ${SUPPORT_EMAIL}`,
  // §9.4 / §9.5 the club block (window only, server-driven)
  'mon.club.join': 'Join the Founding GMs.',
  'mon.pay.founder.price':
    'Founder price: $24.99 a year or $4.99 a month when you subscribe by December 31, 2026.',
  'mon.pay.founder.new': 'Starting in January 2027, new members pay $34.99 a year or $6.99 a month.',
  'mon.pay.founder.keep': 'Keep this price on your plan while your subscription stays active.',
  'mon.pay.founder.lapse':
    'If you switch plans or your subscription ends, you may lose the Founder price.',
  // §9.11 the VerifySheet
  'mon.verify.title': 'Verify this session first',
  'mon.verify.body':
    'To use or start a subscription, verify this session first. Signing in confirms the account is yours.',
  'mon.verify.sleeper': 'Verify with Sleeper',
  'mon.verify.continue': 'Continue',
  'mon.verify.done': 'Session verified.',
  'mon.verify.wrong_account':
    'That sign-in is for a different account, so nothing changed. Use the same account you signed in with.',
  'mon.verify.switched':
    "That sign-in is for a different account, so you're now signed in to that one.",
  // The non-Sleeper variant (legal R28.12 #3 / #3b, verbatim). It NEVER says
  // "verify". CONDITION: "nothing from this session carries over" is true
  // only while Apple sign-in migrates nothing from the entry session (true
  // today, per platforms-eng). If Apple sign-in ever migrates entry-session
  // data, this body must change (legal) before that ships.
  'mon.verify.apple_only.title': 'A new sign-in is needed',
  'mon.verify.apple_only.body':
    "Use Sign in with Apple to subscribe. It's a new sign-in: reconnect your league in Settings, and nothing from this session carries over.",
} as const;

export type MonKey = keyof typeof MON;

/** Not `mon.*` keys yet (flagged in the PR): ux-lead's sheet spec names a
 *  Cancel, and design-lead's FounderTag reads "FOUNDING GM". */
export const VERIFY_CANCEL = 'Cancel';
export const FOUNDER_TAG = 'FOUNDING GM';

// ── Plans (R28.8 #6: titles match App Store Connect exactly) ────────────────
export type PlanPeriod = 'annual' | 'monthly';

export const PLAN_TITLE: Record<PlanPeriod, string> = {
  annual: 'Fleeced Pro Annual',
  monthly: 'Fleeced Pro Monthly',
};

export const PERIOD_SUFFIX: Record<PlanPeriod, string> = {
  annual: '/year',
  monthly: '/month',
};

export function planPeriod(period: string): PlanPeriod | null {
  return period === 'annual' || period === 'monthly' ? period : null;
}

/** "$24.99/year". `price` is StoreKit's localized string when offerings
 *  loaded, else the server's display_price fallback. */
export function pricePerPeriod(period: PlanPeriod, price: string): string {
  return `${price}${PERIOD_SUFFIX[period]}`;
}

/** `mon.offer.trial_line`: rendered ONLY when StoreKit confirmed the free
 *  month for the selected plan (R28.8 #1). */
export function trialLine(period: PlanPeriod, price: string): string {
  return `1 month free, then ${pricePerPeriod(period, price)}`;
}

/** `mon.pay.disc.trial` (eligible) / `mon.pay.disc.paid` (not eligible, and
 *  the DEFAULT while eligibility is unknown or loading). Tracks the selected
 *  plan; sits directly above the button (3.1.2). */
export function disclosure(period: PlanPeriod, price: string, eligible: boolean): string {
  const title = PLAN_TITLE[period];
  const pp = pricePerPeriod(period, price);
  return eligible
    ? `${title}: 1 month free, then ${pp}. Payment is charged to your Apple ID when the free month ends. Renews automatically until cancelled. Cancel in your Apple ID settings at least 24 hours before the free month or the current period ends.`
    : `${title}: ${pp}, charged to your Apple ID when you confirm. Renews automatically until cancelled. Cancel in your Apple ID settings at least 24 hours before the current period ends.`;
}

/** R28.8 #3: the eligible CTA is "Start 1-month trial"; not eligible (or
 *  unknown) is "Subscribe", with no "free" on the screen. */
export function ctaLabel(eligible: boolean): string {
  return eligible ? MON['mon.offer.cta'] : MON['mon.offer.cta_paid'];
}

// ── R28.8 #2: the annual sub line, from live StoreKit prices ────────────────

/** Integer cents from a StoreKit price number (2499 for 24.99). */
export function toCents(price: number): number {
  return Math.round(price * 100);
}

/** The annual price per month, rounded UP to the cent: 2499 → 209. Integer
 *  arithmetic, so 2388 → 199 exactly (no float ceil to 200). */
export function perMonthCentsUp(annualCents: number): number {
  return Math.ceil(annualCents / 12);
}

/** The saving against 12 monthly payments, rounded DOWN to a whole percent:
 *  (2499, 499) → 58. Null when there's no saving to state. */
export function savingsPercentDown(annualCents: number, monthlyCents: number): number | null {
  const twelve = 12 * monthlyCents;
  if (!(annualCents > 0) || !(monthlyCents > 0) || annualCents >= twelve) return null;
  const pct = Math.floor((100 * (twelve - annualCents)) / twelve);
  return pct > 0 ? pct : null;
}

/** Money for a computed figure, in the StoreKit product's currency. */
export function formatCents(cents: number, currencyCode: string): string {
  const amount = cents / 100;
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: currencyCode }).format(amount);
  } catch {
    return currencyCode === 'USD' ? `$${amount.toFixed(2)}` : `${currencyCode} ${amount.toFixed(2)}`;
  }
}

/** `mon.pay.plan.annual`'s sub line: "$2.09/month, billed yearly. 58% less
 *  than 12 months at $4.99." Built ONLY from live StoreKit prices (both
 *  products from the same storefront); null without them, so a server
 *  display string never feeds the math. */
export function annualSubLine(
  annual: { price: number; currencyCode: string } | null | undefined,
  monthly: { price: number; priceString: string; currencyCode: string } | null | undefined,
): string | null {
  if (!annual || !monthly || !(annual.price > 0)) return null;
  if (annual.currencyCode !== monthly.currencyCode) return null;
  const aC = toCents(annual.price);
  const perMonth = formatCents(perMonthCentsUp(aC), annual.currencyCode);
  const pct = savingsPercentDown(aC, toCents(monthly.price));
  const head = `${perMonth}/month, billed yearly.`;
  return pct === null ? head : `${head} ${pct}% less than 12 months at ${monthly.priceString}.`;
}

// ── Paywall variants (ux-lead "Monetization copy placement") ────────────────
export type PaywallSource = 'first_opinion' | 'left_deck' | 'gate' | 'settings' | 'preview_end';

/** The headline by how the paywall was opened. */
export function headlineFor(source: string, kind?: string): string {
  if (source === 'first_opinion' || source === 'left_deck' || source === 'preview_end') {
    return MON['mon.offer.headline'];
  }
  if (source === 'gate') return kind === 'send' ? MON['mon.lock.send'] : MON['mon.lock.find'];
  return MON['mon.pay.headline'];
}

/** `mon.offer.body` is true only at the trigger ("you still finish this
 *  page"), so never on the lock, end-card or Settings variants. */
export function offerBodyFor(source: string, eligible: boolean): string | null {
  if (source !== 'first_opinion' && source !== 'left_deck') return null;
  return eligible ? MON['mon.offer.body.eligible'] : MON['mon.offer.body.paid'];
}

// ── The VerifySheet ─────────────────────────────────────────────────────────
/** `sleeper`: a Sleeper session, verified through SleeperConnect.
 *  `apple`: any other unverified session; a NEW sign-in with Apple. */
export type VerifyPath = 'sleeper' | 'apple';

export function verifyCopy(path: VerifyPath): { title: string; body: string } {
  return path === 'sleeper'
    ? { title: MON['mon.verify.title'], body: MON['mon.verify.body'] }
    : { title: MON['mon.verify.apple_only.title'], body: MON['mon.verify.apple_only.body'] };
}

/** What the sheet may say after a verify attempt, chosen PER PATH (D17, D20):
 *   - Sleeper, the server returned `verified === true` → "Session verified.";
 *   - Sleeper, 403 token_user_mismatch → nothing changed (true on this path);
 *   - Apple landing in a different, EXISTING account → "you're now signed in
 *     to that one" ("nothing changed" would be false there);
 *   - Apple, a brand-new account → nothing (the body already said it's new).
 *  The Apple path never gets the "verified" line: that variant never says
 *  "verify". */
export type VerifyOutcome = 'verified' | 'mismatch' | 'switched' | 'new_account';

export function verifyOutcomeLine(path: VerifyPath, outcome: VerifyOutcome): string | null {
  if (path === 'sleeper') {
    if (outcome === 'verified') return MON['mon.verify.done'];
    if (outcome === 'mismatch') return MON['mon.verify.wrong_account'];
    return null;
  }
  return outcome === 'switched' ? MON['mon.verify.switched'] : null;
}
