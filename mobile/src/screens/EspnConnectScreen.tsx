import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, StyleSheet, Linking, Pressable } from 'react-native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';
import { useNavigation, useRoute } from '@react-navigation/native';
import { ink, chalk, ice, flare, space, radii, type } from '../theme/chalkline';
import { Icon } from '../components/chalkline';
import { clearEspnCookies, readEspnCookies } from '../utils/espnCookies';
import { allowEspnNavigation } from '../utils/espnNavPolicy';
import { deliverEspnCookies } from '../state/espnConnectBus';
import { storeEspnCredentials } from '../api/espn';
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
//
// URL decision (field report, build 95, 2026-08-09): the operator reported
// the WebView "didn't work" on first load and needed a second visit to
// /login within the same browser session before it worked. Candidates
// evaluated instead of this URL, from curl'ing each (redirect chains,
// headers) plus checking what other cookie-based ESPN tools target:
//   - fan.espn.com/espn/login — DNS SERVFAIL, the host does not resolve at
//     all. Not a viable candidate, dead end.
//   - fantasy.espn.com/football/ (unauth) — 404s directly; it is NOT a
//     login redirect target, it's the fantasy home page. An unauth hit on
//     a specific league path 302s to www.espn.com/fantasy/football/ (the
//     signed-out fantasy landing), never to a full-page /login form — so
//     there's no clean "hard login" entry point on this host either.
//   - www.espn.com/login (current) — every curl against it (with or
//     without a redirect query param) gets AWS WAF's JS challenge (202,
//     x-amzn-waf-action: challenge, empty body) rather than a real
//     redirect chain, confirming this is the CURRENT, edge-protected entry
//     point ESPN serves — not a stale/legacy path (a legacy page wouldn't
//     be sitting behind the same active WAF as everything else on
//     espn.com). A bot-signature curl can't pass that challenge, so the
//     iframe-bootstrap behavior itself can't be inspected from this
//     session — a real WKWebView (which runs the challenge JS) is required,
//     hence the TestFlight confirmation note below.
// Conclusion: this is the right URL — the reported failure is a COLD-LOAD
// bug in Disney OneID's iframe bootstrap, not a wrong destination. Grounding
// (recovered browser evidence): in the operator's own successful Chrome
// session, login ALSO only worked on the SECOND load of this exact URL
// (loaded once, reloaded, then succeeded) — which lines up with this screen
// deliberately clearing cookies/storage before every mount (clearEspnCookies
// above), i.e. every capture attempt IS a cold load by construction. Fix:
// keep this URL, and perform ONE automatic reload right after the first
// load completes (mirrors what fixed it for the operator), plus a manual
// RELOAD control and a wedge-detection hint as the resilience net for
// whatever the automatic warm-up doesn't catch. NEEDS TestFlight
// confirmation — this session cannot render a WKWebView to verify the
// iframe bootstrap directly.
const ESPN_LOGIN_URL = 'https://www.espn.com/login';

