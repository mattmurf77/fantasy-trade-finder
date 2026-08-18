# Backend QA Charter — Fantasy Trade Finder

Role: backend QA for the trade engine, APIs, and DB. Goal: operability, performance,
consistency, and proactive bug discovery across each layer individually and the full stack.

## Scope

| Area | What's covered |
|---|---|
| **Trade engine** | `trade_service.py` (v1 legacy + v2), `trade_optimizer.py` (v3), `trade_narrative.py` — inputs (Elo maps, rosters, config, flags), gates (fairness, surplus, Elo-gap, lineup feasibility), scoring (mismatch/fairness/composite), outputs (TradeCard shape) |
| **Ranking model (input quality)** | `ranking_service.py` Elo math, K-factors, 3-player decomposition, confidence counts, tier bands — the engine is only as good as its inputs |
| **APIs** | All `backend/server.py` routes: contracts, envelopes, status codes, naming conventions, auth, doc parity with `docs/api-reference.md` |
| **DB** | Schema vs `database.py` vs `docs/data-dictionary.md`, column/format consistency, FK integrity, index coverage, migration idempotency, SQLite↔Postgres parity |
| **External integration** | Sleeper API passthrough (timeouts, caching, null/string-ID gotchas G-003..G-008), DynastyProcess CSV loader name-matching |
| **Async/infra** | In-memory trade job queue, session store, cron endpoints (`/api/cron/*`), push notification dedup/queue |
| **Config & flags** | the `model_config` table + the `config/features.json` flag matrix (both large and growing — counts live in [`docs/config-reference.md`](../docs/config-reference.md), not here) — engine behavior is flag-routed; tests must pin flags explicitly |
| **Security/operability** | Auth coverage on mutating routes, error-message leakage, rate limiting, debug endpoints |
| **Cross-client invariants** | Enum strings, K-factors, tier cutoffs per `docs/cross-client-invariants.md` — backend is the source of truth the mobile app consumes |
| **Performance** | Per-request budgets (see below), cold-start, enumeration budgets, connection pool behavior |

## Ways of working

1. **Test cycles, not ad-hoc pokes.** Each cycle picks a charter area, writes test cases
   from the template (`TEST_CASE_TEMPLATE.md`), executes, and files a findings report.
2. **Never write to the live DB** (`data/trade_finder.db`). Engine/DB tests run against
   in-memory SQLite fixtures (matching `backend/tests/` convention). Read-only queries
   against the live DB are allowed for data-quality audits.
3. **Pin flags and config.** Every test case states its feature-flag and `model_config`
   assumptions; flag-routed behavior (v2 vs v3 vs legacy) is tested per-route and at
   the flip boundary (kill-switch regression).
4. **Full-stack tests run against a local Flask instance** on a copied DB, exercising
   the same endpoints the mobile client calls (per `mobile/src/api/client.ts`), with
   mobile timeout budgets as the pass bar.
5. **Findings are triaged** P0 (prod-breaking / security / data corruption — stop the line),
   P1 (wrong results or contract violation), P2 (inconsistency, doc drift, perf smell),
   P3 (observation / improvement idea). P0/P1 get surfaced immediately, not batched.
6. **Performance budgets** (working defaults until the operator overrides):
   warm API GET p95 < 500ms local; `/api/trades/generate` end-to-end < 30s (mobile
   timeout); per-opponent engine budget honored (1s / 200k iterations); session_init < 5s warm.
7. **Doc drift is a finding.** Per CLAUDE.md, code↔docs sync is a project requirement;
   mismatches in api-reference / data-dictionary / config-reference are filed as P2.
8. **Ledger discipline.** Executed cases and outcomes are appended to
   `living-memory/TEST_LEDGER.md`; reusable automated cases graduate into `backend/tests/`.

## How QA actually runs today (as of 2026-08-15)

> **The Maestro / simulator lane is retired.** Operator decision **D-056** (2026-08-15,
> Status: Active — `living-memory/DECISIONS.md`): no Maestro flow authoring, extension, or
> execution, and no simulator captures, for any change in any pipeline. `FTF_SKIP_SIM_GATE=1`
> is the standing posture for the pre-push hook. Do not produce `qa/sim-runs/last-sim-run.json`;
> do not write a plan that budgets Maestro work.

Four lanes. Know which one you are in.

| Lane | Where | Runs | Gate |
|---|---|---|---|
| **Automated backend tests** | `backend/tests/` (pytest) | GitHub Actions on every PR + push to `main` ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) | Must be green to merge |
| **Mobile typecheck + testID lint** | `mobile/`, `mobile/scripts/testid-lint.sh` | Same CI workflow — `testid-lint` stayed in CI under D-056 | Must be green to merge |
| **Structural check suites** | `mobile/tests/check-*.js`, `mobile/scripts/check-contrast.js` | `npm run test:<name>` in `mobile/`; ~22 suites | The primary automated evidence for client behavior post-D-056 |
| **Charter test cases** | `qa/<area>/tc_*.py` here | By hand, per test cycle | Not in CI — findings go to `results/` + TEST_LEDGER |

Running a charter case:

```bash
python qa/sec/tc_sec_001.py        # from the repo root, backend env active
```

Each case calls `lib/harness.py` to copy the live DB into `qa/<area>/scratch/`, boot a
local Flask against the copy, and drive it over HTTP. Exit code is the verdict; a run
JSON lands beside the scratch DB. Nothing here touches `data/trade_finder.db` for writes.

## Proving behavior without the simulator

D-056 replaced the runtime lane with two things, both of which are now expected deliverables:

