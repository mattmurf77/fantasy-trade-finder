"""nflverse NFL schedule ingestion — derives per-team bye weeks (feedback #169).

Sleeper's `/v1/players/nfl` dump does NOT carry bye weeks (verified 2026-08-09:
all 12,218 players, 53 distinct keys, zero bye fields). Byes must be DERIVED
from a schedule: a team absent from every REG-season game in a given week is
on bye. nflverse publishes exactly that as a flat CSV, free under CC-BY:

    https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv

License / attribution (CC-BY, per the nflverse/nfldata repo) — same
public-unauthenticated-GitHub-CSV shape FTF already trusts for DynastyProcess
(see docs/integrations/dynastyprocess.md), but a DIFFERENT upstream, so it
gets its own doc: docs/integrations/nflverse.md. Attribution: "Data by
nflverse (https://github.com/nflverse/nfldata), CC-BY."

This module is a pure ingestion + cache seam. It is NOT imported by
pipeline.py, server.py, or any other live-path module as of this commit — see
docs/feedback/items/169-outlook-league-summary/bye-week-multiplier-2026-08-09.md
for the evaluated (not-yet-shipped) consumer (`bye_multiplier.py`).

Team-code normalization
------------------------
nflverse's `home_team`/`away_team` codes match Sleeper's player `team` field
for every current franchise EXCEPT the Rams: nflverse uses "LA", Sleeper uses
"LAR" (verified against a live `/v1/players/nfl` pull 2026-08-09 — Washington
is "WAS" in both, the Raiders are "LV" in both post-2020). `_TEAM_ALIASES`
below is the single normalization point.

Caching
-------
Mirrors the DynastyProcess crosswalk idiom in `espn_service.py`
(`get_crosswalk`/`fetch_crosswalk`): lazy fetch on first access, cached
in-memory, three-tier fallback on failure (live fetch -> last-good in-memory
copy -> bundled snapshot fixture). The TTL is much longer than the DP
crosswalk's 24h because NFL schedules (and therefore byes) are STATIC once
the league publishes them — there is no "daily refresh" reason here, just a
periodic safety re-pull in case the upstream corrects a schema/data error.
"""

from __future__ import annotations

import csv
import io
import os
import threading
import time
import urllib.request

NFLVERSE_GAMES_URL = (
    "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
)
_SNAPSHOT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tests", "fixtures", "nflverse_games_2022_2026.csv",
)
# Schedules are static once published; a week-long TTL is a safety net for
# upstream corrections, not a real "freshness" requirement.
_BYE_CACHE_TTL_SECONDS = 7 * 24 * 3600

# nflverse code -> Sleeper `team` field code. Every other current franchise
# code matches as-of 2022+ (see module docstring).
_TEAM_ALIASES = {"LA": "LAR"}

_lock = threading.Lock()
_cache: dict[str, dict[str, int]] | None = None   # season -> {team_abbr: bye_week}
_cache_fetched_at: float = 0.0
_cache_is_snapshot: bool = False   # True when serving the bundled fallback


def _normalize_team(code: str) -> str:
    return _TEAM_ALIASES.get(code, code)


def derive_byes(csv_text: str) -> dict[str, dict[str, int]]:
    """Parse an nflverse `games.csv` (or a season-filtered slice of it) into
    `{season: {team_abbr: bye_week}}`, restricted to regular-season games
    (`game_type == "REG"`). A team's bye week is the first REG week in that
    season where it appears in neither `home_team` nor `away_team`."""
    reader = csv.DictReader(io.StringIO(csv_text))
    teams_by_week: dict[str, dict[int, set[str]]] = {}
    for row in reader:
        if row.get("game_type") != "REG":
            continue
        season = row.get("season")
        if not season:
            continue
        try:
            week = int(row.get("week"))
        except (TypeError, ValueError):
            continue
        wk_teams = teams_by_week.setdefault(season, {}).setdefault(week, set())
        wk_teams.add(_normalize_team(row.get("home_team", "")))
        wk_teams.add(_normalize_team(row.get("away_team", "")))

    out: dict[str, dict[str, int]] = {}
    for season, weeks in teams_by_week.items():
        all_teams: set[str] = set()
        for teams in weeks.values():
            all_teams |= teams
        byes: dict[str, int] = {}
        for week in sorted(weeks):
            for team in all_teams - weeks[week]:
                byes.setdefault(team, week)  # each team has exactly one bye
        out[season] = byes
    return out


def load_snapshot(path: str = _SNAPSHOT_PATH) -> dict[str, dict[str, int]]:
    with open(path, encoding="utf-8") as f:
        return derive_byes(f.read())


def fetch_byes(timeout: int = 15, _opener=None) -> dict[str, dict[str, int]]:
    """Fetch the live nflverse games CSV and derive byes. Raises on failure."""
    req = urllib.request.Request(
        NFLVERSE_GAMES_URL, headers={"User-Agent": "FantasyTradeFinder/1.0"}
    )
    opener = _opener or urllib.request.urlopen
    # obs.api_events — GitHub egress, public CSV, nothing to redact.
    from .. import api_observability as _api_obs
    with _api_obs.observe_call("nflverse", "schedule",
                               active=_opener is None) as _ob:
        with opener(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        byes = derive_byes(raw)
        _ob.ok(status=200, response_bytes=len(raw), seasons=len(byes))
    return byes


def get_byes(_opener=None) -> dict[str, dict[str, int]]:
    """Return the cached `{season: {team: bye_week}}` map, refreshing from
    nflverse when empty or past TTL. Never raises — falls back to the last
    good copy, then to the bundled snapshot fixture."""
    global _cache, _cache_fetched_at, _cache_is_snapshot
    with _lock:
        now = time.time()
        ttl = 3600 if _cache_is_snapshot else _BYE_CACHE_TTL_SECONDS
        if _cache is not None and (now - _cache_fetched_at) < ttl:
            return _cache
        try:
            _cache = fetch_byes(_opener=_opener)
            _cache_fetched_at = now
            _cache_is_snapshot = False
        except Exception as e:
            print(f"⚠️  nflverse schedule fetch failed ({e}) — "
                  f"{'keeping previous copy' if _cache else 'using bundled snapshot'}")
            if _cache is None:
                _cache = load_snapshot()
                _cache_is_snapshot = True
            _cache_fetched_at = now   # don't hammer on every request; retry after TTL
        return _cache


def team_bye_week(season: str, team_abbr: str, _opener=None) -> int | None:
    """Convenience accessor: bye week for one team in one season, or None if
    unknown (bad season, bad team code, or the schedule hasn't been published
    yet for that season)."""
    byes = get_byes(_opener=_opener)
    return (byes.get(str(season)) or {}).get(_normalize_team(team_abbr))


def reset_cache() -> None:
    """Test-only: clear the in-memory cache so the next `get_byes()` re-fetches."""
    global _cache, _cache_fetched_at, _cache_is_snapshot
    with _lock:
        _cache = None
        _cache_fetched_at = 0.0
        _cache_is_snapshot = False
