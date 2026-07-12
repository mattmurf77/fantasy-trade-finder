import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { chalk, radii, type, tier as tierColors } from '../theme/chalkline';
import type { Tier } from '../shared/types';

interface Props {
  tier: Tier | null | undefined;
  // Optional accompanying position-rank label, e.g. "QB4"
  posRank?: string;
  size?: 'sm' | 'md';
}

// Pick-value tier ladder labels (docs/cross-client-invariants.md).
const TIER_LABEL: Record<Tier, string> = {
  firsts_4plus: '4+ 1sts',
  firsts_3: '3 1sts',
  firsts_2: '2 1sts',
  first_1: '1st',
  second: '2nd',
  third: '3rd',
  fourth: '4th',
  waivers: 'Waivers',
};

// Chalkline badge construction (docs/design/components.md → Badges & chips):
// transparent bg, 1px border in the tier color, chalk text, radius xs.
// Used on Tiers + Trades + Matches screens. Graceful no-op when `tier` is
// falsy so call sites don't have to guard.
export default function TierBadge({ tier, posRank, size = 'md' }: Props) {
  if (!tier) return null;
  const borderColor = tierColors[tier];
  const isSm = size === 'sm';
  const label = posRank ? `${TIER_LABEL[tier]} · ${posRank}` : TIER_LABEL[tier];
  return (
    <View style={[styles.badge, isSm && styles.badgeSm, { borderColor }]}>
      <Text style={[type.label, styles.text]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radii.xs,
    borderWidth: 1,
    alignSelf: 'flex-start',
  },
  badgeSm: { paddingHorizontal: 4, paddingVertical: 1 },
  text: { color: chalk.base },
});
