"""Fit-first trade generation: two scorers, one generator (operator, 2026-10-09).

Plan: "Fit Scorecard Test Plan" (claude.ai doc), docs/plans/fit-scorecard/plan.md.
Instead of enumerating every fair package and ranking it, start from fit: every asset gets
a TEAM VALUE for every team, a trade is kept only when BOTH sides gain in their own team
value, and the value core's hard rules (band, filler, breakup, picks_for_players, roster,
lineup) still apply through core.evaluate_trade.

- Approach A (arm "fit_a"): team value = market x window x need x board multipliers.
- Approach B (arm "fit_b"): player grades (dynasty, redraft, fit profile) x team profiles
  (outlook, positional needs, redraft/dynasty priority); a trade pairs each side's sells
  with the other side's buys.

Pure: no logging, no I/O, no flag or config reads. The one network need (rest-of-season
projections for B's redraft grade) goes through `fetch_ros_points`, whose transport is
injected by the caller.
"""
from __future__ import annotations

import math
from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from typing import Callable, Mapping, Sequence

from .power_rankings import LINEUP_SLOT_ELIGIBILITY, optimal_starters
from .value_core import core
from .value_core.deck import idea_key, partner_cap
from .value_core.types import (CORE_POSITIONS, Board, CoreConfig, LeagueSnapshot, Request)

FIT_VERSION = "fit-1"
ARMS = ("fit_a", "fit_b")
DECK_SIZE = 20
CANDIDATES_PER_SIDE = 6       # top give / receive candidates per partner, by fit arbitrage
OK_PER_PARTNER = 30           # stop evaluating a partner once this many trades pass the rules
ASSET_CAP = 3                 # most cards any one asset may appear in
RATIO_PREFILTER = (0.70, 1.45)  # raw consensus receive/give window before the hard rules
YOUNG_AGE, OLD_AGE = 24, 29
WINDOWS = ("contender", "middle", "rebuilder")

# Approach A multipliers (plan doc, frozen 2026-10-09 before the first run).
A_WINDOW = {
    "contender": {"start": 1.3, "depth": 0.7, "young": 1.0, "old": 1.0, "pick": 0.6},
    "middle":    {"start": 1.15, "depth": 0.85, "young": 1.1, "old": 0.85, "pick": 1.0},
    "rebuilder": {"start": 1.0, "depth": 1.0, "young": 1.3, "old": 0.5, "pick": 1.3},
}
A_NEED = {"contender": {"thin": 1.2, "surplus": 0.8}, "middle": {"thin": 1.2, "surplus": 0.8},
          "rebuilder": {"thin": 1.1, "surplus": 0.9}}
BOARD_CLAMP = (0.67, 1.5)

# Approach B weights (plan doc, frozen 2026-10-09).
B_PRIORITY = {"contender": (0.7, 0.3), "middle": (0.5, 0.5), "rebuilder": (0.2, 0.8)}  # (redraft, dynasty)
B_NEED = {"thin": 1.1, "surplus": 0.9}
PROFILE_GAP = 15.0            # redraft pct - dynasty pct beyond which a player is Win-now / Future

# Share of each flex slot credited to a position when sizing positional demand.
FLEX_SHARE = {"FLEX": {"RB": 0.4, "WR": 0.5, "TE": 0.1},
              "SUPER_FLEX": {"QB": 0.8, "RB": 0.08, "WR": 0.1, "TE": 0.02},
              "WRRB_FLEX": {"RB": 0.5, "WR": 0.5}, "REC_FLEX": {"WR": 0.8, "TE": 0.2}}


# ---------------------------------------------------------------------------
# Shared league facts
# ---------------------------------------------------------------------------

def slot_demand(lineup_slots: Sequence[str]) -> dict[str, float]:
    """Starters per team each position fills: dedicated slots count 1, flex slots by share."""
    out = {p: 0.0 for p in CORE_POSITIONS}
    for s in lineup_slots:
        if s in CORE_POSITIONS:
            out[s] += 1.0
        for p, share in FLEX_SHARE.get(s, {}).items():
            out[p] += share
    return out


