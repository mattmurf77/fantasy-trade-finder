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

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import {
  getLeagueSummary,
  getLeagueCoverage,
  getLeagueMembers,
  getLeagueMemberUnlockStates,
  getActivityFeed,
  getContrarianLeaderboard,
} from '../api/league';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import LeagueSwitcherSheet from '../components/LeagueSwitcherSheet';
import LeaderboardsSection from '../components/LeaderboardsSection';
import ActivityFeed from '../components/ActivityFeed';
import ContrarianLeaderboard from '../components/ContrarianLeaderboard';

// League tab v1 — replaces the prior PlaceholderScreen. Pulls
// /api/league/summary + /api/league/coverage and renders:
//   • League name + scoring + scoring chip
//   • Matches stats (pending / accepted)
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

  // Leaguemate roster (joined ✓ / not-joined ✗). Mirrors the web
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
          <Text style={styles.emptyTitle}>No league selected</Text>
          <Text style={styles.emptyBody}>
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

  const matchesPending  = num((summary as any)?.matches_pending);
  const matchesAccepted = num((summary as any)?.matches_accepted);
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
            tintColor={colors.accent}
          />
        }
      >
        {/* League name + scoring. The whole hero card is now a Pressable
            that opens the LeagueSwitcherSheet — matching the web feedback
            ("Let me navigate/update my league directly from the page
            itself"). The small ⇅ chevron in the top-right communicates
            the affordance; the existing "Switch league →" button at the
            bottom remains for users who scroll past the hero. */}
        <Pressable
          onPress={() => setSwitcherOpen(true)}
          style={({ pressed }) => [styles.heroCard, pressed && { opacity: 0.85 }]}
          accessibilityRole="button"
          accessibilityLabel="Switch league"
        >
          <View style={styles.heroHead}>
            <Text style={styles.heroLabel}>League</Text>
            <Text style={styles.heroChevron}>⇅</Text>
          </View>
          <Text style={styles.heroName} numberOfLines={2}>
            {summary?.league_name || league?.league_name || 'Loading…'}
          </Text>
          <View style={styles.heroChips}>
            <Chip label={fmtScoring(summary?.default_scoring)} tone="accent" />
            <Chip label={summary ? `${num((summary as any)?.leaguemates_total) + 1} teams` : '— teams'} />
            {/* FB-38/42 — joined summary lives in the hero; tapping it opens
                the member-roster overlay. Inner Pressable so the tap doesn't
                bubble to the hero's switch-league handler. The › chevron is
                the clickability cue the feedback asked for. */}
            <Pressable
              onPress={() => setMembersOpen(true)}
              style={({ pressed }) => [
                styles.chip, styles.chipAccent, pressed && { opacity: 0.7 },
              ]}
              accessibilityRole="button"
              accessibilityLabel="View league members and join status"
            >
              <Text style={[styles.chipText, styles.chipTextAccent]}>
                {summaryPending ? '— joined' : `${joinedMates}/${totalMates || '—'} joined`} ›
              </Text>
            </Pressable>
          </View>
        </Pressable>

        {/* Matches roll-up — tiles route to the Matches tab (FB-37). */}
        <SectionTitle>Matches</SectionTitle>
        <View style={styles.statRow}>
          <StatCard
            label="Pending"
            value={summaryPending ? '—' : matchesPending}
            emoji="🤝"
            onPress={() => navigation.navigate('Matches')}
          />
          <StatCard
            label="Accepted"
            value={summaryPending ? '—' : matchesAccepted}
            emoji="✅"
            onPress={() => navigation.navigate('Matches')}
          />
        </View>

        {/* Recent activity — flag-gated. Backend already short-circuits to
            an empty list when the flag is off, but we also gate the section
            header to avoid showing an empty "Recent activity" stub. */}
        {showActivity ? (
          <>
            <View style={styles.divider} />
            <SectionTitle>Recent activity</SectionTitle>
            <ActivityFeed events={activityQuery.data?.events ?? []} limit={10} />
          </>
        ) : null}

        {/* Contrarian ranks — always shown; renders an invite-prompt empty
            state when the league has too few ranking-takers for a baseline. */}
        <SectionTitle>Contrarian ranks</SectionTitle>
        <ContrarianLeaderboard
          rows={contrarianQuery.data?.rows ?? []}
          insufficientData={!!contrarianQuery.data?.insufficient_data}
          message={contrarianQuery.data?.message}
        />

        {/* Ranking coverage */}
        <SectionTitle>Coverage</SectionTitle>
        <View style={styles.card}>
          <View style={styles.statBetween}>
            <Text style={styles.cardLabel}>Opponents you've ranked vs</Text>
            <Text style={styles.cardValue}>
              {coveragePending ? '—' : `${rankedOpps}/${totalOpps || '—'}`}
            </Text>
          </View>
          <ProgressBar pct={coveragePending ? 0 : coveragePct} />
          {coveragePending ? null : (
            <Text style={styles.cardHint}>
              {coveragePct === 100
                ? "You're matched up against every leaguemate. Nice."
                : `Rank more players to widen the trade pool — ${100 - coveragePct}% to go.`}
            </Text>
          )}
        </View>

        {/* Leaderboards — League-specific + Universal sections inline. */}
        <SectionTitle>Leaderboards</SectionTitle>
        <LeaderboardsSection leagueId={leagueId} />

        {/* Switch league — opens an in-app sheet rather than nuking the
            session and bouncing back to the LeaguePicker stack. */}
        <Pressable
          onPress={() => setSwitcherOpen(true)}
          style={({ pressed }) => [
            styles.switchBtn,
            pressed && { opacity: 0.7 },
          ]}
        >
          <Text style={styles.switchBtnText}>Switch league →</Text>
        </Pressable>
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
            <Text style={styles.overlayTitle}>League members</Text>
            <Pressable
              onPress={() => setMembersOpen(false)}
              hitSlop={12}
              accessibilityRole="button"
              accessibilityLabel="Close members overlay"
              style={({ pressed }) => [pressed && { opacity: 0.6 }]}
            >
              <Text style={styles.overlayClose}>✕</Text>
            </Pressable>
          </View>
          <Text style={styles.overlaySub}>
            {summaryPending
              ? '…'
              : `${joinedMates}/${totalMates || '—'} joined · ${unlocked1qb} unlocked 1QB · ${unlockedSf} unlocked SF`}
          </Text>
          <ScrollView style={styles.overlayList} contentContainerStyle={{ gap: 2 }}>
            {(membersQuery.data?.members ?? []).map((m) => {
              const unlock = showUnlockBadges ? unlocksById.get(m.user_id) : undefined;
              return (
                <View key={m.user_id} style={styles.memberRow}>
                  <Text style={styles.memberName} numberOfLines={1}>
                    {m.display_name || m.username || m.user_id}
                  </Text>
                  {showUnlockBadges && m.joined ? (
                    <View style={[
                      styles.unlockChip,
                      unlock?.unlocked ? styles.unlockChipOn : styles.unlockChipOff,
                    ]}>
                      <Text style={[
                        styles.unlockChipText,
                        unlock?.unlocked ? styles.unlockChipTextOn : styles.unlockChipTextOff,
                      ]}>
                        {unlock?.unlocked ? '✓ Unlocked' : 'in progress'}
                      </Text>
                    </View>
                  ) : null}
                  <View style={[
                    styles.memberBadge,
                    m.joined ? styles.memberBadgeJoined : styles.memberBadgeNotJoined,
                  ]}>
                    <Text style={[
                      styles.memberBadgeText,
                      m.joined ? styles.memberBadgeTextJoined : styles.memberBadgeTextNotJoined,
                    ]}>
                      {m.joined ? '✓ Joined' : 'Not joined'}
                    </Text>
                  </View>
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

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <Text style={styles.sectionTitle}>{children}</Text>;
}

function Chip({ label, tone }: { label: string; tone?: 'accent' }) {
  return (
    <View style={[styles.chip, tone === 'accent' && styles.chipAccent]}>
      <Text style={[styles.chipText, tone === 'accent' && styles.chipTextAccent]}>
        {label}
      </Text>
    </View>
  );
}

function StatCard({ label, value, emoji, onPress }: {
  label: string; value: number | string; emoji: string; onPress?: () => void;
}) {
  // Pressable when a destination is supplied (FB-37: Matches tiles route
  // to the Matches tab); plain tile otherwise. The › chevron next to the
  // label is the clickability cue.
  const body = (
    <>
      <Text style={styles.statEmoji}>{emoji}</Text>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{onPress ? `${label} ›` : label}</Text>
    </>
  );
  if (!onPress) return <View style={styles.statCard}>{body}</View>;
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.statCard, pressed && { opacity: 0.7 }]}
      accessibilityRole="button"
      accessibilityLabel={`${label} — open Matches`}
    >
      {body}
    </Pressable>
  );
}

