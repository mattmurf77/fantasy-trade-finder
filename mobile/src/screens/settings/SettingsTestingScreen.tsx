// Settings › Testing — second-level page (dev / allowlisted-tester builds).
//
// Implements plan §3 (`SettingsTesting` row of the page table). Renders, in
// order:
//
//   • TestingSection — "Test stages", keeping its own `testing.stage_users`
//     gate. ("Test feedback" moved to Help & about with #354 BL-10.)
//   • TimingReadoutRow (components/, trades-eng's #363, head-eng ruling 11) —
//     directly after TestingSection, so it sits under the "Testing" banner. It
//     carries its own `testing.timing_readout` gate (renders null when off),
//     so this page adds no gate around it.
//
// BANNER: owned by TestingSection itself (<TickLabel>Testing</TickLabel>), so
// this page adds none.
//
// GATING. Per plan §3 the route is registered unconditionally and the HUB ENTRY
// ROW is gated, matching the RootNav convention; the flat list's shipped
// `{__DEV__ || stageUsersEnabled ? testingSection : null}` in SettingsScreen.tsx
// is unchanged. The hub's entry row and this page's body read the SAME
// predicate, useTesterSurface() (`__DEV__ || testing.stage_users ||
// testing.timing_readout`, #354 D-7; #407 gave the hub row the same three, so
// the readout's flag alone opens the page). When it is false — a non-tester
// following the `settings/testing` deep link — the page shows an honest
// unavailable line instead of an empty "Testing" banner (the RookieRanksScreen
// stale-link precedent); the header Back stays. When it is true the section
// and the readout render, and each keeps its own flag gate.
//
// NON-TESTER STATE (marketing-lead copy addendum 6A). The line reads "There's
// nothing on this page." (no tester vocabulary, no promise it comes back),
// with a "Back to Settings" button under it. The button calls
// navigate('Settings'), never goBack(): on a cold-start deep link the header
// Back has nothing to pop and goes to `Main` (RootNav settingsPageOptions), so
// only this button is sure to land in Settings. And the header title reads
// "Settings", not "Testing": RootNav renders the title through a headerTitle
// closure over 'Testing', so this page replaces both `title` and `headerTitle`
// in a layout effect, only while the predicate is false. With it true,
// RootNav's "Testing" stands.
//
// Data (plan §6): no queries.

import React, { useLayoutEffect, useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import FeedbackFAB from '../../components/FeedbackFAB';
import Toast from '../../components/Toast';
import { TimingReadoutRow } from '../../components/TimingReadoutRow';
import { Button, Text } from '../../components/chalkline';
import { chalk, fonts, space } from '../../theme/chalkline';
import { styles } from './styles';
import TestingSection from './sections/TestingSection';
import { useTesterSurface } from './useTesterSurface';

export default function SettingsTestingScreen({ navigation }: any) {
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);

  // Plan §5 — pushed page, so a plain navigate (no goBack-first hack). The
  // shipped screen needed two navigators here because "Test feedback" went
  // through navigateFromSettings (dismiss-then-navigate) while "Test stages"
  // called navigation.navigate directly; off a modal they are the same call, so
  // both props receive the same plain navigate.
  const navigate = (route: string, params?: object) => navigation.navigate(route, params);
  const onNotice = (msg: string, tone?: 'success' | 'warn') => setToast({ msg, tone });
  const testerSurface = useTesterSurface();

  // Addendum 6A: a non-tester's header never names the hidden page.
  useLayoutEffect(() => {
    if (!testerSurface) {
      navigation.setOptions({
        title: 'Settings',
        headerTitle: () => <PageHeaderTitle>Settings</PageHeaderTitle>,
      });
    }
  }, [navigation, testerSurface]);

  return (
    <SafeAreaView style={styles.root} edges={['bottom']}>
      {testerSurface ? (
        <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
          <TestingSection
            onNotice={onNotice}
            navigate={navigate}
            navigateWithoutDismiss={(route, params) => navigation.navigate(route, params)}
          />
          <TimingReadoutRow />
        </ScrollView>
      ) : (
        <View style={local.unavailable}>
          <Text testID="settings.testing-unavailable" variant="bodySm" style={local.unavailableText}>
            There's nothing on this page.
          </Text>
          <Button
            testID="settings.testing-unavailable.back"
            label="Back to Settings"
            onPress={() => navigation.navigate('Settings')}
          />
        </View>
      )}
      <Toast
        visible={!!toast}
        message={toast?.msg ?? ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />
      <FeedbackFAB activeScreen="SettingsTesting" aboveTabBar={false} />
    </SafeAreaView>
  );
}

// The stack-header title in RootNav's style (Barlow Condensed caps on the
// ink-0 bar). A LOCAL copy of RootNav's private HeaderTitle, the
// LeagueSummaryScreen StackHeaderTitle precedent: RootNav imports this screen,
// so importing from it would close a cycle.
function PageHeaderTitle({ children }: { children: string }) {
  return (
    <Text scale="display" numberOfLines={1} style={local.headerTitle}>
      {children}
    </Text>
  );
}

const local = StyleSheet.create({
  unavailable: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.lg,
    padding: space.lg,
  },
  unavailableText: { textAlign: 'center' },
  headerTitle: {
    fontFamily: fonts.displaySemi,
    fontSize: 18,
    letterSpacing: 0.54,
    textTransform: 'uppercase',
    color: chalk.base,
  },
});
