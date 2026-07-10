import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { semantic, type, space } from '../theme/chalkline';
import { Meter } from './chalkline';

interface Props {
  /** 0–100 score. Values outside the range are clamped. */
  value: number;
  /** Caption shown above-left, e.g. "Match strength". Optional. */
  label?: string;
  /** Legacy prop from the sliver-gradient rendering; the Chalkline meter is a
   *  single square-end fill, so this no longer affects output. Kept so call
   *  sites don't break. */
  segments?: number;
  /** Show the numeric value above the bar on the right. Default true. */
  showValue?: boolean;
  /** Tighter variant for use inside dense rows. Default false. */
  compact?: boolean;
}

// Horizontal "match strength" meter (docs/design/components.md → Meters):
// 4px square-end track on ink-3 via the Chalkline Meter primitive, fill and
// numeric callout in the semantic color for where the value lands
// (pos ≥ 70, warn ≥ 40, neg below).
export default function StrengthBar({
  value,
  label = 'Match strength',
  showValue = true,
  compact = false,
}: Props) {
  const safeValue = Math.max(0, Math.min(100, Math.round(value || 0)));
  const fillColor = toneFor(safeValue);

  return (
    <View style={[styles.wrap, compact && styles.wrapCompact]}>
      {(label || showValue) && (
        <View style={styles.headerRow}>
          {label ? <Text style={type.label}>{label}</Text> : <View />}
          {showValue && (
            <Text style={[type.data, { color: fillColor }]}>{safeValue}</Text>
          )}
        </View>
      )}
      <View
        accessibilityRole="progressbar"
        accessibilityValue={{ min: 0, max: 100, now: safeValue }}
        accessibilityLabel={label}
      >
        <Meter value={safeValue / 100} color={fillColor} />
      </View>
    </View>
  );
}

// Semantic tone for the fill + numeric callout (same thresholds as the
// legacy red→yellow→green callout).
function toneFor(v: number): string {
  if (v >= 70) return semantic.pos;
  if (v >= 40) return semantic.warn;
  return semantic.neg;
}

const styles = StyleSheet.create({
  wrap: { gap: space.sm },
  wrapCompact: { gap: space.xs },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
  },
});
