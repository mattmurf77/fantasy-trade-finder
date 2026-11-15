import React from 'react';
import { StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import FeedbackFAB from '../components/FeedbackFAB';
import { DirectionPage } from '../components/DirectionPage';
import { ink } from '../theme/chalkline';

// Improve Playoff Chances (flag `league.direction_pages`; spec
// docs/plans/league-projections/direction-pages/spec.md §3, D-265). A
// ROOT-STACK push, registered unconditionally in RootNav (the flag gates the
// entry points, not the route), with the Standings header pattern: the
// league selector header (LeagueTopBarHeader) over the #151 JS back. TopBar
// owns the top inset, so this pads the bottom only. The content is shared
// with the other page (components/DirectionPage).
export default function ImprovePlayoffChancesScreen() {
  return (
    <SafeAreaView style={styles.safe} edges={['bottom']} testID="improve-playoffs.screen">
      <DirectionPage page="playoffs" />
      {/* #188 — root-stack push: no tab bar underneath, so it carries its
          own. Exactly one mount. */}
      <FeedbackFAB activeScreen="ImprovePlayoffChances" aboveTabBar={false} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
});
