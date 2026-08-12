#!/usr/bin/env node
// Fresh-login regression test (2026-08-12 incident).
//
// WHY THIS EXISTS. The operator signed in to ESPN with a friend's account to
// test, and could never switch back: the WebView's persistent web session
// (espn.com cookies + the Disney SSO session) silently re-authenticated the
// SAME account on every subsequent sign-in, even after the stored credential
// was deleted. The fix has three structural legs, each of which a future
// refactor could quietly undo without any test failing — hence this file:
//
//   1. EspnConnectScreen only MOUNTS its WebView after the ESPN/Disney
//      session clear settles (`storeCleared` gates the JSX) — the login page
//      can never load with a previous account's session attached.
//   2. The clear itself is SCOPED: espnCookies.ts touches only espn.com and
//      Disney-SSO (go.com) domains, and never calls clearAll — the native
//      cookie store is app-wide and unrelated domains must survive.
//   3. SleeperConnectScreen (same defect class: persistent localStorage JWT
//      auto-captured within ~800ms) runs its login WebView `incognito` —
//      non-persistent data store, no sharedCookiesEnabled to leak the shared
//      store back in.
//
// These are structural claims, so this is a structural test: it parses the
// real TSX with the project's own TypeScript and walks the AST.
//
// Run: node tests/check-espn-connect-clear.js

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

let failures = 0;
function ok(name) {
  console.log(`PASS  ${name}`);
}
function fail(name, detail) {
  failures += 1;
  console.error(`FAIL  ${name}${detail ? `: ${detail}` : ''}`);
}
function assert(cond, name, detail) {
  if (cond) ok(name);
  else fail(name, detail);
}

function parse(rel) {
  const file = path.join(__dirname, '..', rel);
  return ts.createSourceFile(
    file,
    fs.readFileSync(file, 'utf8'),
    ts.ScriptTarget.ES2019,
    /* setParentNodes */ true,
    ts.ScriptKind.TSX,
  );
}

function walk(node, visit) {
  visit(node);
  node.forEachChild((c) => walk(c, visit));
}

function findAll(root, pred) {
  const out = [];
  walk(root, (n) => {
    if (pred(n)) out.push(n);
  });
  return out;
}

function tagOf(node) {
  if (ts.isJsxSelfClosingElement(node)) return node.tagName.getText();
  if (ts.isJsxElement(node)) return node.openingElement.tagName.getText();
  return null;
}

function attrsOf(node) {
  const opening = ts.isJsxSelfClosingElement(node) ? node : node.openingElement;
  return opening.attributes.properties.filter(ts.isJsxAttribute);
}

function ancestors(node) {
  const out = [];
  for (let p = node.parent; p; p = p.parent) out.push(p);
  return out;
}

// ═══════════════════════════════════════════════════════════════════════
// 1. espnCookies.ts — the clear is scoped to ESPN/Disney, never clearAll
// ═══════════════════════════════════════════════════════════════════════

const cookiesSrc = parse('src/utils/espnCookies.ts');
const cookiesText = cookiesSrc.getFullText();

// AST check, not a grep — the file's comments legitimately SAY "clearAll"
// while explaining why it must never be called.
const clearAllCalls = findAll(
  cookiesSrc,
  (n) => ts.isCallExpression(n) && /(^|\.)clearAll$/.test(n.expression.getText()),
);
assert(
  clearAllCalls.length === 0,
  'espnCookies.ts never calls clearAll',
  'the native cookie store is app-wide — clearAll would nuke unrelated domains (Sleeper included)',
);

