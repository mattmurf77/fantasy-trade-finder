# QA round 1 — agent B — 2026-09-08

## Summary: PASS (0 defects; 2 observations, neither blocks)

## Environment
- Worktree: detached at build tip `9a605049` (G-427 Phase 2 exit; code commit `9778c2a7` — `git diff 9778c2a7..9a605049 -- backend` is empty, so the tip IS the build). Diff under test: `git diff 0c01bb00..9a605049` (12 backend files, 4 docs, 2 item docs).
- Python 3.14.4 · Node v24.14.1 · scratch SQLite only (`data/trade_finder.db*` removed before every pytest run; nothing pointed at prod).
- Flags/knobs pinned by the tests themselves: `trade.crown_asset` on, `stud_tax_mode` via `stud_tax_override`, cfg reset to `_DEFAULT_CFG` (`stud_tax_exempt_first_round = 1.0`). No simulator, no Maestro (D-056).

## Results

| Test | Verdict | Evidence |
|---|---|---|
| Targeted subset (`test_first_round_pick_exempt`, `test_stud_tax_modes`, `test_package_benchmark`, `test_crown_asset`, `test_fairness_gate_golden`, `test_bakeoff_arm_a_golden`, `test_engine_quality_golden`) | PASS | `110 passed in 17.05s` (build report says 45 + 65 = 110 — matches) |
| Full `pytest backend/tests -q` | PASS | `5912 passed, 1 skipped in 1127.69s (0:18:47)` — exact expected posture, 0 failed, 0 errors (foreground run; harness backgrounded it past 10 min, summary read from the redirected output file) |
| RED-first: new test file against pre-fix engine (9 files at `0c01bb00`) | PASS (RED proven) | see § RED evidence — `40 failed, 5 passed in 3.63s`; restored to `9a605049` → `45 passed in 5.80s` |
| R-1 arithmetic — case a (report): `[M1, M1]` vs 4220.7 | PASS | hand formula = module: **(4234.0, 4220.7)**, ratio **0.997 → even** (≥ 0.95). Pre-fix / knob 0: **(3492.8, 4220.7)**, ratio 0.828 |
| R-1 arithmetic — case b: `[M2, M2]` vs 1213.1 | PASS | **(999.8, 1213.1)**, ratio **0.824**, favors receive — identical at knob 1 and knob 0 (seconds still taxed). PRD's "999.9" is per-piece rounding; the build pinned the true 999.8 (Phase-2 deviation 2, accepted) |
| R-1 arithmetic — case d: `[1st, WR 2117]` vs 4234 | PASS | **(3862.0, 4234.0)**, ratio **0.912**, favors receive (fair, not even). WR cross-benchmarked at floor 0.40 → 1745.0; cap inert. Knob 0: (3489.9, 4234.0) = 0.824 |
| R-1 heavy mode (case n) | PASS | knob 1: (4234.0, 4577.0) = 0.925; knob 0: (1913.5, 4577.0). Receive side 4577.0 identical both ways → heavy crown premium untouched |
| R-1 knob 0 ⇒ byte-identical | PASS | all three cases at knob 0 equal my hand re-derivation of the PRE-fix formula (all-False mask) to the 0.1; `test_j_knob_off_mask_is_ignored_byte_for_byte` 18/18 |
| R-1 gen-v2 `consolidated_value` | PASS | `[M1, M1]` exempt → 4234.0; `[M1, 1000]` with `[T, F]` = plain (1000 rides the curve either way, v_best = M1) |
| R-2 mask helper (code-walk + guard run) | PASS | see § Code-walk (a); my own run: 3,564 rows × {sleeper, espn, mfl} = **9,840 ids, 0 masked**; no id in the snapshot contains `_` |
| R-3 every pricing site masked | PASS | `git grep "package_value_v2("` outside tests → 34 call sites, **34 pass `exempt=`**; `consolidated_value(` outside tests → only via `_cval_side` (`trade_gen_v2.py:185-189`); no aliases besides `server.py:1007 pkg = ...package_value_v2`, which passes `exempt` at `:1024-1026` |
| R-3 calculator path | PASS | `trade_optimizer._consensus_packages` `:111-122`, `_fairness_v3` `:138-146`; `/api/trade/evaluate` uses them (`server.py:11918, 12028`); `test_evaluate_report_case_is_even` green |
| R-3 "Package depth" row | PASS | `server.py:1024` `base = pkg(vals, v_max, exempt=exempt)`; `depth = base − naive = 0` for an all-firsts side → `:1030 if depth != 0` omits the row. `test_l_adjustments_have_no_depth_row_for_two_firsts` green |
| R-4 knob default / seed / short-circuit | PASS | `trade_service.py:127` `_DEFAULT_CFG` = 1.0; `database.py:2820` seed row 1.0; `:1740-1742` `≤ 0 ⇒ exempt = None` before any branch; gen-v2 `:178-179` same test |
| R-4 existing-DB migration | PASS | `database.py:3585-3596` iterates `_MODEL_CONFIG_DEFAULTS` with `INSERT OR IGNORE` / `ON CONFLICT DO NOTHING` inside `_migrate_db` — a DB created before this commit gains the row on next boot; and `_c()` (`trade_service.py:1363`) falls back to `_DEFAULT_CFG` if the row is ever absent |
| R-6 goldens pinned, not re-captured | PASS | `test_bakeoff_arm_a_golden.py:605` adds the key to the `_PINNED_KNOBS` inventory; value comes from `MODEL_A_PROFILE` (`bakeoff_profiles.py:108` = 0.0) via `_reset_cfg(**MODEL_A_PROFILE)`; `test_engine_quality_golden.py:88` pins 0.0. `git diff --name-only` shows **no fixture/golden data file changed** |
| R-7 clients hold no valuation math | PASS | `git grep` over `web/`, `mobile/src`, `extension/`: web renders `d.adjustments` rows verbatim (`web/calculator.html:299-307`); mobile `AdjustmentsDisclosure.tsx:34-49` filters sides with zero rows and returns null — an absent `package_depth` row needs no client change; `calc.ts:96-100` is a type only |
| Knob-1 vs knob-0 engine files (11 files) | PASS | knob 1 (live default): `316 passed in 55.25s`; knob 0 (scratchpad pytest plugin forcing `_DEFAULT_CFG`, `_cfg` and the `_MODEL_CONFIG_DEFAULTS` seed to 0.0 — sanity-printed `cfg 0.0 seed [0.0]`): `316 passed in 45.68s`. Identical pass sets → the build report's "zero deltas" claim reproduces independently: no fixture in those files has a first inside a multi-asset side whose verdict flips |
| `cd mobile && npx tsc --noEmit` | PASS | exit 0 (sanity only — no mobile/web files in the diff) |

