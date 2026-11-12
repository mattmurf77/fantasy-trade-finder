import React from 'react';
import { Alert, Pressable, StyleSheet, View } from 'react-native';
import { SafeAreaInsetsContext, useSafeAreaInsets } from 'react-native-safe-area-context';

import { flare, fonts, ice, ink, radii, space } from '../theme/chalkline';
import { Text } from './chalkline';
import {
  exitTestProfile,
  resetTestProfile,
  useTestProfile,
} from '../state/testProfile';

// Onboarding test profile banner (docs/plans/onboarding-test-profile/).
// Mounted ONCE in App.tsx, ABOVE RootNav and outside every navigator, so it is
// on every screen — sign-in, league picker, onboarding, tabs, pushes — for as
// long as the device is in the test profile (state/testProfile ACTIVE_KEY,
// read at boot, so it survives restarts). It sits in the layout flow and
// consumes the top safe-area inset; the app below it gets top inset 0, so
// nothing is covered. Renders only `children` when not active.
//
// Chalkline: ink-1 strip, hairline rule; the "TEST PROFILE" label is flare
// (an informational highlight), both actions are ice text buttons.

export default function TestProfileBanner({ children }: { children: React.ReactNode }) {
  const active = useTestProfile((s) => s.active);
  const busy = useTestProfile((s) => s.busy);
  const insets = useSafeAreaInsets();
  if (!active) return <>{children}</>;

  const fail = (e: unknown) =>
    Alert.alert('Test profile', (e as Error)?.message || 'That did not work. Try again.');

  const confirmReset = () =>
    Alert.alert(
      'Reset test profile?',
      'Deletes everything the test profile has saved and starts onboarding again from the beginning. Your real profile is not touched.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Reset', style: 'destructive', onPress: () => resetTestProfile().catch(fail) },
      ],
    );

  return (
    <View style={styles.root}>
      <View testID="test-profile.banner" style={[styles.bar, { paddingTop: insets.top + space.xs }]}>
        <Text variant="bodySm" style={styles.label} numberOfLines={1}>
          TEST PROFILE
        </Text>
        <View style={styles.actions}>
          <Pressable
            testID="test-profile.banner.reset"
            accessibilityRole="button"
            accessibilityLabel="Reset test profile"
            disabled={busy}
            onPress={confirmReset}
            style={({ pressed }) => [styles.btn, pressed && styles.btnPressed]}
          >
            <Text style={styles.btnText}>Reset</Text>
          </Pressable>
          <Pressable
            testID="test-profile.banner.back"
            accessibilityRole="button"
            accessibilityLabel="Back to my profile"
            disabled={busy}
            onPress={() => exitTestProfile().catch(fail)}
            style={({ pressed }) => [styles.btn, pressed && styles.btnPressed]}
          >
            <Text style={styles.btnText}>{busy ? 'Switching…' : 'Back to my profile'}</Text>
          </Pressable>
        </View>
      </View>
      <SafeAreaInsetsContext.Provider value={{ ...insets, top: 0 }}>
        <View style={styles.app}>{children}</View>
      </SafeAreaInsetsContext.Provider>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: ink.ink0 },
  app: { flex: 1 },
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.md,
    paddingBottom: space.xs,
    backgroundColor: ink.ink1,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  label: { flex: 1, color: flare.base, fontFamily: fonts.uiSemi, letterSpacing: 1 },
  actions: { flexDirection: 'row', gap: space.xs },
  btn: {
    minHeight: 36,
    paddingHorizontal: space.sm,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radii.sm,
  },
  btnPressed: { backgroundColor: ink.ink3 },
  btnText: { fontFamily: fonts.uiSemi, fontSize: 14, color: ice.base },
});
