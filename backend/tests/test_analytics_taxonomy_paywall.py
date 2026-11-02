"""paywall_viewed (#393 M1, analytics-lead's grant) — taxonomy registration.

The paywall now opens from a locked action as well as Settings, so the
shipped `paywall_viewed` row gains two props, `gate` (the 402's reason) and
`kind` (find | send), registered in the same commit as the emitter
(mobile/src/screens/PaywallScreen.tsx). The ingest allowlist is default-deny
behind a 200: an unregistered prop is stripped while the response still
reports dropped == 0, so the row must be exact. Same shape as
test_analytics_taxonomy_home_hub.py.

No new event name: `paywall_viewed` stays NON_INTENT (an impression of a
surface the user didn't ask for).
"""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.analytics_ingest as ingest
import backend.database as db_module
import backend.server as server
from backend.database import metadata, user_events_table


_PROPS = {"source": "gate", "platform": "ios", "gate": "preview_used", "kind": "send"}


def test_paywall_viewed_row_is_exact():
    """EQUAL, not <=: an extra key is unspecced, a missing one is stripped."""
    import backend.analytics_taxonomy as tax
    assert tax.CLIENT_EVENT_PROPS["paywall_viewed"] == frozenset(_PROPS)


def test_paywall_viewed_is_allowlisted_and_non_intent():
    import backend.analytics_queries as q
    import backend.analytics_taxonomy as tax
    assert "paywall_viewed" in tax.ALLOWED_CLIENT_EVENTS
    assert "paywall_viewed" not in tax._SERVER_AUTHORITATIVE
    assert "paywall_viewed" in q.NON_INTENT_EVENTS
    assert "paywall_viewed" not in q.INTENT_EVENTS


def test_the_rest_of_the_paywall_funnel_is_unchanged():
    """M1 widens one row; the other four keep their shipped shapes."""
    import backend.analytics_taxonomy as tax
    assert tax.CLIENT_EVENT_PROPS["paywall_purchase_initiated"] == frozenset(
        {"product_id", "source"})
    assert tax.CLIENT_EVENT_PROPS["paywall_purchase_completed"] == frozenset(
        {"product_id", "source"})
    assert tax.CLIENT_EVENT_PROPS["paywall_purchase_failed"] == frozenset(
        {"product_id", "user_cancelled"})
    assert tax.CLIENT_EVENT_PROPS["paywall_restore"] == frozenset({"restored"})


# ---------------------------------------------------------------------------
# Ingest — the props actually survive POST /api/events.
# Harness mirrors test_analytics_taxonomy_home_hub.py.
# ---------------------------------------------------------------------------

USER = "taxonomy_paywall_test"
TOKEN = "tax-paywall-token"
DEVICE = "dev_paywall01"


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
        with server._sessions_lock:
            server._sessions[TOKEN] = {"user_id": USER, "last_active": 0.0}
        with ingest._rate_lock:
            ingest._events_rate.clear()
        try:
            yield client, engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            with ingest._rate_lock:
                ingest._events_rate.clear()


def test_paywall_viewed_lands_with_gate_and_kind(harness):
    client, engine = harness
    body = client.post(
        "/api/events",
        headers={"Content-Type": "application/json", "X-Device-Id": DEVICE},
        data=json.dumps({"events": [{
            "event_id": "evtpw-0001",
            "event_type": "paywall_viewed",
            "client_ts": "2026-10-27T12:00:00Z",
            "screen": "Paywall",
            "props": _PROPS,
            "session_id": "sess-pw-0001",
            "seq": 1,
        }]}),
    ).get_json()
    assert body["accepted"] == 1 and body["dropped"] == 0

    with engine.begin() as conn:
        rows = conn.execute(select(user_events_table)).fetchall()
    assert len(rows) == 1
    landed = {k: v for k, v in json.loads(rows[0]._mapping["props"]).items()
              if k not in {"seq", "ts_suspect"}}
    assert landed == _PROPS
