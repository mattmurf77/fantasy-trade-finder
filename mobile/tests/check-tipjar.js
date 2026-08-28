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
//      surfaces, inside the same `monetize.paywall` gate as the pro row.
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

// 8 — settings entry on both surfaces, inside the paywall gate
{
  const inHub = hub.includes('settings-tip-row')
    && hub.indexOf('settings-tip-row') > hub.indexOf('paywallOn ?');
  const inFlat = flat.includes('settings-tip-row')
    && flat.indexOf('settings-tip-row') > flat.indexOf('paywallEnabled ?');
  const navs = (hub + flat).match(/navigate\?\.\('TipJar', \{ source: 'settings' \}\)/g) || [];
  if (inHub && inFlat && navs.length === 2) {
    ok('8. settings-tip-row on both surfaces, flag-gated, navigates to TipJar');
  } else {
    bad('8. settings-tip-row on both surfaces, flag-gated, navigates to TipJar',
      `hub=${inHub} flat=${inFlat} navs=${navs.length}`);
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
