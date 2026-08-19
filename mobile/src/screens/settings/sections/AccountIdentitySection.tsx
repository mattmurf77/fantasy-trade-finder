// Settings § Account — the IDENTITY half.
//
// Renders (in shipped order): the demo-session row, the linked-identity rows
// (Apple/Google), the "Link Apple" card, the "Linked sign-in — None" fallback
// row, the Sleeper identity row, the account-only LinkSleeperForm card, the
// Verification value row + its settings-v2 explainer footnote, and the
// "Verify account" push row.
//
// Lifted from SettingsScreen.tsx (origin/main) — the `accountSection` block at
// :1255-1412, plus the state/handlers it depends on:
//   • :263-278   accountsEnabled flag, accountQuery (['account']), identities
//   • :368-425   appleAvailable / appleBusy + handleLinkApple
//   • :427-443   verifiedVia / verificationLabel
//   • :1255-1391 the JSX itself, up to and including "Verify account"
//
// NOT here, by design (plan §3/§4):
//   • the three platform disconnect rows (:1391-1393) — a peer module owns
//     them; they move to the Leagues page (F2).
//   • public profile / Download my data / Delete account (:1394-1411) —
//     AccountDataSection.
//
// TickLabel: this module renders `<TickLabel>Account</TickLabel>`. It is the
// FIRST of the three modules that split the shipped `accountSection`, so it
// inherits that section's single banner and the Phase 0 flat list renders
// byte-identically. Plan §3 gives the Phase 2 host page the title
// "Account & data"; when SettingsAccount lands, the banner is expected to move
// to the page header and drop from here.
//
// Intentional behavior changes: NONE. Loading stays as shipped — the Apple
// card and the account-only form render only once `accountQuery.data` has
// resolved (conditional render, no full-screen spinner, no new placeholder).

import React, { useEffect, useState } from 'react';
import { View, Text, Pressable, ActivityIndicator, Platform } from 'react-native';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as AppleAuthentication from 'expo-apple-authentication';

import { chalk, radii } from '../../../theme/chalkline';
import { TickLabel, Card, Icon } from '../../../components/chalkline';
import { appleSignIn, getAccount } from '../../../api/auth';
// P0-5 / S-20 — the Sleeper-identity link form has one owner, shared with
// LeaguePicker's account-only companion state. Settings mounts the FORM (its
// surface is this inline card, not a modal). The 409 two-boards Alert lives in
// that component.
import { LinkSleeperForm } from '../../../components/LinkSleeperSheet';
import { useSession } from '../../../state/useSession';
import { useFlag } from '../../../state/useFeatureFlags';
import { styles } from '../styles';
import type { SettingsSectionProps } from './types';

export interface AccountIdentitySectionProps extends SettingsSectionProps {
  /** Post-link navigation for the account-only Sleeper form. The shipped
   *  handler ran `navigation.replace('LeaguePicker')` (SettingsScreen:1338) —
   *  a stack REPLACE, not a navigate — so the host performs it rather than
   *  losing it to the generic `navigate` prop. Plan §5 flags this as a
   *  code-walk item when Settings stops being a modal. */
  onSleeperLinked: () => void;
}

export default function AccountIdentitySection({
  onNotice,
  navigate,
  onSleeperLinked,
}: AccountIdentitySectionProps) {
  const queryClient = useQueryClient();

  // ── Account (account-auth plan P2) ─────────────────────────────────────
  // Identity display is gated on auth.accounts (GET /api/account 404s while
  // the flag is off); "Verify account" always shows.
  const accountsEnabled = useFlag('auth.accounts');
  // Gates the verification explainer footnote below (S6A-08 / 09-01 §2).
  const settingsV2 = useFlag('account.settings_v2');

  const isDemo = useSession((s) => s.isDemo);
  const user = useSession((s) => s.user);
  const setUser = useSession((s) => s.setUser);
  const setLeague = useSession((s) => s.setLeague);
  const verification = useSession((s) => s.verification);
  const setVerification = useSession((s) => s.setVerification);

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
        onNotice('That Apple ID is already linked to a different account.', 'warn');
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
        onNotice('Apple ID linked — your account is verified.', 'success');
      } else {
        // No live session server-side (restart/expiry) — the backend
        // treated this as a fresh sign-in instead of a link.
        onNotice(
          "Couldn't link — your session expired. Sign out and back in, then retry.",
          'warn',
        );
      }
    } catch (err: unknown) {
      const e = err as { code?: string; message?: string } | null;
      if (e?.code !== 'ERR_REQUEST_CANCELED') {
        onNotice(e?.message || "Couldn't link Apple — try again.", 'warn');
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

  return (
    <>
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
              <LinkSleeperForm
                onNotice={(msg, tone) => onNotice(msg, tone)}
                onLinked={async (res) => {
                  // Session is now keyed to the real Sleeper user — update
                  // the saved user, drop the sentinel league, and send them
                  // to the league picker (which, after P0-5, is a screen
                  // that receives these users properly).
                  await setUser({
                    user_id:      res.sleeper_user_id,
                    username:     res.username,
                    display_name: res.display_name || res.username,
                    avatar_id:    res.avatar ?? null,
                  });
                  await setLeague(null);
                  queryClient.invalidateQueries({ queryKey: ['account'] });
                  onSleeperLinked();
                }}
              />
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
          {settingsV2 ? (
            // One-line explainer (S6A-08 / 09-01 §2): what verification is
            // actually protecting against, stated where users would look.
            <Text style={styles.rowFootnote}>
              {verifiedVia
                ? 'Verified — your board and account actions are locked to you.'
                : 'Until you verify, anyone who knows your username could open a session that sees this board — verifying locks it to you.'}
            </Text>
          ) : null}
          {/* SleeperConnect verification requires a Sleeper-keyed session
              (the JWT claim must match the session user) — hidden for
              account-only users, whose Apple sign-in IS the verification. */}
          {!user?.account_only ? (
            <Pressable
              accessibilityRole="button"
              onPress={() => navigate('SleeperConnect')}
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
        </>
      ) : null}
    </>
  );
}
