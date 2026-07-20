import React from 'react';
import { View, StyleSheet } from 'react-native';
import { ink, chalk, fonts, semantic, space } from '../theme/chalkline';
import { Text } from './chalkline';
import { useFlag } from '../state/useFeatureFlags';

// FB4-61 / #65 — compact stat strip rendered under a player tile on Tiers.
// Shows the SAME two stats (rank + 30d trend) for BOTH the user and the
// consensus on one line, each with a short text label ("You" / "Cons") so
// the distinction never relies on color. The old Consensus | You toggle is
// gone (#65). Purely presentational: the parent resolves the numbers from
// the rankings payload / Trends source and passes them in. Tiles are already
// flagged as too big (#58), so this stays one tight line.
//
// Omit-when-missing: the whole consensus segment drops when its rank is
// unavailable, and the consensus trend glyph drops while the backend has no
// prior-day consensus snapshot yet (no dash graveyard).
//
// Teardown S2 PRD-03/04: ported to Chalkline behind `visual.chalkline_cleanup`
// — labels raised to the 11px floor in chalk-dim (legacy muted was 4.25:1),
// ranks in Plex Mono. Trend green/red were already the semantic pos/neg hexes
// (pure rename). Flag off renders the pre-teardown look via the LEGACY_*
// constants; delete that branch at flag cleanup.

export interface TileStatsProps {
  /** User's pre-formatted rank label, e.g. "#4". `null` → "—". */
  youRankLabel: string | null;
  /** User's 30-day rank delta. Positive = moved UP toward #1; null → "–". */
  youTrendDelta: number | null;
  /** Consensus positional rank label, e.g. "#7". `null` → segment omitted. */
  consensusRankLabel: string | null;
  /** Consensus 30-day rank delta. Positive = moved UP; null → glyph omitted. */
  consensusTrendDelta: number | null;
}

// Format a rank delta with a direction glyph. Mirrors TrendsScreen's
// formatRankDelta so the two surfaces read identically. Neutral color depends
// on the visual branch (legacy muted vs chalk-dim); pos/neg hexes are shared.
function formatTrend(delta: number | null, neutral: string): { text: string; color: string } {
  if (delta == null) return { text: '–', color: neutral };
  if (delta > 0) return { text: `▲${delta}`, color: semantic.pos };
  if (delta < 0) return { text: `▼${Math.abs(delta)}`, color: semantic.neg };
  return { text: '–0', color: neutral };
}

function TileStats({
  youRankLabel,
  youTrendDelta,
  consensusRankLabel,
  consensusTrendDelta,
}: TileStatsProps) {
  const cleanup = useFlag('visual.chalkline_cleanup');
  const s = cleanup ? styles : legacyStyles;
  const neutral = cleanup ? chalk.dim : LEGACY.muted;
  const trend = formatTrend(youTrendDelta, neutral);
  const consTrend =
    consensusTrendDelta != null ? formatTrend(consensusTrendDelta, neutral) : null;
  return (
    <View style={s.row}>
      <Text scale="dense" style={s.label}>You</Text>
      <Text scale="dense" style={s.rank} numberOfLines={1}>
        {youRankLabel ?? '—'}
      </Text>
      <Text scale="dense" style={[s.trend, { color: trend.color }]} numberOfLines={1}>
        {trend.text}
      </Text>
      <Text scale="dense" style={s.label}>30d</Text>
      {consensusRankLabel != null ? (
        <>
          <Text scale="dense" style={s.sep}>·</Text>
          <Text scale="dense" style={s.label}>Cons</Text>
          <Text scale="dense" style={s.rank} numberOfLines={1}>
            {consensusRankLabel}
          </Text>
          {consTrend != null ? (
            <>
              <Text scale="dense" style={[s.trend, { color: consTrend.color }]} numberOfLines={1}>
                {consTrend.text}
              </Text>
              <Text scale="dense" style={s.label}>30d</Text>
            </>
          ) : null}
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
    gap: space.xs,
  },
  rank: {
    fontFamily: fonts.data,
    fontSize: 11,
    fontVariant: ['tabular-nums'],
    color: chalk.base,
  },
  sep: { color: ink.line, fontSize: 11 },
  trend: { fontFamily: fonts.uiSemi, fontSize: 11 },
  label: {
    fontFamily: fonts.uiSemi,
    fontSize: 11, // PRD-04: 10px legacy label raised to the 11px floor
    color: chalk.dim,
    letterSpacing: 0.5,
  },
});

// ── Legacy branch (flag off) — pre-teardown rendering, byte-for-byte ────────
// DELETE when `visual.chalkline_cleanup` is removed. Trend green/red moved to
// semantic.pos/neg above — identical hex values, unflagged rename.
const LEGACY = {
  text: '#e8eaf0',
  muted: '#7a7f96',
  border: '#2a2d3a',
} as const;

const legacyStyles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  rank: { color: LEGACY.text, fontSize: 11, fontWeight: '700' },
  sep: { color: LEGACY.border, fontSize: 11 },
  trend: { fontSize: 11, fontWeight: '800' },
  label: {
    color: LEGACY.muted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
});
