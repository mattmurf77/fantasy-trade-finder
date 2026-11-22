"""Home's next move: the pure composer (docs/plans/home-next-move/scope.md §3,
D-278). Hand-built served blocks in the exact shapes `team_direction`,
`maxpf_moves.compose` and `playoff_targets.compose` serve; the last two tests
run the composer over the real fixture blocks.

- test_sell_names_the_first_max_pf_row / test_buy_names_the_first_target_row:
  both directions, every field the app reads. Sabotage: take rows[0] instead
  of the lowest rank (the rows below are served out of order).
- test_direction_gates: no direction block (flag off), an unusable forecast,
  no direction, a direction not offered.
- test_sell_gates / test_buy_gates: every "suggest nothing" state, each with
  its reason; never the second row.
- test_settled_carries_the_proof_both_sides / test_only_settled_carries_a_proof
  (D-279): `settled` carries the baseline's playoff_proof; every other none
  answer keeps it null.
- test_never_names_a_player_the_list_would_not_show_first: over every
  combination of the gates, a ready answer is always the list's first row,
  with a Find trades button and nothing in front of it.
- test_real_blocks: the composer over the real served blocks of the fixture
  forecast, both directions.
"""
from __future__ import annotations

from copy import deepcopy
import itertools

import pytest

from backend.league_projections import next_move, team_direction


def direction(primary="draft_pick", *, state="ready", offered=("draft_pick", "playoffs")):
    return {"version": 1, "state": state, "reason": None if state == "ready" else "stale", "primary": primary,
            "options": {k: {"offered": k in offered, "reason": None if k in offered else "none_found"}
                        for k in ("draft_pick", "playoffs")}}


def maxpf_row(rank, pid, **patch):
    row = {"rank": rank, "player_id": pid, "name": f"Player {pid}", "short_name": f"P. {pid}", "position": "WR",
           "playoff_probability": {"now": .30, "after": .22}, "top3_probability": {"now": .20, "after": .31},
           "label": {"now": "1.06", "after": "1.04"}, "keep": False, "passes_threshold": True,
           "most_likely_pick": {"now": {"slot": 5, "label": "1.05", "probability": .3},
                                "after": {"slot": 3, "label": "1.03", "probability": .35}}}
    return {**row, **patch}


def maxpf(rows=None, **patch):
    block = {"version": 1, "state": "ready", "reason": None, "captured_at": "2026-11-17T14:00:00Z",
             "draft_order": {"rule": "maxpf_lowest_first", "set_at": "2026-11-01"}, "saved_outlook": None,
             "pick_owner": {"owns_own_pick": True, "owner_roster_id": 1, "owner_name": "Mine"},
             "baseline": {"playoff_probability": .30, "playoff_clinched": False, "playoff_eliminated": False},
             "roster_player_ids": ["101", "102", "103"],
             "rows": rows if rows is not None else [maxpf_row(2, "102"), maxpf_row(1, "101")]}
    return {**block, **patch}


def target_row(rank, pid, **patch):
    row = {"rank": rank, "player_id": pid, "name": f"Target {pid}", "short_name": f"T. {pid}", "position": "RB",
           "playoff_probability": {"now": .55, "after": .63}, "passes_threshold": True,
           "seller": {"roster_id": 4, "name": "Sellers FC", "playoff_probability": .2,
                      "playoff_clinched": False, "playoff_eliminated": False}}
    return {**row, **patch}


def targets(rows=None, **patch):
    block = {"version": 1, "state": "ready", "reason": None, "captured_at": "2026-11-17T14:00:00Z",
             "baseline": {"playoff_probability": .55, "playoff_clinched": False, "playoff_eliminated": False},
             "rows": rows if rows is not None else [target_row(2, "202"), target_row(1, "201")]}
    return {**block, **patch}


def test_sell_names_the_first_max_pf_row():
    block = next_move.compose(direction("draft_pick"), maxpf(), targets())
    assert block == {
        "version": 1, "state": "ready", "reason": None, "direction": "draft_pick", "action": "sell",
        "player": {"player_id": "101", "name": "Player 101", "short_name": "P. 101", "position": "WR"},
        "rank": 1, "seller": None, "captured_at": "2026-11-17T14:00:00Z",
        "playoff_probability": {"now": .30, "after": .22},
        "playoff_proof": {"playoff_clinched": False, "playoff_eliminated": False},
        "pick": {"now": "1.06", "after": "1.04"},
        "most_likely_pick": maxpf_row(1, "101")["most_likely_pick"],
        "top3_probability": {"now": .20, "after": .31}}


