# #427 — investigation: where the stud tax lives, and what a first-round exemption touches

**Date:** 2026-09-08 · **Planner:** G-427 planner (read-only on code) · **Branch:** `claude/feedback-422-428`
**Report:** #427, mattmurf77, 2026-09-08 17:02Z, app 1.17.2, screen TradesHome — *"First round picks should not be devalued. So two firsts straight up for a player in 2 1sts tier should be considered even. Other draft picks should still be subject to the tax."*

All numbers below were computed by importing the live modules against `_DEFAULT_CFG` (no DB) — see §4.

## 1. The tax: one shared function, two modes, plus a second copy in gen-v2

**`package_value_v2(values, v_max, n_other, other_values)` — `backend/trade_service.py:1658-1741`.** Takes a list of raw asset **values** (floats, no ids), the trade-wide best value, and the other side's values. Dispatches on the thread-local stud-tax mode (`:1408-1448`, per-user `users.stud_tax_mode`, `database.py:5013-5026`):

- `off` (`:1712-1713`): naive sum. No tax.
- `market` (default, `:1714-1715` → `_package_value_market` `:1743-1808`): **depth discount per asset** `v · (floor + (1−floor)·(v/bench)^γ)` with `γ = package_adj_gamma_market` 0.5 (`:98`), `floor = package_floor_market` 0.70 (`:97`) when the side holds the trade's best asset, else `bench = v_max`, `floor = package_floor_cross` 0.40 (`:108,:115`, the 2026-08-21 cross-benchmark fix). The side's total discount is capped at `package_discount_cap` 0.35 × naive (`:1792-1793`). Then a **crown credit** of `crown_rate_market` 0.08 per asset with value ≥ `crown_elite_value` 6000 on either side, phased out by naive skew (`:1795-1807`). A single-asset side is never depth-discounted (the bracket is 1.0 at `v == bench`).
- `heavy` (`:1717-1741`): legacy `v · (0.15 + 0.85·(v/v_max)^1.5)` (`package_adj_gamma` `:165`) plus the outnumbered-side crown premium at `crown_rate` 0.12.

**The discount is applied per asset, summed per side.** The cap is per side. Nothing in the function knows what an asset *is*: a first-round pick with value 2117 is taxed exactly like a WR with value 2117. **Picks are currently taxed like players — that is the defect.**

**Second copy — gen-v2's own curve.** `trade_gen_v2.consolidated_value(values)` (`backend/trade_gen_v2.py:149-166`): `v · (0.15 + 0.85·(v/v_best_own)^1.5)` (`gen2_consol_floor`/`_gamma`, `trade_service.py:753-754`). Used only for gen-v2's dual-board ε gate and its own ±band (`:619-620`, `:702-703`, `:813-816`, via `side_gain` `:171-178`). Gen-v2 is served: `trade.bakeoff` is on (`config/features.json:244`) and prod has `bakeoff_serve_interleaved = 1.0`, `bakeoff_include_gen_v2 = 1.0` (`living-memory/CHANGELOG.md:509`), so 10 of every 30 organic cards come from it. Its **cards' displayed values** come from `_consensus_packages` → `package_value_v2` (`trade_gen_v2.py:1189`, `:1212-1213`), so a served gen-v2 card would *display* even while its gate had *priced* the firsts taxed — both must change together.

## 2. Who calls it (blast radius)

Every caller has the asset **ids** in hand next to the values, so an exemption mask can be built at the call site:

| Surface | Site |
|---|---|
| Calculator (mobile + web) | `server.py:11886-11908` route pins mode → `_trade_evaluate_impl` `:11910-12060`; values via `_consensus_packages` `trade_optimizer.py:110-119` and `_fairness_v3` `:122-155`; `even = point_ratio >= 0.95` `:12028`; verdict payload `_value_verdict_payload` `:946-978`; itemised adjustments `_evaluate_adjustments` `:1003-1035` (calls `package_value_v2` with/without `n_other`). Web calls the same route: `web/calculator.html:256`; mobile `mobile/src/api/calc.ts:154,:299,:328`. **Confirmed: no client-side valuation math.** |
| Deck cards' value bar | `trade_card_to_dict` `server.py:13441-13450` — same `_value_verdict_payload` over `card.give_value/receive_value` stamped by the generator. |
| Consensus gates (asset ideas, fair-packages, overhaul, likes-you) | `price_consensus_package` `trade_service.py:2210-2231` → `eval_consensus_package` `:2233-2280`. |
| v2 divergence generator | `trade_service.py:1972-1975, :2224-2227, :2456-2459, :6622-6626, :6938-6941, :7002-7017, :7488-7491, :7523-7526`. |
| v3 optimizer | `trade_optimizer.py:116-119, :138-141, :528-538`. |
| Fit challenger (ADR-013) | `trade_gen_fit.py:681-690`. |
| Owner constructor (ADR-019) | `trade_gen_owner.py:539, :566` pin `market`; its evaluation rides `trade_policy._package_pair` `trade_policy.py:276-292` (values-only signature; callers `:712, :717` hold ids). |
| Trade breaker, win-now | `trade_breaker.py:568-571`, `win_now_optimizer.py:213` (pin). |
| Gen-v2 (served, bakeoff group 3) | `trade_gen_v2.py:149-166` + the four call sites above. |

