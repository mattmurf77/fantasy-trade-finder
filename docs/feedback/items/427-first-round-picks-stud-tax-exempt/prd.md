# PRD — #427 First-round picks are exempt from the stud tax

**Date:** 2026-09-08 · **Path:** polish (valuation rule) · **Platform:** backend only · **Branch:** `claude/feedback-422-428`
**Report:** #427 (mattmurf77, 1.17.2, TradesHome): *"First round picks should not be devalued. Two firsts straight up for a player in the 2-1sts tier should be even. Other draft picks should still be subject to the tax."*
**Evidence:** [investigation.md](investigation.md) — every file:line and number below is derived there.

## Decision in plain words

Today the engine shaves every piece of a multi-asset package below face value ("four quarters ≠ a dollar"). It does that to first-round picks too, so two firsts price at 3,492.8 against a player worth 4,220.7 — the calculator says the player side wins. The owner's rule: a first is the currency of dynasty, it is never a "quarter". After this change a first-round pick always counts at face value inside a package; 2nd+ round picks and players are still taxed. Two Mid 1sts vs a floor-of-`firsts_2` player becomes 4,234.0 vs 4,220.7 — even.

## Requirements

**R-1 — The rule.** In `package_value_v2` (`backend/trade_service.py:1658`) and `_package_value_market` (`:1743`), an asset flagged *exempt* contributes its **face value** to its side. Everything else is unchanged:
- taxable subset `T = [v for v, e in zip(values, exempt) if not e]`, exempt sum `X = Σvalues − ΣT`;
- `market`: benchmark selection is unchanged and still uses **all** values (`own_max = max(values)`, `len(values) > 1`, `:1783-1789`); `contrib = Σ_{v∈T} v·(floor + (1−floor)·(v/bench)^γ)`; **cap applies to the taxable subset only**: `total = X + max(contrib, ΣT·(1−cap))`; crown credit (`:1795-1807`) unchanged over all values.
- `heavy` (`:1717-1741`): `total = X + Σ_{v∈T} v·(0.15 + 0.85·(v/v_max)^γ)`; the outnumbered-side crown premium is unchanged.
- `off`: unchanged. `exempt=None` (or all-False) is byte-identical to today on every path.

**R-2 — Who is exempt.** New helper `first_round_pick_mask(ids) -> list[bool]` beside `is_pick_asset` (`trade_service.py:2282`): True when `pick_values.parse_generic_pick_id(pid)` (`pick_values.py:216`) returns round 1, or when the owned-pick shape `{league}_{season}_{round}_{orig}` (`database.make_pick_id` `:10842`) parses via `pid.rsplit("_", 3)` with a 4-digit season and round `1`. Any season. Rounds ≥ 2 and every player → False. A guard test asserts no player id in the checked-in DP snapshot / universal pool is ever True.

