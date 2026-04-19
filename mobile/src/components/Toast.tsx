import React, { useEffect } from 'react';
import { StyleSheet, Text, Pressable } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  runOnJS,
} from 'react-native-reanimated';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';

interface Props {
  visible: boolean;
  message: string;
  tone?: 'default' | 'success' | 'warn' | 'error';
  onDismiss?: () => void;
  /** total time visible; 0 = persist until dismissed */
  holdMs?: number;
}

// Animated toast banner. Fades in/out, optionally auto-dismisses. Used
// by RankScreen for the QC "Nice call!" compliment (flag swipe.qc_compliments)
// and by other screens for lightweight status feedback.
export default function Toast({
  visible,
  message,
  tone = 'default',
  onDismiss,
  holdMs = 1500,
}: Props) {
  const opacity = useSharedValue(0);
  const translateY = useSharedValue(-20);

  useEffect(() => {
    if (visible) {
      opacity.value = withTiming(1, { duration: 180 });
      translateY.value = withTiming(0, { duration: 220 });
      if (holdMs > 0 && onDismiss) {
        const t = setTimeout(() => {
          opacity.value = withTiming(0, { duration: 220 }, (finished) => {
            if (finished && onDismiss) runOnJS(onDismiss)();
          });
          translateY.value = withTiming(-20, { duration: 220 });
        }, holdMs);
        return () => clearTimeout(t);
      }
    } else {
      opacity.value = withTiming(0, { duration: 180 });
      translateY.value = withTiming(-20, { duration: 180 });
    }
  }, [visible, holdMs, onDismiss, opacity, translateY]);

  const animatedStyle = useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ translateY: translateY.value }],
  }));

  if (!visible && opacity.value === 0) return null;

  return (
    <Animated.View
      pointerEvents="box-none"
      style={[styles.wrap, animatedStyle]}
    >
      <Pressable onPress={onDismiss} style={[styles.bubble, toneStyle(tone)]}>
        <Text style={styles.text}>{message}</Text>
      </Pressable>
    </Animated.View>
  );
}

function toneStyle(tone: NonNullable<Props['tone']>) {
  switch (tone) {
    case 'success':
      return { backgroundColor: 'rgba(34,197,94,0.14)', borderColor: 'rgba(34,197,94,0.45)' };
    case 'warn':
      return { backgroundColor: 'rgba(245,158,11,0.14)', borderColor: 'rgba(245,158,11,0.45)' };
    case 'error':
      return { backgroundColor: 'rgba(239,68,68,0.14)', borderColor: 'rgba(239,68,68,0.45)' };
    default:
      return { backgroundColor: colors.surface, borderColor: colors.border };
  }
}

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    top: spacing.xxl,
    left: 0,
    right: 0,
    alignItems: 'center',
    zIndex: 50,
  },
  bubble: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm + 2,
    borderRadius: radius.pill,
    borderWidth: 1,
    maxWidth: '88%',
  },
  text: { color: colors.text, fontSize: fontSize.sm, fontWeight: '600', textAlign: 'center' },
});
