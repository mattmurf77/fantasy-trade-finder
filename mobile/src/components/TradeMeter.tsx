import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { ink, chalk, flare, fonts } from '../theme/chalkline';

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
      <Text style={styles.label}>{label}</Text>
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
  // Same construction as TileStats' labels, one step smaller (9px caps).
  label: {
    fontFamily: fonts.uiSemi,
    fontSize: 9,
    letterSpacing: 0.5,
    color: chalk.dim,
    // Fixed width so the tracks align into a scannable column across tiles
    // ("TRADE" is wider than "GET").
    width: 34,
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
