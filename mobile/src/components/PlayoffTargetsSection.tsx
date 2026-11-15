import React, { useEffect, useState } from 'react';
import { View, Pressable, StyleSheet } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Button, Icon, Text } from './chalkline';
import { ink, chalk, ice, space, type } from '../theme/chalkline';
import type { PlayoffTargets, PlayoffTargetRow } from '../api/leagueProjections';
import { track } from '../api/events';
import { useFinderTargets } from '../state/useFinderTargets';
import { TARGETS_COPY as C } from '../utils/playoffTargetsCopy';
import {
  rowLine1, rowLine1Parts, rowLine2, rowLine3, rowDetail, visibleRows, viewedProps, expandedProps,
  handOffToFinder, TARGETS_EVENTS, SCREEN, type SectionModel,
} from '../utils/playoffTargets';

// Playoff targets — the body of the fifth disclosure inside the user's OWN
// open team card on Standings (LeagueProjectionDetail mounts it after "Max PF
// moves"). The mirror of MaxPfMovesSection: which players on selling teams
// would raise the user's playoff chance. Everything shown is decided in
// utils/playoffTargets (`model`); this file only renders and wires the taps.
// It mounts when the disclosure opens, which is when the section body becomes
// visible (playoff_targets_viewed, once per opening of the card via
// `viewedRef`).
//
// NO request, ever: the block rides the one forecast read
// (['league-projection-batch', userId, leagueId]) and the live rosters are
// the page's own ['league-rosters', leagueId] query, both passed in.

interface Props {
  block: PlayoffTargets;
  model: SectionModel;
  /** Owned by the open team card, so the impression fires once per opening. */
  viewedRef: React.MutableRefObject<boolean>;
}

export function PlayoffTargetsBody({ block, model, viewedRef }: Props) {
  const navigation = useNavigation<any>();
  const [showAll, setShowAll] = useState(false);
  const [openRank, setOpenRank] = useState<number | null>(null);

  useEffect(() => {
    if (viewedRef.current) return;
    viewedRef.current = true;
    track(TARGETS_EVENTS.viewed, viewedProps(block, model), SCREEN);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onFindTrades = (row: PlayoffTargetRow) =>
    handOffToFinder(row, model.opponents[row.rank] ?? null, {
      setSide: (side, players) => useFinderTargets.getState().setSide(side, players),
      track,
      // Standings is a ROOT-stack push over 'Main': pop back to Main's Trades
      // tab with the canvas prefill (utils/playoffTargets.finderNavParams),
      // the same route Max PF moves' hand-off takes.
      navigate: (params) => navigation.popTo('Main', params),
      now: Date.now,
    });

  const toggleRow = (row: PlayoffTargetRow) => {
    const opening = openRank !== row.rank;
    setOpenRank(opening ? row.rank : null);
    if (opening) track(TARGETS_EVENTS.expanded, expandedProps(row), SCREEN);
  };

  const { rows, showAllButton } = visibleRows(model.listed, showAll);

  return <View style={styles.body} testID="standings.targets.body">
    {model.line ? <Text variant="bodySm" testID="standings.targets.line">{model.line}</Text> : null}

    {model.isList ? <>
      {model.baseline ? <Text variant="bodySm" testID="standings.targets.baseline">{model.baseline}</Text> : null}
      {model.changedLine ? <Text variant="bodySm" style={styles.strong} testID="standings.targets.changed">{model.changedLine}</Text> : null}
      {model.rosterLine ? <Text variant="bodySm" style={styles.strong} testID="standings.targets.roster-changed">{model.rosterLine}</Text> : null}
      {model.noTargetsLine ? <Text variant="bodySm" testID="standings.targets.no-targets">{model.noTargetsLine}</Text> : null}
      {model.noneAloneLine ? <Text variant="bodySm" testID="standings.targets.none-alone">{model.noneAloneLine}</Text> : null}
      {model.head ? <Text variant="label" style={styles.head}>{model.head}</Text> : null}
      {rows.map((row) => <TargetRow key={row.player_id} row={row} block={block}
        opponentId={model.opponents[row.rank] ?? null} open={openRank === row.rank}
        onToggle={() => toggleRow(row)} onFindTrades={() => onFindTrades(row)} />)}
      {showAllButton ? <Pressable accessibilityRole="button" testID="standings.targets.show-all"
        onPress={() => setShowAll(true)} style={styles.link}>
        <Text variant="bodySm" style={styles.linkText}>{C['C-SHOWALL']}</Text>
      </Pressable> : null}
      {model.foot ? <Text variant="bodySm">{model.foot}</Text> : null}
      {model.eligible ? <Text variant="bodySm">{model.eligible}</Text> : null}
    </> : null}
  </View>;
}

function TargetRow({ row, block, opponentId, open, onToggle, onFindTrades }: {
  row: PlayoffTargetRow; block: PlayoffTargets; opponentId: string | null; open: boolean;
  onToggle: () => void; onFindTrades: () => void;
}) {
  const p = rowLine1Parts(row);
  const line2 = rowLine2(row, block);
  const line3 = rowLine3(row);
  const d = open ? rowDetail(row, block, opponentId) : null;
  return <View style={styles.row}>
    <Pressable accessibilityRole="button" aria-expanded={open} testID={`standings.targets.row.${row.rank}`}
      accessibilityLabel={`${rowLine1(row)}. ${line2}. ${line3}`}
      onPress={onToggle} style={styles.rowHead}>
      <View style={styles.rowText}>
        <View style={styles.line1}>
          <Text variant="bodySm" style={[styles.strong, styles.name]} numberOfLines={1}>{p.name}</Text>
          <Text variant="bodySm">{p.position}</Text>
          <Text scale="dense" style={styles.num}>{p.gain}</Text>
        </View>
        <Text variant="bodySm" style={styles.strong}>{line2}</Text>
        <Text variant="bodySm" numberOfLines={1}>{line3}</Text>
      </View>
      <Icon name={open ? 'chevron-up' : 'chevron-down'} size={16} color={chalk.base} />
    </Pressable>
    {d ? <View style={styles.rowDetail} testID={`standings.targets.detail.${row.rank}`}>
      {d.weeks ? <Text variant="bodySm">{d.weeks}</Text> : null}
      {d.replaces ? <Text variant="bodySm">{d.replaces}</Text> : null}
      {d.openSpot ? <Text variant="bodySm">{d.openSpot}</Text> : null}
      {d.button ? <Button label={d.button} variant="secondary" onPress={onFindTrades}
        testID={`standings.targets.find.${row.rank}`} /> : null}
    </View> : null}
  </View>;
}

// MaxPfMovesSection's construction: ink-3 hairlines, 44pt rows, chalk text,
// mono numbers. Ice only on the tappable link (an action).
const styles = StyleSheet.create({
  body: { gap: space.sm },
  strong: { color: chalk.base },
  head: { marginTop: space.xs },
  row: { borderTopWidth: 1, borderTopColor: ink.ink3 },
  rowHead: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: space.sm, paddingVertical: space.xs },
  rowText: { flex: 1, minWidth: 0, gap: 2 },
  line1: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  name: { flexShrink: 1, minWidth: 0 },
  num: { ...type.data, marginLeft: 'auto', flexShrink: 0 },
  rowDetail: { gap: space.xs, paddingBottom: space.sm, alignItems: 'flex-start' },
  link: { minHeight: 44, justifyContent: 'center' },
  linkText: { color: ice.base },
});
