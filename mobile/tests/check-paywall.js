#!/usr/bin/env node
// Paywall / IAP structural guard (docs/plans/monetization/iap-enablement/,
// flags `monetize.paywall` + `monetize.entitlements`, both dark).
//
// WHY THIS EXISTS. Everything below is a claim about client SHAPE — a route's
// presentation, a disclosure string's presence, an env guard sitting BEFORE a
// side effect, a component NOT being mounted. None of it is visible to `tsc`,
// none of it to a backend test, and D-056 retired the simulator. Worse, the
// two most expensive failures here are silent: an App Store rejection under
// guideline 3.1.2 (a missing disclosure looks like working code) and a
// crash-on-launch in a build with no RevenueCat key (a `configure` call that
// escaped its guard runs on every user's device, not just the paywall's).
//
// What is pinned, and why each is a real regression rather than a style note:
//   1. PaywallScreen exists and is registered EXACTLY ONCE, as a root-stack
//      MODAL, and never in a tab stack. Presentation is load-bearing: a push
//      would leave the purchase decision in the navigation hierarchy, and a
//      tab registration would change which FeedbackFAB rule applies (#188).
//   2. The route is registered UNCONDITIONALLY and the SCREEN self-guards on
//      `monetize.paywall`. Wrapping <Stack.Screen> in the flag unmounts an
//      in-flight push during flag revalidation.
//   3. Guideline 3.1.2 copy is rendered: price+period, trial terms, the
//      auto-renew + cancel disclosure. Apple rejects on any one of these.
//   4. Restore Purchases is WIRED, not merely labelled — the handler calls
//      restorePurchases(). Guideline 3.1.1.
//   5. Privacy Policy + Terms are tappable and point at /privacy and /terms.
//   6. No FeedbackFAB in the modal (#188 exception — a second FAB is the
//      #196/#197 bug).
//   7. api/purchases.ts is the ONLY module importing react-native-purchases,
//      and it checks the SDK key BEFORE any configure/purchase call. The
//      single-importer rule is what makes the fail-safe auditable at all.
//   8. The Settings entry row is flag-gated on `monetize.paywall` and exists
//      on BOTH settings surfaces (the hub and the flag-off flat list), since
//      exactly one of them mounts depending on `account.settings_hub`.
//   9. All five paywall_* analytics events fire from the screen, spelled as
//      the backend taxonomy registers them.
//  10. The entitlement store never persists a client-derived unlock and never
//      lets a device receipt REVOKE. Server truth (check_pro) must be able to
//      take Pro away; a receipt must never be able to grant it durably.
//
// Run: node tests/check-paywall.js   (or npm run test:paywall)

'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SRC = path.join(ROOT, 'src');
const SCREEN = path.join(ROOT, 'src/screens/PaywallScreen.tsx');
const PURCHASES = path.join(ROOT, 'src/api/purchases.ts');
const BILLING = path.join(ROOT, 'src/api/billing.ts');
const ENTITLEMENTS = path.join(ROOT, 'src/state/useEntitlements.ts');
const ROOTNAV = path.join(ROOT, 'src/navigation/RootNav.tsx');
const TABNAV = path.join(ROOT, 'src/navigation/TabNav.tsx');
const HUB = path.join(ROOT, 'src/screens/settings/SettingsHubScreen.tsx');
const FLAT = path.join(ROOT, 'src/screens/SettingsScreen.tsx');

const pass = [], fail = [];
const ok = (n) => pass.push(n);
const bad = (n, d) => fail.push(`${n}\n      ${d}`);
const read = (p) => (fs.existsSync(p)
  ? fs.readFileSync(p, 'utf8')
  : (bad('file exists', `missing ${path.relative(ROOT, p)}`), ''));
// Comments are stripped before every content assertion: a disclosure quoted in
// a header banner is not a disclosure the user sees.
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

