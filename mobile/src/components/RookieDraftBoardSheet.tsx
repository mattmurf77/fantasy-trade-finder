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
import { ink, chalk, ice, semantic, space, radii, type, shadowSheet, scrim } from '../theme/chalkline';
import { Button, Icon } from './chalkline';
import PositionChip from './PositionChip';
import { getRookies, type RookiePlayer } from '../api/rankings';
import type { Position } from '../shared/types';

interface Props {
  visible: boolean;
  onClose: () => void;
}

type Filter = 'ALL' | Position;
const FILTERS: Filter[] = ['ALL', 'QB', 'RB', 'WR', 'TE'];

// Bottom-sheet rookie draft board (Chalkline sheet construction: ink-2
// surface, hairline border, sheet shadow, line-strong grabber, solid scrim;
// ghost filter tabs with ice underline; hairline table rows with mono rank
// numerals). Mirrors the web app's rookie overlay (openRookieBoard /
// renderRookieList in web/js/app.js): filterable list of rookie / first-year
// / pre-draft prospect players sorted by Sleeper search_rank. Read-only —
// useful during dynasty rookie draft prep.
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
      <Pressable
        style={styles.backdrop}
        onPress={onClose}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      <View style={styles.sheet}>
        <View style={styles.grabber} />
        <View style={styles.headerRow}>
          <View style={{ flex: 1 }}>
            <Text style={type.heading} accessibilityRole="header">Rookie Draft Board</Text>
            <Text style={[type.bodySm, styles.sub]}>
              First-year players and pre-draft prospects.
            </Text>
          </View>
          <Pressable
            onPress={onClose}
            hitSlop={12}
            accessibilityRole="button"
            accessibilityLabel="Close"
            style={({ pressed }) => [styles.closeBtn, pressed && styles.closeBtnPressed]}
          >
            <Icon name="x" size={20} color={chalk.dim} />
          </Pressable>
        </View>

        {/* Position filter tabs: ghost label text, active = chalk + ice underline */}
        <View style={styles.filterRow}>
          {FILTERS.map((f) => {
            const isActive = f === filter;
            return (
              <Pressable
                key={f}
                accessibilityRole="tab"
                accessibilityState={{ selected: isActive }}
                accessibilityLabel={f === 'ALL' ? 'All positions' : f}
                onPress={() => setFilter(f)}
                style={({ pressed }) => [
                  styles.filterTab,
                  pressed && styles.filterTabPressed,
                ]}
              >
                <Text style={[type.label, isActive && styles.filterTextActive]}>
                  {f}
                </Text>
                <View style={[styles.filterUnderline, isActive && styles.filterUnderlineActive]} />
              </Pressable>
            );
          })}
        </View>

        {/* List */}
        {query.isLoading ? (
          <View style={styles.centered}>
            <ActivityIndicator color={ice.base} />
          </View>
        ) : query.isError ? (
          <View style={styles.centered}>
            <Text style={styles.errorText}>Failed to load rookie data.</Text>
            <Button label="Try again" variant="ghost" compact onPress={() => query.refetch()} />
          </View>
        ) : rows.length === 0 ? (
          <View style={styles.centered}>
            <Text style={[type.bodySm, styles.emptyText]}>
              {filter === 'ALL'
                ? 'No rookie data available yet.'
                : `No ${filter} rookies found.`}
            </Text>
          </View>
        ) : (
          <ScrollView style={styles.list} contentContainerStyle={styles.listContent}>
            {rows.map((r, idx) => (
              <View
                key={r.id}
                style={[styles.row, idx === rows.length - 1 && styles.rowLast]}
              >
                <Text style={styles.rank}>{idx + 1}</Text>
                <View style={styles.info}>
                  <Text style={type.title} numberOfLines={1}>
                    {r.name || '?'}
                  </Text>
                  <View style={styles.metaRow}>
                    <PositionChip position={r.position} size="sm" />
                    <Text style={[type.bodySm, styles.meta]} numberOfLines={1}>
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
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheet: {
    position: 'absolute',
    left: 0, right: 0, bottom: 0,
    maxHeight: '90%',
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    padding: space.lg,
    paddingBottom: space.xxl,
    gap: space.sm,
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    backgroundColor: ink.lineStrong,
    marginBottom: space.sm,
  },
  headerRow: { flexDirection: 'row', alignItems: 'flex-start', gap: space.md },
  sub: { marginTop: 2 },
  closeBtn: {
    width: 32, height: 32, borderRadius: radii.sm,
    alignItems: 'center', justifyContent: 'center',
  },
  closeBtnPressed: { backgroundColor: ink.ink3 },

  filterRow: {
    flexDirection: 'row',
    gap: space.xs,
    marginTop: space.sm,
    marginBottom: space.xs,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  filterTab: {
    flex: 1,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
  },
  filterTabPressed: { backgroundColor: ink.ink3 },
  filterTextActive: { color: chalk.base },
  filterUnderline: {
    alignSelf: 'stretch',
    height: 2,
    backgroundColor: 'transparent',
  },
  filterUnderlineActive: { backgroundColor: ice.base },

  list: { flexGrow: 0 },
  listContent: { paddingBottom: space.lg },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.sm,
    paddingHorizontal: space.xs,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  rowLast: { borderBottomWidth: 0 },
  rank: {
    ...type.data,
    color: chalk.dim,
    width: 28,
    textAlign: 'center',
  },
  info: { flex: 1, minWidth: 0, gap: space.xs },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: space.xs, flexWrap: 'wrap' },
  meta: { flexShrink: 1 },

  centered: {
    paddingVertical: space.xxl,
    alignItems: 'center',
    gap: space.md,
  },
  emptyText: { textAlign: 'center' },
  errorText: { ...type.bodySm, color: semantic.neg, textAlign: 'center' },
});
