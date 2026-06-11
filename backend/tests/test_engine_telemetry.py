"""Tests for load_engine_telemetry (GET /api/admin/engine-metrics backing).

Covers: card dedupe on re-logged decks, decision labeling join, basis /
likes-you / position / shape / league rollups, match conversion, the
days window, and league scoping.

Uses the same isolated in-memory SQLite pattern as test_db_hygiene.py.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text

import backend.database as db_module
from backend.database import load_engine_telemetry, metadata


@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


def _iso(age_days: float = 0.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()


def _insert_impression(conn, user_id, league_id, give, recv, *,
                       basis="divergence", likes_you=0, position=0, age_days=0.0):
    conn.execute(text(
        "INSERT INTO trade_impressions "
        "(user_id, league_id, target_user_id, give_player_ids, receive_player_ids,"
        " basis, likes_you, position_in_deck, shown_at) "
        "VALUES (:uid, :lid, 'opp', :give, :recv, :basis, :ly, :pos, :shown)"
    ), {
        "uid": user_id, "lid": league_id,
        "give": json.dumps(give), "recv": json.dumps(recv),
        "basis": basis, "ly": likes_you, "pos": position, "shown": _iso(age_days),
    })


def _insert_decision(conn, user_id, league_id, give, recv, decision, age_days=0.0):
    conn.execute(text(
        "INSERT INTO trade_decisions "
        "(user_id, league_id, give_player_ids, receive_player_ids, decision, created_at) "
        "VALUES (:uid, :lid, :give, :recv, :dec, :created)"
    ), {
        "uid": user_id, "lid": league_id,
        "give": json.dumps(give), "recv": json.dumps(recv),
        "dec": decision, "created": _iso(age_days),
    })


def _insert_match(conn, league_id, status="pending", age_days=0.0):
    conn.execute(text(
        "INSERT INTO trade_matches "
        "(league_id, user_a_id, user_b_id, user_a_give, user_a_receive, matched_at, status) "
        "VALUES (:lid, 'a', 'b', '[\"p1\"]', '[\"p2\"]', :matched, :status)"
    ), {"lid": league_id, "matched": _iso(age_days), "status": status})


def test_dedupe_and_like_rate_by_basis(mem_engine):
    with mem_engine.begin() as conn:
        # Same card logged twice (regenerated deck) → one unique card.
        _insert_impression(conn, "u1", "L1", ["p1"], ["p2"], basis="divergence", age_days=2)
        _insert_impression(conn, "u1", "L1", ["p1"], ["p2"], basis="divergence", age_days=1)
        # A consensus card, passed on.
        _insert_impression(conn, "u1", "L1", ["p3"], ["p4"], basis="consensus")
        # An undecided divergence card.
        _insert_impression(conn, "u1", "L1", ["p5"], ["p6"], basis="divergence")
        _insert_decision(conn, "u1", "L1", ["p1"], ["p2"], "like")
        _insert_decision(conn, "u1", "L1", ["p3"], ["p4"], "pass")

    t = load_engine_telemetry(days=30)
    assert t["impressions"]["rows"] == 4
    assert t["impressions"]["unique_cards"] == 3
    assert t["by_basis"]["divergence"] == {
        "shown": 2, "liked": 1, "passed": 0, "like_rate": 1.0}
    assert t["by_basis"]["consensus"] == {
        "shown": 1, "liked": 0, "passed": 1, "like_rate": 0.0}
    assert t["decisions"]["likes"] == 1
    assert t["decisions"]["passes"] == 1
    assert t["decisions"]["without_impression"] == 0


def test_decision_join_ignores_order_and_counts_legacy(mem_engine):
    with mem_engine.begin() as conn:
        _insert_impression(conn, "u1", "L1", ["p1", "p2"], ["p3"])
        # Decision stored with the give side in a different order → still joins.
        _insert_decision(conn, "u1", "L1", ["p2", "p1"], ["p3"], "like")
        # Decision with no impression (pre-telemetry) → legacy bucket.
        _insert_decision(conn, "u1", "L1", ["p8"], ["p9"], "like")

    t = load_engine_telemetry(days=30)
    assert t["by_shape"]["2x1"]["liked"] == 1
    assert t["decisions"]["without_impression"] == 1


def test_position_likes_you_and_league_buckets(mem_engine):
    with mem_engine.begin() as conn:
        _insert_impression(conn, "u1", "L1", ["p1"], ["p2"], position=0, likes_you=1)
        _insert_impression(conn, "u1", "L1", ["p3"], ["p4"], position=5)
        _insert_impression(conn, "u2", "L2", ["p5"], ["p6"], position=11)
        _insert_decision(conn, "u1", "L1", ["p1"], ["p2"], "like")

    t = load_engine_telemetry(days=30)
    assert t["by_position"]["top3"]["shown"] == 1
    assert t["by_position"]["4-10"]["shown"] == 1
    assert t["by_position"]["11+"]["shown"] == 1
    assert t["by_likes_you"]["likes_you"]["liked"] == 1
    assert t["by_likes_you"]["organic"]["shown"] == 2
    assert t["by_league"]["L1"]["shown"] == 2
    assert t["by_league"]["L2"]["shown"] == 1


def test_matches_window_and_league_scope(mem_engine):
    with mem_engine.begin() as conn:
        _insert_impression(conn, "u1", "L1", ["p1"], ["p2"])
        _insert_impression(conn, "u9", "L2", ["p7"], ["p8"], age_days=45)  # outside window
        _insert_decision(conn, "u1", "L1", ["p1"], ["p2"], "like")
        _insert_match(conn, "L1", status="accepted")
        _insert_match(conn, "L2", status="pending", age_days=45)           # outside window

    t = load_engine_telemetry(days=30)
    assert t["impressions"]["unique_cards"] == 1
    assert t["matches"]["total"] == 1
    assert t["matches"]["by_status"] == {"accepted": 1}
    assert t["matches"]["per_like"] == 1.0

    scoped = load_engine_telemetry(days=60, league_id="L2")
    assert scoped["impressions"]["unique_cards"] == 1
    assert scoped["matches"]["by_status"] == {"pending": 1}
    assert scoped["decisions"]["likes"] == 0
