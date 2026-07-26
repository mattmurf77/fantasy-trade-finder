import React, { useCallback, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  Alert,
  FlatList,
  Linking,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { useQuery } from '@tanstack/react-query';

import {
  ink,
  chalk,
  ice,
  semantic,
  position,
  space,
  radii,
  type,
} from '../theme/chalkline';
import { Button } from '../components/chalkline';
import FeedbackFAB from '../components/FeedbackFAB';
import PlayerCard from '../components/PlayerCard';
import {
  getFreeAgents,
  type FreeAgentRow,
  type FreeAgentRosterCapacity,
} from '../api/league';
import { ApiError } from '../api/client';
import { isEspnLeague } from '../api/espn';
import { isMflLeague, isFleaflickerLeague } from '../api/platformLink';
import { readErrorCopy } from '../utils/verification';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import type { Position } from '../shared/types';

type PositionFilter = Position | 'ALL';
const FILTERS: PositionFilter[] = ['ALL', 'QB', 'RB', 'WR', 'TE'];

// #179 — where an "Add" can actually be executed. Sleeper publishes no
// write API for roster moves, so the honest Sleeper v1 is a deep-link into
// the league's players page in the Sleeper app/site (same pragmatic pattern
// as the trade-propose deep-link in TradesScreen). Platform-linked leagues
// (ESPN / MFL / Fleaflicker) are read-only imports today — no write path,
// so the Add affordance renders dimmed and explains why on tap. 'local'
// covers demo/local leagues that exist nowhere outside FTF.
type AddPlatform = 'sleeper' | 'espn' | 'mfl' | 'fleaflicker' | 'local';

function resolveAddPlatform(leagueId: string | undefined, isDemo: boolean): AddPlatform {
  if (!leagueId || isDemo) return 'local';
  if (isEspnLeague(leagueId)) return 'espn';
  if (isMflLeague(leagueId)) return 'mfl';
  if (isFleaflickerLeague(leagueId)) return 'fleaflicker';
  // Real Sleeper league ids are numeric; anything else is a local league.
  return /^\d+$/.test(leagueId) ? 'sleeper' : 'local';
}

const NO_ADD_REASON: Record<Exclude<AddPlatform, 'sleeper'>, { title: string; body: string }> = {
  espn: {
    title: "Can't add in ESPN leagues yet",
    body:
      'This league is imported from ESPN with read-only access, so ' +
      'Fantasy Trade Finder can’t make roster moves there. Open the ' +
      'ESPN Fantasy app to add this player.',
  },
  mfl: {
    title: "Can't add in MFL leagues yet",
    body:
      'This league is linked to MyFantasyLeague with read-only access, so ' +
      'Fantasy Trade Finder can’t make roster moves there. Open MFL ' +
      'to add this player.',
  },
  fleaflicker: {
    title: "Can't add in Fleaflicker leagues yet",
    body:
      'This league is linked to Fleaflicker with read-only access, so ' +
      'Fantasy Trade Finder can’t make roster moves there. Open ' +
      'Fleaflicker to add this player.',
  },
  local: {
    title: "Can't add in this league",
    body:
      'This league isn’t connected to a fantasy platform, so there’s ' +
      'no roster to add this player to.',
  },
};

// #179 — per-platform Add handling. Sleeper: explain the hand-off (and warn
// on a full roster when capacity data exists) before deep-linking to the
// league's players page; everything else: honest "why not" alert.
function handleAdd(
  row: FreeAgentRow,
  leagueId: string,
  addPlatform: AddPlatform,
  capacity: FreeAgentRosterCapacity | null | undefined,
) {
  if (addPlatform !== 'sleeper') {
    const reason = NO_ADD_REASON[addPlatform];
    Alert.alert(reason.title, reason.body);
    return;
  }
  const openSleeper = () => {
    // Lands on the league's Players (available players) surface — Sleeper
    // has no public write API, so the add itself happens in Sleeper.
    Linking.openURL(`https://sleeper.com/leagues/${leagueId}/players`).catch(() => {});
  };
  const rosterFull =
    capacity != null &&
    capacity.limit != null &&
    capacity.my_count != null &&
    capacity.my_count >= capacity.limit;
  if (rosterFull) {
    Alert.alert(
      'Your roster is full',
      `You're at ${capacity!.my_count}/${capacity!.limit} players, so Sleeper ` +
        `will block this add until you drop someone. Open Sleeper to make ` +
        `the drop and add ${row.name}.`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Open Sleeper', onPress: openSleeper },
      ],
    );
    return;
  }
  Alert.alert(
    `Add ${row.name}`,
    'Sleeper doesn’t let other apps make roster moves, so we’ll ' +
      'open your league in Sleeper to finish the add there.',
    [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Open Sleeper', onPress: openSleeper },
    ],
  );
}

