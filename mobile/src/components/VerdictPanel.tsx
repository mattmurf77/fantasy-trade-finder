import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Card, Meter } from './chalkline';
import {
  CalcTradeEval,
  CalcVerdict,
  CALC_VERDICT_LABEL,
  formatDelta,
} from '../utils/tradeCalcMath';
import { chalk, semantic, type, space } from '../theme/chalkline';

const VERDICT_COLOR: Record<CalcVerdict, string> = {
  WIN_WIN: semantic.pos,
  FAIR: chalk.base,
  THEY_DECLINE: semantic.warn,
  YOU_LOSE: semantic.neg,
  UNEVEN: chalk.dim,
};

// Dual-perspective fairness readout for the Trade Calculator: verdict line +
// a gives/gets pair of Meter bars per board. Deliberately NOT StrengthBar —
// that's a single-value 0–100 gradient meter, while these bars show the
// give-vs-get proportion of one trade on one owner's board.
function PerspectiveRow({
  label,
  give,
  get,
  deltaPct,
}: {
  label: string;
  give: number;
  get: number;
  deltaPct: number;
}) {
  const total = Math.max(give + get, 1);
  const gain = deltaPct >= 0;
  return (
    <View style={styles.perspective}>
      <View style={styles.perspectiveHeader}>
        <Text style={type.label}>{label}</Text>
        <Text style={[type.data, { color: gain ? semantic.pos : semantic.neg }]}>
          {formatDelta(deltaPct)}
        </Text>
      </View>
      <View style={styles.meterRow}>
        <Text style={[type.label, styles.meterLabel]}>gives</Text>
        <View style={styles.meterTrack}>
          <Meter value={give / total} color={semantic.neg} />
        </View>
        <Text style={[type.data, styles.meterValue]}>{give.toLocaleString()}</Text>
      </View>
      <View style={styles.meterRow}>
        <Text style={[type.label, styles.meterLabel]}>gets</Text>
        <View style={styles.meterTrack}>
          <Meter value={get / total} color={semantic.pos} />
        </View>
        <Text style={[type.data, styles.meterValue]}>{get.toLocaleString()}</Text>
      </View>
    </View>
  );
}

export default function VerdictPanel({ evaluation }: { evaluation: CalcTradeEval }) {
  const color = VERDICT_COLOR[evaluation.verdict];
  return (
    <Card>
      <View style={styles.inner}>
        <Text style={[type.title, styles.verdict, { color }]}>
          {CALC_VERDICT_LABEL[evaluation.verdict]}
        </Text>
        <PerspectiveRow
          label="Your board"
          give={evaluation.myGive}
          get={evaluation.myGet}
          deltaPct={evaluation.myDeltaPct}
        />
        <PerspectiveRow
          label="Their board"
          give={evaluation.theirGive}
          get={evaluation.theirGet}
          deltaPct={evaluation.theirDeltaPct}
        />
        <Text style={styles.hint}>
          A trade only gets accepted when both boards like it — that's the mutual-gain rule the
          finder uses too.
        </Text>
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  inner: { gap: space.md },
  verdict: { textAlign: 'center' },
  perspective: { gap: space.xs },
  perspectiveHeader: { flexDirection: 'row', justifyContent: 'space-between' },
  meterRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  meterLabel: { width: 40 },
  meterTrack: { flex: 1 },
  meterValue: { minWidth: 56, textAlign: 'right' },
  hint: { ...type.bodySm },
});
