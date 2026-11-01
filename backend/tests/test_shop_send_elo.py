"""#531 — the Elo half of a Shop send (head-product 11-01: keep the signal).

#574 swapped the Shop tile's queue button for the platform send router, and
the router now tags a Shop send's propose request `source: "shop"`. The
propose routes answer that tag with `_record_shop_send_signal`: the queue's
Elo half WITHOUT the deck card, once per package, before the platform call.

Pinned here:
  • THE RECORD — one `trade_decisions` row with `decision = "send"` and the
    queue's deterministic `calcq_` id, one in-memory signal, the
    `swipe_decisions` rows, and one `trade_proposed` (props.source "shop").
  • PARITY — a Shop send and a calculator queue of the same package move the
    board identically (in memory and on replay), so a signal-layer rule like
    #389's generic-pick strip can't apply to one and not the other.
  • NO DECK CARD — the send row never reaches the counterparty's likes-you
    injection, mutual-match lookup, Awaiting, or the like readers.
  • ONCE ONLY — a repeat send, a live calculator/Shop queue, and a live deck
    like of the same package each skip the row, the Elo and the event; a
    retracted like, or one renewed by a later pass, does not block.
  • THE D-170 BAR — another league, a stranger, the caller and an empty side
    record nothing.
  • THE ROUTES — Sleeper, MFL and ESPN record only for `source: "shop"`,
    before the platform call, whatever the platform answers; `shop` reaches
    the proposal ledger, and an unknown source is still "deck".
  • NEVER RAISES — a failed write leaves the send untouched.

Harness: test_calc_trade_queue.py's, with a numeric league id (the Sleeper
route refuses a non-numeric one before anything else).
"""

import json
from unittest.mock import patch

import pytest
from sqlalchemy import insert, select

import backend.database as db_module
import backend.feature_flags as ff
import backend.negmem as negmem
import backend.pick_values as pick_values
import backend.server as server
import backend.tests.test_calc_trade_queue as tcq
from backend.database import (
    find_mirror_like,
    league_members_table,
    load_awaiting_trades,
    load_recent_league_likes,
    save_trade_decision,
    swipe_decisions_table,
    trade_decisions_table,
)
from backend.ranking_service import _c
from backend.trade_service import TradeService

ME, OPP, STRANGER = tcq.ME, tcq.OPP, tcq.STRANGER
LEAGUE = "424242"
GIVE, RECV = tcq.GOOD_GIVE, tcq.GOOD_RECV


@pytest.fixture()
def world(monkeypatch):
    """The production session shape (caller absent from `league.members`)."""
    monkeypatch.setattr(tcq, "LEAGUE", LEAGUE)
    yield from tcq._harness_ctx(caller_in_members=False)


def _send(sess, **over):
    kw = {"league_id": LEAGUE, "their_user_id": OPP,
          "give_ids": list(GIVE), "receive_ids": list(RECV)}
    kw.update(over)
    # The routes call it inside a request (it reads `g.device_info`).
    with server.app.test_request_context():
        server._record_shop_send_signal(sess, **kw)


def _rows(engine):
    with engine.connect() as conn:
        return conn.execute(select(trade_decisions_table)
                            .order_by(trade_decisions_table.c.id)).fetchall()


def _swipes(engine):
    with engine.connect() as conn:
        return [(r.winner_player_id, r.loser_player_id, r.k_factor, r.scoring_format)
                for r in conn.execute(select(swipe_decisions_table)
                                      .order_by(swipe_decisions_table.c.id))]


def _memory(service):
    return [(s.winner_id, s.loser_id, k) for s, k in service._trade_swipes]


def _proposed(mock):
    return [c for c in mock.call_args_list if c.args[1] == "trade_proposed"]


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------

