#!/usr/bin/env node
// check-paywall-gate — the paywall client's gate, verify sheet and legal
// rules (#393 M1; scope §3 items 1, 3, 4, 6; legal R28.8 #1–#7, R28.9,
// R28.10, R28.12, R28.15; lead calls D1, D3, D6, D12, D15–D18, D20).
//
// WHY THIS EXISTS. Every failure this file pins is SILENT in a passing app:
//   - a background poll that opens the paywall under the user's thumb (D1);
//   - a verify sheet whose appearance depends on whether the account pays,
//     which tells anyone who typed a username that it subscribes (R28.9);
//   - "free" shown while StoreKit hasn't confirmed the free month, or a
//     per-month figure rounded the flattering way (App Store 3.1.2, R28.8);
//   - a purchase that runs while RevenueCat still holds the PREVIOUS user's
//     identity, so the webhook grants the wrong user_id and the reviewer who
//     paid stays gated (D12): an App Review rejection;
//   - a Send re-sent for the user after verifying, with no fresh tap (D18).
// D-056 retired the simulator, so none of these is caught by looking.
//
// HOW. It TRANSPILES AND EXECUTES the real modules under plain node, with
// throwing stubs for any import it didn't expect (a new runtime import is a
// loud failure, never a silent skip):
//   - api/client.ts against a scripted fetch: 402/403 routing, background,
//     the hold-and-retry after verifying, X-Device;
//   - state/usePaywallGate.ts: the router (paywall vs sheet, path choice);
//   - api/purchases.ts against a fake RevenueCat SDK: the identity-ready
//     gate and StoreKit intro eligibility;
//   - copy/monetization.ts: the verbatim strings and the R28.8 #2 math;
//   - api/trades.ts: the `background` passthrough;
//   - state/subscriptionSession.ts, state/useSession.ts (its purchases
//     identity bridge), state/useEntitlements.ts (the CustomerInfo listener)
//     and screens/PaywallScreen.tsx (its Restore, under a fake React): §10,
//     RevenueCat identifies ONLY verified sessions, and demo gets none.
// What it can only READ (the screens' JSX) it pins structurally, and says so
// in the assertion name ("[shape]").
//
// Run: node tests/check-paywall-gate.js   (or npm run test:paywall-gate)

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

const ROOT = path.resolve(__dirname, '..');
const SRC = path.join(ROOT, 'src');
const read = (rel) => fs.readFileSync(path.join(SRC, rel), 'utf8');
// Comments out before content assertions: a string quoted in a header is not
// a string the user sees.
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"`])\/\/.*$/gm, '$1');

// Checks share the scripted fetch and the router's state, so they run ONE AT
// A TIME, in declaration order.
let failures = 0;
const tests = [];
function check(name, fn) {
  tests.push({ name, fn });
}
function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}
function eq(a, b, msg) {
  if (a !== b) throw new Error(`${msg}: expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`);
}

function load(rel, stubs, globals = {}) {
  const src = read(rel);
  const js = ts.transpileModule(src, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
  }).outputText;
  const mod = { exports: {} };
  const req = (name) => {
    if (Object.prototype.hasOwnProperty.call(stubs, name)) return stubs[name];
    throw new Error(`${rel} gained an unexpected runtime import ("${name}") — stub it here deliberately.`);
  };
  const names = Object.keys(globals);
  // eslint-disable-next-line no-new-func
  new Function('module', 'exports', 'require', ...names, js)(mod, mod.exports, req, ...names.map((n) => globals[n]));
  return mod.exports;
}

const tick = () => new Promise((r) => setTimeout(r, 0));

// The ONE subscription-session predicate (§10). Loaded with NO stubs: a
// runtime import in it is a loud failure here.
const subSession = load('state/subscriptionSession.ts', {});

// ═══ 1. api/client.ts — the 402 / 403 routing, executed ═══════════════════
const responses = []; // queue of {status, body}
const sent = [];      // every fetch: {url, init}
async function fakeFetch(url, init) {
  sent.push({ url, init });
  const r = responses.shift();
  if (!r) throw new Error(`unscripted fetch: ${url}`);
  if (r.before) await r.before();
  return { status: r.status, ok: r.status >= 200 && r.status < 300, text: async () => JSON.stringify(r.body) };
}
let mirrorCalls = 0;
const client = load('api/client.ts', {
  'expo-constants': { default: { expoConfig: { version: '1.22.0', extra: { apiBaseUrl: 'https://api.test' } } } },
  'expo-device': { deviceType: 1, DeviceType: { UNKNOWN: 0, PHONE: 1, TABLET: 2, DESKTOP: 3 }, osVersion: '18.0' },
  'expo-secure-store': {
    getItemAsync: async (k) => (k === 'ftf.sessionToken' ? 'tok-1' : null),
    setItemAsync: async () => {},
    deleteItemAsync: async () => {},
  },
  'react-native': { AppState: { addEventListener: () => ({ remove() {} }) }, Platform: { OS: 'ios' } },
  './events': { track: () => {} },
}, { fetch: fakeFetch });
client.setOnVerificationRequired(() => { mirrorCalls += 1; });

let signals = [];
let handlerReturn = () => undefined;
client.setOnProRequired((s) => { signals.push(s); return handlerReturn(s); });
// The executed sections below test the gate itself, so its switch is ON
// here (§0 covers it off, against its own client and router).
client.setPaywallGateOn(() => true);
function reset() {
  signals = []; sent.length = 0; responses.length = 0; mirrorCalls = 0; handlerReturn = () => undefined;
}
async function rejects(p) {
  try { await p; } catch (e) { return e; }
  throw new Error('expected the call to reject');
}

// ═══ 0. flags off → dark (release-lead QA P1-1), executed ═════════════════
// While `monetize.paywall` is off, or unknown before the flags load, every
// gate path is today's origin/main: nothing opens, nothing is held or
// re-sent, the call is sent ONCE, and its caller gets the same ApiError (the
// banner mirror still fires for a 403, as on main). A fresh client and a
// fresh router wired to EACH OTHER, with the flags store saying off.
const CLIENT_STUBS = {
  'expo-constants': { default: { expoConfig: { version: '1.22.0', extra: { apiBaseUrl: 'https://api.test' } } } },
  'expo-device': { deviceType: 1, DeviceType: { UNKNOWN: 0, PHONE: 1, TABLET: 2, DESKTOP: 3 }, osVersion: '18.0' },
  'expo-secure-store': { getItemAsync: async (k) => (k === 'ftf.sessionToken' ? 'tok-1' : null), setItemAsync: async () => {}, deleteItemAsync: async () => {} },
  'react-native': { AppState: { addEventListener: () => ({ remove() {} }) }, Platform: { OS: 'ios' } },
  './events': { track: () => {} },
};
const flags0 = {};
const session0 = { user: { user_id: '12345', account_only: false }, isDemo: false, verification: null };
let mirror0 = 0;
const client0 = load('api/client.ts', CLIENT_STUBS, { fetch: fakeFetch });
client0.setOnVerificationRequired(() => { mirror0 += 1; });
const nav0 = [];
const gate0 = load('state/usePaywallGate.ts', {
  zustand: { create: makeZustandCreate() },
  '../api/client': client0,
  './useFeatureFlags': { useFeatureFlags: { getState: () => ({ flags: flags0 }) } },
  './subscriptionSession': subSession,
  './useSession': { useSession: { getState: () => session0 } },
});
gate0.installPaywallGate({
  isReady: () => true, navigate: (...a) => nav0.push(a), getCurrentRoute: () => ({ name: 'Trades' }),
  addListener: () => () => {}, reset: () => {},
});
// A spy in front of the router: when off, the client must never dispatch.
const dispatched0 = [];
client0.setOnProRequired((sig) => { dispatched0.push(sig); return gate0.handleGateSignal(sig); });
const DARK = [
  ['402 preview_used', '/api/trades/generate', 402, { error: 'pro_required', gate: 'preview_used' }],
  ['402 verify_required', '/api/trades/generate', 402, { error: 'pro_required', gate: 'verify_required' }],
  ['403 verification_required on a gated route', '/api/trades/generate', 403, { error: 'verification_required' }],
  ['403 verification_required on a free route', '/api/rankings/save', 403, { error: 'verification_required' }],
];
const heldFor = (p, ms) => Promise.race([p.then(() => 'settled', () => 'settled'), new Promise((r) => setTimeout(() => r('held'), ms))]);

check('0a. flags off [executed]: each gate answer opens NOTHING, is not held, is sent ONCE, and rejects with main\'s ApiError', async () => {
  for (const verified of [true, false, null]) {
    session0.verification = verified === null ? null : { session_verified: verified };
    for (const [name, p, status, body] of DARK) {
      responses.length = 0; sent.length = 0; nav0.length = 0; dispatched0.length = 0; mirror0 = 0;
      responses.push({ status, body });
      const call = client0.api.post(p, {});
      const state = await heldFor(call, 50);
      const e = await rejects(call);
      const at = `${name} (${verified === null ? 'unknown' : verified ? 'verified' : 'unverified'} session)`;
      eq(state, 'settled', `${at}: not held`);
      eq(sent.length, 1, `${at}: sent once`);
      eq(dispatched0.length, 0, `${at}: the client dispatched to the router`);
      eq(nav0.length, 0, `${at}: navigated`);
      eq(gate0.usePaywallGate.getState().verifyOpen, false, `${at}: the VerifySheet opened`);
      assert(e instanceof client0.ApiError && e.status === status && JSON.stringify(e.body) === JSON.stringify(body)
        && e.message === (body.message || body.error), `${at}: not main's ApiError`);
      eq(mirror0, status === 403 ? 1 : 0, `${at}: the banner mirror (main-identical)`);
    }
  }
});
check('0b. flags off: gateSignalFor → null for every gate answer (the consumers fall back to today\'s path); on, it classifies', () => {
  for (const [name, p, status, body] of DARK) {
    eq(client0.gateSignalFor(new client0.ApiError(status, body), p), null, `${name}, off`);
  }
  eq(client0.gateSignalFor(new client0.ApiError(403, { error: 'token_user_mismatch' }), '/api/sleeper/link'), null, 'mismatch, off');
  flags0['monetize.paywall'] = true;
  try {
    for (const [name, p, status, body] of DARK.slice(0, 3)) {
      assert(client0.gateSignalFor(new client0.ApiError(status, body), p), `${name}, on: the switch is what is dark`);
    }
  } finally {
    delete flags0['monetize.paywall'];
  }
});
check('0c. unknown → off: an absent or non-true flag is off, and a client with NO reader installed is dark', async () => {
  eq(gate0.paywallGateOn(), false, 'absent');
  flags0['monetize.paywall'] = 'true';
  eq(gate0.paywallGateOn(), false, 'non-boolean');
  delete flags0['monetize.paywall'];
  const bare = load('api/client.ts', CLIENT_STUBS, { fetch: fakeFetch });
  const calls = [];
  bare.setOnProRequired((sig) => { calls.push(sig); return new Promise(() => {}); });
  eq(bare.gateSignalFor(new bare.ApiError(402, { error: 'pro_required', gate: 'lapsed' }), '/api/trades/generate'), null, 'gateSignalFor, no reader');
  responses.length = 0; sent.length = 0;
  responses.push({ status: 403, body: { error: 'verification_required' } });
  const call = bare.api.post('/api/trades/generate', {});
  eq(await heldFor(call, 50), 'settled', 'no reader: not held');
  await rejects(call);
  eq(calls.length, 0, 'no reader: nothing dispatched');
});
check('0d. flags off: the router itself opens nothing for any signal (belt and braces)', () => {
  nav0.length = 0;
  const before = gate0.usePaywallGate.getState().verifySeq;
  for (const sig of [{ action: 'paywall', gate: 'lapsed', kind: 'find' }, { action: 'verify', gate: null, kind: 'send' }, { action: 'verify_mismatch' }]) {
    eq(gate0.handleGateSignal(sig), undefined, `${sig.action}: no hold`);
  }
  eq(nav0.length, 0, 'navigated');
  eq(gate0.usePaywallGate.getState().verifySeq, before, 'opened the sheet');
});

