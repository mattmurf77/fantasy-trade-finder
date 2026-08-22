# Knockout waterfall v2 — three managers, three rostered arms

**2026-08-22 · measurement only · engine at `941a36d`**

> **This supersedes nothing.** [The 2026-08-19 knockout waterfall](2026-08-19-knockout-waterfall/README.md) measured a different engine at a different arm roster. This is a *second measurement at a second engine state*, run so the two can be compared — not a correction of the first. Where a number moved, §7 names the code between the two runs; where it cannot be pinned to one change, it says so.

`git diff origin/main -- backend/ config/ mobile/ web/` is **empty** — checked, 0 bytes. No engine line was changed. All instrumentation lives in a scratchpad harness outside the repo.

---

## 1. What was measured

League `1312140920132497408`, scoring `1qb_ppr`, consensus snapshot **2026-08-22**. Three managers — **mattmurf77**, **jonbonjourvi**, **gdubs10** — and **all six ordered pairs** between them. Direction matters: the deck is generated *for* `user`, so `mattmurf77 → gdubs10` and `gdubs10 → mattmurf77` are separate boards.

Three arms, exactly the ones rostered on `origin/main` today:

| Arm | Roster knob | Value | Rostered | What it is |
|---|---|--:|---|---|
| `current` | — | — | **yes** | the live engine, live defaults |
| `challenger` | `bakeoff_include_challenger` | 1.0 | **yes — new since the last run (D-095)** | the same engine callable under `MODEL_CHALLENGER_PROFILE`, a thread-local config overlay |
| `gen_v2` | `bakeoff_include_gen_v2` | 1.0 | **yes** | `backend/trade_gen_v2.py`, a separate staged generator |
| `baseline` | `bakeoff_include_baseline` | 0.0 | no | not rostered, not measured |
| `fit` | `bakeoff_include_fit` | 0.0 | no | not rostered, not measured |

`bakeoff_serve_interleaved` reads **1.0** in live `model_config`, so all three rostered arms serve. `trade.bakeoff` is on.

**All three managers have published boards**, so every one of the six pairs takes the **divergence** path. The consensus path — 84.5% of live serving, and the path the challenger's headline levers were written for — is **structurally unreachable on this slice**. See §5; it is the single most important caveat in this report.

### Method

Every gate is monkeypatched **in every namespace that binds it by value** (`trade_service`, `trade_optimizer`, `trade_gen_v2` — the import-time binding trap) with a wrapper that calls the original for the true verdict, records it, and returns a forced PASS. The ladder therefore runs end to end for every candidate, so we learn each rule's verdict even on candidates an *earlier* rule would have killed. That is what makes co-kill attribution possible. The last gate in each ladder is forced to KILL, so no card is built and memory stays bounded.

Knob-driven inline gates (`trade_elo_gap_max`, `min_side_surplus`, `gen2_epsilon`, `gen2_band`) are `if` statements, not functions — they are neutralised through the config overlay and their true verdicts recomputed in-harness from values captured out of the real helper calls, at that arm's own effective knob values.

**Two traps, and what was done about each:**

* **`user_gain_epsilon` is read by both consensus one-way tests.** Neutralising it to measure the ε-gate silently neutralises `#108` too, which then reads a clean, plausible zero. The consensus path is not reached on this slice, so the trap does not bite here — but the guard from the previous run is retained verbatim in the harness for the paths that do reach it.
* **The challenger's profile is a *thread-local overlay*, and `_c()` reads the overlay before `_cfg`.** A force-neutralisation written only into `_cfg` would be silently swallowed under the profile, and every knob gate would read its live value while the report claimed it was disabled. The harness merges the neutralisations *into* the same overlay and asserts `ts._c(k) == topt._c(k) == tg2._c(k) == v` for every key, in every namespace, on every arm.

### Proof the counters incremented

A perfect no-op is indistinguishable from a rule that never fires unless the call count is checked. Every gate wrapper is asserted `> 0` and the per-candidate entry gate is asserted equal to the candidate count:

| Arm | candidates | `fit` | `psw` | `fil` | `r1` | `r2` | `r3` | `r5` | `feas` | `fair` |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| `current` | 501,144 | 501,144 | 501,144 | 501,144 | 501,144 | 501,144 | 501,144 | 501,144 | 1,002,288 | 501,144 |
| `challenger` | 501,144 | 501,144 | 501,144 | 501,144 | 501,144 | 501,144 | 501,144 | 501,144 | 1,002,288 | 501,144 |

| Arm | candidates | `fil` | `psw` | `net` | `pkb` | `feas` |
|---|--:|--:|--:|--:|--:|--:|
| `gen_v2` | 50,225 | 50,225 | 50,225 | 50,225 | 50,225 | 100,450 |

`feas` is twice the candidate count because feasibility is evaluated once per side. **`G6_R5_need` shows 0 kills on `challenger` while its call counter reads 501,144** — the gate ran on every candidate and passed on every candidate, because `need_gate_min_value` is 0 in the profile. That is a measured pass, not a missing bar.

### Validation

Each arm's instrumented universe pass is checked against a **truth pass** that runs the identical enumeration at real config with no forcing. The set of candidates the harness says survives every rule must equal the set the real engine actually scores.

| Arm | harness survivors | engine scored | equal? |
|---|--:|--:|---|
| `current` | 133 | 133 | **yes** |
| `challenger` | 50 | 50 | **yes** |
| `gen_v2` | 83 rows / 51 distinct | — | **yes**, and cross-checked against `gen_v2`'s own stage counters (`S2_considered` 50,225; `S3a_composition` 46,227; `S3a_net_cap` 1,130; `S3a_pick_band` 173; `S3b_feasibility` 132; `S3c_dual_board_ir` 2,134; `S3d_fairness_band` 346) — every one an exact match |

One validation bug was found and fixed during this run and is worth recording: the **2026-08-21 gap auto-sweetener** (`sweetener_gap_threshold`, live at 1539.0) calls `_harmonic_mean` on *sweetened* combinations the enumeration never produced, which credited the truth set with three rows the force pass could not have seen. The recorder now takes one `_harmonic_mean` per fairness evaluation, which confines it to the enumeration's own call. This gate did not exist at the previous run.

### Resolution limits

One league. Six boards. These are **replay counts, not production serving counts** — a full-fanout enumeration over one league's rosters at one snapshot, not a sample of what users were shown. `1312140920132497408` is the only production league with more than two boarded members, so it is the only place a six-ordered-pair boarded slice exists at all; nothing here generalises to league-level frequency. Card counts in §6 are what the arm emits for a single uncapped pair sweep, before deck composition, the interleaver and the 30-card cap.

---

## 2. The combined waterfall

**1,052,513 candidate trades** were enumerated across the three arms. **266 survived every gate** (0.025%). Roughly one candidate in four thousand reaches the ranker.

The single most useful reading of this table is the gap between the **first-kill** column and the **only-kill** column. First-kill is the rule that actually stopped the trade in real execution order. Only-kill is the number of trades that rule was the *sole* reason for. A rule with a large first-kill count and a near-zero only-kill count is standing where the traffic is, not doing work of its own.

