#!/usr/bin/env node
// check-fa-move.js — D1 free-agent moves: the dark client for the 11-06
// binary (platforms-eng, 2026-11-01).
//
// WHY THIS EXISTS. The 11-06 binary carries the whole in-app add / drop /
// claim flow, dark: it renders only from the server's per-league capability
// (`move` on GET /api/league/free-agents), so the flip, claims, MFL and ESPN
// are all server-only. The client can't change after 11-06, and D-056 took
// the simulator away, so this suite is the build's evidence. It pins F1–F17
// of docs/plans/sleeper-fa-write/scope.md §3 (plan/fa-moves-launch) against
// the wire contract (docs/plans/sleeper-fa-write/contract.md):
//
//   F1  no client flag read: `send_add_drop` / `fa_write` nowhere in src    [text + AST]
//   F2  faMoveGate's truth table; hosts route by the capability first      [executed + AST]
//   F3  outcome unknown never retries; isMoveOutcomeUnknown's triggers     [executed + AST]
//   F4  the named CTA comes from move.copy / the row's move_kind, with ONE
//       platform-free fallback constant; no Sleeper literal in the submit
//       branch                                                              [executed + AST]
//   F5  refusals map by code suffix (sleeper_ / mfl_ / espn_);
//       feature_disabled and waiver_claim_unsupported → the hand-off       [executed + AST]
//   F6  the move timeout = the server worst case + margin = 91 s, through
//       the real api/client.ts under a fake clock                          [executed]
//   F7  one call site of the move API, behind the gate's submit steps      [AST]
//   F8  the box starts unticked; Make the move needs it; the CTA is busy
//       while sending                                                       [AST]
//   F9  one attempt_id per tap, in the body and the event                  [executed]
//   F10 no steps block, no clipboard, in any mode                          [AST]
//   F11 consent text only from the server; none in src; the echo is the
//       received {copy_version, locale}                                     [executed + text]
//   F12 a terminal result invalidates the ['free-agents', leagueId] prefix [AST]
//   F13 the move goes through the shared client (its _noteWrite discards
//       the held trade page); no bare fetch                                [executed + AST]
//   F14 error_code is C3's platform-free closed set; kind only when sent   [executed]
//   F15 no event outside `submit`; each state-12 trigger's (error_code,
//       status)                                                             [executed]
//   F16 state 7 can't be dismissed; Cancel disabled, not hidden; busy; the
//       8 s line                                                            [AST]
//   F17 offline at the tap: state 11, no request, no attempt_id, no event
//       (stubbed NetInfo)                                                   [executed + AST]
// Plus: dark-safety (no capability → #509's hand-off, its footer neutral),
// the testIDs, Settings' Stop roster moves row, and K-F5's path agreement
// with utils/devicePage.ts (check-device-first-page.js executes the rule).
// Round 1 of platforms-eng's review (2026-11-01):
//   L1  the consent step's legal links: the block's `links`, else the app's
//       own Terms / Privacy from getBaseUrl(), through openPlatform with no
//       catch                                                              [executed + AST]
//   R1  the block's `reason` wins for fa_move_consent_shown                [executed + AST]
//   P1  "Claim pending" on the Free Agents row after a state-9 result, in
//       memory, keyed by league + player, written only from submit mode    [executed + AST]
//   T7  contract §7's fill rules: {bid} as "$N" ($0 for an empty FAAB bid),
//       {date} a short date with no time, a missing known placeholder falls
//       back                                                                [executed]
// Round 2 (independent review + contract 7052d2d7 / 41c1443e), one pin per
// fix, executed through utils/claimSheetPlan.ts and api/faMove.ts:
//   X1  attempt_id: v4-shaped from Math.random with no `crypto`; 1,000 distinct
//   X2  10a the client didn't foresee: drop list, server message, refresh
//   X3  a drop that left the candidates is neither named nor sent
//   X4  offline / no answer before the consent GET → state 11, no GET
//   X5  Usage Trends' pre-read: a plain bounded call, only move + row; busy Add
//   X6  pinned/unpinned: measured on the content, hysteresis, no flip-flop
//   X7  MFL connect/verify/rejected → unsupported; held non-Sleeper rows show
//       the server's line; EspnConnect without reason: 'send'
//   X8  Settings: 404 = valid: false; a failed DELETE keeps the row + a line
//   X9  "terms changed" also on reason: 'version'
//   X10 fully legacy for an absent/unknown mode: no move.copy, no move_line
//   X11 every in-sheet re-read is bounded; a failed one after Connect goes on
//   X12 contract §7's claim/waiver slots by bid and drop; `surface` sent
// Round 3 (contract 3248995b: both consent routes need a verified session):
//   Y1  Settings: a GET 403 verification_required is valid: false (no row);
//       a DELETE 403 keeps the row with the "Couldn't turn off" line       [executed + AST]
//   Y2  the sheet: a consent GET 403 verification_required is state 4
//       (Verify), the move route's plan, never F4's hand-off              [executed + AST]
//   Y3  fa_move_connect_shown records an unknown connect value as
//       `unknown` (analytics-lead); the UI still shows the connect step    [executed + AST]
// Round 5 (head-eng's design note; legal R28.26 / R28.27):
//   B1  a working button keeps full brightness with its spinner, takes no
//       tap (#364's Button: `loading`, not `disabled`)                     [executed + AST]
//   B2  "In {league}" beside the named CTA in every step that shows it,
//       with the server slot absent, from the host's league name          [executed + AST]
//   B3  "nothing was sent" only in state 11 (and F4), never 10f or 13      [executed table]
// Round 4 (marketing-lead's final copy, addendum 17 §A):
//   Z1  every changed fallback verbatim (A3.1–A3.9), the confirmed ones
//       (A2, G22, G23, the bid line), and the Usage Trends footer (A1)     [executed + text]
//
// HONEST LABEL (G-035): the [AST] checks prove wirings are present, not
// behavior; no React tree is rendered here. The [executed] checks run the
// real api/faMove.ts and api/client.ts under plain node with stubs.
//
// FTF_MOBILE_TEST_ROOT selects another mobile/ tree (sabotage runs).
// Run: node tests/check-fa-move.js   (or: npm run test:fa-move)

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

const FA_MOVE = 'src/api/faMove.ts';
const CLAIM = 'src/components/ClaimSheet.tsx';
const FREE_AGENTS = 'src/screens/FreeAgentsScreen.tsx';
const USAGE_TRENDS = 'src/screens/UsageTrendsScreen.tsx';
const SETTINGS_LEAGUES = 'src/screens/settings/SettingsLeaguesScreen.tsx';
const DEVICE_PAGE = 'src/utils/devicePage.ts';
const BUTTON = 'src/components/chalkline/Button.tsx';
const PLAN = 'src/utils/claimSheetPlan.ts';
const V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

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
function expect(cond, msg) {
  if (!cond) throw new Error(msg);
}
const eq = (a, b, msg) =>
  expect(JSON.stringify(a) === JSON.stringify(b), `${msg}: got ${JSON.stringify(a)}, want ${JSON.stringify(b)}`);

// ── AST helpers ─────────────────────────────────────────────────────────────
const parse = (rel) =>
  ts.createSourceFile(rel, read(rel), ts.ScriptTarget.Latest, true,
    rel.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
function walk(node, fn) {
  fn(node);
  ts.forEachChild(node, (c) => walk(c, fn));
}
const unparen = (n) => (ts.isParenthesizedExpression(n) ? unparen(n.expression) : n);
// A function declaration's or a `const name = …`'s text, by name.
function decl(sf, name) {
  let out = null;
  walk(sf, (n) => {
    if (ts.isFunctionDeclaration(n) && n.name && n.name.text === name) out = n;
    if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === name && n.initializer) out = n.initializer;
  });
  return out;
}
const declText = (sf, name) => {
  const n = decl(sf, name);
  return n ? n.getText(sf) : '';
};
// Attributes (name → initializer text) of each JSX element named `tag`, with the node.
function jsxMounts(sf, tag, within) {
  const out = [];
  walk(within || sf, (n) => {
    if ((ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)) && n.tagName.getText(sf) === tag) {
      const attrs = {};
      for (const a of n.attributes.properties) {
        if (ts.isJsxAttribute(a)) attrs[a.name.getText(sf)] = a.initializer ? a.initializer.getText(sf) : 'true';
      }
      out.push({ attrs, node: n });
    }
  });
  return out;
}
const isStringish = (n) =>
  ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isTemplateHead(n) ||
  ts.isTemplateMiddle(n) || ts.isTemplateTail(n) || ts.isJsxText(n);
function literals(sf, within) {
  const out = [];
  walk(within || sf, (n) => {
    if (isStringish(n)) out.push(n.text);
  });
  return out;
}
// Literals a user can read: route names passed to navigate() are not words.
function wording(sf, within) {
  const out = [];
  walk(within || sf, (n) => {
    if (!isStringish(n)) return;
    const p = n.parent;
    const isRoute = p && ts.isCallExpression(p) && ts.isPropertyAccessExpression(p.expression)
      && p.expression.name.text === 'navigate' && p.arguments[0] === n;
    if (!isRoute) out.push(n.text);
  });
  return out;
}
const calls = (sf, name, within) => {
  const out = [];
  walk(within || sf, (n) => {
    if (ts.isCallExpression(n)) {
      const callee = n.expression;
      const id = ts.isIdentifier(callee) ? callee.text : ts.isPropertyAccessExpression(callee) ? callee.name.text : null;
      if (id === name) out.push(n);
    }
  });
  return out;
};
const identRefs = (sf, name, within) => {
  let k = 0;
  walk(within || sf, (n) => {
    if (ts.isIdentifier(n) && n.text === name) k += 1;
  });
  return k;
};
function srcFiles(dir = path.join(ROOT, 'src')) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...srcFiles(p));
    else if (/\.(ts|tsx)$/.test(e.name)) out.push(p);
  }
  return out;
}

