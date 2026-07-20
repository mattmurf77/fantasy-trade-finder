import React from 'react';
import { StyleSheet, View } from 'react-native';
import type { DimensionValue } from 'react-native';
import { Text } from './chalkline';
import type { CalcGap } from '../api/calc';
import { chalk, ice, ink, radii, semantic, space, tier as tierColors, type } from '../theme/chalkline';

// TradeValueBar — the pick-denominated "trade verdict" (feedback #157 + the
// #169 value-bar). Reskins the fairness meter as a DIVERGING bar centered on
// "even": the fill leans toward whichever side wins, and the margin is spoken
// in draft-pick terms so the delta reads as an actionable counteroffer instead
// of an abstract number. Design source-of-truth: mockups/outlook-odds/value-bar.html.
//
// Presentation only — every input comes straight from POST /api/trade/evaluate
// (give_value, receive_value, favors, gap{firsts, pick_equivalent}); this
// component invents no math. Reusable by construction: the calculator verdict
// wires it here (ConsensusVerdictCard) and a later finder-card usage imports
// the same component. `favors` is authoritative for who-wins; `gap` supplies
// the magnitude.

// Scale: the bar spans ±1 generic Mid 1st (the "base first"), so the fill
// position IS gap.firsts — where it lands is literally the pick reading. The
// inner ticks mark the ±2nd landmark, the ends are ±1st. The ±2nd tick sits at
// the mid-2nd / mid-1st value ratio (≈0.57, from backend GENERIC_PICK_SEEDS) —
// a static visual reference only; real magnitude always comes from gap.firsts.
// Gaps beyond one first clamp to the end and the copy falls back to firsts
// ("≈ 1.4 mid 1sts").
const SECOND_IN_FIRSTS = 0.57;
const SECOND_PCT = 50 - SECOND_IN_FIRSTS * 50; // ≈21.5% — the −2nd landmark

export interface TradeValueBarProps {
  /** Consensus value of the side you send (give_value). */
  giveValue: number;
  /** Consensus value of the side you receive (receive_value). */
  receiveValue: number;
  /**
   * From /api/trade/evaluate. 'receive' = you win (you get more back),
   * 'give' = they win (you send more), 'even' / null = balanced.
   */
  favors: 'give' | 'receive' | 'even' | null;
  /** Pick-denominated gap from evaluate; renders null without it (one-sided). */
  gap: CalcGap | null;
  /** Perspective wording. Defaults to first/third person for the calculator. */
  youLabel?: string;
  themLabel?: string;
}

function fmt(v: number): string {
  return Math.round(v).toLocaleString('en-US');
}

const pct = (n: number): DimensionValue => `${n}%`;

// "Mid 2nd Round Pick" → "a Mid 2nd" (article by first-letter vowel sound).
function shortPick(label: string): string {
  const core = label.replace(/\s*Round Pick$/i, '').trim();
  const article = /^[AEIOU]/i.test(core) ? 'an' : 'a';
  return `${article} ${core}`;
}

