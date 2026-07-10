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


def test_severity_reclassification(harness):
    client, token = harness
    sid = _submit(client, token).get_json()["server_id"]   # filed as 'bug'

    # Severity-only update: type flips, status untouched (still 'new').
    res = client.put(f"/api/feedback/admin/{sid}/status",
                     data=json.dumps({"severity": "idea"}),
                     content_type="application/json")
    assert res.status_code == 200
    assert res.get_json()["severity"] == "idea"
    mine = client.get("/api/feedback/mine", headers={"X-Session-Token": token})
    item = mine.get_json()["items"][0]
    assert item["severity"] == "idea"
    assert item["status"] == "new"
    assert item["status_updated_at"] is None    # status never changed

    # Combined update in one call; invalid severity → 400.
    both = client.put(f"/api/feedback/admin/{sid}/status",
                      data=json.dumps({"status": "planned", "severity": "polish"}),
                      content_type="application/json")
    assert both.status_code == 200
    bad = client.put(f"/api/feedback/admin/{sid}/status",
                     data=json.dumps({"severity": "catastrophe"}),
                     content_type="application/json")
    assert bad.status_code == 400
    empty = client.put(f"/api/feedback/admin/{sid}/status",
                       data=json.dumps({}),
                       content_type="application/json")
    assert empty.status_code == 400


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

    # Non-terminal operator statuses stay visible to the user.
    client.put(f"/api/feedback/admin/{mine_id}/status",
               data=json.dumps({"status": "planned"}),
               content_type="application/json")
    res2 = client.get("/api/feedback/mine", headers={"X-Session-Token": token})
    assert res2.get_json()["items"][0]["status"] == "planned"

    # Closed statuses (shipped/declined) disappear from the user's inbox
    # (FB privacy/cleanup, 2026-07-04).
    client.put(f"/api/feedback/admin/{mine_id}/status",
               data=json.dumps({"status": "shipped"}),
               content_type="application/json")
    res3 = client.get("/api/feedback/mine", headers={"X-Session-Token": token})
    assert res3.get_json()["items"] == []


def test_closed_hidden_from_mine_but_visible_to_admin(harness):
    client, token = harness
    a = _submit(client, token, client_id="a").get_json()["server_id"]
    b = _submit(client, token, client_id="b", text="second note").get_json()["server_id"]

    # 'fixed' is NOT closed — the "Fixed — in next update" chip is the
    # user-facing notification, so it must stay visible.
    client.put(f"/api/feedback/admin/{a}/status",
               data=json.dumps({"status": "fixed"}),
               content_type="application/json")
    # 'declined' is closed — hidden from the user.
    client.put(f"/api/feedback/admin/{b}/status",
               data=json.dumps({"status": "declined"}),
               content_type="application/json")

    mine = client.get("/api/feedback/mine", headers={"X-Session-Token": token})
    ids = [it["server_id"] for it in mine.get_json()["items"]]
    assert a in ids and b not in ids

    # The operator's admin readback is unaffected — closed rows remain.
    admin = client.get("/api/feedback/admin?since_id=0")
    admin_ids = [it["id"] for it in admin.get_json()["items"]]
    assert a in admin_ids and b in admin_ids


def test_mine_never_returns_other_users_notes(harness):
    client, token = harness
    other_token = "test-token-other-user"
    with server._sessions_lock:
        server._sessions[other_token] = {
            "user_id": OTHER, "username": "other", "last_active": 0.0,
        }
    try:
        mine_id  = _submit(client, token, client_id="mine-x").get_json()["server_id"]
        other_id = _submit(client, other_token, client_id="other-x",
                           text="someone else's note").get_json()["server_id"]

        mine = client.get("/api/feedback/mine", headers={"X-Session-Token": token})
        ids = [it["server_id"] for it in mine.get_json()["items"]]
        assert ids == [mine_id] and other_id not in ids

        theirs = client.get("/api/feedback/mine",
                            headers={"X-Session-Token": other_token})
        their_ids = [it["server_id"] for it in theirs.get_json()["items"]]
        assert their_ids == [other_id] and mine_id not in their_ids
    finally:
        with server._sessions_lock:
            server._sessions.pop(other_token, None)


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
