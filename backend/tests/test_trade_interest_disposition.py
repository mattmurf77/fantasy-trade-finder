"""Feedback 419 PRD R1/R2, T1-T3: exact interest is resolved by later passes.

Real DB consumers and injector; synthetic history, fixed UTC time, no providers.
The August 14 like / August 16 amnestied and expired pass is the incident RED.
"""

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, insert, select

from backend import database as db, server
from backend.tests.test_trade_match_flow import (
    LEAGUE, ME, OPP, _mk_card, _mk_league, _mk_trade_service,
)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        value = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
        return value if tz else value.replace(tzinfo=None)


@pytest.fixture
def history(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "datetime", Clock)
    yield engine
    engine.dispose()


def decision(engine, actor=OPP, action="like", at="2026-08-14T12:00:00Z",
             give=None, receive=None, league=LEAGUE, trade="old_like", retracted=None):
    give = give if give is not None else (["r1"] if actor == OPP else ["g1"])
    receive = receive if receive is not None else (["g1"] if actor == OPP else ["r1"])
    with engine.begin() as conn:
        return conn.execute(insert(db.trade_decisions_table).values(
            user_id=actor, league_id=league, trade_id=trade,
            give_player_ids=json.dumps(give), receive_player_ids=json.dumps(receive),
            decision=action, created_at=at, retracted_at=retracted,
        )).inserted_primary_key[0]


@pytest.mark.parametrize("existing", [False, True])
def test_incident_old_like_cannot_inject_or_boost_after_amnestied_pass(history, existing):
    decision(history)
    decision(history, actor=ME, action="pass", at="2026-08-16T12:00:00Z")
    svc = _mk_trade_service(["g1", "r1"])
    # The real incident's pass is expired AND amnestied: discovery has no key.
    assert svc._past_decision_keys == set()
    organic = _mk_card(["g1"], ["r1"], composite=2)
    cards = [organic] if existing else []
    deck = server._inject_likes_you_cards(
        cards=cards, trade_service=svc, user_id=ME, league_id=LEAGUE,
        league=_mk_league(["g1"], ["r1"]), user_roster=["g1"], seed_map={},
    )
    assert deck == cards
    assert not any(card.likes_you for card in deck)
    if existing:
        assert organic.composite_score == 2


@pytest.mark.parametrize("pass_actor", [ME, OPP])
def test_later_exact_pass_resolves_badge_and_match_without_mutation(history, pass_actor):
    decision(history)
    decision(history, actor=pass_actor, action="pass", at="2026-08-16T12:00:00Z")
    with history.connect() as conn:
        before = conn.execute(select(db.trade_decisions_table)).all()
    assert db.load_recent_league_likes(LEAGUE, ME) == []
    assert db.find_mirror_like(ME, LEAGUE, OPP, ["g1"], ["r1"]) is None
    with history.connect() as conn:
        assert conn.execute(select(db.trade_decisions_table)).all() == before


def test_receiver_relike_does_not_revive_old_source_but_source_renewal_can_match(history):
    decision(history)
    decision(history, actor=ME, action="pass", at="2026-08-16T12:00:00Z")
    decision(history, actor=ME, at="2026-08-20T12:00:00Z", trade="new_receiver")
    assert db.find_mirror_like(ME, LEAGUE, OPP, ["g1"], ["r1"]) is None
    assert db.find_mirror_like(OPP, LEAGUE, ME, ["r1"], ["g1"]) is not None
    decision(history, at="2026-08-21T12:00:00Z", trade="new_source")
    assert db.find_mirror_like(ME, LEAGUE, OPP, ["g1"], ["r1"])["liked_at"] == "2026-08-21T12:00:00Z"


@pytest.mark.parametrize("pass_args", [
    {"league": "another_league"},
    {"actor": "another_actor", "give": ["g1"], "receive": ["r1"]},
    {"give": ["g1", "g2"]},
    {"give": ["r1"], "receive": ["g1"]},
])
def test_other_package_actor_league_or_orientation_does_not_resolve(history, pass_args):
    decision(history)
    decision(history, **{"actor": ME, "action": "pass", "at": "2026-08-16T12:00:00Z", **pass_args})
    assert len(db.load_recent_league_likes(LEAGUE, ME)) == 1


@pytest.mark.parametrize("like_at,pass_at,expected", [
    ("2026-08-14T12:00:00Z", "2026-08-14T12:00:00+00:00", False),
    ("2026-08-14T12:00:00+02:00", "2026-08-14T11:00:00Z", False),
    ("2026-08-14T12:00:00", "2026-08-14T11:00:00Z", True),
    ("2026-08-14T12:00:00Z", "malformed", False),
])
def test_database_consumers_normalize_time_before_precedence(history, like_at, pass_at, expected):
    decision(history, at=like_at)
    decision(history, actor=ME, action="pass", at=pass_at)
    assert bool(db.load_recent_league_likes(LEAGUE, ME)) is expected
    assert bool(db.find_mirror_like(ME, LEAGUE, OPP, ["g1"], ["r1"])) is expected


