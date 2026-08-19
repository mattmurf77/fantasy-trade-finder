# Landability challenger

Bake-off arm D: a both-willing / less-lopsided overlay on the live engine, generated in the dark against arm `current`. Historical arm A (`baseline`) is not this work.

**Status:** active, not built · 2026-08-19
**PRD (EM-facing, source of truth):** [PRD.md](PRD.md)
**Engineering gate:** [scope.md](scope.md)

## Tickets

| ID | Track | Title | Who | Est | Depends | Serves to users? |
|---|---|---|---|---:|---|---|
| A1 | Challenger | Arm plumbing (`challenger` roster + `model_challenger()` + runner) | backend | 1d | — | no (dark) |
| A2 | Challenger | Generation knobs (`user_elo_shrink`, `consensus_both_ways`, `consensus_fairness_floor`, 1-for-2) | backend | 1d | A1 | no |
| A3 | Challenger | Ranking knobs (compress `tier_mult_*`, R5 off) | backend | 0.5d | A1 | no |
| A4 | Challenger | Tests, knob inventory, dark validation | backend | 1d | A1–A3 | no |
| B1 | Hygiene | Likes-you floor 0 + run R1 | backend | 0.5d | — | **yes**, if promoted |
| B2 | Hygiene | Don’t say “balanced” unless fairness ≥ 0.75 | mobile + web | 0.5d | — | **yes**, if promoted |
| C1 | Measurement | Offline 3-cell count (0.50/0.75 × one-way/both-ways) | analytics | 0.5d | — | n/a |
| C2 | Measurement | Interleaved like-rate analysis | analytics | — | A4 + operator lights interleaved | n/a |

A1 is the only hard prerequisite on Track A. C1 can start today. B1 is recommended in the same sprint (broken under both product choices). C2 is **not** this initiative.

## Do not

- Edit `MODEL_A_PROFILE` or the arm-A golden.
- Change live generation defaults. Overlay only.
- Set `bakeoff_serve_interleaved = 1`.
- Dualize aggression / outlook-direction / `fit_premium` / `need_fit` rank / `block_boost`.
- Delete `filler_ok`.
- Touch `trade_gen_v2.py`.
- Add comparison_counts to `member_rankings`.
- Analyse 2026-08-16…08-19 like-rates as ranking quality (D-091 phantom picks).

## Naming

| In conversation | In code | What it is |
|---|---|---|
| “new Arm A” (operator, 2026-08-19) | **`challenger`** | this work |
| Arm A | `baseline` | pre-G6 engine, D-075, do not touch |
| Arm B | `current` | live defaults, still what users see |
| Arm C | `gen_v2` | out of scope |
| Arm D | `challenger` | this work |
