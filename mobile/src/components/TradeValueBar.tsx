import React, { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import type { DimensionValue } from 'react-native';
import { Icon, Text } from './chalkline';
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
//
// #243 density pass (V1, mockups/polish-lab-2026-08/tradevaluebar-density.html
// frame B1): winner line steps heading→title (mid-card element, not a page
// title), the verdict paragraph collapses by default behind a one-line "Why?"
// disclosure (AdjustmentsDisclosure grammar; per-instance state, so every
// mount — deck cards, featured window, calculator verdicts — starts
// collapsed), verdict-box vertical padding md→sm, and the 9px scale labels
// move to the 11px Chalkline floor. ~56pt saved per instance collapsed.

// Scale: the bar spans ±1 generic Mid 1st (the "base first"), so the fill
// position IS gap.firsts — where it lands is literally the pick reading. The
// inner ticks mark the ±2nd landmark, the ends are ±1st. The ±2nd tick sits at
// the Mid 2nd / Mid 1st value ratio over backend GENERIC_PICK_SEEDS (the same
// source the share card's bar uses, #564), pinned to it by
// backend/tests/test_value_bar_scale.py so the two can't drift again: at 0.57
// a fill reading "≈ a Late 1st" (0.6 firsts) ended on the "2nd" tick. A
// static visual reference only; real magnitude always comes from gap.firsts.
// Gaps beyond one first clamp to the end and the copy falls back to firsts
// ("≈ 1.4 mid 1sts").
const SECOND_IN_FIRSTS = 0.287;
const SECOND_PCT = 50 - SECOND_IN_FIRSTS * 50; // ≈35.7% — the −2nd landmark

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

/**
 * The bar's Even state, the one predicate every reader shares (the bar, the
 * deck card's VoiceOver summary): `favors` 'even' or absent, or the B2 rule
 * (Product P112, 11-02; the share image does the same, #564): a null
 * pick_equivalent under one first is the server's negligible floor (under half
 * the smallest generic pick, 0.058 firsts today), so it reads Even, never
 * "≈ 0.0 mid 1sts". Its body is plain JS: check-value-bar-b2.js executes it.
 */
export function valueBarIsEven(
  favors: TradeValueBarProps['favors'] | undefined,
  gap: CalcGap | null | undefined,
): boolean {
  const pick = gap ? gap.pick_equivalent : null;
  const firsts = gap ? Math.abs(gap.firsts) : 0;
  return favors === 'even' || favors == null || (!pick && firsts < 1);
}

export default function TradeValueBar({
  giveValue: _giveValue,
  receiveValue: _receiveValue,
  favors,
  gap,
  youLabel = 'You',
  themLabel = 'They',
}: TradeValueBarProps) {
  const [whyOpen, setWhyOpen] = useState(false);
  if (!gap) return null;

  const firsts = Math.abs(gap.firsts);
  const pick = gap.pick_equivalent;
  // Every Even/lean reading below (headline, margin, fill, ends, Why?) comes
  // from `even`, never raw `favors`; the B2 rule is inside the predicate.
  const even = valueBarIsEven(favors, gap);
  const youWin = favors === 'receive';
  const clamped = Math.min(1, firsts); // ±1 base-first half-scale
  const frac = even ? 0 : youWin ? clamped : -clamped; // + = toward "You win" (right)

  const winner = even ? null : youWin ? youLabel : themLabel;
  const fillColor = even ? ice.base : youWin ? semantic.pos : semantic.warn;

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
      <Text variant="title" style={[styles.winner, { color: even ? chalk.base : fillColor }]}>
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

      {/* Counteroffer read — the delta as a next move. Collapsed by default
          behind a one-line "Why?" disclosure (#243 density V1). */}
      <Pressable
        testID="valuebar.why"
        onPress={() => setWhyOpen((o) => !o)}
        accessibilityRole="button"
        accessibilityLabel={whyOpen ? 'Hide verdict explanation' : 'Show verdict explanation'}
        style={styles.whyToggle}
        hitSlop={6}
      >
        <Text scale="dense" style={styles.whyText}>Why?</Text>
        <Icon name={whyOpen ? 'chevron-up' : 'chevron-down'} size={14} color={chalk.dim} />
      </Pressable>
      {!whyOpen ? null : even ? (
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
  scaleEnd: { ...type.data, fontSize: 11, color: chalk.faint, width: 30 },
  scaleMid: { flex: 1, height: 12 },
  scaleLbl: { position: 'absolute', width: 44, marginLeft: -22, alignItems: 'center' },
  scaleLblCenter: { left: '50%' },
  scaleTickLbl: { ...type.data, fontSize: 11, color: chalk.faint },

  endRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: space.xs,
  },
  endLbl: { ...type.label, color: chalk.dim },

  whyToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 32,
  },
  whyText: { ...type.label, color: chalk.dim },

  verdict: {
    marginTop: space.sm,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderLeftWidth: 3,
    borderRadius: radii.md,
    paddingVertical: space.sm,
    paddingHorizontal: space.md,
  },
  verdictEven: { borderLeftColor: ice.base },
  verdictBody: { ...type.bodySm, color: chalk.dim },
  verdictStrong: { ...type.bodySm, color: chalk.base, fontFamily: type.title.fontFamily },
});
