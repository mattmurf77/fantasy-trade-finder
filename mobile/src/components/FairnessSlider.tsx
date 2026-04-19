import React, { useCallback, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  LayoutChangeEvent,
  GestureResponderEvent,
} from 'react-native';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';

interface Props {
  value: number;           // 0.5 – 1.0
  onChange: (v: number) => void;
  min?: number;            // default 0.5
  max?: number;            // default 1.0
}

// Small custom slider to avoid pulling in @react-native-community/slider
// just for one control. Drag the track to set the fairness threshold;
// the value is snapped to 2 decimal places for sanity.
export default function FairnessSlider({ value, onChange, min = 0.5, max = 1 }: Props) {
  const [width, setWidth] = useState(0);
  const trackRef = useRef<View>(null);

  const pct = Math.min(1, Math.max(0, (value - min) / (max - min)));

  const updateFromX = useCallback(
    (x: number) => {
      if (!width) return;
      const clamped = Math.min(width, Math.max(0, x));
      const newPct = clamped / width;
      const v = Math.round((min + newPct * (max - min)) * 100) / 100;
      if (v !== value) onChange(v);
    },
    [value, width, min, max, onChange],
  );

  const onLayout = (e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width);

  const onMove = (e: GestureResponderEvent) => {
    updateFromX(e.nativeEvent.locationX);
  };

  return (
    <View style={styles.wrap}>
      <View style={styles.row}>
        <Text style={styles.label}>Trade fairness</Text>
        <Text style={styles.value}>{Math.round(value * 100)}%</Text>
      </View>
      <View
        ref={trackRef}
        onLayout={onLayout}
        onStartShouldSetResponder={() => true}
        onMoveShouldSetResponder={() => true}
        onResponderGrant={onMove}
        onResponderMove={onMove}
        style={styles.track}
      >
        <View style={[styles.fill, { width: `${pct * 100}%` }]} />
        <View style={[styles.thumb, { left: `${pct * 100}%` }]} />
      </View>
      <View style={styles.row}>
        <Text style={styles.legend}>Lean your way</Text>
        <Text style={styles.legend}>Balanced</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: spacing.xs,
    paddingVertical: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  label: {
    color: colors.muted,
    fontSize: fontSize.xs,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  value: {
    color: colors.accent,
    fontSize: fontSize.base,
    fontWeight: '800',
  },
  track: {
    height: 10,
    backgroundColor: colors.border,
    borderRadius: radius.pill,
    marginVertical: spacing.xs,
    position: 'relative',
    overflow: 'visible',
  },
  fill: {
    height: '100%',
    backgroundColor: colors.accent,
    borderRadius: radius.pill,
  },
  thumb: {
    position: 'absolute',
    top: -6,
    width: 22,
    height: 22,
    marginLeft: -11,
    borderRadius: 11,
    backgroundColor: '#fff',
    borderWidth: 3,
    borderColor: colors.accent,
  },
  legend: {
    color: colors.muted,
    fontSize: 10,
  },
});
