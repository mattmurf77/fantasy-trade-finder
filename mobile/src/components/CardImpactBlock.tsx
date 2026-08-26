import React from 'react';
import { View, Text, StyleSheet, ActivityIndicator } from 'react-native';

import { ink, chalk, semantic, space, radii, type, fonts } from '../theme/chalkline';
import type { CalcEvaluationInLeague } from '../api/calc';

// #357 — "what does this trade do to my team?" ON THE DECK CARD.
//
// Operator, 2026-08-19: *"the feature that exists on the team level trade calc
// is mostly what should be presented on the find a trade card suggestions too
// (with the playoff odds shift added in)"*.
//
// TWO DELIBERATE DEPARTURES FROM THE CALCULATOR'S TREATMENT, both because a
// swipe card is not a worksheet:
//
//   1. **Changed slots only.** `InLeagueCalculator`'s LineupImpactTable prints
//      the WHOLE starting template (9-15 rows) with a header and dimmed
//      unchanged rows. On a card that would out-measure the players being
//      traded. Here only slots that actually move are listed, capped at
//      MAX_SLOT_ROWS, with an honest "+N more" tail.
//   2. **No raw value deltas.** The calculator shows the consensus point
//      swing; the card shows the tier/positional-rank movement, which is the
//      thing a swiping user can read in a second ("TE #31 -> TE #2"). The
//      "#" prefix is R-6 (#395): a bare "WR3" beside the slot labels reads as
//      a lineup slot; "WR #3" can only be a positional rank.
//
// PLACEMENT IS BINDING, NOT AESTHETIC. D-025 (operator, #169 frame decisions)
// fixed the card's vertical order: the Pass/Like disposition pair sits directly
// beneath the player tiles, `TradeValueBar` sits below the pair, and **any
// future card odds block mounts below the bar**. That clause was written while
// no card odds block existed; this is the block it was written for, so it
// mounts last. Do not reorder it above the value bar.
//
// ODDS RENDERING RULES (docs/cross-client-invariants.md):
//   * Lead with the BAND movement ("Toss-up -> Likely"), never a bare
//     percentage. The three-band vocabulary and its thresholds are a
//     cross-client encoding, read here from the server's own `before_band` /
//     `after_band` rather than re-derived.
//   * The signed delta may accompany it, rounded to WHOLE percentage points
//     and labelled a projection.
//   * `delta_pct === 0` is meaningful, not missing data: the before/after
//     simulations share one random stream, so an unchanged lineup is
//     bit-identical. Say "no change" rather than showing "+0".
//   * There is no championship/title figure here by construction — the server
//     does not serialize one.

const MAX_SLOT_ROWS = 3;

type Impact = NonNullable<CalcEvaluationInLeague['outlook_impact']>;
type Slot = NonNullable<NonNullable<CalcEvaluationInLeague['starter_impact']>['slots']>[number];

const BAND_LABEL: Record<Impact['before_band'], string> = {
  likely: 'Likely',
  tossup: 'Toss-up',
  unlikely: 'Unlikely',
};

const BAND_COLOR: Record<Impact['before_band'], string> = {
  likely: semantic.pos,
  tossup: semantic.warn,
  unlikely: semantic.neg,
};

/** Whole percentage points, signed. Deliberately coarse: the delta is stable
 *  to well under a point, but a decimal would imply a precision the strength
 *  model does not have. */
function signedPoints(delta: number): string {
  const pts = Math.round(delta * 100);
  return pts > 0 ? `+${pts}` : `${pts}`;
}

/** Trim the numbered suffix off a repeated slot ("RB2" -> "RB") only when the
 *  template repeats it; the server already numbers them. */
function slotLabel(slot: string): string {
  return slot.replace(/_/g, ' ');
}

