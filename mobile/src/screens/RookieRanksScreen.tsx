import React, { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import { Button, PositionBadge, TickLabel } from '../components/chalkline';
import TierBadge from '../components/TierBadge';
import FormatToggle from '../components/FormatToggle';
import Toast from '../components/Toast';
import { RookieScopeEmpty } from '../components/RookieScopeControl';
import { getRankings, splitRankings } from '../api/rankings';
import { useSession } from '../state/useSession';
import { useScoringFormat } from '../hooks/useScoringFormat';
import { useRookieScope } from '../state/rookieScope';
import { tierForElo } from '../utils/tierBands';
import { valueForElo } from '../utils/playerValue';
import {
  chalk,
  ice,
  ink,
  position as positionColors,
  radii,
  space,
  type,
} from '../theme/chalkline';
import { haptics } from '../utils/haptics';
import type { Position, RankedPlayer, ScoringFormat, Tier } from '../shared/types';

// ── Consolidated rookie ranking view (rookie-draft M2, operator decision
// O1-expanded) ─────────────────────────────────────────────────────────
//
// Rookies stay in their position boards AND appear here in ONE cross-
// position list. This is NOT a second Elo space — it is the same board
// read through the same post-Elo view filter (`GET /api/rankings?scope=
// rookie` with no position), so the values shown here and the values on
// the QB/RB/WR/TE boards are synced BY CONSTRUCTION, not by a sync step.
// That is the whole reason a separate rookie Elo space was rejected: a
// second space would fork tier colors, trade values, #161 demotion and
// four cross-client mirrors.
//
// Deliberately READ-ONLY. Every editing gesture already exists on a rank
// surface, and each of them now carries the rookie scope (Head-to-heads,
// Tiers board, Quick Set, Quick Rank, Overall ranks, Pick Anchors) — so
// this view answers "where do my rookies stand against each other" and
// hands the editing back to the mode that fits. Building a seventh drag
// board here would duplicate Overall ranks under scope.
//
// Flag-gated by `ranks.rookie_subset` (server-delivered). No entry point
// exists with the flag off; reaching the route anyway (a stale deep link)
// renders the honest unavailable state rather than an empty board.

const FILTERS: readonly (Position | 'ALL')[] = ['ALL', 'QB', 'RB', 'WR', 'TE'];

const filterUnderline = (f: Position | 'ALL'): string =>
  f === 'ALL'
    ? ice.base
    : positionColors[f.toLowerCase() as keyof typeof positionColors];

interface Row extends RankedPlayer {
  /** 1-based rank among ALL rookies (cross-position, Elo order). */
  overallRookieRank: number;
  /** 1-based rank among rookies at the same position. */
  posRookieRank: number;
}

export default function RookieRanksScreen() {
  const activeFormat = useSession((s) => s.activeFormat);
  const fmt: ScoringFormat = activeFormat || '1qb_ppr';
  const { setFormat, switching: formatSwitching } = useScoringFormat();
  const { enabled } = useRookieScope();
  const [filter, setFilter] = useState<Position | 'ALL'>('ALL');
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);

  // The consolidated read: the scoped rankings payload with NO position,
  // i.e. the cross-position board filtered to rookies. Shares the same
  // `['rankings', fmt, 'all', 'rookie']` key as Overall ranks under scope,
  // so the two never show different numbers and a save on either refreshes
  // both through the existing prefix invalidations.
  const ranksQuery = useQuery({
    queryKey: ['rankings', activeFormat, 'all', 'rookie'],
    queryFn: () => getRankings(null, { scope: 'rookie' }),
    staleTime: 30_000,
    enabled,
  });

  const { rows: rawRows, empty: scopeEmpty } = useMemo(() => {
    const s = splitRankings(ranksQuery.data);
    return { rows: s.rows as RankedPlayer[], empty: s.empty };
  }, [ranksQuery.data]);

  // Cross-position order is Elo order — the same ladder the tier bands are
  // cut from, which is why a rookie WR and a rookie RB are comparable here
  // at all (pick value is position-uniform by design, #117).
  const rows: Row[] = useMemo(() => {
    const sorted = [...rawRows].sort((a, b) => (b.elo ?? 0) - (a.elo ?? 0));
    const posCounts: Partial<Record<string, number>> = {};
    return sorted.map((p, i) => {
      const n = (posCounts[p.position] ?? 0) + 1;
      posCounts[p.position] = n;
      return { ...p, overallRookieRank: i + 1, posRookieRank: n };
    });
  }, [rawRows]);

  const visible = useMemo(
    () => (filter === 'ALL' ? rows : rows.filter((r) => r.position === filter)),
    [rows, filter],
  );

  const onFormatChange = async (f: ScoringFormat) => {
    haptics.selection();
    const ok = await setFormat(f);
    if (!ok) setToast({ msg: 'Could not switch format', tone: 'warn' });
  };

  const renderRow = ({ item }: { item: Row }) => {
    const tier = tierForElo(item.elo, item.position as Position, fmt) as Tier | null;
    const value = valueForElo(item.elo);
    return (
      <View style={styles.row} testID={`rookie-ranks.row.${item.id}`}>
        <Text style={styles.rank}>{item.overallRookieRank}</Text>
        <View style={styles.rowMain}>
          <Text style={styles.name} numberOfLines={1}>{item.name}</Text>
          <View style={styles.metaRow}>
            <PositionBadge pos={item.position as Position} />
            <Text style={styles.meta}>
              {item.team ?? 'FA'}
              {item.age != null ? ` · ${item.age}` : ''}
              {` · ${item.position}${item.posRookieRank} rookie`}
            </Text>
          </View>
        </View>
        <View style={styles.rowRight}>
          <TierBadge tier={tier} size="sm" />
          {value != null ? (
            <Text style={styles.value}>{value.toLocaleString()}</Text>
          ) : null}
        </View>
      </View>
    );
  };

  // Flag off: no entry point exists, so this can only be a stale deep link.
  if (!enabled) {
    return (
      <SafeAreaView style={styles.safe} edges={['bottom']}>
        <View style={styles.center}>
          <Text style={styles.emptyBody}>
            Rookie rankings aren't available yet.
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />

      <View style={styles.header}>
        <TickLabel>Rookies</TickLabel>
        <Text style={styles.hint}>
          Every rookie on your board, ranked across positions. These are the
          same values as your position boards — ranking a rookie anywhere
          moves them here too.
        </Text>
      </View>

      <View style={styles.formatRow}>
        <FormatToggle
          value={activeFormat}
          onChange={onFormatChange}
          disabled={formatSwitching}
        />
      </View>

      {/* Position filter — PositionTabs construction; a filter over the ONE
          consolidated list (no second fetch), so switching is instant and
          the cross-position ranks stay stable. */}
      <View style={styles.filterRow}>
        {FILTERS.map((f) => {
          const active = f === filter;
          return (
            <Pressable
              key={f}
              testID={`rookie-ranks.filter.${f.toLowerCase()}`}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              accessibilityLabel={f === 'ALL' ? 'All positions' : f}
              onPress={() => {
                if (f === filter) return;
                haptics.selection();
                setFilter(f);
              }}
              style={({ pressed }) => [
                styles.filterSeg,
                active && styles.filterSegActive,
                active && { borderBottomColor: filterUnderline(f) },
                pressed && !active && { backgroundColor: ink.ink3 },
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
          <ActivityIndicator color={ice.base} />
        </View>
      ) : scopeEmpty ? (
        <RookieScopeEmpty surface="rookie-ranks" empty={scopeEmpty} />
      ) : ranksQuery.isError ? (
        <View style={styles.center}>
          <Text style={styles.emptyBody}>Could not load rookie rankings.</Text>
          <Button
            variant="secondary"
            compact
            label="Try again"
            onPress={() => ranksQuery.refetch()}
          />
        </View>
      ) : visible.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.emptyBody}>
            No rookie {filter === 'ALL' ? 'players' : `${filter}s`} on your
            board yet.
          </Text>
        </View>
      ) : (
        <FlatList
          testID="rookie-ranks.list"
          data={visible}
          keyExtractor={(r) => r.id}
          renderItem={renderRow}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl
              refreshing={ranksQuery.isFetching && !ranksQuery.isLoading}
              onRefresh={() => ranksQuery.refetch()}
              tintColor={ice.base}
            />
          }
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  header: { paddingHorizontal: space.lg, paddingTop: space.md, gap: space.xs },
  hint: { ...type.bodySm, lineHeight: 19 },
  formatRow: { marginHorizontal: space.lg, marginTop: space.sm },
  filterRow: {
    flexDirection: 'row',
    marginHorizontal: space.lg,
    marginTop: space.sm,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  filterSeg: {
    flex: 1,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  filterSegActive: { backgroundColor: ink.ink3 },
  filterText: { ...type.label },
  filterTextActive: { color: chalk.base },

  list: { padding: space.lg, gap: space.xs },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    minHeight: 56,
  },
  rank: { ...type.data, color: chalk.dim, minWidth: 28 },
  rowMain: { flex: 1, gap: 2 },
  name: { ...type.title },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  meta: { ...type.bodySm, color: chalk.dim, flexShrink: 1 },
  rowRight: { alignItems: 'flex-end', gap: 2 },
  value: { ...type.data, color: chalk.dim },

  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: space.lg,
    gap: space.md,
  },
  emptyBody: { ...type.bodySm, textAlign: 'center' },
});
