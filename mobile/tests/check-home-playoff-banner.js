'use strict';
// Home's playoff tile: the pure util is executed, and the real component is
// rendered against host stubs (no simulator, network or account write).
//   A  what counts as a current estimate (stale, old model, expired, failed)
//   B  incomplete estimates
//   C  the outlook recommendation is the server's, shown only when it is
//      available AND differs; the client never classifies a probability
//   D  the compact row: the percentage and a trailing "View" link (the
//      status rows' own RowAction) both open the projections; no Buy / Sell
//   E  the explanation toggle
//   F  "Review outlook" calls the handler and writes nothing
//   G  the server's suggestion sentence renders in the expanded explanation,
//      above the explanation sentence, exactly when "Consider" shows
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const read = file => fs.readFileSync(path.join(__dirname, '..', file), 'utf8');
const compiled = {};
const utilSource = read('src/utils/homePlayoffBanner.ts');
vm.runInNewContext(ts.transpileModule(utilSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, { exports: compiled });
const model = compiled.homePlayoffBanner;
const now = Date.parse('2026-11-07T15:00:00Z');
function data(probability = .8, state = 'current') {
  return { state, model_current: true, next_attempt_not_before: '2026-11-10T14:30:00Z', run: {
    status: 'complete', result: { captured_at: '2026-11-07T14:00:00Z', coverage: { estimate_status: 'complete' },
      teams: [{ roster_id: 1, playoff_probability: .99 }, { roster_id: 2, playoff_probability: probability }] },
  } };
}
function recommended(outlook, extra = {}) {
  return { status: 'available', reason: null, playoff_probability: .8, recommended_outlook: outlook,
    current_outlook: 'rebuilder', differs: true, suggestion: 'Consider trades that improve your current starting lineup.',
    explanation: 'An 80.0% playoff chance is in the Contending range.', captured_at: '2026-11-07T14:00:00Z', ...extra };
}
const withRec = (rec, probability = .8, state = 'current') => ({ ...data(probability, state), outlook_recommendation: rec });

// ── A. current / stale / old model ────────────────────────────────────────
assert.equal(model(data(), 2, false, now).current, true);
assert.equal(model(data(), 2, false, now).status, '');
assert.equal(model(data(0), 2, false, now).probability, 0);
assert.equal(model(data(.2), 2, false, now).probability, .2); // Never first/other roster.
for (const invalid of [null, NaN, Infinity, -.01, 1.01, '0.8']) {
  const result = model(data(invalid), 2, false, now);
  assert.equal(result.probability, null); assert.equal(result.current, false);
}
const missing = data(); delete missing.run.result.teams[1].playoff_probability;
assert.equal(model(missing, 2, false, now).probability, null);
for (const state of ['no_run', 'queued', 'running', 'stale', 'refresh_failed', 'failed', 'unsupported_policy']) {
  const result = model(data(.9, state), 2, false, now);
  assert.equal(result.current, false);
  assert.equal(result.probability, .9); // The last saved number stays.
}
assert.equal(model(data(.9, 'stale'), 2, false, now).status, 'Update due');
assert.equal(model(data(.9, 'queued'), 2, false, now).status, 'Update pending');
assert.equal(model(data(.9, 'refresh_failed'), 2, false, now).status, 'Update failed');
assert.equal(model(data(.9, 'incomplete_projections'), 2, false, now).status, 'League data incomplete');
assert.equal(model(data(.9, 'unsupported_policy'), 2, false, now).status, 'League rules unsupported');
for (const roster of [null, 99]) assert.equal(model(data(), roster, false, now).probability, null);
assert.equal(model(undefined, 2, false, now).probability, null);
assert.equal(model(undefined, 2, false, now).status, 'First forecast pending');
assert.equal(model(data(), 2, true, now).current, false);
assert.equal(model(data(), 2, true, now).status, 'Update unavailable');
// The local weekly-expiry guard: current strictly before the next attempt.
const lastMs = data(); lastMs.next_attempt_not_before = '2026-11-07T15:00:00.001Z';
assert.equal(model(lastMs, 2, false, now).current, true);
const expired = data(); expired.next_attempt_not_before = '2026-11-07T15:00:00Z';
assert.equal(model(expired, 2, false, now).current, false);
assert.equal(model(expired, 2, false, now).status, 'Update due');
const future = data(); future.run.result.captured_at = '2026-11-08T15:00:00Z';
assert.equal(model(future, 2, false, now).probability, null);
const invalidDate = data(); invalidDate.next_attempt_not_before = null;
assert.equal(model(invalidDate, 2, false, now).current, false);
const unfinished = data(); unfinished.run.status = 'running';
assert.equal(model(unfinished, 2, false, now).probability, null);
// A run saved by an older model is last saved, never current — even when
// every other field says current. A missing field (older server) is current.
const oldModel = data(); oldModel.model_current = false;
assert.equal(model(oldModel, 2, false, now).current, false);
assert.equal(model(oldModel, 2, false, now).probability, .8);
assert.equal(model(oldModel, 2, false, now).status, 'From an earlier forecast model');
const oldModelQueued = data(.8, 'queued'); oldModelQueued.model_current = false;
assert.equal(model(oldModelQueued, 2, false, now).status, 'Update pending');
const noField = data(); delete noField.model_current;
assert.equal(model(noField, 2, false, now).current, true);

// ── B. incomplete ─────────────────────────────────────────────────────────
assert.equal(model(data(), 2, false, now).incomplete, false);
const incomplete = data(); incomplete.run.result.coverage = { estimate_status: 'incomplete', missing_lineup_slots: 3 };
assert.equal(model(incomplete, 2, false, now).incomplete, true);
const noCoverage = data(); delete noCoverage.run.result.coverage;
assert.equal(model(noCoverage, 2, false, now).incomplete, false);
assert.equal(model(data(), 99, false, now).incomplete, false); // No estimate, nothing to qualify.

// ── C. recommendation: available && differs, and only then ────────────────
const plain = value => JSON.parse(JSON.stringify(value));
assert.deepEqual(plain(model(withRec(recommended('contender')), 2, false, now).recommendation),
  { outlook: 'contender', probability: .8, suggestion: 'Consider trades that improve your current starting lineup.' });
assert.equal(model(data(), 2, false, now).recommendation, null); // Block absent (flag off server-side).
assert.equal(model(withRec(recommended('contender', { differs: false })), 2, false, now).recommendation, null);
assert.equal(model(withRec(recommended('contender', { status: 'unavailable' })), 2, false, now).recommendation, null);
assert.equal(model(withRec(recommended(null)), 2, false, now).recommendation, null);
// Not current on this client ⇒ no recommendation, whatever the block says.
assert.equal(model(withRec(recommended('contender')), 2, true, now).recommendation, null);
assert.equal(model(withRec(recommended('contender'), .8, 'stale'), 2, false, now).recommendation, null);
assert.equal(model({ ...expired, outlook_recommendation: recommended('contender') }, 2, false, now).recommendation, null);
assert.equal(model({ ...oldModel, outlook_recommendation: recommended('contender') }, 2, false, now).recommendation, null);
// The client never classifies and never rounds: whatever outlook the server
// names passes through at any probability, with the unrounded number.
for (const [probability, outlook] of [[.99, 'jets'], [.01, 'championship'], [.6499999, 'contender'], [.65, 'rebuilder']]) {
  const result = model(withRec(recommended(outlook, { playoff_probability: probability }), probability), 2, false, now);
  assert.equal(result.recommendation.outlook, outlook);
  assert.equal(result.recommendation.probability, probability);
}
assert(!/>=|<=|\.65|\.35|0\.\d|toFixed|Math\.round/.test(utilSource.replace(/value >= 0 && value <= 1/, '').replace(/captured <= now/, '')),
  'the util holds no band threshold and does no rounding');
// The server's sentence: shown for a live suggestion or a stated absence,
// withheld when it would explain a suggestion this client is not showing.
assert.equal(model(withRec(recommended('contender')), 2, false, now).explanation, 'An 80.0% playoff chance is in the Contending range.');
assert.equal(model(withRec(recommended('contender', { differs: false })), 2, false, now).explanation, 'An 80.0% playoff chance is in the Contending range.');
assert.equal(model(withRec(recommended(null, { status: 'unavailable', explanation: 'No suggestion: the forecast is incomplete.' }), .8, 'stale'), 2, false, now).explanation,
  'No suggestion: the forecast is incomplete.');
assert.equal(model(withRec(recommended('contender'), .8, 'stale'), 2, false, now).explanation, null);
assert.equal(model(data(), 2, false, now).explanation, null);
assert.equal('sides' in model(data(), 2, false, now), false);
assert.equal('partial' in model(data(), 2, false, now), false);

// ── D–F. the component ────────────────────────────────────────────────────
const component = read('src/components/home/HomePlayoffBanner.tsx');
const hub = read('src/components/home/HomeHub.tsx');
assert(component.includes("['league-projection-batch', userId, leagueId]"));
assert(component.includes('hasToken && !switching'));
assert(component.includes('if (!available) return null'));
assert(component.includes("platform === 'sleeper'"));
assert(component.includes("useFlag('league.projection_outlook')"));
assert(!component.includes('placeholderData'));
// Read-only: nothing here can start a forecast or write a preference.
assert(!/queueLeague|projection-runs|api\.post|saveLeaguePreferences|setAssetPref|useMutation|getOutlook|generateTrade/.test(component));
// D — no Buy / Sell, no "Weekly", no "Partial data".
for (const gone of ['home.playoff.buy', 'home.playoff.sell', 'home.playoff.position', 'Buy a player', 'Sell a player',
  'onBuy', 'onSell', 'PlayoffTradeSide', 'SPLIT_POSITIONS', 'Partial data', 'Projected Season Finish']) {
  assert(!component.includes(gone) && !utilSource.includes(gone), `${gone} is gone from the playoff tile`);
}
assert(!/\bWeekly\b/.test(component) && !/\bWeekly\b/.test(utilSource), 'the word "Weekly" is gone');
// D — the "View" link is the status rows' own affordance, not a new look:
// one shared RowAction, drawn by StatusRow's ready state and by this tile.
const statusRow = read('src/components/home/StatusRow.tsx');
assert(component.includes("import { RowAction } from './StatusRow';"), 'the tile draws "View" with StatusRow\'s RowAction');
assert(/export function RowAction\(\{ label \}: \{ label: string \}\)/.test(statusRow)
  && /<Text style=\{styles\.goText\}>\{label\}<\/Text>\s*<Icon name="chevron-right" size=\{14\} \/>/.test(statusRow)
  && /state === 'unavailable' \? null : \(\s*<RowAction label=\{action\} \/>/.test(statusRow),
  'StatusRow\'s ready-state "View ›" is that same RowAction');
assert(!/chevron-right|goText/.test(component), 'the tile defines no View/chevron look of its own');
assert(hub.includes('key={`${user?.user_id}:${leagueId}`}'));
assert(hub.includes('findMyRoster(rostersQuery.data, user?.user_id'));
const mount = (/<HomePlayoffBanner[\s\S]*?\/>/.exec(hub) || [''])[0];
assert(mount.includes('onDetails={onProjections}') && mount.includes('onReviewOutlook={onReviewOutlook}'));
assert(!/onBuy=|onSell=/.test(mount));
// F (hub half) — the handler tracks the existing event, navigates to the
// existing selector with the suggestion, and does nothing else.
const reviewAt = hub.indexOf('const onReviewOutlook = (');
const review = hub.slice(reviewAt, hub.indexOf('\n  };', reviewAt));
assert(reviewAt >= 0);
assert.deepEqual(review.split('\n').slice(1).map(line => line.trim()), [
  "track('home_tile_tapped', { tile: 'outlook' }, 'Home');",
  "navigation.navigate('Trades', { screen: 'TradesHome', params: { mode: 'guided', editDna: true, suggestOutlook: recommended } });",
]);
assert(!/saveLeaguePreferences|setAssetPref|useMutation/.test(hub), 'Home writes no preference');

let open = false;
let active = { user: { user_id: 'viewer' }, league: { league_id: 'league-a' },
  leagues: [{ league_id: 'league-a', platform: 'sleeper' }], hasToken: true, switching: false };
let queryData = data(.8);
let queryError = false;
let queryLoading = false;
let flags = { 'league.projections': true, 'league.projection_outlook': true };
let options;
const calls = [];
const React = { Fragment: 'Fragment', createElement: (type, props, ...children) => ({ type, props: props || {}, children }) };
const NAMES = { championship: 'All-in', contender: 'Contending', rebuilder: 'Rebuilding', jets: 'Tanking' };
const receipt = read('src/components/OutlookBiasReceipt.tsx');
for (const [key, name] of Object.entries(NAMES)) assert(new RegExp(`${key}: \\{ lean: '[^']*', name: '${name}' \\}`).test(receipt));
const token = new Proxy({}, { get: (_, key) => new Proxy({}, { get: (__, inner) => `${String(key)}.${String(inner)}` }) });
const modules = {
  react: { __esModule: true, default: React, useState: () => [open, value => { open = typeof value === 'function' ? value(open) : value; }] },
  'react-native': { Pressable: 'Pressable', StyleSheet: { create: value => value }, View: 'View' },
  '@tanstack/react-query': { useQuery: value => { options = value; return { data: queryData, isError: queryError, isLoading: queryLoading }; } },
  '../chalkline': { Icon: 'Icon', Text: 'Text' },
  '../../theme/chalkline': token,
  '../../api/leagueProjections': { getLeagueProjectionBatch: () => { throw new Error('Render must not fetch directly'); } },
  '../../state/useSession': { NO_LEAGUE_ID: 'no_league', useSession: select => select(active) },
  '../../state/useFeatureFlags': { useFlag: name => { assert(name in flags, `Unexpected flag: ${name}`); return flags[name]; } },
  '../../utils/homePlayoffBanner': { homePlayoffBanner: (value, roster, failed) => model(value, roster, failed, now) },
  '../OutlookBiasReceipt': { outlookDisplayName: value => (value ? NAMES[value] ?? null : null) },
  './StatusRow': { RowAction: 'RowAction' },
};
const componentExports = {};
vm.runInNewContext(ts.transpileModule(component, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React,
} }).outputText, { exports: componentExports, require: name => {
  assert(name in modules, `Unexpected component dependency: ${name}`); return modules[name];
} });
const props = { rosterId: 2, onDetails: () => calls.push('details'), onReviewOutlook: outlook => calls.push(`review:${outlook}`) };
const render = () => componentExports.default(props);
const nodes = node => Array.isArray(node) ? node.flatMap(nodes) : node && typeof node === 'object' ? [node, ...nodes(node.children)] : [];
const byId = (tree, id) => nodes(tree).find(n => n.props?.testID === id);
const words = node => Array.isArray(node) ? node.flatMap(words) : typeof node === 'string' ? [node]
  : node && typeof node === 'object' ? words(node.children) : [];
