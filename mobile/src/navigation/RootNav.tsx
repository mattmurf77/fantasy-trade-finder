import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  NavigationContainer,
  DarkTheme,
  createNavigationContainerRef,
} from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { AppState, View, Text, ActivityIndicator, StyleSheet, Pressable } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import * as Linking from 'expo-linking';
import { ink, chalk, ice, fonts, radii } from '../theme/chalkline';
import { Icon } from '../components/chalkline';
import { useSession, NO_LEAGUE_ID } from '../state/useSession';
import SignInScreen from '../screens/SignInScreen';
import LeaguePickerScreen from '../screens/LeaguePickerScreen';
import LeagueJoinScreen from '../screens/LeagueJoinScreen';
import TabNav from './TabNav';
import SettingsScreen from '../screens/SettingsScreen';
// Settings IA (docs/plans/settings-ia-hub/plan.md) — the hub page and the
// seven second-level pages. The hub replaces SettingsScreen on the
// `Settings` route when `account.settings_hub` is on (see SettingsRoute
// below); the seven pages are registered unconditionally.
import SettingsHubScreen from '../screens/settings/SettingsHubScreen';
import SettingsLeaguesScreen from '../screens/settings/SettingsLeaguesScreen';
import SettingsRankingScreen from '../screens/settings/SettingsRankingScreen';
import SettingsTradeValuesScreen from '../screens/settings/SettingsTradeValuesScreen';
import SettingsNotificationsScreen from '../screens/settings/SettingsNotificationsScreen';
import SettingsAccountScreen from '../screens/settings/SettingsAccountScreen';
import SettingsAboutScreen from '../screens/settings/SettingsAboutScreen';
import SettingsTestingScreen from '../screens/settings/SettingsTestingScreen';
import ProfileScreen from '../screens/ProfileScreen';
import FeedbackInboxScreen from '../screens/FeedbackInboxScreen';
import SleeperConnectScreen from '../screens/SleeperConnectScreen';
import EspnConnectScreen from '../screens/EspnConnectScreen';
import PremiumRankingsBrowserScreen from '../screens/PremiumRankingsBrowserScreen';
import TestStagesScreen from '../screens/TestStagesScreen';
import LeagueSummaryScreen from '../screens/LeagueSummaryScreen';
import FreeAgentsScreen from '../screens/FreeAgentsScreen';
import ReceiptsScreen from '../screens/ReceiptsScreen';
import DraftRoomScreen from '../screens/DraftRoomScreen';
import MockDraftScreen from '../screens/MockDraftScreen';
import PickAssignmentScreen from '../screens/PickAssignmentScreen';
import RecordPicksScreen from '../screens/RecordPicksScreen';
import PushPrimingModal from '../components/PushPrimingModal';
import FeedbackFAB from '../components/FeedbackFAB';
import AnalystGuide from '../components/AnalystGuide';
import VerifyAccountBanner from '../components/VerifyAccountBanner';
import Toast from '../components/Toast';
import { usePushNotifications } from '../hooks/usePushNotifications';
import { useFlag, useFeatureFlags } from '../state/useFeatureFlags';
import {
  getLinkingV2,
  flushPendingNavIntents,
  setLinkFallbackNotifier,
  routeNotificationTap,
} from '../utils/deepLinks';
// Capture-harness launch-argument entry. Inert in production — the gate is
// a build-time constant documented at the top of utils/testRouteEntry.ts.
import { applyTestRouteEntry } from '../utils/testRouteEntry';
import { useLeagueFormatDefault } from '../hooks/useScoringFormat';
import { getProgress } from '../api/rankings';
import { track } from '../api/events';
import { navigationIntegration } from '../observability/sentry';

