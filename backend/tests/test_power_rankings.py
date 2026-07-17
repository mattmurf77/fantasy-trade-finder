"""Unit tests for backend/power_rankings.compute_power_rankings (#142/#144).

Covers both value bases (consensus / personal-with-consensus-fallback),
out-of-pool zero-value handling, deterministic ordering, and the #144
roster grouping contract (position groups, value-desc within group).
"""
from dataclasses import dataclass

from backend.power_rankings import compute_power_rankings
from backend.trade_service import elo_to_value


@dataclass
class _P:
    id: str
    name: str
    position: str
    team: str = "FA"
    age: int = 25


PLAYERS = {p.id: p for p in [
    _P("qb1", "Alpha QB",  "QB"),
    _P("qb2", "Beta QB",   "QB"),
    _P("rb1", "Alpha RB",  "RB"),
    _P("rb2", "Beta RB",   "RB"),
    _P("wr1", "Alpha WR",  "WR"),
    _P("te1", "Alpha TE",  "TE"),
    _P("k1",  "Some K",    "K"),   # out of the value pool
]}

SEED = {
    "qb1": 1800.0,
    "qb2": 1500.0,
    "rb1": 1700.0,
    "rb2": 1400.0,
    "wr1": 1600.0,
    "te1": 1450.0,
    # k1 deliberately absent — no consensus value
}

MEMBERS = [
    {"user_id": "u_a", "username": "alice", "display_name": "Alice",
     "player_ids": ["qb1", "rb1", "k1"]},
    {"user_id": "u_b", "username": "bob", "display_name": "Bob",
     "player_ids": ["qb2", "rb2", "wr1", "te1"]},
]


def _team(teams, user_id):
    return next(t for t in teams if t["user_id"] == user_id)


def test_consensus_totals_and_rank_order():
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS)
    a = _team(teams, "u_a")
    b = _team(teams, "u_b")

    exp_a = round(elo_to_value(1800) + elo_to_value(1700) + 0.0, 1)
    exp_b = round(sum(elo_to_value(SEED[p]) for p in ("qb2", "rb2", "wr1", "te1")), 1)
    assert abs(a["total_value"] - exp_a) < 0.2
    assert abs(b["total_value"] - exp_b) < 0.2

    # Alice's two studs outweigh Bob's four mid assets on this seed.
    assert exp_a > exp_b
    assert [t["user_id"] for t in teams] == ["u_a", "u_b"]
    assert [t["rank"] for t in teams] == [1, 2]


def test_out_of_pool_player_contributes_zero():
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS)
    a = _team(teams, "u_a")
    k_row = next(r for r in a["roster"] if r["player_id"] == "k1")
    assert k_row["value"] == 0.0
    # ...but the player still appears in the roster listing with metadata.
    assert k_row["name"] == "Some K"
    assert k_row["position"] == "K"


def test_personal_basis_overrides_with_consensus_fallback():
    # The caller tanks qb1 and pumps qb2; everyone else unranked → seed.
    board = {"qb1": 1400.0, "qb2": 1900.0}
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS, board_elo=board)
    a = _team(teams, "u_a")
    b = _team(teams, "u_b")

    exp_a = round(elo_to_value(1400) + elo_to_value(1700), 1)   # qb1 by board, rb1 by seed
    exp_b = round(elo_to_value(1900)                            # qb2 by board
                  + sum(elo_to_value(SEED[p]) for p in ("rb2", "wr1", "te1")), 1)
    assert abs(a["total_value"] - exp_a) < 0.2
    assert abs(b["total_value"] - exp_b) < 0.2

    # The board flip inverts the league order vs the consensus basis.
    assert [t["user_id"] for t in teams] == ["u_b", "u_a"]
    assert _team(teams, "u_b")["rank"] == 1


def test_tie_breaks_deterministically_by_user_id():
    members = [
        {"user_id": "u_z", "username": "zed", "player_ids": ["qb1"]},
        {"user_id": "u_a", "username": "ann", "player_ids": ["qb1"]},
    ]
    teams = compute_power_rankings(members, SEED, PLAYERS)
    assert [t["user_id"] for t in teams] == ["u_a", "u_z"]
    assert [t["rank"] for t in teams] == [1, 2]


def test_roster_grouped_by_position_value_desc_within_group():
    members = [{
        "user_id": "u_b", "username": "bob",
        # Deliberately shuffled input order, two QBs to test in-group sort.
        "player_ids": ["te1", "qb2", "wr1", "qb1", "k1", "rb2", "rb1"],
    }]
    teams = compute_power_rankings(members, SEED, PLAYERS)
    roster = teams[0]["roster"]
    assert [r["player_id"] for r in roster] == [
        "qb1", "qb2",        # QB group, value desc
        "rb1", "rb2",        # RB group, value desc
        "wr1",               # WR
        "te1",               # TE
        "k1",                # non-core positions trail
    ]


def test_position_summary_counts_and_values():
    teams = compute_power_rankings(MEMBERS, SEED, PLAYERS)
    a = _team(teams, "u_a")
    assert a["positions"]["QB"]["count"] == 1
    assert a["positions"]["RB"]["count"] == 1
    assert a["positions"]["WR"] == {"count": 0, "value": 0.0}
    assert abs(a["positions"]["QB"]["value"] - round(elo_to_value(1800), 1)) < 0.2
    # K is not a core position — excluded from the summary, counted in total.
    assert "K" not in a["positions"]


def test_member_without_valid_user_id_skipped():
    members = MEMBERS + [{"user_id": "", "username": "ghost", "player_ids": ["qb1"]}]
    teams = compute_power_rankings(members, SEED, PLAYERS)
    assert {t["user_id"] for t in teams} == {"u_a", "u_b"}
