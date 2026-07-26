"""Per-player action weighting on the Ranks leaderboard (operator rule
2026-07-26): one PLAYER placed = one action. A Quick Set tier save batching N
players (props.changed_count) or a reorder moving N players (props.moves_count)
counts N, not 1; trio swipes / anchor answers count 1 each; an empty save
(changed_count 0) counts 0; legacy rows without the prop count 1.
"""
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, insert

import backend.database as db_module
from backend.database import metadata, user_events_table, users_table

QUICKSETTER = "user_quickset_w"   # ranks via batched tier saves
SWIPER = "user_swiper_w"          # ranks via individual trio swipes


@pytest.fixture()
def weighted_db():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with eng.begin() as conn:
        for uid in (QUICKSETTER, SWIPER):
            conn.execute(insert(users_table).values(
                sleeper_user_id=uid, username=uid, created_at="2026-07-19",
            ))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(db_module, "engine", eng)
        yield eng


def _event(conn, uid, event_type, props=None, when="2026-07-26T12:00:00+00:00"):
    conn.execute(insert(user_events_table).values(
        user_id=uid, event_type=event_type, occurred_at=when,
        props=json.dumps(props) if props is not None else None,
    ))


def test_tier_save_counts_per_player_not_per_event(weighted_db):
    with weighted_db.begin() as conn:
        # One save placing 12 players vs 5 individual swipes.
        _event(conn, QUICKSETTER, "tier_save", {"changed_count": 12})
        for _ in range(5):
            _event(conn, SWIPER, "trio_swipe")
    top = db_module._rank_count_top(None, None, 10)
    assert top == [(QUICKSETTER, 12), (SWIPER, 5)]


def test_reorder_moves_count_and_zero_weight_save(weighted_db):
    with weighted_db.begin() as conn:
        _event(conn, QUICKSETTER, "ranking_reorder", {"moves_count": 3})
        _event(conn, QUICKSETTER, "tier_save", {"changed_count": 0})  # skip
        _event(conn, SWIPER, "anchor_answered")
    top = db_module._rank_count_top(None, None, 10)
    assert dict(top) == {QUICKSETTER: 3, SWIPER: 1}


def test_legacy_rows_without_prop_count_one(weighted_db):
    with weighted_db.begin() as conn:
        _event(conn, QUICKSETTER, "tier_save")            # NULL props
        _event(conn, QUICKSETTER, "tier_save", {})        # prop absent
    top = db_module._rank_count_top(None, None, 10)
    assert top == [(QUICKSETTER, 2)]


def test_self_rank_uses_same_weighting(weighted_db):
    with weighted_db.begin() as conn:
        _event(conn, QUICKSETTER, "tier_save", {"changed_count": 12})
        for _ in range(5):
            _event(conn, SWIPER, "trio_swipe")
    assert db_module._rank_count_self_rank(SWIPER, None, None) == (2, 5)
    assert db_module._rank_count_self_rank(QUICKSETTER, None, None) == (1, 12)


def test_all_zero_weight_user_absent_from_board(weighted_db):
    with weighted_db.begin() as conn:
        _event(conn, QUICKSETTER, "tier_save", {"changed_count": 0})
        _event(conn, SWIPER, "trio_swipe")
    top = db_module._rank_count_top(None, None, 10)
    assert top == [(SWIPER, 1)]
    assert db_module._rank_count_self_rank(QUICKSETTER, None, None) is None
