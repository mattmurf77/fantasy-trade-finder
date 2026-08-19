import React from 'react';
import { View, StyleSheet, Pressable } from 'react-native';
import { ink, chalk, ice, space, radii, type } from '../../theme/chalkline';
import { Text, TickLabel, Icon } from '../chalkline';
import { ConfidenceChip } from './ConfidenceChip';
import { confidenceBand, packageSummary } from '../../utils/tradePresentation';
import type { TradeCard } from '../../shared/types';

// FeaturedBench — the middle tier of the pyramid: hero -> Featured -> uncapped
// browse. Flag `trades.presentation_v2`; approved lab
// mockups/trade-suggestion-redesign/03-bench.html.
//
// SMALL ON PURPOSE. Choice overload at the TOP of the funnel produces a
// rejection mind-set (Pronk & Denissen 2020), so this tier is capped at
// FEATURED_CAP rows. That cap is about ENDORSEMENT, not discovery: the footer
// opens the full ranked list, which is deliberately uncapped because every
// view and every dismiss there is ranking-training signal.
//
// Rows are summaries, not cards. Tapping one opens it as the focused idea;
// there is no per-row accept here, because acting on a trade should always
// happen against the full two-sided explanation.

interface Props {
  cards: TradeCard[];
  total: number;
  onOpen: (card: TradeCard) => void;
  onBrowseAll: () => void;
}

export default function FeaturedBench({ cards, total, onOpen, onBrowseAll }: Props) {
  if (cards.length === 0) return null;
  return (
    <View style={styles.bench} testID="presentation.featured">
      <View style={styles.head}>
        <TickLabel>Featured</TickLabel>
        <Text scale="dense" style={styles.count}>
          {cards.length}
        </Text>
      </View>

      {cards.map((c, i) => {
        const who = c.opponent_username?.trim() || 'A league-mate';
        const summary = packageSummary(c);
        return (
          <Pressable
            key={c.trade_id}
            testID={`presentation.featured.row.${i}`}
            accessibilityRole="button"
            accessibilityLabel={`${who}. ${summary}. Open this idea.`}
            onPress={() => onOpen(c)}
            style={({ pressed }) => [
              styles.row,
              i === cards.length - 1 && styles.rowLast,
              pressed && styles.rowPressed,
            ]}
          >
            <View style={styles.body}>
              <Text scale="body" style={styles.who}>
                {who}
              </Text>
              {/* No numberOfLines: OS text scaling must WRAP this, not clip it. */}
              <Text variant="bodySm">{summary}</Text>
            </View>
            <ConfidenceChip band={confidenceBand(c)} />
            <Icon name="chevron-right" size={16} color={chalk.faint} />
          </Pressable>
        );
      })}

      <Pressable
        testID="presentation.browse-all"
        accessibilityRole="button"
        accessibilityLabel={`Browse all ${total} trades`}
        onPress={onBrowseAll}
        style={({ pressed }) => [styles.foot, pressed && styles.rowPressed]}
      >
        <Text scale="body" style={styles.footLink}>
          Browse all {total} trades
        </Text>
        <Text scale="dense" style={styles.footNote}>
          Ranked by mutual fit — viewing and dismissing sharpens your board
        </Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  bench: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    overflow: 'hidden',
  },
  head: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    padding: space.md,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  count: { ...type.data, fontSize: 11, lineHeight: 14, color: chalk.faint },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.md,
    // 44pt minimum target even before text scaling grows the row.
    minHeight: 44,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  rowLast: { borderBottomWidth: 0 },
  rowPressed: { backgroundColor: ink.ink3 },
  body: { flex: 1, minWidth: 0 },
  who: { ...type.body, fontSize: 13, lineHeight: 17, color: chalk.base },
  foot: {
    padding: space.md,
    minHeight: 44,
    borderTopWidth: 1,
    borderTopColor: ink.line,
    alignItems: 'center',
    gap: 2,
  },
  footLink: { ...type.body, color: ice.base },
  footNote: { ...type.bodySm, fontSize: 12, lineHeight: 16, color: chalk.faint, textAlign: 'center' },
});
