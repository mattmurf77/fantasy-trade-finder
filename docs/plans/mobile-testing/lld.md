# FTF Mobile Testing System — Low-Level Design (2026-07-10)

*Implements `hld.md` C1–C9 / ADR-1…10 within `prd.md` R-01…R-32. Ground truth for app facts: `app-inventory-2026-07-10.md`.*

---

## 1. Scope & Files

New files (all in-repo):
```
mobile/app.config.js                          # §2.4 env contract
mobile/scripts/sim-build.sh                   # §2.3
mobile/scripts/sim-run.sh                     # §2.2 single-cell executor
mobile/scripts/ui-test.sh                     # §2.1 matrix runner
mobile/scripts/testid-lint.sh                 # §2.6
mobile/scripts/mutations.md                   # §7 seeded mutations (exact patches)
mobile/.maestro/flows/**.yaml                 # ~30 flows
mobile/.maestro/payloads/*.json               # simctl push payloads
mobile/.maestro/README.md                     # traceability TC ↔ flow
mobile/test-artifacts/                        # gitignored run outputs
backend/test_support.py                       # C2b blueprint (~85 lines incl. fail_next body)
backend/tests/test_test_support.py            # incl. inertness assertion (G5)
backend/tests/fixtures/seed_ui_test_db.py     # C1 seeder
backend/tests/fixtures/profiles/*.json        # §3.1
backend/tests/fixtures/sleeper/<profile>/**   # canned JSON (seeder-emitted)
backend/tests/fixtures/flags/{release,all-on}.json
docs/plans/mobile-testing/layer3-reports/     # §2.7
```
Backend edits: seam branch in `server.py:_sleeper_get` (~60 lines incl. logging/counters), propose fail-closed (~5), players-cache path override (~4), players-cache fetch guard (~5), blueprint wiring (~10); blueprint itself ~85 incl. `fail_next` body support; DP seam in `data_loader.py` (~12); `run.py` PORT env (~4). Mobile edits: testIDs (additive) + `app.config.js`. Total backend blast radius ≤190 lines / ≤5 files, env-gated (R-12). As-built 2026-07-11; pytest-pinned by `backend/tests/test_test_support.py`.

## 2. Interfaces

### 2.1 `ui-test.sh` — matrix runner (C6)

```
ui-test.sh [--matrix smoke|full|render-sweep]     # default smoke
           [--flows <tag|file>[,…]] [--devices <udid>[,…]]
           [--profile <name>] [--flags <set|k=v,…>] [--seed <int>]   # overrides
           [--report-dir <path>] [--no-build] [--no-retry] [--keep-artifacts N]
           [--live-sleeper]                        # manual canary only; refuses --matrix
```
**Exit codes (contract):** `0` green (flaky-passes allowed, reported) · `1` ≥1 flow failed post-retry · `2` infra (build/seed/Flask/sim) · `3` preflight rail refusal (non-localhost URL, write token in profile, `--live-sleeper`+matrix) · `4` guardrail tripped mid-run (`sleeper_live_egress_attempts>0`, `vcr_misses>0`, `completed_proposes>0`, Sentry-on detected) — distinct from 1 because a tripped guardrail invalidates the whole run. `completed_proposes` bumps only if a real outbound Sleeper send occurs (structurally impossible: no token representable + the blueprint refuses 2xx on the propose route); mere propose-route hits are recorded as the non-gating `propose_route_hits` field — TC-TRD-29/33 legitimately hit the route by design · `5` bad args/unknown profile/flag key.

