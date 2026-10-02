"""App objects -> value-core contract -> TradeCard + impression evidence.

docs/plans/value-core-engine/lld.md section 7. The only value-core module that
imports app code (trade_service, ranking_service); it never imports
backend.server. Logs one thing: a duplicate asset id across rosters.
"""
from __future__ import annotations

import logging
import uuid
from typing import Iterable, Mapping, Sequence

from ..ranking_service import RankingService
from ..trade_service import TradeCard, _shrink_user_elo, elo_to_value
from .types import (
    CORE_POSITIONS,
    DEFAULT_WINDOW,
    ENGINE_ID,
    ENGINE_VERSION,
    Asset,
    Board,
    CoreConfig,
    DeckEntry,
    LeagueSnapshot,
    PipelineResult,
    RankConfig,
    Request,
    RosterRules,
    Team,
    TeamWindow,
)

log = logging.getLogger(__name__)

DEFAULT_LINEUP = ("QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX")   # mirrors server._PLATFORM_DEFAULT_LINEUP (server.py:18023)

EVIDENCE_SCHEMA_VERSION = 1
DEFAULT_STANDINGS_WEIGHT = 0.30


def _num(cfg: Mapping[str, float], key: str, default: float, lo: float | None = None,
         hi: float | None = None) -> float:
    v = float(cfg.get(key, default))
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _int(cfg: Mapping[str, float], key: str, default: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(float(cfg.get(key, default))))))


def core_config_from(cfg: Mapping[str, float]) -> CoreConfig:
    """lld section 3 keys with their clamps; a missing key keeps the dataclass default."""
    d = CoreConfig()
    return CoreConfig(
        band=_num(cfg, "vc_band", d.band, 0.01, 0.50),
        gain_band=_num(cfg, "vc_gain_band", d.gain_band, 0.01, 0.50),
        stud_premium=_num(cfg, "vc_stud_premium", d.stud_premium, 0.0, 0.50),
        untouchable_min_ratio=_num(cfg, "vc_untouchable_min_ratio", d.untouchable_min_ratio, 1.0, 2.0),
        max_assets_per_side=_int(cfg, "vc_max_assets_per_side", d.max_assets_per_side, 4, 20),
        max_per_partner=_int(cfg, "vc_max_per_partner", d.max_per_partner, 10, 1000),
        asset_floor_abs=_num(cfg, "asset_floor_abs", d.asset_floor_abs),
        filler_min_frac=_num(cfg, "filler_min_frac", d.filler_min_frac),
        throwin_min_ratio=_num(cfg, "vc_throwin_min_ratio", d.throwin_min_ratio, 1.0, 10.0),
    )


def rank_config_from(cfg: Mapping[str, float]) -> RankConfig:
    """Weights clamp at >= 0; all three at 0 become (1, 1, 1)."""
    d = RankConfig()
    w = (_num(cfg, "vc_w_value", d.w_value, 0.0),
         _num(cfg, "vc_w_outlook", d.w_outlook, 0.0),
         _num(cfg, "vc_w_rank", d.w_rank, 0.0))
    if sum(w) <= 0:
        w = (1.0, 1.0, 1.0)
    return RankConfig(
        w_value=w[0], w_outlook=w[1], w_rank=w[2],
        repeat_penalty=_num(cfg, "vc_repeat_penalty", d.repeat_penalty, 0.0, 1.0),
        player_cap=_int(cfg, "vc_player_cap", d.player_cap, 1, 30),
    )


def standings_weight_from(cfg: Mapping[str, float]) -> float:
    """vc_standings_weight, clamped to [0, 1]."""
    return _num(cfg, "vc_standings_weight", DEFAULT_STANDINGS_WEIGHT, 0.0, 1.0)


def default_lineup_slots(scoring_format: str) -> tuple[str, ...]:
    """DEFAULT_LINEUP + ("SUPER_FLEX",) when scoring_format == "sf_tep"."""
    return DEFAULT_LINEUP + (("SUPER_FLEX",) if scoring_format == "sf_tep" else ())


def tier_values(scoring_format: str) -> tuple[float, float]:
    """(first_round_value, elite_value) = elo_to_value of the lower Elo bound of tiers
    first_1 and firsts_4plus from RankingService.tier_bands_for(None, scoring_format)
    (ranking_service.py:1768; today 1580 -> ~1492, 1927 -> ~8457)."""
    bands = RankingService.tier_bands_for(None, scoring_format)
    return elo_to_value(bands["first_1"][0]), elo_to_value(bands["firsts_4plus"][0])


