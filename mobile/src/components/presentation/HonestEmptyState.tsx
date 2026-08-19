import React from 'react';
import { View, StyleSheet } from 'react-native';
import { ink, chalk, flare, space, radii, type } from '../../theme/chalkline';
import { Text, TickLabel, Badge, Button, Card, Icon } from '../chalkline';
import type { EmptyStateCopy } from '../../utils/tradePresentation';

// HonestEmptyState — the price-feedback pivot when nothing qualifies. Flag
// `trades.presentation_v2`; approved lab
// mockups/trade-suggestion-redesign/07-honest-empty.html.
//
// THE POINT IS THE REFUSAL. When no package clears the bar for both sides we
// show nothing rather than degrading the endorsement, because filler
// suggestions get audited by leaguemates all season and confidently-wrong is
// the most trust-destructive error class in a repeated game. The empty state
// converts no-supply into a price conversation instead.
//
// ── WHAT THIS SHIPS vs WHAT THE LAB DREW ─────────────────────────────────
// The lab names a specific blocking player and shows the user's board value
// beside league consensus for him ("Your ask on Jahmyr Gibbs is above league
// consensus … RB2 · 8,900 vs RB5 · 7,400"). NEITHER datum exists on any
// shipped response — there is no blocking-ask diagnosis and no per-player
// board-vs-consensus pair on the generate/status payloads (scope.md §2).
// Fabricating one here would be exactly the confidently-wrong failure the
// state exists to prevent, so instead we surface the levers that genuinely
// changed the outcome, each read from a real value we hold: the fairness
// threshold the job actually ran at, the user's real board coverage, and the
// decline-suppression count the snapshot already reports.
//
// "Keep my price" is a FIRST-CLASS choice, not a dismissal — the app is a
// mediator, not a nag (round-2 T2).

interface Props {
  copy: EmptyStateCopy;
  onReviewBoard: () => void;
  onWidenFairness?: () => void;
  onKeepPrice: () => void;
}

export default function HonestEmptyState({
  copy,
  onReviewBoard,
  onWidenFairness,
  onKeepPrice,
}: Props) {
  return (
    <View style={styles.wrap} testID="presentation.empty">
      <View style={styles.empty}>
        <Icon name="swap" size={28} color={chalk.faint} />
        <Text variant="heading" style={styles.heading} testID="presentation.empty-heading">
          {copy.heading}
        </Text>
        <Text variant="bodySm" style={styles.center}>
          {copy.body}
        </Text>
        {copy.suppressionNote ? (
          <Text scale="dense" style={[styles.center, styles.faint]}>
            {copy.suppressionNote}
          </Text>
        ) : null}
      </View>

      <Card padding={space.md}>
        <View style={styles.whyRow}>
          <Badge label="Why" color={flare.base} colorText />
          <TickLabel>What would change this</TickLabel>
        </View>
        <Text variant="bodySm" style={styles.gap}>
          Nothing here is broken — the two levers that actually widen the pool are
          your price and your board.
        </Text>

        <Button
          label="Review my board"
          variant="secondary"
          onPress={onReviewBoard}
          testID="presentation.empty-review-board"
          style={styles.btn}
        />
        {copy.canWidenFairness && onWidenFairness ? (
          <Button
            label="Widen the fairness net"
            variant="secondary"
            onPress={onWidenFairness}
            testID="presentation.empty-widen"
            style={styles.btn}
          />
        ) : null}
        <Button
          label="Keep my price"
          variant="ghost"
          onPress={onKeepPrice}
          testID="presentation.empty-keep-price"
          style={styles.btn}
        />
      </Card>

      <View style={styles.waitNote}>
        <Icon name="bell" size={14} color={chalk.faint} />
        <Text scale="dense" style={styles.faint}>
          Keeping your price is fine — we'll check again next cycle.
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: space.md },
  empty: {
    alignItems: 'center',
    gap: space.sm,
    paddingVertical: space.xl,
    paddingHorizontal: space.md,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
  },
  heading: { textAlign: 'center' },
  center: { textAlign: 'center' },
  faint: { ...type.bodySm, fontSize: 12, lineHeight: 16, color: chalk.faint },
  whyRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  gap: { marginTop: space.xs, marginBottom: space.sm },
  btn: { width: '100%', marginTop: space.sm },
  waitNote: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.xs,
    flexWrap: 'wrap',
  },
});
