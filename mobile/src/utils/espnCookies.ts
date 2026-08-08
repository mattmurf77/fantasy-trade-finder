// espnCookies.ts — extract ESPN's espn_s2 + SWID from the NATIVE cookie store.
//
// ESPN Connect WebView (Phase 1b, docs/plans/espn-connect-webview/scope.md).
// espn_s2 is issued HttpOnly, so the WebView's `document.cookie` cannot see
// it — injected JS is a dead end. The cookies live in the native cookie
// store (WKHTTPCookieStore on iOS, shared with the WebView because the screen
// sets sharedCookiesEnabled), which @react-native-cookies/cookies reads via
// CookieManager.get(url). See DECISIONS.md D-021.
//
// ESPN drops these two cookies across more than one host after a Disney SSO
// login, so we poll multiple domains and take the first store that carries
// BOTH. The only thing this module ever exposes is the two cookie strings —
// never anything else from the store.

import CookieManager from '@react-native-cookies/cookies';

/** The two ESPN credentials the private-league link flow needs. */
export interface EspnCookiePair {
  espnS2: string;
  swid: string;
}

// Domains ESPN sets espn_s2 / SWID on after a Disney SSO login. Checked in
// order; the first store carrying BOTH wins. www.espn.com is where the login
// lands; fantasy.espn.com is where the private-league reads happen and is the
// host the backend replays the cookies against.
export const ESPN_COOKIE_DOMAINS = [
  'https://www.espn.com',
  'https://fantasy.espn.com',
] as const;

// The @react-native-cookies/cookies get() result: a map of cookie name → the
// cookie object. We only ever read `.value`. Typed loosely here so the pure
// extractor can be unit-tested without importing the native module.
type CookieBag = Record<string, { value?: string } | undefined>;

/**
 * Pure extractor — given the CookieManager.get() results for each domain (in
 * ESPN_COOKIE_DOMAINS order), return the first pair where BOTH cookies are
 * present and non-empty, else null. No side effects, no native calls — this
 * is the unit-tested core (tests/check-espn-cookies.js).
 *
 * SWID is passed through verbatim (it includes the surrounding braces, which
 * is exactly what POST /api/espn/link and the manual-paste field expect).
 */
export function pickEspnCookies(bags: (CookieBag | null | undefined)[]): EspnCookiePair | null {
  for (const bag of bags) {
    if (!bag) continue;
    const espnS2 = bag['espn_s2']?.value?.trim();
    const swid = bag['SWID']?.value?.trim();
    if (espnS2 && swid) return { espnS2, swid };
  }
  return null;
}

/**
 * Read the native cookie store for both ESPN domains and return the captured
 * pair, or null if either cookie is missing everywhere. Called on a poll and
 * on WebView navigation changes; the caller guards against delivering twice.
 */
export async function readEspnCookies(): Promise<EspnCookiePair | null> {
  try {
    const bags = await Promise.all(
      ESPN_COOKIE_DOMAINS.map((d) =>
        CookieManager.get(d).catch(() => null) as Promise<CookieBag | null>,
      ),
    );
    return pickEspnCookies(bags);
  } catch {
    // Native store unavailable — treat as "not captured yet", never throw
    // into the poll loop.
    return null;
  }
}
