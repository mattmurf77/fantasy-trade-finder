#!/usr/bin/env node
// Tip-jar structural guard (operator request 2026-08-28; flag
// `monetize.paywall`, dark; docs/plans/monetization/iap-enablement/).
//
// A tip is money with NO entitlement, and every expensive failure here is a
// version of forgetting that:
//   1. TipJarScreen exists and is registered EXACTLY ONCE, as a root-stack
//      MODAL (same #188 reasoning as the paywall).
//   2. Route registered UNCONDITIONALLY; the screen self-guards on
//      `monetize.paywall` AND on the server's `enabled === false`.
//   3. The screen never touches the entitlement store — no useEntitlements,
//      no refresh, no noteCustomerInfo. A tip that "unlocks" anything is the
//      bug the backend guard exists to prevent; the client must not fake it.
//   4. The purchase path is wired: purchaseTip() called, and its no-product /
//      cancel / failure branches all track paywall_purchase_failed.
//   5. The copy states a tip unlocks nothing ("unlocks nothing"), so App
//      Review and the user read the same promise the code keeps.
//   6. No FeedbackFAB in the modal (#188 exception).
//   7. purchases.ts stays the ONLY react-native-purchases importer, and the
//      tip helpers keep the configured-guard before any SDK call.
//   8. The Settings entry row (settings-tip-row) exists on BOTH settings
//      surfaces, inside the same `monetize.paywall` gate as the pro row AND
//      inside a `tipsOffered` gate (head-eng's B8: the row shows only while
//      the cached /api/paywall/config `tips[]` is non-empty). The hook is
//      called at the component's top level; `tipsOffered` is EXECUTED here
//      (state/useTipsOffered.ts transpiled with stubs), and useTipsOffered
//      must subscribe with `enabled: false` (never fetching).
//      8d-8g (tip jar C1): the warm observer state/useWarmPaywallConfig.ts
//      is EXECUTED (same key + queryFn, 5-min staleTime, focus refetch;
//      enabled only for monetize.paywall AND a verified session), all four
//      ['paywall-config'] subscribers share one key + queryFn, and it is
//      mounted once under RootNav's Main and referenced by no other file.
//   9. The backend tip guard exists: entitlements.is_tip_product referenced
//      by the projector, and every served tip SKU is ftf_tip_-prefixed on
//      the server (cross-checked into backend/server.py so a drifted id
//      cannot silently start granting Pro).
//
// Run: node tests/check-tipjar.js   (or npm run test:tipjar)

'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const REPO = path.resolve(ROOT, '..');
const SCREEN = path.join(ROOT, 'src/screens/TipJarScreen.tsx');
const PURCHASES = path.join(ROOT, 'src/api/purchases.ts');
const ROOTNAV = path.join(ROOT, 'src/navigation/RootNav.tsx');
const TABNAV = path.join(ROOT, 'src/navigation/TabNav.tsx');
const HUB = path.join(ROOT, 'src/screens/settings/SettingsHubScreen.tsx');
const FLAT = path.join(ROOT, 'src/screens/SettingsScreen.tsx');
const TIPS_HOOK = path.join(ROOT, 'src/state/useTipsOffered.ts');
const WARM_HOOK = path.join(ROOT, 'src/state/useWarmPaywallConfig.ts');
const SUB_SESSION = path.join(ROOT, 'src/state/subscriptionSession.ts');
const BE_ENTL = path.join(REPO, 'backend/entitlements.py');
const BE_SERVER = path.join(REPO, 'backend/server.py');

const pass = [], fail = [];
const ok = (n) => pass.push(n);
const bad = (n, d) => fail.push(`${n}\n      ${d}`);
const read = (p) => (fs.existsSync(p)
  ? fs.readFileSync(p, 'utf8')
  : (bad('file exists', `missing ${path.relative(ROOT, p)}`), ''));
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

const s = strip(read(SCREEN));
const purchases = strip(read(PURCHASES));
const rootnav = strip(read(ROOTNAV));
const tabnav = strip(read(TABNAV));
const hub = strip(read(HUB));
const flat = strip(read(FLAT));
const beEntl = read(BE_ENTL);
const beServer = read(BE_SERVER);

