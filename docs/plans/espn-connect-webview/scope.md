# Feature Scope — ESPN Connect WebView (cookie capture, Phase 1b)

**Date:** 2026-08-08
**Entry point:** direct ask (operator) — executes the deferred Phase 1b of
`docs/plans/espn-league-linking-plan-2026-07-11.md` §4 Option 1
**Builder:** Claude session (worktree `espn-webview-capture` off `origin/main` @ `cb6aacb`)
**Operator sign-off on waivers:** yes — operator approved build 2026-08-08 with the
Maestro in-WebView waiver and deferred sim-gate build surfaced (see §3, §5)

---

## What it is

An in-app `EspnConnectScreen` (WebView to ESPN's own login, modeled on
`SleeperConnectScreen.tsx`) that captures the `espn_s2` + `SWID` cookies from the
**native cookie store** (`@react-native-cookies/cookies` over WKHTTPCookieStore —
NOT injected-JS `document.cookie`, because `espn_s2` can be HttpOnly) and feeds
them into the existing `EspnLinkSheet` private-league flow, replacing the manual
paste as the primary path (paste stays as fallback). Includes an OTP-step assist:
injected JS detects Disney SSO's one-time-code step and surfaces a native hint
banner (iOS system autofill supplies the code itself; we never read the user's
email or the code — nothing but the two cookies ever leaves the WebView).

Backend: **zero changes** — `POST /api/espn/link` already accepts, Fernet-encrypts,
and replays `espn_s2`/`swid`.

## 1. Analytics scope

- [x] **(a) New events specced** (names to be aligned by the builder with the live
  taxonomy conventions before coding — check existing `track()` calls / taxonomy doc):

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `espn_connect_opened` | `{source: 'link_sheet'}` | Connect screen mounts | mobile |
  | `espn_connect_otp_step` | `{}` | OTP step detected in Disney SSO | mobile |
  | `espn_connect_captured` | `{saw_otp: bool}` | Both cookies read from native store | mobile |
  | `espn_connect_abandoned` | `{saw_otp: bool}` | Screen closed without capture | mobile |

  → follow-through: taxonomy doc updated; nothing stored server-side beyond the
  existing `user_events` ingestion (no data-dictionary change).

## 2. Schema & flag scope

