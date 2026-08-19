// Settings › Leagues — second-level page.
//
// Implements plan §3 (target IA, `SettingsLeagues` row of the page table) and
// §4 (row-by-row migration map). Composes three Phase-0 section modules:
//
//   • LeaguesSection            — switch-league rows + the connect-a-league card
//   • PlatformLinkSection       — "Link an ESPN league" / "Link an MFL league"
//   • PlatformDisconnectSection — Sleeper sending / ESPN account / MFL sign-in
//
// PlatformDisconnectSection is the F2 fix: the three disconnects ship today
// inside the Account section, ~15 rows away from the link CTAs they undo. This
// page is the one place a platform connection is made and unmade.
//
// BANNERS. All three modules delegate their banner to the host (see each
// module's header comment). Two are rendered here:
//   1. Above LeaguesSection — "Your leagues" when the user has more than one
//      league (matching the shipped conditional at SettingsScreen.tsx:1483 /
//      the legacy "Switch league" gate), otherwise "Connect a league", which is
//      the only thing LeaguesSection renders in the single-league case.
//   2. "Connected accounts" above the disconnect rows.
//   A separate banner for the connect card is not possible without editing
//   LeaguesSection: that module emits the switch rows and the connect card as
//   one fragment, so nothing can be placed between them. The conditional text
//   on banner 1 covers the case where the card is the whole section.
//
// Data (plan §6): this page owns ['sleeper-link'], ['espn-link'], ['mfl-link'],
// all three inside PlatformDisconnectSection. Nothing is fetched at the hub.

import React, { useState } from 'react';
import { ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { TickLabel } from '../../components/chalkline';
import FeedbackFAB from '../../components/FeedbackFAB';
import Toast from '../../components/Toast';
import { useSession } from '../../state/useSession';
import { styles } from './styles';
import LeaguesSection from './sections/LeaguesSection';
import PlatformLinkSection from './sections/PlatformLinkSection';
import PlatformDisconnectSection from './sections/PlatformDisconnectSection';

export default function SettingsLeaguesScreen({ navigation }: any) {
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);
  const leagues = useSession((s) => s.leagues);

  // Plan §5 — this is a pushed page, not a modal, so the
  // `goBack() then navigate()` hack at SettingsScreen.tsx:227 is deliberately
  // NOT reproduced. Back from the destination returns here.
  const navigate = (route: string, params?: object) => navigation.navigate(route, params);
  const onNotice = (msg: string, tone?: 'success' | 'warn') => setToast({ msg, tone });

  return (
    <SafeAreaView style={styles.root} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <View style={styles.section}>
          <TickLabel>{leagues.length > 1 ? 'Your leagues' : 'Connect a league'}</TickLabel>
        </View>
        <LeaguesSection onNotice={onNotice} navigate={navigate} />
        <PlatformLinkSection onNotice={onNotice} navigate={navigate} />

        <View style={styles.section}>
          <TickLabel>Connected accounts</TickLabel>
        </View>
        <PlatformDisconnectSection onNotice={onNotice} navigate={navigate} />
      </ScrollView>
      <Toast
        visible={!!toast}
        message={toast?.msg ?? ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />
      <FeedbackFAB activeScreen="SettingsLeagues" aboveTabBar={false} />
    </SafeAreaView>
  );
}
