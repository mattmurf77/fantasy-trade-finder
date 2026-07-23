"""Phase 1 — LeagueState ingestion (schedule + standings).

Componentized outlook pipeline (feedback #169). This phase owns the *facts*
of the league: who is on each roster, current W/L/PF standings, the full
regular-season pairing schedule, how many weeks have been played, and the
playoff shape (slots / byes / divisions). Everything downstream (strength,
simulation, seeding, serialization) consumes a `LeagueState` and never talks
to a platform API directly.

Swap seam
---------
`LeagueStateProvider` is the stable Protocol. Concrete providers register into
`LEAGUE_STATE_PROVIDERS` keyed by platform string. Only Sleeper is implemented;
`mfl`/`fleaflicker`/`espn` are registered stubs that raise NotImplementedError
so the seam is real and the gap is explicit.

Sleeper endpoint shapes (per api.sleeper.app v1, verified against the shapes
already consumed elsewhere in this backend — see server._fetch_sleeper_league_meta):
  - GET /league/{id}          → settings.playoff_week_start, settings.playoff_teams,
                                 roster_positions, scoring_settings, season, status
  - GET /league/{id}/rosters  → [{roster_id, owner_id, players[], starters[],
                                   settings:{wins,losses,ties,fpts,fpts_decimal,
                                   fpts_against,fpts_against_decimal,division}}]
  - GET /league/{id}/users    → [{user_id, display_name, metadata:{team_name}}]
  - GET /league/{id}/matchups/{week} → [{roster_id, matchup_id, points, ...}]
NOTE (uncertain, flagged for operator): the exact `matchup_id` pairing semantics
for *future* weeks are assumed stable across the season; if Sleeper only exposes
pairings for the current/played weeks, the remaining-schedule build degrades to
"no pairings" and the simulator falls back to random re-pairing (documented in
simulator.py). This has NOT been validated against live 2025 data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol, runtime_checkable

# Starting-lineup slots we treat as "playable" (everything else is bench/IR/taxi).
_BENCH_SLOTS = {"BN", "IR", "TAXI"}


@dataclass
class TeamState:
    """One team's current, settled facts."""
    roster_id: int
    user_id: str = ""
    username: str = ""
    display_name: str = ""
    division: int | None = None
    wins: int = 0
    losses: int = 0
    ties: int = 0
    points_for: float = 0.0
    points_against: float = 0.0
    player_ids: list[str] = field(default_factory=list)
    starters: list[str] = field(default_factory=list)

    @property
    def win_credit(self) -> float:
        """Wins used for seeding — a tie counts as half a win."""
        return self.wins + 0.5 * self.ties


@dataclass
class LeagueState:
    """Everything the downstream phases need, platform-agnostic."""
    league_id: str
    platform: str
    season: str = ""
    regular_season_weeks: int = 14
    playoff_slots: int = 6
    num_byes: int = 0
    num_divisions: int = 0
    roster_slots: list[str] = field(default_factory=list)   # starting slots only
    teams: list[TeamState] = field(default_factory=list)
    # week -> [(roster_id_a, roster_id_b), ...] for EVERY regular-season week
    schedule: dict[int, list[tuple[int, int]]] = field(default_factory=dict)
    completed_weeks: int = 0
    # roster_id -> [score_week1, score_week2, ...] for COMPLETED weeks only
    weekly_scores: dict[int, list[float]] = field(default_factory=dict)

    @property
    def is_preseason(self) -> bool:
        return self.completed_weeks == 0

    def remaining_weeks(self) -> list[int]:
        """Weeks still to be played (1-indexed), in order."""
        return [w for w in range(self.completed_weeks + 1, self.regular_season_weeks + 1)]


def compute_num_byes(playoff_slots: int) -> int:
    """Byes = (next power of two ≥ slots) − slots.

    6 slots → 2 byes (seeds 1-2), 4 → 0, 8 → 0, 5 → 3. Produces a clean
    reseeding single-elimination bracket for any slot count (see
    playoff_format.py)."""
    if playoff_slots <= 1:
        return 0
    nxt = 1
    while nxt < playoff_slots:
        nxt *= 2
    return nxt - playoff_slots


@runtime_checkable
class LeagueStateProvider(Protocol):
    """Stable Phase-1 interface. Concrete providers vary behind it."""
    platform: str

    def load(self, league_id: str) -> LeagueState:
        ...


