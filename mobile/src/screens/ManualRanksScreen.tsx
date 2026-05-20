import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  TextInput,
  Keyboard,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import DraggableFlatList, {
  RenderItemParams,
  DragEndParams,
} from 'react-native-draggable-flatlist';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import PositionChip from '../components/PositionChip';
import { getRankings, reorderRankings } from '../api/rankings';
import { haptics } from '../utils/haptics';
import { startSpan } from '../observability/sentry';
import type { Position, RankedPlayer } from '../shared/types';

// ── Manual Ranks ──────────────────────────────────────────────────────
// Editable counterpart to OverallRanksScreen. Users can:
//   • Long-press (220ms) a row and drag it to a new position.
//   • Tap the rank number to type in a target rank (jump-to-rank).
// Both gestures kick the same `reorderRankings` save path.
//
// Saves are debounced 600ms after the last reorder so a rapid-fire series
// of drags coalesces into one network call (matches the web's manual-
// ranks pattern). A small header pill conveys save status: green dot for
// "saved", spinner for "saving…", red pill for "error".

const FILTERS: (Position | 'ALL')[] = ['ALL', 'QB', 'RB', 'WR', 'TE'];
const SAVE_DEBOUNCE_MS = 600;
const DRAG_ACTIVATION_MS = 220;

type SaveStatus = 'idle' | 'pending' | 'saving' | 'saved' | 'error';

