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

import {
  ink,
  chalk,
  ice,
  semantic,
  tier,
  space,
  type,
} from '../theme/chalkline';
import {
  TickLabel,
  Badge,
  PositionBadge,
  TierChalkBadge,
  Card,
} from '../components/chalkline';
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

type Position = 'QB' | 'RB' | 'WR' | 'TE';
type Tier = keyof typeof tier;

const POSITIONS: Position[] = ['QB', 'RB', 'WR', 'TE'];
const TIER_ORDER: Tier[] = [
  'firsts_4plus', 'firsts_3', 'firsts_2', 'first_1',
  'second', 'third', 'fourth', 'waivers',
];

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
      for (const t of TIER_ORDER) {
        const arr = bucket[t];
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
          <ActivityIndicator color={ice.base} />
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
        {/* ── Hero / identity block ─────────────────────────────── */}
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
            <Badge
              label={`${profile.leagues_count} ${profile.leagues_count === 1 ? 'league' : 'leagues'}`}
            />
            <Badge
              label={profile.scoring_format === 'sf_tep' ? 'SF · TEP' : '1QB · PPR'}
            />
          </View>
        </View>

        {/* ── Ranks by position ────────────────────────────────── */}
        <View style={styles.section}>
          <View style={styles.sectionTitle}>
            <TickLabel>Ranks</TickLabel>
          </View>
          <Card>
            {POSITIONS.map((pos, i) => (
              <View
                key={pos}
                style={[styles.kvRow, i > 0 && styles.kvRowBorder]}
              >
                <PositionBadge pos={pos} />
                <Text style={styles.kvValue}>{rankCountByPos[pos]}</Text>
              </View>
            ))}
          </Card>
        </View>

        {/* ── Tiers snapshot ───────────────────────────────────── */}
        {Object.keys(profile.tiers_snapshot || {}).length > 0 ? (
          <View style={styles.section}>
            <View style={styles.sectionTitle}>
              <TickLabel>Tiers</TickLabel>
            </View>
            {POSITIONS.map((pos) => {
              const bucket = profile.tiers_snapshot[pos.toLowerCase()];
              if (!bucket) return null;
              return (
                <View key={pos} style={styles.tierGroup}>
                  <View style={styles.tierGroupTitle}>
                    <PositionBadge pos={pos} />
                  </View>
                  {TIER_ORDER.map((t) => {
                    const entries = bucket[t];
                    if (!entries || entries.length === 0) return null;
                    return (
                      <View key={t} style={styles.tierRow}>
                        <View style={styles.tierBadgeCol}>
                          <TierChalkBadge t={t} />
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
            <View style={styles.sectionTitle}>
              <TickLabel>Contrarian takes</TickLabel>
            </View>
            {POSITIONS.map((pos) => {
              const lane = profile.contrarian_takes[pos.toLowerCase()];
              if (!lane) return null;
              const above = lane.above || [];
              const below = lane.below || [];
              if (!above.length && !below.length) return null;
              return (
                <View key={pos} style={styles.tierGroup}>
                  <View style={styles.tierGroupTitle}>
                    <PositionBadge pos={pos} />
                  </View>
                  {above.length ? (
                    <ContrarianRow label="Higher" entries={above} tint={semantic.pos} />
                  ) : null}
                  {below.length ? (
                    <ContrarianRow label="Lower" entries={below} tint={semantic.neg} />
                  ) : null}
                </View>
              );
            })}
          </View>
        ) : null}

        <Text style={styles.footer}>
          Built from @{profile.username}'s rankings across{' '}
          <Text style={styles.footerCount}>{profile.leagues_count}</Text>{' '}
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
        {entries.map((e, i) => (
          <Text key={e.player_id || i}>
            {i > 0 ? ', ' : ''}
            {e.name} (
            <Text style={type.data}>
              {`${e.delta > 0 ? '+' : ''}${e.delta.toFixed(0)}`}
            </Text>
            )
          </Text>
        ))}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: ink.ink0,
  },
  body: {
    padding: space.lg,
    paddingBottom: space.xxl,
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
    paddingHorizontal: space.xl,
  },
  emptyTitle: {
    ...type.heading,
    textAlign: 'center',
    marginBottom: space.xs,
  },
  emptyBody: {
    ...type.bodySm,
    textAlign: 'center',
  },
  hero: {
    alignItems: 'center',
    paddingVertical: space.lg,
  },
  avatar: {
    width: 96,
    height: 96,
    borderRadius: 48, // avatar image may stay round (screen-specific exception)
    backgroundColor: ink.ink1,
    marginBottom: space.md,
  },
  avatarFallback: {
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: ink.line,
  },
  avatarInitial: {
    ...type.display,
  },
  displayName: {
    ...type.title,
  },
  username: {
    ...type.bodySm,
    marginTop: space.xs,
  },
  metaRow: {
    flexDirection: 'row',
    gap: space.sm,
    marginTop: space.md,
  },
  section: {
    marginTop: space.xl,
  },
  sectionTitle: {
    marginBottom: space.md,
  },
  kvRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: space.md,
  },
  kvRowBorder: {
    borderTopWidth: 1,
    borderTopColor: ink.line,
  },
  kvValue: {
    ...type.data,
  },
  tierGroup: {
    marginBottom: space.md,
  },
  tierGroupTitle: {
    marginBottom: space.xs,
  },
  tierRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    marginBottom: space.xs,
  },
  tierBadgeCol: {
    minWidth: 72,
  },
  tierNames: {
    flex: 1,
    ...type.bodySm,
    color: chalk.base,
  },
  contrRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: space.sm,
    marginBottom: space.xs,
  },
  contrLabel: {
    ...type.label,
    width: 72,
    paddingTop: 2,
  },
  contrNames: {
    flex: 1,
    ...type.bodySm,
    color: chalk.base,
  },
  footer: {
    ...type.bodySm,
    textAlign: 'center',
    marginTop: space.xl,
  },
  footerCount: {
    ...type.data,
    color: chalk.dim,
  },
});