export default function CardImpactBlock({
  loading,
  evaluation,
  failed = false,
  testID = 'trades.card-impact',
}: {
  loading: boolean;
  evaluation: CalcEvaluationInLeague | null;
  /** Distinguishes "the read failed" from "this trade moves no slots". Both
   *  render quietly, but only one of them is a bug worth finding. */
  failed?: boolean;
  testID?: string;
}) {
  if (loading) {
    return (
      <View style={styles.wrap} testID={`${testID}.loading`}>
        <ActivityIndicator size="small" color={chalk.faint} />
      </View>
    );
  }
  if (!evaluation) {
    // A failed read gets a single quiet line rather than nothing at all. It
    // must not look identical to a healthy no-op trade — that equivalence is
    // what hid a disabled fetch through an entire TestFlight build.
    return failed ? (
      <View style={styles.wrap} testID={`${testID}.unavailable`}>
        <Text style={styles.muted}>Team impact unavailable for this trade.</Text>
      </View>
    ) : null;
  }

  const impact = evaluation.outlook_impact;
  const slots: Slot[] = evaluation.starter_impact?.slots ?? [];
  const changed = slots.filter(
    (s) => (s.before?.player_id ?? null) !== (s.after?.player_id ?? null),
  );

  // Nothing to say — render nothing rather than an empty shell. A card with no
  // lineup movement and no odds block is a card where this section has no
  // content, not a card with a broken section.
  if (!impact && changed.length === 0) return null;

  const shown = changed.slice(0, MAX_SLOT_ROWS);
  const more = changed.length - shown.length;

  return (
    <View style={styles.wrap} testID={testID}>
      {changed.length > 0 ? (
        <View testID={`${testID}.lineup`}>
          <Text style={styles.kicker}>Your starting lineup</Text>
          {shown.map((s) => {
            // `rank` is the 1-based POSITIONAL rank (types.ts StarterSlotPlayer);
            // present only behind `trade.position_impact`, absent on old servers.
            const beforeRank = s.before?.rank;
            const afterRank = s.after?.rank;
            const haveRanks =
              typeof beforeRank === 'number' && typeof afterRank === 'number';
            // Lower positional rank is better, so an IMPROVEMENT is a decrease.
            const better = haveRanks ? afterRank! < beforeRank! : s.delta > 0;
            return (
              <View key={s.slot} style={styles.row}>
                <Text style={styles.slot} numberOfLines={1}>
                  {slotLabel(s.slot)}
                </Text>
                <Text style={styles.name} numberOfLines={1}>
                  {s.before?.name ?? '—'}
                </Text>
                <Text style={styles.arrow}>›</Text>
                <Text style={[styles.name, styles.nameAfter]} numberOfLines={1}>
                  {s.after?.name ?? '—'}
                </Text>
                {haveRanks ? (
                  <Text
                    style={[
                      styles.rank,
                      { color: better ? semantic.pos : semantic.neg },
                    ]}
                    numberOfLines={1}
                  >
                    {`${s.before?.position ?? ''} #${beforeRank} → ${s.after?.position ?? ''} #${afterRank}`}
                  </Text>
                ) : null}
              </View>
            );
          })}
          {more > 0 ? (
            <Text style={styles.more}>{`+${more} more slot${more === 1 ? '' : 's'} change`}</Text>
          ) : null}
        </View>
      ) : null}

      {impact ? (
        <View
          style={[styles.odds, changed.length > 0 && styles.oddsSpaced]}
          testID={`${testID}.odds`}
          accessible
          accessibilityLabel={
            impact.delta_pct === 0
              ? 'Projected playoff outlook: no change from this trade.'
              : `Projected playoff outlook moves from ${BAND_LABEL[impact.before_band]} to ${BAND_LABEL[impact.after_band]}.`
          }
        >
          <View style={styles.oddsHead}>
            <Text style={styles.kicker}>Playoff outlook</Text>
            <Text style={styles.ribbon} testID={`${testID}.odds.ribbon`}>
              {impact.beta ? 'PROJECTED · BETA' : 'PROJECTED'}
            </Text>
          </View>

          {impact.delta_pct === 0 ? (
            // Exact zero is a real answer, guaranteed by the shared random
            // stream — not a missing number. Never render it as "+0".
            <Text style={styles.noChange} testID={`${testID}.odds.no-change`}>
              No change to your playoff odds
            </Text>
          ) : (
            <View style={styles.bandRow}>
              <Text style={[styles.band, { color: BAND_COLOR[impact.before_band] }]}>
                {BAND_LABEL[impact.before_band]}
              </Text>
              <Text style={styles.arrow}>›</Text>
              <Text style={[styles.band, { color: BAND_COLOR[impact.after_band] }]}>
                {BAND_LABEL[impact.after_band]}
              </Text>
              <Text
                style={[
                  styles.points,
                  { color: impact.delta_pct > 0 ? semantic.pos : semantic.neg },
                ]}
                testID={`${testID}.odds.points`}
              >
                {`${signedPoints(impact.delta_pct)} pts`}
              </Text>
            </View>
          )}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    marginTop: space.md,
    paddingTop: space.md,
    borderTopWidth: 1,
    borderTopColor: ink.line,
  },
  kicker: {
    ...type.label,
    color: chalk.dim,
    letterSpacing: 1,
    textTransform: 'uppercase',
    marginBottom: space.xs,
  },
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: 3, gap: space.sm },
  slot: { ...type.bodySm, color: chalk.faint, width: 34 },
  name: { ...type.bodySm, color: chalk.base, flex: 1 },
  nameAfter: { fontFamily: fonts.uiSemi },
  arrow: { ...type.bodySm, color: chalk.faint },
  rank: { ...type.bodySm, fontVariant: ['tabular-nums'] },
  more: { ...type.bodySm, color: chalk.faint, marginTop: 2 },

  odds: {},
  oddsSpaced: { marginTop: space.md, paddingTop: space.md, borderTopWidth: 1, borderTopColor: ink.line },
  oddsHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  ribbon: {
    ...type.label,
    color: semantic.warn,
    borderWidth: 1,
    borderColor: semantic.warn,
    borderRadius: radii.xs,
    paddingHorizontal: 5,
    paddingVertical: 1,
    letterSpacing: 0.8,
  },
  bandRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  band: { fontFamily: fonts.displaySemi, fontSize: 17, textTransform: 'uppercase' },
  points: { ...type.bodySm, marginLeft: 'auto', fontVariant: ['tabular-nums'] },
  noChange: { ...type.bodySm, color: chalk.dim },
  muted: { ...type.bodySm, color: chalk.faint },
});
