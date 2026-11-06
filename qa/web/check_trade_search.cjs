'use strict';
// Exercise the same search functions the browser invokes with controlled
// requests, a monotonic clock and explicit viewport notifications.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('web/js/app.js', 'utf8');
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
  console.log('Web search scenarios passed');
})().catch(error => { console.error(error); process.exitCode=1; });
