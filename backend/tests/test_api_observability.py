"""API observability (flag obs.api_events, backend/api_observability.py).

Pins the operator-directed observability program's core guarantees:

  • wrapper capture correctness per service class — Sleeper REST
    (`server._sleeper_get`), Sleeper GraphQL (`sleeper_write._post_graphql`),
    the trade_block bypass site, ESPN (`espn_service.fetch_league`), MFL
    (`mfl_service._fetch_one`) — mocked upstream, asserted event properties;
  • REDACTION — a credential value (ESPN espn_s2 cookie, Sleeper JWT) never
    appears ANYWHERE in a stored event, and prop specs (OBS_EVENT_PROPS) are
    enforced by stripping unknown keys;
  • inbound hook capture (route PATTERN not raw path, status, latency,
    error code; /api/events excluded; non-/api paths excluded);
  • sampling — successes 1-in-N with sample_n stamped, errors always full;
  • kill switch — flag off ⇒ ZERO event writes, calls/requests unaffected;
  • failure isolation — a poisoned event store never breaks the API call;
  • retention purge and the apihealth report.

All event writes go through db.ingest_engine — patched here to an isolated
in-memory SQLite so nothing touches the dev DB.
"""

import io
import json
import urllib.error
import urllib.request
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select

import backend.api_observability as ao
import backend.analytics_queries as aq
import backend.database as db
import backend.espn_service as espn_service
import backend.mfl_service as mfl_service
import backend.server as server
import backend.sleeper_write as sleeper_write
import backend.trade_block_service as trade_block_service
from backend.analytics_taxonomy import (ALLOWED_CLIENT_EVENTS,
                                        OBS_EVENT_PROPS, SERVER_FIRED_EVENTS)
from backend.database import metadata, user_events_table

# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

S2_SECRET = "AEBsecret%2Fcookie%2Bvalue%3Dxyzabcdefghijklmnop"
JWT_SECRET = "eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiMTIzIn0.sigsigsigsig"


class FakeResp:
    def __init__(self, body, status=200):
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_urlopen(body, status=200):
    def opener(req, timeout=None, context=None):
        return FakeResp(body, status)
    return opener


def _http_error(code, body=b"err"):
    def opener(req, timeout=None, context=None):
        raise urllib.error.HTTPError("http://x", code, "boom", {}, io.BytesIO(body))
    return opener


@pytest.fixture()
def obs_env(monkeypatch):
    """Isolated in-memory event store + flag forced ON + sample N=1."""
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    monkeypatch.setattr(db, "ingest_engine", eng)
    monkeypatch.setattr(db, "ro_engine", eng)
    monkeypatch.setattr(ao, "is_enabled", lambda key: True)
    monkeypatch.setattr(ao, "_sample_n", lambda: 1)
    ao._counters.clear()
    return eng


def _events(eng, etype=None):
    with eng.connect() as conn:
        q = select(user_events_table)
        if etype:
            q = q.where(user_events_table.c.event_type == etype)
        return [dict(r) for r in conn.execute(q).mappings().all()]


def _props(row):
    return json.loads(row["props"] or "{}")


# ---------------------------------------------------------------------------
# Taxonomy registration
# ---------------------------------------------------------------------------

def test_event_names_registered_server_fired():
    assert "api_call" in SERVER_FIRED_EVENTS
    assert "api_request" in SERVER_FIRED_EVENTS
    # never client-submittable
    assert "api_call" not in ALLOWED_CLIENT_EVENTS
    assert "api_request" not in ALLOWED_CLIENT_EVENTS
    # both carry a prop spec
    assert OBS_EVENT_PROPS["api_call"]
    assert OBS_EVENT_PROPS["api_request"]


def test_prop_spec_enforced_unknown_keys_stripped():
    clean = ao._scrub_props(
        {"service": "espn", "endpoint": "league_read", "bogus": "x",
         "cookie_value": "SECRET"}, "api_call")
    assert clean == {"service": "espn", "endpoint": "league_read"}


def test_value_shape_scrub_redacts_jwt():
    assert JWT_SECRET not in ao._scrub_value(f"failed with {JWT_SECRET} token")


# ---------------------------------------------------------------------------
# Outbound wrapper — per service class
# ---------------------------------------------------------------------------

def test_sleeper_rest_success_captured(obs_env, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen",
                        _fake_urlopen([{"roster_id": 1}]))
    data = server._sleeper_get("https://api.sleeper.app/v1/league/12345/rosters")
    assert data == [{"roster_id": 1}]
    rows = _events(obs_env, "api_call")
    assert len(rows) == 1
    row = rows[0]
    p = _props(row)
    assert p["service"] == "sleeper"
    assert p["endpoint"] == "league.rosters"
    assert p["ok"] is True
    assert p["status"] == 200
    assert p["sample_n"] == 1
    assert isinstance(p["ms"], int)
    assert row["user_id"] == "system:api"
    assert row["league_id"] == "12345"
    assert row["screen"] == "sleeper.league.rosters"
    # every prop conforms to the spec
    assert set(p) <= set(OBS_EVENT_PROPS["api_call"])


