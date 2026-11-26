const fs = require('fs');
const path = require('path');
const assert = require('assert');
const root = path.resolve(__dirname, '../..');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');
const standings = read('mobile/src/screens/StandingsScreen.tsx');
const summary = read('mobile/src/screens/LeagueSummaryScreen.tsx');
// The Projected section was folded into the Standings table (2026-11-12):
// its query + status line live in StandingsScreen, its team detail in
// LeagueProjectionDetail, its status words in utils/standingsTable.
const detail = read('mobile/src/components/LeagueProjectionDetail.tsx');
const table = read('mobile/src/utils/standingsTable.ts');
assert(!fs.existsSync(path.join(root, 'mobile/src/components/LeagueProjectionSection.tsx')), 'LeagueProjectionSection is retired');
const api = read('backend/league_projections/api.py');
assert(standings.includes("const batchProjections = useFlag('league.projections')"));
assert(standings.includes('const forecastEnabled = batchProjections && isSleeper && !!leagueId && !!userId;'));
assert(!standings.includes('getOutlook') && !standings.includes('league-outlook'), 'Standings runs no outlook simulation');
assert(summary.includes('enabled: !batchProjections && oddsEnabled'));
// League Rankings shows Home's playoff tile; the full section is Standings' only.
assert(summary.includes('{batchProjections ? (\n          <HomePlayoffBanner') && !summary.includes('LeagueProjectionSection'));
assert(standings.includes("queryKey: ['league-projection-batch', userId, leagueId],"));
assert(standings.includes('getLeagueProjectionBatch'));
assert(!api.includes('service.wake('));
assert(!api.includes('store.maintenance('));
// The history-weight comparison and the forecast-details disclosure are gone,
// and with them the only client call that could queue a projection run.
const projectionApi = read('mobile/src/api/leagueProjections.ts');
const mobileSources = [detail, table, standings, summary, projectionApi,
  read('mobile/src/components/home/HomePlayoffBanner.tsx'), read('mobile/src/utils/homePlayoffBanner.ts')];
for (const gone of ['queueLeagueProjectionScenario', 'baseline_run_id', 'compare(', 'Compare history weights',
  'historical_weight', 'Forecast details', 'Forecasts update weekly', 'Assumptions and scoring', 'Scoring settings',
  'league-projection-scenario', 'history_fallback', 'fallback_lanes', 'historical blend', 'Historical blending',
  'Historical fallback', 'persistent_sd', 'config.maxpf_variance', 'Variance source']) {
  assert(mobileSources.every(source => !source.includes(gone)), `${gone} is gone from the projection client`);
}
assert(!/api\.post|useMutation/.test(standings + detail + projectionApi), 'the projection client only reads');
// "Check for update" survives in the no-result branch only.
assert.equal(standings.split('league-projections.check').length - 1, 1);
assert(standings.indexOf('league-projections.check') > standings.indexOf('testID="standings.no-forecast"'));
assert(standings.indexOf('testID="standings.forecast-status"') > 0
  && standings.indexOf('testID="standings.no-forecast"') > standings.indexOf('testID="standings.forecast-status"'));
