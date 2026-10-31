// subscriptionSession — the ONE predicate for "may this session touch
// RevenueCat?" (head-eng, 2026-10-29, from release-lead QA P2-5).
//
// RevenueCat is identified ONLY for a verified session. A typed, unverified
// Sleeper id that reached `Purchases.logIn` would let this device read that
// account's CustomerInfo (an R28.9-class leak), and a Restore would move the
// Apple ID's purchases onto it. So:
//   1. `purchasesIdentityTarget` — the only id `initPurchases` may be called
//      with (useSession's identity bridge). Null ⇒ no configure, no logIn,
//      and no anonymous configure either.
//   2. `customerInfoApplies` — RevenueCat CustomerInfo (the entitlement
//      listener, Restore) is read only while the session is verified AND
//      RevenueCat's completed identity is this session's user. A device last
//      logged in as A never shows A's state to a session for B. The server's
//      `/api/me/entitlements` stays the authority either way.
//
// DEMO IS STRICT (head-eng confirmed 2026-10-29): no RevenueCat at all. The
// server treats demo as unverified, and every demo user shares one id. The
// exclusion is the single `=== 'verified'` comparison in
// `purchasesIdentityTarget`; on every subscription surface demo counts as
// unverified (`state/usePaywallGate.isUnverifiedSession`, PaywallScreen).
//
// ZERO runtime imports, so the checks transpile and execute it as is.

import type { SavedUser, SessionVerification } from './useSession';

export type SubscriptionSessionState = 'verified' | 'unverified' | 'unknown' | 'demo';

export interface SubscriptionSessionInput {
  isDemo: boolean;
  verification: Pick<SessionVerification, 'session_verified'> | null | undefined;
  user: Pick<SavedUser, 'user_id' | 'account_only'> | null | undefined;
}

/** In this order: demo; the server's `session_verified` when it has
 *  answered; an Apple/Google-first account-only session (its `acct_` key is
 *  minted only by a verified account sign-in, so it is verified by
 *  construction); otherwise unknown. Unknown is NOT verified. */
export function subscriptionSessionState(s: SubscriptionSessionInput): SubscriptionSessionState {
  if (s.isDemo) return 'demo';
  if (s.verification?.session_verified === true) return 'verified';
  if (s.verification?.session_verified === false) return 'unverified';
  if (s.user?.account_only === true && s.user.user_id.startsWith('acct_')) return 'verified';
  return 'unknown';
}

/** The RevenueCat appUserID this session may use, or null for none. */
export function purchasesIdentityTarget(s: SubscriptionSessionInput): string | null {
  return s.user && subscriptionSessionState(s) === 'verified' ? s.user.user_id : null;
}

/** May this session read RevenueCat CustomerInfo? `rcIdentityUserId` is the
 *  identity RevenueCat has COMPLETED (`api/purchases.currentIdentityUserId`). */
export function customerInfoApplies(
  s: SubscriptionSessionInput,
  rcIdentityUserId: string | null,
): boolean {
  return purchasesIdentityTarget(s) !== null && rcIdentityUserId === s.user?.user_id;
}
