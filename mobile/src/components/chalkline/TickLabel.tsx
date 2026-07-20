import React from 'react';
import { View, StyleSheet } from 'react-native';
import { ice, type, space } from '../../theme/chalkline';
import Text from './Text';

interface Props {
  children: string;
  color?: string; // tick color override (e.g. tier color on TierBin headers)
}

// The brand's smallest unit: 3×14 ice tick + uppercase label.
// Use for section headers, trade-card column headers, sheet titles.
// Teardown S8 PRD-01 (inert a11y): every TickLabel is a section/column
// header by construction — the header trait makes all of them rotor-
// navigable under VoiceOver in one place.
export default function TickLabel({ children, color = ice.base }: Props) {
  return (
    <View style={styles.row}>
      <View style={[styles.tick, { backgroundColor: color }]} />
      <Text scale="dense" accessibilityRole="header" style={type.label}>{children}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  tick: {
    width: 3,
    height: 14,
  },
});
