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
import { useSession } from '../state/useSession';
import SignInScreen from '../screens/SignInScreen';
import LeaguePickerScreen from '../screens/LeaguePickerScreen';
import TabNav from './TabNav';
import SettingsScreen from '../screens/SettingsScreen';
import ProfileScreen from '../screens/ProfileScreen';
import FeedbackInboxScreen from '../screens/FeedbackInboxScreen';
import SleeperConnectScreen from '../screens/SleeperConnectScreen';
import LeagueSummaryScreen from '../screens/LeagueSummaryScreen';
import FreeAgentsScreen from '../screens/FreeAgentsScreen';
import PushPrimingModal from '../components/PushPrimingModal';
import FeedbackFAB from '../components/FeedbackFAB';
import AnalystGuide from '../components/AnalystGuide';
import VerifyAccountBanner from '../components/VerifyAccountBanner';
import { usePushNotifications } from '../hooks/usePushNotifications';
import { useLeagueFormatDefault } from '../hooks/useScoringFormat';
import { getProgress } from '../api/rankings';
import { track } from '../api/events';
import { navigationIntegration } from '../observability/sentry';

type AuthStack = {
  SignIn: undefined;
  // #130 — `espnLink: true` auto-opens the ESPN link sheet (Settings CTA).
  LeaguePicker: { espnLink?: boolean } | undefined;
  Main: undefined;
  Settings: undefined;
  Profile: { username: string };
  FeedbackInbox: undefined;
  SleeperConnect: undefined;
  // #142/#144 — League rankings (power rankings) + FA finder, entered from
  // the League tab's Explore rows.
  LeagueSummary: undefined;
  FreeAgents: undefined;
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

// #130 — explicit close control for modal screens. Modal presentations only
// offered swipe-to-dismiss, which testers didn't discover on Settings. Icon
// Button construction per components.md (32×32, radius sm, chalk-dim glyph,
// pressed = ink-3 fill; no emoji).
function HeaderClose({ onPress, testID }: { onPress: () => void; testID: string }) {
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel="Close"
      onPress={onPress}
      hitSlop={8}
      style={({ pressed }) => [styles.headerClose, pressed && { backgroundColor: ink.ink3 }]}
    >
      <Icon name="x" size={20} color={chalk.dim} />
    </Pressable>
  );
}

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
  // to focus. We intentionally don't pass match_id deeper — the Matches
  // tab loads the latest list on focus and any specific match the user
  // tapped is already at the top.
  const onTapMatchNotification = useCallback(
    (tab: 'Matches' | 'League' | 'Rank' | 'Trades', _matchId?: string | number) => {
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
  // - User + no league (or no token) → LeaguePicker
  // - User + league + token → Main tabs
  const initialRoute: keyof AuthStack = !user
    ? 'SignIn'
    : !league || !hasToken
    ? 'LeaguePicker'
    : 'Main';

  // Linking config — react-navigation translates incoming Universal Links
  // and `dtf://` deep links into navigation actions. We register the same
  // /u/<username> route the web hosts so a single share URL works in both
  // surfaces. The `?ref=` capture is handled separately in utils/deepLinks
  // (we keep both so referrals work even when the URL has no path).
  const linking = {
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
              // Account-first (P2.6): account-only sessions have no leagues
              // to pick — the sentinel league is already pinned.
              onAccountSignedIn={() => navigation.replace('Main')}
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
            />
          )}
        </Stack.Screen>
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
        <Stack.Screen
          name="Settings"
          component={SettingsScreen}
          options={({ navigation }) => ({
            presentation: 'modal',
            headerShown: true,
            title: 'Settings',
            headerTitle: () => <HeaderTitle>Settings</HeaderTitle>,
            headerStyle: { backgroundColor: ink.ink0 },
            headerTintColor: chalk.base,
            // #130 — swipe-dismiss was the only exit; give the modal an
            // explicit close control.
            headerRight: () => (
              <HeaderClose testID="settings.close-btn" onPress={() => navigation.goBack()} />
            ),
          })}
        />
        <Stack.Screen
          name="Profile"
          component={ProfileScreen}
          options={({ route }) => ({
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
            "League rankings" Explore row. Standard (non-modal) push, so the
            native back control applies. */}
        <Stack.Screen
          name="LeagueSummary"
          component={LeagueSummaryScreen}
          options={{
            headerShown: true,
            title: 'League rankings',
            headerTitle: () => <HeaderTitle>League rankings</HeaderTitle>,
            headerStyle: { backgroundColor: ink.ink0 },
            headerTintColor: chalk.base,
          }}
        />
        {/* FA finder — pushed from the League tab's "Free agents" row. */}
        <Stack.Screen
          name="FreeAgents"
          component={FreeAgentsScreen}
          options={{
            headerShown: true,
            title: 'Free agents',
            headerTitle: () => <HeaderTitle>Free agents</HeaderTitle>,
            headerStyle: { backgroundColor: ink.ink0 },
            headerTintColor: chalk.base,
          }}
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
      </Stack.Navigator>
      {/* The Analyst — guided-tour overlay (onboarding.guided_avatar).
          Container-level so S0 (sign-in) and S1 (league picker) are covered,
          not just the authed tabs. Renders null unless a step is active;
          native sheets/alerts still render above it (system modals win). */}
      <AnalystGuide />
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