def test_buy_names_the_first_target_row():
    block = next_move.compose(direction("playoffs"), maxpf(), targets())
    assert block == {
        "version": 1, "state": "ready", "reason": None, "direction": "playoffs", "action": "buy",
        "player": {"player_id": "201", "name": "Target 201", "short_name": "T. 201", "position": "RB"},
        "rank": 1, "seller": {"roster_id": 4, "name": "Sellers FC"}, "captured_at": "2026-11-17T14:00:00Z",
        "playoff_probability": {"now": .55, "after": .63},
        "playoff_proof": {"playoff_clinched": False, "playoff_eliminated": False},
        "pick": None, "most_likely_pick": None, "top3_probability": None}


def test_the_shape_is_the_same_in_every_state():
    keys = set(next_move.compose(direction("draft_pick"), maxpf(), None))
    for block in (next_move.compose(None), next_move.read_failed(), next_move.compose(direction("playoffs"), None, None),
                  next_move.compose(direction("playoffs"), None, targets())):
        assert set(block) == keys and block["version"] == 1


@pytest.mark.parametrize("given, reason, direction_key", [
    ((None,), "direction_off", None),
    ((direction(state="unavailable"),), "unavailable", None),
    ((direction(primary=None),), "no_direction", None),
    ((direction("draft_pick", offered=("playoffs",)), maxpf()), "not_offered", "draft_pick"),
    ((direction("playoffs", offered=("draft_pick",)), maxpf(), targets()), "not_offered", "playoffs"),
])
def test_direction_gates(given, reason, direction_key):
    block = next_move.compose(*given)
    assert block["state"] == "none" and block["reason"] == reason and block["direction"] == direction_key
    assert block["player"] is None and block["action"] is None


@pytest.mark.parametrize("block, reason", [
    (None, "no_moves"),                                                   # flag off: no block served
    (maxpf(state="no_moves"), "no_moves"),
    (maxpf(state="unavailable"), "no_moves"),
    (maxpf(pick_owner={"owns_own_pick": False, "owner_name": "Rivals"}), "pick_owned_elsewhere"),
    (maxpf(pick_owner=None), "pick_owned_elsewhere"),
    # Over 45% with no Rebuilding / Tanking outlook: the list starts behind "Show moves".
    (maxpf(baseline={"playoff_probability": .46, "playoff_clinched": False, "playoff_eliminated": False}), "collapsed"),
    (maxpf(baseline={"playoff_probability": .30, "playoff_clinched": True, "playoff_eliminated": False}), "settled"),
    (maxpf(rows=[]), "no_moves"),
    (maxpf(rows=[maxpf_row(1, "101", keep=True), maxpf_row(2, "102")]), "keep"),
    (maxpf(rows=[maxpf_row(1, "101", passes_threshold=False), maxpf_row(2, "102")]), "below_threshold"),
])
def test_sell_gates(block, reason):
    out = next_move.compose(direction("draft_pick"), block, targets())
    assert (out["state"], out["reason"], out["direction"], out["player"]) == ("none", reason, "draft_pick", None)


def test_sell_follows_the_saved_outlook():
    # 60% would be collapsed, but a saved Rebuilding / Tanking outlook opens the list (the card's lean).
    high = {"playoff_probability": .60, "playoff_clinched": False, "playoff_eliminated": False}
    assert next_move.compose(direction("draft_pick"), maxpf(baseline=high))["reason"] == "collapsed"
    for outlook in ("rebuilder", "jets"):
        out = next_move.compose(direction("draft_pick"), maxpf(baseline=high, saved_outlook=outlook))
        assert out["state"] == "ready" and out["player"]["player_id"] == "101"
    # 45% exactly is the lean's own inclusive cut.
    edge = {**high, "playoff_probability": .45}
    assert next_move.compose(direction("draft_pick"), maxpf(baseline=edge))["state"] == "ready"


@pytest.mark.parametrize("block, reason", [
    (None, "no_targets"),
    (targets(state="no_targets"), "no_targets"),
    (targets(state="near_certain"), "no_targets"),
    (targets(baseline={"playoff_probability": .55, "playoff_clinched": True, "playoff_eliminated": False}), "settled"),
    (targets(baseline={"playoff_probability": .55, "playoff_clinched": False, "playoff_eliminated": True}), "settled"),
    (targets(rows=[]), "no_targets"),
    (targets(rows=[target_row(1, "201", passes_threshold=False), target_row(2, "202")]), "below_threshold"),
])
def test_buy_gates(block, reason):
    out = next_move.compose(direction("playoffs"), maxpf(), block)
    assert (out["state"], out["reason"], out["direction"], out["player"]) == ("none", reason, "playoffs", None)


