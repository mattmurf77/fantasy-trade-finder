// Settings § Account — the DATA-RIGHTS half.
//
// Renders, in shipped order: the public-profile toggle (flag
// `profiles.user_toggle`, dark in prod), "Download my data" (flag
// `account.data_export`), and "Delete account" — which stays LAST, per plan §3
// ("Delete account stays last, after Download my data").
//
// Lifted from SettingsScreen.tsx (origin/main):
//   • :302-320  profileVisQuery (['profile-visibility']) + profilePublic mirror
//   • :322-336  flipProfilePublic
//   • :450-465  promptVerifyStepUp (S6A-09 / teardown 06-02 step-up alert)
//   • :470-491  handleExportData
//   • :611-657  performDeleteAccount + confirmDeleteAccount
//   • :1217-1252 publicProfileRow + exportRow JSX
//   • :1395-1410 the Delete account Pressable
//
// TickLabel: NONE. The shipped `accountSection` has exactly one
// `<TickLabel>Account</TickLabel>` and AccountIdentitySection — the first of
// the three modules that split it — carries it. Emitting a second banner here
// would change the Phase 0 flat render.
//
// Intentional behavior changes: NONE. The public-profile row still renders
// only once the stored value has loaded (`profilePublic !== null`) so the
// switch never lies — that is the shipped per-row loading posture, not a
// full-screen gate.

import React, { useEffect, useState } from 'react';
import { View, Text, Pressable, ActivityIndicator, Alert, Share } from 'react-native';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as FileSystem from 'expo-file-system/legacy';

import { chalk, semantic } from '../../../theme/chalkline';
import { Icon } from '../../../components/chalkline';
import { ApiError } from '../../../api/client';
import { deleteAccount } from '../../../api/auth';
import { exportAccountData, getProfileVisibility, setProfileVisibility } from '../../../api/accountPrefs';
import { useSession } from '../../../state/useSession';
import { useFlag } from '../../../state/useFeatureFlags';
import { styles } from '../styles';
import Row from '../Row';
import type { SettingsSectionProps } from './types';

export interface AccountDataSectionProps extends SettingsSectionProps {
  /** Post-deletion navigation. The shipped handler ran
   *  `navigation.replace('SignIn')` (SettingsScreen:616) after signOut() — a
   *  stack REPLACE, which the generic `navigate` prop cannot express, so the
   *  host performs it. Plan §5 lists this as a code-walk item for the
   *  modal→push flip. */
  onAccountDeleted: () => void;
}

