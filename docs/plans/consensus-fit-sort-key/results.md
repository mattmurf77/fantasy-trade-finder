# Results — consensus roster-fit sort key (`consensus_fit_weight`)

**Date:** 2026-09-02 · **Branch:** `claude/consensus-fit-sort-key` · **Scope:** [scope.md](scope.md) · **Proof:** [code-walk.md](code-walk.md) · **Harness:** [measure_consensus_fit.py](measure_consensus_fit.py) → `results-raw-f075.json` (prod, fairness pref ON), `results-raw-f050.json` (prod, pref OFF), `results-raw-f085.json` (the 2026-08-21 harness regime, for comparison)

Every number here comes from a run on this branch tip with `PYTHONHASHSEED=0`, the clock frozen (`time.monotonic` → constant, G-065), the D-159 prod bundle pinned (`filler_min_frac` 0.15, `overpay_adjusted` 0, `trade_elo_gap_max` 0, `v3_shape_max_delta` 2) and `max_per_opponent=5`. **Every baseline was run twice and was byte-identical in all 120 cells of all three sweeps** (`baseline_identical: true` in every raw row).

## TL;DR

* **Knob 0 is byte-identical to `origin/main` @ `ce3f443c`** — proven by two captured goldens (engine-quality fixture and the mirror fixture, emitted order), the arm-B goldens in `test_bakeoff_challenger.py`, the arm-A golden, and the full suite (**4508 passed, 1 skipped** on the branch; **4483 passed, 1 skipped** on clean main the same day — the delta is exactly the 25 new tests).
* **It reorders, it does not open the floor:** uncapped, `w > 0` emits the same SET of consensus cards as `w = 0` in a different order; every card at every `w` still clears `rv − gv ≥ user_gain_epsilon`.
* **The sort key decides which combos fill the per-opponent cap — not the served order.** `_generate_trades_v2` re-sorts the whole deck by composite (`trade_service.py:4951`) after generation, so the brief's "the composite never reorders anything" is true of *which* cards exist and false of their on-screen order. The knob's deck-level footprint is therefore the change in the emitted set under the cap.
* **Where it moves the deck:** a viewer whose receive pool is not already need-filtered. `mirror@u` (viewer 6 WR + 1 RB): set Jaccard 0.8, top-5 0.667 at every `w > 0` — the value sort's `uRB1 → bRB2` card (giving the user's *only* RB) is replaced by `uWR3 → aRB2` (surplus WR out, RB in). `12t_1qb@u8` (a viewer with no need position, half the 12-team league): at `w = 1.0`, +2 consensus cards, receives-from-partner-surplus 2 → 4, set Jaccard 0.6.
* **Where it does not:** the two team-0 viewpoints of the snake-drafted fixtures are a **flat null at every `w`, every arm, every threshold** (top-5 and set Jaccard 1.0). That is a fixture regime, not a knob property: team 0's `position_needs == ["RB"]` pre-filters the receive pool to RBs and the shed key already fronts the give pool, and the blend cannot reorder same-position assets above replacement (§ Limits). Said plainly rather than dressed as a null.
* **Junk guard (D-159): the sub-450 body share is unchanged — 0.0 pp — in every `B_current` cell at every `w` and every threshold.** No cell shrank the deck at `w = 0.5`.
* **Arm A is unmoved at every `w`** (its `MODEL_A_PROFILE` pin at 0.0 works — every `A_baseline` row is identical down the column), and the challenger inherits the live row as intended.
* **Recommended initial live value: `0.5`** (§ Recommendation).

## Suite

| Run | Command | Result |
|---|---|---|
| clean `origin/main` @ `ce3f443c` (this worktree before any edit) | `PYTHONHASHSEED=0 python3 -m pytest backend/tests -q -p no:cacheprovider` | **4483 passed, 1 skipped** in 307.7 s |
| branch tip | same | **4508 passed, 1 skipped** in 322.1 s (`__pycache__` cleared first) |
| new module alone | `… backend/tests/test_consensus_fit_sort_key.py` | **25 passed** in 9.2 s (three junk-guard cases drive the harness fixtures) |
| golden capture, main tree | `git archive origin/main \| tar -x -C <scratch>/main_tree; cp <test> …; cd main_tree && PYTHONHASHSEED=0 python3 -m backend.tests.test_consensus_fit_sort_key` | 174 engine-quality rows + 74 mirror rows; `diff` against the same capture on the branch: **byte-identical** |

