"""I-2 post-launch copy follow-ups: the asset-aware unnamed fallback, and the
receipt variants of the ownership sentence (`backend/ownership_copy.py`).

The wording of the pick and asset subjects and of the receipt variants is
marketing's final copy (marketing-lead §6 addendum 9, 2026-10-27). These tests
pin the mechanism and the exact strings, so a copy change is a change to
`ownership_copy.py` and to the strings here.

  1. A refused asset with no name on file is counted, never shown by id. The
     count subject matches the assets: one pick -> "A draft pick in this
     trade", several picks -> "{n} draft picks in this trade", players and
     picks together -> "{n} of the players and picks in this trade". Players
     only is unchanged.
  2. `refusal_message(..., receipt=True)` is the same sentence minus "so
     nothing was sent", for team overhaul's prepare-send receipt (wired and
     tested in test_i2_overhaul.py). Send-time stays the default.

SABOTAGE (each proven red, then restored, 2026-10-27):
  * `is_pick_id` always False -> the pick/asset tests here, the predicate
    parity tests, the receipt pick test in test_i2_overhaul.py and the two MFL
    end-to-end tests go red;
  * the /prepare-send route building its receipt with the send-time copy ->
    the three prepare-receipt tests in test_i2_overhaul.py go red;
  * the /send re-check building its receipt with the receipt variant -> the
    two send 409 tests and the prepare-vs-send contrast go red.

No network, no DB.
"""
import pytest

from backend import database as db
from backend import ownership_copy as oc
from backend import pick_values

LEAGUE = "1234567890"
PICK, PICK2 = f"{LEAGUE}_2027_1_4", f"{LEAGUE}_2028_2_7"
GENERIC = "generic_pick_1_early"
PLAYER, PLAYER2, PLAYER3 = "4046", "9509", "6794"
SEND = ", so nothing was sent. Find a new trade."
RECEIPT = ". Find a new trade."


def _msg(side, assets, names=None, team=None, *, receipt=False):
    return oc.refusal_message(side, assets, names or {}, team, receipt=receipt)


# ---------------------------------------------------------------------------
# 1. The unnamed fallback follows the assets
# ---------------------------------------------------------------------------

def test_one_unnamed_pick_says_pick():
    assert _msg("give", [PICK]) == "A draft pick in this trade is no longer on your roster" + SEND
    assert _msg("give", [GENERIC]) == "A draft pick in this trade is no longer on your roster" + SEND


def test_two_unnamed_picks_are_counted_as_picks():
    assert _msg("give", [PICK, PICK2]) == "2 draft picks in this trade are no longer on your roster" + SEND
    assert _msg("give", [PICK, GENERIC, PICK2]) == "3 draft picks in this trade are no longer on your roster" + SEND


def test_a_mixed_unnamed_set_is_counted_as_assets():
    assert _msg("give", [PLAYER, PICK]) == "2 of the players and picks in this trade are no longer on your roster" + SEND
    assert (_msg("give", [PICK, PLAYER, PLAYER2])
            == "3 of the players and picks in this trade are no longer on your roster" + SEND)


def test_one_missing_name_counts_every_offending_asset_by_what_they_all_are():
    # The count covers ALL the offending assets (as it always did), so the
    # subject describes all of them, not just the unnamed one.
    assert (_msg("give", [PLAYER, PICK], {PLAYER: "Josh Allen"})
            == "2 of the players and picks in this trade are no longer on your roster" + SEND)
    assert (_msg("give", [PICK, PICK2], {PICK: "2027 1st (from Dolphins Den)"})
            == "2 draft picks in this trade are no longer on your roster" + SEND)
    assert (_msg("give", [PLAYER, PLAYER2], {PLAYER: "Josh Allen"})
            == "2 players in this trade are no longer on your roster" + SEND)


