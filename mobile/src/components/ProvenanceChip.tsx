import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { ink, chalk, flare, radii, space, fonts } from '../theme/chalkline';

// Provenance chip (onboarding item 4 — docs/plans/onboarding-conversion/
// plan.md): tick-label chip stating which value basis built the deck.
// "CONSENSUS VALUES" until the user Quick-Sets at least one position
// (ob.quicksetCompletedPositions non-empty), then "YOUR BOARD" — flare is
// the informational-highlight accent (ADR-005; never an action color).
//
// The tap-through to Quick Set is item 7's scope: `onPress` defaults to
// undefined and the Pressable is disabled until a handler is wired.

interface Props {
  /** true once the user has personalized at least one position. */
  personalized: boolean;
  /** Item 7 wires this to the onboarding-mode Quick Set entry. */
  onPress?: () => void;
  testID?: string;
}

export default function ProvenanceChip({
  personalized,
  onPress,
  testID = 'trades.provenance-chip',
}: Props) {
  const tickColor = personalized ? flare.base : chalk.dim;
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={!onPress}
      accessibilityRole="button"
      accessibilityLabel={
        personalized
          ? 'Trades priced with your board values'
          : 'Trades priced with consensus values'
      }
      style={({ pressed }) => [
        styles.chip,
        personalized && styles.chipPersonalized,
        pressed && !!onPress && styles.chipPressed,
      ]}
    >
      <View style={[styles.tick, { backgroundColor: tickColor }]} />
      <Text style={[styles.label, personalized && styles.labelPersonalized]}>
        {personalized ? 'YOUR BOARD' : 'CONSENSUS VALUES'}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  // Data-encoding chip construction (components.md → Badges & chips):
  // 1px hairline on ink-1, radius xs, mono micro-label.
  chip: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    minHeight: 24,
    paddingHorizontal: space.sm,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink1,
  },
  chipPersonalized: {
    borderColor: flare.base,
  },
  chipPressed: {
    backgroundColor: ink.ink3,
  },
  tick: {
    width: 3,
    height: 10,
  },
  label: {
    fontFamily: fonts.dataSemi,
    fontSize: 10,
    letterSpacing: 0.5,
    color: chalk.dim,
  },
  labelPersonalized: {
    color: chalk.base,
  },
});
