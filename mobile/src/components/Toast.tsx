import React, { useEffect } from 'react';
import { AccessibilityInfo, StyleSheet, Text, Pressable, View } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  runOnJS,
} from 'react-native-reanimated';
import { ink, chalk, ice, semantic, space, radii, type, fonts, shadowSheet } from '../theme/chalkline';
import { useFlag } from '../state/useFeatureFlags';
import { useReducedMotionSafe } from '../hooks/useReducedMotionSafe';

interface Props {
  visible: boolean;
  message: string;
  tone?: 'default' | 'success' | 'warn' | 'error';
  onDismiss?: () => void;
  /** total time visible; 0 = persist until dismissed */
  holdMs?: number;
  /** Optional trailing action button (teardown S3 PRD-03 — e.g. Undo).
   *  Pressing it fires `onPress` then dismisses the toast. */
  action?: { label: string; onPress: () => void };
}

// Animated toast banner. Fades in/out, optionally auto-dismisses. Used
// by RankScreen for the QC "Nice call!" compliment (flag swipe.qc_compliments)
// and by other screens for lightweight status feedback.
//
// Chalkline: ink-2 surface, hairline border, sheet shadow, 3px left rail in
// the tone color (ice info / pos success / warn / neg error).
//
// Teardown S4 PRD-03 (flag `ux.toast_v2`): tone-based hold — warn/error
// toasts persist ≥5s (or sticky when holdMs=0) so recovery instructions are
// readable; success/default keep the 1.5s default. Unflagged: every show is
// announced to VoiceOver (inert for sighted users), and the slide-in falls
// back to a pure fade under Reduce Motion (`useReducedMotionSafe`, itself
// dark behind `a11y.reduce_motion`).

const ERROR_MIN_HOLD_MS = 5000;

export default function Toast({
  visible,
  message,
  tone = 'default',
  onDismiss,
  holdMs = 1500,
  action,
}: Props) {
  const opacity = useSharedValue(0);
  const translateY = useSharedValue(-20);
  const toastV2 = useFlag('ux.toast_v2');
  const reduceMotion = useReducedMotionSafe();

  // Tone-based hold (flag-gated): warn/error persist ≥5s or sticky.
  const effectiveHoldMs =
    toastV2 && (tone === 'warn' || tone === 'error')
      ? holdMs === 0
        ? 0
        : Math.max(holdMs, ERROR_MIN_HOLD_MS)
      : holdMs;

  // Inert a11y: announce every toast to the screen reader on show. No-op
  // for sighted users; unflagged by design (S4 PRD-03 item 2).
  useEffect(() => {
    if (visible && message) {
      AccessibilityInfo.announceForAccessibility(message);
    }
  }, [visible, message]);

  useEffect(() => {
    if (visible) {
      opacity.value = withTiming(1, { duration: 180 });
      translateY.value = reduceMotion ? 0 : withTiming(0, { duration: 220 });
      if (effectiveHoldMs > 0 && onDismiss) {
        const t = setTimeout(() => {
          opacity.value = withTiming(0, { duration: 220 }, (finished) => {
            if (finished && onDismiss) runOnJS(onDismiss)();
          });
          if (!reduceMotion) {
            translateY.value = withTiming(-20, { duration: 220 });
          }
        }, effectiveHoldMs);
        return () => clearTimeout(t);
      }
    } else {
      opacity.value = withTiming(0, { duration: 180 });
      translateY.value = reduceMotion ? -20 : withTiming(-20, { duration: 180 });
    }
  }, [visible, effectiveHoldMs, onDismiss, opacity, translateY, reduceMotion]);

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
        {action ? (
          <Pressable
            onPress={() => {
              action.onPress();
              onDismiss?.();
            }}
            accessibilityRole="button"
            accessibilityLabel={action.label}
            hitSlop={{ top: 8, bottom: 8, left: 4, right: 8 }}
            style={({ pressed }) => [styles.actionBtn, pressed && styles.actionBtnPressed]}
          >
            <Text style={styles.actionText}>{action.label}</Text>
          </Pressable>
        ) : null}
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
    flexShrink: 1,
    paddingHorizontal: space.lg,
    paddingVertical: space.sm + 2,
  },
  // Trailing action (Undo) — ice text on a hairline-separated well; the
  // 44pt effective target comes from the row height + hitSlop.
  actionBtn: {
    justifyContent: 'center',
    paddingHorizontal: space.md,
    borderLeftWidth: 1,
    borderLeftColor: ink.line,
  },
  actionBtnPressed: { backgroundColor: ink.ink3 },
  actionText: {
    fontFamily: fonts.uiSemi,
    fontSize: 14,
    color: ice.base,
  },
});
