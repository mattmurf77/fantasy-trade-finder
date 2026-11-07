#!/usr/bin/env node
// Execute the shipped page fetcher with controlled HTTP replies and timers.
// Checks scheduling/ownership only; not a measurement of native first-card time.
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert/strict');
const ts = require('typescript');
const read = f => fs.readFileSync(path.join(__dirname, '../src', f), 'utf8');
function compile(source, env = {}) {
  const module = { exports: {} };
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS,
  } }).outputText, { module, exports: module.exports, ...env });
  return module.exports;
}
const rules = compile(read('utils/tradePages.ts'));
const screen = read('screens/TradesScreen.tsx');
const file = ts.createSourceFile('Trades.tsx', screen, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let fn;
(function visit(n) {
  if (ts.isFunctionDeclaration(n) && n.name?.text === 'fetchNextPage') fn = n.getText(file);
  ts.forEachChild(n, visit);
})(file);
assert(fn);
function page(over = {}) { return { job_id: 'j', status: 'running', cursor: 0, total_ready: 0, cards: [], ...over }; }
function fixture(replies, held = []) {
  const requests = [], timers = [], phases = [], applied = [], failures = [];
  const env = {
    ...rules,
    jobRef: { current: page() }, deckRef: { current: held },
    pageLoopRef: { current: { inFlight: false, timer: null, attempt: 0, failures: 0 } },
    deckEpochRef: { current: 1 }, mountedRef: { current: true }, deckGateEndRef: { current: false },
    MAX_SILENT_PAGE_FAILURES: Number(screen.match(/const MAX_SILENT_PAGE_FAILURES = (\d+);/)[1]),
    setPagePhase: p => phases.push(p), setPageKick: () => env.kicks++, kicks: 0,
    setJob: value => { env.jobRef.current = value; },
    setDeckFailure: value => failures.push(value), DECK_FAIL_NETWORK: 'Network failure',
    getTradeStatus: async (...args) => { requests.push(args); const next = replies.shift(); if (next instanceof Error) throw next; return await next; },
    applyJobResult: (next, old, current) => old === current ? next : null,
    applyPage: next => { applied.push(next); const added = next.cards.length; env.deckRef.current = held.concat(next.cards); env.jobRef.current = next; return added; },
    noteDeckGateEnd: e => e.gate === true,
    setTimeout: (callback, ms) => { timers.push({ callback, ms }); return timers.length; },
  };
  const run = compile(fn + '; module.exports = fetchNextPage;', env);
  // vm globals are copied into their own context; mutable counter lives in env via setter.
  return { run, env, requests, timers, applied, phases, failures };
}
let checks = 0;
async function check(name, run) { await run(); checks++; console.log('PASS ' + name); }
let finished = false;
process.on('exit', () => {
  if (!finished) { console.error('Lifecycle suite did not complete.'); process.exitCode = 1; }
});
(async () => {
  await check('first empty successful status gets one 25 ms probe; later delays stay 1000/2000/4000', async () => {
    const h = fixture([page(), page(), page(), page()]);
    for (let i = 0; i < 4; i++) await h.run();
    assert.deepEqual(h.timers.map(t => t.ms), [25, 1000, 2000, 4000]);
    assert.equal(h.requests.length, 4);
  });
  await check('errors retain the 500/1000/2000/4000 ms ladder and stop at bounded failure count', async () => {
    const h = fixture(Array.from({ length: 6 }, () => new Error('offline')));
    for (let i = 0; i < 6; i++) await h.run();
    assert.deepEqual(h.timers.map(t => t.ms), [500, 1000, 2000, 4000, 4000]);
    assert.equal(h.env.pageLoopRef.current.failures, 6);
    assert.equal(h.env.jobRef.current, null);
    assert.equal(h.failures[0].kind, 'poll_abandoned');
  });
  await check('an early empty probe followed by error does not receive a second fast retry', async () => {
    const h = fixture([page(), new Error('network')]); await h.run(); await h.run();
    assert.deepEqual(h.timers.map(t => t.ms), [25, 1000]);
  });
  await check('an already-held card keeps the ordinary 500 ms refill delay', async () => {
    const h = fixture([page()], [{ trade_id: 'held' }]); await h.run();
    assert.deepEqual(h.timers.map(t => t.ms), [500]);
  });
  await check('a newly committed first prefix is applied immediately and refills at ordinary cadence', async () => {
    const next = page({ cards: [{ trade_id: 'first' }], cursor: 1, total_ready: 1, ranked_prefix_ready: true });
    const h = fixture([next]); await h.run();
    assert.equal(h.applied[0], next); assert.equal(h.env.deckRef.current[0].trade_id, 'first');
    assert.deepEqual(h.timers.map(t => t.ms), [500]);
  });
  await check('completed/fully delivered result schedules no retry', async () => {
    const h = fixture([page({ status: 'complete' })]); await h.run(); assert.equal(h.timers.length, 0);
  });
  await check('terminal snapshot error cannot use the quick empty-page probe', async () => {
    const h = fixture([page({ status: 'error' })]); await h.run();
    assert.equal(h.timers.length, 0);
  });
  await check('paywall/verify stop polling without a quick retry', async () => {
    const error = Object.assign(new Error('gate'), { gate: true });
    const h = fixture([error]); await h.run(); assert.equal(h.timers.length, 0);
  });
  for (const [name, change] of [
    ['unmounted', h => { h.env.mountedRef.current = false; }],
    ['replaced loop', h => { h.env.pageLoopRef.current = { inFlight: false, timer: null, attempt: 0, failures: 0 }; }],
    ['changed input epoch', h => { h.env.deckEpochRef.current++; }],
    ['different job', h => { h.env.jobRef.current = page({ job_id: 'other' }); }],
  ]) {
    await check(name + ' in-flight response is dropped without application or timer', async () => {
      let resolve; const h = fixture([new Promise(r => { resolve = r; })]);
      const pending = h.run(); assert.equal(h.requests.length, 1); change(h); resolve(page()); await pending;
      assert.equal(h.applied.length, 0); assert.equal(h.timers.length, 0);
    });
    await check(name + ' rejected response cannot retry or change failure state', async () => {
      let reject; const h = fixture([new Promise((_, r) => { reject = r; })]);
      const pending = h.run(); const oldLoop = h.env.pageLoopRef.current;
      change(h); reject(new Error('late failure')); await pending;
      assert.equal(oldLoop.failures, 0); assert.equal(h.timers.length, 0);
      assert.equal(h.phases.length, 1); // Dispatch's loading state only.
    });
    await check(name + ' timer cannot kick a stale search', async () => {
      const h = fixture([page()]); await h.run(); change(h); h.timers[0].callback();
      assert.equal(h.env.kicks, 0);
    });
  }
  await check('current timer kicks once without starting a new trace or request itself', async () => {
    const h = fixture([page()]); await h.run(); h.timers[0].callback();
    assert.equal(h.env.kicks, 1); assert.equal(h.requests.length, 1);
    assert.doesNotMatch(fn, /beginTradeSearch|tapAt\s*=|find_trades_tapped/);
  });
  console.log(checks + ' initial page polling checks passed.');
  finished = true;
})().catch(e => { console.error(e); process.exitCode = 1; });
