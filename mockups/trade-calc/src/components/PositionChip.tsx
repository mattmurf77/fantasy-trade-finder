import React from 'react';
import { Text, View, StyleSheet } from 'react-native';
import { Position } from '../data/mock';
import { colors, radius, fontSize } from '../theme';

export function PositionChip({ pos }: { pos: Position }) {
  return (
    <View style={[styles.chip, { backgroundColor: colors.position[pos] + '33' }]}>
      <Text style={[styles.text, { color: colors.position[pos] }]}>{pos}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    borderRadius: radius.sm,
    paddingHorizontal: 6,
    paddingVertical: 2,
    minWidth: 32,
    alignItems: 'center',
  },
  text: {
    fontSize: fontSize.xs,
    fontWeight: '700',
  },
});
