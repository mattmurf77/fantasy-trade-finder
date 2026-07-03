import React, { useEffect } from 'react';
import { StyleSheet, Text, Pressable, View } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  runOnJS,
} from 'react-native-reanimated';
import { ink, ice, semantic, space, radii, type, shadowSheet } from '../theme/chalkline';

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
//
// Chalkline: ink-2 surface, hairline border, sheet shadow, 3px left rail in
// the tone color (ice info / pos success / warn / neg error).
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
      <Pressable onPress={onDismiss} style={styles.bubble}>
        <View style={[styles.rail, { backgroundColor: railColor(tone) }]} />
        <Text style={styles.text}>{message}</Text>
      </Pressable>
    </Animated.View>
  );
}

function railColor(tone: NonNullable<Props['tone']>): string {
  switch (tone) {
    case 'success':
      return semantic.pos;
    case 'warn':
      return semantic.warn;
    case 'error':
      return semantic.neg;
    default:
      return ice.base;
  }
}

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    top: space.xxl,
    left: 0,
    right: 0,
    alignItems: 'center',
    zIndex: 50,
  },
  bubble: {
    flexDirection: 'row',
    alignItems: 'stretch',
    backgroundColor: ink.ink2,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.line,
    maxWidth: '88%',
    overflow: 'hidden',
    ...shadowSheet,
  },
  rail: { width: 3 },
  text: {
    ...type.body,
    paddingHorizontal: space.lg,
    paddingVertical: space.sm + 2,
  },
});
