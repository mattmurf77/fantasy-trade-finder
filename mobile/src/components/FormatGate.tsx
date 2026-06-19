import React from 'react';
import { View, Text, StyleSheet, Pressable, ActivityIndicator } from 'react-native';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import type { ScoringFormat } from '../shared/types';

// FB4-59 — Single-format gate error on TradesHome.
// Shown only when the user has established the OTHER scoring format but NOT
// the one this league uses. Names both formats and offers two fast fixes:
// copy from the set format, or set the needed format up manually. Detection
// lives in TradesScreen (it owns the progress signal); this component is
// purely presentational.

// Human label for each format. Mirrors TiersScreen's FORMAT_LABELS so the
// copy reads consistently across the Tiers and Trades surfaces.
const FORMAT_LABELS: Record<ScoringFormat, string> = {
  '1qb_ppr': '1QB PPR',
  sf_tep:    'SF TEP',
};

export function formatLabel(fmt: ScoringFormat): string {
  return FORMAT_LABELS[fmt];
}

interface FormatGateProps {
  /** The format this league uses — the one the user has NOT set up yet. */
  neededFormat: ScoringFormat;
  /** The format the user DID set up (the only established one). */
  setFormat: ScoringFormat;
  /** True while the copy-from-format mutation is in flight. */
  copying: boolean;
  /** Confirm + copy the set format's tiers into the needed format. */
  onCopy: () => void;
  /** Navigate to the ranking entry (Tiers) for the needed format. */
  onSetUpManually: () => void;
}

export default function FormatGate({
  neededFormat,
  setFormat,
  copying,
  onCopy,
  onSetUpManually,
}: FormatGateProps) {
  return (
    <View style={styles.card}>
      <Text style={styles.title}>Set up {FORMAT_LABELS[neededFormat]} to trade here</Text>
      <Text style={styles.body}>
        You've set up your {FORMAT_LABELS[setFormat]} rankings but not{' '}
        {FORMAT_LABELS[neededFormat]}, which this league uses. Add it to start
        finding trades.
      </Text>

      <Pressable
        disabled={copying}
        onPress={onCopy}
        style={({ pressed }) => [
          styles.primaryBtn,
          pressed && { opacity: 0.85 },
          copying && { opacity: 0.5 },
        ]}
      >
        {copying ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.primaryBtnText}>
            ⇆ Copy from {FORMAT_LABELS[setFormat]}
          </Text>
        )}
      </Pressable>

      <Pressable
        disabled={copying}
        onPress={onSetUpManually}
        style={({ pressed }) => [
          styles.secondaryBtn,
          pressed && { opacity: 0.7 },
          copying && { opacity: 0.5 },
        ]}
      >
        <Text style={styles.secondaryBtnText}>
          Set up {FORMAT_LABELS[neededFormat]} manually
        </Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderColor: 'rgba(245,158,11,0.45)', // gold-tinted border — reads as a gate, not an error
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  title: { color: colors.text, fontSize: fontSize.lg, fontWeight: '800' },
  body: {
    color: colors.muted,
    fontSize: fontSize.sm,
    lineHeight: 22,
  },
  primaryBtn: {
    backgroundColor: colors.accent,
    paddingVertical: 14,
    borderRadius: radius.md,
    alignItems: 'center',
    marginTop: spacing.sm,
  },
  primaryBtnText: { color: '#fff', fontSize: fontSize.base, fontWeight: '800' },
  secondaryBtn: {
    paddingVertical: spacing.sm + 2,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
  },
  secondaryBtnText: { color: colors.text, fontSize: fontSize.sm, fontWeight: '700' },
});
