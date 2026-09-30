# Code-walk proof — Value-core serving integration (WP3)

**Date:** 2026-09-30 · **Scope:** [scope.md §3](scope.md#3-evidence-scope) code-walk item · **Branch:** `feat/value-core-wp3`

Every citation is `file:line` on the WP3 branch **after** its edits. Lines inside `backend/value_core/core.py`, `ranking.py`, `deck.py` and `windows.py` are not cited: WP1 and WP2 build them in parallel, so their steps are cited by [lld.md](lld.md) section instead. Mobile and web lines are unchanged by this work.

## Contents

1. [Flag off: the path is byte-identical](#1-flag-off-the-path-is-byte-identical)
2. [Flag on: request → cards → impressions](#2-flag-on-request--cards--impressions)
3. [Clients render value-core cards with no change](#3-clients-render-value-core-cards-with-no-change)
4. [Swipes on value-core cards resolve](#4-swipes-on-value-core-cards-resolve)
5. [Kill switch](#5-kill-switch)
6. [Tests that pin each claim](#6-tests-that-pin-each-claim)

---

## 1. Flag off: the path is byte-identical

**The flag.** `trade.value_core` is registered at `backend/feature_flags.py:1172`. `DEFAULT_FLAGS` derives every key as `False` (`backend/feature_flags.py:1175`). It ships `false` in `config/features.json:268` and in the mirror `backend/tests/fixtures/flags/release.json:236`. It is read in exactly one place, `_value_core_enabled()` (`backend/server.py:7445-7446`).

The flag-off code changes are five, and each is a no-op when the flag is off:

| # | Change | Why it is a no-op when off |
|---|---|---|
| 1 | The branch in `_run_trade_job` (`backend/server.py:7928-7942`) | `_value_core_live` returns `False` at its first statement (`backend/server.py:7452-7453`), before it reads config, the allowlist or anything else. Execution falls through to the untouched legacy stack at `backend/server.py:7944`. |
| 2 | `("value_core", _value_core_enabled())` in `_trade_safety_signature` (`backend/server.py:3385`) | The comprehension keeps only enabled entries (`) if enabled]`, `backend/server.py:3386`), so the stamped `safety_policy` list and the expected lists in `_trade_running_policy_matches` (`backend/server.py:3117-3122`) and `_trade_job_is_fresh` (`backend/server.py:3509-3512`) are unchanged. |
| 3 | `value_core_evidence=None` on `_log_deck_signal_impressions` (`backend/server.py:5085`) | The only use is guarded by `if value_core_evidence is not None:` (`backend/server.py:5538`). The one caller that passes it is `_run_value_core_job` (`backend/server.py:7546`); the legacy call (`backend/server.py:8984`) does not pass it, so legacy rows are built exactly as before. |
| 4 | `and not server._value_core_enabled()` in `prepared_trade_runtime.supported` (`backend/prepared_trade_runtime.py:93-96`) | With the flag off, `not False` is `True`, so the conjunction equals its previous value. |
| 5 | `not k.startswith("vc_")` in the owner request-hash config filter (`backend/server.py:15263-15267`) | Not flag-gated on purpose. The 12 `vc_*` keys seeded at `backend/database.py:3190-3201` reach `trade_service._cfg` through `reload_config()` and from there the owner context's `config`. Filtering them keeps the owner experiment's `request_hash` and its 50/50 parity exactly what they were before the deploy. |

**The package is never imported.** `backend.value_core` is imported in exactly two places in `server.py`, both function-local:
- `backend/server.py:7485`, inside `_run_value_core_job`;
- `backend/server.py:7464`, inside `_value_core_standings`, whose only caller is `backend/server.py:7492` inside `_run_value_core_job`.

`_run_value_core_job` is called only from the branch at `backend/server.py:7931`, which `_value_core_live` guards. `backend/prepared_trade_runtime.py:96` calls `server._value_core_enabled()`, which imports nothing. `backend/value_core/pipeline.py:21` imports `core`, `deck` and `ranking` inside `run`, so even the flag-on import of `pipeline` does not load WP1/WP2 until the pipeline runs.

**Config knobs.** None of the 12 `vc_*` keys is in `trade_service._DEFAULT_CFG`, so the arm-A inventory test (`backend/tests/test_bakeoff_arm_a_golden.py:897`) is untouched. They are seeded through `INSERT OR IGNORE` (`backend/database.py:3735`), with no schema change.

**Accepted one-time effects, not behavior changes** (lld §9.1e). Once the rows are seeded and the flag key exists, the job cache's request signature (`_trade_request_signature`, `backend/server.py:3090-3094`) and the dark prepared-inventory dependency receipt change once, costing one regenerate. Neither changes what any user is served.

## 2. Flag on: request → cards → impressions

1. **Admission (unchanged).** `POST /api/trades/generate` (`backend/server.py:14553`) calls `_kickoff_trade_job` (`backend/server.py:14728` → `:9231`). That starts `_run_leased_job` (`backend/server.py:9286`, thread target at `:9417`), which calls `_run_trade_job` (`backend/server.py:9298` → `:7585`).
2. **Prelude (unchanged).** Inside `_run_trade_job`:
   - the captured context (`ctx`, `backend/server.py:7635`);
   - the viewer board `elo_map_rt` and `seed_map` (`backend/server.py:7653-7654`);
   - the memoised `_job_draft_picks` (`backend/server.py:7706`);
   - the declared outlook (`explicit_outlook`, `backend/server.py:7741`) and opponent outlooks (`backend/server.py:7793`);
   - untouchables and not-interested ids (`backend/server.py:7834-7844`);
   - `players_dict` (`backend/server.py:7846`);
   - the safety block, which stamps `safety_policy` including `"value_core"` (`backend/server.py:7881-7885`);
   - `confidence_counts` and `placement_bands` (`backend/server.py:7893`, `:7900`);
   - owned-pick injection, which rebinds `seed_map` and `g_user_roster` (`backend/server.py:7908-7926`).
3. **Branch.** `_value_core_live(...)` (`backend/server.py:7928-7930`) is True when the flag is on, the league is not `league_demo`, there is no `trade_intent`, the job is not a preparation job, and either `vc_testers_only < 1` or the account id or league identity is on the tester allowlist (`backend/server.py:7452-7459`). Then `_run_value_core_job(...)` runs (`backend/server.py:7931-7941`) and the worker returns (`backend/server.py:7942`). Nothing below that line runs for this job.
4. **`_run_value_core_job`** (`backend/server.py:7478`):
   - **Config.** A snapshot of `_trade_service_mod._cfg` (`:7488`) is mapped by `adapter.core_config_from` / `rank_config_from` (`:7489`; `backend/value_core/adapter.py:55`, `:69`), with the lld §3 clamps.
   - **League facts.**
     - Standings, Sleeper only and fail-soft (`:7492` → `_value_core_standings`, `backend/server.py:7462-7475`).
     - Lineup slots (`:7494`) and roster capacity, Sleeper only (`:7498`). Both fall back to `None` on any exception.
     - Pick shares from the memoised picks (`:7502-7507`).
   - **Windows.** `windows.infer_windows(...)` (`:7510`), which is lld §5.1.
   - **Snapshot.** `adapter.build_snapshot(...)` (`:7515`; `backend/value_core/adapter.py:102`). The viewer's team is inserted first, keyed by `ctx.league_user_id`. Market is raw `elo_to_value(seed)` with no age preference (`adapter.py:128`). Picks become `kind="pick"`, and K/DEF/IDP/unknown ids count in `other_players`.
   - **Request.** `adapter.build_request(...)` (`:7519`; `adapter.py:144`). The board is shrunk by `trade_service._shrink_user_elo` (`adapter.py:156`). The viewer is the first snapshot team (`adapter.py:167`). Id sets are cut to known assets.
   - **Pipeline.** `pipeline.run(...)` (`:7525`; `backend/value_core/pipeline.py:15-26`) runs `core.find_fair_trades` (lld §4), then `ranking.score_trades` (lld §5.2-§5.5), then `deck.assemble_deck` (lld §5.6).
   - **Cards.** `adapter.to_trade_cards(...)` (`:7526`; `adapter.py:232`) builds one `TradeCard` per entry, in deck order:
     - `trade_id = "vc_" + uuid` (`adapter.py:243`);
     - `basis="consensus"` and `reasons` (`adapter.py:250`);
     - `give_value` / `receive_value` = the raw market sums;
     - `preserve_server_order = True` (`adapter.py:252`);
     - plus `{id(card): evidence}` (`adapter.py:254`), in the lld §7.3 schema (`adapter.py:191`).
   - **Registration.** Every card goes into `trade_service._trade_cards` (`:7530`).
   - **Disposition cut.** `_project_trade_dispositions` removes exact passes (`:7531`).
   - **Impressions.**
     - Legacy `trade_impressions` (`:7535`), non-fatal.
     - `_log_deck_signal_impressions(..., value_core_evidence=evidence)` (`:7541-7546`), unless the job was superseded (`:7539`). `base_score` is the card's `composite_score` = priority (`backend/server.py:5385`, `:5401`). `final_score` is the evidence's `effective` via `capture["final_key"]` (`:7544`; consumed at `backend/server.py:5402`). The value-core block (`backend/server.py:5538-5552`) sets, **on every row**:
       - `model_arm = policy_variant = "value_core"`;
       - `arm_rank` = served position;
       - `policy_version = "value-core-1"`;
       - `fairness_threshold` = the ratio floor;
       - `valuation_json` = the evidence (`sort_keys=True`);
       - `trade_concept_id`, `source_like_impression_id = None` and `assets_json`.

       Setting every key on every row keeps the `executemany` first-row-keys rule (`backend/server.py:5429-5433`). Rows are saved at `backend/server.py:5193`.
   - **Publish.** The snapshot rows are `trade_card_to_dict` plus `real_opponent`, `outlook` and `impression_id` (`:7550-7556`). Under the job lock, if the job is still live: `cards`, `final_checks_pending = False`, the opponent counters and a `value_core` diagnostics dict (`:7558-7568`). One summary `log.info` line follows (`:7569`).
   - **Finish.** `_finish_trade_job(job_id)` (`:7573`). A superseded or timed-out job returns `None` and fires no event (`:7574-7575`). Otherwise `record_event(..., "trades_generated", props={"engine_version": "value_core", ...})` fires (`:7577-7580`).
5. **Errors.** Any exception inside the helper propagates to `_run_trade_job`'s outer handler (`backend/server.py:9176`, `:9185-9186`), and the job ends in `error`. There is no legacy fallback (PRD Q1). The only swallowed failures are standings, lineup slots and roster capacity (degrade to defaults), plus the three logging calls (non-fatal, `:7536`, `:7547`, `:7581`).

## 3. Clients render value-core cards with no change

- **Payload.** `trade_card_to_dict` (`backend/server.py:14347`) serialises the value-core card:
  - `basis` (`:14370`);
  - `preserve_server_order: true` (`backend/server.py:14375-14376`);
  - the value bar `give_value`/`receive_value`/`favors`/`gap` via `_value_verdict_payload` (`backend/server.py:14390-14395`);
  - `reasons` when `trade_math.human_explanations` is on (`backend/server.py:14490-14495`).

  `lane` is emitted only when set (`backend/server.py:14477-14479`), and the adapter leaves it `None`.
- **Reasons.** Mobile shows them when the flag is on and the list is non-empty (`mobile/src/components/TradeCard.tsx:323-325`, rendered at `:960`). Web does the same (`web/js/app.js:4072-4073`). The API normaliser passes them through (`mobile/src/api/trades.ts:171`).
- **Server order.** The normaliser keeps `preserve_server_order` (`mobile/src/api/trades.ts:209`). The client session re-rank is disabled when any card carries it (`mobile/src/screens/TradesScreen.tsx:4084`), and so is the adaptation-moment "rerank" variant (`TradesScreen.tsx:2778`).
- **Lane chips.** They render only when some card has a lane (`deckHasLanes`, `mobile/src/screens/TradesScreen.tsx:4101`, used at `:7332`). Value-core cards carry none.
- **Basis.** `"consensus"` is one of the two values the client normalises (`mobile/src/api/trades.ts:183`).

## 4. Swipes on value-core cards resolve

- Cards are registered in the session's shared card store (`backend/server.py:7530`). `_capture_trade_execution` copies the trade service but shares its `_trade_cards` dict (`backend/server.py:7428-7436`), so the registration lands in the store the routes read.
- **Swipe.** `POST /api/trades/swipe` (`backend/server.py:15868`) calls `trade_service.record_decision` (`backend/server.py:15905`), which looks the id up in `_trade_cards` (`backend/trade_service.py:7816-7821`). After a restart it rebuilds the card from the echoed card context (`backend/server.py:15912-15918`, `_reconstruct_swipe_card` at `:15826`). That path needs only the ids and `target_user_id` the payload already carries.
- **Pass reason.** The route resolves the card through the same store (`backend/server.py:16792`), with the same rebuild fallback (`:16799`).
- **Impression join.** Each published card carries its `impression_id` (`backend/server.py:7554-7555`), so `match_swiped` / `trade_pass_reasons` join back to the value-core `deck_impressions` row and its evidence.

## 5. Kill switch

1. **Flip `trade.value_core` to false,** then `POST /api/feature-flags/reload` (`backend/server.py:26276`, `reload_flags()` at `:26285`). The next job's `_value_core_live` returns `False` at `backend/server.py:7452`, and the legacy stack runs.
2. **Cached value-core decks are not reused.** They stamped `safety_policy` with `"value_core"` (`backend/server.py:3385`, stamped at `:7885`). After the flip, `_trade_safety_signature()` no longer contains it, so:
   - `_trade_job_is_fresh` rejects the cached job (`backend/server.py:3509-3513`);
   - `_trade_running_policy_matches` rejects a still-running one (`backend/server.py:3117-3122`).

   The flag map is also part of `_trade_request_signature` (`backend/server.py:3090-3094`). The same holds in the other direction when the flag is turned on.
3. **Rollout lever without a flip.** `PUT /api/admin/config/vc_testers_only` (`backend/server.py:21933`) writes the row and re-runs `trade_service.reload_config()` (`:21956`). `_value_core_live` reads it live (`backend/server.py:7456`). `1` serves only the tester allowlist (`_load_tester_allowlist`, `backend/server.py:26591` alias), and `0` serves everyone.
4. **Prepared inventories.** While the flag is on, `supported()` is False (`backend/prepared_trade_runtime.py:96`). As a result no legacy-prepared inventory is adopted (`try_adopt`, `backend/prepared_trade_runtime.py:527`, called at `backend/server.py:9295`) and none is prepared. After the flip, `supported()` returns its pre-existing value.

## 6. Tests that pin each claim

| Claim | Test |
|---|---|
| Flag registered, default off, mirrored | `backend/tests/test_value_core_serving.py::test_flag_registered_default_off_and_mirrored` |
| 12 knobs seeded, none in `_DEFAULT_CFG` | `::test_model_config_defaults_seeded_not_in_default_cfg`; `test_bakeoff_arm_a_golden.py` unchanged and green |
| Flag off never imports the package (job path in-process, server import in a fresh interpreter) | `::test_flag_off_never_imports_value_core` |
| Flag-off deck byte-identical | `backend/tests/test_bakeoff_serving.py::test_flag_off_is_byte_identical_to_the_captured_golden` (unchanged, green) |
| Flag on serves `vc_` cards with evidence on every row | `::test_flag_on_serves_value_core` |
| Tester gate; intent, demo and preparation stay legacy | `::test_testers_only_gate`, `::test_trade_intent_stays_legacy`, `::test_live_predicate_excludes_demo_and_preparation` |
| Prepared inventory off while on | `::test_prepared_inventory_unsupported_when_on` |
| Safety-signature entry | `::test_safety_signature_entry` |
| Owner hash ignores `vc_*` | `::test_owner_request_hash_ignores_vc_keys` |
| Standings fail-soft | `::test_standings_failure_non_fatal` |
| No fallback on error | `::test_pipeline_error_fails_job_no_fallback` |
| `engine_version = "value_core"` | `::test_trades_generated_engine_version` |
| Card shape, evidence schema v1, payload | `backend/tests/test_value_core_adapter.py` (14 tests) |

Each serving test was shown RED against a named sabotage of the line it guards, then green on revert. The sabotages were:
- dropping the `vc_` filter;
- dropping the prepared guard;
- dropping the safety entry;
- not passing `value_core_evidence`;
- ignoring `vc_testers_only`;
- a module-level `backend.value_core` import in `server.py`;
- a lazy import inside `_value_core_enabled`;
- a silent legacy fallback;
- not excluding `trade_intent`;
- the wrong `engine_version`.
