# Results — below-market card reason (`reason_below_market_frac`)

**Date:** 2026-09-02 · **Branch:** `claude/below-market-reason` · **Scope:** [scope.md](scope.md) · **Proof:** [code-walk.md](code-walk.md) · **Harness:** [measure_below_market.py](measure_below_market.py) → `results-raw-f075.json` (prod, fairness pref ON), `results-raw-f050.json` (pref OFF)

Every number here comes from a run on this branch tip with `PYTHONHASHSEED=0`, the clock frozen (`time.monotonic` → constant, G-065), the D-159 prod bundle pinned (`filler_min_frac` 0.15, `overpay_adjusted` 0, `trade_elo_gap_max` 0, `v3_shape_max_delta` 2) plus the D-172 live value (`consensus_fit_weight` 0.5), `max_per_opponent=5`, live flags (v2 + v3 on, bake-off off). **Every baseline was run twice and was byte-identical in every cell**, and **every sweep deck was fingerprint-identical to its baseline** (`deck_invariant: true` in every raw row) — the knob moved no card anywhere in the harness, which is the property the unit tests pin.

## TL;DR

* **Knob 0 is byte-identical to `origin/main` @ `02d2eac2`** — the FULL `generate_trades` deck on the engine-quality fixture, through `trade_card_to_dict` with `trade_math.human_explanations` ON (the prod posture), captured on a `git archive origin/main` tree and `cmp`'d against the same capture on the branch (8 cards, sha256 of the captured line `8ad11872083c4ae4…`). Pinned by `test_wire_at_knob_zero_is_byte_identical_to_origin_main`; the same fixture is shown to MOVE at 0.15 (non-vacuity).
* **It is presentation only.** At 0.15 / 0.5 / 1.0 vs 0, every card attribute except `reasons` is identical, in order, in count — on the engine-quality fixture and on 100 random leagues under the live flag set (v3, presentment rules, need fit, lanes, …). The harness confirms it on every cell (`deck_invariant: true`).
* **The line fires on the gap the engine priced, not the raw one.** Through the real generator: a user with zero comparisons (`confidence = {}`, the job thread's shape for a no-board user) never fires even with a raw 23% gap; `n = 1` shrinks that gap to ~5% (silent at 0.15); `n = 10,000` fires on every hub-give card. Sabotage S1 (raw board) turns the zero-comparison test red.
* **Headliner only, players only.** The line names the C4b `deck_give_headliner` (the player the give-headliner cap keys on); a below-market filler piece never fires; a pick never headlines a mixed give side; a picks-only give side never fires. Sabotage S2 (fire on any give player) turns the headliner test red.
* **The wire gate holds.** Flag OFF ⇒ no `reasons` key on any card at any knob value; sabotage S3 (drop the gate) turns that test red.
* **Recommended initial live value: `0.15`** (§ Recommendation) — with the harness share table below as the evidence line.

## Suite

| Run | Command | Result |
|---|---|---|
| clean `origin/main` @ `02d2eac2` (`git archive` scratch tree, no new file) | `PYTHONHASHSEED=0 python3 -m pytest backend/tests -q -p no:cacheprovider` | **SUITE_MAIN** |
| branch tip | same | **SUITE_BRANCH** |
| new module alone | `… backend/tests/test_below_market_reason.py` | **23 passed** in 29.0 s (the 100-league property test is 23 s of it) |
| golden capture, main tree | `git archive origin/main \| tar -x -C <scratch>/main_tree; cp <test> …; cd main_tree && PYTHONHASHSEED=0 python3 -m backend.tests.test_below_market_reason` | 8 cards; the branch's own capture `cmp`'d **byte-identical** |
| the three goldens this knob could have disturbed | `pytest backend/tests/test_bakeoff_arm_a_golden.py backend/tests/test_engine_quality_golden.py backend/tests/test_consensus_fit_sort_key.py` | **39 passed** — arm-A golden, engine-quality golden and the D-172 goldens all stand un-recaptured |

## Sabotages (red → green, byte-copy restore, `__pycache__` cleared — G-060)

Script: a scratch `sabotage.py` that backs up the source file, applies one exact-match edit (asserting exactly one match), clears `backend/**/__pycache__`, runs the named test with `PYTHONHASHSEED=0 python3 -m pytest backend/tests/test_below_market_reason.py -k …`, restores by byte copy, clears again, `filecmp`s the restore against the backup, and re-runs.

| # | Sabotage | Target test | Sabotaged | Restored |
|---|---|---|---|---|
| S1 | stamp site reads the RAW board: `shrunk_elo` → `user_elo` in the `below_market_reason(...)` call (`trade_service.py:6531`) | `test_zero_comparisons_never_fires` | **1 failed** | 1 passed |
| S2 | fire on ANY give-side player: replace `deck_give_headliner(...)` in the helper with "the give player with the largest gap" | `test_second_give_player_below_market_but_not_headliner_is_silent` | **1 failed** | 1 passed |
| S3 | drop the wire gate: `if _FLAGS.trade_math_human_explanations:` → `if True:` in `trade_card_to_dict` (`server.py:11890`) | `test_wire_flag_off_never_carries_the_reason` | **1 failed** | 1 passed |

Every restore `filecmp`'d byte-identical to the backup; `git diff --stat` afterwards shows only the intended change set.

## What the knob means in Elo

Both sides of the gap go through `elo_to_value` (`value = 1000·e^{0.005·(elo − 1500)}`), so a fixed fraction of consensus value is a fixed Elo distance below seed **on the shrunk board**: `Δelo = ln(1/(1 − frac)) / 0.005`.

| `frac` | shrunk Elo below seed | roughly what it takes on a board with `shrink_pseudocount` 4, `elo_k` 32 |
|---|---|---|
| 0.05 | 10.3 | one or two "he's worse" votes on a lightly-sampled player — rounding noise |
| 0.10 | 21.1 | ≈ three consistent down-votes (`n = 3`: `w = 0.43`, raw drift ≈ 3 × 16) |
| **0.15** | **32.5** | ≈ four consistent down-votes (`n = 4`: `w = 0.5`, raw drift ≈ 4 × 16) — a held opinion |
| 0.25 | 57.5 | ≈ six, or a placement a tier down |
| 0.35 | 86.2 | a deliberately-placed tier gap |

(The "votes" column is an approximation — an Elo loss against an equal-rated opponent moves ~`K/2` = 16, the shrink weight is `n/(n+4)`, and matchups are 3-player — it is here to make the threshold legible, not as a model.) Below ~0.10 the line would fire on a player the user has barely touched; that is the "rounding noise" band.

## Harness — share of served cards carrying the line

Columns: `deck` = cards served; `carry` = cards carrying the line at that `frac` (count · share); `div` / `cons` = the same split by basis; `gap hist` = the knob-independent distribution of the give-headliner's shrunk gap over the served cards (`<0` = user above market, `—` = picks-only give side). Board models: **binary** = the D-172 fixture boards (40% of players offset by exactly ±120 Elo — a −120 offset is a 45% value gap, so the share is a step function of `frac` and cannot grade a threshold); **graded** = the same hash draws a uniform offset in [−200, +200] Elo (continuous gaps, the share falls with `frac`). `shrunk` = the viewer has hash-drawn comparison counts in {0,1,2,4,8,16} so the stamp reads a genuinely shrunk board; `raw` = no counts (`confidence=None`, the raw board — what the D-172 harness passed).

**`fairness_threshold = 0.75`** (`results-raw-f075.json`; 252 cells, every one `baseline_identical` and `deck_invariant`)

| league · board · viewer board | deck | picks-only give | above mkt | gap hist (knob-independent) | @0.05 | @0.10 | @0.15 | @0.25 | @0.35 | div / cons @0.15 |
|---|---|---|---|---|---|---|---|---|---|---|
| 12t_1qb@u0 · binary · shrunk | 30 | 2 | 4 | 0.00–0.05:13 · 0.10–0.15:3 · 0.15–0.25:3 · 0.25–0.35:5 | 11 (0.37) | 11 (0.37) | 8 (0.27) | 5 (0.17) | 0 (0.00) | 5/17 / 3/13 |
| 12t_1qb@u0 · binary · raw | 28 | 2 | 2 | 0.00–0.05:14 · 0.35–0.50:10 | 10 (0.36) | 10 (0.36) | 10 (0.36) | 10 (0.36) | 10 (0.36) | 7/15 / 3/13 |
| 12t_1qb@u0 · graded · shrunk | 31 | 3 | 6 | 0.00–0.05:6 · 0.05–0.10:2 · 0.15–0.25:9 · 0.25–0.35:2 · 0.35–0.50:3 | 16 (0.52) | 14 (0.45) | 14 (0.45) | 5 (0.16) | 3 (0.10) | 9/17 / 5/14 |
| 12t_1qb@u0 · graded · raw | 27 | 2 | 6 | 0.15–0.25:3 · 0.25–0.35:3 · 0.35–0.50:3 · 0.50–1.01:10 | 19 (0.70) | 19 (0.70) | 19 (0.70) | 16 (0.59) | 13 (0.48) | 7/13 / 12/14 |
| 16t_sf@u0 · binary · shrunk | 35 | 6 | 5 | 0.00–0.05:17 · 0.15–0.25:5 · 0.25–0.35:2 | 7 (0.20) | 7 (0.20) | 7 (0.20) | 2 (0.06) | 0 (0.00) | 3/17 / 4/18 |
| 16t_sf@u0 · binary · raw | 34 | 6 | 2 | 0.00–0.05:18 · 0.35–0.50:8 | 8 (0.24) | 8 (0.24) | 8 (0.24) | 8 (0.24) | 8 (0.24) | 4/18 / 4/16 |
| 16t_sf@u0 · graded · shrunk | 42 | 6 | 15 | 0.10–0.15:1 · 0.15–0.25:6 · 0.25–0.35:13 · 0.35–0.50:1 | 21 (0.50) | 21 (0.50) | 20 (0.48) | 14 (0.33) | 1 (0.02) | 6/19 / 14/23 |
| 16t_sf@u0 · graded · raw | 35 | 6 | 8 | 0.25–0.35:3 · 0.35–0.50:4 · 0.50–1.01:14 | 21 (0.60) | 21 (0.60) | 21 (0.60) | 21 (0.60) | 18 (0.51) | 6/13 / 15/22 |
| mirror@u · binary · shrunk | 9 | 0 | 0 | 0.00–0.05:9 | 0 (0.00) | 0 (0.00) | 0 (0.00) | 0 (0.00) | 0 (0.00) | 0/9 |
| mirror@u · binary · raw | 9 | 0 | 0 | 0.00–0.05:9 | 0 (0.00) | 0 (0.00) | 0 (0.00) | 0 (0.00) | 0 (0.00) | 0/9 |
| 12t_1qb@u8 · binary · shrunk | 19 | 3 | 2 | 0.00–0.05:11 · 0.10–0.15:3 | 3 (0.16) | 3 (0.16) | 0 (0.00) | 0 (0.00) | 0 (0.00) | 0/9 / 0/10 |
| 12t_1qb@u8 · binary · raw | 20 | 3 | 3 | 0.00–0.05:11 · 0.35–0.50:3 | 3 (0.15) | 3 (0.15) | 3 (0.15) | 3 (0.15) | 3 (0.15) | 3/13 / 0/7 |
| 12t_1qb@u8 · graded · shrunk | 21 | 6 | 3 | 0.00–0.05:3 · 0.10–0.15:3 · 0.25–0.35:3 · 0.35–0.50:3 | 9 (0.43) | 9 (0.43) | 6 (0.29) | 6 (0.29) | 3 (0.14) | 6/14 / 0/7 |
| 12t_1qb@u8 · graded · raw | 24 | 6 | 6 | 0.35–0.50:3 · 0.50–1.01:9 | 12 (0.50) | 12 (0.50) | 12 (0.50) | 12 (0.50) | 12 (0.50) | 12/18 / 0/6 |

Pooled share of served cards carrying the line, by arm and board model:

| arm | board · viewer board | @0.05 | @0.10 | @0.15 | @0.25 | @0.35 |
|---|---|---|---|---|---|---|
| B_current | binary · shrunk | 21/93 = 0.23 | 21/93 = 0.23 | 15/93 = **0.16** | 7/93 = 0.08 | 0/93 = 0.00 |
| B_current | binary · raw | 21/91 = 0.23 | 21/91 = 0.23 | 21/91 = **0.23** | 21/91 = 0.23 | 21/91 = 0.23 |
| B_current | graded · shrunk | 46/94 = 0.49 | 44/94 = 0.47 | 40/94 = **0.43** | 25/94 = 0.27 | 7/94 = 0.07 |
| B_current | graded · raw | 52/86 = 0.60 | 52/86 = 0.60 | 52/86 = **0.60** | 49/86 = 0.57 | 43/86 = 0.50 |
| A_baseline | binary · shrunk | 64/189 = 0.34 | 64/189 = 0.34 | 26/189 = **0.14** | 7/189 = 0.04 | 0/189 = 0.00 |
| A_baseline | binary · raw | 56/193 = 0.29 | 56/193 = 0.29 | 56/193 = **0.29** | 56/193 = 0.29 | 56/193 = 0.29 |
| A_baseline | graded · shrunk | 106/185 = 0.57 | 105/185 = 0.57 | 94/185 = **0.51** | 74/185 = 0.40 | 32/185 = 0.17 |
| A_baseline | graded · raw | 138/185 = 0.75 | 138/185 = 0.75 | 138/185 = **0.75** | 133/185 = 0.72 | 126/185 = 0.68 |
| D_challenger | binary · shrunk | 21/80 = 0.26 | 21/80 = 0.26 | 21/80 = **0.26** | 21/80 = 0.26 | 21/80 = 0.26 |
| D_challenger | binary · raw | 20/81 = 0.25 | 20/81 = 0.25 | 20/81 = **0.25** | 20/81 = 0.25 | 20/81 = 0.25 |
| D_challenger | graded · shrunk | 45/82 = 0.55 | 45/82 = 0.55 | 45/82 = **0.55** | 41/82 = 0.50 | 33/82 = 0.40 |
| D_challenger | graded · raw | 42/73 = 0.58 | 42/73 = 0.58 | 42/73 = **0.58** | 38/73 = 0.52 | 32/73 = 0.44 |

**`fairness_threshold = 0.5`** (`results-raw-f050.json`; 252 cells, every one `baseline_identical` and `deck_invariant`)

| league · board · viewer board | deck | picks-only give | above mkt | gap hist (knob-independent) | @0.05 | @0.10 | @0.15 | @0.25 | @0.35 | div / cons @0.15 |
|---|---|---|---|---|---|---|---|---|---|---|
| 12t_1qb@u0 · binary · shrunk | 29 | 2 | 4 | 0.00–0.05:12 · 0.10–0.15:3 · 0.15–0.25:3 · 0.25–0.35:5 | 11 (0.38) | 11 (0.38) | 8 (0.28) | 5 (0.17) | 0 (0.00) | 5/17 / 3/12 |
| 12t_1qb@u0 · binary · raw | 28 | 2 | 2 | 0.00–0.05:13 · 0.35–0.50:11 | 11 (0.39) | 11 (0.39) | 11 (0.39) | 11 (0.39) | 11 (0.39) | 7/15 / 4/13 |
| 12t_1qb@u0 · graded · shrunk | 31 | 3 | 7 | 0.00–0.05:3 · 0.05–0.10:3 · 0.15–0.25:8 · 0.25–0.35:4 · 0.35–0.50:3 | 18 (0.58) | 15 (0.48) | 15 (0.48) | 7 (0.23) | 3 (0.10) | 9/17 / 6/14 |
| 12t_1qb@u0 · graded · raw | 27 | 2 | 7 | 0.15–0.25:3 · 0.25–0.35:3 · 0.35–0.50:3 · 0.50–1.01:9 | 18 (0.67) | 18 (0.67) | 18 (0.67) | 15 (0.56) | 12 (0.44) | 7/13 / 11/14 |
| 16t_sf@u0 · binary · shrunk | 32 | 6 | 7 | 0.00–0.05:12 · 0.15–0.25:4 · 0.25–0.35:3 | 7 (0.22) | 7 (0.22) | 7 (0.22) | 3 (0.09) | 0 (0.00) | 3/17 / 4/15 |
| 16t_sf@u0 · binary · raw | 32 | 6 | 5 | 0.00–0.05:14 · 0.35–0.50:7 | 7 (0.22) | 7 (0.22) | 7 (0.22) | 7 (0.22) | 7 (0.22) | 4/18 / 3/14 |
| 16t_sf@u0 · graded · shrunk | 40 | 7 | 18 | 0.15–0.25:3 · 0.25–0.35:11 · 0.35–0.50:1 | 15 (0.38) | 15 (0.38) | 15 (0.38) | 12 (0.30) | 1 (0.03) | 6/19 / 9/21 |
| 16t_sf@u0 · graded · raw | 34 | 7 | 12 | 0.25–0.35:3 · 0.35–0.50:1 · 0.50–1.01:11 | 15 (0.44) | 15 (0.44) | 15 (0.44) | 15 (0.44) | 12 (0.35) | 6/13 / 9/21 |
| mirror@u · binary · shrunk | 9 | 0 | 0 | 0.00–0.05:9 | 0 (0.00) | 0 (0.00) | 0 (0.00) | 0 (0.00) | 0 (0.00) | 0/9 |
| mirror@u · binary · raw | 9 | 0 | 0 | 0.00–0.05:9 | 0 (0.00) | 0 (0.00) | 0 (0.00) | 0 (0.00) | 0 (0.00) | 0/9 |
| 12t_1qb@u8 · binary · shrunk | 20 | 3 | 2 | 0.00–0.05:12 · 0.10–0.15:3 | 3 (0.15) | 3 (0.15) | 0 (0.00) | 0 (0.00) | 0 (0.00) | 0/9 / 0/11 |
| 12t_1qb@u8 · binary · raw | 20 | 3 | 3 | 0.00–0.05:11 · 0.35–0.50:3 | 3 (0.15) | 3 (0.15) | 3 (0.15) | 3 (0.15) | 3 (0.15) | 3/13 / 0/7 |
| 12t_1qb@u8 · graded · shrunk | 21 | 6 | 3 | 0.00–0.05:3 · 0.10–0.15:3 · 0.25–0.35:3 · 0.35–0.50:3 | 9 (0.43) | 9 (0.43) | 6 (0.29) | 6 (0.29) | 3 (0.14) | 6/14 / 0/7 |
| 12t_1qb@u8 · graded · raw | 24 | 6 | 6 | 0.35–0.50:3 · 0.50–1.01:9 | 12 (0.50) | 12 (0.50) | 12 (0.50) | 12 (0.50) | 12 (0.50) | 12/18 / 0/6 |

Pooled share of served cards carrying the line, by arm and board model:

| arm | board · viewer board | @0.05 | @0.10 | @0.15 | @0.25 | @0.35 |
|---|---|---|---|---|---|---|
| B_current | binary · shrunk | 21/90 = 0.23 | 21/90 = 0.23 | 15/90 = **0.17** | 8/90 = 0.09 | 0/90 = 0.00 |
| B_current | binary · raw | 21/89 = 0.24 | 21/89 = 0.24 | 21/89 = **0.24** | 21/89 = 0.24 | 21/89 = 0.24 |
| B_current | graded · shrunk | 42/92 = 0.46 | 39/92 = 0.42 | 36/92 = **0.39** | 25/92 = 0.27 | 7/92 = 0.08 |
| B_current | graded · raw | 45/85 = 0.53 | 45/85 = 0.53 | 45/85 = **0.53** | 42/85 = 0.49 | 36/85 = 0.42 |
| A_baseline | binary · shrunk | 66/190 = 0.35 | 66/190 = 0.35 | 23/190 = **0.12** | 5/190 = 0.03 | 0/190 = 0.00 |
| A_baseline | binary · raw | 58/193 = 0.30 | 58/193 = 0.30 | 58/193 = **0.30** | 58/193 = 0.30 | 58/193 = 0.30 |
| A_baseline | graded · shrunk | 106/185 = 0.57 | 103/185 = 0.56 | 91/185 = **0.49** | 70/185 = 0.38 | 36/185 = 0.19 |
| A_baseline | graded · raw | 129/185 = 0.70 | 129/185 = 0.70 | 129/185 = **0.70** | 129/185 = 0.70 | 118/185 = 0.64 |
| D_challenger | binary · shrunk | 21/80 = 0.26 | 21/80 = 0.26 | 21/80 = **0.26** | 21/80 = 0.26 | 21/80 = 0.26 |
| D_challenger | binary · raw | 20/81 = 0.25 | 20/81 = 0.25 | 20/81 = **0.25** | 20/81 = 0.25 | 20/81 = 0.25 |
| D_challenger | graded · shrunk | 45/82 = 0.55 | 45/82 = 0.55 | 45/82 = **0.55** | 41/82 = 0.50 | 33/82 = 0.40 |
| D_challenger | graded · raw | 42/73 = 0.58 | 42/73 = 0.58 | 42/73 = **0.58** | 38/73 = 0.52 | 32/73 = 0.44 |

**Reading the tables.**

* **The knob never moved a deck** — 504 cells, every one `deck_invariant` (fingerprint of ids/target/composite/fairness/basis identical to the same cell's knob-0 deck). That is the harness-side confirmation of the unit-test property.
* **The share is a property of the BOARD, not the deck.** The mirror viewer, whose board IS the seed, carries the line on 0 of 9 cards at every knob (the null cell). The two board models are deliberately noisy — 40% of players ±120 Elo, or every player uniform ±200 — far noisier than a real shrunk board, so every share here is an **upper bound** on prod.
* **The binary board is the step function the docstring predicted:** raw (`none`), the share is flat across the whole sweep (0.23–0.24 pooled) because a −120 offset is a 45% value gap and every knob under 0.45 catches the same cards. Only the SHRUNK binary board grades: pooled B_current 0.23 at 0.05/0.10 → **0.16–0.17 at 0.15** → 0.08–0.09 at 0.25 → 0.00 at 0.35. The cards that drop out between 0.10 and 0.15 are exactly the `[0.10, 0.15)` histogram band — the lightly-sampled offsets (`n` ∈ {1, 2}: a −120 raw gap shrunk to 21–32 Elo). Those are the "rounding-noise" fires; 0.15 is the first sweep value that excludes them. On the no-need viewer (`12t_1qb@u8`) they are the ONLY fires: 3/20 at 0.10, 0/20 at 0.15.
* **The graded board grades smoothly:** pooled B_current 0.46–0.49 → 0.42–0.47 → **0.39–0.43 at 0.15** → 0.27 at 0.25 → 0.07–0.08 at 0.35. Under a board where every single player is offset by up to ±200 Elo, roughly two cards in five carry the line at 0.15 — the ceiling case, not the expected one.
* **Arm D is flat across the sweep on every board** because `MODEL_CHALLENGER_PROFILE` pins `user_elo_shrink` at 0 (D-095), so `_shrink_user_elo` returns the raw board and the line measures the raw gap there — consistent with what that arm prices with (code-walk §4). Arm A inherits the live row and grades like B (the EXCLUDED disposition, working as intended).
* **Both thresholds tell the same story** — 0.75 and 0.50 differ by a card or two per cell; the share bands are the same.

## Recommendation — initial live value **0.15**

Evidence line: *On the shrunk binary board (the D-172 fixture boards with comparison counts, the closest the harness gets to prod's shrink mechanics) the live arm carries the line on **15 of 93 served cards (0.16) at 0.15** — versus 21/93 (0.23) at 0.10, where the extra six are all in the `[0.10, 0.15)` band (lightly-sampled −120 offsets shrunk to 21–32 Elo: the rounding-noise fires), and 7/93 (0.08) at 0.25, where a held 33–57-Elo opinion is already silent; on the deliberately noisier graded board 0.15 gives 40/94 (0.43), the ceiling case; the mirror viewer (board == seed) carries it on 0/9 at every value; all 504 cells `deck_invariant`. 0.15 is a 32.5-Elo held opinion on the shrunk board (≈ four consistent down-votes on a player, or one comparison-backed tier disagreement), the first sweep value above the 0.05–0.10 band where one or two votes on a lightly-sampled player would already fire the line — and since no deck output moves at any value, the only cost of the value is how often the line appears: about one card in six on a realistic board.*

If prod shows the line on more than ~40% of served cards for a typical boarded user (the graded-board ceiling), raise to 0.25 with the same PUT; if the operator's own Adams cards do not carry it (After the flip § 2), lower to 0.10.

Rollback is `PUT /api/admin/config/reason_below_market_frac` → `0` (deploy-free), and `trade_math.human_explanations` → `false` via `POST /api/feature-flags/reload` is an independent second lever.

## After the flip — how the lead can verify in prod

1. **Deploy lands the row:** `GET /api/admin/config` (with `CRON_SECRET` from `secrets.local.env`) shows `reason_below_market_frac: 0.0`. Then `PUT /api/admin/config/reason_below_market_frac` → `0.15`. Log the timestamp.
2. **The operator's own deck.** Regenerate mattmurf77's deck in league `1312140920132497408` (the #350 league). Every card whose give side headlines **Davante Adams** must carry `reasons: ["You rank Davante Adams below the market — that gap is what this trade cashes in."]` — on both bases — and cards whose give headliner is a player he rates at or above the market must carry no `reasons` key at all. If NO Adams-give card carries it, the operator's shrunk gap on Adams is under 0.15 (his raw board is "well below consensus" per Q-035, but shrinkage weights by comparison count): read his `comparison_counts` for Adams and his personal vs seed Elo and compute `1 − e^{0.005·(shrunk − seed)}`; if it sits in [0.10, 0.15) the right move is 0.10, not doubt about the feature.
3. **The mobile render.** On TestFlight the line renders in the bordered `styles.reasons` box under the value bar, one `Text` per reason, no truncation (`TradeCard.tsx:955-961`) — one line at ≤ 80 chars, wrapping to a second visual line only for a very long name. Web: `<ul class="trade-reasons">` under the fairness row.
4. **Deck invariance in prod:** a `GET /api/trades` deck diff before/after the PUT on the same league (same `fairness_threshold`, job cache invalidated) must differ ONLY in the presence of `reasons` — ids, order, count, values identical. If anything else moves, something other than this knob changed between the two reads.
5. **D-099 note:** not an engine-affecting change (no deck output moves), so the bake-off window is not censored by this flip under D-099 as written; it IS a presentation change that lands on arms A/B/D and not C/`fit` — log the flip timestamp so a like-rate readout can split on it.
6. **Measuring the effect (a week later):** `reasons` is not in `features_json` (code-walk §5). The split is "like rate on cards whose give headliner is below the user's shrunk market" vs the rest, re-derived from the logged give ids + the user's rankings, restricted to `user_value_basis == "personal"` rows. The one-line follow-up — `"below_market_reason": bool` in `features_json` — makes that a plain query if the lead wants it.

## Ledger draft (for the lead — `living-memory/TEST_LEDGER.md`)

> **2026-09-02 — below-market card reason (`reason_below_market_frac`), branch `claude/below-market-reason`.** `pytest backend/tests`: SUITE_BRANCH (clean `origin/main` @ `02d2eac2` baseline the same day: SUITE_MAIN). New `backend/tests/test_below_market_reason.py` (23): full-deck `trade_card_to_dict` golden with the explanations flag ON captured on a `git archive origin/main` tree, byte-identical at knob 0 and moved at 0.15; the Adams-shaped trigger (seed 3,000 / shrunk 2,300 → exact copy) with every silent case (5% at 0.15, above market, picks-only, pick out-seeding the player, non-headliner filler, knob 0, no name, absent from the board); the shrunk board through the real generator (zero comparisons never fires on a raw 23% gap; n = 1 shrinks it under the bar; n = 10,000 fires; both bases); call-time read through the overlay; both config stores at 0.0; arm A excludes, drift alarm knows; deck invariance on the engine-quality fixture at 0.15/0.5/1.0 and on 100 random leagues under the live flags (non-vacuous); wire ON/OFF. Three sabotages red → green (S1 raw board, S2 any-give-player, S3 wire gate dropped). Harness `docs/plans/below-market-reason/measure_below_market.py` (prod pins + D-172 live value, frozen clock, `PYTHONHASHSEED=0`, baseline twice byte-identical, every sweep deck fingerprint-identical to baseline in all 504 cells): live-arm share of served cards carrying the line on the shrunk binary board 0.23 @0.10 → 0.16 @0.15 → 0.08 @0.25 (the 0.10→0.15 drop is exactly the lightly-sampled `[0.10, 0.15)` band); graded board 0.43 @0.15 (ceiling); mirror viewer (board == seed) 0 at every value; arm D flat (raw board under `user_elo_shrink` 0). Recommended live value 0.15. No mobile/web change; `tsc`/testid-lint untouched. Full gates; no express.

**CHANGELOG draft:** *Below-market card reason (feedback #350 / Q-035): when a trade asks the user to give up a player his own board prices below the market, the card now says so — "You rank {name} below the market — that gap is what this trade cashes in." — because that gap is why the engine picked him. Knob `reason_below_market_frac` (0 = off, byte-identical; live 0.15). Presentation only: no deck output moves. Rides the existing `reasons` field both clients already render.*

**DECISIONS draft (one entry, three choices):** (1) **The vehicle is `TradeCard.reasons`, not `narrative`** — D-097 records that no client renders `narrative`; `reasons` is emitted by `trade_card_to_dict` under `trade_math.human_explanations` (true in prod) and rendered uncapped by mobile (`TradeCard.tsx:955`) and web (`app.js:3679`), so the line reached users with zero client change. (2) **Headliner only, on the shrunk board.** The line names the C4b `deck_give_headliner` — the same player the give-headliner cap keys on — and reads the gap on `_shrink_user_elo`'s output, the board the engine actually prices with. Not "any give-side player" (a below-market filler is not why the trade exists) and not the raw board (a one-vote player would fire; a no-board user's raw board IS consensus anyway). (3) **Arm A excludes rather than pins.** The knob moves no deck output on any arm; a 0.0 pin would only strip the explanatory line from arm A's served cards, making A the one served arm whose cards cannot explain themselves — a presentation confound. Recorded with the asymmetry that arms C/`fit` (own generators, outside `_generate_trades_v2`) never carry the line.
