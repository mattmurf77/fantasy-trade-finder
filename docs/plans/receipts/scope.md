# Feature Scope — Receipts

**Date:** 2026-08-21
**Entry point:** direct ask (operator-issued planning assignment; full gates, NOT express)
**Builder:** planning session on `plan/receipts` (dual-agent doc review); build session TBD
**Operator sign-off on waivers:** not needed (no waivers)

---

## 1. Analytics scope

- [x] **(a) New events specced:**

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `receipts_opened` | `league_id`, `status` (ledger/ready), `n_graded_28d`, `headline_bucket` (neg/flat/pos) | ReceiptsScreen mount with payload resolved | mobile |
  | `receipts_window_changed` | `league_id`, `window_days` | window chip tap | mobile |
  | `receipts_grade_run` | `graded`, `ungradeable`, `cap_hit`, `duration_ms`, `trigger` | end of each grading run | server-fired |

  Classification (same commit as emitters, house rule): `receipts_opened` → INTENT
  (deliberate feature engagement, precedent `find_trades_tapped`); `receipts_window_changed`
  → `NON_INTENT_EVENTS` (navigation, precedent `tab_selected`); `receipts_grade_run` →
  `SERVER_FIRED_EVENTS` + `NON_INTENT_EVENTS`.
  → follow-through: `docs/data-dictionary.md` (grades tables), taxonomy registries in
  `backend/analytics_taxonomy.py` + `backend/analytics_queries.py:63`.

## 2. Schema & flag scope

- **New tables:** `receipts_grades` (append-only grade per impression × window ×
  grader_version), `receipts_grade_runs` (run ledger) — DDL in [LLD.md §3](LLD.md);
  additive via `_migrate_db` → `docs/data-dictionary.md`.
- **New feature flags:** `receipts.grading` (grader + admin route; default **false**;
  graduation: P0 counts reviewed, job idempotent in prod, ledger populating) ·
  `receipts.screen` (user route + screen entry; default **false**; graduation: PRD §8.1
  criteria). Both → `config/features.json` + `feature_flags.py` `FLAG_KEYS` +
  `docs/config-reference.md`.
- **New `model_config` keys:** `receipts_grade_batch` (500) · `receipts_min_n` (10) ·
  `receipts_coverage_min` (0.5) · `receipts_pick_share_max` (0.5) ·
  `receipts_snap_tolerance_days` (3) → `docs/config-reference.md`. Deploy-free rollback
  levers: both flags; env kill switch `FTF_RECEIPTS_GRADE=0`.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-receipts.js` (+ `npm run test:receipts`) —
  pins: ReceiptsScreen registered as root-stack push; `FeedbackFAB
  activeScreen="Receipts"` mounted exactly once; three window chips bound to a single
  payload; no bare `Receipt` component name (collision guard vs `OutlookBiasReceipt.tsx`);
  flag-gated entry point.
- [x] **Unit tests:** `backend/tests/test_receipts_grading.py` — T-1…T-10 per
  [LLD.md §7](LLD.md) (module isolation, honesty theorem, anchor independence, pick rules,
  anti-survivorship imputation, snapshot matching, idempotency, regrade versioning, route
  contracts, append-only).
- [x] **Code-walk proof:** file:line trace at build time — serve → impression row →
  snapshot rows → grade row → API payload → screen render; the cron 202/daemon path;
  flag-off no-ops; the four forbidden-recompute rules (PRD DR-4) with their enforcing
  tests.
- [x] **Manual TestFlight checklist:** PRD §8.3 (9 steps) — run by the operator at P4.
- `testID`s added: `receipts-screen`, `receipts-window-chip-{14,28,56}`, `receipts-row`,
  `receipts-maturity` (must pass `mobile/scripts/testid-lint.sh`).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | at build | 3 new routes (cron, league receipts, admin metrics) |
| `living-memory/LLD.md` | at build | append-only + grader_version convention; receipts_ table family |
| `docs/architecture.md` | at build | new module `receipts_service.py` + grade-time data flow |
| `living-memory/HLD.md` | at build | new offline grading loop (module-level addition) |
| `docs/cross-client-invariants.md` | n/a | v1 renders no shared enums/hexes; revisit if shape labels ever render client-side |
| `docs/glossary.md` | at build | "swap edge", "preregistration", "receipt (graded suggestion)" |
| ADR / `DECISIONS.md` | at build | append-only grades + grader_version pattern; swap-edge metric choice |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (runs `check-*.js`) +
  `maestro-testid-lint` on the pushed sha.
- **Evidence recorded:** TEST_LEDGER entry naming the pytest suite, structural check,
  code-walk doc, and (at P4) the checklist outcome.
- **TestFlight verification:** PRD §8.3 checklist run by operator before
  `receipts.screen` graduates.
- Express lane declared by the operator? **No — full gates** (schema + API + flags =
  bright-line list).
