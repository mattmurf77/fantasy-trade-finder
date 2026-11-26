#!/usr/bin/env node
// check-paid-launch — the paid-launch gap closes (2026-11-21; scope
// docs/plans/monetization-launch/paid-launch/scope.md).
//
// WHY THIS EXISTS. With enforcement on, a non-subscriber's gated tap opens
// the paywall from api/client (check-paywall-gate pins that). What this file
// pins is what the SURFACE does next, which no test covered and every one of
// which reads as a bug in a passing app:
//   §1 the three Send buttons showed "Couldn't send — Something went wrong"
//      on top of the paywall (and their own verify alert on top of the
//      VerifySheet);
//   §2 the calculator's ✓ queue showed "Couldn't queue that. Try again.";
//   §3 Shop a player showed "Couldn't sweep the league" + Try again (a loop
//      back into the paywall);
//   §4 the single-pin ideas panel showed the false empty "No defensible
//      packages found";
//   §5 a 402'd query was retried once by the query client, re-opening the
//      paywall right after the user dismissed it;
//   §6 the in-place notice routes from the server's answer + session only,
//      never an entitlement field (R28.9 / D15), with verbatim mon.* copy.
// Every gate check here is null while monetize.paywall is off, so today's
// (dark) behaviour is byte-identical; §0 executes that.
//
// HOW: transpiles and EXECUTES queueCalcTrade.ts, queryClient.ts and
// PaywallGateNotice.tsx (under a fake React) with throwing stubs for any
// unexpected import; the screens' JSX/catch blocks are pinned [shape].
//
// Run: node tests/check-paid-launch.js   (or npm run test:paid-launch)

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

const SRC = path.resolve(__dirname, '..', 'src');
const read = (rel) => fs.readFileSync(path.join(SRC, rel), 'utf8');
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"`])\/\/.*$/gm, '$1');

const tests = [];
function check(name, fn) {
  tests.push({ name, fn });
}
function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}
function eq(a, b, msg) {
  if (JSON.stringify(a) !== JSON.stringify(b)) {
    throw new Error(`${msg}: expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`);
  }
}

function load(rel, stubs) {
  const js = ts.transpileModule(read(rel), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2019,
      jsx: ts.JsxEmit.React,
    },
  }).outputText;
  const mod = { exports: {} };
  const req = (name) => {
    if (Object.prototype.hasOwnProperty.call(stubs, name)) return stubs[name];
    throw new Error(`${rel} gained an unexpected runtime import ("${name}") — stub it here deliberately.`);
  };
  // eslint-disable-next-line no-new-func
  new Function('module', 'exports', 'require', js)(mod, mod.exports, req);
  return mod.exports;
}

// A stand-in for api/client's gateSignalFor with the real contract: null
// while the gate is off; on, a 402 pro_required → paywall (verify on
// gate=verify_required), a 403 verification_required → verify.
let gateOn = true;
function gateSignalFor(err, p) {
  if (!gateOn || !err) return null;
  const kind = /propose|queue|standing-offer|disposition/.test(p) ? 'send' : 'find';
  if (err.status === 402 && err.body && err.body.error === 'pro_required') {
    return err.body.gate === 'verify_required'
      ? { action: 'verify', gate: err.body.gate, kind }
      : { action: 'paywall', gate: err.body.gate || null, kind };
  }
  if (err.status === 403 && err.body && err.body.error === 'verification_required') {
    return { action: 'verify', gate: null, kind };
  }
  return null;
}
const e402 = (gate = 'lapsed') => ({ status: 402, body: { error: 'pro_required', gate }, message: 'pro_required' });
const e500 = () => ({ status: 500, body: { error: 'server_error' }, message: 'server_error' });

// ═══ §2 queueCalcTrade, executed ═══════════════════════════════════════════
const tracked = [];
let queueAnswer = null; // {resolve: value} | {reject: err}
const queueMod = load('utils/queueCalcTrade.ts', {
  '../api/client': { gateSignalFor },
  '../api/events': { track: (...a) => tracked.push(a) },
  '../api/trades': {
    queueTradeForOpponent: async () => {
      if (queueAnswer.reject) throw queueAnswer.reject;
      return queueAnswer.resolve;
    },
  },
  './haptics': { haptics: { success() {}, warning() {} } },
  '../state/matchesLists': { refreshMatchesLists: async () => {} },
});
const queueArgs = {
  leagueId: 'L1', opponent: { userId: 'u2', name: 'bob' }, giveIds: ['1'], receiveIds: ['2'], screen: 'Trades',
};

check('0a. gate OFF [executed]: a 402 on the ✓ queue keeps today\'s error toast exactly', async () => {
  gateOn = false;
  queueAnswer = { reject: e402() };
  const r = await queueMod.queueCalcTrade(queueArgs);
  gateOn = true;
  eq(r.toast, { msg: "Couldn't queue that. Try again.", tone: 'error' }, 'flag-off toast');
});

