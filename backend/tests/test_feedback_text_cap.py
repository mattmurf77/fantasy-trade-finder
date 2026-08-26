"""The in-app feedback text cap (raised 2000 -> 8000, 2026-08-22).

Why this file exists: the 2000-char cap silently ate a long operator report
on 2026-08-22. `POST /api/feedback` 400s a note over the cap, the mobile sheet
cleared the draft without checking the result, and `retrySync()` re-attempted
forever against a permanent failure. The cap itself is legitimate — the route
accepts ANONYMOUS writes, so it is the only bound on payload size — so the fix
raises it rather than removing it, and this file pins the boundary from BOTH
sides so neither a silent lowering nor a silent removal can pass.

The client mirrors the limit as FEEDBACK_TEXT_MAX in mobile/src/api/feedback.ts;
mobile/tests/check-feedback-capture.js pins the two together across the seam.
"""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.server as server
from backend.database import metadata

ME = "user_cap"


@pytest.fixture()
def harness():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    token = "test-token-fbcap"
    server.app.config["TESTING"] = True
    client = server.app.test_client()

    with patch.object(db_module, "engine", engine):
        with server._sessions_lock:
            server._sessions[token] = {"user_id": ME, "username": "me",
                                       "last_active": 0.0}
        try:
            yield client, token
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _submit(client, token, text, client_id):
    return client.post(
        "/api/feedback",
        data=json.dumps({
            "client_id": client_id,
            "screen": "TradesHome",
            "severity": "bug",
            "text": text,
            "client_created_at": "2026-08-22T03:12:00Z",
        }),
        content_type="application/json",
        headers={"X-Session-Token": token},
    )


def test_a_note_of_exactly_the_cap_is_accepted(harness):
    """Upper bar. The boundary itself is INSIDE the allowed range."""
    client, token = harness
    res = _submit(client, token, "x" * server.FEEDBACK_TEXT_MAX, "cap-exact")
    assert res.status_code == 201, res.get_json()
    assert res.get_json()["ok"] is True


def test_one_character_past_the_cap_is_refused(harness):
    """Lower bar. Without this the cap could be removed and the suite stay green."""
    client, token = harness
    res = _submit(client, token, "x" * (server.FEEDBACK_TEXT_MAX + 1), "cap-over")
    assert res.status_code == 400
    body = res.get_json()
    assert body["error"] == "text_too_long"
    # The echoed limit must come from the constant, not a hardcoded literal —
    # a drifting error body is how a client builds the wrong counter.
    assert body["limit"] == server.FEEDBACK_TEXT_MAX


def test_the_report_the_old_cap_ate_now_lands(harness):
    """The actual regression: 2000 < len <= 8000 used to 400. It must not."""
    client, token = harness
    assert server.FEEDBACK_TEXT_MAX > 2000, (
        "the cap was lowered back to the value that lost an operator report"
    )
    long_note = "a" * 2001
    res = _submit(client, token, long_note, "cap-regression")
    assert res.status_code == 201, res.get_json()

    # And it is stored WHOLE — a cap that truncates instead of refusing would
    # also return 201, and would be the same data loss wearing a success code.
    mine = client.get("/api/feedback/mine",
                      headers={"X-Session-Token": token}).get_json()
    stored = [n for n in mine["items"] if n.get("text", "").startswith("aaa")]
    assert stored, mine
    assert len(stored[0]["text"]) == 2001
