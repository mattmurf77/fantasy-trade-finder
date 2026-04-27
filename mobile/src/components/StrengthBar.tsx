import React, { useMemo } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';

interface Props {
  /** 0–100 score. Values outside the range are clamped. */
  value: number;
  /** Caption shown above-left, e.g. "Match strength". Optional. */
  label?: string;
  /** Number of slivers used to fake a gradient. 24 looks smooth at typical
   *  card widths; lower values feel more "stepped." */
  segments?: number;
  /** Show the numeric value above the bar on the right. Default true. */
  showValue?: boolean;
  /** Tighter variant for use inside dense rows. Default false. */
  compact?: boolean;
}

// Horizontal "match strength" bar with a left→right red→yellow→green
// gradient. Implemented as N small slivers because we don't ship
// expo-linear-gradient (every native module is one more version to keep
// in lock-step with the SDK).
//
// - Filled slivers carry the interpolated color at THAT position on the
//   spectrum. So a 30%-strength bar shows red → reddish-orange and stops.
// - Unfilled slivers fade to a low-opacity track color so the bar still
//   reads as a track even when nearly empty.
export default function StrengthBar({
  value,
  label = 'Match strength',
  segments = 24,
  showValue = true,
  compact = false,
}: Props) {
  const safeValue = Math.max(0, Math.min(100, Math.round(value || 0)));
  const filledCount = Math.round((safeValue / 100) * segments);

  // Pre-compute color stops — cheap, but useMemo keeps re-render quiet.
  const segmentColors = useMemo(() => {
    return Array.from({ length: segments }, (_, i) =>
      interpolateRYG(i / Math.max(1, segments - 1)),
    );
  }, [segments]);

  return (
    <View style={[styles.wrap, compact && styles.wrapCompact]}>
      {(label || showValue) && (
        <View style={styles.headerRow}>
          {label ? <Text style={styles.label}>{label}</Text> : <View />}
          {showValue && (
            <Text style={[styles.value, valueTone(safeValue)]}>
              {safeValue}
            </Text>
          )}
        </View>
      )}
      <View
        style={[styles.track, compact && styles.trackCompact]}
        accessibilityRole="progressbar"
        accessibilityValue={{ min: 0, max: 100, now: safeValue }}
        accessibilityLabel={label}
      >
        {Array.from({ length: segments }, (_, i) => {
          const isFilled = i < filledCount;
          return (
            <View
              key={i}
              style={[
                styles.seg,
                {
                  backgroundColor: isFilled
                    ? segmentColors[i]
                    : 'rgba(255,255,255,0.06)',
                },
              ]}
            />
          );
        })}
      </View>
    </View>
  );
}

// ── Color math ───────────────────────────────────────────────────────
// Stops at red (#ef4444) → yellow (#facc15) → green (#22c55e). Linear in
// each leg; close enough to a perceptually-smooth ramp for a UI accent.
function interpolateRYG(t: number): string {
  const RED    = [0xef, 0x44, 0x44];
  const YELLOW = [0xfa, 0xcc, 0x15];
  const GREEN  = [0x22, 0xc5, 0x5e];
  const lerp = (a: number, b: number, k: number) => Math.round(a + (b - a) * k);
  let r: number, g: number, b: number;
  if (t < 0.5) {
    const k = t * 2;
    r = lerp(RED[0], YELLOW[0], k);
    g = lerp(RED[1], YELLOW[1], k);
    b = lerp(RED[2], YELLOW[2], k);
  } else {
    const k = (t - 0.5) * 2;
    r = lerp(YELLOW[0], GREEN[0], k);
    g = lerp(YELLOW[1], GREEN[1], k);
    b = lerp(YELLOW[2], GREEN[2], k);
  }
  return `rgb(${r},${g},${b})`;
}

// Tint the numeric callout to match where the value lands on the spectrum.
function valueTone(v: number) {
  if (v >= 70) return { color: '#22c55e' };
  if (v >= 40) return { color: '#facc15' };
  return { color: '#ef4444' };
}

const styles = StyleSheet.create({
  wrap: { gap: 6 },
  wrapCompact: { gap: 4 },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
  },
  label: {
    color: colors.muted,
    fontSize: fontSize.xs,
    fontWeight: '700',
    letterSpacing: 0.3,
    textTransform: 'uppercase',
  },
  value: {
    fontSize: fontSize.lg,
    fontWeight: '800',
    letterSpacing: -0.3,
  },
  track: {
    flexDirection: 'row',
    height: 10,
    borderRadius: radius.pill,
    overflow: 'hidden',
    backgroundColor: 'rgba(255,255,255,0.04)',
    gap: 2,
    padding: 1,
  },
  trackCompact: { height: 8 },
  seg: {
    flex: 1,
    borderRadius: 1.5,
  },
});
