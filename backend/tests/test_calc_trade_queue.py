"""#384 W6-A / D-152 / D-170 — POST /api/trades/queue, the calculator's ✓ cell.

D-170 (operator ruling, 2026-08-31) rewrote the contract this file pins.
The ✓ ALWAYS records the like: D-152's up-front mirror predicate
(`_calc_queue_mirror_reason` — roster actionability, the opponent's
preference lists, the D-096 fairness ladder) is deleted, and the likes-you
injector now surfaces hand-queued (`calcq_`) likes PAST the viewer's
preference lists and the whole D-096 ladder — "the fairness check was taking
the decision out of the user's hands." Engine/deck likes keep every gate.

Covers:
  • THE GATE — `calc.merged_layout` off ⇒ 404 before any session work.
  • THE HAPPY PATH — 200 `queued: true`, one `trade_decisions` row, one Elo
    signal, and the recorded like is picked up by `_inject_likes_you_cards`
    when the OPPONENT's deck generates.
  • THE D-170 CONTRACT — a package failing the old D-096 floor queues AND
    surfaces; the opponent's untouchable/not-interested lists refuse nothing;
    a `calcq_` like bypasses the injector's gates while a non-calcq like
    still respects them; the injector KEEPS roster actionability for both.
  • THE ONE SURVIVING REFUSAL — `not_league_member` (unknown opponent, or
    yourself): no counterparty identity ⇒ nothing to record a like against.
    Asserted to write NO row and move NO Elo.
  • IDEMPOTENCY — a second identical POST answers `already_queued: true` with
    no second `trade_decisions` row, no second `swipe_decisions` row and no
    second in-memory Elo signal (the G-049 harm, from a control the user can
    re-tap at will).
  • VALIDATION — missing fields and a foreign league_id are 400s.
  • ANALYTICS — `calc_trade_queued` is registered, prop-bounded, and INTENT.
  • THE PRODUCTION SHAPE (FB-409) — the same route driven through the session
    `/api/session/init` actually builds, where `league.members` EXCLUDES the
    caller. Every case above predates this and runs against a shape production
    never produces, which is how a 100% refusal rate stayed green for 8 days.

Harness follows test_swipe_reconstruct.py: Flask test client, a real
in-memory session, isolated in-memory SQLite, `record_event` mocked.
`save_trade_swipes` is deliberately REAL so the Elo rows can be counted.
TWO fixtures, one per session shape: `harness` (caller in `members`) and
`prod_harness` (caller absent — the real one). Both are kept on purpose.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.feature_flags as ff
import backend.server as server
from backend.analytics_queries import INTENT_EVENTS, NON_INTENT_EVENTS
from backend.analytics_taxonomy import ALLOWED_CLIENT_EVENTS, CLIENT_EVENT_PROPS
from backend.database import (
    metadata,
    set_asset_preference,
    swipe_decisions_table,
    trade_decisions_table,
)
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeService

ME = "user_me"
OPP = "user_opp"
STRANGER = "user_stranger"
LEAGUE = "league_calcq"
TOKEN = "test-token-calcq"

# Two assets each side, priced so the direction of the gain is unambiguous
# from the OPPONENT's point of view (which is the only side the mirror gate
# measures).
SEED = {
    "g1": 2000.0,   # mine, the good one
    "g2": 1200.0,   # mine, the cheap one
    "r1": 1400.0,   # theirs, the cheap one
    "r2": 2200.0,   # theirs, the good one
}
MY_ROSTER = ["g1", "g2"]
THEIR_ROSTER = ["r1", "r2"]

# give g1 (2000) for r1 (1400): the caller overpays, so the OPPONENT gains.
GOOD_GIVE = ["g1"]
GOOD_RECV = ["r1"]
# give g2 (1200) for r2 (2200): the caller wins big, so the OPPONENT loses —
# the package the D-096 floor refused pre-D-170. It now queues AND surfaces
# (calcq_ bypass); a non-calcq like of the same shape still does not.
GREEDY_GIVE = ["g2"]
GREEDY_RECV = ["r2"]


def _players():
    return [Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
            for pid in SEED]


def _harness_ctx(*, caller_in_members: bool):
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    players = _players()
    service = RankingService(players=players)
    service._seed = dict(SEED)
    trade_svc = TradeService(players={p.id: p for p in players})
    members = [LeagueMember(user_id=OPP, username="opp",
                            roster=list(THEIR_ROSTER), elo_ratings={})]
    if caller_in_members:
        members.insert(0, LeagueMember(user_id=ME, username="me",
                                       roster=list(MY_ROSTER), elo_ratings={}))
    league = League(
        league_id=LEAGUE, name="Calc Queue League", platform="sleeper",
        members=members)

    sess = {
        "user_id":       ME,
        "username":      "me",
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
    # Everything else off (DEFAULT_FLAGS), so owned-pick injection and the
    # bake-off harness stay out of this route's way.
    ff._flags_cache = {
        **ff.DEFAULT_FLAGS,
        "calc.merged_layout":      True,
        "trade.likes_you":         True,
        "trade.preference_lists":  True,
    }

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "record_event", MagicMock()):
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        try:
            yield client, engine, sess, service, trade_svc, league
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            ff._flags_cache = old_flags


@pytest.fixture()
def harness():
    """THE TEST-ONLY SHAPE — the caller sits INSIDE `league.members`.

    Production never builds this session (see `prod_harness`), but a session
    that *did* carry the caller must keep working, so this shape is kept and
    the whole original suite still runs against it.
    """
    yield from _harness_ctx(caller_in_members=True)


@pytest.fixture()
def prod_harness():
    """THE PRODUCTION SHAPE (FB-409) — the caller is ABSENT from
    `league.members`, and their roster arrives only as `sess["user_roster"]`.

    This is what `/api/session/init` actually builds: members come from the
    client's `opponent_rosters` (which the clients filter the caller out of)
    and the DB merge explicitly refuses to re-add the caller. Because every
    case in this file used to run against the `harness` shape only, the route
    could — and did — refuse 100% of real ✓ taps with `not_league_member` for
    eight days with a fully green suite. Anything asserting "the caller is in
    this league" belongs here, not there.
    """
    yield from _harness_ctx(caller_in_members=False)


def _queue(client, **over):
    body = {
        "league_id":          LEAGUE,
        "opponent_user_id":   OPP,
        "give_player_ids":    GOOD_GIVE,
        "receive_player_ids": GOOD_RECV,
    }
    body.update(over)
    for k in [k for k, v in body.items() if v is _OMIT]:
        body.pop(k)
    return client.post("/api/trades/queue",
                       data=json.dumps(body),
                       content_type="application/json",
                       headers={"X-Session-Token": TOKEN})


class _Omit:
    pass


_OMIT = _Omit()


def _decision_rows(engine):
    with engine.connect() as conn:
        return conn.execute(select(trade_decisions_table)).fetchall()


def _swipe_rows(engine):
    with engine.connect() as conn:
        return conn.execute(select(swipe_decisions_table)).fetchall()


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def test_flag_off_is_404_and_writes_nothing(harness):
    client, engine, *_ = harness
    ff._flags_cache = {**ff._flags_cache, "calc.merged_layout": False}
    res = _queue(client)
    assert res.status_code == 404
    assert res.get_json()["error"] == "feature_disabled"
    assert _decision_rows(engine) == []


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------

def test_queue_records_the_like(harness):
    client, engine, _sess, service, trade_svc, _league = harness
    res = _queue(client)
    assert res.status_code == 200, res.get_data(as_text=True)
    body = res.get_json()
    assert body["queued"] is True
    assert body["already_queued"] is False
    assert body["trade_id"].startswith("calcq_")

    rows = _decision_rows(engine)
    assert len(rows) == 1
    assert rows[0].decision == "like"
    assert rows[0].user_id == ME
    assert rows[0].trade_id == body["trade_id"]
    assert json.loads(rows[0].give_player_ids) == GOOD_GIVE
    assert json.loads(rows[0].receive_player_ids) == GOOD_RECV

    # The same in-memory card the swipe route would have produced.
    card = trade_svc._trade_cards[body["trade_id"]]
    assert card.decision == "like"
    assert card.target_user_id == OPP
    # …and the same Elo signal: a like scores receive over give.
    assert len(service._trade_swipes) == 1
    assert len(_swipe_rows(engine)) == 1


def test_the_queued_like_reaches_the_opponents_deck(harness):
    """The whole point of the route. `_inject_likes_you_cards` is what puts a
    league-mate's like into your deck; if the row this route writes is not
    the row that function reads, `queued: true` is a lie."""
    client, _engine, _sess, _service, _trade_svc, league = harness
    assert _queue(client).get_json()["queued"] is True

    # Now generate the OPPONENT's deck. Their service, their roster.
    their_svc = TradeService(players={p.id: p for p in _players()})
    cards = server._inject_likes_you_cards(
        cards=[], trade_service=their_svc, user_id=OPP, league_id=LEAGUE,
        league=league, user_roster=list(THEIR_ROSTER), seed_map=dict(SEED),
    )
    assert len(cards) == 1, "the queued like did not surface in their deck"
    mirrored = cards[0]
    assert mirrored.likes_you is True
    assert mirrored.target_user_id == ME
    # Mirrored: they give what I asked for, they receive what I offered.
    assert mirrored.give_player_ids == GOOD_RECV
    assert mirrored.receive_player_ids == GOOD_GIVE


# ---------------------------------------------------------------------------
# The production shape — caller NOT in `league.members` (FB-409)
#
# The caller-exclusion convention has now bitten four times (FB #41 → #291 →
# #295/#296/#305 → #409), and three of the four were hidden by a fixture that
# put the caller in `members`. D-170 deleted the mirror predicate that FB-409's
# synthesized `caller_member` fed, so the route no longer looks the caller up
# at all — but these cases stay as the regression guard: they must be RED with
# `not_league_member` on any change that reintroduces a caller lookup against
# the caller-excluded `league.members`.
# ---------------------------------------------------------------------------

def test_prod_shape_queue_succeeds(prod_harness):
    """THE FB-409 GUARD. Identical to `test_queue_records_the_like`, run
    against the session production actually builds. Before the fix this
    returned `{queued: false, reason: "not_league_member"}` — the 100% refusal
    every fielded ✓ tap got from 2026-08-22 to 2026-08-30."""
    client, engine, _sess, service, trade_svc, _league = prod_harness
    res = _queue(client)
    assert res.status_code == 200, res.get_data(as_text=True)
    body = res.get_json()
    assert body["queued"] is True, body
    assert body["already_queued"] is False

    rows = _decision_rows(engine)
    assert len(rows) == 1
    assert rows[0].user_id == ME
    assert rows[0].decision == "like"
    card = trade_svc._trade_cards[body["trade_id"]]
    assert card.target_user_id == OPP
    assert len(service._trade_swipes) == 1


def test_prod_shape_does_not_mutate_league_members(prod_harness):
    """The synthesized caller is LOCAL to the route. `league.members` is
    shared session state read by the trade engine, the mock draft, power
    rankings and the likes-you injector, all of which assume the exclusion —
    a caller left behind in it is a phantom 13th team."""
    client, _engine, _sess, _service, _trade_svc, league = prod_harness
    assert _queue(client).get_json()["queued"] is True
    assert [m.user_id for m in league.members] == [OPP]


def test_prod_shape_roster_mismatch_still_queues(prod_harness):
    """D-170 — the route no longer checks rosters at all: the like records
    even when a side is not on the roster it must come from. The injector
    keeps roster actionability at mirror time (a trade whose players left the
    rosters cannot render honestly), which is where the check now lives —
    see test_injector_keeps_roster_actionability_for_calcq_likes."""
    client, engine, *_ = prod_harness
    assert _queue(client, give_player_ids=["r2"]).get_json()["queued"] is True
    assert len(_decision_rows(engine)) == 1


def test_prod_shape_cannot_queue_a_trade_with_yourself(prod_harness):
    """Same refusal, different branch: in this shape the caller is not in
    `members`, so it is the OPPONENT lookup that misses. `not_league_member`
    either way, which is all the client switches on."""
    client, engine, _sess, service, *_ = prod_harness
    _assert_refused(_queue(client, opponent_user_id=ME), engine, service,
                    "not_league_member")


def test_prod_shape_unknown_opponent_still_refused(prod_harness):
    """The fix synthesizes the CALLER only — a genuinely foreign
    `opponent_user_id` must still be refused."""
    client, engine, _sess, service, *_ = prod_harness
    _assert_refused(_queue(client, opponent_user_id=STRANGER), engine, service,
                    "not_league_member")


def test_prod_shape_like_reaches_the_opponents_deck(prod_harness):
    """End to end in the real shape: the row this route writes is the row
    `_inject_likes_you_cards` reads. This is the surface FB-409 starved — no
    calculator-built proposal had ever reached a counterparty's deck.

    The opponent's deck is generated from the OPPONENT's session, whose own
    `league.members` excludes them and includes the caller — so it is built
    here explicitly rather than reusing the caller's league object. (Sharing
    one league across both perspectives is exactly the fixture shortcut that
    hid this bug; `test_the_queued_like_reaches_the_opponents_deck` only gets
    away with it because its fixture happens to hold both members.)"""
    client, _engine, *_ = prod_harness
    assert _queue(client).get_json()["queued"] is True

    their_league = League(
        league_id=LEAGUE, name="Calc Queue League", platform="sleeper",
        members=[LeagueMember(user_id=ME, username="me",
                              roster=list(MY_ROSTER), elo_ratings={})])
    their_svc = TradeService(players={p.id: p for p in _players()})
    cards = server._inject_likes_you_cards(
        cards=[], trade_service=their_svc, user_id=OPP, league_id=LEAGUE,
        league=their_league, user_roster=list(THEIR_ROSTER),
        seed_map=dict(SEED),
    )
    assert len(cards) == 1, "the queued like did not surface in their deck"
    assert cards[0].likes_you is True
    assert cards[0].target_user_id == ME
    assert cards[0].give_player_ids == GOOD_RECV
    assert cards[0].receive_player_ids == GOOD_GIVE


# ---------------------------------------------------------------------------
# Idempotency — the same package, twice
# ---------------------------------------------------------------------------

def test_second_identical_call_records_nothing_new(harness):
    client, engine, _sess, service, _trade_svc, _league = harness
    first = _queue(client).get_json()
    second = _queue(client).get_json()

    assert first["queued"] is True and first["already_queued"] is False
    assert second["queued"] is True and second["already_queued"] is True
    assert second["trade_id"] == first["trade_id"], (
        "the id must be derived from the package, not minted per call")

    assert len(_decision_rows(engine)) == 1, "a second decision row was written"
    assert len(_swipe_rows(engine)) == 1, "the Elo write ran twice"
    assert len(service._trade_swipes) == 1, (
        "the in-memory Elo signal doubled — this guard sits BEFORE "
        "record_trade_signal precisely because a ✓ can be re-tapped")


def test_the_id_is_the_package_not_the_call():
    """Set semantics: the canvas built in a different order is one queue, and
    a different partner (or league, or caller) is a different one."""
    base = server._calc_queue_trade_id(ME, LEAGUE, OPP, ["g1", "g2"], ["r1", "r2"])
    assert base == server._calc_queue_trade_id(
        ME, LEAGUE, OPP, ["g2", "g1"], ["r2", "r1"])
    assert base != server._calc_queue_trade_id(
        ME, LEAGUE, STRANGER, ["g1", "g2"], ["r1", "r2"])
    assert base != server._calc_queue_trade_id(
        ME, "other_league", OPP, ["g1", "g2"], ["r1", "r2"])
    assert base != server._calc_queue_trade_id(
        STRANGER, LEAGUE, OPP, ["g1", "g2"], ["r1", "r2"])
    # And the sides are not interchangeable — the reverse trade is a
    # different offer, not the same one queued twice.
    assert base != server._calc_queue_trade_id(
        ME, LEAGUE, OPP, ["r1", "r2"], ["g1", "g2"])


# ---------------------------------------------------------------------------
# The one surviving refusal — not_league_member. A refusal writes nothing.
# ---------------------------------------------------------------------------

def _assert_refused(res, engine, service, reason):
    assert res.status_code == 200, res.get_data(as_text=True)
    body = res.get_json()
    assert body["queued"] is False
    assert body["reason"] == reason, body
    assert reason in server.CALC_QUEUE_REASONS
    assert _decision_rows(engine) == [], "a refusal recorded a like"
    assert service._trade_swipes == [], "a refusal moved the board"


def test_not_league_member(harness):
    """An opponent this session cannot resolve leaves no counterparty identity
    to record the like against — the ONE refusal D-170 keeps."""
    client, engine, _sess, service, *_ = harness
    _assert_refused(_queue(client, opponent_user_id=STRANGER), engine, service,
                    "not_league_member")


def test_cannot_queue_a_trade_with_yourself(harness):
    client, engine, _sess, service, *_ = harness
    _assert_refused(_queue(client, opponent_user_id=ME), engine, service,
                    "not_league_member")


# ---------------------------------------------------------------------------
# D-170 — the removed refusals. Every one of these used to answer
# `{queued: false}` and record nothing; each now records the like.
# ---------------------------------------------------------------------------

def _assert_queued_and_recorded(res, engine):
    assert res.status_code == 200, res.get_data(as_text=True)
    body = res.get_json()
    assert body["queued"] is True, body
    assert body["trade_id"].startswith("calcq_")
    rows = _decision_rows(engine)
    assert len(rows) == 1 and rows[0].decision == "like"
    return body


def test_likes_you_flag_off_still_records(harness):
    """The mirror surface being dark no longer refuses the ✓ — the row is
    recorded and waits for the surface (pre-D-170: `likes_you_off`)."""
    client, engine, *_ = harness
    ff._flags_cache = {**ff._flags_cache, "trade.likes_you": False}
    _assert_queued_and_recorded(_queue(client), engine)


def test_demo_league_still_records(harness):
    """Pre-D-170: `likes_you_off`. The ✓ always records."""
    client, engine, sess, *_ = harness
    sess["league"].league_id = "league_demo"
    _assert_queued_and_recorded(_queue(client, league_id="league_demo"), engine)


def test_give_side_not_on_my_roster_still_queues(harness):
    """Pre-D-170: `assets_not_on_roster`. The route checks no rosters now;
    actionability lives (only) in the injector at mirror time."""
    client, engine, *_ = harness
    _assert_queued_and_recorded(_queue(client, give_player_ids=["r2"]), engine)


def test_receive_side_not_on_their_roster_still_queues(harness):
    client, engine, *_ = harness
    _assert_queued_and_recorded(_queue(client, receive_player_ids=["g2"]),
                                engine)


def test_opponent_untouchable_still_queues(harness):
    """Pre-D-170: `opponent_untouchable`. Their preference no longer takes
    the ✓ out of the caller's hands — and no longer hides the like from THEM
    either (see the injector bypass tests below)."""
    client, engine, *_ = harness
    set_asset_preference(user_id=OPP, league_id=LEAGUE, player_id="r1",
                         list_type="untouchable")
    _assert_queued_and_recorded(_queue(client), engine)


def test_opponent_not_interested_still_queues(harness):
    """Pre-D-170: `opponent_not_interested` (#163)."""
    client, engine, *_ = harness
    set_asset_preference(user_id=OPP, league_id=LEAGUE, player_id="g1",
                         list_type="not_interested")
    _assert_queued_and_recorded(_queue(client), engine)


def test_my_own_preferences_do_not_refuse_my_own_offer(harness):
    """Marking my own guy untouchable and then offering him anyway is my call
    to make. (Was already true pre-D-170.)"""
    client, _engine, *_ = harness
    set_asset_preference(user_id=ME, league_id=LEAGUE, player_id="g1",
                         list_type="untouchable")
    assert _queue(client).get_json()["queued"] is True


def test_fails_old_fairness_floor_now_queues(harness):
    """THE D-170 HEADLINE. The greedy package — I take their 2200 for my 1200,
    a clear loss on the opponent's value bar — was `fails_fairness_floor`
    under D-152/D-096. It now records like any other ✓."""
    client, engine, *_ = harness
    _assert_queued_and_recorded(
        _queue(client, give_player_ids=GREEDY_GIVE,
               receive_player_ids=GREEDY_RECV), engine)


# ---------------------------------------------------------------------------
# D-170 — the injector's calcq_ bypass. A hand-queued like SURFACES past the
# viewer's preference lists and the whole D-096 ladder; an engine/deck like
# (non-calcq trade_id) keeps every gate.
# ---------------------------------------------------------------------------

def _inject_for_opponent(league, **kwargs):
    """Generate the OPPONENT's likes-you injection over an empty deck."""
    their_svc = TradeService(players={p.id: p for p in _players()})
    return server._inject_likes_you_cards(
        cards=[], trade_service=their_svc, user_id=OPP, league_id=LEAGUE,
        league=league, user_roster=list(THEIR_ROSTER), seed_map=dict(SEED),
        **kwargs)


def _insert_engine_like(give_ids, recv_ids, trade_id="deck1234"):
    """A like row shaped exactly like a deck swipe writes it — the trade_id
    carries no `calcq_` prefix, so the injector treats it as an engine like."""
    from backend.database import save_trade_decision
    assert save_trade_decision(
        user_id=ME, league_id=LEAGUE, trade_id=trade_id,
        give_player_ids=give_ids, receive_player_ids=recv_ids,
        decision="like")


def test_calcq_like_bypasses_the_injector_fairness_gate(harness):
    """Queue the greedy package (the opponent loses 1000 on raw seed) and it
    STILL surfaces in their deck, flagged likes_you — the D-096 ladder does
    not run for calcq_ rows."""
    client, _engine, _sess, _service, _trade_svc, league = harness
    res = _queue(client, give_player_ids=GREEDY_GIVE,
                 receive_player_ids=GREEDY_RECV)
    assert res.get_json()["queued"] is True

    cards = _inject_for_opponent(league)
    assert len(cards) == 1, "the hand-queued like did not surface"
    assert cards[0].likes_you is True
    assert cards[0].target_user_id == ME
    # Mirrored: they give what I asked for, they receive what I offered.
    assert cards[0].give_player_ids == GREEDY_RECV
    assert cards[0].receive_player_ids == GREEDY_GIVE
    # The value bar still tells the truth about the package.
    assert cards[0].give_value > cards[0].receive_value


def test_engine_like_still_respects_the_injector_fairness_gate(harness):
    """The SAME greedy package as a non-calcq like row is still refused by
    the D-096 ladder — the D-170 narrowing reaches hand-built likes only."""
    _client, _engine, _sess, _service, _trade_svc, league = harness
    _insert_engine_like(GREEDY_GIVE, GREEDY_RECV)
    assert _inject_for_opponent(league) == []


def test_calcq_like_bypasses_the_viewer_untouchable_list(harness):
    """The viewer marked r1 untouchable — r1 is their give side after the
    mirror. A hand-queued like asking for r1 still surfaces; the identical
    engine like is still skipped."""
    client, _engine, _sess, _service, _trade_svc, league = harness
    assert _queue(client).get_json()["queued"] is True  # GOOD: recv r1
    cards = _inject_for_opponent(league, untouchable_ids={"r1"})
    assert len(cards) == 1 and cards[0].likes_you is True


def test_engine_like_still_respects_the_viewer_untouchable_list(harness):
    _client, _engine, _sess, _service, _trade_svc, league = harness
    _insert_engine_like(GOOD_GIVE, GOOD_RECV)
    assert _inject_for_opponent(league, untouchable_ids={"r1"}) == []


def test_calcq_like_bypasses_the_viewer_not_interested_list(harness):
    """g1 — what the viewer would RECEIVE — is on their not-interested list.
    The hand-queued like surfaces anyway; the engine like does not."""
    client, _engine, _sess, _service, _trade_svc, league = harness
    assert _queue(client).get_json()["queued"] is True  # GOOD: give g1
    cards = _inject_for_opponent(league, not_interested_ids={"g1"})
    assert len(cards) == 1 and cards[0].likes_you is True


def test_engine_like_still_respects_the_viewer_not_interested_list(harness):
    _client, _engine, _sess, _service, _trade_svc, league = harness
    _insert_engine_like(GOOD_GIVE, GOOD_RECV)
    assert _inject_for_opponent(league, not_interested_ids={"g1"}) == []


def test_injector_keeps_roster_actionability_for_calcq_likes(harness):
    """D-170 keeps the structural gates: a hand-queued like whose give side
    has left the liker's roster cannot render honestly and is NOT mirrored."""
    client, _engine, _sess, _service, _trade_svc, _league = harness
    assert _queue(client).get_json()["queued"] is True  # GOOD: ME gives g1

    drifted = League(
        league_id=LEAGUE, name="Calc Queue League", platform="sleeper",
        members=[LeagueMember(user_id=ME, username="me",
                              roster=["g2"],  # g1 traded away since the ✓
                              elo_ratings={})])
    assert _inject_for_opponent(drifted) == []


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", [
    "give_player_ids", "receive_player_ids", "opponent_user_id", "league_id",
])
def test_missing_field_is_400(harness, field):
    client, engine, *_ = harness
    res = _queue(client, **{field: _OMIT})
    assert res.status_code == 400
    assert res.get_json() == {"error": "missing_field", "field": field}
    assert _decision_rows(engine) == []


