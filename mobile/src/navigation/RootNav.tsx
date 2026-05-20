import React, { useCallback, useRef } from 'react';
import {
  NavigationContainer,
  DarkTheme,
  createNavigationContainerRef,
} from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import * as Linking from 'expo-linking';
import { colors } from '../theme/colors';
import { useSession } from '../state/useSession';
import SignInScreen from '../screens/SignInScreen';
import LeaguePickerScreen from '../screens/LeaguePickerScreen';
import TabNav from './TabNav';
import SettingsScreen from '../screens/SettingsScreen';
import ProfileScreen from '../screens/ProfileScreen';
import PushPrimingModal from '../components/PushPrimingModal';
import { usePushNotifications } from '../hooks/usePushNotifications';
import { getProgress } from '../api/rankings';
import { navigationIntegration } from '../observability/sentry';

type AuthStack = {
  SignIn: undefined;
  LeaguePicker: undefined;
  Main: undefined;
  Settings: undefined;
  Profile: { username: string };
};

const Stack = createNativeStackNavigator<AuthStack>();
export const navigationRef = createNavigationContainerRef<AuthStack>();

export default function RootNav({ booted }: { booted: boolean }) {
  const user = useSession((s) => s.user);
  const league = useSession((s) => s.league);
  const hasToken = useSession((s) => s.hasToken);

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
    queryKey: ['progress'],
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
        <ActivityIndicator color={colors.accent} />
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
      }}
      theme={{
        ...DarkTheme,
        colors: {
          ...DarkTheme.colors,
          background: colors.bg,
          card: colors.surface,
          text: colors.text,
          border: colors.border,
          primary: colors.accent,
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
            headerStyle: { backgroundColor: colors.bg },
            headerTintColor: colors.text,
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
            headerStyle: { backgroundColor: colors.bg },
            headerTintColor: colors.text,
          })}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  splash: {
    flex: 1,
    backgroundColor: colors.bg,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
