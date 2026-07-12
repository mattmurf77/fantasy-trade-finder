# QA round 1 — agent A — 2026-07-12

## Summary: FAIL (7 findings)

Batch under test: #126 verify-persistence, #131 apple-entitlement, plus built items #127/#130/#134/#135/#136. All five built items' surfaces PASS as observed. Backend suites fully green (578 tests total across the two runs reported below). The FAIL verdict is carried by: the entire standing legacy smoke suite failing on stale selectors (F-1..F-3, brittle tests — the underlying app behavior passes via ad-hoc equivalents), flow 11 Part 2 failing on a sim-environment surface (F-4, [SIM-ENV-SUSPECT]), the #131 version bump not yet applied (F-5, sequencing), a #126 test-plan coverage deviation (F-6), and one new sim-observed UI defect in the ESPN link sheet (F-7).

## Environment

- Simulator: FTF-iOS18 (89EEFD08-1237-4CEB-8583-30AAF44419AD), iOS 18.4, booted; merged hermetic Release build pre-installed (orchestrator-prepared). No signed-in Apple ID on the sim (relevant to F-4).
- App: com.fantasytradefinder.app; embedded `apiBaseUrl http://127.0.0.1:5001`, `testMode: true` (verified from `mobile/ios/build/resolved-config.json`). Marketing version **1.7.2** (see F-5). Sim binary signs with an **empty entitlements dict** (ad-hoc sim signing, confirmed via `codesign -d --entitlements`) — per orchestrator adjudication, device-artifact codesign is entitlement ground truth.
- Branch: `trade-engine-v2` @ c7a8b88 + uncommitted batch working tree.
- Maestro 2.5.1 (JAVA_HOME per runbook). Backend: test-mode Flask on :5001, profile `standard`, seed 1337, seeded via `backend/tests/fixtures/seed_ui_test_db.py`; sim-run.sh's env replicated exactly (port killed first, seed, then Flask; whoami pid handshake verified both sessions). Flags: pure `release` set for flow 11 and all item checks; legacy 01–06 additionally run with `landing.try_before_sync=true` overridden ON (see F-2 — the flag is OFF in the release set, so the flows cannot start without it).
- Rails audit at end of runs: `vcr_misses=0, sleeper_live_egress_attempts=0, completed_proposes=0` — clean.
- Fixture DB note: for the #126 R-6/R-7 checks I set `users.verified_via='sleeper'` for qa_standard directly in `data/ui-test/standard.db` (verified-controller state is not otherwise reachable on sim — no injection route exists). DB re-seeded to pristine afterward.
- pytest: `backend/tests/test_verified_sessions.py -q` → **20 passed** (0.70s). Full `backend/tests/ -q` → **558 passed** (6.40s). `test_dp_crosswalk_position.py` alone → 4 passed.
- Ad-hoc scratch flows + full Maestro/Flask/pytest logs preserved at `feedback-workspace/126/qa-round-1-agent-A/` (nothing added to `mobile/.maestro/`). Screenshots in `mobile/.maestro/screenshots/`; Maestro failure artifacts in `~/.maestro/tests/2026-07-12_*/`.

## Results

