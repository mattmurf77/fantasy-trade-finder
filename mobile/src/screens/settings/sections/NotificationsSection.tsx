// Notifications — denied-permission banner, the three delivery toggles,
// quiet hours + time zone.
//
// Extracted verbatim from SettingsScreen.tsx (origin/main):
//   • `['notif-prefs']` query + `local` mirror + hydrate effect :655-673
//   • `mutation` + `flip`                                       :675-693
//   • OS permission check + `notifPermDenied` + the
//     `notif_denied_settings_shown` track effect                :341-362
//   • `notifDeniedBanner`                                       :1021-1041
//   • `notifToggleRows`                                         :1043-1064
//   • `quietHoursRows`                                          :1066-1084
//   • the `Row` switch helper                                   :1561-1584
//
// SECTION BANNER: none. The host page owns the
// <TickLabel>Notifications</TickLabel> (plan §3 — `SettingsNotifications`);
// today's flat v2 list renders it at SettingsScreen.tsx:1500. Rows only.
//
// BEHAVIOR CHANGE (the one intended change in Phase 0, plan §6 / finding F4):
// the prefs query no longer blanks the WHOLE screen. SettingsScreen.tsx:750
// returns a full-screen ActivityIndicator while `prefsQuery.isLoading || !local`,
// so opening Settings to switch leagues waits on GET /api/notifications/prefs.
// Here the wait is scoped to the rows that actually need the data: an inline
// placeholder stands in for the toggles + quiet hours until `local` hydrates.
// The denied banner and the permission tracking are unaffected — the banner
// depends only on the OS permission read, and the track effect already fired
// during the old full-screen gate (the early return sat below every hook).
//
// The `Row` helper is duplicated here rather than imported: it is a private
// function inside SettingsScreen.tsx with no export, and this wave does not
// own that file. Fold the two together when the host screen is rewired.

import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Linking, StyleSheet, Text, View } from 'react-native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as Notifications from 'expo-notifications';

import { ice } from '../../../theme/chalkline';
import { Button, Card } from '../../../components/chalkline';
import { getNotifPrefs, updateNotifPrefs } from '../../../api/notifications';
import { track } from '../../../api/events';
import { useFlag } from '../../../state/useFeatureFlags';
import type { NotificationPrefs } from '../../../shared/types';
import { styles } from '../styles';
import Row from '../Row';
import type { SettingsSectionProps } from './types';

