"""sleeper_handoff_resolved — taxonomy registration (#351 / #379, 2026-10-28).

Grant: analytics-lead, 2026-10-20, G1–G7 (widened @ 8b63ef10). Addendum:
docs/business/analytics/2026-10-28-sleeper-handoff-events.md. Registered in
the same commit as the emitter (mobile/src/utils/sleeperHandoff.ts,
trackHandoff), because the ingest allowlist is default-deny behind a 200: an
unregistered name is counted and dropped, and an unregistered prop is stripped
while the response still reports dropped == 0.

INTENT on purpose (G6: no NON_INTENT_EVENTS row). Every firing follows a
deliberate CTA tap, and the outcome of a deliberate act stays INTENT, failure
included (the sleeper_send_* precedent). Not a WAT event.

Same shape as test_analytics_taxonomy_home_hub.py.
"""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.analytics_ingest as ingest
import backend.database as db_module
import backend.server as server
from backend.database import metadata, user_events_table


NAME = "sleeper_handoff_resolved"
PROPS = frozenset({"surface", "target", "rung", "outcome", "has_drop"})

# One row per shape the emitter can send (G2): has_drop only on an add row off
# send_button, and absent (never null) everywhere else.
_ROWS = [
    {"surface": "free_agents", "target": "add", "rung": "bare",
     "outcome": "app", "has_drop": True},
    {"surface": "usage_trends", "target": "add", "rung": "bare",
     "outcome": "not_installed", "has_drop": False},
    {"surface": "send_button", "target": "trade", "rung": "bare",
     "outcome": "app"},
    {"surface": "trade_queue", "target": "trade", "rung": "trades_tab",
     "outcome": "not_installed"},
]


def test_name_is_client_allowlisted_and_not_server_authoritative():
    import backend.analytics_taxonomy as tax
    assert NAME in tax.ALLOWED_CLIENT_EVENTS
    assert NAME not in tax.SERVER_FIRED_EVENTS
    assert NAME not in tax._SERVER_AUTHORITATIVE


def test_namespaces_stay_disjoint():
    import backend.analytics_taxonomy as tax
    tax._assert_namespaces_disjoint(tax.ALLOWED_CLIENT_EVENTS,
                                    tax._SERVER_AUTHORITATIVE)
    with pytest.raises(ValueError):
        tax._assert_namespaces_disjoint(frozenset({NAME}), frozenset({NAME}))


def test_prop_row_is_exact():
    """EQUAL, not <=: an extra key is unspecced, a missing one is stripped."""
    import backend.analytics_taxonomy as tax
    assert tax.CLIENT_EVENT_PROPS[NAME] == PROPS


def test_carries_no_device_platform_or_identity_prop():
    """No device `platform` (a user_events column, never a prop); no player
    id, name or league id (G5)."""
    import backend.analytics_taxonomy as tax
    row = tax.CLIENT_EVENT_PROPS[NAME]
    assert "platform" not in row
    assert not {"player_id", "player_name", "name", "league_id"} & row


def test_is_intent_and_not_wat():
    import backend.analytics_queries as q
    assert NAME not in q.NON_INTENT_EVENTS
    assert NAME in q.INTENT_EVENTS
    assert NAME not in q.WAT_EVENTS


def test_external_link_opened_is_not_registered():
    """Not granted (and its `platform` prop collides with the envelope
    column). Only the Sleeper hand-off event exists."""
    import backend.analytics_taxonomy as tax
    assert "external_link_opened" not in tax.ALLOWED_CLIENT_EVENTS
    assert "external_link_opened" not in tax.CLIENT_EVENT_PROPS


# ---------------------------------------------------------------------------
# Ingest — every shape survives POST /api/events with its props intact, and an
# absent has_drop stays absent.
# Harness mirrors test_analytics_taxonomy_home_hub.py.
# ---------------------------------------------------------------------------

USER = "taxonomy_sleeper_handoff_test"
TOKEN = "tax-sleeper-handoff-token"
DEVICE = "dev_sleeperhandoff01"


def _envelope(i, props):
    return {
        "event_id": f"evtsh-{i:04d}",
        "event_type": NAME,
        "client_ts": "2026-10-28T12:00:00Z",
        "props": props,
        "session_id": "sess-sh-0001",
        "seq": i + 1,
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


def test_every_shape_lands_intact(harness):
    client, engine = harness
    body = client.post(
        "/api/events",
        headers={"Content-Type": "application/json", "X-Device-Id": DEVICE},
        data=json.dumps({"events": [_envelope(i, p) for i, p in enumerate(_ROWS)]}),
    ).get_json()
    assert body["accepted"] == len(_ROWS) and body["dropped"] == 0

    with engine.begin() as conn:
        rows = conn.execute(
            select(user_events_table).order_by(user_events_table.c.id)
        ).fetchall()
    assert [r._mapping["event_type"] for r in rows] == [NAME] * len(_ROWS)
    for row, sent in zip(rows, _ROWS):
        landed = {k: v for k, v in json.loads(row._mapping["props"]).items()
                  if k not in {"seq", "ts_suspect"}}
        assert landed == sent
        if sent["target"] == "trade" or sent["surface"] == "send_button":
            assert "has_drop" not in landed
