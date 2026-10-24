#!/usr/bin/env node
// WHY THIS EXISTS (200 ms path, scope-eng-200ms §3, §6.3–§6.6; head-eng
// rulings 10 and 16): the deck now arrives in PAGES. Three ways that goes
// wrong without anyone seeing it on a device:
//   - the client stops opting in (no `page`/`search_id` on generate, no
//     `deck`/`cursor` on status), silently falling back to the cumulative
//     snapshot — or the legacy snapshot grows paging fields and an OLD
//     server's response is read as a page;
//   - a later page lands IN FRONT of delivered cards, or a duplicate trade
//     (same trade, new per-build trade_id) is shown twice, or the fairness-
//     off match_score re-sort reshuffles cards the user already has — the
//     fronted card changes under the thumb;
//   - a `replace: true` response yanks the visible card or reorders cards
//     already shown (ruling 16), or the prefetch threshold is a client
//     constant instead of the server's `prefetch_remaining`.
// What it does: transpiles and EXECUTES api/trades.ts (stubbed ./client),
// utils/tradePages.ts, and the screen's orderedDeck memo body; then pins the
// screen's wiring by source shape. HONEST LABEL (G-035): the executed parts
// prove the rules; the source pins prove the screen calls them, not that a
// device renders them — the TestFlight checklist covers that.
//
// Run: node tests/check-trade-pages.js   (or: npm run test:trade-pages)
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
let ts;
try { ts = require('typescript'); } catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}
const SRC = path.join(__dirname, '..', 'src');
const read = (r) => fs.readFileSync(path.join(SRC, r), 'utf8');
const stripComments = (t) => t.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
function compile(source, context = {}) {
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS,
  } }).outputText, { module, exports: module.exports, Set, Map, Math, Number, Array, ...context });
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

const P = compile(read('utils/tradePages.ts'));
let lastReq = null;
let nextRes = null;
const api = compile(read('api/trades.ts'), {
  require: (name) => {
    if (name !== './client') throw new Error(`api/trades.ts must stay require-free beyond ./client (saw ${name})`);
    return { api: {
      post: async (route, body) => { lastReq = { route, body }; return nextRes; },
      get: async (route) => { lastReq = { route }; return nextRes; },
    } };
  },
});
const card = (id, hash, extra = {}) => ({ trade_id: id, ...(hash ? { trade_hash: hash } : {}), ...extra });
const ids = (cs) => cs.map((c) => c.trade_id);

const trades = read('screens/TradesScreen.tsx');
const code = stripComments(trades);

