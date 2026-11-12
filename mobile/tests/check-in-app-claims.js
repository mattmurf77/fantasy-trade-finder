#!/usr/bin/env node
// check-in-app-claims.js — D1 Update 1 (docs/plans/in-app-claims/design.md):
// MFL free-agent moves light up SERVER-ONLY, so the 11-06 binary's claim
// sheet must already do the right thing with everything the MFL server path
// can answer. check-fa-move.js pins the sheet itself (F1-F18 and the review
// rounds); this suite pins the server <-> client agreement for MFL and the
// five properties the operator asked for, executed where behaviour is
// involved:
//
//   M1  every error code the MFL move path can emit (parsed from
//       backend/server.py's _fa_move_core_mfl + _fa_move_send) is one the
//       client maps, to the same state as its sleeper_ twin               [text + executed]
//   M2  the capability the MFL path serves: submit + connect ok → Ready;
//       any other connect → unsupported (no MFL connect screen);
//       unsupported → NO_ADD_REASON, never the Sleeper hand-off           [executed]
//   CONFIRM  the gate never submits without consent in hand: unticked →
//       'consent'; only a tick or a valid grant reaches submit            [executed]
//   SINGLE   one call site of the move API (attemptMove → submitMove), and
//       every "may have landed" answer is state 12 (no retry)              [AST + executed]
//   TIMEOUT  the client timer = the server worst case + 15 s = 91 s, and the
//       MFL write path's socket timeouts fit the server's budget          [text + executed]
//   FALLBACK 404 feature_disabled → the hand-off; on MFL the hand-off has
//       no Sleeper opener and shows a line instead                         [executed + AST]
//   FLAGOFF  no client file reads any *.send_add_drop flag: the sheet
//       renders only from the server's capability, so a flag-off server
//       (which answers exactly the pre-Update-1 capability) gives today's
//       app; "Open in Sleeper to claim" is still the Sleeper hand-off      [text]
//
// HONEST LABEL (G-035): [AST]/[text] prove wiring, not behaviour; no React
// tree renders here. [executed] runs the real api/faMove.ts and
// utils/claimSheetPlan.ts under plain node with stubs.
//
// FTF_MOBILE_TEST_ROOT / FTF_BACKEND_TEST_ROOT select other trees (sabotage).
// Run: node tests/check-in-app-claims.js   (or: npm run test:in-app-claims)

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
const BACKEND = process.env.FTF_BACKEND_TEST_ROOT || path.resolve(__dirname, '..', '..', 'backend');
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');

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
function expect(cond, msg) {
  if (!cond) throw new Error(msg);
}

