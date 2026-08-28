import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Linking, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import ChalkText from '../components/chalkline/Text';
import { Button, Icon, TickLabel } from '../components/chalkline';
import { chalk, flare, ice, ink, radii, semantic, space } from '../theme/chalkline';
import { getBaseUrl } from '../api/client';
import { getPaywallConfig, type PaywallConfig, type PaywallProduct } from '../api/billing';
import {
  getOfferings,
  hasProEntitlement,
  isUserCancelled,
  purchasePackage,
  restorePurchases,
  type PurchasesPackage,
} from '../api/purchases';
import { useEntitlements } from '../state/useEntitlements';
import { useFlag } from '../state/useFeatureFlags';
import { track } from '../api/events';

// PAYWALL — the one purchase surface in the app (pro-subscription LLD §3/§4,
// iap-enablement scope block).
//
// SHIPS DARK. `monetize.paywall` is false everywhere today; the route is
// registered unconditionally (RootNav rule) and this component self-guards, so
// a stale push while the flag is off dismisses instead of selling anything.
//
// ── App Store guideline 3.1.2, which is why this screen looks the way it
//    does ────────────────────────────────────────────────────────────────
// Everything Apple requires must be VISIBLE BEFORE the purchase, on this
// screen, without scrolling into a legal appendix or tapping through:
//   • the plan's name                    → planTitle()
//   • price and period                   → "$34.99/year"
//   • trial length and what follows it   → "14 days free, then $34.99/year"
//   • auto-renew + how to cancel         → AUTO_RENEW_COPY, rendered above the CTA
//   • a WORKING Restore Purchases        → paywall-restore
//   • tappable Privacy Policy + Terms    → paywall-privacy-link / paywall-terms-link
// Rejections here are cheap to avoid and expensive to fix, so none of these
// are conditional on data loading: the disclosure and the links render even
// when the config fetch fails.
//
// PRICES. StoreKit's localized `priceString` wins whenever offerings loaded —
// it is the only string guaranteed to match what the App Store will charge in
// the user's storefront and currency. The server's `display_price` is the
// fallback for the case where the SDK is unavailable (no key / Expo Go), so
// the screen still renders honestly instead of showing an empty card.
//
// #188 — this is a MODAL. Modals are the documented FeedbackFAB exception, so
// there is deliberately no <FeedbackFAB> here.
//
// Chalkline (ADR-004/005): ink-1 cards, ONE ice fill (the purchase CTA), the
// "Best value" chip flare-BORDERED because it is informational rather than an
// action, Barlow Condensed headers. No gradients, no emoji, radius ≤ 8.

/** Cancel instructions Apple expects, in Apple's own navigation terms. */
const AUTO_RENEW_COPY =
  'Auto-renews until cancelled. Cancel anytime in Settings ▸ Subscriptions.';

/** period → the suffix that turns a price into a price-per-period. */
const PERIOD_SUFFIX: Record<string, string> = {
  monthly: '/month',
  annual: '/year',
  weekly: '/week',
  lifetime: ' once',
  season: ' per season',
};

/** period → plan name. Only used when StoreKit has not given us a localized
 *  product title; never invented for a period we do not recognise. */
const PERIOD_NAME: Record<string, string> = {
  monthly: 'Fleeced Pro — Monthly',
  annual: 'Fleeced Pro — Annual',
  lifetime: 'Fleeced Pro — Lifetime',
  season: 'Fleeced Pro — Season Pass',
};

/** Feature-key → the line the grid shows. Keys are the cross-client enum in
 *  docs/cross-client-invariants.md; an unknown key is skipped rather than
 *  printed raw, so an older binary degrades quietly. */
const FEATURE_COPY: Record<string, string> = {
  unlimited_leagues: 'Every league you play in, not just one',
  portfolio: 'Portfolio — your roster value over time',
  engine_knobs: 'Tune the trade engine to how you trade',
  extension_overlays: 'Full values in the browser extension',
  ad_free: 'No ads, anywhere',
};

interface Plan {
  product: PaywallProduct;
  /** The StoreKit package, when offerings loaded. Null ⇒ display-only. */
  pkg: PurchasesPackage | null;
  title: string;
  priceLine: string;
  perMonth: string | null;
  trialLine: string | null;
}

