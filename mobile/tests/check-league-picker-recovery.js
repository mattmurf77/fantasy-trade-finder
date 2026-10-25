#!/usr/bin/env node
// League picker recovery (incident 2026-10-17, a username-only Sleeper user
// stuck at league selection).
//
// WHY THIS EXISTS. An unverified Sleeper session is memory-only on the server
// and expires. A 401 cleared the stored token, and nothing re-minted it. The
// next cold start landed on LeaguePicker with a user but no token. Every
// league tap then aborted inside the league lifecycle before any network call
// (no token), and pickLeague's catch swallowed that AbortError (and the
// identity-guard return) WITHOUT resetting `selectingId`. The row spinner
// never stopped, and every row plus the Verify and platform buttons stayed
// `disabled={!!selectingId}`. Relaunching repeated the loop. The fix has five
// legs, and each one is easy to undo by accident:
//
//   1. pickLeague releases the list on EVERY exit: success, every catch
//      branch, the abort return and the guard return.
//   2. The 401 session-expired handler routes Sleeper-keyed users to SignIn,
//      not just account-only ones. Demo and no-user still end quietly.
//   3. The picker's Verify button checks for a real token before opening
//      SleeperConnect (whose link call 401s without one).
//   4. A token-less cold start for a Sleeper-keyed user reroutes the picker to
//      SignIn, confirmed against the STORED token (`hasToken` lags a fresh
//      username sign-in, and trusting it would loop SignIn and the picker).
//   5. The stale "silently re-mint" claim is gone from useSession.ts.
//
// HONEST LABEL (G-035). Legs 1-4 are EXECUTED: the real pickLeague,
// sleeperKeyed, Verify onPress and cold-start effect are lifted out of the TSX
// with the TypeScript compiler API and run under node with stub bindings, and
// the real useSession.ts module is run with stub imports to capture its
// session-expired handler. What the stubs replace (React, navigation, the
// league lifecycle, SecureStore) is NOT exercised. Leg 5 is a text check.
//
// FTF_MOBILE_TEST_ROOT can point at a copy of mobile/ (sabotage runs).
// Run: node tests/check-league-picker-recovery.js

'use strict';

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

let ts;
try {
  ts = require('typescript');
} catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}

const ROOT = process.env.FTF_MOBILE_TEST_ROOT || path.resolve(__dirname, '..');
const PICKER = 'src/screens/LeaguePickerScreen.tsx';
const SESSION = 'src/state/useSession.ts';
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');

let failures = 0;
let passed = 0;
async function check(name, fn) {
  try {
    await fn();
    passed += 1;
    console.log(`PASS  ${name}`);
  } catch (error) {
    failures += 1;
    console.error(`FAIL  ${name}: ${error.message}`);
  }
}
function expect(cond, message) {
  if (!cond) throw new Error(message);
}
const flush = () => new Promise((resolve) => setImmediate(resolve));

function transpile(code) {
  return ts.transpileModule(code, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React },
  }).outputText;
}
function run(code, bindings, filename) {
  const module = { exports: {} };
  vm.runInNewContext(transpile(code), { module, exports: module.exports, ...bindings }, { filename });
  return module.exports;
}

