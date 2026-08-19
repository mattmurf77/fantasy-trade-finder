// Settings § Guided tour — "The Analyst" opt-in/opt-out toggle.
//
// Lifted verbatim from SettingsScreen.tsx (origin/main) `guideSection` at
// :990-1014, plus the two state reads it depends on:
//   • :117  guidedAvatarOn = useOnboardingFeature('onboarding.guided_avatar')
//   • :118  guideDismissed = useOnboardingState((s) => s.ob.guideDismissed)
//
// #187 — dismiss/disable The Analyst from Settings, both directions.
// Off: same path as the bubble's "Skip the tour" (dismissTour — clears any
// active bubble + tracks guide_tour_dismissed). On: enableTour, which
// RESTARTS the tour from its first step (full-replay semantics — see
// useGuide.enableTour for why resume-only would look broken).
//
// This is a standalone module because plan §4 MOVES it: it leaves the
// "Guided tour" group and joins `SettingsAbout` ("Help & about"), on the
// grounds that it is the in-app help system and belongs beside the FAQ link.
//
// TickLabel: renders `<TickLabel>Guided tour</TickLabel>`, matching the shipped
// screen, so the Phase 0 flat list is unchanged. Plan §3 gives the Phase 2 host
// page the title "Help & about" and folds this control into it — the banner is
// expected to drop when SettingsAbout composes this module.
//
// Intentional behavior changes: NONE. This section has no queries and no
// loading state; nothing to place a per-section placeholder against.
//
// Note: this module takes no `SettingsSectionProps`. It has no notice surface
// and no outbound navigation, so requiring them would be dead API.

import React from 'react';
import { View } from 'react-native';

import { TickLabel } from '../../../components/chalkline';
import { useOnboardingFeature } from '../../../state/useFeatureFlags';
import { useOnboardingState } from '../../../state/useOnboardingState';
import { useGuide } from '../../../state/useGuide';
import { styles } from '../styles';
import Row from '../Row';

export default function GuideSection() {
  const guidedAvatarOn = useOnboardingFeature('onboarding.guided_avatar');
  const guideDismissed = useOnboardingState((s) => s.ob.guideDismissed);

  if (!guidedAvatarOn) return null;

  return (
    <>
      <View style={styles.section}>
        <TickLabel>Guided tour</TickLabel>
      </View>
      <Row
        testID="settings.guided-tour-toggle"
        title="The Analyst"
        sub={
          guideDismissed
            ? 'Off. Turning this on restarts the guided tour from the beginning.'
            : 'In-app guide bubbles on relevant screens. Turn off to dismiss The Analyst everywhere.'
        }
        value={!guideDismissed}
        onChange={() => {
          if (guideDismissed) useGuide.getState().enableTour();
          else useGuide.getState().dismissTour();
        }}
      />
    </>
  );
}

