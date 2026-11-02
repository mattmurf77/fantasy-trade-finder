"""POST /api/events — how `user_events.source` is resolved (G-068 repeat).

The ingest used to read `X-Source` and default to "mobile" when it was absent.
Web's page-hide flush uses `navigator.sendBeacon`, which cannot set headers, so
those batches landed `source='mobile'` (25 of 53 prod `platform='web'` rows in
90 days). Resolution is now, first match wins:

  1. `X-Source` header in {mobile, web, extension}
  2. body `source` in the same closed set
  3. body `platform` in {web, extension}  (cached old events.js beacons)
  4. an `X-Device` header → "mobile"      (only the mobile SDK sends one)
  5. MISSING_EVENT_SOURCE (NULL, analytics-lead 2026-10-31)

Every case reads the stored row back: G-068's lesson is that a test which only
checks the request shape can pass while the column holds the wrong client.
Harness mirrors test_events_api.py (in-memory SQLite patched into both
db.engine and db.ingest_engine).
"""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.analytics_ingest as ingest
import backend.database as db_module
import backend.server as server
from backend.database import metadata, user_events_table

DEVICE = "dev_source123"


def _envelope():
    return {
        "event_id": "evt-source-0001",
        "event_type": "app_opened",
        "client_ts": "2026-10-31T12:00:00Z",
        "screen": "Home",
        "props": {"launch_type": "web"},
        "session_id": "sess-source-0001",
        "seq": 1,
    }


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


def _stored(harness, body_extra=None, headers=None):
    """POST one event with no headers beyond Content-Type (+ `headers`), the
    device id in the BODY as the beacon sends it, and return the stored row."""
    client, engine = harness
    body = {"events": [_envelope()], "device_id": DEVICE}
    body.update(body_extra or {})
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    r = client.post("/api/events", headers=h, data=json.dumps(body))
    assert r.status_code == 200 and r.get_json()["accepted"] == 1, r.get_json()
    with engine.begin() as conn:
        rows = conn.execute(select(user_events_table)).fetchall()
    assert len(rows) == 1
    return rows[0]._mapping


def test_t1_beacon_shape_lands_web(harness):
    # Exactly what web/js/events.js flushOnHide sends: no X-Source, no X-Device.
    row = _stored(harness, {"platform": "web", "source": "web"})
    assert row["source"] == "web"
    assert row["platform"] == "web"


def test_t2_body_source_alone_lands_web(harness):
    # No platform, no headers: step 2 on its own.
    row = _stored(harness, {"source": "web"})
    assert row["source"] == "web"


def test_t3_cached_old_beacon_platform_only_lands_web(harness):
    # A browser still running the pre-fix events.js: platform but no source.
    row = _stored(harness, {"platform": "web"})
    assert row["source"] == "web"


def test_t4_unidentified_client_lands_missing_not_mobile(harness):
    row = _stored(harness)
    assert ingest.MISSING_EVENT_SOURCE is None
    assert row["source"] is ingest.MISSING_EVENT_SOURCE
    assert row["source"] != "mobile"


def test_t5_mobile_unchanged(harness):
    # Fielded mobile builds send X-Device and no X-Source (events.ts sendBatch).
    row = _stored(harness, headers={"X-Device": "iphone"})
    assert row["source"] == "mobile"
    assert row["platform"] == "ios"


@pytest.mark.parametrize("value", ["web", "extension"])
def test_t6_header_names_the_client(harness, value):
    row = _stored(harness, headers={"X-Source": value})
    assert row["source"] == value


def test_t7_header_beats_body(harness):
    row = _stored(harness, {"source": "web"}, headers={"X-Source": "extension"})
    assert row["source"] == "extension"


@pytest.mark.parametrize("claimed", ["cron", "api", "server"])
def test_t8_body_cannot_claim_a_server_source(harness, claimed):
    row = _stored(harness, {"source": claimed})
    assert row["source"] is None


def test_t9_header_cannot_claim_a_server_source(harness):
    row = _stored(harness, headers={"X-Source": "api"})
    assert row["source"] is None


def test_t9b_out_of_set_header_falls_through(harness):
    # A header outside the set doesn't win; the X-Device step still applies.
    row = _stored(harness, headers={"X-Source": "server", "X-Device": "iphone"})
    assert row["source"] == "mobile"