function planTitle(p: PaywallProduct, pkg: PurchasesPackage | null): string {
  return pkg?.product?.title || PERIOD_NAME[p.period] || 'Fleeced Pro';
}

function priceLine(p: PaywallProduct, pkg: PurchasesPackage | null): string {
  const price = pkg?.product?.priceString || p.display_price;
  return `${price}${PERIOD_SUFFIX[p.period] ?? ''}`;
}

export default function PaywallScreen({ navigation, route }: any) {
  const source: string = route?.params?.source ?? 'unknown';
  const paywallOn = useFlag('monetize.paywall');
  const refreshEntitlements = useEntitlements((s) => s.refresh);
  const noteCustomerInfo = useEntitlements((s) => s.noteCustomerInfo);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dismiss = useCallback(() => {
    if (navigation?.canGoBack?.()) navigation.goBack();
    else navigation?.navigate?.('Main');
  }, [navigation]);

  // Self-guard. The route stays registered while the flag is off (a flag must
  // gate the entry point, not the navigator entry), so the screen itself is
  // what refuses: pop immediately and render nothing.
  useEffect(() => {
    if (!paywallOn) dismiss();
  }, [paywallOn, dismiss]);

  const configQuery = useQuery({
    queryKey: ['paywall-config', 'ios'],
    queryFn: () => getPaywallConfig('ios'),
    enabled: paywallOn,
    staleTime: 5 * 60_000,
  });

  // Offerings are a SEPARATE, failure-tolerant read: `getOfferings` resolves
  // null rather than throwing when purchases are unavailable, so a missing SDK
  // degrades the screen to server prices instead of an error state.
  const offeringsQuery = useQuery({
    queryKey: ['paywall-offerings'],
    queryFn: () => getOfferings(),
    enabled: paywallOn,
    staleTime: 5 * 60_000,
  });

  const config: PaywallConfig | undefined = configQuery.data;

  // The SERVER's flag beats this device's cached one. `{"enabled": false}` is
  // what /api/paywall/config answers while `monetize.paywall` is off, so a
  // client whose flag map is stale (or overlaid by an experiment) still leaves
  // rather than selling a product the server says is not for sale.
  useEffect(() => {
    if (config && config.enabled === false) dismiss();
  }, [config, dismiss]);

  const dismissible = config?.dismissible !== false;
  const products = useMemo(() => config?.products ?? [], [config]);

  const plans: Plan[] = useMemo(() => {
    const packages = offeringsQuery.data?.current?.availablePackages ?? [];
    return products.map((p) => {
      const pkg = packages.find((x) => x.product?.identifier === p.product_id) ?? null;
      const price = priceLine(p, pkg);
      const trialEligible = config?.trial_eligible !== false;
      return {
        product: p,
        pkg,
        title: planTitle(p, pkg),
        priceLine: price,
        perMonth: p.per_month_equiv ? `${p.per_month_equiv}/month, billed yearly` : null,
        trialLine:
          trialEligible && p.trial_days > 0
            ? `${p.trial_days} days free, then ${price}`
            : null,
      };
    });
  }, [products, offeringsQuery.data, config]);

  // Default selection = the hero SKU the server marked, else the first plan.
  useEffect(() => {
    if (selectedId || plans.length === 0) return;
    setSelectedId((plans.find((p) => p.product.hero) ?? plans[0]).product.product_id);
  }, [plans, selectedId]);

  useEffect(() => {
    if (!paywallOn) return;
    // `platform` is the literal 'ios': this build's only store surface is the
    // App Store (the RevenueCat key is the Apple SDK key), and a literal keeps
    // the taxonomy dimension enumerable.
    track('paywall_viewed', { source, platform: 'ios' });
  }, [paywallOn, source]);

  const selected = plans.find((p) => p.product.product_id === selectedId) ?? null;

  const onPurchase = useCallback(async () => {
    if (!selected || busy) return;
    const productId = selected.product.product_id;
    setError(null);
    track('paywall_purchase_initiated', { product_id: productId, source });
    if (!selected.pkg) {
      // No StoreKit package behind this row — offerings never loaded (no SDK
      // key, Expo Go, or a RevenueCat offering that does not carry this SKU).
      // Say so plainly rather than pretending to charge.
      setError('Purchases aren’t available on this build yet. Try again after the next update.');
      track('paywall_purchase_failed', { product_id: productId, user_cancelled: false });
      return;
    }
    setBusy(true);
    try {
      const result = await purchasePackage(selected.pkg);
      if (!result) {
        setError('Purchases aren’t available on this build yet. Try again after the next update.');
        track('paywall_purchase_failed', { product_id: productId, user_cancelled: false });
        return;
      }
      track('paywall_purchase_completed', { product_id: productId, source });
      // Optimistic unlock so the app opens up now; the webhook + the fetch
      // below are what actually decide, and the server can still say no.
      noteCustomerInfo(hasProEntitlement(result.customerInfo));
      await refreshEntitlements();
      dismiss();
    } catch (err) {
      const cancelled = isUserCancelled(err);
      track('paywall_purchase_failed', { product_id: productId, user_cancelled: cancelled });
      // A cancel is a decision, not a failure — it gets no error message.
      if (!cancelled) {
        setError('That purchase didn’t go through. You haven’t been charged.');
      }
    } finally {
      setBusy(false);
    }
  }, [selected, busy, source, noteCustomerInfo, refreshEntitlements, dismiss]);

  const onRestore = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const info = await restorePurchases();
      const restored = hasProEntitlement(info);
      track('paywall_restore', { restored });
      if (restored) noteCustomerInfo(true);
      // Always re-ask the server: a restore that found nothing on THIS Apple
      // ID can still be a user whose grant lives on their account row.
      await refreshEntitlements();
      if (restored) dismiss();
      else setError('No subscription found on this Apple ID.');
    } finally {
      setBusy(false);
    }
  }, [busy, noteCustomerInfo, refreshEntitlements, dismiss]);

  const openLegal = useCallback((path: '/privacy' | '/terms') => {
    // The backend origin serves the web app at `/` (client.ts getBaseUrl), so
    // the legal pages live at the API base — one origin, no second constant to
    // drift when the deploy target moves.
    void Linking.openURL(`${getBaseUrl()}${path}`);
  }, []);

  if (!paywallOn) return null;

  const featurePage = config?.pages?.find((p) => p.kind === 'features');
  const headlinePage = config?.pages?.find((p) => p.kind === 'trades_found');
  const loading = configQuery.isLoading || offeringsQuery.isLoading;

  return (
    <SafeAreaView style={styles.root} testID="paywall-screen" edges={['top', 'bottom']}>
      <View style={styles.header}>
        <ChalkText variant="heading" style={styles.headerTitle}>
          Fleeced Pro
        </ChalkText>
        {dismissible ? (
          <Pressable
            testID="paywall-close"
            accessibilityRole="button"
            accessibilityLabel="Close"
            onPress={dismiss}
            hitSlop={8}
            style={({ pressed }) => [styles.closeBtn, pressed && styles.pressedWell]}
          >
            <Icon name="x" size={20} color={chalk.dim} />
          </Pressable>
        ) : null}
      </View>

      <ScrollView contentContainerStyle={styles.body}>
        {headlinePage?.title ? (
          <ChalkText variant="display" style={styles.hero}>
            {headlinePage.title}
          </ChalkText>
        ) : null}

        {featurePage?.features?.length ? (
          <View style={styles.featureBlock}>
            <TickLabel>What you get</TickLabel>
            {featurePage.features.map((key) =>
              FEATURE_COPY[key] ? (
                <View key={key} style={styles.featureRow}>
                  <Icon name="check" size={16} color={ice.base} />
                  <ChalkText variant="body" style={styles.featureText}>
                    {FEATURE_COPY[key]}
                  </ChalkText>
                </View>
              ) : null,
            )}
          </View>
        ) : null}

        {loading ? (
          <View style={styles.loading}>
            <ActivityIndicator color={ice.base} />
          </View>
        ) : null}

        {!loading && plans.length === 0 ? (
          <ChalkText variant="bodySm" style={styles.emptyNote}>
            Plans aren’t available right now. Please try again later.
          </ChalkText>
        ) : null}

        {plans.map((plan) => {
          const active = plan.product.product_id === selectedId;
          return (
            <Pressable
              key={plan.product.product_id}
              testID={`paywall-plan-${plan.product.product_id}`}
              accessibilityRole="radio"
              accessibilityState={{ selected: active }}
              accessibilityLabel={
                `${plan.title}. ${plan.priceLine}.` +
                (plan.trialLine ? ` ${plan.trialLine}.` : '')
              }
              onPress={() => setSelectedId(plan.product.product_id)}
              style={({ pressed }) => [
                styles.planCard,
                active && styles.planCardActive,
                pressed && styles.pressedWell,
              ]}
            >
              <View style={styles.planHeadRow}>
                <ChalkText variant="title" style={styles.planTitle}>
                  {plan.title}
                </ChalkText>
                {plan.product.badge === 'best_value' ? (
                  <View style={styles.badge}>
                    <ChalkText variant="label" style={styles.badgeText}>
                      Best value
                    </ChalkText>
                  </View>
                ) : null}
              </View>
              <ChalkText variant="dataLg" style={styles.planPrice}>
                {plan.priceLine}
              </ChalkText>
              {plan.perMonth ? (
                <ChalkText variant="bodySm">{plan.perMonth}</ChalkText>
              ) : null}
              {plan.trialLine ? (
                <ChalkText variant="bodySm">{plan.trialLine}</ChalkText>
              ) : null}
            </Pressable>
          );
        })}

        {error ? (
          <View style={styles.errorBox}>
            <ChalkText variant="bodySm" style={styles.errorText}>
              {error}
            </ChalkText>
          </View>
        ) : null}

        {/* Guideline 3.1.2 — renders unconditionally, above the CTA, whether or
            not the plan fetch succeeded. */}
        <ChalkText variant="bodySm" style={styles.disclosure}>
          {AUTO_RENEW_COPY}
        </ChalkText>

        <Button
          testID="paywall-purchase-cta"
          label={selected?.trialLine ? 'Start free trial' : 'Continue'}
          onPress={onPurchase}
          loading={busy}
          disabled={!selected || busy}
          style={styles.cta}
        />

        <Button
          testID="paywall-restore"
          label="Restore Purchases"
          variant="ghost"
          onPress={onRestore}
          disabled={busy}
        />

        <View style={styles.legalRow}>
          <Pressable
            testID="paywall-privacy-link"
            accessibilityRole="link"
            accessibilityHint="Opens in your browser"
            onPress={() => openLegal('/privacy')}
            hitSlop={8}
          >
            <ChalkText variant="bodySm" style={styles.legalLink}>
              Privacy Policy
            </ChalkText>
          </Pressable>
          <ChalkText variant="bodySm" style={styles.legalDot}>
            ·
          </ChalkText>
          <Pressable
            testID="paywall-terms-link"
            accessibilityRole="link"
            accessibilityHint="Opens in your browser"
            onPress={() => openLegal('/terms')}
            hitSlop={8}
          >
            <ChalkText variant="bodySm" style={styles.legalLink}>
              Terms of Use
            </ChalkText>
          </Pressable>
        </View>
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
  hero: { marginBottom: space.sm },
  featureBlock: { gap: space.sm, marginBottom: space.sm },
  featureRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  featureText: { flex: 1 },
  loading: { paddingVertical: space.xl, alignItems: 'center' },
  emptyNote: { textAlign: 'center', paddingVertical: space.lg },
  planCard: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    padding: space.lg,
    gap: space.xs,
  },
  // Selection is a border change, never a lift or a shadow (prohibition #7/#8).
  planCardActive: { borderColor: ice.base },
  planHeadRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  planTitle: { flex: 1 },
  // Informational highlight ⇒ flare BORDER + flare text on ink, never a fill
  // and never on the action itself (ADR-005).
  badge: {
    borderWidth: 1,
    borderColor: flare.base,
    borderRadius: radii.xs,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  badgeText: { color: flare.base },
  planPrice: { marginTop: space.xs },
  errorBox: {
    borderLeftWidth: 3,
    borderLeftColor: semantic.neg,
    backgroundColor: ink.ink1,
    borderRadius: radii.sm,
    padding: space.md,
  },
  errorText: { color: chalk.base },
  disclosure: { marginTop: space.xs },
  cta: { marginTop: space.xs },
  legalRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    marginTop: space.sm,
  },
  legalLink: { color: ice.base },
  legalDot: { color: chalk.faint },
});
