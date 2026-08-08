import React, { useState, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ScrollView,
  RefreshControl,
  Modal,
  Share,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { useQuery } from '@tanstack/react-query';

import {
  ink,
  chalk,
  ice,
  flare,
  semantic,
  position as positionColors,
  space,
  radii,
  type,
  fonts,
  shadowSheet,
  scrim,
} from '../theme/chalkline';
import {
  TickLabel,
  Badge,
  Button,
  Card,
  Meter,
  Icon,
  IconName,
  Text as ChalkText,
} from '../components/chalkline';
import {
  getLeagueSummary,
  getLeagueCoverage,
  getLeagueMembers,
  getLeagueMemberUnlockStates,
  getActivityFeed,
  getContrarianLeaderboard,
} from '../api/league';
import { getPickAssignments, pickAssignmentSubline } from '../api/pickAssignment';
import { getProgress, getTiersStatus } from '../api/rankings';
import { importEspnLeague } from '../api/espn';
import { initLeagueSession } from '../api/auth';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import { useWhatsNew } from '../hooks/useWhatsNew';
import RankChipBadge from '../components/RankChipBadge';
import LeaderboardsSection from '../components/LeaderboardsSection';
import ActivityFeed from '../components/ActivityFeed';
import ContrarianLeaderboard from '../components/ContrarianLeaderboard';
import CoachMark from '../components/CoachMark';
import RookieDraftBoardSheet from '../components/RookieDraftBoardSheet';
import LeagueProgressModule from '../components/LeagueProgressModule';
import MarketPulseStrip from '../components/MarketPulseStrip';
import TradeValueBar from '../components/TradeValueBar';
import { buildInviteUrl } from '../components/InviteLeaguematesBanner';

// League home (tab v1; since #181 the pushed 'LeagueHome' sub-route of the
// League tab's stack — the tab now LANDS on the rankings view, and this
// classic page is reached from its "League home" row). Pulls
// /api/league/summary + /api/league/coverage and renders:
//   • League name + scoring + scoring chip
//   • Matches stats (mutual matches / awaiting them — FB-91: tiles mirror
//     the Matches tab's two segments so both surfaces always agree)
//   • Leaguemate join progress (joined / total) + 1QB/SF unlocked counts
//   • Ranking-coverage bar (ranked opponents / total)
// League SWITCHING no longer lives here (#223): the global TopBar carries
// the active-league affordance + the single LeagueSwitcherSheet instance.
// #229/#230/#234 (approved mock empty-states-progress-v3.html): in the
// low-activity state the page adds an action row (Rank players | Find a
// trade), ONE LeagueProgressModule owning every unlock, and a "Works right
// now" EXAMPLE-trade card, while the confirmed-zero sections (Matches
// tiles, joined chip, contrarian, coverage, leaderboards) fold into the
// module and return automatically once their counts are > 0. A fully
// unlocked league renders exactly the classic populated layout.
// #243 (2026-08-03, approved mocks league-home-fold.html V1 +
// risers-fallers-cards.html D1): divider double-margin bug fixed, Explore
// reflowed to a 3-across tile row, hero padding 16→12, the progress
// module's invite button became an inline text link — the low-activity
// state's progress module now ends fully above the 658pt fold — and the
// Market pulse strip (flag `market.movers`) mounts below Explore.
export default function LeagueScreen() {
  const league   = useSession((s) => s.league);
  const leagueId = league?.league_id || null;
  // FB-38/42 — member-roster overlay, opened from the hero's joined chip.
  const [membersOpen, setMembersOpen] = useState(false);
  // S7 PRD-04 item 2 (flag league.rookie_board_entry) — the previously
  // orphaned RookieDraftBoardSheet mounts behind an Explore row.
  const showRookieBoard = useFlag('league.rookie_board_entry');
  // rookie-draft M4 / operator decision O1 — the Draft Room REPLACES the
  // rookie-board tile, but only when its flag is on. The replacement is
  // conditional on purpose: an unconditional swap would leave every user
  // with nothing in that slot the moment `draft.room` was flipped back off.
  const showDraftRoom = useFlag('draft.room');
  // draft-extensions W3 M-A — the "Draft picks" section below Explore.
  // Paired with the ESPN check below, because ESPN is the only platform
  // whose rookie draft FTF cannot read.
  const showPickAssignFlag = useFlag('picks.assign');
  const [rookieOpen, setRookieOpen] = useState(false);
  // (#181) The ux.retap_active_tab scroll-to-top registration moved to
  // LeagueSummaryScreen's tab-root variant — this screen is no longer the
  // League tab's root, and a focused re-tap pops back to it instead.
  // S7 PRD-04 item 5 (flag ux.whats_new) — one version-keyed inline tip,
  // shown once per release (see useWhatsNew for the contract).
  const { entry: whatsNew, dismiss: dismissWhatsNew } = useWhatsNew();
  // FB-37 — Matches tiles deep-link to the Matches tab.
  const navigation = useNavigation<any>();

  // ESPN read-only import (flag `espn.link`) — platform comes from the
  // cached league list (set at link time / picker refresh). ESPN leagues
  // get a text badge, read-only expectation copy, and a re-sync action.
  const user = useSession((s) => s.user);
  const cachedLeagues = useSession((s) => s.leagues);
  const isEspn = cachedLeagues.some(
    (lg) => lg.league_id === leagueId && lg.platform === 'espn',
  );
  const showPickAssign = showPickAssignFlag && isEspn;
  const [resyncing, setResyncing] = useState(false);
  const [resyncMsg, setResyncMsg] = useState<string | null>(null);

  async function resyncEspn() {
    if (!leagueId || !user || resyncing) return;
    setResyncing(true);
    setResyncMsg(null);
    try {
      const res = await importEspnLeague(leagueId);
      // Rebuild the server session so the refreshed rosters are live.
      await initLeagueSession(user, {
        league_id: leagueId,
        name: res.name || league?.league_name || '',
      });
      setResyncMsg(`Re-synced ${res.teams_imported} rosters from ESPN.`);
      refetchAll();
    } catch (e: any) {
      setResyncMsg(e?.message || 'Re-sync failed — try again shortly.');
    } finally {
      setResyncing(false);
    }
  }

  // `placeholderData: (prev) => prev` keeps the previous value visible
  // across refetches so the screen doesn't blank when re-entered.
  const summaryQuery = useQuery({
    queryKey: ['league-summary', leagueId],
    queryFn:  () => getLeagueSummary(leagueId!),
    enabled:  !!leagueId,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  // Draft picks (draft-extensions W3 M-A, flag `picks.assign`). The query
  // shares its key with `PickAssignmentScreen`, so opening the screen from
  // this row renders off a warm cache instead of a spinner — and a save
  // made there updates this sub-line on the way back. `enabled` keeps the
  // flag-off / non-ESPN page byte-identical: no request is issued at all.
  const pickAssignQuery = useQuery({
    queryKey: ['pick-assignments', leagueId],
    queryFn:  () => getPickAssignments(leagueId!),
    enabled:  !!leagueId && showPickAssignFlag && isEspn,
    staleTime: 5 * 60_000,
  });

  const coverageQuery = useQuery({
    queryKey: ['league-coverage', leagueId],
    queryFn:  () => getLeagueCoverage(leagueId!),
    enabled:  !!leagueId,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  // Leaguemate roster (joined / not-joined). Mirrors the web
  // client's section in the League Summary page (PR #13, agent #15).
  // The summary stat card shows the count; this list shows the names.
  const membersQuery = useQuery({
    queryKey: ['league-members', leagueId],
    queryFn:  () => getLeagueMembers(leagueId!),
    enabled:  !!leagueId,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  // B7 — flag-gated surfaces. Each query is enabled only when its flag is
  // on so a flag-off user incurs zero network cost.
  const showActivity     = useFlag('league.activity_feed');
  const showUnlockBadges = useFlag('league.unlock_badges_per_member');

  const activityQuery = useQuery({
    queryKey: ['league-activity', leagueId],
    queryFn:  () => getActivityFeed(leagueId!, 10),
    enabled:  !!leagueId && showActivity,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  const contrarianQuery = useQuery({
    queryKey: ['league-contrarian', leagueId],
    queryFn:  () => getContrarianLeaderboard(leagueId!),
    enabled:  !!leagueId,
    staleTime: 5 * 60_000,
    placeholderData: (prev) => prev,
  });

  const unlocksQuery = useQuery({
    queryKey: ['league-member-unlocks', leagueId],
    queryFn:  () => getLeagueMemberUnlockStates(leagueId!),
    enabled:  !!leagueId && showUnlockBadges,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  // #229/#230 — the progress module's ring needs per-position ranking
  // state. Same keys as the Rank surfaces so the cache is shared.
  const activeFormat = useSession((s) => s.activeFormat);
  const progressQuery = useQuery({
    queryKey: ['progress', leagueId, activeFormat],
    queryFn:  getProgress,
    enabled:  !!leagueId,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });
  const tiersStatusQuery = useQuery({
    queryKey: ['tiers-status'],
    queryFn:  getTiersStatus,
    enabled:  !!leagueId,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  // Map user_id → unlock state for cheap per-row chip lookups. Backend
  // returns `flag_off: true` and `members: []` when the flag is off, which
  // collapses to an empty Map naturally.
  const unlocksById = useMemo(() => {
    const m = new Map<string, { unlocked: boolean; has_method: boolean }>();
    for (const u of unlocksQuery.data?.members ?? []) {
      m.set(u.user_id, {
        unlocked:   (u.unlocked_count || 0) > 0,
        has_method: !!u.has_ranking_method,
      });
    }
    return m;
  }, [unlocksQuery.data]);

  const refetchAll = () => {
    summaryQuery.refetch();
    coverageQuery.refetch();
    membersQuery.refetch();
    if (showActivity) activityQuery.refetch();
    contrarianQuery.refetch();
    if (showUnlockBadges) unlocksQuery.refetch();
    progressQuery.refetch();
    tiersStatusQuery.refetch();
  };

  // No league yet — funnel back to the picker. Should be rare since the
  // tab nav only renders this when the user is signed in.
  if (!leagueId) {
    return (
      <SafeAreaView style={styles.safe} edges={['bottom']}>
        <View style={styles.center}>
          <Text style={type.heading}>No league selected</Text>
          <Text style={[type.bodySm, styles.emptyBody]}>
            Pick a league from the league switcher to see this tab populated.
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  const summary  = summaryQuery.data;
  const coverage = coverageQuery.data;
  // First-paint flag: render skeleton chips instead of zeros so the page
  // shape is stable while data is in flight on initial mount.
  const summaryPending  = !summary  && summaryQuery.isLoading;
  const coveragePending = !coverage && coverageQuery.isLoading;

  // Defensive number reader. Backend keys may vary slightly from typed shape.
  const num = (v: unknown, fallback = 0) =>
    typeof v === 'number' && Number.isFinite(v) ? v : fallback;

  // FB-91 — the old matches_pending/matches_accepted split partitioned
  // match rows by disposition status, so one match could read as "a trade
  // available" under both tiles while the Matches tab showed a single
  // entry. The tiles now mirror the Matches tab's segments exactly.
  const matchesMutual   = num((summary as any)?.matches_mutual);
  const matchesAwaiting = num((summary as any)?.matches_awaiting);
  const totalMates      = num((summary as any)?.leaguemates_total);
  const joinedMates     = num((summary as any)?.leaguemates_joined);
  const unlocked1qb     = num((summary as any)?.leaguemates_unlocked_1qb);
  const unlockedSf      = num((summary as any)?.leaguemates_unlocked_sf);
  const totalOpps       = num(coverage?.total);
  const rankedOpps      = num(coverage?.ranked);

  const coveragePct = totalOpps > 0 ? Math.round((rankedOpps / totalOpps) * 100) : 0;

  // ── #229/#230/#234 — low-activity progress system (approved mock
  // mockups/polish-lab-2026-08/empty-states-progress-v3.html) ──────────
  // Positions ranked (0–4): a position counts once its trio interaction
  // count clears the threshold OR it has saved tiers (Quick set / Tiers
  // commit through /api/tiers/save). progress.unlocked — which also folds
  // in the manual method and the monotonic unlock floor — short-circuits
  // to 4/4. null while the progress payload hasn't arrived yet.
  const progress = progressQuery.data;
  const tiersSaved = tiersStatusQuery.data?.saved ?? [];
  const positionsRanked = progress
    ? progress.unlocked
      ? 4
      : (['QB', 'RB', 'WR', 'TE'] as const).filter(
          (p) => num(progress[p]) >= num(progress.threshold, 10) || tiersSaved.includes(p),
        ).length
    : null;

  // Confirmed-zero fold conditions. A section folds ONLY once its own
  // data confirms it is empty (loading/error ⇒ render as today — never
  // hide a possibly-populated section) and returns automatically the
  // moment its counts move:
  //   • Matches tiles       — fold when both segment counts are 0
  //   • hero "joined" chip  — fold when 0 leaguemates have joined
  //   • Coverage card       — fold when 0 leaguemates have rankings
  //   • Contrarian ranks + Leaderboards — fold on the server's own
  //     insufficient_data flag (/api/league/contrarian needs 3 ranked
  //     members; the module's fold line states exactly that)
  const matchesZero = !!summary && matchesMutual === 0 && matchesAwaiting === 0;
  const joinedZero = !!summary && joinedMates === 0;
  const coverageZero = !!coverage && rankedOpps === 0;
  const contrarianInsufficient = contrarianQuery.data?.insufficient_data === true;

  // Populated-state rule (documented): the progress module renders while
  // ANY unlock it tracks is outstanding — ring < 4/4, no matches yet, or
  // contrarian/leaderboards still locked — and hides entirely once all
  // three are live, at which point the page renders exactly as today's
  // populated layout. The action row is part of the same scaffolding; the
  // "Works right now" example card retires as soon as REAL matches exist.
  const ringIncomplete = positionsRanked != null && positionsRanked < 4;
  const moduleVisible =
    !!summary && !!coverage && (ringIncomplete || matchesZero || contrarianInsufficient);
  const worksNowVisible = matchesZero;

  const totalTeamsN = summary
    ? num(summary.total_teams, num((summary as any)?.leaguemates_total) + 1)
    : 0;

  const goRank = () => navigation.navigate('Rank');
  const goFindTrade = () => navigation.navigate('Trades', { screen: 'TradesHome' });

  // Module "Invite leaguemates" — the OS share sheet with the same
  // referral URL the InviteLeaguematesBanner builds (?league=&ref=).
  async function inviteLeaguemates() {
    if (!leagueId) return;
    const url = buildInviteUrl(leagueId, user?.username);
    const where = summary?.league_name || league?.league_name || 'our league';
    try {
      await Share.share({
        message: `Join me on Dynasty Trade Finder to find trades in ${where} → ${url}`,
      });
    } catch {
      /* user dismissed the share sheet */
    }
  }

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={
          <RefreshControl
            refreshing={summaryQuery.isFetching || coverageQuery.isFetching}
            onRefresh={refetchAll}
            tintColor={ice.base}
          />
        }
      >
        {/* ux.whats_new — one CoachMark-style inline tip per release,
            never a modal, never stacked (whatsNew is null when the flag is
            off, the release has no entry, or it was already dismissed).
            Tap = dismiss; when the entry carries a deep-link route the tap
            also navigates there ("show me" semantics). */}
        {whatsNew ? (
          <CoachMark
            testID="league.whats-new"
            text={whatsNew.headline}
            onDismiss={() => {
              dismissWhatsNew();
              if (whatsNew.route) navigation.navigate(whatsNew.route);
            }}
          />
        ) : null}

        {/* League name + scoring. #223 — the hero is IDENTITY only now:
            switching lives in the global TopBar's league affordance (one
            switcher, everywhere), so the hero's Pressable role, chevron
            cue, and the old bottom "Switch league" button are gone.
            #243 (league-home fold V1): hero padding 16 → 12. */}
        <View testID="league.hero">
            <Card padding={space.md}>
              <View style={styles.heroHead}>
                <Text style={type.label}>League</Text>
              </View>
              <Text style={[type.heading, styles.heroName]} numberOfLines={2}>
                {summary?.league_name || league?.league_name || 'Loading…'}
              </Text>
              <View style={styles.heroChips}>
                {/* ESPN read-only import — text badge, no logos. */}
                {isEspn ? <Badge label="ESPN" /> : null}
                <Badge label={fmtScoring(summary?.default_scoring)} />
                {/* FB #41 — show the league's TRUE team count (backend
                    total_teams = Sleeper total_rosters). Deriving it as
                    leaguemates_total + 1 undercounted when a roster was
                    ownerless (departed manager never reaches
                    league_members). Fallback keeps old backends working. */}
                {/* #14 — your consensus power rank in this league (open
                    read; renders nothing on error/old servers). */}
                {league?.league_id ? <RankChipBadge leagueId={league.league_id} /> : null}
                <Badge
                  label={
                    summary
                      ? `${num(summary.total_teams, num((summary as any)?.leaguemates_total) + 1)} teams`
                      : '— teams'
                  }
                />
                {/* FB-38/42 — joined summary lives in the hero; tapping it
                    opens the member-roster overlay. The chevron icon is the
                    clickability cue the feedback asked for. #229 zero-fold:
                    the chip is absorbed by the progress module while ZERO
                    leaguemates have joined (its overlay would only list
                    "Not joined" rows) and returns the moment one joins. */}
                {joinedZero ? null : (
                  <Pressable
                    onPress={() => setMembersOpen(true)}
                    hitSlop={12}
                    style={({ pressed: p }) => [styles.joinedChip, p && styles.joinedChipPressed]}
                    accessibilityRole="button"
                    accessibilityLabel="View league members and join status"
                  >
                    <Text style={type.data}>
                      {summaryPending ? '—' : `${joinedMates}/${totalMates || '—'}`}
                    </Text>
                    <Text style={type.label}>joined</Text>
                    <Icon name="chevron-right" size={12} color={chalk.dim} />
                  </Pressable>
                )}
              </View>
              {isEspn ? (
                <Text style={[type.bodySm, styles.espnNote]}>
                  ESPN read-only import — rankings, tiers, and trios fully
                  work; trade features for ESPN leagues come later.
                </Text>
              ) : null}
            </Card>
        </View>

        {/* #229 (approved v3 mock) — day-one action row: Rank players
            LEFT / outlined-secondary, Find a trade RIGHT / solid ice.
            Same low-activity scaffolding lifecycle as the progress module. */}
        {moduleVisible ? (
          <View style={styles.actionRow}>
            <Button
              testID="league.action.rank"
              label="Rank players"
              variant="secondary"
              onPress={goRank}
              style={styles.actionBtn}
            />
            <Button
              testID="league.action.find"
              label="Find a trade"
              variant="primary"
              onPress={goFindTrade}
              style={styles.actionBtn}
            />
          </View>
        ) : null}

        {/* Matches roll-up — tiles route to the Matches tab (FB-37), each
            deep-linking into its own segment (FB-91). `at` forces the param
            effect to re-fire when the same tile is tapped twice. #229
            zero-fold: both-zero tiles collapse into the progress module's
            unlock line and return once either count is > 0. */}
        {matchesZero ? null : (
          <>
            <TickLabel>Matches</TickLabel>
            <View style={styles.statRow}>
              <StatCard
                label="Mutual matches"
                sub="Liked by both sides"
                value={summaryPending ? '—' : matchesMutual}
                icon="match"
                onPress={() => navigation.navigate('Matches', { segment: 'mutual', at: Date.now() })}
              />
              <StatCard
                label="Awaiting them"
                sub="Your like, waiting on theirs"
                value={summaryPending ? '—' : matchesAwaiting}
                icon="eye"
                onPress={() => navigation.navigate('Matches', { segment: 'awaiting', at: Date.now() })}
              />
            </View>
          </>
        )}

        {/* #142/#144 (League rankings) + FA finder — league-wide explore
            entries. #243 (league-home fold V1, approved mock
            league-home-fold.html): the three stacked hairline rows (~201pt
            with league.rookie_board_entry on) reflowed into ONE 3-across
            tile row (~half the height); the flag adds the 3rd tile.
            #181: the rankings tile returns to the League tab's rankings
            root (this screen sits above it in the same stack); Free agents
            stays a ROOT-stack route, so navigate() bubbles up. */}
        <TickLabel>Explore</TickLabel>
        <View style={styles.exploreTiles}>
          <ExploreTile
            testID="league.rankings-row"
            icon="rank"
            label="Rankings"
            sub="Every team ranked"
            accessibilityLabel="League rankings"
            onPress={() => navigation.navigate('LeagueRankings')}
          />
          <ExploreTile
            testID="league.free-agents-row"
            icon="search"
            label="Free agents"
            sub="Best available"
            accessibilityLabel="Free agents"
            onPress={() => navigation.navigate('FreeAgents')}
          />
          {/* Third tile, one slot, two occupants (rookie-draft O1):
              `draft.room` ON  → "Rookie draft" → the root-stack DraftRoom
                                 screen (the FreeAgents navigate() pattern);
              `draft.room` OFF → today's "Rookie board" sheet, unchanged
                                 (flag league.rookie_board_entry).
              Flipping draft.room off therefore RESTORES the old tile rather
              than emptying the row. */}
          {showDraftRoom ? (
            <ExploreTile
              testID="league.draft-room-row"
              icon="flag"
              label="Rookie draft"
              sub="Board & who's left"
              accessibilityLabel="Rookie draft room"
              onPress={() => navigation.navigate('DraftRoom')}
            />
          ) : showRookieBoard ? (
            <ExploreTile
              testID="league.rookie-board-row"
              icon="flag"
              label="Rookie board"
              sub="Pre-draft prospects"
              accessibilityLabel="Rookie draft board"
              onPress={() => setRookieOpen(true)}
            />
          ) : null}
        </View>

        {/* Draft picks — ESPN pick assignment (draft-extensions W3 M-A,
            flag `picks.assign`, ships OFF). A DEDICATED section below
            Explore, deliberately NOT a 4th Explore tile: that row is a
            fold-budgeted 3-across grid whose third slot is already a
            one-slot/two-occupant conditional, and a 4th tile would either
            wrap it or contest a slot that already has two claimants. The
            separate section also keeps assignment visibly "separate from
            the draft feature", which is how the operator framed it.

            ESPN only, because ESPN is the only platform with no rookie
            draft to read — a Sleeper/MFL league already has this data and
            an entry point here would invite a member to contradict it.
            Sub-line reads the live state off `progress`. Flag off ⇒ no
            section, no query, byte-identical page. */}
        {showPickAssign ? (
          <>
            <View style={styles.divider} />
            <TickLabel>Draft picks</TickLabel>
            <Pressable
              testID="league.draft-picks-row"
              onPress={() => navigation.navigate('PickAssignment')}
              accessibilityRole="button"
              accessibilityLabel="Draft picks"
              accessibilityHint="Set who owns each rookie pick"
              style={({ pressed }) => [
                styles.picksRow,
                pressed && { backgroundColor: ink.ink3 },
              ]}
            >
              <Icon name="flag" size={18} color={chalk.dim} />
              <View style={styles.picksBody}>
                <ChalkText scale="dense" style={styles.picksTitle} numberOfLines={1}>
                  Draft picks
                </ChalkText>
                <ChalkText scale="dense" style={styles.picksSub} numberOfLines={1}>
                  {pickAssignQuery.isLoading
                    ? 'Checking…'
                    : pickAssignmentSubline(
                        pickAssignQuery.data?.progress,
                        pickAssignQuery.data?.seeded,
                      )}
                </ChalkText>
              </View>
              <Icon name="chevron-right" size={16} color={chalk.faint} />
            </Pressable>
          </>
        ) : null}

        {/* #243 — Market pulse strip (movers V3, frame D1; operator
            placement override: below Explore, not top-of-page). Self-
            contained: renders null without flag `market.movers` or data. */}
        <MarketPulseStrip />

        {/* Recent activity — flag-gated. Backend already short-circuits to
            an empty list when the flag is off, but we also gate the section
            header to avoid showing an empty "Recent activity" stub. */}
        {showActivity ? (
          <>
            <View style={styles.divider} />
            <TickLabel>Recent activity</TickLabel>
            <ActivityFeed events={activityQuery.data?.events ?? []} limit={10} />
          </>
        ) : null}

        {/* Contrarian ranks — #229 zero-fold: while the server reports
            insufficient_data (needs 3 ranked members) the empty card is
            absorbed by the progress module's fold line; returns with data. */}
        {contrarianInsufficient ? null : (
          <>
            <View style={styles.divider} />
            <TickLabel>Contrarian ranks</TickLabel>
            <ContrarianLeaderboard
              rows={contrarianQuery.data?.rows ?? []}
              insufficientData={!!contrarianQuery.data?.insufficient_data}
              message={contrarianQuery.data?.message}
            />
          </>
        )}

        {/* Ranking coverage — #229 zero-fold: the 0% bar (and its buried
            "100% to go" hint) is replaced by the progress module's
            segmented bar + unlock line; the card returns once ranked > 0. */}
        {coverageZero ? null : (
          <>
            <View style={styles.divider} />
            <TickLabel>Coverage</TickLabel>
            <Card>
              <View style={styles.statBetween}>
                <Text style={type.body}>Opponents you've ranked vs</Text>
                <Text style={type.data}>
                  {coveragePending ? '—' : `${rankedOpps}/${totalOpps || '—'}`}
                </Text>
              </View>
              <Meter
                value={coveragePending ? 0 : coveragePct / 100}
                color={coveragePct >= 100 ? semantic.pos : ice.base}
              />
              {coveragePending ? null : (
                <Text style={[type.bodySm, styles.coverageHint]}>
                  {coveragePct === 100
                    ? "You're matched up against every leaguemate. Nice."
                    : `Rank more players to widen the trade pool — ${100 - coveragePct}% to go.`}
                </Text>
              )}
            </Card>
          </>
        )}

        {/* #229/#230/#234 — the single progress module. Ring = positions
            ranked; 12-slot bar = ranked members (you + ranked leaguemates);
            one unlock sentence; fold line covers the collapsed sections. */}
        {moduleVisible ? (
          <>
            <View style={styles.divider} />
            <TickLabel>League progress</TickLabel>
            <LeagueProgressModule
              testID="league.progress-module"
              positionsRanked={positionsRanked}
              rankedMates={rankedOpps}
              totalTeams={totalTeamsN}
              showFoldLine={contrarianInsufficient}
              onRankPlayers={goRank}
              onInvite={inviteLeaguemates}
            />
          </>
        ) : null}

        {/* #229 — "Works right now": the clearly-labeled EXAMPLE trade
            renders the real TradeValueBar with static props so the quiet
            league still demonstrates the product's actual verdict
            language. Retires the moment REAL matches exist. */}
        {worksNowVisible ? (
          <>
            <View style={styles.divider} />
            <TickLabel>Works right now</TickLabel>
            <View testID="league.works-now">
              <Card>
                <ExampleTrade />
                {/* Operator tweak on the approved v3 mock: in-section
                    buttons are BOTH solid ice. */}
                <Button
                  label="Find a trade"
                  variant="primary"
                  onPress={goFindTrade}
                  style={styles.worksNowBtn}
                />
              </Card>
            </View>
          </>
        ) : null}

        {/* Leaderboards — League-specific + Universal sections inline.
            #229 zero-fold: folded alongside contrarian (same 3-ranked-
            members threshold the module's fold line states). */}
        {contrarianInsufficient ? null : (
          <>
            <View style={styles.divider} />
            <TickLabel>Leaderboards</TickLabel>
            <LeaderboardsSection leagueId={leagueId} />
          </>
        )}

        {/* ESPN leagues: manual roster re-sync (POST /api/espn/import). */}
        {isEspn ? (
          <>
            <Button
              testID="league.espn-resync"
              label={resyncing ? 'Re-syncing from ESPN…' : 'Re-sync ESPN rosters'}
              variant="secondary"
              onPress={resyncEspn}
              disabled={resyncing}
              style={styles.switchBtn}
            />
            {resyncMsg ? (
              <Text style={[type.bodySm, styles.espnNote]}>{resyncMsg}</Text>
            ) : null}
          </>
        ) : null}

        {/* #223 — the bottom "Switch league" button and this screen's
            LeagueSwitcherSheet mount are gone: the global TopBar owns the
            single switcher entry point (and carries the #199 add-a-league
            wiring). */}
      </ScrollView>

      {/* league.rookie_board_entry — read-only rookie board (fetches only
          once opened; renders nothing while closed). Mounted regardless of
          the flag so an in-flight open survives a flag revalidation; the
          Explore row above is the only opener. */}
      <RookieDraftBoardSheet
        visible={rookieOpen}
        onClose={() => setRookieOpen(false)}
      />

      {/* FB-38 — member-roster overlay: X top-right, join status per
          member, unlock chips when the per-member flag is on. Replaces
          the old standalone Leaguemates card + inline roster list. */}
      <Modal
        visible={membersOpen}
        transparent
        animationType="fade"
        onRequestClose={() => setMembersOpen(false)}
      >
        <Pressable
          style={styles.overlayBackdrop}
          onPress={() => setMembersOpen(false)}
          accessibilityRole="button"
          accessibilityLabel="Close"
        />
        <View style={styles.overlayCard}>
          <View style={styles.overlayHead}>
            <Text style={type.heading} accessibilityRole="header">League members</Text>
            <Pressable
              onPress={() => setMembersOpen(false)}
              hitSlop={12}
              accessibilityRole="button"
              accessibilityLabel="Close members overlay"
              style={({ pressed }) => [styles.overlayClose, pressed && styles.overlayClosePressed]}
            >
              <Icon name="x" size={20} color={chalk.dim} />
            </Pressable>
          </View>
          <Text style={[type.data, styles.overlaySub]}>
            {summaryPending
              ? '…'
              : `${joinedMates}/${totalMates || '—'} joined · ${unlocked1qb} unlocked 1QB · ${unlockedSf} unlocked SF`}
          </Text>
          <ScrollView style={styles.overlayList} contentContainerStyle={{ gap: 2 }}>
            {(membersQuery.data?.members ?? []).map((m) => {
              const unlock = showUnlockBadges ? unlocksById.get(m.user_id) : undefined;
              return (
                <View key={m.user_id} style={styles.memberRow}>
                  <Text style={[type.title, styles.memberName]} numberOfLines={1}>
                    {m.display_name || m.username || m.user_id}
                  </Text>
                  {showUnlockBadges && m.joined ? (
                    <StatusChip
                      label={unlock?.unlocked ? 'Unlocked' : 'in progress'}
                      color={unlock?.unlocked ? semantic.pos : ink.lineStrong}
                      icon={unlock?.unlocked ? 'check' : undefined}
                      dim={!unlock?.unlocked}
                    />
                  ) : null}
                  <StatusChip
                    label={m.joined ? 'Joined' : 'Not joined'}
                    color={m.joined ? semantic.pos : ink.lineStrong}
                    icon={m.joined ? 'check' : undefined}
                    dim={!m.joined}
                  />
                </View>
              );
            })}
          </ScrollView>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function fmtScoring(s?: string | null) {
  if (!s) return 'Scoring: —';
  const map: Record<string, string> = {
    '1qb_ppr': '1QB PPR',
    'sf_tep':  'Superflex TE-Premium',
  };
  return map[s] || s.toUpperCase();
}

// League-wide explore tiles (#142/#144 + FA finder; #243 fold V1 reflow —
// approved mock league-home-fold.html): 3-across card tiles (icon + short
// title + one-line sub) replacing the old stacked hairline rows. testIDs
// unchanged (`league.rankings-row` etc.); accessibilityLabel keeps the
// full descriptive name the rows carried.
function ExploreTile({ label, sub, icon, onPress, testID, accessibilityLabel }: {
  label: string; sub: string; icon: IconName; onPress: () => void;
  testID: string; accessibilityLabel?: string;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      style={({ pressed }) => [styles.exploreTile, pressed && { backgroundColor: ink.ink3 }]}
    >
      <Icon name={icon} size={18} color={chalk.dim} />
      <ChalkText scale="dense" style={styles.exploreTileTitle} numberOfLines={1}>
        {label}
      </ChalkText>
      <ChalkText scale="dense" style={styles.exploreTileSub} numberOfLines={1}>
        {sub}
      </ChalkText>
    </Pressable>
  );
}

// Chalkline badge construction (1px encode-color border + label type on ink)
// with an optional leading check icon — the shared Badge primitive doesn't
// take an icon, so this composes the same tokens inline.
function StatusChip({ label, color, icon, dim }: {
  label: string; color: string; icon?: IconName; dim?: boolean;
}) {
  return (
    <View style={[styles.statusChip, { borderColor: color }]}>
      {icon ? <Icon name={icon} size={12} color={color} /> : null}
      <Text style={[type.label, !dim && styles.statusChipText]}>{label}</Text>
    </View>
  );
}

function StatCard({ label, sub, value, icon, onPress }: {
  label: string; sub?: string; value: number | string; icon: IconName;
  onPress?: () => void;
}) {
  // Pressable when a destination is supplied (FB-37: Matches tiles route
  // to the Matches tab); plain tile otherwise. The chevron icon next to
  // the label is the clickability cue. Optional `sub` is a one-line
  // body-sm definition under the label (FB-91) — MethodTile construction
  // from docs/design/components.md (icon + title + body-sm desc).
  const body = (pressed: boolean) => (
    <Card style={pressed ? styles.statCardPressed : styles.statCard}>
      <Icon name={icon} size={20} color={chalk.dim} />
      <Text style={type.dataLg}>{value}</Text>
      <View style={styles.statLabelRow}>
        <Text style={type.label}>{label}</Text>
        {onPress ? <Icon name="chevron-right" size={12} color={chalk.dim} /> : null}
      </View>
      {sub ? <Text style={type.bodySm} numberOfLines={2}>{sub}</Text> : null}
    </Card>
  );
  if (!onPress) return <View style={styles.statFlex}>{body(false)}</View>;
  return (
    <Pressable
      onPress={onPress}
      style={styles.statFlex}
      accessibilityRole="button"
      accessibilityLabel={`${label} — open Matches`}
    >
      {({ pressed }) => body(pressed)}
    </Pressable>
  );
}

// #229 "Works right now" — the EXAMPLE trade card (approved v3 mock).
// Static, honest demo content: the flare label (informational highlight,
// ADR-005) says outright it is not from the user's league, and the value
// readout is the REAL TradeValueBar component with fixed props (favors
// receive, +380 ≈ 0.6 firsts → "a Mid 2nd") — same verdict language the
// calculator and deck speak, no invented UI.
const EXAMPLE_GAP = {
  value: 380,
  add_to: 'give' as const,
  firsts: 0.6,
  pick_equivalent: {
    pick_id: 'example_mid_2nd',
    label: 'Mid 2nd Round Pick',
    value: 380,
  },
};

function ExampleTradeRow({ rail, name, pos }: {
  rail: string; name: string; pos?: string;
}) {
  return (
    <View style={styles.exRow}>
      <View style={[styles.exRail, { backgroundColor: rail }]} />
      <ChalkText scale="dense" style={styles.exName} numberOfLines={1}>
        {name}
      </ChalkText>
      {pos ? (
        <ChalkText scale="dense" style={[type.label, { color: rail }]}>
          {pos}
        </ChalkText>
      ) : null}
    </View>
  );
}

function ExampleTrade() {
  return (
    <View style={styles.exTrade}>
      <ChalkText scale="dense" style={styles.exLabel}>
        Example — not from your league
      </ChalkText>
      <View style={styles.exCols}>
        <View style={[styles.exCol, styles.exColFirst]}>
          <ChalkText scale="dense" style={type.label}>You send</ChalkText>
          <ExampleTradeRow rail={positionColors.rb} name="Breece Hall" pos="RB" />
        </View>
        <View style={styles.exCol}>
          <ChalkText scale="dense" style={type.label}>You get</ChalkText>
          <ExampleTradeRow rail={positionColors.rb} name="De'Von Achane" pos="RB" />
          <ExampleTradeRow rail={ink.lineStrong} name="2027 2nd" />
        </View>
      </View>
      <View style={styles.exValueBar}>
        <TradeValueBar
          giveValue={0}
          receiveValue={0}
          favors="receive"
          gap={EXAMPLE_GAP}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  scroll: { padding: space.lg, paddingBottom: space.xxl, gap: space.md },

  // Pressed state = surface-color change only (no scale/translate).

  // Header row inside the hero card — label on the left, switch chevron
  // on the right. The chevron communicates that the whole card is
  // pressable to open the league switcher.
  heroHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  heroName: { marginTop: space.sm },
  heroChips: {
    flexDirection: 'row',
    gap: space.sm,
    marginTop: space.md,
    flexWrap: 'wrap',
    alignItems: 'center',
  },

  // FB-38 — member-roster overlay
  overlayBackdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  overlayCard: {
    position: 'absolute',
    left: space.lg,
    right: space.lg,
    top: '14%',
    maxHeight: '72%',
    backgroundColor: ink.ink2,
    borderColor: ink.line,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: space.lg,
    gap: space.sm,
    ...shadowSheet,
  },
  overlayHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  overlayClose: {
    width: 32,
    height: 32,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  overlayClosePressed: { backgroundColor: ink.ink3 },
  overlaySub: { color: chalk.dim },
  overlayList: { marginTop: space.xs },

  joinedChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.lineStrong,
  },
  joinedChipPressed: { backgroundColor: ink.ink3 },

  statRow: { flexDirection: 'row', gap: space.md },

  // #229 — day-one action row (v3 mock: equal-width pair under the hero).
  actionRow: { flexDirection: 'row', gap: space.sm },
  actionBtn: { flex: 1 },

  // #229 — "Works right now" EXAMPLE trade card internals.
  exTrade: {
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    backgroundColor: ink.ink0,
    padding: space.md,
    gap: space.sm,
  },
  exLabel: { ...type.label, color: flare.base },
  exCols: { flexDirection: 'row' },
  exCol: { flex: 1, gap: space.sm, paddingLeft: space.md },
  exColFirst: {
    paddingLeft: 0,
    paddingRight: space.md,
    borderRightWidth: 1,
    borderRightColor: ink.line,
  },
  exRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  exRail: { width: 3, height: 14 },
  exName: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi, flexShrink: 1 },
  exValueBar: {
    borderTopWidth: 1,
    borderTopColor: ink.line,
    paddingTop: space.sm + 2,
    marginTop: 2,
  },
  worksNowBtn: { marginTop: space.md },

  // #142/#144 + #243 fold V1 — explore tiles (3-across card row; sub floor
  // raised to 11px vs the mock's 10.5 per the design-system type floor).
  exploreTiles: { flexDirection: 'row', gap: space.sm },
  exploreTile: {
    flex: 1,
    minWidth: 0,
    minHeight: 44,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    backgroundColor: ink.ink1,
    padding: 10,
    gap: space.xs,
  },
  exploreTileTitle: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
  exploreTileSub: { ...type.bodySm, fontSize: 11, lineHeight: 14, color: chalk.dim },
  statFlex: { flex: 1 },
  statCard: { flex: 1 },
  statCardPressed: { flex: 1, backgroundColor: ink.ink3 },
  statLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
  },

  statBetween: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: space.sm,
  },
  coverageHint: { marginTop: space.sm },

  memberRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: space.sm,
    paddingVertical: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  memberName: { flex: 1 },

  statusChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radii.xs,
    borderWidth: 1,
  },
  statusChipText: { color: chalk.base },

  // #243 (league-home fold V1): no marginTop — the ScrollView's own
  // `gap: space.md` already separates siblings; the old marginTop stacked
  // on top of it, paying 24pt per divider for what should be a 12pt gap.
  divider: {
    height: 1,
    backgroundColor: ink.line,
  },

  // draft-extensions W3 M-A — the "Draft picks" entry row. A full-width
  // hairline row, not an ExploreTile: it carries a live state sub-line
  // ("48 of 48 assigned · 3 traded") that will not fit a third of a row.
  picksRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: 44,
    paddingHorizontal: space.sm,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    backgroundColor: ink.ink1,
  },
  picksBody: { flex: 1, minWidth: 0 },
  picksTitle: { ...type.body, color: chalk.base },
  picksSub: { ...type.bodySm, color: chalk.dim },

  switchBtn: { marginTop: space.lg },
  espnNote: { color: chalk.dim, marginTop: space.sm },

  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: space.xl,
    gap: space.sm,
  },
  emptyBody: { textAlign: 'center' },
});
