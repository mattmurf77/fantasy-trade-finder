import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  useWindowDimensions,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import ChalkText from '../components/chalkline/Text';
import { Button, Icon } from '../components/chalkline';
import { chalk, flare, ice, ink, radii, space } from '../theme/chalkline';
import { getBaseUrl } from '../api/client';
import { getPaywallConfig, type PaywallConfig, type PaywallProduct } from '../api/billing';
import {
  activeProFrom,
  checkIntroEligibility,
  getOfferings,
  hasProEntitlement,
  initPurchases,
  isIdentityReady,
  isPaymentPending,
  isUserCancelled,
  onIdentityChange,
  purchasePackage,
  purchasesReady,
  restorePurchases,
  type PurchasesPackage,
  type PurchasesStoreProduct,
} from '../api/purchases';
import { useEntitlements } from '../state/useEntitlements';
import { useFlag } from '../state/useFeatureFlags';
import { useSession } from '../state/useSession';
import { isUnverifiedSession, verifyThenReturn } from '../state/usePaywallGate';
import { track } from '../api/events';
import { claimFounderWelcome, clubWindowOpen } from './FounderWelcomeScreen';
import {
  FOUNDER_TAG,
  MON,
  PLAN_TITLE,
  annualSubLine,
  ctaLabel,
  disclosure,
  headlineFor,
  inviteeContext,
  offerBodyFor,
  planPeriod,
  pricePerPeriod,
  trialLine,
  type PlanPeriod,
} from '../copy/monetization';

// PAYWALL — the one purchase surface in the app (#393 M1; ux-lead
// "Monetization copy placement"; design-lead §1 FINAL). Every string is a
// `mon.*` key from copy/monetization.ts, verbatim from marketing-lead §9 with
// legal's R28.8 rules.
//
// SHIPS DARK. `monetize.paywall` is false everywhere today; the route is
// registered unconditionally (RootNav rule) and this component self-guards,
// so a stale push while the flag is off dismisses instead of selling.
//
// ONE SCREEN, VARIANTS BY HOW IT WAS OPENED (`route.params.source`):
//   gate (a locked action, with the 402's `gate` + `kind`) → mon.lock.find /
//   mon.lock.send · first_opinion / left_deck (the M2 trigger) →
//   mon.offer.headline + mon.offer.body · preview_end (the M2 end card) →
//   mon.offer.headline, no body · settings / anything else → mon.pay.headline.
// VERIFIED SESSIONS ONLY: a session the server reported unverified gets the
// VerifySheet instead, never the paywall or the trial offer (R28.9).
// D9 (M3): ONE route to it from here, `verifyFirst`, for both the backstop
// (unverified while this is up) and the button / Restore tapped by an
// unverified session: this modal closes, the sheet opens, and only on
// `verified` does the SAME paywall come back (same variant, same plan
// selected). Nothing reaches Apple's sheet first; nothing is bought for the
// user after verifying. The routing reads the session only (D15).
//
// THE WELCOME (M3, D10): a purchase (trial start or paid) made inside the
// Founding GMs window replaces this modal with FounderWelcome, once per
// user; its Back returns to the same card. After the cut-off, or once it
// has shown, the paywall just closes.
//
// INVITEES (M3, §9.6): the trigger variant shows `mon.invitee.context` as
// the eyebrow and `mon.invitee.board` under the body, only when the
// session still holds BOTH the inviter and the league name; otherwise
// neither line renders (never a broken template).
//
// LAYOUT: a scroll area (headline, body, value + bullets, free line, the
// Founding GMs block in the club window) above a BOTTOM-ANCHORED block that
// is always visible: the plan radio rows, the selected plan's price and
// trial line, its disclosure, the button, and Not now · Restore · Terms ·
// Privacy. The block is about 326 pt, so it fits a 4.7" SE (667 pt); if large
// Dynamic Type makes it taller than half the window it stops anchoring and
// joins the end of the scroll, keeping its order. Nothing is clipped.
//
// "FREE" ONLY WHEN STOREKIT CONFIRMS IT (R28.8 #1): the trial line, the trial
// disclosure and "Start 1-month trial" render only when RevenueCat confirms
// this Apple ID's free month for the selected plan. Unknown, loading or an
// error is the PAID state: the paid disclosure, "Subscribe", no "free"
// anywhere. `config.trial_eligible` is never read for copy.
//
// No countdown, days-left, trial-end date or "ends soon" anywhere (D10).
//
// #188 — this is a MODAL. Modals are the documented FeedbackFAB exception, so
// there is deliberately no FeedbackFAB here.
//
// Chalkline: ice only for the one primary action and the selected plan;
// flare only for the FounderTag. No SAVE badge, no gradients, no red.

