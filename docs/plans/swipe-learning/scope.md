# Feature Scope: BL-001, trade-card swipes move ratings again

**Date:** 2026-10-23
**Entry point:** model-change packet BL-001 (`docs/plans/org-bringup/leads/models-lead-launch.md` §M13 and §BL-001-packet, on the org-bringup branch, not yet on `main`). Operator asks M13 and "Why not now?" (both 2026-10-23), relayed by the coordinator and `head-bizops`.
**Builder:** `eng-backend` worker for `models-eng`, branch `eng/bl-001-swipe-learning` (base `origin/main` @ `712dcbed`). Not pushed; the lead ships.
**Operator sign-off on waivers:** pending. There is one waiver, the §3 TestFlight checklist, surfaced through `head-eng` with this build.

---

## What changes

- **A new `model_config` knob, `bakeoff_freeze_trade_k`, default 1.** It gates the bake-off's Channel 1 swipe freeze.
  - `bakeoff_runner.elo_freeze_mult(fit_mult)` returns 0 only when `trade.bakeoff` is on **and** the knob is above 0. Otherwise it returns `fit_mult`.
  - At 1, behavior is byte-identical to today.
  - At 0, trade-card likes and passes move the board at `trade_k_like` 8 / `trade_k_pass` 4 × `fit_congruence_mult`, while `trade.bakeoff` stays on for arm attribution and the ghost infrastructure.
- **The knob ships at 1. Nothing changes for users until `release-lead` writes 0** on the operator's go, after the 13b sign-off.
- **A read-only offline replay, `backend/eval/swipe_replay.py`** (packet fields 5a and 7). It never imports `backend.server`.

## 1. Analytics scope

- [x] **(b) Existing events cover it.**
  - `trade_proposed` and `match_swiped` (`user_events`) fire once per like or pass from the swipe route, unchanged.
  - The learning itself is recorded per row in `swipe_decisions.k_factor`. A trade row with K > 0 written after the flip is direct evidence that learning is on.
  - The knob write lands in `model_config_changes` when it goes through `scripts/set_knob.py` or the admin PUT. That gives the re-enable timestamp the 14-day monitor and the bake-off "new series" cut need.
  - No new event, and no change to any event's properties.

## 2. Schema & flag scope

- **New or changed tables or columns:** none.
- **New or changed feature flags:** none. `trade.bakeoff` is unchanged and stays on.
- **New `model_config` keys:** `bakeoff_freeze_trade_k`, default 1.0. It's seeded in `database._MODEL_CONFIG_DEFAULTS` and listed in `trade_service._DEFAULT_CFG`, and `elo_freeze_mult` has an inline fallback of 1.0. All three are 1 (G-064), pinned by `test_three_defaults_agree_and_freeze`. `docs/config-reference.md` is updated.
- **Deploy-free rollback lever:** set the knob back to 1. See §7.

## 3. Evidence scope

