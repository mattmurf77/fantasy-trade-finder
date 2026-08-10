# #169 Outlook Odds — Bye-Week Multiplier (evaluated, not shipped)

**Date:** 2026-08-09 · **Author:** build+validation agent · **Branch:** `outlook-calibration` (worktree)
**Subject:** operator directive to make byes visible to the odds engine — "middle path" (keep the validated trailing-scores/roster-value μ, apply a per-week multiplier for how much starting-lineup value is on bye) — while considering **both sides** of every matchup.
**Purpose:** validate the multiplier against the same backtest the shipped engine was validated against before touching anything live. The operator rules on the verdict; this document is written so they can.

> **Verdict in one line:** the bye-week data pipeline (`bye_weeks.py`) is solid, tested, and reusable infrastructure. The multiplier itself (`bye_multiplier.py`) does **not** improve playoff/title Brier at any scale tested — the default scale slightly *degrades* it (statistically null, CI includes 0), and a mechanism check shows real fantasy managers absorb ~78% of a bye's value loss via bench swaps that a fixed-lineup multiplier can't see. **NO-SHIP.** Code lands evaluated-only: `model_config.outlook_bye_multiplier_enabled = 0.0` (default, and **not read by `pipeline.py`** — flipping it today does nothing).

---

## Table of contents

