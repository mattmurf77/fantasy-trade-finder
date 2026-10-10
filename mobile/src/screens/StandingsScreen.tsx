import React, { useMemo, useState } from 'react';
import { View, ScrollView, Pressable, ActivityIndicator, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import Text from '../components/chalkline/Text';
import { Badge, Button, TickLabel } from '../components/chalkline';
import FeedbackFAB from '../components/FeedbackFAB';
import { ink, chalk, ice, semantic, space, radii, type, fonts } from '../theme/chalkline';
import { getLeagueRosters, getLeagueUsers, findMyRoster } from '../api/sleeper';
import { getOutlook } from '../api/league';
import { track } from '../api/events';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import { currentStandings, formatRecord } from '../utils/standings';
import { SeasonOutlookSection, OutlookUnsupportedRow } from './LeagueSummaryScreen';

// Standings (Home hub, flag `nav.home_hub`; docs/plans/home-engagement/
// scope.md §6.4, rulings R4/R5/R7). A ROOT-STACK push from Home's Standings
// row: Back returns to Home, so it mounts its own FeedbackFAB and RootNav
// gives it an explicit HeaderBack (RNS#3294). No params — it reads the
// session league.
//
// CURRENT (default) is the league's actual results, computed client-side
// from the Sleeper rosters session init already seeded (utils/standings.ts):
// no request on a warm cache, no simulation. ESPN/MFL have no current
// standings in v1 (R7) and get an honest card.
//
// PROJECTED is League Summary's Season-outlook section itself, imported
// rather than re-drawn, so its calibration rules (bands not percentages, no
// title odds, records only once `meta.beta` clears) live in one place. The
// outlook query runs ONLY while Projected is selected — the 10,000-sim
// request is a tap, never a page open.

type Segment = 'current' | 'projected';

// Display names for the non-Sleeper unavailable card.
const PLATFORM_NAME: Record<string, string> = {
  espn: 'ESPN',
  mfl: 'MFL',
  fleaflicker: 'Fleaflicker',
};

export default function StandingsScreen() {
  const leagueId = useSession((s) => s.league?.league_id) || null;
  const userId = useSession((s) => s.user?.user_id ?? null);
  // League Summary's platform rule (LeagueSummaryScreen `outlookSupported`):
  // unknown resolves to Sleeper, i.e. supported.
  const platform =
    useSession((s) => s.leagues.find((l) => l.league_id === leagueId)?.platform) ?? 'sleeper';
  const isSleeper = platform === 'sleeper';
  const oddsEnabled = useFlag('outlook.odds');
  const [segment, setSegment] = useState<Segment>('current');

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
  // Shared with League Summary's consensus outlook (same key), so a fetch on
  // either surface serves the other within staleTime.
  const outlookQuery = useQuery({
    queryKey: ['league-outlook', leagueId, 'consensus'],
    queryFn: () => getOutlook(leagueId!, 'consensus'),
    enabled: segment === 'projected' && oddsEnabled && isSleeper && !!leagueId,
    staleTime: 60_000,
  });

  const standings = useMemo(() => {
    const rosters = rostersQuery.data;
    if (!rosters) return null;
    const myRosterId = userId ? findMyRoster(rosters, userId)?.roster_id ?? null : null;
    return currentStandings(rosters, usersQuery.data ?? [], myRosterId);
  }, [rostersQuery.data, usersQuery.data, userId]);

  // A lens switch on a read-only page: fires on a CHANGING tap only, never
  // on mount and never on a re-tap of the active segment.
  const selectSegment = (next: Segment) => {
    if (next === segment) return;
    track('standings_segment_changed', { segment: next }, 'Standings');
    setSegment(next);
  };

  const platformName = PLATFORM_NAME[platform];

  let current: React.ReactNode;
  if (!isSleeper || (standings && !standings.hasRecords)) {
    current = (
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
    current = (
      <View style={styles.center}>
        <ActivityIndicator color={ice.base} />
      </View>
    );
  } else if (!standings) {
    current = (
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
  } else if (!standings.gamesPlayed) {
    // Every team is 0–0: say so rather than rank a league-wide tie.
    current = (
      <Text variant="bodySm" style={styles.caption}>
        No games played yet · standings start after week 1
      </Text>
    );
  } else {
    const week = Math.max(...standings.rows.map((r) => r.games));
    const hasTies = standings.rows.some((r) => r.ties > 0);
    current = (
      <>
        <Text variant="bodySm" style={styles.caption}>
          {`Week ${week} · ordered by record, then points for`}
        </Text>
        <View style={styles.table} testID="standings.current.table">
          <View style={styles.headRow}>
            <Text variant="label" style={styles.rankCol}>#</Text>
            <Text variant="label" style={styles.teamCol}>Team</Text>
            <Text variant="label" style={[styles.numCol, styles.right]}>
              {hasTies ? 'W–L–T' : 'W–L'}
            </Text>
            <Text variant="label" style={[styles.numCol, styles.right]}>PF</Text>
          </View>
          {standings.rows.map((r) => {
            const rec = formatRecord(r.wins, r.losses, r.ties);
            const pf = r.pointsFor.toFixed(1);
            return (
              <View
                key={r.rosterId}
                style={[styles.row, r.isYou && styles.rowYou]}
                accessible
                accessibilityLabel={`${r.place}. ${r.name}${r.isYou ? ', you' : ''}. Record ${rec}. ${pf} points for.`}
              >
                <Text scale="dense" style={[styles.rankCol, styles.rank, r.isYou && styles.rankYou]}>
                  {r.place}
                </Text>
                <View style={[styles.teamCol, styles.nameCell]}>
                  <Text style={[type.title, styles.name]} numberOfLines={1}>
                    {r.name}
                  </Text>
                  {r.isYou ? <Badge label="You" color={ice.base} colorText /> : null}
                </View>
                <Text scale="dense" style={[styles.numCol, styles.right, styles.record]}>
                  {rec}
                </Text>
                <Text scale="dense" style={[styles.numCol, styles.right, styles.points]}>
                  {pf}
                </Text>
              </View>
            );
          })}
        </View>
        <Text variant="bodySm" style={styles.note}>
          Your league’s own tiebreakers and divisions may order tied records differently.
        </Text>
      </>
    );
  }

  let projected: React.ReactNode;
  if (!isSleeper) {
    projected = <OutlookUnsupportedRow />;
  } else {
    // SeasonOutlookSection draws its own loading shell and renders NOTHING
    // when there is no data (flag dark, error, pre-draft league). Inside
    // League Summary that is right; here it would leave the page blank, so
    // an empty Projected says so in one line.
    const empty =
      !oddsEnabled ||
      (!outlookQuery.isLoading && (outlookQuery.data?.teams.length ?? 0) === 0);
    projected = (
      <>
        {oddsEnabled ? <SeasonOutlookSection query={outlookQuery} /> : null}
        {empty ? (
          <View style={styles.projectedEmpty}>
            <TickLabel color={semantic.warn}>Season outlook</TickLabel>
            <Text variant="bodySm">Season outlook isn’t available for this league right now.</Text>
            {outlookQuery.isError ? (
              <Button
                label="Try again"
                variant="secondary"
                compact
                loading={outlookQuery.isFetching}
                onPress={() => outlookQuery.refetch()}
              />
            ) : null}
          </View>
        ) : null}
      </>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']} testID="standings.screen">
      {leagueId ? (
        <ScrollView contentContainerStyle={styles.scroll}>
          {/* Current | Projected — the Matches segment construction (hairline
              group at radii.sm; active = ink-3 fill + 2px ice underline). */}
          <View style={styles.segmentRow}>
            <SegmentBtn
              label="Current"
              active={segment === 'current'}
              onPress={() => selectSegment('current')}
              testID="standings.segment.current"
            />
            <SegmentBtn
              label="Projected"
              active={segment === 'projected'}
              onPress={() => selectSegment('projected')}
              testID="standings.segment.projected"
            />
          </View>
          {segment === 'current' ? current : projected}
        </ScrollView>
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

function SegmentBtn({ label, active, onPress, testID }: {
  label: string;
  active: boolean;
  onPress: () => void;
  testID: string;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      accessibilityLabel={label}
      style={({ pressed }) => [
        styles.segmentBtn,
        active && styles.segmentBtnActive,
        pressed && { backgroundColor: ink.ink3 },
      ]}
    >
      <Text variant="label" style={active ? styles.segmentTextActive : null}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  scroll: { padding: space.lg, paddingBottom: space.xxl },
  center: { alignItems: 'center', gap: space.md, paddingVertical: space.xl },
  centerBody: { textAlign: 'center' },

  segmentRow: {
    flexDirection: 'row',
    marginBottom: space.md,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  segmentBtn: {
    flex: 1,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  segmentBtnActive: {
    backgroundColor: ink.ink3,
    borderBottomColor: ice.base,
  },
  segmentTextActive: { color: chalk.base },

  caption: { marginBottom: space.sm },
  note: { marginTop: space.md },

  // Standings table: hairline rows, Plex Mono numerals; the you row is the
  // ranked-list treatment (ink-2 surface, ice numeral, ice You badge).
  table: { borderTopWidth: 1, borderTopColor: ink.line },
  headRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: 28,
    paddingHorizontal: space.xs,
    borderBottomWidth: 1,
    borderBottomColor: ink.lineStrong,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: 40,
    paddingHorizontal: space.xs,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  rowYou: { backgroundColor: ink.ink2, borderBottomColor: ink.lineStrong },
  rankCol: { width: 26, textAlign: 'center' },
  teamCol: { flex: 1, minWidth: 0 },
  numCol: { minWidth: 48, flexShrink: 0 },
  right: { textAlign: 'right' },
  rank: { ...type.data, color: chalk.dim },
  rankYou: { color: ice.base },
  nameCell: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  name: { flexShrink: 1 },
  record: { ...type.data, fontFamily: fonts.dataSemi },
  points: { ...type.data, color: chalk.dim },

  card: {
    gap: space.sm,
    padding: space.lg,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink1,
  },
  cardTitle: { marginBottom: space.xs },

  projectedEmpty: { gap: space.sm, alignItems: 'flex-start' },
});
