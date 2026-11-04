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
//      5b-5d (marketing addendum 15): each final string verbatim, the old
//      strings gone, and the payment-pending branch ahead of the generic
//      failure (a pending payment is neither an error nor a thank-you).
//   6. No FeedbackFAB in the modal (#188 exception).
//   7. purchases.ts stays the ONLY react-native-purchases importer, and the
//      tip helpers keep the configured-guard before any SDK call.
//   8. The Settings entry row (settings-tip-row) is DATA-DRIVEN on BOTH
//      settings surfaces (B8 #1): behind the `monetize.paywall` gate AND the
//      server offering tips (the cached config's `tips` non-empty, read by a
//      cache subscription that never fetches). The server serves `tips: []`
//      at launch, so it is hidden then.
//      8d-8g (tip jar C1): the warm observer state/useWarmPaywallConfig.ts
//      is EXECUTED (same key + queryFn, 5-min staleTime, focus refetch;
//      enabled only for monetize.paywall AND a verified session), all four
//      ['paywall-config'] subscribers share one key + queryFn, and it is
//      mounted once under RootNav's Main and referenced by no other file.
//      8h: a drop out of verified (unverified, demo, user change, sign-out)
//      removes the cached ['paywall-config'] entry once, EXECUTED.
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

// 5b/5c/5d — marketing addendum 15: final strings verbatim, old strings gone,
//     the pending branch ahead of the generic failure. Comments are stripped
//     and whitespace collapsed (JSX text wraps). The lede's "One person
//     builds Fleeced." is in: the operator confirmed it on 2026-11-02.
{
  const flat = s.replace(/\s+/g, ' ');
  const want = [
    ['lede', 'One person builds Fleeced. If the app has earned a spot in your league routine, a tip helps keep it going. A tip unlocks nothing. It’s just a thank-you.', 1],
    ['thank-you body', 'Your tip helps keep Fleeced going.', 1],
    ['C2 (no product, no result)', "setError('Couldn’t load tips right now. Try again later.')", 2],
    ['purchase failure', "setError('The App Store didn’t finish the tip. Check your connection and try again.')", 1],
    ['payment pending', 'Waiting for approval. The tip goes through once it’s approved.', 1],
  ];
  const wrongCopy = want.filter(([, text, n]) => flat.split(text).length - 1 !== n)
    .map(([name, , n]) => `${name} (want ${n})`);
  if (wrongCopy.length === 0) ok('5b. addendum 15 strings verbatim: lede, thank-you body, C2 at both sites, failure, pending');
  else bad('5b. addendum 15 strings verbatim: lede, thank-you body, C2 at both sites, failure, pending',
    `missing or miscounted: ${wrongCopy.join('; ')}`);

  const gone = [/on this build yet/i, /You haven[’']t been charged/i, /Tips keep Fleeced independent/i, /built by one person/i, /donat/i];
  const left = gone.filter((re) => re.test(flat)).map(String);
  if (left.length === 0) ok('5c. old tip-jar strings gone (on this build yet, haven’t been charged, independent, built by one person) and no "donation" (legal R28.26)');
  else bad('5c. old tip-jar strings gone', `still present: ${left.join(', ')}`);

  const catchAt = s.indexOf('} catch (err) {');
  const pendAt = s.indexOf('if (isPaymentPending(err)) {', catchAt);
  const elseAt = s.indexOf('} else if (!cancelled) {', pendAt);
  const failAt = s.indexOf("setError('The App Store didn’t finish the tip.", elseAt);
  const branch = pendAt > -1 && elseAt > pendAt ? s.slice(pendAt, elseAt) : '';
  const ordered = catchAt > -1 && pendAt > catchAt && elseAt > pendAt && failAt > elseAt
    && /setPending\(true\)/.test(branch) && !/setError|setThanked/.test(branch)
    && /import \{[^}]*\bisPaymentPending\b[^}]*\} from '\.\.\/api\/purchases';/.test(s);
  if (ordered) ok('5d. catch: isPaymentPending → pending note (no error, no thank-you) BEFORE the generic failure');
  else bad('5d. catch: isPaymentPending → pending note (no error, no thank-you) BEFORE the generic failure',
    `catch=${catchAt} pending=${pendAt} else=${elseAt} failure=${failAt}`);
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

// 8 — the settings entry, DATA-DRIVEN on both surfaces (B8 #1): the paywall
//     flag AND the server offering tips. The hook subscribes to the cached
//     config and never fetches; `tipsOffered` (pure) is executed in 8b/8c
//     below and in check-paywall-gate §9i.
{
  const subs = strip(read(path.join(ROOT, 'src/state/useTipsOffered.ts')));
  const hook = /export function useTipsOffered\(\): boolean \{\s*const \{ data \} = useQuery<PaywallConfig>\(\{\s*queryKey: \['paywall-config', 'ios'\],\s*queryFn: \(\) => getPaywallConfig\('ios'\),\s*enabled: false,\s*\}\);\s*return tipsOffered\(data\);/.test(subs)
    && /return Array\.isArray\(config\?\.tips\) && config\.tips\.length > 0;/.test(subs);
  // Round-3 P3: the row also needs an EXACTLY-verified session (the shared
  // predicate), so demo, unverified and unknown never see it (8d executes it).
  const gated = (text, flag) => text.includes('settings-tip-row')
    && /import \{ useTipsOffered \} from '(\.\.\/)+state\/useTipsOffered';/.test(text)
    && /import \{ subscriptionSessionState \} from '(\.\.\/)+state\/subscriptionSession';/.test(text)
    && /const tipsOffered\s*= useTipsOffered\(\);/.test(text)
    && /const sessionVerified\s*= useSession\(\(s\) => subscriptionSessionState\(s\) === 'verified'\);/.test(text)
    && text.indexOf(`${flag} && tipsOffered && sessionVerified ? (`) > -1
    && text.indexOf('settings-tip-row') > text.indexOf(`${flag} && tipsOffered && sessionVerified ? (`);
  const inHub = gated(hub, 'paywallOn');
  const inFlat = gated(flat, 'paywallEnabled');
  const navs = (hub + flat).match(/navigate\?\.\('TipJar', \{ source: 'settings' \}\)/g) || [];
  if (hook && inHub && inFlat && navs.length === 2) {
    ok('8. settings-tip-row on both surfaces only with the flag AND the server offering tips (never-fetching cache read) AND an exactly-verified session');
  } else {
    bad('8. settings-tip-row on both surfaces only with the flag AND the server offering tips (never-fetching cache read) AND an exactly-verified session',
      `hook=${hook} hub=${inHub} flat=${inFlat} navs=${navs.length}`);
  }
}

// The shared predicate module, transpiled and loaded for real (it has no
// runtime imports). Used by 8d and 10.
let tsc = null;
try { tsc = require('typescript'); } catch { /* reported by 8b */ }
function loadTs(rel, stubs, tsx = false) {
  const js = tsc.transpileModule(fs.readFileSync(path.join(ROOT, rel), 'utf8'), {
    compilerOptions: { module: tsc.ModuleKind.CommonJS, target: tsc.ScriptTarget.ES2019, ...(tsx ? { jsx: tsc.JsxEmit.React } : {}) },
    fileName: path.basename(rel),
  }).outputText;
  const mod = { exports: {} };
  new Function('module', 'exports', 'require', js)(mod, mod.exports, (name) => {
    if (Object.prototype.hasOwnProperty.call(stubs, name)) return stubs[name];
    throw new Error(`${rel} gained an unexpected runtime import ("${name}")`);
  });
  return mod.exports;
}
const subSession = tsc ? loadTs('src/state/subscriptionSession.ts', {}) : null;
const SESSIONS = [
  ['verified', { isDemo: false, verification: { session_verified: true }, user: { user_id: '111' } }, true],
  ['demo (even with a verified answer)', { isDemo: true, verification: { session_verified: true }, user: { user_id: 'demo_user_ab12' } }, false],
  ['unverified', { isDemo: false, verification: { session_verified: false }, user: { user_id: '111' } }, false],
  ['unknown', { isDemo: false, verification: null, user: { user_id: '111' } }, false],
];

// 8a — EXECUTED: each surface's own `sessionVerified` selector, run on the
//      real predicate: only an exactly-verified session shows the row.
{
  const name = '8a. the tip row\'s session selector (both surfaces, executed): demo, unverified and unknown hide it; verified shows it';
  if (!subSession) {
    bad(name, 'typescript not resolvable');
  } else {
    const wrong = [];
    for (const [surface, text] of [['hub', hub], ['flat', flat]]) {
      // Whatever selector the file passes (not the exact text 8 pins).
      const m = text.match(/const sessionVerified\s*= useSession\(([^;]+)\);/);
      if (!m) { wrong.push(`${surface}: selector not found`); continue; }
      // eslint-disable-next-line no-new-func
      const sel = new Function('subscriptionSessionState', `return ${m[1]};`)(subSession.subscriptionSessionState);
      for (const [label, state, want] of SESSIONS) {
        if (sel(state) !== want) wrong.push(`${surface}/${label} → ${!want}`);
      }
    }
    if (wrong.length === 0) ok(name);
    else bad(name, wrong.join('; '));
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

// 8d/8e — the warm observer (tip jar C1, PR #569's docs/plans/tip-jar/plan.md §3):
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
    // A one-slot fake React effect runner (the hook has ONE useEffect): runs
    // the effect on the first render and whenever a dep changes (Object.is),
    // like React's commit; `fx.reset()` is a fresh mount.
    const fx = { deps: null, pending: null, reset() { this.deps = null; this.pending = null; } };
    const removed = [];   // each removeQueries call: { filter, enabled at that render }
    const client = { removeQueries: (filter) => removed.push({ filter, enabled: seen && seen.enabled }) };
    const render = () => {
      warm.useWarmPaywallConfig();
      if (fx.pending) { const run = fx.pending; fx.pending = null; run(); }
    };
    const warm = load(src, {
      'react': { useEffect: (fn, deps) => {
        const changed = !fx.deps || deps.length !== fx.deps.length || deps.some((d, i) => !Object.is(d, fx.deps[i]));
        fx.deps = deps;
        if (changed) fx.pending = fn;
      } },
      '@tanstack/react-query': {
        useQuery: (opts) => { seen = opts; return {}; },
        useQueryClient: () => client,
      },
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

    // 8h — not verified ⇒ the cached entry is REMOVED (release-lead QA on
    //      #575): a verified → unverified / demo / unknown (a user change) /
    //      signed-out transition removes ['paywall-config'] ONCE; verified →
    //      verified never does; it never fires while the observer is enabled,
    //      and further not-verified renders don't repeat it (no loop). Sign-out
    //      is two sets: user null with verification true is still verified.
    const verifiedS = { isDemo: false, verification: { session_verified: true }, user: sleeper };
    const drops = [
      ['unverified', { isDemo: false, verification: { session_verified: false }, user: sleeper }],
      ['demo', { isDemo: true, verification: { session_verified: true }, user: acct }],
      ['unknown (user change)', { isDemo: false, verification: null, user: { user_id: '999', account_only: false } }],
      ['signed out', { isDemo: false, verification: null, user: null }],
    ];
    const problems = [];
    const sequence = (states) => {
      fx.reset(); removed.length = 0; flag = true;
      states.forEach((st) => { session = st; render(); });
      return removed.slice();
    };
    const keep = sequence([verifiedS, verifiedS, verifiedS]);
    if (keep.length !== 0) problems.push(`verified → verified removed ${keep.length}x`);
    const exactOnce = (r) => r.length === 1 && r[0].enabled === false
      && JSON.stringify(r[0].filter) === JSON.stringify({ queryKey: ['paywall-config'] });
    drops.forEach(([name, st]) => {
      const r = sequence([verifiedS, st, st]);
      if (!exactOnce(r)) problems.push(`verified → ${name}: ${JSON.stringify(r)}`);
    });
    // useSession.signOut's two sets: the first nulls the user but leaves
    // verification true, which subscriptionSessionState still calls verified
    // (no removal); the second nulls verification, which removes it once. An
    // effect keyed on `user` instead of `verified` fails here.
    const midSignOut = { isDemo: false, verification: { session_verified: true }, user: null };
    const signedOut = { isDemo: false, verification: null, user: null };
    const mid = sequence([verifiedS, midSignOut, midSignOut]);
    if (mid.length !== 0) problems.push(`sign-out's first set (user null, verified) removed ${mid.length}x`);
    const full = sequence([verifiedS, midSignOut, signedOut, signedOut]);
    if (!exactOnce(full)) problems.push(`sign-out's second set (verification null): ${JSON.stringify(full)}`);
    if (problems.length === 0) {
      ok("8h. not verified ⇒ ['paywall-config'] removed once (unverified / demo / user change / signed out); verified → verified and sign-out's first set keep it; no loop");
    } else {
      bad("8h. not verified ⇒ ['paywall-config'] removed once (unverified / demo / user change / signed out); verified → verified and sign-out's first set keep it; no loop",
        problems.join('; '));
    }
  }
}

// 8f — one cache entry: every ['paywall-config' (either quote) subscriber in src/ is
//     one of the four, each with the identical key + queryFn. A file whose only
//     use is a `getQueryData(['paywall-config', 'ios'])` cache read (#495's
//     SubscriptionSection) reads the same entry and never fetches, so it is a
//     reader, not a subscriber.
{
  const READ = /getQueryData(?:<[^>()]*>)?\(\s*\['paywall-config', 'ios'\]\s*\)/g;
  const SHARED = /queryKey: \['paywall-config', 'ios'\],\s*queryFn: \(\) => getPaywallConfig\('ios'\),/;
  const want = ['src/screens/PaywallScreen.tsx', 'src/screens/TipJarScreen.tsx',
    'src/state/useTipsOffered.ts', 'src/state/useWarmPaywallConfig.ts'];
  const users = [];
  const readers = [];
  const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).forEach((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p);
    else if (/\.(ts|tsx)$/.test(e.name)) {
      const src = strip(fs.readFileSync(p, 'utf8'));
      if (!/\[\s*['"]paywall-config['"]/.test(src)) return;
      if (/\[\s*['"]paywall-config['"]/.test(src.replace(READ, ''))) users.push(path.relative(ROOT, p));
      else readers.push(path.relative(ROOT, p));
    }
  });
  walk(path.join(ROOT, 'src'));
  const shared = want.filter((f) => SHARED.test(strip(read(path.join(ROOT, f)))));
  if (JSON.stringify(users.sort()) === JSON.stringify([...want].sort()) && shared.length === want.length) {
    ok(`8f. the four ['paywall-config','ios'] subscribers share one key + queryFn (PaywallScreen, TipJarScreen, useTipsOffered, useWarmPaywallConfig); cache-only readers: ${readers.join(', ') || 'none'}`);
  } else {
    bad("8f. the four ['paywall-config','ios'] subscribers share one key + queryFn",
      `users=${JSON.stringify(users)} shared=${JSON.stringify(shared)} readers=${JSON.stringify(readers)}`);
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

const asyncChecks = []; // awaited before the report (10's pending case)

// 10 — EXECUTED: the tip purchase refuses unless customerInfoApplies (round-3
//      P3). TipJarScreen runs under a fake React (hooks as plain calls, JSX
//      as element objects) and a tip is pressed. A refusal is the screen's
//      existing failure path: no purchaseTip, paywall_purchase_failed
//      tracked, "The App Store didn't finish the tip" shown. The refusal throws before
//      any await, so it lands synchronously. Refusals set neither the
//      thank-you nor the pending note. 10b (async): a verified tip that
//      StoreKit defers (RevenueCat code "20", Ask to Buy) tracks exactly
//      initiated → failed {user_cancelled:false}, sets the pending note, and
//      shows no thank-you and no error. isUserCancelled / isPaymentPending
//      are the REAL ones from api/purchases.ts; the useState setters are
//      named by their call order in the screen.
{
  const name = '10. the tip purchase runs ONLY when customerInfoApplies (verified AND RevenueCat is this user); demo, unverified, unknown and a mismatched identity take the failure path, nothing bought';
  if (!subSession) {
    bad(name, 'typescript not resolvable');
  } else {
    const TIP = { product_id: 'ftf_tip_199', display_price: '$1.99' };
    const realPurchases = loadTs('src/api/purchases.ts', {});
    const STATE_NAMES = [...s.matchAll(/const \[(\w+), set\w+\] = useState\b/g)].map((m) => m[1]);
    const mount = (state, rcId, purchaseImpl) => {
      const buys = [];
      const events = [];
      const sets = [];
      let nState = 0;
      const React = {
        createElement: (type, props, ...children) => ({ type, props: { ...(props || {}), children } }),
        Fragment: 'Fragment',
        useState: (init) => { const k = STATE_NAMES[nState++]; return [init, (v) => sets.push([k, v])]; },
        useEffect: () => {},
        useCallback: (fn) => fn,
        useMemo: (fn) => fn(),
      };
      const hook = (sel) => sel(state);
      hook.getState = () => state;
      const tokens = new Proxy({}, { get: () => 1 });
      const screen = loadTs('src/screens/TipJarScreen.tsx', {
        react: { __esModule: true, default: React, ...React },
        'react-native': { ActivityIndicator: 'ActivityIndicator', Pressable: 'Pressable', ScrollView: 'ScrollView', StyleSheet: { create: (x) => x }, View: 'View' },
        'react-native-safe-area-context': { SafeAreaView: 'SafeAreaView' },
        '@tanstack/react-query': { useQuery: ({ queryKey }) => ({ isLoading: false,
          data: queryKey[0] === 'paywall-config' ? { enabled: true, tips: [TIP] } : [{ identifier: TIP.product_id, priceString: '$1.99' }] }) },
        '../components/chalkline/Text': { __esModule: true, default: 'ChalkText' },
        '../components/chalkline': { Button: 'Button', Icon: 'Icon' },
        '../theme/chalkline': { chalk: tokens, ice: tokens, ink: tokens, radii: tokens, semantic: tokens, space: tokens },
        '../api/billing': { getPaywallConfig: async () => ({}) },
        '../api/purchases': {
          currentIdentityUserId: () => rcId, getTipProducts: async () => [],
          isUserCancelled: realPurchases.isUserCancelled,
          isPaymentPending: realPurchases.isPaymentPending,
          PurchaseIdentityError: class PurchaseIdentityError extends Error {},
          purchaseTip: (p) => { buys.push(p.identifier); return purchaseImpl ? purchaseImpl(p) : new Promise(() => {}); },
        },
        '../state/useFeatureFlags': { useFlag: () => true },
        '../state/useSession': { useSession: hook },
        '../state/subscriptionSession': subSession,
        '../api/events': { track: (n, p) => { events.push([n, p]); } },
      }, true);
      const tree = screen.default({ navigation: { canGoBack: () => true, goBack() {} }, route: { params: { source: 'settings' } } });
      const find = (n, id) => {
        if (!n || typeof n !== 'object') return null;
        if (Array.isArray(n)) { for (const c of n) { const f = find(c, id); if (f) return f; } return null; }
        if (n.props && n.props.testID === id) return n;
        return n.props ? find(n.props.children, id) : null;
      };
      const option = find(tree, `tipjar-option-${TIP.product_id}`);
      const pressed = option ? option.props.onPress() : null;
      const setTo = (k, pred) => sets.some(([key, v]) => key === k && pred(v));
      return { option, buys, events, sets, setTo, pressed };
    };
    const named = ['busy', 'error', 'thanked', 'pending'].every((k) => STATE_NAMES.includes(k));
    const wrong = [];
    const cases = [...SESSIONS.map(([label, state, runs]) => [label, state, state.user.user_id, runs]),
      ['verified, RevenueCat is ANOTHER user', SESSIONS[0][1], '999', false]];
    for (const [label, state, rcId, runs] of cases) {
      const m = mount(state, rcId);
      if (!m.option) { wrong.push(`${label}: the tip option did not render`); continue; }
      if (m.buys.length !== (runs ? 1 : 0)) wrong.push(`${label}: purchaseTip calls ${m.buys.length}`);
      if (!runs) {
        const failed = m.events.some(([n, p]) => n === 'paywall_purchase_failed' && p.user_cancelled === false);
        const copy = m.setTo('error', (v) => v === 'The App Store didn’t finish the tip. Check your connection and try again.');
        if (!failed || !copy) wrong.push(`${label}: not the existing failure path (failed=${failed} copy=${copy})`);
        if (m.setTo('thanked', Boolean) || m.setTo('pending', Boolean)) wrong.push(`${label}: a refusal set the thank-you or the pending note`);
      }
    }
    if (!named) wrong.push(`useState names by call order: ${JSON.stringify(STATE_NAMES)}`);
    if (wrong.length === 0) ok(name);
    else bad(name, wrong.join('; '));

    const name10b = '10b. a verified tip StoreKit defers (code "20", Ask to Buy): exactly initiated → failed {user_cancelled:false}, the pending note set, no thank-you, no error, no completion';
    asyncChecks.push((async () => {
      const v = SESSIONS[0][1];
      const m = mount(v, v.user.user_id, () => Promise.reject({ code: '20' }));
      if (!m.option || !m.pressed) { bad(name10b, 'the tip option did not render'); return; }
      await m.pressed;
      const wrongB = [];
      const names = m.events.map(([n]) => n);
      if (JSON.stringify(names) !== JSON.stringify(['paywall_purchase_initiated', 'paywall_purchase_failed'])) wrongB.push(`events ${JSON.stringify(names)}`);
      const fail = m.events.find(([n]) => n === 'paywall_purchase_failed');
      if (!fail || fail[1].user_cancelled !== false || fail[1].product_id !== TIP.product_id) wrongB.push(`failed props ${JSON.stringify(fail && fail[1])}`);
      if (m.buys.length !== 1) wrongB.push(`purchaseTip calls ${m.buys.length}`);
      if (!m.setTo('pending', (x) => x === true)) wrongB.push('pending not set');
      if (m.setTo('thanked', Boolean)) wrongB.push('thank-you set');
      if (m.setTo('error', (x) => x !== null)) wrongB.push('error text set');
      if (!named) wrongB.push(`useState names by call order: ${JSON.stringify(STATE_NAMES)}`);
      if (wrongB.length === 0) ok(name10b);
      else bad(name10b, wrongB.join('; '));
    })());
  }
}

Promise.all(asyncChecks)
  .catch((e) => bad('async checks', String((e && e.stack) || e)))
  .then(() => {
    console.log(pass.map((p) => `PASS  ${p}`).join('\n'));
    if (fail.length) {
      console.log(fail.map((f) => `FAIL  ${f}`).join('\n'));
      console.log(`\ncheck-tipjar: ${pass.length} passed, ${fail.length} failed`);
      process.exit(1);
    }
    console.log(`\ncheck-tipjar: ${pass.length} passed, 0 failed`);
  });