**R-3 — Every pricing site passes the mask.** `package_value_v2(..., exempt=first_round_pick_mask(ids))` at: `trade_optimizer.py:110-119` (`_consensus_packages` — the calculator and gen-v2 cards), `:122-155`, `:528-538`; `trade_service.py:2210-2231` (`price_consensus_package` — asset ideas, fair-packages, overhaul, likes-you), `:1972, :2224, :2456, :6622, :6938, :7002-7017, :7488, :7523`; `trade_gen_fit.py:681-690`; `trade_breaker.py:568-571`; `trade_policy.py:276-292` (signature gains ids or a mask; callers `:712, :717`); `server.py:1003-1035` (`_evaluate_adjustments` — so the calculator's "Package depth" row reads 0 for a first). Gen-v2's own curve gets the same rule: `trade_gen_v2.consolidated_value(values, exempt=None)` (`:149-166`), masks built at `:177-178, :619-620, :702-703, :813-816`. Gen-v2 is served in prod (`CHANGELOG.md:509`), so leaving it out would let a card display "even" while its gate had priced the firsts taxed.

**R-4 — Knob.** `model_config` key **`stud_tax_exempt_first_round`**, default **1.0**, seeded in `database.py` next to the `#214` rows (`:2812-2820`) and in `trade_service._DEFAULT_CFG` (`:97-115`). Read once inside `package_value_v2` / `consolidated_value`: `≤ 0` ⇒ the mask is ignored (byte-identical to today). This is the deploy-free rollback lever (`POST /api/admin/config` → `reload_config` `:1310`). It is **not** a user-facing option and does not touch `stud_tax_mode`; D-144's "no option to flip" ruling was about pick *pricing* modes and does not apply. Arm A pins it at `0.0` in `bakeoff_profiles.MODEL_A_PROFILE` (`:99-101` precedent).

**R-5 — Regression tests, RED first** (new file `backend/tests/test_first_round_pick_exempt.py`; literal values, `market` mode pinned, `trade.crown_asset` on; M1 = 2117.0, E1 = 3004.2, L1 = 1491.8, M2 = 606.5):

| Case | give | receive | today | after | assertion |
|---|---|---|---|---|---|
| a. the report | [M1, M1] (2 firsts) | P = 4220.7 (`firsts_2` floor, Elo 1788) | 3492.8 / 4220.7 = 0.828 | **4234.0 / 4220.7 = 0.997** | `favors == "even"`, ratio ≥ 0.95 via `/api/trade/evaluate` with `generic_pick_1_mid` ×2 |
| b. seconds still taxed | [M2, M2] | P = 1213.1 (`second` tier, Elo 1538.6) | 999.9 / 1213.1 = 0.824 | **unchanged** 0.824 | not even |
| c. players still taxed | [WR 2117, WR 2117] | P = 4234.0 | 0.824 | **unchanged** 0.824 | not even |
| d. mixed package | [M1, WR 2117] | P = 4234.0 | 3489.9 / 4234.0 = 0.824 | **3862.0** / 4234.0 = 0.912 | first at face (2117.0); WR still cross-benchmarked at floor 0.40 → 1745.0; cap inert (0.65·2117 < 1745); verdict `fair`, not even |
| e. any first rung | [E1, L1] | P = 4496.0 | 0.842 | **1.000** | even |
| f. first + second | [M1, M2] | P = 2723.5 | 0.874 | **0.929** | only the 2nd is discounted |
| g. 1-for-1 identity | [M1] | [M1] | 1.000 | 1.000 | unchanged |
| h. stud on the give side | [P 4234.0] | [M1, M1] | 0.824 | **1.000** | symmetric |
| i. owned-pick id | `[L_2027_1_3, L_2028_1_7]` priced 2117.0 each | P = 4220.7 | 0.828 | 0.997 | mask from owned ids |
| j. knob off | case a with `stud_tax_exempt_first_round = 0` | | | 0.828 | byte-identical rollback |
| k. mask guard | every player id in the snapshot | | | | `first_round_pick_mask` all False; `generic_pick_2_mid`, `L_2027_2_3` False |
| l. adjustments row | case a via evaluate | | depth −741.2 on give | **no `package_depth` row** on give | `_evaluate_adjustments` |
| m. gen-v2 curve | `consolidated_value([M1, M1], exempt=[1,1])` | | 2117·(1 + 0.15+0.85) | **4234.0** | and `[M1, WR]` taxes only the WR |
| n. heavy mode | case a, mode `heavy` | | 1913.5 / 4577.0 | **4234.0 / 4577.0 = 0.925** | depth exemption applies; heavy crown premium untouched |

**R-6 — Goldens.** `test_bakeoff_arm_a_golden.py:896-910`: add the key to `_PINNED_KNOBS` with the MODEL_A pin (`0.0`) — generation logic post-dating the reference SHA, same disposition as `package_bench_trade_wide`; golden **not** re-captured. `test_engine_quality_golden.py:85`: pin the new knob at 0 alongside `package_bench_trade_wide` so its byte-identity claim still holds. `test_stud_tax_modes.py`, `test_package_benchmark.py`, `test_crown_asset.py`, `test_fairness_gate_golden.py` use id-less float lists and must pass **untouched**. Deck-level tests that move (`test_engine_quality.py`, `test_overhaul_service.py`, `test_pick_swap_gate.py`, `test_trade_gen_fit.py`, `test_trade_breaker.py`, `test_sweetener_relative_band.py`, `test_knockout_refine.py`) are first proven green with the knob at 0, then each delta at 1 is justified in `status.md` as "a first now counts at face value".

**R-7 — Not changed.** `stud_tax_mode` and its three strings; the crown credit / premium (a pick is never ≥ 6000, so market mode is unaffected; heavy keeps its premium); `GENERIC_PICK_SEEDS`, tier bands, pick year decay, slot pricing (D-144); the calculator's 0.95 even band; the deck's `user_gain_epsilon` gate (an exactly-even trade still does not surface in the user-give direction — that is the gain gate, not the tax); `_pick_gap_equivalent`; every client (mobile/web/extension re-read the server's numbers; no client math exists).

## Docs

| Doc | Change |
|---|---|
| `docs/config-reference.md:786-793` | new row `stud_tax_exempt_first_round` (default 1.0, formula, rollback) |
| `docs/glossary.md:116` "Stud tax" | one sentence: first-round picks are exempt from the depth discount (#427); crown credit unaffected |
| `docs/cross-client-invariants.md` | n/a — mode strings unchanged; no shared constant added |
| `docs/api-reference.md` | n/a — `/api/trade/evaluate` contract unchanged (numbers move, shape does not) |
| `living-memory/DECISIONS.md` | D-NNN: firsts are currency, not quarters; knob rationale; heavy-mode crown premium left alone |
| `docs/plans/three-model-bakeoff/scope-phase2.md` | arm-A knob decision line (required by the inventory guard message) |

## Operator checklist (TestFlight, calculator, any league)

1. Give: two 2027 firsts (owned, or the "2027 Mid 1st" rung twice). Receive: a player whose tier badge is **2 1sts** near the bottom of that band. Expect **Even** and no "Package depth" adjustment on the picks' side.
2. Same, receive a player mid-band. Expect the player side ahead, but the give side's value now equals the two picks' face values summed.
3. Give: two 2027 seconds. Receive: a player badged **2nd** worth about two seconds. Expect the player side ahead (seconds still taxed) with a "Package depth" row on the picks' side.
4. Give: one first + one WR of similar value. Receive: a single player of the summed value. Expect "fair", not even; the depth row shows a deduction on the WR only.

## Open questions (for the operator, not blocking)

- Q-a: the rule says "a player in the 2-1sts tier". The band spans 4,220.7–6,171.9; two Mid 1sts are even only near its floor. Is that acceptable, or should firsts-denominated tiers be quantised for the verdict?
- Q-b: players ≥ 6,000 still earn the market crown credit, so three firsts vs a `firsts_3`-floor player reads 0.926. Suppress the credit when the other side is all firsts?