The `test_deck_signal_v2` 3.12-skew flake did not appear in either full run.

## Sabotages (red → green, byte-copy restore, `__pycache__` cleared — G-060)

Script: a scratch `sabotage.sh` that backs up `backend/trade_service.py`, applies each edit with a `python3` string replace asserting exactly one match, clears `backend/**/__pycache__`, runs the named test(s) with `PYTHONHASHSEED=0 python3 -m pytest backend/tests/test_consensus_fit_sort_key.py -k …`, restores with `cp`, clears again, re-runs, and `cmp`s the restore against the backup.

| # | Sabotage | Target test(s) | Sabotaged | Restored |
|---|---|---|---|---|
| S1 | the blended lambda at `:7142` → `return seed_value` (fit never enters the key) | `test_knob_half_leads_with_the_mirror_swap` | **1 failed** | 1 passed |
| S2 | drop `_pos(p) in shed_positions` from the give sort (`:7154`) | `test_knob0_is_byte_identical_to_origin_main` + `test_mirror_knob0_is_byte_identical_to_origin_main` | **1 failed**, 1 passed (the mirror golden carries shed positions; the engine-quality fixture's partners have none, so it stays green — consistent with it being fit-symmetric) | 2 passed |
| S3 | stamp `consensus_fit` unconditionally (`if _w_fit > 0:` → `if True:`) | `test_knob0_never_stamps` | **1 failed** | 1 passed |
| S4 | hoist the read: `_c("consensus_fit_weight")` → `_DEFAULT_CFG["consensus_fit_weight"]` (binds the default, blind to `_cfg` and the overlay) | `test_knob_half_leads_with_the_mirror_swap` + `test_knob_is_read_at_call_time_through_the_overlay` | **1 failed**, 1 passed (the swap test dies — the knob is always 0; the overlay test trivially passes because an always-0 knob yields the knob-0 deck, which is why S1 and S4 are both needed) | 2 passed |

Every restore `cmp`'d byte-identical to the backup; `git diff --stat backend/trade_service.py` empty afterwards.

## Harness tables — prod, fairness pref ON (`fairness_threshold = 0.75`), v3 path

Columns: `deck` = all cards; `cons` = `basis == "consensus"` cards (everything else is over those); `sub-450` = cards with any traded asset priced under `asset_floor_abs`; `centres` = distinct top receive asset; `top-5 J` / `set J` = Jaccard against the same cell's `w = 0` deck (deck order); `fit` = mean `consensus_fit` stamp; `s→n give` = cards giving from a position where the viewer is at/above `_SURPLUS_AT` to a partner below `_STARTER_NEED`; `s→n recv` = the receive-side mirror; `gUS` / `rPS` = cards giving from the viewer's surplus / receiving from the partner's surplus (need on the other side not required).

**12t_1qb@u0** — viewer team 0, `position_needs = ["RB"]`, surplus `WR, TE` (the 2026-08-21 harness viewpoint)

| arm | w | deck | cons | shapes | sub-450 | share | centres | top-5 J | set J | fit | s→n give | s→n recv | gUS | rPS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B_current | 0.0 | 28 | 13 | 1x1:13 | 7 | 0.538 | 11 | 1.0 | 1.0 | — | 2 | 6 | 9 | 6 |
| B_current | 0.25 | 28 | 13 | 1x1:13 | 7 | 0.538 | 11 | 1.0 | 1.0 | 0.348 | 2 | 6 | 9 | 6 |
| B_current | 0.5 | 28 | 13 | 1x1:13 | 7 | 0.538 | 11 | 1.0 | 1.0 | 0.348 | 2 | 6 | 9 | 6 |
| B_current | 1.0 | 28 | 13 | 1x1:13 | 7 | 0.538 | 11 | 1.0 | 1.0 | 0.348 | 2 | 6 | 9 | 6 |
| A_baseline | all four | 55 | 25 | 1x1:25 | 8 | 0.32 | 16 | 1.0 | 1.0 | — | 5 | 10 | 18 | 10 |
| D_challenger | 0.0 | 28 | 10 | 1x1:10 | 4 | 0.4 | 9 | 1.0 | 1.0 | — | 1 | 4 | 6 | 4 |
| D_challenger | 0.25–1.0 | 28 | 10 | 1x1:10 | 4 | 0.4 | 9 | 1.0 | 1.0 | 0.493 | 1 | 4 | 6 | 4 |

**16t_sf@u0** — viewer team 0, needs `WR, TE`, surplus `QB`

| arm | w | deck | cons | shapes | sub-450 | share | centres | top-5 J | set J | fit | s→n give | s→n recv | gUS | rPS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B_current | 0.0 | 34 | 16 | 1x1:16 | 11 | 0.688 | 15 | 1.0 | 1.0 | — | 1 | 3 | 3 | 3 |
| B_current | 0.25–1.0 | 34 | 16 | 1x1:16 | 11 | 0.688 | 15 | 1.0 | 1.0 | 0.108 | 1 | 3 | 3 | 3 |
| A_baseline | all four | 73 | 40 | 1x1:39 2x1:1 | 11 | 0.275 | 21 | 1.0 | 1.0 | — | 5 | 14 | 12 | 14 |
| D_challenger | 0.0 | 27 | 9 | 1x1:9 | 4 | 0.444 | 7 | 1.0 | 1.0 | — | 0 | 2 | 2 | 2 |
| D_challenger | 0.25–1.0 | 27 | 9 | 1x1:9 | 4 | 0.444 | 7 | 0.667 | 0.8 | 0.233 | 0 | 1 | 2 | 1 |

**mirror@u** — viewer 6 WR + 1 RB (+QB, TE); partners `a` (6 RB + 1 WR + a 1700 QB) and `b` (balanced); nobody boarded

| arm | w | deck | cons | shapes | sub-450 | share | centres | top-5 J | set J | fit | s→n give | s→n recv | gUS | rPS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B_current | 0.0 | 9 | 9 | 1x1:9 | 0 | 0.0 | 4 | 1.0 | 1.0 | — | 4 | 5 | 6 | 5 |
| B_current | 0.25–1.0 | 9 | 9 | 1x1:9 | 0 | 0.0 | 4 | **0.667** | **0.8** | 0.611 | 4 | 5 | **7** | 5 |
| A_baseline | all four | 10 | 10 | 1x1:10 | 0 | 0.0 | 4 | 1.0 | 1.0 | — | 4 | 5 | 7 | 5 |
| D_challenger | 0.0 | 9 | 9 | 1x1:9 | 0 | 0.0 | 4 | 1.0 | 1.0 | — | 4 | 5 | 6 | 5 |
| D_challenger | 0.25–1.0 | 9 | 9 | 1x1:9 | 0 | 0.0 | 4 | 1.0 | 0.8 | 0.611 | 4 | 5 | 7 | 5 |

Top-5 (B_current): `w = 0` → `uWR1→aRB1, uWR2→aRB2, uWR1→bRB1, uWR2→bRB2, uRB1→bRB2`; `w ≥ 0.25` → the same four then **`uWR3→aRB2`** in place of `uRB1→bRB2`. The value sort was spending the viewer's only RB; the blend spends a surplus WR.

**12t_1qb@u8** — viewer team 8, **`position_needs = []`**, surplus `RB, WR` (the no-need viewer: half of this league — u1/u4/u6/u7/u8/u9/u11 — looks like this)

| arm | w | deck | cons | shapes | sub-450 | share | centres | top-5 J | set J | fit | s→n give | s→n recv | gUS | rPS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B_current | 0.0 | 20 | 7 | 1x1:7 | 0 | 0.0 | 6 | 1.0 | 1.0 | — | 2 | 0 | 3 | 2 |
| B_current | 0.25 | 19 | 6 | 1x1:6 | 0 | 0.0 | 6 | 0.667 | 0.857 | 0.326 | 2 | 0 | 3 | 2 |
| B_current | 0.5 | 20 | 7 | 1x1:7 | 0 | 0.0 | 6 | 1.0 | 1.0 | 0.336 | 2 | 0 | 3 | 2 |
| B_current | 1.0 | **22** | **9** | 1x1:9 | 0 | 0.0 | 7 | 0.667 | **0.6** | 0.372 | 3 | 0 | **5** | **4** |
| A_baseline | all four | 55 | 25 | 1x1:25 | 0 | 0.0 | 22 | 1.0 | 1.0 | — | 7 | 0 | 20 | 11 |
| D_challenger | 0.0 | 17 | 3 | 1x1:3 | 0 | 0.0 | 3 | 1.0 | 1.0 | — | 2 | 0 | 2 | 0 |
| D_challenger | 0.25 | 17 | 3 | 1x1:3 | 0 | 0.0 | 3 | 1.0 | 1.0 | 0.517 | 2 | 0 | 2 | 0 |
| D_challenger | 0.5 | 17 | 3 | 1x1:3 | 0 | 0.0 | 3 | 0.5 | 0.5 | 0.683 | 2 | 0 | 2 | 1 |
| D_challenger | 1.0 | 18 | 4 | 1x1:4 | 0 | 0.0 | 4 | 0.4 | 0.4 | 0.637 | 2 | 0 | 3 | 2 |

Note the non-monotonicity on `B_current`: `w = 0.25` and `1.0` change the emitted set, `w = 0.5` happens to reproduce the `w = 0` set exactly. The per-opponent cap is 5 and the first five passing combos are a small, discrete set — a given `w` either flips one of them or it does not. This fixture cannot therefore rank 0.5 against 0 on its own; the mirror@u deck and the unit tests are what show 0.5 moving a deck.

**mirror@b** — the balanced viewer (3 WR + 3 RB on the same rungs, `position_needs = []`)

| arm | w | deck | cons | shapes | sub-450 | share | centres | top-5 J | set J | fit | s→n give | s→n recv | gUS | rPS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B_current | all four | 8 | 8 | 1x1:8 | 0 | 0.0 | 4 | 1.0 | 1.0 | 0.312 (w>0) | 0 | 0 | 0 | 6 |
| A_baseline | all four | 10 | 10 | 1x1:10 | 0 | 0.0 | 4 | 1.0 | 1.0 | — | 0 | 0 | 0 | 8 |
| D_challenger | all four | 8 | 8 | 1x1:8 | 0 | 0.0 | 4 | 1.0 | 1.0 | 0.312 (w>0) | 0 | 0 | 0 | 6 |

Null **by construction of this fixture**, and the reason is a property of the signal worth knowing (§ Limits): `b`'s RB3 and `a`'s RB3 sit on the same 1590 rung, so both rosters have the *same* RB replacement level and the marginal-value asymmetry on every one of `a`'s RBs is exactly 0 — the `consensus_fit` stamps on the probe read 0.5 = give side 1.0 (b's WRs vs a's one WR) + receive side 0.0. The value sort's lead card `bWR1 → aQB` (a's lone 1700 QB into a roster that already starts one) survives at every `w` because both sides have one QB, so its asymmetry is 0 too.

## Harness tables — prod, fairness pref OFF (`fairness_threshold = 0.50`), v3 path, `B_current` only

| league | w | deck | cons | sub-450 | share | centres | top-5 J | set J | fit | s→n give | s→n recv | gUS | rPS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 12t_1qb@u0 | 0.0 | 28 | 13 | 5 | 0.385 | 11 | 1.0 | 1.0 | — | 1 | 6 | 9 | 6 |
| 12t_1qb@u0 | 0.25–1.0 | 28 | 13 | 5 | 0.385 | 11 | 1.0 | 1.0 | 0.423 | 1 | 6 | 9 | 6 |
| 16t_sf@u0 | 0.0 | 32 | 14 | 9 | 0.643 | 11 | 1.0 | 1.0 | — | 0 | 1 | 2 | 1 |
| 16t_sf@u0 | 0.25–1.0 | 32 | 14 | 9 | 0.643 | 11 | 1.0 | 1.0 | 0.147 | 0 | 1 | 2 | 1 |
| mirror@u | 0.0 | 9 | 9 | 0 | 0.0 | 4 | 1.0 | 1.0 | — | 4 | 5 | 6 | 5 |
| mirror@u | 0.25–1.0 | 9 | 9 | 0 | 0.0 | 4 | 0.667 | 0.8 | 0.611 | 4 | 5 | 7 | 5 |
| 12t_1qb@u8 | 0.0 | 20 | 7 | 0 | 0.0 | 6 | 1.0 | 1.0 | — | 3 | 0 | 3 | 2 |
| 12t_1qb@u8 | 0.25 | 19 | 6 | 0 | 0.0 | 6 | 0.667 | 0.857 | 0.341 | 3 | 0 | 3 | 2 |
| 12t_1qb@u8 | 0.5 | 20 | 7 | 0 | 0.0 | 6 | 1.0 | 1.0 | 0.349 | 3 | 0 | 3 | 2 |
| 12t_1qb@u8 | 1.0 | 22 | 9 | 0 | 0.0 | 7 | 0.667 | 0.6 | 0.382 | 4 | 0 | 5 | 4 |
| mirror@b | all four | 8 | 8 | 0 | 0.0 | 4 | 1.0 | 1.0 | 0.312 (w>0) | 0 | 0 | 0 | 6 |

Same shape as 0.75; arms A and D as in `results-raw-f050.json`. The `v2_only` path (`trade_engine.v3` off) is in the raw files for both thresholds and tells the same story.

## Harness tables — the 2026-08-21 regime (`fairness_threshold = 0.85`), for comparison

At 0.85 (the threshold the copied harness hardcoded, which prod never sends) every `B_current` cell but one is a flat null; the exception is again `12t_1qb@u8` (set J 0.667 at `w = 0.5`, 0.615 at `1.0`, rPS 4 → 5 → 6). The mirror@u movement above does **not** appear at 0.85 because the card the blend displaces (`uRB1 → bRB2`, fairness 0.905) and its replacement are both gated differently there. Full rows in `results-raw-f085.json`. Lesson recorded in the harness docstring: the threshold is a load-bearing input and the sweep is run at the two values prod actually sends.

## Per-pair probe (why the deck-level numbers look the way they do)

`_generate_consensus_for_pair` called directly on the `12t_1qb@u0` league, five unboarded partners, prod pins, frozen clock, `PYTHONHASHSEED=0`, at `w = 0` vs `w = 0.5`:

| partner | needs / surplus | thr | uncapped n | same SET | same ORDER | cap 5 overlap | cap 8 overlap |
|---|---|---|---|---|---|---|---|
| u2 | WR / RB,TE | 0.85 | 12 | yes | **no** | 5/5 | 8/8 |
| u2 | | 0.50 | 83 | yes | **no** | 5/5 | 8/8 |
| u4 | — / QB | 0.85 | 19 | **no** | **no** | 5/5 | 8/8 |
| u4 | | 0.50 | 95 | **no** | **no** | 5/5 (first give changes: `11604` → `5859`) | 8/8 |
| u6 | — / WR | 0.85 | 14 | yes | yes | 5/5 | 8/8 |
| u6 | | 0.50 | 52 | **no** | **no** | **4/5** | 8/8 |
| u8 | — / RB,WR | 0.85 | 11 | yes | yes | 5/5 | 8/8 |
| u8 | | 0.50 | 57 | **no** | **no** | 5/5 | 8/8 |
| u10 | WR / QB,TE | 0.85 | 20 | yes | **no** | **4/5** | 8/8 |
| u10 | | 0.50 | 85 | **no** | **no** | 5/5 | 8/8 |

Reading: the sort key reorders emission in almost every pairing (and, uncapped, changes the set in some — the gap-sweetener's `seen` dedupe is order-dependent), but the first 5–8 passing combos are the same combos in a different order when the viewer has a need position: the receive pool is already filtered to that position (`:7098`) and the give pool is already shed-keyed, so the top of both pools is stable under the blend. The deck then re-sorts by composite (`:4951`), which erases the within-pair order.

## Limits of the signal (inherited, not introduced)

`marginal_value` = `max(0, v − replacement) + bench_credit × v`, with `replacement` = the value of the roster's `(starters + 1)`-th player at the position (`replacement_levels`, `:3078`), or `waiver_baseline_value` (250) when the roster has fewer than that. Consequences for the asymmetry `marg(partner) − marg(user)`:

1. **Every asset above both replacement levels at a position has the same asymmetry** (`user_repl − opp_repl`), so the blend cannot reorder a position's starters among themselves — it moves positions relative to each other and starters relative to bench. That is why the need-filtered viewpoints are null: a single-position receive pool sorted by value is left alone.
2. **Depth beyond `starters + 1` is invisible.** A roster with 3 RBs and one with 6 RBs whose RB3s are equal have identical RB replacement and zero asymmetry (the `mirror@b` null). The signal fires when one side is *thin* (below `starters + 1` → waiver baseline) or when the `(starters + 1)`-th players differ in value — the 6 WR + 1 RB roster, the `u8` viewer's partners.
3. At `w = 1.0` an asset with `fit_norm = −1` gets sort key 0 — it sorts below every pick and every bench body regardless of value. That is a de-facto prune of the worst-fit asset, which is the design the lead rejected; at `w = 0.5` the multiplier band is `[0.5, 1.5]` and nothing is ever zeroed.

## Recommendation — initial live value **0.5**

Evidence line: *0.5 is the largest `w` at which the sort multiplier stays strictly positive (band `[0.5, 1.5]`, no de-facto prune — at 1.0 a full-negative-fit asset keys to 0); the D-159 junk share is unchanged (0.0 pp) in every `B_current` cell at every threshold; top-5 Jaccard is 1.0 on both standard fixtures and ≥ 0.667 in every cell that moves; the unit-test mirror leads with `uWR1 → oRB1` at 0.5 (and with the partner's lone QB at 0); the harness mirror deck already moves at 0.25 (set J 0.8, the lone-RB card replaced by a surplus-WR card) and holds that at 0.5.*

What 0.5 does **not** have: a deck-level delta on the snake-drafted fixture from any viewpoint — at 0.5 `12t_1qb@u8` happens to reproduce its `w = 0` set exactly (0.25 and 1.0 move it). The brief's "≥ ~0.7 top-5 Jaccard on the standard fixture" bound therefore never binds, and the number is chosen by the multiplier-band argument plus the mirror evidence, not by a dose-response curve on the standard fixture — there is none to read. Rollback is `PUT /api/admin/config/consensus_fit_weight` → `0` (deploy-free).

## After the flip — how the lead can verify in prod

The harness cannot replay prod boards, so the runtime check is a targeted one. Pick a league and a viewer with these properties (both readable from `analyze_roster_strengths` on the viewer's roster — the profile the job already computes):

1. **Viewer with `position_needs == []`** (a legal startable lineup — the u8 shape) and at least one unboarded partner (`has_rankings == false`) who is **thin at a position the viewer is deep at** (partner has fewer than `starters + 1` startable there, viewer has ≥ `_SURPLUS_AT`). Before the flip, that partner's consensus cards lead with whatever their single most valuable asset is; after, they should lead with the asset from the partner's *deepest* position and the give side should draw from the viewer's surplus position. Concretely: a WR-deep viewer vs an RB-deep, WR-thin partner should see RB-in / WR-out cards fill that partner's consensus slots.
2. **Viewer with exactly one startable player at a position** (the mirror@u shape — `uRB1`): before the flip, the value sort can spend that player; after, cards giving him should drop out of the served deck in favour of surplus-position gives. A `GET /api/trades` deck diff before/after the PUT on the same league (same `fairness_threshold`, job cache invalidated by the config change or forced) is the evidence.
3. **Guardrails to read from the corpus after a week**, split by `basis == "consensus"` as D-095's C2 prescribes: sub-450 share of consensus impressions (expect flat), consensus like rate (the hypothesis is up, on the strength of #96/#304 feedback), and `receive_positions` mix vs `give_positions` on consensus rows for viewers with no need position.

## Ledger draft (for the lead — `living-memory/TEST_LEDGER.md`)

> **2026-09-02 — consensus roster-fit sort key (`consensus_fit_weight`), branch `claude/consensus-fit-sort-key`.** `pytest backend/tests`: 4508 passed, 1 skipped (clean `origin/main` @ `ce3f443c` baseline the same day: 4483 passed, 1 skipped). New `backend/tests/test_consensus_fit_sort_key.py` (25): goldens for the consensus generator on the engine-quality fixture and the mirror fixture captured on a `git archive origin/main` tree, byte-identical at the default; mirror fixture leads with `uWR1 → oQB` at w = 0 and `uWR1 → oRB1` at w = 0.5; sign test holds on every card at every w; picks neutral; call-time read through the overlay; both config stores agree; D-159 junk guard on three harness fixtures. Four sabotages red → green (S1 blend removed, S2 shed key dropped, S3 unconditional stamp, S4 import-time read). Harness `docs/plans/consensus-fit-sort-key/measure_consensus_fit.py` (prod pins, frozen clock, `PYTHONHASHSEED=0`, baseline run twice and byte-identical in all 120 cells × 3 thresholds): sub-450 share unchanged (0 pp) in every live-arm cell; team-0 viewpoints of the snake-drafted fixtures null at every w (need-filtered pools); mirror viewer set-Jaccard 0.8 from w = 0.25 (lone-RB give replaced by surplus-WR give); no-need viewer +2 consensus cards and partner-surplus receives 2 → 4 at w = 1.0; arm A unmoved at every w (pin honoured). Recommended live value 0.5. No mobile/web change; `tsc`/testid-lint untouched. Full gates; no express.
