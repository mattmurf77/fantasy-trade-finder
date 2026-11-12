import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';

import { Button, Icon, Text, TickLabel } from '../components/chalkline';
import ClaimSheet, { explainNoAdd, resolveAddPlatform, type ClaimTarget } from '../components/ClaimSheet';
import FeedbackFAB from '../components/FeedbackFAB';
import UsageTrendCard from '../components/UsageTrendCard';
import { UsageAvailabilitySheet, type UsageLeagueRow } from '../components/UsageLeagueList';
import { UsageStatsHeader, UsageStatsRow, statsTableWidth } from '../components/UsageStatsTable';
import { chalk, fonts, ice, ink, radii, scrim, shadowSheet, space, type } from '../theme/chalkline';
import { ApiError, getSessionRevision } from '../api/client';
import { track } from '../api/events';
import { getFreeAgents } from '../api/league';
import {
  capabilityAtTap,
  capabilityForRow,
  faMoveOpensSheet,
  prefetchLeagueCapability,
  prefetchListCapabilities,
  type FaMoveCapability,
} from '../api/faMove';
import { getUsageTrends, type UsageMetric, type UsagePeriodWeeks, type UsagePlayer } from '../api/usageTrends';
import { useFlag } from '../state/useFeatureFlags';
import { useFinderTargets } from '../state/useFinderTargets';
import { beginTradeSearch, dropPendingSearch, handoffDeckMode } from '../state/tradeSearchTrace';
import { NO_LEAGUE_ID, useSession } from '../state/useSession';
import { readErrorCopy } from '../utils/verification';
import {
  leagueFormatLine,
  newsSplit,
  nextSort,
  ownerName,
  periodOrder,
  periodSplit,
  presetWeeks,
  sortByLatestWeek,
  sortLabel,
  sortStatsRows,
  statusIn,
  toggleWeek,
  visiblePlayers,
  weeksLabel,
  weeksParam,
  type OwnershipFilter,
  type PositionFilter,
  type StatsSort,
  type UsageOrder,
  type UsagePeriod,
  type UsageUnit,
  type UsageView,
} from '../utils/usageTrends';

// Usage Trends (flag `usage_trends.enabled`, docs/plans/usage-trends/scope.md)
// — root-stack push from the Home hub's Usage Rates tile and the Free Agents
// link. Two views of
// the same server payload, flipped by a pill: Version A ("Simple", the
// operator-approved story cards) and Version B ("Raw stats", a per-week
// table with a total column). The server computes every number and the
// order (`rank`); this screen filters, renders and acts.

const METRICS: { key: UsageMetric; label: string }[] = [
  { key: 'snaps', label: 'Snaps' },
  { key: 'carries', label: 'Carries' },
  { key: 'targets', label: 'Targets' },
];
const OWNERSHIP: { key: OwnershipFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'rostered', label: 'Rostered' },
  { key: 'free_agents', label: 'Free agents' },
];
const POSITIONS: PositionFilter[] = ['ALL', 'RB', 'WR', 'TE'];
const PLAYS_NOUN: Record<UsageMetric, string> = { snaps: 'plays', carries: 'carries', targets: 'targets' };
const ORDERS: { key: UsageOrder; label: string }[] = [
  { key: 'jumps', label: 'Biggest jumps' },
  { key: 'week', label: 'Weekly share' },
];
const PERIODS: { key: UsagePeriod; label: string }[] = [
  { key: 'week', label: 'Last week' },
  { key: 'three_weeks', label: 'Last 3 weeks' },
];

// Remembered for the app session so the pill stays where the user left it.
let lastView: UsageView = 'simple';
// Version A's order toggle, remembered the same way. Biggest jumps by default.
let lastOrder: UsageOrder = 'jumps';
// Version A's period toggle, remembered the same way. Last week by default.
let lastPeriod: UsagePeriod = 'week';

type ListItem =
  | { kind: 'section'; key: string; title: string; sub: string }
  | { kind: 'player'; key: string; player: UsagePlayer };

