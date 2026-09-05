#!/usr/bin/env node
// D-056: structural mobile contracts + executable web async race regressions.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const mobile = read('mobile/src/screens/WinNowScreen.tsx');
const api = read('mobile/src/api/winNow.ts');
const web = read('web/js/win-now.js');
const nav = read('mobile/src/navigation/RootNav.tsx');
let checks = 0;
const check = (name, fn) => { fn(); checks++; };
check('root route and feedback mount', () => {
  assert.equal((nav.match(/name="WinNow"/g) || []).length, 1);
  assert.match(mobile, /FeedbackFAB activeScreen="WinNow" aboveTabBar=\{false\}/);
  assert.match(read('mobile/src/utils/deepLinks.ts'), /WinNow: 'app\/trades\/win-now'/);
});
check('gated entry points and dedicated screen guard', () => {
  assert.match(read('mobile/src/screens/TradesScreen.tsx'), /winNowOn && seasonProjectionsOn && leagueId/);
  assert.match(read('mobile/src/screens/LeagueSummaryScreen.tsx'), /seasonProjectionsOn && leagueId/);
  for (const flag of ['outlook.season_projections', 'trades.win_now', 'outlook.championship_probabilities']) assert.ok(mobile.includes(flag));
  assert.match(mobile, /meta\?\.championship_available === true/);
});
check('cancellation on every relevant transition, bounded polling, viewer-keyed component', () => {
  assert.match(mobile, /key=\{`\$\{userId\}:\$\{leagueId\}`\}/);
  assert.match(mobile, /\[leagueId, objective, budget, fairness, protectedIds, seasonOn, searchOn, titleFlag, focused, refresh\]/);
  assert.match(mobile, /controller\.current\?\.abort\(\)/);
  assert.match(mobile, /if \(!current\(request.id\)\) return/);
  assert.match(mobile, /90_000/);
});
check('no dynasty cache, sort, or training decisions', () => {
  for (const source of [mobile, api, web]) {
    assert.doesNotMatch(source, /\/trades\/swipe|\/trades\/queue|trades\.sort\(/);
  }
  assert.match(api, /\/api\/win-now\/scenarios\//);
  assert.match(mobile, /setTrades\(job.result.trades\)/);
});
check('honest budget, evidence and supported-state surfaces', () => {
  for (const marker of ['fixed baseline roster value', 'partner_basis', 'partner_confidence', 'partner_coverage', 'win-now.empty', 'win-now.stale', 'win-now.unavailable', 'win-now.evaluate']) assert.ok(mobile.includes(marker));
  assert.match(mobile, /max_dynasty_spend_pct: Number\(budget\)/);
  assert.match(mobile, /min_fairness: Number\(fairness\) \/ 100/);
  assert.match(read('mobile/src/utils/winNow.ts'), /\(after - before\) \* \(points \? 100 : 1\)/);
});

// Run the mobile formatters too; transpiling removes their type-only import.
const ts = require('typescript');
const utility = {exports: {}};
const scoringWarning = 'Rare special-teams/fumble bonuses are not projected.';
vm.runInNewContext(ts.transpileModule(read('mobile/src/utils/winNow.ts'), {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020}}).outputText, {exports: utility.exports, Date});
check('mobile receipt shows only server-supplied scoring warning', () => {
  const receipt = utility.exports.sourceReceipt;
  assert.ok(receipt({scoring_warning: scoringWarning}).endsWith(`\n${scoringWarning}`));
  assert.equal(receipt({scoring_warning: null}), receipt());
  assert.equal(receipt({scoring_exclusions: {fum_rec_td: 6}}), receipt());
  assert.ok(!receipt().includes(scoringWarning));
});
check('mobile probability and pp formatting preserves zero and rejects missing data', () => {
  const u = utility.exports;
  assert.equal(u.probability(0), '0.0%'); assert.equal(u.probability(null), '—'); assert.equal(u.probability(1.1), '—');
  assert.equal(u.impact(.2, .25, true), '+5.0 pp'); assert.equal(u.impact(.25, .2, true), '-5.0 pp'); assert.equal(u.impact(undefined, .2, true), '—');
  assert.match(u.sourceReceipt({calibrated: false}), /Uncalibrated beta/);
  assert.match(u.sourceReceipt({calibrated: false}), /projection\/model uncertainty is excluded/);
  assert.equal(u.nextThree({weekly_win_probabilities: {'1': .9}}), undefined);
});
check('mobile snapshot expiry stops current recommendations and timestamp stays honest', () => {
  const u = utility.exports;
  assert.equal(u.seasonStale({expires_at: '2026-09-04T12:00:00Z'}, Date.parse('2026-09-04T13:00:00Z')), true);
  assert.equal(u.seasonStale({stale: true}), true);
  assert.match(u.sourceReceipt(), /timestamp unavailable/);
  assert.match(u.sourceReceipt(), /Coverage unavailable/);
});

check('mobile standings sort a copy and sampling ranges use pp', () => {
  const u = utility.exports;
  const teams = [{roster_id: 1, projected_seed: 6.714}, {roster_id: 2, projected_seed: 2.1}];
  const sorted = u.projectedStandings(teams);
  assert.equal(sorted[0].roster_id, 2); assert.equal(teams[0].roster_id, 1);
  const evidence = u.samplingEvidence({buyer: {uncertainty: {playoff_probability: {lower_bound: .01, upper_bound: .05, confirmation_delta: .02}}}, conservative_season_gain: .01}, 'playoffs');
  assert.match(evidence, /\+1.0 pp to \+5.0 pp/); assert.match(evidence, /not a forecast confidence interval/);
});

// Small DOM port executes the shipped web module; requests stay deferred so
// old league/objective responses can arrive after the user has moved on.
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this.textContent = ''; this.attributes = {}; this.classList = {toggle: () => {}}; }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this.children = children; this.textContent = ''; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(key, fn) { this.listeners[key] = fn; }
  scrollIntoView() {}
}
const staticNodes = Object.fromEntries(['win-now-controls', 'win-now-results', 'win-now-status', 'trades-win-now', 'league-win-now'].map(id => [id, new Element('div')]));
const nodes = node => [node, ...node.children.flatMap(nodes)];
const all = () => Object.values(staticNodes).flatMap(nodes);
const text = id => nodes(staticNodes[id]).map(n => n.textContent).join('\n');
const flags = {};
let league = 'league-a', user = 'buyer-a';
const requests = [], timers = new Map(); let timerId = 0;
const window = {FTF_FLAG: key => !!flags[key], FTFWinNowContext: {
  leagueId: () => league, userId: () => user,
  apiFetch: (url, options) => new Promise(resolve => requests.push({url, options, resolve})),
}};
const sandbox = {window, document: {getElementById: id => staticNodes[id] || all().find(n => n.id === id), createElement: tag => new Element(tag), addEventListener: () => {}}, AbortController, Date, setTimeout: (fn, ms) => { const id = ++timerId; timers.set(id, {fn, ms}); return id; }, clearTimeout: id => timers.delete(id)};
vm.runInNewContext(web, sandbox);
const flush = async () => { for (let n = 0; n < 8; n++) await Promise.resolve(); };
const reply = async (request, data, ok = true) => { request.resolve({ok, status: ok ? 200 : 503, json: async () => data}); await flush(); };
const click = async label => {
  const node = all().find(n => n.tag === 'button' && n.textContent === label);
  assert.ok(node, `button exists: ${label}`); assert.equal(node.disabled, false, `button enabled: ${label}`);
  node.listeners.click(); await flush();
};
const baseline = {status: 'available', meta: {source: 'Test provider', as_of: '2026-09-04T12:00:00Z', snapshot_id: 'snap', model_version: 'test', championship_available: false, coverage: .95}, buyer_roster_id: 1, teams: [{roster_id: 1, username: 'Buyer', projected_seed: 2, expected_wins: 8, expected_losses: 6, expected_ties: 0, playoff_probability: .2, bye_probability: .1}, {roster_id: 2, username: 'Earlier finish', projected_seed: 1.123}], assets: [{id: 'a', name: 'Buyer asset', owner_roster_id: 1}, {id: 'b', name: 'Partner asset', owner_roster_id: 2}, ...['a2', 'a3', 'a4'].map(id => ({id, name: id, owner_roster_id: 1}))]};
const trade = name => ({scenario_id: name, partner_roster_id: 2, partner_username: name, give: [baseline.assets[0]], receive: [baseline.assets[1]], conservative_season_gain: .01, buyer: {before: {playoff_probability: .2}, after: {playoff_probability: .25}, uncertainty: {playoff_probability: {lower_bound: .01, upper_bound: .08, confirmation_delta: .03}}}, partner: {before: {playoff_probability: .1}, after: {playoff_probability: .12}}, valuation: {partner_basis: 'market_estimate', partner_confidence: .4, partner_coverage: 0, partner_intent: 'unknown'}});
(async () => {
  window.FTFWinNow.onView('win-now');
  check('dark flags cause no requests', () => assert.equal(requests.length, 0));
  flags['outlook.season_projections'] = true; flags['trades.win_now'] = true;
  window.FTFWinNow.onView('win-now'); const old = requests.at(-1);
  league = 'league-b'; window.FTFWinNow.reset();
  await reply(old, baseline);
  check('old league baseline cannot render', () => { assert.equal(old.options.signal.aborted, true); assert.doesNotMatch(text('win-now-controls'), /Projected standings/); });
  await click('Refresh season projections'); await reply(requests.at(-1), baseline);
  check('web receipt invents no scoring warning when absent', () => assert.ok(!text('win-now-controls').includes(scoringWarning)));
  await click('Refresh season projections');
  await reply(requests.at(-1), {...baseline, meta: {...baseline.meta, scoring_exclusions: {fum_rec_td: 6}, scoring_warning: scoringWarning}});
  check('web receipt displays server-supplied scoring warning', () => assert.ok(text('win-now-controls').includes(scoringWarning)));
  await click('Refresh season projections'); await reply(requests.at(-1), baseline);
  check('web receipt removes scoring warning when next snapshot omits it', () => assert.ok(!text('win-now-controls').includes(scoringWarning)));
  check('web standings use average finish in sorted order and mark beta', () => {
    const output = text('win-now-controls'); assert.match(output, /Avg finish \/ team/); assert.match(output, /1.12 Earlier finish/);
    assert.ok(output.indexOf('Earlier finish') < output.indexOf('Buyer'));
    assert.match(output, /Uncalibrated beta/); assert.match(output, /projection\/model uncertainty is excluded/);
  });
  check('validated title unavailable despite estimates', () => assert.equal(all().filter(n => n.tag === 'button' && n.textContent === 'Championship').length, 0));
  for (const [id, invalid, valid] of [['win-now-budget', '11', '3'], ['win-now-fairness', '70', '90']]) {
    const control = all().find(n => n.id === id); control.value = invalid; control.listeners.input();
    check(`server range enforced: ${id}`, () => { assert.equal(all().find(n => n.id === 'win-now-search').disabled, true); assert.match(text('win-now-status'), /0 to 10%/); });
    control.value = valid; control.listeners.input();
  }
  await click('Find Win Now trades'); const oldSearch = requests.at(-1);
  check('search sends exact objective and baseline percentage', () => {
    const body = JSON.parse(oldSearch.options.body); assert.equal(body.league_id, 'league-b'); assert.equal(body.objective, 'wins'); assert.equal(body.max_dynasty_spend_pct, 3); assert.equal(body.min_fairness, .9);
  });
  await click('Make playoffs'); await reply(oldSearch, {status: 'queued', job_id: 'old-job'});
  check('objective change aborts old job and prevents late polling', () => { assert.equal(oldSearch.options.signal.aborted, true); assert.equal([...timers.values()].filter(t => t.ms === 1500).length, 0); });
  await click('Find Win Now trades'); await reply(requests.at(-1), {status: 'complete', result: {meta: baseline.meta, trades: [trade('Server first'), trade('Server second')]}});
  check('server order and absolute percentage points', () => {
    const output = text('win-now-results'); assert.ok(output.indexOf('Server first') < output.indexOf('Server second')); assert.match(output, /20.0% → 25.0% \(\+5.0 pp\)/); assert.match(output, /market estimate/); assert.match(output, /Sampling range \+1.0 pp to \+8.0 pp/); assert.match(output, /conservative search gain \+1.0 pp/); assert.doesNotMatch(output, /Championship:/);
  });
  await click('Like'); const decision = requests.at(-1);
  check('season decision uses independent endpoint', () => { assert.match(decision.url, /\/win-now\/scenarios\/Server%20first\/decision$/); assert.equal(JSON.parse(decision.options.body).decision, 'like'); });
  await reply(decision, {status: 'unavailable', reason: 'stale_forecast', message: 'Scenario expired. Refresh projections.'});
  check('decision unavailable preserves server explanation', () => assert.match(text('win-now-status'), /Scenario expired/));
  await click('Like'); await reply(requests.at(-1), {ok: true});
  await click('Edit & evaluate');
  const editorNode = () => all().find(n => n.id === 'win-now-editor');
  for (const label of ['a2 · Player', 'a3 · Player']) nodes(editorNode()).find(n => n.tag === 'button' && n.textContent === label).listeners.click();
  check('editor prevents more than three assets per side', () => assert.equal(nodes(editorNode()).find(n => n.tag === 'button' && n.textContent === 'a4 · Player').disabled, true));
  for (const label of ['a2 · Player', 'a3 · Player']) nodes(editorNode()).find(n => n.tag === 'button' && n.textContent === label).listeners.click();
  await click('Evaluate edited trade'); const edited = requests.at(-1);
  check('editor evaluates server-owned assets with same objective constraints', () => { const body = JSON.parse(edited.options.body); assert.equal(body.objective, 'playoffs'); assert.deepEqual(body.give_ids, ['a']); assert.deepEqual(body.receive_ids, ['b']); assert.equal(body.partner_roster_id, 2); });
  await reply(edited, {status: 'available', eligible: false, rejection_reasons: ['partner_gain_required'], meta: baseline.meta});
  check('calculator rejection is visible', () => assert.match(text('win-now-results'), /partner gain required/));
  await click('Find Win Now trades'); await reply(requests.at(-1), {message: 'Forecast source is stale'}, false);
  check('errors stop progress and enable manual retry', () => { assert.match(text('win-now-status'), /Forecast source is stale/); assert.equal(all().find(n => n.id === 'win-now-search').disabled, false); assert.equal([...timers.values()].filter(t => t.ms === 1500).length, 0); });
  await click('Find Win Now trades'); const pending = requests.at(-1); window.FTFWinNow.onView('trades'); await reply(pending, {status: 'complete', result: {meta: baseline.meta, trades: [trade('Late')]}});
  check('mode exit clears scenario results and cancels request', () => { assert.equal(pending.options.signal.aborted, true); assert.doesNotMatch(text('win-now-results'), /Late/); });
  console.log(`Win Now: ${checks} checks passed`);
})().catch(error => { console.error(error); process.exitCode = 1; });
