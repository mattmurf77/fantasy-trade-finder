// Settings › Notifications — second-level page.
//
// Implements plan §3 (`SettingsNotifications` row of the page table). Composes
// one Phase-0 section module:
//
//   • NotificationsSection — the denied-permission banner (flag
//     `notif.denial_recovery`), the three delivery toggles, quiet hours, the
//     time-zone value row and its "Detected from this device" footnote.
//
// BANNER: NotificationsSection delegates to the host (see its header comment),
// so <TickLabel>Notifications</TickLabel> is rendered here, matching the shipped
// flat list at SettingsScreen.tsx:1500.
//
// Data (plan §6): this page owns ['notif-prefs']. That is the point of the
// split — finding F4 is that the WHOLE settings screen blocks on this query
// (SettingsScreen.tsx:750). The wait now lives on the one page where blocking
// on notification prefs is honest, and NotificationsSection already scopes it
// to an inline placeholder rather than a full-screen spinner.

import React, { useState } from 'react';
import { ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { TickLabel } from '../../components/chalkline';
import FeedbackFAB from '../../components/FeedbackFAB';
import Toast from '../../components/Toast';
import { styles } from './styles';
import NotificationsSection from './sections/NotificationsSection';

export default function SettingsNotificationsScreen({ navigation }: any) {
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);

  // Plan §5 — pushed page, so a plain navigate (no goBack-first hack).
  const navigate = (route: string, params?: object) => navigation.navigate(route, params);
  const onNotice = (msg: string, tone?: 'success' | 'warn') => setToast({ msg, tone });

  return (
    <SafeAreaView style={styles.root} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <View style={styles.section}>
          <TickLabel>Notifications</TickLabel>
        </View>
        <NotificationsSection onNotice={onNotice} navigate={navigate} />
      </ScrollView>
      <Toast
        visible={!!toast}
        message={toast?.msg ?? ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />
      <FeedbackFAB activeScreen="SettingsNotifications" aboveTabBar={false} />
    </SafeAreaView>
  );
}
