import React from 'react';
import { StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import FeedbackFAB from '../components/FeedbackFAB';
import { DirectionPage } from '../components/DirectionPage';
import { ink } from '../theme/chalkline';

// Improve Draft Pick (flag `league.direction_pages`; spec
// docs/plans/league-projections/direction-pages/spec.md §3, D-265). A
// ROOT-STACK push, registered unconditionally in RootNav (the flag gates the
// entry points, not the route), with the Standings header pattern: the
// league selector header (LeagueTopBarHeader) over the #151 JS back. TopBar
// owns the top inset, so this pads the bottom only. The content is shared
// with the other page (components/DirectionPage).
export default function ImproveDraftPickScreen() {
  return (
    <SafeAreaView style={styles.safe} edges={['bottom']} testID="improve-pick.screen">
      <DirectionPage page="draft_pick" />
      {/* #188 — root-stack push: no tab bar underneath, so it carries its
          own. Exactly one mount. */}
      <FeedbackFAB activeScreen="ImproveDraftPick" aboveTabBar={false} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
});
