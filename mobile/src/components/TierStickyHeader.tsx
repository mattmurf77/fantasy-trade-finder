import React from 'react';
import { View, Text, StyleSheet, Platform } from 'react-native';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';

// FB4-63 — pinned banner that shows the tier of the topmost VISIBLE player
// as the user scrolls the Tiers list. Presentational only: TiersScreen
// derives the label/accent/count from `onViewableItemsChanged` and passes
// them in. Styled like the inline tier header but visually distinct as a
// floating banner (filled background + shadow).

export interface TierStickyHeaderProps {
  label: string;
  accent: string;
  count: number;
}

function TierStickyHeader({ label, accent, count }: TierStickyHeaderProps) {
  return (
    <View style={[styles.banner, { borderLeftColor: accent }]}>
      <Text style={[styles.label, { color: accent }]} numberOfLines={1}>
        {label}
      </Text>
      <Text style={styles.count}>{count}</Text>
    </View>
  );
}

export default React.memo(TierStickyHeader);

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginHorizontal: spacing.lg,
    marginTop: spacing.xs,
    paddingVertical: spacing.xs + 2,
    paddingHorizontal: spacing.md,
    borderLeftWidth: 4,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    ...Platform.select({
      ios: {
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.25,
        shadowRadius: 4,
      },
      android: { elevation: 3 },
    }),
  },
  label: { fontSize: fontSize.sm, fontWeight: '800', letterSpacing: 0.4 },
  count: { color: colors.muted, fontSize: fontSize.xs, fontWeight: '700' },
});