// The "View" link: present in EVERY rendered state, last in the first row
// (after the info button), the status rows' RowAction, a 44pt target, and
// the very same callback as the percentage.
function assertViewLink(tree) {
  const viewLink = byId(tree, 'home.playoff.view');
  assert(viewLink, 'the View link renders');
  assert.equal(viewLink.type, 'Pressable');
  assert.equal(viewLink.props.accessibilityRole, 'link');
  assert.equal(viewLink.props.accessibilityLabel, 'View full projections');
  assert.equal(viewLink.props.onPress, props.onDetails, 'View calls the same callback as the percentage');
  const action = nodes(viewLink.children).filter(n => n.type === 'RowAction');
  assert.equal(action.length, 1); assert.equal(action[0].props.label, 'View');
  const firstRow = tree.children.find(n => n && n.type === 'View');
  const rowIds = firstRow.children.flat().filter(n => n && typeof n === 'object').map(n => n.props.testID);
  assert.deepEqual(rowIds.slice(-2), ['home.playoff.explain', 'home.playoff.view'], 'info, then View, end the row');
  const slop = viewLink.props.hitSlop;
  assert(viewLink.props.style.minHeight + slop.top + slop.bottom >= 44, 'the View link has a 44pt-tall hit area');
  assert.equal(viewLink.props.style.flexShrink, 0, 'the View link never shrinks');
}

