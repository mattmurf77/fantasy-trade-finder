import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Icon, Text } from './chalkline';
import { UsageLeagueList, type UsageLeagueRow } from './UsageLeagueList';
import { chalk, flare, fonts, ice, ink, position, radii, semantic, space, type } from '../theme/chalkline';
import type { UsageMetric, UsagePlayer } from '../api/usageTrends';
import {
  isNewsWeek,
  lastColumn,
  shortName,
  weekCell,
  type LeagueStatus,
  type StatsSort,
  type UsageUnit,
} from '../utils/usageTrends';

// Usage Trends Version B — the raw stats table, modeled on the snap-count
// sheet the operator worked from: one column per week for the selected stat,
// a TOTAL column on the right (average for % of team), then icon-only
// actions: + (add) or ⇄ (trade), the podium (Re-rank), and a chevron that
// expands the row into the caller's other leagues.

const WEEK_W = 31;
const LAST_W = 42;
const ACT_W = 40;
const CHEV_W = 32;

// 32pt visual box, 40×44 touch target inside its column.
const ICON_SLOP = { top: 6, bottom: 6, left: 4, right: 4 };

/** Table width for a week count: four weeks fit a phone exactly; each extra
 *  week adds one column, and the host scrolls the table sideways. */
export function statsTableWidth(screenWidth: number, weekCount: number): number {
  return screenWidth + Math.max(0, weekCount - 4) * WEEK_W;
}

const POS_COLOR: Record<string, string> = { RB: position.rb, WR: position.wr, TE: position.te };

export function UsageStatsHeader({
  weeks,
  unit,
  sort,
  onSort,
}: {
  weeks: number[];
  unit: UsageUnit;
  sort: StatsSort | null;
  onSort: (key: StatsSort['key']) => void;
}) {
  // Every column sorts (operator, 2026-10-10). Tap: biggest first (A-Z for
  // Player), tap again: reversed, a third tap: back to the default order.
  const head = (key: StatsSort['key'], label: string, spoken: string, colStyle: object, testKey: string) => {
    const active = sort?.key === key;
    const dirWord = active ? (sort!.dir === 'asc' ? 'ascending' : 'descending') : 'not sorted';
    return (
      <Pressable
        key={testKey}
        testID={`usage-trends.sort.${testKey}`}
        accessibilityRole="button"
        accessibilityLabel={`Sort by ${spoken}, ${dirWord}`}
        onPress={() => onSort(key)}
        hitSlop={{ top: 8, bottom: 8 }}
        style={[styles.headPress, colStyle, key === 'player' ? styles.headLeft : styles.headRight]}
      >
        <Text scale="dense" style={[styles.headCell, active && styles.headActive]}>{label}</Text>
        {active ? (
          <Icon name={sort!.dir === 'asc' ? 'chevron-up' : 'chevron-down'} size={10} color={ice.base} />
        ) : null}
      </Pressable>
    );
  };
  return (
    <View style={styles.headerRow}>
      {head('player', 'Player', 'player name', styles.playerCol, 'player')}
      {weeks.map((w, i) => head(i, `W${w}`, `week ${w}`, styles.weekCol, `w${w}`))}
      {head('total', unit === 'share' ? 'Avg' : 'Tot', unit === 'share' ? 'average' : 'total', styles.lastCol, 'total')}
      <View style={{ width: ACT_W * 2 + CHEV_W }} />
    </View>
  );
}

export interface UsageStatsRowProps {
  player: UsagePlayer;
  metric: UsageMetric;
  unit: UsageUnit;
  weeks: number[];
  focusStatus: LeagueStatus;
  expanded: boolean;
  leagueRows: UsageLeagueRow[];
  onToggle: () => void;
  onAdd: () => void;
  onTrade: () => void;
  onRerank: () => void;
  onLeagueAdd: (leagueId: string) => void;
  onLeagueTrade: (leagueId: string) => void;
}

