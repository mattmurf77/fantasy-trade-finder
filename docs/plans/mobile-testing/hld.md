# FTF Mobile Testing System — High-Level Design (2026-07-10)

*Companions: `prd.md` (R-*/M-*/G-*), `plan.md` (S1–S3, W0–W5), `lld.md` (exact interfaces), `test-cases.md`. Ground truth: `app-inventory-2026-07-10.md`.*

---

## 1. Context & Goals

System under test: FTF iOS app (Expo RN 0.81, New Architecture, dark-only, prebuilt native project) + Flask backend that **proxies all Sleeper reads and itself calls `api.sleeper.app` live** (verified: `backend/server.py:404 _sleeper_get` is the single choke point for ~10 call sites; `/api/extension/auth` resolves a real Sleeper username). Sessions are in-memory server-side (they die on Flask restart). Non-numeric league_ids already serve rosters/users from the local DB (`server.py:6202/6232`) — an existing seam the fixture design exploits as a bonus, not the backbone. One more shared global matters: the players warm-cache is a hardcoded file at `data/.sleeper_players_cache.json` (`server.py:353`) — the same `data/` dir as the real dev DB — so test runs must redirect it or they corrupt real dev sessions.

That one fact — the app never talks to Sleeper, the backend does — shapes the whole design: **hermeticity is achieved server-side** (local Flask + seeded SQLite + fixture-served Sleeper egress), not by mocking the mobile network layer.

**NFRs (PRD §4–5):** hermeticity G1 (zero non-localhost egress, fail-closed), safety G2/G3/G4, determinism (M4 flake <5%; structural assertions), inertness G5 (zero backend behavior change without test envs), bounded maintenance (M5/M6), runtime budgets (M1/M2), $0 cost, `expo prebuild`/RN-upgrade survival, additive-only app footprint.

**Fixed architecture:** L1 Maestro flows on sims (scale) → L2 same flows vs Release binary (pre-EAS gate) → L3 Claude driving the actual TestFlight app via iPhone Mirroring + computer-use on a dedicated QA account (capstone).

## 2. Architecture Overview

```
┌────────────────────────────── mac (operator/Claude) ──────────────────────────────┐
│  C6 ui-test.sh (matrix runner)                                                    │
│   │ preflight: evaluated-config check, /__test__/whoami handshake, rails armed    │
│   ├─► C1 seed_ui_test_db.py --profile P ──► P.db + sleeper-fixtures/P/ + manifest │
│   ├─► C3 Flask :5000  (DATABASE_URL=sqlite:P.db, FTF_FLAGS=<json>,                │
│   │        FTF_TEST_MODE=1, FTF_SLEEPER_FIXTURES_DIR=…)                           │
│   │      ├─ C2 fixture seam in _sleeper_get (fail-closed 599 + counter)           │
│   │      └─ C2b /__test__/* blueprint (fail_next, latency, reset, whoami)         │
│   ├─► C4 sim-build.sh: app.config.js bakes localhost URL + null DSN → Release .app│
│   ├─► per device: simctl erase/boot ► install ► maestro test --device UDID        │
│   │        C5 flows in mobile/.maestro/ (clearState+clearKeychain per flow)       │
│   └─► C7 aggregator ► test-artifacts/<run>/{run-report.json, junit, screenshots}  │
│  C9 safety rails (cross-cutting): exit-3 preflight, fail-closed seam & propose,   │
│      DSN-null assert, guardrail counters must read 0                              │
│  C8 Layer 3: iPhone Mirroring + computer-use ─► real iPhone ─► PROD backend       │
│      (QA account only; checkpointed protocol; written report)                     │
└───────────────────────────────────────────────────────────────────────────────────┘
```

