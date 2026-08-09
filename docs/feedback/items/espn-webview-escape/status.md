# espn-webview-escape — status

**Reported:** 2026-08-09, by the operator via chat (a real TestFlight user's
private-league link attempt). **No in-app feedback item exists for this** —
the folder slug stands in for an ID.

**Feature:** ESPN Connect WebView cookie capture (`espn.webview_capture`,
Phase 1b — `docs/plans/espn-connect-webview/scope.md`), shipped in build 90.

**Status:** fixed in code on branch `worktree-agent-a01b25987626b4e84`
(commit "espn-webview: keep login in-app; capture survives background
cycle"). Not merged/pushed by the fixing session. **Not device-verified** —
see Honest limits below.

## Symptoms (operator-reported, refined over three messages)

1. During the in-WebView ESPN/Disney login, the user was bounced out of the
   app to an ESPN page **in Safari** (not the native ESPN app).
2. On returning to FTF, both espn_s2/SWID fields were correctly prefilled
   with the captured values; the user hit Continue, the sheet showed
   "Fetching league…", then errored with the private-league auth message
   ("This league is private. Sign in to ESPN below and we'll fetch it") —
   nothing was stored, and the copy sent the just-signed-in user in a loop.

## Root causes (from code)

### 1. Safari escape: react-native-webview's originWhitelist fallback

`EspnConnectScreen` rendered its WebView with `originWhitelist={['https://*']}`
and **no** `onShouldStartLoadWithRequest`/`onOpenWindow`. In
react-native-webview 13.15.0 (`lib/WebViewShared.js`,
`createOnShouldStartLoadWithRequest`), any navigation whose origin fails the
whitelist is NOT merely blocked — it is handed to `Linking.canOpenURL` →
`Linking.openURL`, i.e. opened **outside the app**: Safari for http(s) URLs,
the owning native app for custom schemes. The native side forwards **every**
navigation action through this gate — subframes included (Disney SSO runs as
an embedded iframe: `cdn.registerdisney.go.com` responder, ESPN-ONESITE.WEB
client) and popups too (with no `onOpenWindow`, iOS
`createWebViewWithConfiguration` reloads `window.open`/`target=_blank`
requests into the same WebView, which re-enters the gate). So any `http://`
(non-TLS) hop, ad-iframe request, or popup navigation anywhere in the
espn.com login chain failed `https://*` and punted the user to Safari
mid-login. A desktop-Chrome control run of the same login showed no inherent
external redirect in the flow — the escape is WebView-specific, exactly this
fallback.

**Fix:** invert the posture. `originWhitelist={['*']}` makes the library's
openURL fallback unreachable; the new pure function
`allowEspnNavigation(url)` (`mobile/src/utils/espnNavPolicy.ts`) becomes the
single gate via `onShouldStartLoadWithRequest`:

- **Allowed (inside the WebView):** all http(s) — the espn.com ↔
  registerdisney/disneyid Disney-SSO family explicitly included, and unknown
  hosts (ad/analytics/recaptcha iframes) deliberately kept in-app rather than
  risk breaking SSO — plus `about:`/`data:`/`blob:` (WKWebView internals).
- **Swallowed (never opened externally):** every non-http(s) scheme
  (`espn://`, `sportscenter://`, `itms-appss://`, `mailto:`, `intent:`, …)
  and http(s) hosts that exist to bounce into another app or the App Store
  (`apps.apple.com`, `itunes.apple.com`, `*.app.link`, `*.smart.link`,
  `*.onelink.me`, `*.page.link`).
- `setSupportMultipleWindows={false}` routes Android popups through the same
  gate. App-scheme swallowing is defensive hardening — the observed escape
  was the http(s)→Safari fallback.

Pinned by `mobile/tests/check-espn-nav-policy.js` (34 checks).

### 2. Rejected values: espn_s2 percent-encoding mismatch

End-to-end value journey: WKHTTPCookieStore → `NSHTTPCookie.value`
(@react-native-cookies `CookieManager.get`) → `pickEspnCookies` (trim only) →
`espnConnectBus` → sheet fields → `POST /api/espn/link` body →
`backend/espn_service.fetch_league` → `Cookie: espn_s2=…; SWID=…` header →
ESPN v3 API.

Ground truth from a live, working browser session: the jar's espn_s2 is
**percent-encoded** (~350 chars with %XX escapes) and SWID has **literal
braces**; those are the wire shapes ESPN accepts, and what manual pasters
copy from devtools. The iOS native cookie store surfaces espn_s2
percent-DECODED, and the backend forwarded whatever it received **verbatim**
(old comment: "Pass both through VERBATIM — espn_s2 is URL-encoded as
captured"— an assumption the WebView capture path broke). ESPN 401/403s the
decoded form → `EspnAuthError` → `espn_auth_required` 403 → the sheet's
auth branch told the user the league is private / to sign in — the loop.

**Fix (load-bearing, backend):** `canonical_espn_s2()` / `canonical_swid()`
in `backend/espn_service.py`, applied at the single Cookie-header choke point
(covers first links, decoded manual pastes, AND stored-encrypted-cookie
replays):

- espn_s2 with %XX escapes (`unquote(v) != v`) → byte-identical passthrough,
  never double-encoded (the decoded value space is base64-ish and never
  contains a bare '%', so the check cleanly separates the forms);
- escape-free espn_s2 → `urllib.parse.quote(v, safe='')` (+ / / / = become
  %2B/%2F/%3D — reproduces the browser wire form);
- SWID: braces added only when missing entirely; braced values untouched.

Pinned by `backend/tests/test_espn_service.py` §1/§1b (encoded-passthrough,
decoded-re-encode incl. header assembly through `fetch_league`, SWID braces,
empty/plain stability). Client capture stays verbatim — one code path for
delivered and pasted values, normalization lives server-side.

**Supporting fixes:**
- `EspnLinkSheet`'s `espn_auth_required` copy now branches on whether cookies
  were actually sent: a rejected pair reads "ESPN didn't accept that sign-in —
  it may have expired. Sign in to ESPN again below and we'll retry…" instead
  of gaslighting a just-signed-in user with "this league is private".
- `espnConnectBus` parks a pair delivered while no sheet is subscribed
  (remount gap across a background/foreground cycle) and flushes it to the
  next subscriber — a spent login can never be silently dropped
  (`deliverEspnCookies` previously no-op'd on a null subscriber).

## Honest limits

The fixing session **could not reproduce either failure on a real device** —
no simulator/TestFlight run was possible from the worktree, and the hermetic
Maestro harness cannot drive the live Disney SSO page (the scope block's
standing waiver). Bug 1's mechanism is verified against the installed
react-native-webview 13.15.0 source and bug 2's against a live browser jar's
cookie shapes + the backend's verbatim forwarding, but the iOS
decoded-espn_s2 behavior is inferred from the module's `NSHTTPCookie.value`
passthrough plus the operator's field report — the normalizer is written to
be correct for **either** captured form, so the fix does not depend on that
inference.

## Operator re-test checklist (TestFlight, real private league)

1. **Login stays in-app:** full ESPN/Disney sign-in (including the OTP email
   step — leaving to Mail and returning is fine) never opens Safari or the
   ESPN app; the WebView walks the whole flow itself.
2. **Capture → auto-advance:** on login completion the sheet reappears with
   both fields filled and auto-advances to the team preview ("which team is
   yours?") without a manual Continue — i.e. ESPN ACCEPTED the captured
   cookies (bug 2's fix). Pick a team; the league imports and opens.
3. **Manual Continue also works:** if auto-advance didn't fire (league ID
   empty at capture time), tapping Continue with the prefilled fields reaches
   the team preview.
4. **Paste fallback regression:** manual paste of devtools-copied
   (percent-encoded) cookies still links the league.
5. **Decoded paste (new coverage):** pasting a DECODED espn_s2 (with +/= and
   no %) should now also work — worth one try if convenient.
6. **Error copy:** with deliberately broken cookies (edit a character), the
   error should say ESPN didn't accept the sign-in/cookies — not "this league
   is private".
7. **Re-sync path:** League tab → Re-sync after cookie expiry still routes to
   the sheet with the sign-in recovery.
