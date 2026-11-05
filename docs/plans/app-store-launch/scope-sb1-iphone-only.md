# Feature Scope — SB-1: ship iPhone-only

**Date:** 2026-10-23
**Entry point:** direct ask. The operator answered SB-1 with "Sb1 iphone only: Yes", relayed by head-eng for the
2026-11-18 App Store launch (`docs/plans/org-bringup/launch-plan-1118.md`, the 11-06 binary cutoff).
**Builder:** `distribution-lead`
**Operator sign-off on waivers:** waivers are listed below (§1, the HLD/LLD rows). They're surfaced to the operator
with the push request.

**What changes:** the app stops declaring iPad as a supported device.
- `mobile/ios/DTFDynastyTradeFinder.xcodeproj/project.pbxproj`: `TARGETED_DEVICE_FAMILY` changes from `"1,2"` to
  `1` in the app target's Debug and Release configurations. This is the setting that ships; it's a bare workflow,
  so G-013 applies.
- `mobile/app.json`: `ios.supportsTablet` changes from `true` to `false`. It's a mirror, so a future
  `expo prebuild` can't regenerate `"1,2"`.

**Why:** with iPad in the device family, App Store Connect requires 13" iPad screenshots, and the review can run on
iPad (launch-readiness L6). No iPad layout pass has been done.

**User effect:**
- iPhone: no change.
- On an iPad, the App Store lists Fleeced as an iPhone app, and it runs in iPhone compatibility mode.
- `UISupportedInterfaceOrientations~ipad` stays in Info.plist. It's ignored on an iPhone-only binary and
  harmless; removing it is unrelated cleanup.
- **Apple constraint, to confirm on the first upload:** App Store Connect rejects a build that drops devices the
  *previously released* version supported. No version has ever been released (TestFlight only), so the upload
  should pass. Confirm it on the 11-07 TestFlight build's submission log. If the upload is rejected, revert before
  the 11-10 release build. After the first App Store release, this change can't be made cheaply.

---

## 1. Analytics scope

- [x] **(c) WAIVED. No analytics needed:** no new surface or event. iPad users were never a tracked segment, and
  `X-Device` already records device type if that question ever comes up.

## 2. Schema & flag scope

- New or changed tables or columns: none.
- New or changed feature flags: none. A build setting can't be flagged. The rollback is a revert commit plus a
  rebuild, possible only until the first App Store release with iPhone-only.
- New env vars or `model_config` keys: none.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-iphone-only.js` (`npm run test:iphone-only`). It pins
  `supportsTablet` as false and every `TARGETED_DEVICE_FAMILY` as `1`, and fails if no device family is set or if
  Info.plist adds a `UIDeviceFamily` containing 2. It's dependency-free and CI runs it (`ci.yml` loops over
  `tests/check-*.js`). Sabotage-tested three ways ("1,2" restored, `supportsTablet` true, the pin removed); each
  fails the check.
- [x] **Unit tests:** none. No backend change. `test_app_version_consistency.py` reads app.json and is unaffected
  (version keys unchanged).
- [x] **Code-walk proof:**
  - The two edited lines are the only `TARGETED_DEVICE_FAMILY` settings in the project. They're in the app target's
    `XCBuildConfiguration` blocks named Debug and Release; the project-level blocks don't set it.
  - Info.plist has no `UIDeviceFamily` key, so Xcode derives it from the build setting.
  - EAS builds the native project as-is ("an ios directory was detected", build 167's log).
- [x] **Manual TestFlight checklist** for the next main build (operator):
  1. In App Store Connect → TestFlight → the new build → Build Metadata, the supported devices list iPhone only
     `[verify on screen]`.
  2. On an iPhone, install from TestFlight, launch, and sign in. Expected: identical to the previous build.
  3. Optional, on an iPad with TestFlight: the app installs as an iPhone app (letterboxed or scaled). Expected: it
     launches and works.
- [ ] **WAIVED:** —
- `testID`s added or renamed: none.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route change |
| `living-memory/LLD.md` | n/a | no schema, route or invariant convention shifted |
| `docs/architecture.md` | n/a | no module or data-flow change |
| `living-memory/HLD.md` | n/a | no architecture shift; a client's device target isn't an architecture change |
| `docs/cross-client-invariants.md` | n/a | no shared constant |
| `docs/glossary.md` | n/a | no new term |
| ADR or `DECISIONS.md` entry | **owed** | Record "iPhone-only at launch (SB-1)" as a D- entry. That's living-memory, so release-lead's scribe writes it at landing. |

## 5. Ship gate declaration

- **CI green:** required on the pushed sha (backend-tests, mobile-typecheck with the `check-*.js` suites, testid-lint).
- **Evidence recorded:** TEST_LEDGER line for release-lead: `2026-10-23 — SB-1 iPhone-only: check-iphone-only.js
  green + 3 sabotages; TestFlight steps 1–3 owed on the next main build`.
- **TestFlight verification:** §3 steps 1–3, run by the operator on the next main build (11-07 to 11-09).
- Express lane declared by the operator? No. Full gates.
