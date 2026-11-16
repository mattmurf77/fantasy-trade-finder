"""Playoff targets: analytics registration and the flag on the flags endpoint
(contract §8, §9). Harness mirrors test_maxpf_moves_analytics.py.

The ingest allowlist is default-deny behind a 200, so the names and props are
registered in the same commit as the app's emitters.

- test_names_are_allowlisted_with_exact_props. Sabotage: register
  playoff_targets_viewed without `n_sellers`.
- test_only_the_impression_is_non_intent. Sabotage: leave
  playoff_targets_viewed out of NON_INTENT_EVENTS.
- test_finder_target_pinned_keeps_its_shape_and_documents_the_new_source.
- test_events_land_with_every_prop: POST /api/events accepts all three with
  their props intact, the receive-side pin included.
- test_flag_code_default_off_shipped_on_and_reaches_the_app:
  `league.playoff_targets` is in FLAG_KEYS, false by default in code, true in
  config/features.json and the three fixtures (ON from 2026-11-15, D-271), and
  on GET /api/feature-flags (the app's flag source). Sabotage: drop the key
  from FLAG_KEYS; set it false in config/features.json.
"""
import inspect
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.analytics_ingest as ingest
import backend.analytics_queries as q
import backend.analytics_taxonomy as tax
import backend.database as db_module
import backend.feature_flags as feature_flags
import backend.server as server
from backend.database import metadata, user_events_table

REPO = Path(__file__).resolve().parents[2]
_PROPS = {
    "playoff_targets_viewed": {"state": "ready", "n_listed": 5, "any_pass": True, "n_sellers": 6, "band": "contender"},
    "playoff_target_expanded": {"position": "RB", "rank": 1},
    "finder_target_pinned": {"side": "receive", "source": "playoff_targets"},
}


def test_names_are_allowlisted_with_exact_props():
    assert set(_PROPS) <= tax.ALLOWED_CLIENT_EVENTS
    assert not (set(_PROPS) & tax._SERVER_AUTHORITATIVE)
    for name, props in _PROPS.items():
        assert tax.CLIENT_EVENT_PROPS[name] == frozenset(props), name
        assert not {"platform", "player_id", "name", "player_name"} & tax.CLIENT_EVENT_PROPS[name]


def test_only_the_impression_is_non_intent():
    assert "playoff_targets_viewed" in q.NON_INTENT_EVENTS and "playoff_targets_viewed" not in q.INTENT_EVENTS
    for name in ("playoff_target_expanded", "finder_target_pinned"):
        assert name not in q.NON_INTENT_EVENTS, name


def test_finder_target_pinned_keeps_its_shape_and_documents_the_new_source():
    assert tax.CLIENT_EVENT_PROPS["finder_target_pinned"] == frozenset({"side", "source"})
    source = inspect.getsource(tax)
    assert "playoff_targets (2026-11-14" in source and "maxpf_moves" in source


USER, TOKEN, DEVICE = "taxonomy_targets_test", "tax-targets-token", "dev_targets1"


@pytest.fixture()
def harness():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    with patch.object(db_module, "engine", engine), patch.object(db_module, "ingest_engine", engine), \
         patch.object(ingest, "is_enabled", lambda k: k == "analytics.ingest"):
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


def test_events_land_with_every_prop(harness):
    client, engine = harness
    events = [{"event_id": f"evtpt-{i:04d}", "event_type": name, "client_ts": "2026-11-14T12:00:00Z",
               "screen": "Standings", "props": props, "session_id": "sess-pt-0001", "seq": i + 1}
              for i, (name, props) in enumerate(_PROPS.items())]
    body = client.post("/api/events", headers={"Content-Type": "application/json", "X-Device-Id": DEVICE},
                       data=json.dumps({"events": events})).get_json()
    assert body["accepted"] == len(_PROPS) and body["dropped"] == 0
    with engine.begin() as conn:
        rows = conn.execute(select(user_events_table).order_by(user_events_table.c.id)).fetchall()
    by_type = {r._mapping["event_type"]: r._mapping for r in rows}
    for name, props in _PROPS.items():
        landed = {k: v for k, v in json.loads(by_type[name]["props"]).items() if k not in {"seq", "ts_suspect"}}
        assert landed == props, name


def test_flag_code_default_off_shipped_on_and_reaches_the_app():
    """D-271 (operator, 2026-11-15): the flag ships ON. The code default stays
    off; the three flag fixtures mirror the shipped value."""
    key = "league.playoff_targets"
    assert key in feature_flags.FLAG_KEYS and feature_flags.DEFAULT_FLAGS[key] is False
    assert json.loads((REPO / "config/features.json").read_text())[key] is True
    for name in ("release", "onboarding-v2", "profiles-on"):
        assert json.loads((REPO / f"backend/tests/fixtures/flags/{name}.json").read_text())[key] is True, name
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    old = feature_flags._flags_cache
    try:
        feature_flags._flags_cache = dict(feature_flags.DEFAULT_FLAGS)
        assert client.get("/api/feature-flags").get_json()["flags"][key] is False
        feature_flags._flags_cache = {**feature_flags.DEFAULT_FLAGS, key: True}
        assert client.get("/api/feature-flags").get_json()["flags"][key] is True
    finally:
        feature_flags._flags_cache = old