def test_sleeper_rest_error_captured_and_reraised(obs_env, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", _http_error(503))
    with pytest.raises(urllib.error.HTTPError):
        server._sleeper_get("https://api.sleeper.app/v1/user/someuser")
    rows = _events(obs_env, "api_call")
    assert len(rows) == 1
    p = _props(rows[0])
    assert p["ok"] is False
    assert p["status"] == 503
    assert p["endpoint"] == "user"          # username never in the class
    assert p["error_class"] == "HTTPError"
    dumped = json.dumps(rows)
    assert "someuser" not in dumped


def test_sleeper_graphql_auth_error_kind(obs_env, monkeypatch):
    monkeypatch.setattr(
        urllib.request, "urlopen",
        _fake_urlopen({"errors": [{"message": "unauthorized token"}]}))
    with pytest.raises(sleeper_write.SleeperAuthError):
        sleeper_write._post_graphql("propose_trade", JWT_SECRET,
                                    {"operationName": "propose_trade"})
    rows = _events(obs_env, "api_call")
    assert len(rows) == 1
    p = _props(rows[0])
    assert p["service"] == "sleeper"
    assert p["endpoint"] == "graphql.propose_trade"
    assert p["ok"] is False
    assert p["error_class"] == "SleeperAuthError"
    assert p["error_kind"] == "auth"
    # THE redaction guarantee: the JWT appears nowhere in any stored event.
    assert JWT_SECRET not in json.dumps(rows)


def test_trade_block_bypass_site_routed_through_wrapper(obs_env, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen",
                        _fake_urlopen([{"roster_id": 2, "owner_id": "u1"}]))
    trade_block_service._fetch_rosters("999")
    rows = _events(obs_env, "api_call")
    assert len(rows) == 1
    p = _props(rows[0])
    assert (p["service"], p["endpoint"]) == ("sleeper", "league.rosters")
    assert rows[0]["league_id"] == "999"


def test_espn_auth_failure_cookie_shape_no_cookie_value(obs_env, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", _http_error(401))
    with pytest.raises(espn_service.EspnAuthError):
        espn_service.fetch_league("777", 2026, espn_s2=S2_SECRET,
                                  swid="{AAAA-BBBB-CCCC}")
    rows = _events(obs_env, "api_call")
    assert len(rows) == 1
    p = _props(rows[0])
    assert p["service"] == "espn"
    assert p["endpoint"] == "league_read"
    assert p["ok"] is False
    assert p["status"] == 401
    assert p["error_kind"] == "auth"
    assert p["auth_mode"] == "cookie"
    assert p["s2_encoded"] is True          # shape boolean, not the value
    assert p["swid_braced"] is True
    # THE test the mission demands: the cookie VALUE never appears anywhere
    # in a stored event — not in props, not in any column.
    dumped = json.dumps(rows)
    assert S2_SECRET not in dumped
    assert "AAAA-BBBB-CCCC" not in dumped


def test_espn_fan_profile_call_redacted_and_props_correct(obs_env, monkeypatch):
    # League-picker fan-profile lookup (2026-08-09, GET /api/espn/my-leagues,
    # flag `espn.league_picker`) — the SAME cookie pair replayed against a
    # SEPARATE host (fan.api.espn.com, not the league-read API). Same
    # redaction posture, distinct endpoint class.
    monkeypatch.setattr(urllib.request, "urlopen",
                        _fake_urlopen({"preferences": []}))
    espn_service.fetch_fan_leagues(S2_SECRET, "{AAAA-BBBB-CCCC}")
    rows = _events(obs_env, "api_call")
    assert len(rows) == 1
    p = _props(rows[0])
    assert p["service"] == "espn"
    assert p["endpoint"] == "fan_profile"
    assert p["ok"] is True
    assert p["auth_mode"] == "cookie"
    assert p["s2_encoded"] is True
    assert p["swid_braced"] is True
    dumped = json.dumps(rows)
    assert S2_SECRET not in dumped
    assert "AAAA-BBBB-CCCC" not in dumped


def test_espn_fan_profile_auth_failure_recorded_and_redacted(obs_env, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", _http_error(401))
    with pytest.raises(espn_service.EspnAuthError):
        espn_service.fetch_fan_leagues(S2_SECRET, "{AAAA-BBBB-CCCC}")
    rows = _events(obs_env, "api_call")
    assert len(rows) == 1
    p = _props(rows[0])
    assert (p["service"], p["endpoint"]) == ("espn", "fan_profile")
    assert p["ok"] is False
    assert p["status"] == 401
    assert p["error_kind"] == "auth"
    dumped = json.dumps(rows)
    assert S2_SECRET not in dumped


def test_mfl_export_captured_with_host_and_type(obs_env, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen",
                        _fake_urlopen({"rosters": {"franchise": []}}))
    out = mfl_service._fetch_one("www44.myfantasyleague.com", 2026, "rosters",
                                 "12345", "MFL_USER_ID=SECRETCOOKIE", 10, None)
    assert out == {"rosters": {"franchise": []}}
    rows = _events(obs_env, "api_call")
    assert len(rows) == 1
    p = _props(rows[0])
    assert p["service"] == "mfl"
    assert p["endpoint"] == "export.rosters"
    assert p["host"] == "www44.myfantasyleague.com"
    assert p["auth_mode"] == "cookie"
    assert "SECRETCOOKIE" not in json.dumps(rows)


def test_injected_opener_seam_is_not_instrumented(obs_env):
    """`_opener` (unit-test seam) skips instrumentation entirely."""
    out = trade_block_service._fetch_rosters(
        "1", _opener=lambda req, timeout=None: FakeResp([]))
    assert out == []
    assert _events(obs_env) == []


# ---------------------------------------------------------------------------
# Sampling — errors always, successes 1-in-N with sample_n stamped
# ---------------------------------------------------------------------------

def test_success_sampling_one_in_n(obs_env, monkeypatch):
    monkeypatch.setattr(ao, "_sample_n", lambda: 3)
    ao._counters.clear()
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen([]))
    for _ in range(6):
        trade_block_service._fetch_rosters("55")
    rows = _events(obs_env, "api_call")
    assert len(rows) == 2                       # 1st and 4th of 6
    assert all(_props(r)["sample_n"] == 3 for r in rows)


def test_errors_never_sampled(obs_env, monkeypatch):
    monkeypatch.setattr(ao, "_sample_n", lambda: 1000)
    ao._counters.clear()
    monkeypatch.setattr(urllib.request, "urlopen", _http_error(500))
    for _ in range(6):
        with pytest.raises(Exception):
            trade_block_service._fetch_rosters("55")
    rows = _events(obs_env, "api_call")
    assert len(rows) == 6
    assert all(_props(r)["ok"] is False for r in rows)
    assert all("sample_n" not in _props(r) for r in rows)


# ---------------------------------------------------------------------------
# Inbound hooks
# ---------------------------------------------------------------------------

def test_inbound_success_captured_route_pattern(obs_env):
    client = server.app.test_client()
    resp = client.get("/api/feature-flags")
    assert resp.status_code == 200
    rows = _events(obs_env, "api_request")
    assert len(rows) == 1
    p = _props(rows[0])
    assert p["route"] == "/api/feature-flags"
    assert p["method"] == "GET"
    assert p["status"] == 200
    assert p["ok"] is True
    assert isinstance(p["ms"], int)
    assert rows[0]["user_id"] == "system:api"
    assert set(p) <= set(OBS_EVENT_PROPS["api_request"])


def test_inbound_error_captures_error_code_not_raw_path(obs_env):
    client = server.app.test_client()
    resp = client.get("/api/admin/analytics/not-a-report")
    assert resp.status_code == 400
    rows = _events(obs_env, "api_request")
    assert len(rows) == 1
    p = _props(rows[0])
    assert p["route"] == "/api/admin/analytics/<report>"  # PATTERN, not path
    assert p["ok"] is False
    assert p["status"] == 400
    assert p["error_code"] == "unknown_report"
    assert "not-a-report" not in json.dumps(rows)


def test_inbound_unmatched_404_bucketed_without_path(obs_env):
    """An unknown /api/ path falls into the static catch-all rule — the
    recorded route is the PATTERN (/<path:filename>), never the raw path."""
    client = server.app.test_client()
    resp = client.get("/api/definitely/not/a/route/PII-VALUE-42")
    assert resp.status_code == 404
    rows = _events(obs_env, "api_request")
    assert len(rows) == 1
    p = _props(rows[0])
    assert p["route"] == "/<path:filename>"
    assert p["status"] == 404
    assert "PII-VALUE-42" not in json.dumps(rows)


def test_inbound_exclusions(obs_env):
    client = server.app.test_client()
    # analytics ingest route must never observe itself
    client.post("/api/events", json={"events": []},
                headers={"X-Device-Id": "dev_obs_test"})
    # non-/api paths (static assets / web pages) are out of scope
    client.get("/definitely-not-api")
    assert _events(obs_env, "api_request") == []


# ---------------------------------------------------------------------------
# Kill switch — off = zero writes, calls/requests unaffected
# ---------------------------------------------------------------------------

def test_kill_switch_zero_writes(obs_env, monkeypatch):
    monkeypatch.setattr(ao, "is_enabled", lambda key: False)
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen([{"a": 1}]))
    data = server._sleeper_get("https://api.sleeper.app/v1/league/1/rosters")
    assert data == [{"a": 1}]
    client = server.app.test_client()
    assert client.get("/api/feature-flags").status_code == 200
    assert _events(obs_env) == []


# ---------------------------------------------------------------------------
# Failure isolation — a poisoned event store never breaks the real path
# ---------------------------------------------------------------------------

class _PoisonEngine:
    def begin(self):
        raise RuntimeError("event store is down")

    def connect(self):
        raise RuntimeError("event store is down")


def test_poisoned_store_does_not_break_outbound_call(obs_env, monkeypatch):
    monkeypatch.setattr(db, "ingest_engine", _PoisonEngine())
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen([{"a": 1}]))
    data = server._sleeper_get("https://api.sleeper.app/v1/league/1/rosters")
    assert data == [{"a": 1}]                  # the real call proceeded