// 1 — exists, registered exactly once, as a modal, root stack only
{
  const hits = (rootnav.match(/name="TipJar"/g) || []).length;
  const block = rootnav.split('name="TipJar"')[1] || '';
  const modal = /presentation:\s*'modal'/.test(block.slice(0, 400));
  if (hits === 1 && modal && !tabnav.includes('TipJar')) {
    ok('1. TipJarScreen registered once, root-stack MODAL only');
  } else {
    bad('1. TipJarScreen registered once, root-stack MODAL only',
      `hits=${hits} modal=${modal} inTabs=${tabnav.includes('TipJar')}`);
  }
}

// 2 — unconditional registration + double self-guard
{
  const regGated = /\{\s*\w+\s*\?\s*<Stack\.Screen[^>]*name="TipJar"/.test(rootnav);
  const flagGuard = s.includes("useFlag('monetize.paywall')")
    && /if\s*\(!paywallOn\)\s*dismiss\(\)/.test(s);
  const serverGuard = /config\.enabled\s*===\s*false\)\s*dismiss\(\)/.test(s);
  if (!regGated && flagGuard && serverGuard) {
    ok('2. route unconditional; screen self-guards on flag AND server enabled:false');
  } else {
    bad('2. route unconditional; screen self-guards on flag AND server enabled:false',
      `regGated=${regGated} flagGuard=${flagGuard} serverGuard=${serverGuard}`);
  }
}

// 3 — no entitlement handling anywhere in the screen
{
  const dirty = /useEntitlements|noteCustomerInfo|refreshEntitlements|hasProEntitlement/.test(s);
  if (!dirty) ok('3. screen never touches the entitlement store (tip unlocks nothing)');
  else bad('3. screen never touches the entitlement store (tip unlocks nothing)',
    'found entitlement-store usage in TipJarScreen');
}

// 4 — purchase path wired, failures tracked
{
  const wired = s.includes('purchaseTip(')
    && s.includes('getTipProducts(')
    && s.includes("track('paywall_purchase_initiated'")
    && s.includes("track('paywall_purchase_completed'")
    && (s.match(/track\('paywall_purchase_failed'/g) || []).length >= 3
    && s.includes('isUserCancelled(');
  if (wired) ok('4. purchaseTip wired; initiated/completed tracked; all 3 failure branches tracked');
  else bad('4. purchaseTip wired; initiated/completed tracked; all 3 failure branches tracked',
    'a purchase or tracking call is missing from TipJarScreen');
}

// 5 — the no-unlock promise is user-visible copy
{
  if (/unlocks\s*\n?\s*nothing/i.test(s)) ok('5. copy states a tip unlocks nothing');
  else bad('5. copy states a tip unlocks nothing', 'promise copy missing');
}

// 6 — no FeedbackFAB (modal exception, #188)
{
  if (!s.includes('FeedbackFAB')) ok('6. no FeedbackFAB in the tip modal (#188)');
  else bad('6. no FeedbackFAB in the tip modal (#188)', 'FeedbackFAB found');
}

// 7 — single SDK importer; tip helpers keep the configured guard
{
  const importers = [];
  const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).forEach((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p);
    else if (/\.(ts|tsx)$/.test(e.name)) {
      // Runtime access is either the lazy require (the sanctioned seam) or a
      // value import; `import type` is erased and does not count.
      const src = fs.readFileSync(p, 'utf8').replace(/import type[^;]+;/g, '');
      if (/require\('react-native-purchases'\)/.test(src)
        || /from 'react-native-purchases'/.test(src)) {
        importers.push(path.relative(ROOT, p));
      }
    }
  });
  walk(path.join(ROOT, 'src'));
  const guards = (purchases.match(/if \(!P \|\| !_configured\)/g) || []).length >= 4;
  if (importers.length === 1 && importers[0] === 'src/api/purchases.ts' && guards) {
    ok('7. purchases.ts sole SDK importer; tip helpers guard on configured');
  } else {
    bad('7. purchases.ts sole SDK importer; tip helpers guard on configured',
      `importers=${JSON.stringify(importers)} guards=${guards}`);
  }
}

