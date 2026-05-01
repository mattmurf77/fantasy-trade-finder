import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  ScrollView,
  LayoutChangeEvent,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  runOnJS,
} from 'react-native-reanimated';
import { haptics } from '../utils/haptics';
import { startSpan } from '../observability/sentry';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import PlayerCard from '../components/PlayerCard';
import TierBin from '../components/TierBin';
import Toast from '../components/Toast';
import {
  getRankings,
  saveTiers,
  getTiersStatus,
  dismissPlayer,
} from '../api/rankings';
import { autoBucket, TIERS } from '../utils/tierBands';
import type { Position, RankedPlayer, Tier, ScoringFormat } from '../shared/types';

const POSITIONS: Position[] = ['QB', 'RB', 'WR', 'TE'];

/** Which zone a card's center falls into at drag-end.  "unassigned" is
 *  a first-class zone — you can drag a player out of a tier back to the pool. */
type Zone = Tier | 'unassigned';

interface BinLayout {
  zone: Zone;
  // Absolute-to-screen Y bounds; we key drop zones on vertical overlap
  // only (the screen is single-column within the ScrollView).
  y: number;
  height: number;
}

export default function TiersScreen() {
  const queryClient = useQueryClient();
  const [position, setPosition] = useState<Position>('QB');
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);

  // tiers[position] = { elite: [player...], starter: [...], ..., unassigned: [...] }
  const [buckets, setBuckets] = useState<Record<Zone, RankedPlayer[]>>(() => emptyBuckets());

  // Players the user has dragged OUT of any tier (back to the pool) since
  // the last save. We pass these to /api/tiers/save as `cleared_pids` so
  // the backend deletes the corresponding tier_overrides rows; without
  // this the chip would reappear on next reload (the round-trip data-
  // loss bug PR #25 fixed for web). Reset to empty after a save lands
  // and on every position switch (the saved snapshot is per-position).
  const [clearedPids, setClearedPids] = useState<Set<string>>(() => new Set());

  // ── Multi-select state ──────────────────────────────────────────────
  // When `multiSelect` is on, taps on chips toggle selection (drag is
  // suppressed). The footer action bar shows when the set is non-empty
  // and lets the user move every selected chip up or down by exactly
  // one tier in a single action. Mirrors web's PR #23 with a touch-
  // friendly interaction model.
  const [multiSelect, setMultiSelect] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const exitMultiSelect = useCallback(() => {
    setMultiSelect(false);
    setSelectedIds(new Set());
  }, []);
  const toggleSelected = useCallback((pid: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(pid)) next.delete(pid);
      else next.add(pid);
      return next;
    });
    haptics.selection();
  }, []);

  // ── Data ────────────────────────────────────────────────────────────
  const rankingsQuery = useQuery({
    queryKey: ['rankings', position],
    queryFn: () => getRankings(position),
    staleTime: 30_000,
  });

  const tiersStatusQuery = useQuery({
    queryKey: ['tiers-status'],
    queryFn: getTiersStatus,
    staleTime: 60_000,
  });

  const saveMutation = useMutation({
    // Wrap the tier save in a Sentry span — measures end-to-end latency
    // including the per-position payload build + the network round-trip.
    // No-op when Sentry isn't initialized.
    mutationFn: () =>
      startSpan({ name: 'tiers.save', op: 'mutation' }, () => {
        // Only send the 5 real tiers — `unassigned` isn't a real tier on the server.
        const payload: Record<string, string[]> = {};
        for (const t of TIERS) payload[t] = buckets[t].map((p) => p.id);
        // Pass the accumulated clearedPids so the backend can DELETE the
        // matching tier_overrides rows for this position. Filter out any
        // ID that's currently sitting in a tier (defensive — the user
        // may have dragged-out then dragged-back-in within the same
        // session); we never want a re-saved tier assignment to be
        // simultaneously cleared.
        const stillAssigned = new Set<string>();
        for (const t of TIERS) for (const p of buckets[t]) stillAssigned.add(p.id);
        const cleared = Array.from(clearedPids).filter((id) => !stillAssigned.has(id));
        return saveTiers(position, payload, cleared);
      }),
    onSuccess: () => {
      setToast({ msg: '✓ Tiers saved', tone: 'success' });
      queryClient.invalidateQueries({ queryKey: ['tiers-status'] });
      queryClient.invalidateQueries({ queryKey: ['progress'] });
      // Reset the clearedPids set — the backend just absorbed them.
      setClearedPids(new Set());
    },
    onError: (e: Error) => {
      setToast({ msg: e.message || 'Save failed', tone: 'warn' });
    },
  });

  const dismissMutation = useMutation({
    mutationFn: (pid: string) => dismissPlayer(pid),
    onMutate: (pid) => {
      // Optimistic: pull the player out of every bucket immediately
      setBuckets((prev) => {
        const next = cloneBuckets(prev);
        for (const z of ALL_ZONES) next[z] = next[z].filter((p) => p.id !== pid);
        return next;
      });
    },
    onSuccess: () => {
      setToast({ msg: 'Player hidden from your pool', tone: 'success' });
    },
  });

  // Re-auto-bucket whenever the rankings response changes OR position switches.
  useEffect(() => {
    const data = rankingsQuery.data;
    if (!data?.rankings) return;

    // Players come back with per-position ELO + rank. The data shape is
    // any[] per api/rankings.ts so cast each row into RankedPlayer.
    const players = (data.rankings as RankedPlayer[]).slice().sort(
      (a, b) => (b.elo ?? 0) - (a.elo ?? 0),
    );

    // Best-effort scoring_format resolution. TiersStatus returns it;
    // otherwise fall back to 1qb_ppr (the default on the server).
    const fmt: ScoringFormat =
      (tiersStatusQuery.data?.scoring_format as ScoringFormat) || '1qb_ppr';

    const bucketed = autoBucket(players, position, fmt);
    setBuckets({ ...bucketed, unassigned: [] });
    // The clearedPids set is per-position (the saved snapshot is too).
    // Position switch or rankings-refetch invalidates the previous
    // position's pending clears.
    setClearedPids(new Set());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rankingsQuery.data, position, tiersStatusQuery.data?.scoring_format]);

  // ── Drag-drop infrastructure ───────────────────────────────────────
  // Bin layouts are captured via onLayout into this ref. We compare the
  // drag's finalY against every known layout and pick the first match.
  const binLayouts = useRef<BinLayout[]>([]);
  // Per-chip layouts (y + height), keyed by playerId. Captured via the
  // chip's onLayout so we can resolve a drop position to an insertion
  // index inside the destination bin (within-tier reordering, not just
  // tier-to-tier moves).
  const chipLayouts = useRef<Map<string, { y: number; height: number }>>(new Map());

  const setBinLayout = useCallback((zone: Zone, e: LayoutChangeEvent) => {
    const { y, height } = e.nativeEvent.layout;
    const existing = binLayouts.current.findIndex((b) => b.zone === zone);
    const entry: BinLayout = { zone, y, height };
    if (existing >= 0) binLayouts.current[existing] = entry;
    else binLayouts.current.push(entry);
  }, []);

  const setChipLayout = useCallback((pid: string, e: LayoutChangeEvent) => {
    const { y, height } = e.nativeEvent.layout;
    chipLayouts.current.set(pid, { y, height });
  }, []);

  const zoneAt = useCallback((absoluteY: number): Zone | null => {
    for (const b of binLayouts.current) {
      if (absoluteY >= b.y && absoluteY <= b.y + b.height) return b.zone;
    }
    return null;
  }, []);

  // Resolve a drop position (in screen Y) to {zone, insertIdx}. Excludes
  // the dragged chip from the insertion-index walk so the math is in
  // POST-removal coordinates — same convention as web's
  // assignToTierAt. Returns null if the cursor isn't over any zone.
  const dropTargetAt = useCallback(
    (absoluteY: number, draggedPid: string): { zone: Zone; insertIdx: number } | null => {
      const zone = zoneAt(absoluteY);
      if (!zone) return null;
      // For 'unassigned' (the pool) order doesn't drive any backend
      // semantic; insert at end.
      if (zone === 'unassigned') {
        return { zone, insertIdx: 0 };
      }
      // Walk the bin's chips in array order. First chip whose vertical
      // midpoint is BELOW the cursor → that's the insert index. Drag
      // source is excluded so the index is correct after we splice it
      // out of its original location.
      const ordered = buckets[zone] || [];
      let insertIdx = 0;
      let visible = 0;
      for (const p of ordered) {
        if (p.id === draggedPid) continue;
        const layout = chipLayouts.current.get(p.id);
        if (!layout) {
          // Layout not yet measured — assume below cursor so the index
          // keeps growing. Safer than skipping which would produce a
          // too-low index on first drop after a re-render.
          insertIdx = visible + 1;
          visible += 1;
          continue;
        }
        if (absoluteY < layout.y + layout.height / 2) {
          // Cursor is above this chip's midpoint → insert before it.
          return { zone, insertIdx: visible };
        }
        visible += 1;
        insertIdx = visible;
      }
      return { zone, insertIdx };
    },
    [buckets, zoneAt],
  );

  // Move a player into the given zone at a specific 0-based array index.
  // `insertIdx` is interpreted in POST-removal coordinates (consistent
  // with dropTargetAt above) — so we splice out FIRST and then splice in
  // at exactly insertIdx with no further bookkeeping. When insertIdx is
  // undefined, falls back to "append at end" for legacy call sites.
  //
  // Same-tier no-op detection: if the player already sits at the
  // requested index in the requested zone, skip the splice round-trip
  // entirely (avoids triggering an unnecessary save).
  const movePlayer = useCallback(
    (playerId: string, toZone: Zone, insertIdx?: number) => {
      let didMove = false;
      setBuckets((prev) => {
        const next = cloneBuckets(prev);
        let moved: RankedPlayer | null = null;
        let fromZone: Zone | null = null;
        let fromIdx = -1;
        for (const z of ALL_ZONES) {
          const idx = next[z].findIndex((p) => p.id === playerId);
          if (idx >= 0) {
            fromZone = z;
            fromIdx  = idx;
            [moved]  = next[z].splice(idx, 1);
            break;
          }
        }
        if (!moved) return prev;

        // Resolve target index: undefined → end. Clamp to current length
        // (post-removal). For same-zone no-op: if fromIdx === target idx
        // in post-removal coords, restore and bail.
        let targetIdx =
          typeof insertIdx === 'number'
            ? Math.max(0, Math.min(insertIdx, next[toZone].length))
            : next[toZone].length;
        if (fromZone === toZone && fromIdx === targetIdx) {
          // Restore to original position; nothing changed.
          next[fromZone].splice(fromIdx, 0, moved);
          return prev;
        }
        next[toZone].splice(targetIdx, 0, moved);
        didMove = true;
        return next;
      });
      if (!didMove) return;

      // Track tier-out moves so the next save can DELETE the backend
      // override. If the user drags BACK into a tier later, the save
      // filter (`stillAssigned`) drops the id from the cleared list so
      // we don't double-message the backend.
      if (toZone === 'unassigned') {
        setClearedPids((prev) => {
          const next = new Set(prev);
          next.add(playerId);
          return next;
        });
      } else {
        setClearedPids((prev) => {
          if (!prev.has(playerId)) return prev;     // skip identity churn
          const next = new Set(prev);
          next.delete(playerId);
          return next;
        });
      }
      haptics.success();
    },
    [],
  );

  // ── Bulk move (multi-select) ────────────────────────────────────────
  // Move every currently-selected chip by exactly ONE tier in `direction`.
  // Order-preserving: chips in the same source tier keep their relative
  // order at the destination's end. Chips already at the boundary stay
  // (top of `elite` for 'up', bottom of `bench` for 'down') — matches
  // web's clamp behavior.
  const bulkMove = useCallback(
    (direction: 'up' | 'down') => {
      if (selectedIds.size === 0) return;
      const TIER_LIST: Tier[] = [...TIERS];
      setBuckets((prev) => {
        const next = cloneBuckets(prev);
        // Group selected by source tier so we can preserve within-tier
        // relative order across the move.
        const grouped: Record<string, RankedPlayer[]> = {};
        for (const t of TIERS) {
          for (const p of next[t]) {
            if (selectedIds.has(p.id)) {
              (grouped[t] ||= []).push(p);
            }
          }
        }
        for (const sourceTier of Object.keys(grouped)) {
          const players = grouped[sourceTier];
          const srcIdx = TIER_LIST.indexOf(sourceTier as Tier);
          const dstIdx =
            direction === 'up'
              ? Math.max(0, srcIdx - 1)
              : Math.min(TIER_LIST.length - 1, srcIdx + 1);
          if (dstIdx === srcIdx) continue;          // already at boundary
          const dst = TIER_LIST[dstIdx];
          // Pull each player from source, append to destination in
          // their original within-tier order.
          for (const p of players) {
            const i = next[sourceTier as Tier].findIndex((x) => x.id === p.id);
            if (i >= 0) next[sourceTier as Tier].splice(i, 1);
            next[dst].push(p);
          }
        }
        return next;
      });
      // No clearedPids change — bulk moves keep all selected players in
      // some tier (boundary chips stay put).
      haptics.success();
    },
    [selectedIds],
  );

  // ── Render helpers ─────────────────────────────────────────────────
  const saving = saveMutation.isPending;
  const loading = rankingsQuery.isLoading || rankingsQuery.isFetching;

  function renderPlayerCard(p: RankedPlayer) {
    return (
      <DraggableRow
        key={p.id}
        player={p}
        dropTargetAt={dropTargetAt}
        onLayout={setChipLayout}
        onDrop={(target) => {
          if (!target) return;
          movePlayer(p.id, target.zone, target.insertIdx);
        }}
        onLongPress={
          // In multi-select mode, long-press dismiss is too easy to
          // misfire; suppress so the only chip-level action is tap-to-
          // toggle.
          multiSelect
            ? undefined
            : () => {
                haptics.warning();
                dismissMutation.mutate(p.id);
              }
        }
        selectionMode={multiSelect}
        isSelected={selectedIds.has(p.id)}
        onTapInSelection={() => toggleSelected(p.id)}
      />
    );
  }

  // ── Render ──────────────────────────────────────────────────────────
  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />

      <View style={styles.headerRow}>
        <Text style={styles.title}>Positional Tiers</Text>
        <View style={styles.headerActions}>
          {/* Multi-select toggle. While ON, chip tap toggles selection
              (drag is suppressed); tapping again here cancels and clears
              the set. The bottom action bar handles the actual moves. */}
          <Pressable
            onPress={() => {
              if (multiSelect) exitMultiSelect();
              else { setMultiSelect(true); haptics.selection(); }
            }}
            style={({ pressed }) => [
              styles.selectBtn,
              multiSelect && styles.selectBtnActive,
              pressed && { opacity: 0.6 },
            ]}
          >
            <Text style={[styles.selectBtnText, multiSelect && styles.selectBtnTextActive]}>
              {multiSelect ? 'Cancel' : 'Select'}
            </Text>
          </Pressable>
          <Pressable
            onPress={() => {
              // Reset = re-auto-bucket from current rankings
              const data = rankingsQuery.data;
              if (!data?.rankings) return;
              const players = (data.rankings as RankedPlayer[]).slice().sort(
                (a, b) => (b.elo ?? 0) - (a.elo ?? 0),
              );
              const fmt: ScoringFormat =
                (tiersStatusQuery.data?.scoring_format as ScoringFormat) || '1qb_ppr';
              const bucketed = autoBucket(players, position, fmt);
              setBuckets({ ...bucketed, unassigned: [] });
              haptics.selection();
            }}
            style={({ pressed }) => [styles.resetBtn, pressed && { opacity: 0.6 }]}
          >
            <Text style={styles.resetBtnText}>Reset</Text>
          </Pressable>
        </View>
      </View>

      {/* Position switcher */}
      <View style={styles.switcher}>
        {POSITIONS.map((p) => {
          const isActive = p === position;
          return (
            <Pressable
              key={p}
              onPress={() => {
                if (p !== position) setPosition(p);
              }}
              style={({ pressed }) => [
                styles.switcherBtn,
                isActive && styles.switcherBtnActive,
                pressed && { opacity: 0.7 },
              ]}
            >
              <Text
                style={[styles.switcherText, isActive && styles.switcherTextActive]}
              >
                {p}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <Text style={styles.hint}>
        {multiSelect
          ? 'Tap chips to select. Use the bar below to move all selected up or down.'
          : 'Long-press + drag a card to move it. Tap "Select" to bulk-move multiple at once.'}
      </Text>

      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator color={colors.accent} />
        </View>
      ) : rankingsQuery.isError ? (
        <View style={styles.centered}>
          <Text style={styles.errorText}>Could not load rankings.</Text>
          <Pressable onPress={() => rankingsQuery.refetch()}>
            <Text style={styles.retryText}>Try again</Text>
          </Pressable>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
        >
          {/* Unassigned pool up top */}
          <TierBin
            tier="unassigned"
            count={buckets.unassigned.length}
            onLayout={(e) => setBinLayout('unassigned', e)}
          >
            {buckets.unassigned.length === 0 ? (
              <Text style={styles.emptyBin}>Every player is in a tier.</Text>
            ) : (
              buckets.unassigned.map(renderPlayerCard)
            )}
          </TierBin>

          {/* The five tier bins */}
          {TIERS.map((t) => (
            <TierBin
              key={t}
              tier={t}
              count={buckets[t].length}
              onLayout={(e) => setBinLayout(t, e)}
            >
              {buckets[t].length === 0 ? (
                <Text style={styles.emptyBin}>Drag players here</Text>
              ) : (
                buckets[t].map(renderPlayerCard)
              )}
            </TierBin>
          ))}
        </ScrollView>
      )}

      {/* Multi-select action bar — only shown in select mode with at
          least one chip selected. Sits above the save bar so the user
          can still commit after a bulk move without leaving select
          mode. "Done" exits select mode without canceling the moves. */}
      {multiSelect && selectedIds.size > 0 ? (
        <View style={styles.actionBar}>
          <Text style={styles.actionBarCount}>
            {selectedIds.size} selected
          </Text>
          <View style={styles.actionBarBtns}>
            <Pressable
              onPress={() => bulkMove('up')}
              style={({ pressed }) => [styles.actionBarBtn, pressed && { opacity: 0.7 }]}
            >
              <Text style={styles.actionBarBtnText}>↑ Up tier</Text>
            </Pressable>
            <Pressable
              onPress={() => bulkMove('down')}
              style={({ pressed }) => [styles.actionBarBtn, pressed && { opacity: 0.7 }]}
            >
              <Text style={styles.actionBarBtnText}>↓ Down tier</Text>
            </Pressable>
            <Pressable
              onPress={exitMultiSelect}
              style={({ pressed }) => [styles.actionBarBtnDone, pressed && { opacity: 0.7 }]}
            >
              <Text style={styles.actionBarBtnDoneText}>Done</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      {/* Save button pinned to the bottom */}
      <View style={styles.saveBar}>
        <Pressable
          disabled={saving || loading}
          onPress={() => saveMutation.mutate()}
          style={({ pressed }) => [
            styles.saveBtn,
            pressed && { opacity: 0.85 },
            (saving || loading) && { opacity: 0.5 },
          ]}
        >
          {saving ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.saveBtnText}>Save {position} tiers</Text>
          )}
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

// ── DraggableRow — encapsulates the per-card gesture + Reanimated style.
//
// dropTargetAt: parent-supplied resolver that turns a screen-Y coordinate
//   into {zone, insertIdx}. The chip's gesture calls it on release. The
//   resolver excludes the dragged chip from its index walk so the
//   returned insertIdx is in POST-removal coordinates — caller can splice
//   directly without further adjustment.
//
// onLayout: parent hook that captures this chip's position so the
//   resolver can do per-chip insertion-index math. We call it on every
//   onLayout fire (cheap) so re-renders after a move stay in sync.
//
// selectionMode + isSelected + onTapInSelection: when multi-select is
// active on the parent, the gesture switches from long-press-drag to
// tap-toggle. We render an accent border + a checkmark to signal
// selected state. Drag is suppressed entirely in selection mode so a
// tap can't accidentally start a pan.
interface DraggableRowProps {
  player: RankedPlayer;
  dropTargetAt: (absoluteY: number, draggedPid: string) => { zone: Zone; insertIdx: number } | null;
  onLayout: (pid: string, e: LayoutChangeEvent) => void;
  onDrop: (target: { zone: Zone; insertIdx: number } | null) => void;
  onLongPress?: () => void;
  selectionMode?: boolean;
  isSelected?: boolean;
  onTapInSelection?: () => void;
}

function DraggableRow({
  player,
  dropTargetAt,
  onLayout,
  onDrop,
  onLongPress,
  selectionMode = false,
  isSelected = false,
  onTapInSelection,
}: DraggableRowProps) {
  const translateX = useSharedValue(0);
  const translateY = useSharedValue(0);
  const scale = useSharedValue(1);
  const zIndex = useSharedValue(0);

  // Pan activates after 220ms hold to avoid fighting ScrollView scrolling.
  const pan = useMemo(
    () =>
      Gesture.Pan()
        .activateAfterLongPress(220)
        .onStart(() => {
          scale.value = withTiming(1.04, { duration: 120 });
          zIndex.value = 10;
          runOnJS(haptics.pickup)();
        })
        .onUpdate((e) => {
          translateX.value = e.translationX;
          translateY.value = e.translationY;
        })
        .onEnd((e) => {
          const absoluteY = e.absoluteY;
          const target = dropTargetAt(absoluteY, player.id);
          // Snap back visually, then commit the move so the card re-renders
          // in its new bin.
          translateX.value = withTiming(0, { duration: 160 });
          translateY.value = withTiming(0, { duration: 160 });
          scale.value = withTiming(1, { duration: 160 });
          zIndex.value = 0;
          runOnJS(onDrop)(target);
        }),
    [dropTargetAt, onDrop, player.id, translateX, translateY, scale, zIndex],
  );

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: translateX.value },
      { translateY: translateY.value },
      { scale: scale.value },
    ],
    zIndex: zIndex.value,
  }));

  // In selection mode the entire chip becomes a tap-toggle Pressable.
  // We deliberately bypass the gesture detector so the long-press
  // gating doesn't silently swallow a tap (Pressable's onPress fires
  // immediately).
  if (selectionMode) {
    return (
      <Pressable
        onPress={onTapInSelection}
        onLayout={(e) => onLayout(player.id, e)}
        style={({ pressed }) => [
          isSelected && styles.chipSelected,
          pressed && { opacity: 0.85 },
        ]}
      >
        <PlayerCard player={player} compact rightSlot={isSelected ? <Text style={styles.chipCheck}>✓</Text> : undefined} />
      </Pressable>
    );
  }

  return (
    <GestureDetector gesture={pan}>
      <Animated.View
        style={animatedStyle}
        onLayout={(e) => onLayout(player.id, e)}
      >
        <PlayerCard player={player} compact onLongPress={onLongPress} />
      </Animated.View>
    </GestureDetector>
  );
}

