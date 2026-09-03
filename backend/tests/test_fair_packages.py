"""#384 W6-B / D-153 — POST /api/trades/fair-packages.

The operator's ruling, verbatim: *"this type of request shouldn't go through
our models. It should be a much simpler set of cards solving for fairness
only. Similar to how we determine the consolidate and downgrade suggestions
already."* So Find a Trade with a FILLED canvas is one synchronous fairness
sweep, not a job: the canvas's give side is an ANCHOR and the search is over
the return.

What this file pins:
  • THE GATE — `calc.merged_layout` off ⇒ 404 `feature_disabled`.
  • ANCHOR EXACTNESS — every idea gives away exactly the canvas give set. This
    is the whole contract: an idea whose give side drifts is a different trade
    than the one the user built.
  • PARTNER SCOPE — `opponent_user_id` limits the sweep to that league-mate;
    a stranger id returns `no_partner` rather than a league-wide sweep.
  • PREFERRED RECEIVE — canvas receive assets are a PREFERENCE, not a
    constraint (this is what retires Q-029's second half): ideas containing all
    of them sort first, ideas that cannot are still returned.
  • THE GATES — an untouchable on the GIVE side is the caller's own rule, so it
    refuses with `give_untouchable` and returns nothing; a not-interested asset
    is excluded from every return.
  • RELAXED REFILL — the #189 convention: the widened band surfaces only when
    the strict band is empty, and stays labelled.
  • THE CAP — `fair_packages_cap`, one flat list.
  • IDEMPOTENT IDS — `fairpk_<sha1…>` is set-semantic and stable across calls.
  • SWIPE-RECONSTRUCT — a card from this route can actually be swiped: the
    id was never minted by a generator, so `_reconstruct_swipe_card` is what
    makes ✕/✓/queue work on it. Asserted end to end.
  • ASSET-IDEAS UNCHANGED — the shared gate extraction (`eval_consensus_package`)
    must leave `generate_asset_ideas` byte-identical. `test_asset_ideas.py` is
    the golden; this file adds the structural assertion that both surfaces call
    the one function.

Harness follows test_calc_trade_queue.py: Flask test client, a real in-memory
session, isolated in-memory SQLite, `record_event` mocked.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.feature_flags as ff
import backend.server as server
import backend.trade_service as ts
from backend.database import metadata, set_asset_preference, trade_decisions_table
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeService

ME = "user_me"
OPP = "user_opp"
OPP2 = "user_opp2"
LEAGUE = "league_fairpk"
TOKEN = "test-token-fairpk"

# Elo → value = 1000 * exp(0.005 * (elo - 1500)).
SEED = {
    # mine — the canvas give side comes from here
    "a1": 1600.0,   # v ≈ 1648.7
    "a2": 1500.0,   # v ≈ 1000.0
    "a3": 1300.0,   # v ≈  367.9  (junk; filler_ok floor material)
    # theirs (OPP)
    "b1": 1620.0,   # v ≈ 1822.1  — a clean 1-for-1 return for a1
    "b2": 1610.0,   # v ≈ 1733.3
    "b3": 1560.0,   # v ≈ 1349.9
    "b4": 1540.0,   # v ≈ 1221.4
    "b5": 1330.0,   # v ≈  427.4  (junk)
    # theirs (OPP2) — only reachable on an unscoped sweep
    "c1": 1630.0,   # v ≈ 1915.5
    "c2": 1615.0,   # v ≈ 1777.1
}
MY_ROSTER = ["a1", "a2", "a3"]
THEIR_ROSTER = ["b1", "b2", "b3", "b4", "b5"]
THEIR2_ROSTER = ["c1", "c2"]


def _players():
    return [Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
            for pid in SEED]


@pytest.fixture()
def harness():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    players = _players()
    service = RankingService(players=players)
    service._seed = dict(SEED)
    trade_svc = TradeService(players={p.id: p for p in players})
    league = League(
        league_id=LEAGUE, name="Fair Packages League", platform="sleeper",
        members=[
            LeagueMember(user_id=ME, username="me",
                         roster=list(MY_ROSTER), elo_ratings={}),
            LeagueMember(user_id=OPP, username="opp",
                         roster=list(THEIR_ROSTER), elo_ratings={}),
            LeagueMember(user_id=OPP2, username="opp2",
                         roster=list(THEIR2_ROSTER), elo_ratings={}),
        ])
    trade_svc.add_league(league)

    sess = {
        "user_id":       ME,
        "league":        league,
        "players":       players,
        "user_roster":   list(MY_ROSTER),
        "services":      {"1qb_ppr": service},
        "service":       service,
        "trade_svcs":    {"1qb_ppr": trade_svc},
        "trade_svc":     trade_svc,
        "active_format": "1qb_ppr",
        "last_active":   0.0,
    }

    server.app.config["TESTING"] = True
    client = server.app.test_client()

    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    ff._flags_cache = {
        **ff.DEFAULT_FLAGS,
        "calc.merged_layout":     True,
        "trade.preference_lists": True,
        # D-178 (#418) — R4's one switch, TRUE in config/features.json since
        # the G6 wave. The route builds its awaiting-like exclusion set under
        # this flag exactly as the deck job does, so the harness runs in the
        # shipped posture; `test_flag_off_is_byte_identical` covers the other
        # side. With no likes in the fixture DB the set is empty, so every
        # test above this line is unaffected.
        "trade.presentment_rules": True,
    }
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "record_event", MagicMock()):
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        try:
            yield client, engine, sess, trade_svc, league
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            ff._flags_cache = old_flags
            ts._cfg.clear()
            ts._cfg.update(old_cfg)


def _post(client, **over):
    body = {"league_id": LEAGUE, "give_player_ids": ["a1"]}
    body.update(over)
    return client.post("/api/trades/fair-packages",
                       data=json.dumps(body),
                       content_type="application/json",
                       headers={"X-Session-Token": TOKEN})


# ---------------------------------------------------------------------------
# The gate and validation
# ---------------------------------------------------------------------------

def test_flag_off_is_404(harness):
    client, *_ = harness
    ff._flags_cache = {**ff._flags_cache, "calc.merged_layout": False}
    res = _post(client)
    assert res.status_code == 404
    assert res.get_json()["error"] == "feature_disabled"


def test_missing_give_side_is_400(harness):
    client, *_ = harness
    res = client.post("/api/trades/fair-packages",
                      data=json.dumps({"league_id": LEAGUE}),
                      content_type="application/json",
                      headers={"X-Session-Token": TOKEN})
    assert res.status_code == 400
    assert res.get_json()["field"] == "give_player_ids"
    assert _post(client, give_player_ids=[]).status_code == 400


def test_foreign_league_is_400(harness):
    client, *_ = harness
    res = _post(client, league_id="some_other_league")
    assert res.status_code == 400
    assert res.get_json()["error"] == "league_mismatch"


def test_unknown_anchor_asset_returns_a_named_empty(harness):
    client, *_ = harness
    body = _post(client, give_player_ids=["zzz"]).get_json()
    assert body["ideas"] == []
    assert body["reason"] == "unknown_asset"


# ---------------------------------------------------------------------------
# The contract: the give side IS the canvas
# ---------------------------------------------------------------------------

def test_every_idea_gives_exactly_the_anchor(harness):
    client, *_ = harness
    body = _post(client, give_player_ids=["a1"]).get_json()
    assert body["basis"] == "consensus"
    assert body["anchor"] == {
        "give_player_ids": ["a1"], "receive_player_ids": [],
        "opponent_user_id": None,
    }
    assert body["ideas"], "the fixture must produce at least one fair package"
    for idea in body["ideas"]:
        assert idea["give_player_ids"] == ["a1"]
        assert [p["id"] for p in idea["give"]] == ["a1"]
        assert 1 <= len(idea["receive_player_ids"]) <= 3
        assert idea["basis"] == "consensus"
        assert idea["trade_id"].startswith("fairpk_")
        # The gate set is shared with asset-ideas, so the #108 direction holds.
        assert idea["receive_value"] >= idea["give_value"]
        assert idea["difference"] == round(
            idea["receive_value"] - idea["give_value"], 1)


def test_a_multi_asset_anchor_is_carried_whole(harness):
    client, *_ = harness
    body = _post(client, give_player_ids=["a1", "a2"]).get_json()
    assert body["ideas"], body
    for idea in body["ideas"]:
        assert idea["give_player_ids"] == ["a1", "a2"]
        # …and no anchor asset is ever ALSO on the return side.
        assert not set(idea["receive_player_ids"]) & {"a1", "a2"}


def test_ideas_carry_the_shared_value_verdict(harness):
    """#216 — same favors/gap construction as evaluate, the deck and
    asset-ideas, so the four surfaces cannot drift."""
    client, *_ = harness
    for idea in _post(client).get_json()["ideas"]:
        assert idea["favors"] in ("give", "receive", "even")
        assert idea["gap"]["value"] == round(
            abs(idea["receive_value"] - idea["give_value"]), 1)


# ---------------------------------------------------------------------------
# Partner scope
# ---------------------------------------------------------------------------

def test_partner_scope_limits_the_sweep(harness):
    client, *_ = harness
    unscoped = _post(client).get_json()
    assert {i["counterparty_user_id"] for i in unscoped["ideas"]} == {OPP, OPP2}

    scoped = _post(client, opponent_user_id=OPP).get_json()
    assert scoped["anchor"]["opponent_user_id"] == OPP
    assert {i["counterparty_user_id"] for i in scoped["ideas"]} == {OPP}
    # And it is a SUBSET of the unscoped sweep, not a different search.
    unscoped_keys = {(i["counterparty_user_id"], tuple(i["receive_player_ids"]))
                     for i in unscoped["ideas"]}
    for i in scoped["ideas"]:
        assert (i["counterparty_user_id"],
                tuple(i["receive_player_ids"])) in unscoped_keys


def test_a_stranger_partner_is_a_named_empty(harness):
    client, *_ = harness
    body = _post(client, opponent_user_id="nobody").get_json()
    assert body["ideas"] == []
    assert body["reason"] == "no_partner"


# ---------------------------------------------------------------------------
# The receive side is a PREFERENCE (Q-029's second half, retired)
# ---------------------------------------------------------------------------

def test_canvas_receive_assets_sort_first_but_do_not_constrain(harness):
    client, *_ = harness
    body = _post(client, opponent_user_id=OPP,
                 receive_player_ids=["b3", "b4"]).get_json()
    ideas = body["ideas"]
    assert body["anchor"]["receive_player_ids"] == ["b3", "b4"]
    assert len(ideas) > 1

    def covers(i):
        return {"b3", "b4"}.issubset(i["receive_player_ids"])

    assert covers(ideas[0]), [i["receive_player_ids"] for i in ideas]
    # Preference, NOT constraint: ideas that cannot include the whole canvas
    # receive side are still served rather than the user getting an empty deck.
    assert any(not covers(i) for i in ideas)
    # …and every covering idea precedes every non-covering one.
    flags = [covers(i) for i in ideas]
    assert flags == sorted(flags, reverse=True)


def test_a_receive_pin_the_partner_does_not_own_costs_nothing(harness):
    """A canvas receive asset that is not on the scoped partner's roster (the
    `picks_pool_cap` class of problem the old pinned_all path turned into an
    empty deck) simply fails to sort anything first."""
    client, *_ = harness
    plain = _post(client, opponent_user_id=OPP).get_json()
    with_pin = _post(client, opponent_user_id=OPP,
                     receive_player_ids=["c1"]).get_json()
    assert with_pin["ideas"] and len(with_pin["ideas"]) == len(plain["ideas"])


# ---------------------------------------------------------------------------
# Preference lists
# ---------------------------------------------------------------------------

def test_an_untouchable_on_the_give_side_refuses_by_name(harness):
    client, *_ = harness
    set_asset_preference(user_id=ME, league_id=LEAGUE,
                         player_id="a1", list_type="untouchable")
    body = _post(client, give_player_ids=["a1", "a2"]).get_json()
    assert body["ideas"] == []
    assert body["reason"] == "give_untouchable"


def test_a_not_interested_asset_never_comes_back(harness):
    client, *_ = harness
    before = _post(client, opponent_user_id=OPP).get_json()["ideas"]
    assert any("b1" in i["receive_player_ids"] for i in before)
    set_asset_preference(user_id=ME, league_id=LEAGUE,
                         player_id="b1", list_type="not_interested")
    after = _post(client, opponent_user_id=OPP).get_json()["ideas"]
    assert after
    assert not any("b1" in i["receive_player_ids"] for i in after)


# ---------------------------------------------------------------------------
# #189 relaxed refill, and the cap
# ---------------------------------------------------------------------------

def test_relaxed_refill_only_when_the_strict_band_is_empty(harness):
    client, *_ = harness
    strict = _post(client, opponent_user_id=OPP).get_json()
    assert strict["relaxed"] is False
    assert all("relaxed" not in i for i in strict["ideas"])

    # Ask for a band nothing can clear strictly; the widened band refills and
    # every surviving idea stays LABELLED.
    relaxed = _post(client, opponent_user_id=OPP,
                    fairness_threshold=0.99).get_json()
    assert relaxed["ideas"], "the widened band should refill an empty group"
    assert relaxed["relaxed"] is True
    assert all(i.get("relaxed") is True
               and i["relaxed_reason"] == "fairness_band"
               for i in relaxed["ideas"])


def test_the_flat_list_is_capped(harness):
    client, *_ = harness
    uncapped = _post(client).get_json()["ideas"]
    assert len(uncapped) > 2
    ts._cfg["fair_packages_cap"] = 2.0
    capped = _post(client).get_json()["ideas"]
    assert len(capped) == 2
    # The cap keeps the HEAD of the same order, it does not re-rank.
    assert [i["receive_player_ids"] for i in capped] == \
           [i["receive_player_ids"] for i in uncapped[:2]]


def test_the_sweep_is_deterministic(harness):
    client, *_ = harness
    first = _post(client).get_json()
    second = _post(client).get_json()
    assert first == second


# ---------------------------------------------------------------------------
# The card id
# ---------------------------------------------------------------------------

def test_trade_ids_are_stable_and_set_semantic(harness):
    client, *_ = harness
    ideas = _post(client, opponent_user_id=OPP).get_json()["ideas"]
    again = _post(client, opponent_user_id=OPP).get_json()["ideas"]
    assert [i["trade_id"] for i in ideas] == [i["trade_id"] for i in again]
    assert len({i["trade_id"] for i in ideas}) == len(ideas)

    # Order within a side is irrelevant; the sides are not interchangeable.
    a = server._fair_package_trade_id(ME, LEAGUE, OPP, ["a1", "a2"], ["b1", "b2"])
    b = server._fair_package_trade_id(ME, LEAGUE, OPP, ["a2", "a1"], ["b2", "b1"])
    c = server._fair_package_trade_id(ME, LEAGUE, OPP, ["b1", "b2"], ["a1", "a2"])
    assert a == b and a != c
    assert a.startswith("fairpk_") and len(a) == len("fairpk_") + 16


# ---------------------------------------------------------------------------
# The card actually works in the deck: swipe-reconstruct
# ---------------------------------------------------------------------------

def test_a_fair_package_card_can_be_swiped(harness):
    """The deck's disposition paths (✕/✓/queue) all POST the card's own id plus
    the echoed card context. These ids were never minted by a generator, so
    `_reconstruct_swipe_card` (FB-46) is the whole reason a swipe on one of
    these cards is not "Unknown trade_id"."""
    client, engine, *_ = harness
    idea = _post(client, opponent_user_id=OPP).get_json()["ideas"][0]

    res = client.post(
        "/api/trades/swipe",
        data=json.dumps({
            "trade_id":           idea["trade_id"],
            "decision":           "like",
            "league_id":          LEAGUE,
            "give_player_ids":    idea["give_player_ids"],
            "receive_player_ids": idea["receive_player_ids"],
            "target_user_id":     idea["counterparty_user_id"],
            "target_username":    idea["counterparty_username"],
        }),
        content_type="application/json",
        headers={"X-Session-Token": TOKEN})
    assert res.status_code == 200, res.get_data(as_text=True)

    with engine.connect() as conn:
        rows = conn.execute(select(trade_decisions_table)).fetchall()
    assert len(rows) == 1
    row = rows[0]._mapping
    assert row["trade_id"] == idea["trade_id"]
    assert row["decision"] == "like"
    assert json.loads(row["give_player_ids"]) == idea["give_player_ids"]
    assert json.loads(row["receive_player_ids"]) == idea["receive_player_ids"]


# ---------------------------------------------------------------------------
# The shared gate extraction
# ---------------------------------------------------------------------------

def test_both_surfaces_use_the_one_gate_function():
    """`eval_consensus_package` was extracted from asset-ideas' `_eval` so the
    fair-package search could not fork the gates. A second copy of the gate
    list is exactly the drift this asserts against — and `test_asset_ideas.py`
    is the golden proving the extraction changed nothing."""
    import inspect
    ideas_src = inspect.getsource(ts.TradeService._generate_asset_ideas_impl)
    fair_src = inspect.getsource(ts.TradeService._generate_fair_packages_impl)
    for src, who in ((ideas_src, "asset-ideas"), (fair_src, "fair-packages")):
        assert "eval_consensus_package(" in src, who
        # …and neither re-states the gates locally.
        assert "package_value_v2(" not in src, who
        assert "filler_ok(" not in src, who
        assert "user_gain_ok_1for1(" not in src, who
    # QA-B F4 hardening — `price_consensus_package` is the SANCTIONED
    # gate-free entry (asset-ideas' tier-scope laterals price without the
    # gate set, by rev-3 §3 design). Fair-packages has no such carve-out:
    # every idea it returns is gated, so the pricing half appearing in its
    # impl would be a silent gate bypass, exactly the drift this test
    # exists to catch.
    assert "price_consensus_package(" not in fair_src, "fair-packages"
    assert "price_consensus_package(" in ideas_src, \
        "asset-ideas' tier-scope lateral pricing rides the shared pricing half"


# ---------------------------------------------------------------------------
# D-178 (#418) — a sent offer is a LIKE, so it stops being offered
#
# Operator ruling, verbatim: *"needs a backend follow up. This should be
# treated the same as any other 'liked' trade."* The deck has always refused
# to re-offer a package the caller has an un-retracted awaiting like on
# (G6 R4 #336, `server._load_presentment_exclusions`, NO time window). This
# route consulted nothing, so an idea the user had already sent came back on
# the very next sweep looking new.
#
# Fixture honesty: the like is written by the SHIPPED routes — `/api/trades/
# queue` (the shop's ✓ / "Send this offer") — and the retraction by
# `/api/trades/awaiting/dismiss` (#318, the only retraction surface). The
# exclusion loader reads `trade_decisions` + `league_members`, so the member
# snapshot `session_init` writes in production is written here too; without
# it `load_awaiting_trades` cannot resolve the counterparty and drops the
# like on the floor — in tests AND in prod.
# ---------------------------------------------------------------------------

def _seed_members(engine):
    """The membership snapshot session_init persists (upsert_league_members).
    load_awaiting_trades recovers the counterparty by roster ownership, so a
    like whose receive side names nobody is invisible to the exclusion set."""
    from backend.database import upsert_league_members
    upsert_league_members(LEAGUE, [
        {"user_id": ME, "username": "me", "player_ids": list(MY_ROSTER)},
        {"user_id": OPP, "username": "opp", "player_ids": list(THEIR_ROSTER)},
        {"user_id": OPP2, "username": "opp2", "player_ids": list(THEIR2_ROSTER)},
    ])


def _queue(client, idea):
    """POST the idea through the real ✓ route — the same call the shop and
    the pushed fair deck make, and the one that writes decision='like'."""
    return client.post(
        "/api/trades/queue",
        data=json.dumps({
            "league_id":          LEAGUE,
            "opponent_user_id":   idea["counterparty_user_id"],
            "give_player_ids":    idea["give_player_ids"],
            "receive_player_ids": idea["receive_player_ids"],
        }),
        content_type="application/json",
        headers={"X-Session-Token": TOKEN})


def test_a_sent_offer_is_gone_from_the_next_sweep(harness):
    """(a) The ruling itself. Send one idea; the next fetch does not contain
    it, and contains everything else it contained before.

    SABOTAGE (the `exclusion_keys` filter removed from `_emit`): the sent
    package is re-served → RED."""
    client, engine, *_ = harness
    _seed_members(engine)
    before = _post(client, opponent_user_id=OPP).get_json()["ideas"]
    assert len(before) > 1, "fixture must offer more than the one we send"
    sent = before[0]

    res = _queue(client, sent)
    assert res.status_code == 200, res.get_data(as_text=True)
    assert res.get_json()["queued"] is True

    after = _post(client, opponent_user_id=OPP).get_json()["ideas"]
    got = [i["receive_player_ids"] for i in after]
    assert sent["receive_player_ids"] not in got
    # Every OTHER idea survives, in the same order — this is one exclusion,
    # not a thinning of the sweep.
    assert got == [i["receive_player_ids"] for i in before[1:]]


def test_a_retracted_like_comes_back(harness):
    """(b) Q-G6-2 / #318, inherited not re-implemented: the exclusion reads
    `load_awaiting_trades`, which already drops retracted likes. Dismissing
    the Awaiting tile restores the idea.

    SABOTAGE (a windowed or client-side 'sent' list instead of the shared
    loader): the idea stays gone after retraction → RED."""
    client, engine, *_ = harness
    _seed_members(engine)
    before = _post(client, opponent_user_id=OPP).get_json()["ideas"]
    sent = before[0]
    assert _queue(client, sent).status_code == 200
    assert (sent["receive_player_ids"]
            not in [i["receive_player_ids"]
                    for i in _post(client, opponent_user_id=OPP).get_json()["ideas"]])

    res = client.post(
        "/api/trades/awaiting/dismiss",
        data=json.dumps({
            "league_id":  LEAGUE,
            "my_give":    sent["give_player_ids"],
            "my_receive": sent["receive_player_ids"],
            "partner_id": sent["counterparty_user_id"],
        }),
        content_type="application/json",
        headers={"X-Session-Token": TOKEN})
    assert res.status_code == 200, res.get_data(as_text=True)
    assert res.get_json()["dismissed_likes"] >= 1

    assert _post(client, opponent_user_id=OPP).get_json()["ideas"] == before


def test_the_cap_still_fills_after_an_exclusion(harness):
    """(d) The filter runs at emission, so it is INSIDE the
    `fair_packages_cap` cut: sending three offers must not hand the user a
    17-idea window where a 20-idea one was promised.

    SABOTAGE (filter applied to the returned list instead of at emission):
    the capped list comes back one short → RED."""
    client, engine, *_ = harness
    _seed_members(engine)
    uncapped = _post(client, opponent_user_id=OPP).get_json()["ideas"]
    assert len(uncapped) > 3
    ts._cfg["fair_packages_cap"] = 3.0
    capped = _post(client, opponent_user_id=OPP).get_json()["ideas"]
    assert len(capped) == 3

    assert _queue(client, capped[0]).status_code == 200
    after = _post(client, opponent_user_id=OPP).get_json()["ideas"]
    assert len(after) == 3, "the cap must REFILL, not shrink"
    assert capped[0]["receive_player_ids"] not in [
        i["receive_player_ids"] for i in after]
    # The refill is the next idea in the same order, not a re-rank.
    assert ([i["receive_player_ids"] for i in after]
            == [i["receive_player_ids"] for i in uncapped[1:4]])


def test_a_live_match_excludes_the_same_way(harness):
    """The set is the DECK's set, not a likes-only invention: a `pending`
    trade_matches row for the same asset sets suppresses the idea with no
    like row at all (`load_matches_for_exclusion`)."""
    from backend.database import trade_matches_table
    client, engine, *_ = harness
    _seed_members(engine)
    before = _post(client, opponent_user_id=OPP).get_json()["ideas"]
    target = before[0]
    with engine.begin() as conn:
        conn.execute(trade_matches_table.insert().values(
            league_id=LEAGUE, user_a_id=ME, user_b_id=OPP,
            user_a_give=json.dumps(target["give_player_ids"]),
            user_a_receive=json.dumps(target["receive_player_ids"]),
            status="pending", matched_at="2026-09-03T00:00:00Z"))
    after = _post(client, opponent_user_id=OPP).get_json()["ideas"]
    assert target["receive_player_ids"] not in [
        i["receive_player_ids"] for i in after]


def test_a_broken_exclusion_load_serves_unfiltered(harness):
    """(e) Non-fatal posture, inherited from `_load_presentment_exclusions`:
    a loader that raises logs and yields an EMPTY set, so the sweep answers
    unfiltered rather than 500-ing or returning nothing.

    SABOTAGE (the load moved outside the loader's try/except): the request
    raises → RED."""
    client, engine, *_ = harness
    _seed_members(engine)
    before = _post(client, opponent_user_id=OPP).get_json()["ideas"]
    sent = before[0]
    assert _queue(client, sent).status_code == 200

    def _boom(_user_id):
        raise RuntimeError("awaiting load exploded")

    with patch.object(server, "load_awaiting_trades", _boom):
        res = _post(client, opponent_user_id=OPP)
    assert res.status_code == 200
    assert res.get_json()["ideas"] == before


def test_flag_off_is_byte_identical(harness):
    """`trade.presentment_rules` is R4's one switch (docs/config-reference.md)
    and stays that way: off ⇒ this route builds no set and re-serves the sent
    package, exactly as it did before D-178."""
    client, engine, *_ = harness
    _seed_members(engine)
    before = _post(client, opponent_user_id=OPP).get_json()["ideas"]
    assert _queue(client, before[0]).status_code == 200
    ff._flags_cache = {**ff._flags_cache, "trade.presentment_rules": False}
    assert _post(client, opponent_user_id=OPP).get_json()["ideas"] == before


# ---------------------------------------------------------------------------
# D-178 follow-up — QA-B B-1 (full parity with the deck's like memory) and
# QA-B C-4 (say what the exclusion dropped).
# ---------------------------------------------------------------------------

def _rebuild_like_memory(trade_svc):
    """What `session_init` does at the top of every session: the `like_days`
    LIKE subset, cut from the same `load_trade_decisions` read as the dismiss
    subset, keyed by the one constructor. The fixture's service was built
    before these rows existed; D-178 imports the deck's like memory as the
    deck holds it — a session snapshot, staleness included."""
    from backend.database import load_trade_decisions
    trade_svc._liked_decision_keys.clear()
    for td in load_trade_decisions(user_id=ME, league_id=LEAGUE, since_days=7):
        if td.get("decision") != "pass":
            trade_svc._liked_decision_keys.add(
                ts.presentment_key(td["give_player_ids"],
                                   td["receive_player_ids"]))


def test_a_declined_offer_stays_suppressed_like_the_deck(harness):
    """QA-B B-1 — R4 is windowless but drops a like the moment ANY match row
    exists, and `load_matches_for_exclusion` re-adds only `pending`/
    `accepted`; a DECLINED offer therefore sat in neither set and returned to
    this sweep at once, while the deck went on suppressing it for
    `like_days`. The route now consults the deck's like subset too.

    SABOTAGE (the route drops `trade_service=` from its
    `_load_presentment_exclusions` call — the shipped-at-77a4e33b
    behaviour): the declined package is re-served → RED."""
    from backend.database import create_trade_match, record_match_disposition
    client, engine, _sess, trade_svc, _league = harness
    _seed_members(engine)
    before = _post(client, opponent_user_id=OPP).get_json()["ideas"]
    sent = before[0]
    assert _queue(client, sent).status_code == 200
    assert sent["receive_player_ids"] not in [
        i["receive_player_ids"]
        for i in _post(client, opponent_user_id=OPP).get_json()["ideas"]]

    match = create_trade_match(
        league_id=LEAGUE, user_a_id=ME, user_b_id=OPP,
        user_a_give=sent["give_player_ids"],
        user_a_receive=sent["receive_player_ids"])
    record_match_disposition(match["id"], ME, "accept")
    assert record_match_disposition(
        match["id"], OPP, "decline")["outcome"] == "declined"
    # R4 alone now holds nothing for this key — proven, not assumed.
    assert server._load_presentment_exclusions(ME, LEAGUE) == set()

    _rebuild_like_memory(trade_svc)
    try:
        after = _post(client, opponent_user_id=OPP).get_json()
        assert sent["receive_player_ids"] not in [
            i["receive_player_ids"] for i in after["ideas"]]
        assert after["excluded_count"] == 1
    finally:
        trade_svc._liked_decision_keys.clear()


def test_the_sweep_reports_what_the_exclusion_dropped(harness):
    """QA-B C-4 — additive `excluded_count`, always present, and it counts the
    packages actually DROPPED rather than the size of the exclusion set. With
    the flag off it is 0, so the rollback state tells the client nothing the
    server did not do.

    SABOTAGE (`excluded_count = len(exclusion_keys)`): the second, unrelated
    like — a package this anchor's sweep can never produce — inflates the
    count to 2 → RED."""
    client, engine, *_ = harness
    _seed_members(engine)
    before = _post(client, opponent_user_id=OPP).get_json()
    assert before["excluded_count"] == 0
    sent = before["ideas"][0]
    assert _queue(client, sent).status_code == 200
    # A like on a package this sweep cannot emit (its give side is not the
    # anchor), so it is in the exclusion set and matches nothing.
    assert _queue(client, {"counterparty_user_id": OPP,
                           "give_player_ids": ["a2"],
                           "receive_player_ids": ["b5"]}).status_code == 200

    after = _post(client, opponent_user_id=OPP).get_json()
    assert sent["receive_player_ids"] not in [
        i["receive_player_ids"] for i in after["ideas"]]
    assert after["excluded_count"] == 1, (
        "the count is what was dropped, not how big the exclusion set is")

    ff._flags_cache = {**ff._flags_cache, "trade.presentment_rules": False}
    off = _post(client, opponent_user_id=OPP).get_json()
    assert off["excluded_count"] == 0
    assert off["ideas"] == before["ideas"]
