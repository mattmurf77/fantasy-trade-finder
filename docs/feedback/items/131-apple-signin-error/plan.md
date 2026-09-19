# #131 — Apple sign-in errors on Sign-In screen + Settings (fast-track bug)

Feedback #131 (bug, app 1.7.2, tester mattmurf77): "Getting an error both on
the Home Screen and settings page for Apple signin." "Home Screen" = the
sign-in landing screen (`SignInScreen`, first screen when signed out); there
is no `HomeScreen.tsx` — the Apple button renders in exactly two places,
matching the report:

- `mobile/src/screens/SignInScreen.tsx` (~line 276, primary portal, P2.6)
- `mobile/src/screens/SettingsScreen.tsx` (~line 535, account-linking row, P2.7)

## Problem statement (root cause — verified)

**The iOS binary is signed without the Sign In with Apple entitlement.**

This is a **bare workflow** project (`mobile/ios/` is tracked in git;
`project.pbxproj` sets `CODE_SIGN_ENTITLEMENTS =
DTFDynastyTradeFinder/DTFDynastyTradeFinder.entitlements` for both Debug and
Release). In bare workflow, **Expo config plugins and `ios.usesAppleSignIn`
in `app.json` are silently ignored at build time** — they only act during
`expo prebuild`, which we don't run. So although `app.json` declares:

- `"usesAppleSignIn": true`
- plugin `"expo-apple-authentication"`

…the native entitlements file contains **only** `aps-environment`:

```xml
<dict>
  <key>aps-environment</key>
  <string>development</string>
</dict>
```

There is no `com.apple.developer.applesignin` key. TestFlight builds 40/41
were therefore signed without the capability, and
`AppleAuthentication.signInAsync()` throws on device
(ASAuthorizationError, typically code 1000 "unknown" — surfaced as the
raw native message).

Why the button still rendered before erroring: `isAvailableAsync()` returns
true on-device on iOS 13+ regardless of the entitlement (it checks OS
support, not signing). Both screens gate the button on it, so the button
appears, the tap calls `signInAsync`, and the throw lands in the existing
catch blocks:

- SignInScreen: `setError(err?.message || 'Apple sign-in failed. Try again.')`
  → inline error text under the form.
- SettingsScreen: `setToast({ msg: err?.message || "Couldn't link Apple — try
  again.", tone: 'warn' })` → warn toast.

So the tester saw **our own error surfaces carrying the raw native message**
(not a crash, not an unhandled dialog). The P2.7 error handling worked as
designed; the failure is upstream of it.

**Backend is NOT suspect** (verified): `backend/accounts.py` expects
`aud == "com.fantasytradefinder.app"` (`APPLE_AUDIENCE`, line 47) and the
native `PRODUCT_BUNDLE_IDENTIFIER` is `com.fantasytradefinder.app`. No
request ever reaches the backend — `signInAsync` fails client-side.

### Config-drift sweep (anything else silently ignored in bare workflow?)

Checked every `app.json` iOS-relevant knob against the native project:

| app.json | Native state | Drift? |
|---|---|---|
| `usesAppleSignIn` / `expo-apple-authentication` plugin | entitlement **missing** | **YES — the bug** |
| `expo-notifications` plugin | `aps-environment` present; `UIBackgroundModes: [remote-notification]` in Info.plist | no |
| `ios.infoPlist.ITSAppUsesNonExemptEncryption: false` | present in Info.plist | no |
| `scheme: "dtf"` | `CFBundleURLSchemes` contains `dtf` | no |
| `version: 1.7.2` | `CFBundleShortVersionString` 1.7.2 | no |
| `expo-secure-store`, `expo-font`, Sentry plugin | no entitlements needed; `ios/sentry.properties` exists | no |

