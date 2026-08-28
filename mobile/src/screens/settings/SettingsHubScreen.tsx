// Settings hub — the top level of the Settings IA (plan §3, mockup §2).
//
// A pushed page: an identity block, then grouped nav rows with STATE
// PREVIEWS, and nothing below the last row. Sign out is NOT here — the
// operator moved it to the Account page on 2026-08-18, which is what keeps
// this screen purely navigational and one screenful tall.
//
// ── The rule that governs this file (plan §6) ────────────────────────────
// 1. ZERO NETWORK. The hub fires no queries of its own. Every preview comes
//    from the session store (zustand, already in memory), from the React
//    Query cache read NON-REACTIVELY via getQueryData (never useQuery — a
//    useQuery here would fetch), from the feature-flag store, or from
//    expo-constants. Opening Settings goes from six queries plus two
//    fetches to none, which is the fix for finding F4.
// 2. NEVER GUESS. A value we do not know for free is not rendered. Where
//    there is a meaningful "not set yet" state we say so, faint and italic
//    (hubStyles.navPreviewNone); otherwise the subtitle line is omitted
//    entirely. A settings page that lies about a setting is worse than one
//    that says nothing.
//
// Consequence worth stating: the Trade values row has no subtitle. Stud tax —
// the only control left on that page since D-144 removed pick pricing — is
// read by TradeValuesSection through a plain fetch in a useEffect
// (getStudTaxMode), not through React Query, so there is no cache for the hub
// to peek at and no way to know it for free. Per rule 2 the line is omitted
// rather than defaulted — showing
// "Stud tax: Market" because 'market' happens to be the code default is
// exactly the lie rule 2 forbids.
//
// All row/chip styling comes from `hubStyles` in ../settings/styles.ts —
// there is no second style source for this screen.

import React from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQueryClient } from '@tanstack/react-query';
import Constants from 'expo-constants';

import { chalk } from '../../theme/chalkline';
import { Icon, TickLabel } from '../../components/chalkline';
import { NO_LEAGUE_ID, useSession, type RankMethodPref } from '../../state/useSession';
import { useFlag } from '../../state/useFeatureFlags';
import { useEntitlements } from '../../state/useEntitlements';
import type { AccountInfo } from '../../api/auth';
import type { NotificationPrefs } from '../../shared/types';
import FeedbackFAB from '../../components/FeedbackFAB';
import { hubStyles, styles } from './styles';

// The ranking preview names the flow the SteerSlider names. Values are the
// `title` strings of SteerSlider's STOPS (components/SteerSlider.tsx) — one
// vocabulary for the setting, whether you are reading it or changing it.
const RANK_PREF_LABEL: Record<RankMethodPref, string> = {
  quickset: 'Tap players into tiers',
  trio:     'Answer quick head-to-heads',
  anchor:   'Price players in picks',
  tiers:    'Sort players into groups',
  manual:   'Order every player yourself',
};

/** Marketing version + iOS build number, whichever the running build's
 *  manifest carries. Mirrors `appVersionLabel()` in
 *  sections/AboutSection.tsx exactly — one version-formatting rule, so the
 *  hub preview can never disagree with the About page's Version row. */
function appVersionLabel(): string | null {
  const version = Constants.expoConfig?.version ?? null;
  const build = Constants.expoConfig?.ios?.buildNumber ?? null;
  if (version && build) return `${version} (${build})`;
  return version ?? build ?? null;
}

