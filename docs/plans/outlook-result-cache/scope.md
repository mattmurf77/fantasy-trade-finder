# Feature Scope — Outlook result cache (`GET /api/league/outlook`)

**Date:** 2026-10-27
**Entry point:** direct ask. Launch piece C2, task `c2-eng-backend-2` (manager league-eng; design accepted by head-eng).
**Builder:** `eng-backend` worker, branch `perf/outlook-result-cache` (base `origin/main` `3eac68d3`)
**Operator sign-off on waivers:** pending. The waivers below (analytics (c), no mobile evidence rows) go to the operator through league-eng.

`league_outlook_route` (`backend/server.py`) re-ran `run_outlook` on every League tab open: 10,000 pure-Python season sims, measured 0.34–0.95 s in-season and 0.9–3.5 s preseason on a local M1 (a lower bound for prod). Prod runs `gunicorn --workers 1 --threads 4`, so each run holds the GIL and starves the other three request threads, the 200 ms tap path included. The existing `_outlook_cache_*` only caches the Sleeper weekly fan-out, not results. This adds an in-process result cache in a new leaf module, `backend/outlook_result_cache.py`, wired into the route with one small change. Nothing under `backend/outlook/` is edited.

---

## 1. Analytics scope

- [x] **(c) WAIVED.** No event is added, changed or removed, and there is no new user action or surface. This is a server-internal performance change with a byte-identical response. The hit/miss/coalesced/error counters are debug log lines only, never in an API response or `user_events`.

## 2. Schema & flag scope

- New/changed tables or columns: **none**.
- New/changed feature flags: **none**. The cache is correctness-preserving by construction (the key hashes every engine input), so a flag would only add a second code path. `outlook.odds` still kills the whole route.
- New env vars / `model_config` keys: **none**. TTL (6 h) and cap (256) are module constants, not knobs.
- **Rollback lever:** revert the commit. The cache is in-process, so a restart also empties it.
- **API:** URL, query params, status codes and response body are unchanged. A hit is byte-identical to an uncached run (test 1).

## 3. Evidence scope

- [ ] **Structural guard:** n/a (no mobile code).
- [x] **Unit tests:** new `backend/tests/test_outlook_result_cache.py`, 27 tests, hermetic (no network, no prod, the real `run_outlook` on crafted leagues). Each was run red under a named sabotage and green after the revert. `backend/tests/conftest.py` gains an autouse fixture that clears the cache between tests, so a test that spies on `run_outlook` through the route is never served an earlier test's result.

  | # | Test | Proves | Sabotage → result |
  |---|---|---|---|
  | 1 | `test_hit_is_byte_identical_to_an_uncached_run` ×3 (roster_value / blended / trailing_scores) | A hit, stamped for callers `u3`, `u1`, `""` and a non-member, `json.dumps`-equals a fresh `run_outlook(you_user_id=<caller>)` | stored value perturbed (`basis` rewritten) → 3/3 red |
  | 2 | `test_any_input_change_misses_and_recomputes` ×12 | A change to roster, record, schedule, points_for, weekly_scores, median_match, playoff_slots, player_value, player_pos, model_cfg, playoff_seed_type or the strength source changes the key and recomputes. Plus `test_digest_ignores_dict_order_and_handles_sets` | `player_ids`, `wins`/`losses`/`ties` and `schedule` dropped from the hash → roster, record, schedule red (3/12) |
  | 3 | `test_personal_basis_keys_per_caller`, `test_shared_basis_entry_is_restamped_for_each_caller` | `basis=personal`: B gets their own computation, never A's entry. Consensus: one computation, and A, B, A each see only their own `is_you`. The stored value carries nobody's `is_you`, and a caller mutating its copy can't touch it | re-stamp skipped → both red, plus the route restamp test. User id dropped from the personal key → personal test red |
  | 4 | `test_concurrent_cold_misses_compute_once`, `test_waiters_on_a_failed_computation_share_the_error_and_nothing_is_cached` | 8 threads behind a Barrier cold-miss one key: one compute, 7 coalesced, all get the same object. On a raise, all 6 threads get the error and the next call recomputes | per-key single-flight removed (`leader = True`) → both red |
  | 5 | `test_ttl_expiry_recomputes`, `test_cap_evicts_least_recently_used`, `test_module_bounds_are_6h_and_256` | Injected clock: a hit at 59.9 s, a recompute at 60.1 s (TTL 60). Cap 3: touching `a` makes `b` the LRU victim when `d` arrives | TTL check → `True`: TTL test red. Eviction loop disabled: cap test red |
  | 6 | `test_an_error_is_not_cached_and_the_next_call_recomputes` ×2 (`ValueError`, `NotImplementedError`) | An error is never stored; the next call recomputes and caches | the error path stores a placeholder → 2/2 red |
  | R | `test_route_runs_the_sim_once_for_two_identical_requests`, `test_route_restamps_is_you_for_a_second_caller_on_a_hit` | Through the Flask test client with `test_outlook_route_cache.py`'s fake Sleeper: two identical requests run `run_outlook` once (spy; called with `you_user_id=""`) and the bodies are byte-equal. Users u1 and u2 on one league share one run, each with their own `is_you`, and the bodies are otherwise equal | key made unique per request → first red. Route stamps the wrong caller → second red |

  Suite run: `python3 -m pytest` over `test_outlook_result_cache`, `test_outlook_route_cache`, `test_outlook_odds`, `test_outlook_calibration`, `test_outlook_direction`, `test_outlook_idp_pricing`, `test_outlook_playoff_seed_type`, `test_outlook_preseason_source`, `test_outlook_seed`, `test_outlook_trade_delta`, `test_opponent_outlook_infer`: **213 passed, 1 skipped** (the offline backtest scaffold).