// D — current estimate: one compact row whose percentage is the link.
let tree = render();
assert.deepEqual(Array.from(options.queryKey), ['league-projection-batch', 'viewer', 'league-a']);
assert(words(tree).includes('Playoff chance'));
let link = byId(tree, 'home.playoff.details');
assert.equal(link.type, 'Pressable');
assert.equal(link.props.accessibilityRole, 'link');
assert.deepEqual(words(link), ['80.0%']);
assert.equal(link.props.accessibilityLabel, '80.0% playoff chance. View projected standings.');
assert(link.props.hitSlop.top + link.props.hitSlop.bottom + 20 >= 44, 'the link has a 44pt hit area');
link.props.onPress(); assert.deepEqual(calls, ['details']);
assertViewLink(tree);
byId(tree, 'home.playoff.view').props.onPress(); assert.deepEqual(calls, ['details', 'details']);
assert.equal(byId(tree, 'home.playoff.status'), undefined);
assert(!words(tree).includes('last saved'));
assert.equal(byId(tree, 'home.playoff.recommendation'), undefined); // No block in this payload.
// Not current: the last saved percentage is still the link, marked, undated.
for (const [state, failed, old] of [['stale', false, false], ['refresh_failed', false, false], ['current', true, false], ['current', false, true]]) {
  queryData = data(.1, state); queryData.model_current = !old; queryError = failed; tree = render();
  link = byId(tree, 'home.playoff.details');
  assert.deepEqual(words(link), ['10.0%']);
  assert.equal(link.props.accessibilityRole, 'link');
  assert.equal(link.props.accessibilityLabel, '10.0% playoff chance, last saved. View projected standings.');
  assertViewLink(tree);
  assert(words(tree).includes('last saved'));
  assert(!words(tree).some(word => /Nov|11\/|2026/.test(word)), 'the date stays behind the tap');
}
queryError = false;
// No estimate: a plain status, not a link.
for (const [value, state, text] of [[null, 'no_run', 'First forecast pending'], [null, 'queued', 'Update pending'],
  [null, 'incomplete_projections', 'League data incomplete'], [null, 'unsupported_policy', 'League rules unsupported']]) {
  queryData = data(value, state); tree = render();
  assert.equal(byId(tree, 'home.playoff.details'), undefined);
  assert.deepEqual(words(byId(tree, 'home.playoff.status')), [text]);
  assert.equal(byId(tree, 'home.playoff.status').props.onPress, undefined);
  assertViewLink(tree); // The projected page has its own states.
}
queryData = undefined; queryError = true; tree = render();
assert.deepEqual(words(byId(tree, 'home.playoff.status')), ['Update unavailable']);
assertViewLink(tree);
queryError = false; queryLoading = true; tree = render();
assert.deepEqual(words(byId(tree, 'home.playoff.status')), ['Loading forecast…']);
assertViewLink(tree);
queryLoading = false;

