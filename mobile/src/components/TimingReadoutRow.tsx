// Testing readout: the device's last tap-to-first-card time (head-eng
// ruling 11; #339 §9.5's per-tap cross-check for the AC-L1 session).
//
// Self-contained and SAFE TO MOUNT ANYWHERE: it renders nothing unless the
// `testing.timing_readout` flag is on (dark by default; delivered per device
// the way `testing.stage_users` is). onboarding-eng owns the Settings files
// and mounts it there; `useTimingReadoutEnabled` is the hub's entry gate.
//
// The value is R2's `ms_from_tap` (a monotonic performance.now() delta)
// with its AC-L1 cell (network_type, launch_state) and R2's serve_source
// (`device` = a device-held first page, C), held in memory by
// utils/tapTiming — written by the R2 emitter, never sent anywhere.
import React, { useSyncExternalStore } from 'react';
import { StyleSheet, View } from 'react-native';
import { Text } from './chalkline';
import { fonts, ink, space } from '../theme/chalkline';
import { useFlag } from '../state/useFeatureFlags';
import { lastTapTiming, subscribeTapTiming } from '../utils/tapTiming';

/** The Testing readout's gate (also the Settings hub entry's). */
export function useTimingReadoutEnabled(): boolean {
  return useFlag('testing.timing_readout');
}

export function TimingReadoutRow({
  testID = 'settings.testing.timing-readout',
}: { testID?: string }): React.JSX.Element | null {
  const enabled = useTimingReadoutEnabled();
  const timing = useSyncExternalStore(subscribeTapTiming, lastTapTiming);
  if (!enabled) return null;
  const cell = timing
    ? ` ms · ${timing.networkType} · ${timing.launchState}`
      + (timing.serveSource ? ` · ${timing.serveSource}` : '')
    : '';
  const line = timing ? `${timing.msFromTap}${cell}` : 'No trade search yet this session';
  return (
    <View testID={testID} style={styles.row} accessible accessibilityLabel={`Last tap to first card: ${line}`}>
      <Text variant="body">Last tap to first card</Text>
      {timing ? (
        <Text variant="bodySm" style={styles.value}>
          <Text style={styles.ms}>{timing.msFromTap}</Text>
          {cell}
        </Text>
      ) : (
        <Text variant="bodySm" style={styles.value}>{line}</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    paddingVertical: space.md,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  value: { marginTop: space.xs },
  // Plex Mono numerals (data), in the line's chalk-dim.
  ms: { fontFamily: fonts.data, fontVariant: ['tabular-nums'] },
});
