#!/usr/bin/env node
// check-send-timeout.js — the ESPN/MFL client double-send fix (2026-10-28).
//
// The app's default 15 s timeout gave up on POST /api/trades/propose-espn,
// /propose-mfl and the team-overhaul send while the server was still in the
// provider write, showed "Please try again", and invited a duplicate trade.
// This suite pins the fix, executing the real modules wherever it can:
//
//   A. The client constant equals the server worst case, with each term parsed
//      from the backend files (provider timeouts, MFL spacing, the calls each
//      propose core makes). A new provider call in a core goes red here. The
//      overhaul's batch timeout is capped at gunicorn's --timeout (render.yaml).
//   B. The three calls run on the long timeout, through the real api/client.ts
//      under a fake clock; every other call keeps its old timeout.
//   C. A timeout, a dropped connection, the server's *_outcome_unknown and a
//      code-less 5xx are "outcome unknown"; the structured errors are not.
//      The copy says "couldn't confirm", never "try again".
//   D. The send buttons and the overhaul summary branch on it first, and the
//      overhaul re-reads its attempts (OverhaulPlan) instead of offering a resend.
//   E. POSTs are never auto-retried (a GET control proves retries are visible).
//
// Dependency-free beyond the TypeScript compiler the mobile app already has.
// FTF_MOBILE_TEST_ROOT selects another mobile/ tree; backend/ always comes
// from this checkout.
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
const BACKEND = path.resolve(__dirname, '..', '..', 'backend');
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');
const readBackend = (name) => fs.readFileSync(path.join(BACKEND, name), 'utf8');

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

// ── Harness: the real modules, a fake clock, a scripted fetch ───────────────
const flush = async () => { for (let n = 0; n < 80; n++) await Promise.resolve(); };
function clock() {
  let now = 1_000_000, id = 0;
  const timers = new Map();
  return {
    Date: class extends Date { static now() { return now; } },
    performance: {now: () => now},
    setTimeout(fn, ms) { const key = ++id; timers.set(key, {at: now + (ms || 0), fn}); return key; },
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
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React},
  }).outputText;
  const module = {exports: {}};
  vm.runInNewContext(out, {
    module, exports: module.exports, require: requireShim,
    AbortController, DOMException, URL, console, ...time, ...extra,
  }, {filename: rel});
  return module.exports;
}
const response = (status, body) => ({
  status, ok: status >= 200 && status < 300,
  text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
});
function harness() {
  const time = clock();
  const requests = [];
  let responder = () => new Promise(() => {}); // never answers
  const native = {
    'expo-constants': {default: {expoConfig: {extra: {apiBaseUrl: 'https://example.invalid'}, version: 'test'}}},
    'expo-device': {DeviceType: {TABLET: 2, DESKTOP: 3}},
    'expo-secure-store': {getItemAsync: async () => 'synthetic-token', setItemAsync: async () => {}, deleteItemAsync: async () => {}},
    'react-native': {Platform: {OS: 'ios'}, AppState: {addEventListener: () => {}}},
    './events': {track: () => {}},
  };
  const fetch = (url, opts) => {
    requests.push({url, method: opts.method});
    return new Promise((resolve, reject) => {
      const abort = () => reject(new DOMException('Aborted', 'AbortError'));
      if (opts.signal?.aborted) return abort();
      opts.signal?.addEventListener('abort', abort, {once: true});
      Promise.resolve().then(() => responder(url, opts)).then(resolve, reject);
    });
  };
  const client = load('src/api/client.ts', (n) => {
    if (!native[n]) throw new Error(`unexpected client import ${n}`);
    return native[n];
  }, time, {fetch});
  const only = (map) => (n) => {
    if (!(n in map)) throw new Error(`unexpected import ${n}`);
    return map[n];
  };
  const outcome = load('src/api/sendOutcome.ts', only({'./client': client}), time);
  const espn = load('src/api/sendInEspn.ts', only({'./client': client, './sendOutcome': outcome}), time);
  const mfl = load('src/api/sendInMfl.ts', only({'./client': client, './sendOutcome': outcome}), time);
  const overhaul = load('src/api/overhaul.ts', only({
    './client': client, './sendOutcome': outcome, './trades': {normalizeTradeCard: (c) => c},
  }), time);
  return {time, requests, client, outcome, espn, mfl, overhaul, respond: (fn) => { responder = fn; }};
}
// Watch a promise without letting its rejection go unhandled.
function watch(p) {
  const s = {state: 'pending', value: undefined};
  p.then((v) => { s.state = 'resolved'; s.value = v; }, (e) => { s.state = 'rejected'; s.value = e; });
  return s;
}

const ESPN_BODY = {league_id: '123', their_user_id: 'espn:123.t2', give_player_ids: ['1'], receive_player_ids: ['2']};
const MFL_BODY = {league_id: '456', their_user_id: 'mfl:456.f0002', give_player_ids: ['1'], receive_player_ids: ['2']};
const BATCH_BODY = {prepare_token: 't', summary_hash: 'h', version: 1, idempotency_key: 'k'};
const SENDS = [
  ['propose-espn', (h) => h.espn.proposeTradeToEspn(ESPN_BODY), 'ESPN'],
  ['propose-mfl', (h) => h.mfl.proposeTradeToMfl(MFL_BODY), 'MFL'],
  ['overhaul send (3 offers)', (h) => h.overhaul.sendBatch('ov_1', BATCH_BODY, 3), null],
];

