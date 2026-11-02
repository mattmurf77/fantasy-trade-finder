#!/usr/bin/env node
// Sign-in identity labels in Settings (ESPN/MFL sign-in, onboarding-eng side).
//
// WHY THIS EXISTS. A proven ESPN or MFL sign-in mints an acct_* account whose
// linked identity has provider `espn` / `mfl`, and whose session reports
// verified_via `espn` / `mfl_login` (platforms-eng's frozen values,
// 2026-10-26). Settings used to render every identity with a two-way ternary,
// `provider === 'apple' ? 'Signed in with Apple' : 'Signed in with Google'`, so
// an ESPN account read "Signed in with Google". The hub's provider type was
// 'apple' | 'google', so an ESPN/MFL user got no sign-in label at all. Neither
// is visible to tsc, and D-056 left no simulator, so:
//
//   1. The shared map (screens/settings/identityLabels.ts, EXECUTED) labels
//      every provider in a hard-coded list (apple, google, espn, mfl) with its
//      exact string, and an unknown provider gets no label.
//   2. No `: 'Signed in with …'` fallback remains anywhere in mobile/src, and
//      no "Signed in with …" string literal lives outside the shared map.
//   3. Both identity-row renderers (the hub's AccountIdentitySection and the
//      flag-off flat SettingsScreen) take their label from identityLabel()
//      and render NO row when it returns null.
//   4. The hub's sign-in label (its own `verifiedVia` / `provider` /
//      `signInLabel` declarations, lifted and EXECUTED) maps an espn/mfl
//      identity and verified_via `espn` / `mfl_login` to "ESPN" / "MFL", with
//      the Apple, Google, Sleeper and demo answers unchanged. `mfl_login`
//      means MFL only on an account-only session: /api/mfl/auth-link also
//      writes it for a Sleeper user who connects MFL, who stays "Sleeper"
//      (release-lead QA P2).
//
// HONEST LABEL (G-035). 1 and 4 run the real code; 2 and 3 pin wiring. The
// runtime proof is the TestFlight checklist in the PR. Every pin was watched
// failing on a mutated copy first (G-035/G-050).
//
// FTF_MOBILE_TEST_ROOT can point at a copy of mobile/ (sabotage runs).
// Run: node tests/check-signin-identity-labels.js   (or: npm run test:signin-identity-labels)

'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

let ts;
try {
  ts = require('typescript');
} catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}

const ROOT = process.env.FTF_MOBILE_TEST_ROOT || path.resolve(__dirname, '..');
const F = {
  labels:  'src/screens/settings/identityLabels.ts',
  section: 'src/screens/settings/sections/AccountIdentitySection.tsx',
  flat:    'src/screens/SettingsScreen.tsx',
  hub:     'src/screens/settings/SettingsHubScreen.tsx',
};
// The providers the server can link (platforms-eng, 2026-10-26), and their rows.
const EXPECTED = {
  apple: 'Signed in with Apple',
  google: 'Signed in with Google',
  espn: 'Signed in with ESPN',
  mfl: 'Signed in with MFL',
};

let failures = 0;
let passed = 0;
function check(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`PASS  ${name}`);
  } catch (e) {
    failures += 1;
    console.error(`FAIL  ${name}\n      ${e.message}`);
  }
}
function expect(cond, msg) { if (!cond) throw new Error(msg); }

const read = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');
function parse(rel, text = read(rel)) {
  return ts.createSourceFile(rel, text, ts.ScriptTarget.Latest, true,
    rel.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
}
function findAll(root, pred) {
  const out = [];
  const visit = (n) => { if (pred(n)) out.push(n); ts.forEachChild(n, visit); };
  visit(root);
  return out;
}
const isStr = (n) => !!n && (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n));
function transpile(code) {
  return ts.transpileModule(code, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React },
  }).outputText;
}
function srcFiles(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...srcFiles(p));
    else if (/\.(ts|tsx)$/.test(e.name)) out.push(p);
  }
  return out;
}