The Apple entitlement is the **only** drift. (`app.config.js` only layers
test-harness `extra` values; it doesn't touch iOS config.)

## Approach

**One surgical edit** to the native entitlements plist — add the Sign In
with Apple key alongside the existing aps-environment key:

```xml
<key>com.apple.developer.applesignin</key>
<array>
  <string>Default</string>
</array>
```

- File: `mobile/ios/DTFDynastyTradeFinder/DTFDynastyTradeFinder.entitlements`
- Both build configs point at this one file, so a single edit covers
  Debug and Release.
- Do **not** touch `aps-environment` ("development" is correct in-source;
  signing swaps it to production at App Store export).
- Do **not** remove `usesAppleSignIn` / the plugin from `app.json` — they're
  harmless, and they keep intent declared if the project ever prebuilds.

Then: version bump (1.7.3), EAS production build, TestFlight. The build is
the actual fix delivery — no JS change is required to fix the bug.

**Client error-copy touch: recommend NOT in scope.** The existing catch
blocks (P2.7) already suppress cancels (`ERR_REQUEST_CANCELED`) and show a
message on our own surfaces; the root-cause fix makes the entitlement error
unreachable. Mapping ASAuthorization "unknown" codes to friendlier copy is
speculative hardening against a config error we're fixing — flagged as an
open question for the Author, default skip (simplicity-first).

## Platforms touched

- **Mobile (iOS native config) only.** No backend, web, or extension changes.
- Ship vehicle: new TestFlight build (entitlement changes only take effect
  in a freshly signed binary — no OTA/JS-only path can deliver this fix).

## Risks

1. **EAS provisioning profile must pick up the capability.** The operator
   has enabled Sign In with Apple on the App ID in the developer portal.
   The EAS-managed provisioning profile from builds 40/41 predates that and
   won't include the capability; `eas build` normally detects the
   entitlement/profile mismatch and regenerates automatically. If signing
   fails or the error persists in build 42, run `eas credentials -p ios`
   and sync/regenerate the profile. **Checkpoint:** in the build logs (or
   `eas credentials`), confirm the profile lists Sign In with Apple before
   submitting to TestFlight.
2. **Entitlements edits affect code signing for the whole app.** Keep the
   plist edit to exactly one added key; any stray change to
   `aps-environment` or plist structure can break push notifications or
   signing for all targets. Diff must be the 4 lines above, nothing else.
3. **Verification ceiling in simulator/Maestro** (see below) — final proof
   is on-device only. Mitigate with an explicit operator checkpoint.
4. **Stale binary confusion:** testers on build 40/41 will still see the
   error after the fix ships. Release note / feedback reply should say
   "fixed in build ≥42, update via TestFlight."

## Verification plan

**What Maestro CAN regress (simulator):**
- Sign-in screen: `signin.apple-btn` (testID exists) renders when
  `auth.accounts` is on.
- Settings: the Apple link button renders for an unverified session
  (needs a testID if it lacks one — additive only).
- Tapping the button does **not** produce the pre-fix failure surfaces:
  SignInScreen inline error text / Settings warn toast containing the
  native failure message. Pre-fix copy is the raw `err.message` — expected
  to be Apple's code-1000 text ("The authorization attempt failed for an
  unknown reason" or similar); QA should pin the exact string from the
  operator's device before asserting on it (open question 2). A native
  Apple sheet appearing (which Maestro can't drive further) counts as PASS.
- Existing smoke suite (`mobile/.maestro/flows/smoke/01-signin.yaml` etc.)
  as regression that the entitlement edit broke nothing else.

**What Maestro CANNOT do:** complete the Apple sheet (requires a real
Apple ID; impossible headlessly in simulator) and prove the signed-binary
entitlement. **Manual on-device checkpoint (operator, build ≥42 via
TestFlight):**
1. Signed-out → Sign-In screen → tap Sign in with Apple → sheet completes →
   lands in app (account-only or linked path).
2. Settings → Account → Link Apple → sheet completes → "Apple ID linked —
   your account is verified." toast + verified status row.

**Pre-fix behavior note for QA:** the button rendering and then erroring IS
the expected broken state on builds 40/41 (`isAvailableAsync` true without
entitlement). Don't file "button shouldn't render" — post-fix the same
render path simply succeeds.

## File-ownership proposal

| File | Owner | Change |
|---|---|---|
| `mobile/ios/DTFDynastyTradeFinder/DTFDynastyTradeFinder.entitlements` | eng-mobile (build agent) | add `com.apple.developer.applesignin` = `[Default]` — the fix |
| `mobile/app.json` + `mobile/ios/DTFDynastyTradeFinder/Info.plist` | eng-mobile | version bump 1.7.3 only (both files carry the version) |
| `mobile/.maestro/flows/smoke/01-signin.yaml` (or new flow) | eng-qa | additive assertions per verification plan |
| `mobile/src/screens/SettingsScreen.tsx` | eng-qa (additive testID only, if needed) | testID on the Apple link button; NO logic changes — respect the P2.7 account-state matrix |
| `mobile/src/screens/SignInScreen.tsx` | (only if Author opts into friendlier copy — see OQ1) | additive catch-branch copy; otherwise untouched |
| `docs/runbook.md` | planner/build agent | record the bare-workflow gotcha: config plugins / `usesAppleSignIn` are no-ops; native `ios/` files are the source of truth for entitlements/Info.plist |
| `docs/feedback/items/131-apple-signin-error/` | pipeline | status.md, QA notes |

No file overlaps with other in-flight G1 items expected — entitlements plist
is touched by nothing else.

## Spike needs

None blocking. The root cause is confirmed statically. Optional 5-minute
check during build: after `eas build`, inspect the artifact's signed
entitlements (`codesign -d --entitlements :- <app>` on the .app, or the EAS
build log's credential summary) to confirm `com.apple.developer.applesignin`
is present before TestFlight submission — cheap, catches risk 1 early.

## Open questions for the Author

1. **Friendlier failure copy — in or out?** Plan defaults to OUT (root cause
   fix removes the error; current handling already shows a controlled
   message). If IN: additive-only mapping of non-cancel ASAuthorization
   errors to e.g. "Apple sign-in isn't available right now — try again
   later." in both screens' catch blocks; keep `err.message` in a Sentry
   breadcrumb so diagnosis isn't lost.
2. **Exact pre-fix error copy:** can the operator screenshot the error on
   Sign-In and Settings (build 40/41) before updating? Pins the exact string
   for the Maestro "must not appear" assertion and closes the loop on what
   the tester saw.
3. **Build number confirmation:** plan assumes next EAS production build
   (autoIncrement) is #42 and ships as 1.7.3 — confirm no other item in this
   batch is bundling into the same build (if so, coordinate one bump).
