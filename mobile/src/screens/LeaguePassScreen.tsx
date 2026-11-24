import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import ChalkText from '../components/chalkline/Text';
import { Button, Icon } from '../components/chalkline';
import { ManageSubscriptionLink } from '../components/SubscriptionSection';
import Row from './settings/Row';
import { chalk, ink, radii, space } from '../theme/chalkline';
import { getBaseUrl } from '../api/client';
import {
  bindLeaguePass,
  createLeaguePassIntent,
  getLeaguePass,
  getPaywallConfig,
  repointLeaguePass,
  setLeaguePassShowBuyer,
  type LeaguePassIntent,
  type LeaguePassView,
} from '../api/billing';
import {
  checkIntroPriceEligible,
  currentIdentityUserId,
  getLeagueOffering,
  getPromoOffer,
  hasProEntitlement,
  isPaymentPending,
  isUserCancelled,
  purchaseDiscountedPackage,
  purchasePackage,
  PurchaseIdentityError,
  purchasesReady,
  whenIdentityReady,
  type PurchasesPackage,
  type PurchasesPromotionalOffer,
} from '../api/purchases';
import { track } from '../api/events';
import { useEntitlements } from '../state/useEntitlements';
import { useFlag } from '../state/useFeatureFlags';
import { useSession } from '../state/useSession';
import {
  customerInfoApplies,
  purchasesIdentityTarget,
  subscriptionSessionState,
} from '../state/subscriptionSession';
import { openVerify } from '../state/usePaywallGate';
import { openWebLink } from '../utils/openExternal';
import { MON } from '../copy/monetization';
import {
  buyerPass,
  fill,
  leagueNameFor,
  passDate,
  purchaseCallFor,
  purchasePlan,
  refusalCopyKey,
  refusalReason,
  type PurchasePlan,
} from '../utils/leaguePass';

// LEAGUE PASS — buy, attach and manage the pass (flag `monetize.league_pass`,
// DARK; docs/plans/monetization/league-pass/lld.md §8, prd R12–R21, R27–R28;
// D-281). A root-stack MODAL like Paywall (#188: modals carry no FeedbackFAB),
// registered unconditionally; it SELF-GUARDS on `monetize.league_pass` AND
// `monetize.paywall`, on a verified session (unverified and demo go to the
// VerifySheet), and on the server: a config without the `league_pass` block
// (server flag off) dismisses.
//
// WHAT IT SHOWS, from `GET /api/league-pass`:
//   - a pass (`pass` set)      → MANAGE: league, renewal date or "won't renew",
//                                covered count, Move (with the cooldown date),
//                                Show my name (R27, R28), Apple's page.
//   - `unbound`                → CHOOSE A LEAGUE for a purchase with no league
//                                on record (R19) → `POST /bind`.
//   - neither                  → BUY: choose a league (the session's leagues,
//                                the ones with a team of the user's) → `POST
//                                /intent` → the ONE version the league
//                                qualifies for, year-one and renewal prices
//                                together, and the team count (R12, R15) →
//                                Apple's sheet → refresh the entitlements until
//                                the buyer's pass shows, else the choose-a-
//                                league state.
//
// NEVER ONE PRICE SHOWN AND ANOTHER CHARGED. The prices on screen come from
// utils/leaguePass.purchasePlan, which is resolved BEFORE the button shows:
//   tier 0 → the list price (purchasePackage);
//   tier 1/2, intro-eligible → the introductory price (purchasePackage; Apple
//     applies the intro);
//   tier 1/2, otherwise → the SIGNED promotional offer, priced from the
//     offer itself (purchaseDiscountedPackage with that exact offer);
//   no offer could be signed → the FULL price, said plainly, with Continue at
//     full price or Cancel. A 'promo' path without its offer never falls back
//     to a plain purchase.
// Every price is StoreKit's (or, with no StoreKit, the server config's display
// strings, when nothing can be bought). No price is written in this file.
//
// Analytics: the existing paywall_purchase_initiated / _completed / _failed,
// with the league product ids and the `source` that opened this screen (the
// paywall's, or 'settings'). No new event names.

