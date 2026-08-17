#!/usr/bin/env node
// #321 ESPN wrong-account surface — structural regression test (2026-08-16).
//
// WHY THIS EXISTS. The identity-binding fix rejects a captured ESPN pair
// whose SWID doesn't own the user's bound team with a 403 whose wire code is
// UNCHANGED (`espn_bad_credentials`) plus an additive `reason:
// "wrong_account"`. Every leg of the client surface is a thing a future
// refactor could quietly undo without any test failing — hence this file
// (PRD §7.2, docs/feedback/items/321-espn-token-bleed/prd.md):
//
//   1. EspnConnectScreen renders a DISTINCT wrong-account state
//      (espn-connect.wrong-account) gated on storeFail === 'wrong_account',
//      with copy naming the real recovery, reachable from the storePair
//      failure path; the retry resets to a fresh sign-in (only
//      'unreachable' re-sends the same pair).
//   2. api/espn.ts exports the typed narrowing helper espnRejectionReason,
//      itself gated on espnCredentialsRejected (absent field → null →
//      exactly today's behavior).
//   3. EspnLinkSheet's link-path rejection surface holds: the
//      isEspnAuthRequired branch matches ONLY `espn_auth_required` (so a
//      403 espn_bad_credentials falls through to the generic branch that
//      renders the server's message), and the espn-link.error element
//      renders {error}.
//   4. The R11 analytics event espn_connect_store_rejected fires from the
//      storePair failure path with a `reason` property.
//   5. No device-side persistence of espn_s2/SWID anywhere in mobile/src.
//
// Run: node tests/check-espn-wrong-account.js

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

function read(rel) {
  return fs.readFileSync(path.join(__dirname, '..', rel), 'utf8');
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

// ── 1. EspnConnectScreen: the wrong-account state ─────────────────────────

const screenSrc = read('src/screens/EspnConnectScreen.tsx');
const screen = parse('src/screens/EspnConnectScreen.tsx');

assert(
  /espnRejectionReason/.test(screenSrc) &&
    /from '\.\.\/api\/espn'/.test(screenSrc),
  'EspnConnectScreen imports espnRejectionReason from api/espn',
);

// The distinct wrong-account element exists…
const wrongAccountEls = findAll(
  screen,
  (n) =>
    (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)) &&
    n.attributes.properties.some(
      (p) =>
        ts.isJsxAttribute(p) &&
        p.name.getText() === 'testID' &&
        p.initializer &&
        p.initializer.getText().includes('espn-connect.wrong-account'),
    ),
);
assert(
  wrongAccountEls.length === 1,
  'exactly one espn-connect.wrong-account element',
  `found ${wrongAccountEls.length}`,
);

// …gated on storeFail === 'wrong_account'…
if (wrongAccountEls.length === 1) {
  let gate = wrongAccountEls[0];
  let gated = false;
  while (gate) {
    if (
      ts.isConditionalExpression(gate) &&
      /storeFail\s*===\s*'wrong_account'/.test(gate.condition.getText())
    ) {
      gated = true;
      break;
    }
    gate = gate.parent;
  }
  assert(gated, "wrong-account element is gated on storeFail === 'wrong_account'");
}

// …with copy naming the real recovery, not the generic 'sign in again'.
assert(
  /owns\s+your\s+team/i.test(screenSrc),
  'wrong-account copy names the owning-account recovery ("owns your team")',
);