const screenRaw = read(SCREEN);
const s = strip(screenRaw);
const purchases = strip(read(PURCHASES));
const billing = strip(read(BILLING));
const entl = strip(read(ENTITLEMENTS));
const rootnav = strip(read(ROOTNAV));
const tabnav = strip(read(TABNAV));
const hub = strip(read(HUB));
const flat = strip(read(FLAT));

// 1 — exists, registered exactly once, as a modal, root stack only
{
  const hits = (rootnav.match(/name="Paywall"/g) || []).length;
  const inTab = /name="Paywall"/.test(tabnav);
  const block = rootnav.match(/<Stack\.Screen[^>]*\n?[\s\S]{0,400}?name="Paywall"[\s\S]{0,400}?\/>/)
    || rootnav.match(/name="Paywall"[\s\S]{0,400}?\/>/);
  const modal = !!(block && /presentation:\s*'modal'/.test(block[0]));
  if (!screenRaw) {
    bad('1a. PaywallScreen.tsx exists', 'src/screens/PaywallScreen.tsx not found');
  } else if (hits !== 1) {
    bad('1b. registered exactly once on the root stack',
      `found ${hits} <Stack.Screen name="Paywall"> in RootNav.tsx — two ` +
      'registrations give one screen two presentations and two back behaviors.');
  } else if (inTab) {
    bad('1c. NOT registered in a tab stack',
      'Paywall appears in TabNav.tsx. A tab-stack screen is covered by ' +
      "RootNav's global FeedbackFAB, and a purchase surface does not belong " +
      'in the tab hierarchy at all.');
  } else if (!modal) {
    bad('1d. registered with presentation: \'modal\'',
      'the Paywall <Stack.Screen> has no presentation:\'modal\'. A push leaves ' +
      'the purchase decision in the navigation hierarchy, so dismissing it no ' +
      'longer returns the user exactly where they were.');
  } else ok('1. PaywallScreen exists, registered once, root-stack MODAL only');
}

