import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors } from '../theme/colors';
import { spacing, fontSize } from '../theme/spacing';

// FB4-61 — compact two-stat strip rendered under a player tile on Tiers.
// Shows a rank (left) + a 30-day trend (right) for the currently-selected
// stat mode (Consensus | You). Purely presentational: the parent resolves
// the numbers from the rankings payload / Trends source and passes them in.
// Tiles are already flagged as too big (#58), so this stays one tight line.

export type StatMode = 'consensus' | 'you';

export interface TileStatsProps {
  /** Pre-formatted rank label, e.g. "#4" or "ADP 12". `null` → "—". */
  rankLabel: string | null;
  /** 30-day rank delta. Positive = moved UP toward #1; null → unavailable. */
  trendDelta: number | null;
}

// Format a rank delta with a direction glyph. Mirrors TrendsScreen's
// formatRankDelta so the two surfaces read identically.
function formatTrend(delta: number | null): { text: string; color: string } {
  if (delta == null) return { text: '–', color: colors.muted };
  if (delta > 0) return { text: `▲${delta}`, color: colors.green };
  if (delta < 0) return { text: `▼${Math.abs(delta)}`, color: colors.red };
  return { text: '–0', color: colors.muted };
}

function TileStats({ rankLabel, trendDelta }: TileStatsProps) {
  const trend = formatTrend(trendDelta);
  return (
    <View style={styles.row}>
      <Text style={styles.rank} numberOfLines={1}>
        {rankLabel ?? '—'}
      </Text>
      <Text style={styles.sep}>·</Text>
      <Text style={[styles.trend, { color: trend.color }]} numberOfLines={1}>
        {trend.text}
      </Text>
      <Text style={styles.trendLabel}>30d</Text>
    </View>
  );
}

export default React.memo(TileStats);

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginTop: spacing.xs,
  },
  rank: { color: colors.text, fontSize: fontSize.xs, fontWeight: '700' },
  sep: { color: colors.border, fontSize: fontSize.xs },
  trend: { fontSize: fontSize.xs, fontWeight: '800' },
  trendLabel: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
});
