// Settings › Ranking — second-level page.
//
// Implements plan §3 (`SettingsRanking` row of the page table). Composes one
// Phase-0 section module:
//
//   • RankingSection — the "we steer ↔ you steer" SteerSlider + its hint,
//     including the v2 immediate-apply reroute of the Rank stack.
//
// BANNER: owned by RankingSection itself (it renders
// <TickLabel>Ranking</TickLabel>, carried verbatim from the shipped screen), so
// this page adds none.
//
// Plan §8 keeps Ranking and Trade values as separate pages even though each is
// small: they answer different questions ("where does the Rank tab open" vs
// "how is a trade priced"), and merging them reproduces the
// undifferentiated-list problem at smaller scale.
//
// Data (plan §6): no queries. `rankingMethodPref` is session state.

import React, { useState } from 'react';
import { ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import FeedbackFAB from '../../components/FeedbackFAB';
import Toast from '../../components/Toast';
import { styles } from './styles';
import RankingSection from './sections/RankingSection';

export default function SettingsRankingScreen({ navigation }: any) {
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);

  // Plan §5 — pushed page, so a plain navigate (no goBack-first hack).
  const navigate = (route: string, params?: object) => navigation.navigate(route, params);
  const onNotice = (msg: string, tone?: 'success' | 'warn') => setToast({ msg, tone });

  return (
    <SafeAreaView style={styles.root} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <RankingSection onNotice={onNotice} navigate={navigate} />
      </ScrollView>
      <Toast
        visible={!!toast}
        message={toast?.msg ?? ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />
      <FeedbackFAB activeScreen="SettingsRanking" aboveTabBar={false} />
    </SafeAreaView>
  );
}
