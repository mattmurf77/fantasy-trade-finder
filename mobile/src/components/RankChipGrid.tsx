import React, { useCallback } from 'react';
import { View, Text, StyleSheet, Pressable, FlatList } from 'react-native';

import {
  ink,
  chalk,
  ice,
  position as positionColors,
  space,
  radii,
  fonts,
} from '../theme/chalkline';
import { Text as ChalkText } from './chalkline';
import { useFlag } from '../state/useFeatureFlags';

// Quick Rank's chip grammar, extracted (roster-first setup prd §8) so the
// setup's inline rank step and QuickRankScreen render the SAME grid: every
// player is a chip, a tap stamps the next rank number (click order), a
// second tap unclicks and the rest renumber. The grid only RENDERS the
// stamps — the click order lives with the host, which also decides what a
// save posts. Extracted verbatim from QuickRankScreen (#136/#138/#140,
// S2 PRD-04); QuickRank's behaviour is unchanged.
//
// `testID` is the chip id PREFIX: chip N carries `${testID}.${player.id}`
// (QuickRank passes `quick-rank.chip`, which is what its capture flow and
// mobile/scripts/testid-lint.sh grep for).

// #140 — same conditional-POS rule as the Quick set walk: the walks are
// position-scoped (the active tab names the position), so the chip's POS
// token is redundant and its width goes to TEAM + AGE. Conditional, not
// deleted: cross-position reuse flips this on.
const SHOW_POSITION = false;

export interface RankChipPlayer {
  id: string;
  name: string;
  position: string;
  team?: string | null;
  age?: number | null;
}

interface Props<T extends RankChipPlayer> {
  /** Chip id prefix — see the header. */
  testID: string;
  /** The chips to RENDER (a host may filter the view; stamps survive it). */
  players: T[];
  /** Click order — index IS the rank (0-based). */
  clicked: string[];
  onToggle: (id: string) => void;
  ListEmptyComponent?: React.ReactElement | null;
}

export default function RankChipGrid<T extends RankChipPlayer>({
  testID,
  players,
  clicked,
  onToggle,
  ListEmptyComponent,
}: Props<T>) {
  // S2 PRD-04 ride-along (flag visual.chalkline_cleanup): 9px chip metas
  // rise to the 11px type floor.
  const cleanup = useFlag('visual.chalkline_cleanup');

  const rankOf = useCallback(
    (pid: string) => {
      const i = clicked.indexOf(pid);
      return i === -1 ? null : i + 1;
    },
    [clicked],
  );

  const renderChip = useCallback(
    ({ item }: { item: T }) => {
      const rank = rankOf(item.id);
      const posKey = String(item.position).toLowerCase() as keyof typeof positionColors;
      return (
        <Pressable
          testID={`${testID}.${item.id}`}
          accessibilityRole="button"
          accessibilityState={{ selected: rank != null }}
          accessibilityLabel={
            rank != null ? `${item.name}, ranked ${rank}` : item.name
          }
          onPress={() => onToggle(item.id)}
          style={[styles.chip, rank != null && styles.chipSelected]}
        >
          <View style={styles.chipTop}>
            <Text style={styles.chipName} numberOfLines={1}>
              {item.name}
            </Text>
            {rank != null ? (
              <View style={styles.rankBadge}>
                <Text style={styles.rankBadgeText}>{rank}</Text>
              </View>
            ) : null}
          </View>
          {/* S2 PRD-04 ride-along — meta row through the chalkline Text
              primitive (dense Dynamic-Type tier); the 9px sizes rise to
              the 11px floor under visual.chalkline_cleanup. */}
          <View style={styles.chipMeta}>
            {SHOW_POSITION ? (
              <ChalkText
                scale="dense"
                style={[
                  styles.chipPos,
                  cleanup && styles.chipMetaFloor,
                  { color: positionColors[posKey] ?? chalk.dim },
                ]}
              >
                {item.position}
              </ChalkText>
            ) : null}
            <ChalkText scale="dense" style={[styles.chipTeam, cleanup && styles.chipMetaFloor]}>
              {item.team ?? 'FA'}
            </ChalkText>
            {item.age != null ? (
              <ChalkText scale="dense" style={[styles.chipAge, cleanup && styles.chipMetaFloor]}>
                {item.age}
              </ChalkText>
            ) : null}
          </View>
        </Pressable>
      );
    },
    [rankOf, onToggle, cleanup, testID],
  );

  return (
    <FlatList
      data={players}
      keyExtractor={(p) => p.id}
      renderItem={renderChip}
      extraData={clicked}
      numColumns={3}
      columnWrapperStyle={styles.gridRow}
      contentContainerStyle={styles.grid}
      keyboardShouldPersistTaps="handled"
      ListEmptyComponent={ListEmptyComponent}
    />
  );
}

const styles = StyleSheet.create({
  grid: {
    paddingHorizontal: space.lg,
    paddingBottom: 96, // room for the host's pinned footer bar
    gap: space.xs,
  },
  gridRow: { gap: space.xs },
  // Same small selectable card as the quick-set grid; selected = ice
  // border + the rank number badge (two signals).
  chip: {
    flex: 1,
    minHeight: 48,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    paddingHorizontal: space.sm,
    paddingVertical: 6,
    justifyContent: 'center',
  },
  chipSelected: { borderColor: ice.base },
  chipTop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  chipName: {
    fontFamily: fonts.uiSemi,
    fontSize: 12,
    color: chalk.base,
    flexShrink: 1,
  },
  // Rank number badge: data numeral (Plex Mono) on an ice-bordered square
  // — radius xs per the badge spec; number is the click order.
  rankBadge: {
    marginLeft: 'auto',
    minWidth: 16,
    height: 16,
    paddingHorizontal: 2,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ice.base,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rankBadgeText: {
    fontFamily: fonts.dataSemi,
    fontSize: 10,
    color: ice.base,
  },
  chipMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 2,
  },
  chipPos: {
    fontFamily: fonts.uiSemi,
    fontSize: 9,
    letterSpacing: 0.5,
  },
  chipTeam: {
    fontFamily: fonts.uiSemi,
    fontSize: 9,
    letterSpacing: 0.5,
    color: chalk.dim,
    textTransform: 'uppercase',
  },
  // #140 — age numeral: 9px Plex Mono (data-numeral rule), chalk-dim,
  // bare-gap separated like the rest of the meta row.
  chipAge: {
    fontFamily: fonts.data,
    fontSize: 9,
    color: chalk.dim,
  },
  // S2 PRD-04 (visual.chalkline_cleanup) — 11px type floor for the chip
  // meta row (was 9px; components.md updated). The 10px rank-badge numeral
  // is untouched: it sits inside a fixed 16px badge (raising it means
  // resizing the badge — a coordinated spec change, not a ride-along).
  chipMetaFloor: { fontSize: 11 },
});
