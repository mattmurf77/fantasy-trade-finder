import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  ActivityIndicator,
  Linking,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import TradeCardComp from '../components/TradeCard';
import Toast from '../components/Toast';
import { getMatches, setMatchDisposition } from '../api/trades';
import { useSession } from '../state/useSession';
import { relativeTime } from '../utils/relativeTime';
import type { TradeMatch, Player } from '../shared/types';

// Matches inbox. Each match card shows both sides + Accept/Decline.
// On Accept: deep-link to the Sleeper trade propose URL so the user
// can ratify the trade on Sleeper directly.
export default function MatchesScreen() {
  const queryClient = useQueryClient();
  const league = useSession((s) => s.league);
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);

  const matchesQuery = useQuery({
    queryKey: ['matches'],
    queryFn: getMatches,
    staleTime: 15_000,
  });

  const dispMutation = useMutation({
    mutationFn: ({ id, d }: { id: string; d: 'accepted' | 'declined' }) =>
      setMatchDisposition(id, d),
    onMutate: async ({ id, d }) => {
      // Optimistic — drop the match from the list so the UI feels instant.
      const prev = queryClient.getQueryData<{ matches: TradeMatch[] }>(['matches']);
      if (prev) {
        queryClient.setQueryData(['matches'], {
          matches: prev.matches.filter((m) => m.match_id !== id),
        });
      }
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(['matches'], ctx.prev);
      setToast({ msg: 'Action failed — try again', tone: 'warn' });
    },
    onSuccess: (_res, vars) => {
      if (vars.d === 'accepted') {
        void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      }
    },
  });

  async function handleAccept(m: TradeMatch) {
    dispMutation.mutate({ id: m.match_id, d: 'accepted' });
    // Deep-link to Sleeper. Sleeper's trade-propose deep link format:
    //   https://sleeper.com/leagues/<league_id>/trade
    const url = `https://sleeper.com/leagues/${m.league_id}/trade`;
    try {
      const can = await Linking.canOpenURL(url);
      if (can) await Linking.openURL(url);
      else Alert.alert('Accepted — open Sleeper to propose the trade.', url);
    } catch {
      Alert.alert('Accepted', 'Open Sleeper manually to propose the trade.');
    }
  }

  function handleDecline(m: TradeMatch) {
    dispMutation.mutate({ id: m.match_id, d: 'declined' });
  }

  const matches = matchesQuery.data?.matches || [];

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />

      <View style={styles.header}>
        <Text style={styles.title}>Matches</Text>
        <Text style={styles.subtitle}>
          Trades where you and a leaguemate both said yes.
        </Text>
      </View>

      {matchesQuery.isLoading ? (
        <View style={styles.centered}>
          <ActivityIndicator color={colors.accent} />
        </View>
      ) : matchesQuery.isError ? (
        <View style={styles.centered}>
          <Text style={styles.errorText}>Could not load matches.</Text>
        </View>
      ) : matches.length === 0 ? (
        <View style={styles.centered}>
          <Text style={styles.emptyTitle}>No matches yet</Text>
          <Text style={styles.emptyBody}>
            Head to the Trades tab and swipe on some proposals. When a
            leaguemate likes the same trade, it'll show up here.
          </Text>
        </View>
      ) : (
        <FlatList
          contentContainerStyle={styles.list}
          data={matches}
          keyExtractor={(m) => m.match_id}
          refreshControl={
            <RefreshControl
              refreshing={matchesQuery.isFetching && !matchesQuery.isLoading}
              onRefresh={() => matchesQuery.refetch()}
              tintColor={colors.accent}
            />
          }
          renderItem={({ item }) => (
            <View style={{ gap: spacing.xs }}>
              <View style={styles.matchHeader}>
                <Text style={styles.matchLabel}>
                  🎯 New match with @{item.counterparty_username}
                </Text>
                <Text style={styles.matchTime}>{relativeTime(item.created_at)}</Text>
              </View>
              <TradeCardComp
                variant="match"
                data={matchToTradeCardShape(item, league?.league_id)}
                onAccept={() => handleAccept(item)}
                onDecline={() => handleDecline(item)}
                acting={dispMutation.isPending}
              />
            </View>
          )}
          ItemSeparatorComponent={() => <View style={{ height: spacing.lg }} />}
        />
      )}
    </SafeAreaView>
  );
}

// TradeMatch and TradeCard have overlapping but not identical shapes —
// TradeMatch stores player IDs only, not full Player objects. This
// adapter stubs out player fields to the minimum TradeCardComp needs
// (name + position + team). Real population will require a followup
// endpoint that returns the joined players; until then we show IDs.
function matchToTradeCardShape(m: TradeMatch, fallbackLeague: string | undefined) {
  const mkPlayer = (id: string): Player => ({
    id,
    name: id,
    position: 'FLX' as any,
    team: '',
  });
  return {
    trade_id: m.match_id,
    league_id: m.league_id || fallbackLeague || '',
    give_player_ids: m.my_side_player_ids,
    receive_player_ids: m.their_side_player_ids,
    give_players: m.my_side_player_ids.map(mkPlayer),
    receive_players: m.their_side_player_ids.map(mkPlayer),
    opponent_user_id: m.counterparty_user_id,
    opponent_username: m.counterparty_username,
    match_score: 100,
    fairness: 1,
  };
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  header: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  title: { color: colors.text, fontSize: fontSize.xxl, fontWeight: '800' },
  subtitle: { color: colors.muted, fontSize: fontSize.sm, marginTop: 4 },
  list: { padding: spacing.lg, paddingBottom: 96 },
  matchHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 4,
  },
  matchLabel: { color: colors.green, fontSize: fontSize.sm, fontWeight: '700' },
  matchTime: { color: colors.muted, fontSize: fontSize.xs },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    gap: spacing.sm,
  },
  errorText: { color: colors.red, fontSize: fontSize.sm },
  emptyTitle: { color: colors.text, fontSize: fontSize.lg, fontWeight: '800' },
  emptyBody: {
    color: colors.muted,
    fontSize: fontSize.sm,
    textAlign: 'center',
    lineHeight: 22,
    maxWidth: 340,
  },
});