- [1. What was built](#1-what-was-built)
- [2. Data source and license](#2-data-source-and-license)
- [3. Derivation](#3-derivation)
- [4. Both-sides handling](#4-both-sides-handling)
- [5. Backtest — does it improve Brier?](#5-backtest--does-it-improve-brier)
- [6. Mechanism check — do real scores fall as predicted?](#6-mechanism-check--do-real-scores-fall-as-predicted)
- [7. Limitations of this validation](#7-limitations-of-this-validation)
- [8. Interaction with BUG-1 (median-match ingestion)](#8-interaction-with-bug-1-median-match-ingestion)
- [9. Ship/no-ship recommendation](#9-shipno-ship-recommendation)
- [10. Reproducing this report](#10-reproducing-this-report)

---

## 1. What was built

| Piece | File | Status |
|---|---|---|
| nflverse schedule ingestion → bye weeks, cached | `backend/outlook/bye_weeks.py` | Shipped as a standalone, tested module. Not called from anywhere in the live server. |
| Committed offline fixture (season-filtered CSV slice) | `backend/tests/fixtures/nflverse_games_2022_2026.csv` | 2022–2026, REG+PRE+POST rows, 395 KB |
| Bye-week μ multiplier, both-sides, evaluated variant | `backend/outlook/bye_multiplier.py` | Pure functions + `simulate_with_bye_multiplier()`. Not imported by `pipeline.py` or `server.py`. |
| Optional seam on the simulator | `backend/outlook/simulator.py::simulate()` | New `weekly_mu_multiplier` kwarg, default `None` — byte-identical draw sequence to before this change when omitted (`test_simulate_is_unchanged_when_multiplier_omitted`). |
| Selection refactor (behavior-preserving) | `backend/outlook/strength.py` | `starting_lineup_value()` now delegates to a new `select_starting_lineup()` so the multiplier can reuse the SAME greedy lineup selection as the shipped `RosterValueStrength`. Existing outlook test suite re-run clean after the refactor. |
| Backtest extension | `scripts/outlook_calibration_backtest.py` | Adds `bye_variant_backtest()` (Brier comparison, same 6 leagues/4 as-of weeks as the shipped engine's validated backtest) and `mechanism_check()` (real-score evidence). |
| Doc | `docs/integrations/nflverse.md` | Endpoints, license, caching, error modes, instrumentation — mirrors `dynastyprocess.md`'s structure. |
| Knobs (defined, not consulted) | `backend/database.py` `model_config` seeds | `outlook_bye_multiplier_enabled` (0.0), `outlook_bye_multiplier_scale` (1.0) — documented in `docs/config-reference.md`. |
| Tests | `backend/tests/test_bye_weeks.py` (11), `backend/tests/test_bye_multiplier.py` (9) | Derivation correctness incl. a known 2025 bye, cache/fallback behavior, multiplier math, both-sides application. |

## 2. Data source and license

Sleeper's `/v1/players/nfl` bulk dump does **not** carry bye weeks — verified 2026-08-09 against a live pull: all 12,218 returned players, 53 distinct keys observed across the whole dump, zero bye-related fields. Byes must be derived from a schedule.

[nflverse/nfldata](https://github.com/nflverse/nfldata) publishes `data/games.csv` (full game-by-game history, 1999–present) as a flat CSV on GitHub, **[CC-BY licensed](https://github.com/nflverse/nfldata#license)** — reuse permitted with attribution. Same trust boundary FTF already relies on for DynastyProcess (`docs/integrations/dynastyprocess.md`): public, unauthenticated, plain HTTP GET, no ToS beyond "be a polite client." A team absent from every `game_type == "REG"` row in a season/week is on bye that week.

**Attribution (required by CC-BY):** "Data by nflverse (https://github.com/nflverse/nfldata), CC-BY."

Live file verified 2026-08-09: 200 OK, ~2.1 MB, 7,548 rows (1999–2026), 45 columns. FTF reads 4 of them (`season`, `game_type`, `week`, `home_team`/`away_team`) — full detail in `docs/integrations/nflverse.md`.

## 3. Derivation

`bye_weeks.derive_byes()` — pure function, tested against the committed fixture:

- Filters to `game_type == "REG"`.
- For each `(season, week)`, collects the set of teams playing.
- A team's bye is the first REG week it's missing from that set.

**Verified against ground truth:** the Philadelphia Eagles' actual 2025 bye was week 9 (`test_known_2025_bye_philadelphia_week_9`) — independently checkable against the real NFL schedule, not just internally consistent. All 32 teams get exactly one bye per season in the derived table for every season 2022–2026 (`test_every_team_has_exactly_one_bye_per_season`).

**Team-code alias:** nflverse uses `"LA"` for the Rams; Sleeper's player `team` field uses `"LAR"` (verified against a live `/v1/players/nfl` pull — Washington is `"WAS"` in both, the Raiders are `"LV"` in both post-2020). `bye_weeks._TEAM_ALIASES` normalizes to Sleeper's convention so `bye_multiplier.py` can join directly against `player_team` with no further translation. Tested (`test_derive_byes_known_2025_bye_rams_week_8_via_la_alias`, `test_team_alias_normalizes_la_to_lar`).

**Caching:** mirrors the DynastyProcess crosswalk idiom (`espn_service.get_crosswalk`) — lazy fetch, 7-day TTL (schedules are static once published, unlike DP's 24h daily-refresh values), three-tier fallback (live → last-good copy → bundled snapshot), snapshot-served results retry hourly. Wrapped in `observe_call("nflverse", "schedule")` per the observability program — though as of this commit that call site is unreachable from any live request, since nothing wires `bye_multiplier.py` into the server.

## 4. Both-sides handling

The operator's explicit requirement: a bye affecting your team matters less if your opponent is equally depleted that week — **both sides** of the matchup must be considered, not just yours.

The multiplier is a per-(team, week) number. `simulator.simulate()`'s regular-season draw already samples **both** sides of every matchup independently:

```python
ma = mu[a] * week_mult[a] if week_mult and a in week_mult else mu[a]
mb = mu[b] * week_mult[b] if week_mult and b in week_mult else mu[b]
sa = gauss(ma, sig[a])
sb = gauss(mb, sig[b])
```

Both teams look up their own multiplier from the same per-week map before drawing their own score. No special-casing was needed — this falls out of the existing "draw both sides independently" structure. **Verified, not just asserted:**

- `test_mutual_bye_cancels_head_to_head`: when both teams in the league's only remaining week have an equal fraction of value on bye (0.5), the head-to-head win split is unchanged from the no-bye baseline (within 0.06 wins of Monte-Carlo tolerance over 6,000 sims) — a mutual bye cancels.
- `test_one_sided_bye_shifts_head_to_head`: when only one side is bye-heavy, the unaffected team's win total increases and the affected team's decreases, as expected.

## 5. Backtest — does it improve Brier?

Same harness the shipped engine was validated against: 6 completed real Sleeper league-seasons (`lakeview-2024/2025`, `ffv3-2022–2025`), as-of weeks 3/6/9/12, 10,000 sims per run, `run_outlook`'s clean as-of rewind (`scripts/outlook_calibration_backtest.py::bye_variant_backtest`). The bye-variant uses the **identical** strengths as the baseline run at each (league, week) — the only difference is whether `simulate()` receives the multiplier — so any Brier delta is attributable to the multiplier alone.

**Headline, default knob (`outlook_bye_multiplier_scale = 1.0`, the shipped `model_config` default):**

| Metric | Baseline (validated) | Bye-variant | Change |
|---|---|---|---|
| Playoff Brier | 0.1113 | 0.1212 | **+8.82% (worse)** |
| Title Brier | 0.0725 | 0.0728 | **+0.40% (worse)** |

Cluster bootstrap over the 6 league-seasons (90% CI on the delta, variant − baseline; negative = improves):

| Metric | Observed delta | 90% CI | Verdict |
|---|---|---|---|
| Playoff Brier | +0.0098 | [−0.0011, +0.0206] | **NULL** (CI includes 0) |
| Title Brier | +0.0003 | [−0.0005, +0.0011] | **NULL** (CI includes 0) |

Per as-of week (10,000 sims):

| week | n | base playoff | variant playoff | base title | variant title |
|---|---|---|---|---|---|
| 3 | 72 | 0.1972 | 0.2034 | 0.0953 | 0.0949 |
| 6 | 72 | 0.1204 | 0.1388 | 0.0694 | 0.0701 |
| 9 | 72 | 0.0729 | 0.0745 | 0.0628 | 0.0630 |
| 12 | 72 | 0.0548 | 0.0679 | 0.0626 | 0.0632 |

Every single as-of week is flat-to-worse on playoff Brier; title Brier is a coin flip around flat. **Honest read: the point estimate leans negative and is never positive at any as-of week, but the confidence interval cannot rule out "no effect."** With only 6 league-seasons this backtest cannot detect a small effect either way — but it gives zero positive signal to act on.

**Supplementary exploratory check — is `scale=1.0` just badly calibrated?** A quick sweep (2,000 sims, not part of the committed script, reproducible from the snippet in [§10](#10-reproducing-this-report)) at scales matching the mechanism check's empirical slope:

| `outlook_bye_multiplier_scale` | Playoff Brier change | Title Brier change |
|---|---|---|
| 0.22 (≈ empirical slope, §6) | +1.12% | +0.20% |
| 0.40 | +2.60% | +0.37% |
| 0.60 | +4.49% | +0.82% |
| 1.00 (default) | +8.82% | +0.40% |

**Monotonic: every scale tested makes playoff Brier worse, and the effect size scales with the knob.** Even the mechanistically-honest low scale (0.22) doesn't help — it's just less bad. There is no scale value in this sweep where the multiplier improves calibration. This is not a tuning problem; the term doesn't carry a useful signal at this sample size, for the reason in §6.

## 6. Mechanism check — do real scores fall as predicted?

This is the strongest available evidence, independent of the Brier comparison and of the strength provider entirely: it uses the fixtures' **real weekly scores**, not simulated ones.

For every team-week across all 6 full completed seasons (1,008 team-weeks), computed the fraction of that team's starting lineup (equal weight per slot — see limitation in §7) whose NFL team was on bye that week, and compared to the team's actual score that week vs. its own season average:

| bye-fraction bucket | n | mean fraction | mean actual deviation | naive predicted deviation (scale=1.0) |
|---|---|---|---|---|
| 0.000–0.001 (no one on bye) | 615 | 0.000 | +1.2% | −0.0% |
| 0.001–0.150 | 219 | 0.093 | −1.3% | −9.3% |
| 0.150–0.300 | 140 | 0.195 | −1.3% | −19.5% |
| 0.300–1.010 | 34 | 0.344 | **−8.8%** | −34.4% |

OLS slope of actual % deviation vs. fraction-on-bye: **−0.222**, 90% CI (cluster bootstrap over the 6 league-seasons) **[−0.305, −0.138]**. The naive multiplier's assumption is slope **−1.000**.

**Reading this:** the CI excludes zero — byes DO have a real, statistically detectable negative effect on real team scores, so the underlying intuition is directionally correct. But the CI sits nowhere near −1.0 either: the true effect is **roughly a quarter to a third the size** the naive value-fraction-on-bye multiplier assumes. The gap is exactly what you'd expect from real-world bench management: **fantasy managers already swap in a bench replacement for a bye-week starter far more often than they eat a zero**, so "fraction of starting-lineup value on bye" overstates "fraction of points actually lost" by ~4x. A fixed-lineup Monte-Carlo model has no notion of a manager reacting mid-week — it doesn't know the bench exists — so it can't see that mitigation, which is exactly why the naive multiplier degrades rather than helps: it's punishing a loss that mostly doesn't happen.

## 7. Limitations of this validation

Two approximations apply to **both** §5 and §6, inherited from what the offline fixture set can actually support:

1. **Current rosters, not historical ones.** `player_ids` on each fixture roster is the CURRENT (2026) Sleeper snapshot — Sleeper exposes no historical roster history, so even a 2022 as-of week is scored against who's on that roster today. This is the identical limitation the shipped engine's own calibration report already flags for the roster-value/trailing-scores backtest; the bye multiplier inherits it rather than introducing a new one.
2. **Equal weight per starting slot, not real dynasty value.** The production design weights by each player's trade value (`player_value`); this backtest uses `1.0` per selected starter because no historical trade-value snapshot exists offline for 2022–2025, and applying TODAY's DynastyProcess values to a 2022-era roster/lineup would be a second, harder-to-defend approximation stacked on top of #1. This is a conservative proxy — "fraction of starting SLOTS on bye" rather than "fraction of starting VALUE on bye" — and it is the same proxy used identically for both the Brier comparison and the mechanism check, so the two results are at least internally consistent with each other even if not perfectly faithful to the shipped design.

Six league-seasons is also a small cluster-bootstrap sample (same caveat the shipped engine's own calibration report makes about title odds) — wide confidence intervals are expected and are not evidence of "no effect," just "not enough data to resolve a small effect." The mechanism check (1,008 team-weeks, not 6 events) is the more statistically resolved of the two checks, and it's the one that isolates the actual problem (bench mitigation).

## 8. Interaction with BUG-1 (median-match ingestion)

`living-memory/GOTCHAS.md` G-024 / the calibration report's BUG-1: `SleeperLeagueState` ignores `settings.league_average_match`, so a live median-match league (2 of the 6 backtest leagues — `lakeview-2024`, `lakeview-2025`) currently ingests W/L on a double-counted scale. **This backtest is unaffected by BUG-1**, for the same reason the shipped engine's headline numbers are: both use the harness's `as_of()` clean rewind, not the shipped Phase-1 ingestion path (documented in the module's own header comment). BUG-1 and the bye multiplier are orthogonal — fixing BUG-1 would not change this verdict, and shipping the bye multiplier would neither fix nor worsen BUG-1. Flagging only because the sample composition (2/6 median-match leagues) is shared with the already-known-affected metric, and because `outlook.odds` is dark for both reasons independently — this report doesn't change that.

## 9. Ship/no-ship recommendation

**NO-SHIP.** At the shipped default (`scale=1.0`) the multiplier makes playoff Brier worse (point estimate, CI technically includes 0) and title Brier flat. A calibrated scale that matches the real empirical effect size (§6) is *less bad* but still never better across the sweep in §5. The mechanism check explains why: the multiplier's core assumption — starting-lineup value on bye translates roughly 1:1 into lost points — overstates the real effect by ~4x, because it has no way to see that managers already roster around byes.

**What to flip if this is ever revisited:** `model_config.outlook_bye_multiplier_enabled` (currently `0.0`) — but as of this commit **`pipeline.py` does not read that key at all**, so flipping it today is a no-op; wiring it into `run_outlook()` is a separate, small follow-up that was deliberately not done here per the "not wired into the live path" instruction. `outlook_bye_multiplier_scale` (currently `1.0`) would need recalibrating to something near the empirical slope first, and even then §5 shows no scale in the tested range helps.

**What retains value regardless of this verdict:** `backend/outlook/bye_weeks.py` is genuinely reusable, tested, licensed-and-attributed schedule infrastructure — exactly the kind of input a real weekly-points projection model (the registered-but-unimplemented `OwnModelStrength` stub in `strength.py`) will need anyway. The operator's stated secondary goal ("pulling this data now will also help accelerate the next phase of the projection engine") is satisfied independent of the multiplier's null result — the ingestion, caching, and derivation work doesn't need to be redone.

**Suggested next step if bye-awareness stays a priority:** model bench mitigation explicitly (e.g., discount the multiplier by an empirically-derived "manager reacts" factor ≈ the §6 slope, rather than assuming a static lineup) — or drop the mu-multiplier approach for something that models the bench swap itself. Out of scope for this evaluation.

## 10. Reproducing this report

```bash
# Full backtest (baseline + bye-variant Brier comparison + mechanism check),
# 10,000 sims, offline — no network calls (the nflverse fetch is forced to
# fall back to the committed fixture snapshot):
python3 scripts/outlook_calibration_backtest.py

# Unit tests:
python3 -m pytest backend/tests/test_bye_weeks.py backend/tests/test_bye_multiplier.py -v
```

The §5 scale sweep (0.22/0.40/0.60) was a one-off exploratory pass, not committed as a script flag — reproduce by calling `bye_multiplier.simulate_with_bye_multiplier(..., cfg={"outlook_bye_multiplier_scale": <value>})` in place of `scripts/outlook_calibration_backtest.py::bye_variant_backtest`'s `cfg={}`.
