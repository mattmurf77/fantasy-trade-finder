---
name: maestro-test
description: >
  RETIRED (D-056, 2026-08-15) — DO NOT INVOKE. This skill ran Maestro UI flows
  against the FTF iOS app on the simulator. Maestro and the simulator are
  retired entirely: no flow authoring, no flow execution, no captures, for any
  change in any pipeline. It is kept only as a historical record of how the
  harness worked. For mobile verification use the structural
  `mobile/tests/check-*.js` suites + unit tests, a written code-walk proof, and
  a manual TestFlight checklist for the operator — never this skill.
---

# ⚠ RETIRED — do not run this skill (2026-08-18)

**[D-056](../../../living-memory/DECISIONS.md) (2026-08-15, operator, Active) retired
Maestro and the simulator entirely** — not just as a ship gate. No flow authoring, no
flow extension, no flow execution, no simulator captures, for any change, in any
pipeline. Operator's ruling: *"It's unreliable and a waste of tokens."*

**If you were routed here, stop and do this instead:**

| Instead of… | Do this |
|---|---|
| Authoring or running a flow to prove behavior | Add/extend a structural guard in `mobile/tests/check-*.js` (conventions: `mobile/tests/README.md`) and/or a unit test. CI's `mobile-typecheck` job globs the directory, so a guard is live the moment the file exists |
| A simulator capture as evidence | A written **code-walk proof** — a file:line-cited trace through the actual commit sequence |
| A sim run for runtime confidence | A concrete **manual TestFlight checklist** for the operator: numbered steps + expected result, specific enough to catch the regression it guards. This is the only runtime evidence mobile now gets |
| Writing `qa/sim-runs/last-sim-run.json` | Nothing — the pre-ship sim gate is retired and `githooks/pre-push` is a deliberate no-op. Record what you ran in `living-memory/TEST_LEDGER.md` |

What survives D-056: `mobile/scripts/testid-lint.sh` still runs in CI (the
`maestro-testid-lint` job keeps its name), so `testID`s still matter. The flows under
`mobile/.maestro/` are kept as historical artifacts — they document intended behavior;
they are never run.

Current evidence contract: `docs/templates/feature-scope.md` §3 and §5, and CLAUDE.md
§Conventions "Feature gates". Everything below this banner is **historical record only**.

---

# Maestro app testing (FTF iOS, hermetic harness) — HISTORICAL

> Superseded by D-056 on 2026-08-15. Retained to document how the harness worked, the
> traps it hit, and why the flows in `mobile/.maestro/` look the way they do. Do not
> execute any of it.

You are operating the mobile UI-test harness specced in
`docs/plans/mobile-testing/` (plan/prd/hld/lld/test-cases). All three gating
spikes passed 2026-07-11/12; the smoke set exists. Never test against Render
prod or a real Sleeper account — the harness makes that structurally
impossible; keep it that way.

## Scope resolution (from the user's ask)

| Ask looks like | Scope | What runs |
|---|---|---|
| One feature ("calculator verdict", "trio submit", "outlook sheet") | **feature** | The TC-mapped flow(s) for that feature; author if missing |
| A screen ("the Tiers page", "Matches") | **page** | Every existing flow tagged for that screen + a render flow; author gaps |
| "smoke", "everything", "full session", post-change regression | **app** | All of `mobile/.maestro/flows/smoke/*.yaml` (10 flows); optionally the full authored set |

