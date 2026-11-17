import React, { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';

import { chalk, ice, ink, radii, space } from '../../theme/chalkline';
import { Text } from '../chalkline';
import FounderLabelReview from './FounderLabelReview';
import RuleWaterfallReview, { confirmLeaveNotes, ruleWaterfallQuery } from './RuleWaterfallReview';
import FounderPagesReview, { founderPagesQuery } from './FounderPagesReview';
import { pagesAvailable as hasPages } from '../../utils/founderPages';

// Founders' review — the section's use-case choice: "Player labels | Trade
// rules" (docs/plans/founder-review/rule-waterfall-design.md §6). The Trade
// rules choice appears only when GET /api/founder/rule-waterfall answers
// (getRuleWaterfall returns null on 404, e.g. an older server); until then, or
// without it, the section is the player label review exactly as before.
// Leaving Trade rules with unsaved notes asks first (confirmLeaveNotes).
// A third choice, "Review pages" (docs/plans/founder-review/pages-design.md),
// appears only when GET /api/founder/pages lists at least one page
// (listFounderPages is null on 404); without it every path above is unchanged.

type UseCase = 'labels' | 'rules' | 'pages';

export default function FounderReview({ leagueId, leagueName }: { leagueId: string; leagueName: string | null }) {
  const [useCase, setUseCase] = useState<UseCase>('labels');
  const rulesQ = useQuery(ruleWaterfallQuery(leagueId));
  const rulesAvailable = rulesQ.data != null;
  const pagesQ = useQuery(founderPagesQuery());
  const pagesAvailable = hasPages(pagesQ.data);
  const showRules = rulesAvailable && useCase === 'rules';
  const showPages = pagesAvailable && useCase === 'pages';
  const showLabels = !showRules && !showPages;

  if (!rulesAvailable && !pagesAvailable) return <FounderLabelReview leagueId={leagueId} />;
  return (
    <View style={styles.root}>
      <View style={styles.segmentRow}>
        <Pressable
          testID="founder-review.use.labels"
          accessibilityRole="button"
          accessibilityState={{ selected: showLabels }}
          onPress={() => confirmLeaveNotes(() => setUseCase('labels'))}
          style={[styles.segmentBtn, showLabels && styles.segmentBtnActive]}
        >
          <Text variant="label" style={showLabels ? styles.segmentTextActive : undefined}>Player labels</Text>
        </Pressable>
        {rulesAvailable ? (
          <Pressable
            testID="founder-review.use.rules"
            accessibilityRole="button"
            accessibilityState={{ selected: showRules }}
            onPress={() => setUseCase('rules')}
            style={[styles.segmentBtn, showRules && styles.segmentBtnActive]}
          >
            <Text variant="label" style={showRules ? styles.segmentTextActive : undefined}>Trade rules</Text>
          </Pressable>
        ) : null}
        {pagesAvailable ? (
          <Pressable
            testID="founder-review.use.pages"
            accessibilityRole="button"
            accessibilityState={{ selected: showPages }}
            onPress={() => confirmLeaveNotes(() => setUseCase('pages'))}
            style={[styles.segmentBtn, showPages && styles.segmentBtnActive]}
          >
            <Text variant="label" style={showPages ? styles.segmentTextActive : undefined}>Review pages</Text>
          </Pressable>
        ) : null}
      </View>
      {showRules
        ? <RuleWaterfallReview leagueId={leagueId} leagueName={leagueName} />
        : showPages
          ? <FounderPagesReview />
          : <FounderLabelReview leagueId={leagueId} />}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  // The Calibration section control's construction (hairline group, active =
  // ink-3 well + ice underline).
  segmentRow: {
    flexDirection: 'row',
    marginHorizontal: space.lg,
    marginTop: space.md,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  segmentBtn: {
    flex: 1, minHeight: 44, alignItems: 'center', justifyContent: 'center',
    borderBottomWidth: 2, borderBottomColor: 'transparent',
  },
  segmentBtnActive: { backgroundColor: ink.ink3, borderBottomColor: ice.base },
  segmentTextActive: { color: chalk.base },
});