export default function AccountDataSection({
  onNotice,
  navigate,
  onAccountDeleted,
}: AccountDataSectionProps) {
  const queryClient = useQueryClient();

  const dataExportEnabled    = useFlag('account.data_export');
  const profileToggleEnabled = useFlag('profiles.user_toggle');

  const isDemo  = useSession((s) => s.isDemo);
  const user    = useSession((s) => s.user);
  const signOut = useSession((s) => s.signOut);

  const [deleting, setDeleting]   = useState(false);
  const [exporting, setExporting] = useState(false);

  // ── Public-profile opt-in (teardown 06-04, flag `profiles.user_toggle`).
  // Optimistic local mirror with rollback on server error.
  const profileVisQuery = useQuery({
    queryKey: ['profile-visibility'],
    queryFn: getProfileVisibility,
    enabled: profileToggleEnabled && !isDemo,
    staleTime: 60_000,
    retry: false,
  });
  const [profilePublic, setProfilePublic] = useState<boolean | null>(null);
  useEffect(() => {
    if (profileVisQuery.data) setProfilePublic(!!profileVisQuery.data.public);
  }, [profileVisQuery.data]);

  // ── Verified-session step-up (S6A-09 / teardown 06-02) ─────────────────
  // Account-data actions 403 `verification_required` when the account is
  // verified but this session isn't. The old dead-end toast is replaced by
  // an alert that routes straight into the SleeperConnect verify flow.
  function promptVerifyStepUp(action: string) {
    Alert.alert(
      'Verify this session first',
      `Your account is verified, but this session isn't. Verify with your ` +
        `Sleeper login to ${action}.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Verify now',
          onPress: () => navigate('SleeperConnect'),
        },
      ],
    );
  }

  function flipProfilePublic() {
    const next = !(profilePublic ?? false);
    setProfilePublic(next); // instant — optimistic
    setProfileVisibility(next)
      .then((res) => queryClient.setQueryData(['profile-visibility'], res))
      .catch((e: unknown) => {
        setProfilePublic(!next); // rollback
        if (e instanceof ApiError && e.status === 403) {
          promptVerifyStepUp('change your public profile');
        } else {
          onNotice("Couldn't save — try again.", 'warn');
        }
      });
  }

  // ── Data export (teardown 06-02, flag `account.data_export`) ───────────
  // GET /api/account/export → write the JSON archive to the cache dir →
  // hand it to the system share sheet (AirDrop / Save to Files / Mail).
  async function handleExportData() {
    if (exporting) return;
    setExporting(true);
    try {
      const archive = await exportAccountData();
      const uri = `${FileSystem.cacheDirectory}fantasy-trade-finder-export.json`;
      await FileSystem.writeAsStringAsync(uri, JSON.stringify(archive, null, 2));
      await Share.share({ url: uri });
    } catch (e: unknown) {
      if (e instanceof ApiError && e.status === 403) {
        promptVerifyStepUp('download your data');
      } else if (e instanceof ApiError && e.status === 400) {
        onNotice('Demo sessions have no stored data.', 'warn');
      } else {
        const msg = (e as { message?: string } | null)?.message;
        onNotice(msg || "Couldn't export your data — try again.", 'warn');
      }
    } finally {
      setExporting(false);
    }
  }

  async function performDeleteAccount() {
    if (deleting) return;
    setDeleting(true);
    try {
      await deleteAccount();
      await signOut();
      onAccountDeleted();
    } catch (e: unknown) {
      if (dataExportEnabled && e instanceof ApiError && e.status === 403) {
        // S6A-09: the verified-step-up 403 used to dead-end in a toast.
        // Same recovery path as export (both PRD 06-02 data-rights gates).
        promptVerifyStepUp('delete your account');
      } else {
        const msg = (e as { message?: string } | null)?.message;
        onNotice(msg || "Couldn't delete your account — try again.", 'warn');
      }
    } finally {
      setDeleting(false);
    }
  }

  function confirmDeleteAccount() {
    Alert.alert(
      'Delete account?',
      'This permanently deletes your rankings, comparison history, trade activity, ' +
        'notifications, push tokens, and any stored Sleeper connection from our ' +
        'servers. Trade matches shared with leaguemates are anonymized on your side. ' +
        'This cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Continue',
          style: 'destructive',
          onPress: () =>
            Alert.alert(
              'Are you absolutely sure?',
              'Your account and all of its data will be deleted immediately. ' +
                'There is no way to recover them.',
              [
                { text: 'Keep my account', style: 'cancel' },
                {
                  text: 'Delete everything',
                  style: 'destructive',
                  onPress: () => void performDeleteAccount(),
                },
              ],
            ),
        },
      ],
    );
  }

  // Public-profile opt-in toggle (flag `profiles.user_toggle`). Only renders
  // once the stored value has loaded so the switch never lies.
  const publicProfileRow =
    profileToggleEnabled && !isDemo && profilePublic !== null ? (
      <Row
        title="Public profile"
        sub={`Let anyone see your tiers at /u/${user?.username || 'your-username'}. Off keeps your board private.`}
        value={profilePublic}
        onChange={flipProfilePublic}
      />
    ) : null;

  // Data-rights export row (flag `account.data_export`) — directly ABOVE
  // Delete account so the two data-rights actions read as a pair.
  const exportRow =
    dataExportEnabled && !isDemo ? (
      <Pressable
        testID="settings.export-data"
        accessibilityRole="button"
        accessibilityState={{ disabled: exporting, busy: exporting }}
        onPress={() => void handleExportData()}
        disabled={exporting}
        style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
      >
        <View style={{ flex: 1 }}>
          <Text style={styles.rowKey}>Download my data</Text>
          <Text style={styles.rowSub}>
            Export everything we store about you as a JSON file.
          </Text>
        </View>
        {exporting ? (
          <ActivityIndicator color={chalk.dim} />
        ) : (
          <Icon name="chevron-right" color={chalk.dim} size={16} />
        )}
      </Pressable>
    ) : null;

  if (isDemo) return null;

  return (
    <>
      {publicProfileRow}
      {exportRow}
      <Pressable
        // S8 PRD-02 acceptance: Delete account announces as a button
        // with a clear destructive label (was a plain text group).
        accessibilityRole="button"
        accessibilityLabel="Delete account"
        accessibilityHint="Permanently deletes your account and all of its data"
        accessibilityState={{ disabled: deleting, busy: deleting }}
        onPress={confirmDeleteAccount}
        disabled={deleting}
        style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
      >
        <View style={{ flex: 1 }}>
          <Text style={[styles.rowKey, styles.destructiveKey]}>Delete account</Text>
          <Text style={styles.rowSub}>
            Permanently delete your account and all of its data.
          </Text>
        </View>
        {deleting ? (
          <ActivityIndicator color={semantic.neg} />
        ) : (
          <Icon name="chevron-right" color={chalk.dim} size={16} />
        )}
      </Pressable>
    </>
  );
}