type Step =
  | { kind: 'idle' }
  | { kind: 'quote'; leagueId: string; intent: LeaguePassIntent; plan: PurchasePlan;
      pkg: PurchasesPackage | null; promo: PurchasesPromotionalOffer | null }
  | { kind: 'confirming'; leagueId: string }
  | { kind: 'done'; leagueId: string | null }
  | { kind: 'pending' };

/** Polls of `/api/me/entitlements` after a purchase while the webhook lands. */
const BIND_POLLS = 6;
const BIND_POLL_MS = 2500;

/** PaywallScreen's identity rule, the same wait: a verified session whose
 *  RevenueCat logIn is still landing waits for it; anything else is refused. */
async function customerInfoAppliesNow(): Promise<boolean> {
  const target = purchasesIdentityTarget(useSession.getState());
  if (target && purchasesReady() && currentIdentityUserId() !== target) {
    try {
      await whenIdentityReady(target);
    } catch {
      /* timed out: refused below */
    }
  }
  return customerInfoApplies(useSession.getState(), currentIdentityUserId());
}

/** The line for a rejected league-pass call: its own copy per 409 reason,
 *  the cooldown with its date, else the generic line. */
export function refusalLine(err: unknown): string {
  const reason = refusalReason(err);
  const key = refusalCopyKey(reason);
  if (reason === 'cooldown') {
    const at = (err as { body?: { can_repoint_at?: string } }).body?.can_repoint_at;
    const date = passDate(at);
    return date ? fill(MON[key], { date }) : MON['mon.lp.refused.generic'];
  }
  return MON[key];
}