// ── Executed harness: the real faMove.ts on the real client.ts ──────────────
const flush = async () => { for (let n = 0; n < 80; n++) await Promise.resolve(); };
function clock() {
  let now = 1_000_000;
  let id = 0;
  const timers = new Map();
  return {
    Date: class extends Date { static now() { return now; } },
    performance: { now: () => now },
    setTimeout(fn, ms) { const key = ++id; timers.set(key, { at: now + (ms || 0), fn }); return key; },
    clearTimeout(key) { timers.delete(key); },
    async advance(ms) {
      const end = now + ms;
      await flush();
      for (;;) {
        const next = [...timers].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!next) break;
        now = Math.max(now, next[1].at); timers.delete(next[0]); next[1].fn(); await flush();
      }
      now = end; await flush();
    },
  };
}
function load(rel, requireShim, time, extra = {}) {
  const out = ts.transpileModule(read(rel), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(out, {
    module, exports: module.exports, require: requireShim,
    AbortController, DOMException, URL, console, ...time, ...extra,
  }, { filename: rel });
  return module.exports;
}
const response = (status, body) => ({
  status, ok: status >= 200 && status < 300,
  text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
});
const only = (map) => (n) => {
  if (!(n in map)) throw new Error(`unexpected import ${n}`);
  return map[n];
};
function harness() {
  const time = clock();
  const log = [];
  const requests = [];
  const events = [];
  const writes = [];
  let responder = () => new Promise(() => {}); // never answers
  let net = { isConnected: true };
  // Math.random is counted (Hermes has no Web Crypto, so the attempt id
  // comes from it); `crypto` is absent from the sandbox, as on a device.
  let rands = 0;
  const countingMath = Object.create(Math);
  countingMath.random = () => { rands += 1; if (rands === 1 || rands % 16 === 1) log.push('rand'); return Math.random(); };
  const native = {
    'expo-constants': { default: { expoConfig: { extra: { apiBaseUrl: 'https://example.invalid' }, version: 'test' } } },
    'expo-device': { DeviceType: { TABLET: 2, DESKTOP: 3 } },
    'expo-secure-store': { getItemAsync: async () => 'synthetic-token', setItemAsync: async () => {}, deleteItemAsync: async () => {} },
    'react-native': { Platform: { OS: 'ios' }, AppState: { addEventListener: () => {} } },
    './events': { track: () => {} }, // the client's own api_request_failed
  };
  const fetch = (url, opts) => {
    log.push('fetch');
    requests.push({ url, method: opts.method, body: opts.body ? JSON.parse(opts.body) : undefined });
    return new Promise((resolve, reject) => {
      const abort = () => reject(new DOMException('Aborted', 'AbortError'));
      if (opts.signal?.aborted) return abort();
      opts.signal?.addEventListener('abort', abort, { once: true });
      Promise.resolve().then(() => responder(url, opts)).then(resolve, reject);
    });
  };
  const client = load('src/api/client.ts', only(native), time, { fetch });
  client.setOnWriteRequest((p) => writes.push(p));
  const league = load('src/api/league.ts', only({ './client': client }), time);
  const faMove = load(FA_MOVE, only({
    './client': client,
    './league': league,
    './events': { track: (name, props) => { log.push('track'); events.push({ name, props }); } },
    '@react-native-community/netinfo': { default: { fetch: async () => { log.push('netinfo'); return net; } } },
  }), time, { Math: countingMath });
  const plan = load(PLAN, only({ '../api/faMove': faMove }), time);
  return {
    time, log, requests, events, writes, client, faMove, plan,
    rands: () => rands,
    respond: (fn) => { responder = fn; },
    setNet: (s) => { net = s; },
  };
}
function watch(p) {
  const s = { state: 'pending', value: undefined };
  p.then((v) => { s.state = 'resolved'; s.value = v; }, (e) => { s.state = 'rejected'; s.value = e; });
  return s;
}
const apiErr = (h, status, body, timeout = false) => new h.client.ApiError(status, body, 'x', timeout);

const SUBMIT = {
  mode: 'submit', claims: true, league_platform: 'sleeper', connect: 'ok',
  consent_until: '2099-01-01T00:00:00Z', copy: {},
};
const REQ = { league_id: '1048293', add_player_id: '4046', move_kind: 'add' };
const C3 = [
  'feature_disabled', 'bad_request', 'verification_required', 'not_linked', 'expired', 'unconfigured',
  'consent_required', 'roster_full_drop_required', 'asset_not_owned', 'player_unavailable',
  'waiver_bid_over_budget', 'waiver_claim_unsupported', 'move_kind_changed', 'rejected', 'write_failed',
  'outcome_unknown', 'move_in_progress', 'internal_error', 'network', 'timeout', 'unknown',
];
const BLOCK = {
  copy_version: 'test-copy-v9', locale: 'en-ZZ', title: 'T', body: ['p1', 'p2'],
  checkbox_label: 'box', this_move: 'This move: {cta} in {league}.', button_label: 'Go',
};

// A check that awaits something that never settles would let the event loop
// drain and node exit 0 mid-run: an unfinished run fails instead.
let finished = false;
process.on('exit', () => {
  if (!finished) {
    console.log('\ncheck-fa-move did not finish (a check hung): FAILED');
    process.exitCode = 1;
  }
});

(async () => {
  console.log('check-fa-move:');
  const claim = parse(CLAIM);
  const fa = parse(FA_MOVE);
  const claimText = read(CLAIM);
  const faText = read(FA_MOVE);

  // ── F1 ───────────────────────────────────────────────────────────────────
  await check('F1 no client flag read: `send_add_drop` / `fa_write` appear nowhere in mobile/src', () => {
    const hits = srcFiles().filter((f) => /send_add_drop|fa_write/.test(fs.readFileSync(f, 'utf8')));
    eq(hits.map((f) => path.relative(ROOT, f)), [], 'files naming the kill switch');
  });
  await check('F1 neither faMove.ts nor ClaimSheet reads a flag (no useFlag / useFeatureFlags)', () => {
    for (const [sf, rel] of [[fa, FA_MOVE], [claim, CLAIM]]) {
      expect(identRefs(sf, 'useFlag') === 0 && identRefs(sf, 'useFeatureFlags') === 0, `${rel} reads a flag`);
    }
  });

  // ── F2 ───────────────────────────────────────────────────────────────────
  {
    const h = harness();
    const G = h.faMove.faMoveGate;
    const gate = (move, o = {}) => G({ move, consentValid: false, ticked: false, ...o });
    await check('F2 absent or unknown `move` → legacy (old server, unknown mode, submit with no platform)', () => {
      eq([undefined, null, {}, 'submit', { mode: 'bogus' }, { ...SUBMIT, league_platform: null },
        { ...SUBMIT, league_platform: 'fleaflicker' }].map((m) => gate(m)),
      Array(7).fill('legacy'), 'gate');
    });
    await check('F2 unsupported → unsupported; handoff → handoff; neither opens the in-app flow', () => {
      eq(gate({ ...SUBMIT, mode: 'unsupported' }), 'unsupported', 'unsupported');
      eq(gate({ ...SUBMIT, mode: 'handoff' }, { consentValid: true }), 'handoff', 'handoff');
      eq([undefined, { ...SUBMIT, mode: 'unsupported' }, { ...SUBMIT, mode: 'handoff' }]
        .map((m) => h.faMove.faMoveOpensSheet(m)), [false, false, false], 'faMoveOpensSheet');
      expect(h.faMove.faMoveOpensSheet(SUBMIT) && h.faMove.faMoveOpensSheet({ ...SUBMIT, league_platform: 'espn' }),
        'submit opens the sheet on any platform (Update 1 with no build)');
    });
    await check('F2 connect and verify beat consent; an unknown connect value is the plain connect step', () => {
      const valid = { consentValid: true, ticked: true };
      eq(['not_linked', 'other_account', 'banana', '', 'expired', 'unverified', 'ok']
        .map((c) => gate({ ...SUBMIT, connect: c }, valid)),
      ['connect', 'connect', 'connect', 'connect', 'verify', 'verify', 'submit'], 'connect');
      eq(gate(SUBMIT, { ...valid, connect: 'not_linked' }), 'connect', 'a refusal overrides move.connect');
    });
    await check('F2 consent: valid → submit; ticked → submit_with_consent; an unticked box never submits', () => {
      eq(gate(SUBMIT, { consentValid: true }), 'submit', 'valid');
      eq(gate(SUBMIT, { ticked: true }), 'submit_with_consent', 'ticked');
      const unticked = [];
      for (const connect of ['ok', 'not_linked', 'expired']) {
        for (const move_kind of ['add', 'claim', null]) {
          unticked.push(gate({ ...SUBMIT, connect }, { row: { move_kind } }));
        }
      }
      expect(!unticked.some((s) => s === 'submit' || s === 'submit_with_consent'), `unticked + no consent: ${unticked}`);
    });
    await check('F2 a held row and a claim while claims are off → the hand-off; MFL not connected → unsupported (contract §6)', () => {
      eq(gate(SUBMIT, { consentValid: true, row: { move_mode: 'handoff' } }), 'handoff', 'row override');
      eq(gate({ ...SUBMIT, claims: false }, { consentValid: true, row: { move_kind: 'claim' } }), 'handoff', 'claims off');
      eq(gate({ ...SUBMIT, claims: false }, { consentValid: true, row: { move_kind: 'add' } }), 'submit', 'add with claims off');
      eq(gate({ ...SUBMIT, league_platform: 'mfl', connect: 'not_linked' }), 'unsupported', 'mfl');
      eq(gate({ ...SUBMIT, league_platform: 'espn', connect: 'expired' }), 'verify', 'espn has EspnConnect');
    });
  }
  await check('F2 both hosts route Add by the capability first, then resolveAddPlatform; else NO_ADD_REASON', () => {
    const faSrc = read(FREE_AGENTS);
    expect(/if \(faMoveOpensSheet\(move, row\) \|\| addPlatform === 'sleeper'\) \{[\s\S]*?setClaimTarget\(row\);\s*\} else \{\s*explainNoAdd\(addPlatform\);/.test(faSrc),
      'FreeAgentsScreen onAdd');
    expect(/const move = query\.data\?\.move \?\? null;/.test(faSrc) && /move=\{claimMove\}/.test(faSrc),
      'Free Agents passes the capability it routed with');
    const ut = read(USAGE_TRENDS);
    expect(/if \(platform !== 'sleeper' && !faMoveOpensSheet\(cap\.move, cap\.row\)\) \{\s*explainNoAdd\(platform\);\s*return;\s*\}/.test(ut),
      'UsageTrendsScreen doAdd');
    expect(/move=\{claim\.move\}/.test(ut) && /readMoveCapability\(lgId, p\.player_id\)/.test(ut),
      'Usage Trends reads the capability and passes it');
  });

  // ── F3 ───────────────────────────────────────────────────────────────────
  {
    const h = harness();
    const U = h.faMove.isMoveOutcomeUnknown;
    await check('F3 isMoveOutcomeUnknown: *_outcome_unknown, move_in_progress, internal_error, timeout, status 0, a code-less 5xx', () => {
      const yes = [
        apiErr(h, 502, { error: 'sleeper_outcome_unknown' }), apiErr(h, 502, { error: 'mfl_outcome_unknown' }),
        apiErr(h, 502, { error: 'espn_outcome_unknown' }), apiErr(h, 409, { error: 'move_in_progress' }),
        apiErr(h, 500, { error: 'internal_error' }), apiErr(h, 0, null, true), apiErr(h, 0, null),
        new TypeError('Network request failed'), apiErr(h, 503, '<html>'), apiErr(h, 504, {}),
      ];
      eq(yes.map(U), yes.map(() => true), 'unknown');
      const no = [
        apiErr(h, 502, { error: 'sleeper_write_failed', kind: 'network' }), apiErr(h, 502, { error: 'sleeper_write_failed' }),
        apiErr(h, 422, { error: 'player_unavailable' }), apiErr(h, 409, { error: 'consent_required' }),
        apiErr(h, 404, { error: 'feature_disabled' }), apiErr(h, 400, { error: 'bad_request' }), apiErr(h, 418, { error: 'teapot' }),
      ];
      eq(no.map(U), no.map(() => false), 'known');
    });
  }
  await check('F3 state 12 is a result panel with no retry: no "Try again" in the sheet, no send from the result block', () => {
    expect(!literals(claim).some((t) => /try again/i.test(t)), 'a "Try again" literal in ClaimSheet');
    const h = harness();
    const cp = h.plan.copyFns(SUBMIT, { league: 'L', name: 'A' });
    for (const code of ['sleeper_outcome_unknown', 'move_in_progress', 'internal_error']) {
      const v = h.plan.planFailure(h.faMove.classifyMoveError(apiErr(h, 502, { error: code })), cp).view;
      expect(v.step === 'result' && v.kind === 'unknown' && v.title === 'Check before resending', `${code} → ${JSON.stringify(v)}`);
    }
    const result = actionBranches(claim).result;
    expect(result && !/onNamedCta|\bsend\(|make-move/.test(result.getText(claim)), 'the result block re-enables no CTA');
  });

  // ── F4 ───────────────────────────────────────────────────────────────────
  {
    const h = harness();
    const M = h.faMove;
    await check('F4 the named CTA: the server template when sent, else the one fallback constant; by move_kind', () => {
      const copy = { cta_add_drop: 'ADD {add} / DROP {drop}', cta_claim: 'CLAIM {add} @ {bid}' };
      eq(M.moveCtaLabel(copy, 'add', { add: 'A', drop: 'B' }, 'sleeper'), 'ADD A / DROP B', 'server add+drop');
      eq(M.moveCtaLabel(copy, 'claim', { add: 'A', bid: '$7' }, 'sleeper'), 'CLAIM A @ $7', 'server claim');
      eq(M.moveCtaLabel({}, 'add', { add: 'A' }, 'sleeper'), 'Add A', 'fallback add');
      eq(M.moveCtaLabel(undefined, 'claim', { add: 'A', bid: '$7', drop: 'B' }, 'mfl'), 'Claim A for $7, drop B', 'fallback claim');
      eq(M.moveCtaLabel(undefined, 'claim', { add: 'A' }, 'espn'), 'Claim A', 'a priority-waiver claim has no bid');
      eq(M.moveCtaLabel({ cta_add: 'Add {add} to {nope}' }, 'add', { add: 'A' }, 'sleeper'), 'Add A to {nope}', 'unknown placeholder kept');
    });
    await check('F4 FA_MOVE_FALLBACK_COPY is the one fallback constant, covers every slot, and is platform-free', () => {
      const keys = ['header_add', 'header_claim', 'cta_add', 'cta_add_drop', 'cta_claim', 'cta_claim_drop', 'league_line',
        'finality', 'waiver_line', 'window_line', 'turn_off', 'do_in_platform', 'open_platform', 'handoff_footer',
        'connect_line', 'verify_line', 'other_account_line', 'not_sent_line', 'unknown_title', 'unknown_body',
        'unavailable_line', 'still_sending'];
      const fb = M.FA_MOVE_FALLBACK_COPY;
      expect(keys.every((k) => typeof fb[k] === 'string' && fb[k]), 'a contract slot without a fallback');
      const named = Object.entries(fb).filter(([, v]) => /Sleeper|ESPN|MFL/.test(v));
      eq(named, [], 'fallbacks naming a platform');
      expect(!Object.values(fb).some((v) => /doesn't allow apps|don't allow apps/i.test(v)), 'the false Sleeper claim');
      eq(M.moveCopy(undefined, 'do_in_platform', {}, 'espn'), 'Do it in ESPN instead', 'the platform is filled');
      let consts = 0;
      walk(fa, (n) => { if (ts.isVariableDeclaration(n) && /FALLBACK/.test(n.name.getText(fa))) consts += 1; });
      eq(consts, 1, 'FALLBACK constants in faMove.ts');
    });
  }
  await check('F4 ClaimSheet: the make-move CTA is `ctaLabel` = moveCtaLabel(move?.copy, kind, …); no Sleeper or "Add …" literal in the submit branch', () => {
    const ctas = jsxMounts(claim, 'Button').filter((m) => m.attrs.testID === '"fa-claim.make-move"');
    expect(ctas.some((m) => m.attrs.label === '{ctaLabel}'), 'no make-move Button labelled {ctaLabel}');
    expect(declText(claim, 'ctaLabel') === 'sel.ctaLabel' && /^moveSelection\(\{[\s\S]*\bkind,[\s\S]*copy: move\?\.copy,/.test(declText(claim, 'sel')),
      `ctaLabel = ${declText(claim, 'ctaLabel').slice(0, 80)}`);
    expect(/rowMove\.move_kind === 'claim'/.test(declText(claim, 'kind')), 'kind comes from the row\'s move_kind');
    const sleeperLits = wording(claim).filter((t) => /Sleeper/.test(t));
    eq(sleeperLits, ['Open in Sleeper to claim'], 'Sleeper literals (only #509\'s pinned hand-off label)');
    const addLits = wording(claim).filter((t) => /^\s*Add\s/.test(t));
    eq(addLits, [], 'hard-coded "Add …" literals');
  });

  // ── F5 ───────────────────────────────────────────────────────────────────
  {
    const h = harness();
    const C = (s, b) => h.faMove.classifyMoveError(apiErr(h, s, b));
    await check('F5 codes map by suffix for sleeper_, mfl_ and espn_ alike', () => {
      const bySuffix = { not_linked: 'connect', expired: 'verify', rejected: 'rejected', unconfigured: 'unavailable',
        write_failed: 'platform_refused', outcome_unknown: 'unknown' };
      for (const p of ['sleeper', 'mfl', 'espn']) {
        for (const [suffix, state] of Object.entries(bySuffix)) {
          const got = C(502, { error: `${p}_${suffix}` });
          eq([got.state, got.errorCode], [state, suffix], `${p}_${suffix}`);
        }
        eq(C(502, { error: `${p}_write_failed`, kind: 'network' }).state, 'not_sent', `${p}_write_failed + network`);
        eq(C(502, { error: `${p}_write_failed`, kind: 'roster_read' }).state, 'not_sent', `${p}_write_failed + roster_read`);
      }
      eq(C(409, { error: 'fleaflicker_not_linked' }).state, 'neutral', 'an unknown platform prefix is not a known code');
    });
    await check('F5 the bare codes: feature_disabled → hand-off, waiver_claim_unsupported → claims_off (14), the rest per §4', () => {
      const want = { feature_disabled: 'handoff', bad_request: 'neutral', verification_required: 'verify',
        consent_required: 'consent', roster_full_drop_required: 'roster_full', asset_not_owned: 'drop_gone',
        player_unavailable: 'player_taken', waiver_bid_over_budget: 'over_budget',
        waiver_claim_unsupported: 'claims_off', move_kind_changed: 'kind_changed', move_in_progress: 'unknown',
        internal_error: 'unknown' };
      for (const [code, state] of Object.entries(want)) eq(C(409, { error: code }).state, state, code);
      eq(C(422, { error: 'waiver_bid_over_budget', remaining: 12 }).remaining, 12, 'remaining rides along');
      eq(C(409, { error: 'consent_required', consent: BLOCK }).consent, BLOCK, 'the 409\'s consent block');
      eq(C(418, { error: 'teapot', message: 'm' }).state, 'neutral', 'an unrecognised 4xx is the 12-style panel');
    });
    await check('F5 ClaimSheet shows the hand-off for feature_disabled and for claims_off, bid and drop kept', () => {
      const cp = h.plan.copyFns(SUBMIT, { league: 'L', name: 'A' });
      for (const [status, code] of [[404, 'feature_disabled'], [422, 'waiver_claim_unsupported']]) {
        const plan = h.plan.planFailure(C(status, { error: code, message: 'm' }), cp);
        expect(plan.view && plan.view.step === 'handoff' && !plan.clearDrop, `${code} → ${JSON.stringify(plan)}`);
      }
    });
  }

  // ── F6 ───────────────────────────────────────────────────────────────────
  {
    const h = harness();
    await check('F6 FA_MOVE_TIMEOUT_MS = (FA_MOVE_SERVER_WORST_CASE_S 76 + margin 15) × 1000 = 91 000', () => {
      eq([h.faMove.FA_MOVE_SERVER_WORST_CASE_S, h.faMove.FA_MOVE_TIMEOUT_MARGIN_S, h.faMove.FA_MOVE_TIMEOUT_MS],
        [76, 15, 91_000], 'constants');
      expect(/FA_MOVE_TIMEOUT_MS = \(FA_MOVE_SERVER_WORST_CASE_S \+ FA_MOVE_TIMEOUT_MARGIN_S\) \* 1000/.test(faText),
        'built from its named parts');
      expect(/timeoutMs: FA_MOVE_TIMEOUT_MS/.test(declText(fa, 'submitMove')), 'submitMove passes it');
    });
    await check('F6 through the real client: the move waits 91 s (pending at 15 s and 90.9 s), a GET still gives up at 15 s', async () => {
      const move = watch(h.faMove.submitMove({ ...REQ, attempt_id: 'a' }));
      await h.time.advance(15_000);
      expect(move.state === 'pending', 'the move gave up at the 15 s default');
      await h.time.advance(75_900);
      expect(move.state === 'pending', 'the move gave up before 91 s');
      await h.time.advance(100);
      expect(move.state === 'rejected' && move.value.isTimeout === true, `at 91 s: ${move.state}`);
      const get = watch(h.client.apiRequest('/api/league/free-agents?league_id=1'));
      await h.time.advance(15_000);
      expect(get.state === 'rejected' && get.value.isTimeout, 'the GET control kept its 15 s');
    });
  }

  // ── F7 ───────────────────────────────────────────────────────────────────
  await check('F7 the move API has one call site (attemptMove), and attemptMove one (ClaimSheet send) behind the gate', () => {
    const everywhere = (name) => srcFiles().reduce((k, f) => {
      const sf = ts.createSourceFile(f, fs.readFileSync(f, 'utf8'), ts.ScriptTarget.Latest, true,
        f.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
      return k + calls(sf, name).length;
    }, 0);
    eq([everywhere('submitMove'), everywhere('attemptMove')], [1, 1], '[submitMove, attemptMove] call sites');
    expect(calls(fa, 'submitMove', decl(fa, 'attemptMove')).length === 1, 'submitMove is called from attemptMove');
    const send = decl(claim, 'send');
    expect(send && calls(claim, 'attemptMove', send).length === 1, 'attemptMove is called from send');
    const body = send.getText(claim);
    const gateAt = body.search(/const step = faMoveGate\(/);
    const guardAt = body.search(/if \(step !== 'submit' && step !== 'submit_with_consent'\) return;/);
    const callAt = body.indexOf('attemptMove(');
    expect(gateAt >= 0 && guardAt > gateAt && callAt > guardAt, 'the gate guard precedes the call');
  });

  // ── F8 ───────────────────────────────────────────────────────────────────
  await check('F8 the box starts unticked, and every consent step re-unticks it', () => {
    expect(/^useState\(false\)$/.test(declText(claim, 'ticked') || '') || /const \[ticked, setTicked\] = useState\(false\);/.test(claimText),
      'ticked starts false');
    expect(/setTicked\(false\);[\s\S]*show\(\{ step: 'consent'/.test(declText(claim, 'showConsent')), 'showConsent unticks first');
  });
  await check('F8 Make the move is disabled until ticked; the named CTA is loading and disabled while sending', () => {
    const consent = actionBranches(claim).consent;
    const make = jsxMounts(claim, 'Button', consent).filter((m) => m.attrs.testID === '"fa-claim.make-move"');
    expect(make.length === 1 && /!ticked/.test(make[0].attrs.disabled || '') && make[0].attrs.loading === '{busy}',
      `consent Make the move disabled=${make[0] && make[0].attrs.disabled} loading=${make[0] && make[0].attrs.loading}`);
    expect(make[0].attrs.onPress === '{() => void send(consentEcho(view.block), false)}', 'Make the move sends the echo');
    const ready = actionBranches(claim).ready;
    const cta = jsxMounts(claim, 'Button', ready).filter((m) => m.attrs.testID === '"fa-claim.make-move"');
    expect(cta.length === 1 && cta[0].attrs.loading === '{busy}', 'the named CTA is loading (inactive) while busy');
    expect(/const busy = sending \|\| loadingConsent;/.test(claimText), 'busy covers sending');
  });

  // ── F9 ───────────────────────────────────────────────────────────────────
  {
    const h = harness();
    h.respond(() => response(200, { status: 'complete', move_kind: 'add', result: 'accepted', league_platform: 'sleeper',
      attempt_id: 'x', title: 't', lines: [] }));
    await check('F9 one attempt_id per tap: minted once, in the body and on write_attempted; a second tap gets a new one', async () => {
      const a = await h.faMove.attemptMove({ move: SUBMIT, surface: 'free_agents', request: REQ });
      const b = await h.faMove.attemptMove({ move: SUBMIT, surface: 'free_agents', request: REQ });
      eq(h.rands(), 32, 'Math.random draws (16 bytes per id, two taps)');
      eq(h.requests.map((r) => r.body.attempt_id), [a.attemptId, b.attemptId], 'body attempt_ids');
      expect(a.attemptId !== b.attemptId && V4.test(a.attemptId) && V4.test(b.attemptId), `ids ${a.attemptId} ${b.attemptId}`);
      eq(h.events.filter((e) => e.name === 'fa_move_write_attempted').map((e) => e.props.attempt_id),
        [a.attemptId, b.attemptId], 'event attempt_ids');
      expect(calls(fa, 'newAttemptId').length === 1 && calls(fa, 'newAttemptId', decl(fa, 'attemptMove')).length === 1,
        'newAttemptId is called once, inside attemptMove');
      expect(calls(claim, 'newAttemptId').length === 0 && calls(claim, 'uuidv4').length === 0, 'ClaimSheet mints nothing');
    });
  }

  // ── F10 ──────────────────────────────────────────────────────────────────
  await check('F10 no steps block and no clipboard in ClaimSheet, in any mode', () => {
    eq(literals(claim).filter((t) => /fa-claim\.steps?\b|fa-claim\.step\./.test(t)), [], 'steps testIDs');
    eq(['clipboardText', 'copyText', 'Clipboard', 'setStringAsync'].map((n) => identRefs(claim, n)), [0, 0, 0, 0],
      'clipboard identifiers');
    expect(!/expo-clipboard|\.\/clipboard|utils\/clipboard/.test(claimText), 'a clipboard import');
  });

  // ── F11 ──────────────────────────────────────────────────────────────────
  await check('F11 no consent text anywhere in mobile/src (R15.8 v1/v2 phrases, copy_version strings)', () => {
    const phrases = [/I authorize Fleeced/i, /Let Fleeced make roster moves/i, /Your OK lasts/i,
      /unofficial Sleeper connection/i, /sleeper-roster-moves-v/i, /add and drop players in your/i];
    const hits = [];
    for (const f of srcFiles()) {
      const sf = ts.createSourceFile(f, fs.readFileSync(f, 'utf8'), ts.ScriptTarget.Latest, true,
        f.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
      for (const t of literals(sf)) if (phrases.some((p) => p.test(t))) hits.push(`${path.basename(f)}: ${t.slice(0, 60)}`);
    }
    eq(hits, [], 'consent literals');
  });
  {
    const h = harness();
    await check('F11 the echo is the received {copy_version, locale}, exactly; an incomplete block is refused (→ hand-off)', async () => {
      const M = h.faMove;
      eq(M.consentEcho(M.readConsentBlock(BLOCK)), { copy_version: 'test-copy-v9', locale: 'en-ZZ' }, 'echo');
      for (const k of Object.keys(BLOCK)) {
        const partial = { ...BLOCK };
        delete partial[k];
        expect(M.readConsentBlock(partial) === null, `a block without ${k} was accepted`);
      }
      expect(M.readConsentBlock({ ...BLOCK, body: [] }) === null, 'an empty body was accepted');
      h.respond(() => response(200, { status: 'complete', move_kind: 'add', result: 'accepted', league_platform: 'sleeper',
        attempt_id: 'x', title: 't', lines: [] }));
      await M.attemptMove({ move: SUBMIT, surface: 'free_agents', request: { ...REQ, consent: M.consentEcho(BLOCK) } });
      eq(h.requests[0].body.consent, { copy_version: 'test-copy-v9', locale: 'en-ZZ' }, 'the wire echo');
      eq(h.events[0].props.consent_ticked, true, 'consent_ticked');
    });
  }
  await check('F11 the consent step renders only the server block (title, body, checkbox_label, this_move, button_label)', () => {
    const consentBody = claimText.slice(claimText.indexOf("if (view.step === 'consent') {\n    const thisMove"), claimText.indexOf("} else if (view.step === 'result') {"));
    for (const f of ['view.block.title', 'view.block.body.map', 'view.block.this_move']) {
      expect(consentBody.includes(f), `the step renders ${f}`);
    }
    const consent = actionBranches(claim).consent.getText(claim);
    expect(/view\.block\.checkbox_label/.test(consent) && /label=\{view\.block\.button_label\}/.test(consent), 'box and button labels');
    expect(/case 'unavailable':\s*show\(\{ step: 'handoff', line: slot\('unavailable_line'\) \}\);/.test(declText(claim, 'openConsent')),
      'F4 (ux-lead): no consent text from the server → the hand-off');
  });

  // ── F12 ──────────────────────────────────────────────────────────────────
  await check("F12 a terminal result invalidates the ['free-agents', leagueId] prefix (both hosts' keys)", () => {
    expect(/invalidateQueries\(\{ queryKey: \['free-agents', leagueId\] \}\)/.test(declText(claim, 'refreshList')),
      'refreshList');
    expect(/if \(plan\.refresh\) refreshList\(\);/.test(declText(claim, 'apply')), 'apply() refreshes on plan.refresh');
    const h = harness();
    const cp = h.plan.copyFns(SUBMIT, { league: 'L', name: 'A' });
    const C = (s, b) => h.faMove.classifyMoveError(apiErr(h, s, b));
    expect(h.plan.planResponse({ status: 'complete', title: 't', lines: [] }, cp).refresh
      && h.plan.planResponse({ status: 'pending', title: 't', lines: [] }, cp).refresh, '8 / 9 refresh');
    for (const [st, code] of [[422, 'player_unavailable'], [502, 'sleeper_write_failed'], [503, 'sleeper_unconfigured'],
      [409, 'sleeper_rejected'], [400, 'bad_request'], [502, 'sleeper_outcome_unknown'], [422, 'roster_full_drop_required'],
      [422, 'asset_not_owned']]) {
      expect(h.plan.planFailure(C(st, { error: code }), cp).refresh === true, `${code} refreshes`);
    }
    expect(/queryKey: \['free-agents', leagueId, filter\]/.test(read(FREE_AGENTS))
      && /queryKey: \['free-agents', claim\?\.leagueId, 'ALL'\]/.test(read(USAGE_TRENDS)), 'both host keys sit under the prefix');
  });

  // ── F13 ──────────────────────────────────────────────────────────────────
  {
    const h = harness();
    h.respond(() => response(200, { status: 'pending', move_kind: 'claim', result: 'accepted', league_platform: 'sleeper',
      attempt_id: 'x', title: 't', lines: [] }));
    await check('F13 the move goes through the shared client: its write listener sees the path on send and settle', async () => {
      await h.faMove.attemptMove({ move: SUBMIT, surface: 'usage_trends', request: REQ });
      eq(h.requests.map((r) => [r.method, r.url]), [['POST', 'https://example.invalid/api/league/free-agents/move']], 'requests');
      eq(h.writes, ['/api/league/free-agents/move', '/api/league/free-agents/move'], '_noteWrite');
    });
  }
  await check('F13 no bare fetch in the move path; the sheet adds no device-page hook; K-F5 names the same path', () => {
    for (const [sf, rel] of [[fa, FA_MOVE], [claim, CLAIM]]) {
      expect(calls(sf, 'fetch').filter((c) => ts.isIdentifier(c.expression)).length === 0, `${rel} calls fetch`);
    }
    expect(/apiRequest<MoveResponse>\(FA_MOVE_PATH/.test(declText(fa, 'submitMove')), 'submitMove → apiRequest');
    expect(!/devicePage|discardAllDevicePages|setOnWriteRequest/.test(claimText), 'ClaimSheet touches the device page');
    const dp = read(DEVICE_PAGE);
    expect(/export const FA_MOVE_PATH = '\/api\/league\/free-agents\/move';/.test(dp)
      && /export const FA_MOVE_PATH = '\/api\/league\/free-agents\/move';/.test(faText)
      && /p === FA_MOVE_PATH/.test(dp), 'discardsDevicePages and faMove.ts name one path');
  });

  // ── F14 ──────────────────────────────────────────────────────────────────
  {
    const h = harness();
    await check("F14 error_code is always one of C3's 21 platform-free values; kind only when the body carries one", () => {
      eq([...h.faMove.FA_MOVE_ERROR_CODES], C3, 'FA_MOVE_ERROR_CODES');
      const inputs = [new TypeError('x'), apiErr(h, 0, null, true), apiErr(h, 0, null), apiErr(h, 503, 'html'),
        apiErr(h, 418, {}), apiErr(h, 418, { error: 'teapot' })];
      for (const p of ['sleeper', 'mfl', 'espn']) {
        for (const s of ['not_linked', 'expired', 'unconfigured', 'rejected', 'write_failed', 'outcome_unknown']) {
          inputs.push(apiErr(h, 502, { error: `${p}_${s}` }), apiErr(h, 502, { error: `${p}_${s}`, kind: 'network' }));
        }
      }
      for (const c of C3) inputs.push(apiErr(h, 409, { error: c }), apiErr(h, 409, { error: c, kind: 'bogus' }));
      for (const err of inputs) {
        const f = h.faMove.classifyMoveError(err);
        expect(C3.includes(f.errorCode) && !/^(sleeper|mfl|espn)_/.test(f.errorCode), `error_code ${f.errorCode}`);
        const sentKind = err && err.body && (err.body.kind === 'network' || err.body.kind === 'roster_read');
        expect(sentKind ? f.kind === err.body.kind : !('kind' in f), `kind ${JSON.stringify(f.kind)} for ${JSON.stringify(err.body)}`);
      }
    });
    await check('F14 write_failed carries kind only when present, and never the raw code', async () => {
      let next = 0;
      const bodies = [[502, { error: 'sleeper_write_failed', kind: 'roster_read' }], [502, { error: 'mfl_write_failed' }]];
      h.respond(() => response(...bodies[next++]));
      await h.faMove.attemptMove({ move: SUBMIT, surface: 'free_agents', request: REQ });
      await h.faMove.attemptMove({ move: { ...SUBMIT, league_platform: 'mfl' }, surface: 'free_agents', request: REQ });
      const failed = h.events.filter((e) => e.name === 'fa_move_write_failed').map((e) => e.props);
      eq(failed.map((p) => [p.error_code, p.status, p.kind, 'kind' in p, p.league_platform]),
        [['write_failed', 502, 'roster_read', true, 'sleeper'], ['write_failed', 502, undefined, false, 'mfl']], 'events');
      expect(failed.every((p) => !('platform' in p)), 'a prop named platform');
    });
  }

  // ── F15 ──────────────────────────────────────────────────────────────────
  {
    const h = harness();
    await check('F15 no fa_move_* event outside `submit` (null, absent, handoff, unsupported, no platform)', async () => {
      for (const m of [null, undefined, { ...SUBMIT, mode: 'handoff' }, { ...SUBMIT, mode: 'unsupported' },
        { ...SUBMIT, league_platform: null }]) {
        expect(h.faMove.trackFaMove(m, 'fa_move_connect_shown', { surface: 'free_agents', reason: 'not_linked' }) === false,
          `emitted for ${JSON.stringify(m)}`);
      }
      h.respond(() => response(502, { error: 'sleeper_write_failed' }));
      await h.faMove.attemptMove({ move: { ...SUBMIT, mode: 'handoff' }, surface: 'free_agents', request: REQ });
      eq(h.events, [], 'events');
    });
  }
  {
    const triggers = [
      ['outcome_unknown', (h) => h.respond(() => response(502, { error: 'sleeper_outcome_unknown', message: 'm' })), 502],
      ['move_in_progress', (h) => h.respond(() => response(409, { error: 'move_in_progress', message: 'm' })), 409],
      ['internal_error', (h) => h.respond(() => response(500, { error: 'internal_error', message: 'm' })), 500],
      ['timeout', () => {}, 0],
      ['network', (h) => h.respond(() => Promise.reject(new TypeError('Network request failed'))), 0],
      ['unknown', (h) => h.respond(() => response(503, '<html>Service Unavailable</html>')), 503],
    ];
    for (const [code, arm, status] of triggers) {
      await check(`F15 state 12 trigger \`${code}\` → write_failed {error_code: ${code}, status: ${status}}, state unknown`, async () => {
        const h = harness();
        arm(h);
        const run = watch(h.faMove.attemptMove({ move: SUBMIT, surface: 'free_agents', request: REQ }));
        await h.time.advance(code === 'timeout' ? 91_000 : 0);
        await flush();
        expect(run.state === 'resolved', `attempt ${run.state}`);
        eq([run.value.failure.state, run.value.failure.errorCode, run.value.failure.status], ['unknown', code, status], 'failure');
        const failed = h.events.filter((e) => e.name === 'fa_move_write_failed');
        eq(failed.map((e) => [e.props.error_code, e.props.status, e.props.league_platform, e.props.surface]),
          [[code, status, 'sleeper', 'free_agents']], 'event');
      });
    }
  }

  // ── F16 ──────────────────────────────────────────────────────────────────
  await check('F16 state 7 is not dismissible: backdrop, Cancel and onRequestClose all go through requestClose, a no-op while busy', () => {
    expect(/^function requestClose\(\) \{[\s\S]*?if \(busy\) return;\s*onClose\(\);\s*\}$/.test(declText(claim, 'requestClose')),
      'requestClose');
    const modals = jsxMounts(claim, 'Modal');
    expect(modals.length === 2 && modals.every((m) => m.attrs.onRequestClose === '{requestClose}'), 'every Modal\'s onRequestClose');
    const backdrops = jsxMounts(claim, 'Pressable').filter((m) => m.attrs.style === '{sheetStyles.backdrop}');
    expect(backdrops.length === 2 && backdrops.every((m) => m.attrs.onPress === '{requestClose}'), 'every backdrop');
    expect(!jsxMounts(claim, 'Modal').some((m) => m.attrs.onRequestClose === '{onClose}'), 'a Modal closing straight to onClose');
  });
  await check('F16 Cancel shows disabled (not hidden) while busy; the CTA is busy for VoiceOver; the 8 s line is wired', () => {
    const cancels = jsxMounts(claim, 'Button').filter((m) => m.attrs.label === '"Cancel"');
    expect(cancels.length === 1 && cancels[0].attrs.disabled === '{busy}' && cancels[0].attrs.onPress === '{requestClose}', 'Cancel');
    expect(/\{view\.step === 'result' \? null : \(\s*<Button label="Cancel"/.test(claimText), 'Cancel hides only on results');
    expect(/accessibilityState=\{\{ disabled: inactive, busy: loading \}\}/.test(read(BUTTON)), 'Button: loading → busy');
    expect(/setTimeout\(\(\) => setStillSending\(true\), FA_MOVE_STILL_SENDING_MS\)/.test(claimText)
      && /export const FA_MOVE_STILL_SENDING_MS = 8_000;/.test(faText), 'the still-sending timer');
    const ready = actionBranches(claim).ready.getText(claim);
    expect(/\{stillSending \? <Text[^>]*>\{slot\('still_sending'\)\}<\/Text> : null\}/.test(ready), 'the still-sending line');
  });

  // ── F17 ──────────────────────────────────────────────────────────────────
  {
    const h = harness();
    h.setNet({ isConnected: false, isInternetReachable: false });
    h.respond(() => response(200, {}));
    await check('F17 offline at the tap: no request, no attempt_id, no event; NetInfo is read first', async () => {
      const out = await h.faMove.attemptMove({ move: SUBMIT, surface: 'free_agents', request: REQ });
      eq(out, { sent: false }, 'outcome');
      eq([h.requests.length, h.rands(), h.events.length, h.writes.length], [0, 0, 0, 0], '[requests, Math.random draws, events, writes]');
      eq(h.log, ['netinfo'], 'call order');
      h.setNet({ isConnected: true });
      await h.faMove.attemptMove({ move: SUBMIT, surface: 'free_agents', request: REQ });
      eq(h.log.slice(1, 4), ['netinfo', 'rand', 'track'], 'online: NetInfo, then the mint, then attempted');
    });
  }
  await check('F17 the sheet shows offline as state 11 (the named CTA with a --neg "nothing was sent" line), never 12', () => {
    const apply = declText(claim, 'applyOutcome');
    const offline = apply.slice(apply.indexOf('if (!outcome.sent) {'), apply.indexOf('pendingConsentRef.current = null;'));
    expect(/apply\(planNotSent\(copy\)\);/.test(offline) && !/'result'|'unknown'/.test(offline), 'the offline branch');
    const h = harness();
    const cp = h.plan.copyFns(SUBMIT, { league: 'L', name: 'A' });
    const v = h.plan.planNotSent(cp).view;
    expect(v.step === 'ready' && v.ctaNotice.tone === 'neg' && /nothing was sent/.test(v.ctaNotice.text), `planNotSent ${JSON.stringify(v)}`);
    const k = h.plan.planFailure(h.faMove.classifyMoveError(apiErr(h, 502, { error: 'sleeper_write_failed', kind: 'network', message: 'm' })), cp).view;
    expect(k.step === 'ready' && k.ctaNotice.text === 'm' && k.ctaNotice.tone === 'neg', "a server 502 with a kind (state 11)");
  });

  // ── Review round 1: L1, R1, P1, T7 ───────────────────────────────────────
  {
    const h = harness();
    const M = h.faMove;
    await check('L1 links: the block\'s own when it sends them; else the app\'s Terms and Privacy at the API base', () => {
      const own = M.readConsentBlock({ ...BLOCK, links: [{ label: 'Terms', url: 'https://legal.example/terms' }] });
      eq(M.consentLinks(own), [{ label: 'Terms', url: 'https://legal.example/terms' }], 'server links');
      eq(M.consentLinks(M.readConsentBlock(BLOCK)), [
        { label: 'Terms', url: `${h.client.getBaseUrl()}/terms` },
        { label: 'Privacy', url: `${h.client.getBaseUrl()}/privacy` },
      ], 'fallback links');
      const junk = M.readConsentBlock({ ...BLOCK, links: [{ label: 'x', url: 'javascript:alert(1)' }, { label: 'y', url: 'http://a.b' },
        { label: '', url: 'https://a.b' }, null, 'https://a.b'] });
      expect(junk && !('links' in junk), `unsafe or empty links kept: ${JSON.stringify(junk && junk.links)}`);
      eq(M.consentLinks(junk).map((l) => l.url), [`${h.client.getBaseUrl()}/terms`, `${h.client.getBaseUrl()}/privacy`],
        'nothing usable → the app\'s own');
      expect(/const base = getBaseUrl\(\);[\s\S]*`\$\{base\}\/terms`[\s\S]*`\$\{base\}\/privacy`/.test(declText(fa, 'consentLinks')),
        'consentLinks builds from getBaseUrl(), as PaywallScreen\'s openLegal does');
      eq(wording(fa).filter((t) => /^https?:\/\//.test(t)), [], 'a hard-coded base URL in faMove.ts');
    });
  }
  await check('L1 the consent step renders the links row and opens each through openPlatform, no catch, no Linking', () => {
    const consent = actionBranches(claim).consent.getText(claim);
    expect(/consentLinks\(view\.block\)\.map\(/.test(consent) && /onPress=\{\(\) => openConsentLink\(l\.url\)\}/.test(consent)
      && /accessibilityRole="link"/.test(consent), 'the links row');
    const open = declText(claim, 'openConsentLink');
    expect(/^\(url: string\) => \{\s*void openPlatform\(\{[^}]*httpsUrl: url[^}]*appMissing: 'https'[^}]*\}\);\s*\}$/.test(open),
      `openConsentLink = ${open.slice(0, 120)}`);
    expect(!/\.catch\(/.test(claimText), 'a .catch in ClaimSheet');
    expect(identRefs(claim, 'Linking') === 0, 'Linking in ClaimSheet');
  });
  {
    const h = harness();
    const M = h.faMove;
    await check('R1 the block\'s `reason` is fa_move_consent_shown\'s reason; absent, the client\'s reading; unknown values dropped', () => {
      const first = { consentUntil: null, shownVersion: null, offeredVersion: 'v1', withdrawnHere: false };
      eq(M.consentShownReason(M.readConsentBlock({ ...BLOCK, reason: 'withdrawn' }), first), 'withdrawn', 'server reason');
      eq(M.consentShownReason(M.readConsentBlock(BLOCK), first), 'first', 'inferred');
      eq(M.consentShownReason(M.readConsentBlock(BLOCK), { ...first, consentUntil: '2020-01-01T00:00:00Z' }), 'lapsed', 'inferred lapsed');
      const bogus = M.readConsentBlock({ ...BLOCK, reason: 'because' });
      expect(bogus && !('reason' in bogus), 'an unknown reason kept');
      eq([...M.CONSENT_REASONS], ['first', 'lapsed', 'version', 'withdrawn'], 'the granted set');
    });
  }
  await check('R1 showConsent reports consentShownReason(block, …) on fa_move_consent_shown', () => {
    const t = declText(claim, 'showConsent');
    expect(/const reason = consentShownReason\(block, \{/.test(t)
      && /trackFaMove\(m, 'fa_move_consent_shown', \{ surface: analyticsSurface, reason \}\)/.test(t), 'showConsent');
  });
  await check('P1 the claims-pending store: empty at start, keyed by league + player, in memory only', () => {
    const zustand = require(path.join(__dirname, '..', 'node_modules', 'zustand'));
    const store = load('src/state/claimsPending.ts', only({ zustand }), {});
    const keys = () => store.useClaimsPending.getState().keys;
    eq(keys().size, 0, 'empty at start');
    store.markClaimPending('L1', '4046');
    eq([store.isClaimPending(keys(), 'L1', '4046'), store.isClaimPending(keys(), 'L2', '4046'),
      store.isClaimPending(keys(), 'L1', '9999'), store.isClaimPending(keys(), undefined, '4046')],
    [true, false, false, false], 'lookups');
    expect(!/AsyncStorage|SecureStore|persist/.test(read('src/state/claimsPending.ts').replace(/^\s*\/\/.*$/gm, '')), 'persisted');
  });
  await check('P1 only a state-9 (pending) result marks it, and only the Free Agents row reads it', () => {
    const everywhere = srcFiles().reduce((k, f) => {
      const sf = ts.createSourceFile(f, fs.readFileSync(f, 'utf8'), ts.ScriptTarget.Latest, true,
        f.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
      return k + calls(sf, 'markClaimPending').length;
    }, 0);
    eq(everywhere, 1, 'markClaimPending call sites');
    expect(/if \(plan\.markPending\) markClaimPending\(leagueId, row\.player_id\);/.test(declText(claim, 'apply')), 'apply() marks on plan.markPending');
    const h = harness();
    const cp = h.plan.copyFns(SUBMIT, { league: 'L', name: 'A' });
    eq([h.plan.planResponse({ status: 'pending', title: 't', lines: [] }, cp).markPending,
      h.plan.planResponse({ status: 'complete', title: 't', lines: [] }, cp).markPending], [true, false], 'marked only when pending');
    const faSrc = read(FREE_AGENTS);
    expect(/claimPending=\{isClaimPending\(pendingClaims, leagueId, item\.player_id\)\}/.test(faSrc), 'the row is told');
    expect(/statsSlot=\{\s*claimPending \? \(\s*<Text style=\{styles\.dropLine\} numberOfLines=\{1\}>\s*\{FA_MOVE_FALLBACK_COPY\.claim_pending\}\s*<\/Text>\s*\) : drop \? \(/.test(faSrc),
      'the row shows "Claim pending" only when pending, else the drop line as before');
    eq(read(FA_MOVE).match(/claim_pending: '([^']+)'/)[1], 'Claim pending', 'the neutral string');
  });
  {
    const h = harness();
    const M = h.faMove;
    await check('T7 contract §7: {bid} is "$N" (an empty FAAB bid is $0); {date} short, no time; a missing known placeholder falls back', () => {
      eq([M.bidText(7), M.bidText(0)], ['$7', '$0'], 'bidText');
      const sel = h.plan.moveSelection({ rowName: 'A', kind: 'claim', dropId: null, candidates: [], faab: true, bid: '',
        copy: undefined, platform: 'sleeper' });
      eq([sel.bid, sel.ctaLabel, sel.request.faab_bid], [0, 'Claim A for $0', 0], 'an empty FAAB bid is $0');
      const d = M.windowDateText('2026-11-08T15:00:00Z');
      expect(/^[A-Z][a-z]{2} \d{1,2}$/.test(d), `{date} = ${d}`);
      eq(M.moveCopy({ waiver_line: 'Bid {bid}' }, 'waiver_line', { bid: '$7' }, 'sleeper'), 'Bid $7', 'server template, filled');
      eq(M.moveCopy({ cta_add: 'Add {add}, drop {drop}' }, 'cta_add', { add: 'A' }, 'sleeper'), 'Add A', 'missing {drop} → the fallback');
      eq(M.moveCopy({ league_line: 'In {league}' }, 'league_line', {}, 'sleeper'), null, 'no value anywhere → not shown');
      eq(M.moveCopy({ turn_off: 'Off {later}' }, 'turn_off', {}, 'sleeper'), 'Off {later}', 'unknown placeholder kept');
    });
  }

  // ── Review round 2: X1–X12 ───────────────────────────────────────────────
  {
    const h = harness();
    await check('X1 attempt_id with no crypto (Hermes): v4-shaped from Math.random, and 1,000 calls are 1,000 values', () => {
      const ids = Array.from({ length: 1000 }, () => h.faMove.newAttemptId());
      const bad = ids.filter((id) => !V4.test(id));
      eq(bad.slice(0, 3), [], 'ids not v4-shaped');
      eq(new Set(ids).size, 1000, 'distinct ids');
      expect(h.rands() === 16000, `Math.random draws ${h.rands()}`);
      expect(!/from '\.\/_queue'/.test(faText), 'faMove.ts still imports _queue');
    });
    await check('X1 with crypto.getRandomValues present it is used, and the id is still v4-shaped', () => {
      let used = 0;
      const t = harness();
      const withCrypto = load(FA_MOVE, only({
        './client': t.client, './league': {}, './events': { track: () => {} },
        '@react-native-community/netinfo': { default: { fetch: async () => ({ isConnected: true }) } },
      }), t.time, { crypto: { getRandomValues: (a) => { used += 1; for (let i = 0; i < a.length; i++) a[i] = (i * 37) & 255; return a; } } });
      const id = withCrypto.newAttemptId();
      expect(used === 1 && V4.test(id), `used ${used}, id ${id}`);
    });
  }
  {
    const h = harness();
    const cp = h.plan.copyFns(SUBMIT, { league: 'L', name: 'A' });
    await check('X2 a 10a the client didn\'t foresee (open slots): the drop list shows, with the server\'s message, focus and a refresh', () => {
      const plan = h.plan.planFailure(h.faMove.classifyMoveError(apiErr(h, 422, { error: 'roster_full_drop_required', message: 'Your roster is full.' })), cp);
      expect(plan.requireDrop && plan.refresh && plan.scrollToDrop, `plan ${JSON.stringify(plan)}`);
      eq(plan.view, { step: 'ready', dropNotice: { text: 'Your roster is full.', tone: 'neg' } }, 'view');
      eq([h.plan.dropListShown({ openSlots: 2, candidates: 0, requireDrop: true }),
        h.plan.dropListShown({ openSlots: 2, candidates: 3, requireDrop: false }),
        h.plan.dropListShown({ openSlots: 0, candidates: 0, requireDrop: false })], [true, false, true], 'dropListShown');
      expect(/const showDropList = dropListShown\(\{ openSlots, candidates: candidates\.length, requireDrop \}\);/.test(claimText), 'the sheet uses it');
      expect(/\{dropNotice \? \(\s*<View ref=\{focusRef\} accessible>/.test(claimText), 'the message takes focus');
    });
    await check('X3 a drop a refresh took away: the CTA reads "Add A" and the body has no drop_player_id (one source)', async () => {
      const base = { rowName: 'A', kind: 'add', dropId: 'b1', faab: false, bid: '', copy: undefined, platform: 'sleeper' };
      const before = h.plan.moveSelection({ ...base, candidates: [{ id: 'b1', name: 'B' }] });
      eq([before.ctaLabel, before.request.drop_player_id], ['Add A, drop B', 'b1'], 'B listed');
      const after = h.plan.moveSelection({ ...base, candidates: [{ id: 'c1', name: 'C' }] });
      eq([after.ctaLabel, 'drop_player_id' in after.request, after.drop], ['Add A', false, null], 'B gone');
      h.respond(() => response(200, { status: 'complete', move_kind: 'add', result: 'accepted', league_platform: 'sleeper', attempt_id: 'x', title: 't', lines: [] }));
      await h.faMove.attemptMove({ move: SUBMIT, surface: 'free_agents', request: { league_id: 'L', add_player_id: 'a1', ...after.request } });
      expect(!('drop_player_id' in h.requests[0].body), `body ${JSON.stringify(h.requests[0].body)}`);
      expect(/\.\.\.sel\.request,/.test(declText(claim, 'send')) && /fillTemplate\(block\.this_move, \{ cta: ctaLabel,/.test(claimText)
        && /if \(dropId && !candidates\.some\(\(c\) => c\.id === dropId\)\) setDropId\(null\);/.test(claimText),
      'the request, the CTA and "This move" all come from the selection; a vanished drop is cleared');
    });
  }
  {
    const cases = [
      ['offline', (h) => h.setNet({ isConnected: false }), 'offline', 0],
      ['network error', (h) => h.respond(() => Promise.reject(new TypeError('Network request failed'))), 'not_sent', 1],
      ['timeout', () => {}, 'not_sent', 1],
      ['500', (h) => h.respond(() => response(500, { error: 'internal_error' })), 'unavailable', 1],
      ['404 (older server)', (h) => h.respond(() => response(404, '<html>')), 'unavailable', 1],
      ['200 valid', (h) => h.respond(() => response(200, { platform: 'sleeper', valid: true })), 'valid', 1],
      ['200 block', (h) => h.respond(() => response(200, { platform: 'sleeper', valid: false, consent: BLOCK })), 'consent', 1],
      ['200 no block', (h) => h.respond(() => response(200, { platform: 'sleeper', valid: false })), 'unavailable', 1],
    ];
    for (const [name, arm, want, gets] of cases) {
      await check(`X4 consent step: ${name} → ${want}${gets ? '' : ', and no GET at all'}`, async () => {
        const h = harness();
        arm(h);
        const run = watch(h.faMove.fetchConsentStep('sleeper'));
        // A GET is retried on a network error (api/client.ts), then gives up.
        await h.time.advance(name === 'timeout' || name === 'network error' ? 20_000 : 0);
        await flush();
        expect(run.state === 'resolved', `step ${run.state}`);
        eq([run.value.kind, h.requests.filter((r) => /platform-write-consent/.test(r.url)).length > 0 ? 1 : 0], [want, gets], 'step, GET');
        expect(h.log[0] === 'netinfo', 'NetInfo first');
      });
    }
    await check('X4 the sheet: offline or no answer at the tap → state 11 (planNotSent); after Connect → Ready', () => {
      const t = declText(claim, 'openConsent');
      expect(/case 'offline':\s*case 'not_sent':\s*if \(sendIfValid\) apply\(planNotSent\(copy\)\);\s*else show\(\{ step: 'ready' \}\);/.test(t), 'openConsent');
      expect(/const step = await fetchConsentStep\(m\.league_platform\);/.test(t), 'reads through fetchConsentStep');
    });
  }
  {
    await check('X5 Usage Trends\' pre-read: a plain call, bounded at 3 s, giving only move and the tapped row', async () => {
      const h = harness();
      h.respond(() => response(200, { move: SUBMIT, free_agents: [{ player_id: 'p1', name: 'A', move_kind: 'claim', move_line: 'x', extra: 1 }], roster_capacity: {} }));
      const out = await h.faMove.readMoveCapability('L1', 'p1');
      eq(out, { move: SUBMIT, row: { move_kind: 'claim', move_line: 'x' } }, 'capability + row');
      eq(h.requests.map((r) => r.url), ['https://example.invalid/api/league/free-agents?league_id=L1'], 'one plain read');
      const slow = harness();
      const run = watch(slow.faMove.readMoveCapability('L1', 'p1'));
      await slow.time.advance(2_999);
      expect(run.state === 'pending', 'gave up before 3 s');
      await slow.time.advance(1);
      eq(run.value, { move: null, row: {} }, 'no answer in 3 s → legacy');
      const old = harness();
      old.respond(() => response(200, { free_agents: [{ player_id: 'p1', move_mode: 'handoff', move_line: 'x' }] }));
      eq(await old.faMove.readMoveCapability('L1', 'p1'), { move: null, row: {} }, 'today\'s server: nothing used');
    });
    await check('X5 Usage Trends never touches the sheet\'s cache, and shows the tapped Add busy while it reads', () => {
      const ut = read(USAGE_TRENDS);
      expect(!/fetchQuery|setQueryData|queryKey: \['free-agents', lgId/.test(ut), 'the sheet\'s key is written');
      expect(/setAdding\(\{ playerId: p\.player_id, leagueId: lgId \}\);[\s\S]*finally \{\s*setAdding\(null\);\s*\}/.test(declText(parse(USAGE_TRENDS), 'doAdd')),
        'busy from the tap to the routing');
      for (const f of ['src/components/UsageTrendCard.tsx', 'src/components/UsageStatsTable.tsx', 'src/components/UsageLeagueList.tsx']) {
        expect(/<ActivityIndicator size="small"/.test(read(f)) && /busy: (adding|addingLeagueId === row\.league_id)/.test(read(f)), `${f}: no busy Add`);
      }
    });
  }
  {
    const h = harness();
    await check('X6 the pin decision is pure, measured on the content, with hysteresis: no flip-flop at the boundary', () => {
      const max = 600; // half = 300
      const P = h.plan.actionBlockPinned;
      const C = h.plan.PINNED_BLOCK_CHROME;
      for (const content of [300 - C - 30, 300 - C - 10, 300 - C, 300 - C + 1, 300 - C + 10]) {
        let pinned = true;
        const seen = [];
        for (let i = 0; i < 6; i++) { pinned = P(pinned, content, max); seen.push(pinned); }
        expect(seen.every((x) => x === seen[seen.length - 1]), `content ${content}: ${seen}`);
      }
      // Re-measured with a few points of jitter around the boundary, a decision holds.
      let pinned = P(true, 300 - C + 5, max);
      expect(pinned === false, 'over half unpins');
      for (const jitter of [-5, 3, -10, 0, -15]) pinned = P(pinned, 300 - C + jitter, max);
      expect(pinned === false, 'jitter inside the band re-pinned');
      expect(P(false, 300 - C - h.plan.PIN_HYSTERESIS - 1, max) === true, 'clearly under re-pins');
      expect(/style=\{sheetStyles\.blockContent\}\s*onLayout=\{\(e\) => \{\s*const h = e\.nativeEvent\.layout\.height;\s*setPinned\(\(p\) => actionBlockPinned\(p, h, windowHeight \* SHEET_MAX_FRACTION\)\);/.test(claimText),
        'the sheet measures the content and asks the pure function');
    });
  }
  {
    const h = harness();
    const C = (st, b) => h.faMove.classifyMoveError(apiErr(h, st, b));
    await check('X7 MFL: connect / verify / rejected render the unsupported explanation, never a dead Connect', () => {
      const mfl = h.plan.copyFns({ ...SUBMIT, league_platform: 'mfl' }, { league: 'L', name: 'A' });
      for (const [st, code] of [[409, 'mfl_not_linked'], [409, 'mfl_expired'], [403, 'verification_required'], [409, 'mfl_rejected']]) {
        eq(h.plan.planFailure(C(st, { error: code }), mfl).view, { step: 'unsupported' }, code);
      }
      const espn = h.plan.copyFns({ ...SUBMIT, league_platform: 'espn' }, { league: 'L', name: 'A' });
      eq(h.plan.planFailure(C(409, { error: 'espn_not_linked' }), espn).view.step, 'connect', 'ESPN keeps its connect step');
      eq(h.plan.initialView({ ...SUBMIT, league_platform: 'mfl', connect: 'not_linked' }, {}, mfl), { step: 'unsupported' }, 'MFL at open');
      expect(/const reason = NO_ADD_REASON\[platform === 'sleeper' \? 'local' : platform\];/.test(claimText), 'the sheet shows NO_ADD_REASON');
    });
    await check('X7 a non-Sleeper row held in hand-off opens the sheet with the server\'s line (else a neutral one), not NO_ADD_REASON', () => {
      const espnMove = { ...SUBMIT, league_platform: 'espn' };
      const held = { move_mode: 'handoff', move_line: 'A recent move wasn\'t confirmed.' };
      expect(h.faMove.faMoveOpensSheet(espnMove, held), 'the host opens the sheet');
      const espn = h.plan.copyFns(espnMove, { league: 'L', name: 'A' });
      eq(h.plan.initialView(espnMove, held, espn), { step: 'handoff', line: 'A recent move wasn\'t confirmed.' }, 'server line');
      eq(h.plan.initialView(espnMove, { move_mode: 'handoff' }, espn),
        { step: 'handoff', line: "This move can't be made from Fleeced right now. Check ESPN." }, 'fallback');
      expect(/else navigation\.navigate\('EspnConnect'\);/.test(claimText) && !/navigate\('EspnConnect',/.test(claimText), 'EspnConnect without reason: send');
    });
  }
  {
    await check('X8 Settings: a 404 is valid: false; a 500 stays an error; a failed DELETE keeps the row with a neutral line', async () => {
      const h = harness();
      let next = 0;
      const answers = [[404, '<html>'], [200, { platform: 'sleeper', valid: false, status_line: null }], [500, { error: 'internal_error' }]];
      h.respond(() => response(...answers[next++]));
      eq((await h.faMove.readConsentStatus('sleeper')).valid, false, '404');
      eq((await h.faMove.readConsentStatus('sleeper')).valid, false, '200 valid: false');
      let threw = false;
      try { await h.faMove.readConsentStatus('sleeper'); } catch { threw = true; }
      expect(threw, 'a 500 was read as valid: false');
      const row = declText(parse(SETTINGS_LEAGUES), 'RosterMovesRow');
      expect(/\} catch \{\s*setFailed\(true\);\s*\}/.test(row) && /\{failed \? \(\s*<Text[^>]*>\s*\{FA_MOVE_FALLBACK_COPY\.stop_failed\}/.test(row),
        'the failure line');
      eq(read(FA_MOVE).match(/stop_failed: "([^"]+)"/)[1], "Couldn't turn off roster moves. Try again.", 'the neutral string (marketing A3.9)');
    });
  }
  {
    const h = harness();
    await check('X9 "terms changed": on the block\'s reason: version, and on an in-sheet version change', () => {
      const T = h.faMove.termsChanged;
      eq([T({ ...BLOCK, reason: 'version' }, null), T(BLOCK, null), T(BLOCK, 'test-copy-v9'), T(BLOCK, 'test-copy-v8')],
        [true, false, false, true], 'termsChanged');
      expect(/const changed = termsChanged\(block, shownVersionRef\.current\);/.test(declText(claim, 'showConsent')), 'showConsent');
    });
    await check('X10 fully legacy for an absent or unknown mode: no move.copy, no row move_line', () => {
      const bogus = { mode: 'bogus', copy: { handoff_footer: 'SERVER FOOTER' } };
      eq(h.faMove.capabilityOrNull(bogus), null, 'capability');
      eq(h.faMove.rowMoveFields(bogus, { move_mode: 'handoff', move_line: 'x' }), {}, 'row fields');
      const cp = h.plan.copyFns(h.faMove.capabilityOrNull(bogus), { league: 'L', name: 'A' });
      eq(cp.slot('handoff_footer'), "You'll finish this move in Sleeper.", 'the footer is the fallback');
      eq(h.plan.initialView(null, h.faMove.rowMoveFields(null, { move_mode: 'handoff', move_line: 'x' }), cp), { step: 'handoff', line: null }, 'no line');
    });
    await check('X11 every in-sheet re-read is bounded (5 s), and a failed one after Connect goes on as connected', async () => {
      const t = harness();
      const run = watch(t.faMove.withTimeout(new Promise(() => {}), t.faMove.FA_MOVE_REREAD_WAIT_MS));
      await t.time.advance(4_999);
      expect(run.state === 'pending', 'gave up early');
      await t.time.advance(1);
      expect(run.state === 'resolved' && run.value === undefined, `at 5 s: ${run.state}`);
      eq(t.faMove.FA_MOVE_REREAD_WAIT_MS, 5000, 'the bound');
      const next = h.plan.resumeAfterConnect(undefined, { move: { ...SUBMIT, connect: 'not_linked', consent_until: null }, row: {}, playerId: 'p' });
      expect(next.assumedConnected && next.move.connect === 'ok', 'assumed connected');
      eq(h.faMove.faMoveGate({ move: next.move, row: next.row, consentValid: false, ticked: false }), 'consent', 'on to consent');
      expect(/return refetch \? withTimeout\(refetch\(\), FA_MOVE_REREAD_WAIT_MS\)/.test(declText(claim, 'refetchSafe')), 'refetchSafe');
    });
    await check('X12 contract §7: the no-bid claim slots, waiver_line / waiver_line_no_drop, bid_line only with a bid; surface sent', async () => {
      const copy = { cta_claim_no_bid: 'CLAIM {add}', cta_claim_drop_no_bid: 'CLAIM {add} - {drop}', waiver_line: 'W {add} {drop}',
        waiver_line_no_drop: 'W {add}', bid_line: 'BID {bid}' };
      const M = h.faMove;
      eq([M.moveCtaLabel(copy, 'claim', { add: 'A' }, 'sleeper'), M.moveCtaLabel(copy, 'claim', { add: 'A', drop: 'B' }, 'sleeper')],
        ['CLAIM A', 'CLAIM A - B'], 'no-bid claim slots');
      eq(M.waiverLines(copy, { add: 'A', drop: 'B', bid: '$7' }, 'sleeper'), ['W A B', 'BID $7'], 'drop + bid');
      eq(M.waiverLines(copy, { add: 'A' }, 'sleeper'), ['W A'], 'no drop, no bid');
      const sel = h.plan.moveSelection({ rowName: 'A', kind: 'claim', dropId: null, candidates: [], faab: false, bid: '', copy, platform: 'sleeper' });
      eq([sel.ctaLabel, sel.waiverLines, 'faab_bid' in sel.request], ['CLAIM A', ['W A'], false], 'a priority-waiver claim');
      const t = harness();
      t.respond(() => response(200, { status: 'pending', move_kind: 'claim', result: 'accepted', league_platform: 'sleeper', attempt_id: 'x', title: 't', lines: [] }));
      await t.faMove.attemptMove({ move: SUBMIT, surface: 'usage_trends', request: REQ });
      eq(t.requests[0].body.surface, 'usage_trends', 'surface on the request');
    });
  }

  // ── Review round 3: Y1, Y2 ───────────────────────────────────────────────
  {
    const VR = { error: 'verification_required', message: 'Verify your account first.' };
    await check('Y1 Settings: a consent GET 403 verification_required reads as valid: false; a DELETE 403 rejects, so the row stays with its line', async () => {
      const h = harness();
      let next = 0;
      const answers = [[403, VR], [403, { error: 'forbidden' }], [403, VR]];
      h.respond(() => response(...answers[next++]));
      eq((await h.faMove.readConsentStatus('sleeper')).valid, false, 'GET 403 verification_required');
      let other = false;
      try { await h.faMove.readConsentStatus('sleeper'); } catch { other = true; }
      expect(other, 'another 403 was read as valid: false');
      let rejected = false;
      try { await h.faMove.withdrawConsent('sleeper'); } catch (e) { rejected = e.status === 403; }
      expect(rejected, 'DELETE 403 did not reject');
      expect(h.faMove.consumeWithdrawal('sleeper') === false, 'a refused DELETE was noted as a withdrawal');
      const row = declText(parse(SETTINGS_LEAGUES), 'RosterMovesRow');
      const caught = /\} catch \{([\s\S]*?)\}\s*finally/.exec(row);
      expect(caught && /setFailed\(true\);/.test(caught[1]) && !/setStopped|setNotice/.test(caught[1]),
        `the DELETE failure branch: ${caught && caught[1].trim()}`);
    });
    await check('Y2 the sheet: a consent GET 403 verification_required is state 4 (Verify), not the F4 hand-off', async () => {
      const h = harness();
      let next = 0;
      const answers = [[403, VR], [403, { error: 'forbidden', message: 'no' }]];
      h.respond(() => response(...answers[next++]));
      eq(await h.faMove.fetchConsentStep('sleeper'), { kind: 'verify', message: 'Verify your account first.' }, '403 verification_required');
      eq((await h.faMove.fetchConsentStep('sleeper')).kind, 'unavailable', 'another 403 is still F4');
      const t = declText(claim, 'openConsent');
      expect(/case 'verify':\s*apply\(planFailure\(\{ state: 'verify', errorCode: 'verification_required', status: 403, message: step\.message \}, copy\)\);/.test(t),
        'openConsent applies the move route\'s verify plan');
      const cp = h.plan.copyFns(SUBMIT, { league: 'L', name: 'A' });
      const plan = h.plan.planFailure({ state: 'verify', errorCode: 'verification_required', status: 403, message: 'Verify your account first.' }, cp);
      eq([plan.view.step, plan.view.verify, plan.view.line, plan.connect, plan.trackConnect],
        ['connect', true, 'Verify your account first.', 'unverified', 'unverified'], 'state 4');
      const moveRoute = h.plan.planFailure(h.faMove.classifyMoveError(apiErr(h, 403, VR)), cp);
      eq(moveRoute, plan, 'the same plan as the move route\'s 403');
    });
  }

  {
    const h = harness();
    await check('Y3 connect_shown.reason: the four connect values as themselves, anything else `unknown`; the step stays the plain connect', () => {
      const R = h.faMove.connectShownReason;
      eq(['not_linked', 'expired', 'unverified', 'other_account', 'banana', '', undefined, null, 'ok'].map(R),
        ['not_linked', 'expired', 'unverified', 'other_account', 'unknown', 'unknown', 'unknown', 'unknown', 'unknown'], 'reasons');
      eq([...h.faMove.CONNECT_SHOWN_REASONS], ['not_linked', 'expired', 'unverified', 'other_account', 'unknown'], 'the granted set');
      expect(/reason: connectShownReason\(override \?\? move\?\.connect\)/.test(declText(claim, 'trackConnectShown')), 'the sheet records through it');
      const cp = h.plan.copyFns({ ...SUBMIT, connect: 'banana' }, { league: 'L', name: 'A' });
      eq(h.plan.initialView({ ...SUBMIT, connect: 'banana' }, {}, cp).step, 'connect', 'the UI is the plain connect step');
    });
  }

  // ── Review round 5: B1, B2, B3 ───────────────────────────────────────────
  {
    // The real chalkline Button, rendered with a stub React that returns the
    // element tree (no React Native).
    function loadButton() {
      const out = ts.transpileModule(read(BUTTON), {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React },
      }).outputText;
      const el = (type, props, ...children) => ({ type, props: { ...(props || {}), children } });
      const React = { createElement: el, Fragment: 'Fragment' };
      const token = new Proxy({}, { get: () => new Proxy({}, { get: () => 8 }) });
      const mod = { exports: {} };
      new Function('module', 'exports', 'require', out)(mod, mod.exports, (n) => {
        if (n === 'react') return { default: React, ...React };
        if (n === 'react-native') {
          return { ActivityIndicator: 'ActivityIndicator', Pressable: 'Pressable', View: 'View',
            StyleSheet: { create: (o) => o, absoluteFillObject: { position: 'absolute' } } };
        }
        if (n === '../../theme/chalkline') return token;
        if (n === '../../state/useFeatureFlags') return { useFlag: () => false };
        if (n === './Text') return { default: 'Text' };
        if (n === './Icon') return { default: 'Icon' };
        throw new Error(`Button gained an import: ${n}`);
      });
      return mod.exports.default;
    }
    const flat = (a) => (Array.isArray(a) ? a.flatMap(flat) : [a]);
    await check('B1 the Button: `loading` is inactive and busy at full brightness; only `disabled` dims (#364)', () => {
      const Button = loadButton();
      const render = (props) => {
        const e = Button({ label: 'Add A', onPress: () => {}, ...props });
        return { e, dim: flat(e.props.style({ pressed: false })).some((x) => x && x.opacity === 0.45) };
      };
      const busy = render({ loading: true });
      expect(busy.e.props.disabled === true && busy.e.props.accessibilityState.busy === true, 'loading takes no tap and is busy');
      expect(busy.dim === false, 'loading dims the button');
      expect(render({ disabled: true }).dim === true && render({ disabled: true, loading: true }).dim === true, 'disabled must dim');
      expect(render({}).dim === false && render({}).e.props.disabled === false, 'idle');
    });
    await check('B1 the named CTA and Make the move are busy through `loading` only, never the disabled dim', () => {
      const ready = jsxMounts(claim, 'Button', actionBranches(claim).ready).filter((m) => m.attrs.testID === '"fa-claim.make-move"');
      const make = jsxMounts(claim, 'Button', actionBranches(claim).consent).filter((m) => m.attrs.testID === '"fa-claim.make-move"');
      for (const [name, m] of [['named CTA', ready[0]], ['Make the move', make[0]]]) {
        expect(m && m.attrs.loading === '{busy}' && !/busy|sending/.test(m.attrs.disabled || ''), `${name}: loading=${m && m.attrs.loading} disabled=${m && m.attrs.disabled}`);
      }
      expect(/if \(busy\) return;/.test(declText(claim, 'onNamedCta')) && /sendingRef\.current\) return;/.test(declText(claim, 'send')),
        'taps stay ignored while busy');
    });
  }
  {
    const h = harness();
    await check('B2 "In {league}" beside the named CTA with the server slot absent, from the host\'s league name', () => {
      eq(h.plan.copyFns({ ...SUBMIT, copy: {} }, { league: 'Dynasty Bros', name: 'A' }).slot('league_line'), 'In Dynasty Bros', 'fallback filled');
      eq(h.plan.copyFns({ ...SUBMIT, copy: { league_line: 'League: {league}' } }, { league: 'Dynasty Bros', name: 'A' }).slot('league_line'),
        'League: Dynasty Bros', 'the server slot when sent');
      eq(h.plan.copyFns({ ...SUBMIT, copy: {} }, { league: null, name: 'A' }).slot('league_line'), null, 'no league, no line');
      const ready = actionBranches(claim).ready.getText(claim);
      expect(/const leagueLine = slot\('league_line'\);/.test(ready) && /actionBlock = !leagueLine \? handoffBlock : \(/.test(ready)
        && /<Text style=\{sheetStyles\.dimLine\}>\{leagueLine\}<\/Text>/.test(ready), 'the ready step always names the league, or shows no named CTA');
      expect(/const leagueName = hostLeagueName \|\| sessionLeagueName \|\| null;/.test(claimText), 'the host\'s name first');
      expect(/leagueName=\{leagueName \?\? null\}/.test(read(FREE_AGENTS)) && /leagueName=\{claim\.leagueName\}/.test(read(USAGE_TRENDS))
        && /leagueName: \(leagues \?\? \[\]\)\.find\(\(l\) => l\.league_id === lgId\)\?\.name \?\? null,/.test(read(USAGE_TRENDS)), 'both hosts pass it');
    });
    await check('B3 "nothing was sent" only in state 11; never 10f or 13, in any fallback the client shows', () => {
      const cp = h.plan.copyFns(SUBMIT, { league: 'L', name: 'A' });
      const text = (v) => (v ? [v.title, ...(v.lines || []), v.line, v.ctaNotice && v.ctaNotice.text, v.dropNotice && v.dropNotice.text].filter(Boolean).join(' | ') : '');
      const cases = [[404, 'feature_disabled'], [400, 'bad_request'], [403, 'verification_required'], [409, 'sleeper_not_linked'],
        [409, 'sleeper_expired'], [409, 'consent_required'], [422, 'roster_full_drop_required'], [422, 'asset_not_owned'],
        [422, 'player_unavailable'], [422, 'waiver_bid_over_budget'], [422, 'waiver_claim_unsupported'], [409, 'sleeper_rejected'],
        [502, 'sleeper_write_failed'], [502, 'sleeper_write_failed', 'network'], [502, 'sleeper_write_failed', 'roster_read'],
        [503, 'sleeper_unconfigured'], [502, 'sleeper_outcome_unknown'], [409, 'move_in_progress'], [500, 'internal_error'], [418, 'teapot']];
      const rows = [];
      for (const [st, code, kind] of cases) {
        const f = h.faMove.classifyMoveError(apiErr(h, st, { error: code, ...(kind ? { kind } : {}) }));
        rows.push([f.state, text(h.plan.planFailure(f, cp).view)]);
      }
      for (const f of [h.faMove.classifyMoveError(apiErr(h, 0, null, true)), h.faMove.classifyMoveError(new TypeError('x'))]) {
        rows.push([f.state, text(h.plan.planFailure(f, cp).view)]);
      }
      rows.push(['kind_changed', text(h.plan.planKindChanged(undefined, { move: SUBMIT, kind: 'add', said: null, connect: null, playerId: 'p', copy: cp }).view)]);
      rows.push(['not_sent', text(h.plan.planNotSent(cp).view)]); // offline at the tap
      const wrong = rows.filter(([state, t]) => /nothing was sent/i.test(t) !== (state === 'not_sent'));
      eq(wrong, [], '[state, text] where "nothing was sent" is wrong or missing');
      const keys = Object.entries(h.faMove.FA_MOVE_FALLBACK_COPY).filter(([, v]) => /nothing was sent/i.test(v)).map(([k]) => k);
      eq(keys, ['not_sent_line'], 'fallbacks that say "nothing was sent"');
      for (const st of ['platform_refused', 'rejected']) expect(rows.some(([s]) => s === st), `${st} not covered`);
    });
  }

  // ── Review round 4: Z1 ───────────────────────────────────────────────────
  {
    const h = harness();
    // marketing-lead-copy.md addendum 17 §A, "Final text", verbatim.
    const FINAL = {
      finality: "Final on {platform}. Fleeced can't undo it.", // A3.1 (legal D10(b))
      waiver_line: 'This places a waiver claim for {add} (dropping {drop} if it clears). {platform} processes it on its waiver schedule.', // A3.2 (R15.1)
      waiver_line_no_drop: 'This places a waiver claim for {add}. {platform} processes it on its waiver schedule.', // A3.2
      window_line: 'Roster moves: on until {date}', // A3.3
      verify_line: 'Verify your {platform} sign-in to make moves from here.', // A3.4
      not_sent_line: "Couldn't reach {platform} right now, so nothing was sent.", // A3.5
      unknown_body: "Couldn't confirm whether this move reached {platform}. Check your roster and claims in {platform} before you make it again.", // A3.6
      unavailable_line: "Moves from Fleeced aren't available right now. You can still make this move in {platform}.", // A3.7
      result_added: 'Done', // A3.8
      stop_failed: "Couldn't turn off roster moves. Try again.", // A3.9
      // Confirmed as written:
      handoff_footer: "You'll finish this move in {platform}.", // A2
      league_line: 'In {league}', // A3.10, G22
      not_connected: "{platform} isn't connected", // A3.10, G23
      bid_line: 'Bid: {bid}', // legal's R15.1
    };
    await check('Z1 marketing\'s final fallbacks, verbatim (A2, A3.1–A3.10, the bid line)', () => {
      for (const [key, text] of Object.entries(FINAL)) eq(h.faMove.FA_MOVE_FALLBACK_COPY[key], text, key);
      eq(h.faMove.fallbackCopy('finality', {}, 'sleeper'), "Final on Sleeper. Fleeced can't undo it.", 'finality, filled');
      eq(h.faMove.waiverLines(undefined, { add: 'A', drop: 'B', bid: '$7' }, 'sleeper'),
        ['This places a waiver claim for A (dropping B if it clears). Sleeper processes it on its waiver schedule.', 'Bid: $7'], 'the claim lines, filled');
      eq(h.faMove.moveCopy(undefined, 'window_line', { date: 'Nov 8' }, 'sleeper'), 'Roster moves: on until Nov 8', 'window, filled');
      const banned = Object.values(h.faMove.FA_MOVE_FALLBACK_COPY).filter((v) => /\bwe\b|\bour\b|failed|error|try again/i.test(v) && v !== FINAL.stop_failed);
      eq(banned, [], 'marketing\'s rules (no "we", "failed", "error", or "try again" where the outcome is unknown)');
    });
    await check('Z1 the Usage Trends availability footer is A1\'s line', () => {
      expect(/Add opens a quick check before the move\. Trade opens the trade finder in that league\./.test(read('src/components/UsageLeagueList.tsx')),
        'UsageLeagueList footer');
    });
  }

  // ── Dark-safety, testIDs, Settings ────────────────────────────────────────
  await check('dark: no capability → the hand-off render (#509): its CTA and the neutral footer; never the false Sleeper claim', () => {
    expect(/useState<FaMoveCapability \| null>\(\(\) => capabilityOrNull\(openedWith\)\)/.test(claimText)
      && /useState<FaMoveRow>\(\(\) => rowMoveFields\(openedWith, row\)\)/.test(claimText), 'the sheet starts from the host\'s capability, normalized');
    let handoff = null;
    walk(claim, (n) => {
      if (ts.isIfStatement(n) && unparen(n.expression).getText(claim) === '!submitLayout') handoff = n.thenStatement;
    });
    expect(handoff, 'no `if (!submitLayout)` render');
    const t = handoff.getText(claim);
    expect(/\{header\}\s*\{bidSection\}\s*\{dropSection\}\s*\{handoffBlock\}/.test(t), 'header, bid, drop, then the hand-off');
    expect(!/actionBlock|KeyboardAvoidingView/.test(t), 'the in-app layout leaks into the hand-off');
    const all = srcFiles().map((f) => fs.readFileSync(f, 'utf8')).join('\n');
    expect(!/doesn't allow apps to submit claims/.test(all), 'the old footer survives somewhere');
    expect(/const footerText = moveCopy\(move\?\.copy, 'handoff_footer', vars, 'sleeper'\);/.test(claimText), 'the footer is the slot');
  });
  await check('testIDs: the six D1 sheet ids and two Settings ids are static strings; fa-claim.open-sleeper kept', () => {
    const ids = new Set();
    for (const f of [CLAIM, SETTINGS_LEAGUES]) {
      for (const m of [...jsxMounts(parse(f), 'Button'), ...jsxMounts(parse(f), 'Pressable'), ...jsxMounts(parse(f), 'View'),
        ...jsxMounts(parse(f), 'Text')]) {
        if (m.attrs.testID && /^"/.test(m.attrs.testID)) ids.add(m.attrs.testID.slice(1, -1));
      }
    }
    for (const id of ['fa-claim.connect', 'fa-claim.consent', 'fa-claim.consent.box', 'fa-claim.make-move',
      'fa-claim.do-in-sleeper', 'fa-claim.result', 'fa-claim.open-sleeper', 'settings.roster-moves.status',
      'settings.roster-moves.stop']) {
      expect(ids.has(id), `${id} missing`);
    }
  });
  await check('Settings › Leagues: Stop roster moves shows only while valid, is one tap (no Alert), and shows the notice verbatim', () => {
    const sf = parse(SETTINGS_LEAGUES);
    const row = decl(sf, 'RosterMovesRow');
    expect(row, 'RosterMovesRow');
    const t = row.getText(sf);
    expect(/if \(stopped \|\| status\?\.valid !== true\) return null;/.test(t), 'hidden unless valid');
    expect(/retry: false/.test(t) && /readConsentStatus\(platform\)/.test(t), 'one consent GET (a 404 reads as valid: false)');
    expect(!/Alert/.test(t), 'a dialog');
    expect(/onPress=\{\(\) => void stop\(\)\}/.test(t) && /withdrawConsent\(platform\)/.test(t), 'one tap withdraws');
    expect(/<Text style=\{rosterMoveText\.notice\}>\{notice\}<\/Text>/.test(t) && /setAccessibilityFocus/.test(t),
      'the notice, verbatim, with focus');
  });

  finished = true;
  console.log(`\n${passed} passed, ${failures} failed`);
  process.exit(failures ? 1 : 0);
})();

// ── Late helpers (hoisted) ──────────────────────────────────────────────────
// The text of `case '<label>':` (through the next case) in applyOutcome.
function caseClause(sf, label) {
  const apply = decl(sf, 'applyOutcome');
  let out = '';
  if (!apply) return out;
  walk(apply, (n) => {
    if (ts.isSwitchStatement(n) && n.expression.getText(sf) === 'f.state') {
      const clauses = n.caseBlock.clauses;
      for (let i = 0; i < clauses.length; i++) {
        const c = clauses[i];
        if (ts.isCaseClause(c) && c.expression.getText(sf) === `'${label}'`) {
          // Fall-through labels share the next non-empty clause.
          let j = i;
          while (j < clauses.length && clauses[j].statements.length === 0) j += 1;
          out = clauses[j] ? clauses[j].getText(sf) : '';
        }
      }
    }
  });
  return out;
}
// The action-block branches: handoff / ready / connect / consent / result.
function actionBranches(sf) {
  let chain = null;
  walk(sf, (n) => {
    if (ts.isIfStatement(n) && n.expression.getText(sf) === "view.step === 'handoff'"
        && /actionBlock = /.test(n.thenStatement.getText(sf))) chain = n;
  });
  const out = {};
  for (let s = chain; s;) {
    if (ts.isIfStatement(s)) {
      const m = /view\.step === '(\w+)'/.exec(s.expression.getText(sf));
      out[m[1]] = s.thenStatement;
      s = s.elseStatement;
    } else {
      out.result = s;
      s = null;
    }
  }
  return out;
}
