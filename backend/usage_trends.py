"""Usage Trends — in-season RB/WR/TE usage over the last four completed weeks.

Pure computation behind GET /api/usage-trends (route + caches in server.py).
Source: Sleeper's weekly actual-stats feed (`/stats/nfl/{season}/{week}`, the
sibling of the projections feed season_forecasts.py / fit_engine.py read). Per
player-week it carries `off_snp`, `tm_off_snp`, `rush_att`, `rec_tgt` and `gp`.
Cross-checked 2026-10-10 against the operator's Weeks 1-4 snap CSV and the
Footballguys target export: 1652/1656 snap and 1648/1652 target player-weeks
identical (docs/plans/usage-trends/scope.md §0).

Definitions (docs/glossary.md "Usage Trends"):
  * team share   — player count / team count that week. Team snaps are
                   `tm_off_snp`; team carries and targets are summed over every
                   QB/RB/WR/TE row of that team (QB scrambles included).
  * played       — the player has `gp` > 0 or offensive snaps that week.
  * bye          — the player's team has no offensive snaps that week.
  * out          — his team played, he did not (injury, inactive, scratch).
  * average      — over PLAYED weeks only: byes and missed games are both left
                   out of the divisor (operator ruling 2026-10-10).
  * spike        — a played week whose team share beats BOTH the player's
                   earlier-weeks average and his previous game by SPIKE_RULES.

The caller injects `fetch_json(url)`; nothing here touches the network, the DB,
flags or server.py.
"""
from __future__ import annotations

from typing import Callable

WINDOW_WEEKS = 4
POSITIONS = ("RB", "WR", "TE")
METRICS = ("snaps", "carries", "targets")
_STAT_KEY = {"snaps": "off_snp", "carries": "rush_att", "targets": "rec_tgt"}
# Rows of these positions feed the team totals (carry and target denominators).
_TEAM_POSITIONS = ("QB", "RB", "WR", "TE", "FB")

# metric -> (min team-share gain in percentage points, min count that week).
# Share-driven on purpose: a raw-count gain is often just the team running more
# plays (Tee Higgins, Wk 4: 53 -> 60 snaps while his share FELL 93% -> 79%), and
# a role can grow while counts fall (Braelon Allen, Wk 4: 34 -> 30 snaps, 52% ->
# 94% of plays). The floor keeps depth players off the list. Calibrated on 2026
# Weeks 1-4; the top of each list is the operator's transcript standouts.
SPIKE_RULES = {"snaps": (15.0, 20), "carries": (10.0, 6), "targets": (8.0, 4)}
# Least-squares slope of weekly team share (pp per week) that reads as a role
# growing or shrinking; needs three played weeks.
TREND_SLOPE_PP = 5.0
# A player is listed when his average snap share reaches this, or any metric
# carries one of these signals.
MIN_AVG_SNAP_SHARE = 10.0
_NEWS_KINDS = ("spike", "return", "new", "rising")


def state_url() -> str:
    return "https://api.sleeper.app/v1/state/nfl"


def stats_url(season: int, week: int) -> str:
    return (f"https://api.sleeper.app/stats/nfl/{int(season)}/{int(week)}"
            "?season_type=regular&position[]=QB&position[]=RB&position[]=WR"
            "&position[]=TE&position[]=FB")


def window_weeks(state: dict | None) -> tuple[int | None, list[int]]:
    """(season, the last WINDOW_WEEKS completed regular-season weeks ascending).

    Sleeper's `week` is the week in progress, so weeks before it are complete.
    Anything but the regular season (pre/post/off) — or week 1 in progress —
    yields [] and the screen shows its out-of-season state.
    """
    state = state or {}
    try:
        season = int(state.get("season"))
        week = int(state.get("week") or 0)
    except (TypeError, ValueError):
        return None, []
    if state.get("season_type") != "regular":
        return season, []
    last = week - 1
    if last < 1:
        return season, []
    return season, list(range(max(1, last - WINDOW_WEEKS + 1), last + 1))


