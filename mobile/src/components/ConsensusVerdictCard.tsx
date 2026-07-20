import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Card, Meter } from './chalkline';
import TradeValueBar from './TradeValueBar';
import type { CalcEvaluation } from '../api/calc';
import { semantic, space, type } from '../theme/chalkline';

// Server-authoritative verdict for the Trade Calculator's live mode: one
// consensus value per side (no per-owner boards), fairness gate + verdict
// straight from POST /api/trade/evaluate. Companion to VerdictPanel, which
// renders the demo mode's dual-board evaluation.
//
// The verdict is presented as a pick-denominated diverging value bar
// (TradeValueBar, feedback #157 + #169) — who wins and by how many picks. The
// raw give/get totals stay below as secondary reference.

export default function ConsensusVerdictCard({
  evaluation,
  stale,
}: {
  evaluation: CalcEvaluation;
  stale?: boolean;
}) {
  const both = evaluation.verdict !== null;
  const maxSide = Math.max(evaluation.give_value, evaluation.receive_value, 1);

  return (
    <Card>
      <View style={[styles.inner, stale && styles.stale]}>
        {both && evaluation.gap ? (
          <TradeValueBar
            giveValue={evaluation.give_value}
            receiveValue={evaluation.receive_value}
            favors={evaluation.favors}
            gap={evaluation.gap}
          />
        ) : (
          <Text style={[type.title, styles.verdict]}>Package value</Text>
        )}

        {/* Raw side totals — secondary reference beneath the value bar. */}
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
  note: { ...type.bodySm },
});