// 8 — settings entry on both surfaces, inside the paywall gate AND the
//     tipsOffered gate; the hook imported and called at the top level
{
  // The row sits after `<flag> ? (`, after a `{tipsOffered ? (` that opens
  // inside the flag block, and before that tips block's `) : null}`, which
  // in turn closes before the flag block's fragment `</>`.
  const gated = (text, flag) => {
    const flagAt = text.indexOf(`${flag} ? (`);
    const tipAt = text.indexOf('{tipsOffered ? (', flagAt);
    const rowAt = text.indexOf('settings-tip-row');
    const tipEnd = tipAt > -1 ? text.indexOf(') : null}', tipAt) : -1;
    const fragEnd = tipEnd > -1 ? text.indexOf('</>', tipEnd) : -1;
    return flagAt > -1 && tipAt > flagAt && rowAt > tipAt && tipEnd > rowAt
      && fragEnd > tipEnd
      && (text.match(/settings-tip-row/g) || []).length === 1
      && /import \{ useTipsOffered \} from '(\.\.\/)+state\/useTipsOffered';/.test(text)
      && /^ {2}const tipsOffered\s*= useTipsOffered\(\);$/m.test(text);
  };
  const inHub = gated(hub, 'paywallOn');
  const inFlat = gated(flat, 'paywallEnabled');
  const navs = (hub + flat).match(/navigate\?\.\('TipJar', \{ source: 'settings' \}\)/g) || [];
  if (inHub && inFlat && navs.length === 2) {
    ok('8. settings-tip-row on both surfaces, inside the flag gate AND the tipsOffered gate, navigates to TipJar');
  } else {
    bad('8. settings-tip-row on both surfaces, inside the flag gate AND the tipsOffered gate, navigates to TipJar',
      `hub=${inHub} flat=${inFlat} navs=${navs.length}`);
  }
}

// 8b/8c — tipsOffered EXECUTED; useTipsOffered subscribes with enabled:false
{
  let ts = null;
  try { ts = require('typescript'); } catch { /* reported below */ }
  const src = read(TIPS_HOOK);
  if (!ts || !src) {
    bad('8b. tipsOffered executed', ts ? 'missing state/useTipsOffered.ts'
      : 'typescript not resolvable — run `npm install` in mobile/ first');
  } else {
    const js = ts.transpileModule(src, { compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019,
    } }).outputText;
    let seen = null;      // the options useTipsOffered hands to useQuery
    let cached;           // what the stubbed cache "holds"
    const stubs = {
      '@tanstack/react-query': {
        useQuery: (opts) => { seen = opts; return { data: cached }; },
      },
      '../api/billing': {
        getPaywallConfig: () => { throw new Error('useTipsOffered fetched'); },
      },
    };
    const mod = { exports: {} };
    new Function('module', 'exports', 'require', js)(mod, mod.exports, (name) => {
      if (name in stubs) return stubs[name];
      throw new Error(`state/useTipsOffered.ts gained a runtime import ("${name}")`);
    });
    const { tipsOffered, useTipsOffered } = mod.exports;
    const tip = { product_id: 'ftf_tip_199', display_price: '$1.99' };
    const cases = [
      [undefined, false], [null, false], [{}, false], [{ tips: [] }, false],
      [{ tips: [tip] }, true],
    ];
    const wrong = cases.filter(([cfg, want]) => tipsOffered(cfg) !== want)
      .map(([cfg, want]) => `${JSON.stringify(cfg)} → ${!want}`);
    if (wrong.length === 0) {
      ok('8b. tipsOffered: undefined/null/{}/{tips:[]} → false; {tips:[tip]} → true');
    } else {
      bad('8b. tipsOffered: undefined/null/{}/{tips:[]} → false; {tips:[tip]} → true',
        `wrong: ${wrong.join('; ')}`);
    }
    cached = { enabled: true, tips: [tip] };
    const shown = useTipsOffered();
    const shape = seen && seen.enabled === false
      && JSON.stringify(seen.queryKey) === JSON.stringify(['paywall-config', 'ios']);
    if (shape && shown === true) {
      ok("8c. useTipsOffered subscribes to ['paywall-config','ios'] with enabled: false (never fetches)");
    } else {
      bad("8c. useTipsOffered subscribes to ['paywall-config','ios'] with enabled: false (never fetches)",
        `options=${JSON.stringify(seen && { queryKey: seen.queryKey, enabled: seen.enabled })} shown=${shown}`);
    }
  }
}

