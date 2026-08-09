import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AccessibilityInfo,
  ActivityIndicator,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
  type AccessibilityActionEvent,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import DraggableFlatList, {
  RenderItemParams,
  DragEndParams,
} from 'react-native-draggable-flatlist';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Button, Icon, PositionBadge, TickLabel } from '../components/chalkline';
import TierBadge from '../components/TierBadge';
import FormatToggle from '../components/FormatToggle';
import Toast from '../components/Toast';
import { RookieScopeEmpty } from '../components/RookieScopeControl';
import { getRankings, reorderRankings, splitRankings } from '../api/rankings';
import { useSession } from '../state/useSession';
import { useScoringFormat } from '../hooks/useScoringFormat';
import { useRookieScope } from '../state/rookieScope';
import { startSpan } from '../observability/sentry';
import { readErrorCopy } from '../utils/verification';
import { TIER_LABEL, tierForElo } from '../utils/tierBands';
import {
  chalk,
  ice,
  ink,
  position as positionColors,
  radii,
  semantic,
  space,
  type,
  DRAG_ACTIVATION_DISTANCE,
} from '../theme/chalkline';
import { haptics } from '../utils/haptics';
import type { Position, RankedPlayer, ScoringFormat, Tier } from '../shared/types';

// ── Consolidated rookie ranking view (rookie-draft M2, operator decision
// O1-expanded) ─────────────────────────────────────────────────────────
//
// Rookies stay in their position boards AND appear here in ONE cross-
// position list. This is NOT a second Elo space — it is the same board
// read through the same post-Elo view filter (`GET /api/rankings?scope=
// rookie` with no position), so the values shown here and the values on
// the QB/RB/WR/TE boards are synced BY CONSTRUCTION, not by a sync step.
// That is the whole reason a separate rookie Elo space was rejected: a
// second space would fork tier colors, trade values, #161 demotion and
// four cross-client mirrors.
//
// ── EDITABLE since 2026-08-06 (operator decision) ─────────────────────
// This screen shipped read-only on the argument that "a seventh drag board
// would just be Overall ranks under scope". Live TestFlight testing killed
// that: the Draft Room's row is labeled "Rank the rookies", it lands here,
// and the screen could not rank. A label that promises an action must
// deliver it on the surface it lands on.
//
// It is the SHIPPED drag board, not a new one: `DraggableFlatList` with
// ManualRanksScreen's exact interaction (220ms long-press pickup,
// DRAG_ACTIVATION_DISTANCE, pickup/swipe haptics, 600ms debounced save,
// filtered-view splice-back, Move up / Move down VoiceOver actions).
//
// ── THE REORDER LANE ONLY ─────────────────────────────────────────────
// Writes go through `POST /api/rankings/reorder` → `ranking_service
// .apply_reorder`, which is subset-safe BY CONSTRUCTION: it permutes the
// sorted multiset of exactly the posted ids' OWN current Elos and writes
// overrides for exactly those pids (backend/ranking_service.py). So a
// rookie-scoped reorder is byte-identical to the same reorder run on the
// full board's rookie subsequence, and no veteran ever moves — which is
// why `reorderRankings` takes no `scope` param.
//
// This screen must NEVER reach the TIER-SAVE lane (`/api/tiers/save`,
// `save_tiers_position`, `apply_tiers`, the merged-band `apply_tiers_subset`
// path). That is the one construction in this codebase that can destroy a
// user's board, and it has done so once. Pinned by a source test in
// `backend/tests/test_rookie_ranks_editable.py`.
//
// Flag-gated by `ranks.rookie_subset` (server-delivered). No entry point
// exists with the flag off; reaching the route anyway (a stale deep link)
// renders the honest unavailable state rather than an empty board.

const FILTERS: readonly (Position | 'ALL')[] = ['ALL', 'QB', 'RB', 'WR', 'TE'];
const SAVE_DEBOUNCE_MS = 600;
const DRAG_ACTIVATION_MS = 220;

