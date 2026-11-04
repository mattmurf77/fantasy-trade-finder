import React, { useEffect, useState } from 'react';
import { Linking, Pressable, StyleSheet, View } from 'react-native';
import { useQueryClient } from '@tanstack/react-query';

import ChalkText from './chalkline/Text';
import { Icon, TickLabel } from './chalkline';
import { chalk, flare, ink, radii, space } from '../theme/chalkline';
import type { PaywallConfig } from '../api/billing';
import {
  currentIdentityUserId,
  getActivePro,
  hasProEntitlement,
  isIdentityReady,
  onIdentityChange,
  restorePurchases,
} from '../api/purchases';
import { track } from '../api/events';
import { useEntitlements } from '../state/useEntitlements';
import { useFlag } from '../state/useFeatureFlags';
import { openPaywall, openVerify } from '../state/usePaywallGate';
import { useSession } from '../state/useSession';
import { customerInfoApplies, subscriptionSessionState } from '../state/subscriptionSession';
import {
  FOUNDER_PRICE,
  FOUNDER_TAG,
  MON,
  clubSince,
  keptSettings,
  periodFromStore,
  planPeriod,
  subStatus,
} from '../copy/monetization';

// Settings › Subscription (#393 M3; design-lead §5, §4.2; ux-lead "Settings ›
// Subscription" and addendum §3.2 item 3; copy §9.4, §9.5, §9.11).
//
// SINGLE OWNER (head-eng's ruling, the TimingReadoutRow precedent): this
// component is self-contained and SAFE TO MOUNT ANYWHERE. It reads the flag,
// the session, the entitlements and the paywall config itself; onboarding-eng
// mounts it in SettingsHub and SettingsScreen and changes nothing else.
//
// WHEN IT RENDERS: whenever `monetize.paywall` is on, whether or not the
// server enforces yet. The paywall (and so a purchase) is reachable from
// here as soon as the flag is on, so Restore and Manage must be too;
// `enforcing` gates the LOCK UI only (D7), never this section.
//
// WHAT IT SHOWS, decided by the SESSION first (legal R28.9, D15, D16 a; head-
// eng's 2026-10-28 ruling), through ONE predicate, subscriptionSessionState
// (state/subscriptionSession, shared with RevenueCat's identity rule and the
// paywall; head-eng 2026-10-29):
//   - unknown (verification still null after a cold start, and not a session
//     that proves itself): NOTHING, not even the banner. Never a guess.
//   - unverified, or a DEMO (demo is strict, head-eng 2026-10-29: no
//     RevenueCat, no purchase flow): ONE row, "Verify this session first" (mon.verify.title),
//     opening the VerifySheet. No See plans, no Restore, no status, the same
//     for every unverified session. That branch is a separate component that
//     reads no subscription field, so it can't vary by what the account has.
//   - verified (session_verified === true; or an Apple/Google-first
//     account-only session, proven by its own fields): the rows below.
//     Restore shows only once RevenueCat's identity is this user.
//   - verified member: Manage subscription (Apple's page) and Restore. The
//     STATUS block (the plan line mon.pay.sub_status; for a Founding GM
//     "Founding GM since {date}" with the FounderTag, the kept-price and
//     lapse lines) waits for update 1 (head-eng's B8 ruling): it renders only
//     when STATUS_ROWS_AT_LAUNCH flips, and until then RevenueCat isn't read.
//   - verified non-subscriber: See plans (→ the paywall, source 'settings',
//     the mon.pay.headline variant; it emits paywall_viewed) and Restore.
// NO trial state, NO dates but the join date, NO countdown (D10). A value
// that isn't known for free is left out, never guessed (the hub's rule 2):
// the plan line and the join date come from RevenueCat's CustomerInfo for
// THIS session's user, and render only when it answers.
//
// ZERO BACKEND REQUESTS (the hub's rule 1): the paywall config is read from
// the React Query cache only; the entitlements are already in memory.

/** Apple's own subscription-management page (Manage subscription). */
const APPLE_SUBSCRIPTIONS_URL = 'https://apps.apple.com/account/subscriptions';

/** Opens Apple's subscription page and does nothing else. The one opener for
 *  Manage subscription: this section's row and both delete-account dialogs
 *  (legal R28.21 5c: never a required step). */
export function openAppleSubscriptions(): void {
  void Linking.openURL(APPLE_SUBSCRIPTIONS_URL).catch(() => {});
}

/** B8 (head-eng, 2026-10-27): the 11-06 binary ships Settings › Subscription
 *  WITHOUT the member status block (plan line, "Founding GM since" + the
 *  FounderTag, kept-price, lapse). Update 1 flips this. While false the block
 *  doesn't render and getActivePro (RevenueCat) is never called. */