// A run from an older model reads as last saved, never as the weekly estimate.
assert(standings.includes("const lastSaved = !!result && (forecastQuery.isError || state !== 'current' || data?.model_current === false);"));
assert(standings.includes("lastSaved ? `Last saved: ${date(result.captured_at)}` : 'Weekly estimate'"));
assert(projectionApi.includes('model_current?: boolean'));
// An incomplete estimate says so in the status line (the "Incomplete" tag).
// The incomplete sentence, its testID and the "Partial Sleeper data" tag were
// removed (owner, 2026-11-25).
assert(standings.includes("const incomplete = result?.coverage?.estimate_status === 'incomplete';"));
assert(standings.includes("incomplete ? 'Incomplete' : null"));
assert(standings.includes("result.provisional ? 'Provisional' : null"), 'the Provisional tag stays');
for (const gone of ['incompleteSentence', 'league-projections.incomplete', 'Partial Sleeper data', 'missing_lineup_slots']) {
  assert(!standings.includes(gone), `${gone} is gone from Standings`);
}
assert(!detail.includes('No projection for an eligible player'), 'the v5 missing-projection wording is gone');
// Model v6 copy is executed, not just matched: utils/projectionCoverage is
// transpiled and run, then the section is pinned to render exactly its output.
const ts = require('typescript');
const vm = require('vm');
const cov = {};
vm.runInNewContext(ts.transpileModule(read('mobile/src/utils/projectionCoverage.ts'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020}}).outputText, {exports: cov});
assert.equal(cov.incompleteSentence, undefined, 'the incomplete-sentence helper is gone (no mobile caller)');
// The league-level free-agent / counts-as-0 summary line was removed
// (operator, 2026-11-12): no helper, no render, no copy. The per-row
// "(free agent)" marker below stays.
assert.equal(cov.freeAgentFillSentence, undefined, 'the free-agent summary helper is gone');
const coverageSource = read('mobile/src/utils/projectionCoverage.ts');
for (const gone of ['freeAgentFillSentence', 'freeAgentLine', 'league-projections.free-agents', 'best available free agent', 'counts as 0', 'count as 0']) {
  assert(!standings.includes(gone) && !detail.includes(gone) && !coverageSource.includes(gone), `${gone} is gone from the projection client`);
}
assert(standings.includes('data?.run?.result'));
// No saved forecast: the table stays, and one line says projections aren't available yet.
assert(table.includes("export const NO_FORECAST_LINE = 'Projections aren’t available for this league yet.';") && standings.includes('noForecastLine({'));
// ── The open team's detail (display rows, 2026-11-25) ─────────────────────
// Section order: Final record odds / Remaining schedule / Draft pick odds,
// then the own-card sections, unchanged.
const at = s => detail.indexOf(s);
assert(at('label="Final record odds"') > 0 && at('label="Final record odds"') < at('<Disclosure label={S.title}>')
  && at('<Disclosure label={S.title}>') < at('label="Draft pick odds"')
  && at('label="Draft pick odds"') < at("{moves ? <Disclosure label={MAXPF_COPY['C-TITLE']}"), 'section order');
// Remaining schedule: copy, headings, the remaining-week rule, win text, fallback, season over.
const S = cov.SCHEDULE_COPY;
assert.equal(S.title, 'Remaining schedule');
assert.deepEqual([S.week, S.opponent, S.own, S.opp, S.win, S.edge], ['Wk', 'Opponent', 'Proj.', 'Opp.', 'Win %', 'Edge']);
assert.equal(S.none, 'No regular-season games left.');
for (const ref of ['{S.week}', '{S.opponent}', '{S.own}', '{S.opp}', '{lastHead}', 'fallback ? S.edge : S.win', '{S.none}']) {
  assert(detail.includes(ref), `the schedule renders ${ref}`);
}
assert.equal(cov.winText(0.774), '77%');
assert.equal(cov.winText(0.996), '>99%', 'never 100%');
assert.equal(cov.winText(1), '>99%');
assert.equal(cov.winText(0.004), '<1%', 'never 0%');
assert.equal(cov.winText(0), '<1%');
assert.equal(cov.winText(0.02), '2%');
assert.equal(cov.EVEN_POINTS, 3);
assert.equal(cov.edgeText(110, 107), 'W', 'exactly 3 points apart is not Even');
assert.equal(cov.edgeText(107, 110), 'L');
assert.equal(cov.edgeText(110, 107.01), 'Even');
assert.equal(cov.edgeText(107.01, 110), 'Even');
assert.equal(cov.edgeText(100, 100), 'Even');
const week = (n, opp, win, mean, observed) => ({week: n, opponent_roster_id: opp, win_probability: win, modeled_score_mean: mean,
  ...(observed === undefined ? {} : {actual_score_observed: observed}), actual: {lineup: []}});