@pytest.mark.parametrize("field", ["give_player_ids", "receive_player_ids"])
def test_empty_side_is_400(harness, field):
    client, _engine, *_ = harness
    res = _queue(client, **{field: []})
    assert res.status_code == 400
    assert res.get_json()["field"] == field


def test_foreign_league_is_400(harness):
    """Another league's members, rosters and seed board are not on this
    session, so the mirror predicate is unanswerable — not refusable."""
    client, engine, *_ = harness
    res = _queue(client, league_id="league_somewhere_else")
    assert res.status_code == 400
    assert res.get_json()["error"] == "league_mismatch"
    assert _decision_rows(engine) == []


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def test_calc_trade_queued_is_registered_and_prop_bounded():
    assert "calc_trade_queued" in ALLOWED_CLIENT_EVENTS
    assert CLIENT_EVENT_PROPS["calc_trade_queued"] == frozenset({"queued", "reason"})


def test_calc_trade_queued_is_intent():
    """The tap IS the user's decision to offer the trade — the
    `sleeper_send_attempted` class, not `prompt_deferred`. Classification is
    by subtraction, so this asserts the absence."""
    assert "calc_trade_queued" not in NON_INTENT_EVENTS
    assert "calc_trade_queued" in INTENT_EVENTS


def test_the_refusal_enum_is_closed():
    """The client switches on these six strings (mobile/src/api/trades.ts
    CalcQueueReason, docs/cross-client-invariants.md). A seventh added
    server-side without the client would fall through to a generic line."""
    assert server.CALC_QUEUE_REASONS == (
        "likes_you_off",
        "not_league_member",
        "assets_not_on_roster",
        "opponent_untouchable",
        "opponent_not_interested",
        "fails_fairness_floor",
    )
