# Feature Scope — Value core: count-bounded, never clock-bounded

**Date:** 2026-10-20
**Entry point:** direct ask (engines lead, models-eng). Rule: engines are count-bounded, never clock-bounded ([G-065](../../../living-memory/GOTCHAS.md))
**Builder:** eng-backend worker, branch `eng/value-core-count-bounded` (base `origin/main` `678834ab`)
**Operator sign-off on waivers:** pending. The waivers in §1 and §3 were surfaced to the engines lead in the hand-back, for the operator.

---

## 0. The change

`backend/value_core/core.py` used to stop enumeration on an 8 s wall clock (`TIME_BUDGET_S`). It checked the clock before each partner and every 1,000 checks. Under CPU contention the clock cut partners, so the deck depended on machine load. The work was already bounded by counts: `MAX_CHECKS_PER_PARTNER` (40,000 base pairs plus 40,000 throw-in variants per partner) and `cfg.max_per_partner`.

- `TIME_BUDGET_S` / `time_budget_s` are removed. In their place are `SAFETY_CEILING_S = 30.0` and a `safety_ceiling_s` parameter, checked at the same two places. The ceiling is not a budget. If it fires, the core sets `diag.budget_exhausted = diag.safety_ceiling_hit = True`, logs one ERROR line (partners done/total, pairs checked) and stops. It must never fire on a normal run.
- `CoreDiagnostics.safety_ceiling_hit` is new (default `False`). `elapsed_ms` stays, as a measurement only.
- `pipeline.run(..., safety_ceiling_s=None)` passes the ceiling through (None ⇒ `core.SAFETY_CEILING_S`). The old duplicated literal `8.0` is gone.
- `blind_grading.run_value_core`: a run with `safety_ceiling_hit` raises `GradingError("value_core_failed", 503)`. `build_session` already turns that into session status `failed` with `error_json = {"code": "value_core_failed"}`, so a partial pool never becomes a Calibration session.
  - **Deviation from the brief:** the brief suggested a new code such as `value_core_safety_ceiling`. That code would change a documented contract: `docs/api-reference.md:1135` (SessionView `error`), `docs/cross-client-invariants.md:1300` (`SessionView.error.code ∈ value_core_too_few | value_core_failed`) and the client type in `docs/plans/blind-grading/specs.md:342`. The existing documented code is used instead. The cause shows in the ERROR logs: one line from the core and one from `blind-grading`.

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** —
- [x] **(c) WAIVED — no analytics needed because:** no event is added, changed or emitted differently. `trades_generated` still fires once per value-core job (`server.py`, unchanged). The safety ceiling is an operational fault, and it is surfaced in the logs: the core's ERROR line, plus `budget_exhausted=True` on the existing per-job INFO line.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. `deck_impressions.valuation_json` still carries `core.budget_exhausted` and only that (`adapter.evidence`, unchanged). `grading_sessions.source_json.value_core.budget_exhausted` is unchanged, because a ceiling run fails before that meta is built.
- New/changed feature flags: **none**.
- New env vars / `model_config` keys: **none**. `SAFETY_CEILING_S` is a code constant, like the `TIME_BUDGET_S` it replaces. Rollback lever: revert the commit. No knob exists or is needed.

## 3. Evidence scope

- [ ] **Structural guard:** n/a. The change is backend-only, with no client file touched.
- [x] **Unit tests** (pytest):
  - `backend/tests/test_value_core_core.py`: `test_public_api` re-pinned on purpose (`TIME_BUDGET_S` → `SAFETY_CEILING_S`). `test_check_cap_and_budget` is now `test_check_cap` (a normal run sets neither flag). The new `test_safety_ceiling_marks_pathology` is parametrized over both check sites: the core's clock is monkeypatched to jump past 30 s, and the test asserts `safety_ceiling_hit`, `budget_exhausted`, `pairs_checked` 0 / 999 and exactly one ERROR record (caplog).
  - `backend/tests/test_value_core_count_bound.py` (new), on `value_core_bench.synthetic_league()` seat `team00` (11 partners):
    - `test_same_deck_when_the_clock_runs_past_the_old_budget` **(primary)**: the clock advances 1 s per read and `safety_ceiling_s=1e9`. The result is the same trades in the same order, with diagnostics equal bar `elapsed_ms`.
    - `test_same_deck_under_real_cpu_contention`: two busy threads spin. The test asserts equality only, never timing.
    - `test_pipeline_passes_the_ceiling_through`.
  - `backend/tests/test_blind_grading_service.py`: `test_safety_ceiling_run_never_becomes_a_session`. With 20 usable cards but `safety_ceiling_hit`, the result is `value_core_failed` 503. The session is `failed` with `{"code": "value_core_failed"}` and no cards.
