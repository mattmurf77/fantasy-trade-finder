"""Feedback lifecycle status (operator request, 2026-06-10).

Covers:
  (a) POST /api/feedback is UNCHANGED by the new columns — submission still
      works (201), idempotent retry still returns duplicate:true (200)
  (b) PUT /api/feedback/admin/<id>/status — valid set persists; invalid
      vocabulary → 400; unknown id → 404
  (c) GET /api/feedback/mine — returns only the caller's notes, with NULL
      status reading as 'new'
  (d) admin readback includes status

No CRON_SECRET in the test env → admin routes run open (documented local-dev
behavior), so no auth header is needed here.
"""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.server as server
from backend.database import metadata, FEEDBACK_STATUSES

ME = "user_me"
OTHER = "user_other"


@pytest.fixture()
def harness():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    token = "test-token-fbstatus"
    sess = {"user_id": ME, "username": "me", "last_active": 0.0}

    server.app.config["TESTING"] = True
    client = server.app.test_client()

    with patch.object(db_module, "engine", engine):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield client, token
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _submit(client, token=None, client_id="c1", text="something broke"):
    headers = {"X-Session-Token": token} if token else {}
    return client.post(
        "/api/feedback",
        data=json.dumps({
            "client_id": client_id,
            "screen": "Trades",
            "severity": "bug",
            "text": text,
            "client_created_at": "2026-06-10T00:00:00Z",
        }),
        content_type="application/json",
        headers=headers,
    )


def test_submission_unchanged_and_idempotent(harness):
    client, token = harness
    res = _submit(client, token)
    assert res.status_code == 201
    body = res.get_json()
    assert body["ok"] is True and body["server_id"] >= 1

    dup = _submit(client, token)
    assert dup.status_code == 200
    assert dup.get_json()["duplicate"] is True


def test_status_set_validate_and_404(harness):
    client, token = harness
    sid = _submit(client, token).get_json()["server_id"]

    ok = client.put(f"/api/feedback/admin/{sid}/status",
                    data=json.dumps({"status": "fixed"}),
                    content_type="application/json")
    assert ok.status_code == 200
    assert ok.get_json()["status"] == "fixed"

    bad = client.put(f"/api/feedback/admin/{sid}/status",
                     data=json.dumps({"status": "bogus"}),
                     content_type="application/json")
    assert bad.status_code == 400
    assert set(bad.get_json()["allowed"]) == set(FEEDBACK_STATUSES)

    missing = client.put("/api/feedback/admin/99999/status",
                         data=json.dumps({"status": "fixed"}),
                         content_type="application/json")
    assert missing.status_code == 404


def test_mine_scopes_to_caller_and_defaults_new(harness):
    client, token = harness
    mine_id = _submit(client, token, client_id="mine-1").get_json()["server_id"]
    # Anonymous note (no session) — attributed to nobody, must not leak in.
    _submit(client, None, client_id="anon-1", text="anonymous note")

    res = client.get("/api/feedback/mine", headers={"X-Session-Token": token})
    assert res.status_code == 200
    items = res.get_json()["items"]
    assert [it["server_id"] for it in items] == [mine_id]
    assert items[0]["status"] == "new"          # NULL reads as 'new'

    # After the operator sets a status, the user sees it.
    client.put(f"/api/feedback/admin/{mine_id}/status",
               data=json.dumps({"status": "shipped"}),
               content_type="application/json")
    res2 = client.get("/api/feedback/mine", headers={"X-Session-Token": token})
    assert res2.get_json()["items"][0]["status"] == "shipped"


def test_admin_readback_includes_status(harness):
    client, token = harness
    sid = _submit(client, token).get_json()["server_id"]
    client.put(f"/api/feedback/admin/{sid}/status",
               data=json.dumps({"status": "planned"}),
               content_type="application/json")
    res = client.get("/api/feedback/admin?since_id=0")
    items = res.get_json()["items"]
    assert items[0]["status"] == "planned"
    assert items[0]["status_updated_at"]
