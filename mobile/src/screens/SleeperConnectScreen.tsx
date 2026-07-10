import React, { useCallback, useRef, useState } from 'react';
import { View, Text, ActivityIndicator, StyleSheet } from 'react-native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';
import { useNavigation } from '@react-navigation/native';
import { ink, chalk, ice, space, type } from '../theme/chalkline';
import { linkSleeperToken } from '../api/sendInSleeper';

// Slice 2 of "Send in Sleeper" (docs/plans/sleeper-write-capture-runbook.md §C1).
// The user logs into Sleeper's OWN page in an in-app WebView — we never handle
// the password. Once logged in, Sleeper drops a 365-day JWT in
// localStorage['token']; we read it out and hand it to POST /api/sleeper/link,
// which stores it encrypted. From then on, sends need no re-login.

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
  const [phase, setPhase] = useState<'browsing' | 'linking' | 'error'>('browsing');
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
        await linkSleeperToken(payload.token);
        navigation.goBack();
      } catch {
        // Let them retry — the token is still in the webview's localStorage.
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
          we securely connect your account so you can send trades from FTF.
        </Text>
        {phase === 'error' && (
          <Text style={[type.bodySm, styles.error]}>
            Couldn’t connect — try logging in again.
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
});
