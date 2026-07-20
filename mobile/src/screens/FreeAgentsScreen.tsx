import React, { useCallback, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  FlatList,
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
import PlayerCard from '../components/PlayerCard';
import { getFreeAgents, type FreeAgentRow } from '../api/league';
import { readErrorCopy } from '../utils/verification';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import type { Position } from '../shared/types';

type PositionFilter = Position | 'ALL';
const FILTERS: PositionFilter[] = ['ALL', 'QB', 'RB', 'WR', 'TE'];

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
            {readErrorCopy(query.error, "Couldn't load free agents.")}
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
          renderItem={({ item }) => <FreeAgentRowCard row={item} />}
        />
      )}
    </SafeAreaView>
  );
}

// One FA row: dense PlayerCard (60px two-line) — line 2 carries the drop
// suggestion; right cluster = positional FA rank over the caller-board value.
function FreeAgentRowCard({ row }: { row: FreeAgentRow }) {
  const drop = row.drop_suggestion;
  // S2 PRD-04 ride-along (visual.chalkline_cleanup): "No drop worth making"
  // is content, not a placeholder — faint → dim.
  const cleanupOn = useFlag('visual.chalkline_cleanup');
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
