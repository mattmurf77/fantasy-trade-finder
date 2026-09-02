# Results — gap-sweetener relative band + best-effort fallback (`sweetener_gap_frac`, `sweetener_best_effort`)

**Date:** 2026-09-02 · **Branch:** `claude/sweetener-relative-band` · **Scope:** [scope.md](scope.md) · **Proof:** [code-walk.md](code-walk.md) · **Harness:** [measure_sweetener.py](measure_sweetener.py) → `results-raw-f075.json` (prod, fairness pref ON), `results-raw-f050.json` (pref OFF)

Every number here comes from a run on this branch tip with `PYTHONHASHSEED=0`, the clock frozen (G-065), prod `model_config` pinned as read 2026-09-01/02 (D-159 bundle, `asset_floor_abs` 450, `max_overpay_frac` 0.25, `sweetener_gap_threshold` 1539, `consensus_fit_weight` 0.5 — D-172, live) and `max_per_opponent=5`. **Every baseline was run twice and was byte-identical in all 140 cells of both sweeps** (`baseline_identical: true` in every raw row). Numbers are frozen-clock (no-time-pressure) decks.

## TL;DR

* **Both knobs at 0 are byte-identical to `origin/main` @ `e16bb487`** — proven by two captured goldens (`close_value_gap` on nine fixtures; full v3 decks on the engine-quality fixture and the gap-sweetener v3 fixture, `gap_sweetener` dicts included), the branch capture `cmp`-identical to the main capture, the existing arm-A / engine-quality / consensus-fit / gap-sweetener goldens all green un-recaptured, and the full suite (§ Suite).
* **The defect reproduces exactly.** The #414 card (London 5,932.8 / CeeDee packaged 7,328.8, gap 1,396.0, fairness 0.81) returns `None` from `close_value_gap` at today's knobs — the trigger is 1,539 and 1,396 < 1,539. At the live triple it triggers at 879.5 and is closed: a best-effort **partial** with a 1,200 piece (→ 1,058.9) on the unit bench, a **full** close with a ≥ 1,500 piece, and — in the planted 12-team league — a full-closed 2x1 (equalizer 1,687.7 → gap 586, fairness 0.921) that at V0 did not even survive the deck cut.
* **QA's regression reproduces and is closed.** V1 (750 alone) lifts the `>1539` share from 0 → **3.5%** on `12t_1qb@u0` (B, v3) and doubles arm C's on `16t_sf` (10.5 → 20%): a card whose partial close no longer counts ships at its ORIGINAL gap. V2/V3 (best-effort on) put it back to **0** in every live-arm cell and the previously-unclosable card ships as a stamped partial.
* **The band matters at the top, not the bottom.** V4 (frac 0.15) re-opens the window — `>1539` back to 3.5% on `12t_1qb@u0` for both B and D — because 0.15 × a 10,000+ package sits above 1,539 again. 0.12 keeps the trigger under 1,539 for every H < 12,825, i.e. every card in the corpus.
* **Sweetened share rises, junk does not:** B v3 cells go 6.9 / 0.0 / 4.8% → **10.3 / 11.1 / 19.1%** (partials 1 / 0 / 1); sub-450 body share moves **0 / +3.5 / 0 pp** (the +3.5 is two extra multi-asset cards on `16t_sf`, both sweetened, both above the #141 floors); **top-5 Jaccard is 1.0 in every B cell**, set Jaccard 0.87 / 0.84 / 0.68. **Arm A is unmoved in every cell.**
* **Deck size is not invariant** under this change (unlike D-172): `16t_sf` B v3 grows 34 → 36 from V1 on — a sweetened card's new key no longer collides with a sibling and its higher fairness survives the deck cut. `12t_1qb@u0`/`@u8` are unchanged.
* **Most closes at the triple are full, not partial, on the fixtures** (partials 1 of 3, 0 of 4, 1 of 4) — the harness rosters hold 1,500–2,400 pieces (picks included: 1 of the 3 sweeteners on `12t_1qb@u0` is a pick). The #414 unit card is a partial only because its bench tops out at 1,200; § Package math explains why a 900 piece nets −107 of packaged gap.
* **Recommended live triple: `sweetener_gap_threshold` 750 · `sweetener_gap_frac` 0.12 · `sweetener_best_effort` 1** — V3 — PUT in the order best-effort → frac → threshold (§ Recommendation).

## Suite

| Run | Command | Result |
|---|---|---|
| clean `origin/main` @ `e16bb487` (`git archive` tree) | `PYTHONHASHSEED=0 python3 -m pytest backend/tests -q -p no:cacheprovider` | **4519 passed, 1 skipped** in 311.5 s |
| branch tip, before the rebase (HEAD `02d2eac2` + this change) | same, `__pycache__` cleared first | **4531 passed, 1 skipped** in 466.9 s (three harness runs sharing the CPU); node-id diff vs the main tree: exactly the 22 new tests added, the 10 `test_prod_blocked_static.py` tests (landed on main after the fork) absent |
| branch tip, rebased onto `e16bb487` | same | **4541 passed, 1 skipped** in 352.6 s — the clean-main 4519 + exactly the 22 new tests |
| new module alone | `… backend/tests/test_sweetener_relative_band.py` | **21 passed** (two fuzz cases drive 200 helper calls + 32 generated decks) |
| touched siblings | `test_bakeoff_arm_a_golden.py` (+1 pin test) · `test_gap_sweetener.py` (two unpack lines) · `test_engine_quality_golden.py` · `test_consensus_fit_sort_key.py` | all green, goldens un-recaptured |
| golden capture, main tree | `git archive origin/main \| tar -x -C <scratch>/main_tree; cp <test> …; cd main_tree && PYTHONHASHSEED=0 python3 -m backend.tests.test_sweetener_relative_band` | 10 helper rows + 31 v3 rows; `cmp` against the same capture on the branch: **byte-identical** |

## Sabotages (red → green, byte-copy restore, `cmp`, `__pycache__` cleared — G-060)

Script: a scratch `sabotage.sh` that backs up the file, applies each edit with a `python3` string replace asserting exactly one match, clears `backend/**/__pycache__`, runs the named test(s) with `PYTHONHASHSEED=0 python3 -m pytest … -k …`, restores with `cp`, clears again, re-runs, and `cmp`s the restore against the backup.

| # | Sabotage | Target test(s) | Sabotaged | Restored |
|---|---|---|---|---|
| S1 | `thr_eff = max(gap_threshold, frac × max(gv, rv))` → `gap_threshold` (the band never lifts the trigger) | `test_414_full_close_when_the_bench_holds_a_closer` + `test_frac_raises_the_trigger_above_the_floor` | **2 failed** | 2 passed |
| S2 | best-effort keeps the LARGEST post-add gap (`n_gap >= best[0]` → `<=`) | `test_qa_regression_best_effort_attaches_the_tightest` | **1 failed** (1,200 → 1,708.3 chosen over 1,480 → 1,534.5) | 1 passed |
| S3 | drop the richer-side flip guard (`or (n_rv > n_gv) != user_richer` removed) | `test_best_effort_never_flips_the_richer_side` + `test_property_fuzz_helper_with_the_live_gate_stack` | **1 failed**, 1 passed — the deterministic flip fixture catches it (the 3,200 piece wins at \|gap\| 1,063.6); the seeded random fuzz happened to draw no flip case, which is why the deterministic test exists | 2 passed |
| S4 | remove the `sweetener_gap_frac` pin from `MODEL_A_PROFILE` | `test_bakeoff_arm_a_golden.py::test_sweetener_band_pins_are_load_bearing` | **1 failed** | 1 passed |
| S4b | remove the `sweetener_best_effort` pin | same | **1 failed** | 1 passed |
| S5 | hoist the read: `_c("sweetener_gap_frac")` → `_ts._DEFAULT_CFG["sweetener_gap_frac"]` (import-time binding, blind to `_cfg` and the overlay) | `test_knobs_are_read_at_call_time_through_the_overlay` + `test_frac_raises_the_trigger_above_the_floor` | **2 failed** | 2 passed |

Every restore `cmp`'d byte-identical to the backup.

## Variants

| Variant | `sweetener_gap_threshold` | `sweetener_gap_frac` | `sweetener_best_effort` | What it is |
|---|---|---|---|---|
| V0_prod | 1539 | 0 | 0 | the live engine, 2026-09-02 |
| V1_thr750 | 750 | 0 | 0 | the threshold cut alone — QA's known-regressing cell |
| V2_thr750_be | 750 | 0 | 1 | cut + best-effort |
| V3_thr750_f12_be | 750 | 0.12 | 1 | **the proposed live bundle** |
| V4_thr750_f15_be | 750 | 0.15 | 1 | the wider band |

## Harness tables — prod, fairness pref ON (`fairness_threshold = 0.75`), v3 path

Columns: `cards` = whole deck; `sweet` = cards carrying `gap_sweetener` (full / partial); `>1539` = share of cards with \|give − receive\| over the late-1st line; `p10/p50/p90` = gap percentiles; `sub-450` = share of cards with any traded asset priced under `asset_floor_abs`; `pf` = partner-favourable share (receive ≤ give); `top-5 J` / `set J` = Jaccard vs the same cell's V0 deck (deck order); `pick/pl` = sweeteners that are PICK pseudo-assets vs players.

**12t_1qb@u0** — viewer team 0 (`position_needs = ["RB"]`), the 2026-08-21 harness viewpoint

| arm | variant | cards | sweet | share | >1539 | p10 | p50 | p90 | sub-450 | pf | top-5 J | set J | pick/pl |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B_current | V0 | 29 | 2 (2/0) | 0.069 | 0.000 | 4.5 | 49 | 1170 | 0.345 | 0.207 | 1.0 | 1.0 | 0/2 |
| B_current | V1 | 29 | 2 (2/0) | 0.069 | **0.035** | 4.5 | 49 | 680 | 0.345 | 0.207 | 1.0 | 0.812 | 1/1 |
| B_current | V2 | 29 | 3 (2/1) | 0.103 | 0.000 | 4.5 | 49 | 680 | 0.345 | 0.207 | 1.0 | 0.812 | 1/2 |
| B_current | **V3** | 29 | 3 (2/1) | **0.103** | **0.000** | 4.5 | 49 | 680 | 0.345 | 0.207 | **1.0** | **0.871** | 1/2 |
| B_current | V4 | 29 | 2 (1/1) | 0.069 | **0.035** | 4.5 | 49 | 680 | 0.345 | 0.207 | 1.0 | 0.812 | 1/1 |
| A_baseline | V0–V4 | 55 | 0 | 0.000 | 0.054 | 7.5 | 94 | 1158 | 0.200 | 0.236 | 1.0 | 1.0 | 0/0 |
| D_challenger | V0 | 29 | 2 (2/0) | 0.069 | 0.000 | 5.3 | 102 | 1156 | 0.241 | 0.310 | 1.0 | 1.0 | 0/2 |
| D_challenger | V1 / V2 | 29 | 4 (4/0) | 0.138 | 0.000 | 5.3 | 101 | 680 | 0.241 | 0.310 | 1.0 | 0.706 | 0/4 |
| D_challenger | **V3** | 29 | 4 (4/0) | 0.138 | 0.000 | 5.3 | 101 | 680 | 0.241 | 0.310 | 1.0 | 0.758 | 0/4 |
| D_challenger | V4 | 29 | 3 (3/0) | 0.103 | **0.035** | 5.3 | 101 | 680 | 0.241 | 0.310 | 1.0 | 0.706 | 0/3 |
| C_gen_v2 | V0 | 22 | 2 (2/0) | 0.091 | 0.045 | 24 | 263 | 998 | 0.091 | 0.500 | 1.0 | 1.0 | 0/2 |
| C_gen_v2 | V1 / V2 | 22 | 3 (3/0) | 0.136 | 0.045 | 24 | 172 | 740 | 0.091 | 0.545 | 0.667 | 0.760 | 1/2 |
| C_gen_v2 | **V3** | 22 | 3 (3/0) | 0.136 | 0.045 | 24 | 263 | 998 | 0.091 | 0.500 | 1.0 | 0.913 | 0/3 |
| C_gen_v2 | V4 | 22 | 3 (3/0) | 0.136 | **0.091** | 24 | 263 | 1514 | 0.091 | 0.500 | 0.667 | 0.833 | 1/2 |

**16t_sf@u0** — viewer team 0, superflex TEP

| arm | variant | cards | sweet | share | >1539 | p10 | p50 | p90 | sub-450 | pf | top-5 J | set J | pick/pl |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B_current | V0 | 34 | 0 | 0.000 | 0.000 | 6.1 | 72 | 489 | 0.382 | 0.382 | 1.0 | 1.0 | 0/0 |
| B_current | V1 / V2 / **V3** | **36** | 4 (4/0) | **0.111** | 0.000 | 6.1 | 82 | 557 | 0.417 | 0.389 | **1.0** | **0.842** | 0/4 |
| B_current | V4 | 36 | 4 (4/0) | 0.111 | 0.000 | 6.1 | 82 | 598 | 0.417 | 0.361 | 1.0 | 0.842 | 1/3 |
| A_baseline | V0–V4 | 73 | 0 | 0.000 | 0.069 | 14 | 200 | 1445 | 0.164 | 0.247 | 1.0 | 1.0 | 0/0 |
| D_challenger | V0 | 27 | 0 | 0.000 | 0.000 | 8.6 | 108 | 356 | 0.185 | 0.556 | 1.0 | 1.0 | 0/0 |
| D_challenger | V1 / V2 / **V3** | 29 | 3 (3/0) | 0.103 | 0.000 | 8.6 | 140 | 557 | 0.241 | 0.517 | 1.0 | 0.867 | 0/3 |
| D_challenger | V4 | 29 | 2 (2/0) | 0.069 | 0.000 | 8.6 | 140 | 557 | 0.241 | 0.517 | 1.0 | 0.931 | 0/2 |
| C_gen_v2 | V0 | 19 | 1 (1/0) | 0.053 | 0.105 | 47 | 489 | 1714 | 0.105 | 0.632 | 1.0 | 1.0 | 0/1 |
| C_gen_v2 | V1 | 20 | 2 (2/0) | 0.100 | **0.200** | 55 | 489 | **2308** | 0.200 | 0.650 | 1.0 | 0.696 | 0/2 |
| C_gen_v2 | V2 | 20 | 6 (3/3) | 0.300 | 0.100 | 55 | 478 | 1714 | 0.200 | 0.600 | 0.667 | 0.625 | 3/3 |
| C_gen_v2 | **V3** | 20 | 5 (3/2) | 0.250 | 0.100 | 55 | 489 | 1714 | 0.200 | 0.650 | 0.667 | 0.696 | 2/3 |
| C_gen_v2 | V4 | 20 | 5 (4/1) | 0.250 | 0.100 | 55 | 489 | 1714 | 0.200 | 0.650 | 0.667 | 0.696 | 2/3 |

**12t_1qb@u8** — viewer team 8, `position_needs = []` (the no-need viewer, half the league)

| arm | variant | cards | sweet | share | >1539 | p10 | p50 | p90 | sub-450 | pf | top-5 J | set J | pick/pl |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B_current | V0 | 21 | 1 (1/0) | 0.048 | 0.000 | 47 | 268 | 645 | 0.143 | 0.238 | 1.0 | 1.0 | 1/0 |
| B_current | V1 | 21 | 3 (3/0) | 0.143 | 0.000 | 47 | 211 | 642 | 0.143 | 0.286 | 1.0 | 0.680 | 0/3 |
| B_current | V2 / **V3** / V4 | 21 | 4 (3/1) | **0.191** | 0.000 | 47 | 211 | 642 | 0.143 | 0.286 | **1.0** | 0.680 | 0/4 |
| A_baseline | V0–V4 | 55 | 0 | 0.000 | 0.018 | 53 | 525 | 1248 | 0.073 | 0.255 | 1.0 | 1.0 | 0/0 |
| D_challenger | V0 | 17 | 1 (1/0) | 0.059 | 0.000 | 41 | 268 | 1109 | 0.176 | 0.353 | 1.0 | 1.0 | 1/0 |
| D_challenger | V1 | 17 | 3 (3/0) | 0.176 | 0.000 | 41 | 211 | 645 | 0.176 | 0.412 | 1.0 | 0.619 | 0/3 |
| D_challenger | V2 / **V3** / V4 | 17 | 4 (3/1) | 0.235 | 0.000 | 41 | 211 | 645 | 0.176 | 0.412 | 1.0 | 0.619 | 0/4 |
| C_gen_v2 | V0 | 15 | 0 | 0.000 | 0.133 | 13 | 427 | 1844 | 0.200 | 0.467 | 1.0 | 1.0 | 0/0 |
| C_gen_v2 | V1 / V2 / **V3** | 15 | 1 (1/0) | 0.067 | 0.133 | 13 | 427 | 1844 | 0.200 | 0.533 | 0.667 | 0.875 | 0/1 |
| C_gen_v2 | V4 | 15 | 1 (1/0) | 0.067 | 0.133 | 13 | 427 | 1844 | 0.200 | 0.467 | 1.0 | 1.0 | 0/1 |

**414_1x1@u4** — the 12-team 1QB fixture viewed from team 4, London (5,932.8) planted as the viewer's best WR and CeeDee (seed 6,965.6 → packaged 7,328.8) as unboarded team 2's best WR. `414 card` = the London → CeeDee card's status in the served deck.

| arm | variant | cards | sweet | share | >1539 | p10 | p50 | p90 | sub-450 | pf | top-5 J | set J | pick/pl | 414 card |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B_current | V0 | 24 | 1 (1/0) | 0.042 | 0.000 | 33 | 139 | 814 | 0.042 | 0.375 | 1.0 | 1.0 | 0/1 | **absent** — the 0.81 1x1 loses the deck cut |
| B_current | V1 / V2 / **V3** | 25 | 4 (4/0) | **0.160** | 0.000 | 33 | 139 | 627 | 0.040 | 0.360 | **1.0** | 0.690 | 1/3 | **full close, 2x1**: equalizer 1,687.7 → gap 586.2, fairness 0.921, consensus |
| B_current | V4 | 25 | 3 (3/0) | 0.120 | 0.000 | 33 | 139 | 680 | 0.040 | 0.400 | 1.0 | 0.750 | 0/3 | full close, 2x1: equalizer 1,385.3 → gap 883.4, fairness 0.882 (the wider band accepts a smaller piece) |
| A_baseline | V0–V4 | 55 | 0 | 0.000 | 0.018 | 8.6 | 189 | 909 | 0.036 | 0.382 | 1.0 | 1.0 | 0/0 | **plain 1x1, gap 1,396.0, fairness 0.81** — the pre-wave engine serves the operator's card exactly as he saw it |
| D_challenger | V0 | 21 | 1 (1/0) | 0.048 | 0.000 | 33 | 115 | 1005 | 0.048 | 0.429 | 1.0 | 1.0 | 0/1 | absent |
| D_challenger | V1 / V2 / **V3** | 22 | 4 (4/0) | 0.182 | 0.000 | 33 | 115 | 598 | 0.045 | 0.455 | 1.0 | 0.654 | 1/3 | absent (arm D's both-ways consensus fills team 2's slots with other cards) |
| D_challenger | V4 | 22 | 3 (3/0) | 0.136 | 0.000 | 33 | 115 | 598 | 0.045 | 0.500 | 1.0 | 0.720 | 0/3 | absent |
| C_gen_v2 | V0 | 13 | 1 (1/0) | 0.077 | 0.000 | 55 | 767 | 1234 | 0.154 | 0.385 | 1.0 | 1.0 | 0/1 | absent (arm C needs both boards) |
| C_gen_v2 | V1 | 14 | 4 (4/0) | 0.286 | **0.143** | 55 | 502 | **1998** | 0.214 | 0.357 | 0.25 | 0.227 | 1/3 | absent |
| C_gen_v2 | V2 | 14 | 5 (4/1) | 0.357 | 0.071 | 55 | 502 | 1177 | 0.214 | 0.357 | 0.25 | 0.227 | 1/4 | absent |
| C_gen_v2 | **V3** | 14 | 4 (3/1) | 0.286 | **0.000** | 55 | 502 | 968 | 0.214 | 0.357 | 0.429 | 0.286 | 0/4 | absent |
| C_gen_v2 | V4 | 14 | 4 (4/0) | 0.286 | 0.000 | 55 | 524 | 1128 | 0.214 | 0.286 | 0.667 | 0.350 | 0/4 | absent |

Reading: on the live engine the operator's card does not survive the deck cut *unsweetened* (V0: absent — a 0.81 1x1 ranks below the body-for-body swaps; arm A, with its 55-card pre-wave deck, serves it plain at exactly the numbers in the feedback). From V1 on it is served as a **fully closed 2x1** — the fixture roster holds a 1,687.7 piece — so the sweetener changes not only the card's shape but whether it is shown at all. Arm C on this league is the one cell where V1 is dramatic (`>1539` 0 → 14.3%, p90 1,998) and V3 is the only variant that returns it to 0. Viewer 0 (`position_needs = ["RB"]`) filters WRs out of the consensus receive pool, and the no-need viewers u1/u6/u8 never serve the card at any variant — measured on the way to this fixture and stated so the lead does not read "absent" as a sweetener effect.

## Harness tables — v2 path (`trade_engine.v3` off), fairness 0.75, live arms

The heap-based v2 pair generator emits low-gap decks (B p90 147–505), so the sweetener rarely bites:

| league | arm | V0 | V1 / V2 | **V3** | V4 |
|---|---|---|---|---|---|
| 12t_1qb@u0 | B / D | 24 / 23 cards, 0 sweetened, `>1539` 0 | unchanged | unchanged | unchanged |
| 16t_sf@u0 | B | 31 cards, 0 sweetened | 33 cards, 3 (3/0), set J 0.882, sub-450 0.323 → 0.364 | same as V1 | 33, 2 (2/0), set J 0.939 |
| 16t_sf@u0 | D | 25, 0 | 27, 3 (3/0), set J 0.857 | same | 27, 2 (2/0) |
| 12t_1qb@u8 | B | 16, 0 | 16, 2 (2/0), set J 0.778 | **16, 0 — the band lifts the trigger above both cards' gaps** (they sit under 12% of their richer side and are left alone) | same as V3 |
| 12t_1qb@u8 | D | 11, 0 | 11, 2 (2/0) | 11, 0 | same |

`>1539` is 0 in every live-arm v2 cell at every variant. Arm A: unchanged in every cell.

## Harness tables — prod, fairness pref OFF (`fairness_threshold = 0.50`), v3 path, V0 vs V3

Same shape as 0.75 in every cell — the sweetener runs after the fairness bar, so the bar the client sends moves which cards exist, not what the closer does to them. Every baseline byte-identical (140/140 cells); `>1539` is 0 at V3 in every live-arm cell except arm C's pre-existing 16t (10.5 → 10.0%) and u8 (13.3%, unchanged — no equalizer passes arm C's band there).