check('2a. gate ON [executed]: a 402 on the ✓ queue returns NO toast (the paywall is the answer)', async () => {
  queueAnswer = { reject: e402() };
  const r = await queueMod.queueCalcTrade(queueArgs);
  eq(r.queued, false, 'not queued');
  eq(r.toast, null, 'no toast over the paywall');
});

check('2b. gate ON [executed]: the verify 403 also returns no toast (the VerifySheet is the answer)', async () => {
  queueAnswer = { reject: { status: 403, body: { error: 'verification_required' } } };
  const r = await queueMod.queueCalcTrade(queueArgs);
  eq(r.toast, null, 'no toast over the sheet');
});

check('2c. gate ON [executed]: a non-gate failure and a refusal keep their honest lines', async () => {
  queueAnswer = { reject: e500() };
  let r = await queueMod.queueCalcTrade(queueArgs);
  eq(r.toast, { msg: "Couldn't queue that. Try again.", tone: 'error' }, '500 toast');
  queueAnswer = { resolve: { queued: false, reason: 'opponent_untouchable' } };
  r = await queueMod.queueCalcTrade(queueArgs);
  eq(r.toast && r.toast.tone, 'warn', 'refusal tone');
  queueAnswer = { resolve: { queued: true } };
  r = await queueMod.queueCalcTrade(queueArgs);
  eq(r.toast && r.toast.tone, 'success', 'success tone');
});

check('2d. the calc_trade_queued row is unchanged on a 402 (no analytics change)', async () => {
  tracked.length = 0;
  queueAnswer = { reject: e402() };
  await queueMod.queueCalcTrade(queueArgs);
  eq(tracked.length, 1, 'one row');
  eq(tracked[0][0], 'calc_trade_queued', 'event');
  eq(tracked[0][1], { queued: false, reason: 'error' }, 'props');
});

// ═══ §5 retryUnlessGated, executed ═════════════════════════════════════════
let qcOptions = null;
const qc = load('state/queryClient.ts', {
  '@tanstack/react-query': { QueryClient: function QueryClient(o) { qcOptions = o; } },
});

check('5a. [executed] the query client never retries a 402 pro_required; everything else keeps ONE retry', () => {
  eq(qcOptions.defaultOptions.queries.retry, qc.retryUnlessGated, 'the default retry is the predicate');
  eq(qc.retryUnlessGated(0, e402()), false, '402 first failure');
  eq(qc.retryUnlessGated(0, e402('verify_required')), false, '402 verify_required');
  eq(qc.retryUnlessGated(0, e500()), true, '500 first failure retries');
  eq(qc.retryUnlessGated(1, e500()), false, '500 second failure stops');
  eq(qc.retryUnlessGated(0, new Error('network')), true, 'network retries once');
  eq(qc.retryUnlessGated(0, null), true, 'unknown retries once');
  eq(qcOptions.defaultOptions.mutations.retry, 0, 'mutations unchanged');
});

// ═══ §6 PaywallGateNotice, executed under a fake React ═════════════════════
const opened = [];
let unverified = false;
const h = (type, props, ...children) => ({ type, props: props || {}, children });
const MON = load('copy/monetization.ts', {
  '../utils/supportContact': load('utils/supportContact.ts', {}),
}).MON;
const notice = load('components/PaywallGateNotice.tsx', {
  react: { __esModule: true, default: { createElement: h }, createElement: h },
  'react-native': { StyleSheet: { create: (s) => s }, View: 'View' },
  '../api/client': { gateSignalFor },
  '../copy/monetization': { MON },
  '../state/usePaywallGate': {
    isUnverifiedSession: () => unverified,
    openPaywall: (p) => opened.push(['paywall', p]),
    openVerify: (o) => opened.push(['verify', !!(o && o.onVerified)]),
  },
  '../theme/chalkline': { space: { sm: 8 } },
  '../utils/haptics': { haptics: { selection() {} } },
  './chalkline/Button': { __esModule: true, default: 'Button' },
  './chalkline/Text': { __esModule: true, default: 'Text' },
});
function findButton(tree) {
  if (!tree || typeof tree !== 'object') return null;
  if (tree.type === 'Button') return tree;
  for (const c of tree.children || []) {
    const b = findButton(c);
    if (b) return b;
  }
  return null;
}
function textOf(tree) {
  if (typeof tree === 'string') return tree;
  if (!tree || typeof tree !== 'object') return '';
  return (tree.children || []).map(textOf).join('');
}

