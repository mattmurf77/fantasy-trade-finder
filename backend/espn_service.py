"""
espn_service.py — ESPN league-linking SPIKE (#101)
===================================================
Read-only adapter for ESPN Fantasy Football's unofficial v3 API
(`lm-api-reads.fantasy.espn.com`) plus the DynastyProcess player-ID
crosswalk that maps ESPN rosters into the app's Sleeper `player_id` space.

Status: **isolated spike** — nothing in `server.py` imports this yet. See
docs/plans/espn-league-linking-plan-2026-07-11.md for the phased plan and
the go/no-go recommendation this module supports.

Design notes
------------
- Pure/offline-testable: the HTTP call is injected via `_opener`, mirroring
  `backend/sleeper_write.py`. Tests use recorded fixtures, never the network.
- Public leagues need no auth. Private leagues need the `espn_s2` + `SWID`
  cookies captured from a logged-in espn.com session; both are passed through
  verbatim in a Cookie header (espn_s2 must keep the exact encoding it was
  captured with).
- Browser-signature headers, same lesson as the Sleeper write path
  (Cloudflare/edge filters ban the default urllib signature).
- Crosswalk: DynastyProcess `db_playerids.csv` (`espn_id` ↔ `sleeper_id`),
  with a normalised-name+position fallback for rows missing an `espn_id`.
  K and D/ST are outside the app's QB/RB/WR/TE pool and are reported
  separately, not counted as match failures.
"""

from __future__ import annotations

import csv
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from backend.data_loader import normalise_name

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ESPN_READS_BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"

# ESPN edge filters reject bare urllib signatures (same as Sleeper's
# Cloudflare 1010 — see test_sleeper_write.py's browser-header regression).
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# ESPN defaultPositionId → position label
ESPN_POSITION_BY_ID = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}

# The app's ranking/trade pool is skill positions only (players table).
POOL_POSITIONS = {"QB", "RB", "WR", "TE"}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class EspnError(Exception):
    """kind: 'auth' | 'not_found' | 'http' | 'parse' | 'input'"""

    def __init__(self, message: str, kind: str = "http"):
        super().__init__(message)
        self.kind = kind


class EspnAuthError(EspnError):
    def __init__(self, message: str = "ESPN rejected the request (private league or bad cookies)"):
        super().__init__(message, kind="auth")


# ---------------------------------------------------------------------------
# Fetch (live path — spike CLI only; tests inject _opener)
# ---------------------------------------------------------------------------

def league_url(league_id: str, season: int) -> str:
    return (
        f"{ESPN_READS_BASE}/seasons/{season}/segments/0/leagues/"
        f"{urllib.parse.quote(str(league_id))}?view=mTeam&view=mRoster&view=mSettings"
    )


def fetch_league(
    league_id: str,
    season: int,
    espn_s2: str | None = None,
    swid: str | None = None,
    timeout: int = 15,
    _opener=None,
) -> dict:
    """Fetch one league's teams+rosters+settings JSON.

    Public leagues work with no cookies; private leagues need both espn_s2
    and SWID. Raises EspnAuthError on 401/403, EspnError(kind='not_found')
    on 404 (no such league in that season — ESPN purges old leagues).
    """
    if not str(league_id).strip().isdigit():
        raise EspnError(f"league_id must be numeric, got {league_id!r}", kind="input")

    headers = dict(BROWSER_HEADERS)
    if espn_s2 and swid:
        # Pass both through VERBATIM — espn_s2 is URL-encoded as captured and
        # re-encoding it breaks auth; SWID keeps its braces.
        headers["Cookie"] = f"espn_s2={espn_s2}; SWID={swid}"

    req = urllib.request.Request(league_url(league_id, season), headers=headers)
    opener = _opener or urllib.request.urlopen
    try:
        with opener(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise EspnAuthError() from e
        if e.code == 404:
            raise EspnError(
                f"league {league_id} not found for season {season}", kind="not_found"
            ) from e
        raise EspnError(f"ESPN HTTP {e.code}", kind="http") from e

    try:
        return json.loads(raw)
    except ValueError as e:
        raise EspnError("ESPN returned non-JSON", kind="parse") from e


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

@dataclass
class EspnPlayer:
    espn_id: str
    name: str
    position: str  # QB/RB/WR/TE/K/DST/?


@dataclass
class EspnTeam:
    team_id: int
    name: str
    owner_swid: str
    owner_display: str
    players: list[EspnPlayer] = field(default_factory=list)


def parse_league(raw: dict) -> dict:
    """Normalise the mTeam+mRoster payload into a small, stable shape."""
    display_by_swid = {
        m.get("id"): m.get("displayName") or "" for m in raw.get("members", [])
    }
    teams: list[EspnTeam] = []
    for t in raw.get("teams", []):
        # Older payloads split name into location/nickname; newer have `name`.
        name = t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}".strip()
        swid = t.get("primaryOwner") or (t.get("owners") or [""])[0]
        players = []
        for entry in (t.get("roster") or {}).get("entries", []):
            p = (entry.get("playerPoolEntry") or {}).get("player") or {}
            if not p.get("id"):
                continue
            players.append(
                EspnPlayer(
                    espn_id=str(p["id"]),
                    name=p.get("fullName") or "",
                    position=ESPN_POSITION_BY_ID.get(p.get("defaultPositionId"), "?"),
                )
            )
        teams.append(
            EspnTeam(
                team_id=t.get("id"),
                name=name,
                owner_swid=swid,
                owner_display=display_by_swid.get(swid, ""),
                players=players,
            )
        )
    return {
        "league_id": str(raw.get("id", "")),
        "name": (raw.get("settings") or {}).get("name", ""),
        "season": raw.get("seasonId"),
        "total_teams": (raw.get("settings") or {}).get("size") or len(teams),
        "teams": teams,
    }


