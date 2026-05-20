import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  ActivityIndicator,
  ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import PositionChip from '../components/PositionChip';
import TierBadge from '../components/TierBadge';
import { getPortfolio } from '../api/league';
import { useSession } from '../state/useSession';
import type { PortfolioRow, PortfolioTier, Tier } from '../shared/types';

// Cross-league portfolio view. Hidden behind a "connect a second league"
// gate — without 2+ leagues there's nothing to compare. Sorted by exposure
// count (most-owned first); rows show per-league tier chips so the user
// can spot lopsided exposure at a glance.
//
// Backend doesn't yet emit per-league tier info, so chips fall back to a
// neutral "Pool" label when `tier === 'pool'`. When the backend starts
// returning tier-per-league, no UI change needed — the type already
// accepts `Tier | 'pool'`.
export default function PortfolioScreen() {
  const leagues = useSession((s) => s.leagues);
  const hasMultiLeague = (leagues?.length || 0) >= 2;

  const query = useQuery({
    queryKey: ['portfolio'],
    queryFn: getPortfolio,
    enabled: hasMultiLeague,
    staleTime: 60_000,
  });

  // Gate: <2 leagues → CTA to Settings → Add a league.
  if (!hasMultiLeague) {
    return (
      <SafeAreaView style={styles.root} edges={['bottom']}>
        <View style={styles.emptyCentered}>
          <Text style={styles.emptyTitle}>Connect a second league</Text>
          <Text style={styles.emptySub}>
            Portfolio shows which players you own across multiple leagues.
            Add another Sleeper league from Settings to unlock it.
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  if (query.isLoading) {
    return (
      <SafeAreaView style={styles.root} edges={['bottom']}>
        <View style={styles.loading}>
          <ActivityIndicator color={colors.accent} />
          <Text style={styles.loadingText}>Loading portfolio…</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (query.error) {
    return (
      <SafeAreaView style={styles.root} edges={['bottom']}>
        <View style={styles.emptyCentered}>
          <Text style={styles.emptyTitle}>Couldn't load portfolio</Text>
          <Text style={styles.emptySub}>{(query.error as Error).message}</Text>
        </View>
      </SafeAreaView>
    );
  }

  const players = query.data?.players || [];

  // Empty: signed in with 2+ leagues but no overlap (or rosters still
  // syncing on the backend).
  if (players.length === 0) {
    return (
      <SafeAreaView style={styles.root} edges={['bottom']}>
        <FlatList
          data={[]}
          renderItem={null as any}
          refreshControl={
            <RefreshControl
              refreshing={query.isFetching}
              onRefresh={() => query.refetch()}
              tintColor={colors.accent}
            />
          }
          ListEmptyComponent={
            <View style={styles.emptyCentered}>
              <Text style={styles.emptyTitle}>No exposure yet</Text>
              <Text style={styles.emptySub}>
                We couldn't find any players on your rosters across leagues.
                Your rosters may still be syncing — pull to refresh.
              </Text>
            </View>
          }
          contentContainerStyle={{ flex: 1 }}
        />
      </SafeAreaView>
    );
  }

  // Total leagues count is identical on every row.
  const total = players[0]?.total_leagues || leagues.length;

  return (
    <SafeAreaView style={styles.root} edges={['bottom']}>
      <FlatList
        data={players}
        keyExtractor={(row) => row.player.id}
        contentContainerStyle={styles.list}
        ListHeaderComponent={
          <View style={styles.summary}>
            <Text style={styles.summaryText}>
              <Text style={styles.summaryStrong}>{players.length}</Text> distinct players across{' '}
              <Text style={styles.summaryStrong}>{total}</Text> leagues
            </Text>
          </View>
        }
        renderItem={({ item }) => <PortfolioRowItem row={item} total={total} />}
        refreshControl={
          <RefreshControl
            refreshing={query.isFetching}
            onRefresh={() => query.refetch()}
            tintColor={colors.accent}
          />
        }
        ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
      />
    </SafeAreaView>
  );
}

function PortfolioRowItem({ row, total }: { row: PortfolioRow; total: number }) {
  const own = row.exposure.length;
  return (
    <View style={styles.row}>
      <View style={styles.rowTop}>
        <Text style={styles.playerName} numberOfLines={1}>
          {row.player.name}
        </Text>
        <PositionChip position={row.player.position} size="sm" />
        <View style={styles.exposureBadge}>
          <Text style={styles.exposureText}>
            Own in {own} / {total}
          </Text>
        </View>
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.tierStrip}
      >
        {row.exposure.map((ex, idx) => (
          <LeagueTierChip
            key={`${ex.league_id}-${idx}`}
            leagueName={ex.league_name}
            tier={ex.tier}
          />
        ))}
      </ScrollView>
    </View>
  );
}

function LeagueTierChip({
  leagueName,
  tier,
}: {
  leagueName: string;
  tier: PortfolioTier;
}) {
  // 'pool' = no tier known yet (backend doesn't currently emit
  // per-league tier). Render a neutral chip with just the league name.
  if (tier === 'pool') {
    return (
      <View style={styles.poolChip}>
        <Text style={styles.poolChipText} numberOfLines={1}>
          {leagueName}
        </Text>
      </View>
    );
  }
  return (
    <View style={styles.tieredChip}>
      <Text style={styles.tieredChipLeague} numberOfLines={1}>
        {leagueName}
      </Text>
      <TierBadge tier={tier as Tier} size="sm" />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing.sm },
  loadingText: { color: colors.muted, fontSize: fontSize.sm },
  emptyCentered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
    gap: spacing.sm,
  },
  emptyTitle: { color: colors.text, fontSize: fontSize.lg, fontWeight: '800' },
  emptySub: {
    color: colors.muted,
    fontSize: fontSize.sm,
    textAlign: 'center',
    lineHeight: 20,
  },
  list: { padding: spacing.lg },
  summary: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  summaryText: { color: colors.muted, fontSize: fontSize.sm },
  summaryStrong: { color: colors.text, fontWeight: '800' },
  row: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: spacing.md,
    gap: spacing.sm,
  },
  rowTop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  playerName: {
    flex: 1,
    color: colors.text,
    fontSize: fontSize.base,
    fontWeight: '700',
  },
  exposureBadge: {
    backgroundColor: 'rgba(79,124,255,0.12)',
    borderColor: 'rgba(79,124,255,0.35)',
    borderWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  exposureText: {
    color: colors.accent,
    fontSize: fontSize.xs,
    fontWeight: '700',
  },
  tierStrip: {
    gap: spacing.xs,
    paddingRight: spacing.sm,
  },
  poolChip: {
    backgroundColor: 'rgba(122,127,150,0.10)',
    borderColor: colors.border,
    borderWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: radius.sm,
    maxWidth: 180,
  },
  poolChipText: {
    color: colors.muted,
    fontSize: fontSize.xs,
    fontWeight: '600',
  },
  tieredChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: 'rgba(122,127,150,0.08)',
    borderColor: colors.border,
    borderWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: radius.sm,
    maxWidth: 220,
  },
  tieredChipLeague: {
    color: colors.text,
    fontSize: fontSize.xs,
    fontWeight: '600',
    maxWidth: 120,
  },
});