def build_snapshot(*, league_id: str, scoring_format: str, viewer_team_id: str, viewer_name: str,
                   viewer_roster: Sequence[str], opponents: Sequence[object],
                   players: Mapping[str, object], seed_elo: Mapping[str, float],
                   lineup_slots: Sequence[str] | None, max_players: int | None,
                   windows: Mapping[str, TeamWindow],
                   partner_boards: Mapping[str, Board] | None = None) -> LeagueSnapshot:
    """The viewer's team is inserted FIRST into `teams` (build_request relies on it).
    Market is raw elo_to_value(seed) with no age preference; an unseeded asset is 0.0.
    `partner_boards` (team_id -> partner_board_from(...)) is cut to known partners and assets."""
    assets: dict[str, Asset] = {}
    owner: dict[str, str] = {}
    teams: dict[str, Team] = {}
    rosters = [(str(viewer_team_id), viewer_name, viewer_roster)]
    rosters += [(str(m.user_id), m.username, m.roster) for m in opponents]
    for team_id, name, roster in rosters:
        ids: list[str] = []
        other = 0
        for pid in roster:
            p = players.get(pid)
            position = getattr(p, "position", None)
            if p is None or (position != "PICK" and position not in CORE_POSITIONS):
                other += 1
                continue
            if pid in owner:
                if owner[pid] != team_id:
                    log.warning("value-core: asset %s on rosters %s and %s; keeping the first",
                                pid, owner[pid], team_id)
                continue
            market = elo_to_value(seed_elo[pid]) if pid in seed_elo else 0.0
            if position == "PICK":
                assets[pid] = Asset(pid, "pick", "PICK", p.name, None, market)
            else:
                assets[pid] = Asset(pid, "player", position, p.name,
                                    float(p.age) if p.age else None, market)
            owner[pid] = team_id
            ids.append(pid)
        teams[team_id] = Team(team_id, name, tuple(ids), other, windows.get(team_id, DEFAULT_WINDOW))
    first_round_value, elite_value = tier_values(scoring_format)
    boards = {}
    for team_id, b in (partner_boards or {}).items():
        values = {a: v for a, v in b.values.items() if a in assets}
        if str(team_id) in teams and str(team_id) != str(viewer_team_id) and values:
            boards[str(team_id)] = Board(values, {a: b.comparisons.get(a, 0) for a in values})
    return LeagueSnapshot(
        league_id, scoring_format, assets, teams,
        RosterRules(tuple(lineup_slots or default_lineup_slots(scoring_format)), max_players),
        first_round_value, elite_value, boards)


def partner_board_from(*, elo_ratings: Mapping[str, float] | None, seed_elo: Mapping[str, float],
                       comparison_counts: Mapping[str, int] | None = None,
                       confidence_source: str | None = None,
                       confidence_weights: Mapping[str, float] | None = None,
                       confidence_sources: Mapping[str, str] | None = None) -> Board | None:
    """A leaguemate's PUBLISHED board (call only for members whose Elo came from real
    member_rankings rows, server has_rankings), shrunk by the personal-market policy's
    symmetric rule: trade_policy.shrink_board with trade_policy.confidence_map. No evidence on
    a player prices him at consensus, so a thin board can never qualify a throw-in."""
    if not elo_ratings:
        return None
    from .. import trade_policy
    conf = trade_policy.confidence_map(dict(comparison_counts or {}) or None,
                                       source=confidence_source,
                                       weights=dict(confidence_weights or {}) or None,
                                       sources=dict(confidence_sources or {}) or None)
    effective = trade_policy.shrink_board(dict(elo_ratings), dict(seed_elo), conf)
    values = {a: elo_to_value(e) for a, e in effective.items()}
    return Board(values=values, comparisons={a: int((comparison_counts or {}).get(a, 0)) for a in values})


def build_request(*, snapshot: LeagueSnapshot, user_elo: Mapping[str, float] | None,
                  seed_elo: Mapping[str, float], confidence: Mapping[str, int] | None,
                  placements: Mapping[str, tuple[float, float]] | None,
                  untouchable_ids: Iterable[str], not_interested_ids: Iterable[str],
                  pinned_give: Iterable[str], pinned_give_mode: str,
                  pinned_receive: Iterable[str], partner_team_id: str | None,
                  fairness_threshold: float | None) -> Request:
    """The viewer is the first team of `snapshot.teams` (build_snapshot inserts it first).
    The board is the viewer's Elo shrunk toward consensus by trade_service._shrink_user_elo
    (w = n/(n+4)); None when the viewer has no board. Id sets are cut to snapshot assets."""
    board = None
    if user_elo:
        shrunk = _shrink_user_elo(dict(user_elo), dict(seed_elo),
                                  dict(confidence) if confidence else None,
                                  dict(placements) if placements else None)
        values = {a: elo_to_value(shrunk[a]) for a in snapshot.assets if a in shrunk}
        board = Board(values=values,
                      comparisons={a: int((confidence or {}).get(a, 0)) for a in values})

    def known(ids: Iterable[str]) -> frozenset[str]:
        return frozenset(i for i in ids if i in snapshot.assets)

    return Request(
        viewer_team_id=next(iter(snapshot.teams)),
        board=board,
        untouchable_ids=known(untouchable_ids),
        not_interested_ids=known(not_interested_ids),
        pinned_give_ids=known(pinned_give),
        pinned_give_mode="all" if pinned_give_mode == "all" else "any",
        pinned_receive_ids=known(pinned_receive),
        partner_team_id=partner_team_id,
        fairness_threshold=fairness_threshold,
    )


