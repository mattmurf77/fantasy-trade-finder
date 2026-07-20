import React from 'react';
import { View, StyleSheet, Pressable } from 'react-native';
import { ink, fonts, radii, space, type } from '../theme/chalkline';
import { Text } from './chalkline';
import { useFlag } from '../state/useFeatureFlags';
import { TIERS, TIER_LABEL } from '../utils/tierBands';
import type { Tier } from '../shared/types';

// FB4-62 — row of tier-target chips shown in multi-select. Tapping a chip
// asks the parent to move all selected players into that tier. Colors +
// labels come from tierBands (never hardcoded). Presentational only.
//
// Teardown S2 PRD-03: ported to Chalkline behind `visual.chalkline_cleanup`
// (ink-1 chip fill, radius r-xs, label type at the 11px floor — border+text
// stay in the tier color, a data encoding). Flag off renders the pre-teardown
// look via the LEGACY_* constants; delete that branch at flag cleanup.
// Teardown S3 PRD-04, flag `ux.touch_polish`: chips grow to minHeight 36 with
// gap 8 + 4pt facing-edge hitSlop (≤ gap/2) → ≥44pt effective targets on the
// no-drag accessibility path.

export interface TierTargetChipsProps {
  /** Accent color resolver for a tier — passed in so we reuse the
   *  screen's single `accentFor`/theme source. */
  accentFor: (tier: Tier) => string;
  onPick: (tier: Tier) => void;
}

const TOUCH_HIT_SLOP = { top: 4, bottom: 4, left: 4, right: 4 } as const;

function TierTargetChips({ accentFor, onPick }: TierTargetChipsProps) {
  const cleanup = useFlag('visual.chalkline_cleanup');
  const touchPolish = useFlag('ux.touch_polish');
  const s = cleanup ? styles : legacyStyles;
  return (
    <View style={s.row}>
      <Text scale="dense" style={s.label}>
        {cleanup ? 'Move to' : 'Move to:'}
      </Text>
      <View style={[s.chips, touchPolish && sharedStyles.chipsTouch]}>
        {TIERS.map((t) => {
          const accent = accentFor(t);
          return (
            <Pressable
              key={t}
              onPress={() => onPick(t)}
              hitSlop={touchPolish ? TOUCH_HIT_SLOP : undefined}
              accessibilityRole="button"
              accessibilityLabel={`Move selected players to ${TIER_LABEL[t]}`}
              style={({ pressed }) => [
                s.chip,
                touchPolish && sharedStyles.chipTouch,
                { borderColor: accent },
                pressed && { opacity: 0.6 },
              ]}
            >
              <Text scale="dense" style={[s.chipText, { color: accent }]}>
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
    marginBottom: space.sm,
  },
  label: {
    ...type.label,
    marginBottom: space.xs,
  },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: space.xs,
  },
  chip: {
    paddingHorizontal: space.sm,
    paddingVertical: space.xs,
    borderRadius: radii.xs,
    borderWidth: 1,
    backgroundColor: ink.ink1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipText: { fontFamily: fonts.uiSemi, fontSize: 11, letterSpacing: 0.5 },
});

// ux.touch_polish additions — shared by both visual branches.
const sharedStyles = StyleSheet.create({
  chipsTouch: { gap: space.sm },
  chipTouch: { minHeight: 36, justifyContent: 'center' },
});

// ── Legacy branch (flag off) — pre-teardown rendering, byte-for-byte ────────
// DELETE when `visual.chalkline_cleanup` is removed.
const LEGACY = {
  surface: '#1a1d27',
  muted: '#7a7f96',
} as const;

const legacyStyles = StyleSheet.create({
  row: {
    marginBottom: 8,
  },
  label: {
    color: LEGACY.muted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
    marginBottom: 4,
  },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 4,
  },
  chip: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 10,
    borderWidth: 1,
    backgroundColor: LEGACY.surface,
  },
  chipText: { fontSize: 11, fontWeight: '800' },
});