const filterUnderline = (f: Position | 'ALL'): string =>
  f === 'ALL'
    ? ice.base
    : positionColors[f.toLowerCase() as keyof typeof positionColors];

type SaveStatus = 'idle' | 'pending' | 'saving' | 'saved' | 'error';

// The no-drag power path (ManualRanksScreen's S8 PRD-01 contract), wired to
// the same move handler the drag uses. A drag-only board is unusable under
// VoiceOver.
const ROW_A11Y_ACTIONS: { name: string; label: string }[] = [
  { name: 'moveUp', label: 'Move up' },
  { name: 'moveDown', label: 'Move down' },
];

export default function RookieRanksScreen({ route, navigation }: any = {}) {
  // draft-extensions W1 — the Draft Room bridge is TWO-WAY now. It lands
  // two hops from any editing gesture, so without a way back "rank this
  // rookie" costs the user their place on the board. The param is set only
  // by the Draft Room; every other entry omits it and this row never
  // renders.
  const returnTo: string | undefined = route?.params?.returnTo;
  const returnLeagueId: string | undefined = route?.params?.returnLeagueId;

  const queryClient = useQueryClient();
  const activeFormat = useSession((s) => s.activeFormat);
  const fmt: ScoringFormat = activeFormat || '1qb_ppr';
  const { setFormat, switching: formatSwitching } = useScoringFormat();
  const { enabled } = useRookieScope();
  const [filter, setFilter] = useState<Position | 'ALL'>('ALL');
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const [errorText, setErrorText] = useState<string | null>(null);

  // The consolidated read: the scoped rankings payload with NO position,
  // i.e. the cross-position board filtered to rookies. Shares the same
  // `['rankings', fmt, 'all', 'rookie']` key as Overall ranks under scope,
  // so the two never show different numbers and a save on either refreshes
  // both through the existing prefix invalidations.
  const ranksQuery = useQuery({
    queryKey: ['rankings', activeFormat, 'all', 'rookie'],
    queryFn: () => getRankings(null, { scope: 'rookie' }),
    staleTime: 30_000,
    enabled,
  });

  const scopeEmpty = useMemo(
    () => splitRankings(ranksQuery.data).empty,
    [ranksQuery.data],
  );

  // Local ordering, driven from the server fetch but mutated client-side
  // during a drag so the list stays responsive; the debounced save posts a
  // snapshot of it. Cross-position order is Elo order — the same ladder the
  // tier bands are cut from, which is why a rookie WR and a rookie RB are
  // comparable here at all (pick value is position-uniform by design, #117).
  const [rows, setRows] = useState<RankedPlayer[]>([]);
  useEffect(() => {
    const all = splitRankings(ranksQuery.data).rows as RankedPlayer[];
    setRows([...all].sort((a, b) => (b.elo ?? 0) - (a.elo ?? 0)));
  }, [ranksQuery.data]);

  const visible = useMemo(
    () => (filter === 'ALL' ? rows : rows.filter((r) => r.position === filter)),
    [rows, filter],
  );

  // Cross-position rookie rank + positional rookie rank, both derived from
  // the FULL local ordering so they update live during a drag, before the
  // debounced save lands. The left column keeps showing the cross-position
  // rank even under a position filter — that is this screen's whole point.
  const ranks = useMemo(() => {
    const posCounts: Partial<Record<string, number>> = {};
    const overall = new Map<string, number>();
    const pos = new Map<string, number>();
    rows.forEach((p, i) => {
      const n = (posCounts[p.position] ?? 0) + 1;
      posCounts[p.position] = n;
      overall.set(p.id, i + 1);
      pos.set(p.id, n);
    });
    return { overall, pos };
  }, [rows]);

  // ── Save plumbing (ManualRanksScreen's shape) ─────────────────────────
  // The latest payload lives in a ref so a string of drag-ends just resets
  // the timer and ONE network call carries the most recent ordering.
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingPayload = useRef<{ position: Position | null; orderedIds: string[] } | null>(null);

  const saveMutation = useMutation({
    mutationFn: ({ position, orderedIds }: { position: Position | null; orderedIds: string[] }) =>
      startSpan({ name: 'rankings.reorder', op: 'mutation' }, () =>
        // `via:'rookie_ranks'` keeps a scoped edit identifiable on the wire.
        // NOTE the lane: reorderRankings, never saveTiers.
        reorderRankings(position, orderedIds, 'rookie_ranks'),
      ),
    onMutate: () => setSaveStatus('saving'),
    onSuccess: () => {
      setSaveStatus('saved');
      setErrorText(null);
      queryClient.invalidateQueries({ queryKey: ['rankings', activeFormat] });
      queryClient.invalidateQueries({ queryKey: ['tiers-status'] });
      queryClient.invalidateQueries({ queryKey: ['progress'] });
    },
    onError: (e: Error) => {
      setSaveStatus('error');
      setErrorText(e.message || 'Save failed');
    },
  });

  // Caller passes the CURRENT full local ordering so ordered_ids always come
  // from a post-mutation snapshot, never from stale closure state.
  //
  // Under a position filter we post THAT position's rookie slice with
  // `position: filter` (apply_reorder then permutes those players' own Elos
  // inside the position pool); with 'ALL' we post every rookie id with
  // `position: null`. Both are subset-safe permutations — see the lane note
  // at the top of this file.
  const scheduleSave = useCallback(
    (nextRows: RankedPlayer[]) => {
      setSaveStatus('pending');
      const position: Position | null = filter === 'ALL' ? null : filter;
      const orderedIds =
        filter === 'ALL'
          ? nextRows.map((r) => r.id)
          : nextRows.filter((r) => r.position === filter).map((r) => r.id);
      pendingPayload.current = { position, orderedIds };

      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      debounceTimer.current = setTimeout(() => {
        const payload = pendingPayload.current;
        if (!payload) return;
        // /api/rankings/reorder requires ≥2 ids.
        if (payload.orderedIds.length < 2) {
          setSaveStatus('idle');
          return;
        }
        saveMutation.mutate(payload);
      }, SAVE_DEBOUNCE_MS);
    },
    [filter, saveMutation],
  );

  // Cancel a pending debounce on unmount so we never fire against an
  // unmounted query client.
  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, []);

  // The "saved" dot fades back to idle so the indicator doesn't get noisy.
  useEffect(() => {
    if (saveStatus !== 'saved') return;
    const t = setTimeout(() => setSaveStatus('idle'), 1500);
    return () => clearTimeout(t);
  }, [saveStatus]);

  // ── Reorder handlers ─────────────────────────────────────────────────
  // `data` is the new order of the VISIBLE (filtered) rows. When filtered we
  // splice that sub-order back into the full list, preserving the relative
  // order of rows that weren't part of the visible set.
  const onDragBegin = useCallback(() => haptics.pickup(), []);

  const spliceBack = useCallback(
    (prev: RankedPlayer[], newVisible: RankedPlayer[]): RankedPlayer[] => {
      if (filter === 'ALL') return newVisible;
      const iter = newVisible[Symbol.iterator]();
      return prev.map((r) =>
        r.position === filter ? (iter.next().value as RankedPlayer) : r,
      );
    },
    [filter],
  );

  const onDragEnd = useCallback(
    ({ data: newVisible, from, to }: DragEndParams<RankedPlayer>) => {
      if (from === to) return;
      // Drag end is routine: impact-light, not success() — success is
      // reserved for server-confirmed outcomes and this save hasn't happened
      // yet (ManualRanksScreen's S3 PRD-04 note).
      haptics.swipe();
      setRows((prev) => {
        const next = spliceBack(prev, newVisible);
        scheduleSave(next);
        return next;
      });
    },
    [scheduleSave, spliceBack],
  );

  // Move `pid` to 1-based `target` in the FILTERED view — the VoiceOver
  // Move up / Move down path.
  const applyRankMove = useCallback(
    (pid: string, target: number) => {
      setRows((prev) => {
        const vis = filter === 'ALL' ? prev : prev.filter((r) => r.position === filter);
        const fromIdx = vis.findIndex((r) => r.id === pid);
        if (fromIdx < 0) return prev;
        const toIdx = Math.max(0, Math.min(vis.length - 1, target - 1));
        if (toIdx === fromIdx) return prev;

        const newVisible = [...vis];
        const [moved] = newVisible.splice(fromIdx, 1);
        newVisible.splice(toIdx, 0, moved);

        const next = spliceBack(prev, newVisible);
        scheduleSave(next);
        haptics.success();
        AccessibilityInfo.announceForAccessibility(
          `${moved.name} moved to rank ${toIdx + 1}`,
        );
        return next;
      });
    },
    [filter, scheduleSave, spliceBack],
  );

  const onFormatChange = async (f: ScoringFormat) => {
    haptics.selection();
    const ok = await setFormat(f);
    if (!ok) setToast({ msg: 'Could not switch format', tone: 'warn' });
  };

  const renderItem = useCallback(
    ({ item, drag, isActive, getIndex }: RenderItemParams<RankedPlayer>) => {
      // #277 — the tier badge IS the value display now; the 0–10k numeric
      // that rendered under it was removed (tier labels app-wide).
      const tier = tierForElo(item.elo, item.position as Position, fmt) as Tier | null;
      const overallRank = ranks.overall.get(item.id) ?? 0;
      const posRank = ranks.pos.get(item.id) ?? 0;
      const visIdx = getIndex();
      const visRank = visIdx != null ? visIdx + 1 : 0;

      // One grouped utterance per row + the custom-action power path, so the
      // row doesn't read fragment-by-fragment under VoiceOver.
      const rowLabel = [
        item.name,
        String(item.position),
        item.team || 'FA',
        `rookie rank ${overallRank}`,
        `${item.position}${posRank} rookie`,
        tier ? `tier ${TIER_LABEL[tier]}` : null,
      ]
        .filter(Boolean)
        .join(', ');

      const onRowA11yAction = ({ nativeEvent }: AccessibilityActionEvent) => {
        if (nativeEvent.actionName === 'moveUp') applyRankMove(item.id, visRank - 1);
        else if (nativeEvent.actionName === 'moveDown') applyRankMove(item.id, visRank + 1);
      };

      return (
        // accessible={false}: an accessible container swallows its children
        // on iOS (the components/CLAUDE.md RN caveat) — the row's semantics
        // live on the grouped block below instead.
        <Pressable
          accessible={false}
          testID={`rookie-ranks.row.${item.id}`}
          onLongPress={drag}
          delayLongPress={DRAG_ACTIVATION_MS}
          disabled={isActive}
          style={({ pressed }) => [
            styles.row,
            isActive && styles.rowActive,
            pressed && !isActive && { backgroundColor: ink.ink3 },
          ]}
        >
          <Text style={styles.rank}>{overallRank}</Text>
          <View
            style={styles.rowMain}
            accessible
            accessibilityLabel={rowLabel}
            accessibilityActions={ROW_A11Y_ACTIONS}
            onAccessibilityAction={onRowA11yAction}
          >
            <Text style={styles.name} numberOfLines={1}>{item.name}</Text>
            <View style={styles.metaRow}>
              <PositionBadge pos={item.position as Position} />
              <Text style={styles.meta}>
                {item.team ?? 'FA'}
                {item.age != null ? ` · ${item.age}` : ''}
                {` · ${item.position}${posRank} rookie`}
              </Text>
            </View>
          </View>
          <View
            style={styles.rowRight}
            accessibilityElementsHidden
            importantForAccessibility="no-hide-descendants"
          >
            <TierBadge tier={tier} size="sm" />
          </View>
          {/* Drag affordance — decorative lineStrong grip bars (no emoji, no
              icon glyph), the shipped Overall-ranks construction. */}
          <View
            style={styles.grip}
            testID={`rookie-ranks.drag-handle.${item.id}`}
            accessibilityElementsHidden
            importantForAccessibility="no-hide-descendants"
          >
            <View style={styles.gripBar} />
            <View style={styles.gripBar} />
          </View>
        </Pressable>
      );
    },
    [applyRankMove, fmt, ranks],
  );

  // Pull-to-refresh would clobber local `rows` through the resync effect
  // while a reorder is pending — skip until the save settles.
  const onRefresh = useCallback(() => {
    if (saveStatus === 'pending' || saveStatus === 'saving') return;
    void ranksQuery.refetch();
  }, [saveStatus, ranksQuery]);

  // Flag off: no entry point exists, so this can only be a stale deep link.
  if (!enabled) {
    return (
      <SafeAreaView style={styles.safe} edges={['bottom']}>
        <View style={styles.center}>
          <Text style={styles.emptyBody}>
            Rookie rankings aren't available yet.
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />

      {returnTo === 'DraftRoom' ? (
        <Pressable
          testID="rookie-ranks.back-to-draft"
          accessibilityRole="button"
          accessibilityLabel="Back to the draft room"
          onPress={() =>
            navigation?.navigate?.(
              'DraftRoom',
              returnLeagueId ? { leagueId: returnLeagueId } : undefined,
            )
          }
          style={({ pressed }) => [
            styles.backRow,
            pressed && { backgroundColor: ink.ink3 },
          ]}
        >
          <Text style={styles.backText}>‹ Back to the draft room</Text>
        </Pressable>
      ) : null}

      <View style={styles.header}>
        <View style={styles.headerRow}>
          <TickLabel>Rookies</TickLabel>
          <SaveIndicator status={saveStatus} errorText={errorText} />
        </View>
        <Text style={styles.hint}>
          Every rookie on your board, ranked across positions. Long-press +
          drag a row to re-rank. These are the same values as your position
          boards — ranking a rookie anywhere moves them here too.
        </Text>
      </View>

      <View style={styles.formatRow}>
        <FormatToggle
          value={activeFormat}
          onChange={onFormatChange}
          disabled={formatSwitching}
        />
      </View>

      {/* Position filter — PositionTabs construction; a filter over the ONE
          consolidated list (no second fetch), so switching is instant and
          the cross-position ranks stay stable. */}
      <View style={styles.filterRow}>
        {FILTERS.map((f) => {
          const active = f === filter;
          return (
            <Pressable
              key={f}
              testID={`rookie-ranks.filter.${f.toLowerCase()}`}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              accessibilityLabel={f === 'ALL' ? 'All positions' : f}
              onPress={() => {
                if (f === filter) return;
                haptics.selection();
                setFilter(f);
              }}
              style={({ pressed }) => [
                styles.filterSeg,
                active && styles.filterSegActive,
                active && { borderBottomColor: filterUnderline(f) },
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
      ) : scopeEmpty ? (
        <RookieScopeEmpty surface="rookie-ranks" empty={scopeEmpty} />
      ) : ranksQuery.isError ? (
        <View style={styles.center}>
          <Text style={styles.emptyBody}>
            {readErrorCopy(ranksQuery.error, 'Could not load rookie rankings.')}
          </Text>
          <Button
            variant="secondary"
            compact
            label="Try again"
            onPress={() => ranksQuery.refetch()}
          />
        </View>
      ) : visible.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.emptyBody}>
            No rookie {filter === 'ALL' ? 'players' : `${filter}s`} on your
            board yet.
          </Text>
        </View>
      ) : (
        <DraggableFlatList
          testID="rookie-ranks.list"
          data={visible}
          keyExtractor={(r) => r.id}
          renderItem={renderItem}
          onDragBegin={onDragBegin}
          onDragEnd={onDragEnd}
          // 18 (the value Tiers and Overall ranks landed on): 5 let ordinary
          // vertical scrolls cross the threshold and steal the touch into a
          // drag, with the accidental re-rank persisted by the auto-save.
          activationDistance={DRAG_ACTIVATION_DISTANCE}
          containerStyle={styles.listContainer}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl
              refreshing={ranksQuery.isFetching && !ranksQuery.isLoading}
              onRefresh={onRefresh}
              tintColor={ice.base}
            />
          }
        />
      )}
    </SafeAreaView>
  );
}

// Save-state pill. Mirrors ManualRanksScreen's indicator (same three states,
// same tokens) — kept local rather than lifted so the shipped Overall-ranks
// board isn't touched by this change.
function SaveIndicator({ status, errorText }: { status: SaveStatus; errorText: string | null }) {
  if (status === 'idle') return null;
  if (status === 'saving' || status === 'pending') {
    return (
      <View style={styles.saveWrap} testID="rookie-ranks.save-status">
        <ActivityIndicator size="small" color={chalk.dim} />
        <Text style={styles.saveText}>saving…</Text>
      </View>
    );
  }
  if (status === 'saved') {
    return (
      <View style={styles.saveWrap} testID="rookie-ranks.save-status">
        <Icon name="check" size={14} color={semantic.pos} />
        <Text style={styles.savedText}>saved</Text>
      </View>
    );
  }
  return (
    <View style={[styles.saveWrap, styles.errorPill]} testID="rookie-ranks.save-status">
      <Text style={styles.errorPillText} numberOfLines={1}>
        {errorText || 'error'}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  // W1 — the return leg of the Draft Room bridge. Renders only when the
  // Draft Room set the param.
  backRow: {
    marginHorizontal: space.lg,
    marginTop: space.md,
    alignSelf: 'flex-start',
    minHeight: 44,
    justifyContent: 'center',
    paddingHorizontal: space.sm,
    borderRadius: radii.sm,
  },
  backText: { ...type.label, color: ice.base },

  header: { paddingHorizontal: space.lg, paddingTop: space.md, gap: space.xs },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  hint: { ...type.bodySm, lineHeight: 19 },
  formatRow: { marginHorizontal: space.lg, marginTop: space.sm },
  filterRow: {
    flexDirection: 'row',
    marginHorizontal: space.lg,
    marginTop: space.sm,
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
  filterSegActive: { backgroundColor: ink.ink3 },
  filterText: { ...type.label },
  filterTextActive: { color: chalk.base },

  // Save status indicator — three visual variants.
  saveWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    paddingHorizontal: space.sm,
    paddingVertical: space.xs,
  },
  saveText: { ...type.label },
  savedText: { ...type.label, color: semantic.pos },
  errorPill: {
    borderColor: semantic.neg,
    borderWidth: 1,
    borderRadius: radii.xs,
  },
  errorPillText: { ...type.label, color: semantic.neg, maxWidth: 180 },

  listContainer: { flex: 1 },
  list: { padding: space.lg, gap: space.xs },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    minHeight: 56,
  },
  rowActive: { backgroundColor: ink.ink2 },
  rank: { ...type.data, color: chalk.dim, minWidth: 28 },
  rowMain: { flex: 1, gap: 2 },
  name: { ...type.title },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  meta: { ...type.bodySm, color: chalk.dim, flexShrink: 1 },
  rowRight: { alignItems: 'flex-end', gap: 2 },
  grip: { gap: 3 },
  gripBar: { width: 14, height: 2, backgroundColor: ink.lineStrong },

  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: space.lg,
    gap: space.md,
  },
  emptyBody: { ...type.bodySm, textAlign: 'center' },
});
