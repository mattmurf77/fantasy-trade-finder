import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { ink, space, radii, type } from '../theme/chalkline';

// Skeleton trade card (onboarding item 4): the first-run deck placeholder
// shown while pregenerated/auto-started cards stream in — replaces the
// manual "Hit 'Find a Trade' to start" empty state on first run. Static by
// design (no shimmer — Chalkline motion budget); the one-line status does
// the narrating.

interface Props {
  status?: string;
  testID?: string;
}

export default function SkeletonTradeCard({
  status = 'Scouting your league. First trades in a few seconds.',
  testID = 'trades.skeleton-card',
}: Props) {
  return (
    <View testID={testID} style={styles.card}>
      <View style={styles.cols}>
        <View style={styles.col}>
          <View style={styles.labelBar} />
          <View style={styles.tile} />
          <View style={styles.tile} />
        </View>
        <View style={styles.col}>
          <View style={styles.labelBar} />
          <View style={styles.tile} />
          <View style={styles.tile} />
        </View>
      </View>
      <View style={styles.meterBar} />
      <Text style={styles.status}>{status}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  // Card construction: ink-1 surface, hairline, radius md.
  card: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    padding: space.lg,
    gap: space.lg,
  },
  cols: {
    flexDirection: 'row',
    gap: space.lg,
  },
  col: {
    flex: 1,
    gap: space.sm,
  },
  // Placeholder blocks — surface steps only, no gradients/shimmer.
  labelBar: {
    width: 88,
    height: 10,
    borderRadius: radii.xs,
    backgroundColor: ink.ink3,
  },
  tile: {
    height: 56,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink2,
  },
  meterBar: {
    height: 4,
    backgroundColor: ink.ink3,
  },
  status: {
    ...type.bodySm,
    textAlign: 'center',
  },
});
