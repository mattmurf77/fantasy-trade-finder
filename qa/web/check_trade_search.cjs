'use strict';
// Exercise the same search functions the browser invokes with controlled
// requests, a monotonic clock and explicit viewport notifications.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('web/js/app.js', 'utf8');
let completed = false;
process.on('exit', () => { if (!completed) { console.error('Web search suite did not finish'); process.exitCode = 1; } });
const section = source.slice(source.indexOf('    let webTradeSearch ='), source.indexOf('    // FB-47 — partner-fit copy.'));
function harness(replies) {
  const events = [], requests = [], rendered = [], observers = [], timers = new Map();
  let clock = 0, nextTimer = 0;
  const list = { replaceChildren() {} };
  const el = new Map([['trades-list', list], ['gen-btn', {}], ['trade-more-btn', {}]]);
  const card = { isConnected: true, querySelector: () => true };
  const context = {
    currentUserId: 'test', currentLeagueId: 'A', sessionToken: 'test',
    webTradeChange: undefined, currentOutlook: null, currentAcquirePositions: [], currentTradeAwayPositions: [],
    _pinnedGivePlayers: new Set(), _pinnedReceivePlayers: new Set(), _allTradeCards: [], _lastRenderedTrades: [],
    getActiveFormat: () => '1qb_ppr', _targetingOn: () => false, getFairnessThreshold: () => 0.75,
    document: { getElementById: key => el.get(key), querySelectorAll: () => [card], addEventListener() {} },
    window: { FTFTrack: (...args) => events.push(args), addEventListener() {}, IntersectionObserver: true },
    navigator: { onLine: true }, performance: { now: () => clock },
    IntersectionObserver: class { constructor(fn) { observers.push(fn); } observe() {} disconnect() {} },
    setTimeout(fn, ms) { const id = ++nextTimer; timers.set(id, fn); if (ms < 10000) queueMicrotask(fn); return id; },
    clearTimeout(id) { timers.delete(id); }, updateLikedBadge() {}, showToast() {},
    renderTrades(cards) { context._allTradeCards = cards; rendered.push(cards.map(c => c.trade_id)); },
    async apiFetch(url, opts) {
      requests.push([url, opts]); assert.equal(opts.headers['X-FTF-Current-Only'], '1');
      const next = await replies.shift();
      return { ok: !next.error, status: next.error ? 409 : 200, json: async () => next };
    },
  };
  vm.createContext(context); vm.runInContext(section, context);
  return { context, requests, rendered, events, el,
    visible(ratio) { clock = 137; observers.at(-1)([{ intersectionRatio: ratio, target: card }]); } };
}
function page(ids, cursor, total, extra = {}) {
  return { job_id: 'job', status: 'complete', current_validated: true, cards: ids.map(trade_id => ({ trade_id })), cursor,
    total_ready: total, ...extra };
}
(async () => {
  let h = harness([page(['A'],1,2), page(['B'],2,2)]);
  await h.context.generateTrades();
  assert.deepEqual(h.rendered, [['A']]);
  assert.equal(h.events.length, 1);
  h.visible(0.49); assert.equal(h.events.length, 1);
  h.visible(0.5); h.visible(1); assert.equal(h.events.length, 2);
  assert.equal(h.events[1][1].ms_from_tap, 137);
  assert.equal(h.events[0][1].search_id, h.events[1][1].search_id);
  await h.context.loadMoreWebTrades();
  assert.deepEqual(h.rendered.at(-1), ['A','B']); assert.equal(h.el.get('trade-more-btn').hidden, true);
  h = harness([page(['wrong'],0,1,{status:'running'}), { error:'trade_snapshot_changed' }, page(['right'],1,1)]);
  await h.context.generateTrades(); assert.deepEqual(h.rendered,[['right']]); assert.equal(h.requests.length,3);
  h = harness([page([],1,2),page(['visible'],2,2)]);
  await h.context.generateTrades(false); assert.deepEqual(h.rendered.at(-1),['visible']); assert.equal(h.events.length,0);
  h = harness([page(['old'],1,2),page(['new'],1,1,{replace:true})]);
  await h.context.generateTrades(); await h.context.loadMoreWebTrades(); assert.deepEqual(h.rendered.at(-1), ['new']);
  h = harness([page(['unconfirmed'],1,1,{current_validated:false})]); await h.context.generateTrades();
  assert.equal(h.rendered.length,0); assert.equal(h.events.at(-1)[1].reason,'error');
  h = harness([page(['first'],1,1,{status:'running',ranked_prefix_ready:true}),page(['second'],2,2)]);
  await h.context.generateTrades(); assert.deepEqual(h.rendered.at(-1),['first']);
  assert.equal(h.requests.length,1); assert.equal(h.el.get('trade-more-btn').hidden,false);
  await h.context.loadMoreWebTrades(); assert.deepEqual(h.rendered.at(-1),['first','second']);
  h = harness([page(['old'],1,2),{error:'trade_snapshot_changed'}]);
  await h.context.generateTrades(); await h.context.loadMoreWebTrades();
  assert.equal(h.rendered.at(-1).length,0); assert.equal(h.el.get('trade-more-btn').hidden,true);
  let fulfill; h = harness([new Promise(resolve => { fulfill = resolve; })]);
  const waiting = h.context.generateTrades();
  h.context.currentLeagueId = 'B'; fulfill(page(['wrong league'],1,1)); await waiting;
  assert.equal(h.rendered.length,0);
  h = harness([page(['old'],1,2)]);
  await h.context.generateTrades();
  h.context.withdrawWebTradeResults();
  assert.equal(h.rendered.at(-1).length, 0);
  assert.equal(h.el.get('trade-more-btn').hidden, true);
  assert.equal(h.events.at(-1)[1].reason, 'abandoned');
  // An in-flight response cannot restore cards after an input write withdraws them.
  h = harness([new Promise(resolve => { fulfill = resolve; })]);
  const edited = h.context.generateTrades();
  h.context.withdrawWebTradeResults();
  fulfill(page(['obsolete'],1,1)); await edited;
  assert.equal(h.rendered.length, 1); assert.equal(h.rendered[0].length, 0);
  // A continuation from the old deck must not block a new empty first page.
  let oldMore;
  h = harness([page(['old'],1,2), new Promise(resolve => { oldMore = resolve; }),
    page([],1,2), page(['fresh'],2,2)]);
  await h.context.generateTrades();
  const obsoleteMore = h.context.loadMoreWebTrades();
  h.context.withdrawWebTradeResults();
  await h.context.generateTrades();
  assert.equal(h.requests.length, 4);
  assert.equal(h.rendered.at(-1)[0], 'fresh');
  oldMore(page(['obsolete-more'],2,2)); await obsoleteMore;
  assert.equal(h.rendered.at(-1)[0], 'fresh');

  // Exercise the real fetch wrapper with two overlapping input mutations.
  h = harness([]);
  const apiStart = source.indexOf('    async function apiFetch(');
  const apiEnd = source.indexOf('      return res;\n    }', apiStart) + '      return res;\n    }'.length;
  const writeResolvers = []; let searchRequests = 0;
  const response = body => ({ ok:true, status:200, json:async () => body });
  h.context.markWebTradeChange = () => {};
  h.context.fetch = url => {
    if (url === '/api/league/preferences') return new Promise(resolve => writeResolvers.push(resolve));
    searchRequests++; return Promise.resolve(response(page(['committed-inputs'],1,1)));
  };
  vm.runInContext(source.slice(apiStart, apiEnd), h.context);
  const write1 = h.context.apiFetch('/api/league/preferences', {method:'POST',body:'{}'});
  const write2 = h.context.apiFetch('/api/league/preferences', {method:'POST',body:'{}'});
  const duringWrites = h.context.generateTrades();
  await Promise.resolve(); assert.equal(searchRequests, 0);
  const originalId = h.events.at(-1)[1].search_id;
  writeResolvers[0](response({})); await write1;
  await Promise.resolve(); assert.equal(searchRequests, 0);
  // Automatic refresh cannot replace the tap's clock while its save settles.
  await h.context.generateTrades(false);
  writeResolvers[1](response({})); await write2;
  await duringWrites;
  assert.equal(searchRequests, 1);
  assert.equal(h.rendered.at(-1)[0], 'committed-inputs');
  assert.equal(h.events.filter(e => e[0] === 'find_trades_tapped').length, 1);
  // A delayed preference body/UI update cannot replace that explicit tap.
  h.context.currentOutlook = 'contender'; h.context.currentAcquirePositions = ['WR'];
  await h.context.generateTrades(false); assert.equal(searchRequests, 1);
  h.visible(0.5); assert.equal(h.events.at(-1)[1].search_id, originalId);
  completed = true;
  console.log('Web search scenarios passed');
})().catch(error => { console.error(error); process.exitCode=1; });
