# Feature Scope — Playoff odds: 100% and 0% need a proof (D-262)

**Date:** 2026-11-13
**Entry point:** direct ask. Operator 2026-11-13: "There should only be 100% probability if there's absolutely 0 possibility they miss the playoffs. Neither team has technically clinched a spot." Asked "Also stop showing 100% or 0% playoff odds until a team has clinched or been eliminated?": "Yes, fix display".
**Builder:** builder agent, branch `feat/playoff-odds-clinch-display` (stacked on `feat/max-pf-moves-show-all`, D-261)
**Operator sign-off on waivers:** not needed (one waiver, analytics, below: nothing new is emitted)

---

## What changes

The weekly forecast (250,000 simulated seasons) gave two 8-1 teams zero misses with five weeks left and every surface printed "100%". The probability is right; the label claimed a certainty nobody had proven. Two parts:

1. **A proof (backend).** `backend/league_projections/clinch.py` decides, from the forecast's own snapshot (records, remaining schedule, playoff spots), whether each team has mathematically clinched a playoff spot or is mathematically eliminated. Ranked exactly as `simulation.simulate` ranks: standing points (2 x wins + ties), then points for, points against, lottery. Clinched: even losing out, fewer than `playoff_spots` other teams can finish level or above (level counts against the team: the tiebreak is future points). Eliminated: even winning out, at least `playoff_spots` other teams finish strictly above in every outcome. Each "can the rivals do it?" is a small max-flow over the remaining games (2 standing points per game split 2-0, 1-1 or 0-2, so in-game ties are exact), tried for every relevant rival set. Validated against brute force over every outcome.
2. **One display rule (app, website, server strings).** A chance that would print 100% at a surface's precision prints 100% only when clinched is proven; otherwise ">99.9%" (one decimal), ">99%" (whole), ">95%" (5-point steps). 0% needs elimination; otherwise "<0.1%" / "<1%" / "<5%". Every other value prints exactly as before. One helper per client: `mobile/src/utils/playoffOdds.ts`, `web/js/playoff-odds.js`, `clinch.odds_text`.

No probability, simulation number, `score_sd`, `core.VERSION`, threshold or price changes.

## Where the proof is computed, and why there

In the forecast job (`service._run`), on every run, right after the result is assembled: `clinch.attach(result, snapshot)` adds `playoff_clinched` / `playoff_eliminated` to every team and a top-level `playoff_proof {status, reason}`. The snapshot is in hand there (fresh capture or saved), and every read surface already reads the saved result's teams, so the flags reach Standings, the team card, Home, Max PF moves, the outlook recommendation and Team Review with no read-time work. A reused prior result passes through the same line, so the planned forecast re-run fills the keys in. Not flag-gated (display honesty). Absent keys (results saved before this) read "not proven": until the next weekly run those surfaces show ">99.9%" where they showed "100%", which is the honest reading.

Read-time computation was the alternative (no change to `result_json`); rejected because it would need the same call in six read paths and the saved result does not carry points against for the season-over case.

## Proven exactly / returned "not proven"

