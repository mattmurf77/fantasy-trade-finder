import React, {useState} from 'react';
import {View, ScrollView, Pressable, StyleSheet} from 'react-native';
import {useQuery} from '@tanstack/react-query';
import {Button, Text} from './chalkline';
import {ink, chalk, ice, space, radii} from '../theme/chalkline';
import {useSession} from '../state/useSession';
import {useFlag} from '../state/useFeatureFlags';
import {getLeagueProjectionBatch, getLeagueProjectionRun, queueLeagueProjectionScenario, type ProjectionResult, type ProjectionTeam} from '../api/leagueProjections';

const pct = (n: number) => `${(n * 100).toFixed(1)}%`;
const number = (n: number | null) => n == null ? 'Unavailable' : n.toFixed(1);
const statuses: Record<string, string> = {
  no_run: 'Projections are being prepared for a scheduled batch. Current standings remain available.',
  queued: 'This league is queued for a scheduled update.', running: 'This league’s scheduled update is running.',
  current: 'Latest completed projection', stale: 'The next weekly update is due. This is the last completed forecast.',
  refresh_failed: 'The latest update could not finish. The last completed projection is shown below.',
  incomplete_projections: 'Some player or scoring inputs are missing. We cannot calculate a complete projection yet.',
  unsupported_policy: 'Projections are not available for this league’s current data or rule coverage.',
  failed: 'The scheduled update failed. Current standings remain available.',
};

/** Stored batch reads only. Opening standings never generates a forecast. */
export default function LeagueProjectionSection() {
  const leagueId = useSession(s => s.league?.league_id);
  const userId = useSession(s => s.user?.user_id);
  const enabled = useFlag('league.projections');
  const platform = useSession(s => s.leagues.find(l => l.league_id === leagueId)?.platform ?? 'sleeper');
  const query = useQuery({queryKey: ['league-projection-batch', userId, leagueId],
    queryFn: () => getLeagueProjectionBatch(leagueId!), enabled: enabled && platform === 'sleeper' && !!leagueId && !!userId,
    staleTime: 60_000});
  if (!enabled) return null;
  if (platform !== 'sleeper') return <Text variant="bodySm" style={styles.text}>Standing projections currently support Sleeper leagues.</Text>;
  const data = query.data;
  return <View style={styles.section} testID="league-projections.section">
    <Text variant="heading" style={styles.text}>Standings projections</Text>
    <Text variant="bodySm" style={styles.text}>{query.isLoading ? 'Loading saved projections…' : statuses[data?.state || 'no_run'] || 'This projection is unavailable.'}</Text>
    {query.isError ? <Text variant="bodySm" style={styles.text}>Could not read the latest batch. Saved results remain below when available.</Text> : null}
    {data ? <Text variant="bodySm" style={styles.text}>Forecasts update weekly. {data.next_attempt_not_before ? `Next eligible attempt: ${new Date(data.next_attempt_not_before).toLocaleString()}.` : 'An attempt time has not been assigned yet.'} Completion time depends on available inputs.</Text> : null}
    <Button label="Check saved update" variant="secondary" compact onPress={() => query.refetch()} loading={query.isFetching} testID="league-projections.check" />
    {data?.run?.result ? <ProjectionTables key={data.run.run_id} result={data.run.result} baselineRunId={data.run.run_id} /> : <Text variant="bodySm" style={styles.text}>Use Current standings for official records and points while projections are unavailable.</Text>}
  </View>;
}

