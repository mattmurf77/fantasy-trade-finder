// espnNavPolicy.ts — pure allow/block decision for every navigation the ESPN
// Connect WebView attempts (2026-08-09 field failure: mid-login Safari escape).
//
// Why this exists: react-native-webview's `originWhitelist` has a fallback its
// name does not advertise — any navigation whose origin fails the whitelist is
// handed to `Linking.openURL` (WebViewShared's createOnShouldStartLoadWithRequest),
// i.e. punted OUT of the app: Safari for http(s) URLs, a native app for custom
// schemes. EspnConnectScreen previously shipped `originWhitelist={['https://*']}`
// with no `onShouldStartLoadWithRequest`, and the whitelist gate sees EVERY
// navigation action — subframes (Disney SSO is an embedded iframe) and popups
// (iOS routes window.open/target=_blank back into the same WebView) included.
// So any http:// hop, ad-iframe request, or popup that failed `https://*`
// bounced the user into Safari mid-login. That is the reported bug 1.
//
// The fix inverts the posture: the WebView passes EVERYTHING
// (`originWhitelist={['*']}`) to this function, which either keeps the
// navigation inside the WebView or swallows it. Nothing is EVER opened
// externally from the login flow — no Linking.openURL on any path.
//
// Zero runtime imports on purpose: tests/check-espn-nav-policy.js transpiles
// this file and runs it under plain node.

// Schemes that render inside the WebView and cannot leave the app.
// - http/https: the login chain itself (espn.com ↔ Disney SSO domains) plus
//   whatever ad/analytics/captcha subframes espn.com embeds. Unknown http(s)
//   hosts are deliberately ALLOWED: an in-WebView page load can't leave the
//   app by itself, while blocklisting unknown hosts risks breaking Disney SSO
//   the next time it adds a domain. Known app-bouncing hosts are the
//   exception (below).
// - about/data/blob: WKWebView internals (about:blank/srcdoc frames, inline
//   resources) — blocking them breaks iframe bootstrapping.
const IN_APP_SCHEMES = new Set(['http', 'https', 'about', 'data', 'blob']);

// http(s) hosts whose whole purpose is to bounce the user into another app or
// the App Store (smart-banner taps, "Open in ESPN app" interstitials, branch/
// AppsFlyer/Firebase link routers). A load of these inside the WebView either
// universal-links out of the app or dead-ends the login — swallow instead.
// Matched by host suffix (exact label boundary).
const BLOCKED_HOST_SUFFIXES = [
  'apps.apple.com',
  'itunes.apple.com',
  'app.link', // branch.io (espn.app.link)
  'smart.link',
  'onelink.me', // AppsFlyer
  'page.link', // Firebase dynamic links
] as const;

function hostMatches(host: string, suffix: string): boolean {
  return host === suffix || host.endsWith('.' + suffix);
}

/**
 * Decide whether the ESPN Connect WebView should perform a navigation.
 * Returns true to load it inside the WebView, false to swallow it entirely
 * (the caller must never hand a blocked URL to Linking/the OS).
 *
 * Pure — string in, boolean out — so the node test can pin every escape
 * class: app schemes (espn://, sportscenter://, itms-appss://), http hops,
 * App Store / deep-link-router hosts, SSO iframe bootstraps.
 */
export function allowEspnNavigation(url: string): boolean {
  const schemeMatch = /^([a-z][a-z0-9+.-]*):/i.exec(url || '');
  if (!schemeMatch) return false; // schemeless/garbage — nothing to load
  const scheme = schemeMatch[1].toLowerCase();
  if (!IN_APP_SCHEMES.has(scheme)) return false; // app-scheme hop — swallow
  if (scheme !== 'http' && scheme !== 'https') return true; // about/data/blob

  // Extract the host: strip any userinfo@ and :port.
  const hostMatch = /^[a-z][a-z0-9+.-]*:\/\/([^/?#]*)/i.exec(url);
  const authority = hostMatch ? hostMatch[1] : '';
  const host = (authority.split('@').pop() || '').split(':')[0].toLowerCase();
  if (!host) return false;
  for (const suffix of BLOCKED_HOST_SUFFIXES) {
    if (hostMatches(host, suffix)) return false;
  }
  return true;
}
