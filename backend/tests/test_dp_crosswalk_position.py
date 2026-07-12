"""DP↔Sleeper crosswalk position-strict join (feedback #127).

The bug: two different NFL players can share a normalised name — Kenneth
Walker (veteran WR, Sleeper id 4634) and Kenneth Walker III (RB, Sleeper
id 8151; DP_TO_SLEEPER_NAME maps the DP suffixed name onto the same
"kenneth walker" key). The universal-pool join was name-only, so BOTH
Sleeper players matched the one DP row and entered the pool with the RB's
value — the QuickSet/Tiers WR tab then showed a phantom "Kenneth Walker"
WR worth RB1 money.

The fix: _fetch_dynasty_process now also returns a {name: DP position}
map (load_consensus_maps), and every DP↔Sleeper name join is
position-strict — a name hit whose positions disagree is NO match. These
tests pin the Walker case and the general rule.
"""
import io

import backend.data_loader as data_loader
from backend.data_loader import _fetch_dynasty_process, seed_elo_for_players
from backend.ranking_service import Player
from backend.server import build_universal_pool

# Real-world shape: DP carries only Kenneth Walker III (RB). Values are
# arbitrary but positive so both rows clear the value>0 pool rule.
_SYNTHETIC_CSV = (
    "player,pos,team,age,value_1qb,value_2qb\n"
    "Kenneth Walker III,RB,KC,25.4,5116,4488\n"
    "Josh Johnson,QB,CIN,39.0,2,2\n"
)


class _FakeResponse(io.BytesIO):
    """Minimal stand-in for urlopen's context-manager response."""


def _mock_fetch(monkeypatch):
    monkeypatch.setattr(
        data_loader.urllib.request, "urlopen",
        lambda req, timeout=10: _FakeResponse(_SYNTHETIC_CSV.encode("utf-8")),
    )


# Sleeper cache slice: the RB (8151) AND his WR namesake (4634), plus a
# QB Josh Johnson (260) with RB/WR namesakes — the real cache contains all
# of these (verified against data/.sleeper_players_cache.json, 2026-07-12).
_SLEEPER_CACHE = {
    "8151": {"full_name": "Kenneth Walker", "position": "RB", "team": "KC",
             "age": 25, "years_exp": 4},
    "4634": {"full_name": "Kenneth Walker", "position": "WR", "team": None,
             "age": 27, "years_exp": 5},
    "260":  {"full_name": "Josh Johnson", "position": "QB", "team": "CIN",
             "age": 39, "years_exp": 17},
    "8051": {"full_name": "Josh Johnson", "position": "RB", "team": None,
             "age": 26, "years_exp": 2},
}


def _dp_maps(monkeypatch):
    _mock_fetch(monkeypatch)
    return _fetch_dynasty_process(scoring="1qb_ppr")


def test_fetch_returns_dp_position_map(monkeypatch):
    _, _, pos_map = _dp_maps(monkeypatch)
    # DP_TO_SLEEPER_NAME translated the suffixed DP name; the position
    # rides along so joins can be position-strict.
    assert pos_map["kenneth walker"] == "RB"
    assert pos_map["josh johnson"] == "QB"


def test_universal_pool_has_exactly_one_kenneth_walker_at_rb(monkeypatch):
    """The #127 repro, pinned: with the position-strict join the pool holds
    ONE Kenneth Walker — the RB (8151) — and the WR namesake is out."""
    dp_elo, dp_vals, dp_pos = _dp_maps(monkeypatch)
    players, seeds = build_universal_pool(
        sleeper_cache=_SLEEPER_CACHE,
        dp_elo=dp_elo,
        dp_vals=dp_vals,
        all_db_players=[],
        dp_pos=dp_pos,
    )
    walkers = [p for p in players if p.name == "Kenneth Walker"]
    assert len(walkers) == 1, f"expected 1 Kenneth Walker, got {len(walkers)}"
    assert walkers[0].position == "RB"
    assert walkers[0].id == "8151"
    assert "4634" not in seeds
    assert seeds["8151"] == dp_elo["kenneth walker"]


def test_name_collision_never_maps_cross_position(monkeypatch):
    """General rule: a DP row only joins Sleeper players at ITS position.
    Josh Johnson QB joins; the RB namesake does not."""
    dp_elo, dp_vals, dp_pos = _dp_maps(monkeypatch)
    players, _ = build_universal_pool(
        sleeper_cache=_SLEEPER_CACHE,
        dp_elo=dp_elo,
        dp_vals=dp_vals,
        all_db_players=[],
        dp_pos=dp_pos,
    )
    real = {p.id for p in players if p.team != "PICK"}
    assert real == {"8151", "260"}


def test_seed_elo_for_players_is_position_strict_with_pos_map(monkeypatch):
    dp_elo, _, dp_pos = _dp_maps(monkeypatch)
    rb = Player(id="8151", name="Kenneth Walker", position="RB", team="KC", age=25)
    wr = Player(id="4634", name="Kenneth Walker", position="WR", team="FA", age=27)
    seeded = seed_elo_for_players([rb, wr], dp_elo, pos_map=dp_pos)
    assert seeded["8151"] == dp_elo["kenneth walker"]
    assert seeded["4634"] == 1500.0  # namesake falls back, never inherits
