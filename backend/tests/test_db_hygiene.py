"""Tests for INIT-14b DB hygiene changes.

Sub-initiative A: check_for_match recency bound (90-day cutoff)
Sub-initiative B: community-ELO in-process cache + invalidation
Sub-initiative C: upsert_league_members bulk upsert correctness (newest-wins)

These tests use an isolated in-memory SQLite engine so they never touch the
real trade_finder.db, and they patch the module-level engine / caches in
backend.database to scope side-effects to each test.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, call
import pytest

import sqlalchemy
from sqlalchemy import create_engine, text

import backend.database as db_module
from backend.database import (
    check_for_match,
    upsert_league_members,
    load_league_members,
    upsert_member_rankings,
    load_community_elo_for_league,
    _COMMUNITY_ELO_CACHE,
    _COMMUNITY_ELO_TTL,
    metadata,
)


# ---------------------------------------------------------------------------
# Fixture: isolated in-memory SQLite engine
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_engine():
    """Fresh in-memory SQLite engine with the full schema, patched in as the
    module-level engine so all database.py functions use it."""
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


# ---------------------------------------------------------------------------
# Sub-initiative A: check_for_match — 90-day recency bound
# ---------------------------------------------------------------------------

def _insert_trade_like(conn, user_id, league_id, give_ids, recv_ids, age_days):
    """Helper: insert a 'like' row with created_at = now - age_days."""
    created = (datetime.utcnow() - timedelta(days=age_days)).isoformat()
    conn.execute(text(
        "INSERT INTO trade_decisions "
        "(user_id, league_id, give_player_ids, receive_player_ids, decision, created_at) "
        "VALUES (:uid, :lid, :give, :recv, 'like', :created)"
    ), {
        "uid":     user_id,
        "lid":     league_id,
        "give":    json.dumps(give_ids),
        "recv":    json.dumps(recv_ids),
        "created": created,
    })


def test_check_for_match_ignores_old_likes(mem_engine):
    """A like that is 95 days old must NOT produce a match (beyond 90-day cutoff)."""
    # user_b liked [A] give / [B] receive 95 days ago
    with mem_engine.begin() as conn:
        _insert_trade_like(conn, "user_b", "league1", ["A"], ["B"], age_days=95)

    # current_user wants to trade [B] for [A] — mirror of what user_b liked
    result = check_for_match(
        current_user_id    = "user_a",
        league_id          = "league1",
        target_user_id     = "user_b",
        give_player_ids    = ["B"],
        receive_player_ids = ["A"],
    )
    assert result is False, "95-day-old like must be ignored (beyond 90-day cutoff)"


def test_check_for_match_includes_recent_likes(mem_engine):
    """A like that is 89 days old MUST produce a match (within 90-day window)."""
    # user_b liked [A] give / [B] receive 89 days ago
    with mem_engine.begin() as conn:
        _insert_trade_like(conn, "user_b", "league1", ["A"], ["B"], age_days=89)

    result = check_for_match(
        current_user_id    = "user_a",
        league_id          = "league1",
        target_user_id     = "user_b",
        give_player_ids    = ["B"],
        receive_player_ids = ["A"],
    )
    assert result is True, "89-day-old like must be detected (within 90-day window)"


def test_check_for_match_boundary_both(mem_engine):
    """Both a stale (95d) and a fresh (89d) like exist — only fresh produces match."""
    with mem_engine.begin() as conn:
        # stale like with player set X / Y
        _insert_trade_like(conn, "user_b", "league1", ["X"], ["Y"], age_days=95)
        # fresh like with player set A / B
        _insert_trade_like(conn, "user_b", "league1", ["A"], ["B"], age_days=89)

    # Mirror of stale — should NOT match
    stale_match = check_for_match(
        current_user_id    = "user_a",
        league_id          = "league1",
        target_user_id     = "user_b",
        give_player_ids    = ["Y"],
        receive_player_ids = ["X"],
    )
    assert stale_match is False

    # Mirror of fresh — SHOULD match
    fresh_match = check_for_match(
        current_user_id    = "user_a",
        league_id          = "league1",
        target_user_id     = "user_b",
        give_player_ids    = ["B"],
        receive_player_ids = ["A"],
    )
    assert fresh_match is True


# ---------------------------------------------------------------------------
# Sub-initiative B: community-ELO server cache + invalidation
# ---------------------------------------------------------------------------

def test_community_elo_cache_avoids_second_db_call(mem_engine):
    """Two successive calls to load_community_elo_for_league must hit
    load_member_rankings exactly once (second call served from cache)."""
    fake_result = {"user_x": {"username": "Player X", "elo": {"p1": 1600}}}

    with patch.object(db_module, "load_member_rankings", return_value=fake_result) as mock_lmr:
        # Clear cache before test
        db_module._COMMUNITY_ELO_CACHE.clear()

        r1 = load_community_elo_for_league("lg1", "exclude_me", "1qb_ppr")
        r2 = load_community_elo_for_league("lg1", "exclude_me", "1qb_ppr")

        # load_member_rankings called exactly once — second hit is from cache
        assert mock_lmr.call_count == 1, (
            f"expected 1 DB call, got {mock_lmr.call_count}"
        )
        assert r1 == fake_result
        assert r2 == fake_result


def test_community_elo_cache_invalidated_by_upsert(mem_engine):
    """After upsert_member_rankings, load_community_elo_for_league must
    make a fresh DB call instead of returning the stale cached value."""
    fake_result_v1 = {"user_x": {"username": "Player X", "elo": {"p1": 1600}}}
    fake_result_v2 = {"user_x": {"username": "Player X", "elo": {"p1": 1700}}}

    db_module._COMMUNITY_ELO_CACHE.clear()

    with patch.object(db_module, "load_member_rankings", side_effect=[fake_result_v1, fake_result_v2]) as mock_lmr:
        # First call — cold cache
        r1 = load_community_elo_for_league("lg1", "exclude_me", "1qb_ppr")
        assert r1 == fake_result_v1
        assert mock_lmr.call_count == 1

        # Upsert invalidates the cache entry for ("lg1", "1qb_ppr")
        upsert_member_rankings("user_x", "lg1", [{"player_id": "p1", "elo": 1700}], "1qb_ppr")

        # Second call — cache was invalidated, must hit DB again
        r2 = load_community_elo_for_league("lg1", "exclude_me", "1qb_ppr")
        assert r2 == fake_result_v2
        assert mock_lmr.call_count == 2, (
            "After invalidation, expected a fresh DB call"
        )


# ---------------------------------------------------------------------------
# Sub-initiative C: upsert_league_members bulk upsert — newest-wins
# ---------------------------------------------------------------------------

def test_upsert_league_members_inserts_then_updates(mem_engine):
    """Call upsert twice: second call must update display_name (newest-wins)
    and must not raise a unique constraint violation."""
    members_v1 = [
        {"user_id": "u1", "username": "alpha", "display_name": "Alpha One", "player_ids": ["p1"]},
        {"user_id": "u2", "username": "beta",  "display_name": "Beta Two",  "player_ids": ["p2"]},
        {"user_id": "u3", "username": "gamma", "display_name": "Gamma Three","player_ids": ["p3"]},
    ]
    # Second call updates u1's display_name
    members_v2 = [
        {"user_id": "u1", "username": "alpha", "display_name": "Alpha Updated", "player_ids": ["p1", "p4"]},
    ]

    upsert_league_members("league_x", members_v1)
    upsert_league_members("league_x", members_v2)  # must not raise

    stored = load_league_members("league_x")
    by_uid = {m["user_id"]: m for m in stored}

    # u1 must have the newest display_name
    assert by_uid["u1"]["display_name"] == "Alpha Updated", (
        f"Expected 'Alpha Updated', got {by_uid['u1']['display_name']!r}"
    )
    # Other members untouched
    assert by_uid["u2"]["display_name"] == "Beta Two"
    assert by_uid["u3"]["display_name"] == "Gamma Three"
    # Total member count unchanged
    assert len(stored) == 3


def test_upsert_league_members_no_constraint_violation(mem_engine):
    """Calling upsert on the same members repeatedly must never raise."""
    members = [
        {"user_id": "x1", "username": "xone", "player_ids": ["q1"]},
        {"user_id": "x2", "username": "xtwo", "player_ids": ["q2"]},
    ]
    # Three identical calls — idempotent
    for _ in range(3):
        upsert_league_members("league_y", members)  # must not raise

    stored = load_league_members("league_y")
    assert len(stored) == 2
