import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Text } from '../chalkline';
import { chalk, fonts, ink, radii, space, type } from '../../theme/chalkline';
import { getLeagueProjectionBatch } from '../../api/leagueProjections';
import { NO_LEAGUE_ID, useSession } from '../../state/useSession';
import { useFlag } from '../../state/useFeatureFlags';
import { NEXT_MOVE_EMPTY_FLAG, NEXT_MOVE_FLAG, nextMoveEmptyView, nextMoveView, type NextMoveView } from '../../utils/homeNextMove';
import type { LiveRoster } from '../../utils/playoffTargets';
import { RowAction } from './StatusRow';

// Home's next move (flag `league.next_move`; docs/plans/home-next-move/
// scope.md, D-278): ONE player and ONE action under the playoff card, from
// the server's `next_move` block. Everything shown is decided in
// utils/homeNextMove; this file only renders. NO new request: the block
// rides the one cached forecast read the card uses (same key, fetcher and
// staleTime as HomePlayoffBanner), and the live rosters are HomeHub's shared
// ['league-rosters', leagueId] query, passed in. Nothing to show ⇒ nothing
// rendered (no placeholder, no error). HomeHub owns the tap (event, "‹ Home"
// arm, navigation).
//
// With `league.next_move_empty` (D-279, docs/plans/next-move-empty/
// scope.md) the same row also shows when there is no move: the label and one
// line from utils/homeNextMove `nextMoveEmptyView`, no button, not tappable,
// no event. That flag off ⇒ exactly the build 199 row.

interface Props {
  rosters: LiveRoster[] | null | undefined;
  /** The viewer's own live roster (`findMyRoster(...)?.players`). */
  liveIds: string[] | null | undefined;
  onPress: (view: NextMoveView) => void;
}

export default function HomeNextMove({ rosters, liveIds, onPress }: Props) {
  const leagueId = useSession(s => s.league?.league_id);
  const userId = useSession(s => s.user?.user_id);
  const hasToken = useSession(s => s.hasToken);
  const switching = useSession(s => s.switching);
  const platform = useSession(s => s.leagues.find(l => l.league_id === leagueId)?.platform ?? 'sleeper');
  const enabled = useFlag('league.projections');
  const flagOn = useFlag(NEXT_MOVE_FLAG);
  const available = flagOn && enabled && hasToken && !switching && !!userId && !!leagueId
    && leagueId !== NO_LEAGUE_ID && platform === 'sleeper';
  const query = useQuery({ queryKey: ['league-projection-batch', userId, leagueId],
    queryFn: () => getLeagueProjectionBatch(leagueId!), enabled: available, staleTime: 60_000 });
  const emptyOn = useFlag(NEXT_MOVE_EMPTY_FLAG);
  const view = available ? nextMoveView(query.data, flagOn, rosters, liveIds) : null;
  if (!view) {
    const empty = available ? nextMoveEmptyView(query.data, flagOn, emptyOn, rosters, liveIds) : null;
    if (!empty) return null;
    return <View testID="home.next-move" accessible accessibilityLabel={empty.accessibilityLabel} style={styles.card}>
      <View style={styles.text}>
        <Text scale="dense" style={type.label}>{empty.label}</Text>
        <Text testID="home.next-move.none" style={styles.line}>{empty.line}</Text>
      </View>
    </View>;
  }
  return <Pressable testID="home.next-move" accessibilityRole="button" accessibilityLabel={view.accessibilityLabel}
    onPress={() => onPress(view)} style={({ pressed }) => [styles.card, pressed ? styles.pressed : null]}>
    <View style={styles.text}>
      <Text scale="dense" style={type.label}>{view.label}</Text>
      <Text testID="home.next-move.line" style={styles.line}>{view.line}</Text>
    </View>
    <RowAction label={view.actionLabel} />
  </Pressable>;
}

// The playoff card's construction (ink-1, hairline, radius md), directly
// under it. The whole row is the target (44pt minimum); ice only on the
// RowAction, as on the card's "View ›".
const styles = StyleSheet.create({
  card: {
    marginBottom: space.sm,
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
  },
  pressed: { backgroundColor: ink.ink3 },
  text: { flex: 1, minWidth: 0, gap: 2 },
  line: { fontFamily: fonts.uiSemi, fontSize: 14, lineHeight: 20, color: chalk.base },
});