@dataclass
class League:
    """Per-snapshot facts both scorers read. Built once per (snapshot, viewer)."""
    snapshot: LeagueSnapshot
    slots: list[str]
    demand: dict[str, float]
    owner: dict[str, str]                       # asset id -> team id
    need: dict[str, dict[str, str]]             # team id -> {pos: thin|balanced|surplus}
    starters: dict[str, frozenset[str]]         # team id -> current value-optimal starters
    _start_cache: dict = field(default_factory=dict)

    def window(self, team_id: str) -> str:
        w = self.snapshot.teams[team_id].window.window
        return w if w in WINDOWS else "middle"

    def would_start(self, team_id: str, asset_id: str) -> bool:
        """Is the player in the team's value-optimal lineup (with him added if he is not theirs)?"""
        a = self.snapshot.assets[asset_id]
        if a.kind != "player":
            return False
        if self.owner.get(asset_id) == team_id:
            return asset_id in self.starters[team_id]
        key = (team_id, asset_id)
        if key not in self._start_cache:
            ids = list(self.snapshot.teams[team_id].asset_ids) + [asset_id]
            self._start_cache[key] = asset_id in set(optimal_starters(_rows(self.snapshot, ids),
                                                                     self.slots))
        return self._start_cache[key]


def _rows(snapshot: LeagueSnapshot, ids: Sequence[str]) -> list[dict]:
    return [{"player_id": i, "position": snapshot.assets[i].position, "value": snapshot.assets[i].market}
            for i in ids if snapshot.assets[i].kind == "player" and snapshot.assets[i].position in CORE_POSITIONS]


def build_league(snapshot: LeagueSnapshot) -> League:
    slots = [s for s in snapshot.rules.lineup_slots if s in LINEUP_SLOT_ELIGIBILITY]
    demand = slot_demand(slots)
    owner = {a: t for t, team in snapshot.teams.items() for a in team.asset_ids}
    n_teams = max(1, len(snapshot.teams))
    by_pos: dict[str, list[tuple[float, str]]] = {p: [] for p in CORE_POSITIONS}
    for a in snapshot.assets.values():
        if a.kind == "player" and a.position in by_pos and a.id in owner:
            by_pos[a.position].append((-a.market, a.id))
    startable: set[str] = set()
    for p, lst in by_pos.items():
        lst.sort()
        cut = math.ceil(n_teams * demand[p])
        startable.update(i for _, i in lst[:cut])
    need: dict[str, dict[str, str]] = {}
    for t, team in snapshot.teams.items():
        counts = Counter(snapshot.assets[a].position for a in team.asset_ids if a in startable)
        need[t] = {}
        for p in CORE_POSITIONS:
            want = round(demand[p])
            have = counts.get(p, 0)
            need[t][p] = "thin" if have < want else "surplus" if have >= want + 2 else "balanced"
    starters = {t: frozenset(optimal_starters(_rows(snapshot, team.asset_ids), slots))
                for t, team in snapshot.teams.items()}
    return League(snapshot, slots, demand, owner, need, starters)


# ---------------------------------------------------------------------------
# Approach A — team value multipliers
# ---------------------------------------------------------------------------

def board_ratio(board: Board | None, asset_id: str, market: float) -> float:
    if board is None or market <= 0 or asset_id not in board.values:
        return 1.0
    lo, hi = BOARD_CLAMP
    return min(hi, max(lo, board.values[asset_id] / market))


def team_value_a(league: League, team_id: str, asset_id: str, board: Board | None) -> float:
    a = league.snapshot.assets[asset_id]
    w = A_WINDOW[league.window(team_id)]
    if a.kind == "pick":
        return a.market * w["pick"] * board_ratio(board, asset_id, a.market)
    mult = w["start"] if league.would_start(team_id, asset_id) else w["depth"]
    if a.age is not None:
        mult *= w["young"] if a.age <= YOUNG_AGE else w["old"] if a.age >= OLD_AGE else 1.0
    state = league.need[team_id].get(a.position, "balanced")
    mult *= A_NEED[league.window(team_id)].get(state, 1.0)
    return a.market * mult * board_ratio(board, asset_id, a.market)


