"""B8 minimum-version gate, server half (head-eng ruling 35 + the B8 event grant).

Scope: docs/plans/trade-time-to-suggestion/scope-min-version-gate.md §3.

The gate is a deploy-free kill switch: the `app_min_version` model_config knob
(major*10000 + minor*100 + patch; 0 = off) rides GET /api/feature-flags as one
additive top-level int, and a mobile build whose own version int is below it
shows a blocking "Update required" screen. The mobile half fails open on every
uncertainty (mobile/tests/check-update-gate.js); this file pins the server's
share of that contract:

  * the seed is 0 and insert-if-absent (a deploy never gates anyone and never
    resets a raised value);
  * the flags route serves the knob as an int, and a missing, NaN, infinite,
    fractional or negative value — or a read error — serves 0;
  * the rest of the response is unchanged;
  * the two events are allowlisted with exactly their two prop rows, are
    NON_INTENT, and land through POST /api/events with no session at all
    (the gate can show before sign-in) and with a dead token.
"""
import json
import math
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select

import backend.analytics_ingest as ingest
import backend.analytics_queries as q
import backend.analytics_taxonomy as tax
import backend.database as db_module
import backend.server as server
from backend.database import metadata, model_config_table, user_events_table
from backend.feature_flags import flags_dict


KEY = "app_min_version"
EVENTS = {"update_gate_shown", "update_gate_tapped"}
PROPS = frozenset({"min_version", "app_version_int"})


@pytest.fixture()
def client():
    server.app.config["TESTING"] = True
    return server.app.test_client()


@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


def _flags(client):
    resp = client.get("/api/feature-flags")
    assert resp.status_code == 200
    return resp


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

def test_seed_row_is_zero():
    assert [v for k, v, _ in db_module._MODEL_CONFIG_DEFAULTS if k == KEY] == [0]


def test_seeding_writes_zero_and_a_redeploy_keeps_a_raised_value(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'b8.db'}",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng), \
         patch.object(db_module, "DATABASE_URL", "sqlite:///b8"):
        db_module._migrate_db()
        assert db_module.get_config()[KEY] == 0
        # The admin PUT path (set_config) works on the seeded row...
        db_module.set_config(KEY, 12200.0, source="test_min_version_gate")
        # ...and the next boot's insert-if-absent seed does not reset it.
        db_module._migrate_db()
        assert db_module.get_config()[KEY] == 12200


# ---------------------------------------------------------------------------
# GET /api/feature-flags
# ---------------------------------------------------------------------------

def test_route_serves_the_seeded_zero(client, mem_engine):
    # Empty table → get_config falls back to _MODEL_CONFIG_DEFAULTS.
    body = _flags(client).get_json()
    assert body[KEY] == 0


def test_route_serves_a_raised_value_as_an_int(client, mem_engine):
    with mem_engine.begin() as conn:
        conn.execute(insert(model_config_table).values(
            key=KEY, value=12200.0, description="test"))
    resp = _flags(client)
    body = resp.get_json()
    assert body[KEY] == 12200
    assert type(body[KEY]) is int
    # On the wire it is an integer literal, never 12200.0 (the mobile parser
    # requires Number.isSafeInteger).
    assert b'"app_min_version":12200' in resp.data.replace(b" ", b"")


def test_rest_of_the_response_is_unchanged(client, mem_engine):
    body = _flags(client).get_json()
    assert set(body) == {"flags", "experiments", "configs", KEY}
    assert body["flags"] == flags_dict()
    assert isinstance(body["experiments"], dict)
    assert isinstance(body["configs"], dict)


_MISSING = object()


@pytest.mark.parametrize("bad", [
    _MISSING, None, -1.0, -12200.0, 12200.5, 0.5,
    math.nan, math.inf, -math.inf, "garbage",
], ids=["missing", "none", "neg1", "neg12200", "fractional", "half",
        "nan", "inf", "neginf", "garbage"])
def test_bad_value_serves_zero(client, monkeypatch, bad):
    cfg = {} if bad is _MISSING else {KEY: bad}
    monkeypatch.setattr(server, "get_config", lambda: cfg)
    assert _flags(client).get_json()[KEY] == 0


def test_read_error_serves_zero(client, monkeypatch):
    def boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(server, "get_config", boom)
    body = _flags(client).get_json()
    assert body[KEY] == 0
    assert "flags" in body


@pytest.mark.parametrize("value,served", [(0.0, 0), (1.0, 1), (12200.0, 12200),
                                          (12201.0, 12201), (999999.0, 999999)])
def test_valid_values_pass_through(client, monkeypatch, value, served):
    monkeypatch.setattr(server, "get_config", lambda: {KEY: value})
    assert _flags(client).get_json()[KEY] == served


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def test_events_are_allowlisted_client_events():
    assert EVENTS <= tax.ALLOWED_CLIENT_EVENTS
    assert not (EVENTS & tax._SERVER_AUTHORITATIVE)


def test_event_prop_rows_are_exact():
    """EQUAL, not <=: an extra key is unspecced, a missing one is stripped."""
    for name in EVENTS:
        assert tax.CLIENT_EVENT_PROPS[name] == PROPS, name


def test_events_carry_no_platform_or_version_string_prop():
    for name in EVENTS:
        assert not (tax.CLIENT_EVENT_PROPS[name]
                    & {"platform", "app_version", "version"}), name


def test_events_are_non_intent():
    for name in EVENTS:
        assert name in q.NON_INTENT_EVENTS, name
        assert name not in q.INTENT_EVENTS, name


# Ingest: the gate can show before sign-in or over a session that died with a
# deploy. mobile/src/api/events.ts always sends X-Device-Id and sends
# X-Session-Token only when one is stored; both shapes must land.
DEVICE = "dev_b8gate01"
DEAD_TOKEN = "b8-dead-token"


def _envelope(i, event_type, props):
    return {
        "event_id": f"evtb8-{i:04d}",
        "event_type": event_type,
        "client_ts": "2026-10-24T12:00:00Z",
        "props": props,
        "session_id": "sess-b8-0001",
        "seq": i + 1,
    }


@pytest.fixture()
def ingest_harness():
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


@pytest.mark.parametrize("token", [None, DEAD_TOKEN], ids=["no-session", "dead-token"])
def test_gate_events_land_pre_auth_with_both_props(ingest_harness, token):
    client, engine = ingest_harness
    props = {"min_version": 12200, "app_version_int": 12104}
    headers = {"Content-Type": "application/json", "X-Device-Id": DEVICE}
    if token:
        headers["X-Session-Token"] = token
    body = client.post(
        "/api/events", headers=headers,
        data=json.dumps({"events": [
            _envelope(i, name, props) for i, name in enumerate(sorted(EVENTS))
        ]}),
    ).get_json()
    assert body["accepted"] == len(EVENTS) and body["dropped"] == 0

    with engine.begin() as conn:
        rows = conn.execute(
            select(user_events_table).order_by(user_events_table.c.id)
        ).fetchall()
    by_type = {r._mapping["event_type"]: r._mapping for r in rows}
    assert set(by_type) == EVENTS
    for name in EVENTS:
        row = by_type[name]
        assert row["user_id"] == f"device:{DEVICE}"
        landed = {k: v for k, v in json.loads(row["props"]).items()
                  if k not in {"seq", "ts_suspect"}}
        assert landed == props, name