def test_a_shop_send_records_the_send_row_the_elo_and_one_event(world):
    _client, engine, sess, service, _tsvc, _league = world
    _send(sess)

    rows = _rows(engine)
    assert len(rows) == 1
    row = rows[0]
    assert row.decision == "send"
    assert row.user_id == ME and row.league_id == LEAGUE
    assert row.trade_id == server._calc_queue_trade_id(ME, LEAGUE, OPP, GIVE, RECV)
    assert json.loads(row.give_player_ids) == GIVE
    assert json.loads(row.receive_player_ids) == RECV
    assert row.impression_id is None and row.retracted_at is None

    assert len(_memory(service)) == 1
    assert len(_swipes(engine)) == 1

    events = _proposed(server.record_event)
    assert len(events) == 1
    call = events[0]
    assert call.args[0] == ME
    assert call.kwargs["league_id"] == LEAGUE
    assert call.kwargs["source"] == "shop_send"
    props = call.kwargs["props"]
    assert props["source"] == "shop"
    assert props["decision"] == "send"
    assert props["trade_id"] == row.trade_id
    assert props["give"] == GIVE and props["receive"] == RECV
    assert props["target"] == OPP


def test_a_shop_send_moves_the_board_exactly_as_the_queue_does(monkeypatch):
    """Same package, two fresh worlds: one queued from the calculator, one
    sent from the Shop. The in-memory signals and the persisted swipes match
    pair for pair and K for K, so replay reproduces both identically."""
    monkeypatch.setattr(tcq, "LEAGUE", LEAGUE)
    # A live bake-off freeze, so a path that skipped it would show.
    monkeypatch.setattr(server._bakeoff, "elo_freeze_mult", lambda m: m * 0.5)
    give, recv = ["g1", "g2"], ["r1", "r2"]

    gen = tcq._harness_ctx(caller_in_members=False)
    client, engine, _sess, service, *_ = next(gen)
    assert tcq._queue(client, give_player_ids=give,
                      receive_player_ids=recv).get_json()["queued"] is True
    queued = (_memory(service), _swipes(engine))
    gen.close()

    gen = tcq._harness_ctx(caller_in_members=False)
    _client, engine, sess, service, *_ = next(gen)
    _send(sess, give_ids=give, receive_ids=recv)
    sent = (_memory(service), _swipes(engine))
    gen.close()

    assert len(queued[0]) == 4 and len(queued[1]) == 4
    assert {round(k, 6) for *_pair, k in queued[0]} == {round(_c("trade_k_like") * 0.5, 6)}
    assert sent == queued


@pytest.mark.skipif(not hasattr(pick_values, "strip_generic_pick_pair"),
                    reason="#389's generic-pick strip is not on this base yet")
def test_a_generic_pick_takes_no_signal_from_a_shop_send(world):
    """#389: generic pick rungs never take a trade signal. The Shop send uses
    the same signal layer, so the strip applies with no code of its own."""
    _client, engine, sess, service, _tsvc, _league = world
    _send(sess, give_ids=["g1", "generic_pick_1_mid"], receive_ids=["r1"])
    assert all("generic_pick_1_mid" not in pair[:2] for pair in _memory(service))
    assert all("generic_pick_1_mid" not in pair[:2] for pair in _swipes(engine))
    assert _swipes(engine) == [("r1", "g1", _swipes(engine)[0][2], _swipes(engine)[0][3])]


# ---------------------------------------------------------------------------
# No deck card: the send row is not a like anywhere
# ---------------------------------------------------------------------------

def test_the_send_row_never_reaches_the_counterpartys_deck(world):
    _client, _engine, sess, _service, _tsvc, league = world
    _send(sess)
    assert load_recent_league_likes(LEAGUE, exclude_user_id=OPP) == []
    their_svc = TradeService(players={p.id: p for p in tcq._players()})
    cards = server._inject_likes_you_cards(
        cards=[], trade_service=their_svc, user_id=OPP, league_id=LEAGUE,
        league=league, user_roster=list(tcq.THEIR_ROSTER), seed_map=dict(tcq.SEED),
    )
    assert cards == []