export default function NotificationsSection({ onNotice }: SettingsSectionProps) {
  const queryClient = useQueryClient();
  const settingsV2 = useFlag('account.settings_v2');
  const denialRecoveryEnabled = useFlag('notif.denial_recovery');

  // Local mirror of server prefs so toggles feel instant. Hydrated from the
  // query below; updates push through `mutation` and the query is invalidated
  // on success.
  const [local, setLocal] = useState<NotificationPrefs | null>(null);

  const prefsQuery = useQuery({
    queryKey: ['notif-prefs'],
    queryFn: getNotifPrefs,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (prefsQuery.data) setLocal(prefsQuery.data);
  }, [prefsQuery.data]);

  const mutation = useMutation({
    mutationFn: (patch: Partial<NotificationPrefs>) => updateNotifPrefs(patch),
    onError: () => {
      // Roll back local state to last-known-good server value.
      if (prefsQuery.data) setLocal(prefsQuery.data);
      onNotice("Couldn't save — try again.", 'warn');
    },
    onSuccess: (next) => {
      setLocal(next);
      queryClient.setQueryData(['notif-prefs'], next);
    },
  });

  const flip = (key: keyof NotificationPrefs) => {
    if (!local) return;
    const nextVal = local[key] ? 0 : 1;
    setLocal({ ...local, [key]: nextVal as 0 | 1 });
    mutation.mutate({ [key]: nextVal as 0 | 1 } as Partial<NotificationPrefs>);
  };

  // ── OS notification-permission state (teardown 05-03, flag
  // `notif.denial_recovery`). Read once per mount; denied → inline banner
  // above the toggles with a deep link into iOS Settings.
  const [notifPermDenied, setNotifPermDenied] = useState(false);
  const deniedShownRef = useRef(false);
  useEffect(() => {
    if (!denialRecoveryEnabled) return;
    let cancelled = false;
    Notifications.getPermissionsAsync()
      .then((p) => {
        if (!cancelled) setNotifPermDenied(p.status === 'denied');
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [denialRecoveryEnabled]);
  useEffect(() => {
    if (notifPermDenied && !deniedShownRef.current) {
      deniedShownRef.current = true;
      track('notif_denied_settings_shown', {}, 'Settings');
    }
  }, [notifPermDenied]);

  // Teardown 05-03 — denied-permission recovery banner. Rendered above the
  // toggles whenever iOS-level permission is denied (flag-gated); the
  // toggles stay editable (prefs persist for when permission returns) but
  // visually subordinate.
  const notifDeniedBanner = notifPermDenied ? (
    <View testID="settings.notif-denied-banner">
      <Card>
        <View style={styles.deniedBody}>
          <Text style={styles.rowSub}>
            Notifications are off for this app in iOS Settings. Your choices
            below are saved, but nothing can be delivered until you turn
            notifications back on.
          </Text>
          <Button
            label="Open iOS Settings"
            variant="secondary"
            onPress={() => {
              track('notif_denied_settings_tapped', {}, 'Settings');
              Linking.openSettings().catch(() => {});
            }}
          />
        </View>
      </Card>
    </View>
  ) : null;

  // Per-section loading (plan §6): the toggles cannot render honestly without
  // server prefs, so THEY wait — not the page. Replaces the full-screen
  // spinner at SettingsScreen.tsx:750-758.
  if (!local) {
    return (
      <>
        {notifDeniedBanner}
        <View style={sectionStyles.inlineLoading}>
          <ActivityIndicator color={ice.base} />
        </View>
      </>
    );
  }

  const notifToggleRows = (
    <View style={notifPermDenied ? styles.subordinate : undefined}>
      <Row
        title="Trade matches"
        sub="New matches, counter-offers, league activity"
        value={!!local.trade_matches}
        onChange={() => flip('trade_matches')}
      />
      <Row
        title="Weekly digest"
        sub="Tuesday/Wednesday morning roundup"
        value={!!local.weekly_digest}
        onChange={() => flip('weekly_digest')}
      />
      <Row
        title="Stay in the game"
        sub="Occasional nudges if you've been away"
        value={!!local.reengagement}
        onChange={() => flip('reengagement')}
      />
    </View>
  );

  const quietHoursRows = (
    <>
      <Row
        title="Pause overnight (10pm – 8am)"
        sub="Notifications will bundle into one summary at 8am local"
        value={!!local.quiet_hours_enabled}
        onChange={() => flip('quiet_hours_enabled')}
      />
      <View style={styles.kvRow}>
        <Text style={styles.rowKey}>Time zone</Text>
        <Text style={styles.kvValue}>{local.tz}</Text>
      </View>
      {settingsV2 ? (
        // Backend `notif.tz_sync` adopts the device tz at session start —
        // tell the user where the value comes from (S6B-05 footer).
        <Text style={styles.rowFootnote}>Detected from this device</Text>
      ) : null}
    </>
  );

  return (
    <>
      {notifDeniedBanner}
      {notifToggleRows}
      {quietHoursRows}
    </>
  );
}

// The ONE rule not present in ../styles: an in-flow placeholder box. The shared
// `styles.loading` is `flex: 1` (it was the full-screen gate's container) and
// collapses to zero height inside a ScrollView content container.
const sectionStyles = StyleSheet.create({
  inlineLoading: {
    minHeight: 132, // ≈ the three toggle rows it stands in for
    alignItems: 'center',
    justifyContent: 'center',
  },
});
