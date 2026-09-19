# QA round 1 — agent A — 2026-09-08

## Summary: PASS (0 defects; 3 minor notes, none blocking)

## Environment
- Worktree: detached at build tip `9a605049` ("G-427 Phase 2 exit: ownership ruling, status"); diff under test `0c01bb00..9a605049` (18 files, +731/−63). Tree clean before and after every step (`git status --short` empty).
- Python 3.14 (`/Library/Frameworks/Python.framework/Versions/3.14`), pytest; Node v24.14.1 for `tsc`.
- Scratch SQLite only (`rm -f data/trade_finder.db*` before every run); `FTF_DP_PICK_VALUES_FILE` pinned by `backend/tests/conftest.py` to the checked-in snapshot; nothing pointed at prod.
- Config in the arithmetic probes: `ts._DEFAULT_CFG` (gamma_market 0.5, floor_market 0.7, floor_cross 0.4, cap 0.35, bench_trade_wide 1.0, `stud_tax_exempt_first_round` 1.0), `trade.crown_asset` on. No simulator, no Maestro (D-056).

## Results

| Test | Verdict | Evidence |
|---|---|---|
| Targeted set: `test_first_round_pick_exempt.py` + `test_stud_tax_modes.py` + `test_package_benchmark.py` + `test_crown_asset.py` + `test_fairness_gate_golden.py` + `test_bakeoff_arm_a_golden.py` + `test_engine_quality_golden.py` | PASS | `110 passed in 18.55s` |
| Full `pytest backend/tests -q` | PASS | **`5912 passed, 1 skipped in 1127.40s (0:18:47)`** — exact match to the build report's counts |
| RED-first (R-5): new test file against the 9 pre-fix modules at `0c01bb00` | PASS (RED proven) | `40 failed, 5 passed in 3.84s`; restored `9a605049` → `45 passed in 2.71s`. See "RED evidence" below |
| `cd mobile && npx tsc --noEmit` | PASS | exit 0, no output (no mobile/web code in the diff — guards not run, per task scope) |
| R-1 arithmetic, case a (two Mid 1sts vs `firsts_2` floor) | PASS | live modules via `_consensus_packages`: **4234.0 / 4220.7 = 0.997 → even**; hand formula `2·2117·(0.40+0.60·√(2117/4220.7)) = 3492.8` reproduces "today", knob 0 gives 3492.8 / 4220.7 = 0.828 favors receive |
| R-1 case b (two Mid 2nds vs 1213.1) | PASS | **999.8 / 1213.1 = 0.824** at knob 1 and knob 0 — unchanged, still taxed (PRD's "999.9" is per-piece rounding; engine rounds once) |
| R-1 case d ([1st, WR 2117] vs 4234) | PASS | **3862.0 / 4234.0 = 0.912**, verdict fair/favors receive; hand: 2117.0 face + 2117·(0.40+0.60·√0.5)=1745.0; taxable-subset cap floor 0.65·2117=1376 < 1745 → inert. Knob 0 → 3489.9 / 4234.0 = 0.824 |
| R-1 heavy (case a, mode `heavy`) | PASS | 4234.0 / 4577.0 = 0.925 — depth exemption applied, crown premium on the player side untouched |
| R-1 `off` mode | PASS | 4234.0 / 4220.7 — naive sum, unchanged path (`trade_service.py:1735-1736` returns before the resolve step) |
| R-4 knob 0 byte-identity | PASS | `package_value_v2([M1,M1], 4220.7, n_other=1, other_values=[4220.7])` with and without `exempt=[True,True]` at knob 0 → `(3492.8, 3492.8)` identical; the 18-way parametrised grid in the test file passes |
| R-2 mask guard (own run) | PASS | `dp_playerids_snapshot_2026-07-11.csv`: **3,564 rows, 9,840 sleeper/espn/mfl ids checked, 0 True, 0 ids contain `_`**. Shape probes: `generic_pick_1_{early,mid,late}`, `L_2027_1_3`, `123456_2027_1_12`, `my_lg_2027_1_9` → True; `generic_pick_2_mid`, `L_2027_2_3`, `L_2027_10_3`, `L_2027_1_`, `_2027_1_3`, `generic_pick_1_gold`, `"4046"`, `None`, `12` → False |
| R-3 every pricing site masked | PASS | AST scan of `backend/*.py` (non-test): **35 calls** to `package_value_v2` / `consolidated_value` / `_package_pair`, **0 without `exempt=`** (or without the two mask args for `_package_pair`) |
| R-3 adjustments row (`server._evaluate_adjustments`) | PASS | case a → `{'give': [], 'receive': []}`, naive `{4234.0, 4220.7}` (no `package_depth` row); case d → one give-side row `package_depth −372.0` |
| R-3 gen-v2 curve | PASS | `consolidated_value([M1,M1], exempt=[1,1])` = 4234.0; `test_m_*` covers the `[3000, M1]` non-best-first case |
| R-6 goldens not re-captured | PASS | `git diff --name-only 0c01bb00..9a605049` touches no fixture/golden data file — only `test_bakeoff_arm_a_golden.py` (`_PINNED_KNOBS` +1 key, `:605`) and `test_engine_quality_golden.py` (`_reset_cfg` pins 0, `:87-88`); `bakeoff_profiles.py:108` pins `MODEL_A_PROFILE` at 0.0 |
| "Zero deltas" claim on the 11 engine files | PASS (verified, not trusted) | Ran the 11 files at knob 1: `316 passed in 46.40s`; at knob 0 via a scratchpad pytest plugin that forces `_DEFAULT_CFG`, `_cfg` and the `_MODEL_CONFIG_DEFAULTS` row to 0.0: `316 passed in 36.65s`; per-test outcome lists diff → **NO DELTAS**. Plugin sanity: under it `test_a_…_is_even` fails with `(3492.8, 4220.7) == (4234.0, 4220.7)`, so the pin was live |
| R-7 clients hold no valuation math | PASS | `web/calculator.html:256-280` renders `d.give_value`/`d.receive_value` from `POST /api/trade/evaluate`; `mobile/src/components/TradeValueBar.tsx:14` "every input comes straight from POST /api/trade/evaluate"; `git grep` for `package_value|stud_tax|0.15 + 0.85|package_adj_gamma` in `web/`, `mobile/src/`, `extension/` finds only the `stud_tax_mode` echo string — no client math, so both clients change together with the server |
| Docs table | PASS | `docs/config-reference.md:794` row; `docs/glossary.md:116`; `docs/plans/three-model-bakeoff/scope-phase2.md:125`; api-reference/cross-client n/a (payload shape unchanged — verified `_trade_evaluate_impl` `server.py:12028-12045` still returns the same keys) |

## Code-walk proofs (file:line, build tip `9a605049`)

**(a) Mask helper.** `trade_service.py:2350-2366` `_is_first_round_pick_id`: non-str → False (`:2367-2368`); `parse_generic_pick_id` (`pick_values.py:216-226`, validated against `GENERIC_PICK_SEEDS`, so `generic_pick_1_gold` → None) → `parsed[0] == 1`; otherwise `pid.rsplit("_", 3)` must yield exactly 4 parts with non-empty league, 4-digit numeric season, round `"1"`, non-empty orig (`:2372-2374`). Owned ids come only from `database.make_pick_id` (`:10841-10850`, INV-8) whose `orig` is a roster/franchise id or slot number at every producer (`database.py:11104, 11141, 11364`; `server.py:13257`) — never underscored. Player ids are bare digit strings (0 of 9,840 snapshot ids contain `_`), so neither parse can match: no false positive path exists. `first_round_pick_mask` (`:2375-2381`) is a plain in-order comprehension over the ids.

**(b) `_package_value_market` (`:1780-1860`).** `naive = sum(values)` `:1825`; `own_max = max(values)` `:1828`; benchmark test `len(values) > 1 and v_max > own_max and bench_trade_wide > 0` `:1831-1834` — all over ALL values, unchanged. `exempt is None` branch `:1836-1839` is the pre-fix text verbatim. Exempt branch `:1840-1844`: `taxable`/`exempt_sum` split, curve over `taxable` only, `total = exempt_sum + max(contrib, sum(taxable)·(1−cap))` — cap on the taxable subset. Crown credit `:1846-1858` sums `v for v in values if v >= elite_ref` — all values, unchanged. Heavy (`:1745-1776`): `exempt is None` → original one-liner `:1746`; else face + curve over taxable `:1750-1753`; premium block `:1755-1776` reads `sum(values)`, `max(values)` — untouched. Resolve step `:1729-1734` in `package_value_v2` collapses `exempt` to `None` unless `any(exempt) and _c(knob) > 0`, so `off` (`:1727-1728`, returns before the resolve), all-False masks and knob ≤ 0 are the pre-fix path bit for bit. `consolidated_value` (`trade_gen_v2.py:150-183`) applies the same rule with `v_best = max(values)` over all values (`:169`) and its own knob read (`:175-176`).

**(c) Mask/value alignment — every site builds values and mask from the same id list with no sort/filter between them:** `trade_optimizer.py:115-122` (`_consensus_packages`), `:139-146` (`_fairness_v3`), `:529-546` (`_surpluses`: `g_exempt`/`r_exempt` built once, reused for the opp-board pair — same ids, same order); `trade_service.py:2019-2029` (`rank_fairness` — `signal_core` returns a **list** `:1993-1997`, so `gvals` and the mask iterate the same list), `:2276-2283` (`price_consensus_package` — feeds `eval_consensus_package :2317`, fair-packages `:5674/:5681`, overhaul `:6126`, `trade_gen_owner.py:259`, `win_now_optimizer.py:214-216`), `:2545-2552` (`overpay_ok`), `:6712-6725` (aggression tilt — `c.give_player_ids`/`c.receive_player_ids` for both), `:7032-7040` (`_fairness`), `:7086-7118` (`_pair_surpluses`, MARGINAL and plain branches both iterate `give_ids`/`recv_ids`), `:7586-7594` (`_gap_gates_ok`), `:7623-7631` (`_emit`); `trade_gen_fit.py:684-692`; `trade_breaker.py:563-574` (`view.recv_ids`/`view.give_ids`); `trade_policy.py:715-725` (`_board_valuation` builds both masks from `give_ids`/`receive_ids`, passes them to both the eff and raw `_package_pair` calls; `_package_pair :291-297` forwards `list(mask) if mask else None`); `trade_gen_v2.py:186-189` `_cval_side` is the only gen-v2 caller of `consolidated_value` and builds mask and values from the same `ids`; `server.py:1013-1027` `_evaluate_adjustments` — `base` and `full` both carry the mask so `depth = base − naive = 0` for a side of firsts and the row is omitted (`:1031`).

**(d) Knob.** `_DEFAULT_CFG["stud_tax_exempt_first_round"] = 1.0` `trade_service.py:127`; seed row `database.py:2820`. `_migrate_db` (`:3104`, called from `init_db :4043`) seeds every `_MODEL_CONFIG_DEFAULTS` row with `INSERT OR IGNORE` (SQLite) / `ON CONFLICT (key) DO NOTHING` (Postgres) at `:3585-3595` — an existing DB gets the row on next boot; until then `_c()` (`:1357-1363`) falls back to `_DEFAULT_CFG`, and `reload_config :1322` only `update()`s over the defaults, so a DB without the row still evaluates at 1.0. `≤ 0` short-circuit `:1732-1734`. Both goldens pin 0 and no golden data file changed.

**(e) Clients.** See R-7 row — server-side evaluate is the only source of `give_value`/`receive_value`/`adjustments` for web, mobile and the deck (`server.py:12028-12045`; Mode B `:12124-12125` also goes through `_consensus_packages`).

## Hunt results (task 5)
- **Fairness-gate let-through:** exemption only *raises* the value of a side that holds a first (X counted at face; cap floor moves from `0.65·(X+ΣT)` to `X+0.65·ΣT`, never lower). A previously blocked package passes only when the firsts side was the *lower* side — the intended fix. Fillers next to a first are still curve-priced against the same benchmark; no path gives a non-first face value. Measured: 316/316 outcomes identical between knob 1 and knob 0 across the 11 engine files (list above) — no fixture flips.
- **Sort/filter misalignment:** none found — see (c). `_pair_surpluses`/`_surpluses` reuse one mask for both boards, which is correct because the id order is the same for both value spaces.
- **`lru_cache`:** `maxsize=65536` (`:2349`), so bounded, not unbounded. Keys are id strings; a non-hashable id would raise `TypeError`, but every producer yields `str` (or `int`/`None`, which are hashable and return False).
- **Seed migration:** covered in (d) — idempotent, both engines.
- **`_pick_gap_equivalent`:** not in the diff (0 hits), per R-7.

## RED evidence (pre-fix modules from `0c01bb00`, new test file from `9a605049`)
```
40 failed, 5 passed in 3.84s
E  assert (3492.8, 4220.7) == (4234.0, 4220.7)     test_a / test_i (report case)
E  assert (3489.9, 4234.0) == (3862.0, 4234.0)     test_d
E  assert (3787.4, 4496.0) == (4496.0, 4496.0)     test_e
E  assert (2381.0, 2723.5) == (2531.3, 2723.5)     test_f
E  assert (4234.0, 3489.9) == (4234.0, 4234.0)     test_h
E  assert (1913.5, 4577.0) == (4234.0, 4577.0)     test_n (heavy)
E  AssertionError: assert ['package_depth'] == []   test_l
E  assert (1 == 1 and -744.1 == -372.0)             test_l mixed
E  assert 4740.5 == 6351.0                          test_crown_credit_still_paid_on_elite_other_side
E  KeyError: 'stud_tax_exempt_first_round'          test_knob_default_is_on
E  TypeError: package_value_v2() got an unexpected keyword argument 'exempt'   (×22)
E  TypeError: consolidated_value() got an unexpected keyword argument 'exempt' (×2)
E  AssertionError: trade_service.first_round_pick_mask is missing              (×2)
```
Passing pre-fix (correctly "unchanged" cases): `test_b`, `test_c`, `test_g`, `test_off_mode_unchanged`, `test_j_knob_off_restores_todays_numbers`. After `git checkout 9a605049 -- <9 files>`: `45 passed`. Full RED log: scratchpad `red-run-A.txt`.

## Findings
No defects. Minor notes for the orchestrator (no action required to ship):

### N-1: build report RED count is off by one
- Severity: minor (documentation)
- Report says "41 failed, 4 passed … the 4 are c, g, `off`, and the elite crown read". Observed: **40 failed, 5 passed**; `test_crown_credit_still_paid_on_elite_other_side` is RED pre-fix (`4740.5 == 6351.0`) and `test_j_knob_off_restores_todays_numbers` passes on both builds (it sets the knob itself and expects today's numbers). The test set is still sound — every behavioural case fails on the defect it names.

### N-2: `_is_first_round_pick_id` does not reuse `server._parse_owned_pick_id`
- Severity: minor (observation, no behaviour gap)
- `server.py:3309-3324` already parses owned pick ids (league-prefix aware, `len(parts) >= 3`). The new helper is league-agnostic by necessity (pricing sites have no `league_id`) and stricter (exactly 4 `rsplit` parts, 4-digit season). For every real id shape the two agree; an `orig` containing `_` would be a false *negative* (a first taxed, i.e. today's behaviour), never a false positive. No producer emits one.

### N-3: PRD Q-a / Q-b remain open by design
- Two Mid 1sts read even only near the `firsts_2` floor (band 4,220.7–6,171.9); three firsts vs a ≥6,000 stud still reads 0.926 because the crown credit is untouched (reconciliation ruling b). Both are operator questions in the PRD, not defects.

## TestFlight checklist (operator-run; backend-only change, no EAS build needed — any TestFlight build against the live server)
1. Trade Calculator (consensus mode) → give: **"2027 Mid 1st" twice** (or two owned 2027 firsts) → receive: a player whose tier badge is **2 1sts** sitting near the *bottom* of that band → expect verdict **Even**, give total = the two picks' face values summed, and **no "Package depth" row** under the give side in the adjustments disclosure.
2. Same give → receive a player **mid-band** in **2 1sts** → expect the player side ahead ("favors receive"), but the give side's number still equals the two picks' face values summed (no depth deduction).
3. Give: **"2027 Mid 2nd" twice** → receive: a player badged **2nd** worth about two seconds → expect the player side ahead (ratio ≈ 0.82) with a **"Package depth" row on the picks' side** — seconds still taxed.
4. Give: **one 2027 Mid 1st + one WR of similar value (≈ a Mid 1st)** → receive: a single player worth roughly their sum → expect **fair, not even** (ratio ≈ 0.91), with a give-side "Package depth" row whose amount equals the WR's deduction only (≈ −372 at the PRD values).
5. Trades home → open a generated deck card that has **two firsts on one side** → tap through to the calculator with the same package → expect the card's verdict/values and the calculator's verdict/values to **match** (both are stamped by the same masked path).
6. Rollback drill (optional, ops): `POST /api/admin/config` `stud_tax_exempt_first_round = 0` → repeat step 1 → expect the pre-fix verdict (player side ahead, depth row back on the picks); set back to 1 → step 1 reads Even again without a deploy.
