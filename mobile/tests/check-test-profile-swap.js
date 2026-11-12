#!/usr/bin/env node
// Crash safety of the onboarding test profile's device swap (review M4).
//
// Transpiles the REAL module (src/utils/testProfileSwap.ts — zero runtime
// imports) and runs enter, exit and reset against an in-memory store that is
// KILLED after its N-th operation, for every N until the phase completes.
// After each kill the app "relaunches": `reconcileSwap` runs (itself killed
// at every point once, then run clean). The device must always end FULLY real
// or FULLY test — never mixed, and never with the real token lost.
//
// Run: node tests/check-test-profile-swap.js   (npm run test:test-profile-swap)

'use strict';

const fs = require('fs');
const path = require('path');

let ts;
try {
  ts = require('typescript');
} catch {
  console.error('typescript not resolvable — run `npm install` in mobile/ first.');
  process.exit(2);
}

const srcPath = path.join(__dirname, '..', 'src', 'utils', 'testProfileSwap.ts');
const js = ts.transpileModule(fs.readFileSync(srcPath, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;
const shim = { exports: {} };
new Function('module', 'exports', 'require', js)(shim, shim.exports, (name) => {
  throw new Error(`testProfileSwap.ts must have no runtime imports (required ${name})`);
});
const S = shim.exports;

let failures = 0;
let checks = 0;
function ok(cond, msg) {
  checks += 1;
  if (!cond) { failures += 1; console.error('FAIL ', msg); }
}

class Killed extends Error {}

/** In-memory AsyncStorage + SecureStore + token, killable after `budget` ops. */
function makeStore(init, budget = Infinity) {
  const st = {
    kv: new Map(Object.entries(init.kv)),
    sec: new Map(Object.entries(init.sec)),
    token: init.token,
    ops: 0,
    budget,
  };
  const step = () => { if (st.ops >= st.budget) throw new Killed(); st.ops += 1; };
  st.api = {
    async getAllKeys() { step(); return [...st.kv.keys()]; },
    async multiGet(keys) { step(); return keys.map((k) => [k, st.kv.has(k) ? st.kv.get(k) : null]); },
    async multiSet(rows) { step(); for (const [k, v] of rows) st.kv.set(k, v); },
    async multiRemove(keys) { step(); for (const k of keys) st.kv.delete(k); },
    async getSecure(k) { step(); return st.sec.has(k) ? st.sec.get(k) : null; },
    async setSecure(k, v) { step(); st.sec.set(k, v); },
    async deleteSecure(k) { step(); st.sec.delete(k); },
    async getToken() { step(); return st.token; },
    async setToken(t) { step(); st.token = t; },
    async clearToken() { step(); st.token = null; },
  };
  return st;
}

const REAL_TOKEN = 'realTokenAbc';
const TEST_TOKEN = 'tp.testTokenOne';
const TEST_TOKEN_2 = 'tp.testTokenTwo';
const REAL_KV = { ftf_onboarding_state: '{"done":true}', ftf_trade_queue_313: '[1]', feature_flags_v1: '{}' };
const REAL_SEC = { 'ftf.lastUsername': 'opsreal', 'sleeper.link.jwt': 'jwt-real' };

function realState() {
  return { kv: { ...REAL_KV }, sec: { ...REAL_SEC }, token: REAL_TOKEN };
}
function snapshot(st) {
  return { kv: Object.fromEntries(st.kv), sec: Object.fromEntries(st.sec), token: st.token };
}

function isFullyReal(st) {
  const kv = Object.fromEntries(st.kv);
  const realKeysBack = Object.entries(REAL_KV).every(([k, v]) => kv[k] === v);
  const noSwapState = ![S.ACTIVE_KEY, S.SWAP_KEY, S.STASH_DONE_KEY].some((k) => st.kv.has(k))
    && ![...st.kv.keys()].some((k) => k.startsWith(S.STASH_PREFIX));
  const secureBack = Object.entries(REAL_SEC).every(([k, v]) => st.sec.get(k) === v)
    && !st.sec.has(S.SECURE_REAL_TOKEN);
  const onlyRealKeys = [...st.kv.keys()].every((k) => k in REAL_KV);
  return st.token === REAL_TOKEN && realKeysBack && noSwapState && secureBack && onlyRealKeys;
}

function isFullyTest(st, tokens) {
  const stashOk = Object.entries(REAL_KV)
    .filter(([k]) => k !== 'feature_flags_v1')
    .every(([k, v]) => st.kv.get(S.STASH_PREFIX + k) === v);
  const noRealOutside = Object.keys(REAL_KV)
    .filter((k) => k !== 'feature_flags_v1')
    .every((k) => !st.kv.has(k) || st.kv.get(k) !== REAL_KV[k] || k.startsWith('tp'));
  return st.kv.get(S.ACTIVE_KEY) === '1' && !st.kv.has(S.SWAP_KEY)
    && st.kv.get(S.STASH_DONE_KEY) === '1'
    && tokens.includes(st.token) && st.sec.get(S.SECURE_REAL_TOKEN) === REAL_TOKEN
    && stashOk && noRealOutside
    && st.sec.get('ftf.tp.realLastUsername') === 'opsreal'
    && st.sec.get('ftf.tp.realSleeperJwt') === 'jwt-real';
}

/** Run `op` killed after `n` operations, then relaunch: reconcile killed at
 *  `m` (when given), then a clean reconcile. Returns [state, completed]. */
async function runKilled(init, op, n, m) {
  const st = makeStore(init, n);
  let completed = true;
  try { await op(st.api); } catch (e) { if (!(e instanceof Killed)) throw e; completed = false; }
  if (m !== undefined) {
    st.ops = 0; st.budget = m;
    try { await S.reconcileSwap(st.api); } catch (e) { if (!(e instanceof Killed)) throw e; }
  }
  st.ops = 0; st.budget = Infinity;
  const profile = await S.reconcileSwap(st.api);
  return [st, completed, profile];
}

async function sweep(name, init, op, accept) {
  let n = 0;
  for (;;) {
    const [st, completed, profile] = await runKilled(init, op, n);
    const verdict = accept(st, profile, completed);
    ok(verdict, `${name}: kill after op ${n} → ${profile} ${JSON.stringify(snapshot(st))}`);
    // The relaunch reconcile itself killed at every point, then run clean.
    for (let m = 0; m < 60; m += 1) {
      const [st2, , profile2] = await runKilled(init, op, n, m);
      ok(accept(st2, profile2, completed),
        `${name}: kill after op ${n}, reconcile killed after ${m} → ${profile2} ${JSON.stringify(snapshot(st2))}`);
    }
    if (completed) break;
    n += 1;
  }
  return n;
}

async function testState() {
  const st = makeStore(realState());
  await S.enterSwap(st.api, TEST_TOKEN);
  st.kv.set('ftf_onboarding_state', '{"done":false}');   // the test profile's own state
  st.sec.set('ftf.lastUsername', 'opsreal');              // its Sleeper sign-in
  return snapshot(st);
}

(async () => {
  // enter: any kill ends fully real (rolled back) or fully test (completed).
  const enterOps = await sweep('enter', realState(), (s) => S.enterSwap(s, TEST_TOKEN),
    (st, profile, completed) => (profile === 'real' ? !completed && isFullyReal(st)
      : isFullyTest(st, [TEST_TOKEN])));
  ok(enterOps > 10, `enter has every step enumerated (${enterOps} kill points)`);

  const inTest = await testState();
  ok(isFullyTest(makeStore(inTest), [TEST_TOKEN]), 'test state built');

  // exit: once its first marker is written it always rolls FORWARD to fully
  // real (real keys never deleted); a kill before that leaves fully test. A
  // completed exit is always real.
  const exitOps = await sweep('exit', inTest, (s) => S.exitSwap(s),
    (st, profile, completed) => (profile === 'real' ? isFullyReal(st)
      : !completed && isFullyTest(st, [TEST_TOKEN])));
  ok(exitOps > 10, `exit has every step enumerated (${exitOps} kill points)`);

  // reset: always fully test (old or new test token), stash intact.
  const resetOps = await sweep('reset', inTest, (s) => S.resetSwap(s, TEST_TOKEN_2),
    (st, profile) => profile === 'test' && isFullyTest(st, [TEST_TOKEN, TEST_TOKEN_2]));
  ok(resetOps >= 3, `reset has every step enumerated (${resetOps} kill points)`);

  // The review's two concrete bugs, replayed directly.
  // (1) Old enter wrote ACTIVE first, then crashed mid-stash: banner said TEST
  //     while the real token was live. Reconcile must read that as REAL and
  //     keep every real key and the real token.
  {
    const st = makeStore({ kv: { ...REAL_KV, [S.ACTIVE_KEY]: '1' }, sec: { ...REAL_SEC }, token: REAL_TOKEN });
    const profile = await S.reconcileSwap(st.api);
    ok(profile === 'real' && isFullyReal(st), 'ACTIVE without a stash and a real token ⇒ real, nothing dropped');
  }
  // (2) Exit with no stash at all must drop nothing and keep a real token.
  {
    const st = makeStore({ kv: { ...REAL_KV, [S.ACTIVE_KEY]: '1' }, sec: { ...REAL_SEC }, token: REAL_TOKEN });
    await S.exitSwap(st.api);
    ok(isFullyReal(st), 'exit with no stash drops nothing and keeps the real token');
  }
  // (3) A test token with no stash anywhere is cleared, never kept as "real".
  {
    const st = makeStore({ kv: { ...REAL_KV }, sec: { ...REAL_SEC }, token: TEST_TOKEN });
    const profile = await S.reconcileSwap(st.api);
    ok(profile === 'real' && st.token === null, 'a stray test token is cleared');
  }
  // (4) Exit twice / reconcile twice: idempotent.
  {
    const st = makeStore(inTest);
    await S.exitSwap(st.api);
    await S.exitSwap(st.api);
    await S.reconcileSwap(st.api);
    ok(isFullyReal(st), 'exit and reconcile are idempotent');
  }
  // isTestToken mirrors the server prefix.
  ok(S.isTestToken('tp.abc') && !S.isTestToken('abc') && !S.isTestToken(null),
    'isTestToken matches server._TP_TOKEN_PREFIX');

  if (failures) {
    console.error(`test-profile-swap: ${failures} of ${checks} checks failed`);
    process.exit(1);
  }
  console.log(`ok    test-profile-swap: ${checks} checks`);
})().catch((e) => { console.error(e); process.exit(1); });
