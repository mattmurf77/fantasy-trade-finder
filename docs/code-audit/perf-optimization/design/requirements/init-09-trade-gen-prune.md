# REQ — INIT-09: Prune Trade-Generation Candidates

- **Initiative / Wave / Scope:** INIT-09 · Wave 2 · [B]
- **Source observations:** OBS-DB-02
- **Peak RICE-P:** 4.3

## Problem statement

Trade generation enumerates all combinations of roster players before the scoring guards fire, producing up to `C(25,2) × C(25,3) ≈ 690 k` iterations for the dominant 3-for-2 term per opponent on a typical dynasty roster. Two guards bound it — a 1-second wall-clock deadline and a 200 k-iteration budget — but they truncate rather than prune: deep leagues silently leave opponents and combinations unsampled, meaning a user in a 10–12-team league never sees a full card deck. The CPU cost also saturates the single gunicorn worker during generation, degrading concurrent requests.

## User stories

- As a dynasty manager in a deep league (10–12 teams), I want the full set of trade opportunities to finish generating instead of being cut off by a time limit, so that I do not miss valuable trades.
- As a dynasty manager, I want my trades deck to fill faster after league pick, so that I can start evaluating trades sooner.
- As a developer, I want the pruning logic to preserve the exact same top-of-deck trade cards as the unpruned path, so that I can ship with confidence that user-visible fairness scores and card rankings are unchanged.

## Functional requirements

- **FR-1** Before the nested combination loops in `_generate_for_pair` (`trade_service.py:922`), pre-prune the user's give-side candidate set to roster players whose user-ELO is below the opponent's ELO for them — these are the only players that can produce `opp_surplus > 0` in `_mismatch_score` (`trade_service.py:1341`).
- **FR-2** Symmetrically, pre-prune the opponent's recv-side candidate set to roster players whose opponent-ELO is below the user's ELO for them.
- **FR-3** The pruning must be applied before the 3-for-2 nested loop (`trade_service.py:1179–1188`), the 2-for-1 loop (`trade_service.py:1078`), and the 1-for-2 loop (`trade_service.py:1134`). The 1-for-1 loop (`trade_service.py:1033–1064`) may apply the same filter for consistency.
- **FR-4** The pruning heuristic must only discard candidates that the existing `if recv_user <= combined_give_user * 0.95: continue` guard at `trade_service.py:948–950` (and equivalent per-loop guards) would reject anyway. No candidate that could pass the existing guards may be silently dropped.
- **FR-5** The target candidate-set size after pruning is approximately 8–12 players per side for a typical 25-player dynasty roster, reducing `C(25,3)` (≈ 2,300) to approximately `C(12,3)` (≈ 220) for the dominant term — a ~10× reduction.
- **FR-6** The 1-second per-opponent wall-clock deadline (`trade_service.py:948`) and 200 k-iteration budget (`trade_service.py:949`) must remain in place as safety guards for edge cases (very large rosters, unusual ELO distributions), but should not be the primary throughput mechanism for typical leagues after pruning is applied.
- **FR-7** The pruning must not alter `_fairness_score` computation or KTC math — only the candidate set fed into the existing scoring functions may change.
- **FR-8** The `_dv` memoization (`trade_service.py:960–971`) and the `_ktc_ok` pre-filter (`trade_service.py:1043`, `:1089–1090`) must be preserved and still apply inside the pruned loops.

## Acceptance criteria