def fetch_weeks(season: int, weeks: list[int], fetch_json: Callable) -> dict[int, list]:
    """{week: rows}. A week whose fetch fails or returns a non-list is an
    exception — a partial window would silently misstate averages."""
    out = {}
    for w in weeks:
        rows = fetch_json(stats_url(season, w))
        if not isinstance(rows, list):
            raise ValueError(f"invalid_stats_response:{w}")
        out[w] = rows
    return out


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def normalize_week(rows: list) -> tuple[dict, dict]:
    """One week of raw Sleeper stat rows -> the stored shape (integers):

      teams   {team: {"snaps", "carries", "targets"}}
              snaps   = max `tm_off_snp` over the team's rows (repeated per row)
              carries = sum `rush_att` over its QB/RB/WR/TE/FB rows
              targets = sum `rec_tgt`  over the same rows
      players {player_id: {"name", "position", "team", "played",
                           "snaps", "carries", "targets"}}   RB/WR/TE only
              played  = `gp` > 0 or `off_snp` > 0 (inactive players still get
                        a row carrying only `gms_active`)

    This is exactly what `usage_team_weeks` / `usage_player_weeks` hold
    (database.py), so a stored week and a live fetch feed `compute_normalized`
    identically. A team with no rows that week had a bye."""
    teams: dict[str, dict] = {}
    players: dict[str, dict] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        team = r.get("team")
        info = r.get("player") or {}
        pos = info.get("position")
        if not team or pos not in _TEAM_POSITIONS:
            continue
        st = r.get("stats") or {}
        t = teams.setdefault(team, {"snaps": 0, "carries": 0, "targets": 0})
        t["snaps"] = max(t["snaps"], _int(st.get("tm_off_snp")))
        t["carries"] += _int(st.get("rush_att"))
        t["targets"] += _int(st.get("rec_tgt"))
        pid = str(r.get("player_id") or "")
        if pos not in POSITIONS or not pid:
            continue
        name = " ".join(x for x in (info.get("first_name"), info.get("last_name")) if x)
        players[pid] = {
            "name": name or pid, "position": pos, "team": team,
            "played": _num(st.get("gp")) > 0 or _num(st.get("off_snp")) > 0,
            **{m: _int(st.get(_STAT_KEY[m])) for m in METRICS},
        }
    return teams, players


def _int(v) -> int:
    return int(round(_num(v)))


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _slope(points):
    """Least-squares slope of [(x, y)]; None under three points."""
    if len(points) < 3:
        return None
    mx = _mean([p[0] for p in points])
    my = _mean([p[1] for p in points])
    den = sum((x - mx) ** 2 for x, _ in points)
    return sum((x - mx) * (y - my) for x, y in points) / den if den else None


def _r1(v):
    return None if v is None else round(v, 1)


def _metric(metric: str, weeks: list[int], status: list[str],
            counts: list, shares: list) -> dict:
    """Counts, shares, played-week average, the one headline `signal` and
    private sort keys for one player's metric."""
    played = [i for i, s in enumerate(status) if s == "played"]
    pc = [counts[i] for i in played]
    dpp, floor = SPIKE_RULES[metric]

    # A spike must clear the bar against BOTH the player's earlier average and
    # his previous game: the average alone turns a steady riser (30 -> 40 -> 50
    # -> 60%) into a "spike" every week once it outruns its own history.
    spikes = []                  # (index, delta count, delta share, prev share, returned)
    for k, i in enumerate(played[1:], start=1):
        base = played[:k]
        base_s = [shares[j] for j in base if shares[j] is not None]
        prev = shares[played[k - 1]]
        if shares[i] is None or not base_s or prev is None:
            continue
        d_count = counts[i] - _mean([counts[j] for j in base])
        d_share = shares[i] - _mean(base_s)
        if counts[i] >= floor and d_share >= dpp and shares[i] - prev >= dpp:
            returned = any(status[j] == "out" for j in range(played[k - 1] + 1, i))
            spikes.append((i, d_count, d_share, prev, returned))

    last = len(weeks) - 1
    signal = None
    tier = 4
    sort = 0.0
    latest_spike = next((s for s in spikes if s[0] == last), None)
    missed_before_latest = 0
    if status[last] == "played":
        j = last - 1
        while j >= 0 and status[j] != "played":
            missed_before_latest += status[j] == "out"
            j -= 1
    if latest_spike:
        i, d_count, d_share, prev, returned = latest_spike
        signal = {"kind": "return" if returned else "spike", "week": weeks[i],
                  "count": counts[i], "share": shares[i], "prev_share": prev,
                  "delta": _r1(d_count), "delta_share": _r1(d_share),
                  "missed": missed_before_latest}
        tier, sort = 0, d_share
    elif status[last] == "out":
        signal = {"kind": "out", "week": weeks[last]}
    elif status[last] == "played" and len(played) == 1:
        # First game of the window (debut, or every earlier week missed):
        # no baseline to spike against, so a meaningful role reads as new.
        if counts[last] >= floor:
            signal = {"kind": "new", "week": weeks[last], "count": counts[last],
                      "share": shares[last], "missed": missed_before_latest}
            tier, sort = 1, shares[last] or 0.0
    elif missed_before_latest:
        signal = {"kind": "return", "week": weeks[last], "count": counts[last],
                  "share": shares[last], "delta": None, "delta_share": None,
                  "missed": missed_before_latest}
        tier, sort = 1, shares[last] or 0.0
    elif spikes:
        i, d_count, d_share, prev, _ = spikes[-1]
        signal = {"kind": "spike", "week": weeks[i], "count": counts[i],
                  "share": shares[i], "prev_share": prev, "delta": _r1(d_count),
                  "delta_share": _r1(d_share), "missed": 0}
        tier, sort = 2, weeks[i] * 1000 + d_share
    if signal is None:
        slope = _slope([(i, shares[i]) for i in played if shares[i] is not None])
        if slope is not None and abs(slope) >= TREND_SLOPE_PP:
            first = next(shares[i] for i in played if shares[i] is not None)
            lastv = next(shares[i] for i in reversed(played) if shares[i] is not None)
            signal = {"kind": "rising" if slope > 0 else "falling",
                      "from_share": first, "to_share": lastv,
                      "per_week": _r1(slope)}
            if slope > 0:
                tier, sort = 3, slope

    return {
        "counts": counts, "shares": shares, "avg": _r1(_mean(pc)),
        "signal": signal, "_tier": tier, "_sort": sort,
    }


