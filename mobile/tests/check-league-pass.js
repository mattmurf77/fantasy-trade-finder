#!/usr/bin/env node
// check-league-pass — the league pass client (flag `monetize.league_pass`,
// dark; docs/plans/monetization/league-pass/lld.md §8, D-281).
//
// WHY THIS EXISTS. Every failure this file pins is SILENT in a running app,
// and D-056 retired the simulator, so none of them is caught by looking:
//   - the flag-off build asking the server for `caps=league_pass`, or showing
//     a pass entry, so the launch binary is no longer "exactly today";
//   - a pre-check that reads account `pro` where the server's gate reads the
//     league, so a covered member is sent to the paywall in the league their
//     pass covers (or worse, a pass for league A unlocks league B in the UI);
//   - an expired `covered_until` still read as coverage;
//   - the sign-out reset leaving the last account's passes in memory;
//   - the purchase screen showing a discounted first-year price and charging
//     the list price (or the reverse) when Apple's promotional offer can't be
//     signed;
//   - a 409 refusal reason with no copy of its own, or a copy key missing
//     from copy/monetization.ts;
//   - an interactive element with no testID.
//
// HOW. It TRANSPILES AND EXECUTES the real modules under plain node, with
// throwing stubs for any import it didn't expect:
//   - utils/leaguePass.ts (zero imports): coverage, the purchase path, the
//     refusal table, the notice, the config path;
//   - copy/monetization.ts: every mon.lp key the sources use exists;
//   - api/billing.ts against a recording `api`: the request paths, flag off
//     and on;
//   - api/purchases.ts against a fake RevenueCat SDK: the league offering,
//     intro eligibility, the signed promotional offer, the discounted buy;
//   - state/useEntitlements.ts + state/accountReset.ts: passes stored,
//     overwritten and cleared;
//   - state/useLeaguePass.ts: `proForLeagueNow`, flag off and on;
//   - SendInSleeperButton's `sendPreCheck` (the function's own text);
//   - components/LeaguePassRows.tsx under a fake React: flag off renders
//     nothing; flag on renders the member / buyer / unbound rows.
// What it can only READ (screens' JSX, the gate sites) it pins structurally,
// and says so in the name ("[shape]").
//
// Run: node tests/check-league-pass.js   (or npm run test:league-pass)

'use strict';

const fs = require('fs');
const path = require('path');

let ts;
try {
  ts = require('typescript');
} catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}

const ROOT = path.resolve(__dirname, '..');
const SRC = path.join(ROOT, 'src');
const REPO = path.resolve(ROOT, '..');
const read = (rel) => fs.readFileSync(path.join(SRC, rel), 'utf8');
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"`])\/\/.*$/gm, '$1');

let failures = 0;
let passes = 0;
const tests = [];
function check(name, fn) { tests.push({ name, fn }); }
function assert(cond, msg) { if (!cond) throw new Error(msg); }
function eq(a, b, msg) {
  if (a !== b) throw new Error(`${msg}: expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`);
}

function load(rel, stubs, globals = {}) {
  const js = ts.transpileModule(read(rel), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019, jsx: ts.JsxEmit.React },
    fileName: path.basename(rel),
  }).outputText;
  const mod = { exports: {} };
  const req = (name) => {
    if (Object.prototype.hasOwnProperty.call(stubs, name)) return stubs[name];
    throw new Error(`${rel} gained an unexpected runtime import ("${name}") — stub it here deliberately.`);
  };
  const names = Object.keys(globals);
  // eslint-disable-next-line no-new-func
  new Function('module', 'exports', 'require', ...names, js)(mod, mod.exports, req, ...names.map((n) => globals[n]));
  return mod.exports;
}

function makeCreate() {
  return function create(init) {
    let state;
    const listeners = new Set();
    const setState = (p) => {
      const prev = state;
      state = Object.assign({}, state, typeof p === 'function' ? p(state) : p);
      listeners.forEach((l) => l(state, prev));
    };
    const getState = () => state;
    state = init(setState, getState);
    const hook = (sel) => (sel ? sel(state) : state);
    hook.getState = getState;
    hook.setState = setState;
    hook.subscribe = (l) => { listeners.add(l); return () => listeners.delete(l); };
    return hook;
  };
}
function makeStorage(seed = {}) {
  const m = new Map(Object.entries(seed));
  return {
    map: m,
    default: {
      getItem: async (k) => (m.has(k) ? m.get(k) : null),
      setItem: async (k, v) => { m.set(k, v); },
      removeItem: async (k) => { m.delete(k); },
      getAllKeys: async () => [...m.keys()],
      multiRemove: async (ks) => { for (const k of ks) m.delete(k); },
    },
  };
}
const tick = () => new Promise((r) => setTimeout(r, 0));
const settle = async () => { for (let i = 0; i < 6; i++) await tick(); };

const NOW = Date.parse('2026-11-24T12:00:00Z');
const FUTURE = '2027-11-24T12:00:00+00:00';
const PAST = '2026-11-01T00:00:00+00:00';
const pass = (league_id, role = 'member', covered_until = FUTURE, buyer_display = null) =>
  ({ league_id, platform: 'sleeper', role, covered_until, buyer_display });

// ═══ 1. utils/leaguePass.ts — executed, no stubs ══════════════════════════
const lp = load('utils/leaguePass.ts', {});

check('1a. proForLeague truth table: pro always wins; flag off is exactly `pro`; a pass counts only for ITS league and only while covered_until is in the future', () => {
  const P = lp.proForLeague;
  const live = [pass('L1')];
  eq(P(true, [], 'L1', false, NOW), true, 'pro, flag off');
  eq(P(true, [], 'L9', true, NOW), true, 'pro, flag on, no pass');
  eq(P(false, live, 'L1', false, NOW), false, 'flag OFF + a live pass for this league → still pro (false)');
  eq(P(false, live, 'L1', true, NOW), true, 'flag on + a live pass for this league');
  eq(P(false, live, 'L2', true, NOW), false, 'another league');
  eq(P(false, [pass('L1', 'member', PAST)], 'L1', true, NOW), false, 'expired covered_until');
  eq(P(false, [pass('L1', 'member', 'not-a-date')], 'L1', true, NOW), false, 'unreadable covered_until');
  eq(P(false, [pass('L1', 'member', null)], 'L1', true, NOW), false, 'missing covered_until');
  eq(P(false, live, null, true, NOW), false, 'no league');
  eq(P(false, live, undefined, true, NOW), false, 'undefined league');
  eq(P(false, null, 'L1', true, NOW), false, 'no passes');
  eq(P(false, [pass('L1', 'buyer')], 'L1', true, NOW), true, 'the buyer\'s own league entry counts too');
  // the boundary: covered_until == now is NOT covered
  eq(P(false, [pass('L1', 'member', new Date(NOW).toISOString())], 'L1', true, NOW), false, 'covered_until == now');
});