// Every https URL in the file must be an espn.com or Disney-SSO (go.com)
// host: the domain lists ARE the entire clear surface, so this is the
// machine-checkable form of "the clear touches nothing unrelated".
const urlLiterals = findAll(
  cookiesSrc,
  (n) => ts.isStringLiteral(n) && /^https:\/\//.test(n.text),
).map((n) => n.text);
assert(urlLiterals.length >= 4, 'espnCookies.ts declares its clear domains', `found ${urlLiterals.length} https URLs`);
const offScope = urlLiterals.filter((u) => {
  const host = u.replace(/^https:\/\//, '').split('/')[0].toLowerCase();
  return !(host === 'espn.com' || host.endsWith('.espn.com') ||
           host === 'go.com' || host.endsWith('.go.com'));
});
assert(
  offScope.length === 0,
  'every clear domain is an espn.com or Disney-SSO go.com host',
  `out-of-scope: ${JSON.stringify(offScope)}`,
);

// The Disney SSO surface is part of the clear — dropping it re-opens the
// silent-reauth path even with espn_s2/SWID gone.
assert(
  /registerdisney\.go\.com/.test(cookiesText),
  'the Disney SSO domain is part of the clear surface',
);
assert(
  /export\s+async\s+function\s+clearEspnCookies/.test(cookiesText),
  'clearEspnCookies is exported',
);

// ═══════════════════════════════════════════════════════════════════════
// 2. EspnConnectScreen — clear BEFORE the login page can load
// ═══════════════════════════════════════════════════════════════════════

const espnSrc = parse('src/screens/EspnConnectScreen.tsx');
const espnText = espnSrc.getFullText();

assert(
  /import\s*\{[^}]*clearEspnCookies[^}]*\}\s*from\s*'\.\.\/utils\/espnCookies'/.test(espnText),
  'EspnConnectScreen imports clearEspnCookies',
);

// The WebView must sit under a conditional on `storeCleared` — i.e. it does
// not EXIST until the clear settles, so the login page cannot load with a
// stale session attached.
const webviews = findAll(espnSrc, (n) => tagOf(n) === 'WebView');
assert(webviews.length === 1, 'EspnConnectScreen renders exactly one WebView', `found ${webviews.length}`);
if (webviews.length === 1) {
  const guardedByCleared = ancestors(webviews[0]).some(
    (a) => ts.isConditionalExpression(a) && a.condition.getText().includes('storeCleared'),
  );
  assert(
    guardedByCleared,
    'the WebView mounts only after the session clear settles (storeCleared gate)',
    'the WebView JSX must be inside a conditional on the cleared state',
  );
}

// And the cleared state may only flip AFTER clearEspnCookies resolves:
// setStoreCleared(true) must live in a function that awaits clearEspnCookies
// earlier in its body.
const setCalls = findAll(
  espnSrc,
  (n) =>
    ts.isCallExpression(n) &&
    n.expression.getText() === 'setStoreCleared' &&
    n.arguments.length === 1 &&
    n.arguments[0].getText() === 'true',
);
assert(setCalls.length >= 1, 'EspnConnectScreen flips storeCleared to true somewhere');
for (const call of setCalls) {
  const fn = ancestors(call).find(
    (a) => ts.isArrowFunction(a) || ts.isFunctionExpression(a) || ts.isFunctionDeclaration(a),
  );
  const body = fn ? fn.getText() : '';
  const clearIdx = body.indexOf('await clearEspnCookies()');
  const setIdx = body.indexOf(call.getText());
  assert(
    clearIdx !== -1 && clearIdx < setIdx,
    'setStoreCleared(true) runs only after `await clearEspnCookies()`',
    'the clear must settle before the WebView is allowed to mount',
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 3. SleeperConnectScreen — same defect class, incognito fix
// ═══════════════════════════════════════════════════════════════════════

const sleeperSrc = parse('src/screens/SleeperConnectScreen.tsx');
const sleeperWebviews = findAll(sleeperSrc, (n) => tagOf(n) === 'WebView');
assert(sleeperWebviews.length === 1, 'SleeperConnectScreen renders exactly one WebView', `found ${sleeperWebviews.length}`);
if (sleeperWebviews.length === 1) {
  const attrNames = attrsOf(sleeperWebviews[0]).map((a) => a.name.getText());
  assert(
    attrNames.includes('incognito'),
    'the Sleeper login WebView is incognito',
    'a persistent store restores the last login and the poller captures the wrong account',
  );
  assert(
    !attrNames.includes('sharedCookiesEnabled'),
    'the Sleeper login WebView does NOT re-import shared cookies',
    'sharedCookiesEnabled would copy the app-wide store back into the fresh session',
  );
}

console.log('');
if (failures) {
  console.error(`${failures} check(s) failed.`);
  process.exit(1);
}
console.log('All ESPN/Sleeper connect fresh-login checks passed.');
