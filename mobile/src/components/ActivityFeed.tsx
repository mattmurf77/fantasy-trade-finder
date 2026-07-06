import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

import { ink, chalk, semantic, space, type } from '../theme/chalkline';
import { Card, Icon } from './chalkline';
import type { IconName } from './chalkline';
import { relativeTime } from '../utils/relativeTime';
import type { ActivityEvent } from '../shared/types';

// Renders a list of activity-feed rows for the League tab. Caller decides
// whether the section is mounted at all (flag-gated upstream); we just
// render the rows and an empty-state when the events list is empty.
//
// The backend's `summary` string is already formatted with "@username verb …
// (Nm ago)". We strip the trailing "(… ago)" because it grows stale and we
// render our own relative timestamp on the right side of the row.
//
// Chalkline: the backend's `emoji` field is intentionally ignored — rows lead
// with a Chalkline icon derived from event_type (status color on check/x).

interface Props {
  events: ActivityEvent[];
  limit?: number;
}

const TRAILING_AGO_RE = /\s*\([^)]*ago\)\s*$/;

const EVENT_ICONS: Record<string, { name: IconName; color: string }> = {
  trade_match:    { name: 'match', color: chalk.dim },
  trade_accepted: { name: 'check', color: semantic.pos },
  trade_declined: { name: 'x',     color: semantic.neg },
  tier_save:      { name: 'rank',  color: chalk.dim },
  league_sync:    { name: 'swap',  color: chalk.dim },
  unlock:         { name: 'eye',   color: chalk.dim },
};
const DEFAULT_ICON: { name: IconName; color: string } = {
  name: 'match',
  color: chalk.dim,
};

export default function ActivityFeed({ events, limit = 10 }: Props) {
  const rows = events.slice(0, limit);

  if (rows.length === 0) {
    return (
      <Card>
        <Text style={styles.empty}>
          No recent activity. Once leaguemates rank or trade, it shows up here.
        </Text>
      </Card>
    );
  }

  return (
    <Card>
      {rows.map((e, idx) => {
        const icon = EVENT_ICONS[e.event_type] ?? DEFAULT_ICON;
        return (
          <View
            key={e.id}
            style={[styles.row, idx === rows.length - 1 && styles.rowLast]}
          >
            <View style={styles.iconWrap}>
              <Icon name={icon.name} size={16} color={icon.color} />
            </View>
            <Text style={styles.summary} numberOfLines={2}>
              {e.summary.replace(TRAILING_AGO_RE, '')}
            </Text>
            <Text style={styles.time}>{relativeTime(e.occurred_at)}</Text>
          </View>
        );
      })}
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
  iconWrap: { width: 22, alignItems: 'center' },
  summary: {
    ...type.body,
    flex: 1,
  },
  time: {
    ...type.data,
    color: chalk.faint,
    marginLeft: space.xs,
  },
  empty: {
    ...type.bodySm,
    textAlign: 'center',
    paddingVertical: space.sm,
  },
});