check('1b. R26 coveredElsewhere: a live pass in ANOTHER league while nothing covers this one; null when covered here, nowhere, or only expired', () => {
  const C = lp.coveredElsewhere;
  eq(C([pass('L1')], 'L2', NOW)?.league_id, 'L1', 'covered in L1, viewing L2');
  eq(C([pass('L1')], 'L1', NOW), null, 'covered here');
  eq(C([pass('L1', 'member', PAST)], 'L2', NOW), null, 'only an expired pass');
  eq(C([], 'L2', NOW), null, 'nothing');
  eq(C([pass('L1'), pass('L2')], 'L2', NOW), null, 'covered here and elsewhere → no line');
});

check('1c. the tier → purchase path: tier 0 standard; tier 1/2 intro-eligible → intro; else a signed promo → promo; else full price. Only promo uses the discounted call', () => {
  const F = lp.purchasePathFor;
  eq(F(0, true, true), 'standard', 'tier 0 ignores intro and promo');
  for (const t of [1, 2]) {
    eq(F(t, true, true), 'intro', `tier ${t} eligible`);
    eq(F(t, true, false), 'intro', `tier ${t} eligible, no promo`);
    eq(F(t, false, true), 'promo', `tier ${t} not eligible, promo signed`);
    eq(F(t, false, false), 'full_price', `tier ${t} neither`);
  }
  eq(lp.purchaseCallFor('promo'), 'discounted', 'promo → purchaseDiscountedPackage');
  for (const p of ['standard', 'intro', 'full_price']) eq(lp.purchaseCallFor(p), 'package', `${p} → purchasePackage`);
});

check('1d. NEVER ONE PRICE SHOWN AND ANOTHER CHARGED: the plan\'s year-one price is the price of the path that runs; the fallback shows the full price only, with its notice', () => {
  const base = { storeAvailable: true, standardPrice: '$99.99', introPrice: '$84.99', promoPrice: null, configYearOne: '$84.99', configRenewal: '$99.99' };
  // intro
  let p = lp.purchasePlan({ ...base, tier: 1, introEligible: true });
  eq(p.path, 'intro', 'intro path'); eq(p.yearOne, '$84.99', 'intro: StoreKit intro price'); eq(p.renewal, '$99.99', 'renews at list');
  eq(p.fullPriceNotice, false, 'no notice');
  // eligible but StoreKit shows no intro on the product → never "intro" (Apple would charge the list price)
  p = lp.purchasePlan({ ...base, tier: 1, introEligible: true, introPrice: null });
  assert(p.path !== 'intro', 'eligible with no intro price must not take the intro path');
  eq(p.yearOne, '$99.99', 'and shows the full price');
  // promo
  p = lp.purchasePlan({ ...base, tier: 2, introEligible: false, introPrice: '$69.99', promoPrice: '$69.99' });
  eq(p.path, 'promo', 'promo path'); eq(p.yearOne, '$69.99', 'promo: the signed offer\'s price');
  eq(lp.purchaseCallFor(p.path), 'discounted', 'promo runs the discounted call');
  // the fallback: no intro, no signed offer
  for (const tier of [1, 2]) {
    p = lp.purchasePlan({ ...base, tier, introEligible: false, promoPrice: null });
    eq(p.path, 'full_price', `tier ${tier} fallback path`);
    eq(p.yearOne, '$99.99', `tier ${tier} fallback: year one is the FULL price`);
    eq(p.renewal, '$99.99', `tier ${tier} fallback: renewal`);
    assert(p.yearOne !== base.configYearOne, `tier ${tier} fallback never shows the config's discounted year-one price`);
    eq(p.fullPriceNotice, true, `tier ${tier} fallback says so`);
    eq(p.canBuy, true, 'and can still be bought (by choice)');
    eq(lp.purchaseCallFor(p.path), 'package', 'at the list price, via purchasePackage');
  }
  // tier 0
  p = lp.purchasePlan({ ...base, tier: 0, introEligible: true, promoPrice: '$1.00' });
  eq(p.path, 'standard', 'tier 0'); eq(p.yearOne, '$99.99', 'tier 0 is the list price whatever StoreKit offers');
  // no StoreKit: nothing can be bought; the server's strings are display only
  p = lp.purchasePlan({ ...base, storeAvailable: false, standardPrice: null, tier: 1, introEligible: false });
  eq(p.canBuy, false, 'no StoreKit → cannot buy'); eq(p.yearOne, '$84.99', 'config year one'); eq(p.renewal, '$99.99', 'config renewal');
  eq(p.fullPriceNotice, false, 'no notice without a purchase');
});

