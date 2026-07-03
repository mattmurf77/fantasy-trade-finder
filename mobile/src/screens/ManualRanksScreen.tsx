import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  TextInput,
  Keyboard,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import DraggableFlatList, {
  RenderItemParams,
  DragEndParams,
} from 'react-native-draggable-flatlist';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ink, chalk, ice, semantic, position, space, radii, type } from '../theme/chalkline';
import { Button, Icon } from '../components/chalkline';
import PositionChip from '../components/PositionChip';
import { getRankings, reorderRankings } from '../api/rankings';
import { haptics } from '../utils/haptics';
import { startSpan } from '../observability/sentry';
import { useSession } from '../state/useSession';
import type { Position, RankedPlayer } from '../shared/types';

// ── Overall Ranks ─────────────────────────────────────────────────────
// The single editable rank board (labeled "Overall Ranks" in the UI; the
// component keeps the ManualRanks name for its route + drag engine, which
// FB-02 reads). Users can:
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

// PositionTabs underline: active segment underlines in that position's
// color; the Overall ("ALL") tab underlines in ice.
const FILTER_UNDERLINE: Record<Position | 'ALL', string> = {
  ALL: ice.base,
  QB: position.qb,
  RB: position.rb,
  WR: position.wr,
  TE: position.te,
};

type SaveStatus = 'idle' | 'pending' | 'saving' | 'saved' | 'error';

// ── RankEditRow ───────────────────────────────────────────────────────────
// Owns the draft string locally so the renderItem useCallback no longer
// depends on `editValue` state — only on `editingPid` + `commitRankEdit`.
// Keeps TextInput re-renders scoped to this component alone.
interface RankEditRowProps {
  initialValue: string;
  onCommit: (val: string) => void;
  onBlur?: () => void;
}
function RankEditRowInner({ initialValue, onCommit, onBlur }: RankEditRowProps) {
  const [draft, setDraft] = useState(initialValue);
  const handleCommit = useCallback(() => {
    onCommit(draft);
    onBlur?.();
  }, [draft, onCommit, onBlur]);
  return (
    <TextInput
      autoFocus
      keyboardType="number-pad"
      value={draft}
      onChangeText={setDraft}
      onBlur={handleCommit}
      onSubmitEditing={handleCommit}
      maxLength={4}
      style={styles.rankInput}
      selectTextOnFocus
    />
  );
}
const RankEditRow = React.memo(RankEditRowInner);