// 8d/8e — the warm observer (tip jar C1, docs/plans/tip-jar/plan.md §3):
//     EXECUTED (state/useWarmPaywallConfig.ts transpiled with stubs, the real
//     subscriptionSession.ts behind it). Same key + queryFn as the hook, the
//     screens' staleTime, focus refetch on, and enabled = flag AND verified.
{
  let ts = null;
  try { ts = require('typescript'); } catch { /* reported below */ }
  const src = read(WARM_HOOK);
  const sessSrc = read(SUB_SESSION);
  if (!ts || !src || !sessSrc) {
    bad('8d. warm observer executed', ts ? 'missing state/useWarmPaywallConfig.ts or subscriptionSession.ts'
      : 'typescript not resolvable — run `npm install` in mobile/ first');
  } else {
    const load = (code, stubs, label) => {
      const js = ts.transpileModule(code, { compilerOptions: {
        module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019,
      } }).outputText;
      const mod = { exports: {} };
      new Function('module', 'exports', 'require', js)(mod, mod.exports, (name) => {
        if (name in stubs) return stubs[name];
        throw new Error(`${label} gained a runtime import ("${name}")`);
      });
      return mod.exports;
    };
    const subscriptionSession = load(sessSrc, {}, 'state/subscriptionSession.ts');
    let seen = null; let flag = false; let session = null;
    const flagKeys = []; const fetched = [];
    const warm = load(src, {
      '@tanstack/react-query': { useQuery: (opts) => { seen = opts; return {}; } },
      '../api/billing': { getPaywallConfig: (p) => { fetched.push(p); return Promise.resolve({}); } },
      './useFeatureFlags': { useFlag: (k) => { flagKeys.push(k); return flag; } },
      './useSession': { useSession: (sel) => sel(session) },
      './subscriptionSession': subscriptionSession,
    }, 'state/useWarmPaywallConfig.ts');

    const sleeper = { user_id: '123456', account_only: false };
    const acct = { user_id: 'acct_abc', account_only: true };
    flag = true; session = { isDemo: false, verification: { session_verified: true }, user: sleeper };
    const rendered = warm.WarmPaywallConfig();
    if (seen) seen.queryFn();
    const shape = rendered === null && seen
      && JSON.stringify(seen.queryKey) === JSON.stringify(['paywall-config', 'ios'])
      && JSON.stringify(fetched) === JSON.stringify(['ios'])
      && seen.staleTime === 5 * 60_000 && seen.refetchOnWindowFocus === true
      && flagKeys.length > 0 && flagKeys.every((k) => k === 'monetize.paywall');
    if (shape) {
      ok("8d. warm observer: ['paywall-config','ios'] + getPaywallConfig('ios'), staleTime 5 min, focus refetch, reads monetize.paywall, renders null");
    } else {
      bad("8d. warm observer: ['paywall-config','ios'] + getPaywallConfig('ios'), staleTime 5 min, focus refetch, reads monetize.paywall, renders null",
        `options=${JSON.stringify(seen && { queryKey: seen.queryKey, staleTime: seen.staleTime, refetchOnWindowFocus: seen.refetchOnWindowFocus })} fetched=${JSON.stringify(fetched)} flags=${JSON.stringify(flagKeys)} rendered=${rendered}`);
    }

    const cases = [
      ['flag off, verified', false, { isDemo: false, verification: { session_verified: true }, user: sleeper }, false],
      ['unverified', true, { isDemo: false, verification: { session_verified: false }, user: sleeper }, false],
      ['unknown', true, { isDemo: false, verification: null, user: sleeper }, false],
      ['demo (server says verified)', true, { isDemo: true, verification: { session_verified: true }, user: acct }, false],
      ['verified (server)', true, { isDemo: false, verification: { session_verified: true }, user: sleeper }, true],
      ['verified (acct_ account-only)', true, { isDemo: false, verification: null, user: acct }, true],
    ];
    const wrong = cases.filter(([, f, s, want]) => {
      flag = f; session = s; seen = null;
      warm.useWarmPaywallConfig();
      return !seen || seen.enabled !== want;
    }).map(([name, , , want]) => `${name} → ${!want}`);
    if (wrong.length === 0) {
      ok('8e. warm observer gate: flag off / unverified / unknown / demo → disabled; flag + verified → enabled');
    } else {
      bad('8e. warm observer gate: flag off / unverified / unknown / demo → disabled; flag + verified → enabled',
        `wrong: ${wrong.join('; ')}`);
    }
  }
}