def compute(weeks_rows: dict[int, list], weeks: list[int]) -> list[dict]:
    """`compute_normalized` over raw Sleeper rows (the live-fetch path)."""
    return compute_normalized({w: normalize_week(weeks_rows.get(w) or []) for w in weeks}, weeks)


def compute_normalized(parsed: dict[int, tuple[dict, dict]], weeks: list[int]) -> list[dict]:
    """One record per RB/WR/TE who played at least one window week and passes
    `_relevant`, each metric carrying its server rank (see `_rank`). Input is
    `{week: normalize_week(...)}` — from a live fetch or the stored tables.
    Shares are percentages rounded to one decimal; counts are ints; a week
    the player did not play (bye or out) is null in both."""
    parsed = {w: parsed.get(w) or ({}, {}) for w in weeks}
    pids = {pid for w in weeks for pid in parsed[w][1]}
    out = []
    for pid in sorted(pids):   # deterministic order: stored == live, byte for byte
        latest = next(parsed[w][1][pid] for w in reversed(weeks) if pid in parsed[w][1])
        status, rec = [], {m: ([], [], []) for m in METRICS}   # counts, shares, team totals
        for w in weeks:
            teams, players = parsed[w]
            row = players.get(pid)
            team = (row or latest)["team"]
            tt = teams.get(team)
            if row and row["played"] and tt and tt["snaps"] > 0:
                status.append("played")
                for m in METRICS:
                    c, s, t = rec[m]
                    c.append(int(row[m]))
                    s.append(_r1(100.0 * row[m] / tt[m]) if tt[m] else None)
                    t.append(tt[m])
            else:
                status.append("out" if tt and tt["snaps"] > 0 else "bye")
                for m in METRICS:
                    c, s, t = rec[m]
                    c.append(None)
                    s.append(None)
                    t.append(None)
        if "played" not in status:
            continue
        metrics = {}
        for m in METRICS:
            counts, shares, totals = rec[m]
            md = _metric(m, weeks, status, counts, shares)
            played_tot = [(counts[i], totals[i]) for i, s in enumerate(status) if s == "played"]
            denom = sum(t for _, t in played_tot)
            md["avg_share"] = _r1(100.0 * sum(c for c, _ in played_tot) / denom) if denom else None
            metrics[m] = md
        if not _relevant(metrics):
            continue
        out.append({"player_id": pid, "name": latest["name"],
                    "position": latest["position"], "team": latest["team"],
                    "status": status, **metrics})
    _rank(out)
    return out


def _relevant(metrics: dict) -> bool:
    """Keeps the payload to players a fantasy manager could care about: a real
    snap share, or something happening in any metric. Drops ~60 deep backups."""
    if (metrics["snaps"]["avg_share"] or 0.0) >= MIN_AVG_SNAP_SHARE:
        return True
    return any((metrics[m]["signal"] or {}).get("kind") in _NEWS_KINDS for m in METRICS)


def _rank(players: list[dict]) -> None:
    """Per metric, `rank` 1..n: latest-week spikes and returns first (biggest
    share jump first), then a latest-week return without a spike, then
    earlier spikes (most recent week first), then rising roles, then
    everyone else by average team share. Private sort keys are dropped."""
    for m in METRICS:
        order = sorted(players, key=lambda p: (
            p[m]["_tier"], -p[m]["_sort"], -(p[m]["avg_share"] or 0.0), p["player_id"]))
        for i, p in enumerate(order, start=1):
            p[m]["rank"] = i
    for p in players:
        for m in METRICS:
            p[m].pop("_tier", None)
            p[m].pop("_sort", None)
