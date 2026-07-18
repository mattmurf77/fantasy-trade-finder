"""
mfl_service.py — MyFantasyLeague (MFL) league linking (Phase 1)
================================================================
Read-only adapter for MyFantasyLeague's official, sanctioned export API
(`{host}/{year}/export?TYPE=…&L=…&JSON=1`) plus the shared DynastyProcess
crosswalk (backend/espn_service.py) that maps MFL rosters into the app's
Sleeper `player_id` space.

Status: **Phase 1 wired** — `server.py`'s `/api/mfl/*` routes import this
module, gated by the `mfl.link` feature flag (default OFF). Plan:
docs/plans/multi-platform-linking-plan-2026-07-17.md §2/§8.

Why MFL after ESPN
------------------
- Official sanctioned API, third-party clients encouraged (low App Store risk).
- Crosswalk is DP's *primary key* (`mfl_id`) → ~100% coverage of skill players.
- MFL exposes **future draft picks** (`futureDraftPicks`) — the first linked
  platform where pick-inclusive trades can eventually work. Phase 1 STORES
  them raw/additively; wiring picks into the engine is the +M follow-up.

Design notes
------------
- Pure/offline-testable: HTTP is injected via `_opener`, mirroring
  espn_service.fetch_league. Tests use recorded fixtures, never the network.
- **Per-league host gotcha:** league-scoped requests must hit the league's
  assigned `wwwNN.myfantasyleague.com` host, NOT the `api.` host (which
  returns empty for `TYPE=league`). Two resolvers:
    * `parse_host_from_url()` — pull the host straight out of a pasted league
      URL (also un-mangles MFL's scheme-less `https//www48…` homeURLs).
    * `resolve_host()` — for a bare league id, `api.…/{year}/home/{id}`
      302-redirects to the correct `wwwNN` host; we read the Location host.
- Public leagues need no auth. Private leagues pass the user's MFL session
  cookie verbatim in a Cookie header (private path is a later phase; the
  seam is here).
- Rosters carry only MFL player ids + status — no position — so we also
  fetch the league `players` DB (id → name/position) for the pool filter and
  the name+position fallback. Names come back "Last, First"; we flip them.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from backend import espn_service as _xwalk

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MFL_API_HOST = "api.myfantasyleague.com"
DEFAULT_YEAR = 2026

# MFL asks unregistered clients to send a fixed User-Agent and space requests
# ≥1s apart. The operator sets the registered UA in config/env after client
# registration (plan §9 Q1); the default is polite and identifies the app.
MFL_USER_AGENT = os.environ.get(
    "MFL_USER_AGENT", "FantasyTradeFinder/1.0 (+https://fantasytradefinder.app)"
)
BROWSER_HEADERS = {"User-Agent": MFL_USER_AGENT, "Accept": "application/json"}

# The app's ranking/trade pool is skill positions only.
POOL_POSITIONS = _xwalk.POOL_POSITIONS

_REQUEST_SPACING_SECONDS = 1.0   # MFL guidance: "wait one second between requests"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class MflError(Exception):
    """kind: 'auth' | 'not_found' | 'http' | 'parse' | 'input'"""

    def __init__(self, message: str, kind: str = "http"):
        super().__init__(message)
        self.kind = kind


class MflAuthError(MflError):
    def __init__(self, message: str = "MFL rejected the request (private league or bad cookie)"):
        super().__init__(message, kind="auth")


# ---------------------------------------------------------------------------
# Host resolution (the wwwNN gotcha)
# ---------------------------------------------------------------------------

def parse_host_from_url(url: str) -> str | None:
    """Extract the `wwwNN.myfantasyleague.com` host from a pasted MFL URL.

    Handles MFL's own scheme-mangled homeURLs (`https//www48.myfantasyleague
    .com/...` — note the missing colon) that `leagueSearch`/`myleagues`
    return. Returns None if no myfantasyleague host is present.
    """
    if not url or not isinstance(url, str):
        return None
    import re
    m = re.search(r"(www\d*\.myfantasyleague\.com)", url, re.IGNORECASE)
    return m.group(1).lower() if m else None


def parse_league_id_from_url(url: str) -> str | None:
    """Pull the numeric MFL league id out of a pasted URL (path or ?L=)."""
    if not url or not isinstance(url, str):
        return None
    import re
    m = re.search(r"myfantasyleague\.com/\d{4}/(?:home|options|standings)/(\d{4,6})", url, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"[?&]L=(\d{4,6})", url, re.IGNORECASE)
    return m.group(1) if m else None


def resolve_host(league_id: str, year: int, timeout: int = 15, _opener=None) -> str:
    """Resolve the league's assigned wwwNN host for a bare league id.

    `api.myfantasyleague.com/{year}/home/{id}` 302-redirects to the league's
    real host; we read the host out of the Location header without following
    the redirect. Raises MflError(kind='not_found') if no league host comes
    back. Injectable via `_opener` for tests (an opener that raises
    urllib.error.HTTPError with a Location header, or returns a response).
    """
    if not str(league_id).strip().isdigit():
        raise MflError(f"league_id must be numeric, got {league_id!r}", kind="input")
    url = f"https://{MFL_API_HOST}/{int(year)}/home/{league_id}"
    req = urllib.request.Request(url, headers=dict(BROWSER_HEADERS))

    if _opener is not None:
        location = _opener(req, timeout=timeout)   # tests return the Location str
    else:
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        opener = urllib.request.build_opener(_NoRedirect)
        location = None
        try:
            with opener.open(req, timeout=timeout) as resp:
                location = resp.headers.get("Location")
        except urllib.error.HTTPError as e:
            location = e.headers.get("Location")
        except urllib.error.URLError as e:
            raise MflError(f"MFL host resolution failed: {e}", kind="http") from e

    host = parse_host_from_url(location or "")
    if not host:
        raise MflError(
            f"MFL has no league {league_id} for {year} (no host redirect)",
            kind="not_found",
        )
    return host


# ---------------------------------------------------------------------------
# Fetch (live path — CLI/route; tests inject _opener)
# ---------------------------------------------------------------------------

def export_url(host: str, year: int, type_: str, league_id: str) -> str:
    return (
        f"https://{host}/{int(year)}/export?TYPE={urllib.parse.quote(type_)}"
        f"&L={urllib.parse.quote(str(league_id))}&JSON=1"
    )


def _fetch_one(host: str, year: int, type_: str, league_id: str,
               cookie: str | None, timeout: int, _opener) -> dict:
    headers = dict(BROWSER_HEADERS)
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(export_url(host, year, type_, league_id), headers=headers)
    opener = _opener or urllib.request.urlopen
    try:
        with opener(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise MflAuthError() from e
        if e.code == 404:
            raise MflError(f"MFL {type_} not found for league {league_id}", kind="not_found") from e
        raise MflError(f"MFL HTTP {e.code}", kind="http") from e
    except urllib.error.URLError as e:
        raise MflError(f"MFL request failed: {e}", kind="http") from e
    try:
        return json.loads(raw)
    except ValueError as e:
        raise MflError("MFL returned non-JSON", kind="parse") from e


def fetch_league_bundle(league_id: str, year: int, host: str,
                        cookie: str | None = None, timeout: int = 15,
                        _opener=None) -> dict:
    """Fetch the four league-scoped exports (league, rosters,
    futureDraftPicks, players) from the league's host.

    Returns {"league":…, "rosters":…, "futureDraftPicks":…, "players":…} of
    raw MFL payloads. Spaces the live calls ≥1s apart (MFL guidance); no pause
    when `_opener` is injected (tests). `players` is best-effort — a failure
    there degrades to id-only crosswalk (positions unknown → those players
    report as unmatched), never a hard error.
    """
    if not str(league_id).strip().isdigit():
        raise MflError(f"league_id must be numeric, got {league_id!r}", kind="input")

    out: dict = {}
    types = ["league", "rosters", "futureDraftPicks", "players"]
    for i, t in enumerate(types):
        if _opener is None and i > 0:
            time.sleep(_REQUEST_SPACING_SECONDS)
        try:
            out[t] = _fetch_one(host, year, t, league_id, cookie, timeout, _opener)
        except MflError:
            if t == "players":
                out[t] = {}      # degrade gracefully — positions best-effort
            else:
                raise
    return out


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

def _as_list(value) -> list:
    """MFL returns a bare dict when a collection has exactly one member and a
    list otherwise. Normalise to always-a-list."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _flip_name(mfl_name: str) -> str:
    """MFL player names are 'Last, First' — flip to 'First Last' so the
    shared normalise_name+position fallback matches DP's forename-first
    names. Team defenses ('Bills, Buffalo') flip harmlessly; they're out of
    pool anyway."""
    if "," in mfl_name:
        last, first = mfl_name.split(",", 1)
        return f"{first.strip()} {last.strip()}".strip()
    return mfl_name.strip()


def parse_bundle(raw: dict) -> dict:
    """Normalise the four MFL exports into a small, stable shape.

    Returns:
      {
        "league_id", "name", "total_teams",
        "franchises": [{"franchise_id", "name",
                        "players": [(mfl_id, flipped_name, position), ...]}],
        "future_picks": [{"franchise_id", "year", "round", "original_owner"}],
      }
    """
    league = (raw.get("league") or {}).get("league") or {}
    franchises_raw = _as_list((league.get("franchises") or {}).get("franchise"))
    fr_name = {f.get("id"): (f.get("name") or "") for f in franchises_raw}

    # players DB: mfl_id → (name, position)
    players_db: dict[str, tuple[str, str]] = {}
    for p in _as_list((raw.get("players") or {}).get("players", {}).get("player")):
        pid = str(p.get("id") or "")
        if pid:
            players_db[pid] = (_flip_name(p.get("name") or ""),
                               (p.get("position") or "").upper())

    rosters_raw = _as_list((raw.get("rosters") or {}).get("rosters", {}).get("franchise"))
    roster_by_fr: dict[str, list] = {}
    for fr in rosters_raw:
        fid = fr.get("id")
        players = []
        for entry in _as_list(fr.get("player")):
            pid = str(entry.get("id") or "")
            if not pid:
                continue
            name, pos = players_db.get(pid, ("", ""))
            players.append((pid, name, pos))
        roster_by_fr[fid] = players

    # Order franchises by the league's franchise list; include roster-only ids.
    franchises = []
    seen = set()
    for f in franchises_raw:
        fid = f.get("id")
        franchises.append({
            "franchise_id": fid,
            "name": fr_name.get(fid) or f"Team {fid}",
            "players": roster_by_fr.get(fid, []),
        })
        seen.add(fid)
    for fid, players in roster_by_fr.items():
        if fid not in seen:
            franchises.append({"franchise_id": fid,
                               "name": fr_name.get(fid) or f"Team {fid}",
                               "players": players})

    future_picks = []
    for fr in _as_list((raw.get("futureDraftPicks") or {})
                       .get("futureDraftPicks", {}).get("franchise")):
        fid = fr.get("id")
        for pk in _as_list(fr.get("futureDraftPick")):
            future_picks.append({
                "franchise_id": fid,
                "year": pk.get("year"),
                "round": pk.get("round"),
                "original_owner": pk.get("originalPickFor"),
            })

    return {
        "league_id": str(league.get("id") or ""),
        "name": league.get("name") or "",
        "total_teams": int(league.get("franchises", {}).get("count")
                           or len(franchises) or 0),
        "franchises": franchises,
        "future_picks": future_picks,
    }


# ---------------------------------------------------------------------------
# Crosswalk mapping (mfl_id → Sleeper id) via the shared generic mapper
# ---------------------------------------------------------------------------

def map_franchises(parsed: dict, xwalk) -> dict:
    """Map each franchise's MFL roster into Sleeper player_ids.

    Returns {"rosters": {franchise_id: [sleeper_id,...]}, "report": {...}} —
    the same shape ESPN's map_rosters returns."""
    teams = [(fr["franchise_id"], fr["players"]) for fr in parsed["franchises"]]
    return _xwalk.map_generic_rosters(teams, xwalk.by_mfl_sleeper, xwalk)


# ---------------------------------------------------------------------------
# Spike CLI:  python3 -m backend.mfl_service <league_id_or_url> [year]
# ---------------------------------------------------------------------------

def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python3 -m backend.mfl_service <league_id_or_url> [year] "
              "(set MFL_COOKIE env var for a private league)")
        return 2
    arg = argv[1]
    year = int(argv[2]) if len(argv) > 2 else DEFAULT_YEAR
    cookie = os.environ.get("MFL_COOKIE") or None

    host = parse_host_from_url(arg)
    league_id = parse_league_id_from_url(arg) or (arg if arg.isdigit() else None)
    if not league_id:
        print(f"could not parse an MFL league id from {arg!r}")
        return 2
    if not host:
        host = resolve_host(league_id, year)
        print(f"resolved host: {host}")

    raw = fetch_league_bundle(league_id, year, host, cookie=cookie)
    parsed = parse_bundle(raw)
    here = os.path.dirname(__file__)
    xwalk = _xwalk.load_crosswalk(
        os.path.join(here, "tests", "fixtures", "dp_playerids_snapshot_2026-07-11.csv")
    )
    out = map_franchises(parsed, xwalk)
    print(f"League: {parsed['name']} ({parsed['league_id']}, {year}, "
          f"{parsed['total_teams']} teams)")
    for fr in parsed["franchises"]:
        n = len(out["rosters"].get(fr["franchise_id"], []))
        print(f"  {fr['franchise_id']}: {fr['name']} — {n} pool players mapped")
    r = out["report"]
    print(f"Crosswalk: {r['matched_by_id']} by id + {r['matched_by_name']} by name "
          f"of {r['pool_players']} pool players → {r['match_rate']:.1%} "
          f"({r['out_of_pool']} K/DST/IDP out of pool)")
    print(f"Future draft picks stored: {len(parsed['future_picks'])}")
    for u in r["unmatched"]:
        print(f"  unmatched: {u['name']} {u['position']} mfl:{u['external_id']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys

    raise SystemExit(_main(sys.argv))