// ── Backend parsing helpers ─────────────────────────────────────────────────
function pyDefault(src, fn, param) {
  const m = new RegExp(`^def ${fn}\\(([^)]*)\\)`, 'ms').exec(src);
  if (!m) throw new Error(`def ${fn}(...) not found`);
  const d = new RegExp(`\\b${param}\\s*:\\s*int\\s*=\\s*(\\d+)`).exec(m[1]);
  if (!d) throw new Error(`${fn}: no \`${param}: int = N\` default`);
  return Number(d[1]);
}
function pyConst(src, name) {
  const m = new RegExp(`^${name}\\s*=\\s*([\\d.]+)`, 'm').exec(src);
  if (!m) throw new Error(`${name} = N not found`);
  return Number(m[1]);
}
function pyBody(src, fn) {
  const start = src.search(new RegExp(`^def ${fn}\\(`, 'm'));
  if (start < 0) throw new Error(`def ${fn}( not found`);
  const rest = src.slice(start + 4);
  const end = rest.search(/^(def |@app\.|class )/m);
  return src.slice(start, end < 0 ? undefined : start + 4 + end);
}
// Every call `prefix.name(...)` in `body` → [{name, args}], parens matched.
function calls(body, prefix) {
  const out = [];
  const re = new RegExp(`(?<![\\w.])${prefix.replace('.', '\\.')}\\.(\\w+)\\(`, 'g');
  let m;
  while ((m = re.exec(body))) {
    let depth = 1, i = re.lastIndex;
    for (; i < body.length && depth; i++) {
      if (body[i] === '(') depth++;
      else if (body[i] === ')') depth--;
    }
    out.push({name: m[1], args: body.slice(re.lastIndex, i - 1)});
  }
  return out;
}

