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

// The two cookie names the capture flow owns. Used by the targeted clear —
// never clearAll: the native store is app-wide (Sleeper's web session lives
// there too).
const ESPN_COOKIE_NAMES = ['espn_s2', 'SWID'] as const;

// Disney OneID SSO hosts (ESPN's login IS Disney SSO — the /login page
// bootstraps a registerdisney iframe). A surviving Disney session cookie
// here silently re-authenticates the PREVIOUS account with no password
// prompt, which is exactly the account-switch trap from the 2026-08-12
// incident: the operator signed in with a friend's ESPN account and could
// never sign in as themselves again. Cleared alongside the espn.com pair so
// sign-in always starts genuinely unauthenticated. These hosts — plus
// ESPN_COOKIE_DOMAINS above — are the ENTIRE clear surface; nothing outside
// espn.com/Disney-SSO domains is ever touched.
export const DISNEY_SSO_DOMAINS = [
  'https://registerdisney.go.com',
  'https://cdn.registerdisney.go.com',
] as const;

/**
 * Clear every cookie currently set for ONE ESPN/Disney domain, by name —
 * enumerate what that domain carries, then clearByName each. Scoped by
 * construction: only names found on `domain` are cleared, and only from
 * `domain` — cookies for any other site are untouchable from here. Never
 * clearAll (the native store is app-wide).
 */
async function clearDomainCookies(domain: string, useWebKit: boolean): Promise<void> {
  try {
    const bag = await CookieManager.get(domain, useWebKit);
    await Promise.all(
      Object.keys(bag ?? {}).map((name) =>
        CookieManager.clearByName(domain, name, useWebKit).catch(() => {}),
      ),
    );
  } catch {
    /* enumeration failed — the named espn_s2/SWID clears still run */
  }
}

/**
 * Clear the ESPN + Disney-SSO web session so every capture is a FRESH login.
 * Without this, a stale pair left from a prior session/capture gets
 * "captured" ~1s after mount — before the user can even see the login — and
 * (2026-08-12 incident) a surviving session re-authenticates WHOEVER was
 * last signed in, making it impossible to switch ESPN accounts even after
 * the stored credential is deleted server-side.
 *
 * Two layers, both scoped to ESPN/Disney domains only — never clearAll (the
 * native store is app-wide; Sleeper's web session lives there too):
 *   1. enumerate-and-clear every cookie on each ESPN + Disney SSO domain
 *      (kills the full login session, not just the two captured cookies);
 *   2. named clears of espn_s2/SWID (belt & braces if enumeration fails).
 * Both native stores are hit (WKHTTPCookieStore via useWebKit:true AND
 * NSHTTPCookieStorage — the screen's sharedCookiesEnabled syncs between
 * them, so a survivor in either would resurface). Failures are swallowed
 * per name: a partial clear still beats no clear, and the WebView only
 * mounts after this settles.
 */
export async function clearEspnCookies(): Promise<void> {
  const domains: string[] = [...ESPN_COOKIE_DOMAINS, ...DISNEY_SSO_DOMAINS];
  await Promise.all(
    domains.flatMap((domain) => [
      clearDomainCookies(domain, true),
      clearDomainCookies(domain, false),
    ]),
  );
  const named: Promise<unknown>[] = [];
  for (const domain of ESPN_COOKIE_DOMAINS) {
    for (const name of ESPN_COOKIE_NAMES) {
      named.push(CookieManager.clearByName(domain, name, true).catch(() => {}));
      named.push(CookieManager.clearByName(domain, name, false).catch(() => {}));
    }
  }
  await Promise.all(named);
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