const teamA = {roster_id: 1, name: 'Alpha', weeks: [week(11, 2, 0.6, 130, true), week(12, 2, 0.774, 120.34, false),
  week(13, 3, 0.996, 101.06), week(14, 9, 0.004, 99.95)]};
const teamB = {roster_id: 2, name: 'A very long opponent name', weeks: [week(11, 1, 0.4, 120, true), week(12, 1, 0.226, 117.31)]};
const teamC = {roster_id: 3, name: 'Gamma', weeks: [week(12, 4, 0.5, 90)]};
assert.deepEqual(cov.remainingWeeks(teamA.weeks).map(w => w.week), [12, 13, 14], 'a week is remaining unless its score is observed');
const sched = cov.scheduleRows(teamA, [teamA, teamB, teamC]);
assert.equal(sched.fallback, false);
assert.deepEqual(JSON.parse(JSON.stringify(sched.rows)), [
  {week: 12, opponent: 'A very long opponent name', own: '120.3', opp: '117.3', last: '77%'},
  {week: 13, opponent: 'Gamma', own: '101.1', opp: '—', last: '>99%'},
  {week: 14, opponent: 'Team 9', own: '100.0', opp: '—', last: '<1%'},
], 'own projection, then the opponent\'s that same week (a dash when it has none), then the win chance');
// No finite win chance on a remaining row: the whole column becomes Edge (per section).
const noWin = {...teamA, weeks: [week(12, 2, null, 120.34), week(13, 3, 0.6, 101.06)]};
const teamC13 = {...teamC, weeks: [week(13, 1, 0.4, 104.0)]};
const fb = cov.scheduleRows(noWin, [noWin, teamB, teamC13]);
assert.equal(fb.fallback, true);
assert.deepEqual(fb.rows.map(r => r.last), ['W', 'Even'], 'every row reads W / L / Even once any row lacks a win chance');
assert.equal(cov.scheduleRows({...teamA, weeks: [week(13, 2, NaN, 90)]}, [teamA]).rows[0].last, '—', 'no opponent projection: a dash');
// Season over: no rows, so the section body is the one line.
assert.deepEqual(cov.scheduleRows({...teamA, weeks: [week(11, 2, 0.6, 130, true)]}, [teamA]).rows, []);
assert(/if \(rows\.length === 0\) return <Text variant="bodySm" style=\{styles\.text\}>\{S\.none\}<\/Text>;/.test(detail));
// Each row is the week's own expand control, 44pt tall, chevron in its own column.
assert(/<Pressable accessibilityRole="button" aria-expanded=\{open\} testID=\{`standings\.schedule\.week\.\$\{r\.week\}`\}/.test(detail));
assert(detail.includes("mTap: {minHeight: 44,") && detail.includes('mOpen: {backgroundColor: ink.ink3}'));
assert(detail.includes("<Icon name={open ? 'chevron-up' : 'chevron-down'} size={16} color={open ? ice.base : chalk.dim} />"));
assert(detail.includes('<View style={styles.chev} />'), 'the heading row keeps a blank chevron cell');
assert(detail.includes('numberOfLines={1}>{r.opponent}</Text>'), 'opponent names truncate, never wrap');
// The opened week: the lineup rows as parts, then players with no estimate.
const fills = [{slot_index: 1, slot: 'WR', player_id: '9', name: 'Free Guy', points: '11.2', estimate_status: 'available'}];
const parts = (row, i, f) => JSON.parse(JSON.stringify(cov.lineupRowParts(row, i, f)));
assert.deepEqual(parts({slot: 'QB', player: {player_id: '4', name: 'Own Guy', points: '20.04'}}, 0, fills),
  {slot: 'QB', name: 'Own Guy', freeAgent: false, points: '20.0'});
