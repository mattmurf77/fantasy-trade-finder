"""Playoff targets: backtest of the shown gains against completed seasons (scope waiver W3).

For each supported league-season in the cache (completed seasons, Sleeper
`previous_league_id` chain) and each forecast week w (default 4, 6, 8, 10;
weeks at or after the trade deadline are skipped, as the product does):

1. Rebuild the snapshot the weekly job would have captured on the Tuesday
   before week w: the product's own `provider.capture`, fed from the cache
   (league settings, rosters as of the end of week w-1, recorded matchups for
   weeks 1..w-1, the schedule of weeks w..end), with the product's own
   `SleeperExperimentalFeed` turning each week's cached Sleeper projections
   into input rows (one call per week, with each player's NFL team that week).
2. The forecast: `simulation.simulate` at the configured 250,000 runs and
   `clinch.attach`, exactly as `service._run`.
3. For every team as the viewer: `playoff_targets.compute`, unmodified, with
   the configured settings and no saved outlooks (none exist for past seasons).
4. Realised: the rest of the regular season replayed with ACTUAL points, every
   team's lineup chosen by that week's projection from its real roster that
   week (open slots filled by the best projected free agent, as the product
   does), twice: baseline, and with the player moved to the viewer from week w
   on (removed from whoever held him each week, nothing back). Playoff places
   come from the product's own standings code: `simulation.simulate` on the
   replayed season with every week entered as an observed score.

Offline only: socket creation is disabled before any file is read; a cache
miss raises. Output (`result.json` next to this file) is aggregate only: no
league, team, manager or player identity.

    python3.12 docs/plans/league-projections/playoff-targets/backtest/backtest.py /path/to/cache

Optional: --out PATH, --reps N (bootstrap draws, default 1000), --workers N,
--weeks 4,6,8,10, --rows PATH (per-row dump WITH ids; refused inside the repo).
Standard library and the repo's own modules only. Python 3.12.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import socket
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import backtest_stats as bs  # noqa: E402
from backend.league_projections import clinch, playoff_targets, provider, season_points, simulation  # noqa: E402
from backend.league_projections.batch import CONFIG_PATH  # noqa: E402
from backend.league_projections.core import SLOTS, Unavailable, decimal, free_agent_fill, optimize  # noqa: E402
from backend.league_projections.maxpf_moves import parity  # noqa: E402
from backend.league_projections.scoring import BEST_AVAILABLE  # noqa: E402
from backend.season_forecasts import normalize_scoring_for_slots  # noqa: E402

API = "https://api.sleeper.app"
FORECAST_WEEKS = (4, 6, 8, 10)
VIEWER = "viewer-1"  # a stand-in owner id for roster 1; capture needs one member
NULL_PER_VIEWER = 2  # random seller players per viewer-forecast, for each null
GAIN_EDGES = (.01, .02, .05, .10)  # predicted chance gain bins
POINT_EDGES = (5, 10, 20, 40)  # predicted lineup gain bins (points)
NOISE_SHARE = .25  # viewer-forecasts re-run with another simulation seed (noise check)


class CacheMiss(RuntimeError):
    pass


def _no_network(*_args, **_kwargs):
    raise RuntimeError("network access is disabled in this backtest")


# ---------------------------------------------------------------- cache
def cache_path(cache, url):
    return Path(cache) / (url.replace("https://", "").replace("/", "_").replace("?", "_") + ".json")


def load(cache, url):
    path = cache_path(cache, url)
    if not path.exists():
        raise CacheMiss(url)
    return json.loads(path.read_text())


def league_ids(cache):
    """League-seasons with cached matchups: the backtest's population."""
    return sorted({m.group(1) for f in Path(cache).glob("*_matchups_*.json")
                   if (m := re.search(r"league_(\d+)_matchups_\d+\.json$", f.name))})


# ---------------------------------------------------------------- pure pieces
def week_teams(by_week, weeks):
    """{week: {player_id: NFL team}} from per-week rows ({week: {pid: team}}).
    A week with no row for a player takes his team from the nearest earlier
    week, else the nearest later week; never from today's player file."""
    out = {}
    for w in weeks:
        current = {}
        for v in sorted(weeks, key=lambda x: (x > w, abs(x - w))):
            for pid, team in by_week.get(v, {}).items():
                current.setdefault(pid, team)
        out[w] = current
    return out


def pregame_scores(rows):
    """Score rows of a past week as they read before kickoff (the product's
    timing contract, `timing.normalize_week_games`)."""
    out = []
    for raw in rows:
        meta = dict(raw.get("metadata") or {})
        meta.update(status="scheduled", has_started=False, is_in_progress=False, is_over=False, canceled=False)
        out.append({**raw, "status": "pre_game", "metadata": meta})
    return out


def record_settings(history, games_by_week, median):
    """Sleeper roster `settings` that reconcile with recorded weekly scores, as
    `provider.capture` checks them: {rid: {wins, losses, ties, fpts, fpts_decimal,
    fpts_against, fpts_against_decimal}}. history {rid: [Decimal per week]}."""
    from backend.league_projections.core import median_outcomes
    rids = sorted(history)
    rec = {rid: [0, 0, 0] for rid in rids}
    pa = {rid: Decimal(0) for rid in rids}
    for w, games in enumerate(games_by_week):
        for a, b in games:
            av, bv = history[a][w], history[b][w]
            o = 0 if av > bv else 1 if av < bv else 2
            rec[a][o] += 1
            rec[b][1 - o if o < 2 else 2] += 1
            pa[a] += bv
            pa[b] += av
        if median:
            for rid, o in zip(rids, median_outcomes([history[r][w] for r in rids])):
                rec[rid][o] += 1
    out = {}
    for rid in rids:
        pf = sum(history[rid], Decimal(0))
        out[rid] = {"wins": rec[rid][0], "losses": rec[rid][1], "ties": rec[rid][2],
                    **_split("fpts", pf), **_split("fpts_against", pa[rid])}
    return out


def _split(key, value):
    """Sleeper's integer + two-digit split (`core.split_points` reads it back)."""
    value = Decimal(value).quantize(Decimal("0.01"))
    whole = int(value)  # toward zero
    frac = int((abs(value) - abs(Decimal(whole))) * 100)
    return {key: whole, f"{key}_decimal": -frac if value < 0 else frac}


