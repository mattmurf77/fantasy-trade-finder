import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors } from '../theme/colors';
import { spacing, fontSize } from '../theme/spacing';

// FB4-61 / #65 — compact stat strip rendered under a player tile on Tiers.
// Shows BOTH the user's rank + 30d trend and the consensus rank on one line,
// each with a short text label ("You" / "Cons") so the distinction never
// relies on color. The old Consensus | You toggle is gone (#65). Purely
// presentational: the parent resolves the numbers from the rankings payload /
// Trends source and passes them in. Tiles are already flagged as too big
// (#58), so this stays one tight line.
//
// Consensus 30d trend has no backend payload yet (#61) — the consensus
// segment intentionally shows rank only, and is omitted entirely when the
// consensus rank is unavailable (no dash graveyard).

export interface TileStatsProps {
  /** User's pre-formatted rank label, e.g. "#4". `null` → "—". */
  youRankLabel: string | null;
  /** User's 30-day rank delta. Positive = moved UP toward #1; null → "–". */
  youTrendDelta: number | null;
  /** Consensus rank label, e.g. "ADP 12" or "#37". `null` → segment omitted. */
  consensusRankLabel: string | null;
}

// Format a rank delta with a direction glyph. Mirrors TrendsScreen's
// formatRankDelta so the two surfaces read identically.
function formatTrend(delta: number | null): { text: string; color: string } {
  if (delta == null) return { text: '–', color: colors.muted };
  if (delta > 0) return { text: `▲${delta}`, color: colors.green };
  if (delta < 0) return { text: `▼${Math.abs(delta)}`, color: colors.red };
  return { text: '–0', color: colors.muted };
}

function TileStats({ youRankLabel, youTrendDelta, consensusRankLabel }: TileStatsProps) {
  const trend = formatTrend(youTrendDelta);
  return (
    <View style={styles.row}>
      <Text style={styles.label}>You</Text>
      <Text style={styles.rank} numberOfLines={1}>
        {youRankLabel ?? '—'}
      </Text>
      <Text style={[styles.trend, { color: trend.color }]} numberOfLines={1}>
        {trend.text}
      </Text>
      <Text style={styles.label}>30d</Text>
      {consensusRankLabel != null ? (
        <>
          <Text style={styles.sep}>·</Text>
          <Text style={styles.label}>Cons</Text>
          <Text style={styles.rank} numberOfLines={1}>
            {consensusRankLabel}
          </Text>
        </>
      ) : null}
    </View>
  );
}

export default React.memo(TileStats);

const styles = StyleSheet.create({
  // No outer margin — since #58 (cozy density) the strip renders INLINE on
  // line 2 of the dense PlayerCard (via its statsSlot), next to the
  // TierChalkBadge, so the host row owns the spacing.
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  rank: { color: colors.text, fontSize: fontSize.xs, fontWeight: '700' },
  sep: { color: colors.border, fontSize: fontSize.xs },
  trend: { fontSize: fontSize.xs, fontWeight: '800' },
  label: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
});