// The refusal reasons the user routes send, read from the API reference so a
// new server reason without copy fails here.
const API_REF = fs.readFileSync(path.join(REPO, 'docs/api-reference.md'), 'utf8');
const lpRows = API_REF.split('\n').filter((l) => /^\| (GET|POST|PUT)[^|]*\| `\/api\/league-pass/.test(l));
const REASONS = new Set();
for (const row of lpRows) {
  const tail = row.slice(row.indexOf('409'));
  // Backticked words after "409" are reasons, except a detail field the
  // row names alongside one (`cooldown` carries `can_repoint_at`).
  if (row.includes('409')) for (const m of tail.matchAll(/`([a-z_]+)`/g)) if (m[1] !== 'can_repoint_at') REASONS.add(m[1]);
}

check('1e. every 409 reason the /api/league-pass routes document maps to its OWN copy key; an unknown reason gets the generic line; refusalReason reads only a 409 body', () => {
  assert(lpRows.length >= 5, `found ${lpRows.length} /api/league-pass rows in docs/api-reference.md`);
  for (const r of ['not_member', 'league_not_allowed', 'already_covered', 'already_buyer', 'refund_blocked', 'tier_mismatch', 'no_purchase', 'no_pass', 'cooldown']) {
    assert(REASONS.has(r), `api-reference no longer lists ${r} (positive control)`);
  }
  const keys = new Set();
  for (const r of REASONS) {
    const k = lp.refusalCopyKey(r);
    assert(k !== 'mon.lp.refused.generic', `${r} has no copy of its own`);
    keys.add(k);
  }
  eq(keys.size, REASONS.size, 'one key per reason');
  eq(lp.refusalCopyKey('something_new'), 'mon.lp.refused.generic', 'unknown → generic');
  eq(lp.refusalCopyKey(null), 'mon.lp.refused.generic', 'null → generic');
  eq(lp.refusalCopyKey('__proto__'), 'mon.lp.refused.generic', 'no prototype keys');
  eq(lp.refusalReason({ status: 409, body: { error: 'cooldown', can_repoint_at: FUTURE } }), 'cooldown', '409');
  eq(lp.refusalReason({ status: 402, body: { error: 'pro_required' } }), null, '402 is not a refusal');
  eq(lp.refusalReason({ status: 404, body: { error: 'feature_disabled' } }), null, '404');
  eq(lp.refusalReason(new Error('net')), null, 'network');
});

check('1f. the paywall config path: flag off is byte-identical to the launch request; flag on adds caps=league_pass', () => {
  eq(lp.paywallConfigPath('ios', false), '/api/paywall/config?platform=ios', 'flag off');
  eq(lp.paywallConfigPath('ios', true), '/api/paywall/config?platform=ios&caps=league_pass', 'flag on');
});

check('1g. R29 notice: due only for a flag-on individual subscriber (not a pass buyer alone) covered as a MEMBER in this league; key carries user and league', () => {
  const D = lp.coveredNoticeDue;
  const live = [pass('L1')];
  eq(D(true, ['apple_iap'], live, 'L1', true, NOW), true, 'annual subscriber, covered here');
  eq(D(true, ['apple_iap'], live, 'L1', false, NOW), false, 'flag off');
  eq(D(false, [], live, 'L1', true, NOW), false, 'not a subscriber');
  eq(D(true, ['league_pass_iap'], [pass('L1', 'buyer')], 'L1', true, NOW), false, 'the buyer is not told about their own pass');
  eq(D(true, ['manual_grant'], live, 'L1', true, NOW), false, 'a manual grant is not an individual subscription');
  eq(D(true, ['apple_iap'], live, 'L2', true, NOW), false, 'another league');
  eq(D(true, ['apple_iap'], [pass('L1', 'member', PAST)], 'L1', true, NOW), false, 'expired');
  const k = lp.coveredNoticeKey('U1', 'L1');
  assert(k.includes('U1') && k.includes('L1') && k !== lp.coveredNoticeKey('U2', 'L1') && k !== lp.coveredNoticeKey('U1', 'L2'), 'per user AND league');
  eq(lp.looksUnbound(true, ['league_pass_iap'], [], NOW), true, 'league product, no buyer entry');
  eq(lp.looksUnbound(true, ['league_pass_iap'], [pass('L1', 'buyer')], NOW), false, 'bound');
  eq(lp.looksUnbound(true, ['apple_iap'], [], NOW), false, 'an individual plan');
});

check('1h. dates and slots: passDate is the copy\'s date style or null; fill inserts values literally', () => {
  eq(lp.passDate('2027-01-15T12:00:00+00:00'), 'January 15, 2027', 'date');
  eq(lp.passDate('garbage'), null, 'unreadable');
  eq(lp.passDate(null), null, 'null');
  eq(lp.fill('{a} and {b}', { a: '$&x', b: 2 }), '$&x and 2', 'literal');
  eq(lp.fill('{a} {missing}', { a: 'x' }), 'x {missing}', 'missing slot untouched');
});

// ═══ 2. copy/monetization.ts — the keys exist; no price literal; no em dash ═
const copy = load('copy/monetization.ts', { '../utils/supportContact': load('utils/supportContact.ts', {}) });
const NEW_FILES = [
  'utils/leaguePass.ts', 'state/useLeaguePass.ts', 'screens/LeaguePassScreen.tsx',
  'components/LeaguePassRows.tsx', 'components/LeaguePassCoveredNotice.tsx',
];

check('2a. every mon.lp key the sources use exists in copy/monetization.ts, and every refusal key does', () => {
  const used = new Set();
  const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).forEach((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p);
    else if (/\.(ts|tsx)$/.test(e.name)) for (const m of strip(fs.readFileSync(p, 'utf8')).matchAll(/'(mon\.lp\.[a-z_.]+)'/g)) used.add(m[1]);
  });
  walk(SRC);
  assert(used.size >= 30, `found ${used.size} mon.lp keys in use (positive control)`);
  for (const k of used) assert(Object.prototype.hasOwnProperty.call(copy.MON, k), `${k} is used but not in MON`);
  for (const k of Object.values(lp.REFUSAL_COPY_KEY)) assert(copy.MON[k], `refusal key ${k} missing`);
  assert(copy.MON['mon.lp.refused.generic'], 'generic refusal');
});

check('2b. the mon.lp block: marked pending legal review; plain text — no hard-coded price, no em dash, no "free", no raw {league}', () => {
  const src = read('copy/monetization.ts');
  assert(/League pass[\s\S]{0,200}PENDING LEGAL REVIEW/.test(src), 'the block carries its pending-legal comment');
  const lpEntries = Object.entries(copy.MON).filter(([k]) => k.startsWith('mon.lp.'));
  assert(lpEntries.length >= 40, `${lpEntries.length} mon.lp keys`);
  for (const [k, v] of lpEntries) {
    assert(!/[$€£]\s?\d/.test(v), `${k} hard-codes a price: ${v}`);
    assert(!/—|–/.test(v), `${k} has an em/en dash: ${v}`);
    assert(!/\bfree\b/i.test(v), `${k} says "free": ${v}`);
    assert(!/\{league\}/.test(v), `${k} uses the invitee's {league} slot`);
  }
  for (const rel of NEW_FILES) {
    const s = strip(read(rel));
    assert(!/[$€£]\d/.test(s.replace(/\$\{/g, '')), `${rel} hard-codes a price`);
  }
});

