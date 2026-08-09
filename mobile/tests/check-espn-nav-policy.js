#!/usr/bin/env node
// Regression test for the ESPN Connect WebView navigation gate
// (src/utils/espnNavPolicy.ts — 2026-08-09 mid-login Safari-escape fix).
//
// Pins allowEspnNavigation(), the pure decision behind
// EspnConnectScreen's onShouldStartLoadWithRequest. The screen passes
// originWhitelist={['*']} so react-native-webview's whitelist fallback
// (Linking.openURL — the Safari/native-app escape) is unreachable, and THIS
// function becomes the single gate: http(s) stays inside the WebView, every
// escape class is swallowed. If these expectations drift, a login navigation
// either leaves the app again or the Disney SSO chain breaks.
//
// Same idiom as check-espn-cookies.js: transpile the REAL module with the
// project's typescript, run under plain node. The module must stay
// import-free — any runtime import throws.
//
// Run: node tests/check-espn-nav-policy.js

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

const srcPath = path.join(__dirname, '..', 'src', 'utils', 'espnNavPolicy.ts');
const source = fs.readFileSync(srcPath, 'utf8');
const js = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;

const moduleShim = { exports: {} };
new Function('module', 'exports', 'require', js)(
  moduleShim,
  moduleShim.exports,
  (name) => {
    throw new Error(
      `espnNavPolicy.ts gained an unexpected runtime import ("${name}") — keep ` +
        'the decision function pure so this check can run it under plain node.',
    );
  },
);

const { allowEspnNavigation } = moduleShim.exports;

let failures = 0;
function check(name, url, expected) {
  const actual = allowEspnNavigation(url);
  if (actual !== expected) {
    failures += 1;
    console.error(`FAIL  ${name}: ${JSON.stringify(url)} → ${actual}, expected ${expected}`);
  } else {
    console.log(`ok    ${name}`);
  }
}

// ── The login chain itself stays inside the WebView ──────────────────────
check('espn login entry', 'https://www.espn.com/login', true);
check('espn parent domain', 'https://espn.com/', true);
check('fantasy.espn.com', 'https://fantasy.espn.com/football/league?leagueId=1', true);
check('Disney SSO responder (iframe)', 'https://cdn.registerdisney.go.com/v2/responder/responder.js', true);
check('Disney SSO api', 'https://api.registerdisney.go.com/v4/client/ESPN-ONESITE.WEB/guest/login', true);
check('disneyid', 'https://secure.disneyid.com/anything', true);
check('http (non-s) hop stays in-app, never Safari', 'http://www.espn.com/redirect', true);
check('unknown https host (ad/analytics iframe) stays in-app', 'https://securepubads.g.doubleclick.net/x', true);
check('recaptcha iframe', 'https://www.google.com/recaptcha/api2/anchor', true);

// ── WKWebView internals ──────────────────────────────────────────────────
check('about:blank', 'about:blank', true);
check('about:srcdoc', 'about:srcdoc', true);
check('data: resource', 'data:text/html;base64,PGI+', true);
check('blob: resource', 'blob:https://www.espn.com/uuid', true);

// ── App-scheme hops are swallowed (never Linking.openURL) ────────────────
check('espn:// deep link', 'espn://showClubhouse', false);
check('sportscenter:// deep link', 'sportscenter://x-callback-url/showClubhouse', false);
check('itms-appss App Store', 'itms-appss://itunes.apple.com/app/id317469184', false);
check('itms-apps App Store', 'itms-apps://itunes.apple.com/app/id317469184', false);
check('mailto', 'mailto:support@espn.com', false);
check('tel', 'tel:+15551234567', false);
check('intent (android)', 'intent://espn.com#Intent;scheme=https;end', false);

// ── App-bouncing http(s) hosts are swallowed ─────────────────────────────
check('App Store web (smart banner tap)', 'https://apps.apple.com/us/app/espn/id317469184', false);
check('itunes.apple.com', 'https://itunes.apple.com/app/id317469184', false);
check('branch link (espn.app.link)', 'https://espn.app.link/open-in-app', false);
check('bare app.link', 'https://app.link/x', false);
check('smart.link router', 'https://espn.smart.link/abc', false);
check('AppsFlyer onelink', 'https://espn.onelink.me/abc', false);
check('Firebase dynamic link', 'https://espn.page.link/abc', false);
// Suffix matching is label-aware: lookalike hosts do NOT match the blocklist.
check('lookalike notapp.link allowed', 'https://notapp.link/x', true);
check('lookalike apps.apple.com.evil.com allowed (not a bounce host)', 'https://apps.apple.com.evil.com/x', true);

// ── Garbage in → swallowed, never external ───────────────────────────────
check('empty string', '', false);
check('schemeless', 'www.espn.com/login', false);
check('https with empty host', 'https:///path', false);
// Userinfo/port stripping still resolves the real host.
check('userinfo trick still blocks App Store', 'https://user@apps.apple.com/app', false);
check('port on espn host allowed', 'https://www.espn.com:443/login', true);

if (failures > 0) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll espnNavPolicy checks passed.');
