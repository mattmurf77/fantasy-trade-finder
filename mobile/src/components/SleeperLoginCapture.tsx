import React, { useRef } from 'react';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';

// Shared first-party login capture. Passwords stay on Sleeper's page;
// callers decide how to prove ownership and when to retain the token.
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

export default function SleeperLoginCapture({ onToken }: {
  onToken: (token: string) => void | Promise<void>;
}) {
  const delivered = useRef(false);
  function onMessage(event: WebViewMessageEvent) {
    if (delivered.current) return;
    // A navigated external page must never supply an account credential.
    if (!/^https:\/\/(?:[a-z0-9-]+\.)*sleeper\.(?:com|app)(?:\/|$)/i.test(event.nativeEvent.url)) return;
    try {
      const payload = JSON.parse(event.nativeEvent.data);
      if (payload?.type !== 'token' || typeof payload.token !== 'string' ||
          payload.token.split('.').length !== 3) return;
      delivered.current = true;
      void onToken(payload.token);
    } catch { /* Ignore page messages that are not captured credentials. */ }
  }
  return <WebView
    testID="sleeper-login.webview"
    source={{ uri: SLEEPER_LOGIN_URL }}
    injectedJavaScript={INJECTED_POLLER}
    onMessage={onMessage}
    domStorageEnabled
    incognito
    originWhitelist={['https://*']}
    style={{ flex: 1 }}
  />;
}