type AuthStack = {
  SignIn: undefined;
  // #130 — `espnLink: true` auto-opens the ESPN link sheet (Settings CTA).
  // P0-5/P0-3 — optional invite context. When an invited user arrives with
  // an account-only session, LeagueJoinScreen (P0-3, commit 12) replaces into
  // this screen carrying the inviter + league name; the picker's companion
  // state renders them as its lead copy. Nothing supplies them in wave 1 and
  // the companion state renders its generic copy when they are absent.
  LeaguePicker:
    | {
        espnLink?: boolean;
        /** P0-3 case B — hint that this league should auto-pin if present.
         *  A hint, not a command: the picker re-derives membership from its
         *  own refreshed list. */
        autoPinLeagueId?: string;
        /** P0-3 case C — render the "not in that league yet" notice row. */
        inviteNotice?: boolean;
        invitedBy?: string;
        invitedLeagueName?: string;
      }
    | undefined;
  // P0-3 — invite join interstitial. ROOT stack: reachable while signed out
  // (the invitee usually is), and the capture harness enters it by name
  // through testRouteEntry's SIGNED_OUT_ENTRY_ROUTES allowlist.
  LeagueJoin: { leagueId: string; ref?: string };
  Main: undefined;
  Settings: undefined;
  // Settings IA second level (plan §3). Registered UNCONDITIONALLY, like
  // every other flag-gated surface on this stack: `account.settings_hub`
  // gates the ENTRY ROWS (the hub renders them), not the routes, so a deep
  // link or an in-flight push during flag revalidation lands on a real page
  // rather than a dead one.
  SettingsLeagues: undefined;
  SettingsRanking: undefined;
  SettingsTradeValues: undefined;
  SettingsNotifications: undefined;
  SettingsAccount: undefined;
  SettingsAbout: undefined;
  SettingsTesting: undefined;
  Profile: { username: string };
  FeedbackInbox: undefined;
  SleeperConnect: undefined;
  // ESPN league linking Phase 1b (flag `espn.webview_capture`) — in-app
  // WebView that captures espn_s2 + SWID from the native cookie store for
  // private ESPN leagues. Pushed from EspnLinkSheet's "Sign in to ESPN"
  // path; delivers the cookies back to the sheet via espnConnectBus. No
  // params — the sheet owns the returned data (it hides its own Modal for
  // the push, since a native-stack screen lands behind an open RN Modal).
  // Send-auth lazy flow (2026-08-11): `reason` tells the screen WHY it was
  // entered so its banner says the right thing — absent/undefined = the
  // private-league link capture (EspnLinkSheet, copy unchanged);
  // 'send' = the trade-send path (SendInEspnButton), which stores the
  // captured pair server-side itself (credential-only POST /api/espn/link)
  // instead of delivering to the sheet's bus.
  EspnConnect: { reason?: 'send' } | undefined;
  // Premium Rankings Import v1, lane 2a ([D-058]) — in-app browser where the
  // user logs into their OWN Dynasty Nerds / DLF account and taps the site's
  // own Export CSV button. FTF never sees a credential; the captured file
  // goes back to the import chooser through `rankImportBus`. Registered
  // UNCONDITIONALLY: `ranks.source.*` gates the entry ROWS in the sheet, not
  // the route (same rule as the draft-surface pushes), so a stale entry
  // lands on an honest page rather than a 404.
  PremiumRankingsBrowser: { source: 'dynasty_nerds' | 'dlf' };
  // #142/#144 — League rankings (power rankings) + FA finder, entered from
  // the League tab's Explore rows.
  LeagueSummary: undefined;
  FreeAgents: undefined;
  // Receipts — the viewer's graded suggestion track record
  // (docs/plans/receipts/). No params: the screen scopes itself to the
  // session's league and the session's own user, because cross-user receipts
  // are a non-goal (PLAN NG-3) and a league param would invite one.
  Receipts: undefined;
  // rookie-draft M4 (flag `draft.room`) — read-only Draft Room, entered
  // from the League tab's Explore tile and (placement wave) the Acquire
  // tab's leading Draft chip. `leagueId` is an OVERRIDE used only by the
  // seasonal Draft tab's league chooser when more than one linked league
  // has a pending draft; every other entry point omits it and the room
  // reads the session's active league exactly as before.
  DraftRoom: { leagueId?: string } | undefined;
  // draft-extensions W2 (flag `draft.mock`) — the mock draft SESSION. The
  // entry is the room's `Real draft | Mock` switch (placement option C);
  // the session is pushed here so its flare mode rail owns a whole screen
  // for the entire time a pick can be made. Same `leagueId` override rule
  // as DraftRoom.
  MockDraft: { leagueId?: string } | undefined;
  // draft-extensions W3 M-A (flag `picks.assign`) — ESPN pick assignment.
  // Entered from the League tab's "Draft picks" section. `leagueId` is the
  // same override rule as DraftRoom; `focusPickId` is M-C's one-action
  // correction path — a priced surface deep-links straight to the slot
  // whose ownership the user wants to challenge, and `season` lands the
  // right season tab even when the payload no longer holds that pick_id
  // (M-C ships `{leagueId, season, focusPickId}` as one triple).
  PickAssignment:
    | { leagueId?: string; season?: number; focusPickId?: string }
    | undefined;
  // draft-extensions W3 M-D (flag `draft.manual_picks`) — live offline pick
  // recording. Entered from the Draft Room once picks are assigned.
  // `leagueId` is the same override rule as DraftRoom/PickAssignment.
  RecordPicks: { leagueId?: string } | undefined;
  // Operator QA (flag testing.stage_users): synthetic adoption-stage users.
  TestStages: undefined;
};

const Stack = createNativeStackNavigator<AuthStack>();
export const navigationRef = createNavigationContainerRef<AuthStack>();

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

// #151 — explicit JS back control for pushed screens. The NATIVE header back
// button goes unresponsive on iOS 26 when the previous screen hides its
// header (react-native-screens#3294 — our root stack's Main tabs run with
// headerShown: false), which testers hit on Free Agents. A JS Pressable
// wired straight to navigation.goBack() sidesteps the native control
// entirely. Icon Button construction per components.md (32×32, radius sm,
// chalk glyph, pressed = ink-3 fill; no emoji).
function HeaderBack({ onPress, testID }: { onPress: () => void; testID: string }) {
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel="Back"
      onPress={onPress}
      hitSlop={8}
      style={({ pressed }) => [styles.headerClose, pressed && { backgroundColor: ink.ink3 }]}
    >
      <Icon name="chevron-left" size={20} color={chalk.base} />
    </Pressable>
  );
}