// storeFail's state union includes 'wrong_account' (the storePair failure
// path can reach the state at all).
assert(
  /'rejected'\s*\|\s*'wrong_account'\s*\|\s*'unreachable'/.test(
    screenSrc.replace(/\s+/g, ' '),
  ) ||
    /null \| 'rejected' \| 'wrong_account' \| 'unreachable'/.test(
      screenSrc.replace(/\s+/g, ' '),
    ),
  "storeFail union includes 'wrong_account'",
);
assert(
  /setStoreFail\(\s*reason === 'unavailable'/.test(
    screenSrc.replace(/\s+/g, ' '),
  ) || /setStoreFail\(/.test(screenSrc),
  'storePair failure path sets storeFail',
);

// Retry semantics: ONLY 'unreachable' re-sends the captured pair — a
// wrong-account (or rejected) pair must go through the fresh sign-in reset.
assert(
  /mode === 'unreachable' && pairRef\.current/.test(screenSrc),
  "retryStore re-sends the pair only for 'unreachable'",
);

// ── 2. api/espn.ts: typed reason helper (R8) ──────────────────────────────

const apiSrc = read('src/api/espn.ts');
assert(
  /export function espnRejectionReason\(err: unknown\): string \| null/.test(apiSrc),
  'espn.ts exports espnRejectionReason(err): string | null',
);
assert(
  /if \(!espnCredentialsRejected\(err\)\) return null;/.test(apiSrc),
  'espnRejectionReason narrows through espnCredentialsRejected first',
);
assert(
  /typeof reason === 'string' \? reason : null/.test(apiSrc),
  'espnRejectionReason tolerates an absent/non-string reason (→ null)',
);
// Compatibility: the rejection predicate still keys on the UNCHANGED wire
// code — this is what keeps old builds working against the new 403.
assert(
  /error === 'espn_bad_credentials'/.test(apiSrc),
  "espnCredentialsRejected still matches wire code 'espn_bad_credentials'",
);

// ── 3. EspnLinkSheet: link-path rejection surface (review N1) ─────────────

const sheetSrc = read('src/components/EspnLinkSheet.tsx');
const clientSrc = read('src/api/client.ts');

// The auth-required branch narrows on espn_auth_required ONLY (via the
// ApiError getter), so a 403 espn_bad_credentials falls through to the
// generic branch…
assert(
  /error === 'espn_auth_required'/.test(clientSrc),
  "ApiError.isEspnAuthRequired matches only 'espn_auth_required'",
);
assert(
  !/espn_bad_credentials/.test(
    clientSrc.slice(
      clientSrc.indexOf('get isEspnAuthRequired'),
      clientSrc.indexOf('}', clientSrc.indexOf('get isEspnAuthRequired') + 400),
    ),
  ),
  'isEspnAuthRequired does not swallow espn_bad_credentials',
);
// …and the generic branch renders the SERVER message.
assert(
  /setError\(e\?\.message \|\|/.test(sheetSrc),
  "EspnLinkSheet's generic catch renders the server message (e?.message)",
);
// Branch ORDER: isEspnAuthRequired is checked before the generic branch in
// both catch blocks, and the error element exists.
const sheet = parse('src/components/EspnLinkSheet.tsx');
const errorEls = findAll(
  sheet,
  (n) =>
    (ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)) &&
    n.attributes.properties.some(
      (p) =>
        ts.isJsxAttribute(p) &&
        p.name.getText() === 'testID' &&
        p.initializer &&
        p.initializer.getText().includes('espn-link.error'),
    ),
);
assert(errorEls.length >= 1, 'espn-link.error element(s) exist', String(errorEls.length));
assert(
  errorEls.every((el) => /\{error\}/.test(el.parent.getText())),
  'espn-link.error renders {error}',
);

// ── 4. R11 analytics: espn_connect_store_rejected from storePair ──────────

const storePairMatch = screenSrc.match(
  /const storePair = useCallback\([\s\S]*?\n  \);/,
);
assert(!!storePairMatch, 'storePair callback found');
if (storePairMatch) {
  const body = storePairMatch[0];
  assert(
    /track\(\s*'espn_connect_store_rejected'/.test(body),
    'storePair failure path fires espn_connect_store_rejected',
  );
  assert(
    /reason,/.test(body) && /source:/.test(body) && /saw_otp:/.test(body),
    'the event carries reason, source and saw_otp',
  );
  assert(
    /'wrong_account'[\s\S]*'bad_credentials'/.test(body) &&
      /'unavailable'/.test(body),
    'reason distinguishes wrong_account / bad_credentials / unavailable',
  );
}

// ── 5. No device-side persistence of espn_s2/SWID (unchanged invariant) ───

function* walkDir(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) yield* walkDir(p);
    else if (/\.(ts|tsx|js|jsx)$/.test(entry.name)) yield p;
  }
}
// A storage CALL whose arguments look credential-shaped is the offense —
// comments and unrelated AsyncStorage use (device id, league cache) are not.
const offenders = [];
const stripComments = (s) =>
  s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
for (const file of walkDir(path.join(__dirname, '..', 'src'))) {
  const src = stripComments(fs.readFileSync(file, 'utf8'));
  const callRe = /(AsyncStorage|SecureStore)\s*\.\s*\w+\s*\(([^;]{0,300})/g;
  let m;
  while ((m = callRe.exec(src))) {
    if (/espn|swid/i.test(m[2])) {
      offenders.push(path.relative(path.join(__dirname, '..'), file));
      break;
    }
  }
}
assert(
  offenders.length === 0,
  'no AsyncStorage/SecureStore call persists anything espn_s2/SWID-shaped',
  offenders.join(', '),
);

process.exit(failures ? 1 : 0);
