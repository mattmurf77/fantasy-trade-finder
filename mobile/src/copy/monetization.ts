// The monetization copy (#393 M1, D8): every `mon.*` string the paywall and
// the VerifySheet render, plus the few pure helpers that assemble them.
//
// SOURCE: docs/plans/org-bringup/leads/marketing-lead-copy.md §9.1–9.5 and
// §9.11, legal-approved (R28.8, R28.9, R28.10, R28.12, R28.15). The strings
// are VERBATIM; change one only from that file. `{Club name}` is "Founding
// GMs" (operator, 2026-10-25).
//
// ZERO RUNTIME IMPORTS, on purpose: tests/check-paywall-gate.js transpiles
// and executes this module under plain node to pin legal R28.8:
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
    'No subscription found for this Apple ID. Questions: fleecedapp@gmail.com',
  // §9.4 (row §2) Settings › Subscription (M3): Manage opens Apple's page
  'mon.pay.manage': 'Manage subscription',
  // §9.4 / §9.5 the club block (window only, server-driven)
  'mon.club.join': 'Join the Founding GMs.',
  'mon.pay.founder.price':
    'Founder price: $24.99 a year or $4.99 a month when you subscribe by December 31, 2026.',
  'mon.pay.founder.new': 'From January 1, 2027, new members pay $34.99 a year or $6.99 a month.',
  'mon.pay.founder.keep': 'Keep this price on your plan while your subscription stays active.',
  'mon.pay.founder.lapse':
    'If you switch plans or your subscription ends, you may lose the Founder price.',
  // §9.5 the Founding GMs lines (M3): the welcome (club window only) and
  // Settings › Subscription. `mon.club.welcome_tester` is NOT here: nothing
  // on the client knows who was a tester, so the welcome ships the
  // non-tester title. `mon.club.kept_home` and `mon.club.mark_a11y` (the
  // Home line and mark) are later updates, not this build.
  'mon.club.welcome_title': 'Welcome, Founding GM.',
  'mon.club.welcome_body.annual':
    'Your plan is at the Founder price: $24.99 a year. Keep this price on your plan while your subscription stays active. From January 1, 2027, new members pay $34.99 a year or $6.99 a month.',
  'mon.club.welcome_body.monthly':
    'Your plan is at the Founder price: $4.99 a month. Keep this price on your plan while your subscription stays active. From January 1, 2027, new members pay $34.99 a year or $6.99 a month.',
  'mon.club.since': 'Founding GM since {join date}',
  'mon.club.back': 'Back to my trades',
  'mon.club.kept_settings.annual':
    'Founder price: $24.99 a year. Keep this price on your plan while your subscription stays active.',
  'mon.club.kept_settings.monthly':
    'Founder price: $4.99 a month. Keep this price on your plan while your subscription stays active.',
  'mon.club.lapse':
    'If you switch plans or your subscription ends, you may lose the Founder price.',
  // §9.6 the invitee lines (M3): the trigger variant only, invitees only.
  // `mon.invitee.context` is a template: render it ONLY through
  // inviteeContext() below, which refuses a missing value.
  'mon.invitee.context': '{inviter} invited you to {league}.',
  'mon.invitee.board':
    "Ranking doesn't need a subscription, and your board shapes the trades your leaguemates see.",
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

// ── The invitee lines (§9.6; ux §5 B7) ──────────────────────────────────────
/** `mon.invitee.context` with both values filled, or null when either is
 *  missing or blank: the eyebrow renders nothing rather than a broken
 *  template. Never returns a string with a raw `{…}` placeholder. */
export function inviteeContext(
  inviter: string | null | undefined,
  league: string | null | undefined,
): string | null {
  const who = (inviter ?? '').trim();
  const where = (league ?? '').trim();
  if (!who || !where) return null;
  return MON['mon.invitee.context'].replace('{inviter}', () => who).replace('{league}', () => where);
}

// ── The Founding GMs lines (§9.4 sub_status, §9.5; M3) ──────────────────────
/** The Founder prices the legal lines name (`mon.pay.founder.price`). A
 *  member's status line uses these, so it can never contradict the
 *  `kept_settings` line under it once new members pay more. */
export const FOUNDER_PRICE: Record<PlanPeriod, string> = {
  annual: '$24.99',
  monthly: '$4.99',
};

/** `mon.pay.sub_status`: "Founding GM · Fleeced Pro Annual · $24.99/year"
 *  for a club member, "Fleeced Pro Annual · $24.99/year" otherwise. No
 *  trial state and no dates (D10). */
export function subStatus(period: PlanPeriod, price: string, founder: boolean): string {
  const line = `${PLAN_TITLE[period]} · ${pricePerPeriod(period, price)}`;
  return founder ? `Founding GM · ${line}` : line;
}

/** `mon.club.welcome_body`, the purchased plan's variant. */
export function welcomeBody(period: PlanPeriod): string {
  return period === 'monthly' ? MON['mon.club.welcome_body.monthly'] : MON['mon.club.welcome_body.annual'];
}

/** `mon.club.kept_settings`, the member's plan variant. */
export function keptSettings(period: PlanPeriod): string {
  return period === 'monthly' ? MON['mon.club.kept_settings.monthly'] : MON['mon.club.kept_settings.annual'];
}

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

/** `mon.club.since` ("Founding GM since {join date}"), split so the date can
 *  render in Plex Mono: the lead words and the date ("November 6, 2026",
 *  the copy's own date style). A JOIN date, never a countdown; null for a
 *  missing or unreadable date, so the line is left out, never guessed. */
export function clubSince(iso: string | null | undefined): { lead: string; date: string } | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return {
    lead: MON['mon.club.since'].replace(' {join date}', ''),
    date: `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`,
  };
}

/** StoreKit's ISO 8601 subscription period → the plan ("P1Y" → annual,
 *  "P1M" → monthly); anything else is unknown. */
export function periodFromStore(subscriptionPeriod: string | null | undefined): PlanPeriod | null {
  if (subscriptionPeriod === 'P1Y') return 'annual';
  if (subscriptionPeriod === 'P1M') return 'monthly';
  return null;
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
