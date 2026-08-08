#!/usr/bin/env node
// Regression test for the ESPN Connect cookie extractor (Phase 1b, flag
// espn.webview_capture; scope docs/plans/espn-connect-webview/scope.md).
//
// Pins the pure core of src/utils/espnCookies.ts — pickEspnCookies() — which
// selects the first native-cookie-store bag carrying BOTH espn_s2 and SWID.
// espn_s2 can be HttpOnly, which is the whole reason capture reads the native
// store instead of document.cookie; this test is the unit-level coverage the
// scope block promises in place of the (waived) in-WebView Maestro leg.
//
// Mobile has no jest harness, so this transpiles the REAL module with the
// project's typescript and runs it under plain node — the same idiom as
// check-session-rerank.js. The one runtime import (@react-native-cookies/
// cookies) is stubbed via the require shim; every other import throws, which
// keeps the module honest about staying node-runnable.
//
// Run: node tests/check-espn-cookies.js  (or wire an npm script)

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

const srcPath = path.join(__dirname, '..', 'src', 'utils', 'espnCookies.ts');
const source = fs.readFileSync(srcPath, 'utf8');
const js = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;

// CookieManager records calls so we can assert readEspnCookies() polls both
// domains; the pure extractor needs no native access.
const cookieGetCalls = [];
const cookieManagerStub = {
  default: {
    get: (url) => {
      cookieGetCalls.push(url);
      return Promise.resolve(null);
    },
  },
};

const moduleShim = { exports: {} };
new Function('module', 'exports', 'require', js)(
  moduleShim,
  moduleShim.exports,
  (name) => {
    if (name === '@react-native-cookies/cookies') return cookieManagerStub;
    throw new Error(
      `espnCookies.ts gained an unexpected runtime import ("${name}") — keep ` +
        'the extractor pure so this check can run it under plain node.',
    );
  },
);

const { pickEspnCookies, readEspnCookies, ESPN_COOKIE_DOMAINS } = moduleShim.exports;

let failures = 0;
function check(name, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (!ok) {
    failures += 1;
    console.error(
      `FAIL  ${name}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
    );
  } else {
    console.log(`ok    ${name}`);
  }
}

const bag = (s2, swid) => {
  const b = {};
  if (s2 !== undefined) b['espn_s2'] = { value: s2 };
  if (swid !== undefined) b['SWID'] = { value: swid };
  return b;
};

// ── Both cookies present in the first bag ────────────────────────────────
check(
  'both present → pair',
  pickEspnCookies([bag('S2VALUE', '{SWID-1}')]),
  { espnS2: 'S2VALUE', swid: '{SWID-1}' },
);

// ── SWID braces preserved verbatim (the paste field + backend expect them)
check(
  'SWID braces preserved',
  pickEspnCookies([bag('x', '{A1B2-C3}')]).swid,
  '{A1B2-C3}',
);

// ── Only one cookie → no pair ────────────────────────────────────────────
check('espn_s2 only → null', pickEspnCookies([bag('only', undefined)]), null);
check('SWID only → null', pickEspnCookies([bag(undefined, '{x}')]), null);

// ── Empty / whitespace values do not count as present ────────────────────
check('empty espn_s2 → null', pickEspnCookies([bag('', '{x}')]), null);
check('whitespace SWID → null', pickEspnCookies([bag('s2', '   ')]), null);

// ── Value trimming ───────────────────────────────────────────────────────
check(
  'values trimmed',
  pickEspnCookies([bag('  s2  ', '  {x}  ')]),
  { espnS2: 's2', swid: '{x}' },
);

// ── First complete bag wins across domains ───────────────────────────────
check(
  'second bag completes',
  pickEspnCookies([bag('s2', undefined), bag('s2b', '{y}')]),
  { espnS2: 's2b', swid: '{y}' },
);

// ── Null / undefined / empty inputs are safe ─────────────────────────────
check('null bag skipped', pickEspnCookies([null, undefined, bag('s2', '{z}')]), {
  espnS2: 's2',
  swid: '{z}',
});
check('all empty → null', pickEspnCookies([]), null);

// ── readEspnCookies polls BOTH domains and returns null when store empty ──
(async () => {
  const res = await readEspnCookies();
  check('empty store → null', res, null);
  check(
    'polls both ESPN domains',
    cookieGetCalls.slice().sort(),
    [...ESPN_COOKIE_DOMAINS].sort(),
  );

  if (failures > 0) {
    console.error(`\n${failures} check(s) failed.`);
    process.exit(1);
  }
  console.log('\nAll espnCookies checks passed.');
})();
