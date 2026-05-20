import React, { useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  Modal,
  ScrollView,
  ActivityIndicator,
} from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import PositionChip from './PositionChip';
import { getRookies, type RookiePlayer } from '../api/rankings';
import type { Position } from '../shared/types';

interface Props {
  visible: boolean;
  onClose: () => void;
}

type Filter = 'ALL' | Position;
const FILTERS: Filter[] = ['ALL', 'QB', 'RB', 'WR', 'TE'];

// Bottom-sheet rookie draft board. Mirrors the web app's rookie overlay
// (openRookieBoard / renderRookieList in web/js/app.js): filterable list
// of rookie / first-year / pre-draft prospect players sorted by Sleeper
// search_rank. Read-only — useful during dynasty rookie draft prep.
export default function RookieDraftBoardSheet({ visible, onClose }: Props) {
  const [filter, setFilter] = useState<Filter>('ALL');

  // Only fetch once the sheet has been opened — keeps boot-time network
  // chatter down. Cached for the session so reopens are instant.
  const query = useQuery({
    queryKey: ['rookies'],
    queryFn: () => getRookies(),
    enabled: visible,
    staleTime: 5 * 60_000,
  });

  const rows = useMemo<RookiePlayer[]>(() => {
    const grouped = query.data?.grouped;
    if (!grouped) return [];
    if (filter === 'ALL') {
      // Merge then sort by search_rank (NULLs last) so the global list
      // matches the web's flattened view.
      const all = [...(grouped.QB ?? []), ...(grouped.RB ?? []), ...(grouped.WR ?? []), ...(grouped.TE ?? [])];
      return all.sort((a, b) => {
        const ar = a.search_rank ?? Number.POSITIVE_INFINITY;
        const br = b.search_rank ?? Number.POSITIVE_INFINITY;
        return ar - br;
      });
    }
    return grouped[filter] ?? [];
  }, [query.data, filter]);

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <Pressable style={styles.backdrop} onPress={onClose} />
      <View style={styles.sheet}>
        <View style={styles.handle} />
        <View style={styles.headerRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.title}>Rookie Draft Board</Text>
            <Text style={styles.sub}>
              First-year players and pre-draft prospects.
            </Text>
          </View>
          <Pressable
            onPress={onClose}
            hitSlop={12}
            style={({ pressed }) => [styles.closeBtn, pressed && { opacity: 0.6 }]}
          >
            <Text style={styles.closeText}>✕</Text>
          </Pressable>
        </View>

        {/* Position filter chips */}
        <View style={styles.filterRow}>
          {FILTERS.map((f) => {
            const isActive = f === filter;
            return (
              <Pressable
                key={f}
                onPress={() => setFilter(f)}
                style={({ pressed }) => [
                  styles.filterChip,
                  isActive && styles.filterChipActive,
                  pressed && { opacity: 0.7 },
                ]}
              >
                <Text style={[styles.filterText, isActive && styles.filterTextActive]}>
                  {f}
                </Text>
              </Pressable>
            );
          })}
        </View>

        {/* List */}
        {query.isLoading ? (
          <View style={styles.centered}>
            <ActivityIndicator color={colors.accent} />
          </View>
        ) : query.isError ? (
          <View style={styles.centered}>
            <Text style={styles.errorText}>Failed to load rookie data.</Text>
            <Pressable onPress={() => query.refetch()}>
              <Text style={styles.retryText}>Try again</Text>
            </Pressable>
          </View>
        ) : rows.length === 0 ? (
          <View style={styles.centered}>
            <Text style={styles.emptyText}>
              {filter === 'ALL'
                ? 'No rookie data available yet.'
                : `No ${filter} rookies found.`}
            </Text>
          </View>
        ) : (
          <ScrollView style={styles.list} contentContainerStyle={styles.listContent}>
            {rows.map((r, idx) => (
              <View key={r.id} style={styles.row}>
                <Text style={styles.rank}>{idx + 1}</Text>
                <View style={styles.info}>
                  <Text style={styles.name} numberOfLines={1}>
                    {r.name || '?'}
                  </Text>
                  <View style={styles.metaRow}>
                    <PositionChip position={r.position} size="sm" />
                    <Text style={styles.meta} numberOfLines={1}>
                      {[
                        r.team || 'Undrafted',
                        r.age != null ? `Age ${r.age}` : null,
                        r.college || null,
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </Text>
                  </View>
                </View>
              </View>
            ))}
          </ScrollView>
        )}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.55)' },
  sheet: {
    position: 'absolute',
    left: 0, right: 0, bottom: 0,
    maxHeight: '90%',
    backgroundColor: colors.bg,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
    gap: spacing.sm,
  },
  handle: {
    alignSelf: 'center',
    width: 44, height: 4, borderRadius: 2,
    backgroundColor: colors.border,
    marginBottom: spacing.sm,
  },
  headerRow: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  title: { color: colors.text, fontSize: fontSize.xl, fontWeight: '800' },
  sub: { color: colors.muted, fontSize: fontSize.sm, marginTop: 2 },
  closeBtn: {
    width: 32, height: 32, borderRadius: 16,
    backgroundColor: colors.surface,
    borderWidth: 1, borderColor: colors.border,
    alignItems: 'center', justifyContent: 'center',
  },
  closeText: { color: colors.muted, fontSize: fontSize.base, fontWeight: '800' },

  filterRow: {
    flexDirection: 'row',
    gap: spacing.xs,
    marginTop: spacing.sm,
    marginBottom: spacing.xs,
  },
  filterChip: {
    flex: 1,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
  },
  filterChipActive: {
    backgroundColor: 'rgba(79,124,255,0.14)',
    borderColor: colors.accent,
  },
  filterText: { color: colors.muted, fontSize: fontSize.sm, fontWeight: '700' },
  filterTextActive: { color: colors.accent },

  list: { flexGrow: 0 },
  listContent: { paddingBottom: spacing.lg, gap: spacing.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  rank: {
    color: colors.muted,
    fontSize: fontSize.sm,
    fontWeight: '800',
    width: 28,
    textAlign: 'center',
  },
  info: { flex: 1, minWidth: 0, gap: 4 },
  name: { color: colors.text, fontSize: fontSize.base, fontWeight: '700' },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, flexWrap: 'wrap' },
  meta: { color: colors.muted, fontSize: fontSize.xs, flexShrink: 1 },

  centered: {
    paddingVertical: spacing.xxl,
    alignItems: 'center',
    gap: spacing.md,
  },
  emptyText: { color: colors.muted, fontSize: fontSize.sm, textAlign: 'center' },
  errorText: { color: colors.red, fontSize: fontSize.sm, textAlign: 'center' },
  retryText: { color: colors.accent, fontSize: fontSize.sm, fontWeight: '700' },
});
