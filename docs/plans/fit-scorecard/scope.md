# Feature Scope — Fit-first generation (Approaches A and B) in Calibration

**Date:** 2026-10-09
**Entry point:** direct ask. The operator proposed fit-first generation and approved the plan doc ("Fit Scorecard Test Plan", claude.ai/code/artifact/8886e24e-2cb7-482e-b263-dcf7b749c1f4). After the offline test failed, the operator chose "Add A + fixed B".
**Builder:** lead session
**Operator sign-off on waivers:** not needed (no waivers)

The plan, the frozen multipliers and the round-1 results live in the plan doc. This file is the repo's gate record.

## 1. Analytics scope

- [x] **(b) Existing events cover it.** Grades and tags land in `grading_cards` and are read with `GET /api/admin/grading/report`, now per arm including `fit_a` / `fit_b`. No new events.

## 2. Schema & flag scope

- New/changed tables or columns: none. New JSON values only: `grading_cards.arms_json` arms `fit_a` / `fit_b`; `grading_sessions.counts_json` / `source_json` keys (data-dictionary updated).
- New/changed feature flags: none. The fit arms are visible only through Calibration (`grading.blind`), and the app's Results screen shows only the two original arms.
- New env vars / `model_config` keys: none. The multipliers are code constants in `backend/fit_engine.py`, frozen before the first run.

## 3. Evidence scope

- [x] **Unit tests:**
  - `backend/tests/test_fit_engine.py`: demand, both team values incl. the B veteran fix, profiles, the generator on both arms incl. picks_for_players, deck caps, projections.
  - `test_blind_grading_service.py::test_add_fit_arms_folds_blind_and_keeps_answered_cards`, `::test_fold_aborts_when_a_moving_card_was_answered`.
  - `test_blind_grading_routes.py::test_admin_add_fit_arms_route`.
  - The e2e blinding test forbids the new arm names and versions in card payloads.
- [x] **Offline test:** `backend/eval/fit_scorecard_test.py` on round-1 grades. Neither approach passed: Q1 AUC A 0.58, B 0.43 (pre-registered); best baseline 0.66. Results are in the plan doc.
- [x] **Dry run on the 12 real seats (read-only):** A 1–18 cards per deck (133 total), B 0–6 (36), each in under 125 ms.
- [x] **WAIVED — TestFlight checklist:** no client change. The app ignores unknown arms (`GradingResults.tsx` renders `ARM_ORDER` only), and the deck simply grows.

## 4. Docs scope

| Doc | Updated? |
|---|---|
| `docs/api-reference.md` | **updated**: `POST /api/admin/grading/add-fit-arms`; the report row lists the fit arms |
| `docs/data-dictionary.md` | **updated**: `arms_json`, `counts_json`, `source_json` |
| `docs/architecture.md` | **updated**: components row `fit_engine.py` |
| `living-memory/HLD.md` | **updated**: major-components row |
| `living-memory/LLD.md` | n/a: no convention shift (a leaf module on existing patterns) |
| `docs/glossary.md` | **updated**: fit engine / team value, fit profile |
| `docs/runbook.md` | **updated**: add-fit-arms curl and expectations |
| `docs/cross-client-invariants.md` | n/a: no shared constant (arm names are server-only) |
| DECISIONS | **D-200** |

## 5. Ship gate declaration

- CI green on the pushed sha. The TEST_LEDGER entry names the offline test, the dry run and the prod fold-in outcome.
- Express lane: **no**.
