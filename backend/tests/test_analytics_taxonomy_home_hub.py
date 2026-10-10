"""Home hub (flag `nav.home_hub`, 2026-10-10) — taxonomy registration.

Scope: docs/plans/home-engagement/scope.md §1. Registered in Phase 1
(foundations) BEFORE either emitter ships, because the ingest allowlist is
default-deny behind a 200: an unregistered name is counted and dropped, and
an unregistered prop is stripped while the response still reports
dropped == 0. Same shape as test_analytics_taxonomy_384.py.

Both names are NON_INTENT on purpose (INTENT is derived by subtraction, so a
passive name left unclassified step-changes DAU/WAU on ship day):
  * home_tile_tapped — navigation off the LAUNCH tab, the tab_selected class;
  * standings_segment_changed — a lens switch on a read-only page.
"""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.analytics_ingest as ingest
import backend.database as db_module
import backend.server as server
from backend.database import metadata, user_events_table


_PROPS: dict[str, dict] = {
    "home_tile_tapped": {"tile": "sell", "position": "RB", "band": "seller"},
    "standings_segment_changed": {"segment": "projected"},
}


def test_home_hub_names_are_allowlisted():
    import backend.analytics_taxonomy as tax
    assert set(_PROPS) <= tax.ALLOWED_CLIENT_EVENTS
    assert not (set(_PROPS) & tax._SERVER_AUTHORITATIVE)


def test_home_hub_prop_rows_are_exact():
    """EQUAL, not <=: an extra key is unspecced, a missing one is stripped."""
    import backend.analytics_taxonomy as tax
    for name, props in _PROPS.items():
        assert tax.CLIENT_EVENT_PROPS[name] == frozenset(props), name


def test_home_hub_carries_no_device_platform_prop():
    import backend.analytics_taxonomy as tax
    for name in _PROPS:
        assert "platform" not in tax.CLIENT_EVENT_PROPS[name], name


def test_home_hub_names_are_non_intent():
    import backend.analytics_queries as q
    for name in _PROPS:
        assert name in q.NON_INTENT_EVENTS, name
        assert name not in q.INTENT_EVENTS, name


def test_home_hub_mints_no_duplicate_of_a_shipped_event():
    """Home adds an entry point, not a second source of truth: the split's
    own exposure and conversion events keep their exact shapes."""
    import backend.analytics_taxonomy as tax
    assert tax.CLIENT_EVENT_PROPS["league_pos_candidates_viewed"] == frozenset(
        {"position", "divider"})
    assert tax.CLIENT_EVENT_PROPS["league_candidate_pinned"] == frozenset(
        {"verb", "position", "rank", "side"})
    assert tax.CLIENT_EVENT_PROPS["tab_selected"] == frozenset(
        {"tab", "from_tab", "refocus", "intercepted"})


# ---------------------------------------------------------------------------
# Ingest — the names and props actually survive POST /api/events.
# Harness mirrors test_analytics_taxonomy_384.py / test_events_api.py.
# ---------------------------------------------------------------------------

USER = "taxonomy_home_hub_test"
TOKEN = "tax-home-hub-token"
DEVICE = "dev_homehub01"


def _envelope(i, event_type, props, screen):
    return {
        "event_id": f"evthh-{i:04d}",
        "event_type": event_type,
        "client_ts": "2026-10-10T12:00:00Z",
        "screen": screen,
        "props": props,
        "session_id": "sess-hh-0001",
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


def test_home_hub_events_land_with_every_prop(harness):
    client, engine = harness
    screens = {"home_tile_tapped": "Home", "standings_segment_changed": "Standings"}
    body = client.post(
        "/api/events",
        headers={"Content-Type": "application/json", "X-Device-Id": DEVICE},
        data=json.dumps({"events": [
            _envelope(i, name, props, screens[name])
            for i, (name, props) in enumerate(_PROPS.items())
        ]}),
    ).get_json()
    assert body["accepted"] == len(_PROPS) and body["dropped"] == 0

    with engine.begin() as conn:
        rows = conn.execute(
            select(user_events_table).order_by(user_events_table.c.id)
        ).fetchall()
    by_type = {r._mapping["event_type"]: r._mapping for r in rows}
    assert set(by_type) == set(_PROPS)
    for name, props in _PROPS.items():
        landed = {k: v for k, v in json.loads(by_type[name]["props"]).items()
                  if k not in {"seq", "ts_suspect"}}
        assert landed == props, name
