import React from 'react';
import { Text } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { colors } from '../theme/colors';
import PlaceholderScreen from '../screens/PlaceholderScreen';
import RankScreen from '../screens/RankScreen';

// Tab definitions kept thin; real screens swap in as Phase 2-4 land.
const Tab = createBottomTabNavigator();

function RankTab() {
  return <RankScreen />;
}
function TradesTab() {
  return <PlaceholderScreen title="Find a Trade" note="Phase 4." />;
}
function MatchesTab() {
  return <PlaceholderScreen title="Matches" note="Phase 4." />;
}
function LeagueTab() {
  return (
    <PlaceholderScreen
      title="League"
      note="League overview, leaguemate list, and invite sheet come post-v1."
    />
  );
}

// Simple text-emoji icon renderer — gets replaced with react-native-vector-icons
// or a custom SVG set in Phase 6 when the real design assets drop.
const tabIcon = (emoji: string) =>
  ({ focused }: { focused: boolean }) =>
    <Text style={{ fontSize: 22, opacity: focused ? 1 : 0.55 }}>{emoji}</Text>;

export default function TabNav() {
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          borderTopWidth: 1,
        },
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: colors.muted,
        tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
      }}
    >
      <Tab.Screen
        name="Rank"
        component={RankTab}
        options={{ tabBarIcon: tabIcon('🏈') }}
      />
      <Tab.Screen
        name="Trades"
        component={TradesTab}
        options={{ tabBarIcon: tabIcon('⚡') }}
      />
      <Tab.Screen
        name="Matches"
        component={MatchesTab}
        options={{ tabBarIcon: tabIcon('🤝') }}
      />
      <Tab.Screen
        name="League"
        component={LeagueTab}
        options={{ tabBarIcon: tabIcon('🏆') }}
      />
    </Tab.Navigator>
  );
}
