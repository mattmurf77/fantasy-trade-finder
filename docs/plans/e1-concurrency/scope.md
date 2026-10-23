# Feature Scope — E1 concurrency fixes (RankingService lock, F2/F6/F7/F8)

**Date:** 2026-10-22
**Entry point:** direct ask. Plan piece E1 (gunicorn `gthread`, launch item 5). The fix list is in the read-only audit `docs/plans/org-bringup/e1-concurrency-audit.md` (org-bringup checkout, base `678834ab`), with design decisions from rankings-eng.
**Builder:** `eng-backend` worker for rankings-eng, branch `fix/e1-ranking-service-lock` (base `origin/main` `712dcbed`)
**Operator sign-off on waivers:** pending. The waivers below go to the operator through rankings-eng.

This is a backend-only safety fix. The server still runs `sync` with one thread. The gthread switch itself (`render.yaml`, T7 smoke, docs) is release-lead's piece. Under `sync` every lock acquisition is uncontended, so behavior does not change until threads are on.

---

## 1. Analytics scope

- [x] **(c) WAIVED.** No analytics are needed: no event is added, changed or removed, and no user action or surface is new. The fix only orders work that already happens.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. Waived because no table, column or migration is touched.
- New/changed feature flags: **none**. The lock is unconditional. A flag would let the unsafe path run under threads, which is the case this removes.
- New env vars / `model_config` keys: **none**.
- **Rollback lever:** revert the branch's commits. The real risk is the thread switch, and its lever is release-lead's `render.yaml` (back to `sync` / `--threads 1`). This change alone is inert under `sync`.
- **API:** no route is added, renamed or changed. Every response stays byte-identical, so `docs/api-reference.md` is n/a.

## 3. Evidence scope

