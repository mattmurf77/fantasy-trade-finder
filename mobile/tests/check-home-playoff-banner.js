'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const read = file => fs.readFileSync(path.join(__dirname, '..', file), 'utf8');
const compiled = {};
vm.runInNewContext(ts.transpileModule(read('src/utils/homePlayoffBanner.ts'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, { exports: compiled });
const model = compiled.homePlayoffBanner;
const now = Date.parse('2026-11-07T15:00:00Z');
function data(probability = .8, state = 'current') {
  return { state, next_attempt_not_before: '2026-11-10T14:30:00Z', run: {
    status: 'complete', result: { captured_at: '2026-11-07T14:00:00Z', coverage: { estimated: true },
      teams: [{ roster_id: 1, playoff_probability: .99 }, { roster_id: 2, playoff_probability: probability }] },
  } };
}
const sides = result => Array.from(result.sides);
assert.deepEqual(sides(model(data(.65), 2, false, now)), ['buy']);
assert.deepEqual(sides(model(data(.35), 2, false, now)), ['buy', 'sell']);
assert.deepEqual(sides(model(data(.34999), 2, false, now)), ['sell']);
assert.deepEqual(sides(model(data(.64999), 2, false, now)), ['buy', 'sell']);
assert.deepEqual(sides(model(data(0), 2, false, now)), ['sell']);
assert.deepEqual(sides(model(data(1), 2, false, now)), ['buy']);
assert.equal(model(data(0), 2, false, now).probability, 0);
assert.equal(model(data(.2), 2, false, now).probability, .2); // Never first/other roster.
for (const invalid of [null, undefined, NaN, Infinity, -.01, 1.01, '0.8']) {
  const result = model(data(invalid), 2, false, now);
  // Undefined is an explicit malformed field rather than the fixture default.
  if (invalid === undefined) {
    const missing = data(); delete missing.run.result.teams[1].playoff_probability;
    assert.equal(model(missing, 2, false, now).probability, null);
  } else {
    assert.equal(result.probability, null); assert.deepEqual(sides(result), []);
  }
}
for (const state of ['no_run', 'queued', 'running', 'stale', 'refresh_failed', 'failed', 'unsupported_policy']) {
  const result = model(data(.9, state), 2, false, now);
  assert.equal(result.current, false); assert.deepEqual(sides(result), []);
}
for (const roster of [null, 99]) assert.equal(model(data(), roster, false, now).probability, null);
assert.equal(model(undefined, 2, false, now).probability, null);
assert.deepEqual(sides(model(data(), 2, true, now)), []);
const expired = data(); expired.next_attempt_not_before = '2026-11-07T15:00:00Z';
assert.equal(model(expired, 2, false, now).current, false);
const future = data(); future.run.result.captured_at = '2026-11-08T15:00:00Z';
assert.equal(model(future, 2, false, now).probability, null);
const invalidDate = data(); invalidDate.next_attempt_not_before = null;
assert.equal(model(invalidDate, 2, false, now).current, false);
const unfinished = data(); unfinished.run.status = 'running';
assert.equal(model(unfinished, 2, false, now).probability, null);
assert.equal(model(data(), 2, false, now).partial, true);

const component = read('src/components/home/HomePlayoffBanner.tsx');
const hub = read('src/components/home/HomeHub.tsx');
assert(component.includes("['league-projection-batch', userId, leagueId]"));
assert(component.includes('hasToken && !switching'));
assert(component.includes('if (!available) return null'));
assert(component.includes("platform === 'sleeper'"));
assert(!component.includes('placeholderData'));
assert(!/queueLeague|projection-runs.*POST|getOutlook|generateTrade/.test(component));
assert(component.includes('view.probability != null'));
assert(component.includes('last saved estimate'));
assert(hub.includes('key={`${user?.user_id}:${leagueId}`}'));
assert(hub.includes('findMyRoster(rostersQuery.data, user?.user_id'));
assert(hub.includes('onBuy(splits.find(s => s.position === position)!)'));
assert(hub.includes('onSell(splits.find(s => s.position === position)!)'));
assert(hub.includes('onDetails={onStandings}'));
// Execute the actual component with host/query stubs: exercise its action flow
// without a simulator, network, account mutation or forecast generation.
let selected = null;
let active = { user: { user_id: 'viewer' }, league: { league_id: 'league-a' },
  leagues: [{ league_id: 'league-a', platform: 'sleeper' }], hasToken: true, switching: false };
let queryData = data(.8);
let queryError = false;
let options;
const presses = [];
const React = { createElement: (type, props, ...children) => ({ type, props: props || {}, children }) };
const modules = {
  react: { __esModule: true, default: React, useState: () => [selected, value => { selected = value; }] },
  'react-native': { Pressable: 'Pressable', StyleSheet: { create: value => value }, View: 'View' },
  '@tanstack/react-query': { useQuery: value => { options = value; return { data: queryData, isError: queryError, isLoading: false }; } },
  '../chalkline': Object.fromEntries(['Button', 'Card', 'Icon', 'Text'].map(k => [k, k])),
  '../../theme/chalkline': { chalk: { dim: 'dim' }, space: { xs: 4, sm: 8, lg: 16 } },
  '../../api/leagueProjections': { getLeagueProjectionBatch: () => { throw new Error('Render must not fetch directly'); } },
  '../../state/useSession': { NO_LEAGUE_ID: 'no_league', useSession: select => select(active) },
  '../../state/useFeatureFlags': { useFlag: () => true },
  '../../utils/homePlayoffBanner': { homePlayoffBanner: (value, roster, failed) => model(value, roster, failed, now) },
  '../../utils/positionSplit': { SPLIT_POSITIONS: ['QB', 'RB', 'WR', 'TE'] },
};
const componentExports = {};
vm.runInNewContext(ts.transpileModule(component, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React,
} }).outputText, { exports: componentExports, require: name => {
  assert(name in modules, `Unexpected component dependency: ${name}`); return modules[name];
} });
const props = { rosterId: 2, onBuy: p => presses.push(`buy:${p}`), onSell: p => presses.push(`sell:${p}`), onDetails: () => presses.push('details') };
const render = () => componentExports.default(props);
const nodes = node => Array.isArray(node) ? node.flatMap(nodes) : node && typeof node === 'object' ? [node, ...nodes(node.children)] : [];
const button = (tree, id) => nodes(tree).find(n => n.props?.testID === id);
let tree = render();
assert.deepEqual(Array.from(options.queryKey), ['league-projection-batch', 'viewer', 'league-a']);
assert.match(button(tree, 'home.playoff.details').props.accessibilityLabel, /Projected Season Finish.*80\.0%.*Partial data.*View standings/);
assert.equal(button(tree, 'home.playoff.positions'), undefined);
button(tree, 'home.playoff.buy').props.onPress();
tree = render(); button(tree, 'home.playoff.position.RB').props.onPress();
assert.deepEqual(presses, ['buy:RB']); assert.equal(selected, null);
queryData = data(.1); tree = render(); button(tree, 'home.playoff.sell').props.onPress();
tree = render(); button(tree, 'home.playoff.position.WR').props.onPress();
assert.deepEqual(presses, ['buy:RB', 'sell:WR']);
selected = 'sell'; queryData = data(.1, 'stale'); tree = render();
assert.match(button(tree, 'home.playoff.details').props.accessibilityLabel, /10\.0% last saved estimate/);
assert.equal(button(tree, 'home.playoff.sell'), undefined);
assert.equal(button(tree, 'home.playoff.positions'), undefined);
button(tree, 'home.playoff.details').props.onPress(); assert.equal(presses.at(-1), 'details');
queryData = data(.8); queryError = true; tree = render();
assert.equal(button(tree, 'home.playoff.buy'), undefined);
active.switching = true; assert.equal(render(), null); assert.equal(options.enabled, false);
active.switching = false; active.hasToken = false; assert.equal(render(), null);
active.hasToken = true; active.leagues[0].platform = 'espn'; assert.equal(render(), null);
console.log('Home playoff banner: boundary, missing/stale/error, own-roster, scope and read-only handoff checks passed');
