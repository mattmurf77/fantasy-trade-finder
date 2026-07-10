import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { TradeEval, Verdict, VERDICT_LABEL, formatDelta } from '../logic/tradeMath';
import { colors, fontSize, radius, spacing } from '../theme';

const VERDICT_COLOR: Record<Verdict, string> = {
  WIN_WIN: colors.green,
  FAIR: colors.accent,
  THEY_DECLINE: colors.gold,
  YOU_LOSE: colors.red,
  UNEVEN: colors.muted,
};

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
        <Text style={styles.perspectiveLabel}>{label}</Text>
        <Text style={[styles.delta, { color: gain ? colors.green : colors.red }]}>
          {gain ? '▲' : '▼'} {formatDelta(deltaPct)}
        </Text>
      </View>
      <View style={styles.bar}>
        <View style={[styles.barGive, { flex: give / total }]} />
        <View style={[styles.barGet, { flex: get / total }]} />
      </View>
      <View style={styles.barLabels}>
        <Text style={styles.barLabel}>gives {give.toLocaleString()}</Text>
        <Text style={styles.barLabel}>gets {get.toLocaleString()}</Text>
      </View>
    </View>
  );
}

export function VerdictPanel({ evaluation }: { evaluation: TradeEval }) {
  const color = VERDICT_COLOR[evaluation.verdict];
  return (
    <View style={[styles.card, { borderColor: color + '66' }]}>
      <View style={[styles.chip, { backgroundColor: color + '26' }]}>
        <Text style={[styles.chipText, { color }]}>{VERDICT_LABEL[evaluation.verdict]}</Text>
      </View>
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
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    padding: spacing.lg,
    gap: spacing.md,
  },
  chip: {
    alignSelf: 'center',
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  chipText: { fontSize: fontSize.sm, fontWeight: '700' },
  perspective: { gap: spacing.xs },
  perspectiveHeader: { flexDirection: 'row', justifyContent: 'space-between' },
  perspectiveLabel: { color: colors.text, fontSize: fontSize.sm, fontWeight: '600' },
  delta: { fontSize: fontSize.sm, fontWeight: '700' },
  bar: {
    flexDirection: 'row',
    height: 8,
    borderRadius: radius.pill,
    overflow: 'hidden',
    backgroundColor: colors.surfaceRaised,
  },
  barGive: { backgroundColor: colors.red + 'aa' },
  barGet: { backgroundColor: colors.green + 'aa' },
  barLabels: { flexDirection: 'row', justifyContent: 'space-between' },
  barLabel: { color: colors.muted, fontSize: fontSize.xs },
  hint: { color: colors.muted, fontSize: fontSize.xs, lineHeight: 16 },
});