// Free-agent finder (#143) — League-stack route 'FreeAgents' (entered from
// the League tab's "Free agents" row). Best available players in the
// league, ranked by the CALLER'S board values (consensus fallback for
// anyone they haven't ranked), with position filter pills and a
// "Drop: <player> (+delta)" subline whenever the backend found a lower-
// valued same-position player on the user's roster to cut for the FA.
export default function FreeAgentsScreen() {
  const navigation = useNavigation<any>();
  const [filter, setFilter] = useState<PositionFilter>('ALL');
  const leagueId = useSession((s) => s.league?.league_id);
  const isDemo = useSession((s) => s.isDemo);
  // S4 PRD-05 (ux.empty_state_ctas): the no-league state gets the action
  // its copy describes. Flag off: copy-only, as before.
  const emptyCtasOn = useFlag('ux.empty_state_ctas');

  const query = useQuery({
    // Position is part of the key: the backend caps each response at ~50
    // rows AFTER filtering, so each position gets its own full page.
    queryKey: ['free-agents', leagueId, filter],
    queryFn: () => getFreeAgents(leagueId as string, filter),
    enabled: !!leagueId,
    staleTime: 60_000,
  });

  const onRefresh = useCallback(() => {
    query.refetch();
  }, [query]);

  const rows = query.data?.free_agents ?? [];
  const consensusOnly = !!query.data && !query.data.user_has_rankings;
  // #179 — Add affordance context (platform + Sleeper roster capacity).
  const addPlatform = resolveAddPlatform(leagueId, isDemo);
  const capacity = query.data?.roster_capacity;
  const onAdd = useCallback(
    (row: FreeAgentRow) => {
      if (!leagueId) return;
      handleAdd(row, leagueId, addPlatform, capacity);
    },
    [leagueId, addPlatform, capacity],
  );

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      {/* PositionTabs spec: segmented hairline group; active segment = ink3
          fill + 2px underline in that position's color (ALL = ice). */}
      <View style={styles.filterRow}>
        {FILTERS.map((f) => {
          const active = f === filter;
          return (
            <Pressable
              key={f}
              testID={`free-agents.pos-tab.${f.toLowerCase()}`}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              accessibilityLabel={f === 'ALL' ? 'All positions' : f}
              onPress={() => setFilter(f)}
              style={({ pressed }) => [
                styles.filterSegment,
                active && [
                  styles.filterSegmentActive,
                  { borderBottomColor: underlineColor(f) },
                ],
                pressed && { backgroundColor: ink.ink3 },
              ]}
            >
              <Text style={[styles.filterText, active && styles.filterTextActive]}>
                {f}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {!leagueId ? (
        <View style={styles.centerFill}>
          <Text testID="free-agents.empty-text" style={styles.emptyBody}>
            Connect a league to see its free agents.
          </Text>
          {emptyCtasOn ? (
            <Button
              testID="free-agents.pick-league"
              label="Pick a league"
              variant="primary"
              onPress={() => navigation.navigate('LeaguePicker')}
            />
          ) : null}
        </View>
      ) : query.isLoading ? (
        <View style={styles.centerFill}>
          <ActivityIndicator color={ice.base} />
        </View>
      ) : query.isError ? (
        <View style={styles.centerFill}>
          <Text style={styles.errorText}>
            {/* #178 — the backend refuses to serve (503 rosters_unavailable)
                rather than list rostered players as FAs; surface its honest
                message instead of the generic copy. */}
            {query.error instanceof ApiError &&
            (query.error.body as any)?.error === 'rosters_unavailable'
              ? query.error.message
              : readErrorCopy(query.error, "Couldn't load free agents.")}
          </Text>
          <Button label="Try again" variant="ghost" compact onPress={() => query.refetch()} />
        </View>
      ) : (
        <FlatList
          testID="free-agents.list"
          data={rows}
          keyExtractor={(r) => r.player_id}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl
              refreshing={query.isFetching && !query.isLoading}
              onRefresh={onRefresh}
              tintColor={ice.base}
            />
          }
          ListHeaderComponent={
            <View>
              <Text style={styles.explainer}>
                Best available players in your league, ranked by your values.
                Drop lines show the weakest same-position player on your
                roster worth less than the free agent.
              </Text>
              {consensusOnly ? (
                <Text style={styles.consensusNote}>
                  You haven't ranked anyone yet, so this list uses consensus
                  values. Rank players to make it yours.
                </Text>
              ) : null}
            </View>
          }
          ListEmptyComponent={
            <View style={styles.centerFill}>
              <Text testID="free-agents.empty-text" style={styles.emptyBody}>
                {filter === 'ALL'
                  ? 'No free agents found — every valued player is rostered.'
                  : `No ${filter} free agents found.`}
              </Text>
            </View>
          }
          renderItem={({ item }) => (
            <FreeAgentRowCard row={item} addPlatform={addPlatform} onAdd={onAdd} />
          )}
        />
      )}
      {/* #188 — root-stack push covers RootNav's FAB mount; carry our own.
          No tab bar under this screen → aboveTabBar={false}. */}
      <FeedbackFAB activeScreen="FreeAgents" aboveTabBar={false} />
    </SafeAreaView>
  );
}

// One FA row: dense PlayerCard (60px two-line) — line 2 carries the drop
// suggestion; right cluster = positional FA rank over the caller-board value.
// #179: rightSlot carries the Add affordance — secondary for Sleeper leagues
// (deep-link hand-off), ghost/dim for platforms with no write path (tap
// explains why).
function FreeAgentRowCard({
  row,
  addPlatform,
  onAdd,
}: {
  row: FreeAgentRow;
  addPlatform: AddPlatform;
  onAdd: (row: FreeAgentRow) => void;
}) {
  const drop = row.drop_suggestion;
  // S2 PRD-04 ride-along (visual.chalkline_cleanup): "No drop worth making"
  // is content, not a placeholder — faint → dim.
  const cleanupOn = useFlag('visual.chalkline_cleanup');
  const canDeepLink = addPlatform === 'sleeper';
  return (
    <View style={styles.rowWrap}>
      <PlayerCard
        testID={`free-agents.row.${row.player_id}`}
        dense
        player={{
          id: row.player_id,
          name: row.name,
          position: row.position,
          team: row.team,
          age: row.age,
        }}
        posRank={`${row.position}${row.pos_rank}`}
        value={row.value}
        rightSlot={
          <Button
            testID={`free-agents.add.${row.player_id}`}
            label="Add"
            variant={canDeepLink ? 'secondary' : 'ghost'}
            compact
            onPress={() => onAdd(row)}
          />
        }
        statsSlot={
          drop ? (
            <Text style={styles.dropLine} numberOfLines={1}>
              Drop: {drop.name}{' '}
              <Text style={styles.dropDelta}>
                (+{Math.round(drop.delta).toLocaleString('en-US')})
              </Text>
            </Text>
          ) : (
            <Text
              style={[styles.noDropLine, cleanupOn && { color: chalk.dim }]}
              numberOfLines={1}
            >
              No drop worth making
            </Text>
          )
        }
      />
    </View>
  );
}

// Active-tab underline per PositionTabs spec: position color, ice for ALL.
function underlineColor(f: PositionFilter): string {
  switch (f) {
    case 'QB': return position.qb;
    case 'RB': return position.rb;
    case 'WR': return position.wr;
    case 'TE': return position.te;
    default:   return ice.base;
  }
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },

  filterRow: {
    flexDirection: 'row',
    marginHorizontal: space.lg,
    marginTop: space.md,
    marginBottom: space.sm,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  filterSegment: {
    flex: 1,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
    backgroundColor: 'transparent',
  },
  filterSegmentActive: {
    backgroundColor: ink.ink3,
  },
  filterText: { ...type.label },
  filterTextActive: { color: chalk.base },

  listContent: {
    paddingHorizontal: space.lg,
    paddingBottom: space.xxl,
    gap: space.sm,
  },
  explainer: {
    ...type.bodySm,
    color: chalk.dim,
    marginTop: space.sm,
    marginBottom: space.sm,
  },
  consensusNote: {
    ...type.bodySm,
    color: chalk.base,
    backgroundColor: ink.ink1,
    borderColor: ink.line,
    borderWidth: 1,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    marginBottom: space.sm,
  },
  rowWrap: {},

  dropLine: {
    ...type.data,
    fontSize: 11,
    color: chalk.dim,
    flexShrink: 1,
  },
  dropDelta: {
    color: semantic.pos,
  },
  noDropLine: {
    ...type.data,
    fontSize: 11,
    color: chalk.faint,
  },

  centerFill: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: space.xl,
    paddingHorizontal: space.lg,
    gap: space.sm,
  },
  emptyBody: {
    ...type.bodySm,
    textAlign: 'center',
  },
  errorText: { ...type.bodySm, color: semantic.neg },
});
