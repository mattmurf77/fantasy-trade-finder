import React from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useQuery } from '@tanstack/react-query';

import { Button, Card, Text, TickLabel } from '../chalkline';
import { chalk, fonts, ink, radii, space, type } from '../../theme/chalkline';
import { getLeaguePreferences, getLeagueSummary, getPowerRankings } from '../../api/league';
import { findMyRoster, getLeagueRosters, getLeagueUsers } from '../../api/sleeper';
import { getProgress } from '../../api/rankings';
import type { ProjectionOutlook } from '../../api/leagueProjections';
import { track } from '../../api/events';
import { NO_LEAGUE_ID, useSession } from '../../state/useSession';
import { useFlag } from '../../state/useFeatureFlags';
import {
  requestLeagueSummaryAll,
  requestLeagueSummaryRoster,
  requestLeagueSummarySplit,
} from '../../state/leagueSummaryIntent';
import {
  MIN_SPLIT_TEAMS,
  SPLIT_POSITIONS,
  canSplit,
  emphasizedSides,
  ordinal,
  positionSplits,
  type PositionSplit,
} from '../../utils/positionSplit';
import { currentStandings, standingsSummary } from '../../utils/standings';
import { tapDestination, type DirectionTap } from '../../utils/directionCard';
import { outlookDisplayName } from '../OutlookBiasReceipt';
import StatusRow from './StatusRow';
import PositionTile from './PositionTile';
import TaskTile from './TaskTile';
import HomePlayoffBanner from './HomePlayoffBanner';
import HomeNextMove from './HomeNextMove';
import { nextMoveTap, type NextMoveView } from '../../utils/homeNextMove';
import { useFinderTargets } from '../../state/useFinderTargets';
import { armHomeReturn } from '../../state/homeReturn';
import {
  HOME_RETURN_FLAG,
  HOME_RETURN_UNIFIED_FLAG,
  homeReturnUnifiedOn,
  type HomeTileTap,
} from '../../navigation/navContinuity';

// Home hub (flag `nav.home_hub`, Direction D; docs/plans/home-engagement/
// scope.md §6.3, mockup mockups/home-engagement/index.html#dir-d). Mounted by
// HomeScreen when the flag was on at mount; owns every query, analytics event
// and navigation of the hub, so HomeScreen itself stays data-free.
//
// Top to bottom: the question; three status rows (team outlook, CURRENT
// standings, overall rank), each its own query that loads and fails alone;
// the 2×2 position tiles with in-tile Buy / Sell (flag `league.pos_candidates`);
// five task tiles that render in every state, so Home always reaches the
// app's main jobs in one tap.
//
// Shared caches: every query uses the key, fetcher and options of the
// surface that already owns it (scope §6.2), so Home is usually free on a
// warm launch. The roster/user keys are seeded by session init and keep
// staleTime 5 * 60_000 so the seed survives to mount (check-session-seed S-2).
//
// Analytics: one `home_tile_tapped` per press, BEFORE navigating, with the
// closed `tile` vocabulary; `position` + `band` ride on buy / sell /
// position_ranking / position_roster only, and `split` on position_roster
// only. Pinned by tests/check-home-hub.js.

// The honest "not available" standings copy names the platform (R7: ESPN/MFL
// current standings are out of v1).
const PLATFORM_NAME: Record<string, string> = {
  espn: 'ESPN',
  mfl: 'MFL',
  fleaflicker: 'Fleaflicker',
};

// home_tile_tapped's `band` prop: the user's own band at that position.
function bandProp(s: PositionSplit): 'seller' | 'buyer' | 'mid' {
  if (s.you?.band === 'Seller') return 'seller';
  if (s.you?.band === 'Buyer') return 'buyer';
  return 'mid';
}