def actual_points(stats_row, scoring):
    """A player's actual fantasy points from Sleeper's weekly stats row under the
    league's scoring (checked against recorded `players_points`)."""
    stats = (stats_row or {}).get("stats") or {}
    return sum((Decimal(str(c)) * Decimal(str(stats[k])) for k, c in scoring.items() if k in stats), Decimal(0))


def chosen_starters(slots, roster, proj, positions, free_agents, empty="fill_available"):
    """The lineup a manager starting by projection would set: the product's
    lineup lane (`core.optimize` on projected points, then `free_agent_fill`
    for open slots). Returns starter ids (free agents included)."""
    pool = [{"player_id": pid, "positions": positions[pid], "points": str(proj[pid])}
            for pid in sorted(roster) if isinstance(proj.get(pid), Decimal) and positions.get(pid)]
    real = optimize(slots, pool, empty_policy=empty)
    filled = free_agent_fill(slots, real, free_agents, empty_policy=empty) if free_agents else real
    return [str(r["player"]["player_id"]) for r in filled["lineup"] if r["player"]]


def hindsight_total(slots, roster, actual, positions):
    """Best lineup in hindsight from the roster alone (no free agents)."""
    pool = [{"player_id": pid, "positions": positions[pid], "points": str(actual.get(pid, Decimal(0)))}
            for pid in sorted(roster) if positions.get(pid)]
    return Decimal(optimize(slots, pool, empty_policy="fill_available")["points"])


def exhaustive_best(slots, players):
    """Independent exact lineup check: dynamic programme over remaining slot
    counts (no assignment algorithm). players: [(positions, Decimal points)].
    Same objective as `optimize(..., empty_policy="fill_available")`."""
    types = sorted(set(slots))
    cap = tuple(slots.count(t) for t in types)
    big = Decimal(10) ** 5
    best = {cap: Decimal(0)}
    for positions, pts in players:
        eligible = [i for i, t in enumerate(types) if SLOTS[t].intersection(positions)]
        new = dict(best)
        for state, value in best.items():
            for i in eligible:
                if state[i]:
                    nxt = state[:i] + (state[i] - 1,) + state[i + 1:]
                    cand = value + big + pts
                    if cand > new.get(nxt, -big * 100):
                        new[nxt] = cand
        best = new
    state, value = max(best.items(), key=lambda kv: kv[1])
    return value - big * (sum(cap) - sum(state))


def replay_snapshot(rids, playoff, byes, median, games_by_week, scores_by_week):
    """A season in the shape `simulation.simulate` reads, every week entered as
    an observed score (no noise): the product's own records, median game,
    points-for / points-against tiebreak and seeded lottery decide places."""
    weeks = []
    for i, (games, scores) in enumerate(zip(games_by_week, scores_by_week)):
        teams = {str(r): {"actual": {"points": str(scores[r]), "lineup": []}, "maxpf": {"points": str(scores[r]), "lineup": []},
                          "modeled_actual_projection": str(scores[r]), "modeled_maxpf_projection": str(scores[r]),
                          "actual_score_observed": True, "maxpf_score_observed": True,
                          "maxpf_dominates_actual": False, "observed_maxpf_floor": None} for r in rids}
        weeks.append({"week": i + 1, "games": [list(g) for g in games], "teams": teams})
    return {"teams": [{"roster_id": r, "name": f"Team {r}", "wins": 0, "losses": 0, "ties": 0, "points_for": "0",
                       "points_against": "0", "maxpf": "0", "actual_history": [], "maxpf_history": []} for r in rids],
            "playoff_spots": playoff, "playoff_byes": byes, "completed_weeks": 0,
            "league_format": {"median_game": bool(median), "games_per_week": 2 if median else 1},
            "weeks": weeks, "pick_ownership": [], "source": "backtest_replay", "captured_at": "replay"}


def made_playoffs(cfg, rids, playoff, byes, median, games_by_week, scores_by_week):
    """{roster_id: share of 100 seeded replays that qualify} (1 or 0 unless an
    exact standings tie goes to the product's lottery)."""
    snap = replay_snapshot(rids, playoff, byes, median, games_by_week, scores_by_week)
    out = simulation.simulate(snap, {**cfg, "iterations": 100})
    return {t["roster_id"]: t["playoff_probability"] for t in out["teams"]}


def bracket_teams(bracket):
    """Every roster in Sleeper's winners bracket: the real playoff teams."""
    return {int(x) for m in bracket or [] for k in ("t1", "t2") if isinstance(x := m.get(k), int)}