export const STATUS_ROWS_AT_LAUNCH: boolean = false;

export default function SubscriptionSection() {
  const paywallOn = useFlag('monetize.paywall');
  const state = useSession(subscriptionSessionState);
  // Unknown renders nothing at all, banner included (never a guess).
  if (!paywallOn || state === 'unknown') return null;
  return (
    <View testID="settings-subscription-row">
      <View style={styles.banner}>
        <TickLabel>Subscription</TickLabel>
      </View>
      {state === 'unverified' || state === 'demo' ? <UnverifiedRow /> : <VerifiedRows />}
    </View>
  );
}

/** The one row an unverified session gets (R28.9 3f): no subscription read. */
function UnverifiedRow() {
  return (
    <LinkRow
      testID="settings-subscription-verify"
      title={MON['mon.verify.title']}
      onPress={() => void openVerify()}
    />
  );
}

function VerifiedRows() {
  const userId = useSession((s) => s.user?.user_id ?? null);
  const loaded = useEntitlements((s) => s.loaded);
  const pro = useEntitlements((s) => s.pro);
  const founder = useEntitlements((s) => s.founder);
  const noteCustomerInfo = useEntitlements((s) => s.noteCustomerInfo);
  const refreshEntitlements = useEntitlements((s) => s.refresh);

  // RevenueCat's identity for THIS user: Restore waits for it, and so does
  // the status block's plan read (which, while that block is off for B8, is
  // never asked at all).
  const [idReady, setIdReady] = useState(() => isIdentityReady(userId));
  useEffect(() => {
    setIdReady(isIdentityReady(userId));
    return onIdentityChange(() => setIdReady(isIdentityReady(userId)));
  }, [userId]);
  const [active, setActive] = useState<Awaited<ReturnType<typeof getActivePro>>>(null);
  useEffect(() => {
    if (!STATUS_ROWS_AT_LAUNCH || !pro || !userId || !idReady) {
      setActive(null);
      return;
    }
    let alive = true;
    void getActivePro(userId).then((a) => {
      if (alive) setActive(a);
    });
    return () => {
      alive = false;
    };
  }, [pro, userId, idReady]);

  const [busy, setBusy] = useState(false);
  const [restoreLine, setRestoreLine] = useState<string | null>(null);
  const onRestore = async () => {
    // D9 / R28.9 3f: Restore runs only for a verified session, by the SAME
    // predicate the render uses. (This branch renders only when verified;
    // this covers a session that changed since.)
    const state = subscriptionSessionState(useSession.getState());
    if (state !== 'verified') {
      if (state === 'unverified' || state === 'demo') void openVerify();
      return;
    }
    // RevenueCat's CustomerInfo only for THIS user (head-eng 2026-10-29):
    // a verified session whose RevenueCat identity isn't it yet gets the
    // existing error line, never another account's restore.
    if (!customerInfoApplies(useSession.getState(), currentIdentityUserId())) {
      setRestoreLine(MON['mon.pay.error']);
      return;
    }
    if (busy || !userId) return;
    setBusy(true);
    setRestoreLine(null);
    try {
      const info = await restorePurchases(userId);
      const restored = hasProEntitlement(info);
      track('paywall_restore', { restored });
      // Re-check before noting: the session or user may have changed while
      // the restore was out. Only the note is skipped; the refresh decides.
      const now = useSession.getState();
      if (restored && now.user?.user_id === userId && customerInfoApplies(now, currentIdentityUserId())) {
        noteCustomerInfo(true);
      }
      // Always re-ask the server, as the paywall's Restore does.
      await refreshEntitlements();
      setRestoreLine(restored ? MON['mon.pay.restore_ok'] : MON['mon.pay.restore_none']);
    } catch {
      setRestoreLine(MON['mon.pay.error']);
    } finally {
      setBusy(false);
    }
  };

  // Restore only once RevenueCat's identity is THIS verified user (head-eng,
  // 2026-10-28): before that there is no Restore row.
  const restoreRows = idReady ? (
    <>
      <LinkRow
        testID="settings-subscription-restore"
        title={MON['mon.pay.restore']}
        onPress={() => void onRestore()}
        disabled={busy}
      />
      {restoreLine ? (
        <ChalkText
          variant="bodySm"
          style={styles.restoreLine}
          testID="settings-subscription-restore-status"
          accessibilityLiveRegion="polite"
        >
          {restoreLine}
        </ChalkText>
      ) : null}
    </>
  ) : null;

  // Never guess before an answer: only Restore until the entitlements load.
  if (!loaded) return restoreRows;

  if (!pro) {
    return (
      <>
        <LinkRow
          testID="settings-subscription-see-plans"
          title={MON['mon.pay.see_plans']}
          onPress={() => void openPaywall({ source: 'settings' })}
        />
        {restoreRows}
      </>
    );
  }

  return (
    <>
      {/* B8: the status block waits for update 1. */}
      {STATUS_ROWS_AT_LAUNCH ? <MemberStatus active={active} founder={founder} /> : null}
      <ManageSubscriptionLink />
      {restoreRows}
    </>
  );
}

