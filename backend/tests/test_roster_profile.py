"""Unit tests for analyze_roster_strengths() and build_match_context()."""
from dataclasses import dataclass

from backend.trade_service import (
    analyze_roster_strengths,
    build_match_context,
)


@dataclass
class _P:
    id: str
    position: str
    search_rank: int = 100
    name: str = "X"
    pick_value: float | None = None


def _build(player_specs):
    return {p.id: p for p in player_specs}


def test_thin_rb_flagged_as_need():
    # 1 elite QB, 1 RB starter, 0 WR starters, 0 TE starters
    players = _build([
        _P("q1", "QB", 5),
        _P("r1", "RB", 30),
        _P("w1", "WR", 200),  # bench tier
        _P("t1", "TE", 200),
    ])
    profile = analyze_roster_strengths(["q1", "r1", "w1", "t1"], players)
    assert "RB" in profile["position_needs"]  # only 1 starter, need 2
    assert "WR" in profile["position_needs"]
    assert "QB" not in profile["position_needs"]


def test_rb_surplus_detected():
    players = _build([
        _P(f"r{i}", "RB", 20 + i * 5) for i in range(5)  # 5 starter+ RBs
    ])
    profile = analyze_roster_strengths([f"r{i}" for i in range(5)], players)
    assert "RB" in profile["position_surplus"]


def test_superflex_demands_two_qbs():
    players = _build([_P("q1", "QB", 5)])
    sf = analyze_roster_strengths(["q1"], players, scoring_format="sf_tep")
    one_qb = analyze_roster_strengths(["q1"], players, scoring_format="1qb_ppr")
    assert "QB" in sf["position_needs"]
    assert "QB" not in one_qb["position_needs"]


def test_match_context_overlap_message():
    user_profile = {"position_needs": ["RB", "TE"], "position_surplus": []}
    opp_profile  = {"position_needs": [], "position_surplus": ["RB"]}
    ctx = build_match_context(user_profile, opp_profile, "1qb_ppr", is_dynasty=True)
    assert ctx["positional_rationale"].startswith("You're thin at RB")
    assert ctx["league_settings"]["dynasty"] is True
    assert ctx["league_settings"]["scoring"] == "ppr"


def test_match_context_sf_tep_is_ppr():
    # sf_tep is a PPR format — must not be reported as "standard"
    ctx = build_match_context({}, {}, "sf_tep")
    assert ctx["league_settings"]["scoring"] == "ppr"
    assert ctx["league_settings"]["superflex"] is True
    assert ctx["league_settings"]["te_premium"] is True


def test_match_context_explicit_standard_format():
    ctx = build_match_context({}, {}, "1qb_standard")
    assert ctx["league_settings"]["scoring"] == "standard"


def test_match_context_no_overlap_falls_back():
    user_profile = {"position_needs": [], "position_surplus": []}
    opp_profile  = {"position_needs": [], "position_surplus": []}
    ctx = build_match_context(user_profile, opp_profile, "sf_tep")
    assert "align" in ctx["positional_rationale"]
    assert ctx["league_settings"]["superflex"] is True
    assert ctx["league_settings"]["te_premium"] is True