// ═══ 3. api/billing.ts — the requests, flag off and on ════════════════════
check('3a. getPaywallConfig: flag off → exactly today\'s path (no caps); flag on → caps=league_pass; the pass routes hit their documented paths, 409 kept quiet', async () => {
  const calls = [];
  const flags = { 'monetize.league_pass': false };
  const api = {
    get: async (p, o) => { calls.push(['GET', p, undefined, o]); return {}; },
    post: async (p, b, o) => { calls.push(['POST', p, b, o]); return {}; },
    put: async (p, b, o) => { calls.push(['PUT', p, b, o]); return {}; },
  };
  const billing = load('api/billing.ts', {
    './client': { api },
    '../state/useFeatureFlags': { useFeatureFlags: { getState: () => ({ flags }) } },
    '../utils/leaguePass': lp,
  });
  await billing.getPaywallConfig('ios');
  eq(calls[0][1], '/api/paywall/config?platform=ios', 'flag off: the launch request');
  await billing.getPaywallConfig();
  eq(calls[1][1], '/api/paywall/config?platform=ios', 'flag off, default platform');
  flags['monetize.league_pass'] = true;
  await billing.getPaywallConfig('ios');
  eq(calls[2][1], '/api/paywall/config?platform=ios&caps=league_pass', 'flag on');
  calls.length = 0;
  await billing.createLeaguePassIntent('L1');
  await billing.getLeaguePass();
  await billing.bindLeaguePass('L2');
  await billing.repointLeaguePass('L3');
  await billing.setLeaguePassShowBuyer(true);
  eq(JSON.stringify(calls.map((c) => [c[0], c[1], c[2]])), JSON.stringify([
    ['POST', '/api/league-pass/intent', { league_id: 'L1' }],
    ['GET', '/api/league-pass', undefined],
    ['POST', '/api/league-pass/bind', { league_id: 'L2' }],
    ['POST', '/api/league-pass/repoint', { league_id: 'L3' }],
    ['PUT', '/api/league-pass/settings', { show_buyer: true }],
  ]), 'paths and bodies');
  for (const c of calls.filter((x) => x[0] !== 'GET')) assert(c[3] && c[3].quietStatuses.includes(409), `${c[1]}: 409 is an expected answer`);
});

// ═══ 4. api/purchases.ts — against a fake RevenueCat SDK ══════════════════
check('4a. the league offering, intro eligibility, the signed offer and the discounted buy: fail-safe, identity-gated, never a thrown read', async () => {
  const sdk = {
    calls: [],
    appUserId: null,
    offerings: { current: { identifier: 'default' }, all: { league: { identifier: 'league', availablePackages: [] } } },
    eligibility: {},
    promo: { identifier: 'league_t1_y1', keyIdentifier: 'K', nonce: 'n', signature: 's', timestamp: 1 },
    promoThrows: false,
    configure({ appUserID }) { this.appUserId = appUserID; },
    async logIn(id) { this.appUserId = id; return {}; },
    async getAppUserID() { return this.appUserId; },
    async getOfferings() { return this.offerings; },
    async checkTrialOrIntroductoryPriceEligibility(ids) { this.calls.push(['elig', ids.join()]); return this.eligibility; },
    async getPromotionalOffer(product, discount) {
      this.calls.push(['promo', product.identifier, discount.identifier]);
      if (this.promoThrows) throw new Error('sign failed');
      return this.promo;
    },
    async purchaseDiscountedPackage(pkg, offer) { this.calls.push(['buyDiscounted', pkg.identifier, offer.identifier, this.appUserId]); return { customerInfo: {} }; },
    async purchasePackage(pkg) { this.calls.push(['buy', pkg.identifier, this.appUserId]); return { customerInfo: {} }; },
  };
  // No key → every export inert.
  delete process.env.EXPO_PUBLIC_REVENUECAT_IOS_KEY;
  const off = load('api/purchases.ts', { 'react-native-purchases': { default: sdk } });
  eq(await off.getLeagueOffering('league'), null, 'no key: no offering');
  eq(await off.checkIntroPriceEligible({ identifier: 'x', introPrice: { price: 1 } }), false, 'no key: not eligible');
  eq(await off.getPromoOffer({ identifier: 'x', discounts: [] }, 'o', 'U1'), null, 'no key: no offer');
  eq(await off.purchaseDiscountedPackage({ identifier: 'p' }, sdk.promo, 'U1'), null, 'no key: no purchase');

  process.env.EXPO_PUBLIC_REVENUECAT_IOS_KEY = 'appl_test';
  const P = load('api/purchases.ts', { 'react-native-purchases': { default: sdk } });
  delete process.env.EXPO_PUBLIC_REVENUECAT_IOS_KEY;
  eq(await P.getLeagueOffering('league'), null, 'not configured yet: null');
  await P.initPurchases('U1');
  eq((await P.getLeagueOffering('league'))?.identifier, 'league', 'the league offering by id (never `current`)');
  eq(await P.getLeagueOffering('nope'), null, 'unknown offering → null');
  const t1 = { identifier: 'ftf_league_annual_t1', priceString: '$99.99', introPrice: { priceString: '$84.99', price: 84.99 },
    discounts: [{ identifier: 'league_t1_y1', priceString: '$84.99', price: 84.99 }] };
  sdk.eligibility = { ftf_league_annual_t1: { status: 2 } };
  eq(await P.checkIntroPriceEligible(t1), true, 'StoreKit ELIGIBLE (2) with an intro price');
  for (const status of [0, 1, 3]) {
    sdk.eligibility = { ftf_league_annual_t1: { status } };
    eq(await P.checkIntroPriceEligible(t1), false, `status ${status} → not eligible`);
  }
  sdk.eligibility = { ftf_league_annual_t1: { status: 2 } };
  eq(await P.checkIntroPriceEligible({ ...t1, introPrice: null }), false, 'no intro on the product → not eligible');
  const got = await P.getPromoOffer(t1, 'league_t1_y1', 'U1');
  eq(got && got.offer.identifier, 'league_t1_y1', 'the signed offer'); eq(got && got.priceString, '$84.99', 'priced from the discount itself');
  eq(await P.getPromoOffer(t1, 'league_t2_y1', 'U1'), null, 'a discount the product lacks → null');
  eq(await P.getPromoOffer(t1, undefined, 'U1'), null, 'no offer id → null');
  eq(await P.getPromoOffer(t1, 'league_t1_y1', 'SOMEONE_ELSE'), null, 'RevenueCat is not this user → null (the signature binds the user)');
  sdk.promoThrows = true;
  eq(await P.getPromoOffer(t1, 'league_t1_y1', 'U1'), null, 'signing failed → null, never a throw');
  sdk.promoThrows = false;
  const res = await P.purchaseDiscountedPackage({ identifier: '$rc_annual' }, sdk.promo, 'U1');
  assert(res && sdk.calls.some((c) => c[0] === 'buyDiscounted' && c[2] === 'league_t1_y1' && c[3] === 'U1'), 'the discounted purchase runs with the exact offer, as U1');
  let threw = false;
  try { await P.purchaseDiscountedPackage({ identifier: '$rc_annual' }, sdk.promo, ''); } catch (e) { threw = e && e.name === 'PurchaseIdentityError'; }
  assert(threw, 'no session user → PurchaseIdentityError, Apple\'s sheet never opens');
});