def _seed_members(engine):
    """Awaiting resolves the partner by roster ownership, so without these
    rows it would return [] for a real like too."""
    with engine.begin() as conn:
        conn.execute(insert(league_members_table), [
            {"league_id": LEAGUE, "user_id": ME, "username": "me",
             "roster_data": json.dumps(tcq.MY_ROSTER)},
            {"league_id": LEAGUE, "user_id": OPP, "username": "opp",
             "roster_data": json.dumps(tcq.THEIR_ROSTER)},
        ])


def test_the_send_row_is_not_a_like_for_matches_or_awaiting(world):
    _client, engine, sess, _service, _tsvc, _league = world
    _seed_members(engine)
    _send(sess)
    # The counterparty liking the mirror package finds no like of mine.
    assert find_mirror_like(OPP, LEAGUE, ME, list(RECV), list(GIVE)) is None
    assert load_awaiting_trades(ME) == []
    # Not vacuous: a real like of another package with the same partner IS
    # awaiting and IS a mirror like, in the same world.
    save_trade_decision(ME, LEAGUE, "abcd1234", ["g2"], ["r2"], "like")
    assert [a["trade_id"] for a in load_awaiting_trades(ME)] == ["abcd1234"]
    assert find_mirror_like(OPP, LEAGUE, ME, ["r2"], ["g2"]) is not None
    assert find_mirror_like(OPP, LEAGUE, ME, list(RECV), list(GIVE)) is None


# Every reader of like/pass counts, pinned against a send row (the LLD rule:
# a reader that means like/pass filters for it). Each is non-vacuous: a real
# like in the same world counts once.
LIKE_PASS_READERS = [
    ("thompson shape counts",
     lambda: db_module.load_trade_decision_shape_counts(ME, LEAGUE),
     lambda r: sum(likes + passes for likes, passes in r.values())),
    ("global like rate",
     lambda: db_module.load_global_like_rate(30),
     lambda r: r[1]),
    ("engine telemetry",
     lambda: db_module.load_engine_telemetry(30, LEAGUE),
     lambda r: r["decisions"]["likes"] + r["decisions"]["passes"]),
    ("negmem retraction leg",
     lambda: negmem._fetch_retracted(ME, LEAGUE, "2000-01-01"),
     len),
]


@pytest.mark.parametrize("name,read,count", LIKE_PASS_READERS,
                         ids=[r[0] for r in LIKE_PASS_READERS])
def test_like_pass_readers_never_count_a_send(world, name, read, count):
    _client, _engine, sess, _service, _tsvc, _league = world
    _send(sess)
    assert count(read()) == 0
    save_trade_decision(ME, LEAGUE, "abcd1234", ["g2"], ["r2"], "like")
    assert count(read()) == 1


def test_the_send_row_is_not_a_trade_opinion_for_analytics(world):
    """The `traded` segment means "has a like or pass". A user whose only
    row is a send stays out of it, and out of `liked_trades_min`."""
    from backend.analytics_queries import _product_op
    _client, engine, sess, _service, _tsvc, _league = world
    _send(sess)
    with engine.connect() as conn:
        assert _product_op(conn, "traded", True) == set()
        assert ME not in _product_op(conn, "liked_trades_min", 1)
    save_trade_decision(ME, LEAGUE, "abcd1234", ["g2"], ["r2"], "pass")
    with engine.connect() as conn:
        assert _product_op(conn, "traded", True) == {ME}


def test_the_offline_replay_skips_send_rows(world, monkeypatch):
    import backend.scripts.replay_trade_decisions as replay
    _client, engine, sess, _service, _tsvc, _league = world
    monkeypatch.setattr(replay, "engine", engine)
    _send(sess)
    assert replay.load_decisions() == {}


