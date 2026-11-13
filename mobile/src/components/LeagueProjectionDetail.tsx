import React, {useRef, useState} from 'react';
import {View, Pressable, StyleSheet} from 'react-native';
import {Button, Icon, Text} from './chalkline';
import {ink, chalk, space} from '../theme/chalkline';
import type {ProjectionResult, ProjectionTeam, ProjectionWeek} from '../api/leagueProjections';
import type {MaxPfMoves} from '../api/leagueProjections';
import {lineupRowText} from '../utils/projectionCoverage';
import {MAXPF_COPY} from '../utils/maxPfMovesCopy';
import {sectionMounts, isOwnCard, deriveSection} from '../utils/maxPfMoves';
import {MaxPfMovesBody} from './MaxPfMovesSection';
import {missOddsText} from '../utils/playoffOdds';

// The saved forecast's per-team detail, mounted inside the Standings table's
// open team (screens/StandingsScreen). Moved from the retired
// LeagueProjectionSection: the text of every sub-section is unchanged. Reads
// nothing; the screen owns the one forecast query.

const pct = (n: number) => `${(n * 100).toFixed(1)}%`;
const number = (n: number | null) => n == null ? 'Unavailable' : n.toFixed(1);

function Disclosure({label, children, testID, initialOpen = false}: {label: string; children: React.ReactNode; testID?: string; initialOpen?: boolean}) {
  const [open, setOpen] = useState(initialOpen);
  return <View style={styles.disclosure}>
    <Pressable accessibilityRole="button" aria-expanded={open} testID={testID}
      onPress={() => setOpen(value => !value)} style={styles.toggle}>
      <Text variant="bodySm" style={[styles.text, styles.toggleLabel]}>{label}</Text>
      <Icon name={open ? 'chevron-up' : 'chevron-down'} size={16} color={chalk.base} />
    </Pressable>
    {open ? <View style={styles.detail}>{children}</View> : null}
  </View>;
}

/** Max PF moves inputs for the viewer's own card (contract §2); the screen
 *  owns the forecast and roster queries and the flag read. */
export interface MaxPfMovesProps {
  block: MaxPfMoves | null | undefined; flagOn: boolean; isSleeper: boolean;
  liveRosterIds: string[] | null; leagueId: string | null; userId: string | null;
}

/** Final record odds, Weekly projections, Draft pick odds and, on the
 *  viewer's own card only, Max PF moves for one team. */
