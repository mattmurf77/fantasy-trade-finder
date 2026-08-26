import React, { useState } from 'react';
import { Text, Pressable, View, StyleSheet, Modal } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { NavigationContainerRefContext, CommonActions, StackActions } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import { ink, chalk, ice, flare, space, radii, type, fonts, shadowSheet, scrim } from '../theme/chalkline';
import { Icon, Button, type IconName } from '../components/chalkline';
import { getNextTrio, getRankings, getTiersStatus } from '../api/rankings';
import { getLikedTrades, getAllMatches } from '../api/trades';
import { useSession } from '../state/useSession';
import { nextQuicksetPosition } from '../state/quicksetProgress';
import { onboardingEnabled, useFeatureFlags, useFlag } from '../state/useFeatureFlags';
import { requestScrollToTop } from './scrollToTop';
import { track } from '../api/events';
import { getOnboardingState } from '../state/useOnboardingState';
import {
  MORE_METHODS,
  PRIMARY_METHODS,
  type ChooserMethod,
} from './rankChooserModel';
import RankScreen from '../screens/RankScreen';
import RankHomeScreen from '../screens/RankHomeScreen';
import PickAnchorScreen from '../screens/PickAnchorScreen';
import TiersScreen from '../screens/TiersScreen';
import QuickSetTiersScreen from '../screens/QuickSetTiersScreen';
import QuickRankScreen from '../screens/QuickRankScreen';
import ManualRanksScreen from '../screens/ManualRanksScreen';
// rookie-draft M2 (operator decision O1-expanded) — the consolidated
// cross-position rookie ranking view. Same Elo space, same board, read
// through the scope view filter; entered from any rank page's scope control
// and from the rank-home chooser. Both entry points are flag-gated, so with
// `ranks.rookie_subset` off this route is unreachable in the UI.
import RookieRanksScreen from '../screens/RookieRanksScreen';
import TrendsScreen from '../screens/TrendsScreen';
import TradesScreen from '../screens/TradesScreen';
// #246 — TradeFinderHubScreen is unrouted (guided-first landing); the file
// stays in the tree pending a later cleanup pass, but nothing imports it.
import PortfolioScreen from '../screens/PortfolioScreen';
import TradeCalculatorScreen from '../screens/TradeCalculatorScreen';
import TeamReviewScreen from '../screens/TeamReviewScreen';
// Presentation v2 (flag `trades.presentation_v2`, docs/plans/
// trade-presentation-v2/scope.md). Both screens register UNCONDITIONALLY,
// per the house rule that a flag gates the ENTRY POINT, not the navigator
// entry — a registered-but-unreachable route costs nothing at render time
// and keeps a stale deep link landing on a real screen instead of 404ing.
// The entry point is the mode strip's "Today" chip, which exists only while
// the flag is on.
import TodaysTradeScreen from '../screens/TodaysTradeScreen';
import TradeBrowseAllScreen from '../screens/TradeBrowseAllScreen';
import MatchesScreen from '../screens/MatchesScreen';
// rookie-draft placement (operator decision 2026-08-06, option A′) — the
// SAME screen the root stack registers. Dual registration is deliberate:
// the root-stack route is what `app/league/draft-room` resolves to, so a
// deep link behaves identically whether or not the seasonal tab exists.
import DraftRoomScreen from '../screens/DraftRoomScreen';
import LeagueScreen from '../screens/LeagueScreen';
import LeagueSummaryScreen from '../screens/LeagueSummaryScreen';
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
// #181 — League tab becomes a small stack so the tab can LAND on the
// rankings view (LeagueSummaryScreen) with the classic league page
// (LeagueScreen) pushed as a sub-route from its "League home" entry row.
const LeagueStack = createNativeStackNavigator();

export type RankRoute =
  | 'RankHome'
  | 'Trios'
  | 'Anchors'
  | 'Tiers'
  | 'QuickSetTiers'
  | 'QuickRank'
  | 'ManualRanks'
  | 'RookieRanks'
  | 'Trends';
export type TradesRoute =
  | 'TradesHome'
  | 'TradeDeck'
  | 'Portfolio'
  | 'TradeCalculator'
  | 'TodaysTrade'
  | 'TradeBrowseAll';

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
      testID="stack.back-btn"
      accessibilityRole="button"
      accessibilityLabel="Back"
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

