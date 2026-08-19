import React from 'react';
import { View, StyleSheet, Pressable } from 'react-native';
import { ink, chalk, ice, space, radii, type } from '../../theme/chalkline';
import { Text, Icon } from '../chalkline';
import { ConfidenceChip } from './ConfidenceChip';
import { confidenceBand, packageSummary } from '../../utils/tradePresentation';
import type { TradeCard } from '../../shared/types';

// TradeIdeaRow — one row of the UNCAPPED "All trades" list, plus its
// dismissed-state acknowledgement. Flag `trades.presentation_v2`; approved lab
// mockups/trade-suggestion-redesign/09-browse-all.html.
//
// WHY DISMISS IS ON EVERY ROW. Scarcity powers the ENDORSEMENT, not
// discovery. This list is deliberately uncapped because every view and every
// dismiss-after-view is ranking-training signal — mining declines is what took
// IBM/ESPN's trade recommender from 76.9% to 97.3%. A row hidden from the user
// is a signal we never collect.
//
// WHY THE ACKNOWLEDGEMENT LINE EXISTS. Undetected miscalibration silently
// destroys reliance (Li 2024 / FAccT 2025). Saying "we'll rank ideas like this
// lower" makes the model's learning visible, and the Undo makes the dismiss
// safe enough to use freely — which is what keeps the signal flowing.
//
// A dismissed row is NOT removed. It stays in place, dimmed, carrying its
// acknowledgement; removing it would delete the very feedback this design is
// for and would make the list jump under the reader's thumb.

interface Props {
  card: TradeCard;
  rank: number;
  dismissed: boolean;
  /** Marks the pinned hero at the top of the list. */
  hero?: boolean;
  onOpen: (card: TradeCard) => void;
  onDismiss: (card: TradeCard) => void;
  onUndo: (card: TradeCard) => void;
}

export default function TradeIdeaRow({
  card,
  rank,
  dismissed,
  hero = false,
  onOpen,
  onDismiss,
  onUndo,
}: Props) {
  const who = card.opponent_username?.trim() || 'A league-mate';
  const summary = packageSummary(card);
  return (
    // testIDs key on RANK, not trade_id: in a ranked list the row's identity
    // IS its position, and a server-minted trade_id is addressable from
    // neither a flow nor a bug report.
    <View testID={`presentation.row.${rank}`}>
      <View style={[styles.row, hero && styles.rowHero, dismissed && styles.rowDismissed]}>
        <Text scale="dense" style={[styles.rank, hero && styles.rankHero]}>
          {rank}
        </Text>
        <Pressable
          style={styles.body}
          testID={`presentation.row-open.${rank}`}
          accessibilityRole="button"
          accessibilityLabel={`Rank ${rank}. ${who}. ${summary}. Open this idea.`}
          onPress={() => onOpen(card)}
        >
          <Text scale="body" style={[styles.who, dismissed && styles.dim]}>
            {who}
          </Text>
          {/* Wraps rather than truncates — text scaling must never clip the
              only description of the package. */}
          <Text variant="bodySm" style={dismissed ? styles.dim : undefined}>
            {summary}
          </Text>
        </Pressable>
        <ConfidenceChip band={confidenceBand(card)} />
        <Pressable
          testID={
            dismissed ? `presentation.row-undo.${rank}` : `presentation.row-dismiss.${rank}`
          }
          accessibilityRole="button"
          accessibilityLabel={dismissed ? `Undo dismissing ${who}'s idea` : `Dismiss ${who}'s idea`}
          // 28pt control padded out to a 44pt effective target.
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          onPress={() => (dismissed ? onUndo(card) : onDismiss(card))}
          style={({ pressed }) => [styles.dismiss, pressed && styles.dismissPressed]}
        >
          <Icon name={dismissed ? 'check' : 'x'} size={12} color={chalk.dim} />
        </Pressable>
      </View>

      {dismissed ? (
        <View style={styles.undoLine} testID={`presentation.row-ack.${rank}`}>
          <Text scale="dense" style={styles.undoText}>
            Dismissed — we'll rank ideas like this lower.
          </Text>
          <Pressable
            testID={`presentation.row-undo-link.${rank}`}
            accessibilityRole="button"
            accessibilityLabel={`Undo dismissing ${who}'s idea`}
            hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
            onPress={() => onUndo(card)}
          >
            <Text scale="dense" style={styles.undoLink}>
              Undo
            </Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingLeft: space.md,
    paddingRight: space.sm,
    paddingVertical: space.sm,
    minHeight: 44,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  rowHero: { backgroundColor: ink.ink2 },
  rowDismissed: { backgroundColor: ink.ink0, borderBottomWidth: 0 },
  rank: {
    ...type.data,
    fontSize: 12,
    lineHeight: 16,
    color: chalk.faint,
    width: 20,
    textAlign: 'right',
  },
  rankHero: { color: ice.base },
  body: { flex: 1, minWidth: 0, paddingVertical: 2 },
  who: { ...type.body, fontSize: 13, lineHeight: 17, color: chalk.base },
  dim: { color: chalk.faint },
  dismiss: {
    width: 28,
    height: 28,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.lineStrongA11y,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dismissPressed: { backgroundColor: ink.ink3 },
  undoLine: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingLeft: 44,
    paddingRight: space.md,
    paddingBottom: space.sm,
    backgroundColor: ink.ink0,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    flexWrap: 'wrap',
  },
  undoText: { ...type.bodySm, fontSize: 12, lineHeight: 16, color: chalk.faint },
  undoLink: { ...type.bodySm, fontSize: 12, lineHeight: 16, color: ice.base },
});