# ---------------------------------------------------------------- one league-season
class Season:
    """Everything cached for one league-season, plus the per-week projection
    and actual tables the replay reads."""

    def __init__(self, cache, league_id, metadata):
        self.cache, self.id, self.metadata = cache, league_id, metadata
        self.league = load(cache, f"{API}/v1/league/{league_id}")
        st = self.league["settings"]
        self.season = int(self.league["season"])
        self.end = int(st["playoff_week_start"]) - 1
        self.weeks = list(range(1, self.end + 1))
        self.matchups = {w: load(cache, f"{API}/v1/league/{league_id}/matchups/{w}") for w in self.weeks}
        self.final_rosters = load(cache, f"{API}/v1/league/{league_id}/rosters")
        self.real_playoff = bracket_teams(load(cache, f"{API}/v1/league/{league_id}/winners_bracket"))
        self.rids = sorted(r["roster_id"] for r in self.final_rosters)
        self.slots = [s for s in self.league["roster_positions"] if s not in {"BN", "IR", "TAXI"}]
        self.scoring = self.league["scoring_settings"]
        self.active = normalize_scoring_for_slots(self.scoring, self.slots)
        self.median = bool(st.get("league_average_match"))
        self.playoff = int(st["playoff_teams"])
        self.byes = (1 << (self.playoff - 1).bit_length()) - self.playoff if self.playoff > 1 else 0
        deadline = st.get("trade_deadline")
        self.deadline = deadline if type(deadline) is int and 0 < deadline < 99 else None
        self.schedule = load(cache, f"{API}/schedule/nfl/regular/{self.season}")
        self.scores = {w: load(cache, f"{API}/scores/nfl/regular/{self.season}/{w}") for w in self.weeks}
        self.projections = {w: load(cache, f"{API}/projections/nfl/{self.season}/{w}?season_type=regular") for w in self.weeks}
        stats = {w: load(cache, f"{API}/stats/nfl/{self.season}/{w}?season_type=regular") for w in self.weeks}
        seen = defaultdict(dict)
        for w in self.weeks:
            for rows in (self.projections[w], stats[w]):
                for r in rows:
                    if r.get("team"):
                        seen[w].setdefault(str(r["player_id"]), r["team"])
        self.teams = week_teams(seen, self.weeks)
        self.games = [provider._games(self.matchups[w], set(self.rids)) for w in self.weeks]
        self.recorded = {w: {r["roster_id"]: decimal(r["points"]) for r in self.matchups[w]} for w in self.weeks}
        self.rosters = {w: {r["roster_id"]: sorted({str(p) for p in r.get("players") or []} - {"0"}) for r in self.matchups[w]}
                        for w in self.weeks}
        self.positions = {pid: list(m.get("fantasy_positions") or []) for pid, m in metadata.items()}
        # Actual points: Sleeper's recorded players_points where the player was
        # rostered that week, the stats row under league scoring otherwise.
        self.actual, self.stats_check = {}, Counter()
        for w in self.weeks:
            table = {str(r["player_id"]): actual_points(r, self.scoring) for r in stats[w]}
            for row in self.matchups[w]:
                for pid, pts in (row.get("players_points") or {}).items():
                    value = decimal(pts)
                    self.stats_check["checked"] += 1
                    self.stats_check["mismatch"] += abs(table.get(str(pid), Decimal(0)) - value) > Decimal("0.011")
                    table[str(pid)] = value
            self.actual[w] = table
        self.proj, self.free_agents = {}, {}

    # -------- the product's feed, one week at a time
    def week_metadata(self, w):
        team = self.teams[w]
        return {pid: {"fantasy_positions": m.get("fantasy_positions"), "position": m.get("position"),
                      "full_name": m.get("full_name"), "injury_status": None, "team": team.get(pid)}
                for pid, m in self.metadata.items()}

    def feed_week(self, w, player_ids, captured_at, free_agent_positions):
        urls = {f"{API}/schedule/nfl/regular/{self.season}": self.schedule,
                f"{API}/scores/nfl/regular/{self.season}/{w}": pregame_scores(self.scores[w]),
                f"{API}/projections/nfl/{self.season}/{w}?season_type=regular": self.projections[w]}

        def fetch(url):
            if url not in urls:
                raise CacheMiss(url)
            return urls[url]
        feed = provider.SleeperExperimentalFeed(fetch, metadata=self.week_metadata(w), captured_at=captured_at,
                                                availability_scenario="conditional_provider_forecast", scoring=self.active,
                                                scoring_contract=BEST_AVAILABLE, free_agent_positions=free_agent_positions)
        return feed.weeks(self.season, [w], set(player_ids))

    def capture_time(self, w):
        """The Tuesday-morning job slot before week w: 58 hours before the
        week's first kickoff (Thursday night), after the previous Monday game."""
        first = min(r["start_time"] for r in self.scores[w])
        return (datetime.fromtimestamp(first / 1000, timezone.utc) - timedelta(hours=58)).isoformat()

    # -------- the replay's projection table (product scoring, all players)
    def build_tables(self, first_week):
        positions = set().union(*(SLOTS[s] for s in self.slots))
        for w in range(first_week, self.end + 1):
            ids = {str(r["player_id"]) for r in self.projections[w]} | {p for team in self.rosters[w].values() for p in team}
            out = self.feed_week(w, ids, self.capture_time(w), None)
            proj = {}
            for pid, row in out["weeks"][str(w)].items():
                entry = {**row, "stats": {k: v for k, v in row.get("stats", {}).items() if k in self.scoring}}
                proj[pid] = season_points._entry_points(entry, self.active, True)
            self.proj[w] = proj
            rostered = {p for team in self.rosters[w].values() for p in team}
            self.free_agents[w] = [{"player_id": pid, "positions": self.positions[pid], "points": str(v)}
                                   for pid, v in sorted(proj.items())
                                   if isinstance(v, Decimal) and pid not in rostered and positions.intersection(self.positions.get(pid) or [])]

    def fas(self, w, exclude=None):
        return [p for p in self.free_agents[w] if p["player_id"] != exclude] if exclude else self.free_agents[w]

    # -------- the snapshot the job would have built on the Tuesday before week w
    def capture(self, w, cfg):
        completed = w - 1
        history = {rid: [self.recorded[t][rid] for t in range(1, completed + 1)] for rid in self.rids}
        settings = record_settings(history, self.games[:completed], self.median)
        roster_now = self.rosters[completed]
        rosters = []
        for rid in self.rids:
            ppts = sum((hindsight_total(self.slots, self.rosters[t][rid], self.actual[t], self.positions)
                        for t in range(1, completed + 1)), Decimal(0))
            rosters.append({"roster_id": rid, "owner_id": VIEWER if rid == self.rids[0] else f"owner-{rid}", "co_owners": None,
                            "players": roster_now[rid], "taxi": [], "reserve": [],
                            "settings": {**settings[rid], **_split("ppts", ppts)}})
        league = {**self.league, "status": "in_season"}
        state = {"season": str(self.season), "season_type": "regular", "week": w, "leg": w}
        future = {}
        for t in range(w, self.end + 1):
            # Before kickoff Sleeper lists the current roster and no scores.
            future[t] = [{"roster_id": r["roster_id"], "matchup_id": r["matchup_id"], "players": roster_now[r["roster_id"]],
                          "starters": [], "points": 0, "custom_points": None} for r in self.matchups[t]]
        captured_at = self.capture_time(w)
        positions = set().union(*(SLOTS[s] for s in self.slots))

        class Feed:
            def weeks(feed_self, season, weeks, player_ids):
                merged = {"source": "sleeper_weekly_experimental", "weeks": {}, "captured_at": captured_at,
                          "free_agents": {}, "coverage": {}}
                for t in weeks:
                    out = self.feed_week(t, player_ids, captured_at, positions)
                    merged["weeks"].update(out["weeks"])
                    merged["free_agents"].update(out["free_agents"])
                    merged["coverage"] = {**out["coverage"], "fully_completed_nfl_weeks": []}
                return merged

        def fetch(url):
            path = url.replace(API + "/v1", "")
            if path == "/state/nfl":
                return state
            if path == f"/league/{self.id}":
                return league
            if path == f"/league/{self.id}/rosters":
                return rosters
            if path == f"/league/{self.id}/users":
                return []  # names are optional; none are read
            if path == f"/league/{self.id}/traded_picks":
                return []  # pick ownership does not enter playoff chances
            if path == "/players/nfl":
                return self.metadata
            m = re.fullmatch(rf"/league/{self.id}/matchups/(\d+)", path)
            if m:
                t = int(m.group(1))
                return self.matchups[t] if t <= completed else future[t]
            raise CacheMiss(url)
        sidecar = {}
        snapshot = provider.capture(self.id, VIEWER, cfg, fetch, feed=Feed(), captured_at=captured_at,
                                    clock=lambda: captured_at, sidecar=sidecar)
        return snapshot, sidecar

    # -------- realised replay
    def season_scores(self, w, moves=None):
        """Weekly scores for every team: recorded before week w; from week w on,
        actual points of the lineup chosen by projection. `moves` (player id,
        viewer roster id) adds the player to the viewer and removes him from
        whoever holds him that week. Returns ([{rid: score} per week], {week: viewer score})."""
        out = []
        for t in self.weeks:
            if t < w:
                out.append(self.recorded[t])
                continue
            out.append(self.week_scores(t, moves))
        return out

    def week_scores(self, t, moves=None):
        key = (t, moves)
        if key in self._memo:
            return self._memo[key]
        if moves is None:
            scores = {rid: self.team_score(t, rid, self.rosters[t][rid], self.fas(t)) for rid in self.rids}
        else:
            pid, viewer = moves
            scores = dict(self.week_scores(t))
            for rid in self.rids:
                roster = self.rosters[t][rid]
                if rid == viewer:
                    if pid not in roster:
                        scores[rid] = self.team_score(t, rid, sorted(set(roster) | {pid}), self.fas(t, pid))
                elif pid in roster:
                    scores[rid] = self.team_score(t, rid, [p for p in roster if p != pid], self.fas(t, pid))
            # A free agent he displaced elsewhere is not modelled: free agents are shared.
        self._memo[key] = scores
        return scores

    _memo: dict

    def team_score(self, t, rid, roster, free_agents):
        starters = chosen_starters(self.slots, roster, self.proj[t], self.positions, free_agents)
        return sum((self.actual[t].get(p, Decimal(0)) for p in starters), Decimal(0))

    def made(self, cfg, scores):
        return made_playoffs(cfg, self.rids, self.playoff, self.byes, self.median, self.games, scores)


