"""Live-deck quality filters (backend/deck_quality.py, flag deck.quality_filters).
Operator 2026-10-14, from the Calibration grades of the live engine."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend import deck_quality as dq

SLOTS = ("QB", "RB", "RB", "WR", "WR", "TE", "FLEX")
MARKET = {"v_star": 4000, "v_wr": 3000, "v_te": 3000, "v_qb": 3000, "v_small": 500,
          "p_mid": 2600, "p_low": 1500, "p_wr": 3100, "p_te": 2800, "p_qb": 2500, "p_qb2": 2600,
          "p_wr2": 2950, "pick1": 2900, "nopx": None}
POS = {"v_star": "WR", "v_wr": "WR", "v_te": "TE", "v_qb": "QB", "v_small": "RB", "p_mid": "WR",
       "p_low": "WR", "p_wr": "WR", "p_te": "TE", "p_qb": "QB", "p_qb2": "QB", "p_wr2": "WR",
       "pick1": "PICK", "nopx": "WR"}
ROSTERS = {"V": ["v_star", "v_wr", "v_te", "v_qb", "v_small"],
           "P": ["p_mid", "p_low", "p_wr", "p_te", "p_qb", "p_wr2", "pick1", "nopx"]}


def card(give, receive, partner="P", **flags):
    return SimpleNamespace(give_player_ids=list(give), receive_player_ids=list(receive),
                           target_user_id=partner, **flags)


def run(cards, slots=SLOTS, rosters=ROSTERS):
    return dq.filter_deck(cards, viewer_id="V", market=MARKET.get, position=POS.get,
                          rosters=rosters, lineup_slots=slots)


def kept(c, **kw):
    out, _ = run([c], **kw)
    return bool(out)


def test_breakup_drops_selling_the_best_piece_for_lesser_ones():
    assert not kept(card(["v_star"], ["p_mid", "p_low"]))      # 2600 = 65% of 4000
    assert kept(card(["v_wr"], ["p_wr"]))                      # best piece back is bigger
    assert kept(card(["v_star"], ["p_wr2", "p_low"]))          # 2950 = 74%: allowed


def test_filler_drops_a_piece_too_small_for_the_trade():
    assert not kept(card(["v_wr", "v_small"], ["p_wr"]))       # 500 < 25% of 3100
    out, counts = run([card(["v_wr", "v_small"], ["p_wr"])])
    assert counts["filler"] == 1


def test_redundant_te_and_qb_both_sides():
    assert not kept(card(["v_te"], ["p_wr"]))                  # P keeps a 2800 TE, takes a 3000 one
    assert kept(card(["v_te"], ["p_te"]))                      # TE for TE: P sends his back
    assert not kept(card(["v_wr"], ["p_te"]))                  # V keeps v_te (3000), takes p_te
    assert not kept(card(["v_qb"], ["p_wr"]))                  # 1QB: P keeps a 2500 QB
    sf = SLOTS + ("SUPER_FLEX",)
    assert kept(card(["v_qb"], ["p_wr"]), slots=sf)            # superflex: a second QB starts
    three = {**ROSTERS, "P": ROSTERS["P"] + ["p_qb2"]}
    assert not kept(card(["v_qb"], ["p_wr"]), slots=sf, rosters=three)   # ...but not a third
    assert not kept(card(["v_te"], ["p_wr"]), slots=sf)        # TE capped in every format
    assert kept(card(["v_te"], ["p_wr"]), slots=SLOTS + ("TE",))   # a two-TE league takes a second
    weak = {**ROSTERS, "P": [p for p in ROSTERS["P"] if p != "p_te"]}
    assert kept(card(["v_te"], ["p_wr"]), rosters=weak)        # no comparable TE: a real upgrade


def test_unknown_lineup_skips_only_the_redundant_rule():
    assert kept(card(["v_te"], ["p_wr"]), slots=None)
    assert not kept(card(["v_star"], ["p_mid", "p_low"]), slots=None)


def test_unknown_market_never_triggers_a_value_rule():
    assert kept(card(["v_wr"], ["nopx"]))


def test_protected_cards_are_never_dropped_or_deferred():
    for attr in ("likes_you", "standing_offer_reason", "injected", "wildcard", "owner_published"):
        assert kept(card(["v_star"], ["p_mid", "p_low"], **{attr: "x"}))


def test_repeat_cap_defers_rather_than_drops():
    cards = [card(["v_wr"], ["p_wr"]) for _ in range(5)] + [card(["v_qb"], ["p_qb"])]
    out, counts = dq.filter_deck(cards, viewer_id="V", market=lambda a: 3000.0,
                                 position=lambda a: "WR", rosters={}, lineup_slots=SLOTS)
    assert len(out) == 6 and counts["deferred"] == 2
    assert out[3] is cards[5]                                  # the different card moves up
    assert out[4:] == cards[3:5]                               # over-cap cards keep their order


def test_counts_and_order_preserved():
    cards = [card(["v_wr"], ["p_wr"]), card(["v_star"], ["p_mid", "p_low"]),
             card(["v_wr", "v_small"], ["p_wr"]), card(["v_te"], ["p_wr"])]
    out, counts = run(cards)
    assert out == [cards[0]]
    assert counts == {"breakup": 1, "filler": 1, "redundant": 1, "deferred": 0}


@pytest.mark.parametrize("enabled", [False, True])
def test_trade_job_wiring(enabled):
    """Flag on: filter_deck sees the served deck with the viewer's team and rosters, and its
    output is what gets served. Flag off: never called, deck unchanged."""
    import backend.server as server
    from backend.tests.support import bakeoff_harness as H

    seen: list = []

    def spy(cards, **kw):
        seen.append((list(cards), kw))
        return list(cards)[1:], {"breakup": 1, "filler": 0, "redundant": 0, "deferred": 0}

    patches = [patch.object(server, "_deck_quality_filters_enabled", lambda: enabled),
               patch.object(dq, "filter_deck", spy)]
    capture, job, _ = H.run_capture(extra_patches=patches)
    assert capture["status"] == "complete", capture["error"]
    if not enabled:
        assert seen == []
        return
    assert len(seen) == 1
    cards_in, kw = seen[0]
    assert kw["viewer_id"] == H.ME and set(kw["rosters"]) >= {H.ME, H.OPP, H.OPP2}
    assert len(job["cards"]) == len(cards_in) - 1