def test_settled_carries_the_proof_both_sides():
    """D-279 (docs/plans/next-move-empty/scope.md): a `settled` answer carries
    the baseline's `playoff_proof`, so the app can say clinched or eliminated
    without deciding it. Every other field after `direction` stays null.
    Sabotage: drop the proof from either `settled` return."""
    clinched = {"playoff_probability": .30, "playoff_clinched": True, "playoff_eliminated": False}
    out = next_move.compose(direction("draft_pick"), maxpf(baseline=clinched), targets())
    assert (out["state"], out["reason"], out["direction"]) == ("none", "settled", "draft_pick")
    assert out["playoff_proof"] == {"playoff_clinched": True, "playoff_eliminated": False}
    for baseline, proof in (({"playoff_probability": .55, "playoff_clinched": True, "playoff_eliminated": False},
                             {"playoff_clinched": True, "playoff_eliminated": False}),
                            ({"playoff_probability": .55, "playoff_clinched": False, "playoff_eliminated": True},
                             {"playoff_clinched": False, "playoff_eliminated": True})):
        out = next_move.compose(direction("playoffs"), maxpf(), targets(baseline=baseline))
        assert (out["state"], out["reason"], out["direction"]) == ("none", "settled", "playoffs")
        assert out["playoff_proof"] == proof
    for key in ("action", "player", "rank", "seller", "captured_at", "playoff_probability", "pick",
                "most_likely_pick", "top3_probability"):
        assert out[key] is None, key


def test_only_settled_carries_a_proof():
    """Every other `none` answer keeps `playoff_proof` null (build 199's shape)."""
    answers = [next_move.compose(None), next_move.read_failed(), next_move.compose(direction(state="unavailable")),
               next_move.compose(direction(primary=None)),
               next_move.compose(direction("draft_pick", offered=("playoffs",)), maxpf()),
               next_move.compose(direction("draft_pick"), None),
               next_move.compose(direction("draft_pick"), maxpf(pick_owner=None)),
               next_move.compose(direction("draft_pick"), maxpf(baseline={"playoff_probability": .8})),
               next_move.compose(direction("draft_pick"), maxpf(rows=[maxpf_row(1, "101", keep=True)])),
               next_move.compose(direction("draft_pick"), maxpf(rows=[maxpf_row(1, "101", passes_threshold=False)])),
               next_move.compose(direction("playoffs"), None, None),
               next_move.compose(direction("playoffs"), None, targets(rows=[])),
               next_move.compose(direction("playoffs"), None,
                                 targets(rows=[target_row(1, "201", passes_threshold=False)]))]
    reasons = {a["reason"] for a in answers}
    assert reasons == {"direction_off", "read_failed", "unavailable", "no_direction", "not_offered", "no_moves",
                       "pick_owned_elsewhere", "collapsed", "keep", "below_threshold", "no_targets"}
    assert all(a["state"] == "none" and a["playoff_proof"] is None for a in answers)


def test_buy_takes_the_first_served_row_after_the_read_drops_a_team():
    # The read drops the rows of a team that stopped selling, so the served
    # list can start at saved rank 2: that is the list's first row, and the move.
    out = next_move.compose(direction("playoffs"), None, targets(rows=[target_row(3, "203"), target_row(2, "202")]))
    assert out["state"] == "ready" and out["player"]["player_id"] == "202" and out["rank"] == 2


def test_never_names_a_player_the_list_would_not_show_first():
    seen = 0
    for keep, passes, rule, owns, p, outlook in itertools.product(
            (False, True), (False, True), (None, "maxpf_lowest_first"), (True, False), (.2, .45, .5, .8),
            (None, "contender", "rebuilder", "jets")):
        rows = [maxpf_row(3, "103"), maxpf_row(1, "101", keep=keep, passes_threshold=passes), maxpf_row(2, "102")]
        block = maxpf(rows=rows, draft_order={"rule": rule, "set_at": None}, saved_outlook=outlook,
                      pick_owner={"owns_own_pick": owns, "owner_name": "x"},
                      baseline={"playoff_probability": p, "playoff_clinched": False, "playoff_eliminated": False})
        out = next_move.compose(direction("draft_pick"), block)
        if out["state"] != "ready":
            assert out["player"] is None
            continue
        seen += 1
        # The list's first row, its Find trades button (no Keep), passing,
        # and nothing in front of the list (no owner gate, not collapsed).
        # The draft-order question shows above the rows and hides nothing.
        assert out["player"]["player_id"] == "101" and not keep and passes and owns
        assert p <= .45 or outlook in ("rebuilder", "jets")
    # Two gate combinations pass (no Keep, passing, own pick; answered or not):
    # 20% and 45% with any outlook (8), 50% and 80% only when Rebuilding or Tanking (4).
    assert seen == 24