def test_awaiting_and_r4_drop_resolved_offer_but_keep_new_package(history):
    with history.begin() as conn:
        for uid, roster in ((ME, ["g1", "g2"]), (OPP, ["r1", "r2"])):
            conn.execute(insert(db.league_members_table).values(
                user_id=uid, league_id=LEAGUE, username=uid,
                roster_data=json.dumps(roster), updated_at="2026-09-05T00:00:00Z"))
    decision(history, actor=ME)
    decision(history, actor=OPP, action="pass", at="2026-08-16T12:00:00Z")
    decision(history, actor=ME, at="2026-08-17T12:00:00Z",
             give=["g2", "g1"], receive=["r1"], trade="different")
    awaiting = db.load_awaiting_trades(ME)
    assert [row["trade_id"] for row in awaiting] == ["different"]
    assert server._load_presentment_exclusions(ME, LEAGUE) == {
        (frozenset(["g1", "g2"]), frozenset(["r1"]))}


def test_source_withdrawal_cannot_fall_back_to_older_like(history):
    decision(history)
    decision(history, at="2026-08-15T12:00:00Z", trade="newer",
             retracted="2026-08-16T12:00:00Z")
    assert db.load_recent_league_likes(LEAGUE, ME) == []
    decision(history, at="2026-08-17T12:00:00Z", trade="fresh")
    assert [row["trade_id"] for row in db.load_recent_league_likes(LEAGUE, ME)] == ["fresh"]


@pytest.mark.parametrize("pick", ["generic_pick_1_Mid", f"{LEAGUE}_2027_1_7"])
def test_awaiting_mixed_player_pick_uses_known_player_anchor(history, pick):
    with history.begin() as conn:
        for uid, roster in ((ME, ["g1"]), (OPP, ["r1"])):
            conn.execute(insert(db.league_members_table).values(
                user_id=uid, league_id=LEAGUE, username=uid,
                roster_data=json.dumps(roster), updated_at="2026-09-05T00:00:00Z"))
    decision(history, actor=ME, receive=["r1", pick])
    rows = db.load_awaiting_trades(ME)
    assert [(row["partner_id"], row["my_receive"]) for row in rows] == [(OPP, ["r1", pick])]
    decision(history, actor=OPP, action="pass", at="2026-08-16T12:00:00Z",
             give=["r1", pick], receive=["g1"])
    assert db.load_awaiting_trades(ME) == []


def test_awaiting_never_invents_partner_from_unknown_or_conflicting_rosters(history):
    with history.begin() as conn:
        for uid, roster in ((ME, ["g1"]), (OPP, ["r1"]), ("third", ["r1", "r2"])):
            conn.execute(insert(db.league_members_table).values(
                user_id=uid, league_id=LEAGUE, username=uid,
                roster_data=json.dumps(roster), updated_at="2026-09-05T00:00:00Z"))
    for i, receive in enumerate((["r1"], ["r1", "r2"], ["generic_pick_1_Mid"])):
        decision(history, actor=ME, receive=receive, trade=f"ambiguous_{i}")
    assert db.load_awaiting_trades(ME) == []


def test_normalized_90_day_cutoff_includes_offset_timestamp(history):
    # Cutoff is June 7 12:00 UTC. Lexically earlier day, actually 13:00 UTC.
    decision(history, at="2026-06-07T00:00:00-13:00")
    assert len(db.load_recent_league_likes(LEAGUE, ME)) == 1
    decision(history, actor=ME, action="pass", at="2026-06-07T15:00:00+01:00")
    assert db.load_recent_league_likes(LEAGUE, ME) == []


def test_batched_5000_row_history_measurement(history):
    """Hermetic diagnostic, not a machine-dependent latency assertion."""
    from time import perf_counter
    from sqlalchemy import event
    rows = [dict(user_id=OPP, league_id=LEAGUE, trade_id=f"bulk_{i}",
                 give_player_ids=json.dumps([f"r{i}"]), receive_player_ids='["g1"]',
                 decision="like", created_at="2026-08-14T12:00:00Z")
            for i in range(5000)]
    with history.begin() as conn:
        conn.execute(insert(db.trade_decisions_table), rows)
    statements = []

    def count(_conn, _cursor, statement, *_):
        if "FROM trade_decisions" in statement:
            statements.append(statement)

    event.listen(history, "before_cursor_execute", count)
    started = perf_counter()
    try:
        result = db.load_recent_league_likes(LEAGUE, ME)
    finally:
        elapsed = (perf_counter() - started) * 1000
        event.remove(history, "before_cursor_execute", count)
    assert len(result) == 5000 and len(statements) == 1
    print(f"419 history: 5000 selected rows / 5000 likes / 1 SELECT / {elapsed:.2f} ms")
    print(statements[0].split("FROM")[0].strip())
    statements.clear()
    cards = [dict(trade_id=f"card_{i}", give=[{"id": "g1"}],
                  receive=[{"id": f"r{i}"}], target_user_id=OPP, likes_you=True)
             for i in range(20)]
    event.listen(history, "before_cursor_execute", count)
    started = perf_counter()
    try:
        projected = server._project_trade_dispositions(cards, ME, LEAGUE)
    finally:
        elapsed = (perf_counter() - started) * 1000
        event.remove(history, "before_cursor_execute", count)
    assert projected == cards and len(statements) == 1
    print(f"419 serve: 5000 selected rows / 20 cards / 1 SELECT / {elapsed:.2f} ms")


def test_multi_card_projection_is_one_history_read(history):
    from sqlalchemy import event
    for index in range(20):
        decision(history, give=[f"r{index}"], receive=[f"g{index}"], trade=str(index))
    statements = []
    def record(_conn, _cursor, statement, *_args):
        statements.append(statement)
    event.listen(history, "before_cursor_execute", record)
    try:
        assert len(db.load_recent_league_likes(LEAGUE, ME)) == 20
    finally:
        event.remove(history, "before_cursor_execute", record)
    assert len(statements) == 1
