"""models-lead addendum D2: the quality filter's inputs, frozen per run.

The worker records what deck_quality.filter_deck read (the same `market`,
`position`, rosters and lineup it was given) as `job["filter_inputs"]`; job
done carries it into the pack's run header (`run["filter_inputs"]`), where
#453's audit re-runs B-DK-4/5/6. Audit provenance, never a scorer input.
"""
import types

import pytest

import backend.server as server
from backend import deck_quality
from backend.eval import contract


def _card(give, receive, target, **attrs):
    return types.SimpleNamespace(give_player_ids=give, receive_player_ids=receive,
                                 target_user_id=target, **attrs)


MARKET = {"g1": 100.0, "r1": 200.0, "wr1": 50.0}
POSITION = {"g1": "QB", "q2": "QB", "r1": "TE", "wr1": "WR"}
ROSTERS = {"me": ["g1", "q2", "wr1"], "opp": ["r1", "x"], "other": ["q9"]}


def _inputs(cards, lineup=("QB", "TE", "SUPER_FLEX")):
    return server._quality_filter_inputs(cards, viewer_team="me", market=MARKET.get,
                                         position=POSITION.get, rosters=ROSTERS,
                                         lineup_slots=lineup)


def test_the_record_holds_what_the_filter_read():
    """market / position for every asset on the returned cards and in the
    holdings (an unseeded asset and a None position are null); qb_te for the
    viewer and each counterparty only; the protected trade_hashes."""
    plain = _card(["g1", "x9"], ["r1"], "opp")
    kept_protected = _card(["wr1"], ["r1"], "opp", likes_you=True)
    got = _inputs([plain, kept_protected])
    assert got == {
        "v": 1, "filter_ran": True, "viewer_team": "me",
        "lineup_slots": ["QB", "TE", "SUPER_FLEX"],
        "market": {"g1": 100.0, "q2": None, "r1": 200.0, "wr1": 50.0, "x9": None},
        "position": {"g1": "QB", "q2": "QB", "r1": "TE", "wr1": "WR", "x9": None},
        "qb_te": {"me": ["g1", "q2"], "opp": ["r1"]},
        "protected": [server._deck_trade_hash(["wr1"], ["r1"], "opp")],
        # two cards, none deferred: the cap kept fewer than REPEAT_WINDOW (#503)
        "repeat_head": [server._deck_trade_hash(["g1", "x9"], ["r1"], "opp"),
                        server._deck_trade_hash(["wr1"], ["r1"], "opp")],
    }


@pytest.mark.parametrize("lineup, recorded", [(None, None), ([], []), (("TE",), ["TE"])])
def test_the_lineup_is_recorded_as_read(lineup, recorded):
    assert _inputs([_card(["g1"], ["r1"], "opp")], lineup=lineup)["lineup_slots"] == recorded


def test_it_is_never_a_frozen_scorer_input():
    assert "filter_inputs" not in contract.FROZEN_INPUT_KEYS


def _many(n):
    return [_card([f"g{i}"], [f"r{i}"], "opp") for i in range(n)]


@pytest.mark.parametrize("n, deferred, head", [(31, 0, None), (30, 0, None), (29, 0, 29),
                                               (40, 13, 27), (40, 10, None)])
def test_repeat_head_is_the_kept_cards_only_when_the_cap_ran_short(n, deferred, head):
    """models-eng #503: the cards the cap kept ahead of the deferred ones,
    when fewer than REPEAT_WINDOW; null when the head is full."""
    cards = _many(n)
    got = server._quality_filter_inputs(cards, viewer_team="me", market=MARKET.get,
                                        position=POSITION.get, rosters=ROSTERS,
                                        lineup_slots=None, deferred=deferred)["repeat_head"]
    want = None if head is None else [
        server._deck_trade_hash(c.give_player_ids, c.receive_player_ids, c.target_user_id)
        for c in cards[:head]]
    assert got == want


def test_a_market_value_is_a_finite_float_or_null():
    """#492 QA P3-4: NaN, inf and a bool are null; a numpy float is a plain
    float, so the header stays strict JSON."""
    import json
    np = pytest.importorskip("numpy")
    values = {"nan": float("nan"), "inf": float("inf"), "ninf": float("-inf"), "bool": True,
              "np": np.float32(1.5), "int": 7, "none": None}
    cards = [_card(list(values), ["r1"], "opp")]
    got = server._quality_filter_inputs(cards, viewer_team="me", market=values.get,
                                        position=lambda a: None, rosters={},
                                        lineup_slots=None)["market"]
    assert got == {"nan": None, "inf": None, "ninf": None, "bool": None, "np": 1.5,
                   "int": 7.0, "none": None, "r1": None}
    assert type(got["np"]) is float
    json.dumps(got, allow_nan=False)
