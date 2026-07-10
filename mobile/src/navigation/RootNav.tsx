import React, { useCallback, useRef, useState } from 'react';
import {
  NavigationContainer,
  DarkTheme,
  createNavigationContainerRef,
} from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { View, Text, ActivityIndicator, StyleSheet } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import * as Linking from 'expo-linking';
import { ink, chalk, ice, fonts } from '../theme/chalkline';
import { useSession } from '../state/useSession';
import SignInScreen from '../screens/SignInScreen';
import LeaguePickerScreen from '../screens/LeaguePickerScreen';
import TabNav from './TabNav';
import SettingsScreen from '../screens/SettingsScreen';
import ProfileScreen from '../screens/ProfileScreen';
import FeedbackInboxScreen from '../screens/FeedbackInboxScreen';
import SleeperConnectScreen from '../screens/SleeperConnectScreen';
import PushPrimingModal from '../components/PushPrimingModal';
import FeedbackFAB from '../components/FeedbackFAB';
import { usePushNotifications } from '../hooks/usePushNotifications';
import { useLeagueFormatDefault } from '../hooks/useScoringFormat';
import { getProgress } from '../api/rankings';
import { navigationIntegration } from '../observability/sentry';

type AuthStack = {
  SignIn: undefined;
  LeaguePicker: undefined;
  Main: undefined;
  Settings: undefined;
  Profile: { username: string };
  FeedbackInbox: undefined;
  SleeperConnect: undefined;
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
        if (r?.name) setActiveScreen(r.name);
      }}
      onStateChange={() => {
        const r = navigationRef.getCurrentRoute?.();
        if (r?.name) setActiveScreen(r.name);
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
            />
          )}
        </Stack.Screen>
        <Stack.Screen name="LeaguePicker">
          {({ navigation }) => (
            <LeaguePickerScreen
              onLeaguePicked={() => navigation.replace('Main')}
              onSignOut={async () => {
                await useSession.getState().signOut();
                navigation.replace('SignIn');
              }}
            />
          )}
        </Stack.Screen>
        <Stack.Screen name="Main">
          {() => (
            <>
              <TabNav />
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
          options={{
            presentation: 'modal',
            headerShown: true,
            title: 'Settings',
            headerTitle: () => <HeaderTitle>Settings</HeaderTitle>,
            headerStyle: { backgroundColor: ink.ink0 },
            headerTintColor: chalk.base,
          }}
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
});