// Settings IA (plan §7 phase 3) — `account.settings_hub` decides WHICH
// component the `Settings` route renders: the new hub page, or the flat list
// that shipped in 1.13.2. This is a wrapper rather than a branch inside
// SettingsScreen on purpose. SettingsScreen opens six queries and two
// fetches from hooks at the top of its body, so a branch inside it would
// still pay that cost on every open (and a post-hook early return is a
// rules-of-hooks violation). Mounting one component or the other is what
// makes the hub's zero-network promise (plan §6) real. Flag OFF mounts
// exactly the component it mounts today.
function SettingsRoute(props: any) {
  const hubEnabled = useFlag('account.settings_hub');
  return hubEnabled ? <SettingsHubScreen {...props} /> : <SettingsScreen {...props} />;
}

// Shared header options for the Settings second-level pages. All seven are
// plain pushes wearing the same Chalkline bar, with the #151 explicit JS
// back control (native back is dead on iOS 26 over a headerShown: false
// previous screen — RNS#3294). canGoBack() guards a cold-start deep link
// into a sub-page, which has no parent to pop to.
const settingsPageOptions =
  (title: string, backTestID: string) =>
  ({ navigation }: { navigation: any }) => ({
    headerShown: true,
    title,
    headerTitle: () => <HeaderTitle>{title}</HeaderTitle>,
    headerStyle: { backgroundColor: ink.ink0 },
    headerTintColor: chalk.base,
    headerBackVisible: false,
    headerLeft: () => (
      <HeaderBack
        testID={backTestID}
        onPress={() =>
          navigation.canGoBack() ? navigation.goBack() : navigation.navigate('Main')
        }
      />
    ),
  });