Matrix definitions: `smoke` = flows tagged `smoke` × 5 devices × `standard` × `release`. `full` = all flows × {FTF-iOS18 `89EEFD08-…`, one iOS 26.4 iPhone} × per-flow declared profile/flags (§4.4 headers). `render-sweep` = flows tagged `render` × {iPhone 16e, iPad Pro 11"} × `standard` × `release`.

### 2.2 `sim-run.sh` — single-cell executor

```
sim-run.sh --udid <UDID> --app <.app path> --profile <name>
           [--flags <set|k=v,…>] [--seed <int>] [--flow <file|tag>]
           [--keep-data] [--report-dir <dir>]
```
Steps: seed (§2.5) → start Flask (§2.5b) → handshake → `simctl shutdown/erase/boot` (skipped with `--keep-data`) → install → per flow: arm injections if declared → `maestro test --device <udid>` (timeout: flow header or 180 s) → `POST /__test__/reset` (always, pass or fail) → retry policy (§4.2) → collect artifacts → stop Flask, archive logs. Exit codes as §2.1.

### 2.3 `sim-build.sh` — build pipeline (C4)

```
sim-build.sh [--api-base <url>]        # default http://127.0.0.1:5001 (:5000 is macOS AirPlay's)
             [--env test|prod-check]   # test: null DSN; prod-check: static config eval only
             [--out <dir>]             # default mobile/ios/build
```
`--env test`: `FTF_API_BASE_URL=<url> FTF_ENV=test xcodebuild -workspace mobile/ios/DTFDynastyTradeFinder.xcworkspace -scheme DTFDynastyTradeFinder -configuration Release -sdk iphonesimulator -derivedDataPath <out> build`; emits `<out>/resolved-config.json` (evaluated expo config) for C9: `extra.apiBaseUrl` must be the localhost URL, `extra.sentryDsn` must be null, AND `EXPO_PUBLIC_SENTRY_DSN` must be unset in the build environment (`sentry.ts:31` reads it as a second DSN source) — else exit 3. Post-build bundle check: if `--api-base` is localhost but the prod URL is the *active* resolved value in the bundle ⇒ exit 3.
`--env prod-check`: evaluates `app.config.js` with no env; asserts `apiBaseUrl` ends `onrender.com` AND DSN present (R-25) — never builds or launches.
> **S1 spike item — RESOLVED (2026-07-11):** `FTF_API_BASE_URL`/`FTF_ENV` DO reach the config-evaluation phases through xcodebuild (verified: built app embeds `EXConstants.bundle/app.config` with the localhost URL, empty DSN, `testMode: true`). The dotenv fallback was not needed. Caveat chain that had to be fixed first (all space-in-path bugs — see runbook + `mobile/ios/Podfile` post_install): EXConstants' phase invocation quoting, its script's silent `basename $PROJECT_DIR` no-op (phase now calls `getAppConfig.js` directly), Sentry's bundling wrapper + skip-branch, Sentry debug-symbols phase, plus `SENTRY_DISABLE_AUTO_UPLOAD=true` for test builds and `ONLY_ACTIVE_ARCH=YES ARCHS=arm64`.

### 2.4 `mobile/app.config.js` env contract

```js
// Layers over app.json. Unset env ⇒ byte-identical to today's behavior (R-01).
export default ({ config }) => {
  const isTest = process.env.FTF_ENV === "test";
  return {
    ...config,
    extra: {
      ...config.extra,
      apiBaseUrl: process.env.FTF_API_BASE_URL ?? config.extra.apiBaseUrl,
      sentryDsn: isTest ? "" : config.extra.sentryDsn,     // "" not null: null survives expo-config
                                                            // serialization as {} (truthy!) — verified 2026-07-11
      testMode: isTest,                                     // reserved; no runtime branch yet
    },
  };
};
```

| Var | Consumer | Effect |
|---|---|---|
| `FTF_API_BASE_URL` | `client.ts` via `expoConfig.extra.apiBaseUrl` (existing chain) | test builds → local Flask |
| `FTF_ENV=test` | `app.config.js` | DSN nulled + `testMode` |
| `FTF_FLAGS` (JSON dict) | backend `feature_flags.py` (existing, highest precedence) | flag pinning (R-09) |
| `FTF_SLEEPER_FIXTURES_DIR` | backend `_sleeper_get` (new) | fixture seam (R-05) |
| `FTF_SLEEPER_RECORD=1` | backend `_sleeper_get` (new) | record cassettes from live (bootstrap; runs with `FTF_TEST_MODE` **unset** — record is deliberately live; conflicts with existing cassettes ⇒ startup abort, never silent overwrite) |
| `FTF_TEST_MODE=1` | backend (new) | mounts `/__test__/*`; propose fails closed; **requires** `FIXTURES_DIR` AND `FTF_PLAYERS_CACHE_FILE` else startup abort (R-12 — a test-mode backend that can write the real players cache is the same class of rails hole as one that can reach live Sleeper) |
| `FTF_PLAYERS_CACHE_FILE` | backend (new, ~4 lines) | redirects the hardcoded players warm-cache path (`server.py:353` → `data/.sleeper_players_cache.json`, shared with real dev) to the profile's cache output. Preflight refuses `players_cache: warm` without it |
| `FTF_DP_VALUES_FILE` | backend `data_loader._fetch_dynasty_process` (new, ~12 lines) | serves a local DP-shaped CSV through the identical parse path — the DynastyProcess live fetch (raw.githubusercontent.com) is an egress the Sleeper seam can't see, and its silent flat-Elo fallback would reshape the universal pool mid-test. **Mandatory under `FTF_TEST_MODE`** (startup abort; also raises lazily if only the env is missing). Seeder emits it as the fourth artifact (`dp-values/<profile>.csv`) |
| `DATABASE_URL` | backend (existing) | seeded DB isolation (S2 verified 2026-07-11: clean isolation, engine reads env at import) |

### 2.5 Seeder — `seed_ui_test_db.py` (C1)

```
seed_ui_test_db.py --profile <name> [--out-dir data/ui-test] [--seed <int>=1337]
                   [--list] [--verify] [--print-env]
exit: 0 ok · 2 io/write failure · 3 refused (write-token field in a hand-edited profile [R-11],
      or --verify schema mismatch → "re-seed profiles") · 4 unknown profile · 5 cassette gap
      (profile references a Sleeper path its generator didn't emit)
```
Writes atomically (temp dir + rename): `<out>/<profile>.db`, `<out>/sleeper/<profile>/`, `<out>/players-cache/<profile>.json`, `<out>/<profile>.manifest.json` (schema hash of `backend/database.py`, seed, created-at, season). `--print-env` emits the env block `sim-run.sh` sources (including `FTF_PLAYERS_CACHE_FILE`). Seeder writes through SQLAlchemy models (never raw SQL) so schema migrations carry it. **One generator, three outputs:** the same synthetic league objects produce DB rows, Sleeper fixture JSONs, and the players cache — `/api/extension/auth`'s view, the DB, and the warm-cache cannot disagree (R-06).

**2.5b Backend launch env (C3):** `DATABASE_URL=sqlite:///<db> FTF_FLAGS='<json>' FTF_TEST_MODE=1 FTF_SLEEPER_FIXTURES_DIR=<dir> FTF_PLAYERS_CACHE_FILE=<file> python run.py`. **One Flask per `(profile, flag-set, seed)` group** — `FTF_FLAGS` is per-process, so cells with different flag pins cannot share a Flask; the runner counts the extra restarts (~10 × ~15 s across the P0 set) in the budget. Health check per group (30 s budget, else exit 2): `GET /__test__/whoami` returns `{profile, test_mode: true, fixtures: true}` AND `GET /api/feature-flags` equals the pinned set (a mis-pinned run must die here, not mid-flow — a wrong flag state in a boundary case is a false-green hazard, not just a red).

### 2.6 `testid-lint.sh`

```
exit: 0 ok · 1 flows reference IDs missing from mobile/src (lists them)
    · 2 banned patterns in flows (fixed sleep, coordinate tap, text-selector tap)
```

### 2.7 Layer-3 report template
`docs/plans/mobile-testing/layer3-reports/<build>.md`: build/device/OS/date · checklist results (test-cases L3 rows by ID, checkpointed sections) · findings `severity(1-3) | screen | description | screenshot` · gesture block (swipe velocity, one Tiers drag, one ManualRanks drag, haptics, real push receipt, WebView login, send stopped at confirmation ✓) · go/no-go.

## 3. Data Structures

### 3.1 Fixture profile schema (`profiles/<name>.json`)

```jsonc
{
  "schema_version": 1,
  "name": "standard",
  "description": "12-team; user unlocked; 1 ranked + 1 unranked opponent",
  "season": 2026,
  "flags_base": "release",                 // file in fixtures/flags/
  "flag_overrides": {},                    // full-map materialized at seed time; every profile's
                                           // effective map is EXPLICIT for all 13 keys (R-07)
  "app_user": { "username": "qa_standard", "user_id": "900000000000000001",
                "unlocked": true,                    // fresh: false+zero; near-unlock: threshold-1
                "rankings": { "positions": ["QB","RB","WR","TE"], "history_days": 30,
                              "formats": ["1qb_ppr","sf_tep"] },
                "tiers": "seeded-suggested", "anchors": null },
  "extra_users": [],                                 // fresh carries {"username":"qa_no_leagues", "leagues": []}
  "activity_seed": 3, "feedback_reply_seed": 1,      // every case data-precondition is a schema field, never free text
  "leagues": [
    { "league_id": "990000000000000001", "name": "QA Standard League",
      "total_rosters": 12, "format": "sf_tep", "roster_size": 26,
      "members": [
        { "username": "qa_opp_ranked",   "user_id": "900…002", "rankings": "generated", "roster": "generated:balanced" },
        { "username": "qa_opp_unranked", "user_id": "900…003", "rankings": null,        "roster": "generated:balanced" }
        // remaining members generated, unranked
      ],
      "matches_seed": { "mutual": 2, "awaiting": 1 } }
  ],
  "players_cache": "warm"                  // pre-writes the players warm-cache artifact
  // Deliberately UNREPRESENTABLE: any sleeper write-token field (seeder exit 3 if present)
}
```
Roster archetypes: `balanced` · `qb-heavy` · `thin` (sparse-roster) · `deep-32` (large-league). `history_days` fabricates Elo timestamps **relative to seed-time `now`** (never absolute dates) so Trends always has 30-day movers. `players_cache: "warm"` emits the per-profile cache file (§2.5) — preflight refuses it without `FTF_PLAYERS_CACHE_FILE`. **MVP profiles** (each a distinct, internally consistent state — a profile is never asked to be two states at once): `standard` · `fresh` (exactly 1 league, locked, **zero** rankings; `extra_users` carries `qa_no_leagues` for the empty-picker case) · `near-unlock` (threshold−1 rankings; one live trio submit crosses the unlock threshold — used by the unlock-banner and push-priming cases) · `two-leagues` · `single-format`. Phase 2: `large-league`, `sparse-roster`, `empty-league`. `demo` is NOT a seeder profile — the runner aliases it to `standard` + `landing.try_before_sync=on`; likewise `no-leagues` in a flow header aliases to `fresh` signing in as its `qa_no_leagues` extra user (exit 4 applies only to genuinely unknown names).

### 3.2 Run-report schema (`run-report.json`)

```jsonc
{
  "schema_version": 1,
  "run_id": "2026-07-12T09-30-00Z-a1b2c3", "commit": "…", "app_version": "1.5.3",
  "matrix": "smoke", "wall_clock_s": 812,
  "guardrails": { "api_base_url": "http://127.0.0.1:5000", "onrender_refused": false,
                  "sentry_dsn_nulled": true, "sentry_env_var_unset": true,
                  "sleeper_live_egress_attempts": 0, "vcr_misses": 0,
                  "completed_proposes": 0, "propose_route_hits": 2,          // gating vs non-gating:
                  "write_token_present": false },   // G1–G3, R-05/R-11 — route hits are expected
                                                    // (TC-TRD-29/33); completed sends are the guardrail
                  // canonical counter name: sleeper_live_egress_attempts — it observes backend
                  // live-Sleeper attempts only; app-side prod-contact proof is indirect (R-03 + fixture usernames)
  "cells": [
    { "device": {"udid": "89EEFD08-…", "name": "FTF-iOS18", "os": "18.4"},
      "profile": "standard", "flags": "release", "seed": 1337,
      "flows": [
        { "flow": "smoke/signin.yaml", "cases": ["TC-SGN-01","TC-LPK-02"],
          "verdict": "passed|failed|flaky|skipped-infra|quarantined",
          "attempts": 1, "duration_s": 41, "failure_class": null,   // APP_ASSERT|DRIVER_ERROR|TIMEOUT|CRASH
          "screenshots": ["cells/0/signin/end.png"],
          "failure": null /* {step, message, screenshot, maestro_log, flask_log} */ }
      ] }
  ],
  "totals": { "flows": 50, "passed": 49, "failed": 0, "flaky": 1, "infra": 0, "flake_rate": 0.02 },
  "verdict": "green", "exit_code": 0
}
```
`cases` back-references `test-cases.md` IDs (traceability, M7). Aggregator also maintains `flake-ledger.json` (rolling 10-run pass rate per case) — quarantine decisions are data, not vibes. Per-case JSON lines appended during the run (crash-safe), aggregated at end.

## 4. Core Logic

### 4.1 Matrix runner (pseudocode)

```
main(args):
  cells = expand_matrix(args)                            # §2.1 definitions + flow headers
  groups = group_by(cells, key=(profile, flags_set, seed))   # FTF_FLAGS is per-process:
                                                             # different flag pins ⇒ different Flask
  preflight: parse profiles; seeder --verify each        # exit 3 on schema drift ("re-seed")
             build app unless --no-build; inspect resolved-config.json:
               apiBaseUrl localhost? sentryDsn null? EXPO_PUBLIC_SENTRY_DSN unset?   # else exit 3
  for group in groups (serial per group):
    seed(group.profile, group.seed, group.flags); flask = start_backend(); handshake_or_exit2()
    for device-group in group (parallel, one maestro proc per booted sim):
      simctl boot-verify ×3   # else drop device → its cells SKIPPED-INFRA, matrix continues
      erase+install unless --keep-data
      for flow in group (ordered; composite push steps per §4.5):
        arm_injections(flow.headers)                     # POST /__test__/fail_next|latency
        r = maestro_run(flow, device, timeout)
        POST /__test__/reset; assert whoami.active_injections == []   # teardown verified
        if r.failed and not --no-retry:
          classify(r) → APP_ASSERT|DRIVER_ERROR|TIMEOUT|CRASH   # CRASH: collect .ips first
          simctl shutdown+erase+boot; reinstall; r2 = maestro_run(flow)
          record(flaky if r2.passed else failed)
        else record(r)
    stop(flask); archive(flask.log, seam.log)
  report = aggregate(); evaluate_guardrails()            # any counter ≠ 0 ⇒ exit 4
  write(run-report.json, junit.xml, summary.md); exit(code)
```

### 4.2 Flake-retry policy (R-18)
Retry unit = whole flow, once, on an erased+reinstalled sim (NOT re-seeded — re-seeding would mask state-corruption bugs; the profile DB persists across the retry). Flows are idempotent against their fixture by construction (§4.4 rule 6). Pass-on-retry ⇒ `flaky` (green run, counted toward M4). Fail-twice ⇒ red. Device unresponsive: one erase-recovery per run, then remaining cells SKIPPED-INFRA (exit 2). Ledger escalation: >5% rolling flake ⇒ quarantine tag (runs, doesn't gate) + triage item.

### 4.3 Backend seams (exact)

**(a) Flag pinning — zero code.** Harness composes `flags_base ∪ flag_overrides ∪ --flags` → `FTF_FLAGS` JSON env (existing precedence: defaults → features.json → env, `feature_flags.py:154-180`). Handshake verifies round-trip.

**(b) Fixture seam (in `_sleeper_get`, `server.py:404`):**
```python
_FIXTURES_DIR = os.environ.get("FTF_SLEEPER_FIXTURES_DIR")
_RECORD = os.environ.get("FTF_SLEEPER_RECORD") == "1"

def _sleeper_get(url: str, timeout: int = 15):
    if _FIXTURES_DIR and not _RECORD:
        rel = _normalize(url)                    # strip https://api.sleeper.app/v1/, drop query
        path = Path(_FIXTURES_DIR) / f"{rel}.json"
        _seam_log(url, path.exists())            # → seam.log; miss ⇒ counter (whoami)
        if not path.exists():
            _bump("vcr_misses")
            abort(599, f"fixture-miss: {rel}")   # fail-closed (R-05); X-FTF-VCR-Miss header
        doc = json.loads(path.read_text())
        if isinstance(doc, dict) and "__http_error__" in doc:
            raise urllib.error.HTTPError(url, doc["__http_error__"], "fixture", {}, None)
        return doc
    resp = _live_get(url, timeout)               # existing path
    if _FIXTURES_DIR and _RECORD:
        _write_cassette(_normalize(url), _scrub(resp))   # key-name denylist scrub
    return resp
```
Notes: `__http_error__` envelopes encode 404-behavior fixtures (unknown username → TC-SGN-03). `sleeper_write.py` needs no seam: no token exists in fixtures, and propose additionally fails closed under `FTF_TEST_MODE` (R-11).

**(c) Test-support blueprint (`backend/test_support.py`, mounted only under `FTF_TEST_MODE=1`):** `fail_next {path_pattern, status, count, body?}` — a general **response override**, not only a failure injector: `status` may be ANY code including 2xx, and `body` (optional JSON) is returned as the payload. This serves two families: error-code branches the client switches on (`sleeper_not_linked/expired`, `sleeper_rejected`, `roster_not_found`, `league_not_found`) and **precondition overrides** — e.g. the Send-in-Sleeper cases must first inject `GET /api/sleeper/link → 200 {"connected": true}` (the client branches on `connected` — inventory §3f) to get past the client's link-status gate before `/api/trades/propose` is ever called (TC-TRD-29/33 step 1). **One normative carve-out: overrides matching `/api/trades/propose` refuse 2xx status (error bodies only, blueprint-enforced)** — propose can never be overridden to success, so `completed_proposes` stays a meaningful guardrail. Without an injection, `/api/trades/propose` still fails closed with a bare 599 (R-11 — and TC-TRD-33 asserts the app degrades sanely on exactly that shape) · `latency {path_pattern, ms}` · `reset` (clear injections + in-memory sessions — sessions are a dict, not a table) · `whoami {profile, test_mode, fixtures, active_injections, counters}`. Implemented as a `before_request` hook consulting an in-memory injection table; ~85 lines incl. body support.

### 4.4 Maestro flow conventions (C5)
1. **Selectors:** `id:` only; text-matching solely for asserting load-bearing copy (error/empty/gate strings), never for tapping, never marketing copy.
2. **Waits:** `extendedWaitUntil` at every async boundary — nav 10 s, query render 15 s, session init 30 s, trade-job terminal 60 s. `waitForAnimationToEnd` after tab switches/sheet opens. Zero fixed sleeps (lint). Debounced saves assert terminal UI (verdict rendered / "Saved" pill), not elapsed time.
3. **Nondeterminism:** structural assertions per ADR-9. Fixture-authored content (league/usernames) may be asserted literally.
4. **Gestures:** banned except plain scroll + pull-to-refresh. Mutations via button equivalents (ADR-6).
5. **Headers:** each flow declares `# tc: TC-…`, `# profile: standard`, `# flags: release[+k=v]`, `# injections: [...]` (optional), `tags: [smoke|full|render, <screen>]` — the flow file is the single source; the runner parses headers to build cells.
6. **Idempotence:** mutating flows either restore state or tolerate re-execution (assertions hold on a second run) — keeps §4.2 sound.
7. **Reset:** `launchApp: {clearState: true, clearKeychain: true}` first step unless tagged `persistence` (R-15).
8. Every flow ends `takeScreenshot` (+ before risky assertions).

### 4.5 Composite (runner-interleaved) cases
Push routing (R-19): `[flow: push-arm.yaml (reach state, background app)] → [shell: xcrun simctl push <udid> com.fantasytradefinder.app payloads/match.json] → [flow: push-assert-matches.yaml]`. Same mechanism reserved for future simctl needs (openurl cold-start deep links use `[shell: simctl terminate + openurl] → [flow: assert]`).

## 5. Error Handling & Edge Cases

| # | Situation | Designed behavior |
|---|---|---|
| E-01 | Fixture miss for a Sleeper URL | `_sleeper_get` raises `HTTPError(599)` (as-built — callers surface their normal error paths; no custom response header, the `vcr_misses` counter + seam log entry naming the exact URL are the observables); app shows normal error state; flow fails; run exits 4 |
| E-02 | Expired/invalid session mid-flow | Injection `fail_next /api/rankings 401` → FB-45 guard path asserted (TC-XC-02: re-mint, no sign-out loop) |
| E-03 | Flag-cache staleness | Persistence-tagged case: run with flag ON, relaunch WITHOUT clear against flag-OFF backend, assert surface degrades after revalidate |
| E-04 | Sim boot failure mid-matrix | 3 attempts → device dropped, cells SKIPPED-INFRA, matrix survives, exit ≥2 |
| E-05 | Backend schema migrated after seeding | `--verify` exit 3 in preflight: "re-seed profiles" — never a mystery 500 mid-flow |
| E-06 | Flask dies mid-profile | Remaining cases INFRA-failed + log tail; next profile fresh Flask |
| E-07 | Sleeper API shape change | Prod sees it first; re-record cadence tied to backend Sleeper-code changes; runbook entry distinguishes from regressions |
| E-08 | Slow-load copy (4 s) | `latency 5000ms` on `/api/session/init` etc. in dedicated cases — deterministic, not luck |
| E-09 | Optimistic rollback | `fail_next /api/trades/swipe 500` → card rewinds + toast (TC-TRD-*, TC-MAT-*) |
| E-10 | Poll-failure cap (MAX_POLL_FAILURES=4) | `fail_next /api/trades/status 500 ×5` → job-failed UI, no infinite spinner |
| E-11 | Cross-flow state pollution | Canaries TC-XC-07..09 every P0 run (ADR-5) |
| E-12 | `clearKeychain` misses expo-secure-store | S3 decides; fallback uninstall/reinstall per flow |
| E-13 | Deep link cold vs warm | Separate cases via composite steps (§4.5) |
| E-14 | Trio nondeterminism | Structural assertions stand alone; seed-determinism is a bonus if S2 confirms |
| E-15 | react-query persister restores stale data | Persistence-tagged case: populate cache, relaunch w/o clear, assert refetch-over-stale |
| E-16 | Push without permission/registration | simctl bypasses both — cases documented as rendering+routing only (R-19) |
| E-17 | Demo divergence | Demo cases test demo itself; nothing else uses demo (R-21); reviewer checklist item |
| E-18 | Port occupied | Fixed :**5001** + preflight free-check ⇒ exit 2 (revised 2026-07-11: macOS AirPlay Receiver permanently owns :5000 on this Mac; run.py gained a `PORT` env; dynamic ports still rejected — they'd force a rebuild per port) |
| E-19 | Injection leaks into next case | `reset` after every case; whoami `active_injections==[]` asserted before next — else the PREVIOUS case is INFRA-failed for bad teardown |
| E-20 | Record-mode cassette conflict | Startup abort, never silent overwrite (§2.4) |

## 6. Backward Compatibility

- **`expo prebuild`:** flows, scripts, profiles, `app.config.js` all live outside `mobile/ios/`; testIDs are JS props. Prebuild regenerates the native project untouched. `sim-build.sh` depends only on workspace+scheme names (two variables, documented in header).
- **RN/Expo upgrades:** the S1 spike flow doubles as the post-upgrade canary — run it before any matrix after a bump.
- **App evolution:** inventory regeneration triggers coverage re-audit; new screens add registry IDs (R-13); per-change tax in W4.
- **Backend migrations:** seeder writes through models; manifests carry the schema hash; `--verify` catches drift.

## 7. Testing the Test System

1. **Seeded mutations (M3, `mobile/scripts/mutations.md`):** (a) revert the FB-45 401-guard in `client.ts` ⇒ TC-XC-02 fails; (b) break the FormatGate condition ⇒ its TC fails; (c) swap Check/X wiring ⇒ its TC fails. Run after major suite refactors + quarterly.
2. **Rail drills:** point a build at a fake `onrender.com` URL ⇒ exit 3; delete one fixture ⇒ 599 path, `sleeper_live_egress_attempts` stays 0, exit 4.
3. **Determinism check:** two consecutive `--matrix full --seed 1337` runs on one commit ⇒ identical verdicts (flaky-set delta reported).
4. **Retry-policy probe:** a purpose-built first-attempt-fails flow ⇒ recorded `flaky`, run green.
5. **Seeder pytest:** profile → row counts, unlock thresholds, history spans, DB↔fixture agreement (every DB league has fixture JSON), write-token refusal, inertness (G5).

## 8. Open Questions

Mirrors plan §9 (env transport S1; session-init call set S2; `clearKeychain` semantics S3; EAS parity R-24; DraggableFlatList row visibility; trio-determinism seam worth one more env line?). LLD-specific: `calc.partner-chip.<n>` index qualifier (demo partners are synthetic and stable — accepted exception) · Maestro JUnit fidelity on the current CLI (if per-step detail is thin, aggregator supplements from `--debug-output`).

## Appendix A — testID registry (grammar + first tranche)

**Grammar:** `testID = <screen> "." <element> [ "." <qualifier> ]`; kebab-case segments; `<screen>` from fixed vocabulary (`signin leagues rank-home trios tiers anchors ranks trends trades calc inleague matches league portfolio profile settings feedback sleeper-connect tab topbar rankmenu header push fab`); `<qualifier>` is a stable domain id (`player_id`, `league_id`, `user_id`, tier, position) — **never a list index** (lists reorder), single accepted exception: synthetic stable lists (demo partner chips). State is asserted via distinct IDs or visible text, never encoded in an ID. Registry lives in `mobile/src/components/CLAUDE.md`; PRs adding screens add IDs.

**Shared chrome:** `tab.rank|trades|matches|league` · `topbar.bell` `topbar.bell-badge` · `rankmenu.trios|anchors|tiers|manual|trends|cancel` · `header.back` · `push.priming-enable|priming-later` · `fab.feedback`.

| Screen | testIDs |
|---|---|
| SignIn | `signin.username-input` `signin.continue-btn` `signin.hint-btn` `signin.demo-link` `signin.error-text` |
| LeaguePicker | `leagues.list` `leagues.row.<league_id>` `leagues.row-spinner.<league_id>` `leagues.signout-btn` `leagues.retry-btn` `leagues.empty-text` `leagues.slowload-text` |
| RankHome | `rank-home.card.<trio\|anchor\|tiers\|manual>` |
| Trios | `trios.card.<player_id>` `trios.rank-badge.<player_id>` `trios.confirm-btn` `trios.skip-btn` `trios.speed-toggle` `trios.pos-tab.<qb\|rb\|wr\|te>` `trios.pos-count.<pos>` `trios.format-toggle` `trios.streak-chip` `trios.progress-bar` `trios.unlock-banner` `trios.retry-btn` `trios.info-sheet` |
| Tiers | `tiers.list` `tiers.row.<player_id>` `tiers.chevron-up.<player_id>` `tiers.chevron-down.<player_id>` `tiers.select-toggle` `tiers.select-chip.<player_id>` `tiers.bulk-rank-up|down` `tiers.bulk-tier-up|down` `tiers.target-chip.<tier>` `tiers.select-done` `tiers.save-btn` `tiers.copy-format-btn` `tiers.reset-btn` `tiers.anchors-btn` `tiers.expand-btn` `tiers.pos-tab.<pos>` `tiers.format-toggle` `tiers.sticky-header` `tiers.tier-header.<tier>` |
| Anchors | `anchors.player-card` `anchors.value.<slug×8>` `anchors.skip-btn` `anchors.startover-btn` `anchors.done-card` |
| ManualRanks | `ranks.row.<player_id>` `ranks.rank-input.<player_id>` `ranks.filter.<all\|qb\|rb\|wr\|te>` `ranks.save-pill` |
| Trades | `trades.find-btn` `trades.card-top` `trades.card-give-side` `trades.card-receive-side` `trades.like-btn` `trades.pass-btn` `trades.flag-btn` `trades.fairness-toggle` `trades.outlook-btn` `trades.league-pill` `trades.subnav.<trades\|portfolio\|calculator>` `trades.queue-btn` `trades.queue-bar` `trades.queue-sendall` `trades.swap-btn` `trades.target-toggle` `trades.target-picker-btn` `trades.target-chip.<player_id>` `trades.send-sleeper-btn` `trades.hide-btn` `trades.progress-strip` `trades.empty-text` `trades.format-gate` `trades.switch-overlay` |
| Calculator | `calc.mode-tab.<league\|live\|demo>` `calc.format-chip.<1qb\|sf>` `calc.partner-chip.<n>` `calc.side-a-add` `calc.side-b-add` `calc.side-a-player.<player_id>` `calc.side-b-player.<player_id>` `calc.side-a-remove.<player_id>` `calc.side-b-remove.<player_id>` `calc.picker.search` `calc.picker.row.<player_id>` `calc.share-btn` `calc.clear-btn` `calc.verdict` `calc.suggestion-card.<n>` `calc.retry-btn` |
| InLeague | `inleague.opponent-row.<user_id>` `inleague.opponent-unranked-dot.<user_id>` `inleague.verdict` `inleague.send-btn` |
| Matches | `matches.segment.<mutual\|awaiting>` `matches.filter.<league_id\|all>` `matches.card.<n>` `matches.dismiss.<n>` `matches.empty-text` |
| League | `league.hero` `league.switch-btn` `league.members-chip` `league.matches-tile.<kind>` `league.coverage-meter` |
| Settings/misc | `settings.signout` `settings.switch-league` `settings.notif.<pref>` `settings.steer-slider` `profile.hero` `portfolio.row.<player_id>` `feedback.severity.<bug\|polish\|idea>` `feedback.note-input` `feedback.send` |

Second tranche (~30 more: Trends, SleeperConnect, sheets, banners, toasts-as-text) follows the grammar in W0.4. **RN caveat (budgeted):** containers with implicit `accessible={true}` swallow child IDs on iOS — fix pattern `accessible={false}` on the container; `DraggableFlatList` rows are the likeliest offender (S1/W0.4 verify; drag cases are NOT-AUTOMATE regardless).