// ── PRD 01-02 (flag `ux.rank_tab_destination`) — the ONE rank exit ──────
// With the flag on, the Rank tab navigates instead of opening the mode
// menu, so every rank surface carries a "More ways to rank" header control.
//
// 2026-08-16 (operator): that control now navigates straight to the
// RankHome chooser ("Build your board") instead of opening the RankMenu
// sheet, and the back control is GONE from these surfaces. Both used to
// ship side by side and did the same job — Back fell back to RankHome and
// the sheet listed the same methods RankHome already shows — so a rank
// surface carried two controls for one destination while the chooser (the
// only place the import entry point lives) stayed a tap deeper than the
// sheet. One control, one destination, and the fuller page wins.
//
// Never-strand still holds (#162/#165): every flag-on rank surface reaches
// RankHome through this control, RankHome keeps its own back control to the
// preferred surface, and the iOS edge-swipe gesture is untouched. The
// RankMenu sheet itself stays mounted for the FLAG-OFF tab-press path.
function MoreWaysButton({ navigation }: { navigation: any }) {
  return (
    <Pressable
      testID="rank.more-ways"
      onPress={() => navigation.navigate('RankHome')}
      hitSlop={8}
    >
      {({ pressed }) => (
        <Text style={[styles.moreWaysLink, pressed && { color: chalk.base }]}>
          More ways to rank
        </Text>
      )}
    </Pressable>
  );
}

// Chalkline header + the More-ways control, and NO back control (flag-on
// rank surfaces). `headerBackVisible: false` is load-bearing on top of the
// null headerLeft: this is a NATIVE stack, so a pushed screen renders the
// platform chevron on its own unless the option says otherwise.
const rankSubScreenOptions = (title: string) =>
  ({ navigation }: { navigation: any }) => ({
    ...chalklineHeader(title),
    headerBackVisible: false,
    headerLeft: () => null,
    headerRight: () => <MoreWaysButton navigation={navigation} />,
  });

// #217 — QuickSetTiers doubles as the Rank tab's launch route (#122). At the
// stack ROOT there is no history to pop, so the always-on back control
// (#162/#165) could only fall through to RankHome — duplicating the "More
// ways to rank" header path (flag off: → RankHome directly; flag on: the
// RankMenu sheet). Hide it there, and ONLY there: pushed from anywhere
// (RankHome chooser, Tiers header, Rank menu), the route sits above index 0
// and the shared control renders as usual. The nav-loop fix's never-strand
// guarantee holds in both cases — root keeps the More-ways path, pushed
// keeps real back history.
function quickSetBackWhenPushed(navigation: any, route: any) {
  const routes = navigation.getState()?.routes ?? [];
  const selfIndex = routes.findIndex((r: any) => r.key === route.key);
  if (selfIndex === 0) return null;
  return <HeaderBack navigation={navigation} fallback="RankHome" />;
}

// PRD 01-05 / 01-02: pop a tab's nested stack to its root. Returns false
// when the tab has no nested history (caller falls back to scroll-to-top).
// Reads the partial nested state off the tab `route` — absent until the
// nested navigator has actually navigated.
function popNestedToTop(navigation: any, route: any): boolean {
  const nested = route?.state;
  if (!nested || !Array.isArray(nested.routes) || !nested.key) return false;
  const depth = typeof nested.index === 'number' ? nested.index + 1 : nested.routes.length;
  if (depth <= 1) return false;
  navigation.dispatch({ ...StackActions.popToTop(), target: nested.key });
  return true;
}