assert.deepEqual(parts({slot: 'WR', player: {player_id: '9', name: 'Free Guy', points: '11.2345'}}, 1, fills),
  {slot: 'WR', name: 'Free Guy', freeAgent: true, points: '11.2'});
assert.equal(parts({slot: 'WR', player: {player_id: '9', name: 'Free Guy', points: '11.2'}}, 1, undefined).freeAgent, false, 'an older run without fills marks nothing');
assert.deepEqual(parts({slot: 'RB', player: {player_id: 'x', points: '8.66', hypothetical: true}}, 2, fills),
  {slot: 'RB', name: 'Hypothetical bye replacement', freeAgent: false, points: '8.7'});
assert.deepEqual(parts({slot: 'TE', player: null}, 3, fills), {slot: 'TE', name: 'Empty slot', freeAgent: false, points: '—'});
assert.deepEqual(parts({slot: 'K', player: null, unpriced_locked_player: {player_id: '7', name: 'Kicker'}}, 4, fills),
  {slot: 'K', name: 'Locked starter Kicker', freeAgent: false, points: '—'});
assert.equal(parts({slot: 'K', player: null, unpriced_locked_player: {player_id: '7'}}, 4).name, 'Locked starter 7');
assert.equal(parts({slot: 'SUPER_FLEX', player: null}, 5).slot, 'SF');
assert.equal(parts({slot: 'IDP_FLEX', player: null}, 6).slot, 'IDP');
assert.equal(parts({slot: 'REC_FLEX', player: null}, 7).slot, 'W/T');
assert.equal(parts({slot: 'WRRB_FLEX', player: null}, 8).slot, 'W/R');
// Every other slot the forecast admits (backend/league_projections/core.py SLOTS) shows as given.
for (const slot of ['QB', 'RB', 'WR', 'TE', 'K', 'FLEX', 'DL', 'LB', 'DB']) assert.equal(cov.slotLabel(slot), slot);
assert(detail.includes('const row = lineupRowParts(r, i, w.projection_coverage?.free_agent_fills);'));
assert(detail.includes('{row.freeAgent ? <Text scale="dense" style={styles.muted}>{S.freeAgent}</Text> : null}') && S.freeAgent === '(free agent)');
assert(detail.includes('const unpriced = w.projection_coverage?.unpriced_players ?? [];')
  && detail.includes('{p.name || p.player_id}</Text>') && detail.includes('{S.noEstimate}') && S.noEstimate === 'no estimate',
  'players with no estimate: name, then "no estimate", only when there are any');
assert(detail.includes("points: {width: NUM_W, textAlign: 'right', marginRight: CHEV_W + COL_GAP}"), 'points end under the Win % column');
// Everything else the old week detail rendered is gone, with the old disclosures.
for (const gone of ['Weekly projections', ' win`}', 'Recorded completed lineup score', 'standard deviation', 'Max PF target',
  'Historical model: input Max PF', 'Show model diagnostics', 'Hide model diagnostics', 'league-projections.diagnostics', 'Latent mean',
  'An already completed eligible lineup', 'Available projections:', 'Score not recorded yet at', 'partial contributions',
  'No hypothetical IDP bye replacement', 'Available lineup contributions', 'w.exclusions', 'lineupRowText',
  'Expected pick if this team misses', 'conditional_expected_pick', 'Missed-playoff simulations', 'non-playoff picks']) {
  assert(!detail.includes(gone), `${gone} is gone from the open team's detail`);
}
assert.equal(cov.lineupRowText, undefined, 'the sentence-form lineup helper is replaced by lineupRowParts');

