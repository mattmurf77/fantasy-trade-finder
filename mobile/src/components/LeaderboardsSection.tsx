import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
} from 'react-native';
import { useQuery } from '@tanstack/react-query';

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import {
  getLeaderboard,
  type LeaderboardScope,
  type LeaderboardMetric,
  type LeaderboardWindow,
  type LeaderboardRow,
} from '../api/leaderboard';

// Two leaderboard sections inline in LeagueScreen — League-specific and
// Universal. Each owns its own metric/window picker. Top 10 + sticky
// self-row when the user is out of top.

interface Props {
  // null when scope is universal-only (e.g. user has no league selected
  // — in practice LeagueScreen short-circuits before rendering us).
  leagueId: string | null;
}

type Tab = { key: string; label: string; metric: LeaderboardMetric; window?: LeaderboardWindow };

const TABS: Tab[] = [
  { key: 'streak', label: '🔥 Streaks', metric: 'streak' },
  { key: 'week',   label: 'This week',  metric: 'ranks', window: 'week'   },
  { key: 'month',  label: 'This month', metric: 'ranks', window: 'month'  },
  { key: 'season', label: 'Season',     metric: 'ranks', window: 'season' },
];

export default function LeaderboardsSection({ leagueId }: Props) {
  return (
    <>
      {leagueId ? <Board scope="league" leagueId={leagueId} title="League leaderboard" /> : null}
      <Board scope="universal" leagueId={null} title="Global leaderboard" />
    </>
  );
}

function Board({
  scope,
  leagueId,
  title,
}: {
  scope: LeaderboardScope;
  leagueId: string | null;
  title: string;
}) {
  const [tabKey, setTabKey] = useState<string>('streak');
  const tab = TABS.find((t) => t.key === tabKey)!;

  const lbQuery = useQuery({
    queryKey: ['leaderboard', scope, leagueId, tab.metric, tab.window ?? null],
    queryFn:  () => getLeaderboard({
      scope,
      metric:   tab.metric,
      window:   tab.window,
      leagueId: leagueId ?? undefined,
    }),
    staleTime: 60_000,
    // League-scoped boards depend on a leagueId; gate accordingly.
    enabled: scope === 'universal' ? true : !!leagueId,
  });

  return (
    <View style={styles.section}>
      <Text style={styles.title}>{title}</Text>

      {/* Metric / window pills */}
      <View style={styles.tabsRow}>
        {TABS.map((t) => {
          const isActive = t.key === tabKey;
          return (
            <Pressable
              key={t.key}
              onPress={() => setTabKey(t.key)}
              style={({ pressed }) => [
                styles.tab,
                isActive && styles.tabActive,
                pressed && { opacity: 0.7 },
              ]}
            >
              <Text style={[styles.tabText, isActive && styles.tabTextActive]}>
                {t.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {lbQuery.isLoading ? (
        <View style={styles.centered}>
          <ActivityIndicator color={colors.accent} />
        </View>
      ) : lbQuery.isError ? (
        <Text style={styles.empty}>Couldn't load leaderboard.</Text>
      ) : !lbQuery.data || lbQuery.data.rows.length === 0 ? (
        <Text style={styles.empty}>
          {scope === 'league'
            ? 'No leaguemates on the board yet — ranks count once they sign in.'
            : 'No one on the board yet. Be the first.'}
        </Text>
      ) : (
        <View style={styles.list}>
          {lbQuery.data.rows.slice(0, 10).map((r) => (
            <Row key={r.user_id} row={r} metric={tab.metric} />
          ))}
          {/* Sticky self-row when user is out of top 10 */}
          {lbQuery.data.self_row && lbQuery.data.self_row.rank > 10 ? (
            <>
              <Text style={styles.gap}>···</Text>
              <Row row={lbQuery.data.self_row} metric={tab.metric} />
            </>
          ) : null}
        </View>
      )}
    </View>
  );
}

function Row({ row, metric }: { row: LeaderboardRow; metric: LeaderboardMetric }) {
  return (
    <View style={[styles.row, row.is_self && styles.rowSelf]}>
      <Text style={[styles.rank, row.is_self && styles.rankSelf]}>{row.rank}</Text>
      <Text style={[styles.name, row.is_self && styles.nameSelf]} numberOfLines={1}>
        {row.display_name}
      </Text>
      <Text style={[styles.value, row.is_self && styles.valueSelf]}>
        {metric === 'streak' ? `🔥 ${row.value}` : row.value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: spacing.sm, marginTop: spacing.md },
  title: {
    color: colors.muted,
    fontSize: fontSize.xs,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
    marginBottom: 4,
  },
  tabsRow: {
    flexDirection: 'row',
    gap: spacing.xs,
    flexWrap: 'wrap',
  },
  tab: {
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  tabActive: {
    backgroundColor: 'rgba(79,124,255,0.14)',
    borderColor: colors.accent,
  },
  tabText: { color: colors.muted, fontSize: fontSize.xs, fontWeight: '700' },
  tabTextActive: { color: colors.accent },
  list: { gap: 4 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  rowSelf: {
    backgroundColor: 'rgba(79,124,255,0.10)',
    borderColor: colors.accent,
  },
  rank: {
    color: colors.muted,
    fontSize: fontSize.sm,
    fontWeight: '800',
    width: 28,
    textAlign: 'right',
  },
  rankSelf: { color: colors.accent },
  name: {
    flex: 1,
    color: colors.text,
    fontSize: fontSize.sm,
    fontWeight: '600',
  },
  nameSelf: { color: colors.text, fontWeight: '800' },
  value: {
    color: colors.text,
    fontSize: fontSize.sm,
    fontWeight: '700',
    minWidth: 40,
    textAlign: 'right',
  },
  valueSelf: { color: colors.accent },
  centered: { paddingVertical: spacing.lg, alignItems: 'center' },
  empty: {
    color: colors.muted,
    fontSize: fontSize.sm,
    textAlign: 'center',
    paddingVertical: spacing.md,
  },
  gap: {
    color: colors.muted,
    textAlign: 'center',
    paddingVertical: 4,
  },
});
