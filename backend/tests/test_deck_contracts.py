"""AC-9 / P2 page contracts (backend/tests/support/deck_contracts.py).

Self-tests on synthetic cards (each assertion passes on a good page and
fails, with a diff, on a bad one), the identity pinned against the
server's `_deck_trade_hash`, and the AC-9 precondition: the trade job is
deterministic, so the same frozen inputs give the same deck by identity
and order (bakeoff_harness, run twice).
"""

from types import SimpleNamespace

import pytest

import backend.server as server
from backend.tests.support import bakeoff_harness as H
from backend.tests.support.deck_contracts import (
    assert_page_is_top_n,
    assert_prefix_stable,
    card_identity,
)

V = "engine-v1"


def _tc(give, recv, partner="opp", trade_id="t-1"):
    """A TradeCard-shaped object (only the identity fields matter)."""
    return SimpleNamespace(trade_id=trade_id, give_player_ids=list(give),
                           receive_player_ids=list(recv), target_user_id=partner)


def _deck(n, partner="opp"):
    return [_tc([f"g{i}"], [f"r{i}", f"x{i}"], partner, trade_id=f"t{i}")
            for i in range(n)]


# ---------------------------------------------------------------------------
# card_identity
# ---------------------------------------------------------------------------

def test_identity_is_content_not_trade_id():
    a = _tc(["p1", "p2"], ["p3"], trade_id="uuid-a")
    b = _tc(["p2", "p1"], ["p3"], trade_id="uuid-b")    # same trade, new build
    assert card_identity(a) == card_identity(b)
    assert card_identity(a) != card_identity(_tc(["p1", "p2"], ["p3"], "other"))
    assert card_identity(a) != card_identity(_tc(["p1"], ["p2", "p3"]))


def test_identity_matches_server_hash_for_every_card_shape():
    give, recv, partner = ["p2", "p1"], ["p3", "pick_2027_1"], "opp"
    expected = server._deck_trade_hash(give, recv, partner)
    served = {"trade_id": "x", "target_user_id": partner,
              "give": [{"id": "p2", "name": "B"}, {"id": "p1", "name": "A"}],
              "receive": [{"id": "p3"}, {"id": "pick_2027_1"}]}
    assert card_identity(_tc(give, recv, partner)) == expected
    assert card_identity(served) == expected
    assert card_identity({"give_player_ids": give, "receive_player_ids": recv,
                          "target_user_id": partner}) == expected
    assert card_identity({"impression_id": "i", "trade_hash": expected}) == expected
    # A missing partner hashes like the server's (`target or ''`).
    assert card_identity(_tc(give, recv, None)) == server._deck_trade_hash(give, recv, None)


def test_identity_refuses_a_card_with_nothing_to_identify():
    with pytest.raises(ValueError):
        card_identity({"trade_id": "only-a-uuid"})


# ---------------------------------------------------------------------------
# assert_page_is_top_n
# ---------------------------------------------------------------------------

def test_page_equal_to_top_n_passes():
    deck = _deck(10)
    page = [_tc(c.give_player_ids, c.receive_player_ids, trade_id="rebuilt")
            for c in deck[:4]]                       # new trade_ids, same cards
    assert_page_is_top_n(page, deck, 4, V, V)
    assert_page_is_top_n(deck[:3], deck[:3], 5, V, V)   # short deck: whole deck


def test_reordered_page_fails_with_a_diff():
    deck = _deck(10)
    page = [deck[1], deck[0], deck[2], deck[3]]
    with pytest.raises(AssertionError) as exc:
        assert_page_is_top_n(page, deck, 4, V, V)
    msg = str(exc.value)
    assert "[0] expected" in msg and "<-- differs" in msg
    assert card_identity(deck[0]) in msg


@pytest.mark.parametrize("page", [
    lambda d: d[:3],                     # short page
    lambda d: d[:3] + [d[5]],            # a card from below the fold
    lambda d: d[:5],                     # too long
])
def test_wrong_page_contents_fail(page):
    deck = _deck(10)
    with pytest.raises(AssertionError):
        assert_page_is_top_n(page(deck), deck, 4, V, V)


