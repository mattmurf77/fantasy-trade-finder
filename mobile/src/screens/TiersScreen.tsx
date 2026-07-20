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
  TextInput,
  RefreshControl,
  LayoutChangeEvent,
  AccessibilityInfo,
  type AccessibilityActionEvent,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import DraggableFlatList, {
  RenderItemParams,
  DragEndParams,
} from 'react-native-draggable-flatlist';
import type { FlatList } from 'react-native-gesture-handler';
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
  DRAG_ACTIVATION_DISTANCE,
} from '../theme/chalkline';
import { useNavigation, useIsFocused } from '@react-navigation/native';
import { TickLabel, Button, Icon } from '../components/chalkline';
import { useFlag } from '../state/useFeatureFlags';
import { setPinnedBottomBarHeight } from '../components/FeedbackFAB';
import FormatToggle from '../components/FormatToggle';
import PlayerCard from '../components/PlayerCard';
import TileStats from '../components/TileStats';
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
import { autoBucket, autoBucketMixed, TIERS, TIER_LABEL } from '../utils/tierBands';
import { valueForElo } from '../utils/playerValue';
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

// #132 — the board can show a single position OR the merged cross-position
// "All" board. 'ALL' is a VIEW, not a server-side position: reads come from
// the unfiltered /api/rankings payload and every mutation is routed to the
// owning position's per-position pathway (see saveMutation/resetMutation) —
// /api/tiers/save only accepts QB/RB/WR/TE and silently drops foreign pids,
// so a merged board must never be posted to a single position.
type BoardTab = Position | 'ALL';
const BOARD_TABS: BoardTab[] = [...POSITIONS, 'ALL'];

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

// S8 PRD-01 — VoiceOver custom actions on player rows: "Move to <tier>"
// mirrors the multi-select tier-target chips (the no-drag path) so a
// screen-reader user can complete a tier move without the drag gesture.
const TIER_A11Y_ACTIONS: { name: string; label: string }[] = TIERS.map((t) => ({
  name: `tier:${t}`,
  label: `Move to ${TIER_LABEL[t]}`,
}));

// Offset of the multi-select action bar's bottom edge from the screen
// bottom (styles.actionBar.bottom) — it sits just above the save bar.
// Shared with the FAB-offset math so the two never drift.
const ACTION_BAR_BOTTOM = 76;

