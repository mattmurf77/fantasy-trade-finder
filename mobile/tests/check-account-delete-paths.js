#!/usr/bin/env node
// Account deletion paths (#354 M11 claim-only delete, LEG-S6 Apple revocation).
//
// WHY THIS EXISTS. "Delete account" now has two meanings. A verified session
// deletes the account. An UNVERIFIED ESPN/MFL entry session (`entry:espn:…` /
// `entry:mfl:…`) can't: its id is derivable from public league data, so the
// server's claim-only branch only signs it out and removes what this device
// added. If the app showed that user the verified path's words ("deleted
// immediately"), it would tell them something false about their data; if it
// sent them to SleeperConnect, they'd hit a dead end. Neither is visible to
// tsc, and D-056 left no simulator, so these are pinned here:
//
//   1. Entry users get the claim-only dialog with marketing-lead's G4 strings
//      (executed from claimOnlyCopy.ts), the typed DELETE gate, and no
//      SleeperConnect step-up anywhere on that path.
//   2. No "Account deleted", and no "deleted" as an outcome, is reachable from
//      the claim-only path: its copy module, dialog, handler, export row and
//      the Delete row's claim branch.
//   3. deleteAccount() (lifted and EXECUTED) always sends X-Device-Id, sends
//      {confirm:"delete"} when asked and apple_authorization_code when it has
//      one, and no body otherwise; the claim path asks for the confirm.
//   4. LEG-S6: the verified delete (lifted and EXECUTED with a stub Apple
//      module) sends a fresh Apple code when it gets one, and still deletes
//      when the Apple prompt is cancelled, fails or is unavailable.
//   5. SignIn consumes the one-shot notice at mount and renders it; the notice
//      module is set-once/consume-once (executed); the claim path sets the G4
//      notice before it signs out.
//   6. The entry mint (lifted and EXECUTED) sends X-Device-Id, so the server
//      can record which install a claim belongs to.
//
// HONEST LABEL (G-035). 1, 2 and 5 pin wiring and copy shape; 3, 4 and the
// notice module run the real code against stubs. The TestFlight checklist in
// docs/plans/launch-support-policy/scope-m11-minimal.md is the runtime proof.
// Every pin was watched failing on a mutated copy first (G-035/G-050).
//
// FTF_MOBILE_TEST_ROOT can point at a copy of mobile/ (sabotage runs).
// Run: node tests/check-account-delete-paths.js   (or: npm run test:account-delete-paths)

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
  copy:    'src/screens/settings/claimOnlyCopy.ts',
  dialog:  'src/screens/settings/ClaimDeleteDialog.tsx',
  section: 'src/screens/settings/sections/AccountDataSection.tsx',
  auth:    'src/api/auth.ts',
  notice:  'src/state/signInNotice.ts',
  signin:  'src/screens/SignInScreen.tsx',
  entry:   'src/api/platformEntry.ts',
};
const SUPPORT_EMAIL = 'fleecedapp@gmail.com';
// marketing-lead-copy.md §6 addendum 3 (folds in legal R27.1 / R27.2), verbatim.
const G4 = {
  G4_DELETE_TITLE: 'Sign out and remove this device?',
  G4_CONFIRM_PROMPT: 'Type DELETE to confirm.',
  G4_CONFIRM_WORD: 'DELETE',
  G4_CONFIRM_PRIMARY: 'Sign out and remove',
  G4_CONFIRM_CANCEL: 'Cancel',
  G4_EXPORT_UNAVAILABLE: "Download my data isn't available for this sign-in.",
  G4_EXPORT_WHY: "A copy is available in the app only for an account confirmed as yours. It's never sent by email. "
    + `For questions about your data, email ${SUPPORT_EMAIL}.`,
  G4_AFTER_NOTICE: "Signed out. This device's sign-in and usage history are removed.",
  G4_DELETE_ERROR: `Sign out and remove didn't go through. Try again in a minute, or email ${SUPPORT_EMAIL}.`,
};
const g4Body = (p) => `This ${p} league hasn't been confirmed as yours. `
  + "Deleting signs you out and removes this device's sign-in and usage history. "
  + "Rankings, trades and league data stay, as they may be the team owner's. "
  + `Questions: ${SUPPORT_EMAIL}.`;
