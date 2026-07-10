"""Backlog #8 — seed unset-league outlook from the user's own roster.

The classifier itself (infer_team_outlook) is covered by
test_opponent_outlook_infer; this pins the #8-specific server seam:
_infer_user_outlook flag-gating + roster→outlook resolution + the
user's pick-share helper. Flags snapshot-restored per test.
"""

from dataclasses import dataclass

import pytest

import backend.feature_flags as ff
import backend.server as srv


@pytest.fixture(autouse=True)
def _isolate():
    old = ff._flags_cache
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)
    try:
        yield
    finally:
        ff._flags_cache = old


@dataclass
class _P:
    id: str
    position: str
    age: int
    search_rank: int
    pick_value: float | None = None


class _League:
    def __init__(self, n=12):
        self.members = list(range(n))


def _sess(roster_players):
    return {"user_roster": [p.id for p in roster_players],
            "players": roster_players}


def _set(**kw):
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update(kw)
    ff._flags_cache = cache


def test_seed_off_returns_none():
    young = [_P("a", "WR", 21, 6), _P("b", "RB", 22, 15)]
    assert srv._infer_user_outlook("u", "L1", _sess(young), _League()) == (None, None)


def test_seed_on_young_roster_rebuilder():
    _set(**{"trade.outlook_seed": True})
    young = [_P("a", "WR", 21, 6), _P("b", "RB", 22, 15),
             _P("c", "WR", 23, 25), _P("d", "QB", 22, 30)]
    outlook, signals = srv._infer_user_outlook("u", "L1", _sess(young), _League())
    assert outlook == "rebuilder"
    assert signals and signals["youth_share"] > 0.5


def test_seed_on_old_roster_contender():
    _set(**{"trade.outlook_seed": True})
    old = [_P("a", "RB", 29, 3), _P("b", "WR", 30, 8),
           _P("c", "QB", 28, 15), _P("d", "WR", 24, 40)]
    outlook, _ = srv._infer_user_outlook("u", "L1", _sess(old), _League())
    assert outlook == "contender"


def test_seed_on_missing_roster_returns_none():
    _set(**{"trade.outlook_seed": True})
    assert srv._infer_user_outlook("u", "L1", {"user_roster": [], "players": []},
                                   _League()) == (None, None)


def test_user_pick_share_no_picks_is_zero():
    # No synced picks for this league ⇒ 0.0, no crash.
    assert srv._user_pick_share("nobody", "league_with_no_picks_xyz") == 0.0
