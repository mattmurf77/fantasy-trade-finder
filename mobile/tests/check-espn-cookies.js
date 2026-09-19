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
// domains and clearEspnCookies() clears both names everywhere; the pure
// extractor needs no native access.
const cookieGetCalls = [];
const cookieClearCalls = [];
// Mutable per-URL store so the enumerate-and-clear scenario below can seed
// cookies (e.g. a Disney SSO session) and watch them get cleared by name.
const storeByUrl = {};
const cookieManagerStub = {
  default: {
    get: (url) => {
      cookieGetCalls.push(url);
      return Promise.resolve(storeByUrl[url] || null);
    },
    clearByName: (url, name, useWebKit) => {
      cookieClearCalls.push({ url, name, useWebKit: !!useWebKit });
      return Promise.resolve(true);
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

const {
  pickEspnCookies,
  readEspnCookies,
  clearEspnCookies,
  ESPN_COOKIE_DOMAINS,
  DISNEY_SSO_DOMAINS,
} = moduleShim.exports;

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

  // ── clearEspnCookies: fresh-login guarantee ────────────────────────────
  // With an EMPTY store, only the named espn_s2/SWID floor fires: BOTH
  // cookie names on BOTH ESPN domains in BOTH native stores
  // (WKHTTPCookieStore + NSHTTPCookieStorage) — a stale espn_s2 surviving
  // any of the 2×2×2 combinations is the insta-capture loop the screen's
  // mount-time clear exists to prevent.
  await clearEspnCookies();
  check('empty store: named-clear floor (2 names × 2 domains × 2 stores)',
        cookieClearCalls.length, 8);
  const combos = new Set(
    cookieClearCalls.map((c) => `${c.url}|${c.name}|${c.useWebKit ? 'wk' : 'ns'}`),
  );
  const expected = [];
  for (const d of ESPN_COOKIE_DOMAINS) {
    for (const n of ['espn_s2', 'SWID']) {
      expected.push(`${d}|${n}|wk`, `${d}|${n}|ns`);
    }
  }
  check(
    'clears every domain × name × store combo',
    [...combos].sort(),
    expected.sort(),
  );

  // ── enumerate-and-clear (2026-08-12 incident): a surviving Disney SSO
  // session (or any non-espn_s2 espn.com session cookie) silently
  // re-authenticates the previous account — the clear must enumerate each
  // ESPN/Disney domain and clear whatever it finds there, by name, on that
  // domain only.
  check(
    'Disney SSO domains are part of the clear surface',
    [...DISNEY_SSO_DOMAINS].sort(),
    ['https://cdn.registerdisney.go.com', 'https://registerdisney.go.com'],
  );
  storeByUrl['https://registerdisney.go.com'] = { OneID: { value: 'sso-session' } };
  storeByUrl['https://www.espn.com'] = { espn_auth: { value: 'legacy-session' } };
  cookieClearCalls.length = 0;
  await clearEspnCookies();
  const cleared = new Set(
    cookieClearCalls.map((c) => `${c.url}|${c.name}|${c.useWebKit ? 'wk' : 'ns'}`),
  );
  check(
    'seeded Disney SSO cookie is cleared on its own domain (both stores)',
    ['https://registerdisney.go.com|OneID|wk', 'https://registerdisney.go.com|OneID|ns']
      .every((k) => cleared.has(k)),
    true,
  );
  check(
    'seeded non-captured espn.com session cookie is cleared too',
    ['https://www.espn.com|espn_auth|wk', 'https://www.espn.com|espn_auth|ns']
      .every((k) => cleared.has(k)),
    true,
  );
  check(
    'enumerated clears never leave the domain the cookie was found on',
    cookieClearCalls.every((c) =>
      [...ESPN_COOKIE_DOMAINS, ...DISNEY_SSO_DOMAINS].includes(c.url)),
    true,
  );

  if (failures > 0) {
    console.error(`\n${failures} check(s) failed.`);
    process.exit(1);
  }
  console.log('\nAll espnCookies checks passed.');
})();