# ---------------------------------------------------------------- one forecast
_METADATA = None


def _work(task):
    global _METADATA
    socket.socket = _no_network
    cache, league_id, weeks, seed = task
    started = time.time()
    if _METADATA is None:
        _METADATA = load(cache, f"{API}/v1/players/nfl")
    model = json.loads(CONFIG_PATH.read_text())
    options = playoff_targets.settings()
    s = Season(cache, league_id, _METADATA)
    s._memo = {}
    cfg = simulation.config({**model["model"], "draft_season": s.season + 1})
    info = {"league_id": league_id, "season": s.season, "weeks_regular": s.end, "median": s.median,
            "idp": any(slot in {"DL", "LB", "DB", "IDP_FLEX"} for slot in s.slots), "deadline": s.deadline,
            "stats_check": dict(s.stats_check), "forecasts": [], "skipped_weeks": []}
    eligible = [w for w in weeks if w <= s.end and not (s.deadline and w - 1 >= s.deadline)]
    info["skipped_weeks"] = [w for w in weeks if w not in eligible]
    if not eligible:
        return info, [], [], []
    try:
        # The product decides what it supports: a format `provider.capture`
        # refuses (divisions, a DEF slot, best ball...) is out of the backtest.
        s.capture(eligible[0], cfg)
    except Unavailable as exc:
        info["excluded"] = exc.reason
        return info, [], [], []
    s.build_tables(min(eligible))
    # Sanity: replays with recorded scores and with projection-chosen lineups.
    recorded_made = s.made(cfg, [s.recorded[t] for t in s.weeks])
    info["recorded_replay_vs_bracket"] = {"teams": len(s.rids), "agree": sum((recorded_made[r] >= .5) == (r in s.real_playoff) for r in s.rids),
                                          "bracket_teams": len(s.real_playoff)}
    rng = random.Random(seed)
    rows, nulls, teams_out = [], [], []
    for w in eligible:
        t0 = time.time()
        snapshot, sidecar = s.capture(w, cfg)
        snap_parity = parity(snapshot, cfg, sidecar.get("free_agents") or {})
        points_parity = Counter()
        for t, table in season_points.player_points(snapshot).items():
            for pid, v in table.items():
                points_parity["checked"] += 1
                points_parity["mismatch"] += v != s.proj[t].get(pid)
        result = simulation.simulate(snapshot, cfg)
        result = clinch.attach({**result, "reused_compatible_result": False, "verified_at": snapshot["captured_at"]}, snapshot)
        t_sim = time.time() - t0
        base_scores = s.season_scores(w)
        base_made = s.made(cfg, base_scores)
        forecast = {"week": w, "completed_weeks": w - 1, "weeks_remaining": s.end - w + 1,
                    "parity_checked": snap_parity["checked"], "parity_mismatches": len(snap_parity["mismatches"]),
                    "points_parity": dict(points_parity), "seconds_forecast": round(t_sim, 1), "viewers": Counter()}
        noise_cfg = {**result["config"], "seed": result["config"]["seed"] + 1}
        for team in result["teams"]:
            rid = team["roster_id"]
            teams_out.append({"league": league_id, "season": s.season, "week": w, "roster": rid,
                              "now": team["playoff_probability"], "clinched": bool(team.get("playoff_clinched")),
                              "eliminated": bool(team.get("playoff_eliminated")),
                              "made_replay": base_made[rid], "made_real": rid in s.real_playoff})
            block = playoff_targets.compute(snapshot, result, sidecar.get("free_agents") or {}, options,
                                            names=sidecar.get("names"), trade_deadline=sidecar.get("trade_deadline"),
                                            roster_id=rid, seller_outlooks={}, owners=sidecar.get("owners"))
            forecast["viewers"][block["skipped"] or ("rows" if block["rows"] else "no_rows")] += 1
            teams_out[-1]["skipped"] = block["skipped"]
            if block["skipped"]:
                continue
            # Step one again (the product's own function) for the candidate pool,
            # the chosen top 8 and the nulls.
            ctx = playoff_targets._Context(snapshot, result["config"], sidecar.get("free_agents") or {}, None)
            base, _played = playoff_targets._base(ctx, snapshot, rid)
            selling = sorted(int(k) for k, v in block["sellers"].items() if v["eligible"])
            pool = []
            for seller in selling:
                for pid in playoff_targets._candidate_ids(ctx, seller):
                    by_week = playoff_targets.lineup_gains(ctx, rid, base, pid)
                    if by_week is not None:
                        pool.append((sum(by_week.values(), Decimal(0)), pid, seller))
            chosen = sorted([g for g in pool if g[0] > 0], key=lambda g: (-g[0], g[1]))[:options["candidates"]]
            listed = {r["player_id"]: r for r in block["rows"]}
            noise = None
            if block["rows"] and rng.random() < NOISE_SHARE:
                again = playoff_targets.compute(snapshot, {**result, "config": noise_cfg}, sidecar.get("free_agents") or {},
                                                options, roster_id=rid, seller_outlooks={}, owners=sidecar.get("owners"))
                noise = {r["player_id"]: r["playoff_probability"]["after"] for r in again["rows"]}
            for n, (gain, pid, seller) in enumerate(chosen, start=1):
                row = listed.get(pid)
                rows.append(_row(s, cfg, w, rid, pid, seller, gain, n, row, team, base_made, snapshot, noise))
            # Nulls: random players from the selling teams the feature searched.
            positive = [g for g in pool if g[0] > 0]
            for kind, source in (("null_candidate", positive), ("null_any", pool)):
                for gain, pid, seller in rng.sample(source, min(NULL_PER_VIEWER, len(source))):
                    nulls.append({**_row(s, cfg, w, rid, pid, seller, gain, None, None, team, base_made, snapshot, None),
                                  "kind": kind})
        forecast["viewers"] = dict(forecast["viewers"])
        forecast["seconds_total"] = round(time.time() - t0, 1)
        info["forecasts"].append(forecast)
    info["seconds"] = round(time.time() - started, 1)
    return info, rows, nulls, teams_out


