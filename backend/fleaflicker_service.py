"""
fleaflicker_service.py — Fleaflicker league linking (Phase 1)
=============================================================
Read-only adapter for Fleaflicker's official public JSON API
(`https://www.fleaflicker.com/api/Fetch*`, `sport=NFL`) plus the shared
DynastyProcess crosswalk (backend/espn_service.py) that maps Fleaflicker
rosters into the app's Sleeper `player_id` space.

Status: **Phase 1 wired** — `server.py`'s `/api/fleaflicker/*` routes import
this module, gated by the `fleaflicker.link` feature flag (default OFF).
Plan: docs/plans/multi-platform-linking-plan-2026-07-17.md §3/§7.

Why Fleaflicker
---------------
- Documented public JSON API, **zero auth** for reads (no key, no OAuth, no
  cookies) — the cheapest and lowest App-Store-risk platform of the four.
- League discovery by user *email* (`FetchUserLeagues`) — the user types
  their own Fleaflicker email; we never hold a credential.
- Crosswalk: DP's `fleaflicker_id` column is a decoy (0.6% coverage); join on
  **`sportradar_id`** instead — request `external_id_type=SPORTRADAR` and the
  roster's `proPlayer.externalIds` carries it (348/348 live, 99.7% mapped).

Design notes
------------
- Pure/offline-testable: HTTP is injected via `_opener`, mirroring
  espn_service.fetch_league. Tests use recorded fixtures, never the network.
- Rosters carry `proPlayer.position` + `nameFull` inline, so no separate
  players DB is needed (unlike MFL). Position → pool filter; nameFull →
  the shared name+position fallback (#127 position-strict).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from backend import espn_service as _xwalk

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FLEAFLICKER_API_BASE = "https://www.fleaflicker.com/api"
BROWSER_HEADERS = {
    "User-Agent": "FantasyTradeFinder/1.0 (+https://fantasytradefinder.app)",
    "Accept": "application/json",
}
POOL_POSITIONS = _xwalk.POOL_POSITIONS


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class FleaflickerError(Exception):
    """kind: 'auth' | 'not_found' | 'http' | 'parse' | 'input'"""

    def __init__(self, message: str, kind: str = "http"):
        super().__init__(message)
        self.kind = kind


# ---------------------------------------------------------------------------
# Fetch (live path — CLI/route; tests inject _opener)
# ---------------------------------------------------------------------------

def _api_url(endpoint: str, **params) -> str:
    params.setdefault("sport", "NFL")
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    return f"{FLEAFLICKER_API_BASE}/{endpoint}?{query}"


def _get(url: str, timeout: int, _opener) -> dict:
    req = urllib.request.Request(url, headers=dict(BROWSER_HEADERS))
    opener = _opener or urllib.request.urlopen
    try:
        with opener(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise FleaflickerError("Fleaflicker rejected the request", kind="auth") from e
        if e.code == 404:
            raise FleaflickerError("Fleaflicker resource not found", kind="not_found") from e
        raise FleaflickerError(f"Fleaflicker HTTP {e.code}", kind="http") from e
    except urllib.error.URLError as e:
        raise FleaflickerError(f"Fleaflicker request failed: {e}", kind="http") from e
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise FleaflickerError("Fleaflicker returned non-JSON", kind="parse") from e
    # Fleaflicker signals errors in-band via an `error` object.
    if isinstance(data, dict) and data.get("error"):
        msg = (data["error"] or {}).get("message") or "Fleaflicker error"
        raise FleaflickerError(msg, kind="not_found")
    return data


def fetch_league_bundle(league_id: str, timeout: int = 15, _opener=None) -> dict:
    """Fetch a league's standings (name/size) + rosters (with sportradar ids).

    Returns {"standings":…, "rosters":…} of raw Fleaflicker payloads. Reads
    need no auth. Raises FleaflickerError(kind='input') for a bad id.
    """
    if not str(league_id).strip().isdigit():
        raise FleaflickerError(f"league_id must be numeric, got {league_id!r}", kind="input")
    standings = _get(_api_url("FetchLeagueStandings", league_id=league_id), timeout, _opener)
    rosters = _get(
        _api_url("FetchLeagueRosters", league_id=league_id,
                 external_id_type="SPORTRADAR"),
        timeout, _opener,
    )
    return {"standings": standings, "rosters": rosters}


def fetch_user_leagues(email: str, timeout: int = 15, _opener=None) -> list[dict]:
    """League discovery by Fleaflicker account email (zero credentials held).

    Returns [{"league_id", "name", "size"}]. Empty list when the email owns
    no NFL leagues.
    """
    if not email or "@" not in email:
        raise FleaflickerError("a valid email is required", kind="input")
    data = _get(_api_url("FetchUserLeagues", email=email), timeout, _opener)
    out = []
    for lg in (data.get("leagues") or []):
        out.append({
            "league_id": str(lg.get("id") or ""),
            "name": lg.get("name") or "",
            "size": lg.get("size") or lg.get("capacity"),
        })
    return out


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

def parse_bundle(raw: dict) -> dict:
    """Normalise the standings + rosters payloads into a small, stable shape.

    Returns:
      {
        "league_id", "name", "total_teams",
        "teams": [{"team_id", "name",
                   "players": [(sportradar_id, name, position), ...]}],
      }
    The Fleaflicker-internal team id is stringified for synthetic-id keying.
    """
    league = (raw.get("standings") or {}).get("league") or {}
    teams = []
    for t in (raw.get("rosters") or {}).get("rosters", []) or []:
        team = t.get("team") or {}
        players = []
        for entry in t.get("players") or []:
            pp = entry.get("proPlayer") or {}
            ext = pp.get("externalIds") or []
            sportradar_id = str((ext[0] or {}).get("id") or "") if ext else ""
            players.append((sportradar_id, pp.get("nameFull") or "",
                            (pp.get("position") or "").upper()))
        teams.append({
            "team_id": str(team.get("id") or ""),
            "name": team.get("name") or f"Team {team.get('id')}",
            "players": players,
        })
    return {
        "league_id": str(league.get("id") or ""),
        "name": league.get("name") or "",
        "total_teams": int(league.get("size") or league.get("capacity") or len(teams) or 0),
        "teams": teams,
    }


# ---------------------------------------------------------------------------
# Crosswalk mapping (sportradar_id → Sleeper id) via the shared generic mapper
# ---------------------------------------------------------------------------

def map_teams(parsed: dict, xwalk) -> dict:
    """Map each team's Fleaflicker roster into Sleeper player_ids.

    Returns {"rosters": {team_id: [sleeper_id,...]}, "report": {...}} — the
    same shape ESPN's map_rosters returns."""
    teams = [(t["team_id"], t["players"]) for t in parsed["teams"]]
    return _xwalk.map_generic_rosters(teams, xwalk.by_sportradar_id, xwalk)


