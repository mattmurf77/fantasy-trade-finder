import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  ScrollView,
  LayoutChangeEvent,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  useDerivedValue,
  withTiming,
  runOnJS,
  SharedValue,
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
import { copyTiersFromFormat } from '../api/league';
import { autoBucket, TIERS } from '../utils/tierBands';
import type { Position, RankedPlayer, Tier, ScoringFormat } from '../shared/types';

// Format-key → human label for the copy button + confirm dialog. Mirrors
// web/positional-tiers.html's FORMAT_LABELS.
const FORMAT_LABELS: Record<ScoringFormat, string> = {
  '1qb_ppr': '🏈 1QB PPR',
  sf_tep:    '🏟 SF TEP',
};
const FORMAT_KEYS: ScoringFormat[] = ['1qb_ppr', 'sf_tep'];

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
    placeholderData: (prev) => prev,
  });

  const tiersStatusQuery = useQuery({
    queryKey: ['tiers-status'],
    queryFn: getTiersStatus,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
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

  // ── Copy tiers from the OTHER scoring format ───────────────────────
  // Pulls the user's tier assignments from the other format (e.g. SF TEP
  // when currently on 1QB PPR) and re-stamps them onto the active format
  // with format-appropriate ELOs. Destructive: replaces existing target-
  // format tier overrides wholesale, so we confirm via Alert first. On
  // success we refetch the per-position rankings + tier-status caches so
  // the screen re-renders with the new state.
  const copyMutation = useMutation({
    mutationFn: ({ from, to }: { from: ScoringFormat; to: ScoringFormat }) =>
      copyTiersFromFormat(from, to),
    onSuccess: (data) => {
      if (!data?.ok) {
        setToast({ msg: data?.error || 'Copy failed', tone: 'warn' });
        return;
      }
      const n = data.total ?? 0;
      setToast({ msg: `✓ Copied ${n} tier placements`, tone: 'success' });
      // Invalidate rankings/tier caches so the per-position load picks up
      // the new override ELOs. Same pattern as saveMutation.onSuccess.
      queryClient.invalidateQueries({ queryKey: ['rankings'] });
      queryClient.invalidateQueries({ queryKey: ['tiers-status'] });
      queryClient.invalidateQueries({ queryKey: ['progress'] });
      // Reset clearedPids — the cleared set is per-position-load and
      // we're about to reload anyway.
      setClearedPids(new Set());
    },
    onError: (e: Error) => {
      setToast({ msg: e.message || 'Copy failed', tone: 'warn' });
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
  // Live drop-preview shared values (issue #14). Updated each gesture
  // tick via runOnJS so non-dragged chips can react in their animated
  // styles without forcing a React re-render. Empty-string sentinel
  // means "no drag in flight" → all chips render with translateY = 0.
  //
  //   proposedZoneSV       — destination zone the dragged chip would
  //                          land in given current finger Y (or '').
  //   proposedInsertIdxSV  — post-removal insertion index in that zone.
  //   draggedPidSV         — id of the chip currently being dragged.
  //   draggedSrcZoneSV     — source zone the dragged chip came from.
  //   draggedSrcIdxSV      — source pre-removal array index.
  //
  // The "post-removal index" model is the same one dropTargetAt uses
  // (see comments on dropTargetAt below); the gap-shift worklet on each
  // chip translates the chip's pre-removal index into post-removal
  // coordinates before comparing against proposedInsertIdxSV.
  const proposedZoneSV = useSharedValue<string>('');
  const proposedInsertIdxSV = useSharedValue<number>(-1);
  const draggedPidSV = useSharedValue<string>('');
  const draggedSrcZoneSV = useSharedValue<string>('');
  const draggedSrcIdxSV = useSharedValue<number>(-1);

  // Bin + chip layouts live in screen-Y coordinates so they're directly
  // comparable to gesture `e.absoluteY` (which is also screen-Y). We
  // CANNOT use `nativeEvent.layout.y` directly: that's relative to the
  // immediate parent (the ScrollView's content view) and is off from
  // the gesture coords by the screen offset of the ScrollView. Pre-fix
  // this caused drops to land one or two tiers below the user's target
  // (TestFlight feedback #23). measureInWindow gives us screen-Y.
  const binLayouts = useRef<BinLayout[]>([]);
  const chipLayouts = useRef<Map<string, { y: number; height: number }>>(new Map());

  // Refs to each bin's outer <View> so we can measureInWindow on layout.
  // TierBin is already a forwardRef. Per-zone setter callbacks are memo'd
  // so React doesn't see a new prop identity each render.
  const binRefs = useRef<Partial<Record<Zone, View | null>>>({});
  const binRefSetters = useMemo(() => {
    const setters: Partial<Record<Zone, (node: View | null) => void>> = {};
    for (const z of ALL_ZONES) {
      setters[z] = (node: View | null) => { binRefs.current[z] = node; };
    }
    return setters as Record<Zone, (node: View | null) => void>;
  }, []);

  // Bin onLayout: re-measure in screen coords. measureInWindow is async
  // but onLayout fires before any user interaction is possible, so the
  // cache is warm by the first drag.
  const setBinLayout = useCallback((zone: Zone, _e: LayoutChangeEvent) => {
    const node = binRefs.current[zone];
    if (!node) return;
    node.measureInWindow((_x, y, _w, height) => {
      const existing = binLayouts.current.findIndex((b) => b.zone === zone);
      const entry: BinLayout = { zone, y, height };
      if (existing >= 0) binLayouts.current[existing] = entry;
      else binLayouts.current.push(entry);
    });
  }, []);

  // Chip onLayout: DraggableRow does its own measureInWindow against
  // its outer Animated.View ref and hands us screen-Y + height directly.
  const setChipLayout = useCallback((pid: string, screenY: number, height: number) => {
    chipLayouts.current.set(pid, { y: screenY, height });
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

  // Drag-preview helpers (issue #14). Called via runOnJS from gesture
  // worklets — JS-thread only because they read buckets/chipLayouts.
  // beginDragPreview captures the dragged chip's source location once
  // at .onStart; updateDragPreview resolves drop target on each tick
  // and writes it to shared values; endDragPreview resets on release.
  const beginDragPreview = useCallback(
    (pid: string) => {
      for (const z of ALL_ZONES) {
        const idx = buckets[z].findIndex((p) => p.id === pid);
        if (idx >= 0) {
          draggedPidSV.value = pid;
          draggedSrcZoneSV.value = z;
          draggedSrcIdxSV.value = idx;
          return;
        }
      }
    },
    [buckets, draggedPidSV, draggedSrcZoneSV, draggedSrcIdxSV],
  );

  const updateDragPreview = useCallback(
    (absoluteY: number, pid: string) => {
      const t = dropTargetAt(absoluteY, pid);
      if (!t) {
        proposedZoneSV.value = '';
        proposedInsertIdxSV.value = -1;
        return;
      }
      proposedZoneSV.value = t.zone;
      proposedInsertIdxSV.value = t.insertIdx;
    },
    [dropTargetAt, proposedZoneSV, proposedInsertIdxSV],
  );

  const endDragPreview = useCallback(() => {
    proposedZoneSV.value = '';
    proposedInsertIdxSV.value = -1;
    draggedPidSV.value = '';
    draggedSrcZoneSV.value = '';
    draggedSrcIdxSV.value = -1;
  }, [proposedZoneSV, proposedInsertIdxSV, draggedPidSV, draggedSrcZoneSV, draggedSrcIdxSV]);

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

  function renderPlayerCard(p: RankedPlayer, binZone: Zone, binIndex: number) {
    return (
      <DraggableRow
        key={p.id}
        player={p}
        binZone={binZone}
        binIndex={binIndex}
        proposedZoneSV={proposedZoneSV}
        proposedInsertIdxSV={proposedInsertIdxSV}
        draggedPidSV={draggedPidSV}
        draggedSrcZoneSV={draggedSrcZoneSV}
        draggedSrcIdxSV={draggedSrcIdxSV}
        onDragStart={beginDragPreview}
        onDragUpdate={updateDragPreview}
        onDragEnd={endDragPreview}
        onLayout={setChipLayout}
        onDropAt={(absoluteY, pid) => {
          const target = dropTargetAt(absoluteY, pid);
          if (!target) return;
          movePlayer(pid, target.zone, target.insertIdx);
        }}
        onLongPressDismiss={
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
        onEnterMultiSelect={() => {
          setMultiSelect(true);
          setSelectedIds(new Set([p.id]));
          haptics.selection();
        }}
        selectionMode={multiSelect}
        isSelected={selectedIds.has(p.id)}
        onTapInSelection={() => toggleSelected(p.id)}
      />
    );
  }

  // ── Copy-from-format button derivation ─────────────────────────────
  // The active format is best discovered from the tiers/status response
  // (the backend tells us which format the user is currently on). If
  // unknown, default to '1qb_ppr' — same fallback the screen already uses
  // for the autoBucket call. The button's `from` is the OTHER format.
  const activeFormat: ScoringFormat =
    (tiersStatusQuery.data?.scoring_format as ScoringFormat) || '1qb_ppr';
  const otherFormat: ScoringFormat =
    FORMAT_KEYS.find((f) => f !== activeFormat) || 'sf_tep';

  const onCopyFromOtherFormat = useCallback(() => {
    // Destructive — confirm before firing. Copy preserves tier label +
    // within-tier rank; only the underlying ELO bands change to fit the
    // target format. Matches web's Alert copy verbatim where practical.
    Alert.alert(
      `Copy tier list from ${FORMAT_LABELS[otherFormat]}?`,
      `This will REPLACE your current ${FORMAT_LABELS[activeFormat]} tiers. ` +
        `Each player keeps their tier and within-tier rank from ` +
        `${FORMAT_LABELS[otherFormat]}; only the underlying ELO values ` +
        `change to fit ${FORMAT_LABELS[activeFormat]}'s bands.\n\n` +
        `Cannot be undone.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Copy',
          style: 'destructive',
          onPress: () => {
            haptics.warning();
            copyMutation.mutate({ from: otherFormat, to: activeFormat });
          },
        },
      ],
    );
  }, [activeFormat, otherFormat, copyMutation]);

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
              {multiSelect
                ? selectedIds.size > 0
                  ? `Selected: ${selectedIds.size}`
                  : 'Cancel'
                : 'Select'}
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

      {/* Copy tier list from the OTHER scoring format. Mirrors web's
          `copy-tiers-btn` — the from-format reads as a label so the user
          knows EXACTLY which format they're pulling tiers from. Disabled
          while the copy is in flight. */}
      <Pressable
        disabled={copyMutation.isPending}
        onPress={onCopyFromOtherFormat}
        style={({ pressed }) => [
          styles.copyBtn,
          pressed && { opacity: 0.7 },
          copyMutation.isPending && { opacity: 0.5 },
        ]}
      >
        {copyMutation.isPending ? (
          <ActivityIndicator color={colors.accent} size="small" />
        ) : (
          <Text style={styles.copyBtnText}>
            ⇆ Copy tier list from {FORMAT_LABELS[otherFormat]}
          </Text>
        )}
      </Pressable>

      <Text style={styles.hint}>
        {multiSelect
          ? 'Tap chips to select. Use the bar below to move all selected up or down.'
          : 'Hold + drag to move a card. Hold still to enter multi-select.'}
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
            ref={binRefSetters.unassigned}
            tier="unassigned"
            count={buckets.unassigned.length}
            onLayout={(e) => setBinLayout('unassigned', e)}
          >
            {buckets.unassigned.length === 0 ? (
              <Text style={styles.emptyBin}>Every player is in a tier.</Text>
            ) : (
              buckets.unassigned.map((p, i) => renderPlayerCard(p, 'unassigned', i))
            )}
          </TierBin>

          {/* The five tier bins */}
          {TIERS.map((t) => (
            <TierBin
              key={t}
              ref={binRefSetters[t]}
              tier={t}
              count={buckets[t].length}
              onLayout={(e) => setBinLayout(t, e)}
            >
              {buckets[t].length === 0 ? (
                <Text style={styles.emptyBin}>Drag players here</Text>
              ) : (
                buckets[t].map((p, i) => renderPlayerCard(p, t, i))
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
// Worklet/JS-boundary rule (preserved from PR #44): every JS-side call
// from a gesture worklet — including the JS function that resolves the
// drop target, the JS function that updates parent state, and even
// `haptics.pickup` — goes through `runOnJS`. Worklets only mutate
// shared values directly. Violating this crashed release builds before.
//
// Gesture wiring for issue #15 (two-stage long-press):
//   - Pan().activateAfterLongPress(220) — short hold then ≥(GH default)
//     finger movement triggers a drag (Gesture Handler's own movement
//     threshold gates pan activation on translation).
//   - LongPress().minDuration(550).maxDistance(8) — same finger held
//     within 8px past 550ms fires `onEnterMultiSelect` (flips multi-
//     select on with this chip pre-selected) instead of starting a
//     drag.
//   - Race(longPress, pan) — whichever activates first wins; the other
//     is canceled. Finger movement wins via the pan; stillness wins
//     via the long-press.
//
// Live drop-preview wiring for issue #14:
//   The chip's `useDerivedValue` worklet reads the parent-owned shared
//   values (proposedZoneSV / proposedInsertIdxSV / dragged{Pid,SrcZone,
//   SrcIdx}SV). Each non-dragged chip translates ±10px when it's the
//   chip immediately adjacent to the proposed insertion point in the
//   proposed zone — opening a visible gap exactly where the chip would
//   land. Computation is index math only (no map lookups), safe inside
//   a worklet.
interface DraggableRowProps {
  player: RankedPlayer;
  binZone: Zone;
  binIndex: number;
  proposedZoneSV: SharedValue<string>;
  proposedInsertIdxSV: SharedValue<number>;
  draggedPidSV: SharedValue<string>;
  draggedSrcZoneSV: SharedValue<string>;
  draggedSrcIdxSV: SharedValue<number>;
  onDragStart: (pid: string) => void;
  onDragUpdate: (absoluteY: number, pid: string) => void;
  onDragEnd: () => void;
  onLayout: (pid: string, screenY: number, height: number) => void;
  onDropAt: (absoluteY: number, pid: string) => void;
  onLongPressDismiss?: () => void;
  onEnterMultiSelect: () => void;
  selectionMode?: boolean;
  isSelected?: boolean;
  onTapInSelection?: () => void;
}

// Vertical translation applied to chips bordering the proposed drop
// slot. The chip immediately above the slot shifts UP; the chip at-or-
// below shifts DOWN — opening a visible gap right where the dragged
// chip would land.
const GAP_SHIFT_PX = 10;

function DraggableRow({
  player,
  binZone,
  binIndex,
  proposedZoneSV,
  proposedInsertIdxSV,
  draggedPidSV,
  draggedSrcZoneSV,
  draggedSrcIdxSV,
  onDragStart,
  onDragUpdate,
  onDragEnd,
  onLayout,
  onDropAt,
  onLongPressDismiss,
  onEnterMultiSelect,
  selectionMode = false,
  isSelected = false,
  onTapInSelection,
}: DraggableRowProps) {
  const translateX = useSharedValue(0);
  const translateY = useSharedValue(0);
  const scale = useSharedValue(1);
  const zIndex = useSharedValue(0);

  // Outer-view ref for measureInWindow inside the onLayout handler so
  // we can hand the parent a screen-Y (matches gesture.absoluteY's
  // coordinate space). Without this, drops resolve against parent-
  // relative Y and land in the wrong tier (TestFlight feedback #23).
  const wrapRef = useRef<View | null>(null);
  const handleLayout = useCallback(() => {
    const node = wrapRef.current;
    if (!node) return;
    node.measureInWindow((_x, y, _w, height) => {
      onLayout(player.id, y, height);
    });
  }, [onLayout, player.id]);

  // Gap-shift for non-dragged chips (issue #14). Derived from the
  // parent's drag-preview shared values so the eased interpolation
  // happens once per change rather than on every animated-style read.
  const gapShiftY = useDerivedValue(() => {
    'worklet';
    if (
      draggedPidSV.value === '' ||
      draggedPidSV.value === player.id ||
      proposedZoneSV.value !== binZone ||
      proposedInsertIdxSV.value < 0
    ) {
      return withTiming(0, { duration: 140 });
    }
    // Translate this chip's pre-removal binIndex into the post-
    // removal coords used by dropTargetAt. If the dragged chip came
    // from this same zone AND its source index sits above this chip,
    // this chip's post-removal index is binIndex - 1; else equal.
    let effective = binIndex;
    if (
      draggedSrcZoneSV.value === binZone &&
      draggedSrcIdxSV.value < binIndex
    ) {
      effective = binIndex - 1;
    }
    if (effective === proposedInsertIdxSV.value) {
      return withTiming(GAP_SHIFT_PX, { duration: 140 });
    }
    if (effective === proposedInsertIdxSV.value - 1) {
      return withTiming(-GAP_SHIFT_PX, { duration: 140 });
    }
    return withTiming(0, { duration: 140 });
  });

  // JS-thread finalizer. Parent owns `dropTargetAt` + movePlayer; we
  // just hand off the screen-Y so the parent can resolve + commit.
  // onDragEnd resets the shared-value preview state before the JS-side
  // bucket mutation triggers a re-render (so the gap doesn't briefly
  // animate against the new layout).
  const handleDropAt = useCallback(
    (absoluteY: number) => {
      onDragEnd();
      onDropAt(absoluteY, player.id);
    },
    [onDragEnd, onDropAt, player.id],
  );

  const longPress = useMemo(
    () =>
      Gesture.LongPress()
        .minDuration(550)
        .maxDistance(8)
        .onStart(() => {
          runOnJS(haptics.selection)();
          runOnJS(onEnterMultiSelect)();
        }),
    [onEnterMultiSelect],
  );

  const pan = useMemo(
    () =>
      Gesture.Pan()
        .activateAfterLongPress(220)
        .onStart(() => {
          scale.value = withTiming(1.04, { duration: 120 });
          zIndex.value = 10;
          runOnJS(haptics.pickup)();
          runOnJS(onDragStart)(player.id);
        })
        .onUpdate((e) => {
          translateX.value = e.translationX;
          translateY.value = e.translationY;
          runOnJS(onDragUpdate)(e.absoluteY, player.id);
        })
        .onEnd((e) => {
          const absoluteY = e.absoluteY;
          translateX.value = withTiming(0, { duration: 160 });
          translateY.value = withTiming(0, { duration: 160 });
          scale.value = withTiming(1, { duration: 160 });
          zIndex.value = 0;
          runOnJS(handleDropAt)(absoluteY);
        }),
    [onDragStart, onDragUpdate, handleDropAt, player.id, translateX, translateY, scale, zIndex],
  );

  // Race ensures only one of {drag, multi-select-enter} fires per
  // gesture. Movement past pan's activation threshold wins for drag;
  // 550ms of stillness wins for long-press.
  const composed = useMemo(
    () => Gesture.Race(longPress, pan),
    [longPress, pan],
  );

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: translateX.value },
      { translateY: translateY.value + gapShiftY.value },
      { scale: scale.value },
    ],
    zIndex: zIndex.value,
  }));

  if (selectionMode) {
    return (
      <Pressable
        ref={wrapRef as any}
        onPress={onTapInSelection}
        onLayout={handleLayout}
        style={({ pressed }) => [
          styles.chipSelectableWrap,
          isSelected && styles.chipSelected,
          pressed && { opacity: 0.85 },
        ]}
      >
        <PlayerCard
          player={player}
          compact
          rightSlot={
            isSelected ? (
              <View style={styles.chipCheckBadge}>
                <Text style={styles.chipCheckBadgeText}>✓</Text>
              </View>
            ) : undefined
          }
        />
      </Pressable>
    );
  }

  return (
    <GestureDetector gesture={composed}>
      <Animated.View
        ref={wrapRef as any}
        style={animatedStyle}
        onLayout={handleLayout}
      >
        <PlayerCard player={player} compact onLongPress={onLongPressDismiss} />
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
  // Wrapper around each chip in multi-select mode. Always present so
  // toggling selection doesn't shift the layout.
  chipSelectableWrap: {
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: 'transparent',
  },
  // Selected-chip state (multi-select mode, issue #16). Accent ring +
  // tinted background + checkmark badge — three signals so selection
  // reads clearly including for color-vision-impaired users.
  chipSelected: {
    backgroundColor: 'rgba(79,124,255,0.14)',
    borderColor: colors.accent,
  },
  chipCheckBadge: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: colors.accent,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipCheckBadgeText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '800',
    lineHeight: 16,
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
  // Copy-tiers-from-other-format pill. Sits between the position switcher
  // and the hint line, full-width with a dashed-ish accent border so it
  // reads as an "action that imports state" rather than a primary CTA.
  copyBtn: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: 'rgba(79,124,255,0.45)',
    backgroundColor: 'rgba(79,124,255,0.08)',
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'center',
    gap: spacing.xs,
    minHeight: 36,
  },
  copyBtnText: {
    color: colors.accent,
    fontSize: fontSize.xs,
    fontWeight: '800',
  },
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
