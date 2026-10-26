import React, { useEffect } from 'react';
import { Linking, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Constants from 'expo-constants';
import { Button, Text } from '../components/chalkline';
import { ink, space } from '../theme/chalkline';
import { track } from '../api/events';
import { useFeatureFlags } from '../state/useFeatureFlags';
import { updateGoesToAppStore, versionInt } from '../utils/appVersion';

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

// ── Where Update goes ────────────────────────────────────────────────────
// The same binary serves TestFlight testers first and App Store users from
// the public release. No installed dependency can tell a TestFlight install
// from an App Store one (expo-constants' executionEnvironment is
// 'bare'/'standalone' for both; expo-application is not a dependency). So:
// the served `app_store_live` decides when ops have set it (1 → App Store,
// 0 → TestFlight); unset (-1) falls back to the compiled instant below.

/** Compiled fallback: App Store public release as a UTC instant, midnight
 *  Pacific (PST, UTC-8) on 2026-11-18. Used only while the served
 *  `app_store_live` is unset (utils/appVersion.updateGoesToAppStore). */
export const APP_STORE_LIVE_FROM_UTC = '2026-11-18T08:00:00Z';

/** Opens the TestFlight app, where a tester installs the newer build. The
 *  repo has no public TestFlight link. */
export const TESTFLIGHT_URL = 'itms-beta://';

/** The App Store listing. The id is the App Store Connect app id
 *  (`ascAppId` in mobile/eas.json → submit.production.ios), which is the
 *  id App Store URLs use. */
export const APP_STORE_URL = 'https://apps.apple.com/app/id6771488431';

// Final copy (marketing-lead via head-eng, the b8.* rows).
const UPDATE_GATE_TITLE = 'Update required';
const UPDATE_GATE_BUTTON = 'Update';
// COPY: option (B), operator pick A8 due 11-03
const UPDATE_GATE_BODY = 'This version of the app is out of date. Update to keep using it.';

interface Props {
  /** The served app_min_version that blocked this build. */
  minVersion: number;
  /** This build's version int (APP_VERSION_INT, non-null whenever blocked). */
  appVersionInt: number;
}

export default function UpdateGateScreen({ minVersion, appVersionInt }: Props) {
  // Served Update target (1 / 0 / -1); from the same resolved fetch that
  // raised the gate, so it is never older than the gate itself.
  const servedTarget = useFeatureFlags((s) => s.appStoreLive);

  // Once per gate show: this screen mounts only after a resolved flag fetch
  // raised the gate, and stays mounted while later fetches keep it raised.
  useEffect(() => {
    track('update_gate_shown', { min_version: minVersion, app_version_int: appVersionInt });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A failed or rejected open leaves the gate up: nothing here changes gate
  // state, and both the sync throw and the async rejection are swallowed.
  const onUpdate = () => {
    track('update_gate_tapped', { min_version: minVersion, app_version_int: appVersionInt });
    const url = updateGoesToAppStore(servedTarget, new Date(), APP_STORE_LIVE_FROM_UTC)
      ? APP_STORE_URL
      : TESTFLIGHT_URL;
    try {
      Linking.openURL(url).catch(() => {});
    } catch {
      /* the gate stays up */
    }
  };

  return (
    <SafeAreaView style={styles.root} testID="update-gate.screen">
      <View style={styles.body}>
        <Text variant="heading" style={styles.title}>
          {UPDATE_GATE_TITLE}
        </Text>
        <Text variant="bodySm" style={styles.line}>
          {UPDATE_GATE_BODY}
        </Text>
        <Button label={UPDATE_GATE_BUTTON} onPress={onUpdate} testID="update-gate.update" />
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
