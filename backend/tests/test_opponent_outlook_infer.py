"""Backlog #1 — opponent outlook auto-classification.

Pins three behaviors (docs/plans/competitor-top20/01-opponent-outlook-classifier.md):

  1. infer_team_outlook buckets roster archetypes correctly
     (old+concentrated → contender, young+pick-rich → rebuilder, mixed → not_sure)
     and reserves the extreme labels (championship/jets) for self-declaration.
  2. Flag OFF (trade.outlook_infer) ⇒ output byte-identical to today: no
     opponent_outlook stamped, same cards as a baseline run.
  3. Flag ON ⇒ each opponent's side is priced through THEIR α: an aging vet is
     valued lower for an inferred rebuilder, and declared outlook overrides
     inference.

Flags/_cfg snapshot-restored per test (mirrors test_fairness_gate_golden).
"""

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import (
    League,
    LeagueMember,
    TradeService,
    infer_team_outlook,
    outlook_alpha,
    outlook_blend_mult,
)


@pytest.fixture(autouse=True)
def _isolate():
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


class _Player:
    def __init__(self, pid, position="RB", age=24, search_rank=50):
        self.id = pid
        self.name = f"Player {pid}"
        self.position = position
        self.team = "TST"
        self.age = age
        self.search_rank = search_rank
        self.pick_value = None


def _set_flags(**kw):
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update(kw)
    ff._flags_cache = cache


# ───────────────────────── classifier ─────────────────────────

def test_infer_buckets_archetypes():
    # Old, concentrated in veterans, light on picks → contender.
    old = {
        "a": _Player("a", "RB", age=29, search_rank=3),
        "b": _Player("b", "WR", age=30, search_rank=8),
        "c": _Player("c", "QB", age=28, search_rank=15),
        "d": _Player("d", "WR", age=24, search_rank=40),
    }
    out, score, _ = infer_team_outlook(list(old), old, pick_share=0.03, num_teams=12)
    assert out == "contender" and score > 0

    # Young roster with hoarded pick capital → rebuilder.
    young = {
        "a": _Player("a", "RB", age=22, search_rank=5),
        "b": _Player("b", "WR", age=21, search_rank=9),
        "c": _Player("c", "WR", age=23, search_rank=20),
        "d": _Player("d", "RB", age=29, search_rank=60),
    }
    out2, score2, _ = infer_team_outlook(list(young), young, pick_share=0.18, num_teams=12)
    assert out2 == "rebuilder" and score2 < 0

    # Mixed/average → not_sure, and the extreme labels are never inferred.
    mixed = {
        "a": _Player("a", "RB", age=26, search_rank=5),
        "b": _Player("b", "WR", age=27, search_rank=9),
        "c": _Player("c", "WR", age=25, search_rank=20),
        "d": _Player("d", "QB", age=28, search_rank=30),
    }
    out3, _, _ = infer_team_outlook(list(mixed), mixed, pick_share=1 / 12, num_teams=12)
    assert out3 == "not_sure"
    assert out3 not in ("championship", "jets")


def test_infer_empty_roster_is_not_sure():
    out, score, sig = infer_team_outlook([], {}, pick_share=0.0, num_teams=12)
    # No value, equal-share pick centring ⇒ score ≈ 0 ⇒ not_sure (no crash).
    assert out == "not_sure"
    assert sig["vet_share"] == 0.0 and sig["youth_share"] == 0.0


def test_blend_direction_matches_window():
    # An aging RB is worth progressively less as α falls (rebuilder < not_sure
    # < contender) — the property the opponent-side blend relies on.
    old_rb = outlook_blend_mult("RB", 30, outlook_alpha("rebuilder"))
    mid_rb = outlook_blend_mult("RB", 30, outlook_alpha("not_sure"))
    win_rb = outlook_blend_mult("RB", 30, outlook_alpha("contender"))
    assert old_rb < mid_rb < win_rb


# ───────────────────────── engine integration ─────────────────────────

def _svc():
    # Clean 1-for-1 divergence (mirrors the golden-test knife fixture): the
    # user undervalues G and covets R; the opponent mirrors. The opponent's
    # roster is uniformly young ⇒ inference classifies them a rebuilder. Ten
    # empty-roster filler members give a realistic league size (num_teams=11)
    # so the pick-share centring term is sane; they never enter `eligible`
    # (no roster), so only `opp` generates cards. G is age-neutral (24) so the
    # outlook blend doesn't move it enough to disturb the card's existence.
    players = {
        "G":  _Player("G", "RB", age=24, search_rank=40),
        "R":  _Player("R", "WR", age=22, search_rank=18),
        "y1": _Player("y1", "WR", age=21, search_rank=22),
        "y2": _Player("y2", "RB", age=23, search_rank=28),
        "y3": _Player("y3", "QB", age=22, search_rank=30),
    }
    # Opponent covets G (1700) and holds R cheaply (1500) — the mirror that
    # makes user-gives-G / user-receives-R a mutual-divergence-gain card.
    # elo_ratings drive the trade; classification uses consensus search_rank,
    # so the young roster still reads as a rebuilder regardless of these.
    opp = LeagueMember(
        user_id="opp", username="opp",
        roster=["R", "y1", "y2", "y3"],
        elo_ratings={"G": 1700, "R": 1500, "y1": 1480, "y2": 1450, "y3": 1400},
        has_rankings=True,
    )
    fillers = [LeagueMember(user_id=f"f{i}", username=f"f{i}", roster=[],
                            elo_ratings={}, has_rankings=False)
               for i in range(10)]
    s = TradeService(players=players)
    s.add_league(League(league_id="L1", name="T", platform="demo",
                        members=[opp] + fillers))
    return s


def _gen(svc, **kw):
    kw.setdefault("fairness_threshold", 0.05)
    return svc.generate_trades(
        user_id="user",
        user_elo={"G": 1500, "R": 1700},
        user_roster=["G"],
        league_id="L1",
        seed_elo={"G": 1540, "R": 1500},
        **kw,
    )


def test_flag_off_no_outlook_stamp_and_baseline_identical():
    _set_flags(**{"trade_engine.v2": True, "trade.outlook_blend": True,
                  "trade.outlook_infer": False})
    base = _gen(_svc())
    # Re-running with infer inputs present but flag OFF must not change anything.
    again = _gen(_svc(),
                 opponent_outlooks={"opp": "rebuilder"},
                 opponent_pick_shares={"opp": 0.2})
    assert [(c.give_player_ids, c.receive_player_ids) for c in base] == \
           [(c.give_player_ids, c.receive_player_ids) for c in again]
    for c in base:
        assert "opponent_outlook" not in (c.match_context or {})


def test_flag_on_stamps_inferred_outlook():
    _set_flags(**{"trade_engine.v2": True, "trade.outlook_blend": True,
                  "trade.outlook_infer": True})
    cards = _gen(_svc(), opponent_pick_shares={"opp": 0.2})
    assert cards, "expected at least one card against the rebuilder opponent"
    oc = cards[0].match_context.get("opponent_outlook")
    assert oc and oc["source"] == "inferred"
    assert oc["value"] == "rebuilder"


def test_declared_overrides_inference():
    _set_flags(**{"trade_engine.v2": True, "trade.outlook_blend": True,
                  "trade.outlook_infer": True})
    cards = _gen(_svc(),
                 opponent_outlooks={"opp": "contender"},
                 opponent_pick_shares={"opp": 0.2})
    assert cards
    oc = cards[0].match_context.get("opponent_outlook")
    assert oc["source"] == "declared" and oc["value"] == "contender"