const pickerSrc = read(PICKER);
const pickerAst = ts.createSourceFile(PICKER, pickerSrc, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
function walk(node, visit) {
  visit(node);
  ts.forEachChild(node, (child) => walk(child, visit));
}
function fnDecl(name) {
  let found = null;
  walk(pickerAst, (node) => {
    if (ts.isFunctionDeclaration(node) && node.name?.text === name) found = node;
  });
  expect(found, `${PICKER} declares function ${name}`);
  return found;
}
// The identity helper the lifted code calls. Optional so a pre-fix source
// fails on its behavior, not on a missing helper; a lifted body that still
// calls it without the declaration throws a ReferenceError and fails anyway.
function helperText() {
  try {
    return fnDecl('sleeperKeyed').getText(pickerAst);
  } catch {
    return '';
  }
}

// ── Shared fixtures ──────────────────────────────────────────────────────
const LEAGUE = { league_id: 'synthetic-league', name: 'Synthetic' };
const SLEEPER_USER = { user_id: 'synthetic-sleeper', username: 'tester', display_name: 'Tester', avatar_id: null };
const ACCOUNT_USER = { user_id: 'acct_synthetic', username: '', display_name: 'Tester', avatar_id: null, account_only: true };
const DEMO_USER = { user_id: 'demo_user_synthetic', username: 'demo', display_name: 'Demo', avatar_id: null };
const abortError = () => Object.assign(new Error('Aborted'), { name: 'AbortError' });
class ApiError extends Error {
  constructor(status, body, message) {
    super(message);
    this.status = status;
    this.body = body;
  }
}
const EXPIRED_COPY = 'Your session expired. Sign out, then sign in again to choose a league.';

// ── 1. pickLeague — every exit releases the list ─────────────────────────
function pickHarness(s) {
  const ui = { selecting: null, sets: [], error: null, picked: 0, replaced: [], navigated: [], verification: null };
  const store = { user: s.user, isDemo: !!s.isDemo, verification: null, setVerification: (v) => { ui.verification = v; } };
  const code = `${helperText()}\n${fnDecl('pickLeague').getText(pickerAst)}\nmodule.exports = pickLeague;`;
  const pickLeague = run(code, {
    user: s.user, selectingId: null, cached: [LEAGUE],
    // React semantics, including functional updates.
    setSelectingId: (v) => { ui.selecting = typeof v === 'function' ? v(ui.selecting) : v; ui.sets.push(ui.selecting); },
    setError: (v) => { ui.error = v; },
    advanceGuideIfActive: () => {}, track: () => {},
    currentSessionGuard: () => (s.identityChanged ? () => { throw abortError(); } : () => {}),
    beginLeagueContext: () => (s.fail ? Promise.reject(s.fail()) : Promise.resolve({ assertIdentity: () => {}, assertCurrent: () => {} })),
    completeLeagueContext: async () => {},
    setLeague: async () => {},
    onLeaguePicked: () => { ui.picked += 1; },
    ApiError,
    useSession: { getState: () => store },
    getSessionToken: async () => s.token ?? null,
    persistentSessions: s.flag !== false,
    navigation: { replace: (name) => ui.replaced.push(name), navigate: (name) => ui.navigated.push(name) },
  }, PICKER);
  return { ui, invoke: () => pickLeague(LEAGUE) };
}

const PICK_EXITS = [
  ['success', { user: SLEEPER_USER, token: 'tok' }, (ui) => ui.picked === 1 && ui.error === null],
  ['abort with a live token (superseded intent): reset only', { user: SLEEPER_USER, token: 'tok', fail: abortError },
    (ui) => ui.error === null && ui.replaced.length === 0],
  ['abort, no token, Sleeper-keyed: routes to SignIn', { user: SLEEPER_USER, fail: abortError },
    (ui) => ui.replaced.join() === 'SignIn' && ui.error === null],
  ['abort, no token, account-only: explains', { user: ACCOUNT_USER, fail: abortError },
    (ui) => ui.error === EXPIRED_COPY && ui.replaced.length === 0],
  ['abort, no token, demo: explains', { user: DEMO_USER, isDemo: true, fail: abortError },
    (ui) => ui.error === EXPIRED_COPY && ui.replaced.length === 0],
  ['abort, no token, Sleeper-keyed, flag off: explains', { user: SLEEPER_USER, flag: false, fail: abortError },
    (ui) => ui.error === EXPIRED_COPY && ui.replaced.length === 0],
  ['guard return (identity changed): reset only', { user: SLEEPER_USER, token: 'tok', identityChanged: true, fail: () => new Error('stale') },
    (ui) => ui.error === null && ui.replaced.length === 0],
  ['verification_required', { user: SLEEPER_USER, token: 'tok', fail: () => new ApiError(403, { error: 'verification_required' }, 'x') },
    (ui) => ui.error === 'Verify your Sleeper account, then choose your league again.' && ui.verification?.enforced === true],
  ['generic error', { user: SLEEPER_USER, token: 'tok', fail: () => new Error('boom') }, (ui) => ui.error === 'boom'],
];

function pickTryStatement() {
  let found = null;
  walk(fnDecl('pickLeague'), (node) => {
    if (!found && ts.isTryStatement(node) && node.catchClause) found = node;
  });
  expect(found, 'pickLeague has a try/catch');
  return found;
}

// ── 2. setOnSessionExpired — Sleeper-keyed users reach SignIn ────────────
function sessionHarness(s) {
  const navs = [];
  let handler = null;
  const create = (init) => {
    let value;
    const store = (selector) => selector(value);
    store.getState = () => value;
    store.setState = (patch) => { value = { ...value, ...(typeof patch === 'function' ? patch(value) : patch) }; };
    value = init(store.setState, store.getState);
    return store;
  };
  const stubs = {
    zustand: { create },
    '../api/client': {
      setOnSessionExpired: (fn) => { handler = fn; },
      setOnVerificationRequired: () => {},
      getSessionRevision: () => 0,
    },
    './leagueSession': {
      createLeagueSessionLifecycle: () => ({ invalidate() {}, currentGeneration: () => 0 }),
      LEAGUE_ATTEMPT_MS: 90_000,
    },
    './useFeatureFlags': { useFeatureFlags: { getState: () => ({ flags: { 'auth.persistent_sessions': s.flag !== false } }) } },
    '../navigation/RootNav': {
      navigationRef: {
        isReady: () => true,
        getCurrentRoute: () => ({ name: s.route || 'LeaguePicker' }),
        navigate: (name) => navs.push(name),
      },
    },
  };
  // Imports used only inside functions this guard never calls resolve to {}.
  const mod = run(read(SESSION), { require: (name) => stubs[name] || {}, console }, SESSION);
  expect(typeof handler === 'function', 'useSession.ts registers a session-expired handler');
  mod.useSession.setState({ user: s.user, isDemo: !!s.isDemo, hasToken: true });
  handler();
  return { navs, hint: mod.consumeAppleReauthHint(), hasToken: mod.useSession.getState().hasToken };
}

const EXPIRY_CASES = [
  ['Sleeper-keyed → SignIn', { user: SLEEPER_USER }, true],
  ['account-only → SignIn', { user: ACCOUNT_USER }, true],
  ['demo session → no reroute', { user: DEMO_USER, isDemo: true }, false],
  ['relaunched demo id → no reroute', { user: DEMO_USER }, false],
  ['no user → no reroute', { user: null }, false],
  ['Sleeper-keyed, flag off → no reroute', { user: SLEEPER_USER, flag: false }, false],
];

// ── 3 + 4. Verify onPress and the cold-start effect ─────────────────────
function verifyPress() {
  let found = null;
  walk(pickerAst, (node) => {
    if (!ts.isJsxSelfClosingElement(node) && !ts.isJsxOpeningElement(node)) return;
    const attrs = node.attributes.properties;
    const id = attrs.find((a) => ts.isJsxAttribute(a) && a.name.getText(pickerAst) === 'testID');
    if (id?.initializer?.getText(pickerAst) !== '"leagues.verify-sleeper"') return;
    const press = attrs.find((a) => ts.isJsxAttribute(a) && a.name.getText(pickerAst) === 'onPress');
    found = press?.initializer?.expression ?? null;
  });
  expect(found, 'leagues.verify-sleeper has an onPress handler');
  return found;
}
function coldStartEffects() {
  const effects = [];
  walk(pickerAst, (node) => {
    if (ts.isCallExpression(node) && node.expression.getText(pickerAst) === 'useEffect'
      && /replace\('SignIn'\)/.test(node.arguments[0]?.getText(pickerAst) || '')) effects.push(node.arguments[0]);
  });
  return effects;
}
async function runColdStart(s) {
  const nav = { replaced: [], tokenReads: 0 };
  const store = { user: s.user, isDemo: false, hasToken: !!s.hasToken };
  const [effect] = coldStartEffects();
  const callback = run(`${helperText()}\nmodule.exports = ${effect.getText(pickerAst)};`, {
    useSession: { getState: () => store },
    persistentSessions: s.flag !== false,
    getSessionToken: async () => { nav.tokenReads += 1; return s.token ?? null; },
    navigation: { replace: (name) => nav.replaced.push(name) },
  }, PICKER);
  callback();
  await flush();
  return nav;
}

async function main() {
  // 1 ─ executed
  for (const [label, scenario, outcome] of PICK_EXITS) {
    await check(`1 pickLeague exit releases the list — ${label}`, async () => {
      const { ui, invoke } = pickHarness(scenario);
      await invoke();
      expect(ui.sets[0] === LEAGUE.league_id, 'the tap never marked its row busy');
      expect(ui.selecting === null, `selectingId left as ${JSON.stringify(ui.selecting)} (frozen picker)`);
      expect(outcome(ui), `unexpected outcome ${JSON.stringify({ error: ui.error, replaced: ui.replaced, picked: ui.picked })}`);
    });
  }
  // 1 ─ structural: no catch path can return around the reset
  await check('1 pickLeague: a finally resets selectingId, or every catch return is preceded by one', () => {
    const tryStmt = pickTryStatement();
    if (tryStmt.finallyBlock && /setSelectingId\(/.test(tryStmt.finallyBlock.getText(pickerAst))) return;
    const block = tryStmt.catchClause.block;
    const resets = (n) => /setSelectingId\(/.test(n.getText(pickerAst));
    const covered = (ret) => {
      for (let n = ret; n && n !== block.parent; n = n.parent) {
        if (n.parent && ts.isBlock(n.parent)) {
          const siblings = n.parent.statements;
          if (siblings.slice(0, siblings.indexOf(n)).some(resets)) return true;
        }
      }
      return false;
    };
    const returns = [];
    walk(block, (n) => { if (ts.isReturnStatement(n)) returns.push(n); });
    const bare = returns.filter((r) => !covered(r));
    expect(bare.length === 0, `catch returns without a reset: ${bare.map((r) => r.parent.getText(pickerAst).slice(0, 60)).join(' | ')}`);
    const last = block.statements[block.statements.length - 1];
    expect(last && resets(last), 'the catch block does not end with a reset');
  });

  // 2 ─ executed
  for (const [label, scenario, reroutes] of EXPIRY_CASES) {
    await check(`2 session-expired handler — ${label}`, () => {
      const r = sessionHarness(scenario);
      expect(r.hasToken === false, 'hasToken still true after the 401 cleared the token');
      expect(r.navs.join() === (reroutes ? 'SignIn' : ''), `navigations ${JSON.stringify(r.navs)}`);
      expect(r.hint === reroutes, `re-auth hint ${r.hint}`);
    });
  }

  // 3 ─ executed + order
  await check('3 Verify checks for a live token before opening SleeperConnect', async () => {
    const press = verifyPress();
    const text = press.getText(pickerAst);
    const tokenAt = text.indexOf('getSessionToken(');
    expect(tokenAt >= 0 && tokenAt < text.indexOf("navigation.navigate('SleeperConnect')"),
      'getSessionToken() is not read before navigate(SleeperConnect)');
    for (const [token, want] of [[null, { replaced: 'SignIn', navigated: '' }], ['tok', { replaced: '', navigated: 'SleeperConnect' }]]) {
      const nav = { replaced: [], navigated: [] };
      const onPress = run(`module.exports = ${text};`, {
        setError: () => {},
        getSessionToken: async () => token,
        navigation: { replace: (n) => nav.replaced.push(n), navigate: (n) => nav.navigated.push(n) },
      }, PICKER);
      await onPress();
      expect(nav.replaced.join() === want.replaced && nav.navigated.join() === want.navigated,
        `token ${token}: ${JSON.stringify(nav)}`);
    }
  });

  // 4 ─ executed
  await check('4 picker has exactly one cold-start reroute to SignIn', () => {
    expect(coldStartEffects().length === 1, `found ${coldStartEffects().length} useEffect(s) calling replace('SignIn')`);
  });
  if (coldStartEffects().length === 1) {
    const COLD = [
      ['no stored token → SignIn', { user: SLEEPER_USER }, 'SignIn'],
      ['stored token despite hasToken=false (fresh sign-in) → stays', { user: SLEEPER_USER, token: 'tok' }, ''],
      ['hasToken → stays', { user: SLEEPER_USER, hasToken: true }, ''],
      ['account-only → stays', { user: ACCOUNT_USER }, ''],
      ['flag off → stays', { user: SLEEPER_USER, flag: false }, ''],
    ];
    for (const [label, scenario, want] of COLD) {
      await check(`4 cold start — ${label}`, async () => {
        const nav = await runColdStart(scenario);
        expect(nav.replaced.join() === want, `replaced ${JSON.stringify(nav.replaced)}`);
        if (want) expect(nav.tokenReads === 1, 'reroute happened without reading the stored token');
      });
    }
  }

  // 5 ─ text
  await check('5 the stale "silently re-mint" claim is gone from useSession.ts', () => {
    // Join wrapped comment lines first: the original read "silently\n// re-mint".
    const prose = read(SESSION).replace(/\s*\n\s*(?:\/\/+|\*)?\s*/g, ' ');
    expect(!/silently re-?mint/i.test(prose), 'useSession.ts still says Sleeper sessions silently re-mint');
  });

  console.log(`${passed} passed; ${failures} failed (league picker recovery)`);
  process.exitCode = failures ? 1 : 0;
}
main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
