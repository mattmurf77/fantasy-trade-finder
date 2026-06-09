import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  Alert,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import DraggableFlatList, {
  RenderItemParams,
  DragEndParams,
} from 'react-native-draggable-flatlist';
import { haptics } from '../utils/haptics';
import { startSpan } from '../observability/sentry';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import PlayerCard from '../components/PlayerCard';
import Toast from '../components/Toast';
import {
  getRankings,
  saveTiers,
  getTiersStatus,
} from '../api/rankings';
import { copyTiersFromFormat } from '../api/league';
import { autoBucket, TIERS, TIER_LABEL } from '../utils/tierBands';
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

/** Which zone a card sits in.  "unassigned" is a first-class zone — you
 *  can drag a player out of a tier back to the pool. */
type Zone = Tier | 'unassigned';

// Flat list rows for the single DraggableFlatList. The list interleaves
// non-draggable header/empty rows with draggable player rows so the
// standard "tiles slide to make room" reorder feel (matching
// ManualRanksScreen) carries across tier boundaries.
type Row =
  | { kind: 'header'; zone: Zone }
  | { kind: 'player'; zone: Zone; player: RankedPlayer }
  | { kind: 'empty';  zone: Zone };

const DRAG_ACTIVATION_MS = 220;

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

  // ── Bulk move (multi-select) ────────────────────────────────────────
  // Collapse the selected chips into a CONTIGUOUS BLOCK and move the whole
  // block by ONE rank in `direction` (#32). Non-adjacent selections gather
  // together; the block crosses tier boundaries as a single unit; clamps
  // at the top of `elite` / bottom of `bench`.
  const bulkMove = useCallback(
    (direction: 'up' | 'down') => {
      if (selectedIds.size === 0) return;
      setBuckets((prev) => {
        // 1. Flatten the five real tiers into one ordered list.
        const flat: { p: RankedPlayer; tier: Tier }[] = [];
        for (const t of TIERS) for (const p of prev[t]) flat.push({ p, tier: t });

        // 2. Split into the selected block (internal order preserved) and
        //    the remaining list; note the first selected flat index.
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

        // 3. Anchor = how many non-selected entries sit above the first
        //    selected one (post-removal coords); shift one slot, clamped.
        let anchor = 0;
        for (let i = 0; i < firstSelectedFlatIdx; i++) {
          if (!selectedIds.has(flat[i].p.id)) anchor += 1;
        }
        const target =
          direction === 'up'
            ? Math.max(0, anchor - 1)
            : Math.min(remaining.length, anchor + 1);
        if (target === anchor) return prev;            // already at boundary

        // 4. Re-insert the contiguous block at the shifted anchor.
        const merged = [
          ...remaining.slice(0, target),
          ...selectedBlock,
          ...remaining.slice(target),
        ];

        // 5. Re-bucket into tiers, refilling each to its ORIGINAL size so
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
      haptics.success();
    },
    [selectedIds],
  );

  // ── Render helpers ─────────────────────────────────────────────────
  const saving = saveMutation.isPending;
  const loading = rankingsQuery.isLoading || rankingsQuery.isFetching;

  // ── Flat list derivation ───────────────────────────────────────────
  // Walk unassigned first, then the five tiers in TIERS order. Every
  // zone always contributes a header (so empty tiers stay visible and
  // droppable); a zone with no players contributes a single muted
  // `empty` placeholder row instead of player rows.
  const listData: Row[] = useMemo(() => {
    const rows: Row[] = [];
    const zones: Zone[] = ['unassigned', ...TIERS];
    for (const zone of zones) {
      rows.push({ kind: 'header', zone });
      const players = buckets[zone];
      if (players.length === 0) {
        rows.push({ kind: 'empty', zone });
      } else {
        for (const player of players) rows.push({ kind: 'player', zone, player });
      }
    }
    return rows;
  }, [buckets]);

  const keyExtractor = useCallback((item: Row) => {
    if (item.kind === 'header') return `hdr:${item.zone}`;
    if (item.kind === 'empty') return `empty:${item.zone}`;
    return item.player.id;
  }, []);

  // ── Drag handler ───────────────────────────────────────────────────
  // Rebuild buckets by walking the post-drag flat order: each header row
  // re-anchors the "current zone", and every player row that follows
  // lands in that zone. Then reconcile clearedPids — players now in the
  // pool are cleared; players in any tier must drop out of the cleared
  // set (drag-out-then-back-in within one session).
  const onDragEnd = useCallback(
    ({ data }: DragEndParams<Row>) => {
      let zone: Zone = 'unassigned';
      const next = emptyBuckets();
      for (const r of data) {
        if (r.kind === 'header') zone = r.zone;
        else if (r.kind === 'player') next[zone].push(r.player);
      }
      setBuckets(next);
      setClearedPids((prev) => {
        const out = new Set(prev);
        for (const p of next.unassigned) out.add(p.id);
        for (const t of TIERS) for (const p of next[t]) out.delete(p.id);
        return out;
      });
      haptics.success();
    },
    [],
  );

  const renderItem = useCallback(
    ({ item, drag, isActive }: RenderItemParams<Row>) => {
      if (item.kind === 'header') {
        const accent = accentFor(item.zone);
        const label = item.zone === 'unassigned' ? 'Unassigned' : TIER_LABEL[item.zone];
        const count = buckets[item.zone].length;
        return (
          <View style={[styles.tierHeader, { borderLeftColor: accent }]}>
            <Text style={[styles.tierHeaderLabel, { color: accent }]}>{label}</Text>
            <Text style={styles.tierHeaderCount}>{count}</Text>
          </View>
        );
      }

      if (item.kind === 'empty') {
        return (
          <Text style={styles.emptyBin}>
            {item.zone === 'unassigned'
              ? 'Every player is in a tier.'
              : 'Drag players here'}
          </Text>
        );
      }

      // ── Player row ──────────────────────────────────────────────────
      const isSelected = selectedIds.has(item.player.id);

      if (multiSelect) {
        return (
          <Pressable
            onPress={() => toggleSelected(item.player.id)}
            style={({ pressed }) => [
              styles.chipSelectableWrap,
              isSelected && styles.chipSelected,
              pressed && { opacity: 0.85 },
            ]}
          >
            {/* pointerEvents="none" so PlayerCard's own inner Pressable
                can't become the touch responder — without this the inner
                Pressable swallows the tap and the outer selection onPress
                never fires, leaving multi-select dead. */}
            <View pointerEvents="none">
              <PlayerCard
                player={item.player}
                compact
                rightSlot={
                  isSelected ? (
                    <View style={styles.chipCheckBadge}>
                      <Text style={styles.chipCheckBadgeText}>✓</Text>
                    </View>
                  ) : undefined
                }
              />
            </View>
          </Pressable>
        );
      }

      // Normal mode: long-press to pick up; the others slide to make room.
      return (
        <Pressable
          onLongPress={drag}
          delayLongPress={DRAG_ACTIVATION_MS}
          disabled={isActive}
          style={({ pressed }) => [
            styles.playerRow,
            isActive && styles.playerRowActive,
            pressed && !isActive && { opacity: 0.9 },
          ]}
        >
          <PlayerCard player={item.player} compact />
        </Pressable>
      );
    },
    [buckets, multiSelect, selectedIds, toggleSelected],
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
          : 'Long-press + drag to re-rank; the others slide to make room. Tap "Select" to move several at once.'}
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
        <DraggableFlatList
          data={listData}
          keyExtractor={keyExtractor}
          renderItem={renderItem}
          onDragEnd={onDragEnd}
          activationDistance={5}
          containerStyle={styles.listContainer}
          contentContainerStyle={styles.scroll}
        />
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

// ── Helpers ─────────────────────────────────────────────────────────

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

// Accent foreground color for a zone's header — mirrors TierBin's accentFor.
function accentFor(zone: Zone): string {
  switch (zone) {
    case 'elite':   return colors.tier.elite;
    case 'starter': return colors.tier.starter;
    case 'solid':   return colors.tier.solid;
    case 'depth':   return colors.tier.depth;
    case 'bench':   return colors.tier.bench;
    default:        return colors.muted;
  }
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
  // Standalone tier-header row inside the flat list. Mirrors TierBin's
  // header look (accent left-border + accent label + muted count).
  tierHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    marginTop: spacing.sm,
    marginBottom: spacing.xs,
    borderLeftWidth: 3,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.md,
    borderTopRightRadius: radius.md,
  },
  tierHeaderLabel: { fontSize: fontSize.sm, fontWeight: '800', letterSpacing: 0.4 },
  tierHeaderCount: { color: colors.muted, fontSize: fontSize.xs, fontWeight: '700' },
  // Player row wrapper in normal (drag) mode. Active row gets a subtle
  // lift to read as "picked up", matching ManualRanks' rowActive.
  playerRow: {
    marginBottom: spacing.xs,
  },
  playerRowActive: {
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
  // Wrapper around each chip in multi-select mode. Always present so
  // toggling selection doesn't shift the layout.
  chipSelectableWrap: {
    marginBottom: spacing.xs,
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: 'transparent',
  },
  // Selected-chip state (multi-select mode, issue #16). Accent ring +
  // tinted background + checkmark badge — three signals so selection
  // reads clearly including for color-vision-impaired users.
  chipSelected: {
    // Clear lighter-blue fill across the whole tile (#32 — the old 0.14
    // alpha read as a faint border-only state).
    backgroundColor: 'rgba(79,124,255,0.30)',
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
  // Floating action bar — shown above the save bar when 1+ chips are
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
  listContainer: { flex: 1 },
  scroll: {
    padding: spacing.lg,
    paddingBottom: 96, // room for the Save bar
  },
  emptyBin: {
    color: colors.muted,
    fontSize: fontSize.xs,
    textAlign: 'center',
    paddingVertical: spacing.sm,
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