// ── Loading the real modules ────────────────────────────────────────────────
class ApiError extends Error {
  constructor(status, body, isTimeout = false) {
    super(`HTTP ${status}`);
    this.status = status;
    this.body = body;
    this.isTimeout = isTimeout;
  }
}
const submitted = [];
function load(rel, requireShim) {
  const out = ts.transpileModule(read(rel), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(out, {
    module, exports: module.exports, require: requireShim, console, Date, Math, URL,
  }, { filename: rel });
  return module.exports;
}
const only = (map) => (n) => {
  if (!(n in map)) throw new Error(`unexpected import ${n}`);
  return map[n];
};
const fa = load('src/api/faMove.ts', only({
  '@react-native-community/netinfo': { __esModule: true, default: { fetch: async () => ({ isConnected: true }) } },
  './client': {
    ApiError,
    getBaseUrl: () => 'https://example.test',
    apiRequest: async (p, o) => { submitted.push([p, o]); return {}; },
  },
  './events': { track: () => {} },
}));
const plan = load('src/utils/claimSheetPlan.ts', only({ '../api/faMove': fa }));

const mflMove = (over = {}) => ({
  mode: 'submit', claims: false, league_platform: 'mfl', connect: 'ok',
  consent_until: null, copy: {}, ...over,
});

// ── M1: the server's MFL codes, all mapped like Sleeper's ───────────────────
function serverMflCodes() {
  const src = fs.readFileSync(path.join(BACKEND, 'server.py'), 'utf8');
  const body = (name) => {
    const at = src.indexOf(`\ndef ${name}(`);
    expect(at >= 0, `backend/server.py has no ${name}`);
    const next = src.indexOf('\ndef ', at + 5);
    return src.slice(at, next < 0 ? undefined : next);
  };
  const text = body('_fa_move_core_mfl') + body('_fa_move_send') + body('_fa_move_write_failure');
  const codes = new Set();
  for (const m of text.matchAll(/_fa_move_error\(\s*f?"([a-z{}_]+)"/g)) codes.add(m[1]);
  for (const m of text.matchAll(/f"\{platform\}_([a-z_]+)"/g)) codes.add(`{platform}_${m[1]}`);
  return [...codes].map((c) => c.replace('{platform}', 'mfl'));
}

check('M1 every MFL move code the server emits is mapped, like its sleeper_ twin', () => {
  const codes = serverMflCodes();
  expect(codes.length >= 8, `parsed only ${codes.length} codes: ${codes}`);
  for (const code of codes) {
    expect(fa.moveCodeSuffix(code) !== null, `client does not map ${code}`);
    const twin = code.replace(/^mfl_/, 'sleeper_');
    for (const status of [409, 422, 502, 503]) {
      const a = fa.classifyMoveError(new ApiError(status, { error: code, message: 'x' }));
      const b = fa.classifyMoveError(new ApiError(status, { error: twin, message: 'x' }));
      expect(a.state === b.state && a.errorCode === b.errorCode,
        `${code} → ${a.state}, but ${twin} → ${b.state}`);
    }
  }
  expect(codes.includes('mfl_outcome_unknown') && codes.includes('mfl_rejected'),
    'the parse missed the platform-prefixed codes');
});

check('M1 mfl_write_failed with kind network is "not sent"; without, "refused"', () => {
  const ns = fa.classifyMoveError(new ApiError(502, { error: 'mfl_write_failed', kind: 'network' }));
  const rf = fa.classifyMoveError(new ApiError(502, { error: 'mfl_write_failed' }));
  expect(ns.state === 'not_sent' && rf.state === 'platform_refused', `${ns.state} / ${rf.state}`);
});

// ── M2: the capability the MFL path serves ──────────────────────────────────
check('M2 MFL submit + connect ok opens the sheet at Ready (consent first)', () => {
  const move = mflMove();
  expect(fa.faMoveOpensSheet(move, {}), 'did not open the sheet');
  const copy = plan.copyFns(move, {});
  const v = plan.initialView(move, {}, copy);
  expect(v.step === 'ready', `initial view ${JSON.stringify(v)}`);
});

check('M2 MFL with any connect but ok is unsupported (no MFL connect screen)', () => {
  for (const connect of ['not_linked', 'expired', 'unverified', 'other_account', 'bogus']) {
    const g = fa.faMoveGate({ move: mflMove({ connect }), consentValid: true, ticked: true });
    expect(g === 'unsupported', `${connect} → ${g}`);
  }
  expect(!fa.hasConnectScreen('mfl') && fa.hasConnectScreen('sleeper'), 'connect screens changed');
});

check('M2 an unsupported MFL league is NO_ADD_REASON, never the Sleeper hand-off', () => {
  const move = mflMove({ mode: 'unsupported', connect: 'not_linked' });
  const v = plan.initialView(move, {}, plan.copyFns(move, {}));
  expect(v.step === 'unsupported', `got ${JSON.stringify(v)}`);
  expect(!fa.faMoveOpensSheet(move, {}), 'an unsupported league opened the in-app flow');
});

// ── CONFIRM ─────────────────────────────────────────────────────────────────
check('CONFIRM nothing submits without a tick or a valid grant', () => {
  const move = mflMove();
  expect(fa.faMoveGate({ move, consentValid: false, ticked: false }) === 'consent', 'unticked submitted');
  expect(fa.faMoveGate({ move, consentValid: false, ticked: true }) === 'submit_with_consent', 'tick');
  expect(fa.faMoveGate({ move, consentValid: true, ticked: false }) === 'submit', 'grant');
  const sheet = read('src/components/ClaimSheet.tsx');
  expect(/submit_with_consent/.test(read('src/api/faMove.ts')) && /attemptMove\(/.test(sheet),
    'the confirm path is gone');
});

// ── SINGLE submit ───────────────────────────────────────────────────────────
function callsTo(rel, name) {
  const sf = ts.createSourceFile(rel, read(rel), ts.ScriptTarget.Latest, true,
    rel.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  let k = 0;
  const walk = (n) => {
    if (ts.isCallExpression(n)) {
      const c = n.expression;
      const id = ts.isIdentifier(c) ? c.text : ts.isPropertyAccessExpression(c) ? c.name.text : null;
      if (id === name) k += 1;
    }
    ts.forEachChild(n, walk);
  };
  walk(sf);
  return k;
}
function srcFiles(dir = path.join(ROOT, 'src')) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...srcFiles(p));
    else if (/\.(ts|tsx)$/.test(e.name)) out.push(path.relative(ROOT, p));
  }
  return out;
}

check('SINGLE one call site of the move API in all of src', () => {
  const files = srcFiles();
  const submit = files.reduce((n, f) => n + callsTo(f, 'submitMove'), 0);
  const attempt = files.reduce((n, f) => n + callsTo(f, 'attemptMove'), 0);
  expect(submit === 1 && attempt === 1, `submitMove ×${submit}, attemptMove ×${attempt}`);
});

check('SINGLE every "may have landed" MFL answer is state 12, never a retry', () => {
  const cases = [
    new ApiError(502, { error: 'mfl_outcome_unknown' }),
    new ApiError(409, { error: 'move_in_progress' }),
    new ApiError(500, { error: 'internal_error' }),
    new ApiError(0, null),
    new ApiError(0, null, true),
    new ApiError(504, 'gateway'),
    new TypeError('Network request failed'),
  ];
  for (const e of cases) {
    expect(fa.isMoveOutcomeUnknown(e), `${JSON.stringify(e.body)} not outcome-unknown`);
    const p = plan.planFailure(fa.classifyMoveError(e), plan.copyFns(mflMove(), {}));
    expect(p.view && p.view.step !== 'ready', `state 12 offered the CTA again: ${JSON.stringify(p.view)}`);
  }
});

// ── TIMEOUT ─────────────────────────────────────────────────────────────────
check('TIMEOUT the client waits the server worst case + 15 s (91 s)', () => {
  const server = fs.readFileSync(path.join(BACKEND, 'server.py'), 'utf8');
  const worst = Number(/^FA_MOVE_SERVER_WORST_CASE_S = (\d+)/m.exec(server)[1]);
  expect(fa.FA_MOVE_SERVER_WORST_CASE_S === worst, `client ${fa.FA_MOVE_SERVER_WORST_CASE_S}, server ${worst}`);
  expect(fa.FA_MOVE_TIMEOUT_MS === (worst + 15) * 1000, `timeout ${fa.FA_MOVE_TIMEOUT_MS}`);
});

check('TIMEOUT the MFL write path fits the server write budget (46 s)', () => {
  const mfl = fs.readFileSync(path.join(BACKEND, 'mfl_write.py'), 'utf8');
  const http = Number(/^_HTTP_TIMEOUT = (\d+)/m.exec(mfl)[1]);
  const tuple = /^FA_MOVE_WRITE_TIMEOUTS_S[^=]*= \(([^)]*)\)/m.exec(mfl);
  expect(tuple, 'mfl_write.FA_MOVE_WRITE_TIMEOUTS_S missing');
  const sum = tuple[1].split(',').map((s) => s.trim()).filter(Boolean)
    .reduce((n, s) => n + (s === '_HTTP_TIMEOUT' ? http : Number(s)), 0);
  expect(sum > 0 && sum <= 46, `sum ${sum}`);
});

