import React, { forwardRef } from 'react';
import { View, Text, StyleSheet, LayoutChangeEvent } from 'react-native';
import { ink, chalk, radii, space, type, tier as tierColors } from '../theme/chalkline';
import { TickLabel } from './chalkline';
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

// Droppable tier container (docs/design/components.md → Tier bins & boards):
// ink-0 well, 1px DASHED line-strong border; header = tick in the tier color
// + label + mono count. Drag-over flips the border to the tier color, solid.
// Measured via onLayout so the drag gesture handler knows its screen bounds
// and can snap a dropped card into this bin. All bins in a TiersScreen share
// a common layout so measurements stay comparable even when content heights
// differ.
const TierBin = forwardRef<View, Props>(function TierBin(
  { tier, count, children, onLayout, active },
  ref,
) {
  const tickColor = tier === 'unassigned' ? chalk.faint : tierColors[tier];
  const label = tier === 'unassigned' ? 'Unassigned' : TIER_LABEL[tier];
  return (
    <View
      ref={ref}
      onLayout={onLayout}
      style={[
        styles.bin,
        active && { borderColor: tickColor, borderStyle: 'solid' },
      ]}
    >
      <View style={styles.header}>
        <TickLabel color={tickColor}>{label}</TickLabel>
        <Text style={styles.count}>{count}</Text>
      </View>
      <View style={styles.body}>{children}</View>
    </View>
  );
});

export default TierBin;

const styles = StyleSheet.create({
  bin: {
    borderColor: ink.lineStrong,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderRadius: radii.md,
    backgroundColor: ink.ink0,
    marginBottom: space.sm,
    overflow: 'hidden',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: space.sm,
    paddingHorizontal: space.md,
  },
  count: { ...type.data, color: chalk.dim },
  body: { padding: space.sm, gap: space.xs, minHeight: 50 },
});
