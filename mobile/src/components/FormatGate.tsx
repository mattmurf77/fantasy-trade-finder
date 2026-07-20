import React from 'react';
import { View, StyleSheet, Pressable, ActivityIndicator } from 'react-native';
import { ink, semantic, radii, space } from '../theme/chalkline';
import { Button, Text } from './chalkline';
import { useFlag } from '../state/useFeatureFlags';
import type { ScoringFormat } from '../shared/types';

// FB4-59 — Single-format gate error on TradesHome.
// Shown only when the user has established the OTHER scoring format but NOT
// the one this league uses. Names both formats and offers two fast fixes:
// copy from the set format, or set the needed format up manually. Detection
// lives in TradesScreen (it owns the progress signal); this component is
// purely presentational.
//
// Teardown S2 PRD-03: rebuilt on Chalkline primitives behind
// `visual.chalkline_cleanup` (kills the banned #4f7cff indigo CTA, radius 14,
// '#fff' literal and the "⇆" text glyph — Button's `swap` Icon instead) and
// adds the S4B-09 jargon subline. Flag off renders the pre-teardown look
// pixel-for-pixel via the LEGACY_* constants below (theme/colors.ts no longer
// exports chrome hexes); delete the legacy branch at flag cleanup.

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

export default function FormatGate(props: FormatGateProps) {
  const cleanup = useFlag('visual.chalkline_cleanup');
  return cleanup ? <ChalklineGate {...props} /> : <LegacyGate {...props} />;
}

// ── Chalkline branch (flag on) ──────────────────────────────────────────────

function ChalklineGate({
  neededFormat,
  setFormat,
  copying,
  onCopy,
  onSetUpManually,
}: FormatGateProps) {
  return (
    <View style={styles.card}>
      <Text variant="title">Set up {FORMAT_LABELS[neededFormat]} to trade here</Text>
      <Text variant="bodySm">
        You've set up your {FORMAT_LABELS[setFormat]} rankings but not{' '}
        {FORMAT_LABELS[neededFormat]}, which this league uses. Add it to start
        finding trades.
      </Text>
      {/* S4B-09 — expand the format jargon once, right where it gates. */}
      <Text variant="bodySm">SF TEP = Superflex, TE premium.</Text>

      <Button
        label={`Copy from ${FORMAT_LABELS[setFormat]}`}
        icon="swap"
        loading={copying}
        onPress={onCopy}
        style={styles.copyBtn}
      />
      <Button
        label={`Set up ${FORMAT_LABELS[neededFormat]} manually`}
        variant="secondary"
        disabled={copying}
        onPress={onSetUpManually}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: ink.ink1,
    // Warn border: this is a gate, not an error — solid encode color per the
    // badge/border construction (replaces the legacy 45%-alpha gold tint).
    borderColor: semantic.warn,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: space.lg,
    gap: space.sm,
  },
  copyBtn: { marginTop: space.xs },
});

// ── Legacy branch (flag off) — pre-teardown rendering, byte-for-byte ────────
// Hexes/values inlined from the retired theme/colors.ts + spacing.ts scales.
// DELETE this whole section when `visual.chalkline_cleanup` is removed.

const LEGACY = {
  surface: '#1a1d27',
  border: '#2a2d3a',
  text: '#e8eaf0',
  muted: '#7a7f96',
  accent: '#4f7cff', // banned indigo — survives only behind the flag-off branch
} as const;

function LegacyGate({
  neededFormat,
  setFormat,
  copying,
  onCopy,
  onSetUpManually,
}: FormatGateProps) {
  return (
    <View style={legacyStyles.card}>
      <Text scale="body" style={legacyStyles.title}>
        Set up {FORMAT_LABELS[neededFormat]} to trade here
      </Text>
      <Text scale="body" style={legacyStyles.body}>
        You've set up your {FORMAT_LABELS[setFormat]} rankings but not{' '}
        {FORMAT_LABELS[neededFormat]}, which this league uses. Add it to start
        finding trades.
      </Text>

      <Pressable
        disabled={copying}
        onPress={onCopy}
        accessibilityRole="button"
        accessibilityLabel={`Copy from ${FORMAT_LABELS[setFormat]}`}
        accessibilityState={{ disabled: copying, busy: copying }}
        style={({ pressed }) => [
          legacyStyles.primaryBtn,
          pressed && { opacity: 0.85 },
          copying && { opacity: 0.5 },
        ]}
      >
        {copying ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text scale="body" style={legacyStyles.primaryBtnText}>
            ⇆ Copy from {FORMAT_LABELS[setFormat]}
          </Text>
        )}
      </Pressable>

      <Pressable
        disabled={copying}
        onPress={onSetUpManually}
        accessibilityRole="button"
        accessibilityState={{ disabled: copying }}
        style={({ pressed }) => [
          legacyStyles.secondaryBtn,
          pressed && { opacity: 0.7 },
          copying && { opacity: 0.5 },
        ]}
      >
        <Text scale="body" style={legacyStyles.secondaryBtnText}>
          Set up {FORMAT_LABELS[neededFormat]} manually
        </Text>
      </Pressable>
    </View>
  );
}

const legacyStyles = StyleSheet.create({
  card: {
    backgroundColor: LEGACY.surface,
    borderColor: 'rgba(245,158,11,0.45)', // gold-tinted border — reads as a gate, not an error
    borderWidth: 1,
    borderRadius: 14,
    padding: 16,
    gap: 8,
  },
  title: { color: LEGACY.text, fontSize: 18, fontWeight: '800' },
  body: {
    color: LEGACY.muted,
    fontSize: 13,
    lineHeight: 22,
  },
  primaryBtn: {
    backgroundColor: LEGACY.accent,
    paddingVertical: 14,
    borderRadius: 10,
    alignItems: 'center',
    marginTop: 8,
  },
  primaryBtnText: { color: '#fff', fontSize: 15, fontWeight: '800' },
  secondaryBtn: {
    paddingVertical: 10,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: LEGACY.border,
    alignItems: 'center',
  },
  secondaryBtnText: { color: LEGACY.text, fontSize: 13, fontWeight: '700' },
});
