import React, { useEffect } from 'react';
import { View, StyleSheet, Pressable } from 'react-native';
import { ink, chalk, ice, space, radii, type, fonts } from '../theme/chalkline';
import { Text } from './chalkline';
import type { Layer1Code, Layer2Code } from '../api/declineReasons';
import { PASS_REASON_CHIPS } from '../utils/passReasonCadence';

// PassReasonChips — the deck card's occasional "why pass?" row (flag
// `trade.pass_reason_cadence`, offer-learnings WS3). Rendered by TradeCard in
// place of the ✕ only on the card the cadence asks on. ONE tap does it:
// a chip is the pass and the reason together (the host advances the deck at
// once, no second layer); "Just pass" is the plain pass and records no reason.
// Built from existing tokens only: the DeclineReasonPanel block chrome and
// option-row borders, chips at radius xs, ice on press (an action).

export interface PassReasonChipsProps {
  onChip: (reason: Layer1Code, detail: Layer2Code) => void;
  onSkip: () => void;
  /** Fired once when the row mounts (TradeCard is remounted per card). */
  onShown?: () => void;
  disabled?: boolean;
}

export default function PassReasonChips({ onChip, onSkip, onShown, disabled }: PassReasonChipsProps) {
  useEffect(() => {
    onShown?.();
    // Once per mount: the card that carries the row is keyed per trade.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <View style={styles.block} testID="trades.pass-reason-chips">
      <Text scale="dense" style={styles.label}>
        WHY PASS?
      </Text>
      <View style={styles.row}>
        {PASS_REASON_CHIPS.map((c) => (
          <Pressable
            key={c.detail}
            testID={`trades.pass-reason-chip.${c.detail}`}
            onPress={() => onChip(c.reason, c.detail)}
            disabled={disabled}
            accessibilityRole="button"
            accessibilityLabel={`Pass — ${c.label}`}
            accessibilityHint="Passes on this trade and records why"
            style={({ pressed }) => [styles.chip, pressed && styles.chipPressed]}
          >
            <Text scale="body" style={styles.chipText}>
              {c.label}
            </Text>
          </Pressable>
        ))}
        <Pressable
          testID="trades.pass-reason-skip"
          onPress={onSkip}
          disabled={disabled}
          accessibilityRole="button"
          accessibilityLabel="Just pass"
          accessibilityHint="Passes on this trade without a reason"
          style={({ pressed }) => [styles.chip, styles.skip, pressed && styles.chipPressed]}
        >
          <Text scale="body" style={styles.skipText}>
            Just pass
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  // Same seat as DeclineReasonPanel's block: beneath the card's ✓, on a hairline.
  block: {
    marginTop: space.md,
    paddingTop: space.md,
    borderTopWidth: 1,
    borderTopColor: ink.line,
    gap: space.sm,
  },
  label: {
    fontFamily: fonts.data,
    fontSize: 11,
    lineHeight: 14,
    letterSpacing: 1.1,
    textTransform: 'uppercase',
    color: chalk.dim,
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: space.sm,
  },
  // 44pt touch floor via minHeight; labels wrap rather than truncate.
  chip: {
    minHeight: 44,
    justifyContent: 'center',
    paddingVertical: space.xs,
    paddingHorizontal: space.md,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.lineStrongA11y,
    borderRadius: radii.xs,
  },
  chipPressed: {
    borderColor: ice.base,
    backgroundColor: ink.ink3,
  },
  chipText: {
    ...type.bodySm,
    fontFamily: fonts.uiSemi,
    color: chalk.base,
  },
  skip: {
    borderColor: ink.line,
  },
  skipText: {
    ...type.bodySm,
    color: chalk.dim,
  },
});
