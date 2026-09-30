"""Three-weight ranking for the value-core engine (docs/plans/value-core-engine/lld.md 5.2-5.5).

Scores every fair trade on value, outlook and rank, each in [0, 1], and combines them into
a weighted-mean priority. card_reasons turns a scored trade into 1-3 card lines.
Deterministic, no logging, no I/O.
"""
from __future__ import annotations

import math
import statistics
from typing import Iterable, Mapping, Sequence

from ..power_rankings import optimal_starters
from .types import (CORE_POSITIONS, Asset, FairTrade, LeagueSnapshot, RankConfig, Request,
                    Scores, ScoredTrade)

DELTA_SATURATION = math.log(1.25)
RANK_GAP_SATURATION = 0.30
SIDE_THRESHOLD = 0.60
FAIR_PCT = 3
RANK_SPOTS_MIN = 5
YOUTH_WEIGHTS = ((24, 1.0), (26, 0.7), (28, 0.4))   # age <= k -> weight; older -> 0.15; picks 1.0; unknown 0.5


def _clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


def youth_weight(asset: Asset) -> float:
    if asset.kind == "pick":
        return 1.0
    if asset.age is None:
        return 0.5
    for max_age, weight in YOUTH_WEIGHTS:
        if asset.age <= max_age:
            return weight
    return 0.15


def lineup_value(asset_ids: Iterable[str], snapshot: LeagueSnapshot) -> tuple[float, frozenset[str]]:
    """(sum of market over the value-optimal starters, starter ids) via
    power_rankings.optimal_starters on core-position players (power_rankings.py:99)."""
    rows = []
    for aid in asset_ids:
        a = snapshot.assets[aid]
        if a.kind == "player" and a.position in CORE_POSITIONS:
            rows.append({"player_id": a.id, "position": a.position, "value": a.market})
    starters = optimal_starters(rows, list(snapshot.rules.lineup_slots))
    return sum(snapshot.assets[s].market for s in starters), frozenset(starters)


def positional_ranks(snapshot: LeagueSnapshot, values: Mapping[str, float]) -> dict[str, int]:
    """1-based rank of every player asset within its position by (-value, id). Picks absent."""
    by_pos: dict[str, list[str]] = {}
    for a in snapshot.assets.values():
        if a.kind == "player":
            by_pos.setdefault(a.position, []).append(a.id)
    ranks: dict[str, int] = {}
    for ids in by_pos.values():
        ids.sort(key=lambda i: (-values[i], i))
        for r, i in enumerate(ids, start=1):
            ranks[i] = r
    return ranks


