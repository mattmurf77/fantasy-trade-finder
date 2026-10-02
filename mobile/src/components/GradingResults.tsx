import React from 'react';
import { StyleSheet, View } from 'react-native';
import { chalk, ink, space } from '../theme/chalkline';
import { Card, Text, TickLabel } from './chalkline';
import {
  GRADING_TAG_LABELS,
  type GradingArmSummary,
  type GradingResults as Results,
  type GradingTag,
} from '../api/grading';

// Calibration — the results reveal (docs/plans/blind-grading/lld.md §10.5).
//
// THE ONLY component that names an arm. Everything before this point in the
// session is blind: the card never says which engine produced it and the
// screen never holds an arm token (mobile/tests/check-blind-grading.js walks
// src/ and fails if `value_core` or these two labels appear anywhere else).
// This component renders only in the results phase, after the last answer.

const ARM_ORDER = ['current', 'value_core'] as const;
const ARM_LABEL = { current: "Today's engine", value_core: 'New engine' } as const;

const fmtMean = (m: number | null) => (m == null ? '—' : m.toFixed(2));
const fmtShare = (s: number | null) => (s == null ? '—' : `${Math.round(s * 100)}%`);

// The three most-used tags, written "Overpay ×4". Ties break by label so the
// order is stable across renders.
function topTags(counts: GradingArmSummary['tag_counts']): string[] {
  return (Object.entries(counts) as [GradingTag, number | undefined][])
    .filter((e): e is [GradingTag, number] => typeof e[1] === 'number' && e[1] > 0)
    .sort((a, b) => b[1] - a[1] || GRADING_TAG_LABELS[a[0]].localeCompare(GRADING_TAG_LABELS[b[0]]))
    .slice(0, 3)
    .map(([tag, n]) => `${GRADING_TAG_LABELS[tag]} ×${n}`);
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text variant="bodySm" style={styles.rowLabel}>{label}</Text>
      <Text variant="data">{value}</Text>
    </View>
  );
}

function ArmCard({ label, arm }: { label: string; arm: GradingArmSummary }) {
  const reasons = topTags(arm.tag_counts);
  return (
    <Card>
      <View style={styles.cardBody}>
        <TickLabel>{label}</TickLabel>
        <Row label="Cards" value={String(arm.cards)} />
        <Row label="Graded" value={String(arm.n)} />
        <Row label="Skipped" value={String(arm.skipped)} />
        <Row label="Average" value={fmtMean(arm.mean)} />
        <Row label="Would send (4–5)" value={fmtShare(arm.share_ge_4)} />
        <View style={styles.reasons}>
          <Text variant="label">Top reasons</Text>
          <Text variant="bodySm" style={styles.reasonsText}>
            {reasons.length ? reasons.join(' · ') : '—'}
          </Text>
        </View>
      </View>
    </Card>
  );
}

export default function GradingResults({ results }: { results: Results }) {
  return (
    <View style={styles.root}>
      {ARM_ORDER.map((arm) => (
        <ArmCard key={arm} label={ARM_LABEL[arm]} arm={results.arms[arm]} />
      ))}
      <Text variant="bodySm" style={styles.footer}>
        {`${results.shared} trades were suggested by both engines and count for both.`}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { gap: space.md },
  cardBody: { gap: space.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    paddingVertical: space.xs,
  },
  rowLabel: { color: chalk.dim },
  reasons: { gap: space.xs, paddingTop: space.xs },
  reasonsText: { color: chalk.base },
  footer: { color: chalk.dim },
});
