import React, { useCallback, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';

import FeedbackFAB from '../components/FeedbackFAB';
import { Icon } from '../components/chalkline';
import { deliverRankCsv } from '../state/rankImportBus';
import { SOURCE_LABEL, type PremiumSource } from '../utils/rankPresets';
import { chalk, flare, ink, radii, space, type } from '../theme/chalkline';

// Premium rankings in-app browser — lane 2a of the Connected Rankings
// addendum, approved as [D-058].
//
// WHAT THIS SCREEN IS. The user opens DLF or Dynasty Nerds here and logs in
// ON THE SITE. FTF never touches, reads, prefills or stores a credential —
// there is no login form in this app and no cookie is ever read out of this
// WebView (contrast EspnConnectScreen, whose entire job is a cookie pair).
// The user then taps THE SITE'S OWN subscriber "Export CSV" button, in their
// own session, on a subscription they already pay for. This screen's only
// job is to catch the file that tap produces and hand it to the existing
// import pipeline.
//
// HARD RULES from [D-058], enforced here:
//   • USER-PRESENT AND ON-DEMAND ONLY. No timers, no polling, no background
//     work, no scheduled refresh. Every line below runs from a user event.
//   • NO AUTO-NAVIGATION beyond the initial URL. `source` picks one of two
//     constant URLs and nothing in this file ever calls injectJavaScript,
//     goBack/goForward programmatically, or sets a new `source` uri.
//   • THE SITE IS NEVER OPERATED BY FTF. The hint bar is native chrome; it
//     does not overlay, alter, click or read the page.
//
// THE DOWNLOAD-CAPTURE SHIM (scope.md §6.1 — pre-authorized deviation,
// flagged loudly in the build report). react-native-webview's
// `onFileDownload` only fires for a NAVIGATION the WebView declines to
// render, and it is iOS-only. Both sites build their CSV in the page and
// hand it to an `<a download>`: DLF as a `data:text/csv,…` URI, Dynasty
// Nerds as a `blob:` URL from `URL.createObjectURL`. WKWebView does not
// navigate for those, so `onFileDownload` does not see them. We therefore
// ALSO inject `INJECTED_DOWNLOAD_CAPTURE` below. Its entire scope:
//   (1) it wraps `URL.createObjectURL` to REMEMBER blobs the page creates
//       (pass-through: the original is called and its value returned
//       unchanged);
//   (2) it listens, in the capture phase, for a click that reaches an
//       `<a download>` and reads THAT anchor's href;
//   (3) it forwards the bytes, once, and only when a real user tap happened
//       in the last few seconds.
// It never clicks, never navigates, never fills a field, never mutates the
// DOM, never reads page text, never reads a cookie, credential or form
// value, and never sends anything anywhere except to this screen. It cannot
// produce a file the user did not ask the site to produce.

const SOURCE_URL: Record<PremiumSource, string> = {
  dynasty_nerds: 'https://www.dynastynerds.com/dynasty-rankings/',
  dlf: 'https://dynastyleaguefootball.com/rankings/dynasty-rankings/',
};

// Schemes that stay inside the WebView. Everything else is SWALLOWED — never
// handed to Linking.openURL, because bouncing a user into Safari mid-login is
// exactly the failure espnNavPolicy.ts documents.
const IN_APP_SCHEMES = new Set(['http', 'https', 'about', 'data', 'blob']);

export function allowPremiumNavigation(url: string): boolean {
  const m = /^([a-z][a-z0-9+.-]*):/i.exec(url || '');
  if (!m) return true; // relative navigation
  return IN_APP_SCHEMES.has(m[1].toLowerCase());
}

// See the shim discussion above. Read-only, user-gesture-gated, one-shot.
const INJECTED_DOWNLOAD_CAPTURE = `
(function () {
  if (window.__ftfRankCapture) return;
  window.__ftfRankCapture = true;

  var sent = false;
  var lastTap = 0;
  var GESTURE_WINDOW_MS = 8000;
  var blobs = {};

  function post(name, text) {
    if (sent) return;
    if (!text) return;
    sent = true;
    try {
      window.ReactNativeWebView.postMessage(JSON.stringify({
        type: 'ftf_rank_csv',
        filename: name || null,
        text: String(text)
      }));
    } catch (e) {}
  }

  function userPresent() {
    return Date.now() - lastTap < GESTURE_WINDOW_MS;
  }

  document.addEventListener('pointerdown', function () { lastTap = Date.now(); }, true);
  document.addEventListener('touchstart', function () { lastTap = Date.now(); }, true);
  document.addEventListener('mousedown', function () { lastTap = Date.now(); }, true);

  // (1) Remember blobs the page builds. Pass-through wrapper: the original
  //     is called with the original arguments and its value returned as-is.
  try {
    var origCreate = URL.createObjectURL.bind(URL);
    URL.createObjectURL = function (obj) {
      var url = origCreate(obj);
      try {
        var t = (obj && obj.type) || '';
        if (t.indexOf('csv') >= 0 || t.indexOf('text/') === 0 || t === '') {
          blobs[url] = obj;
          if (userPresent() && obj && typeof obj.text === 'function') {
            obj.text().then(function (txt) {
              if (looksLikeCsv(txt)) post(null, txt);
            }).catch(function () {});
          }
        }
      } catch (e) {}
      return url;
    };
  } catch (e) {}

  function looksLikeCsv(txt) {
    if (!txt || txt.length < 8) return false;
    var head = txt.slice(0, 400).toLowerCase();
    return head.indexOf(',') >= 0 && head.indexOf('player') >= 0;
  }

  // (2) The user's own tap on the site's own download link.
  document.addEventListener('click', function (ev) {
    try {
      lastTap = Date.now();
      var node = ev.target;
      var a = null;
      while (node && node !== document) {
        if (node.tagName === 'A' && node.hasAttribute('download')) { a = node; break; }
        node = node.parentNode;
      }
      if (!a) return;
      var href = a.getAttribute('href') || '';
      var name = a.getAttribute('download') || null;
      if (href.indexOf('data:') === 0) {
        var comma = href.indexOf(',');
        if (comma < 0) return;
        var meta = href.slice(0, comma);
        var body = href.slice(comma + 1);
        var txt = meta.indexOf('base64') >= 0 ? atob(body) : decodeURIComponent(body);
        if (looksLikeCsv(txt)) post(name, txt);
      } else if (href.indexOf('blob:') === 0) {
        var b = blobs[href];
        if (b && typeof b.text === 'function') {
          b.text().then(function (txt) {
            if (looksLikeCsv(txt)) post(name, txt);
          }).catch(function () {});
        } else {
          fetch(href).then(function (r) { return r.text(); }).then(function (txt) {
            if (looksLikeCsv(txt)) post(name, txt);
          }).catch(function () {});
        }
      }
    } catch (e) {}
  }, true);
})();
true;
`;

export default function PremiumRankingsBrowserScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const source: PremiumSource = route.params?.source === 'dlf' ? 'dlf' : 'dynasty_nerds';
  const label = SOURCE_LABEL[source];

  const [loading, setLoading] = useState(true);
  const [hintOpen, setHintOpen] = useState(true);
  const delivered = useRef(false);

  const uri = useMemo(() => SOURCE_URL[source], [source]);

  const handOff = useCallback(
    (text: string, filename: string | null) => {
      if (delivered.current) return;
      delivered.current = true;
      deliverRankCsv({ text, filename, via: 'browser' });
      // The user is done here the moment we have their file.
      if (navigation.canGoBack()) navigation.goBack();
      else navigation.navigate('Main');
    },
    [navigation],
  );

  const onMessage = useCallback(
    (e: WebViewMessageEvent) => {
      let msg: any;
      try {
        msg = JSON.parse(e.nativeEvent.data);
      } catch {
        return;
      }
      if (!msg || msg.type !== 'ftf_rank_csv' || typeof msg.text !== 'string') return;
      handOff(msg.text, typeof msg.filename === 'string' ? msg.filename : null);
    },
    [handOff],
  );

  // Tried FIRST, per the build brief. iOS-only, and it only fires for a
  // download the WebView treats as a navigation — a `data:` URI export is
  // the case that can reach here; `blob:` exports come through the shim.
  const onFileDownload = useCallback(
    ({ nativeEvent }: { nativeEvent: { downloadUrl: string } }) => {
      const url = nativeEvent?.downloadUrl || '';
      if (!url.startsWith('data:')) return;
      const comma = url.indexOf(',');
      if (comma < 0) return;
      try {
        const meta = url.slice(0, comma);
        const body = url.slice(comma + 1);
        const text = meta.includes('base64')
          ? globalThis.atob(body)
          : decodeURIComponent(body);
        handOff(text, null);
      } catch {
        /* leave it to the shim */
      }
    },
    [handOff],
  );

  return (
    <View style={styles.root}>
      {hintOpen ? (
        <View testID="premium-browser.hint" style={styles.hint}>
          <Icon name="flag" size={16} color={flare.base} />
          <Text style={styles.hintText}>
            Log in, then tap the site&apos;s Export CSV button. This is your
            own {label} account and subscription — we never see your login.
          </Text>
          <Pressable
            testID="premium-browser.hint-dismiss"
            accessibilityRole="button"
            accessibilityLabel="Dismiss hint"
            hitSlop={space.sm}
            onPress={() => setHintOpen(false)}
          >
            <Icon name="x" size={16} color={chalk.dim} />
          </Pressable>
        </View>
      ) : null}

      <WebView
        testID="premium-browser.webview"
        source={{ uri }}
        originWhitelist={['*']}
        onShouldStartLoadWithRequest={(req) => allowPremiumNavigation(req.url)}
        onLoadEnd={() => setLoading(false)}
        onMessage={onMessage}
        onFileDownload={onFileDownload}
        injectedJavaScript={INJECTED_DOWNLOAD_CAPTURE}
        javaScriptEnabled
        domStorageEnabled
        sharedCookiesEnabled
        thirdPartyCookiesEnabled
        style={styles.web}
      />

      {loading ? (
        <View style={styles.loading} pointerEvents="none">
          <ActivityIndicator color={chalk.dim} />
        </View>
      ) : null}

      <FeedbackFAB activeScreen="PremiumRankingsBrowser" aboveTabBar={false} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: ink.ink0 },
  web: { flex: 1, backgroundColor: ink.ink0 },
  hint: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    backgroundColor: ink.ink2,
    borderBottomWidth: 1,
    borderBottomColor: ink.lineStrong,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  hintText: { ...type.bodySm, flex: 1, lineHeight: 19 },
  loading: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: 0,
    bottom: 0,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: ink.ink0,
    borderRadius: radii.xs,
  },
});