const DELETED_OUTCOME = /\bdeleted\b|account\s+deleted|permanently\s+delet/i;

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
const parsed = {};
function parse(rel) {
  if (!parsed[rel]) {
    parsed[rel] = ts.createSourceFile(rel, read(rel), ts.ScriptTarget.Latest, true,
      rel.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  }
  return parsed[rel];
}
function findAll(root, pred) {
  const out = [];
  const visit = (n) => { if (pred(n)) out.push(n); ts.forEachChild(n, visit); };
  visit(root);
  return out;
}
const isStr = (n) => !!n && (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n));
const fnDecl = (sf, name) => findAll(sf, (n) => ts.isFunctionDeclaration(n) && n.name && n.name.text === name)[0];
const varDecl = (sf, name) => findAll(sf, (n) => ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === name)[0];
const jsxOpen = (n) => ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n);
const attr = (el, name) => el.attributes.properties.find((a) => ts.isJsxAttribute(a) && a.name.getText() === name);
const attrStr = (el, name) => {
  const a = attr(el, name);
  if (!a || !a.initializer) return null;
  if (isStr(a.initializer)) return a.initializer.text;
  if (ts.isJsxExpression(a.initializer) && isStr(a.initializer.expression)) return a.initializer.expression.text;
  return null;
};
// Every user-visible literal in a subtree (comments are trivia, never nodes).
function texts(root) {
  return findAll(root, (n) => isStr(n) || ts.isJsxText(n) || ts.isTemplateExpression(n))
    .map((n) => (ts.isTemplateExpression(n)
      ? [n.head.text, ...n.templateSpans.map((s) => s.literal.text)].join(' ')
      : n.text))
    .filter((t) => t && t.trim());
}
function transpile(code) {
  return ts.transpileModule(code, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React },
  }).outputText;
}
function runModule(rel, requireMap) {
  const mod = { exports: {} };
  vm.runInNewContext(transpile(read(rel)), {
    module: mod, exports: mod.exports,
    require: (n) => { if (!(n in requireMap)) throw new Error(`unexpected import ${n} in ${rel}`); return requireMap[n]; },
  }, { filename: rel });
  return mod.exports;
}