## RED evidence

`git checkout 0c01bb00 -- backend/trade_service.py backend/trade_gen_v2.py backend/trade_optimizer.py backend/trade_gen_fit.py backend/trade_breaker.py backend/trade_policy.py backend/server.py backend/database.py backend/bakeoff_profiles.py` then `pytest backend/tests/test_first_round_pick_exempt.py -q`:

```
40 failed, 5 passed in 3.63s

test_a_two_firsts_vs_firsts_2_floor_player_is_even
E       assert (3492.8, 4220.7) == (4234.0, 4220.7)      <- the report case
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
test_n_heavy_mode_exempts_depth_but_keeps_the_crown_premium
E       assert (1913.5, 4577.0) == (4234.0, 4577.0)
test_crown_credit_still_paid_on_elite_other_side
E       assert 4740.5 == 6351.0
test_l_adjustments_have_no_depth_row_for_two_firsts
E       AssertionError: assert ['package_depth'] == []
test_l_adjustments_still_show_depth_on_the_wr_in_a_mixed_package
E       assert (1 == 1 and -744.1 == -372.0)
test_knob_default_is_on
E       KeyError: 'stud_tax_exempt_first_round'
test_k_mask_true_only_for_round_one_pick_ids / test_k_no_player_id_in_the_snapshot_is_masked
E       AssertionError: trade_service.first_round_pick_mask is missing
test_j_knob_off_mask_is_ignored_byte_for_byte[*] (18x) / test_no_mask_and_all_false_mask_are_byte_identical[*] (3x)
E       TypeError: package_value_v2() got an unexpected keyword argument 'exempt'
test_m_consolidated_value_exempts_firsts / test_m_consolidated_value_knob_off_and_no_mask_are_identical
E       TypeError: consolidated_value() got an unexpected keyword argument 'exempt'
test_evaluate_report_case_is_even
E       assert (3492.8, 4220.7) == (4234.0, 4220.7)
test_evaluate_mixed_package_is_fair_not_even
E       assert 3490.1 == 3862.0
test_fairness_v3_point_ratio_uses_the_mask
E       assert ((3492.8, 4220.7) == (4234.0, 4220.7)
```

The 5 that pass on the pre-fix engine are exactly the R-7 "unchanged" assertions (`test_b_two_seconds_still_taxed`, `test_c_two_players_still_taxed`, `test_g_one_for_one_first_is_identity`, `test_j_knob_off_restores_todays_numbers`, `test_off_mode_unchanged`) — they are supposed to pass both before and after, so this is the expected RED shape, not a self-satisfying test. Restored with `git checkout 9a605049 -- <same 9 files>`; `git status` shows only this report untracked; re-run → `45 passed in 5.80s`.

