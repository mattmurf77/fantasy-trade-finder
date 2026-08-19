// Settings › Testing — second-level page (dev / allowlisted-tester builds).
//
// Implements plan §3 (`SettingsTesting` row of the page table). Composes one
// Phase-0 section module:
//
//   • TestingSection — "Test feedback" and "Test stages" (the latter keeping
//     its own `testing.stage_users` gate).
//
// BANNER: owned by TestingSection itself (<TickLabel>Testing</TickLabel>), so
// this page adds none.
//
// GATING. Per plan §3 the route is registered unconditionally and the HUB ENTRY
// ROW is what gets gated (`__DEV__ || testing.stage_users`), matching the
// RootNav convention and the shipped `{__DEV__ || stageUsersEnabled ? … }` at
// SettingsScreen.tsx:1505. This page mounts the section unconditionally, which
// is exactly what the shipped module expects — the section's own comment states
// the host decides whether to mount it.
//
// Data (plan §6): no queries.

import React, { useState } from 'react';
import { ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import FeedbackFAB from '../../components/FeedbackFAB';
import Toast from '../../components/Toast';
import { styles } from './styles';
import TestingSection from './sections/TestingSection';

export default function SettingsTestingScreen({ navigation }: any) {
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);

  // Plan §5 — pushed page, so a plain navigate (no goBack-first hack). The
  // shipped screen needed two navigators here because "Test feedback" went
  // through navigateFromSettings (dismiss-then-navigate) while "Test stages"
  // called navigation.navigate directly; off a modal they are the same call, so
  // both props receive the same plain navigate.
  const navigate = (route: string, params?: object) => navigation.navigate(route, params);
  const onNotice = (msg: string, tone?: 'success' | 'warn') => setToast({ msg, tone });

  return (
    <SafeAreaView style={styles.root} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <TestingSection
          onNotice={onNotice}
          navigate={navigate}
          navigateWithoutDismiss={(route, params) => navigation.navigate(route, params)}
        />
      </ScrollView>
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
