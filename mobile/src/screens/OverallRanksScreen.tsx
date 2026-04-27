import React, { useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  FlatList,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import PositionChip from '../components/PositionChip';
import { getRankings } from '../api/rankings';
import type { Position, RankedPlayer } from '../shared/types';

const FILTERS: (Position | 'ALL')[] = ['ALL', 'QB', 'RB', 'WR', 'TE'];

// Flat scrollable list of every player the current user has ranked, sorted
// by ELO (best → worst). Read-only. Useful for users who want a holistic
// view of their board outside the Tiers UX.
export default function OverallRanksScreen() {
  const [filter, setFilter] = useState<Position | 'ALL'>('ALL');

  // Pull the full unfiltered list once — we filter client-side so flipping
  // between QB/RB/etc. is instant and doesn't refetch.
  const ranksQuery = useQuery({
    queryKey: ['rankings', 'all'],
    queryFn: () => getRankings(null),
    staleTime: 30_000,
  });

  const rows: RankedPlayer[] = useMemo(() => {
    const all = (ranksQuery.data?.rankings || []) as RankedPlayer[];
    const sorted = [...all].sort((a, b) => (b.elo || 0) - (a.elo || 0));
    return filter === 'ALL'
      ? sorted
      : sorted.filter((r) => r.position === filter);
  }, [ranksQuery.data, filter]);

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <View style={styles.filterRow}>
        {FILTERS.map((f) => {
          const active = f === filter;
          return (
            <Pressable
              key={f}
              onPress={() => setFilter(f)}
              style={({ pressed }) => [
                styles.filterChip,
                active && styles.filterChipActive,
                pressed && { opacity: 0.7 },
              ]}
            >
              <Text style={[styles.filterText, active && styles.filterTextActive]}>
                {f}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {ranksQuery.isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.accent} />
        </View>
      ) : ranksQuery.isError ? (
        <View style={styles.center}>
          <Text style={styles.errorText}>Could not load rankings.</Text>
          <Pressable onPress={() => ranksQuery.refetch()}>
            <Text style={styles.retry}>Try again</Text>
          </Pressable>
        </View>
      ) : rows.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.emptyTitle}>No rankings yet</Text>
          <Text style={styles.emptyBody}>
            Rank a few trios on the Trios tab to populate your overall board.
          </Text>
        </View>
      ) : (
        <FlatList
          data={rows}
          keyExtractor={(r) => r.id}
          contentContainerStyle={styles.list}
          renderItem={({ item, index }) => <Row player={item} overallRank={index + 1} />}
          ItemSeparatorComponent={() => <View style={styles.sep} />}
          refreshing={ranksQuery.isFetching && !ranksQuery.isLoading}
          onRefresh={() => ranksQuery.refetch()}
        />
      )}
    </SafeAreaView>
  );
}

interface RowProps {
  player: RankedPlayer;
  overallRank: number;
}
function Row({ player, overallRank }: RowProps) {
  const ageStr = player.age != null ? `${player.age} yo` : null;
  return (
    <View style={styles.row}>
      <Text style={styles.rankNum}>{overallRank}</Text>
      <PositionChip position={player.position as Position} size="sm" />
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={styles.name} numberOfLines={1}>{player.name}</Text>
        <Text style={styles.meta} numberOfLines={1}>
          {(player.team || 'FA')}{ageStr ? ` · ${ageStr}` : ''}
          {player.injury_status ? ` · ${player.injury_status}` : ''}
        </Text>
      </View>
      <View style={styles.eloWrap}>
        <Text style={styles.eloNum}>{Math.round(player.elo)}</Text>
        <Text style={styles.eloLabel}>ELO</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  filterRow: {
    flexDirection: 'row',
    gap: spacing.xs,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
  },
  filterChip: {
    flex: 1,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: 'center',
  },
  filterChipActive: {
    borderColor: colors.accent,
    backgroundColor: 'rgba(79,124,255,0.10)',
  },
  filterText: { color: colors.muted, fontSize: fontSize.xs, fontWeight: '700' },
  filterTextActive: { color: colors.accent },

  list: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xxl },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
  },
  sep: { height: 1, backgroundColor: colors.border, opacity: 0.5 },
  rankNum: {
    width: 32,
    color: colors.muted,
    fontSize: fontSize.sm,
    fontWeight: '800',
    textAlign: 'right',
  },
  name: { color: colors.text, fontSize: fontSize.base, fontWeight: '700' },
  meta: { color: colors.muted, fontSize: fontSize.xs, marginTop: 2 },
  eloWrap: { alignItems: 'flex-end', minWidth: 56 },
  eloNum: { color: colors.text, fontSize: fontSize.base, fontWeight: '800' },
  eloLabel: { color: colors.muted, fontSize: 10, fontWeight: '700', letterSpacing: 0.5 },

  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing.md, padding: spacing.xl },
  errorText: { color: colors.red },
  retry: { color: colors.accent, fontWeight: '700' },
  emptyTitle: { color: colors.text, fontSize: fontSize.lg, fontWeight: '800' },
  emptyBody: { color: colors.muted, fontSize: fontSize.sm, textAlign: 'center', lineHeight: 22 },
});