# ---------------------------------------------------------------------------
# Approach B — player grades and team profiles
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Grades:
    dynasty_pct: dict[str, float]      # asset id -> 0..100
    redraft_pct: dict[str, float]      # asset id -> 0..100 (picks 0)
    redraft_value: dict[str, float]    # asset id -> redraft grade mapped onto the market scale
    profile: dict[str, str]            # asset id -> win_now | balanced | future


def _pct(values: Mapping[str, float]) -> dict[str, float]:
    """0..100 percentile rank (ties share the lower rank)."""
    if not values:
        return {}
    ordered = sorted(values.values())
    n = len(ordered)
    return {k: 100.0 * bisect_left(ordered, v) / max(1, n - 1) for k, v in values.items()}


def build_grades(league: League, ros_points: Mapping[str, float], scoring_format: str) -> Grades:
    """Dynasty = market percentile over league assets. Redraft = value over replacement on
    rest-of-season projected points (replacement = the first player past the league's
    starters at that position), as a percentile over league players, then mapped onto the
    market scale by quantile so it adds like market value. Profile from the gap."""
    snap = league.snapshot
    league_assets = [a for a in snap.assets.values() if a.id in league.owner and a.market > 0]
    dynasty = _pct({a.id: a.market for a in league_assets})
    n_teams = max(1, len(snap.teams))
    vor: dict[str, float] = {}
    for p in CORE_POSITIONS:
        pts = sorted(((ros_points.get(a.id, 0.0), a.id) for a in snap.assets.values()
                      if a.kind == "player" and a.position == p and a.id in league.owner), reverse=True)
        cut = math.ceil(n_teams * league.demand[p])
        repl = pts[cut][0] if len(pts) > cut else (pts[-1][0] if pts else 0.0)
        for v, i in pts:
            vor[i] = max(0.0, v - repl)
    redraft = _pct(vor)
    markets = sorted(a.market for a in league_assets)

    def quantile(pct: float) -> float:
        if not markets:
            return 0.0
        return markets[min(len(markets) - 1, int(round(pct / 100.0 * (len(markets) - 1))))]

    redraft_value, profile = {}, {}
    for a in league_assets:
        r = redraft.get(a.id, 0.0) if a.kind == "player" else 0.0
        redraft_value[a.id] = quantile(r) if a.kind == "player" and vor.get(a.id, 0.0) > 0 else 0.0
        if a.kind == "pick":
            profile[a.id] = "future"
        else:
            gap = r - dynasty.get(a.id, 0.0)
            profile[a.id] = "win_now" if gap >= PROFILE_GAP else "future" if gap <= -PROFILE_GAP else "balanced"
    redraft_pct = {a.id: (redraft.get(a.id, 0.0) if a.kind == "player" else 0.0) for a in league_assets}
    return Grades(dynasty, redraft_pct, redraft_value, profile)


def team_value_b(league: League, grades: Grades, team_id: str, asset_id: str,
                 board: Board | None) -> float:
    """Priority blend of redraft and dynasty value, x0.9-1.1 for positional need. `board`
    (the viewer's own) replaces consensus in the dynasty term; partners use consensus."""
    a = league.snapshot.assets[asset_id]
    w_r, w_d = B_PRIORITY[league.window(team_id)]
    dynasty = board.values.get(asset_id, a.market) if board is not None else a.market
    v = w_r * grades.redraft_value.get(asset_id, 0.0) + w_d * dynasty
    if a.kind == "player":
        v *= B_NEED.get(league.need[team_id].get(a.position, "balanced"), 1.0)
    return v


def b_sells(league: League, grades: Grades, team_id: str, asset_id: str) -> bool:
    """A team sells what clashes with its priority, or sits at a surplus position."""
    window, prof = league.window(team_id), grades.profile.get(asset_id, "balanced")
    a = league.snapshot.assets[asset_id]
    if (window == "rebuilder" and prof == "win_now") or (window == "contender" and prof == "future"):
        return True
    return a.kind == "player" and league.need[team_id].get(a.position) == "surplus"


def b_buys(league: League, grades: Grades, team_id: str, asset_id: str) -> bool:
    """A team buys what matches its priority and does not land at a surplus position."""
    window, prof = league.window(team_id), grades.profile.get(asset_id, "balanced")
    a = league.snapshot.assets[asset_id]
    if (window == "rebuilder" and prof == "win_now") or (window == "contender" and prof == "future"):
        return False
    return not (a.kind == "player" and league.need[team_id].get(a.position) == "surplus")


