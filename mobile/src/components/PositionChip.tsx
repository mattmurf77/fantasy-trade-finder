import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors } from '../theme/colors';
import { radius, fontSize } from '../theme/spacing';
import type { Position } from '../shared/types';

interface Props {
  position: Position | string;
  size?: 'sm' | 'md';
}

// Small colored chip that labels a player by position. Matches the
// web app's .ca-mock-pos style (subtle tinted bg + solid colored text).
// Shared with TiersScreen, TradesScreen, and MatchesScreen later.
export default function PositionChip({ position, size = 'md' }: Props) {
  const pos = (position || '').toUpperCase() as Position;
  const tint = colorFor(pos);
  const isSm = size === 'sm';
  return (
    <View
      style={[
        styles.chip,
        isSm && styles.chipSm,
        { backgroundColor: tint.bg, borderColor: tint.border },
      ]}
    >
      <Text
        style={[styles.text, isSm && styles.textSm, { color: tint.fg }]}
      >
        {pos}
      </Text>
    </View>
  );
}

function colorFor(pos: Position) {
  switch (pos) {
    case 'QB':
      return { fg: colors.position.qb, bg: 'rgba(249,115,22,0.15)', border: 'rgba(249,115,22,0.35)' };
    case 'RB':
      return { fg: colors.position.rb, bg: 'rgba(34,197,94,0.15)',  border: 'rgba(34,197,94,0.35)' };
    case 'WR':
      return { fg: colors.position.wr, bg: 'rgba(59,130,246,0.15)', border: 'rgba(59,130,246,0.35)' };
    case 'TE':
      return { fg: colors.position.te, bg: 'rgba(168,85,247,0.15)', border: 'rgba(168,85,247,0.35)' };
    default:
      return { fg: colors.muted, bg: 'rgba(122,127,150,0.15)', border: colors.border };
  }
}

const styles = StyleSheet.create({
  chip: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: radius.sm,
    borderWidth: 1,
    alignSelf: 'flex-start',
  },
  chipSm: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  text: {
    fontSize: fontSize.xs,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  textSm: { fontSize: 10 },
});
