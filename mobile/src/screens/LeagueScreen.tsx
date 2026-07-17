import React, { useState, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ScrollView,
  RefreshControl,
  Modal,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { useQuery } from '@tanstack/react-query';

import {
  ink,
  chalk,
  ice,
  semantic,
  space,
  radii,
  type,
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
} from '../components/chalkline';
import {
  getLeagueSummary,
  getLeagueCoverage,
  getLeagueMembers,
  getLeagueMemberUnlockStates,
  getActivityFeed,
  getContrarianLeaderboard,
} from '../api/league';
import { importEspnLeague } from '../api/espn';
import { initLeagueSession } from '../api/auth';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import LeagueSwitcherSheet from '../components/LeagueSwitcherSheet';
import LeaderboardsSection from '../components/LeaderboardsSection';
import ActivityFeed from '../components/ActivityFeed';
import ContrarianLeaderboard from '../components/ContrarianLeaderboard';

// League tab v1 — replaces the prior PlaceholderScreen. Pulls
// /api/league/summary + /api/league/coverage and renders:
//   • League name + scoring + scoring chip
//   • Matches stats (mutual matches / awaiting them — FB-91: tiles mirror
//     the Matches tab's two segments so both surfaces always agree)
//   • Leaguemate join progress (joined / total) + 1QB/SF unlocked counts
//   • Ranking-coverage bar (ranked opponents / total)
//   • "Switch league" → returns to LeaguePicker via session reset
export default function LeagueScreen() {
  const league   = useSession((s) => s.league);
  const leagueId = league?.league_id || null;
  const [switcherOpen, setSwitcherOpen] = useState(false);
  // FB-38/42 — member-roster overlay, opened from the hero's joined chip.
  const [membersOpen, setMembersOpen] = useState(false);
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
        {/* League name + scoring. The whole hero card is now a Pressable
            that opens the LeagueSwitcherSheet — matching the web feedback
            ("Let me navigate/update my league directly from the page
            itself"). The small chevron in the top-right communicates
            the affordance; the existing "Switch league" button at the
            bottom remains for users who scroll past the hero. */}
        <Pressable
          testID="league.hero"
          onPress={() => setSwitcherOpen(true)}
          accessibilityRole="button"
          accessibilityLabel="Switch league"
        >
          {({ pressed }) => (
            <Card style={pressed ? styles.cardPressed : undefined}>
              <View style={styles.heroHead}>
                <Text style={type.label}>League</Text>
                <Icon name="chevron-down" size={16} color={chalk.dim} />
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
                <Badge
                  label={
                    summary
                      ? `${num(summary.total_teams, num((summary as any)?.leaguemates_total) + 1)} teams`
                      : '— teams'
                  }
                />
                {/* FB-38/42 — joined summary lives in the hero; tapping it opens
                    the member-roster overlay. Inner Pressable so the tap doesn't
                    bubble to the hero's switch-league handler. The chevron icon
                    is the clickability cue the feedback asked for. */}
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
              </View>
              {isEspn ? (
                <Text style={[type.bodySm, styles.espnNote]}>
                  ESPN read-only import — rankings, tiers, and trios fully
                  work; trade features for ESPN leagues come later.
                </Text>
              ) : null}
            </Card>
          )}
        </Pressable>

        {/* Matches roll-up — tiles route to the Matches tab (FB-37), each
            deep-linking into its own segment (FB-91). `at` forces the param
            effect to re-fire when the same tile is tapped twice. */}
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

        {/* #142/#144 (League rankings) + FA finder — league-wide explore
            rows, LeagueRow construction (hairline list rows, not cards).
            Both destinations are ROOT-stack routes (see RootNav), so
            navigate() bubbles up from the tab navigator. */}
        <TickLabel>Explore</TickLabel>
        <View>
          <ExploreRow
            testID="league.rankings-row"
            label="League rankings"
            sub="Every team ranked by total roster value"
            onPress={() => navigation.navigate('LeagueSummary')}
          />
          <ExploreRow
            testID="league.free-agents-row"
            label="Free agents"
            sub="Best available players in this league"
            onPress={() => navigation.navigate('FreeAgents')}
          />
        </View>

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

        {/* Contrarian ranks — always shown; renders an invite-prompt empty
            state when the league has too few ranking-takers for a baseline. */}
        <View style={styles.divider} />
        <TickLabel>Contrarian ranks</TickLabel>
        <ContrarianLeaderboard
          rows={contrarianQuery.data?.rows ?? []}
          insufficientData={!!contrarianQuery.data?.insufficient_data}
          message={contrarianQuery.data?.message}
        />

        {/* Ranking coverage */}
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

        {/* Leaderboards — League-specific + Universal sections inline. */}
        <View style={styles.divider} />
        <TickLabel>Leaderboards</TickLabel>
        <LeaderboardsSection leagueId={leagueId} />

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

        {/* Switch league — opens an in-app sheet rather than nuking the
            session and bouncing back to the LeaguePicker stack. */}
        <Button
          label="Switch league"
          variant="secondary"
          onPress={() => setSwitcherOpen(true)}
          style={styles.switchBtn}
        />
      </ScrollView>

      <LeagueSwitcherSheet
        visible={switcherOpen}
        onClose={() => setSwitcherOpen(false)}
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
        <Pressable style={styles.overlayBackdrop} onPress={() => setMembersOpen(false)} />
        <View style={styles.overlayCard}>
          <View style={styles.overlayHead}>
            <Text style={type.heading}>League members</Text>
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

// League-wide explore rows (#142/#144 + FA finder) — LeagueRow construction:
// hairline-separated list row, title + body-sm chalk-dim meta + chevron.
function ExploreRow({ label, sub, onPress, testID }: {
  label: string; sub: string; onPress: () => void; testID: string;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => [styles.exploreRow, pressed && { backgroundColor: ink.ink3 }]}
    >
      <View style={styles.exploreMain}>
        <Text style={type.title}>{label}</Text>
        <Text style={[type.bodySm, styles.exploreSub]}>{sub}</Text>
      </View>
      <Icon name="chevron-right" size={16} color={chalk.dim} />
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

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  scroll: { padding: space.lg, paddingBottom: space.xxl, gap: space.md },

  // Pressed state = surface-color change only (no scale/translate).
  cardPressed: { backgroundColor: ink.ink3 },

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

  // #142/#144 — explore rows (LeagueRow list construction)
  exploreRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.md,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  exploreMain: { flex: 1, gap: 2 },
  exploreSub: { color: chalk.dim },
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

  divider: {
    height: 1,
    backgroundColor: ink.line,
    marginTop: space.md,
  },

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