# ---------------------------------------------------------------------------
# Scoring and generation (shared)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FitTrade:
    partner_team_id: str
    give: tuple[str, ...]
    receive: tuple[str, ...]
    gain_viewer: float               # viewer's team-value gain / consensus size of the trade
    gain_partner: float
    mutual: float                    # min of the two

    @property
    def key(self) -> tuple:
        return (self.partner_team_id, frozenset(self.give), frozenset(self.receive))


class Scorer:
    """One approach's team values for one viewer: value(team, asset) memoised."""

    def __init__(self, arm: str, league: League, request: Request,
                 grades: Grades | None = None):
        if arm == "fit_b" and grades is None:
            raise ValueError("fit_b needs grades")
        self.arm, self.league, self.request, self.grades = arm, league, request, grades
        self._memo: dict[tuple[str, str], float] = {}

    def board(self, team_id: str) -> Board | None:
        if team_id == self.request.viewer_team_id:
            return self.request.board
        return self.league.snapshot.partner_boards.get(team_id) if self.arm == "fit_a" else None

    def value(self, team_id: str, asset_id: str) -> float:
        k = (team_id, asset_id)
        if k not in self._memo:
            if self.arm == "fit_a":
                self._memo[k] = team_value_a(self.league, team_id, asset_id, self.board(team_id))
            else:
                self._memo[k] = team_value_b(self.league, self.grades, team_id, asset_id,
                                             self.board(team_id))
        return self._memo[k]

    def gains(self, partner: str, give: Sequence[str], receive: Sequence[str]) -> tuple[float, float]:
        """(viewer gain, partner gain), each in its own team value, over the trade's mean
        consensus side. Positive = that team comes out ahead by its own needs."""
        v = self.request.viewer_team_id
        mk = self.league.snapshot.assets
        size = (sum(mk[a].market for a in give) + sum(mk[a].market for a in receive)) / 2.0
        if size <= 0:
            return 0.0, 0.0
        gv = (sum(self.value(v, a) for a in receive) - sum(self.value(v, a) for a in give)) / size
        gp = (sum(self.value(partner, a) for a in give) - sum(self.value(partner, a) for a in receive)) / size
        return gv, gp

    def candidates(self, giver: str, taker: str, exclude: frozenset[str]) -> list[str]:
        """The giver's assets the taker values most above the giver (relative to market).
        B: only assets that are the giver's sells and the taker's buys."""
        snap = self.league.snapshot
        out = []
        for a in snap.teams[giver].asset_ids:
            asset = snap.assets[a]
            if a in exclude or asset.market < core_floor():
                continue
            if self.arm == "fit_b" and not (b_sells(self.league, self.grades, giver, a)
                                            and b_buys(self.league, self.grades, taker, a)):
                continue
            edge = (self.value(taker, a) - self.value(giver, a)) / asset.market
            if edge > 0:
                out.append((-edge, a))
        out.sort()
        return [a for _, a in out[:CANDIDATES_PER_SIDE]]


_CFG = CoreConfig()


def core_floor() -> float:
    return _CFG.asset_floor_abs


def _packages(ids: Sequence[str]) -> list[tuple[str, ...]]:
    return [c for k in range(1, core.MAX_PACKAGE_SIZE + 1) for c in combinations(ids, k)]