| League shape | Answer |
|---|---|
| Head-to-head, every remaining week a full schedule, records reconciled, any team count, any spot count (in-game ties included) | exact |
| No games left (season over) | exact from final standings (points, PF, PA at the simulation's precision); an exact three-way tie is the lottery: not proven |
| League also plays the weekly median | not proven (`median_game`) |
| Divisions | not proven (`divisions`); `provider.capture` already refuses them, as it does manual seeding and best ball |
| Missing schedule / a week not a full schedule / weeks out of order | not proven (`missing_schedule`, `partial_schedule`) |
| Records that do not reconcile, invalid spots, garbage | not proven; never raises |
| More than 20,000 rival sets in one league (very large leagues, many spots) | not proven (`too_many_rival_sets`) |

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** a display change to existing text; nothing new is emitted, no event property changes.

## 2. Schema & flag scope

- New/changed tables or columns: none. New keys inside `league_projection_runs.result_json` (`teams[].playoff_clinched`, `teams[].playoff_eliminated`, `playoff_proof`) → `docs/data-dictionary.md`.
- New/changed feature flags: none.
- New env vars / `model_config` keys: none. Rollback lever: revert; old app builds already ignore the keys.

## 3. Evidence scope

- [x] **Structural guard:** new `mobile/tests/check-playoff-odds-display.js` (`npm run test:playoff-odds-display`): executes the app and web helpers over the backend's boundary table, both precisions plus 5-point steps, the miss mirror and the sort key; pins every playoff-chance print to the helper; sweeps `mobile/src` and `web/js` for any other formatting. Extended: `check-standings-table` (A0, A5a, A5f, A5g), `check-max-pf-moves` (A5, P1-P3), `check-team-review` (14a), `check-home-playoff-banner`, `check-win-now`, `check-league-projections-web` (load the helper).
- [x] **Unit tests:** new `backend/tests/test_playoff_clinch.py`; one new test in `test_maxpf_moves_job.py` (reuse fills the keys); deliberately updated pins: `test_maxpf_moves_job.py::test_flag_off_saves_exactly_what_main_saves` and `test_league_projection_control_review.py::test_real_simulation_outputs_and_checkpoint_count_identical` (the worker's result now also carries the proof, and the probabilities are asserted unchanged), `test_maxpf_moves_combined.py::test_v1_keys_unchanged` (the v1 golden stays frozen; exactly two baseline keys added), `test_team_review_current_data.py` (`saved_chance` carries the flags), contract §5.1 / §5.4 examples (baseline gains the two keys).
- [x] **Manual TestFlight checklist:** [testflight-checklist.md](testflight-checklist.md).
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | League projections: team keys, `playoff_proof`, `outlook_recommendation`, `max_pf_moves.baseline`; Team Review `standing.playoff_chance` |
| `living-memory/LLD.md` | updated | one line: proof attached at job time, one display helper per client |
| `docs/architecture.md` | n/a because no module wiring changes beyond one call inside the existing worker |
| `living-memory/HLD.md` | n/a because no new module boundary, client or flow |
| `docs/cross-client-invariants.md` | updated | new § "Playoff odds: 100% and 0% need a proof" |
| `docs/glossary.md` | updated | Clinched, Eliminated |
| `docs/data-dictionary.md` | updated | `league_projection_runs.result_json` keys |
| ADR or `DECISIONS.md` | updated | D-262 |

## Surfaces

Changed (all through the helper): Standings table Playoffs cell, open-team line and the Playoffs sort; team card "Miss playoffs"; Home playoff tile percent and the "Consider" accessibility label; Max PF moves collapsed sentence, opened rows and combined lines (baseline proof, roster-independent so it holds for "after"); Team Review standing chance, window projection line and the outlook-odds accessibility label; League rankings outlook percent chip (5-point steps, ships off); Win Now playoff lines (no proof there); web Projected standings table, outlook prompt and sort; web Win Now playoff lines; the server's outlook explanation sentence.

Deliberately left: bye odds, pick odds, top-3 chance, title odds, weekly win odds, final record odds, the trade-impact card (it prints band movement and percentage-point deltas, never a chance), Win Now percentage-point deltas, the CSV export (raw numbers, not display).

**Sort rule:** by probability; at an equal probability a proven clinch sorts above an unproven ">99.9%" and a proven elimination below an unproven "<0.1%" (`playoffSortKey`, web `rank`).

## 5. Ship gate declaration

- CI green on the pushed sha; evidence in `living-memory/TEST_LEDGER.md` (2026-11-13).
- TestFlight checklist run by the operator after the next build.
- Express lane declared by the operator? no.

## Risks

- A wrong proof would print a false "100%". Mitigations: exact agreement with brute force on every random 4- and 6-team state tried; conservative returns on every unmodelled rule; sabotage of each guard.
- Old app builds keep printing "100%" (accepted by the operator).
- Until the next weekly run, saved results lack the keys and every surface shows ">99.9%" for a 100% chance, even for a team that has clinched.