(async () => {
  const copy = runModule(F.copy, { '../../utils/supportContact': { SUPPORT_EMAIL } });
  const section = parse(F.section);
  const dialog = parse(F.dialog);
  const performClaimDelete = fnDecl(section, 'performClaimDelete');
  const claimExportRow = varDecl(section, 'claimExportRow');

  // ── 1. Entry users get the claim-only dialog ─────────────────────────────
  await check('1a. claimOnlyCopy holds the G4 strings verbatim; claimPlatform maps entry ids', () => {
    for (const [k, v] of Object.entries(G4)) expect(copy[k] === v, `${k} is ${JSON.stringify(copy[k])}, want ${JSON.stringify(v)}`);
    for (const p of ['ESPN', 'MFL']) expect(copy.g4DeleteBody(p) === g4Body(p), `g4DeleteBody('${p}') drifted: ${JSON.stringify(copy.g4DeleteBody(p))}`);
    const cases = [['entry:espn:{ABC}', 'ESPN'], ['entry:espn:123.t4', 'ESPN'], ['entry:mfl:61408.f0003', 'MFL'],
      ['313560442465169408', null], ['acct_deadbeef', null], ['demo_user_1', null], [null, null], ['', null]];
    for (const [id, want] of cases) expect(copy.claimPlatform(id) === want, `claimPlatform(${JSON.stringify(id)}) = ${copy.claimPlatform(id)}, want ${want}`);
  });

  await check('1b. AccountDataSection takes the claim path for an UNVERIFIED entry session', () => {
    const decl = varDecl(section, 'claimOnly');
    expect(decl && decl.initializer, 'no `claimOnly` declaration');
    const init = decl.initializer.getText(section);
    expect(/\bplatform\b/.test(init) && /session_verified\s*!==\s*true/.test(init),
      `claimOnly = ${init} — want the entry platform AND an unverified session`);
    const p = varDecl(section, 'platform');
    expect(p && /claimPlatform\(\s*user\?\.user_id\s*\)/.test(p.initializer.getText(section)),
      'platform is not claimPlatform(user?.user_id)');
    const rows = findAll(section, (n) => jsxOpen(n) && attrStr(n, 'accessibilityLabel') === 'Delete account');
    expect(rows.length === 1, `found ${rows.length} "Delete account" rows`);
    const onPress = attr(rows[0], 'onPress');
    const cond = onPress && ts.isJsxExpression(onPress.initializer) ? onPress.initializer.expression : null;
    expect(cond && ts.isConditionalExpression(cond) && cond.condition.getText(section) === 'claimOnly'
      && /setClaimDialogOpen\(\s*true\s*\)/.test(cond.whenTrue.getText(section))
      && cond.whenFalse.getText(section) === 'confirmDeleteAccount',
      'the Delete row does not open the claim dialog when claimOnly (else the verified confirm)');
    const mounts = findAll(section, (n) => jsxOpen(n) && n.tagName.getText(section) === 'ClaimDeleteDialog');
    expect(mounts.length === 1 && /performClaimDelete/.test(attr(mounts[0], 'onConfirm').getText(section)),
      'ClaimDeleteDialog is not mounted with onConfirm → performClaimDelete');
    const exportSwitch = findAll(section, (n) => ts.isConditionalExpression(n)
      && n.condition.getText(section) === 'claimOnly' && n.whenTrue.getText(section) === 'claimExportRow');
    expect(exportSwitch.length === 1, 'the export row does not switch to claimExportRow when claimOnly');
  });

  await check('1c. the dialog renders the G4 strings and gates the button on an exact DELETE', () => {
    const src = read(F.dialog);
    for (const id of ['G4_DELETE_TITLE', 'G4_CONFIRM_PROMPT', 'G4_CONFIRM_WORD', 'G4_CONFIRM_PRIMARY', 'G4_CONFIRM_CANCEL', 'g4DeleteBody']) {
      expect(findAll(dialog, (n) => ts.isIdentifier(n) && n.text === id
        && !(n.parent && ts.isImportSpecifier(n.parent))).length > 0, `ClaimDeleteDialog never uses ${id}`);
    }
    const input = findAll(dialog, (n) => jsxOpen(n) && n.tagName.getText(dialog) === 'TextInput')[0];
    expect(input, 'no TextInput');
    expect(attr(input, 'placeholder').getText(dialog).includes('G4_CONFIRM_WORD'), 'the field placeholder is not G4_CONFIRM_WORD');
    expect(attr(input, 'accessibilityLabel').getText(dialog).includes('G4_CONFIRM_PROMPT'), 'the field label is not G4_CONFIRM_PROMPT');
    const confirm = findAll(dialog, (n) => jsxOpen(n) && attrStr(n, 'testID') === 'settings.claim-delete.confirm')[0];
    expect(confirm && attr(confirm, 'label').getText(dialog).includes('G4_CONFIRM_PRIMARY'), 'the confirm button label is not G4_CONFIRM_PRIMARY');
    expect(/^\{!\s*matches\s*\}$/.test(attr(confirm, 'disabled').initializer.getText(dialog)), 'the confirm button is not disabled={!matches}');
    const matches = varDecl(dialog, 'matches');
    expect(matches && /===\s*G4_CONFIRM_WORD/.test(matches.initializer.getText(dialog)), 'matches is not an exact compare to G4_CONFIRM_WORD');
    expect(!/SleeperConnect/.test(src), 'the dialog mentions SleeperConnect');
  });

  await check('1d. no SleeperConnect step-up on the claim path', () => {
    expect(performClaimDelete, 'no performClaimDelete');
    for (const [label, node] of [['performClaimDelete', performClaimDelete], ['claimExportRow', claimExportRow]]) {
      expect(node, `no ${label}`);
      const t = node.getText(section);
      expect(!/SleeperConnect|promptVerifyStepUp/.test(t), `${label} routes to the SleeperConnect step-up`);
    }
  });

  // ── 2. No "deleted" outcome on the claim path ────────────────────────────
  await check('2. no "Account deleted" / "deleted" outcome text on the claim-only path', () => {
    const bad = [];
    const scan = (label, list) => list.forEach((t) => { if (DELETED_OUTCOME.test(t)) bad.push(`${label}: ${JSON.stringify(t.slice(0, 80))}`); });
    scan('claimOnlyCopy (runtime)', [...Object.values(copy).filter((v) => typeof v === 'string'), copy.g4DeleteBody('ESPN')]);
    scan('claimOnlyCopy', texts(parse(F.copy)));
    scan('ClaimDeleteDialog', texts(dialog));
    scan('performClaimDelete', texts(performClaimDelete));
    scan('claimExportRow', texts(claimExportRow));
    // The Delete row's claim branch: no permanent-deletion hint or subtitle.
    const row = findAll(section, (n) => jsxOpen(n) && attrStr(n, 'accessibilityLabel') === 'Delete account')[0];
    const hint = attr(row, 'accessibilityHint');
    const h = hint && ts.isJsxExpression(hint.initializer) ? hint.initializer.expression : null;
    if (!(h && ts.isConditionalExpression(h) && h.condition.getText(section) === 'claimOnly'
          && h.whenTrue.getText(section) === 'undefined')) bad.push('Delete row: accessibilityHint is not `claimOnly ? undefined : …`');
    const subs = findAll(row.parent, (n) => ts.isConditionalExpression(n) && n.condition.getText(section) === 'claimOnly'
      && n.whenTrue.getText(section) === 'null' && /Permanently delete/.test(n.whenFalse.getText(section)));
    if (subs.length !== 1) bad.push('Delete row: the permanent-deletion subtitle is not hidden when claimOnly');
    // Failures show g4.delete.error, never the server's message; the error
    // line says nothing about data (no deleted, no removed: marketing §6 (e)).
    const notices = findAll(performClaimDelete, (n) => ts.isCallExpression(n) && n.expression.getText(section) === 'onNotice');
    if (!notices.length || notices.some((c) => c.arguments[0].getText(section) !== 'G4_DELETE_ERROR')) {
      bad.push('performClaimDelete: onNotice is not called with G4_DELETE_ERROR only');
    }
    if (/\b(deleted|removed)\b/i.test(String(copy.G4_DELETE_ERROR))) {
      bad.push(`G4_DELETE_ERROR claims an outcome: ${JSON.stringify(copy.G4_DELETE_ERROR)}`);
    }
    expect(!bad.length, bad.join('; '));
  });

  // ── 3. deleteAccount() sends the right request (executed) ────────────────
  await check('3. deleteAccount sends X-Device-Id, the confirm and the Apple code when given', async () => {
    const auth = parse(F.auth);
    const fn = fnDecl(auth, 'deleteAccount');
    expect(fn, 'no deleteAccount in api/auth.ts');
    const calls = [];
    const mod = { exports: {} };
    vm.runInNewContext(transpile(`${fn.getText(auth)}\nmodule.exports = { deleteAccount };`), {
      module: mod, exports: mod.exports,
      apiRequest: async (p, opts) => { calls.push({ p, opts }); return { ok: true, deleted: 'session_only' }; },
      getDeviceId: async () => 'dev_guard',
    });
    const { deleteAccount } = mod.exports;
    await deleteAccount({ confirm: true });
    await deleteAccount({ appleAuthorizationCode: 'apple-code-1' });
    await deleteAccount();
    const [claim, apple, plain] = calls;
    for (const [label, c] of [['claim', claim], ['apple', apple], ['plain', plain]]) {
      expect(c && c.p === '/api/account' && c.opts.method === 'DELETE', `${label}: not DELETE /api/account`);
      expect(c.opts.headers && c.opts.headers['X-Device-Id'] === 'dev_guard', `${label}: no X-Device-Id header`);
    }
    expect(claim.opts.body && claim.opts.body.confirm === 'delete', `claim body is ${JSON.stringify(claim.opts.body)}`);
    expect(apple.opts.body && apple.opts.body.apple_authorization_code === 'apple-code-1' && !('confirm' in apple.opts.body),
      `apple body is ${JSON.stringify(apple.opts.body)}`);
    expect(plain.opts.body === undefined, `a plain call sends a body: ${JSON.stringify(plain.opts.body)}`);
    const sent = findAll(performClaimDelete, (n) => ts.isCallExpression(n) && n.expression.getText(section) === 'deleteAccount');
    expect(sent.length === 1 && /confirm:\s*true/.test(sent[0].getText(section)), 'the claim path does not call deleteAccount({ confirm: true })');
  });

  // ── 4. Apple cancel never blocks the DELETE (executed) ───────────────────
  await check('4. LEG-S6: a fresh Apple code goes up when available; cancel/failure still deletes', async () => {
    const apple = fnDecl(section, 'freshAppleAuthorizationCode');
    const perform = fnDecl(section, 'performDeleteAccount');
    expect(apple && perform, 'freshAppleAuthorizationCode / performDeleteAccount not found');
    const harness = transpile(`function make(env) {
      let { appleLinked, Platform, AppleAuthentication, deleteAccount, signOut, onAccountDeleted,
            setDeleting, onNotice, ApiError, dataExportEnabled, promptVerifyStepUp } = env;
      let deleting = false;
      ${apple.getText(section)}
      ${perform.getText(section)}
      return performDeleteAccount;
    }
    module.exports = make;`);
    const run = async ({ linked = true, available = true, signIn }) => {
      const log = { deletes: [], appleCalls: 0, signedOut: 0, landed: 0, notices: [] };
      const mod = { exports: {} };
      vm.runInNewContext(harness, { module: mod });
      const performDeleteAccount = mod.exports({
        appleLinked: linked,
        Platform: { OS: 'ios' },
        AppleAuthentication: {
          isAvailableAsync: async () => { if (available instanceof Error) throw available; return available; },
          signInAsync: async () => { log.appleCalls += 1; return signIn(); },
        },
        deleteAccount: async (opts) => { log.deletes.push(opts || {}); return { ok: true, deleted: {} }; },
        signOut: async () => { log.signedOut += 1; },
        onAccountDeleted: () => { log.landed += 1; },
        setDeleting: () => {}, onNotice: (m) => log.notices.push(m),
        ApiError: class extends Error {}, dataExportEnabled: true, promptVerifyStepUp: () => {},
      });
      await performDeleteAccount();
      return log;
    };
    const ok = await run({ signIn: async () => ({ authorizationCode: 'fresh-code' }) });
    expect(ok.deletes.length === 1 && ok.deletes[0].appleAuthorizationCode === 'fresh-code', `success: ${JSON.stringify(ok.deletes)}`);
    const cancel = Object.assign(new Error('The user canceled the authorization attempt'), { code: 'ERR_REQUEST_CANCELED' });
    for (const [label, opts] of [
      ['cancelled', { signIn: async () => { throw cancel; } }],
      ['failed', { signIn: async () => { throw new Error('apple down'); } }],
      ['unavailable', { available: false, signIn: async () => ({ authorizationCode: 'never' }) }],
      ['availability check throws', { available: new Error('no'), signIn: async () => ({ authorizationCode: 'never' }) }],
      ['not Apple-linked', { linked: false, signIn: async () => ({ authorizationCode: 'never' }) }],
    ]) {
      const log = await run(opts);
      expect(log.deletes.length === 1, `${label}: the DELETE was not sent (${log.deletes.length})`);
      expect(!log.deletes[0].appleAuthorizationCode, `${label}: sent code ${log.deletes[0].appleAuthorizationCode}`);
      expect(log.signedOut === 1 && log.landed === 1, `${label}: did not sign out and land on SignIn`);
    }
    const notLinked = await run({ linked: false, signIn: async () => ({ authorizationCode: 'x' }) });
    expect(notLinked.appleCalls === 0, 'a non-Apple account was shown the Apple prompt');
  });

  // ── 5. SignIn consumes the one-shot notice ───────────────────────────────
  await check('5. the notice is set before sign-out, consumed once at SignIn mount, and rendered', () => {
    const bus = runModule(F.notice, {});
    bus.setSignInNotice('x');
    expect(bus.consumeSignInNotice() === 'x' && bus.consumeSignInNotice() === null, 'signInNotice is not consume-once');
    const signin = parse(F.signin);
    const imp = signin.statements.some((s) => ts.isImportDeclaration(s) && isStr(s.moduleSpecifier)
      && s.moduleSpecifier.text === '../state/signInNotice' && /consumeSignInNotice/.test(s.getText(signin)));
    expect(imp, 'SignInScreen does not import consumeSignInNotice from ../state/signInNotice');
    const init = findAll(signin, (n) => ts.isCallExpression(n) && n.expression.getText(signin) === 'useState'
      && n.arguments[0] && ts.isArrowFunction(n.arguments[0]) && /consumeSignInNotice\(\)/.test(n.arguments[0].getText(signin)));
    expect(init.length === 1, 'SignInScreen does not consume the notice in a useState initializer (once, at mount)');
    const stateName = init[0].parent && ts.isVariableDeclaration(init[0].parent) && ts.isArrayBindingPattern(init[0].parent.name)
      ? init[0].parent.name.elements[0].getText(signin) : null;
    const slot = findAll(signin, (n) => jsxOpen(n) && attrStr(n, 'testID') === 'signin.notice')[0];
    expect(slot && stateName && slot.parent.getText(signin).includes(`{${stateName}}`), 'no signin.notice element rendering the consumed notice');
    const body = performClaimDelete.getText(section);
    const setAt = body.indexOf('setSignInNotice(G4_AFTER_NOTICE)');
    const outAt = body.indexOf('signOut()');
    expect(setAt >= 0 && outAt > setAt, 'performClaimDelete does not set the G4 notice before signOut()');
  });

  // ── 6. The entry mint sends the device id (executed) ────────────────────
  // The server records it on the new entry session; the claim-only delete
  // then removes THAT install's rows. The shared client doesn't send
  // X-Device-Id by default, so the mint must.
  await check('6. the /api/entry/platform mint sends X-Device-Id from getDeviceId()', async () => {
    const entry = parse(F.entry);
    const fn = fnDecl(entry, 'entryPlatformMint');
    expect(fn, 'no entryPlatformMint in api/platformEntry.ts');
    const posts = [];
    const mod = { exports: {} };
    vm.runInNewContext(transpile(`${fn.getText(entry)}\nmodule.exports = { entryPlatformMint };`), {
      module: mod, exports: mod.exports,
      api: { post: async (p, body, opts) => { posts.push({ p, body, opts }); return { session_token: 'tok' }; } },
      getDeviceId: async () => 'dev_guard',
      setSessionToken: async () => {}, track: () => {}, entryErrorCode: () => 'x',
    });
    await mod.exports.entryPlatformMint({ platform: 'mfl', leagueInput: '61408', year: 2026, teamId: '0003' });
    await mod.exports.entryPlatformMint({ platform: 'espn', espnLeagueId: '987', teamId: 1 });
    expect(posts.length === 2 && posts.every((c) => c.p === '/api/entry/platform'), `mint posts: ${JSON.stringify(posts.map((c) => c.p))}`);
    for (const c of posts) {
      expect(c.opts && c.opts.headers && c.opts.headers['X-Device-Id'] === 'dev_guard',
        `${c.body.platform} mint sends headers ${JSON.stringify(c.opts && c.opts.headers)}`);
    }
  });

  console.log(failures === 0
    ? `\nAll account-delete-path checks passed (${passed}).`
    : `\n${failures} check(s) failed.`);
  process.exit(failures === 0 ? 0 : 1);
})();
