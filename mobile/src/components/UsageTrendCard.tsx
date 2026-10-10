import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Svg, { Rect } from 'react-native-svg';

import { Icon, PositionBadge, Text } from './chalkline';
import { StatusPip } from './UsageLeagueList';
import { chalk, flare, fonts, ink, radii, semantic, space, type } from '../theme/chalkline';
import type { UsageMetric, UsagePlayer } from '../api/usageTrends';
import {
  availabilityLabel,
  headline,
  isNewsWeek,
  ofTeam,
  type LeagueStatus,
  type UsageUnit,
} from '../utils/usageTrends';

// Usage Trends Version A — "Who's rising" story card, built to the
// operator-approved draft (canvas artboard Main.dc.html, 2026-10-10): name ·
// position · team, ONE plain sentence, four week bars (the news week in
// flare, a missed game as an amber baseline tick), then Add / Trade / Yours,
// the cross-league availability pill, and Re-rank.

const BAR_MAX = 36;
const CHART_H = 40;
const CHART_MAX_W = 64;

// Four weeks draw exactly as the approved mock (10pt bars, 4pt gaps). A
// longer user-picked selection shrinks the bars to stay within ~64pt.
function barGeometry(n: number): { w: number; gap: number } {
  if (n <= 4) return { w: 10, gap: 4 };
  return { w: Math.max(3, Math.floor((CHART_MAX_W - (n - 1) * 2) / n)), gap: 2 };
}

function WeekBars({ player, metric, weeks }: { player: UsagePlayer; metric: UsageMetric; weeks: number[] }) {
  const block = player[metric];
  const { w: BAR_W, gap: BAR_GAP } = barGeometry(weeks.length);
  const width = weeks.length * BAR_W + (weeks.length - 1) * BAR_GAP;
  const spoken = weeks
    .map((w, i) => {
      const st = player.status[i];
      if (st === 'out') return `Week ${w}: did not play`;
      if (st === 'bye') return `Week ${w}: bye`;
      return `Week ${w}: ${Math.round(block.shares[i] ?? 0)} percent`;
    })
    .join('. ');
  return (
    <View style={styles.chart} accessible accessibilityRole="image"
      accessibilityLabel={`${spoken}, ${ofTeam(player.team, metric)}`}>
      <Svg width={width} height={CHART_H} viewBox={`0 0 ${width} ${CHART_H}`}>
        {weeks.map((w, i) => {
          const x = i * (BAR_W + BAR_GAP);
          const st = player.status[i];
          if (st === 'out') {
            return <Rect key={w} x={x} y={CHART_H - 2} width={BAR_W} height={2} fill={semantic.warn} />;
          }
          if (st === 'bye') return null;
          const h = Math.max(2, Math.round(((block.shares[i] ?? 0) / 100) * BAR_MAX));
          const fill = isNewsWeek(block.signal, w) ? flare.base : ink.lineStrongA11y;
          return <Rect key={w} x={x} y={CHART_H - h} width={BAR_W} height={h} fill={fill} />;
        })}
      </Svg>
      {weeks.length <= 4 ? (
        <View style={[styles.weekLabels, { gap: BAR_GAP }]} importantForAccessibility="no-hide-descendants">
          {weeks.map((w, i) => {
            const st = player.status[i];
            const color = st === 'out' ? semantic.warn : isNewsWeek(block.signal, w) ? flare.base : chalk.dim;
            return (
              <Text key={w} scale="dense" style={[styles.weekLabel, { width: BAR_W, color }]}>
                {st === 'played' ? String(w) : '–'}
              </Text>
            );
          })}
        </View>
      ) : (
        <View style={[styles.weekLabelsSpan, { width }]} importantForAccessibility="no-hide-descendants">
          <Text scale="dense" style={styles.weekLabel}>{weeks[0]}</Text>
          <Text scale="dense" style={styles.weekLabel}>{weeks[weeks.length - 1]}</Text>
        </View>
      )}
    </View>
  );
}

export interface UsageTrendCardProps {
  player: UsagePlayer;
  metric: UsageMetric;
  unit: UsageUnit;
  weeks: number[];
  focusStatus: LeagueStatus;
  /** Statuses across the caller's leagues, focused league first (pips). */
  leagueStatuses: LeagueStatus[];
  onAdd: () => void;
  onTrade: () => void;
  onRerank: () => void;
  onAvailability: () => void;
}