def test_a_send_with_no_stamp_is_never_a_pass_barrier():
    from backend.database import TradeInterestHistory
    row = {"id": 1, "user_id": ME, "league_id": LEAGUE, "trade_id": "calcq_x",
           "give_player_ids": json.dumps(GIVE), "receive_player_ids": json.dumps(RECV),
           "decision": "send", "created_at": None, "retracted_at": None,
           "impression_id": None, "trade_concept_id": None}
    assert TradeInterestHistory([row]).passes == {}
    assert TradeInterestHistory([{**row, "decision": "pass"}]).passes != {}


# ---------------------------------------------------------------------------
# The deck doesn't re-serve a package just sent (7 days, like a like)
# ---------------------------------------------------------------------------

def test_a_sent_package_is_decided_like_a_like_for_seven_days(world):
    _client, engine, sess, _service, _tsvc, _league = world
    _send(sess)
    key = (frozenset(GIVE), frozenset(RECV))
    decided, passes = server._load_trade_disposition_keys(ME, LEAGUE)
    assert key in decided and key not in passes
    with engine.begin() as conn:
        conn.execute(trade_decisions_table.update().values(
            created_at="2026-01-01T00:00:00+00:00"))
    decided, passes = server._load_trade_disposition_keys(ME, LEAGUE)
    assert key not in decided and key not in passes


# ---------------------------------------------------------------------------
# Account deletion and export cover send rows like any other row
# ---------------------------------------------------------------------------

def test_account_export_and_deletion_cover_send_rows(world):
    from backend import accounts
    _client, engine, sess, _service, _tsvc, _league = world
    _send(sess)
    save_trade_decision(OPP, LEAGUE, "zzzz9999", list(RECV), list(GIVE), "like")
    exported = accounts.export_user_data(ME)["tables"]["trade_decisions"]
    assert [(r["user_id"], r["decision"]) for r in exported] == [(ME, "send")]
    counts = accounts.delete_user_data(ME)
    assert counts["trade_decisions_deleted"] == 1
    assert [(r.user_id, r.decision) for r in _rows(engine)] == [(OPP, "like")]


# ---------------------------------------------------------------------------
# Once only
# ---------------------------------------------------------------------------

def test_a_repeat_send_records_nothing_more(world):
    _client, engine, sess, service, _tsvc, _league = world
    _send(sess)
    _send(sess)
    _send(sess, give_ids=list(reversed(GIVE)))
    assert [r.decision for r in _rows(engine)] == ["send"]
    assert len(_memory(service)) == 1
    assert len(_swipes(engine)) == 1
    assert len(_proposed(server.record_event)) == 1


def test_a_package_already_queued_records_nothing(world):
    client, engine, sess, service, _tsvc, _league = world
    assert tcq._queue(client).get_json()["queued"] is True
    server.record_event.reset_mock()
    _send(sess)
    assert [r.decision for r in _rows(engine)] == ["like"]
    assert len(_memory(service)) == 1
    assert len(_swipes(engine)) == 1
    assert _proposed(server.record_event) == []


def test_a_package_already_liked_on_the_deck_records_nothing(world):
    """A deck like carries a random 8-hex id, so only the package matches."""
    _client, engine, sess, service, _tsvc, _league = world
    save_trade_decision(ME, LEAGUE, "abcd1234", list(GIVE), list(RECV), "like")
    _send(sess)
    assert [r.decision for r in _rows(engine)] == ["like"]
    assert _memory(service) == [] and _swipes(engine) == []
    assert _proposed(server.record_event) == []


def test_a_different_package_with_the_same_partner_still_records(world):
    _client, engine, sess, _service, _tsvc, _league = world
    save_trade_decision(ME, LEAGUE, "abcd1234", list(GIVE), list(RECV), "like")
    _send(sess, give_ids=["g2"], receive_ids=["r2"])
    assert [r.decision for r in _rows(engine)] == ["like", "send"]