/** The member status block (update 1; off while STATUS_ROWS_AT_LAUNCH is
 *  false): the plan line, and for a Founding GM the join date with the
 *  FounderTag, the kept-price and lapse lines. */
function MemberStatus({
  active,
  founder,
}: {
  active: Awaited<ReturnType<typeof getActivePro>>;
  founder: boolean;
}) {
  const queryClient = useQueryClient();
  // The member's plan: StoreKit's period for the active product, else the
  // cached config's. A Founding GM's price is the Founder price the legal
  // lines below name; anyone else's is StoreKit's (else the config's).
  const config = queryClient.getQueryData<PaywallConfig>(['paywall-config', 'ios']);
  const product = config?.products?.find((p) => p.product_id === active?.productId);
  const period = periodFromStore(active?.period) ?? (product ? planPeriod(product.period) : null);
  const price = period
    ? founder
      ? FOUNDER_PRICE[period]
      : active?.priceString ?? product?.display_price ?? null
    : null;
  const status = period && price ? subStatus(period, price, founder) : null;
  const since = founder ? clubSince(active?.since) : null;

  return (
    <>
      {status ? (
        <View style={styles.kvRow} testID="settings-subscription-status">
          <ChalkText variant="body" style={styles.flex}>
            {status}
          </ChalkText>
        </View>
      ) : null}
      {founder ? (
        <View style={styles.club}>
          {since ? (
            <View style={styles.kvRow} testID="settings-subscription-since">
              <ChalkText variant="body" style={styles.flex}>
                {`${since.lead} `}
                <ChalkText variant="data">{since.date}</ChalkText>
              </ChalkText>
              <View style={styles.founderTag}>
                <ChalkText variant="label" style={styles.founderTagText}>
                  {FOUNDER_TAG}
                </ChalkText>
              </View>
            </View>
          ) : null}
          {period ? (
            <ChalkText variant="bodySm" style={styles.clubLine}>
              {keptSettings(period)}
            </ChalkText>
          ) : null}
          <ChalkText variant="bodySm" style={styles.clubLine}>
            {MON['mon.club.lapse']}
          </ChalkText>
        </View>
      ) : null}
    </>
  );
}

/** Manage subscription → Apple's own page (Apple shows Apple's dates; this
 *  app shows none). Self-gated on `monetize.paywall`, so it is safe to mount
 *  anywhere: Settings › Subscription, and the Delete account flow (design §5,
 *  "plus a Manage subscription linkRow"). The same for every session. */
export function ManageSubscriptionLink({
  testID = 'settings-subscription-manage',
}: { testID?: string }): React.JSX.Element | null {
  const paywallOn = useFlag('monetize.paywall');
  if (!paywallOn) return null;
  return (
    <LinkRow
      testID={testID}
      title={MON['mon.pay.manage']}
      onPress={openAppleSubscriptions}
      accessibilityRole="link"
    />
  );
}

function LinkRow({
  testID,
  title,
  onPress,
  disabled,
  accessibilityRole = 'button',
}: {
  testID: string;
  title: string;
  onPress: () => void;
  disabled?: boolean;
  accessibilityRole?: 'button' | 'link';
}) {
  return (
    <Pressable
      testID={testID}
      accessibilityRole={accessibilityRole}
      accessibilityLabel={title}
      accessibilityState={{ disabled: !!disabled }}
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [styles.linkRow, pressed && styles.pressed]}
    >
      <ChalkText variant="title" style={styles.flex}>
        {title}
      </ChalkText>
      <Icon name="chevron-right" color={chalk.dim} size={16} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  // The Settings section banner's spacing (screens/settings/styles `section`).
  banner: { marginTop: space.xl, marginBottom: space.sm },
  flex: { flex: 1 },
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: 44,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  pressed: { backgroundColor: ink.ink3 },
  kvRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: 44,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  club: { paddingBottom: space.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: ink.line },
  clubLine: { color: chalk.dim, marginTop: space.sm },
  restoreLine: { color: chalk.base, paddingVertical: space.sm },
  // FounderTag (design-lead): flare label, 1px flare border, r-xs, no fill.
  founderTag: {
    borderWidth: 1,
    borderColor: flare.base,
    borderRadius: radii.xs,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  founderTagText: { color: flare.base },
});
