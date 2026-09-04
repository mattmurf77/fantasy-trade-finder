# backend/ — Notes for Claude

Python 3 / Flask + SQLAlchemy **Core** (no ORM models, no Alembic). 45 top-level modules plus three
packages (`outlook/`, `eval/`, `tools/`), a `scripts/` dir, and a 175-file test tree. All figures in
this doc are derived from **`origin/main`**, 2026-08-18 — if your checkout disagrees, fetch before
you trust it.

Everything is imported as the `backend` package from the repo root (`from .database import …`
inside, `import backend.server` from tests). There is no `setup.py` / install step —
`pyproject.toml` is pytest config only.

- [Entry points](#entry-points)
- [Module map](#module-map)
- [Subpackages](#subpackages)
- [Identity: account vs league](#identity-account-vs-league)
- [Adding a route](#adding-a-route)
- [Database](#database)
- [Config, flags, experiments](#config-flags-experiments)
- [Tests](#tests)
- [Gotchas](#gotchas)
- [Docs you must keep in sync](#docs-you-must-keep-in-sync)

---

## Entry points

| Command | What it does |
|---|---|
| `python3 run.py` (repo root) | Flask dev server on **:5000** (`PORT` overrides; the UI-test harness uses :5001 because macOS AirPlay squats on 5000). Imports `backend.server:app`, warms the Sleeper player cache from disk, syncs players to the DB. Auto-reloader is disabled under `FTF_TEST_MODE`. |
| `gunicorn run:app --workers 1 --timeout 120` | Production (Render — see `render.yaml`). **One worker on purpose**: `server.py` keeps in-process state. |
| `python3 -m pytest backend/tests -q` | The suite. See [tests/CLAUDE.md](tests/CLAUDE.md). |
| `python3 -m backend.eval.replay --db … --scorer …` | Offline deck-eval CLI (`backend/eval/`). |
| `python3 backend/tests/fixtures/seed_ui_test_db.py --profile <name>` | Seeds the hermetic UI-test world (DB + Sleeper cassettes + player cache + DP values CSV). |

## Module map

**The two giants.** `server.py` (~25.1k lines) and `database.py` (~12.4k lines) hold most of the
backend. Never read either end-to-end — grep for the route path or the table name.

| File | Lines | Responsibility |
|---|---:|---|
| `server.py` | 25.1k | **Every HTTP route** — 186 `@app.route` decorators over 180 distinct paths — on one `Flask` app. The only blueprint is `test_support`'s `/__test__/*`, installed via `_test_support_mod.install(app, …)` and inert unless `FTF_TEST_MODE=1`. Also owns the session store, the Sleeper HTTP client (`_sleeper_get`), the universal player pool, and the background threads (trade jobs, `_cleanup_loop`, players refresh, roster-history daemon). Grep `@app.route("/api/…`. |
| `database.py` | 12.4k | 63 SQLAlchemy Core `Table` definitions + every query helper + `_migrate_db()` (idempotent try/except `ALTER TABLE`s — **no migration framework**) + `init_db()`. Three engines: `engine`, `ingest_engine`, `ro_engine`. |
| `trade_service.py` | 5.0k | Trade-card generation: pair enumeration, package building, fairness gates, mutual-gain scoring. `_DEFAULT_CFG` + `reload_config()` read the `model_config` table. Routes to `trade_gen_v2` when `trade_gen.v2` is on. |
| `trade_gen_v2.py` | 1.0k | **Divergence-driven, dual-board, staged generation** (flag `trade_gen.v2`, default OFF). Ships *alongside* the existing generator — when the flag is off this module is never imported and every legacy/v2/v3 path is byte-identical. |
| `bakeoff_profiles.py` | 80 | **Three-model bake-off arm definitions.** `MODEL_A_PROFILE` — the pinned kill-value set that *is* arm A (the pre-2026-08-16 engine), golden-tested against SHA `92c31d5` — and `model_a()`, which applies it together with `trade_service.r4_bypass()`. Inert until a caller enters the context. |
| `trade_policy.py` | 0.9k | **The ONE trade-policy evaluator** (2026-09-04, dark behind `trade.valuation_telemetry` / `trade.personal_market_policy_v1`). Consensus as a non-bypassable market floor, two-sided personal opportunity as the ordering signal, symmetric ranking confidence (D-180); `policy_variant` recorded orthogonally to `model_arm` (D-181). A **leaf** like `suggestion_telemetry.py` — never imports `server`, and imports `trade_service`/`trade_optimizer` lazily inside functions (both directions cycle). Called by v2, v3 and one choke point in `_run_trade_job` on the final deck. |
| `trade_optimizer.py` | 864 | Trade engine **v3** — exact per-pair package optimizer, lineup feasibility, 3-team cycles, sweeteners (flag `trade_engine.v3`). |
| `ranking_service.py` | 1.7k | Elo math for 2-player and 3-player (trio) matchups; tier bands from `tier_config.json`; same `reload_config()` pattern. |
| `value_model.py` | 812 | F6 learned acceptance heads × V-vector (flag `deck.value_model`). Model store at `VALUE_MODEL_DIR`. |
| `taste_service.py` | 548 | F5 per-user decayed attribute-preference vectors (flag `deck.taste_vectors`). |
| `smart_matchup_generator.py` | 550 | Optional Claude-API matchup selection; algorithmic fallback when `ANTHROPIC_API_KEY` is unset. |
| `trade_narrative.py` | 168 | Template-based (no LLM) trade rationale for `TradeCard.narrative`. |
| `suggestion_telemetry.py` | 456 | Counterfactual logging + **ghost holdout** + executed-trade tagging (flag `suggestion.telemetry`). A leaf: imports flags/database only, never `server.py`; `server.py` calls it from exactly two seams. |
| `pick_values.py` | 317 | Shared draft-pick value ladder. Deliberately standalone so `database.py` can price picks without importing `server.py` (it imports `trade_service` lazily). |
| `data_loader.py` | 873 | Fetches the DynastyProcess consensus CSVs (`values-players.csv`, plus `values.csv` read only for `pos == "PICK"`) + optional KTC blend, and seeds Elo. Seams: `FTF_DP_VALUES_FILE`, `FTF_DP_PICK_VALUES_FILE`, `FTF_KTC_VALUES_FILE`. |
| `dp_values_history.py` | 355 | Dated DP value boards — `values_as_of(date)`; backs backtests. |
| `feature_flags.py` | 935 | 171 flag keys, all defaulting **False** in code; `config/features.json` (or `FTF_FLAGS`) flips them. |
| `experiments.py` | 742 | Layered A/B + multivariate assignment: deterministic, stateless, fail-open. Tester allowlist. |
| `entitlements.py` | 362 | `pro` / `ad_free` resolution, billing-webhook projection, manual grants. |
| `accounts.py` | 999 | Apple/Google identity-token verification against provider JWKS, account lifecycle, `delete_user_data`. |
| `sleeper_roster.py` | 91 | **The ONE roster→user predicate.** See [Identity](#identity-account-vs-league) — read that before touching any "is this my team?" comparison. |
| `roster_history.py` | 268 | ADR-011 league-state history capture (#46 Wrapped). One idempotent writer behind three triggers: on-sync, weekly daily-tick, and `POST /api/cron/roster-snapshot`. `team_value` **must** come from `compute_power_rankings`, never a fresh summation. |
| `analytics_ingest.py` | 507 | `POST /api/events` pipeline (validate → dedupe → PII scrub → rate limit → single txn). |
| `analytics_taxonomy.py` | 1.2k | **Single source of truth for event names.** Spec an event here *before* firing it anywhere; new client event types need a tracking-plan addendum first. |
| `analytics_queries.py` | 1.7k | Report layer — parameterized dual-dialect SQL on the read-only engine. |
| `analytics_stats.py` | 331 | Pure stdlib statistics (z-tests, SRM, ECE). Asserted to 1e-9 against `tests/fixtures/stats_golden.json`. |
| `api_observability.py` | 435 | Inbound + outbound API event capture into `user_events` (flag `obs.api_events`). |
| `espn_service.py` / `espn_write.py` | 961 / 448 | ESPN read adapter — **and the shared DynastyProcess player-ID crosswalk that MFL and Fleaflicker also import** — plus the authenticated propose-trade writer. |
| `mfl_service.py` / `mfl_write.py` | 846 / 373 | MyFantasyLeague read + **officially sanctioned** write API. HTTP is injected via `_opener`, so it is offline-testable. |
| `fleaflicker_service.py` | 237 | Fleaflicker public JSON read adapter. |
| `sleeper_write.py` | 398 | ⚠️ ToS-adverse: reproduces Sleeper's private `propose_trade` GraphQL mutation. Flagged beta. |
| `sleeper_trades_service.py` | 144 | Captures completed Sleeper league transactions (market data). |
| `trade_block_service.py` | 184 | Reads Sleeper Trade-Center block state via the public GraphQL endpoint. |
| `draft_board_service.py` | 1.5k | The whole `GET /api/draft/board` payload (`schema: 1`), Sleeper + MFL. Threads an injectable `_opener` down to `mfl_service`. |
| `mock_draft_service.py` | 1.7k | FTF-native mock draft engine + CPU drafter calibration. |
| `draft_status.py` | 316 | One shared "has this league's rookie draft happened?" detector. |
| `free_agent_service.py` | 223 | Free-agent finder behind `/api/league/free-agents`. |
| `power_rankings.py` | 273 | Pure roster-value power-ranking computation (the route loads the data). |
| `trends_service.py` | 758 | Risers/fallers, contrarian, consensus-gap helpers for `/api/trends/*`. |
| `rankings_import.py` | 308 | Pure parser/matcher for paste-a-table rankings import (flag `ranks.import`). |
| `og_image.py` | 720 | Pillow-rendered 1200×630 OG share cards. |
| `wrapped_collector.py` | 70 | Best-effort append to `wrapped_events`; every DB call swallowed so it can't break a user flow. |
| `profile_session_init.py` | 210 | Standalone profiler for `/api/session/init` — run directly, not imported by the app. |
| `test_support.py` | 382 | ⚠️ **Production module** — the `FTF_TEST_MODE` `/__test__/*` blueprint. |
| `test_users.py` | 184 | ⚠️ **Production module** — the `qa_*` stage-user spawner. |
| `tier_config.json` | — | Per (format, position) tier bands, loaded by `ranking_service`. Cross-client contract. |

## Subpackages

**`outlook/`** — playoff/championship odds (feedback #169, flag `outlook.odds`). Five phases, each
behind a `typing.Protocol`, wired from registries in `pipeline.py`; nothing downstream imports a
concrete provider. Phase 2 (`strength.py`) is the swap seam, selected by
`FTF_OUTLOOK_STRENGTH_SOURCE`. Full detail, provider-authoring steps and the "don't tidy this" list:
[outlook/CLAUDE.md](outlook/CLAUDE.md).

**`eval/`** — F8 offline eval harness. Operator tooling, unflagged, no server wiring. `data.py`
(load the impression spine) → `scorers.py` (registry) → `replay.py` (IPS estimator + CLI) /
`calibration.py` (reliability + ECE) / `nightly.py` (idempotent per UTC day) / `persistence.py`
(append-only JSONL under `EVAL_RUNS_DIR`, default `data/eval_runs/`) / `synth.py` (synthetic logs).

**`tools/`** — `gen_stats_golden.py` (regenerates the stats golden vectors offline; scipy is *not* a
runtime dep, so never import it in shipped code) and `prod_analytics.py` (read-only reports against
production Postgres — forces `default_transaction_read_only=on` at session level).

**`scripts/`** — one-off / offline operator scripts, not imported by the app:
`calibrate_elo_value.py`, `replay_trade_decisions.py`, `rescale_pick_values.py`,
`backfill_feedback_status.py`.

## Identity: account vs league

Two different ids, and mixing them is the bug class `sleeper_roster.py` exists to prevent.

- **`backend/sleeper_roster.py` is the ONE roster→user predicate**: a roster belongs to a user iff
  `user_id == owner_id` **OR** `user_id ∈ co_owners`. Anything asking "is this roster the caller's?"
  goes through it (`owns_roster`, `find_user_roster`, `canonical_owner_id`, `co_owner_ids`). The
  predicate is mirrored in `mobile/src/api/sleeper.ts` and `web/js/app.js` and listed in
  `docs/cross-client-invariants.md` — change one, change all three.
- **A co-owner is an alias of the roster's primary `owner_id` within that league, never a second
  team.** Keeping `owner_id` canonical is what keeps the league-shared `league_members` table
  single-valued; keying on the caller would give a 12-team league 13 rows and hand the engine a
  phantom copy of the user's own team to trade with.
- **`server._league_user_id(sess)`** is the companion: the caller's **LEAGUE** identity (their
  roster's `owner_id`). `sess["user_id"]` is their **ACCOUNT** identity. League-scoped comparisons
  (`league_members`, `is_you`, "my roster") use the former; account-scoped state (rankings, swipes,
  tier overrides, entitlements, analytics, notifications, feedback) uses the latter. They are the
  same string for a sole owner, which is why swapping one in at a league-scoped comparison is safe.

Background: [ADR-012](../docs/adr/adr-012-co-owned-roster-identity.md),
`docs/plans/sleeper-co-owner-rosters/scope.md`. Fixture + tests:
[tests/fixtures/sleeper/co-owned-league/README.md](tests/fixtures/sleeper/co-owned-league/README.md),
`tests/test_co_owner_rosters.py`.

## Adding a route

1. Add `@app.route("/api/…")` in `server.py`. Find the right neighbourhood by its section banner —
   `awk '/^# -----/{getline nx; if (nx ~ /^# [A-Za-z]/) print NR": "nx}' backend/server.py` prints
   all 80 of them (Ranking API Routes, Trade API Routes, Draft Room, Notifications API, Cron-tick
   endpoints, ESPN league linking, …).
2. Decide the auth posture — the three existing patterns:
   - `@_gate_unverified_write` / `@_gate_unverified_read` for user surfaces.
   - `_require_cron_auth()` for operator/admin/cron surfaces — `X-Cron-Secret` must match
     `CRON_SECRET`. Fails **closed** in prod when the env var is unset.
   - Nothing, for the deliberately-public surfaces enumerated in `docs/api-reference.md`.
3. Use the right identity — see [Identity](#identity-account-vs-league). League-scoped ⇒
   `_league_user_id(sess)`.
4. Flag-gate anything user-visible: add the key to `FLAG_KEYS` **and** `DEFAULT_FLAGS` in
   `feature_flags.py`, to `config/features.json`, and to `backend/tests/fixtures/flags/release.json`
   (a test asserts that mirror). Off ⇒ return 404.
5. Update `docs/api-reference.md`, then the rest of the
   [doc triggers](#docs-you-must-keep-in-sync).

## Database

- **Local:** SQLite at `data/trade_finder.db`. Importing `database.py` creates the gitignored
  `data/` dir; `init_db()` creates the tables. **Prod:** set `DATABASE_URL` — `postgres://` is
  rewritten to `postgresql://` for SQLAlchemy.
- **Three engines, one DB** (analytics-platform LLD §3.3):
  `engine` (product path — WAL, `busy_timeout=5000`), `ingest_engine` (`/api/events` writes only,
  150 ms lock budget, `BEGIN IMMEDIATE` up front to dodge `SQLITE_BUSY_SNAPSHOT`), `ro_engine`
  (reports; `mode=ro` URI on SQLite, `default_transaction_read_only` + `statement_timeout=5s` on
  Postgres).
- **No migration framework.** `_migrate_db()` walks a list of `(table, column, type)` tuples through
  try/except'd `ALTER TABLE`s, plus `INSERT OR IGNORE` seeds for `model_config`. Adding a column
  means adding it to the `Table(...)` *and* to `migration_cols`, or existing DBs never get it.
- `get_config()` returns the whole `model_config` table as `{key: float}`. It is **Float-valued** —
  which is why the one string knob in `outlook/` lives in an env var instead.
- Schema is documented table-by-table in [docs/data-dictionary.md](../docs/data-dictionary.md).

## Config, flags, experiments

| Layer | Where | Notes |
|---|---|---|
| Feature flags | `feature_flags.py` → `config/features.json` → `FTF_FLAGS` env | 171 keys (116 currently true in `config/features.json`); code defaults are all `False` so new code ships dark. `POST /api/feature-flags/reload` re-reads at runtime. Dotted `group.feature` in JSON/API, `snake_case` on the dataclass — `_key_to_attr` converts; never hand-maintain a second mapping. |
| Numeric model knobs | `model_config` DB table, seeded from `_MODEL_CONFIG_DEFAULTS` in `database.py` | Read via `database.get_config()`; consumed by `trade_service.reload_config()` / `ranking_service.reload_config()`. Admin surface: `GET /api/admin/config`, `PUT /api/admin/config/<key>` (`X-Cron-Secret`; the PUT re-runs both `reload_config()`s). **Float only.** |
| Tier bands | `backend/tier_config.json` | Per (format, position). Governed by `docs/cross-client-invariants.md`. |
| Experiments | `experiments.py` + `experiments` / `experiment_*` tables | Deterministic layered bucketing salted by `EXPERIMENT_SALT_KEY`; tester allowlist = `FTF_TESTER_ALLOWLIST` ∪ `config/tester_allowlist.json`. |
| Env vars | ~30, all catalogued in [docs/config-reference.md](../docs/config-reference.md) | Load-bearing: `DATABASE_URL`, `CRON_SECRET`, `ANTHROPIC_API_KEY`, `EXPERIMENT_SALT_KEY`, the `FTF_*` test seams, `FTF_OUTLOOK_STRENGTH_SOURCE`, `VALUE_MODEL_DIR`, `EVAL_RUNS_DIR`. |

Secrets come from the gitignored `secrets.local.env` at the repo root — read from there, never ask
the operator to paste one into chat.

## Tests

Layout, harness patterns and fixtures: **[tests/CLAUDE.md](tests/CLAUDE.md)**. The essentials:

```bash
python3 -m pytest backend/tests -q                    # the whole suite (what CI runs)
python3 -m pytest backend/tests/test_trade_engine_v2.py -q
python3 -m pytest backend/tests -q -k fairness
```

`pyproject.toml` sets `testpaths = ["backend/tests"]`, so a bare `pytest` from the repo root works
too. The only dev dependency is `pytest` (`requirements-dev.txt`). CI
(`.github/workflows/ci.yml`, job `backend-tests`) runs `python -m pytest backend/tests -q` on
**Python 3.12**.

## Gotchas

- **`test_support.py` and `test_users.py` are PRODUCTION modules**, imported by `server.py` — the
  `FTF_TEST_MODE` UI-test blueprint and the `qa_*` stage-user spawner. Never move or archive them
  because of the `test_` prefix. Real tests live in `tests/`; `pyproject.toml`'s `testpaths` is what
  stops pytest collecting them.
- **CI and prod run Python 3.12.3** (`.python-version`, `render.yaml`). A local interpreter on a
  newer minor has produced failures that do not reproduce in CI — see `living-memory/TEST_LEDGER.md`
  (2026-08-13). Check CI before attributing a red test to your change.
- **One gunicorn worker on purpose.** `server.py` holds in-process state (`_sessions`, the universal
  player pools, trade-job futures). Scaling workers silently breaks sessions.
- **`FTF_TEST_MODE=1` startup-aborts** unless `FTF_SLEEPER_FIXTURES_DIR`, `FTF_PLAYERS_CACHE_FILE`,
  `FTF_DP_VALUES_FILE` and `FTF_DP_PICK_VALUES_FILE` are all set. A test-mode backend that can reach
  live Sleeper/DynastyProcess is a rails hole, so it refuses to start.
- **`FTF_SLEEPER_RECORD=1` refuses** to run with `FTF_TEST_MODE=1`, and refuses a fixtures dir that
  already holds cassettes — record one corpus per fresh directory, then move it.
- **`database.py` must never import `server.py`.** That is why `pick_values.py` exists as a tiny
  standalone module. Same rule for `suggestion_telemetry.py` — it is a deliberate leaf.
- **`server.py` is the only route file.** Resist "cleaning it up" into blueprints — every doc, test
  and grep convention in the repo assumes one file.
- **Don't mix account and league identity.** See [Identity](#identity-account-vs-league).
- Operational failure modes (KTC parse breaks, owned-pick clobbering, tier-occupancy drift,
  universal-pool caching of a failed DP fetch) are in [docs/runbook.md](../docs/runbook.md) with
  their guardrail test named. Read it before re-debugging one of them.

## Docs you must keep in sync

| Change here | Update |
|---|---|
| `server.py` routes | [docs/api-reference.md](../docs/api-reference.md) |
| `database.py` schema | [docs/data-dictionary.md](../docs/data-dictionary.md) |
| Env var, `config/features.json` key, `model_config` key | [docs/config-reference.md](../docs/config-reference.md) |
| Module wiring / data flow | [docs/architecture.md](../docs/architecture.md) + `living-memory/HLD.md` |
| Tier colors, thresholds, enum strings shared with clients (incl. the co-owner predicate) | [docs/cross-client-invariants.md](../docs/cross-client-invariants.md) |
| New domain term | [docs/glossary.md](../docs/glossary.md) |
| Operational issue worth recording | [docs/runbook.md](../docs/runbook.md) |
| Non-obvious architectural decision | new ADR in [docs/adr/](../docs/adr/) |

Before building anything user-visible, read the **Feature gates** section of the root
[CLAUDE.md](../CLAUDE.md) (scope block → Maestro delta → docs → sim run) and the
[coding guidelines](../docs/coding-guidelines.md).

### Full-roster gate (2026-09-04)

`trade_roster.py` and `trade_roster_adapter.py` are leaf modules. The worker captures one final snapshot and gates after all mutations, before market composition. Do not publish provisional cards while `final_checks_pending`; do not bypass on errors. `trade.roster_evaluation` and `trade.roster_protection` both default false. Keep schema-v1 evidence frozen in impression features; estimated provider templates cannot pass enforcement. See `docs/plans/post-trade-roster-evaluation/`.
