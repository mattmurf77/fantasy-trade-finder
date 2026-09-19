# #131 — Apple sign-in entitlement — mini-PRD

Feedback #131 (bug, app 1.7.2, tester mattmurf77): Apple sign-in errors on the
Sign-In screen and in Settings. Fast-track bug; Planner's plan: `plan.md` in
this folder. All file/line claims below re-verified against the working tree
on 2026-07-12.

**Root cause (verified):**
`mobile/ios/DTFDynastyTradeFinder/DTFDynastyTradeFinder.entitlements` — the
`<dict>` (lines 4–7) contains only `aps-environment`; there is no
`com.apple.developer.applesignin` key. This is a bare-workflow project:
`project.pbxproj` points both Debug (line 365) and Release (line 401) at this
one entitlements file, and `app.json`'s `"usesAppleSignIn": true` (line 20) +
`expo-apple-authentication` plugin (line 50) are prebuild-only no-ops that
never reach it. The binary is therefore signed without the Sign In with Apple
capability and `signInAsync()` rejects on device. Backend is not involved
(`backend/accounts.py:47` `APPLE_AUDIENCE = "com.fantasytradefinder.app"`
matches `PRODUCT_BUNDLE_IDENTIFIER`, pbxproj lines 385/416 — the call never
leaves the client).

## Requirements

### R-1 — Add the Sign In with Apple entitlement (THE fix)

File: `mobile/ios/DTFDynastyTradeFinder/DTFDynastyTradeFinder.entitlements`.
Add exactly these 4 lines inside the existing `<dict>`, alongside (not
replacing) `aps-environment`:

```xml
<key>com.apple.developer.applesignin</key>
<array>
  <string>Default</string>
</array>
```

Resulting dict body:

```xml
<dict>
  <key>aps-environment</key>
  <string>development</string>
  <key>com.apple.developer.applesignin</key>
  <array>
    <string>Default</string>
  </array>
</dict>
```

- `aps-environment` stays `development` in-source (export signing swaps it).
- One file covers Debug and Release (single `CODE_SIGN_ENTITLEMENTS`).
- Do NOT remove `usesAppleSignIn` / the plugin from `app.json`.

**Pass (mechanical):** `git diff` on the entitlements file is exactly the 4
added lines; `plutil -lint mobile/ios/DTFDynastyTradeFinder/DTFDynastyTradeFinder.entitlements`
exits 0.

### R-2 — Zero app-logic changes

No edits to `SignInScreen.tsx` / `SettingsScreen.tsx` handlers, `api/auth`,
or backend. The existing catch blocks (SignInScreen.tsx:141–144,
SettingsScreen.tsx:136–139) already suppress `ERR_REQUEST_CANCELED` and show
controlled surfaces; friendlier error copy is OUT (see reconciliation log,
OQ1).

**Pass (mechanical):** `git diff --stat` for this item touches only: the
entitlements file (R-1), `mobile/src/components/TopBar.tsx` (R-3, one testID
prop), the new Maestro flow (R-5), the testID registry doc (R-3),
`docs/runbook.md` (R-7), version carriers (R-6), and this item's own docs
folder `docs/feedback/items/131-apple-signin-error/*` (status.md, QA
findings — standard pipeline outputs). Nothing else.

### R-3 — Additive testIDs (test reachability only)

Both Apple buttons ALREADY have testIDs — do not add more:

- `signin.apple-btn` — `mobile/src/screens/SignInScreen.tsx:277`
- `settings.link-apple-btn` — `mobile/src/screens/SettingsScreen.tsx:536`

One genuinely missing id: the Settings gear in
`mobile/src/components/TopBar.tsx` (Pressable at ~line 70, currently only
`accessibilityLabel="Settings"`). Maestro conventions
(`docs/plans/mobile-testing/lld.md` §4.4 rule 1) ban tapping by text, so add:

```tsx
testID="topbar.settings"
```

on that Pressable — grammar-conformant (`topbar` is in the §Appendix-A screen
vocabulary; sibling ids `topbar.bell` are already reserved there). No layout,
style, or logic change.

Also register the three ids (`signin.apple-btn`, `settings.link-apple-btn`,
`topbar.settings`) in the registry at `mobile/src/components/CLAUDE.md`
(SignIn row is at line 36; the Apple ids are absent from it today), per the
LLD's "PRs adding screens add IDs" rule.

**Pass (mechanical):** TopBar diff is exactly one added prop line;
`grep -c "apple-btn" mobile/src/components/CLAUDE.md` ≥ 2.