- [x] **Code-walk proof.** Lines are on branch head.
  - **Determinism.** `backend/outlook/simulator.py:84-85` seeds a local `random.Random(stable_hash(league_id) ^ int(config_seed))`. The package has no other `random` use (grep), and the docstring (`:9-14`) rules out global `random`, `time` and `datetime.now`. So equal inputs give equal outputs, and a hit is what an uncached run would return.
  - **Caller-specific output.** `you_user_id` reaches only `serialize.py:98` (`is_you`), via the passthrough at `pipeline.py:92`. `trade_delta.py` passes `""` and is not on this route. Nothing else in the payload depends on the caller. The route computes with `you_user_id=""` (`server.py:35215`), and `for_caller` (`outlook_result_cache.py:88-94`) deep-copies and re-applies the serializer's rule to every team, so even a stored payload with someone's `is_you` would be overwritten.
  - **Key.** `make_key` (`outlook_result_cache.py:74-85`) hashes `vars()` of the `LeagueState` and each `TeamState` (`_canon`, `:58-65`), so attributes attached after construction count. `run_outlook` also reads the env var `FTF_OUTLOOK_STRENGTH_SOURCE` (`config.py:30`); the route passes `get_strength_source(None)` into the key (`server.py:35206`).
  - **Single-flight.** `get_or_compute` (`:125-170`): one lock covers the lookup and the in-flight registration. The leader computes outside the lock, stores the result only on success, then clears the flight and sets its Event in `finally`. Waiters block on the Event and re-raise the leader's exception (`:148-150`).
  - **Wiring.** `server.py:35193-35218` replaces the single `run_outlook` call. Phase 1 (live `rosters`/`users` reads and the fan-out cache) still runs on every request, so a standings change reaches the key on the next open.
- [x] **Timing** (`time_result_cache.py`, reusing the c2 `time_outlook.py` fixture builders: real 12-team captures, offline fetch, the route's value loop, 296-key model config). Same M1 as c2-eng-backend-1, Python 3.14.4, but under heavy shared load (load average 31–48), so absolute sim times run above that baseline. CPU time (`process_time`), 9 runs + 1 warm-up, ms median / min / max. Phase 1 is excluded from every column; cold and warm include the key hash and `for_caller`'s deep copy. Each run asserts cold == warm == an uncached run, byte for byte.

  | Case | Uncached `run_outlook` | Cold (miss) | Warm (hit) | Key hash alone |
  |---|---|---|---|---|
  | 12T mid lakeview-2025 @ wk 8 | 1334 / 1276 / 1517 | 1373 / 1228 / 1473 | **2.3** / 1.7 / 12.8 | 1.24 / 1.06 / 1.57 |
  | 12T mid ffv3-2025 @ wk 8 | 1045 / 1019 / 1061 | 1035 / 633 / 1061 | **3.5** / 1.9 / 5.0 | 1.44 / 1.25 / 2.02 |
  | 12T pre lakeview-2026 | 2707 / 2490 / 3056 | 2635 / 2376 / 2859 | **4.4** / 2.6 / 5.0 | 1.23 / 0.98 / 1.45 |
  | 12T pre ffv3-2026 (pre_draft) | 1780 / 1350 / 1854 | 1793 / 1214 / 1874 | **2.4** / 1.3 / 4.0 | 1.28 / 0.78 / 1.71 |

  A wall-clock pass (5 runs) gave the same picture: warm minimums of 1.5–3.7 ms, with medians up to 39 ms from load spikes. The key hashes about 21–26 KB of canonical JSON (payload ~4.6 KB). A miss costs the sim plus about 1–2 ms, inside the run-to-run noise. Script: `scratchpad/c2b/time_result_cache.py` (session scratchpad).
- [ ] **Manual TestFlight checklist:** **WAIVED**. The response is byte-identical (test 1), and there is no client change. The runtime check is server-side, after deploy: open one league's League tab twice, then confirm a `miss` line followed by a `hit` line from logger `backend.outlook_result_cache` in the Render logs (`docs/runbook.md` § Outlook result cache).
- `testID`s added/renamed: none.

**Known limit.** A cold miss still holds the GIL for the full sim, up to about 3.5 s on an M1. That happens on the first open per league after a restart and the first after any input change. Single-flight stops concurrent opens of one league from multiplying it, but one cold sim still starves the other request threads while it runs. A follow-up is being sized.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | `GET /api/league/outlook` row: one "Result caching" clause next to the fan-out caching note. The contract is unchanged |
| `living-memory/LLD.md` | n/a | no schema, route or invariant convention shifts. In-process per-key caches are an existing convention |
| `docs/architecture.md` | updated | new `outlook_result_cache.py` row after the `outlook/` package row |
| `living-memory/HLD.md` | n/a | a leaf module behind one route; no new client, store or major flow |
| `docs/cross-client-invariants.md` | n/a | no shared constant, enum or color |
| `docs/glossary.md` | n/a | no new domain term |
| ADR or `DECISIONS.md` | n/a | the design was accepted by head-eng. Two choices are recorded here and in the module docstring: compute caller-free and stamp `is_you` per request, and waiters share the leader's exception rather than recomputing (a recompute would hold the GIL for another full sim) |
| `docs/runbook.md` | updated | new § Outlook result cache (2026-10-27): resets on deploy/restart, when cold sims happen, how to tell hits from misses |
| `docs/plans/README.md` | updated | new top row in Thread folders |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` + testid-lint on the pushed sha (CI runs the full suite; this branch ran only the outlook files above).
- **Evidence recorded:** the tests and timing above. The `living-memory/TEST_LEDGER.md` entry is left to whoever merges, to avoid living-memory conflicts across concurrent branches.
- **TestFlight verification:** none (waived above).
- Express lane declared by the operator? **No.**
