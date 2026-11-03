"""POST /api/feedback for the public (#354 BL-10, decision D-2(a)).

The route takes anonymous notes, so it is exempt from @_gate_unverified_write:
an unverified session's note is stored instead of 403'd on every retry. It is
stored with user_id NULL, because an unverified session's user_id is a claim
anyone can make by naming a username (D-183). Only a verified session
attributes the note and fires `feedback_submitted`.

Validation, the 8000-character cap (test_feedback_text_cap.py) and client_id
idempotency are unchanged. In-memory SQLite, injected sessions, no network.
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select, update

import backend.database as db_module
import backend.server as server
from backend.database import metadata, app_feedback_table, sessions_table

ME = "user_fb_public"
VERIFIED = "tok-fb-verified"
UNVERIFIED = "tok-fb-unverified"
EXPIRED = "tok-fb-expired"


@pytest.fixture()
def harness():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    server.app.config["TESTING"] = True
    client = server.app.test_client()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "record_event") as record_event:
        with server._sessions_lock:
            server._sessions[VERIFIED] = {
                "verified": True, "user_id": ME, "username": "me",
                "display_name": "Me Verified", "last_active": 0.0}
            # Username-only sign-in: same user_id claim, never proven.
            server._sessions[UNVERIFIED] = {
                "user_id": ME, "username": "me", "last_active": 0.0}
        try:
            yield client, engine, record_event
        finally:
            with server._sessions_lock:
                server._sessions.pop(VERIFIED, None)
                server._sessions.pop(UNVERIFIED, None)
                server._sessions.pop(EXPIRED, None)


def _submit(client, token=None, client_id="fb-1", severity="bug", screen="Trades"):
    headers = {"X-Session-Token": token} if token else {}
    return client.post(
        "/api/feedback",
        data=json.dumps({
            "client_id": client_id,
            "screen": screen,
            "severity": severity,
            "text": "the trade card overlapped the tab bar",
            "client_created_at": "2026-10-23T12:00:00Z",
        }),
        content_type="application/json",
        headers=headers,
    )


def _rows(engine):
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(select(app_feedback_table))]


def _feedback_events(record_event):
    return [c for c in record_event.call_args_list
            if len(c.args) > 1 and c.args[1] == "feedback_submitted"]


def test_verified_session_is_attributed_and_fires_event(harness):
    client, engine, record_event = harness
    res = _submit(client, VERIFIED)
    assert res.status_code == 201, res.get_json()
    assert res.get_json()["duplicate"] is False

    [row] = _rows(engine)
    assert row["user_id"] == ME
    assert row["username"] == "Me Verified"

    [event] = _feedback_events(record_event)
    assert event.args[0] == ME
    assert event.kwargs["source"] == "api"
    assert event.kwargs["props"] == {"severity": "bug", "screen": "Trades"}


def test_unverified_session_is_stored_anonymously_without_event(harness):
    """The D-2(a) change itself: before it, this was 403 verification_required."""
    client, engine, record_event = harness
    res = _submit(client, UNVERIFIED)
    assert res.status_code == 201, res.get_json()
    assert res.get_json()["ok"] is True

    [row] = _rows(engine)
    assert row["user_id"] is None
    assert row["username"] is None
    assert _feedback_events(record_event) == []


def test_no_token_is_stored_anonymously(harness):
    client, engine, record_event = harness
    res = _submit(client, None)
    assert res.status_code == 201, res.get_json()

    [row] = _rows(engine)
    assert row["user_id"] is None
    assert _feedback_events(record_event) == []


def test_unknown_token_is_stored_anonymously(harness):
    """An evicted in-memory session looks exactly like this."""
    client, engine, record_event = harness
    res = _submit(client, "tok-nobody-has-this")
    assert res.status_code == 201, res.get_json()

    [row] = _rows(engine)
    assert row["user_id"] is None
    assert _feedback_events(record_event) == []


def test_expired_persisted_token_is_stored_anonymously(harness):
    """A durable row past the 90-day idle expiry never restores a session."""
    client, engine, record_event = harness
    db_module.persist_session(EXPIRED, user_id=ME, verified_via="apple")
    stale = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    with engine.begin() as conn:
        conn.execute(update(sessions_table).values(last_seen_at=stale))

    with patch.object(server, "is_enabled",
                      lambda k: k == "auth.persistent_sessions"):
        res = _submit(client, EXPIRED)
    assert res.status_code == 201, res.get_json()

    [row] = _rows(engine)
    assert row["user_id"] is None
    assert _feedback_events(record_event) == []
    with server._sessions_lock:
        assert EXPIRED not in server._sessions


def test_verified_session_restored_after_restart_still_attributes(harness):
    """With the gate gone, the before_request lease hook
    (`_acquire_user_data_lease` → `_get_session`) is what restores a durable
    session into memory before the route's memory lookup runs. If that ever
    stopped, every verified note after a Render restart would land anonymous."""
    client, engine, record_event = harness
    acct = "acct_fbpublic"
    db_module.persist_session(EXPIRED, user_id=acct, verified_via="apple",
                              display_name="Restored Me")

    def fake_acct(user_id, display_name, token=None):
        payload = {"user_id": user_id, "display_name": display_name,
                   "account_only": True, "last_active": 0.0}
        with server._sessions_lock:
            server._sessions[token] = payload
        return token, payload

    with patch.object(server, "is_enabled",
                      lambda k: k == "auth.persistent_sessions"), \
         patch.object(server, "_account_build_session", fake_acct):
        res = _submit(client, EXPIRED)
    assert res.status_code == 201, res.get_json()

    [row] = _rows(engine)
    assert row["user_id"] == acct
    assert row["username"] == "Restored Me"
    assert len(_feedback_events(record_event)) == 1


@pytest.mark.parametrize("token", [VERIFIED, UNVERIFIED, None])
def test_bad_severity_still_400(harness, token):
    client, engine, _ = harness
    res = _submit(client, token, severity="critical")
    assert res.status_code == 400
    assert res.get_json() == {"error": "invalid_severity"}
    assert _rows(engine) == []


@pytest.mark.parametrize("token", [VERIFIED, UNVERIFIED, None])
def test_empty_screen_still_400(harness, token):
    client, engine, _ = harness
    res = _submit(client, token, screen="   ")
    assert res.status_code == 400
    assert res.get_json() == {"error": "missing_field", "field": "screen"}
    assert _rows(engine) == []


@pytest.mark.parametrize("token", [VERIFIED, UNVERIFIED])
def test_duplicate_client_id_stays_idempotent(harness, token):
    client, engine, record_event = harness
    first = _submit(client, token, client_id="fb-dup")
    assert first.status_code == 201
    again = _submit(client, token, client_id="fb-dup")
    assert again.status_code == 200
    body = again.get_json()
    assert body["duplicate"] is True
    assert body["server_id"] == first.get_json()["server_id"]

    assert len(_rows(engine)) == 1
    # A retry never re-fires; an unverified note never fires at all.
    assert len(_feedback_events(record_event)) == (1 if token == VERIFIED else 0)