| Test | Verdict | Evidence |
|---|---|---|
| smoke 01-launch (legacy) | FAIL → F-1 | `~/.maestro/tests/2026-07-12_124336/` (screen renders; "Connect" text no longer exists) |
| smoke 02-demo-session (legacy) | FAIL → F-2 | maestro-02-demo-session.log |
| smoke 03-tiers-render (legacy) | FAIL → F-2 | maestro-03-tiers-render.log |
| smoke 04-tabs-navigation (legacy) | FAIL → F-2 | maestro-04-tabs-navigation.log |
| smoke 05-feedback-capture (legacy) | FAIL → F-2, F-3 | maestro-05-feedback-capture.log |
| smoke 06-tiers-drag-no-crash (legacy) | FAIL → F-2 | maestro-06-tiers-drag-no-crash.log |
| ad-hoc equivalent: demo bootstrap + tabs cycle (02+04 content) | PASS | adhoc-A-demo-main-tabs.png, adhoc-A-tab-{matches,league,trades}.png |
| ad-hoc equivalent: Tiers render + drag-release no crash (03+06 content) | PASS | adhoc-B-tiers-header-135.png, adhoc-B-tiers-after-drag.png |
| ad-hoc equivalent: feedback capture save (05 content) | PASS | adhoc-C2-feedback-saved.png |
| #131 flow 11 Part 1 (regression sensor, official file unmodified) | PASS | smoke-11a-apple-signin-no-error.png; no ".*The authorization attempt failed.*", no `signin.error-text` after tap + 3s bounded settle |
| #131 flow 11 Part 2 (Settings reachability) | FAIL [SIM-ENV-SUSPECT] → F-4 | `~/.maestro/tests/2026-07-12_125836/` |
| #131 R-1 entitlements diff exactly 4 lines + `plutil -lint` OK | PASS | git diff; plutil "OK" |
| #131 R-3 TopBar diff = 1 prop; `grep -c apple-btn` registry = 2 | PASS | git diff mobile/src/components/TopBar.tsx |
| #131 R-4 flow regex matches both pinned strings | PASS | `.*The authorization attempt failed.*` covers both R-4 rows by inspection |
| #131 R-6 version bump (4 carriers) | FAIL (open) → F-5 | grep shows 1.7.2 in all four carriers |
| #131 R-7 runbook entry (bare-workflow + copy pin) | PASS | docs/runbook.md "Bare workflow…(feedback #131, 2026-07-12)" section present incl. 8.0.8 pin line |
| #131 R-8 signed-artifact codesign checkpoint | BLOCKED — no EAS production ipa available in this environment; sim binary signs with empty entitlements by design (not ground truth) | codesign output in Environment |
| #131 R-9 on-device operator checkpoint | BLOCKED — requires physical device + TestFlight build ≥42 + real Apple ID (PRD R-9) | — |
| #126 pytest pins (`test_verified_sessions.py`) | PASS (20/20) with coverage deviation → F-6 | pytest-126.log |
| #126 R-6 banner copy (verified controller + fresh unverified session) | PASS | adhoc-H-verify-banner-r6.png — exact new copy, old "another device" copy absent, `main.verify-banner` present |
| #126 R-7 ESPN sheet gate-403 mapping | PASS (with F-7 en route) | adhoc-I-espn-mapped-403-r7.png — "Verify your account to link a league." shown; raw `verification_required` absent; Flask log AUTH-DENY + 403 on POST /api/espn/link |
| #126 R-1/R-2 Keychain persist + silent replay behavior | BLOCKED — needs a real Sleeper login (WebView capture can't be automated) and Keychain persistence across reinstall isn't exercisable in Maestro; PRD §4 "Maestro / client-visible" designates the manual operator checkpoint (steps 1–4 there) as the coverage | PRD §4 |
| #126 R-5 disconnect clears local copy | BLOCKED — same dependency (no real captured token on sim) | PRD §4 |
| #135 Tiers header reads "Tiers" (not "Positional Tiers") | PASS | adhoc-B-tiers-header-135.png; assertNotVisible "Positional Tiers" green |
| #134 top-tier scale pill row ABSENT on Anchors | PASS | adhoc-D-anchors-no-pill-134.png; "A top-tier asset is worth" not visible (4s settle probe never saw ".*top-tier asset.*") |
| #130 Settings close button + ESPN row; close dismisses | PASS | adhoc-E-settings-espn-row-130.png (X + "LINK AN ESPN LEAGUE" row), adhoc-E-settings-dismissed-130.png |
| #127 exactly one Kenneth Walker, at RB, in QuickSet/Tiers pool | PASS | UI: adhoc-G1f-kw-on-rb-127.png (RB tab, "1st" band, RB11, single row, KC); WR-absence: full-scroll `scrollUntilVisible "Kenneth Walker"` on WR tab found nothing (expected fail, maestro-adhoc-G2.log); data: fixture DB has only player_id 8151 (RB) named Kenneth Walker, in both formats' rankings; backend `test_dp_crosswalk_position.py` 4 passed |
| #136 Quick Rank: `rankmenu.quickrank` reachable; walk renders; tap stamps numeral; Save advances | PASS | adhoc-F-rankmenu-quickrank-136.png, adhoc-F-quickrank-walk-136.png ("3 1STS · TIER 1 OF 7"), adhoc-F-quickrank-stamped-136.png (Mahomes badge "1", "Save 3 1sts (1/6)"), adhoc-F-quickrank-advanced-136.png ("Tier 2 of…") |
| Full backend suite `python3 -m pytest backend/tests/ -q` | PASS — **558 passed, 0 failed** | pytest-full.log |

