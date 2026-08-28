import React, { useState } from 'react';
import { ScrollView, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import ShopOffersBody, { type ShopToast } from '../components/ShopOffersBody';
import FeedbackFAB from '../components/FeedbackFAB';
import Toast from '../components/Toast';
import { ink, space } from '../theme/chalkline';

// #402/#403 rev-3 — the SHOP WINDOW (rev3-spec.md §1, superseding the
// inline strip; rulings-2026-08-28b.md R-2: "launch into a new window …
// with back button navigation to the find a trade card").
//
// A ROOT-STACK push from TradesScreen's give-side "More offers" entry
// (direct for one give asset; via the "Shop which player?" chooser for
// several). The deck underneath was never touched — the native back header
// returns to it and no restore logic exists because nothing moves. The
// route is registered UNCONDITIONALLY in RootNav (house rule: the flag
// gates the ENTRY POINT, not the route) with `gestureEnabled: false`
// (rev-1 D-1: iOS interactive pop is a left-edge horizontal drag that
// would fight the body's FlatList pager).
//
// Params carry the RESOLVED asset (rev3-spec §1): the entry already holds
// the full Player from the deck card, so the screen fetches nothing to
// render its header/body context. `assetId`/`assetName`/`source` ride
// along for debuggability and analytics context. Deliberately NO
// `deepLinks.ts` entry (the Receipts/Paywall precedent): a URL cannot
// carry the resolved Player object this screen renders from, so a cold
// deep link could only open a half-broken window — the in-app entry
// points are the only ways in.
//
// This screen OWNS the Toast mount (rev3-spec §1 — the inline era's host
// wiring on TradesScreen is deleted): `onToast` lands descriptors in local
// state, and `onToastRetract` keeps the exact retract-by-reference
// semantics the host had (QA B-4 — clear the slot only if it still holds
// the reference being retracted, so a newer toast is never clobbered).
//
// #188 — a root-stack push mounts its OWN FeedbackFAB (the global RootNav
// mount covers tab screens only), `aboveTabBar={false}` because no tab bar
// renders underneath. The body component mounts none — one FAB, ever.
export default function ShopAssetScreen({ route }: any) {
  const { leagueId, asset } = route.params ?? {};
  const [toast, setToast] = useState<ShopToast | null>(null);

  return (
    <SafeAreaView testID="shop-asset-screen" style={styles.safe} edges={['bottom']}>
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        holdMs={toast?.holdMs ?? 1500}
        action={toast?.action}
        onDismiss={() => setToast(null)}
      />
      {leagueId && asset ? (
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
        >
          <ShopOffersBody
            leagueId={leagueId}
            asset={asset}
            onToast={(t) => setToast(t)}
            // QA B-4 — retract-by-reference: clear the toast slot only if
            // it still holds the exact descriptor the body issued; a newer
            // toast that already replaced it is left alone.
            onToastRetract={(t) => setToast((cur) => (cur === t ? null : cur))}
          />
        </ScrollView>
      ) : null}
      <FeedbackFAB activeScreen="ShopAsset" aboveTabBar={false} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  scroll: { flex: 1 },
  content: {
    padding: space.md,
    paddingBottom: space.xl,
  },
});
