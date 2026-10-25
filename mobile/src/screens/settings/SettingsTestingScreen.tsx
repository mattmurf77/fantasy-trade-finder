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
// GATING. Per plan §3 the route is registered unconditionally. The hub's entry
// row and this page's body read the SAME predicate, useTesterSurface()
// (`__DEV__ || testing.stage_users || testing.timing_readout`, #354 D-7). When
// it is false — a non-tester following the `settings/testing` deep link — the
// page shows an honest unavailable line instead of an empty "Testing" banner
// (the RookieRanksScreen stale-link precedent); the header Back stays. When it
// is true the section renders, and each row inside keeps its own flag gate.
//
// Data (plan §6): no queries.

import React, { useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import FeedbackFAB from '../../components/FeedbackFAB';
import Toast from '../../components/Toast';
import { TimingReadoutRow } from '../../components/TimingReadoutRow';
import { Text } from '../../components/chalkline';
import { space } from '../../theme/chalkline';
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
            This page isn't available.
          </Text>
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

const local = StyleSheet.create({
  unavailable: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.lg },
  unavailableText: { textAlign: 'center' },
});