@pytest.fixture(scope="module")
def fixture_blocks():
    from backend.league_projections import maxpf_moves, playoff_targets, recommendation, batch
    from backend.tests.test_maxpf_moves import _block, _result
    from backend.tests.test_playoff_targets import VIEWER, _targets
    cuts = recommendation.thresholds(batch.settings())
    sell_saved = {**deepcopy(_result()), "max_pf_moves": deepcopy(_block())}
    buy_saved = {**deepcopy(_result()), "viewer_roster_id": VIEWER,
                 "playoff_targets": deepcopy(_targets(outlooks=((3, "rebuilder"),)))}
    return sell_saved, buy_saved, cuts, maxpf_moves, playoff_targets


def test_real_blocks(fixture_blocks):
    sell_saved, buy_saved, cuts, maxpf_moves, playoff_targets = fixture_blocks
    # Draft pick: the fixture viewer (roster 1, 88%) with a saved Rebuilding
    # outlook and the draft order answered, so the list is open on Standings.
    moves = maxpf_moves.compose("current", sell_saved, draft_order={"rule": "maxpf_lowest_first", "set_at": "x"},
                                saved_outlook="rebuilder", cuts=cuts)
    card = team_direction.compose("current", sell_saved, saved_outlook="rebuilder", draft_order=None,
                                  cuts=team_direction.settings(), max_pf_on=True, max_pf_block=moves)
    assert moves["state"] == "ready" and card["primary"] == "draft_pick"
    first = min(moves["rows"], key=lambda r: r["rank"])
    out = next_move.compose(card, moves, None)
    if first["passes_threshold"]:
        assert out["state"] == "ready" and out["action"] == "sell"
        assert out["player"]["player_id"] == first["player_id"] and out["pick"] == first["label"]
        assert out["player"]["player_id"] in moves["roster_player_ids"]
    else:
        assert (out["state"], out["reason"]) == ("none", "below_threshold")
    # Unanswered question: the list still shows its rows (the question sits
    # above them), so the same sell is suggested.
    unanswered = maxpf_moves.compose("current", sell_saved, draft_order=None, saved_outlook="rebuilder", cuts=cuts)
    assert next_move.compose(card, unanswered, None) == out
    # Answered with a non-max-PF order: the list has no rows
    # (draft_order_not_maxpf), the card does not offer the draft pick and
    # serves no projected pick; nothing is suggested.
    for rule in ("reverse_standings", "lottery_or_other"):
        order = {"rule": rule, "set_at": "x"}
        moves_np = maxpf_moves.compose("current", sell_saved, draft_order=order, saved_outlook="rebuilder", cuts=cuts)
        card_np = team_direction.compose("current", sell_saved, saved_outlook="rebuilder", draft_order=order,
                                         cuts=team_direction.settings(), max_pf_on=True, max_pf_block=moves_np)
        assert moves_np["state"] == "draft_order_not_maxpf" and moves_np["rows"] == []
        assert card_np["options"]["draft_pick"] == {"offered": False, "reason": "draft_order_not_maxpf"}
        assert card_np["projected_pick"] is None and card_np["primary"] is None
        assert next_move.compose(card_np, moves_np, None)["reason"] == "no_direction"
        # Even if handed a draft-pick direction, a non-ready list gives nothing.
        assert next_move.compose(direction("draft_pick"), moves_np, None)["reason"] == "no_moves"
    # Playoffs: the fixture's roster 7 (69%) with roster 3 selling by outlook.
    served = playoff_targets.compose("current", buy_saved, live_outlooks={3: "rebuilder"}, cuts=cuts)
    card = team_direction.compose("current", buy_saved, cuts=team_direction.settings(), targets_on=True,
                                  targets_block=served)
    assert served["state"] == "ready" and card["primary"] == "playoffs"
    first = min(served["rows"], key=lambda r: r["rank"])
    out = next_move.compose(card, None, served)
    assert out["state"] == "ready" and out["action"] == "buy" and out["player"]["player_id"] == first["player_id"]
    assert out["seller"] == {"roster_id": first["seller"]["roster_id"], "name": first["seller"]["name"]}
    assert out["playoff_probability"] == first["playoff_probability"]
    assert out["playoff_probability"]["after"] > out["playoff_probability"]["now"]
