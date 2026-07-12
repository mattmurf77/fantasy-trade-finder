import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Switch,
  ScrollView,
  ActivityIndicator,
  Platform,
  Pressable,
  TextInput,
  Linking,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as AppleAuthentication from 'expo-apple-authentication';

import { ink, chalk, ice, semantic, space, radii, type } from '../theme/chalkline';
import { TickLabel, Button, Card, Icon } from '../components/chalkline';
import Toast from '../components/Toast';
import { getNotifPrefs, updateNotifPrefs } from '../api/notifications';
import { appleSignIn, deleteAccount, getAccount, linkSleeperUsername } from '../api/auth';
import { ApiError } from '../api/client';
import { setRankingMethod } from '../api/rankings';
import SteerSlider from '../components/SteerSlider';
import { useSession, type RankMethodPref } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import type { NotificationPrefs } from '../shared/types';

// Settings sheet shown as a modal from the gear icon in the global TopBar.
// Currently a single section (notification prefs); designed to grow as more
// preferences land.
//
// Optimistic toggles: each Switch flips local state immediately, fires a
// PUT, and only reverts on server error. We surface a toast for failures
// rather than a full-screen error so the user can keep flipping.
export default function SettingsScreen({ navigation }: any) {
  const queryClient = useQueryClient();
  const signOut = useSession((s) => s.signOut);
  // B3 — Multi-league controls (Switch / Add another league).
  const leagues       = useSession((s) => s.leagues);
  const activeLeague  = useSession((s) => s.league);
  const switchLeague  = useSession((s) => s.switchLeague);
  const connectLeague = useSession((s) => s.connectLeague);
  const switching     = useSession((s) => s.switching);
  const [busyLeagueId, setBusyLeagueId] = useState<string | null>(null);
  const [connectUrl, setConnectUrl] = useState('');
  const [connectBusy, setConnectBusy] = useState(false);
  // Rank-home preference — which ranking flow the Rank tab opens at launch.
  // Local persist is what routes; the backend POST is analytics-only, so a
  // failure there never blocks or reverts the slider.
  const rankingPref    = useSession((s) => s.rankingMethodPref);
  const setRankingPref = useSession((s) => s.setRankingMethodPref);
  const onRankingPrefChange = (m: RankMethodPref) => {
    void setRankingPref(m);
    setRankingMethod(m).catch(() => {});
    setToast({ msg: 'Saved — the Rank tab opens there next launch.', tone: 'success' });
  };
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);
  // ── Account (account-auth plan P2) ─────────────────────────────────────
  // Identity display is gated on auth.accounts (GET /api/account 404s while
  // the flag is off); "Verify account" and "Delete account" always show —
  // in-app deletion is App Store Guideline 5.1.1(v), not a flagged feature.
  const accountsEnabled = useFlag('auth.accounts');
  // #130 — ESPN-link CTA row (flag `espn.link`): routes to the LeaguePicker
  // with the EspnLinkSheet auto-opened (the one place the import flow lives).
  const espnLinkEnabled = useFlag('espn.link');
  const isDemo = useSession((s) => s.isDemo);
  const user = useSession((s) => s.user);
  const setUser = useSession((s) => s.setUser);
  const setLeague = useSession((s) => s.setLeague);
  const verification = useSession((s) => s.verification);
  const setVerification = useSession((s) => s.setVerification);
  const [deleting, setDeleting] = useState(false);
  const accountQuery = useQuery({
    queryKey: ['account'],
    queryFn: getAccount,
    enabled: accountsEnabled && !isDemo,
    staleTime: 60_000,
  });
  const identities = accountQuery.data?.account?.identities ?? [];
  const hasAppleIdentity = identities.some((i) => i.provider === 'apple');

  // ── Link Apple from an existing session (feedback: build 40) ───────────
  // The bind path (POST /api/auth/apple with a live session) shipped in P2
  // but its only button lived on SignInScreen — invisible to anyone already
  // signed in. Surface it here for every session with no Apple identity.
  const [appleAvailable, setAppleAvailable] = useState(false);
  const [appleBusy, setAppleBusy] = useState(false);

  useEffect(() => {
    if (!accountsEnabled || isDemo || Platform.OS !== 'ios') return;
    AppleAuthentication.isAvailableAsync()
      .then(setAppleAvailable)
      .catch(() => setAppleAvailable(false));
  }, [accountsEnabled, isDemo]);

  async function handleLinkApple() {
    if (appleBusy) return;
    setAppleBusy(true);
    try {
      const cred = await AppleAuthentication.signInAsync({
        requestedScopes: [
          AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
          AppleAuthentication.AppleAuthenticationScope.EMAIL,
        ],
      });
      if (!cred.identityToken) throw new Error('Apple did not return an identity token.');
      const res = await appleSignIn(cred.identityToken);
      if (res.conflict) {
        // Sticky binding: this Apple ID's account is already bound to a
        // DIFFERENT Sleeper user; the server refuses to rebind (200 +
        // conflict=true). Honest copy, nothing changed server-side.
        setToast({
          msg: 'That Apple ID is already linked to a different account.',
          tone: 'warn',
        });
      } else if (res.linked) {
        // Bound to this session's user; the server marked the session
        // verified (verified_via='apple'). Mirror it into the store so the
        // verify banner / status row react without a re-launch.
        setVerification({
          session_verified: true,
          user_verified: true,
          verified_via: res.verified_via || 'apple',
          enforced: verification?.enforced ?? false,
        });
        queryClient.invalidateQueries({ queryKey: ['account'] });
        setToast({ msg: 'Apple ID linked — your account is verified.', tone: 'success' });
      } else {
        // No live session server-side (restart/expiry) — the backend
        // treated this as a fresh sign-in instead of a link.
        setToast({
          msg: "Couldn't link — your session expired. Sign out and back in, then retry.",
          tone: 'warn',
        });
      }
    } catch (err: any) {
      if (err?.code !== 'ERR_REQUEST_CANCELED') {
        setToast({ msg: err?.message || "Couldn't link Apple — try again.", tone: 'warn' });
      }
    } finally {
      setAppleBusy(false);
    }
  }

  // Verification status label — user-level state. GET /api/account reports
  // the session's verified_via (falling back to the users-row marker); when
  // the flag is off the query never runs, so fall back to the P1 store state
  // (session_init reports it regardless of auth.accounts).
  const verifiedVia =
    accountQuery.data?.verified_via ??
    (verification?.session_verified || verification?.user_verified
      ? verification?.verified_via
      : null);
  const verificationLabel =
    verifiedVia === 'apple' ? 'Verified via Apple'
    : verifiedVia === 'google' ? 'Verified via Google'
    : verifiedVia === 'sleeper' ? 'Verified via Sleeper'
    : verifiedVia ? 'Verified'
    : 'Not verified';

  // ── Link Sleeper username (account-first P2.6) ─────────────────────────
  // Shown for account-only users (Apple/Google account, no Sleeper source).
  // Merge rules live server-side; a 409 merge_choice_required means both
  // the account board AND the Sleeper username's board have data — the
  // user must pick a side explicitly (no silent data loss).
  const [linkUsername, setLinkUsername] = useState('');
  const [linkBusy, setLinkBusy] = useState(false);

  async function handleLinkSleeper(strategy?: 'keep_sleeper' | 'keep_account') {
    const uname = linkUsername.trim();
    if (!uname || linkBusy) return;
    setLinkBusy(true);
    try {
      const res = await linkSleeperUsername(uname, strategy);
      // Session is now keyed to the real Sleeper user — update the saved
      // user, drop the sentinel league, and send them to the league picker.
      await setUser({
        user_id:      res.sleeper_user_id,
        username:     res.username,
        display_name: res.display_name || res.username,
        avatar_id:    res.avatar ?? null,
      });
      await setLeague(null);
      queryClient.invalidateQueries({ queryKey: ['account'] });
      navigation.replace?.('LeaguePicker');
    } catch (e: any) {
      const body = e instanceof ApiError ? (e.body as any) : null;
      if (body?.error === 'merge_choice_required') {
        const acctSwipes = body.account_board?.swipes ?? 0;
        const slpSwipes = body.sleeper_board?.swipes ?? 0;
        Alert.alert(
          'Two boards found',
          `Your account has rankings here (${acctSwipes} comparisons) and ` +
            `@${uname} already has rankings too (${slpSwipes} comparisons). ` +
            'Which board do you want to keep? The other is deleted.',
          [
            { text: 'Cancel', style: 'cancel' },
            {
              text: 'Keep this board',
              onPress: () => void handleLinkSleeper('keep_account'),
            },
            {
              text: `Keep @${uname}'s board`,
              onPress: () => void handleLinkSleeper('keep_sleeper'),
            },
          ],
        );
      } else if (body?.error === 'sleeper_already_claimed') {
        setToast({
          msg: 'That Sleeper account is already verified by another sign-in.',
          tone: 'warn',
        });
      } else {
        setToast({ msg: e?.message || "Couldn't link that username.", tone: 'warn' });
      }
    } finally {
      setLinkBusy(false);
    }
  }

  async function performDeleteAccount() {
    if (deleting) return;
    setDeleting(true);
    try {
      await deleteAccount();
      await signOut();
      navigation.replace?.('SignIn');
    } catch (e: any) {
      setToast({ msg: e?.message || "Couldn't delete your account — try again.", tone: 'warn' });
    } finally {
      setDeleting(false);
    }
  }

  function confirmDeleteAccount() {
    Alert.alert(
      'Delete account?',
      'This permanently deletes your rankings, comparison history, trade activity, ' +
        'notifications, push tokens, and any stored Sleeper connection from our ' +
        'servers. Trade matches shared with leaguemates are anonymized on your side. ' +
        'This cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Continue',
          style: 'destructive',
          onPress: () =>
            Alert.alert(
              'Are you absolutely sure?',
              'Your account and all of its data will be deleted immediately. ' +
                'There is no way to recover them.',
              [
                { text: 'Keep my account', style: 'cancel' },
                {
                  text: 'Delete everything',
                  style: 'destructive',
                  onPress: () => void performDeleteAccount(),
                },
              ],
            ),
        },
      ],
    );
  }
  // Local mirror of server prefs so toggles feel instant. Hydrated from the
  // query below; updates push through `mutation` and the query is invalidated
  // on success.
  const [local, setLocal] = useState<NotificationPrefs | null>(null);

  const prefsQuery = useQuery({
    queryKey: ['notif-prefs'],
    queryFn: getNotifPrefs,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (prefsQuery.data) setLocal(prefsQuery.data);
  }, [prefsQuery.data]);

  const mutation = useMutation({
    mutationFn: (patch: Partial<NotificationPrefs>) => updateNotifPrefs(patch),
    onError: () => {
      // Roll back local state to last-known-good server value.
      if (prefsQuery.data) setLocal(prefsQuery.data);
      setToast({ msg: "Couldn't save — try again.", tone: 'warn' });
    },
    onSuccess: (next) => {
      setLocal(next);
      queryClient.setQueryData(['notif-prefs'], next);
    },
  });

  const flip = (key: keyof NotificationPrefs) => {
    if (!local) return;
    const nextVal = local[key] ? 0 : 1;
    setLocal({ ...local, [key]: nextVal as 0 | 1 });
    mutation.mutate({ [key]: nextVal as 0 | 1 } as Partial<NotificationPrefs>);
  };

  // ── B3 multi-league handlers ───────────────────────────────────
  async function handleSwitch(lgId: string, lgName: string) {
    if (busyLeagueId) return;
    if (lgId === activeLeague?.league_id) return;
    setBusyLeagueId(lgId);
    try {
      await switchLeague({ league_id: lgId, league_name: lgName });
      setToast({ msg: `Switched to ${lgName}`, tone: 'success' });
    } catch (e: any) {
      setToast({ msg: e?.message || 'Failed to switch', tone: 'warn' });
    } finally {
      setBusyLeagueId(null);
    }
  }

  async function handleConnect() {
    const url = connectUrl.trim();
    if (!url || connectBusy) return;
    if (user?.account_only) {
      // Account-first (P2.6): no Sleeper user to attach leagues to yet.
      setToast({
        msg: 'Link your Sleeper username under Account first.',
        tone: 'warn',
      });
      return;
    }
    setConnectBusy(true);
    try {
      const result = await connectLeague(url);
      if (!result.ok) {
        // Backend recognized a non-Sleeper URL — surface as a soft warn.
        const label =
          result.platform === 'espn' ? 'ESPN' :
          result.platform === 'mfl'  ? 'MyFantasyLeague' :
          'That platform';
        setToast({
          msg: `${label} sync isn't supported yet — Sleeper URLs only.`,
          tone: 'warn',
        });
        return;
      }
      setConnectUrl('');
      // Refresh portfolio so the newly-connected league lights it up
      // immediately if the user navigates there next.
      queryClient.invalidateQueries({ queryKey: ['portfolio'] });
      setToast({ msg: `Connected ${result.league_name}`, tone: 'success' });
    } catch (e: any) {
      setToast({ msg: e?.message || 'Could not connect that league', tone: 'warn' });
    } finally {
      setConnectBusy(false);
    }
  }

  if (prefsQuery.isLoading || !local) {
    return (
      <SafeAreaView style={styles.root} edges={['bottom']}>
        <View style={styles.loading}>
          <ActivityIndicator color={ice.base} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.root} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        {/* B3 — Multi-league: switch + add. The Switch section is hidden
            when the user only has one league so single-league users see
            just the "Connect another league" card. */}
        {leagues.length > 1 ? (
          <>
            <View style={styles.section}>
              <TickLabel>Switch league</TickLabel>
            </View>
            {leagues.map((lg) => {
              const isActive = lg.league_id === activeLeague?.league_id;
              const isBusy   = busyLeagueId === lg.league_id || (switching && isActive);
              const dim      = (busyLeagueId !== null && !isBusy) || (switching && !isActive);
              return (
                <Pressable
                  key={lg.league_id}
                  onPress={() => handleSwitch(lg.league_id, lg.name)}
                  disabled={busyLeagueId !== null || switching || isActive}
                  style={({ pressed }) => [
                    styles.leagueRow,
                    dim && styles.rowDim,
                    pressed && !dim && !isActive && styles.rowPressed,
                  ]}
                >
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={styles.leagueName} numberOfLines={1}>{lg.name}</Text>
                    <Text style={styles.leagueMeta}>
                      <Text style={styles.leagueMetaCount}>
                        {(lg.total_rosters as number | undefined) || 12}
                      </Text>
                      {' teams'}
                    </Text>
                  </View>
                  {isBusy ? (
                    <ActivityIndicator color={chalk.dim} />
                  ) : isActive ? (
                    <Icon name="check" color={ice.base} />
                  ) : null}
                </Pressable>
              );
            })}
          </>
        ) : null}

        <View style={styles.section}>
          <TickLabel>
            {leagues.length > 1 ? 'Add another league' : 'Connect another league'}
          </TickLabel>
        </View>
        <Card>
          <View style={styles.connectBody}>
            <Text style={styles.connectHelp}>
              Paste a Sleeper league URL (or bare league ID) to sync it.
            </Text>
            <TextInput
              value={connectUrl}
              onChangeText={setConnectUrl}
              placeholder="sleeper.com/leagues/..."
              placeholderTextColor={chalk.faint}
              autoCapitalize="none"
              autoCorrect={false}
              editable={!connectBusy}
              style={styles.connectInput}
            />
            <Button
              label="Connect"
              onPress={handleConnect}
              disabled={!connectUrl.trim() || connectBusy}
            />
          </View>
        </Card>
        {/* #130 — flag-gated ESPN link entry. Reuses the LeaguePicker's
            EspnLinkSheet flow (espnLink param auto-opens it) rather than
            re-hosting the sheet here. */}
        {espnLinkEnabled ? (
          <Pressable
            testID="settings.link-espn"
            onPress={() => navigation.navigate?.('LeaguePicker', { espnLink: true })}
            style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
          >
            <View style={{ flex: 1 }}>
              <Text style={styles.rowKey}>Link an ESPN league</Text>
              <Text style={styles.rowSub}>
                Read-only import: rankings, tiers, and trios work today.
              </Text>
            </View>
            <Icon name="chevron-right" color={chalk.dim} size={16} />
          </Pressable>
        ) : null}

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

        <View style={styles.section}>
          <TickLabel>Notifications</TickLabel>
        </View>

        <Row
          title="Trade matches"
          sub="New matches, counter-offers, league activity"
          value={!!local.trade_matches}
          onChange={() => flip('trade_matches')}
        />
        <Row
          title="Weekly digest"
          sub="Tuesday/Wednesday morning roundup"
          value={!!local.weekly_digest}
          onChange={() => flip('weekly_digest')}
        />
        <Row
          title="Stay in the game"
          sub="Occasional nudges if you've been away"
          value={!!local.reengagement}
          onChange={() => flip('reengagement')}
        />

        <View style={styles.section}>
          <TickLabel>Quiet hours</TickLabel>
        </View>
        <Row
          title="Pause overnight (10pm – 8am)"
          sub="Notifications will bundle into one summary at 8am local"
          value={!!local.quiet_hours_enabled}
          onChange={() => flip('quiet_hours_enabled')}
        />
        <View style={styles.kvRow}>
          <Text style={styles.rowKey}>Time zone</Text>
          <Text style={styles.kvValue}>{local.tz}</Text>
        </View>

        <View style={styles.section}>
          <TickLabel>Testing</TickLabel>
        </View>
        <Pressable
          onPress={() => navigation.navigate?.('FeedbackInbox')}
          style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
        >
          <View style={{ flex: 1 }}>
            <Text style={styles.rowKey}>Test feedback</Text>
            <Text style={styles.rowSub}>
              Review and share notes you captured with the floating button.
            </Text>
          </View>
          <Icon name="chevron-right" color={chalk.dim} size={16} />
        </Pressable>

        <View style={styles.section}>
          <TickLabel>Account</TickLabel>
        </View>
        {isDemo ? (
          <View style={styles.kvRow}>
            <Text style={styles.rowKey}>Demo session</Text>
            <Text style={styles.kvValue}>Sign in to save your data</Text>
          </View>
        ) : null}
        {accountsEnabled && !isDemo ? (
          <>
            {identities.map((ident) => (
              <View key={ident.provider} style={styles.kvRow}>
                <Text style={styles.rowKey}>
                  {ident.provider === 'apple' ? 'Signed in with Apple' : 'Signed in with Google'}
                </Text>
                <Text style={styles.kvValue}>
                  {ident.linked_at ? new Date(ident.linked_at).toLocaleDateString() : 'Linked'}
                </Text>
              </View>
            ))}
            {/* Link Apple — shown for any session with no Apple identity
                (Sleeper sessions included). Official HIG component, white
                variant on dark, same construction as SignInScreen. Gated on
                the resolved account query so it never flashes for users who
                already have an Apple identity. */}
            {accountQuery.data && !hasAppleIdentity && appleAvailable ? (
              <Card>
                <View style={styles.connectBody}>
                  <Text style={styles.connectHelp}>
                    Link Apple to verify your account and restore it if you
                    ever lose this device.
                  </Text>
                  <AppleAuthentication.AppleAuthenticationButton
                    testID="settings.link-apple-btn"
                    buttonType={AppleAuthentication.AppleAuthenticationButtonType.SIGN_IN}
                    buttonStyle={AppleAuthentication.AppleAuthenticationButtonStyle.WHITE}
                    cornerRadius={radii.sm}
                    style={styles.appleButton}
                    onPress={() => void handleLinkApple()}
                  />
                  {appleBusy ? <ActivityIndicator color={chalk.dim} /> : null}
                </View>
              </Card>
            ) : null}
            {accountQuery.data && !identities.length && !appleAvailable ? (
              <View style={styles.kvRow}>
                <Text style={styles.rowKey}>Linked sign-in</Text>
                <Text style={styles.kvValue}>None</Text>
              </View>
            ) : null}
            {/* Linked league sources (P2.6). Sleeper today; linked ESPN
                leagues will list here alongside it. A Sleeper-keyed session
                shows its own identity even before any account exists — the
                section must never read as empty for signed-in users. */}
            {!user?.account_only || accountQuery.data?.account?.sleeper_user_id ? (
              <View style={styles.kvRow}>
                <Text style={styles.rowKey}>Sleeper</Text>
                <Text style={styles.kvValue}>
                  {accountQuery.data?.sleeper_username
                    ? `@${accountQuery.data.sleeper_username}`
                    : user?.username
                      ? `@${user.username}`
                      : 'Linked'}
                </Text>
              </View>
            ) : null}
            {accountQuery.data?.account_only ? (
              <Card>
                <View style={styles.connectBody}>
                  <Text style={styles.connectHelp}>
                    Link your Sleeper username to load your leagues. Your
                    rankings come with you.
                  </Text>
                  <TextInput
                    testID="settings.link-sleeper-input"
                    value={linkUsername}
                    onChangeText={setLinkUsername}
                    placeholder="Sleeper username"
                    placeholderTextColor={chalk.faint}
                    autoCapitalize="none"
                    autoCorrect={false}
                    editable={!linkBusy}
                    style={styles.connectInput}
                  />
                  <Button
                    label={linkBusy ? 'Linking…' : 'Link Sleeper username'}
                    onPress={() => void handleLinkSleeper()}
                    disabled={!linkUsername.trim() || linkBusy}
                  />
                </View>
              </Card>
            ) : null}
          </>
        ) : null}
        {!isDemo ? (
          <>
            {/* Verification status (P1) — always rendered so the section
                reads meaningfully for every session type. */}
            <View style={styles.kvRow}>
              <Text style={styles.rowKey}>Verification</Text>
              <Text style={styles.kvValue}>{verificationLabel}</Text>
            </View>
            {/* SleeperConnect verification requires a Sleeper-keyed session
                (the JWT claim must match the session user) — hidden for
                account-only users, whose Apple sign-in IS the verification. */}
            {!user?.account_only ? (
              <Pressable
                onPress={() => navigation.navigate?.('SleeperConnect')}
                style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowKey}>Verify account</Text>
                  <Text style={styles.rowSub}>
                    Prove you own this Sleeper account to protect your ranks.
                  </Text>
                </View>
                <Icon name="chevron-right" color={chalk.dim} size={16} />
              </Pressable>
            ) : null}
            <Pressable
              onPress={confirmDeleteAccount}
              disabled={deleting}
              style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
            >
              <View style={{ flex: 1 }}>
                <Text style={[styles.rowKey, styles.destructiveKey]}>Delete account</Text>
                <Text style={styles.rowSub}>
                  Permanently delete your account and all of its data.
                </Text>
              </View>
              {deleting ? (
                <ActivityIndicator color={semantic.neg} />
              ) : (
                <Icon name="chevron-right" color={chalk.dim} size={16} />
              )}
            </Pressable>
          </>
        ) : null}

        <View style={styles.section}>
          <TickLabel>About</TickLabel>
        </View>
        <Pressable
          onPress={() => Linking.openURL('https://fantasy-trade-finder.onrender.com/privacy')}
          style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
        >
          <Text style={[styles.rowKey, { flex: 1 }]}>Privacy Policy</Text>
          <Icon name="chevron-right" color={chalk.dim} size={16} />
        </Pressable>
        <Pressable
          onPress={() => Linking.openURL('https://fantasy-trade-finder.onrender.com/terms')}
          style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
        >
          <Text style={[styles.rowKey, { flex: 1 }]}>Terms of Use</Text>
          <Icon name="chevron-right" color={chalk.dim} size={16} />
        </Pressable>

        <View style={{ height: space.xxl }} />
        <Pressable
          onPress={async () => {
            await signOut();
            navigation.replace?.('SignIn');
          }}
          style={({ pressed }) => [styles.signOut, pressed && styles.rowPressed]}
        >
          <Text style={styles.signOutText}>Sign out</Text>
        </Pressable>
      </ScrollView>
      <Toast
        visible={!!toast}
        message={toast?.msg ?? ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />
    </SafeAreaView>
  );
}

