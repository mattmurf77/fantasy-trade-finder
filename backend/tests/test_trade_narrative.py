"""Snapshot-style tests for the templated trade narrative."""
from dataclasses import dataclass, field

from backend.trade_narrative import build_narrative


@dataclass
class _P:
    id: str
    name: str
    position: str
    pick_value: float | None = None


@dataclass
class _Card:
    give_player_ids: list[str]
    receive_player_ids: list[str]
    fairness_score: float = 0.9
    mismatch_score: float = 50.0
    composite_score: float = 100.0


def test_overlap_mentions_position_and_player():
    players = {"r1": _P("r1", "Bijan Robinson", "RB")}
    card = _Card(give_player_ids=["w1"], receive_player_ids=["r1"])
    ctx = {
        "user_needs":       ["RB"],
        "opponent_surplus": ["RB"],
        "league_settings":  {"dynasty": False},
    }
    out = build_narrative(card, ctx, players)
    assert "RB" in out
    assert "Bijan Robinson" in out
    assert out.count(".") <= 2  # ≤ 2 sentences


def test_picks_get_dynasty_callout_when_dynasty():
    players = {
        "r1": _P("r1", "Saquon", "RB"),
        "p1": _P("p1", "2026 1st", "PICK", pick_value=67.5),
    }
    card = _Card(give_player_ids=["w1"], receive_player_ids=["r1", "p1"])
    ctx = {"user_needs": [], "opponent_surplus": [], "league_settings": {"dynasty": True}}
    out = build_narrative(card, ctx, players)
    assert "dynasty pick" in out.lower()


def test_no_context_falls_back_to_fairness():
    players = {"r1": _P("r1", "Player A", "RB")}
    card = _Card(give_player_ids=["w1"], receive_player_ids=["r1"], fairness_score=0.6)
    out = build_narrative(card, None, players)
    assert "uneven" in out.lower() or "tilt" in out.lower() or "Player A" in out


def test_two_sentence_cap():
    players = {
        "r1": _P("r1", "RB1", "RB"),
        "p1": _P("p1", "Pick", "PICK", pick_value=50),
    }
    card = _Card(give_player_ids=["g"], receive_player_ids=["r1", "p1"])
    ctx = {"user_needs": ["RB"], "opponent_surplus": ["RB"], "league_settings": {"dynasty": True}}
    out = build_narrative(card, ctx, players)
    assert out.count(".") == 2