## Findings

### F-1: legacy smoke 01-launch asserts stale copy "Connect"
- Severity: minor (brittle test — app renders correctly)
- Repro: `maestro --device <UDID> test mobile/.maestro/01-launch.yaml`
- Expected (flow) "Connect" visible vs actual: sign-in screen now reads "Sign in with Apple" / "Continue with Sleeper →" (account-first redesign, 1.7.x); "Dynasty Fantasy Football" assert still passes. App boot itself is healthy.
- Evidence: `~/.maestro/tests/2026-07-12_124336/screenshot-❌-*.png`
- Suspicion for resolution: selector update needed, not an app fix. Do NOT loosen; per README, update the matcher.

### F-2: legacy smoke 02–06 cannot start — demo CTA selector stale twice over
- Severity: minor (brittle tests) with one doc-rot note
- Repro: any of 02–06; they all tap text "Try the app on a sample league".
- Expected vs actual: (a) the gate flag `landing.try_before_sync` is **false** in the shipped release flag set (`backend/tests/fixtures/flags/release.json` mirroring `config/features.json`) — the 02-yaml comment "it is in config/features.json" is stale, so under release flags the CTA doesn't render at all; (b) even with the flag forced on, the visible text is "Try the app on a sample league →" (trailing arrow) and Maestro's full-regex text match misses it. With the flag overridden on and id `signin.demo-link` used instead, the entire 02–06 regression content passes (see ad-hoc equivalents).
- Evidence: maestro-0{2..6}-*.log; adhoc-A/B/C2 screenshots; `/api/feature-flags` round-trip in flask-legacy.log.

### F-3: legacy smoke 05's remaining selectors also stale (emoji removed)
- Severity: minor (brittle test)
- Repro: 05-feedback-capture.yaml steps after demo bootstrap.
- Expected vs actual: FAB is no longer text "📝" — it is an Icon (flag) Pressable with `accessibilityLabel="Capture feedback"` and **no testID** (`mobile/src/components/FeedbackFAB.tsx:42-47`); category chips are now "Bug"/"Polish"/"Idea" (no 💡); and the flow's final `assertNotVisible: "Capture feedback"` would now false-fail on success because the FAB's accessibility label matches after the sheet closes. Capture itself works (adhoc-C2-feedback-saved.png). A `feedback.fab` testID is the obvious registry addition — flagged here per the report-only rule.

### F-4: flow 11 Part 2 blocked by a persistent OS alert on a sim with no Apple ID [SIM-ENV-SUSPECT]
- Severity: minor (environment/flow-design surface; the regression sensor — Part 1 — is green)
- Repro: run `mobile/.maestro/flows/smoke/11-apple-entitlement.yaml` on FTF-iOS18 with no Apple Account signed in. Part 1 taps `signin.apple-btn`; instead of the pinned failure copy (which would indicate the entitlement regression) iOS raises the **system alert "Sign in to your Apple Account — You need to sign in to your Apple Account in Settings."** Part 1's asserts correctly pass (no pinned copy, no `signin.error-text` — the flow comment explicitly counts a native sheet as PASS). Part 2's `launchApp (stopApp)` then relaunches the app, but this alert belongs to the OS layer and **survives the relaunch**, occluding the hierarchy → `signin.username-input` never matches within 15s.
- Expected (PRD R-5 note) vs actual: the flow comment assumes "Relaunch (state kept — still signed out) to dismiss any native sheet" — that assumption does not hold for this alert class. The PRD's known-flake note anticipated a code-1000 rejection on sim; the observed behavior is a third variant (OS sign-in prompt), which is *consistent with the entitlement being honored* but makes Part 2 unrunnable in this cell without manually closing the alert (I dismissed it via a scratch tap-Close flow to unblock the rest of the batch).
- Verdict recording per orchestrator adjudication: observation only; NOT claimed as a build defect. Entitlement ground truth remains the R-8 device-artifact codesign (BLOCKED here).
- Evidence: `~/.maestro/tests/2026-07-12_125836/screenshot-❌-*.png` (alert over sign-in screen), maestro-11-apple.log.

