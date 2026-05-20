import React from 'react';
import { View, StyleSheet } from 'react-native';
import { colors } from '../theme/colors';
import { radius } from '../theme/spacing';

interface Props {
  /** Signed delta. Positive paints green (riser), negative paints red (faller). */
  delta: number;
  /** Largest absolute delta in the current section; normalises bar width. */
  max: number;
  /** Optional bar height. Defaults to 4 px. */
  height?: number;
}

// Horizontal magnitude bar for trend rows. Width is |delta| / max, color
// matches the direction. Kept dumb-presentational so any trend list (risers,
// fallers, consensus gap) can reuse it.
export default function TrendBar({ delta, max, height = 4 }: Props) {
  const safeMax = Math.max(1, Math.abs(max));
  const ratio = Math.min(1, Math.abs(delta) / safeMax);
  const widthPct = `${Math.round(ratio * 100)}%` as const;
  const fillColor = delta >= 0 ? colors.green : colors.red;
  return (
    <View style={[styles.track, { height }]}>
      <View style={[styles.fill, { width: widthPct, backgroundColor: fillColor, height }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    width: '100%',
    backgroundColor: colors.border,
    borderRadius: radius.sm,
    overflow: 'hidden',
  },
  fill: {
    borderRadius: radius.sm,
  },
});