check('1a. a user-initiated 402 opens the paywall: {action:paywall, gate, kind:find}', async () => {
  reset();
  responses.push({ status: 402, body: { error: 'pro_required', gate: 'preview_used' } });
  const e = await rejects(client.api.post('/api/trades/generate', {}));
  assert(e.isProRequired === true && e.gate === 'preview_used', 'ApiError.isProRequired / gate not set');
  eq(signals.length, 1, 'signals');
  eq(JSON.stringify(signals[0]), JSON.stringify({ action: 'paywall', gate: 'preview_used', kind: 'find' }), 'signal');
});
check('1b. a BACKGROUND 402 opens nothing (the caller still gets the 402)', async () => {
  reset();
  responses.push({ status: 402, body: { error: 'pro_required', gate: 'preview_used' } });
  const e = await rejects(client.api.get('/api/trades/status?job_id=j', { background: true }));
  assert(e.isProRequired, 'the background caller must still see the 402');
  eq(signals.length, 0, 'background signals');
});
check('1c. D3 + copy §9.3: the send family is kind=send (propose*, queue, respond-mfl, disposition, standing offer, overhaul send); find otherwise', async () => {
  const send = ['/api/trades/propose', '/api/trades/propose-espn', '/api/trades/propose-mfl', '/api/trades/queue',
    '/api/trades/respond-mfl', '/api/trades/matches/42/disposition', 'https://api.test/api/trades/propose?x=1',
    '/api/trades/standing-offer', '/api/overhauls/o1/send'];
  const find = ['/api/trades/generate', '/api/trades/status?job_id=1', '/api/trades/swipe', '/api/trades/fair-packages',
    '/api/trades/asset-ideas', '/api/win-now/search', '/api/overhauls/o1/generate', '/api/overhauls/o1/roadmaps/r1/prepare-send',
    '/api/trades/standing-offer/revoke'];
  for (const p of send) eq(client.gateKindForPath(p), 'send', p);
  for (const p of find) eq(client.gateKindForPath(p), 'find', p);
});
check('1d. 402 gate=verify_required → the VerifySheet signal, never the paywall', async () => {
  reset();
  responses.push({ status: 402, body: { error: 'pro_required', gate: 'verify_required' } });
  await rejects(client.api.post('/api/trades/propose', {}));
  eq(signals.length, 1, 'signals');
  eq(signals[0].action, 'verify', 'action');
});
check('1e. 403 verification_required on a gated route → the VerifySheet; the banner mirror still fires', async () => {
  reset();
  responses.push({ status: 403, body: { error: 'verification_required' } });
  await rejects(client.api.post('/api/trades/swipe', {}));
  eq(signals.length, 1, 'signals');
  eq(signals[0].action, 'verify', 'action');
  eq(mirrorCalls, 1, 'setOnVerificationRequired mirror');
});
check('1f. 403 verification_required on a FREE route: banner mirror only, no sheet (never on free surfaces)', async () => {
  reset();
  responses.push({ status: 403, body: { error: 'verification_required' } });
  await rejects(client.api.get('/api/rankings?position=QB'));
  eq(signals.length, 0, 'signals on a free route');
  eq(mirrorCalls, 1, 'mirror');
});
check('1g. a background 403 keeps the mirror (byte-identical) and opens no sheet', async () => {
  reset();
  responses.push({ status: 403, body: { error: 'verification_required' } });
  await rejects(client.api.get('/api/trades/status?job_id=1', { background: true }));
  eq(signals.length, 0, 'signals');
  eq(mirrorCalls, 1, 'mirror');
});
check('1h. D18: after `verified` the original call is sent ONCE more and the caller gets that answer', async () => {
  reset();
  handlerReturn = () => Promise.resolve('verified');
  responses.push({ status: 403, body: { error: 'verification_required' } });
  responses.push({ status: 200, body: { cards: [1] } });
  const out = await client.api.get('/api/trades/status?job_id=1');
  eq(sent.length, 2, 'fetches');
  eq(JSON.stringify(out), JSON.stringify({ cards: [1] }), 'resolved with the retry');
});
check('1i. the retry lets the server decide: a 402 on the retry opens the paywall', async () => {
  reset();
  handlerReturn = (s) => (s.action === 'verify' ? Promise.resolve('verified') : undefined);
  responses.push({ status: 403, body: { error: 'verification_required' } });
  responses.push({ status: 402, body: { error: 'pro_required', gate: 'preview_used' } });
  const e = await rejects(client.api.post('/api/trades/generate', {}));
  assert(e.isProRequired, 'the caller ends on the retry\'s 402');
  eq(signals.map((s) => s.action).join(','), 'verify,paywall', 'signal sequence');
});
check('1j. Cancel (or a new sign-in) rejects with the ORIGINAL error and sends nothing more', async () => {
  for (const outcome of ['dismissed', 'signed_in']) {
    reset();
    handlerReturn = () => Promise.resolve(outcome);
    responses.push({ status: 403, body: { error: 'verification_required' } });
    const e = await rejects(client.api.post('/api/trades/swipe', {}));
    assert(e.isVerificationRequired, `${outcome}: original error`);
    eq(sent.length, 1, `${outcome}: fetches`);
  }
});
check('1k. D18: a Send is NEVER re-sent after verifying (the send kind decides); its caller is rejected at once', async () => {
  assert(/function _neverAutoRetry\(path: string\): boolean \{\s*return gateKindForPath\(path\) === 'send';\s*\}/.test(strip(read('api/client.ts'))),
    '[shape] _neverAutoRetry must reuse the send kind, not keep its own list');
  for (const p of ['/api/trades/propose', '/api/trades/queue', '/api/trades/standing-offer', '/api/overhauls/o1/send']) {
    reset();
    let settled = false;
    handlerReturn = () => new Promise(() => {}); // the sheet is still up
    responses.push({ status: 403, body: { error: 'verification_required' } });
    const pr = client.api.post(p, {}).then(() => { settled = true; }, () => { settled = true; });
    await tick(); await tick(); await tick();
    assert(settled, `${p}: the caller was held on the sheet`);
    eq(sent.length, 1, `${p}: fetches`);
    await pr;
  }
});
check('1l. 403 token_user_mismatch from the Sleeper link → verify_mismatch (the wrong-account line)', async () => {
  reset();
  responses.push({ status: 403, body: { error: 'token_user_mismatch' } });
  await rejects(client.api.post('/api/sleeper/link', { token: 't' }));
  eq(signals.length, 1, 'signals');
  eq(signals[0].action, 'verify_mismatch', 'action');
});
check('1l2. an answer to a session that has since changed opens nothing (sign-out / switch mid-flight)', async () => {
  reset();
  responses.push({ status: 402, body: { error: 'pro_required', gate: 'preview_used' }, before: () => client.clearSessionToken() });
  const e = await rejects(client.api.post('/api/trades/generate', {}));
  assert(e.isProRequired, 'the caller still gets the 402');
  eq(signals.length, 0, 'signals after a session change');
});
check('1m. X-Device is still sent as the device label (the gate\'s mobile detection)', async () => {
  reset();
  responses.push({ status: 200, body: {} });
  await client.api.get('/api/me/entitlements');
  eq(sent[0].init.headers['X-Device'], 'iphone', 'X-Device');
  assert(/'X-Device':\s*_resolveDeviceLabel\(\)/.test(read('api/client.ts')), "[shape] 'X-Device': _resolveDeviceLabel() moved");
});
check('1n. [shape] the setOnVerificationRequired mirror is byte-identical (D17)', () => {
  const MIRROR = [
    '            // Central read-gate signal — see setOnVerificationRequired above.',
    '            if (apiErr.isVerificationRequired && _onVerificationRequired) {',
    "              const sent = headers['X-Session-Token'];",
    '              const current = await getSessionToken();',
    '              try {',
    '                // This callback runs BEFORE the caller receives its rejection.',
    '                // A later screen/store guard cannot undo a stale banner write.',
    '                if (sent && sent === current && requestRevision === getSessionRevision() && !timeoutController.signal.aborted && Date.now() < opts.deadlineAt!) {',
    '                  opts.beforeDispatch?.();',
    '                  _onVerificationRequired();',
    '                }',
  ].join('\n');
  assert(read('api/client.ts').includes(MIRROR), 'the 403 state-mirror block in _apiRequestInner changed');
});

