#!/usr/bin/env node
// G420: execute the native transport/session lifecycle with fake time and no network.
// FTF_MOBILE_TEST_ROOT can select an unchanged runtime for honest baseline RED.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const ROOT = process.env.FTF_MOBILE_TEST_ROOT || path.resolve(__dirname, '..');
const flush = async () => { for (let n = 0; n < 80; n++) await Promise.resolve(); };
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return {promise, resolve, reject}; };
function clock() {
  let now = 100_000, id = 0;
  const timers = new Map();
  return {
    Date: class extends Date { static now() { return now; } },
    performance: {now: () => now},
    setTimeout(fn, ms) { const key = ++id; timers.set(key, {at: now + ms, fn}); return key; },
    clearTimeout(key) { timers.delete(key); },
    suspend(ms) { now += ms; },
    async advance(ms) {
      const end = now + ms;
      await flush();
      while (true) {
        const next = [...timers].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!next) break;
        now = Math.max(now, next[1].at); timers.delete(next[0]); next[1].fn(); await flush();
      }
      now = end; await flush();
    },
  };
}
function load(rel, requireShim, time = clock(), extra = {}) {
  const source = fs.readFileSync(path.join(ROOT, rel), 'utf8');
  const module = {exports: {}};
  const output = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React}}).outputText;
  vm.runInNewContext(output, {module, exports: module.exports, require: requireShim, AbortController, DOMException, URL, console, ...time, ...extra}, {filename: rel});
  return module.exports;
}
function transport() {
  const time = clock(), events = [], requests = [];
  let token = 'synthetic-token-a', foreground;
  let tokenReader = async () => token, tokenDeleter = async () => { token = null; };
  let responder = () => new Promise(() => {});
  const native = {
    'expo-constants': {default: {expoConfig: {extra: {apiBaseUrl: 'https://example.invalid'}, version: 'test'}}},
    'expo-device': {DeviceType: {TABLET: 2, DESKTOP: 3}},
    'expo-secure-store': {getItemAsync: (...args) => tokenReader(...args), setItemAsync: async (key, value) => { token = value; }, deleteItemAsync: (...args) => tokenDeleter(...args)},
    'react-native': {Platform: {OS: 'ios'}, AppState: {addEventListener: (event, fn) => { foreground = fn; }}},
    './events': {track: (event, data) => events.push({event, data})},
  };
  const client = load('src/api/client.ts', name => {
    assert.ok(native[name], `unexpected client import ${name}`); return native[name];
  }, time, {fetch: (url, opts) => {
    requests.push({url, opts});
    return new Promise((resolve, reject) => {
      const abort = () => reject(new DOMException('Aborted', 'AbortError'));
      if (opts.signal?.aborted) return abort();
      opts.signal?.addEventListener('abort', abort, {once: true});
      Promise.resolve().then(() => responder(url, opts)).then(resolve, reject);
    });
  }});
  return {time, client, events, requests, setResponder: fn => { responder = fn; }, setTokenReader: fn => { tokenReader = fn; }, setTokenDeleter: fn => { tokenDeleter = fn; }, replaceToken: value => { token = value; }, background: () => foreground('background')};
}
const response = (status, body) => ({status, ok: status >= 200 && status < 300, text: async () => JSON.stringify(body)});
function sessionHarness() {
  const h = transport(), seeds = [], pregen = [], invalidations = [], storage = new Map();
  const user = {user_id: 'synthetic-user', username: 'Tester', display_name: 'Tester', avatar_id: null};
  const league = {league_id: 'synthetic-a', league_name: 'Test A'};
  const providers = {
    rosters: async () => [{owner_id: user.user_id, roster_id: 1, players: []}],
    users: async () => [{user_id: user.user_id, username: 'Tester'}],
    proof: async () => 'verified',
    leagues: async () => [],
    connect: async () => ({ok: true, league_id: 'synthetic-b', league_name: 'Test B'}),
  };
  const sleeper = {
    findMyRoster: (rows, id) => rows.find(r => r.owner_id === id || r.co_owners?.includes(id)),
    getLeagueRosters: (...args) => providers.rosters(...args), getLeagueUsers: (...args) => providers.users(...args),
    getLeagues: (...args) => providers.leagues(...args), warmPlayerCache: async () => {}, resetWarmedFlag: () => {},
  };
  let state;
  const platformRequire = name => {
    if (name === './client') return h.client;
    if (name === '../state/useSession') return state;
    throw Error(`unexpected platform import ${name}`);
  };
  const espn = load('src/api/espn.ts', platformRequire, h.time);
  const platformLink = load('src/api/platformLink.ts', platformRequire, h.time);
  const auth = load('src/api/auth.ts', name => {
    if (name === './client') return h.client;
    if (name === './events') return {getDeviceId: async () => 'synthetic-device'};
    if (name === './sendInSleeper') return {maybeReplaySleeperVerification: (...args) => providers.proof(...args)};
    if (name === './sleeper') return sleeper;
    if (name === './espn') return espn;
    if (name === './platformLink') return platformLink;
    if (name === '../state/useSession') return state;
    throw Error(`unexpected auth import ${name}`);
  }, h.time);
  const winNow = load('src/api/winNow.ts', name => { assert.equal(name, './client'); return h.client; }, h.time);
  const create = init => {
    let value;
    const store = selector => selector(value);
    store.getState = () => value;
    store.setState = patch => { value = {...value, ...(typeof patch === 'function' ? patch(value) : patch)}; };
    value = init(store.setState, store.getState);
    return store;
  };
  const stubs = {
    zustand: {create},
    '@react-native-async-storage/async-storage': {default: {setItem: async (key, value) => storage.set(key, value), removeItem: async key => storage.delete(key), getItem: async key => storage.get(key)}},
    '../api/client': h.client, '../api/auth': auth, '../api/winNow': winNow,
    '../api/tradePregen': {maybePregenTrades: id => pregen.push(id)},
    '../api/league': {connectLeague: (...args) => providers.connect(...args)},
    '../api/sleeper': sleeper, '../api/purchases': {initPurchases: async () => {}},
    '../observability/sentry': {setUser: () => {}},
    './queryClient': {seedLeagueSessionCaches: (id, seed) => seeds.push({id, seed}), queryClient: {invalidateQueries: input => invalidations.push(input)}},
    '../api/rankings': {getActiveScoringFormat: async () => '1qb_ppr'},
  };
  state = load('src/state/useSession.ts', name => {
    if (name === './leagueSession') return load('src/state/leagueSession.ts', dep => { assert.equal(dep, '../api/client'); return h.client; }, h.time);
    assert.ok(stubs[name], `unexpected state import ${name}`); return stubs[name];
  }, h.time);
  state.useSession.setState({user, league, hasToken: true, isDemo: false});
  h.setResponder(url => response(200, url.endsWith('/api/session/init') ? {ok: true, token: 'synthetic-token-a'} : {status: 'available', teams: [], assets: []}));
  return {...h, state, auth, winNow, user, league, seeds, pregen, providers, storage, invalidations};
}
const initRequests = h => h.requests.filter(r => r.url.endsWith('/api/session/init'));
const projectionRequests = h => h.requests.filter(r => r.url.includes('/api/league/season-projections'));
function mountWinNow(h) {
  const values = [], effects = [];
  const React = {
    createElement: (type, props, ...children) => ({type, props: {...props, children}}),
    useState: initial => { const i = values.length; values.push(initial); return [initial, value => { values[i] = typeof value === 'function' ? value(values[i]) : value; }]; },
    useRef: current => ({current}), useEffect: fn => { effects.push(fn); },
  };
  const stubs = {
    react: {...React, default: React}, 'react-native': {StyleSheet: {create: value => value}},
    'react-native-safe-area-context': {}, '@react-navigation/native': {useIsFocused: () => true},
    '../components/chalkline/Text': {}, '../components/FeedbackFAB': {},
    '../state/useSession': h.state, '../state/useFeatureFlags': {useFlag: name => name !== 'outlook.championship_probabilities'},
    '../api/winNow': h.winNow,
    '../utils/winNow': {seasonStale: () => false},
    '../theme/chalkline': {ink: {}, chalk: {}, ice: {}, space: {}, radii: {}, type: {}},
  };
  const screen = load('src/screens/WinNowScreen.tsx', name => { assert.ok(stubs[name], `unexpected screen import ${name}`); return stubs[name]; }, h.time);
  const child = screen.default(); child.type(child.props);
  const cleanup = effects[0]();
  return {values, cleanup};
}
// Execute the actual screen handler, retaining its try/catch/finally and owner
// calls. Only React's surrounding lexical values are supplied by the harness.
function screenHandler(rel, name, bindings, time) {
  const source = fs.readFileSync(path.join(ROOT, rel), 'utf8');
  const ast = ts.createSourceFile(rel, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let found;
  const visit = node => { if (ts.isFunctionDeclaration(node) && node.name?.text === name) found = node; ts.forEachChild(node, visit); };
  visit(ast); assert.ok(found, `screen handler ${name} exists`);
  const output = ts.transpileModule(`${found.getText(ast)}\nmodule.exports = ${name};`, {compilerOptions: {target: ts.ScriptTarget.ES2020}}).outputText;
  const module = {exports: {}};
  vm.runInNewContext(output, {module, ...time, ...bindings}, {filename: rel});
  return module.exports;
}
function picker(h) {
  const ui = {selecting: null, error: null, navigated: 0};
  const invoke = screenHandler('src/screens/LeaguePickerScreen.tsx', 'pickLeague', {
    ...h.state, user: h.user, selectingId: null, cached: [],
    setSelectingId: value => { ui.selecting = value; }, setError: value => { ui.error = value; },
    advanceGuideIfActive: () => {}, track: () => {}, ApiError: h.client.ApiError,
    setLeague: (...args) => h.state.useSession.getState().setLeague(...args),
    onLeaguePicked: () => { ui.navigated++; }, maybePregenTrades: () => {},
  }, h.time);
  return {ui, invoke};
}
let failures = 0, passed = 0;
async function check(name, fn) {
  try { await fn(); passed++; console.log(`PASS ${name}`); }
  catch (error) { failures++; console.error(`FAIL ${name}: ${error.message}`); }
}
async function main() {
  await check('T7 real projection GET accepts measured 15.2-second HTTP completion', async () => {
    const h = transport();
    h.setResponder(() => new Promise(resolve => h.time.setTimeout(() => resolve(response(200, {status: 'unavailable', reason: 'test_source'})), 15_200)));
    const result = h.client.api.get('/api/league/season-projections?league_id=synthetic-league').then(value => ({value}), error => ({error}));
    await h.time.advance(15_200);
    const actual = await result;
    assert.equal(actual.error, undefined, `unexpected deadline: ${actual.error?.message}`);
    assert.equal(actual.value.status, 'unavailable');
  });
  await check('T8 old-session verification 403 cannot mutate replacement verification', async () => {
    const h = transport(), pending = deferred(); let callbacks = 0;
    h.setResponder(() => pending.promise);
    h.client.setOnVerificationRequired(() => { callbacks++; });
    const result = h.client.api.get('/api/league/season-projections').catch(error => error);
    await flush(); h.replaceToken('synthetic-token-b');
    pending.resolve(response(403, {error: 'verification_required'})); await result;
    assert.equal(callbacks, 0, 'stale response published verification');
  });
  await check('T8 deadline is typed and neutral, not a hosting diagnosis', async () => {
    const h = transport();
    const result = h.client.api.get('/api/ordinary').catch(error => error);
    await h.time.advance(15_000); const error = await result;
    assert.equal(error.status, 0); assert.equal(error.isTimeout, true);
    assert.equal(error.message, 'This request took too long. Please try again.');
    assert.equal(h.events.length, 1);
  });
  await check('T1 actual mounted Win Now repairs the exact lost-session refusal once', async () => {
    const h = sessionHarness();
    await h.state.useSession.getState().revalidateSession();
    assert.equal(initRequests(h).length, 1);
    let ready = false; // process rollover after a genuinely successful init
    h.setResponder(url => {
      if (url.endsWith('/api/session/init')) { ready = true; return response(200, {ok: true, token: 'synthetic-token-a'}); }
      return ready ? response(200, {status: 'available', teams: [], assets: []}) : response(409, {error: 'session_not_initialized'});
    });
    // The current native screen must own recovery. The baseline screen invokes
    // only short GET retries; all its existing modules remain executable.
    const mounted = mountWinNow(h); await h.time.advance(2_000);
    assert.equal(initRequests(h).length, 2, 'screen never repaired its previously initialized league context');
    assert.equal(mounted.values[0]?.status, 'available'); assert.equal(mounted.values[1], false);
    mounted.cleanup();
  });
  // These lifecycle APIs did not exist at baseline. The baseline-sensitive
  // screen/transport cases above, not a missing-export assertion, prove RED.
  if (process.env.FTF_BASELINE_ONLY === '1') {
    await check('T2 original foreground revalidation must join pending init', async () => {
      const h = sessionHarness(), pending = deferred(); h.providers.rosters = () => pending.promise;
      const first = h.state.useSession.getState().revalidateSession(); let joined = false;
      const second = h.state.useSession.getState().revalidateSession().then(() => { joined = true; });
      await h.time.advance(5_000); const wasJoinedEarly = joined;
      pending.resolve([]); await first; await second;
      assert.equal(wasJoinedEarly, false, 'second revalidation resolved before shared init settled');
    });
    await check('T4 original shared-token writers must wait for prior init acknowledgement', async () => {
      const h = sessionHarness(), pending = deferred();
      h.setResponder((url, opts) => JSON.parse(opts.body || '{}').league_id === 'synthetic-a' ? pending.promise : response(200, {ok: true, token: 'synthetic-token-a'}));
      const a = h.state.useSession.getState().revalidateSession(); await flush();
      const b = h.state.useSession.getState().switchLeague({league_id: 'synthetic-b', league_name: 'B'});
      await flush(); const beforeAcknowledgement = initRequests(h).length;
      pending.resolve(response(200, {ok: true, token: 'synthetic-token-a'})); await a; await b;
      assert.equal(beforeAcknowledgement, 1, 'B init dispatched while A was still unacknowledged');
    });
    await check('T10 original ambiguous init must block automatic foreground restart', async () => {
      const h = sessionHarness(), pending = deferred(); h.setResponder(() => pending.promise);
      const first = h.state.useSession.getState().revalidateSession(); await h.time.advance(30_000); await first;
      const before = initRequests(h).length;
      const reentry = h.state.useSession.getState().revalidateSession(); await flush();
      const automaticRequests = initRequests(h).length - before;
      pending.resolve(response(200, {ok: true, token: 'synthetic-token-a'})); await reentry;
      assert.equal(automaticRequests, 0, 'ambiguous init silently restarted on foreground');
    });
    console.log(`${passed} passed; ${failures} failed (unchanged runtime baseline)`);
    process.exitCode = failures ? 1 : 0; return;
  }
  await check('T1 locally ready context forces exactly one repair after server restoration', async () => {
    const h = sessionHarness(); await h.state.initializeLeagueSession(h.user, {league_id: h.league.league_id, name: h.league.league_name});
    let ready = false;
    h.setResponder(url => {
      if (url.endsWith('/api/session/init')) { ready = true; return response(200, {ok: true, token: 'synthetic-token-a'}); }
      return ready ? response(200, {status: 'unavailable', reason: 'unsupported_source', message: 'Fixture source is unavailable.'}) : response(409, {error: 'session_not_initialized'});
    });
    const result = h.state.loadSeasonProjections(h.league.league_id, new AbortController().signal);
    await h.time.advance(2_000); const data = await result;
    assert.equal(initRequests(h).length, 2); assert.equal(projectionRequests(h).length, 4);
    assert.equal(data.status, 'unavailable'); assert.equal(data.reason, 'unsupported_source');
  });
  await check('T2 two foreground callers join pending init without an early baseline read', async () => {
    const h = sessionHarness(), pending = deferred();
    h.providers.rosters = () => pending.promise;
    let joined = false;
    const background = h.state.useSession.getState().revalidateSession();
    const second = h.state.useSession.getState().revalidateSession().then(() => { joined = true; });
    const baseline = h.state.loadSeasonProjections(h.league.league_id, new AbortController().signal);
    await h.time.advance(5_000);
    assert.equal(joined, false); assert.equal(projectionRequests(h).length, 0); assert.equal(initRequests(h).length, 0);
    pending.resolve([{owner_id: h.user.user_id, players: []}]);
    await Promise.all([background, second, baseline]);
    assert.equal(initRequests(h).length, 1); assert.equal(h.seeds.length, 1);
  });
  await check('T3 a second typed refusal terminates; a fresh explicit Refresh recovers', async () => {
    const h = sessionHarness();
    h.setResponder(url => response(url.endsWith('/api/session/init') ? 200 : 409, url.endsWith('/api/session/init') ? {ok: true, token: 'synthetic-token-a'} : {error: 'session_not_initialized'}));
    const attempt = h.state.loadSeasonProjections(h.league.league_id, new AbortController().signal).catch(error => error);
    await h.time.advance(5_000); assert.equal((await attempt).status, 409);
    assert.equal(initRequests(h).length, 2); assert.equal(projectionRequests(h).length, 6);
    h.setResponder(url => response(200, url.endsWith('/api/session/init') ? {ok: true, token: 'synthetic-token-a'} : {status: 'available'}));
    assert.equal((await h.state.loadSeasonProjections(h.league.league_id, new AbortController().signal, 'refresh')).status, 'available');
  });
  await check('T4 same-token successful A→B waits for A acknowledgement and publishes B only', async () => {
    const h = sessionHarness(), pending = deferred();
    h.setResponder((url, opts) => JSON.parse(opts.body || '{}').league_id === 'synthetic-a' ? pending.promise : response(200, {ok: true, token: 'synthetic-token-a'}));
    const a = h.state.initializeLeagueSession(h.user, {league_id: 'synthetic-a', name: 'A'}).catch(error => error);
    await flush(); assert.equal(initRequests(h).length, 1);
    const b = h.state.useSession.getState().switchLeague({league_id: 'synthetic-b', league_name: 'B'});
    await flush(); assert.equal(initRequests(h).length, 1, 'B dispatched before A acknowledged');
    pending.resolve(response(200, {ok: true, token: 'synthetic-token-a'})); await a; await b;
    assert.equal(initRequests(h).length, 2); assert.deepEqual(h.seeds.map(s => s.id), ['synthetic-b']);
    assert.equal(h.state.useSession.getState().league.league_id, 'synthetic-b');
  });
  await check('T4 obsolete prepared A never dispatches; only B is initialized', async () => {
    const h = sessionHarness(), pending = deferred(); let first = true;
    h.providers.rosters = () => { if (first) { first = false; return pending.promise; } return Promise.resolve([]); };
    const a = h.state.initializeLeagueSession(h.user, {league_id: 'synthetic-a', name: 'A'}).catch(error => error);
    await flush();
    const b = h.state.initializeLeagueSession(h.user, {league_id: 'synthetic-b', name: 'B'}, {cause: 'selection'});
    pending.resolve([]); await a; await b;
    assert.deepEqual(initRequests(h).map(r => JSON.parse(r.opts.body).league_id), ['synthetic-b']);
    assert.deepEqual(h.seeds.map(s => s.id), ['synthetic-b']);
  });
  await check('T5 one caller detaches without canceling another shared consumer', async () => {
    const h = sessionHarness(), pending = deferred(), caller = new AbortController();
    h.providers.rosters = () => pending.promise;
    const first = h.state.loadSeasonProjections(h.league.league_id, caller.signal).catch(error => error);
    const second = h.state.loadSeasonProjections(h.league.league_id, new AbortController().signal);
    await flush(); caller.abort(); assert.equal((await first).name, 'AbortError');
    pending.resolve([]); await second;
    assert.equal(initRequests(h).length, 1); assert.equal(projectionRequests(h).length, 1); assert.equal(h.events.length, 0);
  });
  await check('T5 sign-out invalidates prepared work before it can restore a token/cache', async () => {
    const h = sessionHarness(), pending = deferred(); h.providers.rosters = () => pending.promise;
    const attempt = h.state.loadSeasonProjections(h.league.league_id, new AbortController().signal).catch(error => error);
    await flush(); await h.state.useSession.getState().signOut(); pending.resolve([]); await flush();
    assert.equal((await attempt).name, 'AbortError'); assert.equal(initRequests(h).length, 0); assert.equal(h.seeds.length, 0);
    assert.equal(h.state.useSession.getState().hasToken, false);
  });
  await check('T10 uncertainty survives queued B, refocus/foreground, and throttle expiry', async () => {
    const h = sessionHarness(), pending = deferred();
    h.setResponder(() => pending.promise);
    const a = h.state.initializeLeagueSession(h.user, {league_id: 'synthetic-a', name: 'A'}).catch(error => error);
    await flush();
    const b = h.state.useSession.getState().switchLeague({league_id: 'synthetic-b', league_name: 'B'}).catch(error => error);
    await flush(); await h.time.advance(30_000); await a; await b;
    const count = h.requests.length;
    for (let n = 0; n < 3; n++) {
      await h.state.useSession.getState().revalidateSession();
      const outcome = await h.state.loadSeasonProjections(h.league.league_id, new AbortController().signal).catch(error => error);
      assert.ok(outcome instanceof Error || outcome?.name === 'ApiError');
      await h.time.advance(60_000);
    }
    pending.resolve(response(200, {ok: true, token: 'synthetic-token-a'})); await flush();
    assert.equal(h.requests.length, count); assert.equal(h.seeds.length, 0);
    h.setResponder(url => response(200, url.endsWith('/api/session/init') ? {ok: true, token: 'synthetic-token-a'} : {status: 'available'}));
    assert.equal((await h.state.loadSeasonProjections(h.league.league_id, new AbortController().signal, 'refresh')).status, 'available');
    assert.equal(h.requests.length, count + 2);
  });
  await check('T10 whole attempt bounds stalled preparation; it cannot dispatch after 90s', async () => {
    const h = sessionHarness(), pending = deferred(); h.providers.rosters = () => pending.promise;
    const attempt = h.state.loadSeasonProjections(h.league.league_id, new AbortController().signal).catch(error => error);
    await h.time.advance(90_000); const error = await attempt;
    assert.equal(error.isTimeout, true); assert.equal(initRequests(h).length, 0); assert.equal(h.events.length, 0);
    pending.resolve([]); await flush(); assert.equal(initRequests(h).length, 0); assert.equal(h.seeds.length, 0);
  });
  await check('T10 ambiguous explicit retry relatches; replacement token starts a separate lane', async () => {
    const h = sessionHarness(); h.setResponder(() => new Promise(() => {}));
    for (const cause of ['automatic', 'refresh']) {
      const failed = h.state.loadSeasonProjections(h.league.league_id, new AbortController().signal, cause).catch(error => error);
      await h.time.advance(30_000); assert.equal((await failed).isTimeout, true);
      const count = initRequests(h).length;
      const automatic = await h.state.loadSeasonProjections(h.league.league_id, new AbortController().signal).catch(error => error);
      assert.equal(automatic.body?.error, 'session_init_uncertain'); assert.equal(initRequests(h).length, count);
    }
    assert.equal(h.seeds.length, 0); assert.equal(projectionRequests(h).length, 0);
    await h.client.setSessionToken('synthetic-token-b');
    h.setResponder(url => response(200, url.endsWith('/api/session/init') ? {ok: true, token: 'synthetic-token-b'} : {status: 'available'}));
    assert.equal((await h.state.loadSeasonProjections(h.league.league_id, new AbortController().signal)).status, 'available');
    assert.equal(initRequests(h).length, 3); assert.equal(projectionRequests(h).length, 1);
  });
  await check('T7 exact pathname/method budgets, query and existing absolute URL form', async () => {
    const cases = [
      ['/api/league/season-projections?league_id=synthetic-a', 'GET', 30_000],
      ['https://example.invalid/api/league/season-projections?league_id=synthetic-a', 'GET', 30_000],
      ['/api/league/season-projections-extra', 'GET', 15_000],
      ['/prefix/api/league/season-projections', 'GET', 15_000],
      ['/api/league/season-projections', 'POST', 15_000],
      ['/api/ordinary', 'GET', 15_000], ['/api/session/init', 'POST', 30_000], ['/api/trades/generate', 'POST', 30_000],
    ];
    for (const [route, method, budget] of cases) {
      const h = transport(); let settled = false;
      const result = h.client.apiRequest(route, {method}).catch(error => { settled = true; return error; });
      await h.time.advance(budget - 1); assert.equal(settled, false, route);
      await h.time.advance(1); assert.equal((await result).isTimeout, true, route);
    }
  });
  await check('T7 token preparation and response body share the route deadline', async () => {
    for (const phase of ['token', 'body']) {
      const h = transport(), pending = deferred();
      if (phase === 'token') h.setTokenReader(() => pending.promise);
      else h.setResponder(() => ({status: 200, ok: true, text: () => pending.promise}));
      const result = h.client.api.get('/api/league/season-projections').catch(error => error);
      await h.time.advance(30_000); assert.equal((await result).isTimeout, true);
      const count = h.requests.length; pending.resolve(phase === 'token' ? 'synthetic-token-a' : '{"status":"available"}'); await flush();
      assert.equal(h.requests.length, count, 'late preparation dispatched after timeout');
    }
  });
  await check('T7 gateway retries/backoff do not restart a 30-second logical GET', async () => {
    const h = transport(); let count = 0;
    h.setResponder(() => ++count === 1
      ? new Promise(resolve => h.time.setTimeout(() => resolve(response(503, {message: 'Synthetic unavailable'})), 29_500))
      : new Promise(() => {}));
    const result = h.client.api.get('/api/league/season-projections').catch(error => error);
    await h.time.advance(30_000); assert.equal((await result).isTimeout, true); assert.equal(h.events.length, 1);
    assert.ok(h.requests.length <= 2);
  });
  await check('T7 JS resume checks the deadline before late dispatch or verification publication', async () => {
    for (const phase of ['token', 'body']) {
      const h = transport(), pending = deferred(); let verified = 0;
      h.client.setOnVerificationRequired(() => { verified++; });
      if (phase === 'token') h.setTokenReader(() => pending.promise);
      else h.setResponder(() => ({status: 403, ok: false, text: () => pending.promise}));
      const result = h.client.api.get('/api/league/season-projections').catch(error => error);
      await flush(); h.time.suspend(30_001);
      pending.resolve(phase === 'token' ? 'synthetic-token-a' : '{"error":"verification_required"}'); await flush();
      assert.equal(phase === 'token' ? h.requests.length : verified, 0, `${phase} published after suspended deadline`);
      await h.time.advance(0); assert.equal((await result).isTimeout, true);
    }
  });
  await check('T8 current verification callback still updates the real store; stale callback does not', async () => {
    const h = sessionHarness(), pending = deferred();
    h.setResponder(() => pending.promise);
    const old = h.client.api.get('/api/ordinary').catch(error => error); await flush();
    await h.client.setSessionToken('synthetic-token-b');
    await h.state.useSession.getState().setUser({...h.user, user_id: 'synthetic-new-user'});
    const verified = {session_verified: true, user_verified: true, enforced: true};
    h.state.useSession.setState({verification: verified});
    pending.resolve(response(403, {error: 'verification_required'})); await old;
    assert.equal(h.state.useSession.getState().verification, verified);
    h.setResponder(() => response(403, {error: 'verification_required'})); await h.client.api.get('/api/ordinary').catch(() => {});
    assert.equal(h.state.useSession.getState().verification.session_verified, false);
  });
  await check('T8 old-league terminal errors remain silent while a new same-token selection is pending', async () => {
    for (const outcome of ['refusal', 'deadline']) {
      const h = sessionHarness(), pending = deferred();
      await h.state.initializeLeagueSession(h.user, {league_id: h.league.league_id, name: 'A'});
      h.setResponder(() => pending.promise);
      const result = h.state.loadSeasonProjections(h.league.league_id, new AbortController().signal).catch(error => error);
      await flush(); await h.state.beginLeagueContext(h.user, {league_id: 'synthetic-b', name: 'B'}, 'selection');
      if (outcome === 'refusal') pending.resolve(response(403, {error: 'verification_required'}));
      else await h.time.advance(30_000);
      assert.equal((await result).name, 'AbortError', `${outcome} leaked from obsolete league`);
      assert.equal(h.state.useSession.getState().verification, null);
      assert.equal(h.events.length, 0, 'superseded projection was reported as a request failure');
    }
  });
  await check('T8 only exact 409 repairs; refusals and source body remain authoritative', async () => {
    for (const [status, body] of [[200, {status: 'unavailable', reason: 'unsupported_source'}], [400, {error: 'invalid_request'}], [409, {error: 'other_conflict'}], [403, {error: 'verification_required'}], [404, {error: 'feature_disabled'}]]) {
      const h = sessionHarness();
      h.setResponder(url => url.endsWith('/api/session/init') ? response(200, {ok: true, token: 'synthetic-token-a'}) : response(status, body));
      const result = await h.state.loadSeasonProjections(h.league.league_id, new AbortController().signal).catch(error => error);
      assert.equal(initRequests(h).length, 1);
      assert.equal(status === 200 ? result.reason : result.status, status === 200 ? body.reason : status);
    }
  });
  await check('T8 stale 401 preserves new token; current 401 clears without init replay', async () => {
    const h = sessionHarness(), pending = deferred(); h.setResponder(() => pending.promise);
    const old = h.client.api.get('/api/ordinary').catch(error => error); await flush();
    await h.client.setSessionToken('synthetic-token-b'); pending.resolve(response(401, {error: 'session_expired'})); await old;
    assert.equal(await h.client.getSessionToken(), 'synthetic-token-b');
    h.setResponder(() => response(401, {error: 'session_expired'})); await h.client.api.get('/api/ordinary').catch(() => {});
    assert.equal(await h.client.getSessionToken(), null);
  });
  await check('T8 expired callback cannot follow a replacement token during secure deletion', async () => {
    const h = transport(), pending = deferred(); let expired = 0;
    h.client.setOnSessionExpired(() => { expired++; });
    h.setTokenDeleter(async () => { h.replaceToken(null); await pending.promise; });
    h.setResponder(() => response(401, {error: 'session_expired'}));
    const result = h.client.api.get('/api/ordinary').catch(error => error); await flush();
    await h.client.setSessionToken('synthetic-token-b'); pending.resolve(); await result;
    assert.equal(expired, 0, 'late expired callback affected replacement login');
    assert.equal(await h.client.getSessionToken(), 'synthetic-token-b');
  });
  await check('T3 cache-missing init retries once only and a refusal does not poison explicit retry', async () => {
    const h = sessionHarness(); let count = 0;
    h.setResponder(() => ++count === 1 ? response(400, {error: 'Player database not cached'}) : response(200, {ok: true, token: 'synthetic-token-a'}));
    await h.state.initializeLeagueSession(h.user, {league_id: h.league.league_id, name: 'A'});
    assert.equal(initRequests(h).length, 2); assert.equal(h.seeds.length, 1);
    h.setResponder(() => response(400, {error: 'Player database not cached'}));
    const failed = await h.state.initializeLeagueSession(h.user, {league_id: h.league.league_id, name: 'A'}, {force: true}).catch(error => error);
    assert.equal(failed.status, 400); assert.equal(initRequests(h).length, 4);
  });
  await check('T10 late verification replay cannot change a replacement session', async () => {
    const h = sessionHarness(), late = deferred(); let proofs = 0;
    h.providers.proof = () => ++proofs === 1 ? Promise.resolve('verified') : late.promise;
    h.setResponder(() => response(200, {ok: true, token: 'synthetic-token-a', verification: {session_verified: false, user_verified: false, enforced: false}}));
    const init = h.state.initializeLeagueSession(h.user, {league_id: h.league.league_id, name: 'A'});
    await h.time.advance(4_000); await init;
    await h.client.setSessionToken('synthetic-token-b');
    const verification = {session_verified: false, user_verified: true, enforced: true};
    h.state.useSession.setState({verification}); late.resolve('verified'); await flush();
    assert.equal(h.state.useSession.getState().verification, verification);
  });
  await check('T10 one 90-second attempt caps near-deadline repair/replay composition', async () => {
    const h = sessionHarness();
    h.providers.rosters = () => new Promise(resolve => h.time.setTimeout(() => resolve([]), 55_000));
    h.setResponder(url => url.endsWith('/api/session/init') ? response(200, {ok: true, token: 'synthetic-token-a'}) : response(409, {error: 'session_not_initialized'}));
    const result = h.state.loadSeasonProjections(h.league.league_id, new AbortController().signal).catch(error => error);
    await h.time.advance(90_000); assert.equal((await result).isTimeout, true);
    assert.equal(initRequests(h).length, 1, 'forced repair preparation must not dispatch within expired caller chain');
    await h.time.advance(60_000);
    assert.equal(initRequests(h).length, 1, 'late forced preparation must not dispatch after the whole attempt ended');
  });
  await check('T11 connect merges platform rows and seeds the same shared initialized league', async () => {
    const h = sessionHarness(); h.state.useSession.setState({leagues: [{league_id: 'platform-synthetic', name: 'Imported', platform: 'espn'}]});
    await h.state.useSession.getState().connectLeague('https://example.invalid/synthetic');
    assert.equal(h.state.useSession.getState().league.league_id, 'synthetic-b');
    assert.equal(h.state.useSession.getState().leagues.length, 2); assert.deepEqual(h.seeds.map(s => s.id), ['synthetic-b']);
  });
  await check('T10 a delayed Connect gesture cannot become new uncertainty authorization', async () => {
    const h = sessionHarness(), accepted = deferred(), target = deferred();
    h.setResponder(() => accepted.promise);
    const a = h.state.initializeLeagueSession(h.user, {league_id: 'synthetic-a', name: 'A'}).catch(error => error);
    await flush(); h.providers.connect = () => target.promise;
    const oldConnect = h.state.useSession.getState().connectLeague('synthetic-url').catch(error => error);
    await h.time.advance(30_000); await a;
    h.setResponder(() => response(200, {ok: true, token: 'synthetic-token-a'}));
    target.resolve({ok: true, league_id: 'synthetic-b', league_name: 'B'});
    const denied = await oldConnect;
    assert.equal(initRequests(h).length, 1, 'old Connect gesture silently authorized a retry');
    assert.equal(denied.body?.error, 'session_init_uncertain');
    await h.state.useSession.getState().connectLeague('synthetic-url');
    assert.equal(initRequests(h).length, 2); assert.equal(h.state.useSession.getState().league.league_id, 'synthetic-b');
  });
  await check('T10 Connect target preparation consumes its captured attempt deadline', async () => {
    const h = sessionHarness(), target = deferred(); h.providers.connect = () => target.promise;
    const result = h.state.useSession.getState().connectLeague('synthetic-url').catch(error => error);
    await h.time.advance(60_000);
    h.providers.rosters = () => new Promise(resolve => h.time.setTimeout(() => resolve([]), 40_000));
    target.resolve({ok: true, league_id: 'synthetic-b', league_name: 'B'}); await flush();
    let settled = false; result.then(() => { settled = true; });
    await h.time.advance(30_000);
    assert.equal(settled, true, 'Connect reset its deadline when the target became known');
    assert.equal((await result).isTimeout, true); assert.equal(initRequests(h).length, 0);
    await h.time.advance(20_000); assert.equal(initRequests(h).length, 0);
  });
  await check('T11 actual picker ends token/preparation timeout with an enabled retry', async () => {
    for (const phase of ['token', 'rosters']) {
      const h = sessionHarness(), pending = deferred(), screen = picker(h);
      if (phase === 'token') h.setTokenReader(() => pending.promise);
      else h.providers.rosters = () => pending.promise;
      const result = screen.invoke({league_id: 'synthetic-b', name: 'B'});
      await h.time.advance(90_000); await result;
      assert.equal(screen.ui.selecting, null, `${phase} timeout left picker busy`);
      assert.equal(screen.ui.error, 'This request took too long. Please try again.');
      assert.equal(screen.ui.navigated, 0); assert.equal(h.seeds.length, 0);
      pending.resolve(phase === 'token' ? 'synthetic-token-a' : []); await flush();
      assert.equal(initRequests(h).length, 0);
    }
  });
  await check('T11 automatic picker cannot clear a prior ambiguous init', async () => {
    const h = sessionHarness(), pending = deferred(); h.setResponder(() => pending.promise);
    const first = h.state.initializeLeagueSession(h.user, {league_id: 'synthetic-a', name: 'A'}).catch(error => error);
    await h.time.advance(30_000); await first;
    h.setResponder(() => response(200, {ok: true, token: 'synthetic-token-a'}));
    const count = initRequests(h).length, screen = picker(h);
    await screen.invoke({league_id: 'synthetic-a', name: 'A'}, {auto: true});
    assert.equal(initRequests(h).length, count, 'automatic picker restarted an uncertain writer');
    assert.equal(screen.ui.navigated, 0); assert.equal(screen.ui.selecting, null);
    assert.match(screen.ui.error, /could not be confirmed/);
  });
  await check('T11 actual ESPN resync ends the shared preparation deadline honestly', async () => {
    const h = sessionHarness(), pending = deferred(), ui = {busy: false, message: null, refreshed: 0};
    h.providers.rosters = () => pending.promise;
    const invoke = screenHandler('src/screens/LeagueScreen.tsx', 'resyncEspn', {
      ...h.state, user: h.user, leagueId: h.league.league_id, league: h.league, resyncing: false,
      tapAction: () => {}, setResyncing: value => { ui.busy = value; }, setResyncMsg: value => { ui.message = value; },
      setResyncAuthFail: () => {}, importEspnLeague: async () => ({teams_imported: 2}), ApiError: h.client.ApiError,
      refetchAll: () => { ui.refreshed++; },
    }, h.time);
    const result = invoke(); await h.time.advance(90_000); await result;
    assert.equal(ui.busy, false, 'expired context left resync busy');
    assert.equal(ui.message, 'This request took too long. Please try again.'); assert.equal(ui.refreshed, 0);
    pending.resolve([]); await flush(); assert.equal(initRequests(h).length, 0);
  });
  await check('T11 account-only real imported leagues keep their actual platform builders', async () => {
    for (const platform of ['espn', 'mfl', 'fleaflicker']) {
      const h = sessionHarness(); Object.assign(h.user, {user_id: 'acct_synthetic', account_only: true});
      h.state.useSession.setState({leagues: [{league_id: h.league.league_id, name: 'Imported', platform}]});
      h.providers.rosters = () => { throw Error('account-only identity reached Sleeper'); };
      h.providers.users = h.providers.rosters;
      h.setResponder(url => url.endsWith(`/api/${platform}/leagues`)
        ? response(200, {leagues: [{league_id: h.league.league_id, name: 'Imported', members: [{user_id: h.user.user_id, player_ids: ['synthetic-player']}]}]})
        : response(200, url.endsWith('/api/session/init') ? {ok: true, token: 'synthetic-token-a'} : {status: 'unavailable', reason: 'platform_not_supported'}));
      const screen = picker(h); await screen.invoke({league_id: h.league.league_id, name: 'Imported'});
      assert.equal(screen.ui.navigated, 1, `${platform} account-only picker was blocked`);
      assert.equal(initRequests(h).length, 1); assert.ok(h.requests.some(r => r.url.endsWith(`/api/${platform}/leagues`)));
      assert.equal(JSON.parse(initRequests(h)[0].opts.body).user_id, 'acct_synthetic');
      assert.equal((await h.state.loadSeasonProjections(h.league.league_id, new AbortController().signal)).reason, 'platform_not_supported');
    }
    const h = sessionHarness(); Object.assign(h.user, {account_only: true});
    h.state.useSession.setState({league: {league_id: 'no_league', league_name: 'None'}});
    await h.state.loadSeasonProjections('no_league', new AbortController().signal).catch(() => {});
    assert.equal(h.requests.length, 0);
  });
  await check('T12 caller abort is silent; background latency is omitted; event fields stay bounded', async () => {
    const h = transport(), caller = new AbortController();
    const canceled = h.client.api.get('/api/league/season-projections?league_id=private-not-reported', {signal: caller.signal}).catch(error => error);
    await flush(); caller.abort(); assert.equal((await canceled).name, 'AbortError'); assert.equal(h.events.length, 0);
    const failed = h.client.api.get('/api/league/season-projections?league_id=private-not-reported').catch(error => error);
    await flush(); h.background(); await h.time.advance(30_000); await failed;
    assert.equal(h.events.length, 1); const event = h.events[0].data;
    assert.equal(event.route, '/api/league/season-projections'); assert.equal(event.bg, true); assert.equal(event.timeout, true); assert.equal(event.ms, undefined);
    assert.deepEqual(Object.keys(event).sort(), ['bg', 'method', 'route', 'status', 'timeout']);
  });
  await check('T11/T12 every init writer uses shared state owner; no write recovery or upward client import', () => {
    const read = rel => fs.readFileSync(path.join(ROOT, rel), 'utf8');
    const state = read('src/state/useSession.ts'), api = read('src/api/auth.ts');
    assert.match(state, /initialize:\s*initLeagueSession/);
    assert.match(api, /sessionInit\(body: SessionInitBody, control: SessionInitControl\)/);
    for (const name of ['LeaguePickerScreen', 'LeagueScreen']) {
      const screen = read(`src/screens/${name}.tsx`);
      assert.match(screen, /const pending = beginLeagueContext\(/); assert.match(screen, /const context = await pending/);
      assert.match(screen, /await completeLeagueContext\(context/);
      assert.doesNotMatch(screen, /await (?:initLeagueSession|submitSessionInit)\(/);
    }
    const recovery = state.slice(state.indexOf('export function loadSeasonProjections('), state.indexOf('// ── Read-gate signal'));
    assert.doesNotMatch(recovery, /searchWinNow|evaluateWinNow|decideWinNow|api\.post/);
    assert.doesNotMatch(read('src/api/client.ts'), /(?:from|require\()\s*['"]\.\.\/state/);
  });
  console.log(`${passed} passed; ${failures} failed (native Win Now recovery)`);
  process.exitCode = failures ? 1 : 0;
}
main().catch(error => { console.error(error); process.exitCode = 1; });