export default function LeaguePassScreen({ navigation, route }: any) {
  const source: string = route?.params?.source ?? 'unknown';
  const lpOn = useFlag('monetize.league_pass');
  const paywallOn = useFlag('monetize.paywall');
  const on = lpOn && paywallOn;
  const session = useSession(subscriptionSessionState);
  const verified = on && session === 'verified';
  const userId = useSession((s) => s.user?.user_id ?? null);
  const leagues = useSession((s) => s.leagues);
  const refreshEntitlements = useEntitlements((s) => s.refresh);
  const noteCustomerInfo = useEntitlements((s) => s.noteCustomerInfo);
  const queryClient = useQueryClient();

  const [step, setStep] = useState<Step>({ kind: 'idle' });
  const [busy, setBusy] = useState(false);
  const [line, setLine] = useState<string | null>(null);
  const [moving, setMoving] = useState(false);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const dismiss = useCallback(() => {
    if (navigation?.canGoBack?.()) navigation.goBack();
    else navigation?.navigate?.('Main');
  }, [navigation]);

  // Self-guards: flags off → leave; unverified or demo → leave, then the
  // VerifySheet (nothing subscription-specific renders first, R28.9).
  useEffect(() => {
    if (!on) dismiss();
  }, [on, dismiss]);
  const leftForVerify = useRef(false);
  useEffect(() => {
    if (!on || leftForVerify.current) return;
    if (session === 'unverified' || session === 'demo') {
      leftForVerify.current = true;
      dismiss();
      setTimeout(() => void openVerify(), 450);
    }
  }, [on, session, dismiss]);

  // Its own key (not the paywall's shared ['paywall-config','ios'] entry):
  // getPaywallConfig sends caps=league_pass while the flag is on.
  const configQuery = useQuery({
    queryKey: ['league-pass-config'],
    queryFn: () => getPaywallConfig('ios'),
    enabled: verified,
    staleTime: 5 * 60_000,
  });
  const viewKey = ['league-pass', userId];
  const viewQuery = useQuery({
    queryKey: viewKey,
    queryFn: () => getLeaguePass(),
    enabled: verified,
    staleTime: 0,
  });
  const lp = configQuery.data?.league_pass ?? null;
  const view: LeaguePassView | undefined = viewQuery.data;

  // The server's answer beats a stale client flag: no league_pass block (or
  // the paywall off) means nothing to sell here.
  useEffect(() => {
    if (configQuery.data && (configQuery.data.enabled === false || !configQuery.data.league_pass)) dismiss();
  }, [configQuery.data, dismiss]);

  const nameOf = (id: string | null | undefined) => leagueNameFor(leagues, id) ?? MON['mon.lp.unknown_league'];
  const setView = (v: LeaguePassView) => queryClient.setQueryData(viewKey, v);

  // ── Buy: choose a league → intent → the plan, resolved before any button.
  const choose = async (leagueId: string) => {
    if (busy || !lp || !userId) return;
    setBusy(true);
    setLine(null);
    try {
      const intent = await createLeaguePassIntent(leagueId);
      const product = lp.products.find((p) => p.product_id === intent.product_id) ?? null;
      const offering = await getLeagueOffering(lp.offering);
      const pkg = offering?.availablePackages.find((x) => x.product?.identifier === intent.product_id) ?? null;
      const sp = pkg?.product ?? null;
      let introEligible = false;
      let promo: { offer: PurchasesPromotionalOffer; priceString: string } | null = null;
      if (sp && intent.tier > 0) {
        introEligible = await checkIntroPriceEligible(sp);
        if (!introEligible) {
          // The signature binds the offer to RevenueCat's user: wait for it.
          await customerInfoAppliesNow();
          promo = await getPromoOffer(sp, product?.promo_offer_id, userId);
        }
      }
      const plan = purchasePlan({
        tier: intent.tier,
        storeAvailable: !!sp,
        introEligible,
        standardPrice: sp?.priceString ?? null,
        introPrice: sp?.introPrice?.priceString ?? null,
        promoPrice: promo?.priceString ?? null,
        configYearOne: product?.display_price ?? null,
        configRenewal: lp.renews_at_price ?? null,
      });
      if (alive.current) setStep({ kind: 'quote', leagueId, intent, plan, pkg, promo: promo?.offer ?? null });
    } catch (err) {
      if (alive.current) setLine(refusalLine(err));
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  // After Apple's sheet: the webhook binds from the intent (R18). Ask until
  // the buyer's pass shows; else the server's view decides (unbound → choose
  // a league, R19; nothing yet → "can take a few minutes").
  const settle = async () => {
    for (let i = 0; i < BIND_POLLS && alive.current; i++) {
      await refreshEntitlements();
      const mine = buyerPass(useEntitlements.getState().leaguePasses, Date.now());
      if (mine) {
        if (alive.current) setStep({ kind: 'done', leagueId: mine.league_id });
        void viewQuery.refetch();
        return;
      }
      await new Promise((r) => setTimeout(r, BIND_POLL_MS));
    }
    if (!alive.current) return;
    try {
      const v = await getLeaguePass();
      setView(v);
      if (!alive.current) return;
      if (v.pass) setStep({ kind: 'done', leagueId: v.pass.league_id });
      else if (v.unbound) setStep({ kind: 'idle' });
      else setStep({ kind: 'pending' });
    } catch {
      if (alive.current) setStep({ kind: 'pending' });
    }
  };

  const buy = async () => {
    if (step.kind !== 'quote' || busy || !userId) return;
    const { plan, pkg, promo, intent, leagueId } = step;
    const productId = intent.product_id;
    setLine(null);
    track('paywall_purchase_initiated', { product_id: productId, source });
    if (!plan.canBuy || !pkg) {
      setLine(MON['mon.lp.unavailable']);
      track('paywall_purchase_failed', { product_id: productId, user_cancelled: false });
      return;
    }
    setBusy(true);
    try {
      if (!(await customerInfoAppliesNow())) throw new PurchaseIdentityError();
      let result;
      if (purchaseCallFor(plan.path) === 'discounted') {
        // The promotional price is on screen only with its signed offer in
        // hand; without it this throws rather than charge the list price.
        if (!promo) throw new Error('promo_offer_missing');
        result = await purchaseDiscountedPackage(pkg, promo, userId);
      } else {
        result = await purchasePackage(pkg, userId);
      }
      if (!result) {
        setLine(MON['mon.lp.unavailable']);
        track('paywall_purchase_failed', { product_id: productId, user_cancelled: false });
        return;
      }
      track('paywall_purchase_completed', { product_id: productId, source });
      const s = useSession.getState();
      if (s.user?.user_id === userId && customerInfoApplies(s, currentIdentityUserId())) {
        noteCustomerInfo(hasProEntitlement(result.customerInfo));
      }
      setStep({ kind: 'confirming', leagueId });
      await settle();
    } catch (err) {
      const cancelled = isUserCancelled(err);
      track('paywall_purchase_failed', { product_id: productId, user_cancelled: cancelled });
      if (isPaymentPending(err)) setLine(MON['mon.pay.pending']);
      else if (!cancelled) setLine(MON['mon.pay.error']);
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  // ── Unbound: attach the purchase to a league (R19).
  const bind = async (leagueId: string) => {
    if (busy) return;
    setBusy(true);
    setLine(null);
    try {
      const v = await bindLeaguePass(leagueId);
      setView(v);
      await refreshEntitlements();
      if (alive.current) setStep({ kind: 'done', leagueId: v.pass?.league_id ?? leagueId });
    } catch (err) {
      if (alive.current) setLine(refusalLine(err));
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  // ── Manage: move (R21) and the name toggle (R28).
  const move = (leagueId: string) => {
    if (busy) return;
    const name = nameOf(leagueId);
    Alert.alert(fill(MON['mon.lp.move.title'], { league_name: name }), fill(MON['mon.lp.move.body'], { league_name: name }), [
      { text: MON['mon.lp.cancel'], style: 'cancel' },
      {
        text: MON['mon.lp.move.confirm'],
        onPress: () => {
          void (async () => {
            setBusy(true);
            setLine(null);
            try {
              setView(await repointLeaguePass(leagueId));
              if (alive.current) setMoving(false);
              await refreshEntitlements();
            } catch (err) {
              if (alive.current) setLine(refusalLine(err));
            } finally {
              if (alive.current) setBusy(false);
            }
          })();
        },
      },
    ]);
  };
  const toggleName = async (show: boolean) => {
    if (busy) return;
    setBusy(true);
    setLine(null);
    try {
      setView(await setLeaguePassShowBuyer(show));
    } catch (err) {
      if (alive.current) setLine(refusalLine(err));
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  if (!verified) return null;

  const loading = configQuery.isLoading || viewQuery.isLoading;
  const lineSlot = line ? (
    <ChalkText variant="bodySm" style={styles.line} testID="league-pass.line" accessibilityLiveRegion="polite">
      {line}
    </ChalkText>
  ) : null;

  const leagueRows = (onPick: (id: string) => void, exclude?: string | null) => {
    const rows = leagues.filter((l) => l.league_id !== exclude);
    if (rows.length === 0) {
      return (
        <ChalkText variant="bodySm" style={styles.dim} testID="league-pass.no-leagues">
          {MON['mon.lp.pick.empty']}
        </ChalkText>
      );
    }
    return rows.map((l) => (
      <Pressable
        key={l.league_id}
        testID={`league-pass.league.${l.league_id}`}
        accessibilityRole="button"
        accessibilityLabel={l.name}
        accessibilityState={{ disabled: busy }}
        disabled={busy}
        onPress={() => onPick(l.league_id)}
        style={({ pressed }) => [styles.row, pressed && styles.pressed]}
      >
        <ChalkText variant="title" style={styles.flex}>{l.name}</ChalkText>
        <Icon name="chevron-right" color={chalk.dim} size={16} />
      </Pressable>
    ));
  };

  const legalLinks = (
    <View style={styles.linkRow}>
      <Pressable
        testID="league-pass.terms"
        accessibilityRole="link"
        accessibilityHint="Opens in your browser"
        onPress={() => void openWebLink(`${getBaseUrl()}/terms`)}
        style={styles.linkHit}
      >
        <ChalkText variant="bodySm" style={styles.linkUnderline}>{MON['mon.pay.terms']}</ChalkText>
      </Pressable>
      <ChalkText variant="bodySm" style={styles.dim}>·</ChalkText>
      <Pressable
        testID="league-pass.privacy"
        accessibilityRole="link"
        accessibilityHint="Opens in your browser"
        onPress={() => void openWebLink(`${getBaseUrl()}/privacy`)}
        style={styles.linkHit}
      >
        <ChalkText variant="bodySm" style={styles.linkUnderline}>{MON['mon.pay.privacy']}</ChalkText>
      </Pressable>
    </View>
  );

  let body: React.ReactNode;
  if (loading) {
    body = (
      <View style={styles.loading}>
        <ActivityIndicator color={chalk.dim} />
      </View>
    );
  } else if (step.kind === 'confirming') {
    body = (
      <View style={styles.center} testID="league-pass.confirming">
        <ActivityIndicator color={chalk.dim} />
        <ChalkText variant="body">{MON['mon.lp.confirming']}</ChalkText>
      </View>
    );
  } else if (step.kind === 'done' || step.kind === 'pending') {
    const text = step.kind === 'pending'
      ? MON['mon.lp.pending']
      : step.leagueId ? fill(MON['mon.lp.done'], { league_name: nameOf(step.leagueId) }) : MON['mon.lp.done.unnamed'];
    body = (
      <View style={styles.section} testID={`league-pass.${step.kind}`}>
        <ChalkText variant="body">{text}</ChalkText>
        <Button testID="league-pass.done-close" label={MON['mon.lp.done.close']} onPress={dismiss} />
      </View>
    );
  } else if (view?.pass) {
    const p = view.pass;
    const renewDate = passDate(p.covered_until) ?? '';
    const moveAt = passDate(p.can_repoint_at);
    body = (
      <View style={styles.section} testID="league-pass.manage">
        <ChalkText variant="heading">{fill(MON['mon.lp.buyer.line'], { league_name: nameOf(p.league_id) })}</ChalkText>
        <ChalkText variant="body" testID="league-pass.manage.renewal">
          {p.will_renew ? fill(MON['mon.lp.buyer.renews'], { date: renewDate }) : fill(MON['mon.lp.buyer.through'], { date: renewDate })}
        </ChalkText>
        <ChalkText variant="body" style={styles.dim} testID="league-pass.manage.count">
          {p.covered_count === 1 ? MON['mon.lp.buyer.count_one'] : fill(MON['mon.lp.buyer.count'], { count: p.covered_count })}
        </ChalkText>
        {lineSlot}
        {moveAt ? (
          <ChalkText variant="bodySm" style={styles.dim} testID="league-pass.move-after">
            {fill(MON['mon.lp.move.after'], { date: moveAt })}
          </ChalkText>
        ) : moving ? (
          <View testID="league-pass.move-list">{leagueRows(move, p.league_id)}</View>
        ) : (
          <Button
            testID="league-pass.move"
            label={MON['mon.lp.move']}
            variant="secondary"
            onPress={() => setMoving(true)}
            disabled={busy}
          />
        )}
        <Row
          testID="league-pass.show-name"
          title={MON['mon.lp.show_name']}
          sub={MON['mon.lp.show_name.hint']}
          value={p.show_buyer}
          onChange={() => void toggleName(!p.show_buyer)}
        />
        <ManageSubscriptionLink testID="league-pass.manage-subscription" />
      </View>
    );
  } else if (view?.unbound) {
    body = (
      <View style={styles.section} testID="league-pass.unbound">
        <ChalkText variant="heading">{MON['mon.lp.unbound.title']}</ChalkText>
        <ChalkText variant="body" style={styles.dim}>{MON['mon.lp.unbound.body']}</ChalkText>
        {lineSlot}
        {leagueRows((id) => void bind(id))}
      </View>
    );
  } else if (step.kind === 'quote') {
    const { plan, intent, leagueId } = step;
    const leagueName = nameOf(leagueId);
    const same = !plan.yearOne || plan.yearOne === plan.renewal;
    const priceLine = same
      ? fill(MON['mon.lp.quote.price_same'], { price: plan.renewal ?? '' })
      : fill(MON['mon.lp.quote.price'], { year_one: plan.yearOne ?? '', renewal: plan.renewal ?? '' });
    const disclosure = same
      ? fill(MON['mon.lp.disclosure_same'], { league_name: leagueName, price: plan.renewal ?? '' })
      : fill(MON['mon.lp.disclosure'], { league_name: leagueName, year_one: plan.yearOne ?? '', renewal: plan.renewal ?? '' });
    body = (
      <View style={styles.section} testID="league-pass.quote">
        <ChalkText variant="heading">{leagueName}</ChalkText>
        {intent.teams ? (
          <ChalkText variant="body" style={styles.dim} testID="league-pass.quote.teams">
            {fill(MON['mon.lp.quote.teams'], { teams: intent.teams })}
          </ChalkText>
        ) : null}
        {/* R12 / R15: one version, year one and renewal side by side. */}
        <ChalkText variant="dataLg" testID="league-pass.quote.price">{priceLine}</ChalkText>
        {plan.fullPriceNotice ? (
          <View style={styles.notice} testID="league-pass.full-price">
            <ChalkText variant="title">{MON['mon.lp.full_price.title']}</ChalkText>
            <ChalkText variant="bodySm">{fill(MON['mon.lp.full_price.body'], { price: plan.renewal ?? '' })}</ChalkText>
          </View>
        ) : null}
        <ChalkText variant="bodySm" style={styles.dim} testID="league-pass.disclosure">{disclosure}</ChalkText>
        {lineSlot}
        <Button
          testID="league-pass.buy"
          label={plan.fullPriceNotice ? MON['mon.lp.full_price.continue'] : MON['mon.lp.buy']}
          onPress={() => void buy()}
          loading={busy}
          disabled={busy}
        />
        {plan.fullPriceNotice ? (
          <Button
            testID="league-pass.full-price-cancel"
            label={MON['mon.lp.cancel']}
            variant="ghost"
            onPress={() => { setLine(null); setStep({ kind: 'idle' }); }}
            disabled={busy}
          />
        ) : (
          <Button
            testID="league-pass.change-league"
            label={MON['mon.lp.change_league']}
            variant="ghost"
            onPress={() => { setLine(null); setStep({ kind: 'idle' }); }}
            disabled={busy}
          />
        )}
        {legalLinks}
      </View>
    );
  } else {
    body = (
      <View style={styles.section} testID="league-pass.pick">
        <ChalkText variant="heading">{MON['mon.lp.pick.title']}</ChalkText>
        <ChalkText variant="body" style={styles.dim}>{MON['mon.lp.pick.body']}</ChalkText>
        {lineSlot}
        {busy ? <ActivityIndicator color={chalk.dim} /> : null}
        {leagueRows((id) => void choose(id))}
        {legalLinks}
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.root} testID="league-pass-screen" edges={['top', 'bottom']}>
      <View style={styles.header}>
        <ChalkText variant="title" style={styles.flex}>{MON['mon.lp.title']}</ChalkText>
        <Pressable
          testID="league-pass.close"
          accessibilityRole="button"
          accessibilityLabel={MON['mon.lp.close_a11y']}
          onPress={dismiss}
          style={({ pressed }) => [styles.closeBtn, pressed && styles.pressed]}
        >
          <Icon name="x" size={20} color={chalk.dim} />
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={styles.scrollPad}>{body}</ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: ink.ink0 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingLeft: space.lg,
    paddingRight: space.sm,
    minHeight: 44,
  },
  closeBtn: { width: 44, height: 44, borderRadius: radii.sm, alignItems: 'center', justifyContent: 'center' },
  pressed: { backgroundColor: ink.ink3 },
  flex: { flex: 1 },
  dim: { color: chalk.dim },
  scrollPad: { paddingHorizontal: space.lg, paddingBottom: space.xl },
  section: { gap: space.md, paddingTop: space.md },
  center: { gap: space.md, alignItems: 'center', paddingVertical: space.xl },
  loading: { paddingVertical: space.xl, alignItems: 'center' },
  line: { color: chalk.base },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: 44,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  notice: {
    gap: space.xs,
    padding: space.md,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    backgroundColor: ink.ink1,
  },
  linkRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'center' },
  linkHit: { minHeight: 44, justifyContent: 'center', paddingHorizontal: space.xs },
  linkUnderline: { color: chalk.base, textDecorationLine: 'underline' },
});
