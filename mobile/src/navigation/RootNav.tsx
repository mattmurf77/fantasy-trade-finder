import React, { useCallback, useRef } from 'react';
import {
  NavigationContainer,
  DarkTheme,
  createNavigationContainerRef,
} from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { colors } from '../theme/colors';
import { useSession } from '../state/useSession';
import SignInScreen from '../screens/SignInScreen';
import LeaguePickerScreen from '../screens/LeaguePickerScreen';
import TabNav from './TabNav';
import { usePushNotifications } from '../hooks/usePushNotifications';

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

  // Registers the device's Expo push token with the backend once the
  // user has signed in. No-op while `user` is null.
  usePushNotifications(user?.user_id ?? null, onTapMatchNotification);

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
