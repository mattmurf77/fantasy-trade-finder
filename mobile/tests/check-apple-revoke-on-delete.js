#!/usr/bin/env node
// LEG-S6 (#354): a fresh Apple code on the verified "Delete account".
//
// WHY THIS EXISTS. App Review 5.1.1(v) wants an account created with Sign in
// with Apple to have its Apple grant revoked when the account is deleted. The
// server can only do that with a FRESH `authorizationCode` (it never keeps an
// Apple token; accounts.revoke_apple_tokens), so the app asks an Apple-linked
// account for a new Apple credential right before the verified DELETE and
// sends the code up. Every part of that is invisible to tsc, and D-056 left no
// simulator, so it is pinned here:
//
//   1. deleteAccount() (lifted and EXECUTED) sends the code as
//      `apple_authorization_code` and nothing else; with no code it is
//      exactly the old body-less DELETE.
//   2. The Apple prompt is requested only for an Apple-linked account (the
//      ['account'] query's identities) on iOS, when Apple says it's available
//      (freshAppleAuthorizationCode, lifted and EXECUTED with a stub Apple
//      module).
//   3. Cancelling, failing or an unavailable Apple prompt returns null, and
//      the DELETE still goes out, followed by sign-out and the SignIn landing
//      (performDeleteAccount, EXECUTED). A fresh code goes up when it exists.
//   4. The path never calls setSessionToken (nor appleSignIn): a re-auth that
//      minted a session could switch the person into another account mid-
//      delete. Pinned statically AND by spies in the executed harness.
//   5. The verified delete is the only caller: freshAppleAuthorizationCode is
//      called once, from performDeleteAccount, which runs only from the
//      "Delete everything" confirm; nothing else in mobile/src sends an Apple
//      code to deleteAccount or writes `apple_authorization_code`.
//   6. No console.* in freshAppleAuthorizationCode, performDeleteAccount or
//      deleteAccount: Sentry keeps console calls as breadcrumbs, so the code
//      would leave the device (release-lead QA on #446).
//
// HONEST LABEL (G-035). 1-3 run the real function text against stubs; 4-6
// pin wiring. The runtime proof is the TestFlight checklist in the LEG-S6 PR
// (an Apple account deletes, the Apple prompt appears, Fleeced leaves iOS
// Settings › Apple ID › Sign in with Apple; cancelling still deletes). Every
// pin was watched failing on a mutated copy first (G-035/G-050).
//
// FTF_MOBILE_TEST_ROOT can point at a copy of mobile/ (sabotage runs).
// Run: node tests/check-apple-revoke-on-delete.js   (or: npm run test:apple-revoke-on-delete)

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
  section: 'src/screens/settings/sections/AccountDataSection.tsx',
  auth:    'src/api/auth.ts',
};