export default function TiersScreen() {
  const queryClient = useQueryClient();
  // Sibling Rank-stack routes (QuickSetTiers) — the stack's param types
  // aren't exported, hence the any.
  const navigation = useNavigation<any>();
  const activeFormat = useSession((s) => s.activeFormat);
  // FB #80 — SF/1QB toggle. setFormat flips the server session + local
  // mirrors and marks the choice explicit so the league-default applier
  // (RootNav) won't override it this session.
  const { setFormat, switching: formatSwitching } = useScoringFormat();
  const [position, setPosition] = useState<BoardTab>('QB');
  const isAllView = position === 'ALL';
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);

  // Teardown flags. All default false → byte-identical behavior.
  //   ux.touch_polish (S3 PRD-01/04): lift haptic, drag-end downgrade,
  //     expand-button 44pt hitSlop, pull-to-refresh, FAB offset/clearance.
  //   ux.board_search (S7 PRD-04): name search with scroll-to + highlight.
  //   visual.chalkline_cleanup (S2 PRD-04): faint→dim on content-carrying
  //     text (Unassigned accent, empty-bin hint).
  const touchPolish = useFlag('ux.touch_polish');
  const boardSearch = useFlag('ux.board_search');
  const cleanup = useFlag('visual.chalkline_cleanup');

  // FB4-63 — zone of the topmost VISIBLE player row, driven by the list's
  // onViewableItemsChanged. Null until the first viewability callback fires
  // (or when the list is empty). Used to render the pinned tier banner.
  const [stickyZone, setStickyZone] = useState<Zone | null>(null);

  // #81 — full-screen tier board. While expanded, the chrome above the
  // board (title row, format toggle, copy button, hint) is
  // hidden so the board gets the whole screen; the position switcher, the
  // sticky tier banner and the save bar stay. The expand/collapse icon
  // button lives on the board bar in both states.
  const [expanded, setExpanded] = useState(false);
  const toggleExpanded = useCallback(() => {
    setExpanded((e) => !e);
    haptics.selection();
  }, []);

  // tiers[position] = { firsts_4plus: [player...], firsts_3: [...], ..., unassigned: [...] }
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
  // #132 — the All view reads the UNFILTERED rankings payload. Query key
  // deliberately matches ManualRanksScreen's overall board
  // (['rankings', fmt, 'all'] ⇄ getRankings(null)) so the two share a cache.
  const rankingsQuery = useQuery({
    queryKey: ['rankings', activeFormat, isAllView ? 'all' : position],
    queryFn: () => getRankings(isAllView ? null : position),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  });

  const tiersStatusQuery = useQuery({
    queryKey: ['tiers-status'],
    queryFn: getTiersStatus,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  // FB4-61 — 30-day trend source for the "You" side. Reuses the Trends
  // screen's risers/fallers endpoint (FB-04 rank-delta view) rather than
  // inventing a new one; the response is the user's OWN ELO-history rank
  // deltas. The consensus side's rank + 30d trend ride the rankings payload
  // itself (see tileStatsFor below).
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

  // #65 — resolve the tile stats for a player. Both the user's and the
  // consensus values render side by side (the FB4-61 Consensus | You toggle
  // is gone). Same two stats for both sides (#61): rank + 30d trend.
  //  • You rank        → player.rank (the user's positional rank, on payload).
  //  • You 30d trend   → trendByPid (risers/fallers rank-delta source).
  //  • Cons rank       → player.consensus_pos_rank (rank within position by
  //    consensus value — replaced the old ADP/search_rank proxy).
  //  • Cons 30d trend  → player.consensus_pos_rank_delta_30d. Absent until
  //    the backend has a prior-day consensus snapshot in the 30d window —
  //    TileStats omits the glyph when null.
  const tileStatsFor = useCallback(
    (player: RankedPlayer): {
      youRankLabel: string | null;
      youTrendDelta: number | null;
      consensusRankLabel: string | null;
      consensusTrendDelta: number | null;
    } => ({
      youRankLabel: player.rank != null ? `#${player.rank}` : null,
      youTrendDelta: trendByPid.get(player.id) ?? null,
      consensusRankLabel:
        player.consensus_pos_rank != null ? `#${player.consensus_pos_rank}` : null,
      consensusTrendDelta: player.consensus_pos_rank_delta_30d ?? null,
    }),
    [trendByPid],
  );

  // #132 — positional ranks for the All board. The unfiltered payload's
  // `rank` is the OVERALL rank, so the per-position rank (QB4, WR12, …)
  // is derived client-side: 1-based index among same-position players in
  // Elo order. Mirrors ManualRanksScreen's posRanks map. Null when a
  // single position is shown (the payload's rank is already positional).
  const allPosRanks = useMemo(() => {
    if (position !== 'ALL') return null;
    const map = new Map<string, number>();
    const data = rankingsQuery.data?.rankings as RankedPlayer[] | undefined;
    if (!data) return map;
    const counts: Partial<Record<string, number>> = {};
    const sorted = [...data].sort((a, b) => (b.elo ?? 0) - (a.elo ?? 0));
    for (const p of sorted) {
      const n = (counts[p.position] ?? 0) + 1;
      counts[p.position] = n;
      map.set(p.id, n);
    }
    return map;
  }, [position, rankingsQuery.data]);

  const saveMutation = useMutation({
    // Wrap the tier save in a Sentry span — measures end-to-end latency
    // including the per-position payload build + the network round-trip.
    // No-op when Sentry isn't initialized.
    mutationFn: () =>
      startSpan({ name: 'tiers.save', op: 'mutation' }, () => {
        // Pass the accumulated clearedPids so the backend can DELETE the
        // matching tier_overrides rows for this position. Filter out any
        // ID that's currently sitting in a tier (defensive — the user
        // may have dragged-out then dragged-back-in within the same
        // session); we never want a re-saved tier assignment to be
        // simultaneously cleared.
        const stillAssigned = new Set<string>();
        for (const t of TIERS) for (const p of buckets[t]) stillAssigned.add(p.id);
        const cleared = Array.from(clearedPids).filter((id) => !stillAssigned.has(id));

        if (!isAllView) {
          // Only send the real tiers — `unassigned` isn't a tier on the server.
          const payload: Record<string, string[]> = {};
          for (const t of TIERS) payload[t] = buckets[t].map((p) => p.id);
          return saveTiers(position, payload, cleared);
        }

        // #132 All view — /api/tiers/save is per-position (QB/RB/WR/TE
        // only, and apply_tiers drops pids outside that position's pool),
        // so the merged board is SPLIT by each player's own position and
        // routed as one save per position. Tier membership + per-position
        // within-tier order round-trip exactly; the cross-position
        // interleave WITHIN a tier is re-derived from the band Elos on
        // reload (each position's list spreads across the same uniform
        // band independently) — a documented All-view limitation, never
        // data loss.
        const perPos: Record<Position, Record<string, string[]>> = {
          QB: {}, RB: {}, WR: {}, TE: {},
        };
        for (const pos of POSITIONS) {
          for (const t of TIERS) perPos[pos][t] = [];
        }
        for (const t of TIERS) {
          // Player.position is `Position | string`; an off-enum value has
          // no per-position save pathway, so the `?.` guard drops it
          // rather than mis-routing (the pool only holds QB/RB/WR/TE).
          for (const p of buckets[t]) perPos[p.position as Position]?.[t]?.push(p.id);
        }
        // Route cleared pids by owning position (looked up from the loaded
        // payload + the pool) — a cleared pid posted to the wrong position
        // would be silently ignored server-side.
        const posById = new Map<string, Position>();
        for (const p of (rankingsQuery.data?.rankings as RankedPlayer[] | undefined) ?? []) {
          posById.set(p.id, p.position as Position);
        }
        for (const p of buckets.unassigned) posById.set(p.id, p.position as Position);
        const clearedByPos: Record<Position, string[]> = { QB: [], RB: [], WR: [], TE: [] };
        for (const id of cleared) {
          const pos = posById.get(id);
          if (pos) clearedByPos[pos]?.push(id);
        }
        const calls = POSITIONS.filter(
          (pos) =>
            TIERS.some((t) => perPos[pos][t].length > 0) ||
            clearedByPos[pos].length > 0,
        ).map((pos) => saveTiers(pos, perPos[pos], clearedByPos[pos]));
        return Promise.all(calls);
      }),
    onSuccess: () => {
      setToast({ msg: 'Tiers saved', tone: 'success' });
      queryClient.invalidateQueries({ queryKey: ['tiers-status'] });
      queryClient.invalidateQueries({ queryKey: ['progress'] });
      // Tier saves rewrite per-position ELO overrides on the backend,
      // which the Overall / Manual / Tiers screens all read via the
      // `['rankings', ...]` family. Scope to the saved format+position
      // + 'all' to avoid evicting unrelated caches. An All-view save
      // touched every position, so it invalidates the whole format prefix.
      if (isAllView) {
        queryClient.invalidateQueries({ queryKey: ['rankings', activeFormat] });
      } else {
        queryClient.invalidateQueries({ queryKey: ['rankings', activeFormat, position] });
        queryClient.invalidateQueries({ queryKey: ['rankings', activeFormat, 'all'] });
      }
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
  // Pulls the user's board from the other format (e.g. SF TEP when
  // currently on 1QB PPR) and value-maps it onto the active format
  // (#124): players keep the user's per-position rank order, but each
  // player's value (and therefore tier label) is re-seeded from the
  // TARGET format's consensus at that rank — QBs shift most, by design.
  // Destructive: replaces existing target-format tier overrides
  // wholesale, so we confirm via Alert first (#139). On success we
  // refetch the per-position rankings + tier-status caches so the
  // screen re-renders with the new state.
  const copyMutation = useMutation({
    mutationFn: ({ from, to }: { from: ScoringFormat; to: ScoringFormat }) =>
      copyTiersFromFormat(from, to),
    onSuccess: (data) => {
      if (!data?.ok) {
        setToast({ msg: data?.error || 'Copy failed', tone: 'warn' });
        return;
      }
      const n = data.total ?? 0;
      setToast({ msg: `Copied ${n} players — values adjusted`, tone: 'success' });
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

    // #132 — the All board buckets each player by ITS OWN position's
    // thresholds (bands are uniform today; autoBucketMixed keeps the merged
    // board honest if they ever diverge).
    const bucketed =
      position === 'ALL'
        ? autoBucketMixed(players, fmt)
        : autoBucket(players, position, fmt);
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
  // at the top of the first tier / bottom of `waivers`.
  const bulkMove = useCallback(
    (direction: 'up' | 'down') => {
      if (selectedIds.size === 0) return;
      bucketsDirtyRef.current = true;
      setBuckets((prev) => {
        // 1. Flatten the real tiers into one ordered list.
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
  // semantics live in the shared moveTierByOne helper below. With the #90
  // per-tile chevrons removed (1.5.4 #98), this + the FB4-62 tier-target
  // chips are the no-drag paths for moving players between tiers.
  const bulkTierMove = useCallback(
    (direction: 'up' | 'down') => {
      if (selectedIds.size === 0) return;
      bucketsDirtyRef.current = true;
      setBuckets((prev) => moveTierByOne(prev, selectedIds, direction));
      haptics.success();
    },
    [selectedIds],
  );

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

  // ── Single-player tier move (S8 PRD-01, VoiceOver custom actions) ──
  // Mirrors moveSelectedToTier's placement semantics (append to the END
  // of the target tier) for ONE player, and — like the drag path — also
  // accepts a pool (unassigned) source, reconciling clearedPids the same
  // way onDragEnd does. Only reachable via the row custom actions, so
  // touch behavior is unchanged.
  const movePlayerToTier = useCallback((player: RankedPlayer, target: Tier) => {
    bucketsDirtyRef.current = true;
    setBuckets((prev) => {
      const next = emptyBuckets();
      next.unassigned = prev.unassigned.filter((p) => p.id !== player.id);
      for (const t of TIERS) next[t] = prev[t].filter((p) => p.id !== player.id);
      next[target] = [...next[target], player];
      return next;
    });
    // The player now sits in a tier — drop any pending clear (drag-out-
    // then-move-back-in within one session), matching onDragEnd.
    setClearedPids((prev) => {
      if (!prev.has(player.id)) return prev;
      const out = new Set(prev);
      out.delete(player.id);
      return out;
    });
    haptics.success();
    AccessibilityInfo.announceForAccessibility(
      `${player.name} moved to ${TIER_LABEL[target]}`,
    );
  }, []);

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
  // Walk unassigned first, then the tiers in TIERS order. Every
  // TIER always contributes a header (so empty tiers stay visible and
  // droppable); a tier with no players contributes a single muted
  // `empty` placeholder row instead of player rows. #105: the Unassigned
  // section (header + bin) is omitted entirely while the pool is empty —
  // it reappears whenever players land back in the pool (the buckets
  // rebuild after resets/clears repopulates it the same way).
  const listData: Row[] = useMemo(() => {
    const rows: Row[] = [];
    const zones: Zone[] =
      buckets.unassigned.length > 0 ? ['unassigned', ...TIERS] : [...TIERS];
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

  // ── Board search (S7 PRD-04, flag ux.board_search) ──────────────────
  // Scroll-to + highlight over the loaded flat list — NOT a filter, for
  // the same reason as ManualRanks: the drag handler rebuilds buckets by
  // walking the FULL post-drag row order (headers re-anchor zones), so a
  // name-filtered view would have no well-defined drop semantics. The
  // first matching PLAYER row scrolls into view with the dense card's ice
  // locate ring.
  const [search, setSearch] = useState('');
  const [searchFocused, setSearchFocused] = useState(false);
  const listRef = useRef<FlatList<Row>>(null);
  const searchQuery = search.trim().toLowerCase();
  const highlightIndex = useMemo(() => {
    if (!boardSearch || searchQuery.length === 0) return -1;
    return listData.findIndex(
      (r) => r.kind === 'player' && r.player.name.toLowerCase().includes(searchQuery),
    );
  }, [boardSearch, searchQuery, listData]);
  const highlightRow = highlightIndex >= 0 ? listData[highlightIndex] : null;
  const highlightPid =
    highlightRow && highlightRow.kind === 'player' ? highlightRow.player.id : null;

  useEffect(() => {
    if (highlightIndex < 0) return;
    listRef.current?.scrollToIndex({
      index: highlightIndex,
      animated: true,
      viewPosition: 0.3,
    });
  }, [highlightIndex]);

  // ── FAB offset reporting (S3 PRD-01, flag ux.touch_polish) ──────────
  // Report the pinned bottom-bar footprint (save bar, plus the multi-
  // select action bar when visible) to the feedback FAB so it rises above
  // the primary CTA instead of covering its right edge. Report only while
  // FOCUSED — this screen stays mounted when the user switches tabs, and
  // an unfocused board must not offset the FAB elsewhere. The FAB ignores
  // reports while ux.touch_polish is off (byte-identical rendering).
  const isFocused = useIsFocused();
  const [saveBarH, setSaveBarH] = useState(0);
  const [actionBarH, setActionBarH] = useState(0);
  const actionBarVisible = multiSelect && selectedIds.size > 0;
  useEffect(() => {
    const occupied = Math.max(
      saveBarH,
      actionBarVisible ? ACTION_BAR_BOTTOM + actionBarH : 0,
    );
    setPinnedBottomBarHeight('tiers', isFocused ? occupied : 0);
  }, [isFocused, saveBarH, actionBarH, actionBarVisible]);
  useEffect(() => () => setPinnedBottomBarHeight('tiers', 0), []);

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
      if (!zone) return;
      // #67 — gate: the banner only appears once the current section's own
      // INLINE header has scrolled off the top. While that header is still
      // on screen (page load, or scrolled back to the very top) the banner
      // is hidden — the inline header already labels the section.
      const headerOnScreen = viewableItems.some((v) => {
        const it = v.item as Row | undefined;
        return it?.kind === 'header' && it.zone === zone;
      });
      setStickyZone(headerOnScreen ? null : zone);
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
    // S3 PRD-04 (flag ux.touch_polish) — tactile lift confirmation for the
    // 220ms long-press pickup (scroll-vs-drag was ambiguous without it).
    if (touchPolish) haptics.pickup();
  }, [touchPolish]);
  const onDragEnd = useCallback(
    ({ data, from, to }: DragEndParams<Row>) => {
      isDraggingRef.current = false;
      // #105 — the Unassigned section is omitted from the list while the
      // pool is empty, so rows dropped ABOVE the first header can't mean
      // "into the pool" then: they belong to the topmost rendered tier
      // (TIERS[0]). When the pool section IS rendered, the pre-header zone
      // stays `unassigned` as before.
      const poolRendered = data.some(
        (r) => r.kind === 'header' && r.zone === 'unassigned',
      );
      const topZone: Zone = poolRendered ? 'unassigned' : TIERS[0];
      // #68 — one-directional pool guard, matching the tier-move path
      // (moveTierByOne): a TIERED player can never land in `unassigned`;
      // dragging FROM the pool INTO a tier stays allowed. `data[to]` is the
      // dragged row at its landing index; its `zone` is the PRE-drag zone
      // (rows are built from the last-committed buckets). The landing zone
      // is the nearest header at/above the landing index. On reject we
      // leave `buckets` untouched, so the controlled list re-renders the
      // row back where it came from (snap-back) — light haptic + toast.
      const moved = from !== to ? data[to] : undefined;
      if (moved?.kind === 'player' && moved.zone !== 'unassigned') {
        let landing: Zone = topZone;
        for (let i = to - 1; i >= 0; i--) {
          const r = data[i];
          if (r.kind === 'header') {
            landing = r.zone;
            break;
          }
        }
        if (landing === 'unassigned') {
          haptics.warning();
          setToast({ msg: 'Tiered players can’t move to Unassigned', tone: 'warn' });
          return;
        }
      }
      bucketsDirtyRef.current = true;
      let zone: Zone = topZone;
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
      // S3 PRD-04 — drag end is routine: impact-light, not success().
      // success() is reserved for server-confirmed outcomes (the save
      // mutation / reset); firing it on every drop diluted its meaning.
      if (touchPolish) haptics.swipe();
      else haptics.success();
    },
    [touchPolish],
  );

  const renderItem = useCallback(
    ({ item, drag, isActive }: RenderItemParams<Row>) => {
      if (item.kind === 'header') {
        const accent = accentFor(item.zone, cleanup);
        const label = item.zone === 'unassigned' ? 'Unassigned' : TIER_LABEL[item.zone];
        const count = buckets[item.zone].length;
        // #58 (cozy) — header aggregates: count sits next to the label,
        // summed 0–10k value right-aligned (tier zones with players only).
        const sum =
          item.zone !== 'unassigned' && count > 0
            ? buckets[item.zone].reduce((acc, p) => acc + (valueForElo(p.elo) ?? 0), 0)
            : null;
        return (
          <View style={styles.tierHeader}>
            <View style={styles.tierHeaderLeft}>
              {/* Tier labels ARE pick terms now ("4+ 1sts" / "1st" / …) —
                  the former #103 sublabel is folded into the name. */}
              <TickLabel color={accent}>{label}</TickLabel>
              <Text style={styles.tierHeaderCount}>{count}</Text>
            </View>
            {sum != null ? (
              <Text style={styles.tierHeaderSum}>{sum.toLocaleString('en-US')}</Text>
            ) : null}
          </View>
        );
      }

      if (item.kind === 'empty') {
        // Tier zones only — the Unassigned section is hidden while empty
        // (#105), so an empty pool never renders a placeholder row.
        // S2 PRD-04 (visual.chalkline_cleanup): the hint is an instruction,
        // not a placeholder — faint (3.4:1) promotes to dim.
        return (
          <Text style={[styles.emptyBin, cleanup && styles.emptyBinDim]}>
            Drag players here
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
      // #65 — resolve the tile's You + Consensus stats. Rendered inside the
      // pointerEvents="none" wrapper so it never captures touches away from
      // the drag / selection Pressable. Since #58 (cozy density) the strip
      // sits on line 2 of the dense PlayerCard via its statsSlot.
      const stats = tileStatsFor(item.player);
      // #53 — positional rank for the right cluster. Per-position queries
      // return `rank` AS the positional rank; the All board (#132) derives
      // it client-side (the unfiltered payload's rank is overall).
      const posRankN = allPosRanks ? allPosRanks.get(item.player.id) : item.player.rank;
      const posRank = posRankN != null ? `${item.player.position}${posRankN}` : undefined;
      const tileValue = valueForElo(item.player.elo);

      if (multiSelect) {
        return (
          <Pressable
            onPress={() => toggleSelected(item.player.id)}
            // S8 PRD-02 — the selection tile is one button with checked
            // state; the inner card's facts fold into the grouped label.
            accessibilityRole="button"
            accessibilityState={{ selected: isSelected }}
            accessibilityLabel={[
              item.player.name,
              String(item.player.position),
              item.player.team || 'FA',
              zoneTier ? `tier ${TIER_LABEL[zoneTier]}` : 'unassigned',
            ].join(', ')}
            accessibilityHint="Toggles selection for bulk tier moves"
            style={styles.chipSelectableWrap}
          >
            {/* pointerEvents="none" so PlayerCard's own inner Pressable
                can't become the touch responder — without this the inner
                Pressable swallows the tap and the outer selection onPress
                never fires, leaving multi-select dead. Selection ring is
                the dense card's own `selected` ice border (#16's two
                signals stay: ring + check icon). */}
            <View pointerEvents="none">
              <PlayerCard
                player={item.player}
                dense
                tier={zoneTier}
                selected={isSelected}
                posRank={posRank}
                value={tileValue}
                statsSlot={<TileStats {...stats} />}
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
      // 1.5.4 #98 — the per-tile #90 chevron gutter is gone; the no-drag
      // paths for tier moves are multi-select's Tier up/down buttons (FB-73)
      // and the tier-target chips (FB4-62).
      return (
        // accessible={false}: the components/CLAUDE.md RN caveat — the row
        // container otherwise swallows the card on iOS. The dense
        // PlayerCard is the row's focusable (grouped label) and carries
        // the S8 PRD-01 "Move to <tier>" custom actions, so a VoiceOver
        // user never needs the long-press drag.
        <Pressable
          accessible={false}
          onLongPress={drag}
          delayLongPress={DRAG_ACTIVATION_MS}
          disabled={isActive}
          style={styles.playerRow}
        >
          <View pointerEvents="none">
            <PlayerCard
              player={item.player}
              dense
              tier={zoneTier}
              // Active (picked-up) ring rides the dense card's own ice
              // border so the 60px row pitch stays exact (no wrapper border).
              // ux.board_search reuses the same ring as the locate cue for
              // the matched row (highlightPid is null while the flag is off
              // or the query is empty).
              selected={isActive || item.player.id === highlightPid}
              posRank={posRank}
              value={tileValue}
              statsSlot={<TileStats {...stats} />}
              accessibilityActions={TIER_A11Y_ACTIONS}
              onAccessibilityAction={({ nativeEvent }: AccessibilityActionEvent) => {
                const t = nativeEvent.actionName.startsWith('tier:')
                  ? (nativeEvent.actionName.slice(5) as Tier)
                  : null;
                if (t) movePlayerToTier(item.player, t);
              }}
            />
          </View>
        </Pressable>
      );
    },
    [buckets, multiSelect, selectedIds, toggleSelected, tileStatsFor, allPosRanks, cleanup, highlightPid, movePlayerToTier],
  );

  // ── Copy-from-format button derivation ─────────────────────────────
  // Resolve the format to copy INTO (the "target"). Prefer the session
  // activeFormat; fall back to the tiers/status response or '1qb_ppr'.
  const copyTargetFormat: ScoringFormat =
    activeFormat ?? (tiersStatusQuery.data?.scoring_format as ScoringFormat) ?? '1qb_ppr';
  const otherFormat: ScoringFormat =
    FORMAT_KEYS.find((f) => f !== copyTargetFormat) || 'sf_tep';

  const onCopyFromOtherFormat = useCallback(() => {
    // Destructive — confirm before firing (#139). Since #124 the copy is
    // VALUE-AWARE: it keeps the user's rank order at each position but
    // re-seeds values (and tier labels) from the target format's
    // consensus at those ranks — a player worth 4+ firsts in SF is not
    // worth 4+ firsts in 1QB, and QBs shift the most. No "copy as-is"
    // option: a verbatim tier-label copy is exactly the mispricing #124
    // reported.
    Alert.alert(
      `Copy tier list from ${FORMAT_LABELS[otherFormat]}?`,
      `Values will be adjusted to ${FORMAT_LABELS[copyTargetFormat]} pick values: ` +
        `players keep your ${FORMAT_LABELS[otherFormat]} rank order at each ` +
        `position, but tiers are re-set to what each rank is worth in ` +
        `${FORMAT_LABELS[copyTargetFormat]} — QBs shift the most.\n\n` +
        `This REPLACES your current ${FORMAT_LABELS[copyTargetFormat]} tiers ` +
        `and cannot be undone.`,
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
      const players = (data?.rankings as RankedPlayer[] | undefined) ?? [];
      if (!isAllView) {
        return saveTiers(position, {}, players.map((p) => p.id));
      }
      // #132 All view — clear-only saves routed per position (the save
      // endpoint is per-position; see saveMutation).
      const byPos: Record<Position, string[]> = { QB: [], RB: [], WR: [], TE: [] };
      for (const p of players) byPos[p.position as Position]?.push(p.id);
      const calls = POSITIONS.filter((pos) => byPos[pos].length > 0).map(
        (pos) => saveTiers(pos, {}, byPos[pos]),
      );
      return Promise.all(calls);
    },
    onSuccess: () => {
      setToast({ msg: 'Tiers reset to suggested', tone: 'success' });
      setClearedPids(new Set());
      // Reset discards local edits by design — let the refetch rebuild.
      bucketsDirtyRef.current = false;
      queryClient.invalidateQueries({ queryKey: ['tiers-status'] });
      queryClient.invalidateQueries({ queryKey: ['progress'] });
      if (isAllView) {
        queryClient.invalidateQueries({ queryKey: ['rankings', activeFormat] });
      } else {
        queryClient.invalidateQueries({ queryKey: ['rankings', activeFormat, position] });
        queryClient.invalidateQueries({ queryKey: ['rankings', activeFormat, 'all'] });
      }
      haptics.success();
    },
    onError: (e: Error) => {
      setToast({ msg: e.message || 'Reset failed', tone: 'warn' });
    },
  });

  const onResetToSuggested = useCallback(() => {
    if (!rankingsQuery.data?.rankings) return;
    Alert.alert(
      isAllView
        ? 'Reset ALL tiers to suggested?'
        : `Reset ${position} tiers to suggested?`,
      `Your manual placements for ${isAllView ? 'every position' : position} ` +
        `will be cleared and replaced with the app's suggested tiers. ` +
        `This takes effect immediately.`,
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
        {/* #135 — "Positional Tiers" wrapped to two lines next to the header
            actions; the stack header (TabNav) already says "Tiers". */}
        <Text style={styles.title} accessibilityRole="header">Tiers</Text>
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
          {/* #104 — guided quick-set walk (top tier → Bench, tap-to-assign).
              Occupies the slot the Anchors link held (#99 — the Pick
              Anchor wizard stays reachable from the Rank tab's menu and
              the Build-your-board chooser). Hidden on the All board
              (#132) — QuickSetTiers is a per-position walk. */}
          {!isAllView && (
            <Button
              variant="ghost"
              compact
              label="Quick set"
              onPress={() => navigation.navigate('QuickSetTiers', { position })}
              style={styles.headerBtn}
            />
          )}
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
          color (position hexes are cross-client invariants). #132 adds the
          cross-position "All" board as the last tab — per the PositionTabs
          spec, the Overall/All tab underlines in ice (it's not a position,
          so no position hex applies). */}
      <View style={styles.switcher}>
        {BOARD_TABS.map((p) => {
          const isActive = p === position;
          return (
            <Pressable
              key={p}
              testID={`tiers.pos-tab.${p.toLowerCase()}`}
              accessibilityRole="tab"
              accessibilityState={{ selected: isActive }}
              accessibilityLabel={p === 'ALL' ? 'All positions' : p}
              onPress={() => {
                if (p !== position) setPosition(p);
              }}
              style={({ pressed }) => [
                styles.switcherBtn,
                isActive && styles.switcherBtnActive,
                isActive && {
                  borderBottomColor:
                    p === 'ALL'
                      ? ice.base
                      : positionColors[p.toLowerCase() as keyof typeof positionColors],
                },
                pressed && !isActive && { backgroundColor: ink.ink3 },
              ]}
            >
              <Text
                style={[styles.switcherText, isActive && styles.switcherTextActive]}
              >
                {p === 'ALL' ? 'All' : p}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {/* ux.board_search — QuickSet-pattern name search (Input construction,
          44pt). Kept visible in BOTH collapsed and expanded states — the
          expanded full-screen board is where findability matters most.
          Scroll-to + highlight, never a filter (see highlightIndex). */}
      {boardSearch ? (
        <TextInput
          testID="tiers.search"
          style={[styles.search, searchFocused && styles.searchFocused]}
          placeholder={isAllView ? 'Search players…' : `Search ${position}s…`}
          placeholderTextColor={chalk.faint}
          value={search}
          onChangeText={setSearch}
          onFocus={() => setSearchFocused(true)}
          onBlur={() => setSearchFocused(false)}
          autoCorrect={false}
          autoCapitalize="none"
          returnKeyType="search"
          clearButtonMode="while-editing"
          accessibilityLabel="Search players on this board"
        />
      ) : null}

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
        accessibilityRole="button"
        accessibilityLabel={`Copy tier list from ${FORMAT_LABELS[otherFormat]}`}
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
              : 'Long-press + drag to re-rank. "Select" moves one or several players between tiers without dragging.'}
          </Text>
        )}
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={expanded ? 'Exit full-screen board' : 'Expand board to full screen'}
          // S3 PRD-04 (ux.touch_polish): 32pt button + 6pt slop = 44pt
          // effective (was 4 → 40pt, under the floor).
          hitSlop={touchPolish ? 6 : 4}
          onPress={toggleExpanded}
          style={({ pressed }) => [
            styles.expandBtn,
            pressed && styles.iconBtnPressed,
          ]}
        >
          <Icon name={expanded ? 'collapse' : 'expand'} size={20} />
        </Pressable>
      </View>

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
        <View testID="tiers.list" style={styles.boardWrap}>
        <DraggableFlatList
          ref={listRef}
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
          // S3 PRD-04: the literal 18 became the shared constant so both
          // drag boards (and any future one) stay in lockstep.
          activationDistance={DRAG_ACTIVATION_DISTANCE}
          // #82: keep the lifted tile anchored to the touch point. Without
          // this the library clamps the hover tile inside the list
          // container, so picking up a partially-visible tile at the top/
          // bottom of the page snaps it into view immediately. Edge
          // auto-scroll engagement is also gated on actual drag movement
          // toward the edge — see patches/react-native-draggable-flatlist.
          dragItemOverflow
          // ux.board_search — rows aren't pre-measured; far targets need
          // the standard offset-then-retry fallback.
          onScrollToIndexFailed={(info) => {
            listRef.current?.scrollToOffset({
              offset: info.averageItemLength * info.index,
              animated: true,
            });
            setTimeout(() => {
              listRef.current?.scrollToIndex({
                index: info.index,
                animated: true,
                viewPosition: 0.3,
              });
            }, 250);
          }}
          // S7 PRD-04 ride-along (ux.touch_polish) — pull-to-refresh.
          // Clobber guard: the auto-bucket effect skips rebuilds while
          // bucketsDirtyRef is set, so a pull with unsaved drags refreshes
          // the caches without wiping the user's local layout.
          refreshControl={
            touchPolish ? (
              <RefreshControl
                refreshing={rankingsQuery.isFetching && !!rankingsQuery.data}
                onRefresh={() => {
                  void queryClient.invalidateQueries({
                    queryKey: ['rankings', activeFormat],
                  });
                  void queryClient.invalidateQueries({ queryKey: ['tiers-status'] });
                }}
                tintColor={ice.base}
              />
            ) : undefined
          }
          containerStyle={styles.listContainer}
          contentContainerStyle={[
            styles.scroll,
            // S3 PRD-01 — extra clearance: with the FAB riding above the
            // save bar, the board's last rows need room to scroll clear.
            touchPolish && styles.scrollFabClearance,
          ]}
        />
        {/* FB4-63 / #67 — pinned tier banner, OVERLAYING the top of the
            board so appearing/disappearing never shifts the list. stickyZone
            is null until the current section's inline header scrolls off
            the top (and again when scrolled back to the very top) — see the
            viewability handler. pointerEvents="none": purely informational. */}
        {hasRankings && stickyZone ? (
          <View
            style={styles.stickyOverlay}
            pointerEvents="none"
            // Decorative duplicate of the inline section header — hidden
            // from both platforms' a11y trees.
            accessibilityElementsHidden
            importantForAccessibility="no-hide-descendants"
          >
            <TierStickyHeader
              label={stickyZone === 'unassigned' ? 'Unassigned' : TIER_LABEL[stickyZone]}
              accent={accentFor(stickyZone, cleanup)}
              count={buckets[stickyZone].length}
            />
          </View>
        ) : null}
        </View>
      )}

      {/* Multi-select action bar — only shown in select mode with at
          least one chip selected. Sits above the save bar so the user
          can still commit after a bulk move without leaving select
          mode. "Done" exits select mode without canceling the moves. */}
      {multiSelect && selectedIds.size > 0 ? (
        <View
          style={styles.actionBar}
          onLayout={(e: LayoutChangeEvent) => setActionBarH(e.nativeEvent.layout.height)}
        >
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
          tokens) because the Button primitive has no in-flight spinner.
          onLayout feeds the S3 PRD-01 FAB-offset registry. */}
      <View
        style={styles.saveBar}
        onLayout={(e: LayoutChangeEvent) => setSaveBarH(e.nativeEvent.layout.height)}
      >
        <Pressable
          testID="tiers.save-btn"
          disabled={saving || loading}
          accessibilityRole="button"
          accessibilityLabel={isAllView ? 'Save all tiers' : `Save ${position} tiers`}
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
            <Text style={styles.saveBtnText}>
              {isAllView ? 'Save all tiers' : `Save ${position} tiers`}
            </Text>
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
    firsts_4plus: [],
    firsts_3: [],
    firsts_2: [],
    first_1: [],
    second: [],
    third: [],
    fourth: [],
    waivers: [],
  };
}

// Move every player in `ids` one whole tier in `direction`, preserving
// relative order. Placement inside the target tier: moving up appends to
// the BOTTOM of the higher tier (they're its newest/weakest members);
// moving down inserts at the TOP of the lower tier (its strongest).
// Clamps at the top/bottom tiers (TIERS[0] / waivers); `unassigned` is
// never a source or target. Used by the multi-select "Tier up / Tier down"
// bar (FB-73). Returns `prev` unchanged when every mover is already
// clamped at the boundary (no re-render).
function moveTierByOne(
  prev: Record<Zone, RankedPlayer[]>,
  ids: ReadonlySet<string>,
  direction: 'up' | 'down',
): Record<Zone, RankedPlayer[]> {
  const next = emptyBuckets();
  next.unassigned = [...prev.unassigned];
  // Split each tier into keepers and movers, preserving order.
  const movers: Record<Tier, RankedPlayer[]> = {
    firsts_4plus: [], firsts_3: [], firsts_2: [], first_1: [],
    second: [], third: [], fourth: [], waivers: [],
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
// S2 PRD-04 (visual.chalkline_cleanup): the Unassigned accent colors the
// header's LABEL text (content, not decoration) — faint (3.4:1) promotes
// to dim when the cleanup flag is on. Tier zones keep their data hexes.
// The optional param keeps the signature compatible with TierTargetChips'
// `accentFor` prop (which only ever passes real tiers).
function accentFor(zone: Zone, cleanupDim?: boolean): string {
  if (zone === 'unassigned') return cleanupDim ? chalk.dim : chalk.faint;
  return tierColors[zone];
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
  // #58 cozy: label + count sit together on the left; the summed 0–10k
  // value is right-aligned.
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
  tierHeaderLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  tierHeaderCount: { ...type.data, color: chalk.dim },
  tierHeaderSum: { ...type.data, color: chalk.dim },
  // Player row wrapper in normal (drag) mode. #58 cozy: no wrapper border —
  // the active (picked-up) ice ring is the dense card's own `selected`
  // border, keeping the row pitch at exactly 60px card + 4px gap.
  playerRow: {
    marginBottom: space.xs,
  },
  // Pressed fill shared by the icon buttons on this screen (#81 expand).
  iconBtnPressed: { backgroundColor: ink.ink3 },
  // Wrapper around each chip in multi-select mode. #58 cozy: the selected
  // ring (issue #16 — ice ring + check icon, two signals so selection reads
  // for color-vision-impaired users too) is the dense card's own `selected`
  // border, so this wrapper only owns the row gap.
  chipSelectableWrap: {
    marginBottom: space.xs,
  },
  // Floating action bar — shown above the save bar when 1+ chips are
  // selected. Holds the FB4-62 tier-target chip row on top + the Up/Down/
  // Done controls row below (so it's a column container now).
  actionBar: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: ACTION_BAR_BOTTOM,        // sits just above the save bar
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
  // ux.board_search — Input construction per the design system (QuickSet's
  // search pattern): line-strong border, ink-2 fill, radius sm, faint
  // placeholder, ice focus border. 44pt tall (touch floor).
  search: {
    ...type.body,
    height: 44,
    marginHorizontal: space.lg,
    marginTop: space.sm,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: 0,
  },
  searchFocused: { borderColor: ice.base },
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
  // chalk-dim glyph, pressed ink-3 fill).
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
  // #67 — hosts the list + the sticky-banner overlay (banner floats over
  // the board's top edge instead of occupying layout, so its gated
  // appear/disappear never shifts the list mid-scroll).
  boardWrap: { flex: 1 },
  stickyOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
  },
  listContainer: { flex: 1 },
  scroll: {
    padding: space.lg,
    paddingBottom: 96, // room for the Save bar
  },
  // S3 PRD-01 (ux.touch_polish) — the FAB rides above the save bar now;
  // give the last rows room to scroll clear of it (52pt FAB + margin).
  scrollFabClearance: { paddingBottom: 96 + 72 },
  emptyBin: {
    ...type.bodySm,
    color: chalk.faint,
    textAlign: 'center',
    paddingVertical: space.sm,
  },
  // S2 PRD-04 (visual.chalkline_cleanup) — instruction text ≥ dim.
  emptyBinDim: { color: chalk.dim },
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
