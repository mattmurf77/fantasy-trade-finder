import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import DraggableFlatList, {
  RenderItemParams,
  DragEndParams,
} from 'react-native-draggable-flatlist';
import { haptics } from '../utils/haptics';
import { startSpan } from '../observability/sentry';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import {
  ink,
  chalk,
  ice,
  semantic,
  tier as tierColors,
  position as positionColors,
  space,
  radii,
  type,
  fonts,
} from '../theme/chalkline';
import { TickLabel, Button, Icon } from '../components/chalkline';
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
  '1qb_ppr': '1QB PPR',
  sf_tep:    'SF TEP',
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
      setToast({ msg: 'Tiers saved', tone: 'success' });
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
      // Local edits are now server truth — let the refetch rebuild buckets.
      bucketsDirtyRef.current = false;
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
      setToast({ msg: `Copied ${n} tier placements`, tone: 'success' });
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
      // Copy replaces local state wholesale — let the refetch rebuild.
      bucketsDirtyRef.current = false;
    },
    onError: (e: Error) => {
      setToast({ msg: e.message || 'Copy failed', tone: 'warn' });
    },
  });

  // Unsaved-local-edits guard (HANDOFF follow-up #1). Any drag / bulk move
  // marks the buckets dirty; while dirty, a background refetch of the SAME
  // position+format must NOT rebuild buckets from server data (it would wipe
  // the user's unsaved placements — e.g. refetchOnWindowFocus mid-edit).
  // Position/format switches and post-save/copy/reset refetches still rebuild:
  // the key changes for the former, the mutations clear the flag for the latter.
  const bucketsDirtyRef = useRef(false);
  const bucketKeyRef = useRef('');

  // Re-auto-bucket whenever the rankings response changes OR position switches.
  useEffect(() => {
    const data = rankingsQuery.data;
    if (!data?.rankings) return;

    // Players come back with per-position ELO + rank. The data shape is
    // any[] per api/rankings.ts so cast each row into RankedPlayer.
    const players = (data.rankings as RankedPlayer[]).slice().sort(
      (a, b) => (b.elo ?? 0) - (a.elo ?? 0),
    );

    // Scoring-format resolution (FB-76). The session's activeFormat is
    // authoritative — it's what the server's _active_format(sess) applies
    // when stamping tier-band ELOs on save. The old primary source
    // (tiersStatusQuery.data?.scoring_format) NEVER existed in the
    // response, so SF leagues silently re-bucketed QB/TE saves with
    // 1qb_ppr thresholds and every Solid save displayed as Starter.
    const fmt: ScoringFormat =
      activeFormat ||
      (tiersStatusQuery.data?.scoring_format as ScoringFormat) ||
      '1qb_ppr';

    const bucketKey = `${position}:${fmt}`;
    if (bucketKey === bucketKeyRef.current && bucketsDirtyRef.current) {
      return; // background refetch mid-edit — keep the user's unsaved layout
    }
    bucketKeyRef.current = bucketKey;
    bucketsDirtyRef.current = false;

    const bucketed = autoBucket(players, position, fmt);
    setBuckets({ ...bucketed, unassigned: [] });
    // The clearedPids set is per-position (the saved snapshot is too).
    // Position switch or rankings-refetch invalidates the previous
    // position's pending clears.
    setClearedPids(new Set());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rankingsQuery.data, position, activeFormat, tiersStatusQuery.data?.scoring_format]);

  // ── Bulk move (multi-select) ────────────────────────────────────────
  // Collapse the selected chips into a CONTIGUOUS BLOCK and move the whole
  // block by ONE rank in `direction` (#32). Non-adjacent selections gather
  // together; the block crosses tier boundaries as a single unit; clamps
  // at the top of `elite` / bottom of `bench`.
  const bulkMove = useCallback(
    (direction: 'up' | 'down') => {
      if (selectedIds.size === 0) return;
      bucketsDirtyRef.current = true;
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

        // 4. Re-insert the contiguous block at the shifted anchor. The block
        //    adopts the tier of the single non-selected entry it swaps past,
        //    so ONLY the selected players can change tier. Every non-selected
        //    player keeps its own tier — moving the selection no longer shoves
        //    boundary players across tiers to preserve fixed tier sizes (the
        //    refill-by-size approach did that and was wrong).
        const passed =
          direction === 'down' ? remaining[anchor] : remaining[anchor - 1];
        const blockTier: Tier = passed ? passed.tier : selectedBlock[0].tier;
        const merged: { p: RankedPlayer; tier: Tier }[] = [
          ...remaining.slice(0, target),
          ...selectedBlock.map((e) => ({ p: e.p, tier: blockTier })),
          ...remaining.slice(target),
        ];

        // 5. Re-bucket by each entry's carried tier: non-selected entries keep
        //    their original tier, the block is blockTier. Walking in global
        //    order preserves within-tier ordering. `unassigned` is untouched.
        const next = emptyBuckets();
        next.unassigned = [...prev.unassigned];
        for (const e of merged) next[e.tier].push(e.p);
        return next;
      });
      haptics.success();
    },
    [selectedIds],
  );

  // ── Bulk TIER move (multi-select, FB-73) ────────────────────────────
  // Move every selected player one whole tier in `direction`, independent
  // of rank position. Complements bulkMove (one RANK at a time). Placement
  // inside the target tier: moving up appends to the BOTTOM of the higher
  // tier (they're its newest/weakest members); moving down inserts at the
  // TOP of the lower tier (its strongest). Relative order among the moved
  // players is preserved. Clamps at elite / bench.
  const bulkTierMove = useCallback(
    (direction: 'up' | 'down') => {
      if (selectedIds.size === 0) return;
      bucketsDirtyRef.current = true;
      setBuckets((prev) => {
        const next = emptyBuckets();
        next.unassigned = [...prev.unassigned];
        // Split each tier into keepers and movers, preserving order.
        const movers: Record<Tier, RankedPlayer[]> = {
          elite: [], starter: [], solid: [], depth: [], bench: [],
        };
        for (const t of TIERS) {
          for (const p of prev[t]) {
            if (selectedIds.has(p.id)) movers[t].push(p);
            else next[t].push(p);
          }
        }
        let changed = false;
        for (let ti = 0; ti < TIERS.length; ti++) {
          const from = TIERS[ti];
          if (movers[from].length === 0) continue;
          const targetIdx =
            direction === 'up'
              ? Math.max(0, ti - 1)
              : Math.min(TIERS.length - 1, ti + 1);
          const to = TIERS[targetIdx];
          if (to === from) {
            next[from] = direction === 'up'
              ? [...movers[from], ...next[from]]
              : [...next[from], ...movers[from]];
            continue; // clamped at the boundary tier
          }
          changed = true;
          if (direction === 'up') next[to] = [...next[to], ...movers[from]];
          else next[to] = [...movers[from], ...next[to]];
        }
        if (!changed) return prev;
        return next;
      });
      haptics.success();
    },
    [selectedIds],
  );

  // ── Render helpers ─────────────────────────────────────────────────
  const saving = saveMutation.isPending;
  // Initial load ONLY (HANDOFF follow-up #1) — `isFetching` here swapped the
  // whole list for a full-screen spinner on every background refetch.
  const loading = rankingsQuery.isLoading;

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
      bucketsDirtyRef.current = true;
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
          <View style={styles.tierHeader}>
            <TickLabel color={accent}>{label}</TickLabel>
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
            style={[styles.chipSelectableWrap, isSelected && styles.chipSelected]}
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
                    <Icon name="check" size={16} color={ice.base} />
                  ) : undefined
                }
              />
            </View>
          </Pressable>
        );
      }

      // Normal mode: long-press to pick up; the others slide to make room.
      // pointerEvents="none" on the PlayerCard wrapper is REQUIRED — PlayerCard
      // renders its own inner Pressable, which would otherwise become the touch
      // responder and swallow the long-press so onLongPress={drag} never fires
      // (the row then only scrolls, never lifts). With touches passing through,
      // the outer Pressable gets the long-press and calls the library's drag().
      return (
        <Pressable
          onLongPress={drag}
          delayLongPress={DRAG_ACTIVATION_MS}
          disabled={isActive}
          style={[styles.playerRow, isActive && styles.playerRowActive]}
        >
          <View pointerEvents="none">
            <PlayerCard player={item.player} compact />
          </View>
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

  // ── Reset to suggested tiers (#55, reworked for FB-74) ─────────────
  // The old client-side revert re-auto-bucketed from the CURRENT served
  // ELOs — but manual tier saves are baked into those ELOs as overrides,
  // so "reset" reproduced the manual layout verbatim and looked like a
  // no-op (FB-74, and FB-55 before it). Real reset = tell the backend to
  // DELETE this position's overrides (a clear-only save: empty tiers +
  // every pid in cleared_pids is a valid payload per the locked
  // /api/tiers/save contract), then refetch; the rankings come back with
  // natural ELOs and the auto-bucket effect rebuilds the true suggested
  // layout.
  const resetMutation = useMutation({
    mutationFn: () => {
      const data = rankingsQuery.data;
      const pids = data?.rankings
        ? (data.rankings as RankedPlayer[]).map((p) => p.id)
        : [];
      return saveTiers(position, {}, pids);
    },
    onSuccess: () => {
      setToast({ msg: 'Tiers reset to suggested', tone: 'success' });
      setClearedPids(new Set());
      // Reset discards local edits by design — let the refetch rebuild.
      bucketsDirtyRef.current = false;
      queryClient.invalidateQueries({ queryKey: ['tiers-status'] });
      queryClient.invalidateQueries({ queryKey: ['progress'] });
      queryClient.invalidateQueries({ queryKey: ['rankings', activeFormat, position] });
      queryClient.invalidateQueries({ queryKey: ['rankings', activeFormat, 'all'] });
      haptics.success();
    },
    onError: (e: Error) => {
      setToast({ msg: e.message || 'Reset failed', tone: 'warn' });
    },
  });

  const onResetToSuggested = useCallback(() => {
    if (!rankingsQuery.data?.rankings) return;
    Alert.alert(
      `Reset ${position} tiers to suggested?`,
      `Your manual placements for ${position} will be cleared and replaced ` +
        `with the app's suggested tiers. This takes effect immediately.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Reset',
          style: 'destructive',
          onPress: () => resetMutation.mutate(),
        },
      ],
    );
  }, [rankingsQuery.data, position, resetMutation]);

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
          <Button
            variant="secondary"
            compact
            label={
              multiSelect
                ? selectedIds.size > 0
                  ? `Selected: ${selectedIds.size}`
                  : 'Cancel'
                : 'Select'
            }
            onPress={() => {
              if (multiSelect) exitMultiSelect();
              else { setMultiSelect(true); haptics.selection(); }
            }}
            style={multiSelect ? styles.selectBtnActive : styles.headerBtn}
          />
          <Button
            variant="ghost"
            compact
            label="Reset to suggested"
            disabled={!rankingsQuery.data?.rankings}
            onPress={onResetToSuggested}
            style={styles.headerBtn}
          />
        </View>
      </View>

      {/* Position switcher — PositionTabs spec: segmented group, active
          segment gets an ink-3 fill + 2px underline in that position's
          color (position hexes are cross-client invariants). */}
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
                isActive && {
                  borderBottomColor:
                    positionColors[p.toLowerCase() as keyof typeof positionColors],
                },
                pressed && !isActive && { backgroundColor: ink.ink3 },
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
          while the copy is in flight. Composed inline (secondary-button
          tokens) because the Button primitive has no icon/spinner slot. */}
      <Pressable
        disabled={copyMutation.isPending}
        onPress={onCopyFromOtherFormat}
        style={({ pressed }) => [
          styles.copyBtn,
          pressed && { backgroundColor: ink.ink3 },
          copyMutation.isPending && { opacity: 0.45 },
        ]}
      >
        {copyMutation.isPending ? (
          <ActivityIndicator color={chalk.dim} size="small" />
        ) : (
          <>
            <Icon name="swap" size={16} color={chalk.dim} />
            <Text style={styles.copyBtnText}>
              Copy tier list from {FORMAT_LABELS[otherFormat]}
            </Text>
          </>
        )}
      </Pressable>

      <Text style={styles.hint}>
        {multiSelect
          ? 'Tap chips to select. Use the bar below to move all selected up or down.'
          : 'Long-press + drag to re-rank; the others slide to make room. Tap "Select" to move several at once.'}
      </Text>

      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator color={chalk.dim} />
        </View>
      ) : rankingsQuery.isError ? (
        <View style={styles.centered}>
          <Text style={styles.errorText}>Could not load rankings.</Text>
          <Button
            variant="ghost"
            compact
            label="Try again"
            onPress={() => rankingsQuery.refetch()}
          />
        </View>
      ) : (
        <DraggableFlatList
          data={listData}
          keyExtractor={keyExtractor}
          renderItem={renderItem}
          onDragEnd={onDragEnd}
          // #57: drag starts from a long-press (onLongPress={drag}), so a
          // small activationDistance only let an ordinary vertical scroll
          // swipe cross the 5px threshold and steal the touch into a drag.
          // Raised to 18px so normal scrolling stays a scroll; the long-
          // press still initiates the drag and edge auto-scroll (library
          // autoscrollThreshold/Speed defaults, untouched) still works.
          activationDistance={18}
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
            <Text style={styles.actionBarCountNum}>{selectedIds.size}</Text>
            {' selected'}
          </Text>
          <View style={styles.actionBarBtns}>
            <Button
              variant="secondary"
              compact
              label="Up"
              onPress={() => bulkMove('up')}
            />
            <Button
              variant="secondary"
              compact
              label="Down"
              onPress={() => bulkMove('down')}
            />
            <Button
              variant="secondary"
              compact
              label="Tier up"
              onPress={() => bulkTierMove('up')}
            />
            <Button
              variant="secondary"
              compact
              label="Tier down"
              onPress={() => bulkTierMove('down')}
            />
            <Button
              variant="ghost"
              compact
              label="Done"
              onPress={exitMultiSelect}
            />
          </View>
        </View>
      ) : null}

      {/* Save button pinned to the bottom. Composed inline (primary-button
          tokens) because the Button primitive has no in-flight spinner. */}
      <View style={styles.saveBar}>
        <Pressable
          disabled={saving || loading}
          onPress={() => saveMutation.mutate()}
          style={({ pressed }) => [
            styles.saveBtn,
            pressed && { backgroundColor: ice.press },
            (saving || loading) && { opacity: 0.45 },
          ]}
        >
          {saving ? (
            <ActivityIndicator color={ice.on} />
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

// Accent (tick) color for a zone's header — mirrors TierBin's tickColor.
function accentFor(zone: Zone): string {
  switch (zone) {
    case 'elite':   return tierColors.elite;
    case 'starter': return tierColors.starter;
    case 'solid':   return tierColors.solid;
    case 'depth':   return tierColors.depth;
    case 'bench':   return tierColors.bench;
    default:        return chalk.faint;
  }
}

// ── Styles ──────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
  },
  title: { ...type.heading, flexShrink: 1 },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
  },
  // Tighter horizontal padding than the Button default so both header
  // actions fit beside the condensed title on narrow screens.
  headerBtn: { paddingHorizontal: space.md },
  // Active state for the Select toggle: pressed-well fill (color change
  // only — no transforms), border stays line-strong via the variant.
  selectBtnActive: {
    paddingHorizontal: space.md,
    backgroundColor: ink.ink3,
  },
  // Standalone tier-header row inside the flat list. Mirrors TierBin's
  // header (tier-colored tick label + mono count) over the ink-0 scaffold.
  tierHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: space.sm,
    marginTop: space.sm,
    marginBottom: space.xs,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  tierHeaderCount: { ...type.data, color: chalk.dim },
  // Player row wrapper in normal (drag) mode. Active (picked-up) row gets
  // a ice ring — border color change only, no shadow/transform lift.
  playerRow: {
    marginBottom: space.xs,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  playerRowActive: {
    borderColor: ice.base,
  },
  // Wrapper around each chip in multi-select mode. Always present so
  // toggling selection doesn't shift the layout.
  chipSelectableWrap: {
    marginBottom: space.xs,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  // Selected-chip state (multi-select mode, issue #16). Volt ring + check
  // icon in the right slot — two signals (color + shape) so selection
  // reads clearly including for color-vision-impaired users.
  chipSelected: {
    borderColor: ice.base,
  },
  // Floating action bar — shown above the save bar when 1+ chips are
  // selected. Up / Down move all selected by one tier; Done exits.
  actionBar: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 76,                       // sits just above the save bar
    paddingVertical: space.sm,
    paddingHorizontal: space.md,
    backgroundColor: ink.ink1,
    borderTopColor: ink.line,
    borderTopWidth: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  actionBarCount: { ...type.bodySm },
  actionBarCountNum: { ...type.data },
  actionBarBtns: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    // Five compact buttons (Up/Down/Tier up/Tier down/Done) overflow a
    // 375pt screen on one line — let them wrap (FB-73).
    flexWrap: 'wrap',
    justifyContent: 'flex-end',
    flexShrink: 1,
  },
  switcher: {
    flexDirection: 'row',
    marginHorizontal: space.lg,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  switcherBtn: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 44,
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  switcherBtnActive: { backgroundColor: ink.ink3 },
  switcherText: { ...type.label },
  switcherTextActive: { color: chalk.base },
  // Copy-tiers-from-other-format action. Sits between the position
  // switcher and the hint line; secondary-button construction (hairline
  // line-strong border, chalk text) with the swap icon.
  copyBtn: {
    marginHorizontal: space.lg,
    marginTop: space.sm,
    paddingHorizontal: space.lg,
    minHeight: 44,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'center',
    gap: space.sm,
  },
  copyBtnText: {
    fontFamily: fonts.uiSemi,
    fontSize: 14,
    color: chalk.base,
  },
  hint: {
    ...type.bodySm,
    textAlign: 'center',
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
  },
  errorText: { ...type.body, color: semantic.neg },
  listContainer: { flex: 1 },
  scroll: {
    padding: space.lg,
    paddingBottom: 96, // room for the Save bar
  },
  emptyBin: {
    ...type.bodySm,
    color: chalk.faint,
    textAlign: 'center',
    paddingVertical: space.sm,
  },
  saveBar: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    padding: space.md,
    backgroundColor: ink.ink0,
    borderTopColor: ink.line,
    borderTopWidth: 1,
  },
  saveBtn: {
    backgroundColor: ice.base,
    borderRadius: radii.sm,
    height: 48,
    alignItems: 'center',
    justifyContent: 'center',
  },
  saveBtnText: {
    fontFamily: fonts.uiSemi,
    fontSize: 14,
    color: ice.on,
  },
});
