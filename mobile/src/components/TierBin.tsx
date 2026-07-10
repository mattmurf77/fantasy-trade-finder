import React, { forwardRef } from 'react';
import { View, Text, StyleSheet, LayoutChangeEvent } from 'react-native';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import { TIER_LABEL } from '../utils/tierBands';
import type { Tier } from '../shared/types';

interface Props {
  tier: Tier | 'unassigned';
  count: number;
  children: React.ReactNode;
  onLayout?: (e: LayoutChangeEvent) => void;
  // Visual highlight while a drag hovers over this bin.
  active?: boolean;
}

// Droppable tier container. Measured via onLayout so the drag gesture
// handler knows its screen bounds and can snap a dropped card into this
// bin. All bins in a TiersScreen share a common layout so measurements
// stay comparable even when content heights differ.
const TierBin = forwardRef<View, Props>(function TierBin(
  { tier, count, children, onLayout, active },
  ref,
) {
  const accent = accentFor(tier);
  const label = tier === 'unassigned' ? 'Unassigned' : TIER_LABEL[tier];
  return (
    <View
      ref={ref}
      onLayout={onLayout}
      style={[
        styles.bin,
        active && { borderColor: accent.border, backgroundColor: accent.bgActive },
      ]}
    >
      <View style={[styles.header, { borderLeftColor: accent.fg }]}>
        <Text style={[styles.label, { color: accent.fg }]}>{label}</Text>
        <Text style={styles.count}>{count}</Text>
      </View>
      <View style={styles.body}>{children}</View>
    </View>
  );
});

export default TierBin;

function accentFor(tier: Tier | 'unassigned') {
  switch (tier) {
    case 'elite':   return { fg: colors.tier.elite,   border: 'rgba(251,191,36,0.45)', bgActive: 'rgba(251,191,36,0.08)' };
    case 'starter': return { fg: colors.tier.starter, border: 'rgba(45,212,191,0.45)', bgActive: 'rgba(45,212,191,0.08)' };
    case 'solid':   return { fg: colors.tier.solid,   border: 'rgba(56,189,248,0.45)', bgActive: 'rgba(56,189,248,0.08)' };
    case 'depth':   return { fg: colors.tier.depth,   border: 'rgba(244,114,182,0.45)', bgActive: 'rgba(244,114,182,0.08)' };
    case 'bench':   return { fg: colors.tier.bench,   border: 'rgba(122,127,150,0.45)', bgActive: 'rgba(122,127,150,0.08)' };
    default:        return { fg: colors.muted,        border: colors.border,           bgActive: 'rgba(255,255,255,0.04)' };
  }
}

const styles = StyleSheet.create({
  bin: {
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    marginBottom: spacing.sm,
    overflow: 'hidden',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderLeftWidth: 3,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  label: { fontSize: fontSize.sm, fontWeight: '800', letterSpacing: 0.4 },
  count: { color: colors.muted, fontSize: fontSize.xs, fontWeight: '700' },
  body: { padding: spacing.sm, gap: spacing.xs, minHeight: 50 },
});
