import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { ink, chalk, ice, radii, type } from '../theme/chalkline';
import type { ScoringFormat } from '../shared/types';

// SF/1QB scoring-format toggle (feedback #80). Presentational only — the
// screens own the switch flow via hooks/useScoringFormat.
//
// Chalkline construction: PositionTabs spec (segmented row, radius r-sm
// group, 1px line border, active segment ink-3 fill + 2px underline). The
// underline is ice — this is an action control, not a position encoding.
//
// Labels mirror FORMAT_LABELS on TiersScreen / FormatGate so the format
// names read consistently across surfaces.
const OPTIONS: Array<{ key: ScoringFormat; label: string }> = [
  { key: '1qb_ppr', label: '1QB PPR' },
  { key: 'sf_tep',  label: 'SF TEP' },
];

interface FormatToggleProps {
  /** Currently active format. Null (pre-bootstrap / default not yet
   *  resolved) renders both segments inactive. */
  value: ScoringFormat | null;
  onChange: (fmt: ScoringFormat) => void;
  /** Disable taps while a switch is in flight. */
  disabled?: boolean;
}

export default function FormatToggle({ value, onChange, disabled }: FormatToggleProps) {
  return (
    <View style={styles.group} accessibilityRole="tablist">
      {OPTIONS.map((opt, i) => {
        const isActive = value === opt.key;
        return (
          <Pressable
            key={opt.key}
            disabled={disabled}
            accessibilityRole="tab"
            accessibilityState={{ selected: isActive }}
            accessibilityLabel={`${opt.label} scoring format`}
            onPress={() => {
              if (!isActive) onChange(opt.key);
            }}
            style={({ pressed }) => [
              styles.segment,
              i > 0 && styles.segmentDivider,
              isActive && styles.segmentActive,
              pressed && !isActive && { backgroundColor: ink.ink3 },
              disabled && { opacity: 0.6 },
            ]}
          >
            <Text style={[styles.segmentText, isActive && styles.segmentTextActive]}>
              {opt.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  group: {
    flexDirection: 'row',
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  segment: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 36,
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  segmentDivider: {
    borderLeftWidth: 1,
    borderLeftColor: ink.line,
  },
  segmentActive: {
    backgroundColor: ink.ink3,
    borderBottomColor: ice.base,
  },
  segmentText: { ...type.label, color: chalk.dim },
  segmentTextActive: { color: chalk.base },
});
