"""Roster-first setup (D-212) — the owner + bilateral engines read `trade_block`.

docs/plans/roster-first-trade-setup/prd.md §4.3, AC-0, AC-7. `trade_block`
mirrors `targets` on the GIVE side (direction < 0 = the team sends the asset
away; `outgoing` is the team's own give list in `_eligible`):
  * owner-v1: +1 `preference_priority` per outgoing trade_block asset, and
    +0.1 `_asset_interest` when direction < 0 (never when direction > 0);
  * bilateral: +0.3 declared interest when direction < 0, and a focal
    outgoing trade_block asset joins the `declared_intent` path.
Gate: `server._owner_generation_context` strips `trade_block` from every
member's prefs when `trades.roster_setup` is OFF, so flag-off constructor
inputs, evidence, request hashes and cards are byte-identical to a league with
no trade_block rows at all (sabotage: delete the strip and the flag-off tests
here fail).
"""

import copy

import pytest

import backend.bakeoff_runner as bakeoff
import backend.database as db
import backend.feature_flags as ff
import backend.server as server
import backend.trade_service as ts
from backend import trade_gen_bilateral as bilateral, trade_gen_owner as owner
from backend.ranking_service import Player
from backend.tests.test_fair_packages import harness, LEAGUE, ME, OPP, SEED  # noqa: F401
from backend.tests.test_owner_generator_routes import owner_harness, worker  # noqa: F401


# ───────────────────────── constructor level (hermetic) ─────────────────────────

@pytest.fixture
def isolated(monkeypatch):
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))


def world(viewer=None, opponent=None, **extra):
    """Two WRs at equal market value, mirroring test_trade_gen_owner.world."""
    spec = {"g": ("WR", 26, 1000), "r": ("WR", 26, 1000)}
    players = {pid: Player(pid, pid, pos, "TST", age) for pid, (pos, age, _) in spec.items()}
    other = ts.LeagueMember("opp", "Other", ["r"],
        {pid: ts.value_to_elo(v) for pid, v in (opponent or {}).items()}, bool(opponent))
    kwargs = dict(players=players, league=ts.League("L", "Synthetic", "sleeper", [other]),
        user_id="me", user_roster=["g"],
        seed_elo={pid: ts.value_to_elo(v) for pid, (_, _, v) in spec.items()},
        user_elo={pid: ts.value_to_elo(v) for pid, v in (viewer or {}).items()},
        outlook="not_sure", opponent_outlooks={"opp": "not_sure"}, fairness_threshold=.75)
    kwargs.update(extra)
    return kwargs


def favorable(**extra):
    return world(viewer={"g": 800, "r": 1200}, opponent={"g": 1200, "r": 800}, **extra)


def test_owner_interest_rises_only_on_the_give_side(isolated):
    base = owner._Search(**favorable())
    tagged = owner._Search(**favorable(manager_preferences={"me": {"trade_block": ["g"]}}))
    give = lambda s: s._asset_interest(s.teams["me"], "g", -1)
    take = lambda s: s._asset_interest(s.teams["me"], "g", 1)
    assert give(tagged) - give(base) == pytest.approx(.1)
    assert take(tagged) == pytest.approx(take(base))   # never a receive-side signal


def test_owner_priority_and_evidence_count_outgoing_trade_block(isolated):
    base, _ = owner.generate_owner_trades(**favorable())
    cards, _ = owner.generate_owner_trades(**favorable(
        manager_preferences={"me": {"trade_block": ["g"]}}))
    assert base and cards
    before, after = base[0].owner_evaluation.as_dict(), cards[0].owner_evaluation.as_dict()
    assert after["preference_priority"] == before["preference_priority"] + 1
    assert after["viewer"]["preferences"]["trade_block"] == ["g"]
    # Evidence gains the key only when the context carried it (flag on).
    assert "trade_block" not in before["viewer"]["preferences"]