# ---------------------------------------------------------------------------
# Spike CLI:  python3 -m backend.fleaflicker_service <league_id | email>
# ---------------------------------------------------------------------------

def _main(argv: list[str]) -> int:
    import os

    if len(argv) < 2:
        print("usage: python3 -m backend.fleaflicker_service <league_id> "
              "(or an email to list that user's leagues)")
        return 2
    arg = argv[1]
    if "@" in arg:
        for lg in fetch_user_leagues(arg):
            print(f"  {lg['league_id']}: {lg['name']} ({lg['size']} teams)")
        return 0

    raw = fetch_league_bundle(arg)
    parsed = parse_bundle(raw)
    here = os.path.dirname(__file__)
    xwalk = _xwalk.load_crosswalk(
        os.path.join(here, "tests", "fixtures", "dp_playerids_snapshot_2026-07-11.csv")
    )
    out = map_teams(parsed, xwalk)
    print(f"League: {parsed['name']} ({parsed['league_id']}, "
          f"{parsed['total_teams']} teams)")
    for t in parsed["teams"]:
        n = len(out["rosters"].get(t["team_id"], []))
        print(f"  {t['team_id']}: {t['name']} — {n} pool players mapped")
    r = out["report"]
    print(f"Crosswalk: {r['matched_by_id']} by id + {r['matched_by_name']} by name "
          f"of {r['pool_players']} pool players → {r['match_rate']:.1%} "
          f"({r['out_of_pool']} K/DST/IDP out of pool)")
    for u in r["unmatched"]:
        print(f"  unmatched: {u['name']} {u['position']} sr:{u['external_id']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys

    raise SystemExit(_main(sys.argv))
