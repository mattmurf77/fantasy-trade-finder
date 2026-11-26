import React, {useRef, useState} from 'react';
import {View, Pressable, StyleSheet} from 'react-native';
import {Icon, Text} from './chalkline';
import {StatRow} from './StatRow';
import {ink, chalk, ice, fonts, space, type} from '../theme/chalkline';
import type {ProjectionResult, ProjectionTeam, ProjectionWeek} from '../api/leagueProjections';
import type {MaxPfMoves, PlayoffTargets} from '../api/leagueProjections';
import {lineupRowParts, scheduleRows, SCHEDULE_COPY as S, type ScheduleRow} from '../utils/projectionCoverage';
import {likelyPickText, pickLabel} from '../utils/pickRange';
import {MAXPF_COPY} from '../utils/maxPfMovesCopy';
import {sectionMounts, isOwnCard, deriveSection} from '../utils/maxPfMoves';
import {MaxPfMovesBody} from './MaxPfMovesSection';
import {TARGETS_COPY} from '../utils/playoffTargetsCopy';
import {sectionMounts as targetsMount, deriveSection as deriveTargets, type LiveRoster} from '../utils/playoffTargets';
import {PlayoffTargetsBody} from './PlayoffTargetsSection';
import {missOddsText} from '../utils/playoffOdds';
import {DIRECTION_COPY} from '../utils/directionPagesCopy';

// The saved forecast's per-team detail, mounted inside the Standings table's
// open team (screens/StandingsScreen). Moved from the retired
// LeagueProjectionSection. Reads nothing; the screen owns the one forecast
// query.

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

/** Playoff targets inputs for the viewer's own card (the mirror of
 *  MaxPfMovesProps); `liveRosters` is the page's roster query, every team. */
export interface PlayoffTargetsProps {
  block: PlayoffTargets | null | undefined; flagOn: boolean; isSleeper: boolean;
  liveRosters: LiveRoster[] | null;
}

/** Improve pages (direction-pages spec P-13): with `league.direction_pages`
 *  on, the screen passes these and each of the two sections becomes a single
 *  row that opens its page. Absent (flag off): both sections render in full,
 *  exactly as before. */
export interface PageLinkProps {draftPick: () => void; playoffs: () => void}

/** Final record odds, Remaining schedule, Draft pick odds and, on the
 *  viewer's own card only, Max PF moves and Playoff targets for one team. */
export function ProjectionTeamDetail({team, result, maxPf, targets, pageLinks}: {team: ProjectionTeam; result: ProjectionResult; maxPf?: MaxPfMovesProps; targets?: PlayoffTargetsProps; pageLinks?: PageLinkProps}) {
  const names = new Map(result.teams.map(t => [t.roster_id, t.name]));
  // Fires playoff_targets_viewed once per opening of this card.
  const targetsViewed = useRef(false);
  const targetsMounted = targets?.block && targetsMount({
    block: targets.block, flagOn: targets.flagOn, isSleeper: targets.isSleeper,
    ownCard: isOwnCard(team.roster_id, result.viewer_roster_id ?? targets.block.viewer_roster_id),
  }) ? {block: targets.block, model: deriveTargets(targets.block, targets.liveRosters)} : null;
  // P-13: a link row replaces the inline section while pageLinks is set.
  const playoffTargets = pageLinks ? null : targetsMounted;
  // Fires maxpf_moves_viewed once per opening of this card (it unmounts on close).
  const maxPfViewed = useRef(false);
  const movesMounted = maxPf?.block && maxPf.leagueId && sectionMounts({
    block: maxPf.block, flagOn: maxPf.flagOn, isSleeper: maxPf.isSleeper,
    ownCard: isOwnCard(team.roster_id, result.viewer_roster_id, maxPf.block),
  }) ? {block: maxPf.block, leagueId: maxPf.leagueId, model: deriveSection(maxPf.block, maxPf.liveRosterIds)} : null;
  const moves = pageLinks ? null : movesMounted;
  const likely = likelyPickText(team.nonplayoff_probability, team.pick_probabilities, result.config.draft_round);
  return <View style={styles.sections} testID="standings.open.detail">
    <Disclosure label="Final record odds">
      {team.final_record_distribution.map(r => <Text key={r.record.join('–')} variant="bodySm">{r.record.join('–')}: {pct(r.probability)}</Text>)}
    </Disclosure>
    <Disclosure label={S.title}>
      <RemainingSchedule team={team} result={result} />
    </Disclosure>
    <Disclosure label="Draft pick odds">
      <Text variant="bodySm">Estimates assume regular-season Max PF draft order.</Text>
      <View>
        <StatRow label="Miss playoffs" value={missOddsText(team.nonplayoff_probability, team, 0.1)} />
        <StatRow label="Pick owner" value={names.get(team.pick_owner_roster_id) ?? `Team ${team.pick_owner_roster_id}`} mono={false} />
        <StatRow label="Pick" value={`${result.config.draft_season} round ${result.config.draft_round}`} />
      </View>
      {likely ? <View testID="standings.pick.range">
        <StatRow label="Likely pick if this team misses" value={likely} />
        <StatRow label={`Chance of the ${pickLabel(result.config.draft_round, 1)}`} value={pct(team.pick_probabilities[0] ?? 0)} />
      </View> : null}
      <Disclosure label="Pick odds and range">
        <Text variant="bodySm">Current Max PF: {number(team.current_maxpf)} · {number(team.maxpf_per_completed_week)} per week</Text>
        <Text variant="bodySm">Projected Max PF, middle 80%: {number(team.maxpf_quantiles['0.1'])}–{number(team.maxpf_quantiles['0.9'])}</Text>
        <Text variant="bodySm">Pick odds include the chance of making playoffs.</Text>
        <View>{team.pick_probabilities.map((p, i) => <StatRow key={i} label={`Pick ${i + 1}`} value={pct(p)} />)}</View>
      </Disclosure>
    </Disclosure>
    {moves ? <Disclosure label={MAXPF_COPY['C-TITLE']} testID="standings.maxpf.toggle" initialOpen={moves.model.initialOpen}>
      <MaxPfMovesBody block={moves.block} model={moves.model} leagueId={moves.leagueId} userId={maxPf?.userId ?? null} viewedRef={maxPfViewed} />
    </Disclosure> : null}
    {playoffTargets ? <Disclosure label={TARGETS_COPY['C-TITLE']} testID="standings.targets.toggle" initialOpen={playoffTargets.model.initialOpen}>
      <PlayoffTargetsBody block={playoffTargets.block} model={playoffTargets.model} viewedRef={targetsViewed} />
    </Disclosure> : null}
    {movesMounted && pageLinks ? <PageLink label={MAXPF_COPY['C-TITLE']} hint={DIRECTION_COPY['TITLE.draft_pick']}
      onPress={pageLinks.draftPick} testID="standings.maxpf.link" /> : null}
    {targetsMounted && pageLinks ? <PageLink label={TARGETS_COPY['C-TITLE']} hint={DIRECTION_COPY['TITLE.playoffs']}
      onPress={pageLinks.playoffs} testID="standings.targets.link" /> : null}
  </View>;
}

