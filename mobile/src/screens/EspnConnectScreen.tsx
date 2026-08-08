import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, ActivityIndicator, StyleSheet, Linking } from 'react-native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';
import { useNavigation } from '@react-navigation/native';
import { ink, chalk, ice, flare, space, radii, type } from '../theme/chalkline';
import { readEspnCookies } from '../utils/espnCookies';
import { deliverEspnCookies } from '../state/espnConnectBus';
import { track } from '../api/events';

// ESPN Connect WebView — Phase 1b of ESPN league linking
// (docs/plans/espn-connect-webview/scope.md, plan §4 Option 1). Modeled on
// SleeperConnectScreen: the user logs in to ESPN's OWN page in an in-app
// WebView — we never handle the password. Once they're logged in, ESPN's
// private-league cookies (espn_s2 + SWID) let the backend read the league.
//
// Why the NATIVE cookie store, not injected JS: espn_s2 is issued HttpOnly,
// so the WebView's `document.cookie` cannot see it. We read the cookies from
// WKHTTPCookieStore via @react-native-cookies/cookies instead (see
// utils/espnCookies.ts + DECISIONS.md D-021). The injected JS on this page
// does exactly ONE thing — signals when Disney SSO shows its one-time-code
// step so we can raise a native hint. It NEVER reads or transmits the code,
// any field value, or any DOM content; the only data that ever leaves this
// screen is the two cookies, and they come from the native store, not JS.

// The fantasy home reliably bounces an unauthenticated user through Disney
// SSO login and lands back logged-in, dropping espn_s2/SWID on the espn.com
// + fantasy.espn.com hosts we poll. (www.espn.com/login also works but can
// land on a generic espn.com home; the fantasy host is where the cookies we
// need are set.)
const ESPN_LOGIN_URL = 'https://www.espn.com/login';

// Injected once per page load (guarded). OTP-STEP DETECTION ONLY. A
// MutationObserver watches for the Disney SSO one-time-code input; when it
// appears we postMessage a bare presence signal. No field value, no code, no
// DOM text ever crosses this boundary — see the screen header.
const INJECTED_OTP_DETECT = `
(function () {
  if (window.__ftfEspnOtp) return;
  window.__ftfEspnOtp = true;
  var signalled = false;
  function isOtpStep() {
    // Disney SSO renders the emailed one-time code as a dedicated input.
    return !!document.querySelector(
      'input[autocomplete="one-time-code"], input[name="otp"], input[data-testid="OneTimePasscode"]'
    );
  }
  function check() {
    if (signalled) return;
    if (isOtpStep()) {
      signalled = true;
      window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'otp_step' }));
    }
  }
  try {
    var mo = new MutationObserver(check);
    mo.observe(document.documentElement, { childList: true, subtree: true });
  } catch (e) {}
  check();
})();
true;
`;

export default function EspnConnectScreen() {
  const navigation = useNavigation<any>();
  const [captured, setCaptured] = useState(false);
  const [otpHint, setOtpHint] = useState(false);
  // Refs so the poll loop and the unmount handler read live values without
  // re-subscribing. `capturedRef` is the post-once guard (mirrors the
  // Sleeper screen's `capturedRef`).
  const capturedRef = useRef(false);
  const sawOtpRef = useRef(false);

  // Deliver exactly once: read the native store, and if BOTH cookies are
  // present hand them to the sheet through the bus and pop back.
  const tryCapture = useCallback(async () => {
    if (capturedRef.current) return;
    const pair = await readEspnCookies();
    if (!pair || capturedRef.current) return;
    capturedRef.current = true;
    setCaptured(true);
    track('espn_connect_captured', { saw_otp: sawOtpRef.current }, 'EspnConnect');
    deliverEspnCookies(pair);
    // Brief success beat so the user sees the connected state before the
    // sheet reappears underneath.
    setTimeout(() => navigation.goBack(), 900);
  }, [navigation]);

  // espn_connect_opened on mount; espn_connect_abandoned if we leave without
  // a capture (cleanup runs on unmount — including header back / swipe).
  useEffect(() => {
    track('espn_connect_opened', { source: 'link_sheet' }, 'EspnConnect');
    return () => {
      if (!capturedRef.current) {
        track('espn_connect_abandoned', { saw_otp: sawOtpRef.current }, 'EspnConnect');
        // Un-hide the sheet's Modal — it hid itself for the WebView push.
        deliverEspnCookies(null);
      }
    };
  }, []);

  // Poll the native cookie store on an interval (login is an SPA/redirect
  // dance, not a single load event we can hook) AND on nav-state changes.
  useEffect(() => {
    const id = setInterval(() => void tryCapture(), 1000);
    return () => clearInterval(id);
  }, [tryCapture]);

  const onMessage = useCallback((e: WebViewMessageEvent) => {
    let payload: { type?: string };
    try {
      payload = JSON.parse(e.nativeEvent.data);
    } catch {
      return;
    }
    if (payload?.type === 'otp_step' && !sawOtpRef.current) {
      sawOtpRef.current = true;
      setOtpHint(true);
      track('espn_connect_otp_step', {}, 'EspnConnect');
    }
  }, []);

  return (
    <View style={styles.root}>
      <View style={styles.banner}>
        <Text style={type.bodySm}>
          Log in to ESPN below. We never see your password — once you’re in,
          we read the two cookies ESPN issues for your private league
          (espn_s2 and SWID) so we can import it.
        </Text>
        <Text style={type.bodySm}>
          Those two cookies are stored encrypted and used only to read this
          league — read-only, we never post or change anything.{' '}
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
        {otpHint ? (
          <View testID="espn-connect.otp-hint" style={styles.otpHint}>
            <Text style={[type.bodySm, styles.otpHintText]}>
              ESPN emailed you a code. iOS can autofill it from Mail or
              Messages — or grab it from your inbox and type it in.
            </Text>
          </View>
        ) : null}
      </View>

      <WebView
        testID="espn-connect.webview"
        source={{ uri: ESPN_LOGIN_URL }}
        injectedJavaScript={INJECTED_OTP_DETECT}
        onMessage={onMessage}
        // Re-check the native store whenever the page navigates (login
        // redirect, SSO bounce) — cheaper than waiting for the next poll.
        onNavigationStateChange={() => void tryCapture()}
        domStorageEnabled
        sharedCookiesEnabled
        thirdPartyCookiesEnabled
        originWhitelist={['https://*']}
        style={styles.web}
      />

      {captured ? (
        <View style={styles.overlay} pointerEvents="auto" testID="espn-connect.done">
          <Text style={[type.label, styles.overlayText]}>ESPN connected</Text>
          <Text style={[type.bodySm, styles.overlaySub]}>
            Bringing your league in…
          </Text>
        </View>
      ) : null}
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
  // Tappable disclosure link — ice = action color (Chalkline).
  learnMore: { color: ice.base },
  // Informational hint — flare is the informational-highlight accent (ADR-005),
  // never used as an action here.
  otpHint: {
    marginTop: space.xs,
    padding: space.sm,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: flare.base,
    backgroundColor: ink.ink2,
  },
  otpHintText: { color: chalk.base },
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
