import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ScrollView,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import { getLeagueSummary, getLeagueCoverage } from '../api/league';
import { useSession } from '../state/useSession';
import LeagueSwitcherSheet from '../components/LeagueSwitcherSheet';

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

  const summaryQuery = useQuery({
    queryKey: ['league-summary', leagueId],
    queryFn:  () => getLeagueSummary(leagueId!),
    enabled:  !!leagueId,
    staleTime: 60_000,
  });

  const coverageQuery = useQuery({
    queryKey: ['league-coverage', leagueId],
    queryFn:  () => getLeagueCoverage(leagueId!),
    enabled:  !!leagueId,
    staleTime: 60_000,
  });

  const refetchAll = () => {
    summaryQuery.refetch();
    coverageQuery.refetch();
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
  const loading  = summaryQuery.isLoading || coverageQuery.isLoading;

  // Defensive number reader. Backend keys may vary slightly from typed shape.
  const num = (v: unknown, fallback = 0) =>
    typeof v === 'number' && Number.isFinite(v) ? v : fallback;

  const matchesPending  = num((summary as any)?.matches_pending);
  const matchesAccepted = num((summary as any)?.matches_accepted);
  const totalMates      = num((summary as any)?.leaguemates_total);
  const joinedMates     = num((summary as any)?.leaguemates_joined);
  const unlocked1qb     = num((summary as any)?.leaguemates_unlocked_1qb);
  const unlockedSf      = num((summary as any)?.leaguemates_unlocked_sf);
  const totalOpps       = num(coverage?.total_opponents);
  const rankedOpps      = num(coverage?.ranked_opponents);

  const coveragePct = totalOpps > 0 ? Math.round((rankedOpps / totalOpps) * 100) : 0;
  const joinPct     = totalMates > 0 ? Math.round((joinedMates / totalMates) * 100) : 0;

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
        {/* League name + scoring */}
        <View style={styles.heroCard}>
          <Text style={styles.heroLabel}>League</Text>
          <Text style={styles.heroName} numberOfLines={2}>
            {summary?.league_name || league?.league_name || 'Loading…'}
          </Text>
          <View style={styles.heroChips}>
            <Chip label={fmtScoring(summary?.default_scoring)} tone="accent" />
            <Chip label={`${num((summary as any)?.leaguemates_total ?? 0)} teams`} />
          </View>
        </View>

        {loading && !summary && !coverage ? (
          <View style={styles.center}>
            <ActivityIndicator color={colors.accent} />
          </View>
        ) : null}

        {/* Matches roll-up */}
        <SectionTitle>Matches</SectionTitle>
        <View style={styles.statRow}>
          <StatCard label="Pending"  value={matchesPending}  emoji="🤝" />
          <StatCard label="Accepted" value={matchesAccepted} emoji="✅" />
        </View>

        {/* Leaguemate progress */}
        <SectionTitle>Leaguemates</SectionTitle>
        <View style={styles.card}>
          <View style={styles.statBetween}>
            <Text style={styles.cardLabel}>Joined the app</Text>
            <Text style={styles.cardValue}>
              {joinedMates}/{totalMates || '—'}
            </Text>
          </View>
          <ProgressBar pct={joinPct} />
          <View style={[styles.statBetween, { marginTop: spacing.md }]}>
            <Text style={styles.cardSubLabel}>Unlocked 1QB</Text>
            <Text style={styles.cardSubValue}>{unlocked1qb}</Text>
          </View>
          <View style={styles.statBetween}>
            <Text style={styles.cardSubLabel}>Unlocked SF</Text>
            <Text style={styles.cardSubValue}>{unlockedSf}</Text>
          </View>
        </View>

        {/* Ranking coverage */}
        <SectionTitle>Coverage</SectionTitle>
        <View style={styles.card}>
          <View style={styles.statBetween}>
            <Text style={styles.cardLabel}>Opponents you've ranked vs</Text>
            <Text style={styles.cardValue}>
              {rankedOpps}/{totalOpps || '—'}
            </Text>
          </View>
          <ProgressBar pct={coveragePct} />
          <Text style={styles.cardHint}>
            {coveragePct === 100
              ? "You're matched up against every leaguemate. Nice."
              : `Rank more players to widen the trade pool — ${100 - coveragePct}% to go.`}
          </Text>
        </View>

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

function StatCard({ label, value, emoji }: { label: string; value: number; emoji: string }) {
  return (
    <View style={styles.statCard}>
      <Text style={styles.statEmoji}>{emoji}</Text>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
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
  heroLabel: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  heroName: { color: colors.text, fontSize: fontSize.xxl, fontWeight: '800' },
  heroChips: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.xs },

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