// ── 1. The shared map (executed) ───────────────────────────────────────────
check('1. identityLabels labels apple, google, espn and mfl exactly; an unknown provider gets none', () => {
  const mod = { exports: {} };
  vm.runInNewContext(transpile(read(F.labels)), {
    module: mod, exports: mod.exports,
    require: (n) => { throw new Error(`identityLabels.ts must have no runtime imports (imports ${n})`); },
  }, { filename: F.labels });
  const { IDENTITY_LABELS, identityLabel } = mod.exports;
  expect(IDENTITY_LABELS && typeof identityLabel === 'function', 'identityLabels.ts does not export IDENTITY_LABELS and identityLabel');
  for (const [provider, want] of Object.entries(EXPECTED)) {
    expect(IDENTITY_LABELS[provider] === want, `IDENTITY_LABELS.${provider} is ${JSON.stringify(IDENTITY_LABELS[provider])}, want ${JSON.stringify(want)}`);
    expect(identityLabel(provider) === want, `identityLabel('${provider}') is ${JSON.stringify(identityLabel(provider))}, want ${JSON.stringify(want)}`);
  }
  for (const unknown of ['sleeper', 'fleaflicker', 'Google', 'constructor', 'toString', '', null, undefined]) {
    expect(identityLabel(unknown) === null, `identityLabel(${JSON.stringify(unknown)}) is ${JSON.stringify(identityLabel(unknown))}, want null (no row)`);
  }
});

