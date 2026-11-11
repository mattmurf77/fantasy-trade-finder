import React, {useState} from 'react';
import {View, Pressable, StyleSheet} from 'react-native';
import {useQuery} from '@tanstack/react-query';
import {Button, Icon, Text} from './chalkline';
import {ink, chalk, ice, space, radii} from '../theme/chalkline';
import {useSession} from '../state/useSession';
import {useFlag} from '../state/useFeatureFlags';
import {getLeagueProjectionBatch, type ProjectionResult, type ProjectionTeam, type ProjectionWeek} from '../api/leagueProjections';

const pct = (n: number) => `${(n * 100).toFixed(1)}%`;
const number = (n: number | null) => n == null ? 'Unavailable' : n.toFixed(1);
const date = (iso: string) => new Date(iso).toLocaleDateString(undefined, {month: 'short', day: 'numeric'});
const statuses: Record<string, string> = {
  no_run: 'Waiting for the first weekly forecast.',
  queued: 'Weekly update queued.', running: 'Weekly update in progress.',
  current: '', stale: 'Weekly update due.',
  refresh_failed: 'Latest update failed.',
  incomplete_projections: 'Missing player or scoring data.',
  unsupported_policy: 'This league’s rules aren’t supported yet.',
  failed: 'Weekly update failed.',
};

function Disclosure({label, children, testID}: {label: string; children: React.ReactNode; testID?: string}) {
  const [open, setOpen] = useState(false);
  return <View style={styles.disclosure}>
    <Pressable accessibilityRole="button" aria-expanded={open} testID={testID}
      onPress={() => setOpen(value => !value)} style={styles.toggle}>
      <Text variant="bodySm" style={[styles.text, styles.toggleLabel]}>{label}</Text>
      <Icon name={open ? 'chevron-up' : 'chevron-down'} size={16} color={chalk.base} />
    </Pressable>
    {open ? <View style={styles.detail}>{children}</View> : null}
  </View>;
}

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
  if (platform !== 'sleeper') return <Text variant="bodySm">Projections are available for Sleeper leagues.</Text>;
  const data = query.data;
  const result = data?.run?.result;
  const state = data?.state || 'no_run';
  const status = query.isLoading ? 'Loading projections…'
    : query.isError ? 'Couldn’t check for an update.'
    : statuses[state] ?? 'Projection unavailable.';
  // A run saved by an older model is last saved, never current.
  const lastSaved = !!result && (query.isError || state !== 'current' || data?.model_current === false);
  const incomplete = result?.coverage?.estimate_status === 'incomplete';
  const missingSlots = result?.coverage?.missing_lineup_slots;
  return <View style={styles.section} testID="league-projections.section">
    <Text variant="heading">Projected standings</Text>
    {status ? <Text variant="bodySm">{status}</Text> : null}
    {result && data?.run ? <>
      <Text variant="bodySm">{[lastSaved ? `Last saved: ${date(result.captured_at)}` : 'Weekly estimate',
        incomplete ? 'Incomplete' : null,
        result.coverage?.estimated ? 'Partial Sleeper data' : null, result.provisional ? 'Provisional' : null].filter(Boolean).join(' · ')}</Text>
      {incomplete ? <Text variant="bodySm" style={styles.text} testID="league-projections.incomplete">{`${missingSlots === 1 ? '1 lineup slot' : `${missingSlots ?? 'Some'} lineup slots`} had no projection for an eligible player, so these odds are incomplete.`}</Text> : null}
      <ProjectionTables key={`${userId}:${leagueId}:${data.run.run_id}`} result={result} />
    </> : !query.isLoading ? <>
      <Text variant="bodySm">Current standings are still available.</Text>
      <Button label="Check for update" variant="secondary" onPress={() => query.refetch()}
        loading={query.isFetching} testID="league-projections.check" />
    </> : null}
  </View>;
}