# ---------------------------------------------------------------------------
# Crosswalk (ESPN id → Sleeper id)
# ---------------------------------------------------------------------------

@dataclass
class Crosswalk:
    by_espn_id: dict[str, str]                     # espn_id → sleeper_id
    by_name_pos: dict[tuple[str, str], str]        # (normalised name, pos) → sleeper_id


def load_crosswalk(csv_path: str) -> Crosswalk:
    """Load a DynastyProcess db_playerids CSV (full or trimmed snapshot).

    Needs columns: sleeper_id, espn_id, merge_name (or name), position.
    'NA' cells are treated as missing.
    """
    by_espn: dict[str, str] = {}
    by_name: dict[tuple[str, str], str] = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = (row.get("sleeper_id") or "").strip()
            eid = (row.get("espn_id") or "").strip()
            if sid in ("", "NA"):
                continue
            if eid not in ("", "NA"):
                by_espn[eid] = sid
            nm = normalise_name(row.get("merge_name") or row.get("name") or "")
            pos = (row.get("position") or "").strip().upper()
            if nm and pos:
                by_name.setdefault((nm, pos), sid)
    return Crosswalk(by_espn_id=by_espn, by_name_pos=by_name)


def map_rosters(teams: list[EspnTeam], xwalk: Crosswalk) -> dict:
    """Map each team's ESPN roster into Sleeper player_ids.

    Returns:
      {
        "rosters": {team_id: [sleeper_id, ...]},
        "report": {
          "pool_players":     skill-position players seen,
          "matched_by_id":    espn_id hit in the crosswalk,
          "matched_by_name":  recovered via normalised name+position,
          "unmatched":        [{"name", "position", "espn_id"}, ...],
          "out_of_pool":      K/DST/unknown-position count (not failures),
          "match_rate":       matched / pool_players (0.0 when pool empty),
        },
      }
    """
    rosters: dict[int, list[str]] = {}
    matched_id = matched_name = out_of_pool = 0
    unmatched: list[dict] = []

    for team in teams:
        ids: list[str] = []
        for p in team.players:
            if p.position not in POOL_POSITIONS:
                out_of_pool += 1
                continue
            sid = xwalk.by_espn_id.get(p.espn_id)
            if sid:
                matched_id += 1
            else:
                sid = xwalk.by_name_pos.get((normalise_name(p.name), p.position))
                if sid:
                    matched_name += 1
            if sid:
                ids.append(sid)
            else:
                unmatched.append(
                    {"name": p.name, "position": p.position, "espn_id": p.espn_id}
                )
        rosters[team.team_id] = ids

    pool = matched_id + matched_name + len(unmatched)
    return {
        "rosters": rosters,
        "report": {
            "pool_players": pool,
            "matched_by_id": matched_id,
            "matched_by_name": matched_name,
            "unmatched": unmatched,
            "out_of_pool": out_of_pool,
            "match_rate": (matched_id + matched_name) / pool if pool else 0.0,
        },
    }


# ---------------------------------------------------------------------------
# Spike CLI:  python3 -m backend.espn_service <league_id> [season]
# ---------------------------------------------------------------------------

def _main(argv: list[str]) -> int:
    import os

    if len(argv) < 2:
        print("usage: python3 -m backend.espn_service <league_id> [season] "
              "(set ESPN_S2 + SWID env vars for a private league)")
        return 2
    league_id = argv[1]
    season = int(argv[2]) if len(argv) > 2 else 2026

    raw = fetch_league(
        league_id, season,
        espn_s2=os.environ.get("ESPN_S2"), swid=os.environ.get("SWID"),
    )
    league = parse_league(raw)
    here = os.path.dirname(__file__)
    xwalk = load_crosswalk(
        os.path.join(here, "tests", "fixtures", "dp_playerids_snapshot_2026-07-11.csv")
    )
    out = map_rosters(league["teams"], xwalk)
    print(f"League: {league['name']} ({league['league_id']}, season {league['season']}, "
          f"{league['total_teams']} teams)")
    for team in league["teams"]:
        print(f"  {team.team_id}: {team.name} — {len(out['rosters'][team.team_id])} "
              f"pool players mapped")
    r = out["report"]
    print(f"Crosswalk: {r['matched_by_id']} by id + {r['matched_by_name']} by name "
          f"of {r['pool_players']} pool players → {r['match_rate']:.1%} "
          f"({r['out_of_pool']} K/DST out of pool)")
    for u in r["unmatched"]:
        print(f"  unmatched: {u['name']} {u['position']} espn:{u['espn_id']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys

    raise SystemExit(_main(sys.argv))