- [ ] **Structural guard:** n/a (no mobile code).
- [x] **Unit tests:** three new pytest files, all hermetic: no network, no prod, and no `data/trade_finder.db`. Each was run red under a named sabotage, then green after the revert, with `__pycache__` cleared per G-060. Race tests set `sys.setswitchinterval(1e-6)` and restore it afterwards.

  | Test | Proves | Sabotage → result | Green |
  |---|---|---|---|
  | **T1** `test_ranking_service_threads.py::test_concurrent_mutations_and_reads` (5 rounds) | 8 writers × 200 mixed `record_ranking`/`record_trade_signal` plus 4 readers. No exception. `_version` and `_interactions[None]` exact. The final board equals a fresh service replaying the shared service's own logs in log order | lock → `contextlib.nullcontext()`: red in 18 of 20 rounds (lost `_interactions` increments), and the 5-round test was red on 5/5 runs | 5/5 |
  | **T2** `…::test_reader_cannot_stamp_half_applied_tiers` | A reader is parked inside `_compute_elo` (patched `_pin_bounds`) while a writer thread runs `apply_tiers`. The cache is never stamped post-save over pre-save data, and the next read shows the save. Deterministic, all waits bounded | nullcontext **+** store-time stamp: **red 3/3** (cache at the post-save version still held q1's pre-save 1420). nullcontext alone: green, because the start stamp closes F1b by itself. Store-time stamp with the lock kept: green | 1/1 |
  | **T3** `test_ranking_routes_threads.py::test_tier_saves_swipes_and_reads_stay_consistent` (20 rounds) | Flask clients, one per thread, behind a Barrier: QB save, RB save, 4 swipes, and a `/api/rankings` loop. All 200. Stored overrides equal in-memory. Each publish equals a recompute from its call-time snapshot. The last publish holds both saves. 4 `swipe_decisions` rows. `_version` +6 | nullcontext: red 3/5 runs (a non-200 `/api/rankings` while a tier save is in flight). **A free race goes red in only about 5% of rounds** (4 of about 120 measured), so treat T3 as the integration check and T3b as the reliable red | 1/1 |
  | **T3b** `…::test_tier_publish_cannot_straddle_a_swipe` | Deterministic. A swipe fires into the tier save's window between the board read and the publish. Under the route lock the swipe waits, and the publish matches its snapshot | nullcontext: red 5/5. **Route-only sabotage** (tiers-save `with service._lock:` → nullcontext, method locks kept): red 3/3, while T3 stays green | 1/1 |
  | **T5** `test_shared_cache_threads.py` (3 tests) | `_rookie_player_ids` across `_bump_pool_generation()`, `_league_members_cached` vs invalidation, and `get_pending_trades`/`get_liked_trades` vs `_trade_cards` inserts. No exception | F6 reverted → T5a red 4/4. F7 reverted → T5b red 4/4. F2 reverted → T5c red 3/3. All were `RuntimeError: dictionary changed size during iteration` | 3/3 |

  T3 uses a per-test SQLite **file** under `tmp_path`, the same as `test_trade_job_admission.py`. `sqlite:///:memory:` gets SQLAlchemy's `SingletonThreadPool`, which gives each thread its own empty database.

- [x] **Code-walk proof.** Lines are on branch head. The decorator `_locked` is at `backend/ranking_service.py:317-329`. The lock is the first statement of `__init__` (`:401`). The start stamp is in `_compute_elo` (`:1489`, stored `:1609`) and `_compute_stats` (`:1620`, stored `:1641`). `comparison_counts` already captured `conf_key` at entry (`:1194`, stored `:1209`), so it is unchanged.

  **Decorated (17):** `placement_bands`, `has_player`, `record_ranking`, `record_trade_signal`, `record_disposition_signal`, `get_next_trio`, `get_rankings`, `get_progress`, `comparison_counts`, `replay_from_db`, `reset`, `apply_tiers`, `apply_tiers_subset`, `apply_anchor`, `board_override_count`, `apply_reorder`, `apply_value_map`. **Not decorated:** classmethods `tier_bands_for` and `tier_for_elo`, staticmethod `_pin_cfg_key`, and all `_private` helpers, which run only inside a locked public method or a route span.

  **Route spans** (`backend/server.py`; `git diff -w` shows only these 14 `with` lines, F6/F7/F8, and the `_owner_generation_context` one-liner from grant G2):

  | Site | Span | Holds | Notes |
  |---|---|---|---|
  | trio `get_trio` | `:9818-9831` | `get_next_trio` `:9822` + `_tier_info` `:9830` | `_tier_info` is a private method called from server, and it writes the stats memo, so it sits in the span |
  | rank3 `post_rank3` | `:10093-10127` | `record_ranking` → `save_ranking_swipes` → `get_rankings(None)` → `_ranking_confidence` → publish `:10119` | |
  | tiers copy `copy_tiers_from_format_route` | `:10928-10978` (`to_svc._lock`) | clear `:10929` → `apply_value_map` `:10938` → `save_tier_overrides` `:10942` → `save_tiers_position` → publish `:10970` | Starts at the wholesale clear, which is the first `to_svc` mutation. `from_svc` reads stay before the span |
  | tiers save `save_tiers_route` | `:11689-11752` | (rookie: `take_tier_override_snapshot`) → `apply_tiers_subset` `:11702` / `apply_tiers` `:11715` → `_invalidate_trade_jobs` → save `:11727` → publish `:11744` | |
  | anchor `save_anchor_route` | `:11906-11940` | `apply_anchor` → invalidate → save `:11915` → publish `:11932` | |
  | reset `reset` | `:12239-12240` | `service.reset` | A single call, so this equals the method lock |
  | reorder `reorder_rankings` | `:12265-12330` | `apply_reorder` → invalidate → `record_event` (DB) → save `:12306` → publish `:12322` | |
  | import-apply `rankings_import_apply` | `:12486-12528` | `apply_reorder` `:12488` → invalidate → `record_event` → save `:12508` → publish `:12520` | |
  | swipe `swipe_trade` | `:16026-16046` | `record_trade_signal` like/pass + K | **Cannot extend to persist.** `save_trade_swipes` `:16104` sits in the same `try` (`:16075-16284`) as `_send_typed_push` `:16265`/`:16274`, so including it would break rule 3 |
  | queue `queue_trade_for_opponent` | `:16549-16600` | `record_trade_signal` → `save_trade_decision` → `save_trade_swipes` `:16573` → `record_event` | DB only |
  | pass-reason `_apply_reasoned_pass_elo_only` | `:16963-16966` | `record_trade_signal` | Persists first (`save_trade_swipes` `:16954`, outside), so the span is the single mutation |
  | account reset `account_reset_rankings` | `:19718-19721` (`svc._lock`, per format) | `reset` + clear `_elo_overrides` / `_elo_override_at` | |
  | match disposition `disposition_trade_match` | `:20628-20633` | `record_disposition_signal` | **Cannot extend to persist.** The `save_trade_swipes` at `:20638` must run even when `service` is None (cross-league), so the span stays on the mutation |
  | rankings submit `submit_rankings` (grant G3) | `:20858-20880` | `get_rankings(None)` → `_ranking_confidence` → publish | Publish only, no mutation. DB writes only; no network call, no `_kickoff_trade_job` (span scan) |

  **Owner context (grant G2):** `server.py:15208` `_owner_generation_context` now iterates `list(getattr(service, "_elo_overrides", {}) or {})`, a snapshot. It is reached from the job thread (`:8106`) and from routes (`:15067`, `:15698`).

  **Lock-order audit** (AST scans, transitive within each module):
  - No code under `_sessions_lock`, `_trade_jobs_lock` or `_pool_build_lock` reaches a RankingService method.
  - The one service call under any global lock is `_session_restore_lock` → `_account_build_session` / `_extension_build_session` → `replay_from_db`. Those services are brand new and not yet shared, so the call is uncontended.
  - No span reaches `_kickoff_trade_job`, a Sleeper or other network call, `urlopen` or a push.
  - The database writers in the spans reach only SQLAlchemy and `json`.
  - Inside spans, `_invalidate_trade_jobs` takes `_trade_jobs_lock`, which is the allowed direction.

  **Deepcopy/pickle:** no code deep-copies or pickles a RankingService:
  - The job execution context travels in thread kwargs, never in the deep-copied job dict.
  - `copy.deepcopy(league)`: League and LeagueMember hold no service.
  - TradeService copies are shallow and hold no service.
  - `_RequestSession` copies the session dict shallowly.
  - Persisted sessions store identity fields only.
- [x] **Manual TestFlight checklist: WAIVED.** This is backend only, and the change cannot be observed under the shipping `sync` worker. The runtime proof is release-lead's T7 local gunicorn smoke (`--threads 4` vs `--threads 1`) once the flip lands.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route contract changes |
| `living-memory/LLD.md` | at merge (release-lead) | The E1 lock-order convention below lands with the merge |
| `docs/architecture.md` | at merge (release-lead) | `:779` ("not … full thread safety") is updated together with the gthread switch |
| `living-memory/HLD.md` | n/a | No new module, client or flow |
| `docs/cross-client-invariants.md` | n/a | No shared constants or enums |
| `docs/glossary.md` | n/a | No new domain term |
| ADR / `DECISIONS.md` | n/a here | The convention below is the decision. release-lead records it with the LLD entry at merge |

## 5. Ship gate declaration

- **CI green is required** (`pytest backend/tests`, `tsc --noEmit`, testid-lint) on the pushed sha. **Not pushed:** this worker does not push or open a PR.
- **Stub-service blocker: resolved.** G1 covers the 51 failures in 7 files. G4 covers the 3 that G3 caused in `test_rankings_submit_authz.py`. A static sweep found no other `_lock`-less service at a lock site. See "Test doubles without `_lock`".
- **Evidence recorded:** draft TEST_LEDGER entry below, for release-lead to paste.
- Express lane declared by the operator? **No.** Full gates apply.

---

## E1 lock-order convention (for LLD.md at merge)

1. Never call a RankingService method while holding `_sessions_lock`, `_trade_jobs_lock` or `_pool_build_lock`. Taking those locks inside the service lock is fine (for example `_invalidate_trade_jobs`).
2. Release the service lock before `_kickoff_trade_job`.
3. A route's service-lock span may include DB writes. It may never include a Sleeper call or any other network call.

The service lock is a per-instance `threading.RLock` (`RankingService._lock`). Every public method takes it, so nested calls are safe: `record_ranking` calls `get_rankings`. Routes take the same lock across mutate → persist → publish.

## Accepted as known

- **The job's three reads** (`_run_trade_job`: `get_rankings(None)` `:7688`, `comparison_counts()` `:7929`, `placement_bands()` `:7936`; on `origin/main` `:7690`, `:7931`, `:7938`) take the lock per call, never for the job's duration. A swipe can land between them. This is known, accepted and unchanged.
- **(a) Swipe persist order.** The `/api/trades/swipe` span covers only the in-memory `record_trade_signal`. The `save_trade_swipes` (`:16104`) sits in the same `try` as `_send_typed_push`, so rule 3 keeps it out.
  - Effect: two concurrent swipes from one user can append in one order in memory and insert in the other order in `swipe_decisions`.
  - The replayed board after a restart can then differ slightly from the in-session board. Trade K is small and feedback-bounded.
- **(b) Disposition persist.** The `/api/trades/matches/<id>/disposition` span covers only `record_disposition_signal`. The persist (`:20638`) runs even when `service` is None (cross-league), so it stays outside. The same ordering caveat as (a) applies.
- **(c) Anthropic call under the lock.** `get_next_trio` calls the Anthropic client inside the method lock and the trio span (`ranking_service.py:857`, `self._generator.generate_next_trio`).
  - It happens only when `ANTHROPIC_API_KEY` is set and `smart_matchup_enabled` = 1. `render.yaml` does not set the key.
  - head-eng has asked the operator whether `ANTHROPIC_API_KEY` is set on Render.
  - If it is set, rule 3 is broken for that lane. Moving the LLM call out of the lock is then a follow-up that must land before the gthread switch.

## F8 rationale

`_significance_exemptions_for` now uses `trade_service.__dict__.setdefault("_significance_exemptions", {})`. Two first callers can no longer each create a dict and lose one. Today's semantics hold:
- The dict lives on the session TradeService and is created there before the job's `copy.copy` (`server.py` `_capture_trade_execution`).
- Every shallow job copy therefore shares it with `/api/trades`, as intended.

It is not moved into the `TradeService` constructor. That would change construction for every caller and is not needed for atomicity.

## Grants (head-eng, 2026-10-23, relayed by rankings-eng)

- **G1** (test only): add `_lock = threading.RLock()` as a class attribute on the hand-rolled stub service in each of the 7 files below, plus `import threading`. Done.
- **G2:** `_owner_generation_context` (`server.py:15208`) iterates `list(...)` of `_elo_overrides`. Done.
- **G3:** one `with service._lock:` in `/api/rankings/submit`, from `get_rankings` through the member_rankings publish. Done (`:20858-20880`). `git diff -w` shows only the lock line.
- **G4** (rankings-eng, test only): `_lock=threading.RLock()` inside `test_rankings_submit_authz.py::_mk_service`'s `SimpleNamespace`, plus `import threading`. Done.

## Test doubles without `_lock`

### Resolved by G1

`with service._lock:` raises `AttributeError` on duck-typed stubs. Seven existing test files failed, 51 tests in all, every one with the `_lock` AttributeError. After G1, all seven files are green: 202 passed.

| File | Stub | Failing |
|---|---|---|
| `test_ranking_method_point_of_use.py` | `_FakeService` `:64` | 23 |
| `test_rookie_scope.py` | `_FakeService` `:373` | 13 |
| `test_trends_history_writers.py` | `_FakeService` `:33` | 6 |
| `test_analytics_p0.py` | `_FakeService` `:283` | 3 |
| `test_pick_rung_year_labels.py` | `_FakeService` `:55` | 3 |
| `test_rankings_import.py` | `_FakeService` `:411` | 2 |
| `test_verified_sessions.py` | `_StubService` `:399` | 1 |

The failure counts before G1 are in the table above.

### Resolved by G4: the eighth stub

`test_rankings_submit_authz.py::_mk_service` (`:37`) returned a `types.SimpleNamespace` with no `_lock`. Under G3, 3 of its 4 tests returned 500 with `AttributeError`. G4 adds `_lock=threading.RLock()` to that namespace, plus `import threading`, and the file is now 4/4 green.

### Static sweep (2026-10-23, no full suite)

**Step 1, call sites.** I grepped `backend/tests` for every test file that hits one of the 14 locked routes or calls `_owner_generation_context`:
- the 14 routes: trio, rank3, tiers copy/save, anchor, reset, reorder, import-apply, trades swipe, queue, pass-reason, account reset-rankings, match disposition, rankings/submit;
- matched by path literal, by direct `server.<route fn>` call, or by name.

That gives 40 files: 39 tests plus `fixtures/seed_ui_test_db.py`.

**Step 2, service objects.** An AST pass over each file classified every object placed under a `"service"`/`"services"` key, a `service=`/`services=` kwarg, a `sess["service"]` subscript, a service-named variable, or a service-builder return. I then read each non-`RankingService` case by hand. Files whose service came from another module's fixture were traced: `test_owner_generator_routes` and `test_trade_input_evidence` use `test_fair_packages`' real `RankingService`; the prepared-trade files use `prepared_trade_runtime`'s.

| Finding | Files | What it actually does |
|---|---|---|
| Stub classes or namespaces, now with `_lock` (G1, G4) | 8 files (G1's 7 + submit_authz) | All green |
| `_FakeService` with no `_lock` | `test_asset_ideas.py` | Used only at `/api/trades/asset-ideas`. That route can reach `_owner_generation_context`, but G2 is a `list()` snapshot and takes no lock. `/api/trades/swipe` appears only in a comment |
| `MagicMock()` service, no spec | `test_pick_assignment.py` | Hits only the pick-assignment and league-members routes. `_owner_generation_context` appears only as a string in an AST allow-list. (A spec-less `MagicMock` would act as a context manager, and its truthy `__exit__` would swallow span exceptions; no locked site sees one.) |
| No `"service"` in the session | `test_pick_labels_in_matches.py` | The disposition route reads `sess.get("service")`, gets None, and skips the locked branch |
| Bare session | `test_verified_reads.py` | `/api/trio` is refused by the gate before the span |
| Real `RankingService` (directly or via a shared fixture) | the remaining 27 test files | Not at risk |
| `MagicMock(spec=…)` / `create_autospec` / `Mock()` services | none in these files | Other `MagicMock` service files (`test_espn_draft_order`, `test_pick_assignment_tradeable`, `test_recorded_picks`) hit no locked route |

**Result:** no test reaches a lock site with a `_lock`-less service. **Files run:** the 8 stub files, `test_asset_ideas`, `test_pick_assignment`, `test_pick_labels_in_matches` and `test_verified_reads`, on `9de6254f`. All are green; counts are in the TEST_LEDGER draft.

## Residuals

Both residuals from the first report are now closed by G2 and G3 (see Grants).

## Draft TEST_LEDGER entry (for release-lead)

```
## 2026-10-22 — E1 RankingService lock + F2/F6/F7/F8 (branch fix/e1-ranking-service-lock)

Full gates, not express ([scope](../docs/plans/e1-concurrency/scope.md)). Backend only; D-056 posture, `FTF_SKIP_SIM_GATE=1`.

- New: test_ranking_service_threads.py (T1 ×5 rounds, T2), test_ranking_routes_threads.py (T3 ×20 rounds, T3b), test_shared_cache_threads.py (T5a–c): 11 passed.
- Named sabotages, each red then green on revert:
  - lock→nullcontext: T1 (18/20 rounds), T3b 5/5, T3 3/5 runs (free race ~5%/round);
  - lock→nullcontext + store-time memo stamp: T2 3/3 (lock alone green — start stamp closes F1b);
  - tiers-save route lock→nullcontext: T3b 3/3 (T3 green);
  - F6 / F7 / F2 reverted: T5a / T5b / T5c red.
- Existing ranking/tier/trio/session + touched-route files (79 files) on 8259e534: 1844 passed, 51 failed — all 51 the `_lock` AttributeError on stub services in 7 files.
- After the head-eng grants (G1 stub `_lock`, G2 owner-context `list()`, G3 submit lock), on a3b93485:
  - G1's 7 files: point_of_use 45, rookie_scope 35, trends_history_writers 6, analytics_p0 24, pick_rung_year_labels 17, rankings_import 50, verified_sessions 25 — 202 passed, 0 failed.
  - Owner-generation / submit coverage: owner_generator_routes 34, owner_only_routes 28, trade_input_evidence 77, trade_counterparty_epochs 61, pick_assignment 36 — all passed; rankings_submit_authz 1 passed, 3 failed (SimpleNamespace stub had no `_lock`).
- After G4 (submit-authz stub `_lock`), on 9de6254f, static-sweep run set — all passed, 0 failed:
  - rankings_submit_authz 4, ranking_method_point_of_use 45, rookie_scope 35, trends_history_writers 6, analytics_p0 24, pick_rung_year_labels 17, rankings_import 50, verified_sessions 25;
  - asset_ideas 70, pick_assignment 36, pick_labels_in_matches 16, verified_reads 6.
  - Sweep: 40 files hit a locked route or `_owner_generation_context`; none reaches a lock site with a `_lock`-less service.
- Full suite: GitHub CI on the PR (not run locally, per operator throttle).
```
