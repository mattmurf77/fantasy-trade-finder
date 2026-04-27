import React, { useCallback, useRef } from 'react';
import {
  NavigationContainer,
  DarkTheme,
  createNavigationContainerRef,
} from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { colors } from '../theme/colors';
import { useSession } from '../state/useSession';
import SignInScreen from '../screens/SignInScreen';
import LeaguePickerScreen from '../screens/LeaguePickerScreen';
import TabNav from './TabNav';
import { usePushNotifications } from '../hooks/usePushNotifications';
import { getProgress } from '../api/rankings';

type AuthStack = {
  SignIn: undefined;
  LeaguePicker: undefined;
  Main: undefined;
};

const Stack = createNativeStackNavigator<AuthStack>();
const navigationRef = createNavigationContainerRef<AuthStack>();

export default function RootNav({ booted }: { booted: boolean }) {
  const user = useSession((s) => s.user);
  const league = useSession((s) => s.league);
  const hasToken = useSession((s) => s.hasToken);

  // Deep-link tapped trade-match pushes into the Matches tab. The
  // callback is stable so the hook's cleanup stays clean.
  const onTapMatchNotification = useCallback((_matchId?: string | number) => {
    if (!navigationRef.isReady()) return;
    try {
      // @ts-expect-error — nested tab nav route; types don't cover cross-stack
      navigationRef.navigate('Main', { screen: 'Matches' });
    } catch {
      // swallow — navigation state may be mid-transition
    }
  }, []);

  // Drive the iOS push-permission deferral. We only want to ask after the
  // user has earned the Find-a-Trade unlock (progress.unlocked === true),
  // so we tail /api/rankings/progress at the root of the authed tree and
  // gate the push hook on that flag.
  //
  // Cache the unlocked flag in a ref. Once it flips true, we stop polling
  // entirely — the gate is one-way (a user who unlocked stays unlocked
  // for this session) and there's no reason to keep hitting the endpoint
  // every focus. Saves a per-resume fetch on the user's most-used flow.
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

  return (
    <NavigationContainer
      ref={navigationRef}
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
            <SignInScreen onSignedIn={() => navigation.replace('LeaguePicker')} />
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
        <Stack.Screen name="Main" component={TabNav} />
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
