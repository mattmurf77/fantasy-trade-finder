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
  * `app_store_live` (the Update target: 1 App Store, 0 TestFlight, -1 unset)
    is seeded -1 and served additively; anything but exactly 0 or 1 serves -1;
  * the rest of the response is unchanged;
  * WRITES of app_min_version go through one shared policy
    (backend/app_version_policy.py): 0, or a decodable x.y.z no higher than
    99999 and no higher than the next minor above mobile/app.json. The admin
    PUT returns 400 with the reason, and scripts/set_knob.py refuses before
    writing on both --local and remote;
  * the two events are allowlisted with exactly their two prop rows, are
    NON_INTENT, and land through POST /api/events with no session at all
    (the gate can show before sign-in) and with a dead token.
"""
import importlib.util
import json
import math
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, insert, select

import backend.analytics_ingest as ingest
import backend.analytics_queries as q
import backend.analytics_taxonomy as tax
import backend.app_version_policy as policy
import backend.database as db_module
import backend.server as server
from backend.database import metadata, model_config_table, user_events_table
from backend.feature_flags import flags_dict


REPO = Path(__file__).resolve().parents[2]
KEY = "app_min_version"
LIVE = "app_store_live"
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
    assert set(body) == {"flags", "experiments", "configs", KEY, LIVE}
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
    assert body[LIVE] == -1
    assert "flags" in body


@pytest.mark.parametrize("value,served", [(0.0, 0), (1.0, 1), (12200.0, 12200),
                                          (12201.0, 12201), (999999.0, 999999)])
def test_valid_values_pass_through(client, monkeypatch, value, served):
    # The READ side stays permissive on purpose: any decodable row serves.
    # Implausible values are stopped at WRITE time (policy tests below).
    monkeypatch.setattr(server, "get_config", lambda: {KEY: value})
    assert _flags(client).get_json()[KEY] == served


# ---------------------------------------------------------------------------
# app_store_live — the Update target (1 App Store, 0 TestFlight, -1 unset)
# ---------------------------------------------------------------------------

def test_app_store_live_seed_is_unset():
    assert [v for k, v, _ in db_module._MODEL_CONFIG_DEFAULTS if k == LIVE] == [-1]


def test_route_serves_the_seeded_unset(client, mem_engine):
    body = _flags(client).get_json()
    assert body[LIVE] == -1 and type(body[LIVE]) is int


@pytest.mark.parametrize("value,served", [(1.0, 1), (0.0, 0), (-1.0, -1)])
def test_app_store_live_valid_values(client, monkeypatch, value, served):
    monkeypatch.setattr(server, "get_config", lambda: {LIVE: value})
    body = _flags(client).get_json()
    assert body[LIVE] == served and type(body[LIVE]) is int


@pytest.mark.parametrize("bad", [
    _MISSING, None, 2.0, -2.0, 0.5, 1.5, math.nan, math.inf, "garbage",
], ids=["missing", "none", "two", "neg2", "half", "one-half", "nan", "inf", "garbage"])
def test_app_store_live_bad_value_serves_unset(client, monkeypatch, bad):
    cfg = {} if bad is _MISSING else {LIVE: bad}
    monkeypatch.setattr(server, "get_config", lambda: cfg)
    assert _flags(client).get_json()[LIVE] == -1


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


# ---------------------------------------------------------------------------
# Write policy — backend/app_version_policy.py (QA P2-1: a typo locks out
# every gate-aware build, so writes are refused before they land)
# ---------------------------------------------------------------------------

def _app_json(tmp_path, version):
    path = tmp_path / "app.json"
    path.write_text(json.dumps({"expo": {"version": version}}))
    return path


@pytest.mark.parametrize("value,app_version", [
    (122000, "1.22.0"),        # one zero too many: above 99999
    (100000, None),            # 99999 + 1 refuses even with app.json unreadable
    (12300, "1.21.4"),         # unreleased: next minor after 1.21.4 is 12200
    (12400, "1.22.0"),         # unreleased: next minor after 1.22.0 is 12300
    (12201, "1.21.4"),         # 1.22.1 does not exist while main is on 1.21.x
    (-1, "1.22.0"),
    (12200.5, "1.22.0"),       # does not decode as x.y.z
    (math.nan, "1.22.0"),
    (math.inf, "1.22.0"),
    ("garbage", "1.22.0"),
    (None, "1.22.0"),
], ids=["122000", "99999+1", "12300@1.21.4", "12400@1.22.0", "12201@1.21.4",
        "neg1", "fractional", "nan", "inf", "garbage", "none"])
def test_policy_refuses(tmp_path, value, app_version):
    path = _app_json(tmp_path, app_version) if app_version else tmp_path / "missing.json"
    reason = policy.validate_app_min_version(value, app_json=path)
    assert reason and reason.startswith("app_min_version")


@pytest.mark.parametrize("value,app_version", [
    (0, "1.21.4"),             # lifting is never refused
    (0, None),
    (12104, "1.21.4"),         # the current build
    (12200, "1.21.4"),         # the next minor's .0 is the cap
    (12200, "1.22.0"),
    (12300, "1.22.0"),         # +1 minor once app.json is 1.22.x
    (12300, "1.22.7"),
    # 12150 decodes as 1.21.50 (major 1, minor 21, patch 50), and the
    # encoding cannot say whether a patch was ever released, so it passes.
    (12150, "1.22.0"),
    (99999, None),             # app.json unreadable → rules 1–2 only
    (50000, "1.22.0-beta"),    # unparseable app.json version → rules 1–2 only
    (20000, "1.99.3"),         # minor 99 carries into the major
], ids=["0", "0-no-app-json", "12104@1.21.4", "12200@1.21.4", "12200@1.22.0",
        "12300@1.22.0", "12300@1.22.7", "12150", "99999-no-app-json",
        "50000-bad-app-version", "20000@1.99.3"])
def test_policy_accepts(tmp_path, value, app_version):
    path = _app_json(tmp_path, app_version) if app_version else tmp_path / "missing.json"
    assert policy.validate_app_min_version(value, app_json=path) is None


def test_policy_reads_the_real_app_json_at_call_time(tmp_path, monkeypatch):
    real = json.loads((REPO / "mobile" / "app.json").read_text())["expo"]["version"]
    assert policy.version_int(real) is not None
    assert policy.current_app_version_int() == policy.version_int(real)
    # APP_JSON is resolved per call, not bound at import: repointing it moves
    # the cap immediately (what a release bump on main does on the server).
    monkeypatch.setattr(policy, "APP_JSON", _app_json(tmp_path, "1.22.0"))
    assert policy.validate_app_min_version(12300) is None
    monkeypatch.setattr(policy, "APP_JSON", _app_json(tmp_path, "1.21.4"))
    assert policy.validate_app_min_version(12300)


SECRET = "b8-unit-test-cron-secret"


@pytest.fixture()
def admin(tmp_path, mem_engine, monkeypatch):
    with mem_engine.begin() as conn:
        conn.execute(insert(model_config_table), [
            {"key": KEY, "value": 0.0, "description": "t"},
            {"key": LIVE, "value": -1.0, "description": "t"},
        ])
    monkeypatch.setattr(policy, "APP_JSON", _app_json(tmp_path, "1.22.0"))
    monkeypatch.setattr(server, "_CRON_SECRET", SECRET)
    monkeypatch.setattr(server, "_IS_PROD_ENV", True)
    monkeypatch.setattr(server._trade_service_mod, "reload_config", MagicMock())
    monkeypatch.setattr(server._ranking_service_mod, "reload_config", MagicMock())
    server.app.config["TESTING"] = True
    return server.app.test_client(), mem_engine


def _put(c, key, value):
    return c.put(f"/api/admin/config/{key}",
                 headers={"X-Cron-Secret": SECRET},
                 data=json.dumps({"value": value}),
                 content_type="application/json")


def _row(eng, key):
    with eng.connect() as conn:
        return conn.execute(select(model_config_table.c.value)
                            .where(model_config_table.c.key == key)).scalar()


def _changes(eng):
    with eng.connect() as conn:
        return conn.execute(select(db_module.model_config_changes_table)).fetchall()


@pytest.mark.parametrize("value", [122000, 100000, 12400, -1, 12200.5, "nan"])
def test_admin_put_refuses_with_400_and_writes_nothing(admin, value):
    c, eng = admin
    resp = _put(c, KEY, value)
    assert resp.status_code == 400
    assert resp.get_json()["error"].startswith("app_min_version")
    assert _row(eng, KEY) == 0.0
    assert _changes(eng) == []


@pytest.mark.parametrize("value", [12200, 12300, 12201, 0])
def test_admin_put_accepts_a_plausible_value(admin, value):
    c, eng = admin
    resp = _put(c, KEY, value)
    assert resp.status_code == 200, resp.get_json()
    assert _row(eng, KEY) == float(value)


def test_admin_put_policy_is_scoped_to_app_min_version(admin):
    c, eng = admin
    assert _put(c, LIVE, 1).status_code == 200
    assert _row(eng, LIVE) == 1.0


def _load_set_knob():
    spec = importlib.util.spec_from_file_location(
        "set_knob_under_test", REPO / "scripts" / "set_knob.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def knob(tmp_path, monkeypatch):
    """scripts/set_knob.py with both write paths stubbed and observable."""
    sk = _load_set_knob()
    monkeypatch.setattr(policy, "APP_JSON", _app_json(tmp_path, "1.22.0"))
    set_config = MagicMock(return_value={"key": KEY, "value": 0.0, "old_value": 0.0})
    monkeypatch.setattr(db_module, "set_config", set_config)
    urlopen = MagicMock()
    urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(
        {"key": KEY, "value": 0.0, "old_value": 0.0}).encode()
    monkeypatch.setattr(sk.urllib.request, "urlopen", urlopen)
    monkeypatch.setenv("CRON_SECRET", "x")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    def run(*args):
        monkeypatch.setattr(sys, "argv", ["set_knob.py", *args])
        sk.main()
    return run, set_config, urlopen


@pytest.mark.parametrize("mode", ["local", "remote"])
@pytest.mark.parametrize("value", ["122000", "12400", "-1", "12200.5"])
def test_set_knob_refuses_before_either_write(knob, mode, value):
    run, set_config, urlopen = knob
    extra = ["--local"] if mode == "local" else ["--base", "http://b8.invalid"]
    with pytest.raises(SystemExit) as exc:
        run(KEY, value, *extra)
    assert str(exc.value).startswith("refusing: app_min_version")
    set_config.assert_not_called()
    urlopen.assert_not_called()


@pytest.mark.parametrize("mode", ["local", "remote"])
def test_set_knob_writes_a_plausible_value(knob, mode):
    run, set_config, urlopen = knob
    if mode == "local":
        run(KEY, "12300", "--local")
        set_config.assert_called_once_with(KEY, 12300.0, source="operator-local")
    else:
        run(KEY, "12300", "--base", "http://b8.invalid")
        urlopen.assert_called_once()
