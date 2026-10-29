#!/usr/bin/env node
// check-send-registry.js — the ESPN/MFL send registry (#527 QA P2-A, 2026-10-29).
//
// A send's state used to live only in the button's useState, and ESPN/MFL
// propose has no cross-request idempotency. With the wait at up to 91 s, a
// remount showed an idle Send while the first request was still going, and an
// unknown outcome left no reminder in the confirm dialog. This suite executes
// the real api/sendRegistry.ts and the real SendInEspnButton / SendInMflButton
// (transpiled, run under a minimal hooks shim with a fake Alert and a scripted
// propose), plus the real api/client.ts ApiError, api/sendOutcome.ts and
// utils/sendOutcomeCopy.ts:
//
//   R1. The key: order-insensitive; platform / league / counterparty scoped;
//       picks count; two different trades never collide; the buttons key on
//       the same identifiers the propose payload carries.
//   R2. in_flight is set synchronously, before the request; a second send of
//       the same trade while in flight is refused with no request; a stale
//       queued dialog never sends once the trade's state has moved on.
//   R3. A remount reads the registry: "Sending…", disabled, inert.
//   R4. Exactly one result alert after a remount, from the call that sent.
//   R5. Unknown → the confirm dialog starts with 8e/8f word for word; success
//       is recorded as sent; a definitive not-sent answer clears the entry.
//   R6. Bounded, in memory, no imports.
//
// Dependency-free beyond the TypeScript compiler the mobile app already has.
// FTF_MOBILE_TEST_ROOT selects another mobile/ tree.
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
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');

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
const flush = async () => { for (let n = 0; n < 50; n++) await Promise.resolve(); };

function load(rel, requireShim, extra = {}) {
  const out = ts.transpileModule(read(rel), {
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React},
  }).outputText;
  const module = {exports: {}};
  vm.runInNewContext(out, {module, exports: module.exports, require: requireShim, console, ...extra}, {filename: rel});
  return module.exports;
}
const only = (map) => (n) => {
  if (!(n in map)) throw new Error(`unexpected import ${n}`);
  return map[n];
};

// ── A minimal hooks renderer: enough to run a function component, keep its
//    hook state across renders, and remount it with fresh state. ───────────
function hooks() {
  let cur = null;
  let idx = 0;
  const slot = (init) => {
    const i = idx++;
    if (!(i in cur.slots)) cur.slots[i] = init();
    return cur.slots[i];
  };
  const React = {
    Fragment: 'Fragment',
    createElement: (type, props, ...children) => ({type, props: {...(props || {}), children}}),
    useState(init) {
      const inst = cur;
      const box = slot(() => ({v: typeof init === 'function' ? init() : init}));
      return [box.v, (v) => { box.v = typeof v === 'function' ? v(box.v) : v; inst.dirty = true; }];
    },
    useRef: (init) => slot(() => ({current: init})),
    useCallback: (fn) => { idx++; return fn; },
    useMemo: (fn) => { idx++; return fn(); },
    useEffect: () => { idx++; },
    useSyncExternalStore(subscribe, getSnapshot) {
      const inst = cur;
      slot(() => ({unsubscribe: subscribe(() => { inst.notified += 1; inst.dirty = true; })}));
      return getSnapshot();
    },
  };
  React.default = React;
  function mount(Component, props) {
    const inst = {slots: {}, props, dirty: false, notified: 0, tree: null, mounted: true};
    inst.render = (next) => {
      if (next) inst.props = next;
      cur = inst; idx = 0;
      try { inst.tree = Component(inst.props); } finally { cur = null; }
      inst.dirty = false;
      return inst;
    };
    inst.unmount = () => {
      inst.mounted = false;
      for (const s of Object.values(inst.slots)) if (s && typeof s.unsubscribe === 'function') s.unsubscribe();
    };
    return inst.render();
  }
  return {React, mount};
}
function findTestId(node, id) {
  if (!node || typeof node !== 'object') return null;
  if (Array.isArray(node)) { for (const c of node) { const f = findTestId(c, id); if (f) return f; } return null; }
  if (node.props && node.props.testID === id) return node;
  return node.props ? findTestId(node.props.children, id) : null;
}

// ── One app run: a fresh registry, the real buttons, a fake Alert and a
//    scripted propose. ──────────────────────────────────────────────────────
const PLATFORMS = {
  ESPN: {
    file: 'src/components/SendInEspnButton.tsx', api: '../api/sendInEspn', propose: 'proposeTradeToEspn',
    status: 'getEspnLinkStatus', testID: 'trades.send-espn-btn', idle: 'Send in ESPN', key: 'espn',
    body: 'This proposes the trade directly in ESPN — your leaguemate gets it as a pending offer (it expires in 48 hours).',
    props: {leagueId: '123', theirUserId: 'espn:123.t2', givePlayerIds: ['4046', '6794'], receivePlayerIds: ['9509'], surface: 'deck'},
  },
  MFL: {
    file: 'src/components/SendInMflButton.tsx', api: '../api/sendInMfl', propose: 'proposeTradeToMfl',
    status: 'getMflLinkStatus', testID: 'trades.send-mfl-btn', idle: 'Send in MFL', key: 'mfl',
    body: 'This proposes the trade directly in MFL — your leaguemate gets it as a pending offer (it expires in 7 days).',
    props: {leagueId: '456', theirUserId: 'mfl:456.f0002', givePlayerIds: ['4046', '456_2027_1_0002'], receivePlayerIds: ['9509'], surface: 'deck'},
  },
};
// Marketing's 8e/8f, word for word (addendum 10; utils/sendOutcomeCopy.ts).
const REMINDER = {
  ESPN: "Couldn't confirm whether this trade reached ESPN. Check your league's pending trades on ESPN before you send it again.",
  MFL: "Couldn't confirm whether this trade reached MFL. Check your league's pending trades on MFL before you send it again.",
};