- New/changed tables or columns: **none**
- New/changed feature flags: **`espn.webview_capture`** — `config/features.json`
  (default **false**) + `backend/feature_flags.py` `FLAG_KEYS` +
  `docs/config-reference.md`. Requires `espn.link` also on to have any effect
  (the sheet itself is gated by `espn.link`). Graduation: operator flips after a
  TestFlight build containing the native dep validates against a real private
  league (the friend's league 493554 is the live test case). Rollback lever:
  flip the flag — the sheet reverts to manual paste with no client update.
  **Graduation superseded 2026-08-08:** operator ordered ship with the flag ON
  at merge, ahead of TestFlight QA. Safe for existing clients (no pre-Phase-1b
  binary reads the flag); the §3 QA checklist runs against the new build with
  the feature already live, and the rollback lever stands.
- New env vars / `model_config` keys: **none**

## 3. Test scope (mobile test platform)

- [x] **New flow:** `mobile/.maestro/` ESPN-connect flow — covers: open link sheet
  (flag on), private toggle shows "Sign in to ESPN" entry, connect screen mounts
  (chrome + consent copy asserted by testID), back out, manual-paste fallback
  still present and functional.
- [x] **WAIVED (partial):** the in-WebView portion (Disney SSO login, OTP entry,
  cookie landing) cannot be driven by the hermetic Maestro harness — it is a live
  third-party page and Maestro id-selectors can't reach WebView internals.
  Covered instead by: unit-level cookie-extraction tests (mock CookieManager) and
  a manual TestFlight QA pass against a real private league before flag flip.
  **Operator informed pre-build.**
- `testID`s added: `espn-connect.sign-in` (sheet entry), `espn-connect.banner`,
  `espn-connect.webview`, `espn-connect.back-btn`, `espn-connect.otp-hint`,
  `league.espn-resync-signin` (League-tab re-sync recovery). **Lint note
  (build amendment):** `mobile/scripts/testid-lint.sh` does not exist on this
  branch — `mobile/scripts/` is gitignored (TEST_LEDGER 2026-08-08), so the
  planned lint script never landed in-repo. Verification performed instead:
  manual cross-check that every id referenced by the flow and registry
  resolves in `mobile/src/` (all ids found). Creating a tracked lint script
  is a separate task.
- **TestFlight QA checklist (pre flag-flip, real private league 493554):**
  1. WebView sign-in captures fresh cookies and the sheet auto-advances to
     the team preview (fresh login every time — the screen clears stale ESPN
     cookies on mount).
  2. **OTP leg:** on an OTP-challenged Disney SSO login, verify the native
     "ESPN emailed you a code" hint actually appears (the detector is
     injected into all frames because SSO may render in an iframe — a
     selector drift here is only observable live).
  3. `espn_auth_required` recovery: a private league ID with no/expired
     cookies auto-expands the sheet's private section with the sign-in
     button; the League-tab re-sync failure shows the sign-in recovery
     button. (Not hermetically testable — the seeded harness backend cannot
     produce ESPN's live 403.)
- Smoke-suite impact: none while flag is off; league-link smoke unaffected.
- Backend: no pytest delta (no backend change); existing `espn.link` tests stand.

### Field failures (2026-08-09, operator-reported from a live TestFlight user) — FIXED

Two coupled failures on a real private-league link attempt, diagnosed in code
(no device repro available to the fixing session — see the re-test list in
`docs/feedback/items/espn-webview-escape/status.md`):

1. **Mid-login Safari escape.** The screen shipped `originWhitelist={['https://*']}`
   with no `onShouldStartLoadWithRequest`. react-native-webview's whitelist
   fallback hands ANY navigation failing the whitelist to `Linking.openURL` —
   Safari for http(s), a native app for schemes — and the gate sees subframe
   and popup navigations too (Disney SSO is an embedded iframe; iOS routes
   `window.open`/`target=_blank` back into the same WebView). Any `http://`
   hop, ad-iframe request, or popup in the login chain bounced the user into
   Safari mid-login. **Fix:** `originWhitelist={['*']}` (fallback unreachable)
   + `onShouldStartLoadWithRequest` backed by the pure, node-tested
   `allowEspnNavigation()` (`src/utils/espnNavPolicy.ts`,
   `tests/check-espn-nav-policy.js`): http(s)/about/data/blob load inside the
   WebView (all Disney SSO domains allowed); app schemes (`espn://`,
   `itms-appss://`, …) and app-bouncing hosts (`apps.apple.com`,
   `*.app.link`, …) are swallowed — nothing is ever opened externally.
   `setSupportMultipleWindows={false}` routes Android popups through the same
   gate.
2. **Captured cookies rejected by ESPN ("fetching league" → private-league
   error with both fields correctly prefilled).** Capture → bus → prefill →
   `POST /api/espn/link` all worked; ESPN rejected the VALUES. Ground truth
   from a live browser jar: espn_s2's wire form is percent-ENCODED (~350
   chars, %XX escapes) and SWID carries literal braces. iOS's native cookie
   store surfaces espn_s2 percent-DECODED (`NSHTTPCookie.value` via
   @react-native-cookies), and the backend forwarded it verbatim
   (`espn_service.fetch_league` Cookie header), so ESPN 401/403'd → mapped to
   `espn_auth_required` → the sheet told a just-signed-in user to sign in
   again. **Fix:** backend canonicalizers `canonical_espn_s2` /
   `canonical_swid` in `backend/espn_service.py` at the single Cookie-header
   choke point (covers WebView capture, decoded pastes, and stored-cookie
   replays): a %XX-bearing value passes byte-identical (never double-encoded);
   an escape-free value is re-encoded (`quote(safe='')`); SWID gains braces
   only if pasted bare. Pinned by `backend/tests/test_espn_service.py`
   (§1/§1b). The sheet's `espn_auth_required` copy now branches on whether
   cookies were actually sent, so a rejected sign-in is named as such instead
   of re-prompting "this league is private". The bus additionally parks a
   pair delivered while no sheet is subscribed (remount gap) and flushes it
   to the next subscriber, so a spent login can't be dropped.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/renamed/changed |
| `living-memory/LLD.md` | updated | mobile convention: native-cookie-store capture pattern for HttpOnly credentials |
| `docs/architecture.md` | n/a | no backend module/data-flow change |
| `living-memory/HLD.md` | n/a | no architecture shift (existing link flow, new capture device) |
| `docs/cross-client-invariants.md` | n/a | no shared constants/enums/colors |
| `docs/glossary.md` | n/a | no new domain term (ESPN linking terms already present) |
| ADR or `DECISIONS.md` | updated | DECISIONS.md: native cookie store over injected JS (HttpOnly); OTP assist = detect + hint, never read the code |
| `docs/config-reference.md` | updated | new flag `espn.webview_capture` |

## 5. Ship gate declaration

- **Simulator-gate tier:** the change is dark (flag default-OFF) but adds a
  **native dependency**, which changes the binary for everyone. Declared tier:
  **feature flow + smoke subset (tier 2)** — but the sim build requires
  `pod install` + a rebuilt dev client, which must run from the no-space clone
  (`../ftf-test-clone`); spaces in this repo path break `expo run:ios`.
- Evidence: TEST_LEDGER entry + `qa/sim-runs/last-sim-run.json` after the run.
- **Operator deviation (decided 2026-08-08):** operator ordered merge + push +
  EAS/TestFlight build with the flag ON, without a local sim run — the tier-2
  sim gate is waived in favor of the TestFlight build as the validation gate
  (the sim run needed a rebuilt dev client from the no-space clone; the
  TestFlight binary exercises the same native module). §3's TestFlight QA
  checklist is the compensating control; rollback is the flag.
