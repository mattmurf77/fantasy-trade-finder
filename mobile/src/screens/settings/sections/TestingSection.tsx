// Settings § Testing — Test stages (operator QA surface). The feedback inbox
// row that used to sit here moved to AboutSection (#354 BL-10, D-3).
//
// Lifted verbatim from SettingsScreen.tsx (origin/main) `testingSection` at
// :1086-1118, plus:
//   • :270  stageUsersEnabled = useFlag('testing.stage_users')
//
// The section itself is rendered unconditionally by this module; the HOST
// decides whether to mount it, exactly as the shipped screen does
// (`{__DEV__ || stageUsersEnabled ? testingSection : null}` at :1505). The
// inner `settings.test-stages` row keeps its own `testing.stage_users` gate,
// which is why this module still reads the flag.
//
// TickLabel: renders `<TickLabel>Testing</TickLabel>`, matching the shipped
// screen, so the Phase 0 flat list is unchanged. Plan §3 gives the Phase 2 host
// page the title "Testing"; the banner is expected to move to the page header
// then.
//
// Intentional behavior changes: NONE. No queries, no loading state.

import React from 'react';
import { View, Text, Pressable, Alert } from 'react-native';

import { chalk } from '../../../theme/chalkline';
import { TickLabel, Icon } from '../../../components/chalkline';
import { useFlag } from '../../../state/useFeatureFlags';
import { enterTestProfile, useTestProfile } from '../../../state/testProfile';
import { styles } from '../styles';
import type { SettingsSectionProps } from './types';

export interface TestingSectionProps extends SettingsSectionProps {
  /** Raw `navigation.navigate`. The shipped "Test stages" row called it
   *  DIRECTLY (SettingsScreen:1103) rather than going through
   *  navigateFromSettings, so — unlike "Test feedback" — it does not dismiss
   *  the Settings modal first. Kept as a separate prop so Phase 0 preserves
   *  that difference exactly; the two collapse in Phase 1, when Settings
   *  stops being a modal and navigateFromSettings goes away (plan §5). */
  navigateWithoutDismiss: (route: string, params?: object) => void;
}

export default function TestingSection({
  navigateWithoutDismiss,
}: TestingSectionProps) {
  // Operator QA tool (server also allowlist-gates the spawn route). The
  // flag is delivered per-device via the experiment overlay, so it doubles
  // as the tester-allowlist signal for gating the Testing section in v2.
  const stageUsersEnabled = useFlag('testing.stage_users');
  // Onboarding test profile: shown only when the SERVER offers it to this
  // account (GET /api/test-profile — flag dev.test_profile AND the account in
  // TEST_PROFILE_ACCOUNTS) and the device is not already in it.
  const testProfileOffered = useTestProfile((s) => s.available && !s.active);
  const testProfileBusy = useTestProfile((s) => s.busy);

  const confirmTestProfile = () =>
    Alert.alert(
      'Test onboarding as a new user?',
      'The app restarts as a first launch. Sleeper, ESPN and MFL linking run the real flows ' +
        'with your own accounts; Apple / Google sign-in is not part of the test, and the ' +
        'landing ESPN / MFL buttons continue to the "Link a league" screens. Your real profile ' +
        'and data are kept exactly as they are; the banner at the top takes you back, or ' +
        'resets the test profile, at any time.\n\n' +
        'Signing in to ESPN or MFL here starts a new session with them. If they end older ' +
        'sessions, your real profile\'s ESPN or MFL link will ask you to re-link.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Start',
          onPress: () =>
            enterTestProfile().catch((e) =>
              Alert.alert('Test profile', e?.message || 'Could not start the test profile.'),
            ),
        },
      ],
    );

  return (
    <>
      <View style={styles.section}>
        <TickLabel>Testing</TickLabel>
      </View>
      {stageUsersEnabled ? (
        <Pressable
          testID="settings.test-stages"
          accessibilityRole="button"
          onPress={() => navigateWithoutDismiss('TestStages')}
          style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
        >
          <View style={{ flex: 1 }}>
            <Text style={styles.rowKey}>Test stages</Text>
            <Text style={styles.rowSub}>
              Spawn a synthetic user at any adoption stage (operator QA).
            </Text>
          </View>
          <Icon name="chevron-right" color={chalk.dim} size={16} />
        </Pressable>
      ) : null}
      {testProfileOffered ? (
        <Pressable
          testID="settings.testing.test-profile"
          accessibilityRole="button"
          disabled={testProfileBusy}
          onPress={confirmTestProfile}
          style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
        >
          <View style={{ flex: 1 }}>
            <Text style={styles.rowKey}>Test onboarding as a new user</Text>
            <Text style={styles.rowSub}>
              Switch to a fresh test profile to run onboarding and Sleeper / ESPN / MFL linking. Your profile is kept.
            </Text>
          </View>
          <Icon name="chevron-right" color={chalk.dim} size={16} />
        </Pressable>
      ) : null}
    </>
  );
}
