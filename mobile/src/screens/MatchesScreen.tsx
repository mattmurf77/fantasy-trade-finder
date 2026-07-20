import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  Pressable,
  ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import { haptics } from '../utils/haptics';
import { track } from '../api/events';
import { getBaseUrl } from '../api/client';
import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query';

import { ink, chalk, ice, semantic, space, radii, type, fonts } from '../theme/chalkline';
import { Button, Badge, Icon } from '../components/chalkline';
import TradeCardComp from '../components/TradeCard';
import Toast from '../components/Toast';
import PlayerContextMenu, { type PlayerMenuAction } from '../components/PlayerContextMenu';
import HelpSheet from '../components/HelpSheet';
import { getAllMatches, getAwaitingTrades, dismissMatch } from '../api/trades';
import { getAssetPrefs, setAssetPref } from '../api/league';
import { useSession } from '../state/useSession';
import { usePushPriming } from '../state/usePushPriming';
import { useFlag } from '../state/useFeatureFlags';
import { relativeTime } from '../utils/relativeTime';
import { readErrorCopy } from '../utils/verification';
import type { TradeMatch, AwaitingTrade, Player } from '../shared/types';

// Triage undo (S3 PRD-03, flag ux.swipe_undo): how long a dismiss's archive
// POST is held (and the Undo toast shown) before committing.
const UNDO_HOLD_MS = 5000;

type LeagueFilter = string | 'all';
type Segment = 'mutual' | 'awaiting';

