import React, { useState } from 'react';
import { Text, Pressable, View, StyleSheet, Modal } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { NavigationContainerRefContext, CommonActions } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import { getNextTrio, getRankings, getTiersStatus } from '../api/rankings';
import { getLikedTrades, getAllMatches } from '../api/trades';
import { useSession } from '../state/useSession';
import RankScreen from '../screens/RankScreen';
import TiersScreen from '../screens/TiersScreen';
import ManualRanksScreen from '../screens/ManualRanksScreen';
import TrendsScreen from '../screens/TrendsScreen';
import TradesScreen from '../screens/TradesScreen';
import PortfolioScreen from '../screens/PortfolioScreen';
import MatchesScreen from '../screens/MatchesScreen';
import LeagueScreen from '../screens/LeagueScreen';
import TopBar from '../components/TopBar';

// Tab definitions. The "Rank" tab fans out into 4 sub-screens — Trios swipe,
// Tiers (drag-to-bin), Overall Ranks (the editable drag/tap board), and
// Trends (movers + consensus gap). Tapping the tab opens an action sheet so
// all four are one tap away (was: tiny pill in corner).
const Tab = createBottomTabNavigator();
const RankStack = createNativeStackNavigator();
// B3 — Trades tab becomes a small stack so Portfolio is reachable as a
// sub-route. TradesScreen renders its own in-screen pill that pushes
// Portfolio; the bottom-nav still surfaces just four tabs.
const TradesStack = createNativeStackNavigator();

export type RankRoute = 'Trios' | 'Tiers' | 'ManualRanks' | 'Trends';
export type TradesRoute = 'TradesHome' | 'Portfolio';

// #51/#52 — Rank sub-screens (Tiers / Overall Ranks / Trends) are siblings
// reached from the Rank menu, not a linear drill-down. The native back button
// was unreliable: depending on stack state it greyed out, dead-clicked, or
// (when it worked) always landed on Trios rather than where the user came
// from. Replace it with an always-enabled header-left control that resolves
// to a defined destination every time: go back if there's history, otherwise
// fall to Trios (the stack root / stable home). Never greyed, never dead.
function RankHeaderBack({ navigation }: { navigation: any }) {
  return (
    <Pressable
      onPress={() =>
        navigation.canGoBack() ? navigation.goBack() : navigation.navigate('Trios')
      }
      hitSlop={spacing.md}
      style={({ pressed }) => [styles.headerBack, pressed && { opacity: 0.6 }]}
    >
      <Text style={styles.headerBackText}>‹ Back</Text>
    </Pressable>
  );
}

// Shared options for the three pushed Rank sub-screens: dark header + the
// custom always-on back control. Built from the per-screen options callback so
// the live `navigation` object for that screen is captured — the native-stack
// `headerLeft` render prop itself does NOT receive `navigation`, so closing
// over it here is what makes the control act on the right screen.
const rankSubScreenOptions = (title: string) =>
  ({ navigation }: { navigation: any }) => ({
    headerShown: true,
    title,
    headerStyle: { backgroundColor: colors.bg },
    headerTintColor: colors.text,
    headerLeft: () => <RankHeaderBack navigation={navigation} />,
  });

function RankStackNav() {
  return (
    <RankStack.Navigator screenOptions={{ headerShown: false }}>
      <RankStack.Screen name="Trios" component={RankScreen} />
      <RankStack.Screen
        name="Tiers"
        component={TiersScreen}
        options={rankSubScreenOptions('Tiers')}
      />
      <RankStack.Screen
        name="ManualRanks"
        component={ManualRanksScreen}
        options={rankSubScreenOptions('Overall Ranks')}
      />
      <RankStack.Screen
        name="Trends"
        component={TrendsScreen}
        options={rankSubScreenOptions('Trends')}
      />
    </RankStack.Navigator>
  );
}

function TradesStackNav() {
  return (
    <TradesStack.Navigator screenOptions={{ headerShown: false }}>
      <TradesStack.Screen name="TradesHome" component={TradesScreen} />
      <TradesStack.Screen
        name="Portfolio"
        component={PortfolioScreen}
        options={{
          headerShown: true,
          title: 'Portfolio',
          headerStyle: { backgroundColor: colors.bg },
          headerTintColor: colors.text,
        }}
      />
    </TradesStack.Navigator>
  );
}

// Simple text-emoji icon renderer — gets replaced with react-native-vector-icons
// or a custom SVG set in Phase 6 when the real design assets drop.
const tabIcon = (emoji: string) =>
  ({ focused }: { focused: boolean }) =>
    <Text style={{ fontSize: 22, opacity: focused ? 1 : 0.55 }}>{emoji}</Text>;

// Rank tab icon — same emoji glyph as the others, but with a small chevron
// (▾) beside it to signal that tapping fans out a MENU of rank modes (Trios,
// Tiers, Overall Ranks, Trends) rather than opening a single screen. The
// chevron inherits the tab's active/inactive tint so it stays consistent with
// the rest of the bar. Laid out in a tight row so nothing clips on the
// fixed-height tab bar.
const rankTabIcon = (emoji: string) =>
  ({ focused, color }: { focused: boolean; color: string }) =>
    (
      <View style={styles.rankIconWrap}>
        <Text style={{ fontSize: 22, opacity: focused ? 1 : 0.55 }}>{emoji}</Text>
        <Text style={[styles.rankIconChevron, { color, opacity: focused ? 1 : 0.55 }]}>▾</Text>
      </View>
    );

