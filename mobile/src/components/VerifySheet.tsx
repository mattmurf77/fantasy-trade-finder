import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, ActivityIndicator, Modal, Pressable, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as AppleAuthentication from 'expo-apple-authentication';

import ChalkText from './chalkline/Text';
import { Button } from './chalkline';
import { chalk, ink, radii, scrim, shadowSheet, space } from '../theme/chalkline';
import { useReducedMotionSafe } from '../hooks/useReducedMotionSafe';
import { appleSignIn } from '../api/auth';
import { NO_LEAGUE_ID, useSession } from '../state/useSession';
import {
  getGateNavigator,
  settleVerify,
  usePaywallGate,
  verifyPathFor,
} from '../state/usePaywallGate';
import {
  MON,
  VERIFY_CANCEL,
  verifyCopy,
  verifyOutcomeLine,
  type VerifyOutcome,
  type VerifyPath,
} from '../copy/monetization';

// The VerifySheet (#393 M1; D15, D17, D18 FINAL, D20; design-lead §3,
// ux-lead addendum §3). Mounted ONCE, container-level in RootNav, so it
// covers root-stack pushes as well as the tabs. Opened only through
// state/usePaywallGate.openVerify: by a user-initiated 402 `verify_required`
// or 403 `verification_required` on a gated route, or by a paywall entry
// from a session the server reported unverified.
//
// What it shows depends on the SESSION, never on the account (legal R28.9):
//   - a Sleeper session: "Verify this session first" + Verify with Sleeper,
//     which goes to the existing SleeperConnect capture and comes back here;
//   - any other unverified session: "A new sign-in is needed" + Apple's own
//     Sign in with Apple button as a NEW sign-in. That variant never says
//     "verify". Its body says nothing carries over from this session, which
//     is true only while Apple sign-in migrates no entry-session data; if
//     that ever changes, the copy (copy/monetization.ts) must change first.
// There is no MFL path (D18 FINAL) and nothing subscription-specific: no
// price, plan, trial, Restore or club line, and no entitlement read.
//
// After verifying (D18): the sheet closes with `verified` and client.ts
// re-sends the original call once, so the server decides: the free page, a
// 402 → the paywall, or entitled → the call just succeeds. A send-like call
// is never re-sent; its caller is back at its confirm step and needs a fresh
// tap. A new Apple sign-in re-sends nothing: it lands on the league picker.

type Phase = 'prompt' | 'away' | 'apple' | 'done' | 'switched' | 'closing';

const APPLE_ERROR = 'Apple sign-in failed. Try again.';

