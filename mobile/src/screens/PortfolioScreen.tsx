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

import { ink, chalk, volt, space, radii, type } from '../theme/chalkline';
import { TickLabel } from '../components/chalkline';
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

  // FB-48 — scope the aggregation to the current-season league list (the
  // same set the switcher shows). The DB also holds last season's instance
  // of each Sleeper league; unscoped, carried-over players double-count.
  const leagueIds = (leagues || []).map((lg) => lg.league_id);
  const query = useQuery({
    queryKey: ['portfolio', leagueIds.join(',')],
    queryFn: () => getPortfolio(leagueIds),
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
          <ActivityIndicator color={volt.base} />
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
              tintColor={volt.base}
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
            <TickLabel>Exposure</TickLabel>
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
            tintColor={volt.base}
          />
        }
        ItemSeparatorComponent={() => <View style={styles.hairline} />}
      />
    </SafeAreaView>
  );
}

function PortfolioRowItem({ row, total }: { row: PortfolioRow; total: number }) {
  const own = row.exposure.length;
  // Sleeper lets a user have multiple leagues that share a display name.
  // The backend already returns distinct league_ids per exposure (so the
  // count is correct), but two chips with identical labels look to the
  // user like the same league counted twice. Append a short league_id
  // suffix only on the chips whose names collide within this row, so the
  // common case (unique names) stays clean.
  const nameCounts = row.exposure.reduce<Record<string, number>>((acc, ex) => {
    acc[ex.league_name] = (acc[ex.league_name] || 0) + 1;
    return acc;
  }, {});
  return (
    <View style={styles.row}>
      <View style={styles.rowTop}>
        <Text style={styles.playerName} numberOfLines={1}>
          {row.player.name}
        </Text>
        <PositionChip position={row.player.position} size="sm" />
        <Text style={styles.exposureText}>
          Own in {own} / {total}
        </Text>
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.tierStrip}
      >
        {row.exposure.map((ex, idx) => {
          const collides = (nameCounts[ex.league_name] || 0) > 1;
          const suffix = collides ? ` · ${shortLeagueId(ex.league_id)}` : '';
          return (
            <LeagueTierChip
              key={`${ex.league_id}-${idx}`}
              leagueName={`${ex.league_name}${suffix}`}
              tier={ex.tier}
            />
          );
        })}
      </ScrollView>
    </View>
  );
}

// Last 4 chars of the league_id are enough to disambiguate same-named
// leagues for a single user (their leagues count is small; collisions
// on the last 4 are vanishingly rare in practice).
function shortLeagueId(leagueId: string): string {
  if (!leagueId) return '';
  return leagueId.length <= 4 ? leagueId : leagueId.slice(-4);
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
  root: { flex: 1, backgroundColor: ink.ink0 },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.sm },
  loadingText: { ...type.bodySm },
  emptyCentered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.xl,
    gap: space.sm,
  },
  emptyTitle: { ...type.heading, textAlign: 'center' },
  emptySub: { ...type.bodySm, textAlign: 'center' },
  list: { padding: space.lg },
  summary: {
    gap: space.sm,
    paddingBottom: space.md,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  summaryText: { ...type.bodySm },
  summaryStrong: { ...type.data },
  hairline: { height: 1, backgroundColor: ink.line },
  row: {
    paddingVertical: space.md,
    gap: space.sm,
  },
  rowTop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  playerName: {
    ...type.title,
    flex: 1,
  },
  exposureText: { ...type.data, color: chalk.dim },
  tierStrip: {
    gap: space.xs,
    paddingRight: space.sm,
  },
  poolChip: {
    borderColor: ink.line,
    borderWidth: 1,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radii.xs,
    maxWidth: 180,
  },
  poolChipText: { ...type.bodySm },
  tieredChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    borderColor: ink.line,
    borderWidth: 1,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radii.xs,
    maxWidth: 220,
  },
  tieredChipLeague: {
    ...type.bodySm,
    color: chalk.base,
    maxWidth: 120,
  },
});
