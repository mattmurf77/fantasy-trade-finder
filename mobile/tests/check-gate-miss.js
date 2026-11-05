#!/usr/bin/env node
// WHY THIS EXISTS (#339 item 12, ux-lead F-5, head-eng approved; PRD §5.4
// "Gate-miss wait"): a no-card gate miss must NAME its reason, make NO
// timing promise, and END. S0 (contract v0.4 §3b) names two:
//   - `status: "error"`, `error: "roster_check_unavailable"` — before this,
//     jobErrorCopy sent it to the generic "server may still be waking up",
//     the wrong reason;
//   - `wait_reason: "roster_check"` on a building response while S0
//     withholds — before this, the deck showed "Looking for trades…" (and
//     its "First few should land within a few seconds" timing promise)
//     for as long as the withhold lasted.
// Ways it regresses unseen: the error code falls back to the generic copy;
// the named wait never shows (the field isn't parsed, or a later response's
// absence doesn't clear it); the wait never ends; or the copy grows a
// "Searching…", a "Finding more" or a time.
// What it does: EXECUTES utils/gateMiss.ts, api/trades.ts's normalizer,
// tradePages.nextDeckJob and the screen's own fall-through effect (fake
// timers); pins the screen's render order and the copy by source shape.
// HONEST LABEL (G-035): it proves the rules and the wiring, not the pixels —
// code-walk-mobile.md §4 has the TestFlight steps (reachable once S0 ships).
//
// Run: node tests/check-gate-miss.js   (or: npm run test:gate-miss)
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

const G = compile(read('utils/gateMiss.ts'), { require: (n) => { throw new Error(`utils/gateMiss.ts must stay import-free (saw ${n})`); } });
const P = compile(read('utils/tradePages.ts'));
const F = compile(read('utils/firstCardEvent.ts'));
let nextRes = null;
const api = compile(read('api/trades.ts'), { require: (name) => {
  if (name !== './client') throw new Error(`api/trades.ts: unexpected require ${name}`);
  return { api: { post: async () => nextRes, get: async () => nextRes } };
} });
const trades = read('screens/TradesScreen.tsx');
const code = stripComments(trades);
const states = read('components/TradeDeckStates.tsx');

let finished = false;
process.on('exit', () => {
  if (!finished) { console.log('\ncheck-gate-miss did not finish (a check hung): FAILED'); process.exitCode = 1; }
});