let failures = 0;
let passed = 0;
async function check(name, fn) {
  try {
    await fn();
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
const fnDecl = (sf, name) => findAll(sf, (n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === name)[0];
const varDecl = (sf, name) => findAll(sf, (n) => ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === name)[0];
const calls = (root, name) => findAll(root, (n) => ts.isCallExpression(n) && n.expression.getText() === name);
const enclosingFn = (n) => {
  for (let p = n.parent; p; p = p.parent) if (ts.isFunctionDeclaration(p)) return p.name && p.name.text;
  return null;
};
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

(async () => {
  const section = parse(F.section);
  const auth = parse(F.auth);
  const apple = fnDecl(section, 'freshAppleAuthorizationCode');
  const perform = fnDecl(section, 'performDeleteAccount');

  // ── 1. deleteAccount() puts the code on the wire (executed) ─────────────
  await check('1. deleteAccount sends the code as apple_authorization_code; no code = the old body-less DELETE', async () => {
    const fn = fnDecl(auth, 'deleteAccount');
    expect(fn, 'no deleteAccount in api/auth.ts');
    const sent = [];
    const mod = { exports: {} };
    vm.runInNewContext(transpile(`${fn.getText(auth)}\nmodule.exports = { deleteAccount };`), {
      module: mod, exports: mod.exports,
      apiRequest: async (p, opts) => { sent.push({ p, opts }); return { ok: true, deleted: {} }; },
    });
    const { deleteAccount } = mod.exports;
    await deleteAccount({ appleAuthorizationCode: 'apple-code-1' });
    for (const none of [undefined, {}, { appleAuthorizationCode: null }, { appleAuthorizationCode: '' }]) {
      await (none === undefined ? deleteAccount() : deleteAccount(none));
    }
    const [withCode, ...without] = sent;
    expect(withCode && withCode.p === '/api/account' && withCode.opts.method === 'DELETE', 'with a code: not DELETE /api/account');
    expect(JSON.stringify(withCode.opts.body) === JSON.stringify({ apple_authorization_code: 'apple-code-1' }),
      `with a code the body is ${JSON.stringify(withCode.opts.body)}, want {"apple_authorization_code":"apple-code-1"}`);
    expect(without.length === 4, `expected 4 code-less calls, got ${without.length}`);
    without.forEach((c, i) => expect(c.p === '/api/account' && JSON.stringify(c.opts) === '{"method":"DELETE"}',
      `code-less call ${i + 1} sent ${JSON.stringify(c.opts)}, want exactly {"method":"DELETE"}`));
  });

  // Executed harness: the two functions' real text, closed over stubs.
  const harness = transpile(`function make(env) {
    let { appleLinked, Platform, AppleAuthentication, deleteAccount, signOut, onAccountDeleted,
          setDeleting, onNotice, ApiError, dataExportEnabled, promptVerifyStepUp,
          setSessionToken, appleSignIn } = env;
    let deleting = false;
    ${apple ? apple.getText(section) : ''}
    ${perform ? perform.getText(section) : ''}
    return { freshAppleAuthorizationCode, performDeleteAccount };
  }
  module.exports = make;`);
  const run = async ({ linked = true, os = 'ios', available = true, signIn }) => {
    const log = { deletes: [], available: 0, appleCalls: 0, scopes: [], signedOut: 0, landed: 0, notices: [], tokens: 0, appleSignIns: 0 };
    const mod = { exports: {} };
    vm.runInNewContext(harness, { module: mod });
    const fns = mod.exports({
      appleLinked: linked,
      Platform: { OS: os },
      AppleAuthentication: {
        isAvailableAsync: async () => { log.available += 1; if (available instanceof Error) throw available; return available; },
        signInAsync: async (o) => { log.appleCalls += 1; log.scopes.push(o && o.requestedScopes); return signIn(); },
      },
      deleteAccount: async (opts) => { log.deletes.push(opts === undefined ? {} : opts); return { ok: true, deleted: {} }; },
      signOut: async () => { log.signedOut += 1; },
      onAccountDeleted: () => { log.landed += 1; },
      setDeleting: () => {}, onNotice: (m) => log.notices.push(m),
      ApiError: class extends Error {}, dataExportEnabled: true, promptVerifyStepUp: () => {},
      setSessionToken: async () => { log.tokens += 1; },
      appleSignIn: async () => { log.appleSignIns += 1; return {}; },
    });
    await fns.performDeleteAccount();
    return log;
  };
  const code = (c) => async () => ({ authorizationCode: c });

  // ── 2. Only Apple-linked, only iOS (executed + the appleLinked wiring) ───
  await check('2. the Apple prompt is requested only for an Apple-linked account on iOS', async () => {
    expect(apple && perform, 'freshAppleAuthorizationCode / performDeleteAccount not found in AccountDataSection');
    const linked = varDecl(section, 'appleLinked');
    const init = linked && linked.initializer.getText(section).replace(/\s+/g, ' ');
    expect(init && /accountQuery\.data\?\.account\?\.identities/.test(init) && /\.some\(\s*\(?i\)?\s*=>\s*i\.provider\s*===\s*'apple'\s*\)/.test(init),
      `appleLinked = ${init} — want the ['account'] query's identities .some(provider === 'apple')`);
    const q = varDecl(section, 'accountQuery');
    const qt = q && q.initializer.getText(section).replace(/\s+/g, ' ');
    expect(qt && /queryKey:\s*\['account'\]/.test(qt) && /queryFn:\s*getAccount\b/.test(qt)
      && /enabled:\s*accountsEnabled\s*&&\s*!isDemo\b/.test(qt),
      `accountQuery is not useQuery({ queryKey: ['account'], queryFn: getAccount, enabled: accountsEnabled && !isDemo })`);
    const flag = varDecl(section, 'accountsEnabled');
    expect(flag && /useFlag\(\s*'auth\.accounts'\s*\)/.test(flag.initializer.getText(section)), "accountsEnabled is not useFlag('auth.accounts')");

    const ok = await run({ signIn: code('fresh-code') });
    expect(ok.appleCalls === 1 && JSON.stringify(ok.scopes[0]) === '[]', `linked iOS: signInAsync calls ${ok.appleCalls}, scopes ${JSON.stringify(ok.scopes[0])}; want 1 with requestedScopes []`);
    for (const [label, opts] of [['not Apple-linked', { linked: false }], ['Android', { os: 'android' }]]) {
      const log = await run({ ...opts, signIn: code('never') });
      expect(log.appleCalls === 0 && log.available === 0, `${label}: the Apple prompt was requested (isAvailableAsync ${log.available}, signInAsync ${log.appleCalls})`);
    }
    const off = await run({ available: false, signIn: code('never') });
    expect(off.available === 1 && off.appleCalls === 0, 'Apple unavailable: signInAsync was still called');
  });

  // ── 3. Cancel / failure never blocks the DELETE (executed) ───────────────
  await check('3. cancel, failure or no Apple → null and the DELETE still goes out; a fresh code goes up', async () => {
    const ok = await run({ signIn: code('fresh-code') });
    expect(ok.deletes.length === 1 && ok.deletes[0].appleAuthorizationCode === 'fresh-code',
      `success: deleteAccount got ${JSON.stringify(ok.deletes)}, want one call with appleAuthorizationCode "fresh-code"`);
    expect(ok.signedOut === 1 && ok.landed === 1, 'success: did not sign out and land on SignIn');
    const cancel = Object.assign(new Error('The user canceled the authorization attempt'), { code: 'ERR_REQUEST_CANCELED' });
    for (const [label, opts] of [
      ['cancelled', { signIn: async () => { throw cancel; } }],
      ['failed', { signIn: async () => { throw new Error('apple down'); } }],
      ['no code returned', { signIn: async () => ({ authorizationCode: null }) }],
      ['unavailable', { available: false, signIn: code('never') }],
      ['availability check throws', { available: new Error('no'), signIn: code('never') }],
      ['not Apple-linked', { linked: false, signIn: code('never') }],
      ['Android', { os: 'android', signIn: code('never') }],
    ]) {
      const log = await run(opts);
      expect(log.deletes.length === 1, `${label}: the DELETE was sent ${log.deletes.length}×, want 1`);
      expect(!log.deletes[0].appleAuthorizationCode, `${label}: sent code ${log.deletes[0].appleAuthorizationCode}`);
      expect(log.signedOut === 1 && log.landed === 1 && log.notices.length === 0,
        `${label}: did not sign out and land on SignIn cleanly (signOut ${log.signedOut}, landed ${log.landed}, notices ${JSON.stringify(log.notices)})`);
    }
  });

  // ── 4. Never setSessionToken on this path ────────────────────────────────
  await check('4. the Apple re-auth never calls setSessionToken (or appleSignIn)', async () => {
    const bad = [];
    for (const [label, node] of [['freshAppleAuthorizationCode', apple], ['performDeleteAccount', perform]]) {
      if (!node) { bad.push(`no ${label}`); continue; }
      const ids = findAll(node, (n) => ts.isIdentifier(n) && /^(setSessionToken|appleSignIn|setSession)$/.test(n.text));
      if (ids.length) bad.push(`${label} references ${[...new Set(ids.map((n) => n.text))].join(', ')}`);
    }
    const imports = section.statements.filter((s) => ts.isImportDeclaration(s)).map((s) => s.getText(section)).join('\n');
    if (/\bsetSessionToken\b|\bappleSignIn\b/.test(imports)) bad.push('AccountDataSection imports setSessionToken / appleSignIn');
    for (const opts of [{ signIn: code('fresh-code') }, { signIn: async () => { throw new Error('x'); } }]) {
      const log = await run(opts);
      if (log.tokens || log.appleSignIns) bad.push(`executed: setSessionToken ${log.tokens}×, appleSignIn ${log.appleSignIns}×`);
    }
    expect(!bad.length, bad.join('; '));
  });

  // ── 5. The verified delete is the only caller ────────────────────────────
  await check('5. only the verified delete asks for and sends the Apple code', () => {
    const bad = [];
    const asks = calls(section, 'freshAppleAuthorizationCode');
    if (asks.length !== 1 || enclosingFn(asks[0]) !== 'performDeleteAccount') {
      bad.push(`freshAppleAuthorizationCode is called ${asks.length}× (${asks.map(enclosingFn).join(', ')}), want once from performDeleteAccount`);
    }
    const dels = calls(section, 'deleteAccount');
    if (dels.length !== 1 || enclosingFn(dels[0]) !== 'performDeleteAccount'
        || !/^\{\s*appleAuthorizationCode\s*\}$/.test((dels[0].arguments[0] || { getText: () => '' }).getText(section))) {
      bad.push('AccountDataSection does not call deleteAccount({ appleAuthorizationCode }) exactly once, from performDeleteAccount');
    }
    const runs = calls(section, 'performDeleteAccount');
    const confirm = fnDecl(section, 'confirmDeleteAccount');
    if (runs.length !== 1 || enclosingFn(runs[0]) !== 'confirmDeleteAccount'
        || !confirm || !/text:\s*'Delete everything'[\s\S]*?performDeleteAccount\(\)/.test(confirm.getText(section))) {
      bad.push(`performDeleteAccount runs from ${runs.map(enclosingFn).join(', ') || 'nowhere'}, want only the "Delete everything" confirm in confirmDeleteAccount`);
    }
    // Repo-wide: no other file sends an Apple code to deleteAccount or writes the wire key.
    for (const file of srcFiles(path.join(ROOT, 'src'))) {
      const rel = path.relative(ROOT, file).split(path.sep).join('/');
      const text = fs.readFileSync(file, 'utf8');
      if (rel !== F.auth && /apple_authorization_code/.test(text)) bad.push(`${rel} writes apple_authorization_code`);
      if (rel === F.section) continue;
      if (/freshAppleAuthorizationCode/.test(text)) bad.push(`${rel} mentions freshAppleAuthorizationCode`);
      const sf = parse(rel, text);
      for (const c of calls(sf, 'deleteAccount')) {
        if (c.arguments.length && /appleAuthorizationCode/.test(c.arguments[0].getText(sf))) bad.push(`${rel} sends an Apple code to deleteAccount`);
      }
    }
    expect(!bad.length, bad.join('; '));
  });

  // ── 6. The Apple code never reaches the console ─────────────────────────
  // Sentry records console calls as breadcrumbs, so a console.* anywhere the
  // fresh authorizationCode passes would ship it off the device (release-lead
  // QA on #446, b). Any reference to `console` inside the three functions.
  await check('6. no console.* in freshAppleAuthorizationCode, performDeleteAccount or deleteAccount', () => {
    const bad = [];
    for (const [label, sf, node] of [
      ['freshAppleAuthorizationCode', section, apple],
      ['performDeleteAccount', section, perform],
      ['deleteAccount', auth, fnDecl(auth, 'deleteAccount')],
    ]) {
      if (!node) { bad.push(`no ${label}`); continue; }
      const uses = findAll(node, (n) => ts.isIdentifier(n) && n.text === 'console');
      if (uses.length) bad.push(`${label} references console (${uses.map((n) => n.parent.getText(sf).slice(0, 40)).join(', ')})`);
    }
    expect(!bad.length, bad.join('; '));
  });

  console.log(failures === 0
    ? `\nAll Apple-revoke-on-delete checks passed (${passed}).`
    : `\n${failures} check(s) failed.`);
  process.exit(failures === 0 ? 0 : 1);
})();