def score_trades(snapshot: LeagueSnapshot, request: Request, trades: Sequence[FairTrade],
                 cfg: RankConfig) -> list[ScoredTrade]:
    """Same length and order as `trades`. Raises ValueError if cfg weights sum <= 0."""
    w_sum = cfg.w_value + cfg.w_outlook + cfg.w_rank
    if w_sum <= 0:
        raise ValueError(f"RankConfig weights sum to {w_sum}; need > 0")

    assets = snapshot.assets
    viewer = snapshot.teams[request.viewer_team_id]
    pre = {tid: lineup_value(t.asset_ids, snapshot) for tid, t in snapshot.teams.items()}
    starter_markets = [assets[s].market for _, starters in pre.values() for s in starters]
    scale = statistics.median(starter_markets) if starter_markets else 0.0
    if scale <= 0:
        scale = 1000.0

    consensus_rank = positional_ranks(snapshot, {aid: a.market for aid, a in assets.items()})
    board = request.board
    if board is not None:
        personal = {aid: board.values.get(aid, a.market) for aid, a in assets.items()}
        personal_rank = positional_ranks(snapshot, personal)

    def after(team_id: str, out: tuple[str, ...], into: tuple[str, ...]) -> list[str]:
        gone = set(out)
        return [a for a in snapshot.teams[team_id].asset_ids if a not in gone] + list(into)

    def side(team_id: str, out: tuple[str, ...], into: tuple[str, ...]) -> tuple[float, dict]:
        lineup_gain = lineup_value(after(team_id, out, into), snapshot)[0] - pre[team_id][0]
        future_gain = (sum(assets[a].market * youth_weight(assets[a]) for a in into)
                       - sum(assets[a].market * youth_weight(assets[a]) for a in out))
        s_con = _clamp01(0.5 + 0.5 * lineup_gain / scale)
        s_reb = _clamp01(0.5 + 0.5 * future_gain / scale)
        window = snapshot.teams[team_id].window.window
        score = s_con if window == "contender" else s_reb if window == "rebuilder" else (s_con + s_reb) / 2
        return score, {"window": window, "lineup_gain": round(lineup_gain, 4),
                       "future_gain": round(future_gain, 4), "score": round(score, 4)}

    out: list[ScoredTrade] = []
    for t in trades:
        # Value.
        delta_ln = math.log(t.receive_market / t.give_market)
        s_delta = _clamp01(0.5 + delta_ln / (2 * DELTA_SATURATION))
        b = min(t.receive, key=lambda a: (-assets[a].market, a))
        post_starters = lineup_value(after(viewer.team_id, t.give, t.receive), snapshot)[1]
        best_in_starter = assets[b].kind == "player" and b in post_starters
        if best_in_starter or assets[b].market >= snapshot.first_round_value:
            s_piece = 1.0
        else:
            s_piece = assets[b].market / snapshot.first_round_value
        value = 0.5 * s_delta + 0.5 * s_piece

        # Outlook.
        v_score, v_side = side(viewer.team_id, t.give, t.receive)
        p_score, p_side = side(t.partner_team_id, t.receive, t.give)
        outlook = (v_score + p_score) / 2

        # Rank.
        if board is None:
            rank, gap_rel, top, top_side, rank_delta = 0.5, 0.0, None, None, None
        else:
            contrib = {a: personal[a] - assets[a].market for a in t.receive}
            contrib.update({a: assets[a].market - personal[a] for a in t.give})
            gap_rel = sum(contrib.values()) / ((t.give_market + t.receive_market) / 2)
            rank = _clamp01(0.5 + gap_rel / (2 * RANK_GAP_SATURATION))
            positive = [a for a, c in contrib.items() if c > 0 and assets[a].kind == "player"]
            top = min(positive, key=lambda a: (-contrib[a], a)) if positive else None
            if top is None:
                top_side, rank_delta = None, None
            else:
                top_side = "receive" if top in t.receive else "give"
                rank_delta = consensus_rank[top] - personal_rank[top]

        priority = (cfg.w_value * value + cfg.w_outlook * outlook + cfg.w_rank * rank) / w_sum
        detail = {
            "value": {"delta_ln": round(delta_ln, 4), "s_delta": round(s_delta, 4),
                      "best_in_id": b, "best_in_market": round(assets[b].market, 4),
                      "best_in_starter": best_in_starter, "s_piece": round(s_piece, 4)},
            "outlook": {"scale": round(scale, 4), "viewer": v_side, "partner": p_side},
            "rank": {"has_board": board is not None, "gap_rel": round(gap_rel, 4),
                     "top_asset": top, "top_side": top_side, "rank_delta": rank_delta},
        }
        out.append(ScoredTrade(t, Scores(value, outlook, rank, priority), detail))
    return out


def card_reasons(scored: ScoredTrade, snapshot: LeagueSnapshot, request: Request) -> tuple[str, ...]:
    """1-3 strings, templates in §5.5."""
    t, d = scored.trade, scored.detail
    reasons: list[str] = []

    pct = round(100 * (t.receive_market / t.give_market - 1))
    if abs(pct) <= FAIR_PCT:
        reasons.append("Fair on value")
    elif pct > FAIR_PCT:
        reasons.append(f"You get {pct}% more market value")
    else:
        reasons.append(f"You pay {-pct}% over market")

    partner, viewer = d["outlook"]["partner"], d["outlook"]["viewer"]
    if partner["score"] >= SIDE_THRESHOLD:
        reasons.append({"rebuilder": "Fits their rebuild", "contender": "Helps their title push",
                        "middle": "Works for their roster"}[partner["window"]])
    elif viewer["score"] >= SIDE_THRESHOLD:
        reasons.append({"contender": "Upgrades your starting lineup",
                        "rebuilder": "Adds youth for your rebuild",
                        "middle": "Works for your roster"}[viewer["window"]])

    r = d["rank"]
    if r["has_board"] and r["top_asset"] is not None:
        name = snapshot.assets[r["top_asset"]].name
        if r["top_side"] == "receive" and r["rank_delta"] >= RANK_SPOTS_MIN:
            reasons.append(f"You rank {name} {r['rank_delta']} spots above market")
        elif r["top_side"] == "give" and r["rank_delta"] <= -RANK_SPOTS_MIN:
            reasons.append(f"You rank {name} {-r['rank_delta']} spots below market")

    if len(reasons) < 3:
        v = d["value"]
        best_in = snapshot.assets[v["best_in_id"]]
        if v["best_in_starter"]:
            reasons.append(f"{best_in.name} would start for you")
        elif best_in.market >= snapshot.first_round_value:
            reasons.append("Brings back 1st-round value")
    return tuple(reasons)
