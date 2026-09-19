# #239 — Invite links open the app when installed (iOS Universal Links)

**Severity:** polish · **Reporter:** mattmurf77 · **Status:** built, pending merge + deploy + iOS build
**Branch:** `teardown-remediation` (worktree)

## Complaint

Tapping an invite link with the app already installed sends you to the App
Store / browser instead of the app.

## What already existed (investigation)

- **Invite URL format:** `https://fantasy-trade-finder.onrender.com/?league=<id>&ref=<username>`
  (`buildInviteUrl` in `mobile/src/components/InviteLeaguematesBanner.tsx`; `ref`
  omitted when the username is unknown; web builds the same shape). Trade shares
  use `/s/trade/<match_id>?ref=…` and packages `/s/p/<short_id>` (flag
  `growth.share_landing`, ON). Production domain: `fantasy-trade-finder.onrender.com`.
- **AASA route:** `GET /.well-known/apple-app-site-association` already existed in
  `backend/server.py` (unflagged, `application/json`, direct 200). appID =
  `N5Y4N2Q49A.com.fantasytradefinder.app` (team id from `mobile/eas.json`
  `appleTeamId`, overridable via `APPLE_TEAM_ID` env — no placeholder needed).
- **Deep-link router:** v2 route table in `mobile/src/utils/deepLinks.ts`
  (flag `ux.deeplink_router_v2`, ON) already accepts the https prefix and
  captures `?ref=` in both router modes; `AppDelegate.swift` already forwards
  `NSUserActivity` to `RCTLinkingManager`.
- **`mobile/app.json`** already declared
  `ios.associatedDomains: ["applinks:fantasy-trade-finder.onrender.com"]` — but
  this repo is **bare workflow**, so app.json iOS config is ignored at build
  time (see runbook, feedback #131). **This was the actual bug:** the committed
  entitlements file never got the key, so every build shipped without the
  Associated Domains capability and iOS never claimed the links.

## What changed

1. **Entitlements (the fix):** `mobile/ios/DTFDynastyTradeFinder/DTFDynastyTradeFinder.entitlements`
   now has `com.apple.developer.associated-domains` →
   `applinks:fantasy-trade-finder.onrender.com`. `project.pbxproj` already
   pointed `CODE_SIGN_ENTITLEMENTS` at this file — no pbxproj change needed.
2. **AASA scope:** added component `{"/": "/", "?": {"league": "?*"}}` so
   ref-less invite URLs (`/?league=<id>`) also open the app. Full claimed set:
   `/u/*`, `/s/*`, `/?ref=*`, `/?league=*` — never `/` unqualified, so normal
   web pages stay in the browser.
3. **Router wiring:** the AASA-claimed `/s/*` paths had no in-app screen, so an
   opened link would have toasted "Couldn't open that link". Added
   `rewriteUniversalPath` in `deepLinks.ts`: `/s/trade/<match_id>` →
   `app/matches/<match_id>` (Matches screen, match highlighted), `/s/p/<id>` →
   `app/trades`. Applied in both resolution paths (react-navigation `linking`
   via a `getStateFromPath` override for cold start; `_routePathV2` for
   warm-start url events). Invite links (`/?league&ref`) route as before:
   `ref` captured into `useSession.invitedBy` → sent as `invited_by` on the
   next `/api/session/init`; signed-out users land on SignIn.
4. **Tests:** new `backend/tests/test_universal_links.py` — content type,
   applinks shape/appID, invite components present, bare `/` never claimed,
   route not flag-gated. (Existing AASA tests in
   `test_account_data_rights.py` still pass.)
5. **Docs:** `docs/api-reference.md` AASA row updated; `docs/runbook.md` note
   on Apple CDN caching of AASA.

**Web fallback:** untouched. Users without the app still get the web landing
(`/` with referral capture in `web/js/app.js`; `/s/…` OG landing pages).

## Verification

- `python3 -m pytest backend/tests -q` → 1409 passed, 1 skipped.
- `cd mobile && npx tsc --noEmit` → clean.

## Operator actions outside the repo

1. **Deploy order matters:** push to `main` → Render deploy **before** building
   or installing the next iOS build. iOS validates the entitlement against the
   live AASA at install time; Apple's CDN can take up to ~24h to pick up the
   file, so deploy early. Sanity-check with an AASA validator (e.g. Branch's)
   against `https://fantasy-trade-finder.onrender.com/.well-known/apple-app-site-association`.
2. **Apple Developer portal:** confirm the Associated Domains capability is
   enabled on the `com.fantasytradefinder.app` identifier (EAS usually syncs
   capabilities automatically on the next build; if signing fails, toggle it
   in the portal). Verify team id `N5Y4N2Q49A` matches the account.
3. **No App Store ID exists in the repo** (app is TestFlight-only). The web
   landing pitches the product but has no `apps.apple.com` link to preserve.
   When the app ships publicly, add the App Store link to the landing page —
   universal links behavior itself does not depend on it.
4. **Device test after the new build:** send an invite link in iMessage and
   tap it — app opens (not Safari); long-press → "Open in [app]" appears.
   Note: pasting the URL directly into Safari's address bar intentionally
   does NOT open the app (Apple behavior); test from Messages/Notes.
