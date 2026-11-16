"""Fill the backtest's Sleeper cache (GET only, public read-only API, about 8 calls a second).

    python3.12 docs/plans/league-projections/playoff-targets/backtest/fetch_cache.py \\
        /path/outside/repo/cache ROOT_LEAGUE_ID [ROOT_LEAGUE_ID ...]

Walks each root league's `previous_league_id` chain and caches, for every
completed earlier season: the league, its rosters, winners bracket and regular-
season matchups; and per season the NFL schedule, and weekly scores,
projections and stats. Plus the player file. Never fetches users. The roots are
not committed here (they are the operator's own leagues; see the README).
`backtest.py` then reads only this cache, with the network disabled.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

API = "https://api.sleeper.app"
_last = [0.]


def get(cache, url):
    path = Path(cache) / (url.replace("https://", "").replace("/", "_").replace("?", "_") + ".json")
    if path.exists():
        return json.loads(path.read_text())
    wait = .12 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    request = urllib.request.Request(url, headers={"User-Agent": "research-backtest"}, method="GET")
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read())
    _last[0] = time.time()
    path.write_text(json.dumps(data))
    return data


def main():
    cache, roots = sys.argv[1], sys.argv[2:]
    Path(cache).mkdir(parents=True, exist_ok=True)
    seasons = set()
    for root in roots:
        league = get(cache, f"{API}/v1/league/{root}")
        while league.get("previous_league_id") not in (None, "", "0"):
            league = get(cache, f"{API}/v1/league/{league['previous_league_id']}")
            if not isinstance(league, dict) or league.get("status") != "complete":
                break
            lid, end = league["league_id"], int(league["settings"]["playoff_week_start"]) - 1
            get(cache, f"{API}/v1/league/{lid}/rosters")
            get(cache, f"{API}/v1/league/{lid}/winners_bracket")
            for week in range(1, end + 1):
                get(cache, f"{API}/v1/league/{lid}/matchups/{week}")
            seasons.add((int(league["season"]), end))
    for season, end in sorted(seasons):
        get(cache, f"{API}/schedule/nfl/regular/{season}")
        for week in range(1, end + 1):
            get(cache, f"{API}/projections/nfl/{season}/{week}?season_type=regular")
            get(cache, f"{API}/stats/nfl/{season}/{week}?season_type=regular")
            get(cache, f"{API}/scores/nfl/regular/{season}/{week}")
    get(cache, f"{API}/v1/players/nfl")


if __name__ == "__main__":
    main()
