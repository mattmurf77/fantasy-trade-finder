import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
} from 'react-native';
import { useQuery } from '@tanstack/react-query';

import { ink, chalk, ice, space, type, fonts } from '../theme/chalkline';
import { Card, TickLabel } from './chalkline';
import { haptics } from '../utils/haptics';
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
//
// Chalkline: TickLabel section headers, FilterTabs-style pickers (ghost
// label text, active = chalk + ice underline), hairline rows in a Card
// with rank/value numerals in Plex Mono. Self row = ink-2 fill.

interface Props {
  // null when scope is universal-only (e.g. user has no league selected
  // — in practice LeagueScreen short-circuits before rendering us).
  leagueId: string | null;
}

type Tab = { key: string; label: string; metric: LeaderboardMetric; window?: LeaderboardWindow };

const TABS: Tab[] = [
  { key: 'streak', label: 'Streaks', metric: 'streak' },
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
      <TickLabel>{title}</TickLabel>

      {/* Metric / window tabs — FilterTabs: ghost label, ice underline on active */}
      <View style={styles.tabsRow}>
        {TABS.map((t) => {
          const isActive = t.key === tabKey;
          return (
            <Pressable
              key={t.key}
              accessibilityRole="tab"
              accessibilityState={{ selected: isActive }}
              onPress={() => {
                if (t.key !== tabKey) haptics.selection();
                setTabKey(t.key);
              }}
              style={({ pressed }) => [
                styles.tab,
                isActive && styles.tabActive,
                pressed && styles.tabPressed,
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
          <ActivityIndicator color={chalk.dim} />
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
        <Card>
          {lbQuery.data.rows.slice(0, 10).map((r, i) => (
            <Row key={r.user_id} row={r} metric={tab.metric} withRule={i > 0} />
          ))}
          {/* Sticky self-row when user is out of top 10 */}
          {lbQuery.data.self_row && lbQuery.data.self_row.rank > 10 ? (
            <>
              <Text style={styles.gap}>···</Text>
              <Row row={lbQuery.data.self_row} metric={tab.metric} />
            </>
          ) : null}
        </Card>
      )}
    </View>
  );
}

function Row({
  row,
  metric,
  withRule,
}: {
  row: LeaderboardRow;
  metric: LeaderboardMetric;
  withRule?: boolean;
}) {
  return (
    <View style={[styles.row, withRule && styles.rowRule, row.is_self && styles.rowSelf]}>
      <Text style={[styles.rank, row.is_self && styles.rankSelf]}>{row.rank}</Text>
      <Text style={[styles.name, row.is_self && styles.nameSelf]} numberOfLines={1}>
        {row.display_name}
      </Text>
      <Text style={[styles.value, row.is_self && styles.valueSelf]}>
        {metric === 'streak' ? String(row.value) : row.value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: space.sm, marginTop: space.md },
  tabsRow: {
    flexDirection: 'row',
    gap: space.md,
    flexWrap: 'wrap',
  },
  tab: {
    minHeight: 44,
    justifyContent: 'center',
    paddingHorizontal: space.xs,
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  tabActive: { borderBottomColor: ice.base },
  // Pressed = color change only (no transforms).
  tabPressed: { backgroundColor: ink.ink3 },
  tabText: { ...type.label },
  tabTextActive: { color: chalk.base },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingVertical: space.sm,
  },
  rowRule: {
    borderTopWidth: 1,
    borderTopColor: ink.line,
  },
  rowSelf: {
    backgroundColor: ink.ink2,
    paddingHorizontal: space.sm,
  },
  rank: {
    ...type.data,
    color: chalk.dim,
    width: 28,
    textAlign: 'right',
  },
  rankSelf: { color: chalk.base, fontFamily: fonts.dataSemi },
  name: {
    ...type.body,
    flex: 1,
  },
  nameSelf: { fontFamily: fonts.uiSemi },
  value: {
    ...type.data,
    minWidth: 40,
    textAlign: 'right',
  },
  valueSelf: { fontFamily: fonts.dataSemi },
  centered: { paddingVertical: space.lg, alignItems: 'center' },
  empty: {
    ...type.bodySm,
    textAlign: 'center',
    paddingVertical: space.md,
  },
  gap: {
    ...type.data,
    color: chalk.faint,
    textAlign: 'center',
    paddingVertical: space.xs,
  },
});