def test_marketings_final_strings_exact():
    """Marketing-lead §6 addendum 9 (2026-10-27), verbatim: the three
    subjects, and each in a full sentence (send-time, receipt, both sides)."""
    assert oc.ONE_UNNAMED_PICK == "A draft pick in this trade"
    assert oc.N_UNNAMED_PICKS == "{n} draft picks in this trade"
    assert oc.N_UNNAMED_ASSETS == "{n} of the players and picks in this trade"
    # Approved unchanged from the draft.
    assert oc.RECEIPT_ASSET_NOT_OWNED == "{assets} {verb} no longer on your roster. Find a new trade."
    assert oc.RECEIPT_COUNTERPARTY_NOT_OWNED == (
        "{assets} {verb} no longer on {team}’s roster. Find a new trade.")
    assert oc.RECEIPT_COUNTERPARTY_NOT_OWNED_UNNAMED == (
        "{assets} {verb} no longer on the other manager’s roster. Find a new trade.")

    assert _msg("give", [PICK]) == (
        "A draft pick in this trade is no longer on your roster, so nothing was sent. Find a new trade.")
    assert _msg("give", [PICK, PICK2]) == (
        "2 draft picks in this trade are no longer on your roster, so nothing was sent. Find a new trade.")
    assert _msg("give", [PLAYER, PICK]) == (
        "2 of the players and picks in this trade are no longer on your roster, "
        "so nothing was sent. Find a new trade.")
    assert _msg("receive", [PICK], team="Chris") == (
        "A draft pick in this trade is no longer on Chris’s roster, so nothing was sent. Find a new trade.")
    assert _msg("receive", [PLAYER, PICK]) == (
        "2 of the players and picks in this trade are no longer on the other manager’s roster, "
        "so nothing was sent. Find a new trade.")

    assert _msg("give", [PICK], receipt=True) == (
        "A draft pick in this trade is no longer on your roster. Find a new trade.")
    assert _msg("give", [PICK, PICK2], receipt=True) == (
        "2 draft picks in this trade are no longer on your roster. Find a new trade.")
    assert _msg("give", [PLAYER, PICK], receipt=True) == (
        "2 of the players and picks in this trade are no longer on your roster. Find a new trade.")
    assert _msg("receive", [PLAYER, PICK], team="Chris", receipt=True) == (
        "2 of the players and picks in this trade are no longer on Chris’s roster. Find a new trade.")
    assert _msg("receive", [PICK, PICK2], receipt=True) == (
        "2 draft picks in this trade are no longer on the other manager’s roster. Find a new trade.")


def test_a_named_pick_still_uses_its_name():
    assert (_msg("give", [PICK], {PICK: "2027 1st (from Dolphins Den)"})
            == "2027 1st (from Dolphins Den) is no longer on your roster" + SEND)
    assert (_msg("give", [PLAYER, PICK], {PLAYER: "Josh Allen", PICK: "2027 1st (from Dolphins Den)"})
            == "Josh Allen and 2027 1st (from Dolphins Den) are no longer on your roster" + SEND)
    assert (_msg("receive", [PICK2], {PICK2: "2028 2nd"}, "Dolphins Den")
            == "2028 2nd is no longer on Dolphins Den’s roster" + SEND)


def test_the_player_fallback_is_unchanged():
    assert _msg("give", [PLAYER]) == "A player in this trade is no longer on your roster" + SEND
    assert _msg("give", [PLAYER, PLAYER2]) == "2 players in this trade are no longer on your roster" + SEND
    assert (_msg("receive", [PLAYER, PLAYER2, PLAYER3], team="Chris")
            == "3 players in this trade are no longer on Chris’s roster" + SEND)
    assert (_msg("receive", [PLAYER])
            == "A player in this trade is no longer on the other manager’s roster" + SEND)
    assert (_msg("give", [PLAYER, PLAYER2, PLAYER3],
                 {PLAYER: "Josh Allen", PLAYER2: "Bijan Robinson", PLAYER3: "CeeDee Lamb"})
            == "Josh Allen, Bijan Robinson and CeeDee Lamb are no longer on your roster" + SEND)


def test_the_counterparty_side_follows_the_assets_too():
    assert _msg("receive", [PICK], team="Dolphins Den") == (
        "A draft pick in this trade is no longer on Dolphins Den’s roster" + SEND)
    assert _msg("receive", [PICK, PICK2]) == (
        "2 draft picks in this trade are no longer on the other manager’s roster" + SEND)
    assert _msg("receive", [PICK, PLAYER], team="Chris") == (
        "2 of the players and picks in this trade are no longer on Chris’s roster" + SEND)