def test_a_retracted_like_does_not_block_the_send(world):
    _client, engine, sess, _service, _tsvc, _league = world
    save_trade_decision(ME, LEAGUE, "abcd1234", list(GIVE), list(RECV), "like")
    with engine.begin() as conn:
        conn.execute(trade_decisions_table.update().values(
            retracted_at="2026-10-01T00:00:00+00:00"))
    _send(sess)
    assert [r.decision for r in _rows(engine)] == ["like", "send"]
    assert len(_proposed(server.record_event)) == 1


def test_a_like_renewed_by_a_later_pass_does_not_block_the_send(world):
    _client, engine, sess, _service, _tsvc, _league = world
    save_trade_decision(ME, LEAGUE, "abcd1234", list(GIVE), list(RECV), "like")
    with engine.begin() as conn:
        conn.execute(trade_decisions_table.update().values(
            created_at="2026-10-01T00:00:00+00:00"))
    save_trade_decision(ME, LEAGUE, "efgh5678", list(GIVE), list(RECV), "pass")
    _send(sess)
    assert [r.decision for r in _rows(engine)] == ["like", "pass", "send"]


def test_a_league_mates_like_of_the_same_package_does_not_block(world):
    """Only the caller's own history counts; the probe also reads the
    partner's rows (for `renewable`), so this pins the user filter."""
    _client, engine, sess, _service, _tsvc, _league = world
    save_trade_decision(OPP, LEAGUE, "zzzz9999", list(GIVE), list(RECV), "like")
    _send(sess)
    assert [r.decision for r in _rows(engine)] == ["like", "send"]


def test_a_write_the_replay_guard_skips_fires_no_event_and_persists_no_elo(world):
    """`save_trade_decision` returns False for a G-049 replay. The event and
    the persisted swipes follow the row (analytics-lead: the event fires
    exactly when the row is written); the in-memory signal stays ungated on
    the DB write, as in the queue route (D-073)."""
    _client, engine, sess, service, _tsvc, _league = world
    with patch.object(server, "save_trade_decision", return_value=False):
        _send(sess)
    assert _swipes(engine) == []
    assert _proposed(server.record_event) == []
    assert len(_memory(service)) == 1


# ---------------------------------------------------------------------------
# The D-170 bar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("over", [
    {"league_id": "999999"},
    {"their_user_id": STRANGER},
    {"their_user_id": ME},
    {"their_user_id": None},
    {"give_ids": []},
    {"receive_ids": []},
])
def test_outside_the_queue_bar_nothing_is_recorded(world, over):
    _client, engine, sess, service, _tsvc, _league = world
    _send(sess, **over)
    assert _rows(engine) == []
    assert _memory(service) == [] and _swipes(engine) == []
    assert _proposed(server.record_event) == []


def test_sending_to_yourself_records_nothing_even_when_you_are_a_member(monkeypatch):
    """The test-only session shape, where the caller IS in `league.members`:
    the lookup finds them, so the self check is what refuses."""
    monkeypatch.setattr(tcq, "LEAGUE", LEAGUE)
    gen = tcq._harness_ctx(caller_in_members=True)
    _client, engine, sess, service, *_ = next(gen)
    try:
        _send(sess, their_user_id=ME)
        assert _rows(engine) == [] and _memory(service) == []
    finally:
        gen.close()


def test_the_event_follows_the_row_even_if_the_swipe_persist_fails(world):
    """Once the send row commits, `trade_proposed` fires: a failed
    `save_trade_swipes` loses only that signal's replay, never the event."""
    _client, engine, sess, service, _tsvc, _league = world
    with patch.object(server, "save_trade_swipes", side_effect=RuntimeError("db blip")):
        _send(sess)
    assert [r.decision for r in _rows(engine)] == ["send"]
    assert len(_proposed(server.record_event)) == 1
    assert len(_memory(service)) == 1 and _swipes(engine) == []


def test_a_failed_write_never_raises(world):
    _client, _engine, sess, _service, _tsvc, _league = world
    with patch.object(server, "save_trade_decision", side_effect=RuntimeError("db down")):
        _send(sess)  # must not raise
    assert _proposed(server.record_event) == []


