"""POST /api/events accepts the marketing landing's visit count (D-287).

`web/js/landing-visit.js` sends ONE request per page load, exactly the one
below: headers X-Device-Id (a fresh `visit_<uuid>`, never stored) and
X-Source web, no X-Session-Token, no X-Device; body {platform, source,
events:[app_opened {launch_type: web}]} with no screen. These tests post that
request and read the stored row back, so a taxonomy or intake change that
drops or mangles landing visits fails here, and they pin what the row holds:
no account, no league, no device snapshot, a hashed session id.

test_events_source.py already covers app_opened {launch_type: web}, but in
events.js's beacon shape (device id in the body, a persistent `dev_` id).
Harness mirrors that file (in-memory SQLite in both engines).
"""
import json
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.analytics_ingest as ingest
import backend.database as db_module
import backend.server as server
from backend.database import metadata, user_events_table


def _landing_request():
    """The request landing-visit.js builds, field for field."""
    headers = {"Content-Type": "application/json",
               "X-Device-Id": "visit_" + str(uuid.uuid4()), "X-Source": "web"}
    body = {"platform": "web", "source": "web", "events": [{
        "event_id": str(uuid.uuid4()), "event_type": "app_opened",
        "client_ts": "2026-11-25T12:00:00.000Z", "session_id": str(uuid.uuid4()),
        "seq": 1, "props": {"launch_type": "web"}}]}
    return headers, body


@pytest.fixture()
def harness():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    with patch.object(db_module, "engine", engine), \
         patch.object(db_module, "ingest_engine", engine), \
         patch.object(ingest, "is_enabled",
                      lambda k: k == "analytics.ingest"):
        with ingest._rate_lock:
            ingest._events_rate.clear()
        try:
            yield client, engine
        finally:
            with ingest._rate_lock:
                ingest._events_rate.clear()


def _rows(engine):
    with engine.begin() as conn:
        return [r._mapping for r in conn.execute(select(user_events_table)).fetchall()]


def test_landing_visit_is_accepted_and_stored(harness):
    client, engine = harness
    headers, body = _landing_request()
    r = client.post("/api/events", headers=headers, data=json.dumps(body))
    assert r.status_code == 200
    assert r.get_json() == {"accepted": 1, "deduped": 0, "rejected": [],
                            "dropped": 0, "disposition": "ok"}
    rows = _rows(engine)
    assert len(rows) == 1
    row = rows[0]
    env = body["events"][0]
    assert row["event_type"] == "app_opened"
    assert json.loads(row["props"]) == {"launch_type": "web", "seq": 1}
    assert row["source"] == "web" and row["platform"] == "web"
    # Anonymous: a throwaway device pseudo-id, no account, league or screen.
    assert row["user_id"] == "device:" + headers["X-Device-Id"]
    assert row["device_id"] == headers["X-Device-Id"]
    assert row["league_id"] is None and row["screen"] is None
    assert row["device_type"] is None and row["os_version"] is None
    assert row["app_version"] is None
    # The session id is stored only as a one-way hash.
    assert row["session_id"] == db_module.analytics_session_id(env["session_id"])
    assert env["session_id"] not in row["session_id"]
    # No CDN country header in this request → no country.
    assert row["country"] is None


def test_two_visits_count_twice(harness):
    """Each load is its own pseudo-device: two loads → two rows, two ids."""
    client, engine = harness
    for _ in range(2):
        headers, body = _landing_request()
        r = client.post("/api/events", headers=headers, data=json.dumps(body))
        assert r.get_json()["accepted"] == 1
    rows = _rows(engine)
    assert len(rows) == 2
    assert len({row["device_id"] for row in rows}) == 2


def test_country_comes_only_from_the_cdn_header(harness):
    client, engine = harness
    headers, body = _landing_request()
    headers["CF-IPCountry"] = "us"
    client.post("/api/events", headers=headers, data=json.dumps(body))
    assert _rows(engine)[0]["country"] == "US"


def test_device_id_is_required(harness):
    """Why the page sends a throwaway id: with none, intake rejects the visit."""
    client, engine = harness
    headers, body = _landing_request()
    del headers["X-Device-Id"]
    r = client.post("/api/events", headers=headers, data=json.dumps(body))
    assert r.get_json()["rejected"] == [{"index": 0, "reason": "no_identity"}]
    assert _rows(engine) == []