def test_counterparty_trade_block_raises_priority_for_receiving_him(isolated):
    """prd §4.3: a league-mate's Move tag is the first per-player signal the
    counterparty side has — it counts on THEIR outgoing (our incoming)."""
    base, _ = owner.generate_owner_trades(**favorable())
    cards, _ = owner.generate_owner_trades(**favorable(
        manager_preferences={"opp": {"trade_block": ["r"]}}))
    assert (cards[0].owner_evaluation.as_dict()["preference_priority"]
            == base[0].owner_evaluation.as_dict()["preference_priority"] + 1)


def test_bilateral_interest_rises_point_three_on_the_give_side(isolated):
    base = bilateral._Search(**favorable())
    tagged = bilateral._Search(**favorable(manager_preferences={"me": {"trade_block": ["g"]}}))
    give = lambda s: s._asset_interest(s.teams["me"], "g", -1)
    take = lambda s: s._asset_interest(s.teams["me"], "g", 1)
    assert give(tagged) - give(base) == pytest.approx(.3)
    assert take(tagged) == pytest.approx(take(base))


def test_bilateral_focal_trade_block_is_declared_intent(isolated):
    """No personal board for the viewer: without a tag the viewer's side is
    `missing_board` and unqualified, so nothing is emitted. Moving the focal
    outgoing asset makes it `declared_intent`, exactly as a target does for
    the focal incoming asset."""
    kwargs = world(opponent={"g": 1200, "r": 800})
    card = ts.TradeCard("x", "L", "me", "opp", "Other", ["g"], ["r"], 0, 0, 0)
    assert bilateral.generate_bilateral_trades(**kwargs)[0] == []
    base = bilateral.evaluate_bilateral_trade(card, **kwargs).as_dict()["viewer"]["intent"]
    assert base["path"] == "missing_board" and base["declared_match"] is False

    kwargs = world(opponent={"g": 1200, "r": 800},
                   manager_preferences={"me": {"trade_block": ["g"]}})
    cards, _ = bilateral.generate_bilateral_trades(**kwargs)
    assert [(c.give_player_ids, c.receive_player_ids) for c in cards] == [(["g"], ["r"])]
    intent = cards[0].owner_evaluation.as_dict()["viewer"]["intent"]
    assert intent["path"] == "declared_intent" and intent["declared_match"] is True
    assert intent["sell_candidate"] == "g"


def test_trade_block_on_incoming_asset_is_not_declared(isolated):
    """Direction matters: tagging the asset you would RECEIVE is not intent."""
    kwargs = world(opponent={"g": 1200, "r": 800},
                   manager_preferences={"me": {"trade_block": ["r"]}})
    assert bilateral.generate_bilateral_trades(**kwargs)[0] == []


# ───────────────────────── the flag gate (server context) ─────────────────────────

ME_BOARD = {**SEED, "a1": 1560., "a2": 1450., "b1": 1700., "b2": 1690., "b3": 1640.}
OPP_BOARD = {**SEED, "a1": 1700., "a2": 1620., "b1": 1560., "b2": 1550., "b3": 1500.}


def _context(harness):
    _, _, sess, svc, league = harness
    return server._owner_generation_context(
        sess=sess, service=sess["service"], league=league, players=svc._players,
        seed_map=dict(SEED), user_elo=dict(ME_BOARD), user_roster=list(sess["user_roster"]),
        scoring_format="1qb_ppr", fairness_threshold=.5,
        captured_rankings={OPP: {"elo_ratings": dict(OPP_BOARD),
                                 "confidence_sources": {p: "explicit" for p in OPP_BOARD}}},
        pinned_give_players=None, pinned_receive_players=None, opponent_user_id=None,
        trade_intent=None)


