#!/usr/bin/env node
// Executes one-tap request transfer and strict API adapters. No device timing claim.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const ts = require('typescript');
const SRC = path.join(__dirname, '../src');
const read = f => fs.readFileSync(path.join(SRC, f), 'utf8');
function compile(source, context = {}) {
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
  } }).outputText, { module, exports: module.exports, ...context });
  return module.exports;
}
const json = v => JSON.parse(JSON.stringify(v));
const rules = compile(read('utils/tradePages.ts'));
const device = compile(read('utils/devicePage.ts'), { require: () => rules });
const selection = compile(read('utils/tradeSearchRequest.ts'));
let now = 1000, revision = 1;
let state = { hasToken: true, switching: false, user: { user_id: 'A' }, league: { league_id: 'L' }, activeFormat: 'sf' };
const handoff = compile(read('state/tradeSearchHandoff.ts'), {
  Date: { now: () => now }, require: n => {
    if (n === '../api/client') return { getSessionRevision: () => revision };
    if (n === './useSession') return { useSession: { getState: () => state } };
    throw Error(n);
  },
});
const request = { league_id: 'L', fairness_threshold: 0.5, pinned_give_players: ['p1'],
  pinned_receive_players: ['p2'], pinned_give_mode: 'all', opponent_user_id: 'B', trade_intent: 'tier_up' };
let passed = 0;
const ok = (name, fn) => Promise.resolve().then(fn).then(() => { passed++; console.log('PASS ' + name); });
function reset() { handoff.invalidateTradeSearchHandoffs(); now = 1000; revision = 1;
  state = { hasToken: true, switching: false, user: { user_id: 'A' }, league: { league_id: 'L' }, activeFormat: 'sf' }; }
const page = (over = {}) => ({ job_id: 'j', status: 'complete', cursor: 1, deck_id: 'd', freshness_state: 'fresh',
  current_validated: true, cards: [{ trade_id: 't', league_id: 'L', give: [], receive: [] }], ...over });

