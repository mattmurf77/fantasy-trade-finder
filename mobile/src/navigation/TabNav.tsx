import React, { useState } from 'react';
import { Text, Pressable, View, StyleSheet, Modal } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { NavigationContainerRefContext, CommonActions } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import { ink, chalk, ice, flare, space, radii, type, fonts, shadowSheet, scrim } from '../theme/chalkline';
import { Icon, Button, type IconName } from '../components/chalkline';
import { getNextTrio, getRankings, getTiersStatus } from '../api/rankings';
import { getLikedTrades, getAllMatches } from '../api/trades';
import { useSession } from '../state/useSession';
import RankScreen from '../screens/RankScreen';
import RankHomeScreen from '../screens/RankHomeScreen';
import PickAnchorScreen from '../screens/PickAnchorScreen';
import TiersScreen from '../screens/TiersScreen';
import QuickSetTiersScreen from '../screens/QuickSetTiersScreen';
import ManualRanksScreen from '../screens/ManualRanksScreen';
import TrendsScreen from '../screens/TrendsScreen';
import TradesScreen from '../screens/TradesScreen';
import PortfolioScreen from '../screens/PortfolioScreen';
import TradeCalculatorScreen from '../screens/TradeCalculatorScreen';
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

export type RankRoute =
  | 'RankHome'
  | 'Trios'
  | 'Anchors'
  | 'Tiers'
  | 'QuickSetTiers'
  | 'ManualRanks'
  | 'Trends';
export type TradesRoute = 'TradesHome' | 'Portfolio' | 'TradeCalculator';

// #51/#52 — Rank sub-screens (Tiers / Overall Ranks / Trends) are siblings
// reached from the Rank menu, not a linear drill-down. The native back button
// was unreliable: depending on stack state it greyed out, dead-clicked, or
// (when it worked) always landed on Trios rather than where the user came
// from. Replace it with an always-enabled header-left control that resolves
// to a defined destination every time: go back if there's history, otherwise
// fall to the stack's stable home (`fallback`). Never greyed, never dead.
// FB #79 generalized this beyond Rank: the Trades stack's Calculator screen
// hit the same dead native back, so the fallback route is now a prop.
function HeaderBack({ navigation, fallback }: { navigation: any; fallback: string }) {
  return (
    <Pressable
      onPress={() =>
        navigation.canGoBack() ? navigation.goBack() : navigation.navigate(fallback)
      }
      hitSlop={space.md}
      style={({ pressed }) => [styles.headerBack, pressed && { opacity: 0.6 }]}
    >
      <Icon name="chevron-left" size={16} color={chalk.base} />
      <Text style={styles.headerBackText}>Back</Text>
    </Pressable>
  );
}

// Chalkline stack-header title — Barlow Condensed caps on the ink-0 bar.
// Native-stack headerTitleStyle can't express letterSpacing/textTransform,
// so we render the title ourselves.
function HeaderTitle({ children }: { children: string }) {
  return (
    <Text numberOfLines={1} style={styles.headerTitle}>
      {children}
    </Text>
  );
}

// Shared Chalkline header options for pushed sub-screens: ink-0 bar, chalk
// tint, condensed-caps title.
const chalklineHeader = (title: string) => ({
  headerShown: true,
  title,
  headerTitle: () => <HeaderTitle>{title}</HeaderTitle>,
  headerStyle: { backgroundColor: ink.ink0 },
  headerTintColor: chalk.base,
});

// Shared options for pushed sub-screens: Chalkline header + the custom
// always-on back control falling back to `fallback` (the stack's home route).
// Built from the per-screen options callback so the live `navigation` object
// for that screen is captured — the native-stack `headerLeft` render prop
// itself does NOT receive `navigation`, so closing over it here is what makes
// the control act on the right screen.
const subScreenOptions = (title: string, fallback: string) =>
  ({ navigation }: { navigation: any }) => ({
    ...chalklineHeader(title),
    headerLeft: () => <HeaderBack navigation={navigation} fallback={fallback} />,
  });

// Where the Rank stack opens at launch, per the saved preference
// (useSession.rankingMethodPref). Null pref = never chosen → the
// Build-your-board chooser. initialRouteName is only honored on the
// navigator's FIRST mount, which is exactly the contract we want: a
// mid-session preference change (Settings slider) applies next launch,
// while the chooser itself routes immediately via navigation.replace.
const PREF_ROUTE: Record<string, RankRoute> = {
  quickset: 'QuickSetTiers',
  trio:     'Trios',
  anchor:   'Anchors',
  tiers:    'Tiers',
  manual:   'ManualRanks',
};

