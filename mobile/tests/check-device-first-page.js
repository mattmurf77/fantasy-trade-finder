#!/usr/bin/env node
// WHY THIS EXISTS (200 ms path C, scope-eng-200ms §2 "C device page", §3, §8
// risk 2; PRD #339 §10.1 approach B, AC-L1's P32 clause, §5.x row 5): the
// phone now renders a trade card at the tap from a page it already holds.
// That is only honest while the page is bounded and the server stays
// authoritative. Ways it goes wrong without anyone seeing it on a device:
//   - a page older than the viewer-roster bound (300 s), or one for another
//     league, format, scope or account, renders as current;
//   - the tap waits on a request before rendering a held page, or offline
//     waits at all (row 5: "Never a wait");
//   - the revalidation never runs, or its answer is appended instead of
//     merged with whole-deck semantics, so a card the server dropped stays
//     fronted with Like/Pass live (U2, AC-L5), or the deck pages from the
//     stored cursor instead of the response's;
//   - "Updating" shows when nothing is revalidating, or never stops;
//   - a swiped card comes back on the next tap, or a rankings write leaves
//     the pre-write page in place (or a deck that predates it writes its
//     cards back on the next swipe), or another account reads it;
//   - a league or format switch lets the OLD deck's cards be written under
//     the NEW key, so the next tap there renders another league's or
//     format's trades (release-lead's P1-a).
// What it does: transpiles and EXECUTES utils/devicePage.ts (with the real
// utils/tradePages.ts) and state/devicePageStore.ts (stubbed AsyncStorage,
// network and API); then pins the screen, client and session wiring by
// source shape. HONEST LABEL (G-035): the executed parts prove the rules and
// the store; the source pins prove the screen calls them, not that a device
// renders them — the TestFlight checklist covers that.
//
// Run: node tests/check-device-first-page.js   (or: npm run test:device-first-page)
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
let ts;
try { ts = require('typescript'); } catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}
const ROOT = path.join(__dirname, '..', '..');
const SRC = path.join(__dirname, '..', 'src');
const read = (r) => fs.readFileSync(path.join(SRC, r), 'utf8');
const stripComments = (t) => t.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
function compile(source, context = {}) {
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS,
  } }).outputText, { module, exports: module.exports, Set, Map, Math, Number, Array, JSON, Promise, ...context });
  return module.exports;
}
let failures = 0;
function check(name, fn) {
  return Promise.resolve().then(fn).then(
    () => console.log(`  ✓ ${name}`),
    (e) => { failures++; console.log(`  ✗ ${name}\n      ${e.message}`); },
  );
}
function eq(a, b, msg) {
  const A = JSON.stringify(a); const B = JSON.stringify(b);
  if (A !== B) throw new Error(`${msg || 'mismatch'}: got ${A}, want ${B}`);
}
function ok(c, msg) { if (!c) throw new Error(msg); }
const flush = () => new Promise((r) => setImmediate(r));

const P = compile(read('utils/tradePages.ts'));
const loadRules = () => compile(read('utils/devicePage.ts'), {
  require: (name) => {
    if (name !== './tradePages') throw new Error(`utils/devicePage.ts must stay pure: one runtime import, ./tradePages (saw ${name})`);
    return P;
  },
});
const D = loadRules();
const card = (id, hash, extra = {}) => ({ trade_id: id, ...(hash ? { trade_hash: hash } : {}), ...extra });
const ids = (cs) => cs.map((c) => c.trade_id);
const S = 'organic:f=0.50';
const T0 = 1_800_000_000_000;
const page1 = (over = {}) => ({
  job_id: 'j1', status: 'complete', error: null, opponents_done: 9, opponents_total: 9,
  cards: [card('a', 'ha'), card('b', 'hb'), card('c', 'hc')],
  cursor: 3, total_ready: 90, deck_id: 'j1', pool_exhausted: false, freshness_state: 'fresh',
  serve_source: 'page', ...over,
});

// A fresh store module per scenario, over shared stubs.
function loadStore(env) {
  return compile(read('state/devicePageStore.ts'), {
    Date: { now: () => (env.clock ?? Date.now()) },
    setTimeout: (fn) => { Promise.resolve().then(fn); return 0; },
    clearTimeout: () => {},
    require: (name) => {
      switch (name) {
        case '@react-native-async-storage/async-storage': return { default: env.storage };
        case '@tanstack/react-query': return { onlineManager: { isOnline: () => env.online } };
        case '../api/client': return { setOnWriteRequest: (fn) => { env.onWrite = fn; } };
        case '../api/trades': return { generateTrades: (body, paging) => {
          env.calls.push({ body, paging });
          return env.respond(body, paging);
        } };
        case '../utils/devicePage': return D;
        default: throw new Error(`devicePageStore.ts: unexpected import ${name}`);
      }
    },
  });
}
function makeStorage(initial = {}) {
  const m = new Map(Object.entries(initial));
  return {
    m,
    getItem: async (k) => (m.has(k) ? m.get(k) : null),
    setItem: async (k, v) => { m.set(k, v); },
    removeItem: async (k) => { m.delete(k); },
    getAllKeys: async () => [...m.keys()],
    multiGet: async (ks) => ks.map((k) => [k, m.has(k) ? m.get(k) : null]),
    multiRemove: async (ks) => { for (const k of ks) m.delete(k); },
  };
}
function makeEnv(over = {}) {
  return { storage: makeStorage(), online: true, calls: [], onWrite: null,
    respond: async () => page1(), ...over };
}

const trades = read('screens/TradesScreen.tsx');
const code = stripComments(trades);
function between(text, start, end) {
  const a = text.indexOf(start);
  ok(a >= 0, `marker not found: ${start}`);
  const b = text.indexOf(end, a + start.length);
  ok(b >= 0, `end marker not found after ${start}: ${end}`);
  return text.slice(a, b);
}
// `signature` ends at the parameter list's '(': the body is the first brace
// after the matching ')' (so an object-typed parameter is skipped).
function fnBody(text, signature) {
  const a = text.indexOf(signature);
  ok(a >= 0, `function not found: ${signature}`);
  let i = a + signature.length - 1;
  for (let parens = 0; i < text.length; i++) {
    if (text[i] === '(') parens++;
    else if (text[i] === ')' && --parens === 0) break;
  }
  i = text.indexOf('{', i);
  let depth = 0;
  for (let j = i; j < text.length; j++) {
    if (text[j] === '{') depth++;
    else if (text[j] === '}' && --depth === 0) return text.slice(a, j + 1);
  }
  throw new Error(`unbalanced: ${signature}`);
}

