// Ranking — the "we steer ↔ you steer" SteerSlider + its hint.
//
// Extracted verbatim from SettingsScreen.tsx (origin/main):
//   • `rankingSection`      :885-898
//   • `onRankingPrefChange` :236-246
//   • `rerouteRankStack`    :191-210
//   • `RANK_PREF_ROUTE`     :72-78
//
// SECTION BANNER: OWNED HERE. The shipped block renders its own
// <TickLabel>Ranking</TickLabel> (SettingsScreen.tsx:887-889) rather than
// letting the composition supply it, so it is carried across unchanged.
//
// Behavior changes: none. There is no query here — `rankingMethodPref` is
// session state — so nothing to gate on and no loading placeholder.
//
// One extraction note: `rerouteRankStack` needs the navigator OBJECT
// (getState + dispatch), not the `navigate` helper, so this component reads it
// from `useNavigation()` instead of taking it as a prop. That keeps the module
// self-contained (plan §6) and preserves the dispatch verbatim.

import React from 'react';
import { Text, View } from 'react-native';
import { CommonActions, useNavigation } from '@react-navigation/native';

import { TickLabel } from '../../../components/chalkline';
import SteerSlider from '../../../components/SteerSlider';
import { setRankingMethod } from '../../../api/rankings';
import { useSession, type RankMethodPref } from '../../../state/useSession';
import { useFlag } from '../../../state/useFeatureFlags';
import { styles } from '../styles';
import type { SettingsSectionProps } from './types';

// Where the Rank stack opens per ranking-method pref — mirror of TabNav's
// PREF_ROUTE (settings v2 uses it to re-point the mounted stack so the
// pref applies without a relaunch; TabNav's initialRouteName covers the
// not-yet-mounted case).
const RANK_PREF_ROUTE: Record<RankMethodPref, string> = {
  quickset: 'QuickSetTiers',
  trio:     'Trios',
  anchor:   'Anchors',
  tiers:    'Tiers',
  manual:   'ManualRanks',
};

// Minimal structural view of the navigator state this section walks. The
// shipped code used `any` on the screen's `navigation` prop; strict mode here
// gets the shape it actually reads instead.
interface NavRouteLike { name?: string; state?: NavStateLike }
interface NavStateLike { key?: string; routes?: NavRouteLike[] }
interface RerouteNav {
  getState?: () => unknown;
  dispatch: (action: {
    type: string; payload?: object; source?: string; target?: string;
  }) => void;
}

export default function RankingSection({ onNotice }: SettingsSectionProps) {
  const navigation = useNavigation() as unknown as RerouteNav;
  const settingsV2 = useFlag('account.settings_v2');
  // Rank-home preference — which ranking flow the Rank tab opens at launch.
  // Local persist is what routes; the backend POST is analytics-only, so a
  // failure there never blocks or reverts the slider. With settings v2 on,
  // the pref also applies IMMEDIATELY (S6B-07: "next launch" made the
  // setting look broken) by resetting the mounted Rank stack.
  const rankingPref    = useSession((s) => s.rankingMethodPref);
  const setRankingPref = useSession((s) => s.setRankingMethodPref);

  function rerouteRankStack(m: RankMethodPref) {
    // Reset the nested Rank stack to the chosen flow WITHOUT changing tab
    // focus or dismissing this modal: dispatch a reset targeted at the
    // nested navigator's state key. If the Rank tab was never focused the
    // nested state doesn't exist yet — TabNav's initialRouteName reads the
    // pref at first mount, so no action is needed.
    try {
      const root = navigation.getState?.() as NavStateLike | undefined;
      const mainRoute = root?.routes?.find((r) => r.name === 'Main');
      const rankRoute = mainRoute?.state?.routes?.find((r) => r.name === 'Rank');
      const key = rankRoute?.state?.key;
      if (!key) return;
      navigation.dispatch({
        ...CommonActions.reset({ index: 0, routes: [{ name: RANK_PREF_ROUTE[m] }] }),
        target: key,
      });
    } catch {
      /* best-effort — worst case is the legacy next-launch behavior */
    }
  }

  const onRankingPrefChange = (m: RankMethodPref) => {
    void setRankingPref(m);
    setRankingMethod(m).catch(() => {});
    if (settingsV2) {
      rerouteRankStack(m);
      onNotice('Saved — the Rank tab opens there now.', 'success');
    } else {
      onNotice('Saved — the Rank tab opens there next launch.', 'success');
    }
  };

  return (
    <>
      <View style={styles.section}>
        <TickLabel>Ranking</TickLabel>
      </View>
      <SteerSlider
        value={rankingPref}
        onChange={onRankingPrefChange}
      />
      <Text style={styles.rankingHint}>
        Where the Rank tab opens at launch. Your trade suggestions are only
        as good as your rankings — pick the flow you'll actually keep up with.
      </Text>
    </>
  );
}
