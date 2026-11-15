import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { Badge, Meter, Text } from '../chalkline';
import { chalk, flare, fonts, ice, ink, radii, space, type } from '../../theme/chalkline';
import { posColor } from '../../theme/colors';
import { useFlag } from '../../state/useFeatureFlags';
import {
  ordinal,
  rankPercentile,
  type PositionSplit,
  type SplitPos,
} from '../../utils/positionSplit';

// One Home hub position tile (scope.md D2/D3): your rank at P, your value
// against the league median, a 4px meter in the position hex and the flare
// Seller / Buyer badge (or "Mid-pack") — League rankings' TeamRow badge. Every number comes from the
// utils/positionSplit result the hub hands in — this file does no band,
// median or ordering arithmetic of its own.
//
// The tile itself is NOT a pressable wrapper: its controls are Buy and Sell
// (36pt visible, 44pt hit, inside the tile), so VoiceOver never meets a
// nested control. The side the user's band implies is drawn in ice on
// every banded tile (the hub's `emphasis`); it changes no behaviour. With no line at this position (no_split /
// no_median) Buy and Sell would promise directions the destination can't
// give, so they collapse into one "See P ranking" button.
//
// split === null is the loading state: static skeletons, Buy/Sell disabled,
// so a tap can never land on a list Home hasn't described.
//
// Body tap (flag `nav.home_position_roster`, docs/plans/position-tile-tap/
// scope.md, D-269): with `onOpen` passed, the tile's UPPER region (label,
// badge, rank, value, median, meter) is one pressable that opens League
// rankings filtered to this position with the user's own team drilled in.
// It is a SIBLING of the actions row, never a wrapper around Buy / Sell, so
// VoiceOver still never meets a nested control. Not pressable while loading.
// Without `onOpen` (flag off) the tile renders exactly as before.

const RAIL = 3;

// Static literal testIDs per position (testid-lint can't see template ids).
const IDS: Record<SplitPos, { tile: string; open: string; buy: string; sell: string; ranking: string }> = {
  QB: {
    tile: 'home.position.qb',
    open: 'home.position.qb.open',
    buy: 'home.position.qb.buy',
    sell: 'home.position.qb.sell',
    ranking: 'home.position.qb.ranking',
  },
  RB: {
    tile: 'home.position.rb',
    open: 'home.position.rb.open',
    buy: 'home.position.rb.buy',
    sell: 'home.position.rb.sell',
    ranking: 'home.position.rb.ranking',
  },
  WR: {
    tile: 'home.position.wr',
    open: 'home.position.wr.open',
    buy: 'home.position.wr.buy',
    sell: 'home.position.wr.sell',
    ranking: 'home.position.wr.ranking',
  },
  TE: {
    tile: 'home.position.te',
    open: 'home.position.te.open',
    buy: 'home.position.te.buy',
    sell: 'home.position.te.sell',
    ranking: 'home.position.te.ranking',
  },
};

interface Props {
  pos: SplitPos;
  /** null while the power-rankings payload loads. */
  split: PositionSplit | null;
  onBuy?: () => void;
  onSell?: () => void;
  onRanking?: () => void;
  /** Body tap: your roster at this position in League rankings. Passed only
   *  while flag `nav.home_position_roster` is on. */
  onOpen?: () => void;
  /** The ice side for this tile, if the hub picked it (utils/positionSplit
   *  emphasizedSides — every banded position, uncapped). */
  emphasis?: 'buy' | 'sell' | null;
}

export default function PositionTile({ pos, split, onBuy, onSell, onRanking, onOpen, emphasis = null }: Props) {
  const ids = IDS[pos];
  const color = posColor(pos);
  const lined = split?.state === 'shown';
  const you = split?.you ?? null;
  const suggested = emphasis;
  const body = (
    <>
      <View style={styles.head}>
        <Text scale="dense" style={[type.label, { color }]}>
          {pos}
        </Text>
        {split == null ? null : !lined ? (
          <Text scale="dense" style={styles.mid}>No clear split</Text>
        ) : you?.band ? (
          <Badge label={you.band} color={flare.base} colorText />
        ) : (
          <Text scale="dense" style={styles.mid}>Mid-pack</Text>
        )}
      </View>
      {split == null ? (
        <>
          <View style={[styles.skel, styles.skelRank]} />
          <View style={styles.skel} />
        </>
      ) : lined && you ? (
        <>
          <Text scale="display" style={type.dataLg}>
            {ordinal(you.rank)}
            <Text scale="display" style={styles.rankOf}>{` /${split.teamCount}`}</Text>
          </Text>
          {/* LeagueSummary TeamRow's rule: the pick-equivalent label, else
              the rounded number; nothing valued reads "—". */}
          <Text scale="dense" style={styles.val} numberOfLines={1}>
            {you.value > 0 ? (you.valueLabel ?? Math.round(you.value).toLocaleString('en-US')) : '—'}
          </Text>
          <Text scale="dense" style={styles.median} numberOfLines={1}>
            {split.median?.valueLabel ? `median ${split.median.valueLabel}` : 'League median'}
          </Text>
          <Meter value={rankPercentile(you.rank, split.teamCount)} color={color} />
        </>
      ) : (
        <Text scale="display" style={type.dataLg}>—</Text>
      )}
    </>
  );
  return (
    <View style={styles.tile} testID={ids.tile}>
      <View style={[styles.rail, { backgroundColor: color }]} />
      {onOpen && split != null ? (
        <Pressable
          testID={ids.open}
          onPress={onOpen}
          accessibilityRole="button"
          accessibilityLabel={openLabel(pos, split)}
          style={({ pressed }) => [styles.body, pressed && styles.bodyPressed]}
        >
          {body}
        </Pressable>
      ) : (
        body
      )}
      <View style={styles.actions}>
        {split != null && !lined ? (
          <SideButton label={`See ${pos} ranking`} testID={ids.ranking} onPress={onRanking} />
        ) : (
          <>
            <SideButton
              label="Buy"
              a11yLabel={`Buy ${pos}${suggested === 'buy' ? ', suggested' : ''}`}
              testID={ids.buy}
              suggested={suggested === 'buy'}
              disabled={split == null}
              onPress={onBuy}
            />
            <SideButton
              label="Sell"
              a11yLabel={`Sell ${pos}${suggested === 'sell' ? ', suggested' : ''}`}
              testID={ids.sell}
              suggested={suggested === 'sell'}
              disabled={split == null}
              onPress={onSell}
            />
          </>
        )}
      </View>
    </View>
  );
}

