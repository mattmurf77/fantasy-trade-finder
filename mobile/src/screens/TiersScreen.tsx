import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  LayoutChangeEvent,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { runOnJS } from 'react-native-reanimated';
import {
  NestableScrollContainer,
  NestableDraggableFlatList,
  ScaleDecorator,
  RenderItemParams,
  DragEndParams,
} from 'react-native-draggable-flatlist';
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
import { useSession } from '../state/useSession';
import type { Position, RankedPlayer, Tier, ScoringFormat } from '../shared/types';

// Format-key → human label for the copy button + confirm dialog. Mirrors
// web/positional-tiers.html's FORMAT_LABELS.
const FORMAT_LABELS: Record<ScoringFormat, string> = {
  '1qb_ppr': '🏈 1QB PPR',
  sf_tep:    '🏟 SF TEP',
};
const FORMAT_KEYS: ScoringFormat[] = ['1qb_ppr', 'sf_tep'];

const POSITIONS: Position[] = ['QB', 'RB', 'WR', 'TE'];

// Hold duration before a chip is picked up for drag. Matches ManualRanks'
// DRAG_ACTIVATION_MS so the pickup feel is identical across screens.
const DRAG_ACTIVATION_MS = 220;

/** Which zone a card's center falls into at drag-end.  "unassigned" is
 *  a first-class zone — you can drag a player out of a tier back to the pool. */
type Zone = Tier | 'unassigned';

interface BinLayout {
  zone: Zone;
  // Absolute-to-screen Y bounds; we key drop zones on vertical overlap
  // only (the screen is single-column within the scroll container).
  y: number;
  height: number;
}