class SleeperLeagueState:
    """Sleeper ingestion. HTTP is injected (`fetch`) so this stays decoupled
    from server.py (which imports the pipeline for the route) and unit-testable
    without the network. The route passes `server._sleeper_get`."""

    platform = "sleeper"

    def __init__(self, fetch: Callable[[str], object] | None = None):
        self._fetch = fetch

    def _get(self, path: str) -> object:
        if self._fetch is None:
            # Lazy default: reuse the shared Sleeper helper. Imported lazily to
            # avoid a circular import (server → pipeline → here).
            from ..server import _sleeper_get
            self._fetch = _sleeper_get
        return self._fetch(f"https://api.sleeper.app/v1/{path}")

    def load(self, league_id: str) -> LeagueState:
        meta = self._get(f"league/{league_id}") or {}
        if not isinstance(meta, dict):
            raise ValueError(f"unexpected league meta shape for {league_id!r}")
        settings = meta.get("settings") or {}
        playoff_week_start = int(settings.get("playoff_week_start") or 15)
        regular_weeks = max(1, playoff_week_start - 1)
        playoff_slots = int(settings.get("playoff_teams") or 6)
        num_divisions = int(settings.get("divisions") or 0)
        roster_slots = [
            p for p in (meta.get("roster_positions") or [])
            if p not in _BENCH_SLOTS
        ]

        rosters = self._get(f"league/{league_id}/rosters") or []
        users = self._get(f"league/{league_id}/users") or []
        user_by_id = {
            str(u.get("user_id")): u
            for u in users if isinstance(u, dict)
        }

        teams: list[TeamState] = []
        roster_ids: list[int] = []
        for r in rosters:
            if not isinstance(r, dict):
                continue
            rid = int(r.get("roster_id"))
            roster_ids.append(rid)
            rs = r.get("settings") or {}
            owner = str(r.get("owner_id") or "")
            u = user_by_id.get(owner, {})
            meta_u = (u.get("metadata") or {}) if isinstance(u, dict) else {}
            name = (meta_u.get("team_name")
                    or (u.get("display_name") if isinstance(u, dict) else None)
                    or f"Roster {rid}")
            fpts = float(rs.get("fpts") or 0) + float(rs.get("fpts_decimal") or 0) / 100.0
            fpa = (float(rs.get("fpts_against") or 0)
                   + float(rs.get("fpts_against_decimal") or 0) / 100.0)
            teams.append(TeamState(
                roster_id=rid,
                user_id=owner,
                username=(u.get("display_name") if isinstance(u, dict) else "") or "",
                display_name=name,
                division=rs.get("division"),
                wins=int(rs.get("wins") or 0),
                losses=int(rs.get("losses") or 0),
                ties=int(rs.get("ties") or 0),
                points_for=round(fpts, 2),
                points_against=round(fpa, 2),
                player_ids=[str(p) for p in (r.get("players") or [])],
                starters=[str(p) for p in (r.get("starters") or [])],
            ))

        schedule, weekly_scores, completed = self._load_matchups(
            league_id, regular_weeks, roster_ids
        )

        return LeagueState(
            league_id=str(league_id),
            platform=self.platform,
            season=str(meta.get("season") or ""),
            regular_season_weeks=regular_weeks,
            playoff_slots=playoff_slots,
            num_byes=compute_num_byes(playoff_slots),
            num_divisions=num_divisions,
            roster_slots=roster_slots,
            teams=teams,
            schedule=schedule,
            completed_weeks=completed,
            weekly_scores=weekly_scores,
        )

    def _load_matchups(self, league_id: str, regular_weeks: int,
                       roster_ids: list[int]):
        """Fetch every regular-season week's matchups → pairing schedule,
        completed-week scores, and completed-week count.

        A week is 'completed' when its entries carry any nonzero points. We
        stop counting completed weeks at the first empty week so a mid-season
        bye or data gap can't over-count."""
        schedule: dict[int, list[tuple[int, int]]] = {}
        weekly_scores: dict[int, list[float]] = {rid: [] for rid in roster_ids}
        completed = 0
        still_completing = True
        for week in range(1, regular_weeks + 1):
            try:
                rows = self._get(f"league/{league_id}/matchups/{week}") or []
            except Exception:
                rows = []
            by_matchup: dict[int, list[tuple[int, float]]] = {}
            week_has_points = False
            for row in rows:
                if not isinstance(row, dict):
                    continue
                rid = row.get("roster_id")
                mid = row.get("matchup_id")
                if rid is None or mid is None:
                    continue
                pts = float(row.get("points") or 0.0)
                if pts:
                    week_has_points = True
                by_matchup.setdefault(int(mid), []).append((int(rid), pts))
            # Pairings for this week (schedule graph)
            pairs: list[tuple[int, int]] = []
            for entries in by_matchup.values():
                if len(entries) == 2:
                    pairs.append((entries[0][0], entries[1][0]))
            if pairs:
                schedule[week] = pairs
            # Completed-week bookkeeping (only while still contiguous)
            if still_completing and week_has_points:
                completed = week
                for entries in by_matchup.values():
                    for rid, pts in entries:
                        weekly_scores.setdefault(rid, []).append(pts)
            elif still_completing and not week_has_points:
                still_completing = False
        # Drop scores for weeks past the completed boundary (defensive)
        return schedule, weekly_scores, completed


class _NotImplementedLeagueState:
    """Registered-but-unimplemented provider. Keeps the swap seam honest."""
    platform = "?"

    def load(self, league_id: str) -> LeagueState:
        raise NotImplementedError(
            f"LeagueState ingestion for platform {self.platform!r} is not "
            f"implemented yet (feedback #169 shipped Sleeper only)."
        )


class MflLeagueState(_NotImplementedLeagueState):
    platform = "mfl"


class FleaflickerLeagueState(_NotImplementedLeagueState):
    platform = "fleaflicker"


class EspnLeagueState(_NotImplementedLeagueState):
    platform = "espn"


# Registry: platform → provider factory (zero-arg callable).
LEAGUE_STATE_PROVIDERS: dict[str, Callable[[], LeagueStateProvider]] = {
    "sleeper": SleeperLeagueState,
    "mfl": MflLeagueState,
    "fleaflicker": FleaflickerLeagueState,
    "espn": EspnLeagueState,
}


def get_league_state_provider(platform: str) -> LeagueStateProvider:
    """Factory: resolve a provider by platform, defaulting to Sleeper."""
    factory = LEAGUE_STATE_PROVIDERS.get((platform or "sleeper").lower())
    if factory is None:
        raise KeyError(f"no LeagueState provider for platform {platform!r}")
    return factory()
