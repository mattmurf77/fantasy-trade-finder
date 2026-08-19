import React from 'react';
import { View, StyleSheet } from 'react-native';
import { ink, chalk, semantic, space, type } from '../../theme/chalkline';
import { Text, Icon } from '../chalkline';
import type { FairnessBand } from '../../utils/tradePresentation';

// FairnessRangeBand — fairness as a POSITION IN A RANGE, never a verdict.
// Flag `trades.presentation_v2`; approved lab
// mockups/trade-suggestion-redesign/01-todays-trade.html (the `.band` block).
//
// WHY THIS EXISTS RATHER THAN FairnessMeter / TradeValueBar. Both shipped
// components are winner-oriented by construction: `Meter` + `fairnessColor`
// paints a single fill whose colour IS a verdict, and `TradeValueBar` is a
// diverging bar that literally renders "You win" / "They win" with a margin.
// The same card here is shown to BOTH managers, so a winner needle becomes a
// league-chat weapon and trains users to demand a calculator win on every
// deal (design principle P3, round-2 T7). Neither of those components may be
// used on this surface. This one can only say "inside the normal window" or
// "outside it" — there is no side and no magnitude in its props.
//
// CHALKLINE GAP (flagged in docs/plans/trade-presentation-v2/scope.md §4 as a
// components.md candidate): a "range band" — a track carrying a shaded
// acceptable ZONE plus a marker — is a construction the design system does
// not yet name. Built from existing tokens only: ink-3 track, pos at 22%
// opacity for the zone, chalk for the marker, no new colour/radius/type.

const TRACK_H = 6;

export default function FairnessRangeBand({ band }: { band: FairnessBand }) {
  // `as const` on the template keeps RN's DimensionValue (`${number}%`) happy.
  const pct = (v: number): `${number}%` =>
    `${Math.round(Math.min(1, Math.max(0, v)) * 100)}%`;
  const tone = band.withinNormal ? semantic.pos : chalk.dim;
  return (
    <View
      style={styles.wrap}
      testID="presentation.fairness-band"
      accessible
      // The screen reader gets the SAME sentence a sighted user gets. No
      // percentage is spoken, because none is displayed (P3/P5).
      accessibilityRole="image"
      accessibilityLabel={`${band.label}, compared with league consensus`}
    >
      <View style={styles.track} importantForAccessibility="no-hide-descendants">
        <View
          style={[
            styles.zone,
            {
              left: pct(band.zoneStartPct),
              right: pct(1 - band.zoneEndPct),
              backgroundColor: semantic.pos,
            },
          ]}
        />
        <View style={[styles.edge, { left: pct(band.zoneStartPct) }]} />
        <View style={[styles.marker, { left: pct(band.markerPct) }]} />
      </View>
      <View style={styles.noteRow} importantForAccessibility="no-hide-descendants">
        {band.withinNormal ? <Icon name="check" size={14} color={semantic.pos} /> : null}
        <Text scale="dense" style={[type.label, { color: tone }]}>
          {band.label}
        </Text>
        <Text scale="dense" style={[type.data, styles.vs]}>
          vs. league consensus
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: space.md, gap: space.xs },
  track: {
    height: TRACK_H,
    backgroundColor: ink.ink3,
    marginTop: space.xs,
  },
  zone: { position: 'absolute', top: 0, bottom: 0, opacity: 0.22 },
  edge: {
    position: 'absolute',
    top: -2,
    bottom: -2,
    width: 1,
    backgroundColor: semantic.pos,
  },
  marker: {
    position: 'absolute',
    top: -3,
    bottom: -3,
    width: 4,
    marginLeft: -2,
    backgroundColor: chalk.base,
  },
  noteRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    flexWrap: 'wrap',
  },
  vs: { marginLeft: 'auto', fontSize: 11, lineHeight: 14, color: chalk.faint },
});
