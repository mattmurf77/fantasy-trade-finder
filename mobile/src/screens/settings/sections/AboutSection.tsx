// Settings § About — Help & FAQ, Your feedback, Privacy Policy, Terms of Use,
// data credits, Version.
//
// Lifted verbatim from SettingsScreen.tsx (origin/main) `aboutSection` at
// :1416-1458, plus:
//   • :103  helpSurfaceEnabled = useFlag('ux.help_surface')
//   • :82   WEB_ORIGIN
//
// TickLabel: renders `<TickLabel>About</TickLabel>`, matching the shipped
// screen, so the Phase 0 flat list is unchanged. Plan §3 gives the Phase 2 host
// page the title "Help & about"; the banner is expected to move to the page
// header then.
//
// Intentional behavior changes — exactly one, and it is an addition:
//   • NEW "Version" row at the end (plan §4 / finding F7: "No version/build
//     row … support triage needs it"). Read from `expo-constants` — the same
//     source Sentry's release tag and useWhatsNew's key use, so it can never
//     drift from the shipped build. testID `settings.version`.
//     Rendering rules: version + build → "1.14.0 (1)"; only one known → that
//     value alone; neither known → the row is not rendered at all. The row
//     never prints "undefined". The value uses the Chalkline `data` type
//     (IBM Plex Mono, tabular numerals) because numerals that represent data
//     are always mono (docs/design/design-system.md).
// No queries, no loading state, so there is nothing to place a per-section
// placeholder against.
//
// Note: this module takes no `SettingsSectionProps`. Every row but one opens
// an external URL via Linking; the "Your feedback" row (#354 BL-10, D-3:
// moved here from the tester-only TestingSection so every user can reach the
// inbox) is the one in-app push, and it reads `useNavigation()` itself so the
// host page needs no notice surface or navigate prop for a single row.

import React from 'react';
import { View, Text, Pressable, Linking } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import Constants from 'expo-constants';

import { chalk, type } from '../../../theme/chalkline';
import { TickLabel, Icon } from '../../../components/chalkline';
import { useFlag } from '../../../state/useFeatureFlags';
import { styles } from '../styles';

const WEB_ORIGIN = 'https://fantasy-trade-finder.onrender.com';

/** Marketing version ("1.14.0") and iOS build number ("1"), whichever are
 *  present in the running build's manifest. Both are optional in the
 *  expo-constants types, so both are treated as possibly-absent. */
function appVersionLabel(): string | null {
  const version = Constants.expoConfig?.version ?? null;
  const build = Constants.expoConfig?.ios?.buildNumber ?? null;
  if (version && build) return `${version} (${build})`;
  return version ?? build ?? null;
}

export default function AboutSection() {
  const navigation = useNavigation<any>();
  const helpSurfaceEnabled = useFlag('ux.help_surface');
  const versionLabel = appVersionLabel();

  return (
    <>
      <View style={styles.section}>
        <TickLabel>About</TickLabel>
      </View>
      {/* In-app help surface (teardown 04-01, flag `ux.help_surface`) —
          the web FAQ is the canonical "how does this work" doc. */}
      {helpSurfaceEnabled ? (
        <Pressable
          testID="settings.help-faq"
          accessibilityRole="link"
          accessibilityHint="Opens in your browser"
          onPress={() => Linking.openURL(`${WEB_ORIGIN}/faq.html`)}
          style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
        >
          <View style={{ flex: 1 }}>
            <Text style={styles.rowKey}>Help & FAQ</Text>
            <Text style={styles.rowSub}>
              How rankings, matches, and trade values work.
            </Text>
          </View>
          <Icon name="chevron-right" color={chalk.dim} size={16} />
        </Pressable>
      ) : null}
      {/* #354 BL-10 (D-3): public home of the feedback inbox. Unflagged (D-4). */}
      <Pressable
        testID="settings.feedback-inbox"
        accessibilityRole="button"
        onPress={() => navigation.navigate('FeedbackInbox')}
        style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
      >
        <View style={{ flex: 1 }}>
          <Text style={styles.rowKey}>Your feedback</Text>
          <Text style={styles.rowSub}>
            Notes you've sent with the flag button, and where each one stands.
          </Text>
        </View>
        <Icon name="chevron-right" color={chalk.dim} size={16} />
      </Pressable>
      <Pressable
        accessibilityRole="link"
        accessibilityHint="Opens in your browser"
        onPress={() => Linking.openURL(`${WEB_ORIGIN}/privacy`)}
        style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
      >
        <Text style={[styles.rowKey, { flex: 1 }]}>Privacy Policy</Text>
        <Icon name="chevron-right" color={chalk.dim} size={16} />
      </Pressable>
      <Pressable
        accessibilityRole="link"
        accessibilityHint="Opens in your browser"
        onPress={() => Linking.openURL(`${WEB_ORIGIN}/terms`)}
        style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
      >
        <Text style={[styles.rowKey, { flex: 1 }]}>Terms of Use</Text>
        <Icon name="chevron-right" color={chalk.dim} size={16} />
      </Pressable>
      {/* Data credits (LEG-S3; legal-lead-drafts.md Part 3, wording verbatim).
          Q5b: no league platform is named here. */}
      <Pressable
        accessibilityRole="link"
        accessibilityHint="Opens in your browser"
        onPress={() => Linking.openURL('https://github.com/nflverse/nfldata')}
        style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
      >
        <View style={{ flex: 1 }}>
          <Text style={styles.rowKey}>
            Data by nflverse (https://github.com/nflverse/nfldata), CC-BY
          </Text>
          <Text style={styles.rowSub}>
            Consensus values from DynastyProcess and other published sources.
          </Text>
        </View>
        <Icon name="chevron-right" color={chalk.dim} size={16} />
      </Pressable>
      {/* F7 — the build the user is actually running, for support triage. */}
      {versionLabel ? (
        <View testID="settings.version" style={styles.kvRow}>
          <Text style={styles.rowKey}>Version</Text>
          <Text style={type.data}>{versionLabel}</Text>
        </View>
      ) : null}
    </>
  );
}