// Where the Rank stack opens at launch, per the saved preference
// (useSession.rankingMethodPref). Null pref = never chosen → Quick Set,
// the default method (#122). initialRouteName is only honored on the
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
  // #122 — Quick set is the DEFAULT ranking method: a user with no stored
  // preference lands in Quick Set directly, with "More ways to rank" in its
  // header carrying chooser discoverability (formerly gated behind
  // onboarding.rank_routing; item 9's Q1 ruling made the chooser
  // never-a-default, #122 ships it unconditionally). A stored pref always
  // wins — existing users' routing is untouched.
  //
  // #244 — the no-pref default is now completion-aware: with all four
  // positions quick-tiers complete (union of the persisted walk record +
  // the cached /api/tiers/status snapshot, both hydrated pre-mount — see
  // state/quicksetProgress.ts) the default lands on Trios instead; with
  // partial progress, Quick Set opens AT the next unset position in ladder
  // order (via initialParams below — every launch-routed or param-less
  // entry inherits it; explicit `position` params from the Tiers header /
  // guide prompts still win). Computed once at first mount, same contract
  // as the pref itself: initialRouteName/initialParams are only honored
  // then, so mid-session completion applies next launch — no reroute
  // flash. An explicit pref (incl. 'quickset') keeps its surface.
  const [launch] = useState(() => {
    const next = nextQuicksetPosition();
    const initialRoute: RankRoute =
      pref && PREF_ROUTE[pref]
        ? PREF_ROUTE[pref]
        : next == null
          ? 'Trios'
          : 'QuickSetTiers';
    return { initialRoute, quicksetStart: next ?? 'QB' };
  });
  const initial = launch.initialRoute;
  // PRD 01-02: with the flag on, every rank surface gets the "More ways to
  // rank" header control (opens the RankMenu sheet). Flag off keeps today's
  // options exactly (QuickSetTiers' RankHome link included).
  const rankDest = useFlag('ux.rank_tab_destination');
  return (
    <RankStack.Navigator
      initialRouteName={initial}
      screenOptions={{ headerShown: false }}
    >
      {/* S1B-05 bug fix (unflagged, noted): RankHome previously rendered
          headerless with only edge-swipe exit. Give it the shared
          sub-screen header so it has a visible back control, falling back
          to the preferred rank surface when it's the stack's first mount. */}
      <RankStack.Screen
        name="RankHome"
        component={RankHomeScreen}
        options={subScreenOptions('Rank', initial)}
      />
      {/* #162/#165 — every rank surface's back control falls back to
          RankHome (the rank-method chooser), not a sibling surface. The old
          fallbacks ('Trios' / 'Tiers') meant a surface mounted as the
          stack's FIRST screen (launch routing via rankingMethodPref) had no
          path back to the chooser at all: Back landed on Trios — itself
          headerless with the flag off — and the RankMenu sheet doesn't list
          the chooser. Testers read that as being "stuck in a loop". Trios
          now carries the same always-on back control in both flag states
          (unflagged fix, same class as RankHome's S1B-05 header). */}
      <RankStack.Screen
        name="Trios"
        component={RankScreen}
        options={
          rankDest
            ? rankSubScreenOptions('Trios')
            : subScreenOptions('Trios', 'RankHome')
        }
      />
      <RankStack.Screen
        name="Anchors"
        component={PickAnchorScreen}
        options={
          rankDest
            ? rankSubScreenOptions('Pick Anchors')
            : subScreenOptions('Pick Anchors', 'RankHome')
        }
      />
      <RankStack.Screen
        name="Tiers"
        component={TiersScreen}
        options={
          rankDest
            ? rankSubScreenOptions('Tiers')
            : subScreenOptions('Tiers', 'RankHome')
        }
      />
      {/* 1.5.4 #104 — guided tier quick-set walk. #119 promoted it to a
          first-class method: reachable from the Tiers header, the Rank menu,
          the rank-home chooser, and launch routing (rankingMethodPref
          'quickset'). #162/#165: back falls back to the RankHome chooser
          (was the Tiers board) so a launch-routed walk always has a path
          back to "all the ranking options"; Tiers stays one menu tap away. */}
      <RankStack.Screen
        name="QuickSetTiers"
        component={QuickSetTiersScreen}
        // #244 — start the walk at the next unset position (ladder order).
        // initialParams only fill MISSING keys: entries that pass an
        // explicit `position` (Tiers header, guide next-position prompt)
        // are untouched; launch routing and param-less entries (Rank menu,
        // chooser) inherit it.
        initialParams={{ position: launch.quicksetStart }}
        // Flag on (PRD 01-02): the shared More-ways control opens the
        // RankMenu sheet like every other rank surface (RankHome stays
        // reachable — the menu's rows and this header's back-fallbacks
        // cover mode switching). Flag off: today's link to RankHome.
        // #217 (both flag states): the back control renders only when the
        // screen was PUSHED — see quickSetBackWhenPushed.
        options={
          rankDest
            // #217's pushed-only back control is moot with the flag on —
            // these surfaces carry no back control at all now.
            ? rankSubScreenOptions('Quick Set Tiers')
            : ({ navigation, route }) => ({
                ...subScreenOptions('Quick Set Tiers', 'RankHome')({ navigation }),
                headerLeft: () => quickSetBackWhenPushed(navigation, route),
                // #122: Quick Set is the no-pref default, so the demoted chooser
                // stays one tap away ("More ways to rank", item 9's Q1 ruling) —
                // it's the only path to RankHome from here (the Rank menu sheet
                // doesn't list the chooser).
                headerRight: () => (
                  <Pressable
                    testID="rank.more-ways"
                    onPress={() => navigation.navigate('RankHome')}
                    hitSlop={8}
                  >
                    {({ pressed }) => (
                      <Text
                        style={[
                          styles.moreWaysLink,
                          pressed && { color: chalk.base },
                        ]}
                      >
                        More ways to rank
                      </Text>
                    )}
                  </Pressable>
                ),
              })
        }
      />
      {/* #136 — within-tier ordering pass, the polish step after Quick set.
          Offered when the quick-set walk finishes and from the Rank menu.
          NOT a launch-routable pref (that's #122, unselected). #162/#165:
          back fallback is the RankHome chooser like every rank surface. */}
      <RankStack.Screen
        name="QuickRank"
        component={QuickRankScreen}
        options={
          rankDest
            ? rankSubScreenOptions('Quick Rank')
            : subScreenOptions('Quick Rank', 'RankHome')
        }
      />
      <RankStack.Screen
        name="ManualRanks"
        component={ManualRanksScreen}
        options={
          rankDest
            ? rankSubScreenOptions('Overall Ranks')
            : subScreenOptions('Overall Ranks', 'RankHome')
        }
      />
      {/* rookie-draft M2 / O1-expanded — the consolidated rookie view is a
          sibling rank surface, not a drill-down: same back topology as
          every other one (#162/#165 — fallback is the RankHome chooser). */}
      <RankStack.Screen
        name="RookieRanks"
        component={RookieRanksScreen}
        options={
          rankDest
            ? rankSubScreenOptions('Rookie Ranks')
            : subScreenOptions('Rookie Ranks', 'RankHome')
        }
      />
      <RankStack.Screen
        name="Trends"
        component={TrendsScreen}
        options={
          rankDest
            ? rankSubScreenOptions('Trends')
            : subScreenOptions('Trends', 'RankHome')
        }
      />
    </RankStack.Navigator>
  );
}