- [x] **Sabotage (evidence, not committed):** an 8 s clock `break` was re-added in the partner loop and the simulated-load test re-run. It **failed** at `assert loaded == baseline`: "Right contains 1477 more items, first extra item: FairTrade(partner_team_id='team03', …)". The old clock kept 2 of 11 partners (336 of 1,813 trades). After the revert the test passes again.
- [x] **Code-walk proof** (file:line on this branch):
  1. `backend/value_core/core.py:404` `started = time.perf_counter()`. The core reads the clock in only three other places. `:442` and `:514` compare it with `safety_ceiling_s`. `:542` computes `diag.elapsed_ms`, which only measures.
  2. Partner loop `:441-443`: the only clock exit is `> safety_ceiling_s`. It sets both flags and breaks.
  3. Check loop `:508-515`. The count caps come first: `checks[kind] > max_checks_per_partner` stops base pairs and skips throw-in variants. Then the ceiling check runs every 1,000 checks.
  4. `:528-530`: the keep cap `cfg.max_per_partner` with the round-robin interleave. Counts only.
  5. `:534`: `if diag.budget_exhausted: break`. Since this change only the ceiling sets that flag.
  6. `:537-540`: the one ERROR line, logged only when `safety_ceiling_hit`.
  7. Conclusion: below the ceiling, nothing in the result depends on the clock. The output is a function of (snapshot, request, cfg, caps) only.
  8. `backend/value_core/pipeline.py:24-25`: None ⇒ `core.SAFETY_CEILING_S`, passed through.
  9. `backend/blind_grading.py:581-584`: a ceiling run raises `GradingError("value_core_failed", 503)` before the too-few check and before any meta. `build_session` at `:254` calls it, and `:279-280` `_mark_failed(session_id, {"code": err.code, **err.detail})` marks the session failed.
  10. Callers: `server.py:7558` (`vc_pipeline.run`, no ceiling argument ⇒ 30 s default), `eval/value_core_bench.py:573`, `eval/value_core_recall.py:255` and `blind_grading.py:566`. None of them passed `time_budget_s`.
- [x] **B3 before/after comparison (evidence, not committed):** `origin/main`'s `core.py` was loaded beside the new one and both were run on the same inputs. That covers all 12 seats of `synthetic_league()` plus the 14-team perf fixture (`test_value_core_perf.fourteen_team_league`), default `CoreConfig`. **13/13 identical** (trades, order and diagnostics bar `elapsed_ms`). Wall time for identical work swung from 0.8 s to 8.1 s with machine load. Earlier in the session, `origin/main`'s core on the 14-team fixture under contention took 10.5 s and stopped at 11 of 13 partners. The new core completes all 13 (2,600 trades).
- [x] **Test runs** (2026-10-20, `FTF_KTC_VALUES_FILE` set to the committed `backend/tests/fixtures/ktc_rankings_snapshot_2026-07-17.html`, so there was no live KTC fetch):
  - Focused (`test_value_core_*`, `test_blind_grading_*`, `test_fit_engine`, `test_eval_*`, `test_scorecard_*`): **430 passed**. That is the 424 baseline on `origin/main` plus 6 new tests, the same count as an earlier run without the fixture.
  - Full suite `python3 -m pytest backend/tests`: **7,723 passed, 1 skipped, 0 failed** (29 min). `test_rookie_scope.py` passed.
  - Hermeticity gap: `FTF_DP_VALUES_FILE` is not set by `conftest.py`, so any process that imports `backend.server` still fetches the DynastyProcess player CSV live (`data_loader.py:624-640`). This is a suite-level gap, reported to the engines lead, and no fixture was added here.
- [ ] **Manual TestFlight checklist:** WAIVED because the change is backend-only and no client surface changes. Runtime load cannot be reproduced on demand from a phone, and the simulated-load and contention tests cover it.
- **Maestro delta:** n/a, retired by D-056.
- `testID`s added/renamed: none.

### B3 statement