## 3. What a "first-round pick" is, by id

Two id shapes, both already parsed elsewhere: generic rungs `generic_pick_{round}_{tier}` (`server.py:1655`; parser `pick_values.parse_generic_pick_id` `:216-226`) and owned picks `{league_id}_{season}_{round}_{original_roster_id}` (`database.make_pick_id` `:10842-10849`; parsed with a league id in `receipts_service.pick_round` `:216-236` and `suggestion_telemetry.py:196-204`). Owned-pick pseudo-players carry `position == "PICK"` but **no round attribute** (`_owned_pick_assets`, `server.py` ~L77-85 of the function), so round must come from the id: `pid.rsplit("_", 3)` → `[league, season, round, orig]`. Player ids in every pool are digit strings (Sleeper ids; the ESPN/MFL paths crosswalk to them) — the build adds a guard test that no player id in the checked-in snapshot satisfies the owned-pick parse. Season/year is irrelevant to the rule (D-079 already makes round 1 flat year over year, `pick_values.py:148-153`).

## 4. Worked example, live config

Ladder (`pick_values.py:24-45`, `elo_to_value` `trade_service.py:1640-1642`, k 0.005 / ref 1500 / base 1000): **Mid 1st = Elo 1650 → 2117.0**; Early 1st 3004.2; Late 1st 1491.8; Mid 2nd 606.5. Two Mid 1sts = **4234.0 → Elo 1788.6**, which is why the `firsts_2` band floor is 1788 (`tier_config.json` `_calibration`; band [1788, 1864] ⇒ values [4220.7, 6171.9]).

**P = a player at the `firsts_2` floor, Elo 1788, value 4220.7. Package = [Mid 1st, Mid 1st].**

| | give (2 firsts) | receive (P) | ratio | calculator verdict |
|---|---|---|---|---|
| Today, `market` | 3492.8 (each pick 2117.0 · (0.40 + 0.60·√(2117/4220.7)) = 1746.4) | 4220.7 | 0.828 | `fair`, favors P — **not even** |
| Today, `heavy` | 1913.5 | 4577.0 (crown premium) | 0.418 | `unfair` |
| Today, `off` | 4234.0 | 4220.7 | 0.997 | `even` |
| **After (R-1), `market`** | **4234.0** | 4220.7 | **0.997** | **`even`** (≥ 0.95) |
| After, `heavy` | 4234.0 | 4577.0 | 0.925 | `fair` — heavy keeps its crown premium |

Full before/after table for the regression cases is in `prd.md` §R-5.

Two honest limits of the rule as phrased. (a) A "2 firsts" player is a *band*: at mid-band (Elo 1826, value 5103.9) two Mid 1sts read 0.830 after the change — that is the band's width, not the tax. (b) Players ≥ 6000 (top of `firsts_2`, all of `firsts_3`+) still earn the market crown credit (`:1795-1807`), so three firsts for a 6351 player reads 0.926 after the change. Both are logged as open questions, not changed.

## 5. Tests and goldens that pin current numbers

- **Unchanged by construction** (literal float lists, no ids → mask never built): `test_stud_tax_modes.py`, `test_package_benchmark.py`, `test_crown_asset.py`, `test_fairness_gate_golden.py`, `test_consensus_consolidation_gate.py`.
- **Knob inventory guards:** `test_bakeoff_arm_a_golden.py:896-910` fails on any new `_DEFAULT_CFG` key until it is added to `_PINNED_KNOBS` and a MODEL_A decision is recorded; `:913` requires the profile name a real knob. Arm A must pin the new knob at 0 in `bakeoff_profiles.MODEL_A_PROFILE` (`:99-101` precedent, `package_bench_trade_wide`) so the golden stands un-recaptured.
- **`test_engine_quality_golden.py`**: fixtures include PICK assets on both sides (`:63`) and it pins `package_bench_trade_wide = 0` (`:85`); the new knob joins that pin so the byte-identity proof still holds.
- **End-to-end deck tests with firsts in multi-asset packages** may legitimately move (`test_engine_quality.py`, `test_overhaul_service.py`, `test_pick_swap_gate.py`, `test_trade_gen_fit.py`, `test_trade_breaker.py`, `test_sweetener_relative_band.py`, `test_knockout_refine.py`): the build runs the suite with the knob at 0 first (must be green), then at 1, and justifies each delta as "a first now counts at face".

## 6. Docs that describe the tax today

`docs/config-reference.md:786-793` (knob table), `docs/glossary.md:116` (Stud tax) and `:415` (Consolidation discount), `docs/cross-client-invariants.md:601-605` (mode strings — unchanged by this item), ADR-003 (crown premium), `docs/feedback/items/214-stud-tax/tuning-proposal.md` (market shapes).