// ═══ 5. state/useEntitlements.ts + accountReset + useLeaguePass ═══════════
function entHarness(answer) {
  const storage = makeStorage();
  const session = makeCreate()(() => ({ user: { user_id: 'A' }, hasToken: true, verification: null }));
  const ent = load('state/useEntitlements.ts', {
    zustand: { create: makeCreate() },
    '@react-native-async-storage/async-storage': storage,
    '../api/billing': { getEntitlements: async () => (typeof answer === 'function' ? answer() : answer) },
    '../api/purchases': { currentIdentityUserId: () => null, hasProEntitlement: () => false, onCustomerInfoChange: () => () => {}, setOnPurchasesReady: () => {} },
    './subscriptionSession': { customerInfoApplies: () => false },
    './useSession': { useSession: session },
  });
  return { storage, session, ent };
}

check('5a. the store keeps the server\'s league_passes and sources, overwrites them in both directions, and reads [] when the server sends none (flag off)', async () => {
  let res = { pro: false, sources: [], league_passes: [pass('L1')], enforcing: true };
  const h = entHarness(() => res);
  eq(JSON.stringify(h.ent.useEntitlements.getState().leaguePasses), '[]', 'default []');
  await h.ent.useEntitlements.getState().refresh();
  eq(h.ent.useEntitlements.getState().leaguePasses.length, 1, 'stored');
  const blob = JSON.parse(h.storage.map.get('ftf.entitlements.v1'));
  eq(blob.userId, 'A', 'cached for its user'); eq(blob.leaguePasses.length, 1, 'cached under the grace clock');
  res = { pro: false, sources: ['apple_iap'], enforcing: true };   // flag off server-side: key absent
  await h.ent.useEntitlements.getState().refresh();
  eq(JSON.stringify(h.ent.useEntitlements.getState().leaguePasses), '[]', 'absent → [] (an ended pass goes)');
  eq(JSON.stringify(h.ent.useEntitlements.getState().sources), '["apple_iap"]', 'sources');
  // noteCustomerInfo (a device receipt) never writes passes
  h.ent.useEntitlements.getState().noteCustomerInfo(true);
  eq(JSON.stringify(h.ent.useEntitlements.getState().leaguePasses), '[]', 'a receipt grants no pass');
});

check('5b. D-280: account reset clears the passes (resetEntitlements via accountReset.resetAccountState) and so does a user change', async () => {
  const h = entHarness({ pro: true, sources: ['league_pass_iap'], league_passes: [pass('L1', 'buyer')], enforcing: true });
  await h.ent.useEntitlements.getState().refresh();
  eq(h.ent.useEntitlements.getState().leaguePasses.length, 1, 'held');
  const create = makeCreate();
  const reset = load('state/accountReset.ts', {
    '@react-native-async-storage/async-storage': h.storage,
    './queryClient': { queryClient: { cancelQueries: () => {}, clear: () => {} } },
    './presentationDismissed': { usePresentationDismissed: create(() => ({})) },
    './claimsPending': { useClaimsPending: create(() => ({})) },
    './useNotifications': { useNotifications: create(() => ({ clear: () => {} })) },
    './premiumImport': { usePremiumImport: create(() => ({})) },
    './useEntitlements': h.ent,
    './quicksetProgress': { clearQuicksetProgress: () => {} },
    './useTradeQueue': { useTradeQueue: create(() => ({})) },
    './teamReviewCompletion': { resetTeamReviewCompletion: () => {} },
    './rosterSetup': { resetRosterSetup: () => {} },
  });
  await reset.resetAccountState();
  const s = h.ent.useEntitlements.getState();
  eq(JSON.stringify(s.leaguePasses), '[]', 'passes cleared'); eq(JSON.stringify(s.sources), '[]', 'sources cleared');
  eq(s.answerFor, null, 'no answer held');
  assert(!h.storage.map.has('ftf.entitlements.v1'), 'the cached blob (with its passes) is gone');
  // user change (initEntitlements' subscriber)
  const h2 = entHarness({ pro: false, sources: [], league_passes: [pass('L1')], enforcing: true });
  h2.ent.initEntitlements();
  await settle();
  eq(h2.ent.useEntitlements.getState().leaguePasses.length, 1, 'A holds a pass');
  let answerB = null;
  h2.ent.useEntitlements.setState({});
  h2.session.setState({ user: { user_id: 'B' }, hasToken: false });
  eq(JSON.stringify(h2.ent.useEntitlements.getState().leaguePasses), '[]', 'B never sees A\'s passes');
  void answerB;
});

check('5c. state/useLeaguePass.proForLeagueNow: flag off → exactly pro; flag on → the league\'s live pass', () => {
  const flags = { 'monetize.league_pass': false };
  const entState = { pro: false, leaguePasses: [pass('L1')] };
  const m = load('state/useLeaguePass.ts', {
    './useFeatureFlags': { useFeatureFlags: { getState: () => ({ flags }) }, useFlag: (k) => !!flags[k] },
    './useEntitlements': { useEntitlements: Object.assign((sel) => sel(entState), { getState: () => entState }) },
    '../utils/leaguePass': lp,
  });
  eq(m.proForLeagueNow('L1'), false, 'flag off: pro (false)');
  flags['monetize.league_pass'] = true;
  eq(m.proForLeagueNow('L1'), true, 'flag on: covered in L1');
  eq(m.proForLeagueNow('L2'), false, 'not in L2');
  eq(m.useProForLeague('L1'), true, 'the hook agrees');
  entState.pro = true;
  eq(m.proForLeagueNow('L2'), true, 'pro everywhere');
});

// ═══ 6. sendPreCheck — the function's own text, executed ══════════════════
check('6a. sendPreCheck(resume, leagueId): a live pass for THAT league lets the send go on (flag on); another league, flag off, or no league → the paywall', () => {
  const src = read('components/SendInSleeperButton.tsx');
  const sf = ts.createSourceFile('x.tsx', src, ts.ScriptTarget.ES2019, true, ts.ScriptKind.TSX);
  let node = null;
  (function find(n) { if (ts.isFunctionDeclaration(n) && n.name && n.name.text === 'sendPreCheck') node = n; else ts.forEachChild(n, find); })(sf);
  assert(node, 'sendPreCheck');
  const js = ts.transpileModule(node.getText(sf).replace(/^export\s+/, ''), { compilerOptions: { target: ts.ScriptTarget.ES2019 } }).outputText;
  const run = (flagLp, passes, leagueId) => {
    const opened = [];
    const deps = {
      useFeatureFlags: { getState: () => ({ flags: { 'monetize.paywall': true, 'monetize.league_pass': flagLp } }) },
      useEntitlements: { getState: () => ({ loaded: true, enforcing: true, pro: false, leaguePasses: passes, refresh: async () => {} }) },
      isUnverifiedSession: () => false,
      openVerify: async () => 'dismissed',
      openPaywall: (p) => { opened.push(p.kind); },
      livePassFor: lp.livePassFor,
    };
    // eslint-disable-next-line no-new-func
    const pre = new Function(...Object.keys(deps), `${js}\nreturn sendPreCheck;`)(...Object.values(deps));
    return { stopped: pre(() => {}, leagueId), opened: opened.join() };
  };
  let r = run(true, [pass('L1')], 'L1');
  eq(r.stopped, false, 'covered league: the send goes on'); eq(r.opened, '', 'no paywall');
  r = run(true, [pass('L1')], 'L2');
  eq(r.stopped, true, 'another league: stopped'); eq(r.opened, 'send', 'the send paywall');
  r = run(false, [pass('L1')], 'L1');
  eq(r.stopped, true, 'flag off: the pass is ignored'); eq(r.opened, 'send', 'paywall');
  r = run(true, [pass('L1', 'member', PAST)], 'L1');
  eq(r.stopped, true, 'expired pass: stopped');
  r = run(true, [pass('L1')], undefined);
  eq(r.stopped, true, 'no league: stopped');
});

