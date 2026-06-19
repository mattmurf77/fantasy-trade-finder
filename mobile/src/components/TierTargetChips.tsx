import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import { TIERS, TIER_LABEL } from '../utils/tierBands';
import type { Tier } from '../shared/types';

// FB4-62 — row of tier-target chips shown in multi-select. Tapping a chip
// asks the parent to move all selected players into that tier. Colors +
// labels come from tierBands (never hardcoded). Presentational only.

export interface TierTargetChipsProps {
  /** Accent color resolver for a tier — passed in so we reuse the
   *  screen's single `accentFor`/theme source. */
  accentFor: (tier: Tier) => string;
  onPick: (tier: Tier) => void;
}

function TierTargetChips({ accentFor, onPick }: TierTargetChipsProps) {
  return (
    <View style={styles.row}>
      <Text style={styles.label}>Move to:</Text>
      <View style={styles.chips}>
        {TIERS.map((t) => {
          const accent = accentFor(t);
          return (
            <Pressable
              key={t}
              onPress={() => onPick(t)}
              style={({ pressed }) => [
                styles.chip,
                { borderColor: accent },
                pressed && { opacity: 0.6 },
              ]}
            >
              <Text style={[styles.chipText, { color: accent }]}>
                {TIER_LABEL[t]}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

export default React.memo(TierTargetChips);

const styles = StyleSheet.create({
  row: {
    marginBottom: spacing.sm,
  },
  label: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
    marginBottom: spacing.xs,
  },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  chip: {
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: radius.md,
    borderWidth: 1,
    backgroundColor: colors.surface,
  },
  chipText: { fontSize: fontSize.xs, fontWeight: '800' },
});