Decks are unchanged, except for runs that previously hit the 8 s clock, which now complete. Below 8 s the old and new code paths take identical decisions: the only difference is the threshold the clock is compared against. The B3 comparison (13/13 identical) confirms this, as do the unchanged pre-existing value-core suites. `test_same_deck_when_the_clock_runs_past_the_old_budget` confirms the second half: under clock pressure that cut the old core (sabotage: 2 of 11 partners kept), the new core returns exactly the unpressured deck.

**Tradeoff to note:** a run that used to be cut at 8 s under load now runs to completion. The work is bounded by counts, at most partners × 2 × 40,000 checks. A loaded instance therefore serves a complete deck later instead of a partial deck at 8 s. The PRD's p95 < 8 s latency target stands, but it is now measured on full decks, not enforced by truncation.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route or contract change. SessionView `error` codes are unchanged, because the ceiling reuses the documented `value_core_failed` (:1135). The in-memory job `value_core` block (:588) is unchanged: `server.py` picks its fields explicitly, and the block is not returned anyway. |
| `docs/data-dictionary.md` | n/a | No schema change. `valuation_json.core.budget_exhausted` (:599) and `grading_sessions.source_json` (:1942) keep their keys. `error_json` codes (:1943) are unchanged. |
| `docs/config-reference.md` | **needs update by the config-reference owner (engines lead)** | :1602 still lists `core.TIME_BUDGET_S = 8.0 (enumeration stops and the partial pool is ranked and served)`. It should read `core.SAFETY_CEILING_S = 30.0` (a pathology marker: partial pool, ERROR log; not a budget). There is no knob, flag or env change. |
| `docs/cross-client-invariants.md` | n/a | `SessionView.error.code ∈ value_core_too_few \| value_core_failed` (:1300) is unchanged by design (see §0, deviation). |
| `docs/architecture.md` | **needs update by the architecture owner (eng-architect / engines lead)** | :283 says the core "is bounded by an 8 s time budget". It should say it is bounded by the check and keep caps, with a 30 s safety ceiling for pathology only. :418 (Calibration failure): a safety-ceiling run is now also `failed` with `value_core_failed`. |
| `living-memory/LLD.md` | **needs update by the lead (living-memory owner)** | Only if "engines are count-bounded, never clock-bounded" is to be recorded as an engine convention. The value core now follows it; the legacy `trade_service` deadlines in G-065 do not. |
| `living-memory/HLD.md` | n/a | No architecture shift: same modules, same data flow. |
| `docs/glossary.md` | n/a | "Safety ceiling" is an internal engine constant name, not a domain or UI term. |
| ADR or `DECISIONS.md` | **needs an entry by the lead (living-memory owner)** | (1) The value core is count-bounded with a 30 s pathology ceiling (G-065). (2) A ceiling run reuses `value_core_failed` rather than a new code, to avoid an API and cross-client invariant change. |
| `docs/plans/value-core-engine/` | **updated** | `lld.md` §3 constants, §4.1 API, §4.5 pseudo-code, §4.6 table and expected load, §4.7, §6, §10. `specs.md` §3 `CoreDiagnostics`, acceptance criteria 4–6, the test table (`test_check_cap`, `test_safety_ceiling_marks_pathology`), and the new `test_value_core_count_bound.py` block. `hld.md` §5 failure modes and §6 time. `prd.md` latency. |
| `docs/runbook.md` | **needs update by the runbook owner (ops-release / engines lead)** | :481 says "`budget_exhausted=True` means the 8 s core budget stopped enumeration". It now means the 30 s safety ceiling fired (pathology), and that line comes with an ERROR `value-core: safety ceiling … hit`. |
| `docs/plans/blind-grading/` | **updated** | `lld.md` §6.3 step 8, `hld.md` §3.2 (step 5 bullet) and the §8 failure-mode table, and the `specs.md` test table (new `test_safety_ceiling_run_never_becomes_a_session` row). Each says a safety-ceiling run ends as `value_core_failed` 503 (session failed, no cards), with the cause in the ERROR log. |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` + testid-lint on the pushed sha. This worker does not push; the lead merges.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry, written by the lead (this worker may not edit `living-memory/`). Contents: the tests above, the sabotage run, the B3 comparison and the code walk. Pre-push: `FTF_SKIP_SIM_GATE=1` (standing posture under D-056).
- **Simulator-gate tier:** n/a, retired by D-056.
- **TestFlight verification:** none (waived in §3).
- Express lane declared by the operator? **no** (full gates).