// ═══ 7. the gate sites [shape] ════════════════════════════════════════════
check('7a. [shape] the league-scoped pre-checks read proForLeague for the league they act on: Trades (active league), Win Now (session league), the Send router and both twins (the button\'s league)', () => {
  const trades = strip(read('screens/TradesScreen.tsx'));
  assert(/const payEntitled = useProForLeague\(leagueId\);/.test(trades), 'TradesScreen: payEntitled = useProForLeague(leagueId)');
  assert(/import \{ useProForLeague \} from '\.\.\/state\/useLeaguePass';/.test(trades), 'TradesScreen imports it');
  const win = strip(read('screens/WinNowScreen.tsx'));
  assert(/const payEntitled = useProForLeague\(leagueId\);/.test(win), 'WinNowScreen: payEntitled = useProForLeague(leagueId)');
  const router = strip(read('components/SendInSleeperButton.tsx'));
  assert(/export function sendPreCheck\(resume: \(\) => void, leagueId\?: string, afterAsk = false\): boolean/.test(router), 'sendPreCheck takes the league');
  assert(/if \(sendPreCheck\(\(\) => \{ void proceed\(\); \}, leagueId\)\) return;/.test(router), 'the router passes its league');
  assert(/sendPreCheck\(resume, leagueId, true\)/.test(router) && /if \(!sendPreCheck\(resume, leagueId\)\) resume\(\);/.test(router), 'the re-runs keep the league');
  for (const rel of ['components/SendInMflButton.tsx', 'components/SendInEspnButton.tsx']) {
    const s = strip(read(rel));
    assert(/sendPreCheck\?\.\(\(\) => \{ void proceed\(\); \}, leagueId\)/.test(s), `${rel}: passes its league`);
  }
  // ShopOffersBody's refetch-on-entitled effect (LLD §8) is not on this
  // branch (it lands with feat/paid-launch). When it arrives it must read
  // the league-aware value, never bare `pro`.
  const shop = strip(read('components/ShopOffersBody.tsx'));
  if (/useEntitlements/.test(shop)) {
    assert(!/useEntitlements\(\(s\) => s\.pro\)/.test(shop) && /useProForLeague\(/.test(shop), 'ShopOffersBody: its entitled read must be useProForLeague');
  }
});

check('7b. [shape] the only `pro` reads off useEntitlements are the account-level ones this feature left alone (an allowlist — a new league-scoped site must use useProForLeague)', () => {
  const ALLOWED = new Set([
    'components/SubscriptionSection.tsx',      // Settings › Subscription: the account's plan (account-level)
    'components/SendInSleeperButton.tsx',      // sendPreCheck: pro first, then the league's pass (6a)
    'components/LeaguePassRows.tsx',           // the unbound-pass row (a league product held), display only
    'components/LeaguePassCoveredNotice.tsx',  // R29: an individual subscriber, display only
    'state/useLeaguePass.ts',                  // the selector itself
    'state/useEntitlements.ts',                // the store
  ]);
  const hits = [];
  const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).forEach((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p);
    else if (/\.(ts|tsx)$/.test(e.name)) {
      const s = strip(fs.readFileSync(p, 'utf8'));
      if (/useEntitlements\(\s*\(?\s*(\w+)\s*\)?\s*=>\s*\1\.pro\s*\)|useEntitlements\.getState\(\)\.pro\b|const \{[^}]*\bpro\b[^}]*\} = useEntitlements\.getState\(\)/.test(s)) {
        hits.push(path.relative(SRC, p).split(path.sep).join('/'));
      }
    }
  });
  walk(SRC);
  for (const h of hits) assert(ALLOWED.has(h), `${h} reads account \`pro\` from useEntitlements: if it gates a league-scoped feature, use useProForLeague(leagueId)`);
  assert(hits.includes('components/SubscriptionSection.tsx') && hits.includes('components/SendInSleeperButton.tsx'), 'positive control: the scan sees the known reads');
  assert(!hits.includes('screens/TradesScreen.tsx') && !hits.includes('screens/WinNowScreen.tsx'), 'Trades and Win Now no longer read bare pro');
});

// ═══ 8. components/LeaguePassRows.tsx under a fake React ══════════════════
function mountRows(flags, ent, session) {
  const navs = [];
  const React = { createElement: (type, props, ...children) => ({ type, props: { ...(props || {}), children } }), Fragment: 'Fragment' };
  const tokens = new Proxy({}, { get: () => 1 });
  const m = load('components/LeaguePassRows.tsx', {
    react: { __esModule: true, default: React, ...React },
    'react-native': { Pressable: 'Pressable', StyleSheet: { create: (x) => x, hairlineWidth: 1 }, View: 'View' },
    '@react-navigation/native': { useNavigation: () => ({ navigate: (...a) => navs.push(a) }) },
    './chalkline/Text': { __esModule: true, default: 'ChalkText' },
    './chalkline': { Icon: 'Icon' },
    '../theme/chalkline': { chalk: tokens, ink: tokens, space: tokens },
    '../state/useEntitlements': { useEntitlements: (sel) => sel(ent) },
    '../state/useFeatureFlags': { useFlag: (k) => !!flags[k] },
    '../state/useSession': { useSession: (sel) => sel(session) },
    '../copy/monetization': copy,
    '../utils/leaguePass': lp,
  });
  return { m, navs };
}
const findId = (n, id) => {
  if (!n || typeof n !== 'object') return null;
  if (Array.isArray(n)) { for (const c of n) { const f = findId(c, id); if (f) return f; } return null; }
  if (n.props && n.props.testID === id) return n;
  return n.props ? findId(n.props.children, id) : null;
};
const textOf = (n) => {
  if (n == null || n === false) return '';
  if (typeof n === 'string' || typeof n === 'number') return String(n);
  if (Array.isArray(n)) return n.map(textOf).join('');
  return n.props ? textOf(n.props.children) : '';
};

