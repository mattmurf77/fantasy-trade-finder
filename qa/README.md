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
| **Config & flags** | `model_config` (77 keys), `config/features.json` flag matrix — engine behavior is flag-routed; tests must pin flags explicitly |
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

## Test ID convention

`TC-<AREA>-<NNN>` where AREA ∈ ENG (trade engine), RNK (ranking/Elo), API, DB,
INT (Sleeper/external), CFG (flags/config), SEC, PERF, E2E (full stack).
