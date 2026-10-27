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
// M3 (account surfaces; §9) adds:
//   - Apple's sheet (or a Restore) reached by an unverified session, or a
//     purchase made FOR the user after they verify (D9);
//   - the Founding GMs welcome after the cut-off, twice, after a Restore, or
//     with a countdown or confetti (D10, design §4.1);
//   - Settings › Subscription varying by subscription for an unverified
//     session, or showing a trial state or any date but the join date
//     (R28.9 3f, D10);
//   - the legal Delete line drifting from its verbatim text;
//   - an invitee eyebrow with a raw "{inviter}" / "{league}" in it;
//   - the Home mark or kept-price line shipping early.
// M2 (the deck; §8) adds:
//   - a prefetch, poll or auto-start that opens the paywall under the thumb
//     (the pinned background set, D2);
//   - the offer shown on the optimistic swipe, twice, over the guide, or to
//     an unverified session (D4; scope guard 5);
//   - the P30 end card drifting, or the preview end card growing a second
//     action, a price or a "free" (D5);
//   - a 402 rendered as "Couldn't load more trades", a refresh-failed line,
//     a swipe toast, or Win Now's raw "HTTP 402" (D19, D16 c);
//   - a Send that reaches its confirm step past the paywall (D16).
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
//   - api/trades.ts: the `background` passthrough.
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
function reset() {
  signals = []; sent.length = 0; responses.length = 0; mirrorCalls = 0; handlerReturn = () => undefined;
}
async function rejects(p) {
  try { await p; } catch (e) { return e; }
  throw new Error('expected the call to reject');
}

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
    'components/VerifySheet.tsx': strip(read('components/VerifySheet.tsx')),
  };
  for (const [name, s] of Object.entries(files)) {
    // `\bfounder\b`: the entitlement field, not the FounderWelcome route
    // name the M3 trigger hold names (§9d).
    const hit = s.match(/useEntitlements|getEntitlements|entitlement|\bfounder\b|\.pro\b|\bpro:|\bsources\b|expires_at/i);
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
// M2: the offer trigger's once-per-user memory lives in AsyncStorage.
const storage = new Map();
const storageWrites = [];
const fakeStorage = {
  getItem: async (k) => (storage.has(k) ? storage.get(k) : null),
  setItem: async (k, v) => { storageWrites.push([k, v]); storage.set(k, v); },
};
// M2: the gate listener settles the open search's R2b (the trace is faked
// here; check-trade-first-card-events §10 runs it against the real trace).
let traceOpen = null;
const traceCalls = [];
const gateMod = load('state/usePaywallGate.ts', {
  '@react-native-async-storage/async-storage': { default: fakeStorage },
  './tradeSearchTrace': { openSearchId: () => traceOpen, failFirstCard: (id, reason) => traceCalls.push([id, reason]) },
  '../utils/firstCardEvent': load('utils/firstCardEvent.ts', {}),
  zustand: { create: makeZustandCreate() },
  '../api/client': { setOnProRequired: (fn) => { seamHandler = fn; } },
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

check('3a. installPaywallGate wires the client seam to the router', () => {
  assert(seamHandler === gateMod.handleGateSignal, 'setOnProRequired(handleGateSignal) not called');
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
const copy = load('copy/monetization.ts', {});
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
  // M3 (§9e): Settings' display-only read of the active plan.
  customerInfo: null,
  products: {},
  async getCustomerInfo() { this.calls.push(['customerInfo', this.appUserId]); return this.customerInfo; },
  async getProducts(ids) { this.calls.push(['products', ids.join(',')]); return ids.map((id) => this.products[id]).filter(Boolean); },
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
check('5f. [shape] every user-setting path calls initPurchases (setUser, bootstrap, startDemoSession)', () => {
  const s = strip(read('state/useSession.ts'));
  const body = (name) => {
    const i = s.indexOf(`${name}: async`);
    const j = s.indexOf('\n  },', i);
    return i > 0 && j > i ? s.slice(i, j) : '';
  };
  assert(/if \(u\?\.user_id\) void initPurchases\(u\.user_id\);/.test(body('setUser')), 'setUser');
  assert(/if \(user\?\.user_id\) void initPurchases\(user\.user_id\);/.test(body('bootstrap')), 'bootstrap (hydrate)');
  const demo = body('startDemoSession');
  const setAt = demo.indexOf('set({');
  const sentryAt = demo.indexOf('sentrySetUser({ id: demoUser.user_id });');
  const initAt = demo.indexOf('void initPurchases(demoUser.user_id);');
  assert(setAt > 0 && sentryAt > setAt && initAt > sentryAt,
    'startDemoSession: initPurchases(demoUser.user_id) must come right after sentrySetUser, after set({');
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
check('6d. [shape] an unverified session never sees the paywall (backstop → the sheet, through M3\'s one D9 route)', () => {
  const s = strip(read('screens/PaywallScreen.tsx'));
  assert(/!s\.isDemo && s\.verification\?\.session_verified === false/.test(s), 'unverified read');
  assert(/if \(!paywallOn \|\| unverified\) return null;/.test(s), 'renders nothing while unverified');
  assert(/useEffect\(\(\) => \{\s*if \(!paywallOn \|\| !unverified\) return;\s*verifyFirst\(\);\s*\}, \[paywallOn, unverified, verifyFirst\]\);/.test(s),
    'the backstop opens the VerifySheet through verifyFirst (§9b)');
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

// ═══ 8. M2 — the deck (D2, D4, D5, D16, D19) ═════════════════════════════
// Scope guard items 2 and 5; the background set; the offer trigger; the
// preview end card; no raw error for a gate answer; the Send pre-check; Win
// Now. What runs under node is EXECUTED (the API defaults, the coordinator,
// the offer memory, the Send pre-check, Win Now's error copy); what lives in
// a screen's closures is pinned by shape, and says so ("[shape]").
const crypto = require('crypto');
function astOf(rel) {
  const text = read(rel);
  return { text, sf: ts.createSourceFile(rel, text, ts.ScriptTarget.Latest, true, rel.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS) };
}
function findNodes(root, pred) {
  const out = [];
  (function v(n) { if (pred(n)) out.push(n); ts.forEachChild(n, v); })(root);
  return out;
}
/** One top-level function out of a file, transpiled and evaluated with its
 *  free names supplied: the real code, without the file's other imports. */
function extractFn(rel, name, deps) {
  const { sf } = astOf(rel);
  const node = findNodes(sf, (n) => ts.isFunctionDeclaration(n) && n.name?.text === name)[0];
  if (!node) throw new Error(`${rel}: function ${name} not found`);
  const js = ts.transpileModule(node.getText(sf).replace(/^export\s+/, ''), {
    compilerOptions: { target: ts.ScriptTarget.ES2019 },
  }).outputText;
  const names = Object.keys(deps);
  // eslint-disable-next-line no-new-func
  return new Function(...names, `${js}\nreturn ${name};`)(...names.map((n) => deps[n]));
}
const TRADES = 'screens/TradesScreen.tsx';

check('8a. D2 [executed]: api/trades — a PAGED status call (the P2 prefetch) and a shop pass are background by default; every other call stays user-initiated unless flagged', async () => {
  const calls = [];
  const trades = load('api/trades.ts', {
    './client': {
      api: {
        post: async (p, b, opts) => { calls.push(['post', p, opts]); return { status: 'running', cards: [] }; },
        get: async (p, opts) => { calls.push(['get', p, opts]); return { status: 'running', cards: [] }; },
      },
    },
  });
  const card = { trade_id: 't1', give_player_ids: [], receive_player_ids: [] };
  await trades.getTradeStatus('j', { deck: 'd', cursor: 30 });
  await trades.getTradeStatus('j');
  await trades.getTradeStatus('j', { deck: 'd', cursor: 30 }, { background: false });
  await trades.swipeTrade(card, 'pass', undefined, 'shop');
  await trades.swipeTrade(card, 'like', undefined, 'deck');
  await trades.swipeTrade(card, 'pass');
  eq(calls[0][2] && calls[0][2].background, true, 'a paged status call');
  eq(calls[1][2], undefined, 'an unpaged status call');
  eq(calls[2][2] && calls[2][2].background, false, 'an explicit flag wins');
  eq(calls[3][2] && calls[3][2].background, true, "a 'shop' pass");
  eq(calls[4][2], undefined, 'a deck swipe is user-initiated');
  eq(calls[5][2], undefined, 'a surface-less swipe is user-initiated');
});

// The pinned background set: every `background: true` in mobile/src code is
// here. A new background caller fails 8b until it is added (D2).
const BACKGROUND_SET = [
  ['api/trades.ts', /request: \{ background\?: boolean \} \| undefined = page \? \{ background: true \} : undefined,/,
    "P2's next-page prefetch (TradesScreen.fetchNextPage's paged getTradeStatus)"],
  ['api/trades.ts', /request: \{ background\?: boolean \} \| undefined = surface === 'shop' \? \{ background: true \} : undefined,/,
    "the Shop's held-Undo pass (ShopOffersBody.commitDismiss)"],
  ['state/devicePageStore.ts', /res = await generateTrades\(target\.request, \{\}, \{ background: true \}\);/, 'refreshDevicePage'],
  ['hooks/usePresentationDeck.ts', /void run\(\{ background: true \}\);/, "usePresentationDeck's mount effect"],
  ['hooks/usePresentationDeck.ts', /await getTradeStatus\(job\.job_id, undefined, \{ background: true \}\)/, "usePresentationDeck's poll"],
  [TRADES, /if \(vars\.auto\) \{\s*return generateTrades\(request, vars\.searchId \? \{ searchId: vars\.searchId \} : undefined, \{ background: true \}\);\s*\}/,
    'the first-run auto-start and its silent retry'],
  [TRADES, /await getTradeStatus\(job\.job_id, undefined, \{ background: true \}\)/, "the deck's legacy status poll"],
  ['api/overhaul.ts', /request: \{ background\?: boolean \} = \{ background: true \},/,
    "the active-overhaul probe (TradesScreen's getActiveOverhaul query, every mount)"],
];
check('8b. D2 [shape]: the pinned background set; nothing else in mobile/src is background; the callers the API defaults cover still match them', () => {
  const want = {};
  for (const [rel, re, what] of BACKGROUND_SET) {
    assert(re.test(strip(read(rel))), `${what} (${rel}) lost its background flag`);
    want[rel] = (want[rel] || 0) + 1;
  }
  for (const f of walk(SRC)) {
    const rel = path.relative(SRC, f).split(path.sep).join('/');
    const n = (strip(fs.readFileSync(f, 'utf8')).match(/background: true/g) || []).length;
    eq(n, want[rel] || 0, `\`background: true\` in ${rel} (add a new background caller to BACKGROUND_SET)`);
  }
  const code = strip(read(TRADES));
  assert(/await getTradeStatus\(snap\.job_id, \{ deck: snap\.deck_id, cursor: requested \}\)/.test(code),
    'the prefetch is a paged getTradeStatus call (the default makes it background)');
  assert(/return generateTrades\(request, vars\.searchId \? \{ searchId: vars\.searchId \} : undefined\);/.test(code),
    "a tap's generate stays user-initiated");
  const shopCallers = walk(SRC).filter((f) => /swipeTrade\([^;]*'shop'\)/.test(strip(fs.readFileSync(f, 'utf8'))));
  eq(shopCallers.map((f) => path.basename(f)).join(','), 'ShopOffersBody.tsx', "the only 'shop' pass caller");
  const shop = strip(read('components/ShopOffersBody.tsx'));
  const commit = shop.slice(shop.indexOf('function commitDismiss('), shop.indexOf('function flushPendingDismiss('));
  assert(/swipeTrade\(ideaToCard\(idea, leagueId\), 'pass', signal, 'shop'\)/.test(commit), "…and it is commitDismiss, the Undo window's commit");
  assert(/refresh: run,/.test(strip(read('hooks/usePresentationDeck.ts'))), 'pull-to-refresh stays user-initiated (run with no flag)');
  // D16 (c): Win Now's job poll is the search tap's own continuation: its 402
  // opens the paywall, so it is deliberately NOT background.
  assert(/getWinNowJob = \(jobId: string, signal\?: AbortSignal\) =>\s*api\.get<WinNowJob>\(`\/api\/win-now\/jobs\/\$\{encodeURIComponent\(jobId\)\}`, \{signal\}\);/.test(read('api/winNow.ts')),
    'the Win Now job poll is user-initiated');
});

check('8c. scope guard 5 [executed]: `paywall_offer` sits directly after `guide_step`; the tour hold and a held slot refuse it', () => {
  const coord = load('state/useInterruptCoordinator.ts', {
    react: { useEffect() {}, useRef: (v) => ({ current: v }) },
    zustand: { create: makeZustandCreate() },
    './useFeatureFlags': { useFlag: () => true },
    '../api/events': { track: () => {} },
  });
  const order = Object.entries(coord.SURFACE_PRIORITY).sort((a, b) => a[1] - b[1]).map(([k]) => k);
  eq(order.slice(0, 2).join(','), 'guide_step,paywall_offer', 'priority order');
  eq(coord.SURFACE_PRIORITY.paywall_offer, coord.SURFACE_PRIORITY.guide_step + 1, 'directly after');
  eq(new Set(Object.values(coord.SURFACE_PRIORITY)).size, order.length, 'distinct priorities');
  const store = coord.useInterruptCoordinator;
  store.getState().beginTourHold();
  eq(store.getState().claim('paywall_offer'), false, 'refused during the tour hold');
  store.getState().endTourHold();
  eq(store.getState().claim('guide_step'), true, 'the guide claims');
  eq(store.getState().claim('paywall_offer'), false, 'never over the guide');
  store.getState().release('guide_step');
  eq(store.getState().claim('paywall_offer'), true, 'a free slot grants');
  eq(coord.isInterruptBusy(store.getState()), true, 'and root modals self-defer while it is held');
  store.getState().release('paywall_offer');
});

check('8d. D4 / ux §1 [executed]: the trigger opens Paywall {source} at most ONCE per user (remembered per user); shut until the memory is read; never for an unverified session; resolves once the paywall is gone', async () => {
  let route = 'Trades';
  const listeners = new Set();
  const navs = [];
  const nav = {
    isReady: () => true,
    navigate: (name, params) => { navs.push([name, params]); route = name; listeners.forEach((l) => l()); },
    getCurrentRoute: () => ({ name: route }),
    addListener: (_t, cb) => { listeners.add(cb); return () => listeners.delete(cb); },
    reset() {},
  };
  gateMod.installPaywallGate(nav);
  try {
    session.verification = { session_verified: true };
    eq(gateMod.offerTriggerOpen('u1'), false, 'an unread memory is shut');
    eq(gateMod.openOfferTrigger('first_opinion', 'u1'), null, 'nothing opens before the read');
    await gateMod.hydrateOfferShown('u1');
    eq(gateMod.offerTriggerOpen('u1'), true, 'read, never shown');
    const closed = gateMod.openOfferTrigger('first_opinion', 'u1');
    assert(closed && typeof closed.then === 'function', 'opened');
    eq(JSON.stringify(navs[0]), JSON.stringify(['Paywall', { source: 'first_opinion' }]), 'the trigger variant (no gate, no kind)');
    eq(JSON.stringify(storageWrites[storageWrites.length - 1]), JSON.stringify(['ftf_paywall_offer_shown_u1', '1']), 'remembered under the user');
    eq(gateMod.openOfferTrigger('left_deck', 'u1'), null, 'never twice for the user');
    let resolved = false;
    closed.then(() => { resolved = true; });
    await tick();
    eq(resolved, false, 'held while the paywall is up');
    route = 'Trades';
    listeners.forEach((l) => l());
    await tick();
    eq(resolved, true, 'resolved once it is gone (the caller releases its slot)');
    await gateMod.hydrateOfferShown('u2');
    eq(gateMod.offerTriggerOpen('u2'), true, 'per user, not per device');
    storage.set('ftf_paywall_offer_shown_u3', '1');
    await gateMod.hydrateOfferShown('u3');
    eq(gateMod.offerTriggerOpen('u3'), false, 'a relaunch remembers');
    session.verification = { session_verified: false };
    const seq = gateMod.usePaywallGate.getState().verifySeq;
    eq(gateMod.openOfferTrigger('left_deck', 'u2'), null, 'unverified: no trigger');
    eq(gateMod.usePaywallGate.getState().verifySeq, seq, '…and no VerifySheet from it');
    eq(gateMod.offerTriggerOpen('u2'), true, 'not spent');
  } finally {
    session.verification = null;
    gateMod.installPaywallGate(fakeNav);
  }
});

check('8e. D4 [shape]: first_opinion fires only on the swipe mutation\'s SERVER ACK, after its stale-action guard; left_deck on a tab switch or Back after a card showed; eligible only flag + enforcing + verified + not entitled; it claims the slot', () => {
  const { text, sf } = astOf(TRADES);
  const swipe = findNodes(sf, (n) => ts.isCallExpression(n) && n.expression.getText(sf) === 'useMutation'
    && n.arguments[0] && /swipeTrade\(card, decision, signal, 'deck'\)/.test(n.arguments[0].getText(sf)))[0];
  assert(swipe, 'the swipe mutation');
  const prop = (name) => swipe.arguments[0].properties.find((p) => p.name && p.name.getText(sf) === name);
  assert(/if \(!ctx \|\| !actionCanUpdateScreen\(ctx\.action\)\) return;\s*requestPaywallOffer\('first_opinion'\);/.test(strip(prop('onSuccess').getText(sf))),
    'onSuccess, right after the stale-action guard');
  for (const name of ['mutationFn', 'onMutate', 'onError']) assert(!prop(name).getText(sf).includes('PaywallOffer'), `${name} must not trigger`);
  const code = strip(text);
  eq((code.match(/requestPaywallOffer\('first_opinion'\)/g) || []).length, 1, 'one first_opinion site');
  assert(/navigation\.addListener\('blur', \(\) => \{\s*if \(tabKey\(\) !== ownTab\) requestPaywallOffer\('left_deck'\);/.test(code), 'left_deck on a tab switch');
  assert(/navigation\.addListener\('beforeRemove', \(e: any\) => \{\s*const type = e\?\.data\?\.action\?\.type;\s*if \(type !== 'RESET' && type !== 'REPLACE'\) setTimeout\(\(\) => presentPaywallOffer\('left_deck'\), 0\);/.test(code),
    'left_deck on Back, after the Back applies (never a reset / replace)');
  eq((code.match(/if \(source === 'left_deck' && !offerCardSeenRef\.current\) return/g) || []).length, 2, 'left_deck only after a card showed');
  assert(/const sessionUnverified = !isDemo && verification\?\.session_verified === false;/.test(code)
    && /const offerEligible = paywallOn && payEnforcing && !payEntitled && !sessionUnverified;/.test(code), 'eligibility');
  assert(/if \(!slot\.claim\('paywall_offer'\)\) return false;\s*const closed = openOfferTrigger\(source, uid\);/.test(code), 'claims the slot, then opens');
  assert(/void closed\.then\(\(\) => useInterruptCoordinator\.getState\(\)\.release\('paywall_offer'\)\);/.test(code), 'holds it until the paywall is gone');
  assert(/if \(!offerSource \|\| toast\) return;/.test(code), 'waits for the toast to clear');
  assert(!/navigate\(\s*'Paywall'/.test(code), 'Trades never navigates to Paywall itself');
  assert(/useEffect\(\(\) => \{\s*if \(wasFocusedRef\.current && !navFocused\) failDeckSearch\('abandoned'\);\s*wasFocusedRef\.current = navFocused;/.test(code),
    "trades-eng's R2b abandoned effect is untouched (adj. 2)");
});

// The P30 render (DeckEndCard's final return), byte-for-byte as #363 shipped
// it. trades-eng owns it: a deliberate P30 change updates this hash.
const P30_RETURN_SHA256 = '0367d26a38d5a1958e2c9355c2d5e501e022f971c299cfb7e85dcfeeec3f28dd';
check('8f. D5 [shape]: DeckEndCard\'s preview_end branch (eyebrow, mon.lock.find, ONE Primary) is an if-return BEFORE the byte-for-byte P30 render; mounted only from the 402 end, ahead of the error variants', () => {
  const { sf } = astOf('components/TradeDeckStates.tsx');
  const fn = findNodes(sf, (n) => ts.isFunctionDeclaration(n) && n.name?.text === 'DeckEndCard')[0];
  const sts = fn.body.statements;
  const iff = sts[sts.length - 2];
  const ret = sts[sts.length - 1];
  assert(ts.isIfStatement(iff) && iff.expression.getText(sf) === 'previewEnd' && ts.isReturnStatement(ret), 'if (previewEnd) { return … } then P30');
  eq(crypto.createHash('sha256').update(ret.getText(sf)).digest('hex'), P30_RETURN_SHA256, 'the P30 render is byte-for-byte');
  const branch = iff.getText(sf);
  eq((branch.match(/<Button\b/g) || []).length, 1, 'one action');
  assert(/testID="deck-end-paywall-cta"/.test(branch) && /variant="primary"/.test(branch), 'the Primary, deck-end-paywall-cta');
  assert(/label=\{previewEnd\.verify \? MON\['mon\.verify\.continue'\] : MON\['mon\.pay\.see_plans'\]\}/.test(branch), 'See plans, or Continue');
  assert(/<Text variant="heading">\{MON\['mon\.preview\.page_end'\]\}<\/Text>/.test(branch)
    && /<Text variant="bodySm" style=\{styles\.endBody\}>\{MON\['mon\.lock\.find'\]\}<\/Text>/.test(branch), 'the eyebrow and the line');
  assert(!/onLike|onPass|tally|count|price|\$\d|free/i.test(branch.replace(/MON\['[^']+'\]/g, '')), 'no Like/Pass, count, price or "free"');
  eq(copy.MON['mon.preview.page_end'], "That's the first page.", 'mon.preview.page_end');
  eq(copy.MON['mon.pay.see_plans'], 'See plans', 'mon.pay.see_plans');
  eq(copy.MON['mon.verify.continue'], 'Continue', 'mon.verify.continue');
  eq(copy.MON['mon.lock.find'], 'Finding trades needs a subscription.', 'mon.lock.find');
  const code = strip(read(TRADES));
  const GATE_BRANCH = ') : pagedWithCards && deckGateEnd && (!rawTopCard || showDeckEndCard) ? (';
  const endAt = code.indexOf(GATE_BRANCH);
  const errAt = code.indexOf(') : pagedWithCards && deckEnd ? (');
  assert(endAt > -1 && errAt > endAt, 'the end card precedes the offline / MoreError branch');
  assert(/\) : pagedWithCards && deckGateEnd && \(!rawTopCard \|\| showDeckEndCard\) \? \(\s*<DeckEndCard\s+minHeight=\{topCardH\}\s+previewEnd=\{\{ verify: deckGateEnd\.verify \|\| sessionUnverified, onPress: handleDeckGateEndPress \}\}\s*\/>/.test(code),
    'the mount');
  assert(/void openPaywall\(\{ source: 'preview_end' \}\);/.test(code), 'See plans opens the paywall, source preview_end');
});

check('8f2. trades-eng follow-up 1 [shape]: a 402 end never shows P30 — the gate branch sits AHEAD of `showDeckEndCard` and takes every slot P30 would (only past the last card otherwise); P30\'s own pinned lines unchanged', () => {
  const code = strip(read(TRADES));
  const gateAt = code.indexOf(') : pagedWithCards && deckGateEnd && (!rawTopCard || showDeckEndCard) ? (');
  const p30At = code.indexOf(') : showDeckEndCard ? (');
  const quickAt = code.indexOf('<QuickSetPromptCard');
  assert(quickAt > -1 && gateAt > quickAt && p30At > gateAt, 'QuickSet prompt → the 402 end → P30, in that order');
  eq((code.match(/\) : showDeckEndCard \? \(/g) || []).length, 1, 'one P30 branch');
  assert(/const showDeckEndCard = pagedWithCards && \(endLatched \|\| deckEnd === 'end'\);/.test(code), "trades-eng's showDeckEndCard (4f) is untouched");
});

check('8f3. trades-eng follow-up 2 [shape]: a gate answer at the landing never pushes the deck (a deck the deadline pushed is popped back); an empty pushed deck never sits behind the paywall; every other fork outcome unchanged', () => {
  const code = strip(read(TRADES));
  const fork = code.slice(code.indexOf('function pushWithFirstPage('), code.indexOf('function handleInlineFindATrade('));
  assert(/generateTrades\(request, \{ searchId: fork\.searchId \}\)\s*\.then\(\(snapshot\) => go\(adoptablePage\(snapshot\)\s*\? \{ request, snapshot, validatedAt: Date\.now\(\), deviceKey \}\s*: undefined\)\)\s*\.catch\(\(e\) => \{\s*const gate = gateSignalFor\(e, '\/api\/trades\/generate'\);\s*if \(!gate \|\| gate\.action === 'verify_mismatch'\) throw e;[\s\S]*?\}\)\s*\.catch\(\(\) => go\(\)\);/.test(fork),
    'the gate catch sits between .then and the verbatim .catch(() => go())');
  const gateCatch = fork.slice(fork.indexOf(".catch((e) => {"), fork.indexOf('.catch(() => go());'));
  assert(!/\bgo\(/.test(gateCatch) && !/pushDeck\(/.test(gateCatch), 'the gate path never pushes');
  assert(/const deckPushed = pushed && resultsPushPendingRef\.current;[\s\S]*if \(deckPushed && mountedRef\.current\) popToLanding\(\);\s*pushed = true;/.test(gateCatch),
    'a deck the deadline already pushed is popped back; then nothing else pushes');
  assert(/failFirstCard\(fork\.searchId, gateFailureReason\(gate\)\);/.test(gateCatch), 'R2b paywall / verify from the gate signal');
  // the pushed deck's own 402 (anchored, offline or deadline pushes) pops an empty deck back
  eq((code.match(/if \(isResultsPushed && deckRef\.current\.length === 0\) popToLanding\(\);/g) || []).length, 2, 'generate and fair-sweep 402s on an empty pushed deck pop to the landing');
});

check('8f4. trades-eng follow-up 3 [shape]: deck_buffer_empty does not fire at a gated preview\'s capped end; trades-eng\'s pinned guard line unchanged', () => {
  const code = strip(read(TRADES));
  assert(/if \(!pagedWithCards \|\| !rawTopCard \|\| !job \|\| unseen > 0 \|\| deckFullyDelivered\(job\)\) return;\s*if \(deckGateEndRef\.current\) return;\s*const searchId = deckSearchRef\.current\?\.id \?\? job\.search_id;[\s\S]{0,200}reportDeckBufferEmpty\(searchId/.test(code),
    'the gate end returns before reportDeckBufferEmpty');
});

check('8g. D16 (a) [executed + shape]: the end card\'s Continue → the VerifySheet, chosen by the server\'s verify answer or session_verified alone, never an entitlement', () => {
  const sig = (status, body) => client.gateSignalFor(new client.ApiError(status, body), '/api/trades/status');
  eq(sig(402, { error: 'pro_required', gate: 'preview_used' }).action, 'paywall', '402 preview_used → See plans');
  eq(sig(402, { error: 'pro_required', gate: 'verify_required' }).action, 'verify', '402 verify_required → Continue');
  eq(sig(403, { error: 'verification_required' }).action, 'verify', '403 verification_required → Continue');
  eq(sig(500, { error: 'boom' }), null, 'a 500 is not an end');
  const code = strip(read(TRADES));
  const fnText = (name) => { const at = code.indexOf(`function ${name}(`); return code.slice(at, code.indexOf('\n  }\n', at)); };
  const press = fnText('handleDeckGateEndPress');
  assert(/if \(deckGateEnd\?\.verify \|\| sessionUnverified\) \{\s*void openVerify\(\{ onVerified: resumeDeckPages \}\);\s*return;\s*\}\s*void openPaywall\(\{ source: 'preview_end' \}\);/.test(press),
    'Continue → openVerify (then the pages resume and the server decides); else See plans');
  assert(/const signal = gateSignalFor\(e, '\/api\/trades\/status'\);\s*if \(!signal \|\| signal\.action === 'verify_mismatch'\) return false;\s*setGateEnd\(\{ verify: signal\.action === 'verify', revalidation \}\);/.test(fnText('noteDeckGateEnd')),
    'the end records the server\'s verify answer');
  for (const [name, s] of [['handleDeckGateEndPress', press], ['noteDeckGateEnd', fnText('noteDeckGateEnd')]]) {
    assert(!/payEntitled|payEnforcing|useEntitlements|entitle|\.pro\b/.test(s), `${name} reads an entitlement`);
  }
});

check('8h. D19 [shape]: a 402 never reaches a deck error variant or the swipe toast — each failure path checks the gate before its error write', () => {
  const { text, sf } = astOf(TRADES);
  const code = strip(text);
  const before = (hay, gate, ...writes) => {
    const g = hay.search(gate);
    assert(g > -1, `gate check ${gate}`);
    for (const w of writes) { const at = hay.indexOf(w); assert(at === -1 || at > g, `${w} precedes the gate check`); }
  };
  const mutation = (re) => {
    const m = findNodes(sf, (n) => ts.isCallExpression(n) && n.expression.getText(sf) === 'useMutation' && n.arguments[0] && re.test(n.arguments[0].getText(sf)))[0];
    return strip(m.arguments[0].properties.find((p) => p.name && p.name.getText(sf) === 'onError').getText(sf));
  };
  // a Find a trade (generate): no toast, no deck-failure card, no auto retry
  before(mutation(/return generateTrades\(request/), /if \(e instanceof ApiError && e\.isProRequired\) \{\s*failDeckSearch\(gateFailureReason\(gateSignalFor\(e, '\/api\/trades\/generate'\)\)\);/, 'setToast(', 'setDeckFailure(', "autoGenRef.current = 'retrying'");
  // a swipe: the card is restored FIRST, then no toast
  const swipeErr = mutation(/swipeTrade\(card, decision, signal, 'deck'\)/);
  before(swipeErr, /if \(err instanceof ApiError && err\.isProRequired\) return;/, 'setToast(');
  assert(swipeErr.indexOf('return cur - 1') < swipeErr.search(/err\.isProRequired\) return;/), 'the existing swipe-failure recovery restores the card first');
  // the fair sweep
  const fair = code.slice(code.indexOf('await getFairPackages('), code.indexOf('setFairDeck(false);\n    } finally'));
  before(fair, /if \(e instanceof ApiError && e\.isProRequired\) \{\s*failDeckSearch\(gateFailureReason\(gateSignalFor\(e, '\/api\/trades\/fair-packages'\)\)\);\s*setFairDeck\(false\);[^}]*return;/, 'setDeckFailure(');
  // the legacy poll: no "Network hiccup" toast, no poll_abandoned card
  assert(/\} catch \(e\) \{\s*if \(cancelled\) return;\s*if \(e instanceof ApiError && e\.isProRequired\) \{\s*setJob\(null\);\s*return;\s*\}\s*failures \+= 1;/.test(code), 'the legacy poll');
  // the page path: the deck's terminal state, never MoreError
  const fetchNext = code.slice(code.indexOf('async function fetchNextPage('), code.indexOf('\n  }\n', code.indexOf('async function fetchNextPage(')));
  assert(/if \(deckGateEndRef\.current\) return;/.test(fetchNext), 'no page is asked after the end');
  assert(/\} catch \(e\) \{\s*if \(!mountedRef\.current \|\| pageLoopRef\.current !== loop\) return;\s*if \(noteDeckGateEnd\(e\)\) \{\s*setPagePhase\('idle'\);\s*return;\s*\}\s*loop\.failures \+= 1;/.test(fetchNext),
    'the page fetch: the end, before a failure is counted');
  // the device deck's revalidation: no refresh-failed line (trades-eng's handler stays verbatim behind it)
  assert(/\.catch\(\(e\) => \{\s*if \(mountedRef\.current && seq === deviceRevalidationRef\.current && noteDeckGateEnd\(e, true\)\) \{\s*setDevicePhase\('done'\);\s*return;\s*\}\s*throw e;\s*\}\)\s*\.catch\(\(\) => \{\s*if \(mountedRef\.current && seq === deviceRevalidationRef\.current\) setDevicePhase\('failed'\);/.test(code),
    'the revalidation');
});

check('8i. D16 GRANTED [executed]: the Send pre-check — dark unless flag + enforcing; unverified → the VerifySheet only (whatever the account holds); verified, not entitled → the paywall {gate, send}; after a verify → re-read, then the paywall or the CONFIRM step, never a send', async () => {
  const st = { flag: true, enforcing: true, pro: false, unverified: false, refreshed: 0 };
  const opened = [];
  let onVerified = null;
  const pre = extractFn('components/SendInSleeperButton.tsx', 'sendPreCheck', {
    useFeatureFlags: { getState: () => ({ flags: { 'monetize.paywall': st.flag } }) },
    useEntitlements: { getState: () => ({ enforcing: st.enforcing, pro: st.pro, refresh: async () => { st.refreshed += 1; } }) },
    isUnverifiedSession: () => st.unverified,
    openVerify: (o) => { opened.push('verify'); onVerified = o && o.onVerified; return Promise.resolve('dismissed'); },
    openPaywall: (p) => { opened.push(JSON.stringify(p)); },
  });
  let confirms = 0;
  const confirm = () => { confirms += 1; };
  const SEND = JSON.stringify({ source: 'gate', kind: 'send' });
  st.flag = false; eq(pre(confirm), false, 'flag off: nothing'); st.flag = true;
  st.enforcing = false; eq(pre(confirm), false, 'not enforcing: nothing'); st.enforcing = true;
  st.pro = true; eq(pre(confirm), false, 'entitled: the send goes on'); st.pro = false;
  opened.length = 0;
  eq(pre(confirm), true, 'locked'); eq(opened.join('|'), SEND, 'the send variant, before any confirm');
  st.unverified = true; st.pro = true; opened.length = 0;
  eq(pre(confirm), true, 'unverified stops'); eq(opened.join('|'), 'verify', 'the sheet only, though the account "holds" pro');
  st.unverified = false; st.pro = false; opened.length = 0;
  onVerified(); await tick(); await tick();
  eq(st.refreshed, 1, 're-read after verifying'); eq(opened.join('|'), SEND, 'not entitled → the paywall'); eq(confirms, 0, 'no confirm');
  st.unverified = true; pre(confirm); st.unverified = false; st.pro = true;
  onVerified(); await tick(); await tick();
  eq(confirms, 1, 'entitled → the confirm step, once (it still waits for the user\'s tap)');
});

check('8j. D16 GRANTED [shape]: the pre-check runs first on every Send tap — the router and the MFL/ESPN twins it renders (their confirm is reached through their own tap) — and a verify resumes with `proceed`, the whole unchanged tap (hand-off, link check, the confirm alert), never a propose', () => {
  const tap = (call, deps) => new RegExp(`const onPress = useCallback\\(\\(\\) => \\{\\s*if \\(state !== 'idle'\\) return;\\s*if \\(${call}\\(\\(\\) => \\{ void proceed\\(\\); \\}\\)\\) return;\\s*void proceed\\(\\);\\s*\\}, \\[${deps}\\]\\);`);
  const router = strip(read('components/SendInSleeperButton.tsx'));
  assert(tap('sendPreCheck', 'state, proceed').test(router), 'router: the pre-check, then proceed');
  eq((router.match(/sendPreCheck=\{sendPreCheck\}/g) || []).length, 2, 'the router hands it to both twins');
  const fnSrc = router.slice(router.indexOf('export function sendPreCheck('), router.indexOf('interface Props'));
  assert(!/propose|doPropose|Alert/.test(fnSrc), 'the pre-check itself never sends or confirms');
  const twins = {
    'components/SendInMflButton.tsx': /const proceed = useCallback\(async \(\) => \{\s*haptics\.pickup\(\);\s*if \(!leagueId \|\| !theirUserId\) \{\s*openMfl\(\);\s*return;\s*\}[\s\S]*?await getMflLinkStatus\(\)[\s\S]*?\{ text: 'Sign in', onPress: openSignIn \}/,
    'components/SendInEspnButton.tsx': /const proceed = useCallback\(async \(\) => \{\s*haptics\.pickup\(\);\s*if \(!leagueId \|\| !theirUserId\) \{\s*openEspn\(\);\s*return;\s*\}[\s\S]*?await getEspnLinkStatus\(\)/,
  };
  assert(/const proceed = useCallback\(async \(\) => \{\s*recordGuideReceipt\(GUIDE_RECEIPTS\.sendAttempted\);\s*track\('sleeper_send_attempted'[\s\S]*?openInSleeper\(\);[\s\S]*?await getSleeperLinkStatus\(\)/.test(router),
    'router: proceed is the whole unchanged tap');
  for (const rel of ['components/SendInSleeperButton.tsx', 'components/SendInMflButton.tsx', 'components/SendInEspnButton.tsx']) {
    const s = strip(read(rel));
    if (twins[rel]) {
      assert(tap('sendPreCheck\\?\\.', 'state, sendPreCheck, proceed').test(s), `${rel}: the pre-check, then proceed (never straight to confirmSend)`);
      assert(twins[rel].test(s), `${rel}: proceed is the whole unchanged tap (hand-off, link check, sign-in)`);
      assert(!/from '\.\/SendInSleeperButton'/.test(s), `${rel}: takes it as a prop (no import cycle)`);
    }
    assert(!/sendPreCheck\??\.?\(\(\) => \{ void confirmSend\(\); \}\)/.test(s), `${rel}: no continuation skips to confirmSend`);
    const confirmFn = s.slice(s.indexOf('const confirmSend = useCallback('), s.indexOf('const proceed = useCallback('));
    assert(/\{ text: 'Send', onPress: \(\) => \{ void doPropose\(\); \} \}/.test(confirmFn), `${rel}: confirmSend's alert gates the propose`);
  }
});

check('8k. D16 (c) [executed]: Win Now maps a 402 / verify 403 to no line (the gate opened the paywall or the sheet), never "HTTP 402"; other errors keep their copy', () => {
  const errorCopy = extractFn('screens/WinNowScreen.tsx', 'errorCopy', {});
  const actionErrorCopy = extractFn('screens/WinNowScreen.tsx', 'actionErrorCopy', { ApiError: client.ApiError, errorCopy });
  const E = (status, body) => new client.ApiError(status, body);
  eq(errorCopy(E(402, { error: 'pro_required', gate: 'lapsed' })), 'HTTP 402', '(why: the raw fallback)');
  eq(actionErrorCopy(E(402, { error: 'pro_required', gate: 'lapsed' })), '', '402');
  eq(actionErrorCopy(E(402, { error: 'pro_required', gate: 'verify_required' })), '', '402 verify_required');
  eq(actionErrorCopy(E(403, { error: 'verification_required' })), '', '403');
  eq(actionErrorCopy(E(500, { message: 'Engine busy' })), 'Engine busy', 'other errors keep their copy');
  const s = strip(read('screens/WinNowScreen.tsx'));
  eq((s.match(/setMessage\(actionErrorCopy\(error\)\)/g) || []).length, 4, 'search, job poll, Edit & evaluate, Like/Pass');
  eq((s.match(/setMessage\(errorCopy\(/g) || []).length, 0, 'no action maps through the raw copy');
  assert(!/HTTP 402/.test(s), 'no "HTTP 402" string');
});

check('8l. D16 (c) [shape]: Win Now\'s pre-check is on "Find Win Now trades" only (verify on session_verified, then the server decides); the standings and controls never read it; the Win Now entries are never gated', () => {
  const s = strip(read('screens/WinNowScreen.tsx'));
  assert(/const search = async \(afterVerify\?: unknown\) => \{\s*if \(!canSearch \|\| busy \|\| seasonStale\(baseline\?\.meta\)\) return;\s*if \(afterVerify !== true && findLocked\(\)\) return;\s*const request = begin\(\);/.test(s),
    'the pre-check runs on the tap, before any request');
  assert(/const findLocked = \(\): boolean => \{\s*if \(!paywallOn \|\| !payEnforcing\) return false;\s*if \(isUnverifiedSession\(\)\) \{\s*void openVerify\(\{ onVerified: \(\) => setSearchAfterVerify\(true\) \}\);\s*return true;\s*\}\s*if \(payEntitled\) return false;\s*void openPaywall\(\{ source: 'gate', kind: 'find' \}\);\s*return true;\s*\};/.test(s),
    'unverified → the sheet; verified, not entitled → mon.lock.find');
  eq((s.match(/findLocked\(\)/g) || []).length, 1, 'one call: the search');
  eq((s.match(/\b(paywallOn|payEnforcing|payEntitled)\b/g) || []).length, 6, 'the paywall state is read by the pre-check alone (3 reads + 3 uses)');
  assert(/if \(!searchAfterVerify \|\| !focused \|\| !canSearch \|\| busy\) return;\s*setSearchAfterVerify\(false\);\s*void search\(true\);/.test(s), 'after a verify: the search once, unchecked (D18)');
  assert(/<Action id="win-now\.search" primary label=\{busy \? 'Working…' : 'Find Win Now trades'\} onPress=\{search\} disabled=\{busy \|\| !canSearch\} \/>/.test(s), 'the search control is unchanged');
  for (const [rel, id] of [['screens/LeagueSummaryScreen.tsx', 'league-summary\\.win-now'], [TRADES, 'trades\\.win-now']]) {
    assert(new RegExp(`testID="${id}" accessibilityRole="button" onPress=\\{\\(\\) => navigation\\.navigate\\('WinNow'\\)\\}`).test(strip(read(rel))),
      `${rel}: the entry navigates straight to Win Now`);
  }
  assert(!/usePaywallGate|openPaywall|sendPreCheck|useEntitlements/.test(strip(read('screens/LeagueSummaryScreen.tsx'))), 'League Summary has no paywall code');
});

check('8m. paywall_viewed: M2 opens the paywall with sources first_opinion | left_deck | preview_end, all in the registered closed set', () => {
  const tax = fs.readFileSync(path.join(ROOT, '..', 'backend', 'analytics_taxonomy.py'), 'utf8');
  assert(/first_opinion \| left_deck \| gate \| settings \| preview_end \| unknown/.test(tax), 'the taxonomy comment lists the sources');
  const gate = strip(read('state/usePaywallGate.ts'));
  assert(/export type OfferTriggerSource = 'first_opinion' \| 'left_deck';/.test(gate) && /nav\.navigate\('Paywall', \{ source \}\);/.test(gate), 'the trigger sources');
  assert(/openPaywall\(\{ source: 'preview_end' \}\)/.test(strip(read(TRADES))), 'the end card source');
  eq(copy.headlineFor('left_deck'), "There's a full deck behind this page.", 'the trigger headline');
  assert(copy.offerBodyFor('first_opinion', false) && copy.offerBodyFor('left_deck', true), 'the trigger body');
});

check('8n. head-eng grant (b) [executed]: the active-overhaul probe is background — a 402 of any gate or the verify 403 opens NOTHING and RESOLVES {active:null}; a 500 still throws; getOverhaul / getOffers stay user-initiated', async () => {
  const overhaul = load('api/overhaul.ts', {
    './client': { apiRequest: client.apiRequest, gateSignalFor: client.gateSignalFor },
    './trades': { normalizeTradeCard: (c) => c },
  });
  const gated = [
    [402, { error: 'pro_required', gate: 'preview_used' }],
    [402, { error: 'pro_required', gate: 'lapsed' }],
    [402, { error: 'pro_required', gate: 'verify_required' }],
    [402, { error: 'pro_required' }],
    [403, { error: 'verification_required' }],
  ];
  for (const [status, body] of gated) {
    reset();
    responses.push({ status, body });
    const r = await overhaul.getActiveOverhaul('L1');
    eq(JSON.stringify(r), JSON.stringify({ active: null }), `${status} ${body.gate || body.error}: resolves {active:null}`);
    eq(signals.length, 0, `${status} ${body.gate || body.error}: opens nothing`);
  }
  reset();
  responses.push({ status: 500, body: { error: 'boom' } });
  const e5 = await rejects(overhaul.getActiveOverhaul('L1'));
  eq(e5.status, 500, 'a 500 still throws');
  reset();
  responses.push({ status: 402, body: { error: 'pro_required', gate: 'lapsed' } });
  await rejects(overhaul.getOverhaul('o1'));
  eq(signals.length, 1, 'getOverhaul is user-initiated (tapping in opens the paywall)');
  reset();
  responses.push({ status: 402, body: { error: 'pro_required', gate: 'lapsed' } });
  await rejects(overhaul.getOffers('o1'));
  eq(signals.length, 1, 'getOffers is user-initiated');
  assert(/queryFn: \(\) => getActiveOverhaul\(leagueId!\),/.test(strip(read(TRADES))), "TradesScreen's probe line is untouched (the defaults do it)");
});

check('8o. trades-eng P3 [executed]: the gate listener settles R2b only for a SEARCH route (generate, fair-packages); another find route (an overhaul) never; the client hands the listener the pathname', async () => {
  traceOpen = 's1';
  traceCalls.length = 0;
  const find = { action: 'paywall', gate: 'lapsed', kind: 'find' };
  gateMod.handleGateSignal(find, '/api/overhauls/o1');
  gateMod.handleGateSignal(find, '/api/overhauls/o1/offers');
  gateMod.handleGateSignal(find, '/api/win-now/search');
  gateMod.handleGateSignal(find);
  eq(traceCalls.length, 0, 'no search route, no R2b');
  gateMod.handleGateSignal(find, '/api/trades/generate');
  gateMod.handleGateSignal({ action: 'verify', gate: 'verify_required', kind: 'find' }, '/api/trades/fair-packages');
  eq(JSON.stringify(traceCalls), JSON.stringify([['s1', 'paywall'], ['s1', 'verify']]), 'the search routes settle it');
  traceOpen = null;
  const paths = [];
  client.setOnProRequired((s, p) => { paths.push(p); });
  try {
    reset();
    responses.push({ status: 402, body: { error: 'pro_required', gate: 'lapsed' } });
    await rejects(client.api.post('https://api.test/api/trades/generate?x=1', {}));
    eq(paths[0], '/api/trades/generate', 'the listener gets the pathname');
  } finally {
    client.setOnProRequired((s) => { signals.push(s); return handlerReturn(s); });
  }
});

// ═══ 9. M3 — account surfaces (D9, D10, design §4.1/§5, copy §9.4–9.6) ═══
// What runs under node is EXECUTED: the router's verify-then-return, the
// club window and the once-per-user welcome memory, the copy helpers (the
// status line, the join date, the invitee template), and the purchases
// display read. What lives in a screen's JSX or closures is pinned by
// shape, and says so ("[shape]").
const PAYWALL = 'screens/PaywallScreen.tsx';
const WELCOME = 'screens/FounderWelcomeScreen.tsx';
const SUBS = 'components/SubscriptionSection.tsx';
const ACCOUNT_DATA = 'screens/settings/sections/AccountDataSection.tsx';
const DELETE_LINE = "Deleting your account doesn't cancel an active subscription. To stop future charges, cancel it in your Apple ID settings first.";
/** The body of `const <name> = useCallback(<arrow>, …)` in a file. */
function callbackBody(rel, name) {
  const { sf } = astOf(rel);
  const decl = findNodes(sf, (n) => ts.isVariableDeclaration(n) && n.name.getText(sf) === name
    && n.initializer && ts.isCallExpression(n.initializer) && n.initializer.expression.getText(sf) === 'useCallback')[0];
  if (!decl) throw new Error(`${rel}: useCallback ${name} not found`);
  return { sf, body: decl.initializer.arguments[0].body };
}
/** One top-level function declaration's source text, comments out. */
function fnText(rel, name) {
  const { sf } = astOf(rel);
  const node = findNodes(sf, (n) => ts.isFunctionDeclaration(n) && n.name?.text === name)[0];
  if (!node) throw new Error(`${rel}: function ${name} not found`);
  return strip(node.getText(sf));
}
const NO_ENTITLEMENT = /useEntitlements|getEntitlements|entitlement|\bfounder\b|\.pro\b|\bpro\b|\bsources\b|expires_at|getActivePro/i;

check('9a. D9 [executed]: verifyThenReturn opens the sheet only; on `verified` the SAME paywall comes back (variant + plan) and nothing is bought; Cancel / a new sign-in open nothing more', async () => {
  navCalls.length = 0;
  session.verification = { session_verified: false };
  const back = { source: 'gate', gate: 'preview_used', kind: 'send', plan: 'ftf_pro_monthly' };
  let held = gateMod.verifyThenReturn(back);
  eq(gateMod.usePaywallGate.getState().verifyOpen, true, 'the sheet is up');
  eq(navCalls.length, 0, 'no paywall while unverified');
  session.verification = { session_verified: true };
  gateMod.settleVerify('verified');
  eq(await held, 'verified', 'outcome');
  eq(JSON.stringify(navCalls), JSON.stringify([['Paywall', back]]), 'the same paywall, same plan');
  for (const outcome of ['dismissed', 'signed_in']) {
    navCalls.length = 0;
    session.verification = { session_verified: false };
    held = gateMod.verifyThenReturn(back);
    gateMod.settleVerify(outcome);
    eq(await held, outcome, outcome);
    eq(navCalls.length, 0, `${outcome}: nothing reopens`);
  }
  navCalls.length = 0;
  session.verification = { session_verified: true };
  gateMod.openPaywall({ source: 'settings' });
  eq(JSON.stringify(navCalls[0]), JSON.stringify(['Paywall', { source: 'settings' }]), 'no plan → none passed');
  session.verification = null;
  assert(!NO_ENTITLEMENT.test(fnText('state/usePaywallGate.ts', 'verifyThenReturn')), '[shape] verifyThenReturn reads a subscription field');
});

check('9b. D9 [shape]: the purchase button and Restore check the session FIRST and route an unverified one to the one verify route; Apple\'s sheet / the restore come after; that route reads the session only and pre-selects the plan', () => {
  for (const [name, sdkCall] of [['onPurchase', 'purchasePackage('], ['onRestore', 'restorePurchases(']]) {
    const { sf, body } = callbackBody(PAYWALL, name);
    const first = body.statements[0];
    assert(first && /^if \(isUnverifiedSession\(\)\) \{\s*verifyFirst\(\);\s*return;\s*\}$/.test(strip(first.getText(sf)).trim()),
      `${name}: its FIRST statement must be the unverified check → verifyFirst; return`);
    const text = strip(body.getText(sf));
    assert(text.indexOf(sdkCall) > text.indexOf('verifyFirst();'), `${name}: ${sdkCall} precedes the check`);
  }
  const vf = callbackBody(PAYWALL, 'verifyFirst');
  const route = strip(vf.body.getText(vf.sf));
  assert(/if \(leavingForVerify\.current\) return;\s*leavingForVerify\.current = true;/.test(route), 'once per mount (the backstop and a tap never both pop the stack)');
  assert(/const back = \{\s*source,\s*\.\.\.\(gate \? \{ gate \} : \{\}\),\s*\.\.\.\(kind \? \{ kind \} : \{\}\),\s*\.\.\.\(selectedId \? \{ plan: selectedId \} : \{\}\),\s*\};\s*dismiss\(\);\s*setTimeout\(\(\) => void verifyThenReturn\(back\), 450\);/.test(route),
    'close this modal, then the sheet; on verified the same variant with the selected plan');
  assert(!NO_ENTITLEMENT.test(route), 'the D9 route reads a subscription field');
  assert(!/purchasePackage|restorePurchases/.test(route), 'the D9 route buys or restores');
  const code = strip(read(PAYWALL));
  eq((code.match(/verifyThenReturn\(/g) || []).length, 1, 'one route to the sheet from the paywall');
  assert(!/\bopenVerify\(/.test(code), 'no second path to the sheet');
  assert(/const pick = plans\.find\(\(p\) => p\.product\.product_id === planParam\)\s*\?\? plans\.find\(\(p\) => p\.period === 'annual'\)/.test(code), 'the carried plan is pre-selected');
});

check('9c. D10 [executed]: the welcome only inside the club window (server open AND before closes_at on this clock); once per user, remembered first; unreadable storage never shows it', async () => {
  const open = extractFn(WELCOME, 'clubWindowOpen', {});
  const CUT = '2027-01-01T00:00:00Z';
  const before = Date.parse('2026-12-31T23:59:00Z');
  eq(open({ open: true, closes_at: CUT }, before), true, 'in the window');
  eq(open({ open: true, closes_at: CUT }, Date.parse(CUT)), false, 'at the cut-off');
  eq(open({ open: true, closes_at: CUT }, Date.parse('2027-01-01T00:01:00Z')), false, 'a cached open:true after the cut-off');
  eq(open({ open: false, closes_at: CUT }, before), false, 'server says closed');
  eq(open({ open: true }, before), false, 'no closes_at');
  eq(open({ open: true, closes_at: 'soon' }, before), false, 'unreadable closes_at');
  eq(open(undefined, before), false, 'no club (older server)');
  const store = new Map();
  const writes = [];
  let broken = false;
  const fakeAS = {
    getItem: async (k) => { if (broken) throw new Error('io'); return store.has(k) ? store.get(k) : null; },
    setItem: async (k, v) => { writes.push(k); store.set(k, v); },
  };
  const prefix = (read(WELCOME).match(/const WELCOME_SHOWN_KEY_PREFIX = '([^']+)';/) || [])[1];
  eq(prefix, 'ftf_founder_welcome_shown_', 'the per-user key');
  const claim = extractFn(WELCOME, 'claimFounderWelcome', { AsyncStorage: fakeAS, WELCOME_SHOWN_KEY_PREFIX: prefix });
  eq(await claim('u1'), true, 'first time');
  eq(writes[0], 'ftf_founder_welcome_shown_u1', 'remembered under the user');
  eq(await claim('u1'), false, 'never twice');
  eq(await claim('u2'), true, 'per user, not per device');
  eq(await claim(''), false, 'no user');
  broken = true;
  eq(await claim('u3'), false, 'unreadable storage → no welcome');
});

check('9d. D10 / design §4.1 [shape + executed]: only a SUCCESSFUL purchase opens it (never Restore), replacing the paywall; the §9.5 keys verbatim, the ram\'s `celebrate`, one Primary (founder-welcome-back), a Reduce-Motion-static stagger, title focus; no confetti or countdown; the trigger\'s slot is held through it', async () => {
  const pb = callbackBody(PAYWALL, 'onPurchase');
  const buy = strip(pb.body.getText(pb.sf));
  const at = buy.search(/if \(clubWindowOpen\(config\?\.club, Date\.now\(\)\) && \(await claimFounderWelcome\(userId\)\)\) \{\s*navigation\.replace\('FounderWelcome', \{\s*period: selected\.period,\s*since: activeProFrom\(result\.customerInfo\)\?\.since \?\? new Date\(\)\.toISOString\(\),\s*\}\);\s*return;\s*\}\s*dismiss\(\);/);
  assert(at > -1, 'the window check + the once claim → replace with FounderWelcome, else close');
  assert(at > buy.indexOf("track('paywall_purchase_completed'") && at > buy.indexOf('await purchasePackage('), 'only after Apple\'s sheet succeeded');
  const rb = callbackBody(PAYWALL, 'onRestore');
  assert(!/FounderWelcome|clubWindowOpen|claimFounderWelcome/.test(strip(rb.body.getText(rb.sf))), 'a Restore never welcomes');
  eq((strip(read(PAYWALL)).match(/'FounderWelcome'/g) || []).length, 1, 'one way in');
  eq(copy.MON['mon.club.welcome_title'], 'Welcome, Founding GM.', 'welcome_title');
  eq(copy.welcomeBody('annual'), 'Your plan is at the Founder price: $24.99 a year. Keep this price on your plan while your subscription stays active. From January 1, 2027, new members pay $34.99 a year or $6.99 a month.', 'welcome_body (annual)');
  eq(copy.welcomeBody('monthly'), 'Your plan is at the Founder price: $4.99 a month. Keep this price on your plan while your subscription stays active. From January 1, 2027, new members pay $34.99 a year or $6.99 a month.', 'welcome_body (monthly)');
  eq(copy.MON['mon.club.since'], 'Founding GM since {join date}', 'since');
  eq(copy.MON['mon.club.back'], 'Back to my trades', 'back');
  const w = strip(read(WELCOME));
  assert(/\{MON\['mon\.club\.welcome_title'\]\}/.test(w) && /\{welcomeBody\(period\)\}/.test(w) && /clubSince\(route\?\.params\?\.since\)/.test(w), 'title, body (plan variant), since');
  assert(/<Button testID="founder-welcome-back" label=\{MON\['mon\.club\.back'\]\} onPress=\{back\} \/>/.test(w), 'the one Primary');
  eq((w.match(/<Button\b/g) || []).length, 1, 'one action');
  assert(/navigation\.goBack\(\)/.test(w), 'Back returns to the same card');
  assert(/<RamAvatar pose="celebrate"/.test(w) && fs.existsSync(path.join(ROOT, 'assets/mascot/ram/celebrate@3x.png')), 'the ram\'s celebrate pose');
  assert(/<ChalkText variant="data">\{since\.date\}<\/ChalkText>/.test(w), 'the date in Plex Mono');
  assert(/const ITEMS = 6;/.test(w) && /Animated\.stagger\(\s*40,/.test(w) && /outputRange: \[8, 0\]/.test(w), '≤6 items, 40 ms apart, an 8 px rise');
  assert(/new Animated\.Value\(reduceMotion \? 1 : 0\)/.test(w) && /if \(reduceMotion\) \{\s*items\.forEach\(\(v\) => v\.setValue\(1\)\);\s*return;\s*\}/.test(w), 'static under Reduce Motion');
  assert(/AccessibilityInfo\.setAccessibilityFocus\(node\)/.test(w) && /ref=\{titleRef\}/.test(w), 'VoiceOver starts on the title');
  assert(!/confetti|countdown|days? left|ends? soon|last chance|expires|FeedbackFAB|welcome_tester|kept_home|LinearGradient|BlurView/i.test(w), 'no confetti, countdown, FAB, tester title or kept-price line');
  assert(!/closes_at/.test(w.replace(fnText(WELCOME, 'clubWindowOpen'), '')), 'closes_at is read only to decide, never rendered');
  const nav = strip(read('navigation/RootNav.tsx'));
  eq((nav.match(/name="FounderWelcome"/g) || []).length, 1, 'registered once');
  assert(/name="FounderWelcome"\s*component=\{FounderWelcomeScreen\}\s*options=\{\{ presentation: 'fullScreenModal', headerShown: false, gestureEnabled: false \}\}/.test(nav), 'a full-screen modal (no FAB, #188)');
  // executed: the trigger's interrupt slot is held through the welcome
  let route = 'Trades';
  const listeners = new Set();
  const nav2 = {
    isReady: () => true,
    navigate: (name) => { route = name; listeners.forEach((l) => l()); },
    getCurrentRoute: () => ({ name: route }),
    addListener: (_t, cb) => { listeners.add(cb); return () => listeners.delete(cb); },
    reset() {},
  };
  gateMod.installPaywallGate(nav2);
  try {
    session.verification = { session_verified: true };
    await gateMod.hydrateOfferShown('w1');
    const closed = gateMod.openOfferTrigger('first_opinion', 'w1');
    let resolved = false;
    closed.then(() => { resolved = true; });
    route = 'FounderWelcome'; listeners.forEach((l) => l()); await tick();
    eq(resolved, false, 'held while the welcome is up');
    route = 'Trades'; listeners.forEach((l) => l()); await tick();
    eq(resolved, true, 'released once it is gone');
  } finally {
    session.verification = null;
    gateMod.installPaywallGate(fakeNav);
  }
});

check('9e. design §5 / R28.9 3f [shape + executed]: Settings › Subscription — flag-gated, NOT enforcing-gated; unverified → ONE row (Verify this session first → the sheet), decided with no subscription read; member / Founding GM / non-member rows and their testIDs; no trial state, no date but the join date', async () => {
  const sub = strip(read(SUBS));
  const main = fnText(SUBS, 'SubscriptionSection');
  assert(/const paywallOn = useFlag\('monetize\.paywall'\);/.test(main) && /if \(!paywallOn\) return null;/.test(main), 'self-gated on monetize.paywall');
  assert(!/enforcing/.test(sub), 'never gated on enforcing (Restore stays reachable once the flag is on)');
  assert(/const unverified = useSession\(\(s\) => !s\.isDemo && s\.verification\?\.session_verified === false\);/.test(main), 'the session decides');
  assert(/<View testID="settings-subscription-row">[\s\S]*\{unverified \? <UnverifiedRow \/> : <VerifiedRows \/>\}/.test(main), 'the container, then the branch');
  for (const [name, t] of [['SubscriptionSection', main], ['UnverifiedRow', fnText(SUBS, 'UnverifiedRow')]]) {
    assert(!NO_ENTITLEMENT.test(t), `${name} reads a subscription field`);
  }
  const un = fnText(SUBS, 'UnverifiedRow');
  eq((un.match(/<LinkRow\b/g) || []).length, 1, 'ONE row');
  assert(/title=\{MON\['mon\.verify\.title'\]\}/.test(un) && /onPress=\{\(\) => void openVerify\(\)\}/.test(un), 'Verify this session first → the sheet');
  assert(!/restore|see_plans|sub_status|Manage|club|FOUNDER/i.test(un), 'no Restore, See plans, status or club line');
  eq(copy.MON['mon.verify.title'], 'Verify this session first', 'the row reuses mon.verify.title');
  const ver = fnText(SUBS, 'VerifiedRows');
  assert(/if \(!loaded\) return restoreRows;/.test(ver), 'never guesses before the entitlements answer');
  assert(/if \(!pro\) \{\s*return \(\s*<>\s*<LinkRow\s*testID="settings-subscription-see-plans"\s*title=\{MON\['mon\.pay\.see_plans'\]\}\s*onPress=\{\(\) => void openPaywall\(\{ source: 'settings' \}\)\}\s*\/>\s*\{restoreRows\}/.test(ver),
    'non-member: See plans → the paywall (source settings: it emits paywall_viewed) + Restore');
  assert(/<ManageSubscriptionLink \/>\s*\{restoreRows\}\s*<\/>\s*\);\s*\}$/.test(ver), 'member: Manage + Restore last');
  // The member status block (update 1; §9j pins that it's off for the binary).
  const st = fnText(SUBS, 'MemberStatus');
  assert(/testID="settings-subscription-status"/.test(st) && /\{status\}/.test(st) && /subStatus\(period, price, founder\)/.test(st), 'member: the status line');
  assert(/founder\s*\?\s*FOUNDER_PRICE\[period\]/.test(st), 'a Founding GM\'s line carries the Founder price');
  assert(/testID="settings-subscription-since"[\s\S]*<ChalkText variant="data">\{since\.date\}<\/ChalkText>[\s\S]*\{FOUNDER_TAG\}/.test(st), 'Founding GM since {date} (Plex Mono) with the FounderTag trailing');
  assert(/\{keptSettings\(period\)\}/.test(st) && /\{MON\['mon\.club\.lapse'\]\}/.test(st), 'kept_settings + lapse');
  assert(/const since = founder \? clubSince\(active\?\.since\) : null;/.test(st), 'the club lines are for members of the club only');
  assert(/testID = 'settings-subscription-manage'/.test(sub) && /'https:\/\/apps\.apple\.com\/account\/subscriptions'/.test(sub), 'Manage subscription → Apple\'s page');
  assert(/testID="settings-subscription-restore"/.test(sub), 'Restore');
  const restore = ver.slice(ver.indexOf('const onRestore'), ver.indexOf('const restoreRows'));
  assert(/if \(isUnverifiedSession\(\)\) \{\s*void openVerify\(\);\s*return;\s*\}/.test(restore) && restore.indexOf('isUnverifiedSession') < restore.indexOf('restorePurchases('),
    'Restore checks the session before restoring');
  assert(/track\('paywall_restore', \{ restored \}\)/.test(restore), 'Restore tracks the registered event');
  assert(/useSession\.subscribe\(\(s, prev\) => \{\s*if \(prev\.verification\?\.session_verified === false && s\.verification\?\.session_verified === true\) \{\s*void useEntitlements\.getState\(\)\.refresh\(\);/.test(strip(read('state/useEntitlements.ts'))),
    'a session that turns verified re-reads its (no longer blanked) entitlements');
  assert(!/trial|expir|periodType|latestPurchase|renew|countdown|days? left|ends? soon|closes_at|toLocaleDateString|getMonth|Date\(/i.test(sub),
    'no trial state, no expiry/renewal, no date but the join date (formatted by clubSince)');
  eq(copy.subStatus('annual', '$24.99', true), 'Founding GM · Fleeced Pro Annual · $24.99/year', 'sub_status (member)');
  eq(copy.subStatus('monthly', '$4.99', false), 'Fleeced Pro Monthly · $4.99/month', 'sub_status (non-club)');
  eq(copy.keptSettings('annual'), 'Founder price: $24.99 a year. Keep this price on your plan while your subscription stays active.', 'kept_settings (annual)');
  eq(copy.keptSettings('monthly'), 'Founder price: $4.99 a month. Keep this price on your plan while your subscription stays active.', 'kept_settings (monthly)');
  eq(copy.MON['mon.club.lapse'], 'If you switch plans or your subscription ends, you may lose the Founder price.', 'lapse');
  eq(copy.MON['mon.pay.manage'], 'Manage subscription', 'manage');
  eq(JSON.stringify(copy.FOUNDER_PRICE), JSON.stringify({ annual: '$24.99', monthly: '$4.99' }), 'the Founder prices the legal lines name');
  const since = copy.clubSince('2026-11-06T12:00:00Z');
  eq(`${since.lead} ${since.date}`, 'Founding GM since November 6, 2026', 'since (a join date)');
  eq(copy.clubSince(null), null, 'no date → no line');
  eq(copy.clubSince('not a date'), null, 'an unreadable date → no line');
  eq(copy.periodFromStore('P1Y'), 'annual', 'P1Y');
  eq(copy.periodFromStore('P1M'), 'monthly', 'P1M');
  eq(copy.periodFromStore('P1W'), null, 'P1W');
  // executed: the display read waits for THIS user's identity
  const before = sdk.calls.length;
  eq(await purchases.getActivePro('someone-else'), null, 'identity not this user → nothing');
  assert(!sdk.calls.slice(before).some((c) => c[0] === 'customerInfo'), 'no CustomerInfo read for another identity');
  sdk.customerInfo = { entitlements: { active: { pro: { productIdentifier: 'ftf_pro_annual', originalPurchaseDate: '2026-11-06T12:00:00Z', expirationDate: '2026-12-06T12:00:00Z', periodType: 'TRIAL' } } } };
  sdk.products = { ftf_pro_annual: { identifier: 'ftf_pro_annual', subscriptionPeriod: 'P1Y', priceString: '$24.99' } };
  eq(JSON.stringify(await purchases.getActivePro('u2')),
    JSON.stringify({ productId: 'ftf_pro_annual', since: '2026-11-06T12:00:00Z', period: 'P1Y', priceString: '$24.99' }),
    'the plan, the join date and the price; no expiry or trial field passes through');
  sdk.customerInfo = { entitlements: { active: {} } };
  eq(await purchases.getActivePro('u2'), null, 'no active pro → nothing');
  sdk.customerInfo = null;
  sdk.products = {};
});

check('9f. legal privacy §6 [shape]: the Delete line verbatim, body-sm chalk-dim, ABOVE the Delete account row; Manage subscription beside it; nothing else in AccountDataSection', () => {
  const a = read(ACCOUNT_DATA);
  eq(a.split(DELETE_LINE).length - 1, 1, 'the line, verbatim, once');
  const lineAt = a.indexOf(DELETE_LINE);
  const deleteAt = a.indexOf('accessibilityLabel="Delete account"');
  assert(lineAt > a.indexOf('{exportRow}') && lineAt < deleteAt, 'directly above the Delete account row (after Download my data)');
  assert(/<Text style=\{styles\.rowSub\} testID="settings\.delete-subscription-note">\s*\{"Deleting your account/.test(a), 'in the body-sm row-sub style');
  assert(/rowSub: \{\s*\.\.\.type\.bodySm,/.test(read('screens/settings/styles.ts')) && /bodySm: \{[^}]*color: chalk\.dim,/.test(read('theme/chalkline.ts')), 'row-sub is body-sm chalk-dim');
  const manageAt = a.indexOf('<ManageSubscriptionLink testID="settings.delete-manage-subscription" />');
  assert(manageAt > lineAt && manageAt < deleteAt, 'Manage subscription between the line and Delete account');
  const m = fnText(SUBS, 'ManageSubscriptionLink');
  assert(/const paywallOn = useFlag\('monetize\.paywall'\);\s*if \(!paywallOn\) return null;/.test(m) && !NO_ENTITLEMENT.test(m), 'the link self-gates on the flag and is the same for every session');
  eq((a.match(/SubscriptionSection|ManageSubscriptionLink|#393/g) || []).length, 4, 'the M3 hunk in AccountDataSection is the import, the comment and the mount');
});

check('9g. copy §9.6 [executed + shape]: the invitee eyebrow and board line — trigger variant only, only with BOTH values; never a raw {inviter} / {league}', () => {
  const C = copy.inviteeContext;
  eq(C('jdoe', 'Dynasty Degenerates'), 'jdoe invited you to Dynasty Degenerates.', 'both values');
  for (const [a, b] of [[null, 'L'], ['jdoe', null], ['', 'L'], ['jdoe', '  '], [undefined, undefined]]) {
    eq(C(a, b), null, `missing value ${JSON.stringify([a, b])} → nothing`);
  }
  eq(C('$&x', 'y$1'), '$&x invited you to y$1.', 'values are inserted literally');
  eq(copy.MON['mon.invitee.board'], "Ranking doesn't need a subscription, and your board shapes the trades your leaguemates see.", 'board verbatim');
  const code = strip(read(PAYWALL));
  assert(/const trigger = source === 'first_opinion' \|\| source === 'left_deck';\s*const invitee = trigger \? inviteeContext\(invitedBy, invitedLeagueName\) : null;/.test(code), 'trigger variant only, both values');
  assert(/\{invitee \? \(\s*<ChalkText variant="label" testID="paywall-invitee-context">\s*\{invitee\}\s*<\/ChalkText>\s*\) : null\}\s*<ChalkText variant="display" testID="paywall-headline">/.test(code), 'the eyebrow, directly above the headline');
  assert(/\{body \? \([\s\S]{0,200}\) : null\}\s*\{invitee \? \(\s*<ChalkText variant="bodySm" testID="paywall-invitee-board">\s*\{MON\['mon\.invitee\.board'\]\}/.test(code), 'the board line, under the body');
  for (const f of walk(SRC)) {
    const rel = path.relative(SRC, f).split(path.sep).join('/');
    let t = strip(fs.readFileSync(f, 'utf8'));
    if (rel === 'copy/monetization.ts') {
      t = t.replace("'mon.invitee.context': '{inviter} invited you to {league}.',", '')
        .replace("MON['mon.invitee.context'].replace('{inviter}', () => who).replace('{league}', () => where)", '');
    }
    // `${league}` is a JS interpolation, not the template's placeholder.
    assert(!/mon\.invitee\.context|(^|[^$])\{(inviter|league)\}/.test(t), `${rel}: the raw template or a raw placeholder`);
  }
});

check('9h. not in this build: the Home mark (mon.club.mark_a11y), the kept-price Home line (mon.club.kept_home), the tester title; the FounderTag only on the paywall, the welcome and Settings', () => {
  const allowed = new Set([PAYWALL, WELCOME, SUBS, 'copy/monetization.ts']);
  for (const f of walk(SRC)) {
    const t = strip(fs.readFileSync(f, 'utf8'));
    const rel = path.relative(SRC, f).split(path.sep).join('/');
    assert(!/mark_a11y|kept_home|welcome_tester|You kept the Founder price|New members now pay/.test(t), `${rel}: a later-update line`);
    if (!allowed.has(rel)) assert(!/FOUNDER_TAG|FOUNDING GM/.test(t), `${rel}: the FounderTag outside the paywall, welcome and Settings`);
  }
  for (const k of ['mon.club.kept_home', 'mon.club.mark_a11y', 'mon.club.welcome_tester']) assert(!(k in copy.MON), `${k} in the copy module`);
});

check('9i. B8 #1 [executed]: the Settings tip row is data-driven — shown only when the cached config offers tips; unknown / empty → hidden; read from the cache, never fetched', () => {
  const offered = extractFn(SUBS, 'tipsOffered', {});
  eq(offered(undefined), false, 'unknown config → hidden');
  eq(offered({ enabled: false }), false, 'paywall off (no tips key) → hidden');
  eq(offered({ enabled: true, tips: [] }), false, 'tips: [] (launch) → hidden');
  eq(offered({ enabled: true, tips: null }), false, 'malformed → hidden');
  eq(offered({ enabled: true, tips: [{ product_id: 'ftf_tip_199', display_price: '$1.99' }] }), true, 'tips offered → shown');
  let opts = null;
  let cached;
  const hook = extractFn(SUBS, 'useTipsOffered', {
    useQuery: (o) => { opts = o; return { data: cached }; },
    getPaywallConfig: () => { throw new Error('fetched'); },
    tipsOffered: offered,
  });
  cached = undefined; eq(hook(), false, 'hook: nothing cached → hidden');
  cached = { tips: [] }; eq(hook(), false, 'hook: tips: [] → hidden');
  cached = { tips: [{ product_id: 'ftf_tip_499' }] }; eq(hook(), true, 'hook: tips → shown');
  eq(JSON.stringify(opts.queryKey), JSON.stringify(['paywall-config', 'ios']), 'the paywall config cache key');
  eq(opts.enabled, false, 'a subscription that never fetches (the hub\'s rule 1)');
});

check('9j. B8 [shape]: the 11-06 binary ships Settings › Subscription WITHOUT the member status block (STATUS_ROWS_AT_LAUNCH = false), never reads RevenueCat for it, and keeps Restore reachable for every verified session (member, non-member, entitlements still loading)', () => {
  const sub = strip(read(SUBS));
  assert(/export const STATUS_ROWS_AT_LAUNCH: boolean = false;/.test(sub), 'the update-1 switch is OFF');
  const ver = fnText(SUBS, 'VerifiedRows');
  eq((sub.match(/<MemberStatus\b/g) || []).length, 1, 'one mount of the status block');
  assert(/\{STATUS_ROWS_AT_LAUNCH \? <MemberStatus active=\{active\} founder=\{founder\} \/> : null\}/.test(ver), 'the status block renders only behind the switch');
  for (const id of ['settings-subscription-status', 'settings-subscription-since']) {
    assert(!ver.includes(id) && fnText(SUBS, 'MemberStatus').includes(id), `${id} lives only in the switched-off block`);
  }
  assert(!/FOUNDER_TAG|keptSettings|mon\.club\.lapse|subStatus/.test(ver), 'no status line, tag, kept-price or lapse outside the block');
  eq((sub.match(/getActivePro\(/g) || []).length, 1, 'one RevenueCat display read');
  assert(/useEffect\(\(\) => \{\s*if \(!STATUS_ROWS_AT_LAUNCH \|\| !pro \|\| !userId \|\| !idReady\) \{\s*setActive\(null\);\s*return;\s*\}\s*let alive = true;\s*void getActivePro\(userId\)/.test(ver),
    'getActivePro is never called while the switch is off');
  // Restore on every verified path: still loading, non-member, member.
  assert(/if \(!loaded\) return restoreRows;/.test(ver), 'loading → Restore');
  assert(/if \(!pro\) \{\s*return \(\s*<>[\s\S]*?\{restoreRows\}\s*<\/>\s*\);\s*\}/.test(ver), 'non-member → See plans + Restore');
  assert(/<ManageSubscriptionLink \/>\s*\{restoreRows\}\s*<\/>\s*\);\s*\}$/.test(ver), 'member → Manage + Restore');
  assert(/testID="settings-subscription-restore"/.test(ver.slice(ver.indexOf('const restoreRows'), ver.indexOf('if (!loaded)'))), 'restoreRows is the Restore row');
  // A session whose verification isn't known yet (null) is NOT unverified:
  // it gets the verified rows, so Restore stays reachable (B8 #3).
  assert(/const unverified = useSession\(\(s\) => !s\.isDemo && s\.verification\?\.session_verified === false\);/.test(fnText(SUBS, 'SubscriptionSection')),
    'null verification reads as not-unverified (Restore reachable)');
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
