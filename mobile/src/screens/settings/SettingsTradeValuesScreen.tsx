// Settings › Trade values — second-level page.
//
// Implements plan §3 (`SettingsTradeValues` row of the page table). Composes
// one Phase-0 section module:
//
//   • TradeValuesSection — the stud-tax segmented control (#214/#215) and the
//     pick-pricing segmented control (flag `trade.slot_pricing`), each with the
//     sub copy describing the active choice.
//
// BANNER: owned by TradeValuesSection itself (it renders
// <TickLabel>Trade values</TickLabel>; pick pricing deliberately has no second
// banner), so this page adds none.
//
// Data (plan §6): this page owns getStudTaxMode() / getPickPricingMode(), both
// fired from inside TradeValuesSection. They no longer run when Settings opens.
//
// Finding F8 — this setting changes how every trade in the app is priced and
// today gets one unlabelled segmented row inline. The page gives it room; the
// explanatory copy itself lives in the section module.

import React, { useState } from 'react';
import { ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import FeedbackFAB from '../../components/FeedbackFAB';
import Toast from '../../components/Toast';
import { styles } from './styles';
import TradeValuesSection from './sections/TradeValuesSection';

export default function SettingsTradeValuesScreen({ navigation }: any) {
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);

  // Plan §5 — pushed page, so a plain navigate (no goBack-first hack).
  const navigate = (route: string, params?: object) => navigation.navigate(route, params);
  const onNotice = (msg: string, tone?: 'success' | 'warn') => setToast({ msg, tone });

  return (
    <SafeAreaView style={styles.root} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <TradeValuesSection onNotice={onNotice} navigate={navigate} />
      </ScrollView>
      <Toast
        visible={!!toast}
        message={toast?.msg ?? ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />
      <FeedbackFAB activeScreen="SettingsTradeValues" aboveTabBar={false} />
    </SafeAreaView>
  );
}