function TradesStackNav() {
  // #246 — guided-first Acquire landing (approved mock mockups/
  // polish-lab-2026-08/acquire-landing-guided-first.html, V1). Flag on:
  // `TradesHome` lands DIRECTLY in the guided deck — TradesScreen with a
  // default `mode:'guided'` param — instead of the #156 launcher hub
  // (TradeFinderHubScreen is now UNROUTED; kept in the tree pending
  // cleanup). Every existing navigate('TradesHome') call site keeps
  // working and now lands on a trade; mode switching lives in the deck's
  // persistent chip strip (TradeFinderModeBar). `TradeDeck` stays
  // registered for the `app/trades/finder` deep-link path (same
  // component; a link there just pushes a second deck instance with
  // back-to-landing semantics). Flag off: TradesScreen stays the classic
  // standalone home exactly as before (no mode param, TradeDeck
  // unregistered).
  const finderHubOn = useFlag('trades.finder_hub');
  return (
    <TradesStack.Navigator screenOptions={{ headerShown: false }}>
      <TradesStack.Screen
        name="TradesHome"
        component={TradesScreen}
        initialParams={finderHubOn ? { mode: 'guided' } : undefined}
      />
      {finderHubOn ? (
        <TradesStack.Screen name="TradeDeck" component={TradesScreen} />
      ) : null}
      {/* Presentation v2 — registered unconditionally (see the import
          comment). Reachable only via the flag-gated "Today" chip. Both use
          the shared always-on back control, falling back to the Acquire
          landing, because native back is dead on iOS 26 (RNS#3294). */}
      <TradesStack.Screen
        name="TodaysTrade"
        component={TodaysTradeScreen}
        options={subScreenOptions("Today's Trade", 'TradesHome')}
      />
      <TradesStack.Screen
        name="TradeBrowseAll"
        component={TradeBrowseAllScreen}
        options={subScreenOptions('All trades', 'TodaysTrade')}
      />
      <TradesStack.Screen
        name="Portfolio"
        component={PortfolioScreen}
        options={chalklineHeader('Portfolio')}
      />
      {/* #357/#358/#359 — Team Review. Registered inside the TRADES stack
          because the operator's framing was explicit: a Team Review button
          INSIDE the find-a-trade experience, not a separate tab. Uses the
          shared always-on back control (native back is dead on iOS 26,
          RNS#3294 — the same reason Calculator and Today do). As a tab-stack
          screen it mounts NO FeedbackFAB of its own; RootNav's single global
          mount already covers it (#188 / #196 / #197). */}
      <TradesStack.Screen
        name="TeamReview"
        component={TeamReviewScreen}
        options={subScreenOptions('Team review', 'TradesHome')}
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

function LeagueStackNav() {
  // #181 — the League tab lands on the rankings view (the primary page);
  // the classic league page is a pushed sub-route reached from the rankings
  // screen's "League home" row. The rankings screen keeps its title via a
  // stack header (no back control — it's the stack root, so the native
  // header simply has no headerLeft; never a back button to nowhere). The
  // legacy ROOT-stack 'LeagueSummary' route (RootNav) stays registered for
  // old entry points (deep link app/league/summary, stored whats-new
  // routes); this tab-root variant is the same component under a different
  // route name.
  return (
    <LeagueStack.Navigator screenOptions={{ headerShown: false }}>
      <LeagueStack.Screen
        name="LeagueRankings"
        component={LeagueSummaryScreen}
        options={chalklineHeader('League rankings')}
      />
      <LeagueStack.Screen
        name="LeagueHome"
        component={LeagueScreen}
        // Shared always-on back control (#51/#52 pattern), falling back to
        // the rankings root — covers the cold-start deep-link case where
        // LeagueHome is the stack's only route.
        options={subScreenOptions('League home', 'LeagueRankings')}
      />
    </LeagueStack.Navigator>
  );
}

// ── The seasonal Draft tab ───────────────────────────────────────────────
// Operator decision (2026-08-06, verbatim): "On the Draft tab - it should
// literally just be set to seasonal. So a flag we turn on and off to display
// the tab. Right now it should be on for all."
//
// So: `draft.tab` and NOTHING else. No league qualification, no AsyncStorage
// snapshot, no confidence check, no platform check. The tab shipped gated on
// a per-league predicate fed by a snapshot that only converged on the NEXT
// launch, and the operator hit exactly the failure that design permits — two
// leagues genuinely qualified (verified server-side) and the tab still did
// not appear, because the snapshot was empty on that build's first run. An
// operator-flipped seasonal switch removes the launch lag entirely.
//
// DESTINATION: the ACTIVE league's Draft Room — no `leagueId` override and
// no chooser, because with the tab always on there is nothing to choose
// between. `DraftRoomScreen` renders every state honestly (drafted ⇒ recap,
// not-drafted ⇒ upcoming, ESPN ⇒ unsupported, no league ⇒ its no-league
// state), so a non-drafting league lands somewhere truthful rather than
// somewhere empty.
//
// The tab's PRESENCE is still decided ONCE at mount (see `showDraftTab` in
// TabNav): `initialRouteName`, #244's completion-aware Rank launch routing
// and #245/#246's Acquire semantics are all first-mount-only contracts that
// a mid-session tab insertion would violate.
const DraftStack = createNativeStackNavigator();

function DraftStackNav() {
  return (
    <DraftStack.Navigator screenOptions={{ headerShown: false }}>
      <DraftStack.Screen
        name="DraftRoom"
        component={DraftRoomScreen}
        // No `leagueId`: the room reads the session's active league, which is
        // what an always-on tab should show. `inTabs` suppresses the screen's
        // OWN FeedbackFAB — as a tab-stack screen it is already covered by
        // RootNav's global mount, and two FABs is the #196/#197 bug. The
        // root-stack registration passes nothing, so the pushed room keeps
        // its local FAB unchanged.
        initialParams={{ inTabs: true }}
        options={chalklineHeader('Rookie draft')}
      />
    </DraftStack.Navigator>
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
  // PRD 01-02: Rank tab is a real destination (navigate, no menu intercept).
  const rankDest = useFlag('ux.rank_tab_destination');
  // PRD 01-05: focused-tab re-tap pops to root / scrolls to top.
  const retapOn = useFlag('ux.retap_active_tab');

  // Onboarding trades-first (the gap found in the build-48 operator smoke):
  // nothing routed a treatment user to the deck — every onboarding surface
  // lives on the Trades tab, but the navigator defaulted to Rank. First-
  // session treatment users (no swipe yet) now land on Trades. Computed
  // once at mount (initialRouteName is only honored then); the App.tsx boot
  // gate awaits ftf_onboarding_state hydration, so this read never races
  // defaults. Flags-off → 'Rank', byte-identical to before.
  const [initialTab] = useState(() =>
    onboardingEnabled('onboarding.trades_first') &&
    !getOnboardingState().firstSwipeDone
      ? 'Trades'
      : 'Rank',
  );

  // The seasonal Draft tab — ONE FLAG, nothing else (operator decision
  // 2026-08-06: "a flag we turn on and off to display the tab"). No league
  // qualification, no snapshot, no confidence check, no platform check.
  //
  // Decided ONCE at mount, exactly like `initialTab` above and #244's Rank
  // launch routing: conditionally rendering a <Tab.Screen> rewrites the
  // navigator's route array, which reshuffles indices and can reset nested
  // stack state, so the bar may change at most once per launch.
  //
  // The flag is read IMPERATIVELY (not via useFlag) on purpose: a
  // mid-session flag revalidation must not be able to insert or remove a
  // tab under the user's thumb. Flag off ⇒ `false` ⇒ four tabs, and the
  // whole subtree below is never constructed.
  //
  // Everything else about this navigator is unchanged whether the tab is
  // present or absent: `initialRouteName` still resolves to Rank/Trades by
  // name (never index), the Rank stack's #244 completion-aware launch
  // routing lives inside RankStackNav, and #245/#246's Acquire semantics
  // live inside TradesStackNav. Adding a sibling touches none of them.
  const [showDraftTab] = useState(
    () => !!useFeatureFlags.getState().flags['draft.tab'],
  );

  // P0-7 — tab_selected. `from_tab` is the tab that OWNED the bar at press
  // time; optional-chained throughout because a null is honest and a throw
  // is not (track swallows anyway, but a throw inside a listener would take
  // the tap with it). NON_INTENT server-side: a tab tap is navigation, not
  // intent (analytics_queries.NON_INTENT_EVENTS).
  const trackTab = (
    tab: string,
    navigation: any,
    opts?: { intercepted?: boolean },
  ) => {
    const st = navigation?.getState?.();
    track('tab_selected', {
      tab,
      from_tab: st?.routes?.[st.index]?.name?.toLowerCase() ?? null,
      refocus: !!navigation?.isFocused?.(),
      intercepted: !!opts?.intercepted,
    });
  };

  return (
    <View style={{ flex: 1, backgroundColor: ink.ink0 }}>
      {/* Global top bar — sits above the tab navigator on every authed
          screen, owns the top safe-area inset, and renders the floating
          notifications bell on the right. Screens below intentionally
          don't include `top` in their SafeAreaView edges so the system
          inset isn't double-counted. */}
      <TopBar />
      <Tab.Navigator
        initialRouteName={initialTab}
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
          // PRD 01-02 (flag on): the tab navigates like a normal tab, so the
          // menu-signal chevron goes away.
          options={{
            tabBarIcon: rankDest ? tabIcon('rank') : rankTabIcon('rank'),
            tabBarLabel: 'Rank',
            tabBarButtonTestID: 'tab.rank',
          }}
          listeners={
            rankDest
              ? ({ navigation, route }) => ({
                  // PRD 01-02: default tab behavior — tapping Rank from
                  // another tab navigates to the stack (its initial route is
                  // the PREF_ROUTE surface; any in-session surface the user
                  // navigated to is preserved, i.e. "last used"). Focused
                  // re-tap pops the Rank stack back to that preferred
                  // surface. Mode switching lives in the surfaces' "More
                  // ways to rank" header control.
                  tabPress: () => {
                    trackTab('rank', navigation);
                    if (!navigation.isFocused()) return;
                    popNestedToTop(navigation, route);
                  },
                })
              : ({ navigation }) => ({
                  // Intercept the tap on the Rank tab — open the action sheet
                  // instead of jumping into a sub-screen. We still keep the tab
                  // active visually so the user knows where they are.
                  tabPress: (e) => {
                    trackTab('rank', navigation, { intercepted: true });
                    e.preventDefault();
                    setRankMenuOpen(true);
                  },
                })
          }
        />
        <Tab.Screen
          name="Trades"
          component={TradesStackNav}
          // #245 — presentation-level rename: the tab reads "Acquire" (trade
          // + free-agency acquisition). Route name 'Trades' is unchanged so
          // deep links, analytics events, and testIDs keep working.
          options={{
            tabBarIcon: tabIcon('trade'),
            tabBarLabel: 'Acquire',
            tabBarAccessibilityLabel: 'Acquire',
            tabBarButtonTestID: 'tab.trades',
          }}
          listeners={({ navigation, route }) => ({
            // Warm the liked-trades cache during the tab transition so
            // TradesScreen's `useQuery(['liked-trades', leagueId])` adopts
            // the in-flight request on mount. Don't preventDefault — the
            // tab should still navigate normally. Read leagueId from the
            // session store (same source TradesScreen uses) and skip the
            // prefetch when no league is active (the screen's query is
            // `enabled: !!leagueId`).
            tabPress: () => {
              trackTab('trades', navigation);
              // PRD 01-05 (flag `ux.retap_active_tab`): focused re-tap pops
              // the Trades stack (Portfolio/Calculator → TradesHome); at
              // root, ask the screen to scroll its deck/list to top.
              if (retapOn && navigation.isFocused()) {
                if (!popNestedToTop(navigation, route)) requestScrollToTop('Trades');
              }
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
        {/* The seasonal Draft tab — third in the bar, matching the approved
            mock's A′1 frame (Rank · Acquire · Draft · Matches · League). No
            flare dot: Sleeper exposes no trustworthy start time, so there is
            no countdown or urgency signal to honestly render. */}
        {showDraftTab ? (
          <Tab.Screen
            name="Draft"
            component={DraftStackNav}
            options={{
              tabBarIcon: tabIcon('flag'),
              tabBarLabel: 'Draft',
              tabBarAccessibilityLabel: 'Draft',
              tabBarButtonTestID: 'tab.draft',
            }}
            listeners={({ navigation, route }) => ({
              // Same focused-re-tap contract as the other stack tabs
              // (PRD 01-05): pop back to the stack root.
              tabPress: () => {
                trackTab('draft', navigation);
                if (retapOn && navigation.isFocused()) {
                  popNestedToTop(navigation, route);
                }
              },
            })}
          />
        ) : null}
        <Tab.Screen
          name="Matches"
          component={MatchesScreen}
          options={{ tabBarIcon: tabIcon('match'), tabBarButtonTestID: 'tab.matches' }}
          listeners={({ navigation }) => ({
            // Warm the cross-league matches cache during the tab transition
            // so MatchesScreen's `useQuery(['matches', 'all'])` adopts the
            // in-flight request on mount. Fire-and-forget; errors surface on
            // the screen's own query.
            tabPress: () => {
              trackTab('matches', navigation);
              // PRD 01-05: no nested stack — focused re-tap scrolls to top.
              if (retapOn && navigation.isFocused()) requestScrollToTop('Matches');
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
          component={LeagueStackNav}
          options={{ tabBarIcon: tabIcon('crown'), tabBarButtonTestID: 'tab.league' }}
          listeners={({ navigation, route }) => ({
            // PRD 01-05 (#181): the tab is a stack now — focused re-tap pops
            // LeagueHome back to the rankings root; at root, scroll to top
            // (the rankings screen registers the 'League' handler).
            tabPress: () => {
              trackTab('league', navigation);
              if (retapOn && navigation.isFocused()) {
                if (!popNestedToTop(navigation, route)) requestScrollToTop('League');
              }
            },
          })}
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
    } else if (screen === 'QuickSetTiers' || screen === 'QuickRank') {
      // #119 — QuickSetTiersScreen opens on position 'QB' and reads through
      // a format-scoped key (QuickSetTiersScreen.tsx:72), unlike TiersScreen's
      // flat key above. #136 — QuickRankScreen shares the same key.
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

  // #232 — the sheet renders the SAME content model as the RankHome
  // chooser (navigation/rankChooserModel.ts): three primary rows labeled
  // by outcome + the "More ways to rank" disclosure (collapsed per open).
  // Quick rank left both surfaces — it's Quick set's follow-on pass,
  // offered when the walk finishes (approved mock rationale). testIDs keep
  // their historical segments (rankmenu.trios for Head-to-heads etc.).
  const MENU_TESTID: Record<string, string> = {
    quickset: 'rankmenu.quickset',
    trio:     'rankmenu.trios',
    tiers:    'rankmenu.tiers',
    anchor:   'rankmenu.anchors',
    manual:   'rankmenu.manual',
    trends:   'rankmenu.trends',
  };
  const [moreOpen, setMoreOpen] = useState(false);
  const closeSheet = () => {
    setMoreOpen(false);
    onClose();
  };
  const pick = (m: ChooserMethod) => {
    setMoreOpen(false);
    go(m.route);
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={closeSheet}>
      <Pressable
        style={styles.backdrop}
        onPress={closeSheet}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      <View style={styles.sheet}>
        <View style={styles.handle} />
        <Text style={type.heading} accessibilityRole="header">Rank</Text>
        <Text style={styles.sheetSub}>Pick how you want to rank players.</Text>
        {PRIMARY_METHODS.map((it) => (
          <Pressable
            key={it.key}
            testID={MENU_TESTID[it.key]}
            accessibilityRole="button"
            accessibilityLabel={
              it.recommended
                ? `${it.title}, ${it.role}, recommended`
                : `${it.title}, ${it.role}`
            }
            accessibilityHint={it.body}
            onPress={() => pick(it)}
            style={({ pressed }) => [
              styles.item,
              pressed && { backgroundColor: ink.ink3 },
            ]}
          >
            <View style={{ flex: 1 }}>
              <View style={styles.itemLabelRow}>
                <Text style={styles.itemRole}>{it.role}</Text>
                {/* #119 — flare label = informational highlight (ADR-005),
                    same treatment as the rank-home chooser's tag. */}
                {it.recommended ? (
                  <Text style={styles.recommendedTag}>recommended</Text>
                ) : null}
              </View>
              <Text style={styles.itemLabel}>{it.title}</Text>
              <Text style={styles.itemSub}>{it.body}</Text>
            </View>
            <Icon name="chevron-right" size={16} color={chalk.dim} />
          </Pressable>
        ))}
        <Pressable
          testID="rankmenu.more-toggle"
          accessibilityRole="button"
          accessibilityLabel="More ways to rank"
          accessibilityState={{ expanded: moreOpen }}
          onPress={() => setMoreOpen((v) => !v)}
          style={styles.moreHeader}
        >
          <Text style={styles.moreHeaderText}>More ways to rank</Text>
          <Icon
            name={moreOpen ? 'chevron-up' : 'chevron-down'}
            size={16}
            color={chalk.dim}
          />
        </Pressable>
        {moreOpen
          ? MORE_METHODS.map((it) => (
              <Pressable
                key={it.key}
                testID={MENU_TESTID[it.key]}
                accessibilityRole="button"
                accessibilityLabel={it.title}
                accessibilityHint={it.body}
                onPress={() => pick(it)}
                style={({ pressed }) => [
                  styles.item,
                  pressed && { backgroundColor: ink.ink3 },
                ]}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.itemLabel}>{it.title}</Text>
                  <Text style={styles.itemSub}>{it.body}</Text>
                </View>
                <Icon name="chevron-right" size={16} color={chalk.dim} />
              </Pressable>
            ))
          : null}
        <Button label="Cancel" variant="ghost" onPress={closeSheet} style={styles.cancel} />
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  // Rank tab icon: glyph + menu chevron in a tight row. Nothing extends past
  // the tab's icon box so there's no clipping on the bottom bar.
  rankIconWrap: { flexDirection: 'row', alignItems: 'center', gap: 2 },

  // Item 9 — chooser discoverability from the Quick Set default.
  moreWaysLink: {
    ...type.bodySm,
    color: chalk.dim,
    fontFamily: fonts.uiSemi,
  },

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

  backdrop:{ ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
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
  // #232 — outcome label (FASTEST / MOST PRECISE / MOST CONTROL) above the
  // primary rows' titles, mirroring the RankHome chooser cards.
  itemRole: { ...type.label, color: chalk.dim },
  moreHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.lg,
    minHeight: 44,
  },
  moreHeaderText: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
  // #119 — mirrors RankHomeScreen's recommended tag (flare, informational).
  recommendedTag: { ...type.label, color: flare.base },
  itemSub: { ...type.bodySm, marginTop: 2 },
  cancel: { marginTop: space.md },
});
