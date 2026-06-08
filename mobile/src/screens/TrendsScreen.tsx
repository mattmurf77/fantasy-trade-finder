import React, { useMemo, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  ScrollView,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import PositionChip from '../components/PositionChip';
import TrendBar from '../components/TrendBar';
import { getRisersAndFallers, getContrarianGap } from '../api/rankings';
import { useSession } from '../state/useSession';
import type {
  Position,
  TrendRow,
  ContrarianGapEntry,
} from '../shared/types';

type PositionFilter = Position | 'ALL';
const FILTERS: PositionFilter[] = ['ALL', 'QB', 'RB', 'WR', 'TE'];
const TOP_N_MOVERS = 10;
const TOP_N_GAP    = 5;
const WINDOW_DAYS  = 30;

// Trends sub-screen of the Rank stack. Three stacked sections:
//   1. Risers (top-N over the last 30 days by ELO delta)
//   2. Fallers (top-N over the last 30 days by ELO delta)
//   3. Easiest sells + easiest buys (per-player consensus gap report)
// Mirrors the web's Rank Players → Trends view (see app.js loadTrends).
export default function TrendsScreen() {
  const [filter, setFilter] = useState<PositionFilter>('ALL');
  const leagueId = useSession((s) => s.league?.league_id);

  const moversQuery = useQuery({
    queryKey: ['trends', 'risers-fallers', WINDOW_DAYS, TOP_N_MOVERS],
    queryFn: () => getRisersAndFallers({ days: WINDOW_DAYS, topN: TOP_N_MOVERS }),
    staleTime: 60_000,
  });

  const gapQuery = useQuery({
    queryKey: ['trends', 'consensus-gap', leagueId, TOP_N_GAP],
    // Guarded by `enabled` so we never call with an empty leagueId.
    queryFn: () =>
      getContrarianGap({ leagueId: leagueId as string, topN: TOP_N_GAP }),
    enabled: !!leagueId,
    staleTime: 60_000,
  });

  const onRefresh = useCallback(() => {
    moversQuery.refetch();
    if (leagueId) gapQuery.refetch();
  }, [moversQuery, gapQuery, leagueId]);

  const refreshing =
    (moversQuery.isFetching && !moversQuery.isLoading) ||
    (gapQuery.isFetching && !gapQuery.isLoading);

  const risers: TrendRow[] = useMemo(() => {
    const d = moversQuery.data;
    if (!d?.risers) return [];
    const rows = (d.risers[filter] || []) as TrendRow[];
    // Backend already sorts; only show real risers (delta > 0).
    return rows.filter((r) => (r.delta || 0) > 0);
  }, [moversQuery.data, filter]);

  const fallers: TrendRow[] = useMemo(() => {
    const d = moversQuery.data;
    if (!d?.fallers) return [];
    const rows = (d.fallers[filter] || []) as TrendRow[];
    return rows.filter((r) => (r.delta || 0) < 0);
  }, [moversQuery.data, filter]);

  // Magnitude scale per section so each bar normalises against its own max.
  const risersMax  = useMemo(() => maxAbsDelta(risers),  [risers]);
  const fallersMax = useMemo(() => maxAbsDelta(fallers), [fallers]);

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

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.accent}
          />
        }
      >
        {/* Risers */}
        <SectionHeader title={`Risers (${WINDOW_DAYS} days)`} />
        <SectionBody
          loading={moversQuery.isLoading}
          error={moversQuery.isError}
          retry={() => moversQuery.refetch()}
          empty={
            !moversQuery.data?.has_history
              ? 'Keep ranking to see trends here.'
              : risers.length === 0
                ? 'No risers in this window.'
                : null
          }
        >
          {risers.map((r) => (
            <MoveRow key={r.player_id} row={r} max={risersMax} kind="up" />
          ))}
        </SectionBody>

        {/* Fallers */}
        <SectionHeader title={`Fallers (${WINDOW_DAYS} days)`} />
        <SectionBody
          loading={moversQuery.isLoading}
          error={moversQuery.isError}
          retry={() => moversQuery.refetch()}
          empty={
            !moversQuery.data?.has_history
              ? 'Keep ranking to see trends here.'
              : fallers.length === 0
                ? 'No fallers in this window.'
                : null
          }
        >
          {fallers.map((r) => (
            <MoveRow key={r.player_id} row={r} max={fallersMax} kind="down" />
          ))}
        </SectionBody>

        {/* Consensus gap */}
        <SectionHeader title="Easiest sells & easiest buys" />
        <SectionBody
          loading={!!leagueId && gapQuery.isLoading}
          error={gapQuery.isError}
          retry={() => gapQuery.refetch()}
          empty={
            !leagueId
              ? 'Connect a league to see consensus gaps.'
              : !gapQuery.data?.has_baseline
                ? 'Not enough leaguemate rankings yet. Keep ranking to see trends here.'
                : (gapQuery.data.easiest_sells.length === 0 &&
                   gapQuery.data.easiest_buys.length === 0)
                  ? 'No standout gaps right now.'
                  : null
          }
        >
          <GapBlock
            label="Easiest sells (you value above market)"
            rows={filterGap(gapQuery.data?.easiest_sells, filter)}
            mode="sell"
          />
          <GapBlock
            label="Easiest buys (you value above owner)"
            rows={filterGap(gapQuery.data?.easiest_buys, filter)}
            mode="buy"
          />
        </SectionBody>
      </ScrollView>
    </SafeAreaView>
  );
}