/** A Disclosure-shaped row that opens a page instead ("Max PF moves ›"). */
function PageLink({label, hint, onPress, testID}: {label: string; hint: string; onPress: () => void; testID: string}) {
  return <View style={styles.disclosure}>
    <Pressable accessibilityRole="button" accessibilityHint={DIRECTION_COPY['HINT.opens'].replace('{title}', hint)}
      testID={testID} onPress={onPress} style={styles.toggle}>
      <Text variant="bodySm" style={[styles.text, styles.toggleLabel]}>{label}</Text>
      <Icon name="chevron-right" size={16} color={chalk.base} />
    </Pressable>
  </View>;
}

/** The matchup table: one row per remaining week, each its own expand
 *  control for that week's projected lineup. */
function RemainingSchedule({team, result}: {team: ProjectionTeam; result: ProjectionResult}) {
  const [openWeek, setOpenWeek] = useState<number | null>(null);
  const {fallback, rows} = scheduleRows(team, result.teams);
  if (rows.length === 0) return <Text variant="bodySm" style={styles.text}>{S.none}</Text>;
  const lastHead = fallback ? S.edge : S.win;
  return <View>
    <View style={[styles.mRow, styles.mHead]}>
      <Text scale="dense" style={[type.label, styles.wk]}>{S.week}</Text>
      <Text scale="dense" style={[type.label, styles.opp]} numberOfLines={1}>{S.opponent}</Text>
      <Text scale="dense" style={[type.label, styles.num]}>{S.own}</Text>
      <Text scale="dense" style={[type.label, styles.num]}>{S.opp}</Text>
      <Text scale="dense" style={[type.label, styles.last]}>{lastHead}</Text>
      <View style={styles.chev} />
    </View>
    {rows.map(r => {
      const open = openWeek === r.week;
      const week = team.weeks.find(w => w.week === r.week)!;
      return <React.Fragment key={r.week}>
        <ScheduleRowButton row={r} open={open} lastHead={lastHead} onPress={() => setOpenWeek(open ? null : r.week)} />
        {open ? <WeekDetail week={week} /> : null}
      </React.Fragment>;
    })}
  </View>;
}

