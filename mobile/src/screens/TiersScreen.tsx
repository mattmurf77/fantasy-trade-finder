import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  Alert,
  Platform,
  ViewToken,
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
// Old-theme tokens — used only by the FB4 statToggle styles merged from the
// batch-4 branch (which predates the Chalkline re-skin). Kept until those
// styles are Chalkline-ified. See the statToggle block in the StyleSheet.
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import { useNavigation } from '@react-navigation/native';
import { TickLabel, Button, Icon } from '../components/chalkline';
import FormatToggle from '../components/FormatToggle';
import PlayerCard from '../components/PlayerCard';
import TileStats, { StatMode } from '../components/TileStats';
import TierStickyHeader from '../components/TierStickyHeader';
import TierTargetChips from '../components/TierTargetChips';
import Toast from '../components/Toast';
import {
  getRankings,
  getRisersAndFallers,
  saveTiers,
  getTiersStatus,
} from '../api/rankings';
import { copyTiersFromFormat } from '../api/league';
import { autoBucket, TIERS, TIER_LABEL } from '../utils/tierBands';
import { useSession } from '../state/useSession';
import { useScoringFormat } from '../hooks/useScoringFormat';
import type { Position, RankedPlayer, Tier, ScoringFormat, TrendRow } from '../shared/types';

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
  // Root-stack modal (PickAnchor) — nested-tab navigate bubbles up to the
  // root stack; the AuthStack type isn't visible from here, hence the any.
  const navigation = useNavigation<any>();
  const activeFormat = useSession((s) => s.activeFormat);
  // FB #80 — SF/1QB toggle. setFormat flips the server session + local
  // mirrors and marks the choice explicit so the league-default applier
  // (RootNav) won't override it this session.
  const { setFormat, switching: formatSwitching } = useScoringFormat();
  const [position, setPosition] = useState<Position>('QB');
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);

  // FB4-61 — Consensus | You stat-mode toggle. Drives which rank + 30d trend
  // each tile shows. Local screen state, defaults to consensus, no persistence.
  const [statMode, setStatMode] = useState<StatMode>('consensus');

  // FB4-63 — zone of the topmost VISIBLE player row, driven by the list's
  // onViewableItemsChanged. Null until the first viewability callback fires
  // (or when the list is empty). Used to render the pinned tier banner.
  const [stickyZone, setStickyZone] = useState<Zone | null>(null);

  // #81 — full-screen tier board. While expanded, the chrome above the
  // board (title row, format toggle, stat toggle, copy button, hint) is
  // hidden so the board gets the whole screen; the position switcher, the
  // sticky tier banner and the save bar stay. The expand/collapse icon
  // button lives on the board bar in both states.
  const [expanded, setExpanded] = useState(false);
  const toggleExpanded = useCallback(() => {
    setExpanded((e) => !e);
    haptics.selection();
  }, []);

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

  // FB #80 — explicit format switch from the header toggle. On failure the
  // local state is untouched (the toggle stays where it was) — just toast.
  const onFormatChange = useCallback(
    async (fmt: ScoringFormat) => {
      haptics.selection();
      const ok = await setFormat(fmt);
      if (!ok) setToast({ msg: 'Could not switch format', tone: 'warn' });
    },
    [setFormat],
  );

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

  // FB4-61 — 30-day trend source. Reuses the Trends screen's risers/fallers
  // endpoint (FB-04 rank-delta view) rather than inventing a new one. The
  // response is the user's OWN ELO-history rank deltas, so it powers the
  // "You" 30d trend. There is no consensus 30d-trend field on any current
  // payload (see the consensus branch in tileStatsFor below).
  const trendsQuery = useQuery({
    queryKey: ['trends', 'risers-fallers', 30, 50],
    queryFn: () => getRisersAndFallers({ days: 30, topN: 50 }),
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  // player_id → positional 30d rank delta (positive = moved UP). Built from
  // BOTH risers and fallers across all position buckets so any player on the
  // current board can be looked up. Missing players → undefined → "—".
  const trendByPid = useMemo(() => {
    const map = new Map<string, number>();
    const d = trendsQuery.data;
    if (!d) return map;
    const absorb = (rows?: TrendRow[]) => {
      for (const r of rows ?? []) {
        if (r.pos_rank_delta != null) map.set(r.player_id, r.pos_rank_delta);
      }
    };
    // The ALL bucket already spans every position; absorbing it is enough,
    // but absorb the per-position buckets too in case ALL is trimmed.
    (['ALL', 'QB', 'RB', 'WR', 'TE'] as const).forEach((k) => {
      absorb(d.risers?.[k]);
      absorb(d.fallers?.[k]);
    });
    return map;
  }, [trendsQuery.data]);

  // FB4-61 — resolve the two tile stats (rank label + 30d trend) for a player
  // in the active mode. DATA NOTES:
  //  • You rank      → player.rank (the user's positional rank, on payload).
  //  • You 30d trend → trendByPid (risers/fallers rank-delta source).
  //  • Consensus rank → player.adp ?? player.search_rank (consensus-ish signals
  //    already on the rankings payload). FB4-61: a dedicated consensus-rank
  //    field is not in the payload — needs backend.
  //  • Consensus 30d trend → not in any payload. FB4-61: consensus 30d trend
  //    not in payload — needs backend. Renders "—".
  const tileStatsFor = useCallback(
    (player: RankedPlayer): { rankLabel: string | null; trendDelta: number | null } => {
      if (statMode === 'you') {
        return {
          rankLabel: player.rank != null ? `#${player.rank}` : null,
          trendDelta: trendByPid.get(player.id) ?? null,
        };
      }
      // Consensus mode.
      const adp = player.adp;
      const searchRank = player.search_rank;
      let rankLabel: string | null = null;
      if (adp != null) rankLabel = `ADP ${Math.round(adp)}`;
      else if (searchRank != null) rankLabel = `#${searchRank}`;
      return { rankLabel, trendDelta: null };
    },
    [statMode, trendByPid],
  );

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
  // of rank position. Complements bulkMove (one RANK at a time). Movement
  // semantics live in the shared moveTierByOne helper below (also used by
  // the per-tile chevron buttons, #90).
  const bulkTierMove = useCallback(
    (direction: 'up' | 'down') => {
      if (selectedIds.size === 0) return;
      bucketsDirtyRef.current = true;
      setBuckets((prev) => moveTierByOne(prev, selectedIds, direction));
      haptics.success();
    },
    [selectedIds],
  );

  // ── Per-tile tier step (#90) ────────────────────────────────────────
  // Move ONE player one whole tier up/down from the chevron buttons on its
  // tile — no drag, no multi-select. Reuses the multi-select "Tier up /
  // Tier down" movement rules via moveTierByOne: up lands at the BOTTOM of
  // the higher tier, down at the TOP of the lower tier, clamps at elite /
  // bench, and never moves a player into or out of `unassigned` (#68).
  const singleTierMove = useCallback((pid: string, direction: 'up' | 'down') => {
    bucketsDirtyRef.current = true;
    setBuckets((prev) => moveTierByOne(prev, new Set([pid]), direction));
    haptics.selection();
  }, []);

  // ── Quick tier-move (multi-select) — FB4-62 ─────────────────────────
  // Send EVERY selected player straight to `target`, appended to the end of
  // that tier in their current flattened (top-to-bottom) order. Non-selected
  // players keep their tier + within-tier order. Selection persists so the
  // user can fine-tune with ↑/↓. `unassigned` is untouched (mirrors bulkMove).
  const moveSelectedToTier = useCallback(
    (target: Tier) => {
      if (selectedIds.size === 0) return;
      bucketsDirtyRef.current = true;
      setBuckets((prev) => {
        // Gather selected players in current flattened tier order so their
        // relative order is preserved when appended to the target tier.
        const movers: RankedPlayer[] = [];
        for (const t of TIERS) {
          for (const p of prev[t]) if (selectedIds.has(p.id)) movers.push(p);
        }
        if (movers.length === 0) return prev;

        const next = emptyBuckets();
        next.unassigned = [...prev.unassigned];
        // Each non-target tier keeps only its non-selected players.
        for (const t of TIERS) {
          next[t] = prev[t].filter((p) => !selectedIds.has(p.id));
        }
        // Append the movers to the END of the target tier.
        next[target] = [...next[target], ...movers];
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
  // FB4-63 — any players on the board at all? Gates the sticky tier banner
  // (empty state hides it).
  const hasRankings = useMemo(
    () => TIERS.some((t) => buckets[t].length > 0) || buckets.unassigned.length > 0,
    [buckets],
  );

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

  // ── Sticky tier header (FB4-63) ─────────────────────────────────────
  // Track the zone of the topmost VISIBLE row off the list's viewability
  // callback — NOT a separate scroll/pan listener (which would fight the
  // drag gesture). RN requires onViewableItemsChanged + viewabilityConfig
  // to be referentially stable for the list's lifetime, so both live in
  // refs. We freeze updates while a drag is active so the banner doesn't
  // flicker as rows reorder mid-drag.
  const isDraggingRef = useRef(false);
  const viewabilityConfigRef = useRef({
    // A row counts as "viewable" the moment any pixel is on screen, so the
    // topmost partially-visible row drives the banner.
    itemVisiblePercentThreshold: 0,
    minimumViewTime: 0,
  });
  const onViewableItemsChangedRef = useRef(
    ({ viewableItems }: { viewableItems: ViewToken[] }) => {
      if (isDraggingRef.current) return;
      if (!viewableItems.length) return;
      // Prefer the first visible PLAYER row's zone; fall back to the first
      // visible row's zone (a header when a section boundary is at the top).
      const firstPlayer = viewableItems.find(
        (v) => (v.item as Row)?.kind === 'player',
      );
      const pick = firstPlayer ?? viewableItems[0];
      const zone = (pick?.item as Row | undefined)?.zone;
      if (zone) setStickyZone(zone);
    },
  );

  // ── Drag handler ───────────────────────────────────────────────────
  // Rebuild buckets by walking the post-drag flat order: each header row
  // re-anchors the "current zone", and every player row that follows
  // lands in that zone. Then reconcile clearedPids — players now in the
  // pool are cleared; players in any tier must drop out of the cleared
  // set (drag-out-then-back-in within one session).
  const onDragBegin = useCallback(() => {
    isDraggingRef.current = true;
  }, []);
  const onDragEnd = useCallback(
    ({ data }: DragEndParams<Row>) => {
      bucketsDirtyRef.current = true;
      isDraggingRef.current = false;
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
      // #83/#84 — tiles carry the TIER encoding explicitly (TierChalkBadge
      // via PlayerCard's `tier` prop), derived from the tile's CURRENT zone.
      // Without it the only per-tile color was the 3px POSITION rail, which
      // is constant across a position page (and happens to share hexes with
      // tier colors on some pages) — so tier colors read as present on some
      // position pages and missing on others (RB). Zone-derived, never
      // hardcoded per position (docs/cross-client-invariants.md).
      const zoneTier: Tier | null = item.zone === 'unassigned' ? null : item.zone;
      // FB4-61 — resolve the tile's two stats for the active mode. Rendered
      // inside the pointerEvents="none" wrapper so it never captures touches
      // away from the drag / selection Pressable.
      const stats = tileStatsFor(item.player);

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
                tier={zoneTier}
                rightSlot={
                  isSelected ? (
                    <Icon name="check" size={16} color={ice.base} />
                  ) : undefined
                }
              />
              <TileStats rankLabel={stats.rankLabel} trendDelta={stats.trendDelta} />
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
      // #90 — the chevron column on the right sits OUTSIDE that wrapper so its
      // own Pressables stay tappable; a press there becomes the touch
      // responder, so it can't accidentally start a long-press drag.
      return (
        <Pressable
          onLongPress={drag}
          delayLongPress={DRAG_ACTIVATION_MS}
          disabled={isActive}
          style={[styles.playerRow, isActive && styles.playerRowActive]}
        >
          <View pointerEvents="none" style={styles.rowBody}>
            <PlayerCard player={item.player} compact tier={zoneTier} />
            <TileStats rankLabel={stats.rankLabel} trendDelta={stats.trendDelta} />
          </View>
          {/* #90 — per-tile tier step buttons (Icon Button spec: 32×32,
              radius sm, chalk-dim glyph, pressed = ink-3 fill). Hidden for
              unassigned tiles — tier stepping never crosses the pool
              boundary, matching the multi-select Tier up/down buttons. */}
          {zoneTier ? (
            <View style={styles.tierStepBtns}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`Move ${item.player.name} up a tier`}
                disabled={isActive || zoneTier === 'elite'}
                hitSlop={4}
                onPress={() => singleTierMove(item.player.id, 'up')}
                style={({ pressed }) => [
                  styles.tierStepBtn,
                  pressed && styles.tierStepBtnPressed,
                  zoneTier === 'elite' && styles.tierStepBtnDisabled,
                ]}
              >
                <Icon name="chevron-up" size={16} />
              </Pressable>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`Move ${item.player.name} down a tier`}
                disabled={isActive || zoneTier === 'bench'}
                hitSlop={4}
                onPress={() => singleTierMove(item.player.id, 'down')}
                style={({ pressed }) => [
                  styles.tierStepBtn,
                  pressed && styles.tierStepBtnPressed,
                  zoneTier === 'bench' && styles.tierStepBtnDisabled,
                ]}
              >
                <Icon name="chevron-down" size={16} />
              </Pressable>
            </View>
          ) : null}
        </Pressable>
      );
    },
    [buckets, multiSelect, selectedIds, toggleSelected, tileStatsFor, singleTierMove],
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

      {/* #81 — header + chrome hidden while the board is expanded. */}
      {expanded ? null : (
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
          {/* Pick Anchor wizard — value players in draft-pick terms; the
              anchors pin Elo overrides so tiers re-bucket on return. */}
          <Button
            variant="ghost"
            compact
            label="Anchors"
            onPress={() => navigation.navigate('PickAnchor')}
            style={styles.headerBtn}
          />
        </View>
      </View>
      )}

      {/* FB #80 — SF/1QB scoring-format toggle. Defaults to the selected
          league's detected format (useLeagueFormatDefault in RootNav);
          tapping here is an explicit in-session override to view/edit the
          other format's rankings. Hidden while expanded (#81). */}
      {expanded ? null : (
      <View style={styles.formatRow}>
        <FormatToggle
          value={activeFormat}
          onChange={onFormatChange}
          disabled={formatSwitching}
        />
      </View>
      )}

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

      {/* FB4-61 — Consensus | You stat toggle. Switches the rank + 30d
          trend each tile shows. Default Consensus; local state only.
          Hidden while expanded (#81). */}
      {expanded ? null : (
      <View style={styles.statToggle}>
        {([
          { key: 'consensus' as StatMode, label: 'Consensus' },
          { key: 'you' as StatMode, label: 'You' },
        ]).map(({ key, label }) => {
          const isActive = statMode === key;
          return (
            <Pressable
              key={key}
              onPress={() => {
                if (statMode !== key) { setStatMode(key); haptics.selection(); }
              }}
              style={({ pressed }) => [
                styles.statToggleBtn,
                isActive && styles.statToggleBtnActive,
                pressed && { opacity: 0.7 },
              ]}
            >
              <Text
                style={[styles.statToggleText, isActive && styles.statToggleTextActive]}
              >
                {label}
              </Text>
            </Pressable>
          );
        })}
      </View>
      )}

      {/* Copy tier list from the OTHER scoring format. Mirrors web's
          `copy-tiers-btn` — the from-format reads as a label so the user
          knows EXACTLY which format they're pulling tiers from. Disabled
          while the copy is in flight. Composed inline (secondary-button
          tokens) because the Button primitive has no icon/spinner slot.
          Hidden while expanded (#81). */}
      {expanded ? null : (
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
      )}

      {/* Board bar — the hint (collapsed only) + the #81 expand/collapse
          icon button. The button keeps the same slot in both states so
          the toggle doesn't jump under the user's finger. */}
      <View style={styles.boardBar}>
        {expanded ? (
          <View style={styles.boardBarSpacer} />
        ) : (
          <Text style={styles.hint}>
            {multiSelect
              ? 'Tap chips to select. Use the bar below to move all selected up or down.'
              : 'Long-press + drag to re-rank, or tap a tile’s arrows to move it a tier. "Select" moves several at once.'}
          </Text>
        )}
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={expanded ? 'Exit full-screen board' : 'Expand board to full screen'}
          hitSlop={4}
          onPress={toggleExpanded}
          style={({ pressed }) => [
            styles.expandBtn,
            pressed && styles.tierStepBtnPressed,
          ]}
        >
          <Icon name={expanded ? 'collapse' : 'expand'} size={20} />
        </Pressable>
      </View>

      {/* FB4-63 — pinned tier banner. Sits between the hint and the list,
          shows the tier of the topmost VISIBLE player. Hidden in the
          empty/loading/error states (no rankings → nothing to anchor to). */}
      {!loading && !rankingsQuery.isError && hasRankings && stickyZone ? (
        <TierStickyHeader
          label={stickyZone === 'unassigned' ? 'Unassigned' : TIER_LABEL[stickyZone]}
          accent={accentFor(stickyZone)}
          count={buckets[stickyZone].length}
        />
      ) : null}

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
          onDragBegin={onDragBegin}
          onDragEnd={onDragEnd}
          // FB4-63 — drive the sticky tier banner off viewability (NOT a
          // competing scroll listener). Both props are referentially stable
          // refs because RN throws if they change between renders.
          onViewableItemsChanged={onViewableItemsChangedRef.current}
          viewabilityConfig={viewabilityConfigRef.current}
          // #57: drag starts from a long-press (onLongPress={drag}), so a
          // small activationDistance only let an ordinary vertical scroll
          // swipe cross the 5px threshold and steal the touch into a drag.
          // Raised to 18px so normal scrolling stays a scroll; the long-
          // press still initiates the drag and edge auto-scroll (library
          // autoscrollThreshold/Speed defaults, untouched) still works.
          activationDistance={18}
          // #82: keep the lifted tile anchored to the touch point. Without
          // this the library clamps the hover tile inside the list
          // container, so picking up a partially-visible tile at the top/
          // bottom of the page snaps it into view immediately. Edge
          // auto-scroll engagement is also gated on actual drag movement
          // toward the edge — see patches/react-native-draggable-flatlist.
          dragItemOverflow
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
          {/* FB4-62 — quick tier-move: tap a tier chip to send every selected
              player straight into that tier (appended, order preserved).
              Selection persists so the ↑/↓ / Tier up/down controls can still
              fine-tune. The secondary swipe-to-reveal gesture stays deferred
              (drag-capture conflict risk with the draggable list). */}
          <TierTargetChips accentFor={accentFor} onPick={moveSelectedToTier} />
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

// Move every player in `ids` one whole tier in `direction`, preserving
// relative order. Placement inside the target tier: moving up appends to
// the BOTTOM of the higher tier (they're its newest/weakest members);
// moving down inserts at the TOP of the lower tier (its strongest).
// Clamps at elite / bench; `unassigned` is never a source or target.
// Shared by the multi-select "Tier up / Tier down" bar (FB-73) and the
// per-tile chevron buttons (#90). Returns `prev` unchanged when every
// mover is already clamped at the boundary (no re-render).
function moveTierByOne(
  prev: Record<Zone, RankedPlayer[]>,
  ids: ReadonlySet<string>,
  direction: 'up' | 'down',
): Record<Zone, RankedPlayer[]> {
  const next = emptyBuckets();
  next.unassigned = [...prev.unassigned];
  // Split each tier into keepers and movers, preserving order.
  const movers: Record<Tier, RankedPlayer[]> = {
    elite: [], starter: [], solid: [], depth: [], bench: [],
  };
  for (const t of TIERS) {
    for (const p of prev[t]) {
      if (ids.has(p.id)) movers[t].push(p);
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
  // Row layout: card body fills the width, the #90 tier-step chevron
  // column sits in a fixed gutter on the right.
  playerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: space.xs,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  playerRowActive: {
    borderColor: ice.base,
  },
  rowBody: { flex: 1 },
  // #90 — per-tile tier step controls. Icon Button spec (components.md →
  // Buttons → Icon): 32×32, radius sm, chalk-dim glyph, pressed ink-3 fill,
  // disabled 45% opacity.
  tierStepBtns: {
    width: 32,
    marginLeft: space.xs,
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.xs,
  },
  tierStepBtn: {
    width: 32,
    height: 32,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tierStepBtnPressed: { backgroundColor: ink.ink3 },
  tierStepBtnDisabled: { opacity: 0.45 },
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
  // selected. Holds the FB4-62 tier-target chip row on top + the Up/Down/
  // Done controls row below (so it's a column container now).
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
  },
  // Up / Down / Done controls row inside the action bar.
  actionBarMain: {
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
  // FB #80 — row hosting the SF/1QB FormatToggle, between the header and
  // the position switcher (consistent slot with RankScreen's).
  formatRow: {
    marginHorizontal: space.lg,
    marginBottom: space.sm,
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
  // FB4-61 — Consensus | You segmented toggle. Compact mirror of the position
  // switcher; sits just below it. (Old-theme tokens; Chalkline-ify as a
  // visual follow-up, matching the FB4 components merged in the same batch.)
  statToggle: {
    flexDirection: 'row',
    gap: spacing.xs,
    marginHorizontal: spacing.lg,
    marginTop: spacing.sm,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: 4,
  },
  statToggleBtn: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: spacing.xs,
    borderRadius: radius.sm,
  },
  statToggleBtnActive: { backgroundColor: 'rgba(79,124,255,0.14)' },
  statToggleText: { color: colors.muted, fontSize: fontSize.xs, fontWeight: '700' },
  statToggleTextActive: { color: colors.accent },
  // Copy-tiers-from-other-format action. Secondary-button construction
  // (hairline line-strong border, chalk text) with the swap icon.
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
  // Board bar — hint + the #81 expand/collapse icon button in one row
  // between the chrome and the board. Keeps the toggle in a stable slot
  // in both states.
  boardBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.lg,
    paddingVertical: space.xs,
  },
  boardBarSpacer: { flex: 1 },
  hint: {
    ...type.bodySm,
    flex: 1,
    textAlign: 'center',
    paddingVertical: space.xs,
  },
  // #81 — expand/collapse toggle. Icon Button spec (32×32, radius sm,
  // chalk-dim glyph, pressed ink-3 fill) — shares tierStepBtnPressed.
  expandBtn: {
    width: 32,
    height: 32,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
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
