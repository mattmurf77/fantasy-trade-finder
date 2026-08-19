# backend/outlook/ — Notes for Claude

Playoff / championship odds pipeline (feedback #169). Serves `GET /api/league/outlook`, gated by
flag **`outlook.odds`** (route 404s when off). 10 modules, ~1,830 lines. Verified against
`origin/main`, **2026-08-18**.

The design point: five phases, each behind a `typing.Protocol`, resolved through a registry.
**Nothing downstream imports a concrete provider** — swapping the projection source is one registry
line plus one config value, and `pipeline.py` never changes.

## Phases

| # | File | Protocol | Registry | Notes |
|---|---|---|---|---|
| 1 | `league_state.py` | `LeagueStateProvider` | `LEAGUE_STATE_PROVIDERS` (`sleeper`, `mfl`, `fleaflicker`, `espn`) | Schedule + standings + playoff shape. **The only phase that touches a platform API.** Only Sleeper is fully implemented; the rest are registered stubs that 501. |
| 2 | `strength.py` | `StrengthProvider` | `STRENGTH_PROVIDERS` (`roster_value`, `trailing_scores`, `blended`, + `sleeper_projections` / `own_model` as `_StubStrength` subclasses that raise `NotImplementedError`) | Per-team `TeamStrength(mu, sigma)`. **The swap seam the operator cares about.** |
| 3 | `simulator.py` | `Simulator` | `get_simulator()` | Seeded Monte-Carlo, pure, no I/O and no clock reads. |
| 4 | `playoff_format.py` | `PlayoffFormat` | `PLAYOFF_FORMATS` (`standard`) | Seeding by record with `points_for` tiebreak, byes, bracket. |
| 5 | `serialize.py` | `OutlookSerializer` | `get_serializer()` | The **fixed public payload**. Providers vary behind it. |

`pipeline.py` has two entry points on purpose: `build_league_state(...)` (Phase 1, may hit the
network) and `run_outlook(state, ...)` (Phases 2–5, **pure**) — which is why the whole computation
core is unit-testable with no I/O.

## Config

| Knob | Where | Why there |
|---|---|---|
| `FTF_OUTLOOK_STRENGTH_SOURCE` | env var, read by `config.py` | `model_config`'s value column is a **Float**, so the one string knob cannot live there. Default `auto`. |
| `outlook_sim_count`, `outlook_seed`, `outlook_trailing_min_weeks`, `outlook_mean_points`, `outlook_points_per_value_sd`, `outlook_sigma_default`, `outlook_bye_multiplier_*` | `model_config` table (seeded in `database.py`) | Numeric. |

`auto` resolves in `strength.resolve_strength_source`: `completed_weeks == 0` → `roster_value`;
`>= outlook_trailing_min_weeks` → `trailing_scores`; in between → `blended`.

**The roster-value→points calibration is a documented heuristic, not a fitted model.** Treat the
numbers as tunable, not as ground truth; the backtest scaffold is
`test_outlook_odds.py::test_backtest_against_captured_season` (skipped unless
`FTF_OUTLOOK_BACKTEST=/path/to/captured.json`).

## Adding a strength provider

1. Write the class in `strength.py` implementing `estimate(state, ctx) -> dict[roster_id, TeamStrength]`.
2. Add **one line** to `STRENGTH_PROVIDERS`.
3. Set `FTF_OUTLOOK_STRENGTH_SOURCE=<key>` (or pass `source_override`).

Do not import it from `pipeline.py`, `serialize.py`, or `server.py` — that breaks the seam.

## Things not to "tidy"

- **Determinism is a contract.** The simulator seeds from `stable_hash(league_id) ^ config_seed`
  using a SHA-256 derivation, deliberately **not** Python's builtin `hash()` (per-process salted by
  `PYTHONHASHSEED`, which would break resumability across restarts). Payload invariants:
  Σ`playoff_pct` == slots, Σ`title_pct` == 1, Σ`bye_pct` == byes.
- **`meta.is_preseason` and `meta.beta` are separate signals.** `is_preseason` = `completed_weeks == 0`
  (a fact). `beta` = `completed_weeks < _BETA_UNTIL_COMPLETED_WEEKS` (6) — a model-confidence signal.
  They were aliased once; the 2026-08-09 fix separated them and both ship on every payload.
- **`bye_multiplier.py` is evaluated, NOT wired.** `pipeline.py` does not call it and does not read
  `outlook_bye_multiplier_enabled`. `simulator.py`'s per-week multiplier hook is left `None` by every
  live caller. It has tests (`test_bye_multiplier.py`) — passing tests are not evidence it ships.
- **`playoff_seed_type` (BUG-3)** is a Phase-1 fact `LeagueState` carries no field for. `server.py`'s
  `league_outlook_route` captures it from the raw Sleeper league-meta response via a side-channel
  (no extra network call) and passes it into `run_outlook`. `0` → fixed bracket, `1` → reseed,
  anything else → reseed with a logged warning (`_resolve_seed_type`).
- **`bye_weeks.py` derives byes from the nflverse schedule CSV** because Sleeper's player dump
  carries no bye field (verified across all 12,218 players). CC-BY upstream — keep the attribution.

## Tests and fixtures

`test_outlook_odds`, `test_outlook_calibration`, `test_outlook_direction`, `test_outlook_seed`,
`test_outlook_idp_pricing`, `test_outlook_preseason_source`, `test_outlook_playoff_seed_type`,
`test_outlook_route_cache`, `test_opponent_outlook_infer`, `test_bye_weeks`, `test_bye_multiplier`.

Fixtures: `../tests/fixtures/outlook-calibration/` (per-league season snapshots),
`../tests/fixtures/outlook-hypotheses/` (backtest record sets),
`../tests/fixtures/nflverse_games_2022_2026.csv`, `../tests/fixtures/dp-values-history/` (dated DP
boards, so a board never contains information from after the date it prices).

Route contract, caching behavior and flag status: [docs/api-reference.md](../../docs/api-reference.md)
(`GET /api/league/outlook`). Knobs: [docs/config-reference.md](../../docs/config-reference.md).