export default function RootNav({ booted }: { booted: boolean }) {
  const user = useSession((s) => s.user);
  const league = useSession((s) => s.league);
  const hasToken = useSession((s) => s.hasToken);
  const activeFormat = useSession((s) => s.activeFormat);
  const leagueId = league?.league_id ?? null;
  // Tracks the active route label so the in-app feedback FAB can pre-fill
  // the "Screen" field with whatever the user was looking at when they
  // tapped it. Updated on every navigation state change. Cheap because
  // the FAB only reads it when opened.
  const [activeScreen, setActiveScreen] = useState<string>('—');
  // Analytics (tracking plan v2): last screen_viewed we emitted, so state
  // changes that don't move the focused route (params, modals re-render)
  // don't double-fire, and each event can carry its prev_screen.
  const prevScreenRef = useRef<string | null>(null);
  // Observability addendum (2026-07-19): when the current screen was
  // entered, so screen_left carries a real dwell_ms. Emitted on nav-away
  // (below, in onStateChange) and on app-background — the case derived
  // dwell (delta between screen_viewed events) could never see.
  const screenEnteredAtRef = useRef<number>(Date.now());

  useEffect(() => {
    const sub = AppState.addEventListener('change', (next) => {
      if (next === 'background' || next === 'inactive') {
        const screen = prevScreenRef.current;
        if (screen) {
          track(
            'screen_left',
            {
              screen,
              dwell_ms: Date.now() - screenEnteredAtRef.current,
              reason: 'background',
            },
            screen,
          );
        }
      } else if (next === 'active') {
        // Foreground resumes the clock for the same screen — dwell across a
        // background gap is two screen_left rows, not one inflated one.
        screenEnteredAtRef.current = Date.now();
      }
    });
    return () => sub.remove();
  }, []);

  // FB #80 / #89 — league-driven scoring-format default. Whenever the
  // selected league changes, fetch its detected format (SF vs 1QB) and
  // apply it app-wide unless the user explicitly toggled a format for
  // this league in this session. Mounted here (once, at the authed root)
  // so ManualRanks/Tiers/Trios all inherit the right default regardless
  // of which screen the user opens first.
  useLeagueFormatDefault();

  // Tap-router: the push hook decodes `data.type` and tells us which tab
  // to focus.
  //
  // Legacy path (flag `notif.tap_routing_v2` OFF): tab-level navigate only —
  // match_id is intentionally discarded (the Matches tab loads the latest
  // list on focus) and not-ready taps are silently dropped.
  //
  // V2 path (flag ON, S5 PRD-02): route through utils/deepLinks'
  // routeNotificationTap — buffers until the container is ready (cold-start
  // taps replay via onReady), passes match_id into Matches as a route param
  // (`{ match_id, src: 'push', ts }` — scroll/highlight is MatchesScreen
  // work), and resolves through the v2 route table when
  // `ux.deeplink_router_v2` is also on.
  const onTapMatchNotification = useCallback(
    (tab: 'Matches' | 'League' | 'Rank' | 'Trades', matchId?: string | number) => {
      if (useFeatureFlags.getState().flags['notif.tap_routing_v2']) {
        routeNotificationTap(tab, matchId);
        return;
      }
      if (!navigationRef.isReady()) return;
      try {
        // @ts-expect-error — nested tab nav route; types don't cover cross-stack
        navigationRef.navigate('Main', { screen: tab });
      } catch {
        // swallow — navigation state may be mid-transition
      }
    },
    [],
  );

  // PRD 01-04 item 3: "Couldn't open that link" fallback toast for
  // unroutable deep links (v2 router only — the legacy parser keeps its
  // silent no-op). The Toast renders null while not visible, so this is
  // inert flag-off.
  const [linkToastVisible, setLinkToastVisible] = useState(false);
  useEffect(() => {
    setLinkFallbackNotifier(() => setLinkToastVisible(true));
    return () => setLinkFallbackNotifier(null);
  }, []);

  // Drive the iOS push-permission deferral. We only want to ask after the
  // user has earned the Find-a-Trade unlock (progress.unlocked === true),
  // so we tail /api/rankings/progress at the root of the authed tree and
  // gate the push hook on that flag.
  //
  // Once the unlock fires it's a one-way gate — there's no path back to
  // locked in the same session — so we cache it in a ref and disable
  // the query once flipped. Saves a per-resume refetch on the user's
  // most-used flow (returning to Trades) without keeping the polling
  // loop alive forever.
  const everUnlockedRef = useRef(false);
  const progressQuery = useQuery({
    queryKey: ['progress', leagueId, activeFormat],
    queryFn: getProgress,
    enabled: !!user && hasToken && !everUnlockedRef.current,
    staleTime: 15_000,
    refetchOnWindowFocus: true,
  });
  if (progressQuery.data?.unlocked === true) everUnlockedRef.current = true;
  const pushEnabled = everUnlockedRef.current || progressQuery.data?.unlocked === true;

  // PRD 01-04: v2 deep-link router flag. Read via hook so the component has
  // the hydrated value at mount; NavigationContainer only reads `linking`
  // once, so a mid-session flag flip applies on next launch (documented).
  const deeplinkV2 = useFlag('ux.deeplink_router_v2');

  // Registers the device's Expo push token with the backend once the
  // user has signed in AND unlocked Find-a-Trade. The hook always wires
  // up listeners post-signin so a notification that arrives despite no
  // permission prompt (e.g. permission was previously granted on this
  // device) still feeds the in-app bell.
  usePushNotifications(
    user?.user_id ?? null,
    onTapMatchNotification,
    pushEnabled,
  );

  if (!booted) {
    return (
      <View style={styles.splash}>
        <ActivityIndicator color={ice.base} />
      </View>
    );
  }

  // Decide initial stop based on what's persisted.
  // - No user  → SignIn
  // - User + no REAL league (or no token) → LeaguePicker
  // - User + real league + token → Main tabs
  //
  // P0-5: an account-only session pins the `no_league` SENTINEL, which is a
  // league object and therefore passed the old `!league` test — so relaunch
  // stranded the user on empty tabs even after the sign-in route was fixed.
  // Key off the sentinel, NEVER off `user.account_only`: account_only stays
  // true after an ESPN/MFL link (it is cleared only by linking a Sleeper
  // username, SettingsScreen's link-Sleeper card), so an account_only
  // predicate would trap a well-provisioned user in the picker forever.
  // `setLeague(real)` overwrites the sentinel, which is what ends this state.
  const hasRealLeague = !!league && league.league_id !== NO_LEAGUE_ID;
  const initialRoute: keyof AuthStack = !user
    ? 'SignIn'
    : !hasRealLeague || !hasToken
    ? 'LeaguePicker'
    : 'Main';

  // Linking config — react-navigation translates incoming Universal Links
  // and `dtf://` deep links into navigation actions. We register the same
  // /u/<username> route the web hosts so a single share URL works in both
  // surfaces. The `?ref=` capture is handled separately in utils/deepLinks
  // (we keep both so referrals work even when the URL has no path).
  //
  // Flag `ux.deeplink_router_v2` swaps in the full nested route table from
  // utils/deepLinks (tabs + pushed screens all URL-addressable); flag off
  // keeps the legacy 5-route map below exactly.
  const linking = deeplinkV2
    ? getLinkingV2()
    : {
        prefixes: [Linking.createURL('/'), 'https://fantasy-trade-finder.onrender.com'],
        config: {
          screens: {
            SignIn:       'signin',
            LeaguePicker: 'leagues',
            Main:         'app',
            Settings:     'settings',
            Profile:      'u/:username',
          },
        },
      };

  return (
    <NavigationContainer
      ref={navigationRef}
      linking={linking}
      onReady={() => {
        // Replay any navigation intents (cold-start push taps, early deep
        // links) buffered while the container wasn't ready. Only flag-on
        // paths enqueue, so with flags off this is a no-op on an empty queue.
        flushPendingNavIntents();
        // Capture harness only: `-FTFTestRoute <RouteName>` in the launch
        // arguments jumps straight to a screen that has no tappable path
        // under release flags. Runs AFTER auth restore (this whole subtree
        // only mounts once `booted` is true). Returns false (no navigator
        // touch at all) in every production bundle: see the build-time gate
        // in utils/testRouteEntry.ts.
        //
        // A signed-out boot is no longer a blanket refusal — `testRouteEntry`
        // owns the policy and allows only the names on its
        // `SIGNED_OUT_ENTRY_ROUTES` allowlist (P0-3's `LeagueJoin`); every
        // other name is still refused, because jumping into Main without a
        // session would photograph a signed-out shell. Behaviour for every
        // existing flow is unchanged.
        applyTestRouteEntry(navigationRef, { authed: initialRoute === 'Main' });
        // Hand the container ref to Sentry so it can tag spans by screen.
        // No-op when Sentry isn't initialized.
        navigationIntegration.registerNavigationContainer(navigationRef);
        // Seed the active-screen tracker with whatever's mounted at boot.
        const r = navigationRef.getCurrentRoute?.();
        if (r?.name) {
          setActiveScreen(r.name);
          track('screen_viewed', { screen: r.name, prev_screen: null }, r.name);
          prevScreenRef.current = r.name;
        }
      }}
      onStateChange={() => {
        const r = navigationRef.getCurrentRoute?.();
        if (r?.name) {
          setActiveScreen(r.name);
          if (r.name !== prevScreenRef.current) {
            // Close out the screen we're leaving with its measured dwell,
            // then open the next one. Order matters: screen_left(prev)
            // precedes screen_viewed(next) in the seq stream.
            if (prevScreenRef.current) {
              track(
                'screen_left',
                {
                  screen: prevScreenRef.current,
                  dwell_ms: Date.now() - screenEnteredAtRef.current,
                  reason: 'nav',
                },
                prevScreenRef.current,
              );
            }
            screenEnteredAtRef.current = Date.now();
            track(
              'screen_viewed',
              { screen: r.name, prev_screen: prevScreenRef.current },
              r.name,
            );
            prevScreenRef.current = r.name;
          }
        }
      }}
      theme={{
        ...DarkTheme,
        colors: {
          ...DarkTheme.colors,
          background: ink.ink0,
          card: ink.ink0,
          text: chalk.base,
          border: ink.line,
          primary: ice.base,
        },
      }}
    >
      <Stack.Navigator
        screenOptions={{ headerShown: false }}
        initialRouteName={initialRoute}
      >
        <Stack.Screen name="SignIn">
          {({ navigation }) => (
            <SignInScreen
              onSignedIn={() => navigation.replace('LeaguePicker')}
              // Demo flow already pinned a synthetic league + token in
              // useSession.startDemoSession, so we jump straight to Main.
              onDemoStarted={() => navigation.replace('Main')}
              // Account-first (P2.6) + P0-5: an account-only session holds the
              // `no_league` sentinel, NOT a league — it has nothing to show in
              // the tabs. Route to the picker, whose companion state leads with
              // "Connect Sleeper, ESPN or MFL". `replace`, not `navigate`: the
              // SignIn screen's session is spent and must not stay on the stack.
              onAccountSignedIn={() => navigation.replace('LeaguePicker')}
            />
          )}
        </Stack.Screen>
        <Stack.Screen name="LeaguePicker">
          {({ navigation, route }) => (
            <LeaguePickerScreen
              onLeaguePicked={() => navigation.replace('Main')}
              onSignOut={async () => {
                await useSession.getState().signOut();
                navigation.replace('SignIn');
              }}
              // #130 — Settings' "Link an ESPN league" row lands here with
              // the sheet already open (flag-gated inside the screen).
              autoOpenEspnLink={route.params?.espnLink === true}
              // P0-3 (commit 12) — invite context, when the arrival came from
              // LeagueJoin. Unset by every wave-1 entry; the companion state
              // renders its generic copy when they are null.
              autoPinLeagueId={route.params?.autoPinLeagueId}
              inviteNotice={route.params?.inviteNotice === true}
              invitedBy={route.params?.invitedBy ?? null}
              invitedLeagueName={route.params?.invitedLeagueName ?? null}
            />
          )}
        </Stack.Screen>
        {/* P0-3 — the invite JOIN interstitial. headerShown:false because it
            is an interstitial, not a pushed detail screen: a spent invite
            link must not present a back edge. */}
        <Stack.Screen
          name="LeagueJoin"
          component={LeagueJoinScreen}
          options={{ headerShown: false }}
        />
        <Stack.Screen name="Main">
          {({ navigation }) => (
            <>
              <TabNav />
              {/* Account-auth P1 — quiet "Verify your account" strip over
                  the authed tabs. Renders null unless the server flagged
                  this session (see VerifyAccountBanner's gate). Routes into
                  the same SleeperConnect capture used by Send-in-Sleeper. */}
              <VerifyAccountBanner
                onVerify={() => navigation.navigate('SleeperConnect')}
              />
              <PushPrimingModal />
              {/* In-app feedback capture (TestFlight). Floats above the
                  tab bar on every authed screen. Settings → Test feedback
                  exposes the inbox + share button. Remove this <FeedbackFAB />
                  line (and the matching Settings row) when the app graduates
                  to a public App Store release. */}
              <FeedbackFAB activeScreen={activeScreen} />
            </>
          )}
        </Stack.Screen>
        {/* Settings — a pushed page, not a modal (settings-IA plan §5). The
            page-sheet presentation is what forced navigateFromSettings to
            dismiss Settings before every outbound link; a push lets Back
            come back here. #130's ✕ went with the modal it was fixing —
            the back chevron is the discoverable control it was reaching
            for. The flip applies in BOTH `account.settings_hub` states,
            because it is the flat list's bug too. */}
        <Stack.Screen
          name="Settings"
          component={SettingsRoute}
          options={({ navigation }) => ({
            headerShown: true,
            title: 'Settings',
            headerTitle: () => <HeaderTitle>Settings</HeaderTitle>,
            headerStyle: { backgroundColor: ink.ink0 },
            headerTintColor: chalk.base,
            // #151 pattern — native back is dead on iOS 26 when the previous
            // screen (Main tabs) runs headerShown: false (RNS#3294). Explicit
            // JS back; canGoBack guards the settings:// cold-start deep link.
            headerBackVisible: false,
            headerLeft: () => (
              <HeaderBack
                testID="settings.back-btn"
                onPress={() =>
                  navigation.canGoBack()
                    ? navigation.goBack()
                    : navigation.navigate('Main')
                }
              />
            ),
          })}
        />
        {/* Settings second level (plan §3). Registered unconditionally —
            `account.settings_hub` gates the hub rows that lead here, not the
            routes. `SettingsTesting` follows the same rule its entry row
            already did (__DEV__ || testing.stage_users gates the ROW). */}
        <Stack.Screen
          name="SettingsLeagues"
          component={SettingsLeaguesScreen}
          options={settingsPageOptions('Leagues', 'settings.leagues.back-btn')}
        />
        <Stack.Screen
          name="SettingsRanking"
          component={SettingsRankingScreen}
          options={settingsPageOptions('Ranking', 'settings.ranking.back-btn')}
        />
        <Stack.Screen
          name="SettingsTradeValues"
          component={SettingsTradeValuesScreen}
          options={settingsPageOptions('Trade values', 'settings.trade-values.back-btn')}
        />
        <Stack.Screen
          name="SettingsNotifications"
          component={SettingsNotificationsScreen}
          options={settingsPageOptions('Notifications', 'settings.notifications.back-btn')}
        />
        <Stack.Screen
          name="SettingsAccount"
          component={SettingsAccountScreen}
          options={settingsPageOptions('Account & data', 'settings.account.back-btn')}
        />
        <Stack.Screen
          name="SettingsAbout"
          component={SettingsAboutScreen}
          options={settingsPageOptions('Help & about', 'settings.about.back-btn')}
        />
        <Stack.Screen
          name="SettingsTesting"
          component={SettingsTestingScreen}
          options={settingsPageOptions('Testing', 'settings.testing.back-btn')}
        />
        <Stack.Screen
          name="Profile"
          component={ProfileScreen}
          options={({ navigation, route }) => ({
            headerShown: true,
            // route.params is typed via AuthStack; cast to a known shape
            // so we can read username without unsafe `any`.
            title: `@${(route.params as { username?: string })?.username || 'profile'}`,
            headerTitle: () => (
              <HeaderTitle>
                {`@${(route.params as { username?: string })?.username || 'profile'}`}
              </HeaderTitle>
            ),
            headerStyle: { backgroundColor: ink.ink0 },
            headerTintColor: chalk.base,
            // #151 pattern — native back is dead on iOS 26 when the previous
            // screen (Main tabs) runs headerShown: false (RNS#3294). Explicit
            // JS back; canGoBack guards the /u/:username cold-start deep link.
            headerBackVisible: false,
            headerLeft: () => (
              <HeaderBack
                testID="profile.back-btn"
                onPress={() =>
                  navigation.canGoBack()
                    ? navigation.goBack()
                    : navigation.navigate('Main')
                }
              />
            ),
          })}
        />
        <Stack.Screen
          name="FeedbackInbox"
          component={FeedbackInboxScreen}
          options={{
            presentation: 'modal',
            headerShown: true,
            title: 'Test feedback',
            headerTitle: () => <HeaderTitle>Test feedback</HeaderTitle>,
            headerStyle: { backgroundColor: ink.ink0 },
            headerTintColor: chalk.base,
          }}
        />
        {/* #142/#144 — League rankings, pushed from the League tab's
            "League rankings" Explore row. Standard (non-modal) push; explicit
            JS back per the #151 pattern (native back dead over headerShown:
            false — RNS#3294). */}
        <Stack.Screen
          name="LeagueSummary"
          component={LeagueSummaryScreen}
          options={({ navigation }) => ({
            headerShown: true,
            title: 'League rankings',
            headerTitle: () => <HeaderTitle>League rankings</HeaderTitle>,
            headerStyle: { backgroundColor: ink.ink0 },
            headerTintColor: chalk.base,
            headerBackVisible: false,
            headerLeft: () => (
              <HeaderBack
                testID="league-summary.back-btn"
                onPress={() =>
                  navigation.canGoBack()
                    ? navigation.goBack()
                    : navigation.navigate('Main')
                }
              />
            ),
          })}
        />
        {/* FA finder — pushed from the League tab's "Free agents" row. */}
        <Stack.Screen
          name="FreeAgents"
          component={FreeAgentsScreen}
          options={({ navigation }) => ({
            headerShown: true,
            title: 'Free agents',
            headerTitle: () => <HeaderTitle>Free agents</HeaderTitle>,
            headerStyle: { backgroundColor: ink.ink0 },
            headerTintColor: chalk.base,
            // #151 — the native back control is unresponsive here on iOS 26
            // (react-native-screens#3294: previous screen has headerShown:
            // false). Hide it and mount our own JS back control. canGoBack
            // guards the cold-start deep-link case (FreeAgents as the only
            // route) by falling back to the Main tabs.
            headerBackVisible: false,
            headerLeft: () => (
              <HeaderBack
                testID="free-agents.back-btn"
                onPress={() =>
                  navigation.canGoBack()
                    ? navigation.goBack()
                    : navigation.navigate('Main')
                }
              />
            ),
          })}
        />
        {/* Receipts — the viewer's graded suggestion track record
            (docs/plans/receipts/). Pushed from the Trades home utility row.
            Registered UNCONDITIONALLY, per the house rule the Draft Room
            comment below states: the FLAG (`receipts.screen`) gates the ENTRY
            POINT, not the route, so an in-flight push survives a flag
            revalidation instead of unmounting under the user.

            A ROOT-STACK push, so ReceiptsScreen mounts its own FeedbackFAB
            (#188) — RootNav's global mount covers the tab stack only. */}
        <Stack.Screen
          name="Receipts"
          component={ReceiptsScreen}
          options={({ navigation }) => ({
            headerShown: true,
            title: 'Track record',
            headerTitle: () => <HeaderTitle>Track record</HeaderTitle>,
            headerStyle: { backgroundColor: ink.ink0 },
            headerTintColor: chalk.base,
            // Same iOS 26 back-control workaround as FreeAgents above
            // (react-native-screens#3294).
            headerBackVisible: false,
            headerLeft: () => (
              <HeaderBack
                testID="receipts.back-btn"
                onPress={() =>
                  navigation.canGoBack()
                    ? navigation.goBack()
                    : navigation.navigate('Main')
                }
              />
            ),
          })}
        />
        {/* Draft Room — pushed from the League tab's "Rookie draft" tile
            (flag `draft.room`). Registered unconditionally: the FLAG gates
            the entry point, not the route, so an in-flight push survives a
            flag revalidation instead of unmounting under the user. */}
        <Stack.Screen
          name="DraftRoom"
          component={DraftRoomScreen}
          options={({ navigation }) => ({
            headerShown: true,
            title: 'Rookie draft',
            headerTitle: () => <HeaderTitle>Rookie draft</HeaderTitle>,
            headerStyle: { backgroundColor: ink.ink0 },
            headerTintColor: chalk.base,
            // #151 pattern — see FreeAgents above (RNS#3294): the native
            // back control is dead on iOS 26 when the previous screen has
            // headerShown:false, so we mount our own.
            headerBackVisible: false,
            headerLeft: () => (
              <HeaderBack
                testID="draft-room.back-btn"
                onPress={() =>
                  navigation.canGoBack()
                    ? navigation.goBack()
                    : navigation.navigate('Main')
                }
              />
            ),
          })}
        />
        {/* Mock draft session — pushed from the room's Mock mode (flag
            `draft.mock`). Registered unconditionally for the same reason as
            DraftRoom: the FLAG gates the entry, not the route, so an
            in-flight push survives a flag revalidation. */}
        <Stack.Screen
          name="MockDraft"
          component={MockDraftScreen}
          options={({ navigation }) => ({
            headerShown: true,
            title: 'Mock draft',
            headerTitle: () => <HeaderTitle>Mock draft</HeaderTitle>,
            headerStyle: { backgroundColor: ink.ink0 },
            headerTintColor: chalk.base,
            // #151 pattern — see FreeAgents above (RNS#3294).
            headerBackVisible: false,
            headerLeft: () => (
              <HeaderBack
                testID="mock-draft.back-btn"
                onPress={() =>
                  navigation.canGoBack()
                    ? navigation.goBack()
                    : navigation.navigate('Main')
                }
              />
            ),
          })}
        />
        {/* Draft picks — ESPN pick assignment (draft-extensions W3 M-A,
            flag `picks.assign`). Pushed from the League tab's "Draft picks"
            section. Registered unconditionally for the same reason as
            DraftRoom and MockDraft: the FLAG gates the entry, not the
            route, so an in-flight push survives a flag revalidation and a
            stale deep link lands on the screen's honest unavailable state
            rather than a dead path. */}
        <Stack.Screen
          name="PickAssignment"
          component={PickAssignmentScreen}
          options={({ navigation }) => ({
            headerShown: true,
            title: 'Draft picks',
            headerTitle: () => <HeaderTitle>Draft picks</HeaderTitle>,
            headerStyle: { backgroundColor: ink.ink0 },
            headerTintColor: chalk.base,
            // #151 pattern — see FreeAgents above (RNS#3294). Omitting this
            // leaves back dead on iOS 26.
            headerBackVisible: false,
            headerLeft: () => (
              <HeaderBack
                testID="pick-assignment.back-btn"
                onPress={() =>
                  navigation.canGoBack()
                    ? navigation.goBack()
                    : navigation.navigate('Main')
                }
              />
            ),
          })}
        />
        {/* Record picks — live offline pick recording (draft-extensions
            W3 M-D, flag `draft.manual_picks`). Registered unconditionally
            for the same reason as PickAssignment/DraftRoom: the flag gates
            the entry point, not the route. */}
        <Stack.Screen
          name="RecordPicks"
          component={RecordPicksScreen}
          options={({ navigation }) => ({
            headerShown: true,
            title: 'Record picks',
            headerTitle: () => <HeaderTitle>Record picks</HeaderTitle>,
            headerStyle: { backgroundColor: ink.ink0 },
            headerTintColor: chalk.base,
            // #151 pattern — see FreeAgents above (RNS#3294). Omitting this
            // leaves back dead on iOS 26.
            headerBackVisible: false,
            headerLeft: () => (
              <HeaderBack
                testID="record-picks.back-btn"
                onPress={() =>
                  navigation.canGoBack()
                    ? navigation.goBack()
                    : navigation.navigate('Main')
                }
              />
            ),
          })}
        />
        <Stack.Screen
          name="TestStages"
          component={TestStagesScreen}
          options={({ navigation }) => ({
            headerShown: true,
            title: 'Test stages',
            headerTitle: () => <HeaderTitle>Test stages</HeaderTitle>,
            headerStyle: { backgroundColor: ink.ink0 },
            headerTintColor: chalk.base,
            // #151 pattern — see FreeAgents above (RNS#3294).
            headerBackVisible: false,
            headerLeft: () => (
              <HeaderBack
                testID="test-stages.back-btn"
                onPress={() =>
                  navigation.canGoBack()
                    ? navigation.goBack()
                    : navigation.navigate('Main')
                }
              />
            ),
          })}
        />
        <Stack.Screen
          name="SleeperConnect"
          component={SleeperConnectScreen}
          options={{
            presentation: 'modal',
            headerShown: true,
            title: 'Connect Sleeper',
            headerTitle: () => <HeaderTitle>Connect Sleeper</HeaderTitle>,
            headerStyle: { backgroundColor: ink.ink0 },
            headerTintColor: chalk.base,
          }}
        />
        {/* ESPN Connect WebView — cookie capture for private ESPN leagues
            (flag `espn.webview_capture`). Pushed (NOT modal) from
            EspnLinkSheet, which hides its own RN Modal for the duration: a
            modal presentation would land behind the sheet's Modal, and a
            push lands on the navigator the hidden Modal reveals. Registered
            unconditionally — the flag gates the entry button in the sheet,
            not the route (same rule as the draft-surface pushes). */}
        <Stack.Screen
          name="EspnConnect"
          component={EspnConnectScreen}
          options={({ navigation }) => ({
            headerShown: true,
            title: 'Connect ESPN',
            headerTitle: () => <HeaderTitle>Connect ESPN</HeaderTitle>,
            headerStyle: { backgroundColor: ink.ink0 },
            headerTintColor: chalk.base,
            // #151 pattern — native back is dead on iOS 26 over headerShown:
            // false (RNS#3294); mount our own JS back control.
            headerBackVisible: false,
            headerLeft: () => (
              <HeaderBack
                testID="espn-connect.back-btn"
                onPress={() =>
                  navigation.canGoBack()
                    ? navigation.goBack()
                    : navigation.navigate('Main')
                }
              />
            ),
          })}
        />
        {/* Premium rankings in-app browser ([D-058], lane 2a). Pushed (NOT
            modal) from ImportRankingsSheet, which the host closes first —
            a modal presentation would land behind that sheet's RN Modal,
            exactly as documented on EspnConnect above. */}
        <Stack.Screen
          name="PremiumRankingsBrowser"
          component={PremiumRankingsBrowserScreen}
          options={({ navigation, route }) => {
            const label =
              (route.params as { source?: string } | undefined)?.source === 'dlf'
                ? 'DLF'
                : 'Dynasty Nerds';
            return {
              headerShown: true,
              title: label,
              headerTitle: () => <HeaderTitle>{label}</HeaderTitle>,
              headerStyle: { backgroundColor: ink.ink0 },
              headerTintColor: chalk.base,
              // #151 pattern — see EspnConnect above (RNS#3294).
              headerBackVisible: false,
              headerLeft: () => (
                <HeaderBack
                  testID="premium-browser.back-btn"
                  onPress={() =>
                    navigation.canGoBack()
                      ? navigation.goBack()
                      : navigation.navigate('Main')
                  }
                />
              ),
            };
          }}
        />
      </Stack.Navigator>
      {/* The Analyst — guided-tour overlay (onboarding.guided_avatar).
          Container-level so S0 (sign-in) and S1 (league picker) are covered,
          not just the authed tabs. Renders null unless a step is active;
          native sheets/alerts still render above it (system modals win). */}
      <AnalystGuide />
      {/* PRD 01-04: unroutable-deep-link fallback toast (v2 router only).
          Renders null while not visible — inert with the flag off. */}
      <Toast
        visible={linkToastVisible}
        message="Couldn't open that link"
        tone="warn"
        holdMs={2500}
        onDismiss={() => setLinkToastVisible(false)}
      />
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  splash: {
    flex: 1,
    backgroundColor: ink.ink0,
    alignItems: 'center',
    justifyContent: 'center',
  },
  // type.heading scaled to fit the native header bar.
  headerTitle: {
    fontFamily: fonts.displaySemi,
    fontSize: 18,
    letterSpacing: 0.54,
    textTransform: 'uppercase',
    color: chalk.base,
  },
  // #130 — Icon Button spec (components.md): 32×32, radius sm, not circular.
  headerClose: {
    width: 32,
    height: 32,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