// ── Helpers ─────────────────────────────────────────────────────────

const ALL_ZONES: Zone[] = ['unassigned', 'elite', 'starter', 'solid', 'depth', 'bench'];

function emptyBuckets(): Record<Zone, RankedPlayer[]> {
  return {
    unassigned: [],
    elite: [],
    starter: [],
    solid: [],
    depth: [],
    bench: [],
  };
}

function cloneBuckets(src: Record<Zone, RankedPlayer[]>): Record<Zone, RankedPlayer[]> {
  return {
    unassigned: [...src.unassigned],
    elite: [...src.elite],
    starter: [...src.starter],
    solid: [...src.solid],
    depth: [...src.depth],
    bench: [...src.bench],
  };
}

// ── Styles ──────────────────────────────────────────────────────────
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
  headerActions: {
    flexDirection: 'row',
    gap: spacing.xs,
  },
  resetBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  resetBtnText: { color: colors.muted, fontSize: fontSize.xs, fontWeight: '700' },
  selectBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  selectBtnActive: {
    borderColor: colors.accent,
    backgroundColor: 'rgba(79,124,255,0.10)',
  },
  selectBtnText: { color: colors.muted, fontSize: fontSize.xs, fontWeight: '700' },
  selectBtnTextActive: { color: colors.accent },
  // Selected-chip state (multi-select mode). Subtle accent ring; the
  // checkmark on the right of the chip carries the explicit signal.
  chipSelected: {
    borderRadius: radius.md,
    backgroundColor: 'rgba(79,124,255,0.10)',
    borderWidth: 1,
    borderColor: colors.accent,
  },
  chipCheck: {
    color: colors.accent,
    fontSize: fontSize.lg,
    fontWeight: '800',
  },
  // Floating action bar — shown above the save bar when 2+ chips are
  // selected. Up / Down move all selected by one tier; Done exits.
  actionBar: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 76,                       // sits just above the save bar
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.surface,
    borderTopColor: colors.border,
    borderTopWidth: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  actionBarCount: {
    color: colors.text,
    fontSize: fontSize.sm,
    fontWeight: '700',
  },
  actionBarBtns: {
    flexDirection: 'row',
    gap: spacing.xs,
  },
  actionBarBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: 'rgba(79,124,255,0.45)',
    backgroundColor: 'rgba(79,124,255,0.10)',
  },
  actionBarBtnText: {
    color: colors.accent,
    fontSize: fontSize.xs,
    fontWeight: '800',
  },
  actionBarBtnDone: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  actionBarBtnDoneText: {
    color: colors.muted,
    fontSize: fontSize.xs,
    fontWeight: '700',
  },
  switcher: {
    flexDirection: 'row',
    gap: spacing.xs,
    marginHorizontal: spacing.lg,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: 4,
  },
  switcherBtn: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: spacing.xs + 2,
    borderRadius: radius.sm,
  },
  switcherBtnActive: { backgroundColor: 'rgba(79,124,255,0.14)' },
  switcherText: { color: colors.muted, fontSize: fontSize.sm, fontWeight: '700' },
  switcherTextActive: { color: colors.accent },
  hint: {
    color: colors.muted,
    fontSize: fontSize.xs,
    textAlign: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
  },
  errorText: { color: colors.red, fontSize: fontSize.sm },
  retryText: { color: colors.accent, fontSize: fontSize.sm, fontWeight: '700' },
  scroll: {
    padding: spacing.lg,
    paddingBottom: 96, // room for the Save bar
  },
  emptyBin: {
    color: colors.muted,
    fontSize: fontSize.xs,
    textAlign: 'center',
    paddingVertical: spacing.xs,
    fontStyle: 'italic',
  },
  saveBar: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    padding: spacing.md,
    backgroundColor: colors.bg,
    borderTopColor: colors.border,
    borderTopWidth: 1,
  },
  saveBtn: {
    backgroundColor: colors.accent,
    borderRadius: radius.md,
    paddingVertical: 14,
    alignItems: 'center',
  },
  saveBtnText: { color: '#fff', fontSize: fontSize.base, fontWeight: '800' },
});