- [ ] **Structural guard:** n/a. There's no mobile change.
- [x] **Unit tests:**
  - **`backend/tests/test_bl001_swipe_learning.py` (17 tests):**
    - (a) bake-off on, knob 1 → 0.0. This is the flag-off identity.
    - (b) bake-off on, knob 0 → `fit_mult` unchanged.
    - (c) bake-off off → `fit_mult`, whatever the knob.
    - Any positive value freezes.
    - The three defaults agree, and a missing row resolves to the freeze.
    - (d) **Real `/api/trades/swipe` route** (the G-049 `route` fixture, in-memory DB). With knob 0, the persisted `swipe_decisions.k_factor` = `trade_k_like × fit_mult` (fit_mult 0.4 on a window-congruent like, so the test isn't vacuous). With knob 1 it's 0. Same for the in-memory signal.
    - **Forward-only (5b i):** a like is frozen, then the knob flips and a pass is written. The frozen row is unchanged, the board rebuilt up to the flip is identical, and only the pass moves the board.
    - `replay_from_db` uses stored K, not the current `trade_k_*`.
  - **`backend/tests/test_swipe_replay.py` (7 tests, synthetic SQLite):**
    - (A) equals prod's own rebuild of the stored rows.
    - (B) moves the board within tiers only.
    - Like/pass recovery and the restored K at 1.0 and 0.5.
    - The metric on a hand-built case, and the PASS/FAIL/NO DATA verdicts.
    - The read-only guard refuses INSERT/UPDATE/DELETE/CREATE, and the file hash is unchanged.
    - A Postgres URL is refused without the flag, and the password never reaches the report.
    - The CLI end to end.
    - The module never imports `backend.server` (subprocess check).
  - **`backend/tests/test_bakeoff_arm_a_golden.py`:** knob inventory. `bakeoff_freeze_trade_k` is EXCLUDED from `MODEL_A_PROFILE`: it's read only on the swipe routes, never in generation. The golden stands.
  - **Targeted run, 2026-10-23: 697 passed across 23 files.** That's the two new files plus every test file that touches `elo_freeze_mult`, `record_trade_signal`, the config inventories and config-reference, and the decline-reason Elo path. The full suite is CI's.
- [x] **Sabotage (not committed):**
  - `elo_freeze_mult` changed to ignore the knob: **6 of 17 tests failed** (b ×3, the defaults pin, (d) knob 0, forward-only). Reverted.
  - `restore_rows` changed to a no-op: **2 of 7 replay tests failed**. Reverted.
- [x] **Code-walk proof** (at this branch, `server.py` and `ranking_service.py` unchanged):
  - **Knob read:** `bakeoff_runner.py:468`, inside `elo_freeze_mult` (`:450`).
  - **Its three callers:**
    - `server.py:16019`, `/api/trades/swipe`. The persisted K is `trade_k_like × fit_mult` (`:16028`) or `trade_k_pass × fit_mult` (`:16038`), written by `save_trade_swipes` (`:16097`).
    - `server.py:16540`, calc queue like (`:16569`).
    - `server.py:16943`, deferred pass-reason Elo (`:16950`).
  - **Replay** reads each row's stored `k_factor` (`ranking_service.py:1207`), so frozen K = 0 rows stay inert forever.
  - **Trade-swipe updates are clamped** inside each player's post-ranking tier band (`_feedback_bounds`, `ranking_service.py:1421`, applied at `:1563`). That's the owner contract of 2026-09-05: feedback may reorder within a tier, never change it (`test_trade_feedback_tier_bounds.py`).
- [x] **Maestro delta:** n/a, retired by D-056.
- [x] **Manual TestFlight checklist: WAIVED.**
  - It's backend-only, and the knob ships at 1 (no behavior change).
  - The runtime proof after the flip is a read-only check on `swipe_decisions` (§7), which is stronger than a device check, because the effect is board order, not UI.
- `testID`s added or renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/config-reference.md` | **updated** | Bake-off "Existing draft and control settings" table: new `bakeoff_freeze_trade_k` row. The Channel 1 paragraph below the table no longer says "not a knob" |
| `docs/api-reference.md` | n/a | No route added, renamed or removed. The three swipe routes' request and response contracts are unchanged; only the K they persist depends on the knob |
| `living-memory/LLD.md` | n/a | No schema, route or invariant convention shifts. The stored-K replay contract already holds |
| `docs/architecture.md` | n/a | No module wiring or data-flow change. `swipe_replay.py` is an offline operator tool beside the existing `backend/eval/` harness, and nothing in the server imports it |
| `living-memory/HLD.md` | n/a | No architecture shift |
| `docs/cross-client-invariants.md` | n/a | K-factors are unchanged (`elo_k` 32, `trade_k_like` 8, `trade_k_pass` 4). No client reads the knob |
| `docs/glossary.md` | n/a | No new domain term. "Swipe freeze" is described in config-reference |
| ADR or `DECISIONS.md` entry | proposed, not written here | The packet carries the proposed D-entry (§BL-001-packet). The scribe claims the ID against fresh `origin/main` via `head-eng` → `release-lead`. `living-memory/` is outside this build's file grant |
| `docs/plans/three-model-bakeoff/scope-phase2.md` (arm-A dispositions) | **not updated: follow-up** | The disposition is recorded in `test_bakeoff_arm_a_golden.py`. That plan doc is outside this build's file grant |

## 5. Ship gate declaration

- **Simulator-gate tier:** n/a, retired by D-056.
- **CI green:** required on the pushed sha (`pytest backend/tests`, `tsc --noEmit`, testid-lint). This worker ran targeted files only, per the one-full-suite-at-a-time rule. CI runs the full suite.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry, written by the scribe, naming the targeted runs and the sabotage above.
- **Express lane:** no. Full gates.

## 6. Model-change packet sign-off (B3)

- **13a, plan:** `models-lead: approve with conditions — 2026-10-23 — via head-bizops → head-eng — conditions: the knob (field 1), forward-only (5b i), the replay (fields 5a and 7), the kill rule (6)`. **Done.**
- **13b, result:** pending. It needs the replay result (§9), routed `head-eng` → `head-bizops` → `models-lead`, **before** `release-lead` writes the knob.

## 7. Rollout and rollback

1. **Merge and deploy.** The seed inserts `bakeoff_freeze_trade_k` = 1 (INSERT OR IGNORE), so there's no behavior change.
2. **After 13b and the operator's go,** `release-lead` writes 0 with `scripts/set_knob.py`, which logs the write in `model_config_changes`. That timestamp is the re-enable time:
   - Calibration round 4 starts there (packet field 10).
   - Bake-off readouts start a new series there (field 7).
3. **Post-flip check (read-only):** the newest `swipe_decisions` rows with `decision_type = 'trade'` written after the flip carry K > 0 (8 or 4, times fit). All earlier frozen rows still carry 0.
4. **Rollback:** write the knob back to 1. It's deploy-free and takes effect on the next swipe.
   - **Rollback stops future learning but doesn't revert boards.** Swipes made while the knob was 0 keep their stored K.
   - Undoing them would be a stored-K rewrite, a prod data change that needs the operator.
5. **No backfill.** The frozen 2026-08-19 to flip swipes stay at K = 0 (condition 3). A catch-up would be a separate, decayed decision.

## 8. Post-ship monitor and kill rule (packet field 6)

- **Window:** 14 days from the re-enable time, every active user.
- **Kill rule:** p95 above 3 tier bands per week of trade-swipe-caused moves, or an operator report that rankings jumped, sets the knob back to 1. No interim verdict beyond the kill rule.
- **The band measure can't trip it.** Under the 2026-09-05 within-tier contract (§3 code-walk), a trade swipe cannot move a player across a tier band. So trade-swipe band moves are 0 by construction, and the kill rule's band test can never fire.
  - **The live signal is within-tier rank churn.** The monitor should read that, and models-lead should restate the kill rule in it. See §10.
- **Method:** the mirror of the replay. Rebuild each board with stored K, and again with the post-flip trade rows at K = 0, then difference them per week.
  - `swipe_replay.py` today only restores frozen rows. A `--mode monitor` is a small follow-up (S), not built here.

## 9. Offline replay (packet fields 5a, 5b i and 7)

- **Tool:** `python3 -m backend.eval.swipe_replay --db <path|URL> [--allow-postgres-readonly] --since 2026-08-19 [--until …] --min-swipes 10 --k-scale 1.0 --output <json>`.
  - It always reports the half-K (4/2) result next to the requested scale.
  - Its module docstring and the report's `metric_definition` state the metric.
- **Reading swipe_decisions:**
  - **Trade swipes vs trio votes:** `swipe_decisions.decision_type`. `'rank'` is a trio vote, `'trade'` is a trade-card like or pass, and `'disposition'` is a match accept/decline. Only frozen `'trade'` rows (K = 0, in the window) are restored.
  - **Like vs pass:** the swipe rows don't record which one it was. The rows of one swipe share a `created_at`, and the tool matches them to the user's latest `trade_decisions` row with the same two sides. An unmatched swipe gets like K, the larger, and is counted.
- **fit_mult is not recoverable.**
  - The card's signed `lane_shift` is never persisted.
  - `deck_impressions.features_json` keeps only the coarse `lane` label, joinable only via `trade_decisions.impression_id` when `trade.valuation_telemetry` was on. It can't separate a neutral pass (1.0) from an anti-window pass (0.4).
  - **The replay uses fit_mult = 1**, an upper bound at the default multipliers.
- **Local run:** none. There is no local snapshot: `/Users/teresadickens/ftf-clean/data/` is empty.
- **Prod run:** goes to analytics-lead's read-only W3 grant, from the repo root at this branch's head:

  ```
  python3 -m backend.eval.swipe_replay --db "$DATABASE_URL_PROD" \
      --allow-postgres-readonly --since 2026-08-19 --min-swipes 10 \
      --k-scale 1.0 --output data/eval_runs/bl001-swipe-replay-$(date -u +%F).json
  ```

  - `data/` is gitignored, and the report names boards by hash, not user id.
  - The report carries the field 8 provenance: code sha, args (password redacted), database, `model_config` hash, seed snapshot dates, and no RNG.

## 10. Findings for models-lead

1. **Bar 5a is met by construction, not by data.**
   - Since the owner's within-tier feedback contract (2026-09-05, `4026ebc8`), `RankingService._compute_elo` applies every trade-swipe update inside the player's post-ranking tier band, after all trio votes.
   - So restored swipes can reorder players inside a tier, but they can never change anyone's band. The replay will report band moves of 0 at any K. The synthetic test shows it: a player at 1578, two Elo under `first_1`, is pushed by four likes and doesn't move.
   - **What the bar can still catch is within-tier rank churn,** which the replay reports per board.
   - **Suggest restating 5a and the kill rule in rank churn** (for example, mean positional-rank change among the top tier per week) before 13b.
2. **Packet field 2 overstates the downstream effect.** "Tier views and pins" don't change from trade swipes. Only the order within a tier does, along with anything that reads the Elo value itself (selection, value).