// How long to wait, after a load that is NOT the automatic warm-up reload,
// before assuming the page is wedged (no capture, no OTP step seen yet) and
// surfacing the reload hint. One timer, checked once when it fires — no
// state machine, no per-navigation resets.
const WEDGE_HINT_TIMEOUT_MS = 10000;

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
  // Send-auth lazy flow (2026-08-11): WHY was this screen entered?
  //   • undefined (default) — the private-league link capture: cookies go
  //     back to EspnLinkSheet through the bus, copy talks about reading a
  //     private league. Unchanged behavior.
  //   • 'send' — the trade-send path (SendInEspnButton): there is no sheet
  //     and no league to link (it's already imported), so THIS screen stores
  //     the captured pair server-side (credential-only POST /api/espn/link)
  //     and the copy is about connecting the account to send trades. Never
  //     tell this user their league is private — it usually isn't.
  const route = useRoute<any>();
  const sendMode: boolean = route.params?.reason === 'send';
  const [otpHint, setOtpHint] = useState(false);
  // Wedge-detection hint (field report, build 95) — shown when a load
  // finishes (past the one-time automatic warm-up reload) and nothing has
  // progressed for WEDGE_HINT_TIMEOUT_MS. Purely a display flag; the actual
  // decision logic is the single timer in onLoadEnd below.
  const [wedgeHint, setWedgeHint] = useState(false);
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
  // WebView imperative handle for the manual reload control + the one-time
  // automatic warm-up reload (see ESPN_LOGIN_URL's URL-decision comment).
  const webviewRef = useRef<WebView>(null);
  // Guards the automatic warm-up reload to fire exactly ONCE per mount — a
  // deterministic single reload, not a retry loop.
  const autoReloadedRef = useRef(false);
  const wedgeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearWedgeTimer = useCallback(() => {
    if (wedgeTimerRef.current) {
      clearTimeout(wedgeTimerRef.current);
      wedgeTimerRef.current = null;
    }
  }, []);

  // One-time automatic warm-up reload + the wedge-hint timer. First load
  // completing: silently reload once (the empirical fix — see the
  // ESPN_LOGIN_URL comment) and wait for THAT load's onLoadEnd before
  // arming anything else. Every load after the warm-up (including one
  // triggered by the manual Reload control): arm a single wedge-hint timer
  // that fires only if nothing has progressed by then.
  const onLoadEnd = useCallback(() => {
    if (unmountedRef.current) return;
    if (!autoReloadedRef.current) {
      autoReloadedRef.current = true;
      webviewRef.current?.reload();
      return;
    }
    clearWedgeTimer();
    wedgeTimerRef.current = setTimeout(() => {
      if (!unmountedRef.current && !capturedRef.current && !sawOtpRef.current) {
        setWedgeHint(true);
      }
    }, WEDGE_HINT_TIMEOUT_MS);
  }, [clearWedgeTimer]);

  // Manual RELOAD control (resilience net regardless of the URL decision —
  // one tap recovers a wedged page without leaving the screen).
  const manualReload = useCallback(() => {
    setWedgeHint(false);
    clearWedgeTimer();
    webviewRef.current?.reload();
  }, [clearWedgeTimer]);

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
    if (sendMode) {
      // Send path: no sheet is listening — store the credential server-side
      // ourselves (credential-only POST /api/espn/link) so the propose can
      // read it, then pop back to the send surface. A failed store is not
      // retried here: the send button's focus handler re-checks GET
      // /api/espn/link on return and reports "Not connected" honestly.
      try {
        await storeEspnCredentials(pair.espnS2, pair.swid);
      } catch {
        /* focus-handler re-check owns the failure report */
      }
      navigation.goBack();
      return;
    }
    deliverEspnCookies(pair);
    // No success overlay: the sheet's Modal re-mounts ABOVE the whole nav
    // stack the moment the bus delivers, so an overlay here could never be
    // seen. The sheet reappearing with the cookies filled (and
    // auto-advancing to the preview) IS the success feedback — just pop.
    navigation.goBack();
  }, [navigation, sendMode]);

  // espn_connect_opened on mount; espn_connect_abandoned if we leave without
  // a capture (cleanup runs on unmount — including header back / swipe).
  useEffect(() => {
    track(
      'espn_connect_opened',
      { source: sendMode ? 'send_button' : 'link_sheet' },
      'EspnConnect',
    );
    return () => {
      unmountedRef.current = true;
      clearWedgeTimer();
      if (!capturedRef.current) {
        track('espn_connect_abandoned', { saw_otp: sawOtpRef.current }, 'EspnConnect');
        // Un-hide the sheet's Modal — it hid itself for the WebView push.
        // Send mode never touches the bus: no sheet hid itself, and a null
        // delivered here could reach an unrelated dormant sheet.
        if (!sendMode) deliverEspnCookies(null);
      }
    };
  }, [clearWedgeTimer, sendMode]);

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
      // Real progress — the wedge hint (if showing) no longer applies.
      setWedgeHint(false);
      clearWedgeTimer();
      track('espn_connect_otp_step', {}, 'EspnConnect');
    }
  }, [clearWedgeTimer]);

  return (
    <View style={styles.root}>
      <View style={styles.banner} testID="espn-connect.banner">
        <View style={styles.bannerTopRow}>
          <Text style={[type.bodySm, styles.bannerTopText]}>
            {sendMode
              ? 'Sign in to ESPN below to connect your account so FTF can ' +
                'send trades for you. We never see your password — once ' +
                'you’re in, we read the two sign-in cookies ESPN issues ' +
                '(espn_s2 and SWID).'
              : 'Log in to ESPN below. We never see your password — once ' +
                'you’re in, we read the two cookies ESPN issues for your ' +
                'private league (espn_s2 and SWID) so we can import it.'}
          </Text>
          {/* Always-visible resilience net (field report, build 95): one
              tap recovers a wedged/blank ESPN login load, regardless of
              whether the automatic warm-up reload already caught it. */}
          <Pressable
            testID="espn-connect.reload"
            onPress={manualReload}
            accessibilityRole="button"
            accessibilityLabel="Reload the ESPN login page"
            style={styles.reloadBtn}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Icon name="reload" size={16} color={chalk.dim} />
          </Pressable>
        </View>
        <Text style={type.bodySm}>
          {sendMode
            ? 'Those two cookies are stored encrypted and used only for ' +
              'actions you take here — like sending a trade you built. '
            : 'Those two cookies are stored encrypted and used only to read ' +
              'this league — read-only, we never post or change anything. '}
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
        {wedgeHint ? (
          <View testID="espn-connect.wedge-hint" style={styles.otpHint}>
            <Text style={[type.bodySm, styles.otpHintText]}>
              Page didn’t load right? Tap the reload icon above.
            </Text>
          </View>
        ) : null}
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
        ref={webviewRef}
        onLoadEnd={onLoadEnd}
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
  bannerTopRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: space.sm,
  },
  bannerTopText: { flex: 1 },
  // Icon-only tap target — hitSlop pads it to a 44pt effective target
  // without inflating the visible glyph inside the banner's copy flow.
  reloadBtn: { padding: space.xs },
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