export default function VerifySheet() {
  const open = usePaywallGate((s) => s.verifyOpen);
  const seq = usePaywallGate((s) => s.verifySeq);
  const mismatchSeq = usePaywallGate((s) => s.mismatchSeq);
  const reduceMotion = useReducedMotionSafe();

  const [phase, setPhase] = useState<Phase>('prompt');
  const [path, setPath] = useState<VerifyPath>('sleeper');
  const [outcome, setOutcome] = useState<VerifyOutcome | null>(null);
  const [appleError, setAppleError] = useState(false);
  const [appleAvailable, setAppleAvailable] = useState(false);
  const afterHide = useRef<(() => void) | null>(null);
  const trip = useRef({ verified: false, mismatch: false, sawConnect: false });

  // Each open: the path is fixed by the session at that moment.
  useEffect(() => {
    if (!open) return;
    const { user, isDemo } = useSession.getState();
    setPath(verifyPathFor(user, isDemo));
    setPhase('prompt');
    setOutcome(null);
    setAppleError(false);
  }, [open, seq]);

  useEffect(() => {
    AppleAuthentication.isAvailableAsync()
      .then(setAppleAvailable)
      .catch(() => setAppleAvailable(false));
  }, []);

  // Hide the sheet, THEN act: a native-stack modal (SleeperConnect, the
  // Paywall a retried call may open) can't present while this RN Modal is
  // still dismissing. iOS reports the dismissal via onDismiss; the timer
  // covers a dismissal that never reports.
  const runAfterHide = useCallback(() => {
    const fn = afterHide.current;
    afterHide.current = null;
    fn?.();
  }, []);
  const hideThen = useCallback(
    (next: Phase, fn: () => void) => {
      afterHide.current = fn;
      setPhase(next);
      setTimeout(runAfterHide, 500);
    },
    [runAfterHide],
  );

  const cancel = useCallback(() => {
    hideThen('closing', () => settleVerify('dismissed'));
  }, [hideThen]);

  // ── Sleeper: the existing SleeperConnect capture, then back here ─────────
  const verifyWithSleeper = useCallback(() => {
    trip.current = { verified: false, mismatch: false, sawConnect: false };
    setOutcome(null);
    hideThen('away', () => {
      const nav = getGateNavigator();
      if (nav?.isReady()) nav.navigate('SleeperConnect');
      else setPhase('prompt');
    });
  }, [hideThen]);

  useEffect(() => {
    if (phase !== 'away') return;
    // SleeperConnectScreen writes `session_verified: true` ONLY after the
    // server's link response says `verified === true`. A fresh verified
    // write during the trip is that answer; nothing else counts.
    const unsubSession = useSession.subscribe((s, prev) => {
      if (s.verification !== prev.verification && s.verification?.session_verified === true) {
        trip.current.verified = true;
      }
    });
    const nav = getGateNavigator();
    const unsubNav = nav && nav.addListener('state', () => {
      const name = nav.getCurrentRoute()?.name;
      if (name === 'SleeperConnect') {
        trip.current.sawConnect = true;
        return;
      }
      if (!trip.current.sawConnect) return;
      if (trip.current.verified) {
        setOutcome('verified');
        setPhase('done');
      } else {
        // Closed without verifying, or a different Sleeper user (403
        // token_user_mismatch: nothing changed server-side).
        setOutcome(trip.current.mismatch ? 'mismatch' : null);
        setPhase('prompt');
      }
    });
    return () => {
      unsubSession();
      if (unsubNav) unsubNav();
    };
  }, [phase]);

  useEffect(() => {
    if (phase === 'away' && mismatchSeq > 0) trip.current.mismatch = true;
    // Only a NEW mismatch matters; `phase` is read at that moment.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mismatchSeq]);

  // "Session verified." for a beat, then close with `verified`.
  useEffect(() => {
    if (phase !== 'done') return;
    AccessibilityInfo.announceForAccessibility(MON['mon.verify.done']);
    const t = setTimeout(() => hideThen('closing', () => settleVerify('verified')), 1200);
    return () => clearTimeout(t);
  }, [phase, hideThen]);

  // ── Every other session: a NEW sign-in with Apple ────────────────────────
  // The same post-auth steps as SignInScreen's Apple path (api/auth
  // appleSignIn, then setUser / setLeague), landing on the league picker.
  const finishSignedIn = useCallback(() => {
    hideThen('closing', () => {
      settleVerify('signed_in');
      getGateNavigator()?.reset({ index: 0, routes: [{ name: 'LeaguePicker' }] });
    });
  }, [hideThen]);

  const signInWithApple = useCallback(async () => {
    if (phase === 'apple') return;
    setPhase('apple');
    setAppleError(false);
    try {
      const cred = await AppleAuthentication.signInAsync({
        requestedScopes: [
          AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
          AppleAuthentication.AppleAuthenticationScope.EMAIL,
        ],
      });
      if (!cred.identityToken) throw new Error('no_identity_token');
      const name = [cred.fullName?.givenName, cred.fullName?.familyName].filter(Boolean).join(' ');
      const res = await appleSignIn(cred.identityToken, name || undefined);
      const session = useSession.getState();
      let switched: boolean;
      if (res.linked && res.sleeper_user_id && res.session_token) {
        // An existing account, already bound to a Sleeper user: the sign-in
        // SWITCHES this device to it (legal R28.15 row 10).
        await session.setUser({
          user_id: res.sleeper_user_id,
          username: res.username || '',
          display_name: res.display_name || res.username || 'Manager',
          avatar_id: res.avatar ?? null,
        });
        await session.setLeague(null);
        switched = true;
      } else if (res.account_only && res.user_id && res.session_token) {
        await session.setUser({
          user_id: res.user_id,
          username: '',
          display_name: res.display_name || 'Manager',
          avatar_id: null,
          account_only: true,
        });
        await session.setLeague({
          league_id: res.league_id || NO_LEAGUE_ID,
          league_name: res.league_name || 'No league linked',
        });
        // The Apple route doesn't say whether this account is new. Say
        // "you're now signed in to that one" only when the server does
        // (`account_created: false`); otherwise claim nothing.
        switched = (res as { account_created?: boolean }).account_created === false;
      } else {
        throw new Error('no_usable_session');
      }
      // The server verified the new session at mint.
      useSession.setState({ isDemo: false });
      session.setVerification({
        session_verified: true,
        user_verified: true,
        verified_via: res.verified_via || 'apple',
        enforced: session.verification?.enforced ?? false,
      });
      if (switched) {
        setOutcome('switched');
        setPhase('switched');
        AccessibilityInfo.announceForAccessibility(MON['mon.verify.switched']);
      } else {
        finishSignedIn();
      }
    } catch (err: any) {
      // Backing out of Apple's own dialog is a decision, not an error.
      if (err?.code !== 'ERR_REQUEST_CANCELED') setAppleError(true);
      setPhase('prompt');
    }
  }, [phase, finishSignedIn]);

  const copy = verifyCopy(path);
  const line = outcome ? verifyOutcomeLine(path, outcome) : null;
  const visible = open && phase !== 'away' && phase !== 'closing';
  const busy = phase === 'apple' || phase === 'done';

  return (
    <Modal
      visible={visible}
      transparent
      animationType={reduceMotion ? 'fade' : 'slide'}
      onRequestClose={() => {
        if (!busy && phase !== 'switched') cancel();
      }}
      onDismiss={runAfterHide}
    >
      <Pressable
        style={styles.backdrop}
        onPress={() => {
          if (!busy && phase !== 'switched') cancel();
        }}
        accessible={false}
        importantForAccessibility="no"
      />
      <View style={styles.sheet} testID="verify-sheet" accessibilityViewIsModal>
        <SafeAreaView edges={['bottom']}>
          <View style={styles.grabber} />
          <ChalkText variant="heading" testID="verify-sheet.title">
            {copy.title}
          </ChalkText>
          <ChalkText variant="body" style={styles.body}>
            {copy.body}
          </ChalkText>

          {line ? (
            <ChalkText
              variant="bodySm"
              style={styles.line}
              testID="verify-sheet.notice"
              accessibilityLiveRegion="polite"
            >
              {line}
            </ChalkText>
          ) : null}
          {appleError && path === 'apple' ? (
            <ChalkText variant="bodySm" style={styles.line} accessibilityLiveRegion="polite">
              {APPLE_ERROR}
            </ChalkText>
          ) : null}

          <View style={styles.actions}>
            {phase === 'switched' ? (
              <Button
                testID="verify-sheet.continue"
                label={MON['mon.verify.continue']}
                onPress={finishSignedIn}
              />
            ) : path === 'sleeper' ? (
              <Button
                testID="verify-sheet.sleeper"
                label={MON['mon.verify.sleeper']}
                onPress={verifyWithSleeper}
                disabled={busy}
              />
            ) : appleAvailable ? (
              <AppleAuthentication.AppleAuthenticationButton
                testID="verify-sheet.apple"
                buttonType={AppleAuthentication.AppleAuthenticationButtonType.SIGN_IN}
                buttonStyle={AppleAuthentication.AppleAuthenticationButtonStyle.WHITE}
                cornerRadius={radii.sm}
                style={styles.appleButton}
                onPress={() => void signInWithApple()}
              />
            ) : null}
            {phase === 'apple' ? <ActivityIndicator color={chalk.dim} /> : null}
            {phase !== 'switched' ? (
              <Button
                testID="verify-sheet.cancel"
                variant="ghost"
                label={VERIFY_CANCEL}
                onPress={cancel}
                disabled={busy}
              />
            ) : null}
          </View>
        </SafeAreaView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    paddingHorizontal: space.xl,
    paddingBottom: space.md,
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    borderRadius: radii.xs,
    backgroundColor: ink.lineStrong,
    marginTop: space.sm,
    marginBottom: space.md,
  },
  body: { color: chalk.dim, marginTop: space.sm },
  line: { color: chalk.base, marginTop: space.md },
  actions: { gap: space.sm, marginTop: space.lg },
  appleButton: { alignSelf: 'stretch', height: 44 },
});