// ── 2. No "Signed in with …" fallback anywhere ─────────────────────────────
check("2. no `: 'Signed in with …'` fallback in mobile/src; the strings live only in the shared map", () => {
  const bad = [];
  for (const file of srcFiles(path.join(ROOT, 'src'))) {
    const rel = path.relative(ROOT, file).split(path.sep).join('/');
    const text = fs.readFileSync(file, 'utf8');
    // The map's own `google: 'Signed in with Google'` entry has the same text
    // shape, so the textual scan skips the map; the AST scan below covers it.
    if (rel !== F.labels && /:\s*(['"`])Signed in with Google\1/.test(text)) bad.push(`${rel}: a ": 'Signed in with Google'" fallback`);
    const sf = parse(rel, text);
    for (const c of findAll(sf, (n) => ts.isConditionalExpression(n) && isStr(n.whenFalse) && /^Signed in with /.test(n.whenFalse.text))) {
      bad.push(`${rel}:${sf.getLineAndCharacterOfPosition(c.getStart(sf)).line + 1}: a ternary falls back to ${JSON.stringify(c.whenFalse.text)}`);
    }
    if (rel !== F.labels) {
      for (const s of findAll(sf, (n) => isStr(n) && /^Signed in with /.test(n.text))) {
        bad.push(`${rel}:${sf.getLineAndCharacterOfPosition(s.getStart(sf)).line + 1}: ${JSON.stringify(s.text)} outside identityLabels.ts`);
      }
    }
  }
  expect(!bad.length, bad.join('; '));
});

// ── 3. Both row renderers use the map and drop unknown providers ───────────
check('3. AccountIdentitySection and the flat SettingsScreen render identityLabel(...) and no row when it is null', () => {
  const bad = [];
  for (const rel of [F.section, F.flat]) {
    const sf = parse(rel);
    const imp = sf.statements.some((s) => ts.isImportDeclaration(s) && isStr(s.moduleSpecifier)
      && /(^|\/)identityLabels$/.test(s.moduleSpecifier.text) && /\bidentityLabel\b/.test(s.getText(sf)));
    if (!imp) bad.push(`${rel} does not import identityLabel from identityLabels`);
    const maps = findAll(sf, (n) => ts.isCallExpression(n) && n.expression.getText(sf) === 'identities.map');
    if (maps.length !== 1) { bad.push(`${rel}: ${maps.length} identities.map(...) calls, want 1`); continue; }
    const cb = maps[0].arguments[0];
    const body = cb && (ts.isArrowFunction(cb) || ts.isFunctionExpression(cb)) && ts.isBlock(cb.body) ? cb.body : null;
    if (!body) { bad.push(`${rel}: the identities.map callback has no block body`); continue; }
    const decl = body.statements.find((s) => ts.isVariableStatement(s)
      && s.declarationList.declarations.some((d) => d.name.getText(sf) === 'label'
        && d.initializer && d.initializer.getText(sf).replace(/\s+/g, '') === 'identityLabel(ident.provider)'));
    if (!decl) bad.push(`${rel}: no \`const label = identityLabel(ident.provider)\` in the identities.map callback`);
    const guard = body.statements.find((s) => ts.isIfStatement(s)
      && s.expression.getText(sf).replace(/\s+/g, '') === '!label'
      && /^return\s+null\s*;?$/.test((ts.isBlock(s.thenStatement) && s.thenStatement.statements.length === 1
        ? s.thenStatement.statements[0] : s.thenStatement).getText(sf).trim()));
    if (!guard) bad.push(`${rel}: no \`if (!label) return null;\` in the identities.map callback`);
    if (decl && guard && body.statements.indexOf(guard) < body.statements.indexOf(decl)) bad.push(`${rel}: the null guard runs before the label is read`);
    const rowKey = findAll(body, (n) => ts.isJsxElement(n) && n.openingElement.tagName.getText(sf) === 'Text'
      && /styles\.rowKey/.test(n.openingElement.getText(sf)));
    if (rowKey.length !== 1 || rowKey[0].children.map((c) => c.getText(sf).trim()).filter(Boolean).join('') !== '{label}') {
      bad.push(`${rel}: the row's rowKey <Text> does not render exactly {label}`);
    }
  }
  expect(!bad.length, bad.join('; '));
});

// ── 4. The hub label (executed) ────────────────────────────────────────────
check("4. the hub maps espn / mfl identities and verified_via 'espn' / 'mfl_login' to ESPN / MFL", () => {
  const sf = parse(F.hub);
  const stmt = (name) => sf.statements.length && findAll(sf, (n) => ts.isVariableStatement(n)
    && n.declarationList.declarations.some((d) => d.name.getText(sf) === name))[0];
  const parts = ['verifiedVia', 'provider', 'signInLabel'].map((n) => [n, stmt(n)]);
  const missing = parts.filter(([, s]) => !s).map(([n]) => n);
  expect(!missing.length, `SettingsHubScreen has no ${missing.join(', ')} declaration`);
  const mod = { exports: {} };
  vm.runInNewContext(transpile(`function label(verification, account, isDemo, user) {
    ${parts.map(([, s]) => s.getText(sf)).join('\n')}
    return signInLabel;
  }
  module.exports = label;`), { module: mod });
  const label = mod.exports;
  const acct = (...providers) => ({ account: { identities: providers.map((p) => ({ provider: p, linked_at: '' })) } });
  const via = (v) => ({ verified_via: v });
  const sleeper = { user_id: '1', username: 'u', account_only: false };
  const acctOnly = { user_id: 'acct_x', username: '', account_only: true };
  const cases = [
    ['espn identity', [null, acct('espn'), false, acctOnly], 'ESPN'],
    ['mfl identity', [null, acct('mfl'), false, acctOnly], 'MFL'],
    ["verified_via 'espn', account not loaded", [via('espn'), undefined, false, acctOnly], 'ESPN'],
    ["verified_via 'mfl_login', account not loaded", [via('mfl_login'), undefined, false, acctOnly], 'MFL'],
    ["verified_via 'mfl_login', no identities", [via('mfl_login'), acct(), false, acctOnly], 'MFL'],
    // unchanged answers
    ['apple identity', [null, acct('apple'), false, acctOnly], 'Apple'],
    ['google identity', [null, acct('google'), false, acctOnly], 'Google'],
    ["verified_via 'apple'", [via('apple'), undefined, false, acctOnly], 'Apple'],
    ["verified_via 'google'", [via('google'), undefined, false, acctOnly], 'Google'],
    ['demo', [via('espn'), acct('espn'), true, acctOnly], 'Demo session'],
    ['Sleeper session', [via('sleeper'), undefined, false, sleeper], 'Sleeper'],
    ['account-only, nothing reported', [null, undefined, false, acctOnly], null],
    // release-lead QA P2: /api/mfl/auth-link also writes 'mfl_login' for a
    // Sleeper user who connects MFL by password. That's not an MFL sign-in.
    ["Sleeper user verified by MFL auth-link (verified_via 'mfl_login')", [via('mfl_login'), undefined, false, sleeper], 'Sleeper'],
    ["Sleeper user verified by MFL auth-link, account loaded, no identities", [via('mfl_login'), acct(), false, sleeper], 'Sleeper'],
  ];
  const bad = [];
  for (const [name, args, want] of cases) {
    const got = label(...args);
    if (got !== want) bad.push(`${name}: ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
  }
  expect(!bad.length, bad.join('; '));
});

console.log(failures === 0
  ? `\nAll sign-in identity label checks passed (${passed}).`
  : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