// Cross-league matches inbox. Pulls /api/trades/matches/all so users can
// see pending / accepted / declined matches regardless of which league is
// currently active in the session. A horizontally-scrollable filter row
// at the top lets them narrow to a single league client-side.
//
// On Accept: deep-link to the Sleeper trade-propose URL so the user can
// ratify the trade on Sleeper directly.
//
// The "Awaiting them" segment surfaces the gap between "I swiped accept"
// and "we both swiped accept" — trades the caller has liked that haven't
// yet been mirrored by the counterparty. Backed by /api/trades/awaiting.
export default function MatchesScreen() {
  const queryClient = useQueryClient();
  const navigation = useNavigation<any>();
  const leagues = useSession((s) => s.leagues);
  const activeLeague = useSession((s) => s.league);
  const [toast, setToast] = useState<{
    msg: string;
    tone?: 'success' | 'warn' | 'error';
    holdMs?: number;
    action?: { label: string; onPress: () => void };
  } | null>(null);
  const [filterLeagueId, setFilterLeagueId] = useState<LeagueFilter>('all');
  const [segment, setSegment] = useState<Segment>('mutual');

  // ── Teardown-remediation flags (all default false — flag off is
  // byte-identical behavior) ──────────────────────────────────────────
  const swipeUndoOn = useFlag('ux.swipe_undo');           // S3 PRD-03
  const menuOn = useFlag('ux.player_context_menu');       // S3 PRD-02
  const emptyCtasOn = useFlag('ux.empty_state_ctas');     // S4 PRD-05
  const helpOn = useFlag('ux.help_surface');              // S4 PRD-01
  const cleanupOn = useFlag('visual.chalkline_cleanup');  // S2 PRD-04 ride-along

  // S4 PRD-01 — "How matching works" sheet from the empty state.
  const [matchingHelpOpen, setMatchingHelpOpen] = useState(false);
  // S3 PRD-02 — shared player context menu target.
  const [menuTarget, setMenuTarget] = useState<{
    leagueId: string;
    player: Player;
    side: 'give' | 'receive';
  } | null>(null);

  // FB-91 — the League tab's Matches tiles deep-link into a specific
  // segment: navigate('Matches', { segment, at }). `at` (a timestamp)
  // changes on every tap so re-tapping the same tile still lands on the
  // requested segment after the user has toggled away.
  const route = useRoute<any>();
  useEffect(() => {
    const s = route.params?.segment;
    if (s === 'mutual' || s === 'awaiting') setSegment(s);
  }, [route.params?.segment, route.params?.at]);

  // Stable query key — `'all'` not the active league. The endpoint returns
  // every-league results, so league switching shouldn't invalidate this
  // cache. Filtering is done client-side below.
  // `placeholderData: (prev) => prev` keeps the previous list visible
  // across refetches so the screen doesn't blank on re-entry.
  const matchesQuery = useQuery({
    queryKey: ['matches', 'all'],
    queryFn:  getAllMatches,
    staleTime: 15_000,
    placeholderData: (prev) => prev,
  });

  // Awaiting trades — fetched lazily the first time the segment is opened,
  // then kept warm so toggling back is instant. Same cross-league scope
  // as matches/all; client-side league filter is reused.
  const awaitingQuery = useQuery({
    queryKey: ['awaiting-trades'],
    queryFn:  getAwaitingTrades,
    staleTime: 15_000,
    enabled:  segment === 'awaiting',
  });

  // Dismiss = archive the match from THIS user's inbox. Persisted + per-user
  // + ELO-neutral (see /api/trades/matches/:id/dismiss). Replaces the old
  // accept/decline dispositions on mutual matches — the real "do the trade"
  // action is now the Send-in-Sleeper button, so the only inbox verb left is
  // "clear it."
  const dismissMutation = useMutation({
    mutationFn: (id: string) => dismissMatch(id),
    onMutate: async (id) => {
      // Optimistic — drop the match from the list so the UI feels instant.
      const prev = queryClient.getQueryData<TradeMatch[]>(['matches', 'all']);
      if (prev) {
        queryClient.setQueryData(
          ['matches', 'all'],
          prev.filter((m) => m.match_id !== id),
        );
      }
      return { prev };
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(['matches', 'all'], ctx.prev);
      // Undo path (ux.swipe_undo): the row was removed at TAP time, so
      // ctx.prev here is the already-filtered list — refetch to restore
      // the failed-dismiss row instead of leaving it invisibly archived.
      if (swipeUndoOn) {
        queryClient.invalidateQueries({ queryKey: ['matches', 'all'] });
      }
      setToast({ msg: 'Could not dismiss — try again', tone: 'warn' });
    },
    onSuccess: () => {
      // Dismissed matches are gone server-side, so refetch to reconcile
      // (the optimistic removal already hid it locally).
      queryClient.invalidateQueries({ queryKey: ['matches', 'all'] });
    },
  });

  // ── Dismiss undo (S3 PRD-03, flag ux.swipe_undo) ─────────────────────
  // Same design decision as the Trades pass-undo: the archive POST is
  // DELAYED for UNDO_HOLD_MS rather than reversed (there is no un-dismiss
  // endpoint). The row is removed optimistically at tap time; Undo restores
  // the snapshotted list and drops the pending write. A second dismiss,
  // or unmount, flushes the pending one first.
  const pendingDismissRef = useRef<{
    id: string;
    prev: TradeMatch[] | undefined;
    timer: ReturnType<typeof setTimeout>;
  } | null>(null);

  function flushPendingDismiss() {
    const p = pendingDismissRef.current;
    if (!p) return;
    pendingDismissRef.current = null;
    clearTimeout(p.timer);
    dismissMutation.mutate(p.id);
  }
  const flushPendingDismissRef = useRef(flushPendingDismiss);
  flushPendingDismissRef.current = flushPendingDismiss;

  function undoDismiss() {
    const p = pendingDismissRef.current;
    if (!p) return;
    pendingDismissRef.current = null;
    clearTimeout(p.timer);
    if (p.prev) queryClient.setQueryData(['matches', 'all'], p.prev);
    track('match_dismiss_undone', { match_id: p.id }, 'Matches');
  }

  // Commit any pending dismiss on unmount — leaving ends the undo window.
  useEffect(
    () => () => {
      flushPendingDismissRef.current();
    },
    [],
  );

  function handleDismiss(m: TradeMatch) {
    haptics.selection();
    if (!swipeUndoOn) {
      dismissMutation.mutate(m.match_id);
      return;
    }
    // Double-fire guard: the tile's Dismiss can only be pending once.
    if (pendingDismissRef.current?.id === m.match_id) return;
    flushPendingDismiss();
    // Optimistic removal now; the POST waits out the undo window.
    const prev = queryClient.getQueryData<TradeMatch[]>(['matches', 'all']);
    if (prev) {
      queryClient.setQueryData(
        ['matches', 'all'],
        prev.filter((x) => x.match_id !== m.match_id),
      );
    }
    pendingDismissRef.current = {
      id: m.match_id,
      prev,
      timer: setTimeout(() => flushPendingDismissRef.current(), UNDO_HOLD_MS),
    };
    setToast({
      msg: 'Dismissed',
      tone: 'success',
      holdMs: UNDO_HOLD_MS,
      action: { label: 'Undo', onPress: undoDismiss },
    });
  }

  const allMatches: TradeMatch[] = matchesQuery.data || [];
  const allAwaiting: AwaitingTrade[] = awaitingQuery.data || [];

  // S4 PRD-04 (ux.prompt_arbiter) — want-it moment for the push primer:
  // the first mutual match seen this session is the "get pinged when a
  // match drops" payoff made concrete. No-op unless the arbiter flag is on
  // AND a backoff-suppressed primer is parked (see usePushPriming).
  const wantItFiredRef = useRef(false);
  useEffect(() => {
    if (wantItFiredRef.current || allMatches.length === 0) return;
    wantItFiredRef.current = true;
    usePushPriming.getState().wantItMoment();
  }, [allMatches.length]);

  // ── Untouchables (feedback #95, flag trade.preference_lists) ─────────
  // Long-press a player on the YOU SEND side to mark/unmark them
  // untouchable — the trade engine then never offers them from your
  // roster. Matches are cross-league, so prefs are fetched per league
  // present in either segment; `combine` memoizes the league→Set map so
  // TradeCard's memo isn't busted every render.
  const untouchablesEnabled = useFlag('trade.preference_lists');
  const prefLeagueIds = useMemo(() => {
    const ids = new Set<string>();
    allMatches.forEach((m) => m.league_id && ids.add(m.league_id));
    allAwaiting.forEach((a) => a.league_id && ids.add(a.league_id));
    return Array.from(ids).sort();
  }, [allMatches, allAwaiting]);

  const untouchablesByLeague = useQueries({
    queries: prefLeagueIds.map((lid) => ({
      queryKey: ['asset-prefs', lid],
      queryFn: () => getAssetPrefs(lid),
      staleTime: 60_000,
      enabled: untouchablesEnabled,
    })),
    combine: (results) => {
      const map = new Map<string, Set<string>>();
      results.forEach((r, i) => {
        if (r.data) map.set(prefLeagueIds[i], new Set(r.data.untouchables || []));
      });
      return map;
    },
  });

  const untouchableMutation = useMutation({
    mutationFn: ({ leagueId, playerId, list }: {
      leagueId: string;
      playerId: string;
      list: 'untouchable' | 'none';
    }) => setAssetPref(leagueId, playerId, list),
    onSuccess: (_res, vars) => {
      queryClient.invalidateQueries({ queryKey: ['asset-prefs', vars.leagueId] });
      setToast({
        msg: vars.list === 'untouchable'
          ? 'Marked untouchable — never offered in trade ideas'
          : 'Untouchable removed',
        tone: 'success',
      });
    },
    onError: () => {
      setToast({ msg: 'Could not update untouchable — try again', tone: 'warn' });
    },
  });

  function handleToggleUntouchable(leagueId: string, p: Player) {
    if (untouchableMutation.isPending) return;
    haptics.selection();
    const marked = untouchablesByLeague.get(leagueId)?.has(p.id) ?? false;
    // S3 PRD-02 discoverability metric — gated so flag-off emits nothing new.
    if (menuOn) {
      track('untouchable_toggled', { marked: !marked }, 'Matches');
    }
    untouchableMutation.mutate({
      leagueId,
      playerId: p.id,
      list: marked ? 'none' : 'untouchable',
    });
  }

  const visibleMatches = useMemo(() => {
    if (filterLeagueId === 'all') return allMatches;
    return allMatches.filter((m) => m.league_id === filterLeagueId);
  }, [allMatches, filterLeagueId]);

  const visibleAwaiting = useMemo(() => {
    if (filterLeagueId === 'all') return allAwaiting;
    return allAwaiting.filter((a) => a.league_id === filterLeagueId);
  }, [allAwaiting, filterLeagueId]);

  // Filter chips: "All" + one per league. Default to the cached session
  // leagues so chips are stable even if the user has matches in leagues no
  // longer in their cache. Awaiting trades can also surface unknown
  // leagues — fold both lists into the "extras" set so neither segment is
  // missing chips for the leagues it actually contains.
  const filterChips = useMemo(() => {
    const seenIds = new Set(leagues.map((l) => l.league_id));
    const extrasMatches = allMatches
      .filter((m) => !seenIds.has(m.league_id))
      .map((m) => ({ id: m.league_id, name: m.league_name || 'Unknown league' }));
    const extrasAwaiting = allAwaiting
      .filter((a) => !seenIds.has(a.league_id))
      .map((a) => ({ id: a.league_id, name: a.league_name || 'Unknown league' }));
    const cachedChips = leagues.map((l) => ({ id: l.league_id, name: l.name }));
    // Dedupe extras by id
    const seenExtra = new Set<string>();
    const uniqueExtras = [...extrasMatches, ...extrasAwaiting].filter((e) => {
      if (seenExtra.has(e.id)) return false;
      seenExtra.add(e.id);
      return true;
    });
    return [{ id: 'all' as const, name: 'All' }, ...cachedChips, ...uniqueExtras];
  }, [leagues, allMatches, allAwaiting]);

  const filteredLeagueName =
    filterLeagueId === 'all'
      ? null
      : leagues.find((l) => l.league_id === filterLeagueId)?.name
        || allMatches.find((m) => m.league_id === filterLeagueId)?.league_name
        || allAwaiting.find((a) => a.league_id === filterLeagueId)?.league_name
        || 'this league';

  const isLoading = segment === 'mutual' ? matchesQuery.isLoading : awaitingQuery.isLoading;
  const isError   = segment === 'mutual' ? matchesQuery.isError   : awaitingQuery.isError;
  const isFetching =
    segment === 'mutual'
      ? matchesQuery.isFetching && !matchesQuery.isLoading
      : awaitingQuery.isFetching && !awaitingQuery.isLoading;
  const onRefresh = () => {
    if (segment === 'mutual') matchesQuery.refetch();
    else                      awaitingQuery.refetch();
  };

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        holdMs={toast?.holdMs ?? 1500}
        action={toast?.action}
        onDismiss={() => setToast(null)}
      />

      <View style={styles.header}>
        <Text style={styles.title}>Matches</Text>
        <Text style={styles.subtitle}>
          {segment === 'mutual'
            ? 'Trades where you and a leaguemate both said yes — across every league.'
            : "Trades you've liked — waiting on the other owner to swipe."}
        </Text>
        {/* Untouchables affordance hint — long-press is invisible without
            it. Only when the flag is on and there's something to press. */}
        {untouchablesEnabled
          && (segment === 'mutual' ? visibleMatches.length > 0 : visibleAwaiting.length > 0) ? (
          // S2 PRD-04 ride-along (visual.chalkline_cleanup): content-carrying
          // hint promotes chalk-faint → chalk-dim. S3 PRD-02: with the menu
          // live, the hold gesture opens the shared menu — say so.
          <Text style={[styles.hint, cleanupOn && styles.hintDim]}>
            {menuOn
              ? 'Hold a player for options — info and untouchable.'
              : "Hold a player you'd send to mark them untouchable."}
          </Text>
        ) : null}
      </View>

      {/* Segment toggle. Two-pill control to flip between mutual matches
          (default) and one-sided likes waiting on the counterparty. */}
      <View style={styles.segmentRow}>
        <SegmentBtn
          label="Mutual matches"
          active={segment === 'mutual'}
          onPress={() => setSegment('mutual')}
          testID="matches.segment.mutual"
        />
        <SegmentBtn
          label="Awaiting them"
          active={segment === 'awaiting'}
          onPress={() => setSegment('awaiting')}
          testID="matches.segment.awaiting"
        />
      </View>

      {/* League filter chip row. Horizontally scrollable so 5+ leagues
          don't cramp the viewport. Defaults to "All". flexGrow:0 keeps the
          row sized to its content even when the body below renders an
          empty-state View with flex:1. */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        keyboardShouldPersistTaps="always"
        style={styles.chipScroll}
        contentContainerStyle={styles.chipRow}
      >
        {filterChips.map((c) => {
          const isActive = c.id === filterLeagueId;
          return (
            <Pressable
              key={c.id}
              accessibilityRole="tab"
              accessibilityState={{ selected: isActive }}
              accessibilityLabel={`Filter: ${c.name}`}
              onPress={() => setFilterLeagueId(c.id)}
              hitSlop={{ top: 6, bottom: 6 }}
              style={({ pressed }) => [
                styles.chip,
                isActive && styles.chipActive,
                pressed && { backgroundColor: ink.ink3 },
              ]}
            >
              <Text style={[styles.chipText, isActive && styles.chipTextActive]}>
                {c.name}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>

      {(segment === 'mutual'
          ? matchesQuery.data === undefined && matchesQuery.isLoading
          : awaitingQuery.data === undefined && awaitingQuery.isLoading
        ) ? (
        <View style={styles.list}>
          {[0, 1, 2].map((i) => (
            <View key={i} style={{ gap: space.xs, marginBottom: space.lg }}>
              <View style={styles.matchHeader}>
                <View style={styles.skeletonLabel} />
                <View style={styles.skeletonTime} />
              </View>
              <View style={styles.skeletonCard} />
            </View>
          ))}
        </View>
      ) : isError ? (
        <View style={styles.centered}>
          <Text style={styles.errorText}>
            {readErrorCopy(
              segment === 'mutual' ? matchesQuery.error : awaitingQuery.error,
              segment === 'mutual' ? 'Could not load matches.' : 'Could not load pending trades.',
            )}
          </Text>
        </View>
      ) : segment === 'mutual' ? (
        visibleMatches.length === 0 ? (
          <View style={styles.centered}>
            <Text testID="matches.empty-text" style={styles.emptyTitle}>
              {filterLeagueId === 'all'
                ? 'No matches in any of your leagues yet'
                : `No matches in ${filteredLeagueName} yet`}
            </Text>
            <Text style={styles.emptyBody}>
              Head to the Trades tab and swipe on some proposals. When a
              leaguemate likes the same trade, it'll show up here.
            </Text>
            {/* S4 PRD-05 (ux.empty_state_ctas): the primary button DOES what
                the copy says — navigate into the core loop. Refresh demotes
                to a quiet secondary. Flag off: Refresh alone, as before. */}
            {emptyCtasOn ? (
              <>
                <Button
                  testID="matches.go-to-trades"
                  label="Go to Trades"
                  variant="primary"
                  onPress={() => navigation.navigate('Trades')}
                />
                <Button label="Refresh" variant="ghost" compact onPress={onRefresh} />
              </>
            ) : (
              <Button label="Refresh" variant="secondary" compact onPress={onRefresh} />
            )}
            {/* S4 PRD-01 (ux.help_surface): answer "how does matching work?"
                at the moment the empty inbox raises it. */}
            {helpOn ? (
              <Pressable
                testID="matches.matching-help"
                onPress={() => {
                  track('help_opened', { topic: 'matching' }, 'Matches');
                  setMatchingHelpOpen(true);
                }}
                accessibilityRole="button"
                accessibilityLabel="How matching works"
                hitSlop={8}
                style={styles.helpLink}
              >
                {({ pressed }) => (
                  <Text style={[styles.helpLinkText, pressed && { color: chalk.base }]}>
                    How matching works
                  </Text>
                )}
              </Pressable>
            ) : null}
          </View>
        ) : (
          <FlatList
            contentContainerStyle={styles.list}
            data={visibleMatches}
            keyExtractor={(m) => m.match_id}
            refreshControl={
              <RefreshControl
                refreshing={isFetching}
                onRefresh={onRefresh}
                tintColor={ice.base}
              />
            }
            renderItem={({ item }) => (
              <View style={{ gap: space.xs }}>
                {/* League badge — only shown in the "All" view; redundant
                    when a single-league filter is active. */}
                {filterLeagueId === 'all' && item.league_name ? (
                  <View style={styles.leagueBadgeRow}>
                    <Badge label={item.league_name} />
                  </View>
                ) : null}
                <View style={styles.matchHeader}>
                  <View style={styles.matchLabelRow}>
                    <Icon name="match" size={16} color={semantic.pos} />
                    <Text style={styles.matchLabel}>
                      New match with @{item.counterparty_username}
                    </Text>
                  </View>
                  <Text style={[styles.matchTime, cleanupOn && styles.matchTimeDim]}>{relativeTime(item.created_at)}</Text>
                </View>
                <TradeCardComp
                  variant="match"
                  data={matchToTradeCardShape(item, activeLeague?.league_id)}
                  onDismiss={() => handleDismiss(item)}
                  acting={dismissMutation.isPending}
                  showSend
                  untouchableIds={
                    untouchablesEnabled
                      ? untouchablesByLeague.get(item.league_id)
                      : undefined
                  }
                  onToggleUntouchable={
                    untouchablesEnabled
                      ? (p) => handleToggleUntouchable(item.league_id, p)
                      : undefined
                  }
                  onPlayerMenu={
                    menuOn
                      ? (p, side) => {
                          haptics.selection();
                          track(
                            'player_menu_opened',
                            { surface: 'matches', side },
                            'Matches',
                          );
                          setMenuTarget({ leagueId: item.league_id, player: p, side });
                        }
                      : undefined
                  }
                />
              </View>
            )}
            ItemSeparatorComponent={() => <View style={{ height: space.lg }} />}
          />
        )
      ) : (
        // Awaiting-them segment
        visibleAwaiting.length === 0 ? (
          <View style={styles.centered}>
            <Text style={styles.emptyTitle}>No pending trades.</Text>
            <Text style={styles.emptyBody}>
              Swipe more in the Trades tab.
            </Text>
            {/* S4 PRD-05 — same rule as the mutual empty state. */}
            {emptyCtasOn ? (
              <>
                <Button
                  testID="matches.go-to-trades"
                  label="Go to Trades"
                  variant="primary"
                  onPress={() => navigation.navigate('Trades')}
                />
                <Button label="Refresh" variant="ghost" compact onPress={onRefresh} />
              </>
            ) : (
              <Button label="Refresh" variant="secondary" compact onPress={onRefresh} />
            )}
          </View>
        ) : (
          <FlatList
            contentContainerStyle={styles.list}
            data={visibleAwaiting}
            keyExtractor={(a) => `${a.league_id}:${a.trade_id}`}
            refreshControl={
              <RefreshControl
                refreshing={isFetching}
                onRefresh={onRefresh}
                tintColor={ice.base}
              />
            }
            renderItem={({ item }) => (
              <View style={{ gap: space.xs }}>
                {filterLeagueId === 'all' && item.league_name ? (
                  <View style={styles.leagueBadgeRow}>
                    <Badge label={item.league_name} />
                  </View>
                ) : null}
                <View style={styles.matchHeader}>
                  <Text style={styles.awaitingLabel}>
                    Waiting on @{item.counterparty_username}
                  </Text>
                  <Text style={[styles.matchTime, cleanupOn && styles.matchTimeDim]}>{relativeTime(item.liked_at)}</Text>
                </View>
                {/* Reuse swipe variant — no Accept/Decline buttons because
                    the user has already swiped accept. They're just waiting
                    on the other owner. */}
                <TradeCardComp
                  variant="swipe"
                  data={awaitingToTradeCardShape(item, activeLeague?.league_id)}
                  showSend
                  untouchableIds={
                    untouchablesEnabled
                      ? untouchablesByLeague.get(item.league_id)
                      : undefined
                  }
                  onToggleUntouchable={
                    untouchablesEnabled
                      ? (p) => handleToggleUntouchable(item.league_id, p)
                      : undefined
                  }
                  onPlayerMenu={
                    menuOn
                      ? (p, side) => {
                          haptics.selection();
                          track(
                            'player_menu_opened',
                            { surface: 'matches_awaiting', side },
                            'Matches',
                          );
                          setMenuTarget({ leagueId: item.league_id, player: p, side });
                        }
                      : undefined
                  }
                />
              </View>
            )}
            ItemSeparatorComponent={() => <View style={{ height: space.lg }} />}
          />
        )
      )}

      {/* S3 PRD-02 (ux.player_context_menu) — shared long-press menu.
          menuTarget is only ever set while the flag is on. */}
      <PlayerContextMenu
        visible={!!menuTarget}
        player={menuTarget?.player ?? null}
        actions={menuTarget ? menuActionsFor(menuTarget) : []}
        onClose={() => setMenuTarget(null)}
      />

      {/* S4 PRD-01 (ux.help_surface) — "How matching works" in place. */}
      {helpOn ? (
        <HelpSheet
          visible={matchingHelpOpen}
          title="How matching works"
          body={
            'When you like a trade, we quietly show its mirror to the other ' +
            'owner in their own deck. If they like it too, it becomes a ' +
            'mutual match and lands here — neither side sees a one-way ' +
            'like, so there is no pressure until you both said yes.'
          }
          readMoreUrl={`${getBaseUrl()}/faq.html`}
          topic="matching"
          onClose={() => setMatchingHelpOpen(false)}
        />
      ) : null}
    </SafeAreaView>
  );

  // S3 PRD-02 — per-surface commands for the shared player context menu.
  function menuActionsFor(target: {
    leagueId: string;
    player: Player;
    side: 'give' | 'receive';
  }): PlayerMenuAction[] {
    const { leagueId, player, side } = target;
    const actions: PlayerMenuAction[] = [];
    if (side === 'give' && untouchablesEnabled) {
      const marked = untouchablesByLeague.get(leagueId)?.has(player.id) ?? false;
      actions.push({
        key: marked ? 'untouchable-remove' : 'untouchable-add',
        label: marked ? 'Remove untouchable' : 'Mark untouchable',
        hint: marked
          ? 'Allow this player in trade ideas again'
          : 'Never offered from your roster in trade ideas',
        onPress: () => {
          setMenuTarget(null);
          handleToggleUntouchable(leagueId, player);
        },
      });
    }
    return actions;
  }
}

function SegmentBtn({
  label,
  active,
  onPress,
  testID,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
  testID?: string;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      style={({ pressed }) => [
        styles.segmentBtn,
        active && styles.segmentBtnActive,
        pressed && { backgroundColor: ink.ink3 },
      ]}
    >
      <Text style={[styles.segmentText, active && styles.segmentTextActive]}>
        {label}
      </Text>
    </Pressable>
  );
}

// TradeMatch and TradeCard have overlapping but not identical shapes.
// Cross-league enrichment (server.py: /api/trades/matches/all) provides
// names + teams + positions as parallel arrays — use those when present.
// Falls back to ID-as-name / "FA" / "FLX" (legacy behavior, only happens
// when the backend hasn't been redeployed with the enrichment yet).
function matchToTradeCardShape(m: TradeMatch, fallbackLeague: string | undefined) {
  const POS_UNKNOWN = 'FLX' as any;
  const give = m.my_side_player_ids.map((id, i): Player => ({
    id,
    name:     m.my_side_player_names?.[i]     || id,
    position: m.my_side_player_positions?.[i] || POS_UNKNOWN,
    team:     m.my_side_player_teams?.[i]     || '',
  }));
  const recv = m.their_side_player_ids.map((id, i): Player => ({
    id,
    name:     m.their_side_player_names?.[i]     || id,
    position: m.their_side_player_positions?.[i] || POS_UNKNOWN,
    team:     m.their_side_player_teams?.[i]     || '',
  }));
  return {
    trade_id:           m.match_id,
    league_id:          m.league_id || fallbackLeague || '',
    give_player_ids:    m.my_side_player_ids,
    receive_player_ids: m.their_side_player_ids,
    give_players:       give,
    receive_players:    recv,
    opponent_user_id:   m.counterparty_user_id,
    opponent_username:  m.counterparty_username,
    match_score:        100,
    fairness:           1,
  };
}

// Same adapter pattern for awaiting trades — parallel TradeMatch shape so
// we don't pay for a second TradeCard variant. Match score is unknown for
// historical likes (the in-memory card may not still be around), so we
// show 100 to keep the strength bar consistent with mutual matches.
function awaitingToTradeCardShape(a: AwaitingTrade, fallbackLeague: string | undefined) {
  const POS_UNKNOWN = 'FLX' as any;
  const give = a.my_side_player_ids.map((id, i): Player => ({
    id,
    name:     a.my_side_player_names?.[i] || id,
    position: POS_UNKNOWN,
    team:     '',
  }));
  const recv = a.their_side_player_ids.map((id, i): Player => ({
    id,
    name:     a.their_side_player_names?.[i] || id,
    position: POS_UNKNOWN,
    team:     '',
  }));
  return {
    trade_id:           a.trade_id,
    league_id:          a.league_id || fallbackLeague || '',
    give_player_ids:    a.my_side_player_ids,
    receive_player_ids: a.their_side_player_ids,
    give_players:       give,
    receive_players:    recv,
    opponent_user_id:   a.counterparty_user_id,
    opponent_username:  a.counterparty_username,
    match_score:        100,
    fairness:           1,
  };
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  header: { paddingHorizontal: space.lg, paddingVertical: space.md },
  title: { ...type.display },
  subtitle: { ...type.bodySm, marginTop: space.xs },
  hint: { ...type.bodySm, color: chalk.faint, marginTop: space.xs },
  // S2 PRD-04 ride-along (visual.chalkline_cleanup): content-carrying text
  // never sits at chalk-faint (3.4:1) — promote to chalk-dim.
  hintDim: { color: chalk.dim },
  matchTimeDim: { color: chalk.dim },
  // S4 PRD-01 — quiet "How matching works" link on the empty state.
  helpLink: {
    minHeight: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  helpLinkText: {
    ...type.bodySm,
    color: chalk.dim,
    fontFamily: fonts.uiSemi,
  },

  // flexGrow:0 prevents the horizontal ScrollView from stretching to fill
  // remaining vertical space when the body below is an empty-state View.
  chipScroll: { flexGrow: 0, flexShrink: 0 },

  // Segmented group per PositionTabs spec: 1px hairline group at radii.sm;
  // active segment = ink3 fill + 2px ice underline (ice use: active state).
  segmentRow: {
    flexDirection: 'row',
    marginHorizontal: space.lg,
    marginBottom: space.sm,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  segmentBtn: {
    flex: 1,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
    backgroundColor: 'transparent',
  },
  segmentBtnActive: {
    backgroundColor: ink.ink3,
    borderBottomColor: ice.base,
  },
  segmentText: { ...type.label },
  segmentTextActive: { color: chalk.base },

  chipRow: {
    paddingHorizontal: space.lg,
    paddingBottom: space.sm,
    gap: space.xs,
    alignItems: 'center',
  },
  // Chalkline badge construction, sized up for touch: 1px border in the
  // encode color + chalk text on ink. Active = ice border (active state).
  chip: {
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    minHeight: 32,
    justifyContent: 'center',
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    backgroundColor: 'transparent',
  },
  chipActive: {
    borderColor: ice.base,
  },
  chipText: { ...type.label },
  chipTextActive: { color: chalk.base },

  list: { padding: space.lg, paddingBottom: 96 },
  leagueBadgeRow: { flexDirection: 'row', paddingHorizontal: space.xs },
  matchHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: space.xs,
  },
  matchLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    flexShrink: 1,
  },
  matchLabel: {
    ...type.bodySm,
    fontFamily: fonts.uiSemi,
    color: semantic.pos,
    flexShrink: 1,
  },
  awaitingLabel: {
    ...type.bodySm,
    fontFamily: fonts.uiSemi,
    flexShrink: 1,
  },
  // Timestamps are data — Plex Mono, chalk-faint (ActivityRow convention).
  matchTime: { ...type.data, color: chalk.faint },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: space.xl,
    gap: space.md,
  },
  errorText: { ...type.bodySm, color: semantic.neg },

  // Skeleton tiles — same outer dimensions as a real TradeCard match
  // tile (ink-1 surface, hairline, radii.md) so the page shape is stable
  // on first paint. Static — no shimmer/animation library introduced.
  skeletonCard: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    height: 220,
  },
  skeletonLabel: {
    width: 180,
    height: 12,
    borderRadius: radii.xs,
    backgroundColor: ink.ink3,
  },
  skeletonTime: {
    width: 48,
    height: 10,
    borderRadius: radii.xs,
    backgroundColor: ink.ink3,
  },
  emptyTitle: { ...type.heading, textAlign: 'center' },
  emptyBody: {
    ...type.bodySm,
    textAlign: 'center',
    maxWidth: 340,
  },
});
