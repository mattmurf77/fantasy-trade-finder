"""Recommendation labels must be authorized and survive analytics admission."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, insert, select

from backend import analytics_ingest as ingest, database as db, server

_REAL_RATE_EXCEEDED = ingest._rate_exceeded


@pytest.fixture
def outcome_store(monkeypatch):
    eng = create_engine("sqlite:///:memory:")
    db.metadata.create_all(eng)
    monkeypatch.setattr(db, "engine", eng)
    monkeypatch.setattr(db, "ingest_engine", eng)
    monkeypatch.setattr(ingest, "is_enabled", lambda _: True)
    monkeypatch.setattr(ingest, "_rate_exceeded", lambda *_: False)
    monkeypatch.setattr(server, "_deck_signal_v2_enabled", lambda: True)
    monkeypatch.setattr(server, "_deck_taste_enabled", lambda: False)
    monkeypatch.setattr(server, "_sessions", {
        "verified-test": {"user_id": "owner", "verified": True},
        "unverified-test": {"user_id": "owner"},
        "other-test": {"user_id": "other", "verified": True},
    })
    with eng.begin() as conn:
        conn.execute(insert(db.deck_impressions_table).values(
            impression_id="owned-impression", user_id="owner", league_id="league",
            deck_job_id="job", card_index=0, propensity=1,
            served_at=datetime.now(timezone.utc).isoformat()))
    yield eng
    eng.dispose()


def event(**updates):
    result = dict(event_id=uuid.uuid4().hex, event_type="deck_card_viewed",
                  session_id="client-session", seq=1,
                  props={"impression_id": "owned-impression", "dwell_ms": 700})
    result.update(updates)
    return result


def submit(events, token="verified-test"):
    headers = {"X-Device-Id": "device"}
    if token:
        headers["X-Session-Token"] = token
    with server.app.test_request_context("/api/events", method="POST",
                                         json={"events": events}, headers=headers):
        return server.ingest_client_events_route().get_json()


def outcomes(eng):
    with eng.connect() as conn:
        return conn.execute(select(db.deck_outcomes_table)).all()


@pytest.mark.parametrize("case", ["anonymous", "unverified", "foreign", "orphan",
                                    "bad_envelope", "too_many", "too_large", "oversized_props",
                                    "rate_limited", "disabled", "pii", "bad_dwell"])
def test_rejected_or_untrusted_analytics_cannot_label(outcome_store, monkeypatch, case):
    events, token = [event()], "verified-test"
    if case in ("anonymous", "unverified", "foreign"):
        token = {"anonymous": None, "unverified": "unverified-test", "foreign": "other-test"}[case]
    elif case == "orphan":
        events[0]["props"]["impression_id"] = "missing-impression"
    elif case == "bad_envelope":
        events[0].pop("event_id")
    elif case == "too_many":
        events = [event() for _ in range(51)]
    elif case == "too_large":
        events[0]["props"]["trade_id"] = "x" * 132000
    elif case == "oversized_props":
        events[0]["props"]["trade_id"] = "x" * 5000
    elif case == "rate_limited":
        import time
        monkeypatch.setattr(ingest, "_rate_exceeded", _REAL_RATE_EXCEEDED)
        monkeypatch.setattr(ingest, "_rate_limit_per_hr", lambda: 1)
        monkeypatch.setattr(ingest, "_events_rate", {"owner": (int(time.time() // 3600), 1)})
    elif case == "disabled":
        monkeypatch.setattr(ingest, "is_enabled", lambda _: False)
    elif case == "pii":
        events[0]["props"]["impression_id"] = "owner@example.com"
    elif case == "bad_dwell":
        events[0]["props"]["dwell_ms"] = -1
    submit(events, token)
    assert outcomes(outcome_store) == []


def test_owned_verified_accepted_event_is_bounded_and_deduped(outcome_store):
    env = event()
    assert submit([env])["accepted"] == 1
    assert submit([env])["deduped"] == 1
    submit([event()])  # New event id cannot repeat an impression view.
    rows = outcomes(outcome_store)
    assert len(rows) == 1
    assert rows[0].action == "viewed" and rows[0].dwell_ms == 700
    for _ in range(35):
        submit([event(event_type="swipe_undone")])
    assert len(outcomes(outcome_store)) == 33


def test_storage_requires_owner_and_valid_values(outcome_store):
    for iid, owner, values in [
        ("missing", "owner", {}), ("owned-impression", "other", {}),
        ("owned-impression", "owner", {"detail_expanded": "false"}),
        ("owned-impression", "owner", {"dwell_ms": 3_600_001}),
    ]:
        assert not db.save_deck_outcome(iid, "like", acting_user_id=owner, **values)
    assert outcomes(outcome_store) == []


def test_raced_conflict_does_not_emit_a_second_undo(outcome_store, monkeypatch):
    """A competing insert can win after the pre-insert existence check."""
    monkeypatch.setattr(ingest, '_insert_events_ignore', lambda conn, rows: set())
    response = submit([event(event_type='swipe_undone')])
    assert response['accepted'] == 0
    assert response['deduped'] == 1
    assert outcomes(outcome_store) == []


def test_conflict_insert_returns_only_actually_inserted_ids(outcome_store):
    rows = [dict(event_id='synthetic-once', user_id='owner',
                 event_type='swipe_undone', occurred_at='2026-09-04')]
    with outcome_store.begin() as conn:
        assert ingest._insert_events_ignore(conn, rows) == {'synthetic-once'}
        assert ingest._insert_events_ignore(conn, rows) == set()
