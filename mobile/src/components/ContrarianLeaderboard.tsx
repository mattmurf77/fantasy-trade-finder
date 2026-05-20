import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import type { ContrarianRow } from '../shared/types';

// Sorted leaguemate list with a divergence-score chip. Caller passes rows
// already aggregated across positions (see api/league.ts:getContrarianLeaderboard).
// Mirrors the web's contrarian leaderboard but flattened to a single list —
// the per-position breakdown would be too cramped for mobile.

interface Props {
  rows: ContrarianRow[];
  insufficientData?: boolean;
  message?: string;
}

export default function ContrarianLeaderboard({
  rows,
  insufficientData,
  message,
}: Props) {
  if (insufficientData) {
    return (
      <View style={styles.card}>
        <Text style={styles.empty}>
          {message || 'Invite leaguemates to unlock — need 3+ ranking-takers.'}
        </Text>
      </View>
    );
  }

  if (rows.length === 0) {
    return (
      <View style={styles.card}>
        <Text style={styles.empty}>No divergence data yet.</Text>
      </View>
    );
  }

  return (
    <View style={styles.card}>
      {rows.map((r, idx) => (
        <View
          key={r.user_id}
          style={[styles.row, idx === rows.length - 1 && styles.rowLast]}
        >
          <Text style={styles.rank}>{idx + 1}</Text>
          <Text style={styles.name} numberOfLines={1}>
            @{r.username || r.user_id}
          </Text>
          <View style={styles.scoreChip}>
            <Text style={styles.scoreText}>{r.divergence_score.toFixed(1)}</Text>
            <Text style={styles.scoreUnit}>ELO Δ</Text>
          </View>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: spacing.md,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  rowLast: { borderBottomWidth: 0 },
  rank: {
    color: colors.muted,
    fontSize: fontSize.sm,
    fontWeight: '800',
    width: 24,
    textAlign: 'right',
  },
  name: {
    flex: 1,
    color: colors.text,
    fontSize: fontSize.sm,
    fontWeight: '700',
  },
  scoreChip: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: 'rgba(79,124,255,0.35)',
    backgroundColor: 'rgba(79,124,255,0.10)',
  },
  scoreText: {
    color: colors.accent,
    fontSize: fontSize.sm,
    fontWeight: '800',
  },
  scoreUnit: {
    color: colors.accent,
    fontSize: 10,
    fontWeight: '700',
    opacity: 0.8,
  },
  empty: {
    color: colors.muted,
    fontSize: fontSize.sm,
    textAlign: 'center',
    paddingVertical: spacing.sm,
  },
});