def _row(s, cfg, w, rid, pid, seller, gain, rank_by_points, row, team, base_made, snapshot, noise):
    """One player: predicted (from `compute` when listed) and realised."""
    cf_scores = s.season_scores(w, (pid, rid))
    cf_made = s.made(cfg, cf_scores)
    base_scores = s.season_scores(w)
    # Realised lineup gain: the viewer's own weeks, w..end.
    real_gain = sum((cf_scores[t - 1][rid] - base_scores[t - 1][rid] for t in range(w, s.end + 1)), Decimal(0))
    fixed_roster = s.rosters[w - 1][rid]
    fixed_gain = hind_gain = Decimal(0)
    for t in range(w, s.end + 1):
        if pid in fixed_roster:
            break
        fixed_gain += (s.team_score(t, rid, sorted(set(fixed_roster) | {pid}), s.fas(t, pid))
                       - s.team_score(t, rid, fixed_roster, s.fas(t)))
        roster = s.rosters[t][rid]
        if pid not in roster:
            hind_gain += (hindsight_total(s.slots, sorted(set(roster) | {pid}), s.actual[t], s.positions)
                          - hindsight_total(s.slots, roster, s.actual[t], s.positions))
    held = sum(any(pid in s.rosters[t][r] for r in s.rids) for t in range(w, s.end + 1))
    with_seller = sum(pid in s.rosters[t][seller] for t in range(w, s.end + 1))
    out = {"league": s.id, "season": s.season, "week": w, "weeks_remaining": s.end - w + 1, "viewer": rid,
           "player": pid, "seller": seller, "position": (s.positions.get(pid) or ["?"])[0],
           "rank_by_points": rank_by_points, "listed": row is not None,
           "now": team["playoff_probability"], "lineup_gain_step_one": float(gain),
           "made_base": base_made[rid], "made_cf": cf_made[rid],
           "realised_gain": cf_made[rid] - base_made[rid],
           "seller_made_base": base_made[seller], "seller_made_cf": cf_made[seller],
           "realised_lineup_gain": float(real_gain), "realised_lineup_gain_fixed_roster": float(fixed_gain),
           "realised_hindsight_gain": float(hind_gain),
           "weeks_with_seller": with_seller, "weeks_rostered_anywhere": held}
    if row is not None:
        out.update(rank=row["rank"], after=row["playoff_probability"]["after"],
                   predicted_gain=row["playoff_probability"]["after"] - row["playoff_probability"]["now"],
                   passes=row["passes_threshold"], lineup_gain=float(Decimal(row["lineup_gain_exact"])),
                   weeks_affected=row["weeks_affected"])
        if noise is not None:
            out["after_other_seed"] = noise.get(pid)
    return out