check('8a. FLAG OFF: the paywall entry, the R26 line and the Settings rows render NOTHING, whatever the passes say', () => {
  const ent = { pro: true, sources: ['league_pass_iap'], leaguePasses: [pass('L1', 'buyer'), pass('L2')] };
  const session = { league: { league_id: 'L3' }, leagues: [{ league_id: 'L1', name: 'Alpha' }] };
  for (const flags of [{}, { 'monetize.paywall': true }, { 'monetize.league_pass': true }]) {
    const { m } = mountRows(flags, ent, session);
    eq(m.LeaguePassPaywallEntry({ source: 'settings' }), null, `entry, flags ${JSON.stringify(flags)}`);
    eq(m.LeaguePassOtherLeagueLine(), null, `R26 line, flags ${JSON.stringify(flags)}`);
    eq(m.LeaguePassSettingsRows(), null, `Settings rows, flags ${JSON.stringify(flags)}`);
  }
});

check('8b. FLAG ON: the entry opens LeaguePass with the paywall\'s source; R26 names the other league; Settings shows the member line ("a leaguemate" unless named), the buyer line + Manage, and the unbound row', () => {
  const flags = { 'monetize.paywall': true, 'monetize.league_pass': true };
  const leagues = [{ league_id: 'L1', name: 'Alpha' }, { league_id: 'L2', name: 'Bravo' }];
  let { m, navs } = mountRows(flags, { pro: false, sources: [], leaguePasses: [pass('L1')] }, { league: { league_id: 'L2' }, leagues });
  const entry = m.LeaguePassPaywallEntry({ source: 'gate' });
  eq(entry.props.testID, 'paywall-league-pass-entry', 'entry testID');
  entry.props.onPress();
  eq(JSON.stringify(navs[0]), JSON.stringify(['LeaguePass', { source: 'gate' }]), 'navigates to LeaguePass with the source');
  const line = m.LeaguePassOtherLeagueLine();
  eq(line.props.testID, 'paywall-league-pass-other-league', 'R26 testID');
  assert(textOf(line).includes('Alpha') && textOf(line).includes('only'), `R26 names the covered league: ${textOf(line)}`);
  const rows = m.LeaguePassSettingsRows();
  const member = findId(rows, 'settings-league-pass-member-L1');
  assert(member && /Alpha/.test(textOf(member)) && /November 24, 2027/.test(textOf(member)), `member line: ${textOf(member)}`);
  assert(/a leaguemate/.test(textOf(member)), 'R28: the buyer is "a leaguemate" when not named');
  ({ m } = mountRows(flags, { pro: false, sources: [], leaguePasses: [pass('L1', 'member', FUTURE, 'Dana')] }, { league: { league_id: 'L1' }, leagues }));
  assert(/Dana/.test(textOf(m.LeaguePassSettingsRows())), 'R28: named when the buyer opted in');
  eq(m.LeaguePassOtherLeagueLine(), null, 'covered here → no R26 line');
  ({ m, navs } = mountRows(flags, { pro: true, sources: ['league_pass_iap'], leaguePasses: [pass('L2', 'buyer')] }, { league: null, leagues }));
  const buyer = m.LeaguePassSettingsRows();
  assert(/Bravo/.test(textOf(findId(buyer, 'settings-league-pass-buyer'))), 'R27: the buyer\'s league');
  const manage = findId(buyer, 'settings-league-pass-manage');
  manage.props.onPress();
  eq(JSON.stringify(navs[0]), JSON.stringify(['LeaguePass', { source: 'settings', mode: 'manage' }]), 'Manage → LeaguePass manage');
  ({ m } = mountRows(flags, { pro: true, sources: ['league_pass_iap'], leaguePasses: [] }, { league: null, leagues }));
  assert(findId(m.LeaguePassSettingsRows(), 'settings-league-pass-unbound'), 'R19: the unbound row');
  ({ m } = mountRows(flags, { pro: true, sources: ['apple_iap'], leaguePasses: [] }, { league: null, leagues }));
  eq(m.LeaguePassSettingsRows(), null, 'an individual subscriber with no pass: nothing');
});

