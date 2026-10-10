import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Text } from '../components/chalkline';
import { useFlag } from '../state/useFeatureFlags';
import { ink, space, type } from '../theme/chalkline';

// Home tab (flag `nav.home_tab`, docs/plans/home-tab/plan.md) — the launch
// tab for returning users: one question and four plain-text ways into the
// app. Each option is a jump to a SIBLING TAB by route name, nothing more;
// the destination tab keeps whatever stack state it already had.
//
// One table drives the rows so copy, target and testID cannot drift apart
// (pinned by mobile/tests/check-home-tab.js). No data, no state, and no
// FeedbackFAB — RootNav's global mount already covers tab screens (#188).
const OPTIONS = [
  { label: 'Rank', tab: 'Rank', testID: 'home.option.rank' },
  { label: 'Find a Trade', tab: 'Trades', testID: 'home.option.trades' },
  { label: 'See Matches', tab: 'Matches', testID: 'home.option.matches' },
  { label: 'View my Leagues', tab: 'League', testID: 'home.option.league' },
] as const;

// Usage Trends (flag `usage_trends.enabled`, docs/plans/usage-trends/) — a
// fifth row, but not a tab jump: it pushes the ROOT-stack `UsageTrends`
// screen. Same row styling so it reads as one more way into the app; the
// flag hides it entirely (reactive useFlag is fine here — a row, unlike a
// tab, can appear without rewriting the navigator).
const TRENDS_ROW = { label: 'Usage Trends', route: 'UsageTrends', testID: 'home.option.trends' } as const;

export default function HomeScreen() {
  const navigation = useNavigation<any>();
  const trendsOn = useFlag('usage_trends.enabled');
  return (
    // No `top` safe-area edge: TabNav's TopBar owns the top inset.
    <View style={styles.root} testID="home.screen">
      <Text variant="heading" style={styles.heading}>
        What would you like to do today?
      </Text>
      {OPTIONS.map((o) => (
        <Pressable
          key={o.tab}
          testID={o.testID}
          accessibilityRole="button"
          accessibilityLabel={o.label}
          onPress={() => navigation.navigate(o.tab)}
          style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
        >
          <Text variant="title">{o.label}</Text>
        </Pressable>
      ))}
      {trendsOn ? (
        <Pressable
          testID={TRENDS_ROW.testID}
          accessibilityRole="button"
          accessibilityLabel={TRENDS_ROW.label}
          onPress={() => navigation.navigate(TRENDS_ROW.route)}
          style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
        >
          <Text variant="title">{TRENDS_ROW.label}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: ink.ink0, paddingHorizontal: space.lg },
  // Sentence case on purpose: the heading token uppercases, and this line is
  // a question put to the user, not a section label.
  heading: { ...type.heading, textTransform: 'none', marginTop: space.xl, marginBottom: space.md },
  row: {
    minHeight: 56,
    justifyContent: 'center',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  rowPressed: { backgroundColor: ink.ink3 },
});