function ProgressBar({ pct }: { pct: number }) {
  const safe = Math.max(0, Math.min(100, pct));
  return (
    <View style={styles.progressTrack}>
      <View
        style={[
          styles.progressFill,
          {
            width: `${safe}%`,
            backgroundColor: safe >= 100 ? colors.green : colors.accent,
          },
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.md },

  heroCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  // Header row inside the hero card — label on the left, switch chevron
  // on the right. The chevron communicates that the whole card is
  // pressable to open the league switcher.
  heroHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  heroChevron: {
    color: colors.muted,
    fontSize: 16,
    fontWeight: '700',
  },
  heroLabel: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  heroName: { color: colors.text, fontSize: fontSize.xxl, fontWeight: '800' },
  heroChips: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.xs, flexWrap: 'wrap' },

  // FB-38 — member-roster overlay
  overlayBackdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.55)' },
  overlayCard: {
    position: 'absolute',
    left: spacing.lg,
    right: spacing.lg,
    top: '14%',
    maxHeight: '72%',
    backgroundColor: colors.bg,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.xl,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  overlayHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  overlayTitle: { color: colors.text, fontSize: fontSize.lg, fontWeight: '800' },
  overlayClose: { color: colors.muted, fontSize: fontSize.lg, fontWeight: '800' },
  overlaySub: { color: colors.muted, fontSize: fontSize.xs },
  overlayList: { marginTop: spacing.xs },

  chip: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.bg,
  },
  chipAccent: {
    borderColor: colors.accent,
    backgroundColor: 'rgba(79,124,255,0.10)',
  },
  chipText: { color: colors.muted, fontSize: fontSize.xs, fontWeight: '700' },
  chipTextAccent: { color: colors.accent },

  sectionTitle: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
    marginTop: spacing.md,
    marginLeft: 4,
  },

  statRow: { flexDirection: 'row', gap: spacing.md },
  statCard: {
    flex: 1,
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: spacing.lg,
    alignItems: 'center',
    gap: 4,
  },
  statEmoji: { fontSize: 24 },
  statValue: { color: colors.text, fontSize: fontSize.xxl, fontWeight: '800' },
  statLabel: { color: colors.muted, fontSize: fontSize.xs, fontWeight: '700' },

  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  statBetween: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  cardLabel:    { color: colors.text,  fontSize: fontSize.sm,  fontWeight: '700' },
  cardValue:    { color: colors.text,  fontSize: fontSize.lg,  fontWeight: '800' },
  cardSubLabel: { color: colors.muted, fontSize: fontSize.xs },
  cardSubValue: { color: colors.text,  fontSize: fontSize.sm,  fontWeight: '700' },
  cardHint:     { color: colors.muted, fontSize: fontSize.xs,  marginTop: spacing.xs, lineHeight: 18 },

  memberRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  memberName: {
    flex: 1,
    color: colors.text,
    fontSize: fontSize.sm,
    fontWeight: '700',
    marginRight: spacing.sm,
  },
  memberBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  memberBadgeJoined: {
    backgroundColor: 'rgba(34,197,94,0.12)',
    borderColor: 'rgba(34,197,94,0.45)',
  },
  memberBadgeNotJoined: {
    backgroundColor: 'transparent',
    borderColor: colors.border,
    borderStyle: 'dashed',
  },
  memberBadgeText: { fontSize: 10, fontWeight: '800', letterSpacing: 0.3 },
  memberBadgeTextJoined: { color: colors.green },
  memberBadgeTextNotJoined: { color: colors.muted },

  unlockChip: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: radius.pill,
    borderWidth: 1,
    marginRight: spacing.xs,
  },
  unlockChipOn: {
    backgroundColor: 'rgba(34,197,94,0.10)',
    borderColor: 'rgba(34,197,94,0.40)',
  },
  unlockChipOff: {
    backgroundColor: 'transparent',
    borderColor: colors.border,
  },
  unlockChipText: { fontSize: 10, fontWeight: '800', letterSpacing: 0.3 },
  unlockChipTextOn: { color: colors.green },
  unlockChipTextOff: { color: colors.muted },

  divider: {
    height: 1,
    backgroundColor: colors.border,
    marginTop: spacing.md,
  },

  progressTrack: {
    height: 6,
    backgroundColor: colors.border,
    borderRadius: radius.pill,
    overflow: 'hidden',
    marginTop: 4,
  },
  progressFill: { height: '100%', borderRadius: radius.pill },

  switchBtn: {
    marginTop: spacing.lg,
    paddingVertical: 14,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
  },
  switchBtnText: { color: colors.muted, fontSize: fontSize.sm, fontWeight: '700' },

  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl, gap: spacing.sm },
  emptyTitle: { color: colors.text, fontSize: fontSize.lg, fontWeight: '800' },
  emptyBody:  { color: colors.muted, fontSize: fontSize.sm, textAlign: 'center', lineHeight: 22 },
});