// ── FALLBACK ────────────────────────────────────────────────────────────────
check('FALLBACK 404 feature_disabled → hand-off; MFL shows a line, not a Sleeper opener', () => {
  const f = fa.classifyMoveError(new ApiError(404, { error: 'feature_disabled', message: 'm' }));
  expect(f.state === 'handoff', `state ${f.state}`);
  const p = plan.planFailure(f, plan.copyFns(mflMove(), {}));
  expect(p.view && p.view.step === 'handoff', `view ${JSON.stringify(p.view)}`);
  const sheet = read('src/components/ClaimSheet.tsx');
  expect(/const opensSleeper = platform === 'sleeper';/.test(sheet), 'opensSleeper rule changed');
  expect(/\{opensSleeper \? handoffCta : null\}/.test(sheet), 'the Sleeper opener is not gated');
});

// ── FLAGOFF ─────────────────────────────────────────────────────────────────
check('FLAGOFF no client file reads a send_add_drop flag', () => {
  const hits = srcFiles().filter((f) => /send_add_drop/.test(read(f)));
  expect(hits.length === 0, `read in ${hits.join(', ')}`);
});

check('FLAGOFF the Sleeper hand-off CTA is unchanged', () => {
  expect(read('src/components/ClaimSheet.tsx').includes('Open in Sleeper to claim'),
    '"Open in Sleeper to claim" is gone');
});

console.log(`\n${passed} passed, ${failures} failed`);
process.exit(failures ? 1 : 0);