| rule | what it does | first kills | % of universe | only kills | mean value gap | arms |
|---|---|--:|--:|--:|--:|---|
| `gap_max` | won't pair two headliners more than 250 board points apart | 508,132 | 48.278% | 12 | 5,020 | current, challenger |
| `R0_141_filler` | every extra piece must be worth ≥ ¼ of its side's best player | 480,197 | 45.624% | 12,543 | 3,414 | current, challenger |
| `S3a_141_filler` | the same junk-filler rule inside `gen_v2` | 46,227 | 4.392% | 1,286 | 5,091 | gen_v2 |
| `G6_R1_overpay` | kills lopsided deals (≥ 500 value AND ≥ 25% more one way) | 9,832 | 0.934% | 118 | 5,149 | current, challenger |
| `S3c_dual_eps_opp` | the partner must gain on their own board | 1,544 | 0.147% | 31 | 7,955 | gen_v2 |
| `min_side_surplus` | **both** managers must gain ≥ 60 on their own board | 1,241 | 0.118% | 1,142 | 742 | current, challenger |
| `S3a_net_cap` | no more than a one-player net swing at any position | 1,130 | 0.107% | 15 | 9,819 | gen_v2 |
| `R0_227_pickswap` | a pick-for-pick swap moves nothing for anyone | 819 | 0.078% | 0 | 663 | current, challenger |
| `G6_R5_need` | contenders must receive an actual roster need | 648 | 0.062% | 106 | 1,019 | current only |
| `S3c_dual_eps_user` | you must gain on your own board | 590 | 0.056% | 88 | 3,930 | gen_v2 |
| `G6_R2_posnet` | the live engine's positional net cap | 587 | 0.056% | 6 | 694 | current, challenger |
| `R0_108_1for1` | never send a player you rank above the one coming back, 1-for-1 | 399 | 0.038% | 4 | 754 | current, challenger |
| `S3d_fairness_band` | `gen_v2`'s market-value band | 346 | 0.033% | 346 | 5,877 | gen_v2 |
| `S3a_pick_band` | a pick used as the exact filler papering a large gap | 173 | 0.016% | 14 | 2,162 | gen_v2 |
| `S3b_feasibility` | starting-lineup check inside `gen_v2` | 132 | 0.013% | 14 | 5,238 | gen_v2 |
| `G6_R3_pickgap` | the live engine's pick-as-filler rule | 94 | 0.009% | 18 | 2,046 | current, challenger |
| `feasibility` | both teams must still field a legal lineup | 83 | 0.008% | 47 | 3,062 | current, challenger |
| `fairness` | the live engine's market-fairness gate — the last gate | 73 | 0.007% | 73 | 3,426 | current, challenger |
| `S3a_227_pickswap` | pick-for-pick churn inside `gen_v2` | 0 | 0.000% | 0 | — | gen_v2 |
| **UNIVERSE** | | **1,052,513** | 100% | | | |
| **SURVIVED** | cleared every gate | **266** | 0.025% | | **1,499** | |

**Two rules account for 94% of every death.** `gap_max` and `R0_141_filler` between them first-kill 988,329 of 1,052,513 candidates. Everything else in the ladder is fighting over the remaining 6%.

**`gap_max` still does almost no independent work.** 508,132 first kills, **12** only-kills — and all 12 are on the challenger, none on `current`. On `current` its only-kill count is exactly **zero**, unchanged from the previous run: every single candidate it stops would have died to another rule anyway. It is a cheap early prune sitting first in the ladder, not a judgement.

**Four rules earn their place, and they are all small.** `min_side_surplus` (1,142 of 1,241 = 92%), `fairness` (73 of 73 = 100%), `S3d_fairness_band` (346 of 346 = 100%) and `feasibility` (47 of 83 = 57%) kill things nothing else would have. Between them that is 1,608 trades — 0.15% of the universe — and it is the only 0.15% where removing a rule would actually change what exists.

---

## 3. Per-arm waterfalls

The arms do **not** share a taxonomy and are not forced into one. `current` and `challenger` run the same eleven-rung ladder in `trade_optimizer.generate_pair_trades_v3` at different knob values; `gen_v2` runs its own eight-stage pipeline in `trade_gen_v2`. Rules named `S3*` exist only in `gen_v2` and have no counterpart column on the other two.

#### `current` — 501,144 candidates, 133 survived, 17 cards emitted

| # | rule | first kills | % of arm universe | co-kills (any rule) | unique kills | mean value gap | leans |
|--:|---|--:|--:|--:|--:|--:|---|
| 1 | `gap_max` | 250,695 | 50.025% | 250,695 | 0 | 5162.5 | receive |
| 2 | `R0_108_1for1` | 218 | 0.044% | 464 | 3 | 695.5 | give |
| 3 | `R0_227_pickswap` | 411 | 0.082% | 538 | 0 | 733.4 | give |
| 4 | `R0_141_filler` | 242,066 | 48.303% | 489,609 | 8,047 | 3137.4 | receive |
| 5 | `G6_R1_overpay` | 5,836 | 1.165% | 420,684 | 52 | 4196.6 | receive |
| 6 | `G6_R2_posnet` | 487 | 0.097% | 186,578 | 5 | 561.9 | receive |
| 7 | `G6_R3_pickgap` | 54 | 0.011% | 58,924 | 14 | 1891.8 | receive |
| 8 | `G6_R5_need` | 648 | 0.129% | 169,661 | 106 | 1019.1 | receive |
| 9 | `feasibility` | 6 | 0.001% | 19,423 | 1 | 5159.9 | receive |
| 10 | `min_side_surplus` | 538 | 0.107% | 409,825 | 513 | 540.2 | receive |
| 11 | `fairness` | 52 | 0.010% | 397,345 | 52 | 3154.8 | receive |
| — | **SURVIVED** | 133 | 0.027% | — | — | **1228.5** | {'give': 21, 'receive': 109, 'even': 3} |

#### `challenger` — 501,144 candidates, 50 survived, 11 cards emitted

| # | rule | first kills | % of arm universe | co-kills (any rule) | unique kills | mean value gap | leans |
|--:|---|--:|--:|--:|--:|--:|---|
| 1 | `gap_max` | 257,437 | 51.370% | 257,437 | 12 | 4880.2 | receive |
| 2 | `R0_108_1for1` | 181 | 0.036% | 390 | 1 | 824.7 | give |
| 3 | `R0_227_pickswap` | 408 | 0.081% | 538 | 0 | 591.9 | give |
| 4 | `R0_141_filler` | 238,131 | 47.517% | 492,582 | 4,496 | 3694.5 | give |
| 5 | `G6_R1_overpay` | 3,996 | 0.797% | 421,102 | 66 | 6539.9 | give |
| 6 | `G6_R2_posnet` | 100 | 0.020% | 182,084 | 1 | 1337.3 | give |
| 7 | `G6_R3_pickgap` | 40 | 0.008% | 53,720 | 4 | 2254.1 | receive |
| 8 | `G6_R5_need` | 0 | 0.000% | 0 | 0 | — | — |
| 9 | `feasibility` | 77 | 0.015% | 21,798 | 46 | 2898.9 | receive |
| 10 | `min_side_surplus` | 703 | 0.140% | 409,779 | 629 | 895.8 | receive |
| 11 | `fairness` | 21 | 0.004% | 398,172 | 21 | 4097.9 | receive |
| — | **SURVIVED** | 50 | 0.010% | — | — | **2349.0** | {'receive': 20, 'give': 30} |

#### `gen_v2` — 50,225 candidates, 83 survived, 20 cards emitted

| # | rule | first kills | % of arm universe | co-kills (any rule) | unique kills | mean value gap | leans |
|--:|---|--:|--:|--:|--:|--:|---|
| 1 | `S3a_141_filler` | 46,227 | 92.040% | 46,227 | 1,286 | 5090.7 | receive |
| 2 | `S3a_227_pickswap` | 0 | 0.000% | 0 | 0 | — | — |
| 3 | `S3a_net_cap` | 1,130 | 2.250% | 22,588 | 15 | 9819.3 | receive |
| 4 | `S3a_pick_band` | 173 | 0.344% | 1,931 | 14 | 2162.0 | give |
| 5 | `S3b_feasibility` | 132 | 0.263% | 4,214 | 14 | 5238.4 | receive |
| 6 | `S3c_dual_eps_user` | 590 | 1.175% | 15,314 | 88 | 3930.0 | give |
| 7 | `S3c_dual_eps_opp` | 1,544 | 3.074% | 25,711 | 31 | 7954.9 | receive |
| 8 | `S3d_fairness_band` | 346 | 0.689% | 44,503 | 346 | 5877.1 | receive |
| — | **SURVIVED** | 83 | 0.165% | — | — | **1419.8** | {'receive': 31, 'even': 34, 'give': 18} |

### What the per-arm split actually says

**`current` and `challenger` enumerate the identical 501,144 candidates and end up 2.7× apart on survivors** — 133 against 50. Same rosters, same pools by count, same eleven rules. The difference is entirely knob-driven:

* **`user_elo_shrink` 0.0** is the lever doing the work. On `current` the user's board is blended toward consensus by comparison count; on `challenger` it is used raw. That changes the divergence prune *map*, so the two arms admit different assets into their twelve-deep pools even though both pools are twelve deep — and it changes `gap_max`, which measures the spread on the *shrunk* board. `gap_max` first-kills 6,742 **more** on the challenger (257,437 vs 250,695), and — uniquely — 12 of those are kills nothing else would have made. On `current` that number is zero.
* **`need_gate_min_value` 0.0 turns R5 off completely.** On `current`, R5 first-kills 648 and is the *sole* reason for **106** of them — the third-largest only-kill count on that arm. On the challenger it kills nothing, from 501,144 live calls. Those 106 trades are exactly what D-095 set out to unblock: laterals that a championship/contender user was refused because the headliner coming back did not fill a need, with no partner-need term anywhere in the test.
* **`feasibility` inverts.** 6 first-kills on `current`, **77** on the challenger, with only-kills going 1 → 46. The raw board reaches shapes the shrunk board never proposed, and a meaningful share of them cannot be fielded.
* **`min_side_surplus` gets harder, not easier**: 538 → 703 first kills, 513 → 629 only-kills. Removing the shrink does not make mutual gain easier to find; it makes the two boards disagree more, and the 60-point floor on *both* sides bites more often.

