# Claude-Driven Mobile App Testing — Plan (2026-07-09, rev 2)

*Set up the FTF iOS app (`mobile/`, Expo RN, prebuilt native project at `mobile/ios/DTFDynastyTradeFinder.xcworkspace`) for Claude-driven UX/UI functional testing **at scale** before rollout. Rev 2 replaces the original XCUITest-centered draft with a three-layer pyramid: **Maestro flows on simulators** (scale) → **the same flows against a release build** (TestFlight-equivalent binary) → **Claude driving the actual TestFlight app on a real iPhone via iPhone Mirroring** (capstone). Planning doc — no code yet. Grounded in `trade-engine-v2`.*

---

## Why this shape (decision record)

- **No tool can attach automation to a TestFlight-installed app.** XCUITest requires building from source with a test runner; a TestFlight binary is release-signed and manual-only. "Automate the actual TestFlight app" therefore narrows to vision-driven control of a real phone — possible (Layer 3) but serial and slow, so it can't be the scale layer.
- **A release-configuration simulator build is functionally the TestFlight binary**: identical JS bundle, identical native code, identical backend calls. TestFlight only adds signing/entitlements, real push, and real-hardware rendering/perf — a thin layer covered by Layer 3.
- **Maestro over XCUITest** for the automated layers: YAML flows Claude authors in minutes, drives *any installed app* on the simulator (including release builds — no Xcode test target needed), survives `expo prebuild` (nothing lives in the Xcode project), parallelizes across simulators, and is the de facto RN standard. XCUITest's advantages (native `.xcresult` integration) don't pay for their maintenance cost in an Expo app. XCUITest remains the fallback if Maestro fights RN's New Architecture accessibility tree.
- **Scale = data states × flows × screen sizes**, in that order of importance for a trade app. Seeded backend fixtures (ranked/unranked opponents, empty/large leagues, odd rosters) do more work than device count.

## Current state (verified 2026-07-09)

| Fact | Detail |
|---|---|
| Native project | `mobile/ios/DTFDynastyTradeFinder.xcworkspace`, shared scheme `DTFDynastyTradeFinder`, CocoaPods installed |
| Test tooling | **None** — no Xcode test targets, no jest/detox/maestro in `mobile/package.json` |
| `testID` usage | **Zero** occurrences in `mobile/src` — no stable identifiers for any driver to key on |
| Toolchain | Xcode 26.4.1; simulators for iOS 18.4 + 26.4 incl. dedicated **FTF-iOS18** (`89EEFD08-…`); iPads available (`supportsTablet: true`) |
| API base URL | `expo.extra.apiBaseUrl` via `expo-constants` (`mobile/src/api/client.ts:66`), falls back to Render prod — **an unconfigured build talks to production** |
| Auth / writes | Sleeper-based login; Send-in-Sleeper performs a real outbound write |
| Distribution | EAS → TestFlight |

---

## Phase 0 — Foundations (prerequisite for every layer)

### 0.1 Stable identifiers (`testID`)

RN's `testID` maps to `accessibilityIdentifier` on iOS — exactly what Maestro's `id:` selector matches. Zero exist today.

- Convention: `screen.element` kebab-case (`trade-calc.give-picker`, `login.username-input`); record it in `mobile/src/components/CLAUDE.md`.
- Instrument in test-value order:
  1. Login screen (username input, submit)
  2. Tab bar items (all tabs)
  3. `TradeCalculatorScreen` — mode toggle (Consensus / Demo / In-league), side pickers, verdict area, Send-in-Sleeper button
  4. `InLeagueCalculator` — opponent rows (+ `has_rankings` badge), roster pickers
  5. Rankings/matchup cards + choice buttons
  6. Trade finder suggestion cards
- ~40–60 identifiers, additive props only. Watch RN container-accessibility quirks: a parent with `accessible={true}` (implicit on some touchables) hides children from the driver — budget debugging time on lists (`react-native-draggable-flatlist` especially).

### 0.2 Backend isolation + data-state fixtures

Automated runs must never touch Render prod. The iOS Simulator shares host loopback, so local Flask (`run.py`, :5000) is directly reachable.