const BULLETS = ['mon.pay.b1', 'mon.pay.b2', 'mon.pay.b3', 'mon.pay.b4'] as const;
const FOUNDER_LINES = [
  'mon.pay.founder.price',
  'mon.pay.founder.new',
  'mon.pay.founder.keep',
  'mon.pay.founder.lapse',
] as const;

/** Shown only on a build without the RevenueCat key (dev / pre-11-05). */
const UNAVAILABLE_COPY =
  'Purchases aren’t available on this build yet. Try again after the next update.';

type Status = 'error' | 'pending' | 'restore_ok' | 'restore_none' | 'unavailable';

interface Plan {
  product: PaywallProduct;
  period: PlanPeriod;
  /** The StoreKit package, when offerings loaded. Null ⇒ display-only. */
  pkg: PurchasesPackage | null;
  /** StoreKit's localized price when offerings loaded, else the server's. */
  price: string;
}

export default function PaywallScreen({ navigation, route }: any) {
  const source: string = route?.params?.source ?? 'unknown';
  const gate: string | undefined = route?.params?.gate || undefined;
  const kind: 'find' | 'send' | undefined =
    route?.params?.kind === 'send' || route?.params?.kind === 'find' ? route.params.kind : undefined;
  const paywallOn = useFlag('monetize.paywall');
  const refreshEntitlements = useEntitlements((s) => s.refresh);
  const noteCustomerInfo = useEntitlements((s) => s.noteCustomerInfo);
  const userId = useSession((s) => s.user?.user_id ?? null);
  const unverified = useSession((s) => !s.isDemo && s.verification?.session_verified === false);
  const planParam: string | undefined = route?.params?.plan || undefined;
  // Read-only: the invite intent as the session holds it (useSession P0-3).
  const invitedBy = useSession((s) => s.invitedBy);
  const invitedLeagueName = useSession((s) => s.invitedLeagueName);
  const { height: windowHeight } = useWindowDimensions();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);
  const [idReady, setIdReady] = useState(() => isIdentityReady(userId));
  const [blockHeight, setBlockHeight] = useState(0);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
  }, []);

  const dismiss = useCallback(() => {
    if (navigation?.canGoBack?.()) navigation.goBack();
    else navigation?.navigate?.('Main');
  }, [navigation]);
  const closeSoon = useCallback(() => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(dismiss, 2500);
  }, [dismiss]);

  // Self-guard. The route stays registered while the flag is off (a flag must
  // gate the entry point, not the navigator entry), so the screen itself is
  // what refuses: pop immediately and render nothing.
  useEffect(() => {
    if (!paywallOn) dismiss();
  }, [paywallOn, dismiss]);

  // D9 — the ONE route from this screen to the VerifySheet: close this
  // modal, then (once it's gone, so the two never present at once) the
  // sheet; on `verified`, the same paywall with the same plan selected.
  // Reads the session only (D15). Once per mount: the backstop and a tap
  // can't both pop the stack.
  const leavingForVerify = useRef(false);
  const verifyFirst = useCallback(() => {
    if (leavingForVerify.current) return;
    leavingForVerify.current = true;
    const back = {
      source,
      ...(gate ? { gate } : {}),
      ...(kind ? { kind } : {}),
      ...(selectedId ? { plan: selectedId } : {}),
    };
    dismiss();
    // Not cleared on unmount: dismissing unmounts this screen, and the sheet
    // must still open once the modal is gone. openVerify is idempotent.
    setTimeout(() => void verifyThenReturn(back), 450);
  }, [source, gate, kind, selectedId, dismiss]);

  // Backstop for a direct navigate (the router already sends these to the
  // sheet): an unverified session gets the VerifySheet. Nothing
  // subscription-specific renders in between (R28.9).
  useEffect(() => {
    if (!paywallOn || !unverified) return;
    verifyFirst();
  }, [paywallOn, unverified, verifyFirst]);

  const configQuery = useQuery({
    queryKey: ['paywall-config', 'ios'],
    queryFn: () => getPaywallConfig('ios'),
    enabled: paywallOn && !unverified,
    staleTime: 5 * 60_000,
  });

  // Offerings are a SEPARATE, failure-tolerant read: `getOfferings` resolves
  // null rather than throwing when purchases are unavailable, so a missing SDK
  // degrades the screen to server prices instead of an error state.
  const offeringsQuery = useQuery({
    queryKey: ['paywall-offerings'],
    queryFn: () => getOfferings(),
    enabled: paywallOn && !unverified,
    staleTime: 5 * 60_000,
  });

  const config: PaywallConfig | undefined = configQuery.data;

  // The SERVER's flag beats this device's cached one. `{"enabled": false}` is
  // what /api/paywall/config answers while `monetize.paywall` is off, so a
  // client whose flag map is stale still leaves rather than selling.
  useEffect(() => {
    if (config && config.enabled === false) dismiss();
  }, [config, dismiss]);

  // `dismissible` (always true from S1) governs Close, Not now and the swipe.
  const dismissible = config?.dismissible !== false;
  useEffect(() => {
    navigation?.setOptions?.({ gestureEnabled: dismissible });
  }, [navigation, dismissible]);

  // Only the two launch SKUs, whose titles match App Store Connect (R28.8
  // #6): Annual (the hero) first, Monthly below.
  const plans: Plan[] = useMemo(() => {
    const packages = offeringsQuery.data?.current?.availablePackages ?? [];
    const out: Plan[] = [];
    for (const product of config?.products ?? []) {
      const period = planPeriod(product.period);
      if (!period) continue;
      const pkg = packages.find((x) => x.product?.identifier === product.product_id) ?? null;
      out.push({ product, period, pkg, price: pkg?.product?.priceString || product.display_price });
    }
    return out.sort((a, b) => (a.period === 'annual' ? 0 : 1) - (b.period === 'annual' ? 0 : 1));
  }, [config, offeringsQuery.data]);

  // StoreKit intro eligibility for the two products (D6). Until it answers,
  // and on any error, `eligibleFor` is false: the paid state.
  const storeProducts = useMemo(
    () => plans.map((p) => p.pkg?.product).filter((p): p is PurchasesStoreProduct => !!p),
    [plans],
  );
  const eligibilityQuery = useQuery({
    queryKey: ['paywall-intro-eligibility', userId, storeProducts.map((p) => p.identifier).join(',')],
    queryFn: () => checkIntroEligibility(storeProducts),
    enabled: paywallOn && !unverified && storeProducts.length > 0,
    staleTime: 60_000,
  });
  const eligibleFor = (productId: string) => eligibilityQuery.data?.[productId] === true;

  // Default selection = the plan a verify round-trip carried back (D9), else
  // Annual (the hero), else the first plan.
  useEffect(() => {
    if (selectedId || plans.length === 0) return;
    const pick = plans.find((p) => p.product.product_id === planParam)
      ?? plans.find((p) => p.period === 'annual')
      ?? plans[0];
    setSelectedId(pick.product.product_id);
  }, [plans, selectedId, planParam]);

  const selected = plans.find((p) => p.product.product_id === selectedId) ?? null;
  const eligible = !!selected && eligibleFor(selected.product.product_id);

  // R28.8 #2: "$2.09/month, billed yearly. 58% less than 12 months at $4.99."
  // from live StoreKit prices only; absent without them.
  const annualSub = useMemo(() => {
    const annual = plans.find((p) => p.period === 'annual')?.pkg?.product;
    const monthly = plans.find((p) => p.period === 'monthly')?.pkg?.product;
    return annualSubLine(annual, monthly);
  }, [plans]);

  // RevenueCat identity must be this session's user before Apple's sheet
  // (D12). While it isn't, the button shows a pending state.
  useEffect(() => {
    setIdReady(isIdentityReady(userId));
    const unsub = onIdentityChange(() => setIdReady(isIdentityReady(userId)));
    // A logIn that failed earlier gets another go; the bridge never throws.
    if (userId && purchasesReady() && !isIdentityReady(userId)) void initPurchases(userId);
    return unsub;
  }, [userId]);
  const identityPending = purchasesReady() && !idReady;

  useEffect(() => {
    if (!paywallOn || unverified) return;
    // `platform` is the literal 'ios': this build's only store surface is the
    // App Store, and a literal keeps the taxonomy dimension enumerable.
    // `gate` (the 402's reason) and `kind` (find | send) ride only when the
    // paywall was opened by a locked action.
    track('paywall_viewed', {
      source,
      platform: 'ios',
      ...(gate ? { gate } : {}),
      ...(kind ? { kind } : {}),
    });
  }, [paywallOn, unverified, source, gate, kind]);

  const onPurchase = useCallback(async () => {
    // D9: an unverified session never reaches Apple's sheet.
    if (isUnverifiedSession()) {
      verifyFirst();
      return;
    }
    if (!selected || busy || !userId) return;
    const productId = selected.product.product_id;
    setStatus(null);
    track('paywall_purchase_initiated', { product_id: productId, source });
    if (!selected.pkg) {
      // No StoreKit package behind this row — offerings never loaded (no SDK
      // key, Expo Go, or an offering without this SKU). Say so plainly.
      setStatus('unavailable');
      track('paywall_purchase_failed', { product_id: productId, user_cancelled: false });
      return;
    }
    setBusy(true);
    try {
      const result = await purchasePackage(selected.pkg, userId);
      if (!result) {
        setStatus('unavailable');
        track('paywall_purchase_failed', { product_id: productId, user_cancelled: false });
        return;
      }
      track('paywall_purchase_completed', { product_id: productId, source });
      // Optimistic unlock so the app opens up now; the webhook + the fetch
      // below are what actually decide, and the server can still say no.
      noteCustomerInfo(hasProEntitlement(result.customerInfo));
      await refreshEntitlements();
      // D10: the Founding GMs welcome, once per user, only inside the club
      // window. It REPLACES this modal, so its Back lands on the same card.
      if (clubWindowOpen(config?.club, Date.now()) && (await claimFounderWelcome(userId))) {
        navigation.replace('FounderWelcome', {
          period: selected.period,
          since: activeProFrom(result.customerInfo)?.since ?? new Date().toISOString(),
        });
        return;
      }
      dismiss();
    } catch (err) {
      const cancelled = isUserCancelled(err);
      track('paywall_purchase_failed', { product_id: productId, user_cancelled: cancelled });
      if (isPaymentPending(err)) {
        // Ask to Buy: nothing charged yet. Say so once, then close.
        setStatus('pending');
        closeSoon();
      } else if (!cancelled) {
        // A cancel is a decision, not a failure — it gets no message.
        setStatus('error');
      }
    } finally {
      setBusy(false);
    }
  }, [selected, busy, userId, source, noteCustomerInfo, refreshEntitlements, dismiss, closeSoon, verifyFirst, config, navigation]);

  const onRestore = useCallback(async () => {
    // D9: Restore waits for verification too (R28.9 3f).
    if (isUnverifiedSession()) {
      verifyFirst();
      return;
    }
    if (busy || !userId) return;
    setBusy(true);
    setStatus(null);
    try {
      const info = await restorePurchases(userId);
      const restored = hasProEntitlement(info);
      track('paywall_restore', { restored });
      if (restored) noteCustomerInfo(true);
      // Always re-ask the server: a restore that found nothing on THIS Apple
      // ID can still be a user whose grant lives on their account row.
      await refreshEntitlements();
      if (restored) {
        setStatus('restore_ok');
        closeSoon();
      } else {
        // The offer stays open.
        setStatus('restore_none');
      }
    } catch {
      // RevenueCat's identity couldn't be confirmed as this user.
      setStatus('error');
    } finally {
      setBusy(false);
    }
  }, [busy, userId, noteCustomerInfo, refreshEntitlements, closeSoon, verifyFirst]);

  const openLegal = useCallback((path: '/privacy' | '/terms') => {
    // The backend origin serves the web app at `/` (client.ts getBaseUrl), so
    // the legal pages live at the API base — one origin, no second constant.
    void Linking.openURL(`${getBaseUrl()}${path}`);
  }, []);

  if (!paywallOn || unverified) return null;

  const loading = configQuery.isLoading || offeringsQuery.isLoading;
  const body = offerBodyFor(source, eligible);
  // §9.6: invitees, on the trigger variant only.
  const trigger = source === 'first_opinion' || source === 'left_deck';
  const invitee = trigger ? inviteeContext(invitedBy, invitedLeagueName) : null;
  const clubOpen = config?.club?.open === true;
  // Dynamic Type: past half the window, the block joins the scroll's end.
  const unanchored = blockHeight > 0 && blockHeight > windowHeight * 0.5;

  const statusSlot = status ? (
    <View style={styles.statusSlot} testID="paywall-status" accessibilityLiveRegion="polite">
      <ChalkText variant="bodySm" style={styles.statusText}>
        {status === 'error'
          ? MON['mon.pay.error']
          : status === 'pending'
            ? MON['mon.pay.pending']
            : status === 'restore_ok'
              ? MON['mon.pay.restore_ok']
              : status === 'restore_none'
                ? MON['mon.pay.restore_none']
                : UNAVAILABLE_COPY}
      </ChalkText>
      {status === 'error' ? (
        <Button
          testID="paywall-try-again"
          label={MON['mon.pay.error.retry']}
          variant="ghost"
          compact
          onPress={() => void onPurchase()}
          disabled={busy}
        />
      ) : null}
    </View>
  ) : null;

  const anchoredBlock = (
    <View
      style={[styles.anchored, unanchored && styles.anchoredInline]}
      onLayout={(e) => setBlockHeight(e.nativeEvent.layout.height)}
      testID="paywall-anchored"
    >
      {statusSlot}
      <View accessibilityRole="radiogroup" style={styles.plans}>
        {plans.map((plan) => {
          const active = plan.product.product_id === selectedId;
          const pp = pricePerPeriod(plan.period, plan.price);
          const sub = plan.period === 'annual' ? annualSub : null;
          return (
            <Pressable
              key={plan.product.product_id}
              testID={`paywall-plan-${plan.product.product_id}`}
              accessibilityRole="radio"
              accessibilityState={{ selected: active, checked: active }}
              accessibilityLabel={`${PLAN_TITLE[plan.period]}. ${pp}.${sub ? ` ${sub}` : ''}`}
              onPress={() => setSelectedId(plan.product.product_id)}
              style={({ pressed }) => [
                styles.planRow,
                active && styles.planRowActive,
                pressed && styles.pressedWell,
              ]}
            >
              <View style={styles.planLeft}>
                <ChalkText variant="title">{PLAN_TITLE[plan.period]}</ChalkText>
                {sub ? <ChalkText variant="bodySm">{sub}</ChalkText> : null}
              </View>
              {/* /year is the largest price text (R28.8 #2): data-lg, while
                  the per-month figure above is body-sm. */}
              <ChalkText variant="dataLg">{pp}</ChalkText>
            </Pressable>
          );
        })}
      </View>

      {selected ? (
        <View style={styles.summary} testID="paywall-summary">
          {/* The selected price, at 22 pt against the button's 14 pt label:
              the prominence legal's CTA rule reads (R28.8 #3). */}
          <ChalkText variant="dataLg">{pricePerPeriod(selected.period, selected.price)}</ChalkText>
          {eligible ? (
            <ChalkText variant="bodySm" style={styles.trialLine}>
              {trialLine(selected.period, selected.price)}
            </ChalkText>
          ) : null}
        </View>
      ) : null}

      {selected ? (
        <ChalkText variant="bodySm" style={styles.disclosure} testID="paywall-disclosure">
          {disclosure(selected.period, selected.price, eligible)}
        </ChalkText>
      ) : null}

      <View testID="paywall-offer-cta">
        <Button
          testID="paywall-purchase-cta"
          label={ctaLabel(eligible)}
          onPress={() => void onPurchase()}
          loading={busy || identityPending}
          disabled={!selected || busy || identityPending}
        />
      </View>

      <View style={styles.linkRow}>
        {dismissible ? (
          <>
            <Pressable
              testID="paywall-offer-not-now"
              accessibilityRole="button"
              onPress={dismiss}
              style={styles.linkHit}
            >
              <ChalkText variant="bodySm" style={styles.linkChalk}>
                {MON['mon.offer.not_now']}
              </ChalkText>
            </Pressable>
            <ChalkText variant="bodySm" style={styles.linkDot}>
              ·
            </ChalkText>
          </>
        ) : null}
        <Pressable
          testID="paywall-restore"
          accessibilityRole="button"
          onPress={() => void onRestore()}
          disabled={busy}
          style={styles.linkHit}
        >
          <ChalkText variant="bodySm" style={styles.linkChalk}>
            {MON['mon.pay.restore']}
          </ChalkText>
        </Pressable>
        <ChalkText variant="bodySm" style={styles.linkDot}>
          ·
        </ChalkText>
        <Pressable
          testID="paywall-terms-link"
          accessibilityRole="link"
          accessibilityHint="Opens in your browser"
          onPress={() => openLegal('/terms')}
          style={styles.linkHit}
        >
          <ChalkText variant="bodySm" style={styles.linkUnderline}>
            {MON['mon.pay.terms']}
          </ChalkText>
        </Pressable>
        <ChalkText variant="bodySm" style={styles.linkDot}>
          ·
        </ChalkText>
        <Pressable
          testID="paywall-privacy-link"
          accessibilityRole="link"
          accessibilityHint="Opens in your browser"
          onPress={() => openLegal('/privacy')}
          style={styles.linkHit}
        >
          <ChalkText variant="bodySm" style={styles.linkUnderline}>
            {MON['mon.pay.privacy']}
          </ChalkText>
        </Pressable>
      </View>
    </View>
  );

  return (
    <SafeAreaView style={styles.root} testID="paywall-screen" edges={['top', 'bottom']}>
      <View style={styles.header}>
        {dismissible ? (
          <Pressable
            testID="paywall-close"
            accessibilityRole="button"
            accessibilityLabel={MON['mon.offer.close_a11y']}
            onPress={dismiss}
            style={({ pressed }) => [styles.closeBtn, pressed && styles.pressedWell]}
          >
            <Icon name="x" size={20} color={chalk.dim} />
          </Pressable>
        ) : null}
      </View>

      <ScrollView>
        <View style={styles.scrollPad}>
          {invitee ? (
            <ChalkText variant="label" testID="paywall-invitee-context">
              {invitee}
            </ChalkText>
          ) : null}
          <ChalkText variant="display" testID="paywall-headline">
            {headlineFor(source, kind)}
          </ChalkText>
          {body ? (
            <ChalkText variant="body" style={styles.dim}>
              {body}
            </ChalkText>
          ) : null}
          {invitee ? (
            <ChalkText variant="bodySm" testID="paywall-invitee-board">
              {MON['mon.invitee.board']}
            </ChalkText>
          ) : null}

          <View style={styles.value}>
            <ChalkText variant="body">{MON['mon.pay.value']}</ChalkText>
            {BULLETS.map((key) => (
              <View key={key} style={styles.bulletRow}>
                <Icon name="check" size={16} color={chalk.dim} />
                <ChalkText variant="body" style={styles.bulletText}>
                  {MON[key]}
                </ChalkText>
              </View>
            ))}
          </View>

          <ChalkText variant="bodySm">{MON['mon.lock.free']}</ChalkText>

          {clubOpen ? (
            <View style={styles.club} testID="paywall-club">
              <View style={styles.founderTag}>
                <ChalkText variant="label" style={styles.founderTagText}>
                  {FOUNDER_TAG}
                </ChalkText>
              </View>
              <ChalkText variant="title">{MON['mon.club.join']}</ChalkText>
              {FOUNDER_LINES.map((key) => (
                <ChalkText key={key} variant="bodySm">
                  {MON[key]}
                </ChalkText>
              ))}
            </View>
          ) : null}

          {loading ? (
            <View style={styles.loading}>
              <ActivityIndicator color={chalk.dim} />
            </View>
          ) : null}
          {!loading && plans.length === 0 ? (
            <ChalkText variant="bodySm" style={styles.emptyNote}>
              Plans aren’t available right now. Please try again later.
            </ChalkText>
          ) : null}
        </View>
        {unanchored ? anchoredBlock : null}
      </ScrollView>

      {unanchored ? null : anchoredBlock}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: ink.ink0 },
  header: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    paddingHorizontal: space.sm,
    minHeight: 44,
  },
  closeBtn: {
    width: 44,
    height: 44,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pressedWell: { backgroundColor: ink.ink3 },
  scrollPad: { paddingHorizontal: space.lg, paddingBottom: space.lg, gap: space.md },
  dim: { color: chalk.dim },
  value: { gap: space.sm },
  bulletRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  bulletText: { flex: 1 },
  club: { gap: space.sm, marginTop: space.sm },
  // FounderTag (design-lead): flare label, 1px flare border, r-xs, no fill.
  founderTag: {
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderColor: flare.base,
    borderRadius: radii.xs,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  founderTagText: { color: flare.base },
  loading: { paddingVertical: space.lg, alignItems: 'center' },
  emptyNote: { textAlign: 'center', paddingVertical: space.lg },
  // The anchored block: ink-1, a 1px line top hairline, padded space.md.
  anchored: {
    backgroundColor: ink.ink1,
    borderTopWidth: 1,
    borderTopColor: ink.line,
    padding: space.md,
    gap: space.sm,
  },
  anchoredInline: { marginTop: space.md },
  statusSlot: { gap: space.xs },
  statusText: { color: chalk.base },
  plans: { gap: space.sm },
  planRow: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.md,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
  // Selection is a border change, never a lift or a shadow.
  planRowActive: { borderColor: ice.base },
  planLeft: { flex: 1, gap: 2 },
  summary: { flexDirection: 'row', alignItems: 'baseline', flexWrap: 'wrap', gap: space.sm },
  trialLine: { color: chalk.base },
  disclosure: { color: chalk.dim },
  linkRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'center',
  },
  linkHit: { minHeight: 44, justifyContent: 'center', paddingHorizontal: space.xs },
  linkChalk: { color: chalk.base },
  linkUnderline: { color: chalk.base, textDecorationLine: 'underline' },
  linkDot: { color: chalk.faint },
});
