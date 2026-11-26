import React, { useMemo, useState } from 'react';
import { View, ScrollView, Pressable, ActivityIndicator, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { useNavigation } from '@react-navigation/native';

import Text from '../components/chalkline/Text';
import { Badge, Button, Icon } from '../components/chalkline';
import FeedbackFAB from '../components/FeedbackFAB';
import { ProjectionTeamDetail } from '../components/LeagueProjectionDetail';
import { StatRow } from '../components/StatRow';
import { ink, chalk, ice, space, radii, type, fonts } from '../theme/chalkline';
import { getLeagueRosters, getLeagueUsers, findMyRoster } from '../api/sleeper';
import { getLeagueProjectionBatch } from '../api/leagueProjections';
import { track } from '../api/events';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import { currentStandings } from '../utils/standings';
import {
  buildTableRows, sortRows, nextSort, cellText, openTeamStats, noForecastLine,
  VIEW_COLUMNS, DEFAULT_SORT, COLUMN_LABEL, COLUMN_SPOKEN, DASH,
  type StandingsView, type StandingsColumn,
} from '../utils/standingsTable';

// Standings (Home hub, flag `nav.home_hub`; docs/plans/home-engagement/
// scope-standings-table.md). A ROOT-STACK push from Home's Standings row, the
// playoff tile and League rankings' tile: Back returns to the page that
// opened it, so it mounts its own FeedbackFAB and RootNav gives it the league
// selector header (LeagueTopBarHeader) over an explicit HeaderBack (RNS#3294).
//
// ONE TABLE, one row per team. The current results come from the Sleeper
// rosters session init already seeded (utils/standings.ts: W–L, PF, Max PF),
// joined by roster id to the SAVED weekly forecast (Proj. W–L, Playoffs,
// Proj. Max PF, SoS). A Record | Points pill picks which numbers show; every
// heading sorts (utils/standingsTable.ts). No forecast ⇒ those columns are a
// dash and one line says why.
//
// NO SIMULATION FROM THIS PAGE. The forecast is a stored weekly result on
// the one cached read Home's and League rankings' playoff tiles share
// (['league-projection-batch', userId, leagueId]); opening the page only
// reads it. With `league.projections` off there is no forecast read at all:
// the 10,000-sim season outlook (`outlook.odds`) lives on League rankings.
//
// The route still accepts `{ segment }` (installed builds and deep links may
// send it); there are no segments, so the screen never reads it.

// Display names for the non-Sleeper unavailable card.
const PLATFORM_NAME: Record<string, string> = {
  espn: 'ESPN',
  mfl: 'MFL',
  fleaflicker: 'Fleaflicker',
};

const date = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

// Numeric column widths (pt). A heading is exactly this wide, so a long one
// wraps to two lines ("Proj." over "W–L" / "Max PF", "Play" over "offs"); a
// number cell is AT LEAST this wide, so a number never truncates and, at large
// text sizes, the team column (flex: 1, ellipsis) gives way instead. Record
// columns are sized to their widest real cell or their heading plus the 12pt
// sort caret (10pt arrow + 2pt gap), whichever is larger, plus about 1pt for
// text rounding: W–L "8–5–1" 39; "PROJ." 38 + 12; "OFFS" 33 + 12; "SoS" 24 + 12
// (cells "12th" 31, "easy" 23). On a 375pt phone: 375 − 2×16 page padding − 2×4
// row padding − 16 chevron = 319pt; Record 40+51+46+37 and five 4pt gaps leave
// the team 125pt, Points 48+60+60 and four gaps leave it 135pt.
const COL_WIDTH: Record<StandingsColumn, number> = {
  team: 0, wl: 40, projWl: 51, playoffs: 46, sos: 37, pf: 48, maxPf: 60, projMaxPf: 60,
};
const CHEVRON = 16;

export default function StandingsScreen() {
  const leagueId = useSession((s) => s.league?.league_id) || null;
  const userId = useSession((s) => s.user?.user_id ?? null);
  // League Summary's platform rule (LeagueSummaryScreen `outlookSupported`):
  // unknown resolves to Sleeper, i.e. supported.
  const platform =
    useSession((s) => s.leagues.find((l) => l.league_id === leagueId)?.platform) ?? 'sleeper';
  const isSleeper = platform === 'sleeper';
  const batchProjections = useFlag('league.projections');
  const maxPfMovesOn = useFlag('league.max_pf_moves');
  const playoffTargetsOn = useFlag('league.playoff_targets');
  // Improve pages (direction-pages spec P-13): with the flag on, the two
  // sections on the viewer's own card become rows that open the pages. Off:
  // `pageLinks` is undefined and the card is exactly as before.
  const directionPagesOn = useFlag('league.direction_pages');
  const navigation = useNavigation<any>();
  const pageLinks = directionPagesOn ? {
    draftPick: () => navigation.navigate('ImproveDraftPick', { source: 'standings' }),
    playoffs: () => navigation.navigate('ImprovePlayoffChances', { source: 'standings' }),
  } : undefined;

  // View and per-view sort live as long as the screen is mounted, so a
  // league switch in the header keeps them.
  const [view, setView] = useState<StandingsView>('record');
  const [sorts, setSorts] = useState(DEFAULT_SORT);
  // The open team remembers its league: a roster id repeats across leagues,
  // so after a switch nothing is open (no effect needed).
  const [open, setOpen] = useState<{ leagueId: string; rosterId: number } | null>(null);

  // Same keys, fetchers and staleTime as every other Sleeper-roster consumer
  // (check-session-seed.js S-2), so the session-init seed is what renders.
  const rostersQuery = useQuery({
    queryKey: ['league-rosters', leagueId],
    queryFn: () => getLeagueRosters(leagueId!),
    enabled: isSleeper && !!leagueId,
    staleTime: 5 * 60_000,
  });
  const usersQuery = useQuery({
    queryKey: ['league-users', leagueId],
    queryFn: () => getLeagueUsers(leagueId!),
    enabled: isSleeper && !!leagueId,
    staleTime: 5 * 60_000,
  });
  // Stored batch reads only. Opening standings never generates a forecast.
  const forecastEnabled = batchProjections && isSleeper && !!leagueId && !!userId;
  const forecastQuery = useQuery({
    queryKey: ['league-projection-batch', userId, leagueId],
    queryFn: () => getLeagueProjectionBatch(leagueId!),
    enabled: forecastEnabled,
    staleTime: 60_000,
  });

  const standings = useMemo(() => {
    const rosters = rostersQuery.data;
    if (!rosters) return null;
    const myRosterId = userId ? findMyRoster(rosters, userId)?.roster_id ?? null : null;
    return currentStandings(rosters, usersQuery.data ?? [], myRosterId);
  }, [rostersQuery.data, usersQuery.data, userId]);

  // Max PF moves' roster-changed check (contract §6.3): the viewer's live
  // Sleeper roster from the query above; null until it loads (no check).
  const liveRosterIds = useMemo(() => {
    const rosters = rostersQuery.data;
    return rosters && userId ? findMyRoster(rosters, userId)?.players ?? null : null;
  }, [rostersQuery.data, userId]);

  const data = forecastEnabled ? forecastQuery.data : undefined;
  const result = data?.run?.result ?? null;
  const rows = useMemo(
    () => (standings ? buildTableRows(standings.rows, result?.teams ?? null) : []),
    [standings, result],
  );
  const sort = sorts[view];
  const sorted = useMemo(() => sortRows(rows, sort), [rows, sort]);
  const openRosterId = open && open.leagueId === leagueId ? open.rosterId : null;

  // A lens switch on a read-only page: fires on a CHANGING tap only, never
  // on mount and never on a re-tap of the active view. Closes the open team.
  const selectView = (next: StandingsView) => {
    if (next === view) return;
    track('standings_segment_changed', { segment: next }, 'Standings');
    setView(next);
    setOpen(null);
  };
  const onSort = (column: StandingsColumn) =>
    setSorts((s) => ({ ...s, [view]: nextSort(s[view], column) }));
  const toggleTeam = (rosterId: number) =>
    setOpen(openRosterId === rosterId || !leagueId ? null : { leagueId, rosterId });

  const platformName = PLATFORM_NAME[platform];

  let body: React.ReactNode;
  if (!isSleeper || (standings && !standings.hasRecords)) {
    body = (
      <View style={styles.card} testID="standings.current.unavailable">
        <Text variant="heading" style={styles.cardTitle}>
          {platformName ? `${platformName} standings coming` : 'Standings coming'}
        </Text>
        <Text variant="bodySm">
          Fleeced can’t read this league’s standings yet. Overall rank and the trade market work as usual.
        </Text>
      </View>
    );
  } else if (rostersQuery.isLoading || usersQuery.isLoading) {
    body = (
      <View style={styles.center}>
        <ActivityIndicator color={ice.base} />
      </View>
    );
  } else if (!standings) {
    body = (
      <View style={styles.center}>
        <Text variant="bodySm" style={styles.centerBody}>
          Couldn’t load standings.
        </Text>
        <Button
          label="Try again"
          variant="secondary"
          compact
          loading={rostersQuery.isFetching}
          onPress={() => {
            rostersQuery.refetch();
            usersQuery.refetch();
          }}
        />
      </View>
    );
  } else {
    const state = data?.state || 'no_run';
    // A run saved by an older model is last saved, never current.
    const lastSaved = !!result && (forecastQuery.isError || state !== 'current' || data?.model_current === false);
    const incomplete = result?.coverage?.estimate_status === 'incomplete';
    // Every team 0–0 and nothing projected: say so rather than rank a league-wide tie.
    const showTable = standings.gamesPlayed || !!result;
    const week = Math.max(0, ...standings.rows.map((r) => r.games));
    const cols = VIEW_COLUMNS[view];
    body = (
      <>
        <View style={styles.captionRow}>
          <Text variant="bodySm" style={styles.captionText} numberOfLines={showTable ? 1 : undefined}>
            {standings.gamesPlayed ? `Week ${week}`
              : showTable ? 'No games played yet' : 'No games played yet · standings start after week 1'}
          </Text>
          {showTable ? (
            <View style={styles.pill} accessibilityRole="tablist" testID="standings.view-pill">
              <ViewSeg label="Record" active={view === 'record'} onPress={() => selectView('record')} testID="standings.view.record" />
              <ViewSeg label="Points" active={view === 'points'} onPress={() => selectView('points')} testID="standings.view.points" />
            </View>
          ) : null}
        </View>
        {showTable ? (
          <View style={styles.table} testID="standings.table">
            <View style={styles.headRow}>
              <HeadCell column="team" sort={sort} onSort={onSort} />
              {cols.map((c) => (
                <HeadCell key={c} column={c} sort={sort} onSort={onSort} />
              ))}
              <View style={styles.chevronCol} />
            </View>
            {sorted.map((r) => {
              const isOpen = openRosterId === r.rosterId;
              const spoken = cols
                .map((c) => `${COLUMN_SPOKEN[c]} ${cellText(r, c) === DASH ? 'not available' : cellText(r, c)}${c === 'sos' && r.sos?.band ? `, ${r.sos.band}` : ''}`)
                .join('. ');
              const stats = isOpen ? openTeamStats(view, r, result?.playoff_byes ?? 0) : null;
              return (
                <View
                  key={r.rosterId}
                  style={[styles.row, r.isYou && styles.rowYou, isOpen && styles.rowOpen]}
                  testID={isOpen ? 'standings.open' : undefined}
                >
                  <Pressable
                    testID={`standings.row.${r.rosterId}`}
                    accessibilityRole="button"
                    accessibilityState={{ expanded: isOpen }}
                    accessibilityLabel={`${r.name}${r.isYou ? ', you' : ''}. ${spoken}.`}
                    onPress={() => toggleTeam(r.rosterId)}
                    style={({ pressed }) => [styles.rowHead, pressed && !isOpen && styles.rowPressed]}
                  >
                    <View style={[styles.teamCol, styles.nameCell]}>
                      <Text style={[styles.name, isOpen && styles.nameOpen]} numberOfLines={1}>
                        {r.name}
                      </Text>
                      {r.isYou ? <Badge label="You" color={ice.base} colorText /> : null}
                    </View>
                    {cols.map((c) => {
                      const text = cellText(r, c);
                      if (c === 'sos' && r.sos) {
                        return (
                          <View key={c} style={[styles.sosCell, { minWidth: COL_WIDTH.sos }]}>
                            <Text scale="dense" style={styles.num}>{text}</Text>
                            {r.sos.band ? <Text scale="dense" style={styles.band}>{r.sos.band}</Text> : null}
                          </View>
                        );
                      }
                      return (
                        <Text
                          key={c}
                          scale="dense"
                          style={[styles.num, { minWidth: COL_WIDTH[c] }, c === 'wl' && styles.record, text === DASH && styles.dash]}
                        >
                          {text}
                        </Text>
                      );
                    })}
                    <View style={styles.chevronCol}>
                      <Icon name={isOpen ? 'chevron-up' : 'chevron-down'} size={CHEVRON} color={isOpen ? ice.base : chalk.dim} />
                    </View>
                  </Pressable>
                  {stats ? (
                    <View style={styles.openBody}>
                      <View style={styles.stats} testID="standings.open.stats">
                        {stats.map((x) => <StatRow key={x.label} label={x.label} value={x.value} />)}
                      </View>
                      {r.forecast && result ? <ProjectionTeamDetail team={r.forecast} result={result} maxPf={{
                        block: data?.max_pf_moves, flagOn: maxPfMovesOn, isSleeper, liveRosterIds, leagueId, userId,
                      }} targets={{
                        block: data?.playoff_targets, flagOn: playoffTargetsOn, isSleeper,
                        liveRosters: rostersQuery.data ?? null,
                      }} pageLinks={pageLinks} /> : null}
                    </View>
                  ) : null}
                </View>
              );
            })}
          </View>
        ) : null}
        {result ? (
          <View style={styles.notes} testID="standings.forecast-status">
            <Text variant="bodySm">{[lastSaved ? `Last saved: ${date(result.captured_at)}` : 'Weekly estimate',
              incomplete ? 'Incomplete' : null, result.provisional ? 'Provisional' : null].filter(Boolean).join(' · ')}</Text>
          </View>
        ) : (
          <View style={styles.notes} testID="standings.no-forecast">
            <Text variant="bodySm">
              {noForecastLine({ enabled: forecastEnabled, isLoading: forecastQuery.isLoading, isError: forecastQuery.isError, state: data?.state })}
            </Text>
            {forecastEnabled && !forecastQuery.isLoading ? (
              <Button label="Check for update" variant="secondary" compact onPress={() => forecastQuery.refetch()}
                loading={forecastQuery.isFetching} testID="league-projections.check" />
            ) : null}
          </View>
        )}
        {showTable ? (
          <Text variant="bodySm" style={styles.note}>
            Your league’s own tiebreakers and divisions may order tied records differently.
          </Text>
        ) : null}
      </>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']} testID="standings.screen">
      {leagueId ? (
        <ScrollView contentContainerStyle={styles.scroll}>{body}</ScrollView>
      ) : (
        <View style={styles.center}>
          <Text variant="heading">No league selected</Text>
          <Text variant="bodySm" style={styles.centerBody}>
            Pick a league from the league switcher to see its standings.
          </Text>
        </View>
      )}
      {/* #188 — root-stack push: no tab bar underneath, so it carries its
          own. Exactly one mount, outside every branch. */}
      <FeedbackFAB activeScreen="Standings" aboveTabBar={false} />
    </SafeAreaView>
  );
}

// Record | Points — the Usage Trends view pill construction (specced pill:
// lineStrongA11y outline, active = ink-3 well + ice border, chalk text).
function ViewSeg({ label, active, onPress, testID }: {
  label: string;
  active: boolean;
  onPress: () => void;
  testID: string;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      accessibilityRole="tab"
      accessibilityState={{ selected: active }}
      accessibilityLabel={`${label} view`}
      hitSlop={{ top: 6, bottom: 6 }}
      style={[styles.seg, active && styles.segOn]}
    >
      <Text scale="dense" style={[styles.segText, active && styles.segTextOn]}>{label}</Text>
    </Pressable>
  );
}

// A sortable heading: the active one is ice with an arrow (down = best /
// biggest first, up = reversed; Team: up = A–Z; SoS: down = toughest first).
// A number heading draws its arrow on the LEFT, so the heading text keeps the
// cells' right edge in every sort state; Team keeps it on the right.
function HeadCell({ column, sort, onSort }: {
  column: StandingsColumn;
  sort: { column: StandingsColumn; dir: 'asc' | 'desc' };
  onSort: (c: StandingsColumn) => void;
}) {
  const active = sort.column === column;
  const isTeam = column === 'team';
  const dirWord = !active ? 'not sorted' : isTeam
    ? (sort.dir === 'asc' ? 'A to Z' : 'Z to A')
    : column === 'sos'
      ? (sort.dir === 'desc' ? 'toughest first' : 'easiest first')
      : (sort.dir === 'desc' ? 'highest first' : 'lowest first');
  const caret = active ? (
    <Icon name={sort.dir === 'asc' ? 'chevron-up' : 'chevron-down'} size={10} color={ice.base} />
  ) : null;
  return (
    <Pressable
      testID={`standings.sort.${column}`}
      accessibilityRole="button"
      accessibilityLabel={`Sort by ${COLUMN_SPOKEN[column]}, ${dirWord}`}
      onPress={() => onSort(column)}
      hitSlop={{ top: 8, bottom: 8 }}
      style={[styles.headCell, isTeam ? styles.teamCol : { width: COL_WIDTH[column], justifyContent: 'flex-end' }]}
    >
      {isTeam ? null : caret}
      <Text
        variant="label"
        numberOfLines={2}
        style={[styles.headText, !isTeam && styles.right, column === 'sos' && styles.asWritten, active && styles.headActive]}
      >
        {COLUMN_LABEL[column]}
      </Text>
      {isTeam ? caret : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  scroll: { padding: space.lg, paddingBottom: space.xxl },
  center: { alignItems: 'center', gap: space.md, paddingVertical: space.xl },
  centerBody: { textAlign: 'center' },

  // Caption line: week on the left, the Record | Points pill top right.
  captionRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm, marginBottom: space.sm },
  captionText: { flex: 1, minWidth: 0 },
  pill: {
    flexDirection: 'row',
    borderWidth: 1,
    borderColor: ink.lineStrongA11y,
    borderRadius: radii.pill,
    padding: 2,
  },
  seg: { minHeight: 32, paddingHorizontal: space.md, justifyContent: 'center', borderRadius: radii.pill },
  segOn: { backgroundColor: ink.ink3, borderWidth: 1, borderColor: ice.base },
  segText: { ...type.bodySm, fontFamily: fonts.uiSemi },
  segTextOn: { color: chalk.base },

  // One table: hairline rows, Plex Mono numerals. The you row keeps the
  // ranked-list treatment (ink-2 surface, ice You badge).
  table: { borderTopWidth: 1, borderTopColor: ink.line },
  headRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: space.xs,
    minHeight: 32,
    paddingHorizontal: space.xs,
    paddingBottom: space.xs,
    borderBottomWidth: 1,
    borderBottomColor: ink.lineStrong,
  },
  headCell: { flexDirection: 'row', alignItems: 'flex-end', gap: 2, minHeight: 28 },
  headText: { flexShrink: 1 },
  // "SoS" keeps its lowercase o: the one heading exempt from the label style's uppercase.
  asWritten: { textTransform: 'none' },
  headActive: { color: ice.base },
  row: { paddingHorizontal: space.xs, borderBottomWidth: 1, borderBottomColor: ink.line },
  rowYou: { backgroundColor: ink.ink2, borderBottomColor: ink.lineStrong },
  // The open team: an outlined card (1pt ice border, radius 8, raised ink-2
  // surface, a gap above and below). Border + padding = the closed row's
  // padding, so the columns do not move when a row opens.
  rowOpen: {
    borderWidth: 1,
    borderColor: ice.base,
    borderRadius: radii.md,
    backgroundColor: ink.ink2,
    borderBottomColor: ice.base,
    paddingHorizontal: space.xs - 1,
    marginVertical: space.sm,
  },
  rowHead: { flexDirection: 'row', alignItems: 'center', gap: space.xs, minHeight: 44 },
  rowPressed: { backgroundColor: ink.ink3 },
  teamCol: { flex: 1, minWidth: 0 },
  chevronCol: { width: CHEVRON, alignItems: 'center' },
  right: { textAlign: 'right' },
  nameCell: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  name: { ...type.body, flexShrink: 1 },
  nameOpen: { fontFamily: fonts.uiSemi },
  num: { ...type.data, textAlign: 'right', flexShrink: 0 },
  record: { fontFamily: fonts.dataSemi },
  dash: { color: chalk.faint },
  // SoS: the rank, with "hard" / "easy" under it in small muted text (label size, body face).
  sosCell: { alignItems: 'flex-end', flexShrink: 0 },
  band: { ...type.bodySm, fontSize: type.label.fontSize, lineHeight: type.label.lineHeight, textAlign: 'right' },
  openBody: { gap: space.xs, paddingBottom: space.sm },
  // Stat values end under the last number column, not under the chevron.
  stats: { marginRight: space.xs + CHEVRON },

  notes: { gap: space.xs, marginTop: space.md, alignItems: 'flex-start' },
  note: { marginTop: space.md },

  card: {
    gap: space.sm,
    padding: space.lg,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink1,
  },
  cardTitle: { marginBottom: space.xs },
});