| league | arm | V0: cards / sweet / >1539 / sub-450 / pf | **V3**: cards / sweet / >1539 / sub-450 / pf / top-5 J / set J |
|---|---|---|---|
| 12t_1qb@u0 | B | 29 / 2 (2/0) / 0 / 0.276 / 0.207 | 29 / 3 (2/1) / 0 / 0.276 / 0.207 / 1.0 / 0.871 |
| 12t_1qb@u0 | D | 29 / 2 (2/0) / 0 / 0.241 / 0.310 | 29 / 4 (4/0) / 0 / 0.241 / 0.310 / 1.0 / 0.758 |
| 12t_1qb@u0 | C | 22 / 2 (2/0) / 0.045 / 0.091 / 0.500 | 22 / 3 (3/0) / 0.045 / 0.091 / 0.500 / 1.0 / 0.913 |
| 16t_sf@u0 | B | 33 / 0 / 0 / 0.333 / 0.364 | 34 / 4 (4/0) / 0 / 0.353 / 0.382 / 1.0 / 0.811 |
| 16t_sf@u0 | D | 27 / 0 / 0 / 0.185 / 0.556 | 29 / 3 (3/0) / 0 / 0.241 / 0.517 / 1.0 / 0.867 |
| 16t_sf@u0 | C | 19 / 1 (1/0) / 0.105 / 0.105 / 0.632 | 20 / 5 (3/2) / 0.100 / 0.200 / 0.650 / 0.667 / 0.696 |
| 12t_1qb@u8 | B | 21 / 1 (1/0) / 0 / 0.143 / 0.238 | 21 / 4 (3/1) / 0 / 0.143 / 0.286 / 1.0 / 0.680 |
| 12t_1qb@u8 | D | 17 / 1 (1/0) / 0 / 0.176 / 0.353 | 17 / 4 (3/1) / 0 / 0.176 / 0.412 / 1.0 / 0.619 |
| 12t_1qb@u8 | C | 15 / 0 / 0.133 / 0.200 / 0.467 | 15 / 1 (1/0) / 0.133 / 0.200 / 0.533 / 0.667 / 0.875 |
| 414_1x1@u4 | B | 24 / 1 (1/0) / 0 / 0.042 / 0.375 · card absent | 25 / 4 (4/0) / 0 / 0.040 / 0.360 / 1.0 / 0.690 · **card: full 2x1, eq 1,687.7 → 586.2** |
| 414_1x1@u4 | D | 21 / 1 (1/0) / 0 / 0.048 / 0.429 | 22 / 4 (4/0) / 0 / 0.045 / 0.455 / 1.0 / 0.654 |
| 414_1x1@u4 | C | 13 / 1 (1/0) / 0 / 0.154 / 0.385 | 14 / 4 (3/1) / 0 / 0.214 / 0.357 / 0.429 / 0.286 |