// ═══ 2. the routing reads no entitlement field (R28.9, D15) ═══════════════
check('2a. [shape] the gate routing, router and sheet read no entitlement field', () => {
  const clientSrc = strip(read('api/client.ts'));
  const gateBlock = clientSrc.slice(clientSrc.indexOf('export type GateKind'), clientSrc.indexOf('const DEFAULT_TIMEOUT_MS'));
  assert(gateBlock.length > 500 && gateBlock.includes('async function _afterGateFailure'), 'gate block not found in client.ts');
  assert(/_reportApiFailure\([\s\S]{0,200}\);\s*return _afterGateFailure<T>\(err, path, opts\);\s*\} finally \{/.test(clientSrc),
    "apiRequest's catch no longer hands the failure to the gate");
  const files = {
    'client.ts gate code': gateBlock,
    'state/usePaywallGate.ts': strip(read('state/usePaywallGate.ts')),
    'state/subscriptionSession.ts': strip(read('state/subscriptionSession.ts')),
    'components/VerifySheet.tsx': strip(read('components/VerifySheet.tsx')),
  };
  for (const [name, s] of Object.entries(files)) {
    const hit = s.match(/useEntitlements|getEntitlements|entitlement|founder|\.pro\b|\bpro:|\bsources\b|expires_at/i);
    assert(!hit, `${name} reads "${hit && hit[0]}"`);
  }
});

// ═══ 3. state/usePaywallGate.ts — the router, executed ════════════════════
function makeZustandCreate() {
  return function create(init) {
    let state;
    const listeners = new Set();
    const setState = (p) => {
      const prev = state;
      state = Object.assign({}, state, typeof p === 'function' ? p(state) : p);
      listeners.forEach((l) => l(state, prev));
    };
    const getState = () => state;
    state = init(setState, getState);
    const hook = (sel) => (sel ? sel(state) : state);
    hook.getState = getState;
    hook.setState = setState;
    hook.subscribe = (l) => { listeners.add(l); return () => listeners.delete(l); };
    return hook;
  };
}
const session = { user: { user_id: '12345', account_only: false }, isDemo: false, verification: null };
let seamHandler = null;
let gateReader = null;
const gateMod = load('state/usePaywallGate.ts', {
  zustand: { create: makeZustandCreate() },
  '../api/client': { setOnProRequired: (fn) => { seamHandler = fn; }, setPaywallGateOn: (fn) => { gateReader = fn; } },
  './useFeatureFlags': { useFeatureFlags: { getState: () => ({ flags: { 'monetize.paywall': true } }) } },
  './subscriptionSession': subSession,
  './useSession': { useSession: { getState: () => session } },
});
const navCalls = [];
const fakeNav = {
  isReady: () => true,
  navigate: (...a) => navCalls.push(a),
  getCurrentRoute: () => ({ name: 'Trades' }),
  addListener: () => () => {},
  reset: () => {},
};
gateMod.installPaywallGate(fakeNav);

check('3a. installPaywallGate wires the client seam to the router, and the gate switch to monetize.paywall', () => {
  assert(seamHandler === gateMod.handleGateSignal, 'setOnProRequired(handleGateSignal) not called');
  assert(gateReader === gateMod.paywallGateOn, 'setPaywallGateOn(paywallGateOn) not called');
});
check('3b. a paywall signal opens Paywall {source:gate, gate, kind} for a verified session', () => {
  navCalls.length = 0;
  session.verification = { session_verified: true };
  const r = seamHandler({ action: 'paywall', gate: 'trial_expired', kind: 'send' });
  eq(r, undefined, 'no hold for the paywall');
  eq(JSON.stringify(navCalls[0]), JSON.stringify(['Paywall', { source: 'gate', gate: 'trial_expired', kind: 'send' }]), 'navigate');
});
check('3c. D16a: a session the server reported UNVERIFIED gets the sheet, never the paywall', async () => {
  navCalls.length = 0;
  session.verification = { session_verified: false };
  const r = seamHandler({ action: 'paywall', gate: 'preview_used', kind: 'find' });
  eq(navCalls.length, 0, 'navigate');
  eq(gateMod.usePaywallGate.getState().verifyOpen, true, 'verifyOpen');
  assert(r && typeof r.then === 'function', 'the converted call is held on the sheet');
  gateMod.settleVerify('dismissed');
  eq(await r, 'dismissed', 'outcome');
});
check('3d. a verify signal opens ONE shared sheet; `verified` runs onVerified and resolves every holder', async () => {
  session.verification = { session_verified: false };
  let continued = 0;
  const a = seamHandler({ action: 'verify', gate: null, kind: 'find' });
  const b = gateMod.openVerify({ onVerified: () => { continued += 1; } });
  const seq = gateMod.usePaywallGate.getState().verifySeq;
  gateMod.openVerify();
  eq(gateMod.usePaywallGate.getState().verifySeq, seq, 'a second open must not reopen');
  gateMod.settleVerify('verified');
  eq(await a, 'verified', 'holder a');
  eq(await b, 'verified', 'holder b');
  eq(continued, 1, 'onVerified');
  eq(gateMod.usePaywallGate.getState().verifyOpen, false, 'closed');
});
check('3e. the same signal routes the same way whatever the account holds (no subscription input)', () => {
  // The router's only session reads are verification + isDemo; give the
  // session a "subscriber" shape and nothing may change.
  navCalls.length = 0;
  session.verification = { session_verified: true };
  seamHandler({ action: 'paywall', gate: 'lapsed', kind: 'find' });
  Object.assign(session, { pro: true, founder: true, entitlements: { pro: true } });
  seamHandler({ action: 'paywall', gate: 'lapsed', kind: 'find' });
  eq(JSON.stringify(navCalls[0]), JSON.stringify(navCalls[1]), 'routing changed with a subscription field');
  delete session.pro; delete session.founder; delete session.entitlements;
});
check('3f. D18 FINAL: Sleeper sessions verify with Sleeper; every other session gets the Apple variant; no MFL path', () => {
  const p = gateMod.verifyPathFor;
  eq(p({ user_id: '123456789' }, false), 'sleeper', 'sleeper user');
  eq(p({ user_id: 'entry:espn:{SWID}' }, false), 'apple', 'espn entry');
  eq(p({ user_id: 'entry:mfl:123.f0001' }, false), 'apple', 'mfl entry');
  eq(p({ user_id: 'acct_9' }, false), 'apple', 'account key');
  eq(p({ user_id: '123', account_only: true }, false), 'apple', 'account_only');
  eq(p({ user_id: 'demo_user_ab12' }, true), 'apple', 'demo');
  eq(p(null, false), 'apple', 'no user');
  const both = strip(read('state/usePaywallGate.ts')) + strip(read('components/VerifySheet.tsx'));
  assert(!/mfl/i.test(both.replace(/entry:/g, '')), '[shape] an MFL path in the router or sheet');
});

// ═══ 4. copy/monetization.ts — verbatim strings and R28.8, executed ═══════
// Its one import, the support address, is the real constant-only module.
const copy = load('copy/monetization.ts', { '../utils/supportContact': load('utils/supportContact.ts', {}) });
const SLEEPER_TITLE = 'Verify this session first';
const SLEEPER_BODY = 'To use or start a subscription, verify this session first. Signing in confirms the account is yours.';
const APPLE_TITLE = 'A new sign-in is needed';
const APPLE_BODY = "Use Sign in with Apple to subscribe. It's a new sign-in: reconnect your league in Settings, and nothing from this session carries over.";
const WRONG = 'That sign-in is for a different account, so nothing changed. Use the same account you signed in with.';
const SWITCHED = "That sign-in is for a different account, so you're now signed in to that one.";

