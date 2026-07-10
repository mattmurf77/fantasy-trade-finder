"""League-summary match bucketing (feedback #91).

The League tab's two Matches tiles must mirror the Matches screen's segments
so both surfaces always agree, and every underlying trade must live in
exactly ONE bucket:

  - matches_mutual   → "Mutual matches": trade_matches rows involving the
                        user (any disposition status), minus rows the user
                        dismissed — exactly what load_matches renders.
  - matches_awaiting → "Awaiting them": the user's one-sided likes that have
                        not matured into a trade_matches row — exactly what
                        load_awaiting_trades renders, scoped to the league.

The legacy matches_pending / matches_accepted keys (status-split, dismissal-
blind) are still emitted for pre-1.4 clients but are not asserted beyond
presence.

Also pins the load_awaiting_trades regression found while fixing #91: it
ordered trade_matches by a nonexistent created_at column, so any user with
likes AND the awaiting query raised AttributeError (surfaced as a permanently
empty "Awaiting them" segment).

Runs against an isolated in-memory SQLite engine patched into
backend.database (same pattern as test_dismiss_match.py).
"""

import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
from backend.database import (
    dismiss_match,
    get_league_summary,
    league_members_table,
    load_awaiting_trades,
    load_matches,
    metadata,
    record_match_disposition,
    trade_decisions_table,
    trade_matches_table,
)

LEAGUE = "league_x"
UA = "user_a"
UB = "user_b"


@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    # Rosters — load_awaiting_trades resolves the counterparty by looking up
    # which member's roster owns the receive-side players.
    with eng.begin() as conn:
        conn.execute(league_members_table.insert(), [
            {"league_id": LEAGUE, "user_id": UA, "username": "alice",
             "roster_data": json.dumps(["p1", "p2"])},
            {"league_id": LEAGUE, "user_id": UB, "username": "bob",
             "roster_data": json.dumps(["q1", "q2"])},
        ])
    with patch.object(db_module, "engine", eng):
        yield eng


def _insert_like(eng, user_id, give, receive, trade_id="t1"):
    with eng.begin() as conn:
        conn.execute(trade_decisions_table.insert().values(
            user_id=user_id,
            league_id=LEAGUE,
            trade_id=trade_id,
            give_player_ids=json.dumps(list(give)),
            receive_player_ids=json.dumps(list(receive)),
            decision="like",
            created_at="2026-07-06T00:00:00",
        ))


def _insert_match(eng, give=("p1",), receive=("q1",)) -> int:
    """Mutual match: UA gives `give`, receives `receive`."""
    with eng.begin() as conn:
        res = conn.execute(trade_matches_table.insert().values(
            league_id=LEAGUE,
            user_a_id=UA,
            user_b_id=UB,
            user_a_give=json.dumps(list(give)),
            user_a_receive=json.dumps(list(receive)),
            matched_at="2026-07-06T00:00:00",
            status="pending",
        ))
        return int(res.inserted_primary_key[0])


def test_mutual_match_counts_only_as_mutual(mem_engine):
    """A liked-by-both trade is ONE mutual match — never also 'awaiting'."""
    # Both sides liked the mirrored trade, so both like rows AND the match
    # row exist (this is also the created_at-regression shape: likes present
    # while the awaiting query scans trade_matches).
    _insert_like(mem_engine, UA, give=["p1"], receive=["q1"])
    _insert_like(mem_engine, UB, give=["q1"], receive=["p1"])
    _insert_match(mem_engine, give=("p1",), receive=("q1",))

    for user in (UA, UB):
        summary = get_league_summary(LEAGUE, user)
        assert summary["matches_mutual"] == 1
        assert summary["matches_awaiting"] == 0

    # The buckets are exactly the two Matches-screen segments.
    assert len(load_matches(user_id=UA, league_id=LEAGUE)) == 1
    assert load_awaiting_trades(UA) == []


def test_one_sided_like_counts_only_as_awaiting(mem_engine):
    """A like the counterparty hasn't mirrored is 'awaiting them' only."""
    _insert_like(mem_engine, UA, give=["p1"], receive=["q1"])

    summary = get_league_summary(LEAGUE, UA)
    assert summary["matches_awaiting"] == 1
    assert summary["matches_mutual"] == 0

    awaiting = load_awaiting_trades(UA)
    assert len(awaiting) == 1
    assert awaiting[0]["partner_id"] == UB

    # Nothing awaits the counterparty — the like is invisible to them.
    assert get_league_summary(LEAGUE, UB)["matches_awaiting"] == 0


def test_repeat_likes_of_same_trade_count_once(mem_engine):
    """Deck regenerations re-offer the same trade under a new trade_id —
    re-liking it must not inflate the awaiting bucket."""
    _insert_like(mem_engine, UA, give=["p1"], receive=["q1"], trade_id="t1")
    _insert_like(mem_engine, UA, give=["p1"], receive=["q1"], trade_id="t2")

    assert get_league_summary(LEAGUE, UA)["matches_awaiting"] == 1
    assert len(load_awaiting_trades(UA)) == 1


def test_disposition_never_moves_match_between_buckets(mem_engine):
    """Accepting (one side, then both) keeps the match exactly one mutual
    match — the legacy pending→accepted status flip must not surface as two
    different 'trades available'."""
    mid = _insert_match(mem_engine)

    # Undecided.
    assert get_league_summary(LEAGUE, UA)["matches_mutual"] == 1

    # One side accepted (status stays 'pending').
    record_match_disposition(mid, UA, "accept")
    summary = get_league_summary(LEAGUE, UA)
    assert summary["matches_mutual"] == 1
    assert summary["matches_awaiting"] == 0

    # Both accepted (status flips to 'accepted') — still one mutual match.
    record_match_disposition(mid, UB, "accept")
    for user in (UA, UB):
        summary = get_league_summary(LEAGUE, user)
        assert summary["matches_mutual"] == 1
        assert summary["matches_awaiting"] == 0
    # Legacy keys still emitted for old clients.
    assert summary["matches_pending"] == 0
    assert summary["matches_accepted"] == 1


def test_dismissed_match_leaves_dismissers_count_only(mem_engine):
    """The tile equals the visible Matches list: a dismissed match drops out
    of the dismisser's count (as it does from their inbox) but stays in the
    counterparty's, and never resurfaces as 'awaiting'."""
    mid = _insert_match(mem_engine)
    # UA's like underlies the match — dismissing must not resurrect it.
    _insert_like(mem_engine, UA, give=["p1"], receive=["q1"])

    dismiss_match(mid, UA)

    ua = get_league_summary(LEAGUE, UA)
    assert ua["matches_mutual"] == 0
    assert ua["matches_awaiting"] == 0
    assert len(load_matches(user_id=UA, league_id=LEAGUE)) == 0

    ub = get_league_summary(LEAGUE, UB)
    assert ub["matches_mutual"] == 1
