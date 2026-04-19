import React from 'react';
import { Text, Pressable } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { colors } from '../theme/colors';
import PlaceholderScreen from '../screens/PlaceholderScreen';
import RankScreen from '../screens/RankScreen';
import TiersScreen from '../screens/TiersScreen';
import TradesScreen from '../screens/TradesScreen';
import MatchesScreen from '../screens/MatchesScreen';

// Tab definitions. Rank is a nested native-stack so Trios (default) can
// push to Tiers without losing the tab-bar. Trades/Matches/League follow
// as plain screens until Phase 4.
const Tab = createBottomTabNavigator();
const RankStack = createNativeStackNavigator();

function RankStackNav() {
  return (
    <RankStack.Navigator screenOptions={{ headerShown: false }}>
      <RankStack.Screen name="Trios" component={RankScreenWithTiersLink} />
      <RankStack.Screen
        name="Tiers"
        component={TiersScreen}
        options={{ headerShown: true, title: 'Tiers', headerStyle: { backgroundColor: colors.bg }, headerTintColor: colors.text }}
      />
    </RankStack.Navigator>
  );
}

// Wrap RankScreen in a lightweight adapter that adds a small "📋 Tiers"
// button in the top-right corner. Kept inline here instead of editing
// RankScreen so the Trios screen stays focused on its own flow.
function RankScreenWithTiersLink({ navigation }: any) {
  return (
    <>
      <Pressable
        onPress={() => navigation.navigate('Tiers')}
        style={{
          position: 'absolute',
          right: 12,
          top: 48,
          zIndex: 30,
          backgroundColor: colors.surface,
          paddingHorizontal: 12,
          paddingVertical: 6,
          borderRadius: 999,
          borderWidth: 1,
          borderColor: colors.border,
        }}
        hitSlop={10}
      >
        <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>
          📋 Tiers
        </Text>
      </Pressable>
      <RankScreen />
    </>
  );
}

function TradesTab() {
  return <TradesScreen />;
}
function MatchesTab() {
  return <MatchesScreen />;
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
        component={RankStackNav}
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
