import React from 'react';
import { Pressable, Text, StyleSheet, ViewStyle } from 'react-native';
import { ink, chalk, volt, semantic, radii, space, fonts } from '../../theme/chalkline';

type Variant = 'primary' | 'secondary' | 'like' | 'pass' | 'ghost';

interface Props {
  label: string;
  onPress?: () => void;
  variant?: Variant;
  disabled?: boolean;
  compact?: boolean; // 36px instead of 40px
  style?: ViewStyle;
}

// Chalkline button set (docs/design/components.md → Buttons).
// State changes use fill/border color — never scale or translate transforms.
export default function Button({
  label,
  onPress,
  variant = 'primary',
  disabled = false,
  compact = false,
  style,
}: Props) {
  const v = VARIANTS[variant];
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      style={({ pressed }) => [
        styles.base,
        compact && styles.compact,
        {
          backgroundColor: pressed ? v.bgPressed : v.bg,
          borderColor: v.border,
        },
        disabled && styles.disabled,
        style,
      ]}
    >
      {({ pressed }) => (
        <Text style={[styles.label, { color: pressed ? v.textPressed : v.text }]}>
          {label}
        </Text>
      )}
    </Pressable>
  );
}

const VARIANTS = {
  primary: {
    bg: volt.base,
    bgPressed: volt.press,
    border: 'transparent',
    text: volt.on,
    textPressed: volt.on,
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
    height: 44, // touch floor on mobile (web spec is 40)
    minWidth: 44,
    paddingHorizontal: space.lg,
    borderRadius: radii.sm,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  compact: { height: 36 },
  label: {
    fontFamily: fonts.uiSemi,
    fontSize: 14,
  },
  disabled: { opacity: 0.45 },
});