// E — the explanation toggle.
const DEFINITION = 'Share of simulated seasons in which your team makes the playoffs, from projected weekly lineups. Updated weekly.';
queryData = data(.8); tree = render();
let toggle = byId(tree, 'home.playoff.explain');
assert.equal(toggle.type, 'Pressable');
assert.equal(toggle.props.accessibilityRole, 'button');
assert.equal(toggle.props['aria-expanded'], false);
assert(toggle.props.accessibilityLabel);
assert.equal(byId(tree, 'home.playoff.explanation'), undefined);
toggle.props.onPress(); tree = render();
assert.equal(byId(tree, 'home.playoff.explain').props['aria-expanded'], true);
assert.deepEqual(words(byId(tree, 'home.playoff.explanation')), [DEFINITION]);
queryData = data(.8, 'stale'); tree = render();
let lines = words(byId(tree, 'home.playoff.explanation'));
assert.equal(lines.length, 2);
assert.match(lines[1], /^Last saved \S.*\. Update due\.$/);
queryData = data(.8); queryData.model_current = false; tree = render();
assert.match(words(byId(tree, 'home.playoff.explanation'))[1], /^Last saved \S.*\. From an earlier forecast model\.$/);
queryData = data(.8); queryError = true; tree = render();
assert.match(words(byId(tree, 'home.playoff.explanation'))[1], /^Last saved \S.*\. Update unavailable\.$/);
queryError = false;
queryData = incomplete; tree = render();
assert.deepEqual(words(byId(tree, 'home.playoff.explanation')), [DEFINITION, 'Incomplete: some lineup slots had no projection.']);
queryData = withRec(recommended('contender', { differs: false })); tree = render();
assert.deepEqual(words(byId(tree, 'home.playoff.explanation')), [DEFINITION, 'An 80.0% playoff chance is in the Contending range.']);
flags['league.projection_outlook'] = false; tree = render();
assert.deepEqual(words(byId(tree, 'home.playoff.explanation')), [DEFINITION]);
flags['league.projection_outlook'] = true;
byId(tree, 'home.playoff.explain').props.onPress(); tree = render();
assert.equal(byId(tree, 'home.playoff.explanation'), undefined);