// The body of the screen's useEffect whose callback contains `marker`, as a
// function of the names it reads: the guard runs the screen's OWN code.
function screenEffect(marker, names) {
  const sf = ts.createSourceFile('T.tsx', trades, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const found = [];
  (function visit(n) {
    if (ts.isCallExpression(n) && n.expression.getText(sf) === 'useEffect'
        && n.arguments[0] && ts.isArrowFunction(n.arguments[0])
        && n.arguments[0].body.getText(sf).includes(marker)) {
      found.push(n.arguments[0].body.getText(sf));
    }
    ts.forEachChild(n, visit);
  })(sf);
  ok(found.length === 1, `exactly one useEffect containing ${marker} (found ${found.length})`);
  return compile(`module.exports = function (env) { const { ${names.join(', ')} } = env; ${found[0]} };`);
}
// The balanced `{ … }` block that follows `marker` in the raw source.
function blockAfter(text, marker) {
  const a = text.indexOf(marker);
  ok(a >= 0, `marker not found: ${marker}`);
  const i = text.indexOf('{', a + marker.length - 1);
  for (let j = i, depth = 0; j < text.length; j++) {
    if (text[j] === '{') depth++;
    else if (text[j] === '}' && --depth === 0) return text.slice(i, j + 1);
  }
  throw new Error(`unbalanced after ${marker}`);
}

// A check that awaits something that never settles would let the event loop
// drain and node exit 0 mid-run: an unfinished run fails instead.
let finished = false;
process.on('exit', () => {
  if (!finished) {
    console.log('\ncheck-device-first-page did not finish (a check hung): FAILED');
    process.exitCode = 1;
  }
});

(async () => {
  console.log('check-device-first-page:');

  // ── 1. The rules (utils/devicePage.ts, executed) ────────────────────────
  await check('1a. stored per (user, league, format) under a versioned key; unknown parts store nothing', () => {
    eq(D.devicePageKey('u1', 'L1', '1qb_ppr'), 'ftf_trade_device_page_v1:u1:L1:1qb_ppr');
    ok(D.devicePageKey('u1', 'L2', '1qb_ppr') !== D.devicePageKey('u1', 'L1', '1qb_ppr'), 'a league switch is another key');
    ok(D.devicePageKey('u1', 'L1', 'sf_tep') !== D.devicePageKey('u1', 'L1', '1qb_ppr'), 'a format switch is another key');
    ok(D.devicePageKey('u2', 'L1', '1qb_ppr') !== D.devicePageKey('u1', 'L1', '1qb_ppr'), 'another account is another key');
    eq([D.devicePageKey('', 'L', 'f'), D.devicePageKey('u', null, 'f'), D.devicePageKey('u', 'L', null)], [null, null, null]);
  });
  await check('1b. only the organic default scope (the server\'s page-store scope string) has a device page', () => {
    eq(D.devicePageScope({ league_id: 'L', fairness_threshold: 0.5 }), 'organic:f=0.50');
    eq(D.devicePageScope({ league_id: 'L', fairness_threshold: 0.75 }), 'organic:f=0.75');
    const nulls = [
      { league_id: 'L', fairness_threshold: 0.5, pinned_give_players: ['p'] },
      { league_id: 'L', fairness_threshold: 0.5, pinned_receive_players: ['p'] },
      { league_id: 'L', fairness_threshold: 0.5, opponent_user_id: 'o' },
      { league_id: 'L', fairness_threshold: 0.5, trade_intent: 'tier_up' },
      { league_id: 'L', fairness_threshold: 0.5, force: true },
      { league_id: 'league_demo', fairness_threshold: 0.5 },
      { league_id: 'no_league', fairness_threshold: 0.5 },
      { league_id: 'L' },
    ].map((r) => D.devicePageScope(r));
    eq(nulls, [null, null, null, null, null, null, null, null]);
    ok(D.devicePageScope({ league_id: 'L', fairness_threshold: 0.5, pinned_give_players: [] }) === S,
      'an empty pin list is still organic (the request omits it)');
  });
  await check('1c. max age: fresh renders, stale / missing / another scope / empty / clock-back never do', () => {
    eq(D.DEVICE_PAGE_MAX_AGE_S, 300, 'the PRD §5.1 viewer-roster bound');
    const p = D.devicePageFrom(page1(), { scope: S, validatedAt: T0 });
    eq([0, 299_999, 300_000].map((dt) => D.devicePageUsable(p, S, T0 + dt)), [true, true, true], 'fresh, inside the bound');
    eq(D.devicePageUsable(p, S, T0 + 300_001), false, 'stale: past 300 s');
    eq(D.devicePageUsable(p, S, T0 + 6 * 60_000), false, 'the 6-minute tap');
    eq(D.devicePageUsable(null, S, T0), false, 'missing');
    eq(D.devicePageUsable(p, 'organic:f=0.75', T0), false, 'another scope (fairness toggled)');
    eq(D.devicePageUsable(p, null, T0), false, 'a pinned / scoped request');
    eq(D.devicePageUsable({ ...p, cards: [] }, S, T0), false, 'nothing left');
    eq(D.devicePageUsable(p, S, T0 - 1), false, 'a clock that went backwards reads as stale');
  });
  await check('1d. only a complete, non-error, ownership-checked P2 page is kept; one page at most', () => {
    const p = D.devicePageFrom(page1({ built_at: '2026-10-24T00:00:00Z', roster_fp: 'rfp1:x', values_snapshot_id: 'vsn1:y' }),
      { scope: S, validatedAt: T0 });
    eq([p.v, p.scope, ids(p.cards), p.job_id, p.deck_id, p.cursor, p.total_ready, p.pool_exhausted, p.validated_at],
      [1, S, ['a', 'b', 'c'], 'j1', 'j1', 3, 90, false, T0]);
    eq([p.built_at, p.roster_fp, p.vsn], ['2026-10-24T00:00:00Z', 'rfp1:x', 'vsn1:y'], 'fingerprints stored as sent');
    eq([D.devicePageFrom(page1(), { scope: S, validatedAt: T0 }).roster_fp], [null], 'absent fingerprints are null');
    const many = page1({ cards: Array.from({ length: 45 }, (_, i) => card(`c${i}`, `h${i}`)) });
    eq(D.devicePageFrom(many, { scope: S, validatedAt: T0 }).cards.length, D.DEVICE_PAGE_MAX_CARDS);
    eq(D.DEVICE_PAGE_MAX_CARDS, 30);
    const refused = [
      page1({ status: 'running' }), page1({ status: 'error' }), page1({ error: 'boom' }),
      page1({ freshness_state: 'updating' }), page1({ deck_id: undefined }), page1({ cards: [] }),
      page1({ cursor: undefined }),
    ].map((r) => D.devicePageFrom(r, { scope: S, validatedAt: T0 }));
    eq(refused, [null, null, null, null, null, null, null]);
  });
  await check('1e. swipe update: an acted-on card leaves the page (by trade_hash, else trade_id)', () => {
    const p = D.devicePageFrom(page1({ cards: [card('a', 'ha'), card('b', 'hb'), card('c')] }), { scope: S, validatedAt: T0 });
    eq(ids(D.withoutCard(p, 'hb').cards), ['a', 'c']);
    eq(ids(D.withoutCard(p, 'c').cards), ['a', 'b']);
    ok(D.withoutCard(p, 'zz') === p, 'a card the page does not hold changes nothing');
  });
  await check('1f. a deck never writes over a page the server validated later', () => {
    const p = D.devicePageFrom(page1(), { scope: S, validatedAt: T0 });
    eq([D.deckMayWrite(null, T0), D.deckMayWrite(p, T0), D.deckMayWrite(p, T0 + 1), D.deckMayWrite(p, T0 - 1)],
      [true, true, true, false]);
  });
  await check('1g. background refresh throttle: once per key per 60 s', () => {
    eq(D.DEVICE_PAGE_REFRESH_MIN_S, 60);
    eq([D.refreshDue(undefined, T0), D.refreshDue(T0, T0 + 59_999), D.refreshDue(T0, T0 + 60_000), D.refreshDue(T0, T0 - 5)],
      [true, false, true, true]);
  });
  await check('1h. the revalidation merge: seen cards stay, unseen ones take the server\'s order, an absent fronted card is withdrawn', () => {
    // a: swiped (seen); b: fronted; c, d: unseen device cards.
    const held = [card('a', 'ha'), card('b', 'hb'), card('c', 'hc'), card('d', 'hd')];
    const gone = D.mergeRevalidation(held, [card('e', 'he'), card('c2', 'hc')], 'hb');
    eq(ids(gone.cards), ['a', 'b', 'e', 'c2'], 'unseen d dropped, server order behind the front');
    eq(gone.withdrawFront, true, 'the fronted card the server lacks is withdrawn in place');
    ok(gone.cards[0] === held[0] && gone.cards[1] === held[1], 'the seen and fronted cards are the same objects, same slots');
    const kept = D.mergeRevalidation(held, [card('e', 'he'), card('b2', 'hb'), card('c', 'hc')], 'hb');
    eq([ids(kept.cards), kept.withdrawFront], [['a', 'b', 'e', 'c'], false], 'a fronted card the server still serves stays fronted');
    const past = D.mergeRevalidation(held, [card('e', 'he'), card('a', 'ha')], null);
    eq([ids(past.cards), past.withdrawFront], [['a', 'b', 'c', 'd', 'e'], false], 'past the last card: appends only');
    // It IS the whole-deck merge, not the append merge.
    eq(ids(gone.cards), ids(P.mergeDeckPage(held, [card('e', 'he'), card('c2', 'hc')], 'hb', true).cards));
    ok(ids(P.mergeDeckPage(held, [card('e', 'he')], 'hb', false).cards).includes('d'), 'control: an append would have kept d');
  });
  await check('1i. the adopted snapshot reports serve_source "device" under the tap\'s search id', () => {
    const p = D.devicePageFrom(page1(), { scope: S, validatedAt: T0 });
    const snap = D.devicePageSnapshot(p, 's-9');
    eq([snap.serve_source, snap.search_id, snap.status, snap.deck_id, snap.cursor, snap.job_id, snap.freshness_state],
      ['device', 's-9', 'complete', 'j1', 3, 'j1', 'fresh']);
    eq(ids(snap.cards), ['a', 'b', 'c']);
    ok(P.isPagedEnvelope(snap), 'adoptable: a paged envelope');
  });
  await check('1j. storage round trip; anything malformed reads as no page', () => {
    const p = D.devicePageFrom(page1(), { scope: S, validatedAt: T0 });
    eq(D.parseDevicePage(JSON.stringify(p)), p);
    const bad = [null, '', 'nope', '{}', JSON.stringify({ ...p, v: 2 }), JSON.stringify({ ...p, cards: [{}] }),
      JSON.stringify({ ...p, validated_at: 'x' }), JSON.stringify({ ...p, deck_id: null })].map(D.parseDevicePage);
    eq(bad, [null, null, null, null, null, null, null, null]);
  });
  await check('1k. the client\'s own rankings / preference writes are named, query and host ignored', () => {
    for (const p of D.RANKING_WRITE_PATHS) ok(D.isRankingWritePath(p), `${p} discards`);
    ok(D.isRankingWritePath('https://api.example/api/rank3?x=1'), 'absolute URL + query');
    eq(['/api/trades/generate', '/api/trades/swipe', '/api/trio/skip', '/api/rankings', '/api/rank3x']
      .map(D.isRankingWritePath), [false, false, false, false, false]);
    eq(D.RANKING_WRITE_PATHS.length, 8);
    // A format switch discards too (an organic page refreshed during it may be the other format's).
    eq([D.discardsDevicePages('/api/scoring/switch'), D.discardsDevicePages('/api/rank3?x=1'),
      D.discardsDevicePages('/api/trades/swipe')], [true, true, false]);
  });
  await check('1l. every named write is a path the app really posts (drift guard)', () => {
    const api = ['api/rankings.ts', 'api/league.ts'].map(read).join('\n');
    for (const p of D.RANKING_WRITE_PATHS) ok(api.includes(`'${p}'`), `${p} not posted by api/rankings.ts or api/league.ts`);
  });
  await check('1m. the max age has its cross-client-invariants row', () => {
    const doc = fs.readFileSync(path.join(ROOT, 'docs', 'cross-client-invariants.md'), 'utf8');
    const row = between(doc, '## Device-held first page', '\n---');
    ok(/`DEVICE_PAGE_MAX_AGE_S` \| \*\*300\*\*/.test(row), 'row states DEVICE_PAGE_MAX_AGE_S = 300');
    for (const p of D.RANKING_WRITE_PATHS) ok(row.includes(`\`${p}\``), `row lists ${p}`);
  });

  // ── 2. The store (state/devicePageStore.ts, executed) ───────────────────
  const KEY = D.devicePageKey('u1', 'L1', '1qb_ppr');
  const KEY2 = D.devicePageKey('u1', 'L2', '1qb_ppr');
  const target = { key: KEY, scope: S, request: { league_id: 'L1', fairness_threshold: 0.5 } };
  await check('2a. a refresh asks for page 1 under NO search id, keeps a storable answer, and persists it', async () => {
    const env = makeEnv();
    const st = loadStore(env);
    await st.refreshDevicePage(target, T0);
    eq(env.calls.length, 1);
    eq([env.calls[0].body, env.calls[0].paging], [target.request, {}], 'organic body; paging with no searchId');
    eq(ids(st.readDevicePage(KEY).cards), ['a', 'b', 'c']);
    await flush(); await flush();
    ok(env.storage.m.has(KEY), 'persisted under its key');
    eq(D.parseDevicePage(env.storage.m.get(KEY)).deck_id, 'j1');
  });
  await check('2b. throttled to once per key per 60 s; one at a time; per key', async () => {
    let release;
    const env = makeEnv({ respond: () => new Promise((r) => { release = () => r(page1()); }) });
    const st = loadStore(env);
    const first = st.refreshDevicePage(target, T0);
    await st.refreshDevicePage(target, T0 + 61_000); // in flight: skipped
    release(); await first;
    await st.refreshDevicePage(target, T0 + 30_000);
    eq(env.calls.length, 1, 'inside 60 s: no request');
    const p2 = st.refreshDevicePage({ ...target, key: KEY2 }, T0 + 30_000); release(); await p2;
    eq(env.calls.length, 2, 'another key is not throttled by this one');
    const p3 = st.refreshDevicePage(target, T0 + 60_000); release(); await p3;
    eq(env.calls.length, 3, 'due again at 60 s');
  });
  await check('2c. offline: no request at all', async () => {
    const env = makeEnv({ online: false });
    await loadStore(env).refreshDevicePage(target, T0);
    eq(env.calls.length, 0);
  });
  await check('2d. a server answer that can\'t be kept discards the held page; a failed request keeps it', async () => {
    const env = makeEnv();
    const st = loadStore(env);
    await st.refreshDevicePage(target, T0);
    env.respond = async () => { throw new Error('offline'); };
    await st.refreshDevicePage(target, T0 + 60_000);
    ok(st.readDevicePage(KEY), 'a failed request keeps what is held (the max age bounds it)');
    for (const over of [{ status: 'running' }, { freshness_state: 'updating' }, { status: 'error' }]) {
      const e2 = makeEnv();
      const s2 = loadStore(e2);
      await s2.refreshDevicePage(target, T0);
      ok(s2.readDevicePage(KEY), 'seeded');
      e2.respond = async () => page1(over);
      await s2.refreshDevicePage(target, T0 + 60_000);
      eq(s2.readDevicePage(KEY), null, `discarded on ${JSON.stringify(over)}`);
    }
  });
  await check('2e. the client\'s own ranking write discards every held page, on send; other writes keep them', async () => {
    const env = makeEnv();
    const st = loadStore(env);
    ok(typeof env.onWrite === 'function', 'the store registers the client write listener at import');
    await st.refreshDevicePage(target, T0);
    await st.refreshDevicePage({ ...target, key: KEY2 }, T0);
    env.onWrite('/api/trades/swipe');
    ok(st.readDevicePage(KEY) && st.readDevicePage(KEY2), 'a swipe POST is not a ranking write');
    env.onWrite('/api/rank3');
    eq([st.readDevicePage(KEY), st.readDevicePage(KEY2)], [null, null], 'a trio swipe discards every page the user holds');
    await flush(); await flush();
    ok(!env.storage.m.has(KEY) && !env.storage.m.has(KEY2), 'and from disk');
  });
  await check('2f2. a refresh that was out when the format switched drops its answer (it may be the other format\'s)', async () => {
    let release;
    const env = makeEnv({ respond: () => new Promise((r) => { release = () => r(page1()); }) });
    const st = loadStore(env);
    const pending = st.refreshDevicePage(target, T0);
    env.onWrite('/api/scoring/switch');
    release(); await pending;
    eq(st.readDevicePage(KEY), null, 'never kept under this format\'s key');
  });
  await check('2f. a refresh that was out when a ranking write happened drops its answer', async () => {
    let release;
    const env = makeEnv({ respond: () => new Promise((r) => { release = () => r(page1()); }) });
    const st = loadStore(env);
    const pending = st.refreshDevicePage(target, T0);
    env.onWrite('/api/tiers/save');
    release(); await pending;
    eq(st.readDevicePage(KEY), null, 'the pre-write answer is never kept');
  });
  await check('2g. swiping removes the card from the page; the last one discards it', async () => {
    const env = makeEnv();
    const st = loadStore(env);
    await st.refreshDevicePage(target, T0);
    st.removeDeviceCard(KEY, 'hb');
    eq(ids(st.readDevicePage(KEY).cards), ['a', 'c']);
    st.removeDeviceCard(null, 'ha');
    st.removeDeviceCard(KEY, 'ha'); st.removeDeviceCard(KEY, 'hc');
    eq(st.readDevicePage(KEY), null);
  });
  await check('2h. clearDevicePages (sign-out / account switch) removes every device page and nothing else', async () => {
    const env = makeEnv();
    env.storage.m.set('ftf:trades:fairness_on', 'on');
    const st = loadStore(env);
    await st.refreshDevicePage(target, T0);
    await st.refreshDevicePage({ ...target, key: KEY2 }, T0);
    await flush(); await flush();
    await st.clearDevicePages();
    eq([st.readDevicePage(KEY), st.readDevicePage(KEY2)], [null, null]);
    eq([...env.storage.m.keys()], ['ftf:trades:fairness_on']);
  });
  await check('2i. a launch hydrates stored pages; a malformed one is ignored', async () => {
    const p = D.devicePageFrom(page1(), { scope: S, validatedAt: T0 });
    const env = makeEnv({ storage: makeStorage({ [KEY]: JSON.stringify(p), [KEY2]: '{"v":9}' }) });
    const st = loadStore(env);
    eq(st.readDevicePage(KEY), null, 'nothing before hydration');
    await st.hydrateDevicePages();
    eq(ids(st.readDevicePage(KEY).cards), ['a', 'b', 'c']);
    eq(st.readDevicePage(KEY2), null);
  });

  await check('2j. a save never keeps cards validated before the last discard (a swipe after a re-rank writes nothing)', async () => {
    const env = makeEnv({ clock: T0 });
    const st = loadStore(env);
    const deckPage = (validatedAt, cards = [card('a', 'ha'), card('b', 'hb')]) =>
      D.devicePageFrom(page1({ cards }), { scope: S, validatedAt });
    st.saveDevicePage(KEY, deckPage(T0), T0);
    ok(st.readDevicePage(KEY), 'control: a deck validated now is kept');
    env.clock = T0 + 5_000;
    env.onWrite('/api/rank3'); // the re-rank: every page goes
    eq(st.readDevicePage(KEY), null, 'discarded by the write');
    env.clock = T0 + 9_000;
    st.saveDevicePage(KEY, deckPage(T0), T0); // the old deck's next swipe
    eq(st.readDevicePage(KEY), null, 'cards validated before the re-rank are refused');
    st.saveDevicePage(KEY2, deckPage(T0 + 4_999), T0 + 4_999);
    eq(st.readDevicePage(KEY2), null, 'on every key (the write discarded them all)');
    st.saveDevicePage(KEY, deckPage(T0 + 6_000), T0 + 6_000);
    ok(st.readDevicePage(KEY), 'a deck revalidated after the write is kept');
    // A key-level discard (a server answer that can't be kept) bars older cards for that key only.
    st.saveDevicePage(KEY, null, T0 + 7_000);
    st.saveDevicePage(KEY, deckPage(T0 + 6_500), T0 + 6_500);
    eq(st.readDevicePage(KEY), null, 'older than the key discard: refused');
    st.saveDevicePage(KEY2, deckPage(T0 + 6_500), T0 + 6_500);
    ok(st.readDevicePage(KEY2), 'another key is not barred by it');
    // A deck's own unkeepable answer (asOf = its validation) doesn't bar that same deck later.
    st.saveDevicePage(KEY, null, T0 + 8_000);
    st.saveDevicePage(KEY, deckPage(T0 + 8_000), T0 + 8_000);
    ok(st.readDevicePage(KEY), 'same validation time: kept');
    // Swipes emptying a page don't bar the deck that still holds more cards.
    st.removeDeviceCard(KEY, 'ha'); st.removeDeviceCard(KEY, 'hb');
    eq(st.readDevicePage(KEY), null, 'emptied by swipes');
    st.saveDevicePage(KEY, deckPage(T0 + 8_000, [card('c', 'hc')]), T0 + 8_000);
    ok(st.readDevicePage(KEY), 'the same deck writes its next cards');
    // Sign-out bars everything validated before it too.
    env.clock = T0 + 20_000;
    await st.clearDevicePages();
    st.saveDevicePage(KEY, deckPage(T0 + 19_000), T0 + 19_000);
    eq(st.readDevicePage(KEY), null, 'validated before the sign-out: refused');
  });

  // ── 3. The screen: no wait, background revalidation, "Updating" ─────────
  await check('3a. the tap renders a held page with NO network wait (no request, timer or await before the push)', () => {
    const push = fnBody(code, 'function pushWithFirstPage(');
    const branch = between(push, 'const held = readDevicePage(deviceKey);', 'let pushed = false;');
    ok(/if \(devicePageUsable\(held, devicePageScope\(request\), Date\.now\(\)\)\) \{\s*pushDeck\(\{\s*request,\s*snapshot: devicePageSnapshot\(held, fork\.searchId\),\s*device: true,\s*validatedAt: held\.validated_at,\s*deviceKey,\s*\}\);\s*return;\s*\}/.test(branch),
      'a usable device page is pushed at once, then return');
    ok(!/generateTrades|await|setTimeout|\.then\(/.test(branch), 'nothing in the device / offline branches waits on anything');
    ok(push.indexOf('const held = readDevicePage(deviceKey);') < push.indexOf('generateTrades(request'),
      'the device check runs before the network page 1');
  });
  await check('3b. offline at the tap with no usable page: pushed at once, the Offline state in the card rect', () => {
    const push = fnBody(code, 'function pushWithFirstPage(');
    ok(/if \(!readOnline\(\)\) \{\s*pushDeck\(\);\s*return;\s*\}/.test(push), 'offline pushes at once');
    ok(push.indexOf('if (!readOnline())') < push.indexOf('setTimeout(() => go(), FIRST_PAGE_PUSH_DEADLINE_MS)'),
      'before the page-1 deadline is ever armed');
    ok(/\) : !online && deck\.length === 0 && !deckFailure && generateMutation\.isPending \? \(\s*<DeckOfflineCard minHeight=\{topCardH\} onRetry=\{handleOfflineTapRetry\} \/>/.test(code),
      'the paused search renders the Offline card, ahead of any wait card');
    ok(code.indexOf('<DeckOfflineCard minHeight={topCardH} onRetry={handleOfflineTapRetry} />')
      < code.indexOf(") : fairPending || generateMutation.isPending || job?.status === 'running' ? ("),
      'Offline outranks the "Looking for trades…" wait card');
  });
  await check('3c. the pushed deck revalidates in the background, right after mount, with the tap\'s own request', () => {
    ok(/useState<'none' \| 'running' \| 'failed' \| 'done'>\(\s*\(\) => \(adopted\?\.device \? \(readOnline\(\) \? 'running' : 'failed'\) : 'none'\),\s*\)/.test(code),
      'a device deck starts revalidating (offline: refresh-failed from the first frame)');
    ok(/useEffect\(\(\) => \{\s*if \(adopted\?\.device\) revalidateDevicePage\(\);\s*\}, \[\]\);/.test(code), 'mount effect');
    const reval = fnBody(code, 'function revalidateDevicePage(');
    ok(reval.includes('generateTrades(adopted.request, { searchId: adopted.snapshot.search_id })'), 'same request, same search');
    ok(/if \(!readOnline\(\)\) \{\s*setDevicePhase\('failed'\);\s*return;\s*\}/.test(reval), 'offline fails at once, no request');
    ok(/applyJobResult\(next, epoch, deckEpochRef\.current\) === null/.test(reval), 'the epoch guard drops a superseded answer');
    ok(/useEffect\(\(\) => \{\s*if \(online && devicePhase === 'failed'\) revalidateDevicePage\(\);\s*\}, \[online\]\);/.test(code), 'reconnect retries');
    ok(/function handleDeckMoreRetry\(\) \{\s*haptics\.selection\(\);\s*if \(devicePhase === 'failed'\) \{\s*revalidateDevicePage\(\);\s*return;\s*\}/.test(code), 'Retry retries');
  });
  await check('3d. "Updating" only while the revalidation runs, for at most DEVICE_REVALIDATE_MAX_MS', () => {
    ok(/const deckUpdating = devicePhase === 'running'\s*\|\| \(pagedDeck && job\?\.freshness_state === 'updating'\);/.test(code), 'deckUpdating');
    eq((code.match(/setDevicePhase\('running'\)/g) || []).length, 1, "one place enters 'running'");
    const reval = fnBody(code, 'function revalidateDevicePage(');
    ok(reval.includes("setDevicePhase('running')"), "…inside revalidateDevicePage");
    ok(/setDevicePhase\('done'\)/.test(reval) && /\.catch\(\(\) => \{[\s\S]*?setDevicePhase\('failed'\)/.test(reval)
      && /setTimeout\(\(\) => \{[\s\S]*?setDevicePhase\(\(p\) => \(p === 'running' \? 'failed' : p\)\)[\s\S]*?\}, DEVICE_REVALIDATE_MAX_MS\)/.test(reval),
      'every way out of running: done, failed, timed out');
    eq(D.DEVICE_REVALIDATE_MAX_MS, 10_000);
    ok(/const deviceRefreshFailed = devicePhase === 'failed';/.test(code)
      && /\{deviceRefreshFailed \? \(\s*<DeckRefreshFailedLine onRetry=\{handleDeckMoreRetry\} \/>\s*\) : null\}/.test(code),
      'failed → the refresh-failed line, under the card');
    ok(/headerRight: deckUpdating \? \(\) => <DeckUpdatingLabel \/> : undefined/.test(code), 'the pushed deck\'s header label reads deckUpdating');
  });
  await check('3e. the response merges with whole-deck semantics, and paging continues from ITS deck_id / cursor', () => {
    const reval = fnBody(code, 'function revalidateDevicePage(');
    ok(reval.includes('applyPage(next, { revalidation: true })'), 'the revalidation is applied as one');
    const apply = fnBody(code, 'function applyPage(');
    ok(/const merged = opts\?\.revalidation\s*\? mergeRevalidation\(deckRef\.current, next\.cards, frontKey\)/.test(apply), 'mergeRevalidation');
    // (The job is built by tradePages.nextDeckJob since the kill-switch fix; executed here.)
    ok(/nextDeckJob\(prev, next, merged\.cards, \{ revalidation: opts\?\.revalidation, rebind \}\)/.test(apply)
      && P.nextDeckJob({ job_id: 'j', cursor: 3, deck_id: 'old', cards: [] },
        { job_id: 'n', status: 'complete', cursor: 30, deck_id: 'new', cards: [] }, [], { revalidation: true }).deck_id === 'new'
      && P.nextDeckJob({ job_id: 'j', cursor: 3, deck_id: 'old', cards: [] },
        { job_id: 'n', status: 'complete', cursor: 30, cards: [] }, [], { revalidation: true }).deck_id === undefined,
      "the response's deck_id, even a new one (or none: never the stored page's)");
    ok(/if \(merged\.withdrawFront && front\) \{\s*setWithdrawnIds/.test(apply), 'an absent fronted card is withdrawn in place');
    const trigger = between(code, 'if (!snap?.job_id || !online) return;', 'void fetchNextPage();');
    ok(/if \(devicePhase === 'running' \|\| devicePhase === 'failed'\) return;/.test(trigger), 'no paging from the stored cursor');
    ok(/unseen, online, pageKick, devicePhase\]\);/.test(code), 'the trigger re-runs when the revalidation lands');
    ok(/const endPhase: PageFetchPhase = devicePhase === 'running' \? 'loading'\s*: devicePhase === 'failed' \? 'failed'\s*: pagePhase;/.test(code),
      'a stored envelope never ends the deck');
  });
  await check('3f. the background refresh: Trades landing focus and app foreground only, never the tap', () => {
    ok(/if \(isResultsPushed \|\| !navFocused \|\| !devicePageTarget\) return;\s*void hydrateDevicePages\(\)\.then\(\(\) => refreshDevicePage\(devicePageTarget\)\);/.test(code), 'focus');
    ok(/if \(st !== 'active'\) return;\s*void useSession\.getState\(\)\.revalidateSession\(\)\s*\.then\(\(\) => hydrateDevicePages\(\)\)\s*\.then\(\(\) => refreshDevicePage\(devicePageTarget\)\);/.test(code),
      'foreground, after that foreground\'s session-init');
    eq((code.match(/refreshDevicePage\(/g) || []).length, 2, 'exactly the two triggers');
    for (const fn of ['function pushWithFirstPage(', 'function handleInlineFindATrade(', 'function handleFindTrades(']) {
      ok(!fnBody(code, fn).includes('refreshDevicePage'), `${fn} never refreshes`);
    }
    ok(/const request: GenerateBody = \{ league_id: leagueId, fairness_threshold: effectiveFairness \};/.test(code), 'the organic request the tap sends');
    ok(/const devicePageStoreOn = useFlag\('trade\.first_page_store'\);\s*const deviceKey = devicePageStoreOn && !isDemo\s*\? devicePageKey\(userId, leagueId, activeFormat\)\s*: null;/.test(code),
      'rides the page-store flag; never the demo');
  });
  await check('3g. swipes keep the page current: every disposition removes its card; the deck rewrites its unseen cards', () => {
    const adv = fnBody(code, 'function advance(');
    ok(/const actedKey = deckCardKey\(rawTopCard \?\? topCard\);\s*actedDeviceKeysRef\.current\.add\(actedKey\);\s*removeDeviceCard\(deviceKey, actedKey\);/.test(adv),
      'advance() removes the acted-on card, and remembers it');
    const eff = between(code, 'const scope = deckScopeRef.current;', 'job?.error, deck, rawTopCard?.trade_id, withdrawnIds]);');
    ok(/if \(!deckMayWrite\(readDevicePage\(deviceKey\), validatedAt\)\) return;/.test(eff), 'never over a later page');
    ok(/deck\.slice\(frontAt\)\s*\.filter\(\(c\) => !withdrawnIds\.has\(c\.trade_id\) && !acted\.has\(deckCardKey\(c\)\)\)/.test(eff),
      'the fronted card onward, never a withdrawn or acted-on one (a deferred advance still fronts it)');
    ok(/saveDevicePage\(deviceKey, devicePageFrom\(job, \{ scope, validatedAt, cards: unacted \}\), validatedAt\);/.test(eff),
      'kept or discarded by the same rule (a discard answers the deck\'s own validation time)');
    ok(/deckScopeRef\.current = lastModelRequestRef\.current\s*\? devicePageScope\(lastModelRequestRef\.current\)\s*: null;\s*deckKeyRef\.current = lastModelKeyRef\.current;\s*validatedAtRef\.current = Date\.now\(\);/.test(code),
      'a model answer stamps its scope, its key and its validation time');
  });

  await check('3h. EXECUTED: the deck writes only under the key it was validated for — a league switch, then a format switch, write nothing under the new key', async () => {
    const save = screenEffect('saveDevicePage(deviceKey', ['deckScopeRef', 'validatedAtRef', 'deckKeyRef', 'deviceKey',
      'job', 'isPagedEnvelope', 'deckMayWrite', 'readDevicePage', 'rawTopCard', 'deck', 'actedDeviceKeysRef',
      'withdrawnIds', 'deckCardKey', 'saveDevicePage', 'devicePageFrom']);
    const formatChange = screenEffect('deckFormatRef.current === activeFormat',
      ['deckFormatRef', 'activeFormat', 'deckKeyRef', 'validatedAtRef']);
    const resetBlock = blockAfter(trades, 'if (!keepAdoptedPage) {');
    ok(resetBlock.includes('setDeck([])'), 'the league reset\'s own block');
    const leagueReset = compile(`module.exports = function (env) {
      const { setDeck, setDeckIdx, deckKeyRef, validatedAtRef, deckScopeRef } = env; ${resetBlock} };`);

    const K1 = D.devicePageKey('u1', 'L1', '1qb_ppr');
    const K2 = D.devicePageKey('u1', 'L2', '1qb_ppr');
    const K1sf = D.devicePageKey('u1', 'L1', 'sf_tep');
    const cards = [card('a', 'ha'), card('b', 'hb'), card('c', 'hc')];
    const env = makeEnv();
    const st = loadStore(env);
    const now = Date.now();
    const refs = () => ({
      deckScopeRef: { current: S }, validatedAtRef: { current: now }, deckKeyRef: { current: K1 },
      actedDeviceKeysRef: { current: new Set() },
    });
    const run = (r, deviceKey) => save({ ...r, deviceKey, job: page1({ cards }), deck: cards, rawTopCard: cards[0],
      withdrawnIds: new Set(), isPagedEnvelope: P.isPagedEnvelope, deckCardKey: P.deckCardKey,
      deckMayWrite: D.deckMayWrite, devicePageFrom: D.devicePageFrom,
      readDevicePage: st.readDevicePage, saveDevicePage: st.saveDevicePage });

    // Control: the deck's own key is written (the harness can write).
    const r = refs();
    run(r, K1);
    eq(ids(st.readDevicePage(K1).cards), ['a', 'b', 'c'], 'its own key');
    // League switch, release-lead's order: the NEW key renders while the old
    // deck's refs are still bound (the reset only schedules setDeck/setJob).
    run(r, K2);
    eq(st.readDevicePage(K2), null, 'league switch: nothing under the new league\'s key, even with stale refs');
    // …and the reset itself nulls them, so nothing can follow.
    leagueReset({ ...r, setDeck: () => {}, setDeckIdx: () => {} });
    eq([r.deckKeyRef.current, r.validatedAtRef.current, r.deckScopeRef.current], [null, null, null], 'the league reset unbinds the deck');
    run(r, K2);
    eq(st.readDevicePage(K2), null, 'still nothing after the reset');

    // Format switch (no deck reset at all): same league, new format.
    const f = refs();
    run(f, K1sf);
    eq(st.readDevicePage(K1sf), null, 'format switch: nothing under the new format\'s key, before the format effect');
    const deckFormatRef = { current: '1qb_ppr' };
    formatChange({ ...f, deckFormatRef, activeFormat: 'sf_tep' });
    eq([f.deckKeyRef.current, f.validatedAtRef.current], [null, null], 'the format change unbinds the deck');
    run(f, K1sf);
    eq(st.readDevicePage(K1sf), null, 'nothing after it either');
    const before = JSON.stringify(st.readDevicePage(K1));
    run(f, K1); // switched back: the old deck stays unbound
    eq(JSON.stringify(st.readDevicePage(K1)), before, 'switching back does not revive the old deck\'s writes');
    // The mount run changes nothing (same format).
    const g = refs();
    formatChange({ ...g, deckFormatRef: { current: '1qb_ppr' }, activeFormat: '1qb_ppr' });
    eq(g.deckKeyRef.current, K1, 'no format change, no unbind');
    // The kill switch (#400): a deck un-paged by a legacy answer keeps nothing for its key.
    const legacyJob = { job_id: 'j1', status: 'complete', error: null, opponents_done: 9, opponents_total: 9, cards };
    save({ ...refs(), deviceKey: K1, job: legacyJob, deck: cards, rawTopCard: cards[0],
      withdrawnIds: new Set(), isPagedEnvelope: P.isPagedEnvelope, deckCardKey: P.deckCardKey,
      deckMayWrite: D.deckMayWrite, devicePageFrom: D.devicePageFrom,
      readDevicePage: st.readDevicePage, saveDevicePage: st.saveDevicePage });
    eq(st.readDevicePage(K1), null, 'a legacy (un-paged) deck discards its key\'s page: C never renders with paging off');
  });
  await check('3i. the key is bound where the deck is validated: adoption (from the landing\'s key) and a model answer (from its request\'s render)', () => {
    ok(/const deckKeyRef = useRef<string \| null>\(adopted\?\.deviceKey \?\? null\);/.test(code), 'adoption');
    ok(/lastModelRequestRef\.current = request;\s*lastModelKeyRef\.current = deviceKey;/.test(code), 'bound with the request it answers');
    ok(/\? \{ request, snapshot, validatedAt: Date\.now\(\), deviceKey \}/.test(code), 'the network first page carries the landing\'s key');
    const eff = between(code, 'const scope = deckScopeRef.current;', 'job?.error, deck, rawTopCard?.trade_id, withdrawnIds]);');
    ok(/if \(!deviceKey \|\| deviceKey !== deckKeyRef\.current\) return;/.test(eff), 'the save effect\'s key check');
    ok(code.indexOf('deckFormatRef.current === activeFormat') < code.indexOf('const scope = deckScopeRef.current;'),
      'the format change runs before the save in the same commit');
  });

  // ── 4. Discards outside the screen ─────────────────────────────────────
  await check('4a. api/client tells the store about every write, when sent and when settled', () => {
    const client = stripComments(read('api/client.ts'));
    ok(/function _noteWrite\(path: string, method: string\): void \{\s*if \(method === 'GET' \|\| !_onWriteRequest\) return;\s*try \{ _onWriteRequest\(path\); \} catch \{\s*\}/.test(client), 'non-GET only; never throws');
    const req = fnBody(client, 'export async function apiRequest<T = unknown>(');
    ok(req.indexOf("_noteWrite(path, opts.method || 'GET');") < req.indexOf('runWithDeadline'), 'on send');
    ok(/\} finally \{\s*_noteWrite\(path, opts\.method \|\| 'GET'\);\s*\}/.test(req), 'on settle');
  });
  await check('4b. sign-out and account switch clear every device page (useSession)', () => {
    const sess = stripComments(read('state/useSession.ts'));
    ok(/import \{ clearDevicePages \} from '\.\/devicePageStore';/.test(sess), 'imported');
    const signOut = between(sess, 'signOut: async () => {', '\n  },');
    ok(/await Promise\.all\(\[[\s\S]*clearDevicePages\(\),[\s\S]*\]\);/.test(signOut), 'signOut awaits it with the other per-account keys');
    const setUser = between(sess, 'setUser: async (u) => {', '\n  },');
    ok(/const previous = get\(\)\.user;\s*if \(previous && previous\.user_id !== u\?\.user_id\) void clearDevicePages\(\);/.test(setUser), 'another account');
    // A demo bypasses setUser (onboarding-eng A1): it clears before it writes the demo user.
    const demo = between(sess, 'startDemoSession: async () => {', '\n  },');
    ok(/const previous = get\(\)\.user;\s*if \(previous && previous\.user_id !== demoUser\.user_id\) void clearDevicePages\(\);\s*set\(\{\s*user:\s*demoUser,/.test(demo), 'a demo over another account');
  });

  await check('4c. the refresh-failed line carries the final copy, and Retry its spoken label (marketing §6 add. 4)', () => {
    const states = read('components/TradeDeckStates.tsx');
    ok(/DECK_REFRESH_FAILED_LINE = "Couldn't refresh\. These trades may be out of date\.";/.test(states), 'line');
    ok(/DECK_REFRESH_FAILED_RETRY_A11Y = 'Retry refreshing trades';/.test(states), 'a11y string');
    ok(/testID="trades\.deck-refresh-failed\.retry"\s*label="Retry"\s*accessibilityLabel=\{DECK_REFRESH_FAILED_RETRY_A11Y\}/.test(states), 'wired on the Retry button');
    ok(/accessibilityLabel=\{accessibilityLabel\}/.test(read('components/chalkline/Button.tsx')), 'Button passes it to the Pressable');
  });

  finished = true;
  console.log(failures ? `\n${failures} failed` : '\nall passed');
  process.exit(failures ? 1 : 0);
})();
