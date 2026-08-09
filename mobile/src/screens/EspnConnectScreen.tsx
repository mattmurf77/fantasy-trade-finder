import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, StyleSheet, Linking } from 'react-native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';
import { useNavigation } from '@react-navigation/native';
import { ink, chalk, ice, flare, space, radii, type } from '../theme/chalkline';
import { clearEspnCookies, readEspnCookies } from '../utils/espnCookies';
import { allowEspnNavigation } from '../utils/espnNavPolicy';
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
//
// On mount we CLEAR any existing ESPN cookies from the native store BEFORE
// the first poll (clearEspnCookies), so every capture is a fresh login. A
// stale pair from a prior session would otherwise be "captured" ~1s after
// mount — before the user can even see the login — and a server-expired
// espn_s2 would loop the user through 403s with no in-flow escape.

// ESPN's login entry: bounces straight into Disney SSO and returns to a
// logged-in state. Both cookies land on the `.espn.com` PARENT domain
// (domain-wide), so the plain www login host is fine — fantasy.espn.com
// inherits the same pair, and readEspnCookies polls both hosts anyway.
const ESPN_LOGIN_URL = 'https://www.espn.com/login';

// Injected once per page load (guarded). OTP-STEP DETECTION ONLY. A
// MutationObserver watches for the Disney SSO one-time-code input; when it
// appears we postMessage a bare presence signal. No field value, no code, no
// DOM text ever crosses this boundary — see the screen header. Injected into
// ALL frames (injectedJavaScriptForMainFrameOnly={false} below) because
// Disney SSO can render its form inside an iframe a main-frame-only script
// would never see; a presence-only observer is safe to run in subframes.
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
  const [otpHint, setOtpHint] = useState(false);
  // Refs so the poll loop and the unmount handler read live values without
  // re-subscribing. `capturedRef` is the post-once guard (mirrors the
  // Sleeper screen's `capturedRef`); `unmountedRef` stops an in-flight
  // cookie read from capturing AFTER the abandon path already ran (the user
  // can back out mid-read); `storeClearedRef` holds all polling until the
  // fresh-login clear settles.
  const capturedRef = useRef(false);
  const sawOtpRef = useRef(false);
  const unmountedRef = useRef(false);
  const storeClearedRef = useRef(false);

  // Deliver exactly once: read the native store, and if BOTH cookies are
  // present hand them to the sheet through the bus and pop back. The guards
  // are re-checked after the await — without that, backing out mid-read
  // would fire espn_connect_abandoned + deliver(null) in cleanup and THEN
  // this continuation would fire espn_connect_captured + deliver(pair).
  const tryCapture = useCallback(async () => {
    if (!storeClearedRef.current || capturedRef.current || unmountedRef.current) return;
    const pair = await readEspnCookies();
    if (!pair || capturedRef.current || unmountedRef.current) return;
    capturedRef.current = true;
    track('espn_connect_captured', { saw_otp: sawOtpRef.current }, 'EspnConnect');
    deliverEspnCookies(pair);
    // No success overlay: the sheet's Modal re-mounts ABOVE the whole nav
    // stack the moment the bus delivers, so an overlay here could never be
    // seen. The sheet reappearing with the cookies filled (and
    // auto-advancing to the preview) IS the success feedback — just pop.
    navigation.goBack();
  }, [navigation]);

  // espn_connect_opened on mount; espn_connect_abandoned if we leave without
  // a capture (cleanup runs on unmount — including header back / swipe).
  useEffect(() => {
    track('espn_connect_opened', { source: 'link_sheet' }, 'EspnConnect');
    return () => {
      unmountedRef.current = true;
      if (!capturedRef.current) {
        track('espn_connect_abandoned', { saw_otp: sawOtpRef.current }, 'EspnConnect');
        // Un-hide the sheet's Modal — it hid itself for the WebView push.
        deliverEspnCookies(null);
      }
    };
  }, []);

  // Fresh-login guarantee FIRST, then poll: clear any stale ESPN cookies,
  // and only once that settles start the 1s poll (login is an SPA/redirect
  // dance, not a single load event we can hook). Nav-state changes also
  // call tryCapture, but it bails until storeClearedRef flips.
  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | null = null;
    (async () => {
      try {
        await clearEspnCookies();
      } catch {
        /* per-name failures are already swallowed inside; belt & braces */
      }
      storeClearedRef.current = true;
      if (unmountedRef.current) return;
      interval = setInterval(() => void tryCapture(), 1000);
    })();
    return () => {
      if (interval) clearInterval(interval);
    };
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
      <View style={styles.banner} testID="espn-connect.banner">
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
        // OTP detector must reach a Disney SSO iframe too — presence-only
        // signal, so all-frames injection is safe (see the script header).
        injectedJavaScriptForMainFrameOnly={false}
        onMessage={onMessage}
        // Re-check the native store whenever the page navigates (login
        // redirect, SSO bounce) — cheaper than waiting for the next poll.
        onNavigationStateChange={() => void tryCapture()}
        domStorageEnabled
        sharedCookiesEnabled
        thirdPartyCookiesEnabled
        // ── Keep the whole login IN the app (2026-08-09 field failure) ──
        // originWhitelist is NOT just a filter: any navigation failing it is
        // handed to Linking.openURL by react-native-webview — i.e. punted to
        // Safari (http/https) or a native app (espn:// etc.). The previous
        // ['https://*'] whitelist is exactly how a user got bounced into
        // Safari mid-login (the gate sees subframe + popup navigations too).
        // So: pass EVERYTHING ('*') and make allowEspnNavigation the single
        // gate — it keeps http(s) inside the WebView (Disney SSO's iframe
        // hops between espn.com and registerdisney/disneyid domains included)
        // and SWALLOWS app-scheme/App-Store/deep-link-router hops. Nothing is
        // ever opened externally from this screen's WebView.
        originWhitelist={['*']}
        onShouldStartLoadWithRequest={(req) => allowEspnNavigation(req.url)}
        // Android: window.open/target=_blank navigates this same WebView (and
        // therefore through the gate above) instead of spawning a window the
        // OS would route to the browser. iOS ignores this prop; with no
        // onOpenWindow handler set, RNCWebView already loads popup requests
        // back into this WebView, where the same gate applies.
        setSupportMultipleWindows={false}
        style={styles.web}
      />
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
  // Informational hint — flare is the informational-highlight accent
  // (ADR-005), never used as an action here.
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
});
