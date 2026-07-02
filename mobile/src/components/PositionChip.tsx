import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { ink, chalk, radii, type, position } from '../theme/chalkline';
import type { Position } from '../shared/types';

interface Props {
  position: Position | string;
  size?: 'sm' | 'md';
}

// Chalkline badge construction (docs/design/components.md → Badges & chips):
// transparent bg, 1px border in the position color, chalk text, radius xs.
// Shared with TiersScreen, TradesScreen, and MatchesScreen.
export default function PositionChip({ position: positionProp, size = 'md' }: Props) {
  const pos = (positionProp || '').toUpperCase() as Position;
  const borderColor = colorFor(pos);
  const isSm = size === 'sm';
  return (
    <View style={[styles.chip, isSm && styles.chipSm, { borderColor }]}>
      <Text style={[type.label, styles.text]}>{pos}</Text>
    </View>
  );
}

function colorFor(pos: Position): string {
  switch (pos) {
    case 'QB':
      return position.qb;
    case 'RB':
      return position.rb;
    case 'WR':
      return position.wr;
    case 'TE':
      return position.te;
    default:
      return ink.lineStrong;
  }
}

const styles = StyleSheet.create({
  chip: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radii.xs,
    borderWidth: 1,
    alignSelf: 'flex-start',
  },
  chipSm: { paddingHorizontal: 4, paddingVertical: 1 },
  text: { color: chalk.base },
});
