import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { ink, ice, semantic, type, space } from '../../theme/chalkline';

interface Props {
  /** 0–1 fill fraction. Fairness meters receive fairness_score directly (invariant: ×100 for display only). */
  value: number;
  /** Fill color; defaults to ice (coverage). */
  color?: string;
  /** Optional left label (rendered as Chalkline label type). */
  label?: string;
  /** Show the value as a right-aligned mono percentage. */
  showPercent?: boolean;
}

// Chalkline meter: 4px track, square ends (chalk lines, not pills).
export default function Meter({ value, color = ice.base, label, showPercent = false }: Props) {
  const clamped = Math.max(0, Math.min(1, value));
  return (
    <View style={styles.row}>
      {label ? <Text style={type.label}>{label}</Text> : null}
      <View style={styles.track}>
        <View style={[styles.fill, { width: `${clamped * 100}%`, backgroundColor: color }]} />
      </View>
      {showPercent ? <Text style={type.data}>{Math.round(clamped * 100)}%</Text> : null}
    </View>
  );
}

/** Fairness color ramp per docs/design/components.md → FairnessMeter. */
export function fairnessColor(value: number): string {
  if (value >= 0.8) return semantic.pos;
  if (value >= 0.6) return semantic.warn;
  return semantic.neg;
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
  },
  track: {
    flex: 1,
    height: 4,
    backgroundColor: ink.ink3,
  },
  fill: {
    height: 4,
  },
});