# ---------------------------------------------------------------- independent lineup check
def dp_check(cache, league_id, week, rng, metadata, count=40):
    """Exhaustive DP against `playoff_targets.lineup_gains` for random
    (viewer, seller player) pairs in one rebuilt snapshot, on weeks where
    neither lineup uses a free agent or an IDP bye fill."""
    s = Season(cache, league_id, metadata)
    s._memo = {}
    model = json.loads(CONFIG_PATH.read_text())
    cfg = simulation.config({**model["model"], "draft_season": s.season + 1})
    snapshot, sidecar = s.capture(week, cfg)
    ctx = playoff_targets._Context(snapshot, cfg, sidecar.get("free_agents") or {}, None)
    points = season_points.player_points(snapshot)
    checked = mismatched = skipped = 0
    for _ in range(count):
        viewer, other = rng.sample(s.rids, 2)
        roster = ctx.rosters[viewer]["players"]
        candidates = [p for p in ctx.rosters[other]["players"] if p not in roster]
        if not candidates:
            continue
        pid = rng.choice(candidates)
        base, _ = playoff_targets._base(ctx, snapshot, viewer)
        gains = playoff_targets.lineup_gains(ctx, viewer, base, pid, prune=False)
        if gains is None:
            continue
        for t, (detail, actual, _m) in base.items():
            added, _ = ctx.lineups(viewer, t, detail, add={pid})
            if any(r["player"] and (r["player"].get("free_agent") or r["player"].get("hypothetical"))
                   for lineup in (actual, added) for r in lineup["lineup"]):
                skipped += 1
                continue
            mine = [(ctx.positions[p], v) for p in roster if isinstance(v := points[t].get(p), Decimal)]
            his = [(ctx.positions[pid], points[t][pid])] if isinstance(points[t].get(pid), Decimal) else []
            expect = exhaustive_best(s.slots, mine + his) - exhaustive_best(s.slots, mine)
            checked += 1
            mismatched += expect != gains[t]
    return {"player_weeks_checked": checked, "mismatches": mismatched, "skipped_free_agent_or_idp_fill": skipped}


# ---------------------------------------------------------------- analysis
def by_league(rows, keys):
    groups = defaultdict(list)
    for r in rows:
        groups[r["league"]].append(r)
    return [groups[k] for k in keys]


