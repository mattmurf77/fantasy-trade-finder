import React from 'react';
import { View, StyleSheet } from 'react-native';
import { ink, chalk, flare, fonts } from '../theme/chalkline';
import { Text } from './chalkline';
import { useFlag } from '../state/useFeatureFlags';

interface Props {
  /** Which meter this is: 'trade' = tradeability (player the user owns),
   *  'get' = acquirability (player a leaguemate owns). Drives the label,
   *  so the meaning never relies on color alone. */
  kind: 'trade' | 'get';
  /** 0–1 score from the rankings payload (tradeability / acquirability).
   *  Values outside the range are clamped. */
  score: number;
}

// TestFlight #71 — tile trade meter for the Tiers board's dense 60px rows.
// A Chalkline Meter shrunk to tile scale: 9px caps label ("TRADE" / "GET")
// + 3px square-end track (ink-3) with a flare fill (informational highlight,
// ADR-005 — this is market information, not an action). The full-size Meter
// primitive (4px track + space-md gap + label type) is too tall/loose for
// the 60px pitch, hence this minimal inline variant — see
// docs/design/components.md → Meters → TradeMeter.
export default function TradeMeter({ kind, score }: Props) {
  // Teardown S2 PRD-04 (`visual.chalkline_cleanup`): the 9px caps label rises
  // to the 11px floor; the fixed label column widens 34→42 so "TRADE" still
  // fits and the tracks stay a scannable aligned column. Flag off = 9px/34,
  // the pre-teardown look.
  const cleanup = useFlag('visual.chalkline_cleanup');
  const clamped = Math.max(0, Math.min(1, score || 0));
  const label = kind === 'trade' ? 'TRADE' : 'GET';
  return (
    <View
      style={styles.row}
      accessibilityRole="progressbar"
      accessibilityValue={{ min: 0, max: 100, now: Math.round(clamped * 100) }}
      accessibilityLabel={
        kind === 'trade' ? 'Tradeability' : 'Acquirability'
      }
    >
      <Text scale="dense" style={[styles.label, cleanup && styles.labelFloor]}>{label}</Text>
      <View style={styles.track}>
        <View style={[styles.fill, { width: `${clamped * 100}%` }]} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  // Same construction as TileStats' labels (9px = legacy, flag off only).
  label: {
    fontFamily: fonts.uiSemi,
    fontSize: 9,
    letterSpacing: 0.5,
    color: chalk.dim,
    // Fixed width so the tracks align into a scannable column across tiles
    // ("TRADE" is wider than "GET").
    width: 34,
  },
  // S2 PRD-04 (`visual.chalkline_cleanup`): 11px type floor + widened column.
  labelFloor: {
    fontSize: 11,
    width: 42,
  },
  track: {
    flex: 1,
    maxWidth: 140,
    height: 3,
    backgroundColor: ink.ink3,
    // Square ends per the design system — chalk lines, not pills.
  },
  fill: {
    height: 3,
    backgroundColor: flare.base,
  },
});
