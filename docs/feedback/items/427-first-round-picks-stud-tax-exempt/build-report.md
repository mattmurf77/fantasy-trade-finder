# #427 — build report: first-round picks exempt from the stud tax

**Date:** 2026-09-08 · **Builder:** G-427 backend build agent · **Branch:** `feat/fb427-first-round-pick-tax-exempt` (base `0c01bb00`)
**Spec:** [prd.md](prd.md) (R-1…R-7), rulings in [reconciliation-log.md](reconciliation-log.md). Backend only; no mobile / web / flag / schema change.

## What shipped, in plain words

A first-round pick now always counts at its face value inside a multi-asset trade side. Second-round-and-later picks and players are still shaved by the depth discount exactly as before. Two Mid 1sts against a player at the floor of the `2 1sts` band now read **4234.0 vs 4220.7 = 0.997, Even** (was 3492.8 vs 4220.7 = 0.828, "fair, favors the player"). Rollback is one config write: `stud_tax_exempt_first_round = 0` restores today's numbers bit for bit.

## Code walk — mask → exempt contribution

Line numbers are post-edit on this branch.

### The rule (R-1)

| Step | Where | What |
|---|---|---|
| Knob | `backend/trade_service.py:127` `_DEFAULT_CFG["stud_tax_exempt_first_round"] = 1.0`; DB seed `backend/database.py:2820` (same default, next to the #214 rows) | read via `_c()` at call time, so `POST /api/admin/config` → `reload_config` flips it without a deploy |
| Entry | `trade_service.py:1670` `package_value_v2(values, v_max, n_other=None, other_values=None, exempt=None)` | new keyword; `:1737-1742` resolves it **once**: `exempt` becomes `None` unless at least one flag is True **and** the knob is `> 0`. Every branch below then runs the pre-#427 code path when `exempt is None` |
| `off` | `:1735-1736` | untouched — naive sum before the resolve step |
| `market` | `:1743` → `_package_value_market(values, other_values, v_max, exempt)` `:1779` | benchmark test `:1830-1834` unchanged — `own_max = max(values)`, `len(values) > 1`, over **all** values. `:1836-1839` (`exempt is None`) is the original contrib + cap, byte-identical. `:1840-1844`: `taxable = [v for v,e if not e]`, `exempt_sum = Σ exempt v`, `contrib = Σ_taxable v·(floor + (1−floor)(v/bench)^γ)`, `total = exempt_sum + max(contrib, Σtaxable·(1−cap))` — **cap on the taxable subset only**. Crown credit `:1847-1858` unchanged, over all values |
| `heavy` | `:1746-1756` | `exempt is None` → the original one-liner; else `Σ_exempt v + Σ_taxable v·(0.15 + 0.85(v/v_max)^γ)`. Crown premium `:1758-1775` unchanged (`side_sum`, `v_top`, `top_contrib` over all values) |
| gen-v2 curve (R-3) | `backend/trade_gen_v2.py:151` `consolidated_value(values, exempt=None)` | `v_best = max(values)` over all values `:169`; `:175-179` exempt at face + curve over the taxable subset when `any(exempt)` and the knob `> 0`; else the original sum `:180-183`. `_cval_side(ids, value_of)` `:186-189` is the one place gen-v2 prices a side from ids and builds the mask there |

### Who is exempt (R-2)

`trade_service.py:2350` `_is_first_round_pick_id(pid)` (lru-cached — the generators build masks inside enumeration loops) and `:2375` `first_round_pick_mask(ids)`, beside `is_pick_asset`. True when `pick_values.parse_generic_pick_id(pid)` returns round 1 (validated against `GENERIC_PICK_SEEDS`, so `generic_pick_1_gold` is False), or when `pid.rsplit("_", 3)` yields `[league, season, round, orig]` with a non-empty league, a 4-digit season, round `"1"` and a non-empty orig (`database.make_pick_id` shape; league ids may contain underscores). Non-strings, rounds ≥ 2 and every player id (bare digit strings — no underscore, so neither parse can match) are False.

### Every pricing site passes the mask (R-3)

| Surface | File:line | Mask source |
|---|---|---|
| Calculator + gen-v2 card display (`_consensus_packages`) | `backend/trade_optimizer.py:116-122` | `first_round_pick_mask(give_ids / recv_ids)` |
| Calculator point ratio (`_fairness_v3`) | `trade_optimizer.py:140-146` | ids |
| v3 optimizer surpluses (`_surpluses`, both boards) | `trade_optimizer.py:533-546` | `g_exempt` / `r_exempt` built once per combo |
| Consensus pricing (`price_consensus_package` — asset ideas, fair-packages, overhaul, likes-you, and `eval_consensus_package` via it) | `trade_service.py:2278-2283` | ids |
| Rank-divergence fairness (`signal_core` sides) | `trade_service.py:2024-2029` | `core_give` / `core_recv` ids |
| Overpay gate (`overpay_adjusted`) | `trade_service.py:2547-2552` | ids |
| Aggression tilt over cards | `trade_service.py:6715-6724` | `c.give_player_ids` / `c.receive_player_ids` |
| v2 `_fairness` | `trade_service.py:7035-7040` | ids |
| v2 both-board packages (`_uv`/`_mu`, `_vo`/`_mo`) | `trade_service.py:7101-7118` | `g_exempt` / `r_exempt` once per combo |
| v2 gap-sweetener gates (`_gap_gates_ok`) | `trade_service.py:7589-7594` | `g` / `r` ids |
| v2 `_emit` | `trade_service.py:7626-7631` | ids |
| Fit challenger `_surplus` | `backend/trade_gen_fit.py:687-692` | `ts.first_round_pick_mask` |
| Trade breaker `value_giving` | `backend/trade_breaker.py:569-574` | `view.recv_ids` / `view.give_ids` |
| Owner constructor policy gate (`_package_pair`) | `backend/trade_policy.py:276-298` signature gains `give_exempt` / `recv_exempt`; callers `:716-726` build both masks from ids | ids |
| Calculator adjustments row (`_evaluate_adjustments`) | `backend/server.py:1013-1026` | both `base` and `full` calls carry the mask, so a side of firsts has depth delta 0 and **no `package_depth` row** |
| gen-v2 ε gate (`side_gain`) | `trade_gen_v2.py:200` | `_cval_side` |
| gen-v2 ±band, sweetener re-check, `give_val_opp` | `trade_gen_v2.py:641-642, 724-725, 835-836, 864` | `_cval_side` |

Not changed, by design: `_trade_evaluate_impl` (`server.py` ~L11910) and Mode B — they price through `_consensus_packages` / `_fairness_v3`, which now mask internally; deck value bars (`server.py` ~L13460) — they re-serialise `card.give_value / receive_value` the generator stamped through the masked paths. `win_now_optimizer.py:213` only pins a mode. A post-edit scan found **zero** `package_value_v2(...)` calls without `exempt=` outside tests.

### Arm A / goldens (R-6)

`backend/bakeoff_profiles.py:102-110` pins `stud_tax_exempt_first_round = 0.0` in `MODEL_A_PROFILE`; `backend/tests/test_bakeoff_arm_a_golden.py:605` adds the key to `_PINNED_KNOBS`; `backend/tests/test_engine_quality_golden.py:87-90` pins 0 next to `package_bench_trade_wide`. Neither golden was re-captured; both pass. The decision line is in `docs/plans/three-model-bakeoff/scope-phase2.md` (row after `sweetener_gap_threshold`).

## Before / after — the PRD's table, measured

Through `trade_optimizer._consensus_packages` (the calculator's path), mode `market` unless noted, `trade.crown_asset` on.

| Case | give | receive | today | after | verdict after |
|---|---|---|---|---|---|
| a. report | [M1, M1] | P 4220.7 | 3492.8 / 4220.7 = 0.828 | **4234.0 / 4220.7 = 0.997** | even |
| b. seconds | [M2, M2] | 1213.1 | 999.8 / 1213.1 = 0.824 | 999.8 = 0.824 (unchanged) | not even |
| c. players | [2117, 2117] | 4234.0 | 3489.9 = 0.824 | 3489.9 = 0.824 (unchanged) | not even |
| d. mixed | [M1, WR 2117] | 4234.0 | 3489.9 = 0.824 | **3862.0 = 0.912** (first at face; WR 1745.0; cap 0.65·2117 inert) | fair, not even |
| e. any rung | [E1, L1] | 4496.0 | 3787.4 = 0.842 | **4496.0 = 1.000** | even |
| f. 1st + 2nd | [M1, M2] | 2723.5 | 2381.0 = 0.874 | **2531.3 = 0.929** | fair |
| g. 1-for-1 | [M1] | [M1] | 1.000 | 1.000 | unchanged |
| h. stud gives | [4234.0] | [M1, M1] | rv 3489.9 = 0.824 | **rv 4234.0 = 1.000** | even |
| i. owned ids | [L_2027_1_3, L_2028_1_7] | 4220.7 | 0.828 | **0.997** | even |
| j. knob 0 | case a | | 0.828 | 0.828 | byte-identical |
| l. adjustments | case a | | give: `package_depth −741.2` | **no give-side row** | |
| m. gen-v2 | `consolidated_value([3000, M1], exempt=[0,1])` | | ≈ 4385.0 | **5117.0**; `[M1, WR 1000]` taxes only the WR | |
| n. heavy | case a | | 1913.5 / 4577.0 | **4234.0 / 4577.0 = 0.925** (crown premium kept) | fair |

PRD nit: case b's "999.9" rounded each piece before summing; the engine rounds the side once → 999.8 today and after. Pinned to the actual value since the case is "unchanged".

## Evidence

### RED — new tests against the pre-fix code (`0c01bb00`, before any edit)

`pytest backend/tests/test_first_round_pick_exempt.py -q` → **41 failed, 4 passed** (the 4 are the "unchanged" cases c, g, `off`, and the elite crown read). Representative lines:

```
test_a_two_firsts_vs_firsts_2_floor_player_is_even
E       assert (3492.8, 4220.7) == (4234.0, 4220.7)
test_d_first_plus_wr_taxes_only_the_wr
E       assert (3489.9, 4234.0) == (3862.0, 4234.0)
test_e_early_and_late_first_both_exempt
E       assert (3787.4, 4496.0) == (4496.0, 4496.0)
test_f_first_plus_second_discounts_only_the_second
E       assert (2381.0, 2723.5) == (2531.3, 2723.5)
test_h_stud_on_the_give_side_is_symmetric
E       assert (4234.0, 3489.9) == (4234.0, 4234.0)
test_i_owned_first_round_pick_ids_are_exempt
E       assert ((3492.8, 4220.7) == (4234.0, 4220.7)
test_l_adjustments_have_no_depth_row_for_two_firsts
E       AssertionError: assert ['package_depth'] == []
test_n_heavy_mode_exempts_depth_but_keeps_the_crown_premium
E       assert (1913.5, 4577.0) == (4234.0, 4577.0)
test_knob_default_is_on
E       KeyError: 'stud_tax_exempt_first_round'
test_j_knob_off_mask_is_ignored_byte_for_byte[*]  (18×)
E       TypeError: package_value_v2() got an unexpected keyword argument 'exempt'
test_m_consolidated_value_exempts_firsts
E       TypeError: consolidated_value() got an unexpected keyword argument 'exempt'
test_k_mask_true_only_for_round_one_pick_ids
E       AssertionError: trade_service.first_round_pick_mask is missing
test_evaluate_report_case_is_even / test_evaluate_mixed_package_is_fair_not_even  FAILED
```

### GREEN — after the change

- `pytest backend/tests/test_first_round_pick_exempt.py -q` → **45 passed** (cases a–n, the 18-way knob-0 byte-identity grid across `market`/`heavy`/`off` with and without crown args, the no-mask/all-False identity, the taxable-subset cap proof, the 3,564-row player-id guard, both `/api/trade/evaluate` cases, `_fairness_v3`).
- Must stay green, untouched: `test_stud_tax_modes.py`, `test_package_benchmark.py`, `test_crown_asset.py`, `test_fairness_gate_golden.py` + the two pinned goldens → **65 passed**.
- Engine files the PRD flagged as "may move" (`test_engine_quality.py`, `test_overhaul_service.py`, `test_pick_swap_gate.py`, `test_trade_gen_fit.py`, `test_trade_breaker.py`, `test_sweetener_relative_band.py`, `test_knockout_refine.py`, plus `test_trade_gen_v2.py`, `test_gap_sweetener_arm_c.py`, `test_trade_policy.py`, `test_fair_packages.py`) at the live default (knob 1) → **316 passed, zero deltas** — no fixture in those files has a first inside a multi-asset side whose verdict flips, so there is nothing to justify.
- Full suite: `pytest backend/tests -q` → **5912 passed, 1 skipped in 1707.09s (0:28:27)** — 0 failed, 0 errors (foreground run on this shared machine; harness backgrounded it past the 10-min cap, summary read from the output file)

Knob-0 posture: the PRD asked for a second full run at knob 0. That is covered structurally instead — `test_j_knob_off_mask_is_ignored_byte_for_byte` proves the masked call equals the unmasked call bit-for-bit on every mode/shape, and both goldens run the whole deck fixture at the pin and pass un-recaptured.

## Docs

| Doc | Change |
|---|---|
| `docs/config-reference.md` | new `stud_tax_exempt_first_round` row (default 1.0, formula, modes, rollback, arm-A pin) after `package_floor_cross` |
| `docs/glossary.md` "Stud tax" | one sentence: firsts exempt from the depth discount (#427); crown credit unaffected |
| `docs/plans/three-model-bakeoff/scope-phase2.md` | arm-A disposition row (INCLUDED at kill value 0.0, golden un-recaptured) |
| `docs/cross-client-invariants.md`, `docs/api-reference.md` | n/a — no mode string, shared constant, route or payload shape changed |
| `living-memory/*` (DECISIONS D-NNN, LLD line, OPEN_QUESTIONS Q-a/Q-b, TEST_LEDGER) | **not in this agent's owned paths** — left for the orchestrator; suggested D text: "firsts are the currency, not quarters; knob is the rollback lever; heavy crown premium and market crown credit left alone" |

## Operator checklist (TestFlight, calculator, any league — backend-only, no EAS build needed)

1. Give: two 2027 firsts (owned, or the "2027 Mid 1st" rung twice). Receive: a player whose tier badge is **2 1sts** near the bottom of that band. Expect **Even** and no "Package depth" adjustment on the picks' side.
2. Same, receive a player mid-band. Expect the player side ahead, but the give side's value now equals the two picks' face values summed.
3. Give: two 2027 seconds. Receive: a player badged **2nd** worth about two seconds. Expect the player side ahead (seconds still taxed) with a "Package depth" row on the picks' side.
4. Give: one first + one WR of similar value. Receive: a single player of the summed value. Expect "fair", not even; the depth row shows a deduction on the WR only.

Rollback without a deploy: `POST /api/admin/config` with `stud_tax_exempt_first_round = 0`.
