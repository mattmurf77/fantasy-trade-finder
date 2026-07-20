import React from 'react';
import { Text as RNText, TextProps } from 'react-native';
import { type as typeStyles, maxFontScale, typeMaxFontScale } from '../../theme/chalkline';
import { useFlag } from '../../state/useFeatureFlags';

// Chalkline Text primitive — the ONE place Dynamic Type policy lives
// (teardown S2 PRD-01, flag `a11y.text_scaling`).
//
// Flag ON:  applies a per-style `maxFontSizeMultiplier` cap so OS text-size
//           settings scale copy generously (body/controls ×2.0) while dense
//           data rows and decorative display type stay inside their fixed
//           layouts (×1.35 / ×1.2). Tiers come from theme/chalkline.ts →
//           `maxFontScale` / `typeMaxFontScale`.
// Flag OFF: renders exactly like RN's Text today — no multiplier cap,
//           unlimited OS scaling (current behavior, pixel-identical).
//
// Usage:
//   <Text variant="body">…</Text>          — token style + its default cap
//   <Text scale="dense" style={s.tag}>…    — custom style, explicit cap tier
//   <Text style={s.name}>…                 — custom style, defaults to `body` tier
//
// Wave-2/3 screen migrations: swap `import { Text } from 'react-native'` for
// `import { Text } from '../components/chalkline'` and pick a `scale` tier
// (or `variant`) per usage. Don't hand-write maxFontSizeMultiplier anywhere.

export type TypeVariant = keyof typeof typeStyles;
export type ScaleTier = keyof typeof maxFontScale;

export interface ChalkTextProps extends TextProps {
  /** Chalkline type-token style to apply (display/heading/label/…). */
  variant?: TypeVariant;
  /** Dynamic Type cap tier. Defaults to the variant's tier, else `body`. */
  scale?: ScaleTier;
}

export default function Text({ variant, scale, style, ...rest }: ChalkTextProps) {
  const scalingOn = useFlag('a11y.text_scaling');
  const tier: ScaleTier = scale ?? (variant ? typeMaxFontScale[variant] : 'body');
  // Teardown S8 PRD-01 (inert a11y, unflagged): the display/heading variants
  // are section titles by construction — give them the VoiceOver header trait
  // so rotor heading-navigation works app-wide. Callers can still override
  // via an explicit accessibilityRole in `rest`.
  const headerRole =
    variant === 'display' || variant === 'heading' ? ('header' as const) : undefined;
  return (
    <RNText
      maxFontSizeMultiplier={scalingOn ? maxFontScale[tier] : undefined}
      accessibilityRole={headerRole}
      style={variant ? [typeStyles[variant], style] : style}
      {...rest}
    />
  );
}