export default function UsageTrendCard({
  player,
  metric,
  unit,
  weeks,
  focusStatus,
  leagueStatuses,
  onAdd,
  onTrade,
  onRerank,
  onAvailability,
}: UsageTrendCardProps) {
  const latest = weeks.length ? weeks[weeks.length - 1] : null;
  const known = leagueStatuses.filter((s) => s !== 'unknown');
  const fa = known.filter((s) => s === 'free_agent').length;
  const mine = known.filter((s) => s === 'mine').length;
  const pillLabel = availabilityLabel({ known: known.length, freeAgent: fa });
  const pillSpoken =
    `Free agent in ${fa} of your ${known.length} leagues` +
    (mine ? `, on your roster in ${mine}` : '') + '. See your leagues';
  const id = player.player_id;
  return (
    <View style={styles.card} testID={`usage-trends.row.${id}`}>
      <View style={styles.top}>
        <View style={styles.text}>
          <View style={styles.nameRow}>
            <Text style={styles.name} numberOfLines={1}>{player.name}</Text>
            <PositionBadge pos={player.position} />
            <Text style={type.bodySm}>{player.team}</Text>
          </View>
          <Text style={styles.sentence}>{headline(player, metric, player[metric], latest, unit)}</Text>
        </View>
        <WeekBars player={player} metric={metric} weeks={weeks} />
      </View>
      <View style={styles.actions}>
        {focusStatus === 'free_agent' ? (
          <Pressable
            testID={`usage-trends.action.${id}`}
            accessibilityRole="button"
            accessibilityLabel={`Add ${player.name}`}
            onPress={onAdd}
            style={({ pressed }) => [styles.btn, pressed && styles.pressed]}
          >
            <Icon name="plus" size={16} color={chalk.base} />
            <Text style={styles.btnText}>Add</Text>
          </Pressable>
        ) : focusStatus === 'rostered' ? (
          <Pressable
            testID={`usage-trends.action.${id}`}
            accessibilityRole="button"
            accessibilityLabel={`Find a trade for ${player.name}`}
            onPress={onTrade}
            style={({ pressed }) => [styles.btn, pressed && styles.pressed]}
          >
            <Icon name="trade" size={16} color={chalk.base} />
            <Text style={styles.btnText}>Trade</Text>
          </Pressable>
        ) : focusStatus === 'mine' ? (
          <View style={styles.yours} testID={`usage-trends.yours.${id}`}>
            <Icon name="check" size={16} color={chalk.dim} />
            <Text style={styles.yoursText}>Yours</Text>
          </View>
        ) : null}
        {known.length ? (
          <Pressable
            testID={`usage-trends.availability.${id}`}
            accessibilityRole="button"
            accessibilityLabel={pillSpoken}
            onPress={onAvailability}
            style={({ pressed }) => [styles.pill, pressed && styles.pressed]}
          >
            {known.length <= 5 ? (
              <View style={styles.pips}>
                {leagueStatuses.map((s, i) => <StatusPip key={i} status={s} />)}
              </View>
            ) : null}
            <Text scale="dense" style={styles.pillText}>{pillLabel}</Text>
            <Icon name="chevron-right" size={16} color={chalk.dim} />
          </Pressable>
        ) : null}
        <Pressable
          testID={`usage-trends.rerank.${id}`}
          accessibilityRole="button"
          accessibilityLabel={`Re-rank ${player.name} in Quick Set`}
          onPress={onRerank}
          style={({ pressed }) => [styles.rerank, pressed && styles.pressed]}
        >
          <Icon name="podium" size={16} color={chalk.dim} />
          <Text style={styles.rerankText}>Re-rank</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    paddingVertical: space.md,
    paddingHorizontal: 14,
    gap: 10,
  },
  top: { flexDirection: 'row', gap: space.md, alignItems: 'flex-start' },
  text: { flex: 1, minWidth: 0, gap: space.xs },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  name: { ...type.title, flexShrink: 1 },
  sentence: { ...type.body, fontSize: 15, lineHeight: 20, fontFamily: fonts.uiMedium },
  chart: { alignItems: 'center', gap: space.xs, flexShrink: 0 },
  weekLabels: { flexDirection: 'row' },
  weekLabelsSpan: { flexDirection: 'row', justifyContent: 'space-between' },
  weekLabel: { ...type.data, fontSize: 11, lineHeight: 14, color: chalk.dim, textAlign: 'center' },
  actions: { flexDirection: 'row', alignItems: 'center', gap: space.sm, flexWrap: 'wrap' },
  btn: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: ink.lineStrongA11y,
    borderRadius: radii.sm,
  },
  btnText: { ...type.body, fontFamily: fonts.uiSemi },
  pressed: { backgroundColor: ink.ink3 },
  yours: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: space.xs },
  yoursText: { ...type.body, fontFamily: fonts.uiSemi, color: chalk.dim },
  pill: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: 10,
    borderWidth: 1,
    borderColor: ink.lineStrongA11y,
    borderRadius: radii.sm,
  },
  pips: { flexDirection: 'row', gap: 3 },
  pillText: { ...type.data },
  rerank: {
    marginLeft: 'auto',
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: space.xs,
  },
  rerankText: { ...type.body, fontFamily: fonts.uiSemi, color: chalk.dim },
});
