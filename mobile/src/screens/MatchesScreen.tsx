import React, { useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  Linking,
  Alert,
  Pressable,
  ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { haptics } from '../utils/haptics';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { ink, chalk, volt, semantic, space, radii, type, fonts } from '../theme/chalkline';
import { Button, Badge, Icon } from '../components/chalkline';
import TradeCardComp from '../components/TradeCard';
import Toast from '../components/Toast';
import { getAllMatches, getAwaitingTrades, setMatchDisposition } from '../api/trades';
import { useSession } from '../state/useSession';
import { relativeTime } from '../utils/relativeTime';
import type { TradeMatch, AwaitingTrade, Player } from '../shared/types';

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
  const leagues = useSession((s) => s.leagues);
  const activeLeague = useSession((s) => s.league);
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);
  const [filterLeagueId, setFilterLeagueId] = useState<LeagueFilter>('all');
  const [segment, setSegment] = useState<Segment>('mutual');

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

  const dispMutation = useMutation({
    mutationFn: ({ id, d }: { id: string; d: 'accepted' | 'declined' }) =>
      setMatchDisposition(id, d),
    onMutate: async ({ id }) => {
      // Optimistic — drop the match from the list so the UI feels instant.
      // Same query key as above; using a different key here was the bug
      // before this refactor.
      const prev = queryClient.getQueryData<TradeMatch[]>(['matches', 'all']);
      if (prev) {
        queryClient.setQueryData(
          ['matches', 'all'],
          prev.filter((m) => m.match_id !== id),
        );
      }
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(['matches', 'all'], ctx.prev);
      setToast({ msg: 'Action failed — try again', tone: 'warn' });
    },
    onSuccess: (_res, vars) => {
      if (vars.d === 'accepted') {
        haptics.success();
      }
      // An accept/decline shouldn't just disappear the match from the
      // Mutual segment — the same match can sit in the "Awaiting them"
      // bucket (when only the counterparty has yet to swipe) and in the
      // user's liked-trades list. Invalidate both so the inbox is
      // consistent across segments without a manual refresh. The match
      // inbox is cross-league, so we invalidate every league's
      // liked-trades cache via the partial-key match (TanStack matches
      // any queryKey that starts with the supplied array).
      // Mirrors api-layer review #A2 + silent-bugs review bug #5.
      queryClient.invalidateQueries({ queryKey: ['awaiting-trades'] });
      queryClient.invalidateQueries({ queryKey: ['liked-trades'] });
    },
  });

  async function handleAccept(m: TradeMatch) {
    // Wait for the disposition POST to settle BEFORE deep-linking. The
    // previous fire-and-forget pattern would optimistically remove the
    // match from the list and then leave the user on Sleeper.com if the
    // backend later 500'd — the rollback toast would only render after
    // they switched back to the app, which is confusing.
    //
    // mutateAsync re-throws on failure (onError still fires for the
    // optimistic rollback), so the catch keeps the user inside the app
    // and the existing onError toast surfaces a real failure. On
    // success: deep-link.
    try {
      await dispMutation.mutateAsync({ id: m.match_id, d: 'accepted' });
    } catch {
      // onError already toasts + rolls back the optimistic removal.
      return;
    }
    // Deep-link to Sleeper. Sleeper's trade-propose deep link format:
    //   https://sleeper.com/leagues/<league_id>/trade
    const url = `https://sleeper.com/leagues/${m.league_id}/trade`;
    try {
      const can = await Linking.canOpenURL(url);
      if (can) await Linking.openURL(url);
      else Alert.alert('Accepted — open Sleeper to propose the trade.', url);
    } catch {
      Alert.alert('Accepted', 'Open Sleeper manually to propose the trade.');
    }
  }

  function handleDecline(m: TradeMatch) {
    dispMutation.mutate({ id: m.match_id, d: 'declined' });
  }

  const allMatches: TradeMatch[] = matchesQuery.data || [];
  const allAwaiting: AwaitingTrade[] = awaitingQuery.data || [];

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
        onDismiss={() => setToast(null)}
      />

      <View style={styles.header}>
        <Text style={styles.title}>Matches</Text>
        <Text style={styles.subtitle}>
          {segment === 'mutual'
            ? 'Trades where you and a leaguemate both said yes — across every league.'
            : "Trades you've liked — waiting on the other owner to swipe."}
        </Text>
      </View>

      {/* Segment toggle. Two-pill control to flip between mutual matches
          (default) and one-sided likes waiting on the counterparty. */}
      <View style={styles.segmentRow}>
        <SegmentBtn
          label="Mutual matches"
          active={segment === 'mutual'}
          onPress={() => setSegment('mutual')}
        />
        <SegmentBtn
          label="Awaiting them"
          active={segment === 'awaiting'}
          onPress={() => setSegment('awaiting')}
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
            {segment === 'mutual' ? 'Could not load matches.' : 'Could not load pending trades.'}
          </Text>
        </View>
      ) : segment === 'mutual' ? (
        visibleMatches.length === 0 ? (
          <View style={styles.centered}>
            <Text style={styles.emptyTitle}>
              {filterLeagueId === 'all'
                ? 'No matches in any of your leagues yet'
                : `No matches in ${filteredLeagueName} yet`}
            </Text>
            <Text style={styles.emptyBody}>
              Head to the Trades tab and swipe on some proposals. When a
              leaguemate likes the same trade, it'll show up here.
            </Text>
            <Button label="Refresh" variant="secondary" compact onPress={onRefresh} />
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
                tintColor={volt.base}
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
                  <Text style={styles.matchTime}>{relativeTime(item.created_at)}</Text>
                </View>
                <TradeCardComp
                  variant="match"
                  data={matchToTradeCardShape(item, activeLeague?.league_id)}
                  onAccept={() => handleAccept(item)}
                  onDecline={() => handleDecline(item)}
                  acting={dispMutation.isPending}
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
            <Button label="Refresh" variant="secondary" compact onPress={onRefresh} />
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
                tintColor={volt.base}
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
                  <Text style={styles.matchTime}>{relativeTime(item.liked_at)}</Text>
                </View>
                {/* Reuse swipe variant — no Accept/Decline buttons because
                    the user has already swiped accept. They're just waiting
                    on the other owner. */}
                <TradeCardComp
                  variant="swipe"
                  data={awaitingToTradeCardShape(item, activeLeague?.league_id)}
                />
              </View>
            )}
            ItemSeparatorComponent={() => <View style={{ height: space.lg }} />}
          />
        )
      )}
    </SafeAreaView>
  );
}

function SegmentBtn({
  label,
  active,
  onPress,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
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

  // flexGrow:0 prevents the horizontal ScrollView from stretching to fill
  // remaining vertical space when the body below is an empty-state View.
  chipScroll: { flexGrow: 0, flexShrink: 0 },

  // Segmented group per PositionTabs spec: 1px hairline group at radii.sm;
  // active segment = ink3 fill + 2px volt underline (volt use: active state).
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
    borderBottomColor: volt.base,
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
  // encode color + chalk text on ink. Active = volt border (active state).
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
    borderColor: volt.base,
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
