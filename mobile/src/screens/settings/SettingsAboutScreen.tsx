// Settings › Help & about — second-level page.
//
// Implements plan §3 (`SettingsAbout` row of the page table) and §4. Composes
// two Phase-0 section modules, in this order:
//
//   1. GuideSection — "The Analyst" guided-tour toggle (#187, flag
//      `onboarding.guided_avatar`). Plan §3 grouping call 3 MOVES it here: it
//      is the in-app help system, so it belongs beside the FAQ link rather than
//      owning a top-level group.
//   2. AboutSection — Help & FAQ (flag `ux.help_surface`), Privacy Policy,
//      Terms of Use, and the Version row (finding F7, added in Phase 0 from
//      expo-constants).
//
// BANNERS: both modules carry their own (<TickLabel>Guided tour</TickLabel> and
// <TickLabel>About</TickLabel>, verbatim from the shipped screen), so this page
// adds none.
//
// Neither module takes SettingsSectionProps: GuideSection has no notice surface
// and no outbound navigation, and every AboutSection row opens an external URL
// via Linking. So this page mounts NO Toast — there is nothing to announce, and
// a Toast with no producer is dead state. Add one back with the first row that
// actually needs it.
//
// Data (plan §6): no queries.

import React from 'react';
import { ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import FeedbackFAB from '../../components/FeedbackFAB';
import { styles } from './styles';
import GuideSection from './sections/GuideSection';
import AboutSection from './sections/AboutSection';

export default function SettingsAboutScreen({ navigation: _navigation }: any) {
  return (
    <SafeAreaView style={styles.root} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <GuideSection />
        <AboutSection />
      </ScrollView>
      <FeedbackFAB activeScreen="SettingsAbout" aboveTabBar={false} />
    </SafeAreaView>
  );
}
