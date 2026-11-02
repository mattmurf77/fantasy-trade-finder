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
// all three inside PlatformDisconnectSection, and D1's
// ['platform-write-consent', platform] (RosterMovesRow below). Nothing is
// fetched at the hub.

import React, { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, ScrollView, StyleSheet, Text, View, findNodeHandle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { Button, TickLabel } from '../../components/chalkline';
import FeedbackFAB from '../../components/FeedbackFAB';
import Toast from '../../components/Toast';
import { FA_MOVE_FALLBACK_COPY, readConsentStatus, withdrawConsent, type LeaguePlatform } from '../../api/faMove';
import { isEspnLeague } from '../../api/espn';
import { isMflLeague } from '../../api/platformLink';
import { useSession } from '../../state/useSession';
import { chalk, space, type } from '../../theme/chalkline';
import { styles } from './styles';
import LeaguesSection from './sections/LeaguesSection';
import PlatformLinkSection from './sections/PlatformLinkSection';
import PlatformDisconnectSection from './sections/PlatformDisconnectSection';

export default function SettingsLeaguesScreen({ navigation }: any) {
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);
  const leagues = useSession((s) => s.leagues);
  const isDemo = useSession((s) => s.isDemo);
  const accountOnly = useSession((s) => !!s.user?.account_only);
  // D1: one consent read per platform the user has a league on.
  const movePlatforms: LeaguePlatform[] = isDemo
    ? []
    : [
        ...(accountOnly ? [] : (['sleeper'] as const)),
        ...(leagues.some((l) => isEspnLeague(l.league_id)) ? (['espn'] as const) : []),
        ...(leagues.some((l) => isMflLeague(l.league_id)) ? (['mfl'] as const) : []),
      ];

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
        {movePlatforms.map((p) => (
          <RosterMovesRow key={p} platform={p} />
        ))}
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

// D1 — Stop roster moves (scope §C state 15; consent.md §4.4). Shown only
// while the consent GET says a grant is active (contract §2: 200 with
// `valid: false` when there's none; a 404 is an older server, read the same
// way; any other error shows nothing). This client has no request option
// that keeps that 404 out of api_request_failed.
// One tap, no dialog (K-F7). The server's withdrawal notice (R15.2.6)
// replaces the row verbatim and takes VoiceOver focus; the row goes. A
// failed DELETE keeps the row (the grant stays in force) with a line saying so.
function RosterMovesRow({ platform }: { platform: LeaguePlatform }) {
  const queryClient = useQueryClient();
  const consentQuery = useQuery({
    queryKey: ['platform-write-consent', platform],
    queryFn: () => readConsentStatus(platform),
    staleTime: 60_000,
    retry: false,
  });
  const [stopping, setStopping] = useState(false);
  const [stopped, setStopped] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const noticeRef = useRef<View>(null);

  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => {
      const node = noticeRef.current ? findNodeHandle(noticeRef.current) : null;
      if (node != null) AccessibilityInfo.setAccessibilityFocus(node);
    }, 150);
    return () => clearTimeout(t);
  }, [notice]);

  async function stop() {
    if (stopping) return;
    setStopping(true);
    setFailed(false);
    try {
      const out = await withdrawConsent(platform);
      setStopped(true);
      setNotice(typeof out?.notice === 'string' && out.notice ? out.notice : null);
      queryClient.invalidateQueries({ queryKey: ['platform-write-consent', platform] });
      // The claim sheet's capability (consent_until) rides on the FA read.
      queryClient.invalidateQueries({ queryKey: ['free-agents'] });
    } catch {
      setFailed(true);
      // iOS ignores accessibilityLiveRegion, so say it.
      AccessibilityInfo.announceForAccessibility(FA_MOVE_FALLBACK_COPY.stop_failed);
    } finally {
      setStopping(false);
    }
  }

  if (notice) {
    return (
      <View ref={noticeRef} accessible style={styles.row}>
        <Text style={rosterMoveText.notice}>{notice}</Text>
      </View>
    );
  }
  const status = consentQuery.data;
  if (stopped || status?.valid !== true) return null;
  return (
    <View>
      <View style={styles.kvRow}>
        <Text testID="settings.roster-moves.status" style={rosterMoveText.status}>
          {status.status_line || 'Roster moves'}
        </Text>
        <Button
          testID="settings.roster-moves.stop"
          label={status.stop_label || 'Stop roster moves'}
          variant="secondary"
          compact
          loading={stopping}
          onPress={() => void stop()}
        />
      </View>
      {failed ? (
        <Text style={rosterMoveText.failed} accessibilityLiveRegion="polite">
          {FA_MOVE_FALLBACK_COPY.stop_failed}
        </Text>
      ) : null}
    </View>
  );
}

const rosterMoveText = StyleSheet.create({
  status: { ...type.bodySm, color: chalk.dim, flex: 1 },
  notice: { ...type.bodySm, color: chalk.base, flex: 1 },
  failed: { ...type.bodySm, color: chalk.base, marginTop: space.xs },
});