// ── Helpers ─────────────────────────────────────────────────────────────

function maxAbsDelta(rows: TrendRow[]): number {
  return rows.reduce((m, r) => Math.max(m, Math.abs(r.delta || 0)), 0);
}

// Format a rank delta with an up/down arrow. Returns null when the delta can't
// be derived (insufficient history) so callers can degrade to "—".
function formatRankDelta(delta?: number | null): string | null {
  if (delta == null) return null;
  if (delta > 0) return `▲${delta}`;
  if (delta < 0) return `▼${Math.abs(delta)}`;
  return '–0';
}

// Position-aware label for a positional rank, e.g. "RB7". Falls back to "#7".
function posRankLabel(rank?: number | null, position?: string): string | null {
  if (rank == null) return null;
  const pos = (position || '').toUpperCase();
  return pos ? `${pos}${rank}` : `#${rank}`;
}

function filterGap(rows: ContrarianGapEntry[] | undefined, f: PositionFilter): ContrarianGapEntry[] {
  if (!rows) return [];
  if (f === 'ALL') return rows;
  return rows.filter((r) => (r.position || '').toUpperCase() === f);
}

// ── Sub-components ──────────────────────────────────────────────────────

function SectionHeader({ title }: { title: string }) {
  return <Text style={styles.sectionHeader}>{title}</Text>;
}

interface SectionBodyProps {
  loading: boolean;
  error: boolean;
  retry: () => void;
  empty: string | null;
  children: React.ReactNode;
}
function SectionBody({ loading, error, retry, empty, children }: SectionBodyProps) {
  if (loading) {
    return (
      <View style={[styles.sectionCard, styles.sectionCenter]}>
        <ActivityIndicator color={colors.accent} />
      </View>
    );
  }
  if (error) {
    return (
      <View style={[styles.sectionCard, styles.sectionCenter]}>
        <Text style={styles.errorText}>Couldn't load.</Text>
        <Pressable onPress={retry}>
          <Text style={styles.retry}>Try again</Text>
        </Pressable>
      </View>
    );
  }
  if (empty) {
    return (
      <View style={[styles.sectionCard, styles.sectionCenter]}>
        <Text style={styles.emptyBody}>{empty}</Text>
      </View>
    );
  }
  return <View style={styles.sectionCard}>{children}</View>;
}

interface MoveRowProps {
  row: TrendRow;
  max: number;
  kind: 'up' | 'down';
}
function MoveRow({ row, max, kind }: MoveRowProps) {
  const delta = row.delta || 0;
  const sign  = delta > 0 ? '+' : '';
  const deltaColor = kind === 'up' ? colors.green : colors.red;

  // Rank deltas are the primary, more-intuitive signal (FB-04). ELO delta stays
  // as a clearly-labeled secondary number on the right.
  const overallRank      = row.overall_rank;
  const overallRankDelta = formatRankDelta(row.overall_rank_delta);
  const posRankDelta     = formatRankDelta(row.pos_rank_delta);
  const posLabel         = posRankLabel(row.pos_rank, row.position as string);

  // Compose the rank line, e.g. "Overall #12 ▲3 · RB7 ▲1". Degrades to "—".
  const rankParts: string[] = [];
  if (overallRank != null) {
    rankParts.push(
      `Overall #${overallRank}${overallRankDelta ? ` ${overallRankDelta}` : ''}`,
    );
  } else if (overallRankDelta) {
    rankParts.push(`Overall ${overallRankDelta}`);
  }
  if (posLabel != null) {
    rankParts.push(`${posLabel}${posRankDelta ? ` ${posRankDelta}` : ''}`);
  }
  const rankLine = rankParts.length ? rankParts.join(' · ') : '—';

  return (
    <View style={styles.row}>
      <View style={{ flex: 1, minWidth: 0 }}>
        <View style={styles.rowTopLine}>
          <Text style={styles.name} numberOfLines={1}>
            {row.name || row.player_id}
          </Text>
          {row.position ? (
            <PositionChip position={row.position as Position} size="sm" />
          ) : null}
        </View>
        <Text style={[styles.rankLine, { color: deltaColor }]} numberOfLines={1}>
          {rankLine}
        </Text>
        <Text style={styles.meta} numberOfLines={1}>
          {Math.round(row.previous_elo)} → {Math.round(row.current_elo)} ELO
        </Text>
        <View style={styles.barWrap}>
          <TrendBar delta={delta} max={max} />
        </View>
      </View>
      <View style={styles.deltaWrap}>
        <Text style={[styles.deltaNum, { color: deltaColor }]}>
          {sign}{delta.toFixed(1)}
        </Text>
        <Text style={styles.deltaLabel}>ELO</Text>
      </View>
    </View>
  );
}