export function UsageStatsRow({
  player,
  metric,
  unit,
  weeks,
  focusStatus,
  expanded,
  leagueRows,
  onToggle,
  onAdd,
  onTrade,
  onRerank,
  onLeagueAdd,
  onLeagueTrade,
}: UsageStatsRowProps) {
  const block = player[metric];
  const id = player.player_id;
  const unitWord = unit === 'share' ? 'percent of team' : metric;
  const spoken =
    `${player.name}, ${player.position}, ${player.team}. ` +
    weeks.map((w, i) => `Week ${w} ${weekCell(player, block, i, unit)}`).join(', ') +
    `. ${unit === 'share' ? 'Average' : 'Total'} ${lastColumn(block, unit)} ${unitWord}.`;
  return (
    <View style={[styles.rowWrap, expanded && styles.rowWrapOpen]}>
      <View style={styles.row} testID={`usage-trends.row.${id}`}>
        <Pressable
          style={styles.dataArea}
          onPress={onToggle}
          accessibilityRole="button"
          accessibilityLabel={spoken}
          accessibilityHint={expanded ? 'Hides your other leagues' : 'Shows this player in your other leagues'}
          accessibilityState={{ expanded }}
        >
          <View style={styles.playerCol}>
            <Text scale="dense" style={styles.name} numberOfLines={1}>{shortName(player.name)}</Text>
            <Text scale="dense" style={styles.meta} numberOfLines={1}>
              <Text style={{ color: POS_COLOR[player.position] ?? chalk.dim }}>{player.position}</Text>
              {` · ${player.team}`}
            </Text>
          </View>
          {weeks.map((w, i) => {
            const st = player.status[i];
            const cell = weekCell(player, block, i, unit);
            const style = st === 'out'
              ? styles.flagOut
              : st === 'bye'
                ? styles.flagBye
                : isNewsWeek(block.signal, w) ? styles.news : null;
            return (
              <Text key={w} scale="dense" style={[styles.cell, styles.weekCol, style]}>{cell}</Text>
            );
          })}
          <Text scale="dense" style={[styles.cell, styles.lastCol, styles.total]}>{lastColumn(block, unit)}</Text>
        </Pressable>
        <View style={styles.actCell}>
          {focusStatus === 'free_agent' ? (
            <Pressable
              testID={`usage-trends.action.${id}`}
              accessibilityRole="button"
              accessibilityLabel={`Add ${player.name}`}
              onPress={onAdd}
              hitSlop={ICON_SLOP}
              style={({ pressed }) => [styles.iconBtn, pressed && styles.pressed]}
            >
              <Icon name="plus" size={16} color={chalk.base} />
            </Pressable>
          ) : focusStatus === 'rostered' ? (
            <Pressable
              testID={`usage-trends.action.${id}`}
              accessibilityRole="button"
              accessibilityLabel={`Find a trade for ${player.name}`}
              onPress={onTrade}
              hitSlop={ICON_SLOP}
              style={({ pressed }) => [styles.iconBtn, pressed && styles.pressed]}
            >
              <Icon name="trade" size={16} color={chalk.base} />
            </Pressable>
          ) : focusStatus === 'mine' ? (
            <View accessible accessibilityLabel="On your roster" testID={`usage-trends.yours.${id}`}>
              <Icon name="check" size={16} color={chalk.dim} />
            </View>
          ) : null}
        </View>
        <Pressable
          testID={`usage-trends.rerank.${id}`}
          accessibilityRole="button"
          accessibilityLabel={`Re-rank ${player.name} in Quick Set`}
          onPress={onRerank}
          style={({ pressed }) => [styles.actCell, pressed && styles.pressed]}
        >
          <Icon name="podium" size={18} color={chalk.dim} />
        </Pressable>
        <Pressable
          testID={`usage-trends.availability.${id}`}
          accessibilityRole="button"
          accessibilityLabel={expanded ? `Hide ${player.name}'s other leagues` : `Show ${player.name} in your other leagues`}
          accessibilityState={{ expanded }}
          onPress={onToggle}
          style={styles.chevCell}
        >
          <Icon name={expanded ? 'chevron-down' : 'chevron-right'} size={16} color={chalk.dim} />
        </Pressable>
      </View>
      {expanded ? (
        <View style={styles.expand} testID={`usage-trends.expand.${id}`}>
          <UsageLeagueList player={player} rows={leagueRows} onAdd={onLeagueAdd} onTrade={onLeagueTrade} compact />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  headerRow: {
    flexDirection: 'row',
    alignItems: 'stretch',
    minHeight: 36,
    paddingLeft: space.lg,
    paddingRight: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: ink.lineStrongA11y,
  },
  headCell: { ...type.label },
  headActive: { color: ice.base },
  headPress: { flexDirection: 'row', alignItems: 'flex-end', gap: 2, paddingBottom: 6 },
  headLeft: { justifyContent: 'flex-start' },
  headRight: { justifyContent: 'flex-end' },
  playerCol: { flex: 1, minWidth: 0, paddingRight: space.xs },
  weekCol: { width: WEEK_W, textAlign: 'right' },
  lastCol: { width: LAST_W, textAlign: 'right' },
  rowWrap: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: ink.line },
  rowWrapOpen: { backgroundColor: ink.ink1 },
  row: { flexDirection: 'row', alignItems: 'center', paddingLeft: space.lg, paddingRight: space.sm, minHeight: 52 },
  dataArea: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', minHeight: 52 },
  name: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
  meta: { ...type.label, textTransform: 'none', letterSpacing: 0.4 },
  cell: { ...type.data },
  total: { fontFamily: fonts.dataSemi },
  news: { color: flare.base, fontFamily: fonts.dataSemi },
  flagOut: { ...type.label, color: semantic.warn, lineHeight: 18 },
  flagBye: { ...type.label, lineHeight: 18 },
  actCell: { width: ACT_W, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  iconBtn: {
    width: 32,
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: ink.lineStrongA11y,
    borderRadius: radii.sm,
  },
  pressed: { backgroundColor: ink.ink3 },
  chevCell: { width: CHEV_W, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  expand: { paddingHorizontal: space.lg, paddingBottom: space.sm },
});
