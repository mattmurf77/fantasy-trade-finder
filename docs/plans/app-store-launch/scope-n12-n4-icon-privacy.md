# Feature Scope — N12 square app icon + N4 privacy manifest

**Date:** 2026-10-23
**Entry point:** direct ask. head-eng assigned both for the 11-06 binary cutoff of the 2026-11-18 App Store launch
(`docs/plans/org-bringup/launch-plan-1118.md`). Full gates; a short scope note was allowed.
**Builder:** `distribution-lead`
**Operator sign-off on waivers:** the waivers below (§1, the doc rows) are surfaced with the push request.

## What changes

- **N12, the app icon.** Both icon files are replaced with design-lead's square master
  (`docs/design/app-icon/fleeced-app-icon-1024.png` on PR #358, sha256 `4cbc6939…`):
  - `mobile/assets/icon.png` (the Expo `icon` in app.json; the path is unchanged);
  - `mobile/ios/…/AppIcon.appiconset/App-Icon-1024x1024@1x.png` (what a bare build ships, G-013).

  The master is 1024×1024 sRGB RGB with no alpha. Only the four baked white corners were filled; iOS applies the
  corner mask itself. Side effect: `expo-notifications`' plugin icon (app.json :48) reads the same file, which
  matters only for Android notifications, and Android doesn't ship.
- **N4, the privacy manifest.** `ios/DTFDynastyTradeFinder/PrivacyInfo.xcprivacy` **already exists** on main and
  is in the app target's Resources build phase (`project.pbxproj` :14, :200). The audit found **no missing
  declaration**, so the manifest is unchanged and gets a pin.
  - **Audit (2026-10-23):** a scan of all 101 native podspec dirs in `node_modules` found these required-reason
    APIs in use: FileTimestamp, SystemBootTime, DiskSpace, UserDefaults. ActiveKeyboards isn't used.
  - Pods with no manifest of their own (`@react-native-cookies/cookies` UserDefaults, `expo-document-picker`
    FileTimestamp, RN `Settings`/`CoreModules` UserDefaults, `jsi` FileTimestamp) are covered by the app-level
    categories. `3B52.1` covers document-picker's user-selected files.
  - The app's own native code (`AppDelegate.swift`) calls none of these APIs.
  - Pods that do ship manifests are merged in at `pod install` by RN's aggregation (Podfile :52, on by default).
  - `NSPrivacyTracking` is false.
  - Not verifiable here: the Sentry Cocoa pod comes from CocoaPods trunk and ships its own manifest.

## 1. Analytics scope
- [x] **(c) WAIVED:** no new surface or event.

## 2. Schema & flag scope
- No tables, flags or env vars. Rollback: a revert commit plus a rebuild.

## 3. Evidence scope
- [x] **Structural guards** (CI runs both through the `tests/check-*.js` loop):
  - `mobile/tests/check-app-icon.js` (`npm run test:app-icon`). The Expo and native icons are byte-identical,
    1024×1024 8-bit RGB with no alpha and no tRNS (ITMS-90717), and no corner pixel is near-white. It's
    dependency-free and decodes the PNG with zlib. Three sabotages each fail it: the old cornered icon (corners
    253–255), one file swapped alone, a tRNS chunk added.
  - `mobile/tests/check-privacy-manifest.js` (`npm run test:privacy-manifest`). The file is in the Resources
    build phase; each of the four categories carries at least its audited reasons; `NSPrivacyTracking` is false;
    aggregation isn't disabled. Five sabotages each fail it: a reason dropped, a category dropped, the file
    removed from Resources, tracking true, aggregation off.
- [x] **Code-walk:** see the audit above.
- [x] **Manual TestFlight checklist** for the next main build (operator):
  1. On the iPhone home screen, the Fleeced icon is the full-bleed ram under iOS's rounded mask, with no white
     corner or light ring.
  2. In App Store Connect → TestFlight → the build, the build's icon shows the same square-art icon.
  3. After processing, Apple sends **no** "ITMS-91053: Missing API declaration" email for this build. If it
     does, forward the API category named in it to distribution-lead.
- `testID`s: none.

## 4. Docs scope
| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md`, `docs/architecture.md`, `living-memory/LLD.md`, `living-memory/HLD.md`, `docs/cross-client-invariants.md`, `docs/glossary.md` | n/a | no route, module, convention, constant or term change |
| ADR or `DECISIONS.md` | n/a | design-lead's #358 README records the icon decision |

**Collected data types, folded in 2026-10-24.** `NSPrivacyCollectedDataTypes` (empty before) now lists legal-lead's
R3-FINAL set exactly: Name, EmailAddress, CoarseLocation, CustomerSupport, OtherUserContent, UserID, DeviceID,
ProductInteraction, CrashData, PerformanceData, OtherDiagnosticData, OtherDataTypes.
- Each is linked and not used for tracking, with R3's purposes. There's no Purchases while the RevenueCat key is
  unset (R3 Q7).
- `check-privacy-manifest.js` now pins the set exactly. Five more sabotages each fail it: the old empty array, a
  type dropped, tracking true, an extra purpose, an undeclared PurchaseHistory.
- The R5 trigger applies: any R3 change updates the manifest, and the check's table, in the same commit.
- **2026-10-25, R28.2:** the paywall entered the launch binary (operator approved R1), so legal-lead's R28.2 adds
  **PurchaseHistory**: linked, not tracking, purposes App Functionality + Analytics (subscription events feed the
  K0–K3 metrics). The manifest and COLLECTED now hold 13 types. Two sabotages each fail it: the row dropped, the
  Analytics purpose dropped. RevenueCat's own SDK manifest stays alongside it. The app calls no RevenueCat
  device-identifier or attribution API (no `collectDeviceIdentifiers` / `enableAdServicesAttributionTokenCollection`
  in `mobile/src`).
- The code-vs-label diff found no mismatch:
  - Name: `api/auth.ts:99-102` forwards Apple's first-sign-in name; `users.display_name` holds Sleeper names.
  - Coarse Location: the time zone (`server.py:2905`, `notif.tz_sync`); also `user_events.country` from a CDN header
    (`analytics_ingest.py:379-384`), which is NULL on bare Render.
  - Search History really isn't collected: `analytics_taxonomy.py:281`, "the query string is never sent".

## 5. Ship gate declaration
- CI green on the pushed sha.
- TEST_LEDGER line for release-lead: `2026-10-23 — N12/N4: check-app-icon.js (3 sabotages) + check-privacy-manifest.js
  (5 sabotages) green; pod audit 101 podspecs, no missing category; TestFlight steps 1–3 owed`.
- Express: no.
