import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

import { ink, chalk, space, type, fonts } from '../theme/chalkline';
import { Card } from './chalkline';
import type { ContrarianRow } from '../shared/types';

// Sorted leaguemate list with a divergence score. Caller passes rows
// already aggregated across positions (see api/league.ts:getContrarianLeaderboard).
// Mirrors the web's contrarian leaderboard but flattened to a single list —
// the per-position breakdown would be too cramped for mobile.
//
// Chalkline: hairline rows, rank numerals + score in Plex Mono (type.data);
// score is a bare number per the ScorePill spec — no tinted chip box.

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
      <Card>
        <Text style={styles.empty}>
          {message || 'Invite leaguemates to unlock — need 3+ ranking-takers.'}
        </Text>
      </Card>
    );
  }

  if (rows.length === 0) {
    return (
      <Card>
        <Text style={styles.empty}>No divergence data yet.</Text>
      </Card>
    );
  }

  return (
    <Card>
      {rows.map((r, idx) => (
        <View
          key={r.user_id}
          style={[styles.row, idx === rows.length - 1 && styles.rowLast]}
        >
          <Text style={styles.rank}>{idx + 1}</Text>
          <Text style={styles.name} numberOfLines={1}>
            @{r.username || r.user_id}
          </Text>
          <View style={styles.score}>
            <Text style={styles.scoreValue}>{r.divergence_score.toFixed(1)}</Text>
            <Text style={styles.scoreUnit}>ELO Δ</Text>
          </View>
        </View>
      ))}
    </Card>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingVertical: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  rowLast: { borderBottomWidth: 0 },
  rank: {
    ...type.data,
    color: chalk.dim,
    width: 24,
    textAlign: 'right',
  },
  name: {
    ...type.body,
    fontFamily: fonts.uiSemi,
    flex: 1,
  },
  score: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: space.xs,
  },
  scoreValue: {
    ...type.data,
  },
  scoreUnit: {
    ...type.label,
    color: chalk.faint,
  },
  empty: {
    ...type.bodySm,
    textAlign: 'center',
    paddingVertical: space.sm,
  },
});