| ID | Component | Responsibility |
|---|---|---|
| C1 | Fixture seeder | ONE generator atomically emits per profile: SQLite DB (users, leagues, rankings history, tiers, matches, unlock progress, seed-field data: `matches_seed`/`activity_seed`/`feedback_reply_seed`) + matching Sleeper fixture JSON dir + **per-profile players warm-cache file** + manifest (schema hash, seed). None of the three outputs can drift from the others. `--verify` catches backend-schema drift. Record mode bootstraps realistic shapes once from live (with `FTF_TEST_MODE` unset) |
| C2 | Fixture seam | In `_sleeper_get`: `FTF_SLEEPER_FIXTURES_DIR` set ⇒ serve canned JSON by URL path; miss ⇒ 599 + `X-FTF-VCR-Miss` + run-fatal counter. Never a silent live fallthrough |
| C2b | Test-support blueprint | Mounted only under `FTF_TEST_MODE=1`: fault/latency injection (`fail_next` — path pattern, status, count, **optional JSON body** for error-code branches like `sleeper_not_linked`; `latency`), `reset`, `whoami` (profile, mode, guardrail counters, active injections). Makes error/slow/rollback/error-code-branch paths deterministic |
| C3 | Local backend harness | One Flask per **`(profile, flag-set, seed)` group** — `FTF_FLAGS` is per-process, so cells with different flag pins get their own Flask (+~15 s each, counted in budgets); seeded DB via `DATABASE_URL`, players cache via `FTF_PLAYERS_CACHE_FILE`, seam + blueprint active; health check per group = `/__test__/whoami` returns the expected profile AND `/api/feature-flags` round-trips the pinned set |
| C4 | Build pipeline | `app.config.js` env contract + `sim-build.sh`: Release-config simulator build, embedded JS, localhost URL, nulled DSN; emits the evaluated config for C9 inspection; `--prod-check` statically asserts the shipping config (Render URL + real DSN) without executing |
| C5 | Maestro flow suite | ~30 YAML flows in `mobile/.maestro/` implementing `test-cases.md` L1 cases; `# tc:`/`# profile:`/`# flags:` headers are the single source the runner parses; conventions LLD §4.4 |
| C6 | Matrix runner | Expands sets × devices × profiles × flags per the pruning principle (ADR-7); orchestrates C1/C3/C4/C5 per cell; parallel per booted sim; retry + quarantine policy; composite steps (simctl push) interleaved |
| C7 | Report aggregator | run-report.json (LLD §3.2) + JUnit + screenshot archive + Flask/seam logs + flake ledger; guardrail counters are first-class fields; crash-safe (per-case JSON lines) |
| C8 | Layer-3 protocol | Pairing checklist, checkpointed pass script (gestures/haptics/push/WebView/send-gate), severity-ranked report template, QA-account containment rules |
| C9 | Safety rails | Preflight exit-3 (non-localhost URL, write-token in profile, `--live-sleeper` with a matrix); run-end guardrail evaluation (exit 4 if tripped) |

## 3. Data Model & Flow

**Fixture profile** = `(db_seed, sleeper_fixtures, players_cache, flags_map, manifest)`, generated atomically (schema LLD §3.1). Profile → coverage: `standard` = 12-team, user unlocked, 1 ranked + 1 unranked opponent (L+O); `fresh` = exactly 1 league, locked, zero rankings (gating/empty paths; carries a second `no-leagues` fixture user); `near-unlock` = threshold−1 rankings (unlock-banner + push-priming transitions — one trio submit crosses the threshold live); `two-leagues` = portfolio, matches filters, league switcher; `single-format` = FormatGate; phase 2: `large-league` (32 rosters), `sparse-roster` (graceful-drop), `empty-league` (seed-fallback). **W** (write token) is unrepresentable in the schema. **Push** is not data (simctl injection). **Demo** is not a seeder profile — the runner aliases it to `standard` + a `landing.try_before_sync=on` pin (server-generated session, a feature under test — R-21).

**Run flow:** expand cells → group by `(profile, flag-set, seed)` → per group: seed → start Flask → handshake → per device: erase/boot/install → per flow: [arm injections] → maestro run → `/__test__/reset` (always; whoami must show zero active injections before the next flow) → [retry once on erased sim] → collect → aggregate → guardrail evaluation → exit code. Smoke flows are **independent** (each self-signs-in, ~8–12 s against the seam) — never chained; order-dependence is exactly what ADR-5 exists to kill. Artifacts in `mobile/test-artifacts/<run-id>/` (gitignored, last-10 retention).

**Flag pinning flow:** `profile.flags ∪ cell overrides` → `FTF_FLAGS` env (existing highest-precedence override) → app fetches `/api/feature-flags` on boot → fresh install per cell means the AsyncStorage flag cache starts empty, so pinned server truth wins. Flag changes are new cells, never mid-run flips (determinism). Flag-cache *staleness* itself is tested by one persistence-tagged case (LLD E-03).

## 4. Key Design Decisions (mini-ADRs)