## Code-walk proofs

**(a) `first_round_pick_mask` recognises only round-1 pick ids — `trade_service.py:2349-2380`.**
`_is_first_round_pick_id(pid)`: non-`str` → False (`:2366-2367`). `parse_generic_pick_id` (`pick_values.py:216-226`) requires the `generic_pick_` prefix, exactly two `_`-separated parts, a digit round, and `(round, tier) ∈ GENERIC_PICK_SEEDS` — so only `generic_pick_1_{early,mid,late}` return `(1, …)` → `parsed[0] == 1` (`:2368-2370`). Otherwise `pid.rsplit("_", 3)` (`:2371-2373`) must yield 4 parts with non-empty league, a 4-digit numeric season, round literally `"1"`, non-empty orig — the exact `database.make_pick_id` shape `{league}_{season}_{int(round)}_{orig}` (`database.py:10841-10850`), and `rsplit` keeps league ids that themselves contain `_` (`espn_12345_2028_1_7`, `mfl_2026_54321_2027_1_0001` → True in my run). Rounds ≥ 2 (`L_2027_2_3`, `L_2027_10_3`), 2-digit seasons (`L_27_1_3`), and all 12 generic rungs outside round 1 → False in my run. Player ids: every one of the 9,840 sleeper/espn/mfl ids in `fixtures/dp_playerids_snapshot_2026-07-11.csv` is a bare digit string with no `_` → cannot satisfy either shape → 0 masked. `first_round_pick_mask` (`:2375-2380`) is a positional list comprehension over `ids`, so index i of the mask is id i.

**(b) `_package_value_market` split — `trade_service.py:1824-1859`.** `naive = sum(values)` (`:1824`), `own_max = max(values)` (`:1827`), benchmark test `len(values) > 1 and v_max > own_max` (`:1831-1834`) — all over ALL values, unchanged. With `exempt` resolved (`:1840-1845`): `taxable = [v … if not e]`, `exempt_sum = Σ v where e`, `contrib` over `taxable` only, `total = exempt_sum + max(contrib, sum(taxable)·(1−cap))` — the cap binds on T only (my case-d check: 0.65·2117 = 1376 < 1745 → inert; `test_cap_applies_to_the_taxable_subset_only` proves X + 0.65·ΣT). Crown credit (`:1847-1858`) sums `v for v in values if v >= elite_ref` — ALL values, untouched. Heavy mode `:1749-1756`: same X + curve(T) split; the crown premium `:1758-1775` reads `sum(values)`, `max(values)` and `top_contrib` over all values — untouched (receive side 4577.0 identical at knob 0 and 1). `off` returns at `:1735-1736` before the mask is even resolved.

**(c) Every call site passes the mask, aligned with its values.** At each of the 34 `package_value_v2(` sites the values list is `[f(p) for p in IDS]` and the mask is `first_round_pick_mask(IDS)` over the *same* name in the *same* scope with no sort/filter between: `trade_service.py:2021-2029` (`core_give`/`core_recv` — both lists come out of `signal_core` and feed both), `:2275-2283`, `:2541-2552`, `:6712-6724` (`c.give_player_ids`/`c.receive_player_ids`), `:7032-7040`, `:7095-7118` (`g_exempt`/`r_exempt` built at `:7101-7102` from the same `give_ids`/`recv_ids` as `uvals_*` and `ovals_*`), `:7586-7594`, `:7623-7631`; `trade_optimizer.py:114-122`, `:138-146`, `:530-546`; `trade_gen_fit.py:684-692`; `trade_breaker.py:563-574` (`view.recv_ids`/`view.give_ids` — values at `:563-564` from the identical attributes); `trade_policy.py:716-725` (masks built from `give_ids`/`receive_ids` at `:716-717`, values from the same at `:718-719, :723-724`, both `_package_pair` calls take the same pair; `_package_pair` `:276-297` forwards `list(mask)` or `None`); `server.py:1008-1026`. Gen-v2: `_cval_side(ids, value_of)` (`trade_gen_v2.py:185-189`) builds values and mask from one `ids` argument; its callers pass lists (`give_options` are `list(c)` at `:660`, `recv_options` list literals `:655-656`; sweetened `_ng`/`_nr` are `list(...) + [s_pid]` from `trade_optimizer.py:1010-1012`). No generator is ever passed (a generator would silently yield an empty mask). Un-masked calls outside tests: **zero**.

