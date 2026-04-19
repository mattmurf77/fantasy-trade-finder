import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors } from '../theme/colors';
import { radius, fontSize } from '../theme/spacing';
import type { Tier } from '../shared/types';

interface Props {
  tier: Tier | null | undefined;
  // Optional accompanying position-rank label, e.g. "QB4"
  posRank?: string;
  size?: 'sm' | 'md';
}

const TIER_LABEL: Record<Tier, string> = {
  elite: 'Elite',
  starter: 'Starter',
  solid: 'Solid',
  depth: 'Depth',
  bench: 'Bench',
};

// Visual tier indicator mirroring the Chrome extension's .ftf-badge pill.
// Used on Tiers + Trades + Matches screens (Phase 3-4). Graceful no-op
// when `tier` is falsy so call sites don't have to guard.
export default function TierBadge({ tier, posRank, size = 'md' }: Props) {
  if (!tier) return null;
  const c = tint(tier);
  const isSm = size === 'sm';
  const label = posRank ? `${TIER_LABEL[tier]} · ${posRank}` : TIER_LABEL[tier];
  return (
    <View
      style={[
        styles.badge,
        isSm && styles.badgeSm,
        { backgroundColor: c.bg, borderLeftColor: c.fg, borderColor: c.border },
      ]}
    >
      <Text style={[styles.text, isSm && styles.textSm, { color: c.fg }]}>
        {label}
      </Text>
    </View>
  );
}

function tint(t: Tier) {
  switch (t) {
    case 'elite':   return { fg: colors.tier.elite,   bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.35)' };
    case 'starter': return { fg: colors.tier.starter, bg: 'rgba(34,197,94,0.12)',  border: 'rgba(34,197,94,0.35)' };
    case 'solid':   return { fg: colors.tier.solid,   bg: 'rgba(59,130,246,0.12)', border: 'rgba(59,130,246,0.35)' };
    case 'depth':   return { fg: colors.tier.depth,   bg: 'rgba(249,115,22,0.12)', border: 'rgba(249,115,22,0.35)' };
    case 'bench':   return { fg: colors.tier.bench,   bg: 'rgba(148,163,184,0.12)',border: 'rgba(148,163,184,0.35)' };
  }
}

const styles = StyleSheet.create({
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderLeftWidth: 3,
    alignSelf: 'flex-start',
  },
  badgeSm: { paddingHorizontal: 6, paddingVertical: 2 },
  text: { fontSize: fontSize.xs, fontWeight: '700', letterSpacing: 0.3 },
  textSm: { fontSize: 10 },
});