- [ ] AC-1 — **Top-K equivalence test (required before shipping):** Given a sample of at least 3 real rosters with different ELO distributions, when trade generation runs both with and without the pruning applied, then the top-5 trade cards (by `_fairness_score`) are identical in content and order for each roster sample. This test must be automated and must pass in CI before the change ships.
- [ ] AC-2 — Given a 12-team dynasty league where each user has a ~25-player roster, when trade generation runs with pruning enabled, then a full sweep of all opponents completes without hitting the 1-second per-opponent deadline on any opponent (verified by log: deadline-hit counter = 0 for all opponents in the test run).
- [ ] AC-3 — Given the same 12-team league, when trade generation runs with pruning, then the total generation time is below 3 seconds of CPU wall time (versus the current ~11 s worst case documented at `trade_service.py:943–947`).
- [ ] AC-4 — Given a roster where a player has equal ELO on both sides (neither above nor below the opponent's value), the pruning must include that player in the candidate set (boundary condition: do not drop equal-ELO players).
- [ ] AC-5 — Given a new user with no swipe history (all ELOs at initial value), the pruning must degrade gracefully — either include all players (no pruning possible without ELO signal) or apply a sensible fallback that does not produce an empty candidate set.
- [ ] AC-6 — The `_fairness_score` output and KTC math for any trade card that appears in both the pruned and unpruned runs are numerically identical (same bytes), verified by the equivalence test harness.
- [ ] AC-7 — The existing `trade_elo_gap_max` and `max_candidates` values in `model_config` (`database.py:542,559`) are unchanged. The pruning is implemented in the combination-loop setup, not by tightening these config knobs.

## Related components

- `backend/trade_service.py:827–866` — opponent loop (`generate_trades`)
- `backend/trade_service.py:922` — `_generate_for_pair` entry point
- `backend/trade_service.py:948–950` — per-opponent deadline + iteration budget guards
- `backend/trade_service.py:960–971` — `_dv` memoization (must be preserved)
- `backend/trade_service.py:1033–1064` — 1-for-1 loop
- `backend/trade_service.py:1078` — 2-for-1 `combinations(user_roster, 2)`
- `backend/trade_service.py:1134` — 1-for-2 `combinations(opp_roster, 2)`
- `backend/trade_service.py:1179–1188` — 3-for-2 nested loops (dominant cost)
- `backend/trade_service.py:1341` — `_mismatch_score` (`opp_surplus` computation — defines what the prune heuristic mirrors)
- `backend/trade_service.py:1043`, `:1089–1090` — `_ktc_ok` pre-filter (must be preserved)
- `backend/database.py:542,559` — `model_config` keys `max_candidates`, `trade_elo_gap_max`
- `backend/server.py:2691` — background generation worker that invokes `generate_trades`

## Prerequisite components / dependencies

- **Top-K equivalence test harness (AC-1)** is a hard prerequisite and must be built before the pruning code ships. This is not optional — the trade fairness output is user-visible and the only validation that the pruning does not change results is this test. See sequencing note in `lld.md`: `golden ELO test harness ──before──► INIT-03, INIT-08-OptB, INIT-09`.
- **ELO memoization (INIT-03, Wave 1)** should already be landed before INIT-09 ships. The pruning logic reads per-player ELO values; if ELO is recomputed 3–4× per request without INIT-03, the pruning setup itself adds another pass. With INIT-03 in place, the ELO read during pruning hits the memoized result.
- No schema or infrastructure changes are required — this is a pure service-logic change in `trade_service.py`.

## Non-functional requirements & invariants

- **Trade fairness is a user-visible invariant.** The `_fairness_score` / KTC math must produce identical values for any given set of players, regardless of whether they arrived via the pruned or unpruned path. The pruning is a candidate-set filter only — it must never alter the scoring functions. See `docs/cross-client-invariants.md`.
- **ELO math is a cross-client invariant.** The ELO values read during the pruning setup must come from the same computation as the rest of the generation pass (memoized from INIT-03). Do not introduce a separate ELO read or recompute for the pruning step.
- **Per-format independence (cross-client invariant):** the ELO values used to prune must be the format-appropriate values for the active scoring format. A 1QB-PPR pruning pass must use 1QB-PPR ELO, and an SF-TEP pass must use SF-TEP ELO. These are independent rank sets.
- **Graceful degradation for new users:** a user with no swipe history has no ELO signal to prune on. The implementation must handle this without producing an empty candidate set or erroring — include all players (unpruned) for new users, or use a sensible ELO-default floor.
- **Performance target:** after pruning, a full 12-team deep-league sweep should complete in under 3 s of wall time, removing the truncation behavior for typical leagues.
- **Rollback:** the pruning can be disabled by reverting the candidate-set setup in `_generate_for_pair`. The deadline and iteration-budget guards remain as a safety net. No schema or config change is needed to roll back.

## Out of scope

- Lowering `_iter_budget` or `max_candidates` config values (OBS-DB-02 Option C) — these are blunt instruments that reduce coverage without improving the algorithm; addressed by the pruning instead.
- KTC-bucket filtering (OBS-DB-02 Option B) — coarser than ELO-based pruning; risks dropping legitimate lopsided-but-fair packages (e.g. depth-for-star trades). Superseded by Option A.
- Incremental / cached trade generation between sessions — the generation worker already runs fresh per job; result caching is a separate architectural concern.
- Any change to `_fairness_score`, KTC math, or the `opp_surplus` formula in `_mismatch_score`.
- Web or mobile client changes — this is a pure backend service change.
