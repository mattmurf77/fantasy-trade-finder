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
import SettingsScreen from '../screens/SettingsScreen';
import PushPrimingModal from '../components/PushPrimingModal';
import { usePushNotifications } from '../hooks/usePushNotifications';
import { getProgress } from '../api/rankings';

type AuthStack = {
  SignIn: undefined;
  LeaguePicker: undefined;
  Main: undefined;
  Settings: undefined;
};

const Stack = createNativeStackNavigator<AuthStack>();
export const navigationRef = createNavigationContainerRef<AuthStack>();

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
  // Query is enabled only after sign-in. Cached short so unlock flips
  // propagate within ~30s of the user finishing rankings on the Trios screen
  // (which itself invalidates this query — see RankScreen submitMutation).
  const progressQuery = useQuery({
    queryKey: ['progress'],
    queryFn: getProgress,
    enabled: !!user && hasToken,
    staleTime: 15_000,
    refetchOnWindowFocus: true,
  });
  const pushEnabled = progressQuery.data?.unlocked === true;

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