export default function HomeHub() {
  const navigation = useNavigation<any>();
  const user = useSession((s) => s.user);
  const hasToken = useSession((s) => s.hasToken);
  const activeFormat = useSession((s) => s.activeFormat);
  const leagueId = useSession((s) => s.league?.league_id ?? null);
  const hasLeague = !!leagueId && leagueId !== NO_LEAGUE_ID;
  // LeagueSummaryScreen's platform rule: UNKNOWN RESOLVES TO SLEEPER.
  const platform =
    useSession((s) => s.leagues.find((l) => l.league_id === leagueId)?.platform) ?? 'sleeper';
  const isSleeper = platform === 'sleeper';
  const posCandidatesOn = useFlag('league.pos_candidates');
  // Usage Rates tile (flag `usage_trends.enabled`, docs/plans/usage-trends/).
  const usageOn = useFlag('usage_trends.enabled');
  // Position tile body tap → your roster at that position (D-269, docs/plans/
  // position-tile-tap/scope.md). Off ⇒ no onOpen, the tile is unchanged.
  const tileRosterOn = useFlag('nav.home_position_roster');
  // "‹ Home" on the destination of a tile that crosses to another tab (flag
  // `nav.home_return`, D-275, decision Q1 (a)). Armed AFTER the tap is
  // tracked and BEFORE it navigates, so the destination tab's focus finds
  // it. navigation/navContinuity.homeReturnTabFor decides which taps arm:
  // rank pages (Rank players) do not; D-269's roster arrival
  // does only in unified mode (D-276: `nav.home_return_unified` on top of
  // `nav.home_return`), where League rankings drops its own header "Home"
  // control so the bar is the one control. Off ⇒ nothing is armed.
  const homeReturnOn = useFlag(HOME_RETURN_FLAG);
  const unifiedOn = useFlag(HOME_RETURN_UNIFIED_FLAG);
  const homeReturnUnified = homeReturnUnifiedOn(homeReturnOn, unifiedOn);
  const armReturn = (tap: HomeTileTap) => {
    if (homeReturnOn) armHomeReturn(tap, homeReturnUnified);
  };

  // ── Queries (scope §6.2) ──────────────────────────────────────────────
  const prefsQuery = useQuery({
    queryKey: ['league-prefs', leagueId],
    queryFn: () => getLeaguePreferences(leagueId!),
    enabled: hasLeague,
  });
  const rostersQuery = useQuery({
    queryKey: ['league-rosters', leagueId],
    queryFn: () => getLeagueRosters(leagueId!),
    enabled: hasLeague && isSleeper,
    staleTime: 5 * 60_000,
  });
  const usersQuery = useQuery({
    queryKey: ['league-users', leagueId],
    queryFn: () => getLeagueUsers(leagueId!),
    enabled: hasLeague && isSleeper,
    staleTime: 5 * 60_000,
  });
  const rankingsQuery = useQuery({
    queryKey: ['league-power-rankings', leagueId, 'consensus'],
    queryFn: () => getPowerRankings(leagueId!, 'consensus'),
    enabled: hasLeague,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });
  const summaryQuery = useQuery({
    queryKey: ['league-summary', leagueId],
    queryFn: () => getLeagueSummary(leagueId!),
    enabled: hasLeague,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });
  const progressQuery = useQuery({
    queryKey: ['progress', leagueId, activeFormat],
    queryFn: getProgress,
    enabled: !!user && hasToken,
    staleTime: 15_000,
    refetchOnWindowFocus: true,
  });

  // `placeholderData` carries the PREVIOUS league's payload across a league
  // switch. Home never describes one league with another's numbers, so it
  // reads placeholder data as "not loaded yet" (skeleton, Buy/Sell disabled).
  const rankings = rankingsQuery.isPlaceholderData ? undefined : rankingsQuery.data;
  const rankingsFailed = rankingsQuery.isError && !rankings;
  const summary = summaryQuery.isPlaceholderData ? undefined : summaryQuery.data;
  const you = rankings?.teams.find((t) => t.is_you) ?? null;
  // The split arithmetic is utils/positionSplit's, shared with League
  // rankings (parity-guarded), so Home's band is the band the user lands on.
  const splits = rankings && canSplit(rankings) ? positionSplits(rankings) : null;
  const emphasis = splits ? emphasizedSides(splits) : {};

  const standings = rostersQuery.data
    ? standingsSummary(
        currentStandings(
          rostersQuery.data,
          usersQuery.data ?? [],
          findMyRoster(rostersQuery.data, user?.user_id ?? '')?.roster_id ?? null,
        ),
      )
    : null;

  // ── Handlers: track, then navigate (scope §6.2) ──────────────────────
  const onOutlook = () => {
    track('home_tile_tapped', { tile: 'outlook' }, 'Home');
    armReturn('outlook');
    navigation.navigate('Trades', { screen: 'TradesHome', params: { mode: 'guided', editDna: true } });
  };
  // The playoff tile's "Review outlook": the same destination as the Team
  // outlook row, with the server's suggestion marked in the selector. It
  // saves nothing — the user's tap on an outlook card is the write.
  const onReviewOutlook = (recommended: ProjectionOutlook) => {
    track('home_tile_tapped', { tile: 'outlook' }, 'Home');
    armReturn('review_outlook');
    navigation.navigate('Trades', { screen: 'TradesHome', params: { mode: 'guided', editDna: true, suggestOutlook: recommended } });
  };
  const onStandings = () => {
    track('home_tile_tapped', { tile: 'standings' }, 'Home');
    navigation.navigate('Standings');
  };
  // The playoff tile's percentage and "View": the same page, whose one
  // table carries the projected record, playoff odds and Max PF.
  const onProjections = () => {
    track('home_tile_tapped', { tile: 'standings' }, 'Home');
    navigation.navigate('Standings');
  };
  // The playoff card's half sheet (D-270): "View" opening it, and each
  // row. Same event with the closed `tile` vocabulary plus `via`; a row then
  // opens Standings or an Improve page (told it came from the sheet).
  const onDirectionTap = (tap: DirectionTap) => {
    track('home_tile_tapped', { tile: tap.tile, via: tap.via }, 'Home');
    const to = tapDestination(tap);
    if (to) navigation.navigate(to.route, 'params' in to ? to.params : undefined);
  };
  // The next-move row under the playoff card (flag `league.next_move`,
  // D-278): the list row's own "Find trades" (utils/homeNextMove.nextMoveTap
  // runs that row's hand-off, which pins the player and logs
  // finder_target_pinned under Home), opened on the Trades tab, with the
  // "‹ Home" bar armed for it like the "Find a trade" tile.
  const onNextMove = (view: NextMoveView) => {
    track('home_tile_tapped', { tile: 'next_move' }, 'Home');
    armReturn('next_move');
    nextMoveTap(view, {
      setSide: (side, players) => useFinderTargets.getState().setSide(side, players),
      track,
      navigate: (p) => navigation.navigate(p.screen, p.params),
      now: Date.now,
    });
  };
  const onOverallRank = () => {
    track('home_tile_tapped', { tile: 'overall_rank' }, 'Home');
    armReturn('overall_rank');
    requestLeagueSummaryAll(leagueId!);
    navigation.navigate('League', { screen: 'LeagueRankings' });
  };
  const onBuy = (s: PositionSplit) => {
    track('home_tile_tapped', { tile: 'buy', position: s.position, band: bandProp(s) }, 'Home');
    armReturn('buy');
    requestLeagueSummarySplit(leagueId!, s.position, 'buy');
    navigation.navigate('League', { screen: 'LeagueRankings' });
  };
  const onSell = (s: PositionSplit) => {
    track('home_tile_tapped', { tile: 'sell', position: s.position, band: bandProp(s) }, 'Home');
    armReturn('sell');
    requestLeagueSummarySplit(leagueId!, s.position, 'sell');
    navigation.navigate('League', { screen: 'LeagueRankings' });
  };
  // No line at this position: the plain ordering, landing at the list top
  // (side 'buy'); League rankings draws no banner when the split isn't shown.
  const onRanking = (s: PositionSplit) => {
    track('home_tile_tapped', { tile: 'position_ranking', position: s.position, band: bandProp(s) }, 'Home');
    armReturn('position_ranking');
    requestLeagueSummarySplit(leagueId!, s.position, 'buy');
    navigation.navigate('League', { screen: 'LeagueRankings' });
  };
  // The tile body: League rankings filtered to the position with the user's
  // own team drilled in. `split` is the tile's state (shown | no_split |
  // no_median), so a no-split tile's tap is readable apart from Mid-pack.
  const onOpenRoster = (s: PositionSplit) => {
    track('home_tile_tapped', { tile: 'position_roster', position: s.position, band: bandProp(s), split: s.state }, 'Home');
    if (homeReturnUnified) armReturn('position_roster');
    requestLeagueSummaryRoster(leagueId!, s.position);
    navigation.navigate('League', { screen: 'LeagueRankings' });
  };
  const onLinkLeague = () => {
    track('home_tile_tapped', { tile: 'link_league' }, 'Home');
    navigation.navigate('LeaguePicker');
  };
  const onRetry = (refetch: () => unknown) => {
    track('home_tile_tapped', { tile: 'retry' }, 'Home');
    refetch();
  };

  // ── Status rows ───────────────────────────────────────────────────────
  const prefs = prefsQuery.data;
  const declared = outlookDisplayName(prefs?.team_outlook);
  const inferred = outlookDisplayName(prefs?.inferred_outlook);

  const standingsRow = !isSleeper ? (
    <StatusRow
      testID="home.status.standings"
      label="Standings"
      state="unavailable"
      value={`Not available for ${PLATFORM_NAME[platform] ?? 'this league'} yet`}
    />
  ) : rostersQuery.isError && !rostersQuery.data ? (
    <StatusRow
      testID="home.status.standings"
      label="Standings"
      state="error"
      onRetry={() => onRetry(rostersQuery.refetch)}
    />
  ) : !standings ? (
    <StatusRow testID="home.status.standings" label="Standings" state="loading" />
  ) : standings.kind === 'unavailable' ? (
    <StatusRow
      testID="home.status.standings"
      label="Standings"
      state="unavailable"
      value="Not available for this league yet"
    />
  ) : (
    // Actual results, never projections: the outlook beta rule does not
    // apply, and before week 1 every team is 0–0, so the row says so rather
    // than ranking a 12-way tie.
    <StatusRow
      testID="home.status.standings"
      label="Standings"
      state="ready"
      value={standings.kind === 'record' ? standings.record : '0–0'}
      valueMono
      detail={
        standings.kind === 'record'
          ? `${ordinal(standings.place)} of ${standings.teamCount}`
          : 'no games yet'
      }
      onPress={onStandings}
    />
  );

  const rankRow = rankingsFailed ? (
    <StatusRow
      testID="home.status.rank"
      label="Overall rank"
      state="error"
      onRetry={() => onRetry(rankingsQuery.refetch)}
      last
    />
  ) : !rankings ? (
    <StatusRow testID="home.status.rank" label="Overall rank" state="loading" last />
  ) : rankings.teams.length < MIN_SPLIT_TEAMS ? (
    // Same gate as the grid's "Not enough rosters yet" card.
    <StatusRow
      testID="home.status.rank"
      label="Overall rank"
      state="unavailable"
      value={`${rankings.teams.length} ${rankings.teams.length === 1 ? 'roster' : 'rosters'} valued so far`}
      last
    />
  ) : !you ? (
    <StatusRow
      testID="home.status.rank"
      label="Overall rank"
      state="unavailable"
      value="Your roster isn’t valued yet"
      last
    />
  ) : (
    <StatusRow
      testID="home.status.rank"
      label="Overall rank"
      state="ready"
      value={`${ordinal(you.rank)} of ${rankings.teams.length}`}
      valueMono
      detail={you.total_value_label ?? null}
      detailMono
      onPress={onOverallRank}
      last
    />
  );

  // ── Position tiles (D2/D3) ────────────────────────────────────────────
  const grid = (tiles: React.ReactNode[]) => (
    <View style={styles.grid}>
      <View style={styles.gridRow}>
        {tiles[0]}
        {tiles[1]}
      </View>
      <View style={styles.gridRow}>
        {tiles[2]}
        {tiles[3]}
      </View>
    </View>
  );
  let positions: React.ReactNode = null;
  if (rankingsFailed) {
    positions = (
      <View testID="home.positions.error">
        <Card>
          <Text variant="heading">Couldn’t load rosters</Text>
          <Text style={styles.noticeBody}>
            The league’s rosters didn’t load. Check your connection and try again.
          </Text>
          <Button
            label="Try again"
            variant="secondary"
            icon="reload"
            testID="home.positions.retry"
            onPress={() => onRetry(rankingsQuery.refetch)}
          />
        </Card>
      </View>
    );
  } else if (!rankings) {
    positions = grid(SPLIT_POSITIONS.map((p) => <PositionTile key={p} pos={p} split={null} />));
  } else if (splits) {
    positions = grid(
      splits.map((s) => (
        <PositionTile
          key={s.position}
          pos={s.position}
          split={s}
          onBuy={() => onBuy(s)}
          onSell={() => onSell(s)}
          onRanking={() => onRanking(s)}
          onOpen={tileRosterOn ? () => onOpenRoster(s) : undefined}
          emphasis={emphasis[s.position] ?? null}
        />
      )),
    );
  } else if (rankings.teams.length < MIN_SPLIT_TEAMS) {
    // No line to buy or sell across: one honest card, no Buy/Sell.
    positions = (
      <Card>
        <Text variant="heading">Not enough rosters yet</Text>
        <Text style={styles.noticeBody}>
          Buying and selling by position needs at least {MIN_SPLIT_TEAMS} valued rosters. This
          fills in as the league’s rosters sync.
        </Text>
      </Card>
    );
  }
  // else: >= 3 teams but no median anywhere (an old server) — no grid.

  // ── Task tiles (D4) ───────────────────────────────────────────────────
  const progress = progressQuery.data;
  const mutual = summary?.matches_mutual ?? 0;
  const awaiting = summary?.matches_awaiting ?? 0;

  return (
    // No `top` safe-area edge: TabNav's TopBar owns the top inset.
    <ScrollView style={styles.root} contentContainerStyle={styles.content} testID="home.hub">
      <Text variant="heading" style={styles.heading}>
        What would you like to do today?
      </Text>

      {hasLeague ? (
        <>
          <HomePlayoffBanner key={`${user?.user_id}:${leagueId}`}
            rosterId={findMyRoster(rostersQuery.data, user?.user_id ?? '')?.roster_id ?? null}
            onDetails={onProjections}
            onReviewOutlook={onReviewOutlook}
            screen="Home"
            onDirectionTap={onDirectionTap} />
          <HomeNextMove rosters={rostersQuery.data}
            liveIds={findMyRoster(rostersQuery.data, user?.user_id ?? '')?.players ?? null}
            onPress={onNextMove} />
          <View style={styles.rows}>
            <StatusRow
              testID="home.status.outlook"
              label="Team outlook"
              state={prefs ? 'ready' : prefsQuery.isError ? 'error' : 'loading'}
              value={declared ?? 'Not set'}
              detail={declared ? 'set by you' : inferred ? `reads as ${inferred}` : null}
              action={declared ? 'View' : 'Set'}
              onPress={onOutlook}
              onRetry={() => onRetry(prefsQuery.refetch)}
            />
            {standingsRow}
            {rankRow}
          </View>

          {posCandidatesOn && positions ? (
            <>
              <View style={styles.tick}>
                <TickLabel>Your positions</TickLabel>
                <Text scale="dense" style={styles.tickNote}>consensus values</Text>
              </View>
              {positions}
            </>
          ) : null}
        </>
      ) : (
        // Status rows and tiles collapse into one setup card.
        <Card>
          <Text variant="heading">Link a league</Text>
          <Text style={styles.noticeBody}>
            Your outlook, standings and rank, plus who’s buying and selling at each position,
            need a league. Link Sleeper, ESPN or MFL.
          </Text>
          <Button label="Link a league" testID="home.link-league" onPress={onLinkLeague} />
        </Card>
      )}

      <View style={styles.tick}>
        <TickLabel>Get things done</TickLabel>
      </View>
      <View style={styles.tasks}>
        <TaskTile
          testID="home.tile.find-trade"
          icon="trade"
          title="Find a trade"
          detail="Fair packages with any leaguemate"
          onPress={() => {
            track('home_tile_tapped', { tile: 'find_trade' }, 'Home');
            armReturn('find_trade');
            navigation.navigate('Trades');
          }}
        />
        <TaskTile
          testID="home.tile.rank"
          icon="rank"
          title="Rank players"
          detail={progress?.unlocked ? 'Board live' : 'Build your board'}
          onPress={() => {
            track('home_tile_tapped', { tile: 'rank' }, 'Home');
            navigation.navigate('Rank');
          }}
        />
        <TaskTile
          testID="home.tile.matches"
          icon="match"
          title="View matches"
          detail={
            !hasLeague
              ? 'Needs a league'
              : awaiting > 0
                ? `${awaiting} awaiting them`
                : 'Trades you and a leaguemate both like'
          }
          badge={hasLeague && mutual > 0 ? `${mutual} mutual` : null}
          onPress={() => {
            track('home_tile_tapped', { tile: 'matches' }, 'Home');
            armReturn('matches');
            navigation.navigate('Matches');
          }}
        />
        {/* No "Check trends" tile: the Rank-stack Trends page was cut for
            launch (owner call 2026-11-25; route kept, no entry points).
            Usage Rates: RB/WR/TE snaps, carries and targets by week — a
            different screen (Usage Trends). Root-stack push; hidden while
            usage_trends.enabled is off. */}
        {usageOn ? (
          <TaskTile
            testID="home.tile.usage-rates"
            icon="usage"
            title="Usage Rates"
            detail="Snaps, carries and targets by week"
            onPress={() => {
              track('home_tile_tapped', { tile: 'usage_rates' }, 'Home');
              navigation.navigate('UsageTrends');
            }}
          />
        ) : null}
        <TaskTile
          testID="home.tile.free-agents"
          icon="search"
          title="Search free agents"
          detail={hasLeague ? 'Best available on your board' : 'Needs a league'}
          onPress={() => {
            track('home_tile_tapped', { tile: 'free_agents' }, 'Home');
            navigation.navigate('FreeAgents');
          }}
        />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: ink.ink0 },
  // Bottom pad clears RootNav's global FeedbackFAB (the Matches list's value).
  content: { paddingHorizontal: space.lg, paddingBottom: 96 },
  // Sentence case on purpose, as on the flag-off Home: a question, not a label.
  heading: { ...type.heading, textTransform: 'none', marginTop: space.lg, marginBottom: space.md },
  rows: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    overflow: 'hidden',
  },
  tick: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: space.xl,
    marginBottom: space.md,
  },
  tickNote: {
    fontFamily: fonts.data,
    fontSize: 11,
    lineHeight: 14,
    color: chalk.dim,
  },
  grid: { gap: space.sm },
  gridRow: { flexDirection: 'row', gap: space.sm },
  noticeBody: { ...type.bodySm, marginTop: space.xs, marginBottom: space.md },
  tasks: { gap: space.sm },
});
