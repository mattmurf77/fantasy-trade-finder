# backend/tests/ — Notes for Claude

175 `test_*.py` files, plus `support/` (import-only helpers) and `fixtures/` (committed cassettes
and snapshots). Pure pytest — **no `conftest.py` anywhere in the repo**, no custom markers, no
plugins. Figures derived from **`origin/main`**, 2026-08-18.

- [Running](#running)
- [Layout](#layout)
- [The four harness patterns](#the-four-harness-patterns)
- [Hermeticity](#hermeticity)
- [Fixtures](#fixtures)
- [Conventions](#conventions)
- [Known state](#known-state)

---

## Running

```bash
python3 -m pytest backend/tests -q                    # whole suite
python3 -m pytest backend/tests/test_accounts.py -q   # one file
python3 -m pytest backend/tests -q -k "fairness or gate"
python3 -m pytest backend/tests -q --durations=25     # find the slow ones
```

`pyproject.toml` sets `testpaths = ["backend/tests"]`, so a bare `pytest` from the repo root does
the same thing. The only dev dependency is `pytest` (`requirements-dev.txt`); runtime deps
(`flask`, `sqlalchemy`, `cryptography`, `Pillow`, …) come from `requirements.txt`.

**CI** (`.github/workflows/ci.yml`) has three jobs: `backend-tests` runs
`python -m pytest backend/tests -q` on **Python 3.12**; `mobile-typecheck` runs `npx tsc --noEmit`
**and** every `mobile/tests/check-*.js` structural suite; `maestro-testid-lint` runs
`mobile/scripts/testid-lint.sh`. There is no iOS-simulator tier in CI (no free macOS runner).

Log real runs in [`living-memory/TEST_LEDGER.md`](../../living-memory/TEST_LEDGER.md).

## Layout

Flat. One file per feature/behavior, named for what it pins rather than for the module it imports —
so grep by symptom, not by import path.

| Cluster | Files (examples) |
|---|---|
| Trade engine | `test_trade_engine_v2`, `test_trade_optimizer`, `test_trade_gen_prune`, `test_fairness_gate_golden`, `test_user_gain_gate`, `test_three_team_cycles`, `test_presentment_rules`, `test_offer_hard_lock_330` (12 `test_trade_*` files plus these) |
| Deck / discovery (F1–F10) | `test_deck_*` (9: exploration, fatigue, first_session, ordering, replenishment, signal_v2, taste, thompson_v2, value_model), `test_engine_telemetry`, `test_pass_cooldown` |
| Ranking / tiers / Elo | `test_rnk_elo_golden`, `test_elo_memoization`, `test_tier_occupancy`, `test_trio_*`, `test_compressed_board`, `test_rankings_import` |
| Draft | `test_draft_*` (5), `test_mock_draft`, `test_mock_pick_ownership`, `test_pick_*` (8), `test_recorded_picks`, `test_owned_picks` |
| Platform integrations | `test_espn_*` (7), `test_mfl_*` (7), `test_fleaflicker_*` (2), `test_sleeper_write*`, `test_crosswalk_generalized`, `test_co_owner_rosters` |
| Auth / accounts / sessions | `test_accounts`, `test_account_*`, `test_verified_sessions`, `test_verified_reads`, `test_persistent_sessions`, `test_espn_identity_binding` |
| Analytics + experiments | `test_analytics_*` (4), `test_events_api`, `test_api_observability` |
| Outlook (#169) | `test_outlook_*` (8), `test_bye_weeks`, `test_bye_multiplier`, `test_opponent_outlook_infer` |
| History / Wrapped | `test_roster_history` |
| Eval harness (F8) | `test_eval_replay`, `test_eval_calibration`, `test_deck_value_model` |
| Harness self-tests | `test_test_support`, `test_test_users`, `test_seed_ui_test_db`, `test_backfill_scripts` |

`support/draft_replay.py` is the only shared helper module: it turns the committed draft cassettes
into a steppable live draft (`DraftReplay`, `FakeClock`, `mfl_opener`) with zero network and zero
wall-clock waiting.

## The four harness patterns

Copy these from a neighbouring file; there is no conftest to inherit from.

**1. Isolated in-memory DB** — 84 files.

```python
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
metadata.create_all(engine)
with patch.object(db_module, "engine", engine):
    yield engine
```

`backend.database.engine` is read at call time by the helpers, so patching the module attribute is
enough. The production module also builds `ingest_engine` and `ro_engine` — analytics tests patch
those separately when they need them.

**2. Flask client + injected session** — 80 files use `app.test_client()`, 68 touch
`server._sessions`.

```python
server.app.config["TESTING"] = True
c = server.app.test_client()
with server._sessions_lock:
    server._sessions[TOKEN] = {"user_id": USER, "last_active": 0.0}
```

Pop the token in a `finally` — `_sessions` is process-global and leaks across test files. For
league-scoped assertions remember the session may also carry `league_user_id` (see
`backend/CLAUDE.md` § Identity).

**3. Flags** — two idioms, both in wide use: `monkeypatch.setattr(server, "is_enabled", …)` (56
files reference `is_enabled`) or resetting `feature_flags._flags_cache` to `DEFAULT_FLAGS` in an
autouse fixture (41 files). Whichever you pick, **restore it** — the cache is lazily computed and
other modules depend on it.

**4. Config** — `trade_service._cfg` / `ranking_service._cfg` are module-level dicts refreshed by
`reload_config()`. Snapshot and restore them in an autouse fixture;
`test_trade_engine_v2.py::_isolate_flags_and_cfg` is the canonical version.

## Hermeticity

Nothing in the suite touches the network, and nothing reads or writes `data/trade_finder.db`.
The seams:

| Boundary | How tests neutralize it |
|---|---|
| Sleeper REST | `FTF_SLEEPER_FIXTURES_DIR` — `server._sleeper_fixture_path` maps `…/v1/<path>` → `<dir>/<path>.json`; a miss raises HTTP 599 (fail-closed, never live) |
| Sleeper GraphQL / ESPN / Fleaflicker / DP CSV | `monkeypatch.setattr(urllib.request, "urlopen", …)` |
| MFL | An injected `_opener` — `mfl_service._fetch_one` takes one, and `draft_board_service` threads it all the way down |
| DynastyProcess values | `FTF_DP_VALUES_FILE`, `FTF_DP_PICK_VALUES_FILE` (data_loader seams) |
| KeepTradeCut scrape | `FTF_KTC_VALUES_FILE`; unset under test mode ⇒ KTC is simply off |
| Clock / TTLs | `support.draft_replay.FakeClock` + module-level `_now_monotonic` indirection — never `time.sleep` |
| Randomness | Everything seeded (`stable_hash(league_id) ^ seed`); `test_trade_engine_v2` is explicitly RNG-free |

`backend/test_support.py` (a **production** module, not a test) counts rail violations —
`vcr_misses`, `sleeper_live_egress_attempts` — and `test_test_support.py` asserts the whole
blueprint is inert when `FTF_TEST_MODE` is unset.

**Three files spawn subprocesses.** `backend.server` reads the `FTF_*` env vars at *import* time and
other tests import it un-gated, so anything testing import-time env behavior (test-mode startup
aborts, inertness guardrail G5) runs in a child interpreter with a scratch `DATABASE_URL`. Follow
that pattern for anything depending on import-time state — and expect those cases to be slow.

## Fixtures

`fixtures/` is committed reference data, not generated at runtime. Two subdirectories carry their
own README — read them before touching the data:

- [`fixtures/draft/README.md`](fixtures/draft/README.md) — the 9 draft corpora: provenance table,
  the two "don't tidy this" traps, and re-recording instructions.
- [`fixtures/sleeper/co-owned-league/README.md`](fixtures/sleeper/co-owned-league/README.md) — the
  real co-owned-roster capture behind ADR-012; real ids, synthetic player lists.

| Path | Contents | Consumed by |
|---|---|---|
| `draft/` | 9 corpora (Sleeper cassettes + MFL `draftResults.json`), each with a `manifest.json` stating provenance | `test_draft_replay`, `test_draft_board`, `support/draft_replay.py` |
| `sleeper/co-owned-league/` | `rosters.json` + `users.json` for a real league where the operator co-owns roster 3 | `test_co_owner_rosters` |
| `profiles/` (10) | UI-test world definitions (`standard`, `fresh`, `draft`, `draft-pre`, `espn`, `near-unlock`, `quickset-done`, …) — schema in `docs/plans/mobile-testing/lld.md` §3.1 | `seed_ui_test_db.py`, `test_seed_ui_test_db` |
| `flags/` (6) | Flag sets for seeding. `release.json` is a **generated mirror of `config/features.json`** — `test_seed_ui_test_db.test_release_flags_mirror_features_json` fails the build on drift; `all-on.json` deliberately omits uncalibrated flags | `seed_ui_test_db.py`, `mobile/scripts/screen-capture.sh`, several route tests |
| `dp-values-history/` (24 CSVs + `index.json`) | Dated DynastyProcess boards, 2022–2025, each the nearest commit at-or-before its key date | `backend/dp_values_history.py` (**production**), outlook backtests |
| `outlook-calibration/` (10) | Per-league season snapshots for the #169 odds calibration | `test_outlook_calibration`, `test_outlook_playoff_seed_type` |
| `outlook-hypotheses/` (12) | Backtest record sets (IDP pricing, preseason source) | `test_outlook_idp_pricing`, `test_outlook_preseason_source` |
| `stats_golden.json` | scipy-generated golden vectors, asserted to 1e-9 | `test_analytics_stats`; regenerate with `python3 -m backend.tools.gen_stats_golden` (scipy is **not** a runtime dep) |
| `rankings_paste_golden.json`, `dynasty_rankings_sflextep.csv` | Paste-import parser goldens + a real ranking export | `test_rankings_import` |
| `dp_values_snapshot_*.json`, `dp_playerids_snapshot_*.csv`, `dp_values_picks_*.csv` | DP value / crosswalk / pick snapshots | tier-occupancy, format-mapping, crosswalk, slot-value tests |
| `ktc_rankings_snapshot_*.html`, `ktc_blend_pipeline_*.json` | Trimmed KTC page + matched DP+KTC pool | `test_ktc_blend` |
| `espn_league_snapshot_*`, `espn_league_11896_standings_*`, `mfl_league_snapshot_*`, `fleaflicker_league_snapshot_*` | Per-platform league snapshots (ESPN has a second one for draft order) | the matching `*_service` / `*_link_route` / `test_espn_draft_order` tests |
| `nflverse_games_2022_2026.csv` | NFL schedule (CC-BY) → derived bye weeks | `backend/outlook/bye_weeks.py`, `test_bye_weeks` |
| `player_pool_2026.json`, `rookie_universe_2026.json` | 340 real players with DP values in both formats; the rookie class | `seed_ui_test_db.py`, `test_mock_draft` |

**`fixtures/seed_ui_test_db.py` is a library *and* a CLI**, not a test. One generator, four outputs
(profile DB, Sleeper cassettes, players warm-cache, DP values CSV) written atomically so they can
never disagree. Exit codes are a contract: `0` ok · `2` io · `3` refused (token-like field, or
`--verify` schema mismatch) · `4` unknown profile · `5` internal cassette gap.

## Conventions

- **Docstring first.** All 175 files open with a module docstring naming the spec section and
  enumerating what is covered — no exceptions. Match that; it is how the suite stays greppable.
- **Repo root is `Path(__file__).resolve().parents[2]`**, conventionally bound to `REPO`.
- **Golden-vector tests** (`*_golden`) pin numeric output against a committed snapshot. If consensus
  data genuinely shifts, refresh the fixture and re-tune — don't loosen the assertion.
- **Sabotage discipline** (standing repo practice — see TEST_LEDGER): a new behavioral test is
  proven RED against a *named* sabotage of the code it guards, then green on revert. The ledger
  records the sabotage names.
- Tests never read or write `data/trade_finder.db`; every DB-touching test builds its own in-memory
  engine. (The dev DB does accumulate suite artifacts from historical runs — `caller_uid`,
  `user_anchor_test`, `stm_user`; see `docs/runbook.md`. That is why local analytics numbers are
  noise and `backend/tools/prod_analytics.py` exists.)

## Known state

- **`origin/main` is green.** `living-memory/TEST_LEDGER.md` (2026-08-18, tip `505ca2c`) records
  **3125 passed / 1 skipped / 0 failed**, run pre-push. Re-derive rather than trusting this number
  if time has passed — and don't quote a count taken on a stale branch.
- **The 1 skip is a deliberate opt-in**: `test_outlook_odds.py::test_backtest_against_captured_season`
  runs only with `FTF_OUTLOOK_BACKTEST=/path/to/captured.json`. Two more files
  (`test_outlook_calibration.py`, `test_outlook_playoff_seed_type.py`) skip wholesale if their
  fixture directory is missing; it ships, so they run.
- **One test dominates the wall clock.** `test_mock_draft.py::test_w2_16_calibration_gate` fits and
  validates the CPU-drafter model; measured at **~160s**, comfortably more than half of a full
  local run. Everything else is sub-6s. If you only need fast feedback,
  `-k "not calibration_gate"` roughly quarters the runtime.
- **Python version skew is a real failure source.** CI and prod are 3.12.3; a newer local minor has
  produced failures that do not reproduce in CI (TEST_LEDGER 2026-08-13, `test_rookie_scope.py`).
  Check CI before attributing a red test to your change.
- Single-process and CPU-bound. No `pytest-xdist` and no `pytest-timeout` are installed, so `-n auto`
  and `--timeout` are unavailable.
