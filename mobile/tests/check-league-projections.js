const fs = require('fs');
const path = require('path');
const assert = require('assert');
const root = path.resolve(__dirname, '../..');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');
const standings = read('mobile/src/screens/StandingsScreen.tsx');
const summary = read('mobile/src/screens/LeagueSummaryScreen.tsx');
const section = read('mobile/src/components/LeagueProjectionSection.tsx');
const api = read('backend/league_projections/api.py');
assert(standings.includes("const batchProjections = useFlag('league.projections')"));
assert(standings.includes("enabled: !batchProjections && segment === 'projected'"));
assert(summary.includes('enabled: !batchProjections && oddsEnabled'));
// League Rankings shows Home's playoff tile; the full section is Standings' only.
assert(summary.includes('{batchProjections ? (\n          <HomePlayoffBanner') && !summary.includes('LeagueProjectionSection'));
assert(section.includes("['league-projection-batch', userId, leagueId]"));
assert(section.includes('getLeagueProjectionBatch'));
assert(!api.includes('service.wake('));
assert(!api.includes('store.maintenance('));
// The history-weight comparison and the forecast-details disclosure are gone,
// and with them the only client call that could queue a projection run.
const projectionApi = read('mobile/src/api/leagueProjections.ts');
const mobileSources = [section, standings, summary, projectionApi,
  read('mobile/src/components/home/HomePlayoffBanner.tsx'), read('mobile/src/utils/homePlayoffBanner.ts')];
for (const gone of ['queueLeagueProjectionScenario', 'baseline_run_id', 'compare(', 'Compare history weights',
  'historical_weight', 'Forecast details', 'Forecasts update weekly', 'Assumptions and scoring', 'Scoring settings',
  'league-projection-scenario', 'history_fallback', 'fallback_lanes', 'historical blend', 'Historical blending',
  'Historical fallback', 'persistent_sd', 'config.maxpf_variance', 'Variance source']) {
  assert(mobileSources.every(source => !source.includes(gone)), `${gone} is gone from the projection client`);
}
assert(!/api\.post|useMutation/.test(section + projectionApi), 'the projection client only reads');
// "Check for update" survives in the no-result branch only.
assert.equal(section.split('league-projections.check').length - 1, 1);
assert(section.indexOf('league-projections.check') > section.indexOf('Current standings are still available.'));
assert(section.indexOf('league-projections.check') < section.indexOf('function ProjectionTables'));
// A run from an older model reads as last saved, never as the weekly estimate.
assert(section.includes("const lastSaved = !!result && (query.isError || state !== 'current' || data?.model_current === false);"));
assert(section.includes("lastSaved ? `Last saved: ${date(result.captured_at)}` : 'Weekly estimate'"));
assert(projectionApi.includes('model_current?: boolean'));
// An incomplete estimate says so in the status line and in one plain sentence.
assert(section.includes("const incomplete = result?.coverage?.estimate_status === 'incomplete';"));
assert(section.includes("incomplete ? 'Incomplete' : null"));
assert(section.includes('{incompleteSentence(missingSlots)}'));
assert(section.includes('result?.coverage?.missing_lineup_slots'));
assert(section.includes('w.projection_coverage?.complete === false'));
assert(section.includes('Score not recorded yet at: '));
assert(!section.includes('No projection for an eligible player'), 'the v5 missing-projection wording is gone');
// Model v6 copy is executed, not just matched: utils/projectionCoverage is
// transpiled and run, then the section is pinned to render exactly its output.
const ts = require('typescript');
const vm = require('vm');
const cov = {};
vm.runInNewContext(ts.transpileModule(read('mobile/src/utils/projectionCoverage.ts'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020}}).outputText, {exports: cov});
assert.equal(cov.incompleteSentence(1), '1 lineup slot had a starter whose score is not recorded yet, so these odds are incomplete.');
assert.equal(cov.incompleteSentence(3), '3 lineup slots had a starter whose score is not recorded yet, so these odds are incomplete.');
assert.equal(cov.incompleteSentence(undefined), 'Some lineup slots had a starter whose score is not recorded yet, so these odds are incomplete.');
const fa = cov.freeAgentFillSentence;
assert.equal(fa({fa_filled_slots: 12, zero_filled_slots: 1}), '12 open lineup slots use the best available free agent; 1 has none and counts as 0.');
assert.equal(fa({fa_filled_slots: 1, zero_filled_slots: 3}), '1 open lineup slot uses the best available free agent; 3 have none and count as 0.');
assert.equal(fa({fa_filled_slots: 2, zero_filled_slots: 0}), '2 open lineup slots use the best available free agent.');
assert.equal(fa({fa_filled_slots: 1}), '1 open lineup slot uses the best available free agent.');
assert.equal(fa({fa_filled_slots: 0, zero_filled_slots: 1}), '1 open lineup slot has no free agent available and counts as 0.');
assert.equal(fa({zero_filled_slots: 4}), '4 open lineup slots have no free agent available and count as 0.');
for (const none of [undefined, null, {}, {fa_filled_slots: 0, zero_filled_slots: 0}, {estimated: true, missing_lineup_slots: 2}]) {
  assert.equal(fa(none), null, `no free-agent line for ${JSON.stringify(none)}`);
}
assert(section.includes('const freeAgentLine = freeAgentFillSentence(result?.coverage);'));
assert(section.includes('{freeAgentLine ? <Text variant="bodySm" style={styles.text} testID="league-projections.free-agents">{freeAgentLine}</Text> : null}'));
// Team-week lineup: a slot in free_agent_fills is marked "(free agent)"; a roster starter is not.
const fills = [{slot_index: 1, slot: 'WR', player_id: '9', name: 'Free Guy', points: '11.2', estimate_status: 'available'}];
assert.equal(cov.lineupRowText({slot: 'WR', player: {player_id: '9', name: 'Free Guy', points: '11.2'}}, 1, fills), 'WR: Free Guy (free agent) · 11.2');
assert.equal(cov.lineupRowText({slot: 'QB', player: {player_id: '4', name: 'Own Guy', points: '20.0'}}, 0, fills), 'QB: Own Guy · 20.0');
assert.equal(cov.lineupRowText({slot: 'WR', player: {player_id: '9', name: 'Free Guy', points: '11.2'}}, 1, undefined), 'WR: Free Guy · 11.2', 'an older run without fills marks nothing');
assert.equal(cov.lineupRowText({slot: 'TE', player: null}, 2, fills), 'TE: Empty slot');
assert.equal(cov.lineupRowText({slot: 'K', player: null, unpriced_locked_player: {player_id: '7', name: 'Kicker'}}, 3, fills), 'K: Locked starter Kicker: actual score unavailable');
assert(section.includes('{lineupRowText(r, i, w.projection_coverage?.free_agent_fills)}'));
assert(section.includes('Recorded completed lineup score ${number(w.modeled_score_mean)}.'));
assert(section.includes('Projected lineup score ${number(w.modeled_score_mean)}; standard deviation ${number(w.modeled_score_sd)}.'));
assert(section.includes('data?.run?.result'));
assert(section.includes('Current standings'));
assert(section.includes('conditional_expected_pick'));
console.log('league projections: stored reads, model/coverage state, removed comparison UI and old-query exclusion verified');
