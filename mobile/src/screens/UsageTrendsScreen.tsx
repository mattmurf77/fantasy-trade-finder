import React, { useCallback, useEffect, useLayoutEffect, useMemo, useState } from 'react';
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
import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { Button, Icon, Text, TickLabel } from '../components/chalkline';
import ClaimSheet, { explainNoAdd, resolveAddPlatform, type ClaimTarget } from '../components/ClaimSheet';
import FeedbackFAB from '../components/FeedbackFAB';
import UsageTrendCard from '../components/UsageTrendCard';
import { UsageAvailabilitySheet, type UsageLeagueRow } from '../components/UsageLeagueList';
import { UsageStatsHeader, UsageStatsRow, statsTableWidth } from '../components/UsageStatsTable';
import { chalk, fonts, ice, ink, radii, scrim, shadowSheet, space, type } from '../theme/chalkline';
import { ApiError } from '../api/client';
import { track } from '../api/events';
import { getFreeAgents } from '../api/league';
import { getUsageTrends, type UsageMetric, type UsagePlayer } from '../api/usageTrends';
import { useFlag } from '../state/useFeatureFlags';
import { useFinderTargets } from '../state/useFinderTargets';
import { NO_LEAGUE_ID, useSession } from '../state/useSession';
import { readErrorCopy } from '../utils/verification';
import {
  leagueFormatLine,
  newsCount,
  nextSort,
  ownerName,
  presetWeeks,
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

// Remembered for the app session so the pill stays where the user left it.
let lastView: UsageView = 'simple';

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
  const [metric, setMetric] = useState<UsageMetric>('snaps');
  const [ownership, setOwnership] = useState<OwnershipFilter>(route.params?.ownership ?? 'all');
  const [positionFilter, setPositionFilter] = useState<PositionFilter>('ALL');
  const [units, setUnits] = useState<Record<UsageView, UsageUnit>>({ simple: 'share', stats: 'count' });
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [sheetPlayer, setSheetPlayer] = useState<UsagePlayer | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  // Version B only: the user's column sort (null = server order).
  const [statsSort, setStatsSort] = useState<StatsSort | null>(null);
  // The user's week selection (Filters → Weeks). null = the server default,
  // the last four completed weeks.
  const [selectedWeeks, setSelectedWeeks] = useState<number[] | null>(null);
  const { width: screenWidth } = useWindowDimensions();
  const [claim, setClaim] = useState<{ target: ClaimTarget; leagueId: string } | null>(null);

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
  const query = useQuery({
    queryKey: ['usage-trends', focusId, otherIds.join(','), weeksParam(selectedWeeks)],
    queryFn: () => getUsageTrends(focusId as string, otherIds, selectedWeeks),
    enabled: enabled && !!focusId,
    staleTime: 10 * 60_000,
    // A new week selection keeps the current list on screen while it loads.
    placeholderData: keepPreviousData,
  });
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
             sort?: StatsSort | null; weeks?: number[] | null }) => {
      track('usage_trends_view_changed', {
        league_id: focusId,
        metric: next.metric ?? metric,
        ownership: next.ownership ?? ownership,
        view: next.view ?? view,
        sort: sortLabel(next.sort !== undefined ? next.sort : statsSort, weeks),
        weeks: weeksParam(next.weeks !== undefined ? next.weeks : selectedWeeks),
      }, 'UsageTrends');
    },
    [focusId, metric, ownership, view, statsSort, weeks, selectedWeeks],
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
    }, 'UsageTrends');
  };

  // Acting in a league other than the focused one switches to it first
  // (the MatchesScreen precedent). Pins are cleared by any league switch,
  // so every caller writes its pins AFTER this resolves.
  const switchTo = async (lgId: string): Promise<boolean> => {
    if (lgId === focusId) return true;
    const target = (leagues ?? []).find((l) => l.league_id === lgId);
    if (!target) {
      Alert.alert("Couldn't open that league", 'Pick it from your league list, then try again.');
      return false;
    }
    try {
      await useSession.getState().switchLeague({ league_id: target.league_id, league_name: target.name });
      return true;
    } catch {
      Alert.alert("Couldn't switch leagues", 'Try again in a moment.');
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

  const doTrade = async (p: UsagePlayer, lgId: string) => {
    trackAction('trade', p, lgId);
    const lg = data?.leagues.find((l) => l.league_id === lgId);
    const ownerKey = lg?.rosters[p.player_id];
    await closeSheetFirst();
    if (!(await switchTo(lgId))) return;
    const store = useFinderTargets.getState();
    store.setSide('give', []);
    store.setSide('receive', [{ id: p.player_id, name: p.name, position: p.position, team: p.team }]);
    store.setHandoff({
      opponent:
        ownerKey && !ownerKey.startsWith('roster:')
          ? { userId: ownerKey, name: lg?.owners[ownerKey] ?? ownerKey }
          : null,
      autoRun: true,
    });
    navigation.navigate('Main', { screen: 'Trades', params: { screen: 'TradesHome' } });
  };

  const doAdd = async (p: UsagePlayer, lgId: string) => {
    trackAction('add', p, lgId);
    const platform = resolveAddPlatform(lgId, isDemo);
    await closeSheetFirst();
    if (platform !== 'sleeper') {
      explainNoAdd(platform);
      return;
    }
    if (!(await switchTo(lgId))) return;
    setClaim({ target: { player_id: p.player_id, name: p.name, position: p.position, team: p.team }, leagueId: lgId });
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
    const n = newsCount(list, metric, latest);
    const out: ListItem[] = [];
    if (n) {
      out.push({
        kind: 'section', key: 's-news', title: 'Biggest jumps last week',
        sub: `Players whose ${metric} jumped in Week ${latest}, biggest first.`,
      });
      out.push(...list.slice(0, n).map((p) => ({ kind: 'player' as const, key: p.player_id, player: p })));
    }
    if (list.length > n) {
      out.push({
        kind: 'section', key: 's-rest', title: n ? 'Everyone else' : 'All players',
        sub: `Recent changes first, then by share of team ${PLAYS_NOUN[metric]}.`,
      });
      out.push(...list.slice(n).map((p) => ({ kind: 'player' as const, key: p.player_id, player: p })));
    }
    return out;
  }, [view, list, metric, latest, unit, statsSort]);

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
            focusStatus={focusStatus}
            leagueStatuses={(data?.leagues ?? []).map((lg) => statusIn(lg, p.player_id))}
            onAdd={() => focusId && doAdd(p, focusId)}
            onTrade={() => focusId && doTrade(p, focusId)}
            onRerank={() => doRerank(p)}
            onAvailability={() => {
              reportAvailability(p);
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
          if (!open) reportAvailability(p);
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
  } else {
    const list = (
      <FlatList
        testID="usage-trends.list"
        data={items}
        keyExtractor={(it) => it.key}
        renderItem={renderItem}
        contentContainerStyle={view === 'simple' ? styles.listSimple : styles.listStats}
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
          capacity={faQuery.data?.roster_capacity}
          waivers={faQuery.data?.waivers}
          dropCandidates={faQuery.data?.drop_candidates}
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