def test_poisoned_store_does_not_break_inbound_request(obs_env, monkeypatch):
    monkeypatch.setattr(db, "ingest_engine", _PoisonEngine())
    client = server.app.test_client()
    resp = client.get("/api/feature-flags")
    assert resp.status_code == 200             # byte-identical response path


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------

def test_retention_purge_deletes_only_old_obs_rows(obs_env, monkeypatch):
    monkeypatch.setattr(db, "engine", obs_env)
    with obs_env.begin() as conn:
        for etype, day in (("api_call", "2020-01-01"),
                           ("api_call", "2099-01-01"),
                           ("api_request", "2020-01-01"),
                           ("trade_proposed", "2020-01-01")):   # non-obs: kept
            conn.execute(insert(user_events_table).values(
                user_id="system:api", event_type=etype,
                occurred_at=f"{day}T00:00:00+00:00"))
    deleted = ao.purge_observability_events(force=True)
    assert deleted == 2
    remaining = {(r["event_type"], r["occurred_at"][:4])
                 for r in _events(obs_env)}
    assert remaining == {("api_call", "2099"), ("trade_proposed", "2020")}


# ---------------------------------------------------------------------------
# apihealth report
# ---------------------------------------------------------------------------

def _seed_report_rows(eng):
    def ev(etype, props, day="2026-08-09"):
        with eng.begin() as conn:
            conn.execute(insert(user_events_table).values(
                user_id="system:api", event_type=etype,
                occurred_at=f"{day}T12:00:00+00:00",
                props=json.dumps(props)))
    ev("api_call", {"service": "espn", "endpoint": "league_read", "ok": False,
                    "status": 401, "error_class": "EspnAuthError",
                    "error_kind": "auth", "ms": 340})
    ev("api_call", {"service": "espn", "endpoint": "league_read", "ok": True,
                    "status": 200, "ms": 250, "sample_n": 10})
    ev("api_call", {"service": "sleeper", "endpoint": "league.rosters",
                    "ok": True, "status": 200, "ms": 90, "sample_n": 10})
    ev("api_request", {"route": "/api/trades/generate", "method": "POST",
                       "ok": False, "status": 500, "ms": 5000,
                       "error_class": "RuntimeError"})