export default function TabNav() {
  const [rankMenuOpen, setRankMenuOpen] = useState(false);
  const queryClient = useQueryClient();

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
          // #49: FB-28 added a ▾ to the label, but the icon already renders a
          // chevron (PR #79) — the two cues stacked. Keep the icon chevron
          // (the conventional "fans out" signal) and drop the label arrow.
          options={{ tabBarIcon: rankTabIcon('🏈'), tabBarLabel: 'Rank' }}
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
          component={TradesStackNav}
          options={{ tabBarIcon: tabIcon('⚡') }}
          listeners={() => ({
            // Warm the liked-trades cache during the tab transition so
            // TradesScreen's `useQuery(['liked-trades', leagueId])` adopts
            // the in-flight request on mount. Don't preventDefault — the
            // tab should still navigate normally. Read leagueId from the
            // session store (same source TradesScreen uses) and skip the
            // prefetch when no league is active (the screen's query is
            // `enabled: !!leagueId`).
            tabPress: () => {
              const leagueId = useSession.getState().league?.league_id ?? null;
              if (!leagueId) return;
              void queryClient.prefetchQuery({
                queryKey: ['liked-trades', leagueId],
                queryFn: getLikedTrades,
                staleTime: 30_000,
              });
            },
          })}
        />
        <Tab.Screen
          name="Matches"
          component={MatchesScreen}
          options={{ tabBarIcon: tabIcon('🤝') }}
          listeners={() => ({
            // Warm the cross-league matches cache during the tab transition
            // so MatchesScreen's `useQuery(['matches', 'all'])` adopts the
            // in-flight request on mount. Fire-and-forget; errors surface on
            // the screen's own query.
            tabPress: () => {
              void queryClient.prefetchQuery({
                queryKey: ['matches', 'all'],
                queryFn: getAllMatches,
                staleTime: 15_000,
              });
            },
          })}
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
// Bottom-sheet style picker for the four Rank sub-screens. Tapping a row
// dispatches a navigation action that focuses the Rank tab AND pushes the
// chosen sub-route inside the RankStack. Driven from TabNav so we can use
// a single root-nav handle (the Rank stack's child screens can't reach the
// tab navigator's parent on their own).
function RankMenu({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  // We need the root navigation (the Tab navigator), not a screen-local one.
  // Grabbing it through context lets this stay outside any specific Screen.
  const navContext = React.useContext(NavigationContainerRefContext as any) as any;
  const queryClient = useQueryClient();

  const go = (screen: RankRoute) => {
    // Prefetch the destination's payload during the modal-close + tab-
    // transition animation (~250–400 ms of otherwise-dead time). Each Rank
    // sub-screen's `useQuery` adopts the in-flight request when it mounts,
    // so the user gets a free head start on the round-trip. All calls are
    // fire-and-forget — prefetchQuery surfaces errors via the query's own
    // error state once the destination screen reads it, so we swallow here.
    // NOTE: keys are the destinations' CURRENT flat shapes; key-scoping
    // (format/leagueId) is a separate Wave-2 initiative (INIT-07).
    if (screen === 'Trios') {
      void queryClient.prefetchQuery({
        queryKey: ['trio', 'QB'],
        queryFn: () => getNextTrio('QB'),
        staleTime: 0,
      });
    } else if (screen === 'Tiers') {
      // TiersScreen opens on position 'QB' (TiersScreen.tsx:65) and also
      // pulls the per-position saved-state map.
      void queryClient.prefetchQuery({
        queryKey: ['rankings', 'QB'],
        queryFn: () => getRankings('QB'),
        staleTime: 30_000,
      });
      void queryClient.prefetchQuery({
        queryKey: ['tiers-status'],
        queryFn: getTiersStatus,
        staleTime: 60_000,
      });
    } else if (screen === 'ManualRanks') {
      // The Overall Ranks screen (ManualRanksScreen) pulls the full
      // unfiltered list once and filters client-side (ManualRanksScreen.tsx:92).
      void queryClient.prefetchQuery({
        queryKey: ['rankings', 'all'],
        queryFn: () => getRankings(null),
        staleTime: 30_000,
      });
    }
    // Trends is intentionally not prefetched: its queries take runtime args
    // (window_days/top_n, plus a league_id for the consensus-gap call) and
    // don't match a single obvious flat key — deferred per the LLD.
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
    { route: 'ManualRanks',   emoji: '🏅', label: 'Overall Ranks', sub: 'Drag rows or tap a rank number to re-order your board by hand' },
    { route: 'Trends',        emoji: '📈', label: 'Trends',        sub: 'See your biggest movers and how you differ from consensus' },
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
  // Rank tab icon: emoji + menu chevron in a tight row. The negative left
  // margin pulls the chevron snug to the glyph; nothing extends past the
  // tab's icon box so there's no clipping on the bottom bar.
  rankIconWrap: { flexDirection: 'row', alignItems: 'center' },
  // FB-28: bumped from 11 — the smaller chevron read as decoration.
  rankIconChevron: { fontSize: 14, fontWeight: '900', marginLeft: 2, marginTop: 2 },

  // #51/#52: always-on header back control for Rank sub-screens. Padded for a
  // comfortable tap target; tinted with the accent so it reads as actionable
  // (never the greyed/disabled native arrow).
  headerBack: { paddingVertical: spacing.xs, paddingRight: spacing.md },
  headerBackText: { color: colors.accent, fontSize: fontSize.base, fontWeight: '700' },

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