def generate(snapshot: LeagueSnapshot, request: Request, scorer: Scorer,
             cfg: CoreConfig = _CFG) -> tuple[list[FitTrade], dict]:
    """Fit-first trades for the viewer against every partner: candidate gives/receives by fit
    edge, 1-3 x 1-3 packages, both sides must gain in their own team value, consensus ratio
    inside RATIO_PREFILTER, then core.evaluate_trade's hard rules. Best mutual fit first."""
    viewer = request.viewer_team_id
    mk = snapshot.assets
    lo, hi = RATIO_PREFILTER
    out: list[FitTrade] = []
    diag = Counter()
    for pid in sorted(t for t in snapshot.teams if t != viewer):
        gives = _packages(scorer.candidates(viewer, pid, frozenset()))
        recvs = _packages(scorer.candidates(pid, viewer, request.not_interested_ids))
        if not gives or not recvs:
            diag["partners_without_candidates"] += 1
            continue
        pool = []
        for g in gives:
            g_total = sum(mk[a].market for a in g)
            for r in recvs:
                ratio = sum(mk[a].market for a in r) / g_total
                if not lo <= ratio <= hi:
                    continue
                gv, gp = scorer.gains(pid, g, r)
                if gv > 0 and gp > 0:
                    pool.append((min(gv, gp), gv, gp, g, r))
        diag["mutual_pairs"] += len(pool)
        pool.sort(key=lambda x: (-x[0], -x[1], x[3], x[4]))
        ok = 0
        for mutual, gv, gp, g, r in pool:
            if ok >= OK_PER_PARTNER:
                break
            verdict = core.evaluate_trade(snapshot, request, cfg, partner_team_id=pid,
                                          give=list(g), receive=list(r))
            if not verdict.ok:
                diag[f"rejected_{verdict.reason}"] += 1
                continue
            t = verdict.trade
            out.append(FitTrade(pid, t.give, t.receive, round(gv, 4), round(gp, 4), round(mutual, 4)))
            ok += 1
    out.sort(key=lambda t: (-t.mutual, -t.gain_viewer, t.partner_team_id, t.give, t.receive))
    diag["pool"] = len(out)
    return out, dict(diag)


def assemble(trades: Sequence[FitTrade], snapshot: LeagueSnapshot, size: int = DECK_SIZE) -> list[FitTrade]:
    """Variety: one card per trade idea (partner, give headliner, receive headliner; picks
    collapsed), a partner cap, and at most ASSET_CAP cards per asset. Greedy in mutual order."""
    n_partners = len({t.partner_team_id for t in trades})
    cap = partner_cap(n_partners)
    ideas, per_partner, per_asset, deck = set(), Counter(), Counter(), []
    for t in trades:
        k = idea_key(t, snapshot)  # duck-typed: partner_team_id, give, receive
        if k in ideas or per_partner[t.partner_team_id] >= cap:
            continue
        if any(per_asset[a] >= ASSET_CAP for a in (*t.give, *t.receive)):
            continue
        ideas.add(k)
        per_partner[t.partner_team_id] += 1
        per_asset.update((*t.give, *t.receive))
        deck.append(t)
        if len(deck) >= size:
            break
    return deck


# ---------------------------------------------------------------------------
# Rest-of-season projections (B's redraft grade) — the only I/O, transport injected
# ---------------------------------------------------------------------------

LAST_FANTASY_WEEK = 17


def fetch_ros_points(fetch_json: Callable[[str], object], scoring_format: str,
                     season: int | None = None, week: int | None = None) -> dict:
    """{"season", "from_week", "weeks", "points": {player_id: rest-of-season points}} from
    Sleeper's weekly projections (the feed season_forecasts.py already reads). PPR points;
    sf_tep adds 0.5 per TE reception. Season/week default to Sleeper's NFL state."""
    if season is None or week is None:
        state = fetch_json("https://api.sleeper.app/v1/state/nfl") or {}
        season = int(season or state.get("season") or 0)
        week = int(week or state.get("week") or 1)
    weeks = list(range(max(1, week), LAST_FANTASY_WEEK + 1))
    points: dict[str, float] = {}
    for w in weeks:
        url = (f"https://api.sleeper.app/projections/nfl/{season}/{w}?season_type=regular"
               "&position[]=QB&position[]=RB&position[]=WR&position[]=TE&order_by=pts_ppr")
        try:
            rows = fetch_json(url)
        except Exception:
            continue
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            stats = row.get("stats") or {}
            pid = str(row.get("player_id") or "")
            if not pid:
                continue
            pts = float(stats.get("pts_ppr") or 0.0)
            pos = (row.get("player") or {}).get("position")
            if scoring_format == "sf_tep" and pos == "TE":
                pts += 0.5 * float(stats.get("rec") or 0.0)
            points[pid] = points.get(pid, 0.0) + pts
    return {"season": season, "from_week": week, "weeks": len(weeks), "points": points}