check('6a. [executed] gateNoticeFor: null while the gate is off and for non-gate errors; the server\'s answer otherwise', () => {
  gateOn = false;
  eq(notice.gateNoticeFor(e402(), '/api/trades/asset-ideas'), null, 'flag off');
  gateOn = true;
  eq(notice.gateNoticeFor(e500(), '/api/trades/asset-ideas'), null, '500');
  eq(notice.gateNoticeFor(e402('lapsed'), '/api/trades/asset-ideas'), { verify: false, gate: 'lapsed', kind: 'find' }, 'lapsed');
  eq(notice.gateNoticeFor(e402('verify_required'), '/api/trades/asset-ideas'), { verify: true, gate: 'verify_required', kind: 'find' }, 'verify');
});

check('6b. [executed] a paywall notice: mon.lock.find + "See plans" → openPaywall {source:gate, kind, gate}', () => {
  opened.length = 0;
  unverified = false;
  const tree = notice.default({ notice: { verify: false, gate: 'never_trialed', kind: 'find' }, testID: 't' });
  assert(textOf(tree).includes(MON['mon.lock.find']), 'the lock line');
  const b = findButton(tree);
  eq(b.props.label, MON['mon.pay.see_plans'], 'label');
  eq(b.props.testID, 't-cta', 'testID');
  b.props.onPress();
  eq(opened, [['paywall', { source: 'gate', kind: 'find', gate: 'never_trialed' }]], 'opened the paywall');
});

check('6c. [executed] a verify answer, or an unverified session, gets "Continue" → the VerifySheet, never the paywall', () => {
  opened.length = 0;
  unverified = false;
  let b = findButton(notice.default({ notice: { verify: true, gate: 'verify_required', kind: 'find' }, testID: 't', onVerified() {} }));
  eq(b.props.label, MON['mon.verify.continue'], 'verify label');
  b.props.onPress();
  unverified = true;
  b = findButton(notice.default({ notice: { verify: false, gate: 'lapsed', kind: 'find' }, testID: 't' }));
  eq(b.props.label, MON['mon.verify.continue'], 'unverified label');
  b.props.onPress();
  unverified = false;
  eq(opened, [['verify', true], ['verify', false]], 'both opened the sheet');
});

check('6d. [shape] the notice reads no entitlement field and renders only mon.* copy', () => {
  const src = strip(read('components/PaywallGateNotice.tsx'));
  assert(!/useEntitlements|\.pro\b|enforcing|expires_at|founder/.test(src), 'an entitlement read');
  const literals = src.match(/'[^'\n]*'/g) || [];
  const visible = literals.filter((l) => /[A-Z][a-z]+ [a-z]/.test(l));
  eq(visible, [], 'hard-coded user-visible strings');
});

// ═══ §1 the Send buttons [shape] ═══════════════════════════════════════════
function catchBody(src, marker) {
  const at = src.indexOf(marker);
  assert(at >= 0, `catch marker not found: ${marker}`);
  return src.slice(at, at + 6000);
}

check('1a. [shape] every Send button checks gateSignalFor on its own route BEFORE any Alert in its catch', () => {
  for (const [file, route, marker] of [
    ['components/SendInSleeperButton.tsx', '/api/trades/propose', "track('sleeper_send_failed'"],
    ['components/SendInMflButton.tsx', '/api/trades/propose-mfl', 'settleSend(sendKey, isSendOutcomeUnknown(err)'],
    ['components/SendInEspnButton.tsx', '/api/trades/propose-espn', 'settleSend(sendKey, isSendOutcomeUnknown(err)'],
  ]) {
    const body = catchBody(strip(read(file)), marker);
    const gate = body.indexOf(`gateSignalFor(err, '${route}')`);
    assert(gate >= 0, `${file}: no gate check on ${route}`);
    // Only the outcome-unknown branch may come first (check-send-timeout D
    // pins it first; a gate answer is never an unknown outcome). Every
    // other alert, the generic "Couldn't send" and the button's own verify
    // alert included, must come after the gate check.
    const unknown = body.indexOf('if (isSendOutcomeUnknown(err)) {');
    const firstAlert = body.indexOf('Alert.alert(');
    if (unknown >= 0) {
      assert(unknown < gate && body.indexOf('SEND_OUTCOME_UNKNOWN_TITLE') < gate, `${file}: outcome-unknown first`);
      assert(body.indexOf('Alert.alert(', body.indexOf('SEND_OUTCOME_UNKNOWN_TITLE') + 1) > gate,
        `${file}: a second Alert precedes the gate check`);
    } else {
      assert(firstAlert < 0 || gate < firstAlert, `${file}: an Alert precedes the gate check`);
    }
    for (const later of ['Something went wrong sending', "'Verify your account'"]) {
      const at = body.indexOf(later);
      assert(at < 0 || gate < at, `${file}: "${later}" precedes the gate check`);
    }
    assert(/import \{[^}]*\bgateSignalFor\b[^}]*\} from '\.\.\/api\/client'/.test(read(file)), `${file}: import`);
  }
});

