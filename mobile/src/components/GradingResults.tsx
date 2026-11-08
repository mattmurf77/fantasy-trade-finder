import React, { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { chalk, ink, space } from '../theme/chalkline';
import { Card, Icon, Text, TickLabel } from './chalkline';
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
  return (
    <Card>
      <View style={styles.cardBody}>
        <TickLabel>{label}</TickLabel>
        {/* Yes/No since 2026-10-14: share_ge_4 is the Yes rate (an older 1–5
            session reads it as the share of 4s and 5s). The mean is no longer shown. */}
        <Row label="Would send" value={fmtShare(arm.share_ge_4)} />
        <Text variant="bodySm" style={styles.footer}>{`${arm.n} rated · ${arm.skipped} skipped`}</Text>
      </View>
    </Card>
  );
}

export default function GradingResults({ results }: { results: Results }) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  return (
    <View style={styles.root}>
      {ARM_ORDER.map((arm) => (
        <ArmCard key={arm} label={ARM_LABEL[arm]} arm={results.arms[arm]} />
      ))}
      {results.round_id && results.sample_size_status === 'limited' ? (
        <Text variant="bodySm" style={styles.footer}>Small sample. Compare with care.</Text>
      ) : null}
      <Pressable
        accessibilityRole="button"
        aria-expanded={detailsOpen}
        onPress={() => setDetailsOpen(open => !open)}
        style={styles.detailsToggle}
      >
        <Text variant="bodySm" style={styles.detailsLabel}>Rating details</Text>
        <Icon name={detailsOpen ? 'chevron-up' : 'chevron-down'} size={16} color={chalk.base} />
      </Pressable>
      {detailsOpen && <View style={styles.details}>
        {ARM_ORDER.map(key => {
          const arm = results.arms[key];
          const reasons = topTags(arm.tag_counts);
          return <View key={key} style={styles.details}>
            <TickLabel>{ARM_LABEL[key]}</TickLabel>
            <Text variant="bodySm" style={styles.footer}>{`${arm.cards} trades shown`}</Text>
            {reasons.length > 0 && <Text variant="bodySm" style={styles.footer}>
              {`Top reasons: ${reasons.join(' · ')}`}
            </Text>}
          </View>;
        })}
        {results.shared > 0 && <Text variant="bodySm" style={styles.footer}>
          {results.shared === 1 ? '1 trade counted for both engines.' : `${results.shared} trades counted for both engines.`}
        </Text>}
        <Text variant="bodySm" style={styles.footer}>Results reflect only the trades you rated.</Text>
      </View>}
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
  details: { gap: space.xs },
  detailsToggle: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: space.xs },
  detailsLabel: { color: chalk.base, flexShrink: 1 },
  footer: { color: chalk.dim },
});
