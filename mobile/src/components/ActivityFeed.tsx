import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import { relativeTime } from '../utils/relativeTime';
import type { ActivityEvent } from '../shared/types';

// Renders a list of activity-feed rows for the League tab. Caller decides
// whether the section is mounted at all (flag-gated upstream); we just
// render the rows and an empty-state when the events list is empty.
//
// The backend's `summary` string is already formatted with "@username verb …
// (Nm ago)". We strip the trailing "(… ago)" because it grows stale and we
// render our own relative timestamp on the right side of the row.

interface Props {
  events: ActivityEvent[];
  limit?: number;
}

const TRAILING_AGO_RE = /\s*\([^)]*ago\)\s*$/;

export default function ActivityFeed({ events, limit = 10 }: Props) {
  const rows = events.slice(0, limit);

  if (rows.length === 0) {
    return (
      <View style={styles.card}>
        <Text style={styles.empty}>
          No recent activity. Once leaguemates rank or trade, it shows up here.
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.card}>
      {rows.map((e, idx) => (
        <View
          key={e.id}
          style={[styles.row, idx === rows.length - 1 && styles.rowLast]}
        >
          <Text style={styles.emoji}>{e.emoji || '•'}</Text>
          <Text style={styles.summary} numberOfLines={2}>
            {e.summary.replace(TRAILING_AGO_RE, '')}
          </Text>
          <Text style={styles.time}>{relativeTime(e.occurred_at)}</Text>
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
  emoji: { fontSize: 16, width: 22, textAlign: 'center' },
  summary: {
    flex: 1,
    color: colors.text,
    fontSize: fontSize.sm,
    lineHeight: 18,
  },
  time: {
    color: colors.muted,
    fontSize: fontSize.xs,
    fontWeight: '700',
    marginLeft: spacing.xs,
  },
  empty: {
    color: colors.muted,
    fontSize: fontSize.sm,
    textAlign: 'center',
    paddingVertical: spacing.sm,
  },
});