// ── Draft pick odds: rows, and the likely pick range ─────────────────────
const pr = {};
vm.runInNewContext(ts.transpileModule(read('mobile/src/utils/pickRange.ts'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020}}).outputText, {exports: pr});
assert.equal(pr.PICK_RANGE_MIN_MISS, 0.25);
assert.equal(pr.pickLabel(1, 1), '1.01');
assert.equal(pr.pickLabel(2, 12), '2.12');
// Real saved values (review folder pick_detail.json / values.json, 2026-11-24).
const laResistance = [0.83704, 0.16296, 0, 0, 0, 0]; // viewer, misses in 100%
const version3 = [0, 0, 0, 0.00002, 0.00168, 0.023388]; // viewer, misses in 2.5%
const bcorkLR = [0, 0, 0.0148, 0.0586, 0.1188, 0.0739]; // misses in 26.6%
assert.equal(pr.likelyPickText(1, laResistance, 1), '1.01–1.02');
assert.equal((laResistance[0] * 100).toFixed(1) + '%', '83.7%');
assert.equal(pr.likelyPickText(0.025088, version3, 1), null, 'under 25%: no range');
assert.equal(pr.likelyPickText(0.2661, bcorkLR, 1), '1.04–1.06');
assert.equal(pr.likelyPickText(0.25, bcorkLR, 1), '1.04–1.06', 'exactly 25% shows the range');
assert.equal(pr.likelyPickText(0.2499, bcorkLR, 1), null);
assert.deepEqual(JSON.parse(JSON.stringify(pr.likelyPickSlots(version3))), {low: 6, high: 6});
assert.equal(pr.pickRangeText(1, pr.likelyPickSlots(version3)), '1.06', 'both ends match: one label');
assert.equal(pr.likelyPickText(0.5, version3, 2), '2.06', 'the config\'s draft round');
assert.equal(pr.likelyPickSlots([0, 0, 0]), null, 'a zero sum has no range');
assert.equal(pr.likelyPickSlots([]), null);
assert.equal(pr.likelyPickText(0.9, [0, 0], 1), null);
assert.equal(pr.likelyPickText(null, laResistance, 1), null);
assert.equal(pr.likelyPickText(1, laResistance, undefined), null);
// The section: sentence, then StatRows; the range rows only when likelyPickText gives one.
assert(detail.includes('<Text variant="bodySm">Estimates assume regular-season Max PF draft order.</Text>'));
assert(detail.includes('<StatRow label="Miss playoffs" value={missOddsText(team.nonplayoff_probability, team, 0.1)} />'));
assert(detail.includes('<StatRow label="Pick owner" value={names.get(team.pick_owner_roster_id) ?? `Team ${team.pick_owner_roster_id}`} mono={false} />'));
assert(detail.includes('<StatRow label="Pick" value={`${result.config.draft_season} round ${result.config.draft_round}`} />'));
assert(detail.includes('const likely = likelyPickText(team.nonplayoff_probability, team.pick_probabilities, result.config.draft_round);'));
assert(/\{likely \? <View testID="standings\.pick\.range">\s*<StatRow label="Likely pick if this team misses" value=\{likely\} \/>\s*<StatRow label=\{`Chance of the \$\{pickLabel\(result\.config\.draft_round, 1\)\}`\} value=\{pct\(team\.pick_probabilities\[0\] \?\? 0\)\} \/>\s*<\/View> : null\}/.test(detail),
  'Likely pick and Chance of the <round>.01 rows, gated on the range');
assert(detail.includes("import {StatRow} from './StatRow';"));
// The nested Pick odds and range keeps its three lines; the per-pick list is rows.
for (const kept of ['Current Max PF: {number(team.current_maxpf)} · {number(team.maxpf_per_completed_week)} per week',
  "Projected Max PF, middle 80%: {number(team.maxpf_quantiles['0.1'])}–{number(team.maxpf_quantiles['0.9'])}",
  'Pick odds include the chance of making playoffs.', '<StatRow key={i} label={`Pick ${i + 1}`} value={pct(p)} />']) {
  assert(detail.includes(kept), `Pick odds and range keeps ${kept}`);
}
console.log('league projections: stored reads, model/coverage state, removed comparison UI, Remaining schedule, lineup rows and pick range verified');