check('4a. the verify strings are verbatim, per variant', () => {
  eq(copy.verifyCopy('sleeper').title, SLEEPER_TITLE, 'sleeper title');
  eq(copy.verifyCopy('sleeper').body, SLEEPER_BODY, 'sleeper body');
  eq(copy.verifyCopy('apple').title, APPLE_TITLE, 'apple title');
  eq(copy.verifyCopy('apple').body, APPLE_BODY, 'apple body');
  eq(copy.MON['mon.verify.sleeper'], 'Verify with Sleeper', 'sleeper button');
  eq(copy.MON['mon.verify.done'], 'Session verified.', 'done');
  eq(copy.MON['mon.verify.continue'], 'Continue', 'continue');
});
check('4b. the Apple variant never says "verify"; the Sleeper variant never offers Apple', () => {
  // The module's own strings (4a pins them verbatim; this pins the rule).
  const apple = [...Object.values(copy.verifyCopy('apple')), copy.verifyOutcomeLine('apple', 'switched')].join(' ');
  assert(!/verif/i.test(apple), 'the Apple variant says verify');
  const sleeper = Object.values(copy.verifyCopy('sleeper')).join(' ') + copy.MON['mon.verify.sleeper'];
  assert(!/apple/i.test(sleeper), 'the Sleeper variant mentions Apple');
  const sheet = strip(read('components/VerifySheet.tsx'));
  const i = sheet.indexOf("path === 'sleeper' ? (");
  const sleeperArm = sheet.slice(i, sheet.indexOf(') : appleAvailable ?', i));
  assert(i > 0 && /mon\.verify\.sleeper/.test(sleeperArm) && !/Apple/.test(sleeperArm),
    "[shape] the sheet's Sleeper arm renders Verify with Sleeper and no Apple button");
  assert(/navigate\('SleeperConnect'\)/.test(sheet), "[shape] Verify with Sleeper → SleeperConnect");
  assert(/AppleAuthenticationButton/.test(sheet.slice(sheet.indexOf(') : appleAvailable ?'))),
    "[shape] the other arm is Apple's own button");
});
check('4c. post-verify lines are chosen PER PATH (D17, D20): done / wrong account / switched', () => {
  const L = copy.verifyOutcomeLine;
  eq(L('sleeper', 'verified'), 'Session verified.', 'sleeper verified');
  eq(L('sleeper', 'mismatch'), WRONG, 'sleeper mismatch (nothing changed)');
  eq(L('apple', 'switched'), SWITCHED, 'apple switched (now signed in to that one)');
  eq(L('apple', 'verified'), null, 'apple never shows "Session verified."');
  eq(L('apple', 'mismatch'), null, 'apple never says "nothing changed"');
  eq(L('apple', 'new_account'), null, 'a new Apple account claims nothing');
  eq(L('sleeper', 'switched'), null, 'sleeper never "switches"');
});
check('4d. [shape] "Session verified." only after the server returned verified === true', () => {
  const sheet = strip(read('components/VerifySheet.tsx'));
  const setsVerified = sheet.match(/setOutcome\('verified'\)/g) || [];
  eq(setsVerified.length, 1, "setOutcome('verified') sites");
  assert(/if \(trip\.current\.verified\) \{\s*setOutcome\('verified'\);/.test(sheet),
    "setOutcome('verified') is not gated on trip.current.verified");
  const flagSets = sheet.match(/trip\.current\.verified = true/g) || [];
  eq(flagSets.length, 1, 'trip.current.verified = true sites');
  assert(/s\.verification !== prev\.verification && s\.verification\?\.session_verified === true\) \{\s*trip\.current\.verified = true/.test(sheet),
    'the verified flag is set only on a fresh session_verified === true write');
  eq((sheet.match(/settleVerify\('verified'\)/g) || []).length, 1, "settleVerify('verified') sites");
  // The one writer of that state on the Sleeper path writes it only after the
  // link response says `verified === true`.
  const conn = strip(read('screens/SleeperConnectScreen.tsx'));
  const gateAt = conn.indexOf('const isVerified = res?.verified === true;');
  const throwAt = conn.indexOf("if (!isVerified) throw new Error('verification_incomplete');");
  const writeAt = conn.indexOf('session_verified: true');
  assert(gateAt > 0 && throwAt > gateAt && writeAt > throwAt,
    'SleeperConnectScreen no longer writes session_verified only after verified === true');
});
check('4e. [shape] the wrong-account lines by path: mismatch only on the Sleeper return, switched only after Apple', () => {
  const sheet = strip(read('components/VerifySheet.tsx'));
  eq((sheet.match(/'mismatch'/g) || []).length, 1, "'mismatch' sites");
  assert(/trip\.current\.mismatch \? 'mismatch' : null/.test(sheet), 'mismatch comes from the Sleeper trip');
  const apple = sheet.slice(sheet.indexOf('const signInWithApple'), sheet.indexOf('const copy = verifyCopy'));
  assert(/setOutcome\('switched'\)/.test(apple), 'switched is set in the Apple path');
  eq((sheet.match(/setOutcome\('switched'\)/g) || []).length, 1, "setOutcome('switched') sites");
  assert(/account_created\?: boolean \}\)\.account_created === false/.test(apple) && /switched = true;/.test(apple),
    'switched only for an existing account (linked, or account_created === false)');
  assert(!/restore|Restore|PLAN_TITLE|\$\d|price/i.test(sheet.replace(/pricing/gi, '')),
    'the sheet shows something subscription-specific (Restore, a plan or a price)');
});
check('4f. [shape] the Apple variant body condition is recorded in code (nothing carries over)', () => {
  const raw = read('copy/monetization.ts') + read('components/VerifySheet.tsx');
  assert(/carries over[\s\S]{0,300}migrates?[\s\S]{0,200}must change/i.test(raw),
    'no code comment that the "nothing carries over" copy must change if Apple sign-in migrates entry-session data');
});

