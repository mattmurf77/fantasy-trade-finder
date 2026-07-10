"""Coverage for the per-user match dismissal (archive) path.

`dismiss_match` + the `load_matches` filter back the mobile "Dismiss" CTA on
mutual matches: it must hide the match from ONE user's inbox permanently,
leave the counterparty's view intact, and apply NO ELO / decision side effect
(distinct from a decline via record_match_disposition).

Runs against an isolated in-memory SQLite engine patched into
backend.database (same pattern as test_trade_match_flow.py).
"""

import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
from backend.database import (
    dismiss_match,
    load_matches,
    record_match_disposition,
    metadata,
    trade_matches_table,
)

LEAGUE = "league_x"
UA = "user_a"
UB = "user_b"


@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


def _insert_match(eng, give=("p1",), receive=("q1",)) -> int:
    """Insert a mutual match (user_a gives `give`, receives `receive`) and
    return its id."""
    with eng.begin() as conn:
        res = conn.execute(
            trade_matches_table.insert().values(
                league_id=LEAGUE,
                user_a_id=UA,
                user_b_id=UB,
                user_a_give=json.dumps(list(give)),
                user_a_receive=json.dumps(list(receive)),
                matched_at="2026-07-06T00:00:00",
                status="pending",
            )
        )
        return int(res.inserted_primary_key[0])


def _match_ids(user_id) -> set:
    return {m["match_id"] for m in load_matches(user_id=user_id, league_id=None)}


def test_dismiss_hides_only_for_that_user(mem_engine):
    mid = _insert_match(mem_engine)
    # Baseline: both see it.
    assert mid in _match_ids(UA)
    assert mid in _match_ids(UB)

    assert dismiss_match(mid, UA) == {"status": "ok", "match_id": mid}

    # Gone for the dismisser, still there for the counterparty.
    assert mid not in _match_ids(UA)
    assert mid in _match_ids(UB)


def test_dismiss_persists_and_is_idempotent(mem_engine):
    mid = _insert_match(mem_engine)
    assert dismiss_match(mid, UB)["status"] == "ok"
    # Re-dismiss is a no-op 'ok', still hidden.
    assert dismiss_match(mid, UB)["status"] == "ok"
    assert mid not in _match_ids(UB)
    # Only the counterparty's flag was set.
    with mem_engine.connect() as conn:
        row = conn.execute(
            select(trade_matches_table).where(trade_matches_table.c.id == mid)
        ).fetchone()
    assert row.user_b_dismissed == 1
    assert not row.user_a_dismissed


def test_dismiss_leaves_decisions_untouched(mem_engine):
    """Archiving must not write a decision (no ELO signal path)."""
    mid = _insert_match(mem_engine)
    dismiss_match(mid, UA)
    with mem_engine.connect() as conn:
        row = conn.execute(
            select(trade_matches_table).where(trade_matches_table.c.id == mid)
        ).fetchone()
    assert row.user_a_decision is None
    assert row.user_b_decision is None
    # Disposition still works independently after a dismiss (the counterparty
    # can still decide; the row isn't consumed by the archive).
    res = record_match_disposition(mid, UB, "accept")
    assert res["status"] == "ok"


def test_dismiss_rejects_nonparticipant_and_missing(mem_engine):
    mid = _insert_match(mem_engine)
    assert dismiss_match(mid, "stranger")["status"] == "not_found"
    assert dismiss_match(999999, UA)["status"] == "not_found"