def analyse(infos, rows, nulls, teams, reps, lineage=None):
    keys = sorted({i["league_id"] for i in infos if i["forecasts"]})
    listed = [r for r in rows if r["listed"]]
    out = {}

    def boot(part, stat, seed):
        return bs.bootstrap(by_league(part, keys), stat, reps, seed)

    # ---- B. the playoff-chance gain
    def chance(rs):
        return {"rows": len(rs), "mean_predicted_gain": bs.mean(r["predicted_gain"] for r in rs),
                "mean_realised_gain": bs.mean(r["realised_gain"] for r in rs),
                "bias_predicted_minus_realised": bs.mean(r["predicted_gain"] - r["realised_gain"] for r in rs),
                "share_flipped_in": bs.mean(r["realised_gain"] > 0 for r in rs),
                "share_flipped_out": bs.mean(r["realised_gain"] < 0 for r in rs),
                "flips_in": sum(r["realised_gain"] > 0 for r in rs), "flips_out": sum(r["realised_gain"] < 0 for r in rs)}
    out["chance_gain_all_listed"] = boot(listed, chance, 101)
    out["chance_gain_passing"] = boot([r for r in listed if r["passes"]], chance, 103)
    out["chance_gain_not_passing"] = boot([r for r in listed if not r["passes"]], chance, 107)
    out["chance_gain_by_bin"] = [{"bin": label, **{k: v for k, v in boot(part, chance, 109 + i).items()}}
                                 for i, (label, part) in enumerate(bs.binned(listed, "predicted_gain", GAIN_EDGES))]
    out["chance_gain_by_forecast_week"] = {str(w): boot([r for r in listed if r["week"] == w], chance, 131 + w)
                                           for w in sorted({r["week"] for r in listed})}
    out["chance_gain_by_baseline_now"] = [{"bin": label, **boot(part, chance, 151 + i)} for i, (label, part) in
                                          enumerate(bs.binned(listed, "now", (.1, .3, .5, .7, .9)))]
    # The viewer is fixed per forecast, so whether he can flip at all depends on
    # how close he is: only rows whose baseline replay sits on either side can.
    out["chance_gain_by_baseline_replay_outcome"] = {
        "made_in_baseline_replay": boot([r for r in listed if r["made_base"] >= .5], chance, 171),
        "missed_in_baseline_replay": boot([r for r in listed if r["made_base"] < .5], chance, 173)}
    # ---- ranking
    def flip(rs):
        return {"n": len(rs), "mean_realised_gain": bs.mean(r["realised_gain"] for r in rs),
                "share_flipped_in": bs.mean(r["realised_gain"] > 0 for r in rs),
                "share_flipped_out": bs.mean(r["realised_gain"] < 0 for r in rs),
                "mean_predicted_gain": bs.mean(r.get("predicted_gain") for r in rs if r.get("predicted_gain") is not None),
                "mean_realised_lineup_gain": bs.mean(r["realised_lineup_gain"] for r in rs)}
    out["ranking"] = {
        "listed_rank_1": boot([r for r in listed if r["rank"] == 1], flip, 201),
        "listed_rank_2_3": boot([r for r in listed if r["rank"] in (2, 3)], flip, 203),
        "listed_rank_4_plus": boot([r for r in listed if r["rank"] >= 4], flip, 207),
        "re_simulated_not_listed": boot([r for r in rows if not r["listed"]], flip, 209),
        "null_random_candidate": boot([r for r in nulls if r["kind"] == "null_candidate"], flip, 211),
        "null_random_any_seller_player": boot([r for r in nulls if r["kind"] == "null_any"], flip, 213)}
    # Paired within viewer-forecasts that have both a #1 row and a null draw.
    firsts = {(r["league"], r["week"], r["viewer"]): r for r in listed if r["rank"] == 1}
    paired = []
    for r in nulls:
        key = (r["league"], r["week"], r["viewer"])
        if r["kind"] == "null_candidate" and key in firsts:
            paired.append({"league": r["league"], "diff": firsts[key]["realised_gain"] - r["realised_gain"]})
    out["ranking"]["paired_rank_1_minus_null_candidate"] = boot(paired, lambda rs: {"n": len(rs), "mean": bs.mean(x["diff"] for x in rs)}, 217)
    out["ranking"]["spearman_predicted_vs_realised_gain_within_listed"] = boot(
        listed, lambda rs: {"spearman": bs.spearman([r["predicted_gain"] for r in rs], [r["realised_gain"] for r in rs])}, 219)
    # ---- the baseline chance's own calibration
    evaluated = [t for t in teams if not t["skipped"]]
    with_rows = {(r["league"], r["week"], r["viewer"]) for r in listed}
    cases = [t for t in teams if (t["league"], t["week"], t["roster"]) in with_rows]
    def brier(ts, target):
        return {"n": len(ts), "brier": bs.mean((t["now"] - t[target]) ** 2 for t in ts),
                "brier_climatology": bs.brier_climatology([t[target] for t in ts]),
                "mean_now": bs.mean(t["now"] for t in ts), "mean_outcome": bs.mean(t[target] for t in ts)}
    out["baseline_chance"] = {
        "all_teams_vs_replay": boot(teams, lambda ts: brier(ts, "made_replay"), 301),
        "all_teams_vs_real": boot([{**t, "made_real": float(t["made_real"])} for t in teams], lambda ts: brier(ts, "made_real"), 303),
        "viewers_with_rows_vs_replay": boot(cases, lambda ts: brier(ts, "made_replay"), 307),
        "viewers_with_rows_vs_real": boot([{**t, "made_real": float(t["made_real"])} for t in cases], lambda ts: brier(ts, "made_real"), 309),
        "reliability_all_teams_vs_replay": [{"bin": label, **boot(part, lambda ts: {"n": len(ts), "mean_now": bs.mean(t["now"] for t in ts),
                                                                                   "share_made": bs.mean(t["made_replay"] for t in ts)}, 311 + i)}
                                            for i, (label, part) in enumerate(bs.binned(teams, "now", (.05, .2, .4, .6, .8, .95)))],
        "reliability_viewers_with_rows_vs_replay": [{"bin": label, **boot(part, lambda ts: {"n": len(ts), "mean_now": bs.mean(t["now"] for t in ts),
                                                                                            "share_made": bs.mean(t["made_replay"] for t in ts)}, 331 + i)}
                                                    for i, (label, part) in enumerate(bs.binned(cases, "now", (.2, .4, .6, .8)))],
        "skipped": dict(Counter(t["skipped"] or "computed" for t in teams)),
        "evaluated_viewers": len(evaluated)}
    # ---- sanity: the baseline replay against the real season
    out["sanity"] = {
        "baseline_replay_vs_real_bracket": boot(teams, lambda ts: {"n": len(ts), "agree": bs.mean((t["made_replay"] >= .5) == t["made_real"] for t in ts)}, 401),
        "recorded_scores_replay_vs_real_bracket": {
            "teams": sum(i.get("recorded_replay_vs_bracket", {}).get("teams", 0) for i in infos),
            "agree": sum(i.get("recorded_replay_vs_bracket", {}).get("agree", 0) for i in infos)}}
    # ---- monte carlo noise of the shown gain (same snapshot, another seed)
    redo = [r for r in listed if "after_other_seed" in r]
    out["noise_other_seed"] = {
        "rows_rerun": len(redo), "rows_still_listed": sum(r["after_other_seed"] is not None for r in redo),
        "mean_abs_after_difference": bs.mean(abs(r["after"] - r["after_other_seed"]) for r in redo if r["after_other_seed"] is not None),
        "sd_after_difference": bs.sd([r["after"] - r["after_other_seed"] for r in redo if r["after_other_seed"] is not None]),
        "passes_changed": sum((r["after_other_seed"] is None or (r["after_other_seed"] - r["now"] >= .01 - 1e-9)) != r["passes"] for r in redo)}
    # ---- A. the lineup gain (points)
    def points(pred_key, real_key):
        def stat(rs):
            return bs.summary((r[pred_key], r[real_key]) for r in rs)
        return stat
    lineup_rows = [{**r, "lineup_gain": r.get("lineup_gain", r["lineup_gain_step_one"])} for r in rows]
    out["lineup_gain"] = {
        "listed_rows": boot(listed, points("lineup_gain", "realised_lineup_gain"), 501),
        "listed_rows_hindsight": boot(listed, points("lineup_gain", "realised_hindsight_gain"), 503),
        "listed_rows_fixed_roster": boot(listed, points("lineup_gain", "realised_lineup_gain_fixed_roster"), 505),
        "re_simulated_candidates": boot(lineup_rows, points("lineup_gain", "realised_lineup_gain"), 507),
        "null_any_seller_player": boot([r for r in nulls if r["kind"] == "null_any"], points("lineup_gain_step_one", "realised_lineup_gain"), 509),
        "listed_by_bin": [{"bin": label, **boot(part, points("lineup_gain", "realised_lineup_gain"), 511 + i)}
                          for i, (label, part) in enumerate(bs.binned(listed, "lineup_gain", POINT_EDGES))],
        "listed_by_position": {p: boot([r for r in listed if r["position"] == p], points("lineup_gain", "realised_lineup_gain"), 531)
                               for p in sorted({r["position"] for r in listed})},
        "listed_by_weeks_remaining": {str(n): boot([r for r in listed if r["weeks_remaining"] == n], points("lineup_gain", "realised_lineup_gain"), 541)
                                      for n in sorted({r["weeks_remaining"] for r in listed})},
        # `lineup_gain_exact` is saved to the cent; step one is unrounded.
        "check_step_one_equals_listed_to_the_cent": sum(abs(r["lineup_gain"] - r["lineup_gain_step_one"]) > .00501 for r in listed)}
    # ---- thresholds: what a higher min_playoff_gain would keep
    out["thresholds"] = {f"{t:g}": boot([r for r in listed if r["predicted_gain"] >= t - 1e-9], chance, 601 + i)
                         for i, t in enumerate((.01, .02, .03, .05, .10))}
    out["small_gains_below_0.02"] = boot([r for r in listed if r["predicted_gain"] < .02], chance, 613)
    # ---- clustering: rows of one viewer-forecast share its baseline replay
    forecasts = defaultdict(list)
    for r in listed:
        forecasts[(r["league"], r["week"], r["viewer"])].append(r)
    out["clustering"] = {
        "viewer_forecasts_with_rows": len(forecasts),
        "with_a_flip_in": sum(any(x["realised_gain"] > 0 for x in v) for v in forecasts.values()),
        "with_a_flip_out": sum(any(x["realised_gain"] < 0 for x in v) for v in forecasts.values()),
        "missed_in_baseline_replay": sum(v[0]["made_base"] < .5 for v in forecasts.values()),
        "mean_rows_per_viewer_forecast": bs.mean(len(v) for v in forecasts.values()),
        "seller_outcome_changed_rows": sum(r["seller_made_base"] != r["seller_made_cf"] for r in listed)}
    # ---- franchise sensitivity: the headline with each lineage left out
    if lineage:
        names = sorted(set(lineage.values()))
        out["leave_one_franchise_out"] = [
            {"franchises_kept": len(names) - 1, **chance([r for r in listed if lineage[r["league"]] != name])} for name in names]
    out["roster_path"] = {
        "listed_rows": len(listed),
        "mean_share_of_weeks_still_with_seller": bs.mean(r["weeks_with_seller"] / r["weeks_remaining"] for r in listed),
        "mean_share_of_weeks_rostered_anywhere": bs.mean(r["weeks_rostered_anywhere"] / r["weeks_remaining"] for r in listed)}
    return out


