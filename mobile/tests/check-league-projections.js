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
assert(summary.includes('{batchProjections ? <LeagueProjectionSection />'));
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
assert(section.includes('had no projection for an eligible player, so these odds are incomplete.'));
assert(section.includes('result?.coverage?.missing_lineup_slots'));
assert(section.includes('w.projection_coverage?.complete === false'));
assert(section.includes('No projection for an eligible player at: '));
assert(section.includes('Recorded completed lineup score ${number(w.modeled_score_mean)}.'));
assert(section.includes('Projected lineup score ${number(w.modeled_score_mean)}; standard deviation ${number(w.modeled_score_sd)}.'));
assert(section.includes('data?.run?.result'));
assert(section.includes('Current standings'));
assert(section.includes('conditional_expected_pick'));
console.log('league projections: stored reads, model/coverage state, removed comparison UI and old-query exclusion verified');