**`gen_v2` is a different animal entirely.** It enumerates a tenth of the candidates (50,225) because it prunes to five centerpieces per pair, and its junk-filler rule kills **92%** of what it does enumerate. Its one fully independent gate is `S3d_fairness_band` — 346 kills, 346 of them unique, the only 100%-independent rule in the whole system — and its user-side mutual-gain test is the next most independent at 14.9%. Its survival rate, 0.165%, is six times `current`'s and sixteen times the challenger's.

### Which rules kill uniquely, per arm

| Arm | rules that are the *sole* reason a trade died | only-kills | share of that arm's first kills |
|---|---|--:|--:|
| `current` | `R0_141_filler` | 8,047 | 3.3% |
| | `min_side_surplus` | 513 | **95.4%** |
| | `G6_R5_need` | 106 | 16.4% |
| | `fairness` | 52 | **100%** |
| | `G6_R1_overpay` | 52 | 0.9% |
| | `G6_R3_pickgap` | 14 | 25.9% |
| | `G6_R2_posnet` | 5 | 1.0% |
| | `R0_108_1for1` | 3 | 1.4% |
| | `feasibility` | 1 | 16.7% |
| | *`gap_max`, `R0_227_pickswap`* | **0** | — |
| `challenger` | `R0_141_filler` | 4,496 | 1.9% |
| | `min_side_surplus` | 629 | **89.5%** |
| | `G6_R1_overpay` | 66 | 1.7% |
| | `feasibility` | 46 | **59.7%** |
| | `fairness` | 21 | **100%** |
| | `gap_max` | 12 | 0.005% |
| | `G6_R3_pickgap` | 4 | 10.0% |
| | `R0_108_1for1` | 1 | 0.6% |
| | `G6_R2_posnet` | 1 | 1.0% |
| | *`R0_227_pickswap`, `G6_R5_need`* | **0** | — |
| `gen_v2` | `S3a_141_filler` | 1,286 | 2.8% |
| | `S3d_fairness_band` | 346 | **100%** |
| | `S3c_dual_eps_user` | 88 | 14.9% |
| | `S3c_dual_eps_opp` | 31 | 2.0% |
| | `S3a_net_cap` | 15 | 1.3% |
| | `S3a_pick_band` | 14 | 8.1% |
| | `S3b_feasibility` | 14 | 10.6% |
| | *`S3a_227_pickswap`* | **0** (never fired at all) | — |

Read the third column, not the second. `min_side_surplus` first-kills 538 trades on `current` and **95.4% of them would exist if it were removed** — it is the mutual-gain floor and nothing stands behind it. `R0_141_filler` first-kills 242,066 and only 3.3% are its own; the junk-filler rule is mostly agreeing with rules that were going to fire anyway.

### Coverage: three of six directions are empty on the challenger

| direction | `current` survivors | `challenger` survivors | `gen_v2` survivors |
|---|--:|--:|--:|
| mattmurf77 → jonbonjourvi | 14 | 31 | **0** |
| mattmurf77 → gdubs10 | 1 | **0** | 9 |
| jonbonjourvi → mattmurf77 | 3 | 15 | 44 |
| jonbonjourvi → gdubs10 | 101 | **0** | 25 |
| gdubs10 → mattmurf77 | 4 | 4 | 5 |
| gdubs10 → jonbonjourvi | 10 | **0** | 0 |

`current` is the only arm with a non-empty board in all six directions. The challenger concentrates: 46 of its 50 survivors sit on the mattmurf77 ⇄ jonbonjourvi axis, and it produces nothing at all in any direction touching gdubs10 as the *partner*. `gen_v2` covers four of six and is richest (44) exactly where `current` is nearly empty (3) — jonbonjourvi → mattmurf77 — while producing nothing at all in two directions `current` covers.

---

## 4. The value bar — average market-value gap

### What the numbers mean, precisely

The card renders `TradeValueBar` (`mobile/src/components/TradeValueBar.tsx`) from four fields the payload carries: `give_value`, `receive_value`, `favors` and `gap`. Their construction is a single function, `server._value_verdict_payload` (`backend/server.py:926`), which `trade_card_to_dict` calls for the deck and `POST /api/trade/evaluate` calls for the calculator, so the two can never drift.

* **Units: consensus package value, `elo_to_value` space.** `give_value`/`receive_value` are `_consensus_packages(give_ids, recv_ids, seed_value)` (`backend/trade_optimizer.py:100`) — `package_value_v2` over each side with a trade-wide `v_max`, priced off the **consensus seed board**, not either manager's personal board. All three arms stamp the card from that identical call (`trade_optimizer.py:588`, `trade_service.py:5981` and `:6274`, `trade_gen_v2.py:1187`), so the number is comparable across arms by construction. Both are rounded to 1 dp before the payload is built.
* **`gap` is ABSOLUTE and unsigned.** `gap.value = round(abs(receive_value - give_value), 1)`. Direction is carried separately by `favors` (`'receive'` = you get more, `'give'` = you send more, `'even'`) and by `gap.add_to`, which names the lighter side. `even` is the ratio test `min/max ≥ 0.95`, not `gap == 0`.
* This report computes the identical expression on every candidate, from the same helper the engine calls. It is not a lookalike.

Two things the bar is **not**: it is not the personal-board surplus the mutual-gain gates test (`gain_user`/`gain_partner` in the CSVs carry that separately), and it is not the fairness ratio — `gap` is a scale-*ful* absolute delta, which is exactly why the 2026-08-21 gap auto-sweetener exists.

### Average gap per rule, per arm

Mean of `|receive_value − give_value|` over every candidate that rule first-killed. Dashes mean the rule does not exist on that arm.

| rule | `current` | `challenger` | `gen_v2` | combined |
|---|--:|--:|--:|--:|
| `gap_max` | 5,163 | 4,880 | — | 5,020 |
| `R0_108_1for1` | 696 | 825 | — | 754 |
| `R0_227_pickswap` | 733 | 592 | — | 663 |
| `R0_141_filler` | 3,137 | 3,695 | — | 3,414 |
| `G6_R1_overpay` | 4,197 | 6,540 | — | 5,149 |
| `G6_R2_posnet` | 562 | 1,337 | — | 694 |
| `G6_R3_pickgap` | 1,892 | 2,254 | — | 2,046 |
| `G6_R5_need` | 1,019 | *never fires* | — | 1,019 |
| `feasibility` | 5,160 | 2,899 | — | 3,062 |
| `min_side_surplus` | 540 | 896 | — | 742 |
| `fairness` | 3,155 | 4,098 | — | 3,426 |
| `S3a_141_filler` | — | — | 5,091 | 5,091 |
| `S3a_net_cap` | — | — | 9,819 | 9,819 |
| `S3a_pick_band` | — | — | 2,162 | 2,162 |
| `S3b_feasibility` | — | — | 5,238 | 5,238 |
| `S3c_dual_eps_user` | — | — | 3,930 | 3,930 |
| `S3c_dual_eps_opp` | — | — | 7,955 | 7,955 |
| `S3d_fairness_band` | — | — | 5,877 | 5,877 |
| **all candidates** | **4,151** | **4,318** | **5,261** | **4,284** |
| **SURVIVORS** | **1,229** | **2,349** | **1,420** | **1,499** |

### What this says

**The gates are, on the whole, doing the right thing to the bar.** Mean gap across every enumerated candidate is 4,284; mean gap across survivors is 1,499 — the ladder cuts the typical imbalance by 65%. For scale, the live `sweetener_gap_threshold` is **1,539**, so the average survivor sits just under the threshold at which the engine now tries to auto-sweeten.

**But the arms differ sharply, and not in the challenger's favour on this axis.** `current` survivors average a 1,229 gap; challenger survivors average **2,349**, nearly twice as wide. And the direction flips:

| Arm | survivors | favours **you** (`receive`) | favours **them** (`give`) | `even` |
|---|--:|--:|--:|--:|
| `current` | 133 | **109 (82%)** | 21 (16%) | 3 (2%) |
| `challenger` | 50 | 20 (40%) | **30 (60%)** | 0 (0%) |
| `gen_v2` | 83 | 31 (37%) | 18 (22%) | **34 (41%)** |

This is the challenger's thesis showing up as a measurement. `current`'s board is 82% trades where the user receives more consensus value than they send — the "one-sidedness" D-095 was written against — but that one-sidedness runs *in the user's favour*, and removing the shrink does not make the deck more even, it makes 60% of it point the other way while widening the average gap. On this slice, the challenger trades a user-favouring skew for a partner-favouring one, at roughly double the absolute imbalance.

`gen_v2` is the only arm whose modal survivor is `even` (41%). Its `S3d_fairness_band` gate is a **ratio** band and it is the only 100%-independent fairness rule in the whole system; it produces the tightest verdicts and the widest kills (mean gap 5,877 on what it stops).

**Per-rule, the gap column reads as a diagnosis of what each rule is for.** The rules with the widest mean kill gaps — `S3a_net_cap` (9,819), `S3c_dual_eps_opp` (7,955), `G6_R1_overpay` (5,149), `S3d_fairness_band` (5,877) — are catching genuinely lopsided proposals. The rules with the narrowest — `min_side_surplus` (742), `G6_R2_posnet` (694), `R0_227_pickswap` (663), `R0_108_1for1` (754) — are killing trades that are already close to even on market value, for reasons that have nothing to do with market value: mutual gain on personal boards, roster shape, and churn. That is the correct division of labour, and it is visible in the data rather than assumed.

### On the served cards, not just the survivors

Survivor gap is measured on the candidate as enumerated. The **2026-08-21 gap auto-sweetener** then runs on emitted cards and re-balances any card whose absolute gap exceeds 1,539 by adding the smallest sufficient equalizer. Measured on the cards each arm actually emits:

| Arm | cards emitted | mean gap on the card | sweetened |
|---|--:|--:|--:|
| `current` | 17 | 1,753 | 3 |
| `challenger` | 11 | 2,398 | 2 |
| `gen_v2` | 20 | 1,719 | 0 |

Emitted-card gaps run **higher** than survivor gaps on every arm, because emission is not a random draw from the survivors — the ranker prefers big names, and big names carry big absolute gaps. The sweetener closed 5 of 48 cards.

---

## 5. The caveat that governs the challenger comparison

Three of the challenger's nine profile keys — `consensus_both_ways` 1.0, `consensus_fairness_floor` 0.75, and the shrink lever's consensus half — are read **only on the consensus generator** (`backend/trade_service.py:6056`). That path runs when the opponent has no published board. All three managers in this slice have boards, so **every one of the six pairs takes the divergence path and none of those three levers is reachable.**

What is being compared here is therefore the challenger's *divergence* profile only: `user_elo_shrink` 0.0, `need_gate_min_value` 0.0, and the compressed `tier_mult` ladder — and the tier ladder is a ranking term that never appears in a knockout waterfall at all, because it multiplies `composite_score` after every gate has run.

D-095's own note is that the consensus group "is the whole point: 84.5% of cards take that path." **None of that 84.5% is measured here.** A boarded-pair slice is the right place to measure the shrink lever and R5, and the wrong place to form a view on the challenger as a whole.

One related note: **D-085's placement tier clamp is live on `current` and structurally inert on `challenger`.** `_shrink_user_elo` returns early when `user_elo_shrink ≤ 0`, and the clamp is a bound on the blend, so there is nothing left to bound. That is deliberate in the code and it means the two arms differ by D-085 as well as by the shrink itself.

---

## 6. What each arm actually offers

The 48 cards the three arms emit across the six pairs, at their real `give_value` / `receive_value` / `gap`, are in `served-cards.json` and reproduced in the HTML view. A few worth naming:

* **`current`, jonbonjourvi → mattmurf77, 4-for-2**: Marvin Harrison Jr + three picks for Drake London + Ashton Jeanty. `give_value` 7,163, `receive_value` 12,253, gap **5,090** in the user's favour. This is the widest card the arm emits.
* **`challenger`, mattmurf77 → jonbonjourvi, 2-for-3**: Trey McBride + Emeka Egbuka for Rome Odunze + two picks. Gap **3,737**, favouring the *partner*. `current` never proposes this direction at this magnitude.
* **`gen_v2`, jonbonjourvi → gdubs10, 1-for-2**: a 2026 1.03 for Tyler Warren + Derrick Henry. Gap **16**. The tightest card any arm produced.
* Both `current` and `challenger` emit **Jordan Watkins for a 2028 2nd** (gap 133) — a genuine agreement between the two arms on a small, clean, even trade.

---

## 7. What changed since the 2026-08-19 run

**Do not read the deltas below as the effect of any one change.** The task brief named seven decisions between the two runs (D-082 give-side headliner cap, D-084 round-2 pick reprice, D-085 placement tier clamp, D-088 pick-badge inverse, D-090 real slot labels, D-091 pick-horizon filter, D-096 likes-you gating). The actual delta on `origin/main` between the previous run's base (`2a492b6`) and `941a36d` is **about thirty commits** and includes at least four more that move these numbers directly:

| landed | what it does to this measurement |
|---|---|
| **#162 / d42872f** — package-pricing honesty (`package_bench_trade_wide`, live 1.0) | changes `package_value_v2`, i.e. **`give_value` and `receive_value` themselves**. Every value-bar number in this report is on the new math and is not comparable to a pre-#162 value. |
| **#162 / #166 / #167** — gap auto-sweetener (`sweetener_gap_threshold`, live 1,539) | a post-gate pass that rewrites emitted cards' ids and values. It did not exist at the last run; §4's served-card table is measuring something that had no counterpart. |
| **#167 / 3192d13** — true per-slot pick pricing (D-146) | picks are now priced at read time per resolved draft slot. The top-6 owned picks injected into each pool are a **different set** than last time, and they are priced differently. Both pools and both boards move. |
| **#168** — negative-results memory (dark, `negmem_strength` 1.0) | multiplies `composite_score` inside generation. Ranking only; no gate reads it. |
| **D-091** — pick-horizon filter | confirmed in the data: prod `draft_picks` for this league now carry **2026/2027/2028 only**, no 2029. The phantom class is gone. |
| **D-090** — real slot labels | confirmed: picks resolve to `2026 1.01`, `2026 1.04 (from PaulSm3nis)`, not generic ordinals. |
| **D-095** | added the `challenger` arm, which is half of this report. |

With that stated, the like-for-like comparison is clean for the two arms that existed in both runs, because both were measured over the identical six ordered pairs and the divergence universe is unchanged at 501,144:

| rule | 2026-08-19 first kills | 2026-08-22 first kills | Δ | only-kills then → now |
|---|--:|--:|--:|---|
| `gap_max` | 203,726 | 250,695 | **+46,969** | 0 → 0 |
| `R0_141_filler` | 284,694 | 242,066 | **−42,628** | 15,964 → 8,047 |
| `G6_R1_overpay` | 8,161 | 5,836 | −2,325 | 107 → 52 |
| `R0_227_pickswap` | 1,459 | 411 | −1,048 | 0 → 0 |
| `min_side_surplus` | 1,162 | 538 | −624 | 1,149 → 513 |
| `G6_R5_need` | 809 | 648 | −161 | 105 → 106 |
| `G6_R2_posnet` | 361 | 487 | +126 | 38 → 5 |
| `R0_108_1for1` | 218 | 218 | 0 | 0 → 3 |
| `feasibility` | 183 | 6 | −177 | 19 → 1 |
| `G6_R3_pickgap` | 71 | 54 | −17 | 1 → 14 |
| `fairness` | 0 | **52** | **+52** | 0 → 52 |
| **survivors** | **300** | **133** | **−167 (−56%)** | |

And for `gen_v2`:

| rule | 2026-08-19 | 2026-08-22 | Δ |
|---|--:|--:|--:|
| universe | 53,025 | 50,225 | −2,800 (−5.3%) |
| `S3a_141_filler` | 50,152 | 46,227 | −3,925 |
| `S3a_net_cap` | 917 | 1,130 | +213 |
| `S3c_dual_eps_opp` | 774 | 1,544 | +770 |
| `S3c_dual_eps_user` | 759 | 590 | −169 |
| `S3d_fairness_band` | 40 | 346 | +306 |
| `S3a_pick_band` | 121 | 173 | +52 |
| `S3b_feasibility` | 216 | 132 | −84 |
| **survivor rows** | **46** | **83** | **+37 (+80%)** |