Map features → cases with `docs/plans/mobile-testing/test-cases.md` (feature
list: `app-inventory-2026-07-10.md` §7; check its drift ledger for states the
cases don't know yet). Existing flows: `mobile/.maestro/flows/smoke/` (01–10)
and `mobile/.maestro/flows/` (spike flows). Available testIDs: the registry in
`mobile/src/components/CLAUDE.md`. If a needed element has no testID, add one
(additive prop only, registry grammar `screen.element[.qualifier]`, never a
list index), update the registry, and note that a rebuild is required.

## The run sequence (do these in order)

1. **Build (only if app code changed since the last test build):**
   `./mobile/scripts/sim-build.sh --env test` — captures exit code directly,
   never through a pipe. Bakes `http://127.0.0.1:5001` + null Sentry DSN.
   App lands at `mobile/ios/build/Build/Products/Release-iphonesimulator/DTFDynastyTradeFinder.app`.
2. **Backend (fresh, pid-verified):**
   ```bash
   python3 backend/tests/fixtures/seed_ui_test_db.py --profile standard --print-env > /tmp/mt-env.txt
   set -a; source /tmp/mt-env.txt; set +a
   PORT=5001 python3 run.py > /tmp/mt-flask.log 2>&1 &   # note $! as FPID
   # poll http://127.0.0.1:5001/__test__/whoami until 200, then REQUIRE:
   #   whoami.pid == FPID   (stale-instance guard — a leftover Flask answers
   #   the profile handshake convincingly; pid is the only honest check)
   ```
   If the port is occupied: NEVER blind-kill the port owner (a parallel dev
   session may own it — this was a real incident). Identify it first
   (`ps -p <pid> -o command`, check env for FTF_TEST_PROFILE via `ps eww`);
   kill only a provably-ours harness instance, otherwise ask the user.
   Seed BEFORE starting Flask, always (reseed-race incident, runbook).
   Other profiles (`fresh`, `near-unlock`, `two-leagues`, `single-format`)
   exist for gating/empty/multi-league/FormatGate states — pick per the case's
   Profile column.
3. **Simulator:** UDID `89EEFD08-1237-4CEB-8583-30AAF44419AD` (FTF-iOS18).
   `simctl boot` + `bootstatus -b` + `install` the .app. Erase first for a
   clean session; skip erase when iterating on one flow.
4. **Maestro:** `export JAVA_HOME="/opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home"`
   (maestro dies without it), then `maestro --device <UDID> test <flow.yaml>`.
5. **Rails audit (every session):** `GET /__test__/whoami` counters must read
   `vcr_misses: 0, sleeper_live_egress_attempts: 0, completed_proposes: 0`.
   Nonzero = the run is invalid regardless of green flows — report it loudly.
6. **Teardown:** kill only the Flask pid you started.

## Flow authoring rules (binding — from lld.md §4.4)

- `id:` selectors only; text-matching only to assert load-bearing copy, never
  to tap. `extendedWaitUntil` at every async boundary (nav 10s, query 15s,
  session init 30s, trade job 60s); zero fixed sleeps.
- Every flow: `launchApp {clearState: true, clearKeychain: true, stopApp: true}`
  first (independent flows, never chained), header comments
  (`# tc:`, `# profile:`, `# flags:`), terminal `takeScreenshot`.
- Server-chosen content (trio players, deck order) → structural asserts only.
  Fixture-authored content (league "QA Standard League", user `qa_standard`,
  Joe Burrow id `6770`) may be asserted literally.
- Gestures (pan-swipe, long-press drags) are NOT automated — use the button
  equivalents (Check/X `trades.like-btn`/`trades.pass-btn`, chevrons,
  jump-to-rank).
- Sign-in preamble: type `qa_standard` → `signin.continue-btn` →
  `leagues.row.990000000000000001` → wait `tab.trades`.

## Known traps (each cost a debugging round — check FIRST on failure)

- **First Trades visit auto-opens the OutlookSheet** — conditionally dismiss
  via `outlook.save-btn`, then `extendedWaitUntil notVisible` + `waitForAnimationToEnd`
  (a tap during the close animation gets swallowed and "completes" without
  navigating).
- **Keyboard eats taps** — after `inputText`, `hideKeyboard` before tapping
  anything below the field (row tap "completes" but onPress never fires).
- **Calculator picker stays open after a pick** — tap `calc.picker.done`.
- **Below-the-fold targets** — `scrollUntilVisible` (like-btn, calc.verdict).
- **Container accessibility swallows children** — text renders but text-asserts
  fail; select by the container's own testID, or add `accessible={false}`.
- **Verify a tap NAVIGATED/acted** by asserting the destination state; a
  COMPLETED tap proves the element was hit, not that the app responded.
- **Full authoring-law list lives in `mobile/.maestro/README.md` § Flow-authoring
  laws** (2026-08-10, 23 laws from the screen-library build) — read it before
  writing or fixing ANY flow. Highest-frequency additions since this list was
  written: text matchers are FULL-MATCH regex (wrap `.*`); `visible:` counts
  off-screen ScrollView children (scrollUntilVisible with
  visibilityPercentage:100 before below-fold taps AND shutters); never
  `waitForAnimationToEnd` before an ActivityIndicator shutter; loading states
  need `clearState: true` cold starts (persisted query cache); injection
  budgets 2/4/6/1 by retry stack; arm `fail_next` BEFORE opening the surface;
  `# flags:` is a resolved fixture filename, never prose; deep links are dead
  — use launch-argument entry; reset the simulator when cells slow 5-10x.
- **Failure debugging:** `~/.maestro/tests/<latest>/` has the screenshot +
  hierarchy; `/tmp/mt-flask.log` shows what the app actually called — a flow
  bug usually diagnoses faster from the Flask side.

## Report format (end of session)

Per-flow table (PASS/FAIL, failing step for FAILs), rails counters, paths to
terminal screenshots (send the interesting ones to the user), and — required —
any NEW app state discovered that the flows/test-cases don't model: add it to
the drift ledger in `docs/plans/mobile-testing/test-cases.md` and, if you
added testIDs, to the registry. A finding that "X is broken in the app" (not
the test) goes to the user as a finding, not a silent fix.

## Whole-app sessions

Run all smoke flows serially on the standard profile; on any failure, retry
once after `simctl terminate` + relaunch (record as flaky if it passes).
For a deeper session, extend with feature flows per screen (Profile column
drives per-flow profile; restart Flask per profile group — `FTF_FLAGS` is
per-process). Wall-clock guide: smoke ≈ 12–15 min including build.
