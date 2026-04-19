import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  FlatList,
  Pressable,
  ActivityIndicator,
  StyleSheet,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import { useSession } from '../state/useSession';
import { getLeagues, getLeagueRosters, getLeagueUsers } from '../api/sleeper';
import { sessionInit } from '../api/auth';
import type { LeagueSummary } from '../shared/types';

interface Props {
  onLeaguePicked: () => void;
  onSignOut: () => void;
}

// Show user's leagues → tap one → run sessionInit against it → done.
// Matches the web app's selectLeague flow but without the overlay modals.
export default function LeaguePickerScreen({ onLeaguePicked, onSignOut }: Props) {
  const user = useSession((s) => s.user);
  const cached = useSession((s) => s.leagues);
  const setLeagues = useSession((s) => s.setLeagues);
  const setLeague = useSession((s) => s.setLeague);

  const [loading, setLoading] = useState(cached.length === 0);
  const [selectingId, setSelectingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    if (cached.length > 0) {
      setLoading(false);
      return;
    }
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.user_id]);

  async function refresh() {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      const lgs = await getLeagues(user.user_id);
      setLeagues(lgs);
    } catch (e: any) {
      setError(e?.message || 'Could not load leagues');
    } finally {
      setLoading(false);
    }
  }

  async function pickLeague(lg: LeagueSummary) {
    if (!user || selectingId) return;
    setSelectingId(lg.league_id);
    setError(null);
    try {
      // Fetch rosters + users to build the session_init payload, same shape
      // as the web app sends from selectLeague().
      const [rosters, leagueUsers] = await Promise.all([
        getLeagueRosters(lg.league_id),
        getLeagueUsers(lg.league_id),
      ]);
      const usernameMap: Record<string, string> = {};
      for (const u of leagueUsers || []) {
        usernameMap[u.user_id] = u.display_name || u.username || u.user_id;
      }
      const myRoster = (rosters || []).find((r) => r.owner_id === user.user_id);
      const myPlayerIds = (myRoster?.players || []).filter(Boolean);
      const opponentRosters = (rosters || [])
        .filter((r) => r.owner_id && r.owner_id !== user.user_id)
        .map((r) => ({
          user_id: r.owner_id,
          username: usernameMap[r.owner_id] || `Team ${r.roster_id}`,
          player_ids: (r.players || []).filter(Boolean),
        }))
        .filter((r) => r.player_ids.length > 0);

      await sessionInit({
        user_id: user.user_id,
        username: user.username,
        display_name: user.display_name,
        avatar: user.avatar_id,
        league_id: lg.league_id,
        league_name: lg.name,
        user_player_ids: myPlayerIds,
        opponent_rosters: opponentRosters,
      });

      await setLeague({ league_id: lg.league_id, league_name: lg.name });
      onLeaguePicked();
    } catch (e: any) {
      setError(e?.message || 'Failed to import this league');
      setSelectingId(null);
    }
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Choose a League</Text>
          <Text style={styles.sub}>Leagues for {user?.display_name || '…'}</Text>
        </View>
        <Pressable onPress={onSignOut} hitSlop={10}>
          <Text style={styles.signout}>Sign out</Text>
        </Pressable>
      </View>

      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator color={colors.accent} />
          <Text style={styles.loadingText}>Loading your leagues…</Text>
        </View>
      ) : error ? (
        <View style={styles.centered}>
          <Text style={styles.error}>{error}</Text>
          <Pressable onPress={refresh}>
            <Text style={styles.retry}>Try again</Text>
          </Pressable>
        </View>
      ) : cached.length === 0 ? (
        <View style={styles.centered}>
          <Text style={styles.error}>
            No 2026 NFL leagues found for this account.
          </Text>
        </View>
      ) : (
        <FlatList
          data={cached}
          keyExtractor={(lg) => lg.league_id}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl refreshing={false} onRefresh={refresh} tintColor={colors.accent} />
          }
          renderItem={({ item }) => {
            const isBusy = selectingId === item.league_id;
            return (
              <Pressable
                style={({ pressed }) => [
                  styles.row,
                  pressed && styles.rowPressed,
                  isBusy && styles.rowBusy,
                ]}
                onPress={() => pickLeague(item)}
                disabled={!!selectingId}
              >
                <View style={styles.rowAvatar}>
                  <Text style={styles.rowAvatarEmoji}>🏈</Text>
                </View>
                <View style={styles.rowBody}>
                  <Text style={styles.rowName} numberOfLines={1}>
                    {item.name}
                  </Text>
                  <Text style={styles.rowMeta}>
                    {item.total_rosters || 12} teams
                  </Text>
                </View>
                {isBusy ? (
                  <ActivityIndicator color={colors.accent} />
                ) : (
                  <Text style={styles.chevron}>›</Text>
                )}
              </Pressable>
            );
          }}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  header: {
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  title: { color: colors.text, fontSize: fontSize.xl, fontWeight: '800' },
  sub: { color: colors.muted, fontSize: fontSize.sm, marginTop: 2 },
  signout: { color: colors.muted, fontSize: fontSize.sm, fontWeight: '600' },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    gap: spacing.md,
  },
  loadingText: { color: colors.muted, fontSize: fontSize.sm },
  error: { color: colors.red, fontSize: fontSize.sm, textAlign: 'center' },
  retry: { color: colors.accent, fontSize: fontSize.sm, fontWeight: '700' },
  list: { padding: spacing.lg, gap: spacing.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: spacing.lg,
    marginBottom: spacing.sm,
    gap: spacing.md,
  },
  rowPressed: { borderColor: colors.accent, backgroundColor: 'rgba(79,124,255,0.06)' },
  rowBusy: { opacity: 0.6 },
  rowAvatar: {
    width: 44,
    height: 44,
    borderRadius: 10,
    backgroundColor: 'rgba(79,124,255,0.12)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowAvatarEmoji: { fontSize: 22 },
  rowBody: { flex: 1, minWidth: 0 },
  rowName: { color: colors.text, fontSize: fontSize.base, fontWeight: '700' },
  rowMeta: { color: colors.muted, fontSize: fontSize.xs, marginTop: 2 },
  chevron: { color: colors.muted, fontSize: 22 },
});
