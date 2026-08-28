import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import ChalkText from '../components/chalkline/Text';
import { Button, Icon } from '../components/chalkline';
import { chalk, ice, ink, radii, semantic, space } from '../theme/chalkline';
import { getPaywallConfig, type PaywallTip } from '../api/billing';
import {
  getTipProducts,
  isUserCancelled,
  purchaseTip,
  type PurchasesStoreProduct,
} from '../api/purchases';
import { useFlag } from '../state/useFeatureFlags';
import { track } from '../api/events';

// TIP JAR — "support the platform" consumables (operator request 2026-08-28).
//
// SHIPS DARK behind `monetize.paywall` (the flag's contract is "no purchase
// UI anywhere" when off), same double self-guard as PaywallScreen: the local
// flag AND the server's `{"enabled": false}` from /api/paywall/config.
//
// A tip buys NOTHING, and this screen must never suggest otherwise: no
// entitlement copy, no unlock language, no refresh of the entitlements store.
// The backend enforces the same promise mechanically —
// backend/entitlements.is_tip_product() stores the webhook event for the
// revenue ledger and grants nothing. Guideline 3.1.1 is why this is IAP at
// all: money to the developer inside the app must go through the store.
//
// Consumables are not restorable and carry no subscription terms, so there is
// deliberately no Restore button and no auto-renew disclosure here (both are
// 3.1.2 subscription requirements — PaywallScreen's job, not this one's).
//
// #188 — MODAL, so no <FeedbackFAB>.
//
// Chalkline: ink-1 cards, ONE ice fill (the tip CTA), Barlow Condensed
// headers via ChalkText variants. No gradients, no emoji, radius ≤ 8.

interface TipOption {
  tip: PaywallTip;
  /** StoreKit product when the SDK loaded it. Null ⇒ display-only. */
  product: PurchasesStoreProduct | null;
  priceLabel: string;
}