// 2 — route unconditional; the SCREEN carries the flag gate
{
  const wrapped = /\{\s*paywall(On|Enabled)[\s\S]{0,120}<Stack\.Screen[\s\S]{0,200}name="Paywall"/.test(rootnav);
  const selfGuard = /useFlag\(\s*'monetize\.paywall'\s*\)/.test(s)
    && /if\s*\(\s*!paywallOn\s*\)/.test(s);
  if (wrapped) {
    bad('2a. route registered unconditionally',
      'the <Stack.Screen name="Paywall"> is inside a flag conditional. A flag ' +
      'gates the ENTRY POINT, not the navigator entry — gating the route ' +
      'unmounts an in-flight push the moment revalidateFlags lands.');
  } else if (!selfGuard) {
    bad('2b. the screen self-guards on monetize.paywall',
      'PaywallScreen does not read useFlag(\'monetize.paywall\') and refuse ' +
      'when it is off. With the route registered unconditionally, the screen ' +
      'is the ONLY thing standing between a stale push and a live paywall.');
  } else ok('2. route registered unconditionally; PaywallScreen self-guards on the flag');
}

// 3 — guideline 3.1.2 copy, all of it, all rendered
{
  const problems = [];
  if (!/Auto-renews until cancelled/.test(s)) {
    problems.push('no auto-renew sentence ("Auto-renews until cancelled…")');
  }
  if (!/Cancel anytime in Settings/.test(s)) {
    problems.push('no cancellation instructions ("Cancel anytime in Settings ▸ Subscriptions.")');
  }
  if (!/days free, then/.test(s)) {
    problems.push('no trial-terms line ("N days free, then <price>") — a trial with '
      + 'no stated conversion price is the classic 3.1.2 rejection');
  }
  // price + period: the suffix map is what turns "$34.99" into "$34.99/year".
  if (!/\/year/.test(s) || !/\/month/.test(s)) {
    problems.push('no period suffix map (/year, /month) — a bare price is not a '
      + 'price AND period');
  }
  // The disclosure must not be hidden behind a data-loading branch.
  if (!/AUTO_RENEW_COPY/.test(s)) {
    problems.push('the auto-renew copy is not rendered through a constant the '
      + 'screen always emits');
  }
  if (problems.length === 0) {
    ok('3. guideline 3.1.2 copy present: price+period, trial terms, auto-renew + cancel');
  } else {
    bad('3. guideline 3.1.2 copy is complete', problems.join('; '));
  }
}

// 4 — Restore Purchases is wired, not decorative
{
  const hasId = /testID="paywall-restore"/.test(s);
  const imported = /restorePurchases/.test(s) && /from '\.\.\/api\/purchases'/.test(s);
  const called = /await restorePurchases\(/.test(s);
  const refreshes = /refreshEntitlements\(\)/.test(s);
  if (hasId && imported && called && refreshes) {
    ok('4. Restore Purchases calls restorePurchases() and refreshes entitlements');
  } else {
    bad('4. Restore Purchases is wired',
      `testID:${hasId} imported:${imported} called:${called} refresh:${refreshes} — ` +
      'a Restore button that does not call restorePurchases() is a 3.1.1 ' +
      'rejection AND a dead end for every user who reinstalled.');
  }
}

// 5 — legal links, tappable, to the right paths
{
  const privacy = /testID="paywall-privacy-link"/.test(s) && /'\/privacy'/.test(s);
  const terms = /testID="paywall-terms-link"/.test(s) && /'\/terms'/.test(s);
  const opens = /Linking\.openURL\(/.test(s) && /getBaseUrl\(\)/.test(s);
  if (privacy && terms && opens) {
    ok('5. Privacy Policy + Terms are tappable and open /privacy and /terms on the API origin');
  } else {
    bad('5. legal links present and tappable',
      `privacy:${privacy} terms:${terms} openURL+origin:${opens} — guideline ` +
      '3.1.2 requires both links ON the purchase screen, and a hardcoded ' +
      'origin drifts the moment the deploy target moves.');
  }
}

// 6 — no FeedbackFAB in the modal (#188 exception)
{
  if (/<FeedbackFAB/.test(s) || /FeedbackFAB/.test(s)) {
    bad('6. no FeedbackFAB in the paywall modal',
      'PaywallScreen mounts a FeedbackFAB. Modals are the documented #188 ' +
      'exception; a FAB here floats over a StoreKit purchase flow and is the ' +
      '#196/#197 double-FAB bug in the making.');
  } else ok('6. no FeedbackFAB in the paywall modal (#188 exception honored)');
}

// 7 — one importer of the SDK, and the key guard sits before any side effect
{
  const walk = (dir, out = []) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) walk(p, out);
      else if (/\.(ts|tsx)$/.test(e.name)) out.push(p);
    }
    return out;
  };
  const importers = walk(SRC).filter((f) =>
    /['"`]react-native-purchases['"`]/.test(strip(fs.readFileSync(f, 'utf8'))));
  const rel = importers.map((f) => path.relative(ROOT, f)).sort();
  if (rel.length !== 1 || rel[0] !== 'src/api/purchases.ts') {
    bad('7a. api/purchases.ts is the only module importing react-native-purchases',
      `importers: ${rel.join(', ') || '(none)'} — one seam is what makes the ` +
      'no-key / Expo Go fail-safe auditable. A second importer can call the ' +
      'SDK without ever passing the guard.');
  } else ok('7a. react-native-purchases is imported in exactly one module');

  const readsKey = /process\.env\.EXPO_PUBLIC_REVENUECAT_IOS_KEY/.test(purchases);
  // The lazy SDK handle must refuse before it ever hands the SDK out.
  const guardBeforeSdk = /if\s*\(!API_KEY[\s\S]{0,80}return null/.test(purchases);
  const configureGuarded = /const P = sdk\(\);\s*\n\s*if \(!P/.test(purchases);
  const noLogOut = !/\.logOut\(/.test(purchases);
  if (readsKey && guardBeforeSdk && configureGuarded && noLogOut) {
    ok('7b. purchases.ts checks EXPO_PUBLIC_REVENUECAT_IOS_KEY before any SDK call, and never logs out');
  } else {
    bad('7b. purchases.ts guards on the SDK key (and never calls logOut)',
      `readsKey:${readsKey} guardBeforeSdk:${guardBeforeSdk} ` +
      `configureGuarded:${configureGuarded} noLogOut:${noLogOut} — an ` +
      'unguarded configure() runs on every device in a build with no key, and ' +
      'logOut() re-anonymizes the RevenueCat identity on sign-out.');
  }
}

// 8 — the Settings entry row, flag-gated, on BOTH settings surfaces
{
  const rowIn = (text) =>
    /testID="settings-pro-row"/.test(text)
    && /'Paywall'\s*,\s*\{\s*source:\s*'settings'\s*\}/.test(text)
    && /useFlag\(\s*'monetize\.paywall'\s*\)/.test(text);
  const hubOk = rowIn(hub);
  const flatOk = rowIn(flat);
  if (hubOk && flatOk) {
    ok('8. flag-gated "Fleeced Pro" row navigates to Paywall {source:\'settings\'} on both settings surfaces');
  } else {
    bad('8. the Settings entry row exists on both settings surfaces',
      `hub:${hubOk} flat:${flatOk} — \`account.settings_hub\` decides which of ` +
      'the two mounts (it is TRUE in config/features.json today), so a row on ' +
      'only one of them makes the paywall unreachable in the other state.');
  }
}

// 9 — the five taxonomy event names, spelled exactly
{
  const EVENTS = [
    'paywall_viewed',
    'paywall_purchase_initiated',
    'paywall_purchase_completed',
    'paywall_purchase_failed',
    'paywall_restore',
  ];
  const missing = EVENTS.filter((e) => !new RegExp(`track\\('${e}'`).test(s));
  if (missing.length === 0) {
    ok(`9. all ${EVENTS.length} paywall_* events fire from PaywallScreen`);
  } else {
    bad('9. every paywall_* event fires from the screen',
      `missing: ${missing.join(', ')} — the backend taxonomy registers these ` +
      'names; an emitter that drifts from them lands as a rejected event, not ' +
      'as a renamed one.');
  }
}

// 10 — the client cache can raise, never grant durably, never revoke
{
  const marker = /client receipts are never trusted/i.test(read(ENTITLEMENTS));
  const raisesOnly = /if \(proActive && !get\(\)\.pro\)/.test(entl);
  // The optimistic path must not write the cache; only refresh() persists.
  const noteBody = entl.match(/noteCustomerInfo:\s*\(proActive\)\s*=>\s*\{[\s\S]*?\n  \}/);
  const noPersist = !!noteBody && !/setItem/.test(noteBody[0]);
  const serverFetch = /getEntitlements\(\)/.test(entl)
    && /\/api\/me\/entitlements/.test(billing);
  if (marker && raisesOnly && noPersist && serverFetch) {
    ok('10. entitlement cache: server-authoritative fetch; receipts raise only, never persist');
  } else {
    bad('10. the entitlement cache never outranks the server',
      `marker:${marker} raisesOnly:${raisesOnly} noPersist:${noPersist} ` +
      `serverFetch:${serverFetch} — a persisted client-derived unlock survives ` +
      'a relaunch and impersonates a server answer inside the 72h grace window; ' +
      'a receipt that can set pro=false lets an SDK cache miss look like a refund.');
  }
}

// ── Report ────────────────────────────────────────────────────────────────
for (const p of pass) console.log(`PASS  ${p}`);
for (const f of fail) console.error(`FAIL  ${f}`);
console.log(`\ncheck-paywall: ${pass.length} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