function Row({
  title, sub, value, onChange,
}: { title: string; sub?: string; value: boolean; onChange: () => void }) {
  return (
    <View style={styles.row}>
      <View style={{ flex: 1, paddingRight: space.md }}>
        <Text style={styles.rowKey}>{title}</Text>
        {sub ? <Text style={styles.rowSub}>{sub}</Text> : null}
      </View>
      <Switch
        value={value}
        onValueChange={onChange}
        trackColor={{ false: ink.ink3, true: ice.base }}
        thumbColor={chalk.base}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: ink.ink0 },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  body: { padding: space.lg },
  section: {
    marginTop: space.xl,
    marginBottom: space.sm,
  },
  // Hairline key-value / toggle rows — surface stays ink-0, depth via lines.
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 44,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  rowKey: type.label,
  rowSub: {
    ...type.bodySm,
    marginTop: space.xs,
  },
  kvRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 44,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  kvValue: type.body,
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: 44,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  rowPressed: { backgroundColor: ink.ink3 },
  rowDim: { opacity: 0.45 },
  signOut: {
    minHeight: 44,
    paddingVertical: space.md,
    justifyContent: 'center',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: ink.line,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  signOutText: {
    ...type.body,
    color: semantic.neg,
  },
  destructiveKey: {
    ...type.label,
    color: semantic.neg,
  },
  // B3 — Switch league rows + Connect another league card
  leagueRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: 44,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  leagueName: type.title,
  leagueMeta: {
    ...type.bodySm,
    marginTop: space.xs,
  },
  leagueMetaCount: {
    ...type.data,
    color: chalk.dim,
  },
  connectBody: { gap: space.md },
  connectHelp: type.bodySm,
  // Official Sign in with Apple button (Settings → Account link card).
  appleButton: {
    alignSelf: 'stretch',
    height: 44,
  },
  rankingHint: { ...type.bodySm, color: chalk.faint, marginTop: space.sm },
  connectInput: {
    ...type.body,
    height: 44,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
  },
});