**ADR-1 — Sleeper hermeticity: fail-closed fixture seam in `_sleeper_get`.** The backend live-calls Sleeper for auth, leagues, rosters, users, players, ADP — so seeded-DB-only cannot boot a session, and live reads in L1 would import nondeterminism, rate limits, and third-party coupling. Chosen: one env-gated branch at the single choke point; canned JSON by URL path; miss ⇒ 599 + counter (a missing fixture is a test bug, never a reason to go live). Sign-in resolves fixture usernames through the same seam. Rejected: standalone mock Sleeper server + URL rewrites across ~10 hardcoded call sites (that's the blast radius we refuse); client-side mocking (tests a different app); live public reads (rev 2's position — wrong). `--live-sleeper` exists for manual canary runs only; refuses to combine with a matrix.

**ADR-2 — Flag pinning via existing `FTF_FLAGS` env override.** Verified present with highest precedence (`feature_flags.py:154`, defaults → features.json → env). Zero new code; per-process; working tree never dirtied. Rejected: editing `config/features.json` (race/commit hazard); a new overlay env (`FTF_FEATURES_FILE`) or flags endpoint (invented surface area). Fresh-install-per-cell defeats the client cache.

**ADR-3 — Fault/latency injection as an env-gated blueprint (C2b).** The app branches on status codes AND error-code bodies (401 guard, poll-failure cap, optimistic rollback, 4 s slow-load copy, `sleeper_not_linked/expired`, `sleeper_rejected`, `roster_not_found`, `league_not_found`). Backend-down testing exercises only connection-refused; deterministic per-path injection (`fail_next` with optional JSON body, `latency`) is what turns "hope it flakes" into designed cases — the body parameter is what makes the Send-in-Sleeper error-branch family testable at all against a propose route that otherwise fails closed (R-11: the bare 599 remains the un-injected default, with its own degradation case). `fail_next` is a general response override (2xx legal — needed as a precondition override to pass the client's link-status gate) with one normative carve-out: the propose route refuses 2xx overrides. Guardrail semantics follow: `completed_proposes` (real outbound sends — structurally impossible) gates exit-4; `propose_route_hits` is recorded non-gating, since the error-branch cases hit the route by design. Rejected: a fronting proxy (second process; the app's baked absolute URL makes per-path proxying fiddly); growing the Sleeper seam itself (keep it tiny — injection targets FTF routes, not Sleeper fixtures). Blast-radius accounting: seam ≈60 lines, blueprint incl. body ≈85, propose fail-closed ≈5, players-cache override ≈4, wiring ≈10 ⇒ ≤170, each behind env, pytest-asserted inert (G5).

**ADR-4 — Auth by driving the real sign-in UI per flow.** Sessions are in-memory; each flow signs in fresh as its fixture user (seam answers auth instantly; ~8–12 s/flow, absorbed by budgets). Rejected: pre-minting session tokens into SecureStore (no injection path without shipping test hooks; and sign-in is the single most load-bearing flow — exempting it from coverage is backwards).

**ADR-5 — Three-scope reset architecture, verified by canaries.** Flow scope: `clearState`+`clearKeychain` per launch (resets AsyncStorage incl. the 30-min react-query persister and flag cache, SecureStore token, Keychain hint). Profile scope: Flask restart + fresh DB + `/__test__/reset`. Retry scope: simulator erase + reinstall. Persistence-tagged cases opt out deliberately. Canaries TC-XC-07..09 run in every P0 pass — the reset story is verified per run, not trusted. Rejected: erase-per-flow (+20–30 s × ~150 flows ≈ +1 h/run — only the retry path pays it); in-app reset hook (code in the shipping bundle); trusting fresh-install-per-cell alone (S3 exists because the persister and SecureStore leak across flows otherwise). Residual: if `clearKeychain` misses expo-secure-store items (S3 decides), fallback is uninstall/reinstall per flow, priced.

**ADR-6 — Gestures out of L1; button equivalents assert the same mutations; real gestures in L3.** Swipe needs 120 px AND velocity >200; drags need 220 ms long-press on a patched list lib — synthetic gestures would be the #1 flake source. Every gesture has a product-supported equivalent (Check/X; chevrons + multi-select + jump-to-rank). L1 asserts the mutations through those; L3 verifies the gestures themselves every release (checklist items, R-28). Residual accepted: a gesture-only regression surfaces in L3, not L1. Plain scrolls and pull-to-refresh stay in L1 (coarse, reliable).

**ADR-7 — Matrix pruning: each axis only where it can change the outcome.** Devices vary layout ⇒ device axis on smoke + tagged layout cases (5 devices) ; P0 runs 2 devices (18.4 anchor + one 26.4). Profiles vary data ⇒ applied per tagged case. Flags vary presence ⇒ boundary pairs (on: works; off: absent) on one device/profile. Honest arithmetic: naive 82×5×7×13 ≈ 37k cells; pruned P0 ≈ 45 × ~1.4 ≈ 65 executions/device ≈ 60–90 min. Rejected: the full matrix (dishonest — nobody runs it, so it tests nothing).