export default function TradeValueBar({
  giveValue: _giveValue,
  receiveValue: _receiveValue,
  favors,
  gap,
  youLabel = 'You',
  themLabel = 'They',
}: TradeValueBarProps) {
  if (!gap) return null;

  const even = favors === 'even' || favors == null;
  const youWin = favors === 'receive';
  const firsts = Math.abs(gap.firsts);
  const clamped = Math.min(1, firsts); // ±1 base-first half-scale
  const frac = even ? 0 : youWin ? clamped : -clamped; // + = toward "You win" (right)

  const winner = even ? null : youWin ? youLabel : themLabel;
  const fillColor = even ? ice.base : youWin ? semantic.pos : semantic.warn;
  const pick = gap.pick_equivalent;

  // Fill geometry: center = even. Positive fraction grows right from the center;
  // negative grows left toward it. Even shows a small centered nub.
  const fillStyle: { left: DimensionValue; width: DimensionValue; marginLeft?: number } = even
    ? { left: pct(50), width: 6, marginLeft: -3 }
    : frac > 0
      ? { left: pct(50), width: pct(frac * 50) }
      : { left: pct(50 + frac * 50), width: pct(-frac * 50) };

  const sign = youWin ? '+' : '−';
  const worthTail = pick
    ? ` (≈ ${firsts.toFixed(1)} firsts)`
    : '';
  const worth = pick ? shortPick(pick.label) : `≈ ${firsts.toFixed(1)} mid 1sts`;
  const counter = youWin
    ? 'Accept as-is, or offer a small give-back.'
    : `Ask them to add ≈ ${pick ? shortPick(pick.label) : 'a 1st'} to even it out.`;

  return (
    <View style={styles.wrap}>
      <Text scale="dense" style={styles.head}>
        Dynasty value swing
      </Text>

      {/* WHO WINS headline + margin, spoken in picks */}
      <Text variant="heading" style={[styles.winner, { color: even ? chalk.base : fillColor }]}>
        {even ? 'Even' : `${winner} win`}
      </Text>
      {even ? (
        <Text style={styles.margin}>
          Within a rounding error — <Text style={styles.marginData}>{fmt(gap.value)}</Text> apart
          {gap.firsts ? ` (≈ ${gap.firsts.toFixed(1)} firsts)` : ''}
        </Text>
      ) : (
        <Text style={styles.margin}>
          by <Text style={[styles.marginData, { color: fillColor }]}>{sign}{fmt(gap.value)}</Text>
          {'  ·  '}
          <Text style={styles.marginPick}>{worth}</Text>
          {worthTail}
        </Text>
      )}

      {/* The diverging bar */}
      <View style={styles.track}>
        <View style={styles.rail} />
        <View style={[styles.fill, fillStyle, { backgroundColor: fillColor }]} />
        {/* pick-landmark ticks */}
        <View style={[styles.tick, { left: pct(SECOND_PCT) }]} />
        <View style={[styles.tick, { left: pct(100 - SECOND_PCT) }]} />
        <View style={styles.center} />
      </View>

      {/* landmark labels: −1st · −2nd · Even · +2nd · +1st */}
      <View style={styles.scaleRow}>
        <Text scale="dense" style={styles.scaleEnd}>−1st</Text>
        <View style={styles.scaleMid}>
          <View style={[styles.scaleLbl, { left: pct(SECOND_PCT) }]}>
            <Text scale="dense" style={styles.scaleTickLbl}>−2nd</Text>
          </View>
          <View style={[styles.scaleLbl, styles.scaleLblCenter]}>
            <Text scale="dense" style={styles.scaleTickLbl}>Even</Text>
          </View>
          <View style={[styles.scaleLbl, { left: pct(100 - SECOND_PCT) }]}>
            <Text scale="dense" style={styles.scaleTickLbl}>+2nd</Text>
          </View>
        </View>
        <Text scale="dense" style={styles.scaleEnd}>+1st</Text>
      </View>

      {/* who-wins end labels */}
      <View style={styles.endRow}>
        <Text scale="dense" style={[styles.endLbl, !even && !youWin && { color: fillColor }]}>
          {themLabel} win
        </Text>
        <Text scale="dense" style={[styles.endLbl, !even && youWin && { color: fillColor }]}>
          {youLabel} win
        </Text>
      </View>

      {/* Counteroffer read — the delta as a next move */}
      {even ? (
        <View style={[styles.verdict, styles.verdictEven]}>
          <Text style={styles.verdictBody}>
            Straight swap of comparable value — no sweetener needed.
          </Text>
        </View>
      ) : (
        <View style={[styles.verdict, { borderLeftColor: fillColor }]}>
          <Text style={styles.verdictBody}>
            <Text style={styles.verdictStrong}>{winner} win</Text> the equivalent of{' '}
            <Text style={styles.marginPick}>{worth}</Text> in dynasty value. {counter}
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: space.sm },
  head: { ...type.label, color: chalk.dim },
  winner: { marginTop: space.xs },
  margin: { ...type.bodySm, color: chalk.dim },
  marginData: { ...type.data, color: chalk.base },
  marginPick: { ...type.bodySm, color: tierColors.first_1, fontFamily: type.title.fontFamily },

  track: {
    position: 'relative',
    height: 16,
    marginTop: space.sm,
    justifyContent: 'center',
  },
  rail: {
    position: 'absolute',
    left: 0,
    right: 0,
    height: 14,
    backgroundColor: ink.ink3,
    borderRadius: radii.xs,
  },
  fill: {
    position: 'absolute',
    height: 14,
    borderRadius: radii.xs,
  },
  tick: {
    position: 'absolute',
    top: -4,
    height: 24,
    width: 1,
    backgroundColor: ink.line,
  },
  center: {
    position: 'absolute',
    left: '50%',
    marginLeft: -1,
    top: -4,
    height: 24,
    width: 1,
    backgroundColor: ink.lineStrongA11y,
  },

  scaleRow: { flexDirection: 'row', alignItems: 'center', marginTop: space.sm },
  scaleEnd: { ...type.data, fontSize: 9, color: chalk.faint, width: 30 },
  scaleMid: { flex: 1, height: 12 },
  scaleLbl: { position: 'absolute', width: 44, marginLeft: -22, alignItems: 'center' },
  scaleLblCenter: { left: '50%' },
  scaleTickLbl: { ...type.data, fontSize: 9, color: chalk.faint },

  endRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: space.xs,
  },
  endLbl: { ...type.label, color: chalk.dim },

  verdict: {
    marginTop: space.sm,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderLeftWidth: 3,
    borderRadius: radii.md,
    padding: space.md,
  },
  verdictEven: { borderLeftColor: ice.base },
  verdictBody: { ...type.bodySm, color: chalk.dim },
  verdictStrong: { ...type.bodySm, color: chalk.base, fontFamily: type.title.fontFamily },
});