export default function TipJarScreen({ navigation, route }: any) {
  const source: string = route?.params?.source ?? 'unknown';
  const paywallOn = useFlag('monetize.paywall');

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [thanked, setThanked] = useState(false);

  const dismiss = useCallback(() => {
    if (navigation?.canGoBack?.()) navigation.goBack();
    else navigation?.navigate?.('Main');
  }, [navigation]);

  // Self-guard, PaywallScreen convention: route registered unconditionally,
  // screen refuses while the flag is off.
  useEffect(() => {
    if (!paywallOn) dismiss();
  }, [paywallOn, dismiss]);

  const configQuery = useQuery({
    queryKey: ['paywall-config', 'ios'],
    queryFn: () => getPaywallConfig('ios'),
    enabled: paywallOn,
    staleTime: 5 * 60_000,
  });
  const config = configQuery.data;

  // The server's flag beats a stale client flag map.
  useEffect(() => {
    if (config && config.enabled === false) dismiss();
  }, [config, dismiss]);

  const tips = useMemo(() => config?.tips ?? [], [config]);

  const productsQuery = useQuery({
    queryKey: ['tip-products', tips.map((t) => t.product_id).join(',')],
    queryFn: () => getTipProducts(tips.map((t) => t.product_id)),
    enabled: paywallOn && tips.length > 0,
    staleTime: 5 * 60_000,
  });

  const options: TipOption[] = useMemo(
    () =>
      tips.map((tip) => {
        const product =
          productsQuery.data?.find((p) => p.identifier === tip.product_id) ?? null;
        return {
          tip,
          product,
          // StoreKit's localized priceString wins; the server string is the
          // no-SDK fallback so the sheet still renders honestly.
          priceLabel: product?.priceString || tip.display_price,
        };
      }),
    [tips, productsQuery.data],
  );

  useEffect(() => {
    if (!paywallOn) return;
    track('paywall_viewed', { source: 'tip_jar', platform: 'ios' });
  }, [paywallOn]);

  const onTip = useCallback(
    async (option: TipOption) => {
      if (busy) return;
      const productId = option.tip.product_id;
      setError(null);
      track('paywall_purchase_initiated', { product_id: productId, source });
      if (!option.product) {
        setError('Tips aren’t available on this build yet. Thanks for the thought!');
        track('paywall_purchase_failed', { product_id: productId, user_cancelled: false });
        return;
      }
      setBusy(true);
      try {
        const result = await purchaseTip(option.product);
        if (!result) {
          setError('Tips aren’t available on this build yet. Thanks for the thought!');
          track('paywall_purchase_failed', { product_id: productId, user_cancelled: false });
          return;
        }
        track('paywall_purchase_completed', { product_id: productId, source });
        // No entitlement refresh on purpose — a tip changes nothing about
        // what the user can do, and pretending otherwise would be the bug.
        setThanked(true);
      } catch (err) {
        const cancelled = isUserCancelled(err);
        track('paywall_purchase_failed', { product_id: productId, user_cancelled: cancelled });
        if (!cancelled) {
          setError('That didn’t go through. You haven’t been charged.');
        }
      } finally {
        setBusy(false);
      }
    },
    [busy, source],
  );

  if (!paywallOn) return null;

  return (
    <SafeAreaView style={styles.root} testID="tipjar-screen" edges={['top', 'bottom']}>
      <View style={styles.header}>
        <ChalkText variant="heading" style={styles.headerTitle}>
          Support Fleeced
        </ChalkText>
        <Pressable
          testID="tipjar-close"
          accessibilityRole="button"
          accessibilityLabel="Close"
          onPress={dismiss}
          hitSlop={8}
          style={({ pressed }) => [styles.closeBtn, pressed && styles.pressedWell]}
        >
          <Icon name="x" size={20} color={chalk.dim} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.body}>
        {thanked ? (
          <View style={styles.thanksBlock} testID="tipjar-thanks">
            <Icon name="check" size={28} color={ice.base} />
            <ChalkText variant="title" style={styles.thanksTitle}>
              Thank you.
            </ChalkText>
            <ChalkText variant="body" style={styles.thanksBody}>
              Tips keep Fleeced independent — every one goes straight into
              building the tool.
            </ChalkText>
            <Button testID="tipjar-done" label="Done" onPress={dismiss} style={styles.cta} />
          </View>
        ) : (
          <>
            <ChalkText variant="body" style={styles.lede}>
              Fleeced is built by one person. If it’s earned a spot in your
              league routine, a tip helps keep it going. A tip unlocks
              nothing — it’s just a thank-you.
            </ChalkText>

            {configQuery.isLoading ? (
              <View style={styles.loading}>
                <ActivityIndicator color={ice.base} />
              </View>
            ) : null}

            {!configQuery.isLoading && options.length === 0 ? (
              <ChalkText variant="bodySm" style={styles.emptyNote}>
                Tips aren’t available right now.
              </ChalkText>
            ) : null}

            {options.map((option) => (
              <Pressable
                key={option.tip.product_id}
                testID={`tipjar-option-${option.tip.product_id}`}
                accessibilityRole="button"
                accessibilityLabel={`Tip ${option.priceLabel}`}
                disabled={busy}
                onPress={() => onTip(option)}
                style={({ pressed }) => [styles.tipCard, pressed && styles.tipCardPressed]}
              >
                <ChalkText variant="dataLg">{option.priceLabel}</ChalkText>
                <Icon name="chevron-right" size={16} color={chalk.dim} />
              </Pressable>
            ))}

            {busy ? (
              <View style={styles.loading}>
                <ActivityIndicator color={ice.base} />
              </View>
            ) : null}

            {error ? (
              <View style={styles.errorBox}>
                <ChalkText variant="bodySm" style={styles.errorText}>
                  {error}
                </ChalkText>
              </View>
            ) : null}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: ink.ink0 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  headerTitle: { flex: 1 },
  closeBtn: {
    width: 32,
    height: 32,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pressedWell: { backgroundColor: ink.ink3 },
  body: { padding: space.lg, gap: space.md, paddingBottom: space.xxl },
  lede: { marginBottom: space.sm },
  loading: { paddingVertical: space.lg, alignItems: 'center' },
  emptyNote: { textAlign: 'center', paddingVertical: space.lg },
  tipCard: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    padding: space.lg,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  // Press feedback is a border change, never a lift or a shadow.
  tipCardPressed: { borderColor: ice.base },
  errorBox: {
    borderLeftWidth: 3,
    borderLeftColor: semantic.neg,
    backgroundColor: ink.ink1,
    borderRadius: radii.sm,
    padding: space.md,
  },
  errorText: { color: chalk.base },
  thanksBlock: { alignItems: 'center', gap: space.sm, paddingVertical: space.xl },
  thanksTitle: { marginTop: space.xs },
  thanksBody: { textAlign: 'center' },
  cta: { marginTop: space.md, alignSelf: 'stretch' },
});