function ProjectionTables({result}: {result: ProjectionResult}) {
  const [view, setView] = useState<'playoff' | 'draft'>('playoff');
  const [sort, setSort] = useState<'odds' | 'name' | 'record'>('odds');
  const [selected, setSelected] = useState<number | null>(null);
  const teams = [...result.teams].sort((a, b) => view === 'draft' ? a.maxpf_mean - b.maxpf_mean : sort === 'name' ? a.name.localeCompare(b.name) : sort === 'record' ? (b.current_record[0] + .5 * b.current_record[2]) - (a.current_record[0] + .5 * a.current_record[2]) : b.playoff_probability - a.playoff_probability);
  const names = new Map(result.teams.map(t => [t.roster_id, t.name]));
  const pickView = view === 'draft';
  return <>
    <View style={styles.buttons}>
      <ProjectionToggle label="Playoffs" selected={!pickView} onPress={() => { setView('playoff'); setSelected(null); }} />
      <ProjectionToggle label="Non-playoff picks" selected={pickView} onPress={() => { setView('draft'); setSelected(null); }} />
    </View>
    {pickView ? <Text variant="bodySm">Estimates assume regular-season Max PF draft order.</Text> : null}
    <View testID="league-projections.grid">
      <View style={styles.gridRow}>
        <Text variant="bodySm" style={styles.teamCell}>Team</Text>
        <Text variant="bodySm" style={styles.numberCell}>{pickView ? 'Miss playoffs' : 'Playoff odds'}</Text>
        <Text variant="bodySm" style={styles.numberCell}>{pickView ? 'Proj. Max PF' : 'Avg. record'}</Text>
        <View style={styles.chevronSpace} />
      </View>
      {teams.map(team => {
        const primary = pct(pickView ? team.nonplayoff_probability : team.playoff_probability);
        const secondary = pickView ? number(team.maxpf_mean) : team.expected_record.map(n => n.toFixed(1)).join('–');
        const open = selected === team.roster_id;
        return <View key={team.roster_id} style={styles.row}>
          <Pressable accessibilityRole="button" aria-expanded={open}
            accessibilityLabel={`${team.name}. ${primary} ${pickView ? 'chance of missing playoffs' : 'playoff chance'}. ${pickView ? 'Projected Max PF' : 'Average final record'}: ${secondary}.`}
            onPress={() => setSelected(open ? null : team.roster_id)} style={[styles.gridRow, styles.teamButton]}>
            <Text variant="body" style={styles.teamCell}>{team.name}</Text>
            <Text variant="bodySm" style={[styles.numberCell, styles.odds]}>{primary}</Text>
            <Text variant="bodySm" style={[styles.numberCell, styles.text]}>{secondary}</Text>
            <Icon name={open ? 'chevron-up' : 'chevron-down'} size={16} color={chalk.dim} />
          </Pressable>
          {open && <TeamDetail team={team} pickView={pickView} names={names} result={result} />}
        </View>;
      })}
      {teams.length === 0 ? <Text variant="bodySm">No team projections in this forecast.</Text> : null}
    </View>
    {!pickView && <Disclosure label="Sort teams">
      <View style={styles.buttons}>
        <ProjectionToggle label="Playoff odds" selected={sort === 'odds'} onPress={() => setSort('odds')} />
        <ProjectionToggle label="Team name" selected={sort === 'name'} onPress={() => setSort('name')} />
        <ProjectionToggle label="Current record" selected={sort === 'record'} onPress={() => setSort('record')} />
      </View>
      <Text variant="bodySm">Average records come from simulations. Odds don’t confirm a playoff spot.</Text>
    </Disclosure>}
  </>;
}

function ProjectionToggle({label, selected, onPress}: {label: string; selected: boolean; onPress: () => void}) {
  return <Pressable accessibilityRole="button" accessibilityState={{selected}} aria-pressed={selected}
    onPress={onPress} style={[styles.option, selected && styles.activeOption]}>
    <Text variant="bodySm" style={[styles.text, selected && styles.odds]}>{label}</Text>
  </Pressable>;
}

