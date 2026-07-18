# Claude-Driven Mobile App Testing — Plan (rev 3, 2026-07-10)

*Supersedes rev 2 (`docs/plans/claude-xcode-testing-plan-2026-07-09.md`, now a pointer stub). Grounded in the app inventory (`app-inventory-2026-07-10.md`: 19 screens, 82 features, 13 flag-gated surfaces, all Sleeper access proxied through the FTF backend) and direct backend source verification. Suite companions: `prd.md` (requirements R-*, metrics M-*/G-*), `hld.md` (components C1–C9, decisions ADR-1…10), `lld.md` (interfaces), `test-cases.md` (201 cases). Branch `trade-engine-v2`, app v1.5.3. Dual-agent validated; reconciliation log at `reconciliation-log.md`.*

---

## 1. Objective & Definition of Done

**Objective.** Before each TestFlight rollout, Matt (solo operator, with Claude Code as executor) can run an automated, screenshot-backed regression of the FTF iOS app across its real data states and device sizes, plus a structured real-device pass on the actual TestFlight binary — with zero risk of touching Render prod, completing a Sleeper send, or polluting prod Sentry. The failure mode this system exists to prevent: **a broken P0 flow (sign-in, session init, trio submit, trade generation, calculator verdict) reaching TestFlight because nobody re-walked it after a weekly feature batch.**

**Definition of Done (the rollout gate, mirrors PRD §8):**
1. `ui-test.sh --matrix smoke` green in <15 min from a clean checkout on FTF-iOS18.
2. `ui-test.sh --matrix full` green on the release-candidate commit, 2 devices: the 45-case P0 gate within ≤90 min/device (automated P1s also run in `full`; their addition to the budget is revalidated at W1 — the 90-min promise is made for P0 only).
3. Layer 2 green: same flows, Release-config build, prod-parity `release` flag set, as the pre-EAS gate.
4. Layer 3 report filed for the TestFlight build (dedicated QA account) with no severity-1 findings.
5. Rails verifiably held (run-report guardrail counters): zero non-localhost egress, zero completed proposes, zero prod-Sentry events from test builds.
6. Drift containment live: testid-lint green, per-case flake <5% rolling, weekly 30-min triage happening.

**Explicitly NOT in the DoD:** 100% automation of all 82 features. `test-cases.md` carries a 12-entry NOT-AUTOMATE register with reasons and compensating coverage — honest coverage beats aspirational coverage.

**What changed from rev 2:**
- Flow suite grows ~9 → ~30 flows (201 test cases; Layer-1 automatable ≈ 140).
- Rev 2's "Sleeper public reads" assumption was wrong: the app never calls Sleeper directly — the **backend** does, live (verified: `backend/server.py:404 _sleeper_get`; `/api/extension/auth` resolves real usernames). Hermeticity therefore moves server-side: a fail-closed **Sleeper fixture seam** (HLD ADR-1).
- Feature-flag pinning is a first-class harness concern — via the **existing** `FTF_FLAGS` env override (verified `backend/feature_flags.py:154`; zero new code — HLD ADR-2).
- State reset between flows is a designed architecture, not an afterthought (HLD ADR-5).
- Layer 3 runs on a **dedicated QA Sleeper account** — the TestFlight binary targets prod, so every L3 tap writes real rows (HLD ADR-8).
- Error/latency paths are made deterministic via an env-gated test-support blueprint (HLD ADR-6), not left to luck.

## 2. Scope

