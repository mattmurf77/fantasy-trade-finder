// Platform link CTAs — "Link an ESPN league" and the MFL/Fleaflicker chooser.
//
// Extracted verbatim from SettingsScreen.tsx (origin/main):
//   • `platformLinkRows`  :836-882
//   • the three flags it reads: `espn.link` :250, `mfl.link` :260,
//     `fleaflicker.link` :261
//
// SECTION BANNER: none. The host page owns the <TickLabel>Leagues</TickLabel>
// (plan §3 — these rows sit under Leagues on `SettingsLeagues`, as they do in
// today's flat v2 list at SettingsScreen.tsx:1487). Rows only.
//
// Behavior changes: none. `navigateFromSettings` becomes the `navigate` prop;
// both flags are read locally, so there is no data to wait on and no loading
// state to render.

import React from 'react';
import { Pressable, Text, View } from 'react-native';

import { chalk } from '../../../theme/chalkline';
import { Icon } from '../../../components/chalkline';
import { useFlag } from '../../../state/useFeatureFlags';
import { styles } from '../styles';
import type { SettingsSectionProps } from './types';

export default function PlatformLinkSection({ navigate }: SettingsSectionProps) {
  // #130 — ESPN-link CTA row (flag `espn.link`): routes to the LeaguePicker
  // with the EspnLinkSheet auto-opened (the one place the import flow lives).
  const espnLinkEnabled = useFlag('espn.link');
  // Zero-auth platforms (MFL / Fleaflicker) share one CTA → the LeaguePicker
  // platform chooser, where each flag-gated link button lives.
  const mflLinkEnabled = useFlag('mfl.link');
  const fleaflickerLinkEnabled = useFlag('fleaflicker.link');

  return (
    <>
      {/* #130 — flag-gated ESPN link entry. Reuses the LeaguePicker's
          EspnLinkSheet flow (espnLink param auto-opens it) rather than
          re-hosting the sheet here. */}
      {espnLinkEnabled ? (
        <Pressable
          testID="settings.link-espn"
          accessibilityRole="button"
          onPress={() => navigate('LeaguePicker', { espnLink: true })}
          style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
        >
          <View style={{ flex: 1 }}>
            <Text style={styles.rowKey}>Link an ESPN league</Text>
            <Text style={styles.rowSub}>
              Read-only import: rankings, tiers, and trios work today.
            </Text>
          </View>
          <Icon name="chevron-right" color={chalk.dim} size={16} />
        </Pressable>
      ) : null}
      {/* MFL / Fleaflicker link entry (flags `mfl.link` / `fleaflicker.link`).
          Both are zero-auth, so one row routes to the LeaguePicker chooser
          where the per-platform buttons live. */}
      {mflLinkEnabled || fleaflickerLinkEnabled ? (
        <Pressable
          testID="settings.link-platform"
          accessibilityRole="button"
          onPress={() => navigate('LeaguePicker')}
          style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
        >
          <View style={{ flex: 1 }}>
            <Text style={styles.rowKey}>
              {mflLinkEnabled && fleaflickerLinkEnabled
                ? 'Link an MFL or Fleaflicker league'
                : mflLinkEnabled
                  ? 'Link an MFL league'
                  : 'Link a Fleaflicker league'}
            </Text>
            <Text style={styles.rowSub}>
              Read-only import: rankings, tiers, and trios work today.
            </Text>
          </View>
          <Icon name="chevron-right" color={chalk.dim} size={16} />
        </Pressable>
      ) : null}
    </>
  );
}
