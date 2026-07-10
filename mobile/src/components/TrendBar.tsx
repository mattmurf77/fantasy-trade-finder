import React from 'react';
import { View, StyleSheet } from 'react-native';
import { ink, semantic } from '../theme/chalkline';

interface Props {
  /** Signed delta. Positive paints pos (riser), negative paints neg (faller). */
  delta: number;
  /** Largest absolute delta in the current section; normalises bar width. */
  max: number;
  /** Optional bar height. Defaults to 4 px. */
  height?: number;
}

// Horizontal magnitude bar for trend rows (Chalkline meter pattern: square-end
// track on ink-3, no rounding). Width is |delta| / max, color matches the
// direction. Kept dumb-presentational so any trend list (risers, fallers,
// consensus gap) can reuse it.
export default function TrendBar({ delta, max, height = 4 }: Props) {
  const safeMax = Math.max(1, Math.abs(max));
  const ratio = Math.min(1, Math.abs(delta) / safeMax);
  const widthPct = `${Math.round(ratio * 100)}%` as const;
  const fillColor = delta >= 0 ? semantic.pos : semantic.neg;
  return (
    <View style={[styles.track, { height }]}>
      <View style={[{ width: widthPct, backgroundColor: fillColor, height }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    width: '100%',
    backgroundColor: ink.ink3,
    overflow: 'hidden',
  },
});