def test_engine_version_mismatch_fails():
    deck = _deck(6)
    with pytest.raises(AssertionError, match="engine version"):
        assert_page_is_top_n(deck[:3], deck, 3, "engine-v1", "engine-v2")


# ---------------------------------------------------------------------------
# assert_prefix_stable
# ---------------------------------------------------------------------------

def test_stable_prefix_passes_even_when_repaged():
    deck = _deck(9)
    delivered = [deck[0:3], deck[3:5]]
    later = [deck[0:4], deck[4:9]]           # same order, different page sizes
    assert_prefix_stable(delivered, later)
    assert_prefix_stable([deck[0:3]], [deck[0:3], _deck(3, partner="new")])


@pytest.mark.parametrize("later", [
    lambda d: [[d[1], d[0], d[2]], d[3:6]],          # delivered cards swapped
    lambda d: [[d[0], d[2], d[3]], d[4:6]],          # a delivered card dropped
    lambda d: [d[0:3], [d[3], d[1]]],                # new page repeats d[1]
    lambda d: [d[0:2]],                              # later deck lost the tail
])
def test_unstable_prefix_fails(later):
    deck = _deck(6)
    with pytest.raises(AssertionError):
        assert_prefix_stable([deck[0:3]], later(deck))


# ---------------------------------------------------------------------------
# AC-9 precondition: the engine is deterministic on frozen inputs
# ---------------------------------------------------------------------------

# A larger league than the harness default (which serves one card), so the
# determinism check covers an ordering. Swapped in through the harness's
# module globals, which run_capture reads at call time.
_POOL = [
    ("qb1", "QB One", "QB", "AAA", 26, 1750.0),
    ("qb2", "QB Two", "QB", "EEE", 30, 1580.0),
    ("rb1", "RB One", "RB", "AAA", 24, 1700.0),
    ("rb2", "RB Two", "RB", "BBB", 27, 1520.0),
    ("rb3", "RB Three", "RB", "DDD", 22, 1600.0),
    ("rb4", "RB Four", "RB", "EEE", 25, 1640.0),
    ("wr1", "WR One", "WR", "BBB", 25, 1680.0),
    ("wr2", "WR Two", "WR", "CCC", 29, 1430.0),
    ("wr3", "WR Three", "WR", "DDD", 28, 1490.0),
    ("wr4", "WR Four", "WR", "FFF", 23, 1660.0),
    ("wr5", "WR Five", "WR", "FFF", 26, 1550.0),
    ("te1", "TE One", "TE", "CCC", 23, 1560.0),
    ("te2", "TE Two", "TE", "GGG", 27, 1510.0),
]


def test_trade_job_is_deterministic_on_frozen_inputs(tmp_path, monkeypatch):
    # Hermetic: a local DynastyProcess CSV, which also turns KTC off.
    dp = tmp_path / "dp.csv"
    dp.write_text("player,pos,value_1qb,value_2qb\nQB One,QB,5000,6000\n")
    monkeypatch.setenv("FTF_DP_VALUES_FILE", str(dp))
    monkeypatch.setattr(H, "_POOL", _POOL)
    monkeypatch.setattr(H, "SEED", {pid: elo for pid, *_r, elo in _POOL})
    monkeypatch.setattr(H, "ME_ROSTER", ["qb1", "rb1", "wr2", "te1", "wr5"])
    monkeypatch.setattr(H, "OPP_ROSTER", ["rb2", "wr1", "qb2", "rb4"])
    monkeypatch.setattr(H, "OPP2_ROSTER", ["rb3", "wr3", "wr4", "te2"])

    decks = []
    for _ in range(2):
        capture, job, _eng = H.run_capture()
        assert capture["status"] == "complete", capture["error"]
        served = [card_identity(c) for c in job["cards"]]
        logged = [r["trade_hash"] for r in
                  sorted(capture["impressions"], key=lambda r: r["card_index"])]
        assert served == logged     # served identity == the logged trade_hash
        decks.append(job["cards"])

    first, second = decks
    assert len(first) >= 3, "world too small to test an ordering"
    assert_page_is_top_n(first, second, len(second), V, V)
    assert_page_is_top_n(first[:2], second, 2, V, V)
