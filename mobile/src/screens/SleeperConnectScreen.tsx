import React, { useCallback, useRef, useState } from 'react';
import { View, Text, ActivityIndicator, StyleSheet } from 'react-native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';
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

const SLEEPER_LOGIN_URL = 'https://sleeper.com/login';

// Injected once per page load (guarded). Login is an SPA transition, not a full
// reload, so we poll localStorage until the token appears, then post it out
// exactly once. Sends only the token string — nothing else leaves the page.
const INJECTED_POLLER = `
(function () {
  if (window.__ftfSleeperCap) return;
  window.__ftfSleeperCap = true;
  var sent = false;
  function tick() {
    if (sent) return;
    try {
      var t = window.localStorage.getItem('token');
      if (t && String(t).split('.').length === 3) {
        sent = true;
        window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'token', token: t }));
      }
    } catch (e) {}
  }
  setInterval(tick, 800);
  tick();
})();
true;
`;

export default function SleeperConnectScreen() {
  const navigation = useNavigation<any>();
  const [phase, setPhase] = useState<'browsing' | 'linking' | 'done' | 'error'>('browsing');
  const [verified, setVerified] = useState(false);
  const capturedRef = useRef(false);

  const onMessage = useCallback(
    async (e: WebViewMessageEvent) => {
      if (capturedRef.current) return;
      let payload: { type?: string; token?: string };
      try {
        payload = JSON.parse(e.nativeEvent.data);
      } catch {
        return;
      }
      if (payload?.type !== 'token' || !payload.token) return;

      capturedRef.current = true;
      setPhase('linking');
      try {
        const res = await linkSleeperToken(payload.token);
        // #126: persist the captured JWT to the device Keychain so future
        // fresh sessions re-verify via silent replay instead of another
        // manual capture. Any 200 means the claim matched the session user
        // (mismatches 403 before storing) — keep the token even when
        // `verified` is false (inconclusive oracle; worth replaying later).
        const uid = useSession.getState().user?.user_id;
        if (uid) {
          persistSleeperToken(uid, payload.token).catch(() => {});
        }
        const isVerified = res?.verified === true;
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
        setTimeout(() => navigation.goBack(), 1200);
      } catch {
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
        {phase === 'error' && (
          <Text style={[type.bodySm, styles.error]}>
            Couldn’t connect — try again, and make sure you log in to the same
            Sleeper account you use here.
          </Text>
        )}
      </View>

      <WebView
        source={{ uri: SLEEPER_LOGIN_URL }}
        injectedJavaScript={INJECTED_POLLER}
        onMessage={onMessage}
        domStorageEnabled
        sharedCookiesEnabled
        thirdPartyCookiesEnabled
        originWhitelist={['https://*']}
        style={styles.web}
      />

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