**ADR-8 — Layer 3 on a dedicated QA account against prod, accepted and contained.** The TestFlight binary targets prod by construction; L3 writes real rows (trios mutate Elo/member_rankings, swipes create trade rows). Chosen: disposable `ftf-qa-*` account in a throwaway league; Matt's account read-only; one-time leaderboard-scoping verification; cleanup path documented before scaling. Rejected: L3 against local backend (needs a resigned build — then it's not the TestFlight artifact and L3 loses its reason to exist); a staging backend + special build (doubles infra for a solo operator).

**ADR-9 — Structural assertions for server-chosen content.** Trios are server-selected; deck order depends on job timing + fairness sort. Pinning server RNG reaches deep into ranking/trade services for little value; response record/replay bypasses the backend logic under test. Flows assert invariants (3 cards render; tap-order enables Confirm; submit increments progress; deck shows a card with give/receive + meter) and terminal states via `extendedWaitUntil` (trade job 60 s covering the 800→4000 ms backoff) — never fixed sleeps (lint-banned), never player names. Slow-load copy (4 s) is tested deterministically via latency injection in dedicated cases only. S2 checks whether seeding makes trios deterministic as a bonus; the convention doesn't depend on it.

**ADR-10 — Maestro + embedded Release bundle (carried from rev 2, re-affirmed at scale).** YAML flows, outside the Xcode project (prebuild-proof), drive any installed app, parallelize per-sim; no Metro. XCUITest is the pre-scoped fallback (S1 abort); the seeder/report/L3/rails layers are deliberately driver-agnostic — an S1 abort swaps the flow layer, not the investment.

## 5. Cross-Cutting Concerns

- **Flake containment:** determinism at source (seam, injections, structural asserts) → no fixed sleeps (lint) → per-cell sim hygiene → retry-once with `flaky` tag → flake ledger (rolling 10-run rates) → quarantine >5% → weekly triage. Ranked flake sources and their treatment: gestures (designed out), timing (designed out), simulator state (erased), driver/OS drift (18.4 anchor + post-upgrade canary flow).
- **Partial failure:** device lost mid-matrix ⇒ SKIPPED-INFRA rows, matrix survives (exit ≥2); Flask dies mid-profile ⇒ remaining cases INFRA-failed with log tail, next profile fresh; injection leak ⇒ `/__test__/reset` after every case + whoami `active_injections` asserted empty before the next; report writing crash-safe.
- **Security/secrets:** fixtures are synthetic or public-shape data with fake usernames; write token unrepresentable; recorder scrubs token-bearing fields by key-name denylist; `secrets.local.env` never read by the harness; artifacts gitignored. Sentry has TWO DSN sources (`extra.sentryDsn` and `EXPO_PUBLIC_SENTRY_DSN`, `sentry.ts:29-33`) — preflight asserts both are null/unset in test builds.
- **Observability:** every run reconstructable from run-report + screenshots + Flask log + seam log; guardrail counters at the top of the report; the report is the only interface the rollout gate reads — humans don't grep logs to decide a release.
- **At 10×:** flows shard by tags per-sim (Macs run 4–6 sims); profiles are data, not code; CI is a thin wrapper over `ui-test.sh` when it ever arrives. The non-scaling piece is L3 (serial, ~90 min) — by design, it's a capstone.
- **Drift containment:** testid-lint in the checklist; stated per-change tax; fixture re-record only when backend Sleeper-facing code changes; inventory regeneration triggers a coverage re-audit.

## 6. Risks & Open Questions

Design-level residuals (full table: plan §7): Maestro×New-Arch (S1; everything but the flow layer survives a driver swap) · fixture-shape drift when Sleeper changes APIs (prod sees it first; re-record cadence tied to backend changes) · `clearKeychain` vs expo-secure-store semantics (S3; uninstall fallback) · seams shipping to prod (env-gated, G5 pytest, review rule: no `FTF_TEST_MODE` reads outside the blueprint + seam) · trio determinism (structural assertions stand alone) · QA rows visible to real users (one-time scoping verification, R-26).

Open questions mirror plan §9. HLD-specific: none remaining — the stub-location question (fixtures under `backend/tests/fixtures/sleeper/<profile>/`, seam inline in `_sleeper_get`) is resolved as drawn; revisit only if the seam ever needs behaviors beyond serve-or-599 (it must not — injection lives in C2b).