@pytest.mark.parametrize("assets", [
    [PICK], [GENERIC], [PICK, PICK2], [PLAYER, PICK], [PLAYER], [PLAYER, PLAYER2, PICK, PICK2]])
@pytest.mark.parametrize("side,team", [("give", None), ("receive", "Chris"), ("receive", None)])
@pytest.mark.parametrize("receipt", [False, True])
def test_never_a_raw_id(assets, side, team, receipt):
    message = _msg(side, assets, team=team, receipt=receipt)
    assert not any(a in message for a in assets), message


# ---------------------------------------------------------------------------
# The pick predicate matches the server's
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("league_id", [LEAGUE, "league_demo", "espn_555", "a_b_c", "2027"])
def test_is_pick_id_agrees_with_the_servers_predicate(league_id):
    from backend import server          # fine under pytest; never imported from plain Python
    samples = [
        db.make_pick_id(league_id, 2027, 1, "4"),            # the real producer
        db.make_pick_id(league_id, 2030, 12, "0007"),
        db.make_pick_id(league_id, 2027, 1, "x_y"),          # an original-roster id with an underscore
        f"{league_id}_2027_1_", f"{league_id}_27_1_4", f"{league_id}_2027_123_4",
        f"{league_id}_2027_1", f"{league_id}_2027__4",
        "generic_pick_1_early", "generic_pick_4_late", "generic_pick_",
        "4046", "DEN", "FP_0007_2027_1", "DP_01_02", "12_34", "", None,
    ]
    for a in samples:
        assert oc.is_pick_id(a) == server._is_ftf_pick_asset(league_id, a), (league_id, a)
    assert oc.is_pick_id(db.make_pick_id(league_id, 2027, 1, "4")) is True
    assert oc.is_pick_id("4046") is False


def test_the_generic_rung_prefix_is_the_shared_one():
    assert oc._GENERIC_PICK_ID_PREFIX == pick_values.GENERIC_PICK_ID_PREFIX


# ---------------------------------------------------------------------------
# 2. Receipt variants
# ---------------------------------------------------------------------------

def test_receipt_variant_is_the_send_time_sentence_without_nothing_was_sent():
    names = {PLAYER: "Josh Allen", PLAYER2: "Bijan Robinson"}
    assert (_msg("give", [PLAYER, PLAYER2], names, receipt=True)
            == "Josh Allen and Bijan Robinson are no longer on your roster" + RECEIPT)
    assert (_msg("receive", [PLAYER], names, "Chris", receipt=True)
            == "Josh Allen is no longer on Chris’s roster" + RECEIPT)
    assert (_msg("receive", [PLAYER], names, receipt=True)
            == "Josh Allen is no longer on the other manager’s roster" + RECEIPT)


def test_receipt_variant_keeps_the_pick_and_count_fallbacks():
    assert _msg("give", [PICK], receipt=True) == "A draft pick in this trade is no longer on your roster" + RECEIPT
    assert _msg("give", [PICK, PICK2], receipt=True) == "2 draft picks in this trade are no longer on your roster" + RECEIPT
    assert _msg("give", [PLAYER, PICK], receipt=True) == "2 of the players and picks in this trade are no longer on your roster" + RECEIPT
    assert _msg("give", [PLAYER], receipt=True) == "A player in this trade is no longer on your roster" + RECEIPT
    assert (_msg("receive", [PICK, PICK2], receipt=True)
            == "2 draft picks in this trade are no longer on the other manager’s roster" + RECEIPT)
    assert (_msg("receive", [PLAYER, PICK], team="Chris", receipt=True)
            == "2 of the players and picks in this trade are no longer on Chris’s roster" + RECEIPT)


def test_send_time_is_still_the_default():
    assert oc.refusal_message("give", [PLAYER], {PLAYER: "Josh Allen"}) == (
        "Josh Allen is no longer on your roster" + SEND)
    assert oc.refusal_message("receive", [PLAYER], {PLAYER: "Josh Allen"}, "Chris") == (
        "Josh Allen is no longer on Chris’s roster" + SEND)