**In scope**
- iOS only. Simulators: FTF-iOS18 (iOS 18.4, UDID `89EEFD08-1237-4CEB-8583-30AAF44419AD`) as anchor, one iOS 26.4 iPhone, small-screen iPhone 16e, iPad Pro 11" (render-sweep only).
- Layers 1–3 as fixed. testID instrumentation (~90 IDs — rev 2's 40–60 undercounted; Trades alone needs ~20). `app.config.js` env contract. Backend fixture seam + test-support blueprint (blast radius ≤170 env-gated lines). Seeder with named profiles. Matrix runner + run report. Layer-3 protocol + QA account.
- Test cases for all 82 inventory features including flag-off, error, and empty states.

**Out of scope (explicit cut lines; revisit only on evidence)**
- Android; CI (all invocations local, Claude-run); unit/component tests (separate initiative); pixel-diff visual regression (screenshot archive gives most of the value at a fraction of the maintenance); device farms; load/perf testing (cold-start timing is observed in L3, not gated); removing TestFlight-era feedback surfaces (tested as-is).
- Automating: Sleeper WebView login, real APNs delivery, haptics, drag-gesture physics, OS share sheets, queue Send-All deep-link storm (NOT-AUTOMATE table in `test-cases.md`, each with compensating coverage).

## 3. Gating spikes (all three before broad investment)

> **STATUS 2026-07-11: ALL THREE SPIKES PASSED.** S1: Maestro resolves testIDs on the RN New-Arch Release build — id-select, tap, type, clearState/clearKeychain all work; full sign-in→league-pick→tabs journey green by id selectors; 10/10 back-to-back runs with zero cross-run leakage (S3). S2: full hermetic first-run path verified — fixture auth, session init with client-contract body (26-player roster), trio/rankings/progress (12/12/12/12 unlocked), trade job → 30 cards, propose fail-closed 599, all guardrail counters 0. The XCUITest fallback is NOT needed. Learnings folded into the LLD/runbook: :5001 (AirPlay owns :5000), DP-values seam added (live egress found during W0), reloader off under test mode, container-accessibility hazard confirmed live on LeaguePicker rows, session/init body must follow the client contract (user_id + user_player_ids). W0 is substantially complete. **W1 SMOKE MILESTONE DONE (2026-07-12): 10/10 smoke flows green on FTF-iOS18 against a pid-verified hermetic backend, guardrail counters all zero** (flows: `mobile/.maestro/flows/smoke/`; day-to-day driver: the `/maestro-test` skill). Next: remaining P0 flow authoring (~35 cases), then the W2 release gate.

Rev 2 buried its riskiest assumption behind a half-day spike with no failure definition. Rev 3 runs three gating spikes first; each has an abort criterion and a pre-decided fallback. No broad testID instrumentation or suite authoring until all three pass.

| # | Spike | Proves | Time | Abort criterion | Fallback |
|---|---|---|---|---|---|
| S1 | **Maestro visibility.** 6 testIDs on SignIn + TabNav; Release sim build; one flow: launch → type username → tap each tab. Also verifies: `FTF_API_BASE_URL` reaches `app.config.js` through the xcodebuild bundling phase (else `.env.test` + dotenv fallback) | Maestro + RN 0.81 New Arch + reanimated 4 exposes `testID`; the build contract works | 0.5–1 d | After 4 h of accessibility-tree debugging, Maestro cannot reliably (10/10) select an ID on SignIn or tap a tab | XCUITest target (pre-scoped; fixture/report/L3 architecture is driver-agnostic and survives the swap). If even that fails: L2-manual-checklist + L3 + jest — pre-agreed, not renegotiated in crisis |
| S2 | **Hermetic boot.** Fixture seam in `_sleeper_get` + seeded `standard` profile; app signs in as `qa_standard`, picks the fixture league, completes 2-phase session init, reaches Main — with the seam fail-closed (no live fallthrough). Verifies `DATABASE_URL=sqlite:` cleanly isolates the test DB (else dedicated test checkout fallback), `FTF_FLAGS` round-trips via `/api/feature-flags`, and records the exact live-call set of a cold session init (drives the cassette contract) | The whole server-side hermeticity story | 1 d | Session init requires live Sleeper data the seam cannot satisfy after recording one real session | Expand record mode (record once per profile, replay forever); last resort: live reads for auth path only, documented flake |
| S3 | **Reset + determinism.** Run the S1 flow 10× back-to-back on one simulator; assert zero cross-run leakage (session token, react-query 30-min persister, Keychain username hint). Sub-check: is `getNextTrio` deterministic against a seeded DB? | Per-flow `clearState`+`clearKeychain` actually resets AsyncStorage/SecureStore/Keychain | 0.5 d | Any leakage survives clearing | `simctl uninstall`+reinstall per flow (+20–30 s/flow, priced) . Trio nondeterminism → structural assertions only (already the convention) |

## 4. Workstreams & Milestones

### W0 — Foundations (blocked by S1–S3)
- **W0.1 Build contract:** `app.config.js` (layers over `app.json`); env `FTF_API_BASE_URL`, `FTF_ENV=test` (nulls Sentry DSN, sets `extra.testMode`). *Done bar:* test build provably never resolves `onrender.com` (runtime + `ui-test.sh` preflight bundle check); unset env ⇒ byte-identical prod behavior.
- **W0.2 Backend harness:** fixture seam in `_sleeper_get` (fail-closed 599 + guardrail counter + `X-FTF-VCR-Miss`); `FTF_SLEEPER_RECORD=1` bootstrap mode (runs with `FTF_TEST_MODE` unset — record is deliberately live); test-support blueprint (`/__test__/fail_next|latency|reset|whoami`) mounted only under `FTF_TEST_MODE=1`, with `fail_next` supporting an optional response **body** (the app branches on error codes in bodies — `sleeper_not_linked`, `sleeper_rejected`, `roster_not_found`); propose fails closed under test mode; `FTF_PLAYERS_CACHE_FILE` override (the players warm-cache is a hardcoded shared global at `data/.sleeper_players_cache.json`, `server.py:353` — without the override the seeder would clobber the real dev cache). Blast radius ≤170 lines / ≤4 files, all dead unless env set. *Done bar:* `pytest backend/tests/test_test_support.py` green, including the inertness assertion (envs unset ⇒ behavior identical to today).
- **W0.3 Seeder + profiles:** `seed_ui_test_db.py --profile <name>` atomically emits SQLite DB + Sleeper fixture dir + per-profile players cache + manifest from ONE generator (DB, fixtures, and cache cannot drift). **MVP profiles:** `standard`, `fresh` (1 league, locked, zero rankings), `near-unlock` (threshold−1 — the P0 unlock-banner and push-priming cases need it), `two-leagues`, `single-format`; `fresh` also carries a second `no-leagues` fixture user. **Phase 2:** `large-league`, `sparse-roster`, `empty-league` (consumed only by P1/P2 cases). *Done bar:* every MVP profile boots the app to Main via the S2 path; `--verify` catches schema drift.
- **W0.4 testIDs:** grammar + registry (LLD §2.5) in `mobile/src/components/CLAUDE.md`; ~90 IDs, shared chrome + all screens referenced by Layer-1 cases. *Done bar:* `testid-lint.sh` cross-check green; zero visual/behavior diff (additive props only).
- **W0.5 Rails:** preflight refuses non-localhost base URL (exit 3); seam fail-closed; no write token representable in the profile schema (seeder refuses); Sentry DSN-null asserted **including the second DSN source `EXPO_PUBLIC_SENTRY_DSN` (must be unset in test builds — `mobile/src/observability/sentry.ts:31`)**; preflight refuses `players_cache: warm` without `FTF_PLAYERS_CACHE_FILE`; guardrail counters wired into the run report. *Done bar:* a deliberately misconfigured run aborts before app launch; a deliberate propose attempt fails closed and flags the report.

### W1 — Layer-1 suite
Smoke set (10 cases) first, then all P0 (~45), then P1 opportunistically (~60 of the enumerated 104 — the rest stay enumerated-but-unbuilt, honestly). Conventions: ids only, `extendedWaitUntil` never fixed sleeps, per-flow `clearState`+`clearKeychain` (persistence-tagged cases opt out), structural assertions for server-chosen content, button-equivalents for gestures, terminal screenshot per flow, `# tc:`/`# profile:`/`# flags:` headers (LLD §4.4). Matrix runner + run report + flake ledger (LLD §2.1, §3.2). *Done bar:* smoke <15 min; P0 <90 min/device; the three seeded mutations (LLD §7) each turn the run red; state-pollution canaries (TC-XC-07..09) pass in every P0 run.

### W2 — Layer-2 gate
Same flows, Release config (already the build type — this is a checklist + static prod-config check, not new authoring): shipped-config sanity (no env ⇒ Render URL + real DSN present — inspected statically, never executed). Pre-EAS checklist lands in `docs/runbook.md`; **first submit runs the gate in shadow (non-blocking), second submit enforces.** *Done bar:* one real EAS submit gated.

### W3 — Layer-3 protocol
One-time: **dedicated QA Sleeper account (`ftf-qa-*`) + throwaway QA league** (operator, ~30 min); iPhone Mirroring pairing; computer-use grant. Per-build pass (45–90 min, checkpointed so a mirroring drop costs minutes): cold-launch timing, smoke-by-eye, the simulator-unreachable set (real push receipt, haptics, OLED/safe-area, swipe velocity + one real drag, SleeperConnect WebView login), Send-in-Sleeper **to confirmation sheet only**. L3 writes land in prod under the QA account by construction — contained: disposable account, Matt's account read-only, one-time leaderboard-scoping verification before steady state. *Done bar:* first written report filed under `docs/plans/mobile-testing/layer3-reports/`.

### W4 — Drift containment (continuous)
Per-change tax, stated: element rename → IDs + flows (~10–20 min); new screen → 1–2 flows + profile touch (~1–2 h); new flag → boundary case pair (~30 min) — paid in the same change, enforced by testid-lint in the pre-submit checklist. Weekly 30-min triage: quarantine >5%-flake cases (rolling 10 runs, flake ledger), delete cases for removed features, re-record fixtures only when backend Sleeper-facing code changes. *Done bar:* three consecutive weekly feature batches land without suite rot.

### W5 — Documentation
Runbook (run/read/extend/exit codes), `docs/config-reference.md` (new env vars), traceability (test-cases ↔ flows). *Done bar:* a fresh Claude session operates the smoke matrix from docs alone.

## 5. Sequencing & Critical Path

```
S1 ──┬─ S3 ─┐
     │      ├── W0.1..W0.5 (parallelizable) ── W1 smoke ── W1 p0 ── W2 gate ── rollout comfort
S2 ──┘      │                                                        (W5 alongside)
            └── W3 one-time setup (operator, parallel) ── W3 first pass
```
- **Critical path:** S1 → S2 → W0.2/W0.3 → W1 smoke → W1 p0 → W2.
- **Parallel:** W0.1+W0.4 (mobile) ∥ W0.2+W0.3 (backend) after spikes; per-screen flow authoring parallelizes across Claude sessions; W3 is Maestro-independent — if S1 aborts, W3 still ships.
- **Matrix arithmetic (pruning principle, HLD ADR-7):** naive 82×5×7×13 ≈ 37k cells — never run. Devices vary layout → device axis on smoke + tagged layout cases only; profiles vary data → applied per tagged case; flags vary presence → boundary pairs. Actual: smoke 10×5×1×1 (10 independent self-signing-in flows; wall-clock is the slowest device across 5 parallel sims — feasibility of 5 concurrent Release-app sims + Flask on one Mac is checked in S3); full ≈ 45 P0 × ~1.4 avg cells ≈ 65 executions/device on 2 devices; render-sweep = per-screen render flows × {iPhone 16e, iPad}. **Flask lifecycle:** `FTF_FLAGS` is per-process, so the runner groups cells by `(profile, flag-set, seed)` and restarts Flask per group — ~10 extra restarts × ~15 s is counted in the ≤90-min budget.

## 6. Timeline & Effort (solo Matt + Claude Code)

| Milestone | Effort | Confidence | Notes |
|---|---|---|---|
| Spikes S1–S3 | 2–2.5 d | 70% | S1 is the coin-flip; fallback priced |
| W0 complete | 3–4 d | 80% | Seeder is the bulk; seam is small |
| W1 smoke green | 1–2 d | 85% given S1 | |
| W1 P0 green (~45 cases) | 4–6 d | 70% | List-accessibility debugging is the tail risk |
| W2 gate live | 0.5 d | 95% | |
| W3 first pass | 1 d + 0.5 d operator | 85% | Mirroring quirks unknown until tried |
| W5 docs | 0.5 d | 95% | Continuous, booked at end |
| **Total to rollout comfort** | **12–15 focused days ≈ 4 calendar weeks part-time** | | P1 backlog (~60 cases) continues opportunistically after, ~2 cases/day |

Estimates include ~30% debugging budget; they exclude triaging new app bugs the system finds (separate work). Anything shorter cuts P0 breadth, not polish.

## 7. Risks & Mitigations

| # | Risk | L | I | Mitigation | Abort criterion |
|---|---|---|---|---|---|
| R-1 | Maestro can't see New-Arch elements | Med | Fatal to L1 | Spike S1; container-accessibility fix pattern; driver-agnostic architecture | S1 criterion; fallback XCUITest |
| R-2 | Fixture seam can't satisfy session init | Low-Med | Fatal to hermetic L1 | S2 records a real session's call set; record-mode expansion | S2 criterion |
| R-3 | State leaks between flows | Med | Silent false-green/red | S3 spike; per-flow clearing; canaries TC-XC-07..09 in every P0 run | S3 criterion |
| R-4 | Suite rots under weekly batches | **High** | Suite abandoned by week 6 | W4 loop: lint-in-checklist, stated tax, quarantine, weekly triage | Two consecutive triages >2 h ⇒ cut P1 cases until under budget |
| R-5 | Flake burns trust (timers, polling, animations, sims) | High | Med | Determinism at source (seam, injections, structural asserts); no fixed sleeps (lint); retry-once + quarantine >5%; per-cell sim erase | Case >5% flake after 2 fix attempts ⇒ quarantine or NOT-AUTOMATE |
| R-6 | L3 corrupts real data | Med | Prod pollution | QA account only; Matt's account read-only; stop-at-confirm | QA rows leak into shared surfaces ⇒ pause L3 until cleanup path exists |
| R-7 | iOS 26.4 Maestro driver lag | Med | Loses a device axis | 18.4 anchor; 26.4 verified in S1 | Drop to 18.4-only; 26.x coverage moves to L3 |
| R-8 | `DATABASE_URL` sqlite override doesn't isolate | Low-Med | High | S2 item; fallback dedicated test checkout | Never point harness at the working checkout's live DB |
| R-9 | Test seams drift into prod behavior | Low | Correctness | Env-gated, fail-closed, pytest inertness assert, review rule | — |
| R-10 | Accidental Sleeper write / prod hit / Sentry noise | Very Low | Critical | Layered rails (exit 3 preflight, fail-closed propose, DSN null, guardrail counters must read 0) | Any real send observed ⇒ halt all runs, audit |
| R-11 | Mirroring unreliable | Med | Low | Checkpointed protocol; note-and-continue | Fully unworkable ⇒ Appium/WDA tethered fallback |
| R-12 | Scope creep: gold-plating P2 flows | Med | Med | P0/P1 first; cut-line rule (PRD §6) | — |

## 8. Resourcing

- **Matt:** ~2–3 h one-time (QA account + league, pairing, grants, TestFlight installs); ~15 min/release (kick off gate, read report, L3 supervision — phone stationary and locked); 30 min/week triage co-review; decisions on open questions.
- **Claude Code:** everything else — authoring (testIDs, seams, seeder, flows, runner), execution, reports, L3 driving via computer-use. Parallel sessions during W0 and per-screen flow authoring.
- **Cost:** $0 new services; disk ~200 MB/run, last-10-runs retention.

## 9. Open Questions (owner: Matt unless noted)

1. **(before W0.3)** Exact live-call set of a cold `/api/session/init` — S2 records it; drives the per-profile cassette list. *(Claude, in S2)*
2. **(before W1 P0)** Do `DraggableFlatList` rows expose testIDs under New Arch at all? Drag cases are NOT-AUTOMATE regardless (button alternatives are covered); this only affects tile-tap cases. *(Claude, in W0.4)*
3. **(before W2)** EAS parity: is an EAS build's `expo.extra` identical to the local Release build's? One-time introspection; a gate that tests different config than ships is theater. *(Claude + Matt)*
4. **(before W3)** Sleeper ToS posture for the QA account — Send-in-Sleeper is already ToS-adverse per backend comments; does even stop-at-confirm L3 on a QA account carry ban risk Matt accepts?
5. **(before W3)** True end-to-end send: keep at zero, or one supervised send per release in the QA league?
6. Flag-pair interactions: per-flag boundaries are covered; name the 2–3 genuinely interacting pairs (e.g. `trade.finder_targeting` × `trade.preference_lists` share the long-press surface) or accept as untested.
7. Trends history: synthetic 30-day Elo timestamps acceptable? *(default: yes)*
8. iPad: render-sweep only, report-only, non-blocking? *(default: yes)*