(async () => {
  console.log('check-gate-miss:');

  // ── 1. The rules, executed ──────────────────────────────────────────────
  await check('1a. roster_check_unavailable is the named check error; nothing else is', () => {
    eq(G.ROSTER_CHECK_UNAVAILABLE, 'roster_check_unavailable');
    eq(['roster_check_unavailable', 'timeout', 'boom', null, undefined].map(G.isRosterCheckError),
      [true, false, false, false, false]);
  });
  await check('1b. the named wait: no cards, still building, and wait_reason "roster_check" — all three', () => {
    eq(G.WAIT_REASON_ROSTER_CHECK, 'roster_check');
    const running = { status: 'running', wait_reason: 'roster_check' };
    eq([
      G.isRosterCheckWait(running, 0),
      G.isRosterCheckWait(running, 1),
      G.isRosterCheckWait({ ...running, status: 'complete' }, 0),
      G.isRosterCheckWait({ status: 'running' }, 0),
      G.isRosterCheckWait({ status: 'running', wait_reason: 'other' }, 0),
      G.isRosterCheckWait(null, 0),
    ], [true, false, false, false, false, false]);
  });
  await check('1c. api/trades parses wait_reason as optional (present → kept; absent → no key)', async () => {
    nextRes = { job_id: 'j', status: 'running', cards: [], wait_reason: 'roster_check' };
    eq((await api.generateTrades({ league_id: 'L' })).wait_reason, 'roster_check', '/generate');
    eq((await api.getTradeStatus('j', { cursor: 0 })).wait_reason, 'roster_check', '/status');
    nextRes = { job_id: 'j', status: 'running', cards: [] };
    ok(!('wait_reason' in (await api.getTradeStatus('j'))), 'absent means today\'s behavior');
  });
  await check('1d. a later response without wait_reason ends the withhold (no carry-over), paged or legacy', () => {
    const prev = { job_id: 'j', status: 'running', cards: [], cursor: 0, total_ready: 0, wait_reason: 'roster_check' };
    eq(P.nextDeckJob(prev, { job_id: 'j', status: 'running', cards: [], cursor: 0, total_ready: 0 }, []).wait_reason, undefined, 'paged');
    eq(P.nextDeckJob(prev, { job_id: 'j', status: 'running', cards: [] }, []).wait_reason, undefined, 'legacy');
    eq(P.nextDeckJob({ ...prev, wait_reason: undefined }, { ...prev }, []).wait_reason, 'roster_check', 'and starts when one says so');
  });
  await check('1e. EXECUTED: the screen\'s fall-through ends the wait after FIRST_CARD_TIMEOUT_MS (R2b\'s 10 s)', () => {
    eq(F.FIRST_CARD_TIMEOUT_MS, 10_000);
    const sf = ts.createSourceFile('T.tsx', trades, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const found = [];
    (function visit(n) {
      if (ts.isCallExpression(n) && n.expression.getText(sf) === 'useEffect' && n.arguments[0]
          && ts.isArrowFunction(n.arguments[0]) && n.arguments[0].body.getText(sf).includes('setRosterWaitExpired(false)')) {
        found.push(n.arguments[0].body.getText(sf));
      }
      ts.forEachChild(n, visit);
    })(sf);
    ok(found.length === 1, `one fall-through effect (found ${found.length})`);
    const effect = compile(`module.exports = function (env) {
      const { rosterWait, setRosterWaitExpired, setTimeout, clearTimeout, FIRST_CARD_TIMEOUT_MS } = env; ${found[0]} };`);
    const run = (rosterWait) => {
      const calls = []; const timers = [];
      const cleanup = effect({ rosterWait, FIRST_CARD_TIMEOUT_MS: F.FIRST_CARD_TIMEOUT_MS,
        setRosterWaitExpired: (v) => calls.push(v),
        setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; }, clearTimeout: () => {} });
      return { calls, timers, cleanup };
    };
    const waiting = run(true);
    eq([waiting.calls, waiting.timers.map((t) => t.ms)], [[false], [10_000]], 'a fresh wait starts at "not expired" with one 10 s timer');
    waiting.timers[0].fn();
    eq(waiting.calls, [false, true], 'at 10 s it falls through to the error');
    ok(typeof waiting.cleanup === 'function', 'the timer is cleared when the wait ends (cards, a new search)');
    const idle = run(false);
    eq([idle.calls, idle.timers.length], [[false], 0], 'no wait, no timer (and the error state resets)');
  });
  await check('1f. EXECUTED: Retry while the SAME job still runs (a non-force repeat) restarts the wait — it never sticks on the error', () => {
    // The screen's own effect WITH its deps array, re-run React-style only
    // when a dep changes, plus the screen's own Retry handler.
    const sf = ts.createSourceFile('T.tsx', trades, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    let body = null; let deps = null; let retry = null;
    (function visit(n) {
      if (ts.isCallExpression(n) && n.expression.getText(sf) === 'useEffect' && n.arguments[0]
          && ts.isArrowFunction(n.arguments[0]) && n.arguments[0].body.getText(sf).includes('setRosterWaitExpired(false)')) {
        body = n.arguments[0].body.getText(sf);
        deps = n.arguments[1] && n.arguments[1].getText(sf);
      }
      if (ts.isFunctionDeclaration(n) && n.name && n.name.text === 'handleGateRetry') retry = n.getText(sf);
      ts.forEachChild(n, visit);
    })(sf);
    ok(body && deps, 'the fall-through effect and its deps');
    ok(retry, 'handleGateRetry');
    const names = ['rosterWait', 'job', 'gateRetrySeq', 'setRosterWaitExpired', 'setTimeout', 'clearTimeout', 'FIRST_CARD_TIMEOUT_MS'];
    const effect = compile(`module.exports = function (env) { const { ${names.join(', ')} } = env; ${body} };`);
    const depsOf = compile(`module.exports = function (env) { const { ${names.join(', ')} } = env; return ${deps}; };`);
    const handler = compile(`module.exports = function (env) {
      const { setGateRetrySeq, handleFindTrades } = env; return ${retry}; };`);
    // A tiny React: state, and an effect that re-runs when its deps change.
    const st = { expired: false, seq: 0, timers: [], searches: [] };
    let prevDeps = null; let cleanup = null;
    const env = () => ({
      rosterWait: true, job: { job_id: 'j1' }, gateRetrySeq: st.seq, FIRST_CARD_TIMEOUT_MS: F.FIRST_CARD_TIMEOUT_MS,
      setRosterWaitExpired: (v) => { st.expired = v; },
      setTimeout: (fn, ms) => { st.timers.push({ fn, ms, live: true }); return st.timers.length; },
      clearTimeout: (id) => { if (st.timers[id - 1]) st.timers[id - 1].live = false; },
    });
    const render = () => {
      const e = env(); const d = depsOf(e);
      if (!prevDeps || d.some((v, i) => !Object.is(v, prevDeps[i]))) {
        if (typeof cleanup === 'function') cleanup();
        cleanup = effect(e);
      }
      prevDeps = d;
    };
    const fire = () => { for (const t of st.timers) if (t.live) { t.live = false; t.fn(); } };
    render();
    fire();
    eq(st.expired, true, 'the wait expired into the error');
    render(); // the same running job answers again: nothing changes by itself
    eq(st.expired, true, 'control: with no retry the error stays (same job_id)');
    handler({ setGateRetrySeq: (u) => { st.seq = typeof u === 'function' ? u(st.seq) : u; },
      handleFindTrades: (src) => st.searches.push(src) })();
    eq(st.searches, ['deck_error_retry'], 'Retry runs a new search as deck_error_retry');
    render(); // the retry's answer: SAME job_id, still withholding
    eq(st.expired, false, 'Retry restarts the named wait even on the same job');
    eq(st.timers.filter((t) => t.live).map((t) => t.ms), [10_000], '…with a fresh 10 s, so it ends again');
    fire();
    eq(st.expired, true, 'and it ends again');
  });

  // ── 2. The screen's wiring ──────────────────────────────────────────────
  await check('2a. a roster_check_unavailable job error maps to the NAMED error, not the generic copy', () => {
    ok(/setDeckFailure\(isRosterCheckError\(job\.error\)\s*\? \{ kind: 'roster_check', message: GATE_ROSTER_CHECK_FAILED_LINE \}\s*: \{ kind: 'job_error', message: jobErrorCopy\(job\.error\) \}\);/.test(code),
      'the job-error mirror');
    ok(/\) : deckFailure\?\.kind === 'roster_check' \? \(\s*<GateErrorCard minHeight=\{topCardH\} onRetry=\{handleGateRetry\} \/>\s*\) : deckFailure \? \(/.test(code),
      'its card, ahead of the generic "Search failed" card; Retry re-runs as deck_error_retry');
  });
  await check('2b. the withhold renders the named wait in place of "Looking for trades…", then the error', () => {
    ok(/const rosterWait = isRosterCheckWait\(job, deck\.length\);/.test(code), 'derived from the job and the device\'s cards');
    ok(/\) : rosterWait \? \(\s*rosterWaitExpired \? \(\s*<GateErrorCard minHeight=\{topCardH\} onRetry=\{handleGateRetry\} \/>\s*\) : \(\s*<GateWaitCard minHeight=\{topCardH\} \/>\s*\)\s*\) : firstRun &&/.test(code),
      'wait, then error');
    const at = (s) => code.indexOf(s);
    ok(at(') : rosterWait ? (') > at('onRetry={handleOfflineTapRetry} />'), 'offline outranks it');
    ok(at(') : rosterWait ? (') < at(") : fairPending || generateMutation.isPending || job?.status === 'running' ? ("),
      'it outranks "Looking for trades…" (and the first-run skeleton)');
    ok(/next\.wait_reason !== job\.wait_reason/.test(code), 'the legacy poller applies a wait_reason change on its own');
  });
  await check('2c. the copy: marketing-lead\'s final trades.gate.* (§6 addendum 5), no placeholder marks; no "Searching…", no "Finding more", no time', () => {
    const want = {
      GATE_ROSTER_CHECK_FAILED_TITLE: "Couldn't confirm current rosters",
      GATE_ROSTER_CHECK_FAILED_LINE: "The roster check didn't go through.",
      GATE_ROSTER_CHECK_RETRY: 'Retry',
      GATE_ROSTER_CHECK_RETRY_A11Y: 'Retry the roster check',
      GATE_ROSTER_CHECK_WAIT: "Checking your league's current rosters…",
    };
    ok(!/COPY: placeholder, marketing-lead \(trades\.gate\.\*\)/.test(states), 'no trades.gate.* placeholder marks remain');
    for (const [name, text] of Object.entries(want)) {
      const m = new RegExp(`export const ${name} = (["'])(.*?)\\1;`).exec(states);
      ok(m, `${name} not found`);
      const actual = m[2];
      // The rules run on the shipped string (whatever it says), then the final copy.
      ok(!/search(ing)?…|searching|finding more|find more/i.test(actual), `${name}: no Searching / Finding more (${actual})`);
      ok(!/\d|second|minute|moment|soon|few/i.test(actual), `${name}: no timing promise (${actual})`);
      ok(!/\bwe\b|sleeper|espn|mfl|fleaflicker|platform|trade/i.test(actual), `${name}: no "we", no platform, no promise of trades (${actual})`);
      eq(actual, text, `${name}: marketing-lead's final copy`);
    }
    ok(/testID="trades\.gate-wait"/.test(states) && /testID="trades\.gate-error"/.test(states)
      && /testID="trades\.gate-error\.retry"\s*label=\{GATE_ROSTER_CHECK_RETRY\}\s*accessibilityLabel=\{GATE_ROSTER_CHECK_RETRY_A11Y\}/.test(states),
      'testIDs, and Retry speaks its own label');
  });
  await check('2d. the gate cards take no navigation or deck props: Back stays the header\'s', () => {
    ok(/export function GateWaitCard\(\{ minHeight \}: \{ minHeight\?: number \| null \}\)/.test(states), 'wait: minHeight only');
    ok(/export function GateErrorCard\(\{ minHeight, onRetry \}: \{ minHeight\?: number \| null; onRetry: \(\) => void \}\)/.test(states), 'error: minHeight + Retry only');
  });

  finished = true;
  console.log(failures ? `\ncheck-gate-miss: ${failures} FAILED` : '\ncheck-gate-miss: all passed');
  process.exit(failures ? 1 : 0);
})();
