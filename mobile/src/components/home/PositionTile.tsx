import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { Badge, Meter, Text } from '../chalkline';
import { chalk, fonts, ice, ink, radii, space, type } from '../../theme/chalkline';
import { posColor } from '../../theme/colors';
import { useFlag } from '../../state/useFeatureFlags';
import {
  ordinal,
  rankPercentile,
  type PositionSplit,
  type SplitPos,
} from '../../utils/positionSplit';

// One Home hub position tile (scope.md D2/D3): your rank at P, your value
// against the league median, a 4px meter in the position hex and the neutral
// Seller / Buyer badge (or "Mid-pack"). Every number comes from the
// utils/positionSplit result the hub hands in — this file does no band,
// median or ordering arithmetic of its own.
//
// The tile itself is NOT pressable: its only controls are Buy and Sell
// (36pt visible, 44pt hit, inside the tile), so VoiceOver never meets a
// nested control. The side the user's band implies is drawn in ice on at
// most two tiles (the hub's `emphasis`, for the ≤3 ice ration); it changes
// no behaviour. With no line at this position (no_split /
// no_median) Buy and Sell would promise directions the destination can't
// give, so they collapse into one "See P ranking" button.
//
// split === null is the loading state: static skeletons, Buy/Sell disabled,
// so a tap can never land on a list Home hasn't described.

// Static literal testIDs per position (testid-lint can't see template ids).
const IDS: Record<SplitPos, { tile: string; buy: string; sell: string; ranking: string }> = {
  QB: {
    tile: 'home.position.qb',
    buy: 'home.position.qb.buy',
    sell: 'home.position.qb.sell',
    ranking: 'home.position.qb.ranking',
  },
  RB: {
    tile: 'home.position.rb',
    buy: 'home.position.rb.buy',
    sell: 'home.position.rb.sell',
    ranking: 'home.position.rb.ranking',
  },
  WR: {
    tile: 'home.position.wr',
    buy: 'home.position.wr.buy',
    sell: 'home.position.wr.sell',
    ranking: 'home.position.wr.ranking',
  },
  TE: {
    tile: 'home.position.te',
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
  /** The ice side for this tile, if the hub picked it (utils/positionSplit
   *  emphasizedSides caps the screen at two, for the ≤3 ice ration). */
  emphasis?: 'buy' | 'sell' | null;
}

export default function PositionTile({ pos, split, onBuy, onSell, onRanking, emphasis = null }: Props) {
  const ids = IDS[pos];
  const color = posColor(pos);
  const lined = split?.state === 'shown';
  const you = split?.you ?? null;
  const suggested = emphasis;
  return (
    <View style={styles.tile} testID={ids.tile}>
      <View style={[styles.rail, { backgroundColor: color }]} />
      <View style={styles.head}>
        <Text scale="dense" style={[type.label, { color }]}>
          {pos}
        </Text>
        {split == null ? null : !lined ? (
          <Text scale="dense" style={styles.mid}>No clear split</Text>
        ) : you?.band ? (
          <Badge label={you.band} />
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
  // 3px position rail across the top edge (data encoding, paired with the label).
  rail: { position: 'absolute', top: 0, left: 0, right: 0, height: 3 },
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