### Reading the deltas honestly

**The `gap_max` / `R0_141_filler` swap is a re-ordering, not a behaviour change.** `gap_max` gained 46,969 first kills and `R0_141_filler` lost 42,628 — and `gap_max` sits *above* the filler rule in the ladder, so most of that is the same trades changing which rule got to them first. What moved `gap_max` is the **shrunk board**: D-085's placement tier clamp (2026-08-19, live at `placement_tier_clamp` 1.0) bounds the blend to the user's own placement band, and `gap_max` measures the spread on exactly that board. Repriced picks (D-146) move it too, since picks sit in both pools.

**The one genuinely new bar is `fairness`.** It first-killed nothing in the three-manager slice on 2026-08-19 and first-kills 52 now, all 52 of them uniquely. A candidate only reaches `fairness` if all ten rules above it passed, so this is a change in *what arrives at the last gate*, and `package_bench_trade_wide` — which is precisely a change to how the two package values that gate compares are computed — is the defensible attribution. It is not the only possible one and this report does not claim it is proven.

**The survivor collapse on `current` (300 → 133) is real and is not explained by any single item above.** The universe is identical, the enumeration is identical, and 167 trades that cleared every gate three days ago no longer do. The three candidates with a direct mechanism are D-085 (changes the shrunk board every surplus and gap test runs on), D-146 (changes what picks are in the pool and what they are worth) and #162 (changes both package values). Isolating them would need a per-change bisect, which this measurement did not run.

**`gen_v2` moved the other way (+80% survivors) while its universe shrank 5.3%.** Its centerpiece pool is pick-sensitive, so D-146 and D-091 are the visible cause of the smaller universe; why more of a smaller universe survives is not established here.

---

## 8. Files

Written to `~/Desktop/ftf-knockout-three-managers-v2/` — outside the repo, because these are raw production rows and prod extracts are not committed.

| file | rows | what it is |
|---|--:|---|
| `trades.csv` | 16,129 | one row per **notable** trade — every survivor plus every trade a rule killed *uniquely*. Carries arm, manager, readable player and pick names, shape, both values, the gap, `favors`, the verdict, the rule, the plain-language `what_the_rule_does`, and every other rule that also failed. Same subset convention as the 2026-08-19 `trades.csv`. |
| `trades-all-candidates.csv.gz` | 1,052,513 | every enumerated candidate, ids not names — join to `assets.csv`. 22 MB compressed. |
| `waterfall.csv` | 21 | the rule table with **per-arm columns**: first kills, % of that arm's universe, only-kills and mean value gap for each of `current`, `challenger`, `gen_v2`, plus combined totals. The `what_it_does` text is carried over verbatim from the 2026-08-19 run so the two files line up. |
| `top100-give-heavy.csv` | 100 | the 100 candidates where the give side most exceeds the receive side. |
| `top100-receive-heavy.csv` | 100 | the 100 where the receive side most exceeds the give side. |
| `assets.csv` | 691 | id → name / position / team / player-or-pick, for every asset in the sheets. |

Every Sleeper id is resolved to a name. Current-year picks resolve to real slots (`2026 1.01`, `2026 1.04 (from PaulSm3nis)`) since D-090.

---

## 9. The two top-100 lists

Both lists are sorted on the **signed** value difference, so each is one-directional. Both are dominated by near-duplicate shapes: the same elite core with a rotating third or fourth piece, which is what an exhaustive subset enumeration produces at the extremes.

Read the composition first, because it is the finding:

| | give-heavy 100 | receive-heavy 100 |
|---|---|---|
| arms | `challenger` 46, `current` 45, `gen_v2` 9 | **`challenger` 100, `current` 0, `gen_v2` 0** |
| manager | mattmurf77 ×100 | jonbonjourvi ×100 |
| verdict | 100 killed, 0 survived | 100 killed, 0 survived |
| killing rule | `gap_max` 91, `S3a_net_cap` 5, `S3a_141_filler` 4 | `gap_max` 100 |
| gap range | 20,990 → 20,057 | 18,958 → 18,309 |

**Not one of the 200 most lopsided candidates in either direction survives.** All 200 die, 191 of them to `gap_max` — which, as §2 records, almost never kills anything *uniquely*. The engine's most extreme proposals are caught by its cheapest rule, and caught redundantly.

**The receive-heavy list is 100% challenger, and that is the sharpest single result in this report.** `current`'s widest receive-heavy candidate is a gap of 13,899; the challenger's is 18,958. Removing `user_elo_shrink` opens the "jonbonjourvi receives mattmurf77's entire elite core" direction that the shrunk board never proposes at that magnitude. The gates catch all of it — but the *enumeration* under the challenger reaches 36% further into that tail.

### Top 100 — the give side most exceeds the receive side

Sorted by `give_value − receive_value`, descending. Every one of these is a trade where the user would be sending far more consensus value than they get back.

