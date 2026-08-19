// Settings § Testing — Test feedback + Test stages (operator QA surface).
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
import { View, Text, Pressable } from 'react-native';

import { chalk } from '../../../theme/chalkline';
import { TickLabel, Icon } from '../../../components/chalkline';
import { useFlag } from '../../../state/useFeatureFlags';
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
  navigate,
  navigateWithoutDismiss,
}: TestingSectionProps) {
  // Operator QA tool (server also allowlist-gates the spawn route). The
  // flag is delivered per-device via the experiment overlay, so it doubles
  // as the tester-allowlist signal for gating the Testing section in v2.
  const stageUsersEnabled = useFlag('testing.stage_users');

  return (
    <>
      <View style={styles.section}>
        <TickLabel>Testing</TickLabel>
      </View>
      <Pressable
        accessibilityRole="button"
        onPress={() => navigate('FeedbackInbox')}
        style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
      >
        <View style={{ flex: 1 }}>
          <Text style={styles.rowKey}>Test feedback</Text>
          <Text style={styles.rowSub}>
            Review and share notes you captured with the floating button.
          </Text>
        </View>
        <Icon name="chevron-right" color={chalk.dim} size={16} />
      </Pressable>
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
    </>
  );
}