// "Your QBs, 3rd of 12. Opens your roster in League rankings." Built only
// from what the tile already shows; no rank when the tile shows none.
function openLabel(pos: SplitPos, split: PositionSplit): string {
  const you = split.state === 'shown' ? split.you : null;
  const rank = you ? `, ${ordinal(you.rank)} of ${split.teamCount}` : '';
  return `Your ${pos}s${rank}. Opens your roster in League rankings.`;
}

// The compact Secondary construction (components.md § Buttons) with an ice
// border + label for the suggested side. Not chalkline/Button because that
// primitive has no ice-outline variant and its 4pt hitSlop is flag-gated.
function SideButton({
  label,
  a11yLabel,
  testID,
  suggested = false,
  disabled = false,
  onPress,
}: {
  label: string;
  a11yLabel?: string;
  testID: string;
  suggested?: boolean;
  disabled?: boolean;
  onPress?: () => void;
}) {
  // Same contrast-raised border chalkline/Button's Secondary picks.
  const cleanup = useFlag('visual.chalkline_cleanup');
  const border = disabled
    ? ink.line
    : suggested
      ? ice.base
      : cleanup
        ? ink.lineStrongA11y
        : ink.lineStrong;
  const text = disabled ? chalk.faint : suggested ? ice.base : chalk.base;
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={disabled}
      hitSlop={{ top: 4, bottom: 4 }}
      accessibilityRole="button"
      accessibilityLabel={a11yLabel ?? label}
      accessibilityState={{ disabled }}
      style={({ pressed }) => [styles.side, { borderColor: border }, pressed && styles.sidePressed]}
    >
      <Text style={[styles.sideLabel, { color: text }]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  tile: {
    flex: 1,
    minWidth: 0,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    overflow: 'hidden',
    paddingTop: space.md,
    paddingHorizontal: space.sm,
    paddingBottom: space.sm,
    gap: space.xs,
  },
  // The body pressable stacks its children exactly as the tile does. It
  // reaches into the tile's top and side padding (negative margin, equal
  // padding), so the content does not move, the whole upper region answers
  // (well over 44pt tall) and the pressed fill reads as the tile's top. It
  // starts below the 3px rail so the press never hides the position colour.
  body: {
    gap: space.xs,
    marginTop: -(space.md - RAIL),
    marginHorizontal: -space.sm,
    paddingTop: space.md - RAIL,
    paddingHorizontal: space.sm,
  },
  bodyPressed: { backgroundColor: ink.ink3 },
  // 3px position rail across the top edge (data encoding, paired with the label).
  rail: { position: 'absolute', top: 0, left: 0, right: 0, height: RAIL },
  head: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: space.xs,
  },
  mid: { fontFamily: fonts.ui, fontSize: 11, lineHeight: 14, color: chalk.dim },
  rankOf: { fontFamily: fonts.data, fontSize: 11, color: chalk.dim },
  val: { ...type.data, fontFamily: fonts.dataSemi },
  median: {
    fontFamily: fonts.data,
    fontSize: 11,
    lineHeight: 14,
    color: chalk.dim,
    fontVariant: ['tabular-nums'],
  },
  skel: { height: 12, backgroundColor: ink.ink2, borderRadius: radii.xs },
  skelRank: { width: '50%', height: 22 },
  actions: {
    flexDirection: 'row',
    gap: space.sm,
    marginTop: 'auto',
    paddingTop: space.xs,
  },
  side: {
    flex: 1,
    minWidth: 0,
    minHeight: 36,
    paddingVertical: space.xs,
    paddingHorizontal: space.xs,
    borderWidth: 1,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sidePressed: { backgroundColor: ink.ink3 },
  sideLabel: { fontFamily: fonts.uiSemi, fontSize: 13, textAlign: 'center' },
});
