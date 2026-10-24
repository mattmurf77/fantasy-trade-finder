import React, { useEffect } from 'react';
import { Linking, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Constants from 'expo-constants';
import { Button, Text } from '../components/chalkline';
import { ink, space } from '../theme/chalkline';
import { track } from '../api/events';
import { versionInt } from '../utils/appVersion';

// ── B8 minimum-version gate — the blocking "Update required" screen ──────
// Head-eng ruling 35. App.tsx renders this IN PLACE OF RootNav (so nothing
// beneath it can be reached, modals included) when shouldBlockForUpdate(
// the flag store's appMinVersion, APP_VERSION_INT) is true. The decision
// and every fail-open path live in utils/appVersion + state/useFeatureFlags;
// this file only draws the wall and fires the gate's two events.
//
// No FeedbackFAB: a blocking gate is in the modal/onboarding exception class
// (root CLAUDE.md #188). Construction = components.md EmptyState (heading +
// body-sm + one Primary button) on ink-0. One ice use.
//
// Pinned by mobile/tests/check-update-gate.js.

/** The build's own version int (utils/appVersion encoding), read the same
 *  way api/client.ts reads X-App-Version. null when unparseable, and then
 *  the gate never blocks. */
export const APP_VERSION_INT = versionInt(Constants.expoConfig?.version);

/** The App Store listing. The id is the App Store Connect app id
 *  (`ascAppId` in mobile/eas.json → submit.production.ios), which is the
 *  id App Store URLs use. */
export const APP_STORE_URL = 'https://apps.apple.com/app/id6771488431';

// COPY: placeholder, marketing-lead to supply
const COPY = {
  title: 'Update required',
  body: 'This version of Fleeced is no longer supported. Update to keep trading.',
  button: 'Update',
} as const;

interface Props {
  /** The served app_min_version that blocked this build. */
  minVersion: number;
  /** This build's version int (APP_VERSION_INT, non-null whenever blocked). */
  appVersionInt: number;
}

export default function UpdateGateScreen({ minVersion, appVersionInt }: Props) {
  // Once per gate show: this screen mounts only after a resolved flag fetch
  // raised the gate, and stays mounted while later fetches keep it raised.
  useEffect(() => {
    track('update_gate_shown', { min_version: minVersion, app_version_int: appVersionInt });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onUpdate = () => {
    track('update_gate_tapped', { min_version: minVersion, app_version_int: appVersionInt });
    Linking.openURL(APP_STORE_URL).catch(() => {});
  };

  return (
    <SafeAreaView style={styles.root} testID="update-gate.screen">
      <View style={styles.body}>
        <Text variant="heading" style={styles.title}>
          {COPY.title}
        </Text>
        <Text variant="bodySm" style={styles.line}>
          {COPY.body}
        </Text>
        <Button label={COPY.button} onPress={onUpdate} testID="update-gate.update" />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: ink.ink0,
  },
  body: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: space.xl,
  },
  title: {
    textAlign: 'center',
    marginBottom: space.sm,
  },
  line: {
    textAlign: 'center',
    marginBottom: space.xl,
  },
});
