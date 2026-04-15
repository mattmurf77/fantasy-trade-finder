import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView,
  ActivityIndicator, Alert,
} from 'react-native';
import { colors, spacing, fontSize, borderRadius } from '../utils/theme';
import { api } from '../services/api';
import { useApp } from '../context/AppContext';

export default function LeagueSelectScreen({ navigation }) {
  const { user, setLeague, setLeagues } = useApp();
  const [leagues, setLocalLeagues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedIdx, setSelectedIdx] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    loadLeagues();
  }, []);

  const loadLeagues = async () => {
    try {
      const data = await api.getLeagues(user.user_id);
      if (!data || !data.length) {
        setError('No 2024 NFL leagues found for this account.');
        setLoading(false);
        return;
      }
      setLocalLeagues(data);
      setLeagues(data);
    } catch (e) {
      setError('Failed to load leagues. Check your connection.');
    } finally {
      setLoading(false);
    }
  };

  const selectLeague = async (idx) => {
    const lg = leagues[idx];
    setSelectedIdx(idx);

    try {
      // 1. Warm player cache
      await api.warmPlayerCache();

      // 2. Fetch rosters and league users in parallel
      const [rosters, leagueUsers] = await Promise.all([
        api.getRosters(lg.league_id),
        api.getLeagueUsers(lg.league_id),
      ]);

      // Build username map
      const usernameMap = {};
      for (const u of (leagueUsers || [])) {
        usernameMap[u.user_id] = u.display_name || u.username || u.user_id;
      }

      // 3. Find user's roster
      const userRoster = (rosters || []).find(r => r.owner_id === user.user_id);
      if (!userRoster) {
        Alert.alert('Error', 'Could not find your roster in this league.');
        setSelectedIdx(null);
        return;
      }

      const userPlayerIds = (userRoster.players || []).filter(Boolean);
      const opponentRosters = (rosters || [])
        .filter(r => r.owner_id && r.owner_id !== user.user_id)
        .map(r => ({
          user_id: r.owner_id,
          username: usernameMap[r.owner_id] || `Team ${r.roster_id}`,
          player_ids: (r.players || []).filter(Boolean),
        }))
        .filter(r => r.player_ids.length > 0);

      // 4. Init session
      const result = await api.initSession({
        user_id: user.user_id,
        display_name: user.display_name || '',
        username: user.display_name || '',
        avatar: user.avatar_id || null,
        league_id: lg.league_id,
        league_name: lg.name || 'Unnamed League',
        user_player_ids: userPlayerIds,
        opponent_rosters: opponentRosters,
      });

      if (!result || !result.ok) {
        Alert.alert('Error', 'Failed to initialise session.');
        setSelectedIdx(null);
        return;
      }

      // 5. Save and navigate
      setLeague({ league_id: lg.league_id, league_name: lg.name || 'Unnamed League' });
      navigation.replace('Main');
    } catch (e) {
      Alert.alert('Error', e.message || 'Something went wrong.');
      setSelectedIdx(null);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.card}>
        <View style={styles.header}>
          <Text style={styles.title}>Choose a League</Text>
          <Text style={styles.subtitle}>
            Leagues for {user?.display_name || 'you'}
          </Text>
        </View>

        {loading ? (
          <ActivityIndicator color={colors.accent} style={{ marginTop: 40 }} />
        ) : error ? (
          <Text style={styles.errorText}>{error}</Text>
        ) : (
          <ScrollView style={styles.list} showsVerticalScrollIndicator={false}>
            {leagues.map((lg, i) => (
              <TouchableOpacity
                key={lg.league_id}
                style={[styles.item, selectedIdx === i && styles.itemLoading]}
                onPress={() => selectLeague(i)}
                disabled={selectedIdx !== null}
                activeOpacity={0.7}
              >
                <View style={styles.itemIcon}>
                  <Text style={{ fontSize: 20 }}>🏈</Text>
                </View>
                <View style={styles.itemInfo}>
                  <Text style={styles.itemName}>{lg.name || 'Unnamed League'}</Text>
                  <Text style={styles.itemMeta}>
                    {lg.total_rosters || '?'} teams · {lg.scoring_settings?.rec ? 'PPR' : 'Standard'}
                  </Text>
                </View>
                {selectedIdx === i ? (
                  <ActivityIndicator size="small" color={colors.accent} />
                ) : (
                  <Text style={styles.itemArrow}>›</Text>
                )}
              </TouchableOpacity>
            ))}
          </ScrollView>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.xl,
  },
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: borderRadius.xl,
    padding: 28,
    width: '100%',
    maxWidth: 480,
    maxHeight: '80%',
    gap: spacing.xl,
  },
  header: { gap: 6 },
  title: { fontSize: fontSize.lg, fontWeight: '700', color: colors.text },
  subtitle: { fontSize: fontSize.sm, color: colors.muted },
  list: { flex: 1 },
  item: {
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: borderRadius.md,
    padding: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    marginBottom: 10,
  },
  itemLoading: { opacity: 0.5 },
  itemIcon: {
    width: 40,
    height: 40,
    borderRadius: borderRadius.sm,
    backgroundColor: 'rgba(79,124,255,0.15)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  itemInfo: { flex: 1 },
  itemName: { fontSize: fontSize.md, fontWeight: '600', color: colors.text },
  itemMeta: { fontSize: fontSize.sm, color: colors.muted, marginTop: 2 },
  itemArrow: { fontSize: 24, color: colors.muted },
  errorText: { fontSize: fontSize.md, color: colors.muted, textAlign: 'center', marginTop: 20 },
});
