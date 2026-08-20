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


def test_pick_assets_never_occupy_a_riser_or_faller_row():
    """#261 — both pick families are dropped from the ROWS, in every bucket,
    while the ranks reported for the surviving players stay whole-board."""
    current = {
        "a": 1700.0, "b": 1600.0, "c": 1500.0,
        "generic_pick_1_mid": 1650.0,     # pool rung: real position, team PICK
        "owned_pick": 1550.0,             # owned-pick pseudo-player
        "generic_pick_4_late": 1400.0,    # pool rung with NO enrichment row
    }
    history = [
        {"player_id": "a", "elo": 1500.0, "snapshot_at": "t0"},
        {"player_id": "generic_pick_1_mid", "elo": 1000.0, "snapshot_at": "t0"},
        {"player_id": "owned_pick", "elo": 1000.0, "snapshot_at": "t0"},
        {"player_id": "generic_pick_4_late", "elo": 1000.0, "snapshot_at": "t0"},
    ]
    players = {
        **_players(),
        "generic_pick_1_mid": {"name": "Mid 1st Round Pick",
                               "position": "RB", "team": "PICK"},
        "owned_pick": {"name": "2026 Round 1", "position": "PICK",
                       "team": "PICK"},
        # generic_pick_4_late deliberately absent → the id-prefix arm is the
        # only defence for it.
    }

    out = compute_risers_fallers(current, history, players_by_id=players)

    for bucket in ("ALL", "QB", "RB", "WR", "TE"):
        ids = {r["player_id"] for r in out["risers"][bucket]
               + out["fallers"][bucket]}
        assert not any(i in ("generic_pick_1_mid", "owned_pick", "generic_pick_4_late")
                       for i in ids), bucket
    assert {r["player_id"] for r in out["risers"]["ALL"]} == {"a"}
    assert out["sample_size"] == 1

    # Ranks stay whole-board: picks remain in the rank denominator, so `a`
    # (1700) is still #1 of six and its RB rank still counts the RB-tabbed rung.
    a = out["risers"]["ALL"][0]
    assert a["overall_rank"] == 1
    assert a["pos_rank"] == 1


# ── Consensus gap ───────────────────────────────────────────────────────────

def test_consensus_gap_sells_are_where_the_market_is_higher_than_you():
    """#367 — the sell edge is the MARKET above your board, not below it.

    This test asserted the inverse until 2026-08-20: it took player "a", whom
    the user rates 300 above the community, and called him an "easiest sell".
    That is the player the league will NOT pay up for — and it is how the Team
    Review card came to promise "someone pays you more than you think they're
    worth" over exactly the players nobody would overpay for.

    Both roster players are held here so the test proves a SELECTION, not just
    a sign: "c" (market 200 above you) is a sell, "a" (you 300 above market) is
    excluded from the same call.
    """
    user_elo = {"a": 1800.0, "b": 1600.0, "c": 1500.0}
    community = {
        "u1": {"username": "x", "elo_ratings": {"a": 1500, "b": 1600, "c": 1700}},
        "u2": {"username": "y", "elo_ratings": {"a": 1500, "b": 1600, "c": 1700}},
        "u3": {"username": "z", "elo_ratings": {"a": 1500, "b": 1600, "c": 1700}},
    }
    out = compute_consensus_gap(
        user_elo=user_elo,
        community_rankings=community,
        user_roster=["a", "c"],
        league_members=[],
        players_by_id=_players(),
    )
    assert out["has_baseline"] is True
    sells = {r["player_id"]: r for r in out["easiest_sells"]}
    assert "c" in sells, "the market rates c 200 above your board — that is the sell"
    assert "a" not in sells, (
        "you rate a 300 ABOVE the market; nobody overpays for him. Selecting "
        "him here is the #367 inversion."
    )
    c = sells["c"]
    # User overall: a#1, b#2, c#3. Community mean: c#1, b#2, a#3.
    assert c["user_rank"] == 3
    assert c["comparison_rank"] == 1
    assert c["rank_gap"] == 2          # 3 - 1, the market ranks him 2 spots higher
    assert c["user_pos_rank"] == 3     # RB3 for the user
    assert c["pos_rank_gap"] == 2
    # `gap` is a POSITIVE edge magnitude, same convention as easiest_buys.
    assert c["gap"] == 200.0