Arm A: identical in every cell at every variant. Full rows, V1/V2/V4 and the v2-only path are in `results-raw-f050.json`.

## Package math — why a 900 equalizer barely moves the bar (finding for the lead)

The brief expected the 900 piece to close the #414 gap to ≤ 879 — the naive-sum picture. `close_value_gap` measures the gap with `_consensus_packages` = `package_value_v2` in 'market' mode, and under the live knobs (`package_bench_trade_wide` 1.0, `package_floor_cross` 0.4, `package_adj_gamma_market` 0.5, `trade.crown_asset` ON) three things happen to a 1x1 that gains a second piece (code-walk § 8):

| bench piece | London's packaged value | give package | receive package | gap | Δ vs 1,396 | filler (0.15) |
|---|---|---|---|---|---|---|
| — (the served 1x1) | 5,932.8 | 5,932.8 | 7,328.8 | 1,396.0 | — | — |
| 450 | 5,658 | 5,906.9 | 7,421.1 | 1,514.2 | **+118** | fails |
| 600 | 5,658 | 6,004.0 | 7,449.0 | 1,445.0 | +49 | fails |
| 900 | 5,658 | 6,212.4 | 7,501.2 | 1,288.8 | −107 | passes |
| 1,200 | 5,658 | 6,437.2 | 7,496.1 | 1,058.9 | −337 | passes |
| 1,500 | 5,658 | 6,676.0 | 7,448.1 | 772.1 | −624 | passes — first full close under 879.5 |
| 2,200 | 5,658 | 7,280.2 | 7,336.1 | 55.9 | −1,340 | passes |
| 3,200 | 5,658 | 8,239.7 | 7,176.1 | 1,063.6 (flipped) | — | passes, R1 passes (0.237) — refused by the flip guard |