| # | arm | manager → partner | shape | gives | receives | give val | recv val | gap | verdict / rule |
|--:|---|---|---|---|---|--:|--:|--:|---|
| 1 | `gen_v2` | mattmurf77 → gdubs10 | 3x1 | Ashton Jeanty + Drake London + Jaxon Smith-Njigba | Tua Tagovailoa | 21,229 | 239 | **20,990** | killed · `S3a_net_cap` |
| 2 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + MarShawn Lloyd | 21,229 | 338 | **20,891** | killed · `gap_max` |
| 3 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + MarShawn Lloyd | 21,229 | 338 | **20,891** | killed · `gap_max` |
| 4 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + Elijah Arroyo | 21,229 | 345 | **20,884** | killed · `gap_max` |
| 5 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + Elijah Arroyo | 21,229 | 345 | **20,884** | killed · `gap_max` |
| 6 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Elijah Arroyo + MarShawn Lloyd | 21,229 | 373 | **20,856** | killed · `gap_max` |
| 7 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Elijah Arroyo + MarShawn Lloyd | 21,229 | 373 | **20,856** | killed · `gap_max` |
| 8 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + 2028 2nd | 21,229 | 388 | **20,841** | killed · `gap_max` |
| 9 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + 2028 2nd | 21,229 | 388 | **20,841** | killed · `gap_max` |
| 10 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + Dylan Sampson | 21,229 | 404 | **20,825** | killed · `gap_max` |
| 11 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + Dylan Sampson | 21,229 | 404 | **20,825** | killed · `gap_max` |
| 12 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 2028 2nd + MarShawn Lloyd | 21,229 | 416 | **20,813** | killed · `gap_max` |
| 13 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 2028 2nd + MarShawn Lloyd | 21,229 | 416 | **20,813** | killed · `gap_max` |
| 14 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 2028 2nd + Elijah Arroyo | 21,229 | 423 | **20,806** | killed · `gap_max` |
| 15 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Elijah Arroyo + 2028 2nd | 21,229 | 423 | **20,806** | killed · `gap_max` |
| 16 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Dylan Sampson + MarShawn Lloyd | 21,229 | 432 | **20,797** | killed · `gap_max` |
| 17 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Dylan Sampson + MarShawn Lloyd | 21,229 | 432 | **20,797** | killed · `gap_max` |
| 18 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Dylan Sampson + Elijah Arroyo | 21,229 | 439 | **20,790** | killed · `gap_max` |
| 19 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Dylan Sampson + Elijah Arroyo | 21,229 | 439 | **20,790** | killed · `gap_max` |
| 20 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Dylan Sampson + 2028 2nd | 21,229 | 482 | **20,747** | killed · `gap_max` |
| 21 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Dylan Sampson + 2028 2nd | 21,229 | 482 | **20,747** | killed · `gap_max` |
| 22 | `challenger` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + Elijah Arroyo + MarShawn Lloyd | 21,229 | 528 | **20,702** | killed · `gap_max` |
| 23 | `current` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + Elijah Arroyo + MarShawn Lloyd | 21,229 | 528 | **20,702** | killed · `gap_max` |
| 24 | `challenger` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + 2028 2nd + MarShawn Lloyd | 21,229 | 571 | **20,658** | killed · `gap_max` |
| 25 | `current` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + 2028 2nd + MarShawn Lloyd | 21,229 | 571 | **20,658** | killed · `gap_max` |
| 26 | `challenger` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + 2028 2nd + Elijah Arroyo | 21,229 | 578 | **20,651** | killed · `gap_max` |
| 27 | `current` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + Elijah Arroyo + 2028 2nd | 21,229 | 578 | **20,651** | killed · `gap_max` |
| 28 | `challenger` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + Dylan Sampson + MarShawn Lloyd | 21,229 | 587 | **20,642** | killed · `gap_max` |
| 29 | `current` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + Dylan Sampson + MarShawn Lloyd | 21,229 | 587 | **20,642** | killed · `gap_max` |
| 30 | `challenger` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + Dylan Sampson + Elijah Arroyo | 21,229 | 594 | **20,635** | killed · `gap_max` |
| 31 | `current` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + Dylan Sampson + Elijah Arroyo | 21,229 | 594 | **20,635** | killed · `gap_max` |
| 32 | `challenger` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 2028 2nd + Elijah Arroyo + MarShawn Lloyd | 21,229 | 606 | **20,624** | killed · `gap_max` |
| 33 | `current` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Elijah Arroyo + 2028 2nd + MarShawn Lloyd | 21,229 | 606 | **20,624** | killed · `gap_max` |
| 34 | `challenger` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Dylan Sampson + Elijah Arroyo + MarShawn Lloyd | 21,229 | 622 | **20,607** | killed · `gap_max` |
| 35 | `current` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Dylan Sampson + Elijah Arroyo + MarShawn Lloyd | 21,229 | 622 | **20,607** | killed · `gap_max` |
| 36 | `challenger` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + Dylan Sampson + 2028 2nd | 21,229 | 637 | **20,592** | killed · `gap_max` |
| 37 | `current` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + Dylan Sampson + 2028 2nd | 21,229 | 637 | **20,592** | killed · `gap_max` |
| 38 | `challenger` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Dylan Sampson + 2028 2nd + MarShawn Lloyd | 21,229 | 665 | **20,564** | killed · `gap_max` |
| 39 | `current` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Dylan Sampson + 2028 2nd + MarShawn Lloyd | 21,229 | 665 | **20,564** | killed · `gap_max` |
| 40 | `challenger` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Dylan Sampson + 2028 2nd + Elijah Arroyo | 21,229 | 672 | **20,557** | killed · `gap_max` |
| 41 | `current` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Dylan Sampson + Elijah Arroyo + 2028 2nd | 21,229 | 672 | **20,557** | killed · `gap_max` |
| 42 | `gen_v2` | mattmurf77 → gdubs10 | 3x2 | Ashton Jeanty + Drake London + Jaxon Smith-Njigba | Tua Tagovailoa + Jaxson Dart | 21,229 | 688 | **20,541** | killed · `S3a_141_filler` |
| 43 | `gen_v2` | mattmurf77 → gdubs10 | 3x2 | Ashton Jeanty + Drake London + Jaxon Smith-Njigba | Jaxson Dart + Tua Tagovailoa | 21,229 | 688 | **20,541** | killed · `S3a_141_filler` |
| 44 | `gen_v2` | mattmurf77 → gdubs10 | 3x2 | Ashton Jeanty + Drake London + Jaxon Smith-Njigba | Tua Tagovailoa + Jaylen Warren | 21,229 | 746 | **20,483** | killed · `S3a_141_filler` |
| 45 | `gen_v2` | mattmurf77 → gdubs10 | 3x2 | Ashton Jeanty + Drake London + Jaxon Smith-Njigba | Jaylen Warren + Tua Tagovailoa | 21,229 | 746 | **20,483** | killed · `S3a_141_filler` |
| 46 | `gen_v2` | mattmurf77 → gdubs10 | 3x1 | Ashton Jeanty + Drake London + Jaxon Smith-Njigba | Jaxson Dart | 21,229 | 819 | **20,410** | killed · `S3a_net_cap` |
| 47 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Isaiah Likely + James Conner | 21,229 | 895 | **20,334** | killed · `gap_max` |
| 48 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + Isaiah Likely | 21,229 | 895 | **20,334** | killed · `gap_max` |
| 49 | `gen_v2` | mattmurf77 → gdubs10 | 3x1 | Ashton Jeanty + Drake London + Jaxon Smith-Njigba | Jaylen Warren | 21,229 | 908 | **20,321** | killed · `S3a_net_cap` |
| 50 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Isaiah Likely + MarShawn Lloyd | 21,229 | 923 | **20,306** | killed · `gap_max` |
| 51 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Isaiah Likely + MarShawn Lloyd | 21,229 | 923 | **20,306** | killed · `gap_max` |
| 52 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Isaiah Likely + Elijah Arroyo | 21,229 | 930 | **20,299** | killed · `gap_max` |
| 53 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Isaiah Likely + Elijah Arroyo | 21,229 | 930 | **20,299** | killed · `gap_max` |
| 54 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Isaiah Likely + 2028 2nd | 21,229 | 973 | **20,256** | killed · `gap_max` |
| 55 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Isaiah Likely + 2028 2nd | 21,229 | 973 | **20,256** | killed · `gap_max` |
| 56 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Isaiah Likely + Dylan Sampson | 21,229 | 989 | **20,240** | killed · `gap_max` |
| 57 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Dylan Sampson + Isaiah Likely | 21,229 | 989 | **20,240** | killed · `gap_max` |
| 58 | `challenger` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Isaiah Likely + James Conner + MarShawn Lloyd | 21,229 | 1,078 | **20,151** | killed · `gap_max` |
| 59 | `current` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + Isaiah Likely + MarShawn Lloyd | 21,229 | 1,078 | **20,151** | killed · `gap_max` |
| 60 | `challenger` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Isaiah Likely + James Conner + Elijah Arroyo | 21,229 | 1,085 | **20,144** | killed · `gap_max` |
| 61 | `current` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + Isaiah Likely + Elijah Arroyo | 21,229 | 1,085 | **20,144** | killed · `gap_max` |
| 62 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Trey McBride | James Conner + MarShawn Lloyd | 20,472 | 338 | **20,135** | killed · `gap_max` |
| 63 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Trey McBride | James Conner + MarShawn Lloyd | 20,472 | 338 | **20,135** | killed · `gap_max` |
| 64 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Emeka Egbuka | James Conner + MarShawn Lloyd | 20,467 | 338 | **20,129** | killed · `gap_max` |
| 65 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Emeka Egbuka | James Conner + MarShawn Lloyd | 20,467 | 338 | **20,129** | killed · `gap_max` |
| 66 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Trey McBride | James Conner + Elijah Arroyo | 20,472 | 345 | **20,128** | killed · `gap_max` |
| 67 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Trey McBride | James Conner + Elijah Arroyo | 20,472 | 345 | **20,128** | killed · `gap_max` |
| 68 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + 2028 1st | 21,229 | 1,104 | **20,126** | killed · `gap_max` |
| 69 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + 2028 1st | 21,229 | 1,104 | **20,126** | killed · `gap_max` |
| 70 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Emeka Egbuka | James Conner + Elijah Arroyo | 20,467 | 345 | **20,122** | killed · `gap_max` |
| 71 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Emeka Egbuka | James Conner + Elijah Arroyo | 20,467 | 345 | **20,122** | killed · `gap_max` |
| 72 | `challenger` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Isaiah Likely + Elijah Arroyo + MarShawn Lloyd | 21,229 | 1,112 | **20,116** | killed · `gap_max` |
| 73 | `current` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Isaiah Likely + Elijah Arroyo + MarShawn Lloyd | 21,229 | 1,112 | **20,116** | killed · `gap_max` |
| 74 | `gen_v2` | mattmurf77 → gdubs10 | 3x2 | Ashton Jeanty + Drake London + Jaxon Smith-Njigba | Jaylen Warren + Jaxson Dart | 21,229 | 1,123 | **20,106** | killed · `S3a_net_cap` |
| 75 | `gen_v2` | mattmurf77 → gdubs10 | 3x2 | Ashton Jeanty + Drake London + Jaxon Smith-Njigba | Jaxson Dart + Jaylen Warren | 21,229 | 1,123 | **20,106** | killed · `S3a_net_cap` |
| 76 | `challenger` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Isaiah Likely + James Conner + 2028 2nd | 21,229 | 1,128 | **20,101** | killed · `gap_max` |
| 77 | `current` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + Isaiah Likely + 2028 2nd | 21,229 | 1,128 | **20,101** | killed · `gap_max` |
| 78 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Trey McBride | Elijah Arroyo + MarShawn Lloyd | 20,472 | 373 | **20,100** | killed · `gap_max` |
| 79 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Trey McBride | Elijah Arroyo + MarShawn Lloyd | 20,472 | 373 | **20,100** | killed · `gap_max` |
| 80 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | MarShawn Lloyd + 2028 1st | 21,229 | 1,131 | **20,098** | killed · `gap_max` |
| 81 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | MarShawn Lloyd + 2028 1st | 21,229 | 1,131 | **20,098** | killed · `gap_max` |
| 82 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Emeka Egbuka | Elijah Arroyo + MarShawn Lloyd | 20,467 | 373 | **20,094** | killed · `gap_max` |
| 83 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Emeka Egbuka | Elijah Arroyo + MarShawn Lloyd | 20,467 | 373 | **20,094** | killed · `gap_max` |
| 84 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Elijah Arroyo + 2028 1st | 21,229 | 1,138 | **20,091** | killed · `gap_max` |
| 85 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Elijah Arroyo + 2028 1st | 21,229 | 1,138 | **20,091** | killed · `gap_max` |
| 86 | `current` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | James Conner + Dylan Sampson + Isaiah Likely | 21,229 | 1,144 | **20,085** | killed · `gap_max` |
| 87 | `challenger` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Isaiah Likely + James Conner + Dylan Sampson | 21,229 | 1,144 | **20,085** | killed · `gap_max` |
| 88 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Trey McBride | James Conner + 2028 2nd | 20,472 | 388 | **20,085** | killed · `gap_max` |
| 89 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Trey McBride | James Conner + 2028 2nd | 20,472 | 388 | **20,085** | killed · `gap_max` |
| 90 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Emeka Egbuka | James Conner + 2028 2nd | 20,467 | 388 | **20,079** | killed · `gap_max` |
| 91 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Emeka Egbuka | James Conner + 2028 2nd | 20,467 | 388 | **20,079** | killed · `gap_max` |
| 92 | `challenger` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Isaiah Likely + 2028 2nd + MarShawn Lloyd | 21,229 | 1,156 | **20,073** | killed · `gap_max` |
| 93 | `current` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Isaiah Likely + 2028 2nd + MarShawn Lloyd | 21,229 | 1,156 | **20,073** | killed · `gap_max` |
| 94 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Trey McBride | James Conner + Dylan Sampson | 20,472 | 404 | **20,068** | killed · `gap_max` |
| 95 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Trey McBride | James Conner + Dylan Sampson | 20,472 | 404 | **20,068** | killed · `gap_max` |
| 96 | `challenger` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Isaiah Likely + 2028 2nd + Elijah Arroyo | 21,229 | 1,163 | **20,066** | killed · `gap_max` |
| 97 | `current` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Isaiah Likely + Elijah Arroyo + 2028 2nd | 21,229 | 1,163 | **20,066** | killed · `gap_max` |
| 98 | `challenger` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Emeka Egbuka | James Conner + Dylan Sampson | 20,467 | 404 | **20,062** | killed · `gap_max` |
| 99 | `current` | mattmurf77 → jonbonjourvi | 3x2 | Ashton Jeanty + Jaxon Smith-Njigba + Emeka Egbuka | James Conner + Dylan Sampson | 20,467 | 404 | **20,062** | killed · `gap_max` |
| 100 | `challenger` | mattmurf77 → jonbonjourvi | 3x3 | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | Isaiah Likely + Dylan Sampson + MarShawn Lloyd | 21,229 | 1,172 | **20,057** | killed · `gap_max` |