export default function ManualRanksScreen() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<Position | 'ALL'>('ALL');
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const [errorText, setErrorText] = useState<string | null>(null);

  // Local list state — driven from the server fetch but mutated client-
  // side during drag/jump so the UI stays responsive. We snapshot back to
  // the server on debounce expiry.
  const [rows, setRows] = useState<RankedPlayer[]>([]);

  // Pull the full unfiltered list once and filter client-side so flipping
  // chips is instant (same approach as OverallRanksScreen). The reorder
  // endpoint accepts a per-position `ordered_ids` payload — when the
  // filter is 'ALL' we send `position: null` and the full ID list.
  const ranksQuery = useQuery({
    queryKey: ['rankings', 'all'],
    queryFn: () => getRankings(null),
    staleTime: 30_000,
  });

  // Snapshot the server result into local state on load. Re-sync whenever
  // the underlying query data changes (e.g. invalidation from elsewhere).
  // We dedupe ELO-sort so the initial order matches OverallRanks.
  useEffect(() => {
    const all = (ranksQuery.data?.rankings || []) as RankedPlayer[];
    const sorted = [...all].sort((a, b) => (b.elo || 0) - (a.elo || 0));
    setRows(sorted);
  }, [ranksQuery.data]);

  // Visible rows = filter-applied view of the local state. Drag mutations
  // happen on the FILTERED list, then we splice the result back into the
  // overall ordering so unrelated positions don't lose their place. This
  // matches the web's "filter the view, edit the underlying overall list"
  // model.
  const visibleRows: RankedPlayer[] = useMemo(() => {
    return filter === 'ALL' ? rows : rows.filter((r) => r.position === filter);
  }, [rows, filter]);

  // ── Save plumbing ─────────────────────────────────────────────────
  // Debounce + mutation. We hold the latest `ordered_ids` payload in a
  // ref so a string of drag-ends just resets the timer; the timer fires
  // ONE network call with the most recent ordering. Status flows:
  //   pending  → user just made a change, timer running
  //   saving   → mutation in flight
  //   saved    → success
  //   error    → mutation rejected; click rows again to retry
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingPayload = useRef<{ position: Position | null; orderedIds: string[] } | null>(null);

  const saveMutation = useMutation({
    mutationFn: ({ position, orderedIds }: { position: Position | null; orderedIds: string[] }) =>
      startSpan({ name: 'rankings.reorder', op: 'mutation' }, () =>
        reorderRankings(position, orderedIds),
      ),
    onMutate: () => setSaveStatus('saving'),
    onSuccess: () => {
      setSaveStatus('saved');
      setErrorText(null);
      // Reorder may invalidate downstream caches (tier status, progress)
      // — refetch lazily.
      queryClient.invalidateQueries({ queryKey: ['rankings'] });
      queryClient.invalidateQueries({ queryKey: ['tiers-status'] });
      queryClient.invalidateQueries({ queryKey: ['progress'] });
    },
    onError: (e: Error) => {
      setSaveStatus('error');
      setErrorText(e.message || 'Save failed');
    },
  });

  // Schedule (or reschedule) the debounced save. Caller passes the
  // CURRENT full local state so we always derive ordered_ids from a
  // post-mutation snapshot — never from stale closure state.
  const scheduleSave = useCallback(
    (nextRows: RankedPlayer[]) => {
      setSaveStatus('pending');
      // When the user is filtering by a single position, send THAT
      // position's slice — backend's apply_reorder writes only those
      // ELOs. With 'ALL' we send the entire list with position: null
      // so the backend recomputes overall ELO ordering across positions.
      let position: Position | null;
      let orderedIds: string[];
      if (filter === 'ALL') {
        position = null;
        orderedIds = nextRows.map((r) => r.id);
      } else {
        position = filter;
        orderedIds = nextRows.filter((r) => r.position === filter).map((r) => r.id);
      }
      pendingPayload.current = { position, orderedIds };

      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      debounceTimer.current = setTimeout(() => {
        const payload = pendingPayload.current;
        if (!payload) return;
        // /api/rankings/reorder requires ≥2 ids — skip if the user
        // somehow drained the list to a single row in the filtered view.
        if (payload.orderedIds.length < 2) {
          setSaveStatus('idle');
          return;
        }
        saveMutation.mutate(payload);
      }, SAVE_DEBOUNCE_MS);
    },
    [filter, saveMutation],
  );

  // Cancel pending debounce on unmount so we don't fire a save against
  // an unmounted query client.
  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, []);

  // ── Drag handler ──────────────────────────────────────────────────
  // `data` from DraggableFlatList is the new order of the VISIBLE
  // (filtered) rows. When filtered, we splice that sub-order back into
  // the full `rows` list, preserving the relative order of rows that
  // weren't part of the visible set.
  const onDragEnd = useCallback(
    ({ data: newVisible, from, to }: DragEndParams<RankedPlayer>) => {
      if (from === to) return;        // no-op
      haptics.success();
      setRows((prev) => {
        let next: RankedPlayer[];
        if (filter === 'ALL') {
          next = newVisible;
        } else {
          // Walk prev; whenever we hit a row in the visible set, replace
          // it with the next item from newVisible (in newVisible's order).
          const visibleIter = newVisible[Symbol.iterator]();
          next = prev.map((r) =>
            r.position === filter ? (visibleIter.next().value as RankedPlayer) : r,
          );
        }
        scheduleSave(next);
        return next;
      });
    },
    [filter, scheduleSave],
  );

  // ── Inline rank edit ──────────────────────────────────────────────
  // Tap a row's rank number → that row enters edit mode. The TextInput
  // shows current visible-index+1; on blur (or submit) we move the row
  // to the typed target index in the filtered view, then splice the
  // change back into `rows` like the drag path.
  const [editingPid, setEditingPid] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');

  const commitRankEdit = useCallback(() => {
    if (!editingPid) return;
    const target = parseInt(editValue, 10);
    setEditingPid(null);
    setEditValue('');
    if (!Number.isFinite(target) || target < 1) return;

    setRows((prev) => {
      // Resolve indexes in the FILTERED view first.
      const visible = filter === 'ALL' ? prev : prev.filter((r) => r.position === filter);
      const fromVisIdx = visible.findIndex((r) => r.id === editingPid);
      if (fromVisIdx < 0) return prev;
      const toVisIdx = Math.max(0, Math.min(visible.length - 1, target - 1));
      if (toVisIdx === fromVisIdx) return prev;

      const newVisible = [...visible];
      const [moved] = newVisible.splice(fromVisIdx, 1);
      newVisible.splice(toVisIdx, 0, moved);

      let next: RankedPlayer[];
      if (filter === 'ALL') {
        next = newVisible;
      } else {
        const visibleIter = newVisible[Symbol.iterator]();
        next = prev.map((r) =>
          r.position === filter ? (visibleIter.next().value as RankedPlayer) : r,
        );
      }
      scheduleSave(next);
      haptics.success();
      return next;
    });
  }, [editingPid, editValue, filter, scheduleSave]);

  // ── Render helpers ────────────────────────────────────────────────
  const renderItem = useCallback(
    ({ item, drag, isActive, getIndex }: RenderItemParams<RankedPlayer>) => {
      const visIdx = getIndex();
      const rankNum = visIdx != null ? visIdx + 1 : 0;
      const isEditing = editingPid === item.id;
      const ageStr = item.age != null ? `${item.age} yo` : null;

      return (
        <Pressable
          onLongPress={drag}
          delayLongPress={DRAG_ACTIVATION_MS}
          disabled={isActive || isEditing}
          style={({ pressed }) => [
            styles.row,
            isActive && styles.rowActive,
            pressed && !isActive && { backgroundColor: 'rgba(79,124,255,0.06)' },
          ]}
        >
          {isEditing ? (
            <TextInput
              autoFocus
              keyboardType="number-pad"
              value={editValue}
              onChangeText={setEditValue}
              onBlur={commitRankEdit}
              onSubmitEditing={commitRankEdit}
              maxLength={4}
              style={styles.rankInput}
              selectTextOnFocus
            />
          ) : (
            <Pressable
              onPress={() => {
                setEditingPid(item.id);
                setEditValue(String(rankNum));
                haptics.selection();
              }}
              hitSlop={8}
              style={styles.rankNumWrap}
            >
              <Text style={styles.rankNum}>{rankNum}</Text>
            </Pressable>
          )}
          <PositionChip position={item.position as Position} size="sm" />
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={styles.name} numberOfLines={1}>{item.name}</Text>
            <Text style={styles.meta} numberOfLines={1}>
              {(item.team || 'FA')}{ageStr ? ` · ${ageStr}` : ''}
              {item.injury_status ? ` · ${item.injury_status}` : ''}
            </Text>
          </View>
          <View style={styles.eloWrap}>
            <Text style={styles.eloNum}>{Math.round(item.elo)}</Text>
            <Text style={styles.eloLabel}>ELO</Text>
          </View>
        </Pressable>
      );
    },
    [commitRankEdit, editValue, editingPid],
  );

  // ── Header save indicator ─────────────────────────────────────────
  // Renders one of three states. The "saved" dot fades back to idle
  // after a brief delay so the indicator doesn't get noisy.
  useEffect(() => {
    if (saveStatus !== 'saved') return;
    const t = setTimeout(() => setSaveStatus('idle'), 1500);
    return () => clearTimeout(t);
  }, [saveStatus]);

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <View style={styles.headerRow}>
        <Text style={styles.title}>Manual Ranks</Text>
        <SaveIndicator status={saveStatus} errorText={errorText} />
      </View>

      <Text style={styles.hint}>
        Long-press + drag a row to re-rank. Tap the rank number to jump to a
        specific spot.
      </Text>

      <View style={styles.filterRow}>
        {FILTERS.map((f) => {
          const active = f === filter;
          return (
            <Pressable
              key={f}
              onPress={() => {
                if (f === filter) return;
                // Dismiss any in-flight rank edit; the visible index would
                // be ambiguous across a filter switch.
                setEditingPid(null);
                setEditValue('');
                Keyboard.dismiss();
                setFilter(f);
              }}
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
      ) : visibleRows.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.emptyTitle}>No rankings yet</Text>
          <Text style={styles.emptyBody}>
            Rank a few trios on the Trios tab to populate your overall board.
          </Text>
        </View>
      ) : (
        <DraggableFlatList
          data={visibleRows}
          keyExtractor={(r) => r.id}
          renderItem={renderItem}
          onDragEnd={onDragEnd}
          activationDistance={5}
          containerStyle={styles.listContainer}
          contentContainerStyle={styles.listContent}
          ItemSeparatorComponent={() => <View style={styles.sep} />}
        />
      )}
    </SafeAreaView>
  );
}