### R-4 — Pinned failure-copy contract (no operator screenshot needed)

The pre-fix error text is pinned from the installed
`expo-apple-authentication@8.0.8` native source
(`mobile/node_modules/expo-apple-authentication/ios/AppleAuthenticationExceptions.swift`):

| ASAuthorizationError | JS `err.code` | `err.message` (exact) |
|---|---|---|
| `.unknown` (1000 — the entitlement failure) | `ERR_REQUEST_UNKNOWN` | `The authorization attempt failed for an unknown reason` |
| `.failed` (1004) | `ERR_REQUEST_FAILED` | `The authorization attempt failed` |
| `.canceled` (1001) | `ERR_REQUEST_CANCELED` | `The user canceled the authorization attempt` (suppressed by both catch blocks) |

No cause text is appended (`AppleAuthenticationRequest.swift:71` passes the
exception with no chained cause; expo-modules-core `Exception.description` =
the bare reason string). So the stable assertion substring covering both
failure codes is:

```
The authorization attempt failed
```

**Scoping (deliberate):** this guard covers ONLY `.unknown` (1000) and
`.failed` (1004). The other reasons (`.invalidResponse`, `.notHandled`,
`.notInteractive`) produce different copy and are intentionally outside the
net — the entitlement failure is deterministically code 1000, and this is an
entitlement-regression guard, not a general Apple-auth failure detector. Do
not widen the regex.

**Version pin:** these are expo-authored Swift literals (not Apple/OS
strings, not localized) pinned from `expo-apple-authentication@8.0.8`;
`package.json` floats `~8.0.8`, so re-verify
`AppleAuthenticationExceptions.swift` on any package upgrade. The R-5 flow
header and the R-7 runbook line both carry this pin.

**Pass (mechanical):** the Maestro flow in R-5 asserts on regex
`.*The authorization attempt failed.*` and that regex matches both pinned
strings above.

### R-5 — Maestro regression flow

New file `mobile/.maestro/flows/smoke/11-apple-entitlement.yaml` (next free
smoke number; conventions per `docs/plans/mobile-testing/lld.md` §4.4 —
header block, id-selectors for taps, text-matching only for load-bearing
copy asserts, `clearState`+`clearKeychain` first, `extendedWaitUntil` at
async boundaries, ends in `takeScreenshot`). `auth.accounts` is already true
in the `release` flag set (`backend/tests/fixtures/flags/release.json:42`,
mirroring `config/features.json:42`) and
`isAvailableAsync()` returns unconditionally `true` on iOS
(`AppleAuthenticationModule.swift:12–14`), so both buttons render in the
standard smoke cell with no flag pinning.

**Assertion design (Planner round-2 B-1/B-2, incorporated):**

- **Part 1 (Sign-In) is the regression sensor.** Its failure surface
  (`signin.error-text`) is persistent — it renders until the next attempt —
  so a negative assert against it is meaningful. The entitlement is
  binary-wide, so a regression detected here covers the Settings surface
  too.
- **Part 1 MUST include a bounded settle of ≥2 s between the tap and the
  negative asserts.** Pre-fix, the rejection → `setError` → re-render takes
  ~200–400 ms; without a settle, the negative asserts can evaluate before
  the error mounts and pass green on a regressed build. The reference
  mechanism below is a fixed-window probe: `extendedWaitUntil: visible` on
  the error regex with `optional: true` and a 3 s timeout — it returns
  early when the error appears (pre-fix → the following `assertNotVisible`
  reds) and waits out the full window when it never appears (post-fix →
  green). The QA agent may substitute an equivalent bounded-settle idiom
  accepted by the harness, but may NOT remove the settle, and the flow
  comment explaining it must be preserved verbatim so it isn't "optimized
  away" as a redundant wait.
- **Part 2 (Settings) is reachability-only — no failure-copy asserts.** The
  Settings failure surface is a warn toast that auto-dismisses ~1.7 s after
  appearing (`SettingsScreen.tsx:692–697` passes no `holdMs`; default
  `holdMs = 1500`, `mobile/src/components/Toast.tsx:30`), so any
  `notVisible` assert against it is structurally blind — on a regressed
  build the toast expires inside the assert window and the check passes
  green. Part 2 therefore only proves the link card renders and is
  tappable for the `standard` profile; regression sensing is Part 1's job.

Exact flow content:

