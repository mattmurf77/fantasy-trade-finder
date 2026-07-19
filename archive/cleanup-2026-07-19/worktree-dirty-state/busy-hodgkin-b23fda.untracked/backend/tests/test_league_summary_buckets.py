"""Feedback #91 — League Summary match buckets.

get_league_summary() returns two rebucketed match counters that must agree
with the Matches screen segments:

  - matches_mutual:   trade_matches rows involving the caller in this
                      league, ANY status ("Mutual matches" segment).
  - matches_awaiting: the caller's one-sided likes that have NOT matured
                      into a match ("Awaiting them" segment, via
                      load_awaiting_trades) — so the buckets are disjoint.

The legacy status-split keys (matches_pending / matches_accepted) are
deprecated but still returned for older clients.

All tests run against an isolated in-memory SQLite engine patched into
backend.database (same pattern as test_trade_match_flow.py).
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text

import backend.database as db_module
from backend.database import get_league_summary, metadata


LEAGUE = "league_91"
OTHER_LEAGUE = "league_other"
ME  = "user_me"
OPP = "user_opp"


@pytest.fixture()
def mem_engine():
    """Fresh in-memory SQLite engine with the full schema, patched in as the
    module-level engine so all database.py functions use it."""
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


def _seed_league(conn, league_id=LEAGUE):
    conn.execute(text(
        "INSERT INTO leagues (sleeper_league_id, user_id, name) "
        "VALUES (:lid, :uid, 'Test League')"
    ), {"lid": league_id, "uid": ME})
    # Two members; OPP owns q1/q2 so awaiting-trade counterparty
    # resolution (owner of a receive player) succeeds.
    for uid, roster in ((ME, ["p1", "p2"]), (OPP, ["q1", "q2"])):
        conn.execute(text(
            "INSERT INTO league_members (league_id, user_id, username, roster_data) "
            "VALUES (:lid, :uid, :uname, :roster)"
        ), {"lid": league_id, "uid": uid, "uname": uid, "roster": json.dumps(roster)})


def _insert_match(conn, status, league_id=LEAGUE, user_a=ME, user_b=OPP,
                  a_give=None, a_receive=None):
    conn.execute(text(
        "INSERT INTO trade_matches "
        "(league_id, user_a_id, user_b_id, user_a_give, user_a_receive, matched_at, status) "
        "VALUES (:lid, :ua, :ub, :give, :recv, :at, :status)"
    ), {
        "lid": league_id, "ua": user_a, "ub": user_b,
        "give": json.dumps(a_give or ["p1"]),
        "recv": json.dumps(a_receive or ["q1"]),
        "at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "status": status,
    })


def _insert_like(conn, give_ids, recv_ids, league_id=LEAGUE, user_id=ME, age_days=1):
    created = (datetime.now(timezone.utc).replace(tzinfo=None)
               - timedelta(days=age_days)).isoformat()
    conn.execute(text(
        "INSERT INTO trade_decisions "
        "(user_id, league_id, give_player_ids, receive_player_ids, decision, created_at) "
        "VALUES (:uid, :lid, :give, :recv, 'like', :created)"
    ), {
        "uid": user_id, "lid": league_id,
        "give": json.dumps(give_ids), "recv": json.dumps(recv_ids),
        "created": created,
    })


def test_mutual_counts_all_statuses(mem_engine):
    """matches_mutual counts the caller's matches regardless of status —
    unlike the deprecated pending/accepted split."""
    with mem_engine.begin() as conn:
        _seed_league(conn)
        _insert_match(conn, "pending",  a_give=["p1"], a_receive=["q1"])
        _insert_match(conn, "accepted", a_give=["p2"], a_receive=["q2"])
        _insert_match(conn, "declined", a_give=["p1"], a_receive=["q2"])

    summary = get_league_summary(league_id=LEAGUE, user_id=ME)
    assert summary["matches_mutual"] == 3
    # Deprecated keys still present, still status-split.
    assert summary["matches_pending"] == 1
    assert summary["matches_accepted"] == 1


def test_mutual_scoped_to_league_and_caller(mem_engine):
    """Other leagues' matches and matches not involving the caller are
    excluded; caller counts from either the user_a or user_b seat."""
    with mem_engine.begin() as conn:
        _seed_league(conn)
        _insert_match(conn, "pending", user_a=ME, user_b=OPP)
        _insert_match(conn, "pending", user_a=OPP, user_b=ME)
        _insert_match(conn, "pending", user_a=OPP, user_b="user_third")
        _insert_match(conn, "pending", league_id=OTHER_LEAGUE)

    summary = get_league_summary(league_id=LEAGUE, user_id=ME)
    assert summary["matches_mutual"] == 2


def test_awaiting_counts_unmatured_likes_only(mem_engine):
    """matches_awaiting counts the caller's likes in this league that have
    no trade_matches row — a like that matured into a match moves to the
    mutual bucket instead of double-counting under both."""
    with mem_engine.begin() as conn:
        _seed_league(conn)
        # One-sided like: no matching trade_matches row → awaiting.
        _insert_like(conn, give_ids=["p1"], recv_ids=["q1"])
        # Matured like: an identical match row exists → mutual, not awaiting.
        _insert_like(conn, give_ids=["p2"], recv_ids=["q2"])
        _insert_match(conn, "pending", a_give=["p2"], a_receive=["q2"])
        # Another league's like doesn't leak into this league's count.
        _insert_like(conn, give_ids=["p1"], recv_ids=["q9"], league_id=OTHER_LEAGUE)

    summary = get_league_summary(league_id=LEAGUE, user_id=ME)
    assert summary["matches_awaiting"] == 1
    assert summary["matches_mutual"] == 1


def test_empty_league_returns_zero_buckets(mem_engine):
    """A league with no members besides implicit data still returns the new
    keys (the leaguemates_total == 0 early-return path)."""
    with mem_engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO leagues (sleeper_league_id, user_id, name) "
            "VALUES (:lid, :uid, 'Lonely League')"
        ), {"lid": LEAGUE, "uid": ME})

    summary = get_league_summary(league_id=LEAGUE, user_id=ME)
    assert summary["matches_mutual"] == 0
    assert summary["matches_awaiting"] == 0