// ── TypeScript AST helpers ──────────────────────────────────────────────────
const parse = (rel) => ts.createSourceFile(rel, read(rel), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
function findAll(node, pred, acc = []) {
  if (pred(node)) acc.push(node);
  ts.forEachChild(node, (c) => { findAll(c, pred, acc); }); // a truthy return would stop forEachChild
  return acc;
}
function callbackBody(sf, name) {
  const decl = findAll(sf, (n) => ts.isVariableDeclaration(n) && n.name.getText(sf) === name)[0];
  if (!decl) throw new Error(`const ${name} not found`);
  const fn = findAll(decl, (n) => ts.isArrowFunction(n))[0];
  if (!fn) throw new Error(`${name} is not an arrow callback`);
  return fn;
}
function catchOf(sf, fnNode) {
  const tryStmt = findAll(fnNode, (n) => ts.isTryStatement(n) && !!n.catchClause)[0];
  if (!tryStmt) throw new Error('no try/catch');
  return tryStmt;
}
// The first `if` in the catch block, which must be the outcome-unknown branch.
// The user-visible strings in a node (string and template literals, not comments).
function literals(node) {
  return findAll(node, (n) => ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isTemplateExpression(n))
    .map((n) => n.getText()).join(' ');
}
function firstCatchIf(sf, tryStmt) {
  const first = tryStmt.catchClause.block.statements.find((s) => ts.isIfStatement(s));
  if (!first) throw new Error('catch block has no if statement');
  return first;
}

(async () => {
  // ════ A. The constant is the server worst case ═══════════════════════════
  const espnWrite = readBackend('espn_write.py');
  const mflWrite = readBackend('mfl_write.py');
  const mflService = readBackend('mfl_service.py');
  const espnService = readBackend('espn_service.py');
  const server = readBackend('server.py');
  const terms = {};

  await check('A1. provider timeouts parsed from the backend, each used by its HTTP call', () => {
    terms.espnWrite = pyConst(espnWrite, '_HTTP_TIMEOUT');
    terms.mflWrite = pyConst(mflWrite, '_HTTP_TIMEOUT');
    terms.mflSpacing = pyConst(mflWrite, '_REQUEST_SPACING_SECONDS');
    terms.resolveHost = pyDefault(mflService, 'resolve_host', 'timeout');
    terms.rosters = pyDefault(mflService, 'fetch_rosters', 'timeout');
    terms.picks = pyDefault(mflService, 'fetch_future_draft_picks', 'timeout');
    terms.league = pyDefault(espnService, 'fetch_league', 'timeout');
    terms.crosswalk = pyDefault(espnService, 'fetch_crosswalk', 'timeout');
    const bad = [];
    if (!/opener\(request, timeout=_HTTP_TIMEOUT\)/.test(pyBody(espnWrite, '_post_transaction'))) bad.push('espn_write._post_transaction no longer opens with _HTTP_TIMEOUT');
    const imp = pyBody(mflWrite, '_issue_import');
    if (!/opener\(request, timeout=_HTTP_TIMEOUT\)/.test(imp)) bad.push('mfl_write._issue_import no longer opens with _HTTP_TIMEOUT');
    if (!/_REQUEST_SPACING_SECONDS/.test(imp)) bad.push('mfl_write._issue_import no longer spaces with _REQUEST_SPACING_SECONDS');
    if (!/timeout=timeout/.test(pyBody(mflService, 'resolve_host'))) bad.push('resolve_host ignores its timeout');
    if (!/opener\(req, timeout=timeout\)/.test(pyBody(mflService, '_fetch_one'))) bad.push('mfl_service._fetch_one ignores its timeout');
    for (const fn of ['fetch_rosters', 'fetch_future_draft_picks']) {
      if (!/_fetch_one\([^)]*\btimeout\b/.test(pyBody(mflService, fn))) bad.push(`${fn} does not pass its timeout to _fetch_one`);
    }
    if (!/opener\(req, timeout=timeout\)/.test(pyBody(espnService, 'fetch_league'))) bad.push('fetch_league ignores its timeout');
    if (!/opener\(req, timeout=timeout\)/.test(pyBody(espnService, 'fetch_crosswalk'))) bad.push('fetch_crosswalk ignores its timeout');
    if (!/fetch_crosswalk\(_opener=_opener\)/.test(pyBody(espnService, 'get_crosswalk'))) bad.push('get_crosswalk calls fetch_crosswalk with something other than its default timeout');
    expect(!bad.length, bad.join('; '));
  });

  await check('A2. each propose core makes exactly the counted provider calls, on their default timeouts', () => {
    const bad = [];
    const NON_NETWORK = new Set([
      'MflError', 'MflAuthError', 'parse_roster_ids', 'parse_future_picks',
      'MflWriteError', 'MflWriteAuthError', 'ProposeTradeRequest', 'is_pick_asset_id', 'normalize_franchise_id',
      'EspnError', 'EspnAuthError', 'parse_league',
      'EspnWriteError', 'EspnWriteAuthError', 'EspnTradeProposalRequest', 'current_scoring_period', 'extract_lineup_slots',
    ]);
    const cores = {
      _mfl_propose_core: {
        modules: ['_mfl', '_mfl_write'],
        want: {'_mfl.resolve_host': 1, '_mfl.fetch_rosters': 1, '_mfl.fetch_future_draft_picks': 1, '_mfl_write.propose_trade': 1},
        map: '_sleeper_to_mfl_map',
      },
      _espn_propose_core: {
        modules: ['_espn', '_espn_write'],
        want: {'_espn.fetch_league': 1, '_espn_write.propose_trade': 1},
        map: '_sleeper_to_espn_map',
      },
    };
    for (const [core, spec] of Object.entries(cores)) {
      const body = pyBody(server, core);
      const seen = {};
      for (const mod of spec.modules) {
        for (const c of calls(body, mod)) {
          if (NON_NETWORK.has(c.name)) continue;
          const key = `${mod}.${c.name}`;
          seen[key] = (seen[key] || 0) + 1;
          if (/\btimeout\s*=/.test(c.args)) bad.push(`${core}: ${key}(...) overrides its timeout`);
        }
      }
      for (const [key, n] of Object.entries(seen)) {
        if (spec.want[key] !== n) bad.push(`${core}: ${key} called ${n}x — not in the counted worst case; update SERVER_SEND_WORST_CASE_S (api/sendOutcome.ts) and this list`);
      }
      for (const key of Object.keys(spec.want)) if (!seen[key]) bad.push(`${core}: expected ${key}(...) not found`);
      if (!new RegExp(`\\b${spec.map}\\(\\)`).test(body)) bad.push(`${core}: no ${spec.map}() (the crosswalk term)`);
      if (/urlopen|_sleeper_get\(|requests\./.test(body)) bad.push(`${core}: a direct HTTP call not counted in the worst case`);
      if (!/_shared_crosswalk\(\)/.test(pyBody(server, spec.map))) bad.push(`${spec.map} no longer reads _shared_crosswalk()`);
    }
    if (!/get_crosswalk\(\)/.test(pyBody(server, '_shared_crosswalk'))) bad.push('_shared_crosswalk no longer calls get_crosswalk()');
    expect(!bad.length, bad.join('; '));
  });

  const h0 = harness();
  const O = h0.outcome;
  await check('A3. SERVER_SEND_WORST_CASE_S = max(MFL, ESPN) of the parsed terms; margin = DEFAULT_TIMEOUT_MS; PLATFORM_SEND_TIMEOUT_MS = (sum + margin) s', () => {
    const mfl = terms.crosswalk + terms.resolveHost + terms.rosters + terms.picks + terms.mflSpacing + terms.mflWrite;
    const espn = terms.crosswalk + terms.league + terms.espnWrite;
    const worst = Math.max(mfl, espn);
    const def = /const DEFAULT_TIMEOUT_MS = ([\d_]+);/.exec(read('src/api/client.ts'));
    expect(def, 'DEFAULT_TIMEOUT_MS not found in api/client.ts');
    const marginS = Number(def[1].replace(/_/g, '')) / 1000;
    expect(O.SERVER_SEND_WORST_CASE_S === worst,
      `SERVER_SEND_WORST_CASE_S = ${O.SERVER_SEND_WORST_CASE_S}, server worst case = ${worst} (MFL ${mfl}, ESPN ${espn})`);
    expect(O.SEND_TIMEOUT_MARGIN_S === marginS, `margin ${O.SEND_TIMEOUT_MARGIN_S} s, want DEFAULT_TIMEOUT_MS = ${marginS} s`);
    expect(O.PLATFORM_SEND_TIMEOUT_MS === (worst + marginS) * 1000,
      `PLATFORM_SEND_TIMEOUT_MS = ${O.PLATFORM_SEND_TIMEOUT_MS}, want ${(worst + marginS) * 1000}`);
    expect(O.PLATFORM_SEND_TIMEOUT_MS === 91_000, `PLATFORM_SEND_TIMEOUT_MS = ${O.PLATFORM_SEND_TIMEOUT_MS}, the documented value is 91000 — update the comment's arithmetic too`);
  });

  await check('A4. the constant\'s comment cites every server term (file:line) and the arithmetic', () => {
    const src = read('src/api/sendOutcome.ts');
    const cites = [
      'backend/espn_service.py:774', 'backend/espn_service.py:139', ':755',
      'backend/mfl_service.py:129', 'backend/mfl_service.py:441', 'backend/mfl_service.py:401',
      'backend/mfl_write.py:63', 'backend/mfl_write.py:58', 'backend/espn_write.py:80',
      '_mfl_propose_core', '_espn_propose_core', '= 76 s', '= 45 s',
      'render.yaml:16', '--timeout 120',
    ];
    const missing = cites.filter((c) => !src.includes(c));
    expect(!missing.length, `missing from the comment: ${missing.join(', ')}`);
    for (const f of new Set([...src.matchAll(/backend\/(\w+\.py):\d+/g)].map((m) => m[1]))) {
      expect(fs.existsSync(path.join(BACKEND, f)), `cited file backend/${f} does not exist`);
    }
  });

  await check('A5. GUNICORN_TIMEOUT_S = the web service\'s `--timeout N` in render.yaml; one propose fits under it uncapped', () => {
    const yaml = fs.readFileSync(path.resolve(__dirname, '..', '..', 'render.yaml'), 'utf8');
    const web = /-\s*type:\s*web\b[\s\S]*?startCommand:\s*([^\n]+)/.exec(yaml);
    expect(web, 'no `type: web` service with a startCommand in render.yaml');
    const t = /--timeout[ =](\d+)/.exec(web[1]);
    expect(t, `the web startCommand sets no --timeout: ${web[1].trim()}`);
    expect(O.GUNICORN_TIMEOUT_S === Number(t[1]), `GUNICORN_TIMEOUT_S = ${O.GUNICORN_TIMEOUT_S}, render.yaml --timeout ${t[1]}`);
    expect(O.SERVER_SEND_WORST_CASE_S <= O.GUNICORN_TIMEOUT_S,
      `one propose (${O.SERVER_SEND_WORST_CASE_S} s) outlives the server ceiling (${O.GUNICORN_TIMEOUT_S} s): PLATFORM_SEND_TIMEOUT_MS needs the cap too`);
  });

  await check('A6. overhaulSendTimeoutMs = (min(offers × worst case, ceiling) + margin) s; 10 offers = the cap; a missing count is one offer', () => {
    const w = O.SERVER_SEND_WORST_CASE_S, m = O.SEND_TIMEOUT_MARGIN_S, cap = O.GUNICORN_TIMEOUT_S;
    for (const n of [1, 2, 3, 5, 10, 12]) {
      expect(O.overhaulSendTimeoutMs(n) === (Math.min(n * w, cap) + m) * 1000, `overhaulSendTimeoutMs(${n}) = ${O.overhaulSendTimeoutMs(n)}`);
    }
    expect(O.overhaulSendTimeoutMs(10) === (cap + m) * 1000,
      `overhaulSendTimeoutMs(10) = ${O.overhaulSendTimeoutMs(10)} ms, want the cap ${(cap + m) * 1000} ms`);
    expect(O.overhaulSendTimeoutMs(10) === 135_000, `overhaulSendTimeoutMs(10) = ${O.overhaulSendTimeoutMs(10)}, the documented cap is 135000`);
    expect(O.overhaulSendTimeoutMs(1) === O.PLATFORM_SEND_TIMEOUT_MS, 'one offer must equal the single-send timeout');
    for (const n of [0, -2, NaN, undefined]) {
      expect(O.overhaulSendTimeoutMs(n) === O.PLATFORM_SEND_TIMEOUT_MS, `overhaulSendTimeoutMs(${n}) must fall back to one offer`);
    }
  });

  // ════ B. The three calls wait the long timeout; nothing else changes ═════
  for (const [label, call] of SENDS) {
    await check(`B. ${label}: still waiting at the old 15 s, times out at its long timeout, one request`, async () => {
      const h = harness();
      const want = label.startsWith('overhaul') ? h.outcome.overhaulSendTimeoutMs(3) : h.outcome.PLATFORM_SEND_TIMEOUT_MS;
      const s = watch(call(h));
      await h.time.advance(15_000);
      expect(s.state === 'pending', `settled (${s.state}: ${s.value && s.value.message}) at 15 s — the default timeout still applies`);
      await h.time.advance(want - 15_000 - 1);
      expect(s.state === 'pending', `settled 1 ms before ${want} ms`);
      await h.time.advance(1);
      expect(s.state === 'rejected' && s.value instanceof h.client.ApiError && s.value.isTimeout,
        `at ${want} ms: ${s.state} ${s.value && s.value.message}`);
      expect(h.requests.length === 1 && h.requests[0].method === 'POST', `${h.requests.length} requests sent`);
    });
  }

  await check('B4. other calls keep their timeouts: GET link status, prepare-send, refresh, a plain POST = 15 s', async () => {
    const others = [
      ['GET /api/espn/link', (h) => h.espn.getEspnLinkStatus()],
      ['GET /api/mfl/auth-link', (h) => h.mfl.getMflLinkStatus()],
      ['POST prepare-send', (h) => h.overhaul.prepareSend('ov_1', 'rm_1', {version: 1, offer_ids: ['a']})],
      ['POST refresh', (h) => h.overhaul.refreshOverhaul('ov_1')],
      ['POST /api/trades/propose', (h) => h.client.api.post('/api/trades/propose', {})],
    ];
    const bad = [];
    for (const [label, call] of others) {
      const h = harness();
      const s = watch(call(h));
      await h.time.advance(15_000 - 1);
      if (s.state !== 'pending') { bad.push(`${label} settled before 15 s`); continue; }
      await h.time.advance(1);
      if (!(s.state === 'rejected' && s.value.isTimeout)) bad.push(`${label} did not time out at 15 s (${s.state})`);
    }
    expect(!bad.length, bad.join('; '));
  });

  // ════ C. What counts as "outcome unknown", and what it says ══════════════
  await check('C1. a timeout on each of the three calls is outcome-unknown', async () => {
    for (const [label, call] of SENDS) {
      const h = harness();
      const s = watch(call(h));
      await h.time.advance(h.outcome.overhaulSendTimeoutMs(3) + 1);
      expect(s.state === 'rejected', `${label}: ${s.state}`);
      expect(h.outcome.isSendOutcomeUnknown(s.value) === true, `${label}: a timeout (${s.value.message}) is not outcome-unknown`);
    }
  });

  await check('C2. a dropped connection (fetch rejects) is outcome-unknown, and the POST is sent once', async () => {
    for (const [label, call] of SENDS) {
      const h = harness();
      h.respond(() => Promise.reject(new TypeError('Network request failed')));
      const s = watch(call(h));
      await h.time.advance(1_000);
      expect(s.state === 'rejected', `${label}: ${s.state}`);
      expect(h.outcome.isSendOutcomeUnknown(s.value) === true, `${label}: a network drop is not outcome-unknown`);
      expect(h.requests.length === 1, `${label}: ${h.requests.length} requests — a POST was retried`);
    }
  });

  const SERVER_CASES = [
    [502, {error: 'espn_outcome_unknown', kind: 'outcome_unknown', detail: 'x'}, true],
    [502, {error: 'mfl_outcome_unknown', kind: 'outcome_unknown', detail: 'x'}, true],
    [500, {error: 'internal_error', message: 'Unexpected server error.'}, true],
    [504, '<html>Gateway Timeout</html>', true],
    [503, '', true],
    [502, {error: 'espn_write_failed', kind: 'error', detail: 'x'}, false],
    [502, {error: 'mfl_write_failed', kind: 'error', detail: 'x'}, false],
    [502, {error: 'espn_unavailable', kind: 'network', detail: 'x'}, false],
    [502, {error: 'mfl_unavailable', kind: 'network', detail: 'x'}, false],
    [409, {error: 'espn_auth_expired'}, false],
    [409, {error: 'mfl_auth_expired'}, false],
    [422, {error: 'asset_not_owned', detail: 'x'}, false],
    [422, {error: 'mfl_asset_unmapped', unmapped: ['1']}, false],
    [409, {error: 'prepare_expired'}, false],
    [409, {error: 'asset_reserved'}, false],
    [403, {error: 'verification_required'}, false],
    [404, {error: 'feature_disabled'}, false],
    [599, {error: 'test_mode_propose_disabled'}, false],
  ];
  await check(`C3. server answers through the real client: unknown codes + code-less 5xx are unknown, the ${SERVER_CASES.filter((c) => !c[2]).length} structured errors are not`, async () => {
    const bad = [];
    for (const [status, body, want] of SERVER_CASES) {
      const h = harness();
      h.respond(() => response(status, body));
      const s = watch(h.espn.proposeTradeToEspn(ESPN_BODY));
      await h.time.advance(1_000);
      if (s.state !== 'rejected') { bad.push(`${status} ${JSON.stringify(body)}: ${s.state}`); continue; }
      if (h.outcome.isSendOutcomeUnknown(s.value) !== want) bad.push(`${status} ${JSON.stringify(body).slice(0, 40)} → ${!want}, want ${want}`);
      if (h.requests.length !== 1) bad.push(`${status}: ${h.requests.length} requests`);
    }
    expect(!bad.length, bad.join('; '));
  });

  const copy = load('src/utils/sendOutcomeCopy.ts', (n) => { throw new Error(`unexpected copy import ${n}`); }, clock());
  // Marketing's final copy, addendum 10 items 8a/8b/8e/8f/8i, word for word
  // with STRAIGHT apostrophes (docs/plans/org-bringup/leads/marketing-lead-copy.md).
  const FINAL = {
    unknownTitle: 'Check before resending',
    notSentTitle: 'Not sent',
    unknown: {
      ESPN: "Couldn't confirm whether this trade reached ESPN. Check your league's pending trades on ESPN before you send it again.",
      MFL: "Couldn't confirm whether this trade reached MFL. Check your league's pending trades on MFL before you send it again.",
    },
    notSent: {
      ESPN: "ESPN didn't accept this trade, so nothing was sent. You can still propose it on ESPN.",
      MFL: "MFL didn't accept this trade, so nothing was sent. You can still propose it on MFL.",
    },
  };
  await check('C4. the copy, word for word: titles "Check before resending" / "Not sent", 8e/8f client bodies, 8a/8b fallbacks, straight apostrophes', () => {
    const bad = [];
    if (copy.SEND_OUTCOME_UNKNOWN_TITLE !== FINAL.unknownTitle) bad.push(`unknown title: ${copy.SEND_OUTCOME_UNKNOWN_TITLE}`);
    if (copy.SEND_NOT_SENT_TITLE !== FINAL.notSentTitle) bad.push(`not-sent title: ${copy.SEND_NOT_SENT_TITLE}`);
    for (const p of ['ESPN', 'MFL']) {
      if (copy.sendOutcomeUnknownMessage(p) !== FINAL.unknown[p]) bad.push(`${p} unknown: ${copy.sendOutcomeUnknownMessage(p)}`);
      if (copy.sendNotSentFallback(p) !== FINAL.notSent[p]) bad.push(`${p} not-sent fallback: ${copy.sendNotSentFallback(p)}`);
    }
    const finals = [FINAL.unknownTitle, FINAL.notSentTitle, ...Object.values(FINAL.unknown), ...Object.values(FINAL.notSent)];
    if (finals.some((s) => s.includes('’'))) bad.push('a final string carries a curly apostrophe');
    expect(!bad.length, bad.join('; '));
  });

  await check('C5. outcome-unknown body: the server\'s own detail for <platform>_outcome_unknown, else the client line; never another code\'s text', () => {
    const bad = [];
    const cases = [
      ['ESPN', 'espn_outcome_unknown', 'Server line.', 'Server line.'],
      ['MFL', 'mfl_outcome_unknown', 'Server line.', 'Server line.'],
      ['ESPN', undefined, undefined, FINAL.unknown.ESPN],             // our timeout / network drop
      ['MFL', undefined, undefined, FINAL.unknown.MFL],
      ['ESPN', 'internal_error', 'Unexpected server error.', FINAL.unknown.ESPN],
      ['ESPN', 'mfl_outcome_unknown', 'Wrong platform.', FINAL.unknown.ESPN],
      ['MFL', 'mfl_outcome_unknown', '  ', FINAL.unknown.MFL],
      ['ESPN', undefined, '<html>Gateway Timeout</html>', FINAL.unknown.ESPN],
    ];
    for (const [p, code, detail, want] of cases) {
      const got = copy.sendOutcomeUnknownBody(p, code, detail);
      if (got !== want) bad.push(`${p}/${code}/${JSON.stringify(detail)} → ${got}`);
    }
    expect(!bad.length, bad.join('; '));
  });

  await check('C6. sweep of the copy module: no "failed" / "error" anywhere; no "nothing was sent" / "try again" in outcome-unknown copy; overhaul line marked pending marketing', () => {
    const bad = [];
    const sf = parse('src/utils/sendOutcomeCopy.ts');
    const lits = findAll(sf, (n) => ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isTemplateExpression(n));
    expect(lits.length >= 6, `only ${lits.length} literals found in the copy module`);
    for (const n of lits) {
      if (/\bfail(ed|ure|s)?\b|\berrors?\b/i.test(n.getText(sf))) bad.push(`literal: ${n.getText(sf)}`);
    }
    const outputs = [];
    for (const [name, v] of Object.entries(copy)) {
      if (typeof v === 'string') outputs.push([name, v]);
      else if (typeof v === 'function') for (const p of ['ESPN', 'MFL', 'Sleeper']) outputs.push([`${name}(${p})`, v(p)]);
    }
    expect(outputs.length >= 14, `only ${outputs.length} copy outputs swept`);
    for (const [name, s] of outputs) {
      if (/\bfail(ed|ure|s)?\b|\berrors?\b/i.test(s)) bad.push(`${name}: ${s}`);
      const unknown = /UNKNOWN|Unknown/.test(name);
      if (unknown && /nothing (was|went) (sent|out)|try again|retry/i.test(s)) bad.push(`${name}: ${s}`);
    }
    const src = read('src/utils/sendOutcomeCopy.ts');
    const ovh = src.indexOf('export function overhaulSendOutcomeUnknownMessage');
    if (!/PENDING MARKETING/.test(src.slice(Math.max(0, ovh - 200), ovh))) bad.push('overhaul line not marked PENDING MARKETING');
    for (const p of ['ESPN', 'MFL', 'Sleeper']) {
      const msg = copy.overhaulSendOutcomeUnknownMessage(p);
      if (!msg.startsWith(`Couldn’t confirm whether these offers reached ${p}.`)) bad.push(`overhaul ${p}: ${msg}`);
    }
    expect(!bad.length, bad.join('; '));
  });

  // ════ D. The UI branches on it first ═════════════════════════════════════
  for (const [file, platform, opener, sender] of [
    ['src/components/SendInEspnButton.tsx', 'ESPN', 'openEspn', 'proposeTradeToEspn'],
    ['src/components/SendInMflButton.tsx', 'MFL', 'openMfl', 'proposeTradeToMfl'],
  ]) {
    await check(`D. ${path.basename(file)}: the catch's FIRST branch is isSendOutcomeUnknown(err) (so "Couldn’t send" never shows for it) → "Check before resending", buttons exactly OK + Open ${platform}, no Retry / resend`, () => {
      const sf = parse(file);
      const doPropose = callbackBody(sf, 'doPropose');
      const tryStmt = catchOf(sf, doPropose);
      expect(findAll(tryStmt.tryBlock, (n) => ts.isCallExpression(n) && n.expression.getText(sf) === sender).length === 1,
        `${sender}(...) is not called in doPropose's try block`);
      const first = firstCatchIf(sf, tryStmt);
      expect(first.expression.getText(sf) === 'isSendOutcomeUnknown(err)', `first catch branch is \`if (${first.expression.getText(sf)})\``);
      const alerts = findAll(first.thenStatement, (n) => ts.isCallExpression(n) && n.expression.getText(sf) === 'Alert.alert');
      expect(alerts.length === 1, `${alerts.length} Alert.alert calls in the unknown branch`);
      const [title, body, actions] = alerts[0].arguments;
      expect(title && title.getText(sf) === 'SEND_OUTCOME_UNKNOWN_TITLE', `title: ${title && title.getText(sf)}`);
      expect(body && body.getText(sf) === `sendOutcomeUnknownBody('${platform}', code, detail)`, `body: ${body && body.getText(sf)}`);
      expect(actions && ts.isArrayLiteralExpression(actions), 'no actions array');
      const texts = actions.elements.map((el) => {
        const t = ts.isObjectLiteralExpression(el) && el.properties.find((p) => p.name && p.name.getText(sf) === 'text');
        return t ? t.initializer.getText(sf) : el.getText(sf);
      });
      expect(JSON.stringify(texts) === JSON.stringify(["'OK'", `'Open ${platform}'`]), `buttons: ${texts.join(', ')} — want exactly OK + Open ${platform}`);
      expect(first.thenStatement.getText(sf).includes(`onPress: ${opener}`), `Open ${platform} does not call ${opener}`);
      const resend = findAll(first.thenStatement, (n) => ts.isIdentifier(n) && /^(doPropose|confirmSend|setState|propose\w*)$/.test(n.text));
      expect(!resend.length, `the unknown branch can resend: ${resend.map((n) => n.text).join(', ')}`);
      expect(!/try again|retry|send again/i.test(literals(first.thenStatement)), 'the unknown branch offers a retry');
      const imports = sf.statements.filter(ts.isImportDeclaration).map((d) => d.getText(sf)).join('\n');
      expect(/import \{ isSendOutcomeUnknown \} from '\.\.\/api\/sendOutcome'/.test(imports), 'isSendOutcomeUnknown not imported from api/sendOutcome');
      expect(/from '\.\.\/utils\/sendOutcomeCopy'/.test(imports), 'copy not imported from utils/sendOutcomeCopy');
    });

    await check(`D. ${path.basename(file)}: ${platform.toLowerCase()}_write_failed → "Not sent", body = detail alone (no "rejected the request" prefix), fallback 8${platform === 'ESPN' ? 'a' : 'b'}`, () => {
      const sf = parse(file);
      const tryStmt = catchOf(sf, callbackBody(sf, 'doPropose'));
      let branch = firstCatchIf(sf, tryStmt);
      while (branch && branch.expression.getText(sf) !== `code === '${platform.toLowerCase()}_write_failed'`) {
        branch = branch.elseStatement && ts.isIfStatement(branch.elseStatement) ? branch.elseStatement : null;
      }
      expect(branch, `no \`code === '${platform.toLowerCase()}_write_failed'\` branch in the catch chain`);
      const alert = findAll(branch.thenStatement, (n) => ts.isCallExpression(n) && n.expression.getText(sf) === 'Alert.alert')[0];
      expect(alert, 'no Alert.alert in the write_failed branch');
      const [title, body] = alert.arguments;
      expect(title.getText(sf) === 'SEND_NOT_SENT_TITLE', `title: ${title.getText(sf)}`);
      expect(body.getText(sf).replace(/\s+/g, ' ') === `detail || sendNotSentFallback('${platform}')`, `body: ${body.getText(sf)}`);
      const lits = literals(sf);
      expect(!/rejected the request|wouldn.t accept the send/i.test(lits), `the old write_failed copy is still in ${path.basename(file)}`);
    });
  }

  await check('D3. OverhaulSummaryScreen: sendBatch gets the offer count; unknown → re-read + OverhaulPlan + the copy, no resend, never "nothing went out"', () => {
    const file = 'src/screens/OverhaulSummaryScreen.tsx';
    const sf = parse(file);
    const onSend = callbackBody(sf, 'onSend');
    const tryStmt = catchOf(sf, onSend);
    const send = findAll(tryStmt.tryBlock, (n) => ts.isCallExpression(n) && n.expression.getText(sf) === 'sendBatch')[0];
    expect(send, 'no sendBatch(...) in onSend');
    expect(send.arguments.length === 3 && send.arguments[2].getText(sf) === 'pv.counts.offers',
      `sendBatch's offer count: ${send.arguments[2] ? send.arguments[2].getText(sf) : 'missing'}`);
    const first = firstCatchIf(sf, tryStmt);
    expect(first.expression.getText(sf) === 'isSendOutcomeUnknown(e)', `first catch branch is \`if (${first.expression.getText(sf)})\``);
    const callsIn = findAll(first.thenStatement, (n) => ts.isCallExpression(n)).map((n) => n.expression.getText(sf));
    for (const need of ['invalidate', 'navigation.replace', 'Alert.alert', 'overhaulSendOutcomeUnknownMessage']) {
      expect(callsIn.includes(need), `the unknown branch does not call ${need}(...) (calls: ${callsIn.join(', ')})`);
    }
    const then = first.thenStatement.getText(sf);
    expect(/navigation\.replace\('OverhaulPlan', \{ overhaulId \}\)/.test(then), 'the unknown branch does not go to OverhaulPlan');
    expect(then.includes('Alert.alert(SEND_OUTCOME_UNKNOWN_TITLE,'), 'the unknown branch does not use the shared title');
    const banned = callsIn.filter((c) => ['prepare', 'sendBatch', 'setToast', 'onSend', 'setPrepared'].includes(c));
    expect(!banned.length, `the unknown branch can resend or claim failure: ${banned.join(', ')}`);
    expect(!/nothing went out|try again/i.test(literals(first.thenStatement)), 'the unknown branch says "nothing went out" / "try again"');
  });

  // ════ E. No automatic retry of a POST ════════════════════════════════════
  await check('E1. POSTs are never auto-retried (502 / 503 / 504 / network drop), while a GET control IS retried', async () => {
    const bad = [];
    for (const [label, call] of [...SENDS, ['plain POST', (h) => h.client.api.post('/api/anything', {})]]) {
      for (const answer of [() => response(502, ''), () => response(503, ''), () => response(504, ''), () => Promise.reject(new TypeError('Network request failed'))]) {
        const h = harness();
        h.respond(answer);
        const s = watch(call(h));
        await h.time.advance(10_000);
        if (s.state !== 'rejected') bad.push(`${label}: ${s.state}`);
        if (h.requests.length !== 1) bad.push(`${label}: ${h.requests.length} requests on one failure`);
      }
    }
    const g = harness();
    g.respond(() => response(502, ''));
    watch(g.client.api.get('/api/espn/link'));
    await g.time.advance(10_000);
    if (g.requests.length < 2) bad.push(`GET control sent ${g.requests.length} request(s) on a 502 — the harness can't see retries`);
    expect(!bad.length, bad.join('; '));
  });

  await check('E2. the only POST replay is the pre-handler 409 session_not_initialized; any other 409 is sent once', async () => {
    const h = harness();
    h.respond(() => response(409, {error: 'session_not_initialized'}));
    watch(h.espn.proposeTradeToEspn(ESPN_BODY));
    await h.time.advance(10_000);
    expect(h.requests.length === 3, `session_not_initialized: ${h.requests.length} requests (the guard runs before the route, so a replay can't double-send)`);
    const h2 = harness();
    h2.respond(() => response(409, {error: 'espn_auth_expired'}));
    watch(h2.espn.proposeTradeToEspn(ESPN_BODY));
    await h2.time.advance(10_000);
    expect(h2.requests.length === 1, `espn_auth_expired: ${h2.requests.length} requests`);
  });

  await check('E3. api/client.ts: gateway/network retry eligibility starts with `method === \'GET\'`', () => {
    const sf = parse('src/api/client.ts');
    const decl = findAll(sf, (n) => ts.isVariableDeclaration(n) && n.name.getText(sf) === 'canRetry')[0];
    expect(decl && decl.initializer, 'const canRetry not found');
    const init = decl.initializer.getText(sf).replace(/\s+/g, ' ');
    expect(/^method === 'GET' && /.test(init), `canRetry = ${init}`);
  });

  console.log(failures === 0
    ? `\nAll send-timeout checks passed (${passed}).`
    : `\n${failures} check(s) failed, ${passed} passed.`);
  process.exit(failures === 0 ? 0 : 1);
})();
