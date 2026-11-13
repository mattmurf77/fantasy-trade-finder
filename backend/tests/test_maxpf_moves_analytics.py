"""Max PF moves: analytics registration and the flag on the flags endpoint
(contract §8, §9; plan B7).

The ingest allowlist is default-deny behind a 200, so the names and props are
registered in the same change as the app's emitters. Harness mirrors
test_analytics_taxonomy_home_hub.py.

- test_names_are_allowlisted_with_exact_props. Sabotage: register
  maxpf_moves_viewed without `band`.
- test_only_the_impression_is_non_intent. Sabotage: classify
  maxpf_move_expanded as non-intent / leave maxpf_moves_viewed out.
- test_finder_target_pinned_keeps_its_shape_and_documents_the_new_source.
- test_events_land_with_every_prop: POST /api/events accepts all four with
  their props intact.
- test_build_191_shape_and_a_combined_line_land (v1.1, D-261).
- test_flags_endpoint_serves_the_flag: GET /api/feature-flags (the app's
  flag source, mobile/src/api/flags.ts) carries `league.max_pf_moves`, false
  by default and true when turned on. Sabotage: drop the key from FLAG_KEYS.
"""
import inspect
import json
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

_PROPS = {
    "maxpf_moves_viewed": {"state": "ready", "n_moves": 3, "band": "jets", "n_listed": 8, "any_pass": True},
    "maxpf_move_expanded": {"position": "RB", "rank": 1},
    "draft_order_rule_answered": {"answer": "reverse_standings", "source": "first_ask"},
    "finder_target_pinned": {"side": "give", "source": "maxpf_moves"},
}
NEW = ("maxpf_moves_viewed", "maxpf_move_expanded", "draft_order_rule_answered")


def test_names_are_allowlisted_with_exact_props():
    assert set(_PROPS) <= tax.ALLOWED_CLIENT_EVENTS
    assert not (set(_PROPS) & tax._SERVER_AUTHORITATIVE)
    for name, props in _PROPS.items():
        assert tax.CLIENT_EVENT_PROPS[name] == frozenset(props), name
        assert "platform" not in tax.CLIENT_EVENT_PROPS[name]


def test_only_the_impression_is_non_intent():
    assert "maxpf_moves_viewed" in q.NON_INTENT_EVENTS and "maxpf_moves_viewed" not in q.INTENT_EVENTS
    for name in ("maxpf_move_expanded", "draft_order_rule_answered", "finder_target_pinned"):
        assert name not in q.NON_INTENT_EVENTS, name


def test_finder_target_pinned_keeps_its_shape_and_documents_the_new_source():
    assert tax.CLIENT_EVENT_PROPS["finder_target_pinned"] == frozenset({"side", "source"})
    assert "maxpf_moves" in inspect.getsource(tax)


USER, TOKEN, DEVICE = "taxonomy_maxpf_test", "tax-maxpf-token", "dev_maxpf01"


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
    events = [{"event_id": f"evtmp-{i:04d}", "event_type": name, "client_ts": "2026-11-12T12:00:00Z",
               "screen": "Standings", "props": props, "session_id": "sess-mp-0001", "seq": i + 1}
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


def test_build_191_shape_and_a_combined_line_land(harness):
    """v1.1 (D-261): the registration is a superset, so a build-191 viewed event
    (no n_listed / any_pass) lands as sent, and a combined line's expand event
    carries rank 'combined_2'."""
    client, engine = harness
    sent = {"maxpf_moves_viewed": {"state": "no_moves", "n_moves": 0, "band": "contender"},
            "maxpf_move_expanded": {"position": "combined", "rank": "combined_2"}}
    events = [{"event_id": f"evtmq-{i:04d}", "event_type": name, "client_ts": "2026-11-13T12:00:00Z",
               "screen": "Standings", "props": props, "session_id": "sess-mq-0001", "seq": i + 1}
              for i, (name, props) in enumerate(sent.items())]
    body = client.post("/api/events", headers={"Content-Type": "application/json", "X-Device-Id": DEVICE},
                       data=json.dumps({"events": events})).get_json()
    assert body["accepted"] == 2 and body["dropped"] == 0
    with engine.begin() as conn:
        rows = conn.execute(select(user_events_table).order_by(user_events_table.c.id)).fetchall()
    for r in rows:
        landed = {k: v for k, v in json.loads(r._mapping["props"]).items() if k not in {"seq", "ts_suspect"}}
        assert landed == sent[r._mapping["event_type"]]


def test_flags_endpoint_serves_the_flag():
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    old = feature_flags._flags_cache
    try:
        feature_flags._flags_cache = dict(feature_flags.DEFAULT_FLAGS)
        assert client.get("/api/feature-flags").get_json()["flags"]["league.max_pf_moves"] is False
        feature_flags._flags_cache = {**feature_flags.DEFAULT_FLAGS, "league.max_pf_moves": True}
        assert client.get("/api/feature-flags").get_json()["flags"]["league.max_pf_moves"] is True
    finally:
        feature_flags._flags_cache = old