// ═══ 9. screens, navigation, testIDs, analytics [shape] ═══════════════════
check('9a. [shape] LeaguePass is registered ONCE in RootNav as a modal (no FeedbackFAB, #188); the screen self-guards on both flags, the session and the server config', () => {
  const nav = strip(read('navigation/RootNav.tsx'));
  eq((nav.match(/name="LeaguePass"/g) || []).length, 1, 'registered once');
  assert(/name="LeaguePass"\s*component=\{LeaguePassScreen\}\s*options=\{\{ presentation: 'modal', headerShown: false \}\}/.test(nav), 'a modal with its own header');
  const s = strip(read('screens/LeaguePassScreen.tsx'));
  assert(!/FeedbackFAB/.test(s), 'no FeedbackFAB on a modal');
  assert(/const on = lpOn && paywallOn;/.test(s) && /if \(!on\) dismiss\(\);/.test(s), 'flags off → dismiss');
  assert(/const verified = on && session === 'verified';/.test(s) && /if \(!verified\) return null;/.test(s), 'renders only for a verified session');
  assert(/if \(session === 'unverified' \|\| session === 'demo'\)/.test(s), 'unverified / demo → the VerifySheet');
  assert(/configQuery\.data\.enabled === false \|\| !configQuery\.data\.league_pass/.test(s), 'server config without the block → dismiss');
  assert(!/\['paywall-config'/.test(s), 'its own config key, never the paywall\'s shared entry (check-tipjar 8f)');
});

check('9b. [shape] the purchase runs the plan it showed: the discounted call only with its signed offer (never a silent list-price fallback); prices only from the plan', () => {
  const s = strip(read('screens/LeaguePassScreen.tsx'));
  assert(/if \(purchaseCallFor\(plan\.path\) === 'discounted'\) \{\s*if \(!promo\) throw new Error\('promo_offer_missing'\);\s*result = await purchaseDiscountedPackage\(pkg, promo, userId\);\s*\} else \{\s*result = await purchasePackage\(pkg, userId\);\s*\}/.test(s),
    'discounted only with the offer; otherwise purchasePackage');
  assert(/const plan = purchasePlan\(\{/.test(s), 'the plan comes from utils/leaguePass.purchasePlan');
  assert(/label=\{plan\.fullPriceNotice \? MON\['mon\.lp\.full_price\.continue'\] : MON\['mon\.lp\.buy'\]\}/.test(s), 'fallback: "Continue at full price"');
  assert(/testID="league-pass\.full-price-cancel"/.test(s), 'fallback: Cancel');
  assert(/introEligible = await checkIntroPriceEligible\(sp\);\s*if \(!introEligible\) \{[\s\S]{0,200}promo = await getPromoOffer\(sp, product\?\.promo_offer_id, userId\);/.test(s), 'intro first, then the config\'s promo_offer_id');
  assert(/await refreshEntitlements\(\);\s*const mine = buyerPass\(/.test(s), 'after the purchase: refresh until the buyer\'s pass shows');
  assert(/else if \(v\.unbound\) setStep\(\{ kind: 'idle' \}\);/.test(s), 'else the server\'s unbound view (choose a league, R19)');
});

check('9c. analytics: the new surfaces fire only the existing paywall_purchase_* events (no new event names); every new interactive element carries a testID', () => {
  const OK = new Set(['paywall_purchase_initiated', 'paywall_purchase_completed', 'paywall_purchase_failed']);
  for (const rel of NEW_FILES) {
    for (const m of strip(read(rel)).matchAll(/track\('([a-z_]+)'/g)) assert(OK.has(m[1]), `${rel}: a new event name ${m[1]}`);
  }
  const fired = new Set([...strip(read('screens/LeaguePassScreen.tsx')).matchAll(/track\('([a-z_]+)'/g)].map((m) => m[1]));
  for (const e of OK) assert(fired.has(e), `LeaguePassScreen fires ${e}`);
  const INTERACTIVE = /^(Pressable|Button|Row|Switch|TouchableOpacity)$/;
  for (const rel of ['screens/LeaguePassScreen.tsx', 'components/LeaguePassRows.tsx', 'components/LeaguePassCoveredNotice.tsx']) {
    const text = read(rel);
    const sf = ts.createSourceFile(rel, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    let n = 0;
    (function visit(node) {
      if ((ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) && INTERACTIVE.test(node.tagName.getText(sf))) {
        n += 1;
        const has = node.attributes.properties.some((p) => ts.isJsxAttribute(p) && p.name.getText(sf) === 'testID');
        assert(has, `${rel}: <${node.tagName.getText(sf)}> at line ${sf.getLineAndCharacterOfPosition(node.getStart()).line + 1} has no testID`);
      }
      ts.forEachChild(node, visit);
    })(sf);
    assert(n > 0, `${rel}: positive control (found interactive elements)`);
  }
  const want = ['league-pass-screen', 'league-pass.close', 'league-pass.buy', 'league-pass.full-price-cancel', 'league-pass.change-league',
    'league-pass.move', 'league-pass.show-name', 'league-pass.terms', 'league-pass.privacy', 'league-pass.done-close'];
  const s = read('screens/LeaguePassScreen.tsx');
  for (const id of want) assert(s.includes(`testID="${id}"`), `LeaguePassScreen: ${id}`);
  assert(/testID=\{`league-pass\.league\.\$\{l\.league_id\}`\}/.test(s), 'league rows: league-pass.league.<id>');
});

check('9d. [shape] PaywallScreen: the R30 entry sits in the anchored block after the links (not a plan row); the R26 line after the body; Settings mounts the rows in both branches', () => {
  const p = strip(read('screens/PaywallScreen.tsx'));
  assert(/\{MON\['mon\.pay\.privacy'\]\}[\s\S]{0,120}<\/Pressable>\s*<\/View>\s*(\{\s*\}\s*)?<LeaguePassPaywallEntry source=\{source\} \/>\s*<\/View>/.test(p), 'the entry closes the anchored block, below the plans and links');
  const plans = p.slice(p.indexOf('accessibilityRole="radiogroup"'), p.indexOf('{selected ? ('));
  assert(!/LeaguePass/.test(plans), 'never inside the plan rows');
  assert(/testID="paywall-invitee-board">[\s\S]{0,120}\) : null\}\s*(\{\s*\}\s*)?<LeaguePassOtherLeagueLine \/>/.test(p), 'R26 line under the body');
  const subs = strip(read('components/SubscriptionSection.tsx'));
  eq((subs.match(/<LeaguePassSettingsRows \/>/g) || []).length, 2, 'Settings › Subscription: member and non-member branches');
});

check('9e. R29 [shape]: TradesScreen mounts the covered notice for the active league; the notice keys by user AND league and writes the key when it shows', () => {
  const t = strip(read('screens/TradesScreen.tsx'));
  assert(/<LeaguePassCoveredNotice userId=\{userId\} leagueId=\{leagueId\} \/>/.test(t), 'mounted with the user and league');
  const n = strip(read('components/LeaguePassCoveredNotice.tsx'));
  assert(/const key = coveredNoticeKey\(userId, leagueId\);/.test(n), 'keyed per user and league');
  assert(/if \(!already\) AsyncStorage\.setItem\(key, '1'\)/.test(n), 'told once: the key is written when it shows');
  assert(/coveredNoticeDue\(pro, sources, passes, leagueId, flagOn, Date\.now\(\)\)/.test(n), 'due through the pure rule (flag included)');
});

check('9f. R38 [shape]: account deletion tells EVERY subscriber, a pass buyer included, that the App Store subscription is cancelled separately (legal\'s sub-note, no condition; check-paywall-gate 9f pins the dialog)', () => {
  const del = load('copy/deleteAccount.ts', {});
  assert(/doesn't cancel an active subscription/.test(del.DELETE_ACCOUNT_SUB_NOTE), 'the sub-note');
  for (const rel of ['screens/settings/sections/AccountDataSection.tsx', 'screens/SettingsScreen.tsx']) {
    assert(/DELETE_ACCOUNT_BODY \+ '\\n\\n' \+ DELETE_ACCOUNT_SUB_NOTE/.test(strip(read(rel))), `${rel}: the sub-note is in the message for everyone`);
  }
});

(async () => {
  console.log('check-league-pass');
  for (const t of tests) {
    try {
      await t.fn();
      passes += 1;
      console.log(`  ✓ ${t.name}`);
    } catch (e) {
      failures += 1;
      console.log(`  ✗ ${t.name}\n      ${String(e && e.message).split('\n').join('\n      ')}`);
    }
  }
  console.log(`\ncheck-league-pass: ${passes} passed, ${failures} failed`);
  process.exit(failures ? 1 : 0);
})();
