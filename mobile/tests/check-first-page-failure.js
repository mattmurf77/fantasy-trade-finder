#!/usr/bin/env node
// Execute the real page loop, render branch and explicit retry handlers.
// Synthetic timers/network only; this is not a device or latency measurement.
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert');
const ts = require('typescript');
const source = fs.readFileSync(path.join(__dirname, '../src/screens/TradesScreen.tsx'), 'utf8');
const ast = ts.createSourceFile('screen.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const nodes = [];
(function walk(n) { nodes.push(n); ts.forEachChild(n, walk); })(ast);
const fn = name => nodes.find(n => ts.isFunctionDeclaration(n) && n.name?.text === name).getText(ast);
const compile = (s, context = {}) => {
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(s, { compilerOptions: { target: ts.ScriptTarget.ES2020,
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React } }).outputText,
  { module, exports: module.exports, ...context });
  return module.exports;
};
const rules = compile(fs.readFileSync(path.join(__dirname, '../src/utils/tradePages.ts'), 'utf8'));
const bind = (name, context) => compile(`module.exports=function(context){with(context){${fn(name)};return ${name};}}`)(context);
const branch = nodes.find(n => ts.isConditionalExpression(n) && n.condition.getText(ast) === 'pagedWithCards && deckEnd').getText(ast);
const render = compile(`module.exports=function(context){with(context){return (${branch});}}`, {
  React: { createElement: (type, props, ...children) => ({ type, props, children }) },
  Card: 'Card', View: 'View', ActivityIndicator: 'ActivityIndicator', Text: 'Text', Button: 'Button',
  SkeletonTradeCard: 'SkeletonTradeCard', DeckMoreErrorCard: 'DeckMoreErrorCard',
});
const find = (tree, id) => tree && typeof tree === 'object'
  ? tree.props?.testID === id ? tree : (tree.children || []).flat(Infinity).map(x => find(x, id)).find(Boolean)
  : undefined;
