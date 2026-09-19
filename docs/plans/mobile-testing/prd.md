# FTF Mobile Testing System — PRD (2026-07-10)

*The "product" is **rollout confidence** for the FTF iOS app (v1.5.3, `trade-engine-v2`); the "users" are Matt (solo operator) and Claude Code (test author/executor/driver). Suite: `plan.md` (S1–S3, W0–W5), `hld.md` (C1–C9, ADR-1…10), `lld.md`, `test-cases.md`. Ground truth: `app-inventory-2026-07-10.md`.*

---

## 1. Summary

A three-layer testing system so every TestFlight rollout is preceded by: (L1) automated Maestro regression on simulators against a hermetic local backend — seeded data profiles, canned Sleeper fixtures, pinned feature flags, injected faults; (L2) the same suite against the Release-config binary as a pre-EAS gate; (L3) a Claude-driven pass on the actual TestFlight app on a real iPhone via iPhone Mirroring, on a dedicated QA account. Safety is a product requirement, not a footnote: the system is *by construction* unable to reach Render prod, complete a Sleeper send, or pollute prod Sentry.

## 2. Problem & Context

- 19 screens / 82 features / 13 flag-gated surfaces ship weekly with **zero** automated UI coverage and **zero** testIDs. Regressions are found by the beta group, or not at all. Manual full passes cost hours and get skipped under time pressure.
- The app is state-heavy and nondeterministic (server-chosen trios, streaming trade jobs, debounced saves, unlock gating, multi-league state). Manual testing cannot cover the data-state matrix — ranked vs unranked opponents, empty vs 32-team leagues, flag on/off — that actually breaks trade apps.
- Real hazards: an unconfigured build talks to Render prod; Send-in-Sleeper performs a real outbound trade proposal; Sentry is live in every build; the backend live-calls Sleeper. An un-railed testing system is worse than none.
- Solo operator: no QA team, no CI. Everything must be runnable and maintainable by Matt + Claude Code on one Mac.

## 3. Goals & Non-Goals

**Goals**
1. Catch P0-flow regressions pre-submit, automatically, across the data states that matter, in <15 min (smoke) / <90 min per device (P0 set).
2. Hermetic, reproducible runs: same commit + profile + seed + flags ⇒ same verdict, offline from Sleeper.
3. Legible release decisions: one run report per run, one checklist per release; guardrails are recorded facts, not hopes.
4. Real-device verification per build of what simulators can't show (push, haptics, gestures, OLED, feel) — without corrupting real accounts.
5. Keep the suite alive under weekly app churn at a stated, bounded maintenance tax.
6. Leave the codebase permanently more testable (testIDs, env contract, seedable fixtures).

