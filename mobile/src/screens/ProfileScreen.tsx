import React, { useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Image,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import { colors, posColor, tierColor } from '../theme/colors';
import type { Position, Tier } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import { getPublicProfile } from '../api/auth';
import { useFlag } from '../state/useFeatureFlags';
import type {
  PublicProfile,
  PublicProfileContrarianEntry,
} from '../shared/types';
import { ApiError } from '../api/client';

// Public profile screen — read-only view of a user's ranking footprint.
// Reached via a deep link (/u/<username>) or future in-app entry points.
// Gated by the `profiles.public_pages` feature flag both client- and
// server-side; backend returns 404 when off, which we render as a friendly
// "Profile not available" state.
//
// Out of scope: any actions (follow / connect / message). Spec calls those
// out as later work; this screen is pure display.

interface Props {
  // react-navigation route prop; we only need params.username
  route: { params?: { username?: string } };
}

const POSITIONS: Position[] = ['QB', 'RB', 'WR', 'TE'];
const TIER_ORDER: Tier[] = ['elite', 'starter', 'solid', 'depth', 'bench'];

export default function ProfileScreen({ route }: Props) {
  const username = (route?.params?.username || '').trim();
  const enabled  = useFlag('profiles.public_pages');

  const profileQuery = useQuery<PublicProfile>({
    queryKey: ['public-profile', username.toLowerCase()],
    queryFn: () => getPublicProfile(username),
    enabled: !!username && enabled,
    staleTime: 60_000,
    retry: (failures, err) => {
      // 404 = not found / feature off — no point retrying
      if (err instanceof ApiError && (err.status === 404 || err.status === 400)) {
        return false;
      }
      return failures < 1;
    },
  });

  // Derived: per-position count of tier-bucketed players. The backend
  // returns {position: {tier: [{player_id, name, elo}]}} — we just sum
  // sublist lengths so the header chips read "12 QB tiers · 8 RB …".
  const rankCountByPos = useMemo(() => {
    const out: Record<Position, number> = { QB: 0, RB: 0, WR: 0, TE: 0 };
    const snap = profileQuery.data?.tiers_snapshot;
    if (!snap) return out;
    for (const pos of POSITIONS) {
      const bucket = snap[pos.toLowerCase()];
      if (!bucket) continue;
      let n = 0;
      for (const tier of TIER_ORDER) {
        const arr = bucket[tier];
        if (Array.isArray(arr)) n += arr.length;
      }
      out[pos] = n;
    }
    return out;
  }, [profileQuery.data]);

  // ── States ────────────────────────────────────────────────────────────
  if (!enabled) {
    return (
      <SafeAreaView style={styles.root} edges={['bottom']}>
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>Profile not available</Text>
          <Text style={styles.emptyBody}>
            Public profiles are coming soon.
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  if (!username) {
    return (
      <SafeAreaView style={styles.root} edges={['bottom']}>
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>Missing username</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (profileQuery.isLoading) {
    return (
      <SafeAreaView style={styles.root} edges={['bottom']}>
        <View style={styles.loading}>
          <ActivityIndicator color={colors.accent} />
        </View>
      </SafeAreaView>
    );
  }

  if (profileQuery.isError || !profileQuery.data) {
    const status = profileQuery.error instanceof ApiError
      ? profileQuery.error.status
      : 0;
    return (
      <SafeAreaView style={styles.root} edges={['bottom']}>
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>
            {status === 404 ? 'Profile not found' : "Couldn't load profile"}
          </Text>
          <Text style={styles.emptyBody}>
            {status === 404
              ? `No public profile for @${username}.`
              : 'Try again in a moment.'}
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  const profile = profileQuery.data;

  return (
    <SafeAreaView style={styles.root} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.body}>
        {/* ── Hero ──────────────────────────────────────────────── */}
        <View style={styles.hero}>
          {profile.avatar_url ? (
            <Image
              source={{ uri: profile.avatar_url }}
              style={styles.avatar}
            />
          ) : (
            <View style={[styles.avatar, styles.avatarFallback]}>
              <Text style={styles.avatarInitial}>
                {(profile.display_name || profile.username || '?')
                  .charAt(0)
                  .toUpperCase()}
              </Text>
            </View>
          )}
          <Text style={styles.displayName}>{profile.display_name}</Text>
          <Text style={styles.username}>@{profile.username}</Text>
          <View style={styles.metaRow}>
            <View style={styles.metaChip}>
              <Text style={styles.metaChipText}>
                {profile.leagues_count} {profile.leagues_count === 1 ? 'league' : 'leagues'}
              </Text>
            </View>
            <View style={styles.metaChip}>
              <Text style={styles.metaChipText}>
                {profile.scoring_format === 'sf_tep' ? 'SF · TEP' : '1QB · PPR'}
              </Text>
            </View>
          </View>
        </View>

        {/* ── Ranks by position ────────────────────────────────── */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Ranks</Text>
          <View style={styles.posGrid}>
            {POSITIONS.map((pos) => (
              <View key={pos} style={styles.posCell}>
                <View style={[styles.posDot, { backgroundColor: posColor(pos) }]} />
                <Text style={styles.posCount}>{rankCountByPos[pos]}</Text>
                <Text style={styles.posLabel}>{pos}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* ── Tiers snapshot ───────────────────────────────────── */}
        {Object.keys(profile.tiers_snapshot || {}).length > 0 ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Tiers</Text>
            {POSITIONS.map((pos) => {
              const bucket = profile.tiers_snapshot[pos.toLowerCase()];
              if (!bucket) return null;
              return (
                <View key={pos} style={styles.tierGroup}>
                  <Text style={[styles.tierGroupTitle, { color: posColor(pos) }]}>
                    {pos}
                  </Text>
                  {TIER_ORDER.map((tier) => {
                    const entries = bucket[tier];
                    if (!entries || entries.length === 0) return null;
                    return (
                      <View key={tier} style={styles.tierRow}>
                        <View
                          style={[
                            styles.tierBadge,
                            { backgroundColor: tierColor(tier) },
                          ]}
                        >
                          <Text style={styles.tierBadgeText}>
                            {tier.toUpperCase()}
                          </Text>
                        </View>
                        <Text style={styles.tierNames} numberOfLines={2}>
                          {entries.map((e) => e.name).join(', ')}
                        </Text>
                      </View>
                    );
                  })}
                </View>
              );
            })}
          </View>
        ) : null}

        {/* ── Contrarian takes ─────────────────────────────────── */}
        {profile.contrarian_takes ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Contrarian takes</Text>
            {POSITIONS.map((pos) => {
              const lane = profile.contrarian_takes[pos.toLowerCase()];
              if (!lane) return null;
              const above = lane.above || [];
              const below = lane.below || [];
              if (!above.length && !below.length) return null;
              return (
                <View key={pos} style={styles.tierGroup}>
                  <Text style={[styles.tierGroupTitle, { color: posColor(pos) }]}>
                    {pos}
                  </Text>
                  {above.length ? (
                    <ContrarianRow label="Higher" entries={above} tint={colors.green} />
                  ) : null}
                  {below.length ? (
                    <ContrarianRow label="Lower" entries={below} tint={colors.red} />
                  ) : null}
                </View>
              );
            })}
          </View>
        ) : null}

        <Text style={styles.footer}>
          Built from @{profile.username}'s rankings across {profile.leagues_count}{' '}
          {profile.leagues_count === 1 ? 'league' : 'leagues'}.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

function ContrarianRow({
  label,
  entries,
  tint,
}: {
  label: string;
  entries: PublicProfileContrarianEntry[];
  tint: string;
}) {
  return (
    <View style={styles.contrRow}>
      <Text style={[styles.contrLabel, { color: tint }]}>{label}</Text>
      <Text style={styles.contrNames} numberOfLines={2}>
        {entries
          .map((e) => `${e.name} (${e.delta > 0 ? '+' : ''}${e.delta.toFixed(0)})`)
          .join(', ')}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  body: {
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
  },
  loading: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  empty: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
  },
  emptyTitle: {
    color: colors.text,
    fontSize: fontSize.lg,
    fontWeight: '700',
    marginBottom: spacing.xs,
  },
  emptyBody: {
    color: colors.muted,
    fontSize: fontSize.sm,
    textAlign: 'center',
  },
  hero: {
    alignItems: 'center',
    paddingVertical: spacing.lg,
  },
  avatar: {
    width: 96,
    height: 96,
    borderRadius: 48,
    backgroundColor: colors.surface,
    marginBottom: spacing.md,
  },
  avatarFallback: {
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
  },
  avatarInitial: {
    color: colors.text,
    fontSize: fontSize.xxl,
    fontWeight: '800',
  },
  displayName: {
    color: colors.text,
    fontSize: fontSize.xl,
    fontWeight: '700',
  },
  username: {
    color: colors.muted,
    fontSize: fontSize.base,
    marginTop: spacing.xs,
  },
  metaRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  metaChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: 'rgba(255,255,255,0.03)',
  },
  metaChipText: {
    color: colors.text,
    fontSize: fontSize.xs,
    fontWeight: '600',
  },
  section: {
    marginTop: spacing.xl,
  },
  sectionTitle: {
    color: colors.text,
    fontSize: fontSize.base,
    fontWeight: '700',
    marginBottom: spacing.md,
  },
  posGrid: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  posCell: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  posDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginBottom: spacing.xs,
  },
  posCount: {
    color: colors.text,
    fontSize: fontSize.xl,
    fontWeight: '800',
  },
  posLabel: {
    color: colors.muted,
    fontSize: fontSize.xs,
    fontWeight: '600',
    letterSpacing: 0.5,
  },
  tierGroup: {
    marginBottom: spacing.md,
  },
  tierGroupTitle: {
    fontSize: fontSize.sm,
    fontWeight: '700',
    letterSpacing: 0.5,
    marginBottom: spacing.xs,
  },
  tierRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.xs,
  },
  tierBadge: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.sm,
    minWidth: 64,
    alignItems: 'center',
  },
  tierBadgeText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
  tierNames: {
    flex: 1,
    color: colors.text,
    fontSize: fontSize.sm,
  },
  contrRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
    marginBottom: spacing.xs,
  },
  contrLabel: {
    width: 64,
    fontSize: fontSize.xs,
    fontWeight: '700',
    letterSpacing: 0.5,
    paddingTop: 2,
  },
  contrNames: {
    flex: 1,
    color: colors.text,
    fontSize: fontSize.sm,
  },
  footer: {
    color: colors.muted,
    fontSize: fontSize.xs,
    textAlign: 'center',
    marginTop: spacing.xl,
  },
});
