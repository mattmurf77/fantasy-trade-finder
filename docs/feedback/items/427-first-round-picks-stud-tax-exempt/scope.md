# Feature Scope — #427 First-round picks exempt from the stud tax

**Date:** 2026-09-08
**Entry point:** feedback #427 (mattmurf77, app 1.17.2, TradesHome) — polish path, batch plan [422-win-now-ffv3-unavailable/plan.md](../422-win-now-ffv3-unavailable/plan.md)
**Builder:** G-427 build agent (backend only), branch `claude/feedback-422-428`
**Operator sign-off on waivers:** needed — §1(c) analytics waived, §3 TestFlight checklist is the only runtime evidence

---

## 1. Analytics scope

- [ ] (a) New events specced: none.
- [ ] (b) Existing events cover it: n/a.
- [x] **(c) WAIVED — no analytics needed because:** this is a pure valuation-rule change inside `package_value_v2` / `consolidated_value`; no new user action, screen, or setting. The existing `stud_tax_mode_changed` event (`analytics_taxonomy.py:1375`) is untouched because the user-facing mode is untouched. Its effect on served cards is already observable through `deck_impressions` (give/receive values are stamped per card) and the receipts grader, so a before/after read needs no new emitter.

## 2. Schema & flag scope

- New/changed tables or columns: **none**.
- New/changed feature flags: **none**. `trade.crown_asset`, `trade.bakeoff`, `trade_gen.v2` unchanged.
- New `model_config` key: **`stud_tax_exempt_first_round`**, default **1.0** (seeded in `backend/database.py` model_config rows next to the #214 block, `:2812-2820`, and in `trade_service._DEFAULT_CFG`). `≤ 0` restores today's math byte-for-byte on every path — this is the deploy-free rollback lever (`POST /api/admin/config` → `reload_config`). Arm A pins it at `0.0` in `bakeoff_profiles.MODEL_A_PROFILE`. Documented in `docs/config-reference.md`. Not user-facing; does not add a `stud_tax_mode` string, so `docs/cross-client-invariants.md` § Stud-tax mode strings is unchanged.

**Bright line check:** no schema, no API contract change (`/api/trade/evaluate` shape identical; only numbers move), no feature-flag surface, no analytics events. A model_config knob is the established shape for engine tuning (D-079, 2026-08-21 benchmark fix). Full gates apply regardless — the operator did not declare express.

## 3. Evidence scope

- [ ] Structural guard `mobile/tests/check-*.js`: **n/a** — zero files under `mobile/` change.
- [x] **Unit tests:** new `backend/tests/test_first_round_pick_exempt.py` — the 14 RED-first cases in [prd.md](prd.md) R-5 (report case even at 0.997; seconds/players unchanged at 0.824; mixed [1st, WR] at 0.912; owned-pick ids; knob-off byte identity; player-id mask guard; adjustments row; gen-v2 curve; heavy mode). Updated: `test_bakeoff_arm_a_golden.py` `_PINNED_KNOBS` (+ MODEL_A pin), `test_engine_quality_golden.py` kill pin. Untouched and must stay green: `test_stud_tax_modes.py`, `test_package_benchmark.py`, `test_crown_asset.py`, `test_fairness_gate_golden.py`. Suite run twice: knob 0 (must equal today, 0 failures) then knob 1 (deltas listed and justified in `status.md`).
- [x] **Code-walk proof:** [investigation.md](investigation.md) §1-§2 traces the tax from `trade_service.py:1658-1808` through every caller (calculator `server.py:11910-12060`, cards `:13441-13450`, consensus gates `:2210-2280`, v2/v3/fit/owner/breaker/gen-v2) and confirms the web calculator (`web/calculator.html:256`) and mobile (`calc.ts:154`) hold no valuation math — one server change covers every client. The build's `status.md` re-cites each site after the edit.
- [x] **Manual TestFlight checklist:** prd.md § Operator checklist (4 steps: two 2027 firsts vs a `firsts_2` player → Even, no depth row; mid-band player → player ahead but picks at face; two 2027 seconds vs a `second` player → still taxed with a depth row; first + WR mixed → fair, depth on the WR only). This is the only runtime evidence the mobile calculator gets.
- [ ] WAIVED: no.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/renamed; `/api/trade/evaluate` and card payload shapes unchanged |
| `living-memory/LLD.md` | updated | one line under the package-value convention: exempt mask is built from ids at the call site, never inferred from value |
| `docs/architecture.md` | n/a | no module wiring change |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | mode strings and tier keys unchanged; no shared constant added |
| `docs/glossary.md` | updated | "Stud tax" entry (`:116`): first-round picks exempt from the depth discount (#427) |
| `docs/config-reference.md` | updated | new `stud_tax_exempt_first_round` row in the `package_*` table (`:786-793`) |
| ADR or `DECISIONS.md` | updated | D-NNN: firsts are the currency, not quarters; knob rationale; heavy-mode crown premium and market crown credit left alone; Q-a/Q-b logged in `OPEN_QUESTIONS.md` |
| `docs/plans/three-model-bakeoff/scope-phase2.md` | updated | arm-A disposition for the new knob (required by the inventory guard) |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` (+ the new file), `tsc --noEmit` (no mobile change, still runs), `testid-lint`.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry: unit cases, the knob-0 identity run, the knob-1 delta list, and the code-walk.
- **TestFlight verification:** operator runs the 4-step checklist after the Render deploy (backend-only — no EAS build needed; the calculator reads server numbers).
- **Express lane:** no — full gates.
- **Pre-push:** `FTF_SKIP_SIM_GATE=1` per D-056, evidence noted in the ledger.