### Top 100 — the receive side most exceeds the give side

Sorted by `receive_value − give_value`, descending. Every one of these is a trade where the user would be receiving far more consensus value than they send.

| # | arm | manager → partner | shape | gives | receives | give val | recv val | gap | verdict / rule |
|--:|---|---|---|---|---|--:|--:|--:|---|
| 1 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | James Conner + MarShawn Lloyd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 80 | 19,039 | **18,958** | killed · `gap_max` |
| 2 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | James Conner + Elijah Arroyo | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 82 | 19,039 | **18,956** | killed · `gap_max` |
| 3 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | Elijah Arroyo + MarShawn Lloyd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 89 | 19,039 | **18,949** | killed · `gap_max` |
| 4 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | James Conner + 2028 2nd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 94 | 19,039 | **18,945** | killed · `gap_max` |
| 5 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | James Conner + Dylan Sampson | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 98 | 19,039 | **18,941** | killed · `gap_max` |
| 6 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | 2028 2nd + MarShawn Lloyd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 100 | 19,039 | **18,938** | killed · `gap_max` |
| 7 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | 2028 2nd + Elijah Arroyo | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 102 | 19,039 | **18,936** | killed · `gap_max` |
| 8 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | Dylan Sampson + MarShawn Lloyd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 105 | 19,039 | **18,934** | killed · `gap_max` |
| 9 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | Dylan Sampson + Elijah Arroyo | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 106 | 19,039 | **18,932** | killed · `gap_max` |
| 10 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | Dylan Sampson + 2028 2nd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 118 | 19,039 | **18,921** | killed · `gap_max` |
| 11 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | James Conner + Elijah Arroyo + MarShawn Lloyd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 126 | 19,039 | **18,913** | killed · `gap_max` |
| 12 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | James Conner + 2028 2nd + MarShawn Lloyd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 137 | 19,039 | **18,902** | killed · `gap_max` |
| 13 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | James Conner + 2028 2nd + Elijah Arroyo | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 139 | 19,039 | **18,900** | killed · `gap_max` |
| 14 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | James Conner + Dylan Sampson + MarShawn Lloyd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 141 | 19,039 | **18,897** | killed · `gap_max` |
| 15 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | James Conner + Dylan Sampson + Elijah Arroyo | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 143 | 19,039 | **18,895** | killed · `gap_max` |
| 16 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | 2028 2nd + Elijah Arroyo + MarShawn Lloyd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 146 | 19,039 | **18,893** | killed · `gap_max` |
| 17 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Dylan Sampson + Elijah Arroyo + MarShawn Lloyd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 150 | 19,039 | **18,888** | killed · `gap_max` |
| 18 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | James Conner + Dylan Sampson + 2028 2nd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 154 | 19,039 | **18,884** | killed · `gap_max` |
| 19 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Dylan Sampson + 2028 2nd + MarShawn Lloyd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 161 | 19,039 | **18,877** | killed · `gap_max` |
| 20 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Dylan Sampson + 2028 2nd + Elijah Arroyo | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 163 | 19,039 | **18,876** | killed · `gap_max` |
| 21 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | Isaiah Likely + James Conner | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 262 | 19,039 | **18,776** | killed · `gap_max` |
| 22 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | Isaiah Likely + MarShawn Lloyd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 269 | 19,039 | **18,770** | killed · `gap_max` |
| 23 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | Isaiah Likely + Elijah Arroyo | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 271 | 19,039 | **18,768** | killed · `gap_max` |
| 24 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | Isaiah Likely + 2028 2nd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 281 | 19,039 | **18,757** | killed · `gap_max` |
| 25 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | Isaiah Likely + Dylan Sampson | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 286 | 19,039 | **18,753** | killed · `gap_max` |
| 26 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + James Conner + MarShawn Lloyd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 303 | 19,039 | **18,736** | killed · `gap_max` |
| 27 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + James Conner + Elijah Arroyo | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 304 | 19,039 | **18,734** | killed · `gap_max` |
| 28 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + Elijah Arroyo + MarShawn Lloyd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 311 | 19,039 | **18,727** | killed · `gap_max` |
| 29 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + James Conner + 2028 2nd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 316 | 19,039 | **18,723** | killed · `gap_max` |
| 30 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + James Conner + Dylan Sampson | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 320 | 19,039 | **18,719** | killed · `gap_max` |
| 31 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + 2028 2nd + MarShawn Lloyd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 322 | 19,039 | **18,716** | killed · `gap_max` |
| 32 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + 2028 2nd + Elijah Arroyo | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 324 | 19,039 | **18,714** | killed · `gap_max` |
| 33 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + Dylan Sampson + MarShawn Lloyd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 327 | 19,039 | **18,712** | killed · `gap_max` |
| 34 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + Dylan Sampson + Elijah Arroyo | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 328 | 19,039 | **18,710** | killed · `gap_max` |
| 35 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + Dylan Sampson + 2028 2nd | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 340 | 19,039 | **18,699** | killed · `gap_max` |
| 36 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | James Conner + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 358 | 19,039 | **18,681** | killed · `gap_max` |
| 37 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | MarShawn Lloyd + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 364 | 19,039 | **18,674** | killed · `gap_max` |
| 38 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | Elijah Arroyo + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 366 | 19,039 | **18,672** | killed · `gap_max` |
| 39 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | 2028 2nd + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 377 | 19,039 | **18,662** | killed · `gap_max` |
| 40 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | Dylan Sampson + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 381 | 19,039 | **18,658** | killed · `gap_max` |
| 41 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | James Conner + MarShawn Lloyd + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 395 | 19,039 | **18,644** | killed · `gap_max` |
| 42 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | James Conner + Elijah Arroyo + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 397 | 19,039 | **18,642** | killed · `gap_max` |
| 43 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Elijah Arroyo + MarShawn Lloyd + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 404 | 19,039 | **18,635** | killed · `gap_max` |
| 44 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | James Conner + 2028 2nd + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 408 | 19,039 | **18,631** | killed · `gap_max` |
| 45 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | James Conner + Dylan Sampson + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 412 | 19,039 | **18,626** | killed · `gap_max` |
| 46 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | 2028 2nd + MarShawn Lloyd + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 415 | 19,039 | **18,624** | killed · `gap_max` |
| 47 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | 2028 2nd + Elijah Arroyo + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 417 | 19,039 | **18,622** | killed · `gap_max` |
| 48 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Dylan Sampson + MarShawn Lloyd + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 419 | 19,039 | **18,620** | killed · `gap_max` |
| 49 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Dylan Sampson + Elijah Arroyo + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 421 | 19,039 | **18,618** | killed · `gap_max` |
| 50 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Dylan Sampson + 2028 2nd + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 432 | 19,039 | **18,607** | killed · `gap_max` |
| 51 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | James Conner + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 461 | 19,039 | **18,578** | killed · `gap_max` |
| 52 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | James Conner + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 461 | 19,039 | **18,578** | killed · `gap_max` |
| 53 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | MarShawn Lloyd + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 467 | 19,039 | **18,571** | killed · `gap_max` |
| 54 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | MarShawn Lloyd + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 467 | 19,039 | **18,571** | killed · `gap_max` |
| 55 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | Elijah Arroyo + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 469 | 19,039 | **18,570** | killed · `gap_max` |
| 56 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | Elijah Arroyo + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 469 | 19,039 | **18,570** | killed · `gap_max` |
| 57 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | 2028 2nd + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 479 | 19,039 | **18,559** | killed · `gap_max` |
| 58 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | 2028 2nd + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 479 | 19,039 | **18,559** | killed · `gap_max` |
| 59 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | Dylan Sampson + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 483 | 19,039 | **18,555** | killed · `gap_max` |
| 60 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | Dylan Sampson + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 483 | 19,039 | **18,555** | killed · `gap_max` |
| 61 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | James Conner + MarShawn Lloyd + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 494 | 19,039 | **18,545** | killed · `gap_max` |
| 62 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | James Conner + MarShawn Lloyd + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 494 | 19,039 | **18,545** | killed · `gap_max` |
| 63 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | James Conner + Elijah Arroyo + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 496 | 19,039 | **18,543** | killed · `gap_max` |
| 64 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | James Conner + Elijah Arroyo + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 496 | 19,039 | **18,543** | killed · `gap_max` |
| 65 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Elijah Arroyo + MarShawn Lloyd + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 502 | 19,039 | **18,536** | killed · `gap_max` |
| 66 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Elijah Arroyo + MarShawn Lloyd + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 502 | 19,039 | **18,536** | killed · `gap_max` |
| 67 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | James Conner + 2028 2nd + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 507 | 19,039 | **18,532** | killed · `gap_max` |
| 68 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | James Conner + 2028 2nd + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 507 | 19,039 | **18,532** | killed · `gap_max` |
| 69 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | James Conner + Dylan Sampson + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 511 | 19,039 | **18,528** | killed · `gap_max` |
| 70 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | James Conner + Dylan Sampson + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 511 | 19,039 | **18,528** | killed · `gap_max` |
| 71 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | 2028 2nd + MarShawn Lloyd + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 514 | 19,039 | **18,525** | killed · `gap_max` |
| 72 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | 2028 2nd + MarShawn Lloyd + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 514 | 19,039 | **18,525** | killed · `gap_max` |
| 73 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | 2028 2nd + Elijah Arroyo + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 515 | 19,039 | **18,523** | killed · `gap_max` |
| 74 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | 2028 2nd + Elijah Arroyo + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 515 | 19,039 | **18,523** | killed · `gap_max` |
| 75 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Dylan Sampson + MarShawn Lloyd + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 518 | 19,039 | **18,521** | killed · `gap_max` |
| 76 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Dylan Sampson + MarShawn Lloyd + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 518 | 19,039 | **18,521** | killed · `gap_max` |
| 77 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Dylan Sampson + Elijah Arroyo + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 520 | 19,039 | **18,519** | killed · `gap_max` |
| 78 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Dylan Sampson + Elijah Arroyo + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 520 | 19,039 | **18,519** | killed · `gap_max` |
| 79 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Dylan Sampson + 2028 2nd + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 531 | 19,039 | **18,508** | killed · `gap_max` |
| 80 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Dylan Sampson + 2028 2nd + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 531 | 19,039 | **18,508** | killed · `gap_max` |
| 81 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | Isaiah Likely + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 538 | 19,039 | **18,501** | killed · `gap_max` |
| 82 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + James Conner + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 573 | 19,039 | **18,465** | killed · `gap_max` |
| 83 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + MarShawn Lloyd + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 580 | 19,039 | **18,458** | killed · `gap_max` |
| 84 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + Elijah Arroyo + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 582 | 19,039 | **18,456** | killed · `gap_max` |
| 85 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + 2028 2nd + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 593 | 19,039 | **18,445** | killed · `gap_max` |
| 86 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + Dylan Sampson + 2028 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 598 | 19,039 | **18,441** | killed · `gap_max` |
| 87 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | Isaiah Likely + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 638 | 19,039 | **18,400** | killed · `gap_max` |
| 88 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | Isaiah Likely + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 638 | 19,039 | **18,400** | killed · `gap_max` |
| 89 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + James Conner + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 672 | 19,039 | **18,366** | killed · `gap_max` |
| 90 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + James Conner + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 672 | 19,039 | **18,366** | killed · `gap_max` |
| 91 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + MarShawn Lloyd + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 679 | 19,039 | **18,360** | killed · `gap_max` |
| 92 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + MarShawn Lloyd + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 679 | 19,039 | **18,360** | killed · `gap_max` |
| 93 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + Elijah Arroyo + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 681 | 19,039 | **18,358** | killed · `gap_max` |
| 94 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + Elijah Arroyo + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 681 | 19,039 | **18,358** | killed · `gap_max` |
| 95 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + 2028 2nd + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 692 | 19,039 | **18,347** | killed · `gap_max` |
| 96 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + 2028 2nd + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 692 | 19,039 | **18,347** | killed · `gap_max` |
| 97 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + Dylan Sampson + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 696 | 19,039 | **18,342** | killed · `gap_max` |
| 98 | `challenger` | jonbonjourvi → mattmurf77 | 3x3 | Isaiah Likely + Dylan Sampson + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 696 | 19,039 | **18,342** | killed · `gap_max` |
| 99 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | 2028 1st + 2027 1st | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 729 | 19,039 | **18,310** | killed · `gap_max` |
| 100 | `challenger` | jonbonjourvi → mattmurf77 | 2x3 | 2028 1st + 2027 1st (from gdubs10) | Drake London + Ashton Jeanty + Jaxon Smith-Njigba | 729 | 19,039 | **18,310** | killed · `gap_max` |


---

A companion self-contained HTML view of the same data — combined and per-arm waterfalls, the value-bar tables, every emitted card and both top-100 lists — is at [`2026-08-22-knockout-waterfall-v2.html`](2026-08-22-knockout-waterfall-v2.html).

*Harness, context build and raw output live in a scratchpad `ko2/` directory and are **not** committed: they hold production rows. What is committed here is derived tables and named trades only. Branch `audit/knockout-waterfall-v2`, engine `941a36d`, `git diff origin/main -- backend/ config/ mobile/ web/` empty.*
