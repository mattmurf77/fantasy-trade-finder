# Feature Scope — Live-deck quality filters (`deck.quality_filters`)

**Date:** 2026-10-14
**Entry point:** direct ask. The operator read the Calibration analysis and said "turn [the live engine's fixable problems] into changes" (D-207).
**Builder:** lead session
**Operator sign-off on waivers:** not needed (no waivers)

**Why.** Calibration grades of today's live engine (`owner_v2_bilateral`), from 3 graders, show four repeatable failures:
- junk filler is the reason on 59% of its 1–2 cards;
- breaking up the viewer's best piece scored 18% would-send vs ~47% otherwise;
- redundant TE/QB cards (e.g. McBride to the Bowers owner) graded 3.47 vs 3.91;
- "same guy again" was tagged 8 times by one grader.

**What.** `backend/deck_quality.py` applies four rules to the served deck. Breakup, filler and redundant drop cards; the repeat cap defers cards past the first 30. Protected cards are untouched. It runs in `_run_trade_job` after owner presentment and before the served/ghost split. Other serving surfaces (targeted search, `_owner_selected_ideas`, prepared inventory) are deliberately out of scope for v1: they are user-steered, and the deck is where the grades came from.

## 1. Analytics scope
- [x] **(b) Existing events cover it.** Served cards are still logged as `deck_impressions` (the dropped ones never are). The per-job counts go to the job log line and `significance_diag["quality_filters"]`. The effect is measured by Calibration's current arm (it reads served `deck_impressions`), via `GET /api/admin/grading/report?since=<deploy>`.

## 2. Schema & flag scope
- Tables / columns: none.
- Flag: `deck.quality_filters`. Code default false; `config/features.json` **true**, mirrored in the five release fixtures; config-reference row with kill switch and graduation criterion. The bake-off harness pins it off so golden captures are unchanged.
- Env / `model_config`: none. Thresholds are module constants, the same as the value core's.

## 3. Evidence scope
- [x] **Unit tests:** `backend/tests/test_deck_quality.py`. It covers each rule, the 1QB vs superflex QB cap, TE in superflex, two-TE leagues, the swap, an unknown lineup skipping only redundant, an unknown market never firing, protected cards, the repeat cap deferring, and counts and order. The wiring test runs the real trade job through the bake-off harness: flag on calls the filter with the viewer's team and every roster and serves its output; flag off never calls it.
- [x] **Full suite:** see TEST_LEDGER. `test_rookie_scope.py` is excluded because it is machine-local.
- [x] **Code-walk:** the insertion point sits after `trade_bilateral_presentment.present` and before the `served_final` / ghost split, so impressions, ghost telemetry and owner impression completeness all see only kept cards. `presentation["records"]` is re-aligned by identity (`_records_in_order`), because `retain_occurrences` only handles in-order removal. A filter exception restores `before_quality`.
- [x] **WAIVED: TestFlight checklist.** This is server-only and not visible as UI; the evidence is the Calibration current arm in the next round.

## 4. Docs scope
| Doc | Updated? |
|---|---|
| `docs/api-reference.md` | n/a: no route or contract change (fewer or re-ordered cards in the same payloads) |
| `docs/config-reference.md` | **updated**: flag row |
| `docs/architecture.md` | **updated**: components row |
| `living-memory/LLD.md`, `HLD.md` | n/a: one pure module on an existing pipeline step |
| `docs/cross-client-invariants.md` | n/a |
| `docs/glossary.md` | n/a: the terms (breakup, filler, redundancy) are already defined for the value core |
| DECISIONS | **D-207** (lead writes it at ship) |

## 5. Ship gate declaration
- CI green on the pushed sha. The TEST_LEDGER entry names the tests and the full-suite result. Express: **no**: this changes the live deck behind a flag.