export default function SettingsHubScreen({ navigation }: any) {
  // Non-reactive cache reads. getQueryData returns what is already resident
  // and never triggers a fetch or a subscription; `undefined` means "this
  // page has not been opened yet this launch", which rule 2 turns into an
  // omitted subtitle rather than a placeholder.
  const queryClient = useQueryClient();
  const notifPrefs = queryClient.getQueryData<NotificationPrefs>(['notif-prefs']);
  const account = queryClient.getQueryData<AccountInfo>(['account']);

  // Session store — free, already in memory.
  const user = useSession((s) => s.user);
  const isDemo = useSession((s) => s.isDemo);
  const leagues = useSession((s) => s.leagues);
  const activeLeague = useSession((s) => s.league);
  const rankingPref = useSession((s) => s.rankingMethodPref);
  const verification = useSession((s) => s.verification);

  // Flag store — free. `testing.stage_users` gates the Testing row exactly
  // as SettingsScreen.tsx:1546 does; `ux.help_surface` decides whether the
  // About page actually has an FAQ link to advertise.
  const stageUsersEnabled = useFlag('testing.stage_users');
  const helpSurfaceOn = useFlag('ux.help_surface');
  // Monetization (iap-enablement, flag `monetize.paywall`, dark). The flag
  // gates this ROW, not the Paywall route — same rule as Testing above.
  const paywallOn = useFlag('monetize.paywall');
  // Entitlements come from the zustand store, already in memory: no query, so
  // rule 1 (zero network) survives. `loaded` is what keeps rule 2: before any
  // source has answered we say NOTHING rather than printing "Free", which
  // would be a guess that happens to be wrong for every paying user.
  const proLoaded = useEntitlements((s) => s.loaded);
  const isPro = useEntitlements((s) => s.pro);

  const go = (route: string) => () => navigation?.navigate?.(route);

  // ── Identity ───────────────────────────────────────────────────────────
  // Handle precedence matches sections/AccountIdentitySection.tsx: the
  // account's bound Sleeper username first, then the session user's.
  const handle =
    account?.sleeper_username ? `@${account.sleeper_username}`
    : user?.username ? `@${user.username}`
    : 'Your account';

  // How they are signed in. Only stated when something we hold actually
  // says so: a linked identity from the ['account'] cache, or a verified_via
  // the session store already reported.
  const verifiedVia = verification?.verified_via;
  const provider: 'apple' | 'google' | null =
    account?.account?.identities?.[0]?.provider
    ?? (verifiedVia === 'apple' || verifiedVia === 'google' ? verifiedVia : null);

  const signInLabel =
    isDemo ? 'Demo session'
    : provider === 'apple' ? 'Apple'
    : provider === 'google' ? 'Google'
    // A non-account_only session is keyed to a real Sleeper user by
    // construction (useSession.SavedUser) — that is a fact, not a guess.
    : user && !user.account_only ? 'Sleeper'
    : null;

  const identityMeta =
    isDemo ? 'Demo session — sign in to save your data'
    : signInLabel ? `Signed in with ${signInLabel}`
    : null;

  // Verification is only claimed when some source has reported it. Both are
  // absent on a cold launch before the first session_init lands, and a chip
  // reading "Not verified" in that window would be an invention.
  const verificationKnown = verification !== null || account !== undefined;
  const isVerified =
    !!account?.verified_via
    || !!verification?.session_verified
    || !!verification?.user_verified;

  // ── Leagues preview ────────────────────────────────────────────────────
  // "<active league> + N more", or just the name when there is one league.
  // The account-only sentinel league is not a league the user has.
  const realLeagues = leagues.filter((l) => l.league_id !== NO_LEAGUE_ID);
  const activeName =
    activeLeague && activeLeague.league_id !== NO_LEAGUE_ID
      ? activeLeague.league_name
      : null;
  const otherCount = realLeagues.filter(
    (l) => l.league_id !== activeLeague?.league_id,
  ).length;

  let leaguesPreview: string | null = null;
  let leaguesPreviewEmpty = false;
  if (activeName) {
    leaguesPreview = otherCount > 0 ? `${activeName} + ${otherCount} more` : activeName;
  } else if (realLeagues.length === 1) {
    leaguesPreview = realLeagues[0].name;
  } else if (realLeagues.length > 1) {
    leaguesPreview = `${realLeagues.length} leagues`;
  } else {
    // A real, knowable state — the account-only user with nothing linked.
    leaguesPreview = 'No league connected';
    leaguesPreviewEmpty = true;
  }

  // ── Ranking preview ────────────────────────────────────────────────────
  // Null pref = never chosen; the Rank tab still opens on the chooser. That
  // is the shipped empty state, so it is named rather than omitted.
  const rankingPreview = rankingPref ? RANK_PREF_LABEL[rankingPref] : 'Not chosen yet';
  const rankingPreviewEmpty = !rankingPref;

  // ── Notifications preview ──────────────────────────────────────────────
  // Four switches live on the Notifications page (three delivery toggles +
  // pause overnight). The 10pm–8am window is fixed copy on that page, not a
  // stored value, so naming it is a statement of fact.
  let notifPreview: string | null = null;
  if (notifPrefs) {
    // Quiet hours is deliberately NOT in the numerator: it suppresses
    // notifications, so folding it in would let "3 of 4 on" mean the user
    // turned MORE things off. It is named separately below instead.
    const on = [
      notifPrefs.trade_matches,
      notifPrefs.weekly_digest,
      notifPrefs.reengagement,
    ].filter(Boolean).length;
    notifPreview = `${on} of 3 on`;
    if (notifPrefs.quiet_hours_enabled) notifPreview += ' · Quiet hours 10p–8a';
  }

  // ── Account preview ────────────────────────────────────────────────────
  // 'Sign out' is named here on purpose. The operator's 2026-08-18 decision
  // moved it off the hub onto this page, which costs discoverability — users
  // reach for it at the bottom of Settings by habit. Naming it in the preview
  // buys that back for free: it is a true statement about what is behind this
  // row, not a guess, so it satisfies the never-guess rule in plan §6.
  const accountPreview =
    [
      signInLabel,
      verificationKnown ? (isVerified ? 'Verified' : 'Not verified') : null,
      'Sign out',
    ]
      .filter(Boolean)
      .join(' · ') || null;

  // ── About preview ──────────────────────────────────────────────────────
  const versionLabel = appVersionLabel();
  const aboutLinks = helpSurfaceOn ? 'FAQ, privacy, terms' : 'Privacy, terms';
  const aboutPreview = versionLabel ? `${aboutLinks} · v${versionLabel}` : aboutLinks;

  return (
    <SafeAreaView style={styles.root} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.body}>
        {/* Identity — not a nav row: who you are, whether you are verified,
            and a tap through to Account & data. */}
        <Pressable
          testID="settings.hub.identity"
          accessibilityRole="button"
          accessibilityLabel={`${handle}${identityMeta ? `. ${identityMeta}` : ''}`}
          onPress={go('SettingsAccount')}
          style={({ pressed }) => [hubStyles.identityRow, pressed && styles.rowPressed]}
        >
          <View style={{ flex: 1 }}>
            <Text style={hubStyles.identityName}>{handle}</Text>
            {identityMeta ? (
              <Text style={hubStyles.identityMeta}>{identityMeta}</Text>
            ) : null}
          </View>
          {verificationKnown ? (
            <View style={[hubStyles.verifyChip, isVerified && hubStyles.verifyChipOk]}>
              <Text
                style={[
                  hubStyles.verifyChipText,
                  isVerified && hubStyles.verifyChipTextOk,
                ]}
              >
                {isVerified ? 'Verified' : 'Not verified'}
              </Text>
            </View>
          ) : null}
          <Icon name="chevron-right" color={chalk.dim} size={16} />
        </Pressable>

        <View style={styles.section}>
          <TickLabel>Leagues</TickLabel>
        </View>
        <NavRow
          testID="settings.hub.leagues"
          title="Leagues"
          preview={leaguesPreview}
          previewEmpty={leaguesPreviewEmpty}
          onPress={go('SettingsLeagues')}
        />

        <View style={styles.section}>
          <TickLabel>How the app works</TickLabel>
        </View>
        <NavRow
          testID="settings.hub.ranking"
          title="Ranking"
          preview={rankingPreview}
          previewEmpty={rankingPreviewEmpty}
          onPress={go('SettingsRanking')}
        />
        {/* No subtitle by design — see the header note. */}
        <NavRow
          testID="settings.hub.trade-values"
          title="Trade values"
          preview={null}
          onPress={go('SettingsTradeValues')}
        />

        <View style={styles.section}>
          <TickLabel>Alerts</TickLabel>
        </View>
        <NavRow
          testID="settings.hub.notifications"
          title="Notifications"
          preview={notifPreview}
          onPress={go('SettingsNotifications')}
        />

        {/* Monetization entry point (iap-enablement). The ONLY route to the
            paywall in this build — gate-driven sources land here in a later
            wave. Hidden entirely while `monetize.paywall` is false, which is
            everywhere today. */}
        {paywallOn ? (
          <>
            <View style={styles.section}>
              <TickLabel>Subscription</TickLabel>
            </View>
            <NavRow
              testID="settings-pro-row"
              title="Fleeced Pro"
              preview={proLoaded ? (isPro ? 'Pro' : 'Free') : null}
              onPress={() => navigation?.navigate?.('Paywall', { source: 'settings' })}
            />
            <NavRow
              testID="settings-tip-row"
              title="Support Fleeced"
              preview="Tip jar"
              onPress={() => navigation?.navigate?.('TipJar', { source: 'settings' })}
            />
          </>
        ) : null}

        <View style={styles.section}>
          <TickLabel>Account</TickLabel>
        </View>
        <NavRow
          testID="settings.hub.account"
          title="Account & data"
          preview={accountPreview}
          onPress={go('SettingsAccount')}
        />

        <View style={styles.section}>
          <TickLabel>About</TickLabel>
        </View>
        <NavRow
          testID="settings.hub.about"
          title="Help & about"
          preview={aboutPreview}
          onPress={go('SettingsAbout')}
        />

        {/* Dev builds and allowlisted testers only — the same gate the
            shipped flat list uses (SettingsScreen.tsx:1546). No banner: it
            is not a group, it is a build-conditional escape hatch. */}
        {__DEV__ || stageUsersEnabled ? (
          <NavRow
            testID="settings.hub.testing"
            title="Testing"
            preview={null}
            onPress={go('SettingsTesting')}
          />
        ) : null}
        {/* Nothing below this row. Sign out lives on Account & data. */}
      </ScrollView>
      {/* #188 — pushed pages are NOT exempt from the feedback surface; only
          modals/sheets and onboarding are. The FAB's own status refresh is an
          app-wide concern, not a settings query, so the hub still fires no
          settings requests of its own (plan §6). */}
      <FeedbackFAB activeScreen="Settings" aboveTabBar={false} />
    </SafeAreaView>
  );
}

// Hub nav row: 16px sentence-case title over an optional 13px state preview,
// chevron right. Spec row owed to docs/design/components.md § Navigation
// (plan §7) — the rules themselves live in hubStyles.
function NavRow({
  title, preview, previewEmpty, testID, onPress,
}: {
  title: string;
  /** Null = we do not know this for free, so nothing is shown. */
  preview: string | null;
  /** True = an honest "not set yet", rendered faint + italic. */
  previewEmpty?: boolean;
  testID: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={preview ? `${title}. ${preview}` : title}
      onPress={onPress}
      style={({ pressed }) => [hubStyles.navRow, pressed && styles.rowPressed]}
    >
      <View style={{ flex: 1 }}>
        <Text style={hubStyles.navTitle}>{title}</Text>
        {preview ? (
          <Text
            numberOfLines={1}
            style={previewEmpty ? hubStyles.navPreviewNone : hubStyles.navPreview}
          >
            {preview}
          </Text>
        ) : null}
      </View>
      <Icon name="chevron-right" color={chalk.dim} size={16} />
    </Pressable>
  );
}
