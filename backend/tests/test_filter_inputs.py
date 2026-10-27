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
from backend.tests.test_trade_freshness_roster import _complete_job, live  # noqa: F401  (fixture)


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
    }


@pytest.mark.parametrize("lineup, recorded", [(None, None), ([], []), (("TE",), ["TE"])])
def test_the_lineup_is_recorded_as_read(lineup, recorded):
    assert _inputs([_card(["g1"], ["r1"], "opp")], lineup=lineup)["lineup_slots"] == recorded


def test_it_is_never_a_frozen_scorer_input():
    assert "filter_inputs" not in contract.FROZEN_INPUT_KEYS


def _filters_on(monkeypatch):
    monkeypatch.setattr(server, "_deck_quality_filters_enabled", lambda: True)


def test_the_worker_records_the_inputs_its_filter_used(live, monkeypatch):
    """The real worker: the recorded values reproduce the filter's decisions,
    so every kept, unprotected card passes the breakup and filler rules on
    them."""
    _filters_on(monkeypatch)
    job = _complete_job()
    inputs = job["filter_inputs"]
    assert inputs["filter_ran"] is True and inputs["v"] == 1
    market = inputs["market"]
    for card in job["cards"]:
        give = [p["id"] for p in card["give"]]
        receive = [p["id"] for p in card["receive"]]
        assert set(give + receive) <= set(market)
        assert not deck_quality._breakup(give, receive, market.get)
        assert not deck_quality._filler(give, receive, market.get)


def test_flag_off_records_that_the_filter_never_ran(live, monkeypatch):
    monkeypatch.setattr(server, "_deck_quality_filters_enabled", lambda: False)
    assert _complete_job()["filter_inputs"] == {"v": 1, "filter_ran": False}


def test_a_failed_filter_records_that_it_never_ran(live, monkeypatch):
    _filters_on(monkeypatch)
    monkeypatch.setattr(deck_quality, "filter_deck",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("filter")))
    assert _complete_job()["filter_inputs"] == {"v": 1, "filter_ran": False}


def test_a_failed_record_never_unfilters_the_deck(live, monkeypatch):
    """Provenance can't change the deck: the filter's output is served and the
    run says it ran, with no inputs (the audit reads it as not auditable)."""
    _filters_on(monkeypatch)
    real = deck_quality.filter_deck
    kept = []

    def first_only(cards, **kw):
        out, counts = real(cards, **kw)
        kept.extend(out[:1])
        return out[:1], counts
    monkeypatch.setattr(deck_quality, "filter_deck", first_only)
    monkeypatch.setattr(server, "_quality_filter_inputs",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("record")))
    job = _complete_job()
    assert job["filter_inputs"] == {"v": 1, "filter_ran": True}
    assert len(job["cards"]) == len(kept) == 1