function TeamDetail({team, pickView, names, result}: {team: ProjectionTeam; pickView: boolean; names: Map<number, string>; result: ProjectionResult}) {
  return <View style={styles.detail}>
    {pickView ? <>
      <Text variant="bodySm">Pick owner: {names.get(team.pick_owner_roster_id) ?? `Team ${team.pick_owner_roster_id}`} · {result.config.draft_season} round {result.config.draft_round}</Text>
      <Text variant="bodySm">Expected pick if this team misses: {number(team.conditional_expected_pick)}</Text>
      <Disclosure label="Pick odds and range">
        <Text variant="bodySm">Current Max PF: {number(team.current_maxpf)} · {number(team.maxpf_per_completed_week)} per week</Text>
        <Text variant="bodySm">Projected Max PF, middle 80%: {number(team.maxpf_quantiles['0.1'])}–{number(team.maxpf_quantiles['0.9'])}</Text>
        <Text variant="bodySm">Pick odds include the chance of making playoffs.</Text>
        {team.pick_probabilities.map((p, i) => <Text key={i} variant="bodySm">Pick {i + 1}: {pct(p)}</Text>)}
        <Text variant="bodySm">Missed-playoff simulations: {team.nonplayoff_samples}. This franchise is projected to own {number(team.owner_expected_nonplayoff_picks)} non-playoff picks, with a {pct(team.owner_probability_at_least_one)} chance of at least one.</Text>
      </Disclosure>
    </> : <>
      <Text variant="bodySm">Current: {team.current_record.join('–')} · {number(team.current_points_for)} PF · {number(team.current_ppg)} PPG</Text>
      <Text variant="bodySm">Most likely finish: {team.modal_record.join('–')}{result.playoff_byes > 0 ? ` · Bye odds: ${pct(team.bye_probability)}` : ''}</Text>
      <Disclosure label="Final record odds">
        {team.final_record_distribution.map(r => <Text key={r.record.join('–')} variant="bodySm">{r.record.join('–')}: {pct(r.probability)}</Text>)}
      </Disclosure>
    </>}
    <Disclosure label="Weekly projections">
      {team.weeks.map(w => <Disclosure key={w.week} label={`Week ${w.week} · ${pct(w.win_probability)} win`}>
        <WeekDetail week={w} opponent={names.get(w.opponent_roster_id) ?? `Team ${w.opponent_roster_id}`} />
      </Disclosure>)}
    </Disclosure>
  </View>;
}

