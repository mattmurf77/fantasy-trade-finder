import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Icon from './chalkline/Icon';
import { chalk, fonts, ink, radii, space, type } from '../theme/chalkline';
import { haptics } from '../utils/haptics';

// #270/#272 — inline trades home, experiment `trades_home_inline` (variants
// `strip` and `canvas`; see mockups/polish-lab-2026-08/trades-home-inline.html
// BASE-1/A1/B1 frames + docs/feedback/items/270-inline-trades-home/status.md).
//
// Replaces TradeFinderModeBar's row on the guided landing ONLY while a
// `trades_home_inline` variant is assigned: a bigger (28pt, up from 22pt)
// Free-agents icon button plus a Manual-calc button that carries no league or
// player reference (#272, verbatim: "remove any league or player references
// for 'Manual' calc"). The Draft cell that used to LEAD this row was removed
// by G-425 (#425, "the overhaul tile should replace the draft button") — the
// Team overhaul hero now sits directly above this row, and the Draft Room
// keeps its seasonal bottom tab, League-tab tile and deep link. The removal is
// unconditional: no Draft handler prop exists here, whatever `draft.room` says.
// (TradeFinderModeBar, the control cohort's row, still carries its own Draft
// chip — that is a different control and was deliberately left alone.)
//
// Free Agents borrows the shared `search` glyph (nearest semantic fit — "find
// available players"); no dedicated free-agents icon exists in the shared
// Icon set (lab's own grounding note). Manual calc reuses `swap`, the same
// glyph InLeagueCalculator already renders between its two sides.

interface Props {
  onFreeAgents: () => void;
  onManualCalc: () => void;
  /** Presentation v2 (flag `trades.presentation_v2`) — opens the `TodaysTrade`
   *  surface. Optional-prop convention (TradeFinderModeBar's optional-
   *  handler pattern): omitting it renders today's two buttons exactly, so
   *  a flag-off build is byte-identical.
   *  This row REPLACES TradeFinderModeBar for users in the
   *  `trades_home_inline` experiment, so the entry point has to exist here
   *  too — otherwise those users could never reach the surface under test. */
  onTodaysTrade?: () => void;
  /** Receipts (docs/plans/receipts/, flag `receipts.screen`) — opens the
   *  viewer's graded suggestion track record. Same optional-prop convention as
   *  `onTodaysTrade` above: passing the handler is what
   *  creates the control, so a flag-off build renders this row byte-identical
   *  to today. The FLAG gates this entry point; the route itself is
   *  registered unconditionally in RootNav. */
  onTrackRecord?: () => void;
}

export default function TradeHomeUtilityRow({
  onFreeAgents,
  onManualCalc,
  onTodaysTrade,
  onTrackRecord,
}: Props) {
  return (
    <View style={styles.row} testID="trades.home-utility-row">
      {/* #379 — the #376 Filters button that used to lead this row was
          removed by operator ruling: filters live inside the Find-a-Trade
          page (the minimized "Outlook & filters" row, TradesScreen's
          trades.outlook-fallback), not as a top-row icon. */}
      {onTodaysTrade ? (
        <Pressable
          testID="trades.home-utility.todays-trade"
          accessibilityRole="button"
          accessibilityLabel="Today's trade"
          onPress={() => {
            haptics.selection();
            onTodaysTrade();
          }}
          style={({ pressed }) => [styles.btn, pressed && styles.btnPressed]}
        >
          {/* `trade` is the same glyph the Acquire tab itself carries — this
              button opens the endorsed trade, so it is the honest fit. */}
          <Icon name="trade" size={28} color={chalk.dim} />
          <Text style={styles.lbl}>Today</Text>
        </Pressable>
      ) : null}
      <Pressable
        testID="trades.home-utility.free-agents"
        accessibilityRole="button"
        accessibilityLabel="Free agents"
        onPress={() => {
          haptics.selection();
          onFreeAgents();
        }}
        style={({ pressed }) => [styles.btn, pressed && styles.btnPressed]}
      >
        <Icon name="search" size={28} color={chalk.dim} />
        <Text style={styles.lbl}>Free agents</Text>
      </Pressable>
      <Pressable
        testID="trades.home-utility.manual-calc"
        accessibilityRole="button"
        accessibilityLabel="Manual calculator"
        onPress={() => {
          haptics.selection();
          onManualCalc();
        }}
        style={({ pressed }) => [styles.btn, styles.btnManual, pressed && styles.btnPressed]}
      >
        <Icon name="swap" size={24} color={chalk.dim} />
        <Text style={styles.lbl}>Manual calc</Text>
      </Pressable>
      {/* Receipts — how past suggestions actually tracked the market. Uses the
          shared `trends` glyph (nearest semantic fit: a record over time); no
          dedicated glyph exists in the shared Icon set. */}
      {onTrackRecord ? (
        <Pressable
          testID="trades.home-utility.track-record"
          accessibilityRole="button"
          accessibilityLabel="Track record"
          onPress={() => {
            haptics.selection();
            onTrackRecord();
          }}
          style={({ pressed }) => [styles.btn, pressed && styles.btnPressed]}
        >
          <Icon name="trends" size={28} color={chalk.dim} />
          <Text style={styles.lbl}>Track record</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: space.sm, marginBottom: space.md },
  btn: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.xs,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    backgroundColor: ink.ink1,
    paddingVertical: space.sm,
    paddingHorizontal: space.xs,
    minHeight: 64,
  },
  btnManual: { borderStyle: 'dashed' },
  btnPressed: { backgroundColor: ink.ink3 },
  lbl: { ...type.bodySm, color: chalk.dim, fontFamily: fonts.uiSemi, textAlign: 'center' },
});