check('1b. [shape] the Sleeper button still returns to idle before the gate check (never stuck "Sending…")', () => {
  const body = catchBody(strip(read('components/SendInSleeperButton.tsx')), "track('sleeper_send_failed'");
  assert(body.indexOf("setState('idle')") >= 0
    && body.indexOf("setState('idle')") < body.indexOf("gateSignalFor(err, '/api/trades/propose')"), 'idle first');
});

check('1c. [shape] the send pre-check still runs first on the tap (unchanged)', () => {
  const src = strip(read('components/SendInSleeperButton.tsx'));
  // League pass (D-281) adds the button's league as the second parameter
  // (check-league-pass 6a / 7a pin what it does with it).
  assert(/export function sendPreCheck\(resume: \(\) => void(, leagueId\?: string)?(, afterAsk = false)?\): boolean/.test(src), 'sendPreCheck');
  for (const f of ['components/SendInMflButton.tsx', 'components/SendInEspnButton.tsx']) {
    assert(/preCheck\??\.?\(/.test(strip(read(f))) || /sendPreCheck/.test(strip(read(f))), `${f}: pre-check call`);
  }
});

// ═══ §3 / §4 Shop and the single-pin panel [shape] ═════════════════════════
check('3a. [shape] Shop: a gate answer renders the notice AHEAD of the generic "Couldn\'t sweep the league"', () => {
  const src = strip(read('components/ShopOffersBody.tsx'));
  const gated = src.indexOf("gateNoticeFor(ideasQuery.error, '/api/trades/asset-ideas')");
  const generic = src.indexOf('testID="shop.error"');
  assert(gated >= 0 && generic >= 0 && gated < generic, 'order');
  assert(/<PaywallGateNotice[\s\S]{0,80}testID="shop\.gated"/.test(src), 'the notice testID');
});

check('4a. [shape] the single-pin panel: a gated sweep renders the notice before the "No defensible packages" empty', () => {
  const src = strip(read('components/AssetIdeasPanel.tsx'));
  const gated = src.indexOf('gated && !groups ?');
  const empty = src.indexOf('No defensible packages');
  assert(gated >= 0 && empty >= 0 && gated < empty, 'order');
  const host = strip(read('screens/TradesScreen.tsx'));
  assert(/gated=\{assetIdeasQuery\.isError \? gateNoticeFor\(assetIdeasQuery\.error, '\/api\/trades\/asset-ideas'\) : null\}/.test(host),
    'TradesScreen passes the gate answer');
});

check('4b. [shape] no locked-feature card (R28.8 #5): the notice is mounted only on an error branch, never pre-tap', () => {
  for (const f of ['components/ShopOffersBody.tsx', 'components/AssetIdeasPanel.tsx']) {
    const src = strip(read(f));
    const mounts = src.split('<PaywallGateNotice').length - 1;
    eq(mounts, 1, `${f}: one mount`);
  }
  const shop = strip(read('components/ShopOffersBody.tsx'));
  assert(/ideasQuery\.isError && gateNoticeFor/.test(shop), 'shop mount is behind isError');
  const host = strip(read('screens/TradesScreen.tsx'));
  assert(/assetIdeasQuery\.isError \? gateNoticeFor/.test(host), 'panel input is behind isError');
});

check('7a. [shape] a purchase/Restore while a notice shows sweeps again (Shop and the panel refetch on pro), no routing read', () => {
  const shop = strip(read('components/ShopOffersBody.tsx'));
  // League pass (D-281): entitled = Pro, or a pass covering Shop's league
  // (check-league-pass 7a pins the league).
  assert(/const entitled = useProForLeague\(leagueId\);\s*useEffect\(\(\) => \{\s*if \(entitled && ideasQuery\.isError\) void ideasQuery\.refetch\(\);/.test(shop),
    'Shop refetches on pro');
  const host = strip(read('screens/TradesScreen.tsx'));
  assert(/if \(payEntitled && assetIdeasQuery\.isError\) void assetIdeasQuery\.refetch\(\);\s*\}, \[payEntitled\]\);/.test(host),
    'TradesScreen refetches the panel on pro');
});

// ── Run ────────────────────────────────────────────────────────────────────
(async () => {
  let failed = 0;
  for (const t of tests) {
    try {
      await t.fn();
      console.log(`  ✓ ${t.name}`);
    } catch (e) {
      failed += 1;
      console.log(`  ✗ ${t.name}\n      ${e.message}`);
    }
  }
  console.log(`\ncheck-paid-launch: ${tests.length - failed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
