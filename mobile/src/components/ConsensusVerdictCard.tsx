import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Card, Meter } from './chalkline';
import type { CalcEvaluation } from '../api/calc';
import { chalk, ice, semantic, space, type } from '../theme/chalkline';

// Server-authoritative verdict for the Trade Calculator's live mode: one
// consensus value per side (no per-owner boards), fairness gate + verdict
// straight from POST /api/trade/evaluate. Companion to VerdictPanel, which
// renders the demo mode's dual-board evaluation.

const VERDICT_COPY: Record<string, { label: string; color: string }> = {
  even:   { label: 'Dead even',  color: ice.base },
  fair:   { label: 'Fair trade', color: semantic.pos },
  unfair: { label: 'Uneven',     color: semantic.neg },
};

export default function ConsensusVerdictCard({
  evaluation,
  stale,
}: {
  evaluation: CalcEvaluation;
  stale?: boolean;
}) {
  const both = evaluation.verdict !== null;
  const v = evaluation.verdict ? VERDICT_COPY[evaluation.verdict] : null;
  const maxSide = Math.max(evaluation.give_value, evaluation.receive_value, 1);
  const favorsNote =
    evaluation.verdict === 'unfair'
      ? evaluation.favors === 'give'
        ? ' — you send more than you get back'
        : ' — you get more than you send'
      : '';

  return (
    <Card>
      <View style={[styles.inner, stale && styles.stale]}>
        {v ? (
          <Text style={[type.title, styles.verdict, { color: v.color }]}>
            {v.label}
            {favorsNote}
          </Text>
        ) : (
          <Text style={[type.title, styles.verdict]}>Package value</Text>
        )}

        <View style={styles.row}>
          <Text style={[type.label, styles.rowLabel]}>You send</Text>
          <View style={styles.meter}>
            <Meter value={evaluation.give_value / maxSide} color={semantic.neg} />
          </View>
          <Text style={[type.data, styles.rowValue]}>
            {Math.round(evaluation.give_value).toLocaleString()}
          </Text>
        </View>
        <View style={styles.row}>
          <Text style={[type.label, styles.rowLabel]}>You get</Text>
          <View style={styles.meter}>
            <Meter value={evaluation.receive_value / maxSide} color={semantic.pos} />
          </View>
          <Text style={[type.data, styles.rowValue]}>
            {Math.round(evaluation.receive_value).toLocaleString()}
          </Text>
        </View>

        {both && evaluation.point_ratio !== null ? (
          <Text style={styles.ratio}>
            Value ratio {Math.round(evaluation.point_ratio * 100)}%
          </Text>
        ) : null}

        {/* Pick-denominated gap: turn the delta into an actionable
            counteroffer ("ask for ≈ a Mid 2nd back"). Hidden on dead-even
            verdicts — naming a 4th under "Dead even" is noise. */}
        {evaluation.verdict && evaluation.verdict !== 'even' &&
         evaluation.gap && evaluation.gap.add_to ? (
          <Text style={styles.gapNote}>
            {evaluation.gap.pick_equivalent
              ? evaluation.gap.add_to === 'give'
                ? `You get more — evens out if you add ≈ a ${evaluation.gap.pick_equivalent.label}.`
                : `You send more — ask for ≈ a ${evaluation.gap.pick_equivalent.label} back.`
              : `Gap ≈ ${evaluation.gap.firsts.toFixed(1)} mid 1sts — more than any single pick closes.`}
          </Text>
        ) : null}
        {evaluation.dropped_player_ids.length > 0 ? (
          <Text style={styles.note}>
            {evaluation.dropped_player_ids.length} asset(s) had no consensus value and were
            excluded.
          </Text>
        ) : null}
        <Text style={styles.note}>
          Consensus values — the same engine numbers the trade finder uses.
        </Text>
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  inner: { gap: space.md },
  stale: { opacity: 0.55 },
  verdict: { textAlign: 'center' },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  rowLabel: { width: 64 },
  meter: { flex: 1 },
  rowValue: { minWidth: 56, textAlign: 'right' },
  ratio: { ...type.data, textAlign: 'center', color: chalk.dim },
  gapNote: { ...type.data, textAlign: 'center', color: chalk.base },
  note: { ...type.bodySm },
});