export default function ManualRanksScreen() {
  const queryClient = useQueryClient();
  const activeFormat = useSession((s) => s.activeFormat);
  const [filter, setFilter] = useState<Position | 'ALL'>('ALL');
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const [errorText, setErrorText] = useState<string | null>(null);

  // Local list state — driven from the server fetch but mutated client-
  // side during drag/jump so the UI stays responsive. We snapshot back to
  // the server on debounce expiry.
  const [rows, setRows] = useState<RankedPlayer[]>([]);

  // Pull the full unfiltered list once and filter client-side so flipping
  // chips is instant. The reorder
  // endpoint accepts a per-position `ordered_ids` payload — when the
  // filter is 'ALL' we send `position: null` and the full ID list.
  const ranksQuery = useQuery({
    queryKey: ['rankings', activeFormat, 'all'],
    queryFn: () => getRankings(null),
    staleTime: 30_000,
  });

  // Snapshot the server result into local state on load. Re-sync whenever
  // the underlying query data changes (e.g. invalidation from elsewhere).
  // ELO-sort so the initial order is best → worst.
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
      // — refetch lazily. Scope to activeFormat so only the current
      // format's cache entries are stale; the other format's data is
      // still valid.
      queryClient.invalidateQueries({ queryKey: ['rankings', activeFormat] });
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
  // Tap a row's rank number → that row enters edit mode. RankEditRow owns
  // the draft string internally; commitRankEdit receives the committed value
  // so renderItem's useCallback no longer depends on `editValue`.
  const [editingPid, setEditingPid] = useState<string | null>(null);

  const commitRankEdit = useCallback((val: string) => {
    if (!editingPid) return;
    const target = parseInt(val, 10);
    setEditingPid(null);
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
  }, [editingPid, filter, scheduleSave]);

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
            pressed && !isActive && { backgroundColor: ink.ink3 },
          ]}
        >
          {isEditing ? (
            <RankEditRow
              initialValue={String(rankNum)}
              onCommit={commitRankEdit}
            />
          ) : (
            <Pressable
              onPress={() => {
                setEditingPid(item.id);
                haptics.selection();
              }}
              hitSlop={{ top: 13, bottom: 13, left: 8, right: 8 }}
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
          <View style={styles.grip} importantForAccessibility="no-hide-descendants">
            <View style={styles.gripBar} />
            <View style={styles.gripBar} />
          </View>
        </Pressable>
      );
    },
    [commitRankEdit, editingPid],
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
        <Text style={styles.title}>Overall Ranks</Text>
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
                Keyboard.dismiss();
                setFilter(f);
              }}
              style={({ pressed }) => [
                styles.filterSeg,
                active && styles.filterSegActive,
                active && { borderBottomColor: FILTER_UNDERLINE[f] },
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
      ) : ranksQuery.isError ? (
        <View style={styles.center}>
          <Text style={styles.errorText}>Could not load rankings.</Text>
          <Button
            variant="secondary"
            compact
            label="Try again"
            onPress={() => ranksQuery.refetch()}
          />
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
        <ActivityIndicator size="small" color={chalk.dim} />
        <Text style={styles.saveIndicatorText}>saving…</Text>
      </View>
    );
  }
  if (status === 'saved') {
    return (
      <View style={styles.saveIndicatorWrap}>
        <Icon name="check" size={14} color={semantic.pos} />
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
  safe: { flex: 1, backgroundColor: ink.ink0 },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
  },
  title: { ...type.heading },

  // Save status indicator — three visual variants.
  saveIndicatorWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    paddingHorizontal: space.sm,
    paddingVertical: space.xs,
  },
  saveIndicatorText: { ...type.label },
  savedText: { ...type.label, color: semantic.pos },
  errorPill: {
    borderColor: semantic.neg,
    borderWidth: 1,
    borderRadius: radii.xs,
  },
  errorPillText: {
    ...type.label,
    color: semantic.neg,
    maxWidth: 180,
  },

  hint: {
    ...type.bodySm,
    textAlign: 'center',
    paddingHorizontal: space.lg,
    paddingBottom: space.sm,
  },

  // PositionTabs — segmented row (docs/design/components.md → Navigation).
  filterRow: {
    flexDirection: 'row',
    marginHorizontal: space.lg,
    marginBottom: space.sm,
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
  filterSegActive: {
    backgroundColor: ink.ink3,
  },
  filterText: { ...type.label },
  filterTextActive: { color: chalk.base },

  listContainer: { flex: 1 },
  listContent: { paddingHorizontal: space.lg, paddingBottom: space.xxl },

  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.md,
    paddingHorizontal: space.xs,
  },
  rowActive: {
    backgroundColor: ink.ink2,
    borderRadius: radii.sm,
  },
  sep: { height: 1, backgroundColor: ink.line },

  rankNumWrap: { width: 36, alignItems: 'center' },
  rankNum: {
    ...type.data,
    color: chalk.dim,
    textAlign: 'center',
  },
  rankInput: {
    ...type.data,
    width: 48,
    height: 44,
    textAlign: 'center',
    backgroundColor: ink.ink2,
    borderColor: ice.base,
    borderWidth: 1,
    borderRadius: radii.sm,
    paddingVertical: 4,
  },

  name: { ...type.title },
  meta: { ...type.bodySm, marginTop: 2 },
  eloWrap: { alignItems: 'flex-end', minWidth: 56 },
  eloNum: { ...type.data },
  eloLabel: { ...type.label, fontSize: 10, lineHeight: 12, letterSpacing: 0.8 },

  // Drag affordance — decorative lineStrong grip bars (no emoji, no icon glyph).
  grip: { gap: 3 },
  gripBar: { width: 14, height: 2, backgroundColor: ink.lineStrong },

  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.md, padding: space.xl },
  errorText: { ...type.body, color: semantic.neg },
  emptyTitle: { ...type.heading },
  emptyBody: { ...type.bodySm, textAlign: 'center' },
});