function RankStackNav() {
  const pref = useSession((s) => s.rankingMethodPref);
  const initial: RankRoute = (pref && PREF_ROUTE[pref]) || 'RankHome';
  return (
    <RankStack.Navigator
      initialRouteName={initial}
      screenOptions={{ headerShown: false }}
    >
      <RankStack.Screen name="RankHome" component={RankHomeScreen} />
      <RankStack.Screen name="Trios" component={RankScreen} />
      <RankStack.Screen
        name="Anchors"
        component={PickAnchorScreen}
        options={subScreenOptions('Pick Anchors', 'Trios')}
      />
      <RankStack.Screen
        name="Tiers"
        component={TiersScreen}
        options={subScreenOptions('Tiers', 'Trios')}
      />
      {/* 1.5.4 #104 — guided tier quick-set walk. #119 promoted it to a
          first-class method: reachable from the Tiers header, the Rank menu,
          the rank-home chooser, and launch routing (rankingMethodPref
          'quickset'). Back fallback stays the Tiers board it writes to. */}
      <RankStack.Screen
        name="QuickSetTiers"
        component={QuickSetTiersScreen}
        options={subScreenOptions('Quick Set Tiers', 'Tiers')}
      />
      <RankStack.Screen
        name="ManualRanks"
        component={ManualRanksScreen}
        options={subScreenOptions('Overall Ranks', 'Trios')}
      />
      <RankStack.Screen
        name="Trends"
        component={TrendsScreen}
        options={subScreenOptions('Trends', 'Trios')}
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
        options={chalklineHeader('Portfolio')}
      />
      <TradesStack.Screen
        name="TradeCalculator"
        component={TradeCalculatorScreen}
        // FB #79 — the native back control here was unreliable (greyed/dead),
        // same failure #51/#52 fixed on the Rank sub-screens. Use the shared
        // always-on back control, falling back to the Trades home screen.
        options={subScreenOptions('Calculator', 'TradesHome')}
      />
    </TradesStack.Navigator>
  );
}

// Chalkline tab icons — stroke SVG set from src/components/chalkline. The
// navigator passes the active/inactive tint (ice / chalk-dim) as `color`.
const tabIcon = (name: IconName) =>
  ({ color }: { color: string }) =>
    <Icon name={name} size={22} color={color} />;

// Rank tab icon — same glyph treatment as the others, but with a small
// chevron beside it to signal that tapping fans out a MENU of rank modes
// (Trios, Tiers, Overall Ranks, Trends) rather than opening a single screen.
// The chevron inherits the tab's active/inactive tint so it stays consistent
// with the rest of the bar. Laid out in a tight row so nothing clips on the
// fixed-height tab bar.
const rankTabIcon = (name: IconName) =>
  ({ color }: { color: string }) =>
    (
      <View style={styles.rankIconWrap}>
        <Icon name={name} size={22} color={color} />
        <Icon name="chevron-down" size={12} color={color} />
      </View>
    );