function ProjectionTables({result, baselineRunId}: {result: ProjectionResult; baselineRunId: string}) {
  const leagueId = useSession(s => s.league?.league_id);
  const userId = useSession(s => s.user?.user_id);
  const [scenarioId, setScenarioId] = useState<string | null>(null);
  const [scenarioMessage, setScenarioMessage] = useState('');
  const scenario = useQuery({queryKey: ['league-projection-scenario', userId, leagueId, scenarioId],
    queryFn: () => getLeagueProjectionRun(scenarioId!), enabled: !!scenarioId,
    refetchInterval: query => ['queued', 'running'].includes(query.state.data?.status || '') ? 30_000 : false});
  async function compare(weight: number) {
    if (!leagueId) return;
    setScenarioMessage('Queueing a comparison using these same saved inputs…');
    try {
      const run = await queueLeagueProjectionScenario(leagueId, {...result.config, historical_weight: weight}, baselineRunId);
      if (useSession.getState().league?.league_id !== leagueId || useSession.getState().user?.user_id !== userId) return;
      setScenarioId(run.run_id); setScenarioMessage('Comparison queued for background processing. The weekly baseline stays unchanged.');
    } catch (_) { setScenarioMessage('Could not queue the comparison. The weekly baseline stays unchanged.'); }
  }
  const [view, setView] = useState<'playoff' | 'draft'>('playoff');
  const [sort, setSort] = useState<'odds' | 'name' | 'record'>('odds');
  const [selected, setSelected] = useState<number | null>(null);
  const teams = [...result.teams].sort((a, b) => view === 'draft' ? a.maxpf_mean - b.maxpf_mean : sort === 'name' ? a.name.localeCompare(b.name) : sort === 'record' ? (b.current_record[0] + .5 * b.current_record[2]) - (a.current_record[0] + .5 * a.current_record[2]) : b.playoff_probability - a.playoff_probability);
  const detail = teams.find(t => t.roster_id === selected);
  return <>
    <Text variant="bodySm" style={styles.text}>{result.league_name} · {result.completed_weeks} completed weeks · {result.playoff_spots} playoff places · {result.playoff_byes} byes</Text>
    <Text variant="bodySm" style={styles.text}>Model estimate{result.provisional ? ' · provisional sample' : ''} · {result.iterations.toLocaleString()} simulations</Text>
    <Text variant="bodySm" style={styles.text}>Inputs: {new Date(result.captured_at).toLocaleString()} · Model {result.model_version}</Text>
    <View style={styles.buttons}><Button label="Playoffs" compact variant="secondary" onPress={() => setView('playoff')} /><Button label="Non-playoff picks" compact variant="secondary" onPress={() => setView('draft')} /></View>
    <Text variant="bodySm" style={styles.text}>{view === 'draft' ? `Sorted by projected Max PF, not final draft order. Ownership: ${result.config.draft_season}, round ${result.config.draft_round}. Pick odds include the chance of reaching the playoffs.` : `Sorted by ${sort === 'odds' ? 'playoff probability' : sort === 'record' ? 'current record' : 'team name'}. Expected records are averages; modal records are the most frequent exact result. Neither proves a clinch.`}</Text>
    {view === 'playoff' ? <View style={styles.buttons}>
      <Button label="Odds" variant="secondary" compact onPress={() => setSort('odds')} />
      <Button label="Team" variant="secondary" compact onPress={() => setSort('name')} />
      <Button label="Record" variant="secondary" compact onPress={() => setSort('record')} />
    </View> : null}
    <ScrollView horizontal testID="league-projections.grid">
      <View>
        <View style={styles.gridRow}>{(view === 'playoff'
          ? ['Team', 'Current W–L–T', 'PF / PPG', 'Expected W–L–T', 'Modal W–L–T', 'Playoffs', 'Bye']
          : ['Original team', 'Current owner', 'Max PF / week', 'Projected Max PF [10–90%]', 'Miss playoffs', ...Array.from({length: teams[0]?.pick_probabilities.length || 0}, (_, i) => `Pick ${i + 1}`,), 'Expected pick if missed']
        ).map(label => <Text key={label} variant="label" style={[styles.tableHeader, styles.cell]}>{label}</Text>)}</View>
        {teams.map(team => {
          const cells = view === 'playoff'
            ? [team.name, team.current_record.join('–'), `${number(team.current_points_for)} / ${number(team.current_ppg)}`, team.expected_record.map(n => n.toFixed(1)).join('–'), team.modal_record.join('–'), pct(team.playoff_probability), pct(team.bye_probability)]
            : [team.name, result.teams.find(t => t.roster_id === team.pick_owner_roster_id)?.name || `Team ${team.pick_owner_roster_id}`, `${number(team.current_maxpf)} / ${number(team.maxpf_per_completed_week)}`, `${number(team.maxpf_mean)} [${number(team.maxpf_quantiles['0.1'])}–${number(team.maxpf_quantiles['0.9'])}]`, pct(team.nonplayoff_probability), ...team.pick_probabilities.map(pct), number(team.conditional_expected_pick)];
          return <Pressable key={team.roster_id} accessibilityRole="button" accessibilityLabel={`Show projection detail for ${team.name}`} onPress={() => setSelected(selected === team.roster_id ? null : team.roster_id)} style={[styles.row, styles.gridRow]}>
            {cells.map((value, i) => <Text key={i} variant="bodySm" style={[styles.text, styles.cell]}>{value}</Text>)}
          </Pressable>;
        })}
      </View>
    </ScrollView>
    {detail ? <TeamDetail team={detail} /> : null}
    <Text variant="heading" style={styles.text}>Compare historical weighting</Text>
    <Text variant="bodySm" style={styles.text}>An explicit comparison uses the same saved inputs and runs separately from the weekly baseline.</Text>
    <View style={styles.buttons}>{[.4, .6, .8].map(weight => <Button key={weight} label={`${weight * 100}%`} compact variant="secondary" onPress={() => compare(weight)} />)}</View>
    {scenarioMessage ? <Text variant="bodySm" style={styles.text}>{scenarioMessage}</Text> : null}
    {scenario.data ? <Text variant="bodySm" style={styles.text}>Comparison status: {scenario.data.status.replace(/_/g, ' ')}</Text> : null}
    {scenario.data?.result?.teams.map(t => <Text key={t.roster_id} variant="bodySm" style={styles.text}>{t.name}: baseline {pct(result.teams.find(b => b.roster_id === t.roster_id)!.playoff_probability)}, comparison {pct(t.playoff_probability)} playoffs; conditional expected pick {number(t.conditional_expected_pick)}.</Text>)}
    <Text variant="heading" style={styles.text}>Assumptions and coverage</Text>
    <Text variant="bodySm" style={styles.text}>Historical weight: {Number(result.config.historical_weight) * 100}%. IR in Max PF: {result.config.ir_maxpf === 'include' ? 'included' : 'excluded'}. Current reserves and taxi stay out of actual lineups; taxi remains eligible for Max PF. Draft ties use a randomized scenario. Residual correlation: {String(result.config.residual_correlation)}. Variance source: {result.config.maxpf_variance === 'actual_history_proxy' ? 'actual-score history proxy' : 'reconstructed Max PF history'}.</Text>
    <Text variant="bodySm" style={styles.text}>Scoring: {Object.entries(result.scoring).filter(([,v]) => v !== 0).map(([k,v]) => `${k.replace(/_/g, ' ')} ${v}`).join('; ')}</Text>
    {result.warnings.map(w => <Text key={w} variant="bodySm" style={styles.text}>{w}</Text>)}
  </>;
}
function TeamDetail({team}: {team: ProjectionTeam}) {
  return <View style={styles.detail}>
    <Text variant="heading" style={styles.text}>{team.name}</Text>
    <Text variant="bodySm" style={styles.text}>Missed-playoff samples: {team.nonplayoff_samples}. {team.name}’s own franchise portfolio — expected non-playoff pick count: {number(team.owner_expected_nonplayoff_picks)}; chance of at least one: {pct(team.owner_probability_at_least_one)}.</Text>
    <Text variant="bodySm" style={styles.text}>Final record distribution: {team.final_record_distribution.map(r => `${r.record.join('–')}: ${pct(r.probability)}`).join('; ')}</Text>
    {team.weeks.map(w => <View key={w.week} style={styles.detail}>
      <Text variant="bodySm" style={styles.text}>Week {w.week} vs Team {w.opponent_roster_id}: win {pct(w.win_probability)}, tie {pct(w.tie_probability)}, loss {pct(w.loss_probability)}. Modeled score {number(w.modeled_score_mean)}; standard deviation {number(w.modeled_score_sd)}.</Text>
      {w.maxpf_floor && <Text variant="bodySm" style={styles.text}>Max PF before floor {number(w.maxpf_floor.input_mean)}; simulated mean {number(w.maxpf_floor.simulated_mean)}. Floor adds {number(w.maxpf_floor.mean_uplift)} points on average ({pct(w.maxpf_floor.frequency)} of scenarios).</Text>}
      {w.actual.lineup.map((r, i) => <Text key={i} variant="bodySm" style={styles.text}>{r.slot}: {r.player ? `${r.player.hypothetical ? 'Hypothetical bye replacement' : r.player.name || r.player.player_id} · ${r.player.points}` : 'Empty slot'}</Text>)}
      <Text variant="bodySm" style={styles.text}>Optimized lineup {w.actual.points}; Max PF eligible lineup {w.maxpf.points}. Historical blending can cushion an empty slot.</Text>
      {w.exclusions.map(p => <Text key={p.player_id} variant="bodySm" style={styles.text}>{p.player_id}: {p.reason.replace(/_/g, ' ')}</Text>)}
    </View>)}
  </View>;
}
const styles = StyleSheet.create({section: {backgroundColor: ink.ink1, padding: space.md, gap: space.sm, borderRadius: radii.sm},
  gridRow: {flexDirection: 'row'}, cell: {width: 140, paddingHorizontal: space.sm},
  text: {color: chalk.base}, buttons: {flexDirection: 'row', gap: space.sm}, row: {minHeight: 44, justifyContent: 'center'},
  tableHeader: {color: ice.base, paddingVertical: space.sm}, detail: {gap: space.sm, paddingVertical: space.sm}});