(async () => {
  console.log('check-trade-pages:');

  // ── 1. The API opts in, and a legacy response stays legacy ──────────────
  await check('1a. generateTrades with { searchId } sends page: 1 + search_id', async () => {
    nextRes = { job_id: 'j', status: 'complete', cards: [], cursor: 0, total_ready: 0 };
    await api.generateTrades({ league_id: 'L' }, { searchId: 's-1' });
    eq(lastReq.route, '/api/trades/generate');
    eq([lastReq.body.page, lastReq.body.search_id], [1, 's-1'], 'paged generate body');
  });
  await check('1b. generateTrades without paging sends the body untouched (presentation deck, old callers)', async () => {
    nextRes = { job_id: 'j', status: 'complete', cards: [] };
    await api.generateTrades({ league_id: 'L' });
    eq(lastReq.body, { league_id: 'L' }, 'unpaged body');
  });
  await check('1c. getTradeStatus with { deck, cursor } sends job_id, deck and cursor', async () => {
    nextRes = { job_id: 'j', status: 'running', cards: [], cursor: 30, total_ready: 30 };
    await api.getTradeStatus('job 1', { deck: 'deck-9', cursor: 30 });
    eq(lastReq.route, '/api/trades/status?job_id=job%201&deck=deck-9&cursor=30');
    await api.getTradeStatus('j', { cursor: 7 });
    eq(lastReq.route, '/api/trades/status?job_id=j&deck=j&cursor=7', 'deck defaults to the job id (E2/P1 page by job)');
    await api.getTradeStatus('j');
    eq(lastReq.route, '/api/trades/status?job_id=j', 'legacy poll has no cursor');
  });
  await check('1d. a LEGACY response (no cursor) normalizes with no paging fields and no from_page', async () => {
    nextRes = { job_id: 'j', status: 'running', opponents_done: 1, opponents_total: 4,
      cards: [{ trade_id: 'a', give: [], receive: [] }] };
    const snap = await api.getTradeStatus('j');
    eq(Object.keys(snap).sort(), ['cards', 'error', 'job_id', 'opponents_done', 'opponents_total', 'status']);
    ok(!('from_page' in snap.cards[0]) && !('trade_hash' in snap.cards[0]), 'legacy card untouched');
  });
  await check('1e. a PAGED response types every envelope field and stamps its cards from_page; trade_hash kept', async () => {
    nextRes = { job_id: 'j', status: 'complete', cursor: 30, total_ready: 90, replace: false,
      deck_id: 'd', rebased: true, pool_exhausted: false, serve_source: 'page', freshness_state: 'updating',
      prefetch_remaining: 50, search_id: 's', cards: [{ trade_id: 'a', trade_hash: 'h1', give: [], receive: [] }] };
    const snap = await api.getTradeStatus('j', { deck: 'd', cursor: 0 });
    eq([snap.cursor, snap.total_ready, snap.deck_id, snap.rebased, snap.pool_exhausted, snap.serve_source,
      snap.freshness_state, snap.prefetch_remaining, snap.search_id],
      [30, 90, 'd', true, false, 'page', 'updating', 50, 's']);
    eq([snap.cards[0].trade_hash, snap.cards[0].from_page], ['h1', true]);
    nextRes = { ...nextRes, freshness_state: 'stale?', cursor: -1, prefetch_remaining: '50' };
    const bad = await api.getTradeStatus('j');
    ok(bad.freshness_state === undefined && bad.cursor === undefined && bad.prefetch_remaining === undefined,
      'malformed envelope values are dropped, never coerced');
  });
  await check('1f. an old server that does not echo search_id still hands the client id back', async () => {
    nextRes = { job_id: 'j', status: 'complete', cards: [], cursor: 0, total_ready: 0 };
    const snap = await api.generateTrades({ league_id: 'L' }, { searchId: 's-2' });
    eq(snap.search_id, 's-2');
  });

  // ── 2. Appends: behind the front, deduped by trade_hash, never reordered ─
  await check('2a. an append page goes BEHIND everything held, in server order', () => {
    const held = [card('a', 'ha'), card('b', 'hb'), card('c', 'hc')];
    const r = P.mergeDeckPage(held, [card('d', 'hd'), card('e', 'he')], 'hb', false);
    eq(ids(r.cards), ['a', 'b', 'c', 'd', 'e']);
    eq(r.added, 2);
    ok(r.cards[0] === held[0] && r.cards[1] === held[1] && r.cards[2] === held[2], 'held cards are the same objects, same slots');
  });
  await check('2b. dedupe by trade_hash: the same trade under a new per-build trade_id is dropped', () => {
    const held = [card('a', 'ha'), card('b', 'hb')];
    const r = P.mergeDeckPage(held, [card('x', 'hb'), card('y', 'hy'), card('y2', 'hy')], 'ha', false);
    eq(ids(r.cards), ['a', 'b', 'y']);
  });
  await check('2c. no trade_hash ⇒ dedupe falls back to trade_id (today\'s key)', () => {
    const r = P.mergeDeckPage([card('a'), card('b')], [card('b'), card('c')], 'a', false);
    eq(ids(r.cards), ['a', 'b', 'c']);
    eq(P.deckCardKey(card('z')), 'z');
    eq(P.deckCardKey(card('z', 'hz')), 'hz');
  });
  await check('2d. a rebased page that does NOT span the new deck only appends (no card judged absent)', () => {
    const held = [card('a', 'ha'), card('b', 'hb'), card('c', 'hc')];
    const env = { status: 'complete', rebased: true, cursor: 30, total_ready: 80 };
    ok(!P.isWholeDeck(env), 'a first page of a longer deck is not the whole deck');
    const r = P.mergeDeckPage(held, [card('n', 'hn'), card('b2', 'hb')], 'ha', P.isWholeDeck(env));
    eq(ids(r.cards), ['a', 'b', 'c', 'n']);
    eq(r.withdrawFront, false);
  });

  // ── 3. Ruling 16: replace never yanks the visible card ─────────────────
  await check('3a. replace keeps the seen cards and the fronted card in place; only what is behind is replaced', () => {
    const held = [card('s1', 'h1'), card('s2', 'h2'), card('f', 'hf'), card('b1', 'hb1'), card('b2', 'hb2')];
    ok(P.isWholeDeck({ status: 'running', replace: true }), 'replace is a whole-deck response');
    // Server's full current list, in a NEW order, still serving the front.
    const full = [card('b2x', 'hb2'), card('f2', 'hf'), card('n1', 'hn1'), card('s1x', 'h1')];
    const r = P.mergeDeckPage(held, full, 'hf', true);
    eq(ids(r.cards), ['s1', 's2', 'f', 'b2x', 'n1'], 'head untouched; behind = server order, deduped vs head');
    ok(r.cards[2] === held[2], 'the fronted card is the same object in the same slot');
    eq(r.withdrawFront, false);
  });
  await check('3b. replace drops behind-cards the server no longer serves, silently', () => {
    const held = [card('f', 'hf'), card('gone', 'hg'), card('kept', 'hk')];
    const r = P.mergeDeckPage(held, [card('kept2', 'hk'), card('f', 'hf')], 'hf', true);
    eq(ids(r.cards), ['f', 'kept2']);
  });
  await check('3c. replace with nothing fronted (past the last card) can only append', () => {
    const held = [card('a', 'ha'), card('b', 'hb')];
    const r = P.mergeDeckPage(held, [card('c', 'hc'), card('a', 'ha')], null, true);
    eq(ids(r.cards), ['a', 'b', 'c']);
    eq(r.withdrawFront, false);
  });
  await check('3d. a rebased page spanning the new, complete deck counts as whole', () => {
    ok(P.isWholeDeck({ status: 'complete', rebased: true, cursor: 12, total_ready: 12 }), 'spanning');
    ok(!P.isWholeDeck({ status: 'running', rebased: true, cursor: 12, total_ready: 12 }), 'still building');
    ok(!P.isWholeDeck({ status: 'complete', cursor: 12, total_ready: 12 }), 'a plain last page is not');
  });

  // ── 4. Prefetch reads the server's threshold (ruling 10) ────────────────
  await check('4a. next page while FEWER than prefetch_remaining unseen cards are held', () => {
    const env = { status: 'complete', cursor: 30, total_ready: 90, busy: false };
    eq(P.wantsNextPage({ ...env, unseen: 49, prefetch_remaining: 50 }), true);
    eq(P.wantsNextPage({ ...env, unseen: 50, prefetch_remaining: 50 }), false);
    eq(P.wantsNextPage({ ...env, unseen: 10, prefetch_remaining: 8 }), false, 'the server value wins over the fallback');
    eq(P.wantsNextPage({ ...env, unseen: 49 }), true, 'fallback 50 when the server sends none');
    eq(P.wantsNextPage({ ...env, unseen: 50 }), false);
    eq(P.PREFETCH_REMAINING_FALLBACK, 50);
  });
  await check('4b. at most one request in flight or scheduled; never for a finished or legacy deck', () => {
    const env = { status: 'complete', cursor: 30, total_ready: 90, unseen: 0 };
    eq(P.wantsNextPage({ ...env, busy: true }), false);
    eq(P.wantsNextPage({ ...env, cursor: undefined, busy: false }), false, 'legacy (no cursor)');
    eq(P.wantsNextPage({ ...env, pool_exhausted: true, busy: false }), false);
    eq(P.wantsNextPage({ ...env, status: 'error', busy: false }), false);
    eq(P.wantsNextPage({ ...env, cursor: 90, busy: false }), false, 'no deck_id (flag off): complete and fully paged');
    eq(P.wantsNextPage({ ...env, cursor: 90, pool_exhausted: false, busy: false }), false,
      'no deck_id: the job\'s own end ends the deck, whatever pool_exhausted says');
    eq(P.wantsNextPage({ ...env, deck_id: 'd', cursor: 90, pool_exhausted: false, busy: false }), true,
      'deck_id (P2): only pool_exhausted ends the deck ⇒ keep asking');
    eq(P.wantsNextPage({ ...env, deck_id: 'd', cursor: 90, pool_exhausted: true, busy: false }), false);
  });
  await check('4c. empty-while-building backs off; a rebased short page does not', () => {
    eq(P.needsBackoff({ status: 'running', cursor: 12, total_ready: 12 }, 12), true);
    eq(P.needsBackoff({ status: 'complete', deck_id: 'd', cursor: 90, total_ready: 90, pool_exhausted: false }, 60), true);
    eq(P.needsBackoff({ status: 'complete', cursor: 60, total_ready: 90 }, 30), false);
    eq(P.needsBackoff({ status: 'complete', rebased: true, cursor: 30, total_ready: 90 }, 60), false);
    eq(P.needsBackoff({ status: 'complete', cursor: 90, total_ready: 90, pool_exhausted: true }, 60), false);
    eq([0, 1, 2, 3, 9].map(P.pageRetryDelayMs), [500, 1000, 2000, 4000, 4000]);
  });

  // ── 5. The screen wires all of the above ───────────────────────────────
  await check('5a. every dispatch is a paged search with its own client search id', () => {
    ok(/return generateTrades\(request, vars\.searchId \? \{ searchId: vars\.searchId \} : undefined\);/.test(code),
      'mutationFn passes the dispatch search id');
    ok(/const claimed = claimPendingSearch\(\);[\s\S]{0,200}?generateMutation\.mutate\(\{ \.\.\.vars, searchId: claimed \?\? uuidv4\(\) \}, mutateOpts\);/.test(code),
      'dispatchGenerate carries the tap\'s search id (R1), else mints one');
  });
  await check('5b. pages are fetched by deck + cursor, merged through mergeDeckPage at the fronted card', () => {
    ok(/getTradeStatus\(snap\.job_id, \{ deck: snap\.deck_id, cursor: requested \}\)/.test(code), 'status call');
    const fn = code.slice(code.indexOf('function applyPage('), code.indexOf('async function fetchNextPage('));
    ok(/mergeDeckPage\(\s*deckRef\.current,\s*next\.cards,\s*front \? deckCardKey\(front\) : null,\s*isWholeDeck\(next\),?\s*\)/.test(fn),
      'applyPage merges at the fronted card with the whole-deck rule');
    ok(/setDeck\(merged\.cards\)/.test(fn) && /cards: merged\.cards/.test(fn), 'deck and job.cards stay one list');
    ok(/applyJobResult\(next, epoch, deckEpochRef\.current\) === null/.test(code), 'epoch guard on every page');
  });
  await check('5c. the prefetch threshold comes from the response, not a client literal', () => {
    const eff = code.slice(code.indexOf('if (!wantsNextPage({'), code.indexOf('void fetchNextPage();'));
    ok(/\.\.\.snap,/.test(eff), 'the job envelope (prefetch_remaining included) is handed to wantsNextPage');
    ok(!/prefetch_remaining:\s*\d/.test(eff) && !/unseen\s*<\s*\d/.test(code), 'no hard-coded threshold in the screen');
    ok(/job\?\.prefetch_remaining/.test(code), 'a changed server threshold re-evaluates');
  });
  await check('5d. the legacy poller stands aside for paged jobs; the append effect dedupes by deckCardKey', () => {
    ok(/if \(!job \|\| job\.status !== 'running' \|\| !job\.job_id\) return;\s*if \(isPagedEnvelope\(job\)\) return;/.test(code),
      'poller');
    ok(/const seen = new Set\(prev\.map\(deckCardKey\)\);\s*const fresh = job\.cards\.filter\(\(c\) => !seen\.has\(deckCardKey\(c\)\)\);/.test(code),
      'append effect');
  });
  await check('5e. EXECUTED: the orderedDeck memo keeps a paged deck in server order with fairness OFF', () => {
    const sf = ts.createSourceFile('T.tsx', trades, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    let body;
    (function visit(n) {
      if (ts.isVariableDeclaration(n) && n.name.getText(sf) === 'orderedDeck') {
        body = n.initializer.arguments[0].body.getText(sf).slice(1, -1);
      }
      ts.forEachChild(n, visit);
    })(sf);
    ok(body, 'orderedDeck memo found');
    const run = new Function('deck', 'fairnessOn', 'laneFilter', 'canvasResultsOn', 'browseSession', body);
    const paged = [{ id: 'p1', match_score: 1, from_page: true }, { id: 'p2', match_score: 99, from_page: true },
      { id: 'liked', match_score: 0, likesYou: true, from_page: true }];
    ok(run(paged, false, null, false, null) === paged, 'paged deck returned as-is (no re-sort, no likes-you lift)');
    const legacy = [{ id: 'a', match_score: 1 }, { id: 'b', match_score: 2 }];
    eq(run(legacy, false, null, false, null).map((c) => c.id), ['b', 'a'], 'legacy fairness-off re-sort unchanged');
  });

  console.log(failures ? `check-trade-pages: ${failures} FAILED` : 'check-trade-pages: all passed');
  process.exit(failures ? 1 : 0);
})();
