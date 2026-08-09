import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Icon from './chalkline/Icon';
import { chalk, fonts, ink, radii, space, type } from '../theme/chalkline';
import { haptics } from '../utils/haptics';

// #270 — inline trades home, experiment `trades_home_inline` (variants
// `strip` and `canvas`; see mockups/polish-lab-2026-08/trades-home-inline.html
// A1/B1 frames). Pulls League + "Trading with" out from behind the #257 full
// sheet's Change link onto the page as a compact 2-pill strip (#270,
// verbatim: "League and teams to trade with more naturally presenting back
// outside the change link too").
//
// Presentational only — both taps reuse the SAME state/pickers #269 already
// wired into the sheet (TradesScreen's `teamPickerOpen`/`leaguePickerOpen`),
// just opened directly instead of via the sheet's close-then-reopen dance
// (openTeamPickerFromSheet/openLeaguePickerFromSheet would pop the full
// sheet back open on close, which defeats the point of this strip).

interface Props {
  leagueName: string | null;
  opponentName: string | null;
  onOpenLeaguePicker: () => void;
  onOpenTeamPicker: () => void;
}

export default function TradingWithStrip({
  leagueName,
  opponentName,
  onOpenLeaguePicker,
  onOpenTeamPicker,
}: Props) {
  return (
    <View style={styles.row} testID="trades.trading-with-strip">
      <Pressable
        testID="trades.trading-with-strip.league"
        accessibilityRole="button"
        accessibilityLabel={`League: ${leagueName ?? 'choose a league'}`}
        onPress={() => {
          haptics.selection();
          onOpenLeaguePicker();
        }}
        style={({ pressed }) => [styles.pill, pressed && styles.pillPressed]}
      >
        <Text style={styles.lbl}>League</Text>
        <View style={styles.valRow}>
          <Text style={styles.val} numberOfLines={1}>
            {leagueName ?? 'Choose a league'}
          </Text>
          <Icon name="chevron-down" size={10} color={chalk.faint} />
        </View>
      </Pressable>
      <Pressable
        testID="trades.trading-with-strip.team"
        accessibilityRole="button"
        accessibilityLabel={`Trading with: ${opponentName ?? 'any league-mate'}`}
        onPress={() => {
          haptics.selection();
          onOpenTeamPicker();
        }}
        style={({ pressed }) => [styles.pill, pressed && styles.pillPressed]}
      >
        <Text style={styles.lbl}>Trading with</Text>
        <View style={styles.valRow}>
          <Text style={styles.val} numberOfLines={1}>
            {opponentName ?? 'Any league-mate'}
          </Text>
          <Icon name="chevron-down" size={10} color={chalk.faint} />
        </View>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: space.sm, marginBottom: space.md },
  pill: {
    flex: 1,
    gap: 2,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    backgroundColor: ink.ink1,
    paddingHorizontal: space.sm,
    paddingVertical: space.sm,
    minWidth: 0,
  },
  pillPressed: { backgroundColor: ink.ink3 },
  lbl: {
    fontSize: 9,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    color: chalk.faint,
    fontFamily: fonts.uiSemi,
  },
  valRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  val: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi, flexShrink: 1 },
});