interface GapBlockProps {
  label: string;
  rows: ContrarianGapEntry[];
  mode: 'sell' | 'buy';
}
function GapBlock({ label, rows, mode }: GapBlockProps) {
  if (rows.length === 0) {
    return (
      <View>
        <Text style={styles.subHeader}>{label}</Text>
        <Text style={styles.emptyInline}>None for this filter.</Text>
      </View>
    );
  }
  return (
    <View>
      <Text style={styles.subHeader}>{label}</Text>
      {rows.map((r) => (
        <GapRow key={r.player_id} row={r} mode={mode} />
      ))}
    </View>
  );
}

function GapRow({ row, mode }: { row: ContrarianGapEntry; mode: 'sell' | 'buy' }) {
  const compareElo = mode === 'sell' ? row.community_elo : row.owner_elo;
  const compareLabel = mode === 'sell' ? 'consensus' : (row.owner_username || 'owner');

  // Express the gap as a rank difference where meaningful (FB-04): your rank vs
  // the comparison rank. Prefer the rank view; fall back to the ELO gap when no
  // rank could be derived.
  const rankGap = row.rank_gap;
  const haveRanks = row.user_rank != null && row.comparison_rank != null;
  const rankMeta = haveRanks
    ? `You #${row.user_rank} · ${compareLabel} #${row.comparison_rank}`
    : null;

  return (
    <View style={styles.row}>
      <View style={{ flex: 1, minWidth: 0 }}>
        <View style={styles.rowTopLine}>
          <Text style={styles.name} numberOfLines={1}>
            {row.name || row.player_id}
          </Text>
          {row.position ? (
            <PositionChip position={row.position as Position} size="sm" />
          ) : null}
        </View>
        {rankMeta ? (
          <Text style={styles.meta} numberOfLines={1}>
            {rankMeta}
          </Text>
        ) : null}
        <Text style={styles.meta} numberOfLines={1}>
          You {Math.round(row.user_elo)} · {compareLabel}{' '}
          {compareElo != null ? Math.round(compareElo) : '—'}
        </Text>
      </View>
      <View style={styles.deltaWrap}>
        {rankGap != null && rankGap > 0 ? (
          <>
            <Text style={[styles.deltaNum, { color: colors.green }]}>
              ▲{rankGap}
            </Text>
            <Text style={styles.deltaLabel}>RANK</Text>
          </>
        ) : (
          <>
            <Text style={[styles.deltaNum, { color: colors.green }]}>
              +{(row.gap || 0).toFixed(1)}
            </Text>
            <Text style={styles.deltaLabel}>GAP</Text>
          </>
        )}
      </View>
    </View>
  );
}

// ── Styles ──────────────────────────────────────────────────────────────

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

  scroll: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xxl,
  },

  sectionHeader: {
    color: colors.text,
    fontSize: fontSize.base,
    fontWeight: '800',
    marginTop: spacing.lg,
    marginBottom: spacing.sm,
  },
  sectionCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  sectionCenter: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.xl,
    gap: spacing.sm,
  },

  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
    borderBottomColor: colors.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  rowTopLine: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  name: {
    color: colors.text,
    fontSize: fontSize.base,
    fontWeight: '700',
    flexShrink: 1,
  },
  rankLine: { fontSize: fontSize.sm, fontWeight: '700', marginTop: 2 },
  meta: { color: colors.muted, fontSize: fontSize.xs, marginTop: 2 },
  barWrap: { marginTop: spacing.sm },

  deltaWrap: { alignItems: 'flex-end', minWidth: 72 },
  deltaNum: { fontSize: fontSize.base, fontWeight: '800' },
  deltaLabel: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
  },

  subHeader: {
    color: colors.muted,
    fontSize: fontSize.xs,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
    marginTop: spacing.md,
    marginBottom: spacing.xs,
  },
  emptyInline: {
    color: colors.muted,
    fontSize: fontSize.sm,
    paddingVertical: spacing.md,
  },
  emptyBody: {
    color: colors.muted,
    fontSize: fontSize.sm,
    textAlign: 'center',
    lineHeight: 22,
  },
  errorText: { color: colors.red },
  retry: { color: colors.accent, fontWeight: '700' },
});