### F-5: #131 R-6 version bump not applied — all four carriers still 1.7.2
- Severity: minor (open sequencing item, not a code defect)
- Repro: `grep -rn "1\.7\.2" mobile/app.json mobile/ios/DTFDynastyTradeFinder/Info.plist mobile/ios/DTFDynastyTradeFinder.xcodeproj/project.pbxproj` → 4 hits (app.json:5, Info.plist:22, pbxproj:378 + 409).
- Expected (PRD R-6) vs actual: PRD's mechanical pass requires zero 1.7.2 hits post-bump, while also stating the batch orchestrator owns final version sequencing across the group ("treat 1.7.3 as the default, not a hard assumption"). Recording as open, for the orchestrator to sequence before ship.

### F-6: #126 pytest pins — only §4.6 and §4.7 were added; §4.1–§4.5 rest on pre-existing tests that don't pin the PRD's exact sequences
- Severity: minor (test-plan deviation; all existing behavior pins are green)
- Repro: `git diff backend/tests/test_verified_sessions.py` → +38 lines: `test_link_expired_token_denied_before_oracle` (§4.6) and `test_link_delete_then_get_reports_disconnected` (§4.7) only.
- Expected (PRD §4.1–4.5) vs actual: §4.1's single end-to-end sequence (link 200 → gated write 200 **and** P2.5 read 200 **and** `POST /api/espn/link` 200 preview) is not pinned anywhere as one test; §4.2 (link then `session/init` reports verified) is approximated by `test_session_init_verified_carryover_and_controller_flag`, which stamps the session directly rather than via the link route; §4.4's "second replay with the oracle healthy → verified" heal step is untested; §4.3/§4.5's constituent predicates ARE covered piecemeal by pre-existing tests (`test_link_dead_token_denied_by_oracle`, `test_gate_denies_unverified_when_controller_exists`, `test_first_verified_wins_across_live_sessions`, read gate in `test_verified_reads.py`). §4.8 holds (full suite green, additive-only edit to this file). Resolution loop should adjudicate whether piecemeal coverage satisfies the PRD or the missing sequence pins get written.
- Evidence: pytest-126.log; test file at `backend/tests/test_verified_sessions.py`.

### F-7: ESPN link sheet content disappears while the iOS keyboard is open (both entry paths); primary CTA unreachable until keyboard dismissed
- Severity: minor as observed on sim (recoverable via the keyboard's return key), flagged for on-device verification — if it reproduces on device it is major for the ESPN funnel
- Repro (sim, iOS 18.4): sign in as qa_standard → LeaguePicker → tap `leagues.link-espn` (or Settings → `settings.link-espn`) → sheet renders correctly → tap `espn-link.input` → keyboard opens and the **entire sheet content vanishes** (dimmed backdrop + keyboard only; input, Continue, Cancel all visually gone while still present in the accessibility hierarchy — taps on their recorded coordinates hit the keyboard/backdrop and do nothing; no POST reaches the backend). Pressing **return** dismisses the keyboard and the sheet content returns, after which Continue works normally. Maestro's `hideKeyboard` closes the entire sheet (distinct behavior, worth knowing for future flows).
- Expected vs actual: sheet should stay visible (keyboard-avoiding) while the league ID is typed; actual is a blank backdrop. Note this is on the pre-existing #115 sheet layout, not the #126 R-7 catch-block edit — R-7's mapped copy itself verified correct once the request fires.
- Evidence: `~/.maestro/tests/2026-07-12_132127/screenshot-❌-*.png` and `2026-07-12_132750/…` (vanished-content state, both paths), adhoc-I-espn-sheet-open.png (healthy pre-focus state), adhoc-I-espn-mapped-403-r7.png (healthy post-return state with mapped error), flask-release.log (no `/api/espn/link` POST during occlusion; AUTH-DENY 403 once reachable).

## Notes for adjudication

- Flow 11 Part 1's optional 3s probe emitted the expected "Warning: Assertion is false" (the probe timing out is the green path) — not a failure.
- The Tiers screen lands on the QB tab by default with the SF TEP format pre-selected for qa_standard (legacy 03 expected an RB-default; irrelevant once selectors are fixed, but noted for whoever updates the flow).
- All ad-hoc flows were scratch files under the session scratchpad (copies preserved in `feedback-workspace/126/qa-round-1-agent-A/`); nothing was added to or changed in `mobile/.maestro/` and no test YAML, app code, or fixture code was modified. The only environment mutations were: one fixture-DB `verified_via` UPDATE (reverted by reseed), Flask start/stop on :5001, and dismissing the F-4 OS alert.