def _effective_band(band: float, fairness_threshold: float | None) -> float:
    # Mirrors core.effective_band (lld section 4.1) without importing core.
    if fairness_threshold is None:
        return band
    return min(band, max(0.02, 1 - fairness_threshold))


def _window(w: TeamWindow) -> dict:
    return {"window": w.window, "score": w.score, "source": w.source,
            "pf_index": w.pf_index, "standings_weight": w.standings_weight}


def _throwin_evidence(t, snapshot: LeagueSnapshot, request: Request) -> dict | None:
    if t.throwin is None:
        return None
    to_viewer = t.throwin in t.receive
    board = request.board if to_viewer else snapshot.partner_boards.get(t.partner_team_id)
    value = board.values.get(t.throwin) if board is not None else None
    return {"id": t.throwin, "recipient": "viewer" if to_viewer else "partner",
            "market": round(snapshot.assets[t.throwin].market, 1),
            "recipient_value": round(value, 1) if value is not None else None}


def evidence(entry: DeckEntry, snapshot: LeagueSnapshot, request: Request,
             core_cfg: CoreConfig, rank_cfg: RankConfig, *, budget_exhausted: bool) -> dict:
    """deck_impressions.valuation_json, schema v1 (lld section 7.3)."""
    t = entry.scored.trade
    s = entry.scored.scores
    band = _effective_band(core_cfg.band, request.fairness_threshold)
    gain = _effective_band(core_cfg.gain_band, request.fairness_threshold)
    board = request.board

    def asset_row(aid: str, side: str) -> dict:
        on_board = board is not None and aid in board.values
        return {"id": aid, "side": side, "market": round(snapshot.assets[aid].market, 1),
                "personal": round(board.values[aid], 1) if on_board else None,
                "n": board.comparisons.get(aid) if on_board else None}

    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "generator": ENGINE_ID,
        "generator_version": ENGINE_VERSION,
        "deck_position": entry.position,
        "weights": {"value": rank_cfg.w_value, "outlook": rank_cfg.w_outlook,
                    "rank": rank_cfg.w_rank, "repeat_penalty": rank_cfg.repeat_penalty,
                    "player_cap": rank_cfg.player_cap},
        "scores": {"value": round(s.value, 4), "outlook": round(s.outlook, 4),
                   "rank": round(s.rank, 4), "priority": round(s.priority, 4)},
        "effective": round(entry.effective, 4),
        "market": {"give": round(t.give_market, 1), "receive": round(t.receive_market, 1),
                   "adjusted_ratio": round(t.adjusted_ratio, 4),
                   "premium": round(t.premium, 4), "premium_side": t.premium_side},
        "core": {"band": round(band, 4), "gain_band": round(gain, 4),
                 "ratio_floor": round(1 / (1 + band), 4),
                 "ratio_ceiling": round(1 + gain, 4), "stud_premium": core_cfg.stud_premium,
                 "untouchable_min_ratio": core_cfg.untouchable_min_ratio,
                 "uses_untouchable": t.uses_untouchable, "drops_needed": list(t.drops_needed),
                 "budget_exhausted": budget_exhausted,
                 "throwin_min_ratio": core_cfg.throwin_min_ratio,
                 "throwin": _throwin_evidence(t, snapshot, request)},
        "windows": {"viewer": _window(snapshot.teams[request.viewer_team_id].window),
                    "partner": _window(snapshot.teams[t.partner_team_id].window)},
        "detail": dict(entry.scored.detail),
        "assets": ([asset_row(a, "give") for a in t.give]
                   + [asset_row(a, "receive") for a in t.receive]),
    }


def to_trade_cards(result: PipelineResult, snapshot: LeagueSnapshot, request: Request, *,
                   league_id: str, proposing_user_id: str, core_cfg: CoreConfig,
                   rank_cfg: RankConfig) -> tuple[list[TradeCard], dict[int, dict]]:
    """One TradeCard per entry, in entry order, plus {id(card): evidence}. lane, narrative,
    match_context, tier and rationale stay None so the payload omits them."""
    cards: list[TradeCard] = []
    ev: dict[int, dict] = {}
    for entry in result.entries:
        t = entry.scored.trade
        r = t.receive_market / t.give_market
        card = TradeCard(
            trade_id="vc_" + uuid.uuid4().hex, league_id=league_id,
            proposing_user_id=proposing_user_id,
            target_user_id=t.partner_team_id, target_username=snapshot.teams[t.partner_team_id].name,
            give_player_ids=list(t.give), receive_player_ids=list(t.receive),
            mismatch_score=round(entry.scored.scores.rank, 4),
            fairness_score=round(min(r, 1 / r), 4),
            composite_score=round(entry.scored.scores.priority, 6),
            basis="consensus", reasons=list(entry.reasons),
            give_value=round(t.give_market, 1), receive_value=round(t.receive_market, 1))
        card.preserve_server_order = True           # disables client re-rank (TradesScreen.tsx:2778, :4084)
        cards.append(card)
        ev[id(card)] = evidence(entry, snapshot, request, core_cfg, rank_cfg,
                                budget_exhausted=result.core.budget_exhausted)
    return cards, ev