// 8f — one cache entry: every ['paywall-config' subscriber in src/ is one of
//     the four, each with the identical key + queryFn
{
  const SHARED = /queryKey: \['paywall-config', 'ios'\],\s*queryFn: \(\) => getPaywallConfig\('ios'\),/;
  const want = ['src/screens/PaywallScreen.tsx', 'src/screens/TipJarScreen.tsx',
    'src/state/useTipsOffered.ts', 'src/state/useWarmPaywallConfig.ts'];
  const users = [];
  const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).forEach((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p);
    else if (/\.(ts|tsx)$/.test(e.name) && strip(fs.readFileSync(p, 'utf8')).includes("['paywall-config'")) {
      users.push(path.relative(ROOT, p));
    }
  });
  walk(path.join(ROOT, 'src'));
  const shared = want.filter((f) => SHARED.test(strip(read(path.join(ROOT, f)))));
  if (JSON.stringify(users.sort()) === JSON.stringify([...want].sort()) && shared.length === want.length) {
    ok("8f. the four ['paywall-config','ios'] subscribers share one key + queryFn (PaywallScreen, TipJarScreen, useTipsOffered, useWarmPaywallConfig)");
  } else {
    bad("8f. the four ['paywall-config','ios'] subscribers share one key + queryFn",
      `users=${JSON.stringify(users)} shared=${JSON.stringify(shared)}`);
  }
}

// 8g — mounted ONCE, under RootNav's always-mounted `Main` screen (which stays
//     mounted beneath every Settings push), and referenced nowhere else: in
//     particular not in any Settings file, so the hub stays zero-network
{
  const mainAt = rootnav.indexOf('<Stack.Screen name="Main">');
  const mainEnd = mainAt > -1 ? rootnav.indexOf('</Stack.Screen>', mainAt) : -1;
  const mountAt = rootnav.indexOf('<WarmPaywallConfig />');
  const mounted = mainAt > -1 && mountAt > mainAt && mountAt < mainEnd
    && (rootnav.match(/<WarmPaywallConfig \/>/g) || []).length === 1
    && /import \{ WarmPaywallConfig \} from '\.\.\/state\/useWarmPaywallConfig';/.test(rootnav);
  const refs = [];
  const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).forEach((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p);
    else if (/\.(ts|tsx)$/.test(e.name) && /WarmPaywallConfig/.test(strip(fs.readFileSync(p, 'utf8')))) {
      refs.push(path.relative(ROOT, p));
    }
  });
  walk(path.join(ROOT, 'src'));
  const only = JSON.stringify(refs.sort())
    === JSON.stringify(['src/navigation/RootNav.tsx', 'src/state/useWarmPaywallConfig.ts']);
  if (mounted && only) {
    ok('8g. WarmPaywallConfig mounted once under RootNav Main; referenced by no other file (no Settings file)');
  } else {
    bad('8g. WarmPaywallConfig mounted once under RootNav Main; referenced by no other file (no Settings file)',
      `mounted=${mounted} refs=${JSON.stringify(refs)}`);
  }
}

// 9 — backend guard exists and every served tip SKU hits it
{
  const guard = beEntl.includes('def is_tip_product')
    && /if is_tip_product\(product_id\):/.test(beEntl);
  const served = [...beServer.matchAll(/"product_id":\s*"(ftf_tip_[^"]+)"/g)].map((m) => m[1]);
  const allPrefixed = served.length >= 1 && served.every((id) => id.startsWith('ftf_tip_'));
  if (guard && allPrefixed) {
    ok(`9. backend is_tip_product guard present; ${served.length} served tip SKUs all ftf_tip_*`);
  } else {
    bad('9. backend is_tip_product guard present; served tip SKUs all ftf_tip_*',
      `guard=${guard} served=${JSON.stringify(served)}`);
  }
}

console.log(pass.map((p) => `PASS  ${p}`).join('\n'));
if (fail.length) {
  console.log(fail.map((f) => `FAIL  ${f}`).join('\n'));
  console.log(`\ncheck-tipjar: ${pass.length} passed, ${fail.length} failed`);
  process.exit(1);
}
console.log(`\ncheck-tipjar: ${pass.length} passed, 0 failed`);