def _total(dicts, keys):
    return {k: sum(d.get(k, 0) for d in dicts) for k in keys}


def lineages(cache, ids):
    """{league id: lineage root} among `ids` (linked by `previous_league_id`)."""
    prev = {lid: str(load(cache, f"{API}/v1/league/{lid}").get("previous_league_id") or "") for lid in ids}
    roots = {}
    for start in ids:
        lid = start
        while prev.get(lid) in prev:
            lid = prev[lid]
        roots[start] = lid
    return roots


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cache")
    parser.add_argument("--out", default=str(HERE / "result.json"))
    parser.add_argument("--reps", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--weeks", default=",".join(map(str, FORECAST_WEEKS)))
    parser.add_argument("--leagues", help="comma-separated subset (debugging)")
    parser.add_argument("--rows", help="optional per-row dump WITH ids; must be outside the repo")
    args = parser.parse_args()
    if args.rows and Path(args.rows).resolve().is_relative_to(ROOT):
        raise SystemExit("--rows must be outside the repository")
    socket.socket = _no_network
    weeks = [int(x) for x in args.weeks.split(",")]
    ids = args.leagues.split(",") if args.leagues else league_ids(args.cache)
    tasks = [(args.cache, lid, weeks, 1000 + i) for i, lid in enumerate(ids)]
    started = time.time()
    if args.workers > 1:
        from multiprocessing import get_context
        with get_context("spawn").Pool(min(args.workers, len(tasks))) as pool:
            parts = pool.map(_work, tasks, chunksize=1)
    else:
        parts = [_work(t) for t in tasks]
    infos = [p[0] for p in parts]
    rows = [r for p in parts for r in p[1]]
    nulls = [r for p in parts for r in p[2]]
    teams = [r for p in parts for r in p[3]]
    metadata = load(args.cache, f"{API}/v1/players/nfl")
    rng = random.Random(9)
    checks = [dp_check(args.cache, info["league_id"], info["forecasts"][0]["week"], rng, metadata)
              for info in infos if info["forecasts"]]
    if args.rows:
        Path(args.rows).write_text(json.dumps({"infos": infos, "rows": rows, "nulls": nulls, "teams": teams}, default=str))
    usable = [i for i in infos if i["forecasts"]]
    lineage = lineages(args.cache, [i["league_id"] for i in usable])
    result = {
        "question": "Do the playoff-chance gains Playoff targets shows come true when the rest of the regular season is replayed with actual points?",
        "bootstrap": f"{args.reps} draws of whole league-seasons with replacement; 95% percentile intervals",
        "units": "chance gains as probabilities (0.05 = 5 percentage points); lineup gains in fantasy points of the league's own scoring, summed over the remaining regular-season weeks",
        "sample": {"league_seasons": len(usable), "franchises": len(set(lineage.values())), "seasons": dict(Counter(i["season"] for i in usable)),
                   "median_leagues": sum(i["median"] for i in usable), "idp_leagues": sum(i["idp"] for i in usable),
                   "forecasts": sum(len(i["forecasts"]) for i in usable),
                   "forecast_weeks": dict(Counter(f["week"] for i in usable for f in i["forecasts"])),
                   "forecast_weeks_skipped_after_deadline_or_season": sum(len(i["skipped_weeks"]) for i in infos),
                   "league_seasons_excluded_by_product": dict(Counter(i["excluded"] for i in infos if i.get("excluded"))),
                   "team_forecasts": len(teams), "viewers_by_outcome": dict(sum((Counter(f["viewers"]) for i in usable for f in i["forecasts"]), Counter())),
                   "re_simulated_candidates": len(rows), "listed_rows": sum(r["listed"] for r in rows),
                   "listed_rows_passing": sum(bool(r.get("passes")) for r in rows),
                   "null_draws": dict(Counter(r["kind"] for r in nulls)), "minutes": round((time.time() - started) / 60, 1)},
        "harness_checks": {
            "stats_scoring_vs_recorded_players_points": _total([i["stats_check"] for i in usable], ("checked", "mismatch")),
            "product_parity_rebuilt_lineups_vs_snapshot": {"team_weeks": sum(f["parity_checked"] for i in usable for f in i["forecasts"]),
                                                           "mismatches": sum(f["parity_mismatches"] for i in usable for f in i["forecasts"])},
            "snapshot_points_vs_replay_table": _total([f["points_parity"] for i in usable for f in i["forecasts"]], ("checked", "mismatch")),
            "exhaustive_dp_vs_lineup_gains": _total(checks, ("player_weeks_checked", "mismatches", "skipped_free_agent_or_idp_fill")),
            "recorded_scores_replay_vs_real_bracket": _total([i["recorded_replay_vs_bracket"] for i in usable], ("teams", "agree"))},
        **analyse(infos, rows, nulls, teams, args.reps, lineage)}
    Path(args.out).write_text(json.dumps(result, indent=1, default=str) + "\n")
    print(json.dumps(result["sample"], indent=1))
    print(json.dumps(result["harness_checks"], indent=1))


if __name__ == "__main__":
    main()
