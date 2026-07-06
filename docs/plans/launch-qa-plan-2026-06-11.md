# Launch QA Plan — Agent Roles & Test Phases
*Created 2026-06-11, branch `trade-engine-v2`. Goal: catch all bugs, hardcoded values, and API errors before launch.*

## Scope

Five surfaces, one contract:

| Surface | Code | Risk profile |
|---|---|---|
| Backend | `backend/server.py` (88 routes), services | Error paths, auth on admin/cron routes, Sleeper API failures |
| Web SPA | `web/js/app.js` (5.7k lines), 8 HTML pages | Contract drift, hardcoded URLs, unhandled fetch errors |
| Mobile | `mobile/src/` (15 screens, 11 API modules) | Missing loading/error/empty states, stale contract assumptions |
| Extension | `extension/` (MV3) | Permissions, hardcoded endpoints, content-script breakage |
| Config/data | `config/features.json`, `data/trade_finder.db`, docs | Flag drift, schema vs docs drift, SQLite→Postgres portability |

## Phase 0 — Baseline (deterministic, no agents)

Before fanning out, establish a green baseline so agent findings aren't noise on top of known breakage:

1. `pytest backend/tests/` — all 18 test files must pass.
2. Boot `run.py`, confirm the server starts clean (no tracebacks, no missing-config warnings).
3. Snapshot route inventory (88 routes) and feature-flag state for later phases.

**Gate:** anything red here gets fixed before Phase 1.

## Phase 1 — Parallel static audit (6 agent roles)

Each agent sweeps independently and returns structured findings: `{file, line, severity (P0–P3), category, description, suggested_fix}`. Observation only — no edits.

### R1 — Hardcoded Values Auditor
Hunts: `localhost`/`127.0.0.1`/`:5000` URLs in clients; test/seed user IDs and league IDs left in code (`scripts/seed_test_user*.py` values leaking into app code); magic numbers that should be in `model_config` or `tier_config.json`; absolute file paths; embedded API keys or tokens; debug flags left on; `tmp_check_db*.py`-style scratch files that shouldn't ship.

### R2 — API Contract Auditor
Cross-references all 88 routes in `server.py` against every caller: `web/js/app.js`, `mobile/src/api/*.ts`, `extension/*.js`, and `docs/api-reference.md`. Hunts: params a client sends that the backend ignores (or vice versa), response fields a client reads that the backend doesn't always return, inconsistent error-response shapes, routes documented but removed, routes added but undocumented, enum strings that differ across surfaces.

### R3 — Error Handling & Resilience Auditor
Hunts: Sleeper API calls without timeout/retry/failure handling; unhandled exceptions that 500 instead of returning structured errors; empty-roster / new-user / zero-matchup edge cases; client fetch calls with no `.catch` or error UI; division-by-zero or empty-list risks in `ranking_service.py` and `trade_service.py` math; Anthropic API optional-dependency path when `ANTHROPIC_API_KEY` is unset.

### R4 — Security Auditor
Hunts: auth on `/api/feedback/admin` and `/api/cron/*` (CRON_SECRET enforcement on every admin route, constant-time comparison); SQL injection surface in SQLAlchemy Core usage (raw `text()` with interpolation); secrets committed anywhere in history-visible files; CORS configuration; extension manifest permissions broader than needed; XSS in the web SPA (innerHTML with user/Sleeper data); rate limiting on expensive endpoints (trade generation).

### R5 — Config & Feature Flag Auditor
Cross-references `config/features.json` ↔ `backend/feature_flags.py` defaults ↔ every client-side flag check. Hunts: flags checked in code but missing from config (silently false); flags in config no longer read anywhere (dead); v2-engine flag combinations that were never tested together (e.g., `trade_engine.v2` + legacy `trade_math.*` flags); env vars read in code but missing from `docs/config-reference.md`; the known 1-for-1 fairness-gate watch item.

### R6 — Cross-Client Consistency Auditor
Enforces `docs/cross-client-invariants.md`: tier colors, K-factors, thresholds, enum strings must match across backend, web, mobile, and extension. Also checks docs drift per the CLAUDE.md table: schema vs `data-dictionary.md`, routes vs `api-reference.md`, architecture doc vs actual module wiring.

## Phase 2 — Adversarial verification

All Phase 1 findings are deduped (same file+line+category), then each finding goes to a skeptic agent prompted to **refute** it (read surrounding code, check whether the value is actually configurable elsewhere, whether the error path is handled upstream, etc.). Only confirmed findings survive. This kills the false-positive noise that makes big audits unactionable.

## Phase 3 — Dynamic testing (4 agent roles)

### R7 — Live API Smoke Tester
Boots the Flask server against a copy of `data/trade_finder.db`. For every route: valid request, malformed body, missing auth, wrong method, nonexistent IDs. Asserts status codes and that error responses are structured JSON (never HTML tracebacks). Specifically exercises trade-generation endpoints with edge rosters (empty, single-player, all-picks).

### R8 — Web UI Flow Tester
Drives the SPA via browser preview against the live local server: Sleeper login flow, ranking matchups (including rapid swiping), trade discovery, profile, tiers, trends pages. Checks console for errors, network tab for failed/4xx calls, and that every error state renders something (not a blank page).

### R9 — Mobile Crash-Risk Reviewer
Static review of all 15 screens + hooks + state: missing loading/error/empty states, unguarded `.map`/property access on API data, unhandled promise rejections, navigation params assumed present, stale contract usage found by R2. (Simulator E2E is out of scope for agents; this is the highest-value static substitute.)

### R10 — Extension Reviewer
Manifest permissions audit, hardcoded endpoint check, content-script selector fragility against Sleeper's DOM, background/popup message-passing error paths.

## Phase 4 — Triage & fix loop

- **P0 (launch blocker):** crashes, data corruption, auth bypass, hardcoded dev URLs in shipping clients → fix on this branch, each fix gets a regression test.
- **P1 (fix before launch):** broken error states, contract mismatches with user-visible impact → fix on this branch.
- **P2/P3:** log as issues with the finding details; do not fix pre-launch (surgical-changes principle).

Fixes are implemented by separate fixer agents with disjoint file ownership, then re-reviewed.

## Phase 5 — Regression & launch gate

1. Full `pytest` rerun — green.
2. R7 smoke rerun — green.
3. Docs updated per CLAUDE.md trigger table for any code changed in Phase 4.
4. Launch checklist:
   - [ ] No P0/P1 findings open
   - [ ] All clients point at production API URL via config, not hardcode
   - [ ] CRON_SECRET rotated (pending item from 2026-06-10) and enforced on all admin/cron routes
   - [ ] Feature flags set to intended launch values; dead flags removed or documented
   - [ ] Scratch files (`tmp_check_db*.py`, `dump_mismatches.py`, workspace dirs) excluded from deploy
   - [ ] DB migrations / Postgres `DATABASE_URL` path verified if launching on Postgres

## Execution notes

- Phases 1 and 3's static roles (R9, R10) can run concurrently; R7/R8 need the Phase 0 server baseline.
- Run as an orchestrated workflow: Phase 1 fans out 6 auditors → dedup barrier → Phase 2 verifiers per finding → report. Phase 3–5 run after human review of the confirmed findings.
- Estimated agent count: ~10 role agents + 1 verifier per confirmed finding (typically 20–60).
