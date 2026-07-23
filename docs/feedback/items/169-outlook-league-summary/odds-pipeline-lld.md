# #169 Outlook Odds — Componentized Pipeline LLD

**Status:** design, 2026-07-23. Approved direction: build v1 playoff/title-odds engine now, ship dark + beta-gated (operator, 2026-07-23).
**Hard requirement (operator):** every phase of the projection/odds pipeline must be a **swappable component behind a stable interface**, so any single source (points/projection, schedule, sim, format) can be replaced without touching the others or the UI. Source selection is **config-driven**, never hard-wired.
**Grounding:** [projection-source-research.md](projection-source-research.md), `mockups/outlook-odds/league-summary.html`, `backend/power_rankings.py`.

---

## Architecture — 5 phases, each a Protocol behind a fixed contract

```
LeagueStateProvider → StrengthProvider → Simulator → PlayoffFormat → OutputSerializer → /api/league/outlook → UI
   (schedule+standings)  (the μ,σ per team)  (pure MC)   (seeds/byes)     (fixed payload)
```

New module: `backend/outlook/` (package). Each phase in its own file; a thin `pipeline.py` wires them from config. NOTHING downstream imports a concrete provider — only the Protocol + a registry/factory.

### Phase 1 — `LeagueStateProvider` (schedule + standings) — swappable per platform
```python
class LeagueState(TypedDict):
    teams: list[str]                     # team/roster ids
    usernames: dict[str, str]
    standings: dict[str, Standing]       # {wins, losses, ties, points_for}
    schedule: list[Week]                 # [{week:int, matchups:[(team_a, team_b)]}]  remaining only
    completed_weeks: int
    current_week: int
    playoff_slots: int
    bye_slots: int
    playoff_start_week: int

class LeagueStateProvider(Protocol):
    def fetch(self, league_id: str) -> LeagueState: ...
```
- v1 impl: **`SleeperLeagueState`** — `GET /league/{id}` (settings: `playoff_week_start`, `playoff_teams`, roster count), `/league/{id}/rosters` (`settings.wins/losses/ties/fpts`), and `/league/{id}/matchups/{week}` per week (pair by `matchup_id`, read `points`). This is NEW Sleeper ingestion (FTF doesn't fetch schedule/standings today).
- Registry keyed by platform: `sleeper` (v1). `mfl`/`fleaflicker`/`espn` = registered stubs raising `NotImplemented` (future). Selection follows the league's platform.

### Phase 2 — `StrengthProvider` (THE swappable projection/points seam)
```python
class TeamStrength(TypedDict):
    mu: float        # projected weekly team points (mean)
    sigma: float     # weekly stdev
    source: str      # provenance tag for the payload/caption

class StrengthProvider(Protocol):
    def team_strengths(self, league_id: str, state: LeagueState, basis: str) -> dict[str, TeamStrength]: ...
```
Implementations (all interchangeable; add more without touching the simulator):
- **`RosterValueStrength`** — v1 **preseason default**. μ from summed **starting-lineup** roster value (reuse `power_rankings`/consensus-or-personal board) mapped to a points scale via a calibration fn; σ = league-default heuristic. **Works with zero games played.**
- **`TrailingScoresStrength`** — v1 **in-season**. μ = trailing mean weekly team score, σ = stdev of last N weeks, from `state.schedule` completed scores. Requires `completed_weeks >= K`.
- **`SleeperProjectionsStrength`** — v2 stub (behind a sub-flag). μ from Sleeper's unofficial projections endpoint summed over starters. Isolated so the unofficial-endpoint risk is contained to this one file.
- **`OwnModelStrength`** — future (nflverse-derived). Stub only.
- **`BlendedStrength`** — weighted blend (roster-value prior decaying into trailing as `completed_weeks` grows).

Selection: `model_config["outlook_strength_source"]` ∈ `auto|roster_value|trailing|sleeper_proj|blended` (default `auto`). `auto` = `roster_value` when `completed_weeks < K` else `blended`/`trailing`. **This key is the operator's "swap the source" lever.**

### Phase 3 — `Simulator` (pure, source-agnostic)
```python
def simulate(strengths: dict[str, TeamStrength], state: LeagueState,
             fmt: PlayoffFormat, n_sims: int, seed: int) -> dict[str, TeamOdds]: ...
```
Monte-Carlo: per remaining week, per matchup, draw each team score ~ `Normal(mu, sigma)`, higher wins; accumulate onto current standings; seed via `fmt`; tally playoff/bye/title. **Pure function, no I/O.** RNG is **explicitly seeded** from `hash(league_id) ^ config_seed` — NOT time/`random()` (repo rule: no `Math.random`/`Date.now`; deterministic & resumable). `TeamOdds = {playoff_pct, bye_pct, title_pct, expected_wins, seed_dist}`.

### Phase 4 — `PlayoffFormat` (seeding/byes/tiebreakers) — swappable
```python
class PlayoffFormat(Protocol):
    def seed(self, standings: dict[str, Standing]) -> list[str]: ...   # ranked team ids
```
- v1 impl: **`StandardFormat`** — top-`playoff_slots` by wins, `points_for` tiebreak, `bye_slots` top seeds. Reads slots/byes from `LeagueState`. Swappable for divisional/median formats later.

### Phase 5 — `OutputSerializer` → the FIXED payload contract
`GET /api/league/outlook?league_id=&basis=consensus|personal` →
```json
{
  "meta": {"source": "roster_value", "n_sims": 10000, "completed_weeks": 0,
           "is_preseason": true, "beta": true, "generated_for_week": 1, "platform": "sleeper"},
  "teams": [{"team_id": "...", "username": "...", "playoff_pct": 0.0, "title_pct": 0.0,
             "bye_pct": 0.0, "expected_wins": 0.0, "seed_dist": [..],
             "strength": {"mu": 0.0, "sigma": 0.0, "source": "roster_value"}}]
}
```
**This contract is fixed** — the UI binds to it; any provider swap must keep it stable. `is_preseason`/`beta` drive UI labeling.

---

## Gating & off-season (load-bearing)
- Feature flag **`outlook.odds`** (default **false**, dark). Endpoint 404/403s when off; UI hides the layer.
- **Preseason** (`completed_weeks == 0`, true today — July 2026): `meta.is_preseason = meta.beta = true`; `auto` source = `roster_value`; **UI labels every number "Projected · preseason · beta"** and shows the source caption. No hard "86% playoff odds" preseason.
- Redraft basis stays 501 (separate redraft-VALUE gap — Dependency A, not built here). The odds engine is basis-agnostic: it runs on dynasty roster value as the preseason strength prior, and on trailing scores in-season.

## UI (mobile, `LeagueSummaryScreen.tsx`)
Wire the parked odds layer per `mockups/outlook-odds/league-summary.html`: per-team playoff%/title% presentation, a **beta ribbon** when `meta.beta`, and a source caption from `meta.source`. Entirely behind `outlook.odds`. New `league-summary.odds.*` testIDs.

## Tests
- **Simulator** (deterministic, seeded): dominant-team toy league → high title%; symmetric league → ~uniform; sum of playoff_pct == playoff_slots (± MC noise); title_pct sums to ~1.
- **Providers**: interface conformance; `RosterValueStrength` works at `completed_weeks==0`; `TrailingScoresStrength` errors/needs `>=K`.
- **Format**: seeding/byes/tiebreak on crafted standings.
- **Endpoint**: payload shape; flag-dark rejection; preseason `beta` true.
- **Backtest harness** (offline, not CI-gated): run against a captured 2025 final regular season → the actual champion should have carried a non-trivial pre-playoff title%.

## Docs to update
`docs/api-reference.md` (/api/league/outlook), `docs/config-reference.md` (`outlook.odds` flag + `outlook_strength_source` model_config), `docs/architecture.md` (new `backend/outlook/` pipeline + data flow), `docs/glossary.md` (playoff odds / strength provider terms), `docs/data-dictionary.md` if any table added (prefer none — compute on read).