function appRun() {
  const w = {alerts: [], posts: [], statusCalls: 0, warnings: [], pending: []};
  const {React, mount} = hooks();
  const native = {
    'expo-constants': {default: {expoConfig: {extra: {apiBaseUrl: 'https://example.invalid'}, version: 'test'}}},
    'expo-device': {DeviceType: {TABLET: 2, DESKTOP: 3}},
    'expo-secure-store': {getItemAsync: async () => null, setItemAsync: async () => {}, deleteItemAsync: async () => {}},
    'react-native': {Platform: {OS: 'ios'}, AppState: {addEventListener: () => {}}},
    './events': {track: () => {}},
  };
  const client = load('src/api/client.ts', only(native), {AbortController, DOMException, URL, setTimeout, clearTimeout, fetch: () => new Promise(() => {})});
  const outcome = load('src/api/sendOutcome.ts', only({'./client': client}));
  const copy = load('src/utils/sendOutcomeCopy.ts', only({}));
  const registry = load('src/api/sendRegistry.ts', only({}));
  const propose = (platform) => (payload) => {
    const key = registry.tradeSendKey(platform, payload.league_id, payload.their_user_id, payload.give_player_ids, payload.receive_player_ids);
    w.posts.push({payload, stateAtCall: registry.getSendRecord(key) && registry.getSendRecord(key).state});
    return new Promise((resolve, reject) => w.pending.push({resolve, reject}));
  };
  const status = async () => { w.statusCalls += 1; return {connected: true}; };
  const shared = {
    react: React,
    'react-native': {Alert: {alert: (...a) => w.alerts.push(a)}, Linking: {openURL: async () => {}}},
    '@react-navigation/native': {useNavigation: () => ({navigate: () => {}, addListener: () => () => {}})},
    './chalkline/Button': {default: 'Button'},
    './MflSignInSheet': {default: 'MflSignInSheet'},
    '../utils/haptics': {haptics: {pickup() {}, success() {}}},
    // #379 (build/open-external-helper) moves Open ESPN / Open MFL onto this
    // helper. Harmless before it lands; keeps this suite green after.
    '../utils/openExternal': {openPlatform: async () => {}},
    '../utils/ratingPrompt': {maybeRequestReview: async () => {}},
    '../state/useFeatureFlags': {useFlag: () => true},
    '../api/sendInEspn': {getEspnLinkStatus: status, proposeTradeToEspn: propose('espn')},
    '../api/sendInMfl': {getMflLinkStatus: status, proposeTradeToMfl: propose('mfl')},
    '../api/sendInSleeper': {validateTradeSend: async () => ({warnings: w.warnings})},
    '../api/client': client,
    '../api/sendOutcome': outcome,
    '../api/sendRegistry': registry,
    '../utils/sendOutcomeCopy': copy,
  };
  const buttons = {};
  for (const [p, spec] of Object.entries(PLATFORMS)) buttons[p] = load(spec.file, only(shared)).default;
  Object.assign(w, {client, registry, copy, buttons, mount: (p, props) => mount(buttons[p], {...PLATFORMS[p].props, ...props})});
  return w;
}
const btn = (w, p, inst) => {
  const b = findTestId(inst.tree, PLATFORMS[p].testID);
  if (!b) throw new Error(`no ${PLATFORMS[p].testID} in the render`);
  return b;
};
// Tap Send in ESPN / MFL and return the confirm dialog it opens.
async function openConfirm(w, p, inst) {
  const before = w.alerts.length;
  btn(w, p, inst).props.onPress();
  await flush();
  inst.render();
  expect(w.alerts.length === before + 1, `tapping ${PLATFORMS[p].idle} opened ${w.alerts.length - before} dialogs`);
  return w.alerts[w.alerts.length - 1];
}
const pressAction = (dialog, text) => {
  const a = (dialog[2] || []).find((b) => b.text === text);
  if (!a) throw new Error(`dialog "${dialog[0]}" has no ${text} button`);
  a.onPress();
};
const keyOf = (w, p, props = PLATFORMS[p].props) =>
  w.registry.tradeSendKey(PLATFORMS[p].key, props.leagueId, props.theirUserId, props.givePlayerIds, props.receivePlayerIds);
// A started send: the confirm dialog's Send pressed. Returns the dialog.
async function startSend(w, p, inst) {
  const dialog = await openConfirm(w, p, inst);
  pressAction(dialog, 'Send');
  return dialog;
}