```yaml
appId: com.fantasytradefinder.app
# tc: TC-131-APPLE-01 (feedback #131 — Apple sign-in entitlement regression guard)
# profile: standard
# flags: release
# Failure copy pinned from expo-apple-authentication@8.0.8
# (ios/AppleAuthenticationExceptions.swift) — re-verify the strings there on
# any package upgrade (package.json floats ~8.0.8). See PRD R-4.
tags: [smoke, signin, settings]
---
# ── Part 1: Sign-In screen (SignInScreen.tsx ~L276) — REGRESSION SENSOR ──
- launchApp:
    clearState: true
    clearKeychain: true
    stopApp: true
- extendedWaitUntil:
    visible:
      id: "signin.apple-btn"
    timeout: 15000
- assertNotVisible:
    id: "signin.error-text"
- tapOn:
    id: "signin.apple-btn"
# SETTLE — DO NOT REMOVE. Pre-fix, the native rejection takes ~200-400 ms to
# reach setError and re-render; asserting immediately after the tap would
# pass green on a broken build. This optional probe IS the mandated >=2 s
# bounded settle (PRD R-5): it returns early if the error copy appears
# (making the assertNotVisible below fail = regression caught) and waits the
# full 3 s when it never appears (fixed entitlement = green). A native Apple
# sheet appearing during the window = PASS (Maestro cannot drive it further).
- extendedWaitUntil:
    visible:
      text: ".*The authorization attempt failed.*"
    timeout: 3000
    optional: true
- assertNotVisible:
    text: ".*The authorization attempt failed.*"
- assertNotVisible:
    id: "signin.error-text"
- takeScreenshot: smoke-11a-apple-signin-no-error

# ── Part 2: Settings link row (SettingsScreen.tsx ~L535) ────────────────
# REACHABILITY ONLY — no failure-copy asserts here: the Settings failure
# surface is a warn toast that auto-dismisses in ~1.7 s (Toast.tsx holdMs
# default 1500), so a notVisible assert can never catch a regression on
# this surface. The entitlement is binary-wide; Part 1 is the sensor.
# Relaunch (state kept — still signed out) to dismiss any native sheet.
- launchApp:
    stopApp: true
- extendedWaitUntil:
    visible:
      id: "signin.username-input"
    timeout: 15000
- tapOn:
    id: "signin.username-input"
- inputText: "qa_standard"
- tapOn:
    id: "signin.continue-btn"
- extendedWaitUntil:
    visible:
      id: "leagues.row.990000000000000001"
    timeout: 30000
- tapOn:
    id: "leagues.row.990000000000000001"
- extendedWaitUntil:
    visible:
      id: "tab.trades"
    timeout: 30000
- tapOn:
    id: "topbar.settings"
- waitForAnimationToEnd
- extendedWaitUntil:
    visible:
      id: "settings.link-apple-btn"
    timeout: 15000
- tapOn:
    id: "settings.link-apple-btn"
- takeScreenshot: smoke-11b-apple-settings-link-reachable
```

Notes for QA:
- Part 2 works on the `standard` profile because `qa_standard` is a
  Sleeper-keyed session with no Apple identity → the link card renders
  (gate at SettingsScreen.tsx:528: `accountQuery.data && !hasAppleIdentity
  && appleAvailable`).
- **Known flake surface (Part 1):** post-fix, a simulator runtime with no
  Apple ID signed in may still reject code 1000 instead of showing the
  sheet (runtime-dependent). If Part 1 reds while the R-8 codesign
  checkpoint passes, the failure is environmental — quarantine per LLD §4.2
  ledger policy; the entitlement ground truth is R-8, not this flow.
- Pre-fix behavior note: the button rendering and then erroring IS the
  expected broken state on builds 40/41 — don't file "button shouldn't
  render".

**Pass (mechanical):** flow exits green in the smoke matrix; both screenshots
produced; the shipped flow file contains the Part 1 settle step (bounded
≥2 s) with its DO-NOT-REMOVE comment, and Part 2 contains no failure-copy
asserts.

### R-6 — Version bump to 1.7.3 (batch-coordinated)

Marketing version 1.7.2 lives in THREE places (plan listed two; third found
during verification):

- `mobile/app.json:5` (`"version": "1.7.2"`)
- `mobile/ios/DTFDynastyTradeFinder/Info.plist:22` (`CFBundleShortVersionString` — literal, not `$(MARKETING_VERSION)`)
- `mobile/ios/DTFDynastyTradeFinder.xcodeproj/project.pbxproj` `MARKETING_VERSION` lines 378 and 409 (Debug + Release)