export default function TiersScreen() {
  const queryClient = useQueryClient();
  const activeFormat = useSession((s) => s.activeFormat);
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
  // Multi-select is entered ONLY via the "Select" button (FB-02 Part B —
  // the two-stage long-press from PR #58 is removed). While ON, tapping a
  // chip toggles its selection (a lighter-blue full-tile fill marks it)
  // and drag is suppressed. Up/down arrows move the selection as a
  // collapsed contiguous block by one rank per tap.
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
    queryKey: ['rankings', activeFormat, position],
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
      // Tier saves rewrite per-position ELO overrides on the backend,
      // which the Overall / Manual / Tiers screens all read via the
      // `['rankings', ...]` family. Scope to the saved format+position
      // + 'all' to avoid evicting unrelated caches.
      queryClient.invalidateQueries({ queryKey: ['rankings', activeFormat, position] });
      queryClient.invalidateQueries({ queryKey: ['rankings', activeFormat, 'all'] });
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
      // A format copy affects all positions; use the broad prefix so the
      // format-level cache is fully invalidated.
      queryClient.invalidateQueries({ queryKey: ['rankings', activeFormat] });
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
      // Optimistic: pull the player out of every bucket immediately.
      // Snapshot the PRE-removal bucket layout so onError can restore the
      // chip in its original tier + index if the backend rejects the
      // dismiss. Without this, a failed POST silently vanishes the chip
      // until the next rankings refetch (silent-bugs review bug #3).
      const snapshot = cloneBuckets(buckets);
      setBuckets((prev) => {
        const next = cloneBuckets(prev);
        for (const z of ALL_ZONES) next[z] = next[z].filter((p) => p.id !== pid);
        return next;
      });
      return { snapshot };
    },
    onError: (_err, _pid, ctx) => {
      // Restore the snapshot taken in onMutate. We replace the entire
      // bucket map rather than re-inserting the single chip because
      // there's no source-zone bookkeeping (the optimistic filter
      // scans every zone). If the user has already mutated buckets in
      // the meantime (e.g. dragged another chip between optimistic
      // remove and error), this rollback wins — that's the safest
      // semantic for a "this hide failed" error: revert to last-known
      // good and let the user redo the drag.
      if (ctx?.snapshot) setBuckets(ctx.snapshot);
      setToast({ msg: "Couldn't hide player — try again.", tone: 'warn' });
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
    // A position switch / fresh load should not leave us stuck in a stale
    // multi-select over players that no longer exist in the new view.
    exitMultiSelect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rankingsQuery.data, position, tiersStatusQuery.data?.scoring_format]);

  // ── Cross-tier drop infrastructure (PR #60 invariant) ──────────────
  // The drag engine itself is `react-native-draggable-flatlist`: each tier
  // (and the unassigned pool) is its own NestableDraggableFlatList, which
  // gives the Apple "make room" animation WITHIN a tier for free. The
  // library only reorders within its own list, though — it can't move a
  // chip across bins. So cross-tier moves are resolved on drop using the
  // SAME screen-Y model PR #60 introduced:
  //
  //   • Each bin measures its screen-Y bounds via measureInWindow on
  //     layout (binLayouts). These are directly comparable to a finger's
  //     `absoluteY` (screen-Y) — NOT parent-relative layout.y, which
  //     drifts by the scroll container's offset and made drops land one
  //     or two tiers too low (TestFlight feedback #23).
  //   • Each chip measures its own screen-Y on layout (chipLayouts) so we
  //     can resolve the precise insertion index within the target bin.
  //   • A non-activating "spy" Pan tracks the live finger screen-Y. It
  //     uses manualActivation(true) so it NEVER competes with the
  //     library's own drag gesture; it only reads onTouchesMove.absoluteY.
  //
  // On a bin's onDragEnd we compare the last finger screen-Y to the bin
  // layouts. If the finger is over a DIFFERENT zone than the drag's source
  // bin, we treat it as a cross-tier move (resolve zone+index in screen-Y
  // and splice across buckets). If it's over the same zone, we apply the
  // library's within-bin reorder verbatim (preserving the make-room slot).
  const binLayouts = useRef<BinLayout[]>([]);
  const chipLayouts = useRef<Map<string, { y: number; height: number }>>(new Map());

  // Live finger screen-Y, written by the spy-pan's onTouchesMove worklet
  // via runOnJS. Read at drag-end to resolve the drop zone.
  const fingerScreenY = useRef<number>(-1);
  const setFingerScreenY = useCallback((y: number) => {
    fingerScreenY.current = y;
  }, []);

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

  // Chip onLayout: TierRow does its own measureInWindow against its outer
  // View ref and hands us screen-Y + height directly.
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
  // POST-removal coordinates — same convention as web's assignToTierAt.
  // Returns null if the cursor isn't over any zone.
  const dropTargetAt = useCallback(
    (absoluteY: number, draggedPid: string): { zone: Zone; insertIdx: number } | null => {
      const zone = zoneAt(absoluteY);
      if (!zone) return null;
      // For 'unassigned' (the pool) order doesn't drive any backend
      // semantic; insert at end.
      if (zone === 'unassigned') {
        return { zone, insertIdx: buckets.unassigned.length };
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

  // Reorder a single bin in place (within-tier drag — the library's
  // onDragEnd gives us the post-move data array for that bin). No
  // clearedPids change: nothing leaves a tier here.
  const reorderWithinZone = useCallback(
    (zone: Zone, data: RankedPlayer[]) => {
      setBuckets((prev) => {
        const next = cloneBuckets(prev);
        next[zone] = data;
        return next;
      });
      haptics.success();
    },
    [],
  );

  // ── Bulk move (multi-select, collapse-into-a-block) ─────────────────
  // Locked decision: the selected players COLLAPSE INTO A CONTIGUOUS
  // BLOCK and move together one rank per tap (NOT shift-each-
  // independently). The block stays together as it moves, including
  // across tier boundaries.
  //
  // Model: flatten the five tiers into one ordered list (elite→bench).
  // The selected players form a block; we anchor the block at the
  // position of its FIRST selected member, remove all selected from the
  // flat list, then re-insert the contiguous block one slot up or down
  // from that anchor. Re-bucketing the flat list back into tiers makes
  // the block naturally cross a tier boundary when it reaches one.
  const bulkMove = useCallback(
    (direction: 'up' | 'down') => {
      if (selectedIds.size === 0) return;
      setBuckets((prev) => {
        // 1. Flatten the five real tiers into one ordered list, tagging
        //    each player with its source tier so we can re-bucket later.
        const flat: { p: RankedPlayer; tier: Tier }[] = [];
        for (const t of TIERS) {
          for (const p of prev[t]) flat.push({ p, tier: t });
        }

        // 2. Pull out the selected block, preserving its internal order.
        //    Anchor = index (in the post-removal list) where the block
        //    should be re-inserted. We anchor on the FIRST selected
        //    member's original flat index, adjusted for removals above it.
        const selectedBlock: { p: RankedPlayer; tier: Tier }[] = [];
        const remaining: { p: RankedPlayer; tier: Tier }[] = [];
        let firstSelectedFlatIdx = -1;
        flat.forEach((entry, i) => {
          if (selectedIds.has(entry.p.id)) {
            if (firstSelectedFlatIdx < 0) firstSelectedFlatIdx = i;
            selectedBlock.push(entry);
          } else {
            remaining.push(entry);
          }
        });
        if (selectedBlock.length === 0) return prev;

        // Anchor in post-removal coordinates: how many NON-selected
        // entries sit above the first selected one.
        let anchor = 0;
        for (let i = 0; i < firstSelectedFlatIdx; i++) {
          if (!selectedIds.has(flat[i].p.id)) anchor += 1;
        }

        // 3. Shift the anchor one slot in the requested direction, clamped
        //    to the bounds of the remaining list. If we're already at the
        //    boundary the move is a no-op (matches web's clamp behavior).
        const maxAnchor = remaining.length;          // can insert at end
        const target =
          direction === 'up'
            ? Math.max(0, anchor - 1)
            : Math.min(maxAnchor, anchor + 1);
        if (target === anchor) return prev;           // already at boundary

        // 4. Re-insert the contiguous block at the shifted anchor.
        const merged = [
          ...remaining.slice(0, target),
          ...selectedBlock,
          ...remaining.slice(target),
        ];

        // 5. Re-bucket the flat list back into tiers. Tier membership is
        //    decided positionally by the original tier-size partition —
        //    walk `merged` and refill each tier to its ORIGINAL count so
        //    the block visibly crosses a boundary as it passes through.
        const next = cloneBuckets(prev);
        let cursor = 0;
        for (const t of TIERS) {
          const size = prev[t].length;
          next[t] = merged.slice(cursor, cursor + size).map((e) => e.p);
          cursor += size;
        }
        // `unassigned` is untouched by bulk moves.
        return next;
      });
      // No clearedPids change — bulk moves keep all selected players in
      // some tier (the flat list only ever contains tier members).
      haptics.success();
    },
    [selectedIds],
  );

  // ── Render helpers ─────────────────────────────────────────────────
  const saving = saveMutation.isPending;
  const loading = rankingsQuery.isLoading || rankingsQuery.isFetching;

  // Stable per-chip dismiss (long-press in normal mode only). Suppressed
  // in select mode so the only chip-level action there is tap-to-toggle.
  const handleDismiss = useCallback(
    (pid: string) => {
      haptics.warning();
      dismissMutation.mutate(pid);
    },
    [dismissMutation],
  );

  // renderItem factory bound to a specific zone. DraggableFlatList passes
  // {item, drag, isActive, getIndex}; `drag` is the library's own
  // long-press-to-pickup trigger (gives the make-room feel). In select
  // mode we render a tappable, light-blue-fillable tile and ignore `drag`.
  const makeRenderItem = useCallback(
    (zone: Zone) =>
      ({ item, drag, isActive }: RenderItemParams<RankedPlayer>) => (
        <TierRow
          player={item}
          drag={drag}
          isActive={isActive}
          onLayout={setChipLayout}
          onDismiss={multiSelect ? undefined : handleDismiss}
          selectionMode={multiSelect}
          isSelected={selectedIds.has(item.id)}
          onTapInSelection={() => toggleSelected(item.id)}
        />
      ),
    [multiSelect, selectedIds, setChipLayout, handleDismiss, toggleSelected],
  );

  // Per-bin drag-end. The library hands us {data, from, to} for THIS bin
  // only. We decide within-tier vs cross-tier from the finger's last
  // screen-Y (PR #60 model).
  const makeOnDragEnd = useCallback(
    (zone: Zone) =>
      ({ data, from, to }: DragEndParams<RankedPlayer>) => {
        // The dragged chip is the one that was at `from` in this bin's
        // PRE-move array; after the library's reorder it sits at `to` in
        // `data`. We recover its id from the moved item.
        const movedId = data[to]?.id;
        const fingerY = fingerScreenY.current;
        const target = movedId != null ? dropTargetAt(fingerY, movedId) : null;

        // Cross-tier: finger ended over a DIFFERENT zone than this bin.
        if (target && target.zone !== zone && movedId != null) {
          movePlayer(movedId, target.zone, target.insertIdx);
          return;
        }
        // Same-zone (or unresolved finger) → apply the library's within-
        // bin reorder verbatim. The make-room animation already showed
        // the user exactly this order.
        if (from === to) return;        // no-op drag
        reorderWithinZone(zone, data);
      },
    [dropTargetAt, movePlayer, reorderWithinZone],
  );

  // ── Copy-from-format button derivation ─────────────────────────────
  // Resolve the format to copy INTO (the "target"). Prefer the session
  // activeFormat; fall back to the tiers/status response or '1qb_ppr'.
  const copyTargetFormat: ScoringFormat =
    activeFormat ?? (tiersStatusQuery.data?.scoring_format as ScoringFormat) ?? '1qb_ppr';
  const otherFormat: ScoringFormat =
    FORMAT_KEYS.find((f) => f !== copyTargetFormat) || 'sf_tep';

  const onCopyFromOtherFormat = useCallback(() => {
    // Destructive — confirm before firing. Copy preserves tier label +
    // within-tier rank; only the underlying ELO bands change to fit the
    // target format. Matches web's Alert copy verbatim where practical.
    Alert.alert(
      `Copy tier list from ${FORMAT_LABELS[otherFormat]}?`,
      `This will REPLACE your current ${FORMAT_LABELS[copyTargetFormat]} tiers. ` +
        `Each player keeps their tier and within-tier rank from ` +
        `${FORMAT_LABELS[otherFormat]}; only the underlying ELO values ` +
        `change to fit ${FORMAT_LABELS[copyTargetFormat]}'s bands.\n\n` +
        `Cannot be undone.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Copy',
          style: 'destructive',
          onPress: () => {
            haptics.warning();
            copyMutation.mutate({ from: otherFormat, to: copyTargetFormat });
          },
        },
      ],
    );
  }, [copyTargetFormat, otherFormat, copyMutation]);

  // ── Spy-pan: live finger screen-Y for cross-tier resolution ─────────
  // manualActivation(true) means this gesture NEVER activates and so never
  // competes with the per-bin drag gestures owned by the draggable lists.
  // It only observes touch moves to record screen-Y (PR #60 coordinate
  // space). Worklet/JS boundary (PR #44): the only JS call is setFinger-
  // ScreenY, routed through runOnJS.
  const spyPan = useMemo(
    () =>
      Gesture.Pan()
        .manualActivation(true)
        .onTouchesMove((e) => {
          const t = e.changedTouches[0] ?? e.allTouches[0];
          if (t) runOnJS(setFingerScreenY)(t.absoluteY);
        }),
    [setFingerScreenY],
  );

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
          {/* Multi-select toggle (FB-02 Part B — the ONLY way into select
              mode; long-press no longer triggers it). While ON, chip tap
              toggles selection (drag is suppressed); tapping again here
              cancels and clears the set. The bottom action bar handles
              the actual grouped moves. */}
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
          : 'Hold + drag a card to re-rank it; the others slide to make room.'}
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
        <GestureDetector gesture={spyPan}>
          <NestableScrollContainer
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
                <NestableDraggableFlatList
                  data={buckets.unassigned}
                  keyExtractor={keyExtractor}
                  renderItem={makeRenderItem('unassigned')}
                  onDragEnd={makeOnDragEnd('unassigned')}
                  activationDistance={12}
                  scrollEnabled={false}
                  ItemSeparatorComponent={Separator}
                />
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
                  <NestableDraggableFlatList
                    data={buckets[t]}
                    keyExtractor={keyExtractor}
                    renderItem={makeRenderItem(t)}
                    onDragEnd={makeOnDragEnd(t)}
                    activationDistance={12}
                    scrollEnabled={false}
                    ItemSeparatorComponent={Separator}
                  />
                )}
              </TierBin>
            ))}
          </NestableScrollContainer>
        </GestureDetector>
      )}

      {/* Multi-select action bar — only shown in select mode with at
          least one chip selected. Sits above the save bar so the user
          can still commit after a grouped move without leaving select
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
              <Text style={styles.actionBarBtnText}>↑ Up</Text>
            </Pressable>
            <Pressable
              onPress={() => bulkMove('down')}
              style={({ pressed }) => [styles.actionBarBtn, pressed && { opacity: 0.7 }]}
            >
              <Text style={styles.actionBarBtnText}>↓ Down</Text>
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

// ── TierRow — one player chip inside a NestableDraggableFlatList ───────
//
// Two render modes:
//   • Normal: a draggable cell. `drag` (passed by the library) is wired to
//     the row's onLongPress so a hold-then-move picks the chip up — the
//     library then animates the OTHER cells out of the way to open the
//     destination slot (the Apple "make room" feel, matching ManualRanks).
//     ScaleDecorator lifts the active cell. A separate, longer long-press
//     on the card itself dismisses the player (kept from the prior screen).
//   • Select mode: a plain tappable tile. Tapping toggles selection; a
//     selected tile gets a LIGHTER-BLUE FULL-TILE FILL (FB-02 Part B).
//     Drag is fully suppressed in this mode.
//
// The outer view measures its own screen-Y on layout (measureInWindow) and
// hands it to the parent so cross-tier drop resolution stays in screen-Y
// (PR #60). React.memo keeps re-renders scoped to selection/active changes.
interface TierRowProps {
  player: RankedPlayer;
  drag: () => void;
  isActive: boolean;
  onLayout: (pid: string, screenY: number, height: number) => void;
  onDismiss?: (pid: string) => void;
  selectionMode: boolean;
  isSelected: boolean;
  onTapInSelection: () => void;
}

function TierRowInner({
  player,
  drag,
  isActive,
  onLayout,
  onDismiss,
  selectionMode,
  isSelected,
  onTapInSelection,
}: TierRowProps) {
  const wrapRef = useRef<View | null>(null);
  const handleLayout = useCallback(() => {
    const node = wrapRef.current;
    if (!node) return;
    node.measureInWindow((_x, y, _w, height) => {
      onLayout(player.id, y, height);
    });
  }, [onLayout, player.id]);

  if (selectionMode) {
    return (
      <View
        ref={wrapRef}
        onLayout={handleLayout}
        style={[styles.chipWrap, isSelected && styles.chipSelected]}
      >
        <Pressable
          onPress={onTapInSelection}
          style={({ pressed }) => [pressed && { opacity: 0.85 }]}
        >
          <PlayerCard player={player} compact />
        </Pressable>
      </View>
    );
  }

  return (
    <ScaleDecorator activeScale={1.04}>
      <Pressable
        ref={wrapRef}
        onLayout={handleLayout}
        // Long-press picks the chip up — this is the library's `drag`
        // trigger, mirroring ManualRanks' `onLongPress={drag}` (220ms).
        // Once held, the library animates the OTHER cells out of the way
        // to open the destination slot (the "make room" feel).
        onLongPress={drag}
        delayLongPress={DRAG_ACTIVATION_MS}
        disabled={isActive}
        style={({ pressed }) => [
          styles.chipWrap,
          isActive && styles.chipActive,
          pressed && !isActive && { opacity: 0.92 },
        ]}
      >
        <PlayerCard
          player={player}
          compact
          // Hide-from-pool affordance. A long-press now belongs to the
          // drag engine, so dismiss moves to an explicit tap target in
          // the card's rightSlot (a supported PlayerCard prop — no edit
          // to PlayerCard). hitSlop keeps it comfortably tappable without
          // stealing the long-press that starts a drag.
          rightSlot={
            onDismiss ? (
              <Pressable
                onPress={() => onDismiss(player.id)}
                hitSlop={10}
                style={({ pressed }) => [styles.hideBtn, pressed && { opacity: 0.6 }]}
              >
                <Text style={styles.hideBtnText}>✕</Text>
              </Pressable>
            ) : undefined
          }
        />
      </Pressable>
    </ScaleDecorator>
  );
}

const TierRow = React.memo(TierRowInner);

// ── Helpers ─────────────────────────────────────────────────────────

const ALL_ZONES: Zone[] = ['unassigned', 'elite', 'starter', 'solid', 'depth', 'bench'];

const keyExtractor = (p: RankedPlayer) => p.id;
const Separator = () => <View style={styles.sep} />;

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
  // Wrapper around each chip. Always present so toggling selection / drag-
  // active state never shifts the surrounding layout.
  chipWrap: {
    borderRadius: radius.md,
  },
  // Selected-chip state (FB-02 Part B): a LIGHTER-BLUE FULL-TILE FILL —
  // a clear, whole-tile signal (not a subtle border). The fill sits on
  // the wrapper so it reads as the entire chip turning light blue.
  chipSelected: {
    backgroundColor: 'rgba(79,124,255,0.28)',
  },
  // Active (being dragged) chip — subtle lift tint so the picked-up card
  // reads as elevated. ScaleDecorator handles the scale.
  chipActive: {
    backgroundColor: 'rgba(79,124,255,0.06)',
  },
  // Hide-from-pool tap target in the card's rightSlot (normal mode only).
  hideBtn: {
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(122,127,150,0.18)',
  },
  hideBtnText: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: '800',
    lineHeight: 15,
  },
  // Floating action bar — shown above the save bar when ≥1 chip is
  // selected. Up / Down move the selected block by one rank; Done exits.
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
  sep: { height: spacing.xs },
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