The headliner loses 275 the moment it has a partner (trade-wide benchmark at floor 0.4), the added piece is depth-discounted against CeeDee, and CeeDee's crown credit grows as the skew narrows. So "add a player to make it more fair" moves the bar by roughly a third of the player's face value until the piece is large. This is the 2026-08-21 benchmark fix's shape, not this change's — but it is why most #414-shaped closes on a thin bench will be partials, and why the cheap pieces are refused twice (filler AND strict reduction).

## Recommendation — live triple **750 / 0.12 / 1**

Evidence line: *V3 is the only variant where the `>1539` share is 0 in every live-arm v3 cell (V1 re-opens it to 3.5% on `12t_1qb@u0` and doubles arm C's 16t share to 20%; V4 re-opens 3.5% on `12t_1qb@u0` for B and D); sweetened share rises from 6.9 / 0.0 / 4.8% to 10.3 / 11.1 / 19.1% on the three B cells with the sub-450 share flat (0 / +3.5 / 0 pp — two extra floor-clean multi-asset cards); top-5 Jaccard is 1.0 in every B cell and set Jaccard ≥ 0.68; arm A is unmoved in all 140 cells; the QA regression is closed in the unit test and in the harness; the #414 card closes in the unit test (partial at a 1,200 bench, full at 1,500) and in the planted league (full, equalizer 1,687.7).*

Why 0.12 and not 0.15: the band's job is to keep the trigger under the late-1st line for every card the corpus actually holds; 0.12 × H < 1,539 for H < 12,825 (no served package prices that high), while 0.15 crosses 1,539 at H = 10,260 and the harness shows the window re-opening there. Why 750 and not lower: 750 is the operator's proposed floor (≈ half a late 1st); below it the sweetener would start touching 1x1s the fairness bar already calls fair.

**Order of PUTs (load-bearing):** `sweetener_best_effort` → 1, then `sweetener_gap_frac` → 0.12, then `sweetener_gap_threshold` → 750. A 750 row standing alone, even for a minute, is V1 — the regressing cell. **Rollback** is the reverse order: threshold → 1539 first, then the two knobs → 0.

## After the flip — how the lead can verify in prod

1. **Rows landed:** `GET /api/admin/config` shows `sweetener_gap_frac: 0.0` and `sweetener_best_effort: 0.0` right after the deploy (seeded by boot); after the three PUTs, 750 / 0.12 / 1, with three `model_config_changes` rows (source `admin-api`) whose timestamps are the D-099 censoring point for the running bake-off window.
2. **The #414 card:** regenerate mattmurf77's deck in league `1312140920132497408` (the config change invalidates the job cache, or force it) and read the new `deck_impressions` row for give ∋ `8112` (London) / receive ∋ `6786` (CeeDee), `basis = consensus`: expect `gap_sweetener` non-null with `gap_before ≈ 1,396`, `gap_after < 1,396`, the equalizer id inside the give array, `fairness_score > 0.81`, and `partial: true` **unless** his roster holds a single WR/flex piece of ≥ ~1,500 consensus value (then a full close at ≤ 879). If the card is absent altogether, that is the deck cut (a 0.81 1x1 losing to higher-fairness cards), not the sweetener — the planted harness league showed exactly that at V0.
3. **Corpus after a week**, split by `model_arm` and `basis` (D-095 C2): sweetened share (`features_json->'gap_sweetener' IS NOT NULL`), the partial share within it, `>1539` share (expect → 0 on arms B/D), sub-450 share (expect flat), and like rate on partial vs full vs unsweetened cards — the hypothesis is that partials are liked more than the unsweetened gap cards they replace, and if they are liked *less* the fallback should be the first thing rolled back.
4. **D-099 censoring:** arm D serves and inherits all three rows; the flip censors the 2026-09-01→09-07 window at the PUT timestamps, as D-172's flip already did the same day.

## Ledger draft (for the lead — `living-memory/TEST_LEDGER.md`)

> **2026-09-02 — gap-sweetener relative band + best-effort fallback (`sweetener_gap_frac`, `sweetener_best_effort`; #414), branch `claude/sweetener-relative-band`.** `pytest backend/tests`: 4541 passed, 1 skipped (clean `origin/main` @ `e16bb487` baseline the same day: 4519 passed, 1 skipped; +22 = the new tests exactly, node-id diff verified). New `backend/tests/test_sweetener_relative_band.py` (21) + `test_bakeoff_arm_a_golden.py::test_sweetener_band_pins_are_load_bearing`: goldens for `close_value_gap` (nine fixtures) and full v3 decks captured on a `git archive origin/main` tree at prod's flag posture, byte-identical at the defaults and non-vacuous at the triple; the #414 card reproduced exactly (5,932.8 / 7,328.8, gap 1,396.0, fairness 0.81) — `None` at today's knobs, a best-effort partial (1,200 → 1,058.9) at 750 / 0.12 / 1, a full close with a 1,500 piece; QA's regression (1,828 → 1,535 at 1,539; unsweetened at 750 alone; partial with the tightest piece at 750 + best-effort); flip guard (a 3,200 piece that passes R1 is refused), strict-reduction guard, call-time reads through the overlay, both stores at 0.0, arm A pins / challenger inherits; stamp path on consensus, v3 and v2-divergence; 200-roster helper fuzz + 32-deck fuzz at the triple (R1, #141 on the path's boards, the path's fairness bar, feasibility, strict reduction, no flip). Six sabotages red → green (S1 band removed, S2 max-for-min, S3 flip guard dropped, S4/S4b arm-A pins removed, S5 import-time read). Harness `docs/plans/sweetener-relative-band/measure_sweetener.py` (prod pins incl. `consensus_fit_weight` 0.5, frozen clock, `PYTHONHASHSEED=0`, baseline twice byte-identical in all 140 cells × 2 thresholds): V1 (750 alone) re-opens `>1539` 0 → 3.5% on 12t@u0 and doubles arm C's 16t share; V3 (750 / 0.12 / 1) closes it to 0 in every live-arm cell, sweetened share 6.9/0/4.8 → 10.3/11.1/19.1%, sub-450 0/+3.5/0 pp, top-5 Jaccard 1.0 in every B cell, arm A unmoved; V4 (0.15) re-opens 3.5%. Planted #414 league: the card is absent at V0 (deck cut) and a full-closed 2x1 (eq 1,687.7 → gap 586) from V1 on. Recommended live triple 750 / 0.12 / 1, PUT order best-effort → frac → threshold. No mobile/web change; `tsc`/testid-lint untouched. Full gates; no express.

## CHANGELOG draft (for the lead)

> **#414 — the gap sweetener now scales with the trade and never ships a closable card unsweetened.** `trade_optimizer.close_value_gap` gains two `model_config` knobs, both default 0 = byte-identical: `sweetener_gap_frac` makes its trigger `max(sweetener_gap_threshold, frac × the richer side)` — the flat 1,539 left the sweetenable window `(1539, 0.25·H)` empty below H ≈ 6,156, so the served London-for-CeeDee 1x1 (gap 1,396 = 19%) passed R1 and was never sweetened; `sweetener_best_effort` replaces the all-or-nothing closer with "attach the gate-passing piece that leaves the tightest gap" (strictly narrower, richer side unchanged, stamped `gap_sweetener.partial: true` on the card and in `features_json`), because a threshold cut alone was a measured regression. Live at 750 / 0.12 / 1 via PUT (the code default of the threshold stays 1539); arm A pins both identities. Docs: `docs/plans/sweetener-relative-band/`, `docs/config-reference.md`.

## DECISIONS draft (for the lead — next free ID; grep first)

> **D-NNN — The Gap Sweetener's Trigger Is a Floor Plus a Relative Band, and Its Closer Is Best-Effort; Shipped Live at 750 / 0.12 / 1.**
> **Context:** #414 (2026-08-31): a London-for-CeeDee 1x1 served at a 1,396 gap (19% of the richer side, fairness 0.81) with no sweetener. The 2026-09-01 review showed the general case — the flat 1,539 trigger and R1's relative 0.25 leave an empty sweetenable window below H ≈ 6,156 — and QA showed the closer is all-or-nothing, so lowering the threshold alone regresses (a card partially closable to 1,535 at 1,539 ships at 1,825 once the line is 750; harness: `>1539` share 0 → 3.5%).
> **Decision:** (1) the trigger is `max(absolute, frac × max(gv, rv))` — a floor plus a band, never a replacement, so the operator's absolute line is relaxed only by a deliberate PUT; (2) when no single asset closes the gap, attach the gate-passing piece that minimises the post-add |gap|, strictly narrower, richer side unchanged (a flipped piece can pass R1 — the 3,200 case), and stamp `partial`; a full close found later still wins; (3) any threshold cut ships WITH best-effort, and the PUT order is best-effort → frac → threshold; (4) arm A pins both identities although its `sweetener_gap_threshold` 0.0 pin makes the reads unreachable today — the D-172 reasoning over the C1/C2 precedent, proven load-bearing with the threshold pin lifted; (5) 0.12, not 0.15: the band must keep the trigger under 1,539 for every package the corpus holds (0.15 crosses at H = 10,260 and re-opens the window in the harness).
> **Consequences:** byte-identical at 0/0 (goldens vs `e16bb487`); at the triple, `>1539` share 0 in every live-arm cell, sweetened share ~1.5–4× with sub-450 flat and top-5 unchanged; deck size can move by ±2 (a sweetened card's key and fairness change what survives the cut). Under the live trade-wide package benchmark a 900 equalizer nets only ~−107 of packaged gap, so thin-bench closes are partials by construction — a property of the 2026-08-21 benchmark fix, recorded here as a finding, not changed.