export default function TabNav() {
  const [rankMenuOpen, setRankMenuOpen] = useState(false);
  const queryClient = useQueryClient();

  return (
    <View style={{ flex: 1, backgroundColor: ink.ink0 }}>
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
            backgroundColor: ink.ink0,
            borderTopColor: ink.line,
            borderTopWidth: 1,
          },
          tabBarActiveTintColor: ice.base,
          tabBarInactiveTintColor: chalk.dim,
          tabBarLabelStyle: { fontFamily: fonts.uiSemi, fontSize: 11 },
        }}
      >
        <Tab.Screen
          name="Rank"
          component={RankStackNav}
          // #49: FB-28 added a chevron to the label, but the icon already
          // renders one (PR #79) — the two cues stacked. Keep the icon chevron
          // (the conventional "fans out" signal) and drop the label arrow.
          options={{ tabBarIcon: rankTabIcon('rank'), tabBarLabel: 'Rank', tabBarButtonTestID: 'tab.rank' }}
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
          options={{ tabBarIcon: tabIcon('trade'), tabBarButtonTestID: 'tab.trades' }}
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
          options={{ tabBarIcon: tabIcon('match'), tabBarButtonTestID: 'tab.matches' }}
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
          options={{ tabBarIcon: tabIcon('crown'), tabBarButtonTestID: 'tab.league' }}
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
    } else if (screen === 'QuickSetTiers') {
      // #119 — QuickSetTiersScreen opens on position 'QB' and reads through
      // a format-scoped key (QuickSetTiersScreen.tsx:72), unlike TiersScreen's
      // flat key above.
      const fmt = useSession.getState().activeFormat;
      void queryClient.prefetchQuery({
        queryKey: ['rankings', fmt, 'QB'],
        queryFn: () => getRankings('QB'),
        staleTime: 30_000,
      });
    } else if (screen === 'Anchors') {
      // PickAnchorScreen snapshots the pool under its own format-scoped key
      // (staleTime: Infinity — the wizard queue must not reshuffle mid-run).
      const fmt = useSession.getState().activeFormat ?? '1qb_ppr';
      void queryClient.prefetchQuery({
        queryKey: ['anchor-pool', fmt],
        queryFn: () => getRankings(null),
        staleTime: Infinity,
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

  const items: { route: RankRoute; label: string; sub: string; testID: string; recommended?: boolean }[] = [
    // #119 — Quick set is a first-class method: lowest effort, recommended.
    { route: 'QuickSetTiers', label: 'Quick set',     sub: 'Tap players into pick-value tiers, one tier at a time — the fastest board', testID: 'rankmenu.quickset', recommended: true },
    { route: 'Trios',         label: 'Trios',         sub: '3-at-a-time swipe ranking', testID: 'rankmenu.trios' },
    { route: 'Anchors',       label: 'Pick Anchors',  sub: 'Say what each player is worth in draft picks — 4 1sts down to no value', testID: 'rankmenu.anchors' },
    { route: 'Tiers',         label: 'Tiers',         sub: 'Drag players into pick-value tiers (4+ 1sts down to Waivers)', testID: 'rankmenu.tiers' },
    { route: 'ManualRanks',   label: 'Overall Ranks', sub: 'Drag rows or tap a rank number to re-order your board by hand', testID: 'rankmenu.manual' },
    { route: 'Trends',        label: 'Trends',        sub: 'See your biggest movers and how you differ from consensus', testID: 'rankmenu.trends' },
  ];

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} />
      <View style={styles.sheet}>
        <View style={styles.handle} />
        <Text style={type.heading}>Rank</Text>
        <Text style={styles.sheetSub}>Pick how you want to rank players.</Text>
        {items.map((it) => (
          <Pressable
            key={it.route}
            testID={it.testID}
            onPress={() => go(it.route)}
            style={({ pressed }) => [
              styles.item,
              pressed && { backgroundColor: ink.ink3 },
            ]}
          >
            <View style={{ flex: 1 }}>
              <View style={styles.itemLabelRow}>
                <Text style={styles.itemLabel}>{it.label}</Text>
                {/* #119 — flare label = informational highlight (ADR-005),
                    same treatment as the rank-home chooser's tag. */}
                {it.recommended ? (
                  <Text style={styles.recommendedTag}>recommended</Text>
                ) : null}
              </View>
              <Text style={styles.itemSub}>{it.sub}</Text>
            </View>
            <Icon name="chevron-right" size={16} color={chalk.dim} />
          </Pressable>
        ))}
        <Button label="Cancel" variant="ghost" onPress={onClose} style={styles.cancel} />
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  // Rank tab icon: glyph + menu chevron in a tight row. Nothing extends past
  // the tab's icon box so there's no clipping on the bottom bar.
  rankIconWrap: { flexDirection: 'row', alignItems: 'center', gap: 2 },

  // #51/#52: always-on header back control for pushed sub-screens. Padded for a
  // comfortable tap target; chevron + label in chalk so it reads as actionable
  // (never the greyed/disabled native arrow).
  headerBack: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    paddingVertical: space.xs,
    paddingRight: space.md,
  },
  headerBackText: { color: chalk.base, fontFamily: fonts.uiSemi, fontSize: 14 },
  // type.heading scaled to fit the native header bar.
  headerTitle: {
    fontFamily: fonts.displaySemi,
    fontSize: 18,
    letterSpacing: 0.54,
    textTransform: 'uppercase',
    color: chalk.base,
  },

  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheet: {
    position: 'absolute',
    left: 0, right: 0, bottom: 0,
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    padding: space.lg,
    paddingBottom: space.xxl,
    gap: space.sm,
    ...shadowSheet,
  },
  handle: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    borderRadius: radii.xs,
    backgroundColor: ink.lineStrong,
    marginBottom: space.sm,
  },
  sheetSub: { ...type.bodySm, marginBottom: space.sm },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    padding: space.lg,
    borderRadius: radii.sm,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  itemLabel: type.title,
  itemLabelRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  // #119 — mirrors RankHomeScreen's recommended tag (flare, informational).
  recommendedTag: { ...type.label, color: flare.base },
  itemSub: { ...type.bodySm, marginTop: 2 },
  cancel: { marginTop: space.md },
});