export function ProjectionTeamDetail({team, result, maxPf}: {team: ProjectionTeam; result: ProjectionResult; maxPf?: MaxPfMovesProps}) {
  const names = new Map(result.teams.map(t => [t.roster_id, t.name]));
  // Fires maxpf_moves_viewed once per opening of this card (it unmounts on close).
  const maxPfViewed = useRef(false);
  const moves = maxPf?.block && maxPf.leagueId && sectionMounts({
    block: maxPf.block, flagOn: maxPf.flagOn, isSleeper: maxPf.isSleeper,
    ownCard: isOwnCard(team.roster_id, result.viewer_roster_id, maxPf.block),
  }) ? {block: maxPf.block, leagueId: maxPf.leagueId, model: deriveSection(maxPf.block, maxPf.liveRosterIds)} : null;
  return <View style={styles.sections} testID="standings.open.detail">
    <Disclosure label="Final record odds">
      {team.final_record_distribution.map(r => <Text key={r.record.join('–')} variant="bodySm">{r.record.join('–')}: {pct(r.probability)}</Text>)}
    </Disclosure>
    <Disclosure label="Weekly projections">
      {team.weeks.map(w => <Disclosure key={w.week} label={`Week ${w.week} · ${pct(w.win_probability)} win`}>
        <WeekDetail week={w} opponent={names.get(w.opponent_roster_id) ?? `Team ${w.opponent_roster_id}`} />
      </Disclosure>)}
    </Disclosure>
    <Disclosure label="Draft pick odds">
      <Text variant="bodySm">Estimates assume regular-season Max PF draft order.</Text>
      <Text variant="bodySm">Miss playoffs: {missOddsText(team.nonplayoff_probability, team, 0.1)}</Text>
      <Text variant="bodySm">Pick owner: {names.get(team.pick_owner_roster_id) ?? `Team ${team.pick_owner_roster_id}`} · {result.config.draft_season} round {result.config.draft_round}</Text>
      <Text variant="bodySm">Expected pick if this team misses: {number(team.conditional_expected_pick)}</Text>
      <Disclosure label="Pick odds and range">
        <Text variant="bodySm">Current Max PF: {number(team.current_maxpf)} · {number(team.maxpf_per_completed_week)} per week</Text>
        <Text variant="bodySm">Projected Max PF, middle 80%: {number(team.maxpf_quantiles['0.1'])}–{number(team.maxpf_quantiles['0.9'])}</Text>
        <Text variant="bodySm">Pick odds include the chance of making playoffs.</Text>
        {team.pick_probabilities.map((p, i) => <Text key={i} variant="bodySm">Pick {i + 1}: {pct(p)}</Text>)}
        <Text variant="bodySm">Missed-playoff simulations: {team.nonplayoff_samples}. This franchise is projected to own {number(team.owner_expected_nonplayoff_picks)} non-playoff picks, with a {pct(team.owner_probability_at_least_one)} chance of at least one.</Text>
      </Disclosure>
    </Disclosure>
    {moves ? <Disclosure label={MAXPF_COPY['C-TITLE']} testID="standings.maxpf.toggle" initialOpen={moves.model.initialOpen}>
      <MaxPfMovesBody block={moves.block} model={moves.model} leagueId={moves.leagueId} userId={maxPf?.userId ?? null} viewedRef={maxPfViewed} />
    </Disclosure> : null}
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
      {w.projection_coverage?.complete === false && (w.projection_coverage.missing_actual_slots?.length ?? 0) > 0 && <Text variant="bodySm" style={styles.text}>Score not recorded yet at: {w.projection_coverage.missing_actual_slots!.join(', ')}.</Text>}
      {w.projection_coverage?.unpriced_players.map(p => <Text key={`unpriced-${p.player_id}`} variant="bodySm" style={styles.text}>{p.name || p.player_id}: no usable estimate ({p.reason.replace(/_/g, ' ')}).</Text>)}
      {w.projection_coverage?.partial_players.map(p => <Text key={`partial-${p.player_id}`} variant="bodySm" style={styles.text}>{p.name || p.player_id}: partial contributions; missing {p.missing_keys.map(k => k.replace(/_/g, ' ')).join(', ')}.</Text>)}
      {w.projection_coverage?.idp_replacement_unavailable && <Text variant="bodySm" style={styles.text}>No hypothetical IDP bye replacement was added because its historical scoring average is unavailable.</Text>}
      {w.actual.lineup.map((r, i) => <Text key={i} variant="bodySm" style={styles.text}>{lineupRowText(r, i, w.projection_coverage?.free_agent_fills)}</Text>)}
      <Text variant="bodySm" style={styles.text}>Available lineup contributions {w.actual.points}; Max PF eligible contributions {w.maxpf.points}.{w.actual_score_observed ? ` Recorded team total ${w.modeled_actual_projection} supplies the actual score; individual missing scores remain unavailable.` : ''}</Text>
      {w.exclusions.map(p => <Text key={p.player_id} variant="bodySm" style={styles.text}>{p.player_id}: {p.reason.replace(/_/g, ' ')}</Text>)}
  </View>;
}

// Indented, with a quieter separator (ink-3 on the open card's ink-2) than
// the table's row hairline, so a sub-section never reads as another team.
const styles = StyleSheet.create({
  sections: {paddingLeft: space.md},
  text: {color: chalk.base},
  disclosure: {borderTopWidth: 1, borderTopColor: ink.ink3},
  toggle: {minHeight: 44, flexDirection: 'row', gap: space.sm, justifyContent: 'space-between', alignItems: 'center'},
  toggleLabel: {flexShrink: 1},
  detail: {gap: space.sm, paddingBottom: space.sm},
});