// C/F — the prompt: flag on AND available AND differs.
queryData = withRec(recommended('contender', { playoff_probability: .7249 }), .7249); tree = render();
assert.deepEqual(words(byId(tree, 'home.playoff.recommendation')), ['Consider Contending', 'Review outlook']);
let reviewButton = byId(tree, 'home.playoff.review-outlook');
assert.equal(reviewButton.type, 'Pressable');
assert.equal(reviewButton.props.accessibilityRole, 'button');
assert.equal(reviewButton.props.accessibilityLabel, '72% playoff chance. Consider Contending. Review outlook.');
assert.deepEqual(words(byId(tree, 'home.playoff.details')), ['72.5%']); // Display rounding only.
calls.length = 0; reviewButton.props.onPress();
assert.deepEqual(calls, ['review:contender']); // The handler, once, and nothing else.
queryData = withRec(recommended('jets', { playoff_probability: .99 }), .99); tree = render();
assert.deepEqual(words(byId(tree, 'home.playoff.recommendation')), ['Consider Tanking', 'Review outlook']); // Never re-classified.
flags['league.projection_outlook'] = false; tree = render();
assert.equal(byId(tree, 'home.playoff.recommendation'), undefined);
flags['league.projection_outlook'] = true;
for (const none of [recommended('contender', { differs: false }), recommended('contender', { status: 'unavailable' }),
  recommended('unknown_outlook')]) {
  queryData = withRec(none); tree = render();
  assert.equal(byId(tree, 'home.playoff.recommendation'), undefined);
  assert.equal(byId(tree, 'home.playoff.review-outlook'), undefined);
}
queryData = withRec(recommended('contender'), .8, 'stale'); tree = render();
assert.equal(byId(tree, 'home.playoff.recommendation'), undefined);

