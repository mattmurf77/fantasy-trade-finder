// Platform disconnects — Sleeper sending, ESPN account, MFL sign-in.
//
// Extracted verbatim from SettingsScreen.tsx (origin/main):
//   • `sleeperDisconnectRow`  :1126-1162   (+ query :286-292)
//   • `espnDisconnectRow`     :1164-1189   (+ query :299-305)
//   • `mflDisconnectRow`      :1191-1217   (+ query :306-312)
//   • `confirmDisconnectSleeper` / `performDisconnectSleeper`  :490-531
//   • `confirmDisconnectEspn` / `performDisconnectEspn`        :533-574
//   • `confirmDisconnectMfl` / `performDisconnectMfl`          :576-606
//
// These three rows ship TODAY inside the Account section. They are their own
// module because plan §4 moves all three to the Leagues page (finding F2 —
// "Link an ESPN league" and "Disconnect ESPN account" currently sit ~15 rows
// apart in two sections that never mention each other). Phase 0 does not move
// them; it only makes moving them a one-line composition change.
//
// SECTION BANNER: none. Whichever page hosts these owns the banner — Account
// today (SettingsScreen.tsx:1255), Leagues from Phase 2 on. Rows only.
//
// Behavior changes: none. Each row already renders `null` until its status
// query resolves (and stays null on error / flag-dark 404 — retry:false makes
// that a stable answer), so absence IS the shipped loading state. No skeleton
// is added: a placeholder for a row that may legitimately never appear would
// be a new, wrong affordance.

import React, { useState } from 'react';
import { ActivityIndicator, Alert, Pressable, Text, View } from 'react-native';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { chalk } from '../../../theme/chalkline';
import { Icon } from '../../../components/chalkline';
import { getSleeperLinkStatus, unlinkSleeper } from '../../../api/sendInSleeper';
import { getEspnLinkStatus, unlinkEspn } from '../../../api/sendInEspn';
import { getMflLinkStatus, unlinkMfl } from '../../../api/sendInMfl';
import { useSession } from '../../../state/useSession';
import { useFlag } from '../../../state/useFeatureFlags';
import { styles } from '../styles';
import type { SettingsSectionProps } from './types';