(async () => {
  await ok('one tap starts once, takes once, preserves already-resolved answer', async () => {
    reset(); let calls = 0;
    handoff.startTradeSearchHandoff('s', 'model', request, async () => { calls++; return page(); });
    assert.equal(handoff.startTradeSearchHandoff('s', 'model', request, async () => { calls++; }), true);
    assert.equal(calls, 1);
    assert.equal((await handoff.takeTradeSearchHandoff('s', 'model', { ...request })).job_id, 'j');
    assert.equal(handoff.takeTradeSearchHandoff('s', 'model', request), null);
    assert.equal(handoff.takeTradeSearchHandoff('another-tap', 'model', request), null);
  });
  for (const [key, value] of Object.entries({ league_id: 'other', fairness_threshold: 0.75,
    pinned_give_players: ['other'], pinned_receive_players: [], pinned_give_mode: 'any',
    opponent_user_id: 'C', trade_intent: 'consolidate', force: true })) {
    await ok('request mismatch rejected: ' + key, () => {
      reset(); handoff.startTradeSearchHandoff('s', 'model', request, async () => page());
      assert.equal(handoff.takeTradeSearchHandoff('s', 'model', { ...request, [key]: value }), null);
    });
  }
  for (const change of [() => { state.user = { user_id: 'other' }; }, () => { state.league = { league_id: 'other' }; },
    () => { state.activeFormat = '1qb'; }, () => { revision++; }, () => { state.switching = true; },
    () => { state.hasToken = false; }, () => handoff.invalidateTradeSearchHandoffs(),
    () => { now += 10001; }, () => { now--; }]) {
    await ok('replaced/expired input context is never reused', () => {
      reset(); handoff.startTradeSearchHandoff('s', 'model', request, async () => page()); change();
      assert.equal(handoff.takeTradeSearchHandoff('s', 'model', request), null);
    });
  }
  await ok('a taken pending response is rejected after a later identity change', async () => {
    reset(); let resolve;
    handoff.startTradeSearchHandoff('s', 'model', request, () => new Promise(r => { resolve = r; }));
    const pending = handoff.takeTradeSearchHandoff('s', 'model', request);
    state.activeFormat = '1qb'; resolve(page());
    await assert.rejects(pending, /trade_search_context_changed/);
  });
  await ok('fair sweep and model cannot exchange responses; fair request includes its complete selection', async () => {
    reset(); const fair = selection.fairPackagesRequest('L', { giveIds: ['g'], receiveIds: ['r'] }, 0.75, 'B');
    assert.deepEqual(json(fair), { league_id: 'L', fairness_threshold: 0.75, give_player_ids: ['g'], receive_player_ids: ['r'], opponent_user_id: 'B' });
    handoff.startTradeSearchHandoff('s', 'fair', fair, async () => ({ ideas: [] }));
    assert.equal(handoff.takeTradeSearchHandoff('s', 'model', fair), null);
  });

  const file = ts.createSourceFile('T.tsx', read('screens/TradesScreen.tsx'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let pushSource;
  (function visit(n) { if (ts.isFunctionDeclaration(n) && n.name?.text === 'pushWithFirstPage') pushSource = n.getText(file);
    ts.forEachChild(n, visit); })(file);
  assert(pushSource);
  for (const kind of ['model', 'fair']) await ok('actual ' + kind + ' tap starts once and pushes immediately before response', async () => {
    reset(); const calls = [], pushes = []; let resolve;
    const load = body => { calls.push(body); return new Promise(r => { resolve = r; }); };
    const context = { switching: false, leagueId: 'L', fairnessReady: true, effectiveFairness: 0.5,
      sheetTargetingOn: true, targetingEnabled: true, tradeIntent: undefined, deviceKey: null,
      payEnforcing: false, payEntitled: false, resultsPushPendingRef: { current: false },
      dropPendingSearch: () => {}, readOnline: () => true, readDevicePage: () => null,
      devicePageScope: device.devicePageScope, devicePageUsable: device.devicePageUsable,
      devicePageSnapshot: device.devicePageSnapshot, modelSelectionParams: selection.modelSelectionParams,
      fairPackagesRequest: selection.fairPackagesRequest, useFinderTargets: { getState: () => ({ packageMode: true }) },
      generateTrades: load, getFairPackages: load, ...handoff };
    const run = compile('module.exports = env => { const {' + Object.keys(context).join(',') + '} = env; return ' + pushSource + '; };')(context);
    const fork = { giveIds: kind === 'fair' ? ['g'] : [], receiveIds: ['r'], opponent: { userId: 'B' }, anchor: kind === 'fair' ? {} : null, searchId: 's' };
    run(fork, p => pushes.push(p));
    assert.equal(pushes.length, 1); assert.equal(calls.length, 1);
    const pending = handoff.takeTradeSearchHandoff('s', kind, calls[0]); assert(pending);
    resolve(kind === 'model' ? page() : { ideas: [] }); await pending;
  });

  await ok('strict adapters preserve preview header and reject a non-acknowledging older server', async () => {
    let response = page(); const calls = [];
    const api = compile(read('api/trades.ts'), { require: () => ({ api: {
      post: async (url, body, opts) => { calls.push(opts); return response; },
      get: async (url, opts) => { calls.push(opts); return response; },
    } }) });
    await api.generateTrades({ league_id: 'L' }, {}, { background: true, headers: { 'X-FTF-Prewarm': '1' } });
    await api.getTradeStatus('j');
    assert.equal(calls[0].headers['X-FTF-Current-Only'], '1'); assert.equal(calls[0].headers['X-FTF-Prewarm'], '1');
    assert.equal(calls[1].background, undefined); assert.equal(calls[1].headers['X-FTF-Current-Only'], '1');
    response = page({ current_validated: undefined });
    for (const load of [() => api.generateTrades({ league_id: 'L' }), () => api.getTradeStatus('j')]) {
      await assert.rejects(load(), e => e.code === 'trade_snapshot_unvalidated');
    }
  });
  await ok('strict 409 status revokes the whole prior snapshot and uses one-shot inputs_changed recovery', async () => {
    const api = compile(read('api/trades.ts'), { require: () => ({ api: { get: async () => { throw { status: 409, body: { error: 'trade_snapshot_changed' } }; } } }) });
    const snapshot = await api.getTradeStatus('j', { deck: 'd', cursor: 3 });
    assert.equal(snapshot.status, 'error'); assert.equal(snapshot.error, 'inputs_changed');
    assert.equal(snapshot.cards.length, 0); assert.equal(snapshot.replace, true);
    assert.equal(snapshot.current_invalidated, true);
    assert.equal(rules.autoResearchOnJobError('idle', snapshot.error), 'pending');
    assert.equal(rules.autoResearchOnJobError('used', snapshot.error), 'fail');
    assert.equal(device.devicePageFrom(snapshot, { scope: 'organic:f=0.50', validatedAt: now }), null);
    let applySource;
    (function visit(n) { if (ts.isFunctionDeclaration(n) && n.name?.text === 'applyPage') applySource = n.getText(file);
      ts.forEachChild(n, visit); })(file);
    const kept = { current: ['obsolete'] }; let deck, job; const discarded = [];
    const env = { deckRef: kept, lastDispositionedRef: { current: 'old' }, setDeck: v => { deck = v; }, setDeckIdx: () => {},
      setJob: v => { job = v; }, deviceKey: 'cache-key', discardDevicePage: k => discarded.push(k) };
    const apply = compile('module.exports = env => { const {' + Object.keys(env).join(',') + '} = env; return ' + applySource + '; };')(env);
    assert.equal(apply(snapshot), 0); assert.equal(kept.current.length, 0);
    assert.equal(deck.length, 0); assert.equal(job.status, 'error'); assert.deepEqual(discarded, ['cache-key']);
  });
  await ok('v1 and unproved pages cannot become usable v2 pages; targeted scopes stay off disk', () => {
    const p = device.devicePageFrom(page(), { scope: 'organic:f=0.50', validatedAt: now }); assert(p);
    assert.equal(p.v, 2); assert.equal(device.devicePageUsable(p, p.scope, now), true);
    assert.equal(device.parseDevicePage(JSON.stringify({ ...p, v: 1 })), null);
    assert.equal(device.devicePageFrom(page({ current_validated: undefined }), { scope: p.scope, validatedAt: now }), null);
    assert.equal(device.devicePageScope(request), null);
  });
  await ok('running cards require a ranked prefix proof and an unproved prefix never advances cursor', async () => {
    let response = page({ status: 'running', cursor: 30 });
    const api = compile(read('api/trades.ts'), { require: () => ({ api: { get: async () => response } }) });
    const hidden = await api.getTradeStatus('j', { deck: 'd', cursor: 0 });
    assert.equal(hidden.cards.length, 0); assert.equal(hidden.cursor, 0); assert.equal(hidden.status, 'running');
    response = page({ status: 'running', ranked_prefix_ready: true, cursor: 30 });
    const ready = await api.getTradeStatus('j', { deck: 'd', cursor: 0 });
    assert.equal(ready.cards.length, 1); assert.equal(ready.cursor, 30);
  });
  console.log(`${passed} instant trade handoff checks passed.`);
})().catch(e => { console.error(e); process.exitCode = 1; });