const ANSWERS = (w) => ({
  success: () => w.pending.shift().resolve({status: 'proposed'}),
  timeout: () => w.pending.shift().reject(new w.client.ApiError(0, null, 'Request timed out', true)),
  dropped: () => w.pending.shift().reject(new TypeError('Network request failed')),
  outcome_unknown: (p) => w.pending.shift().reject(new w.client.ApiError(502, {error: `${p.toLowerCase()}_outcome_unknown`, detail: 'x'})),
  internal_error: () => w.pending.shift().reject(new w.client.ApiError(500, {error: 'internal_error'})),
  gateway: () => w.pending.shift().reject(new w.client.ApiError(504, '<html>Gateway Timeout</html>')),
  write_failed: (p) => w.pending.shift().reject(new w.client.ApiError(502, {error: `${p.toLowerCase()}_write_failed`, detail: 'Trades are locked.'})),
  unavailable: (p) => w.pending.shift().reject(new w.client.ApiError(502, {error: `${p.toLowerCase()}_unavailable`, kind: 'network'})),
  auth_expired: (p) => w.pending.shift().reject(new w.client.ApiError(409, {error: `${p.toLowerCase()}_auth_expired`})),
  asset_unmapped: (p) => w.pending.shift().reject(new w.client.ApiError(422, {error: `${p.toLowerCase()}_asset_unmapped`, unmapped: ['1']})),
  feature_disabled: () => w.pending.shift().reject(new w.client.ApiError(404, {error: 'feature_disabled'})),
});
const UNKNOWN = ['timeout', 'dropped', 'outcome_unknown', 'internal_error', 'gateway'];
const NOT_SENT = ['write_failed', 'unavailable', 'auth_expired', 'asset_unmapped', 'feature_disabled'];
const RESULT_TITLE = {success: 'Trade sent', unknown: 'Check before resending'};