// G — the server's suggestion sentence is reachable: in the expanded
// explanation, above the explanation sentence, exactly when "Consider" shows.
const SUGGESTION = 'Consider trades that improve your current starting lineup.';
const EXPLANATION = 'An 80.0% playoff chance is in the Contending range.';
queryData = withRec(recommended('contender')); tree = render();
assert.equal(byId(tree, 'home.playoff.explanation'), undefined); // Collapsed: unchanged.
assert(!words(tree).includes(SUGGESTION), 'the suggestion stays behind the info toggle');
assert.deepEqual(words(byId(tree, 'home.playoff.recommendation')), ['Consider Contending', 'Review outlook']);
byId(tree, 'home.playoff.explain').props.onPress(); tree = render();
assert(byId(tree, 'home.playoff.recommendation'), 'the prompt shows');
assert.deepEqual(words(byId(tree, 'home.playoff.explanation')), [DEFINITION, SUGGESTION, EXPLANATION]);
assert.deepEqual(words(byId(tree, 'home.playoff.suggestion')), [SUGGESTION]);
const ALL_IN = 'This is a suggestion, not a guarantee: consider trading future picks for proven starters.';
queryData = withRec(recommended('championship', { suggestion: ALL_IN })); tree = render();
assert.deepEqual(words(byId(tree, 'home.playoff.explanation')), [DEFINITION, ALL_IN, EXPLANATION]);
// No prompt ⇒ no suggestion sentence.
for (const [value, flagOn] of [[withRec(recommended('contender', { differs: false })), true],
  [withRec(recommended('contender', { status: 'unavailable' })), true],
  [withRec(recommended('contender'), .8, 'stale'), true],
  [withRec(recommended('unknown_outlook')), true],
  [withRec(recommended('contender')), false]]) {
  queryData = value; flags['league.projection_outlook'] = flagOn; tree = render();
  assert.equal(byId(tree, 'home.playoff.recommendation'), undefined);
  assert(byId(tree, 'home.playoff.explanation'), 'the explanation is open');
  assert.equal(byId(tree, 'home.playoff.suggestion'), undefined);
  assert(!words(tree).includes(SUGGESTION), 'no suggestion sentence without the prompt');
}
flags['league.projection_outlook'] = true;
byId(tree, 'home.playoff.explain').props.onPress(); tree = render();
assert.equal(byId(tree, 'home.playoff.explanation'), undefined);

active.switching = true; assert.equal(render(), null); assert.equal(options.enabled, false);
active.switching = false; active.hasToken = false; assert.equal(render(), null);
active.hasToken = true; active.leagues[0].platform = 'espn'; assert.equal(render(), null);
active.leagues[0].platform = 'sleeper'; flags['league.projections'] = false; assert.equal(render(), null);
console.log('Home playoff banner: current/stale/old-model/incomplete, recommendation, link, explanation and read-only checks passed');