// Header pill that conveys save state. "Pending" looks identical to
// "saving" — both are in-progress from the user's POV — but we route
// them through different colors so the diff is visible in screenshots /
// e2e tests.
function SaveIndicator({ status, errorText }: { status: SaveStatus; errorText: string | null }) {
  if (status === 'idle') return null;
  if (status === 'saving' || status === 'pending') {
    return (
      <View style={styles.saveIndicatorWrap}>
        <ActivityIndicator size="small" color={colors.muted} />
        <Text style={styles.saveIndicatorText}>saving…</Text>
      </View>
    );
  }
  if (status === 'saved') {
    return (
      <View style={styles.saveIndicatorWrap}>
        <View style={styles.savedDot} />
        <Text style={styles.savedText}>saved</Text>
      </View>
    );
  }
  // error
  return (
    <View style={[styles.saveIndicatorWrap, styles.errorPill]}>
      <Text style={styles.errorPillText} numberOfLines={1}>
        {errorText || 'error'}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  title: { color: colors.text, fontSize: fontSize.lg, fontWeight: '800' },

  // Save status indicator — three visual variants.
  saveIndicatorWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  saveIndicatorText: { color: colors.muted, fontSize: fontSize.xs, fontWeight: '700' },
  savedDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.green,
  },
  savedText: { color: colors.green, fontSize: fontSize.xs, fontWeight: '800' },
  errorPill: {
    backgroundColor: 'rgba(239,68,68,0.14)',
    borderColor: 'rgba(239,68,68,0.45)',
    borderWidth: 1,
    borderRadius: radius.pill,
  },
  errorPillText: {
    color: colors.red,
    fontSize: fontSize.xs,
    fontWeight: '700',
    maxWidth: 180,
  },

  hint: {
    color: colors.muted,
    fontSize: fontSize.xs,
    textAlign: 'center',
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
  },

  filterRow: {
    flexDirection: 'row',
    gap: spacing.xs,
    paddingHorizontal: spacing.lg,
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

  listContainer: { flex: 1 },
  listContent: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xxl },

  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.xs,
  },
  rowActive: {
    backgroundColor: 'rgba(79,124,255,0.10)',
    borderRadius: radius.md,
    ...Platform.select({
      ios: {
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.35,
        shadowRadius: 8,
      },
      android: { elevation: 6 },
    }),
  },
  sep: { height: 1, backgroundColor: colors.border, opacity: 0.5 },

  rankNumWrap: { width: 36, alignItems: 'center' },
  rankNum: {
    color: colors.muted,
    fontSize: fontSize.sm,
    fontWeight: '800',
    textAlign: 'center',
  },
  rankInput: {
    width: 48,
    color: colors.text,
    fontSize: fontSize.sm,
    fontWeight: '800',
    textAlign: 'center',
    backgroundColor: colors.surface,
    borderColor: colors.accent,
    borderWidth: 1,
    borderRadius: radius.sm,
    paddingVertical: 4,
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