export default function PlatformDisconnectSection({ onNotice }: SettingsSectionProps) {
  const queryClient = useQueryClient();
  const isDemo = useSession((s) => s.isDemo);
  const user   = useSession((s) => s.user);

  const sleeperDisconnectEnabled = useFlag('account.sleeper_disconnect');
  const espnLinkEnabled          = useFlag('espn.link');
  // MFL authenticated sign-in (#177) — powers the MFL disconnect row below.
  const mflAuthLinkEnabled       = useFlag('mfl.auth_link');

  const [disconnecting, setDisconnecting] = useState(false);
  const [espnDisconnecting, setEspnDisconnecting] = useState(false);
  const [mflDisconnecting, setMflDisconnecting] = useState(false);

  // ── Sleeper-sending link status (teardown 09-01, flag
  // `account.sleeper_disconnect`) — powers the disconnect row. retry:false
  // because a 404 (send-in-sleeper dark) is a stable answer, not a blip;
  // on any error the row simply doesn't render.
  const sleeperLinkQuery = useQuery({
    queryKey: ['sleeper-link'],
    queryFn: getSleeperLinkStatus,
    enabled: sleeperDisconnectEnabled && !isDemo && !user?.account_only,
    staleTime: 60_000,
    retry: false,
  });

  // ── ESPN / MFL account credentials (2026-08-12 incident) — power the
  // per-platform disconnect rows, same posture as sleeperLinkQuery: a 404
  // (flag dark) is a stable answer, and on any error the row simply doesn't
  // render. Before these rows existed, removing a captured ESPN sign-in
  // (e.g. a friend's account used to test) required a production-DB delete.
  const espnLinkQuery = useQuery({
    queryKey: ['espn-link'],
    queryFn: getEspnLinkStatus,
    enabled: espnLinkEnabled && !isDemo,
    staleTime: 60_000,
    retry: false,
  });
  const mflLinkQuery = useQuery({
    queryKey: ['mfl-link'],
    queryFn: getMflLinkStatus,
    enabled: mflAuthLinkEnabled && !isDemo,
    staleTime: 60_000,
    retry: false,
  });

  // ── Disconnect Sleeper sending (teardown 09-01, flag
  // `account.sleeper_disconnect`) — the policy's promised "disconnect at
  // any time" control. unlinkSleeper() drops the server-side token AND this
  // device's Keychain copy (#126 R-5).
  async function performDisconnectSleeper() {
    if (disconnecting) return;
    setDisconnecting(true);
    try {
      await unlinkSleeper();
      queryClient.invalidateQueries({ queryKey: ['sleeper-link'] });
      onNotice('Sleeper sending disconnected — the stored token was deleted.', 'success');
    } catch (e: any) {
      onNotice(e?.message || "Couldn't disconnect — try again.", 'warn');
    } finally {
      setDisconnecting(false);
    }
  }

  function confirmDisconnectSleeper() {
    Alert.alert(
      'Disconnect Sleeper sending?',
      'This deletes the Sleeper sign-in token we store for sending trades ' +
        'you approve. Your rankings and matches are unaffected, and you can ' +
        'reconnect anytime.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Disconnect',
          style: 'destructive',
          onPress: () => void performDisconnectSleeper(),
        },
      ],
    );
  }

  // ── Disconnect ESPN / MFL accounts (2026-08-12 incident) — same shape as
  // the Sleeper disconnect: destructive confirm naming exactly what is
  // deleted, then DELETE + status invalidation. After an ESPN disconnect the
  // user can immediately sign in as a DIFFERENT account: the credential row
  // is gone server-side and EspnConnectScreen clears the WebView's
  // ESPN/Disney session on every mount.
  async function performDisconnectEspn() {
    if (espnDisconnecting) return;
    setEspnDisconnecting(true);
    try {
      await unlinkEspn();
      queryClient.invalidateQueries({ queryKey: ['espn-link'] });
      onNotice('ESPN account disconnected — the stored sign-in cookies were deleted.', 'success');
    } catch (e: any) {
      onNotice(e?.message || "Couldn't disconnect — try again.", 'warn');
    } finally {
      setEspnDisconnecting(false);
    }
  }

  function confirmDisconnectEspn() {
    Alert.alert(
      'Disconnect ESPN account?',
      'This deletes the two ESPN sign-in cookies (espn_s2 and SWID) we ' +
        'store. FTF will no longer be able to read private ESPN leagues or ' +
        'send ESPN trades until you sign in again — and you can sign in as ' +
        'a different ESPN account right away. Imported leagues stay.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Disconnect',
          style: 'destructive',
          onPress: () => void performDisconnectEspn(),
        },
      ],
    );
  }

  async function performDisconnectMfl() {
    if (mflDisconnecting) return;
    setMflDisconnecting(true);
    try {
      await unlinkMfl();
      queryClient.invalidateQueries({ queryKey: ['mfl-link'] });
      onNotice('MFL sign-in disconnected — the stored session cookie was deleted.', 'success');
    } catch (e: any) {
      onNotice(e?.message || "Couldn't disconnect — try again.", 'warn');
    } finally {
      setMflDisconnecting(false);
    }
  }

  function confirmDisconnectMfl() {
    Alert.alert(
      'Disconnect MFL sign-in?',
      'This deletes the MFL session cookie we store. FTF will no longer be ' +
        'able to send MFL trades or import private MFL leagues until you ' +
        'sign in again — as this or any other MFL account. Imported ' +
        'leagues stay.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Disconnect',
          style: 'destructive',
          onPress: () => void performDisconnectMfl(),
        },
      ],
    );
  }

  // Sleeper-sending status/disconnect row (flag `account.sleeper_disconnect`).
  // Hidden entirely when the link status can't be read (feature dark / error).
  const sleeperLink = sleeperLinkQuery.data;
  const sleeperDisconnectRow =
    sleeperDisconnectEnabled && !isDemo && !user?.account_only && sleeperLink ? (
      sleeperLink.connected ? (
        <Pressable
          testID="settings.sleeper-disconnect"
          accessibilityRole="button"
          accessibilityState={{ disabled: disconnecting, busy: disconnecting }}
          onPress={confirmDisconnectSleeper}
          disabled={disconnecting}
          style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
        >
          <View style={{ flex: 1 }}>
            <Text style={styles.rowKey}>Disconnect Sleeper sending</Text>
            <Text style={styles.rowSub}>
              {sleeperLink.expired
                ? 'Connection expired — disconnect to delete the stored token.'
                : 'Connected — FTF can send trades you approve. Disconnecting deletes the stored token.'}
            </Text>
          </View>
          {disconnecting ? (
            <ActivityIndicator color={chalk.dim} />
          ) : (
            <Icon name="chevron-right" color={chalk.dim} size={16} />
          )}
        </Pressable>
      ) : (
        <View style={styles.kvRow}>
          <Text style={styles.rowKey}>Sleeper sending</Text>
          <Text style={styles.kvValue}>Not connected</Text>
        </View>
      )
    ) : null;

  // ESPN account credential row (2026-08-12 incident). Renders only while a
  // credential is actually stored — a "Not connected" placeholder would
  // duplicate what the link flow already communicates. The disconnect is the
  // user-facing removal path that previously didn't exist.
  const espnLink = espnLinkQuery.data;
  const espnDisconnectRow =
    espnLinkEnabled && !isDemo && espnLink?.connected ? (
      <Pressable
        testID="settings.espn-disconnect"
        accessibilityRole="button"
        accessibilityState={{ disabled: espnDisconnecting, busy: espnDisconnecting }}
        onPress={confirmDisconnectEspn}
        disabled={espnDisconnecting}
        style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
      >
        <View style={{ flex: 1 }}>
          <Text style={styles.rowKey}>Disconnect ESPN account</Text>
          <Text style={styles.rowSub}>
            Connected — disconnecting deletes the stored ESPN sign-in cookies.
            Sign in again anytime, as any ESPN account.
          </Text>
        </View>
        {espnDisconnecting ? (
          <ActivityIndicator color={chalk.dim} />
        ) : (
          <Icon name="chevron-right" color={chalk.dim} size={16} />
        )}
      </Pressable>
    ) : null;

  // MFL sign-in row — same gap, same fix (audited in the same pass).
  const mflLink = mflLinkQuery.data;
  const mflDisconnectRow =
    mflAuthLinkEnabled && !isDemo && mflLink?.connected ? (
      <Pressable
        testID="settings.mfl-disconnect"
        accessibilityRole="button"
        accessibilityState={{ disabled: mflDisconnecting, busy: mflDisconnecting }}
        onPress={confirmDisconnectMfl}
        disabled={mflDisconnecting}
        style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
      >
        <View style={{ flex: 1 }}>
          <Text style={styles.rowKey}>Disconnect MFL sign-in</Text>
          <Text style={styles.rowSub}>
            {mflLink?.mfl_username
              ? `Signed in as ${mflLink.mfl_username} — disconnecting deletes the stored session cookie.`
              : 'Signed in — disconnecting deletes the stored session cookie.'}
          </Text>
        </View>
        {mflDisconnecting ? (
          <ActivityIndicator color={chalk.dim} />
        ) : (
          <Icon name="chevron-right" color={chalk.dim} size={16} />
        )}
      </Pressable>
    ) : null;

  return (
    <>
      {sleeperDisconnectRow}
      {espnDisconnectRow}
      {mflDisconnectRow}
    </>
  );
}