function ScheduleRowButton({row: r, open, lastHead, onPress}: {row: ScheduleRow; open: boolean; lastHead: string; onPress: () => void}) {
  return <Pressable accessibilityRole="button" aria-expanded={open} testID={`standings.schedule.week.${r.week}`}
    accessibilityLabel={`Week ${r.week}, against ${r.opponent}. Projected ${r.own} to ${r.opp}. ${lastHead === S.win ? `${r.last} chance to win` : `${lastHead} ${r.last}`}.`}
    onPress={onPress} style={[styles.mRow, styles.mTap, open ? styles.mOpen : null]}>
    <Text scale="dense" style={[styles.mono, styles.wk]}>{r.week}</Text>
    <Text variant="bodySm" style={[styles.text, styles.opp]} numberOfLines={1}>{r.opponent}</Text>
    <Text scale="dense" style={[styles.mono, styles.num]}>{r.own}</Text>
    <Text scale="dense" style={[styles.mono, styles.num]}>{r.opp}</Text>
    <Text scale="dense" style={[styles.mono, styles.strong, styles.last]}>{r.last}</Text>
    <View style={styles.chev}><Icon name={open ? 'chevron-up' : 'chevron-down'} size={16} color={open ? ice.base : chalk.dim} /></View>
  </Pressable>;
}

/** An opened week: the projected lineup, then any players with no estimate. */
function WeekDetail({week: w}: {week: ProjectionWeek}) {
  const unpriced = w.projection_coverage?.unpriced_players ?? [];
  return <View style={styles.weekDetail}>
    {w.actual.lineup.map((r, i) => {
      const row = lineupRowParts(r, i, w.projection_coverage?.free_agent_fills);
      return <View key={i} style={styles.lRow}>
        <Text scale="dense" style={[type.label, styles.slot]} numberOfLines={1}>{row.slot}</Text>
        <View style={styles.lName}>
          <Text variant="bodySm" style={[styles.text, styles.shrink]} numberOfLines={1}>{row.name}</Text>
          {row.freeAgent ? <Text scale="dense" style={styles.muted}>{S.freeAgent}</Text> : null}
        </View>
        <Text scale="dense" style={[styles.mono, styles.points]}>{row.points}</Text>
      </View>;
    })}
    {unpriced.map((p, i) => <View key={`unpriced-${p.player_id}`} style={[styles.lRow, i === 0 ? styles.lFirstNoEst : null]}>
      <View style={styles.slot} />
      <Text variant="bodySm" style={[styles.text, styles.opp]} numberOfLines={1}>{p.name || p.player_id}</Text>
      <Text scale="dense" style={[styles.muted, styles.noEst]}>{S.noEstimate}</Text>
    </View>)}
  </View>;
}

// Remaining schedule column widths (pt).
const WK_W = 26, NUM_W = 48, LAST_W = 44, CHEV_W = 16, COL_GAP = 4, SLOT_W = 44;

// Indented, with a quieter separator (ink-3 on the open card's ink-2) than
// the table's row hairline, so a sub-section never reads as another team.
const styles = StyleSheet.create({
  sections: {paddingLeft: space.md},
  text: {color: chalk.base},
  disclosure: {borderTopWidth: 1, borderTopColor: ink.ink3},
  toggle: {minHeight: 44, flexDirection: 'row', gap: space.sm, justifyContent: 'space-between', alignItems: 'center'},
  toggleLabel: {flexShrink: 1},
  detail: {gap: space.sm, paddingBottom: space.sm},
  // Remaining schedule: fixed numeric columns so every week lines up; the
  // chevron has its own column (a blank cell in the heading row).
  mRow: {flexDirection: 'row', alignItems: 'center', gap: COL_GAP},
  mHead: {minHeight: 20, borderBottomWidth: 1, borderBottomColor: ink.ink3},
  mTap: {minHeight: 44, borderBottomWidth: 1, borderBottomColor: ink.ink3},
  mOpen: {backgroundColor: ink.ink3},
  wk: {width: WK_W},
  opp: {flex: 1, minWidth: 0},
  num: {width: NUM_W, textAlign: 'right'},
  last: {width: LAST_W, textAlign: 'right'},
  chev: {width: CHEV_W, alignItems: 'center'},
  mono: {...type.data},
  strong: {fontFamily: fonts.dataSemi},
  // The opened week, indented past the week column; points end under Win %.
  weekDetail: {paddingLeft: WK_W + COL_GAP, paddingTop: space.xs, paddingBottom: space.sm, borderBottomWidth: 1, borderBottomColor: ink.ink3},
  lRow: {flexDirection: 'row', alignItems: 'center', gap: space.sm, minHeight: 24},
  lFirstNoEst: {borderTopWidth: 1, borderTopColor: ink.ink3},
  slot: {width: SLOT_W},
  lName: {flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'baseline', gap: space.xs},
  shrink: {flexShrink: 1},
  muted: {...type.bodySm, fontSize: 12, color: chalk.dim},
  points: {width: NUM_W, textAlign: 'right', marginRight: CHEV_W + COL_GAP},
  noEst: {textAlign: 'right', marginRight: CHEV_W + COL_GAP},
});
