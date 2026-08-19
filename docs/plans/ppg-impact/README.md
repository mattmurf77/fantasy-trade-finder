# Starter PPG delta

Show starting-lineup PPG before → after on every suggested trade (you and them). Free sources: Sleeper unofficial weekly projections (v1) + nflverse last-season actuals (fallback). **Not a generation input. Not dynasty value** (that’s [card-evidence E2](../card-evidence/README.md)).

**Status:** active, not built · 2026-08-19
**PRD:** [PRD.md](PRD.md)
**Scope:** [scope.md](scope.md)

## Tickets

| ID | Title | Who | Est | Depends | Users see it? |
|---|---|---|---:|---|---|
| F1 | Player PPG cache (Sleeper proj + nflverse fallback) | backend | 1.5d | operator yes on unofficial Sleeper | no (dark cache) |
| F2 | Stamp `ppg_impact` after top-K | backend | 1d | F1 | when `trade.ppg_impact` lit |
| F3 | Card + calculator strip | mobile + web | 1.5d | F2 | yes, flag-gated |

## Do not

- Rank or gate trades on PPG.
- Call RosterAudit or FantasyPros.
- Treat nflverse as forward projections (it isn’t).
- Light `outlook.odds`.
- Custom-score every league setting in v1 (PPR / half / std families only; TEP captioned).
- Fetch HTTP inside `generate_trades`.

## Source (one line)

Sleeper `GET api.sleeper.app/projections/nfl/<season>/<week>` — fixture and URL already in `backend/tests/fixtures/outlook-calibration/sleeper-projections-2026.json`. Lineup sum: `starting_lineup_value()`.
