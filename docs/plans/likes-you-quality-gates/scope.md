# Feature Scope — likes-you injector quality gates (D-096)

**Date:** 2026-08-19
**Entry point:** direct ask (P0 of the deck-quality audit; reverses D-055 sub-decision (5) / Q-G6-1)
**Builder:** session `fix/likes-you-quality-gates`
**Operator sign-off on waivers:** not needed (no waivers — every section answered)

---

## 0. Problem, measured

`server._inject_likes_you_cards_impl` synthesises and boosts `TradeCard`s that face
none of the engine's quality gates. Its only floor, `likes_you_min_user_delta`
(default **−500**), explicitly permits the user to lose — and it is measured on
**raw summed values** while the `TradeValueBar` the user sees renders
**package-adjusted** values. Injected cards are pinned to deck position 1–3 by
`boost_score = max(composite) + 1.0`.

Read-only prod measurement (`deck_impressions.features_json` + `trade_impressions`,
one league, 198 served likes-you impressions / 51 distinct cards, 2026-08-11 → 08-19):

| | |
|---|---|
| Impressions where the value bar shows the user paying | **115 / 198** (58%) |
| Worst single card (bar delta) | **−5,571** (audit's independently-derived worst: −6,019) |
| Same figure on the gated deck | 348 / 8,432, and 0 in the audit's stricter slice |
| Cards passing today's raw −500 floor but showing ≥ 500 loss on the bar | 5 (the unit mismatch, live) |

## 1. Analytics scope

- [x] **(b) Existing events cover it.** `deck_impressions.features_json` already
  stamps `likes_you`, `give_value`, `receive_value`, `fairness_score` per served
  card — the exact fields this measurement ran on, and the exact fields that will
  show the fix landing (user-pays share on `likes_you: true` rows should go to 0).
  No new event is needed and none is added.
- [x] **(c) waiver n/a** — (b) answered.

## 2. Schema & flag scope

- New/changed tables or columns: **none**.
- New/changed feature flags: **none**. `trade.likes_you` already gates the whole
  surface; adding a second flag would give two switches for one behaviour.
- New/changed `model_config` keys → `docs/config-reference.md`:

  | Key | Default | Meaning |
  |---|---|---|
  | `likes_you_gate_level` | **2.0** | 0 = pre-D-096 behaviour exactly; 1 = package-adjusted floor only; 2 = package floor + directional R1 + `filler_ok` |
  | `likes_you_min_user_gain` | **0.0** | the floor, in **package-adjusted** value-bar units (levels ≥ 1) |
  | `likes_you_min_user_delta` | −500.0 | **unchanged** — the legacy raw-sum floor, now read only at level 0 |

  **Ship-the-knob / deploy-free rollback:** `likes_you_gate_level = 0` restores
  today's behaviour exactly, in one value, with no deploy. Verified by
  `test_likes_you_gates.py::test_level_zero_is_byte_identical_to_legacy`.

## 3. Evidence scope

- [x] **Structural guard:** n/a — backend-only. No mobile source changes, so no
      `check-*.js` suite applies and no `testID` is added or renamed.
- [x] **Unit tests:** `backend/tests/test_likes_you_gates.py` (new, 17 tests) —
      pins the floor unit, the level ladder, directional R1, `filler_ok`, the
      no-cap-slot-consumed semantics, and that a gated-out existing card keeps its
      organic deck position rather than being dropped.
- [x] **Code-walk proof:** `docs/plans/likes-you-quality-gates/code-walk.md`.
- [x] **Manual TestFlight checklist:** `docs/plans/likes-you-quality-gates/testflight-checklist.md`.
- [x] `testID`s added/renamed: **none**.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added, renamed, removed, or contract-changed — the injector runs inside the existing `/api/trades/generate` job |
| `living-memory/LLD.md` | **updated** | likes-you injector gate contract |
| `docs/architecture.md` | n/a | module wiring and data flow unchanged; the injector keeps the same inputs, call site and return contract |
| `living-memory/HLD.md` | n/a | no new module, client, or major flow |
| `docs/cross-client-invariants.md` | n/a | no shared constant, enum, or colour changes; the knobs are backend-only |
| `docs/glossary.md` | n/a | no new domain term ("likes-you", "presentment rules", "package value" all already defined) |
| `docs/config-reference.md` | **updated** | the two new `model_config` keys + the changed role of `likes_you_min_user_delta` |
| `DECISIONS.md` entry | **added** | **D-096**, recording the reversal of D-055 sub-decision (5) / Q-G6-1 |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` re-run on the base commit and on the tip;
  `tsc --noEmit` and `testid-lint` unaffected (no mobile change).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`.
- **TestFlight verification:** checklist written (§3); operator to run, outcome to TEST_LEDGER.
- Express lane declared by the operator? **no** — full gates.
