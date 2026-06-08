"""Unit tests for the FB-04 rank-delta derivation in trends_service.

Rank is a pure view of the existing ELOs: sort by ELO desc, highest = rank 1.
A rank delta is previous_rank - current_rank, so positive = moved UP toward #1.
These tests pin the derivation and its graceful degradation, and confirm the
existing ELO fields are untouched (backward-compatible).
"""
from backend.trends_service import (
    _rank_map,
    _pos_rank_map,
    _rank_delta,
    compute_risers_fallers,
    compute_consensus_gap,
)


# ── Low-level rank helpers ──────────────────────────────────────────────────

def test_rank_map_orders_by_elo_desc():
    ranks = _rank_map({"a": 1500, "b": 1700, "c": 1600})
    assert ranks == {"b": 1, "c": 2, "a": 3}


def test_rank_map_ties_break_on_player_id():
    # Equal ELO → deterministic order by player_id.
    ranks = _rank_map({"z": 1500, "a": 1500})
    assert ranks == {"a": 1, "z": 2}


def test_pos_rank_map_groups_by_position():
    elos = {"r1": 1700, "r2": 1500, "w1": 1600}
    players = {
        "r1": {"position": "RB"},
        "r2": {"position": "RB"},
        "w1": {"position": "WR"},
    }
    pos = _pos_rank_map(elos, players)
    assert pos == {"r1": 1, "r2": 2, "w1": 1}


def test_pos_rank_map_skips_unknown_position():
    pos = _pos_rank_map({"x": 1500}, {"x": {}})
    assert pos == {}


def test_rank_delta_sign_and_none():
    assert _rank_delta(10, 7) == 3      # climbed 3 spots → positive
    assert _rank_delta(7, 10) == -3     # dropped 3 spots → negative
    assert _rank_delta(None, 5) is None
    assert _rank_delta(5, None) is None


# ── Risers / fallers ────────────────────────────────────────────────────────

def _players():
    return {
        "a": {"name": "A", "position": "RB"},
        "b": {"name": "B", "position": "RB"},
        "c": {"name": "C", "position": "RB"},
    }


def test_risers_attach_overall_and_pos_rank_deltas():
    # Current: a=1700, b=1600, c=1500 → overall a#1 b#2 c#3 (all RB).
    # History earliest: a=1500, b=1700 → previously b#1 a#2 (c had no history).
    current = {"a": 1700.0, "b": 1600.0, "c": 1500.0}
    history = [
        {"player_id": "a", "elo": 1500.0, "snapshot_at": "t0"},
        {"player_id": "b", "elo": 1700.0, "snapshot_at": "t0"},
    ]
    out = compute_risers_fallers(current, history, players_by_id=_players(), top_n=5)

    rows = {r["player_id"]: r for r in out["risers"]["ALL"] + out["fallers"]["ALL"]}
    a = rows["a"]
    # Prev snapshot reconstructed: a=1500,b=1700,c(fallback)=1500.
    # Prev overall: b#1, then a & c tie at 1500 → a#2, c#3 (id tiebreak).
    # Curr overall: a#1, b#2, c#3.
    assert a["overall_rank"] == 1
    assert a["overall_rank_delta"] == 1   # 2 -> 1, moved up 1
    assert a["pos_rank"] == 1
    assert a["pos_rank_delta"] == 1
    # Existing ELO fields preserved (backward compatible).
    assert a["current_elo"] == 1700.0
    assert a["previous_elo"] == 1500.0
    assert a["delta"] == 200.0

    b = rows["b"]
    assert b["overall_rank"] == 2
    assert b["overall_rank_delta"] == -1  # 1 -> 2, dropped 1
    assert b["delta"] == -100.0


def test_risers_no_history_for_player_excluded_gracefully():
    # c never appears in history → not a mover, no crash.
    current = {"a": 1700.0, "b": 1600.0, "c": 1500.0}
    history = [{"player_id": "a", "elo": 1500.0, "snapshot_at": "t0"}]
    out = compute_risers_fallers(current, history, players_by_id=_players())
    ids = {r["player_id"] for r in out["risers"]["ALL"] + out["fallers"]["ALL"]}
    assert "c" not in ids


# ── Consensus gap ───────────────────────────────────────────────────────────

def test_consensus_gap_sells_expose_rank_gap():
    # User values a RB far above the community → easiest sell, with a rank gap.
    user_elo = {"a": 1800.0, "b": 1600.0, "c": 1500.0}
    community = {
        "u1": {"username": "x", "elo_ratings": {"a": 1500, "b": 1600, "c": 1700}},
        "u2": {"username": "y", "elo_ratings": {"a": 1500, "b": 1600, "c": 1700}},
        "u3": {"username": "z", "elo_ratings": {"a": 1500, "b": 1600, "c": 1700}},
    }
    out = compute_consensus_gap(
        user_elo=user_elo,
        community_rankings=community,
        user_roster=["a"],
        league_members=[],
        players_by_id=_players(),
    )
    assert out["has_baseline"] is True
    sells = {r["player_id"]: r for r in out["easiest_sells"]}
    assert "a" in sells
    a = sells["a"]
    # User overall: a#1, b#2, c#3. Community mean: c#1, b#2, a#3.
    assert a["user_rank"] == 1
    assert a["comparison_rank"] == 3
    assert a["rank_gap"] == 2          # 3 - 1, you rank them 2 spots higher
    assert a["user_pos_rank"] == 1     # RB1 for the user
    assert a["pos_rank_gap"] == 2
    # ELO gap still present.
    assert a["gap"] == 300.0