1. **Written code-walk proof** — a file:line-cited trace through the commit sequence, standing in for what a sim capture used to show.
2. **A concrete manual TestFlight checklist for the operator** — specific enough to actually catch a runtime regression, because it is now the only thing that will.

## Historical evidence — do not treat as current

| Path | Frozen at | What it was |
|---|---|---|
| `qa/sim-runs/` (gitignored, per-machine) | last run **2026-08-15**, `last-sim-run.json` sha `44c8bbf`, tier 2, result `fail` | Pre-ship simulator-gate evidence. Kept as a record; the gate it fed is retired |
| [`mobile/.maestro/`](../mobile/.maestro/README.md) | — | Flow definitions. **Kept, never run** — they document intended behavior, per D-056 |
| [`screens/`](../screens/CLAUDE.md) | 2026-08-11 | The screen-capture library, frozen because captures stopped |

`githooks/pre-push` still exists and still checks for the artifact; the standing answer
is `FTF_SKIP_SIM_GATE=1` with a one-line note in `living-memory/TEST_LEDGER.md`.
[`docs/runbook.md` § Pre-ship simulator gate](../docs/runbook.md) still reads as live —
D-056 says it should carry a historical banner; it does not yet. Trust D-056.

## Executed test cases

Write-ups in [`results/`](results/). All executed 2026-06-11 unless a newer run is logged
in [`living-memory/TEST_LEDGER.md`](../living-memory/TEST_LEDGER.md), which is the
authority on current posture — this table is the index, not the score.

| Case | Layer | Subject | Recorded status |
|---|---|---|---|
| [TC-ENG-001](results/TC-ENG-001.md) | engine | Trade-engine kill-switch regression (legacy / v2 / v3) | PASS 30/30 |
| [TC-ENG-002](results/TC-ENG-002.md) | engine | Fairness-gate golden fixtures (1-for-1 gate, package discount) | PASS 8/8 |
| [TC-ENG-003](results/TC-ENG-003.md) | engine | Engine gate config-responsiveness (admin tuning surface) | PASS 4/4, in CI |
| [TC-ENG-004](results/TC-ENG-004.md) | engine | 3-team cycle clearing (`find_three_team_cycles`) | PASS 4/4, in CI |
| [TC-RNK-001](results/TC-RNK-001.md) | ranking | Elo math golden fixtures | PASS 6/6, in CI |
| [TC-API-001](results/TC-API-001.md) | api | API consistency + doc-drift audit | COMPLETE — 7/8; the 1 FAIL is the surfaced naming finding |
| [TC-API-002](results/TC-API-002.md) | api / security | Public-route auth-intent audit + abuse surface | PASS 4/4 |
| [TC-CFG-001](results/TC-CFG-001.md) | config | Feature flags + `model_config` live-tuning contract | PASS 11/11 |
| [TC-DB-001](results/TC-DB-001.md) | db | Schema integrity, migration idempotency, SQLite↔Postgres parity | PASS 24/24 |
| [TC-DB-002](results/TC-DB-002.md) | db | Concurrency, write integrity, recency bounds | PASS 5/5 |
| [TC-INT-001](results/TC-INT-001.md) | integration | Sleeper-boundary input handling (G-003..G-008) | PASS 8/8 |
| [TC-SEC-001](results/TC-SEC-001.md) | security | Operator-endpoint auth enforcement (cron-secret + session gate) | PASS 35/35 |
| [TC-PERF-001](results/TC-PERF-001.md) | perf | Cold-start, warm latency, concurrent load, budgets | PASS 9/9 |
| [TC-E2E-001](results/TC-E2E-001.md) | full-stack | Happy path: session_init → rank → generate → swipe → match → disposition | PASS 67/67 |
| [TC-E2E-002](results/TC-E2E-002.md) | full-stack | Restart resilience (in-memory session + trade-job loss) | PASS 9/9 |
| [TC-E2E-003](results/TC-E2E-003.md) | full-stack | Superflex (`sf_tep`) format path + format isolation | PASS 8/8 |
| [TC-E2E-004](results/TC-E2E-004.md) | full-stack | Cross-league flow (matches/all, awaiting, portfolio, disposition) | PASS 9/9 |

Note: TC-ENG-002/003/004 and TC-RNK-001 have write-ups here but no `tc_*.py` — their
executable form graduated into `backend/tests/` (which is what CI runs), per way-of-working
8 above. A missing script under `qa/<area>/` is not a missing test. TC-INT-001's script
lives in `qa/sec/`, not a `qa/int/` directory.

## Related checklists

- [accessibility-release-checklist.md](accessibility-release-checklist.md) — per-release
  mobile a11y regression pass (VoiceOver walk, AX5 screenshots, Reduce Motion / Increase
  Contrast, token contrast). Client-side scope, but run records land in `qa/results/`
  and findings use this charter's P0–P3 triage. Post-D-056 this is an **operator device
  pass**, not a simulator pass; `npm run test:contrast` covers the token half.
- [teardown-remediation-qa.md](teardown-remediation-qa.md) — device-QA tracker for the
  30 flag-gated features (+ unflagged fixes) from the app-teardown wave (branch
  `teardown-remediation`). Per-feature verify steps, cross-feature interaction watch-list,
  and an issue log. Catalog: [`../FEATURES.md`](../FEATURES.md).

## Test ID convention

`TC-<AREA>-<NNN>` where AREA ∈ ENG (trade engine), RNK (ranking/Elo), API, DB,
INT (Sleeper/external), CFG (flags/config), SEC, PERF, E2E (full stack).