function WeekDetail({week: w, opponent}: {week: ProjectionWeek; opponent: string}) {
  const [advanced, setAdvanced] = useState(false);
  return <View style={styles.detail}>
      <Text variant="bodySm" style={styles.text}>vs {opponent}: win {pct(w.win_probability)}, tie {pct(w.tie_probability)}, loss {pct(w.loss_probability)}. {w.actual_score_observed ? `Recorded completed lineup score ${number(w.modeled_score_mean)}.` : `Projected lineup score ${number(w.modeled_score_mean)}; standard deviation ${number(w.modeled_score_sd)}.`}</Text>
      {w.maxpf_floor && <Text variant="bodySm" style={styles.text}>{w.maxpf_floor.policy ? `Max PF target ${number(w.maxpf_floor.target_mean ?? null)}; simulated mean ${number(w.maxpf_floor.simulated_mean)}. Simulation averages vary; predictive uncertainty is not calibrated.` : `Historical model: input Max PF ${number(w.maxpf_floor.input_mean)}; simulated mean ${number(w.maxpf_floor.simulated_mean)}.`}</Text>}
      {w.maxpf_floor?.policy && <Button label={advanced ? 'Hide model diagnostics' : 'Show model diagnostics'} variant="secondary" onPress={() => setAdvanced(!advanced)} testID="league-projections.diagnostics" />}
      {advanced && w.maxpf_floor?.policy && <Text variant="bodySm" style={styles.text}>Latent mean {w.maxpf_floor.latent_maxpf_mean == null ? "not used for a zero target gap" : number(w.maxpf_floor.latent_maxpf_mean)}. Configured latent variance {number(w.maxpf_floor.configured_latent_maxpf_variance ?? null)}; realized model variance {number(w.maxpf_floor.analytic_realized_variance ?? null)}. Latent residual correlation {number(w.maxpf_floor.configured_residual_correlation ?? null)}; sampled total correlation {number(w.maxpf_floor.simulated_correlation ?? null)}. Simulation mean standard error {w.maxpf_floor.simulated_mean_standard_error?.toPrecision(3)}. Rounding mean bound ±{w.maxpf_floor.rounding_mean_error_bound} points. Floor adjustment relative to latent draws {number(w.maxpf_floor.mean_uplift)}; floor activation {pct(w.maxpf_floor.frequency)}.</Text>}
      {w.observed_mean_conditioning?.known_maxpf_floor != null && <Text variant="bodySm" style={styles.text}>An already completed eligible lineup establishes at least {number(w.observed_mean_conditioning.known_maxpf_floor)} Max PF. {w.maxpf_score_observed ? 'Max PF is fully observed for this roster.' : `The target adjustment from that known result is ${number(w.observed_mean_conditioning.target_adjustment)} points.`}</Text>}
      {w.projection_coverage?.estimated && <Text variant="bodySm" style={styles.text}>Available projections: {w.projection_coverage.priced_actual_pool} players for the actual lineup, {w.projection_coverage.priced_maxpf_pool} for Max PF. The lineup uses available contributions; unknown players and rules are not confirmed zeros.</Text>}
      {w.projection_coverage?.complete === false && (w.projection_coverage.missing_actual_slots?.length ?? 0) > 0 && <Text variant="bodySm" style={styles.text}>No projection for an eligible player at: {w.projection_coverage.missing_actual_slots!.join(', ')}.</Text>}
      {w.projection_coverage?.unpriced_players.map(p => <Text key={`unpriced-${p.player_id}`} variant="bodySm" style={styles.text}>{p.name || p.player_id}: no usable estimate ({p.reason.replace(/_/g, ' ')}).</Text>)}
      {w.projection_coverage?.partial_players.map(p => <Text key={`partial-${p.player_id}`} variant="bodySm" style={styles.text}>{p.name || p.player_id}: partial contributions; missing {p.missing_keys.map(k => k.replace(/_/g, ' ')).join(', ')}.</Text>)}
      {w.projection_coverage?.idp_replacement_unavailable && <Text variant="bodySm" style={styles.text}>No hypothetical IDP bye replacement was added because its historical scoring average is unavailable.</Text>}
      {w.actual.lineup.map((r, i) => <Text key={i} variant="bodySm" style={styles.text}>{r.slot}: {r.player ? `${r.player.hypothetical ? 'Hypothetical bye replacement' : r.player.name || r.player.player_id} · ${r.player.points}` : r.unpriced_locked_player ? `Locked starter ${r.unpriced_locked_player.name || r.unpriced_locked_player.player_id}: actual score unavailable` : 'Empty slot'}</Text>)}
      <Text variant="bodySm" style={styles.text}>Available lineup contributions {w.actual.points}; Max PF eligible contributions {w.maxpf.points}.{w.actual_score_observed ? ` Recorded team total ${w.modeled_actual_projection} supplies the actual score; individual missing scores remain unavailable.` : ''}</Text>
      {w.exclusions.map(p => <Text key={p.player_id} variant="bodySm" style={styles.text}>{p.player_id}: {p.reason.replace(/_/g, ' ')}</Text>)}
  </View>;
}
const styles = StyleSheet.create({
  section: {backgroundColor: ink.ink1, padding: space.md, gap: space.sm, borderRadius: radii.sm},
  gridRow: {flexDirection: 'row', alignItems: 'center', gap: space.xs},
  teamCell: {flex: 1, minWidth: 0},
  numberCell: {flexBasis: '26%', flexShrink: 0, textAlign: 'right'},
  chevronSpace: {width: 16},
  row: {borderTopWidth: 1, borderColor: ink.line},
  teamButton: {minHeight: 44, paddingVertical: space.sm},
  text: {color: chalk.base},
  odds: {color: ice.base},
  buttons: {flexDirection: 'row', flexWrap: 'wrap', gap: space.sm},
  option: {minHeight: 44, justifyContent: 'center', paddingHorizontal: space.sm, borderWidth: 1, borderColor: ink.lineStrongA11y, borderRadius: radii.sm},
  activeOption: {borderColor: ice.base, backgroundColor: ink.ink3},
  disclosure: {borderTopWidth: 1, borderTopColor: ink.line},
  toggle: {minHeight: 44, flexDirection: 'row', gap: space.sm, justifyContent: 'space-between', alignItems: 'center'},
  toggleLabel: {flexShrink: 1},
  detail: {gap: space.sm, paddingBottom: space.sm},
});