const limit = Number(source.match(/const MAX_SILENT_PAGE_FAILURES = (\d+)/)[1]);
let passed = 0;
async function check(name, run) { await run(); passed++; console.log('PASS ' + name); }
function world({ held = false, failures = limit, emptyResponses = 0, afterRequest, gated = false } = {}) {
  let calls = 0, phase = 'idle', failure = null, kicks = 0;
  const cards = held ? [{ trade_id: 'held' }] : [];
  const job = { job_id: 'j', status: 'running', cursor: cards.length, total_ready: cards.length, cards };
  const loop = { inFlight: false, timer: null, attempt: 0, failures: 0 };
  const timers = [];
  const ctx = { ...rules, jobRef: { current: job }, deckRef: { current: cards }, deckGateEndRef: { current: null },
    pageLoopRef: { current: loop }, deckEpochRef: { current: 1 }, mountedRef: { current: true },
    MAX_SILENT_PAGE_FAILURES: limit, DECK_FAIL_NETWORK: 'Network issue. Try again.',
    setPagePhase: value => { phase = typeof value === 'function' ? value(phase) : value; },
    setPageKick: () => { kicks++; }, setJob: value => { ctx.jobRef.current = value; },
    setDeckFailure: value => { failure = value; },
    getTradeStatus: async () => {
      calls++;
      if (afterRequest) afterRequest(ctx);
      if (calls <= failures) throw Error('synthetic status failure');
      if (calls <= emptyResponses) return { ...job, cards: [], total_ready: 0, cursor: 0, pool_exhausted: false };
      return { ...job, status: 'complete', cursor: 1, total_ready: 1, pool_exhausted: true, cards: [{ trade_id: 'arrived' }] };
    },
    applyJobResult: (value, old, current) => old === current ? value : null,
    noteDeckGateEnd: () => gated,
    applyPage: next => { ctx.deckRef.current = next.cards; ctx.jobRef.current = next; return next.cards.length; },
    setTimeout: cb => { timers.push(cb); return timers.length; },
  };
  const fetch = bind('fetchNextPage', ctx);
  const drain = async () => { await fetch(); while (timers.length) { timers.shift()(); await fetch(); } };
  const view = (firstRun = false, handleFindTrades = () => {}) => render({
    pagedWithCards: ctx.deckRef.current.length > 0, deckEnd: held ? 'error' : null, online: true,
    deck: ctx.deckRef.current, deckFailure: failure, generateMutation: { isPending: false },
    rosterWait: false, firstRun, fairDeck: false, autoGenFailed: false, fairPending: false,
    job: ctx.jobRef.current, summaryVisible: false, scopedEmpty: null, topCardH: 400,
    styles: {}, ice: { base: 'blue' }, space: { sm: 1 }, handleFindTrades, handleDeckMoreRetry: () => {},
  });
  return { ctx, loop, timers, drain, fetch, view, state: () => ({ calls, phase, failure, kicks }) };
}
(async () => {
  for (const firstRun of [false, true]) await check('empty first-page failures show actionable error, firstRun=' + firstRun, async () => {
    const w = world(); await w.drain();
    assert.equal(w.state().calls, limit); assert.equal(w.timers.length, 0);
    assert.equal(w.ctx.jobRef.current, null); assert.equal(w.state().failure.kind, 'poll_abandoned');
    const view = w.view(firstRun);
    assert(find(view, 'trades.deck-error')); assert(find(view, 'trades.deck-error.retry'));
    assert(!JSON.stringify(view).includes('ActivityIndicator')); assert(!JSON.stringify(view).includes('SkeletonTradeCard'));
  });
  await check('last allowed status response can still deliver first card', async () => {
    const w = world({ failures: limit - 1 }); await w.drain();
    assert.equal(w.state().calls, limit); assert.equal(w.state().failure, null);
    assert.equal(w.ctx.deckRef.current[0].trade_id, 'arrived'); assert.equal(w.ctx.jobRef.current.status, 'complete');
  });
  await check('successful running-empty pages continue until a later published card arrives', async () => {
    const w = world({ failures: 0, emptyResponses: 12 }); await w.drain();
    assert.equal(w.state().calls, 13); assert.equal(w.state().failure, null);
    assert.equal(w.ctx.deckRef.current[0].trade_id, 'arrived'); assert.equal(w.ctx.jobRef.current.status, 'complete');
  });
  await check('early transient errors continue existing bounded polling', async () => {
    const w = world(); await w.fetch();
    assert.equal(w.ctx.jobRef.current.status, 'running'); assert.equal(w.state().failure, null);
    assert.equal(w.timers.length, 1);
  });
  await check('held-card paging retains job and existing more-error UI', async () => {
    const w = world({ held: true }); await w.drain();
    assert.equal(w.ctx.jobRef.current.status, 'running'); assert.equal(w.state().failure, null);
    assert.equal(w.ctx.deckRef.current[0].trade_id, 'held'); assert.equal(w.view().type, 'DeckMoreErrorCard');
  });
  for (const change of [c => { c.mountedRef.current = false; }, c => { c.deckEpochRef.current++; },
    c => { c.jobRef.current = { job_id: 'new' }; }, c => { c.pageLoopRef.current = {}; }]) {
    await check('obsolete failure cannot replace current view', async () => {
      const w = world({ afterRequest: change }); await w.drain();
      assert.equal(w.state().failure, null); assert.equal(w.timers.length, 0);
    });
  }
  await check('paywall/verification branch retains its existing handling', async () => {
    const w = world({ gated: true }); await w.drain();
    assert.equal(w.state().calls, 1); assert.equal(w.state().failure, null);
  });
  await check('rendered retry dispatches a fresh search with the existing exact request retained', async () => {
    const w = world(); await w.drain();
    const saved = { league_id: 'L', pinned_give_players: ['p'], opponent_user_id: 'O', trade_intent: 'tier_up' };
    const events = [], mutations = []; let pending = null;
    const context = { fairPendingRef: { current: false }, setDeckFailure: () => {}, setScopedEmpty: () => {},
      lastFairRequestRef: { current: null }, lastModelRequestRef: { current: saved },
      useFinderTargets: { getState: () => ({ pinnedGive: [], pinnedReceive: [] }) },
      beginTradeSearch: event => { events.push(event); pending = 'fresh-search'; },
      searchTypeOf: value => value, isDeepLinkDeck: false, deckMode: 'guided', tradeIntent: 'tier_up', scopedOpponent: 'O',
      prefsChangedSinceGenerateRef: {}, setShowPrefsChangedStrip: () => {}, setPinIdeaResumed: () => {},
      setFairDeck: () => {}, pendingScrollToDeckRef: {}, canvasResultsLive: false,
      handoffSearchRef: { current: null }, claimPendingSearch: () => { const p = pending; pending = null; return p; },
      claimSearch: () => {}, deckSearchRef: {}, generateMutation: { mutate: args => mutations.push(args) },
      uuidv4: () => { throw Error('must use the explicit retry tap id'); },
    };
    context.dispatchGenerate = bind('dispatchGenerate', context);
    const handle = bind('handleFindTrades', context);
    find(w.view(false, handle), 'trades.deck-error.retry').props.onPress();
    assert.equal(events.length, 1); assert.equal(events[0].source, 'deck_error_retry');
    assert.equal(mutations.length, 1); assert.equal(mutations[0].repeat, true);
    assert.equal(mutations[0].searchId, 'fresh-search'); assert.equal(context.lastModelRequestRef.current, saved);
  });
  console.log(`${passed} first-page failure checks passed`);
})().catch(error => { console.error(error); process.exit(1); });
