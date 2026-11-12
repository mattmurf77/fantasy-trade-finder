# Feature Scope — Rest-of-season forecasts for ESPN and MFL leagues

**Date:** 2026-11-11
**Entry point:** direct ask (operator: "Add the MFL standings read to pull max PF and build rest of season projections for both platforms.")
**Builder:** design session on `feat/forecasts-espn-mfl` (design only; builders TBD per [design.md §7](design.md#7-build-plan))
**Operator sign-off on waivers:** needed for the two waivers below (§1(c) partial, §3 TestFlight); and decisions 1–6 in [design.md §8](design.md#8-open-decisions-for-the-operator) before build item B finishes

Design: [design.md](design.md). Built on the open median PR #659.

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [x] **(b) Existing events cover it.** The forecast is a server batch with no new client
  interaction. Run outcomes are already durable in `league_projection_runs`
  (`status`, `reason`), which answers "how many ESPN/MFL forecasts complete, and why do the
  rest fail?" by a read-only query. The new fields `platform` and `draft_order_rule` on the
  result make that query split by platform. Outbound ESPN/MFL calls are captured by the
  existing `obs.api_events` instrumentation inside `espn_service.fetch_league` and
  `mfl_service._fetch_one` (source `espn` / `mfl`, export type, status, latency; never cookies).
- [ ] **(c) WAIVED:** n/a.

## 2. Schema & flag scope

- **New/changed tables or columns:**
  - `leagues.draft_order_rule` TEXT NULL — `maxpf_lowest_first` | `reverse_standings` | NULL (= platform default: Sleeper and MFL max PF, ESPN reverse standings). Plus the `_migrate_db` entry. → `docs/data-dictionary.md`
  - `league_projection_targets.platform_cache_json` TEXT NULL — reconciled per-week MFL team totals and weekly optimum for completed weeks, so each completed week is read once. → `docs/data-dictionary.md`
  - No new table. Snapshots and results stay in `league_projection_runs`.
- **New/changed feature flags:** `league.projections_espn`, `league.projections_mfl`. Both default **off**. Each also requires the existing `league.projections` and `league.projections_provider_approved`, which are both off in `config/features.json` today. Added to `FLAG_KEYS`, `DEFAULT_FLAGS`, `config/features.json` and `backend/tests/fixtures/flags/release.json`. → `docs/config-reference.md`. **Graduation:** each platform's recorded-league reconciliation passes exactly (design §6.1), and the operator reviews one real forecast per platform.
- **New env vars / `model_config` keys:** none. **Rollback lever:** flip the platform flag off. Queued runs for that platform then fail at admission, and saved forecasts stay readable as stale.

## 3. Evidence scope

- [ ] **Structural guard:** none. No mobile change is planned. The existing
  `LeagueProjectionSection` already renders whatever forecast the server returns. If the
  pick pricer or the section later reads `draft_order_rule` or the playoff block, that change
  brings its own `check-*.js`.
- [x] **Unit tests (backend pytest):** `test_league_projection_contract.py` (facts schema and
  Sleeper byte-identical snapshot digests), `test_league_projection_draft_rules.py`,
  `test_league_projection_def_slot.py`, `test_league_projection_platforms.py` (flags,
  dispatch fairness), `test_league_projection_espn.py`, `test_league_projection_mfl.py`, plus
  scoring-table tests. Each names a sabotage in [design.md §7](design.md#7-build-plan). The full
  existing `test_league_projection_*` suite must stay green.
- [x] **Code-walk proof:** required at build time for (1) the adapter split leaving the
  Sleeper path unchanged, (2) the per-user dispatch de-dup, and (3) no cookie, SWID or
  username reaching a log line or a snapshot. Each is a file:line trace in the build evidence.
- [x] **Recorded-league check (replaces a runtime capture):** one consenting ESPN league and one
  MFL league are recorded once by an operator-run, stdlib-only script. The recorded data must
  reconcile exactly: W/L/T, PF and PA rebuilt from the schedule, and for MFL, Σ weekly optimum
  = `pp`. Logged in TEST_LEDGER.
- [ ] **Manual TestFlight checklist: WAIVED because** there is no mobile change. The server
  output for ESPN/MFL leagues is the same schema the app already renders, and the forecast stays
  dark behind the four flags. If the operator wants a device look before flipping a platform
  flag, the check is: open an ESPN-linked league's Team page → the projection section shows
  playoff odds and a draft-slot line, not "Sleeper only".
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | at build | `/api/leagues/<id>/projection-runs*`: ESPN/MFL leagues no longer return `sleeper_only` when their flag is on; the result gains `platform`, `draft_order_rule`, `seeding_rule` and `league_format`; new refusal reasons |
| `living-memory/LLD.md` | at build | the forecast's platform-adapter convention (adapters read facts; `assemble` is platform-free; the simulator never branches on platform) |
| `docs/architecture.md` | at build | league_projections module wiring: `adapters/` + `assemble.py`; ESPN and MFL background readers |
| `living-memory/HLD.md` | at build | the first background ESPN reader (a new egress pattern); relation to device-side auth G1 |
| `docs/cross-client-invariants.md` | n/a because no client constant changes; the `draft_order_rule` enum is server-only until a client reads it |
| `docs/glossary.md` | at build | "potential points (MFL `pp`)", "reverse standings (draft order)", "draft-order rule" |
| ADR or `DECISIONS.md` entry | at build | the operator's answers to design §8, and the choice of Sleeper projections with translated scoring |
| `docs/integrations/espn.md`, `docs/integrations/mfl.md` | at build | new views and exports, the background reader, request counts and the safe-to-log split |
| `docs/data-dictionary.md`, `docs/config-reference.md` | at build | per §2 |

## 5. Ship gate declaration

- **CI green:** `backend-tests`, `mobile-typecheck` (unchanged) and `maestro-testid-lint`, all passing on the pushed sha
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming the new test files, their sabotage runs and both recorded-league reconciliations
- **TestFlight verification:** waived (§3)
- **Express lane declared by the operator?** No. Express would not be admissible anyway: this changes schema, flags and an API contract.
