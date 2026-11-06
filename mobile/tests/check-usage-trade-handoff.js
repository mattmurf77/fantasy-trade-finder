#!/usr/bin/env node
// Execute the actual handlers with controlled native-dismissal and session promises.
// These are lifecycle/identity checks, not native frame-time measurements.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const ts = require('typescript');
const read = file => fs.readFileSync(path.join(__dirname, '../src', file), 'utf8');
const screen = read('screens/UsageTrendsScreen.tsx');
const ast = ts.createSourceFile('Usage.tsx', screen, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
function initializer(name) {
  let source;
  (function visit(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(ast) === name) source = node.initializer.getText(ast);
    ts.forEachChild(node, visit);
  })(ast);
  assert(source, name);
  return source;
}
function compile(source, env) {
  const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React } }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(js, { module, exports: module.exports, ...env });
  return module.exports;
}
function handler(name, env) { return compile('module.exports = ' + initializer(name), env); }
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; }
function fixture() {
  const dismissal = deferred(), switching = deferred();
  const state = { hasToken: true, switching: false, user: { user_id: 'u' }, league: { league_id: 'a' } };
  const calls = [], drops = [], pins = [], navigations = [], events = [], alerts = [];
  let revision = 1, focused = true;
  const env = {
    useSession: { getState: () => state },
    navigation: { isFocused: () => focused, navigate: (...a) => navigations.push(a) },
    tradeAction: { current: { serial: 0, searchId: null } },
    getSessionRevision: () => revision, trackAction: () => {},
    data: { leagues: [{ league_id: 'b', rosters: { p: 'owner' }, owners: { owner: 'Partner' } },
      { league_id: 'a', rosters: { p: 'owner' }, owners: { owner: 'Partner' } }] },
    beginTradeSearch: o => { events.push(o); calls.push('tap'); return 'search'; },
    handoffDeckMode: () => 'single_pin', dropPendingSearch: id => drops.push(id),
    closeTradeSheet: () => { calls.push('dismiss'); return dismissal.promise; },
    switchTo: id => { calls.push('switch:' + id); return switching.promise; },
    useFinderTargets: { getState: () => ({ setSide: (...a) => pins.push(a), setHandoff: o => pins.push(o) }) },
    Alert: { alert: (...a) => alerts.push(a) },
  };
  return { env, state, calls, drops, pins, navigations, events, alerts, dismissal, switching,
    rotate: () => revision++, blur: () => focused = false,
    run: target => handler('doTrade', env)({ player_id: 'p', name: 'Player', position: 'WR', team: 'BUF' }, target) };
}
let count = 0;
async function test(name, run) { await run(); count++; console.log('PASS ' + name); }
(async () => {
  await test('tap clock starts before parallel dismissal and switch; waits for both', async () => {
    const f = fixture(), work = f.run('b');
    assert.deepEqual(f.calls, ['tap', 'dismiss', 'switch:b']);
    assert.equal(f.events[0].scenario, 'cross_league_handoff');
    f.state.league.league_id = 'b'; f.switching.resolve(true);
    await Promise.resolve(); assert.equal(f.pins.length, 0);
    f.dismissal.resolve(); await work;
    assert.equal(f.pins.length, 3); assert.equal(f.pins[2].searchId, 'search');
    assert.equal(f.navigations.length, 1); assert.equal(f.drops.length, 0);
    assert.equal(f.env.tradeAction.current.searchId, null);
  });
  await test('same-league tap does not claim cross-league scenario', async () => {
    const f = fixture(), work = f.run('a');
    assert.equal(f.events[0].scenario, undefined);
    f.dismissal.resolve(); f.switching.resolve(true); await work;
    assert.equal(f.navigations.length, 1);
  });
  for (const [name, change] of [
    ['account replaced', f => { f.state.user = { user_id: 'other' }; }],
    ['signed out', f => { f.state.hasToken = false; }],
    ['token replaced for same account', f => f.rotate()],
    ['left screen', f => f.blur()],
    ['newer action', f => { f.env.tradeAction.current.serial++; }],
    ['switch did not commit target', f => { f.state.league.league_id = 'c'; }],
    ['another switch in progress', f => { f.state.switching = true; }],
  ]) await test(name + ' cannot write pins or navigate', async () => {
    const f = fixture(), work = f.run('b'); f.state.league.league_id = 'b'; change(f);
    f.dismissal.resolve(); f.switching.resolve(true); await work;
    assert.equal(f.pins.length, 0); assert.equal(f.navigations.length, 0); assert.deepEqual(f.drops, ['search']);
  });
  await test('failed switch reports after dismissal and abandons original trace', async () => {
    const f = fixture(), work = f.run('b'); f.switching.resolve(false);
    await Promise.resolve(); assert.equal(f.alerts.length, 0);
    f.dismissal.resolve(); await work;
    assert.equal(f.alerts.length, 1); assert.equal(f.pins.length, 0); assert.deepEqual(f.drops, ['search']);
  });
  await test('matching active league cannot replace failed switch acknowledgement', async () => {
    const f = fixture(), work = f.run('b'); f.state.league.league_id = 'b';
    f.dismissal.resolve(); f.switching.resolve(false); await work;
    assert.equal(f.pins.length, 0); assert.equal(f.navigations.length, 0); assert.deepEqual(f.drops, ['search']);
  });
  for (const unavailable of ['user', 'hasToken', 'switching', 'focus']) await test('does not start unactionable tap: ' + unavailable, async () => {
    const f = fixture();
    if (unavailable === 'user') f.state.user = null;
    if (unavailable === 'hasToken') f.state.hasToken = false;
    if (unavailable === 'switching') f.state.switching = true;
    if (unavailable === 'focus') f.blur();
    await f.run('b'); assert.equal(f.calls.length, 0);
  });
  await test('unknown owner opens builder without creating a false search trace', async () => {
    const f = fixture(); f.env.data.leagues[0].rosters.p = 'roster:3';
    const work = f.run('b'); f.state.league.league_id = 'b';
    f.dismissal.resolve(); f.switching.resolve(true); await work;
    assert.equal(f.events.length, 0); assert.equal(f.pins[2].searchId, undefined);
    assert.equal(f.pins[2].opponent, null); assert.equal(f.navigations.length, 1);
  });
  await test('native dismissal resolves only on completion and is shared by concurrent callers', async () => {
    const env = { sheetDismissal: { current: null }, sheetPlayer: {}, setTradeSheetClosing: v => env.closing = v,
      setSheetPlayer: v => env.sheetPlayer = v };
    const close = handler('closeTradeSheet', env), done = handler('onTradeSheetDismissed', env);
    const first = close(); assert.equal(first, close()); assert.equal(env.closing, true);
    let settled = false; first.then(() => settled = true);
    await Promise.resolve(); assert.equal(settled, false);
    done(); await first; assert.equal(settled, true); assert.equal(env.sheetPlayer, null);
    assert.equal(env.closing, false); assert.equal(env.sheetDismissal.current, null);
  });
  await test('no-sheet path resolves without a presentation delay', async () => {
    const env = { sheetDismissal: { current: null }, sheetPlayer: null, setTradeSheetClosing: () => { throw Error('should not close'); } };
    await handler('closeTradeSheet', env)();
  });
  await test('switch no-op is never assumed successful when target was not committed', async () => {
    const state = { hasToken: true, switching: false, user: { user_id: 'u' }, league: { league_id: 'a' },
      leagues: [{ league_id: 'b', name: 'B' }], switchLeague: async () => {} };
    const env = { useSession: { getState: () => state }, Alert: { alert: () => {} } };
    assert.equal(await handler('switchTo', env)('b', true), false);
    state.switchLeague = async () => { state.league.league_id = 'b'; };
    assert.equal(await handler('switchTo', env)('b', true), true);
  });
  await test('sheet uses native completion on iOS, committed hidden state elsewhere, and no Trade timer', () => {
    const component = read('components/UsageLeagueList.tsx');
    assert.match(component, /onDismiss=\{onDismiss\}/);
    assert.match(component, /animationType=\{immediateDismiss \? 'none' : 'slide'\}/);
    assert.match(component, /!visible && immediateDismiss && Platform\.OS !== 'ios'/);
    assert.doesNotMatch(initializer('doTrade'), /setTimeout|closeSheetFirst/);
    assert.match(initializer('closeSheetFirst'), /setTimeout\(r, 450\)/); // Add's modal safety retained.
  });
  for (const os of ['ios', 'android']) await test(os + ' sheet completes through its real platform callback', () => {
    const source = read('components/UsageLeagueList.tsx');
    const file = ts.createSourceFile('Sheet.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    let fn;
    (function visit(node) {
      if (ts.isFunctionDeclaration(node) && node.name?.text === 'UsageAvailabilitySheet') fn = node.getText(file).replace('export ', '');
      ts.forEachChild(node, visit);
    })(file);
    const effects = [], React = { createElement: (tag, props, ...children) => ({ tag, props, children }) };
    const env = { React, useEffect: f => effects.push(f), Platform: { OS: os }, styles: {}, type: {}, chalk: {},
      Modal: 'Modal', Pressable: 'Pressable', View: 'View', SafeAreaView: 'SafeAreaView', ScrollView: 'ScrollView',
      Text: 'Text', Icon: 'Icon', TickLabel: 'TickLabel', PositionBadge: 'PositionBadge', UsageLeagueList: 'UsageLeagueList' };
    const render = compile(fn + '; module.exports = UsageAvailabilitySheet;', env);
    let count = 0;
    const modal = render({ player: {}, rows: [], visible: false, immediateDismiss: true,
      onClose: () => {}, onDismiss: () => count++ });
    assert.equal(modal.tag, 'Modal'); assert.equal(modal.props.visible, false); assert.equal(modal.props.animationType, 'none');
    effects.forEach(f => f());
    assert.equal(count, os === 'ios' ? 0 : 1);
    if (os === 'ios') { modal.props.onDismiss(); assert.equal(count, 1); }
  });
  await test('explicit tap scenario is not overwritten or assigned an unrelated input age', () => {
    const events = read('api/events.ts');
    const start = events.indexOf("if (eventType === 'find_trades_tapped')");
    const end = events.indexOf('if (!flagEnabled())', start);
    const block = events.slice(start, end);
    const run = compile(`module.exports = props => { const eventType = 'find_trades_tapped'; ${block}; return props; };`, {
      Constants: { platform: { ios: { buildNumber: 'candidate' } } },
      takeTradeInputChange: () => ({ scenario: 'after_preferences_change', input_age_ms: 12 }),
    });
    assert.deepEqual(JSON.parse(JSON.stringify(run({ scenario: 'cross_league_handoff' }))), { scenario: 'cross_league_handoff', client_build: 'candidate' });
    assert.equal(run({}).input_age_ms, 12);
  });
  console.log(`${count} lifecycle checks passed; physical-device latency remains unmeasured.`);
})().catch(error => { console.error(error); process.exit(1); });
