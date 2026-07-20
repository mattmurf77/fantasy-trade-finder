import React from 'react';
import { View, StyleSheet, Platform } from 'react-native';
import { ink, chalk, fonts, radii, space } from '../theme/chalkline';
import { Text } from './chalkline';
import { useFlag } from '../state/useFeatureFlags';

// FB4-63 — pinned banner that shows the tier of the topmost VISIBLE player
// as the user scrolls the Tiers list. Presentational only: TiersScreen
// derives the label/accent/count from `onViewableItemsChanged` and passes
// them in. Styled like the inline tier header but visually distinct as a
// floating banner (raised ink-2 surface).
//
// Teardown S2 PRD-03: ported to Chalkline behind `visual.chalkline_cleanup` —
// ink-2 raised fill + hairline (surface step, no off-token shadow on a
// non-sheet element), radius r-sm, Plex Mono count in chalk-dim. The 4px
// left border stays: tier color is a data encoding. Flag off renders the
// pre-teardown look via the LEGACY_* constants (theme/colors.ts no longer
// exports chrome hexes); delete the legacy branch at flag cleanup.

export interface TierStickyHeaderProps {
  label: string;
  accent: string;
  count: number;
}

function TierStickyHeader({ label, accent, count }: TierStickyHeaderProps) {
  const cleanup = useFlag('visual.chalkline_cleanup');
  if (cleanup) {
    return (
      <View style={[styles.banner, { borderLeftColor: accent }]}>
        <Text scale="dense" style={[styles.label, { color: accent }]} numberOfLines={1}>
          {label}
        </Text>
        <Text scale="dense" style={styles.count}>{count}</Text>
      </View>
    );
  }
  return (
    <View style={[legacyStyles.banner, { borderLeftColor: accent }]}>
      <Text scale="dense" style={[legacyStyles.label, { color: accent }]} numberOfLines={1}>
        {label}
      </Text>
      <Text scale="dense" style={legacyStyles.count}>{count}</Text>
    </View>
  );
}

export default React.memo(TierStickyHeader);

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginHorizontal: space.lg,
    marginTop: space.xs,
    paddingVertical: space.xs + 2,
    paddingHorizontal: space.md,
    borderLeftWidth: 4,
    borderRadius: radii.sm,
    backgroundColor: ink.ink2, // raised step — distinct from the ink-1 tiles below
    borderWidth: 1,
    borderColor: ink.line,
  },
  label: {
    fontFamily: fonts.uiSemi,
    fontSize: 13,
    letterSpacing: 0.4,
  },
  count: {
    fontFamily: fonts.data,
    fontSize: 11,
    fontVariant: ['tabular-nums'],
    color: chalk.dim,
  },
});

// ── Legacy branch (flag off) — pre-teardown rendering, byte-for-byte ────────
// DELETE when `visual.chalkline_cleanup` is removed.
const LEGACY = {
  surface: '#1a1d27',
  border: '#2a2d3a',
  muted: '#7a7f96',
} as const;

const legacyStyles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginHorizontal: 16,
    marginTop: 4,
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderLeftWidth: 4,
    borderRadius: 10,
    backgroundColor: LEGACY.surface,
    borderWidth: 1,
    borderColor: LEGACY.border,
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
  label: { fontSize: 13, fontWeight: '800', letterSpacing: 0.4 },
  count: { color: LEGACY.muted, fontSize: 11, fontWeight: '700' },
});
