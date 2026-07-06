import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { ice, type, space } from '../../theme/chalkline';

interface Props {
  children: string;
  color?: string; // tick color override (e.g. tier color on TierBin headers)
}

// The brand's smallest unit: 3×14 ice tick + uppercase label.
// Use for section headers, trade-card column headers, sheet titles.
export default function TickLabel({ children, color = ice.base }: Props) {
  return (
    <View style={styles.row}>
      <View style={[styles.tick, { backgroundColor: color }]} />
      <Text style={type.label}>{children}</Text>
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
