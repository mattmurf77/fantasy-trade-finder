"""Snapshot-style tests for the templated trade narrative."""
from dataclasses import dataclass, field

from backend.trade_narrative import build_narrative


@dataclass
class _P:
    id: str
    name: str
    position: str
    pick_value: float | None = None
    search_rank: int = 100


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


def test_picks_highest_value_received_player_not_first():
    # depth piece listed first, headliner second — narrative must name headliner
    players = {
        "depth":     _P("depth",     "Bench Guy",     "WR", search_rank=400),
        "headliner": _P("headliner", "CeeDee Lamb",   "WR", search_rank=3),
    }
    card = _Card(give_player_ids=["g"], receive_player_ids=["depth", "headliner"])
    ctx = {"user_needs": ["WR"], "opponent_surplus": ["WR"], "league_settings": {}}
    out = build_narrative(card, ctx, players)
    assert "CeeDee Lamb" in out
    assert "Bench Guy" not in out


# ───────────── positional honesty (2026-08-15 correctness fix) ─────────────
# `user_needs` comes from the roster analysis and the received players come
# from the card. A sentence may only pair a position with a player who
# actually plays it.

def test_te_only_return_never_claims_the_qb_need():
    players = {"r1": _P("r1", "Brock Bowers", "TE", search_rank=8)}
    card = _Card(give_player_ids=["g"], receive_player_ids=["r1"])
    ctx = {
        "user_needs":       ["QB", "RB"],
        "opponent_surplus": ["TE"],
        "league_settings":  {},
    }
    out = build_narrative(card, ctx, players)
    assert "QB" not in out
    assert "Brock Bowers" in out
    assert "thin" not in out and "shore up" not in out   # neutral fallback


def test_names_the_position_the_received_player_actually_plays():
    # top need is QB; the only need-filling player received is the RB
    players = {
        "rb": _P("rb", "Bijan Robinson", "RB", search_rank=2),
        "te": _P("te", "Bench TE",       "TE", search_rank=300),
    }
    card = _Card(give_player_ids=["g"], receive_player_ids=["rb", "te"])
    ctx = {
        "user_needs":       ["QB", "RB"],
        "opponent_surplus": ["RB"],
        "league_settings":  {},
    }
    out = build_narrative(card, ctx, players)
    assert "shore up RB by acquiring Bijan Robinson" in out
    assert "QB" not in out


def test_overlap_position_matches_the_named_player():
    # overlap[0] is QB but only the WR comes back
    players = {"wr": _P("wr", "Puka Nacua", "WR", search_rank=5)}
    card = _Card(give_player_ids=["g"], receive_player_ids=["wr"])
    ctx = {
        "user_needs":       ["QB", "WR"],
        "opponent_surplus": ["QB", "WR"],
        "league_settings":  {},
    }
    out = build_narrative(card, ctx, players)
    assert "shore up WR by acquiring Puka Nacua" in out
    assert "QB" not in out


def test_picks_alone_do_not_fill_a_positional_need():
    players = {"p1": _P("p1", "2026 1st", "PICK", pick_value=67.5)}
    card = _Card(give_player_ids=["g"], receive_player_ids=["p1"])
    ctx = {"user_needs": ["QB"], "opponent_surplus": ["QB"],
           "league_settings": {"dynasty": True}}
    out = build_narrative(card, ctx, players)
    assert "QB" not in out
    assert "2026 1st" in out


def test_fit_premium_uses_the_premium_position():
    players = {"r1": _P("r1", "Trey McBride", "TE", search_rank=15)}
    card = _Card(give_player_ids=["g"], receive_player_ids=["r1"])
    card.fit_premium = {"value_paid": 120.0, "position": "TE"}
    ctx = {"user_needs": ["QB", "TE"], "opponent_surplus": ["TE"],
           "league_settings": {}}
    out = build_narrative(card, ctx, players)
    assert "Fills your TE hole with Trey McBride" in out
    assert "QB" not in out


def test_fit_premium_without_a_position_does_not_borrow_the_top_need():
    players = {"r1": _P("r1", "Trey McBride", "TE", search_rank=15)}
    card = _Card(give_player_ids=["g"], receive_player_ids=["r1"])
    card.fit_premium = {"value_paid": 120.0, "position": None}
    ctx = {"user_needs": ["QB"], "opponent_surplus": ["QB"],
           "league_settings": {}}
    out = build_narrative(card, ctx, players)
    assert "QB" not in out
    assert "Trey McBride" in out


def test_no_position_is_claimed_that_is_not_actually_received():
    """Invariant over every needs × received-positions combination: a
    position token in the narrative must belong to a received player."""
    import itertools

    POSITIONS = ["QB", "RB", "WR", "TE"]
    for recv in itertools.chain(
        itertools.combinations(POSITIONS, 1),
        itertools.combinations(POSITIONS, 2),
    ):
        players = {p: _P(p, f"{p} Guy", p, search_rank=10) for p in recv}
        card = _Card(give_player_ids=["g"], receive_player_ids=list(recv))
        for r in range(1, len(POSITIONS) + 1):
            for needs in itertools.permutations(POSITIONS, r):
                for surplus in ([], list(needs), POSITIONS):
                    ctx = {"user_needs": list(needs),
                           "opponent_surplus": surplus,
                           "league_settings": {}}
                    out = build_narrative(card, ctx, players)
                    claimed = [p for p in POSITIONS
                               if f" {p} " in f" {out} "
                               or f"{p} hole" in out
                               or f"{p} group" in out]
                    assert all(p in recv for p in claimed), (
                        f"recv={recv} needs={needs} surplus={surplus} → {out}")


def test_two_sentence_cap():
    players = {
        "r1": _P("r1", "RB1", "RB"),
        "p1": _P("p1", "Pick", "PICK", pick_value=50),
    }
    card = _Card(give_player_ids=["g"], receive_player_ids=["r1", "p1"])
    ctx = {"user_needs": ["RB"], "opponent_surplus": ["RB"], "league_settings": {"dynasty": True}}
    out = build_narrative(card, ctx, players)
    assert out.count(".") == 2