- Add an `app.config.js` reading `FTF_API_BASE_URL` at build time into `expo.extra.apiBaseUrl`; test builds set `http://127.0.0.1:5000`.
- Build a **fixture seeding script** (`backend/tests/fixtures/seed_ui_test_db.py`) that produces a SQLite DB from a named **profile** — this is the scale axis that matters most:
  | Profile | Exercises |
  |---|---|
  | `standard` | 12-team league, opponent with `member_rankings`, opponent without | 
  | `empty-league` | league with no rankings anywhere → seed-fallback paths |
  | `large-league` | 32 rosters, deep benches → picker perf, pagination |
  | `sparse-roster` | opponents with few universal-pool-valued players → graceful-drop paths |
  | `superflex` / `1qb` | format-toggle verdict differences |
- Sleeper public reads (`mobile/src/api/sleeper.ts` direct calls): prefer routing test traffic through seeded local endpoints; where the app truly calls Sleeper directly, accept live public reads in Layer 1 and document the flake risk.

### 0.3 Safety rails

- **Send-in-Sleeper**: flows may assert the button's state/visibility but never complete a send. The fixture backend has no Sleeper write token, so an accidental tap fails closed. Layer 3 (real phone, real account) stops at the confirmation sheet — or uses a dedicated throwaway test league if we want one true end-to-end send verified manually.
- **Prod DB**: `ui-test.sh` refuses to run if the built app's `apiBaseUrl` resolves to `onrender.com`.

---

## Layer 1 — Maestro on simulators (the scale layer)

### 1.1 Setup

- Install Maestro CLI (`brew tap mobile-dev-inc/tap && brew install maestro` or the curl installer). No project dependency; flows are plain YAML in `mobile/.maestro/` (in git — survives `expo prebuild`).
- Hermetic app build: release-configuration simulator build so the JS bundle is embedded and no Metro process is needed:
  `xcodebuild -workspace mobile/ios/DTFDynastyTradeFinder.xcworkspace -scheme DTFDynastyTradeFinder -configuration Release -sdk iphonesimulator -derivedDataPath mobile/ios/build build` (with `FTF_API_BASE_URL` exported so the config plugin bakes in the local URL).
- `mobile/scripts/sim-run.sh`: build → `simctl boot` → `simctl install` → `simctl launch com.fantasytradefinder.app`, parameterized by simulator UDID and fixture profile (seeds DB + [re]starts Flask).

### 1.2 Flow suite

One YAML flow per user journey, keyed on Phase 0 identifiers, each ending in assertions + `takeScreenshot`:

| Flow | Asserts |
|---|---|
| `login.yaml` | fixture Sleeper username → lands on home tab |
| `tabs-render.yaml` | every tab renders without redbox; screenshot each |
| `calc-consensus.yaml` | assemble 2-for-1 → verdict renders with values |
| `calc-in-league-ranked.yaml` | ranked opponent → two-board verdict (`your_value_delta` / `their_value_delta` visible) |
| `calc-in-league-fallback.yaml` | unranked opponent → consensus-fallback copy shown |
| `send-in-sleeper-gate.yaml` | reach send confirmation → **stop**; assert link-state messaging |
| `rankings-matchup.yaml` | complete a 3-player matchup → Elo updates reflected |
| `trade-finder.yaml` | suggestions render from fixture league |
| `trends.yaml` | trends screen renders with fixture data |

Flow-authoring rules: `waitForAnimationToEnd` / explicit `extendedWaitUntil` everywhere (RN renders async); no coordinate taps — ids only; tag flows (`smoke`, `full`) so a quick pass is `maestro test --include-tags smoke .maestro/`.

### 1.3 Scale matrix

Run the suite as **flows × device sizes × fixture profiles**:

- Devices: FTF-iOS18 (iPhone 16 class, iOS 18.4), iPhone 17 Pro + iPhone 17e (iOS 26.4), iPhone 16e (small screen), iPad Pro 11" (tablet support is declared — currently untested).
- Parallelism: one `maestro test --device <udid>` process per booted simulator; Claude orchestrates the fan-out and aggregates JUnit output (`--format junit`) + screenshots into a single pass/fail report per run.
- Full matrix (9 flows × 5 devices × spot-checked profiles) is a Claude-runnable command: `mobile/scripts/ui-test.sh [--matrix full|smoke]`.

**Exit criteria:** from clean checkout, `ui-test.sh --matrix smoke` goes green in <15 min; `--matrix full` runs unattended and produces a screenshot-backed report; any covered regression turns it red.

## Layer 2 — Same flows, release build (TestFlight-equivalent)

Nothing new to author — this layer is a *configuration* of Layer 1, run before every EAS/TestFlight submit:

- Build exactly as 1.1 (Release config — already the TestFlight-equivalent JS bundle: no dev menu, no redbox, prod error handling via Sentry).
- Run the `full` matrix against it. Differences that only show here: minified-JS-only crashes, `__DEV__`-gated code paths, splash/startup timing.
- Gate: EAS submit waits for Layer 2 green. Manual invocation first; CI later if the repo grows CI.

**Exit criteria:** documented pre-TestFlight checklist where Layer 2 green is step 1.

## Layer 3 — Actual TestFlight app on a real iPhone (Claude via iPhone Mirroring)

The only layer that touches the true TestFlight artifact. Claude drives the phone through macOS iPhone Mirroring using computer-use tools — vision-based, serial, ~30–60 min per pass. Used as an exploratory UX capstone before each rollout, not as a regression engine.

### Needs from the operator (one-time)

- iPhone Mirroring enabled and paired (macOS Sequoia+ — this Mac qualifies); phone nearby, on Wi-Fi, locked.
- Current TestFlight build installed on the phone.
- Computer-use access granted to the iPhone Mirroring app when prompted.
- A decision on the Sleeper account: default is **stop at every send confirmation**; optionally provide a dedicated throwaway test league to verify one true end-to-end send.

### The pass (checklist, evolves per release)

1. Cold launch: splash → login with real Sleeper account; time-to-interactive feel.
2. Every Layer 1 smoke flow, executed by eye/tap on real hardware — watching for what simulators can't show: touch-target comfort, scroll feel, safe-area/notch issues, dark-mode rendering on OLED.
3. Real push notification receipt (`expo-notifications` — only verifiable here; simulators can't receive APNs).
4. Haptics fire where expected (`expo-haptics` — real device only).
5. Send-in-Sleeper up to the confirmation sheet with the real linked account (per safety rail).
6. Screenshot-backed UX judgment report: not just pass/fail, but "this feels off" findings ranked by severity.

**Exit criteria:** a written Layer 3 report per TestFlight build, filed alongside the release notes; rollout comfort = Layers 1–3 green plus human beta feedback from the TestFlight group.

---

## Rollout gate (what "comfortable rolling out" means)

1. Layer 1 `full` matrix green on the release candidate commit.
2. Layer 2 green on the actual EAS release build config.
3. Layer 3 report for the TestFlight build with no severity-1 findings.
4. No automated run wrote to Sleeper or touched Render prod (rails held).

## Decisions (defaults locked, alternatives recorded)

| Decision | Locked default | Fallback |
|---|---|---|
| Scale driver | Maestro (simulators) | XCUITest target (if Maestro can't see RN New-Arch elements) |
| Real-device/TestFlight testing | Claude + iPhone Mirroring | Appium/WDA tethered (heavy; only if mirroring proves unworkable) |
| Real-hardware scale | Skipped for now | BrowserStack/AWS Device Farm with the EAS `.ipa` (~$100+/mo) if hardware-specific bugs ever appear |
| Backend override | build-time `expo.extra` env | runtime launch argument |
| JS bundle for test runs | embedded (Release config) | live Metro (dev iteration only, never for the matrix) |

## Risks

- **RN New Architecture + accessibility tree**: some components hide children from drivers unless container accessibility is adjusted — the main threat to Maestro; mitigated by instrumenting + verifying one screen end-to-end (spike) before writing all 40–60 testIDs.
- **Maestro on iOS 26.4 simulators**: newest-OS driver support can lag; FTF-iOS18 (18.4) is the stable anchor — verify 26.4 in the spike.
- **Sleeper live reads** are non-deterministic — contained by fixture-first routing.
- **Simulator flake** — `ui-test.sh` does `simctl shutdown` + `erase` on the pinned device before retry.
- **iPhone Mirroring quirks**: some secure fields/DRM surfaces black out; session drops when the phone is picked up mid-pass. Layer 3 is judgment-driven, so Claude notes and works around rather than failing hard.

## Implementation order

1. **Spike (half day):** testIDs on `TradeCalculatorScreen` only → release sim build → one Maestro flow (`calc-consensus.yaml`) green on FTF-iOS18 and one iOS 26.4 device. Proves the whole stack before broad investment.
2. Phase 0 complete (all testIDs, `app.config.js` override, fixture profiles, rails).
3. Layer 1 suite + matrix scripts.
4. Layer 2 gate wired into the pre-TestFlight checklist.
5. Layer 3 first pass on the next TestFlight build.