Bump all four occurrences together. Build number is EAS-remote-owned
(`mobile/eas.json`: `appVersionSource: "remote"`, production
`autoIncrement: true`) — do NOT hand-edit it. The batch orchestrator owns
final version/build sequencing across G1 (see reconciliation log OQ3);
treat 1.7.3 as the default, not a hard assumption.

**Pass (mechanical):** `grep -rn "1\.7\.2" mobile/app.json mobile/ios/DTFDynastyTradeFinder/Info.plist mobile/ios/DTFDynastyTradeFinder.xcodeproj/project.pbxproj` returns no version-string hits after the bump.

### R-7 — Runbook entry (bare-workflow gotcha)

Add to `docs/runbook.md`: in this repo's bare workflow (`mobile/ios/`
tracked, no `expo prebuild`), `app.json` iOS config plugins and
`ios.usesAppleSignIn` are silently ignored at build time — native
`mobile/ios/` files (entitlements, Info.plist) are the source of truth.
Cite #131 as the incident. (Plan's config-drift sweep found the Apple
entitlement to be the only drift.) Include one line on the pinned failure
copy: the Maestro guard's strings come from
`expo-apple-authentication@8.0.8` (`AppleAuthenticationExceptions.swift`)
and must be re-verified when that package is upgraded (`package.json`
floats `~8.0.8`).

**Pass (mechanical):** runbook diff contains the entry referencing #131,
the entitlements file path, and the `expo-apple-authentication@8.0.8` pin
line.

### R-8 — Signed-artifact entitlement checkpoint (pre-TestFlight gate)

Before submitting the EAS production build to TestFlight, verify the actual
signed binary:

```bash
# <ipa> = the EAS production artifact
unzip -q <ipa> -d /tmp/ftf-131-ipa
codesign -d --entitlements :- "/tmp/ftf-131-ipa/Payload/DTFDynastyTradeFinder.app" \
  | grep -A 2 "com.apple.developer.applesignin"
```

**Pass (mechanical):** output contains the
`com.apple.developer.applesignin` key with `<string>Default</string>` in its
array. (In the store-signed artifact `aps-environment` should read
`production` — expected, do not "fix".) Also confirm the regenerated EAS
provisioning profile lists Sign In with Apple (build log credential summary
or `eas credentials -p ios`); if the old build-40/41 profile is reused,
signing fails or the error persists — regenerate via `eas credentials`.

### R-9 — Manual on-device operator checkpoint (final proof)

Maestro cannot complete the Apple sheet (needs a real Apple ID) and cannot
attest the store-signed binary's runtime behavior. Operator, on a physical
device with build ≥42 from TestFlight:

1. Signed out → Sign-In screen → tap "Sign in with Apple" → native sheet
   completes → lands in the app (account-only or linked path). No inline
   error under the form.
2. Settings → Account → "Link Apple" (Sleeper session with no Apple
   identity) → sheet completes → toast "Apple ID linked — your account is
   verified." + verified status row.

**Pass:** operator confirms both, recorded in this folder's status.md.
Release note / #131 feedback reply: "fixed in build ≥42 — update via
TestFlight" (testers on 40/41 will still see the error).

## Success criteria (summary)

1. R-1 diff is exactly the 4-line plist addition; plutil lint clean.
2. R-8 codesign output shows `com.apple.developer.applesignin` = `[Default]`
   in the shipped artifact.
3. New Maestro flow green; existing smoke suite
   (`mobile/.maestro/flows/smoke/01`–`10`) green — entitlement edit broke
   nothing else.
4. R-9 both operator checks pass on device.
5. Docs (runbook + testID registry) updated; version carriers consistent.

## Out of scope

- Friendlier / mapped error copy in either catch block (OQ1 — OUT; see
  reconciliation log).
- Any backend, web, or extension change.
- Removing `usesAppleSignIn` / the plugin from `app.json` (kept as declared
  intent for a future prebuild).
- Any other testID backfill beyond the three ids in R-3.
- Google sign-in surfaces, ESPN linking, account-state matrix changes (P2.7
  behavior is correct and untouched).

## Guardrails

- The entitlements plist edit is signing-critical for the whole app: exactly
  one added key, `aps-environment` byte-untouched, no whitespace/DOCTYPE
  churn. Diff must be the 4 lines in R-1, nothing else.
- No OTA/JS-only delivery path exists for this fix — it ships only in a
  freshly signed binary. Don't mark #131 resolved until R-8 + R-9 pass.
- TopBar edit: one prop, no reordering, no style changes — TopBar renders on
  every authed screen; blast radius must stay zero.
- Respect the SettingsScreen P2.7 account-state matrix: no logic edits there.
