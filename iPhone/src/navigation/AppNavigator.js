import React, { useEffect, useState } from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { Text, View, TouchableOpacity, ActivityIndicator, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useApp } from '../context/AppContext';
import { storage } from '../utils/storage';
import { api } from '../services/api';

import LoginScreen from '../screens/LoginScreen';
import LeagueSelectScreen from '../screens/LeagueSelectScreen';
import RankPlayersScreen from '../screens/RankPlayersScreen';
import TradeFinderScreen from '../screens/TradeFinderScreen';

const colors = {
  bg: '#0f1117',
  surface: '#1a1d27',
  border: '#2a2d3a',
  text: '#e8eaf0',
  muted: '#7a7f96',
  accent: '#4f7cff',
};

const Stack = createNativeStackNavigator();

// ── Custom tab bar (no @react-navigation/bottom-tabs, no vector icons) ──
function MainTabs() {
  const [activeTab, setActiveTab] = useState('rank');
  const insets = useSafeAreaInsets();

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      {/* Screen content */}
      <View style={{ flex: 1 }}>
        {activeTab === 'rank' ? <RankPlayersScreen /> : <TradeFinderScreen onSwitchToRank={() => setActiveTab('rank')} />}
      </View>

      {/* Tab bar */}
      <View style={[tabStyles.bar, { paddingBottom: insets.bottom || 16 }]}>
        <TouchableOpacity
          style={tabStyles.tab}
          onPress={() => setActiveTab('rank')}
          activeOpacity={0.7}
        >
          <Text style={tabStyles.emoji}>📊</Text>
          <Text style={[tabStyles.label, activeTab === 'rank' && tabStyles.labelActive]}>
            Rank
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={tabStyles.tab}
          onPress={() => setActiveTab('trades')}
          activeOpacity={0.7}
        >
          <Text style={tabStyles.emoji}>⚡</Text>
          <Text style={[tabStyles.label, activeTab === 'trades' && tabStyles.labelActive]}>
            Trades
          </Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const tabStyles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: 8,
  },
  tab: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
  },
  emoji: { fontSize: 20 },
  label: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.muted,
  },
  labelActive: {
    color: colors.accent,
  },
});

// ── Loading screen ──
function LoadingScreen() {
  return (
    <View style={loadStyles.container}>
      <Text style={loadStyles.logo}>
        Dynasty <Text style={loadStyles.accent}>Trade Finder</Text>
      </Text>
      <ActivityIndicator color={colors.accent} size="large" style={{ marginTop: 20 }} />
    </View>
  );
}

const loadStyles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg, justifyContent: 'center', alignItems: 'center' },
  logo: { fontSize: 24, fontWeight: '700', color: colors.text },
  accent: { color: colors.accent },
});

// ── Main navigator ──
export default function AppNavigator() {
  const { user, league, setUser, setLeague, setLeagues, setInitialized } = useApp();
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    boot();
  }, []);

  const boot = async () => {
    try {
      const savedUser = await storage.getUser();
      const savedLeague = await storage.getLeague();

      if (savedUser) {
        setUser(savedUser);

        if (savedLeague) {
          setLeague(savedLeague);

          try {
            await api.warmPlayerCache();
            const [rosters, leagueUsers] = await Promise.all([
              api.getRosters(savedLeague.league_id),
              api.getLeagueUsers(savedLeague.league_id),
            ]);

            const usernameMap = {};
            for (const u of (leagueUsers || [])) {
              usernameMap[u.user_id] = u.display_name || u.username || u.user_id;
            }

            const userRoster = (rosters || []).find(r => r.owner_id === savedUser.user_id);
            if (userRoster) {
              const userPlayerIds = (userRoster.players || []).filter(Boolean);
              const opponentRosters = (rosters || [])
                .filter(r => r.owner_id && r.owner_id !== savedUser.user_id)
                .map(r => ({
                  user_id: r.owner_id,
                  username: usernameMap[r.owner_id] || `Team ${r.roster_id}`,
                  player_ids: (r.players || []).filter(Boolean),
                }))
                .filter(r => r.player_ids.length > 0);

              await api.initSession({
                user_id: savedUser.user_id,
                display_name: savedUser.display_name || '',
                username: savedUser.display_name || '',
                avatar: savedUser.avatar_id || null,
                league_id: savedLeague.league_id,
                league_name: savedLeague.league_name,
                user_player_ids: userPlayerIds,
                opponent_rosters: opponentRosters,
              });
            }

            try {
              const leagues = await api.getLeagues(savedUser.user_id);
              if (leagues?.length) setLeagues(leagues);
            } catch {}
          } catch {
            // Session restore failed — still show the app
          }
        }
      }
    } catch {}
    setInitialized();
    setBooting(false);
  };

  if (booting) return <LoadingScreen />;

  let initialRoute = 'Login';
  if (user && league) initialRoute = 'Main';
  else if (user) initialRoute = 'LeagueSelect';

  return (
    <Stack.Navigator
      initialRouteName={initialRoute}
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: colors.bg },
        animation: 'fade',
      }}
    >
      <Stack.Screen name="Login" component={LoginScreen} />
      <Stack.Screen name="LeagueSelect" component={LeagueSelectScreen} />
      <Stack.Screen name="Main" component={MainTabs} />
    </Stack.Navigator>
  );
}
