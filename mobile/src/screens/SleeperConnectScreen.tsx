import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, ActivityIndicator, StyleSheet, Linking } from 'react-native';
import SleeperLoginCapture from '../components/SleeperLoginCapture';
import { Button } from '../components/chalkline';
import { useNavigation } from '@react-navigation/native';
import { ink, chalk, ice, space, type } from '../theme/chalkline';
import { linkSleeperToken, persistSleeperToken } from '../api/sendInSleeper';
import { useSession } from '../state/useSession';

// Slice 2 of "Send in Sleeper" (docs/plans/sleeper-write-capture-runbook.md §C1).
// The user logs into Sleeper's OWN page in an in-app WebView — we never handle
// the password. Once logged in, Sleeper drops a 365-day JWT in
// localStorage['token']; we read it out and hand it to POST /api/sleeper/link,
// which stores it encrypted. From then on, sends need no re-login.
//
// Account-auth P1: this capture DOUBLES AS ACCOUNT VERIFICATION. The backend
// checks the token's user_id claim against the session user and proves the
// token live against Sleeper (the signature oracle); on success the session
// is VERIFIED (link response `verified: true`) and write access is
// protected. We surface that in the success state and mirror it into
// useSession.verification so the "Verify your account" banner clears.

export default function SleeperConnectScreen() {
  const navigation = useNavigation<any>();
  const [phase, setPhase] = useState<'browsing' | 'linking' | 'done' | 'error'>('browsing');
  const [captureAttempt, setCaptureAttempt] = useState(0);
  const [verified, setVerified] = useState(false);
  const capturedRef = useRef(false);
  const mountedRef = useRef(true);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    mountedRef.current = false;
    if (closeTimer.current) clearTimeout(closeTimer.current);
  }, []);

  const onToken = useCallback(
    async (token: string) => {
      if (capturedRef.current) return;
      const userId = useSession.getState().user?.user_id;
      if (!userId) return;
      capturedRef.current = true;
      setPhase('linking');
      try {
        const res = await linkSleeperToken(token);
        if (!mountedRef.current || useSession.getState().user?.user_id !== userId) return;
        const isVerified = res?.verified === true;
        if (!isVerified) throw new Error('verification_incomplete');
        await persistSleeperToken(userId, token);
        if (!mountedRef.current || useSession.getState().user?.user_id !== userId) return;
        setVerified(isVerified);
        if (isVerified) {
          // The capture just proved control of this account — clear the
          // "Verify your account" banner without waiting for the next
          // session_init round-trip.
          const prev = useSession.getState().verification;
          useSession.getState().setVerification({
            session_verified: true,
            user_verified: true,
            verified_via: 'sleeper',
            enforced: prev?.enforced ?? false,
          });
        }
        // Brief success beat so the user sees the connected/verified state
        // before the modal closes under them.
        setPhase('done');
        if (mountedRef.current) closeTimer.current = setTimeout(() => navigation.goBack(), 1200);
      } catch {
        if (!mountedRef.current || useSession.getState().user?.user_id !== userId) return;
        // Let them retry — the token is still in the webview's localStorage.
        // (A 403 token_user_mismatch / token_rejected also lands here: the
        // Sleeper login doesn't control this FTF account.)
        capturedRef.current = false;
        setPhase('error');
      }
    },
    [navigation],
  );

  return (
    <View style={styles.root}>
      <View style={styles.banner}>
        <Text style={type.bodySm}>
          Log in to Sleeper below. We never see your password — once you’re in,
          we securely connect and verify your account so you can send trades
          from FTF.
        </Text>
        {/* Teardown 09-02 — token disclosure AT the consent moment (the
            policy already discloses this; the decision point didn't). */}
        <Text style={type.bodySm}>
          We store the sign-in token Sleeper issues — encrypted, used to verify
          your account and send trades you approve. Disconnect anytime in Settings.{' '}
          <Text
            style={styles.learnMore}
            accessibilityRole="link"
            onPress={() =>
              Linking.openURL('https://fantasy-trade-finder.onrender.com/privacy')
            }
          >
            Learn more
          </Text>
        </Text>
        {phase === 'error' && (
          <Text style={[type.bodySm, styles.error]}>
            Couldn’t connect — try again, and make sure you log in to the same
            Sleeper account you use here.
          </Text>
        )}
      </View>

      <View style={styles.web}>
        <SleeperLoginCapture key={captureAttempt} onToken={onToken} />
      </View>
      {phase === 'error' && (
        <Button label="Try Sleeper sign-in again" onPress={() => {
          setPhase('browsing');
          setCaptureAttempt((attempt) => attempt + 1);
        }} />
      )}

      {phase === 'linking' && (
        <View style={styles.overlay} pointerEvents="auto">
          <ActivityIndicator color={ice.base} />
          <Text style={[type.label, styles.overlayText]}>Connecting…</Text>
        </View>
      )}

      {phase === 'done' && (
        <View style={styles.overlay} pointerEvents="auto" testID="sleeperconnect.done">
          <Text style={[type.label, styles.overlayText]}>
            {verified ? 'Account verified' : 'Sleeper connected'}
          </Text>
          <Text style={[type.bodySm, styles.overlaySub]}>
            {verified
              ? 'Your ranks are now protected and trades can send from FTF.'
              : 'Connected — verification will complete next time you send.'}
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: ink.ink0 },
  banner: {
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    backgroundColor: ink.ink1,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    gap: space.xs,
  },
  error: { color: chalk.dim },
  // Tappable disclosure link — ice = action color (Chalkline).
  learnMore: { color: ice.base },
  web: { flex: 1, backgroundColor: ink.ink0 },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(0,0,0,0.5)',
    gap: space.sm,
  },
  overlayText: { color: chalk.base },
  overlaySub: { color: chalk.dim, textAlign: 'center', paddingHorizontal: space.xl },
});
