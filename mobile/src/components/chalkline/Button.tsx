import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View, ViewStyle } from 'react-native';
import { ink, chalk, ice, semantic, radii, space, fonts } from '../../theme/chalkline';
import { useFlag } from '../../state/useFeatureFlags';
import Text from './Text';
import Icon, { IconName } from './Icon';

type Variant = 'primary' | 'secondary' | 'like' | 'pass' | 'ghost';

interface Props {
  label: string;
  onPress?: () => void;
  variant?: Variant;
  disabled?: boolean;
  compact?: boolean; // 36px instead of 44px
  /** Optional leading Chalkline icon (16px, label-colored). */
  icon?: IconName;
  /** Replaces the label with a spinner; implies disabled. */
  loading?: boolean;
  style?: ViewStyle;
  testID?: string;   // UI-test harness id (registry: mobile/src/components/CLAUDE.md)
}

// Chalkline button set (docs/design/components.md → Buttons).
// State changes use fill/border color — never scale or translate transforms.
export default function Button({
  label,
  onPress,
  variant = 'primary',
  disabled = false,
  compact = false,
  icon,
  loading = false,
  style,
  testID,
}: Props) {
  // a11y.text_scaling (S2 PRD-01): fixed height → minHeight + padding so the
  // label can wrap/grow at large OS text sizes. Flag off = fixed height,
  // pixel-identical to the pre-flag build.
  const textScaling = useFlag('a11y.text_scaling');
  // ux.touch_polish (S3 PRD-04): the 36px compact variant gets default
  // vertical hitSlop to a 44pt effective target.
  const touchPolish = useFlag('ux.touch_polish');
  // visual.chalkline_cleanup (S2 PRD-04): secondary border at ≥3:1 contrast.
  const cleanup = useFlag('visual.chalkline_cleanup');

  const v = VARIANTS[variant];
  const borderColor =
    variant === 'secondary' && cleanup ? ink.lineStrongA11y : v.border;
  const inactive = disabled || loading;
  return (
    <Pressable
      onPress={onPress}
      disabled={inactive}
      testID={testID}
      accessibilityRole="button"
      accessibilityState={{ disabled: inactive, busy: loading }}
      hitSlop={compact && touchPolish ? { top: 4, bottom: 4 } : undefined}
      style={({ pressed }) => [
        styles.base,
        textScaling
          ? (compact ? styles.growCompact : styles.grow)
          : (compact ? styles.fixedCompact : styles.fixed),
        {
          backgroundColor: pressed ? v.bgPressed : v.bg,
          borderColor,
        },
        inactive && styles.disabled,
        style,
      ]}
    >
      {({ pressed }) =>
        loading ? (
          <ActivityIndicator size="small" color={v.text} />
        ) : (
          <View style={styles.content}>
            {icon ? <Icon name={icon} size={16} color={pressed ? v.textPressed : v.text} /> : null}
            <Text scale="body" style={[styles.label, { color: pressed ? v.textPressed : v.text }]}>
              {label}
            </Text>
          </View>
        )
      }
    </Pressable>
  );
}

const VARIANTS = {
  primary: {
    bg: ice.base,
    bgPressed: ice.press,
    border: 'transparent',
    text: ice.on,
    textPressed: ice.on,
  },
  secondary: {
    bg: 'transparent',
    bgPressed: ink.ink3,
    border: ink.lineStrong,
    text: chalk.base,
    textPressed: chalk.base,
  },
  like: {
    bg: 'transparent',
    bgPressed: semantic.pos,
    border: semantic.pos,
    text: semantic.pos,
    textPressed: ink.ink0,
  },
  pass: {
    bg: 'transparent',
    bgPressed: semantic.neg,
    border: semantic.neg,
    text: semantic.neg,
    textPressed: ink.ink0,
  },
  ghost: {
    bg: 'transparent',
    bgPressed: 'transparent',
    border: 'transparent',
    text: chalk.dim,
    textPressed: chalk.base,
  },
} as const;

const styles = StyleSheet.create({
  base: {
    minWidth: 44,
    paddingHorizontal: space.lg,
    borderRadius: radii.sm,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  // Flag off — today's fixed heights (44 = touch floor on mobile; web spec is 40).
  fixed: { height: 44 },
  fixedCompact: { height: 36 },
  // Flag on — same resting size, but scaled text can grow the button.
  grow: { minHeight: 44, paddingVertical: space.sm },
  growCompact: { minHeight: 36, paddingVertical: space.xs },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  label: {
    fontFamily: fonts.uiSemi,
    fontSize: 14,
  },
  disabled: { opacity: 0.45 },
});