**Non-Goals (explicit)**
- NG1 CI/CD; NG2 Android/web/extension; NG3 pixel-diff visual regression (screenshots are archived evidence, not assertions); NG4 performance benchmarking (L3 observes cold-start, doesn't gate it); NG5 backend load testing; NG6 unit/component tests.
- NG7 Automating: Sleeper WebView login, real APNs delivery, haptics, drag/swipe gesture physics, OS share sheets, queue Send-All (each has compensating manual/alternative coverage — `test-cases.md` NOT-AUTOMATE table).
- NG8 Exhaustive flag combinations — per-flag boundary pairs only; interactions untested unless explicitly named (plan Q6).
- NG9 Coverage of orphaned surfaces (`RookieDraftBoardSheet`, `POST /api/trio/skip`) — no UI reaches them.
- NG10 A bug tracker — findings flow into the existing feedback/issue habits.

## 4. Success Metrics & Guardrails

| # | Metric | Target |
|---|---|---|
| M1 | Smoke wall-clock (clean checkout → verdict, FTF-iOS18) | <15 min |
| M2 | P0 set wall-clock (Release build, per device, unattended) | <90 min |
| M3 | Seeded-mutation detection (3 documented mutations: 401-guard revert, FormatGate break, Check/X swap) | 3/3 turn the run red; re-run after major suite refactors |
| M4 | Per-case flake rate (rolling 10 runs, flake ledger) | <5%; quarantined above |
| M5 | Suite survival: 3 consecutive weekly feature batches with lint green + triage ≤30 min | yes |
| M6 | Maintenance tax per screen-level app change | ≤20 min, measured |
| M7 | Coverage: every one of the 82 inventory features covered by some layer (1/2/3/M) and 100% of automatable P0s by L1/L2 | audit table in `test-cases.md` |
| M8 | New-flow authoring time on an instrumented screen | ≤30 min |
| M9 | L3 pass duration incl. report | ≤90 min |
| **G1** | Guardrail: backend live-Sleeper attempts during L1/L2 (`sleeper_live_egress_attempts`) | **0** (fail-closed seam; counter in every report). App-side prod-contact proof is indirect: fixture-only usernames make accidental prod contact fail loudly at sign-in, and preflight pins the baked base URL |
| **G2** | Guardrail: completed Sleeper sends in any automated run (`completed_proposes`) | **0** (structurally impossible: no token representable, propose refuses 2xx overrides). Propose-route *hits* are expected from the error-branch cases and recorded non-gating (`propose_route_hits`) |
| **G3** | Guardrail: prod-Sentry events from test builds | **0** (DSN nulled; preflight-asserted) |
| **G4** | Guardrail: L3 writes on non-QA accounts | **0** |
| **G5** | Guardrail: backend behavior change with test envs unset | none (pytest-asserted inertness) |

## 5. Requirements

### 5.1 Build & configuration
- **R-01 (P0)** `mobile/app.config.js` layers over `app.json`, reading `FTF_API_BASE_URL` and `FTF_ENV` into `expo.extra` at build time. Unset ⇒ byte-identical prod behavior (verified by static config evaluation). `FTF_ENV=test` ⇒ Sentry DSN nulled + `extra.testMode: true`.
- **R-02 (P0)** All gating runs use Release-config builds with embedded JS bundle; Metro-attached dev builds never gate.
- **R-03 (P0)** The runner preflight-fails (exit 3) if the app it is about to launch resolves `apiBaseUrl` to any non-localhost host — checked via the evaluated expo config AND a backend `/__test__/whoami` handshake before the first flow.
- **R-04 (P0)** Test builds send nothing to Sentry (G3): `extra.sentryDsn` nulled at build time AND the second DSN source `EXPO_PUBLIC_SENTRY_DSN` (`sentry.ts:31`) asserted unset by preflight; W0.1 verifies `Sentry.init` genuinely short-circuits on a falsy DSN. L3 (real binary) sends real events by design; whether they're attributable to the QA account depends on Sentry user context — verify in W0.1, else identify L3 events by build+time window.

### 5.2 Hermetic backend (Layer 1)
- **R-05 (P0)** All backend egress to `api.sleeper.app` routes through the fixture seam (`_sleeper_get`) when `FTF_SLEEPER_FIXTURES_DIR` is set: known path → canned JSON; unknown path → HTTP 599 + run-fatal guardrail counter + `X-FTF-VCR-Miss` header. Silent live fallback is prohibited.
- **R-06 (P0)** The seeder emits, atomically from ONE generator: SQLite DB + Sleeper fixture dir + **per-profile players warm-cache file** + manifest (schema hash, seed) — none of the three can drift from the others. The backend's cache path is a hardcoded shared global (`data/.sleeper_players_cache.json`, `server.py:353`): test runs MUST redirect it via `FTF_PLAYERS_CACHE_FILE`, and preflight refuses `players_cache: warm` without the override — the harness must never clobber the real dev cache. `FTF_SLEEPER_RECORD=1` bootstrap mode records live shapes once (runs with `FTF_TEST_MODE` unset — record is deliberately live). `--verify` detects backend-schema drift (exit 3 "re-seed profiles").
- **R-07 (P0)** Named profiles at MVP: `standard`; `fresh` (exactly 1 league, locked, zero rankings; carries a second `no-leagues` fixture user for the empty-picker case); `near-unlock` (threshold−1 rankings — unlock-banner and push-priming transitions); `two-leagues`; `single-format`. Phase 2: `large-league`, `sparse-roster`, `empty-league`. Deterministic given `--seed`. Full 13-key flag map explicit per profile (a new flag forces a per-profile decision). Every test-case data precondition maps to a profile schema field (`matches_seed`, `activity_seed`, `feedback_reply_seed`) — free-text "seed:" notes are not an interface. `demo` is a runner alias (standard DB + `landing.try_before_sync=on` pin), not a seeder profile.
- **R-08 (P0)** A `standard` boot supports the full first-run path with zero live network: `/api/extension/auth` (fixture user `qa_standard`), league list, 2-phase `/api/session/init`, players warm-cache, rankings, trio, trade generation.
- **R-09 (P0)** Flag pinning uses the existing `FTF_FLAGS` env override (highest precedence, `feature_flags.py:154`) — `config/features.json` is never mutated. Canonical sets: `release` (mirror of prod) and `all-on`; per-case single-flag pins. Fresh install per cell defeats the client's `feature_flags_v1` cache.
- **R-10 (P0)** Test-support blueprint mounted ONLY under `FTF_TEST_MODE=1`: `POST /__test__/fail_next` (path pattern, status, count, **optional JSON body**; a general response override — 2xx legal for precondition overrides like the Sleeper link-status gate — with one carve-out: `/api/trades/propose` refuses 2xx overrides, so propose can never be faked to success. The client branches on error codes in response bodies: `sleeper_not_linked/expired`, `sleeper_rejected`, `roster_not_found`, `league_not_found`), `POST /__test__/latency` (path, ms), `POST /__test__/reset`, `GET /__test__/whoami` (profile, mode, guardrail counters, active injections). 404 in normal operation. This is what makes error states, error-code branches, optimistic-rollback, slow-load copy, and poll-failure paths deterministic.
- **R-11 (P0)** `/api/trades/propose` fails closed (599) under `FTF_TEST_MODE` — defense-in-depth beyond "fixtures carry no token" (the profile schema cannot represent a write token; seeder refuses hand-edited ones).
- **R-12 (P0)** Backend blast radius ≤190 lines / ≤5 files (Sleeper seam ≈60, blueprint incl. body param ≈85, propose fail-closed ≈5, players-cache override + fetch guard ≈9, DynastyProcess seam ≈12, wiring ≈10, run.py PORT ≈4), every line dead unless a test env is set; pytest asserts inertness (G5). `FTF_TEST_MODE` without `FIXTURES_DIR`, `FTF_PLAYERS_CACHE_FILE`, or `FTF_DP_VALUES_FILE` ⇒ startup abort (a test-mode backend that can reach live Sleeper/DynastyProcess — or write the real players cache — is a rails hole; guards manual runs, since `sim-run.sh` always sets all three). *(The DP seam was added 2026-07-11 when implementation surfaced the DynastyProcess CSV as a live egress invisible to the Sleeper seam, with a silent flat-Elo fallback that would reshape the universal pool mid-test.)*

### 5.3 App instrumentation
- **R-13 (P0)** testIDs per the LLD grammar (`screen.element[.qualifier]`, natural keys never list indexes), ~90 IDs covering every element a Layer-1 flow references; additive props only; registry in `mobile/src/components/CLAUDE.md`; new screens must add IDs (definition-of-done for future features).
- **R-14 (P1)** `testid-lint.sh` cross-checks flow-referenced IDs against source and bans fixed sleeps/coordinate taps; failing lint fails the pre-submit checklist.

### 5.4 Execution & reset
- **R-15 (P0)** Every flow launches with `clearState: true, clearKeychain: true` unless explicitly tagged `persistence`. Reset scopes: flow (clear), profile (Flask restart + fresh DB + `/__test__/reset`), retry (simulator erase + reinstall).
- **R-16 (P0)** State-pollution canaries (TC-XC-07..09: session leak, react-query persister leak, Keychain hint leak) run in every P0 set — the reset story is verified, not trusted.
- **R-17 (P0)** Selectors are ids; every async boundary uses `extendedWaitUntil` (nav 10 s, query render 15 s, session init 30 s, trade-job terminal 60 s); server-chosen content asserted structurally (counts, presence, transitions), never player names; fixture-authored content may be asserted literally.
- **R-18 (P0)** Matrix runner: expands matrix per the pruning principle (ADR-7); isolates device failures (SKIPPED-INFRA, matrix survives); one retry per failed flow after relaunch — pass-on-retry recorded `flaky` (run stays green, counts toward M4); emits run-report JSON + JUnit + screenshot archive; exit codes distinguish test failure (1) / infra (2) / preflight rail (3) / guardrail tripped mid-run (4).
- **R-19 (P1)** Push on simulators via `xcrun simctl push` composite runner steps — proves payload rendering + tap-routing by `data.type` ONLY (not permission, registration, or delivery — those are L3). Priming modal: "Maybe later" path in L1; "Enable" path in L3.
- **R-20 (P1)** Deep links: cold start (`simctl openurl` on terminated app) and warm start as separate cases, including `?ref=` capture and `/u/<username>`.
- **R-21 (P0)** Demo mode is a feature under test, never a fixture mechanism for non-demo cases (its in-memory, DB-bypassing session is exactly the divergence blind spot). Demo cells pin `landing.try_before_sync=true`; one case asserts the link hidden under `release` flags.

### 5.5 Layer 2 (release gate)
- **R-22 (P0)** Layer 2 = the L1 suite against the Release build under the **full test env contract** (`FTF_API_BASE_URL=localhost` AND `FTF_ENV=test` — the DSN stays nulled; G3 applies to Layer 2 exactly as to Layer 1). Prod-config parity is verified **statically only** (R-25): Layer 2 never executes a build with a live DSN or prod URL. Hunts: minified-JS crashes, `__DEV__` divergence, startup timing.
- **R-23 (P0)** Pre-EAS checklist in `docs/runbook.md` lists Layer 2 green as step 1; first submit shadow, second enforces; a submit without it is a recorded process violation.
- **R-24 (P1)** One-time EAS parity check: introspect an actual EAS build's `expo.extra` to confirm the gate tests the config that ships.
- **R-25 (P1)** Static shipped-config check: `app.config.js` with no env resolves to the Render URL + real DSN — inspected, never executed.

### 5.6 Layer 3 (real iPhone, actual TestFlight binary)
- **R-26 (P0)** L3 runs ONLY on the dedicated QA account (`ftf-qa-*`) in a throwaway QA league; Matt's account is read-only in L3 (G4). L3 writes land in prod under the QA account by construction — accepted and contained (one-time leaderboard-scoping verification before steady state; cleanup path documented before scaling beyond one league).
- **R-27 (P0)** Send-in-Sleeper stops at the confirmation sheet. A true end-to-end send is a separate, operator-approved manual event (≤1 per release, QA league only — plan Q5).
- **R-28 (P0)** Per-build checklist minimum: cold launch + time-to-interactive observation; smoke-by-eye; real push receipt; haptics spot-check; safe-area/OLED look; swipe-velocity like/pass + one real drag; SleeperConnect WebView login; send stop-at-confirm. Output: written severity-ranked report per build, filed in-repo.
- **R-29 (P1)** The protocol is checkpointed (per-section, resumable) — a mirroring drop costs minutes, not the pass.

### 5.7 Maintenance & meta
- **R-30 (P1)** Per-change maintenance tax documented in the registry doc and enforced via checklist + lint (M5/M6); weekly 30-min triage with the flake ledger.
- **R-31 (P1)** Testing-the-tests: the 3 seeded mutations (M3) documented as exact patches in `mobile/scripts/mutations.md`.
- **R-32 (P1)** Runbook: run/read/extend/exit-codes/fixture-refresh; a fresh Claude session operates the system from docs alone.

## 6. Scope & Phasing

- **MVP (gates the next TestFlight):** S1–S3 + W0 + smoke(10) + P0(45) + L2 gate + L3 protocol/first pass. Profiles per R-07: `standard`/`fresh`/`near-unlock`/`two-leagues`/`single-format`; flag sets `release` + targeted pins.
- **Phase 2:** P1 flows (~60), remaining profiles, `all-on` sweep, push-injection cases, formal flake accounting maturity.
- **Phase 3 (opportunistic):** P2 cases, iPad depth, quarterly mutation drill, CI if it ever exists.
- **Cut-line rule:** nothing below the MVP line blocks a release; everything above it does. If S1 aborts: MVP degrades to manual-checklist L2 + L3 + jest component tests — pre-agreed.

## 7. Dependencies & Risks

Maestro ↔ RN New Arch visibility (spike-gated, XCUITest fallback pre-scoped); `DATABASE_URL` sqlite isolation (spike, test-checkout fallback); one-time live Sleeper recording (network + real username); TestFlight build + paired iPhone + QA account for L3; Sleeper ToS posture (plan Q4, operator decision). Backend seams ride to prod as env-gated dead code (accepted; G5 guards). Full risk table with abort criteria: plan §7.

## 8. Rollout & Measurement

Adopt incrementally: spikes → smoke gate on the very next TestFlight (even before the full suite) → P0 gate (shadow, then enforce) → L3 from the first build after W3. Run-report metrics (M1/M2/M4/G1–G3) accumulate in `mobile/test-artifacts/`; mutation drill after refactors + quarterly; coverage audit (M7) re-syncs whenever the app inventory is regenerated. **Kill criteria for the system itself:** flake >15% for a month despite demotions, or maintenance >1 day/release ⇒ pause the full matrix, keep smoke + L3, revisit tooling (XCUITest fallback).
