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
// `trades_home_inline` variant is assigned: bigger (28pt, up from 22pt)
// Draft/Free-agents icon buttons plus a Manual-calc button that carries no
// league or player reference (#272, verbatim: "remove any league or player
// references for 'Manual' calc"). `onDraft` omitted ⇒ two buttons, mirroring
// TradeFinderModeBar's own `onDraft?` convention (flag `draft.room` gates the
// chip's existence upstream, not this component).
//
// Free Agents borrows the shared `search` glyph (nearest semantic fit — "find
// available players"); no dedicated free-agents icon exists in the shared
// Icon set (lab's own grounding note). Manual calc reuses `swap`, the same
// glyph InLeagueCalculator already renders between its two sides.

interface Props {
  onDraft?: () => void;
  onFreeAgents: () => void;
  onManualCalc: () => void;
}

export default function TradeHomeUtilityRow({ onDraft, onFreeAgents, onManualCalc }: Props) {
  return (
    <View style={styles.row} testID="trades.home-utility-row">
      {onDraft ? (
        <Pressable
          testID="trades.home-utility.draft"
          accessibilityRole="button"
          accessibilityLabel="Draft"
          onPress={() => {
            haptics.selection();
            onDraft();
          }}
          style={({ pressed }) => [styles.btn, pressed && styles.btnPressed]}
        >
          <Icon name="flag" size={28} color={chalk.dim} />
          <Text style={styles.lbl}>Draft</Text>
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
