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
- **A read-only offline replay, `backend/eval/swipe_replay.py`** (packet fields 5a and 7), with a `--mode monitor` for the 14-day post-flip watch. It never imports `backend.server`.
- **Ships at half K** (final 13b): `trade_k_like` 4, `trade_k_pass` 2, then `bakeoff_freeze_trade_k` 0 (§7).

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
  - **`backend/tests/test_bl001_swipe_learning.py` (18 tests):**
    - (a) bake-off on, knob 1 → 0.0. This is the flag-off identity.
    - (b) bake-off on, knob 0 → `fit_mult` unchanged.
    - (c) bake-off off → `fit_mult`, whatever the knob.
    - Any positive value freezes.
    - The three defaults agree, and a missing row resolves to the freeze.
    - (d) **Real `/api/trades/swipe` route** (the G-049 `route` fixture, in-memory DB). With knob 0, the persisted `swipe_decisions.k_factor` = `trade_k_like × fit_mult` (fit_mult 0.4 on a window-congruent like, so the test isn't vacuous). With knob 1 it's 0. Same for the in-memory signal.
    - **Forward-only (5b i):** a like is frozen, then the knob flips and a pass is written. The frozen row is unchanged, the board rebuilt up to the flip is identical, and only the pass moves the board.
    - `replay_from_db` uses stored K, not the current `trade_k_*`.
    - **5b(ii), through `RankingService`'s real feedback path.** Trio votes establish a board. Then 600 likes and passes at K 8/4 hit players sitting on tier edges, both through live `record_trade_signal` and through the same rows replayed from storage. Every player keeps his tier, and unranked stays unranked. Within-tier order does change (asserted, so the test isn't vacuous).
  - **`backend/tests/test_swipe_replay.py` (22 tests, synthetic SQLite):**
    - **Final 13b:**
      - Revised kill (b): 1 board → ALERT, not a kill; 2 boards at ≥ 5% → KILL; 2 boards under 5% → ALERT. A 100-point move in a group of 3 doesn't count, and one in a group of 4 does.
      - Kill (d) fires on any introduced inversion.
      - **Monitor mode:** a post-flip window with stored K > 0 moves the board and reads OK. A pre-existing trio inversion of the 1st-round rungs doesn't fire (d). 40 stored-K Mid-over-Early likes introduce one inversion and read KILL (d).
      - The monitor CLI refuses to run without `--since`, and defaults to `--min-swipes 1`.
    - **13b A2:**
      - The pool holds the 12 generic rungs, with `GENERIC_PICK_SEEDS` and the live tabs (pinned to server.py's `_PICK_POS` by reading the source).
      - Pick rows are classified by id form, both directly and through `run()` counters.
      - A pick-order case: 40 Mid-over-Early swipes invert the 1st-round Early and Mid rungs inside `first_1`, and the check catches it. The same pressure across a band edge (Early 2nd over Late 1st) is clamped, with no inversion.
      - Zero inversions on a clean board.
      - An introduced inversion fails the ship rule.
    - The stored rebuild equals prod's own rebuild of the stored rows.
    - The restored board moves within tiers only.
    - End to end: the exact per-week discordant and same-tier pair counts, Kendall, percentile move, 5b(ii) = 0, the verdicts and the ship rule.
    - WITH and WITHOUT differ only in that week's trade swipes.
    - Like/pass recovery and the restored K at 1.0 and 0.5.
    - Hand-built cases:
      - Kendall: 2 of 7 same-group pairs. Unranked players and singletons are excluded.
      - Percentile move: top of 5 to bottom = 100.
      - Kill-rule thresholds: 0.25 doesn't fire and 0.26 does; 74.9 doesn't count and 75 does; 5% fires.
      - The 5b(ii) violation counter.
      - Bars and the ship rule.
    - The read-only guard refuses INSERT/UPDATE/DELETE/CREATE, and the file hash is unchanged.
    - A Postgres URL is refused without the flag, and the password never reaches the report.
    - The CLI end to end.
    - The module never imports `backend.server` (subprocess check).
  - **`backend/tests/test_bakeoff_arm_a_golden.py`:** knob inventory. `bakeoff_freeze_trade_k` is EXCLUDED from `MODEL_A_PROFILE`: it's read only on the swipe routes, never in generation. The golden stands.
  - **Targeted run, 2026-10-24: 819 passed across 32 files.** That's:
    - the two BL-001 files;
    - every test file that touches `elo_freeze_mult`, `record_trade_signal`, the config inventories and config-reference, and the decline-reason Elo path;
    - the nine test files main's merges added or changed (RankingService threads, session-init single-flight, small responses, status lock, daily tick, deck replenishment).

    The full suite is CI's.
- [x] **Sabotage (not committed; every one reverted):**
  - `elo_freeze_mult` changed to ignore the knob: **6 of 17 tests failed** (b ×3, the defaults pin, (d) knob 0, forward-only).
  - `restore_rows` changed to a no-op: **2 of 7 replay tests failed**.
  - WITHOUT made equal to WITH (5a trivially 0): **2 of 12 failed** (the end-to-end Kendall counts and the week isolation).
  - 5b(ii) counter returning 0: **1 of 12 failed** (the violation counter).
  - Generic rungs dropped from the pool: **5 of 16 failed** (the pool mirror, the classification, the pick-order case, and the two end-to-end tests).
  - Early and Mid reversed in the ladder: **5 of 16 failed** (the clean-board and pick-order cases, the pool mirror, the end-to-end check and the CLI).
  - Kill (b) firing on a single board: **1 of 22 failed** (the revised-(b) test).
  - Kill (d) counting pre-existing inversions: **1 of 22 failed** (the monitor's pre-existing case).
- [x] **Code-walk proof** (line numbers at `9c58e93e`, after main's merges; this build doesn't edit `server.py` or `ranking_service.py`):
  - **Knob read:** `bakeoff_runner.py:468`, inside `elo_freeze_mult` (`:450`).
  - **Its three callers:**
    - `server.py:16144`, `/api/trades/swipe`. The persisted K is `trade_k_like × fit_mult` (`:16154`) or `trade_k_pass × fit_mult` (`:16164`), written by `save_trade_swipes` (`:16223`).
    - `server.py:16666`, calc queue like (`:16696`).
    - `server.py:17070`, deferred pass-reason Elo (`:17077`).
  - **Replay** reads each row's stored `k_factor` (`ranking_service.py:1235`), so frozen K = 0 rows stay inert forever.
  - **Trade-swipe updates are clamped** inside each player's post-ranking tier band (`_feedback_bounds`, `ranking_service.py:1450`, applied at `:1595`). That's the owner contract of 2026-09-05: feedback may reorder within a tier, never change it (`test_trade_feedback_tier_bounds.py`).
  - **13b A2, picks:**
    - **Generic rungs are in the session pool.** `build_universal_pool` appends the 12 rungs with `GENERIC_PICK_SEEDS` in `_PICK_POS` tabs (`server.py:1670-1690`). Session init builds each format's RankingService from that pool (`:22454`, `:22461`).
    - **League picks never are.** `_inject_owned_picks` writes them only to `trade_service._players`, the job's `players_dict` (`:14225-14226`) and Elo maps (`:14238`).
    - **Live skips pairs outside the pool:** `record_trade_signal` (`ranking_service.py:747`) and `replay_from_db` (`:1231`).
    - **The calc queue passes client ids through unfiltered.** It takes them as strings (`server.py:16577`), rebuilds the card (`:16639`, `:16041`) and calls `record_trade_signal` (`:16669`) with no asset-kind check.
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
- **13b, FINAL:** `models-lead: approve — ship at HALF K (trade_k_like 4, trade_k_pass 2) — 2026-10-24`, on analytics-lead's prod re-run at `fd54c52a`.
  - **Full K fails 5a-ii** (p95 77.8 > 50); half K passes every bar (p95 38.9).
  - **Conditions:**
    1. the generic-pick guard (trades-eng) and its tests deploy before or with the knob write, and release-lead verifies them on the sha;
    2. revised kill (b) with its single-board alert (§9);
    3. the 14-day monitor reports weekly via `head-bizops`.
  - **A step-up to full K needs a new packet** with live evidence; it never happens automatically.

## 7. Shipping config, rollout and rollback

**Ship at half K:**

| Key | Today | Ship |
|---|---|---|
| `trade_k_like` | 8 | **4** |
| `trade_k_pass` | 4 | **2** |
| `bakeoff_freeze_trade_k` | 1 (frozen) | **0** (learning on) |

1. **Merge and deploy.** The seed inserts `bakeoff_freeze_trade_k` = 1 (INSERT OR IGNORE), so there's no behavior change. trades-eng's generic-pick guard deploys before or with the knob write.
2. **Write order for `release-lead`** (operator's go; `scripts/set_knob.py`, logged in `model_config_changes`):
   1. **First,** `trade_k_like` = 4 and `trade_k_pass` = 2.
   2. **Then,** `bakeoff_freeze_trade_k` = 0.

   This order means no swipe ever learns at 8/4. The `bakeoff_freeze_trade_k` write's timestamp is the re-enable time:
   - Calibration round 4 starts there (packet field 10).
   - Bake-off readouts start a new series there (field 7).
   - The monitor's `--since` is set to it.
3. **With `trade.bakeoff` off, the freeze knob is ignored** and swipes learn at `trade_k_*` directly. So setting half K in `trade_k_*` protects that path too.
4. **Post-flip check (read-only):** the newest `swipe_decisions` rows with `decision_type = 'trade'` written after the flip carry K > 0 (4 or 2, times fit). All earlier frozen rows still carry 0.
5. **Step-up to full K:** only by a new packet with 14 days of live evidence (live 5a-ii p95 ≤ 50 at half K, plus a replay or live estimate at full K). Never automatic.
6. **Rollback:** write the knob back to 1. It's deploy-free and takes effect on the next swipe.
   - **Caveat for `release-lead`:** that stops learning only while `trade.bakeoff` is on. If the flag is off when a kill fires, the freeze knob does nothing. The equivalent stop is `trade_k_like` = `trade_k_pass` = 0.
   - **Rollback stops future learning but doesn't revert boards.** Swipes made while the knob was 0 keep their stored K.
   - Undoing them would be a stored-K rewrite, a prod data change that needs the operator.
7. **No backfill.** The frozen 2026-08-19 to flip swipes stay at K = 0 (condition 3). A catch-up would be a separate, decayed decision.

## 8. Bars and ship rule (packet fields 5 and 6, revised 2026-10-24)

**Trade feedback can't move a player across a tier band.** `_feedback_bounds` (§3 code-walk) holds every feedback-moved rating inside its band, and an unranked player can't become ranked. So stability is measured as reordering within tiers.

**Unit of measure:** an active board-week.
- A board is one user and scoring format with at least 10 frozen-period trade swipes.
- A week is a 7-day window from `--since`.
- An active board-week has at least one trade swipe in it.
- For each board-week, two end-of-week boards share the same start:
  - **WITH:** that week's trade swipes at restored K × `--k-scale`.
  - **WITHOUT:** those swipes at K = 0.
  - Both boards carry earlier weeks' restored swipes and every other row of the week (trio votes, dispositions).
- **Groups** are (position, tier) on WITHOUT, ranked tiers only.

| Bar | Definition | Pass |
|---|---|---|
| **5a-i, magnitude** | Normalized Kendall distance: discordant same-group pairs ÷ all same-group pairs | Median ≤ 0.05 **and** p95 ≤ 0.15 across active board-weeks |
| **5a-ii, no ratchet** | Within a group of n ≥ 2 (singletons skipped), pct = rank / (n − 1) × 100. A board-week scores the max \|pct_with − pct_without\| over players | p95 ≤ 50 |
| **5b(i), forward-only** | Restoring at K × 0 reproduces the stored board, and nothing before `--since` moves | Every board |
| **5b(ii), structural** | Players whose tier differs WITH vs WITHOUT (unranked counted as a tier) | 0. This replaces the old band-move bar, which couldn't fire. Tested in both files |
| 5b(iii)–(v) | Trio K unchanged; first-deck gate unaffected; no Calibration session mixes boards | Not touched by this build: `elo_k` and the trio path are unchanged; brand-new users have no swipes; Calibration builds every arm in a session from one board (packet §M13) |
| **Pick order (13b A2)** | The 12 generic rungs on every WITH and WITHOUT board: Early ≥ Mid ≥ Late within a round, and min(round r) ≥ max(round r + 1). An inversion is a ladder pair rated the wrong way round. Pre-existing (WITHOUT) and introduced (on WITH, not on WITHOUT) are both reported | **0 introduced.** Part of the ship rule, and the monitor keeps it as a tripwire |

p95 is nearest rank throughout.

**Ship rule:**
- **Ship at full K (8/4)** when 5a-i, 5a-ii, 5b(i) and 5b(ii) all hold on the replay and no pick inversion is introduced.
- **Otherwise, ship at half K (4/2)** if they hold there, and re-check.
- **Otherwise, hold.** The replay is an upper bound (§10 caveats), so a fail calls for half K or a fidelity fix, not abandoning.
- The tool always reports both scales and prints the rule's outcome (`ship_rule`).

## 9. Post-ship monitor and kill rule (packet field 6)

- **Window:** 14 days from the re-enable time (the `bakeoff_freeze_trade_k` = 0 write), weekly, every active user.
- **Metrics:** 5a-i and 5a-ii on live boards (informational after the flip), and 5b(ii).
- **Kill rule** (field 6, (b) revised 2026-10-24 before the monitor runs). Set `bakeoff_freeze_trade_k` back to 1.0 (§7 for the flag-off caveat) if any of these holds:
  - **(a)** the weekly p95 within-tier Kendall distance is **> 0.25**;
  - **(b)** in a week, **at least 2 boards AND at least 5% of active boards** each have a player move **≥ 75 percentile points** within his tier from trade swipes alone, **counting only groups of n ≥ 4.** A 2- or 3-player tier never counts: one swap there scores 50 to 100.
    - **Alert, not a kill:** any board meeting that test without (b) firing (typically exactly one) is reported to `models-lead` that week for review.
  - **(c)** the operator reports that rankings jumped;
  - **(d)** any generic-pick-rung inversion **introduced** by trade swipes on a live board. Pre-existing inversions (BL-003) are excluded. An introduced one means the guard failed, so investigate before any re-enable.
- No interim verdict beyond the kill rule. The kill thresholds sit above the bars to leave headroom for the replay's upper-bound gap.
- **Monitor mode:** `python3 -m backend.eval.swipe_replay --mode monitor`.
  - **The comparison:** WITH is the live board, every trade row at its **stored** `k_factor` (the learning that actually happened). WITHOUT is the same week with that week's trade rows at K = 0. Everything else is the same machinery as the replay. Boards are every user × format with at least one trade swipe in the window.
  - **What it prints:** a **KILL / ALERT / OK** line per week and overall, naming the kill rule that fired. A (b) alert names its board hashes.
  - **In the JSON:** `results.stored.kill_rule.weeks[]` carries `p95_kendall`, `boards_ge75_n4`, `share_ge75_n4`, `boards_ge75_n4_hashes`, `introduced_pick_inversions`, `fires_a`, `fires_b`, `alert_b`, `fires_d` and `status`.
  - **The replay reports the same indicators** for its own window. (c) has no analogue in either.
- **The weekly monitor command** (`release-lead`, or `analytics-lead` under W3 read-only), from the repo root at the deployed sha. `<FLIP>` is the `model_config_changes.changed_at` of the `bakeoff_freeze_trade_k` = 0 write:

  ```
  python3 -m backend.eval.swipe_replay --mode monitor --db "$DATABASE_URL_PROD" \
      --allow-postgres-readonly --since <FLIP> \
      --output data/eval_runs/bl001-monitor-$(date -u +%F).json
  ```

  `--until` defaults to now, and `--min-swipes` defaults to 1 in monitor mode.

## 10. Offline replay (packet fields 5, 7 and 8)

- **Tool:** `python3 -m backend.eval.swipe_replay --db <path|URL> [--allow-postgres-readonly] --since 2026-08-19 [--until …] --min-swipes 10 --k-scale 1.0 --output <json>`.
  - It always reports the half-K (4/2) result next to the requested scale.
  - The module docstring and the report's `metric_definition` state the metrics.
- **The pool mirrors the live session RankingService pool (13b A2):**
  - **Players:** the `player_value_history` snapshot joined to `players`.
  - **Plus the 12 generic rungs** `generic_pick_{1..4}_{early,mid,late}`, with `pick_values.GENERIC_PICK_SEEDS` and the live builder's position tabs. The tabs are `GENERIC_PICK_TABS`; a test pins them to server.py's `_PICK_POS` literal by reading the source, since that map is local to the builder.
  - **A pair applies only when both ids are in the pool,** exactly as live: `record_trade_signal` and `replay_from_db` skip any other pair.
  - **Restored rows are counted by id form:** `generic_pick_rows_applied`, `skipped_league_pick_rows` (league-owned `{league}_{season}_{round}_{orig}` ids live only in the trade engine's maps, never in the ranking pool) and `skipped_other_rows`.
  - **Before the flip, trades-eng will strip `generic_pick_*` ids on the queue and swipe routes,** so live churn will be a subset of what the replay measures.
- **JSON output fields:**
  - Top level: `mode`, `metric_definition`, `pick_order_definition`, `caveats`, `window`, `k`, `min_swipes`, `counts`, `seed_snapshots`, `model_config_sha256`, `check_5b_i` and `ship_rule` (both null in monitor mode), `provenance`.
  - Each `boards[].k_scale_*` week row also carries `board` and `max_pct_move_n4` (kill (b)'s n ≥ 4 move).
  - `counts` adds `generic_pick_rows_applied`, `skipped_league_pick_rows` and `skipped_other_rows`.
  - **`results["1.0" | "0.5"]`:**
    - `board_weeks_active` and `board_weeks_inactive`;
    - `kendall` and `max_pct_move`, each as {median, p95, max};
    - `bar_5a_i` and `bar_5a_ii`;
    - `check_5b_ii` {tier_membership_violations, verdict};
    - `kill_rule` {weeks[{week_start, active_boards, p95_kendall, boards_ge75_n4, share_ge75_n4, boards_ge75_n4_hashes, introduced_pick_inversions, fires_a, fires_b, alert_b, fires_d, status}], would_have_fired, status};
    - `pick_order` {preexisting_inversions, board_weeks_with_preexisting, introduced_inversions, board_weeks_with_introduced, verdict}.
  - **`boards[]`:** each board by hash, with per-week rows: trade_swipes, kendall, discordant_pairs, same_tier_pairs, max_pct_move, tier_violations, pick_inversions_without, pick_inversions_introduced.
- **Reading swipe_decisions:**
  - **Trade swipes vs trio votes:** `swipe_decisions.decision_type`. `'rank'` is a trio vote, `'trade'` is a trade-card like or pass, and `'disposition'` is a match accept/decline. Only frozen `'trade'` rows (K = 0, in the window) are restored.
- **Fidelity caveats.** Both push churn up, so the replay is an **upper bound** on live churn. Both are printed and written to `caveats`.
  - **Like or pass is matched through `trade_decisions`.** The rows of one swipe share a `created_at`, and the tool takes the user's latest decision with the same two sides. An unmatched swipe takes like K (the larger) and is counted.
  - **fit_mult is 1.**
    - The card's signed `lane_shift` is never persisted.
    - `deck_impressions.features_json` keeps only the coarse `lane` label, which can't separate a neutral pass (1.0) from an anti-window pass (0.4).
    - Live K is scaled down for window-explained swipes, so 1 is an upper bound.
- **Local run:** none. There is no local snapshot: `/Users/teresadickens/ftf-clean/data/` is empty.
- **Prod run:** goes to analytics-lead's read-only W3 grant, from the repo root at this branch's head:

  ```
  python3 -m backend.eval.swipe_replay --db "$DATABASE_URL_PROD" \
      --allow-postgres-readonly --since 2026-08-19 --min-swipes 10 \
      --k-scale 1.0 --output data/eval_runs/bl001-swipe-replay-$(date -u +%F).json
  ```

  - `data/` is gitignored, and the report names boards by hash, not user id.
  - The report carries the field 8 provenance: code sha, args (password redacted), database, `model_config` hash, seed snapshot dates, and no RNG.

## 11. Findings for models-lead

1. **Resolved 2026-10-24.** The original band-move bar could never fire: trade feedback is held inside each tier band. models-lead restated 5a as within-tier Kendall and percentile move, and kept the band check as structural guardrail 5b(ii).
2. **Resolved 2026-10-24: field 2 corrected by models-lead.** Trade swipes don't change tier views or pins. They change within-tier order, and anything that reads the Elo value itself (selection, value).
3. **13b A2, pick pairs (code read at `9c58e93e`):**
   - **Generic rungs move ratings live.** They're in the session RankingService pool, and `_feedback_bounds` lets a swipe invert two rungs that share a tier: Early and Mid 1st are both `first_1`. The replay now includes them, and the pick-order check catches that case.
   - **Rungs in different bands can't invert.** The band edge holds Late 1st (`first_1`) against Early 2nd (`second`).
   - **League-owned picks never move ratings.** They're never in the ranking pool, so both live and replay skip their pairs.
   - **Deck cards are built from rosters** (Sleeper players plus league-owned picks), so deck swipes carry no generic rungs.
   - **The calculator queue (`/api/trades/queue`) passes client ids straight to `record_trade_signal` with no asset-kind check.** That's the path generic rungs reach. trades-eng's strip closes it before the flip.