def _run(harness, *, rows, flag_on, arm):
    ff._flags_cache = {**ff._flags_cache, "trades.roster_setup": flag_on}
    ts._cfg["owner_bilateral_enabled"] = 1. if arm == "bilateral" else 0.
    for uid, pid in ((ME, "a2"), (OPP, "b2")):
        db.set_asset_preference(uid, LEAGUE, pid, "trade_block" if rows else None)
    context = _context(harness)
    prefs = copy.deepcopy(context["manager_preferences"])
    request_hash = server._owner_selected_assignment(context, "organic", serve=True)["request_hash"]
    cards, report = bakeoff.owner_generator(context["config"])(**context)
    return {"prefs": prefs, "hash": request_hash, "report": report.snapshot_json,
            "cards": [(c.give_player_ids, c.receive_player_ids, c.owner_evaluation.snapshot_json)
                      for c in cards]}


@pytest.mark.parametrize("arm", ["owner", "bilateral"])
def test_flag_off_is_byte_identical_to_no_trade_block_rows(harness, arm):
    clean = _run(harness, rows=False, flag_on=False, arm=arm)
    tagged = _run(harness, rows=True, flag_on=False, arm=arm)
    assert all("trade_block" not in p for p in tagged["prefs"].values())
    assert tagged == clean
    assert clean["cards"], "fixture must emit cards or identity proves nothing"


@pytest.mark.parametrize("arm", ["owner", "bilateral"])
def test_flag_on_reads_trade_block_for_every_member(harness, arm):
    """Sensitivity check for the identity test above: the same rows with the
    flag ON reach the constructors and change the frozen output."""
    clean = _run(harness, rows=False, flag_on=False, arm=arm)
    tagged = _run(harness, rows=True, flag_on=True, arm=arm)
    assert tagged["prefs"][ME]["trade_block"] == ["a2"]
    assert tagged["prefs"][OPP]["trade_block"] == ["b2"]
    assert tagged["hash"] != clean["hash"]
    assert tagged["cards"] != clean["cards"]


def test_flag_off_strips_viewer_preferences_override_too(harness):
    """The calibration adapter passes `viewer_preferences` straight in; the
    gate sits after that merge, so it is covered by the same strip."""
    _, _, sess, svc, league = harness
    ff._flags_cache = {**ff._flags_cache, "trades.roster_setup": False}
    context = server._owner_generation_context(
        sess=sess, service=sess["service"], league=league, players=svc._players,
        seed_map=dict(SEED), user_elo=dict(ME_BOARD), user_roster=list(sess["user_roster"]),
        scoring_format="1qb_ppr", fairness_threshold=.5, captured_rankings={},
        viewer_preferences={"trade_block": ["a1"], "targets": ["b1"]})
    assert "trade_block" not in context["manager_preferences"][ME]
    assert context["manager_preferences"][ME]["targets"] == ["b1"]


# ───────────────────────── the live job path (review fix) ─────────────────────────

@pytest.mark.parametrize("flag_on", [False, True])
def test_live_job_carries_the_viewer_s_own_trade_block_to_the_constructor(
        owner_harness, monkeypatch, flag_on):
    """`_run_trade_job` builds `viewer_preferences` itself from its one asset
    prefs read, and `_owner_generation_context` then skips the viewer's DB
    load. The viewer's Move tags must ride that dict, or only league-mates'
    tags would ever reach the engine (review finding on 12166a94)."""
    ff._flags_cache["trades.roster_setup"] = flag_on
    db.set_asset_preference(ME, LEAGUE, "a1", "trade_block")
    db.set_asset_preference(OPP, LEAGUE, "b2", "trade_block")
    seen = []
    real = server._bakeoff.owner_generator

    def spy(config=None):
        generate = real(config)

        def capture(**context):
            seen.append(copy.deepcopy(context["manager_preferences"]))
            return generate(**context)
        return capture
    monkeypatch.setattr(server._bakeoff, "owner_generator", spy)
    worker(owner_harness, monkeypatch)
    assert seen, "the owner constructor never ran on the live job path"
    for prefs in seen:
        if flag_on:
            assert prefs[ME]["trade_block"] == ["a1"]
            assert prefs[OPP]["trade_block"] == ["b2"]
        else:
            assert all("trade_block" not in p for p in prefs.values())