export default function UsageTrendsScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const enabled = useFlag('usage_trends.enabled');
  const leagueId = useSession((s) => s.league?.league_id);
  const leagueName = useSession((s) => s.league?.league_name);
  const leagues = useSession((s) => s.leagues);
  const isDemo = useSession((s) => s.isDemo);

  const [view, setView] = useState<UsageView>(lastView);
  const [order, setOrder] = useState<UsageOrder>(lastOrder);
  const [period, setPeriod] = useState<UsagePeriod>(lastPeriod);
  const [metric, setMetric] = useState<UsageMetric>('snaps');
  const [ownership, setOwnership] = useState<OwnershipFilter>(route.params?.ownership ?? 'all');
  const [positionFilter, setPositionFilter] = useState<PositionFilter>('ALL');
  const [units, setUnits] = useState<Record<UsageView, UsageUnit>>({ simple: 'share', stats: 'count' });
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [sheetPlayer, setSheetPlayer] = useState<UsagePlayer | null>(null);
  const [tradeSheetClosing, setTradeSheetClosing] = useState(false);
  const sheetDismissal = useRef<{ promise: Promise<void>; resolve: () => void } | null>(null);
  const tradeAction = useRef({ serial: 0, searchId: null as string | null });
  // A departure cancels the pending handoff, including while the native
  // sheet is dismissing. Keep the modal mounted until it confirms dismissal.
  useEffect(() => {
    const cancel = () => {
      tradeAction.current.serial++;
      if (tradeAction.current.searchId) dropPendingSearch(tradeAction.current.searchId);
      tradeAction.current.searchId = null;
      sheetDismissal.current?.resolve();
      sheetDismissal.current = null;
    };
    const unsubscribe = navigation.addListener('blur', cancel);
    return () => { unsubscribe(); cancel(); };
  }, [navigation]);
  const [expanded, setExpanded] = useState<string | null>(null);
  // Version B only: the user's column sort (null = server order).
  const [statsSort, setStatsSort] = useState<StatsSort | null>(null);
  // The user's week selection (Filters → Weeks). null = the server default,
  // the last four completed weeks.
  const [selectedWeeks, setSelectedWeeks] = useState<number[] | null>(null);
  const { width: screenWidth } = useWindowDimensions();
  // D1: `move` is the league's capability as cached at the Add tap.
  const [claim, setClaim] = useState<{
    target: ClaimTarget;
    leagueId: string;
    leagueName: string | null;
    move: FaMoveCapability | null;
  } | null>(null);
  const queryClient = useQueryClient();

  // The Free Agents link pushes `{ownership:'free_agents'}`; honour it on a
  // re-push into an already-mounted screen too.
  useEffect(() => {
    if (route.params?.ownership) setOwnership(route.params.ownership);
  }, [route.params?.ownership]);

  const focusId = leagueId && leagueId !== NO_LEAGUE_ID ? leagueId : undefined;
  const otherIds = useMemo(
    () => (leagues ?? []).map((l) => l.league_id).filter((id) => id && id !== focusId && id !== NO_LEAGUE_ID),
    [leagues, focusId],
  );
  // "Last 3 weeks" asks the server for its period reading (`period=3`). Last
  // week sends today's request under today's cache key.
  const periodParam = period === 'three_weeks' ? 3 : null;
  const query = useQuery({
    queryKey: ['usage-trends', focusId, otherIds.join(','), weeksParam(selectedWeeks),
      ...(periodParam ? ['period3'] : [])],
    queryFn: () => getUsageTrends(focusId as string, otherIds, selectedWeeks, periodParam),
    enabled: enabled && !!focusId,
    staleTime: 10 * 60_000,
    // A new week selection keeps the current list on screen while it loads.
    placeholderData: keepPreviousData,
  });
  // D1: the focused league's capability, prefetched once in the background
  // on mount and when the focused league changes, so the card's own Add can
  // route by it. A real Sleeper league session only (never demo or local, and
  // not with no league). Same trimmed fetch, 60 s staleTime and no retry as
  // the list prefetch; nothing on the Add path waits for it. While dark (or
  // with moves off) this is the visit's only capability read.
  useEffect(() => {
    if (!enabled || !focusId || resolveAddPlatform(focusId, isDemo) !== 'sleeper') return;
    void prefetchLeagueCapability(queryClient, focusId);
  }, [enabled, focusId, isDemo, queryClient]);
  const faQuery = useQuery({
    queryKey: ['free-agents', claim?.leagueId, 'ALL'],
    queryFn: () => getFreeAgents(claim!.leagueId, 'ALL'),
    enabled: !!claim,
    staleTime: 60_000,
  });

  const data = query.data;
  const weeks = data?.weeks ?? [];
  const latest = weeks.length ? weeks[weeks.length - 1] : null;
  const focus = data?.leagues?.[0];
  const unit = units[view];
  // The period applies to Simple only, and only with three or more weeks
  // selected (the pill hides otherwise). While the period response loads,
  // the previous one-week list is not shown under the period's titles; a
  // server without the reading (no `period` in a settled answer) falls back
  // to the one-week list rather than spinning.
  const periodShown = view === 'simple' && weeks.length >= 3;
  const periodMeta: UsagePeriodWeeks | null =
    periodShown && period === 'three_weeks' ? data?.period ?? null : null;
  const periodPending = periodShown && period === 'three_weeks' && !data?.period && query.isPlaceholderData;
  const list = useMemo(
    () => (data ? visiblePlayers(data.players, focus, metric, ownership, positionFilter) : []),
    [data, focus, metric, ownership, positionFilter],
  );
  const leagueMeta = useMemo(() => new Map((leagues ?? []).map((l) => [l.league_id, l])), [leagues]);

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <Pressable
          testID="usage-trends.info"
          accessibilityRole="button"
          accessibilityLabel="How Usage Trends works"
          onPress={() =>
            Alert.alert(
              'How Usage Trends works',
              'Snaps, carries and targets for running backs, receivers and tight ends over the ' +
                'last four finished weeks, from Sleeper. "% of team" is his share of what his team ' +
                'had that week. Bye weeks and games he missed are left out of averages. A big jump ' +
                'is a week well above his own earlier weeks. Newest jumps are listed first.',
            )
          }
          style={styles.headerBtn}
        >
          <Icon name="info" size={20} color={chalk.dim} />
        </Pressable>
      ),
    });
  }, [navigation]);

  const reportView = useCallback(
    (next: { view?: UsageView; metric?: UsageMetric; ownership?: OwnershipFilter;
             sort?: StatsSort | null; weeks?: number[] | null; order?: UsageOrder;
             period?: UsagePeriod }) => {
      track('usage_trends_view_changed', {
        league_id: focusId,
        metric: next.metric ?? metric,
        ownership: next.ownership ?? ownership,
        view: next.view ?? view,
        sort: sortLabel(next.sort !== undefined ? next.sort : statsSort, weeks),
        weeks: weeksParam(next.weeks !== undefined ? next.weeks : selectedWeeks),
        order: next.order ?? order,
        period: next.period ?? period,
      }, 'UsageTrends');
    },
    [focusId, metric, ownership, view, statsSort, weeks, selectedWeeks, order, period],
  );

  const leagueRowsFor = useCallback(
    (p: UsagePlayer): UsageLeagueRow[] =>
      (data?.leagues ?? []).map((lg, i) => {
        const meta = leagueMeta.get(lg.league_id);
        return {
          league_id: lg.league_id,
          name: meta?.name ?? (i === 0 ? leagueName ?? 'This league' : 'Another league'),
          formatLine: leagueFormatLine(meta),
          isFocus: i === 0,
          status: statusIn(lg, p.player_id),
          owner: ownerName(lg, p.player_id),
        };
      }),
    [data, leagueMeta, leagueName],
  );

  const trackAction = (action: 'trade' | 'add' | 'rerank', p: UsagePlayer, lgId: string | undefined) => {
    const lg = data?.leagues.find((l) => l.league_id === lgId);
    track('usage_trends_action', {
      league_id: lgId,
      action,
      player_id: p.player_id,
      position: p.position,
      metric,
      signal: p[metric].signal?.kind ?? 'none',
      focus_status: statusIn(lg, p.player_id),
      ownership,
      view,
      order,
      period,
    }, 'UsageTrends');
  };

  // Acting in a league other than the focused one switches to it first
  // (the MatchesScreen precedent). Pins are cleared by any league switch,
  // so every caller writes its pins AFTER this resolves.
  const switchTo = async (lgId: string, quiet = false): Promise<boolean> => {
    const before = useSession.getState();
    if (before.switching || !before.hasToken || !before.user) return false;
    if (lgId === before.league?.league_id) return true;
    const target = (before.leagues ?? []).find((l) => l.league_id === lgId);
    if (!target) {
      if (!quiet) Alert.alert("Couldn't open that league", 'Pick it from your league list, then try again.');
      return false;
    }
    try {
      await useSession.getState().switchLeague({ league_id: target.league_id, league_name: target.name });
      const after = useSession.getState();
      return !after.switching && after.hasToken && after.user?.user_id === before.user.user_id
        && after.league?.league_id === lgId;
    } catch {
      if (!quiet) Alert.alert("Couldn't switch leagues", 'Try again in a moment.');
      return false;
    }
  };

  // A sheet is dismissing when the next Modal/Alert wants to appear; iOS
  // drops a presentation that starts mid-dismissal.
  const closeSheetFirst = async () => {
    if (!sheetPlayer) return;
    setSheetPlayer(null);
    await new Promise((r) => setTimeout(r, 450));
  };

  const closeTradeSheet = (): Promise<void> => {
    if (sheetDismissal.current) return sheetDismissal.current.promise;
    if (!sheetPlayer) return Promise.resolve();
    let resolve!: () => void;
    const promise = new Promise<void>((done) => { resolve = done; });
    sheetDismissal.current = { promise, resolve };
    setTradeSheetClosing(true);
    return promise;
  };
  const onTradeSheetDismissed = () => {
    const pending = sheetDismissal.current;
    sheetDismissal.current = null;
    setSheetPlayer(null);
    setTradeSheetClosing(false);
    pending?.resolve();
  };

  const doTrade = async (p: UsagePlayer, lgId: string) => {
    const before = useSession.getState();
    if (!navigation.isFocused() || before.switching || !before.hasToken || !before.user) return;
    const userId = before.user.user_id;
    const serial = ++tradeAction.current.serial;
    const revision = getSessionRevision();
    if (tradeAction.current.searchId) dropPendingSearch(tradeAction.current.searchId);
    trackAction('trade', p, lgId);
    const lg = data?.leagues.find((l) => l.league_id === lgId);
    const ownerKey = lg?.rosters[p.player_id];
    // R1 (time to suggestion, addendum v2): the tap starts the search only
    // when the hand-off will run one — it needs the owning partner (the
    // deck's auto-run gate); without one it lands on the builder.
    const searchId = ownerKey && !ownerKey.startsWith('roster:')
      ? beginTradeSearch({
          source: 'usage_trends',
          mode: handoffDeckMode(1),
          searchType: 'pinned',
          screen: 'UsageTrends',
          ...(lgId !== before.league?.league_id ? { scenario: 'cross_league_handoff' } : {}),
        })
      : null;
    tradeAction.current.searchId = searchId;
    // Dismissal and the authorized switch start together; neither adds an
    // arbitrary timer to the original tap's clock. No pins before both finish.
    const [, switched] = await Promise.all([closeTradeSheet(), switchTo(lgId, true)]);
    const current = useSession.getState();
    const stillCurrent = serial === tradeAction.current.serial && navigation.isFocused()
      && revision === getSessionRevision() && current.hasToken
      && current.user?.user_id === userId;
    if (!stillCurrent || !switched || current.switching || current.league?.league_id !== lgId) {
      if (searchId) dropPendingSearch(searchId);
      if (serial === tradeAction.current.serial) tradeAction.current.searchId = null;
      if (stillCurrent && !switched) Alert.alert("Couldn't switch leagues", 'Try again in a moment.');
      return;
    }
    const store = useFinderTargets.getState();
    store.setSide('give', []);
    store.setSide('receive', [{ id: p.player_id, name: p.name, position: p.position, team: p.team }]);
    store.setHandoff({
      ...(searchId ? { searchId } : {}),
      opponent:
        ownerKey && !ownerKey.startsWith('roster:')
          ? { userId: ownerKey, name: lg?.owners[ownerKey] ?? ownerKey }
          : null,
      autoRun: true,
    });
    tradeAction.current.searchId = null;
    navigation.navigate('Main', { screen: 'Trades', params: { screen: 'TradesHome' } });
  };

  // D1: the listed leagues' capabilities, prefetched in the background when an
  // availability list opens (the sheet, or an expanded row), each under its
  // own key (60 s staleTime, no retry); the cache keeps only `move` and the
  // rows' move_* fields. Only once the focused league's cached capability
  // says `submit` (dark or moves off: no list reads), then at most six of
  // the leagues where Add shows, Sleeper first (release-lead P2-A).
  const prefetchCapabilities = (rows: UsageLeagueRow[]) => {
    if (isDemo) return;
    prefetchListCapabilities(queryClient, focusId, rows, (id) => resolveAddPlatform(id, isDemo) === 'sleeper');
  };

  const doAdd = async (p: UsagePlayer, lgId: string) => {
    trackAction('add', p, lgId);
    const platform = resolveAddPlatform(lgId, isDemo);
    // D1 (scope §B1): the server's capability first, but only if it's already
    // cached, fresh (under 5 minutes) and not invalidated since; the tap never
    // waits for it. Otherwise (or on today's server) it routes exactly as
    // #509: Sleeper opens the sheet in hand-off, the rest get the alert. The
    // sheet still reads its own list after the switch.
    const cap = capabilityForRow(isDemo ? undefined : capabilityAtTap(queryClient, lgId), p.player_id);
    await closeSheetFirst();
    if (platform !== 'sleeper' && !faMoveOpensSheet(cap.move, cap.row)) {
      explainNoAdd(platform);
      return;
    }
    if (!(await switchTo(lgId))) return;
    setClaim({
      target: { player_id: p.player_id, name: p.name, position: p.position, team: p.team, ...cap.row },
      leagueId: lgId,
      // The tapped league's name, for the named CTA's "In {league}" (R28.26).
      leagueName: (leagues ?? []).find((l) => l.league_id === lgId)?.name ?? null,
      move: cap.move,
    });
  };

  const doRerank = (p: UsagePlayer) => {
    trackAction('rerank', p, focusId);
    navigation.navigate('Main', {
      screen: 'Rank',
      params: { screen: 'QuickSetTiers', params: { position: p.position, positionSeq: Date.now() } },
    });
  };

  const reportAvailability = (p: UsagePlayer) => {
    const rows = leagueRowsFor(p);
    track('usage_trends_availability_opened', {
      league_id: focusId,
      player_id: p.player_id,
      n_leagues: rows.filter((r) => r.status !== 'unknown').length,
      n_free_agent: rows.filter((r) => r.status === 'free_agent').length,
      view,
    }, 'UsageTrends');
  };

  const items: ListItem[] = useMemo(() => {
    if (view !== 'simple') {
      return sortStatsRows(list, metric, unit, statsSort)
        .map((p) => ({ kind: 'player' as const, key: p.player_id, player: p }));
    }
    const rows = (ps: UsagePlayer[]) => ps.map((p) => ({ kind: 'player' as const, key: p.player_id, player: p }));
    if (periodMeta) return periodItems(list, metric, order, unit, periodMeta);
    if (order === 'week') {
      if (!list.length || latest == null) return [];
      return [
        {
          kind: 'section', key: 's-week',
          title: unit === 'share' ? `Week ${latest} share of team ${PLAYS_NOUN[metric]}` : `Week ${latest} ${metric}`,
          sub: `Highest first. Anyone who didn't play in Week ${latest} is last.`,
        },
        ...rows(sortByLatestWeek(list, metric, unit, weeks.length)),
      ];
    }
    const { jumps, backOrNew } = newsSplit(list, metric, latest);
    const out: ListItem[] = [];
    if (jumps) {
      out.push({
        kind: 'section', key: 's-news', title: 'Biggest jumps last week',
        sub: `Players whose ${metric} jumped in Week ${latest}, biggest jump first.`,
      });
      out.push(...rows(list.slice(0, jumps)));
    }
    if (backOrNew) {
      out.push({
        kind: 'section', key: 's-back', title: 'Back or new last week',
        sub: `Returned from a missed game, or played their first game, in Week ${latest}.`,
      });
      out.push(...rows(list.slice(jumps, jumps + backOrNew)));
    }
    const n = jumps + backOrNew;
    if (list.length > n) {
      out.push({
        kind: 'section', key: 's-rest', title: n ? 'Everyone else' : 'All players',
        sub: `Recent changes first, then by share of team ${PLAYS_NOUN[metric]}.`,
      });
      out.push(...rows(list.slice(n)));
    }
    return out;
  }, [view, order, list, metric, latest, unit, statsSort, weeks.length, periodMeta]);

  const renderItem = ({ item }: { item: ListItem }) => {
    if (item.kind === 'section') {
      return (
        <View style={styles.section}>
          <TickLabel color={ice.base}>{item.title.toUpperCase()}</TickLabel>
          <Text style={type.bodySm}>{item.sub}</Text>
        </View>
      );
    }
    const p = item.player;
    const focusStatus = statusIn(focus, p.player_id);
    if (view === 'simple') {
      return (
        <View style={styles.cardWrap}>
          <UsageTrendCard
            player={p}
            metric={metric}
            unit={unit}
            weeks={weeks}
            order={order}
            period={periodMeta}
            focusStatus={focusStatus}
            leagueStatuses={(data?.leagues ?? []).map((lg) => statusIn(lg, p.player_id))}
            onAdd={() => focusId && doAdd(p, focusId)}
            onTrade={() => focusId && doTrade(p, focusId)}
            onRerank={() => doRerank(p)}
            onAvailability={() => {
              reportAvailability(p);
              prefetchCapabilities(leagueRowsFor(p));
              setSheetPlayer(p);
            }}
          />
        </View>
      );
    }
    const open = expanded === p.player_id;
    return (
      <UsageStatsRow
        player={p}
        metric={metric}
        unit={unit}
        weeks={weeks}
        focusStatus={focusStatus}
        expanded={open}
        leagueRows={open ? leagueRowsFor(p) : []}
        onToggle={() => {
          if (!open) {
            reportAvailability(p);
            prefetchCapabilities(leagueRowsFor(p));
          }
          setExpanded(open ? null : p.player_id);
        }}
        onAdd={() => focusId && doAdd(p, focusId)}
        onTrade={() => focusId && doTrade(p, focusId)}
        onRerank={() => doRerank(p)}
        onLeagueAdd={(lgId) => doAdd(p, lgId)}
        onLeagueTrade={(lgId) => doTrade(p, lgId)}
      />
    );
  };

  const errorBody = (query.error instanceof ApiError ? query.error.body : null) as
    | { error?: string; message?: string }
    | null;
  // A selection the server no longer accepts falls back to the default window.
  useEffect(() => {
    if (errorBody?.error === 'invalid_weeks' && selectedWeeks) setSelectedWeeks(null);
  }, [errorBody?.error, selectedWeeks]);

  let body: React.ReactNode;
  if (!enabled || errorBody?.error === 'feature_disabled') {
    body = <Centered testID="usage-trends.unavailable" text="Usage Trends isn't available yet." />;
  } else if (!focusId) {
    body = (
      <Centered testID="usage-trends.no-league" text="Connect a league to see usage trends.">
        <Button testID="usage-trends.pick-league" label="Pick a league" variant="primary"
          onPress={() => navigation.navigate('LeaguePicker')} />
      </Centered>
    );
  } else if (query.isLoading) {
    body = <View style={styles.center}><ActivityIndicator color={ice.base} /></View>;
  } else if (query.isError) {
    body = (
      <Centered
        testID="usage-trends.error"
        text={errorBody?.message ?? readErrorCopy(query.error, "Couldn't load usage trends.")}
      >
        <Button label="Try again" variant="ghost" compact onPress={() => query.refetch()} />
      </Centered>
    );
  } else if (data && !data.in_season) {
    body = (
      <Centered
        testID="usage-trends.off-season"
        text="Usage Trends is in-season only. It fills in once Week 1's games are done."
      />
    );
  } else if (periodPending) {
    body = <View style={styles.center}><ActivityIndicator color={ice.base} /></View>;
  } else {
    const list = (
      <FlatList
        testID="usage-trends.list"
        data={items}
        keyExtractor={(it) => it.key}
        renderItem={renderItem}
        contentContainerStyle={view === 'simple' ? styles.listSimple : styles.listStats}
        ListHeaderComponent={view === 'simple' ? (
          // Order and period share one wrapping row: side by side where they
          // fit, the period pill on its own line under the order on a phone.
          <View style={styles.orderRow}>
            <View style={styles.viewPill} accessibilityRole="tablist" accessibilityLabel="Order">
              {ORDERS.map((o) => {
                const on = order === o.key;
                return (
                  <Pressable
                    key={o.key}
                    testID={`usage-trends.order.${o.key}`}
                    accessibilityRole="tab"
                    accessibilityState={{ selected: on }}
                    onPress={() => {
                      if (on) return;
                      setOrder(o.key);
                      lastOrder = o.key;
                      reportView({ order: o.key });
                    }}
                    style={[styles.viewSeg, on && styles.viewSegOn]}
                  >
                    <Text scale="dense" style={[styles.viewText, on && styles.viewTextOn]}>
                      {o.key === 'week' && unit === 'count' ? 'Weekly count' : o.label}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
            {periodShown ? (
              <View style={styles.viewPill} accessibilityRole="tablist" accessibilityLabel="Period">
                {PERIODS.map((pr) => {
                  const on = period === pr.key;
                  return (
                    <Pressable
                      key={pr.key}
                      testID={`usage-trends.period.${pr.key}`}
                      accessibilityRole="tab"
                      accessibilityState={{ selected: on }}
                      onPress={() => {
                        if (on) return;
                        setPeriod(pr.key);
                        lastPeriod = pr.key;
                        reportView({ period: pr.key });
                      }}
                      style={[styles.viewSeg, on && styles.viewSegOn]}
                    >
                      <Text scale="dense" style={[styles.viewText, on && styles.viewTextOn]}>{pr.label}</Text>
                    </Pressable>
                  );
                })}
              </View>
            ) : null}
          </View>
        ) : null}
        refreshControl={
          <RefreshControl refreshing={query.isFetching && !query.isLoading}
            onRefresh={() => query.refetch()} tintColor={ice.base} />
        }
        ListEmptyComponent={
          <Centered
            testID="usage-trends.empty"
            text={
              ownership === 'free_agents'
                ? 'No free agents with recent usage in this league.'
                : ownership === 'rostered'
                  ? 'No rostered players match these filters.'
                  : 'No players match these filters.'
            }
          />
        }
      />
    );
    if (view === 'simple') {
      body = list;
    } else {
      // Version B: the header rides with the rows. Four weeks fit a phone;
      // a wider selection makes the whole table swipe sideways, so header
      // and rows always scroll together.
      const tableWidth = statsTableWidth(screenWidth, weeks.length);
      const wide = tableWidth > screenWidth;
      const table = (
        <View style={wide ? [styles.tableWide, { width: tableWidth }] : styles.table}>
          <UsageStatsHeader
            weeks={weeks}
            unit={unit}
            sort={statsSort}
            onSort={(key) => {
              const next = nextSort(statsSort, key);
              setStatsSort(next);
              reportView({ sort: next });
            }}
          />
          {list}
        </View>
      );
      body = wide ? (
        <ScrollView
          horizontal
          testID="usage-trends.table-scroll"
          contentContainerStyle={styles.tableScroll}
          showsHorizontalScrollIndicator
        >
          {table}
        </ScrollView>
      ) : table;
    }
  }

  const showControls = enabled && !!focusId && !!data?.in_season;
  // How many Filters-sheet settings differ from their defaults.
  const activeFilters = (positionFilter !== 'ALL' ? 1 : 0) + (selectedWeeks ? 1 : 0);

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']} testID="usage-trends.screen">
      {showControls ? (
        <View style={styles.controls}>
          <View style={styles.subRow}>
            {/* Two lines so "Weeks 1–4" never truncates beside the pill
                (the canvas preview cut it at 390pt); a long league name
                ellipsizes alone. */}
            <View style={styles.subText}>
              <Text style={styles.subLeague} numberOfLines={1}>{leagueName ?? 'Your league'}</Text>
              {weeks.length ? (
                <Text style={styles.sub} numberOfLines={1} testID="usage-trends.weeks-label">
                  {weeksLabel(weeks)}
                </Text>
              ) : null}
            </View>
            <View style={styles.viewPill} accessibilityRole="tablist">
              {(['simple', 'stats'] as const).map((v) => {
                const on = view === v;
                return (
                  <Pressable
                    key={v}
                    testID={`usage-trends.view.${v}`}
                    accessibilityRole="tab"
                    accessibilityState={{ selected: on }}
                    onPress={() => {
                      if (on) return;
                      setView(v);
                      lastView = v;
                      setExpanded(null);
                      reportView({ view: v });
                    }}
                    style={[styles.viewSeg, on && styles.viewSegOn]}
                  >
                    <Text scale="dense" style={[styles.viewText, on && styles.viewTextOn]}>
                      {v === 'simple' ? 'Simple' : 'Raw stats'}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          </View>
          <View style={styles.metricRow} accessibilityRole="tablist">
            {METRICS.map((m, i) => {
              const on = metric === m.key;
              return (
                <Pressable
                  key={m.key}
                  testID={`usage-trends.metric.${m.key}`}
                  accessibilityRole="tab"
                  accessibilityState={{ selected: on }}
                  onPress={() => {
                    if (on) return;
                    setMetric(m.key);
                    reportView({ metric: m.key });
                  }}
                  style={[styles.metricSeg, i > 0 && styles.metricSegDivider, on && styles.metricSegOn]}
                >
                  <Text style={[styles.segText, on && styles.segTextOn]}>{m.label}</Text>
                </Pressable>
              );
            })}
          </View>
          <View style={styles.ownRow}>
            <View style={styles.ownTabs} accessibilityRole="tablist">
              {OWNERSHIP.map((o) => {
                const on = ownership === o.key;
                return (
                  <Pressable
                    key={o.key}
                    testID={`usage-trends.ownership.${o.key}`}
                    accessibilityRole="tab"
                    accessibilityState={{ selected: on }}
                    onPress={() => {
                      if (on) return;
                      setOwnership(o.key);
                      reportView({ ownership: o.key });
                    }}
                    style={[styles.ownTab, on && styles.ownTabOn]}
                  >
                    <Text style={[styles.segText, on && styles.segTextOn]}>{o.label}</Text>
                  </Pressable>
                );
              })}
            </View>
            <Pressable
              testID="usage-trends.filters"
              accessibilityRole="button"
              accessibilityLabel={`Filters: weeks, position, show as count or percent${activeFilters ? `, ${activeFilters} changed` : ''}`}
              onPress={() => setFiltersOpen(true)}
              style={({ pressed }) => [styles.filtersBtn, pressed && styles.pressed]}
            >
              <Icon name="settings" size={16} color={chalk.base} />
              <Text style={styles.filtersText}>
                Filters{activeFilters ? ` · ${activeFilters}` : ''}
              </Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      <View style={styles.body}>{body}</View>

      {filtersOpen ? (
        <FiltersSheet
          position={positionFilter}
          unit={unit}
          available={data?.available_weeks ?? []}
          weeks={weeks}
          isDefaultWeeks={!selectedWeeks}
          onPosition={setPositionFilter}
          onUnit={(u) => setUnits((prev) => ({ ...prev, [view]: u }))}
          onClose={(nextWeeks) => {
            setFiltersOpen(false);
            // Weeks are committed when the sheet closes: one refetch per
            // change, not one per chip tap.
            if (nextWeeks !== undefined && weeksParam(nextWeeks) !== weeksParam(selectedWeeks)) {
              setSelectedWeeks(nextWeeks);
              setExpanded(null);
              reportView({ weeks: nextWeeks });
            }
          }}
        />
      ) : null}
      {sheetPlayer ? (
        <UsageAvailabilitySheet
          player={sheetPlayer}
          rows={leagueRowsFor(sheetPlayer)}
          visible={!tradeSheetClosing}
          immediateDismiss={tradeSheetClosing}
          onDismiss={onTradeSheetDismissed}
          onAdd={(lgId) => doAdd(sheetPlayer, lgId)}
          onTrade={(lgId) => doTrade(sheetPlayer, lgId)}
          onClose={() => setSheetPlayer(null)}
        />
      ) : null}
      {claim ? (
        <ClaimSheet
          key={`${claim.leagueId}:${claim.target.player_id}`}
          row={claim.target}
          leagueId={claim.leagueId}
          surface="usage_trends"
          capacity={faQuery.data?.roster_capacity}
          waivers={faQuery.data?.waivers}
          dropCandidates={faQuery.data?.drop_candidates}
          move={claim.move}
          refetch={async () => (await faQuery.refetch()).data}
          leagueName={claim.leagueName}
          onClose={() => setClaim(null)}
        />
      ) : null}
      {/* #188 — root-stack push: carries its own FAB above no tab bar. */}
      <FeedbackFAB activeScreen="UsageTrends" aboveTabBar={false} />
    </SafeAreaView>
  );
}

function Centered({ text, testID, children }: { text: string; testID: string; children?: React.ReactNode }) {
  return (
    <View style={styles.center} testID={testID}>
      <Text style={styles.centerText}>{text}</Text>
      {children}
    </View>
  );
}

function FiltersSheet({
  position,
  unit,
  available,
  weeks,
  isDefaultWeeks,
  onPosition,
  onUnit,
  onClose,
}: {
  position: PositionFilter;
  unit: UsageUnit;
  available: number[];
  weeks: number[];
  isDefaultWeeks: boolean;
  onPosition: (p: PositionFilter) => void;
  onUnit: (u: UsageUnit) => void;
  /** `weeks` is the draft week selection (null = default); undefined = unchanged. */
  onClose: (weeks?: number[] | null) => void;
}) {
  const chip = (on: boolean) => [styles.chip, on && styles.chipOn];
  // Draft selection: chips toggle locally and commit once, on close.
  const [draft, setDraft] = useState<number[] | null>(isDefaultWeeks ? null : weeks);
  const defaultWeeks = available.slice(-4);   // the server's default window
  const shown = draft ?? defaultWeeks;
  // A pick identical to the default IS the default (keeps "Last 4" lit and
  // avoids a pointless refetch).
  const close = () => onClose(draft && weeksParamEq(draft, defaultWeeks) ? null : draft);
  const preset = (key: 'last4' | 'last2' | 'season', label: string) => {
    const value = presetWeeks(key, available);
    const on = key === 'last4' ? draft === null : weeksParamEq(draft, value);
    return (
      <Pressable key={key} testID={`usage-trends.weeks.${key}`} accessibilityRole="button"
        accessibilityState={{ selected: on }} onPress={() => setDraft(value)} style={chip(on)}>
        <Text style={[styles.segText, on && styles.segTextOn]}>{label}</Text>
      </Pressable>
    );
  };
  return (
    <Modal visible transparent animationType="slide" onRequestClose={close}>
      <Pressable style={styles.backdrop} onPress={close} accessibilityRole="button" accessibilityLabel="Close" />
      <View style={styles.sheet} testID="usage-trends.filters-sheet">
        <SafeAreaView edges={['bottom']} style={styles.sheetContent}>
          <View style={styles.grabber} />
          <Text style={type.heading} accessibilityRole="header">Filters</Text>
          <View style={styles.filterGroup}>
            <TickLabel>WEEKS</TickLabel>
            <View style={styles.chips}>
              {preset('last4', 'Last 4')}
              {preset('last2', 'Last 2')}
              {preset('season', 'All season')}
            </View>
            <View style={styles.chips}>
              {available.map((w) => {
                const on = shown.includes(w);
                return (
                  <Pressable
                    key={w}
                    testID={`usage-trends.week.${w}`}
                    accessibilityRole="checkbox"
                    accessibilityLabel={`Week ${w}`}
                    accessibilityState={{ checked: on }}
                    onPress={() => setDraft(toggleWeek(shown, w))}
                    style={[styles.weekChip, on && styles.chipOn]}
                  >
                    <Text style={[styles.weekChipText, on && styles.segTextOn]}>{w}</Text>
                  </Pressable>
                );
              })}
            </View>
            <Text style={type.bodySm}>{weeksLabel(shown)} · averages and totals cover these weeks only.</Text>
          </View>
          <View style={styles.filterGroup}>
            <TickLabel>POSITION</TickLabel>
            <View style={styles.chips}>
              {POSITIONS.map((p) => (
                <Pressable key={p} testID={`usage-trends.position.${p.toLowerCase()}`} accessibilityRole="button"
                  accessibilityState={{ selected: position === p }} onPress={() => onPosition(p)} style={chip(position === p)}>
                  <Text style={[styles.segText, position === p && styles.segTextOn]}>{p === 'ALL' ? 'All' : p}</Text>
                </Pressable>
              ))}
            </View>
          </View>
          <View style={styles.filterGroup}>
            <TickLabel>SHOW AS</TickLabel>
            <View style={styles.chips}>
              {(['share', 'count'] as const).map((u) => (
                <Pressable key={u} testID={`usage-trends.unit.${u}`} accessibilityRole="button"
                  accessibilityState={{ selected: unit === u }} onPress={() => onUnit(u)} style={chip(unit === u)}>
                  <Text style={[styles.segText, unit === u && styles.segTextOn]}>
                    {u === 'share' ? '% of team' : 'Count'}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
          <Button testID="usage-trends.filters-done" label="Done" variant="secondary" onPress={close} />
        </SafeAreaView>
      </View>
    </Modal>
  );
}

// "Last 3 weeks": the list in the server's order for that reading
// (`periodOrder`, ranks only), split into sections the way the server ranked
// them. Section lines name the weeks each number covers.
function periodItems(
  list: UsagePlayer[], metric: UsageMetric, order: UsageOrder, unit: UsageUnit, meta: UsagePeriodWeeks,
): ListItem[] {
  const rows = (ps: UsagePlayer[]) => ps.map((p) => ({ kind: 'player' as const, key: p.player_id, player: p }));
  const ordered = periodOrder(list, metric, order, unit);
  if (!ordered.length) return [];
  const span = weeksLabel(meta.weeks);
  const noun = PLAYS_NOUN[metric];
  if (order === 'week') {
    return [
      {
        kind: 'section', key: 's-week3',
        title: unit === 'share' ? `${span} average share of team ${noun}` : `${span} average ${metric} a game`,
        sub: 'Highest first, over the games each player played. Anyone with fewer than 2 games is last.',
      },
      ...rows(ordered),
    ];
  }
  const before = meta.base_weeks.length ? weeksLabel(meta.base_weeks) : null;
  const split = periodSplit(ordered, metric);
  const out: ListItem[] = [];
  if (split.jumps) {
    out.push({
      kind: 'section', key: 's-news3', title: 'Biggest jumps over the last 3 weeks',
      sub: `Share of team ${noun} in ${span} against ${before}, biggest jump first.`,
    });
    out.push(...rows(ordered.slice(0, split.jumps)));
  }
  if (split.backOrNew) {
    out.push({
      kind: 'section', key: 's-back3', title: 'Back or new over the last 3 weeks',
      sub: `No games in ${before}, then a real role in ${span}.`,
    });
    out.push(...rows(ordered.slice(split.jumps, split.jumps + split.backOrNew)));
  }
  const n = split.jumps + split.backOrNew;
  if (ordered.length > n) {
    out.push({
      kind: 'section', key: 's-rest3', title: n ? 'Everyone else' : 'All players',
      sub: before
        ? `By share of team ${noun} in ${span}. Anyone with fewer than 2 games is last.`
        : `No earlier weeks to compare with yet. By share of team ${noun} in ${span}.`,
    });
    out.push(...rows(ordered.slice(n)));
  }
  return out;
}

function weeksParamEq(a: number[] | null, b: number[] | null): boolean {
  return weeksParam(a) === weeksParam(b);
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  body: { flex: 1 },
  headerBtn: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  controls: { paddingTop: space.sm, gap: space.sm, borderBottomWidth: 1, borderBottomColor: ink.line },
  subRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm, paddingHorizontal: space.lg },
  subText: { flex: 1, minWidth: 0 },
  subLeague: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
  sub: { ...type.bodySm },
  viewPill: {
    flexDirection: 'row',
    borderWidth: 1,
    borderColor: ink.lineStrongA11y,
    borderRadius: radii.pill,
    padding: 2,
  },
  viewSeg: { minHeight: 32, paddingHorizontal: space.md, justifyContent: 'center', borderRadius: radii.pill },
  viewSegOn: { backgroundColor: ink.ink3, borderWidth: 1, borderColor: ice.base },
  viewText: { ...type.bodySm, fontFamily: fonts.uiSemi },
  viewTextOn: { color: chalk.base },
  metricRow: {
    flexDirection: 'row',
    marginHorizontal: space.lg,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  metricSeg: {
    flex: 1,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  metricSegDivider: { borderLeftWidth: 1, borderLeftColor: ink.line },
  metricSegOn: { backgroundColor: ink.ink3, borderBottomColor: ice.base },
  segText: { ...type.body, fontFamily: fonts.uiSemi, color: chalk.dim },
  segTextOn: { color: chalk.base },
  ownRow: { flexDirection: 'row', alignItems: 'center', gap: space.xs, paddingHorizontal: space.lg },
  ownTabs: { flexDirection: 'row', flex: 1, gap: 2 },
  ownTab: {
    height: 44,
    paddingHorizontal: 10,
    justifyContent: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  ownTabOn: { borderBottomColor: ice.base },
  filtersBtn: {
    height: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: space.md,
    borderWidth: 1,
    borderColor: ink.lineStrongA11y,
    borderRadius: radii.sm,
  },
  filtersText: { ...type.body, fontFamily: fonts.uiSemi },
  pressed: { backgroundColor: ink.ink3 },
  section: { gap: 2, paddingTop: space.md, paddingBottom: space.sm },
  orderRow: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, paddingTop: space.md },
  cardWrap: { marginBottom: space.sm },
  listSimple: { paddingHorizontal: space.lg, paddingBottom: space.xxxl * 2 },
  listStats: { paddingBottom: space.xxxl * 2 },
  center: { alignItems: 'center', justifyContent: 'center', paddingVertical: space.xxl, paddingHorizontal: space.lg, gap: space.md },
  centerText: { ...type.body, color: chalk.dim, textAlign: 'center' },

  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    ...shadowSheet,
  },
  sheetContent: { paddingHorizontal: space.lg, paddingBottom: space.xl, gap: space.lg },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    borderRadius: radii.xs,
    backgroundColor: ink.lineStrongA11y,
    marginTop: space.sm,
  },
  filterGroup: { gap: space.sm },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: {
    minHeight: 44,
    paddingHorizontal: 14,
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: ink.lineStrongA11y,
    borderRadius: radii.sm,
  },
  chipOn: { backgroundColor: ink.ink3, borderColor: ice.base },
  weekChip: {
    minWidth: 44,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: ink.lineStrongA11y,
    borderRadius: radii.sm,
  },
  weekChipText: { ...type.data, color: chalk.dim },
  table: { flex: 1 },
  // Inside the horizontal ScrollView: explicit width, full height (the row
  // container's cross-axis stretch) — never flex:1, which would override it.
  tableWide: { alignSelf: 'stretch' },
  tableScroll: { flexGrow: 1 },
});