def test_apihealth_report_aggregates(obs_env):
    _seed_report_rows(obs_env)
    env, _ = aq.run_report("apihealth", start="2026-08-09", end="2026-08-09")
    svc = env["summary"]["services"]
    assert svc["espn"]["errors"] == 1
    assert svc["espn"]["est_calls"] == 11          # 10 (sampled) + 1 (error)
    assert svc["espn"]["failure_rate"] == pytest.approx(1 / 11)
    assert svc["ftf_api"]["errors"] == 1
    fails = env["summary"]["recent_failures"]
    assert {f["service"] for f in fails} == {"espn", "ftf_api"}
    slowest = env["summary"]["slowest"]
    assert slowest[0]["ms"] == 5000
    day_rows = [r for r in env["rows"] if r["service"] == "espn"]
    assert day_rows and day_rows[0]["endpoint"] == "league_read"


def test_apihealth_service_filter_failed_espn_calls_today(obs_env):
    """'Show me all failed ESPN calls today' — one authenticated request."""
    _seed_report_rows(obs_env)
    env, _ = aq.run_report("apihealth", start="2026-08-09", end="2026-08-09",
                           service="espn")
    assert set(env["summary"]["services"]) == {"espn"}
    fails = env["summary"]["recent_failures"]
    assert len(fails) == 1
    assert fails[0]["error_kind"] == "auth"
    assert env["params"]["service"] == "espn"


def test_apihealth_dark_when_empty(obs_env):
    env, _ = aq.run_report("apihealth", start="2026-08-01", end="2026-08-02")
    assert env["rows"] == []
    assert any(c["code"] == "dark" for c in env["caveats"])