# ---------------------------------------------------------------------------
# The routes
# ---------------------------------------------------------------------------

ROUTES = [
    ("/api/trades/propose", "trade.send_in_sleeper", "_sleeper_propose_core"),
    ("/api/trades/propose-mfl", "trade.send_in_mfl", "_mfl_propose_core"),
    ("/api/trades/propose-espn", "espn.send", "_espn_propose_core"),
]


@pytest.fixture()
def routes(world, monkeypatch):
    monkeypatch.setattr(server, "_TEST_MODE", False)
    ff._flags_cache = {**ff._flags_cache, "trade.send_in_sleeper": True,
                       "trade.send_in_mfl": True, "espn.send": True}
    yield world


def _post(client, path, **over):
    body = {"league_id": LEAGUE, "their_user_id": OPP,
            "give_player_ids": list(GIVE), "receive_player_ids": list(RECV)}
    body.update(over)
    return client.post(path, data=json.dumps(body), content_type="application/json",
                       headers={"X-Session-Token": tcq.TOKEN})


@pytest.mark.parametrize("path,flag,core", ROUTES)
def test_a_shop_send_records_before_the_platform_call(routes, path, flag, core):
    """The core is where the platform write happens; by the time it runs,
    the send row is already there, and the ledger hears `shop`."""
    client, engine, *_ = routes
    seen = {}

    def fake_core(sess, **kw):
        seen["source"] = kw["source"]
        seen["rows"] = [r.decision for r in _rows(engine)]
        return {"status": "proposed"}, 200

    with patch.object(server, core, side_effect=fake_core):
        res = _post(client, path, source="shop")
    assert res.status_code == 200, res.get_data(as_text=True)
    assert seen == {"source": "shop", "rows": ["send"]}
    assert len(_proposed(server.record_event)) == 1


@pytest.mark.parametrize("path,flag,core", ROUTES)
def test_the_signal_stands_whatever_the_platform_answers(routes, path, flag, core):
    """Intent, not outcome: a refused or failed platform write keeps it."""
    client, engine, *_ = routes
    with patch.object(server, core, return_value=({"error": "write_failed"}, 502)):
        res = _post(client, path, source="shop")
    assert res.status_code == 502
    assert [r.decision for r in _rows(engine)] == ["send"]


@pytest.mark.parametrize("path,flag,core", ROUTES)
@pytest.mark.parametrize("source,ledger", [
    (None, "deck"), ("deck", "deck"), ("match", "match"),
    ("calculator", "calculator"), ("awaiting", "deck"), ("SHOP", "deck"),
])
def test_every_other_source_records_nothing(routes, path, flag, core, source, ledger):
    client, engine, *_ = routes
    seen = {}

    def fake_core(sess, **kw):
        seen["source"] = kw["source"]
        return {"status": "proposed"}, 200

    over = {} if source is None else {"source": source}
    with patch.object(server, core, side_effect=fake_core):
        assert _post(client, path, **over).status_code == 200
    assert seen["source"] == ledger
    assert _rows(engine) == []
    assert _proposed(server.record_event) == []


@pytest.mark.parametrize("path,flag,core", ROUTES)
def test_a_flag_off_route_records_nothing(routes, path, flag, core):
    client, engine, *_ = routes
    ff._flags_cache = {**ff._flags_cache, flag: False}
    with patch.object(server, core) as stub:
        assert _post(client, path, source="shop").status_code == 404
    stub.assert_not_called()
    assert _rows(engine) == []


@pytest.mark.parametrize("path,flag,core", ROUTES)
def test_a_failing_signal_never_blocks_the_send(routes, path, flag, core):
    client, engine, *_ = routes
    with patch.object(server, "find_prior_trade_signal", side_effect=RuntimeError("db down")), \
         patch.object(server, core, return_value=({"status": "proposed"}, 200)) as stub:
        assert _post(client, path, source="shop").status_code == 200
    stub.assert_called_once()
    assert _rows(engine) == []