// ── AST helpers ─────────────────────────────────────────────────────────────
const parse = (rel) => ts.createSourceFile(rel, read(rel), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
function findAll(node, pred, acc = []) {
  if (pred(node)) acc.push(node);
  ts.forEachChild(node, (c) => { findAll(c, pred, acc); });
  return acc;
}
function arrow(sf, name) {
  const decl = findAll(sf, (n) => ts.isVariableDeclaration(n) && n.name.getText(sf) === name)[0];
  if (!decl) throw new Error(`const ${name} not found`);
  const fn = findAll(decl, (n) => ts.isArrowFunction(n))[0];
  if (!fn) throw new Error(`${name} is not an arrow callback`);
  return fn;
}

(async () => {
  // ════ R1. The key ═══════════════════════════════════════════════════════
  await check('R1a. key: order-insensitive on both sides; platform, league and counterparty scoped; picks count; no collisions', () => {
    const {registry: R} = appRun();
    const k = (p, l, t, g, r) => R.tradeSendKey(p, l, t, g, r);
    const base = k('mfl', '456', 'mfl:456.f0002', ['4046', '456_2027_1_0002'], ['9509', '6794']);
    const bad = [];
    if (k('mfl', '456', 'mfl:456.f0002', ['456_2027_1_0002', '4046'], ['6794', '9509']) !== base) bad.push('reordered assets gave a different key');
    const distinct = {
      'other platform': k('espn', '456', 'mfl:456.f0002', ['4046', '456_2027_1_0002'], ['9509', '6794']),
      'other league': k('mfl', '457', 'mfl:456.f0002', ['4046', '456_2027_1_0002'], ['9509', '6794']),
      'other counterparty': k('mfl', '456', 'mfl:456.f0003', ['4046', '456_2027_1_0002'], ['9509', '6794']),
      'pick dropped': k('mfl', '456', 'mfl:456.f0002', ['4046'], ['9509', '6794']),
      'other pick': k('mfl', '456', 'mfl:456.f0002', ['4046', '456_2028_1_0002'], ['9509', '6794']),
      'player added': k('mfl', '456', 'mfl:456.f0002', ['4046', '456_2027_1_0002', '1'], ['9509', '6794']),
      'sides swapped': k('mfl', '456', 'mfl:456.f0002', ['9509', '6794'], ['4046', '456_2027_1_0002']),
      'asset moved across sides': k('mfl', '456', 'mfl:456.f0002', ['4046', '456_2027_1_0002', '9509'], ['6794']),
    };
    for (const [label, key] of Object.entries(distinct)) if (key === base) bad.push(`${label}: same key`);
    if (k('espn', '1', 't', ['1,2'], []) === k('espn', '1', 't', ['1', '2'], [])) bad.push('a comma inside an id collides with two ids');
    if (k('espn', '1', 't|x', [], []) === k('espn', '1|t', 'x', [], [])) bad.push('league and counterparty run together');
    const all = Object.values(distinct);
    if (new Set(all).size !== all.length) bad.push('two of the distinct trades collide with each other');
    const input = ['b', 'a'];
    k('espn', '1', 't', input, input);
    if (input[0] !== 'b') bad.push('tradeSendKey sorted the caller\'s array in place');
    expect(!bad.length, bad.join('; '));
  });

  for (const p of Object.keys(PLATFORMS)) {
    const spec = PLATFORMS[p];
    await check(`R1b. ${path.basename(spec.file)}: keys on ('${spec.key}', leagueId, theirUserId, givePlayerIds, receivePlayerIds), the same identifiers its ${spec.propose} payload carries, no names`, () => {
      const sf = parse(spec.file);
      const call = findAll(sf, (n) => ts.isCallExpression(n) && n.expression.getText(sf) === 'tradeSendKey');
      expect(call.length === 1, `${call.length} tradeSendKey(...) calls`);
      const args = call[0].arguments.map((a) => a.getText(sf));
      expect(JSON.stringify(args) === JSON.stringify([`'${spec.key}'`, 'leagueId', 'theirUserId', 'givePlayerIds', 'receivePlayerIds']), `tradeSendKey(${args.join(', ')})`);
      const send = findAll(arrow(sf, 'doPropose'), (n) => ts.isCallExpression(n) && n.expression.getText(sf) === spec.propose)[0];
      const payload = send && send.arguments[0];
      expect(payload && ts.isObjectLiteralExpression(payload), `${spec.propose}(...) has no object payload`);
      const field = (name) => {
        const prop = payload.properties.find((q) => q.name && q.name.getText(sf) === name);
        return prop && ts.isPropertyAssignment(prop) ? prop.initializer.getText(sf) : null;
      };
      const want = {league_id: 'leagueId', their_user_id: 'theirUserId', give_player_ids: 'givePlayerIds', receive_player_ids: 'receivePlayerIds'};
      for (const [f, v] of Object.entries(want)) expect(field(f) === v, `payload ${f}: ${field(f)}, the key uses ${v}`);
      expect(!/Names/.test(call[0].getText(sf)), 'the key uses player names');
    });
  }

  for (const p of Object.keys(PLATFORMS)) {
    const spec = PLATFORMS[p];
    const name = path.basename(spec.file);

    // ════ R2. in_flight before the request; a second send is refused ═════
    await check(`R2a. ${name}: doPropose's first statement is \`if (!beginSend(sendKey)) return;\`, before any await`, () => {
      const sf = parse(spec.file);
      const body = arrow(sf, 'doPropose').body;
      expect(ts.isBlock(body), 'doPropose has no block body');
      const first = body.statements[0];
      expect(first && first.getText(sf).replace(/\s+/g, ' ') === 'if (!beginSend(sendKey)) return;', `first statement: ${first && first.getText(sf)}`);
      expect(!findAll(first, (n) => ts.isAwaitExpression(n)).length, 'an await before the guard');
    });

    await check(`R2b. ${name}: pressing Send sets in_flight synchronously, and the request goes out with it already set`, async () => {
      const w = appRun();
      const inst = w.mount(p);
      const dialog = await openConfirm(w, p, inst);
      pressAction(dialog, 'Send');
      const rec = w.registry.getSendRecord(keyOf(w, p));
      expect(rec && rec.state === 'in_flight', `right after the press, before any await: ${rec ? rec.state : 'no entry'}`);
      await flush();
      expect(w.posts.length === 1, `${w.posts.length} requests`);
      expect(w.posts[0].stateAtCall === 'in_flight', `the request saw ${w.posts[0].stateAtCall}`);
      inst.render();
      const b = btn(w, p, inst);
      expect(b.props.label === 'Sending…' && b.props.disabled === true, `the sending button: ${b.props.label}, disabled ${b.props.disabled}`);
    });

    await check(`R2c. ${name}: a same-frame double press, two queued confirm dialogs, and a second mount each send once (one POST)`, async () => {
      const w = appRun();
      const inst = w.mount(p);
      const dialog = await openConfirm(w, p, inst);
      pressAction(dialog, 'Send');
      pressAction(dialog, 'Send');
      await flush();
      expect(w.posts.length === 1, `double press: ${w.posts.length} POSTs`);

      const w2 = appRun();
      const a = w2.mount(p);
      btn(w2, p, a).props.onPress();
      btn(w2, p, a).props.onPress(); // same frame: the closure still sees idle
      await flush();
      const dialogs = w2.alerts.filter((x) => x[0] === 'Send this trade?');
      expect(dialogs.length === 2, `${dialogs.length} confirm dialogs from a same-frame double tap`);
      pressAction(dialogs[0], 'Send');
      await flush();
      pressAction(dialogs[1], 'Send');
      await flush();
      expect(w2.posts.length === 1, `two queued dialogs, second pressed while in flight: ${w2.posts.length} POSTs`);
      ANSWERS(w2).success(p);
      await flush();
      pressAction(dialogs[1], 'Send'); // the stale dialog again, after the confirmed send
      await flush();
      expect(w2.posts.length === 1, `stale dialog pressed after the confirmed send: ${w2.posts.length} POSTs`);

      const w3 = appRun();
      const one = w3.mount(p);
      const two = w3.mount(p);
      const d2 = await openConfirm(w3, p, two); // opened before the first send starts
      await startSend(w3, p, one);
      pressAction(d2, 'Send');
      await flush();
      expect(w3.posts.length === 1, `second mount: ${w3.posts.length} POSTs`);
    });

    await check(`R2d. ${name}: a stale queued dialog (#539 QA P3-1): double tap → two dialogs; Send on the first; unknown; Send on the second sends nothing and reopens the dialog with the 8${p === 'ESPN' ? 'e' : 'f'} reminder`, async () => {
      const w = appRun();
      const inst = w.mount(p);
      btn(w, p, inst).props.onPress();
      btn(w, p, inst).props.onPress(); // same frame
      await flush();
      const [d1, d2] = w.alerts.filter((x) => x[0] === 'Send this trade?');
      expect(d1 && d2, 'a same-frame double tap did not queue two dialogs');
      pressAction(d1, 'Send');
      await flush();
      ANSWERS(w).timeout(p);
      await flush();
      expect(w.alerts[w.alerts.length - 1][0] === 'Check before resending', `after the timeout: ${w.alerts[w.alerts.length - 1][0]}`);
      const before = w.alerts.length;
      pressAction(d2, 'Send'); // 60–91 s later, on the dialog built before the send
      await flush();
      expect(w.posts.length === 1, `the stale dialog sent: ${w.posts.length} POSTs`);
      const reopened = w.alerts.slice(before);
      expect(reopened.length === 1 && reopened[0][0] === 'Send this trade?', `after the stale press: ${reopened.map((a) => a[0]).join(' | ') || 'no dialog'}`);
      expect(reopened[0][1] === `${REMINDER[p]}\n\n${spec.body}`, `reopened body: ${JSON.stringify(reopened[0][1])}`);
      expect(JSON.stringify(reopened[0][2].map((x) => x.text)) === '["Cancel","Send"]', `reopened buttons ${reopened[0][2].map((x) => x.text)}`);
      pressAction(reopened[0], 'Send'); // sent knowingly, after the reminder
      await flush();
      expect(w.posts.length === 2, `the reopened dialog's Send: ${w.posts.length} POSTs, want 2`);

      // In flight or sent since the dialog was built: nothing, no new dialog.
      const v = appRun();
      const one = v.mount(p);
      const two = v.mount(p);
      const stale = await openConfirm(v, p, two);
      await startSend(v, p, one);
      await flush();
      let n = v.alerts.length;
      pressAction(stale, 'Send');
      await flush();
      expect(v.posts.length === 1 && v.alerts.length === n, `stale press while in flight: ${v.posts.length} POSTs, ${v.alerts.length - n} dialogs`);
      ANSWERS(v).success(p);
      await flush();
      n = v.alerts.length;
      pressAction(stale, 'Send');
      await flush();
      expect(v.posts.length === 1 && v.alerts.length === n, `stale press after sent: ${v.posts.length} POSTs, ${v.alerts.length - n} dialogs`);

      // The warnings dialog ("Send anyway") is guarded the same way.
      const x = appRun();
      x.warnings.push({severity: 'advisory', message: 'Roster limit.'});
      const wi = x.mount(p);
      btn(x, p, wi).props.onPress();
      btn(x, p, wi).props.onPress();
      await flush();
      const [w1, w2] = x.alerts.filter((a) => a[0] === 'Heads up before sending');
      pressAction(w1, 'Send anyway');
      await flush();
      ANSWERS(x).dropped(p);
      await flush();
      pressAction(w2, 'Send anyway');
      await flush();
      const last = x.alerts[x.alerts.length - 1];
      expect(x.posts.length === 1, `stale warnings dialog: ${x.posts.length} POSTs`);
      expect(last[0] === 'Heads up before sending' && last[1] === `${REMINDER[p]}\n\n• Roster limit.`, `reopened warnings dialog: ${last[0]} ${JSON.stringify(last[1])}`);
    });

    await check(`R2e. ${name}: both dialogs' Send is \`send\`, which calls doPropose only when \`now === shown\` (shown = the state when the dialog was built)`, () => {
      const sf = parse(spec.file);
      const fn = arrow(sf, 'confirmSend');
      const shown = findAll(fn, (n) => ts.isVariableDeclaration(n) && n.name.getText(sf) === 'shown')[0];
      expect(shown && shown.initializer.getText(sf) === 'getSendRecord(sendKey)?.state', `shown = ${shown && shown.initializer.getText(sf)}`);
      const send = findAll(fn, (n) => ts.isVariableDeclaration(n) && n.name.getText(sf) === 'send')[0];
      expect(send, 'no const send in confirmSend');
      const ifs = findAll(send, (n) => ts.isIfStatement(n));
      const guard = ifs.find((i) => findAll(i.thenStatement, (c) => ts.isIdentifier(c) && c.text === 'doPropose').length);
      expect(guard && guard.expression.getText(sf) === 'now === shown', `doPropose is not guarded by \`now === shown\` (${guard ? guard.expression.getText(sf) : 'no if around it'})`);
      const outside = findAll(send, (c) => ts.isIdentifier(c) && c.text === 'doPropose').filter((c) => !findAll(guard.thenStatement, (d) => d === c).length);
      expect(!outside.length, 'doPropose is reachable outside the `now === shown` branch');
      const presses = findAll(fn, (n) => ts.isPropertyAssignment(n) && n.name.getText(sf) === 'onPress').map((n) => n.initializer.getText(sf));
      expect(JSON.stringify(presses) === '["send","send"]', `dialog onPress handlers: ${presses.join(', ')}`);
    });

    // ════ R3. A remount reads the registry ════════════════════════════════
    await check(`R3. ${name}: a remount during the wait renders "Sending…" disabled and a tap does nothing; another trade on the same instance is idle`, async () => {
      const w = appRun();
      const first = w.mount(p);
      await startSend(w, p, first);
      await flush();
      first.unmount();
      const again = w.mount(p);
      const b = btn(w, p, again);
      expect(b.props.label === 'Sending…', `remount label: ${b.props.label}`);
      expect(b.props.disabled === true, 'remount is not disabled');
      const alerts = w.alerts.length;
      b.props.onPress();
      await flush();
      expect(w.statusCalls === 1 && w.alerts.length === alerts && w.posts.length === 1,
        `a tap on the remount: ${w.statusCalls - 1} link checks, ${w.alerts.length - alerts} dialogs, ${w.posts.length} POSTs`);
      const other = {...spec.props, receivePlayerIds: ['1111']};
      again.render(other);
      expect(btn(w, p, again).props.label === spec.idle && !btn(w, p, again).props.disabled, `another trade while the first is in flight: ${btn(w, p, again).props.label}`);
      again.render({...spec.props});
      expect(btn(w, p, again).props.label === 'Sending…', `back to the trade in flight: ${btn(w, p, again).props.label}`);
    });

    // ════ R4. Exactly one result alert after a remount ═════════════════════
    for (const [answer, kind, after] of [['success', 'success', 'Proposal sent'], ['timeout', 'unknown', spec.idle], ['write_failed', 'not_sent', spec.idle]]) {
      await check(`R4. ${name}: send, leave, reopen, then ${answer}: exactly one result alert; the remount is notified and shows "${after}"`, async () => {
        const w = appRun();
        const first = w.mount(p);
        await startSend(w, p, first);
        await flush();
        first.unmount();
        const again = w.mount(p);
        const before = w.alerts.length;
        ANSWERS(w)[answer](p);
        await flush();
        const results = w.alerts.slice(before);
        expect(results.length === 1, `${results.length} alerts after the answer: ${results.map((a) => a[0]).join(' | ')}`);
        if (RESULT_TITLE[kind]) expect(results[0][0] === RESULT_TITLE[kind], `alert title: ${results[0][0]}`);
        if (kind === 'not_sent') expect(results[0][0] === 'Not sent', `alert title: ${results[0][0]}`);
        expect(again.notified >= 1 && again.dirty, 'the remount was not notified of the settle');
        again.render();
        const b = btn(w, p, again);
        expect(b.props.label === after, `remount label after ${answer}: ${b.props.label}`);
        expect(b.props.disabled === (kind === 'success'), `remount disabled ${b.props.disabled} after ${answer}`);
      });
    }

    // ════ R5. Unknown → the reminder; success → sent; not-sent → cleared ═══
    await check(`R5a. ${name}: every unknown outcome (${UNKNOWN.join(', ')}) records unknown with its time; the next confirm dialog starts with 8${p === 'ESPN' ? 'e' : 'f'} word for word, buttons unchanged`, async () => {
      const bad = [];
      for (const answer of UNKNOWN) {
        const w = appRun();
        const inst = w.mount(p);
        await startSend(w, p, inst);
        await flush();
        const t0 = Date.now();
        ANSWERS(w)[answer](p);
        await flush();
        const rec = w.registry.getSendRecord(keyOf(w, p));
        if (!rec || rec.state !== 'unknown') { bad.push(`${answer}: ${rec ? rec.state : 'no entry'}`); continue; }
        if (!(rec.at >= t0 - 5 && rec.at <= Date.now())) bad.push(`${answer}: at ${rec.at}`);
        const again = w.mount(p);
        const b = btn(w, p, again);
        if (b.props.label !== spec.idle || b.props.disabled) bad.push(`${answer}: remount ${b.props.label}, disabled ${b.props.disabled}`);
        const dialog = await openConfirm(w, p, again);
        if (dialog[0] !== 'Send this trade?') bad.push(`${answer}: dialog title ${dialog[0]}`);
        if (dialog[1] !== `${REMINDER[p]}\n\n${spec.body}`) bad.push(`${answer}: dialog body ${JSON.stringify(dialog[1])}`);
        if (JSON.stringify((dialog[2] || []).map((x) => x.text)) !== '["Cancel","Send"]') bad.push(`${answer}: dialog buttons ${(dialog[2] || []).map((x) => x.text)}`);
      }
      expect(!bad.length, bad.join('; '));
    });

    await check(`R5b. ${name}: the warnings dialog ("Send anyway") carries the reminder too; with no unknown, both dialogs are unchanged`, async () => {
      const w = appRun();
      w.warnings.push({severity: 'advisory', message: 'Roster limit.'});
      const inst = w.mount(p);
      const plain = await openConfirm(w, p, inst);
      expect(plain[1] === '• Roster limit.', `warnings body with no unknown: ${JSON.stringify(plain[1])}`);
      pressAction(plain, 'Send anyway');
      await flush();
      ANSWERS(w).timeout(p);
      await flush();
      const warned = await openConfirm(w, p, inst);
      expect(warned[1] === `${REMINDER[p]}\n\n• Roster limit.`, `warnings body after unknown: ${JSON.stringify(warned[1])}`);
      expect(JSON.stringify(warned[2].map((x) => x.text)) === '["Cancel","Send anyway"]', `buttons ${warned[2].map((x) => x.text)}`);
      const w2 = appRun();
      const fresh = await openConfirm(w2, p, w2.mount(p));
      expect(fresh[1] === spec.body, `confirm body with no unknown: ${JSON.stringify(fresh[1])}`);
    });

    await check(`R5c. ${name}: success records sent ("Proposal sent", disabled, on a remount too); each definitive not-sent answer (${NOT_SENT.join(', ')}) clears the entry, and the next dialog has no reminder`, async () => {
      const bad = [];
      const w = appRun();
      await startSend(w, p, w.mount(p));
      await flush();
      ANSWERS(w).success(p);
      await flush();
      const rec = w.registry.getSendRecord(keyOf(w, p));
      if (!rec || rec.state !== 'sent') bad.push(`success: ${rec ? rec.state : 'no entry'}`);
      const again = w.mount(p);
      if (btn(w, p, again).props.label !== 'Proposal sent' || !btn(w, p, again).props.disabled) bad.push(`remount after success: ${btn(w, p, again).props.label}`);
      for (const answer of NOT_SENT) {
        const x = appRun();
        const inst = x.mount(p);
        await startSend(x, p, inst);
        await flush();
        ANSWERS(x)[answer](p);
        await flush();
        const r = x.registry.getSendRecord(keyOf(x, p));
        if (r) bad.push(`${answer}: entry left as ${r.state}`);
        const fresh = x.mount(p);
        if (btn(x, p, fresh).props.label !== spec.idle || btn(x, p, fresh).props.disabled) bad.push(`${answer}: remount ${btn(x, p, fresh).props.label}`);
        const d = await openConfirm(x, p, fresh);
        if (d[1] !== spec.body) bad.push(`${answer}: dialog body ${JSON.stringify(d[1])}`);
      }
      // After an unknown, a new send that is refused definitively clears the reminder.
      const y = appRun();
      const inst = y.mount(p);
      await startSend(y, p, inst);
      await flush();
      ANSWERS(y).timeout(p);
      await flush();
      await startSend(y, p, inst);
      await flush();
      ANSWERS(y).write_failed(p);
      await flush();
      if (y.registry.getSendRecord(keyOf(y, p))) bad.push('unknown then write_failed: entry not cleared');
      expect(!bad.length, bad.join('; '));
    });

    await check(`R5d. ${name}: the catch settles first, \`settleSend(sendKey, isSendOutcomeUnknown(err) ? 'unknown' : 'not_sent')\`; the reminder is sendOutcomeUnknownMessage('${p}')`, () => {
      const sf = parse(spec.file);
      const fn = arrow(sf, 'doPropose');
      const tryStmt = findAll(fn, (n) => ts.isTryStatement(n) && !!n.catchClause)[0];
      const first = tryStmt.catchClause.block.statements[0];
      expect(first && first.getText(sf) === "settleSend(sendKey, isSendOutcomeUnknown(err) ? 'unknown' : 'not_sent');", `catch starts with: ${first && first.getText(sf)}`);
      const ok = findAll(tryStmt.tryBlock, (n) => ts.isCallExpression(n) && n.getText(sf) === "settleSend(sendKey, 'sent')");
      expect(ok.length === 1, `${ok.length} settleSend(sendKey, 'sent') in the try block`);
      const reminder = findAll(arrow(sf, 'confirmSend'), (n) => ts.isVariableDeclaration(n) && n.name.getText(sf) === 'reminder')[0];
      expect(reminder, 'confirmSend has no const reminder');
      expect(reminder.initializer.getText(sf) === `shown === 'unknown' ? \`\${sendOutcomeUnknownMessage('${p}')}\\n\\n\` : ''`,
        `reminder = ${reminder.initializer.getText(sf)}`);
    });

    await check(`R5e. ${name}: subscribeSends is only the store of useSyncExternalStore (a remount has no listener that could alert); no local sending/sent state is left`, () => {
      const sf = parse(spec.file);
      const uses = findAll(sf, (n) => ts.isIdentifier(n) && n.text === 'subscribeSends' && !ts.isImportSpecifier(n.parent));
      expect(uses.length === 1, `${uses.length} uses of subscribeSends`);
      const call = uses[0].parent;
      expect(ts.isCallExpression(call) && call.expression.getText(sf) === 'useSyncExternalStore' && call.arguments[0] === uses[0],
        `subscribeSends used as: ${call.getText(sf)}`);
      expect(call.arguments[1].getText(sf) === '() => getSendRecord(sendKey)?.state', `snapshot: ${call.arguments[1].getText(sf)}`);
      const src = read(spec.file);
      expect(!/setState\('(sending|sent)'\)|state === '(sending|sent)'/.test(src), 'a local sending/sent state is still read or set');
    });
  }

  // ════ R6. Bounded, in memory, no imports ═════════════════════════════════
  await check('R6a. bounded (#539 QA P3-3): over SEND_REGISTRY_CAP, sent entries go first, then unknown, oldest first in each; in_flight never, even past the cap', () => {
    const {registry: R} = appRun();
    const cap = R.SEND_REGISTRY_CAP;
    expect(Number.isInteger(cap) && cap >= 10 && cap <= 200, `SEND_REGISTRY_CAP = ${cap}`);
    const key = (i) => R.tradeSendKey('espn', 'L', 't', [String(i)], []);
    const state = (i) => { const r = R.getSendRecord(key(i)); return r ? r.state : undefined; };
    const size = () => { let n = 0; for (let i = 0; i < 1000; i++) if (R.getSendRecord(key(i))) n++; return n; };
    // Fill to the cap, oldest first, interleaved: i % 3 = 0 in flight, 1 unknown, 2 sent.
    const want = (i) => ['in_flight', 'unknown', 'sent'][i % 3];
    for (let i = 0; i < cap; i++) {
      R.beginSend(key(i));
      if (want(i) !== 'in_flight') R.settleSend(key(i), want(i));
    }
    const of = (st) => [...Array(cap).keys()].filter((i) => want(i) === st);
    const [flying, unknown, sent] = [of('in_flight'), of('unknown'), of('sent')];
    const bad = [];
    let next = cap;
    const add = () => { R.beginSend(key(next)); next += 1; };
    add();
    if (state(sent[0]) !== undefined) bad.push(`1st over the cap kept the oldest sent (${sent[0]})`);
    if (state(flying[0]) !== 'in_flight' || state(unknown[0]) !== 'unknown') bad.push('1st over the cap evicted an older in_flight / unknown instead of the oldest sent');
    for (let k = 1; k < sent.length; k++) add();
    if (sent.some((i) => state(i) !== undefined)) bad.push('sent entries left after as many additions as there were sent');
    if (unknown.some((i) => state(i) !== 'unknown')) bad.push('an unknown entry went while a sent one was left');
    R.settleSend(key(unknown[0]), 'unknown'); // re-recorded: now the newest unknown
    add();
    if (state(unknown[0]) !== 'unknown') bad.push('the re-recorded unknown was evicted before older ones');
    if (state(unknown[1]) !== undefined) bad.push(`the oldest unknown (${unknown[1]}) was kept`);
    for (let k = 1; k < unknown.length; k++) add();
    if (unknown.some((i) => state(i) !== undefined)) bad.push('unknown entries left once only in_flight could go');
    if (flying.some((i) => state(i) !== 'in_flight')) bad.push('an in_flight entry was evicted');
    if (size() !== cap) bad.push(`${size()} entries, want the cap ${cap}`);
    add(); // every entry is in flight now
    if (size() !== cap + 1) bad.push(`all in flight: ${size()} entries, want cap + 1 (never evict in_flight)`);
    if (flying.some((i) => state(i) !== 'in_flight')) bad.push('an in_flight entry was evicted past the cap');
    R.settleSend(key(flying[0]), 'sent');
    add();
    if (state(flying[0]) !== undefined) bad.push('over the cap, the only sent entry was kept');
    if (size() !== cap + 1) bad.push(`after evicting the one sent entry: ${size()}, want cap + 1`);
    expect(!bad.length, bad.join('; '));
  });

  await check('R6b. module API: beginSend refuses in_flight and sent, allows after unknown or not_sent; listeners fire on every change and unsubscribe', () => {
    const {registry: R} = appRun();
    const k = R.tradeSendKey('mfl', 'L', 't', ['1'], ['2']);
    let n = 0;
    const off = R.subscribeSends(() => { n += 1; });
    const steps = [
      [R.beginSend(k), true], [R.beginSend(k), false],
      [(R.settleSend(k, 'unknown'), R.beginSend(k)), true],
      [(R.settleSend(k, 'not_sent'), R.getSendRecord(k)), undefined],
      [R.beginSend(k), true],
      [(R.settleSend(k, 'sent'), R.beginSend(k)), false],
    ];
    steps.forEach(([got, want], i) => expect(got === want, `step ${i}: ${got}, want ${want}`));
    expect(n === 6, `${n} notifications for 6 changes`);
    off();
    R.settleSend(k, 'not_sent');
    expect(n === 6, 'notified after unsubscribe');
  });

  await check('R6c. in memory per app run: sendRegistry.ts imports nothing (no storage, no React) and says it does not survive a restart', () => {
    const sf = parse('src/api/sendRegistry.ts');
    const imports = sf.statements.filter((s) => ts.isImportDeclaration(s) || ts.isImportEqualsDeclaration(s));
    expect(!imports.length, `imports: ${imports.map((s) => s.getText(sf)).join('; ')}`);
    expect(!/\brequire\(/.test(read('src/api/sendRegistry.ts')), 'require(...) in the registry');
    expect(/NOT an app restart/.test(read('src/api/sendRegistry.ts')), 'the in-memory limitation is not stated in the module comment');
  });

  await check('R6d. scope: the Sleeper send button and the overhaul screens do not use the registry', () => {
    for (const f of ['src/components/SendInSleeperButton.tsx', 'src/screens/OverhaulSummaryScreen.tsx', 'src/screens/OverhaulPlanScreen.tsx', 'src/api/overhaul.ts']) {
      expect(!/sendRegistry/.test(read(f)), `${f} imports the send registry`);
    }
  });

  console.log(failures === 0
    ? `\nAll send-registry checks passed (${passed}).`
    : `\n${failures} check(s) failed, ${passed} passed.`);
  process.exit(failures === 0 ? 0 : 1);
})();
