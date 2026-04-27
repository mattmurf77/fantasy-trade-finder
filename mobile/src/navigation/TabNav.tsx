import React, { useState } from 'react';
import { Text, Pressable, View, StyleSheet, Modal } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { NavigationContainerRefContext, CommonActions } from '@react-navigation/native';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import RankScreen from '../screens/RankScreen';
import TiersScreen from '../screens/TiersScreen';
import OverallRanksScreen from '../screens/OverallRanksScreen';
import TradesScreen from '../screens/TradesScreen';
import MatchesScreen from '../screens/MatchesScreen';
import LeagueScreen from '../screens/LeagueScreen';
import TopBar from '../components/TopBar';

// Tab definitions. The "Rank" tab fans out into 3 sub-screens — Trios swipe,
// Tiers (drag-to-bin), and Overall Ranks (flat list). Tapping the tab opens
// an action sheet so all three are one tap away (was: tiny pill in corner).
const Tab = createBottomTabNavigator();
const RankStack = createNativeStackNavigator();

export type RankRoute = 'Trios' | 'Tiers' | 'OverallRanks';

function RankStackNav() {
  return (
    <RankStack.Navigator screenOptions={{ headerShown: false }}>
      <RankStack.Screen name="Trios" component={RankScreen} />
      <RankStack.Screen
        name="Tiers"
        component={TiersScreen}
        options={{ headerShown: true, title: 'Tiers', headerStyle: { backgroundColor: colors.bg }, headerTintColor: colors.text }}
      />
      <RankStack.Screen
        name="OverallRanks"
        component={OverallRanksScreen}
        options={{ headerShown: true, title: 'Overall Ranks', headerStyle: { backgroundColor: colors.bg }, headerTintColor: colors.text }}
      />
    </RankStack.Navigator>
  );
}

// Simple text-emoji icon renderer — gets replaced with react-native-vector-icons
// or a custom SVG set in Phase 6 when the real design assets drop.
const tabIcon = (emoji: string) =>
  ({ focused }: { focused: boolean }) =>
    <Text style={{ fontSize: 22, opacity: focused ? 1 : 0.55 }}>{emoji}</Text>;

export default function TabNav() {
  const [rankMenuOpen, setRankMenuOpen] = useState(false);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      {/* Global top bar — sits above the tab navigator on every authed
          screen, owns the top safe-area inset, and renders the floating
          notifications bell on the right. Screens below intentionally
          don't include `top` in their SafeAreaView edges so the system
          inset isn't double-counted. */}
      <TopBar />
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
          listeners={() => ({
            // Intercept the tap on the Rank tab — open the action sheet
            // instead of jumping into a sub-screen. We still keep the tab
            // active visually so the user knows where they are.
            tabPress: (e) => {
              e.preventDefault();
              setRankMenuOpen(true);
            },
          })}
        />
        <Tab.Screen
          name="Trades"
          component={TradesScreen}
          options={{ tabBarIcon: tabIcon('⚡') }}
        />
        <Tab.Screen
          name="Matches"
          component={MatchesScreen}
          options={{ tabBarIcon: tabIcon('🤝') }}
        />
        <Tab.Screen
          name="League"
          component={LeagueScreen}
          options={{ tabBarIcon: tabIcon('🏆') }}
        />
      </Tab.Navigator>

      <RankMenu
        visible={rankMenuOpen}
        onClose={() => setRankMenuOpen(false)}
      />
    </View>
  );
}

// ── Rank action sheet ────────────────────────────────────────────────
// Bottom-sheet style picker for the three Rank sub-screens. Tapping a row
// dispatches a navigation action that focuses the Rank tab AND pushes the
// chosen sub-route inside the RankStack. Driven from TabNav so we can use
// a single root-nav handle (the Rank stack's child screens can't reach the
// tab navigator's parent on their own).
function RankMenu({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  // We need the root navigation (the Tab navigator), not a screen-local one.
  // Grabbing it through context lets this stay outside any specific Screen.
  const navContext = React.useContext(NavigationContainerRefContext as any) as any;

  const go = (screen: RankRoute) => {
    onClose();
    if (!navContext) return;
    navContext.dispatch(
      CommonActions.navigate({
        name: 'Rank',
        params: { screen },
      }),
    );
  };

  const items: { route: RankRoute; emoji: string; label: string; sub: string }[] = [
    { route: 'Trios',         emoji: '🏈', label: 'Trios',         sub: '3-at-a-time swipe ranking' },
    { route: 'Tiers',         emoji: '📋', label: 'Tiers',         sub: 'Drag players into Elite / Starter / Solid / Depth / Bench' },
    { route: 'OverallRanks',  emoji: '🏅', label: 'Overall Ranks', sub: 'Full ELO-sorted list of every player you\'ve ranked' },
  ];

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} />
      <View style={styles.sheet}>
        <View style={styles.handle} />
        <Text style={styles.sheetTitle}>Rank</Text>
        <Text style={styles.sheetSub}>Pick how you want to rank players.</Text>
        {items.map((it) => (
          <Pressable
            key={it.route}
            onPress={() => go(it.route)}
            style={({ pressed }) => [
              styles.item,
              pressed && { opacity: 0.7 },
            ]}
          >
            <Text style={styles.itemEmoji}>{it.emoji}</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.itemLabel}>{it.label}</Text>
              <Text style={styles.itemSub}>{it.sub}</Text>
            </View>
            <Text style={styles.itemChevron}>›</Text>
          </Pressable>
        ))}
        <Pressable onPress={onClose} style={({ pressed }) => [styles.cancel, pressed && { opacity: 0.7 }]}>
          <Text style={styles.cancelText}>Cancel</Text>
        </Pressable>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.55)' },
  sheet: {
    position: 'absolute',
    left: 0, right: 0, bottom: 0,
    backgroundColor: colors.bg,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
    gap: spacing.sm,
  },
  handle: {
    alignSelf: 'center',
    width: 44,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.border,
    marginBottom: spacing.sm,
  },
  sheetTitle: { color: colors.text, fontSize: fontSize.xl, fontWeight: '800' },
  sheetSub: { color: colors.muted, fontSize: fontSize.sm, marginBottom: spacing.sm },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.lg,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  itemEmoji: { fontSize: 26 },
  itemLabel: { color: colors.text, fontSize: fontSize.base, fontWeight: '800' },
  itemSub: { color: colors.muted, fontSize: fontSize.xs, marginTop: 2, lineHeight: 18 },
  itemChevron: { color: colors.muted, fontSize: 26 },
  cancel: {
    marginTop: spacing.md,
    padding: spacing.md,
    alignItems: 'center',
  },
  cancelText: { color: colors.muted, fontWeight: '700', fontSize: fontSize.sm },
});