**(d) Knob.** Default 1.0 at `trade_service.py:127` and `database.py:2820`; `MODEL_A_PROFILE` pin 0.0 at `bakeoff_profiles.py:108`. Short-circuit `trade_service.py:1740-1742`: `exempt = None` unless `any(exempt) and knob > 0`; every downstream branch keys on `exempt is None`. Gen-v2 `:178-179` same predicate. Goldens: inventory + pin only, no capture files touched.

**(e) Clients.** `web/calculator.html:299-307` and `mobile/src/components/AdjustmentsDisclosure.tsx:34-49` render whatever `adjustments` rows the server returns; neither computes a package value; `favors`/`verdict` come from `server._value_verdict_payload` (`:946-964`, `even` = `point_ratio >= 0.95` at the evaluate call `:12028-12036`). Deck cards go through the same `_consensus_packages` (`server.py:3430-3431`), so card and calculator verdicts share one function.

## Hunts (step 5)

- **Fairness-gate paths in deck generation.** All gates price through the masked sites in (c); the effect is symmetric — a two-firsts side now prices higher, which pulls a `[1st,1st] → floor-player` card INTO the band (intended) and pushes a `[1st,1st] → 3000-player` card OUT of it (also intended: the picks side is now visibly the overpay). No path lets a package through *unpriced*. Engine-file knob-1 vs knob-0 diff: 316 passed both ways (see Results) — no existing fixture's gate verdict moves, so the deck-level effect is only reachable through packages the current suite does not construct; checklist step 5 is the runtime check for that.
- **Mask/values misalignment by sort or filter.** None found: every site builds both from one id list in one scope (proof (c)); `rank_fairness` filters BEFORE building both; `signal_core` output feeds both. The one structural risk (a generator passed to `_cval_side`) does not occur.
- **`lru_cache` on `_is_first_round_pick_id`.** `maxsize=65536` (`:2349`) — bounded, LRU-evicted; my 9,840-id run left `currsize=9075`. Keys are the id strings themselves; every call site passes hashable str ids (a list/dict id would raise `TypeError`, but no caller constructs one).
- **Seed row on a pre-existing DB.** Covered in R-4 above (`database.py:3585-3596`, idempotent insert-if-missing; `_c()` fallback).
- **Legacy `package_value` (`trade_service.py:7907, 8129, 8146`)** is the pre-v2 KTC pre-filter under `_generate_for_pair` (`:7824`), reachable only when `trade_engine.v2` is false; `config/features.json:32` has it `true`. Out of PRD scope (R-7) and dormant — observation only.

## Findings

None blocking. Observations (no action required for ship):

### O-1: `_parse_owned_pick_id` (server.py:3309-3324) and `_is_first_round_pick_id` parse the owned-pick shape differently
- Severity: minor (observation)
- The server-side offer parser accepts any integer season; the #427 helper requires exactly 4 digits. For every id `make_pick_id` (`database.py:10850`) actually produces (seasons are 4-digit years) both agree, so there is no live divergence — noting it so the next person who changes one knows the other exists.

### O-2: PRD case-b literal 999.9 vs build 999.8
- Severity: minor (documentation)
- PRD R-5 row b lists "999.9 / 1213.1"; the actual pre- and post-fix value is 999.8 (PRD rounded each piece before summing). The build pinned 999.8 and the Phase-2 reconciliation accepted the deviation. PRD row b should say 999.8 so the next reader does not chase a phantom 0.1.

## TestFlight checklist (operator-run — calculator, any league; backend-only so no new build is needed)

1. **Trade Calculator → Give:** add "2027 Mid 1st" twice (or two owned 2027 firsts). **Receive:** a player whose tier badge is **2 1sts** and who sits near the bottom of that band. Expect **Even**; open "Value adjustments" → the give side shows **no** "Package depth" row (the disclosure may be absent entirely if neither side has rows).
2. Same give side; swap the receive player for one mid-band in **2 1sts**. Expect the player side ahead ("favors receive"), and the give total to equal the two picks' face values added together (no depth deduction).
3. **Give:** two 2027 seconds. **Receive:** a player badged **2nd** worth about two seconds. Expect the player side ahead and a **"Package depth"** row with a negative amount on the give side (seconds still taxed).
4. **Give:** one 2027 Mid 1st + one WR of similar value (~a mid first). **Receive:** a single player worth the two summed (tier **2 1sts**, low in band). Expect **fair, not even** (ratio ≈ 0.91), with a single "Package depth" deduction on the give side attributable to the WR only.
5. **Trades deck:** find (or generate with two firsts pinned) a card with two firsts on one side. Its value bar / favors label must match what the calculator says for the identical give/receive — same verdict, same side values.
6. **Settings → stud tax = Heavy**, repeat step 1. Expect the player side ahead (≈ 0.93, the heavy crown premium still applies to the single player) but the give total still equal to the two firsts' face values. Switch back to Market.