// R28.8
const NOT_ELIGIBLE = [
  copy.disclosure('annual', '$24.99', false),
  copy.disclosure('monthly', '$4.99', false),
  copy.ctaLabel(false),
  copy.offerBodyFor('first_opinion', false),
  copy.offerBodyFor('left_deck', false),
  copy.headlineFor('first_opinion'), copy.headlineFor('gate', 'find'), copy.headlineFor('gate', 'send'),
  copy.headlineFor('settings'), copy.headlineFor('preview_end'),
  copy.MON['mon.pay.value'], copy.MON['mon.pay.b1'], copy.MON['mon.pay.b2'], copy.MON['mon.pay.b3'],
  copy.MON['mon.pay.b4'], copy.MON['mon.lock.free'], copy.MON['mon.club.join'],
  copy.MON['mon.pay.founder.price'], copy.MON['mon.pay.founder.new'], copy.MON['mon.pay.founder.keep'],
  copy.MON['mon.pay.founder.lapse'],
];
check('4g. R28.8 #1: the paid state (not eligible / unknown) has no "free" anywhere', () => {
  for (const s of NOT_ELIGIBLE) assert(!/free/i.test(s), `"free" in the paid state: ${s}`);
  eq(copy.disclosure('annual', '$24.99', false),
    'Fleeced Pro Annual: $24.99/year, charged to your Apple ID when you confirm. Renews automatically until cancelled. Cancel in your Apple ID settings at least 24 hours before the current period ends.',
    'mon.pay.disc.paid (annual) verbatim');
  eq(copy.disclosure('monthly', '$4.99', true),
    'Fleeced Pro Monthly: 1 month free, then $4.99/month. Payment is charged to your Apple ID when the free month ends. Renews automatically until cancelled. Cancel in your Apple ID settings at least 24 hours before the free month or the current period ends.',
    'mon.pay.disc.trial (monthly) verbatim');
  eq(copy.trialLine('annual', '$24.99'), '1 month free, then $24.99/year', 'mon.offer.trial_line verbatim');
});
check('4h. R28.8 #1 [shape]: the screen keys every "free" string off StoreKit eligibility, never config', () => {
  const s = strip(read('screens/PaywallScreen.tsx'));
  assert(!/trial_eligible/.test(s), 'PaywallScreen reads config.trial_eligible');
  assert(/eligibilityQuery\.data\?\.\[productId\] === true/.test(s), 'eligibility must be `=== true` (unknown → false)');
  assert(/checkIntroEligibility\(/.test(s), 'checkIntroEligibility not used');
  assert(/\{eligible \? \(\s*<ChalkText[^>]*>\s*\{trialLine\(/.test(s), 'the trial line renders only when eligible');
  assert(/disclosure\(selected\.period, selected\.price, eligible\)/.test(s), 'the disclosure tracks eligibility');
  assert(/label=\{ctaLabel\(eligible\)\}/.test(s), 'the CTA tracks eligibility');
});
check('4i. R28.8 #2: per-month rounds UP, savings rounds DOWN, from live StoreKit prices', () => {
  eq(copy.perMonthCentsUp(copy.toCents(24.99)), 209, '$24.99/12 → $2.09');
  eq(copy.perMonthCentsUp(copy.toCents(34.99)), 292, '$34.99/12 → $2.92');
  eq(copy.perMonthCentsUp(copy.toCents(23.88)), 199, 'exact $1.99 stays $1.99 (no float ceil)');
  eq(copy.savingsPercentDown(2499, 499), 58, '58.27% → 58');
  eq(copy.savingsPercentDown(3499, 699), 58, '58.29% → 58');
  eq(copy.savingsPercentDown(5999, 999), 49, '49.96% → 49 (never rounds up to 50)');
  eq(copy.savingsPercentDown(2388, 199), null, 'no saving → no claim');
  const line = copy.annualSubLine({ price: 24.99, currencyCode: 'USD' }, { price: 4.99, priceString: '$4.99', currencyCode: 'USD' });
  assert(/^\$?2\.09\/month, billed yearly\. 58% less than 12 months at \$4\.99\.$/.test(line.replace(/^US\$/, '$')), `sub line: ${line}`);
  eq(copy.annualSubLine(null, { price: 4.99, priceString: '$4.99', currencyCode: 'USD' }), null, 'no StoreKit annual → no line');
  const s = strip(read('screens/PaywallScreen.tsx'));
  assert(/annualSubLine\(annual, monthly\)/.test(s) && /pkg\?\.product;/.test(s), '[shape] the sub line is fed StoreKit products only');
});
check('4j. R28.8 #2 [shape]: "/year" is the largest price text; the per-month line is smaller; no SAVE badge', () => {
  const s = strip(read('screens/PaywallScreen.tsx'));
  assert(/\{sub \? <ChalkText variant="bodySm">\{sub\}<\/ChalkText> : null\}/.test(s), 'the per-month sub line is not body-sm');
  assert(/<ChalkText variant="dataLg">\{pp\}<\/ChalkText>/.test(s), 'the plan price is not data-lg');
  assert(!/SAVE|Best value|best_value|badge/i.test(s), 'a SAVE / Best value badge');
});
check('4k. R28.8 #3: the CTA is "Start 1-month trial" (eligible) / "Subscribe"; no "Start my free month" yet', () => {
  eq(copy.ctaLabel(true), 'Start 1-month trial', 'eligible CTA');
  eq(copy.ctaLabel(false), 'Subscribe', 'paid CTA');
  const all = walk(SRC).map((f) => strip(fs.readFileSync(f, 'utf8'))).join('\n');
  assert(!/Start my free month/.test(all), '"Start my free month" in src before legal\'s ruling lands');
});
check('4l. R28.8 #4/#5/#7: no kept_home line, no locked-feature card, no board-based pricing wording', () => {
  const all = walk(SRC).map((f) => strip(fs.readFileSync(f, 'utf8'))).join('\n');
  assert(!/kept_home|You kept the Founder price/.test(all), 'mon.club.kept_home is in M1');
  assert(!/GatedCard|LockedFeatureCard|mz\.gate/.test(all), 'a locked-feature card');
  const mon = Object.values(copy.MON).join(' ');
  assert(!/pric\w*[^.]{0,40}\bboards?\b|\bboards?\b[^.]{0,40}pric/i.test(mon), 'board-based pricing wording');
});
check('4m. R28.8 #6: the plan titles match App Store Connect exactly; no em-dash fallbacks', () => {
  eq(copy.PLAN_TITLE.annual, 'Fleeced Pro Annual', 'annual');
  eq(copy.PLAN_TITLE.monthly, 'Fleeced Pro Monthly', 'monthly');
  const all = walk(SRC).map((f) => strip(fs.readFileSync(f, 'utf8'))).join('\n');
  assert(!/Fleeced Pro\s+[—–-]\s/.test(all), '"Fleeced Pro — …" title variant');
  const s = strip(read('screens/PaywallScreen.tsx'));
  assert(!/product\?\.title/.test(s), 'the screen renders StoreKit\'s title instead of the ASC constant');
});
check('4n. scope §3.4: no "days free", "30 days" or trial_days anywhere in mobile/src', () => {
  for (const f of walk(SRC)) {
    const s = strip(fs.readFileSync(f, 'utf8'));
    const hit = s.match(/days free|\b30 days\b|trial_days/i);
    assert(!hit, `${path.relative(ROOT, f)}: "${hit && hit[0]}"`);
  }
});
check('4o. D10 / scope §3.6: no countdown, days-left, ends-soon or trial-end date in the paywall sources', () => {
  const files = ['screens/PaywallScreen.tsx', 'copy/monetization.ts', 'components/VerifySheet.tsx', 'state/usePaywallGate.ts'];
  for (const f of files) {
    const s = strip(read(f));
    const hit = s.match(/days? left|ends? soon|countdown|last chance|trial ends|ends on|expires on|closes_at|expires_at|toLocaleDateString/i);
    assert(!hit, `${f}: "${hit && hit[0]}"`);
  }
});

// ═══ 5. api/purchases.ts — identity-ready gate + eligibility, executed ════
const sdk = {
  calls: [],
  appUserId: null,
  pendingLogin: null,
  eligibility: {},
  eligibilityThrows: false,
  configure({ appUserID }) { this.calls.push(['configure', appUserID]); this.appUserId = appUserID; },
  logIn(id) {
    this.calls.push(['logIn', id]);
    return new Promise((res) => { this.pendingLogin = () => { this.appUserId = id; res({}); }; });
  },
  logOut() { throw new Error('logOut must never be called'); },
  async getAppUserID() { return this.appUserId; },
  async purchasePackage(pkg) { this.calls.push(['purchase', pkg.id, this.appUserId]); return { customerInfo: {} }; },
  async restorePurchases() { this.calls.push(['restore', this.appUserId]); return { entitlements: { active: {} } }; },
  async checkTrialOrIntroductoryPriceEligibility(ids) {
    if (this.eligibilityThrows) throw new Error('boom');
    this.calls.push(['eligibility', ids.join(',')]);
    return this.eligibility;
  },
};
process.env.EXPO_PUBLIC_REVENUECAT_IOS_KEY = 'appl_test';
const purchases = load('api/purchases.ts', { 'react-native-purchases': { default: sdk } });
delete process.env.EXPO_PUBLIC_REVENUECAT_IOS_KEY;

check('5a. D12: configure uses the session user_id, and identity is ready only for that user', async () => {
  await purchases.initPurchases('u1');
  eq(JSON.stringify(sdk.calls[0]), JSON.stringify(['configure', 'u1']), 'configure');
  assert(purchases.isIdentityReady('u1') && !purchases.isIdentityReady('u2'), 'ready for u1 only');
});
check('5b. D12: after a switch, purchase and restore WAIT until RevenueCat is the new user', async () => {
  const p = purchases.initPurchases('u2');
  assert(!purchases.isIdentityReady('u1') && !purchases.isIdentityReady('u2'), 'nobody is ready mid-logIn');
  const before = sdk.calls.length;
  let done = false;
  const buy = purchases.purchasePackage({ id: 'annual' }, 'u2').then(() => { done = true; });
  const rest = purchases.restorePurchases('u2');
  await tick(); await tick();
  assert(!done && !sdk.calls.slice(before).some((c) => c[0] === 'purchase' || c[0] === 'restore'),
    'Apple\'s sheet was reached before RevenueCat became u2');
  sdk.pendingLogin();
  await p; await buy; await rest;
  const after = sdk.calls.slice(before);
  assert(after.some((c) => c[0] === 'purchase' && c[2] === 'u2'), 'the purchase ran as u2');
  assert(after.some((c) => c[0] === 'restore' && c[1] === 'u2'), 'the restore ran as u2');
});
check('5c. D12: a stale identity never reaches Apple\'s sheet (PurchaseIdentityError)', async () => {
  const before = sdk.calls.length;
  let threw = null;
  try { await purchases.purchasePackage({ id: 'monthly' }, ''); } catch (e) { threw = e; }
  assert(threw && threw.name === 'PurchaseIdentityError', 'no session user → identity error');
  sdk.appUserId = 'drifted';
  threw = null;
  try { await purchases.purchasePackage({ id: 'monthly' }, 'u2'); } catch (e) { threw = e; }
  assert(threw && threw.name === 'PurchaseIdentityError', 'SDK appUserID ≠ session user → identity error');
  sdk.appUserId = 'u2';
  assert(!sdk.calls.slice(before).some((c) => c[0] === 'purchase'), 'a purchase ran on a mismatched identity');
  let timedOut = false;
  await purchases.whenIdentityReady('u9', 30).catch(() => { timedOut = true; });
  assert(timedOut, 'whenIdentityReady never gives up');
});
check('5d. D6 / R28.8 #1: StoreKit intro eligibility — confirmed free month only; unknown / error → not eligible', async () => {
  const month = { price: 0, period: 'P1M', periodUnit: 'MONTH', periodNumberOfUnits: 1 };
  sdk.eligibility = { ftf_pro_annual: { status: 2 }, ftf_pro_monthly: { status: 0 } };
  let out = await purchases.checkIntroEligibility([
    { identifier: 'ftf_pro_annual', introPrice: month },
    { identifier: 'ftf_pro_monthly', introPrice: month },
  ]);
  eq(out.ftf_pro_annual, true, 'eligible + free month');
  eq(out.ftf_pro_monthly, false, 'UNKNOWN → not eligible');
  sdk.eligibility = { ftf_pro_annual: { status: 2 } };
  out = await purchases.checkIntroEligibility([{ identifier: 'ftf_pro_annual', introPrice: null }]);
  eq(out.ftf_pro_annual, false, 'eligible but no intro offer data');
  out = await purchases.checkIntroEligibility([{ identifier: 'ftf_pro_annual', introPrice: { price: 0, period: 'P1W', periodUnit: 'WEEK', periodNumberOfUnits: 1 } }]);
  eq(out.ftf_pro_annual, false, 'an intro that is not one free month');
  out = await purchases.checkIntroEligibility([{ identifier: 'ftf_pro_annual', introPrice: { price: 0.99, period: 'P1M', periodUnit: 'MONTH', periodNumberOfUnits: 1 } }]);
  eq(out.ftf_pro_annual, false, 'a PAID one-month intro is not "1 month free"');
  sdk.eligibilityThrows = true;
  out = await purchases.checkIntroEligibility([{ identifier: 'ftf_pro_annual', introPrice: month }]);
  eq(JSON.stringify(out), '{}', 'SDK error → nothing eligible');
  sdk.eligibilityThrows = false;
  eq(purchases.isConfirmedFreeMonth(1, month), false, 'INELIGIBLE');
  eq(purchases.isConfirmedFreeMonth(3, month), false, 'NO_INTRO_OFFER_EXISTS');
});
check('5e. [shape] the paywall passes the session user to purchase/restore and shows a pending CTA meanwhile', () => {
  const s = strip(read('screens/PaywallScreen.tsx'));
  assert(/await purchasePackage\(selected\.pkg, userId\)/.test(s), 'purchasePackage(pkg, userId)');
  assert(/await restorePurchases\(userId\)/.test(s), 'restorePurchases(userId)');
  assert(/loading=\{busy \|\| identityPending\}/.test(s) && /disabled=\{!selected \|\| busy \|\| identityPending\}/.test(s),
    'the CTA is not pending while identity is unconfirmed');
  const p = strip(read('api/purchases.ts'));
  assert(!/\.logOut\(/.test(p), 'logOut in purchases.ts');
});
check('5f. [shape] every user- and verification-setting path runs the identity bridge (setUser, bootstrap, startDemoSession, setVerification), and initPurchases is reached ONLY through it', () => {
  const s = strip(read('state/useSession.ts'));
  const body = (name, head = `${name}: async`) => {
    const i = s.indexOf(head);
    const j = s.indexOf('\n  },', i);
    return i > 0 && j > i ? s.slice(i, j) : '';
  };
  eq((s.match(/\binitPurchases\(/g) || []).length, 1, 'initPurchases( call sites in useSession (only the helper)');
  assert(/function syncPurchasesIdentity\(s: SessionState\): void \{\s*const id = purchasesIdentityTarget\(s\);\s*if \(id\) void initPurchases\(id\);\s*\}/.test(s),
    'the helper: initPurchases only with purchasesIdentityTarget\'s id');
  const user = body('setUser');
  const guardAt = user.indexOf('if (generation !== leagueSessions.currentGeneration() || get().user !== u) return;');
  const syncAt = user.indexOf('syncPurchasesIdentity(get());');
  assert(guardAt > 0 && syncAt > guardAt, 'setUser: the bridge runs after the generation / user-changed guard');
  assert(body('bootstrap').includes('syncPurchasesIdentity(get());'), 'bootstrap (hydrate)');
  const verif = body('setVerification', 'setVerification: (v) => {');
  assert(verif.indexOf('set({ verification: v });') >= 0
    && verif.indexOf('syncPurchasesIdentity(get());') > verif.indexOf('set({ verification: v });'),
  'setVerification: the bridge runs after the verification is stored');
  const demo = body('startDemoSession');
  const setAt = demo.indexOf('set({');
  const sentryAt = demo.indexOf('sentrySetUser({ id: demoUser.user_id });');
  const initAt = demo.indexOf('syncPurchasesIdentity(get());');
  assert(setAt > 0 && sentryAt > setAt && initAt > sentryAt,
    'startDemoSession: the bridge must come right after sentrySetUser, after set({');
  assert(!/\.logOut\(/.test(s), 'logOut in useSession');
});

// ═══ 6. the paywall screen — Restore, variants, testIDs (shape) ═══════════
check('6a. [shape] Restore renders on the paywall and is wired', () => {
  const s = strip(read('screens/PaywallScreen.tsx'));
  assert(/testID="paywall-restore"/.test(s) && /\{MON\['mon\.pay\.restore'\]\}/.test(s), 'Restore not rendered');
  const block = s.slice(s.indexOf('const anchoredBlock'), s.indexOf('<SafeAreaView'));
  assert(block.includes('testID="paywall-restore"'), 'Restore must sit in the always-visible anchored block');
  const nn = block.indexOf('{dismissible ? (');
  assert(nn > 0 && !block.slice(nn, block.indexOf(') : null}', nn)).includes('paywall-restore'),
    'Restore must not depend on `dismissible` or any other condition');
});
check('6b. [shape] the headline/body variants come from the copy module by source + kind', () => {
  const s = strip(read('screens/PaywallScreen.tsx'));
  assert(/headlineFor\(source, kind\)/.test(s), 'headlineFor(source, kind)');
  assert(/offerBodyFor\(source, eligible\)/.test(s), 'offerBodyFor(source, eligible)');
  eq(copy.headlineFor('gate', 'find'), 'Finding trades needs a subscription.', 'gate/find');
  eq(copy.headlineFor('gate', 'send'), 'Sending trades needs a subscription.', 'gate/send');
  eq(copy.headlineFor('first_opinion'), "There's a full deck behind this page.", 'trigger');
  eq(copy.headlineFor('preview_end'), "There's a full deck behind this page.", 'end card');
  eq(copy.headlineFor('settings'), 'Find trades. Send them to your league.', 'settings');
  eq(copy.offerBodyFor('gate', true), null, 'no body on the lock variant');
  eq(copy.offerBodyFor('preview_end', true), null, 'no body on the end-card variant');
});
check('6c. [shape] testIDs kept + the scope\'s added; paywall_viewed carries gate + kind', () => {
  const s = strip(read('screens/PaywallScreen.tsx'));
  for (const id of ['paywall-screen', 'paywall-close', 'paywall-purchase-cta', 'paywall-restore',
    'paywall-privacy-link', 'paywall-terms-link', 'paywall-offer-cta', 'paywall-offer-not-now']) {
    assert(s.includes(`testID="${id}"`), id);
  }
  assert(/testID=\{`paywall-plan-\$\{/.test(s), 'paywall-plan-<id>');
  assert(/track\('paywall_viewed', \{\s*source,\s*platform: 'ios',\s*\.\.\.\(gate \? \{ gate \} : \{\}\),\s*\.\.\.\(kind \? \{ kind \} : \{\}\),/.test(s),
    'paywall_viewed {source, platform, gate?, kind?}');
});
check('6d. [shape] an unverified session never sees the paywall (backstop → the sheet)', () => {
  const s = strip(read('screens/PaywallScreen.tsx'));
  assert(/const unverified = useSession\(\(s\) => isUnverifiedSession\(s\)\);/.test(s), 'unverified read (the router\'s predicate, demo included)');
  assert(/if \(!paywallOn \|\| unverified\) return null;/.test(s), 'renders nothing while unverified');
  assert(/openVerify\(\)/.test(s), 'opens the VerifySheet');
});
check('6f. R28.9 [shape]: an unverified session fetches nothing subscription-specific — the config, offerings and eligibility queries all wait on `!unverified` (release-lead QA S2d)', () => {
  const s = strip(read('screens/PaywallScreen.tsx'));
  assert(/queryFn: \(\) => getPaywallConfig\('ios'\),\s*enabled: paywallOn && !unverified,/.test(s), 'the paywall config');
  assert(/queryFn: \(\) => getOfferings\(\),\s*enabled: paywallOn && !unverified,/.test(s), 'the offerings');
  assert(/queryFn: \(\) => checkIntroEligibility\(storeProducts\),\s*enabled: paywallOn && !unverified && storeProducts\.length > 0,/.test(s), 'the intro eligibility');
  eq((s.match(/useQuery\(\{/g) || []).length, 3, 'exactly these three queries');
});
check('6g. release-lead QA P3 [executed]: a user change resets useEntitlements (not-entitled defaults, the device cache dropped, the server asked again); boot\'s null → user hydrate keeps the grace cache', async () => {
  const sessionStore = makeZustandCreate()(() => ({ user: null, hasToken: true }));
  const removed = [];
  let fetches = 0;
  const ent = load('state/useEntitlements.ts', {
    zustand: { create: makeZustandCreate() },
    '@react-native-async-storage/async-storage': { default: {
      getItem: async () => null, setItem: async () => {}, removeItem: async (k) => { removed.push(k); },
    } },
    '../api/billing': { getEntitlements: async () => { fetches += 1; return { pro: false, enforcing: false }; } },
    '../api/purchases': { currentIdentityUserId: () => null, hasProEntitlement: () => false, onCustomerInfoChange: () => () => {}, setOnPurchasesReady: () => {} },
    './subscriptionSession': subSession,
    './useSession': { useSession: sessionStore },
  });
  ent.initEntitlements();
  await tick(); await tick();
  const grant = { pro: true, founder: true, enforcing: true, expiresAt: '2027-01-01', optimistic: false };
  ent.useEntitlements.setState(grant);
  const f0 = fetches;
  sessionStore.setState({ user: { user_id: 'A' } });
  await tick();
  eq(ent.useEntitlements.getState().pro, true, 'boot hydrate (null → A) keeps the cached answer');
  eq(removed.length, 0, 'boot hydrate keeps the device cache');
  ent.useEntitlements.setState(grant);
  sessionStore.setState({ user: { user_id: 'B' } });
  const st = ent.useEntitlements.getState();
  eq(JSON.stringify([st.pro, st.founder, st.enforcing, st.expiresAt]), JSON.stringify([false, false, false, null]), 'A → B resets');
  eq(removed[0], 'ftf.entitlements.v1', 'the device cache dropped');
  await tick();
  assert(fetches > f0, 'the server asked again');
  ent.useEntitlements.setState(grant);
  sessionStore.setState({ user: null });
  eq(ent.useEntitlements.getState().pro, false, 'sign-out resets');
  ent.useEntitlements.setState(grant);
  sessionStore.setState({ user: null, hasToken: false });
  eq(ent.useEntitlements.getState().pro, true, 'no user change, no reset');
});
check('6e. [shape] the analytics row is registered with the emitter (gate + kind)', () => {
  const tax = fs.readFileSync(path.join(ROOT, '..', 'backend', 'analytics_taxonomy.py'), 'utf8');
  assert(/"paywall_viewed":\s*frozenset\(\{"source", "platform", "gate", "kind"\}\)/.test(tax),
    'backend/analytics_taxonomy.py paywall_viewed row');
});

// ═══ 7. api/trades.ts — the background passthrough, executed ══════════════
check('7a. generateTrades / getTradeStatus pass `background` through to the client', async () => {
  const calls = [];
  const trades = load('api/trades.ts', {
    './client': {
      api: {
        post: async (p, body, opts) => { calls.push(['post', p, opts]); return { status: 'running', cards: [] }; },
        get: async (p, opts) => { calls.push(['get', p, opts]); return { status: 'running', cards: [] }; },
      },
    },
  });
  await trades.generateTrades({ league_id: 'L' }, undefined, { background: true });
  await trades.getTradeStatus('job1', undefined, { background: true });
  await trades.getTradeStatus('job2');
  eq(calls[0][2] && calls[0][2].background, true, 'generateTrades');
  eq(calls[1][2] && calls[1][2].background, true, 'getTradeStatus');
  eq(calls[2][2], undefined, 'default stays user-initiated');
});

// ═══ 10. RC identity — RevenueCat identifies ONLY verified sessions ═══════
// head-eng 2026-10-29 (release-lead QA P2-5): a typed, unverified Sleeper id
// that reached `Purchases.logIn` would let this device read that account's
// CustomerInfo (R28.9-class) and a Restore would move the Apple ID's
// purchases onto it. Demo is STRICT: no configure, no logIn, no CustomerInfo,
// no purchase, no Restore, and it counts as unverified on every subscription
// surface. Everything below is EXECUTED except where labelled [shape].
const V = (session_verified) => ({ session_verified });
const sleeperUser = (id) => ({ user_id: id, username: 'typed', display_name: 'Typed', avatar_id: null });
const acctUser = (id) => ({ user_id: id, username: '', display_name: 'Manager', avatar_id: null, account_only: true });

check('10a. subscriptionSessionState: demo, then the server\'s answer, then the account-only acct_ key; else unknown', () => {
  const st = subSession.subscriptionSessionState;
  const rows = [
    [{ isDemo: true, verification: V(true), user: acctUser('acct_1') }, 'demo', 'demo beats a verified answer'],
    [{ isDemo: true, verification: null, user: { user_id: 'demo_user_ab12' } }, 'demo', 'demo, unknown'],
    [{ isDemo: false, verification: V(true), user: sleeperUser('111') }, 'verified', 'session_verified true'],
    [{ isDemo: false, verification: V(false), user: sleeperUser('111') }, 'unverified', 'session_verified false'],
    [{ isDemo: false, verification: V(false), user: acctUser('acct_1') }, 'unverified', 'the server\'s false beats the acct_ key'],
    [{ isDemo: false, verification: null, user: acctUser('acct_1') }, 'verified', 'account_only + acct_ (verified by construction)'],
    [{ isDemo: false, verification: null, user: { user_id: '111', account_only: true } }, 'unknown', 'account_only WITHOUT the acct_ prefix'],
    [{ isDemo: false, verification: null, user: { user_id: 'acct_1' } }, 'unknown', 'an acct_ key without account_only'],
    [{ isDemo: false, verification: V(null), user: sleeperUser('111') }, 'unknown', 'session_verified null'],
    [{ isDemo: false, verification: null, user: sleeperUser('111') }, 'unknown', 'verification null'],
    [{ isDemo: false, verification: undefined, user: null }, 'unknown', 'no user, no answer'],
  ];
  for (const [input, want, name] of rows) eq(st(input), want, name);
});
check('10b. purchasesIdentityTarget: the user id for EXACTLY verified; null for unverified, unknown and demo', () => {
  const t = subSession.purchasesIdentityTarget;
  eq(t({ isDemo: false, verification: V(true), user: sleeperUser('111') }), '111', 'verified');
  eq(t({ isDemo: false, verification: null, user: acctUser('acct_1') }), 'acct_1', 'account-only acct_');
  eq(t({ isDemo: false, verification: V(false), user: sleeperUser('111') }), null, 'unverified');
  eq(t({ isDemo: false, verification: null, user: sleeperUser('111') }), null, 'unknown');
  eq(t({ isDemo: false, verification: V(null), user: sleeperUser('111') }), null, 'session_verified null');
  eq(t({ isDemo: false, verification: null, user: { user_id: '111', account_only: true } }), null, 'account_only without acct_');
  eq(t({ isDemo: true, verification: V(true), user: { user_id: 'demo_user_ab12' } }), null, 'demo (strict), even with a verified answer');
  eq(t({ isDemo: true, verification: null, user: acctUser('acct_1') }), null, 'demo over an acct_ key');
  eq(t({ isDemo: false, verification: V(true), user: null }), null, 'no user');
});
check('10c. customerInfoApplies: verified AND RevenueCat\'s completed identity is the session user', () => {
  const a = subSession.customerInfoApplies;
  const ver = { isDemo: false, verification: V(true), user: sleeperUser('111') };
  eq(a(ver, '111'), true, 'verified, matching identity');
  eq(a(ver, '222'), false, 'verified, MISMATCHED identity (a device last logged in as someone else)');
  eq(a(ver, null), false, 'verified, no completed identity (unconfigured / logIn in flight)');
  eq(a({ ...ver, verification: V(false) }, '111'), false, 'unverified, matching identity');
  eq(a({ ...ver, verification: null }, '111'), false, 'unknown, matching identity');
  eq(a({ isDemo: true, verification: V(true), user: { user_id: 'demo_user_ab12' } }, 'demo_user_ab12'), false, 'demo, matching identity');
  eq(a({ isDemo: false, verification: null, user: acctUser('acct_1') }, 'acct_1'), true, 'account-only acct_, matching');
});
check('10d. [shape] the demo exclusion is the ONE `=== \'verified\'` comparison in purchasesIdentityTarget; no runtime import', () => {
  const s = strip(read('state/subscriptionSession.ts'));
  assert(!/^\s*import\s+(?!type\b)/m.test(s) && !/\brequire\(/.test(s), 'a runtime import in subscriptionSession.ts');
  const i = s.indexOf('export function purchasesIdentityTarget');
  const fn = s.slice(i, s.indexOf('\n}', i));
  eq((fn.match(/=== 'verified'/g) || []).length, 1, 'the target\'s verified comparison');
  assert(!/demo/.test(fn), 'the target names demo itself (the exclusion must be the one comparison)');
});

// useSession, loaded for real: its identity bridge against the REAL
// api/purchases.ts on a fake RevenueCat SDK, with a spy on initPurchases.
function makeRcSdk() {
  return {
    calls: [],
    appUserId: null,
    configure({ appUserID }) { this.calls.push(['configure', appUserID]); this.appUserId = appUserID; },
    async logIn(id) { this.calls.push(['logIn', id]); this.appUserId = id; return {}; },
    logOut() { throw new Error('logOut must never be called'); },
    async getAppUserID() { return this.appUserId; },
  };
}
function rcHarness({ stored = null } = {}) {
  const sdk10 = makeRcSdk();
  process.env.EXPO_PUBLIC_REVENUECAT_IOS_KEY = 'appl_test';
  const realP = load('api/purchases.ts', { 'react-native-purchases': { default: sdk10 } });
  delete process.env.EXPO_PUBLIC_REVENUECAT_IOS_KEY;
  const initCalls = [];
  const P = { ...realP, initPurchases: (id) => { initCalls.push(id); return realP.initPurchases(id); } };
  const storage = new Map(stored ? [['sleeper_user', JSON.stringify(stored)]] : []);
  const store = load('state/useSession.ts', {
    zustand: { create: makeZustandCreate() },
    '@react-native-async-storage/async-storage': { default: {
      getItem: async (k) => (storage.has(k) ? storage.get(k) : null),
      setItem: async (k, v) => { storage.set(k, v); },
      removeItem: async (k) => { storage.delete(k); },
    } },
    '../api/client': {
      api: { post: async () => ({}) }, ApiError: class ApiError extends Error {},
      clearSessionToken: async () => {}, getSessionRevision: () => 0, getSessionToken: async () => 'tok',
      isCurrentSessionExpiry: () => false, requestAborted: () => new Error('aborted'), runWithDeadline: (fn) => fn(),
      setOnSessionExpired: () => {}, setOnVerificationRequired: () => {},
    },
    '../api/auth': {
      initLeagueSession: async () => {}, refreshVerification: async () => {},
      startDemoSession: async () => ({ user_id: 'demo_user_ab12', league_id: 'demo_league', display_name: 'Demo User', league_name: 'The Demo League' }),
    },
    '../api/winNow': { getSeasonProjections: async () => ({}) },
    './leagueSession': {
      LEAGUE_ATTEMPT_MS: 1000,
      createLeagueSessionLifecycle: () => ({
        invalidate() {}, currentGeneration: () => 0, capture: async () => ({}), ensure: async () => {},
        onSuperseded: () => () => {}, reserveSelectionAuthorization: () => 0,
      }),
    },
    '../api/league': { connectLeague: async () => ({}) },
    '../api/sleeper': { getLeagues: async () => [] },
    '../api/purchases': P,
    './subscriptionSession': subSession,
    '../observability/sentry': { setUser: () => {} },
    './queryClient': { queryClient: { invalidateQueries() {} }, seedLeagueSessionCaches() {} },
    './devicePageStore': { clearDevicePages: async () => {} },
    '../api/rankings': { getActiveScoringFormat: async () => null },
  });
  const S = store.useSession;
  const rc = (kind) => sdk10.calls.filter((c) => c[0] === kind);
  const settle = async () => { for (let i = 0; i < 6; i += 1) await tick(); };
  return { S, sdk: sdk10, P: realP, initCalls, rc, settle };
}
const VERIFIED = { session_verified: true, user_verified: true, enforced: false };
const UNVERIFIED = { session_verified: false, user_verified: true, enforced: false };

check('10e. a typed, UNVERIFIED Sleeper sign-in never reaches configure or logIn (and unknown never does either)', async () => {
  const h = rcHarness();
  await h.S.getState().setUser(sleeperUser('111'));
  await h.settle();
  eq(h.S.getState().verification, null, 'a new user starts unknown');
  h.S.getState().setVerification(UNVERIFIED);
  h.S.getState().setVerification(null);
  await h.settle();
  eq(h.initCalls.length, 0, 'initPurchases calls');
  eq(h.rc('configure').length + h.rc('logIn').length, 0, 'RevenueCat configure/logIn');
  eq(h.P.currentIdentityUserId(), null, 'RevenueCat identity');
  // account_only WITHOUT the acct_ prefix stays unknown too.
  await h.S.getState().setUser({ user_id: '333', username: '', display_name: 'X', avatar_id: null, account_only: true });
  await h.settle();
  eq(h.rc('configure').length + h.rc('logIn').length, 0, 'account_only without acct_');
});
check('10f. a restored session at boot: a Sleeper key waits for verification (then configures once); an acct_ key configures now', async () => {
  const h = rcHarness({ stored: sleeperUser('111') });
  await h.S.getState().bootstrap();
  await h.settle();
  eq(h.S.getState().user.user_id, '111', 'restored');
  eq(h.rc('configure').length, 0, 'configure before session_init answers');
  h.S.getState().setVerification(VERIFIED);
  await h.settle();
  eq(JSON.stringify(h.rc('configure')), JSON.stringify([['configure', '111']]), 'configure once verified');
  eq(h.P.currentIdentityUserId(), '111', 'identity');
  const h2 = rcHarness({ stored: acctUser('acct_9') });
  await h2.S.getState().bootstrap();
  await h2.settle();
  eq(JSON.stringify(h2.rc('configure')), JSON.stringify([['configure', 'acct_9']]), 'acct_ configures at boot');
});
check('10g. an Apple-first sign-in logs in at once; unknown → setVerification(true) logs in ONCE, then; repeats add nothing', async () => {
  const h = rcHarness({ stored: acctUser('acct_9') });
  await h.S.getState().bootstrap();
  await h.settle();
  await h.S.getState().setUser(acctUser('acct_7'));
  await h.settle();
  eq(JSON.stringify(h.rc('logIn')), JSON.stringify([['logIn', 'acct_7']]), 'Apple-first: logIn once');
  await h.S.getState().setUser(sleeperUser('222'));
  await h.settle();
  eq(h.rc('logIn').length, 1, 'a typed sign-in adds no logIn while unknown');
  eq(h.P.currentIdentityUserId(), 'acct_7', 'RevenueCat stays the previous verified user');
  h.S.getState().setVerification(VERIFIED);
  await h.settle();
  h.S.getState().setVerification(VERIFIED);
  await h.settle();
  eq(JSON.stringify(h.rc('logIn')), JSON.stringify([['logIn', 'acct_7'], ['logIn', '222']]), 'logIn for 222 once, when it verified');
  eq(h.P.currentIdentityUserId(), '222', 'identity');
  eq(h.rc('configure').length, 1, 'configured once per launch');
});
check('10h. demo (strict): no configure on a fresh SDK, even with a verified answer', async () => {
  const h = rcHarness();
  await h.S.getState().startDemoSession();
  h.S.getState().setVerification(VERIFIED);
  await h.settle();
  eq(h.S.getState().isDemo, true, 'demo');
  eq(h.rc('configure').length, 0, 'demo configured RevenueCat');
  eq(h.initCalls.length, 0, 'demo reached initPurchases');
});
check('10h2. demo (strict): no logIn over a verified user, even with a verified answer; no CustomerInfo', async () => {
  const h2 = rcHarness({ stored: acctUser('acct_9') });
  await h2.S.getState().bootstrap();
  await h2.settle();
  await h2.S.getState().startDemoSession();
  h2.S.getState().setVerification(VERIFIED);
  await h2.settle();
  eq(h2.rc('logIn').length, 0, 'demo logged RevenueCat in');
  eq(h2.P.currentIdentityUserId(), 'acct_9', 'RevenueCat stays the verified user');
  eq(subSession.customerInfoApplies(h2.S.getState(), h2.P.currentIdentityUserId()), false, 'demo reads no CustomerInfo');
});
check('10i. verified A → unverified B on one device: RevenueCat stays A and B may not read it', async () => {
  const h = rcHarness({ stored: sleeperUser('A1') });
  await h.S.getState().bootstrap();
  h.S.getState().setVerification(VERIFIED);
  await h.settle();
  eq(h.P.currentIdentityUserId(), 'A1', 'A is RevenueCat');
  await h.S.getState().setUser(sleeperUser('B2'));
  h.S.getState().setVerification(UNVERIFIED);
  await h.settle();
  eq(h.rc('logIn').length, 0, 'B logged RevenueCat in');
  eq(h.sdk.appUserId, 'A1', 'SDK identity');
  eq(subSession.customerInfoApplies(h.S.getState(), h.P.currentIdentityUserId()), false, 'B reads A\'s CustomerInfo');
  assert(!h.P.isIdentityReady('B2'), 'B\'s purchase identity is never ready');
});

// state/useEntitlements — the CustomerInfo listener, loaded for real.
check('10j. the CustomerInfo listener believes a push ONLY for a verified session whose RevenueCat identity is its user; refresh() runs either way', async () => {
  const sess = makeZustandCreate()(() => ({ user: sleeperUser('111'), isDemo: false, verification: V(true), hasToken: true }));
  let rcId = '111';
  let fetches = 0;
  let onReady = null;
  let push = null;
  const ent = load('state/useEntitlements.ts', {
    zustand: { create: makeZustandCreate() },
    '@react-native-async-storage/async-storage': { default: { getItem: async () => null, setItem: async () => {}, removeItem: async () => {} } },
    '../api/billing': { getEntitlements: () => { fetches += 1; return new Promise(() => {}); } },
    '../api/purchases': {
      currentIdentityUserId: () => rcId,
      hasProEntitlement: (info) => !!(info && info.entitlements && info.entitlements.active.pro),
      onCustomerInfoChange: (cb) => { push = cb; return () => {}; },
      setOnPurchasesReady: (fn) => { onReady = fn; },
    },
    './subscriptionSession': subSession,
    './useSession': { useSession: sess },
  });
  ent.initEntitlements();
  await tick();
  assert(onReady, 'the listener rides setOnPurchasesReady');
  onReady();
  assert(push, 'onCustomerInfoChange bound');
  const PRO = { entitlements: { active: { pro: {} } } };
  const cases = [
    ['verified, identity = the session user', { verification: V(true) }, '111', true],
    ['verified, identity = ANOTHER user', { verification: V(true) }, '999', false],
    ['verified, no completed identity', { verification: V(true) }, null, false],
    ['unverified, identity = the session user', { verification: V(false) }, '111', false],
    ['unknown, identity = the session user', { verification: null }, '111', false],
    ['demo, identity = the demo user', { isDemo: true, verification: V(true), user: { user_id: 'demo_user_ab12' } }, 'demo_user_ab12', false],
  ];
  for (const [name, patch, id, believed] of cases) {
    sess.setState({ user: sleeperUser('111'), isDemo: false, verification: V(true), ...patch });
    ent.useEntitlements.setState({ pro: false, optimistic: false });
    rcId = id;
    const f0 = fetches;
    push(PRO);
    eq(ent.useEntitlements.getState().pro, believed, `${name}: pro`);
    eq(fetches, f0 + 1, `${name}: the server is still asked`);
  }
});

// screens/PaywallScreen — mounted under a fake React (hooks as plain calls,
// JSX as element objects), its Restore pressed for real.
function mountPaywall({ state, rcId }) {
  const effects = [];
  const sets = [];
  const React = {
    createElement: (type, props, ...children) => ({ type, props: { ...(props || {}), children } }),
    Fragment: 'Fragment',
    useState: (init) => [typeof init === 'function' ? init() : init, (v) => sets.push(v)],
    useRef: (current) => ({ current }),
    useEffect: (fn) => { effects.push(fn); },
    useCallback: (fn) => fn,
    useMemo: (fn) => fn(),
  };
  const restores = [];
  const verifies = [];
  const nav = { back: 0, canGoBack: () => true, goBack() { this.back += 1; }, navigate() {}, setOptions() {} };
  const timers = [];
  const hook = (sel) => sel(state);
  hook.getState = () => state;
  const gate = load('state/usePaywallGate.ts', {
    zustand: { create: makeZustandCreate() },
    '../api/client': { setOnProRequired: () => {}, setPaywallGateOn: () => {} },
    './useFeatureFlags': { useFeatureFlags: { getState: () => ({ flags: { 'monetize.paywall': true } }) } },
    './subscriptionSession': subSession,
    './useSession': { useSession: hook },
  });
  const tokens = new Proxy({}, { get: () => 1 });
  const js = ts.transpileModule(read('screens/PaywallScreen.tsx'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019, jsx: ts.JsxEmit.React },
    fileName: 'PaywallScreen.tsx',
  }).outputText;
  const stubs = {
    react: { __esModule: true, default: React, ...React },
    'react-native': {
      ActivityIndicator: 'ActivityIndicator', Linking: { openURL() {} }, Pressable: 'Pressable', ScrollView: 'ScrollView',
      StyleSheet: { create: (x) => x }, useWindowDimensions: () => ({ height: 800, width: 400 }), View: 'View',
    },
    'react-native-safe-area-context': { SafeAreaView: 'SafeAreaView' },
    '@tanstack/react-query': { useQuery: () => ({ data: undefined, isLoading: false }) },
    '../components/chalkline/Text': { __esModule: true, default: 'ChalkText' },
    '../components/chalkline': { Button: 'Button', Icon: 'Icon' },
    '../theme/chalkline': { chalk: tokens, flare: tokens, ice: tokens, ink: tokens, radii: tokens, space: tokens },
    '../api/client': { getBaseUrl: () => 'https://api.test' },
    '../api/billing': { getPaywallConfig: async () => ({}) },
    '../api/purchases': {
      checkIntroEligibility: async () => ({}), currentIdentityUserId: () => rcId, getOfferings: async () => null,
      hasProEntitlement: (info) => !!(info && info.entitlements && info.entitlements.active.pro),
      initPurchases: async () => {}, isIdentityReady: () => false, isPaymentPending: () => false,
      isUserCancelled: () => false, onIdentityChange: () => () => {}, purchasePackage: async () => null,
      purchasesReady: () => false,
      restorePurchases: async (id) => { restores.push(id); return { entitlements: { active: { pro: {} } } }; },
    },
    '../state/useEntitlements': { useEntitlements: (sel) => sel({ refresh: async () => {}, noteCustomerInfo: () => {} }) },
    '../state/useFeatureFlags': { useFlag: () => true },
    '../state/useSession': { useSession: hook },
    '../state/subscriptionSession': subSession,
    '../state/usePaywallGate': { isUnverifiedSession: gate.isUnverifiedSession, openVerify: () => { verifies.push(1); } },
    '../api/events': { track: () => {} },
    '../copy/monetization': copy,
  };
  const mod = { exports: {} };
  const req = (name) => {
    if (Object.prototype.hasOwnProperty.call(stubs, name)) return stubs[name];
    throw new Error(`PaywallScreen.tsx gained an unexpected runtime import ("${name}") — stub it here deliberately.`);
  };
  // eslint-disable-next-line no-new-func
  new Function('module', 'exports', 'require', 'setTimeout', 'clearTimeout', js)(
    mod, mod.exports, req, (fn) => { timers.push(fn); return timers.length; }, () => {});
  const tree = mod.exports.default({ navigation: nav, route: { params: { source: 'settings' } } });
  const find = (node, id) => {
    if (!node || typeof node !== 'object') return null;
    if (Array.isArray(node)) {
      for (const n of node) { const f = find(n, id); if (f) return f; }
      return null;
    }
    if (node.props && node.props.testID === id) return node;
    return node.props ? find(node.props.children, id) : null;
  };
  return { tree, find: (id) => find(tree, id), effects, sets, restores, verifies, nav, timers };
}
check('10k. PaywallScreen Restore runs ONLY when customerInfoApplies; otherwise the identity-not-confirmed path (status "error", no new copy)', async () => {
  const ver = { user: sleeperUser('111'), isDemo: false, verification: V(true) };
  const cases = [
    ['verified, identity = the session user', ver, '111', true],
    ['verified, identity = ANOTHER user', ver, '999', false],
    ['verified, no completed identity', ver, null, false],
    ['unknown, identity = the session user', { ...ver, verification: null }, '111', false],
  ];
  for (const [name, state, rcId, runs] of cases) {
    const m = mountPaywall({ state, rcId });
    const btn = m.find('paywall-restore');
    assert(btn, `${name}: Restore rendered`);
    await btn.props.onPress();
    await tick(); await tick();
    eq(m.restores.length, runs ? 1 : 0, `${name}: restorePurchases calls`);
    if (runs) eq(m.restores[0], '111', `${name}: restore for the session user`);
    else {
      assert(m.sets.includes('error') && !m.sets.includes('restore_none') && !m.sets.includes('restore_ok'),
        `${name}: the refusal is the existing error status`);
    }
  }
});
check('10l. demo shows no purchase flow: isUnverifiedSession() is true in demo, the paywall renders nothing and hands off to the VerifySheet, and openPaywall opens the sheet', async () => {
  const demoState = { user: { user_id: 'demo_user_ab12' }, isDemo: true, verification: null };
  const m = mountPaywall({ state: demoState, rcId: 'demo_user_ab12' });
  eq(m.tree, null, 'the paywall rendered in demo');
  for (const fn of m.effects) fn();
  for (const fn of m.timers) fn();
  assert(m.nav.back >= 1, 'the paywall did not dismiss in demo');
  assert(m.verifies.length >= 1, 'the paywall did not open the VerifySheet in demo');
  // The router, executed (§3's instance): demo → the sheet, never the paywall.
  const saved = { ...session };
  try {
    Object.assign(session, { user: { user_id: 'demo_user_ab12' }, isDemo: true, verification: V(true) });
    eq(gateMod.isUnverifiedSession(), true, 'isUnverifiedSession() in demo');
    navCalls.length = 0;
    const r = gateMod.openPaywall({ source: 'settings' });
    eq(navCalls.length, 0, 'openPaywall navigated to the paywall in demo');
    eq(gateMod.usePaywallGate.getState().verifyOpen, true, 'openPaywall in demo: the sheet');
    gateMod.settleVerify('dismissed');
    eq(await r, 'dismissed', 'outcome');
    Object.assign(session, { isDemo: false, verification: null });
    eq(gateMod.isUnverifiedSession(), false, 'unknown is not unverified');
  } finally {
    Object.assign(session, saved);
  }
});

function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (/\.(ts|tsx)$/.test(e.name)) out.push(p);
  }
  return out;
}

// ── Run, in declaration order ─────────────────────────────────────────────
(async () => {
  console.log('check-paywall-gate:');
  for (const t of tests) {
    try {
      await t.fn();
      console.log(`  ✓ ${t.name}`);
    } catch (e) {
      failures++;
      console.log(`  ✗ ${t.name}\n      ${e && e.message ? e.message : e}`);
    }
  }
  console.log(`\ncheck-paywall-gate: ${tests.length - failures} passed, ${failures} failed`);
  process.exit(failures ? 1 : 0);
})();
